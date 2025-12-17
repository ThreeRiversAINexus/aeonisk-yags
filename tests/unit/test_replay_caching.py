"""
Unit tests for replay caching mechanism - TDD approach.

These tests define the expected behavior of the replay system's caching:
1. Cached LLM calls should be written to output JSONL
2. Player actions should match exactly between baseline and replayed fixtures
3. All-cached replay should produce deterministic results

Written BEFORE fixing the bug (TDD red phase).
"""

import json
import pytest
from pathlib import Path
from scripts.aeonisk.multiagent.llm_logger import MockLLMClient, MockMessages


class TestMockLLMClientLogging:
    """Test that MockLLMClient properly logs cached responses."""

    def test_mock_client_returns_cached_response(self):
        """MockLLMClient should return the cached response text."""
        cache = {
            ('player_01', 0): {
                'response': 'Fire suppressive shots at enemies',
                'tokens': {'input': 100, 'output': 50}
            }
        }

        client = MockLLMClient(cache, agent_id='player_01')

        # Simulate LLM call
        response = client.messages.create(
            model='claude-3-5-sonnet',
            messages=[{'role': 'user', 'content': 'What do you do?'}],
            temperature=0.8
        )

        # Should return cached text
        assert response.content[0].text == 'Fire suppressive shots at enemies'
        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 50

    def test_mock_client_increments_call_sequence(self):
        """MockLLMClient should track call sequence correctly."""
        cache = {
            ('player_01', 0): {'response': 'First action', 'tokens': {'input': 50, 'output': 25}},
            ('player_01', 1): {'response': 'Second action', 'tokens': {'input': 60, 'output': 30}},
        }

        client = MockLLMClient(cache, agent_id='player_01')

        # First call
        response1 = client.messages.create(
            model='claude-3-5-sonnet',
            messages=[{'role': 'user', 'content': 'Action 1'}],
            temperature=0.8
        )
        assert response1.content[0].text == 'First action'

        # Second call should get next cached response
        response2 = client.messages.create(
            model='claude-3-5-sonnet',
            messages=[{'role': 'user', 'content': 'Action 2'}],
            temperature=0.8
        )
        assert response2.content[0].text == 'Second action'

    def test_mock_client_raises_on_missing_cache(self):
        """MockLLMClient should raise if no cached response exists."""
        cache = {
            ('player_01', 0): {'response': 'Only one response', 'tokens': {'input': 50, 'output': 25}},
        }

        client = MockLLMClient(cache, agent_id='player_01')

        # First call works
        client.messages.create(
            model='claude-3-5-sonnet',
            messages=[{'role': 'user', 'content': 'Action 1'}],
            temperature=0.8
        )

        # Second call should raise (no cache for call #1)
        with pytest.raises(KeyError, match="No cached response"):
            client.messages.create(
                model='claude-3-5-sonnet',
                messages=[{'role': 'user', 'content': 'Action 2'}],
                temperature=0.8
            )

    def test_agent_id_mismatch_causes_keyerror(self):
        """
        Verify that agent_id mismatch causes KeyError (root cause hypothesis).

        This test demonstrates the bug we identified:
        - Cache has entries for 'player_01'
        - MockLLMClient initialized with wrong agent_id 'player'
        - Cache lookup fails because ('player', 0) != ('player_01', 0)

        This test should PASS (confirming hypothesis is correct).
        """
        # Setup: Cache with specific agent_id
        cache = {
            ('player_01', 0): {
                'response': 'Fire suppressive shots at enemies',
                'tokens': {'input': 100, 'output': 50}
            }
        }

        # Bug scenario: MockLLMClient initialized with WRONG agent_id
        client = MockLLMClient(cache, agent_id='player')  # Should be 'player_01'

        # This should raise KeyError (demonstrating the bug)
        with pytest.raises(KeyError, match="No cached response"):
            client.messages.create(
                model='claude-3-5-sonnet',
                messages=[{'role': 'user', 'content': 'What do you do?'}],
                temperature=0.8
            )


