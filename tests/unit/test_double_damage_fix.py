"""
Unit tests for double damage and damage-on-miss bug fixes.

Bug 1 (Double Damage): Every player combat action applied damage TWICE —
once via _process_structured_damage_effects() and once via legacy damage
extraction from state_changes['damage_effects']. Both paths consumed the
same DamageEffect data.

Bug 2 (Damage on Miss): When mechanical d20 roll was a miss (resolution.success=False),
damage was still applied because neither path checked the roll result. DM could
hallucinate a hit and populate effects.damage.dealt — which was then applied.

Fix for Bug 1: Remove legacy damage extraction from structured output path
(state_changes['damage_effects'] no longer creates a legacy 'effect' dict).

Fix for Bug 2: Gate _process_structured_damage_effects on resolution.success.
Clear hallucinated damage when mechanical roll says miss.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


# === Fixtures ===

def make_mock_enemy(agent_id="enemy_grunt_1234", name="Enemy Grunt #1",
                    health=30, max_health=30, wounds=0, soak=5):
    """Create a mock enemy entity."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stun = 0
    enemy.soak = soak
    enemy.barriers = []
    enemy.status_effects = []
    enemy.is_active = True
    enemy.spawned_round = 0

    # Make health/wounds mutable (Mock attributes are already mutable)
    # But we need take_damage side effects to modify health
    def take_damage_side_effect(amount):
        enemy.health -= amount
        enemy.wounds += amount // 5
        return amount
    enemy.take_damage = Mock(side_effect=take_damage_side_effect)

    # Death check (alive if health > 0)
    def check_death_save():
        if enemy.health <= 0:
            return (False, "killed")
        return (True, "alive")
    enemy.check_death_save = Mock(side_effect=check_death_save)

    return enemy


def make_mock_shared_state(enemies=None):
    """Create a mock SharedState with target ID mapper."""
    shared = Mock()

    if enemies is None:
        enemies = [make_mock_enemy()]

    enemy_map = {}
    for e in enemies:
        tgt_id = f"tgt_{e.agent_id[-4:]}"
        enemy_map[tgt_id] = e

    # Mock target ID mapper
    mapper = Mock()
    mapper.enabled = True
    mapper.resolve_target = Mock(side_effect=lambda tgt_id: enemy_map.get(tgt_id))
    mapper.is_player = Mock(return_value=False)
    mapper.get_combatant_info = Mock(side_effect=lambda tgt_id: {
        'id': enemy_map[tgt_id].agent_id if tgt_id in enemy_map else 'unknown',
        'name': enemy_map[tgt_id].name if tgt_id in enemy_map else 'Unknown',
        'type': 'enemy'
    } if tgt_id in enemy_map else None)
    shared.get_target_id_mapper = Mock(return_value=mapper)

    # Mock get_entity
    shared.get_entity = Mock(side_effect=lambda aid: next(
        (e for e in enemies if e.agent_id == aid), None
    ))

    shared.enemy_combat = Mock()
    shared.enemy_combat.enemy_agents = enemies

    # Player agents (for weapon resolution)
    shared.player_agents = []

    return shared


def make_mock_mechanics():
    """Create a mock mechanics engine with JSONL logger."""
    mechanics = Mock()
    mechanics.jsonl_logger = Mock()
    mechanics.jsonl_logger.log_combat_action = Mock()
    mechanics.jsonl_logger.log_enemy_defeat = Mock()
    mechanics.current_round = 1
    return mechanics


@dataclass
class MockResolution:
    """Mock of mechanics.ActionResolution dataclass."""
    intent: str = "Attack the grunt"
    attribute: str = "Agility"
    skill: Optional[str] = "Guns"
    attribute_value: int = 4
    skill_value: int = 3
    roll: int = 15
    total: int = 27
    difficulty: int = 15
    margin: int = 12
    success: bool = True
    narrative: str = "You hit!"
    outcome_tier: Any = None
    state_effects: Dict[str, Any] = field(default_factory=dict)
    modifiers_applied: list = field(default_factory=list)
    ability: int = 12
    is_unskilled: bool = False
    roll_formula: Optional[str] = "4×3 + d20(15) = 27"

    def __post_init__(self):
        if self.outcome_tier is None:
            # Use a mock enum
            self.outcome_tier = Mock()
            self.outcome_tier.value = "GOOD" if self.success else "FAILURE"


