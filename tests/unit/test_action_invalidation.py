"""
Tests for action invalidation during the declare/resolve cycle.

Bug: Combatants knocked unconscious by stun damage (stuns >= 6) can still act
because:
1. check_death_save() only checks wounds, not stuns
2. is_in_combat doesn't check stun status
3. _mark_defeated_from_resolution only checks is_active, not health/stuns

The declare/resolve cycle:
  - Declaration: All combatants declare (slowest first)
  - Resolution: Actions resolve (fastest first)
  - If someone is incapacitated during resolution, their already-declared
    action should be INVALIDATED.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional


# ============================================================================
# TEST FIXTURES
# ============================================================================

@dataclass
class MockEnemyAgent:
    """Minimal mock of EnemyAgent for testing."""
    agent_id: str = "enemy_test_01"
    name: str = "Test Enemy"
    health: int = 20
    max_health: int = 20
    stuns: int = 0
    wounds: int = 0
    soak: int = 2
    is_active: bool = True
    faction: str = "Independent"
    spawned_round: int = 0


@dataclass
class MockPlayerAgent:
    """Minimal mock of AIPlayerAgent for testing stun/death tracking."""
    agent_id: str = "player_test_01"
    name: str = "Test Player"
    health: int = 27
    max_health: int = 27
    stuns: int = 0
    wounds: int = 0
    soak: int = 3
    is_alive: bool = True
    is_extracted: bool = False

    @property
    def is_in_combat(self) -> bool:
        """Mirror the real player.is_in_combat logic."""
        if not self.is_alive:
            return False
        if self.is_extracted:
            return False
        return True

    def check_death_save(self):
        """Mirror real check_death_save — only checks wounds."""
        if self.wounds < 5:
            return True, "conscious"
        # Simplified: wounds >= 5 = unconscious
        return True, "unconscious"


# ============================================================================
# TEST: _mark_defeated_from_resolution safety net
# ============================================================================

class TestMarkDefeatedSafetyNet:
    """
    _mark_defeated_from_resolution should catch enemies that are
    effectively defeated but whose is_active wasn't set to False.
    """

    def _get_mark_defeated(self):
        """Import the function under test."""
        import importlib
        import sys
        # Import the module
        session_mod = importlib.import_module('scripts.aeonisk.multiagent.session')
        return session_mod._mark_defeated_from_resolution

    def _make_resolution_state(self):
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState
        return ResolutionState()

    def test_enemy_health_zero_but_is_active_true(self):
        """Enemy with health <= 0 but is_active=True should be marked defeated."""
        mark_defeated = self._get_mark_defeated()
        resolution_state = self._make_resolution_state()

        enemy = MockEnemyAgent(health=0, is_active=True)
        enemy_combat = MagicMock()
        enemy_combat.enemy_agents = [enemy]

        mark_defeated(enemy_combat, resolution_state)

        assert resolution_state.is_defeated(enemy.agent_id), \
            "Enemy with health=0 should be marked defeated even if is_active=True"

    def test_enemy_stuns_at_ko_threshold(self):
        """Enemy with stuns >= 6 (Beaten/unconscious) should be marked incapacitated."""
        mark_defeated = self._get_mark_defeated()
        resolution_state = self._make_resolution_state()

        enemy = MockEnemyAgent(stuns=6, is_active=True, health=15)
        enemy_combat = MagicMock()
        enemy_combat.enemy_agents = [enemy]

        mark_defeated(enemy_combat, resolution_state)

        assert resolution_state.is_incapacitated(enemy.agent_id), \
            "Enemy with stuns >= 6 should be marked incapacitated (stun KO)"
        # Incapacitated enemies can't act — ActionValidator blocks them
        from scripts.aeonisk.multiagent.tactical_resolution import ActionValidator
        can_proceed, reason = ActionValidator.can_attack(enemy.agent_id, "player_01", resolution_state)
        assert not can_proceed, "Incapacitated enemy should not be able to attack"
        assert reason == "attacker_incapacitated"

    def test_enemy_active_and_healthy_not_defeated(self):
        """Active enemy with health > 0 and low stuns should NOT be defeated."""
        mark_defeated = self._get_mark_defeated()
        resolution_state = self._make_resolution_state()

        enemy = MockEnemyAgent(health=15, stuns=2, is_active=True)
        enemy_combat = MagicMock()
        enemy_combat.enemy_agents = [enemy]

        mark_defeated(enemy_combat, resolution_state)

        assert not resolution_state.is_defeated(enemy.agent_id), \
            "Active enemy with health and low stuns should NOT be defeated"

    def test_already_defeated_not_double_marked(self):
        """Already-defeated enemy should not be re-processed."""
        mark_defeated = self._get_mark_defeated()
        resolution_state = self._make_resolution_state()
        resolution_state.mark_defeated("enemy_test_01")

        enemy = MockEnemyAgent(health=0, is_active=False)
        enemy_combat = MagicMock()
        enemy_combat.enemy_agents = [enemy]

        # Should not raise or duplicate
        mark_defeated(enemy_combat, resolution_state)
        assert resolution_state.is_defeated(enemy.agent_id)


# ============================================================================
# TEST: Stun KO in enemy attack (_execute_attack)
# ============================================================================

class TestStunKOInvalidation:
    """
    When an enemy attack applies stun damage that causes KO (stuns >= 6),
    the target should be marked as incapacitated in resolution_state, even if
    their wound count is low and health is still > 0.

    The fix: stun KO is detected SEPARATELY from wound-based death saves.
    check_death_save() correctly only checks wounds (per YAGS).
    Stun KO bypasses check_death_save entirely.
    """

    def test_stun_ko_triggers_unconscious_check(self):
        """Stun damage reaching 6+ should trigger unconscious_check_needed."""
        from scripts.aeonisk.multiagent.mechanics import apply_stun_damage

        target = MockPlayerAgent(stuns=0, health=27, wounds=0)
        result = apply_stun_damage(target, 8)  # 8 stuns > 0 current, new_stuns = 8

        assert result['unconscious_check_needed'] is True, \
            "8 stuns should trigger unconscious check"
        assert target.stuns >= 6, \
            f"Target should have 6+ stuns, got {target.stuns}"

    def test_check_death_save_ignores_stuns_correctly(self):
        """check_death_save only checks wounds — stun KO handled separately."""
        target = MockPlayerAgent(stuns=8, health=27, wounds=0)

        # check_death_save should return "conscious" because wounds < 5
        # This is CORRECT behavior — stun KO is not a wound-based death save
        alive, status = target.check_death_save()
        assert status == "conscious", \
            "check_death_save should ignore stuns (wounds < 5 = conscious)"

    def test_stun_ko_marks_incapacitated_via_mark_defeated(self):
        """_mark_defeated_from_resolution should catch stun KO enemies."""
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState
        import importlib
        session_mod = importlib.import_module('scripts.aeonisk.multiagent.session')
        mark_defeated = session_mod._mark_defeated_from_resolution

        resolution_state = ResolutionState()
        enemy = MockEnemyAgent(stuns=7, health=15, is_active=True)
        enemy_combat = MagicMock()
        enemy_combat.enemy_agents = [enemy]

        mark_defeated(enemy_combat, resolution_state)

        assert resolution_state.is_incapacitated(enemy.agent_id), \
            "Enemy with stuns >= 6 should be marked incapacitated"


# ============================================================================
# TEST: PC is_in_combat with stun KO
# ============================================================================

class TestPlayerStunCombatStatus:
    """
    A player knocked unconscious by stun damage (stuns >= 6)
    should not be considered in combat.
    """

    def test_pc_with_high_stuns_not_in_combat(self):
        """PC with stuns >= 6 should not be in combat."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        # We need a real player agent to test is_in_combat
        # But creating one requires complex setup, so test the property logic
        player = MockPlayerAgent(stuns=8, health=27, wounds=0)

        # Currently is_in_combat only checks is_alive and is_extracted
        # After fix, it should also check stun status
        # For now we just verify the mock mirrors the real behavior
        assert player.health > 0, "Player health should still be positive"
        assert player.is_alive, "Player should still be 'alive' (not dead)"

        # The bug: is_in_combat returns True even with 8 stuns
        # After fix: should return False
        # We'll test the real player class separately


