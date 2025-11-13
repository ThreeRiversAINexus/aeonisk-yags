"""
Tests for clock updates before conversion check integration.

This test suite verifies that:
1. Clock updates are applied BEFORE conversion check phase
2. Filled clocks are properly flagged with 'filled' attribute
3. Critical clocks (80%+) are NOT marked filled unless they actually reach max
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


@pytest.fixture
def mechanics_with_clocks():
    """Create mechanics engine with test clocks."""
    mechanics = MechanicsEngine(
        jsonl_logger=None,
        shared_state=None
    )

    # Add test clocks
    mechanics.create_scene_clock(
        name="Security Response",
        maximum=6,
        description="Guards responding to alarm",
        advance_meaning="Guards mobilizing",
        filled_consequence="Security reinforcements arrive"
    )

    mechanics.create_scene_clock(
        name="Escape Route Found",
        maximum=4,
        description="Players finding escape path",
        advance_meaning="Path becoming clearer",
        filled_consequence="Safe exit discovered"
    )

    return mechanics


class TestClockUpdateTiming:
    """Test clock updates happen before conversion check."""

    def test_clocks_updated_before_conversion_check(self, mechanics_with_clocks):
        """Verify clock updates are applied before conversion check sees them."""
        # Queue clock updates (simulating action resolutions)
        mechanics_with_clocks.queue_clock_update(
            clock_name="Security Response",
            ticks=3,
            reason="Failed stealth checks"
        )

        # Apply updates (this happens in session.py before conversion check)
        updates = mechanics_with_clocks.apply_queued_clock_updates()

        # Verify update was applied
        assert "Security Response" in updates
        assert updates["Security Response"][0]['new_value'] == 3

        # Verify conversion check can now see updated clock state
        clock = mechanics_with_clocks.get_clock("Security Response")
        assert clock['current_ticks'] == 3
        assert clock['max_ticks'] == 6

    def test_filled_clocks_flagged(self, mechanics_with_clocks):
        """Verify filled clocks get 'filled' flag set."""
        # Fill the "Escape Route Found" clock (max=4)
        mechanics_with_clocks.queue_clock_update(
            clock_name="Escape Route Found",
            ticks=4,
            reason="Successful navigation"
        )

        # Apply updates
        mechanics_with_clocks.apply_queued_clock_updates()

        # Check filled flag
        clock = mechanics_with_clocks.get_clock("Escape Route Found")
        assert clock['filled'] is True
        assert clock['current_ticks'] == 4
        assert clock['max_ticks'] == 4

    def test_critical_clocks_not_marked_filled(self, mechanics_with_clocks):
        """Verify critical clocks (80%+) are NOT marked filled unless they actually fill."""
        # Advance to 5/6 (83% - critical but not filled)
        mechanics_with_clocks.queue_clock_update(
            clock_name="Security Response",
            ticks=5,
            reason="Multiple failures"
        )

        # Apply updates
        mechanics_with_clocks.apply_queued_clock_updates()

        # Check NOT filled
        clock = mechanics_with_clocks.get_clock("Security Response")
        assert clock.get('filled', False) is False
        assert clock['current_ticks'] == 5
        assert clock['max_ticks'] == 6

        # Calculate percent for testing marker logic
        percent = int((5 / 6) * 100)
        assert percent >= 80  # Would get ⚠️ CRITICAL marker
        assert percent < 100  # But NOT 🎯 FILLED marker

    def test_multiple_clocks_filled(self, mechanics_with_clocks):
        """Verify multiple clocks can fill simultaneously."""
        # Fill both clocks
        mechanics_with_clocks.queue_clock_update("Security Response", 6, "Alarm")
        mechanics_with_clocks.queue_clock_update("Escape Route Found", 4, "Navigation")
        mechanics_with_clocks.apply_queued_clock_updates()

        # Both should be filled
        security_clock = mechanics_with_clocks.get_clock("Security Response")
        escape_clock = mechanics_with_clocks.get_clock("Escape Route Found")

        assert security_clock['filled'] is True
        assert escape_clock['filled'] is True


# NOTE: Integration tests for DM conversion check seeing filled clocks
# are better tested via end-to-end session tests or manual gameplay.
# The mechanics tests above verify the core clock update timing behavior
# that enables conversion check to make informed decisions based on filled clocks.
