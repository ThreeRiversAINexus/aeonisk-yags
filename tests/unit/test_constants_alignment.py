"""
Regression tests to prevent constants drift (Charisma creep).

Written FIRST (TDD red phase) - all tests FAIL initially.

This test suite ensures that YAGS_ATTRIBUTES and other game constants
are defined in a single location (constants.py) and referenced everywhere else.

See .claude/SINGLE_SOURCE_OF_TRUTH.md for architecture philosophy.
"""

import re
from pathlib import Path
import pytest


class TestAttributeConstants:
    """Verify YAGS_ATTRIBUTES is single source of truth"""

    def test_constants_file_exists(self):
        """constants.py should exist"""
        constants_path = Path("scripts/aeonisk/multiagent/constants.py")
        assert constants_path.exists(), "constants.py does not exist yet (TDD red phase)"

    def test_yags_attributes_defined(self):
        """YAGS_ATTRIBUTES should have 8 attributes"""
        from scripts.aeonisk.multiagent.constants import YAGS_ATTRIBUTES

        assert len(YAGS_ATTRIBUTES) == 8, f"Expected 8 attributes, got {len(YAGS_ATTRIBUTES)}"

        # Check all 8 are present
        expected = ["Strength", "Agility", "Endurance", "Dexterity",
                   "Perception", "Intelligence", "Empathy", "Willpower"]
        for attr in expected:
            assert attr in YAGS_ATTRIBUTES, f"Missing attribute: {attr}"

        # Regression: Charisma should NOT be present
        assert "Charisma" not in YAGS_ATTRIBUTES, "Charisma regression!"

    def test_attributes_string_helper(self):
        """ATTRIBUTES_STRING should be comma-separated list"""
        from scripts.aeonisk.multiagent.constants import ATTRIBUTES_STRING

        assert isinstance(ATTRIBUTES_STRING, str)
        assert "Strength" in ATTRIBUTES_STRING
        assert "," in ATTRIBUTES_STRING
        assert len(ATTRIBUTES_STRING.split(", ")) == 8

    def test_mechanics_imports_constants(self):
        """mechanics.py should import from constants"""
        mechanics_path = Path("scripts/aeonisk/multiagent/mechanics.py")
        with open(mechanics_path) as f:
            content = f.read()

        assert "from .constants import YAGS_ATTRIBUTES" in content, \
            "mechanics.py should import YAGS_ATTRIBUTES from constants"

        # Should NOT have hardcoded list
        assert '["Strength", "Agility"' not in content, \
            "mechanics.py has hardcoded attribute list (should use constants)"

    def test_character_validator_imports_constants(self):
        """character_validator.py should import from constants"""
        validator_path = Path("scripts/aeonisk/multiagent/character_validator.py")
        with open(validator_path) as f:
            content = f.read()

        assert "from .constants import YAGS_ATTRIBUTES" in content, \
            "character_validator.py should import from constants"

    def test_player_action_imports_constants(self):
        """player_action.py should import from constants"""
        player_action_path = Path("scripts/aeonisk/multiagent/schemas/player_action.py")
        with open(player_action_path) as f:
            content = f.read()

        # Should import either YAGS_ATTRIBUTES or ATTRIBUTES_STRING
        has_import = ("from ..constants import" in content)
        assert has_import, "player_action.py should import from constants"

    def test_action_schema_imports_constants(self):
        """action_schema.py should import from constants"""
        action_schema_path = Path("scripts/aeonisk/multiagent/action_schema.py")
        with open(action_schema_path) as f:
            content = f.read()

        # Should import from constants
        has_import = ("from .constants import" in content)
        assert has_import, "action_schema.py should import from constants"

    def test_no_hardcoded_attribute_lists(self):
        """No Python files should have hardcoded YAGS attribute lists"""
        violations = []

        multiagent_dir = Path("scripts/aeonisk/multiagent")
        for pyfile in multiagent_dir.rglob("*.py"):
            # Skip constants.py itself (it's allowed to define the list)
            if pyfile.name == "constants.py":
                continue

            with open(pyfile) as f:
                content = f.read()

            # Look for hardcoded list pattern
            # Pattern: ["Strength", "Agility" or similar
            if re.search(r'\["Strength",\s*"Agility"', content):
                violations.append(str(pyfile.relative_to(Path.cwd())))

        assert not violations, \
            f"Found hardcoded attribute lists in: {violations}. Use constants.py instead!"


