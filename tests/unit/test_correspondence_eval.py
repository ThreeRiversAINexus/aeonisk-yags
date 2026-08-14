"""The judge lane for #156, and the things that would make its number a lie.

Coverage is checked; correspondence is not. The only oracle for "does this
prose describe this outcome" is a reading, so this lane pays a judge for one —
which means the lane itself has to be trustworthy before the number is:

  * the judge must never be shown which deterministic filter fired, or the
    filters' precision measured against it is circular;
  * a response that failed to arrive or failed to parse must never score as
    faithful, because the silent direction of every broken join is "clean";
  * the judge must be shown to separate cases we have already read, or the
    census is a number nobody can falsify.
"""

import json

import pytest

from scripts.correspondence_eval import (
    SEED_ACCOUNTED, SEED_NOT_RENDERED, SEED_RENDERED, SEED_UNACCOUNTED,
    _seed_pairs, build_prompts, build_segment_prompts, filter_agreement,
    parse_unaccounted, parse_verdict, score,
)
from scripts.session_invariants import load
from scripts.synthesis_scorers import actor_presence, segment_outcome_pairs

CHAIN = "tests/fixtures/sessions/synthesis_repetition_chain.jsonl"


@pytest.fixture(scope="module")
def pairs():
    return segment_outcome_pairs(load(CHAIN))


@pytest.fixture(scope="module")
def prompts(pairs):
    return build_prompts(pairs, session="chain")


def _prompt_for(prompts, key):
    found = [p for p in prompts if p["item_id"].endswith(key)]
    assert len(found) == 1, f"no single prompt for {key}"
    return found[0]


class TestPromptConstruction:

    def test_one_prompt_per_resolved_pair(self, pairs, prompts):
        assert len(prompts) == len([p for p in pairs if p.resolved]) == 19

    def test_the_item_id_carries_session_and_pair(self, prompts):
        assert all(p["item_id"].startswith("chain|r") for p in prompts)
        assert len({p["item_id"] for p in prompts}) == len(prompts)

    def test_the_outcome_record_is_in_the_prompt(self, prompts):
        """The judge rules against the record, so it must not have to infer it.
        Failure especially: `out_000015` failed by 14 and the prose renders a
        composed, successful de-escalation."""
        user = _prompt_for(prompts, "r3/seg_3/out_000015")["user"]

        assert "Hard Vane" in user
        assert "Corporate Influence" in user
        assert "failure" in user.lower()
        assert "Cold Tarn" in user

    def test_a_segment_says_what_else_it_covers(self, prompts):
        """Round 3's `seg_2` renders three outcomes in one paragraph. Asked
        about one of them in isolation, a faithful paragraph reads as false."""
        user = _prompt_for(prompts, "r3/seg_2/out_000013")["user"]

        assert "out_000014" in user and "out_000018" in user

    def test_the_filters_are_held_out(self, pairs, prompts):
        """Measuring a filter's precision against a judge that was told what
        the filter said measures nothing. This is the load-bearing one.
        """
        flagged = {f["key"] for f in actor_presence(pairs)}
        assert flagged, "no filter findings in this fixture; the test is vacuous"

        for prompt in prompts:
            blob = (prompt["system"] + prompt["user"]).lower()
            for banned in ("actor_presence", "target_presence",
                           "cross_round_reuse", "unnamed", "reuse", "filter"):
                assert banned not in blob, f"{banned!r} leaked into the prompt"

    def test_an_unresolvable_pair_gets_no_prompt(self, pairs):
        """Nothing to rule against. It is dropped here and counted in `score`,
        never dropped in both places."""
        for pair in pairs:
            pair.resolved = False
        try:
            assert build_prompts(pairs, session="chain") == []
        finally:
            for pair in pairs:
                pair.resolved = True


class TestVerdictParsing:

    def test_a_plain_object(self):
        assert parse_verdict('{"renders": true, "reason": "ok"}').renders is True

    def test_a_fenced_object(self):
        text = '```json\n{"renders": false, "reason": "wrong round"}\n```'
        assert parse_verdict(text).renders is False

    @pytest.mark.parametrize("text", [None, "", "not json", "{}", '{"renders": "yes"}'])
    def test_anything_unreadable_is_None_and_never_faithful(self, text):
        """The silent direction of a broken join is "clean". A verdict that
        cannot be read must not be counted in either direction."""
        assert parse_verdict(text) is None


