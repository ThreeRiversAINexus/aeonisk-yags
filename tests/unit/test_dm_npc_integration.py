"""
Unit tests for DM integration with NPC system.

Tests RoundSynthesis handling of NPC spawns, de-escalations, and escalations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.schemas.story_events import (
    RoundSynthesis,
    NPCSpawn,
    Deescalation,
    Escalation,
)
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.shared_state import SharedState


def create_mock_shared_state():
    """Create mock SharedState with mechanics engine."""
    shared_state = Mock(spec=SharedState)
    shared_state.npc_agents = []
    shared_state.enemy_agents = []
    shared_state.add_npc = Mock()
    shared_state.remove_enemy = Mock()
    shared_state.get_enemy = Mock()

    # Mock mechanics engine
    mechanics = Mock()
    mechanics.jsonl_logger = Mock()
    shared_state.get_mechanics_engine = Mock(return_value=mechanics)

    return shared_state


def test_round_synthesis_supports_npc_spawns():
    """RoundSynthesis schema accepts npc_spawns field."""
    synthesis = RoundSynthesis(
        narration="A guide emerges from the shadows, weathered and cautious. She introduces herself as a Freeborn navigator willing to assist your group.",
        npc_spawns=[
            NPCSpawn(
                name="Freeborn Guide",
                faction="Freeborn",
                entity_type="neutral",
                threat_level="non_combatant",
                disposition="neutral",
                description="Weathered navigator with void-stained fingers",
                health=20,
                soak=2
            )
        ],
        enemy_spawns=[],
        enemy_removals=[]
    )

    assert len(synthesis.npc_spawns) == 1
    assert synthesis.npc_spawns[0].name == "Freeborn Guide"


def test_round_synthesis_supports_deescalations():
    """RoundSynthesis schema accepts deescalations field."""
    synthesis = RoundSynthesis(
        narration="The raider lowers his weapon hesitantly. Your words about shared Freeborn kinship strike a chord. He agrees to a temporary ceasefire, watching you warily.",
        npc_spawns=[],
        deescalations=[
            Deescalation(
                enemy_id="enemy_raider_1",
                resulting_entity_type="neutral",
                resulting_disposition="wary",
                reason="Convinced via shared Freeborn heritage, agrees to temporary truce"
            )
        ],
        enemy_spawns=[],
        enemy_removals=[]
    )

    assert len(synthesis.deescalations) == 1
    assert synthesis.deescalations[0].enemy_id == "enemy_raider_1"


def test_round_synthesis_supports_escalations():
    """RoundSynthesis schema accepts escalations field."""
    synthesis = RoundSynthesis(
        narration="The civilian panics at the sudden violence, eyes wide with terror. In desperation, she grabs a fallen weapon and aims it at your group with shaking hands.",
        npc_spawns=[],
        escalations=[
            Escalation(
                npc_id="enemy_civilian_1",
                reason="Attacked by player, now defending self in desperation",
                template="desperate_fighter"
            )
        ],
        enemy_spawns=[],
        enemy_removals=[]
    )

    assert len(synthesis.escalations) == 1
    assert synthesis.escalations[0].npc_id == "enemy_civilian_1"


def test_process_npc_spawn_creates_agent():
    """DM processing NPC spawn creates NPCAgent and registers it."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    npc_spawn = NPCSpawn(
        name="Test Guide",
        faction="Freeborn",
        entity_type="neutral",
        threat_level="non_combatant",
        disposition="friendly",
        description="Test description for validation",
        health=20,
        soak=0,
        skills={"perception": 5}
    )

    # Process spawn (this will be implemented in dm.py)
    npc = dm._process_npc_spawn(npc_spawn)

    assert npc.name == "Test Guide"
    assert npc.faction == "Freeborn"
    assert npc.entity_type == "neutral"
    assert npc.disposition == "friendly"
    assert npc.health == 20
    assert npc.skills["perception"] == 5


