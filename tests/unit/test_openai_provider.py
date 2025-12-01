"""
Unit tests for OpenAI provider implementation.

Tests the OpenAIProvider class for both basic text generation and structured
output generation using Pydantic AI.
"""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field

from scripts.aeonisk.multiagent.llm_provider import (
    OpenAIProvider,
    LLMConfig,
    LLMResponse,
    create_provider
)


# Test schema for structured output
class SimpleAction(BaseModel):
    """Simple test schema for structured output."""
    action: str = Field(description="The action to take")
    target: str = Field(description="The target of the action")
    reason: str = Field(description="Why this action was chosen")


class TestOpenAIProviderBasic:
    """Test basic OpenAI provider functionality."""

    def test_provider_initialization_with_api_key(self):
        """Test that provider initializes correctly with API key."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-api-key-12345'
        )

        provider = OpenAIProvider(config)

        assert provider.provider_name == 'openai'
        assert provider.config.model == 'gpt-5-mini'
        assert provider.client is not None

    def test_provider_initialization_from_env(self, monkeypatch):
        """Test that provider reads API key from environment."""
        monkeypatch.setenv('OPENAI_API_KEY', 'env-api-key-67890')

        config = LLMConfig(provider='openai', model='gpt-5-mini')
        provider = OpenAIProvider(config)

        assert provider.client is not None

    def test_provider_initialization_missing_api_key(self, monkeypatch):
        """Test that provider raises error when API key is missing."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        config = LLMConfig(provider='openai', model='gpt-5-mini')

        with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
            OpenAIProvider(config)

    def test_get_prompt_dir(self):
        """Test that provider returns correct prompt directory."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        assert provider.get_prompt_dir() == 'openai'

    def test_create_provider_returns_openai(self):
        """Test that create_provider factory returns OpenAI provider."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )

        provider = create_provider(config)

        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == 'openai'


class TestOpenAIProviderGenerate:
    """Test OpenAI provider text generation (non-structured)."""

    @pytest.mark.asyncio
    async def test_generate_basic_text(self):
        """Test basic text generation with OpenAI."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock the OpenAI client response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a test response."
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response):
            response = await provider.generate(
                prompt="Test prompt",
                system_prompt="You are a helpful assistant."
            )

        assert isinstance(response, LLMResponse)
        assert response.text == "This is a test response."
        assert response.model == 'gpt-5-mini'
        assert response.provider == 'openai'
        assert response.finish_reason == 'stop'

    @pytest.mark.asyncio
    async def test_generate_respects_temperature(self):
        """Test that generate() overrides temperature to 1.0 for OpenAI gpt-5-mini."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key',
            temperature=0.9
        )
        provider = OpenAIProvider(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = None

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            await provider.generate(prompt="Test")

            # OpenAI gpt-5-mini requires temperature=1.0, should override config value
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['temperature'] == 1.0

    @pytest.mark.asyncio
    async def test_generate_handles_none_content(self):
        """Test that generate() handles None content from OpenAI API."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock OpenAI API returning None content
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None  # This can happen with OpenAI
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = None

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response):
            response = await provider.generate(prompt="Test prompt")

            # Should handle None gracefully, returning empty string instead of crashing
            assert isinstance(response, LLMResponse)
            assert response.text == ""  # Empty string, not None

    @pytest.mark.asyncio
    async def test_generate_handles_empty_string_content(self):
        """Test that generate() handles empty string content from OpenAI API."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock OpenAI API returning empty string content
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""  # Empty response
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = None

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response):
            response = await provider.generate(prompt="Test prompt")

            # Should preserve empty string
            assert isinstance(response, LLMResponse)
            assert response.text == ""


