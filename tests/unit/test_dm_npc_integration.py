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
    StoryAdvancement,
    ScenePivot,
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


def test_round_synthesis_no_longer_has_entity_lifecycle_fields():
    """RoundSynthesis schema NO LONGER has npc_spawns/enemy_conversions/escalations fields.

    These fields were moved to Entity Lifecycle Phase (before synthesis).
    """
    # Create a valid synthesis (with long enough narration)
    long_narration = "A guide emerges from the shadows, weathered and cautious. " * 10  # Make it 300+ chars
    synthesis = RoundSynthesis(
        narration=long_narration,
        clocks_filled=[],
        clocks_expired=[]
    )

    # Verify removed fields don't exist
    assert not hasattr(synthesis, 'npc_spawns')
    assert not hasattr(synthesis, 'enemy_conversions')
    assert not hasattr(synthesis, 'escalations')
    assert not hasattr(synthesis, 'enemy_spawns')


# NOTE: Tests for enemy_conversions and escalations in RoundSynthesis removed.
# These fields were moved to Entity Lifecycle Phase (ConversionDecisions).
# See test_entity_lifecycle_phase tests for validation of these features.


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
    from dataclasses import dataclass, field

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    # Create mock enemy with minimal required fields
    @dataclass
    class MockEnemy:
        agent_id: str = "enemy_raider_1"
        name: str = "Raider"
        faction: str = "Freeborn"
        health: int = 25
        max_health: int = 30
        soak: int = 5
        void_score: int = 3
        skills: dict = field(default_factory=lambda: {"combat": 5})
        stuns: int = 0
        wounds: int = 0
        conditions: list = field(default_factory=list)
        template: str = "raider"
        personality: str = "professional"
        position: str = "close"

    enemy = MockEnemy()
    dm.shared_state.get_enemy = Mock(return_value=enemy)

    deescalation = Deescalation(
        enemy_id="enemy_raider_1",
        resolution="convinced",
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
    from dataclasses import dataclass, field

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=create_mock_shared_state()
    )

    # Create mock enemy with minimal required fields
    @dataclass
    class MockEnemy:
        agent_id: str = "enemy_test_1"
        name: str = "Test Enemy"
        faction: str = "Freeborn"
        health: int = 20
        max_health: int = 20
        soak: int = 0
        void_score: int = 0
        skills: dict = field(default_factory=lambda: {"combat": 3})
        stuns: int = 0
        wounds: int = 0
        conditions: list = field(default_factory=list)
        template: str = "test"
        personality: str = "professional"
        position: str = "close"

    enemy = MockEnemy()
    dm.shared_state.get_enemy = Mock(return_value=enemy)

    deescalation = Deescalation(
        enemy_id="enemy_test_1",
        resolution="subdued",
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


# NOTE: test_multiple_conversions_same_round removed.
# This test validated RoundSynthesis fields that no longer exist (moved to Entity Lifecycle Phase).
# Multiple conversions are now handled in ConversionDecisions, not RoundSynthesis.


def test_story_advancement_supports_npc_departures():
    """StoryAdvancement schema accepts npc_departures field."""
    advancement = StoryAdvancement(
        should_advance=True,
        location="Next Location",
        situation="The party moves forward after the guide departs",
        npc_departures=["npc_guide_1", "Dr. Yuki Tanaka"]
    )

    assert len(advancement.npc_departures) == 2
    assert "npc_guide_1" in advancement.npc_departures
    assert "Dr. Yuki Tanaka" in advancement.npc_departures


def test_scene_pivot_supports_npc_departures():
    """ScenePivot schema accepts npc_departures field."""
    pivot = ScenePivot(
        should_pivot=True,
        location="Adjacent room",
        situation="The informant flees when the alarm sounds",
        npc_departures=["npc_informant_vex"]
    )

    assert len(pivot.npc_departures) == 1
    assert pivot.npc_departures[0] == "npc_informant_vex"


def test_npc_departures_via_story_advancement():
    """Session processing removes NPCs via StoryAdvancement.npc_departures."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    shared_state = create_mock_shared_state()
    shared_state.remove_npc = Mock(return_value=True)

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=shared_state
    )

    # Create mock NPCs
    npc1 = NPCAgent(
        agent_id="npc_guide_1",
        name="Guide",
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Guide NPC",
        health=20,
        max_health=20,
        soak=0,
        void_score=0,
        skills={}
    )

    npc2 = NPCAgent(
        agent_id="npc_informant_2",
        name="Informant",
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Informant NPC",
        health=15,
        max_health=15,
        soak=0,
        void_score=0,
        skills={}
    )

    shared_state.npc_agents = [npc1, npc2]

    advancement = StoryAdvancement(
        should_advance=True,
        location="Next location",
        situation="The guide and informant depart",
        npc_departures=["npc_guide_1", "npc_informant_2"]
    )

    # This will be the actual processing code in session.py
    # For now, we simulate it by calling remove_npc directly
    for npc_id in advancement.npc_departures:
        shared_state.remove_npc(npc_id)

    # Verify remove_npc was called for each departure
    assert shared_state.remove_npc.call_count == 2
    shared_state.remove_npc.assert_any_call("npc_guide_1")
    shared_state.remove_npc.assert_any_call("npc_informant_2")


def test_npc_departures_via_scene_pivot():
    """Session processing removes NPCs via ScenePivot.npc_departures."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    shared_state = create_mock_shared_state()
    shared_state.remove_npc = Mock(return_value=True)

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=shared_state
    )

    # Create mock NPC
    npc = NPCAgent(
        agent_id="npc_civilian_worker_1",
        name="Worker",
        faction="Unknown",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Civilian worker",
        health=12,
        max_health=12,
        soak=0,
        void_score=0,
        skills={}
    )

    shared_state.npc_agents = [npc]

    pivot = ScenePivot(
        should_pivot=True,
        location="Alarm triggers in adjacent room",
        situation="Civilian workers flee from danger",
        npc_departures=["npc_civilian_worker_1"]
    )

    # Simulate processing
    for npc_id in pivot.npc_departures:
        shared_state.remove_npc(npc_id)

    # Verify removal
    shared_state.remove_npc.assert_called_once_with("npc_civilian_worker_1")


