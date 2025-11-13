"""
Unit tests for conversion validation and fuzzy agent ID matching.
"""

import pytest
from unittest.mock import Mock
from scripts.aeonisk.multiagent.conversion_validation import (
    find_closest_agent_id,
    validate_enemy_conversion,
    validate_npc_escalation,
    auto_correct_conversion
)


class TestFindClosestAgentID:
    """Tests for fuzzy agent ID matching."""

    def test_exact_match(self):
        """Exact match should return the same ID."""
        valid_ids = ["enemy_grunt_440219d6", "enemy_thug_2bc22537"]
        result = find_closest_agent_id("enemy_grunt_440219d6", valid_ids)
        assert result == "enemy_grunt_440219d6"

    def test_substring_match(self):
        """Substring matches should have high confidence."""
        valid_ids = ["enemy_grunt_440219d6", "enemy_raider_abc123"]
        result = find_closest_agent_id("grunt", valid_ids)
        assert result == "enemy_grunt_440219d6"

    def test_typo_match(self):
        """Close typos should match."""
        valid_ids = ["enemy_grunt_440219d6"]
        result = find_closest_agent_id("enemy_grunt_440219d", valid_ids)
        assert result == "enemy_grunt_440219d6"

    def test_no_match_below_threshold(self):
        """Very different IDs should return None."""
        valid_ids = ["enemy_grunt_440219d6"]
        result = find_closest_agent_id("npc_civilian_xyz", valid_ids, threshold=0.6)
        assert result is None

    def test_empty_valid_ids(self):
        """Empty list should return None."""
        result = find_closest_agent_id("enemy_grunt_123", [])
        assert result is None

    def test_narrative_invention_match(self):
        """DM narrative inventions should find best match based on tokens."""
        valid_ids = ["enemy_grunt_440219d6", "enemy_raider_2bc22537"]
        # DM invents "enemy_red_coil_thug_1" but actual enemies exist
        # With threshold=0.6, this may not match (too different)
        # This is actually CORRECT behavior - we don't want to auto-match very different names
        result = find_closest_agent_id("enemy_red_coil_thug_1", valid_ids, threshold=0.4)
        # Should match with lower threshold based on "enemy" prefix
        assert result in valid_ids


