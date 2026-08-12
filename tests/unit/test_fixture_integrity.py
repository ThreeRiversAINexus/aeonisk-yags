"""Fixtures must describe states the engine can actually produce.

Why this file exists: 3,966 unit tests were green while nine defects were live,
and three of those tests were actively concealing bugs. The pattern was always
the same — a fixture that could not come out of a real run.

`create_test_player()` in test_death_save.py supplied BOTH 'Endurance' and
'Health'. No character built from a session config has a 'Health' attribute, so
`check_death_save` fell through to a hardcoded default of 3 for every player
character for eight months, and the test that existed to cover death saves could
never have caught it.

Session fixtures have a subtler version of the same problem. All eleven pass
every invariant, which reads as reassuring until you notice that ten of them are
extracted round ranges containing no `session_end`, no `end_state_snapshot` and
no `post_resolution_adjudication` — so the terminal checkers cannot fire on them
at all. Green there is absence of evidence.

These tests check the fixtures themselves, not the engine.
"""

import ast
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.session_invariants import ERROR, check

_TESTS = Path(__file__).resolve().parent.parent
_FIXTURES = _TESTS / "fixtures" / "sessions"
_REFERENCE = "golden_lawful_arrest_complete.jsonl"

# Attributes that cannot coexist on a real character. Aeonisk replaced YAGS
# 'Health' with 'Endurance'; enemy templates still ship the legacy key, but
# nothing produces both at once.
_MUTUALLY_EXCLUSIVE = ("Health", "Endurance")


def fixture_files():
    """Recursive: `sessions/golden_seed/` holds five more fixtures.

    A non-recursive glob left those five checked by nothing at all — not this
    test, and not `session_invariants.py`/`schema_mine.py`, which globbed
    `session_*.jsonl` and skipped them on the filename too. One of them
    (`golden_seed_combat.jsonl`) had been freezing a zombie_actor violation the
    whole time.
    """
    return sorted(_FIXTURES.rglob("*.jsonl"))


def load_events(path):
    events = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


# Fixtures captured 2025-12-01, before the call_sequence stamp-authority fix.
# Every one has llm_call sequences of [0, 0, 0, ...] per agent, so each cached
# call overwrites the last — real data loss in the replay cache. The engine no
# longer does this (the reference golden shows dm_01 at 0..27, all unique), but
# these files preserve the old behaviour and cannot be cleaned without
# regeneration.
#
# Listed explicitly rather than skipped silently: a quiet allowlist is how the
# invariant runner came to report "Scanned 0 complete sessions ... 0 with
# ERROR-severity" over the whole fixture corpus and exit 0.
LEGACY_CALL_SEQUENCE_DEBT = {
    "golden_clock_lifecycle_complete.jsonl",
    "golden_npc_deescalation.jsonl",
    "golden_npc_escalation_lifecycle.jsonl",
    "negative_health_bug.jsonl",
    "regression_soulcredit_logging_bug.jsonl",
    "replay_test_fresh.jsonl",
    "session_debt_auction_ambush.jsonl",
    "session_starting_clocks.jsonl",
    "session_status_effect_narrative_test.jsonl",
    "session_status_effect_tactical_test.jsonl",
    "session_void_story_advancement_partial.jsonl",
    # Only visible once fixture_files() went recursive; same [0, 0, ...] shape.
    "golden_seed_combat.jsonl",
    "golden_seed_conversion.jsonl",
    "golden_seed_ritual.jsonl",
    "golden_seed_social.jsonl",
    "golden_seed_vendor.jsonl",
}

