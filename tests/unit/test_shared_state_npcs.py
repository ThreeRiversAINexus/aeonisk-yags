"""
Unit tests for NPC tracking in SharedState.

Tests that SharedState can manage NPC agents alongside players and enemies.
"""

import pytest
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.npc_agent import NPCAgent


def create_test_npc(agent_id="enemy_guide_1", name="Guide"):
    """Create minimal test NPC."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Test NPC",
        health=20,
        max_health=20,
        soak=0,
        void_score=2,
        skills={}
    )


def test_shared_state_tracks_npcs():
    """SharedState maintains NPC pool."""
    state = SharedState()
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")

    state.add_npc(npc)

    assert len(state.npc_agents) == 1
    assert state.npc_agents[0].name == "Guide"


def test_shared_state_add_multiple_npcs():
    """SharedState can track multiple NPCs."""
    state = SharedState()
    npc1 = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    npc2 = create_test_npc(agent_id="enemy_medic_1", name="Medic")

    state.add_npc(npc1)
    state.add_npc(npc2)

    assert len(state.npc_agents) == 2
    assert state.npc_agents[0].name == "Guide"
    assert state.npc_agents[1].name == "Medic"


def test_shared_state_get_npc():
    """SharedState can retrieve NPCs by agent_id."""
    state = SharedState()
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    state.add_npc(npc)

    retrieved = state.get_npc("enemy_guide_1")

    assert retrieved is not None
    assert retrieved.agent_id == "enemy_guide_1"
    assert retrieved.name == "Guide"


def test_shared_state_get_npc_not_found():
    """SharedState returns None for missing NPC."""
    state = SharedState()

    retrieved = state.get_npc("enemy_nonexistent_1")

    assert retrieved is None


def test_shared_state_remove_npc():
    """SharedState can remove NPCs."""
    state = SharedState()
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    state.add_npc(npc)

    assert len(state.npc_agents) == 1

    state.remove_npc("enemy_guide_1")

    assert len(state.npc_agents) == 0


def test_shared_state_remove_npc_by_object():
    """SharedState can remove NPCs by object reference."""
    state = SharedState()
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    state.add_npc(npc)

    assert len(state.npc_agents) == 1

    state.remove_npc_object(npc)

    assert len(state.npc_agents) == 0


def test_shared_state_get_all_agents():
    """SharedState can return all agents (players, enemies, NPCs)."""
    state = SharedState()

    # Add NPC
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    state.add_npc(npc)

    # Get all agents
    all_agents = state.get_all_agents()

    # Should include NPCs
    assert any(agent.agent_id == "enemy_guide_1" for agent in all_agents)


def test_shared_state_get_agent_by_id_cross_pool():
    """SharedState can find agents across pools (player/enemy/npc)."""
    state = SharedState()

    # Add NPC
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    state.add_npc(npc)

    # Get by ID (should search all pools)
    retrieved = state.get_agent_by_id("enemy_guide_1")

    assert retrieved is not None
    assert retrieved.agent_id == "enemy_guide_1"
    assert isinstance(retrieved, NPCAgent)


def test_shared_state_get_active_npcs():
    """SharedState can filter active NPCs."""
    state = SharedState()

    npc1 = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    npc1.is_active = True

    npc2 = create_test_npc(agent_id="enemy_medic_1", name="Medic")
    npc2.is_active = False

    state.add_npc(npc1)
    state.add_npc(npc2)

    active_npcs = state.get_active_npcs()

    assert len(active_npcs) == 1
    assert active_npcs[0].agent_id == "enemy_guide_1"


def test_shared_state_convert_enemy_to_npc():
    """SharedState can swap enemy to NPC pool during conversion."""
    from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc

    state = SharedState()

    # Create a mock enemy (simplified)
    from dataclasses import dataclass
    @dataclass
    class MockEnemy:
        agent_id: str = "enemy_raider_1"
        name: str = "Raider"
        faction: str = "Freeborn"
        health: int = 30
        max_health: int = 30
        soak: int = 5
        void_score: int = 4
        skills: dict = None
        stuns: int = 0
        wounds: int = 0
        conditions: list = None
        template_name: str = "freeborn_pirate"

        def __post_init__(self):
            if self.skills is None:
                self.skills = {"combat": 5}
            if self.conditions is None:
                self.conditions = []

    enemy = MockEnemy()

    # Convert
    npc = deescalate_enemy_to_npc(enemy, disposition="prisoner")

    # Add to state
    state.add_npc(npc)

    # Verify
    assert len(state.npc_agents) == 1
    assert state.npc_agents[0].agent_id == "enemy_raider_1"  # ✅ STABLE ID
    assert state.npc_agents[0].entity_type == "prisoner"


def test_shared_state_npc_count():
    """SharedState tracks NPC count."""
    state = SharedState()

    assert state.get_npc_count() == 0

    state.add_npc(create_test_npc(agent_id="enemy_guide_1"))
    assert state.get_npc_count() == 1

    state.add_npc(create_test_npc(agent_id="enemy_medic_1"))
    assert state.get_npc_count() == 2

    state.remove_npc("enemy_guide_1")
    assert state.get_npc_count() == 1
