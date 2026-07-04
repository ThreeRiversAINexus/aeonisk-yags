"""
Tests for proxy config injection in bulk_session_runner and LLMConfig.from_dict().

TDD: These tests define the expected behavior for:
1. inject_proxy_config() switching provider to batch_proxy
2. LLMConfig.from_dict() forwarding extra params
"""

import pytest
import copy
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))


# --- Sample configs for testing ---

def make_openai_config():
    """Minimal OpenAI session config with DM + 2 players."""
    return {
        "session_name": "test_proxy",
        "max_turns": 2,
        "agents": {
            "dm": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "temperature": 0.7
                }
            },
            "players": [
                {
                    "name": "Alice",
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "temperature": 0.8
                    }
                },
                {
                    "name": "Bob",
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "temperature": 0.8
                    }
                }
            ]
        }
    }


def make_config_with_enemies():
    """Config with enemy agents too."""
    config = make_openai_config()
    config["agents"]["enemies"] = {
        "llm": {
            "provider": "openai",
            "model": "gpt-5-mini",
            "temperature": 0.5
        }
    }
    return config


def make_config_with_legacy_enemy_agents():
    """Config with legacy enemy_agents LLM shape."""
    config = make_openai_config()
    config["agents"]["enemy_agents"] = {
        "llm": {
            "provider": "openai",
            "model": "gpt-5-mini",
            "temperature": 0.5
        }
    }
    return config


# --- Tests for inject_proxy_config ---

class TestInjectProxyConfig:
    """Tests that inject_proxy_config correctly switches provider to batch_proxy."""

    def test_switches_dm_provider_to_batch_proxy(self):
        """DM provider should change from openai to batch_proxy."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        result = inject_proxy_config(config, "http://localhost:8000")

        dm_llm = result["agents"]["dm"]["llm"]
        assert dm_llm["provider"] == "batch_proxy"
        assert dm_llm["underlying_provider"] == "openai"
        assert dm_llm["use_proxy"] is True
        assert dm_llm["proxy_url"] == "http://localhost:8000"

    def test_switches_player_providers_to_batch_proxy(self):
        """All player providers should change to batch_proxy."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        result = inject_proxy_config(config, "http://localhost:8000")

        for player in result["agents"]["players"]:
            llm = player["llm"]
            assert llm["provider"] == "batch_proxy", f"Player {player['name']} provider not switched"
            assert llm["underlying_provider"] == "openai"
            assert llm["use_proxy"] is True
            assert llm["proxy_url"] == "http://localhost:8000"

    def test_switches_enemy_agent_provider(self):
        """Enemy agent provider should also be switched if present."""
        from bulk_session_runner import inject_proxy_config

        config = make_config_with_enemies()
        result = inject_proxy_config(config, "http://localhost:8000")

        enemy_llm = result["agents"]["enemies"]["llm"]
        assert enemy_llm["provider"] == "batch_proxy"
        assert enemy_llm["underlying_provider"] == "openai"
        assert enemy_llm["use_proxy"] is True

    def test_switches_legacy_enemy_agent_provider(self):
        """Legacy enemy_agents provider should still be switched if present."""
        from bulk_session_runner import inject_proxy_config

        config = make_config_with_legacy_enemy_agents()
        result = inject_proxy_config(config, "http://localhost:8000")

        enemy_llm = result["agents"]["enemy_agents"]["llm"]
        assert enemy_llm["provider"] == "batch_proxy"
        assert enemy_llm["underlying_provider"] == "openai"
        assert enemy_llm["use_proxy"] is True

    def test_preserves_original_model_and_temperature(self):
        """Model and temperature should be preserved after provider switch."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        result = inject_proxy_config(config, "http://localhost:8000")

        dm_llm = result["agents"]["dm"]["llm"]
        assert dm_llm["model"] == "gpt-5-mini"
        assert dm_llm["temperature"] == 0.7

    def test_does_not_invent_priority_or_strategy(self):
        """Injection without explicit strategy/priority must not set them:
        the config's values (or the provider defaults) stay authoritative.

        Regression: 2026-07-04, --proxy without --direct stomped every
        config's proxy_strategy 'direct' with 'auto'."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        result = inject_proxy_config(config, "http://localhost:8000")

        dm_llm = result["agents"]["dm"]["llm"]
        assert "proxy_priority" not in dm_llm
        assert "proxy_strategy" not in dm_llm

    def test_preserves_config_strategy_when_none_passed(self):
        """A config that chose its strategy keeps it through injection."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        config["agents"]["dm"]["llm"]["proxy_strategy"] = "direct"
        result = inject_proxy_config(config, "http://localhost:8000")

        assert result["agents"]["dm"]["llm"]["proxy_strategy"] == "direct"

    def test_handles_anthropic_provider(self):
        """Should work with anthropic provider too."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        config["agents"]["dm"]["llm"]["provider"] = "anthropic"
        config["agents"]["dm"]["llm"]["model"] = "claude-sonnet-4-5"
        result = inject_proxy_config(config, "http://localhost:8000")

        dm_llm = result["agents"]["dm"]["llm"]
        assert dm_llm["provider"] == "batch_proxy"
        assert dm_llm["underlying_provider"] == "anthropic"

    def test_preserves_existing_batch_proxy_underlying_provider(self):
        """Pre-proxied mixed-provider configs should not be rewritten to batch_proxy."""
        from bulk_session_runner import inject_proxy_config

        config = make_openai_config()
        config["agents"]["dm"]["llm"] = {
            "provider": "batch_proxy",
            "underlying_provider": "openai",
            "model": "gpt-5.4-mini",
        }
        config["agents"]["players"][0]["llm"] = {
            "provider": "batch_proxy",
            "underlying_provider": "gemini",
            "model": "gemini-3.5-flash",
        }
        config["agents"]["enemies"] = {
            "llm": {
                "provider": "batch_proxy",
                "underlying_provider": "gemini",
                "model": "gemini-3.5-flash",
            }
        }

        result = inject_proxy_config(config, "http://localhost:8017", "direct")

        assert result["agents"]["dm"]["llm"]["underlying_provider"] == "openai"
        assert result["agents"]["players"][0]["llm"]["underlying_provider"] == "gemini"
        assert result["agents"]["enemies"]["llm"]["underlying_provider"] == "gemini"
        assert result["agents"]["dm"]["llm"]["proxy_strategy"] == "direct"
        assert result["agents"]["players"][0]["llm"]["proxy_url"] == "http://localhost:8017"
        assert result["agents"]["enemies"]["llm"]["proxy_url"] == "http://localhost:8017"

    def test_no_agents_key_is_noop(self):
        """Config without agents key should not crash."""
        from bulk_session_runner import inject_proxy_config

        config = {"session_name": "test"}
        result = inject_proxy_config(config, "http://localhost:8000")
        assert result == config


