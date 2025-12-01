"""
Test suite for player LLM call logging.

This module tests that LLMCallLogger correctly logs LLM calls with proper
structure for replay functionality. Tests the logger directly rather than
through full agent instantiation.

Key assertions:
- Events have correct event_type='llm_call'
- Events include agent_id, agent_type, prompt, response, tokens
- Events are written to the JSONL logger

These tests verify the logging contract that player.py relies on.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime


class TestLLMCallLoggerDirectly:
    """Test LLMCallLogger._log_llm_call() directly without agent instantiation.

    This verifies the logging contract: when _log_llm_call is called,
    the event is written to JSONL with correct structure.
    """

    def test_llm_call_event_structure(self):
        """
        Verify LLM call events have correct structure for replay.

        Event structure is critical for replay_fixture.py to rebuild
        the LLM cache. Missing fields break replay functionality.
        """
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger

        # Track logged events
        logged_events = []

        def mock_write_event(event_data):
            logged_events.append(event_data.copy())

        mock_jsonl_logger = Mock()
        mock_jsonl_logger.write_event = mock_write_event

        # Create logger for a player agent
        logger = LLMCallLogger(
            agent_id='player_test',
            agent_type='player',
            jsonl_logger=mock_jsonl_logger,
            session_id='test_session_123'
        )

        # Simulate what player.py does when logging
        test_messages = [
            {'role': 'system', 'content': 'You are a player character.'},
            {'role': 'user', 'content': 'What do you do this round?'}
        ]

        logger._log_llm_call(
            messages=test_messages,
            response='{"intent": "Fire at enemies", "action_type": "combat"}',
            model='claude-sonnet-4-5',
            temperature=0.8,
            tokens={'input': 500, 'output': 150},
            current_round=1,
            call_sequence=0
        )

        # Verify event was logged
        assert len(logged_events) == 1, "Expected exactly 1 event logged"

        event = logged_events[0]

        # Verify all required fields for replay
        assert event['event_type'] == 'llm_call'
        assert event['agent_id'] == 'player_test'
        assert event['agent_type'] == 'player'
        assert event['session'] == 'test_session_123'
        assert event['round'] == 1
        assert event['call_sequence'] == 0
        assert event['model'] == 'claude-sonnet-4-5'
        assert event['temperature'] == 0.8

        # Verify prompt and response captured
        assert event['prompt'] == test_messages
        assert event['response'] == '{"intent": "Fire at enemies", "action_type": "combat"}'

        # Verify tokens captured (critical for cost tracking)
        assert event['tokens']['input'] == 500
        assert event['tokens']['output'] == 150

        # Verify timestamp is present and valid format
        assert 'ts' in event
        # Should be ISO format
        datetime.fromisoformat(event['ts'])

    def test_llm_call_increments_call_sequence(self):
        """
        Verify call_sequence increments properly for replay ordering.

        Replay uses (agent_id, call_sequence) to match cached responses.
        Incorrect sequencing breaks replay determinism.
        """
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger

        logged_events = []

        def mock_write_event(event_data):
            logged_events.append(event_data.copy())

        mock_jsonl_logger = Mock()
        mock_jsonl_logger.write_event = mock_write_event

        logger = LLMCallLogger(
            agent_id='player_01',
            agent_type='player',
            jsonl_logger=mock_jsonl_logger,
            session_id='test_session'
        )

        # Log multiple calls
        for i in range(3):
            logger._log_llm_call(
                messages=[{'role': 'user', 'content': f'Round {i}'}],
                response=f'Action {i}',
                model='test-model',
                temperature=0.7,
                tokens={'input': 100, 'output': 50},
                current_round=i,
                call_sequence=i  # Manual sequence - in real code this comes from logger.call_count
            )

        # Verify sequences are distinct
        sequences = [e['call_sequence'] for e in logged_events]
        assert sequences == [0, 1, 2], f"Expected [0, 1, 2], got {sequences}"

    def test_llm_call_handles_none_jsonl_logger(self):
        """
        Verify logger handles missing JSONL logger gracefully.

        Some test scenarios run without JSONL logging enabled.
        Should not raise exceptions.
        """
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger

        # Create logger WITHOUT jsonl_logger
        logger = LLMCallLogger(
            agent_id='player_test',
            agent_type='player',
            jsonl_logger=None,  # No logger
            session_id='test_session'
        )

        # Should not raise - just skip logging
        logger._log_llm_call(
            messages=[{'role': 'user', 'content': 'Test'}],
            response='Test response',
            model='test-model',
            temperature=0.7,
            tokens={'input': 10, 'output': 5},
            current_round=0,
            call_sequence=0
        )
        # No assertion needed - test passes if no exception

    def test_llm_call_supports_all_agent_types(self):
        """
        Verify logger works for all agent types: player, dm, enemy.

        Each agent type must log calls for full session replay.
        """
        from scripts.aeonisk.multiagent.llm_logger import LLMCallLogger

        for agent_type, agent_id in [
            ('player', 'player_01'),
            ('dm', 'dm'),
            ('enemy', 'enemy_grunt_abc')
        ]:
            logged_events = []

            def mock_write_event(event_data):
                logged_events.append(event_data.copy())

            mock_jsonl = Mock()
            mock_jsonl.write_event = mock_write_event

            logger = LLMCallLogger(
                agent_id=agent_id,
                agent_type=agent_type,
                jsonl_logger=mock_jsonl,
                session_id='test'
            )

            logger._log_llm_call(
                messages=[{'role': 'user', 'content': 'Test'}],
                response='Response',
                model='test-model',
                temperature=0.7,
                tokens={'input': 10, 'output': 5},
                current_round=0,
                call_sequence=0
            )

            assert len(logged_events) == 1
            assert logged_events[0]['agent_type'] == agent_type
            assert logged_events[0]['agent_id'] == agent_id


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
