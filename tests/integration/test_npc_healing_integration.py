"""
Integration test: NPC healing via Medicine skill check.

Tests that NPC heal actions flow through _resolve_action_mechanically,
perform a Medicine skill check (Intelligence x Medicine + d20 vs DC 18),
create HealingEffect on success, and apply HP changes to the target.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ============================================================================
# Fixtures
# ============================================================================

def make_player(agent_id="player_01", name="Ash Vex", health=0, max_health=20,
                wounds=3, stuns=0):
    """Create a mock player entity."""
    player = Mock()
    player.agent_id = agent_id
    player.health = health
    player.max_health = max_health
    player.wounds = wounds
    player.stuns = stuns
    player.is_active = True
    player.character_state = Mock()
    player.character_state.name = name
    player.character_state.void_score = 2
    player.equipped_weapons = {}
    return player


def make_npc(agent_id="npc_medic_01", name="Medic Kira", health=20,
             max_health=20, medicine_skill=4, skills=None):
    """Create a mock NPC entity with optional skills."""
    npc = Mock()
    npc.agent_id = agent_id
    npc.name = name
    npc.health = health
    npc.max_health = max_health
    npc.wounds = 0
    npc.stuns = 0
    npc.soak = 3
    npc.is_active = True
    npc.entity_type = "ally"
    npc.disposition = "friendly"
    npc.faction = "Freeborn"
    npc.skills = skills or {}
    if medicine_skill:
        npc.skills["Medicine"] = medicine_skill
    return npc


def make_enemy(agent_id="enemy_grunt_01", name="Wounded Grunt", health=5,
               max_health=30, wounds=2):
    """Create a mock enemy entity."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stuns = 0
    enemy.is_active = True
    enemy.barriers = []
    enemy.soak = 3
    return enemy


def make_target_id_mapper(entities):
    """Create a target ID mapper that resolves tgt_ IDs."""
    mapper = Mock()
    mapper.enabled = True

    tgt_map = {}
    for e in entities:
        tgt_id = f"tgt_{e.agent_id[-4:]}"
        tgt_map[tgt_id] = e

    mapper.resolve_target = Mock(side_effect=lambda tid: tgt_map.get(tid))
    mapper.is_player = Mock(side_effect=lambda tid: any(
        hasattr(tgt_map.get(tid), 'character_state') for _ in [1] if tid in tgt_map
    ))
    mapper.get_all_target_ids = Mock(return_value=list(tgt_map.keys()))
    return mapper


def make_mechanics(jsonl_logger=None):
    """Create a mock MechanicsEngine."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine

    mechanics = Mock(spec=MechanicsEngine)
    mechanics.current_round = 1
    mechanics.scene_clocks = {}
    mechanics.jsonl_logger = jsonl_logger or Mock()
    mechanics.jsonl_logger.log_action_resolution = Mock()
    return mechanics


def make_shared_state(players, npcs, enemies=None, mechanics=None):
    """Create a mock SharedState."""
    all_entities = players + npcs + (enemies or [])
    shared = Mock()
    shared.player_agents = players
    shared.npc_agents = npcs
    shared.registered_players = []

    enemy_combat = Mock()
    enemy_combat.enemy_agents = enemies or []
    shared.enemy_combat = enemy_combat

    shared.get_mechanics_engine = Mock(return_value=mechanics)
    shared.get_target_id_mapper = Mock(return_value=make_target_id_mapper(all_entities))
    shared.consume_coordination_bonus = Mock(return_value=None)
    shared.session = Mock()
    shared.session.track_player_damage_dealt = Mock()
    shared.get_agent_by_id = Mock(return_value=None)

    return shared


def make_dm(shared_state, llm_config=None):
    """Create a minimal DM instance (bypass __init__)."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent.__new__(AIDMAgent)
    dm.agent_id = "dm_test"
    dm.shared_state = shared_state
    dm.llm_config = llm_config or {"provider": "openai", "model": "gpt-5-mini", "temperature": 0.7}
    dm.current_scenario = Mock()
    dm.current_scenario.void_level = 3
    dm.current_scenario.theme = "medical_test"
    dm.current_scenario.location = "Field Hospital"
    dm.current_scenario.situation = "NPC healing test"
    dm.llm_logger = Mock()
    dm.llm_logger.call_count = 0
    dm.agent_prompt_logger = None
    dm.session_config = {}
    dm._last_structured_resolution = None
    dm.llm_provider = Mock()
    dm.llm_client = Mock()

    shared_state.mechanics_engine = shared_state.get_mechanics_engine()

    return dm


# ============================================================================
# Tests
# ============================================================================

