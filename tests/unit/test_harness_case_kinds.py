"""Two shapes of recorded call, one optimisation loop (#158).

The harness grew around a single shape — vary the system prompt, resend the
recorded user prompt, score damage fields — and that shape was load-bearing in
four places at once. Synthesis does not fit it: its template lives in the *user*
message, so the module body never appears in the recording verbatim, and the
change worth testing (trimming `previous_ending` from the whole previous round
to its closing sentence) is not a text edit to the template at all. It is a
change to a *value*.

So synthesis re-renders from the recorded inputs instead of swapping text. The
load-bearing test is that re-rendering a recorded case reproduces the recorded
prompt **byte for byte** — without that, a variant's score would be measuring
the reconstruction as much as the change.

`resolution` keeps its old behaviour exactly, and that is asserted too: a
selection or rebuild change is silent, and quietly altering the population would
make old and new results incomparable while looking like the same experiment.
"""

import json
from pathlib import Path

import pytest

from scripts.prompt_eval_harness import (
    CASE_KINDS, RESOLUTION, SYNTHESIS, EvalCase, kind_for_call_type,
    synthesis_inputs_for_round,
)

CHAIN = Path(__file__).parent.parent / "fixtures/sessions/synthesis_repetition_chain.jsonl"


def _events_by_round():
    by_round = {}
    for line in CHAIN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        rnd = event.get("round")
        if rnd is not None:
            by_round.setdefault(rnd, []).append(event)
    return by_round


def _case(**kw):
    defaults = dict(
        case_id="c1", session_file="s.jsonl", condition="unknown", round_num=3,
        original_model="gpt-5.4-mini", system_prompt="SYS OLD BODY SYS",
        user_prompt="recorded user message", response_text="{}",
        action_type=None, player_action_text=None, margin=None)
    defaults.update(kw)
    return EvalCase(**defaults)


class FakeSwapper:
    """Stands in for ModuleSwapper, carrying the module a variant would supply.

    `replacement_module` matters more than it looks: `_synthesis_prompts` reads
    the render knobs (`previous_ending`, `include_schema`) off it. A stub without
    them silently renders with defaults, so a test could "pass" while never
    exercising the setting it names.
    """

    def __init__(self, module=None):
        self.replacement_module = module or {"system_prompt": "role line",
                                             "user_prompt": "unused"}

    def swap_module(self, system_prompt, module_name, new_content):
        if "OLD BODY" not in system_prompt:
            raise ValueError("not found")
        return system_prompt.replace("OLD BODY", new_content)


class TestKindSelection:

    def test_no_call_type_is_resolution(self):
        assert kind_for_call_type(None) is RESOLUTION

    def test_the_synthesis_tag_selects_synthesis(self):
        assert kind_for_call_type("structured:OutcomeRoundSynthesis") is SYNTHESIS

    def test_a_bare_tag_without_the_prefix_still_matches(self):
        assert kind_for_call_type("OutcomeRoundSynthesis") is SYNTHESIS

    def test_an_unknown_tag_replays_as_resolution(self):
        """Falling back keeps a new call_type usable the day it appears, rather
        than erroring on a tag nobody has taught the harness yet."""
        assert kind_for_call_type("structured:SomethingNew") is RESOLUTION

    def test_a_case_defaults_to_resolution(self):
        """The field was added to existing cases; the default has to be the
        behaviour those cases already had."""
        assert _case().kind_name == "resolution"


class TestResolutionIsUnchanged:

    def test_it_swaps_the_system_prompt_and_keeps_the_user_message(self):
        system, user = RESOLUTION.build_prompts(_case(), FakeSwapper(), "m", "NEW")

        assert system == "SYS NEW SYS"
        assert user == "recorded user message"

    def test_a_missing_module_body_still_raises(self):
        """`build_modified_prompts` relies on this to drop the case."""
        with pytest.raises(ValueError):
            RESOLUTION.build_prompts(_case(system_prompt="no match"),
                                     FakeSwapper(), "m", "NEW")


class TestSynthesisRebuild:

    def test_it_returns_both_the_render_inputs_and_the_ground_truth(self):
        """Two different jobs from one walk of the round: the four values the
        prompt renders, and the outcomes a response gets validated against."""
        inputs, outcomes = synthesis_inputs_for_round(_events_by_round(), 3)

        assert isinstance(inputs, dict) and isinstance(outcomes, list)
        assert len(outcomes) == len(inputs["safe_payload"])

    def test_the_four_inputs_come_back_from_the_recording(self):
        got, _outcomes = synthesis_inputs_for_round(_events_by_round(), 3)

        assert set(got) == {"round_num", "safe_payload", "previous_ending",
                            "safe_lifecycle"}
        assert got["round_num"] == 3
        assert len(got["safe_payload"]) == 6      # r3 has six applied outcomes
        assert got["previous_ending"].startswith("The chamber remains taut")

    def test_the_payload_is_the_prose_safe_whitelist_not_the_raw_outcome(self):
        """A field absent from the whitelist never reaches the narrator, so a
        rebuild that leaked extra keys would be testing a different prompt."""
        payload = synthesis_inputs_for_round(_events_by_round(), 3)[0]["safe_payload"]

        assert "entity_states_after" not in payload[0]
        assert {"outcome_id", "actor_name", "intent", "weapon"} <= set(payload[0])

    def test_round_one_has_no_prior_narration(self):
        assert synthesis_inputs_for_round(_events_by_round(), 1)[0]["previous_ending"] == ""

    def test_a_round_with_no_outcomes_is_dropped_not_faked(self):
        """Replaying against an empty scene would score a prompt nobody sent."""
        assert synthesis_inputs_for_round(_events_by_round(), 99) is None

    def test_a_missing_round_number_is_not_a_crash(self):
        assert synthesis_inputs_for_round(_events_by_round(), None) is None


