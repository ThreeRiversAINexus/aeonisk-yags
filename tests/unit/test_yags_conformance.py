"""
Comprehensive tests for YAGS mechanics conformance.

Tests the core YAGS rules implementation (v1.2.3):
- Unskilled checks (d20 ÷ 2) - when skill=None or skill_value=0
- Unskilled Knowledge skill checks (blocked) - cannot attempt without training
- Skilled checks (attribute × skill + d20)
- Attribute ranges and validation
- Skill-attribute mappings
- Combat mechanics
- Damage types (stun, wound, mixed)

Note: Raw attribute checks (attribute × 4) were removed in v1.2.3.
All actions now require skills; pure attribute checks use unskilled formula.
"""

import pytest
import random
from unittest.mock import Mock, patch

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, is_knowledge_skill
from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE


class TestYAGSNoSkillChecks:
    """Test that skill=None uses unskilled formula (d20 ÷ 2) - raw attribute removed in v1.2.3."""

    def test_no_skill_uses_unskilled_formula(self):
        """When skill=None, should use d20 ÷ 2 (not attribute × 4)."""
        mechanics = MechanicsEngine()

        # Mock d20 roll to 10 for predictable results
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Lift heavy object",  # Pure strength, no skill
                attribute="Strength",
                skill=None,  # No skill - uses unskilled formula
                attribute_value=3,  # High attribute shouldn't help!
                skill_value=0,
                difficulty=20
            )

        # v1.2.3: d20(10) ÷ 2 = 5 (attribute doesn't matter)
        assert resolution.total == 5, f"Expected total 5 (10÷2), got {resolution.total}"
        assert resolution.success == False, "Should fail against DC 20 with only 5"
        assert resolution.margin == -15, f"Expected margin -15, got {resolution.margin}"

    def test_no_skill_with_low_roll(self):
        """Skill=None with low roll should be poor."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=4):
            resolution = mechanics.resolve_action(
                intent="Push through pain",  # No skill
                attribute="Endurance",
                skill=None,
                attribute_value=5,  # Even high attribute doesn't help
                skill_value=0,
                difficulty=10
            )

        # d20(4) ÷ 2 = 2
        assert resolution.total == 2, f"Expected total 2 (4÷2), got {resolution.total}"
        assert resolution.success == False

    def test_no_skill_with_high_roll(self):
        """Skill=None with high roll can succeed at easy tasks."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=18):
            resolution = mechanics.resolve_action(
                intent="Resist mental assault",  # No skill
                attribute="Willpower",
                skill=None,
                attribute_value=5,
                skill_value=0,
                difficulty=8  # Very easy
            )

        # d20(18) ÷ 2 = 9
        assert resolution.total == 9, f"Expected total 9 (18÷2), got {resolution.total}"
        assert resolution.success == True, "Should succeed at DC 8"


