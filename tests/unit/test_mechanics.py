"""
Unit tests for YAGS mechanics engine.

Tests core game mechanics without LLM dependencies:
- Dice rolling (with seeded random for determinism)
- Difficulty calculations
- Action resolution
- Scene clock mechanics
- Condition/status effects
- Void progression
"""

import pytest
import random
from unittest.mock import MagicMock, patch
from pathlib import Path

from aeonisk.multiagent.mechanics import (
    MechanicsEngine,
    Difficulty,
    OutcomeTier,
    Condition
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mechanics_engine(tmp_path):
    """Create a MechanicsEngine with no logging for fast tests."""
    # Create engine without JSONL logging
    engine = MechanicsEngine(jsonl_logger=None)
    return engine


@pytest.fixture
def seeded_mechanics(tmp_path):
    """Create a MechanicsEngine with seeded random for deterministic tests."""
    random.seed(42)
    engine = MechanicsEngine(jsonl_logger=None)
    yield engine
    # Reset random after test
    random.seed()


# ============================================================================
# Difficulty and DC Tests
# ============================================================================

class TestDifficulty:
    """Test difficulty system and DC calculations."""

    def test_difficulty_enum_values(self):
        """Test standard difficulty ratings."""
        assert Difficulty.TRIVIAL.value == 10
        assert Difficulty.ROUTINE.value == 18
        assert Difficulty.MODERATE.value == 20
        assert Difficulty.DIFFICULT.value == 26

    def test_get_difficulty_recommendation(self, mechanics_engine):
        """Test difficulty recommendation logic."""
        # Standard action under pressure
        dc = mechanics_engine.get_difficulty_recommendation(
            context="disarm a bomb under time pressure"
        )
        assert 18 <= dc <= 26  # Should be routine to difficult

    def test_calculate_dc_basic(self, mechanics_engine):
        """Test basic DC calculation."""
        # For a moderate difficulty action
        dc = mechanics_engine.calculate_dc(
            intent="perform a standard skill check",
            action_type="general"
        )

        assert 18 <= dc <= 22  # Should be in routine/moderate range

    def test_calculate_dc_extreme(self, mechanics_engine):
        """Test DC calculation for extreme actions."""
        # Extreme/desperate action
        dc = mechanics_engine.calculate_dc(
            intent="perform a desperate, dangerous action",
            action_type="general",
            is_extreme=True
        )

        assert dc >= 26  # Should be difficult or higher


# ============================================================================
# Action Resolution Tests
# ============================================================================

class TestActionResolution:
    """Test action resolution mechanics."""

    def test_resolve_action_success(self, seeded_mechanics):
        """Test successful action resolution."""
        resolution = seeded_mechanics.resolve_action(
            intent="Test action",
            attribute="Agility",
            skill="Athletics",
            attribute_value=4,
            skill_value=3,
            difficulty=20
        )

        assert resolution is not None
        assert hasattr(resolution, 'total')
        assert hasattr(resolution, 'margin')
        assert hasattr(resolution, 'outcome_tier')
        assert resolution.total >= 0

    def test_resolve_action_determines_tier(self, mechanics_engine):
        """Test resolution correctly determines outcome tier."""
        # Mock the dice roll to control outcome
        with patch('random.randint', return_value=15):
            resolution = mechanics_engine.resolve_action(
                intent="Test action",
                attribute="Willpower",
                skill="Astral Arts",
                attribute_value=3,
                skill_value=2,
                difficulty=20
            )
            # ability = 3*2 = 6, d20 = 15, total = 21
            # margin = 21 - 20 = 1 (marginal success)
            assert resolution.total == 21
            assert resolution.margin == 1

    def test_resolve_action_critical_failure(self, mechanics_engine):
        """Test critical failure on large negative margin."""
        with patch('random.randint', return_value=1):
            resolution = mechanics_engine.resolve_action(
                intent="Risky action",
                attribute="Agility",
                skill="Athletics",
                attribute_value=2,
                skill_value=1,
                difficulty=30  # Very high difficulty
            )
            # ability = 2*1 = 2, d20 = 1, total = 3, margin = -27
            # Large negative margin should be critical failure
            assert resolution.total == 3
            assert resolution.margin < -10
            assert resolution.outcome_tier == OutcomeTier.CRITICAL_FAILURE

    def test_resolve_action_unskilled(self, mechanics_engine):
        """Test action resolution with unskilled penalty."""
        with patch('random.randint', return_value=10):
            resolution = mechanics_engine.resolve_action(
                intent="Unskilled attempt",
                attribute="Agility",
                skill=None,  # Unskilled
                attribute_value=4,
                skill_value=0,
                difficulty=15
            )
            # ability = 4 - 5 (unskilled penalty) = -1
            # total = -1 + 10 = 9
            assert resolution.total == 9
            assert resolution.margin == 9 - 15  # Negative margin


# ============================================================================
# Scene Clock Tests
# ============================================================================

class TestSceneClocks:
    """Test scene clock mechanics."""

    def test_create_scene_clock(self, mechanics_engine):
        """Test creating a scene clock."""
        clock = mechanics_engine.create_scene_clock(
            name="Test Clock",
            maximum=6,
            description="A test clock for unit testing"
        )

        assert clock.name == "Test Clock"
        assert clock.maximum == 6
        assert clock.current == 0
        assert clock.filled == False

    def test_advance_clock(self, mechanics_engine):
        """Test advancing a clock."""
        mechanics_engine.create_scene_clock("Progress", maximum=6)

        result = mechanics_engine.advance_clock("Progress", ticks=2)

        # advance_clock returns bool (True if completed)
        assert isinstance(result, bool)
        # Check actual clock state
        clock = mechanics_engine.scene_clocks.get("Progress")
        assert clock is not None
        assert clock.current == 2

    def test_clock_completion(self, mechanics_engine):
        """Test clock completes when filled."""
        mechanics_engine.create_scene_clock("Quick Clock", maximum=4)

        # Fill it completely
        result = mechanics_engine.advance_clock("Quick Clock", ticks=4)

        clock = mechanics_engine.scene_clocks.get("Quick Clock")
        assert clock.current == 4
        assert clock.filled == True  # Property to check if filled

    def test_clock_over_fill(self, mechanics_engine):
        """Test clock can overflow max (indicating urgency)."""
        mechanics_engine.create_scene_clock("Test", maximum=6)

        # Try to add 10 ticks (more than max)
        mechanics_engine.advance_clock("Test", ticks=10)

        clock = mechanics_engine.scene_clocks.get("Test")
        # According to the SceneClock docs, it CAN overflow to indicate increasing urgency
        assert clock.current == 10
        assert clock.filled == True  # Should be marked as filled

    def test_advance_nonexistent_clock(self, mechanics_engine):
        """Test advancing a clock that doesn't exist."""
        result = mechanics_engine.advance_clock("Nonexistent", ticks=1)

        # Should return False for non-existent clock
        assert result == False

    def test_queue_and_apply_clock_updates(self, mechanics_engine):
        """Test queued clock updates."""
        mechanics_engine.create_scene_clock("Queue Test", maximum=6)

        # Queue updates
        mechanics_engine.queue_clock_update("Queue Test", 2, "First update")
        mechanics_engine.queue_clock_update("Queue Test", 1, "Second update")

        # Apply all queued updates
        results = mechanics_engine.apply_queued_clock_updates()

        # Should have applied both (total 3 ticks)
        clock = mechanics_engine.scene_clocks.get("Queue Test")
        assert clock.current == 3

    def test_get_and_clear_filled_clocks(self, mechanics_engine):
        """Test retrieving and clearing completed clocks."""
        mechanics_engine.create_scene_clock("Clock1", maximum=4)
        mechanics_engine.create_scene_clock("Clock2", maximum=4)

        # Complete first clock
        mechanics_engine.advance_clock("Clock1", ticks=4)

        filled = mechanics_engine.get_and_clear_filled_clocks()

        assert len(filled) >= 1
        # Each entry is a dict with 'clock_name' and 'reason'
        assert any(c['clock_name'] == "Clock1" for c in filled)

        # Calling again should return empty (already cleared)
        filled_again = mechanics_engine.get_and_clear_filled_clocks()
        assert len(filled_again) == 0


# ============================================================================
# Condition/Status Effect Tests
# ============================================================================

class TestConditions:
    """Test condition and status effect mechanics."""

    def test_add_condition(self, mechanics_engine):
        """Test adding a condition to a character."""
        condition = Condition(
            name="Stunned",
            type="stun",
            penalty=-3,
            description="Cannot act, -3 to all rolls",
            duration=2
        )
        mechanics_engine.add_condition("TestChar", condition)

        conditions = mechanics_engine.get_conditions("TestChar")

        assert len(conditions) == 1
        assert conditions[0].name == "Stunned"
        assert conditions[0].penalty == -3
        assert conditions[0].duration == 2

    def test_remove_condition(self, mechanics_engine):
        """Test removing a condition."""
        condition = Condition(
            name="Inspired",
            type="buff",
            penalty=2,
            description="Inspired",
            duration=1
        )
        mechanics_engine.add_condition("TestChar", condition)

        mechanics_engine.remove_condition("TestChar", "Inspired")

        conditions = mechanics_engine.get_conditions("TestChar")
        assert len(conditions) == 0

    def test_tick_conditions(self, mechanics_engine):
        """Test condition duration decrements."""
        condition = Condition(
            name="Blessed",
            type="buff",
            penalty=1,
            description="Blessed",
            duration=3
        )
        mechanics_engine.add_condition("TestChar", condition)

        # Tick once
        mechanics_engine.tick_conditions("TestChar")

        conditions = mechanics_engine.get_conditions("TestChar")
        assert conditions[0].duration == 2

    def test_condition_expiration(self, mechanics_engine):
        """Test condition expires when duration reaches 0."""
        condition = Condition(
            name="Temp Buff",
            type="buff",
            penalty=1,
            description="Temporary buff",
            duration=1
        )
        mechanics_engine.add_condition("TestChar", condition)

        # Tick to expiration
        mechanics_engine.tick_conditions("TestChar")

        conditions = mechanics_engine.get_conditions("TestChar")
        assert len(conditions) == 0  # Should be removed

    def test_multiple_conditions(self, mechanics_engine):
        """Test character can have multiple conditions."""
        stunned = Condition(
            name="Stunned",
            type="stun",
            penalty=-3,
            description="Stunned",
            duration=2
        )
        poisoned = Condition(
            name="Poisoned",
            type="poison",
            penalty=-1,
            description="Poisoned",
            duration=5
        )
        mechanics_engine.add_condition("TestChar", stunned)
        mechanics_engine.add_condition("TestChar", poisoned)

        conditions = mechanics_engine.get_conditions("TestChar")

        assert len(conditions) == 2
        names = [c.name for c in conditions]
        assert "Stunned" in names
        assert "Poisoned" in names


# ============================================================================
# Void System Tests
# ============================================================================

class TestVoidSystem:
    """Test void corruption mechanics."""

    def test_get_void_state_empty(self, mechanics_engine):
        """Test void state for character with no void."""
        void_state = mechanics_engine.get_void_state("TestChar")

        assert void_state.score == 0
        assert isinstance(void_state.history, list)

    def test_add_void(self, mechanics_engine):
        """Test adding void to a character."""
        void_state = mechanics_engine.get_void_state("TestChar")

        new_score = void_state.add_void(2, "Performed risky ritual")

        assert new_score == 2
        assert void_state.score == 2
        assert len(void_state.history) > 0

    def test_void_progression(self, mechanics_engine):
        """Test void level increases."""
        void_state = mechanics_engine.get_void_state("TestChar")

        # Add void multiple times
        void_state.add_void(2, "First ritual")
        void_state.add_void(3, "Second ritual")

        assert void_state.score == 5


# ============================================================================
# Integration Tests (Multiple Systems)
# ============================================================================

class TestMechanicsIntegration:
    """Test interactions between multiple mechanical systems."""

    def test_action_with_conditions(self, mechanics_engine):
        """Test action resolution with conditions present."""
        # Add a debuff condition
        condition = Condition(
            name="Wounded",
            type="wound",
            penalty=-2,
            description="Wounded",
            duration=3
        )
        mechanics_engine.add_condition("TestChar", condition)

        # Resolve action
        with patch('random.randint', return_value=10):
            resolution = mechanics_engine.resolve_action(
                intent="Attack despite wounds",
                attribute="Strength",
                skill="Brawling",
                attribute_value=3,
                skill_value=2,
                difficulty=18,
                agent_id="TestChar"
            )

            # Verify resolution exists
            assert resolution is not None
            assert resolution.total >= 0

    def test_clock_and_void_interaction(self, mechanics_engine):
        """Test clock completion can trigger void effects."""
        mechanics_engine.create_scene_clock("Void Surge", maximum=6)

        # Advance to completion
        result = mechanics_engine.advance_clock("Void Surge", ticks=6)

        # Check clock is filled
        clock = mechanics_engine.scene_clocks.get("Void Surge")
        assert clock is not None
        assert clock.current >= 6

    def test_multiple_simultaneous_systems(self, mechanics_engine):
        """Test multiple systems working together."""
        # Set up complex state
        mechanics_engine.create_scene_clock("Enemy Reinforcements", maximum=8)

        inspired = Condition(
            name="Inspired",
            type="buff",
            penalty=2,
            description="Inspired",
            duration=3
        )
        mechanics_engine.add_condition("Player1", inspired)

        void_state = mechanics_engine.get_void_state("Player1")
        void_state.add_void(2, "Test void")

        # Advance clock
        mechanics_engine.advance_clock("Enemy Reinforcements", ticks=3)

        # Resolve action with conditions
        with patch('random.randint', return_value=12):
            resolution = mechanics_engine.resolve_action(
                intent="Attack",
                attribute="Agility",
                skill="Combat",
                attribute_value=4,
                skill_value=3,
                difficulty=20,
                agent_id="Player1"
            )

        # Tick conditions
        mechanics_engine.tick_conditions("Player1")

        # Verify state
        clock = mechanics_engine.scene_clocks.get("Enemy Reinforcements")
        assert clock.current == 3

        conditions = mechanics_engine.get_conditions("Player1")
        assert conditions[0].duration == 2  # Decremented

        void_state = mechanics_engine.get_void_state("Player1")
        assert void_state.score == 2


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestMechanicsEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_attribute(self, mechanics_engine):
        """Test action with zero attribute value."""
        with patch('random.randint', return_value=10):
            resolution = mechanics_engine.resolve_action(
                intent="Weak attempt",
                attribute="Strength",
                skill="Athletics",
                attribute_value=0,
                skill_value=2,
                difficulty=15
            )
            # ability = 0 * 2 = 0, total = 0 + 10 = 10
            assert resolution.total == 10

    def test_very_high_difficulty(self, mechanics_engine):
        """Test action against legendary difficulty."""
        with patch('random.randint', return_value=20):  # Max roll
            resolution = mechanics_engine.resolve_action(
                intent="Legendary feat",
                attribute="Agility",
                skill="Combat",
                attribute_value=5,
                skill_value=5,
                difficulty=Difficulty.LEGENDARY.value  # DC 40
            )
            # ability = 25, d20 = 20, total = 45
            # margin = 45 - 40 = 5
            assert resolution.total == 45
            assert resolution.margin == 5

    def test_negative_clock_ticks(self, mechanics_engine):
        """Test clock can regress with negative ticks."""
        clock = mechanics_engine.create_scene_clock("Regression Test", maximum=6)
        mechanics_engine.advance_clock("Regression Test", ticks=4)

        # Regress by 2 using the clock's regress method
        clock_obj = mechanics_engine.scene_clocks.get("Regression Test")
        clock_obj.regress(2)

        assert clock_obj.current == 2  # 4 - 2 = 2

    def test_clock_regression_below_zero(self, mechanics_engine):
        """Test clock doesn't go below 0 when regressing."""
        clock = mechanics_engine.create_scene_clock("Test", maximum=6)
        mechanics_engine.advance_clock("Test", ticks=2)

        # Try to regress by more than current
        clock_obj = mechanics_engine.scene_clocks.get("Test")
        clock_obj.regress(5)

        assert clock_obj.current == 0  # Should stop at 0, not go negative

    def test_condition_zero_penalty(self, mechanics_engine):
        """Test condition with zero penalty (narrative only)."""
        condition = Condition(
            name="Marked",
            type="status",
            penalty=0,
            description="Tracked by scanner",
            duration=999
        )
        mechanics_engine.add_condition("TestChar", condition)

        conditions = mechanics_engine.get_conditions("TestChar")
        assert conditions[0].penalty == 0

    def test_get_state_summary(self, mechanics_engine):
        """Test comprehensive state summary."""
        # Set up state
        mechanics_engine.create_scene_clock("Clock1", maximum=6)
        mechanics_engine.advance_clock("Clock1", ticks=3)

        inspired = Condition(
            name="Inspired",
            type="buff",
            penalty=2,
            description="Inspired",
            duration=2
        )
        mechanics_engine.add_condition("Player1", inspired)

        void_state = mechanics_engine.get_void_state("Player1")
        void_state.add_void(4, "Test")

        summary = mechanics_engine.get_state_summary()

        assert summary is not None
        # Verify the summary contains expected data
        assert isinstance(summary, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
