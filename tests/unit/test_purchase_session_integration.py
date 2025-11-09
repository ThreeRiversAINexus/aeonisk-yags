"""
Test that purchase effects flow from DM → session → mechanics.

Documents the bug where effects.purchase is logged to JSONL but NOT sent
back to session.py in the ACTION_RESOLVED message, so purchases never get processed.
"""

import pytest
from scripts.aeonisk.multiagent.schemas.story_events import PurchaseEffect


class TestPurchaseMessageFlow:
    """Test purchase data flows through the message pipeline."""

    def test_serializable_res_must_include_effects(self):
        """
        Document the bug: serializable_res at dm.py:2136 doesn't include effects.

        Bug flow:
        1. DM generates ActionResolution with effects.purchase populated ✓
        2. DM logs effects.purchase to JSONL ✓ (line 2088)
        3. DM creates serializable_res for ACTION_RESOLVED message ✗ (line 2136)
           - includes: player_id, character_name, initiative, action, resolution, narration
           - MISSING: effects (purchase, crafting)
        4. Session.py receives ACTION_RESOLVED, stores resolution_data ✗
           - resolution_data = serializable_res (without effects)
        5. Session.py tries: effects = resolution_data.get('effects', {}) ✗
           - Returns {} because effects not in resolution_data
        6. Session.py: if purchase_effect: <-- Never reached ✗

        Expected fix at dm.py:2136:
        ```python
        serializable_res = {
            'player_id': res['player_id'],
            'character_name': res['character_name'],
            'initiative': res['initiative'],
            'action': res['action'],
            'resolution': res['resolution']['outcome'],
            'narration': res['resolution']['narration'],
            'effects': res['resolution'].get('effects')  # ADD THIS
        }
        ```

        Where effects comes from:
        - DM._adjudicate_actions() builds resolution dict at line ~2050-2076
        - effects includes: damage, status_effects, inventory_changes, purchase, crafting
        - These come from mechanics.get_applicable_effects() or structured output
        """
        # This test documents the bug
        # Actual fix requires modifying dm.py:2136 to include effects
        pass

    def test_purchase_effect_schema_conversion(self):
        """
        Test that PurchaseEffect from DM can be converted to dict and back.

        This verifies that the data structure can survive serialization through
        the message pipeline.
        """
        # Create PurchaseEffect as DM would
        purchase = PurchaseEffect(
            success=True,
            vendor_name="Test Vendor",
            items_purchased=["Blood Offering", "Incense Bundle"],
            currency_spent={"drip": 20},
            narrative="The vendor accepts your currency and provides the items",
            failure_reason=None
        )

        # Convert to dict (as would happen in message payload)
        purchase_dict = purchase.model_dump()

        # Verify structure
        assert purchase_dict['success'] is True
        assert purchase_dict['vendor_name'] == "Test Vendor"
        assert len(purchase_dict['items_purchased']) == 2
        assert purchase_dict['currency_spent']['drip'] == 20

        # Verify can reconstruct from dict (as session.py would)
        reconstructed = PurchaseEffect(**purchase_dict)
        assert reconstructed.success is True
        assert reconstructed.items_purchased == ["Blood Offering", "Incense Bundle"]

    def test_effects_dict_structure(self):
        """
        Document expected effects dict structure in resolution_data.

        This is what session.py expects to receive in resolution_data.
        """
        expected_effects = {
            'damage': None,  # or DamageEffect dict
            'status_effects': [],
            'inventory_changes': [],
            'purchase': {
                'success': True,
                'vendor_name': 'Test Vendor',
                'items_purchased': ['Item 1'],
                'currency_spent': {'drip': 5},
                'narrative': 'Purchase successful - vendor provides item',
                'failure_reason': None
            },
            'crafting': None  # or CraftingEffect dict
        }

        # Session.py code at line 1200:
        # effects = resolution_data.get('effects', {})
        # purchase_effect = effects.get('purchase')
        # if purchase_effect:
        #     mechanics.process_purchase_effect(purchase_effect, character_state)

        # Verify structure
        purchase = expected_effects.get('purchase')
        assert purchase is not None
        assert purchase['success'] is True
        assert 'items_purchased' in purchase
        assert 'currency_spent' in purchase
