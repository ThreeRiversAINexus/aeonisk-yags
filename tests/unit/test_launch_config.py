"""
Tests for launch_config: shared config resolution for session entry points.

Precedence contract: session config JSON is authoritative. CLI flags only
take effect when explicitly passed (non-None), and any explicit override
that CHANGES an existing config value must be reported so callers log it.

Regression anchor: 2026-07-04, `bulk_session_runner --proxy <url>` without
`--direct` silently overwrote every agent's proxy_strategy "direct" with
"auto", sending a corpus run into the batch queue.
"""

import copy
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.launch_config import (
    LOG_LEVEL_CHOICES,
    PROXY_STRATEGY_CHOICES,
    apply_proxy_overrides,
    effective_routing_report,
    validate_session_config,
)


def make_config(**overrides):
    """Minimal valid session config: DM + 2 players, plain openai."""
    config = {
        "session_name": "test_launch",
        "max_turns": 2,
        "party_size": 2,
        "agents": {
            "dm": {
                "llm": {"provider": "openai", "model": "gpt-5-mini",
                        "temperature": 0.7}
            },
            "players": [
                {"name": "Alice", "faction": "Freeborn",
                 "llm": {"provider": "openai", "model": "gpt-5-mini"}},
                {"name": "Bob", "faction": "Sovereign Nexus",
                 "llm": {"provider": "openai", "model": "gpt-5-mini"}},
            ],
        },
    }
    config.update(overrides)
    return config


def make_proxied_config(strategy="direct", priority="high"):
    """Config already routed through the proxy with explicit routing choices."""
    config = make_config()
    for llm in [config["agents"]["dm"]["llm"]] + [
        p["llm"] for p in config["agents"]["players"]
    ]:
        llm.update({
            "provider": "batch_proxy",
            "underlying_provider": "openai",
            "use_proxy": True,
            "proxy_url": "http://localhost:9090",
            "proxy_strategy": strategy,
            "proxy_priority": priority,
        })
    return config


class TestApplyProxyOverridesPrecedence:
    """The stomp regression tests: unset flags never touch config values."""

    def test_proxy_url_alone_preserves_config_strategy(self):
        """--proxy without --strategy must NOT touch proxy_strategy."""
        config = make_proxied_config(strategy="direct")
        apply_proxy_overrides(config, proxy_url="http://localhost:9090")

        assert config["agents"]["dm"]["llm"]["proxy_strategy"] == "direct"
        for player in config["agents"]["players"]:
            assert player["llm"]["proxy_strategy"] == "direct"

    def test_proxy_url_alone_preserves_config_priority(self):
        config = make_proxied_config(priority="high")
        apply_proxy_overrides(config, proxy_url="http://localhost:9090")

        assert config["agents"]["dm"]["llm"]["proxy_priority"] == "high"

    def test_proxy_url_alone_leaves_strategy_absent_when_absent(self):
        """Injecting proxy into a plain config must not invent a strategy;
        the provider default ('auto') applies downstream and the routing
        report says so."""
        config = make_config()
        apply_proxy_overrides(config, proxy_url="http://localhost:9090")

        dm_llm = config["agents"]["dm"]["llm"]
        assert dm_llm["provider"] == "batch_proxy"
        assert dm_llm["underlying_provider"] == "openai"
        assert dm_llm["use_proxy"] is True
        assert dm_llm["proxy_url"] == "http://localhost:9090"
        assert "proxy_strategy" not in dm_llm
        assert "proxy_priority" not in dm_llm

    def test_no_args_is_noop(self):
        config = make_proxied_config()
        before = copy.deepcopy(config)
        changes = apply_proxy_overrides(config)
        assert config == before
        assert changes == []

    def test_explicit_strategy_overrides_and_reports(self):
        config = make_proxied_config(strategy="batch")
        changes = apply_proxy_overrides(
            config, proxy_url="http://localhost:9090", strategy="direct")

        assert config["agents"]["dm"]["llm"]["proxy_strategy"] == "direct"
        # Every agent whose value changed produces a report line
        assert any("dm" in line and "batch" in line and "direct" in line
                   for line in changes)
        assert len([l for l in changes if "proxy_strategy" in l]) == 3

    def test_explicit_strategy_matching_config_reports_nothing(self):
        """Setting the same value the config already has is not a change."""
        config = make_proxied_config(strategy="direct")
        changes = apply_proxy_overrides(
            config, proxy_url="http://localhost:9090", strategy="direct")
        assert [l for l in changes if "proxy_strategy" in l] == []

    def test_explicit_priority_overrides_and_reports(self):
        config = make_proxied_config(priority="high")
        changes = apply_proxy_overrides(
            config, proxy_url="http://localhost:9090", priority="normal")
        assert config["agents"]["dm"]["llm"]["proxy_priority"] == "normal"
        assert any("proxy_priority" in line for line in changes)

    def test_strategy_without_proxy_url_applies_to_proxied_agents_only(self):
        """--strategy alone retargets configs already routed via proxy;
        plain-provider agents are untouched."""
        config = make_proxied_config(strategy="batch")
        config["agents"]["players"][1]["llm"] = {
            "provider": "openai", "model": "gpt-5-mini"}

        apply_proxy_overrides(config, strategy="direct")

        assert config["agents"]["dm"]["llm"]["proxy_strategy"] == "direct"
        assert "proxy_strategy" not in config["agents"]["players"][1]["llm"]
        assert config["agents"]["players"][1]["llm"]["provider"] == "openai"

    def test_proxy_url_change_is_reported(self):
        config = make_proxied_config()
        changes = apply_proxy_overrides(config, proxy_url="http://other:8000")
        assert config["agents"]["dm"]["llm"]["proxy_url"] == "http://other:8000"
        assert any("proxy_url" in line for line in changes)

    def test_provider_switch_is_reported(self):
        config = make_config()
        changes = apply_proxy_overrides(config, proxy_url="http://localhost:9090")
        assert any("provider" in line and "batch_proxy" in line
                   for line in changes)

    def test_preserves_underlying_provider_on_reproxy(self):
        """Mixed-provider pre-proxied configs keep their underlying provider."""
        config = make_proxied_config()
        config["agents"]["players"][0]["llm"]["underlying_provider"] = "gemini"

        apply_proxy_overrides(config, proxy_url="http://localhost:9090",
                              strategy="direct")
        assert (config["agents"]["players"][0]["llm"]["underlying_provider"]
                == "gemini")

    def test_covers_enemies_and_legacy_enemy_agents(self):
        for key in ("enemies", "enemy_agents"):
            config = make_config()
            config["agents"][key] = {
                "llm": {"provider": "openai", "model": "gpt-5-mini",
                        "proxy_strategy": "direct"}}
            apply_proxy_overrides(config, proxy_url="http://localhost:9090")
            enemy_llm = config["agents"][key]["llm"]
            assert enemy_llm["provider"] == "batch_proxy"
            assert enemy_llm["proxy_strategy"] == "direct", key

    def test_no_agents_key_is_noop(self):
        config = {"session_name": "x"}
        changes = apply_proxy_overrides(config, proxy_url="http://localhost:9090")
        assert config == {"session_name": "x"}
        assert changes == []


