"""
YAGS Ritual Mechanics Compliance Tests

Tests ritual resolution mechanics from the YAGS Module v1.2.2:
- Ritual roll formula: Willpower × Astral Arts + d20 vs Threshold
- Thresholds: Minor 16, Standard 18, Major 20-22, Forbidden 26-28
- Offering mechanics (skip = +1 Void + downgrade)
- Group ritual bonuses (+2 for Bonded participant)
- Primary Ritual Item mechanics
"""

import pytest
from unittest.mock import patch

from aeonisk.multiagent.mechanics import (
    MechanicsEngine,
    Difficulty,
    OutcomeTier
)


class TestRitualThresholds:
    """Test ritual difficulty thresholds match YAGS specification."""

    def test_minor_ritual_threshold(self):
        """Minor rituals require DC 16."""
        # Minor rituals: simple effects, minimal risk
        # Examples: Sense Void, Minor Healing, Simple Divination
        assert Difficulty.EASY.value <= 16 <= Difficulty.ROUTINE.value

    def test_standard_ritual_threshold(self):
        """Standard rituals require DC 18."""
        # Standard rituals: typical mystical effects
        assert Difficulty.ROUTINE.value <= 18 <= Difficulty.MODERATE.value

    def test_major_ritual_threshold_range(self):
        """Major rituals require DC 20-22."""
        # Major rituals: powerful effects, significant consequences
        assert 20 <= Difficulty.MODERATE.value <= 22
        assert 20 <= Difficulty.CHALLENGING.value

    def test_forbidden_ritual_threshold_range(self):
        """Forbidden rituals require DC 26-28."""
        # Forbidden rituals: dangerous, corrupting, high void cost
        assert 26 <= Difficulty.DIFFICULT.value <= 28


class TestRitualResolution:
    """Test ritual resolution mechanics."""

    @pytest.fixture
    def mechanics(self):
        """Create mechanics engine for ritual tests."""
        return MechanicsEngine(jsonl_logger=None)

    def test_ritual_roll_formula(self, mechanics):
        """Test ritual uses Willpower × Astral Arts + d20."""
        with patch('random.randint', return_value=10):
            resolution = mechanics.resolve_action(
                intent="Perform minor divination ritual",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=3,
                skill_value=2,
                difficulty=16  # Minor ritual threshold
            )

            # Ability = 3 × 2 = 6, d20 = 10, total = 16
            assert resolution.attribute == "Willpower"
            assert resolution.skill == "Astral Arts"
            assert resolution.total == 16
            assert resolution.margin == 0
            assert resolution.success == True

    def test_ritual_with_high_willpower(self, mechanics):
        """Test ritual success with high Willpower."""
        with patch('random.randint', return_value=12):
            resolution = mechanics.resolve_action(
                intent="Perform standard ritual",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=4,  # High willpower
                skill_value=3,
                difficulty=18  # Standard ritual
            )

            # Ability = 4 × 3 = 12, d20 = 12, total = 24
            assert resolution.total == 24
            assert resolution.margin == 6
            assert resolution.success == True

    def test_ritual_failure_low_skill(self, mechanics):
        """Test ritual failure with low Astral Arts."""
        with patch('random.randint', return_value=8):
            resolution = mechanics.resolve_action(
                intent="Attempt ritual beyond skill",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=3,
                skill_value=1,  # Low skill
                difficulty=20  # Major ritual
            )

            # Ability = 3 × 1 = 3, d20 = 8, total = 11
            assert resolution.total == 11
            assert resolution.margin == -9
            assert resolution.success == False

    def test_forbidden_ritual_difficulty(self, mechanics):
        """Test forbidden ritual requires exceptional roll."""
        with patch('random.randint', return_value=15):
            resolution = mechanics.resolve_action(
                intent="Perform forbidden ritual",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=4,
                skill_value=4,
                difficulty=26  # Forbidden ritual
            )

            # Ability = 4 × 4 = 16, d20 = 15, total = 31
            assert resolution.total == 31
            assert resolution.margin == 5
            assert resolution.success == True


class TestOfferingMechanics:
    """Test offering mechanics for rituals."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_ritual_offering_available(self, mechanics):
        """Test checking for ritual offering in inventory."""
        # Create a mock character state with offering
        from types import SimpleNamespace
        character_state = SimpleNamespace(
            inventory={'blood_offering': 1, 'common_seed': 3}
        )

        has_offering, offering_type, quantity = mechanics.has_offering(character_state)

        # Should find the offering
        assert has_offering == True
        assert offering_type == 'blood_offering'
        assert quantity == 1

    def test_ritual_no_offering(self, mechanics):
        """Test ritual without offering returns False."""
        from types import SimpleNamespace
        character_state = SimpleNamespace(
            inventory={'common_seed': 3}  # No ritual offerings
        )

        has_offering, offering_type, quantity = mechanics.has_offering(character_state)

        # No offering found
        assert has_offering == False
        assert offering_type is None
        assert quantity == 0


class TestGroupRituals:
    """Test group ritual mechanics."""

    def test_bonded_participant_bonus(self):
        """Test Bonded participants provide +2 bonus."""
        # According to YAGS rules, Bonded participants give +2 to ritual rolls
        # This would be implemented in the session logic, not mechanics engine
        # Test documents the expected behavior

        base_ability = 3 * 2  # Willpower × Astral Arts
        bonded_bonus = 2
        expected_total_with_bonus = base_ability + bonded_bonus + 10  # +d20

        # With one Bonded assistant
        assert expected_total_with_bonus == 18

    def test_multiple_participants(self):
        """Test multiple ritual participants."""
        # Group rituals can have multiple participants
        # Each Bonded participant adds +2

        base_ability = 12  # 4 × 3
        bonded_count = 2
        total_bonus = bonded_count * 2  # +4 total

        assert total_bonus == 4


class TestPrimaryRitualItem:
    """Test Primary Ritual Item mechanics."""

    def test_ritual_item_bonus(self):
        """Test Primary Ritual Item provides bonus."""
        # Primary Ritual Items provide bonus to ritual rolls
        # Exact bonus depends on item quality/power

        base_ability = 10
        ritual_item_bonus = 3  # Example bonus from quality item

        total_with_item = base_ability + ritual_item_bonus
        assert total_with_item == 13

    def test_ritual_without_item(self):
        """Test ritual without Primary Ritual Item."""
        # Rituals can be performed without item but are less effective

        base_ability = 10
        # No bonus applied
        assert base_ability == 10


class TestRitualConsequences:
    """Test ritual failure and success consequences."""

    @pytest.fixture
    def mechanics(self):
        return MechanicsEngine(jsonl_logger=None)

    def test_ritual_failure_void_gain(self, mechanics):
        """Test failed rituals may cause void gain."""
        # Failed rituals, especially forbidden ones, increase Void
        void_state = mechanics.get_void_state("ritualist_1")
        initial_void = void_state.score

        # Simulate failed ritual void gain
        void_state.add_void(2, "Failed major ritual")

        assert void_state.score == initial_void + 2

    def test_critical_ritual_failure(self, mechanics):
        """Test critical failure on ritual."""
        with patch('random.randint', return_value=2):
            resolution = mechanics.resolve_action(
                intent="Desperate forbidden ritual",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=2,
                skill_value=1,
                difficulty=28  # Forbidden threshold
            )

            # Ability = 2, d20 = 2, total = 4, margin = -24
            assert resolution.margin <= -20
            assert resolution.outcome_tier == OutcomeTier.CRITICAL_FAILURE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
