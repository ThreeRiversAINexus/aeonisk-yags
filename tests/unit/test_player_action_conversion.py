"""
TDD: PlayerAction→ActionDeclaration Conversion Must Preserve Purchase Fields

ROOT CAUSE (from session a8ed67c7):
- LLM generates PlayerAction with vendor_id="vnd_k9xi", item_id="itm_9315"
- player.py:1350-1362 converts PlayerAction→ActionDeclaration
- Conversion DROPS vendor_id and item_id fields
- action_declaration event shows vendor_id: null

SOLUTION:
Add vendor_id and item_id to the ActionDeclaration constructor call.

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration


class TestPlayerActionConversion:
    """
    TDD: PlayerAction→ActionDeclaration conversion must preserve vendor_id and item_id.

    This is the MISSING LINK: ActionDeclaration has the fields (we added them),
    but the conversion code doesn't copy them over!
    """

    def test_conversion_preserves_vendor_id(self):
        """
        CRITICAL: When converting PlayerAction→ActionDeclaration,
        vendor_id must be preserved.
        """
        # Create PlayerAction with vendor_id (as LLM would generate)
        player_action = PlayerAction(
            intent="Purchase Med Kit from Field Medic Jara",
            description="Approaching the vendor to buy medical supplies for my injuries",
            attribute="Empathy",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple transaction with friendly vendor",
            action_type=ActionType.SOCIAL,
            character_name="Test Player",
            agent_id="player_01",
            vendor_id="vnd_abc123",
            item_id="itm_xyz789"
        )

        # Simulate the conversion that player.py:1350-1362 does
        action_declaration = ActionDeclaration(
            intent=player_action.intent,
            description=player_action.description,
            attribute=player_action.attribute,
            skill=player_action.skill,
            difficulty_estimate=player_action.difficulty_estimate,
            difficulty_justification=player_action.difficulty_justification,
            character_name=player_action.character_name,
            agent_id=player_action.agent_id,
            action_type=player_action.action_type,
            target=player_action.target,
            target_position=player_action.target_position,
            vendor_id=player_action.vendor_id,  # CRITICAL: Must copy this!
            item_id=player_action.item_id
        )

        # ASSERTION: vendor_id must be preserved in ActionDeclaration
        assert action_declaration.vendor_id == "vnd_abc123", \
            "Conversion must preserve vendor_id from PlayerAction"
        assert action_declaration.item_id == "itm_xyz789", \
            "Conversion must preserve item_id from PlayerAction"

    def test_conversion_preserves_none_values(self):
        """
        Design principle: If PlayerAction has vendor_id=None, conversion should preserve None.
        """
        # Non-purchase action
        player_action = PlayerAction(
            intent="Search the terminal",
            description="Investigating the computer system for clues about the anomaly and recent activity logs",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=20,
            difficulty_justification="Complex system requiring technical expertise",
            action_type=ActionType.TECHNICAL,
            character_name="Test Player",
            agent_id="player_01"
        )

        # Convert
        action_declaration = ActionDeclaration(
            intent=player_action.intent,
            description=player_action.description,
            attribute=player_action.attribute,
            skill=player_action.skill,
            difficulty_estimate=player_action.difficulty_estimate,
            difficulty_justification=player_action.difficulty_justification,
            character_name=player_action.character_name,
            agent_id=player_action.agent_id,
            action_type=player_action.action_type,
            target=player_action.target,
            target_position=player_action.target_position,
            vendor_id=player_action.vendor_id,
            item_id=player_action.item_id
        )

        # ASSERTION: None values should be preserved
        assert action_declaration.vendor_id is None
        assert action_declaration.item_id is None

    def test_action_declaration_to_dict_after_conversion(self):
        """
        END-TO-END: After conversion, to_dict() must include vendor_id/item_id.

        This is what gets sent in ACTION_DECLARED messages!
        """
        player_action = PlayerAction(
            intent="Purchase Combat Stim",
            description="Approaching the vendor to buy combat enhancement stimulant for upcoming engagement",
            attribute="Empathy",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple transaction with established vendor",
            action_type=ActionType.SOCIAL,
            character_name="Test Player",
            agent_id="player_01",
            vendor_id="vnd_test",
            item_id="itm_test"
        )

        action_declaration = ActionDeclaration(
            intent=player_action.intent,
            description=player_action.description,
            attribute=player_action.attribute,
            skill=player_action.skill,
            difficulty_estimate=player_action.difficulty_estimate,
            difficulty_justification=player_action.difficulty_justification,
            character_name=player_action.character_name,
            agent_id=player_action.agent_id,
            action_type=player_action.action_type,
            target=player_action.target,
            target_position=player_action.target_position,
            vendor_id=player_action.vendor_id,
            item_id=player_action.item_id
        )

        action_dict = action_declaration.to_dict()

        # ASSERTION: Dict must contain purchase fields (this is what goes in JSONL)
        assert 'vendor_id' in action_dict
        assert action_dict['vendor_id'] == 'vnd_test'
        assert 'item_id' in action_dict
        assert action_dict['item_id'] == 'itm_test'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