def test_process_deescalation_converts_enemy():
    """DM processing de-escalation converts enemy to NPC."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    # Create mock enemy
    enemy = EnemyAgent(
        agent_id="enemy_raider_1",
        name="Raider",
        health=25,
        max_health=30,
        soak=5,
        void_score=3,
        position="close",
        tactics={"aggression": "medium"},
        template="raider"
    )

    dm.shared_state.get_enemy = Mock(return_value=enemy)

    deescalation = Deescalation(
        enemy_id="enemy_raider_1",
        resulting_entity_type="neutral",
        resulting_disposition="wary",
        reason="Convinced via intimidation, agrees to stand down temporarily"
    )

    # Process de-escalation (this will be implemented in dm.py)
    npc = dm._process_deescalation(deescalation, current_round=3)

    assert npc.agent_id == "enemy_raider_1"  # Stable ID preserved
    assert npc.name == "Raider"
    assert npc.health == 25  # State preserved
    assert npc.entity_type == "neutral"
    assert npc.disposition == "wary"
    assert npc.converted_from_enemy is True


def test_process_escalation_converts_npc():
    """DM processing escalation converts NPC to enemy."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    # Create mock NPC
    npc = NPCAgent(
        agent_id="enemy_guide_1",
        name="Guide",
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Guide NPC",
        health=20,
        max_health=20,
        soak=0,
        void_score=2,
        skills={}
    )

    dm.shared_state.get_npc = Mock(return_value=npc)

    escalation = Escalation(
        npc_id="enemy_guide_1",
        reason="Attacked by player, defending self in panic and fear",
        template="desperate_fighter"
    )

    # Process escalation (this will be implemented in dm.py)
    enemy = dm._process_escalation(escalation, current_round=5)

    assert enemy.agent_id == "enemy_guide_1"  # Stable ID preserved
    assert enemy.name == "Guide"
    assert enemy.health == 20  # State preserved
    # Enemy should be added back to enemy pool


def test_deescalation_removes_from_enemy_pool():
    """De-escalation removes agent from enemy pool."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    enemy = EnemyAgent(
        agent_id="enemy_test_1",
        name="Test Enemy",
        health=20,
        max_health=20,
        soak=0,
        void_score=0,
        position="close",
        tactics={},
        template="test"
    )

    dm.shared_state.get_enemy = Mock(return_value=enemy)

    deescalation = Deescalation(
        enemy_id="enemy_test_1",
        resulting_entity_type="prisoner",
        resulting_disposition="prisoner",
        reason="Subdued via stun damage, now restrained and disarmed"
    )

    dm._process_deescalation(deescalation, current_round=2)

    # Verify enemy removed from pool
    dm.shared_state.remove_enemy.assert_called_once()


def test_escalation_removes_from_npc_pool():
    """Escalation removes agent from NPC pool."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    npc = NPCAgent(
        agent_id="enemy_civilian_1",
        name="Civilian",
        faction="Unknown",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Civilian NPC",
        health=15,
        max_health=15,
        soak=0,
        void_score=0,
        skills={}
    )

    dm.shared_state.get_npc = Mock(return_value=npc)
    dm.shared_state.remove_npc = Mock()

    escalation = Escalation(
        npc_id="enemy_civilian_1",
        reason="Player attacked unprovoked, civilian defends self desperately",
        template="desperate_fighter"
    )

    dm._process_escalation(escalation, current_round=3)

    # Verify NPC removed from pool
    dm.shared_state.remove_npc.assert_called_once_with("enemy_civilian_1")


def test_multiple_conversions_same_round():
    """DM can process multiple NPC events in same round."""
    synthesis = RoundSynthesis(
        narration="Chaos erupts as allegiances shift rapidly in the firefight. A medic appears to help the wounded. The guard surrenders. The civilian, cornered and desperate, turns hostile.",
        npc_spawns=[
            NPCSpawn(
                name="Medic",
                faction="Freeborn",
                entity_type="ally",
                threat_level="non_combatant",
                disposition="friendly",
                description="Field medic offering assistance to wounded",
                health=15,
                soak=0
            )
        ],
        deescalations=[
            Deescalation(
                enemy_id="enemy_guard_1",
                resulting_entity_type="neutral",
                resulting_disposition="neutral",
                reason="Convinced to stand down via negotiation and bribery"
            )
        ],
        escalations=[
            Escalation(
                npc_id="enemy_civilian_1",
                reason="Attacked by player, forced to defend self violently",
                template="desperate_fighter"
            )
        ],
        enemy_spawns=[],
        enemy_removals=[]
    )

    # Should accept all three event types simultaneously
    assert len(synthesis.npc_spawns) == 1
    assert len(synthesis.deescalations) == 1
    assert len(synthesis.escalations) == 1
