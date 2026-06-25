"""
Unit tests for BatchProxyProvider.

Tests the batch proxy LLM provider integration with UnifiedAIClient.
Uses mocking to avoid actual API calls during testing.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from scripts.aeonisk.multiagent.llm_provider import LLMConfig
from scripts.aeonisk.multiagent.llm_batch_provider import BatchProxyProvider
from pydantic import BaseModel


# Test Pydantic model for structured output tests
class SampleResponse(BaseModel):
    """Simple test response model."""
    message: str
    count: int


@pytest.fixture
def batch_provider_config():
    """Create test config for batch provider."""
    return LLMConfig(
        provider="batch_proxy",
        model="gpt-5-mini",
        temperature=0.7,
        max_tokens=1000,
        extra_params={
            'underlying_provider': 'openai',
            'use_proxy': True,
            'proxy_url': 'http://localhost:8000',
            'proxy_priority': 'normal',
            'proxy_strategy': 'auto'
        }
    )


@pytest.fixture
def batch_provider(batch_provider_config):
    """Create BatchProxyProvider instance with mocked client."""
    with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient'):
        provider = BatchProxyProvider(batch_provider_config)
        provider.client = Mock()  # Replace with mock
        return provider


class TestBatchProxyProviderInit:
    """Test provider initialization."""

    def test_init_with_openai_backend(self, batch_provider_config):
        """Test initialization with OpenAI as underlying provider."""
        with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient') as mock_client:
            provider = BatchProxyProvider(batch_provider_config)

            assert provider.underlying_provider == 'openai'
            assert provider.config.model == 'gpt-5-mini'

            # Verify UnifiedAIClient was called with correct params
            mock_client.assert_called_once_with(
                provider='openai',
                use_proxy=True,
                proxy_url='http://localhost:8000',
                proxy_priority='normal',
                proxy_strategy='auto',
                proxy_timeout=None,
                no_fallback=False,
            )

    def test_init_with_anthropic_backend(self):
        """Test initialization with Anthropic as underlying provider."""
        config = LLMConfig(
            provider="batch_proxy",
            model="claude-sonnet-4-5",
            extra_params={
                'underlying_provider': 'anthropic',
                'use_proxy': True,
                'proxy_url': 'http://localhost:8000',
            }
        )

        with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient') as mock_client:
            provider = BatchProxyProvider(config)

            assert provider.underlying_provider == 'anthropic'
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs['provider'] == 'anthropic'

    def test_init_defaults_to_proxy_enabled(self):
        """Test that use_proxy defaults to True for batch_proxy provider."""
        config = LLMConfig(
            provider="batch_proxy",
            model="gpt-5-mini",
            extra_params={
                'underlying_provider': 'openai',
                # use_proxy not specified - should default to True
            }
        )

        with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient') as mock_client:
            provider = BatchProxyProvider(config)

            call_kwargs = mock_client.call_args[1]
            assert call_kwargs['use_proxy'] is True


class TestBatchProxyProviderGenerate:
    """Test text generation via batch proxy."""

    @pytest.mark.asyncio
    async def test_generate_success(self, batch_provider):
        """Test successful text generation."""
        # Mock client response
        batch_provider.client.chat_completion.return_value = "Generated response text"

        # Call generate
        response = await batch_provider.generate(
            prompt="Test prompt",
            system_prompt="System instructions",
            max_tokens=500,
            temperature=0.8
        )

        # Verify response
        assert response.text == "Generated response text"
        assert response.model == "gpt-5-mini"
        assert response.provider == "batch_proxy:openai"
        assert response.finish_reason == "stop"

        # Verify client was called correctly
        batch_provider.client.chat_completion.assert_called_once()
        call_kwargs = batch_provider.client.chat_completion.call_args[1]
        assert call_kwargs['model'] == 'gpt-5-mini'
        assert call_kwargs['temperature'] == 0.8
        assert call_kwargs['max_tokens'] == 500
        assert len(call_kwargs['messages']) == 2
        assert call_kwargs['messages'][0]['role'] == 'system'
        assert call_kwargs['messages'][1]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self, batch_provider):
        """Test generation without system prompt."""
        batch_provider.client.chat_completion.return_value = "Response"

        response = await batch_provider.generate(prompt="Test prompt")

        # Should only have user message (no system message)
        call_kwargs = batch_provider.client.chat_completion.call_args[1]
        messages = call_kwargs['messages']
        assert len(messages) == 1
        assert messages[0]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_generate_uses_config_defaults(self, batch_provider):
        """Test that generate uses config defaults when params not provided."""
        batch_provider.client.chat_completion.return_value = "Response"

        # Don't specify max_tokens or temperature
        await batch_provider.generate(prompt="Test")

        call_kwargs = batch_provider.client.chat_completion.call_args[1]
        assert call_kwargs['max_tokens'] == 1000  # From config
        assert call_kwargs['temperature'] == 0.7  # From config

    @pytest.mark.asyncio
    async def test_generate_error_propagation(self, batch_provider):
        """Test that errors from client are propagated."""
        batch_provider.client.chat_completion.side_effect = Exception("Proxy error")

        with pytest.raises(Exception, match="Proxy error"):
            await batch_provider.generate(prompt="Test")


class TestBatchProxyProviderStructuredOutput:
    """Test structured output generation via batch proxy."""

    @pytest.mark.asyncio
    async def test_generate_structured_success(self, batch_provider):
        """Test successful structured output generation."""
        # Mock response as valid JSON
        json_response = json.dumps({"message": "Hello", "count": 42})
        batch_provider.client.chat_completion.return_value = json_response

        # Call generate_structured
        result = await batch_provider.generate_structured(
            prompt="Test prompt",
            result_type=SampleResponse,
            system_prompt="System instructions"
        )

        # Verify result is validated Pydantic instance
        assert isinstance(result, SampleResponse)
        assert result.message == "Hello"
        assert result.count == 42

    @pytest.mark.asyncio
    async def test_generate_structured_strips_markdown(self, batch_provider):
        """Test that markdown code blocks are stripped from JSON."""
        # Response wrapped in markdown
        json_response = '```json\n{"message": "Test", "count": 10}\n```'
        batch_provider.client.chat_completion.return_value = json_response

        result = await batch_provider.generate_structured(
            prompt="Test",
            result_type=SampleResponse
        )

        assert result.message == "Test"
        assert result.count == 10

    @pytest.mark.asyncio
    async def test_generate_structured_invalid_json(self, batch_provider):
        """Test error handling for invalid JSON response after all retries."""
        batch_provider.client.chat_completion.return_value = "Not valid JSON"

        with pytest.raises(ValueError, match="Failed to generate valid"):
            await batch_provider.generate_structured(
                prompt="Test",
                result_type=SampleResponse
            )

    @pytest.mark.asyncio
    async def test_generate_structured_schema_mismatch(self, batch_provider):
        """Test error handling for JSON that doesn't match schema."""
        # Valid JSON but wrong schema
        json_response = json.dumps({"wrong_field": "value"})
        batch_provider.client.chat_completion.return_value = json_response

        with pytest.raises(Exception):  # Pydantic validation error
            await batch_provider.generate_structured(
                prompt="Test",
                result_type=SampleResponse
            )

    @pytest.mark.asyncio
    async def test_generate_structured_with_logger(self, batch_provider):
        """Test token logging when llm_logger provided."""
        json_response = json.dumps({"message": "Test", "count": 5})
        batch_provider.client.chat_completion.return_value = json_response

        # Mock logger
        mock_logger = Mock()
        mock_logger.call_count = 3

        result = await batch_provider.generate_structured(
            prompt="Test prompt",
            result_type=SampleResponse,
            llm_logger=mock_logger,
            current_round=2
        )

        # Verify logger was called with expected fields
        mock_logger._log_llm_call.assert_called_once()
        call_kwargs = mock_logger._log_llm_call.call_args[1]
        assert call_kwargs['current_round'] == 2
        assert call_kwargs['call_sequence'] == 3
        assert call_kwargs['model'] == 'gpt-5-mini'
        assert 'tokens' in call_kwargs
        assert call_kwargs['tokens']['total'] > 0  # Estimated tokens


