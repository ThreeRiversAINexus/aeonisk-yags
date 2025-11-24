"""
Unit tests for vendor spawn-time validation.

Tests NPCSpawn schema validation of vendor_inventory field to ensure:
1. Only VendorItem objects are accepted
2. Negative prices are rejected
3. Malformed data is caught at spawn time (not runtime)

Following TDD: These tests should FAIL initially, then PASS after fixing
the NPCSpawn.vendor_inventory type from List to List[VendorItem].
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.schemas.story_events import NPCSpawn
from scripts.aeonisk.multiagent.energy_economy import VendorItem


class TestVendorInventoryTypeValidation:
    """Test that vendor_inventory only accepts VendorItem instances."""

    def test_valid_vendor_with_proper_items(self):
        """Valid vendor with VendorItem instances should pass."""
        vendor_spawn = NPCSpawn(
            name="Test Vendor",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="A friendly vendor selling supplies",
            health=50,
            soak=0,
            skills={"Barter": 2},
            is_vendor=True,
            vendor_inventory=[
                VendorItem(
                    name="Medkit",
                    description="Basic medical supplies",
                    price_drip=5,
                    item_type="consumable"
                ),
                VendorItem(
                    name="Ration Pack",
                    description="Standard survival rations",
                    price_drip=2,
                    item_type="food"
                )
            ]
        )

        assert vendor_spawn.is_vendor is True
        assert len(vendor_spawn.vendor_inventory) == 2
        assert all(isinstance(item, VendorItem) for item in vendor_spawn.vendor_inventory)

    def test_reject_string_list_as_inventory(self):
        """Vendor inventory with strings should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NPCSpawn(
                name="Broken Vendor",
                faction="neutral",
                entity_type="neutral",
                threat_level="non_combatant",
                disposition="friendly",
                description="Vendor with malformed inventory",
                health=50,
                soak=0,
                skills={},
                is_vendor=True,
                vendor_inventory=["Medkit", "Ammo", "Food"]  # WRONG: strings
            )

        # Should raise validation error about incorrect type
        assert "vendor_inventory" in str(exc_info.value).lower()

    def test_reject_dict_list_as_inventory(self):
        """Vendor inventory with raw dicts should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NPCSpawn(
                name="Broken Vendor",
                faction="neutral",
                entity_type="neutral",
                threat_level="non_combatant",
                disposition="friendly",
                description="Vendor with dict inventory",
                health=50,
                soak=0,
                skills={},
                is_vendor=True,
                vendor_inventory=[
                    {"name": "Medkit", "price": 5}  # WRONG: dict, not VendorItem
                ]
            )

        assert "vendor_inventory" in str(exc_info.value).lower()

    def test_reject_mixed_type_inventory(self):
        """Vendor inventory with mixed types should be rejected."""
        valid_item = VendorItem(
            name="Medkit",
            description="Medical supplies",
            price_drip=5,
            item_type="consumable"
        )

        with pytest.raises(ValidationError):
            NPCSpawn(
                name="Mixed Vendor",
                faction="neutral",
                entity_type="neutral",
                threat_level="non_combatant",
                disposition="friendly",
                description="Vendor with mixed types",
                health=50,
                soak=0,
                skills={},
                is_vendor=True,
                vendor_inventory=[
                    valid_item,
                    "Food",  # WRONG: string mixed with VendorItem
                ]
            )

    def test_empty_vendor_inventory_allowed(self):
        """Vendors with empty inventory should be valid (can spawn without items)."""
        vendor_spawn = NPCSpawn(
            name="Empty Vendor",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="Vendor with no stock",
            health=50,
            soak=0,
            skills={},
            is_vendor=True,
            vendor_inventory=[]  # Empty is OK
        )

        assert vendor_spawn.vendor_inventory == []


class TestVendorItemPriceValidation:
    """Test that VendorItem rejects invalid prices."""

    def test_negative_price_drip_rejected(self):
        """Negative prices should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            VendorItem(
                name="Free Money",
                description="Gives you money!",
                price_drip=-50,  # WRONG: negative price
                item_type="consumable"
            )

        error_msg = str(exc_info.value).lower()
        assert "price" in error_msg or "negative" in error_msg

    def test_negative_price_spark_rejected(self):
        """Negative spark prices should be rejected."""
        with pytest.raises(ValidationError):
            VendorItem(
                name="Debt Item",
                description="Costs negative currency",
                price_spark=-10,  # WRONG
                item_type="tool"
            )

    def test_zero_prices_allowed(self):
        """Zero prices (free items) should be valid."""
        free_item = VendorItem(
            name="Free Sample",
            description="Promotional item",
            price_drip=0,
            price_spark=0,
            item_type="consumable"
        )

        assert free_item.cost == {}  # No currency required

    def test_multiple_currency_prices_valid(self):
        """Items can cost multiple currency types."""
        expensive_item = VendorItem(
            name="Luxury Item",
            description="Costs multiple currencies",
            price_drip=10,
            price_spark=2,
            price_grain=5,
            item_type="tool"
        )

        assert expensive_item.cost["drip"] == 10
        assert expensive_item.cost["spark"] == 2
        assert expensive_item.cost["grain"] == 5


