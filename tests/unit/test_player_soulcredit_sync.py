"""
Unit tests for player soulcredit sync from mechanics engine.

Tests verify that AIPlayerAgent syncs character_state.soulcredit from
mechanics.soulcredit_states after action resolution (parallel to void sync).
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
from scripts.aeonisk.multiagent.base import Message, MessageType
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, SoulcreditState


@pytest.fixture
def base_character_state():
    """Create a base character state for testing."""
    return CharacterState(
        name="Test Character",
        pronouns="they/them",
        faction="Test Faction",
        attributes={
            "Strength": 3,
            "Health": 4,
            "Agility": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 3,
            "Resolve": 3,
        },
        skills={
            "Combat": 4,
            "Investigation": 3,
        },
        void_score=2,
        soulcredit=5,  # Initial soulcredit
        bonds=[],
        goals=["Test Goal"],
    )


def create_mock_player_with_mechanics(character_state: CharacterState, agent_id: str = "test_agent_123"):
    """
    Create a mock AIPlayerAgent with a real MechanicsEngine for testing soulcredit sync.

    Args:
        character_state: CharacterState to use
        agent_id: Agent ID for tracking
    """
    # Create real MechanicsEngine with soulcredit tracking
    mechanics = MechanicsEngine(
        jsonl_logger=None,
        shared_state=None
    )

    # Initialize soulcredit state in mechanics AND void state (required by _handle_action_resolved)
    sc_state = mechanics.get_soulcredit_state(agent_id, initial_score=character_state.soulcredit)
    void_state = mechanics.get_void_state(agent_id)
    void_state.score = character_state.void_score  # Set initial void score

    # Create mock shared_state that returns the real mechanics engine
    mock_shared_state = MagicMock()
    mock_shared_state.get_mechanics_engine.return_value = mechanics

    # Create mock player agent (using MagicMock for simplicity)
    player = MagicMock(spec=AIPlayerAgent)
    player.agent_id = agent_id
    player.character_state = character_state
    player.shared_state = mock_shared_state
    player.recent_narrations = []  # Required by _handle_action_resolved

    # Bind the REAL _handle_action_resolved method to our mock
    # This allows us to test the real implementation logic
    from scripts.aeonisk.multiagent.player import AIPlayerAgent as RealPlayerAgent
    player._handle_action_resolved = RealPlayerAgent._handle_action_resolved.__get__(player, AIPlayerAgent)

    return player, mechanics


@pytest.mark.asyncio
async def test_player_syncs_soulcredit_after_action_resolution(base_character_state):
    """
    Test that player syncs character_state.soulcredit from mechanics after action resolution.

    This test verifies the fix for the bug where soulcredit changes were tracked in
    mechanics.soulcredit_states but not synced to character_state.soulcredit before
    JSONL logging (unlike void, which was synced correctly).
    """
    # Setup
    agent_id = "test_agent_123"
    player, mechanics = create_mock_player_with_mechanics(base_character_state, agent_id)

    # Initial state: soulcredit = 5 (from base_character_state)
    assert player.character_state.soulcredit == 5
    assert mechanics.get_soulcredit_state(agent_id).score == 5

    # Simulate soulcredit change in mechanics (e.g., DM applied +2 for honorable action)
    mechanics.get_soulcredit_state(agent_id).adjust(+2, "honorable negotiation")
    assert mechanics.get_soulcredit_state(agent_id).score == 7  # 5 + 2 = 7

    # Character state still has old value (not synced yet)
    assert player.character_state.soulcredit == 5  # STALE

    # Simulate ACTION_RESOLVED message
    message = Message(
        id="test_msg_001",
        type=MessageType.ACTION_RESOLVED,
        sender="dm",
        recipient=agent_id,
        payload={
            'agent_id': agent_id,
            'outcome': {},
            'narration': 'Test narration',
            'original_action': {
                'character_name': 'Test Character'
            }
        },
        timestamp=datetime.now()
    )

    # Handle action resolution (should sync soulcredit from mechanics)
    await player._handle_action_resolved(message)

    # CRITICAL ASSERTION: Character state should now reflect mechanics soulcredit
    # This test will FAIL before the fix (character_state.soulcredit = 5)
    # This test will PASS after the fix (character_state.soulcredit = 7)
    assert player.character_state.soulcredit == 7, (
        f"Expected character_state.soulcredit to sync from mechanics (7), "
        f"but got {player.character_state.soulcredit}"
    )


@pytest.mark.asyncio
async def test_player_syncs_negative_soulcredit_changes(base_character_state):
    """Test that player syncs negative soulcredit changes (e.g., -1 for threatening violence)."""
    agent_id = "test_agent_456"
    player, mechanics = create_mock_player_with_mechanics(base_character_state, agent_id)

    # Initial soulcredit = 5
    assert player.character_state.soulcredit == 5

    # Apply negative soulcredit change (e.g., threatened violence as enforcer)
    mechanics.get_soulcredit_state(agent_id).adjust(-1, "threatened violence")
    assert mechanics.get_soulcredit_state(agent_id).score == 4  # 5 - 1 = 4

    # Simulate action resolution
    message = Message(
        id="test_msg_002",
        type=MessageType.ACTION_RESOLVED,
        sender="dm",
        recipient=agent_id,
        payload={
            'agent_id': agent_id,
            'outcome': {},
            'narration': 'Test narration',
            'original_action': {'character_name': 'Test Character'}
        },
        timestamp=datetime.now()
    )

    await player._handle_action_resolved(message)

    # Should sync negative change
    assert player.character_state.soulcredit == 4


@pytest.mark.asyncio
async def test_player_syncs_clamped_soulcredit(base_character_state):
    """Test that player syncs clamped soulcredit values (min -10, max +10)."""
    agent_id = "test_agent_789"
    base_character_state.soulcredit = 9  # Close to max
    player, mechanics = create_mock_player_with_mechanics(base_character_state, agent_id)

    # Apply +5 soulcredit (should clamp to +10)
    mechanics.get_soulcredit_state(agent_id).adjust(+5, "heroic action")
    assert mechanics.get_soulcredit_state(agent_id).score == 10  # Clamped to max

    # Simulate action resolution
    message = Message(
        id="test_msg_003",
        type=MessageType.ACTION_RESOLVED,
        sender="dm",
        recipient=agent_id,
        payload={
            'agent_id': agent_id,
            'outcome': {},
            'narration': 'Test narration',
            'original_action': {'character_name': 'Test Character'}
        },
        timestamp=datetime.now()
    )

    await player._handle_action_resolved(message)

    # Should sync clamped value
    assert player.character_state.soulcredit == 10


@pytest.mark.asyncio
async def test_player_does_not_sync_for_other_agents(base_character_state):
    """Test that player does NOT sync soulcredit when ACTION_RESOLVED is for another agent."""
    agent_id = "test_agent_self"
    other_agent_id = "test_agent_other"
    player, mechanics = create_mock_player_with_mechanics(base_character_state, agent_id)

    # Initial soulcredit = 5
    assert player.character_state.soulcredit == 5

    # Change soulcredit in mechanics
    mechanics.get_soulcredit_state(agent_id).adjust(+3, "test change")
    assert mechanics.get_soulcredit_state(agent_id).score == 8

    # Simulate ACTION_RESOLVED for ANOTHER agent (not self)
    message = Message(
        id="test_msg_004",
        type=MessageType.ACTION_RESOLVED,
        sender="dm",
        recipient=agent_id,
        payload={
            'agent_id': other_agent_id,  # Different agent!
            'outcome': {},
            'narration': 'Test narration',
            'original_action': {'character_name': 'Other Character'}
        },
        timestamp=datetime.now()
    )

    await player._handle_action_resolved(message)

    # Should NOT sync (early return at line 846-847)
    assert player.character_state.soulcredit == 5  # Still stale (expected behavior)
