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
