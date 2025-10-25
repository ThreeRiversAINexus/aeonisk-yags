"""
LLM Call Logger - Captures all LLM API calls for replay functionality.

This module provides a wrapper around LLM clients that logs all prompts
and responses to enable deterministic replay of game sessions.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMCallLogger:
    """
    Wraps LLM API calls to log prompts and responses for replay.

    This enables deterministic replay by caching all AI decisions
    from DM, Player, and Enemy agents.
    """

    def __init__(self,
                 agent_id: str,
                 agent_type: str,  # 'dm', 'player', 'enemy'
                 jsonl_logger: Optional[Any] = None,
                 session_id: Optional[str] = None):
        """
        Initialize LLM call logger.

        Args:
            agent_id: Unique identifier for the agent (e.g., 'player_01', 'dm', 'enemy_grunt_abc')
            agent_type: Type of agent ('dm', 'player', 'enemy')
            jsonl_logger: Reference to the JSONLLogger for writing events
            session_id: Current session ID
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.jsonl_logger = jsonl_logger
        self.session_id = session_id
        self.call_count = 0  # Track number of calls per agent (for replay sequencing)

    async def send_message(self,
                          client: Any,
                          messages: List[Dict[str, str]],
                          model: str,
                          temperature: float,
                          max_tokens: int = 4000,
                          current_round: Optional[int] = None,
                          **kwargs) -> str:
        """
        Send message to LLM and log the call.

        Args:
            client: The actual LLM client (Anthropic, OpenAI, etc.)
            messages: List of message dicts with 'role' and 'content'
            model: Model name
            temperature: Sampling temperature
            max_tokens: Max tokens in response
            current_round: Current game round (for logging)
            **kwargs: Additional arguments passed to client

        Returns:
            The LLM response text
        """
        # Make the actual API call
        try:
            response = await client.messages.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            # Extract response text
            response_text = response.content[0].text

            # Extract token usage
            tokens = {
                'input': getattr(response.usage, 'input_tokens', 0),
                'output': getattr(response.usage, 'output_tokens', 0)
            }

        except Exception as e:
            logger.error(f"LLM API call failed for {self.agent_id}: {e}")
            raise

        # Log the call
        self._log_llm_call(
            messages=messages,
            response=response_text,
            model=model,
            temperature=temperature,
            tokens=tokens,
            current_round=current_round,
            call_sequence=self.call_count
        )

        self.call_count += 1
        return response_text

    def _log_llm_call(self,
                     messages: List[Dict[str, str]],
                     response: str,
                     model: str,
                     temperature: float,
                     tokens: Dict[str, int],
                     current_round: Optional[int],
                     call_sequence: int):
        """
        Log an LLM call event to JSONL.

        Event format:
        {
            "event_type": "llm_call",
            "ts": "...",
            "session": "...",
            "round": 1,
            "agent_id": "player_01",
            "agent_type": "player",
            "call_sequence": 0,  # Nth call by this agent (for replay ordering)
            "prompt": [...],  # Full message history
            "response": "...",
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.8,
            "tokens": {"input": 1234, "output": 567}
        }
        """
        if not self.jsonl_logger:
            logger.debug(f"No JSONL logger configured for {self.agent_id}, skipping LLM call log")
            return

        event = {
            'event_type': 'llm_call',
            'ts': datetime.utcnow().isoformat(),
            'session': self.session_id or 'unknown',
            'round': current_round,
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'call_sequence': call_sequence,
            'prompt': messages,
            'response': response,
            'model': model,
            'temperature': temperature,
            'tokens': tokens
        }

        # Write to JSONL log
        try:
            self.jsonl_logger.write_event(event)
            logger.debug(f"Logged LLM call for {self.agent_id} (sequence {call_sequence})")
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}")


class MockLLMResponse:
    """Mock response object that mimics Anthropic API response structure."""

    def __init__(self, text: str, input_tokens: int = 0, output_tokens: int = 0):
        self.content = [MockContent(text)]
        self.usage = MockUsage(input_tokens, output_tokens)


class MockContent:
    """Mock content object for response.content[0]."""

    def __init__(self, text: str):
        self.text = text


