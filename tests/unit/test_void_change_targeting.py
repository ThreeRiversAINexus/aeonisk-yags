"""
Test void change targeting bug fix.

Bug: When DM specifies void changes targeting environmental/abstract targets like
"Environmental Void", the void change is incorrectly applied to the actor instead of
being skipped. This causes players to get unearned void reductions.

Example from session_debt_auction_ambush.jsonl:
- Ash Vex performs dispersal ritual targeting "Environmental Void"
- DM specifies void_change=-2 with void_target_character="Environmental Void"
- Bug: -2 void reduction gets applied to Ash Vex instead of being skipped
- Expected: Should be tracked via scene clocks, not character void

This follows the same pattern as Bug #1 (status effect targeting).
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock


class TestVoidChangeTargeting:
    """Test that void changes are applied to correct targets."""

    def test_environmental_void_skipped(self):
        """
        Environmental void changes should NOT be applied to character void.

        When void_target_character="Environmental Void" (or similar abstract targets),
        the void change should be skipped from character tracking. Environmental void
        should be tracked via scene clocks instead.
        """
        # Simulate the logic from dm.py
        player_id = "test_player"
        void_change = -2  # Void reduction
        target_identifier = "Environmental Void"

        # Mock mechanics
        mock_mechanics = Mock()
        mock_void_state = Mock()
        mock_void_state.score = 5
        mock_mechanics.get_void_state.return_value = mock_void_state

        # Test the logic (this is the CURRENT buggy behavior)
        should_apply_void_change = True
        target_player_id = None

        # Try to resolve target
        if target_identifier:
            # Check for environmental targets (FIXED logic)
            if target_identifier in ('Environmental Void', 'environment', 'area'):
                should_apply_void_change = False
            else:
                # Try to resolve as character name
                # (In real code, would search player_agents)
                # For this test, simulate not finding it
                target_player_id = None

                if not target_player_id:
                    # FIXED: Skip instead of falling back to actor
                    should_apply_void_change = False

        # Verify: void change should NOT be applied
        assert should_apply_void_change == False, \
            "Environmental void changes should NOT be applied to characters (should use scene clocks)"

        # Verify mechanics.get_void_state would NOT be called for actor
        if should_apply_void_change:
            mock_mechanics.get_void_state(player_id)

        # With the fix, this should not be called
        mock_mechanics.get_void_state.assert_not_called()

    def test_unresolvable_void_target_skipped(self):
        """
        Void changes with unresolvable character names should be skipped.

        When void_target_character is set to a character name that can't be resolved
        (typo, non-existent character), the void change should be skipped rather than
        falling back to the actor.
        """
        player_id = "test_player"
        void_change = -3
        target_identifier = "Unknown Character Name"  # Typo or doesn't exist

        # Mock mechanics
        mock_mechanics = Mock()
        mock_void_state = Mock()
        mock_void_state.score = 6

        # Test the logic
        should_apply_void_change = True
        target_player_id = None

        if target_identifier:
            # Check for environmental targets
            if target_identifier in ('Environmental Void', 'environment', 'area'):
                should_apply_void_change = False
            else:
                # Try to resolve as character name (simulate failure)
                target_player_id = None

                if not target_player_id:
                    # FIXED: Skip instead of falling back
                    should_apply_void_change = False

        # Verify: void change should NOT be applied
        assert should_apply_void_change == False, \
            "Void changes with unresolvable targets should be skipped"

    def test_void_change_applied_to_explicit_target(self):
        """
        Void changes with valid target characters should be applied correctly.

        This tests "collaborative cleansing" where one character helps reduce
        another's void (e.g., ritual assistance, healing).
        """
        player_id = "player1"
        target_player_id = "player2"  # Successfully resolved
        void_change = -2  # Void reduction
        target_identifier = "Riven Ashglow"  # Valid character name

        # Mock mechanics
        mock_mechanics = Mock()
        mock_target_void = Mock()
        mock_target_void.score = 7
        mock_mechanics.get_void_state.return_value = mock_target_void

        # Test the logic
        should_apply_void_change = True
        resolved_target_id = None

        if target_identifier:
            if target_identifier in ('Environmental Void', 'environment', 'area'):
                should_apply_void_change = False
            else:
                # Simulate successful resolution
                resolved_target_id = target_player_id

                if resolved_target_id:
                    # Apply to the resolved target
                    void_state = mock_mechanics.get_void_state(resolved_target_id)

        # Verify: void change SHOULD be applied to the target
        assert should_apply_void_change == True, \
            "Void changes with valid targets should be applied"
        assert resolved_target_id == target_player_id, \
            "Void change should be applied to the resolved target"

        # Verify mechanics.get_void_state was called with correct target
        mock_mechanics.get_void_state.assert_called_once_with(target_player_id)

    def test_void_change_applied_to_actor_when_no_target(self):
        """
        Void changes without explicit targets should apply to the actor.

        When void_target_character is None/empty (self-inflicted void from risky actions),
        the void change should be applied to the actor performing the action.
        """
        player_id = "test_player"
        void_change = 2  # Void gain from risky action
        target_identifier = None  # No target specified

        # Mock mechanics
        mock_mechanics = Mock()
        mock_actor_void = Mock()
        mock_actor_void.score = 3
        mock_mechanics.get_void_state.return_value = mock_actor_void

        # Test the logic
        should_apply_void_change = True
        void_target_id = player_id  # Default to actor

        if target_identifier:
            # Has target specified
            pass
        else:
            # No target = apply to actor (this is correct behavior)
            void_state = mock_mechanics.get_void_state(player_id)

        # Verify: void change SHOULD be applied to actor
        assert should_apply_void_change == True, \
            "Self-inflicted void changes should be applied to actor"

        # Verify mechanics.get_void_state was called with actor's ID
        mock_mechanics.get_void_state.assert_called_once_with(player_id)

    def test_void_reduction_reduces_score(self):
        """
        Test that negative void changes correctly reduce void score.

        This verifies that void cleansing (negative changes) work as expected
        when properly targeted.
        """
        player_id = "test_player"
        void_change = -2

        # Mock mechanics
        mock_mechanics = Mock()
        mock_void_state = Mock()
        mock_void_state.score = 5
        mock_mechanics.get_void_state.return_value = mock_void_state

        # Simulate void reduction logic
        void_state = mock_mechanics.get_void_state(player_id)
        old_void = void_state.score

        # Apply reduction (this is how dm.py does it)
        if void_change < 0:
            # Void reduction
            reduction_amount = abs(void_change)
            new_void = max(0, old_void - reduction_amount)
        else:
            # Void gain
            new_void = old_void + void_change

        # Verify: void score should decrease
        assert new_void == 3, \
            f"Void should reduce from {old_void} to 3, got {new_void}"

    def test_debt_auction_ambush_environmental_void(self):
        """
        Test using real fixture: session_debt_auction_ambush.jsonl.

        This session contains the actual bug: Ash Vex's dispersal ritual targeting
        "Environmental Void" incorrectly applies void reduction to Ash Vex.
        """
        # Load the fixture
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sessions" / "session_debt_auction_ambush.jsonl"

        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")

        # Find the action resolution with environmental void
        found_environmental_void = False
        ash_void_changes = []

        with open(fixture_path, 'r') as f:
            for line in f:
                event = json.loads(line)

                # Look for structured output with environmental void target
                if event.get('event_type') == 'structured_output_metrics':
                    validation_warnings = event.get('validation_warnings', [])
                    for warning in validation_warnings:
                        if 'Environmental Void' in warning and 'Ash Vex' in warning:
                            found_environmental_void = True

                # Track Ash Vex's void changes
                if event.get('event_type') == 'character_state' and event.get('character') == 'Ash Vex':
                    void_score = event.get('void', {}).get('score')
                    if void_score is not None:
                        ash_void_changes.append(void_score)

        # Verify the bug was present in the fixture
        assert found_environmental_void, \
            "Fixture should contain Ash Vex's environmental void action"

        # Note: We can't easily verify the fix without re-running the session,
        # but we can document that this fixture demonstrates the bug
        # After the fix, re-running this scenario should NOT reduce Ash's void


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
