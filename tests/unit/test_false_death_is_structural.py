"""The false-death guard, moved off prose and onto claims (#142).

The old guard was a regex over narration:

    _DEATH_LANGUAGE = re.compile(r"\\b(?:dead|dies?|died|killed|corpse|...)\\b")
    if living_changed and not actual_death and _DEATH_LANGUAGE.search(segment.text):

`\\bdies?\\b` matches "die" in "no one needs to die", so session 234ba3f1 aborted
at round 1 on this line:

    "Easy—Confessor's orders. You're coming with us, no one needs to die," Corin says

An officer mid-arrest promising *not* to kill anyone is the most on-doctrine
sentence a II.8 lawful subdue can produce, and it failed the round closed three
retries running. The guard fired hardest on the branch the violence probes exist
to observe: kill everyone and `actual_death` is true so the check never runs;
subdue someone and say so, and the session dies.

The pipeline already had the right mechanism forty-five lines below. The engine
writes `entity_states_after[...].life_state`, the narrator files a
`StateClaim(claim_kind="life_state", ...)`, and the validator compares the two
typed fields. Exact, language-independent, no false positives — the codebase's
own "structured output over keyword detection" rule, which the regex violated.

What remains is the half the regex was really covering: prose that asserts a
death while filing no claim at all. The structural answer is to make the claim
mandatory whenever a rendered outcome actually changes `life_state`, so a real
death can never go unnarrated-but-unclaimed, and every claim is value-checked.

Not covered, stated plainly: prose inventing a death for an entity whose state
never changed, with no claim filed. There is no structured signal for that
without reading the text, and the trade is deliberate — a narrow uncovered case
in exchange for a guard that no longer aborts sessions on correct behaviour.
"""

import pytest

from aeonisk.multiagent.outcome_pipeline import (
    CoverageEntry, EntityStateSnapshot, NarrativeSegment,
    OutcomeRoundSynthesis, StateClaim, SynthesisValidationError,
    validate_outcome_synthesis,
)

from tests.unit.test_outcome_pipeline import _outcome, _state, _synthesis


DE_ESCALATION = (
    "\"Easy—Confessor's orders. You're coming with us, no one needs to die,\" "
    "Corin says, his voice calm but unyielding. The dart hisses across the "
    "chamber and buries itself in the Matron's shoulder. She staggers, then her "
    "knees buckle beneath her."
)


def _fatal_outcome():
    """An outcome where life_state genuinely changes alive -> dead."""
    outcome = _outcome()
    outcome.entity_states_before = {"enemy_vane": _state(health=4)}
    outcome.entity_states_after = {
        "enemy_vane": _state(health=0, life_state="dead", combat_state="defeated")
    }
    return outcome


def _claim(outcome, subject="enemy_vane", value="dead", kind="life_state"):
    return StateClaim(
        claim_kind=kind,
        subject_id=subject,
        causing_actor_id=outcome.actor_id,
        source_outcome_id=outcome.outcome_id,
        symbolic_value=value,
    )


class TestRestraintNoLongerKillsTheSession:
    """The #142 regression, stated as the sentence that caused it."""

    def test_a_promise_not_to_kill_is_accepted(self):
        outcome = _outcome()

        validate_outcome_synthesis(_synthesis(DE_ESCALATION, outcome), [outcome])

    @pytest.mark.parametrize("line", [
        "\"No one needs to die here,\" she says, lowering the barrel.",
        "\"You don't have to die for this contract.\"",
        "\"She won't die — the dart is a sedative, nothing more.\"",
        "\"Nobody gets killed today. Stand down.\"",
    ])
    def test_negated_death_language_in_dialogue_is_accepted(self, line):
        outcome = _outcome()
        text = (line + " The chamber settles into a wary quiet around them, "
                "dust drifting through the lamplight while nobody reaches for "
                "a weapon and the moment holds.")

        validate_outcome_synthesis(_synthesis(text, outcome), [outcome])


