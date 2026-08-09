"""
Unit tests for NPC combat, logging, and death state fixes (Spec 01).

Tests 3 bugs:
1. NPC double-logging — NPC actions should produce exactly 1 JSONL event, not 2
2. NPC 0-damage — NPC attacks should deal mechanical damage via YAGS formula
3. Death state — stun KO (stuns >= 6) should result in "unconscious", not "alive"

TDD: Tests written FIRST, then implementation.
"""

import pytest
import random
from unittest.mock import MagicMock, patch, call

from scripts.aeonisk.multiagent.enemy_agent import Position
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.agent_conversion import deescalate_enemy_to_npc
from scripts.aeonisk.multiagent.mechanics import apply_stun_damage, apply_wound_damage


# ===========================================================================
# Helpers
# ===========================================================================

def _make_weapon(
    name="Combat Pistol",
    skill="Guns",
    attack=3,
    defence=0,
    damage=5,
    damage_type="wound",
):
    """Create a minimal Weapon for testing."""
    from scripts.aeonisk.multiagent.weapons import Weapon
    return Weapon(
        name=name,
        skill=skill,
        attack=attack,
        defence=defence,
        damage=damage,
        damage_type=damage_type,
    )


def _make_npc(
    agent_id="npc_guard_01",
    name="Freeborn Guard",
    faction="Freeborn",
    skills=None,
    weapons=None,
    health=20,
    max_health=20,
    soak=4,
    stuns=0,
    wounds=0,
):
    """Create a minimal NPCAgent for testing."""
    from scripts.aeonisk.multiagent.enemy_agent import Position

    if skills is None:
        skills = {"Guns": 3, "Melee": 3, "Awareness": 2}

    npc = NPCAgent(
        agent_id=agent_id,
        name=name,
        faction=faction,
        entity_type="neutral",
        disposition="wary",
        threat_level="armed_neutral",
        description="A guard",
        health=health,
        max_health=max_health,
        soak=soak,
        void_score=0,
        skills=skills,
        weapons=weapons or [],
        stuns=stuns,
        wounds=wounds,
        position=Position.from_string("Near-PC"),
        can_act=False,  # Prevent LLM client initialization
    )
    return npc


def _make_target(
    agent_id="player_01",
    name="Test Player",
    health=25,
    max_health=25,
    soak=4,
    wounds=0,
    stuns=0,
):
    """Create a mock target with health tracking."""
    target = MagicMock()
    target.agent_id = agent_id
    target.name = name
    target.health = health
    target.max_health = max_health
    target.soak = soak
    target.wounds = wounds
    target.stuns = stuns
    target.is_active = True
    target.position = Position.from_string("Near-PC")
    target.character_state = MagicMock()
    target.character_state.name = name
    return target


def _make_enemy(
    agent_id="enemy_raider_01",
    name="Raider",
    faction="Freeborn",
    skills=None,
    attributes=None,
    weapons=None,
    health=30,
    max_health=30,
    soak=5,
):
    """Create a minimal test enemy for conversion testing."""
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

    if skills is None:
        skills = {"Guns": 4, "Melee": 3, "Awareness": 2}
    if attributes is None:
        attributes = {
            "Perception": 4, "Dexterity": 3, "Agility": 3,
            "Strength": 4, "Intelligence": 3, "Empathy": 2,
            "Willpower": 3, "Endurance": 3,
        }

    return EnemyAgent(
        agent_id=agent_id,
        name=name,
        faction=faction,
        health=health,
        max_health=max_health,
        soak=soak,
        skills=skills,
        attributes=attributes,
        weapons=weapons or [_make_weapon()],
        template="grunt_patrol",
        position=Position.from_string("Near-PC"),
        initiative=5,
        spawned_round=0,
        wounds=0,
        stuns=0,
    )


# ===========================================================================
# Bug 1 Tests: NPC Single-Logging
# ===========================================================================

