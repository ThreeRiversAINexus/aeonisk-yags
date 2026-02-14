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
        Generate structured output via batch proxy with retry-then-truncate resilience.

        Retry flow:
        1. Generate + parse + validate
        2. On ValidationError/JSONDecodeError: retry with error feedback (up to max_retries)
        3. After retries exhausted: truncate long string fields and return
        4. Non-retryable errors (connection, auth): raise immediately

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
        max_retries = 2  # 3 total attempts: 1 initial + 2 retries

        # Get JSON schema from Pydantic model
        schema = result_type.model_json_schema()
        schema_json = json.dumps(schema, indent=2)

        # Augment system prompt to request JSON output
        enhanced_system_prompt = system_prompt or ""
        enhanced_system_prompt += f"\n\nYou must respond with valid JSON matching this schema:\n{schema_json}\n"
        enhanced_system_prompt += "\nRespond ONLY with the JSON object, no additional text."

        last_error = None
        last_data = None
        content = None

        for attempt in range(1 + max_retries):
            # Build messages (may include error feedback on retry)
            messages = []
            if enhanced_system_prompt:
                messages.append({"role": "system", "content": enhanced_system_prompt})

            user_content = prompt
            if attempt > 0 and last_error:
                user_content = (
                    f"{prompt}\n\n"
                    f"YOUR PREVIOUS RESPONSE FAILED VALIDATION: {last_error}\n"
                    f"Please regenerate with shorter text for the fields that exceeded limits."
                )

            messages.append({"role": "user", "content": user_content})

            # Call via unified client — non-retryable errors propagate immediately
            content = self.client.chat_completion(
                messages=messages,
                model=self.config.model,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Parse JSON response
            if not content or not content.strip():
                last_error = f"Batch proxy returned empty/null content for {result_type.__name__}"
                logger.warning(f"Attempt {attempt + 1}: {last_error}")
                continue

            # Strip markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Attempt to repair common JSON issues before parsing
            content = self._repair_json(content)

            # Try to parse JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                last_error = str(e)
                last_data = None
                logger.warning(
                    f"Attempt {attempt + 1}/{1 + max_retries}: JSON parse failed: {e}. "
                    f"Content preview: {repr(content[:200])}"
                )
                continue

            # Pre-filter invalid position_changes
            data = self._filter_invalid_position_changes(data)

            # Preemptive truncation when force_truncate is enabled
            if self.config.force_truncate:
                data = self._pre_validate_fields(data, schema)

            # Try to validate against Pydantic schema
            try:
                validated = result_type(**data)
            except Exception as e:
                last_error = str(e)
                last_data = data
                logger.warning(
                    f"Attempt {attempt + 1}/{1 + max_retries}: Validation failed for "
                    f"{result_type.__name__}: {e}"
                )
                continue

            # Success — log and return
            if llm_logger:
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

        # All retries exhausted — try truncation as last resort
        if last_data is not None:
            logger.warning(
                f"All {1 + max_retries} attempts failed for {result_type.__name__}. "
                f"Truncating long fields as last resort."
            )
            truncated_data = self._pre_validate_fields(last_data, schema)
            validated = result_type(**truncated_data)

            if llm_logger and content:
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

        # No parseable data at all — raise the last error
        raise ValueError(
            f"Failed to generate valid {result_type.__name__} after {1 + max_retries} attempts: {last_error}"
        )

    def _pre_validate_fields(self, data: Dict, schema: Dict) -> Dict:
        """Truncate string fields exceeding maxLength. Delegates to standalone utility."""
        from .llm_provider import truncate_to_schema_limits
        return truncate_to_schema_limits(data, schema)

    def _resolve_schema_ref(self, field_schema: Dict, defs: Dict) -> Dict:
        """Resolve a $ref or anyOf reference in JSON schema. Delegates to standalone utility."""
        from .llm_provider import _resolve_schema_ref
        return _resolve_schema_ref(field_schema, defs)

    def _repair_json(self, content: str) -> str:
        """
        Attempt to repair common JSON issues from LLM output.

        Handles:
        1. Truncated JSON (missing closing braces/brackets)
        2. Invalid control characters (unescaped newlines in strings)
        3. Empty responses

        Args:
            content: Raw JSON string from LLM

        Returns:
            Repaired JSON string (or original if no repair needed/possible)
        """
        if not content or content.strip() == "":
            logger.warning("Empty JSON response from LLM, cannot repair")
            return content

        original = content

        # Fix 1: Remove/escape invalid control characters in string values
        # This handles unescaped newlines, tabs, etc.
        import re

        def escape_control_chars(match):
            """Escape control chars inside JSON strings."""
            s = match.group(0)
            # Replace control chars with escaped versions
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\t', '\\t')
            return s

        # Match JSON string values (content between quotes, not the quotes themselves)
        # This is a simplified pattern - may not handle all edge cases
        try:
            # Try to find strings that contain control characters
            content = re.sub(
                r'"([^"\\]*(?:\\.[^"\\]*)*)"',
                lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"',
                content
            )
        except Exception as e:
            logger.debug(f"Control char escape failed: {e}")

        # Fix 2: Try to repair truncated JSON by adding missing closing brackets/braces
        # Count opening and closing brackets
        open_braces = content.count('{')
        close_braces = content.count('}')
        open_brackets = content.count('[')
        close_brackets = content.count(']')

        # Add missing closing characters
        if open_braces > close_braces or open_brackets > close_brackets:
            logger.warning(
                f"Detected truncated JSON: {open_braces}/{close_braces} braces, "
                f"{open_brackets}/{close_brackets} brackets. Attempting repair."
            )

            # Find the last valid position and build closing sequence
            # We need to track the nesting order to close correctly
            stack = []
            in_string = False
            escape_next = False

            for char in content:
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue

                if char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char in '}]':
                    if stack and stack[-1] == char:
                        stack.pop()

            # Close any unclosed structures
            if stack:
                # Check if we're in the middle of a string (truncated)
                stripped = content.rstrip()

                # Only add closing quote if we're clearly in a string context
                # (last char is alphanumeric or common sentence-ending punctuation)
                if stripped and in_string:
                    # We're inside an unclosed string
                    content = content.rstrip() + '"'
                    logger.debug("Closed truncated string")

                closing = ''.join(reversed(stack))
                content = content + closing
                logger.info(f"Repaired truncated JSON by adding: {closing}")

        if content != original:
            logger.debug(f"JSON repair applied. Original length: {len(original)}, repaired: {len(content)}")

        return content

    def _filter_invalid_position_changes(self, data: Dict) -> Dict:
        """
        Filter out position_changes with invalid Position enum values.

        LLMs sometimes generate invalid values like 'cover' or 'exposed' instead of
        valid tactical positions (Engaged, Near-PC, Near-Enemy, etc.). Rather than
        crash the entire adjudication, we filter these out and log a warning.

        Args:
            data: Raw parsed JSON data from LLM response

        Returns:
            Data with invalid position_changes removed
        """
        # Valid Position enum values
        VALID_POSITIONS = {
            'Engaged', 'Near-PC', 'Near-Enemy', 'Far-PC', 'Far-Enemy',
            'Extreme-PC', 'Extreme-Enemy'
        }

        # Check for position_changes in effects
        if 'effects' in data and isinstance(data['effects'], dict):
            effects = data['effects']
            if 'position_changes' in effects and isinstance(effects['position_changes'], list):
                original_count = len(effects['position_changes'])
                valid_changes = []

                for pc in effects['position_changes']:
                    if isinstance(pc, dict):
                        new_pos = pc.get('new_position', '')
                        if new_pos in VALID_POSITIONS:
                            valid_changes.append(pc)
                        else:
                            # Log warning for invalid position
                            char_name = pc.get('character_name', 'unknown')
                            logger.warning(
                                f"Filtering invalid position_change: character='{char_name}', "
                                f"new_position='{new_pos}' (valid: {list(VALID_POSITIONS)})"
                            )
                    else:
                        valid_changes.append(pc)  # Keep non-dict items for Pydantic to validate

                effects['position_changes'] = valid_changes

                if len(valid_changes) < original_count:
                    logger.info(
                        f"Filtered {original_count - len(valid_changes)} invalid position_changes, "
                        f"kept {len(valid_changes)}"
                    )

        return data

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
