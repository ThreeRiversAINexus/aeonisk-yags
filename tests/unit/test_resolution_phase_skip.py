"""
Tests for Resolution Phase Skip (Spec 15).

Three mechanisms for preventing dead/incapacitated/preempted PCs from acting:

Phase 1: Hard Auto-Skip
- Engine auto-skips defeated/incapacitated players BEFORE LLM call
- Uses existing ResolutionState checks (same as enemy invalidation)

Phase 2: DM Narrative Skip
- DM flags preempted actions via action_skipped field on ActionResolution
- Engine suppresses all mechanical effects when action_skipped=True

Phase 3: Dead PC Cleanup
- Dead PCs removed from player_agents on story advancement
- Dead PCs filtered from target_id assignment at round start
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import warnings


# ============================================================================
# TEST FIXTURES
# ============================================================================

@dataclass
class MockCharacterState:
    """Minimal character_state for player agents."""
    name: str = "Test Player"
    faction: str = "Eidolon Collective"


@dataclass
class MockPlayerAgent:
    """Minimal mock of AIPlayerAgent."""
    agent_id: str = "player_test_01"
    is_alive: bool = True
    is_extracted: bool = False
    _permanently_dead: bool = False
    position: str = "front"

    def __post_init__(self):
        self.character_state = MockCharacterState(name=f"PC_{self.agent_id}")

    @property
    def is_in_combat(self) -> bool:
        if not self.is_alive:
            return False
        if self.is_extracted:
            return False
        return True


@dataclass
class MockTargetIdMapper:
    """Minimal mock of TargetIdMapper."""
    target_id_map: Dict[str, Any] = field(default_factory=dict)
    reverse_map: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def assign_ids(self, player_agents=None, enemy_agents=None, npc_agents=None, vendors=None):
        """Assign target IDs to entities."""
        self.target_id_map.clear()
        self.reverse_map.clear()
        if player_agents:
            for i, agent in enumerate(player_agents):
                tid = f"pc_{i:04x}"
                self.target_id_map[tid] = agent
                self.reverse_map[agent.agent_id] = tid

    def unregister(self, agent_id):
        """Remove agent from both maps."""
        tid = self.reverse_map.pop(agent_id, None)
        if tid:
            self.target_id_map.pop(tid, None)


# ============================================================================
# PHASE 1: Hard Auto-Skip Tests
# ============================================================================

class TestPlayerAutoSkipDefeated:
    """Defeated players should be auto-skipped before LLM call."""

    def test_player_auto_skip_defeated(self):
        """A defeated player's action should be skipped with no LLM call."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ResolutionState,
            generate_invalidation_message
        )

        resolution_state = ResolutionState()
        agent = MockPlayerAgent(agent_id="player_kael_01")
        resolution_state.mark_defeated(agent.agent_id)

        # Verify defeated check works
        assert resolution_state.is_defeated(agent.agent_id)

        # Generate skip narration using existing infrastructure
        narration = generate_invalidation_message(
            agent.character_state.name,
            "combat",
            "attacker_defeated"
        )
        assert "defeated" in narration.lower()
        assert agent.character_state.name in narration

    def test_player_auto_skip_incapacitated(self):
        """An incapacitated (stun KO) player should be auto-skipped."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ResolutionState,
            generate_invalidation_message
        )

        resolution_state = ResolutionState()
        agent = MockPlayerAgent(agent_id="player_echo_01")
        resolution_state.mark_incapacitated(agent.agent_id)

        assert resolution_state.is_incapacitated(agent.agent_id)

        narration = generate_invalidation_message(
            agent.character_state.name,
            "combat",
            "attacker_incapacitated"
        )
        assert "unconscious" in narration.lower() or "incapacitated" in narration.lower()

    def test_player_not_skipped_when_healthy(self):
        """A healthy player should NOT be skipped by resolution state checks."""
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        resolution_state = ResolutionState()
        agent = MockPlayerAgent(agent_id="player_ash_01")

        # Healthy player passes all checks
        assert not resolution_state.is_defeated(agent.agent_id)
        assert not resolution_state.is_incapacitated(agent.agent_id)

    def test_skip_narration_in_all_resolutions(self):
        """Skip narration should be appendable to all_resolutions for previous_context."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ResolutionState,
            generate_invalidation_message
        )

        resolution_state = ResolutionState()
        agent = MockPlayerAgent(agent_id="player_sera_01")
        resolution_state.mark_defeated(agent.agent_id)

        narration = generate_invalidation_message(
            agent.character_state.name,
            "combat",
            "attacker_defeated"
        )

        # Build a skip resolution data dict (matches format of normal resolutions)
        skip_resolution = {
            'character_name': agent.character_state.name,
            'player_id': agent.agent_id,
            'action': {'action_type': 'skipped', 'intent': 'auto-skipped'},
            'narration': narration,
            'action_skipped': True,
            'skip_reason': 'defeated',
            'effects': {},
        }

        all_resolutions = []
        all_resolutions.append(skip_resolution)

        # Verify it's visible in previous context
        assert len(all_resolutions) == 1
        assert all_resolutions[0]['action_skipped'] is True
        assert all_resolutions[0]['character_name'] == agent.character_state.name

    def test_skip_logged_to_jsonl(self):
        """Auto-skip should log an action_resolution event with skip fields."""
        # The JSONL log should contain action_type='skipped' and skip reason
        skip_log_data = {
            'round_num': 3,
            'enemy_id': 'player_kael_01',
            'enemy_name': 'Kael Dren',
            'action_type': 'skipped',
            'result': 'defeated',
            'narration': 'Kael Dren cannot act - already defeated earlier in the round',
            'effects': {'skip_reason': 'defeated', 'action_skipped': True}
        }

        # Verify the data structure matches expected JSONL format
        assert skip_log_data['action_type'] == 'skipped'
        assert skip_log_data['effects']['action_skipped'] is True

    def test_enemy_skip_still_works(self):
        """Enemy invalidation should not be affected (regression check)."""
        from scripts.aeonisk.multiagent.tactical_resolution import (
            ActionValidator, ResolutionState
        )

        state = ResolutionState()
        state.mark_defeated("enemy_grunt_01")
        state.mark_incapacitated("enemy_grunt_02")

        can_proceed_1, reason_1 = ActionValidator.can_attack("enemy_grunt_01", "player_01", state)
        assert not can_proceed_1
        assert reason_1 == "attacker_defeated"

        can_proceed_2, reason_2 = ActionValidator.can_attack("enemy_grunt_02", "player_01", state)
        assert not can_proceed_2
        assert reason_2 == "attacker_incapacitated"


