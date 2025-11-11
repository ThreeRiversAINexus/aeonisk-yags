"""
TDD: ActionValidator Must Accept ActionType.PURCHASE

ROOT CAUSE (from session with ActionType.PURCHASE):
- Added ActionType.PURCHASE to enum
- ActionDeclaration.validate() has HARDCODED list of valid types
- List doesn't include "purchase"
- Result: "Action type must be one of: explore, investigate, ritual, social..."

SOLUTION:
Add "purchase" to valid_action_types list in action_schema.py

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration


class TestActionValidatorPurchase:
    """
    TDD: ActionDeclaration.validate() must accept action_type="purchase".
    """

    def test_purchase_action_type_is_valid(self):
        """
        CRITICAL: Validator must accept action_type="purchase".

        This test will FAIL until we add "purchase" to valid_action_types list.
        """
        action = ActionDeclaration(
            intent="Purchase Med Kit from vendor",
            description="Buying medical supplies",
            attribute="Charisma",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Simple transaction",
            character_name="Test Character",
            agent_id="player_01",
            action_type="purchase",  # Should be valid!
            vendor_id="vnd_test",
            item_id="itm_test"
        )

        errors = action.validate()

        # ASSERTION: Should have NO errors for purchase action type
        assert len(errors) == 0, \
            f"action_type='purchase' should be valid, but got errors: {errors}"

    def test_social_action_type_still_valid(self):
        """
        Design principle: Existing action types should still work.
        """
        action = ActionDeclaration(
            intent="Persuade guard",
            description="Convincing the guard to let us pass",
            attribute="Charisma",
            skill="Charm",
            difficulty_estimate=18,
            difficulty_justification="Suspicious guard",
            character_name="Test Character",
            agent_id="player_01",
            action_type="social"
        )

        errors = action.validate()
        assert len(errors) == 0

    def test_invalid_action_type_rejected(self):
        """
        Design principle: Invalid action types should still be rejected.
        """
        action = ActionDeclaration(
            intent="Do something",
            description="Testing invalid action type",
            attribute="Charisma",
            skill="Charm",
            difficulty_estimate=15,
            difficulty_justification="Testing",
            character_name="Test Character",
            agent_id="player_01",
            action_type="invalid_type"  # NOT valid
        )

        errors = action.validate()

        # Should have at least one error about action type
        assert len(errors) > 0
        assert any("Action type must be one of" in error for error in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
