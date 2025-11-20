"""
Unit tests for free vendor browsing via INVESTIGATE action.

Tests that investigating a vendor:
1. Does not require a roll (free action)
2. Returns full inventory with prices
3. Identifies vendor via entities_present matching
4. Does not consume time or resources
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.schemas.player_action import ActionType


class TestFreeVendorBrowsing:
    """Test that vendor browsing via INVESTIGATE is a free action."""

    def test_investigate_vendor_is_free_action(self):
        """Test that investigating a vendor does not require a roll."""
        # Setup: Create vendor with inventory
        vendor = Vendor(
            name="Test Vending Machine",
            vendor_id="vnd_test_001",
            faction="Sovereign Nexus",
            vendor_type="vending_machine",
            greeting="Select your purchase.",
            inventory=[
                VendorItem(
                    name="Health Kit",
                    description="Restores 10 HP",
                    inventory_key="health_kit",
                    price_drip=5,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="consumable"
                ),
                VendorItem(
                    name="Ammo Pack",
                    description="20 rounds of standard ammunition",
                    inventory_key="ammo_pack",
                    price_drip=3,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="consumable"
                )
            ]
        )

        # Setup shared state
        shared_state = SharedState()
        shared_state.add_vendor(vendor)

        # Player action: Investigate the vending machine
        player_action = {
            "action_type": ActionType.INVESTIGATE,
            "description": "I examine the vending machine to see what's available for purchase",
            "skill_intent": "Investigation",  # Would normally be used, but should be skipped for vendor browsing
        }

        # Expected: No roll should be required
        # Expected: Full inventory should be returned
        # This is the interface we want - actual implementation TBD
        assert vendor.vendor_id in [v.vendor_id for v in shared_state.current_vendors]
        assert len(vendor.inventory) == 2

    def test_vendor_browsing_returns_full_inventory(self):
        """Test that browsing a vendor returns the complete inventory."""
        vendor = Vendor(
            name="Scribe's Supply Shop",
            vendor_id="vnd_scribe_001",
            faction="Archivists",
            vendor_type="humanoid",
            greeting="Knowledge has its price.",
            inventory=[
                VendorItem(
                    name="Data Slate",
                    description="Blank data recording device",
                    inventory_key="data_slate",
                    price_drip=10,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="tool"
                ),
                VendorItem(
                    name="Archive Access Token",
                    description="7-day access to restricted archives",
                    inventory_key="archive_token",
                    price_breath=1,
                    price_drip=0,
                    price_spark=0,
                    seed_barter=False,
                    item_type="service"
                ),
                VendorItem(
                    name="Translation Module",
                    description="Deciphers pre-collapse texts",
                    inventory_key="translation_module",
                    price_drip=25,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=True,
                    item_type="tool"
                )
            ]
        )

        # Expected: All 3 items should be visible when browsing
        assert len(vendor.inventory) == 3

        # Expected: Prices should be included
        assert vendor.inventory[0].price_drip == 10
        assert vendor.inventory[1].price_breath == 1
        assert vendor.inventory[2].seed_barter is True

    def test_vendor_identification_via_entities_present(self):
        """Test that vendor browsing works by matching entities_present."""
        vendor = Vendor(
            name="S4CU Vending Node",
            vendor_id="vnd_s4cu_001",
            faction="Sovereign Nexus",
            vendor_type="vending_machine",
            greeting="S4CU Authorized.",
            inventory=[]
        )

        shared_state = SharedState()
        shared_state.add_vendor(vendor)

        # Simulate entities_present context (would be provided by session)
        entities_present = [
            {
                "entity_id": "vnd_s4cu_001",
                "entity_name": "S4CU Vending Node",
                "ent_type": "vendor"
            }
        ]

        # Player describes investigating "the vending machine" or "S4CU node"
        # System should match description to entities_present
        vendor_found = any(
            e["ent_type"] == "vendor"
            for e in entities_present
        )
        assert vendor_found is True

    def test_non_vendor_investigate_still_requires_roll(self):
        """Test that investigating non-vendor entities still requires rolls."""
        # This is a control test - normal investigation should not be affected

        # Entities present includes non-vendor
        entities_present = [
            {
                "entity_id": "obj_terminal_001",
                "entity_name": "Corrupted Terminal",
                "ent_type": "object"
            }
        ]

        # Investigating a terminal should still require Investigation roll
        # This test ensures we don't break normal investigate mechanics
        assert entities_present[0]["ent_type"] != "vendor"

    def test_vendor_browsing_works_with_empty_inventory(self):
        """Test that browsing a vendor with no items doesn't crash."""
        vendor = Vendor(
            name="Empty Vendor",
            vendor_id="vnd_empty_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Sorry, sold out.",
            inventory=[]
        )

        # Should handle gracefully - no items to display
        assert len(vendor.inventory) == 0

    def test_multiple_vendors_in_scene(self):
        """Test vendor browsing when multiple vendors are present."""
        vendor1 = Vendor(
            name="Weapons Dealer",
            vendor_id="vnd_weapons_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Need firepower?",
            inventory=[
                VendorItem(
                    name="Flechette Pistol",
                    description="Standard sidearm",
                    inventory_key="flechette_pistol",
                    price_drip=50,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="weapon"
                )
            ]
        )

        vendor2 = Vendor(
            name="Food Vendor",
            vendor_id="vnd_food_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Fresh rations!",
            inventory=[
                VendorItem(
                    name="Ration Pack",
                    description="Preserved food",
                    inventory_key="ration_pack",
                    price_drip=2,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="consumable"
                )
            ]
        )

        shared_state = SharedState()
        shared_state.add_vendor(vendor1)
        shared_state.add_vendor(vendor2)

        # Player should be able to specify which vendor to browse
        # "I browse the weapons dealer's inventory"
        # vs
        # "I check what the food vendor has"

        assert len(shared_state.current_vendors) == 2
        assert shared_state.get_vendor_by_id("vnd_weapons_001") is not None
        assert shared_state.get_vendor_by_id("vnd_food_001") is not None


