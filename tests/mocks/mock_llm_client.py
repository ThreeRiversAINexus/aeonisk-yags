"""
Mock LLM client for deterministic testing without API calls.

This module provides mock implementations of LLM clients that can:
1. Return hand-crafted responses for unit tests
2. Replay recorded responses from real sessions
3. Simulate API errors and rate limiting
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock


class MockLLMResponse:
    """Simulates an Anthropic API response."""

    def __init__(
        self,
        content: str,
        model: str = "claude-3-5-sonnet-20241022",
        input_tokens: int = 100,
        output_tokens: int = 50,
        stop_reason: str = "end_turn"
    ):
        self.id = f"msg_mock_{hashlib.md5(content.encode()).hexdigest()[:8]}"
        self.type = "message"
        self.role = "assistant"
        self.model = model
        self.stop_reason = stop_reason

        # Content as list of content blocks
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = content
        self.content = [content_block]

        # Usage stats
        self.usage = MagicMock()
        self.usage.input_tokens = input_tokens
        self.usage.output_tokens = output_tokens

    def __repr__(self):
        return f"MockLLMResponse(id={self.id}, model={self.model})"


class MockLLMClient:
    """
    Mock Anthropic client that returns pre-defined responses.

    Can be configured with:
    - Fixed responses (same response every time)
    - Response cache (keyed by prompt hash)
    - Response queue (sequential responses)
    - Fixture files (JSON files with responses)
    """

    def __init__(
        self,
        responses: Optional[Union[str, List[str]]] = None,
        response_cache: Optional[Dict[str, str]] = None,
        fixtures_dir: Optional[Path] = None,
        simulate_delay: bool = False,
        delay_ms: int = 100
    ):
        """
        Initialize mock LLM client.

        Args:
            responses: Single response or list of responses to return sequentially
            response_cache: Dict mapping prompt hashes to responses
            fixtures_dir: Directory containing fixture JSON files
            simulate_delay: Whether to simulate API latency
            delay_ms: Delay in milliseconds if simulating
        """
        # Response handling
        if isinstance(responses, str):
            self._responses = [responses]
        elif isinstance(responses, list):
            self._responses = responses
        else:
            self._responses = ["This is a default mock response."]

        self._response_index = 0
        self._response_cache = response_cache or {}
        self._fixtures_dir = fixtures_dir

        # Behavior settings
        self._simulate_delay = simulate_delay
        self._delay_ms = delay_ms

        # Call tracking
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

        # Mock the messages attribute
        self.messages = MagicMock()
        self.messages.create = self._create_message

    async def _create_message(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        system: Optional[Union[str, List[Dict[str, str]]]] = None,
        temperature: float = 1.0,
        **kwargs
    ) -> MockLLMResponse:
        """
        Mock implementation of messages.create().

        Returns responses in order:
        1. Check response_cache (by prompt hash)
        2. Check fixtures_dir (if fixture name in kwargs)
        3. Use sequential responses list
        4. Fall back to default response
        """
        # Track call
        self.call_count += 1
        self.call_history.append({
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "system": system,
            "temperature": temperature,
            "kwargs": kwargs
        })

        # Simulate delay if enabled
        if self._simulate_delay:
            await asyncio.sleep(self._delay_ms / 1000.0)

        # Try to get response from cache (hash prompt)
        prompt_hash = self._hash_prompt(messages)
        if prompt_hash in self._response_cache:
            content = self._response_cache[prompt_hash]
            return MockLLMResponse(content, model=model)

        # Try to load from fixture file (if specified in kwargs)
        if self._fixtures_dir and "fixture" in kwargs:
            fixture_name = kwargs["fixture"]
            content = self._load_fixture(fixture_name)
            if content:
                return MockLLMResponse(content, model=model)

        # Use sequential responses
        if self._response_index < len(self._responses):
            content = self._responses[self._response_index]
            self._response_index += 1
            return MockLLMResponse(content, model=model)

        # Fallback
        return MockLLMResponse("Default mock response.", model=model)

    def _hash_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Create a hash of the prompt for cache lookup."""
        # Combine all message content
        prompt_text = ""
        for msg in messages:
            if isinstance(msg.get("content"), str):
                prompt_text += msg["content"]
            elif isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        prompt_text += block.get("text", "")

        return hashlib.md5(prompt_text.encode()).hexdigest()

    def _load_fixture(self, fixture_name: str) -> Optional[str]:
        """Load response from fixture file."""
        if not self._fixtures_dir:
            return None

        # Try manual first, then recorded
        for subdir in ["manual", "recorded"]:
            fixture_path = self._fixtures_dir / subdir / f"{fixture_name}.json"
            if fixture_path.exists():
                with open(fixture_path, 'r') as f:
                    data = json.load(f)
                    return data.get("response", data.get("content", ""))

        return None

    def reset(self):
        """Reset the mock client state."""
        self._response_index = 0
        self.call_count = 0
        self.call_history.clear()


