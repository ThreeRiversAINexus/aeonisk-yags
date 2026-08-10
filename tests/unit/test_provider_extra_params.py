"""`extra_params` carries two unrelated things, and one of them reached the API.

Found by a smoke run on 2026-08-10 (session 9e9ad880). Every enemy declaration
died:

    Claude API error (non-retryable):
        Messages.create() got an unexpected keyword argument 'agent_id'
    Threshold Acolyte Nyv Rift: Error generating declaration: ...
    Matron Ysolde Xalith: Error generating declaration: ...

Enemies were mute for the whole session. That is the exact confound the
tactical-module rule exists to prevent — it makes "the model would not fight"
indistinguishable from "the harness never let it".

The chain: `session.py:786` stashes the enemy's id into the config so replay can
select a per-enemy response stream (#101), `LLMConfig.from_dict` forwards every
unknown key into `extra_params`, and `ClaudeProvider.generate` splats
`extra_params` straight into `messages.create()`.

So `extra_params` is doing double duty — genuine pass-through API parameters
*and* provider construction metadata (`agent_id`, `proxy_url`,
`underlying_provider`, `replay_source`). Only the first kind may reach the API.
Note the second kind is load-bearing: `ScriptedProvider` reads
`extra.get("agent_id")` to pick its stream, so the fix cannot be to stop putting
it there.

The OpenAI structured path already pops these keys by hand
(`llm_provider.py:1272-1276`); the Anthropic path never did.
"""

import pytest

from scripts.aeonisk.multiagent.llm_provider import (
    LLMConfig, PROVIDER_ONLY_KEYS, api_extra_params,
    build_anthropic_api_params,
)


def anthropic_config(**overrides):
    return LLMConfig.from_dict(
        {"provider": "anthropic", "model": "claude-sonnet-4-5"}, **overrides)


class TestProviderMetadataNeverReachesTheAPI:

    def test_agent_id_is_filtered(self):
        """The exact key that killed every enemy declaration."""
        assert "agent_id" not in api_extra_params({"agent_id": "enemy_x"})

    @pytest.mark.parametrize("key", sorted(PROVIDER_ONLY_KEYS))
    def test_every_provider_only_key_is_filtered(self, key):
        assert api_extra_params({key: "whatever"}) == {}

    def test_genuine_api_params_survive(self):
        """The feature `extra_params` exists for must keep working."""
        kept = api_extra_params({"top_p": 0.9, "stop_sequences": ["END"],
                                 "agent_id": "enemy_x"})

        assert kept == {"top_p": 0.9, "stop_sequences": ["END"]}

    def test_none_is_tolerated(self):
        assert api_extra_params(None) == {}

    def test_the_config_path_that_produced_the_bug(self):
        """End to end from the call `session.py:786` actually makes."""
        config = LLMConfig.from_dict(
            {"provider": "anthropic", "model": "claude-sonnet-4-5"},
            max_tokens=500, agent_id="enemy_ysolde")

        assert config.extra_params == {"agent_id": "enemy_ysolde"}, (
            "replay selects a stream by this, so it must stay in extra_params")
        assert api_extra_params(config.extra_params) == {}, (
            "...but it must never reach messages.create()")


class TestTheCallSiteActuallyFilters:
    """Asserting `api_extra_params` in isolation is a check that cannot fail:
    mutation testing showed the whole call site could stop calling it with every
    test still green. These exercise the params that really go to the API."""

    def test_agent_id_never_appears_in_the_request(self):
        params = build_anthropic_api_params(
            anthropic_config(agent_id="enemy_ysolde"),
            "prompt", None, 500, 1.0)

        assert "agent_id" not in params

    def test_logging_kwargs_never_appear_in_the_request(self):
        params = build_anthropic_api_params(
            anthropic_config(), "prompt", None, 500, 1.0,
            {"llm_logger": object(), "current_round": 3, "call_sequence": 7})

        assert set(params) == {"model", "max_tokens", "temperature", "messages"}

    def test_the_request_still_carries_what_it_must(self):
        params = build_anthropic_api_params(
            anthropic_config(agent_id="enemy_ysolde"),
            "the prompt", "the system prompt", 500, 1.0, {"top_p": 0.9})

        assert params["model"] == "claude-sonnet-4-5"
        assert params["messages"] == [{"role": "user", "content": "the prompt"}]
        assert params["system"] == "the system prompt"
        assert params["top_p"] == 0.9

    def test_no_system_key_when_none_given(self):
        params = build_anthropic_api_params(
            anthropic_config(), "prompt", None, 500, 1.0)

        assert "system" not in params


class TestReplayStillFindsItsStream:
    """The fix must not break what put `agent_id` there in the first place."""

    def test_scripted_provider_reads_agent_id_from_extra_params(self, tmp_path):
        from scripts.aeonisk.multiagent.scripted_provider import ScriptedProvider

        recording = tmp_path / "session.jsonl"
        recording.write_text(
            '{"event_type": "llm_call", "agent_id": "enemy_ysolde", '
            '"call_sequence": 0, "prompt": "p", "response": "r"}\n')

        provider = ScriptedProvider(LLMConfig.from_dict(
            {"provider": "scripted", "model": "replay",
             "replay_source": str(recording)},
            agent_id="enemy_ysolde"))

        assert provider.agent_id == "enemy_ysolde"
        assert len(provider._calls) == 1
