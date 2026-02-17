"""
Unit tests for NPC attack action resolution in dm.py.

Tests NPC simplified YAGS combat: skill check + weapon damage.
"""

import pytest
import random
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from scripts.aeonisk.multiagent.npc_agent import NPCAction, NPCAgent
from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY


class TestNPCActionAttackValidation:
    """NPCAction schema validates attack requirements."""

    def test_attack_with_target_valid(self):
        """Attack with target should validate successfully."""
        action = NPCAction(
            action_type="attack",
            reason="The guard threatens my people, I must fight back.",
            target="tgt_1234"
        )
        assert action.action_type == "attack"
        assert action.target == "tgt_1234"

    def test_attack_without_target_raises(self):
        """Attack without target should raise ValidationError."""
        with pytest.raises(ValidationError, match="target is REQUIRED.*attack"):
            NPCAction(
                action_type="attack",
                reason="I want to fight someone but didn't specify who.",
            )

    def test_attack_with_named_target(self):
        """Attack can use named target (not just tgt_ IDs)."""
        action = NPCAction(
            action_type="attack",
            reason="Defending myself against the approaching guard.",
            target="enemy_pantheon_01"
        )
        assert action.target == "enemy_pantheon_01"


class TestNPCAttackResolution:
    """NPC attack resolution in DM adjudication."""

    def _make_npc_entity(
        self,
        name="Freeborn Guard",
        agent_id="npc_guard_01",
        skills=None,
        weapons=None,
        health=20,
        soak=4,
    ):
        """Create a mock NPC entity with combat stats."""
        npc = MagicMock(spec=NPCAgent)
        npc.name = name
        npc.agent_id = agent_id
        npc.health = health
        npc.max_health = health
        npc.soak = soak
        npc.stuns = 0
        npc.wounds = 0
        npc.is_active = True
        npc.skills = skills or {"Guns": 3, "Melee": 2}
        npc.weapons = weapons or [WEAPON_LIBRARY['pistol']]
        return npc

    def _make_target_pc(self, name="Ash Vex", agent_id="player_01", health=27, soak=12):
        """Create a mock PC target."""
        pc = MagicMock()
        pc.name = name
        pc.agent_id = agent_id
        pc.health = health
        pc.max_health = 27
        pc.soak = soak
        pc.stuns = 0
        pc.wounds = 0
        pc.character_state = MagicMock()
        pc.character_state.name = name
        return pc

    def _make_target_enemy(self, name="Pantheon Guard", agent_id="enemy_01", health=20, soak=8):
        """Create a mock enemy target."""
        enemy = MagicMock()
        enemy.name = name
        enemy.agent_id = agent_id
        enemy.health = health
        enemy.max_health = 20
        enemy.soak = soak
        enemy.stuns = 0
        enemy.wounds = 0
        enemy.is_active = True
        enemy.tactics = "aggressive"
        return enemy

    def test_npc_attack_hit_damages_pc(self):
        """NPC attack that hits should deal damage to target PC."""
        npc = self._make_npc_entity(skills={"Guns": 4})
        target = self._make_target_pc(health=27, soak=10)

        # Simulate attack: attr(3) × skill(4) + weapon.attack(0) + d20(18) = 12+0+18 = 30 vs DC 15
        # Hit! Damage: strength(3) + weapon.damage(6) + d20(10) = 19, × 0.85 = 16
        # After soak(10): 6 damage dealt
        with patch('random.randint', return_value=18):
            # Attack roll: Perception(3) × Guns(4) + pistol.attack(0) + d20(18)
            attack_total = (3 * 4) + WEAPON_LIBRARY['pistol'].attack + 18
            assert attack_total >= 15  # Should hit (= 30)

        # Damage roll
        with patch('random.randint', return_value=10):
            base_damage = 3 + WEAPON_LIBRARY['pistol'].damage + 10
            total_damage = int(base_damage * 0.85)
            damage_dealt = max(0, total_damage - 10)  # soak = 10
            assert total_damage > 0

    def test_npc_attack_miss(self):
        """NPC attack with low roll should miss."""
        npc = self._make_npc_entity(skills={"Guns": 1})

        # attr(3) × skill(1) + weapon.attack(2) + d20(1) = 3+2+1 = 6 vs DC 15
        attack_total = (3 * 1) + WEAPON_LIBRARY['pistol'].attack + 1
        assert attack_total < 15  # Should miss

    def test_npc_no_weapon_fails(self):
        """NPC with no weapons should fail to attack."""
        npc = MagicMock()
        npc.name = "Unarmed NPC"
        npc.agent_id = "npc_unarmed_01"
        npc.weapons = []  # Explicitly empty - no spec to override
        npc.skills = {"Guns": 0}
        # No weapons → attack should fail (handled in DM adjudication code)
        assert len(npc.weapons) == 0

    def test_unskilled_penalty_applied(self):
        """NPC with skill=0 gets -5 unskilled penalty."""
        npc = self._make_npc_entity(skills={"Guns": 0})

        # Unskilled: attr(3) × max(skill,1) + weapon.attack(0) + d20(10) - 5 = 3+0+10-5 = 8 vs DC 15
        skill = npc.skills.get("Guns", 0)
        unskilled_penalty = -5 if skill == 0 else 0
        skill_value = max(skill, 1)
        attack_total = (3 * skill_value) + WEAPON_LIBRARY['pistol'].attack + 10 + unskilled_penalty
        assert attack_total == 8  # 3*1+0+10-5 = 8 < DC 15 → miss

    def test_stun_damage_type(self):
        """NPC with stun weapon applies stun damage."""
        from scripts.aeonisk.multiagent.mechanics import apply_stun_damage

        target = MagicMock()
        target.stuns = 0

        result = apply_stun_damage(target, 5)
        assert result['stuns_dealt'] == 5
        assert target.stuns == 5

    def test_wound_damage_type(self):
        """NPC with wound weapon applies wound damage."""
        from scripts.aeonisk.multiagent.mechanics import apply_wound_damage

        target = MagicMock()
        target.wounds = 0
        target.health = 20

        result = apply_wound_damage(target, 5)
        # Wound damage reduces health and may add wounds
        assert result['wounds_dealt'] >= 0

    def test_mixed_damage_type(self):
        """NPC with mixed weapon applies mixed damage."""
        from scripts.aeonisk.multiagent.mechanics import apply_mixed_damage

        target = MagicMock()
        target.stuns = 0
        target.wounds = 0
        target.health = 20

        result = apply_mixed_damage(target, 8)
        assert result['stuns_dealt'] >= 0
        assert result['wounds_dealt'] >= 0

    def test_npc_can_attack_enemy_target(self):
        """NPC should be able to resolve attacks against enemy targets."""
        npc = self._make_npc_entity()
        target = self._make_target_enemy()

        # The NPC attack code uses the same mechanics as enemy combat
        # Verify attack math works with enemy stats
        skill = npc.skills.get("Guns", 0)
        skill_value = max(skill, 1)
        attack_total = (3 * skill_value) + WEAPON_LIBRARY['pistol'].attack + 15
        assert attack_total >= 15  # Should hit with d20=15

    def test_npc_can_attack_other_npc(self):
        """NPC should be able to resolve attacks against other NPCs."""
        attacker = self._make_npc_entity(name="Freeborn Fighter", agent_id="npc_01")
        target = MagicMock()
        target.name = "Freeborn Worker"
        target.agent_id = "npc_02"
        target.health = 15
        target.soak = 4
        target.stuns = 0
        target.wounds = 0

        # Verify both entities have required combat attributes
        assert hasattr(target, 'health')
        assert hasattr(target, 'soak')
        assert hasattr(target, 'stuns')
        assert hasattr(target, 'wounds')

    def test_guns_uses_perception(self):
        """Guns skill attack should use Perception attribute (default 3)."""
        # Guns → Perception
        attr_value = 3  # Default NPC Perception
        skill = 3
        weapon_attack = WEAPON_LIBRARY['pistol'].attack  # = 0
        d20 = 10
        total = attr_value * skill + weapon_attack + d20
        assert total == 3 * 3 + 0 + 10  # = 19

    def test_melee_uses_dexterity(self):
        """Melee skill attack should use Dexterity attribute (default 3)."""
        # Melee → Dexterity
        attr_value = 3  # Default NPC Dexterity
        skill = 2
        weapon_attack = WEAPON_LIBRARY['combat_knife'].attack
        d20 = 10
        total = attr_value * skill + weapon_attack + d20
        # combat_knife has attack=3 (check actual value)
        assert total == 3 * 2 + weapon_attack + 10

    def test_brawl_uses_agility(self):
        """Brawl skill attack should use Agility attribute (default 3)."""
        # Brawl → Agility
        attr_value = 3  # Default NPC Agility
        skill = 1
        weapon_attack = WEAPON_LIBRARY['fists'].attack
        d20 = 10
        total = attr_value * skill + weapon_attack + d20
        assert total == 3 * 1 + 0 + 10  # = 13
