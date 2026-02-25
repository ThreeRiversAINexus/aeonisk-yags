"""
Tests for skill name validation in session configs.

Ensures all session configs use canonical skill names from skill_descriptions.py.
Non-canonical names (like "Notice" instead of "Awareness") cause skill lookups
to fail, resulting in all checks being treated as unskilled.
"""

import json
import pytest
from pathlib import Path

from scripts.aeonisk.multiagent.skill_mapping import (
    is_canonical_skill,
    get_canonical_skills,
    get_canonical_suggestion,
    validate_character_skills,
    validate_session_config_skills,
)


class TestCanonicalSkillValidation:
    """Test the is_canonical_skill function."""

    def test_canonical_skills_are_valid(self):
        """All skills in SKILL_DATABASE should be canonical."""
        canonical = get_canonical_skills()
        assert len(canonical) > 40, "Should have 40+ canonical skills"

        # Spot check known canonical skills
        assert "Awareness" in canonical
        assert "Guile" in canonical
        assert "Charm" in canonical
        assert "Investigation" in canonical
        assert "Systems" in canonical
        assert "Combat" in canonical

    def test_non_canonical_skills_detected(self):
        """Non-canonical skill names should be detected."""
        assert is_canonical_skill("Awareness") is True
        assert is_canonical_skill("Notice") is False  # Should be Awareness

        assert is_canonical_skill("Guile") is True
        assert is_canonical_skill("Deception") is False  # Should be Guile

        assert is_canonical_skill("Charm") is True
        assert is_canonical_skill("Persuasion") is False  # Should be Charm

    def test_case_sensitivity(self):
        """Skill names are case-sensitive."""
        assert is_canonical_skill("Awareness") is True
        assert is_canonical_skill("awareness") is False
        assert is_canonical_skill("AWARENESS") is False


class TestCanonicalSuggestions:
    """Test the get_canonical_suggestion function."""

    def test_known_non_canonical_suggestions(self):
        """Common non-canonical names should have suggestions."""
        assert get_canonical_suggestion("Notice") == "Awareness"
        assert get_canonical_suggestion("Deception") == "Guile"
        assert get_canonical_suggestion("Persuasion") == "Charm"
        assert get_canonical_suggestion("Observation") == "Awareness"
        assert get_canonical_suggestion("Engineering") == "Tech/Craft"

    def test_canonical_skills_suggest_themselves(self):
        """Canonical skills should suggest themselves via normalize."""
        # These should normalize to themselves
        assert get_canonical_suggestion("awareness") == "Awareness"
        assert get_canonical_suggestion("guile") == "Guile"

    def test_unknown_skills_return_none(self):
        """Unknown skills should return None."""
        assert get_canonical_suggestion("MadeUpSkill") is None
        assert get_canonical_suggestion("Hacking123") is None


class TestCharacterSkillValidation:
    """Test validate_character_skills function."""

    def test_valid_character_passes(self):
        """Character with all canonical skills should pass."""
        skills = {
            "Investigation": 6,
            "Awareness": 5,
            "Combat": 4,
            "Athletics": 4,
            "Stealth": 3
        }
        is_valid, errors = validate_character_skills("Test Character", skills, raise_on_error=False)
        assert is_valid is True
        assert len(errors) == 0

    def test_non_canonical_skill_fails(self):
        """Character with non-canonical skills should fail."""
        skills = {
            "Investigation": 6,
            "Notice": 5,  # Should be Awareness
            "Combat": 4,
        }
        is_valid, errors = validate_character_skills("Test Character", skills, raise_on_error=False)
        assert is_valid is False
        assert len(errors) == 1
        assert "Notice" in errors[0]
        assert "Awareness" in errors[0]  # Should suggest fix

    def test_multiple_non_canonical_skills(self):
        """Multiple non-canonical skills should all be reported."""
        skills = {
            "Notice": 5,      # Should be Awareness
            "Deception": 7,   # Should be Guile
            "Persuasion": 5,  # Should be Charm
        }
        is_valid, errors = validate_character_skills("Sandra", skills, raise_on_error=False)
        assert is_valid is False
        assert len(errors) == 3

    def test_raise_on_error(self):
        """Should raise ValueError when raise_on_error=True."""
        skills = {"Notice": 5}
        with pytest.raises(ValueError) as exc_info:
            validate_character_skills("Test", skills, raise_on_error=True)
        assert "Notice" in str(exc_info.value)