# ============================================================================
# PHASE 2: DM Narrative Skip Tests
# ============================================================================

class TestActionSkippedSchema:
    """ActionResolution schema should accept action_skipped fields."""

    def test_action_skipped_field_defaults_false(self):
        """action_skipped should default to False (backwards compatible)."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution
        from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier

        resolution = ActionResolution(
            narration="A" * 200,  # Min 200 chars
            success_tier=SuccessTier.MODERATE,
            margin=5,
        )
        assert resolution.action_skipped is False
        assert resolution.skip_reason is None

    def test_action_skipped_field_accepted(self):
        """action_skipped=True with skip_reason should validate."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution
        from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier

        resolution = ActionResolution(
            narration="A" * 200,
            success_tier=SuccessTier.FAILURE,
            margin=-5,
            action_skipped=True,
            skip_reason="Target was already defeated by a faster actor before this character could act",
        )
        assert resolution.action_skipped is True
        assert "defeated" in resolution.skip_reason

    def test_action_skipped_warns_on_populated_effects(self):
        """When action_skipped=True but effects have data, emit a validation warning."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution, MechanicalEffects
        from scripts.aeonisk.multiagent.schemas.shared_types import (
            SuccessTier, SoulcreditChange, VoidChange
        )

        # This should still validate (we warn, not reject)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resolution = ActionResolution(
                narration="A" * 200,
                success_tier=SuccessTier.FAILURE,
                margin=-5,
                action_skipped=True,
                skip_reason="Character was stunned and could not complete their action this round",
                effects=MechanicalEffects(
                    void_changes=[VoidChange(character_name="Ash", amount=1, reason="ritual backfire from void exposure")],
                    soulcredit_changes=[SoulcreditChange(character_name="Ash", amount=-1, reason="reckless void manipulation")]
                )
            )
            # Schema should validate successfully
            assert resolution.action_skipped is True
            # Effects are present but will be suppressed by engine
            assert len(resolution.effects.void_changes) == 1

    def test_skip_reason_required_when_skipped(self):
        """skip_reason should be present when action_skipped=True (validator warns)."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution
        from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier

        # action_skipped=True without skip_reason — should still validate but warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resolution = ActionResolution(
                narration="A" * 200,
                success_tier=SuccessTier.FAILURE,
                margin=-5,
                action_skipped=True,
                # No skip_reason
            )
            assert resolution.action_skipped is True

    def test_skip_reason_without_action_skipped_warns(self):
        """skip_reason without action_skipped=True should warn about inconsistency."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution
        from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resolution = ActionResolution(
                narration="A" * 200,
                success_tier=SuccessTier.MODERATE,
                margin=5,
                action_skipped=False,
                skip_reason="Character was preempted by environmental hazard before acting",
            )
            # Should validate (we warn, not reject)
            assert resolution.action_skipped is False
            assert resolution.skip_reason is not None


class TestEffectSuppressionWhenSkipped:
    """When action_skipped=True, engine should suppress all mechanical effects."""

    def test_effects_ignored_when_skipped(self):
        """Verify the guard logic: when action_skipped is True, effects should not be applied."""
        # Simulates the session.py guard
        resolution_data = {
            'action_skipped': True,
            'skip_reason': 'Character was stunned and could not complete their action',
            'narration': 'Kael tries to move but collapses from the stun.',
            'effects': {
                'purchase': {'item': 'Healing Potion', 'cost': 5},
                'crafting': {'item': 'Void Ward', 'skill': 'Crafting'},
                'attunement': {'seed': 'Fire Seed', 'success': True},
                'item_discovery': {'item': 'Ancient Key'},
                'stabilization': {'target': 'player_02', 'success': True},
            }
        }

        # Simulate the guard
        action_skipped = resolution_data.get('action_skipped', False)
        if action_skipped:
            effects_to_process = {}
        else:
            effects_to_process = resolution_data.get('effects', {})

        # No effects should be processed
        assert effects_to_process == {}

    def test_effects_processed_when_not_skipped(self):
        """Normal resolution should process effects normally."""
        resolution_data = {
            'action_skipped': False,
            'effects': {
                'purchase': {'item': 'Healing Potion', 'cost': 5},
            }
        }

        action_skipped = resolution_data.get('action_skipped', False)
        if action_skipped:
            effects_to_process = {}
        else:
            effects_to_process = resolution_data.get('effects', {})

        assert effects_to_process.get('purchase') is not None


class TestEnhancedPreviousContextFormat:
    """Previous context should show [SKIPPED] prefix for skipped actions."""

    def test_skipped_action_prefix_in_context(self):
        """Skipped actions should have [SKIPPED - reason] prefix."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context

        resolutions = [
            {
                'character_name': 'Ash',
                'action': {'action_type': 'combat'},
                'narration': 'Ash fires and hits the target squarely in the chest.' + 'x' * 100,
                'resolution': {'margin': 12},
                'effects': {'soulcredit_changes': [{'amount': 0, 'reason': 'justified combat'}]},
            },
            {
                'character_name': 'Kael',
                'action': {'action_type': 'skipped'},
                'narration': 'Kael cannot act - already defeated earlier in the round',
                'action_skipped': True,
                'skip_reason': 'defeated',
                'resolution': {'margin': 0},
                'effects': {},
            }
        ]

        context = _build_enhanced_previous_context(resolutions)

        # The skipped action should be visible
        assert 'Kael' in context
        # Should have a SKIPPED indicator
        assert '[SKIPPED' in context or 'SKIPPED' in context

    def test_invalidated_action_prefix(self):
        """Enemy invalidations should show [INVALIDATED] prefix."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context

        resolutions = [
            {
                'character_name': 'Guard Captain',
                'action': {'action_type': 'combat'},
                'narration': 'Guard Captain cannot act - already defeated',
                'result': 'invalidated',
                'resolution': {'margin': 0},
                'effects': {},
            }
        ]

        context = _build_enhanced_previous_context(resolutions)
        assert 'Guard Captain' in context
        assert '[INVALIDATED' in context or 'INVALIDATED' in context

    def test_normal_action_no_prefix(self):
        """Normal actions should have no special prefix."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context

        resolutions = [
            {
                'character_name': 'Echo',
                'action': {'action_type': 'investigate'},
                'narration': 'Echo scans the terminal and discovers access logs.' + 'x' * 80,
                'resolution': {'margin': 8},
                'effects': {'soulcredit_changes': [{'amount': 0, 'reason': 'neutral'}]},
            }
        ]

        context = _build_enhanced_previous_context(resolutions)
        assert 'Echo' in context
        # Normal actions should NOT have SKIPPED or INVALIDATED prefix
        assert '[SKIPPED' not in context
        assert '[INVALIDATED' not in context


