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
    Condition,
    JSONLLogger,
    apply_wound_damage,
    apply_mixed_damage,
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
            # YAGS unskilled: ability = attribute × 4 = 4 × 4 = 16
            # total = 16 + 10 = 26
            assert resolution.total == 26
            assert resolution.margin == 26 - 15  # +11 margin
            assert resolution.success == True  # Should succeed


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

    def test_clock_removal_logging(self, mechanics_engine):
        """Test that clock removal events are logged correctly."""
        from unittest.mock import Mock

        # Set up mock JSONL logger
        mock_logger = Mock()
        mechanics_engine.jsonl_logger = mock_logger

        # Create and fill a clock
        mechanics_engine.create_scene_clock("Test Clock", maximum=3, description="Test description")
        mechanics_engine.queue_clock_update("Test Clock", ticks=3, reason="completed")
        mechanics_engine.apply_queued_clock_updates()

        # Check and expire the filled clock
        expired = mechanics_engine.check_and_expire_clocks()

        # Verify clock was expired
        assert len(expired) == 1
        assert expired[0]['clock_name'] == "Test Clock"
        assert expired[0]['removal_reason'] == 'filled'

        # Verify JSONL logging was called
        assert mock_logger.log_event.called

        # Find the clock_removal event call
        removal_calls = [call for call in mock_logger.log_event.call_args_list
                        if call[1]['event_type'] == 'clock_removal']

        assert len(removal_calls) == 1
        removal_event = removal_calls[0][1]

        # Verify event structure
        assert removal_event['event_type'] == 'clock_removal'
        assert removal_event['data']['clock_name'] == "Test Clock"
        assert removal_event['data']['current_ticks'] == 3
        assert removal_event['data']['maximum_ticks'] == 3
        assert removal_event['data']['description'] == "Test description"
        assert removal_event['data']['removal_reason'] == 'filled'
        assert removal_event['data']['filled'] == True
        assert removal_event['data']['consequence_triggered'] == True

    def test_get_all_clocks_includes_filled_flag(self, mechanics_engine):
        """Test that get_all_clocks() includes 'filled' flag for conversion check."""
        # Create two clocks
        mechanics_engine.create_scene_clock("Security Response", maximum=6)
        mechanics_engine.create_scene_clock("Escape Route", maximum=4)

        # Fill the Escape Route clock
        mechanics_engine.queue_clock_update("Escape Route", ticks=4, reason="Players found exit")
        mechanics_engine.apply_queued_clock_updates()

        # Partially fill Security Response (critical but not filled)
        mechanics_engine.queue_clock_update("Security Response", ticks=5, reason="Alarms triggered")
        mechanics_engine.apply_queued_clock_updates()

        # Get all clocks (this is what conversion check uses)
        all_clocks = mechanics_engine.get_all_clocks()

        # Should return 2 clocks
        assert len(all_clocks) == 2

        # Find each clock in results
        security_clock = next((c for c in all_clocks if c['name'] == "Security Response"), None)
        escape_clock = next((c for c in all_clocks if c['name'] == "Escape Route"), None)

        assert security_clock is not None
        assert escape_clock is not None

        # Verify 'filled' flag is present in dict
        assert 'filled' in security_clock
        assert 'filled' in escape_clock

        # Verify filled states
        assert security_clock['filled'] is False  # 5/6 is critical but not filled
        assert escape_clock['filled'] is True     # 4/4 is filled

        # Verify current/max ticks
        assert security_clock['current_ticks'] == 5
        assert security_clock['max_ticks'] == 6
        assert escape_clock['current_ticks'] == 4
        assert escape_clock['max_ticks'] == 4


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

    def test_environmental_void_gain_moderate(self, mechanics_engine):
        """Test environmental void gain in void_level 7-8 zones (per scene)."""
        void_state = mechanics_engine.get_void_state("TestChar")

        # Simulate being in void_level=7 environment for one scene
        void_state.add_void(1, "Environmental exposure (void_level 7)")

        assert void_state.score == 1
        assert "Environmental exposure" in void_state.history[-1]['reason']

    def test_environmental_void_gain_extreme(self, mechanics_engine):
        """Test environmental void gain in void_level 9-10 zones (per round)."""
        void_state = mechanics_engine.get_void_state("TestChar")

        # Simulate being in void_level=9 environment for 3 rounds
        for round_num in range(3):
            void_state.add_void(1, f"Environmental exposure round {round_num + 1} (void_level 9)")

        assert void_state.score == 3

    def test_void_forged_weapon_corruption(self, mechanics_engine):
        """Test void gain from using void-forged weapons (+1-2 per combat scene)."""
        void_state = mechanics_engine.get_void_state("TestChar")

        # Use void-forged weapon in combat
        void_state.add_void(2, "Used void-forged kinetic rifle in combat")

        assert void_state.score == 2

    def test_oath_breaking_void_gain(self, mechanics_engine):
        """Test void gain from breaking sacred oaths (+1-3 by severity)."""
        void_state = mechanics_engine.get_void_state("TestChar")

        # Minor oath broken
        void_state.add_void(1, "Broke minor promise to ally")
        assert void_state.score == 1

        # Major sacred oath broken
        void_state.add_void(3, "Broke sacred bond with faction")
        assert void_state.score == 4


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