class TestExtractFixtureCompleteness:
    """Test that fixtures include all necessary LLM calls.

    Uses existing replay_test_fresh.jsonl fixture for validation.
    """

    @pytest.fixture
    def replay_fixture_path(self):
        """Path to the replay test fixture."""
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "replay_test_fresh.jsonl"

    @pytest.fixture
    def fixture_events(self, replay_fixture_path):
        """Load all events from the replay fixture."""
        if not replay_fixture_path.exists():
            pytest.skip(f"Fixture not found: {replay_fixture_path}")
        events = []
        with open(replay_fixture_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_extracted_fixture_includes_player_llm_calls(self, fixture_events):
        """Fixtures must include player LLM calls for replay caching.

        Validates that replay_test_fresh.jsonl contains player LLM calls with:
        1. agent_type='player'
        2. Valid call_sequence
        3. Response text present
        """
        player_llm_calls = [
            e for e in fixture_events
            if e.get('event_type') == 'llm_call' and e.get('agent_type') == 'player'
        ]

        assert len(player_llm_calls) > 0, \
            "Fixture should contain at least 1 player LLM call for replay caching"

        # Verify structure of first player LLM call
        first_call = player_llm_calls[0]
        assert 'agent_id' in first_call, "Player LLM call must have agent_id"
        assert first_call['agent_id'].startswith('player_'), \
            f"Player agent_id should start with 'player_', got {first_call['agent_id']}"
        assert 'call_sequence' in first_call, "LLM call must have call_sequence for replay ordering"
        assert 'response' in first_call, "LLM call must have response for caching"

    def test_extracted_fixture_includes_enemy_llm_calls(self, fixture_events):
        """Fixtures must include enemy LLM calls for replay caching.

        Enemy caching is known to work correctly, so this validates the baseline.
        """
        enemy_llm_calls = [
            e for e in fixture_events
            if e.get('event_type') == 'llm_call' and e.get('agent_type') == 'enemy'
        ]

        assert len(enemy_llm_calls) > 0, \
            "Fixture should contain at least 1 enemy LLM call for replay caching"

        # Verify structure
        first_call = enemy_llm_calls[0]
        assert 'agent_id' in first_call
        assert 'response' in first_call


class TestReplayDeterminism:
    """Test fixture structure supports deterministic replay.

    These tests validate the fixture contains all necessary data for replay
    without actually running expensive replay operations.
    """

    @pytest.fixture
    def replay_fixture_path(self):
        """Path to the replay test fixture."""
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "replay_test_fresh.jsonl"

    @pytest.fixture
    def fixture_events(self, replay_fixture_path):
        """Load all events from the replay fixture."""
        if not replay_fixture_path.exists():
            pytest.skip(f"Fixture not found: {replay_fixture_path}")
        events = []
        with open(replay_fixture_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_fixture_has_random_seed_for_determinism(self, fixture_events):
        """
        Fixture must have random_seed in session_start for deterministic replay.

        Without random_seed, dice rolls differ between runs, breaking determinism.
        """
        session_starts = [e for e in fixture_events if e.get('event_type') == 'session_start']
        assert len(session_starts) >= 1, "Fixture should have session_start event"

        session_start = session_starts[0]
        assert 'random_seed' in session_start, \
            "session_start must have random_seed for deterministic replay"
        assert isinstance(session_start['random_seed'], int), \
            "random_seed must be an integer"

    def test_fixture_has_llm_calls_for_all_agents(self, fixture_events):
        """
        Fixture must have LLM calls for DM, player, and enemy agents.

        All agent types need cached LLM calls for full deterministic replay.
        """
        llm_calls = [e for e in fixture_events if e.get('event_type') == 'llm_call']

        agent_types = set(call.get('agent_type') for call in llm_calls)

        assert 'dm' in agent_types, "Fixture should have DM LLM calls"
        assert 'player' in agent_types, "Fixture should have player LLM calls"
        # enemy may not be present in all fixtures, but check if combat fixture
        action_declarations = [e for e in fixture_events if e.get('event_type') == 'action_declaration']
        enemy_actions = [a for a in action_declarations if a.get('agent_type') == 'enemy']
        if enemy_actions:
            assert 'enemy' in agent_types, "Combat fixture should have enemy LLM calls"

    def test_fixture_llm_calls_have_sequence_numbers(self, fixture_events):
        """
        All LLM calls must have call_sequence for replay ordering.

        Replay uses (agent_id, call_sequence) to match cached responses.
        """
        llm_calls = [e for e in fixture_events if e.get('event_type') == 'llm_call']

        for call in llm_calls[:5]:  # Check first 5 calls
            assert 'call_sequence' in call, \
                f"LLM call for {call.get('agent_id')} missing call_sequence"
            assert isinstance(call['call_sequence'], int), \
                f"call_sequence must be int, got {type(call['call_sequence'])}"

    def test_fixture_action_declarations_match_llm_calls(self, fixture_events):
        """
        Verify action declarations can be traced back to LLM calls.

        This validates the data integrity needed for replay verification.
        """
        llm_calls = [e for e in fixture_events if e.get('event_type') == 'llm_call']
        action_declarations = [e for e in fixture_events if e.get('event_type') == 'action_declaration']

        # Get player agent IDs from declarations
        player_agents_in_actions = set(
            a.get('agent_id') for a in action_declarations
            if a.get('agent_type') == 'player'
        )

        # Get player agent IDs from LLM calls
        player_agents_in_llm = set(
            c.get('agent_id') for c in llm_calls
            if c.get('agent_type') == 'player'
        )

        # Every player with actions should have LLM calls
        assert player_agents_in_actions <= player_agents_in_llm, \
            f"Players with actions but no LLM calls: {player_agents_in_actions - player_agents_in_llm}"


class TestReplayOutputLogging:
    """Test LLM call logging structure for replay output."""

    @pytest.fixture
    def replay_fixture_path(self):
        """Path to the replay test fixture."""
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "replay_test_fresh.jsonl"

    @pytest.fixture
    def fixture_events(self, replay_fixture_path):
        """Load all events from the replay fixture."""
        if not replay_fixture_path.exists():
            pytest.skip(f"Fixture not found: {replay_fixture_path}")
        events = []
        with open(replay_fixture_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_llm_calls_have_tokens_for_cost_tracking(self, fixture_events):
        """
        LLM calls should include token counts for cost analysis.

        Token counts are useful for:
        1. Estimating replay cost
        2. Detecting anomalies (unusually long prompts)
        3. Cost optimization analysis
        """
        llm_calls = [e for e in fixture_events if e.get('event_type') == 'llm_call']

        calls_with_tokens = [c for c in llm_calls if 'tokens' in c]
        assert len(calls_with_tokens) > 0, "Some LLM calls should have token counts"

        # Check structure of tokens
        sample = calls_with_tokens[0]
        tokens = sample['tokens']
        assert 'input' in tokens or 'output' in tokens, \
            "tokens should have input/output fields"

    def test_llm_calls_have_model_info(self, fixture_events):
        """
        LLM calls should include model name for replay compatibility.

        Knowing which model generated responses helps:
        1. Debug behavior differences between models
        2. Ensure replay uses same model
        """
        llm_calls = [e for e in fixture_events if e.get('event_type') == 'llm_call']

        for call in llm_calls[:5]:  # Sample first 5
            assert 'model' in call, f"LLM call missing model field: {call.get('agent_id')}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