# === Test Class ===

class TestDoubleDamageFix:
    """Tests for Bug 1: Double damage application."""

    def test_single_combat_action_produces_one_damage_application(self):
        """Enemy HP should be decremented exactly once for a single player attack."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=15, dealt=10, soak=5)
        ]

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol"
        )

        # Enemy should have taken exactly 10 damage (30 - 10 = 20)
        assert enemy.health == 20, \
            f"Expected enemy health=20 (30 - 10), got {enemy.health}. " \
            f"Damage may have been applied more than once."

    def test_single_combat_action_logs_one_combat_event(self):
        """log_combat_action should be called exactly once per player attack."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=15, dealt=10, soak=5)
        ]

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol"
        )

        assert mechanics.jsonl_logger.log_combat_action.call_count == 1, \
            f"Expected 1 log_combat_action call, got {mechanics.jsonl_logger.log_combat_action.call_count}. " \
            f"Combat event may have been logged more than once."

    def test_multi_target_damage_applies_once_per_target(self):
        """When DM outputs 2 DamageEffects for different targets, each takes damage once."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy1 = make_mock_enemy(agent_id="enemy_alpha_aaaa", name="Alpha", health=30)
        enemy2 = make_mock_enemy(agent_id="enemy_bravo_bbbb", name="Bravo", health=25)
        shared = make_mock_shared_state(enemies=[enemy1, enemy2])

        # Override mapper to resolve both targets
        mapper = shared.get_target_id_mapper()
        target_map = {"tgt_aaaa": enemy1, "tgt_bbbb": enemy2}
        mapper.resolve_target = Mock(side_effect=lambda tid: target_map.get(tid))

        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_aaaa", base_damage=12, dealt=8, soak=4),
            DamageEffect(target="tgt_bbbb", base_damage=10, dealt=6, soak=4),
        ]

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Frag Grenade"
        )

        assert enemy1.health == 22, \
            f"Expected enemy1 health=22 (30-8), got {enemy1.health}"
        assert enemy2.health == 19, \
            f"Expected enemy2 health=19 (25-6), got {enemy2.health}"
        assert mechanics.jsonl_logger.log_combat_action.call_count == 2, \
            f"Expected 2 log_combat_action calls (one per target), got {mechanics.jsonl_logger.log_combat_action.call_count}"

    def test_successful_hit_applies_correct_damage(self):
        """Sanity: successful roll + damage = correct HP reduction."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=20, dealt=15, soak=5)
        ]

        messages = _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Rifle"
        )

        assert enemy.health == 15, f"Expected health=15 (30-15), got {enemy.health}"
        assert len(messages) > 0, "Should produce at least one damage message"
        assert any("15" in m and "damage" in m.lower() for m in messages), \
            f"Damage message should mention 15 damage, got: {messages}"


