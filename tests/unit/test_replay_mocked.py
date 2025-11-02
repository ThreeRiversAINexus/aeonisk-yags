"""
Unit tests for replay system using mocked LLM clients.

Tests fixture loading, agent identification, cache extraction, mock LLM behavior,
validation, and round filtering without making live API calls.

Target runtime: <10 seconds (vs 5-10 minutes for integration tests)
"""

import pytest
import json
from pathlib import Path
import sys

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from aeonisk.multiagent.replay import ReplaySession
from aeonisk.multiagent.llm_logger import MockLLMClient
from replay_fixture import (
    load_jsonl,
    extract_cache_for_agents,
    identify_player_agent_ids,
    identify_enemy_agent_ids
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def replay_fixture_path():
    """Path to replay_test_fresh.jsonl fixture."""
    return Path(__file__).parent.parent / "fixtures/sessions/replay_test_fresh.jsonl"


@pytest.fixture
def sample_events(tmp_path):
    """Create minimal JSONL events for testing."""
    events = [
        {
            "event_type": "session_start",
            "session": "test_session_123",
            "random_seed": 42,
            "config": {
                "session_name": "test_session",
                "max_turns": 3,
                "void_level": 5
            }
        },
        {
            "event_type": "llm_call",
            "round": None,
            "agent_id": "player_01",
            "agent_type": "player",
            "call_sequence": 0,
            "prompt": ["What do you do?"],
            "response": "I search for clues in the terminal",
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "tokens": {"input": 100, "output": 50}
        },
        {
            "event_type": "action_declaration",
            "round": 0,
            "action": {
                "agent_id": "player_01",
                "intent": "Search terminal for clues"
            }
        }
    ]

    jsonl_path = tmp_path / "test.jsonl"
    with open(jsonl_path, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    return jsonl_path, events


@pytest.fixture
def sample_llm_cache():
    """Create sample LLM cache for testing MockLLMClient."""
    return {
        ("player_01", 0): {
            "response": "I shoot the enemy with my rifle",
            "tokens": {"input": 120, "output": 60}
        },
        ("player_01", 1): {
            "response": "I take cover behind the terminal",
            "tokens": {"input": 130, "output": 55}
        },
        ("player_02", 0): {
            "response": "I hack the security console",
            "tokens": {"input": 110, "output": 45}
        }
    }


# ============================================================================
# FIXTURE LOADING TESTS
# ============================================================================

class TestFixtureLoading:
    """Test loading and parsing JSONL fixtures."""

    def test_load_jsonl_parses_events(self, sample_events):
        """load_jsonl() should parse all events from JSONL file."""
        path, expected_events = sample_events
        events = load_jsonl(path)

        assert len(events) == len(expected_events)
        assert events[0]['event_type'] == 'session_start'
        assert events[1]['event_type'] == 'llm_call'
        assert events[2]['event_type'] == 'action_declaration'

    def test_load_jsonl_skips_empty_lines(self, tmp_path):
        """load_jsonl() should skip blank lines in JSONL."""
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('{"event_type":"session_start"}\n\n{"event_type":"scenario"}\n')

        events = load_jsonl(jsonl)
        assert len(events) == 2
        assert events[0]['event_type'] == 'session_start'
        assert events[1]['event_type'] == 'scenario'

    def test_replay_session_extracts_metadata(self, sample_events):
        """ReplaySession.load_log() should extract session metadata."""
        path, _ = sample_events
        replay = ReplaySession(str(path))
        replay.load_log()

        assert replay.session_id == "test_session_123"
        assert replay.random_seed == 42
        assert replay.config['session_name'] == "test_session"
        assert replay.config['max_turns'] == 3

    def test_replay_session_builds_llm_cache(self, sample_events):
        """ReplaySession.load_log() should build LLM call cache."""
        path, _ = sample_events
        replay = ReplaySession(str(path))
        replay.load_log()

        # Cache key: (agent_id, call_sequence)
        cache_key = ("player_01", 0)
        assert cache_key in replay.llm_cache

        cached = replay.llm_cache[cache_key]
        assert cached['response'] == "I search for clues in the terminal"
        assert cached['model'] == "claude-sonnet-4"
        assert cached['tokens']['input'] == 100
        assert cached['tokens']['output'] == 50


# ============================================================================
# AGENT ID IDENTIFICATION TESTS
# ============================================================================

class TestAgentIdentification:
    """Test agent ID extraction from fixture events."""

    def test_identify_player_agents_from_llm_calls(self):
        """Should identify players from llm_call events."""
        events = [
            {
                "event_type": "llm_call",
                "agent_id": "player_ash",
                "agent_type": "player"
            },
            {
                "event_type": "llm_call",
                "agent_id": "player_echo",
                "agent_type": "player"
            }
        ]

        player_ids = identify_player_agent_ids(events)
        assert "player_ash" in player_ids
        assert "player_echo" in player_ids
        assert len(player_ids) == 2

    def test_identify_player_agents_from_action_declarations(self):
        """Should identify players from action_declaration events."""
        events = [
            {
                "event_type": "action_declaration",
                "action": {"agent_id": "player_test_001"}
            },
            {
                "event_type": "action_declaration",
                "action": {"agent_id": "player_test_002"}
            }
        ]

        player_ids = identify_player_agent_ids(events)
        assert "player_test_001" in player_ids
        assert "player_test_002" in player_ids

    def test_identify_enemy_agents(self):
        """Should identify enemies from llm_call events."""
        events = [
            {
                "event_type": "llm_call",
                "agent_id": "enemy_agent_abc123",
                "agent_type": "enemy"
            },
            {
                "event_type": "llm_call",
                "agent_id": "enemy_agent_def456",
                "agent_type": "enemy"
            }
        ]

        enemy_ids = identify_enemy_agent_ids(events)
        assert "enemy_agent_abc123" in enemy_ids
        assert "enemy_agent_def456" in enemy_ids
        assert len(enemy_ids) == 2


# ============================================================================
# CACHE EXTRACTION TESTS
# ============================================================================

class TestCacheExtraction:
    """Test LLM cache extraction for selective caching."""

    def test_extract_cache_all_agents(self):
        """extract_cache_for_agents() with None should cache all agents."""
        events = [
            {
                "event_type": "llm_call",
                "agent_id": "player_01",
                "call_sequence": 0,
                "prompt": ["Test prompt"],
                "response": "Player response",
                "model": "claude",
                "temperature": 0.7,
                "tokens": {"input": 50, "output": 25}
            },
            {
                "event_type": "llm_call",
                "agent_id": "dm",
                "call_sequence": 0,
                "prompt": ["Narrate"],
                "response": "DM narration",
                "model": "claude",
                "temperature": 0.7,
                "tokens": {"input": 60, "output": 30}
            }
        ]

        cache = extract_cache_for_agents(events, agent_ids=None)

        assert ("player_01", 0) in cache
        assert ("dm", 0) in cache
        assert len(cache) == 2
        assert cache[("player_01", 0)]['response'] == "Player response"
        assert cache[("dm", 0)]['response'] == "DM narration"

    def test_extract_cache_specific_agents(self):
        """extract_cache_for_agents() should filter by agent_ids."""
        events = [
            {
                "event_type": "llm_call",
                "agent_id": "player_01",
                "call_sequence": 0,
                "prompt": ["Test"],
                "response": "Player response",
                "model": "claude",
                "temperature": 0.7,
                "tokens": {"input": 50, "output": 25}
            },
            {
                "event_type": "llm_call",
                "agent_id": "dm",
                "call_sequence": 0,
                "prompt": ["Test"],
                "response": "DM response",
                "model": "claude",
                "temperature": 0.7,
                "tokens": {"input": 60, "output": 30}
            }
        ]

        # Only cache player
        cache = extract_cache_for_agents(events, agent_ids={"player_01"})

        assert ("player_01", 0) in cache
        assert ("dm", 0) not in cache
        assert len(cache) == 1


# ============================================================================
# MOCK LLM CLIENT TESTS
# ============================================================================

class TestMockLLMClient:
    """Test MockLLMClient behavior."""

    def test_returns_cached_response(self, sample_llm_cache):
        """MockLLMClient should return cached response for correct agent."""
        client = MockLLMClient(sample_llm_cache, agent_id="player_01")
        response = client.messages.create(
            model="claude",
            messages=[{"role": "user", "content": "What do you do?"}],
            temperature=0.8
        )

        assert response.content[0].text == "I shoot the enemy with my rifle"
        assert response.usage.input_tokens == 120
        assert response.usage.output_tokens == 60

    def test_increments_call_sequence(self, sample_llm_cache):
        """MockLLMClient should track call sequence correctly."""
        client = MockLLMClient(sample_llm_cache, agent_id="player_01")

        # First call (sequence 0)
        response1 = client.messages.create(
            model="claude",
            messages=[{"role": "user", "content": "Action 1"}],
            temperature=0.8
        )
        assert response1.content[0].text == "I shoot the enemy with my rifle"

        # Second call (sequence 1)
        response2 = client.messages.create(
            model="claude",
            messages=[{"role": "user", "content": "Action 2"}],
            temperature=0.8
        )
        assert response2.content[0].text == "I take cover behind the terminal"

    def test_raises_on_missing_cache(self, sample_llm_cache):
        """MockLLMClient should raise KeyError when cache is missing."""
        client = MockLLMClient(sample_llm_cache, agent_id="player_01")

        # Consume both cached calls
        client.messages.create(model="claude", messages=[], temperature=0.8)
        client.messages.create(model="claude", messages=[], temperature=0.8)

        # Third call has no cache
        with pytest.raises(KeyError, match="No cached response"):
            client.messages.create(model="claude", messages=[], temperature=0.8)

    def test_wrong_agent_id_causes_cache_miss(self, sample_llm_cache):
        """MockLLMClient with wrong agent_id cannot find cache entries."""
        # Create client with WRONG agent_id
        client = MockLLMClient(sample_llm_cache, agent_id="player_wrong")

        with pytest.raises(KeyError, match="No cached response"):
            client.messages.create(model="claude", messages=[], temperature=0.8)


# ============================================================================
# REPLAY SESSION VALIDATION TESTS
# ============================================================================

class TestReplayValidation:
    """Test ReplaySession validation logic."""

    def test_validate_completeness_success(self, sample_events):
        """Validation should pass for complete fixture."""
        path, _ = sample_events
        replay = ReplaySession(str(path))
        replay.load_log()

        validation = replay.validate_completeness()

        # Check validation structure
        assert 'can_replay' in validation
        assert 'issues' in validation
        assert 'llm_calls_cached' in validation
        assert isinstance(validation['can_replay'], bool)
        assert isinstance(validation['issues'], list)

    def test_validate_detects_missing_random_seed(self, tmp_path):
        """Validation should warn about missing random seed."""
        events = [
            {
                "event_type": "session_start",
                "session": "test",
                "config": {}
                # Missing random_seed
            }
        ]

        path = tmp_path / "no_seed.jsonl"
        with open(path, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')

        replay = ReplaySession(str(path))
        replay.load_log()
        validation = replay.validate_completeness()

        # Should have issue about missing random seed
        issues_text = ' '.join(validation['issues']).lower()
        assert "random" in issues_text or "seed" in issues_text


# ============================================================================
# ROUND FILTERING TESTS
# ============================================================================

class TestRoundFiltering:
    """Test round-based event filtering."""

    def test_get_rounds_in_session(self, replay_fixture_path):
        """Should identify all round numbers in session."""
        if not replay_fixture_path.exists():
            pytest.skip("Fixture not available")

        replay = ReplaySession(str(replay_fixture_path))
        replay.load_log()

        rounds = replay.get_rounds_in_session()
        assert isinstance(rounds, list)
        assert all(isinstance(r, int) for r in rounds)
        assert rounds == sorted(rounds)  # Should be sorted
        assert len(rounds) > 0  # Should have at least one round

    def test_start_from_round_parameter(self, tmp_path):
        """ReplaySession should accept start_from_round parameter."""
        fake_file = tmp_path / "fake.jsonl"
        fake_file.write_text('{"event_type":"session_start"}\n')

        replay = ReplaySession(str(fake_file), start_from_round=2)
        assert replay.start_from_round == 2
