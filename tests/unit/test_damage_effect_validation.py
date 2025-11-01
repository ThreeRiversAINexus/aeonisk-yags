"""
Unit tests for DamageEffect target ID validation.

Tests the @field_validator on DamageEffect.target to ensure:
1. Valid target IDs pass (tgt_xxxx format with exactly 4 alphanumeric chars)
2. Invalid target IDs fail (tgt_<name> patterns like tgt_heavy_gunners)
3. Non-tgt_ targets are allowed (for backward compatibility with character names)
"""

import pytest
from pydantic import ValidationError
from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


class TestDamageEffectTargetValidation:
    """Test suite for DamageEffect target ID format validation."""

    def test_valid_target_ids(self):
        """Valid target IDs should pass validation."""
        valid_ids = [
            "tgt_7a3f",
            "tgt_grpq",
            "tgt_3yp8",
            "tgt_ous1",
            "tgt_xe1g",
            "tgt_7qj8",
            "tgt_0000",  # All zeros is valid
            "tgt_zzzz",  # All letters is valid
            "tgt_123a",  # Mix is valid
        ]

        for target_id in valid_ids:
            damage = DamageEffect(
                target=target_id,
                base_damage=10,
                dealt=10
            )
            assert damage.target == target_id, f"Failed for valid ID: {target_id}"

    def test_invalid_target_ids_too_long(self):
        """Target IDs that are too long should fail validation."""
        invalid_ids = [
            "tgt_heavy_gunners",  # The bug pattern from logs
            "tgt_sniper_team",
            "tgt_elite_assault_squad",
            "tgt_12345",  # 5 chars instead of 4
            "tgt_abcdef",  # 6 chars instead of 4
        ]

        for target_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                DamageEffect(
                    target=target_id,
                    base_damage=10,
                    dealt=10
                )

            # Check that error message is helpful
            error_message = str(exc_info.value)
            assert "Invalid target ID format" in error_message, f"Missing helpful error for: {target_id}"
            assert "tgt_7a3f" in error_message, "Error should include example"
            assert "combatant list" in error_message, "Error should mention combatant list"

    def test_invalid_target_ids_too_short(self):
        """Target IDs that are too short should fail validation."""
        invalid_ids = [
            "tgt_",      # No chars after prefix
            "tgt_1",     # 1 char instead of 4
            "tgt_ab",    # 2 chars instead of 4
            "tgt_123",   # 3 chars instead of 4
        ]

        for target_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                DamageEffect(
                    target=target_id,
                    base_damage=10,
                    dealt=10
                )

            error_message = str(exc_info.value)
            assert "Invalid target ID format" in error_message

    def test_invalid_target_ids_wrong_chars(self):
        """Target IDs with uppercase or special chars should fail validation."""
        invalid_ids = [
            "tgt_7A3F",    # Uppercase
            "tgt_GRPQ",    # Uppercase
            "tgt_7a_f",    # Underscore in suffix
            "tgt_7a-f",    # Hyphen in suffix
            "tgt_7a.f",    # Period in suffix
        ]

        for target_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                DamageEffect(
                    target=target_id,
                    base_damage=10,
                    dealt=10
                )

            error_message = str(exc_info.value)
            assert "Invalid target ID format" in error_message

    def test_non_tgt_targets_allowed(self):
        """Non-tgt_ targets (character names) should be allowed for backward compatibility."""
        valid_names = [
            "Thresh Ireveth",
            "Ash Vex",
            "Heavy Gunners",  # Without tgt_ prefix, this is fine
            "Sniper Team",
            "enemy_1",
            "player",
        ]

        for name in valid_names:
            damage = DamageEffect(
                target=name,
                base_damage=10,
                dealt=10
            )
            assert damage.target == name, f"Failed for character name: {name}"

    def test_bug_reproduction_tgt_heavy_gunners(self):
        """Reproduce the exact bug from game_test_impossible_combat.log."""
        # This is the exact pattern that caused the bug
        with pytest.raises(ValidationError) as exc_info:
            DamageEffect(
                target="tgt_heavy_gunners",
                base_damage=15,
                dealt=15
            )

        error_message = str(exc_info.value)
        assert "tgt_heavy_gunners" in error_message
        assert "Invalid target ID format" in error_message
        assert "Do NOT use enemy names" in error_message

    def test_full_damage_effect_with_valid_id(self):
        """Test a complete DamageEffect with all fields and valid target ID."""
        damage = DamageEffect(
            target="tgt_7a3f",
            base_damage=15,
            soak=7,
            dealt=8,
            damage_type="kinetic"
        )

        assert damage.target == "tgt_7a3f"
        assert damage.base_damage == 15
        assert damage.soak == 7
        assert damage.dealt == 8
        assert damage.damage_type == "kinetic"

    def test_full_damage_effect_with_invalid_id(self):
        """Test that validation fails even with all other fields correct."""
        with pytest.raises(ValidationError) as exc_info:
            DamageEffect(
                target="tgt_elite_squad",  # Invalid - too long
                base_damage=15,
                soak=7,
                dealt=8,
                damage_type="kinetic"
            )

        error_message = str(exc_info.value)
        assert "Invalid target ID format" in error_message
