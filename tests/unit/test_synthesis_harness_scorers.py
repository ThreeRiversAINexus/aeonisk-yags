"""Scoring a synthesis variant without paying a judge to state the obvious (#158).

Three scorers, and the division between them is the point. Two are exact
measurements against recorded text. The first is the engine's own contract:
`validate_outcome_synthesis` is the same function the live session runs, so a
response it rejects would have been rejected in play — that is an oracle, not an
opinion, and it costs nothing.

What is left for a frontier judge is only the part with no oracle: whether the
prose is *better*, rather than merely less repetitive. That is a small
stratified sample, not a pass over 245 cases.

The scorers are checked against the real recorded responses from `3de9e609`,
where the answers are known by hand: round 3 carries exactly two validation
warnings (out-of-chronological-order, and one outcome rendered by two segments),
its opening is 0.81 similar to round 2's, and the narration grows 1611 → 2105 →
3143 characters.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "scripts"))

from scripts.prompt_eval_harness import (  # noqa: E402
    CASE_KINDS, OPENING_CHARS, SCORER_REGISTRY, SYNTHESIS, MechanicalExtractor,
    SynthesisGrowthScorer, SynthesisRepetitionScorer, SynthesisValidationScorer,
    EvalCase, synthesis_inputs_for_round,
)

CHAIN = pathlib.Path(__file__).parent.parent / "fixtures/sessions/synthesis_repetition_chain.jsonl"


def _events_by_round():
    by_round = {}
    for line in CHAIN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("round") is not None:
            by_round.setdefault(event["round"], []).append(event)
    return by_round


def _recorded_case(round_num):
    """A case built from the recording, response and all — the round's own
    answer is the thing being scored."""
    by_round = _events_by_round()
    rebuilt = synthesis_inputs_for_round(by_round, round_num)
    response = ""
    for event in by_round.get(round_num, []):
        body = event.get("data") if isinstance(event.get("data"), dict) else event
        if event.get("event_type") == "llm_call" and "OutcomeRoundSynthesis" in str(
                body.get("call_type")):
            response = body.get("response") or ""
    return EvalCase(
        case_id=f"r{round_num}", session_file=str(CHAIN), condition="unknown",
        round_num=round_num, original_model="gpt-5.4-mini", system_prompt="sys",
        user_prompt="user", response_text=response, action_type=None,
        player_action_text=None, margin=None, kind_name="synthesis",
        synthesis_inputs=rebuilt[0] if rebuilt else None,
        synthesis_outcomes=rebuilt[1] if rebuilt else None)


def _fields(round_num):
    case = _recorded_case(round_num)
    parsed = MechanicalExtractor.parse_response(case.response_text)
    return SYNTHESIS.extract(parsed, case), case


class TestTheExtractorReadsWhatTheEngineReads:

    def test_a_recorded_response_is_schema_valid_and_measured(self):
        fields, _ = _fields(3)

        assert fields["schema_valid"] is True
        assert fields["segment_count"] == 4
        assert fields["narration_chars"] == 3143

    def test_round_three_carries_exactly_its_two_known_warnings(self):
        """Named by hand in #156 before any of this existed: a segment out of
        chronological order, and one outcome rendered by two segments."""
        fields, _ = _fields(3)

        assert fields["validation_errors"] == []
        assert len(fields["validation_warnings"]) == 2
        assert any("chronological" in w for w in fields["validation_warnings"])
        assert any("multiple segments" in w for w in fields["validation_warnings"])

    def test_a_clean_round_carries_none(self):
        fields, _ = _fields(1)

        assert fields["validation_errors"] == []
        assert fields["validation_warnings"] == []

    def test_the_engine_validator_really_does_mutate_its_argument(self):
        """Why the extractor validates a copy.

        This is the hazard, asserted rather than assumed: the validator sorts
        `source_outcome_ids` and auto-repairs coverage in place. Anything that
        reported fields off the post-validation object would be crediting the
        prompt for repairs the engine performed on its behalf. Nothing does
        today, and this test is what makes that stay a deliberate choice.
        """
        from aeonisk.multiagent.outcome_pipeline import (
            AppliedOutcome, OutcomeRoundSynthesis, validate_outcome_synthesis)

        case = _recorded_case(3)
        parsed = MechanicalExtractor.parse_response(case.response_text)
        synthesis = OutcomeRoundSynthesis.model_validate(parsed)
        outcomes = [AppliedOutcome.model_validate(o) for o in case.synthesis_outcomes]
        before = [list(seg.source_outcome_ids) for seg in synthesis.segments]

        validate_outcome_synthesis(synthesis, outcomes)

        after = [list(seg.source_outcome_ids) for seg in synthesis.segments]
        assert before != after or any(
            entry.disposition for entry in synthesis.coverage)

    def test_scoring_the_same_case_twice_gives_the_same_answer(self):
        """Catches aliasing of any kind: if scoring left a mark on the case, the
        outcomes, or the parsed response, a second pass would disagree — and an
        optimiser comparing arms would read that drift as a prompt effect."""
        case = _recorded_case(3)
        parsed = MechanicalExtractor.parse_response(case.response_text)

        first = SYNTHESIS.extract(parsed, case)
        second = SYNTHESIS.extract(parsed, case)

        assert first == second

    def test_an_unparseable_response_is_the_worst_score_not_a_gap(self):
        """A response the schema rejects never reached the narrator, so it must
        register as a failure rather than as a missing measurement."""
        case = _recorded_case(3)

        fields = SYNTHESIS.extract({"narration": "too short"}, case)

        assert fields["schema_valid"] is False
        assert fields["validation_errors"]

    def test_an_empty_response_does_not_crash(self):
        assert SYNTHESIS.extract({}, _recorded_case(3))["schema_valid"] is False

    def test_a_case_without_ground_truth_reports_no_validation(self):
        """Coverage cannot be judged against outcomes we do not have; silence
        is the honest answer, not zero errors."""
        case = _recorded_case(3)
        case.synthesis_outcomes = []
        parsed = MechanicalExtractor.parse_response(case.response_text)

        fields = SYNTHESIS.extract(parsed, case)

        assert fields["schema_valid"] is True
        assert fields["validation_errors"] == []
        assert fields["validation_warnings"] == []


class TestValidationScorer:

    def test_a_clean_round_scores_clean(self):
        fields, case = _fields(1)

        score = SynthesisValidationScorer().score(fields, fields, case)

        assert score["clean"] is True
        assert (score["replay_errors"], score["replay_warnings"]) == (0, 0)

    def test_warnings_do_not_make_a_round_dirty(self):
        """Warnings are style; errors are the contract. Conflating them would
        make every stylistic preference block a variant."""
        fields, case = _fields(3)

        score = SynthesisValidationScorer().score(fields, fields, case)

        assert score["replay_warnings"] == 2
        assert score["clean"] is True

    def test_it_reports_a_delta_against_the_original(self):
        """A variant is measured as a change, not against an absolute nobody
        has calibrated."""
        original, case = _fields(1)
        replay = dict(original, validation_errors=["a", "b"])

        score = SynthesisValidationScorer().score(original, replay, case)

        assert score["error_delta"] == 2
        assert score["clean"] is False


class TestRepetitionScorer:
    """The defect itself: how much of this round's opening is the last one's."""

    def test_it_reproduces_the_measured_drift(self):
        for round_num, expected in ((2, 0.53), (3, 0.81)):
            fields, case = _fields(round_num)

            score = SynthesisRepetitionScorer().score(fields, fields, case)

            assert score["replay_similarity"] == pytest.approx(expected, abs=0.01)

    def test_the_opening_round_has_nothing_to_repeat(self):
        fields, case = _fields(1)

        score = SynthesisRepetitionScorer().score(fields, fields, case)

        assert score["has_prior"] is False
        assert score["replay_similarity"] == 0.0

    def test_a_verbatim_repeat_is_flagged_identical(self):
        """22% of corpus round pairs do exactly this."""
        _, case = _fields(3)
        prior = case.synthesis_inputs["previous_ending"]
        replay = {"narration": prior}

        score = SynthesisRepetitionScorer().score(replay, replay, case)

        assert score["replay_identical"] is True
        assert score["replay_similarity"] == 1.0

    def test_a_shared_tail_does_not_count_as_repetition(self):
        """Two rounds ending in the same room is fine — returning to a place is
        not the defect. Opening on the same sentence is. Only the first
        OPENING_CHARS are compared, so text beyond the window is invisible
        however much of it two rounds share.
        """
        _, case = _fields(3)
        prior = case.synthesis_inputs["previous_ending"]
        fresh = "Rain hammers the freight yard and nobody moves a muscle now. " * 3

        score = SynthesisRepetitionScorer().score(
            {"narration": fresh + prior}, {"narration": fresh + prior}, case)

        assert len(fresh) > OPENING_CHARS  # the shared tail is out of frame
        assert score["replay_similarity"] < 0.4

    def test_it_uses_the_same_window_as_the_offline_sweep(self):
        from scripts.synthesis_scorers import OPENING_CHARS as offline

        assert OPENING_CHARS == offline


class TestGrowthScorer:

    def test_it_reproduces_the_measured_accretion(self):
        for round_num, expected in ((2, 1.31), (3, 1.49)):
            fields, case = _fields(round_num)

            score = SynthesisGrowthScorer().score(fields, fields, case)

            assert score["growth_ratio"] == pytest.approx(expected, abs=0.01)

    def test_the_opening_round_has_no_ratio_rather_than_zero(self):
        """None and 0.0 are different answers; a median over zeros would say
        the narration collapsed."""
        fields, case = _fields(1)

        assert SynthesisGrowthScorer().score(fields, fields, case)["growth_ratio"] is None


class TestRegistration:

    def test_all_three_are_reachable_by_name(self):
        for name in ("synthesis_validation", "synthesis_repetition", "synthesis_growth"):
            assert name in SCORER_REGISTRY
            assert SCORER_REGISTRY[name]().name == name

    def test_synthesis_defaults_to_validation_and_repetition(self):
        assert SYNTHESIS.default_scorers == ("synthesis_validation", "synthesis_repetition")

    def test_growth_is_not_a_default_target(self):
        """Held out so it can catch a rewrite that games repetition by padding —
        a scorer inside the optimisation loop cannot also be its check."""
        assert "synthesis_growth" not in SYNTHESIS.default_scorers

    def test_resolution_does_not_get_synthesis_scorers(self):
        """Damage scorers over narration report zeros and look like a clean
        result; narrative scorers over resolutions would do the same in reverse."""
        assert CASE_KINDS["resolution"].default_scorers == ("damage_comparison",)