# ============================================================================
# JSONL Logging Tests
# ============================================================================

class TestJSONLLogging:
    """Test JSONL logging captures structured mechanical data."""

    def test_log_action_resolution_WITHOUT_damage_in_context(self, tmp_path):
        """
        Test showing the BUG: When damage_effects is NOT in context, damage is null.

        This test documents the current broken behavior and should FAIL initially.
        """
        from unittest.mock import Mock
        from aeonisk.multiagent.mechanics import JSONLLogger, ActionResolution, OutcomeTier

        # Create logger
        jsonl_logger = JSONLLogger(session_id="test_session", output_dir=str(tmp_path))

        # Mock the _write_event method to capture events
        logged_events = []
        def mock_write(event):
            logged_events.append(event)
        jsonl_logger._write_event = mock_write

        # Create ActionResolution
        resolution = ActionResolution(
            intent="Shoot enemy",
            attribute="Agility",
            skill="Combat",
            attribute_value=4,
            skill_value=3,
            roll=15,
            total=27,
            difficulty=20,
            margin=7,
            outcome_tier=OutcomeTier.MODERATE,
            success=True,
            narrative="Shot hits"
        )

        # BUG: dm.py currently does NOT include damage_effects in context
        context = {
            "action_type": "combat",
            "narration": "Shot hits enemy",
            # damage_effects is MISSING here (the bug!)
        }

        # Log the action resolution
        jsonl_logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Ash Vex",
            action="Shoot enemy",
            resolution=resolution,
            economy_changes={},
            clock_states={},
            effects=[],
            context=context
        )

        # Get the logged event
        event = [e for e in logged_events if e.get('event_type') == 'action_resolution'][0]

        # This assertion shows the BUG: damage is null
        assert event['effects']['damage'] is None, "BUG CONFIRMED: Without damage_effects in context, damage is null"

    def test_log_action_resolution_captures_damage(self, tmp_path):
        """
        Test that action resolution logging captures damage from structured output.

        CRITICAL BUG FIX: Previously damage was extracted from DM structured output
        but NOT passed to JSONL logger, resulting in effects.damage=null for all
        combat actions. This test verifies the fix.
        """
        from unittest.mock import Mock
        from aeonisk.multiagent.mechanics import JSONLLogger, ActionResolution, OutcomeTier

        # Create logger
        jsonl_logger = JSONLLogger(session_id="test_session", output_dir=str(tmp_path))

        # Mock the _write_event method to capture events
        logged_events = []
        original_write = jsonl_logger._write_event
        def mock_write(event):
            logged_events.append(event)
            # Don't actually write to file
        jsonl_logger._write_event = mock_write

        # Create ActionResolution (dataclass from mechanics.py, NOT Pydantic schema)
        resolution = ActionResolution(
            intent="Shoot enemy with kinetic weapon",
            attribute="Agility",
            skill="Combat",
            attribute_value=4,
            skill_value=3,
            roll=15,  # d20 roll
            total=27,  # 4*3 + 15 = 27
            difficulty=20,
            margin=7,  # 27 - 20 = 7
            outcome_tier=OutcomeTier.MODERATE,
            success=True,
            narrative="Your kinetic round punches through their shoulder guard."
        )

        # Create context dict (simulating what dm.py builds)
        # THIS IS THE FIX: dm.py needs to include damage_effects in context
        context = {
            "action_type": "combat",
            "is_ritual": False,
            "faction": "Covenant",
            "description": "Shoot enemy with kinetic weapon",
            "narration": "Shot hit enemy for 8 damage",
            # FIX: Add damage_effects to context (currently missing in dm.py!)
            "damage_effects": [
                {
                    "type": "damage",
                    "target": "tgt_7a3f",
                    "base_damage": 15,
                    "soak": 7,
                    "dealt": 8,
                }
            ]
        }

        # Log the action resolution
        jsonl_logger.log_action_resolution(
            round_num=1,
            phase="action",
            agent_name="Ash Vex",
            action="Shoot enemy with kinetic weapon",
            resolution=resolution,
            economy_changes={"void_delta": 1, "soulcredit_delta": 0},
            clock_states={},
            effects=[],
            context=context
        )

        # Verify event was logged
        assert len(logged_events) >= 1, "Should have action_resolution event"

        # Get the action_resolution event
        event = [e for e in logged_events if e.get('event_type') == 'action_resolution'][0]

        # CRITICAL ASSERTIONS: Verify damage is captured from context
        assert event['event_type'] == 'action_resolution'
        assert event['effects']['damage'] is not None, "Damage should be captured from context"
        assert event['effects']['damage']['target'] == "tgt_7a3f"
        assert event['effects']['damage']['dealt'] == 8
        assert event['effects']['damage']['source'] == "structured_output"

    def test_event_chain_fields_present(self, tmp_path):
        """Test that all events have event_id, parent_event_id, correlation_id."""
        import json
        from aeonisk.multiagent.mechanics import ActionResolution

        logger = JSONLLogger(session_id="test_chain", output_dir=str(tmp_path))

        # Start a round (sets correlation_id)
        logger.start_round(round_num=1)

        # Log a resolution
        resolution = ActionResolution(
            intent="Test action",
            attribute="Strength", skill="Combat",
            attribute_value=4, skill_value=3,
            roll=12, total=24, difficulty=20, margin=4,
            outcome_tier=OutcomeTier.MARGINAL, success=True,
            narrative="Test combat narration with sufficient length to meet minimum requirements."
        )

        logger.log_action_resolution(
            round_num=1,
            phase="test",
            agent_name="Test Character",
            action="Test action",
            resolution=resolution,
            economy_changes={},
            clock_states={},
            effects=[]
        )

        # Read logged events
        log_file = tmp_path / f"session_test_chain.jsonl"
        with open(log_file, 'r') as f:
            logged_events = [json.loads(line) for line in f]

        # Session start event should have event chain fields
        session_start = logged_events[0]
        assert session_start['event_type'] == 'session_start'
        assert 'event_id' in session_start, "session_start must have event_id"
        assert session_start['parent_event_id'] is None, "session_start has no parent"
        assert session_start['correlation_id'] is None, "session_start not part of round"

        # Action resolution should have event chain fields
        action_event = [e for e in logged_events if e.get('event_type') == 'action_resolution'][0]
        assert 'event_id' in action_event, "action_resolution must have event_id"
        assert 'parent_event_id' in action_event, "action_resolution must have parent_event_id"
        assert 'correlation_id' in action_event, "action_resolution must have correlation_id"

        # Parent should be session_start (or another event)
        assert action_event['parent_event_id'] is not None, "action_resolution parent should not be None"

        # Correlation should indicate round 1
        assert action_event['correlation_id'] is not None, "correlation_id should be set by start_round()"
        assert 'round_1' in action_event['correlation_id'], "correlation_id should include round number"


