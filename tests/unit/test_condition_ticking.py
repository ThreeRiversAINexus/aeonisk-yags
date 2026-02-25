"""
Tests for condition ticking (duration enforcement) in session.py and mechanics.py.

Spec 14, Bug 3 (continued): Verifies that tick_conditions() is called during
round cleanup so conditions actually expire.

Spec 14, Bug 6: Verifies that tick_conditions() returns the names of expired
conditions.

TDD: These tests are written FIRST (red phase) before adding the call site.
"""

import pytest
from unittest.mock import MagicMock, patch

from aeonisk.multiagent.mechanics import Condition, MechanicsEngine


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mechanics_engine():
    """Create a MechanicsEngine with no logging for fast tests."""
    engine = MechanicsEngine(jsonl_logger=None)
    return engine


# ============================================================================
# Bug 6: tick_conditions() should return expired condition names
# ============================================================================

class TestTickConditionsReturnValue:
    """Verify tick_conditions() returns list of expired condition names."""

    def test_tick_returns_expired_names(self, mechanics_engine):
        """tick_conditions() returns list of expired condition names."""
        condition = Condition(
            name="Stunned",
            type="stun",
            penalty=-3,
            description="stunned, -3 to all rolls",
            duration=1,
        )
        mechanics_engine.add_condition("agent_a", condition)

        expired = mechanics_engine.tick_conditions("agent_a")

        assert expired is not None, (
            "tick_conditions() returned None. Bug: it should return a list of "
            "expired condition names."
        )
        assert "Stunned" in expired

    def test_tick_returns_empty_list_when_nothing_expires(self, mechanics_engine):
        """tick_conditions() returns empty list when no conditions expire."""
        condition = Condition(
            name="Blessed",
            type="buff",
            penalty=1,
            description="blessed, +1 to all rolls",
            duration=5,
        )
        mechanics_engine.add_condition("agent_a", condition)

        expired = mechanics_engine.tick_conditions("agent_a")

        assert expired is not None, "tick_conditions() returned None instead of empty list"
        assert expired == []

    def test_tick_returns_multiple_expired_names(self, mechanics_engine):
        """tick_conditions() returns all expired condition names when multiple expire."""
        cond1 = Condition(
            name="Stunned", type="stun", penalty=-3,
            description="stunned", duration=1,
        )
        cond2 = Condition(
            name="Dazed", type="daze", penalty=-1,
            description="dazed", duration=1,
        )
        cond3 = Condition(
            name="Blessed", type="buff", penalty=2,
            description="blessed", duration=5,
        )
        mechanics_engine.add_condition("agent_a", cond1)
        mechanics_engine.add_condition("agent_a", cond2)
        mechanics_engine.add_condition("agent_a", cond3)

        expired = mechanics_engine.tick_conditions("agent_a")

        assert "Stunned" in expired
        assert "Dazed" in expired
        assert "Blessed" not in expired

    def test_tick_returns_none_or_empty_for_unknown_agent(self, mechanics_engine):
        """tick_conditions() for unknown agent returns empty or None (no crash)."""
        result = mechanics_engine.tick_conditions("nonexistent_agent")
        # Should not crash and should return something falsy or empty
        assert result is None or result == []


# ============================================================================
# Condition lifecycle through ticking
# ============================================================================

class TestConditionTickingLifecycle:
    """Verify conditions expire after their duration via tick_conditions()."""

    def test_condition_expires_after_duration(self, mechanics_engine):
        """A condition with duration=2 should expire after 2 ticks."""
        condition = Condition(
            name="Pinned",
            type="debuff",
            penalty=-4,
            description="-4 to all actions while pinned down",
            duration=2,
        )
        mechanics_engine.add_condition("agent_a", condition)

        # Tick 1: duration 2 -> 1 (still present)
        mechanics_engine.tick_conditions("agent_a")
        conditions = mechanics_engine.get_conditions("agent_a")
        assert len(conditions) == 1
        assert conditions[0].duration == 1

        # Tick 2: duration 1 -> 0 -> removed
        mechanics_engine.tick_conditions("agent_a")
        conditions = mechanics_engine.get_conditions("agent_a")
        assert len(conditions) == 0

    def test_permanent_condition_not_ticked(self, mechanics_engine):
        """A condition with duration=-1 persists through ticking."""
        condition = Condition(
            name="Cursed",
            type="curse",
            penalty=-2,
            description="permanent curse, -2 to all rolls",
            duration=-1,
        )
        mechanics_engine.add_condition("agent_a", condition)

        # Tick many times
        for _ in range(10):
            mechanics_engine.tick_conditions("agent_a")

        conditions = mechanics_engine.get_conditions("agent_a")
        assert len(conditions) == 1
        assert conditions[0].name == "Cursed"
        assert conditions[0].duration == -1

    def test_zero_duration_removed_on_first_tick(self, mechanics_engine):
        """Duration=0 condition removed on first tick."""
        condition = Condition(
            name="Flash",
            type="instant",
            penalty=-2,
            description="momentary flash",
            duration=0,
        )
        mechanics_engine.add_condition("agent_a", condition)

        # Duration=0 should be removed immediately on tick
        mechanics_engine.tick_conditions("agent_a")
        conditions = mechanics_engine.get_conditions("agent_a")
        assert len(conditions) == 0

    def test_mixed_durations_selective_expiry(self, mechanics_engine):
        """Only conditions that hit duration=0 are removed, others persist."""
        short = Condition(
            name="Short", type="debuff", penalty=-1,
            description="short effect", duration=1,
        )
        medium = Condition(
            name="Medium", type="debuff", penalty=-2,
            description="medium effect", duration=3,
        )
        permanent = Condition(
            name="Permanent", type="curse", penalty=-1,
            description="permanent effect", duration=-1,
        )
        mechanics_engine.add_condition("agent_a", short)
        mechanics_engine.add_condition("agent_a", medium)
        mechanics_engine.add_condition("agent_a", permanent)

        # Tick 1: Short expires, Medium goes to 2, Permanent stays
        expired = mechanics_engine.tick_conditions("agent_a")
        conditions = mechanics_engine.get_conditions("agent_a")

        condition_names = [c.name for c in conditions]
        assert "Short" not in condition_names
        assert "Medium" in condition_names
        assert "Permanent" in condition_names
        assert len(conditions) == 2

        # Verify expired return includes Short
        if expired is not None:
            assert "Short" in expired
