"""
Tests for NPC faction context and conversion memory.

Phase 3A: NPC prompts include faction relationships.
Phase 3B: Converted NPCs have memory of their conversion.
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient


class TestNPCFactionContext:
    """NPC system prompt includes faction relationship info."""

    def test_npc_prompt_includes_faction_relationships(self):
        npc = NPCAgent(
            agent_id="enemy_guard_01",
            name="ACG Guard",
            faction="ACG",
            entity_type="prisoner",
            disposition="prisoner",
            threat_level="armed_neutral",
            description="A corporate guard",
            health=15, max_health=30, soak=8, void_score=0,
        )
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        # Should include faction relationship info beyond just abbreviation list
        assert "ACG" in prompt
        assert "Astral Commerce Group" in prompt or "faction" in prompt.lower()

    def test_acg_prisoner_sees_nexus_alignment(self):
        npc = NPCAgent(
            agent_id="enemy_guard_02",
            name="ACG Enforcer",
            faction="ACG",
            entity_type="prisoner",
            disposition="prisoner",
            threat_level="armed_neutral",
            description="A corporate enforcer",
            health=10, max_health=30, soak=8, void_score=0,
        )
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        # Should show that ACG is Nexus-aligned
        assert "Nexus" in prompt

    def test_tempest_npc_sees_anti_nexus_stance(self):
        npc = NPCAgent(
            agent_id="enemy_rebel_01",
            name="Tempest Operative",
            faction="Tempest Industries",
            entity_type="neutral",
            disposition="wary",
            threat_level="armed_neutral",
            description="A Tempest operative",
            health=20, max_health=30, soak=8, void_score=0,
        )
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        assert "Tempest" in prompt


class TestNPCConversionMemory:
    """Converted NPCs should have memory of their conversion."""

    def test_prisoner_npc_memory_has_surrender_context(self):
        from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

        enemy = EnemyAgent(
            agent_id="enemy_guard_mem01",
            name="ACG Guard",
            template="grunt",
            attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
            skills={"Brawl": 2, "Guns": 3},
            health=8, max_health=30, soak=8, wounds=2,
            position=Position(ring="Near", side="Enemy"),
            initiative=12,
            morale_behavior="surrender_if_cornered",
        )
        npc = deescalate_enemy_to_npc(enemy, disposition="prisoner", current_round=3)

        # NPC should have memory with conversion context
        assert npc.memory is not None
        goal = npc.memory.current_goal
        assert "prisoner" in goal.lower() or "captive" in goal.lower() or "surrender" in goal.lower()

    def test_friendly_npc_memory_has_cooperation_context(self):
        from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

        enemy = EnemyAgent(
            agent_id="enemy_guard_mem02",
            name="Guard",
            template="grunt",
            attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
            skills={"Brawl": 2, "Guns": 3},
            health=20, max_health=30, soak=8, wounds=0,
            position=Position(ring="Near", side="Enemy"),
            initiative=12,
        )
        npc = deescalate_enemy_to_npc(enemy, disposition="friendly", current_round=2)
        goal = npc.memory.current_goal
        assert "cooperate" in goal.lower() or "friendly" in goal.lower()

    def test_wary_npc_memory_has_cautious_context(self):
        from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

        enemy = EnemyAgent(
            agent_id="enemy_guard_mem03",
            name="Guard",
            template="grunt",
            attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
            skills={"Brawl": 2, "Guns": 3},
            health=20, max_health=30, soak=8, wounds=0,
            position=Position(ring="Near", side="Enemy"),
            initiative=12,
        )
        npc = deescalate_enemy_to_npc(enemy, disposition="wary", current_round=2)
        goal = npc.memory.current_goal
        assert "cautious" in goal.lower() or "wary" in goal.lower() or "stopped fighting" in goal.lower()