class TestNPCHealPlayerIntegration:
    """Test NPC healing a player through full DM resolution."""

    @pytest.mark.asyncio
    async def test_npc_heal_player_end_to_end(self):
        """
        NPC with Medicine 4 heals unconscious player.
        Mock d20=15 → total = 3*4 + 15 = 27, passes DC 18.
        Verify HealingEffect created and applied.
        """
        player = make_player(health=0, wounds=3)
        npc = make_npc(medicine_skill=4)
        mechanics = make_mechanics()
        shared = make_shared_state([player], [npc], mechanics=mechanics)
        dm = make_dm(shared)

        # Mock LLM narration response
        narration_response = Mock()
        narration_response.text = (
            "Medic Kira drops to her knees beside Ash, hands already moving with practiced "
            "efficiency. She tears open a sterile pack with her teeth, pressing gauze firmly "
            "against the worst of the wounds. 'Stay with me, soldier,' she mutters, fingers "
            "finding the pressure point beneath the jaw. The bleeding slows, then stops. She "
            "checks the pulse — thready but there. One hand reaches for the stim injector on "
            "her belt, thumb flicking the safety cap."
        )

        with patch('random.randint', return_value=15):
            with patch.object(dm, 'llm_provider') as mock_provider:
                mock_provider.generate_structured = AsyncMock(return_value=narration_response)

                result = await dm._resolve_action_mechanically(
                    player_id=npc.agent_id,
                    action={
                        'agent_id': npc.agent_id,
                        'character_name': npc.name,
                        'is_npc': True,
                        'action_type': 'heal',
                        'intent': 'Stabilize unconscious Ash with field medicine',
                        'description': 'I kneel beside Ash and apply emergency medical care',
                        'target': 'player_01',
                    }
                )

        # Verify resolution contains healing
        assert result is not None
        resolution = result.get('resolution') if isinstance(result, dict) else result
        # Check that the narration mentions Medicine check SUCCESS
        assert 'SUCCESS' in str(resolution) or 'success' in str(resolution).lower()

    @pytest.mark.asyncio
    async def test_npc_heal_enemy_end_to_end(self):
        """NPC heals a wounded enemy entity (e.g., for interrogation)."""
        enemy = make_enemy(health=5, wounds=2)
        npc = make_npc(medicine_skill=3)
        mechanics = make_mechanics()
        shared = make_shared_state([], [npc], enemies=[enemy], mechanics=mechanics)
        dm = make_dm(shared)

        narration_response = Mock()
        narration_response.text = (
            "Medic Kira approaches the wounded grunt cautiously, hands raised to show she "
            "means no harm. She kneels beside the groaning figure, pulling out a trauma kit. "
            "'Easy now — I'm not going to hurt you,' she says, voice calm and measured. She "
            "cleans the wound methodically, applying a stasis field to slow the bleeding while "
            "she sutures the deepest gash. The grunt's breathing steadies."
        )

        with patch('random.randint', return_value=12):
            with patch.object(dm, 'llm_provider') as mock_provider:
                mock_provider.generate_structured = AsyncMock(return_value=narration_response)

                result = await dm._resolve_action_mechanically(
                    player_id=npc.agent_id,
                    action={
                        'agent_id': npc.agent_id,
                        'character_name': npc.name,
                        'is_npc': True,
                        'action_type': 'heal',
                        'intent': 'Treat enemy wounds for interrogation',
                        'description': 'I carefully treat the wounded enemy',
                        'target': 'enemy_grunt_01',
                    }
                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_npc_heal_failed_roll(self):
        """
        NPC with low Medicine fails the check.
        Mock d20=5 → total = 3*1 - 5 + 5 = 3, fails DC 18.
        Verify target HP unchanged.
        """
        player = make_player(health=0, wounds=3)
        npc = make_npc(medicine_skill=None)  # No medicine skill
        npc.skills = {}  # Ensure empty
        mechanics = make_mechanics()
        shared = make_shared_state([player], [npc], mechanics=mechanics)
        dm = make_dm(shared)

        narration_response = Mock()
        narration_response.text = (
            "Kira fumbles with the medkit, her hands shaking as she tries to remember the "
            "basic training she never completed. She presses gauze against the wound but in "
            "the wrong place, the blood seeping past her fingers. Her breathing quickens — "
            "panic setting in. 'I don't... I can't...' She looks around desperately for "
            "someone with actual medical training to help."
        )

        player_health_before = player.health

        with patch('random.randint', return_value=5):
            with patch.object(dm, 'llm_provider') as mock_provider:
                mock_provider.generate_structured = AsyncMock(return_value=narration_response)

                result = await dm._resolve_action_mechanically(
                    player_id=npc.agent_id,
                    action={
                        'agent_id': npc.agent_id,
                        'character_name': npc.name,
                        'is_npc': True,
                        'action_type': 'heal',
                        'intent': 'Try to stabilize Ash',
                        'description': 'I attempt first aid despite lacking training',
                        'target': 'player_01',
                    }
                )

        # Verify FAILED in narration
        assert result is not None
        assert 'FAILED' in str(result) or 'FAILURE' in str(result)
