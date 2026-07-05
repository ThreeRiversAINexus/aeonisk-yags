"""
Tests for round-batch DM assessment: schema, merge semantics, and the
anti-anchoring content guard on the assessment prompt.

Design contract (2026-07-04): the DM is the difficulty authority; the
player's difficulty_estimate stays a logged counterfactual. DM may
reframe attribute/skill only when the player's framing is clearly wrong;
a reframed skill the character lacks resolves unskilled - misframing
has a price. Assessment failure falls back to the legacy category table
(no session ever stalls on this call).
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.round_assessment import (
    ActionAssessment,
    RoundAssessment,
    apply_assessments,
)

PROMPT_PATH = (Path(__file__).parent.parent.parent /
               "scripts/aeonisk/multiagent/prompts/claude/en/dm/"
               "dm_round_assessment.yaml")


def make_declared(name="Renna Volt", **action_overrides):
    action = {
        'character_name': name,
        'intent': 'slip past the checkpoint scanner',
        'attribute': 'Agility',
        'skill': 'Stealth',
        'attribute_value': 4,
        'skill_value': 5,
        'difficulty_estimate': 18,
    }
    action.update(action_overrides)
    return {'agent_id_1': [{'action': action}]}


SHEETS = {"Renna Volt": ({'Agility': 4, 'Perception': 5},
                         {'Stealth': 5, 'Deception': 3})}


class TestApplyAssessments:

    def test_difficulty_lands_on_action(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Renna Volt", difficulty=14,
            reasoning="Scanner is old and understaffed at night")])
        changes = apply_assessments(declared, ruling, SHEETS)

        action = declared['agent_id_1'][0]['action']
        assert action['dm_assessed_difficulty'] == 14
        assert action['difficulty_estimate'] == 18  # counterfactual survives
        assert any("18 → 14" in c for c in changes)

    def test_no_assessment_is_noop(self):
        declared = make_declared()
        before = str(declared)
        assert apply_assessments(declared, None, SHEETS) == []
        assert str(declared) == before

    def test_unmatched_character_untouched(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Somebody Else", difficulty=30,
            reasoning="Different character entirely here")])
        apply_assessments(declared, ruling, SHEETS)
        assert 'dm_assessed_difficulty' not in declared['agent_id_1'][0]['action']

    def test_skill_reframe_recomputes_value(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Renna Volt", difficulty=18, skill="Deception",
            reasoning="Talking past a guard is deception, not stealth")])
        apply_assessments(declared, ruling, SHEETS)
        action = declared['agent_id_1'][0]['action']
        assert action['skill'] == 'Deception'
        assert action['skill_value'] == 3

    def test_reframe_to_unknown_skill_goes_unskilled(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Renna Volt", difficulty=20, skill="Systems",
            reasoning="Bypassing the scanner firmware is a Systems task")])
        changes = apply_assessments(declared, ruling, SHEETS)
        action = declared['agent_id_1'][0]['action']
        assert action['skill_value'] == 0
        assert any("unskilled" in c for c in changes)

    def test_attribute_reframe_recomputes_value(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Renna Volt", difficulty=16,
            attribute="Perception",
            reasoning="Spotting the scanner gap is perception work")])
        apply_assessments(declared, ruling, SHEETS)
        action = declared['agent_id_1'][0]['action']
        assert action['attribute'] == 'Perception'
        assert action['attribute_value'] == 5

    def test_null_overrides_keep_player_framing(self):
        declared = make_declared()
        ruling = RoundAssessment(assessments=[ActionAssessment(
            character_name="Renna Volt", difficulty=18,
            reasoning="Framing is sound, difficulty stands as declared")])
        apply_assessments(declared, ruling, SHEETS)
        action = declared['agent_id_1'][0]['action']
        assert action['attribute'] == 'Agility'
        assert action['skill'] == 'Stealth'
        assert action['skill_value'] == 5


class TestSchemaBounds:

    def test_difficulty_bounds_enforced(self):
        with pytest.raises(Exception):
            ActionAssessment(character_name="X", difficulty=3,
                             reasoning="Below the schema floor entirely")
        with pytest.raises(Exception):
            ActionAssessment(character_name="X", difficulty=45,
                             reasoning="Above the schema ceiling entirely")


class TestPromptContentGuard:
    """Anti-anchoring guard: this failure mode shipped three times on
    2026-07-04 (soulcredit zero-example, DC 18 category table, synthesis
    opener template). The assessment prompt must span the ladder."""

    def test_prompt_exists_and_loads(self):
        data = yaml.safe_load(PROMPT_PATH.read_text())
        assert 'round_assessment_prompt' in data

    def test_examples_span_at_least_four_distinct_dcs(self):
        import re
        content = PROMPT_PATH.read_text()
        dcs = {int(m) for m in re.findall(r'difficulty[=:]\s*(\d+)', content)}
        assert len(dcs) >= 4, f"examples anchor on too few DCs: {dcs}"
        assert min(dcs) <= 12, f"no easy-band example present: {dcs}"
        assert max(dcs) >= 25, f"no hard-band example present: {dcs}"

    def test_prompt_instructs_fiction_over_category(self):
        content = PROMPT_PATH.read_text().lower()
        assert "fiction" in content and "stakes" in content
