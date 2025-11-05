"""
Unit tests for NPC tracking in tactical_resolution.py ResolutionState.

Tests verify that ResolutionState correctly tracks:
- Surrendered NPCs (invalidate actions but keep present)
- Fled NPCs (removed from scene, don't appear in narration)
- Differentiation between defeated, surrendered, and fled states
"""

import pytest
from scripts.aeonisk.multiagent.tactical_resolution import (
    ResolutionState,
    ActionValidator,
    generate_invalidation_message
)


class TestResolutionStateNPCs:
    """Tests for NPC tracking in ResolutionState."""

    def test_mark_surrendered(self):
        """Enemies can be marked as surrendered."""
        state = ResolutionState()

        state.mark_surrendered("enemy_raider_1")

        assert state.is_surrendered("enemy_raider_1") == True
        assert state.is_defeated("enemy_raider_1") == False  # Not defeated, just surrendered

    def test_mark_fled(self):
        """NPCs can be marked as fled (left scene)."""
        state = ResolutionState()

        state.mark_fled("npc_civilian_1")

        assert state.has_fled("npc_civilian_1") == True
        assert state.is_defeated("npc_civilian_1") == False
        assert state.is_surrendered("npc_civilian_1") == False

    def test_surrendered_different_from_defeated(self):
        """Surrendered NPCs are distinct from defeated combatants."""
        state = ResolutionState()

        state.mark_surrendered("enemy_prisoner_1")
        state.mark_defeated("enemy_grunt_1")

        # Prisoner surrendered (alive, present, not acting)
        assert state.is_surrendered("enemy_prisoner_1") == True
        assert state.is_defeated("enemy_prisoner_1") == False

        # Grunt defeated (dead/unconscious)
        assert state.is_defeated("enemy_grunt_1") == True
        assert state.is_surrendered("enemy_grunt_1") == False

    def test_fled_different_from_defeated_and_surrendered(self):
        """Fled NPCs are distinct from defeated and surrendered."""
        state = ResolutionState()

        state.mark_fled("npc_civilian_1")
        state.mark_surrendered("enemy_prisoner_1")
        state.mark_defeated("enemy_grunt_1")

        # Civilian fled (not present)
        assert state.has_fled("npc_civilian_1") == True
        assert state.is_surrendered("npc_civilian_1") == False
        assert state.is_defeated("npc_civilian_1") == False

        # Prisoner surrendered (present, not acting)
        assert state.has_fled("enemy_prisoner_1") == False
        assert state.is_surrendered("enemy_prisoner_1") == True
        assert state.is_defeated("enemy_prisoner_1") == False

        # Grunt defeated (present, incapacitated)
        assert state.has_fled("enemy_grunt_1") == False
        assert state.is_surrendered("enemy_grunt_1") == False
        assert state.is_defeated("enemy_grunt_1") == True

    def test_multiple_surrendered_npcs(self):
        """Multiple NPCs can be marked as surrendered."""
        state = ResolutionState()

        state.mark_surrendered("enemy_raider_1")
        state.mark_surrendered("enemy_raider_2")
        state.mark_surrendered("enemy_raider_3")

        assert state.is_surrendered("enemy_raider_1") == True
        assert state.is_surrendered("enemy_raider_2") == True
        assert state.is_surrendered("enemy_raider_3") == True

    def test_multiple_fled_npcs(self):
        """Multiple NPCs can be marked as fled."""
        state = ResolutionState()

        state.mark_fled("npc_civilian_1")
        state.mark_fled("npc_civilian_2")
        state.mark_fled("npc_dock_worker_1")

        assert state.has_fled("npc_civilian_1") == True
        assert state.has_fled("npc_civilian_2") == True
        assert state.has_fled("npc_dock_worker_1") == True

    def test_action_validator_attacker_surrendered(self):
        """Surrendered attackers cannot attack."""
        state = ResolutionState()
        state.mark_surrendered("enemy_raider_1")

        can_attack, reason = ActionValidator.can_attack(
            attacker_id="enemy_raider_1",
            target_id="player_01",
            resolution_state=state
        )

        assert can_attack == False
        assert reason == "attacker_surrendered"

    def test_action_validator_attacker_defeated(self):
        """Defeated attackers cannot attack."""
        state = ResolutionState()
        state.mark_defeated("enemy_raider_1")

        can_attack, reason = ActionValidator.can_attack(
            attacker_id="enemy_raider_1",
            target_id="player_01",
            resolution_state=state
        )

        assert can_attack == False
        assert reason == "attacker_defeated"

    def test_action_validator_claimant_surrendered(self):
        """Surrendered claimants cannot claim tokens."""
        state = ResolutionState()
        state.mark_surrendered("enemy_raider_1")

        can_claim, reason = ActionValidator.can_claim_token(
            claimant_id="enemy_raider_1",
            token_name="Cover",
            resolution_state=state
        )

        assert can_claim == False
        assert reason == "claimant_surrendered"

    def test_action_validator_mover_surrendered(self):
        """Surrendered movers cannot move."""
        state = ResolutionState()
        state.mark_surrendered("enemy_raider_1")

        can_move, reason = ActionValidator.can_move(
            mover_id="enemy_raider_1",
            resolution_state=state
        )

        assert can_move == False
        assert reason == "mover_surrendered"

    def test_invalidation_message_attacker_surrendered(self):
        """Generate appropriate message for surrendered attacker."""
        message = generate_invalidation_message(
            agent_name="Raider",
            action_type="attack",
            failure_reason="attacker_surrendered"
        )

        assert "🏳️" in message
        assert "surrendered" in message.lower()
        assert "will not fight" in message.lower()

    def test_invalidation_message_claimant_surrendered(self):
        """Generate appropriate message for surrendered claimant."""
        message = generate_invalidation_message(
            agent_name="Prisoner",
            action_type="claim_token",
            failure_reason="claimant_surrendered"
        )

        assert "🏳️" in message
        assert "surrendered" in message.lower()

    def test_invalidation_message_mover_surrendered(self):
        """Generate appropriate message for surrendered mover."""
        message = generate_invalidation_message(
            agent_name="Captive",
            action_type="move",
            failure_reason="mover_surrendered"
        )

        assert "🏳️" in message
        assert "surrendered" in message.lower()
        assert "remains in place" in message.lower()

    def test_surrendered_set_initialization(self):
        """ResolutionState initializes with empty surrendered set."""
        state = ResolutionState()

        assert len(state.surrendered) == 0
        assert state.is_surrendered("any_id") == False

    def test_fled_set_initialization(self):
        """ResolutionState initializes with empty fled_npcs set."""
        state = ResolutionState()

        assert len(state.fled_npcs) == 0
        assert state.has_fled("any_id") == False

    def test_mark_surrendered_logs_debug(self, caplog):
        """mark_surrendered logs info message."""
        import logging
        caplog.set_level(logging.INFO)

        state = ResolutionState()
        state.mark_surrendered("enemy_raider_1")

        assert "enemy_raider_1 marked as surrendered" in caplog.text

    def test_mark_fled_logs_info(self, caplog):
        """mark_fled logs info message."""
        import logging
        caplog.set_level(logging.INFO)

        state = ResolutionState()
        state.mark_fled("npc_civilian_1")

        assert "npc_civilian_1 marked as fled" in caplog.text

    def test_has_fled_check_nonexistent(self):
        """has_fled returns False for non-existent NPC."""
        state = ResolutionState()

        assert state.has_fled("npc_nonexistent") == False

    def test_is_surrendered_check_nonexistent(self):
        """is_surrendered returns False for non-existent agent."""
        state = ResolutionState()

        assert state.is_surrendered("enemy_nonexistent") == False

    def test_fled_npcs_field_exists(self):
        """ResolutionState has fled_npcs field."""
        state = ResolutionState()

        assert hasattr(state, 'fled_npcs')
        assert isinstance(state.fled_npcs, set)

    def test_surrendered_field_exists(self):
        """ResolutionState has surrendered field."""
        state = ResolutionState()

        assert hasattr(state, 'surrendered')
        assert isinstance(state.surrendered, set)

    def test_resolution_state_tracks_all_three_states(self):
        """ResolutionState can track defeated, surrendered, and fled simultaneously."""
        state = ResolutionState()

        # Set up different states
        state.mark_defeated("enemy_grunt_1")
        state.mark_surrendered("enemy_raider_1")
        state.mark_fled("npc_civilian_1")

        # All three tracked independently
        assert state.is_defeated("enemy_grunt_1") == True
        assert state.is_surrendered("enemy_raider_1") == True
        assert state.has_fled("npc_civilian_1") == True

        # No overlap
        assert state.is_surrendered("enemy_grunt_1") == False
        assert state.has_fled("enemy_grunt_1") == False

        assert state.is_defeated("enemy_raider_1") == False
        assert state.has_fled("enemy_raider_1") == False

        assert state.is_defeated("npc_civilian_1") == False
        assert state.is_surrendered("npc_civilian_1") == False

    def test_action_validator_works_with_mix_of_states(self):
        """ActionValidator correctly handles multiple state types."""
        state = ResolutionState()

        state.mark_defeated("enemy_grunt_1")
        state.mark_surrendered("enemy_raider_1")
        state.mark_fled("npc_civilian_1")

        # Defeated can't attack
        can_attack, _ = ActionValidator.can_attack("enemy_grunt_1", "player_01", state)
        assert can_attack == False

        # Surrendered can't attack
        can_attack, _ = ActionValidator.can_attack("enemy_raider_1", "player_01", state)
        assert can_attack == False

        # Fled NPC can't attack (but no specific validator for fled)
        # (Fled NPCs are removed from scene, so they wouldn't be in action list anyway)

        # Fresh agent can attack
        can_attack, reason = ActionValidator.can_attack("enemy_fresh_1", "player_01", state)
        assert can_attack == True
        assert reason == None