class TestSynthesisRendersFaithfully:
    """The load-bearing test. If a rebuild does not reproduce the recording,
    every variant score is partly measuring the reconstruction."""

    #: The two things #158 V1 changed when it was promoted into the live module
    #: on 2026-08-12. Byte identity against a 2026-08-11 recording is a property
    #: of the rebuild *plus the module of the day*, not of today's module, so the
    #: fidelity test reverts exactly these and nothing else.
    AS_RECORDED = {"previous_ending": "full"}
    RECORDED_HEADING = "PRIOR CANONICAL ENDING:"
    CURRENT_HEADING = "HOW THE PREVIOUS ROUND CLOSED"

    def _built(self, content=None, as_recorded=False):
        from aeonisk.multiagent import synthesis_prompt
        module = dict(synthesis_prompt.load_module())
        module.setdefault("system_prompt", "role line")
        if as_recorded:
            module.update(self.AS_RECORDED)
            heading = next(l for l in module["user_prompt"].splitlines()
                           if l.startswith(self.CURRENT_HEADING))
            module["user_prompt"] = module["user_prompt"].replace(
                heading, self.RECORDED_HEADING)
        rebuilt, outcomes = synthesis_inputs_for_round(_events_by_round(), 3)
        case = _case(kind_name="synthesis", synthesis_inputs=rebuilt,
                     synthesis_outcomes=outcomes)
        return SYNTHESIS.build_prompts(
            case, FakeSwapper(module), "dm_outcome_synthesis",
            content if content is not None else module["user_prompt"])

    def test_rerendering_reproduces_the_recorded_prompt_byte_for_byte(self):
        """The one that makes every variant score mean something.

        If the rebuild drifted from what was actually sent — a key ordering, an
        indent, a missing lifecycle list — then a variant's score would be
        measuring the reconstruction as much as the change, and the difference
        would be invisible because both runs share the same drift.
        """
        recorded = None
        for line in CHAIN.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            body = event.get("data") if isinstance(event.get("data"), dict) else event
            if event.get("event_type") == "llm_call" and event.get("round") == 3:
                for message in body.get("prompt") or []:
                    if message.get("role") == "user":
                        recorded = message["content"]

        assert recorded, "fixture lost round 3's recorded user prompt"
        _, rebuilt = self._built(as_recorded=True)
        assert rebuilt == recorded

    def test_todays_module_no_longer_reproduces_it_and_that_is_the_point(self):
        """The promotion, seen from the other side.

        If this ever passes again, either V1 was reverted or the trim stopped
        working — both of which the byte-identity test above would happily miss,
        because it renders with the old settings on purpose.
        """
        _, current = self._built()
        _, as_recorded = self._built(as_recorded=True)

        assert current != as_recorded
        assert len(current) < len(as_recorded)

    def test_the_system_prompt_comes_from_the_module_not_the_recording(self):
        """Synthesis recordings carry only the user turn — the role line is the
        module's, which is exactly why the extractor stopped requiring both.

        The schema block follows it because a replay talks to a plain chat
        endpoint: without being told the shape, every response would fail
        validation for a reason unrelated to the prompt under test.
        """
        system, _ = self._built()

        assert system.startswith(
            "You are the literary DM for Aeonisk YAGS")
        assert "You must respond with valid JSON matching this schema:" in system

    def test_a_variant_actually_changes_the_prompt(self):
        _, base = self._built()
        _, variant = self._built(
            self._module_text().replace("BINDING CONTRACT:", "THE RULES:"))

        assert variant != base
        assert "THE RULES:" in variant

    def test_a_case_without_inputs_raises_rather_than_rendering_an_empty_scene(self):
        case = _case(kind_name="synthesis", synthesis_inputs=None)

        with pytest.raises(ValueError, match="no synthesis inputs"):
            SYNTHESIS.build_prompts(case, FakeSwapper(), "m", "template")

    @staticmethod
    def _module_text():
        from aeonisk.multiagent import synthesis_prompt
        return synthesis_prompt.load_module()["user_prompt"]


class TestTheRegistry:

    def test_both_kinds_are_registered_under_their_names(self):
        assert CASE_KINDS == {"resolution": RESOLUTION, "synthesis": SYNTHESIS}

    def test_each_kind_names_its_own_default_scorers(self):
        """Damage scorers over narration would report zeros and look like a
        clean result."""
        assert RESOLUTION.default_scorers == ("damage_comparison",)
        assert "synthesis_validation" in SYNTHESIS.default_scorers
