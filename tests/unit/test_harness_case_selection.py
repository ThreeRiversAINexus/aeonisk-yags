"""Which recorded calls the eval harness can see (#158).

The harness selected cases by looking for `"narration"` and `"effects"` in the
response body. That is the `ActionResolution` shape. The round synthesis call
answers with `narration` + `segments` + `coverage` and no `effects`, so the one
prompt most in need of optimisation was invisible — for a reason that had
nothing to do with whether it was replayable.

Selecting on the `call_type` tag instead is both the fix and a generalisation:
the tag says what the call *was*, the substring test said what its answer
happened to contain. Every `llm_call` has carried the tag since the batch-proxy
path was tagged, so this reaches every call type at once rather than one more.

The legacy path stays the default and is asserted unchanged, because a
selection change is silent — nothing errors, the harness just evaluates a
different population and reports it as the same experiment.
"""

import json
from pathlib import Path

import pytest

from scripts.prompt_eval_harness import LEGACY_RESOLUTION_MARKERS, is_eval_candidate

CHAIN = Path(__file__).parent.parent / "fixtures/sessions/synthesis_repetition_chain.jsonl"

RESOLUTION = {"event_type": "llm_call", "agent_type": "dm",
              "call_type": "structured:ActionResolution",
              "response": '{"narration": "He fires.", "effects": {"damage": []}}'}
SYNTHESIS = {"event_type": "llm_call", "agent_type": "dm",
             "call_type": "structured:OutcomeRoundSynthesis",
             "response": '{"narration": "The chamber stays taut.", '
                         '"segments": [], "coverage": []}'}


class TestLegacySelectionIsUnchanged:
    """The default must keep choosing exactly what it chose before."""

    def test_a_resolution_response_is_selected(self):
        assert is_eval_candidate(RESOLUTION) is True

    def test_the_synthesis_response_is_still_invisible_by_default(self):
        """Not a bug to fix in the default — the legacy population is what
        existing results were measured against, and quietly widening it would
        make old and new runs incomparable."""
        assert is_eval_candidate(SYNTHESIS) is False

    def test_both_markers_are_required(self):
        half = dict(RESOLUTION, response='{"narration": "He fires."}')

        assert is_eval_candidate(half) is False

    def test_the_markers_are_named_not_inlined(self):
        assert LEGACY_RESOLUTION_MARKERS == ('"narration"', '"effects"')


class TestCallTypeSelection:

    def test_synthesis_is_selected_by_its_tag(self):
        assert is_eval_candidate(SYNTHESIS, "structured:OutcomeRoundSynthesis") is True

    def test_a_resolution_is_excluded_when_asking_for_synthesis(self):
        assert is_eval_candidate(RESOLUTION, "structured:OutcomeRoundSynthesis") is False

    def test_the_tag_is_matched_as_a_substring(self):
        """`--call-type OutcomeRoundSynthesis` should work without the prefix."""
        assert is_eval_candidate(SYNTHESIS, "OutcomeRoundSynthesis") is True

    def test_selection_no_longer_depends_on_the_response_body(self):
        """The point of the change: a call is replayable because of what it was,
        not because of what its answer happened to contain."""
        empty = dict(SYNTHESIS, response="")

        assert is_eval_candidate(empty, "structured:OutcomeRoundSynthesis") is True

    def test_a_missing_tag_matches_nothing(self):
        untagged = {"event_type": "llm_call", "agent_type": "dm", "response": "{}"}

        assert is_eval_candidate(untagged, "structured:OutcomeRoundSynthesis") is False


class TestNonCandidates:

    @pytest.mark.parametrize("event", [
        {"event_type": "round_synthesis", "agent_type": "dm",
         "call_type": "structured:OutcomeRoundSynthesis"},
        {"event_type": "llm_call", "agent_type": "player",
         "call_type": "structured:OutcomeRoundSynthesis"},
        {},
    ])
    def test_only_dm_llm_calls_qualify(self, event):
        assert is_eval_candidate(event, "structured:OutcomeRoundSynthesis") is False


class TestAgainstTheRecording:
    """A synthetic event proves the predicate; a real one proves the tag is
    actually written the way the predicate expects."""

    def test_the_recorded_synthesis_calls_are_now_selectable(self):
        events = [json.loads(line) for line in
                  CHAIN.read_text(encoding="utf-8").splitlines() if line.strip()]

        selected = [e for e in events
                    if is_eval_candidate(e, "structured:OutcomeRoundSynthesis")]

        assert len(selected) == 3
        assert [e["round"] for e in selected] == [1, 2, 3]

    def test_the_default_selects_none_of_them(self):
        events = [json.loads(line) for line in
                  CHAIN.read_text(encoding="utf-8").splitlines() if line.strip()]

        assert [e for e in events if is_eval_candidate(e)] == []
