"""
Tests for Spec 15 extension: Condition-based resolution skip triggers.

After Spec 14 conditions are working, agents with incapacitating conditions
(abs(penalty) >= 6) should be auto-skipped during the resolution phase.

This is additive to the existing ResolutionState.is_incapacitated() check —
conditions are scanned BEFORE the existing check and feed into it by marking
the agent as incapacitated in resolution_state.
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from scripts.aeonisk.multiagent.mechanics import Condition
from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState


# =============================================================================
# CONSTANTS (match session.py implementation)
# =============================================================================

INCAPACITATION_THRESHOLD = 6  # abs(penalty) >= this means incapacitated


# =============================================================================
# HELPER: check_condition_incapacitation
# This is the function we expect session.py to implement
# =============================================================================

def _check_condition_incapacitation(agent_id: str, mechanics, resolution_state: ResolutionState) -> bool:
    """
    Check if an agent has incapacitating conditions and mark them in resolution_state.

    This mirrors the logic that should be added to session.py's resolution phase.
    Returns True if the agent was marked incapacitated (for test assertions).
    """
    # Import the actual function from session.py
    from scripts.aeonisk.multiagent.session import _check_condition_incapacitation as impl
    return impl(agent_id, mechanics, resolution_state)


# =============================================================================
# TEST 1: Agent with severe condition (penalty >= -6) is marked incapacitated
# =============================================================================

class TestConditionBasedIncapacitation:
    """Test that conditions with abs(penalty) >= 6 trigger auto-skip."""

    def test_stunned_condition_marks_incapacitated(self):
        """A Stunned condition with penalty -6 should mark the agent incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Stunned",
                type="stun",
                penalty=-6,
                description="Knocked senseless by shock baton",
                duration=2,
                affects=["all"],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)

    def test_severe_wound_marks_incapacitated(self):
        """A wound condition with penalty -8 (> threshold) should mark incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Critical Wound",
                type="wound",
                penalty=-8,
                description="Severe bleeding, barely conscious",
                duration=-1,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_02"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)

    def test_exactly_threshold_marks_incapacitated(self):
        """Penalty of exactly -6 (threshold boundary) should mark incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Heavy Stun",
                type="stun",
                penalty=-6,
                description="Dazed and unable to act",
                duration=1,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_03"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)


# =============================================================================
# TEST 2: Agent with mild condition (abs(penalty) < 6) is NOT marked
# =============================================================================

class TestMildConditionsNoSkip:
    """Test that conditions below the threshold do NOT trigger skip."""

    def test_minor_penalty_not_incapacitated(self):
        """A condition with penalty -3 should NOT mark the agent incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Shaken",
                type="mental_strain",
                penalty=-3,
                description="Rattled but functional",
                duration=2,
                affects=["Willpower"],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)

    def test_penalty_minus_five_not_incapacitated(self):
        """A condition with penalty -5 (just below threshold) should NOT mark incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Moderate Wound",
                type="wound",
                penalty=-5,
                description="Painful but manageable",
                duration=-1,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)

    def test_zero_penalty_not_incapacitated(self):
        """A condition with penalty 0 should NOT mark the agent incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Barrier",
                type="barrier",
                penalty=0,
                description="Energy barrier active",
                duration=3,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)

    def test_no_conditions_not_incapacitated(self):
        """Agent with no conditions at all should NOT be marked incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = []

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)


# =============================================================================
# TEST 3: Multiple conditions — one incapacitating triggers skip
# =============================================================================

class TestMultipleConditions:
    """Test behavior with multiple conditions on the same agent."""

    def test_one_incapacitating_among_mild_triggers_skip(self):
        """If any condition has abs(penalty) >= 6, agent should be incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Shaken",
                type="mental_strain",
                penalty=-2,
                description="Slightly rattled",
                duration=2,
                affects=["Willpower"],
            ),
            Condition(
                name="Stunned",
                type="stun",
                penalty=-7,
                description="Heavily stunned",
                duration=1,
                affects=[],
            ),
            Condition(
                name="Bruised",
                type="wound",
                penalty=-1,
                description="Minor bruise",
                duration=3,
                affects=[],
            ),
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)

    def test_all_mild_conditions_no_skip(self):
        """If all conditions are below threshold, agent should NOT be incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Shaken",
                type="mental_strain",
                penalty=-2,
                description="Slightly rattled",
                duration=2,
                affects=["Willpower"],
            ),
            Condition(
                name="Bruised",
                type="wound",
                penalty=-3,
                description="Minor bruise",
                duration=3,
                affects=[],
            ),
            Condition(
                name="Distracted",
                type="mental_strain",
                penalty=-1,
                description="Can't focus",
                duration=1,
                affects=["Perception"],
            ),
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)


# =============================================================================
# TEST 4: Condition check is additive — doesn't duplicate existing skip
# =============================================================================

class TestAdditiveToExistingSkip:
    """Test that condition-based skip is additive to existing ResolutionState checks."""

    def test_already_incapacitated_not_re_marked(self):
        """If already in resolution_state.incapacitated, condition check should be a no-op."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Stunned",
                type="stun",
                penalty=-6,
                description="Stunned",
                duration=1,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"
        # Already marked by stun KO path
        resolution_state.mark_incapacitated(agent_id)

        # Should still return True (agent is incapacitating), but not crash
        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)

    def test_defeated_agent_not_affected(self):
        """Condition check on a defeated agent should still work (the defeated check happens separately)."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Stunned",
                type="stun",
                penalty=-6,
                description="Stunned",
                duration=1,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"
        resolution_state.mark_defeated(agent_id)

        # Condition check should still mark incapacitated (both defeated and incapacitated)
        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)
        # defeated check is separate
        assert resolution_state.is_defeated(agent_id)


# =============================================================================
# TEST 5: No mechanics engine — graceful fallback
# =============================================================================

class TestGracefulFallback:
    """Test that condition check handles edge cases gracefully."""

    def test_none_mechanics_returns_false(self):
        """If mechanics is None, should return False without error."""
        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, None, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)

    def test_mechanics_without_conditions_method(self):
        """If mechanics has no get_conditions method, should return False."""
        mechanics = MagicMock(spec=[])  # Empty spec — no methods
        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)


# =============================================================================
# TEST 6: Enemy agents also benefit from condition-based skip
# =============================================================================

class TestEnemyConditionSkip:
    """Condition-based incapacitation should work for any agent_id, including enemies."""

    def test_enemy_with_severe_condition(self):
        """An enemy with abs(penalty) >= 6 should be marked incapacitated."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Stunned",
                type="stun",
                penalty=-6,
                description="Stunned by flashbang",
                duration=2,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "enemy_grunt_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is True
        assert resolution_state.is_incapacitated(agent_id)


# =============================================================================
# TEST 7: Positive penalty values don't trigger incapacitation
# =============================================================================

class TestPositivePenaltyNoSkip:
    """Positive penalty values (buffs) should never trigger incapacitation."""

    def test_positive_penalty_not_incapacitated(self):
        """A condition with positive penalty (buff) should NOT trigger skip."""
        mechanics = MagicMock()
        mechanics.get_conditions.return_value = [
            Condition(
                name="Inspired",
                type="buff",
                penalty=6,  # Positive — this is a bonus, not a penalty
                description="Inspired by leadership",
                duration=3,
                affects=[],
            )
        ]

        resolution_state = ResolutionState()
        agent_id = "player_01"

        result = _check_condition_incapacitation(agent_id, mechanics, resolution_state)

        assert result is False
        assert not resolution_state.is_incapacitated(agent_id)
