"""Enemy call_sequence must be unique + contiguous per enemy across rounds.

Bug: `_run_initiative_round` built a FRESH `EnemyFallbackLLMClient` per enemy
*every round*, and the client's `call_sequence` starts at 0 in __init__. So an
enemy that declared in rounds 1 and 2 logged [0, 0] — colliding cache keys,
exactly like the two-phase player bug. Fix: the client (and its counter) must
persist per agent_id across rounds via a session-level cache.
"""
import types

import pytest

from aeonisk.multiagent.session import EnemyFallbackLLMClient, SelfPlayingSession


class _FakeProvider:
    """Stand-in for an LLMProvider: async .generate returning an object with .text."""

    def __init__(self):
        self.n = 0

    async def generate(self, prompt, max_tokens=500, temperature=0.7):
        self.n += 1
        return types.SimpleNamespace(text=f"decision-{self.n}")


def _capturing_logger():
    captured = []
    return types.SimpleNamespace(write_event=lambda e: captured.append(e)), captured


@pytest.mark.asyncio
async def test_client_counter_advances_per_call():
    jl, cap = _capturing_logger()
    client = EnemyFallbackLLMClient(
        llm_config={"model": "test-model"},
        jsonl_logger=jl,
        agent_id="enemy_grunt_a",
        session_id="s",
        provider=_FakeProvider(),
    )
    for _ in range(3):
        await client.generate_async(prompt="p", temperature=1.0)

    seqs = [e["call_sequence"] for e in cap]
    assert seqs == [0, 1, 2]
    assert all(e["agent_id"] == "enemy_grunt_a" for e in cap)
    assert all(e["agent_type"] == "enemy" for e in cap)


def test_session_caches_client_per_agent_id():
    # A bare session (bypass heavy __init__) with just the cache wired.
    sess = SelfPlayingSession.__new__(SelfPlayingSession)
    sess._enemy_llm_clients = {}
    sess.session_id = "s"
    sess.agent_prompt_logger = None

    mechanics = types.SimpleNamespace(jsonl_logger=None)
    cfg = {"model": "test-model"}

    c1 = sess._get_enemy_llm_client(cfg, "enemy_grunt_a", mechanics, provider=_FakeProvider())
    c1_again = sess._get_enemy_llm_client(cfg, "enemy_grunt_a", mechanics, provider=_FakeProvider())
    c2 = sess._get_enemy_llm_client(cfg, "enemy_grunt_b", mechanics, provider=_FakeProvider())

    assert c1 is c1_again, "same agent_id must reuse the cached client (preserves call_sequence)"
    assert c1 is not c2, "different enemies get distinct clients/counters"


@pytest.mark.asyncio
async def test_counter_survives_simulated_rounds_via_cache():
    # Simulate the real bug: two rounds, same enemy. With the cache, sequences
    # must be [0, 1] not [0, 0].
    jl, cap = _capturing_logger()
    sess = SelfPlayingSession.__new__(SelfPlayingSession)
    sess._enemy_llm_clients = {}
    sess.session_id = "s"
    sess.agent_prompt_logger = None
    mechanics = types.SimpleNamespace(jsonl_logger=jl)
    cfg = {"model": "test-model"}
    provider = _FakeProvider()

    for _round in range(2):
        client = sess._get_enemy_llm_client(cfg, "enemy_grunt_a", mechanics, provider=provider)
        await client.generate_async(prompt="p", temperature=1.0)

    assert [e["call_sequence"] for e in cap] == [0, 1]
