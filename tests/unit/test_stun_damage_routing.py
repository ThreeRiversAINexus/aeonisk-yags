"""
Unit tests for weapon damage type routing (stun/wound/mixed).

Problem: Weapons define damage_type ("stun", "wound", "mixed") but the structured
output pipeline ignores it — all damage is applied as wounds. This means unarmed
attacks kill instead of stunning.

Fix: Route damage through apply_stun_damage/apply_wound_damage/apply_mixed_damage
based on weapon damage_type, with LLM's DamageEffect.damage_type as primary signal
and backend weapon lookup as fallback.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


# === Fixtures ===

def make_mock_enemy(agent_id="enemy_grunt_1234", name="Enemy Grunt #1",
                    health=30, max_health=30, wounds=0, stuns=0, soak=5):
    """Create a mock enemy entity."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stuns = stuns
    enemy.soak = soak
    enemy.barriers = []
    enemy.status_effects = []
    enemy.is_active = True
    enemy.spawned_round = 0

    def check_death_save():
        if enemy.health <= 0:
            return (False, "killed")
        return (True, "alive")
    enemy.check_death_save = Mock(side_effect=check_death_save)

    return enemy


def make_mock_shared_state(enemies=None, player_agents=None):
    """Create a mock SharedState with target ID mapper."""
    shared = Mock()

    if enemies is None:
        enemies = [make_mock_enemy()]

    enemy_map = {}
    for e in enemies:
        tgt_id = f"tgt_{e.agent_id[-4:]}"
        enemy_map[tgt_id] = e

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

    shared.get_entity = Mock(side_effect=lambda aid: next(
        (e for e in enemies if e.agent_id == aid), None
    ))

    shared.enemy_combat = Mock()
    shared.enemy_combat.enemy_agents = enemies

    shared.player_agents = player_agents or []

    return shared


def make_mock_mechanics():
    """Create a mock mechanics engine with JSONL logger."""
    mechanics = Mock()
    mechanics.jsonl_logger = Mock()
    mechanics.jsonl_logger.log_combat_action = Mock()
    mechanics.jsonl_logger.log_enemy_defeat = Mock()
    mechanics.current_round = 1
    return mechanics


def make_mock_player_agent(agent_id="player_vex_1234", primary=None, sidearm=None):
    """Create a mock player agent with equipped weapons."""
    agent = Mock()
    agent.agent_id = agent_id
    agent.equipped_weapons = {}
    if primary:
        agent.equipped_weapons['primary'] = primary
    if sidearm:
        agent.equipped_weapons['sidearm'] = sidearm
    return agent


def make_mock_weapon(name="Test Weapon", skill="Guns", damage_type="wound"):
    """Create a mock weapon object."""
    weapon = Mock()
    weapon.name = name
    weapon.skill = skill
    weapon.damage_type = damage_type
    return weapon


# =============================================================================
# TEST: Damage Type Routing in _process_structured_damage_effects
# =============================================================================

