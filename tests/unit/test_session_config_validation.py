"""
Unit tests for session configuration validation.

Tests session config JSON files for:
- Required fields
- Valid JSON structure
- Deprecated field usage
- Tactical module dependencies
- Character schema compliance
"""

import json
import pytest
from pathlib import Path


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

    return configs


def load_config(config_path: Path) -> dict:
    """Load and parse a session config JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


class TestSessionConfigStructure:
    """Test basic session config structure and required fields."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_valid_json(self, config_path):
        """All session configs must be valid JSON."""
        with open(config_path, 'r') as f:
            data = json.load(f)
        assert isinstance(data, dict), f"{config_path.name} must be a JSON object"

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_required_fields_present(self, config_path):
        """All session configs must have required top-level fields."""
        config = load_config(config_path)
        required_fields = [
            "session_name",
            "max_turns",
            "party_size",
            "agents"
        ]
        for field in required_fields:
            assert field in config, f"{config_path.name} missing required field: {field}"

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_agents_structure(self, config_path):
        """Agents section must have dm and players."""
        config = load_config(config_path)
        assert "dm" in config["agents"], f"{config_path.name} missing agents.dm"
        assert "players" in config["agents"], f"{config_path.name} missing agents.players"
        assert isinstance(config["agents"]["players"], list), f"{config_path.name} agents.players must be a list"
        assert len(config["agents"]["players"]) > 0, f"{config_path.name} must have at least one player"


class TestDeprecatedFields:
    """Test for deprecated configuration patterns."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_no_deprecated_initial_clocks(self, config_path):
        """Configs should use root-level 'starting_clocks', not 'scenario.initial_clocks'."""
        config = load_config(config_path)

        # Check if deprecated scenario.initial_clocks exists
        if "scenario" in config and "initial_clocks" in config["scenario"]:
            pytest.fail(
                f"{config_path.name} uses deprecated 'scenario.initial_clocks'. "
                "Use root-level 'starting_clocks' instead."
            )


class TestTacticalModuleDependencies:
    """Test tactical module configuration consistency."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_enemy_agents_requires_tactical_module(self, config_path):
        """If enemy_agents_enabled=true, tactical_module_enabled must also be true."""
        config = load_config(config_path)

        enemy_agents_enabled = config.get("enemy_agents_enabled", False)
        tactical_module_enabled = config.get("tactical_module_enabled", False)

        if enemy_agents_enabled and not tactical_module_enabled:
            pytest.fail(
                f"{config_path.name}: enemy_agents_enabled=true requires tactical_module_enabled=true"
            )


