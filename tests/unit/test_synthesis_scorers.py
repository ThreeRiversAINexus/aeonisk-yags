"""Offline scorers for the synthesis prompt, and what each one can honestly claim (#158).

The point of these is that a frontier judge should not be paid to notice a
model copying its own previous paragraph. Two of the three are exact
measurements against recorded text; the third is a filter with error in both
directions, and the tests below pin that down rather than papering over it.

They already earned their keep. Across the corpus, **22% of consecutive round
pairs in outcome-first sessions open with character-identical text, against 0%
in the 1,760 legacy round pairs**, and one session opens all six of its rounds
with the same sentence. That was found for nothing, before a single token was
spent on a variant.
"""

import json
from pathlib import Path

import pytest

from scripts.session_invariants import load
from scripts.synthesis_scorers import (
    OPENING_CHARS, RoundNarration, actor_presence, is_outcome_first,
    length_growth, opening_similarity, score_session, summarise,
    synthesis_rounds,
)

CHAIN = Path(__file__).parent.parent / "fixtures/sessions/synthesis_repetition_chain.jsonl"


def _events():
    return load(str(CHAIN))


def _rounds(*texts):
    return [RoundNarration(i + 1, t) for i, t in enumerate(texts)]


class TestOpeningSimilarity:
    """Exact and deterministic. It measures repetition, not quality."""

    def test_identical_openings_score_one_and_are_flagged(self):
        r = opening_similarity(_rounds("The pod chamber holds its breath." + "x" * 200,
                                       "The pod chamber holds its breath." + "x" * 200))

        assert r[0]["similarity"] == 1.0
        assert r[0]["identical"] is True

    def test_a_genuinely_new_scene_scores_low(self):
        r = opening_similarity(_rounds("The pod chamber holds its breath under clinical light.",
                                       "Rain hammers the freight yard, and nobody moves."))

        assert r[0]["similarity"] < 0.4
        assert r[0]["identical"] is False

    def test_only_the_opening_is_compared(self):
        """Two rounds may end similarly — returning to the same room is fine.
        Opening on the same sentence is not."""
        shared_tail = " " + "z" * 400
        r = opening_similarity(_rounds("A" * OPENING_CHARS + shared_tail,
                                       "B" * OPENING_CHARS + shared_tail))

        assert r[0]["similarity"] == 0.0

    def test_a_single_round_has_nothing_to_compare(self):
        assert opening_similarity(_rounds("only one")) == []

    def test_the_recorded_session_shows_the_drift(self):
        r = opening_similarity(synthesis_rounds(_events()))

        assert [x["round"] for x in r] == [2, 3]
        assert all(x["similarity"] > 0.5 for x in r)


class TestLengthGrowth:
    """Accretion is the signature of re-telling rather than continuing."""

    def test_the_ratio_is_against_the_first_round(self):
        g = length_growth(_rounds("a" * 100, "b" * 150, "c" * 300))

        assert [x["ratio"] for x in g] == [1.0, 1.5, 3.0]

    def test_the_recorded_session_nearly_doubles(self):
        g = length_growth(synthesis_rounds(_events()))

        assert [x["chars"] for x in g] == [1611, 2105, 3143]
        assert g[-1]["ratio"] == pytest.approx(1.95, abs=0.01)

    def test_an_empty_session_is_not_a_crash(self):
        assert length_growth([]) == []


class TestActorPresence:
    """A filter, and the tests say so in both directions."""

    def test_it_catches_a_segment_that_never_names_its_actor(self):
        """Round 3's `seg_1` cites Sela's extraction plan and is pure
        scene-setting — it does not mention her at all."""
        found = actor_presence(_events())

        seg1 = [f for f in found if f["round"] == 3 and f["segment_id"] == "seg_1"]
        assert seg1 and seg1[0]["unnamed_actors"] == ["Oathkeeper Sela"]

    def test_it_misses_the_worst_segment_in_the_session(self):
        """The honest limit, asserted so nobody mistakes this for a fidelity
        check. Round 3's `seg_3` cites Hard Vane's failed Corporate Influence
        call and narrates him holstering his weapon — an action from round 2.
        It names him, so this scorer stays silent. Only a judge catches that.
        """
        found = {(f["round"], f["segment_id"]) for f in actor_presence(_events())}

        assert (3, "seg_3") not in found
        assert (3, "seg_4") not in found

    def test_collective_reference_reads_as_a_miss(self):
        """The other direction: prose that says "the subdued operatives" rather
        than naming all three is good writing and scores as unnamed. False
        positives are why this selects cases instead of scoring them."""
        found = actor_presence(_events())

        collective = [f for f in found
                      if all("Subdued Operative" in a for a in f["unnamed_actors"])]
        assert len(collective) >= 2

    def test_a_session_with_no_synthesis_calls_yields_nothing(self):
        assert actor_presence([{"event_type": "round_start", "round": 1}]) == []

    def test_an_unparseable_response_is_skipped_not_fatal(self):
        events = [{"event_type": "llm_call", "round": 1,
                   "call_type": "structured:OutcomeRoundSynthesis",
                   "response": "not json"}]

        assert actor_presence(events) == []


class TestPipelineSplit:
    """The comparison is the finding, so the split has to be right."""

    def test_the_fixture_is_recognised_as_outcome_first(self):
        assert is_outcome_first(_events()) is True

    def test_a_session_without_applied_outcomes_is_legacy(self):
        assert is_outcome_first([{"event_type": "round_synthesis", "round": 1}]) is False

    def test_the_summary_separates_the_two_pipelines(self):
        results = [
            {"outcome_first": True, "opening_similarity": [
                {"similarity": 1.0, "identical": True}], "length_growth": [
                {"round": 1, "chars": 10, "ratio": 1.0}]},
            {"outcome_first": False, "opening_similarity": [
                {"similarity": 0.2, "identical": False}], "length_growth": [
                {"round": 1, "chars": 10, "ratio": 1.0}]},
        ]

        s = summarise(results)

        assert s["outcome_first"]["identical_pct"] == 100.0
        assert s["legacy"]["identical_pct"] == 0.0

    def test_an_empty_corpus_reports_none_rather_than_zero(self):
        """Zero and "nothing measured" are different answers, and conflating
        them is how a scorer starts certifying its own blind spot."""
        s = summarise([])

        assert s["outcome_first"]["median_opening_similarity"] is None
        assert s["outcome_first"]["identical_pct"] is None


class TestScoreSession:

    def test_it_scores_the_fixture_end_to_end(self):
        r = score_session(str(CHAIN))

        assert r["rounds"] == 3
        assert r["outcome_first"] is True
        assert len(r["opening_similarity"]) == 2

    def test_a_file_without_synthesis_scores_nothing(self, tmp_path):
        p = tmp_path / "session_empty.jsonl"
        p.write_text(json.dumps({"event_type": "round_start", "round": 1}) + "\n")

        assert score_session(str(p)) is None
