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


class MockLLMClient:
    """
    Mock LLM client that returns cached responses for replay.

    Instead of making API calls, this returns pre-recorded responses
    from the original session log.
    """

    def __init__(self, cache: Dict[tuple, str]):
        """
        Initialize mock client with cached responses.

        Args:
            cache: Dict mapping (agent_id, call_sequence) -> response text
        """
        self.cache = cache
        self.call_index: Dict[str, int] = {}  # Track current call for each agent

    async def send_message(self,
                          agent_id: str,
                          messages: List[Dict[str, str]],
                          model: str,
                          temperature: float,
                          max_tokens: int = 4000,
                          **kwargs) -> str:
        """
        Return cached response instead of calling LLM API.

        Args:
            agent_id: Agent making the call
            messages: Message history (ignored in replay)
            model: Model name (ignored in replay)
            temperature: Temperature (ignored in replay)
            max_tokens: Max tokens (ignored in replay)

        Returns:
            Cached response from original session

        Raises:
            KeyError: If cached response not found (indicates replay divergence)
        """
        # Get current call sequence for this agent
        call_seq = self.call_index.get(agent_id, 0)

        # Look up cached response
        cache_key = (agent_id, call_seq)
        if cache_key not in self.cache:
            raise KeyError(
                f"No cached response for {agent_id} call #{call_seq}. "
                f"Replay has diverged from original session."
            )

        response = self.cache[cache_key]

        # Increment call counter
        self.call_index[agent_id] = call_seq + 1

        logger.debug(f"Replay: Returning cached response for {agent_id} call #{call_seq}")
        return response
