"""Drift guard for the config-schema registry.

The registry (`aeonisk.multiagent.config_schema`) is the single source of truth for the
session-config surface. These tests fail loudly when code and registry diverge:

  * every top-level key the CODE reads off the session `config` has a `FieldSpec`
    (so a newly-read key can't silently escape the schema / audit / editor);
  * a spot-checked set of defaults matches the code's inline defaults;
  * the values the validator derives from the registry still equal the historical
    hardcoded ones (behavior-preserving rewire);
  * the registry itself is internally consistent.

This mirrors the spirit of test_schema_drift.py for the config surface.
"""
import re
from pathlib import Path

import pytest

from aeonisk.multiagent import config_schema as cs
from aeonisk.multiagent import launch_config as lc

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "scripts" / "aeonisk" / "multiagent"

# Files that read the session config directly (receiver literally `config`/`self.config`).
_CODE_FILES = [
    _SRC / "session.py",
    _SRC / "dm.py",
    _SRC / "launch_config.py",
    _SRC / "mechanics.py",
]

# Keys matched by the grep that are NOT top-level session-config keys — e.g. reads on a
# same-named local, or keys that live under a nested object. Keep this list SHORT and
# justified; the point of the test is to force new keys into the schema, not to hide them.
_KNOWN_UNMODELED = {
    # nested LLM-block keys read via `config.get(...)` on an llm sub-dict named `config`
    "provider", "model", "temperature", "max_tokens",
    # per-item / per-vendor / per-clock local dicts sometimes named `config`
    "name", "description", "faction",
}

