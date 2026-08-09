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
from dataclasses import dataclass, fields

# Import custom log levels
from . import custom_log_levels  # noqa: F401

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
            logger.llm(f"APIRateLimiter initialized: max_concurrent={max_concurrent}, min_interval={min_request_interval}s")

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

# Supported models per provider
# Used for validation and helpful error messages
SUPPORTED_MODELS = {
    'anthropic': {
        'models': [
            'claude-opus-4-6',
            'claude-sonnet-4-5',
            'claude-sonnet-4-5-20250929',
            'claude-3-5-sonnet-20241022',
            'claude-3-5-haiku-20241022',
            'claude-3-opus-20240229',
        ],
        'recommended': 'claude-sonnet-4-5',
        'pricing_url': 'https://www.anthropic.com/pricing'
    },
    'openai': {
        'models': [
            # GPT-5 family (2025+)
            'gpt-5.2-2025-12-11',
            'gpt-5.1',
            'gpt-5',
            'gpt-5-mini',
            'gpt-5-nano',
            # GPT-4 family
            'gpt-4.1',
            'gpt-4.1-mini',
            'gpt-4.1-nano',
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo-preview',
            # O-series (reasoning)
            'o1',
            'o3',
            'o3-mini',
            'o4-mini',
        ],
        'recommended': 'gpt-5-mini',
        'pricing_url': 'https://openai.com/pricing'
    },
    'grok': {
        'models': ['grok-4-latest', 'grok-3', 'grok-3-mini'],
        'recommended': 'grok-4-latest',
        'pricing_url': 'https://x.ai/api/pricing'
    },
    'gemini': {
        'models': ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
        'recommended': 'gemini-2.5-pro',
        'pricing_url': 'https://ai.google.dev/pricing'
    },
    'deepinfra': {
        'models': [
            'deepseek-ai/DeepSeek-V3.2',
            'zai-org/GLM-5',
            'moonshotai/Kimi-K2.5',
            'NousResearch/Hermes-3-Llama-3.1-405B',
            'Qwen/Qwen3-32B',
        ],
        'recommended': 'deepseek-ai/DeepSeek-V3.2',
        'pricing_url': 'https://deepinfra.com/pricing'
    },
    'local': {
        'models': [
            'llama3.1',
            'llama3.1:70b',
            'mistral-7b',
            'mixtral-8x7b',
        ],
        'recommended': 'llama3.1',
        'pricing_url': 'N/A (local inference)'
    },
    'batch_proxy': {
        'models': [
            # OpenAI models via proxy
            'gpt-5.2-2025-12-11', 'gpt-5.1', 'gpt-5', 'gpt-5-mini', 'gpt-5-nano',
            'gpt-4.1', 'gpt-4.1-mini', 'gpt-4o', 'gpt-4o-mini',
            # Anthropic models via proxy
            'claude-opus-4-6', 'claude-sonnet-4-5', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
            # Grok models via proxy
            'grok-4-latest', 'grok-3', 'grok-3-mini',
            # Gemini models via proxy
            'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash',
            # DeepInfra models via proxy
            'deepseek-ai/DeepSeek-V3.2', 'zai-org/GLM-5', 'moonshotai/Kimi-K2.5',
            'NousResearch/Hermes-3-Llama-3.1-405B', 'Qwen/Qwen3-32B',
        ],
        'recommended': 'gpt-5-mini (50% cheaper via proxy)',
        'pricing_url': 'https://docs.anthropic.com/en/docs/build-with-claude/message-batches'
    }
}