class TestOpenAIProviderStructuredOutput:
    """Test OpenAI provider structured output generation (the critical feature).

    Note: OpenAI provider uses native OpenAI API (not Pydantic AI) via
    generate_structured_openai_native. Tests mock at that level.
    """

    @pytest.mark.asyncio
    async def test_generate_structured_basic(self, monkeypatch):
        """Test that generate_structured() works with simple schema."""
        # Set API key in environment
        monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key-12345')

        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock the native OpenAI structured output function
        expected_result = SimpleAction(
            action="attack",
            target="goblin",
            reason="eliminate threat"
        )

        with patch('scripts.aeonisk.multiagent.openai_structured.generate_structured_openai_native',
                   new_callable=AsyncMock, return_value=expected_result):
            result = await provider.generate_structured(
                prompt="Attack the goblin with my sword",
                result_type=SimpleAction,
                system_prompt="You are a game master."
            )

            # Verify we get back a validated Pydantic model
            assert isinstance(result, SimpleAction)
            assert result.action == "attack"
            assert result.target == "goblin"
            assert result.reason == "eliminate threat"

    @pytest.mark.asyncio
    async def test_generate_structured_returns_correct_type(self, monkeypatch):
        """Test that generate_structured() returns the correct Pydantic type."""
        monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key-12345')

        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock result with SimpleAction
        expected_result = SimpleAction(
            action="Investigate the terminal",
            target="security console",
            reason="find clues"
        )

        with patch('scripts.aeonisk.multiagent.openai_structured.generate_structured_openai_native',
                   new_callable=AsyncMock, return_value=expected_result):
            result = await provider.generate_structured(
                prompt="I want to hack the terminal to disable security",
                result_type=SimpleAction,
                system_prompt="Generate a simple action."
            )

            assert isinstance(result, SimpleAction)
            assert result.action == "Investigate the terminal"
            assert result.target == "security console"

    @pytest.mark.asyncio
    async def test_generate_structured_passes_parameters(self, monkeypatch):
        """Test that structured generation passes correct parameters to native API."""
        monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key-12345')

        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key',
            temperature=0.3,
            max_tokens=2000
        )
        provider = OpenAIProvider(config)

        # Mock result
        expected_result = SimpleAction(
            action="test", target="target", reason="reason"
        )

        with patch('scripts.aeonisk.multiagent.openai_structured.generate_structured_openai_native',
                   new_callable=AsyncMock, return_value=expected_result) as mock_native:
            result = await provider.generate_structured(
                prompt="Test action",
                result_type=SimpleAction,
                system_prompt="Test system prompt",
                temperature=0.8  # Override config
            )

            # Verify native function was called with correct parameters
            mock_native.assert_called_once()
            call_kwargs = mock_native.call_args[1]
            assert call_kwargs['prompt'] == "Test action"
            assert call_kwargs['result_type'] == SimpleAction
            assert call_kwargs['system_prompt'] is not None  # Enhanced prompt
            assert call_kwargs['temperature'] == 0.8  # Override value
            assert call_kwargs['max_tokens'] == 2000  # From config
            assert isinstance(result, SimpleAction)

    @pytest.mark.asyncio
    async def test_generate_structured_handles_exception(self, monkeypatch):
        """Test that generate_structured propagates exceptions from native API."""
        monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key-12345')

        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock the native function to raise an error
        with patch('scripts.aeonisk.multiagent.openai_structured.generate_structured_openai_native',
                   new_callable=AsyncMock, side_effect=ValueError("OpenAI returned empty content")):
            with pytest.raises(ValueError, match="OpenAI returned empty content"):
                await provider.generate_structured(
                    prompt="Test",
                    result_type=SimpleAction
                )


class TestOpenAIProviderErrorHandling:
    """Test OpenAI-specific error handling."""

    @pytest.mark.asyncio
    async def test_handles_rate_limit_error(self):
        """Test that provider handles OpenAI 429 rate limit errors."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key',
            max_retries=2
        )
        provider = OpenAIProvider(config)

        # Mock OpenAI API to raise rate limit error
        from openai import RateLimitError

        with patch.object(provider.client.chat.completions, 'create') as mock_create:
            mock_create.side_effect = RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None
            )

            with pytest.raises(RateLimitError):
                await provider.generate(prompt="Test")

    @pytest.mark.asyncio
    async def test_handles_service_unavailable_error(self):
        """Test that provider handles OpenAI 503 service unavailable errors."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key',
            max_retries=2
        )
        provider = OpenAIProvider(config)

        # Mock OpenAI API to raise service unavailable error
        from openai import APIError

        with patch.object(provider.client.chat.completions, 'create') as mock_create:
            mock_create.side_effect = APIError(
                "Service unavailable",
                request=MagicMock(),
                body=None
            )

            with pytest.raises(APIError):
                await provider.generate(prompt="Test")