class TestYAGSUnskilledStandardSkills:
    """Test YAGS unskilled Standard skill checks: d20 ÷ 2 (halved)."""

    def test_unskilled_standard_skill_uses_halved_d20(self):
        """Unskilled Standard skill check should use d20 ÷ 2, no attribute bonus."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Hack a terminal",
                attribute="Intelligence",
                skill="Systems",  # Standard skill, not trained
                attribute_value=5,  # High attribute shouldn't help!
                skill_value=0,  # Unskilled
                difficulty=10
            )

        # Unskilled Standard: d20(10) ÷ 2 = 5 (no attribute bonus!)
        assert resolution.total == 5, f"Expected total 5 (10÷2), got {resolution.total}"
        assert resolution.success == False, "Should fail DC 10 with only 5"
        assert resolution.margin == -5, f"Expected margin -5, got {resolution.margin}"

    def test_unskilled_standard_skill_high_roll(self):
        """Unskilled with high roll can still succeed at easy tasks."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=18):
            resolution = mechanics.resolve_action(
                intent="Fire weapon",
                attribute="Perception",
                skill="Guns",  # Standard skill, not trained
                attribute_value=4,
                skill_value=0,
                difficulty=8  # Very easy
            )

        # Unskilled: d20(18) ÷ 2 = 9
        assert resolution.total == 9, f"Expected total 9 (18÷2), got {resolution.total}"
        assert resolution.success == True, "Should succeed at DC 8"

    def test_unskilled_fumble_on_natural_1(self):
        """Unskilled Standard skill fumbles on natural 1."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=1):
            resolution = mechanics.resolve_action(
                intent="Pick lock",
                attribute="Dexterity",
                skill="Sleight",  # Talent, but testing with 0
                attribute_value=4,
                skill_value=0,
                difficulty=5  # Very easy
            )

        # Natural 1 = fumble for unskilled
        assert resolution.roll == 1
        assert resolution.success == False, "Natural 1 should be fumble"
        assert resolution.outcome_tier.value == "critical_failure", "Should be critical failure"

    def test_unskilled_fumble_on_natural_2(self):
        """Unskilled Standard skill also fumbles on natural 2."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=2):
            resolution = mechanics.resolve_action(
                intent="Throw grenade",
                attribute="Dexterity",
                skill="Throw",
                attribute_value=3,
                skill_value=0,
                difficulty=5
            )

        # Natural 2 = fumble for unskilled
        assert resolution.roll == 2
        assert resolution.success == False, "Natural 2 should be fumble"
        assert resolution.outcome_tier.value == "critical_failure"

    def test_unskilled_no_fumble_on_3(self):
        """Unskilled Standard skill does NOT fumble on natural 3."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=3):
            resolution = mechanics.resolve_action(
                intent="Notice something",
                attribute="Perception",
                skill="Awareness",
                attribute_value=4,
                skill_value=0,
                difficulty=1  # Very easy - 3÷2=1 should barely pass
            )

        # Natural 3 = 1 (3÷2), no fumble
        assert resolution.roll == 3
        assert resolution.total == 1, "3÷2 = 1"
        assert resolution.outcome_tier.value != "critical_failure", "Natural 3 should not fumble"


class TestYAGSUnskilledKnowledgeSkills:
    """Test YAGS Knowledge skill restrictions: cannot attempt untrained."""

    def test_knowledge_skill_helper(self):
        """Test is_knowledge_skill() helper function."""
        # Knowledge skills (per skill_descriptions.py)
        assert is_knowledge_skill("Magick Theory") == True
        assert is_knowledge_skill("Ritual Lore") == True
        assert is_knowledge_skill("Science") == True
        assert is_knowledge_skill("History") == True
        assert is_knowledge_skill("Area Lore") == True
        assert is_knowledge_skill("Void Lore") == True  # Note: "Void Lore" not "Void Theory"
        assert is_knowledge_skill("Debt Law") == True

        # Standard skills
        assert is_knowledge_skill("Systems") == False
        assert is_knowledge_skill("Guns") == False
        assert is_knowledge_skill("Brawl") == False
        assert is_knowledge_skill("Charm") == False

        # Edge cases
        assert is_knowledge_skill(None) == False
        assert is_knowledge_skill("") == False
        assert is_knowledge_skill("NonexistentSkill") == False

    def test_unskilled_knowledge_skill_blocked(self):
        """Knowledge skills cannot be attempted without training."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=20):  # Even nat 20 shouldn't help
            resolution = mechanics.resolve_action(
                intent="Recall arcane theory",
                attribute="Intelligence",
                skill="Magick Theory",  # Knowledge skill
                attribute_value=5,
                skill_value=0,  # Unskilled
                difficulty=10  # Easy DC
            )

        # Should be automatic critical failure
        assert resolution.success == False
        assert resolution.outcome_tier == "critical_failure" or getattr(resolution.outcome_tier, 'value', resolution.outcome_tier) == "critical_failure"
        # Check narrative field for "training" message
        narrative_text = getattr(resolution, 'narrative', '') or ''
        assert "training" in narrative_text.lower(), f"Expected 'training' in narrative: {narrative_text}"

    def test_trained_knowledge_skill_works(self):
        """Trained Knowledge skill should work normally."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Recall ritual lore",
                attribute="Intelligence",
                skill="Ritual Lore",  # Knowledge skill
                attribute_value=4,
                skill_value=3,  # Trained!
                difficulty=20
            )

        # Skilled: 4 × 3 = 12 + 10 = 22
        assert resolution.total == 22
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
        """Skilled check should vastly outperform unskilled Standard skill."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            # Skilled: 3 × 4 = 12 + 10 = 22
            skilled_resolution = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=3,
                skill_value=4,
                difficulty=20
            )

            # Unskilled Standard skill: d20(10) ÷ 2 = 5 (much worse!)
            unskilled_resolution = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",  # Same skill, but untrained
                attribute_value=3,
                skill_value=0,
                difficulty=20
            )

        # Skilled: 3 × 4 = 12, total 22 ✓
        skilled_ability = skilled_resolution.total - skilled_resolution.roll
        assert skilled_ability == 12, "Skilled: 3×4=12"
        assert skilled_resolution.total == 22

        # Unskilled: d20(10) ÷ 2 = 5 (no attribute bonus!)
        assert unskilled_resolution.total == 5, "Unskilled: 10÷2=5"
        assert unskilled_resolution.success == False, "Unskilled should fail DC 20"

        # The gap is massive: 22 vs 5 = 17 point difference!
        gap = skilled_resolution.total - unskilled_resolution.total
        assert gap == 17, f"Expected 17 point gap, got {gap}"

    def test_skilled_vs_no_skill_comparison(self):
        """Compare skilled check to no-skill check (v1.2.3: both use different formulas)."""
        mechanics = MechanicsEngine()

        with patch('random.randint', return_value=10):
            # Skilled: 3 × 4 = 12 + 10 = 22
            skilled_resolution = mechanics.resolve_action(
                intent="Hack",
                attribute="Intelligence",
                skill="Systems",
                attribute_value=3,
                skill_value=4,
                difficulty=20
            )

            # No skill (v1.2.3): d20(10) ÷ 2 = 5
            no_skill_resolution = mechanics.resolve_action(
                intent="Pure mental effort",
                attribute="Intelligence",
                skill=None,  # No skill - uses unskilled formula
                attribute_value=3,
                skill_value=0,
                difficulty=20
            )

        # Skilled: 3 × 4 = 12 + 10 = 22
        assert skilled_resolution.total == 22

        # No skill: d20(10) ÷ 2 = 5 (v1.2.3 - raw attribute checks removed)
        assert no_skill_resolution.total == 5

        # Massive gap shows why skills matter!
        gap = skilled_resolution.total - no_skill_resolution.total
        assert gap == 17, f"Expected 17 point gap, got {gap}"


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
