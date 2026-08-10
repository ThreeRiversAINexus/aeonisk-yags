"""Replay a recorded session's LLM responses. No network, no cost, no drift.

#100, deliberately narrow. This exists to regenerate fixtures (#101), not as a
general integration harness — see #108 for why direct seam testing beat a
scripted harness on the evidence.

Everything needed was already in the corpus. Each `llm_call` event carries
`agent_id`, `call_sequence`, `prompt` and `response`, and `(agent_id,
call_sequence)` is the replay cache key — which is precisely why
`call_sequence_collision` is an ERROR-severity invariant: a duplicate destroys
one of these responses.

Providers are constructed per agent (`player.py`, `dm.py`, `enemy_combat.py`),
so each ScriptedProvider owns one agent's response stream and serves it in
`call_sequence` order.

Structured output needs `generate_structured()`, not `generate()` — the latter
is only the fallback at `structured_output_helpers.py:158`. That method is
absent from the `LLMProvider` ABC yet required by four call sites, so replay
implements it and validates the recorded JSON back into the model.

Usage — in a session config's `llm` block:

    {"provider": "scripted", "model": "replay",
     "replay_source": "multiagent_output/.../session_<uuid>.jsonl"}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_provider import LLMConfig, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class ReplayExhausted(RuntimeError):
    """The engine asked for more calls than the recording contains.

    Raised rather than returning something plausible: a replay that quietly
    invents a response is no longer a replay, and the resulting fixture would
    be a forgery.
    """


def load_recorded_calls(source: str | Path) -> Dict[str, List[dict]]:
    """Group a session's llm_call events by agent, ordered by call_sequence.

    Duplicate sequences are kept in file order and warned about — that is the
    `call_sequence_collision` signature, and it means the recording lost a
    response before it ever reached here.
    """
    by_agent: Dict[str, List[dict]] = {}
    with open(source) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") != "llm_call":
                continue
            agent_id = event.get("agent_id")
            if not agent_id or event.get("response") is None:
                continue
            by_agent.setdefault(agent_id, []).append(event)

    for agent_id, calls in by_agent.items():
        sequences = [c.get("call_sequence") for c in calls]
        if len(set(sequences)) != len(sequences):
            logger.warning(
                f"Replay source has duplicate call_sequence values for "
                f"{agent_id} ({sequences}); the recording already lost responses "
                f"to a cache-key collision")
        calls.sort(key=lambda c: (c.get("call_sequence") is None,
                                  c.get("call_sequence", 0)))
    return by_agent


class ScriptedProvider(LLMProvider):
    """Serves one agent's recorded responses in order.

    Deterministic by construction: the same recording always produces the same
    sequence, so a replay diff isolates *code* changes from model variance.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        extra = getattr(config, "extra_params", None) or {}

        source = extra.get("replay_source")
        if not source:
            raise ValueError(
                "scripted provider requires 'replay_source' (a session JSONL) "
                "in the agent's llm config")

        self.agent_id: Optional[str] = extra.get("agent_id")
        self._source = str(source)
        self._calls: List[dict] = load_recorded_calls(source).get(self.agent_id, []) \
            if self.agent_id else []
        self._cursor = 0

        if self.agent_id and not self._calls:
            logger.warning(
                f"Replay source {self._source} has no recorded calls for "
                f"{self.agent_id}; that agent will raise on its first call")

    # -- LLMProvider interface ------------------------------------------------

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                       max_tokens: Optional[int] = None,
                       temperature: Optional[float] = None,
                       **kwargs: Any) -> LLMResponse:
        """Return the next recorded response. The prompt is ignored by design.

        Matching on prompt text would make replay fail the moment a prompt
        template changed — which is exactly the situation replay exists to test.
        Order is the contract, and `call_sequence` is what guarantees it.
        """
        if self._cursor >= len(self._calls):
            raise ReplayExhausted(
                f"{self.agent_id or 'agent'} requested call "
                f"#{self._cursor} but the recording holds {len(self._calls)}. "
                f"The engine is making more calls than it did when "
                f"{self._source} was recorded.")

        call = self._calls[self._cursor]
        self._cursor += 1
        tokens = call.get("tokens") or {}
        return LLMResponse(
            text=call.get("response", ""),
            model=call.get("model") or self.config.model,
            provider="scripted",
            tokens_used=tokens.get("total") if isinstance(tokens, dict) else None,
            finish_reason="replay",
            raw_response=call,
        )

    async def generate_structured(self, prompt: str, result_type: type,
                                  system_prompt: Optional[str] = None,
                                  max_tokens: Optional[int] = None,
                                  temperature: Optional[float] = None,
                                  llm_logger: Optional[Any] = None,
                                  current_round: Optional[int] = None,
                                  **kwargs: Any):
        """Rebuild the recorded structured output as a validated model.

        Not on the `LLMProvider` ABC, but required in practice: `dm.py:2601`,
        `player.py:1999`, `enemy_combat.py:761` and `npc_agent.py:689` all call
        it, and only two of the four shipped providers implemented it. The first
        end-to-end replay died here.

        Recordings made before the JSON-logging fix hold `repr(model)` rather
        than JSON. Those raise: parsing a repr means `eval`, and a replay that
        guesses at the DM's mechanical output is worse than one that stops.
        """
        expected = self.peek_call_type()
        response = await self.generate(prompt, system_prompt, max_tokens,
                                       temperature, **kwargs)

        # `call_type` is a second, independent record of what this call was.
        # Without it, replay serves by position alone and a diverged engine gets
        # the wrong response silently whenever two adjacent calls share a schema.
        if expected and expected != f"structured:{result_type.__name__}":
            raise ReplayExhausted(
                f"{self.agent_id or 'agent'} replay misaligned at call "
                f"#{self._cursor - 1}: the engine asked for "
                f"{result_type.__name__}, the recording holds {expected}. The "
                f"engine's call sequence has diverged from {self._source}.")

        validate = getattr(result_type, "model_validate_json", None)
        if not callable(validate):
            return response.text

        try:
            return validate(response.text)
        except Exception as exc:
            call = response.raw_response or {}
            raise ReplayExhausted(
                f"{self.agent_id or 'agent'} call #{call.get('call_sequence')} "
                f"cannot be replayed as {result_type.__name__}: the recording "
                f"holds a non-JSON response. Sessions recorded via ClaudeProvider "
                f"before the structured-logging fix stored repr(model), which is "
                f"not recoverable without eval. ({type(exc).__name__})") from exc

    def get_prompt_dir(self) -> str:
        """Replay reuses the prompts of whichever provider recorded the session,
        so the directory follows the recording rather than this provider."""
        extra = getattr(self.config, "extra_params", None) or {}
        return extra.get("prompt_dir", "claude")

    # -- introspection --------------------------------------------------------

    def peek_call_type(self) -> Optional[str]:
        """The `call_type` of the next recorded call, if the recording has one.

        Sessions logged before `call_type` existed return None and replay by
        position, as before.
        """
        if self._cursor >= len(self._calls):
            return None
        return self._calls[self._cursor].get("call_type")

    @property
    def remaining(self) -> int:
        return max(0, len(self._calls) - self._cursor)

    @property
    def consumed(self) -> int:
        return self._cursor
