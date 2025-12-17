"""
TDD: ActionDeclaration Must Support Purchase Fields

ROOT CAUSE (from session dcbc3d6a):
- Player LLM generates action with vendor_id="vnd_09x2"
- ActionDeclaration dataclass has NO vendor_id/item_id fields
- When .to_dict() is called, vendor_id is lost
- action_declaration event shows vendor_id: null

SOLUTION:
Add vendor_id and item_id fields to ActionDeclaration dataclass.

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration


class TestActionDeclarationPurchaseFields:
    """
    TDD: ActionDeclaration must have vendor_id and item_id fields.

    These fields are CRITICAL for the pre-validation purchase system.
    Without them, vendor_id gets stripped during action processing.
    """

    def test_action_declaration_has_vendor_id_field(self):
        """
        CRITICAL: ActionDeclaration must have vendor_id field.

        This test will FAIL until we add the field to action_schema.py
        """
        action = ActionDeclaration(
            intent="Purchase Med Kit",
            description="Buying medical supplies from vendor",
            attribute="Empathy",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple purchase transaction",
            character_name="Test Character",
            agent_id="player_01",
            action_type="social",
            vendor_id="vnd_abc123"  # This should work!
        )

        # ASSERTION: vendor_id should be preserved
        assert hasattr(action, 'vendor_id'), \
            "ActionDeclaration must have vendor_id field for purchase system"
        assert action.vendor_id == "vnd_abc123"

    def test_action_declaration_has_item_id_field(self):
        """
        CRITICAL: ActionDeclaration must have item_id field.
        """
        action = ActionDeclaration(
            intent="Purchase Med Kit",
            description="Buying medical supplies",
            attribute="Empathy",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple purchase",
            character_name="Test Character",
            agent_id="player_01",
            action_type="social",
            vendor_id="vnd_abc123",
            item_id="itm_xyz789"  # This should work!
        )

        # ASSERTION: item_id should be preserved
        assert hasattr(action, 'item_id'), \
            "ActionDeclaration must have item_id field for purchase system"
        assert action.item_id == "itm_xyz789"

    def test_to_dict_includes_vendor_and_item_ids(self):
        """
        CRITICAL: to_dict() must include vendor_id and item_id.

        This is what gets sent in ACTION_DECLARED messages and logged.
        """
        action = ActionDeclaration(
            intent="Purchase Med Kit",
            description="Buying medical supplies",
            attribute="Empathy",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple purchase",
            character_name="Test Character",
            agent_id="player_01",
            action_type="social",
            vendor_id="vnd_abc123",
            item_id="itm_xyz789"
        )

        action_dict = action.to_dict()

        # ASSERTION: Dict must contain purchase fields
        assert 'vendor_id' in action_dict, \
            "to_dict() must include vendor_id field"
        assert action_dict['vendor_id'] == "vnd_abc123"

        assert 'item_id' in action_dict, \
            "to_dict() must include item_id field"
        assert action_dict['item_id'] == "itm_xyz789"

    def test_purchase_fields_are_optional(self):
        """
        Design principle: vendor_id/item_id should be optional (None for non-purchase actions).
        """
        # Non-purchase action
        action = ActionDeclaration(
            intent="Search the terminal",
            description="Investigating the computer terminal",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=20,
            difficulty_justification="Complex system",
            character_name="Test Character",
            agent_id="player_01",
            action_type="investigate"
        )

        # ASSERTION: Should work without vendor_id/item_id
        assert hasattr(action, 'vendor_id')
        assert action.vendor_id is None
        assert hasattr(action, 'item_id')
        assert action.item_id is None

        # Dict should still have the fields (as None)
        action_dict = action.to_dict()
        assert 'vendor_id' in action_dict
        assert action_dict['vendor_id'] is None
        assert 'item_id' in action_dict
        assert action_dict['item_id'] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