# Provider-specific rate limit presets
# These are optimized for each provider's rate limits and pricing
RATE_LIMIT_PRESETS = {
    'anthropic': {
        'max_concurrent_requests': 3,      # Conservative for Claude (50 req/min tier limit)
        'min_request_interval': 0.8,       # ~75 req/min max throughput
        'reasoning': 'Prevents 500/529 overload errors on Anthropic API'
    },
    'openai': {
        'max_concurrent_requests': 15,     # OpenAI handles higher concurrency
        'min_request_interval': 0.08,      # ~750 req/min max throughput (GPT-4+ tier allows 500-10k)
        'reasoning': 'OpenAI has higher rate limits (500 req/min for GPT-4, 10k for GPT-3.5/4o-mini)'
    },
    'grok': {
        'max_concurrent_requests': 15,     # xAI handles decent concurrency
        'min_request_interval': 0.08,      # Similar to OpenAI
        'reasoning': 'xAI Grok API has similar rate limits to OpenAI'
    },
    'gemini': {
        'max_concurrent_requests': 15,     # Google handles decent concurrency
        'min_request_interval': 0.08,      # Similar to OpenAI
        'reasoning': 'Google Gemini API has generous rate limits'
    },
    'deepinfra': {
        'max_concurrent_requests': 15,     # DeepInfra handles decent concurrency
        'min_request_interval': 0.08,      # Similar to OpenAI
        'reasoning': 'DeepInfra serverless inference has generous rate limits'
    },
    'local': {
        'max_concurrent_requests': 1,      # Local models typically single-threaded
        'min_request_interval': 0.0,       # No rate limiting needed
        'reasoning': 'Local inference - no API rate limits'
    },
    'batch_proxy': {
        'max_concurrent_requests': 9999,   # No rate limiting (proxy handles queueing)
        'min_request_interval': 0.0,       # No throttling (proxy batches requests)
        'reasoning': 'Batch proxy handles rate limiting and request queuing internally'
    }
}


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
    max_retries: int = 6  # Number of retry attempts for overloaded/rate limit/timeout errors (increased from 3)
    base_delay: float = 5.0  # Base delay in seconds for exponential backoff (increased from 2.0)
    max_delay: float = 120.0  # Maximum delay between retries (increased from 60.0)
    jitter: bool = True  # Add randomness to prevent thundering herd

    # Rate limiting (global across all agents)
    # Tuned for large multi-agent sessions (4 PCs + 8 enemies + DM = 13 agents max)
    # Defaults are for Anthropic (conservative), but auto-adjusted based on provider
    use_rate_limiter: bool = True  # Enable global rate limiting
    max_concurrent_requests: int = 3  # Max concurrent API calls across all agents
    min_request_interval: float = 0.8  # Minimum seconds between request starts

    # Force-truncate long string fields instead of retrying LLM calls
    # When True, providers truncate strings to maxLength on first attempt
    force_truncate: bool = False

    # Provider-specific kwargs
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}

        # Validate provider
        if self.provider not in SUPPORTED_MODELS:
            logger.warning(
                f"⚠️  Unknown provider '{self.provider}'. "
                f"Supported providers: {', '.join(SUPPORTED_MODELS.keys())}"
            )

        # Validate model (warning only, not fatal)
        if self.provider in SUPPORTED_MODELS:
            supported = SUPPORTED_MODELS[self.provider]
            if self.model not in supported['models']:
                logger.warning(
                    f"⚠️  Model '{self.model}' not in known models for provider '{self.provider}'.\n"
                    f"   Supported models: {', '.join(supported['models'][:5])}...\n"
                    f"   Recommended: {supported['recommended']}\n"
                    f"   Pricing: {supported['pricing_url']}\n"
                    f"   Continuing anyway (model may still work if recently released)."
                )

        # Auto-apply provider-specific rate limits if not explicitly overridden
        # This only applies if the values match the default (haven't been customized)
        if self.use_rate_limiter and self.provider in RATE_LIMIT_PRESETS:
            preset = RATE_LIMIT_PRESETS[self.provider]

            # Only override if using default values (user hasn't customized)
            default_concurrent = 3
            default_interval = 0.8

            if self.max_concurrent_requests == default_concurrent:
                self.max_concurrent_requests = preset['max_concurrent_requests']
                logger.llm(
                    f"Applied {self.provider} rate limit preset: "
                    f"max_concurrent={preset['max_concurrent_requests']}"
                )

            if self.min_request_interval == default_interval:
                self.min_request_interval = preset['min_request_interval']
                logger.llm(
                    f"Applied {self.provider} rate limit preset: "
                    f"min_interval={preset['min_request_interval']}s"
                )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any], **overrides) -> 'LLMConfig':
        """Create LLMConfig from a config dict, forwarding unknown keys to extra_params.

        Extracts known dataclass fields from config_dict and puts everything
        else into extra_params (e.g. proxy_url, underlying_provider).
        Keyword overrides take precedence over dict values.

        Args:
            config_dict: Dict from session config (e.g. agent['llm'])
            **overrides: Keyword args that override dict values (e.g. max_tokens=500)

        Returns:
            LLMConfig with extra_params populated from unknown keys
        """
        known_fields = {f.name for f in fields(cls)} - {'extra_params'}

        merged = dict(config_dict)
        merged.update(overrides)

        known = {}
        extra = {}
        for key, value in merged.items():
            if key in known_fields:
                known[key] = value
            else:
                extra[key] = value

        return cls(**known, extra_params=extra)