class TestAClaimedDeathIsCheckedAgainstTheOracle:
    """The mechanism that replaces the regex: typed field vs typed field."""

    def test_claiming_death_for_a_living_entity_is_rejected(self):
        outcome = _outcome()
        synthesis = _synthesis("Vane goes still on the rain-dark stones while the witnesses retreat behind their shutters, leaving the alley to its long grey quiet.", outcome)
        synthesis.state_claims = [_claim(outcome, value="dead")]

        with pytest.raises(SynthesisValidationError, match="contradicts"):
            validate_outcome_synthesis(synthesis, [outcome])

    def test_claiming_death_for_a_dead_entity_is_accepted(self):
        outcome = _fatal_outcome()
        synthesis = _synthesis("Vane falls where he stood, and does not rise again. The alley holds its breath around the shape on the wet stones, and no one moves to help him.", outcome)
        synthesis.state_claims = [_claim(outcome, value="dead")]

        validate_outcome_synthesis(synthesis, [outcome])


class TestARealDeathMustBeClaimed:
    """The half the regex was actually covering, done structurally.

    Without this, dropping the text scan would let a narrator render a genuine
    death with no typed record of it, and nothing downstream could tell.
    """

    def test_an_unclaimed_life_state_change_is_rejected(self):
        outcome = _fatal_outcome()

        with pytest.raises(SynthesisValidationError, match="life_state"):
            validate_outcome_synthesis(
                _synthesis("Vane falls where he stood, and does not rise again. The alley holds its breath around the shape on the wet stones, and no one moves to help him.", outcome), [outcome])

    def test_the_error_names_the_subject_and_the_outcome(self):
        outcome = _fatal_outcome()
        try:
            validate_outcome_synthesis(
                _synthesis("Vane falls where he stood, and does not rise again. The alley holds its breath around the shape on the wet stones, and no one moves to help him.", outcome), [outcome])
        except SynthesisValidationError as exc:
            assert "enemy_vane" in str(exc) and outcome.outcome_id in str(exc)
        else:
            pytest.fail("expected the unclaimed life_state change to be rejected")

    def test_a_claim_of_the_wrong_kind_does_not_satisfy_it(self):
        outcome = _fatal_outcome()
        synthesis = _synthesis("Vane falls where he stood, and does not rise again. The alley holds its breath around the shape on the wet stones, and no one moves to help him.", outcome)
        synthesis.state_claims = [_claim(outcome, kind="other", value="grim")]

        with pytest.raises(SynthesisValidationError, match="life_state"):
            validate_outcome_synthesis(synthesis, [outcome])

    def test_an_omitted_outcome_needs_no_claim(self):
        """An outcome with no prose has nothing to be false about.

        Without this carve-out the requirement fires on outcomes the synthesis
        deliberately did not render, which would fail rounds for narrating
        *less* — the mirror of the bug being fixed.
        """
        rendered = _outcome(sequence=1)
        omitted = _fatal_outcome()
        omitted.outcome_id = "out_2"
        omitted.sequence = 2
        omitted.consequential = False
        text = ("The square empties as the patrol moves on, and the long "
                "afternoon light finds nothing left worth reporting to anyone "
                "still listening at the gate.")
        synthesis = OutcomeRoundSynthesis(
            narration=text,
            segments=[NarrativeSegment(
                segment_id="beat_1", text=text,
                source_outcome_ids=[rendered.outcome_id],
            )],
            coverage=[
                CoverageEntry(outcome_id=rendered.outcome_id,
                              disposition="rendered", segment_id="beat_1"),
                CoverageEntry(outcome_id=omitted.outcome_id,
                              disposition="omitted_nonconsequential"),
            ],
        )

        validate_outcome_synthesis(synthesis, [rendered, omitted])

    def test_an_unchanged_life_state_needs_no_claim(self):
        """A wounding, a stunning, an arrest — the ordinary case, and the one
        the old guard punished for saying the word."""
        outcome = _outcome()

        validate_outcome_synthesis(_synthesis(DE_ESCALATION, outcome), [outcome])
