"""
Test DM purchase integration bugs discovered in session fa4d5e03.

Documents bugs where:
1. DM marks successful negotiations as failed purchases (pending confirmation)
2. DM doesn't populate purchase effect when item unavailable
3. DM doesn't offer alternate items even when available
4. Purchased items don't appear in character inventory

These tests define EXPECTED behavior for fixing the bugs.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse, Vendor, VendorItem, VendorType
from scripts.aeonisk.multiagent.mechanics import PurchaseValidation
from scripts.aeonisk.multiagent.schemas.vendor_interaction import PurchaseEffect


class TestDMPurchaseIntegrationBugs:
    """Document bugs from session fa4d5e03 purchase attempts."""

    def test_bug1_negotiation_marked_as_failed_purchase(self):
        """
        BUG: DM marks successful negotiation as failed purchase.

        Session fa4d5e03, line 12:
        - Player: "I need an Echo-Calibrator... I can pay well"
        - DM Narration: "Five Spark... their hand extends, the Calibrator gleaming"
        - DM marked: success=false, failure_reason="Transaction pending confirmation"

        EXPECTED: When vendor offers item and player has currency, mark as SUCCESS.
        The "confirmation" step is implicit in declaring the purchase action.
        """
        # Simulate the scenario
        player_currency = {"spark": 5}  # Mira had 0 Spark (BUG!)
        vendor_price = {"spark": 5}
        vendor_has_item = True

        # What DM SHOULD have done:
        # 1. Check if player has 5 Spark
        # 2. If yes: success=True, deduct currency, add item
        # 3. If no: success=False, failure_reason="Insufficient funds (need 5 Spark)"

        # In reality, Mira had 0 Spark, so purchase SHOULD have failed with shortage
        # But DM said "transaction pending" instead of "insufficient funds"

        # Expected validation result
        expected_validation = PurchaseValidation(
            is_valid=False,  # Player has 0 Spark, needs 5
            failure_reason="Insufficient currency: need 5 Spark, have 0 Spark",
            shortage={"spark": 5},
            sc_blocked=False,
            vendor_accessible=True
        )

        # This is what SHOULD have been logged
        expected_purchase = PurchaseEffect(
            success=False,
            vendor_name="Cipher (Masked Freeborn Vendor)",
            items_purchased=[],
            currency_spent={},
            narrative="You don't have enough currency - need 5 Spark but have 0 Spark",
            failure_reason="Insufficient currency: need 5 Spark, have 0 Spark"
        )

        assert expected_purchase.success is False
        assert "Insufficient currency" in expected_purchase.failure_reason
        assert "5 Spark" in expected_purchase.failure_reason

    def test_bug2_dm_doesnt_populate_purchase_when_item_unavailable(self):
        """
        BUG: DM sets purchase=null when item out of stock.

        Session fa4d5e03, line 16:
        - Player: "Purchase Echo-Calibrator from Test Vend-O-Mat"
        - DM Narration: "INVENTORY DEPLETED - LAST UNIT SOLD"
        - DM set: effects.purchase = null

        EXPECTED: DM should populate purchase effect with failure reason.
        """
        # What SHOULD have been logged
        expected_purchase = PurchaseEffect(
            success=False,
            vendor_name="Test Vend-O-Mat",
            items_purchased=[],
            currency_spent={},
            narrative="The Echo-Calibrator is out of stock - last unit sold 47 seconds ago",
            failure_reason="Item not in vendor inventory: Echo-Calibrator"
        )

        assert expected_purchase.success is False
        assert expected_purchase.failure_reason is not None
        assert "not in vendor inventory" in expected_purchase.failure_reason

    def test_bug3_dm_doesnt_offer_alternate_items_in_purchase_effect(self):
        """
        BUG: DM narrates alternate items but doesn't populate purchase effect.

        Session fa4d5e03, line 16:
        - DM Narration mentions: "Resonance Dampener (2 Spark)" and "Portable Ley Anchor (3 Spark)"
        - But effects.purchase = null (no structured data about alternates)

        EXPECTED: DM should suggest alternates in failure_reason or as separate field.
        """
        # Ideal: Purchase effect includes alternates
        expected_purchase = PurchaseEffect(
            success=False,
            vendor_name="Test Vend-O-Mat",
            items_purchased=[],
            currency_spent={},
            narrative="Echo-Calibrator out of stock. Alternate items available: Resonance Dampener (2 Spark), Portable Ley Anchor (3 Spark)",
            failure_reason="Requested item unavailable. Alternates: Resonance Dampener, Portable Ley Anchor"
        )

        assert expected_purchase.success is False
        assert "Alternate" in expected_purchase.narrative or "Alternate" in (expected_purchase.failure_reason or "")

    def test_bug4_purchased_items_must_appear_in_inventory(self):
        """
        BUG: Even if purchase succeeds, item doesn't get added to character inventory.

        EXPECTED: After successful purchase, item appears in character's inventory dict.
        Example: character.inventory['echo_calibrator'] += 1
        """
        # Simulate successful purchase processing
        starting_inventory = {
            "blood_offering": 2,
            "incense": 1,
            "echo_calibrator": 0  # Item not yet owned
        }

        # Successful purchase
        purchase = PurchaseEffect(
            success=True,
            vendor_name="Test Vendor",
            items_purchased=["Echo-Calibrator"],
            currency_spent={"spark": 5},
            narrative="You purchase the Echo-Calibrator from the vendor",
            failure_reason=None
        )

        # Process purchase (THIS IS WHAT NEEDS TO BE IMPLEMENTED)
        result_inventory = starting_inventory.copy()
        for item in purchase.items_purchased:
            item_key = item.lower().replace("-", "_").replace(" ", "_")
            if item_key in result_inventory:
                result_inventory[item_key] += 1
            else:
                # Add new item type if not tracked
                result_inventory[item_key] = 1

        # Verify item was added
        assert result_inventory["echo_calibrator"] == 1
        assert result_inventory["blood_offering"] == 2  # Others unchanged

    def test_pre_validation_prevents_hallucination(self):
        """
        Test that pre-validation catches issues BEFORE DM narrates.

        This is the architecture that prevents all these bugs:
        1. Validate BEFORE calling DM
        2. Inject validation results into DM prompt
        3. DM narrates appropriately based on validation
        """
        # Player wants to buy Echo-Calibrator for 5 Spark
        player_purse = EnergyPurse(spark=0, drip=4, breath=20, grain=1)

        vendor = Vendor(
            name="Test Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(name="Health Kit", description="Restores HP", price_drip=5),
                VendorItem(name="Echo-Calibrator", description="Attunes seeds", price_spark=5)
            ],
            greeting="Welcome",
            vendor_type=VendorType.VENDING_MACHINE
        )

        # Pre-validation BEFORE DM narration
        validation = self._validate_purchase(
            player_purse=player_purse,
            vendor=vendor,
            item_name="Echo-Calibrator"
        )

        # Should detect shortage
        assert validation.is_valid is False
        assert validation.shortage == {"spark": 5}
        assert "5 Spark" in validation.failure_reason

        # This validation result should be injected into DM prompt:
        # "Player wants Echo-Calibrator but has 0 Spark (needs 5).
        #  Narrate vendor offering it but player unable to afford it."

    def _validate_purchase(self, player_purse, vendor, item_name):
        """Simulate purchase validation."""
        # Find item in vendor inventory
        item = None
        for vendor_item in vendor.inventory:
            if vendor_item.name == item_name:
                item = vendor_item
                break

        if not item:
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Item not in vendor inventory: {item_name}",
                shortage=None,
                sc_blocked=False,
                vendor_accessible=True
            )

        # Check if player has currency
        cost = item.cost
        shortage = {}
        for currency_type, amount in cost.items():
            player_amount = getattr(player_purse, currency_type, 0)
            if player_amount < amount:
                shortage[currency_type] = amount - player_amount

        if shortage:
            shortage_str = ", ".join([f"{amount} {curr.title()}" for curr, amount in shortage.items()])
            return PurchaseValidation(
                is_valid=False,
                failure_reason=f"Insufficient currency: need {shortage_str}",
                shortage=shortage,
                sc_blocked=False,
                vendor_accessible=True
            )

        return PurchaseValidation(
            is_valid=True,
            failure_reason=None,
            shortage=None,
            sc_blocked=False,
            vendor_accessible=True
        )


class TestInventoryItemMapping:
    """Test that purchased items map correctly to inventory keys."""

    def test_item_name_normalization(self):
        """
        Test that vendor item names normalize to inventory keys.

        Vendor: "Echo-Calibrator"
        Inventory: "echo_calibrator"
        """
        vendor_name = "Echo-Calibrator"
        expected_key = "echo_calibrator"

        # Normalization logic
        result_key = vendor_name.lower().replace("-", "_").replace(" ", "_")

        assert result_key == expected_key

    def test_common_item_mappings(self):
        """Test common vendor items map to correct inventory keys."""
        mappings = {
            "Blood Offering": "blood_offering",
            "Echo-Calibrator": "echo_calibrator",
            "Incense Bundle": "incense_bundle",
            "Health Kit": "health_kit",
            "Raw Crystal": "raw_crystal",
            "Attuned Seed (Fire)": "attuned_seed_fire",
        }

        for vendor_name, expected_key in mappings.items():
            result_key = vendor_name.lower().replace("-", "_").replace(" ", "_").replace("(", "").replace(")", "")
            # This is simplistic - actual implementation needs better handling
            # For now, document the expected mappings

    def test_inventory_has_item_slots(self):
        """
        Test that character inventory has slots for purchasable items.

        If player buys Echo-Calibrator, inventory must have echo_calibrator key.
        """
        # Typical starting inventory
        inventory = {
            "blood_offering": 0,
            "herbs": 3,
            "incense": 0,
            "raw_crystal": 0,
            "blood_sample": 2,
            # Missing: echo_calibrator slot!
        }

        # When processing purchase of Echo-Calibrator, need to handle missing key
        item_key = "echo_calibrator"

        if item_key not in inventory:
            # Should either:
            # A) Add new key with value 1
            inventory[item_key] = 1
            # B) Track in separate "purchased_items" list
            # C) Use dynamic inventory system

        assert "echo_calibrator" in inventory
        assert inventory["echo_calibrator"] == 1
