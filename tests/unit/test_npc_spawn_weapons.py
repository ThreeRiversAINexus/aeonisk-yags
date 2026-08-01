"""
Unit tests for NPCSpawn weapons field and weapon passthrough to NPCAgent.
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.schemas.story_events import NPCSpawn
from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY


class TestNPCSpawnWeaponsSchema:
    """NPCSpawn schema accepts optional weapons list."""

    def test_npc_spawn_with_weapons(self):
        """NPCSpawn should accept a weapons field."""
        spawn = NPCSpawn(
            name="Armed Freeborn",
            faction="Freeborn",
            entity_type="neutral",
            threat_level="armed_neutral",
            disposition="neutral",
            description="An armed neutral character standing guard at the perimeter.",
            health=20,
            soak=6,
            skills={"Guns": 3, "Melee": 2},
            weapons=["pistol", "combat_knife"]
        )
        assert spawn.weapons == ["pistol", "combat_knife"]

    def test_npc_spawn_without_weapons_defaults_empty(self):
        """NPCSpawn without weapons field should default to empty list."""
        spawn = NPCSpawn(
            name="Unarmed Civilian",
            faction="Freeborn",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="friendly",
            description="A harmless civilian going about their business in the area.",
            health=15,
            soak=0,
        )
        assert spawn.weapons == []

    def test_npc_spawn_weapons_serialization(self):
        """NPCSpawn weapons should serialize/deserialize correctly."""
        spawn = NPCSpawn(
            name="Guard",
            faction="Freeborn",
            entity_type="neutral",
            threat_level="armed_neutral",
            disposition="neutral",
            description="A guard with standard equipment standing at their post.",
            health=20,
            soak=6,
            weapons=["pistol", "baton"]
        )
        dump = spawn.model_dump()
        assert dump['weapons'] == ["pistol", "baton"]

        # Reconstruct from dict
        spawn2 = NPCSpawn(**dump)
        assert spawn2.weapons == ["pistol", "baton"]


class TestNPCSpawnWeaponPassthrough:
    """Weapons from NPCSpawn are assigned to NPCAgent during _process_npc_spawn."""

    def test_weapons_from_spawn_assigned_to_agent(self):
        """NPCSpawn with weapons should result in NPCAgent with those weapons."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        spawn = NPCSpawn(
            name="Armed Guard",
            faction="Freeborn",
            entity_type="neutral",
            threat_level="armed_neutral",
            disposition="neutral",
            description="An armed guard with pistol and combat knife at their station.",
            health=20,
            soak=6,
            skills={"Guns": 3, "Melee": 2},
            weapons=["pistol", "combat_knife"]
        )

        # Create a minimal DM for _process_npc_spawn
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = MagicMock()
        dm.shared_state.get_target_id_mapper.return_value = MagicMock()
        dm.agent_prompt_logger = None
        dm.llm_provider = None
        dm.names_client = None

        npc = dm._process_npc_spawn(spawn)

        # Should have the specified weapons, not auto-generated ones
        weapon_names = [w.name for w in npc.weapons]
        assert "Pistol" in weapon_names
        assert "Combat Knife" in weapon_names

    def test_empty_weapons_falls_through_to_auto(self):
        """NPCSpawn without weapons should auto-assign based on threat level."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        spawn = NPCSpawn(
            name="Potential Threat",
            faction="Freeborn",
            entity_type="neutral",
            threat_level="armed_neutral",
            disposition="neutral",
            description="A potentially threatening individual lurking near the perimeter.",
            health=20,
            soak=6,
            skills={"Guns": 3, "Melee": 2},
            # No weapons field → auto-assign
        )

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = MagicMock()
        dm.shared_state.get_target_id_mapper.return_value = MagicMock()
        dm.agent_prompt_logger = None
        dm.llm_provider = None
        dm.names_client = None

        npc = dm._process_npc_spawn(spawn)

        # Should have auto-assigned weapons based on skills
        assert len(npc.weapons) > 0


class TestConfigNPCWeaponsPassthrough:
    """Config initial_npcs with weapons field processes correctly."""

    def test_config_weapons_in_npc_spawn(self):
        """NPC config dict with weapons should create NPCSpawn with weapons."""
        npc_config = {
            "name": "Freeborn Militant",
            "faction": "Freeborn",
            "entity_type": "neutral",
            "threat_level": "armed_neutral",
            "disposition": "neutral",
            "description": "A heavily armed Freeborn militant protecting their territory.",
            "health": 25,
            "soak": 8,
            "skills": {"Guns": 4, "Melee": 3},
            "weapons": ["pistol", "combat_knife"]
        }

        spawn = NPCSpawn(**npc_config)
        assert spawn.weapons == ["pistol", "combat_knife"]
        assert spawn.skills == {"Guns": 4, "Melee": 3}