class TestEffectiveRoutingReport:

    def test_reports_each_agent_with_strategy_source(self):
        config = make_proxied_config(strategy="direct")
        lines = effective_routing_report(config)

        # one line per agent (dm + 2 players)
        agent_lines = [l for l in lines if "strategy" in l]
        assert len(agent_lines) == 3
        assert any("dm" in l and "direct" in l and "config" in l
                   for l in agent_lines)
        assert any("Alice" in l for l in agent_lines)

    def test_absent_strategy_flagged_as_provider_default(self):
        config = make_config()
        apply_proxy_overrides(config, proxy_url="http://localhost:9090")
        lines = effective_routing_report(config)
        assert any("auto" in l and "default" in l for l in lines)

    def test_non_proxy_agent_shows_plain_provider(self):
        config = make_config()
        lines = effective_routing_report(config)
        assert any("openai" in l and "gpt-5-mini" in l for l in lines)

    def test_env_fallback_layer_surfaced(self, monkeypatch):
        monkeypatch.setenv("LLM_PROXY_MODE", "batch")
        config = make_proxied_config()
        lines = effective_routing_report(config)
        assert any("LLM_PROXY_MODE" in l for l in lines)

    def test_no_env_no_env_lines(self, monkeypatch):
        for var in ("LLM_PROXY_MODE", "USE_LLM_PROXY", "LLM_PROXY_URL"):
            monkeypatch.delenv(var, raising=False)
        config = make_proxied_config()
        lines = effective_routing_report(config)
        assert not any("LLM_PROXY_MODE" in l or "USE_LLM_PROXY" in l
                       for l in lines)


