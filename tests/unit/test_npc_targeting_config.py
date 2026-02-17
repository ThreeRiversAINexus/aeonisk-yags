"""
Unit tests for NPC targeting test session config.

Validates the three-faction standoff config has all required elements
and passes the same validation as test_session_config_validation.py.
"""

import pytest
import json
from pathlib import Path


CONFIG_PATH = Path("scripts/session_configs/experiment/npc_targeting_test/session_config_npc_targeting_openai_gpt5mini.json")


@pytest.fixture
def config():
    """Load the NPC targeting test config."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


class TestConfigLoads:
    """Config JSON is valid and loadable."""

    def test_config_file_exists(self):
        assert CONFIG_PATH.exists(), f"Config file not found: {CONFIG_PATH}"

    def test_config_loads_valid_json(self, config):
        assert isinstance(config, dict)
        assert "session_name" in config
        assert "agents" in config

    def test_required_fields_present(self, config):
        """Session config has all required fields (matches test_session_config_validation)."""
        for field in ["session_name", "max_turns", "party_size", "agents"]:
            assert field in config, f"Missing required field: {field}"
        assert config["party_size"] == 2
        assert config["force_combat"] is True

    def test_agents_structure(self, config):
        """Agents section has dm and players (not 'characters')."""
        assert "dm" in config["agents"]
        assert "players" in config["agents"]
        assert isinstance(config["agents"]["players"], list)
        assert len(config["agents"]["players"]) > 0

    def test_tactical_module_dependencies(self, config):
        """enemy_agents_enabled requires tactical_module_enabled."""
        if config.get("enemy_agents_enabled", False):
            assert config.get("tactical_module_enabled", False), \
                "enemy_agents_enabled=true requires tactical_module_enabled=true"


class TestConfigPlayers:
    """Player characters are properly structured."""

    def test_player_required_fields(self, config):
        """Each player has name, faction, llm."""
        for idx, player in enumerate(config["agents"]["players"]):
            assert "name" in player, f"Player {idx} missing 'name'"
            assert "faction" in player, f"Player {idx} missing 'faction'"
            assert "llm" in player, f"Player {idx} missing 'llm'"
            assert "provider" in player["llm"]
            assert "model" in player["llm"]

    def test_player_pronouns(self, config):
        """Players have pronouns."""
        for idx, player in enumerate(config["agents"]["players"]):
            assert "pronouns" in player, f"Player {idx} missing 'pronouns'"

    def test_player_goals_drive_targeting(self, config):
        """PC goals explicitly mention attacking NPCs or enemies."""
        players = config["agents"]["players"]
        # Sera should have goals about attacking NPCs
        sera = players[0]
        sera_goals = " ".join(sera["goals"]).lower()
        assert "freeborn" in sera_goals or "npc" in sera_goals, \
            "Sera's goals should mention targeting Freeborn NPCs"

        # Ash should have goals about attacking enemies
        ash = players[1]
        ash_goals = " ".join(ash["goals"]).lower()
        assert "tempest" in ash_goals, \
            "Ash's goals should mention targeting Tempest enemies"

    def test_no_deprecated_void_score(self, config):
        """Players use 'void', not deprecated 'void_score'."""
        for idx, player in enumerate(config["agents"]["players"]):
            assert "void_score" not in player, \
                f"Player {idx} uses deprecated 'void_score'"

    def test_weapons_exist_in_library(self, config):
        """All player weapon references exist in WEAPON_LIBRARY."""
        from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY
        for idx, player in enumerate(config["agents"]["players"]):
            if "equipped_weapons" in player:
                for slot, weapon_id in player["equipped_weapons"].items():
                    if weapon_id:
                        assert weapon_id in WEAPON_LIBRARY, \
                            f"Player {idx} weapon '{weapon_id}' not in WEAPON_LIBRARY"


class TestConfigEnemies:
    """Config has correct enemy setup."""

    def test_has_initial_enemies(self, config):
        assert "initial_enemies" in config
        assert len(config["initial_enemies"]) == 4

    def test_two_hostile_factions_present(self, config):
        """Enemies belong to two hostile factions."""
        factions = set(e["faction"] for e in config["initial_enemies"])
        assert "Pantheon Security" in factions
        assert "Tempest Industries" in factions

    def test_each_faction_has_two_enemies(self, config):
        """Each faction has 2 grunts."""
        pantheon = [e for e in config["initial_enemies"] if e["faction"] == "Pantheon Security"]
        tempest = [e for e in config["initial_enemies"] if e["faction"] == "Tempest Industries"]
        assert len(pantheon) == 2
        assert len(tempest) == 2

    def test_enemy_tactics_mention_npcs(self, config):
        """Enemy tactics should mention targeting NPCs."""
        all_tactics = " ".join(e.get("tactics", "") for e in config["initial_enemies"]).lower()
        assert "freeborn" in all_tactics or "npc" in all_tactics, \
            "Enemy tactics should mention targeting Freeborn NPCs"


class TestConfigNPCs:
    """Config has correct NPC setup."""

    def test_has_initial_npcs(self, config):
        assert "initial_npcs" in config
        assert len(config["initial_npcs"]) == 2

    def test_npcs_are_freeborn(self, config):
        """NPCs are Freeborn faction."""
        for npc in config["initial_npcs"]:
            assert npc["faction"] == "Freeborn"

    def test_npcs_are_armed(self, config):
        """NPCs have armed_neutral threat level."""
        for npc in config["initial_npcs"]:
            assert npc["threat_level"] == "armed_neutral"

    def test_npcs_have_weapons(self, config):
        """NPCs have explicit weapon assignments."""
        for npc in config["initial_npcs"]:
            assert "weapons" in npc
            assert len(npc["weapons"]) > 0

    def test_npc_weapons_valid(self, config):
        """NPC weapons reference valid WEAPON_LIBRARY keys."""
        from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY
        for npc in config["initial_npcs"]:
            for weapon_key in npc["weapons"]:
                assert weapon_key in WEAPON_LIBRARY, f"Invalid weapon key: {weapon_key}"

    def test_npcs_have_skills(self, config):
        """NPCs have combat skills defined."""
        for npc in config["initial_npcs"]:
            assert "skills" in npc
            assert len(npc["skills"]) > 0