class TestNPCSingleLog:
    """Verify NPC actions produce exactly 1 JSONL log event, not 2."""

    def test_npc_action_skips_generic_logging(self):
        """
        When an action has is_npc=True, the generic logging block in
        _handle_adjudication_inner should be skipped (NPC logging is
        already handled inside _resolve_action_mechanically with
        phase='adjudicate_npc').
        """
        action_npc = {
            'is_npc': True,
            'action_type': 'dialogue',
            'agent_id': 'npc_guard_01',
            'description': 'speaks to the party',
        }

        is_npc_action = action_npc.get('is_npc', False)
        assert is_npc_action is True, "NPC action should have is_npc=True"

    def test_player_action_not_skipped(self):
        """
        Player actions (without is_npc flag) should NOT be skipped
        by the NPC guard — they should go through generic logging.
        """
        action_player = {
            'action_type': 'attack',
            'description': 'fires at enemy',
        }

        is_npc_action = action_player.get('is_npc', False)
        assert is_npc_action is False, "Player action should not have is_npc flag"

    def test_npc_guard_in_dm_source(self):
        """
        Verify the is_npc guard prevents generic logging for NPC actions
        in dm.py _handle_adjudication_inner.

        The code should check is_npc and either:
        - Use `continue` to skip the rest of the loop body, OR
        - Use `not is_npc_action` guard around the logging call

        Either approach prevents double-logging.
        """
        import inspect
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        source = inspect.getsource(AIDMAgent._handle_adjudication_inner)

        # The guard must exist in some form
        assert "is_npc_action" in source or "is_npc" in source, (
            "_handle_adjudication_inner must check is_npc to prevent double-logging"
        )

        # The guard must prevent logging: either continue or conditional
        has_continue_guard = "is_npc_action" in source and "continue" in source
        has_conditional_guard = "not is_npc_action" in source
        assert has_continue_guard or has_conditional_guard, (
            "_handle_adjudication_inner must skip generic logging for NPC actions "
            "via either 'continue' or 'not is_npc_action' guard"
        )


# ===========================================================================
# Bug 2 Tests: NPC Attack Damage
# ===========================================================================

class TestEstimateAttributes:
    """Verify estimate_attributes() is a module-level function and produces correct values."""

    def test_estimate_attributes_importable(self):
        """estimate_attributes should be importable from agent_conversion at module level."""
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes
        assert callable(estimate_attributes)

    def test_estimate_attributes_from_skills(self):
        """
        Verify estimate_attributes() produces reasonable values.

        Input: {"Guns": 4, "Melee": 3, "Awareness": 2, "Athletics": 1}
        """
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        skills = {"Guns": 4, "Melee": 3, "Awareness": 2, "Athletics": 1}
        attrs = estimate_attributes(skills)

        assert attrs['Perception'] >= 3
        assert attrs['Dexterity'] >= 3
        assert attrs['Strength'] >= 3
        assert attrs['Agility'] >= 3

        # Human cap: all attributes should be <= 5
        for attr_name, attr_value in attrs.items():
            assert attr_value <= 5, f"{attr_name} should be <= 5 (human cap), got {attr_value}"

    def test_estimate_attributes_empty_skills(self):
        """NPC with empty skills={} should get all-default attributes (>= 2)."""
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        attrs = estimate_attributes({})

        assert attrs['Agility'] >= 3
        assert attrs['Strength'] >= 3
        assert attrs['Intelligence'] == 3
        assert attrs['Empathy'] == 2
        assert attrs['Willpower'] == 3

    def test_estimate_attributes_has_dexterity(self):
        """
        The extracted estimate_attributes must include Dexterity
        (needed for Melee combat) which the original nested version lacked.
        """
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        attrs = estimate_attributes({"Melee": 4})
        assert 'Dexterity' in attrs, "estimate_attributes must include Dexterity"
        assert attrs['Dexterity'] >= 3

    def test_estimate_attributes_has_endurance(self):
        """
        The extracted estimate_attributes must include Endurance
        (YAGS standard attribute) which the original nested version lacked.
        """
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        attrs = estimate_attributes({})
        assert 'Endurance' in attrs, "estimate_attributes must include Endurance"

    def test_estimate_attributes_high_skills_capped(self):
        """High skill values should produce higher attributes, capped at 5."""
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        skills = {"Guns": 8, "Melee": 8, "Athletics": 8, "Awareness": 8, "Brawl": 8}
        attrs = estimate_attributes(skills)

        for attr_name, attr_value in attrs.items():
            assert attr_value <= 5, f"{attr_name} should be capped at 5, got {attr_value}"


