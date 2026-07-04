"""
Tests for Wait/Dialogue/Surrender combat execution.

Phase 1E: Wire new actions into enemy_combat.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position


def _make_enemy(**overrides):
    """Create a minimal EnemyAgent for testing."""
    defaults = dict(
        agent_id="enemy_test_01",
        name="Test Guard",
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
        skills={"Brawl": 2, "Guns": 3},
        health=30,
        max_health=30,
        soak=8,
        wounds=0,
        position=Position(ring="Near", side="Enemy"),
        initiative=12,
        morale_behavior="flee_when_broken",
        character_brief="Test enemy.",
    )
    defaults.update(overrides)
    return EnemyAgent(**defaults)


class TestPanickedMoraleBehavior:
    """Panicked override should be morale-behavior-aware."""

    def test_panicked_surrender_morale_declares_surrender(self):
        """surrender_if_cornered enemies surrender when panicked instead of fleeing."""
        enemy = _make_enemy(
            morale_behavior="surrender_if_cornered",
            is_panicked=True,
            panic_trigger="hp_below_25"
        )
        # Import the function that determines panicked behavior
        from scripts.aeonisk.multiagent.enemy_combat import _get_panicked_action
        action = _get_panicked_action(enemy)
        assert action == "Surrender"

    def test_panicked_flee_morale_declares_flee(self):
        """flee_when_broken enemies flee when panicked (existing behavior)."""
        enemy = _make_enemy(
            morale_behavior="flee_when_broken",
            is_panicked=True,
            panic_trigger="hp_below_25"
        )
        from scripts.aeonisk.multiagent.enemy_combat import _get_panicked_action
        action = _get_panicked_action(enemy)
        assert action == "FLEE"

    def test_panicked_fight_to_death_continues(self):
        """fight_to_death enemies never panic-override (morale check returns 'continue')."""
        enemy = _make_enemy(
            morale_behavior="fight_to_death",
            is_panicked=True,
            panic_trigger="hp_below_25"
        )
        from scripts.aeonisk.multiagent.enemy_combat import _get_panicked_action
        action = _get_panicked_action(enemy)
        assert action == "FLEE"  # fight_to_death still uses default FLEE in panic override
        # (fight_to_death is handled at morale check level - they never GET panicked)


class TestExecuteSurrender:
    """Regression: 2026-07-04 corpus wave 1, run 11 crashed mid-combat.

    _execute_surrender called resolution_state.add_shared_intel(), a method
    that has never existed on ResolutionState (intel lives on the manager's
    SharedIntel pool), and marked the enemy defeated instead of surrendered
    (surrendered enemies stay present for NPC conversion; defeated are
    removed).
    """

    def _run_surrender(self):
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        manager = EnemyCombatManager()
        manager.current_round = 3
        enemy = _make_enemy()
        declaration = MagicMock()
        declaration.reasoning = "Outnumbered and wounded, drops weapon"
        state = ResolutionState()

        result = manager._execute_surrender(enemy, declaration, state)
        return manager, enemy, state, result

    def test_surrender_does_not_crash_and_reports_success(self):
        _, enemy, _, result = self._run_surrender()
        assert result['surrender'] is True
        assert result['result'] == 'success'
        assert enemy.is_prisoner is True
        assert enemy.is_active is False

    def test_surrendered_not_defeated_in_resolution_state(self):
        _, enemy, state, _ = self._run_surrender()
        assert state.is_surrendered(enemy.agent_id)
        assert enemy.agent_id not in state.defeated

    def test_surrender_recorded_in_shared_intel_pool(self):
        manager, enemy, _, _ = self._run_surrender()
        assert any(
            enemy.name in item.intel and "surrender" in item.intel.lower()
            for item in manager.shared_intel.intel_pool
        )
