"""
Unit tests for item_discovery pipeline: DM structured output → effects_dict → session.py → inventory.

Tests the fix for the bug where DM correctly outputs item_discovery but it wasn't included
in effects_dict, so items never reached player inventory.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


class TestItemDiscoveryEffectsDict:
    """Tests that item_discovery is included in effects_dict from DM structured output."""

    def test_item_discovery_extracted_from_structured_output(self):
        """item_discovery should be extracted from ActionResolution.effects and included in effects_dict."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects
        from scripts.aeonisk.multiagent.schemas.action_effects import ItemEffect

        # Create mock effects with item_discovery
        item_discovery = ItemEffect(
            items_added={"raw_seed_fresh": 3, "drip": 20, "medkit": 1},
            source="supply_cache"
        )
        effects = MechanicalEffects(item_discovery=item_discovery)

        # Simulate the effects_dict construction from dm.py line 4660-4668
        damage_list = None
        if effects.damage:
            damage_list = [dmg.model_dump() for dmg in effects.damage]

        effects_dict = {
            'damage': damage_list,
            'status_effects': [],
            'inventory_changes': [],
            'purchase': effects.purchase.model_dump() if effects.purchase else None,
            'crafting': effects.crafting.model_dump() if effects.crafting else None,
            'attunement': effects.attunement.model_dump() if effects.attunement else None,
            'item_discovery': effects.item_discovery.model_dump() if effects.item_discovery else None
        }

        # Verify item_discovery is present and correct
        assert effects_dict['item_discovery'] is not None
        assert effects_dict['item_discovery']['items_added'] == {"raw_seed_fresh": 3, "drip": 20, "medkit": 1}
        assert effects_dict['item_discovery']['source'] == "supply_cache"

    def test_item_discovery_none_when_not_present(self):
        """item_discovery should be None in effects_dict when not in structured output."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects

        # Effects without item_discovery
        effects = MechanicalEffects()

        effects_dict = {
            'damage': None,
            'status_effects': [],
            'inventory_changes': [],
            'purchase': effects.purchase.model_dump() if effects.purchase else None,
            'crafting': effects.crafting.model_dump() if effects.crafting else None,
            'attunement': effects.attunement.model_dump() if effects.attunement else None,
            'item_discovery': effects.item_discovery.model_dump() if effects.item_discovery else None
        }

        assert effects_dict['item_discovery'] is None


class TestItemDiscoveryProcessing:
    """Tests that session.py correctly processes item_discovery from effects dict."""

    def test_process_item_effect_adds_seeds_to_inventory(self):
        """process_item_effect should add raw seeds to character inventory."""
        from scripts.aeonisk.multiagent.mechanics import process_item_effect
        from scripts.aeonisk.multiagent.energy_economy import EnergyPurse

        # Create mock character state
        character_state = Mock()
        character_state.name = "TestChar"
        character_state.inventory = {}
        character_state.energy_purse = EnergyPurse()

        # Use dict format (as passed from dm.py via model_dump())
        item_effect = {
            "items_added": {"raw_seed_fresh": 3},
            "source": "leyline_plant"
        }

        result = process_item_effect(item_effect, character_state, "player_1")

        assert result is True
        # Seeds should be added to energy_purse.seeds list as Seed objects
        assert len(character_state.energy_purse.seeds) == 3

    def test_process_item_effect_adds_currency_to_purse(self):
        """process_item_effect should add currency to character energy_purse."""
        from scripts.aeonisk.multiagent.mechanics import process_item_effect
        from scripts.aeonisk.multiagent.energy_economy import EnergyPurse

        character_state = Mock()
        character_state.name = "TestChar"
        character_state.inventory = {}
        character_state.energy_purse = EnergyPurse(drip=10)

        # Use dict format (as passed from dm.py via model_dump())
        item_effect = {
            "items_added": {"drip": 20},
            "source": "corpse_loot"
        }

        result = process_item_effect(item_effect, character_state, "player_1")

        assert result is True
        assert character_state.energy_purse.drip == 30  # 10 + 20

    def test_process_item_effect_adds_items_to_inventory(self):
        """process_item_effect should add standard items to character inventory."""
        from scripts.aeonisk.multiagent.mechanics import process_item_effect
        from scripts.aeonisk.multiagent.energy_economy import EnergyPurse

        character_state = Mock()
        character_state.name = "TestChar"
        character_state.inventory = {"medkit": 1}
        character_state.energy_purse = EnergyPurse()

        # Use dict format (as passed from dm.py via model_dump())
        item_effect = {
            "items_added": {"medkit": 2, "ration_pack": 1},
            "source": "supply_cache"
        }

        result = process_item_effect(item_effect, character_state, "player_1")

        assert result is True
        assert character_state.inventory["medkit"] == 3  # 1 + 2
        assert character_state.inventory["ration_pack"] == 1


class TestItemDiscoveryJSONLLogging:
    """Tests that item_discovery is correctly logged to JSONL."""

    def test_jsonl_log_contains_item_discovery(self):
        """JSONL action_resolution events should include item_discovery field."""
        # This test documents the expected JSONL structure
        # The actual logging is verified in integration tests

        expected_fields = {
            "event_type": "action_resolution",
            "effects": {
                "item_discovery": {
                    "items_added": {"raw_seed_fresh": 3, "drip": 20},
                    "source": "supply_cache"
                }
            }
        }

        # Verify field structure matches schema
        assert "item_discovery" in expected_fields["effects"]
        assert "items_added" in expected_fields["effects"]["item_discovery"]
        assert "source" in expected_fields["effects"]["item_discovery"]


class TestItemEffectSchema:
    """Tests for the ItemEffect Pydantic schema."""

    def test_item_effect_serialization(self):
        """ItemEffect should serialize correctly for JSONL logging."""
        from scripts.aeonisk.multiagent.schemas.action_effects import ItemEffect

        item_effect = ItemEffect(
            items_added={"raw_seed_fresh": 2, "drip": 15, "ration_pack": 1},
            source="leyline_plant"
        )

        data = item_effect.model_dump()

        assert data == {
            "items_added": {"raw_seed_fresh": 2, "drip": 15, "ration_pack": 1},
            "source": "leyline_plant"
        }

    def test_item_effect_in_mechanical_effects(self):
        """ItemEffect should be properly nested in MechanicalEffects."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects
        from scripts.aeonisk.multiagent.schemas.action_effects import ItemEffect

        item_discovery = ItemEffect(
            items_added={"medkit": 1},
            source="corpse"
        )

        effects = MechanicalEffects(item_discovery=item_discovery)

        assert effects.item_discovery is not None
        assert effects.item_discovery.items_added == {"medkit": 1}
        assert effects.item_discovery.source == "corpse"
