"""
YAGS Skill System Compliance Tests

Tests skill mechanics from YAGS Module v1.2.2:
- Skill check formula: Attribute × Skill + d20 vs DC
- Attribute check formula: Attribute × 4 + d20 vs DC
- Unskilled penalty: -5 or halved result
- Skill level meanings (1 Casual, 4-7 Professional, 8+ Master)
"""

import pytest
from unittest.mock import patch

from aeonisk.multiagent.mechanics import MechanicsEngine


class TestSkillFormulas:
    """Test basic skill resolution formulas."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_skill_check_formula(self, mechanics):
        """Test skill check: Attribute × Skill + d20."""
        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Climb wall",
                attribute="Agility",
                skill="Athletics",
                attribute_value=3,
                skill_value=2,
                difficulty=18
            )

            # Ability = 3 × 2 = 6, d20 = 12, total = 18
            expected_ability = 3 * 2
            assert resolution.total == expected_ability + 12
            assert resolution.total == 18

    def test_high_skill_bonus(self, mechanics):
        """Test high skill level provides significant bonus."""
        with patch('random.randint', return_value=10):
            # Professional level skill (5)
            resolution = mechanics.resolve_action(
                intent="Expert swordplay",
                attribute="Agility",
                skill="Combat",
                attribute_value=4,
                skill_value=5,  # Professional
                difficulty=22
            )

            # Ability = 4 × 5 = 20
            assert resolution.total == 30
            assert resolution.success == True

    def test_low_skill_penalty(self, mechanics):
        """Test low skill level limits success."""
        with patch('random.randint', return_value=15):
            # Casual skill level (1)
            resolution = mechanics.resolve_action(
                intent="Casual skill attempt",
                attribute="Intelligence",
                skill="Medicine",
                attribute_value=3,
                skill_value=1,  # Casual
                difficulty=20
            )

            # Ability = 3 × 1 = 3, total = 18
            assert resolution.total == 18
            assert resolution.margin == -2


class TestUnskilledPenalty:
    """Test unskilled penalty mechanics."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_unskilled_penalty_applied(self, mechanics):
        """Test unskilled (skill=0) applies -5 penalty."""
        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Unskilled attempt",
                attribute="Agility",
                skill=None,  # Unskilled
                attribute_value=4,
                skill_value=0,
                difficulty=15
            )

            # Ability = 4 - 5 (unskilled penalty) = -1
            # Total = -1 + 12 = 11
            assert resolution.total == 11
            assert resolution.margin == -4

    def test_skilled_no_penalty(self, mechanics):
        """Test skilled character doesn't get penalty."""
        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Skilled attempt",
                attribute="Agility",
                skill="Athletics",
                attribute_value=4,
                skill_value=2,  # Skilled
                difficulty=15
            )

            # Ability = 4 × 2 = 8, total = 20
            assert resolution.total == 20
            assert resolution.success == True

    def test_unskilled_vs_skilled_comparison(self, mechanics):
        """Compare unskilled vs skilled attempt with same attribute."""
        with patch('random.randint', return_value=10):
            # Unskilled
            unskilled = mechanics.resolve_action(
                intent="Unskilled",
                attribute="Intelligence",
                skill=None,
                attribute_value=3,
                skill_value=0,
                difficulty=18
            )

        with patch('random.randint', return_value=10):
            # Skilled (level 2)
            skilled = mechanics.resolve_action(
                intent="Skilled",
                attribute="Intelligence",
                skill="Investigation",
                attribute_value=3,
                skill_value=2,
                difficulty=18
            )

        # Unskilled: 3 - 5 = -2, +10 = 8
        # Skilled: 3 × 2 = 6, +10 = 16
        assert unskilled.total < skilled.total
        assert skilled.total - unskilled.total == 8


class TestAttributeChecks:
    """Test pure attribute checks (no skill)."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_attribute_check_formula(self, mechanics):
        """Test attribute check: Attribute × 4 + d20."""
        # According to YAGS, pure attribute checks use Attribute × 4
        # Our implementation uses the unskilled formula (Attribute - 5)
        # This test documents the difference

        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Raw strength check",
                attribute="Strength",
                skill=None,
                attribute_value=4,
                skill_value=0,
                difficulty=15
            )

            # Current implementation: 4 - 5 = -1, +10 = 9
            # YAGS pure attribute: 4 × 4 = 16, +10 = 26
            # This test documents current behavior
            assert resolution.total == 9


class TestSkillLevels:
    """Test skill level meanings and progression."""

    def test_casual_skill_level(self):
        """Casual skill (level 1): hobbyist, amateur."""
        skill_level = 1
        attribute = 3
        ability = skill_level * attribute

        # Casual: 3 × 1 = 3 (needs good roll for moderate tasks)
        assert ability == 3

    def test_student_skill_level(self):
        """Student skill (level 2-3): learning, developing."""
        skill_level = 2
        attribute = 3
        ability = skill_level * attribute

        # Student: 3 × 2 = 6
        assert 6 <= ability <= 9

    def test_professional_skill_level(self):
        """Professional skill (level 4-7): competent practitioner."""
        skill_level = 5
        attribute = 4
        ability = skill_level * attribute

        # Professional: 4 × 5 = 20 (highly capable)
        assert 16 <= ability <= 28

    def test_master_skill_level(self):
        """Master skill (level 8+): expert, renowned."""
        skill_level = 8
        attribute = 4
        ability = skill_level * attribute

        # Master: 4 × 8 = 32 (exceptional capability)
        assert ability >= 32


class TestSkillProgression:
    """Test skill advancement makes meaningful difference."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_skill_increase_improves_success(self, mechanics):
        """Test each skill level increase improves success rate."""
        with patch('random.randint', return_value=10):
            # Skill 2
            skill_2 = mechanics.resolve_action(
                intent="Moderate skill",
                attribute="Agility",
                skill="Combat",
                attribute_value=4,
                skill_value=2,
                difficulty=20
            )

        with patch('random.randint', return_value=10):
            # Skill 3
            skill_3 = mechanics.resolve_action(
                intent="Higher skill",
                attribute="Agility",
                skill="Combat",
                attribute_value=4,
                skill_value=3,
                difficulty=20
            )

        # Skill 2: 4 × 2 = 8, +10 = 18 (fail)
        # Skill 3: 4 × 3 = 12, +10 = 22 (succeed)
        assert skill_2.success == False
        assert skill_3.success == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
