"""
Unit tests for _mark_defeated_from_resolution in session.py.

Tests verify that defeated enemies (is_active=False) are properly
marked in resolution_state so their actions get invalidated with
proper JSONL events and narration.
"""

import pytest
from unittest.mock import MagicMock
from scripts.aeonisk.multiagent.session import _mark_defeated_from_resolution
from scripts.aeonisk.multiagent.tactical_resolution import (
    ResolutionState,
    ActionValidator,
)


def _make_enemy(agent_id: str, name: str, is_active: bool = True):
    """Create a minimal mock enemy agent."""
    enemy = MagicMock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.is_active = is_active
    return enemy


def _make_enemy_combat(enemies):
    """Create a minimal mock EnemyCombatManager."""
    ec = MagicMock()
    ec.enemy_agents = enemies
    return ec


class TestMarkDefeatedFromResolution:
    """Tests for _mark_defeated_from_resolution."""

    def test_inactive_enemy_marked_defeated(self):
        """Enemy with is_active=False gets marked defeated in resolution_state."""
        enemy = _make_enemy("enemy_grunt_1", "Grunt Alpha", is_active=False)
        ec = _make_enemy_combat([enemy])
        state = ResolutionState()

        _mark_defeated_from_resolution(ec, state)

        assert state.is_defeated("enemy_grunt_1")

    def test_active_enemy_not_marked(self):
        """Active enemy is NOT marked defeated."""
        enemy = _make_enemy("enemy_grunt_1", "Grunt Alpha", is_active=True)
        ec = _make_enemy_combat([enemy])
        state = ResolutionState()

        _mark_defeated_from_resolution(ec, state)

        assert not state.is_defeated("enemy_grunt_1")

    def test_idempotent_already_defeated(self):
        """Already-defeated enemy doesn't crash when called again."""
        enemy = _make_enemy("enemy_grunt_1", "Grunt Alpha", is_active=False)
        ec = _make_enemy_combat([enemy])
        state = ResolutionState()
        state.mark_defeated("enemy_grunt_1")  # pre-mark

        _mark_defeated_from_resolution(ec, state)  # should not crash

        assert state.is_defeated("enemy_grunt_1")

    def test_mixed_states(self):
        """Only newly-inactive enemies get marked; active ones are untouched."""
        active = _make_enemy("enemy_grunt_1", "Active Grunt", is_active=True)
        defeated = _make_enemy("enemy_grunt_2", "Defeated Grunt", is_active=False)
        already = _make_enemy("enemy_grunt_3", "Already Marked", is_active=False)
        ec = _make_enemy_combat([active, defeated, already])

        state = ResolutionState()
        state.mark_defeated("enemy_grunt_3")  # pre-mark

        _mark_defeated_from_resolution(ec, state)

        assert not state.is_defeated("enemy_grunt_1")
        assert state.is_defeated("enemy_grunt_2")
        assert state.is_defeated("enemy_grunt_3")

    def test_none_enemy_combat(self):
        """enemy_combat=None doesn't crash."""
        state = ResolutionState()

        _mark_defeated_from_resolution(None, state)  # should not crash

        assert len(state.defeated) == 0

    def test_no_enemy_agents_attr(self):
        """Object without enemy_agents attribute doesn't crash."""
        ec = MagicMock(spec=[])  # no attributes
        state = ResolutionState()

        _mark_defeated_from_resolution(ec, state)  # should not crash

        assert len(state.defeated) == 0

    def test_defeated_enemy_action_invalidated(self):
        """Integration: defeated enemy's action is invalidated by ActionValidator."""
        enemy = _make_enemy("enemy_grunt_1", "Grunt Alpha", is_active=False)
        ec = _make_enemy_combat([enemy])
        state = ResolutionState()

        _mark_defeated_from_resolution(ec, state)

        # ActionValidator should reject attacks from defeated enemies
        can_attack, reason = ActionValidator.can_attack(
            "enemy_grunt_1", "player_1", state
        )
        assert not can_attack
        assert reason == "attacker_defeated"

    def test_empty_enemy_list(self):
        """Empty enemy_agents list doesn't crash."""
        ec = _make_enemy_combat([])
        state = ResolutionState()

        _mark_defeated_from_resolution(ec, state)

        assert len(state.defeated) == 0