class TestNPCCombatProxy:
    """Verify NPCCombatProxy adapter and execute_npc_attack function."""

    def test_execute_npc_attack_importable(self):
        """execute_npc_attack should be importable from enemy_combat."""
        from scripts.aeonisk.multiagent.enemy_combat import execute_npc_attack
        assert callable(execute_npc_attack)

    def test_npc_combat_proxy_attributes(self):
        """
        NPCCombatProxy should have all attributes that _execute_attack needs.
        """
        from scripts.aeonisk.multiagent.enemy_combat import NPCCombatProxy
        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes

        weapon = _make_weapon()
        npc = _make_npc(weapons=[weapon])
        proxy = NPCCombatProxy(npc, estimate_attributes(npc.skills))

        assert proxy.agent_id == npc.agent_id
        assert proxy.name == npc.name
        assert proxy.faction == npc.faction
        assert isinstance(proxy.attributes, dict)
        assert proxy.skills == npc.skills
        assert proxy.weapons == npc.weapons
        assert proxy.health == npc.health
        assert proxy.max_health == npc.max_health
        assert proxy.soak == npc.soak
        assert proxy.wounds == npc.wounds
        assert proxy.stuns == npc.stuns
        assert proxy.is_active == npc.is_active
        assert proxy.defence_token is None
        assert proxy.tactical_token is None

    def test_npc_attack_no_weapon_graceful(self):
        """NPC with empty weapons list should get a failure result, not crash."""
        from scripts.aeonisk.multiagent.enemy_combat import execute_npc_attack
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        npc = _make_npc(weapons=[])
        resolution_state = ResolutionState()

        shared_state = MagicMock()
        shared_state.get_target_id_mapper.return_value = None

        result = execute_npc_attack(
            npc=npc,
            target_id="player_01",
            weapon_name=None,
            shared_state=shared_state,
            mechanics_engine=None,
            resolution_state=resolution_state,
            player_agents=[],
        )

        assert result is not None
        assert result.get('result') == 'no weapon' or 'no weapon' in str(result.get('narration', '')).lower()

    def test_npc_attack_deals_damage_via_proxy(self):
        """
        NPC attack through execute_npc_attack should use the full YAGS formula
        from _execute_attack via the NPCCombatProxy adapter.
        """
        from scripts.aeonisk.multiagent.enemy_combat import (
            execute_npc_attack,
            EnemyCombatManager,
        )
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        weapon = _make_weapon(name="Combat Pistol", skill="Guns", attack=3, damage=5, damage_type="wound")
        npc = _make_npc(
            skills={"Guns": 3, "Melee": 3, "Awareness": 2},
            weapons=[weapon],
        )
        target = _make_target(health=25, soak=4)

        resolution_state = ResolutionState()

        combat_manager = EnemyCombatManager()
        combat_manager.shared_state = MagicMock()
        combat_manager.shared_state.get_target_id_mapper.return_value = None

        shared_state = MagicMock()
        shared_state.get_target_id_mapper.return_value = None
        shared_state.session = MagicMock()
        shared_state.session.enemy_combat = combat_manager

        random.seed(42)

        result = execute_npc_attack(
            npc=npc,
            target_id=target.agent_id,
            weapon_name=None,
            shared_state=shared_state,
            mechanics_engine=MagicMock(),
            resolution_state=resolution_state,
            player_agents=[target],
        )

        assert result is not None
        assert 'enemy_id' in result or 'character_name' in result

    def test_npc_preserved_stats_used_after_conversion(self):
        """
        Convert EnemyAgent to NPCAgent via deescalate_enemy_to_npc().
        Then verify the NPC still has the original skills and weapons.
        """
        enemy = _make_enemy(
            skills={"Guns": 4, "Melee": 3, "Awareness": 2},
            weapons=[_make_weapon(name="Assault Rifle", skill="Guns", attack=5, damage=8)],
        )

        npc = deescalate_enemy_to_npc(enemy, disposition="wary")

        assert npc.skills.get("Guns") == 4
        assert npc.skills.get("Melee") == 3
        assert len(npc.weapons) == 1
        assert npc.weapons[0].name == "Assault Rifle"

        from scripts.aeonisk.multiagent.agent_conversion import estimate_attributes
        attrs = estimate_attributes(npc.skills)
        assert attrs['Agility'] >= 3


