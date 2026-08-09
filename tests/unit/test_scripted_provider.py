"""Replay a recorded session with no network and no cost.

#100, narrow by design: this serves fixture regeneration (#101), not general
integration testing — #108 covers why direct seam testing won that argument.

The recording already exists. Every `llm_call` event carries `agent_id`,
`call_sequence`, `prompt` and `response`, and `(agent_id, call_sequence)` is the
cache key — which is why `call_sequence_collision` is ERROR-severity: a
duplicate destroys one of these responses before replay ever sees it.
"""

import json

import pytest

from scripts.aeonisk.multiagent.llm_provider import LLMConfig, create_provider
from scripts.aeonisk.multiagent.scripted_provider import (
    ReplayExhausted, ScriptedProvider, load_recorded_calls,
)


def write_session(path, calls):
    """calls: list of (agent_id, call_sequence, response)."""
    with open(path, "w") as fh:
        fh.write(json.dumps({"event_type": "session_start", "session": "t"}) + "\n")
        for agent_id, seq, response in calls:
            fh.write(json.dumps({
                "event_type": "llm_call", "agent_id": agent_id,
                "call_sequence": seq, "prompt": f"prompt {seq}",
                "response": response, "model": "gpt-5-mini",
                "tokens": {"input": 10, "output": 5, "total": 15},
            }) + "\n")
        fh.write(json.dumps({"event_type": "session_end"}) + "\n")
    return str(path)


@pytest.fixture
def recording(tmp_path):
    return write_session(tmp_path / "session_rec.jsonl", [
        ("dm_01", 0, "dm-zero"),
        ("player_01", 0, "p1-zero"),
        ("dm_01", 1, "dm-one"),
        ("player_01", 1, "p1-one"),
        ("dm_01", 2, "dm-two"),
    ])


def make(source, agent_id, **extra):
    return ScriptedProvider(LLMConfig.from_dict(
        {"provider": "scripted", "model": "replay",
         "replay_source": source, "agent_id": agent_id, **extra}))


class TestLoading:

    def test_groups_by_agent(self, recording):
        calls = load_recorded_calls(recording)

        assert set(calls) == {"dm_01", "player_01"}
        assert len(calls["dm_01"]) == 3

    def test_orders_by_call_sequence_not_file_order(self, tmp_path):
        """File order is interleaved across agents; sequence is the contract."""
        source = write_session(tmp_path / "s.jsonl", [
            ("dm_01", 2, "third"), ("dm_01", 0, "first"), ("dm_01", 1, "second")])

        responses = [c["response"] for c in load_recorded_calls(source)["dm_01"]]

        assert responses == ["first", "second", "third"]

    def test_ignores_non_llm_events(self, recording):
        assert all(c["event_type"] == "llm_call"
                   for calls in load_recorded_calls(recording).values()
                   for c in calls)

    def test_skips_calls_with_no_response(self, tmp_path):
        path = tmp_path / "s.jsonl"
        with open(path, "w") as fh:
            fh.write(json.dumps({"event_type": "llm_call", "agent_id": "dm_01",
                                 "call_sequence": 0}) + "\n")

        assert load_recorded_calls(path) == {}

    def test_warns_on_duplicate_sequences(self, tmp_path, caplog):
        """The call_sequence_collision signature — the recording already lost a
        response before replay could use it."""
        source = write_session(tmp_path / "s.jsonl", [
            ("dm_01", 0, "a"), ("dm_01", 0, "b")])

        load_recorded_calls(source)

        assert "duplicate call_sequence" in caplog.text


class TestReplay:

    @pytest.mark.asyncio
    async def test_serves_responses_in_order(self, recording):
        provider = make(recording, "dm_01")

        seen = [(await provider.generate("anything")).text for _ in range(3)]

        assert seen == ["dm-zero", "dm-one", "dm-two"]

    @pytest.mark.asyncio
    async def test_each_agent_gets_its_own_stream(self, recording):
        dm = make(recording, "dm_01")
        player = make(recording, "player_01")

        assert (await dm.generate("x")).text == "dm-zero"
        assert (await player.generate("x")).text == "p1-zero"
        assert (await dm.generate("x")).text == "dm-one"

    @pytest.mark.asyncio
    async def test_the_prompt_is_ignored(self, recording):
        """Matching on prompt text would break replay the moment a template
        changed — which is the situation replay exists to test."""
        provider = make(recording, "dm_01")

        assert (await provider.generate("a totally different prompt")).text == "dm-zero"

    @pytest.mark.asyncio
    async def test_exhaustion_raises_rather_than_inventing(self, recording):
        """A replay that quietly fabricates a response is not a replay, and the
        fixture it produces would be a forgery."""
        provider = make(recording, "dm_01")
        for _ in range(3):
            await provider.generate("x")

        with pytest.raises(ReplayExhausted, match="more calls"):
            await provider.generate("x")

    @pytest.mark.asyncio
    async def test_response_carries_recording_metadata(self, recording):
        response = await make(recording, "dm_01").generate("x")

        assert response.provider == "scripted"
        assert response.model == "gpt-5-mini"
        assert response.tokens_used == 15

    def test_counts_are_introspectable(self, recording):
        provider = make(recording, "dm_01")

        assert provider.remaining == 3 and provider.consumed == 0

    def test_unknown_agent_warns_and_starts_empty(self, recording, caplog):
        provider = make(recording, "nobody_01")

        assert provider.remaining == 0
        assert "no recorded calls" in caplog.text


class TestWiring:

    def test_registered_in_the_provider_factory(self, recording):
        provider = create_provider(LLMConfig.from_dict(
            {"provider": "scripted", "model": "replay",
             "replay_source": recording, "agent_id": "dm_01"}))

        assert isinstance(provider, ScriptedProvider)

    def test_missing_replay_source_fails_loudly(self):
        with pytest.raises(ValueError, match="replay_source"):
            create_provider(LLMConfig.from_dict(
                {"provider": "scripted", "model": "replay"}))

    def test_needs_no_api_key(self, recording, monkeypatch):
        """The whole point: no network, no credentials, no cost."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        assert make(recording, "dm_01").remaining == 3

    def test_replays_a_real_recorded_session(self):
        """Against the reference golden, not a synthetic file."""
        from pathlib import Path
        golden = (Path(__file__).resolve().parents[1] / "fixtures" / "sessions"
                  / "golden_lawful_arrest_complete.jsonl")
        if not golden.exists():
            pytest.skip("reference golden not present")

        calls = load_recorded_calls(golden)

        assert "dm_01" in calls
        assert len(calls["dm_01"]) == 28
        sequences = [c["call_sequence"] for c in calls["dm_01"]]
        assert sequences == sorted(sequences) == list(range(28))
