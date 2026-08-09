"""A DM reframe may not invent an attribute.

Regression origin (session fa9d2891, 2026-08-09):

    DM assessment: Kneeling Cultist: attribute None → Presence (DM reframe)
    DM assessment: Kneeling Cultist: skill None → Persuade (DM reframe - unskilled)

"Presence" is not one of the eight YAGS/Aeonisk attributes. The reframe was
applied anyway, and `attributes.get('Presence', 3)` quietly resolved it to the
default 3 — the action then rolled against a stat the character does not have.
This is the same drift the Dec 2025 Charisma removal was meant to end.

Skills are deliberately NOT validated here: the skill vocabulary is open across
configs, and a reframe onto a skill the character lacks is already meaningful
(skill_value 0, unskilled — the documented cost of misframing). An attribute
outside the fixed set of eight is a different thing: it cannot exist.
"""

import pytest

from scripts.aeonisk.multiagent.constants import YAGS_ATTRIBUTES
from scripts.aeonisk.multiagent.round_assessment import apply_assessments


class _Ruling:
    def __init__(self, character_name, difficulty=15, attribute=None, skill=None):
        self.character_name = character_name
        self.difficulty = difficulty
        self.attribute = attribute
        self.skill = skill
        self.reasoning = "test"


class _Assessment:
    def __init__(self, rulings):
        self.assessments = rulings


def _declared(character_name="Corin", **action_over):
    action = {"character_name": character_name, "attribute": "Intelligence",
              "attribute_value": 4, "skill": "Systems", "skill_value": 0}
    action.update(action_over)
    return {"agent_01": [{"action": action}]}


SHEETS = {"Corin": ({"Strength": 4, "Agility": 4, "Endurance": 4, "Dexterity": 4,
                     "Perception": 4, "Intelligence": 3, "Empathy": 3,
                     "Willpower": 5},
                    {"Guns": 4, "Melee": 3})}


class TestAttributeReframeValidation:

    def test_invented_attribute_is_rejected(self):
        """'Presence' does not exist — the player's framing must stand."""
        declared = _declared()

        changes = apply_assessments(
            declared, _Assessment([_Ruling("Corin", attribute="Presence")]), SHEETS)

        action = declared["agent_01"][0]["action"]
        assert action["attribute"] == "Intelligence"
        assert action["attribute_value"] == 4
        # no APPLIED reframe (the "old → new" form); a rejection note is expected
        assert not any("→ Presence" in c for c in changes)

    def test_rejection_is_reported(self):
        declared = _declared()

        changes = apply_assessments(
            declared, _Assessment([_Ruling("Corin", attribute="Presence")]), SHEETS)

        assert any("Presence" in c and "rejected" in c.lower() for c in changes)

    @pytest.mark.parametrize("attribute", YAGS_ATTRIBUTES)
    def test_every_canonical_attribute_is_accepted(self, attribute):
        declared = _declared(attribute="Intelligence")

        apply_assessments(
            declared, _Assessment([_Ruling("Corin", attribute=attribute)]), SHEETS)

        assert declared["agent_01"][0]["action"]["attribute"] == attribute

    def test_valid_reframe_recomputes_value_from_the_sheet(self):
        declared = _declared()

        apply_assessments(
            declared, _Assessment([_Ruling("Corin", attribute="Willpower")]), SHEETS)

        action = declared["agent_01"][0]["action"]
        assert action["attribute"] == "Willpower"
        assert action["attribute_value"] == 5

    def test_difficulty_still_applies_when_attribute_rejected(self):
        """A bad attribute must not discard the DM's difficulty ruling."""
        declared = _declared()

        apply_assessments(
            declared,
            _Assessment([_Ruling("Corin", difficulty=19, attribute="Presence")]),
            SHEETS)

        assert declared["agent_01"][0]["action"]["dm_assessed_difficulty"] == 19

    def test_skill_reframe_is_left_alone(self):
        """Skills stay open — a lacked skill is still a legal (unskilled) reframe."""
        declared = _declared()

        apply_assessments(
            declared, _Assessment([_Ruling("Corin", skill="Persuade")]), SHEETS)

        action = declared["agent_01"][0]["action"]
        assert action["skill"] == "Persuade"
        assert action["skill_value"] == 0