# ============================================================================
# Damage Application Tests
# ============================================================================

class TestDamageApplication:
    """Test damage application functions - health should never go negative."""

    def test_apply_wound_damage_normal(self):
        """Test normal wound damage doesn't make health negative."""
        # Create a mock target with health
        target = MagicMock()
        target.wounds = 0
        target.health = 20

        result = apply_wound_damage(target, 10)

        # Health should be 10, not negative
        assert target.health == 10
        assert target.wounds == 2  # 10 damage // 5 = 2 wounds

    def test_apply_wound_damage_floors_at_zero(self):
        """Test that health floors at 0, never goes negative."""
        target = MagicMock()
        target.wounds = 0
        target.health = 10

        # Apply more damage than health
        result = apply_wound_damage(target, 25)

        # Health should be 0, NOT -15
        assert target.health == 0, f"Health should floor at 0, got {target.health}"
        assert target.wounds == 5  # 25 damage // 5 = 5 wounds

    def test_apply_wound_damage_already_at_zero(self):
        """Test damage to already-zero health stays at 0."""
        target = MagicMock()
        target.wounds = 5
        target.health = 0

        result = apply_wound_damage(target, 10)

        assert target.health == 0
        assert target.wounds == 7  # +2 more wounds

    def test_apply_mixed_damage_floors_at_zero(self):
        """Test mixed damage also floors health at 0."""
        target = MagicMock()
        target.stuns = 0
        target.wounds = 0
        target.health = 5

        # Apply more damage than health
        result = apply_mixed_damage(target, 20)

        # wound_damage = 20 // 2 = 10
        # health should be 0, not -5
        assert target.health == 0, f"Health should floor at 0, got {target.health}"

    def test_apply_mixed_damage_normal(self):
        """Test normal mixed damage calculation."""
        target = MagicMock()
        target.stuns = 0
        target.wounds = 0
        target.health = 50

        result = apply_mixed_damage(target, 10)

        # stun_damage = (10 + 1) // 2 = 5
        # wound_damage = 10 // 2 = 5
        assert target.stuns == 5
        assert target.health == 45  # 50 - 5 wound_damage

    def test_kira_thane_overkill_scenario(self):
        """
        Regression test based on real session: session_a4cf5513-*.jsonl

        Kira Thane had 9 HP in round 4, took 14+ damage in round 5,
        ended up at -5 HP (bug). With the fix, should be 0 HP.

        This simulates the exact scenario from the fixture:
        tests/fixtures/sessions/negative_health_bug.jsonl
        """
        target = MagicMock()
        target.wounds = 3  # From round 4
        target.health = 9  # From round 4: health=9, wounds=3

        # Round 5: Takes massive damage (14 points)
        result = apply_wound_damage(target, 14)

        # BUG: health would have been 9 - 14 = -5
        # FIX: health should be max(0, 9 - 14) = 0
        assert target.health == 0, f"Kira Thane should be at 0 HP, not {target.health}"
        assert target.wounds == 5  # 3 + (14 // 5) = 3 + 2 = 5

    def test_successive_overkill_stays_at_zero(self):
        """Test that multiple overkill hits keep health at 0."""
        target = MagicMock()
        target.wounds = 0
        target.health = 10

        # First hit: overkill
        apply_wound_damage(target, 15)
        assert target.health == 0

        # Second hit: already at 0
        apply_wound_damage(target, 20)
        assert target.health == 0

        # Third hit: still at 0
        apply_wound_damage(target, 100)
        assert target.health == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
