"""Properties of the round-synthesis validator.

`validate_outcome_synthesis` is the densest self-contained validator in the
codebase — 18 distinct error conditions — and it decides whether a round
narrates at all (`dm.py:4552`, bounded retry, then `RoundSynthesisFailClosed`).

Two facts about it that are easy to get wrong, and which I did get wrong
before reading it properly:

* **It raises rather than returning errors.** The returned list is *style
  warnings*; errors go out as `SynthesisValidationError.errors` (`:861`).
* **It mutates its input.** Before validating it sorts each segment's
  `source_outcome_ids` and rewrites coverage dispositions, appending
  `auto-repair:` warnings (`:669-698`).

The centrepiece here is an **inverse pair**. E17 says a soft state claim with no
matching observable fact is an error; E18 says a qualifying fact with no state
claim is an error. Build a synthesis deriving exactly one claim per qualifying
fact and both must be silent — then drop one claim and *only* E18 fires, add a
spurious one and *only* E17 fires. That needs no model of the game's rules,
which is what makes it a property rather than a restatement of the code.
"""

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.aeonisk.multiagent.outcome_pipeline import (
    _MECHANICS_LEAK_PATTERNS, _severity, AppliedOutcome, CoverageEntry,
    EntityStateSnapshot, NarrativeSegment, ObservableFact, OutcomeRoundSynthesis,
    StateClaim, SynthesisValidationError, canonicalize_viewer_ids,
    reset_outcome_ids, validate_outcome_synthesis,
)

# Facts that oblige a matching state claim (outcome_pipeline.py:848).
CLAIMABLE = ("damage", "healing", "condition", "movement", "dialogue")


@pytest.fixture(autouse=True)
def stable_ids():
    """AppliedOutcome mints ids from a module-global counter, so without this
    ids drift between tests and cross-test comparisons stop meaning anything."""
    reset_outcome_ids()


def snapshot(entity_id="npc_1", health=20, **kw):
    return EntityStateSnapshot(
        entity_id=entity_id, entity_type=kw.pop("entity_type", "npc"),
        name=kw.pop("name", "Guard"), narrative_name=kw.pop("narrative_name", "the guard"),
        health=health, max_health=kw.pop("max_health", 20), **kw)


def fact(kind="damage", subject="npc_1", actor="player_01"):
    return ObservableFact(fact_kind=kind, subject_id=subject, causing_actor_id=actor,
                          prose_safe_summary=f"{kind} befell {subject}")


def outcome(facts=None, actor="player_01", sequence=0, **kw):
    return AppliedOutcome(
        round=1, sequence=sequence, actor_id=actor, actor_name="Nera",
        actor_narrative_name="Nera", intent="act",
        observable_facts=facts if facts is not None else [],
        entity_states_after=kw.pop("after", {}), **kw)


def claims_for(outcomes):
    """One state claim per qualifying fact — the shape the validator wants."""
    out = []
    for o in outcomes:
        for f in o.observable_facts:
            kind = "damage" if f.fact_kind == "unconscious" else f.fact_kind
            if kind not in CLAIMABLE and kind != "death":
                continue
            out.append(StateClaim(
                claim_kind="life_state" if kind == "death" else kind,
                subject_id=f.subject_id, causing_actor_id=f.causing_actor_id,
                source_outcome_id=o.outcome_id, symbolic_value="noted"))
    return out


# RoundSynthesis.narration requires at least 100 characters, and the text is
# also what the mechanics-leak patterns scan, so the default has to be both long
# and clean.
CLEAN_PROSE = ("The corridor stills, and the lattice light goes thin against the "
               "far wall while the guard steadies himself and says nothing at all.")


def synthesis_for(outcomes, state_claims=None, text=CLEAN_PROSE):
    seg = NarrativeSegment(segment_id="seg_1", text=text,
                           source_outcome_ids=[o.outcome_id for o in outcomes])
    return OutcomeRoundSynthesis(
        narration=text, segments=[seg],
        coverage=[CoverageEntry(outcome_id=o.outcome_id, disposition="rendered",
                                segment_id="seg_1") for o in outcomes],
        state_claims=claims_for(outcomes) if state_claims is None else state_claims)