class TestValidateSessionConfig:

    def test_valid_config_passes(self):
        assert validate_session_config(make_config()) == []

    def test_missing_required_field(self):
        config = make_config()
        del config["max_turns"]
        errors = validate_session_config(config)
        assert any("max_turns" in e for e in errors)

    def test_missing_dm(self):
        config = make_config()
        del config["agents"]["dm"]
        errors = validate_session_config(config)
        assert any("dm" in e for e in errors)

    def test_empty_players(self):
        config = make_config()
        config["agents"]["players"] = []
        errors = validate_session_config(config)
        assert any("player" in e.lower() for e in errors)

    def test_deprecated_initial_clocks(self):
        config = make_config()
        config["scenario"] = {"initial_clocks": []}
        errors = validate_session_config(config)
        assert any("initial_clocks" in e for e in errors)

    def test_enemy_agents_requires_tactical_module(self):
        config = make_config(enemy_agents_enabled=True,
                             tactical_module_enabled=False)
        errors = validate_session_config(config)
        assert any("tactical_module_enabled" in e for e in errors)

    def test_player_missing_llm(self):
        config = make_config()
        del config["agents"]["players"][0]["llm"]
        errors = validate_session_config(config)
        assert any("llm" in e for e in errors)

    def test_deprecated_void_score(self):
        config = make_config()
        config["agents"]["players"][0]["void_score"] = 3
        errors = validate_session_config(config)
        assert any("void_score" in e for e in errors)

    def test_void_out_of_range(self):
        config = make_config()
        config["agents"]["players"][0]["void"] = 11
        errors = validate_session_config(config)
        assert any("void" in e for e in errors)

    def test_unknown_weapon_rejected(self):
        config = make_config()
        config["agents"]["players"][0]["equipped_weapons"] = {
            "primary": "definitely_not_a_weapon_xyz"}
        errors = validate_session_config(config)
        assert any("definitely_not_a_weapon_xyz" in e for e in errors)

    def test_fists_is_implicitly_valid(self):
        config = make_config()
        config["agents"]["players"][0]["equipped_weapons"] = {"primary": "fists"}
        assert validate_session_config(config) == []

    def test_clock_missing_meanings(self):
        config = make_config(starting_clocks=[
            {"name": "Doom", "current_ticks": 0, "max_ticks": 8}])
        errors = validate_session_config(config)
        assert any("advance_meaning" in e for e in errors)

    def test_clock_current_exceeds_max(self):
        config = make_config(starting_clocks=[
            {"name": "Doom", "current_ticks": 9, "max_ticks": 8,
             "advance_meaning": "worse", "regress_meaning": "better"}])
        errors = validate_session_config(config)
        assert any("Doom" in e or "current" in e.lower() for e in errors)

    def test_multiple_terminal_clocks_rejected(self):
        clock = {"current_ticks": 0, "max_ticks": 8,
                 "advance_meaning": "worse", "regress_meaning": "better",
                 "is_terminal_clock": True, "filled_consequence": "ends"}
        config = make_config(starting_clocks=[
            dict(clock, name="A"), dict(clock, name="B")])
        errors = validate_session_config(config)
        assert any("terminal" in e.lower() for e in errors)

    def test_terminal_clock_requires_filled_consequences(self):
        config = make_config(starting_clocks=[
            {"name": "A", "current_ticks": 0, "max_ticks": 8,
             "advance_meaning": "worse", "regress_meaning": "better",
             "is_terminal_clock": True, "filled_consequence": "ends"},
            {"name": "B", "current_ticks": 0, "max_ticks": 8,
             "advance_meaning": "worse", "regress_meaning": "better"},
        ])
        errors = validate_session_config(config)
        assert any("filled_consequence" in e for e in errors)

    def test_invalid_terminal_outcome(self):
        config = make_config(starting_clocks=[
            {"name": "A", "current_ticks": 0, "max_ticks": 8,
             "advance_meaning": "worse", "regress_meaning": "better",
             "is_terminal_clock": True, "filled_consequence": "ends",
             "terminal_outcome": "stalemate"}])
        errors = validate_session_config(config)
        assert any("terminal_outcome" in e for e in errors)

    def test_vendor_spawn_frequency_bounds(self):
        config = make_config(vendor_spawn_frequency=-2)
        errors = validate_session_config(config)
        assert any("vendor_spawn_frequency" in e for e in errors)

    def test_character_ref_players_skip_field_checks(self):
        config = make_config()
        config["agents"]["players"][0] = {"character_ref": "Alice Prime"}
        assert validate_session_config(config) == []

    def test_path_included_in_errors_when_given(self):
        config = make_config()
        del config["max_turns"]
        errors = validate_session_config(config, path="foo/bar.json")
        assert any("bar.json" in e for e in errors)


class TestSharedConstants:

    def test_log_level_choices_complete(self):
        assert set(LOG_LEVEL_CHOICES) == {
            "TRACE", "DEBUG", "LLM", "INFO", "WARNING", "ERROR"}

    def test_proxy_strategy_choices(self):
        assert set(PROXY_STRATEGY_CHOICES) == {"auto", "direct", "batch"}
