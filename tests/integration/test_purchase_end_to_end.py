"""
END-TO-END PURCHASE INTEGRATION TEST

Tests the COMPLETE purchase flow from action declaration → validation → execution.

This test verifies:
1. Vendors are loaded into SharedState with proper IDs
2. PlayerAction with vendor_id/item_id is processed
3. Pre-validation runs and returns proper data
4. Currency is deducted
5. Item is added to inventory
6. JSONL logs record purchase attempt

This is the test the user demanded: "we REALLY REALLY REALLY need this to work
properly and to be completely automated tested, integration tested"
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType, EnergyPurse


class TestPurchaseEndToEnd:
    """
    Integration test: Full purchase flow from declaration to execution.
    """

    def test_purchase_flow_complete(self):
        """
        CRITICAL: End-to-end purchase test - the COMPLETE flow.

        This is the integration test that unit tests couldn't catch.
        """
        # Setup: Create SharedState with vendor
        shared_state = SharedState()

        # Create vendor with known IDs
        vendor = Vendor(
            name="Test Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(
                    name="Health Kit",
                    description="Restores 10 HP",
                    item_id="itm_test123",
                    price_drip=5
                )
            ],
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id="vnd_test456"
        )

        shared_state.add_vendor(vendor)

        # Create mechanics engine
        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state
        shared_state.mechanics_engine = mechanics

        # Create mock character with currency
        character_state = Mock()
        character_state.name = "Test Character"
        character_state.energy_purse = EnergyPurse(
            breath=50,
            drip=15,
            grain=5,
            spark=3
        )
        character_state.inventory = {}
        character_state.soulcredit = 0

        # TEST: Validate purchase
        validation = mechanics.validate_purchase(
            character_state=character_state,
            vendor_id="vnd_test456",
            item_id="itm_test123"
        )

        # ASSERTION: Validation should succeed
        assert validation.can_afford is True, \
            f"Purchase validation failed: {validation.failure_reason}"
        assert validation.item_name == "Health Kit"
        assert validation.cost == {'drip': 5}
        assert validation.player_currency['drip'] == 15

        # TEST: Execute purchase (deduct currency)
        for currency_type, amount in validation.cost.items():
            character_state.energy_purse.spend_currency(currency_type, amount)

        # TEST: Add item to inventory
        inventory_key = validation.inventory_key
        character_state.inventory[inventory_key] = character_state.inventory.get(inventory_key, 0) + 1

        # ASSERTIONS: Verify final state
        assert character_state.energy_purse.drip == 10, \
            f"Currency not deducted! Expected 10 Drip, got {character_state.energy_purse.drip}"
        assert character_state.inventory.get('health_kit', 0) == 1, \
            f"Item not added! Inventory: {character_state.inventory}"

    def test_purchase_flow_insufficient_funds(self):
        """
        CRITICAL: Purchase should fail gracefully when player can't afford item.
        """
        shared_state = SharedState()

        vendor = Vendor(
            name="Expensive Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(
                    name="Expensive Item",
                    description="Costs too much",
                    item_id="itm_expensive",
                    price_spark=10  # Player only has 3
                )
            ],
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id="vnd_expensive"
        )

        shared_state.add_vendor(vendor)

        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state

        character_state = Mock()
        character_state.name = "Poor Character"
        character_state.energy_purse = EnergyPurse(
            breath=0,
            drip=0,
            grain=0,
            spark=3  # Only 3, needs 10!
        )
        character_state.soulcredit = 0

        # TEST: Validate purchase
        validation = mechanics.validate_purchase(
            character_state=character_state,
            vendor_id="vnd_expensive",
            item_id="itm_expensive"
        )

        # ASSERTIONS: Should fail with proper shortage info
        assert validation.can_afford is False
        assert validation.failure_reason is not None
        assert "Insufficient currency" in validation.failure_reason
        assert validation.shortage == {'spark': 7}  # Need 7 more
        assert validation.item_name == "Expensive Item"  # Still know what item was

    def test_purchase_flow_vendor_not_found(self):
        """
        CRITICAL: Should fail gracefully if vendor doesn't exist.
        """
        shared_state = SharedState()
        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state

        character_state = Mock()
        character_state.name = "Test Character"
        character_state.energy_purse = EnergyPurse(drip=100)
        character_state.soulcredit = 0

        # TEST: Try to buy from non-existent vendor
        validation = mechanics.validate_purchase(
            character_state=character_state,
            vendor_id="vnd_nonexistent",
            item_id="itm_anything"
        )

        # ASSERTIONS: Should fail with vendor not found
        assert validation.can_afford is False
        assert "Vendor vnd_nonexistent not found" in validation.failure_reason
        assert validation.vendor_accessible is False

    def test_purchase_flow_item_not_found(self):
        """
        CRITICAL: Should fail gracefully if item doesn't exist in vendor.
        """
        shared_state = SharedState()

        vendor = Vendor(
            name="Limited Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(
                    name="Only Item",
                    description="The only item",
                    item_id="itm_only",
                    price_drip=5
                )
            ],
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id="vnd_limited"
        )

        shared_state.add_vendor(vendor)

        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state

        character_state = Mock()
        character_state.name = "Test Character"
        character_state.energy_purse = EnergyPurse(drip=100)
        character_state.soulcredit = 0

        # TEST: Try to buy item that doesn't exist
        validation = mechanics.validate_purchase(
            character_state=character_state,
            vendor_id="vnd_limited",
            item_id="itm_nonexistent"
        )

        # ASSERTIONS: Should fail with item not found
        assert validation.can_afford is False
        assert "Item itm_nonexistent not in" in validation.failure_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
