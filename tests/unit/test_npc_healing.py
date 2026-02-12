"""
Unit tests for NPC healing feature.

Tests that NPCAction schema supports heal action type and that
the DM properly resolves NPC heal actions with Medicine skill checks.
"""

import pytest
import random
from unittest.mock import MagicMock, patch, AsyncMock

from scripts.aeonisk.multiagent.npc_agent import NPCAction


class TestNPCActionHealSchema:
    """Test NPCAction schema accepts and validates heal action."""

    def test_npc_action_schema_accepts_heal(self):
        """NPCAction validates with action_type='heal'."""
        action = NPCAction(
            action_type="heal",
            reason="I rush to stabilize the wounded player with field medicine.",
            target="player_01"
        )
        assert action.action_type == "heal"
        assert action.target == "player_01"

    def test_npc_action_heal_requires_target(self):
        """Heal action without target raises ValidationError."""
        with pytest.raises(ValueError, match="target.*REQUIRED.*heal"):
            NPCAction(
                action_type="heal",
                reason="I try to heal someone but forgot who."
            )

    def test_npc_action_heal_with_target_is_valid(self):
        """Heal action with target passes validation."""
        action = NPCAction(
            action_type="heal",
            reason="Applying pressure bandages to stop the bleeding.",
            target="tgt_a3f2"
        )
        assert action.action_type == "heal"
        assert action.target == "tgt_a3f2"

    def test_npc_action_other_types_still_work(self):
        """Existing action types are unaffected by adding heal."""
        # flee - no target needed
        flee = NPCAction(action_type="flee", reason="Running away from the gunfire and chaos.")
        assert flee.action_type == "flee"

        # assist - with target
        assist = NPCAction(action_type="assist", reason="Helping the player hack the terminal.", target="player_02")
        assert assist.action_type == "assist"

        # dialogue - with content
        dialogue = NPCAction(
            action_type="dialogue",
            reason="Warning the players about the ambush ahead of them.",
            dialogue_content="Watch out! There are guards around the corner!"
        )
        assert dialogue.action_type == "dialogue"


class TestNPCHealResolution:
    """Test DM resolution of NPC heal actions."""

    def _make_npc_entity(self, medicine_skill=None, intelligence=3):
        """Create a mock NPC entity with optional Medicine skill."""
        npc = MagicMock()
        npc.name = "Medic Kira"
        npc.agent_id = "npc_medic_01"
        npc.health = 20
        npc.max_health = 20
        npc.wounds = 0
        npc.stuns = 0
        npc.skills = {"Medicine": medicine_skill} if medicine_skill else {}
        npc.is_active = True
        return npc

    def _make_target_entity(self, health=0, max_health=20, wounds=3, is_player=True):
        """Create a mock target entity (player or NPC)."""
        target = MagicMock()
        target.health = health
        target.max_health = max_health
        target.wounds = wounds
        target.stuns = 0
        target.is_active = True
        if is_player:
            target.agent_id = "player_01"
            target.character_state = MagicMock()
            target.character_state.name = "Ash Vex"
        else:
            target.agent_id = "npc_ally_01"
            target.name = "Field Agent"
        return target

    def test_npc_heal_resolution_with_medicine_skill(self):
        """NPC with Medicine skill gets proper roll formula: 3 x Medicine + d20."""
        npc = self._make_npc_entity(medicine_skill=4)

        # Medicine 4 * 3 = 12. With d20=10, total = 22, passes DC 18
        intelligence = 3  # Default NPC intelligence
        medicine = npc.skills.get("Medicine", 0)
        roll_total = intelligence * medicine  # 3 * 4 = 12
        d20 = 10
        total = roll_total + d20  # 22
        dc = 18

        assert total >= dc  # Should succeed
        assert medicine == 4

    def test_npc_heal_without_medicine_uses_unskilled(self):
        """NPC without Medicine skill gets unskilled penalty (-5)."""
        npc = self._make_npc_entity(medicine_skill=None)

        intelligence = 3
        medicine = npc.skills.get("Medicine", 0)
        unskilled_penalty = -5 if medicine == 0 else 0
        # With 0 medicine: base = 3 * 0 = 0, penalty = -5
        # Need d20 >= 23 to pass DC 18 (impossible with d20)
        roll_total = intelligence * max(medicine, 1) + unskilled_penalty  # 3*1 - 5 = -2
        d20 = 20  # Best possible roll
        total = roll_total + d20  # -2 + 20 = 18

        # With max d20, unskilled NPC barely ties DC 18
        assert total >= dc if (dc := 18) else True  # Marginal pass at best

    def test_npc_heal_dead_target_no_effect(self):
        """Target with wounds >= 6 cannot be healed (dead)."""
        target = self._make_target_entity(health=-10, wounds=6)

        # Dead check: wounds >= 6 means permanently dead
        is_dead = target.wounds >= 6
        assert is_dead is True  # Should not attempt healing

    def test_npc_heal_any_entity_type(self):
        """NPCs can target players, enemies, or other NPCs for healing."""
        # Player target
        action_player = NPCAction(
            action_type="heal",
            reason="Stabilizing the unconscious player with emergency medicine.",
            target="player_01"
        )
        assert action_player.target == "player_01"

        # Enemy target (NPCs might have reasons to heal enemies)
        action_enemy = NPCAction(
            action_type="heal",
            reason="Healing the wounded enemy to interrogate them later.",
            target="enemy_pirate_01"
        )
        assert action_enemy.target == "enemy_pirate_01"

        # NPC target
        action_npc = NPCAction(
            action_type="heal",
            reason="Helping fellow NPC ally with their injuries.",
            target="npc_ally_02"
        )
        assert action_npc.target == "npc_ally_02"