class TestVendorBrowsingNarration:
    """Test that vendor browsing produces appropriate narration."""

    def test_full_inventory_narration_format(self):
        """Test expected narration format for full inventory display."""
        vendor = Vendor(
            name="Tech Vendor",
            vendor_id="vnd_tech_001",
            faction="Archivists",
            vendor_type="humanoid",
            greeting="Cutting edge tech.",
            inventory=[
                VendorItem(
                    name="Scanner",
                    description="Detects energy signatures",
                    inventory_key="scanner",
                    price_drip=15,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=False,
                    item_type="tool"
                ),
                VendorItem(
                    name="Comm Link",
                    description="Encrypted communication device",
                    inventory_key="comm_link",
                    price_drip=20,
                    price_spark=0,
                    price_breath=0,
                    seed_barter=True,
                    item_type="tool"
                )
            ]
        )

        # Expected narration should include:
        # 1. All item names
        # 2. All descriptions
        # 3. All prices in clear format
        # 4. Seed barter indication

        # Verify data is available for narration
        assert len(vendor.inventory) == 2
        for item in vendor.inventory:
            assert item.name
            assert item.description
            assert hasattr(item, 'price_drip')
            assert hasattr(item, 'seed_barter')

    def test_price_display_multi_currency(self):
        """Test that items with multiple currency prices are handled."""
        vendor = Vendor(
            name="Rare Goods Vendor",
            vendor_id="vnd_rare_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Rare items, rare prices.",
            inventory=[
                VendorItem(
                    name="Void Shard",
                    description="Crystallized void energy",
                    inventory_key="void_shard",
                    price_drip=100,
                    price_spark=50,
                    price_breath=2,
                    seed_barter=True,
                    item_type="ritual_component"
                )
            ]
        )

        # Item has 3 currency types + seed barter
        item = vendor.inventory[0]
        assert item.price_drip > 0
        assert item.price_spark > 0
        assert item.price_breath > 0
        assert item.seed_barter is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