class TestVendorItemRequiredFields:
    """Test that VendorItem requires essential fields."""

    def test_missing_name_rejected(self):
        """VendorItem without name should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            VendorItem(
                description="Item with no name",
                price_drip=5,
                item_type="consumable"
            )

        assert "name" in str(exc_info.value).lower()

    def test_missing_description_rejected(self):
        """VendorItem without description should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            VendorItem(
                name="Mystery Item",
                price_drip=5,
                item_type="consumable"
            )

        assert "description" in str(exc_info.value).lower()

    def test_item_type_defaults_to_consumable(self):
        """item_type should default to 'consumable' if not specified."""
        item = VendorItem(
            name="Generic Item",
            description="No type specified",
            price_drip=3
        )

        assert item.item_type == "consumable"


class TestNPCSpawnVendorFields:
    """Test vendor-specific fields on NPCSpawn."""

    def test_is_vendor_defaults_to_false(self):
        """NPCs should not be vendors by default."""
        npc = NPCSpawn(
            name="Regular NPC",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="A regular non-vendor NPC character without merchant functionality",
            health=50,
            soak=0,
            skills={}
        )

        assert npc.is_vendor is False
        assert npc.vendor_inventory == []

    def test_vendor_with_greeting(self):
        """Vendors can have custom greetings."""
        vendor = NPCSpawn(
            name="Chatty Vendor",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="A talkative merchant who enjoys conversation with customers",
            health=50,
            soak=0,
            skills={},
            is_vendor=True,
            vendor_greeting="Welcome, traveler! Browse my wares!",
            vendor_type="human_trader"
        )

        assert vendor.vendor_greeting == "Welcome, traveler! Browse my wares!"
        assert vendor.vendor_type == "human_trader"

    def test_accepts_purchases_defaults_to_false(self):
        """accepts_purchases should default to False."""
        vendor = NPCSpawn(
            name="Window Shopping Vendor",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="Vendor displaying items but not actually selling them to customers",
            health=50,
            soak=0,
            skills={},
            is_vendor=True,
            vendor_inventory=[
                VendorItem(
                    name="Display Item",
                    description="Not for sale",
                    price_drip=999,
                    item_type="prop"
                )
            ]
        )

        assert vendor.accepts_purchases is False


class TestVendorSpawnEdgeCases:
    """Test edge cases in vendor spawning."""

    def test_non_vendor_with_inventory_allowed(self):
        """NPCs can have vendor_inventory even if is_vendor=False (for future use)."""
        npc = NPCSpawn(
            name="NPC with Items",
            faction="neutral",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="Has items but not selling",
            health=50,
            soak=0,
            skills={},
            is_vendor=False,
            vendor_inventory=[
                VendorItem(
                    name="Personal Item",
                    description="Not for sale",
                    price_drip=0,
                    item_type="prop"
                )
            ]
        )

        # Should be valid (maybe NPC will become vendor later)
        assert npc.is_vendor is False
        assert len(npc.vendor_inventory) == 1

    def test_vendor_with_only_hollow_priced_items(self):
        """Vendors can sell items priced only in hollow currency."""
        # This test will pass once price_hollow is added
        vendor = NPCSpawn(
            name="Black Market Dealer",
            faction="tempest",
            entity_type="neutral",
            threat_level="potential_threat",
            disposition="wary",
            description="Only accepts illicit currency",
            health=60,
            soak=2,
            skills={"Stealth": 3},
            is_vendor=True,
            vendor_inventory=[
                VendorItem(
                    name="Illegal Scanner",
                    description="Void-tainted device",
                    price_hollow=3,  # Will fail until price_hollow added
                    item_type="tool"
                )
            ]
        )

        assert vendor.vendor_inventory[0].name == "Illegal Scanner"
        # Once price_hollow is added, also check:
        # assert vendor.vendor_inventory[0].cost == {"hollow": 3}
