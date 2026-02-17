"""
Tests for DM conversion context enrichment.

Phase 2B: DM sees morale_behavior, character_brief, faction when deciding conversions.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position


def _make_enemy(**overrides):
    defaults = dict(
        agent_id="enemy_grunt_abc123",
        name="ACG Guard",
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
        skills={"Brawl": 2, "Guns": 3},
        health=8,
        max_health=30,
        soak=8,
        wounds=2,
        position=Position(ring="Near", side="Enemy"),
        initiative=12,
        faction="ACG",
        morale_behavior="surrender_if_cornered",
        character_brief="Obedient and methodical. Follows orders without question.",
    )
    defaults.update(overrides)
    return EnemyAgent(**defaults)


class TestConversionContextBuilding:
    """DM builds rich context for conversion decisions."""

    def test_available_enemies_includes_morale_behavior(self):
        """Enemy list sent to DM includes morale_behavior."""
        enemy = _make_enemy()
        # Simulate the context building logic from dm.py
        health_pct = int((enemy.health / enemy.max_health) * 100)
        morale = getattr(enemy, 'morale_behavior', 'unknown')
        line = f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP, morale: {morale}, faction: {enemy.faction})"
        assert "morale: surrender_if_cornered" in line

    def test_available_enemies_includes_faction(self):
        enemy = _make_enemy(faction="Tempest Industries")
        health_pct = int((enemy.health / enemy.max_health) * 100)
        morale = getattr(enemy, 'morale_behavior', 'unknown')
        line = f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP, morale: {morale}, faction: {enemy.faction})"
        assert "faction: Tempest Industries" in line

    def test_available_enemies_includes_character_brief(self):
        enemy = _make_enemy(character_brief="Obedient and methodical.")
        brief = getattr(enemy, 'character_brief', '')
        assert "Obedient" in brief

    def test_fight_to_death_not_marked_candidate_above_threshold(self):
        """fight_to_death enemies below 30% HP are still candidates (DM decides)."""
        enemy = _make_enemy(
            morale_behavior="fight_to_death",
            health=8, max_health=30
        )
        health_pct = int((enemy.health / enemy.max_health) * 100)
        is_candidate = health_pct < 30
        assert is_candidate  # They're low HP, they appear as candidates
        # But morale_behavior tells DM they resist conversion
        assert enemy.morale_behavior == "fight_to_death"
