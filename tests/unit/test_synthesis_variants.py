"""The three variants, and the promise that each changes one thing (#158).

An arm is only interpretable if it differs from the base in exactly the way its
notes claim. These tests compare each variant against the base module field by
field, because a variant that quietly changed a second thing would still produce
a number — a better or worse number — and nothing would say which change earned
it.

V2  the contract moves above the payload and its 18 rules group by consequence
V3  the ~21,700-character schema dump is not sent

V1 is no longer among them. It was measured, it won, and it was promoted into
`dm_outcome_synthesis.yaml` on 2026-08-12 — identical round openings 5/19 to
0/19, median similarity 0.62 to 0.36. Its behaviour is asserted here as the
base module's, which is where a shipped change belongs.

The knobs live in the YAML rather than in a caller, so an arm is fully declared
in the file under test — which is the point of getting these prompts out of
Python in the first place (#159).
"""

import pathlib

import pytest
import yaml

from aeonisk.multiagent import synthesis_prompt
from aeonisk.multiagent.synthesis_prompt import (
    PREVIOUS_ENDING_MODES, response_schema_block, system_prompt,
    trim_previous_ending, user_prompt,
)

PROMPTS = pathlib.Path(synthesis_prompt.MODULE_PATH).parent
BASE = yaml.safe_load((PROMPTS / "dm_outcome_synthesis.yaml").read_text())

PAYLOAD = [{"outcome_id": "out_1", "sequence": 0, "actor_name": "Hard Vane",
            "intent": "fire", "weapon": "Union Heavy Pistol", "target_names": [],
            "facts": []}]
PRIOR = ("The chamber stays taut and airless. Blood and restraint hang between them.\n\n"
         "He holsters the weapon and opens his hands. Nobody moves.")


def variant(name):
    return yaml.safe_load((PROMPTS / f"dm_outcome_synthesis_{name}.yaml").read_text())


def rendered(module):
    return user_prompt(3, PAYLOAD, PRIOR, {"npcs_departed": []}, module=module)


class TestTrimming:
    """The knob V1 turns."""

    def test_full_is_untouched(self):
        assert trim_previous_ending(PRIOR, "full") == PRIOR

    def test_final_sentence_keeps_the_handhold_and_drops_the_transcript(self):
        """Continuity needs to know where the last round left off, not what
        every paragraph of it said."""
        assert trim_previous_ending(PRIOR, "final_sentence") == "Nobody moves."

    def test_final_paragraph_keeps_the_last_beat(self):
        got = trim_previous_ending(PRIOR, "final_paragraph")

        assert got.startswith("He holsters the weapon")
        assert "Blood and restraint" not in got

    def test_none_is_the_control(self):
        assert trim_previous_ending(PRIOR, "none") == ""

    def test_prose_ending_in_a_quote_keeps_the_quote(self):
        """Narration routinely ends on dialogue; cutting at the period would
        hand the next round a dangling quotation mark."""
        text = 'She turned away. "Your patients, Sela."'

        assert trim_previous_ending(text, "final_sentence") == '"Your patients, Sela."'

    def test_text_with_no_sentence_end_survives_whole(self):
        assert trim_previous_ending("no terminator here", "final_sentence") == "no terminator here"

    def test_empty_input_is_not_an_error(self):
        assert trim_previous_ending("", "final_sentence") == ""

    def test_an_unknown_mode_is_refused(self):
        """A typo in a variant file must not silently render the base prompt
        and report the result as the arm's."""
        with pytest.raises(ValueError, match="unknown previous_ending mode"):
            trim_previous_ending(PRIOR, "last_line")

    def test_the_modes_are_a_closed_set(self):
        assert PREVIOUS_ENDING_MODES == ("full", "final_paragraph",
                                         "final_sentence", "none")


class TestTheSchemaBlock:
    """What V3 removes."""

    def test_it_reproduces_what_production_appends(self):
        """118-char role line + this block == the 21,849 characters recorded on
        2026-08-11. If it drifts, V3 measures the drift instead of the change.
        """
        assert len(system_prompt()) == len(BASE["system_prompt"]) + len(response_schema_block())
        assert len(system_prompt()) == 21849

    def test_dropping_it_removes_most_of_the_call(self):
        assert len(system_prompt(include_schema=False)) == 118

    def test_the_module_decides_by_default(self):
        assert len(system_prompt(variant("v3"))) == 118
        assert len(system_prompt(BASE)) == 21849


