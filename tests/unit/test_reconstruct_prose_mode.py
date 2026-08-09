"""`--prose` emits a story, not a debug report.

Regression origin (session fa9d2891, 2026-08-09): the reconstruction is what the
transmedia pipeline consumes, but the default output interleaves `# Round N`
headers, `### Round N Synthesis`, stat blocks (`- Clocks: 2 advanced (+3 ticks)`,
`- Average margin: +0.0`) and raw player declarations that quote mechanics
("6/26 HP, 4 wounds") and free-targeting IDs (`tgt_vyfq`).

The DM's own narration is clean — `outcome_first_narration` did its job. The leak
was entirely reconstruction scaffolding, so the fix belongs here, not in the DM.
"""

import pytest

from scripts.aeonisk.multiagent.reconstruct_narrative import (
    PROSE_ELEMENT_TYPES, select_prose_elements, strip_scaffolding,
)


def _el(type_, content, round_=1):
    return {"type": type_, "content": content, "round": round_}


class TestSelectProseElements:

    def test_keeps_scenario_and_synthesis(self):
        elements = [
            _el("scenario", "The annex reeks of sterile decay."),
            _el("round_synthesis", "Corin forces himself upright."),
        ]

        kept = select_prose_elements(elements)

        assert [e["content"] for e in kept] == [
            "The annex reeks of sterile decay.",
            "Corin forces himself upright.",
        ]

    @pytest.mark.parametrize("noisy", [
        "round_start", "round_summary", "statistics_summary", "clock_summary",
        "clock_advancement", "clock_spawn", "clock_removal", "clock_completion",
        "character_state", "character_summary", "entity_summary",
        "entity_lifecycle", "economy_summary", "session_start",
    ])
    def test_drops_scaffolding_and_stat_blocks(self, noisy):
        kept = select_prose_elements([_el(noisy, "- Average margin: +0.0")])

        assert kept == []

    def test_drops_raw_action_declarations(self):
        """Declarations quote HP and target IDs straight into the story."""
        kept = select_prose_elements([_el(
            "action_declaration",
            "Nera is critically wounded (6/26 HP, 4 wounds); tgt_vyfq is hostile.")])

        assert kept == []

    def test_keeps_mission_debrief(self):
        kept = select_prose_elements([_el("mission_debrief", "We took him alive.")])

        assert len(kept) == 1

    def test_preserves_order(self):
        elements = [
            _el("scenario", "one"),
            _el("round_summary", "- Average margin: +0.0"),
            _el("round_synthesis", "two"),
            _el("clock_summary", "noise"),
            _el("mission_debrief", "three"),
        ]

        assert [e["content"] for e in select_prose_elements(elements)] == [
            "one", "two", "three"]

    def test_skips_empty_content(self):
        kept = select_prose_elements([
            _el("round_synthesis", "   "),
            _el("round_synthesis", ""),
            _el("round_synthesis", "real prose"),
        ])

        assert [e["content"] for e in kept] == ["real prose"]

    def test_strips_headers_baked_into_element_content(self):
        """round_synthesis content opens with '### Round N Synthesis' — selecting
        the right element is not enough, the furniture inside it must go too."""
        text = strip_scaffolding(
            "### Round 2 Synthesis\n\nCorin forces himself upright.\n")

        assert text == "Corin forces himself upright."

    def test_strips_rule_lines(self):
        text = strip_scaffolding("========\nThe lattice hums.\n--------")

        assert text == "The lattice hums."

    def test_strips_key_value_metadata_headers(self):
        """'Void Level: 4' is game state — the leak the user calls a dealbreaker."""
        text = strip_scaffolding(
            "**Location:** Disused biocreche annex\n"
            "**Void Level:** 4\n\n"
            "The annex reeks of sterile decay.")

        assert text == "The annex reeks of sterile decay."

    def test_bold_emphasis_mid_sentence_survives(self):
        prose = "She said **no** and meant it."

        assert strip_scaffolding(prose) == prose

    def test_leaves_ordinary_prose_untouched(self):
        prose = "He fires once. The dart punches into the Theorist's shoulder."

        assert strip_scaffolding(prose) == prose

    def test_prose_types_are_a_strict_allowlist(self):
        """New event types must be opted IN, so scaffolding cannot leak back."""
        assert "round_summary" not in PROSE_ELEMENT_TYPES
        assert "action_declaration" not in PROSE_ELEMENT_TYPES
        assert "round_synthesis" in PROSE_ELEMENT_TYPES
