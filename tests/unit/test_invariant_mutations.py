"""Mutate a real session by one field; exactly one invariant must notice.

The tempting version of this file generates synthetic session streams and runs
the checkers over them. That was considered and **rejected**: the checkers are
consistency rules *between* fields (`is_defeated == (death_state != "alive")`,
`dealt == max(0, total - soak)`, per-agent contiguous `call_sequence`), so a
generator that avoids firing them has to reimplement them. The test would then
assert that two copies of one rule agree — a tautology when both have the same
author, and a maintenance trap when the rule changes.

Mutation needs no rules model at all. Take a real recorded session, change one
field, and the mutation *is* the oracle. The second half — that **no other**
invariant fires — is the more valuable half, because it is exactly the
no-false-positives promise the module's docstring makes and nothing was checking
it.

Reads the committed fixtures, never `multiagent_output/` or `bulk_output/`:
those are gitignored and get cleared, and a test that breaks when someone tidies
up is not a test.
"""

import copy
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from scripts.session_invariants import ERROR, check
from scripts.session_extract import _event_body

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"

# Purpose-built base: a complete 2-round session recorded on current code, with
# **zero** invariant violations, so "no other invariant fires" is an absolute
# claim rather than a delta against legacy debt. The goldens all carry
# call_sequence debt, which would have muddied every assertion here.
#
# `llm_call` prompt/response bodies are elided — no invariant reads them, and
# keeping them made the file 568KB instead of 116KB. That makes this a
# structural fixture, not a replay source.
_REFERENCE = _FIXTURES / "mutation_base_clean.jsonl"

pytestmark = pytest.mark.skipif(not _REFERENCE.exists(),
                                reason="reference fixture absent")


def load_events(path):
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


@pytest.fixture(scope="module")
def base():
    return load_events(_REFERENCE)


def ids_of(events):
    """Multiset of invariant ids, so a duplicated finding is not mistaken for a
    new one."""
    from collections import Counter
    return Counter(v.invariant for v in check(events))


def new_findings(base_events, mutated):
    """Invariant ids the mutation introduced, over the fixture's own baseline.

    The reference fixture is not violation-free — it carries known legacy debt —
    so the delta is what matters, not the absolute count.
    """
    before, after = ids_of(base_events), ids_of(mutated)
    return {k: after[k] - before.get(k, 0) for k in after if after[k] > before.get(k, 0)}


def first(events, event_type, predicate=None):
    for i, e in enumerate(events):
        if e.get("event_type") != event_type:
            continue
        if predicate is None or predicate(_event_body(e)):
            return i
    raise AssertionError(f"fixture has no usable {event_type}")


class TestSingleFieldMutationsAreCaughtExactly:
    """Each mutation names the invariant it should trip — and only that one."""

    def test_flipping_is_defeated_trips_the_internal_consistency_check(self, base):
        m = copy.deepcopy(base)
        i = first(m, "character_state", lambda b: b.get("death_state") == "alive")
        _event_body(m[i])["is_defeated"] = True

        assert new_findings(base, m) == {"defeat_flag_internal": 1}

    def test_health_above_max_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "character_state", lambda b: b.get("max_health"))
        body = _event_body(m[i])
        body["health"] = body["max_health"] + 5

        assert new_findings(base, m) == {"hp_exceeds_max": 1}

    def test_void_out_of_bounds_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "character_state", lambda b: b.get("void_score") is not None)
        _event_body(m[i])["void_score"] = 11

        assert new_findings(base, m) == {"void_out_of_bounds": 1}

    def test_a_duplicated_session_end_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "session_end")
        m.append(copy.deepcopy(m[i]))

        assert "duplicate_session_end" in new_findings(base, m)

    def test_a_shifted_call_sequence_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "llm_call", lambda b: b.get("call_sequence") is not None)
        _event_body(m[i])["call_sequence"] += 50

        found = new_findings(base, m)

        assert "call_sequence_gap" in found or "call_sequence_collision" in found

    def test_negative_damage_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "combat_action", lambda b: (b.get("damage") or {}).get("dealt") is not None)
        _event_body(m[i])["damage"]["dealt"] = -3

        assert "damage_negative" in new_findings(base, m)

    def test_broken_soak_arithmetic_is_caught(self, base):
        m = copy.deepcopy(base)
        i = first(m, "combat_action",
                  lambda b: (b.get("damage") or {}).get("soak") is not None)
        dmg = _event_body(m[i])["damage"]
        dmg["dealt"] = (dmg.get("dealt") or 0) + 7

        assert "soak_arithmetic" in new_findings(base, m)