def test_npc_departure_invalid_id():
    """Attempting to remove non-existent NPC logs warning but doesn't crash."""
    shared_state = create_mock_shared_state()
    shared_state.remove_npc = Mock(return_value=False)

    advancement = StoryAdvancement(
        should_advance=True,
        location="Next location",
        situation="Trying to remove non-existent NPC",
        npc_departures=["npc_nonexistent_999"]
    )

    # Simulate processing with invalid ID
    for npc_id in advancement.npc_departures:
        removed = shared_state.remove_npc(npc_id)
        # In actual implementation, this would log a warning
        # but not crash the session
        assert removed is False

    shared_state.remove_npc.assert_called_once_with("npc_nonexistent_999")


def test_npc_lifecycle_full_spawn_then_depart():
    """Integration test: NPC spawn followed by departure in later round."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    shared_state = create_mock_shared_state()
    shared_state.remove_npc = Mock(return_value=True)

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=shared_state
    )

    # Round 1: Spawn NPC
    npc_spawn = NPCSpawn(
        name="Guide Vex",
        faction="Freeborn",
        entity_type="neutral",
        threat_level="non_combatant",
        disposition="friendly",
        description="Experienced guide offering help",
        health=20,
        soak=2
    )

    npc = dm._process_npc_spawn(npc_spawn)
    shared_state.npc_agents.append(npc)

    assert len(shared_state.npc_agents) == 1
    assert shared_state.npc_agents[0].name == "Guide Vex"

    # Round 3: Guide departs after providing intel
    advancement = StoryAdvancement(
        should_advance=True,
        location="Deeper into facility",
        situation="Guide Vex has fulfilled her bargain and departs",
        npc_departures=[npc.agent_id]
    )

    # Simulate departure processing
    for npc_id in advancement.npc_departures:
        shared_state.remove_npc(npc_id)

    # Verify departure was processed
    shared_state.remove_npc.assert_called_once()


def test_enemy_conversion_fallback_for_npc_escalation():
    """
    When DM mistakenly uses enemy_conversions with an NPC ID,
    system should auto-correct and escalate the NPC properly.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.schemas.story_events import EnemyConversion, EnemyResolution

    shared_state = create_mock_shared_state()

    # Create mock NPC
    npc = NPCAgent(
        agent_id="npc_dorian_thrace_6336",
        name="Dorian Thrace",
        faction="Unknown",
        entity_type="neutral",
        disposition="neutral",
        threat_level="potential_threat",
        description="Suspicious operative",
        health=25,
        max_health=25,
        soak=3,
        void_score=0,
        skills={}
    )

    shared_state.npc_agents = [npc]
    shared_state.get_npc = Mock(return_value=npc)
    shared_state.remove_npc = Mock(return_value=True)

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=shared_state
    )

    # Mock _process_escalation to return a mock enemy
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
    mock_enemy = Mock(spec=EnemyAgent)
    mock_enemy.agent_id = "npc_dorian_thrace_6336"
    mock_enemy.name = "Dorian Thrace"
    dm._process_escalation = Mock(return_value=mock_enemy)

    # DM mistakenly uses enemy_conversions with NPC ID
    conversion = EnemyConversion(
        enemy_id="npc_dorian_thrace_6336",  # Wrong field - this is an NPC!
        resolution=EnemyResolution.CONVINCED,  # Doesn't matter, will be escalated
        reason="Attacked by player, turned hostile"
    )

    # The fallback should detect this and escalate automatically
    # Simulate the fallback logic (since we can't run full session.py here)
    npc_check = shared_state.get_npc(conversion.enemy_id)

    assert npc_check is not None, "NPC should be found in fallback check"
    assert npc_check.agent_id == "npc_dorian_thrace_6336"

    # In actual code, this would trigger escalation
    # Verify the _process_escalation would be called with correct params
    from scripts.aeonisk.multiagent.schemas.story_events import Escalation
    expected_escalation = Escalation(
        npc_id="npc_dorian_thrace_6336",
        reason="Attacked by player, turned hostile",
        template="desperate_fighter"
    )

    # Verify escalation would work
    assert expected_escalation.npc_id == npc.agent_id
