"""llm_call events must carry a `call_type` tag — the semantic replay-cache key.

Today the replay cache is keyed by strict ordinal (agent_id, call_sequence), so
ANY call-flow change (a skipped or added LLM call) shatters alignment and forces
a full re-record. Tagging each call with WHAT it was (structured:<Schema> for
Pydantic calls, text[:purpose] otherwise) is the enabler for semantic keying:
a skipped call simply isn't looked up; a new call falls through to stub/live.
It also lets contract replay know which schema to re-validate a response against.
"""
import re
import types
from pathlib import Path

import pytest

from aeonisk.multiagent.llm_logger import LLMCallLogger
from aeonisk.multiagent.session import EnemyFallbackLLMClient

_MULTIAGENT = Path(__file__).resolve().parents[2] / "scripts" / "aeonisk" / "multiagent"


def _logger():
    captured = []
    jl = types.SimpleNamespace(write_event=lambda e: captured.append(e))
    lg = LLMCallLogger(agent_id="player_01", agent_type="player",
                       jsonl_logger=jl, session_id="s")
    return lg, captured


def _log(lg, call_type=None):
    kwargs = {} if call_type is None else {"call_type": call_type}
    lg._log_llm_call(messages=[{"role": "user", "content": "p"}], response="r",
                     model="m", temperature=0.7, tokens={}, current_round=1, **kwargs)


class TestLoggerTag:
    def test_default_is_text(self):
        lg, cap = _logger()
        _log(lg)
        assert cap[0]["call_type"] == "text"

    def test_explicit_tag_passthrough(self):
        lg, cap = _logger()
        _log(lg, call_type="structured:ActionIntent")
        assert cap[0]["call_type"] == "structured:ActionIntent"


class TestEnemyClientTag:
    @pytest.mark.asyncio
    async def test_enemy_fallback_events_are_tagged(self):
        captured = []
        jl = types.SimpleNamespace(write_event=lambda e: captured.append(e))

        class _P:
            async def generate(self, prompt, max_tokens=500, temperature=0.7):
                return types.SimpleNamespace(text="decision")

        client = EnemyFallbackLLMClient({"model": "m"}, jsonl_logger=jl,
                                        agent_id="enemy_a", session_id="s",
                                        provider=_P())
        await client.generate_async(prompt="p")
        assert captured[0]["call_type"] == "text:enemy_tactical"


class TestStructuredPathsPassTag:
    """Source-level guard: both structured-output logging sites must derive the
    tag from result_type. (Functional coverage comes from the live smoke — these
    paths need a whole provider stack to execute.)"""

    def _site_passes_tag(self, path: Path) -> bool:
        src = path.read_text()
        # every _log_llm_call( call in the file must include a call_type= kwarg
        sites = [m.start() for m in re.finditer(r"_log_llm_call\(", src)]
        calls = [src[s:s + 600] for s in sites if not src[:s].rstrip().endswith("def")]
        return calls and all("call_type=" in c for c in calls)

    def test_anthropic_provider_site(self):
        assert self._site_passes_tag(_MULTIAGENT / "llm_provider.py")

    def test_openai_native_site(self):
        assert self._site_passes_tag(_MULTIAGENT / "openai_structured.py")

    def test_batch_proxy_provider_sites(self):
        # the third structured path — found UNTAGGED in the live smoke (28 'text',
        # 0 structured): the proxy provider logs through its own generate_structured
        assert self._site_passes_tag(_MULTIAGENT / "llm_batch_provider.py")
