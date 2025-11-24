"""
Tests for ItemEffect schema and item discovery mechanics.

Tests cover:
1. ItemEffect schema validation (items_added dict, source field)
2. Seed handling (raw_seed_fresh, attuned_seed_fire special keys)
3. Currency addition (breath, grain, drip, spark, hollow)
4. Integration with ActionResolution.effects
"""

import pytest
from scripts.aeonisk.multiagent.schemas.action_effects import ItemEffect
from scripts.aeonisk.multiagent.energy_economy import Seed, SeedType, Element


class TestItemEffectSchema:
    """Test ItemEffect Pydantic model validation."""

    def test_basic_item_discovery(self):
        """Test basic item discovery with standard inventory items."""
        effect = ItemEffect(
            items_added={"ration_pack": 2, "medkit": 1},
            source="environmental_loot"
        )
        assert effect.items_added == {"ration_pack": 2, "medkit": 1}
        assert effect.source == "environmental_loot"

    def test_currency_discovery(self):
        """Test currency discovery (drip, breath, grain, spark, hollow)."""
        effect = ItemEffect(
            items_added={"drip": 15, "hollow": 3},
            source="corpse_loot"
        )
        assert effect.items_added == {"drip": 15, "hollow": 3}
        assert effect.source == "corpse_loot"

    def test_seed_discovery_special_keys(self):
        """Test seed discovery using special keys (raw_seed_fresh, attuned_seed_fire)."""
        effect = ItemEffect(
            items_added={"raw_seed_fresh": 1, "attuned_seed_fire": 1},
            source="leyline_plant"
        )
        assert effect.items_added == {"raw_seed_fresh": 1, "attuned_seed_fire": 1}
        assert effect.source == "leyline_plant"

    def test_mixed_discovery(self):
        """Test discovering multiple item types at once (items + seeds + currency)."""
        effect = ItemEffect(
            items_added={
                "ration_pack": 1,
                "raw_seed_fresh": 2,
                "drip": 10,
                "spark": 3
            },
            source="supply_cache"
        )
        assert len(effect.items_added) == 4
        assert effect.items_added["ration_pack"] == 1
        assert effect.items_added["raw_seed_fresh"] == 2
        assert effect.items_added["drip"] == 10
        assert effect.items_added["spark"] == 3

    def test_empty_items_added_valid(self):
        """Test that empty items_added dict is valid (failed discovery)."""
        effect = ItemEffect(
            items_added={},
            source="failed_search"
        )
        assert effect.items_added == {}

    def test_npc_gift_source(self):
        """Test NPC gifting items via ItemEffect."""
        effect = ItemEffect(
            items_added={"ritual_incense": 1, "raw_seed_aged": 1},
            source="npc_gift"
        )
        assert effect.source == "npc_gift"

    def test_quest_reward_source(self):
        """Test quest reward tracking."""
        effect = ItemEffect(
            items_added={"echo_calibrator": 1, "grain": 50},
            source="quest_reward"
        )
        assert effect.source == "quest_reward"

    def test_negative_quantities_rejected(self):
        """Test that negative quantities are rejected (use inventory_changes for consumption)."""
        with pytest.raises(ValueError):
            ItemEffect(
                items_added={"ration_pack": -1},  # Should be positive
                source="environmental_loot"
            )

    def test_zero_quantity_valid(self):
        """Test that zero quantities are valid (edge case)."""
        effect = ItemEffect(
            items_added={"medkit": 0},
            source="environmental_loot"
        )
        assert effect.items_added["medkit"] == 0

    def test_source_required(self):
        """Test that source field is required."""
        with pytest.raises(ValueError):
            ItemEffect(items_added={"ration_pack": 1})

    def test_items_added_required(self):
        """Test that items_added field is required."""
        with pytest.raises(ValueError):
            ItemEffect(source="environmental_loot")


