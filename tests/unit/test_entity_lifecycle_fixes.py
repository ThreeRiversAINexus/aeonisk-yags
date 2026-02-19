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

class TestDuplicateDefeatPrevention:

    def test_already_defeated_enemy_no_second_defeat_log(self):
        """An enemy killed by PC #1 should not produce a second defeat event when PC #2 also hits it."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects
        from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect

        # Create a mock enemy at 5 HP (will die from first hit)
        enemy = MagicMock()
        enemy.agent_id = "enemy_drone_01"
        enemy.name = "Drone #1"
        enemy.health = 5
        enemy.max_health = 20
        enemy.wounds = 0
        enemy.stuns = 0
        enemy.soak = 0
        enemy.is_active = True
        enemy.spawned_round = 1
        enemy.despawned_round = None
        # Enemies don't have check_death_save — delete auto-created MagicMock attr
        del enemy.check_death_save

        # Make health decrease when damage applied (matches mechanics.apply_wound_damage return format)
        def apply_wound(entity, dmg):
            entity.health = max(0, entity.health - dmg)
            wounds = dmg // 5
            entity.wounds += wounds
            return {
                "wounds_dealt": wounds,
                "old_wounds": entity.wounds - wounds,
                "new_wounds": entity.wounds,
                "hp_lost": dmg,
                "effect": {"death_check": False, "penalty": 0, "description": ""},
                "death_check_needed": False
            }

        # Set up shared_state with target mapper
        shared_state = MagicMock()
        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = enemy
        mapper.is_player.return_value = False
        mapper.get_combatant_info.return_value = {"name": "Drone #1", "faction": "Unknown"}
        shared_state.get_target_id_mapper.return_value = mapper

        # Set up mechanics with jsonl_logger
        mechanics = MagicMock()
        mechanics.current_round = 3
        logged_defeats = []
        def capture_defeat(**kwargs):
            logged_defeats.append(kwargs)
        mechanics.jsonl_logger.log_enemy_defeat = capture_defeat
        mechanics.jsonl_logger.log_combat_action = MagicMock()

        # Two damage effects targeting the same enemy (two PCs both hit it)
        damage_effects = [
            DamageEffect(target="tgt_abc1", base_damage=10, dealt=10),
            DamageEffect(target="tgt_abc1", base_damage=8, dealt=8),
        ]

        with patch("scripts.aeonisk.multiagent.mechanics.apply_wound_damage", side_effect=apply_wound):
            _process_structured_damage_effects(
                damage_effects=damage_effects,
                shared_state=shared_state,
                current_round=3,
                mechanics=mechanics,
                attacker_id="player_01",
                attacker_name="Test Player",
            )

        # Should only have ONE defeat event, not two
        assert len(logged_defeats) == 1, f"Expected 1 defeat event, got {len(logged_defeats)}: {logged_defeats}"
        assert logged_defeats[0]["enemy_id"] == "enemy_drone_01"


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