class TestEachVariantChangesOneThing:

    def _differences(self, name):
        module = variant(name)
        prose_keys = {"description", "notes"}
        return {k for k in set(BASE) | set(module)
                if BASE.get(k) != module.get(k) and k not in prose_keys}

    def test_v2_changes_only_the_template(self):
        assert self._differences("v2") == {"user_prompt"}

    def test_v3_changes_only_the_schema_flag(self):
        assert self._differences("v3") == {"include_schema"}
        assert variant("v3")["include_schema"] is False

    @pytest.mark.parametrize("name", ["v2", "v3"])
    def test_every_variant_still_names_the_base_module(self, name):
        """`ModuleSwapper` looks the old body up by this name; a variant that
        renamed itself would not be found."""
        assert variant(name)["module"] == "dm_outcome_synthesis"

    @pytest.mark.parametrize("name", ["v2", "v3"])
    def test_every_variant_still_renders(self, name):
        """A stray brace raises inside `str.format`, and it would raise on the
        one call that turns mechanics into story rather than here."""
        assert rendered(variant(name)).startswith("Write the canonical")


class TestTheShippedPrompt:
    """V1, now the live module. Measured over 24 replayed cases before promotion:
    identical openings 5/19 -> 0/19, median similarity 0.62 -> 0.36, warnings
    9 -> 1, errors 16 -> 10, schema-valid 23/24 -> 24/24."""

    def test_it_sends_the_closing_line_not_the_whole_round(self):
        text = rendered(BASE)

        assert PRIOR not in text
        assert "Nobody moves." in text

    def test_the_heading_no_longer_calls_a_whole_round_an_ending(self):
        """The label mattered as much as the length: 2,131 characters of
        finished prose were introduced to the narrator as an 'ending'."""
        text = rendered(BASE)

        assert "PRIOR CANONICAL ENDING:" not in text
        assert "do not retell it" in text

    def test_the_knob_is_declared_in_the_module(self):
        """Not in a caller. A shipped behaviour that lives in Python is one the
        harness cannot vary — the whole reason for #159."""
        assert BASE["previous_ending"] == "final_sentence"

    def test_an_opening_round_is_unaffected(self):
        """Round 1 has no prior narration to trim, and must not acquire one."""
        text = user_prompt(1, PAYLOAD, "", {}, module=BASE)

        assert synthesis_prompt.NO_PRIOR_ROUND in text


class TestV2:

    def test_no_rule_was_added_dropped_or_reworded(self):
        """The one thing a reorder must not do. Grouping is the variable;
        content is not."""
        def rules(text):
            return sorted(l for l in text.splitlines() if l.startswith("- "))

        assert rules(variant("v2")["user_prompt"]) == rules(BASE["user_prompt"])
        assert len(rules(BASE["user_prompt"])) == 18

    def test_the_contract_now_precedes_the_payload(self):
        text = rendered(variant("v2"))

        assert text.index("BINDING CONTRACT") < text.index("AUTHORITATIVE, PROSE-SAFE OUTCOMES")

    def test_the_groups_are_ordered_by_consequence(self):
        text = variant("v2")["user_prompt"]

        assert text.index("TRUTH") < text.index("COVERAGE") < text.index("CRAFT")


class TestTheGoalFile:
    GOALS = pathlib.Path(__file__).parent.parent.parent / "evals/goals/synthesis_goals.yaml"

    def test_it_parses_and_selects_synthesis_cases(self):
        goals = yaml.safe_load(self.GOALS.read_text())

        assert goals["eval_subset"]["call_type"] == "structured:OutcomeRoundSynthesis"

    def test_growth_is_a_regression_and_never_a_target(self):
        """The hold-out. `synthesis_repetition` is trivially gameable, and a
        scorer inside the optimisation loop cannot also be its own check."""
        goals = yaml.safe_load(self.GOALS.read_text())

        assert "synthesis_growth" not in goals["targets"]
        assert any("synthesis_growth" in (reg.get("scorers") or [])
                   for reg in goals["regressions"].values())

    def test_the_targets_are_the_two_free_scorers(self):
        goals = yaml.safe_load(self.GOALS.read_text())

        assert set(goals["targets"]) == {"synthesis_validation", "synthesis_repetition"}