class TestSeedKeyConversion:
    """Test conversion of special seed keys to Seed objects (mechanics layer)."""

    # These tests will verify the mechanics layer correctly interprets special keys
    # Actual conversion happens in mechanics.py, not in the schema

    def test_raw_seed_fresh_key_format(self):
        """Verify raw_seed_fresh key format is recognized."""
        effect = ItemEffect(
            items_added={"raw_seed_fresh": 1},
            source="leyline_plant"
        )
        assert "raw_seed_fresh" in effect.items_added
        # Mechanics layer should convert this to:
        # Seed(seed_type=SeedType.RAW, cycles_remaining=10-14, origin="leyline_plant")

    def test_raw_seed_aged_key_format(self):
        """Verify raw_seed_aged key format is recognized."""
        effect = ItemEffect(
            items_added={"raw_seed_aged": 2},
            source="corpse_loot"
        )
        assert "raw_seed_aged" in effect.items_added
        # Mechanics layer should convert this to:
        # Seed(seed_type=SeedType.RAW, cycles_remaining=3-6, origin="corpse_loot")

    def test_attuned_seed_element_keys(self):
        """Verify attuned seed element keys are recognized."""
        effect = ItemEffect(
            items_added={
                "attuned_seed_fire": 1,
                "attuned_seed_water": 1,
                "attuned_seed_air": 1,
                "attuned_seed_earth": 1,
                "attuned_seed_spirit": 1
            },
            source="npc_gift"
        )
        assert len(effect.items_added) == 5
        # Mechanics layer should convert these to:
        # Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE, origin="npc_gift")
        # etc.

    def test_hollow_seed_key(self):
        """Verify hollow seed key is recognized."""
        effect = ItemEffect(
            items_added={"hollow_seed": 3},
            source="illicit_trade"
        )
        assert "hollow_seed" in effect.items_added
        # Mechanics layer should add 3 hollow currency instead of seeds


class TestItemEffectIntegrationWithActionResolution:
    """Test ItemEffect integration into ActionResolution.effects."""

    def test_item_discovery_in_mechanical_effects(self):
        """Test that ItemEffect can be included in MechanicalEffects."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects

        effects = MechanicalEffects(
            item_discovery=ItemEffect(
                items_added={"ration_pack": 2, "raw_seed_fresh": 1},
                source="environmental_loot"
            )
        )

        assert effects.item_discovery is not None
        assert effects.item_discovery.items_added["ration_pack"] == 2
        assert effects.item_discovery.source == "environmental_loot"

    def test_item_discovery_optional_in_effects(self):
        """Test that item_discovery is optional in MechanicalEffects."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects

        effects = MechanicalEffects()
        assert effects.item_discovery is None

    def test_full_action_resolution_with_discovery(self):
        """Test full ActionResolution with ItemEffect."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import (
            ActionResolution,
            MechanicalEffects,
        )
        from scripts.aeonisk.multiagent.schemas.shared_types import (
            SuccessTier,
            SoulcreditChange
        )

        resolution = ActionResolution(
            narration="You search the leyline-corrupted plant, carefully examining the twisted vines wrapped around the ancient pillars. Your gloved hands part the glowing foliage, revealing two Fresh Raw Seeds nestled within bio-luminescent pods. The organic material pulses with faint void resonance, but the Seeds themselves appear stable and fresh, their surfaces unmarred by corruption. You carefully extract them and secure them in your pack.",
            success_tier=SuccessTier.GOOD,
            margin=5,
            effects=MechanicalEffects(
                soulcredit_changes=[
                    SoulcreditChange(character_name="Kade", amount=0, reason="neutral discovery")
                ],
                item_discovery=ItemEffect(
                    items_added={"raw_seed_fresh": 2},
                    source="leyline_plant"
                )
            )
        )

        assert resolution.effects.item_discovery is not None
        assert resolution.effects.item_discovery.items_added["raw_seed_fresh"] == 2


class TestDiscoverySourceTypes:
    """Test different discovery source categorizations."""

    def test_environmental_sources(self):
        """Test environmental discovery sources."""
        sources = [
            "leyline_plant",
            "corpse_loot",
            "supply_cache",
            "environmental_search",
            "container_opened"
        ]

        for source in sources:
            effect = ItemEffect(
                items_added={"ration_pack": 1},
                source=source
            )
            assert effect.source == source

    def test_npc_interaction_sources(self):
        """Test NPC interaction sources."""
        sources = [
            "npc_gift",
            "quest_reward",
            "bribe_accepted",
            "trade_bonus"
        ]

        for source in sources:
            effect = ItemEffect(
                items_added={"grain": 10},
                source=source
            )
            assert effect.source == source

    def test_consequence_sources(self):
        """Test action consequence sources."""
        sources = [
            "penalty_for_failure",
            "bonus_for_success",
            "random_spawn",
            "dm_award"
        ]

        for source in sources:
            effect = ItemEffect(
                items_added={"raw_seed_fresh": 1},
                source=source
            )
            assert effect.source == source