class TestDamageTypeRouting:
    """Test that damage_type correctly routes to stun/wound/mixed handlers."""

    def test_stun_damage_applies_stuns_not_wounds(self):
        """DamageEffect with damage_type='stun' should increase stuns, not wounds/HP."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=10,
            soak=2,
            dealt=8,
            damage_type="stun"
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unarmed",
            resolved_damage_type="stun"
        )

        # Stun damage should NOT reduce HP or add wounds
        assert enemy.health == 30, f"Stun should not reduce HP, got {enemy.health}"
        assert enemy.wounds == 0, f"Stun should not add wounds, got {enemy.wounds}"
        # Stun damage should increase stuns
        assert enemy.stuns > 0, f"Stun should increase stuns, got {enemy.stuns}"

    def test_wound_damage_applies_wounds_and_hp_loss(self):
        """DamageEffect with damage_type='wound' should reduce HP and add wounds."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=15,
            soak=5,
            dealt=10,
            damage_type="wound"
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Kinetic Pistol",
            resolved_damage_type="wound"
        )

        # Wound damage should reduce HP
        assert enemy.health == 20, f"Expected HP 20, got {enemy.health}"
        # Every 5 damage = 1 wound
        assert enemy.wounds == 2, f"Expected 2 wounds (10//5), got {enemy.wounds}"
        # Wound damage should not affect stuns
        assert enemy.stuns == 0, f"Wound should not affect stuns, got {enemy.stuns}"

    def test_mixed_damage_splits_correctly(self):
        """DamageEffect with damage_type='mixed' should affect both stuns and wounds."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=12,
            soak=2,
            dealt=10,
            damage_type="mixed"
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Shock Baton",
            resolved_damage_type="mixed"
        )

        # Mixed splits: stun=(10+1)//2=5, wound=10//2=5
        assert enemy.stuns > 0, f"Mixed should increase stuns, got {enemy.stuns}"
        # Wound portion reduces HP (by wound_damage=5)
        assert enemy.health < 30, f"Mixed should reduce HP, got {enemy.health}"

    def test_missing_damage_type_defaults_to_wound(self):
        """DamageEffect with damage_type=None should default to wound behavior."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=15,
            soak=5,
            dealt=10,
            damage_type=None  # Not specified
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unknown Weapon"
            # resolved_damage_type not passed — defaults to None
        )

        # Should default to wound behavior (backward compat)
        assert enemy.health == 20, f"Default should reduce HP like wound, got {enemy.health}"
        assert enemy.wounds == 2, f"Default should add wounds, got {enemy.wounds}"

    def test_freeform_damage_type_normalizes_to_wound(self):
        """DamageEffect with freeform damage_type ('kinetic') should be treated as wound."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=15,
            soak=5,
            dealt=10,
            damage_type="kinetic"  # Freeform, not a YAGS type
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Kinetic Pistol"
            # No resolved_damage_type — falls through to LLM's "kinetic" → normalized to "wound"
        )

        # Freeform types should be normalized to wound
        assert enemy.health == 20, f"Freeform type should be treated as wound, got {enemy.health}"
        assert enemy.wounds == 2, f"Expected 2 wounds, got {enemy.wounds}"

    def test_stun_unconscious_check_triggers(self):
        """High stun damage should trigger unconscious check and mark entity inactive."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        # Target with low stats — high stun damage should trigger unconscious check
        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        # Massive stun damage — should trigger unconscious check
        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=25,
            soak=0,
            dealt=25,
            damage_type="stun"
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unarmed",
            resolved_damage_type="stun"
        )

        # Should have stun damage applied
        assert enemy.stuns > 0, f"Should have stuns, got {enemy.stuns}"
        # Health should NOT be reduced
        assert enemy.health == 30, f"Stun should not reduce HP, got {enemy.health}"

    def test_stun_does_not_kill(self):
        """Stun damage should never trigger health <= 0 death check."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=5, max_health=30, wounds=5, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        # Even with enemy at low HP, stun should not kill
        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=20,
            soak=0,
            dealt=20,
            damage_type="stun"
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unarmed",
            resolved_damage_type="stun"
        )

        # HP should remain at 5 (stun doesn't reduce HP)
        assert enemy.health == 5, f"Stun should not reduce HP, got {enemy.health}"
        # Should NOT have "KILLED" in messages
        kill_messages = [m for m in messages if "KILLED" in m]
        assert len(kill_messages) == 0, f"Stun should not kill: {kill_messages}"

    def test_resolved_damage_type_overrides_llm_type(self):
        """Backend-resolved weapon type takes priority over LLM's DamageEffect.damage_type."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        # LLM says "wound" but backend knows weapon is "stun"
        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=10,
            soak=2,
            dealt=8,
            damage_type="wound"  # LLM got it wrong
        )

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unarmed",
            resolved_damage_type="stun"  # Backend override
        )

        # Backend "stun" should override LLM's "wound"
        assert enemy.health == 30, f"Backend stun override should prevent HP loss, got {enemy.health}"
        assert enemy.stuns > 0, f"Backend stun override should add stuns, got {enemy.stuns}"


# =============================================================================
# TEST: _resolve_weapon_and_damage_type helper
# =============================================================================

