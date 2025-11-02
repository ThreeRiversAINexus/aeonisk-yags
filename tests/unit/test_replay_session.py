"""
Unit tests for ReplaySession functionality.

Tests the replay system's ability to:
1. Parse session structure from JSONL logs
2. Start replay from specific rounds (skip early rounds)
3. Cache dependencies correctly when starting mid-session
4. Restore character state appropriately

Following TDD approach: Tests written first to define desired behavior,
then implementation will be added to make tests pass.
"""

import asyncio
import json
import pytest
from pathlib import Path
from typing import Dict, List, Set

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from aeonisk.multiagent.replay import ReplaySession


# === FIXTURES ===

@pytest.fixture
def sample_session_path(tmp_path):
    """
    Create a minimal valid session JSONL for testing.

    Session structure:
    - Round 0: Player action + resolution
    - Round 1: Player action + resolution
    - Round 2: Player action + resolution

    This allows testing start-from-round=2 functionality.
    """
    session_file = tmp_path / "test_session.jsonl"

    events = [
        # Session start
        {
            "event_type": "session_start",
            "session": "test_session_123",
            "random_seed": 42,
            "config": {
                "session_name": "test_combat",
                "max_turns": 5,
                "dm_narration_style": "tactical"
            }
        },

        # Scenario
        {
            "event_type": "scenario",
            "round": 0,
            "theme": "test_scenario",
            "location": "Test Zone",
            "enemies": []
        },

        # Round 0
        {
            "event_type": "round_start",
            "round": 0
        },
        {
            "event_type": "llm_call",
            "round": None,  # Pre-round declaration
            "agent_id": "player_test_001",
            "agent_type": "player",
            "call_sequence": 0,
            "prompt": ["Test prompt round 0"],
            "response": "INTENT: Search for clues\nATTRIBUTE: Intelligence\nSKILL: Investigation",
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "tokens": {"input": 100, "output": 50}
        },
        {
            "event_type": "action_declaration",
            "round": 0,
            "action": {
                "agent_id": "player_test_001",
                "intent": "Search for clues",
                "attribute": "Intelligence",
                "skill": "Investigation",
                "action_type": "investigate"
            }
        },
        {
            "event_type": "action_resolution",
            "round": 0,
            "agent": "Test Player",
            "action": "Search for clues",
            "roll": {
                "success": True,
                "total": 15,
                "margin": 5
            },
            "effects": {
                "void_changes": [],
                "damage": {"dealt": 0}
            }
        },
        {
            "event_type": "round_summary",
            "round": 0,
            "summary": "Round 0 complete"
        },

        # Round 1
        {
            "event_type": "round_start",
            "round": 1
        },
        {
            "event_type": "llm_call",
            "round": None,
            "agent_id": "player_test_001",
            "agent_type": "player",
            "call_sequence": 1,
            "prompt": ["Test prompt round 1"],
            "response": "INTENT: Attack enemy\nATTRIBUTE: Agility\nSKILL: Guns",
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "tokens": {"input": 100, "output": 50}
        },
        {
            "event_type": "action_declaration",
            "round": 1,
            "action": {
                "agent_id": "player_test_001",
                "intent": "Attack enemy",
                "attribute": "Agility",
                "skill": "Guns",
                "action_type": "combat"
            }
        },
        {
            "event_type": "action_resolution",
            "round": 1,
            "agent": "Test Player",
            "action": "Attack enemy",
            "roll": {
                "success": True,
                "total": 18,
                "margin": 8
            },
            "effects": {
                "void_changes": [],
                "damage": {"dealt": 12}
            }
        },
        {
            "event_type": "round_summary",
            "round": 1,
            "summary": "Round 1 complete"
        },

        # Round 2
        {
            "event_type": "round_start",
            "round": 2
        },
        {
            "event_type": "llm_call",
            "round": None,
            "agent_id": "player_test_001",
            "agent_type": "player",
            "call_sequence": 2,
            "prompt": ["Test prompt round 2"],
            "response": "INTENT: Take cover\nATTRIBUTE: Agility\nSKILL: Tactics",
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "tokens": {"input": 100, "output": 50}
        },
        {
            "event_type": "action_declaration",
            "round": 2,
            "action": {
                "agent_id": "player_test_001",
                "intent": "Take cover",
                "attribute": "Agility",
                "skill": "Tactics",
                "action_type": "investigate"
            }
        },
        {
            "event_type": "action_resolution",
            "round": 2,
            "agent": "Test Player",
            "action": "Take cover",
            "roll": {
                "success": True,
                "total": 16,
                "margin": 6
            },
            "effects": {
                "void_changes": [],
                "damage": {"dealt": 0}
            }
        },
        {
            "event_type": "round_summary",
            "round": 2,
            "summary": "Round 2 complete"
        }
    ]

    with open(session_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    return session_file


# === SESSION STRUCTURE PARSING TESTS ===

def test_load_session_structure(sample_session_path):
    """Verify we can parse session structure correctly."""
    replay = ReplaySession(str(sample_session_path))
    replay.load_log()

    assert replay.random_seed == 42
    assert len(replay.llm_cache) == 3  # 3 player LLM calls
    assert replay.config['session_name'] == "test_combat"
    assert replay.session_id == "test_session_123"


def test_identify_round_boundaries(sample_session_path):
    """Verify we can identify where each round starts/ends."""
    replay = ReplaySession(str(sample_session_path))
    replay.load_log()

    # Count events by round
    round_events = {0: [], 1: [], 2: []}
    for event in replay.events:
        if 'round' in event and event['round'] in round_events:
            round_events[event['round']].append(event['event_type'])

    # Each round should have: round_start, action_declaration, action_resolution, round_summary
    assert 'round_start' in round_events[0]
    assert 'action_declaration' in round_events[0]
    assert 'action_resolution' in round_events[0]
    assert 'round_summary' in round_events[0]

    assert 'round_start' in round_events[1]
    assert 'round_start' in round_events[2]


def test_llm_cache_structure(sample_session_path):
    """Verify LLM cache has correct structure."""
    replay = ReplaySession(str(sample_session_path))
    replay.load_log()

    # Check cache keys
    assert ("player_test_001", 0) in replay.llm_cache
    assert ("player_test_001", 1) in replay.llm_cache
    assert ("player_test_001", 2) in replay.llm_cache

    # Check cache content structure
    cached_response = replay.llm_cache[("player_test_001", 0)]
    assert 'prompt' in cached_response
    assert 'response' in cached_response
    assert 'model' in cached_response
    assert cached_response['response'] == "INTENT: Search for clues\nATTRIBUTE: Intelligence\nSKILL: Investigation"


# === START-FROM-ROUND LOGIC TESTS (THESE WILL FAIL UNTIL IMPLEMENTED) ===

def test_replay_has_start_from_round_parameter(tmp_path):
    """Verify ReplaySession accepts start_from_round parameter."""
    # Create a fake file for the file existence check
    fake_file = tmp_path / "fake.jsonl"
    fake_file.write_text('{"event_type":"session_start"}\n')

    replay = ReplaySession(
        log_path=str(fake_file),
        start_from_round=2
    )
    assert replay.start_from_round == 2


def test_replay_from_round_2_skips_early_rounds(sample_session_path):
    """
    Verify starting from round 2 skips rounds 0-1.

    When start_from_round=2:
    - Should NOT replay round 0 actions
    - Should NOT replay round 1 actions
    - Should replay round 2 actions
    - BUT critical events like scenario may have round=0 and are included
    """
    # This will fail until we implement the logic
    replay = ReplaySession(
        str(sample_session_path),
        start_from_round=2,
        replay_to_round=2
    )
    replay.load_log()

    # After implementation, this method will filter events
    filtered_events = replay.get_events_to_replay()

    # Check that non-critical round 0/1 events are skipped
    action_resolutions = [e for e in filtered_events if e.get('event_type') == 'action_resolution']
    resolution_rounds = [e.get('round') for e in action_resolutions]

    assert 0 not in resolution_rounds, "Round 0 action resolutions should be skipped"
    assert 1 not in resolution_rounds, "Round 1 action resolutions should be skipped"
    assert 2 in resolution_rounds, "Round 2 action resolutions should be included"

    # Verify critical events are still included even if round < start_from_round
    event_types = [e.get('event_type') for e in filtered_events]
    assert 'session_start' in event_types, "session_start must always be included"
    assert 'scenario' in event_types, "scenario must be included for context"


def test_cache_includes_all_agent_declarations(sample_session_path):
    """
    Verify starting from round N includes ALL agent LLM cache.

    When starting from round 2, we still need:
    - Player agent LLM cache (for personality consistency)
    - Enemy agent LLM cache (if enemies spawned in earlier rounds)

    This is because agents are stateful and their behavior in round 2
    depends on their earlier decisions/personality.
    """
    replay = ReplaySession(
        str(sample_session_path),
        start_from_round=2
    )
    replay.load_log()

    # All LLM calls should be in cache, even from skipped rounds
    # (because agents are stateful and need context)
    assert ("player_test_001", 0) in replay.llm_cache, "Need round 0 cache for agent consistency"
    assert ("player_test_001", 1) in replay.llm_cache, "Need round 1 cache for agent consistency"
    assert ("player_test_001", 2) in replay.llm_cache, "Need round 2 cache for current round"


def test_start_from_round_requires_session_start(sample_session_path):
    """
    Verify session_start event is always included.

    Even when starting from round N, we need:
    - session_start (for config and random seed)
    - scenario (for environmental context)
    """
    replay = ReplaySession(
        str(sample_session_path),
        start_from_round=2
    )
    replay.load_log()

    filtered_events = replay.get_events_to_replay()
    event_types = [e['event_type'] for e in filtered_events]

    assert 'session_start' in event_types, "session_start must always be included"
    assert 'scenario' in event_types, "scenario must be included for context"


# === INTEGRATION TEST (WILL FAIL UNTIL FULL IMPLEMENTATION) ===

@pytest.mark.skip(reason="Integration test requiring full session setup - tested manually later")
async def test_isolated_round_replay_executes(sample_session_path):
    """
    Verify replaying isolated round 2 actually executes.

    This is an integration test that the full replay system works
    when starting from a specific round.

    NOTE: Skipped in unit tests - will be tested with real production session.
    """
    replay = ReplaySession(
        str(sample_session_path),
        start_from_round=2,
        replay_to_round=2
    )
    replay.load_log()

    # Validate before replay
    validation = replay.validate_completeness()
    assert validation['can_replay'], f"Validation failed: {validation['issues']}"

    # Execute replay (this will fail until we implement start_from_round)
    result = await replay.replay()

    assert result['status'] == 'success'
    # When properly implemented, should only replay round 2
    # (exact assertion depends on how we track rounds_replayed)


# === HELPER METHOD TESTS ===

def test_get_rounds_in_session(sample_session_path):
    """Verify we can identify all rounds in a session."""
    replay = ReplaySession(str(sample_session_path))
    replay.load_log()

    # After implementation, this helper method will exist
    rounds = replay.get_rounds_in_session()
    assert rounds == [0, 1, 2]


def test_get_round_range_events(sample_session_path):
    """Verify we can extract events for a specific round range."""
    replay = ReplaySession(str(sample_session_path))
    replay.load_log()

    # After implementation, this helper method will exist
    round_2_events = replay.get_events_for_round_range(start_round=2, end_round=2)

    # Should only have round 2 events
    round_numbers = set(e.get('round') for e in round_2_events if 'round' in e and e['round'] is not None)
    assert round_numbers == {2}


# === VALIDATION TESTS ===

def test_validation_detects_missing_session_start(tmp_path):
    """Verify validation catches missing session_start event."""
    bad_session = tmp_path / "bad_session.jsonl"

    # Create session without session_start
    events = [
        {"event_type": "action_declaration", "round": 0, "action": {}}
    ]

    with open(bad_session, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    replay = ReplaySession(str(bad_session))

    with pytest.raises(ValueError, match="session_start"):
        replay.load_log()


def test_validation_warns_missing_random_seed(tmp_path):
    """Verify validation warns about missing random seed."""
    no_seed_session = tmp_path / "no_seed.jsonl"

    events = [
        {
            "event_type": "session_start",
            "session": "test",
            "config": {}
            # Missing random_seed
        }
    ]

    with open(no_seed_session, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    replay = ReplaySession(str(no_seed_session))
    replay.load_log()  # Should succeed but warn

    validation = replay.validate_completeness()
    assert any("random seed" in issue.lower() for issue in validation['issues'])


# === DOCUMENTATION TESTS ===

def test_start_from_round_docstring():
    """Verify start_from_round parameter is documented."""
    import inspect

    # After implementation, __init__ docstring should mention start_from_round
    doc = inspect.getdoc(ReplaySession.__init__)
    # This will fail until we add the parameter
    assert "start_from_round" in doc.lower() if doc else False, \
        "start_from_round parameter should be documented in __init__ docstring"