# Debt that is NOT call_sequence: a fixture freezing a genuine engine bug.
# `golden_seed_combat.jsonl` has "r3 [Enforcer Kael Dren]: dealt 10 damage while
# defeated" — a defeated entity acting. It sat unchecked because the fixture
# lived in a subdirectory the test never walked.
#
# Recorded per-file and per-invariant rather than waived wholesale, so the
# amnesty cannot silently widen. It goes away when the fixture is re-recorded.
LEGACY_INVARIANT_DEBT = {
    "golden_seed_combat.jsonl": {"zombie_actor", "clock_without_spawn"},
    # clock_without_spawn was raised WARN -> ERROR in #119. Every occurrence
    # predates 0898af3 (2026-08-09 06:52), which moved log_clock_spawn into
    # create_scene_clock — the single chokepoint — so these recordings show
    # clocks that genuinely existed but were never announced. Unfixable without
    # re-recording; the condition is impossible under current code.
    "golden_clock_lifecycle_complete.jsonl": {"clock_without_spawn"},
    "golden_seed_social.jsonl": {"clock_without_spawn"},
    "negative_health_bug.jsonl": {"clock_without_spawn"},
    "regression_soulcredit_logging_bug.jsonl": {"clock_without_spawn"},
    "session_debt_auction_ambush.jsonl": {"clock_without_spawn"},
    "session_starting_clocks.jsonl": {"clock_without_spawn"},
    "session_void_story_advancement_partial.jsonl": {"clock_without_spawn"},
}

# harm_unrecorded (#150) is separated out because it is not one bug but two,
# both since fixed, and neither reachable by editing a recording:
#
#   * enemies gated on `is_active` (#138) — an enemy stopped being snapshotted
#     at the moment it was defeated;
#   * NPCs deleted from `npc_agents` in the entity-lifecycle phase, which runs
#     before the round-end snapshot (#150), so an NPC harmed and removed in the
#     same round was never written down at all.
#
# Nine recordings carry the consequence: something took combat damage and has no
# `character_state` row anywhere in the file, so its fate is unknowable from the
# oracle. Listed per file, and merged into the ledger above rather than added to
# it by hand, so re-recording any one of them retires its exemption on its own.
LEGACY_HARM_UNRECORDED = {
    "golden_clock_lifecycle_complete.jsonl",   # 4
    "golden_npc_deescalation.jsonl",           # 1
    "golden_seed_combat.jsonl",                # 1
    "negative_health_bug.jsonl",               # 2
    "regression_soulcredit_logging_bug.jsonl", # 1
    "replay_test_fresh.jsonl",                 # 1
    "session_debt_auction_ambush.jsonl",       # 4
    "session_status_effect_narrative_test.jsonl",  # 2
    "session_void_story_advancement_partial.jsonl",  # 1
    # Not legacy: recorded 2026-08-12 *because* it violates. The ten-event chain
    # from session 81125d33 in which a subdued prisoner is shot for 19 wound
    # damage and removed in the same round. See test_harm_is_recorded.py — it is
    # the evidence, and it must keep failing.
    "harm_unrecorded_chain.jsonl",
}

for _name in LEGACY_HARM_UNRECORDED:
    LEGACY_INVARIANT_DEBT.setdefault(_name, set()).add("harm_unrecorded")


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_has_no_invariant_errors(path):
    """A fixture that violates an invariant encodes buggy behaviour.

    Freezing such a file as 'golden' teaches every test that reads it that the
    bug is correct. Known legacy debt is allowed only for `call_sequence_collision`
    and only on the pre-2025-12-01 files — any other violation, or any violation
    on a newer fixture, fails.
    """
    violations = [v for v in check(load_events(path)) if v.severity == ERROR]

    if path.name in LEGACY_CALL_SEQUENCE_DEBT:
        violations = [v for v in violations
                      if v.invariant != "call_sequence_collision"]

    waived = LEGACY_INVARIANT_DEBT.get(path.name, set())
    if waived:
        violations = [v for v in violations if v.invariant not in waived]

    assert not violations, (
        f"{path.name} violates invariants:\n  " +
        "\n  ".join(str(v) for v in violations))


def test_legacy_debt_list_has_no_stale_entries():
    """Regenerate a fixture and its exemption must go with it.

    Otherwise the allowlist quietly grants amnesty to files that no longer need
    it, and a real regression hides behind a stale exemption.
    """
    by_name = {p.name: p for p in fixture_files()}
    stale = []
    for name in sorted(LEGACY_CALL_SEQUENCE_DEBT):
        path = by_name.get(name)
        if path is None:
            stale.append(f"{name} (file is gone)")
            continue
        collisions = [v for v in check(load_events(path))
                      if v.invariant == "call_sequence_collision"]
        if not collisions:
            stale.append(f"{name} (no longer collides — drop the exemption)")

    assert not stale, "stale entries in LEGACY_CALL_SEQUENCE_DEBT:\n  " + "\n  ".join(stale)