_RECEIVER_GET = re.compile(r"(?<![\w.])(?:self\.)?config\.get\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
_RECEIVER_IDX = re.compile(r"(?<![\w.])(?:self\.)?config\[\s*['\"]([a-z_][a-z0-9_]*)['\"]\s*\]")


def _keys_read_by_code() -> set:
    keys = set()
    for f in _CODE_FILES:
        text = f.read_text()
        keys |= set(_RECEIVER_GET.findall(text))
        keys |= set(_RECEIVER_IDX.findall(text))
    return keys


class TestCodeReadsAreModeled:
    def test_every_read_key_has_a_fieldspec(self):
        """Any top-level key the code reads off `config` must be in the registry."""
        read = _keys_read_by_code()
        known = cs.top_level_keys()
        missing = {
            k for k in read
            if k not in known and not cs.is_meta_key(k) and k not in _KNOWN_UNMODELED
        }
        assert not missing, (
            "Code reads session-config keys with no FieldSpec in config_schema.py "
            "(add them to CONFIG_SCHEMA, or to _KNOWN_UNMODELED if genuinely nested/local): "
            + ", ".join(sorted(missing))
        )


class TestDefaultsMatchCode:
    # Spot-check the flags/values whose inline defaults we assert don't drift.
    EXPECTED_DEFAULTS = {
        "max_turns": 50,
        "party_size": 2,
        "iff_enabled": False,
        "bonds_enabled": True,
        "dm_assessment_enabled": True,
        "tactical_module_enabled": False,
        "enemy_agents_enabled": False,
        "outcome_first_narration": False,
        "outcome_synthesis_attempts": 3,
        "party_capabilities_enabled": True,
        "party_chat_enabled": True,
        "vendor_spawn_frequency": -1,
        "enemy_agent_config.free_targeting_mode": True,
        "scenario.situation": "Something mysterious is happening",
        "scenario.altars[].quality": 5,
        "persistent_vendors[].greeting": "Looking to trade?",
        "starting_checkpoints[].faction": "Neutral",
        "generate_bonds.min_bonds": 2,
        "generate_bonds.max_bonds": 5,
        "names_mcp.from_pool": True,
        "discovery_limits.max_seeds_per_session": 3,
        "discovery_limits.max_currency_per_session": 50,
    }

    @pytest.mark.parametrize("path,expected", EXPECTED_DEFAULTS.items())
    def test_default(self, path, expected):
        spec = cs.by_path(path)
        assert spec is not None, f"no FieldSpec for {path}"
        assert path not in cs.KNOWN_DIVERGENT, f"{path} is divergent; don't assert its default"
        assert spec.default == expected, (
            f"{path} default {spec.default!r} != code default {expected!r}")


class TestValidatorParity:
    def test_required_top_level_unchanged(self):
        assert lc._REQUIRED_TOP_LEVEL == [
            "session_name", "max_turns", "party_size", "agents"]

    def test_enemy_dependency_pair(self):
        assert lc._ENEMY_DEPENDS_ON == "tactical_module_enabled"

    def test_known_deprecations_present(self):
        deps = cs.deprecations()
        assert deps.get("scenario.initial_clocks") == "starting_clocks"
        assert deps.get("agents.players[].void_score") == "void"
        assert deps.get("_scenario_hint") == "scenario_hint"
        assert deps.get("agents.enemy_agents") == "agents.enemies"

    def test_validator_still_flags_dependency(self):
        cfg = {
            "session_name": "x", "max_turns": 1, "party_size": 1,
            "agents": {"dm": {}, "players": [
                {"name": "A", "faction": "F", "llm": {"provider": "openai", "model": "m"}}]},
            "enemy_agents_enabled": True,  # no tactical_module_enabled
        }
        errs = lc.validate_session_config(cfg)
        assert any("requires tactical_module_enabled" in e for e in errs)


class TestExplainConfig:
    BASE = {
        "session_name": "x", "max_turns": 3, "party_size": 1,
        "agents": {"dm": {}, "players": [
            {"name": "A", "faction": "Freeborn", "llm": {"provider": "openai", "model": "m"}}]},
    }

    def test_enforce_shows_magistrate_ledger(self):
        cfg = dict(self.BASE, post_resolution_adjudication="enforce")
        out = cs.explain_config(cfg)
        assert "magistrate" in out
        # enforce with no gating surface → neutral teeth note, not a warning
        assert "DM may add teeth" in out or "add teeth" in out

    def test_enforce_with_checkpoint_has_no_teeth_note(self):
        cfg = dict(self.BASE, post_resolution_adjudication="enforce",
                   starting_checkpoints=[{"name": "Gate", "soulcredit_requirement": 0}])
        out = cs.explain_config(cfg)
        assert "gate movement at 1 SC checkpoint" in out
        assert "add teeth" not in out

    def test_default_off_flags_land_in_wont(self):
        out = cs.explain_config(self.BASE)  # nothing enabled
        assert "This session will NOT:" in out
        assert "tactical combat" in out
        # narrator-inline ledger is the default (no enforce)
        assert "narrator writes the SC/Void ledger inline" in out

    def test_has_teeth_detects_sc_locked_weapon(self):
        cfg = dict(self.BASE)
        cfg["agents"] = {"dm": {}, "players": [
            {"name": "A", "faction": "Freeborn", "llm": {"provider": "openai", "model": "m"},
             "equipped_weapons": {"primary": "debtbreaker_sidearm"}}]}
        assert cs.has_teeth(cfg) is True

    def test_has_teeth_false_without_gating(self):
        assert cs.has_teeth(self.BASE) is False


class TestRegistryIntegrity:
    def test_paths_unique(self):
        paths = [fs.path for fs in cs.CONFIG_SCHEMA]
        dupes = {p for p in paths if paths.count(p) > 1}
        assert not dupes, f"duplicate paths: {dupes}"

    def test_categories_valid(self):
        valid = {"identity", "agents", "party", "mechanics", "scenario", "clocks",
                 "checkpoints", "enemies", "economy", "bonds", "names", "meta",
                 "experiment"}
        bad = {fs.path: fs.category for fs in cs.CONFIG_SCHEMA if fs.category not in valid}
        assert not bad, f"unknown categories: {bad}"

    def test_deprecated_specs_have_replacement(self):
        bad = [fs.path for fs in cs.CONFIG_SCHEMA
               if fs.status == "deprecated" and not fs.deprecated_by]
        assert not bad, f"deprecated specs missing deprecated_by: {bad}"

    def test_vestigial_specs_have_note(self):
        bad = [fs.path for fs in cs.CONFIG_SCHEMA
               if fs.status == "vestigial" and not fs.note]
        assert not bad, f"vestigial specs missing note: {bad}"

    def test_known_divergent_paths_exist(self):
        for p in cs.KNOWN_DIVERGENT:
            assert cs.by_path(p) is not None, f"KNOWN_DIVERGENT path {p} not in schema"

    def test_recommended_are_the_research_flags(self):
        assert cs.recommended_overrides() == {
            "tactical_module_enabled": True,
            "enemy_agents_enabled": True,
            "outcome_first_narration": True,
            "iff_enabled": True,
            "post_resolution_adjudication": "enforce",
        }


class TestExplainShape:
    """The size/cost header must be read off the config, never narrated."""

    BASE_CFG = {
        "session_name": "probe", "max_turns": 2, "party_size": 1,
        "agents": {
            "dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
            "players": [{"name": "Sera",
                         "llm": {"provider": "openai", "model": "gpt-5-mini"}}],
        },
    }

    def test_states_rounds_party_and_scale(self):
        out = cs.explain_config(self.BASE_CFG)
        assert "2 round(s) max" in out
        assert "1 player(s)" in out
        assert "smoke-sized" in out

    def test_full_length_above_smoke_threshold(self):
        cfg = {**self.BASE_CFG, "max_turns": 10}
        assert "full-length" in cs.explain_config(cfg)

    def test_names_the_model_each_agent_uses(self):
        out = cs.explain_config(self.BASE_CFG)
        assert "openai/gpt-5-mini" in out
        assert "DM" in out and "Sera" in out

    def test_unwraps_batch_proxy_to_the_real_provider(self):
        cfg = {**self.BASE_CFG, "agents": {
            "dm": {"llm": {"provider": "batch_proxy", "underlying_provider": "openai",
                           "model": "gpt-5-mini"}},
            "players": self.BASE_CFG["agents"]["players"]}}
        assert "proxy→openai/gpt-5-mini" in cs.explain_config(cfg)

    def test_warns_when_interactive(self):
        """enable_human_interface defaults true and blocks on stdin — say so."""
        cfg = {**self.BASE_CFG, "enable_human_interface": True}
        assert "[Observer]>" in cs.explain_config(cfg)
        assert "[Observer]>" not in cs.explain_config(
            {**self.BASE_CFG, "enable_human_interface": False})
