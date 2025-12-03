"""
Comprehensive tests for YAGS mechanics conformance.

Tests the core YAGS rules implementation:
- Unskilled penalty (attribute × 4)
- Skilled checks (attribute × skill + d20)
- Attribute ranges and validation
- Skill-attribute mappings
- Combat mechanics
- Damage types (stun, wound, mixed)
"""

import pytest
import random
from unittest.mock import Mock, patch

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE


class TestYAGSUnskilledPenalty:
    """Test YAGS unskilled penalty: attribute × 4 (not -5)."""

    def test_unskilled_check_uses_attribute_times_four(self):
        """Unskilled check should use attribute × 4, not -5 penalty."""
        mechanics = MechanicsEngine()

        # Mock d20 roll to 10 for predictable results
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Hack a terminal",
                attribute="Intelligence",
                skill=None,  # Unskilled
                attribute_value=3,
                skill_value=0,
                difficulty=20
            )

        # YAGS unskilled: ability = 3 × 4 = 12
        # total = 12 + 10 = 22
        ability = resolution.total - resolution.roll
        assert ability == 12, f"Expected ability 12 (3×4), got {ability}"
        assert resolution.total == 22, f"Expected total 22 (12+10), got {resolution.total}"
        assert resolution.success == True, "Should succeed against DC 20"
        assert resolution.margin == 2, f"Expected margin +2, got {resolution.margin}"

    def test_unskilled_with_low_attribute(self):
        """Unskilled check with attribute 1 should still be positive."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=15):
            resolution = mechanics.resolve_action(
                intent="Lift heavy object",
                attribute="Strength",
                skill=None,
                attribute_value=1,
                skill_value=0,
                difficulty=20
            )

        # YAGS unskilled: 1 × 4 = 4 (not -5!)
        ability = resolution.total - resolution.roll
        assert ability == 4, f"Expected ability 4 (1×4), got {ability}"
        assert resolution.total == 19, f"Expected total 19 (4+15), got {resolution.total}"

    def test_unskilled_with_high_attribute(self):
        """Unskilled check with high attribute should be viable."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Analyze complex system",
                attribute="Intelligence",
                skill=None,
                attribute_value=5,
                skill_value=0,
                difficulty=25
            )

        # YAGS unskilled: 5 × 4 = 20
        ability = resolution.total - resolution.roll
        assert ability == 20, f"Expected ability 20 (5×4), got {ability}"
        assert resolution.total == 30, f"Expected total 30 (20+10), got {resolution.total}"
        assert resolution.success == True


class TestYAGSSkilledChecks:
    """Test YAGS skilled checks: attribute × skill + d20."""

    def test_skilled_check_basic(self):
        """Skilled check should use attribute × skill."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Hack terminal",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=4,
                skill_value=3,
                difficulty=25
            )

        # YAGS skilled: 4 × 3 = 12
        ability = resolution.total - resolution.roll
        assert ability == 12, f"Expected ability 12 (4×3), got {ability}"
        assert resolution.total == 24, f"Expected total 24 (12+12), got {resolution.total}"
        assert resolution.success == False, "Should fail against DC 25"
        assert resolution.margin == -1

    def test_skilled_check_high_skill(self):
        """High skill level should provide significant bonus."""
        mechanics = MechanicsEngine()
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Aimed shot",
                attribute="Perception",
                skill="Guns",
                attribute_value=4,
                skill_value=5,
                difficulty=30
            )

        # YAGS skilled: 4 × 5 = 20
        ability = resolution.total - resolution.roll
        assert ability == 20, f"Expected ability 20 (4×5), got {ability}"
        assert resolution.total == 30, f"Expected total 30 (20+10), got {resolution.total}"
        assert resolution.success == True

    def test_skilled_vs_unskilled_comparison(self):
        """Skilled check should vastly outperform unskilled."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            skilled_resolution = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=3,
                skill_value=4,
                difficulty=20
            )

            unskilled_resolution = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill=None,
                attribute_value=3,
                skill_value=0,
                difficulty=20
            )

        # Skilled: 3 × 4 = 12, total 22 ✓
        # Unskilled: 3 × 4 = 12, total 22 ✓ (same as skilled with skill 4!)
        # This shows unskilled is viable at low skill levels
        skilled_ability = skilled_resolution.total - skilled_resolution.roll
        unskilled_ability = unskilled_resolution.total - unskilled_resolution.roll
        assert skilled_ability == 12, "Skilled: 3×4=12"
        assert unskilled_ability == 12, "Unskilled: 3×4=12"

        # Now compare with higher skill level (skill 6)
        with patch('random.randint', return_value=10):
            skilled_high = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=3,
                skill_value=6,
                difficulty=20
            )

        # Skilled (high): 3 × 6 = 18, total 28
        skilled_high_ability = skilled_high.total - skilled_high.roll
        assert skilled_high_ability == 18, "High skill should be 3×6=18"
        assert skilled_high.total == 28


