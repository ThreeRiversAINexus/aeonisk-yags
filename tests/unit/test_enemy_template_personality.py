"""
Tests for enemy template morale_behavior and character_brief fields.

TDD: Written BEFORE implementation.
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.enemy_templates import ENEMY_TEMPLATES


# Templates that should be production (not test) templates
PRODUCTION_TEMPLATES = [
    "grunt", "elite", "sniper", "boss", "void_cultist",
    "enforcer", "support", "ambusher",
    "security_drone", "seedwalker_heavy", "voidcradle_antibot"
]


class TestMoraleBehavior:
    """All production templates must have morale_behavior."""

    def test_all_templates_have_morale_behavior(self):
        for name in PRODUCTION_TEMPLATES:
            template = ENEMY_TEMPLATES[name]
            assert "morale_behavior" in template, \
                f"Template '{name}' missing morale_behavior"

    def test_grunt_morale_flee(self):
        assert ENEMY_TEMPLATES["grunt"]["morale_behavior"] == "flee_when_broken"

    def test_elite_morale_surrender(self):
        assert ENEMY_TEMPLATES["elite"]["morale_behavior"] == "surrender_if_cornered"

    def test_boss_morale_fight_to_death(self):
        assert ENEMY_TEMPLATES["boss"]["morale_behavior"] == "fight_to_death"

    def test_morale_behavior_valid_values(self):
        """All morale_behavior values must be one of the 3 valid options."""
        valid = {"flee_when_broken", "surrender_if_cornered", "fight_to_death"}
        for name in PRODUCTION_TEMPLATES:
            template = ENEMY_TEMPLATES[name]
            assert template["morale_behavior"] in valid, \
                f"Template '{name}' has invalid morale_behavior: {template['morale_behavior']}"


class TestCharacterBrief:
    """All production templates must have character_brief."""

    def test_all_templates_have_character_brief(self):
        for name in PRODUCTION_TEMPLATES:
            template = ENEMY_TEMPLATES[name]
            assert "character_brief" in template, \
                f"Template '{name}' missing character_brief"

    def test_character_brief_is_nonempty_string(self):
        for name in PRODUCTION_TEMPLATES:
            template = ENEMY_TEMPLATES[name]
            brief = template["character_brief"]
            assert isinstance(brief, str), \
                f"Template '{name}' character_brief should be str, got {type(brief)}"
            assert len(brief) > 10, \
                f"Template '{name}' character_brief too short: '{brief}'"


class TestSpawnerReadsFields:
    """Spawner should read morale_behavior and character_brief from template."""

    def test_spawn_reads_morale_from_template(self):
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        agent = spawn_enemy(
            template_key="elite",
            name="Test Elite",
            position_str="Near-Enemy",
        )
        assert agent.morale_behavior == "surrender_if_cornered"

    def test_spawn_reads_character_brief_from_template(self):
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        agent = spawn_enemy(
            template_key="elite",
            name="Test Elite",
            position_str="Near-Enemy",
        )
        assert agent.character_brief != ""
        assert len(agent.character_brief) > 10

    def test_spawn_morale_override_takes_precedence(self):
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy
        from scripts.aeonisk.multiagent.enemy_agent import Position

        agent = spawn_enemy(
            template_key="grunt",
            name="Test Grunt",
            position_str="Near-Enemy",
            personality_override="fight_to_death"
        )
        # personality_override maps to morale_behavior
        assert agent.morale_behavior == "fight_to_death"


class TestMoraleCheck:
    """check_morale() should use morale_behavior field."""

    def test_morale_check_uses_morale_behavior(self):
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        agent = spawn_enemy(
            template_key="elite",
            name="Test Elite",
            position_str="Near-Enemy",
        )
        assert agent.morale_behavior == "surrender_if_cornered"

        # Force a failed morale check by using a very high DC
        import random
        random.seed(42)  # Ensure deterministic rolls
        result = agent.check_morale(dc=100)  # DC 100 = guaranteed fail

        assert result["success"] is False
        assert result["action"] == "surrender"  # surrender_if_cornered → surrender
