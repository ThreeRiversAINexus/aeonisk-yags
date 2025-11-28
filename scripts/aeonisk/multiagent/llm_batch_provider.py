"""
Batch Proxy Provider for LLM API calls.

Routes LLM requests through a batching proxy server for cost optimization.
Supports both OpenAI and Anthropic providers with 50% cost reduction.

This provider wraps the UnifiedAIClient and adapts it to the LLMProvider interface.
"""

import json
import logging
from typing import Optional, Any, Dict, List

from .llm_provider import LLMProvider, LLMConfig, LLMResponse
from .unified_llm_client import UnifiedAIClient

logger = logging.getLogger(__name__)


class BatchProxyProvider(LLMProvider):
    """
    LLM provider that routes requests through a batching proxy server.

    This provider wraps UnifiedAIClient to provide cost-optimized LLM calls
    via a batching proxy. Requests are queued and batched together for 50% savings.

    Usage in session config:
        {
          "llm": {
            "provider": "batch_proxy",
            "model": "gpt-5-mini",  # or any supported model
            "use_proxy": true,
            "proxy_url": "http://localhost:8000",
            "proxy_priority": "normal",
            "proxy_strategy": "auto",
            "underlying_provider": "openai"  # or "anthropic"
          }
        }

    The underlying_provider determines which direct API to use as fallback
    and which model catalog to validate against.
    """

    provider_name = "batch_proxy"

    def __init__(self, config: LLMConfig):
        """
        Initialize batch proxy provider.

        Args:
            config: LLMConfig with proxy settings in extra_params:
                - underlying_provider: "openai" or "anthropic"
                - use_proxy: bool (default True for this provider)
                - proxy_url: str (default http://localhost:8000)
                - proxy_priority: "high", "normal", "low" (default "normal")
                - proxy_strategy: "auto", "direct", "batch" (default "auto")
        """
        super().__init__(config)

        # Extract proxy settings from extra_params
        self.underlying_provider = config.extra_params.get('underlying_provider', 'openai')
        use_proxy = config.extra_params.get('use_proxy', True)
        proxy_url = config.extra_params.get('proxy_url', 'http://localhost:8000')
        proxy_priority = config.extra_params.get('proxy_priority', 'normal')
        proxy_strategy = config.extra_params.get('proxy_strategy', 'auto')

        # Initialize unified client
        self.client = UnifiedAIClient(
            provider=self.underlying_provider,
            use_proxy=use_proxy,
            proxy_url=proxy_url,
            proxy_priority=proxy_priority,
            proxy_strategy=proxy_strategy,
        )

        logger.info(
            f"BatchProxyProvider initialized: underlying_provider={self.underlying_provider}, "
            f"use_proxy={use_proxy}, proxy_url={proxy_url}, strategy={proxy_strategy}"
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text from prompt via batch proxy.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature
            **kwargs: Additional provider-specific parameters (ignored)

        Returns:
            LLMResponse with generated text and metadata
        """
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Build messages in OpenAI format (UnifiedAIClient handles conversion)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Call via unified client (handles proxy routing)
        try:
            content = self.client.chat_completion(
                messages=messages,
                model=self.config.model,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return LLMResponse(
                text=content,
                model=self.config.model,
                provider=f"{self.provider_name}:{self.underlying_provider}",
                tokens_used=None,  # Proxy doesn't return token counts in sync mode
                finish_reason="stop",
            )

        except Exception as e:
            logger.error(f"Batch proxy generation failed: {e}")
            raise

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
        Generate structured output via batch proxy.

        This method requests JSON output and validates against a Pydantic schema.
        The proxy server should ideally support structured output natively, but
        we use prompt engineering as a fallback.

        Args:
            prompt: User prompt/message
            result_type: Pydantic BaseModel class for validation
            system_prompt: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature
            llm_logger: Optional logger for token tracking
            current_round: Current round number for logging
            **kwargs: Additional provider-specific parameters

        Returns:
            Validated Pydantic model instance
        """
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Get JSON schema from Pydantic model
        schema = result_type.model_json_schema()
        schema_json = json.dumps(schema, indent=2)

        # Augment system prompt to request JSON output
        enhanced_system_prompt = system_prompt or ""
        enhanced_system_prompt += f"\n\nYou must respond with valid JSON matching this schema:\n{schema_json}\n"
        enhanced_system_prompt += "\nRespond ONLY with the JSON object, no additional text."

        # Build messages
        messages = []
        if enhanced_system_prompt:
            messages.append({"role": "system", "content": enhanced_system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Call via unified client
        try:
            content = self.client.chat_completion(
                messages=messages,
                model=self.config.model,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Parse JSON response
            # Try to extract JSON if wrapped in markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Parse and validate
            data = json.loads(content)
            validated = result_type(**data)

            # Log if logger provided
            if llm_logger:
                # Estimate tokens (rough approximation: 1 token ≈ 4 chars)
                input_chars = len(enhanced_system_prompt) + len(prompt)
                output_chars = len(content)
                estimated_tokens = {
                    'input': input_chars // 4,
                    'output': output_chars // 4,
                    'total': (input_chars + output_chars) // 4
                }

                llm_logger._log_llm_call(
                    messages=messages,
                    response=content,
                    model=self.config.model,
                    temperature=temperature,
                    tokens=estimated_tokens,
                    current_round=current_round,
                    call_sequence=llm_logger.call_count
                )

            return validated

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nResponse: {content[:500]}")
            raise
        except Exception as e:
            logger.error(f"Batch proxy structured generation failed: {e}")
            raise

    def get_prompt_dir(self) -> str:
        """
        Get the directory name for prompts.

        Uses the underlying provider's prompt directory (e.g., "claude", "openai").
        """
        return self.underlying_provider.lower()

    def health_check(self) -> Dict[str, Any]:
        """
        Check if proxy server is reachable and functioning.

        Returns:
            Dict with status information
        """
        return self.client.health_check()


def create_batch_proxy_provider(
    underlying_provider: str,
    model: str,
    use_proxy: bool = True,
    proxy_url: str = "http://localhost:8000",
    proxy_priority: str = "normal",
    proxy_strategy: str = "auto",
    **config_kwargs
) -> BatchProxyProvider:
    """
    Factory function for creating batch proxy provider.

    Args:
        underlying_provider: "openai" or "anthropic"
        model: Model name (e.g., "gpt-5-mini", "claude-sonnet-4-5")
        use_proxy: Enable proxy routing (default True)
        proxy_url: Proxy server URL
        proxy_priority: Request priority ("high", "normal", "low")
        proxy_strategy: Routing strategy ("auto", "direct", "batch")
        **config_kwargs: Additional LLMConfig parameters

    Returns:
        Configured BatchProxyProvider instance
    """
    config = LLMConfig(
        provider="batch_proxy",
        model=model,
        extra_params={
            'underlying_provider': underlying_provider,
            'use_proxy': use_proxy,
            'proxy_url': proxy_url,
            'proxy_priority': proxy_priority,
            'proxy_strategy': proxy_strategy,
        },
        **config_kwargs
    )

    return BatchProxyProvider(config)
