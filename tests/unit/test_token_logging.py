"""
Test that LLM token usage is properly tracked in JSONL logs.

TDD Tests - These tests SHOULD FAIL initially until the fix is implemented.
"""
import pytest
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from aeonisk.multiagent.llm_provider import ClaudeProvider, LLMConfig
from aeonisk.multiagent.llm_logger import LLMCallLogger


class TestClaudeProviderTokenLogging:
    """Test that ClaudeProvider logs actual token counts (not zeros)."""

    @pytest.fixture
    def mock_llm_logger(self):
        """Create a mock LLM logger to track logged events."""
        logger = Mock(spec=LLMCallLogger)
        logger._log_llm_call = Mock()
        logger.call_count = 0
        return logger

    @pytest.mark.asyncio
    async def test_generate_structured_logs_actual_tokens(self, mock_llm_logger):
        """
        Test that generate_structured() logs actual token counts when llm_logger is provided.

        EXPECTED BEHAVIOR:
        - When llm_logger kwarg is passed to generate_structured()
        - Extract tokens from Pydantic AI result.usage()
        - Log actual token counts (not zeros)

        CURRENT BUG:
        - generate_structured() doesn't accept llm_logger kwarg
        - Returns only result.output, discarding usage data
        - Callers log tokens={'input': 0, 'output': 0}
        """
        # Arrange
        config = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.7,
            api_key="test_api_key"
        )

        # Mock Pydantic AI agent and result
        mock_result = AsyncMock()
        mock_result.output = {"test": "output"}

        # Create mock usage object with token counts
        mock_usage = Mock()
        mock_usage.input_tokens = 150
        mock_usage.output_tokens = 75
        mock_usage.requests = 1
        mock_result.usage = Mock(return_value=mock_usage)

        # Mock both anthropic client and Pydantic AI Agent
        with patch('anthropic.Anthropic'), \
             patch('pydantic_ai.Agent') as mock_agent_class:

            provider = ClaudeProvider(config=config)

            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            # Act: Call generate_structured with llm_logger
            # This should log tokens internally
            await provider.generate_structured(
                prompt="Test prompt",
                result_type=dict,
                llm_logger=mock_llm_logger,
                current_round=1
            )

        # Assert: _log_llm_call was called with actual token counts
        assert mock_llm_logger._log_llm_call.called, \
            "generate_structured should call llm_logger._log_llm_call when logger is provided"

        call_args = mock_llm_logger._log_llm_call.call_args
        tokens = call_args.kwargs.get('tokens')

        assert tokens is not None, \
            "Tokens should be passed to _log_llm_call"

        assert 'input' in tokens and 'output' in tokens, \
            "Tokens dict should have 'input' and 'output' fields"

        assert tokens['input'] == 150, \
            f"Expected input tokens 150, got {tokens['input']}"

        assert tokens['output'] == 75, \
            f"Expected output tokens 75, got {tokens['output']}"

    @pytest.mark.asyncio
    async def test_generate_structured_without_logger_still_works(self):
        """
        Test that generate_structured() still works when llm_logger is NOT provided.

        This ensures backward compatibility - existing callers that don't pass
        llm_logger should continue to work.
        """
        # Arrange
        config = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.7,
            api_key="test_api_key"
        )

        mock_result = AsyncMock()
        mock_result.output = {"test": "output"}
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_result.usage = Mock(return_value=mock_usage)

        with patch('anthropic.Anthropic'), \
             patch('pydantic_ai.Agent') as mock_agent_class:

            provider = ClaudeProvider(config=config)

            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            # Act: Call without llm_logger (backward compatibility)
            result = await provider.generate_structured(
                prompt="Test prompt",
                result_type=dict
            )

        # Assert: Should return output successfully
        assert result == {"test": "output"}, \
            "generate_structured should still return output when llm_logger not provided"

    @pytest.mark.asyncio
    async def test_generate_structured_extracts_tokens_from_usage(self, mock_llm_logger):
        """
        Test that tokens are extracted from result.usage() (Pydantic AI API).

        This verifies we're using the correct Pydantic AI API to get token counts.
        """
        # Arrange
        config = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.7,
            api_key="test_api_key"
        )

        mock_result = AsyncMock()
        mock_result.output = {"test": "output"}

        # Mock usage object with specific token counts
        mock_usage = Mock()
        mock_usage.input_tokens = 250
        mock_usage.output_tokens = 125
        mock_result.usage = Mock(return_value=mock_usage)

        with patch('anthropic.Anthropic'), \
             patch('pydantic_ai.Agent') as mock_agent_class:

            provider = ClaudeProvider(config=config)

            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            # Act
            await provider.generate_structured(
                prompt="Test prompt",
                result_type=dict,
                llm_logger=mock_llm_logger,
                current_round=2
            )

        # Assert: result.usage() was called to extract token counts
        mock_result.usage.assert_called_once(), \
            "Should call result.usage() to extract token counts"

        # Verify logged tokens match usage data
        call_args = mock_llm_logger._log_llm_call.call_args
        tokens = call_args.kwargs.get('tokens')

        assert tokens['input'] == 250 and tokens['output'] == 125, \
            f"Logged tokens {tokens} should match usage data (250 input, 125 output)"


class TestFixtureTokenLogging:
    """Test that existing fixtures have proper token logging.

    Validates that production fixtures capture token usage for cost analysis.
    """

    @pytest.fixture
    def fixture_events(self):
        """Load events from a test fixture."""
        import json
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sessions" / "replay_test_fresh.jsonl"
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")
        events = []
        with open(fixture_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_player_llm_calls_have_token_counts(self, fixture_events):
        """
        Verify player LLM calls in fixtures have token counts.

        Token logging enables:
        - Cost analysis per player
        - Prompt optimization
        - Replay cost estimation
        """
        import json
        player_llm_calls = [
            e for e in fixture_events
            if e.get('event_type') == 'llm_call' and e.get('agent_type') == 'player'
        ]

        assert len(player_llm_calls) > 0, "Fixture should have player LLM calls"

        # Check that at least some player calls have tokens
        calls_with_tokens = [
            c for c in player_llm_calls
            if 'tokens' in c and c['tokens'].get('input', 0) > 0
        ]

        assert len(calls_with_tokens) > 0, \
            "At least some player LLM calls should have non-zero token counts"

    def test_dm_llm_calls_have_token_counts(self, fixture_events):
        """
        Verify DM LLM calls in fixtures have token counts.

        DM calls are typically the most expensive, so token tracking is critical.
        """
        import json
        dm_llm_calls = [
            e for e in fixture_events
            if e.get('event_type') == 'llm_call' and e.get('agent_type') == 'dm'
        ]

        assert len(dm_llm_calls) > 0, "Fixture should have DM LLM calls"

        # Check that DM calls have tokens
        for call in dm_llm_calls[:3]:  # Check first 3
            assert 'tokens' in call, f"DM LLM call should have tokens field"


# NOTE: Integration tests for ClaudeProvider token extraction are deferred.
# The tests above validate that fixtures contain token data.
# When ClaudeProvider is refactored, add tests here:
# - test_generate_structured_logs_tokens_from_usage()
# - test_generate_text_logs_tokens()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