class TestScoring:

    def _responses(self, prompts, renders):
        return [{"item_id": p["item_id"],
                 "response": json.dumps({"renders": renders, "reason": "r"})}
                for p in prompts]

    def test_drift_rate_over_the_pairs_that_were_judged(self, pairs, prompts):
        report = score(pairs, self._responses(prompts, False), session="chain")

        assert report["judged"] == 19
        assert report["drift"] == 19
        assert report["drift_pct"] == 100.0

    def test_unparseable_responses_are_reported_not_absorbed(self, pairs, prompts):
        responses = self._responses(prompts, True)
        responses[0]["response"] = "the model apologised"
        report = score(pairs, responses, session="chain")

        assert report["judged"] == 18
        assert report["unreadable"] == 1
        assert report["drift"] == 0

    def test_a_missing_response_is_counted_as_missing(self, pairs, prompts):
        report = score(pairs, self._responses(prompts, True)[:-4], session="chain")

        assert report["judged"] == 15
        assert report["unanswered"] == 4

    def test_a_segment_scoped_answer_belongs_to_the_other_question(
            self, pairs, prompts):
        """Q2's ids look like `r3/seg_1`. They are not answers to Q1 and they
        are not unmatched either — counting them so reported 467 phantom
        failures over a census that had none."""
        responses = self._responses(prompts, True)
        responses.append({"item_id": "chain|r3/seg_1",
                          "response": '{"unaccounted": true, "reason": "r"}'})
        report = score(pairs, responses, session="chain")

        assert report["unmatched"] == 0
        assert report["judged"] == 19

    def test_the_agreement_universe_is_what_was_judged_not_what_exists(
            self, pairs, prompts):
        """A filter firing on a pair the judge never answered is neither right
        nor wrong about it. Folding unjudged pairs into the universe deflates
        precision for exactly the filters that fire most, which is the number
        the whole census exists to produce."""
        report = score(pairs, self._responses(prompts, True)[:5], session="chain")

        assert len(report["judged_keys"]) == 5
        assert set(report["judged_keys"]) < {p.key for p in pairs}

    def test_a_response_for_an_unknown_pair_is_not_silently_dropped(self, pairs, prompts):
        responses = self._responses(prompts, True)
        responses.append({"item_id": "chain|r9/seg_9/out_999999",
                          "response": '{"renders": true, "reason": "r"}'})
        report = score(pairs, responses, session="chain")

        assert report["unmatched"] == 1


class TestFilterAgreement:
    """What the census is really for: can a free check stand in for a paid one?"""

    def test_precision_and_recall_against_the_verdicts(self, pairs):
        drift = {"r3/seg_3/out_000015", "r3/seg_1/out_000016"}
        flagged = {"r3/seg_1/out_000016", "r2/seg_01/out_000007"}

        agreement = filter_agreement(flagged, drift, {p.key for p in pairs})

        assert agreement["true_positive"] == 1
        assert agreement["false_positive"] == 1
        assert agreement["false_negative"] == 1
        assert agreement["precision"] == pytest.approx(0.5)
        assert agreement["recall"] == pytest.approx(0.5)

    def test_a_filter_firing_on_an_unjudged_pair_is_neither_right_nor_wrong(self):
        """The judge answered one pair. The filter fired on two, and the second
        was never ruled on — counting it as a false positive would report a
        precision of 0.5 for a filter that was, on the evidence, perfect."""
        judged = {"r1/seg_1/out_000001"}
        agreement = filter_agreement(
            flagged={"r1/seg_1/out_000001", "r9/seg_9/out_000099"},
            drift={"r1/seg_1/out_000001"},
            universe=judged)

        assert agreement["flagged"] == 1
        assert agreement["false_positive"] == 0
        assert agreement["precision"] == pytest.approx(1.0)

    def test_drift_outside_the_judged_universe_does_not_hurt_recall(self):
        judged = {"r1/seg_1/out_000001"}
        agreement = filter_agreement(
            flagged={"r1/seg_1/out_000001"},
            drift={"r1/seg_1/out_000001", "r9/seg_9/out_000099"},
            universe=judged)

        assert agreement["false_negative"] == 0
        assert agreement["recall"] == pytest.approx(1.0)

    def test_a_filter_that_never_fires_has_no_precision_not_perfect_precision(self, pairs):
        agreement = filter_agreement(set(), {"r3/seg_3/out_000015"},
                                     {p.key for p in pairs})

        assert agreement["precision"] is None
        assert agreement["recall"] == 0.0