class TestWeaponLibrary:
    """Test that weapons used in configs exist in codebase."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_weapons_exist_in_library(self, config_path):
        """All weapons referenced in configs must exist in weapons.py WEAPON_LIBRARY."""
        config = load_config(config_path)

        # Import weapon library
        import sys
        from pathlib import Path
        weapons_module_path = Path(__file__).parent.parent.parent / "scripts" / "aeonisk" / "multiagent"
        sys.path.insert(0, str(weapons_module_path))
        from weapons import WEAPON_LIBRARY

        # Collect all weapon references from players
        weapon_refs = []
        for idx, player in enumerate(config["agents"]["players"]):
            # Skip character_ref
            if "character_ref" in player:
                continue

            # Check equipped_weapons
            if "equipped_weapons" in player:
                for slot, weapon_id in player["equipped_weapons"].items():
                    if weapon_id and weapon_id != "fists":  # "fists" is implicit, not in library
                        weapon_refs.append((idx, player.get("name", "unnamed"), slot, weapon_id))

            # Check carried_weapons
            if "carried_weapons" in player:
                for weapon_id in player["carried_weapons"]:
                    if weapon_id and weapon_id != "fists":
                        weapon_refs.append((idx, player.get("name", "unnamed"), "carried", weapon_id))

        # Validate each weapon exists
        for idx, char_name, slot, weapon_id in weapon_refs:
            assert weapon_id in WEAPON_LIBRARY, (
                f"{config_path.name}: Player {idx} ({char_name}) has {slot} weapon '{weapon_id}' "
                f"not found in WEAPON_LIBRARY. Add it to scripts/aeonisk/multiagent/weapons.py"
            )


class TestCharacterFormat:
    """Test player character schema compliance."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_player_required_fields(self, config_path):
        """Each player must have required fields."""
        config = load_config(config_path)

        required_character_fields = ["name", "faction", "llm"]

        for idx, player in enumerate(config["agents"]["players"]):
            # Skip if using character_ref (will be tested separately once feature is implemented)
            if "character_ref" in player:
                continue

            for field in required_character_fields:
                assert field in player, (
                    f"{config_path.name}: Player {idx} missing required field '{field}'"
                )

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_void_field_standardization(self, config_path):
        """Players must use 'void' key, not deprecated 'void_score'."""
        config = load_config(config_path)

        for idx, player in enumerate(config["agents"]["players"]):
            # Skip character_ref
            if "character_ref" in player:
                continue

            # Fail if deprecated void_score is used
            if "void_score" in player:
                pytest.fail(
                    f"{config_path.name}: Player {idx} ({player.get('name', 'unnamed')}) "
                    "uses deprecated 'void_score' key. Use 'void' instead."
                )

            # Void field is optional (defaults to 0), but if present must be valid
            if "void" in player:
                void_value = player["void"]
                assert isinstance(void_value, int), (
                    f"{config_path.name}: Player {idx} 'void' must be integer"
                )
                assert 0 <= void_value <= 10, (
                    f"{config_path.name}: Player {idx} 'void' must be 0-10, got {void_value}"
                )

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_player_llm_structure(self, config_path):
        """Each player's LLM config must have provider and model."""
        config = load_config(config_path)

        for idx, player in enumerate(config["agents"]["players"]):
            # Skip if using character_ref
            if "character_ref" in player:
                continue

            assert "llm" in player, f"{config_path.name}: Player {idx} missing 'llm' config"
            llm = player["llm"]
            assert "provider" in llm, f"{config_path.name}: Player {idx} LLM missing 'provider'"
            assert "model" in llm, f"{config_path.name}: Player {idx} LLM missing 'model'"

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
    def test_personality_description_format(self, config_path):
        """If personality.description exists, it must be a string."""
        config = load_config(config_path)

        for idx, player in enumerate(config["agents"]["players"]):
            # Skip character_ref
            if "character_ref" in player:
                continue

            # Personality is optional
            if "personality" not in player:
                continue

            personality = player["personality"]
            if not isinstance(personality, dict):
                continue  # Non-dict personality handled elsewhere

            # description is optional, but if present must be a non-empty string
            if "description" in personality:
                desc = personality["description"]
                assert isinstance(desc, str), (
                    f"{config_path.name}: Player {idx} personality.description must be string"
                )
                assert len(desc) > 0, (
                    f"{config_path.name}: Player {idx} personality.description must not be empty"
                )


class TestVendorConfiguration:
    """Test vendor system configuration."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_vendor_spawn_frequency_valid(self, config_path):
        """vendor_spawn_frequency must be valid value (-1, 0, or positive int)."""
        config = load_config(config_path)

        if "vendor_spawn_frequency" in config:
            freq = config["vendor_spawn_frequency"]
            assert isinstance(freq, int), f"{config_path.name}: vendor_spawn_frequency must be integer"
            assert freq >= -1, f"{config_path.name}: vendor_spawn_frequency must be >= -1"


class TestEnemyConfiguration:
    """Test enemy agent configuration."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_enemy_agent_config_structure(self, config_path):
        """If enemy_agent_config exists, validate its structure (optional fields)."""
        config = load_config(config_path)

        if "enemy_agent_config" not in config:
            pytest.skip(f"{config_path.name} has no enemy_agent_config")

        enemy_config = config["enemy_agent_config"]

        # These fields are recommended but not strictly required
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


