"""The judgeable unit for #156: one segment's text against one outcome's record.

The pipeline validates coverage and never validates correspondence. A segment
can cite exactly the right outcome ids, satisfy every structural check, and
describe a different round — round 3 of `3de9e609` did, and that session is
`synthesis_repetition_chain.jsonl`. Nothing here judges prose; these tests pin
the extraction and the two deterministic filters that select cases for a judge.

Read `synthesis_scorers`' own warning before using any of it to make a claim:
naming an actor is necessary for a segment to be about an outcome and nowhere
near sufficient. The filters choose what a judge looks at. They never score.
"""

import json

import pytest

from scripts.session_invariants import load
from scripts.synthesis_scorers import (
    actor_presence,
    cross_round_reuse,
    segment_outcome_pairs,
    target_presence,
)

CHAIN = "tests/fixtures/sessions/synthesis_repetition_chain.jsonl"
CLEAN = "tests/fixtures/sessions/golden_lawful_arrest_complete.jsonl"
LEGACY = "tests/fixtures/sessions/golden_npc_deescalation.jsonl"


@pytest.fixture(scope="module")
def chain():
    return load(CHAIN)


@pytest.fixture(scope="module")
def pairs(chain):
    return segment_outcome_pairs(chain)


def _one(pairs, rnd, segment_id, outcome_id):
    found = [p for p in pairs if p.round == rnd
             and p.segment_id == segment_id and p.outcome_id == outcome_id]
    assert len(found) == 1, f"expected exactly one r{rnd}/{segment_id}/{outcome_id}"
    return found[0]


class TestExtraction:

    def test_one_pair_per_citation(self, pairs):
        """19 citations across three rounds — not 12 segments, not 18 outcomes.

        The unit is the citation, because that is what can be wrong: a segment
        covering three outcomes may describe two of them faithfully and invent
        the third.
        """
        assert len(pairs) == 19

    def test_segment_ids_are_round_qualified(self, pairs):
        """`seg_1` is a round-1 segment AND a round-3 segment in this session.

        Keying on the bare id merges the faithful round-1 text with the round-3
        text that drifted, which is the one collision that would hide the defect
        this whole measurement exists to find.
        """
        seg_1_rounds = {p.round for p in pairs if p.segment_id == "seg_1"}
        assert seg_1_rounds == {1, 3}
        # Uniqueness alone proves nothing here: outcome ids are round-scoped, so
        # a round-less key is unique *by accident* and stops being unique the
        # moment two rounds cite one id. The round has to be in the key.
        assert all(p.key.startswith(f"r{p.round}/") for p in pairs)
        assert len({p.key for p in pairs}) == len(pairs)

    def test_the_outcome_record_comes_along(self, pairs):
        """Everything a judge needs to rule, and nothing it has to infer."""
        pair = _one(pairs, 3, "seg_3", "out_000015")
        assert pair.actor_narrative_name == "Hard Vane"
        assert pair.success is False
        assert pair.outcome_tier == "failure"
        assert pair.margin == -14
        assert "Corporate Influence" in pair.intent
        assert pair.target_names == ["Cold Tarn"]

    def test_a_segment_knows_what_else_it_covers(self, pairs):
        """Round 3's `seg_2` renders three outcomes in one paragraph.

        Judged in isolation, "does this text describe out_000013" is unfairly
        false for a paragraph that faithfully covers 13, 14 and 18 together. The
        pair carries the whole citation set so the judge sees the segment's real
        job.
        """
        pair = _one(pairs, 3, "seg_2", "out_000013")
        assert pair.cited_outcome_ids == ["out_000013", "out_000014", "out_000018"]
        assert pair.text == _one(pairs, 3, "seg_2", "out_000018").text

    def test_pairs_come_from_the_accepted_synthesis_not_the_llm_call(self):
        """Retries are 40% of the corpus's synthesis calls and never shipped.

        103 of 257 `OutcomeRoundSynthesis` llm_calls across the corpus are
        surplus to the `round_synthesis` events that record what was accepted —
        rejected drafts, in 32 sessions. Reading the call log scores prose no
        reader ever saw. `round_synthesis` is what the story actually said.
        """
        events = load(CHAIN)
        assert any(e.get("event_type") == "llm_call" for e in events), \
            "fixture has no llm_call events, so this test could not fail"
        without_calls = [e for e in events if e.get("event_type") != "llm_call"]
        assert segment_outcome_pairs(without_calls) == segment_outcome_pairs(events)

    def test_an_unresolvable_citation_is_kept_and_marked(self, chain):
        """Dropping it silently is how a census reports a clean number.

        The validator already errors on unknown outcome ids, so this should not
        occur live — which is exactly why it must be counted rather than
        filtered away if it ever does.
        """
        broken = [e for e in chain
                  if not (e.get("event_type") == "applied_outcome"
                          and json.dumps(e).count("out_000015"))]
        pairs = segment_outcome_pairs(broken)
        assert len(pairs) == 19
        orphan = _one(pairs, 3, "seg_3", "out_000015")
        assert orphan.resolved is False
        assert orphan.actor_narrative_name is None
        assert all(p.resolved for p in pairs if p.outcome_id != "out_000015")


