"""
Tests for entity lifecycle and clock persistence fixes.

Covers:
1. Defeated enemy pruning at round boundaries
2. Clock persistence through story advancement (clear_specific_clocks)
3. Logging deduplication (no duplicate action_resolution for enemy attacks)
"""

import pytest
import warnings
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from scripts.aeonisk.multiagent.schemas.story_events import StoryAdvancement, NewClock


# ============================================================================
# Helpers
# ============================================================================

def _make_enemy(agent_id: str, is_active: bool = True,
                spawned_round: int = 0, despawned_round: Optional[int] = None,
                health: int = 20):
    """Create a minimal mock enemy for pruning tests."""
    enemy = MagicMock()
    enemy.agent_id = agent_id
    enemy.name = f"Enemy {agent_id}"
    enemy.is_active = is_active
    enemy.spawned_round = spawned_round
    enemy.despawned_round = despawned_round
    enemy.health = health
    return enemy


def _make_combat_manager(enemies=None, current_round=0):
    """Create an EnemyCombatManager with mocked shared_state."""
    from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager
    mgr = EnemyCombatManager.__new__(EnemyCombatManager)
    mgr.enemy_agents = enemies or []
    mgr.current_round = current_round
    mgr.shared_state = MagicMock()
    # Default: target mapper with empty maps
    mapper = MagicMock()
    mapper.reverse_map = {}
    mapper.target_id_map = {}
    mgr.shared_state.get_target_id_mapper.return_value = mapper
    return mgr


def _make_clock(name, current=3, maximum=8):
    """Create a mock scene clock."""
    clock = MagicMock()
    clock.current = current
    clock.maximum = maximum
    clock.filled = current >= maximum
    clock.description = f"Clock: {name}"
    return clock


# ============================================================================
# Enemy Pruning Tests
# ============================================================================

class TestPruneDefeatedEnemies:

    def test_prune_removes_enemies_past_grace_period(self):
        """Enemy defeated round 2, pruned at round 5 (>2 round grace)."""
        enemy = _make_enemy("enemy_01", is_active=False, despawned_round=2)
        mgr = _make_combat_manager([enemy], current_round=5)

        pruned = mgr.prune_defeated_enemies(grace_rounds=2)

        assert pruned == 1
        assert len(mgr.enemy_agents) == 0

    def test_prune_keeps_recently_defeated(self):
        """Enemy defeated round 3, kept at round 4 (within 2-round grace)."""
        enemy = _make_enemy("enemy_01", is_active=False, despawned_round=3)
        mgr = _make_combat_manager([enemy], current_round=4)

        pruned = mgr.prune_defeated_enemies(grace_rounds=2)

        assert pruned == 0
        assert len(mgr.enemy_agents) == 1

    def test_prune_never_removes_active(self):
        """Active enemies survive pruning at any round."""
        enemy = _make_enemy("enemy_01", is_active=True)
        mgr = _make_combat_manager([enemy], current_round=100)

        pruned = mgr.prune_defeated_enemies()

        assert pruned == 0
        assert len(mgr.enemy_agents) == 1

    def test_prune_handles_none_despawned_round(self):
        """Enemies with despawned_round=None kept (safety case)."""
        enemy = _make_enemy("enemy_01", is_active=False, despawned_round=None)
        mgr = _make_combat_manager([enemy], current_round=100)

        pruned = mgr.prune_defeated_enemies()

        assert pruned == 0
        assert len(mgr.enemy_agents) == 1

    def test_prune_cleans_target_mapper(self):
        """Pruned enemy's target ID mapping is also removed."""
        enemy = _make_enemy("enemy_01", is_active=False, despawned_round=1)
        mgr = _make_combat_manager([enemy], current_round=5)

        # Set up target mapper with entry for this enemy
        mapper = mgr.shared_state.get_target_id_mapper()
        mapper.reverse_map = {"enemy_01": "tgt_abc1"}
        mapper.target_id_map = {"tgt_abc1": enemy}

        pruned = mgr.prune_defeated_enemies()

        assert pruned == 1
        assert "enemy_01" not in mapper.reverse_map
        assert "tgt_abc1" not in mapper.target_id_map

    def test_prune_mixed_list(self):
        """Correct handling of active + recent + stale in same list."""
        active = _make_enemy("active_01", is_active=True)
        recent = _make_enemy("recent_01", is_active=False, despawned_round=4)
        stale = _make_enemy("stale_01", is_active=False, despawned_round=1)

        mgr = _make_combat_manager([active, recent, stale], current_round=5)

        pruned = mgr.prune_defeated_enemies(grace_rounds=2)

        assert pruned == 1
        assert len(mgr.enemy_agents) == 2
        remaining_ids = [e.agent_id for e in mgr.enemy_agents]
        assert "active_01" in remaining_ids
        assert "recent_01" in remaining_ids
        assert "stale_01" not in remaining_ids


# ============================================================================
# Clock Persistence Tests
# ============================================================================

class TestClockPersistence:

    def test_clear_specific_clocks_defaults_empty(self):
        """StoryAdvancement with default clear_specific_clocks=[] keeps all clocks."""
        adv = StoryAdvancement(
            should_advance=True,
            location="New Location Area",
            situation="A" * 50,  # Meet min_length
        )
        assert adv.clear_specific_clocks == []

    def test_clear_specific_clocks_accepts_names(self):
        """Can specify clock names to clear."""
        adv = StoryAdvancement(
            should_advance=True,
            location="New Location Area",
            situation="A" * 50,
            clear_specific_clocks=["Facility Lockdown", "Breach Containment"]
        )
        assert len(adv.clear_specific_clocks) == 2
        assert "Facility Lockdown" in adv.clear_specific_clocks

    def test_new_clocks_coexist_with_clear_specific(self):
        """new_clocks and clear_specific_clocks work together."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Safe House District",
            situation="B" * 50,
            clear_specific_clocks=["Old Threat"],
            new_clocks=[NewClock(
                name="New Pursuit",
                max_ticks=6,
                description="Faction is tracking players",
                advance_meaning="Pursuit intensifies",
                regress_meaning="Players lose tail"
            )]
        )
        assert len(adv.clear_specific_clocks) == 1
        assert len(adv.new_clocks) == 1


# ============================================================================
# Logging Deduplication Tests
# ============================================================================

class TestLoggingDeduplication:

    def test_log_enemy_action_emits_deprecation_warning(self):
        """Calling log_enemy_action() directly triggers DeprecationWarning."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger_instance = JSONLLogger.__new__(JSONLLogger)
        logger_instance.session_id = "test_session"
        logger_instance.output_file = None
        # Mock _write_event to prevent actual file writes
        logger_instance._write_event = MagicMock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            logger_instance.log_enemy_action(
                round_num=1,
                enemy_id="enemy_01",
                enemy_name="Test Enemy",
                action_type="attack",
                result="hit",
                narration="Test narration"
            )

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "log_combat_action" in str(deprecation_warnings[0].message)