class TestTheUnmutatedFixtureIsStable:

    def test_checking_twice_gives_the_same_answer(self, base):
        assert ids_of(base) == ids_of(copy.deepcopy(base))

    def test_no_checker_crashes_on_a_real_session(self, base):
        crashed = [v for v in check(base) if "checker crashed" in v.message]

        assert not crashed, crashed

    def test_the_base_fixture_is_completely_clean(self, base):
        """The whole point of building this fixture rather than reusing a
        golden: a zero baseline makes every mutation assertion absolute."""
        assert check(base) == []


class TestCheckerRobustness:
    """No oracle needed: `check()` converts a crashing checker into a WARN
    (`session_invariants.py:812`), so a broken checker silently stops catching
    real violations. Malformed input must never reach that path.
    """

    def assert_no_crash(self, events):
        crashed = [v.message for v in check(events) if "checker crashed" in v.message]
        assert not crashed, crashed

    def test_empty_stream(self):
        self.assert_no_crash([])

    def test_events_with_no_event_type(self):
        self.assert_no_crash([{"round": 1}, {"data": {}}])

    @given(st.lists(st.fixed_dictionaries({
        "event_type": st.sampled_from(["character_state", "combat_action", "llm_call",
                                       "session_end", "clock_advancement"]),
        "round": st.one_of(st.none(), st.integers(min_value=-5, max_value=50)),
    }), max_size=12))
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_typed_events_with_no_payload(self, events):
        self.assert_no_crash(events)

    @pytest.mark.xfail(strict=True, reason="see #118: mixed round types crash "
                                           "inv_zombie_actor and inv_dead_targetable")
    def test_mixed_round_types_do_not_crash_a_checker(self):
        """Found by the fuzz family above on its first run.

        `_death_oracle` compares round values, so one string round alongside an
        int raises TypeError. `check()` converts that into a WARN, meaning both
        checkers silently stop looking for zombie actors and dead-targetable
        entities for the whole session — the same shape as every other defect in
        this audit: a check that quietly stops checking.

        Latent rather than live: every `round` in all 330 corpus sessions is int
        or None. xfail(strict) so this flips the moment the fix lands.
        """
        self.assert_no_crash([{"event_type": "character_state", "round": 0},
                              {"event_type": "character_state", "round": "0"}])

    @given(st.lists(st.dictionaries(
        keys=st.sampled_from(["event_type", "round", "data", "damage", "health",
                              "call_sequence", "agent_id"]),
        values=st.one_of(st.none(), st.text(max_size=4),
                         st.integers(min_value=-9, max_value=9), st.booleans(),
                         st.lists(st.integers(), max_size=2)),
        max_size=5), max_size=10))
    @settings(max_examples=200, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_arbitrary_type_confused_events(self, events):
        self.assert_no_crash(events)

    def test_a_truncated_real_session_never_crashes(self, base):
        for cut in (1, 5, len(base) // 3, len(base) // 2, len(base) - 1):
            self.assert_no_crash(base[:cut])

    def test_a_reversed_session_never_crashes(self, base):
        self.assert_no_crash(list(reversed(base)))


class TestClockWithoutSpawnIsAnError:
    """#119: it was WARN, so all 693 corpus occurrences went unread for months.

    A checker whose findings never surface in a default run is doing the work
    and throwing the answer away.
    """

    def test_severity_is_error(self, base):
        m = copy.deepcopy(base)
        i = first(m, "clock_advancement")
        _event_body(m[i])["clock_name"] = "A Clock That Was Never Born"

        found = [v for v in check(m) if v.invariant == "clock_without_spawn"]

        assert found, "mutation did not trip the checker"
        assert all(v.severity == ERROR for v in found)

    def test_it_still_fires_only_for_the_mutated_clock(self, base):
        m = copy.deepcopy(base)
        i = first(m, "clock_advancement")
        _event_body(m[i])["clock_name"] = "A Clock That Was Never Born"

        assert new_findings(base, m) == {"clock_without_spawn": 1}