class TestStartingClocks:
    """Test starting_clocks configuration."""

    @pytest.mark.parametrize("config_path", get_all_session_configs())
    def test_starting_clocks_format(self, config_path):
        """If starting_clocks exists, validate format (supports both current/max and current_ticks/max_ticks)."""
        config = load_config(config_path)

        if "starting_clocks" not in config:
            pytest.skip(f"{config_path.name} has no starting_clocks")

        clocks = config["starting_clocks"]
        assert isinstance(clocks, list), f"{config_path.name}: starting_clocks must be a list"

        for idx, clock in enumerate(clocks):
            assert "name" in clock, f"{config_path.name}: Clock {idx} missing 'name'"

            # Support both formats: current/max (old) and current_ticks/max_ticks (new)
            has_old_format = "current" in clock and "max" in clock
            has_new_format = "current_ticks" in clock and "max_ticks" in clock

            assert has_old_format or has_new_format, (
                f"{config_path.name}: Clock {idx} must have either (current/max) or (current_ticks/max_ticks)"
            )

            if has_new_format:
                current = clock["current_ticks"]
                maximum = clock["max_ticks"]
            else:
                current = clock["current"]
                maximum = clock["max"]

            assert isinstance(current, int), f"{config_path.name}: Clock {idx} current value must be int"
            assert isinstance(maximum, int), f"{config_path.name}: Clock {idx} max value must be int"
            assert 0 <= current <= maximum, (
                f"{config_path.name}: Clock {idx} current ({current}) must be between 0 and max ({maximum})"
            )

            # Required fields for clock meaning (added after schema validation errors)
            assert "advance_meaning" in clock, (
                f"{config_path.name}: Clock {idx} ('{clock.get('name', 'unnamed')}') missing required 'advance_meaning' field"
            )
            assert "regress_meaning" in clock, (
                f"{config_path.name}: Clock {idx} ('{clock.get('name', 'unnamed')}') missing required 'regress_meaning' field"
            )

            # Validate advance_meaning and regress_meaning are non-empty strings
            assert isinstance(clock["advance_meaning"], str) and clock["advance_meaning"].strip(), (
                f"{config_path.name}: Clock {idx} 'advance_meaning' must be non-empty string"
            )
            assert isinstance(clock["regress_meaning"], str) and clock["regress_meaning"].strip(), (
                f"{config_path.name}: Clock {idx} 'regress_meaning' must be non-empty string"
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
    """

    @pytest.mark.parametrize("config_path", get_all_session_configs_recursive())
    def test_terminal_config_has_consequences_and_one_terminal(self, config_path):
        config = load_config(config_path)
        clocks = config.get("starting_clocks")
        if not clocks:
            pytest.skip(f"{config_path.name} has no starting_clocks")

        terminal = [c for c in clocks if c.get("is_terminal_clock")]
        if not terminal:
            pytest.skip(f"{config_path.name} authors no terminal clock (grandfathered)")

        # Exactly one terminal clock resolves the scene -- the engine takes the first.
        assert len(terminal) == 1, (
            f"{config_path.name}: {len(terminal)} terminal clocks "
            f"({[c.get('name') for c in terminal]}); a scene resolves on exactly one"
        )

        # A scenario serious enough to define an ending must define what each beat does.
        for idx, clock in enumerate(clocks):
            cons = clock.get("filled_consequence", "")
            assert isinstance(cons, str) and cons.strip(), (
                f"{config_path.name}: terminal-clock config but clock {idx} "
                f"('{clock.get('name', 'unnamed')}') has no filled_consequence"
            )

        # terminal_outcome, if present, must be a valid session outcome.
        outcome = terminal[0].get("terminal_outcome", "victory")
        assert outcome in ("victory", "defeat", "draw"), (
            f"{config_path.name}: invalid terminal_outcome '{outcome}'"
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
