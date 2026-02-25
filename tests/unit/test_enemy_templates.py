"""
Unit tests for enemy templates.

TDD approach: These tests define expected behavior for enemy templates,
particularly around weapon validation and robot enemy types.
"""

import pytest
from scripts.aeonisk.multiagent.enemy_templates import ENEMY_TEMPLATES
from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY, get_weapon


class TestEnemyWeaponValidation:
    """Test that all enemy template weapons exist in WEAPON_LIBRARY."""

    def test_all_enemy_weapons_valid(self):
        """
        All weapons referenced in enemy templates must exist in WEAPON_LIBRARY.

        This is CRITICAL - if an enemy template references a non-existent weapon,
        the game should crash during enemy spawn (not silently fall back to fists).
        """
        errors = []

        for template_name, template_data in ENEMY_TEMPLATES.items():
            weapons_list = template_data.get("weapons", [])

            for weapon_id in weapons_list:
                if weapon_id not in WEAPON_LIBRARY:
                    errors.append(
                        f"Template '{template_name}' references missing weapon '{weapon_id}'"
                    )

        assert not errors, "\n".join([
            "Enemy templates reference non-existent weapons:",
            *errors,
            "\nAll enemy weapons must exist in WEAPON_LIBRARY"
        ])

    def test_enemy_weapons_can_be_loaded(self):
        """Test that get_weapon() works for all enemy weapons."""
        for template_name, template_data in ENEMY_TEMPLATES.items():
            weapons_list = template_data.get("weapons", [])

            for weapon_id in weapons_list:
                # This should not raise KeyError
                weapon = get_weapon(weapon_id)
                assert weapon is not None, \
                       f"Template '{template_name}' weapon '{weapon_id}' returned None"
                assert weapon.name, f"Weapon '{weapon_id}' has no name"


class TestRobotEnemyTemplates:
    """Test robot enemy templates from Gear & Tech Reference."""

    def test_robot_enemy_templates_exist(self):
        """Robot enemies should be available for DM spawning."""
        required_robots = [
            "security_drone",
            "seedwalker_heavy",
            "voidcradle_antibot"
        ]

        for robot_id in required_robots:
            assert robot_id in ENEMY_TEMPLATES, \
                   f"Missing robot template: {robot_id}"

    def test_security_drone_stats(self):
        """Security drone should be flying surveillance/attack bot."""
        if "security_drone" not in ENEMY_TEMPLATES:
            pytest.skip("security_drone not yet implemented")

        drone = ENEMY_TEMPLATES["security_drone"]

        # Should be fragile but evasive
        assert drone["health"] <= 30, "Drones should be low HP"

        # Should have ranged weapons
        weapons = drone.get("weapons", [])
        assert len(weapons) > 0, "Drone should have weapons"

        # At least one ranged weapon
        has_ranged = any(
            WEAPON_LIBRARY[w].is_ranged
            for w in weapons
            if w in WEAPON_LIBRARY
        )
        assert has_ranged, "Drone should have ranged weapons"

    def test_seedwalker_heavy_stats(self):
        """Seedwalker should be heavy utility bot."""
        if "seedwalker_heavy" not in ENEMY_TEMPLATES:
            pytest.skip("seedwalker_heavy not yet implemented")

        walker = ENEMY_TEMPLATES["seedwalker_heavy"]

        # Should be durable
        assert walker["health"] >= 40, "Heavy walker should have high HP"

        # Should be slow (low move speed)
        assert walker["move"] <= 10, "Heavy walker should be slow"

    def test_voidcradle_antibot_stats(self):
        """Voidcradle should be anti-ritual bot."""
        if "voidcradle_antibot" not in ENEMY_TEMPLATES:
            pytest.skip("voidcradle_antibot not yet implemented")

        antibot = ENEMY_TEMPLATES["voidcradle_antibot"]

        # Should have void corruption
        assert antibot["void_score"] >= 1, "Antibot should have void score"