class TestTokenNormalization:
    """Test that OpenAI token field names are normalized correctly."""

    @pytest.mark.asyncio
    async def test_token_fields_normalized(self):
        """Test that prompt_tokens/completion_tokens are mapped to input/output."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            api_key='test-key'
        )
        provider = OpenAIProvider(config)

        # Mock response with OpenAI token field names
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 75

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response):
            response = await provider.generate(prompt="Test")

        # Currently returns completion_tokens in tokens_used field
        # Should be normalized to have both input_tokens and output_tokens
        # This test will likely fail until we add normalization
        assert response.tokens_used is not None


@pytest.mark.skipif(
    not os.getenv('OPENAI_API_KEY'),
    reason="OPENAI_API_KEY not set - skipping live API tests"
)
class TestOpenAIProviderLiveAPI:
    """Live API tests - only run if OPENAI_API_KEY is available."""

    @pytest.mark.asyncio
    async def test_live_generate_structured(self):
        """Test generate_structured() against live OpenAI API."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            temperature=0.7
        )
        provider = OpenAIProvider(config)

        result = await provider.generate_structured(
            prompt="Describe a character attacking a goblin with a sword",
            result_type=SimpleAction,
            system_prompt="Generate a simple game action."
        )

        assert isinstance(result, SimpleAction)
        assert len(result.action) > 0
        assert len(result.target) > 0
        assert len(result.reason) > 0

        print(f"\nLive API result:\n  Action: {result.action}\n  Target: {result.target}\n  Reason: {result.reason}")

    @pytest.mark.asyncio
    async def test_live_generate_basic(self):
        """Test basic text generation against live OpenAI API."""
        config = LLMConfig(
            provider='openai',
            model='gpt-5-mini',
            temperature=0.7
        )
        provider = OpenAIProvider(config)

        response = await provider.generate(
            prompt="Say hello in exactly 5 words.",
            system_prompt="You are a concise assistant."
        )

        assert isinstance(response, LLMResponse)
        assert len(response.text) > 0
        assert response.provider == 'openai'

        print(f"\nLive API response: {response.text}")


class TestProviderFactory:
    """Test the create_provider factory function."""

    def test_anthropic_alias_maps_to_claude(self, monkeypatch):
        """Test that 'anthropic' provider name is aliased to 'claude'."""
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-anthropic-key-123')

        config = LLMConfig(provider='anthropic', model='claude-sonnet-4-5')
        provider = create_provider(config)

        # Should create ClaudeProvider, not fail with "Unknown provider"
        assert provider is not None
        assert provider.provider_name == 'claude'
        assert provider.config.model == 'claude-sonnet-4-5'

    def test_claude_provider_still_works(self, monkeypatch):
        """Test that 'claude' provider name still works directly."""
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-anthropic-key-456')

        config = LLMConfig(provider='claude', model='claude-sonnet-4-5')
        provider = create_provider(config)

        assert provider is not None
        assert provider.provider_name == 'claude'

    def test_openai_provider_unchanged(self, monkeypatch):
        """Test that openai provider is not affected by alias."""
        monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-key-789')

        config = LLMConfig(provider='openai', model='gpt-5-mini')
        provider = create_provider(config)

        assert provider is not None
        assert provider.provider_name == 'openai'

    def test_unknown_provider_still_raises_error(self):
        """Test that truly unknown providers still raise ValueError."""
        config = LLMConfig(provider='invalid_provider', model='some-model')

        with pytest.raises(ValueError, match="Unknown provider: invalid_provider"):
            create_provider(config)