# =============================================================================
# Truncation utilities (used by multiple providers)
# =============================================================================

def _resolve_schema_ref(field_schema: Dict, defs: Dict) -> Dict:
    """Resolve a $ref or anyOf reference in JSON schema."""
    if "$ref" in field_schema:
        ref_name = field_schema["$ref"].split("/")[-1]
        return defs.get(ref_name, field_schema)

    # Handle anyOf (e.g. Optional[SomeModel] generates anyOf with null)
    if "anyOf" in field_schema:
        for option in field_schema["anyOf"]:
            if "$ref" in option:
                ref_name = option["$ref"].split("/")[-1]
                return defs.get(ref_name, option)
            if option.get("type") != "null":
                return option

    return field_schema


def truncate_to_schema_limits(data: Dict, schema: Dict) -> Dict:
    """
    Recursively walk parsed JSON data and truncate string fields exceeding maxLength.

    Args:
        data: Parsed JSON data dict
        schema: JSON schema from result_type.model_json_schema()

    Returns:
        Data dict with long strings truncated to their maxLength limits
    """
    if not isinstance(data, dict):
        return data

    defs = schema.get("$defs", {})
    properties = schema.get("properties", {})

    for field_name, field_schema in properties.items():
        if field_name not in data or data[field_name] is None:
            continue

        resolved = _resolve_schema_ref(field_schema, defs)
        value = data[field_name]

        if isinstance(value, str):
            max_length = resolved.get("maxLength")
            if max_length and len(value) > max_length:
                logger.warning(
                    f"⚠️ Force-truncating field '{field_name}': "
                    f"{len(value)} → {max_length} chars"
                )
                data[field_name] = value[:max_length]

        elif isinstance(value, dict):
            if "properties" in resolved:
                nested_schema = {**resolved, "$defs": defs}
                data[field_name] = truncate_to_schema_limits(value, nested_schema)
            elif "additionalProperties" in resolved:
                val_schema = _resolve_schema_ref(resolved["additionalProperties"], defs)
                if "properties" in val_schema:
                    for key in value:
                        if isinstance(value[key], dict):
                            nested = {**val_schema, "$defs": defs}
                            value[key] = truncate_to_schema_limits(value[key], nested)

    return data


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

        logger.llm(
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
        Check if an error is retryable (overloaded/rate limit/validation/timeout).

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

        # Check error type for connection/timeout errors
        error_type = type(error).__name__
        if error_type in ['ConnectTimeout', 'ReadTimeout', 'TimeoutError', 'ConnectionError']:
            return True

        # Check error message for overloaded/timeout indicators
        error_str = str(error).lower()
        if 'overloaded' in error_str or 'rate limit' in error_str:
            return True
        if 'timeout' in error_str or 'connection' in error_str:
            return True

        # Check for Pydantic validation errors (allow retries for LLM to self-correct)
        # These occur when LLM generates output violating schema constraints
        if 'validationerror' in error_str or 'validation error' in error_str:
            return True

        # Check for pydantic-ai specific retry messages
        if 'exceeded maximum retries' in error_str:
            return True

        # Check for JSON decode errors (proxy may return truncated/malformed responses)
        # This indicates a transient issue, not a fundamental problem with the prompt
        if error_type == 'JSONDecodeError' or 'jsondecode' in error_str:
            logger.warning("🔄 JSON decode error (possibly truncated response), will retry")
            return True

        return False

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
                        logger.llm(f"✓ Claude API call succeeded after {attempt} retries")

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
        llm_logger: Optional[Any] = None,
        current_round: Optional[int] = None,
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
            llm_logger: Optional LLM call logger for token tracking
            current_round: Optional current round number for logging
            **kwargs: Additional parameters

        Returns:
            Validated Pydantic model instance

        Example:
            ```python
            from schemas.action_resolution import ActionResolution

            resolution = await provider.generate_structured(
                prompt="Resolve this action: ...",
                result_type=ActionResolution,
                system_prompt="You are a game master...",
                llm_logger=self.llm_logger,  # Optional: enables token tracking
                current_round=self.current_round
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

        # Enhance system prompt for ActionResolution to emphasize void_changes
        final_system_prompt = system_prompt or ""
        if result_type.__name__ == 'ActionResolution':
            void_emphasis = """

⚠️ CRITICAL FIELD REQUIREMENT: effects.void_changes

When generating ActionResolution, you MUST populate the `effects.void_changes` field for ANY void-triggering event:

**MANDATORY void_changes scenarios (DO NOT leave empty):**
- **Ritual failures** (astral arts, void manipulation) → `[VoidChange(character_name="PC Name", amount=1, reason="...")]`
- **Missing offerings** (ritual without consumed offering) → `[VoidChange(amount=1, reason="missing offering")]`
- **Missing tools** (ritual without primary tool/focus) → `[VoidChange(amount=1, reason="missing ritual tool")]`
- **Void exposure** (breaches, corrupted areas) → `[VoidChange(amount=1+, reason="void exposure")]`
- **Corrupted technology** interaction → `[VoidChange(amount=1, reason="corrupted tech")]`
- **Cleansing rituals** (success) → `[VoidChange(amount=-2 to -5, reason="purification")]`

**When NOT to populate (empty list is correct):**
- Proper ritual execution WITH offerings consumed = `void_changes=[]`
- Regular combat/social/investigation failures (no void involvement) = `void_changes=[]`

**character_name MUST be specific PC name**, NOT "Environmental Void" or abstract targets.

This field is used for ML training and game mechanics - it is NOT optional when void events occur!
"""
            final_system_prompt += void_emphasis

        # Create Pydantic AI agent with output type
        # Note: pydantic-ai 1.9.0+ uses 'output_type' not 'result_type'
        agent = Agent(
            f'anthropic:{self.config.model}',
            output_type=result_type,
            system_prompt=final_system_prompt
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
                        logger.llm(f"✓ Structured output succeeded after {attempt} retries")

                    # Extract token usage and log if logger provided
                    if llm_logger:
                        usage = result.usage()
                        tokens = {
                            'input': usage.input_tokens,
                            'output': usage.output_tokens,
                            'total': usage.input_tokens + usage.output_tokens
                        }

                        llm_logger._log_llm_call(
                            messages=[{"role": "user", "content": prompt}],
                            response=str(result.output),
                            model=self.config.model,
                            temperature=temperature,
                            tokens=tokens,
                            current_round=current_round,
                            call_sequence=llm_logger.call_count,
                            call_type=f"structured:{result_type.__name__}"
                        )

                    # Return validated Pydantic model instance
                    # Note: pydantic-ai 1.9.0 uses 'output' not 'data' or 'response'
                    # result.output contains the validated Pydantic model
                    # result.response contains the raw ModelResponse
                    return result.output

                except Exception as e:
                    last_error = e

                    # Enhanced error logging for Pydantic AI validation failures
                    error_details = {
                        'exception_type': type(e).__name__,
                        'error_message': str(e),
                        'attempt': attempt + 1,
                        'max_retries': self.config.max_retries + 1,
                        'model': self.config.model,
                        'result_type': result_type.__name__,
                    }

                    # Try to extract Pydantic validation details if available
                    if hasattr(e, '__cause__') and e.__cause__:
                        error_details['underlying_error'] = f"{type(e.__cause__).__name__}: {e.__cause__}"

                    # Try to extract raw model output if available
                    # UnexpectedModelBehavior has a 'body' attribute with the raw response
                    if hasattr(e, 'body') and e.body:
                        body_str = str(e.body)  # pydantic-ai 1.107 body is not a string; coerce
                        error_details['raw_model_response'] = body_str[:2000]
                        logger.error(f"📋 Raw model response that failed validation:\n{body_str[:1000]}")
                    elif hasattr(e, 'message') and e.message:
                        error_details['pydantic_ai_message'] = str(e.message)[:500]

                    # Try to extract raw model output from args as fallback
                    if hasattr(e, 'args') and len(e.args) > 0:
                        error_details['raw_error_args'] = str(e.args[0])[:500]  # Truncate to 500 chars

                    # Log detailed error info
                    logger.error(
                        f"🔴 STRUCTURED OUTPUT VALIDATION ERROR (attempt {attempt + 1}/{self.config.max_retries + 1}):\n"
                        f"  Exception: {error_details['exception_type']}\n"
                        f"  Message: {error_details['error_message']}\n"
                        f"  Schema: {result_type.__name__}\n"
                        f"  Model: {self.config.model}\n"
                        + (f"  Underlying: {error_details.get('underlying_error', 'N/A')}\n" if 'underlying_error' in error_details else "")
                        + (f"  Raw response available: YES ({len(error_details.get('raw_model_response', ''))} chars)\n" if 'raw_model_response' in error_details else "")
                    )

                    # Force-truncate recovery: parse raw response, truncate, validate
                    if self.config.force_truncate and hasattr(e, 'body') and e.body:
                        try:
                            import json as _json
                            raw_data = _json.loads(e.body)
                            schema = result_type.model_json_schema()
                            truncated = truncate_to_schema_limits(raw_data, schema)
                            validated = result_type.model_validate(truncated)
                            logger.warning(
                                f"⚠️ Force-truncate recovered {result_type.__name__} "
                                f"from raw response (attempt {attempt + 1})"
                            )
                            return validated
                        except Exception:
                            pass  # Fall through to normal retry/error handling

                    # Check if error is retryable
                    if not self._is_retryable_error(e):
                        # Non-retryable error, fail immediately
                        logger.error(f"❌ Structured output error is NON-RETRYABLE, aborting")
                        raise

                    # Check if we have retries left
                    if attempt >= self.config.max_retries:
                        # Out of retries - log comprehensive failure info
                        logger.error(
                            f"❌ STRUCTURED OUTPUT FAILED PERMANENTLY after {attempt + 1} attempts:\n"
                            f"  Final error: {error_details['exception_type']}: {error_details['error_message']}\n"
                            f"  Schema: {result_type.__name__}\n"
                            f"  This indicates the model consistently generates invalid output for this schema.\n"
                            f"  Check schema definition, prompt clarity, or model capability."
                        )
                        raise

                    # Calculate backoff delay
                    delay = self._calculate_backoff_delay(attempt)

                    # Log retry attempt with enhanced details
                    logger.warning(
                        f"⚠️  Structured output failed (attempt {attempt + 1}/{self.config.max_retries + 1}), "
                        f"retrying in {delay:.2f}s\n"
                        f"  Error: {error_details['exception_type']}: {error_details['error_message']}"
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

        # Create client with increased timeout for OpenAI's slower response times
        # OpenAI can be very slow with complex structured outputs (especially gpt-5-mini)
        # Increase to: 30s connect, 180s read, 90s write, 240s total pool
        from httpx import Timeout
        self.client = openai.OpenAI(
            api_key=api_key,
            timeout=Timeout(connect=30.0, read=180.0, write=90.0, pool=240.0)
        )

        # Initialize rate limiter if enabled
        if config.use_rate_limiter:
            # Schedule rate limiter initialization in event loop
            # This will be initialized on first use if event loop doesn't exist yet
            self._rate_limiter_initialized = False

        logger.llm(
            f"OpenAIProvider initialized: model={config.model}, "
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
        Check if an error is retryable (rate limit/server error/validation/timeout).

        OpenAI-specific error codes:
        - 429: Rate limit exceeded
        - 500: Internal server error
        - 503: Service unavailable
        - 400: Bad request (ONLY for known Pydantic AI bugs like null content)

        Args:
            error: Exception from API call

        Returns:
            True if error is retryable
        """
        error_str = str(error).lower()

        # Check for OpenAI API errors
        if hasattr(error, 'status_code'):
            # 429: Rate limit exceeded
            # 500: Internal server error
            # 503: Service unavailable
            if error.status_code in [429, 500, 503]:
                return True

            # 400: Bad request - ONLY retry if it's the known Pydantic AI null content bug
            # This is a Pydantic AI bug where it sends {'role': 'assistant', 'content': null}
            # after a tool call, which OpenAI rejects
            if error.status_code == 400:
                if 'content' in error_str and 'null' in error_str:
                    logger.warning("🐛 Detected Pydantic AI null content bug, will retry")
                    return True
                # Don't retry other 400 errors (they're usually schema/validation issues)
                return False

        # Check error type for connection/timeout errors
        error_type = type(error).__name__
        if error_type in ['ConnectTimeout', 'ReadTimeout', 'TimeoutError', 'ConnectionError']:
            return True

        # Check error message for rate limit/overload/timeout indicators
        if 'rate limit' in error_str or 'overloaded' in error_str or 'service unavailable' in error_str:
            return True
        if 'timeout' in error_str or 'connection' in error_str:
            return True

        # Check for Pydantic validation errors (allow retries for LLM to self-correct)
        if 'validationerror' in error_str or 'validation error' in error_str:
            return True

        # Check for length limit errors (retry with increased max_tokens)
        if 'lengthfinishreasonerror' in error_str or 'length limit was reached' in error_str:
            logger.warning("🔄 Length limit reached, will retry with increased max_tokens")
            return True

        # Check for finish_reason: length from openai_structured.py (with space or underscore)
        if ('finish_reason' in error_str or 'finish reason' in error_str) and 'length' in error_str:
            logger.warning("🔄 OpenAI finish_reason: length detected, will retry with increased max_tokens")
            return True

        # Check for pydantic-ai specific retry messages
        if 'exceeded maximum retries' in error_str:
            return True

        # Check for JSON decode errors (proxy may return truncated/malformed responses)
        # This indicates a transient issue, not a fundamental problem with the prompt
        if error_type == 'JSONDecodeError' or 'jsondecode' in error_str:
            logger.warning("🔄 JSON decode error (possibly truncated response), will retry")
            return True

        return False

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

        # OpenAI gpt-5-mini and newer models require temperature=1.0
        if temperature != 1.0:
            logger.debug(f"OpenAI {self.config.model} requires temperature=1.0, normalizing from {temperature}")
            temperature = 1.0

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Call API
        try:
            # gpt-5-mini and newer models require max_completion_tokens instead of max_tokens
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            # Extract text (handle None content gracefully)
            content = response.choices[0].message.content
            text = content.strip() if content is not None else ""

            # Log warning if content is None or empty
            if not text:
                logger.warning(
                    f"OpenAI API returned empty content. "
                    f"Model: {self.config.model}, "
                    f"finish_reason: {response.choices[0].finish_reason}, "
                    f"tokens_used: {response.usage.completion_tokens if response.usage else 'N/A'}"
                )

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

        Uses OpenAI's native Structured Output API directly to avoid Pydantic AI bugs.

        TODO: Switch back to Pydantic AI once null content bug is fixed.
              See: openai_structured.py module docstring

        Args:
            prompt: User prompt
            result_type: Pydantic BaseModel class to validate against
            system_prompt: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature (MUST be 1.0 for OpenAI)
            **kwargs: Additional parameters

        Returns:
            Validated Pydantic model instance

        Example:
            ```python
            from schemas.action_resolution import ActionResolution

            resolution = await provider.generate_structured(
                prompt="Resolve this action: ...",
                result_type=ActionResolution,
                system_prompt="You are a game master...",
                temperature=1.0  # Required for OpenAI structured output
            )
            # resolution is a validated ActionResolution instance
            print(resolution.narration)
            print(resolution.effects.void_changes)
            ```
        """
        # Import the native OpenAI implementation
        from .openai_structured import generate_structured_openai_native

        # Use config defaults if not overridden
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Enhance system prompt for OpenAI models
        final_system_prompt = system_prompt or ""

        # Add conciseness instruction for all OpenAI structured outputs
        conciseness_note = "\n\n**IMPORTANT**: Be concise in your narration. Aim for 2-4 sentences maximum to avoid token limits."
        final_system_prompt += conciseness_note

        if result_type.__name__ == 'ActionResolution':
            void_emphasis = """

⚠️ CRITICAL FIELD REQUIREMENT: effects.void_changes

When generating ActionResolution, you MUST populate the `effects.void_changes` field for ANY void-triggering event:

**MANDATORY void_changes scenarios (DO NOT leave empty):**
- **Ritual failures** (astral arts, void manipulation) → `[VoidChange(character_name="PC Name", amount=1, reason="...")]`
- **Missing offerings** (ritual without consumed offering) → `[VoidChange(amount=1, reason="missing offering")]`
- **Missing tools** (ritual without primary tool/focus) → `[VoidChange(amount=1, reason="missing ritual tool")]`
- **Void exposure** (breaches, corrupted areas) → `[VoidChange(amount=1+, reason="void exposure")]`
- **Corrupted technology** interaction → `[VoidChange(amount=1, reason="corrupted tech")]`
- **Cleansing rituals** (success) → `[VoidChange(amount=-2 to -5, reason="purification")]`

**When NOT to populate (empty list is correct):**
- Proper ritual execution WITH offerings consumed = `void_changes=[]`
- Regular combat/social/investigation failures (no void involvement) = `void_changes=[]`

**character_name MUST be specific PC name**, NOT "Environmental Void" or abstract targets.

This field is used for ML training and game mechanics - it is NOT optional when void events occur!
"""
            final_system_prompt += void_emphasis

        # Initialize rate limiter if needed
        if self.config.use_rate_limiter and not self._rate_limiter_initialized:
            await _rate_limiter.initialize(
                max_concurrent=self.config.max_concurrent_requests,
                min_request_interval=self.config.min_request_interval
            )
            self._rate_limiter_initialized = True

        # Extract logging parameters from kwargs (before retry loop)
        llm_logger = kwargs.pop('llm_logger', None)
        agent_prompt_logger = kwargs.pop('agent_prompt_logger', None)
        agent_id = kwargs.pop('agent_id', None)
        current_round = kwargs.pop('current_round', None)
        call_sequence = kwargs.pop('call_sequence', 0)

        # Acquire rate limiter slot if enabled
        if self.config.use_rate_limiter:
            await _rate_limiter.acquire()

        try:
            # Retry loop with exponential backoff
            last_error = None
            for attempt in range(self.config.max_retries + 1):
                try:

                    # Use native OpenAI API (bypasses Pydantic AI null content bug)
                    output = await generate_structured_openai_native(
                        client=self.client,
                        model=self.config.model,
                        prompt=prompt,
                        result_type=result_type,
                        system_prompt=final_system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        llm_logger=llm_logger,
                        agent_prompt_logger=agent_prompt_logger,
                        agent_id=agent_id,
                        current_round=current_round,
                        call_sequence=call_sequence,
                        force_truncate=self.config.force_truncate,
                        **kwargs
                    )

                    # Log successful retry if not first attempt
                    if attempt > 0:
                        logger.llm(f"✓ Structured output succeeded after {attempt} retries")

                    # Return validated Pydantic model instance
                    return output

                except Exception as e:
                    last_error = e

                    # Enhanced error logging
                    error_details = {
                        'exception_type': type(e).__name__,
                        'error_message': str(e),
                        'attempt': attempt + 1,
                        'max_retries': self.config.max_retries + 1,
                        'model': self.config.model,
                        'result_type': result_type.__name__,
                    }

                    # Try to extract error details from OpenAI exception
                    if hasattr(e, 'response'):
                        try:
                            error_details['http_status'] = e.response.status_code
                            error_details['response_body'] = str(e.response.text)[:1000]
                        except (AttributeError, TypeError, UnicodeDecodeError):
                            # Diagnostic only; the original error still propagates.
                            pass

                    # Try to extract underlying error
                    if hasattr(e, '__cause__') and e.__cause__:
                        error_details['underlying_error'] = f"{type(e.__cause__).__name__}: {e.__cause__}"

                    # Log detailed error info
                    logger.error(
                        f"🔴 STRUCTURED OUTPUT VALIDATION ERROR (attempt {attempt + 1}/{self.config.max_retries + 1}):\n"
                        f"  Exception: {error_details['exception_type']}\n"
                        f"  Message: {error_details['error_message']}\n"
                        f"  Schema: {result_type.__name__}\n"
                        f"  Model: {self.config.model}\n"
                        + (f"  HTTP Status: {error_details.get('http_status', 'N/A')}\n" if 'http_status' in error_details else "")
                        + (f"  Underlying: {error_details.get('underlying_error', 'N/A')}\n" if 'underlying_error' in error_details else "")
                    )

                    # Special handling for length errors - retry with more tokens
                    error_str_check = str(e).lower()
                    if ("finish_reason" in error_str_check or "finish reason" in error_str_check) and "length" in error_str_check:
                        if max_tokens < 8000:  # Cap at 8000 tokens
                            new_max_tokens = min(max_tokens + 2000, 8000)
                            logger.warning(
                                f"⚠️  Hit token limit ({max_tokens}), retrying with {new_max_tokens} tokens"
                            )
                            max_tokens = new_max_tokens
                            continue  # Retry immediately with higher limit

                    # Check if error is retryable
                    if not self._is_retryable_error(e):
                        # Non-retryable error, fail immediately
                        logger.error(f"❌ Structured output error is NON-RETRYABLE, aborting")
                        raise

                    # Check if we have retries left
                    if attempt >= self.config.max_retries:
                        # Out of retries - log comprehensive failure info
                        logger.error(
                            f"❌ STRUCTURED OUTPUT FAILED PERMANENTLY after {attempt + 1} attempts:\n"
                            f"  Final error: {error_details['exception_type']}: {error_details['error_message']}\n"
                            f"  Schema: {result_type.__name__}\n"
                            f"  This indicates the model consistently generates invalid output for this schema.\n"
                            f"  Check schema definition, prompt clarity, or model capability."
                        )
                        raise

                    # Calculate backoff delay
                    delay = self._calculate_backoff_delay(attempt)

                    # Log retry attempt with enhanced details
                    logger.warning(
                        f"⚠️  Structured output failed (attempt {attempt + 1}/{self.config.max_retries + 1}), "
                        f"retrying in {delay:.2f}s\n"
                        f"  Error: {error_details['exception_type']}: {error_details['error_message']}"
                    )

                    # Wait before retry
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            raise last_error or Exception("Unknown error in retry loop")

        finally:
            # Always release rate limiter slot
            if self.config.use_rate_limiter:
                _rate_limiter.release()

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


# Import batch proxy provider
from .llm_batch_provider import BatchProxyProvider

# Provider registry
PROVIDERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "batch_proxy": BatchProxyProvider,
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

    # Map "anthropic" alias to "claude" for backward compatibility
    if provider_name == "anthropic":
        provider_name = "claude"

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
                    logger.llm(f"✓ Anthropic API call succeeded after {attempt} retries")

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
