"""
Unit tests for ItemType enum and food categorization.

Tests that:
1. ItemType enum exists with correct values
2. Food items are properly categorized
3. VendorItem validates item_type
4. Standard vendors have correct item types

Following TDD: These tests should FAIL initially, then PASS after creating
the ItemType enum and categorizing food items.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    VendorItem,
    create_standard_vendors
)


class TestItemTypeEnum:
    """Test ItemType enum (once created)."""

    def test_item_type_enum_exists(self):
        """ItemType enum should exist with standard categories."""
        # This will fail until we create the enum
        from scripts.aeonisk.multiagent.energy_economy import ItemType

        assert hasattr(ItemType, 'CONSUMABLE')
        assert hasattr(ItemType, 'FOOD')
        assert hasattr(ItemType, 'TOOL')
        assert hasattr(ItemType, 'SEED')
        assert hasattr(ItemType, 'OFFERING')
        assert hasattr(ItemType, 'EXCHANGE')
        assert hasattr(ItemType, 'PROP')
        assert hasattr(ItemType, 'EQUIPMENT')

    def test_item_type_enum_values(self):
        """ItemType enum values should be lowercase strings."""
        from scripts.aeonisk.multiagent.energy_economy import ItemType

        assert ItemType.CONSUMABLE.value == "consumable"
        assert ItemType.FOOD.value == "food"
        assert ItemType.PROP.value == "prop"
        assert ItemType.TOOL.value == "tool"


class TestVendorItemTypeField:
    """Test VendorItem item_type field."""

    def test_vendor_item_accepts_string_item_type(self):
        """VendorItem should accept string item_type (backward compatible)."""
        item = VendorItem(
            name="Test Item",
            description="Test description",
            price_drip=5,
            item_type="consumable"  # String should work
        )

        assert item.item_type == "consumable"

    def test_vendor_item_defaults_to_consumable(self):
        """item_type should default to 'consumable' if not specified."""
        item = VendorItem(
            name="Generic Item",
            description="No type specified",
            price_drip=3
        )

        assert item.item_type == "consumable"

    def test_vendor_item_accepts_food_type(self):
        """VendorItem should accept 'food' as item_type."""
        item = VendorItem(
            name="Ration Pack",
            description="Survival rations",
            price_drip=2,
            item_type="food"
        )

        assert item.item_type == "food"

    def test_vendor_item_accepts_prop_type(self):
        """VendorItem should accept 'prop' as item_type."""
        item = VendorItem(
            name="Story Token",
            description="Narrative item with no mechanics",
            price_breath=1,
            item_type="prop"
        )

        assert item.item_type == "prop"

    def test_vendor_item_accepts_tool_type(self):
        """VendorItem should accept 'tool' as item_type."""
        item = VendorItem(
            name="Multitool",
            description="Useful gadget",
            price_drip=10,
            item_type="tool"
        )

        assert item.item_type == "tool"


class TestFoodCategorization:
    """Test that food items in standard vendors are categorized as 'food'."""

    def test_ration_pack_is_food(self):
        """Ration Pack should have item_type='food'."""
        vendors = create_standard_vendors()

        # Find Ration Pack in any vendor
        ration_item = None
        for vendor in vendors:
            for item in vendor.inventory:
                if "Ration Pack" in item.name:
                    ration_item = item
                    break
            if ration_item:
                break

        assert ration_item is not None, "Ration Pack not found in standard vendors"
        assert ration_item.item_type == "food", f"Ration Pack has item_type='{ration_item.item_type}', expected 'food'"

    def test_dripfruit_chews_is_food(self):
        """Dripfruit Chews should have item_type='food'."""
        vendors = create_standard_vendors()

        dripfruit_item = None
        for vendor in vendors:
            for item in vendor.inventory:
                if "Dripfruit Chews" in item.name:
                    dripfruit_item = item
                    break
            if dripfruit_item:
                break

        assert dripfruit_item is not None, "Dripfruit Chews not found"
        assert dripfruit_item.item_type == "food"

    def test_glowpeel_noodles_is_food(self):
        """Glowpeel Noodles should have item_type='food'."""
        vendors = create_standard_vendors()

        noodles_item = None
        for vendor in vendors:
            for item in vendor.inventory:
                if "Glowpeel Noodles" in item.name:
                    noodles_item = item
                    break
            if noodles_item:
                break

        assert noodles_item is not None, "Glowpeel Noodles not found"
        assert noodles_item.item_type == "food"

    def test_all_food_items_categorized(self):
        """All food items should have item_type='food'."""
        vendors = create_standard_vendors()

        # Expected food items (from economy_economy.py lines 694-798)
        expected_food_items = [
            "Dripfruit Chews",
            "Ration Pack",
            "Echo-Crackers",
            "Glowpeel Noodles",
            "Hollow Cone",
            "Ley Pop",
            "Sparksticks",
            "Reviv-Essence Lozenges"
        ]

        found_food_items = {}
        for vendor in vendors:
            for item in vendor.inventory:
                for food_name in expected_food_items:
                    if food_name in item.name:
                        found_food_items[food_name] = item.item_type

        # Check all expected food items were found and categorized correctly
        for food_name in expected_food_items:
            assert food_name in found_food_items, f"{food_name} not found in any vendor"
            assert found_food_items[food_name] == "food", \
                f"{food_name} has item_type='{found_food_items[food_name]}', expected 'food'"


class TestNonFoodCategorization:
    """Test that non-food items are NOT categorized as food."""

    def test_medkit_not_food(self):
        """Medkit should NOT have item_type='food'."""
        vendors = create_standard_vendors()

        medkit_item = None
        for vendor in vendors:
            for item in vendor.inventory:
                if "Med Kit" in item.name or "Medkit" in item.name:
                    medkit_item = item
                    break
            if medkit_item:
                break

        if medkit_item:  # If medkit exists in vendors
            assert medkit_item.item_type != "food", "Medkit should not be categorized as food"

    def test_echo_calibrator_not_food(self):
        """Echo-Calibrator should have item_type='tool', not 'food'."""
        vendors = create_standard_vendors()

        calibrator_item = None
        for vendor in vendors:
            for item in vendor.inventory:
                if "Echo-Calibrator" in item.name:
                    calibrator_item = item
                    break
            if calibrator_item:
                break

        if calibrator_item:
            assert calibrator_item.item_type == "tool", \
                f"Echo-Calibrator should be 'tool', not '{calibrator_item.item_type}'"

    def test_offerings_have_offering_type(self):
        """Ritual offerings should have item_type='offering'."""
        vendors = create_standard_vendors()

        offering_items = []
        for vendor in vendors:
            for item in vendor.inventory:
                if "offering" in item.name.lower() or "incense" in item.name.lower():
                    offering_items.append(item)

        # Should have at least some offering items
        assert len(offering_items) > 0, "No offering items found"

        for item in offering_items:
            assert item.item_type == "offering", \
                f"{item.name} should have item_type='offering', not '{item.item_type}'"


class TestItemTypeUsageInConsumption:
    """Test that item_type can be used to validate consumption."""

    def test_can_identify_food_items(self):
        """Should be able to filter items by item_type='food'."""
        vendors = create_standard_vendors()

        all_food_items = []
        for vendor in vendors:
            food_items = [item for item in vendor.inventory if item.item_type == "food"]
            all_food_items.extend(food_items)

        # Should find at least 8 food items
        assert len(all_food_items) >= 8, f"Expected at least 8 food items, found {len(all_food_items)}"

    def test_can_exclude_non_food_items(self):
        """Should be able to filter out non-food items."""
        vendors = create_standard_vendors()

        all_items = []
        for vendor in vendors:
            all_items.extend(vendor.inventory)

        non_food_items = [item for item in all_items if item.item_type != "food"]

        # Should have many non-food items
        assert len(non_food_items) > 0, "Should have non-food items in vendors"

        # None of these should be named like food
        food_keywords = ["ration", "chew", "noodle", "cracker", "cone", "pop", "lozenge"]
        for item in non_food_items:
            item_name_lower = item.name.lower()
            has_food_keyword = any(keyword in item_name_lower for keyword in food_keywords)
            assert not has_food_keyword, \
                f"Non-food item '{item.name}' has food keyword but item_type='{item.item_type}'"