class TestEnemyTemplateStructure:
    """Test that all enemy templates have required fields."""

    def test_all_templates_have_required_fields(self):
        """All templates must have required fields for combat."""
        required_fields = [
            "description",
            "attributes",
            "skills",
            "health",
            "weapons",
            "armor"
        ]

        errors = []
        for template_name, template_data in ENEMY_TEMPLATES.items():
            for field in required_fields:
                if field not in template_data:
                    errors.append(f"Template '{template_name}' missing field '{field}'")

        assert not errors, "\n".join(errors)

    def test_weapons_field_is_list(self):
        """Weapons field should be a list of weapon IDs."""
        for template_name, template_data in ENEMY_TEMPLATES.items():
            weapons = template_data.get("weapons", [])
            assert isinstance(weapons, list), \
                   f"Template '{template_name}' weapons should be list, got {type(weapons)}"
            assert len(weapons) > 0, \
                   f"Template '{template_name}' should have at least one weapon"

    def test_health_values_reasonable(self):
        """Health values should be in reasonable range."""
        for template_name, template_data in ENEMY_TEMPLATES.items():
            health = template_data.get("health", 0)
            assert 10 <= health <= 200, \
                   f"Template '{template_name}' health {health} out of reasonable range (10-200)"

    def test_all_templates_have_engagement_stance(self):
        """Every template must have an engagement_stance field."""
        valid_stances = {"lethal", "capture", "adaptive"}
        errors = []
        for template_name, template_data in ENEMY_TEMPLATES.items():
            if "engagement_stance" not in template_data:
                errors.append(f"Template '{template_name}' missing 'engagement_stance'")
            elif template_data["engagement_stance"] not in valid_stances:
                errors.append(
                    f"Template '{template_name}' has invalid stance "
                    f"'{template_data['engagement_stance']}' (must be one of {valid_stances})"
                )
        assert not errors, "\n".join(errors)


class TestCaptureTeamTemplate:
    """Tests for the capture_team enemy template."""

    def test_capture_team_template_exists(self):
        """capture_team template should be available for spawning."""
        assert "capture_team" in ENEMY_TEMPLATES

    def test_capture_team_has_stun_weapons(self):
        """All capture_team weapons should be non-lethal (stun damage type)."""
        template = ENEMY_TEMPLATES["capture_team"]
        weapons = template["weapons"]
        assert len(weapons) > 0, "capture_team should have weapons"

        for weapon_id in weapons:
            weapon = WEAPON_LIBRARY[weapon_id]
            assert weapon.damage_type == "stun", \
                   f"capture_team weapon '{weapon_id}' has damage_type '{weapon.damage_type}', expected 'stun'"

    def test_capture_team_engagement_stance(self):
        """capture_team should have 'capture' engagement stance."""
        assert ENEMY_TEMPLATES["capture_team"]["engagement_stance"] == "capture"

    def test_capture_team_has_required_fields(self):
        """capture_team should have all required template fields."""
        required = ["description", "attributes", "skills", "health", "weapons", "armor"]
        template = ENEMY_TEMPLATES["capture_team"]
        for field in required:
            assert field in template, f"capture_team missing '{field}'"


class TestEnforcerTemplate:
    """Tests for enforcer template updates."""

    def test_enforcer_has_shock_baton(self):
        """Enforcer should have shock_baton for non-lethal option."""
        weapons = ENEMY_TEMPLATES["enforcer"]["weapons"]
        assert "shock_baton" in weapons, \
               f"Enforcer weapons {weapons} should include 'shock_baton'"

    def test_enforcer_engagement_stance_adaptive(self):
        """Enforcer should have 'adaptive' engagement stance."""
        assert ENEMY_TEMPLATES["enforcer"]["engagement_stance"] == "adaptive"


class TestEngagementStanceValues:
    """Test specific engagement stance assignments."""

    def test_grunt_is_lethal(self):
        assert ENEMY_TEMPLATES["grunt"]["engagement_stance"] == "lethal"

    def test_elite_is_lethal(self):
        assert ENEMY_TEMPLATES["elite"]["engagement_stance"] == "lethal"

    def test_sniper_is_lethal(self):
        assert ENEMY_TEMPLATES["sniper"]["engagement_stance"] == "lethal"

    def test_boss_is_lethal(self):
        assert ENEMY_TEMPLATES["boss"]["engagement_stance"] == "lethal"

    def test_security_drone_is_adaptive(self):
        """Security drone has stun_gun already — should be adaptive."""
        assert ENEMY_TEMPLATES["security_drone"]["engagement_stance"] == "adaptive"

    def test_void_cultist_is_lethal(self):
        assert ENEMY_TEMPLATES["void_cultist"]["engagement_stance"] == "lethal"