class MockUsage:
    """Mock usage object for token counts."""

    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockMessages:
    """Mock messages interface that provides the .create() method."""

    def __init__(self, cache: Dict[tuple, Dict], call_index: Dict[str, int], agent_id: str):
        self.cache = cache
        self.call_index = call_index
        self.agent_id = agent_id

    def create(self, model: str, messages: List[Dict[str, str]],
               temperature: float = 0.7, max_tokens: int = 4000, **kwargs):
        """
        Return cached response instead of calling LLM API.

        This mimics the Anthropic client.messages.create() interface.
        """
        # Get current call sequence for this agent
        call_seq = self.call_index.get(self.agent_id, 0)

        # Look up cached response
        cache_key = (self.agent_id, call_seq)
        if cache_key not in self.cache:
            raise KeyError(
                f"No cached response for {self.agent_id} call #{call_seq}. "
                f"Replay has diverged from original session."
            )

        cached = self.cache[cache_key]
        response_text = cached['response']
        tokens = cached.get('tokens', {'input': 0, 'output': 0})

        # Increment call counter
        self.call_index[self.agent_id] = call_seq + 1

        logger.debug(f"Replay: Returning cached response for {self.agent_id} call #{call_seq}")

        # Return response in Anthropic API format
        return MockLLMResponse(response_text, tokens['input'], tokens['output'])


class MockLLMClient:
    """
    Mock LLM client that mimics Anthropic API for replay.

    Instead of making API calls, this returns pre-recorded responses
    from the original session log.

    Usage:
        client = MockLLMClient(cache, agent_id='dm_01')
        response = client.messages.create(model='...', messages=[...])
        text = response.content[0].text
    """

    def __init__(self, cache: Dict[tuple, Dict], agent_id: str):
        """
        Initialize mock client with cached responses.

        Args:
            cache: Dict mapping (agent_id, call_sequence) -> response dict
            agent_id: ID of the agent using this client
        """
        self.cache = cache
        self.call_index: Dict[str, int] = {}  # Track current call for each agent
        self.agent_id = agent_id

        # Create messages interface (mimics client.messages.create())
        self.messages = MockMessages(self.cache, self.call_index, self.agent_id)


class HybridMessages:
    """Messages interface that routes to mock or real client based on round."""

    def __init__(self, mock_messages: MockMessages, real_client: Any, continue_from_round: int):
        self.mock_messages = mock_messages
        self.real_client = real_client
        self.continue_from_round = continue_from_round
        self.current_round = 0  # Track which round we're in

    def set_round(self, round_num: int):
        """Update current round (called by session before each round)."""
        self.current_round = round_num
        logger.debug(f"HybridMessages: Round updated to {round_num} (switch at {self.continue_from_round})")

    def create(self, model: str, messages: List[Dict[str, str]],
               temperature: float = 0.7, max_tokens: int = 4000, **kwargs):
        """
        Route to mock or real client based on current round.

        If current_round <= continue_from_round: use cached mock responses
        If current_round > continue_from_round: make real LLM API calls
        """
        if self.current_round <= self.continue_from_round:
            # Use cached response
            logger.debug(f"HybridMessages: Round {self.current_round} <= {self.continue_from_round}, using MOCK")
            return self.mock_messages.create(model, messages, temperature, max_tokens, **kwargs)
        else:
            # Make real API call
            logger.info(f"HybridMessages: Round {self.current_round} > {self.continue_from_round}, using REAL LLM")
            return self.real_client.messages.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )


class HybridLLMClient:
    """
    Hybrid LLM client that switches from cached to live responses.

    Used for "continue-from-round" replay mode:
    - Rounds 1-N: Use cached responses (deterministic replay)
    - Rounds N+1+: Make real LLM API calls (continue live)

    This enables warm-start testing and debugging specific rounds.
    """

    def __init__(self, cache: Dict[tuple, Dict], agent_id: str, continue_from_round: int):
        """
        Initialize hybrid client.

        Args:
            cache: Dict mapping (agent_id, call_sequence) -> response dict
            agent_id: ID of the agent using this client
            continue_from_round: Switch to live calls after this round
        """
        import anthropic
        import os

        self.cache = cache
        self.agent_id = agent_id
        self.continue_from_round = continue_from_round
        self.call_index: Dict[str, int] = {}

        # Create mock messages interface
        mock_messages = MockMessages(self.cache, self.call_index, self.agent_id)

        # Create real Anthropic client
        self.real_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # Create hybrid messages interface that routes between them
        self.messages = HybridMessages(mock_messages, self.real_client, continue_from_round)

    def set_round(self, round_num: int):
        """Update current round (called by session)."""
        self.messages.set_round(round_num)