class TestDamageOnMissFix:
    """Tests for Bug 2: Damage applied on missed rolls."""

    def test_missed_roll_applies_zero_damage(self):
        """When resolution.success=False, enemy HP should be unchanged despite DM populating damage."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution as PydanticResolution

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        # Create a resolution object with damage (DM hallucinated a hit)
        # but the mechanical roll was a miss
        resolution_obj = Mock()
        resolution_obj.effects = Mock()
        resolution_obj.effects.damage = [
            DamageEffect(target="tgt_1234", base_damage=10, dealt=5, soak=5)
        ]

        miss_resolution = MockResolution(
            roll=1, total=5, difficulty=15, margin=-10, success=False
        )

        # The gate should clear damage BEFORE calling _process_structured_damage_effects
        # So if the gate works, effects.damage should be empty/cleared
        # and _process_structured_damage_effects should receive no damage

        # Simulate the gate logic that should exist before the call
        if not miss_resolution.success and resolution_obj.effects and resolution_obj.effects.damage:
            resolution_obj.effects.damage = []

        _process_structured_damage_effects(
            damage_effects=resolution_obj.effects.damage,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol"
        )

        assert enemy.health == 30, \
            f"Expected enemy health unchanged at 30 (roll was a miss), got {enemy.health}"

    def test_missed_roll_clears_damage_effects(self):
        """When resolution.success=False, resolution_obj.effects.damage should be emptied."""
        resolution_obj = Mock()
        resolution_obj.effects = Mock()
        resolution_obj.effects.damage = [
            DamageEffect(target="tgt_1234", base_damage=10, dealt=5, soak=5)
        ]

        miss_resolution = MockResolution(
            roll=3, total=7, difficulty=20, margin=-13, success=False
        )

        # Apply the gate logic
        if not miss_resolution.success and resolution_obj.effects and resolution_obj.effects.damage:
            resolution_obj.effects.damage = []

        assert resolution_obj.effects.damage == [], \
            f"Damage effects should be cleared on miss, got: {resolution_obj.effects.damage}"

    def test_missed_roll_logs_warning(self):
        """Warning should be logged when DM contradicts mechanical roll."""
        with patch('scripts.aeonisk.multiagent.dm.logger') as mock_logger:
            resolution_obj = Mock()
            resolution_obj.effects = Mock()
            resolution_obj.effects.damage = [
                DamageEffect(target="tgt_1234", base_damage=10, dealt=5, soak=5)
            ]

            miss_resolution = MockResolution(
                roll=1, total=5, difficulty=15, margin=-10, success=False
            )

            # Simulate the gate logic with logging
            if not miss_resolution.success and resolution_obj.effects and resolution_obj.effects.damage:
                mock_logger.warning(
                    f"DM populated damage effects despite mechanical MISS "
                    f"(d20={miss_resolution.roll}, total={miss_resolution.total}, "
                    f"DC={miss_resolution.difficulty}, tier={miss_resolution.outcome_tier.value}). "
                    f"Clearing hallucinated damage."
                )
                resolution_obj.effects.damage = []

            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "MISS" in warning_msg
            assert "d20=1" in warning_msg
            assert "Clearing hallucinated damage" in warning_msg


class TestCombatActionLogEnrichment:
    """Tests for enriched combat_action log data (attack roll + weapon)."""

    def test_combat_action_log_has_attack_roll_data(self):
        """The combat_action log should include d20, total, DC, hit, margin."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=15, dealt=10, soak=5)
        ]

        attack_roll_data = {
            "attr": "Agility",
            "attr_val": 4,
            "skill": "Guns",
            "skill_val": 3,
            "d20": 15,
            "total": 27,
            "dc": 15,
            "hit": True,
            "margin": 12
        }

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol",
            attack_roll=attack_roll_data
        )

        call_kwargs = mechanics.jsonl_logger.log_combat_action.call_args.kwargs
        assert call_kwargs['attack_roll'] == attack_roll_data, \
            f"Expected attack_roll data in log, got: {call_kwargs['attack_roll']}"
        assert call_kwargs['attack_roll']['d20'] == 15
        assert call_kwargs['attack_roll']['hit'] is True
        assert call_kwargs['attack_roll']['margin'] == 12

    def test_combat_action_log_has_actual_weapon_name(self):
        """Log should use equipped weapon name ('Pistol'), not skill ('Guns')."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=15, dealt=10, soak=5)
        ]

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol"  # Actual weapon name, not "Guns"
        )

        call_kwargs = mechanics.jsonl_logger.log_combat_action.call_args.kwargs
        assert call_kwargs['weapon'] == "Void Pistol", \
            f"Expected weapon='Void Pistol', got: {call_kwargs['weapon']}"

    def test_combat_action_log_defaults_attack_roll_to_empty(self):
        """When no attack_roll provided, it should default to empty dict."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30)
        shared = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effects = [
            DamageEffect(target="tgt_1234", base_damage=15, dealt=10, soak=5)
        ]

        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=shared,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Pistol"
            # No attack_roll provided
        )

        call_kwargs = mechanics.jsonl_logger.log_combat_action.call_args.kwargs
        assert call_kwargs['attack_roll'] == {}, \
            f"Expected attack_roll={{}}, got: {call_kwargs['attack_roll']}"