def errors_from(synthesis, outcomes):
    try:
        validate_outcome_synthesis(synthesis, outcomes)
        return []
    except SynthesisValidationError as exc:
        return exc.errors


class TestTheClaimFactInversePair:
    """E17 and E18 are converses; a correct synthesis satisfies both at once."""

    @given(kinds=st.lists(st.sampled_from(CLAIMABLE), min_size=1, max_size=5))
    @settings(max_examples=60, deadline=None)
    def test_one_claim_per_fact_is_silent(self, kinds):
        o = outcome([fact(kind=k, subject=f"npc_{i}") for i, k in enumerate(kinds)])

        assert errors_from(synthesis_for([o]), [o]) == []

    @given(kinds=st.lists(st.sampled_from(CLAIMABLE), min_size=2, max_size=5))
    @settings(max_examples=60, deadline=None)
    def test_dropping_one_claim_fires_exactly_one_error(self, kinds):
        """E18, isolated: the missing claim is named and nothing else complains."""
        o = outcome([fact(kind=k, subject=f"npc_{i}") for i, k in enumerate(kinds)])
        full = claims_for([o])
        s = synthesis_for([o], state_claims=full[1:])

        errs = errors_from(s, [o])

        assert len(errs) == 1, errs
        assert "lacks a state claim" in errs[0]

    def test_a_spurious_claim_fires_exactly_one_error(self):
        """E17, isolated: a claim with no fact behind it."""
        o = outcome([fact(kind="damage")])
        s = synthesis_for([o], state_claims=claims_for([o]) + [
            StateClaim(claim_kind="movement", subject_id="npc_1",
                       causing_actor_id="player_01", source_outcome_id=o.outcome_id,
                       symbolic_value="drifted")])

        errs = errors_from(s, [o])

        assert len(errs) == 1, errs
        assert "lacks an applied fact" in errs[0]

    def test_an_other_claim_never_needs_a_fact(self):
        """The documented escape hatch for attitude and social observation."""
        o = outcome([fact(kind="damage")])
        s = synthesis_for([o], state_claims=claims_for([o]) + [
            StateClaim(claim_kind="other", subject_id="npc_1",
                       causing_actor_id="player_01", source_outcome_id=o.outcome_id,
                       symbolic_value="wary")])

        assert errors_from(s, [o]) == []

    def test_unconscious_is_satisfied_by_a_damage_claim(self):
        """An explicit alias in the validator (`:824`), worth pinning."""
        o = outcome([fact(kind="unconscious")])
        s = synthesis_for([o], state_claims=[
            StateClaim(claim_kind="damage", subject_id="npc_1",
                       causing_actor_id="player_01", source_outcome_id=o.outcome_id,
                       symbolic_value="felled")])

        assert errors_from(s, [o]) == []


class TestOrderIndependence:
    """Shuffling inputs must not change *which* errors fire."""

    @given(perm=st.permutations(range(4)))
    @settings(max_examples=24, deadline=None)
    def test_claim_order_does_not_change_the_error_set(self, perm):
        o = outcome([fact(kind=k, subject=f"npc_{i}")
                     for i, k in enumerate(CLAIMABLE[:4])])
        base = claims_for([o])
        shuffled = [base[i] for i in perm]

        assert set(errors_from(synthesis_for([o], state_claims=shuffled), [o])) == \
            set(errors_from(synthesis_for([o], state_claims=base), [o]))

    def test_missing_claims_are_reported_once_each(self):
        o = outcome([fact(kind=k, subject=f"npc_{i}")
                     for i, k in enumerate(CLAIMABLE[:3])])

        errs = errors_from(synthesis_for([o], state_claims=[]), [o])

        assert len(errs) == 3


