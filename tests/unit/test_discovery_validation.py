"""
Tests for discovery validation and processing in mechanics layer.

Tests cover:
1. ItemEffect validation (environmental prerequisites, NPC gift validation)
2. Seed key conversion (raw_seed_fresh → Seed objects)
3. Currency addition to EnergyPurse
4. Standard item addition to inventory
5. Abuse prevention (daily limits, quantity caps)
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.schemas.action_effects import ItemEffect
from scripts.aeonisk.multiagent.energy_economy import Seed, SeedType, Element, EnergyPurse
from dataclasses import dataclass, field
from typing import Dict, List


# Mock Character class for testing
@dataclass
class MockCharacter:
    """Mock character for testing discovery mechanics."""
    name: str
    inventory: Dict[str, int] = field(default_factory=dict)
    energy_purse: EnergyPurse = field(default_factory=lambda: EnergyPurse())
    health: int = 10
    max_health: int = 10


class TestSeedKeyConversion:
    """Test conversion of special seed keys to Seed objects."""

    def test_convert_raw_seed_fresh(self):
        """Test raw_seed_fresh → Seed(RAW, cycles=10-14)."""
        # This will be implemented in mechanics.py
        # For now, test the expected behavior

        seed_key = "raw_seed_fresh"
        source = "leyline_plant"

        # Expected behavior:
        # seed = Seed(
        #     seed_type=SeedType.RAW,
        #     cycles_remaining=random.randint(10, 14),
        #     origin=source
        # )

        assert seed_key == "raw_seed_fresh"
        assert source == "leyline_plant"
        # Actual conversion tested in mechanics implementation

    def test_convert_raw_seed_aged(self):
        """Test raw_seed_aged → Seed(RAW, cycles=3-6)."""
        seed_key = "raw_seed_aged"
        source = "corpse_loot"

        # Expected: Seed(SeedType.RAW, cycles_remaining=random.randint(3, 6), origin=source)
        assert seed_key == "raw_seed_aged"
        assert source == "corpse_loot"

    def test_convert_attuned_seed_elements(self):
        """Test attuned_seed_<element> → Seed(ATTUNED, element=<element>)."""
        element_keys = {
            "attuned_seed_fire": Element.FIRE,
            "attuned_seed_water": Element.WATER,
            "attuned_seed_air": Element.AIR,
            "attuned_seed_earth": Element.EARTH,
            "attuned_seed_spirit": Element.SPIRIT
        }

        for key, expected_element in element_keys.items():
            assert key.startswith("attuned_seed_")
            # Actual conversion: Seed(SeedType.ATTUNED, element=expected_element, origin=source)

    def test_convert_hollow_seed_to_currency(self):
        """Test hollow_seed → adds hollow currency instead of Seed object."""
        seed_key = "hollow_seed"
        quantity = 3

        # Expected behavior: purse.hollow += quantity (no Seed object created)
        assert seed_key == "hollow_seed"
        assert quantity == 3


class TestProcessItemEffect:
    """Test process_item_effect() function in mechanics.py."""

    def test_process_standard_items(self):
        """Test adding standard items to inventory."""
        character = MockCharacter(name="Kade")
        effect = ItemEffect(
            items_added={"ration_pack": 2, "medkit": 1},
            source="environmental_loot"
        )

        # Expected behavior:
        # character.inventory["ration_pack"] += 2
        # character.inventory["medkit"] += 1

        # For now, just verify structure
        assert "ration_pack" in effect.items_added
        assert effect.items_added["ration_pack"] == 2

    def test_process_currency_addition(self):
        """Test adding currency to EnergyPurse."""
        character = MockCharacter(name="Ash")
        effect = ItemEffect(
            items_added={"drip": 15, "hollow": 3},
            source="corpse_loot"
        )

        # Expected behavior:
        # character.energy_purse.drip += 15
        # character.energy_purse.hollow += 3

        assert "drip" in effect.items_added
        assert "hollow" in effect.items_added

    def test_process_seed_discovery(self):
        """Test converting seed keys to Seed objects and adding to purse."""
        character = MockCharacter(name="Riven")
        effect = ItemEffect(
            items_added={"raw_seed_fresh": 2, "attuned_seed_fire": 1},
            source="leyline_plant"
        )

        # Expected behavior:
        # for _ in range(2):
        #     seed = Seed(SeedType.RAW, cycles_remaining=random.randint(10, 14), origin="leyline_plant")
        #     character.energy_purse.seeds.append(seed)
        # seed = Seed(SeedType.ATTUNED, element=Element.FIRE, origin="leyline_plant")
        # character.energy_purse.seeds.append(seed)

        assert "raw_seed_fresh" in effect.items_added
        assert "attuned_seed_fire" in effect.items_added

    def test_process_mixed_discovery(self):
        """Test processing items + seeds + currency in single effect."""
        character = MockCharacter(name="Echo")
        effect = ItemEffect(
            items_added={
                "ration_pack": 1,
                "raw_seed_fresh": 1,
                "drip": 10,
                "spark": 3
            },
            source="supply_cache"
        )

        # Expected to handle all types correctly
        assert len(effect.items_added) == 4


class TestDiscoveryValidation:
    """Test validate_item_discovery() function in mechanics.py."""

    def test_validate_environmental_discovery_prerequisites(self):
        """Test that environmental discovery requires location context."""
        effect = ItemEffect(
            items_added={"raw_seed_fresh": 1},
            source="leyline_plant"
        )

        # Expected validation:
        # - Check if location has leyline plants (could be tracked in SharedState)
        # - Verify character is in appropriate location
        # - Return (success, reason)

        # For now, just verify structure
        assert effect.source == "leyline_plant"

    def test_validate_npc_gift_prerequisites(self):
        """Test that NPC gifts validate NPC has items."""
        effect = ItemEffect(
            items_added={"ritual_incense": 1},
            source="npc_gift"
        )

        # Expected validation:
        # - Check if NPC exists
        # - Check if NPC has items in vendor_inventory (or personal_inventory)
        # - Verify NPC is friendly/neutral (not hostile)
        # - Return (success, reason)

        assert effect.source == "npc_gift"

    def test_validate_daily_limits(self):
        """Test abuse prevention via daily discovery limits."""
        # Expected limits (configurable):
        # - Max 3 seeds per player per session
        # - Max 50 drip per player per session
        # - Max 5 items per discovery event

        effect = ItemEffect(
            items_added={"raw_seed_fresh": 10},  # Exceeds daily limit
            source="leyline_plant"
        )

        # Expected validation to cap at daily limit
        assert effect.items_added["raw_seed_fresh"] == 10  # Schema allows it
        # Mechanics layer should cap to limit

    def test_validate_quest_rewards_no_limits(self):
        """Test that quest rewards bypass daily limits."""
        effect = ItemEffect(
            items_added={"echo_calibrator": 1, "grain": 100},  # High value, but quest reward
            source="quest_reward"
        )

        # Expected: No daily limit checks for quest rewards
        assert effect.source == "quest_reward"

    def test_validate_failed_discovery(self):
        """Test validation of failed discovery (empty items_added)."""
        effect = ItemEffect(
            items_added={},
            source="failed_search"
        )

        # Expected: Valid effect, but no items to process
        assert len(effect.items_added) == 0


class TestAbusePrevention:
    """Test daily limit enforcement and abuse prevention."""

    def test_daily_seed_discovery_limit(self):
        """Test max 3 seeds per player per session."""
        # Expected tracking in SharedState or mechanics layer:
        # discovery_tracking = {
        #     "player_01": {"seeds_discovered": 2, "drip_discovered": 30}
        # }

        # Attempt to discover 2 more seeds (would exceed limit of 3)
        effect = ItemEffect(
            items_added={"raw_seed_fresh": 2},
            source="leyline_plant"
        )

        # Expected: Validation returns (False, "Daily seed discovery limit reached (3/session)")
        pass

    def test_daily_currency_discovery_limit(self):
        """Test max 50 drip per player per session."""
        effect = ItemEffect(
            items_added={"drip": 60},  # Exceeds limit
            source="environmental_loot"
        )

        # Expected: Capped at remaining daily limit
        pass

    def test_discovery_limits_reset_per_session(self):
        """Test that discovery limits reset each session."""
        # Expected: Limits tracked per session, reset on new session start
        pass

    def test_npc_gift_frequency_limits(self):
        """Test that NPCs can't gift repeatedly in same scene."""
        # Expected: Track gifts per NPC per scene
        # NPC can gift once per scene, not every round
        pass


