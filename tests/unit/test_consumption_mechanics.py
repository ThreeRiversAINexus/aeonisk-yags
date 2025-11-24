"""
Unit tests for food consumption mechanics.

Tests validate_consumption() and process_consumption_effect() functions.

Following TDD: These tests should FAIL initially, then PASS after implementing
the consumption validation and execution logic in mechanics.py.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import VendorItem


class MockCharacter:
    """Mock character for testing consumption mechanics."""
    def __init__(self, name="Test Player", health=80, max_health=100):
        self.name = name
        self.health = health
        self.max_health = max_health
        self.inventory = {}


class TestConsumptionValidation:
    """Test validate_consumption() pre-validation logic."""

    def test_valid_food_consumption(self):
        """Valid food consumption with item in inventory should pass validation."""
        from scripts.aeonisk.multiagent.mechanics import validate_consumption

        # Create character with food item
        character = MockCharacter(health=80, max_health=100)
        character.inventory["ration_pack"] = 1

        # Create food item
        food_item = VendorItem(
            name="Ration Pack",
            description="Survival rations",
            price_drip=2,
            item_type="food",
            item_id="itm_ration_01",
            inventory_key="ration_pack"
        )

        # Validate consumption
        result = validate_consumption(
            character_state=character,
            item_id="itm_ration_01",
            food_item=food_item
        )

        assert result.is_valid is True
        assert result.failure_reason is None

    def test_reject_non_food_item(self):
        """Attempting to consume non-food item should fail validation."""
        from scripts.aeonisk.multiagent.mechanics import validate_consumption

        character = MockCharacter(health=80, max_health=100)
        character.inventory["medkit"] = 1

        # Medkit is not food
        medkit = VendorItem(
            name="Med Kit",
            description="Medical supplies",
            price_drip=5,
            item_type="consumable",  # NOT "food"
            item_id="itm_medkit_01",
            inventory_key="medkit"
        )

        result = validate_consumption(
            character_state=character,
            item_id="itm_medkit_01",
            food_item=medkit
        )

        assert result.is_valid is False
        assert "not food" in result.failure_reason.lower() or "item_type" in result.failure_reason.lower()

    def test_reject_missing_inventory_item(self):
        """Attempting to consume item not in inventory should fail."""
        from scripts.aeonisk.multiagent.mechanics import validate_consumption

        character = MockCharacter(health=80, max_health=100)
        # Character has NO ration pack in inventory

        food_item = VendorItem(
            name="Ration Pack",
            description="Survival rations",
            price_drip=2,
            item_type="food",
            item_id="itm_ration_01",
            inventory_key="ration_pack"
        )

        result = validate_consumption(
            character_state=character,
            item_id="itm_ration_01",
            food_item=food_item
        )

        assert result.is_valid is False
        assert "inventory" in result.failure_reason.lower() or "don't have" in result.failure_reason.lower()

    def test_reject_consumption_at_full_health(self):
        """Attempting to consume food at full HP should fail (no benefit)."""
        from scripts.aeonisk.multiagent.mechanics import validate_consumption

        character = MockCharacter(health=100, max_health=100)
        character.inventory["ration_pack"] = 1

        food_item = VendorItem(
            name="Ration Pack",
            description="Survival rations",
            price_drip=2,
            item_type="food",
            item_id="itm_ration_01",
            inventory_key="ration_pack"
        )

        result = validate_consumption(
            character_state=character,
            item_id="itm_ration_01",
            food_item=food_item
        )

        assert result.is_valid is False
        assert "full" in result.failure_reason.lower() or "max" in result.failure_reason.lower()

    def test_allow_consumption_near_max_health(self):
        """Consumption at 99/100 HP should be valid (even though only +1 HP benefit)."""
        from scripts.aeonisk.multiagent.mechanics import validate_consumption

        character = MockCharacter(health=99, max_health=100)
        character.inventory["ration_pack"] = 1

        food_item = VendorItem(
            name="Ration Pack",
            description="Survival rations",
            price_drip=2,
            item_type="food",
            item_id="itm_ration_01",
            inventory_key="ration_pack"
        )

        result = validate_consumption(
            character_state=character,
            item_id="itm_ration_01",
            food_item=food_item
        )

        # Should allow (even though only +1 HP benefit due to capping)
        assert result.is_valid is True


class TestConsumptionExecution:
    """Test process_consumption_effect() execution logic."""

    def test_consumption_removes_item_from_inventory(self):
        """Consuming food should remove 1 item from inventory."""
        from scripts.aeonisk.multiagent.mechanics import process_consumption_effect
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        character = MockCharacter(health=80, max_health=100)
        character.inventory["ration_pack"] = 2  # Start with 2

        consumption_effect = ConsumptionEffect(
            item_id="itm_ration_01",
            inventory_key="ration_pack",
            healing=2
        )

        process_consumption_effect(
            consumption_effect=consumption_effect,
            character_state=character
        )

        # Should have 1 left
        assert character.inventory["ration_pack"] == 1

    def test_consumption_heals_plus_two_hp(self):
        """Consuming food should heal +2 HP."""
        from scripts.aeonisk.multiagent.mechanics import process_consumption_effect
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        character = MockCharacter(health=80, max_health=100)
        character.inventory["ration_pack"] = 1

        consumption_effect = ConsumptionEffect(
            item_id="itm_ration_01",
            inventory_key="ration_pack",
            healing=2
        )

        process_consumption_effect(
            consumption_effect=consumption_effect,
            character_state=character
        )

        # Should be 82 HP
        assert character.health == 82

    def test_consumption_caps_at_max_health(self):
        """Healing from food consumption should cap at max_health."""
        from scripts.aeonisk.multiagent.mechanics import process_consumption_effect
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        character = MockCharacter(health=99, max_health=100)
        character.inventory["ration_pack"] = 1

        consumption_effect = ConsumptionEffect(
            item_id="itm_ration_01",
            inventory_key="ration_pack",
            healing=2  # Would heal to 101, but should cap at 100
        )

        process_consumption_effect(
            consumption_effect=consumption_effect,
            character_state=character
        )

        # Should cap at 100
        assert character.health == 100

    def test_consumption_with_zero_quantity_returns_false(self):
        """Attempting to consume when quantity is 0 should return False."""
        from scripts.aeonisk.multiagent.mechanics import process_consumption_effect
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        character = MockCharacter(health=80, max_health=100)
        character.inventory["ration_pack"] = 0  # None left!

        consumption_effect = ConsumptionEffect(
            item_id="itm_ration_01",
            inventory_key="ration_pack",
            healing=2
        )

        # Should return False (graceful failure)
        result = process_consumption_effect(
            consumption_effect=consumption_effect,
            character_state=character
        )

        assert result is False


class TestConsumptionEffectSchema:
    """Test ConsumptionEffect schema."""

    def test_consumption_effect_schema_exists(self):
        """ConsumptionEffect schema should exist."""
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        effect = ConsumptionEffect(
            item_id="itm_food_01",
            inventory_key="food_item",
            healing=2
        )

        assert effect.item_id == "itm_food_01"
        assert effect.inventory_key == "food_item"
        assert effect.healing == 2

    def test_consumption_effect_requires_item_id(self):
        """ConsumptionEffect should require item_id."""
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ConsumptionEffect(
                inventory_key="food_item",
                healing=2
                # Missing item_id
            )

    def test_consumption_effect_requires_inventory_key(self):
        """ConsumptionEffect should require inventory_key."""
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ConsumptionEffect(
                item_id="itm_food_01",
                healing=2
                # Missing inventory_key
            )

    def test_consumption_effect_healing_defaults_to_two(self):
        """Consumption healing should default to 2 HP."""
        from scripts.aeonisk.multiagent.schemas.action_effects import ConsumptionEffect

        effect = ConsumptionEffect(
            item_id="itm_food_01",
            inventory_key="food_item"
            # healing not specified
        )

        assert effect.healing == 2


class TestConsumptionValidationDataclass:
    """Test ConsumptionValidation dataclass."""

    def test_consumption_validation_exists(self):
        """ConsumptionValidation dataclass should exist."""
        from scripts.aeonisk.multiagent.mechanics import ConsumptionValidation

        validation = ConsumptionValidation(
            is_valid=True,
            failure_reason=None
        )

        assert validation.is_valid is True
        assert validation.failure_reason is None

    def test_consumption_validation_with_failure(self):
        """ConsumptionValidation should support failure state."""
        from scripts.aeonisk.multiagent.mechanics import ConsumptionValidation

        validation = ConsumptionValidation(
            is_valid=False,
            failure_reason="Character doesn't have this item"
        )

        assert validation.is_valid is False
        assert validation.failure_reason == "Character doesn't have this item"