class TestAntiVacuity:
    """A silent zero must never read as a clean session."""

    def test_a_legacy_session_yields_nothing_and_says_so(self):
        events = load(LEGACY)
        assert any(e.get("event_type") == "round_synthesis" for e in events), \
            "fixture has no synthesis at all; it proves nothing about the join"
        assert not any(e.get("event_type") == "applied_outcome" for e in events)
        assert segment_outcome_pairs(events) == []

    def test_the_clean_golden_still_produces_pairs(self):
        """If the extractor returned [] here, every filter below would be
        vacuously silent on the reference session and nobody would notice."""
        assert len(segment_outcome_pairs(load(CLEAN))) == 22


class TestTargetPresence:

    def test_it_only_speaks_about_outcomes_that_have_targets(self, pairs):
        findings = target_presence(pairs)
        untargeted = {p.key for p in pairs if not p.target_names}
        assert untargeted, "no untargeted outcomes in the fixture; test is vacuous"
        assert not ({f["key"] for f in findings} & untargeted)

    def test_it_fires_when_no_target_is_named(self, pairs):
        """Round 3's `seg_3` cites Hard Vane's failed call to Cold Tarn and
        names Sela instead — the round-2 scene it actually describes."""
        keys = {f["key"] for f in target_presence(pairs)}
        assert _one(pairs, 3, "seg_3", "out_000015").key in keys

    def test_naming_the_target_is_enough_to_stay_silent(self, pairs):
        """Necessary, not sufficient — and the docstring on it must say so."""
        assert "FILTER" in target_presence.__doc__.upper()


class TestCrossRoundReuse:
    """`opening_similarity` compares round openings. The #156 case re-narrated
    round 2's dialogue in the *middle* of round 3, which openings cannot see."""

    def test_round_three_is_round_two_reworded(self, pairs):
        flagged = {f["round"] for f in cross_round_reuse(pairs)}
        assert 3 in flagged

    def test_round_two_is_genuinely_new_prose(self, pairs):
        """Whole-session similarity of r1->r2 is 0.02-0.07 and r2->r3 is
        0.27-0.51; a filter that cannot tell those apart flags everything."""
        flagged = {f["round"] for f in cross_round_reuse(pairs)}
        assert 2 not in flagged

    def test_the_first_round_can_never_be_reuse(self, pairs):
        assert all(f["round"] > 1 for f in cross_round_reuse(pairs))

    def test_it_names_which_earlier_round_it_matched(self, pairs):
        for finding in cross_round_reuse(pairs):
            assert finding["prior_round"] < finding["round"]
            assert finding["shared"]


class TestFiltersAgreeOnTheirSource:

    def test_actor_presence_reads_the_same_pairs(self, pairs):
        """One definition of "what the story said", shared by all three filters.

        `actor_presence` originally parsed llm_call responses, so it scored
        rejected retries; moving it onto pairs is what makes its findings
        comparable with the other two and with a judge's verdicts.
        """
        findings = actor_presence(pairs)
        assert findings, "no actor_presence findings in the drift fixture"
        keys = {p.key for p in pairs}
        assert all(f["key"] in keys for f in findings)
