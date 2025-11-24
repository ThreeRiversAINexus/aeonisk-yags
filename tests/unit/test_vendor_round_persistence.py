"""
Test that vendors persist across multiple rounds in player prompts.
"""

import pytest
from scripts.aeonisk.multiagent.dm import Scenario
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestVendorRoundPersistence:
    """Test vendor persistence across game rounds."""

    def test_vendor_remains_in_scenario_across_rounds(self):
        """
        Verify that once a vendor is in a scenario, it persists for all rounds.

        The scenario object is created once at session start and reused for all rounds.
        Vendors should remain in scenario.active_vendors throughout the session.
        """
        # Create vendor
        vendor = Vendor(
            name="Test Vendor",
            faction="Freeborn",
            inventory=[
                VendorItem(name="Test Item", description="Test", price_drip=5)
            ],
            greeting="Hello",
            vendor_type=VendorType.HUMAN_TRADER
        )

        # Create scenario with vendor (happens at session start)
        scenario = Scenario(
            theme="Test",
            location="Test Location",
            situation="Test situation",
            active_npcs=[],
            environmental_factors=[],
            void_level=5,
            active_vendors=[vendor]
        )

        # Verify vendor is in scenario
        assert scenario.active_vendors is not None
        assert len(scenario.active_vendors) == 1
        assert scenario.active_vendors[0].name == "Test Vendor"

        # Simulate multiple rounds - scenario object doesn't change
        # In real sessions, the same scenario object persists across all rounds
        # unless explicitly modified by StoryAdvancement.vendor_departures

        # Round 1 - vendor should be present
        round_1_vendors = scenario.active_vendors
        assert len(round_1_vendors) == 1
        assert round_1_vendors[0].name == "Test Vendor"

        # Round 2 - vendor should still be present (no departure)
        round_2_vendors = scenario.active_vendors
        assert len(round_2_vendors) == 1
        assert round_2_vendors[0].name == "Test Vendor"

        # Round 3 - vendor should still be present
        round_3_vendors = scenario.active_vendors
        assert len(round_3_vendors) == 1
        assert round_3_vendors[0].name == "Test Vendor"

        # Verify it's the same object (not a copy)
        assert round_1_vendors is round_2_vendors
        assert round_2_vendors is round_3_vendors

    def test_scenario_active_vendors_is_persistent_reference(self):
        """
        Verify that scenario.active_vendors is a persistent list reference,
        not recreated each time it's accessed.
        """
        vendor = Vendor(
            name="Persistent Vendor",
            faction="Freeborn",
            inventory=[],
            greeting="Hello",
            vendor_type=VendorType.HUMAN_TRADER
        )

        scenario = Scenario(
            theme="Test",
            location="Test",
            situation="Test",
            active_npcs=[],
            environmental_factors=[],
            void_level=5,
            active_vendors=[vendor]
        )

        # Get reference to active_vendors
        vendors_ref_1 = scenario.active_vendors
        vendors_ref_2 = scenario.active_vendors

        # Should be the same list object
        assert vendors_ref_1 is vendors_ref_2

        # Modifications to the list should persist
        assert len(vendors_ref_1) == 1

        # In real sessions, vendor removal happens via SharedState.remove_vendor()
        # which is triggered by StoryAdvancement.vendor_departures
        # NOT by directly modifying scenario.active_vendors

    def test_vendor_inventory_accessible_across_rounds(self):
        """
        Verify that vendor inventory remains accessible in all rounds.

        Players should be able to see vendor inventory in Round 1, Round 2, etc.
        """
        vendor = Vendor(
            name="Shop Vendor",
            faction="Freeborn",
            inventory=[
                VendorItem(name="Item 1", description="First item", price_drip=5),
                VendorItem(name="Item 2", description="Second item", price_drip=10),
                VendorItem(name="Item 3", description="Third item", price_spark=1)
            ],
            greeting="Welcome!",
            vendor_type=VendorType.VENDING_MACHINE
        )

        scenario = Scenario(
            theme="Shopping",
            location="Market",
            situation="Shopping scenario",
            active_npcs=[],
            environmental_factors=[],
            void_level=3,
            active_vendors=[vendor]
        )

        # Round 1 - all 3 items visible
        round_1_inventory = scenario.active_vendors[0].inventory
        assert len(round_1_inventory) == 3
        assert round_1_inventory[0].name == "Item 1"
        assert round_1_inventory[1].name == "Item 2"
        assert round_1_inventory[2].name == "Item 3"

        # Round 2 - same inventory (in real sessions, inventory changes via purchase processing)
        round_2_inventory = scenario.active_vendors[0].inventory
        assert len(round_2_inventory) == 3
        assert round_2_inventory is round_1_inventory  # Same object

        # Inventory is persistent reference
        assert scenario.active_vendors[0].inventory is round_1_inventory