class TestSessionConfigValidation:
    """Test validate_session_config_skills function."""

    def test_valid_config_passes(self):
        """Session config with all canonical skills should pass."""
        config = {
            "agents": {
                "players": [
                    {
                        "name": "Hector",
                        "skills": {"Investigation": 6, "Awareness": 5, "Combat": 4}
                    },
                    {
                        "name": "Sandra",
                        "skills": {"Guile": 7, "Stealth": 6, "Charm": 5}
                    }
                ]
            }
        }
        is_valid, errors = validate_session_config_skills(config, raise_on_error=False)
        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_config_fails(self):
        """Session config with non-canonical skills should fail."""
        config = {
            "agents": {
                "players": [
                    {
                        "name": "Hector",
                        "skills": {"Investigation": 6, "Notice": 5}  # Notice is wrong
                    },
                    {
                        "name": "Sandra",
                        "skills": {"Deception": 7, "Persuasion": 5}  # Both wrong
                    }
                ]
            }
        }
        is_valid, errors = validate_session_config_skills(config, raise_on_error=False)
        assert is_valid is False
        assert len(errors) == 3  # Notice, Deception, Persuasion


class TestAllSessionConfigsValid:
    """Validate all actual session config files use canonical skills."""

    @pytest.fixture
    def session_config_dir(self):
        """Get the session configs directory."""
        return Path("scripts/session_configs")

    def test_all_session_configs_use_canonical_skills(self, session_config_dir):
        """
        CRITICAL TEST: All session configs must use canonical skill names.

        Non-canonical skill names cause skill lookups to fail, resulting in
        all skill checks being treated as unskilled (d20÷2 formula).
        """
        config_files = list(session_config_dir.glob("*.json"))
        assert len(config_files) > 0, "Should find session config files"

        all_errors = []

        for config_file in config_files:
            try:
                with open(config_file) as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                all_errors.append(f"{config_file.name}: Invalid JSON - {e}")
                continue

            is_valid, errors = validate_session_config_skills(config, raise_on_error=False)
            if not is_valid:
                for error in errors:
                    all_errors.append(f"{config_file.name}: {error}")

        if all_errors:
            error_msg = "Session configs with non-canonical skill names:\n" + "\n".join(all_errors)
            pytest.fail(error_msg)

    def test_cheating_player_config_uses_canonical_skills(self, session_config_dir):
        """Specifically test the cheating player config."""
        config_file = session_config_dir / "session_config_cheating_player_test.json"
        assert config_file.exists(), "Cheating player test config should exist"

        with open(config_file) as f:
            config = json.load(f)

        is_valid, errors = validate_session_config_skills(config, raise_on_error=False)
        assert is_valid, f"Cheating player config has non-canonical skills: {errors}"


class TestKnownNonCanonicalSkills:
    """Document and test the known non-canonical → canonical mappings."""

    @pytest.mark.parametrize("non_canonical,canonical", [
        ("Notice", "Awareness"),
        ("Deception", "Guile"),
        ("Persuasion", "Charm"),
        ("Observation", "Awareness"),
        ("Engineering", "Tech/Craft"),
        ("Meditation", "Discipline"),
        ("Magic Theory", "Magick Theory"),
    ])
    def test_non_canonical_mappings(self, non_canonical, canonical):
        """Test that non-canonical skills map to correct canonical skills."""
        assert is_canonical_skill(non_canonical) is False, f"{non_canonical} should not be canonical"
        assert is_canonical_skill(canonical) is True, f"{canonical} should be canonical"
        suggestion = get_canonical_suggestion(non_canonical)
        assert suggestion == canonical, f"{non_canonical} should suggest {canonical}, got {suggestion}"


# =============================================================================
# Runtime player action skill validation (reject hallucinated skills at action time)
# =============================================================================

from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE


class TestValidatePlayerSkill:
    """Test the validate_player_skill function used in the player action pipeline."""

    def test_invalid_skill_rejected(self):
        """Action with skill='Command' (not in SKILL_DATABASE) should be rejected."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill("Command")
        assert is_valid is False
        assert "Command" in feedback
        assert "does not exist" in feedback

    def test_valid_skill_accepted(self):
        """Action with skill='Investigation' (in SKILL_DATABASE) should be accepted."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill("Investigation")
        assert is_valid is True
        assert feedback is None

    def test_awareness_accepted(self):
        """Skill='Awareness' (in SKILL_DATABASE) should be accepted even if character doesn't have it."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill("Awareness")
        assert is_valid is True
        assert feedback is None

    def test_none_skill_always_accepted(self):
        """Action with skill=None should always be accepted (raw attribute check)."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill(None)
        assert is_valid is True
        assert feedback is None

    def test_rejection_feedback_lists_valid_skills(self):
        """Rejection feedback should include valid skill names for LLM correction."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill("Telepathy")
        assert is_valid is False
        assert "Valid skills:" in feedback

    def test_all_database_skills_accepted(self):
        """Every skill in SKILL_DATABASE should be accepted."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        for skill_name in SKILL_DATABASE:
            is_valid, feedback = validate_player_skill(skill_name)
            assert is_valid is True, f"Valid skill '{skill_name}' was rejected: {feedback}"

    def test_feedback_suggests_skill_none(self):
        """Rejection feedback should suggest skill=None as an option."""
        from scripts.aeonisk.multiagent.player import validate_player_skill

        is_valid, feedback = validate_player_skill("Negotiation")
        assert is_valid is False
        assert "None" in feedback or "null" in feedback.lower()
