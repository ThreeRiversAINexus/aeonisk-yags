"""
LLM Provider Abstraction for Aeonisk YAGS Multi-Agent System

Supports multiple LLM providers (Claude, GPT-4, local models) with a unified interface.
"""

import os
import logging
import time
import random
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Global rate limiter for concurrent API calls
class APIRateLimiter:
    """
    Global rate limiter to prevent too many concurrent API calls.

    Uses a semaphore to limit concurrent requests and optional minimum delay
    between requests to prevent thundering herd.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self, max_concurrent: int = 5, min_request_interval: float = 0.2):
        """
        Initialize rate limiter with concurrency and timing constraints.

        Args:
            max_concurrent: Maximum concurrent API calls
            min_request_interval: Minimum seconds between request starts
        """
        if not self._initialized:
            self._semaphore = asyncio.Semaphore(max_concurrent)
            self._min_interval = min_request_interval
            self._last_request_time = 0.0
            self._initialized = True
            logger.info(f"APIRateLimiter initialized: max_concurrent={max_concurrent}, min_interval={min_request_interval}s")

    async def acquire(self):
        """Acquire permission to make an API call."""
        if not self._initialized:
            await self.initialize()

        # Wait for semaphore slot
        await self._semaphore.acquire()

        # Enforce minimum interval between requests
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                wait_time = self._min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    def release(self):
        """Release API call permission."""
        if self._initialized:
            self._semaphore.release()


# Global rate limiter instance
_rate_limiter = APIRateLimiter()


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str  # "claude", "openai", "local"
    model: str
    api_key: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.8
    language: str = "en"  # For prompt selection

    # Retry/backoff configuration
    max_retries: int = 3  # Number of retry attempts for overloaded/rate limit errors
    base_delay: float = 2.0  # Base delay in seconds for exponential backoff (increased from 1.0)
    max_delay: float = 120.0  # Maximum delay between retries (increased from 60.0)
    jitter: bool = True  # Add randomness to prevent thundering herd

    # Rate limiting (global across all agents)
    # Tuned for multi-agent sessions (3 PCs + 2 enemies + DM = 6 agents)
    # More aggressive to prevent Anthropic API 500 Overloaded errors
    use_rate_limiter: bool = True  # Enable global rate limiting
    max_concurrent_requests: int = 3  # Max concurrent API calls across all agents (reduced from 5)
    min_request_interval: float = 0.5  # Minimum seconds between request starts (increased from 0.2)

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

        # Initialize rate limiter if enabled
        if config.use_rate_limiter:
            # Schedule rate limiter initialization in event loop
            # This will be initialized on first use if event loop doesn't exist yet
            self._rate_limiter_initialized = False

        logger.info(
            f"ClaudeProvider initialized: model={config.model}, "
            f"max_retries={config.max_retries}, rate_limit={config.use_rate_limiter}"
        )

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with optional jitter.

        Args:
            attempt: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: delay = base_delay * (2 ^ attempt)
        delay = self.config.base_delay * (2 ** attempt)

        # Cap at max_delay
        delay = min(delay, self.config.max_delay)

        # Add jitter if enabled (randomize 50-100% of delay)
        if self.config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Check if an error is retryable (overloaded/rate limit).

        Args:
            error: Exception from API call

        Returns:
            True if error is retryable
        """
        # Check for Anthropic API errors
        if hasattr(error, 'status_code'):
            # 500: Internal server error / Overloaded
            # 529: Overloaded (explicit)
            return error.status_code in [500, 529]

        # Check error message for overloaded indicators
        error_str = str(error).lower()
        return 'overloaded' in error_str or 'rate limit' in error_str

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text using Claude API with rate limiting and exponential backoff retry.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt (used as system parameter)
            max_tokens: Override default
            temperature: Override default
            **kwargs: Additional parameters for anthropic.messages.create()

        Returns:
            LLMResponse with generated text
        """
        # Initialize rate limiter on first use if needed
        if self.config.use_rate_limiter and not self._rate_limiter_initialized:
            await _rate_limiter.initialize(
                max_concurrent=self.config.max_concurrent_requests,
                min_request_interval=self.config.min_request_interval
            )
            self._rate_limiter_initialized = True

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

        # Acquire rate limiter slot if enabled
        if self.config.use_rate_limiter:
            await _rate_limiter.acquire()

        try:
            # Retry loop with exponential backoff
            last_error = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = self.client.messages.create(**api_params)

                    # Extract text
                    text = response.content[0].text.strip()

                    # Log successful retry if not first attempt
                    if attempt > 0:
                        logger.info(f"✓ Claude API call succeeded after {attempt} retries")

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
                    last_error = e

                    # Check if error is retryable
                    if not self._is_retryable_error(e):
                        # Non-retryable error, fail immediately
                        logger.error(f"Claude API error (non-retryable): {e}")
                        raise

                    # Check if we have retries left
                    if attempt >= self.config.max_retries:
                        # Out of retries
                        logger.error(f"Claude API error after {attempt} retries: {e}")
                        raise

                    # Calculate backoff delay
                    delay = self._calculate_backoff_delay(attempt)

                    # Log retry attempt
                    logger.warning(
                        f"Claude API overloaded (attempt {attempt + 1}/{self.config.max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )

                    # Wait before retry
                    await asyncio.sleep(delay)  # Use asyncio.sleep for async compatibility

            # Should never reach here, but just in case
            raise last_error or Exception("Unknown error in retry loop")

        finally:
            # Always release rate limiter slot
            if self.config.use_rate_limiter:
                _rate_limiter.release()

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

    async def generate_structured(
        self,
        prompt: str,
        result_type: type,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ):
        """
        Generate structured output validated against a Pydantic model.

        Uses Pydantic AI for type-safe LLM responses. This eliminates keyword
        detection and text parsing in favor of validated structured output.

        Args:
            prompt: User prompt
            result_type: Pydantic BaseModel class to validate against
            system_prompt: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature
            **kwargs: Additional parameters

        Returns:
            Validated Pydantic model instance

        Example:
            ```python
            from schemas.action_resolution import ActionResolution

            resolution = await provider.generate_structured(
                prompt="Resolve this action: ...",
                result_type=ActionResolution,
                system_prompt="You are a game master..."
            )
            # resolution is a validated ActionResolution instance
            print(resolution.narration)
            print(resolution.effects.void_changes)
            ```
        """
        try:
            from pydantic_ai import Agent
        except ImportError:
            raise ImportError(
                "pydantic-ai not installed. Install with: pip install pydantic-ai"
            )

        # Use config defaults if not overridden
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Create Pydantic AI agent with output type
        # Note: pydantic-ai 1.9.0+ uses 'output_type' not 'result_type'
        agent = Agent(
            f'anthropic:{self.config.model}',
            output_type=result_type,
            system_prompt=system_prompt or ""
        )

        # Initialize rate limiter if needed
        if self.config.use_rate_limiter and not self._rate_limiter_initialized:
            await _rate_limiter.initialize(
                max_concurrent=self.config.max_concurrent_requests,
                min_request_interval=self.config.min_request_interval
            )
            self._rate_limiter_initialized = True

        # Acquire rate limiter slot if enabled
        if self.config.use_rate_limiter:
            await _rate_limiter.acquire()

        try:
            # Retry loop with exponential backoff
            last_error = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    # Run Pydantic AI agent
                    result = await agent.run(
                        prompt,
                        model_settings={
                            'max_tokens': max_tokens,
                            'temperature': temperature,
                            **kwargs
                        }
                    )

                    # Log successful retry if not first attempt
                    if attempt > 0:
                        logger.info(f"✓ Structured output succeeded after {attempt} retries")

                    # Return validated Pydantic model instance
                    # Note: pydantic-ai 1.9.0 uses 'output' not 'data' or 'response'
                    # result.output contains the validated Pydantic model
                    # result.response contains the raw ModelResponse
                    return result.output

                except Exception as e:
                    last_error = e

                    # Check if error is retryable
                    if not self._is_retryable_error(e):
                        # Non-retryable error, fail immediately
                        logger.error(f"Structured output error (non-retryable): {e}")
                        raise

                    # Check if we have retries left
                    if attempt >= self.config.max_retries:
                        # Out of retries
                        logger.error(f"Structured output error after {attempt} retries: {e}")
                        raise

                    # Calculate backoff delay
                    delay = self._calculate_backoff_delay(attempt)

                    # Log retry attempt
                    logger.warning(
                        f"Structured output failed (attempt {attempt + 1}/{self.config.max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )

                    # Wait before retry
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            raise last_error or Exception("Unknown error in retry loop")

        finally:
            # Always release rate limiter slot
            if self.config.use_rate_limiter:
                _rate_limiter.release()


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
    model: str = "claude-sonnet-4-5",
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


# Wrapper for backward compatibility with existing code
async def call_anthropic_with_retry(
    client,
    model: str,
    messages: list,
    max_tokens: int = 4000,
    temperature: float = 0.8,
    system: Optional[str] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    use_rate_limiter: bool = True,
    **kwargs
):
    """
    Wrapper for anthropic.messages.create() with retry logic and rate limiting.

    This allows existing code using raw Anthropic clients to benefit from
    retry/backoff logic without refactoring to ClaudeProvider.

    Args:
        client: anthropic.Anthropic client instance
        model: Model name
        messages: Messages list
        max_tokens: Max tokens to generate
        temperature: Sampling temperature
        system: Optional system prompt
        max_retries: Number of retry attempts
        base_delay: Base delay for exponential backoff
        max_delay: Maximum delay between retries
        use_rate_limiter: Use global rate limiter
        **kwargs: Additional params for messages.create()

    Returns:
        Response from messages.create()
    """
    # Initialize rate limiter if enabled
    if use_rate_limiter and not _rate_limiter._initialized:
        await _rate_limiter.initialize()

    # Acquire rate limiter slot if enabled
    if use_rate_limiter:
        await _rate_limiter.acquire()

    try:
        # Build API params
        api_params = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        if system:
            api_params["system"] = system
        api_params.update(kwargs)

        # Retry loop
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = client.messages.create(**api_params)

                # Log successful retry if not first attempt
                if attempt > 0:
                    logger.info(f"✓ Anthropic API call succeeded after {attempt} retries")

                return response

            except Exception as e:
                last_error = e

                # Check if retryable (500/529 or "overloaded"/"rate limit" in message)
                is_retryable = False
                if hasattr(e, 'status_code') and e.status_code in [500, 529]:
                    is_retryable = True
                elif 'overloaded' in str(e).lower() or 'rate limit' in str(e).lower():
                    is_retryable = True

                if not is_retryable:
                    logger.error(f"Anthropic API error (non-retryable): {e}")
                    raise

                if attempt >= max_retries:
                    logger.error(f"Anthropic API error after {attempt} retries: {e}")
                    raise

                # Calculate backoff with jitter
                delay = base_delay * (2 ** attempt)
                delay = min(delay, max_delay)
                delay = delay * (0.5 + random.random() * 0.5)  # Jitter

                logger.warning(
                    f"Anthropic API overloaded (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay:.2f}s: {e}"
                )

                await asyncio.sleep(delay)

        raise last_error or Exception("Unknown error in retry loop")

    finally:
        if use_rate_limiter:
            _rate_limiter.release()


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
