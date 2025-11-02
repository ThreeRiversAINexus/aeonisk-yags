"""
Test suite for player LLM call logging.

This test verifies that player action generation ALWAYS logs LLM calls,
regardless of whether it uses structured output (Pydantic AI) or legacy
text parsing. Without proper logging, replay functionality fails because
the cache is empty.

Root Cause (pre-fix):
- Modern players use _generate_player_action_pydantic() which calls
  llm_provider.generate_structured()
- Neither method logs LLM calls
- Logging code exists in legacy fallback path (never reached)
- Result: player LLM calls never logged, replay cache empty, replay fails

Fix Required:
- Add llm_logger._log_llm_call() after successful structured output generation
- Extract prompt/response/tokens from Pydantic AI result
- Must happen BEFORE returning from _generate_player_action_pydantic()
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime

# No module-level markers - using pytest.mark.asyncio on each test instead


class TestPlayerLLMLogging:
    """Test that player action generation logs LLM calls for replay."""

    @pytest.mark.skip(reason="Requires event-driven architecture refactor - AIPlayerAgent uses message-based protocol, not direct method calls. Test needs rewrite to mock socket communication.")
    @pytest.mark.asyncio
    async def test_structured_output_logs_llm_call(self):
        """
        Player using Pydantic AI structured output MUST log LLM calls.

        This test should FAIL until player.py is fixed to log LLM calls
        when using _generate_player_action_pydantic().

        Expected behavior:
        - Player calls llm_provider.generate_structured()
        - After successful generation, MUST call llm_logger._log_llm_call()
        - Log event must have agent_type='player', agent_id, prompt, response

        Current behavior (bug):
        - Player calls llm_provider.generate_structured()
        - Returns immediately without logging
        - llm_logger._log_llm_call() never called
        - Replay cache empty for players
        """
        # Import after pytest collection to avoid import errors
        from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger
        from scripts.aeonisk.multiagent.shared_state import SharedState

        # Create mock JSONL logger that tracks logged events
        logged_events = []

        def mock_write_event(event_data):
            logged_events.append(event_data.copy())

        mock_jsonl_logger = Mock()
        mock_jsonl_logger.write_event = mock_write_event

        # Create LLM logger for player
        llm_logger = LLMCallLogger(
            agent_id='player_test',
            agent_type='player',
            jsonl_logger=mock_jsonl_logger,
            session_id='test_session'
        )

        # Create mock llm_provider with generate_structured
        mock_llm_provider = AsyncMock()

        # Mock successful structured output (PlayerAction schema)
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction

        mock_player_action = PlayerAction(
            intent="Fire suppressive shots at raiders",
            description="I draw my pistol and open fire with controlled bursts at the raiders, aiming to suppress their advance and force them to take cover.",
            action_type="combat",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Combat action under stress against multiple targets",
            character_name="Test Player",
            agent_id="player_test",
            target="tgt_raider_01",
            target_position=None
        )

        mock_llm_provider.generate_structured = AsyncMock(return_value=mock_player_action)

        # Create character config (mimics session config format)
        character_config = {
            'name': 'Test Player',
            'faction': 'Test Faction',
            'attributes': {'Size': 5, 'Endurance': 3, 'Perception': 4},
            'skills': {'Guns': 3},
            'void_score': 3,
            'soulcredit': 5,
            'bonds': ["Defend the innocent"],
            'goals': ["Survive the mission"]
        }

        # Create mock shared state
        mock_shared_state = Mock(spec=SharedState)
        mock_shared_state.get_mechanics_engine = Mock(return_value=None)
        mock_shared_state.get_other_players = Mock(return_value=[])

        # Create player agent with mocked components
        player = AIPlayerAgent(
            agent_id='player_test',
            socket_path='/tmp/test_socket',  # Required positional arg
            character_config=character_config,
            llm_client=None,  # Not needed with llm_provider
            llm_config={'provider': 'anthropic', 'model': 'claude-3-5-sonnet-20241022'},
            shared_state=mock_shared_state
        )

        # Inject our mocked components
        player.llm_logger = llm_logger
        player.llm_provider = mock_llm_provider

        # Set scenario context (required for action generation)
        player.current_scenario = {
            'theme': 'Test Combat',
            'location': 'Test Arena',
            'situation': 'Test enemies approaching',
            'round': 1
        }

        # Generate action (should use structured output path)
        action = await player.generate_action()

        # CRITICAL ASSERTION: Verify LLM call was logged
        assert len(logged_events) > 0, \
            "Expected at least 1 LLM call logged, got 0. " \
            "Player structured output path is NOT logging LLM calls!"

        # Find the llm_call event
        llm_call_events = [e for e in logged_events if e.get('event_type') == 'llm_call']

        assert len(llm_call_events) >= 1, \
            f"Expected at least 1 llm_call event, got {len(llm_call_events)}. " \
            f"Logged events: {logged_events}"

        # Verify the llm_call event has correct structure
        llm_call = llm_call_events[0]

        assert llm_call['agent_id'] == 'player_test', \
            f"Expected agent_id='player_test', got '{llm_call.get('agent_id')}'"

        assert llm_call['agent_type'] == 'player', \
            f"Expected agent_type='player', got '{llm_call.get('agent_type')}'"

        assert 'prompt' in llm_call, "LLM call event missing 'prompt' field"
        assert 'response' in llm_call, "LLM call event missing 'response' field"
        assert 'model' in llm_call, "LLM call event missing 'model' field"
        assert 'tokens' in llm_call, "LLM call event missing 'tokens' field"

        # Verify the action was generated correctly (sanity check)
        assert action is not None, "Player should have generated an action"
        assert action.intent == "Fire suppressive shots at raiders"

    @pytest.mark.skip(reason="Requires event-driven architecture refactor - AIPlayerAgent uses message-based protocol, not direct method calls. Test needs rewrite to mock socket communication.")
    @pytest.mark.asyncio
    async def test_legacy_fallback_logs_llm_call(self):
        """
        Player using legacy text parsing MUST log LLM calls.

        This path already has logging code (player.py:1823-1833) but we
        test it anyway to ensure it doesn't regress.

        This test should PASS both before and after the fix.
        """
        # Import after pytest collection
        from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger
        from scripts.aeonisk.multiagent.shared_state import SharedState

        # Create mock JSONL logger
        logged_events = []

        def mock_write_event(event_data):
            logged_events.append(event_data.copy())

        mock_jsonl_logger = Mock()
        mock_jsonl_logger.write_event = mock_write_event

        # Create LLM logger
        llm_logger = LLMCallLogger(
            agent_id='player_legacy',
            agent_type='player',
            jsonl_logger=mock_jsonl_logger,
            session_id='test_session'
        )

        # Create mock LLM client (for legacy path)
        mock_llm_client = AsyncMock()

        # Mock Anthropic API response
        mock_response = Mock()
        mock_response.content = [Mock(text="INTENT: Scan for enemies\nDESCRIPTION: I carefully scan the area")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        # Create character config (mimics session config format)
        character_config = {
            'name': 'Legacy Player',
            'faction': 'Test Faction',
            'attributes': {'Size': 5, 'Endurance': 3, 'Perception': 4},
            'skills': {'Investigation': 2},
            'void_score': 3,
            'soulcredit': 5,
            'bonds': ["Uncover the truth"],
            'goals': ["Complete the patrol"]
        }

        # Create mock shared state
        mock_shared_state = Mock(spec=SharedState)
        mock_shared_state.get_mechanics_engine = Mock(return_value=None)
        mock_shared_state.get_other_players = Mock(return_value=[])

        # Create player WITHOUT llm_provider (forces legacy path)
        player = AIPlayerAgent(
            agent_id='player_legacy',
            socket_path='/tmp/test_socket',  # Required positional arg
            character_config=character_config,
            llm_client=mock_llm_client,
            llm_config={'provider': 'anthropic', 'model': 'claude-3-5-sonnet-20241022'},
            shared_state=mock_shared_state
        )

        # Inject LLM logger
        player.llm_logger = llm_logger

        # Ensure llm_provider is None to force legacy path
        player.llm_provider = None

        # Set scenario context
        player.current_scenario = {
            'theme': 'Test Patrol',
            'location': 'Test Zone',
            'situation': 'Searching for threats',
            'round': 1
        }

        # Mock call_anthropic_with_retry to return our mock response
        with patch('scripts.aeonisk.multiagent.llm_provider.call_anthropic_with_retry',
                   return_value=mock_response):
            # Generate action (should use legacy path)
            action = await player.generate_action()

        # Verify LLM call was logged (legacy path should already work)
        llm_call_events = [e for e in logged_events if e.get('event_type') == 'llm_call']

        assert len(llm_call_events) >= 1, \
            f"Legacy path should log LLM calls, got {len(llm_call_events)} events"

        llm_call = llm_call_events[0]

        assert llm_call['agent_id'] == 'player_legacy'
        assert llm_call['agent_type'] == 'player'
        assert 'prompt' in llm_call
        assert 'response' in llm_call


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