class TestAutoRepairSettles:
    """It mutates its input, so a second pass must be a no-op."""

    def test_validating_twice_does_not_raise(self):
        o = outcome([fact(kind="damage")])
        s = synthesis_for([o])

        validate_outcome_synthesis(s, [o])
        validate_outcome_synthesis(s, [o])

    def test_the_second_pass_emits_no_auto_repair_warnings(self):
        o = outcome([fact(kind="damage")], consequential=True)
        s = synthesis_for([o])
        s.coverage[0].disposition = "omitted_nonconsequential"

        first = validate_outcome_synthesis(s, [o])
        second = validate_outcome_synthesis(s, [o])

        assert any("auto-repair" in w for w in first)
        assert not any("auto-repair" in w for w in second)


class TestMechanicsLeakPatterns:
    """Mechanics in prose is the stated quality dealbreaker, so these are
    characterised honestly — including where they over-match."""

    def leaks(self, text):
        return [label for pattern, label in _MECHANICS_LEAK_PATTERNS
                if pattern.search(text)]

    @pytest.mark.parametrize("text,label", [
        ("she was down to 22/30", "raw HP fraction"),
        ("he took 8 hp", "raw HP value"),
        ("three became 3 wounds", "raw counter"),
        ("the check was DC 18", "roll mechanics"),
        ("it lunged at tgt_a1b2", "target ID"),
        ("[round 4] the door gave", "round/turn label"),
    ])
    def test_each_pattern_catches_its_case(self, text, label):
        assert label in self.leaks(text)

    def test_clean_prose_leaks_nothing(self):
        assert self.leaks("The lattice hummed, and Nera stepped back into the dark.") == []

    def test_a_bare_fraction_is_treated_as_a_leak(self):
        """Documented, not endorsed: the unit is optional in pattern 1, so
        in-fiction fractions read as raw HP. Recorded so that a future change
        here is a deliberate decision rather than a surprise."""
        assert "raw HP fraction" in self.leaks("3/4 of the crowd turned away")

    @given(n=st.integers(min_value=0, max_value=99))
    def test_any_wound_count_is_caught(self, n):
        assert "raw counter" in self.leaks(f"he bore {n} wounds")


class TestCanonicalizeViewerIds:

    ROSTER = {"player_01": "Nera Mereth", "npc_1": "Guard"}

    @given(ids=st.lists(st.sampled_from(["player_01", "npc_1", "dm", "gm", "nobody"]),
                        max_size=6))
    @settings(max_examples=60, deadline=None)
    def test_is_idempotent(self, ids):
        once = canonicalize_viewer_ids(ids, self.ROSTER)

        assert canonicalize_viewer_ids(once, self.ROSTER) == once

    @given(ids=st.lists(st.sampled_from(["player_01", "npc_1", "dm", "junk"]), max_size=6))
    @settings(max_examples=60, deadline=None)
    def test_output_is_a_subset_of_the_roster_plus_dm(self, ids):
        assert set(canonicalize_viewer_ids(ids, self.ROSTER)) <= \
            set(self.ROSTER) | {"dm"}

    @given(ids=st.lists(st.sampled_from(["player_01", "npc_1", "dm"]), max_size=8))
    @settings(max_examples=60, deadline=None)
    def test_never_returns_duplicates(self, ids):
        out = canonicalize_viewer_ids(ids, self.ROSTER)

        assert len(out) == len(set(out))


class TestSeverity:

    @given(health=st.integers(min_value=0, max_value=40),
           max_health=st.integers(min_value=1, max_value=40))
    def test_is_total(self, health, max_health):
        assert _severity(snapshot(health=health, max_health=max_health))

    @given(max_health=st.integers(min_value=1, max_value=40))
    def test_never_divides_by_zero_on_a_missing_maximum(self, max_health):
        assert _severity(snapshot(health=None, max_health=None))

    def test_the_dead_are_always_critical(self):
        assert _severity(snapshot(health=20, life_state="dead")) == "critical"

    @given(health=st.integers(min_value=1, max_value=40))
    def test_severity_never_improves_as_health_falls(self, health):
        rank = {"minor": 0, "moderate": 1, "severe": 2, "critical": 3}
        high = _severity(snapshot(health=health, max_health=40))
        low = _severity(snapshot(health=max(health - 5, 0), max_health=40))

        assert rank[low] >= rank[high]