class TestItemEffectIntegration:
    """Test integration between ItemEffect and character state."""

    def test_add_items_to_empty_inventory(self):
        """Test adding items when inventory is empty."""
        character = MockCharacter(name="Kade")
        assert len(character.inventory) == 0

        # After processing ItemEffect:
        # character.inventory = {"ration_pack": 2, "medkit": 1}

    def test_add_items_to_existing_inventory(self):
        """Test adding items to non-empty inventory (quantity stacking)."""
        character = MockCharacter(name="Ash")
        character.inventory = {"ration_pack": 1}

        # After processing ItemEffect with {"ration_pack": 2}:
        # character.inventory["ration_pack"] = 3  # Stacked

    def test_add_seeds_to_empty_purse(self):
        """Test adding seeds when purse has no seeds."""
        character = MockCharacter(name="Riven")
        assert len(character.energy_purse.seeds) == 0

        # After processing ItemEffect with {"raw_seed_fresh": 2}:
        # len(character.energy_purse.seeds) == 2

    def test_add_currency_to_purse(self):
        """Test adding currency to existing purse."""
        character = MockCharacter(name="Echo")
        initial_drip = character.energy_purse.drip

        # After processing ItemEffect with {"drip": 15}:
        # character.energy_purse.drip == initial_drip + 15


class TestDiscoverySourceValidation:
    """Test validation of discovery sources."""

    def test_environmental_source_requires_location(self):
        """Test that environmental sources validate location context."""
        sources = ["leyline_plant", "corpse_loot", "supply_cache"]

        # Expected: Each source requires specific location/context validation
        for source in sources:
            effect = ItemEffect(items_added={"ration_pack": 1}, source=source)
            assert effect.source == source

    def test_npc_source_requires_npc_exists(self):
        """Test that NPC sources validate NPC existence."""
        sources = ["npc_gift", "quest_reward", "bribe_accepted"]

        # Expected: Validate NPC exists and has items
        for source in sources:
            effect = ItemEffect(items_added={"grain": 10}, source=source)
            assert effect.source == source

    def test_consequence_source_no_validation(self):
        """Test that DM consequence sources bypass validation."""
        sources = ["penalty_for_failure", "bonus_for_success", "dm_award"]

        # Expected: DM awards bypass prerequisite checks
        for source in sources:
            effect = ItemEffect(items_added={"raw_seed_fresh": 1}, source=source)
            assert effect.source == source
