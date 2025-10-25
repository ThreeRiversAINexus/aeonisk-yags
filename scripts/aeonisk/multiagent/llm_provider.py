"""
LLM Provider Abstraction for Aeonisk YAGS Multi-Agent System

Supports multiple LLM providers (Claude, GPT-4, local models) with a unified interface.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str  # "claude", "openai", "local"
    model: str
    api_key: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.8
    language: str = "en"  # For prompt selection

    # Provider-specific kwargs
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None

    # Raw response for debugging
    raw_response: Any = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement the generate() method and provide
    a consistent interface for text generation.
    """

    provider_name: str = "base"

    def __init__(self, config: LLMConfig):
        """
        Initialize provider with configuration.

        Args:
            config: LLMConfig with provider settings
        """
        self.config = config
        self.language = config.language

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text from prompt.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt (provider-specific behavior)
            max_tokens: Override default max tokens
            temperature: Override default temperature
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated text and metadata
        """
        pass

    @abstractmethod
    def get_prompt_dir(self) -> str:
        """
        Get the directory name for this provider's prompts.

        Returns:
            Directory name (e.g., "claude", "openai")
        """
        pass

    def get_language(self) -> str:
        """Get the language code for this provider."""
        return self.language

    def set_language(self, language: str):
        """Set the language code for prompt selection."""
        self.language = language
        self.config.language = language


class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude provider.

    Wraps the existing anthropic.Anthropic client for backward compatibility.
    """

    provider_name = "claude"

    def __init__(self, config: LLMConfig):
        """Initialize Claude provider."""
        super().__init__(config)

        # Import anthropic
        try:
            import anthropic
            self.anthropic = anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        # Get API key
        api_key = config.api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found in config or environment variables"
            )

        # Create client
        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info(f"ClaudeProvider initialized with model: {config.model}")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text using Claude API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt (used as system parameter)
            max_tokens: Override default
            temperature: Override default
            **kwargs: Additional parameters for anthropic.messages.create()

        Returns:
            LLMResponse with generated text
        """
        # Use config defaults if not overridden
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        # Prepare API call parameters
        api_params = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }

        # Add system prompt if provided
        if system_prompt:
            api_params["system"] = system_prompt

        # Merge any extra params
        api_params.update(self.config.extra_params)
        api_params.update(kwargs)

        # Call API
        try:
            response = self.client.messages.create(**api_params)

            # Extract text
            text = response.content[0].text.strip()

            # Create standardized response
            return LLMResponse(
                text=text,
                model=self.config.model,
                provider=self.provider_name,
                tokens_used=response.usage.output_tokens if hasattr(response, 'usage') else None,
                finish_reason=response.stop_reason if hasattr(response, 'stop_reason') else None,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

    def get_prompt_dir(self) -> str:
        """Get prompt directory name."""
        return "claude"

    def get_raw_client(self):
        """
        Get the raw Anthropic client for backward compatibility.

        This allows existing code that uses self.llm_client.messages.create()
        to continue working without modification.

        Returns:
            anthropic.Anthropic client instance
        """
        return self.client


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT provider (GPT-4, GPT-3.5, etc.).

    Future implementation for multi-provider comparison.
    """

    provider_name = "openai"

    def __init__(self, config: LLMConfig):
        """Initialize OpenAI provider."""
        super().__init__(config)

        # Import openai
        try:
            import openai
            self.openai = openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        # Get API key
        api_key = config.api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in config or environment variables"
            )

        # Create client
        self.client = openai.OpenAI(api_key=api_key)
        logger.info(f"OpenAIProvider initialized with model: {config.model}")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate text using OpenAI API."""
        # Use config defaults if not overridden
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Call API
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            # Extract text
            text = response.choices[0].message.content.strip()

            # Create standardized response
            return LLMResponse(
                text=text,
                model=self.config.model,
                provider=self.provider_name,
                tokens_used=response.usage.completion_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def get_prompt_dir(self) -> str:
        """Get prompt directory name."""
        return "openai"


class LocalModelProvider(LLMProvider):
    """
    Local model provider (Ollama, llama.cpp, etc.).

    Future implementation for cost-effective testing and privacy.
    """

    provider_name = "local"

    def __init__(self, config: LLMConfig):
        """Initialize local model provider."""
        super().__init__(config)

        # TODO: Implement Ollama/llama.cpp integration
        logger.warning("LocalModelProvider is not yet implemented")
        raise NotImplementedError("Local model support coming soon")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate text using local model."""
        raise NotImplementedError("Local model support coming soon")

    def get_prompt_dir(self) -> str:
        """Get prompt directory name."""
        return "local"


# Provider registry
PROVIDERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "local": LocalModelProvider
}


def create_provider(config: LLMConfig) -> LLMProvider:
    """
    Factory function to create an LLM provider.

    Args:
        config: LLMConfig specifying provider and settings

    Returns:
        Initialized LLMProvider instance

    Raises:
        ValueError: If provider not found
    """
    provider_name = config.provider.lower()

    if provider_name not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(
            f"Unknown provider: {provider_name}. Available: {available}"
        )

    provider_class = PROVIDERS[provider_name]
    return provider_class(config)


def create_claude_provider(
    model: str = "claude-3-5-sonnet-20241022",
    api_key: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.8,
    language: str = "en"
) -> ClaudeProvider:
    """
    Convenience function to create a Claude provider with common defaults.

    Args:
        model: Claude model name
        api_key: Optional API key (uses ANTHROPIC_API_KEY env var if not provided)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        language: Language code for prompts

    Returns:
        Configured ClaudeProvider
    """
    config = LLMConfig(
        provider="claude",
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        language=language
    )
    return ClaudeProvider(config)


# Example usage and testing
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Test Claude provider creation
    try:
        claude = create_claude_provider(language="en")
        print(f"✓ Claude provider created: {claude.config.model}")
        print(f"  Prompt directory: {claude.get_prompt_dir()}")
        print(f"  Language: {claude.get_language()}")

        # Test getting raw client for backward compatibility
        raw_client = claude.get_raw_client()
        print(f"  Raw client available: {raw_client is not None}")

    except Exception as e:
        print(f"✗ Claude provider error: {e}")

    # Test OpenAI provider (will likely fail without API key, that's expected)
    try:
        config = LLMConfig(provider="openai", model="gpt-4", api_key="dummy")
        openai_provider = create_provider(config)
        print(f"✓ OpenAI provider created: {openai_provider.config.model}")
    except Exception as e:
        print(f"  OpenAI provider (expected to fail without key): {type(e).__name__}")

    # Test local provider (not implemented, will fail)
    try:
        config = LLMConfig(provider="local", model="llama-2-7b")
        local_provider = create_provider(config)
    except NotImplementedError as e:
        print(f"  Local provider (not yet implemented): OK")