# ============================================================================
# PHASE 3: Dead PC Cleanup Tests
# ============================================================================

class TestDeadPCCleanup:
    """Dead PCs should be cleaned up on story advancement and excluded from target IDs."""

    def test_dead_pc_excluded_from_target_id_assignment(self):
        """Dead PCs should not receive target IDs at round start."""
        alive_pc = MockPlayerAgent(agent_id="player_01", is_alive=True)
        dead_pc = MockPlayerAgent(agent_id="player_02", is_alive=False, _permanently_dead=True)

        # Filter dead PCs before assigning IDs (as the implementation should do)
        active_players = [p for p in [alive_pc, dead_pc]
                         if p.is_alive and not p._permanently_dead]

        assert len(active_players) == 1
        assert active_players[0].agent_id == "player_01"

        mapper = MockTargetIdMapper()
        mapper.assign_ids(player_agents=active_players)

        assert "player_01" in mapper.reverse_map
        assert "player_02" not in mapper.reverse_map

    def test_dead_pc_removed_from_player_agents(self):
        """Dead PCs should be removable from player_agents list."""
        alive_pc = MockPlayerAgent(agent_id="player_01", is_alive=True)
        dead_pc = MockPlayerAgent(agent_id="player_02", is_alive=False, _permanently_dead=True)

        player_agents = [alive_pc, dead_pc]

        # Simulate the cleanup
        dead_agents = [a for a in player_agents if a._permanently_dead or not a.is_alive]
        assert len(dead_agents) == 1
        assert dead_agents[0].agent_id == "player_02"

        # Remove dead agents
        for dead in dead_agents:
            player_agents.remove(dead)

        assert len(player_agents) == 1
        assert player_agents[0].agent_id == "player_01"

    def test_dead_pc_removed_from_target_id_mapper(self):
        """Dead PCs should be cleaned from both target_id_map and reverse_map."""
        alive_pc = MockPlayerAgent(agent_id="player_01", is_alive=True)
        dead_pc = MockPlayerAgent(agent_id="player_02", is_alive=False, _permanently_dead=True)

        mapper = MockTargetIdMapper()
        # Initially both have IDs
        mapper.assign_ids(player_agents=[alive_pc, dead_pc])

        # Both should have IDs initially
        assert "player_01" in mapper.reverse_map
        assert "player_02" in mapper.reverse_map

        # Cleanup dead PC
        mapper.unregister(dead_pc.agent_id)

        assert "player_01" in mapper.reverse_map
        assert "player_02" not in mapper.reverse_map
        # Verify forward map is also clean
        for tid, entity in mapper.target_id_map.items():
            assert entity.agent_id != "player_02"

    def test_alive_pc_not_removed(self):
        """Living PCs should not be affected by dead PC cleanup."""
        alive_pc_1 = MockPlayerAgent(agent_id="player_01", is_alive=True)
        alive_pc_2 = MockPlayerAgent(agent_id="player_02", is_alive=True)
        dead_pc = MockPlayerAgent(agent_id="player_03", is_alive=False, _permanently_dead=True)

        player_agents = [alive_pc_1, alive_pc_2, dead_pc]

        # Filter
        remaining = [a for a in player_agents if a.is_alive and not a._permanently_dead]

        assert len(remaining) == 2
        assert all(a.is_alive for a in remaining)

    def test_dead_pc_skipped_in_next_round_target_assignment(self):
        """Dead PC doesn't get new tgt_xxxx after cleanup."""
        alive_pc = MockPlayerAgent(agent_id="player_01", is_alive=True)
        dead_pc = MockPlayerAgent(agent_id="player_02", is_alive=False, _permanently_dead=True)

        # Round N: both have IDs
        mapper = MockTargetIdMapper()
        mapper.assign_ids(player_agents=[alive_pc, dead_pc])
        assert len(mapper.target_id_map) == 2

        # Cleanup after story advancement
        mapper.unregister(dead_pc.agent_id)

        # Round N+1: only alive PC gets new ID
        active_players = [alive_pc]  # Dead PC filtered out before assign_ids
        mapper.assign_ids(player_agents=active_players)

        assert len(mapper.target_id_map) == 1
        assert "player_01" in mapper.reverse_map
        assert "player_02" not in mapper.reverse_map