def test_invariant_debt_list_has_no_stale_entries():
    """The same rule for the non-call_sequence waivers.

    A waived invariant that no longer fires is amnesty for a bug nobody is
    committing any more — and it would hide the next one that fires.
    """
    by_name = {p.name: p for p in fixture_files()}
    stale = []
    for name, waived in sorted(LEGACY_INVARIANT_DEBT.items()):
        path = by_name.get(name)
        if path is None:
            stale.append(f"{name} (file is gone)")
            continue
        firing = {v.invariant for v in check(load_events(path))
                  if v.severity == ERROR}
        for invariant in sorted(waived - firing):
            stale.append(f"{name}:{invariant} (no longer fires — drop it)")

    assert not stale, "stale entries in LEGACY_INVARIANT_DEBT:\n  " + "\n  ".join(stale)


class TestReferenceFixtureIsWhole:
    """At least one fixture must be able to exercise the terminal checkers.

    Ten of eleven are extracts. `duplicate_session_end`,
    `snapshot_oracle_mismatch` and `enforce_ruling_dropped` need events those
    extracts do not contain, so before this fixture existed those three checkers
    were never exercised by any fixture at all.
    """

    @pytest.fixture(scope="class")
    def events(self):
        path = _FIXTURES / _REFERENCE
        if not path.exists():
            pytest.skip(f"{_REFERENCE} not present")
        return load_events(path)

    def test_reference_fixture_exists(self):
        assert (_FIXTURES / _REFERENCE).exists(), (
            "the reference golden is the only whole-session fixture; without it "
            "the terminal invariants have no data in the test suite")

    @pytest.mark.parametrize("event_type", [
        "session_end", "end_state_snapshot", "post_resolution_adjudication",
        "character_state", "combat_action",
    ])
    def test_carries_terminal_events(self, events, event_type):
        counts = Counter(e.get("event_type") for e in events)

        assert counts[event_type] > 0, (
            f"reference fixture has no {event_type}; the checkers that read it "
            f"would be silently unexercised")

    def test_covers_all_three_entity_kinds(self, events):
        """NPCs were absent from the oracle entirely until #89 — the fixture has
        to prove all three kinds are recorded."""
        kinds = Counter(e.get("agent") for e in events
                        if e.get("event_type") == "character_state")

        assert {"player", "enemy", "npc"} <= set(kinds), (
            f"reference fixture covers only {sorted(k for k in kinds if k)}")

    def test_demonstrates_a_non_lethal_resolution(self, events):
        """The artifact of the II.8 subdue path working. If this ever goes to
        zero, the lawful off-ramp has regressed."""
        stun_hits = [
            e for e in events
            if e.get("event_type") == "combat_action"
            and ((e.get("damage") or {}).get("damage_type") == "stun")
        ]

        assert stun_hits, "reference fixture no longer shows a non-lethal takedown"
        assert all((e.get("wounds_dealt") or 0) == 0 for e in stun_hits)


class TestNoImpossibleCharacterShapes:
    """No test may construct a character that cannot exist."""

    def _offenders(self):
        """Dict literals carrying BOTH keys at once.

        Deliberately per-literal, not per-file: a fixture passing only 'Health'
        is a legitimate test of the legacy fallback that enemy templates still
        rely on. The impossible shape is one character holding both.
        """
        hits = []
        for path in sorted((_TESTS / "unit").glob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                if set(_MUTUALLY_EXCLUSIVE) <= keys:
                    hits.append(f"{path.name}:{node.lineno}")
        return hits

    def test_no_character_carries_both_health_and_endurance(self):
        offenders = self._offenders()

        assert not offenders, (
            "these build a character with both 'Health' and 'Endurance' — a shape "
            "no session config can produce. That exact fixture hid #82 for eight "
            "months: every player death save silently rolled a hardcoded 3, and "
            "the test suite covering death saves could not have caught it because "
            "its character was not one the engine makes.\n  "
            + "\n  ".join(offenders))
