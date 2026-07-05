"""
Unit tests for session configuration validation.

The error checks live in aeonisk.multiagent.launch_config.
validate_session_config — the same function the session entry points run
at launch time — so tests and runtime behavior cannot drift. This file
sweeps every shipped config through that validator, plus keeps the
advisory (skip-only) checks that are recommendations rather than errors.

Negative tests (validator catches malformed configs) live in
tests/unit/test_launch_config.py.
"""

import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.launch_config import validate_session_config


# Test fixtures directory
SESSION_CONFIGS_DIR = Path(__file__).parent.parent.parent / "scripts" / "session_configs"


def get_all_session_configs():
    """Get all session config JSON files (excluding character_library.json)."""
    configs = []
    # Get configs from root directory
    for config_file in SESSION_CONFIGS_DIR.glob("*.json"):
        if config_file.name != "character_library.json":
            configs.append(config_file)

    # Get configs from ml_training_scenarios subdirectories
    ml_scenarios_dir = SESSION_CONFIGS_DIR / "ml_training_scenarios"
    if ml_scenarios_dir.exists():
        for config_file in ml_scenarios_dir.glob("*/*.json"):
            configs.append(config_file)

    # Get corpus generation configs
    corpus_v2_dir = SESSION_CONFIGS_DIR / "corpus_v2"
    if corpus_v2_dir.exists():
        configs.extend(corpus_v2_dir.glob("*.json"))

    corpus_v3_dir = SESSION_CONFIGS_DIR / "corpus_v3"
    if corpus_v3_dir.exists():
        configs.extend(corpus_v3_dir.glob("*.json"))

    return configs


def load_config(config_path: Path) -> dict:
    """Load and parse a session config JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


class TestSessionConfigValidation:
    """Every shipped config must pass the runtime validator clean."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_valid_json(self, config_path):
        """All session configs must be valid JSON objects."""
        with open(config_path, 'r') as f:
            data = json.load(f)
        assert isinstance(data, dict), f"{config_path.name} must be a JSON object"

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_passes_runtime_validator(self, config_path):
        """The launch-time validator (required fields, deprecated patterns,
        tactical dependencies, character schema, weapon library, clock
        format) must report zero errors for every shipped config."""
        config = load_config(config_path)
        errors = validate_session_config(config, path=str(config_path))
        assert errors == [], (
            f"{config_path.name} failed launch validation:\n"
            + "\n".join(f"  ✗ {e}" for e in errors)
        )


class TestAdvisoryChecks:
    """Recommendations, not errors — these skip rather than fail."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_pronouns_present(self, config_path):
        """Characters should have pronouns field (desirable, not required)."""
        config = load_config(config_path)

        for idx, player in enumerate(config["agents"]["players"]):
            # Skip character_ref
            if "character_ref" in player:
                continue

            if "pronouns" not in player:
                pytest.skip(
                    f"{config_path.name}: Player {idx} ({player.get('name', 'unnamed')}) "
                    "missing 'pronouns' field (recommended but not required)"
                )

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_enemy_agent_config_structure(self, config_path):
        """If enemy_agent_config exists, recommended fields should be present."""
        config = load_config(config_path)

        if "enemy_agent_config" not in config:
            pytest.skip(f"{config_path.name} has no enemy_agent_config")

        enemy_config = config["enemy_agent_config"]

        recommended_fields = [
            "free_targeting_mode",
            "allow_groups",
            "max_enemies_per_combat"
        ]

        missing_fields = [f for f in recommended_fields if f not in enemy_config]
        if missing_fields:
            pytest.skip(
                f"{config_path.name}: enemy_agent_config missing recommended fields: {missing_fields} "
                "(not required but recommended)"
            )


def get_all_session_configs_recursive():
    """Every config under session_configs/ (all subdirs), for terminal-clock checks."""
    configs = []
    for config_file in SESSION_CONFIGS_DIR.rglob("*.json"):
        if config_file.name != "character_library.json":
            configs.append(config_file)
    return configs


class TestTerminalClockConfigs:
    """
    Forward guardrail: a config that authors a terminal clock is a drama-authored
    scenario, so it must declare its beat consequences. Legacy non-terminal configs
    are grandfathered (the engine fallback synthesizes their consequences at runtime
    -- see SceneClock.effective_consequence), so this rule does not touch them.

    Applies recursively to ALL config subdirectories (legacy dirs included),
    unlike the full validator sweep above, so it filters the validator's
    output to terminal-clock errors only.
    """

    @pytest.mark.parametrize("config_path", get_all_session_configs_recursive())
    def test_terminal_config_has_consequences_and_one_terminal(self, config_path):
        config = load_config(config_path)
        clocks = config.get("starting_clocks")
        if not clocks:
            pytest.skip(f"{config_path.name} has no starting_clocks")

        terminal = [c for c in clocks if isinstance(c, dict) and c.get("is_terminal_clock")]
        if not terminal:
            pytest.skip(f"{config_path.name} authors no terminal clock (grandfathered)")

        errors = [
            e for e in validate_session_config(config, path=str(config_path))
            if "terminal" in e.lower()
        ]
        assert errors == [], (
            f"{config_path.name} terminal-clock violations:\n"
            + "\n".join(f"  ✗ {e}" for e in errors)
        )


# Character library tests (will test once feature is implemented)
class TestCharacterLibrary:
    """Test character_library.json structure (if it exists)."""

    def test_character_library_exists(self):
        """Character library should exist after implementation."""
        char_lib_path = SESSION_CONFIGS_DIR / "character_library.json"
        if not char_lib_path.exists():
            pytest.skip("character_library.json not yet implemented")

        with open(char_lib_path, 'r') as f:
            lib = json.load(f)

        assert "characters" in lib, "character_library.json must have 'characters' field"
        assert isinstance(lib["characters"], list), "'characters' must be a list"

    def test_character_library_format(self):
        """Each character in library must have required fields."""
        char_lib_path = SESSION_CONFIGS_DIR / "character_library.json"
        if not char_lib_path.exists():
            pytest.skip("character_library.json not yet implemented")

        with open(char_lib_path, 'r') as f:
            lib = json.load(f)

        required_fields = ["name", "faction"]

        for idx, char in enumerate(lib["characters"]):
            for field in required_fields:
                assert field in char, f"Character {idx} missing required field '{field}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