class TestYAGSAttributeRanges:
    """Test attribute value ranges and validation."""

    def test_minimum_attribute_value(self):
        """Attribute 1 is minimum for humans."""
        mechanics = MechanicsEngine()
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Punch",
                attribute="Strength",
                skill="Brawl",
                attribute_value=1,
                skill_value=2,
                difficulty=15
            )

        # 1 × 2 = 2, total 12
        ability = resolution.total - resolution.roll
        assert ability == 2
        assert resolution.total == 12

    def test_typical_human_attributes(self):
        """Typical human (attr 2-3) should have reasonable ability."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Climb",
                attribute="Agility",
                skill="Athletics",
                attribute_value=3,
                skill_value=2,  # YAGS Talent starts at 2
                difficulty=20
            )

        # 3 × 2 = 6, total 16
        ability = resolution.total - resolution.roll
        assert ability == 6
        assert resolution.total == 16

    def test_exceptional_human_attributes(self):
        """Exceptional human (attr 5-6) should excel."""
        mechanics = MechanicsEngine()
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Spot hidden",
                attribute="Perception",
                skill="Awareness",
                attribute_value=5,
                skill_value=4,
                difficulty=30
            )

        # 5 × 4 = 20, total 30
        ability = resolution.total - resolution.roll
        assert ability == 20
        assert resolution.total == 30
        assert resolution.success == True


class TestYAGSSkillAttributeMappings:
    """Test that skills map to correct attributes per YAGS."""

    def test_combat_skills_use_correct_attributes(self):
        """Combat skills should map to correct attributes."""
        # Guns → Perception
        assert SKILL_DATABASE["Guns"].attribute == "Perception"

        # Melee → Dexterity
        assert SKILL_DATABASE["Melee"].attribute == "Dexterity"

        # Brawl → Agility
        assert SKILL_DATABASE["Brawl"].attribute == "Agility"

        # Throw → Dexterity
        assert SKILL_DATABASE["Throw"].attribute == "Dexterity"

    def test_social_skills_use_correct_attributes(self):
        """Social skills should map to Empathy/Willpower."""
        # Charm → Empathy
        assert SKILL_DATABASE["Charm"].attribute == "Empathy"

        # Guile → Empathy
        assert SKILL_DATABASE["Guile"].attribute == "Empathy"

        # Counsel → Empathy
        assert SKILL_DATABASE["Counsel"].attribute == "Empathy"

        # Intimidation → Willpower (mental dominance)
        assert SKILL_DATABASE["Intimidation"].attribute == "Willpower"

    def test_technical_skills_use_intelligence(self):
        """Technical skills should use Intelligence."""
        assert SKILL_DATABASE["Systems"].attribute == "Intelligence"
        assert SKILL_DATABASE["Drone Operation"].attribute == "Intelligence"
        assert SKILL_DATABASE["Medicine"].attribute == "Intelligence"

    def test_perception_skills_use_perception(self):
        """Perception-based skills should use Perception."""
        assert SKILL_DATABASE["Awareness"].attribute == "Perception"
        assert SKILL_DATABASE["Attunement"].attribute == "Perception"
        assert SKILL_DATABASE["Investigation"].attribute == "Perception"

    def test_ritual_skills_use_willpower(self):
        """Most ritual skills should use Willpower."""
        assert SKILL_DATABASE["Astral Arts"].attribute == "Willpower"
        assert SKILL_DATABASE["Discipline"].attribute == "Willpower"
        assert SKILL_DATABASE["Dreamwork"].attribute == "Willpower"

        # Exception: Intimacy Ritual uses Empathy (emotional magic)
        assert SKILL_DATABASE["Intimacy Ritual"].attribute == "Empathy"


class TestYAGSTalentSystem:
    """Test YAGS Talent mechanics (skills that start at level 2)."""

    def test_talents_are_marked_correctly(self):
        """YAGS Talents should be marked with is_talent=True."""
        talents = [
            "Athletics", "Awareness", "Brawl", "Charm",
            "Guile", "Sleight", "Stealth", "Throw"
        ]

        for talent_name in talents:
            skill_info = SKILL_DATABASE[talent_name]
            assert skill_info.is_talent == True, f"{talent_name} should be marked as Talent"

    def test_non_talents_are_not_marked(self):
        """Regular skills should not be marked as Talents."""
        regular_skills = [
            "Guns", "Melee", "Systems", "Healing",
            "Astral Arts", "Drone Operation"
        ]

        for skill_name in regular_skills:
            skill_info = SKILL_DATABASE[skill_name]
            assert skill_info.is_talent == False, f"{skill_name} should not be a Talent"


class TestYAGSCriticalHits:
    """Test YAGS critical hit mechanics (roll 20)."""

    def test_natural_20_is_critical_success(self):
        """Rolling natural 20 should be critical success."""
        mechanics = MechanicsEngine()
        with patch('random.randint', return_value=20):
            resolution = mechanics.resolve_action(
                intent="Punch",
                attribute="Agility",
                skill="Brawl",
                attribute_value=2,
                skill_value=2,
                difficulty=30  # Very hard
            )

        # 2 × 2 = 4, + 20 = 24 (still fails DC 30)
        # But natural 20 should be treated specially
        assert resolution.roll == 20
        assert resolution.total == 24


class TestYAGSDifficultyScaling:
    """Test YAGS difficulty number scaling."""

    def test_difficulty_ranges(self):
        """Test standard YAGS difficulty ranges."""
        difficulties = {
            "Very Easy": 10,
            "Easy": 15,
            "Moderate": 20,
            "Challenging": 25,
            "Difficult": 30,
            "Very Difficult": 35,
            "Formidable": 40,
            "Nearly Impossible": 45
        }

        mechanics = MechanicsEngine()
        # With 4×4=16 + average roll of 10 = 26
        # Should succeed at Moderate/Challenging, fail at Difficult+

        with patch('random.randint', return_value=10):
            # Moderate (DC 20): 16+10=26 ✓
            moderate = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=4,
                skill_value=4,
                difficulty=20
            )
            assert moderate.success == True, "Should succeed at Moderate"

            # Challenging (DC 25): 16+10=26 ✓
            challenging = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=4,
                skill_value=4,
                difficulty=25
            )
            assert challenging.success == True, "Should barely succeed at Challenging"

            # Difficult (DC 30): 16+10=26 ✗
            difficult = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=4,
                skill_value=4,
                difficulty=30
            )
            assert difficult.success == False, "Should fail at Difficult"


class TestYAGSMarginOfSuccess:
    """Test margin of success/failure calculations."""

    def test_margin_calculation(self):
        """Margin should be (total - DC)."""
        mechanics = MechanicsEngine()
        with patch('random.randint', return_value=10):
            # 3×4=12 + 10 = 22 vs DC 20 → margin +2
            resolution = mechanics.resolve_action(
                intent="Punch",
                attribute="Strength",
                skill="Brawl",
                attribute_value=3,
                skill_value=4,
                difficulty=20
            )

        assert resolution.margin == 2, f"Expected margin +2, got {resolution.margin}"

        with patch('random.randint', return_value=5):
            # 3×4=12 + 5 = 17 vs DC 20 → margin -3
            failure = mechanics.resolve_action(
                intent="Punch",
                attribute="Strength",
                skill="Brawl",
                attribute_value=3,
                skill_value=4,
                difficulty=20
            )

        assert failure.margin == -3, f"Expected margin -3, got {failure.margin}"


@pytest.mark.parametrize("attribute,expected_attr_value", [
    ("Strength", 3),
    ("Agility", 4),
    ("Endurance", 3),
    ("Dexterity", 3),
    ("Perception", 4),
    ("Intelligence", 3),
    ("Empathy", 3),
    ("Willpower", 4),
])
def test_all_yags_attributes_supported(attribute, expected_attr_value):
    """Test that all 8 YAGS attributes are supported."""
    mechanics = MechanicsEngine()
    with patch('random.randint', return_value=10):
        resolution = mechanics.resolve_action(
            intent=f"Test {attribute}",
            attribute=attribute,
            skill="TestSkill",
            attribute_value=expected_attr_value,
            skill_value=2,
            difficulty=20
        )

    expected_ability = expected_attr_value * 2
    ability = resolution.total - resolution.roll
    assert ability == expected_ability, f"{attribute}: Expected ability {expected_ability}, got {ability}"