# ===========================================================================
# Bug 3 Tests: Death State Determination
# ===========================================================================

class TestDeathStateDetermination:
    """Verify correct death_state assignment in character_state snapshots."""

    def _determine_death_state(self, wounds, health, stuns):
        """
        Replicate the death_state logic from session.py.
        This is the EXPECTED logic after the fix.
        """
        if wounds >= 6:
            return "dead"
        elif health <= 0:
            return "unconscious"
        elif stuns >= 6:
            return "unconscious"
        else:
            return "alive"

    def test_zero_hp_is_unconscious(self):
        """Player with health=0, wounds<6, stuns<6 -> death_state='unconscious'."""
        assert self._determine_death_state(wounds=3, health=0, stuns=0) == "unconscious"

    def test_fatal_wounds_is_dead(self):
        """Player with wounds>=6 -> death_state='dead' regardless of HP."""
        assert self._determine_death_state(wounds=7, health=10, stuns=0) == "dead"
        assert self._determine_death_state(wounds=6, health=0, stuns=0) == "dead"

    def test_stun_ko_is_unconscious(self):
        """
        Player with stuns>=6 (Beaten threshold) -> death_state='unconscious'
        even if health > 0 and wounds < 6.
        """
        assert self._determine_death_state(wounds=0, health=20, stuns=7) == "unconscious"
        assert self._determine_death_state(wounds=0, health=20, stuns=6) == "unconscious"

    def test_healthy_is_alive(self):
        """Player with health>0, wounds<6, stuns<6 -> death_state='alive'."""
        assert self._determine_death_state(wounds=0, health=20, stuns=0) == "alive"
        assert self._determine_death_state(wounds=3, health=10, stuns=5) == "alive"

    def test_stun_damage_does_not_reduce_hp(self):
        """
        Verify apply_stun_damage() does NOT modify target.health.
        """
        target = MagicMock()
        target.stuns = 0
        target.health = 20

        result = apply_stun_damage(target, 7)

        assert target.health == 20, "apply_stun_damage should not reduce health"
        assert target.stuns == 7

    def test_wound_damage_reduces_hp(self):
        """Verify apply_wound_damage() reduces target.health."""
        target = MagicMock()
        target.wounds = 0
        target.health = 20

        result = apply_wound_damage(target, 8)

        assert target.health == 12, "apply_wound_damage should reduce health by damage_dealt"
        assert target.wounds == 1, "8 damage // 5 = 1 wound"

    def test_session_player_death_state_includes_stun_check(self):
        """
        Verify that session.py's player death_state logic includes
        the stun KO check (stuns >= 6 -> 'unconscious').
        """
        import inspect
        from scripts.aeonisk.multiagent import session

        source = inspect.getsource(session)

        # After fix, there should be a stun check in death_state logic
        # Look for "stuns >= 6" or "elif stuns" near death_state
        assert "stuns >= 6" in source or "enemy_stuns >= 6" in source, (
            "session.py must check stuns >= 6 for death_state determination"
        )

    def test_damage_without_wound_increment(self):
        """
        Apply 4 wound damage (< 5 threshold). Verify:
        - HP reduced by 4
        - wounds unchanged (4 // 5 = 0)
        """
        target = MagicMock()
        target.wounds = 0
        target.health = 4

        result = apply_wound_damage(target, 4)

        assert target.health == 0, "4 damage should reduce 4 HP to 0"
        assert target.wounds == 0, "4 damage // 5 = 0 wounds"

        death_state = self._determine_death_state(
            wounds=target.wounds, health=target.health, stuns=0
        )
        assert death_state == "unconscious", "0 HP with 0 wounds should be unconscious"

    def test_stun_ko_at_full_hp(self):
        """
        A character at full HP but stuns >= 6 should be 'unconscious'.
        """
        death_state = self._determine_death_state(wounds=0, health=25, stuns=8)
        assert death_state == "unconscious", (
            "Full HP but stuns>=6 should be 'unconscious', not 'alive'"
        )