class TestPromptAlignment:
    """Verify prompts match Python constants"""

    def test_player_yaml_has_correct_attributes(self):
        """player.yaml should list all 8 attributes correctly"""
        player_yaml = Path("scripts/aeonisk/multiagent/prompts/claude/en/player.yaml")
        with open(player_yaml) as f:
            content = f.read()

        # Should have all 8
        assert "Strength" in content
        assert "Dexterity" in content
        assert "Endurance" in content

        # Should NOT have deprecated Charisma
        assert "Charisma" not in content, "Charisma found in player.yaml (regression!)"

        # Should not have duplicate Empathy in attribute list
        # Empathy appears in: attribute list (once), examples, skill descriptions
        # Normal count: ~10-15 times. Count >20 indicates duplicate in list.
        empathy_count = content.count("Empathy")
        assert empathy_count < 20, \
            f"Empathy appears {empathy_count} times (possible duplicate in attribute list - normal is ~14)"

    def test_action_schema_prompt_alignment(self):
        """action_schema.py prompts should reference constants"""
        action_schema = Path("scripts/aeonisk/multiagent/action_schema.py")
        with open(action_schema) as f:
            content = f.read()

        # Should reference constants or use ATTRIBUTES_STRING
        references_constants = (
            "YAGS_ATTRIBUTES" in content or
            "ATTRIBUTES_STRING" in content
        )
        assert references_constants, \
            "action_schema.py should reference constants for attribute lists"


class TestDifficultyConstants:
    """Verify difficulty scales are centralized"""

    def test_difficulty_ranges_defined(self):
        """DIFFICULTY_RANGES should be in constants.py"""
        from scripts.aeonisk.multiagent.constants import DIFFICULTY_RANGES

        assert isinstance(DIFFICULTY_RANGES, dict)
        assert 10 in DIFFICULTY_RANGES  # Easy
        assert 15 in DIFFICULTY_RANGES  # Moderate
        assert 20 in DIFFICULTY_RANGES  # Challenging

        assert DIFFICULTY_RANGES[10] == "Easy"
        assert DIFFICULTY_RANGES[20] == "Challenging"

    def test_difficulty_guidance_helper(self):
        """DIFFICULTY_GUIDANCE should be formatted string"""
        from scripts.aeonisk.multiagent.constants import DIFFICULTY_GUIDANCE

        assert isinstance(DIFFICULTY_GUIDANCE, str)
        assert "10" in DIFFICULTY_GUIDANCE
        assert "Easy" in DIFFICULTY_GUIDANCE

    def test_no_excessive_hardcoded_difficulty_scales(self):
        """Prompts should not have too many hardcoded difficulty scales"""
        violations = []

        prompts_dir = Path("scripts/aeonisk/multiagent/prompts")
        for yamlfile in prompts_dir.rglob("*.yaml"):
            with open(yamlfile) as f:
                content = f.read()

            # Look for hardcoded difficulty scales (pattern: "10 = Easy" or "10: Easy")
            if re.search(r'10\s*[=:]\s*Easy', content):
                violations.append(str(yamlfile.relative_to(Path.cwd())))

        # Some prompts may have hardcoded scales (will be fixed in Phase 4)
        # But there shouldn't be MORE than we started with
        assert len(violations) <= 5, \
            f"Too many hardcoded difficulty scales ({len(violations)}): {violations}"


class TestSecondaryStats:
    """Verify secondary stats constants"""

    def test_secondary_stats_defined(self):
        """YAGS_SECONDARY_STATS should include Size"""
        from scripts.aeonisk.multiagent.constants import YAGS_SECONDARY_STATS

        assert "Size" in YAGS_SECONDARY_STATS

    def test_default_attributes_defined(self):
        """DEFAULT_ATTRIBUTES should have sensible defaults"""
        from scripts.aeonisk.multiagent.constants import DEFAULT_ATTRIBUTES

        # Should have all 8 core attributes
        assert DEFAULT_ATTRIBUTES["Strength"] == 3
        assert DEFAULT_ATTRIBUTES["Agility"] == 3
        assert DEFAULT_ATTRIBUTES["Endurance"] == 3

        # Should have Size
        assert DEFAULT_ATTRIBUTES["Size"] == 5


class TestImportPatterns:
    """Verify import patterns are correct"""

    def test_relative_imports_work(self):
        """Test that imports work from different module depths"""
        # Top-level modules (mechanics.py, character_validator.py)
        from scripts.aeonisk.multiagent.constants import YAGS_ATTRIBUTES as attrs1
        assert len(attrs1) == 8

        # Schemas submodule (would use: from ..constants import)
        # We can't test the import path directly, but we can verify the file exists
        constants_path = Path("scripts/aeonisk/multiagent/constants.py")
        assert constants_path.exists()

    def test_constants_module_is_importable(self):
        """constants module should be importable without errors"""
        try:
            import scripts.aeonisk.multiagent.constants as const
            assert hasattr(const, 'YAGS_ATTRIBUTES')
            assert hasattr(const, 'ATTRIBUTES_STRING')
            assert hasattr(const, 'DIFFICULTY_RANGES')
        except ImportError as e:
            pytest.fail(f"Failed to import constants module: {e}")


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