class TestBatchProxyProviderHelpers:
    """Test helper methods."""

    def test_get_prompt_dir_openai(self, batch_provider):
        """Test prompt directory for OpenAI backend."""
        assert batch_provider.get_prompt_dir() == "openai"

    def test_get_prompt_dir_anthropic(self):
        """Test prompt directory for Anthropic backend."""
        config = LLMConfig(
            provider="batch_proxy",
            model="claude-sonnet-4-5",
            extra_params={'underlying_provider': 'anthropic'}
        )

        with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient'):
            provider = BatchProxyProvider(config)
            assert provider.get_prompt_dir() == "anthropic"

    def test_health_check_delegates_to_client(self, batch_provider):
        """Test that health_check delegates to UnifiedAIClient."""
        batch_provider.client.health_check.return_value = {
            'reachable': True,
            'status': 'healthy',
            'response_time_ms': 50.0
        }

        result = batch_provider.health_check()

        assert result['reachable'] is True
        assert result['status'] == 'healthy'
        batch_provider.client.health_check.assert_called_once()


class TestFactoryFunction:
    """Test create_batch_proxy_provider factory function."""

    @patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient')
    def test_factory_creates_provider(self, mock_client):
        """Test factory function creates configured provider."""
        from scripts.aeonisk.multiagent.llm_batch_provider import create_batch_proxy_provider

        provider = create_batch_proxy_provider(
            underlying_provider='openai',
            model='gpt-5-mini',
            proxy_url='http://test:9000',
            temperature=0.5,
            max_tokens=2000
        )

        assert provider.config.model == 'gpt-5-mini'
        assert provider.config.temperature == 0.5
        assert provider.config.max_tokens == 2000
        assert provider.underlying_provider == 'openai'

    @patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient')
    def test_factory_defaults(self, mock_client):
        """Test factory function uses sensible defaults."""
        from scripts.aeonisk.multiagent.llm_batch_provider import create_batch_proxy_provider

        provider = create_batch_proxy_provider(
            underlying_provider='anthropic',
            model='claude-sonnet-4-5'
        )

        # Verify defaults
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs['use_proxy'] is True
        assert call_kwargs['proxy_url'] == 'http://localhost:8000'
        assert call_kwargs['proxy_priority'] == 'normal'
        assert call_kwargs['proxy_strategy'] == 'auto'
        assert call_kwargs['proxy_timeout'] is None
        assert call_kwargs['no_fallback'] is False

    def test_init_forced_batch_disables_direct_fallback(self):
        """Forced batch strategy should not silently fall back to direct API."""
        config = LLMConfig(
            provider="batch_proxy",
            model="gpt-5-mini",
            extra_params={
                'underlying_provider': 'openai',
                'use_proxy': True,
                'proxy_url': 'http://localhost:8000',
                'proxy_strategy': 'batch',
                'proxy_timeout': 60,
            }
        )

        with patch('scripts.aeonisk.multiagent.llm_batch_provider.UnifiedAIClient') as mock_client:
            BatchProxyProvider(config)

        call_kwargs = mock_client.call_args[1]
        assert call_kwargs['proxy_strategy'] == 'batch'
        assert call_kwargs['proxy_timeout'] == 60
        assert call_kwargs['no_fallback'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