# --- Tests for LLMConfig.from_dict ---

class TestLLMConfigFromDict:
    """Tests that LLMConfig.from_dict() properly forwards extra params."""

    def test_basic_fields(self):
        """Known fields should be set on the LLMConfig."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config_dict = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "temperature": 0.7,
        }
        config = LLMConfig.from_dict(config_dict)

        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.temperature == 0.7

    def test_extra_params_forwarded(self):
        """Unknown keys should land in extra_params."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config_dict = {
            "provider": "batch_proxy",
            "model": "gpt-5-mini",
            "underlying_provider": "openai",
            "use_proxy": True,
            "proxy_url": "http://localhost:8000",
            "proxy_priority": "normal",
            "proxy_strategy": "auto",
        }
        config = LLMConfig.from_dict(config_dict)

        assert config.provider == "batch_proxy"
        assert config.extra_params["underlying_provider"] == "openai"
        assert config.extra_params["use_proxy"] is True
        assert config.extra_params["proxy_url"] == "http://localhost:8000"
        assert config.extra_params["proxy_priority"] == "normal"
        assert config.extra_params["proxy_strategy"] == "auto"

    def test_keyword_overrides(self):
        """Keyword overrides should take precedence over dict values."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config_dict = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "max_tokens": 4000,
        }
        config = LLMConfig.from_dict(config_dict, max_tokens=500)

        assert config.max_tokens == 500

    def test_empty_dict_uses_defaults(self):
        """Empty dict with required overrides should work."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config = LLMConfig.from_dict({}, provider="openai", model="gpt-5-mini")

        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.max_tokens == 4000  # default
        assert config.extra_params == {}

    def test_api_key_forwarded(self):
        """api_key should be set as a known field, not extra_params."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config_dict = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "api_key": "sk-test-123",
        }
        config = LLMConfig.from_dict(config_dict)

        assert config.api_key == "sk-test-123"
        assert "api_key" not in config.extra_params

    def test_does_not_mutate_input_dict(self):
        """from_dict should not modify the input dictionary."""
        from aeonisk.multiagent.llm_provider import LLMConfig

        config_dict = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "proxy_url": "http://localhost:8000",
        }
        original = copy.deepcopy(config_dict)
        LLMConfig.from_dict(config_dict)

        assert config_dict == original