class TestSegmentPrompts:
    """The second question: does the passage narrate what this round did not?"""

    def test_one_prompt_per_segment_not_per_citation(self, pairs):
        prompts = build_segment_prompts(pairs, session="chain")

        assert len(prompts) == 12
        assert len({p["item_id"] for p in prompts}) == 12

    def test_the_whole_round_goes_in_not_just_the_cited_outcomes(self, pairs):
        """`r3/seg_3` cites only out_000015. Shown that alone, its mention of
        the operatives going quiet reads as invention; they are out_000013,
        014 and 018 of the same round."""
        prompts = build_segment_prompts(pairs, session="chain")
        user = [p for p in prompts if p["item_id"] == "chain|r3/seg_3"][0]["user"]

        for outcome_id in ("out_000013", "out_000015", "out_000017"):
            assert outcome_id in user
        assert "out_000009" not in user, "round 2's record must not be shown"

    def test_the_filters_are_held_out_here_too(self, pairs):
        for prompt in build_segment_prompts(pairs, session="chain"):
            blob = (prompt["system"] + prompt["user"]).lower()
            for banned in ("actor_presence", "cross_round_reuse", "reuse",
                           "filter", "unnamed"):
                assert banned not in blob

    @pytest.mark.parametrize("text,expected", [
        ('{"unaccounted": true, "reason": "r"}', True),
        ('{"unaccounted": false, "reason": "r"}', False),
        ('{"renders": true}', None),
        ("not json", None),
        (None, None),
    ])
    def test_parsing(self, text, expected):
        assert parse_unaccounted(text) is expected


class TestCalibrationSeed:
    """Read before it is judged. If the judge cannot reproduce these, stop.

    The first calibration run rewrote this seed. #156's table reads round 3's
    `seg_3` as pure round-2 prose; its second half in fact renders out_000015
    and renders it as the failure it was. The judge said so, the seed said
    otherwise, and the seed was wrong. What is actually true of that passage —
    and of `seg_4` — is that it renders its outcome *and* re-narrates round 2
    alongside it, which is why there are two questions now.
    """

    def test_both_classes_are_present_on_both_questions(self):
        """A one-sided seed cannot detect a judge that answers the same way
        every time — which is the failure mode most likely to occur."""
        assert SEED_NOT_RENDERED and SEED_RENDERED
        assert SEED_UNACCOUNTED and SEED_ACCOUNTED
        assert not (set(SEED_NOT_RENDERED) & set(SEED_RENDERED))
        assert not (set(SEED_UNACCOUNTED) & set(SEED_ACCOUNTED))

    def test_every_seed_key_exists_in_the_chain(self, pairs):
        keys = {p.key for p in pairs}
        segments = {f"r{p.round}/{p.segment_id}" for p in pairs}
        missing = ((set(SEED_NOT_RENDERED) | set(SEED_RENDERED)) - keys) | (
            (set(SEED_UNACCOUNTED) | set(SEED_ACCOUNTED)) - segments)

        assert not missing, f"seed refers to pairs that do not exist: {missing}"

    def test_the_segments_the_issue_named_are_labelled_rendered(self):
        """The correction, pinned. A check for "does it render its outcome"
        alone would pass three of the four segments in the round #156 was filed
        about, which is why it cannot be the only question."""
        assert "r3/seg_3/out_000015" in SEED_RENDERED
        assert "r3/seg_4/out_000016" in SEED_RENDERED

    def test_every_round_three_segment_is_seeded_as_unaccounted(self):
        """All four re-narrate round 2. That is the defect the round has."""
        assert set(SEED_UNACCOUNTED) == {f"r3/seg_{i}" for i in range(1, 5)}

    def test_the_recorded_judge_run_still_separates_the_seed(self):
        """The live calibration, frozen, so the gate reruns for free.

        This pins the SCORING, not the model: if a later edit to the seed, the
        parsing or the join stops separating these fifteen recorded answers,
        that is a defect in the lane and it should not need an API key to find.
        gpt-5.4-mini, 15/15 exact on both questions, 2026-08-14.
        """
        recorded = [json.loads(line) for line
                    in open("tests/fixtures/judge/correspondence_calibration_verdicts.jsonl")
                    if line.strip()]
        assert len(recorded) == 15

        not_rendered = set(score(_seed_pairs(), recorded, "chain")["drift_keys"])
        unaccounted = {r["item_id"].split("|", 1)[-1] for r in recorded
                       if r["item_id"].split("|", 1)[-1].count("/") == 1
                       and parse_unaccounted(r["response"])}

        assert set(SEED_NOT_RENDERED) == not_rendered
        assert not (set(SEED_RENDERED) & not_rendered)
        assert set(SEED_UNACCOUNTED) == unaccounted
        assert not (set(SEED_ACCOUNTED) & unaccounted)

    def test_the_clean_side_is_drawn_from_rounds_that_did_not_drift(self):
        """Rounds 1 and 2 reuse 2-7% of each other's shingles; round 3 reuses
        9-30% of round 2's. The clean side has to come from the clean rounds or
        the seed is testing the same defect twice."""
        assert all(k.startswith(("r1/", "r2/")) for k in SEED_RENDERED[:4])
        assert all(k.startswith(("r1/", "r2/")) for k in SEED_ACCOUNTED)