class MockLLMProvider:
    """
    Mock implementation of LLMProvider for testing.

    Wraps MockLLMClient to match the interface of the real LLMProvider.
    """

    def __init__(
        self,
        responses: Optional[Union[str, List[str]]] = None,
        response_cache: Optional[Dict[str, str]] = None,
        fixtures_dir: Optional[Path] = None
    ):
        """Initialize mock provider."""
        self.client = MockLLMClient(
            responses=responses,
            response_cache=response_cache,
            fixtures_dir=fixtures_dir
        )
        self.provider_name = "mock"
        self.model_name = "mock-model"

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs
    ) -> str:
        """
        Generate a response (matches LLMProvider.generate interface).

        Returns:
            String content from the mock response
        """
        response = await self.client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            messages=messages,
            system=system_prompt,
            temperature=temperature,
            **kwargs
        )

        # Extract text from response
        if response.content and len(response.content) > 0:
            return response.content[0].text

        return ""

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_model: Any,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs
    ) -> Any:
        """
        Generate structured output (Pydantic model).

        For testing, we return a mock instance of the response_model.
        Subclasses can override to return specific test data.
        """
        # Get text response
        text = await self.generate(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        # Try to parse as JSON and create model instance
        try:
            # Assume response is JSON
            data = json.loads(text)
            return response_model(**data)
        except (json.JSONDecodeError, Exception):
            # Fallback: create empty instance (tests should provide proper fixtures)
            return response_model()

    def reset(self):
        """Reset mock state."""
        self.client.reset()


# ============================================================================
# Utility Functions
# ============================================================================

def load_fixture_response(fixture_name: str, fixtures_dir: Path) -> str:
    """
    Load a fixture response from file.

    Args:
        fixture_name: Name of the fixture (without .json extension)
        fixtures_dir: Path to fixtures directory

    Returns:
        Response text content

    Raises:
        FileNotFoundError: If fixture doesn't exist
    """
    # Try manual, then recorded
    for subdir in ["manual", "recorded"]:
        fixture_path = fixtures_dir / subdir / f"{fixture_name}.json"
        if fixture_path.exists():
            with open(fixture_path, 'r') as f:
                data = json.load(f)
                return data.get("response", data.get("content", ""))

    raise FileNotFoundError(f"Fixture '{fixture_name}' not found in {fixtures_dir}")


def create_response_cache_from_fixtures(fixtures_dir: Path) -> Dict[str, str]:
    """
    Create a response cache from all fixtures in a directory.

    This allows tests to automatically use fixtures based on prompt content.

    Args:
        fixtures_dir: Path to directory containing fixture JSON files

    Returns:
        Dict mapping prompt hashes to responses
    """
    cache = {}

    for subdir in ["manual", "recorded"]:
        fixture_subdir = fixtures_dir / subdir
        if not fixture_subdir.exists():
            continue

        for fixture_file in fixture_subdir.glob("*.json"):
            with open(fixture_file, 'r') as f:
                data = json.load(f)

                # If fixture includes prompt, hash it
                if "prompt" in data:
                    prompt_hash = hashlib.md5(data["prompt"].encode()).hexdigest()
                    cache[prompt_hash] = data.get("response", data.get("content", ""))

    return cache