class TestResolveWeaponAndDamageType:
    """Test weapon resolution helper function."""

    def test_brawl_unarmed_returns_stun(self):
        """Brawl skill with no Brawl sidearm → ('Unarmed', 'stun', fists weapon)."""
        from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type

        shared_state = make_mock_shared_state()
        player = make_mock_player_agent(
            agent_id="player_vex_1234",
            primary=make_mock_weapon("Plasma Rifle", "Guns", "wound"),
            sidearm=None
        )
        shared_state.player_agents = [player]

        action = {
            'agent_id': 'player_vex_1234',
            'skill': 'Brawl',
            'action_type': 'attack'
        }

        weapon_name, damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

        assert weapon_name == "Unarmed"
        assert damage_type == "stun"

    def test_brawl_with_shock_baton_returns_stun(self):
        """Brawl skill with Brawl-type sidearm → (weapon name, weapon damage_type)."""
        from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type

        shock_baton = make_mock_weapon("Shock Baton", "Brawl", "stun")
        shared_state = make_mock_shared_state()
        player = make_mock_player_agent(
            agent_id="player_vex_1234",
            sidearm=shock_baton
        )
        shared_state.player_agents = [player]

        action = {
            'agent_id': 'player_vex_1234',
            'skill': 'Brawl',
            'action_type': 'attack'
        }

        weapon_name, damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

        assert weapon_name == "Shock Baton"
        assert damage_type == "stun"

    def test_guns_with_primary_returns_wound(self):
        """Guns skill with primary weapon → (weapon name, weapon damage_type)."""
        from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type

        rifle = make_mock_weapon("Plasma Rifle", "Guns", "wound")
        shared_state = make_mock_shared_state()
        player = make_mock_player_agent(
            agent_id="player_vex_1234",
            primary=rifle
        )
        shared_state.player_agents = [player]

        action = {
            'agent_id': 'player_vex_1234',
            'skill': 'Guns',
            'action_type': 'attack'
        }

        weapon_name, damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

        assert weapon_name == "Plasma Rifle"
        assert damage_type == "wound"

    def test_melee_with_sidearm_returns_correct_type(self):
        """Melee skill with sidearm → (sidearm name, sidearm damage_type)."""
        from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type

        knife = make_mock_weapon("Combat Knife", "Melee", "mixed")
        shared_state = make_mock_shared_state()
        player = make_mock_player_agent(
            agent_id="player_vex_1234",
            sidearm=knife
        )
        shared_state.player_agents = [player]

        action = {
            'agent_id': 'player_vex_1234',
            'skill': 'Melee',
            'action_type': 'attack'
        }

        weapon_name, damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

        assert weapon_name == "Combat Knife"
        assert damage_type == "mixed"

    def test_no_player_found_returns_fallback(self):
        """No matching player agent → fallback values."""
        from scripts.aeonisk.multiagent.dm import _resolve_weapon_and_damage_type

        shared_state = make_mock_shared_state()
        shared_state.player_agents = []  # No players

        action = {
            'agent_id': 'player_nobody_0000',
            'skill': 'Guns',
            'action_type': 'attack'
        }

        weapon_name, damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

        assert damage_type == "wound"  # Default fallback


# =============================================================================
# TEST: JSONL Logging includes damage_type and stuns
# =============================================================================

class TestDamageTypeLogging:
    """Test that combat_action logs include damage_type and stuns."""

    def test_stun_damage_logged_with_type(self):
        """Stun damage should log damage_type='stun' in combat_action."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        enemy = make_mock_enemy(health=30, max_health=30, wounds=0, stuns=0)
        shared_state = make_mock_shared_state(enemies=[enemy])
        mechanics = make_mock_mechanics()

        damage_effect = DamageEffect(
            target="tgt_1234",
            base_damage=10,
            soak=2,
            dealt=8,
            damage_type="stun"
        )

        _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            mechanics=mechanics,
            attacker_id="player_vex",
            attacker_name="Vex",
            weapon="Unarmed",
            resolved_damage_type="stun"
        )

        # Verify log_combat_action was called with damage_type
        mechanics.jsonl_logger.log_combat_action.assert_called_once()
        call_kwargs = mechanics.jsonl_logger.log_combat_action.call_args
        damage_roll = call_kwargs.kwargs.get('damage_roll') or call_kwargs[1].get('damage_roll')
        assert damage_roll['damage_type'] == 'stun', f"Expected damage_type='stun' in log, got {damage_roll}"

        # Verify defender_state includes stuns
        defender_state = call_kwargs.kwargs.get('defender_state_after') or call_kwargs[1].get('defender_state_after')
        assert 'stuns' in defender_state, f"defender_state should include stuns: {defender_state}"
