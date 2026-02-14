"""
Unified AI client supporting both OpenAI and Anthropic providers with batch proxy support.

Adapted from aeonisk-transmedia-pipeline for use in aeonisk-yags multi-agent system.
Supports LLM batching proxy for 50% cost reduction on bulk operations.
"""

import os
import time
import logging
import requests
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class UnifiedAIClient:
    """
    Unified interface for OpenAI and Anthropic AI models with batch proxy support.

    This client can route requests through an LLM batching proxy server for cost optimization.
    When proxy is enabled, requests are queued and batched together for 50% cost savings.

    Usage:
        # Direct API calls (fast, full cost)
        client = UnifiedAIClient(provider="openai")
        response = client.chat_completion(messages=[...])

        # Via proxy (slower, 50% cost)
        client = UnifiedAIClient(provider="openai", use_proxy=True, proxy_url="http://localhost:8000")
        response = client.chat_completion(messages=[...])

        # Environment-based (recommended for bulk operations)
        # export USE_LLM_PROXY=true
        # export LLM_PROXY_URL=http://localhost:8000
        client = UnifiedAIClient(provider="openai")
        response = client.chat_completion(messages=[...])
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        use_proxy: bool = False,
        proxy_url: Optional[str] = None,
        proxy_priority: str = "normal",
        proxy_strategy: Optional[str] = None,
    ):
        """
        Initialize AI client with specified provider.

        Args:
            provider: 'openai' or 'anthropic' (defaults to AI_PROVIDER env var)
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            anthropic_api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            use_proxy: Use LLM batching proxy for cost optimization
            proxy_url: Proxy server URL (defaults to LLM_PROXY_URL env var or localhost:8000)
            proxy_priority: Request priority ('high', 'normal', 'low')
            proxy_strategy: Routing strategy ('auto', 'direct', 'batch') or None for env default
        """
        self.provider = provider or os.getenv('AI_PROVIDER', 'openai')

        # Proxy settings
        self.use_proxy = use_proxy or os.getenv('USE_LLM_PROXY', '').lower() == 'true'
        self.proxy_url = proxy_url or os.getenv('LLM_PROXY_URL', 'http://localhost:8000')
        self.proxy_priority = proxy_priority
        self.proxy_strategy = proxy_strategy  # Can be None (use env default)

        # OpenAI-compatible provider configs (base_url + env key for API key)
        # Any provider using an OpenAI-compatible API goes here.
        self._OPENAI_COMPATIBLE_PROVIDERS = {
            'grok': {
                'base_url': 'https://api.x.ai/v1',
                'env_key': 'XAI_API_KEY',
                'default_model': 'grok-4-latest',
                'model_env': 'GROK_MODEL',
            },
            'gemini': {
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
                'env_key': 'GEMINI_API_KEY',
                'default_model': 'gemini-2.5-pro',
                'model_env': 'GEMINI_MODEL',
            },
            'deepinfra': {
                'base_url': 'https://api.deepinfra.com/v1/openai',
                'env_key': 'DEEPINFRA_API_KEY',
                'default_model': 'deepseek-ai/DeepSeek-V3.2',
                'model_env': 'DEEPINFRA_MODEL',
            },
        }

        # Initialize provider clients lazily to avoid import errors if not needed
        self._openai_client = None
        self._anthropic_client = None
        self._openai_compatible_client = None

        # Set default models
        if self.provider == 'openai':
            self.default_model = os.getenv('OPENAI_MODEL', 'gpt-5-mini')
        elif self.provider == 'anthropic':
            self.default_model = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-5')
        elif self.provider in self._OPENAI_COMPATIBLE_PROVIDERS:
            cfg = self._OPENAI_COMPATIBLE_PROVIDERS[self.provider]
            self.default_model = os.getenv(cfg['model_env'], cfg['default_model'])
        else:
            raise ValueError(
                f"Unsupported AI provider: {self.provider}. "
                f"Use 'openai', 'anthropic', {', '.join(repr(k) for k in self._OPENAI_COMPATIBLE_PROVIDERS)}"
            )

        # Store API keys for lazy initialization
        self._openai_api_key = openai_api_key
        self._anthropic_api_key = anthropic_api_key

        logger.debug(
            f"UnifiedAIClient initialized: provider={self.provider}, "
            f"use_proxy={self.use_proxy}, proxy_url={self.proxy_url}"
        )

    @property
    def openai_client(self):
        """Lazy initialization of OpenAI client"""
        if self._openai_client is None:
            from openai import OpenAI
            api_key = self._openai_api_key or os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI provider")
            self._openai_client = OpenAI(api_key=api_key)
        return self._openai_client

    @property
    def anthropic_client(self):
        """Lazy initialization of Anthropic client"""
        if self._anthropic_client is None:
            import anthropic
            api_key = self._anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY required for Anthropic provider")
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
        return self._anthropic_client

    @property
    def _openai_compatible_config(self):
        """Get config dict for an OpenAI-compatible provider (grok, gemini, etc.)."""
        if self.provider not in self._OPENAI_COMPATIBLE_PROVIDERS:
            raise ValueError(f"Provider '{self.provider}' is not an OpenAI-compatible provider")
        return self._OPENAI_COMPATIBLE_PROVIDERS[self.provider]

    def _get_openai_compatible_client(self):
        """Lazy initialization of OpenAI-compatible client with custom base_url."""
        if self._openai_compatible_client is None:
            from openai import OpenAI
            cfg = self._openai_compatible_config
            api_key = os.getenv(cfg['env_key'])
            if not api_key:
                raise ValueError(f"{cfg['env_key']} required for {self.provider} provider")
            self._openai_compatible_client = OpenAI(api_key=api_key, base_url=cfg['base_url'])
        return self._openai_compatible_client

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        """
        Get chat completion from configured AI provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (uses default if not specified)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response

        Raises:
            ValueError: If provider is not supported
            Exception: If all retries fail and fallback fails
        """
        model = model or self.default_model

        # Auto-fix temperature for gpt-5-mini (only supports 1.0)
        if 'gpt-5-mini' in model and temperature != 1.0:
            logger.warning(f"gpt-5-mini only supports temperature=1.0, overriding {temperature} → 1.0")
            temperature = 1.0

        # Route through proxy if enabled
        if self.use_proxy:
            try:
                return self._proxy_completion(messages, model, temperature, max_tokens)
            except Exception as e:
                logger.error(f"Proxy completion failed: {e}")
                raise

        # Direct API call
        return self._direct_completion(messages, model, temperature, max_tokens)

    def _direct_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Route to the correct direct API based on provider."""
        if self.provider == 'openai':
            return self._openai_completion(messages, model, temperature, max_tokens)
        elif self.provider == 'anthropic':
            return self._anthropic_completion(messages, model, temperature, max_tokens)
        elif self.provider in self._OPENAI_COMPATIBLE_PROVIDERS:
            return self._openai_compatible_completion(messages, model, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _openai_compatible_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """OpenAI-compatible chat completion (grok, gemini, etc.) via custom base_url."""
        client = self._get_openai_compatible_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _proxy_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """
        Route request through LLM batching proxy.

        Handles connection errors with exponential backoff and automatic fallback to direct API.

        Returns:
            Generated text response

        Raises:
            Exception: If all retries fail and fallback also fails
        """
        # Get routing strategy (prefer instance setting, then env, then auto)
        strategy = self.proxy_strategy or os.getenv('LLM_PROXY_MODE', 'auto')

        # Prepare request
        request_data = {
            "provider": self.provider,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "priority": self.proxy_priority,
            "strategy": strategy,
        }

        # Submit to proxy with retries
        max_retries = 3
        retry_delay = 5  # Start with 5 seconds

        for attempt in range(max_retries):
            try:
                logger.debug(f"Submitting request to proxy (attempt {attempt + 1}/{max_retries})")
                response = requests.post(
                    f"{self.proxy_url}/submit",
                    json=request_data,
                    timeout=None,  # No timeout - wait indefinitely for batch completion
                )
                response.raise_for_status()

                result = response.json()

                if result.get("status") == "completed":
                    content = result.get("content")
                    if not content:
                        logger.error(
                            "PROXY BUG: Batch completed but content is null/empty. "
                            "Falling back to direct API."
                        )
                        return self._direct_completion(messages, model, temperature, max_tokens)
                    logger.debug(f"Proxy request completed successfully")
                    return content
                else:
                    error = result.get("error", "Unknown error")
                    status = result.get("status", "unknown")
                    logger.error(f"Proxy request failed with status: {status}, error: {error}")

                    # Detect confusing proxy bug: batch completed but no output file
                    # Error looks like: "Batch ended with status: completed" with status="failed"
                    # This is a proxy-side bug - don't retry endlessly, fall back to direct API
                    if "Batch ended with status: completed" in error or "Batch ended with status: ended" in error:
                        logger.error(
                            "PROXY BUG: Batch completed but output file missing. "
                            "This is a bug in the proxy server. Falling back to direct API. "
                            "Check proxy logs for why output_file_path is None."
                        )
                        # Fall back to direct API immediately, don't retry
                        return self._direct_completion(messages, model, temperature, max_tokens)

                    raise Exception(f"Proxy request failed: {error}")

            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{max_retries}): {e}, "
                        f"retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.info(
                        f"Proxy unavailable at {self.proxy_url} after {max_retries} attempts, "
                        f"falling back to direct {self.provider} API"
                    )
                    # Fallback to direct
                    return self._direct_completion(messages, model, temperature, max_tokens)

            except requests.exceptions.Timeout:
                # This shouldn't happen with timeout=None, but handle it just in case
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout error (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.info(f"Proxy timeout after {max_retries} attempts, falling back to direct {self.provider} API")
                    return self._direct_completion(messages, model, temperature, max_tokens)

            except requests.exceptions.HTTPError as e:
                # HTTP errors (4xx, 5xx) - don't retry, fall back immediately
                logger.info(f"Proxy HTTP error ({e}), falling back to direct {self.provider} API")
                return self._direct_completion(messages, model, temperature, max_tokens)

            except Exception as e:
                # Other errors - try once more then fall back
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Proxy error (attempt {attempt + 1}/{max_retries}): {e}, "
                        f"retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.info(f"Proxy error after {max_retries} attempts ({e}), falling back to direct {self.provider} API")
                    return self._direct_completion(messages, model, temperature, max_tokens)

        # Should never reach here, but just in case
        raise Exception("Unexpected error: exceeded max retries without returning or raising")

    def _openai_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """
        OpenAI chat completion via direct API.

        Handles model-specific parameter differences (GPT-5 vs GPT-4).
        """
        kwargs = {
            'model': model,
            'messages': messages,
        }

        # GPT-5 models have different parameter requirements
        if model.startswith('gpt-5'):
            # GPT-5 only supports temperature=1 (default)
            # Uses max_completion_tokens instead of max_tokens
            kwargs['max_completion_tokens'] = max_tokens
            # Don't set temperature - use default
        else:
            # GPT-4 and earlier models
            kwargs['temperature'] = temperature
            kwargs['max_tokens'] = max_tokens

        response = self.openai_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()

    def _anthropic_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """
        Anthropic chat completion via direct API.

        Converts OpenAI-style messages to Anthropic format:
        - Extracts system message if present
        - Converts remaining messages to Anthropic format
        """
        # Extract system message if present
        system_message = None
        user_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                user_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

        # Create Anthropic request
        kwargs = {
            'model': model,
            'messages': user_messages,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        if system_message:
            kwargs['system'] = system_message

        response = self.anthropic_client.messages.create(**kwargs)

        # Extract text from response
        return response.content[0].text.strip()

    def health_check(self) -> Dict[str, any]:
        """
        Check if proxy server is reachable and functioning.

        Returns:
            Dict with status information:
            {
                'reachable': bool,
                'status': str ('healthy', 'unhealthy', 'unreachable'),
                'response_time_ms': float or None,
                'error': str or None
            }
        """
        if not self.use_proxy:
            return {
                'reachable': True,
                'status': 'direct',
                'response_time_ms': None,
                'error': None,
                'message': 'Proxy not enabled, using direct API'
            }

        try:
            start_time = time.time()
            response = requests.get(f"{self.proxy_url}/health", timeout=5)
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                return {
                    'reachable': True,
                    'status': 'healthy',
                    'response_time_ms': response_time_ms,
                    'error': None
                }
            else:
                return {
                    'reachable': True,
                    'status': 'unhealthy',
                    'response_time_ms': response_time_ms,
                    'error': f"HTTP {response.status_code}"
                }
        except requests.exceptions.ConnectionError as e:
            return {
                'reachable': False,
                'status': 'unreachable',
                'response_time_ms': None,
                'error': f"Connection error: {e}"
            }
        except requests.exceptions.Timeout:
            return {
                'reachable': False,
                'status': 'unreachable',
                'response_time_ms': None,
                'error': "Timeout (>5s)"
            }
        except Exception as e:
            return {
                'reachable': False,
                'status': 'unreachable',
                'response_time_ms': None,
                'error': str(e)
            }
