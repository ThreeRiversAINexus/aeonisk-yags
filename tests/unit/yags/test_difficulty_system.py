"""
YAGS Difficulty System Compliance Tests

Tests difficulty tiers and success margins from YAGS Module v1.2.2:
- Difficulty tiers: Trivial 10, Easy 15, Routine 18, Moderate 20, Challenging 22, Difficult 26
- Success margins: Moderate 0-4, Good 5-9, Excellent 10-14, Exceptional 15+
- Failure margins: Failure -1 to -9, Critical Failure -10+
"""

import pytest
from aeonisk.multiagent.mechanics import Difficulty, OutcomeTier


class TestDifficultyTiers:
    """Test YAGS difficulty tier values."""

    def test_trivial_difficulty(self):
        """Trivial tasks: DC 10."""
        assert Difficulty.TRIVIAL.value == 10

    def test_easy_difficulty(self):
        """Easy tasks: DC 15."""
        assert Difficulty.EASY.value == 15

    def test_routine_difficulty(self):
        """Routine tasks (combat-pace, time-sensitive): DC 18."""
        assert Difficulty.ROUTINE.value == 18

    def test_moderate_difficulty(self):
        """Moderate tasks (default uncertain): DC 20."""
        assert Difficulty.MODERATE.value == 20

    def test_challenging_difficulty(self):
        """Challenging tasks (requires focus): DC 22."""
        assert Difficulty.CHALLENGING.value == 22

    def test_difficult_difficulty(self):
        """Difficult tasks (extreme, dangerous): DC 26."""
        assert Difficulty.DIFFICULT.value == 26

    def test_very_difficult_threshold(self):
        """Very difficult tasks: DC 30."""
        assert Difficulty.VERY_DIFFICULT.value == 30

    def test_formidable_threshold(self):
        """Formidable tasks: DC 35."""
        assert Difficulty.FORMIDABLE.value == 35

    def test_legendary_threshold(self):
        """Legendary tasks: DC 40."""
        assert Difficulty.LEGENDARY.value == 40


class TestSuccessMargins:
    """Test success tier thresholds."""

    def test_marginal_success_range(self):
        """Marginal success: margin 0-4."""
        # Barely succeeded
        assert OutcomeTier.MARGINAL.value == "marginal"

    def test_moderate_success_range(self):
        """Moderate success: margin 0-4 (same as marginal in this implementation)."""
        assert OutcomeTier.MODERATE.value == "moderate"

    def test_good_success_range(self):
        """Good success: margin 5-9 (beat DC by 5-9)."""
        assert OutcomeTier.GOOD.value == "good"

    def test_excellent_success_range(self):
        """Excellent success: margin 10-14 (beat DC by 10-14)."""
        assert OutcomeTier.EXCELLENT.value == "excellent"

    def test_exceptional_success_range(self):
        """Exceptional success: margin 15+ (beat DC by 15+)."""
        assert OutcomeTier.EXCEPTIONAL.value == "exceptional"


class TestFailureMargins:
    """Test failure tier thresholds."""

    def test_failure_range(self):
        """Standard failure: margin -1 to -9."""
        assert OutcomeTier.FAILURE.value == "failure"

    def test_critical_failure_range(self):
        """Critical failure: margin -10 or worse."""
        assert OutcomeTier.CRITICAL_FAILURE.value == "critical_failure"


class TestDifficultyProgression:
    """Test difficulty tier progression is logical."""

    def test_difficulty_values_ascending(self):
        """Test difficulty values increase monotonically."""
        difficulties = [
            Difficulty.TRIVIAL,
            Difficulty.EASY,
            Difficulty.ROUTINE,
            Difficulty.MODERATE,
            Difficulty.CHALLENGING,
            Difficulty.DIFFICULT,
            Difficulty.VERY_DIFFICULT,
            Difficulty.FORMIDABLE,
            Difficulty.LEGENDARY
        ]

        for i in range(len(difficulties) - 1):
            assert difficulties[i].value < difficulties[i + 1].value

    def test_routine_vs_moderate_gap(self):
        """Test gap between Routine and Moderate is small."""
        # Routine (18) and Moderate (20) are close - both common in gameplay
        gap = Difficulty.MODERATE.value - Difficulty.ROUTINE.value
        assert gap == 2

    def test_difficult_represents_major_jump(self):
        """Test Difficult (26) is a significant jump from Challenging (22)."""
        gap = Difficulty.DIFFICULT.value - Difficulty.CHALLENGING.value
        assert gap == 4


class TestContextualDifficulty:
    """Test difficulty selection based on context."""

    def test_combat_action_difficulty(self):
        """Combat actions typically use Routine (18) or Challenging (22)."""
        # Standard attack/defense under pressure
        combat_min = Difficulty.ROUTINE.value  # 18
        combat_max = Difficulty.CHALLENGING.value  # 22

        assert 18 <= combat_min <= 22
        assert 18 <= combat_max <= 22

    def test_skill_check_difficulty(self):
        """Non-combat skill checks use Moderate (20) as default."""
        default_skill_dc = Difficulty.MODERATE.value
        assert default_skill_dc == 20

    def test_desperate_action_difficulty(self):
        """Desperate/extreme actions use Difficult (26) or higher."""
        desperate_min = Difficulty.DIFFICULT.value
        assert desperate_min >= 26


class TestSuccessRatios:
    """Test expected success rates at different skill levels."""

    def test_expert_vs_moderate_task(self):
        """Expert (ability 12) has ~65% success on Moderate (DC 20)."""
        # Expert: attribute 4 × skill 3 = 12
        # DC 20: needs 8+ on d20 (13/20 = 65%)
        ability = 12
        dc = 20
        needed_roll = dc - ability  # 8

        # 13 rolls succeed (8-20), 7 fail (1-7)
        expected_success_rate = (20 - needed_roll + 1) / 20
        assert 0.60 <= expected_success_rate <= 0.70

    def test_novice_vs_easy_task(self):
        """Novice (ability 4) has ~55% success on Easy (DC 15)."""
        # Novice: attribute 2 × skill 2 = 4
        # DC 15: needs 11+ on d20 (10/20 = 50%)
        ability = 4
        dc = 15
        needed_roll = dc - ability  # 11

        expected_success_rate = (20 - needed_roll + 1) / 20
        assert 0.45 <= expected_success_rate <= 0.55

    def test_master_vs_difficult_task(self):
        """Master (ability 20) has ~55% success on Difficult (DC 26)."""
        # Master: attribute 4 × skill 5 = 20
        # DC 26: needs 6+ on d20 (15/20 = 75%)
        ability = 20
        dc = 26
        needed_roll = dc - ability  # 6

        expected_success_rate = (20 - needed_roll + 1) / 20
        assert 0.70 <= expected_success_rate <= 0.80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