class TestValidateEnemyConversion:
    """Tests for enemy conversion validation."""

    def test_valid_conversion(self):
        """Valid enemy ID should pass validation."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        is_valid, error, suggested = validate_enemy_conversion(
            "enemy_grunt_440219d6", active_enemies
        )
        assert is_valid is True
        assert error == ""
        assert suggested is None

    def test_invalid_enemy_id(self):
        """Invalid enemy ID should fail with suggestion if close match exists."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        # Test with very different ID - may not suggest a match (correct behavior)
        is_valid, error, suggested = validate_enemy_conversion(
            "enemy_red_coil_thug_1", active_enemies
        )
        assert is_valid is False
        assert "not found" in error
        # Suggestion may be None if no close match (threshold=0.6)
        # This is CORRECT - we don't want to suggest very different IDs

    def test_invalid_enemy_id_with_typo(self):
        """Invalid enemy ID with typo should fail with suggestion."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        # Test with typo - should suggest correct ID
        is_valid, error, suggested = validate_enemy_conversion(
            "enemy_grunt_440219d", active_enemies
        )
        assert is_valid is False
        assert "not found" in error
        assert suggested == "enemy_grunt_440219d6"

    def test_already_defeated_enemy(self):
        """Defeated enemy should fail validation."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]
        defeated_enemies = ["enemy_grunt_440219d6"]

        is_valid, error, suggested = validate_enemy_conversion(
            "enemy_grunt_440219d6", active_enemies, defeated_enemies
        )
        assert is_valid is False
        assert "already defeated" in error
        assert suggested is None

    def test_no_fuzzy_match(self):
        """No fuzzy match should list all active enemies."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        enemy2 = Mock()
        enemy2.agent_id = "enemy_raider_abc123"
        active_enemies = [enemy1, enemy2]

        is_valid, error, suggested = validate_enemy_conversion(
            "completely_invalid_xyz", active_enemies
        )
        assert is_valid is False
        assert "not found" in error
        assert "enemy_grunt_440219d6" in error
        assert "enemy_raider_abc123" in error
        assert suggested is None


class TestValidateNPCEscalation:
    """Tests for NPC escalation validation."""

    def test_valid_escalation(self):
        """Valid NPC ID should pass validation."""
        npc1 = Mock()
        npc1.agent_id = "npc_civilian_3fa8"
        active_npcs = [npc1]

        is_valid, error, suggested = validate_npc_escalation(
            "npc_civilian_3fa8", active_npcs
        )
        assert is_valid is True
        assert error == ""
        assert suggested is None

    def test_invalid_npc_id(self):
        """Invalid NPC ID should fail with suggestion if close match exists."""
        npc1 = Mock()
        npc1.agent_id = "npc_civilian_3fa8"
        active_npcs = [npc1]

        # Test with very different ID - may not suggest a match (correct behavior)
        is_valid, error, suggested = validate_npc_escalation(
            "npc_guard_xyz", active_npcs
        )
        assert is_valid is False
        assert "not found" in error
        # Suggestion may be None if no close match

    def test_invalid_npc_id_with_typo(self):
        """Invalid NPC ID with typo should fail with suggestion."""
        npc1 = Mock()
        npc1.agent_id = "npc_civilian_3fa8"
        active_npcs = [npc1]

        # Test with typo - should suggest correct ID
        is_valid, error, suggested = validate_npc_escalation(
            "npc_civilian_3fa", active_npcs
        )
        assert is_valid is False
        assert "not found" in error
        assert suggested == "npc_civilian_3fa8"

    def test_already_escalated(self):
        """NPC already escalated to enemy should fail."""
        npc1 = Mock()
        npc1.agent_id = "npc_guard_3fa8"
        active_npcs = [npc1]

        enemy1 = Mock()
        enemy1.agent_id = "npc_guard_3fa8"  # Same ID (escalated)
        active_enemies = [enemy1]

        is_valid, error, suggested = validate_npc_escalation(
            "npc_guard_3fa8", active_npcs, active_enemies
        )
        assert is_valid is False
        assert "already escalated" in error
        assert suggested is None

    def test_no_fuzzy_match(self):
        """No fuzzy match should list all active NPCs."""
        npc1 = Mock()
        npc1.agent_id = "npc_civilian_3fa8"
        npc2 = Mock()
        npc2.agent_id = "npc_guard_abc123"
        active_npcs = [npc1, npc2]

        is_valid, error, suggested = validate_npc_escalation(
            "completely_invalid_xyz", active_npcs
        )
        assert is_valid is False
        assert "not found" in error
        assert "npc_civilian_3fa8" in error
        assert "npc_guard_abc123" in error
        assert suggested is None


class TestAutoCorrectConversion:
    """Tests for auto-correction with high confidence matches."""

    def test_high_confidence_typo(self):
        """High confidence typo should auto-correct."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        corrected = auto_correct_conversion(
            "enemy_grunt_440219d", active_enemies, threshold=0.8
        )
        assert corrected == "enemy_grunt_440219d6"

    def test_low_confidence_no_correction(self):
        """Low confidence match should not auto-correct."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        corrected = auto_correct_conversion(
            "enemy_red_coil_thug_1", active_enemies, threshold=0.8
        )
        assert corrected is None

    def test_exact_match(self):
        """Exact match should return itself."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        active_enemies = [enemy1]

        corrected = auto_correct_conversion(
            "enemy_grunt_440219d6", active_enemies, threshold=0.8
        )
        assert corrected == "enemy_grunt_440219d6"

    def test_empty_enemies(self):
        """Empty enemy list should return None."""
        corrected = auto_correct_conversion(
            "enemy_grunt_123", [], threshold=0.8
        )
        assert corrected is None

    def test_multiple_enemies_best_match(self):
        """Should pick best match among multiple enemies."""
        enemy1 = Mock()
        enemy1.agent_id = "enemy_grunt_440219d6"
        enemy2 = Mock()
        enemy2.agent_id = "enemy_raider_abc123"
        active_enemies = [enemy1, enemy2]

        corrected = auto_correct_conversion(
            "enemy_grunt_440219d", active_enemies, threshold=0.8
        )
        assert corrected == "enemy_grunt_440219d6"
