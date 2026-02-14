"""
Unit tests for healing defeat guard (Fix 5).

Problem: Structured output healing can resurrect defeated characters.
A character at 0 HP/4 wounds/alive=false was healed to 27/27 HP — full resurrection.

Fix: _process_structured_healing_effects() must check defeat/death state:
- Dead (wounds >= 6): reject healing entirely
- Defeated/unconscious (health <= 0, wounds < 6): cap at 1 HP (stabilized)
- Alive (health > 0): normal healing
"""

import pytest
from unittest.mock import MagicMock

from scripts.aeonisk.multiagent.schemas.action_effects import HealingEffect


class TestHealingDefeatGuard:
    """Verify _process_structured_healing_effects rejects resurrection."""

    def _make_target(self, health, max_health=27, wounds=0, is_player=True):
        """Create mock entity."""
        entity = MagicMock()
        entity.health = health
        entity.max_health = max_health
        entity.wounds = wounds
        entity.stuns = 0
        entity.is_active = health > 0
        if is_player:
            entity.agent_id = "player_kael"
            entity.character_state = MagicMock()
            entity.character_state.name = "Kael Draven"
        else:
            entity.agent_id = "npc_arin"
            entity.name = "Arin Voss"
        return entity

    def _make_shared_state(self, target_entity, use_tgt_id=True):
        """Create mock shared state that resolves the target."""
        shared_state = MagicMock()
        shared_state.player_agents = []
        shared_state.npc_agents = []
        shared_state.enemy_combat = None

        if use_tgt_id:
            mapper = MagicMock()
            mapper.enabled = True
            mapper.resolve_target.return_value = target_entity
            shared_state.get_target_id_mapper.return_value = mapper
        else:
            shared_state.get_target_id_mapper.return_value = None
            if hasattr(target_entity, 'character_state'):
                shared_state.player_agents = [target_entity]
            else:
                shared_state.npc_agents = [target_entity]

        return shared_state

    def _call_healing(self, target, shared_state, heal_amount=20, heal_type="hp", target_id="tgt_kael"):
        """Call _process_structured_healing_effects with given params."""
        from scripts.aeonisk.multiagent.dm import _process_structured_healing_effects

        healing_effects = [
            HealingEffect(
                target=target_id,
                heal_type=heal_type,
                amount=heal_amount,
                source="Medicine (Arin Voss)"
            )
        ]

        mechanics = MagicMock()
        mechanics.jsonl_logger = MagicMock()

        messages = _process_structured_healing_effects(
            healing_effects=healing_effects,
            shared_state=shared_state,
            current_round=2,
            mechanics=mechanics,
        )
        return messages

    def test_dead_character_cannot_be_healed(self):
        """Character with wounds >= 6 is dead — healing should be rejected."""
        target = self._make_target(health=-5, wounds=6)
        shared_state = self._make_shared_state(target)

        messages = self._call_healing(target, shared_state, heal_amount=27)

        # Health should NOT change
        assert target.health == -5, f"Dead character HP changed: {target.health}"
        # Message should indicate rejection
        assert any("beyond saving" in m.lower() or "dead" in m.lower() for m in messages), \
            f"Expected rejection message, got: {messages}"

    def test_defeated_character_capped_at_1hp(self):
        """Character at 0 HP with wounds < 6 is unconscious — heal caps at 1 HP."""
        target = self._make_target(health=0, wounds=4)
        shared_state = self._make_shared_state(target)

        self._call_healing(target, shared_state, heal_amount=27)

        # Should be stabilized at 1 HP, not fully healed to 27
        assert target.health == 1, f"Expected 1 HP (stabilized), got {target.health}"

    def test_defeated_negative_hp_capped_at_1hp(self):
        """Character at negative HP with wounds < 6 — heal caps at 1 HP."""
        target = self._make_target(health=-3, wounds=3)
        shared_state = self._make_shared_state(target)

        self._call_healing(target, shared_state, heal_amount=20)

        assert target.health == 1, f"Expected 1 HP (stabilized), got {target.health}"

    def test_alive_character_healed_normally(self):
        """Character with health > 0 gets normal healing capped at max_health."""
        target = self._make_target(health=10, max_health=27, wounds=1)
        shared_state = self._make_shared_state(target)

        self._call_healing(target, shared_state, heal_amount=20)

        # Should heal to min(10+20, 27) = 27
        assert target.health == 27, f"Expected 27 HP, got {target.health}"

    def test_alive_character_healing_capped_at_max(self):
        """Healing doesn't exceed max_health for alive characters."""
        target = self._make_target(health=25, max_health=27, wounds=0)
        shared_state = self._make_shared_state(target)

        self._call_healing(target, shared_state, heal_amount=10)

        assert target.health == 27, f"Expected 27 HP (capped), got {target.health}"

    def test_defeated_character_not_reactivated(self):
        """Stabilized character should not be marked is_active=True."""
        target = self._make_target(health=0, wounds=4)
        target.is_active = False
        shared_state = self._make_shared_state(target)

        self._call_healing(target, shared_state, heal_amount=27)

        # Should stabilize but NOT reactivate
        assert target.health == 1
        # is_active should remain False (stabilized, not combat-ready)
        # The healing_applied log should say "stabilized" not "active"

    def test_wound_healing_on_dead_character_rejected(self):
        """Wound healing on dead character (wounds >= 6) should be rejected."""
        target = self._make_target(health=-10, wounds=7)
        shared_state = self._make_shared_state(target)

        old_wounds = target.wounds
        self._call_healing(target, shared_state, heal_amount=3, heal_type="wound")

        assert target.wounds == old_wounds, f"Dead character wounds changed: {target.wounds}"

    def test_stun_healing_on_dead_character_rejected(self):
        """Stun healing on dead character should be rejected."""
        target = self._make_target(health=-10, wounds=6)
        shared_state = self._make_shared_state(target)

        messages = self._call_healing(target, shared_state, heal_amount=5, heal_type="stun")
        assert any("beyond saving" in m.lower() or "dead" in m.lower() for m in messages)

    def test_stabilization_message_for_unconscious(self):
        """Healing an unconscious character should produce 'stabilized' message."""
        target = self._make_target(health=0, wounds=3)
        shared_state = self._make_shared_state(target)

        messages = self._call_healing(target, shared_state, heal_amount=15)

        assert target.health == 1
        assert any("stabiliz" in m.lower() for m in messages), \
            f"Expected stabilization message, got: {messages}"