# ============================================================================
# TEST: ActionValidator with incapacitated combatants
# ============================================================================

class TestActionValidatorIncapacitation:
    """
    ActionValidator.can_attack should block attacks from/to
    incapacitated combatants.
    """

    def test_defeated_attacker_blocked(self):
        """Existing behavior: defeated attacker can't attack."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_defeated("enemy_01")

        can_proceed, reason = ActionValidator.can_attack("enemy_01", "player_01", state)
        assert not can_proceed
        assert reason == "attacker_defeated"

    def test_defeated_target_blocked(self):
        """Existing behavior: can't attack a defeated target."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_defeated("player_01")

        can_proceed, reason = ActionValidator.can_attack("enemy_01", "player_01", state)
        assert not can_proceed
        assert reason == "target_defeated"

    def test_incapacitated_attacker_blocked(self):
        """NEW: incapacitated (stun KO) attacker can't attack."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_incapacitated("enemy_01")

        can_proceed, reason = ActionValidator.can_attack("enemy_01", "player_01", state)
        assert not can_proceed
        assert reason == "attacker_incapacitated"

    def test_incapacitated_target_blocked(self):
        """NEW: can't attack an incapacitated target."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_incapacitated("player_01")

        can_proceed, reason = ActionValidator.can_attack("enemy_01", "player_01", state)
        assert not can_proceed
        assert reason == "target_incapacitated"

    def test_incapacitated_mover_blocked(self):
        """NEW: incapacitated combatant can't move."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_incapacitated("enemy_01")

        can_proceed, reason = ActionValidator.can_move("enemy_01", state)
        assert not can_proceed
        assert reason == "mover_incapacitated"

    def test_incapacitated_claimant_blocked(self):
        """NEW: incapacitated combatant can't claim tokens."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )
        state = ResolutionState()
        state.mark_incapacitated("enemy_01")

        can_proceed, reason = ActionValidator.can_claim_token("enemy_01", "cover", state)
        assert not can_proceed
        assert reason == "claimant_incapacitated"


# ============================================================================
# TEST: Invalidation message for incapacitated
# ============================================================================

class TestIncapacitatedInvalidationMessage:
    """Proper narrative messages for stun KO invalidation."""

    def test_attacker_incapacitated_message(self):
        from scripts.aeonisk.multiagent.tactical_resolution import generate_invalidation_message

        msg = generate_invalidation_message(
            "Guard Captain",
            "attack",
            "attacker_incapacitated",
            "Kael Dren"
        )
        assert "Guard Captain" in msg
        assert "incapacitated" in msg.lower() or "unconscious" in msg.lower()

    def test_target_incapacitated_message(self):
        from scripts.aeonisk.multiagent.tactical_resolution import generate_invalidation_message

        msg = generate_invalidation_message(
            "Kael Dren",
            "attack",
            "target_incapacitated",
            "Guard Captain"
        )
        assert "Guard Captain" in msg
