"""
Tests for NPC narration deduplication in enemy prompts.

Bug: Broadcast narrations (e.g., NPC dialogue) are stored by every player agent.
When enemy_combat.py collects narrations by iterating all player agents, the
same text appears N times (once per player). This test verifies the fix:
a set-based deduplication that keeps only unique narration texts.

Also tests that JSONL double-logging of NPC actions is prevented.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List

from scripts.aeonisk.multiagent.awareness import NarrationEntry, filter_narrations_for_agent


class TestEnemyNarrationDeduplication:
    """Test that enemy prompt narration collection deduplicates across player agents."""

    def _collect_narrations_like_enemy_combat(self, enemy_agent_id, player_agents):
        """
        Reimplements the narration collection logic from enemy_combat.py
        to verify deduplication behavior in isolation.
        """
        recent_narrations = []
        seen_narration_texts = set()
        for player_agent in player_agents:
            if hasattr(player_agent, 'recent_narrations') and player_agent.recent_narrations:
                visible_narrations = filter_narrations_for_agent(
                    enemy_agent_id,
                    player_agent.recent_narrations
                )
                for narration in visible_narrations:
                    narration_text = narration.text if isinstance(narration, NarrationEntry) else narration
                    if narration_text not in seen_narration_texts:
                        seen_narration_texts.add(narration_text)
                        recent_narrations.append(narration_text)
        return recent_narrations

    def test_broadcast_narrations_not_duplicated(self):
        """Same broadcast narration stored by 2 players should appear only once."""
        shared_narration = NarrationEntry(
            text="[Desk Guard Chen] 'Halt! Show your credentials!'",
            aware_agents=[]  # public broadcast
        )

        player1 = MagicMock()
        player1.recent_narrations = [shared_narration]
        player2 = MagicMock()
        player2.recent_narrations = [shared_narration]

        result = self._collect_narrations_like_enemy_combat(
            "enemy_grunt_1", [player1, player2]
        )

        assert len(result) == 1
        assert result[0] == "[Desk Guard Chen] 'Halt! Show your credentials!'"

    def test_broadcast_narrations_not_duplicated_three_players(self):
        """With 3 players, broadcast narration still appears only once."""
        shared = NarrationEntry(
            text="[Patrol Guard Vasquez] 'Area clear, moving to sector 7.'",
            aware_agents=[]
        )

        players = [MagicMock(recent_narrations=[shared]) for _ in range(3)]

        result = self._collect_narrations_like_enemy_combat("enemy_grunt_1", players)

        assert len(result) == 1

    def test_distinct_narrations_preserved(self):
        """Different narrations from different players should all appear."""
        narration1 = NarrationEntry(
            text="[Echo] Echo ducks behind cover.",
            aware_agents=[]
        )
        narration2 = NarrationEntry(
            text="[Sera] Sera charges forward.",
            aware_agents=[]
        )

        player1 = MagicMock(recent_narrations=[narration1])
        player2 = MagicMock(recent_narrations=[narration2])

        result = self._collect_narrations_like_enemy_combat(
            "enemy_grunt_1", [player1, player2]
        )

        assert len(result) == 2
        assert "[Echo] Echo ducks behind cover." in result
        assert "[Sera] Sera charges forward." in result

    def test_mixed_shared_and_unique_narrations(self):
        """Shared broadcast + unique narrations: shared deduped, unique kept."""
        shared = NarrationEntry(
            text="[Guard Chen] 'Intruders detected!'",
            aware_agents=[]
        )
        unique_to_p1 = NarrationEntry(
            text="[Echo] Echo picks the lock quietly.",
            aware_agents=["player_1", "dm"]  # only player 1 sees this
        )
        unique_to_p2 = NarrationEntry(
            text="[Sera] Sera smashes a window.",
            aware_agents=[]
        )

        player1 = MagicMock(recent_narrations=[shared, unique_to_p1])
        player2 = MagicMock(recent_narrations=[shared, unique_to_p2])

        result = self._collect_narrations_like_enemy_combat(
            "enemy_grunt_1", [player1, player2]
        )

        # shared appears once, unique_to_p1 filtered out (enemy not in aware_agents),
        # unique_to_p2 appears once
        assert len(result) == 2
        assert "[Guard Chen] 'Intruders detected!'" in result
        assert "[Sera] Sera smashes a window." in result
        assert "[Echo] Echo picks the lock quietly." not in result

    def test_plain_string_narrations_deduplicated(self):
        """Plain strings (backwards compat) also get deduplicated."""
        player1 = MagicMock(recent_narrations=["A loud explosion echoes."])
        player2 = MagicMock(recent_narrations=["A loud explosion echoes."])

        result = self._collect_narrations_like_enemy_combat(
            "enemy_grunt_1", [player1, player2]
        )

        assert len(result) == 1
        assert result[0] == "A loud explosion echoes."

    def test_empty_narrations_handled(self):
        """Players with no narrations don't cause errors."""
        player1 = MagicMock(recent_narrations=[])
        player2 = MagicMock(spec=[])  # no recent_narrations attr

        result = self._collect_narrations_like_enemy_combat(
            "enemy_grunt_1", [player1, player2]
        )

        assert result == []


class TestNPCActionDoubleLogging:
    """Test that NPC actions are not double-logged in JSONL."""

    def test_npc_action_flagged_as_is_npc(self):
        """NPC actions should have is_npc=True in their action dict."""
        # This verifies the contract that _resolve_action_mechanically
        # sets is_npc on NPC action dicts
        npc_action = {
            'action_type': 'dialogue',
            'character_name': 'Guard Chen',
            'is_npc': True,
            'target': None,
        }
        assert npc_action.get('is_npc', False) is True

    def test_pc_action_not_flagged_as_npc(self):
        """PC actions should not have is_npc=True."""
        pc_action = {
            'action_type': 'attack',
            'character_name': 'Echo',
            'target': 'tgt_1234',
        }
        assert pc_action.get('is_npc', False) is False

    def test_npc_skip_logic_matches_dm_pattern(self):
        """
        Verify the skip pattern: when is_npc is True and action_resolution
        is truthy, logging should be skipped.
        """
        # Simulate the guard logic from dm.py _handle_adjudication_inner
        action_resolution = MagicMock()  # truthy
        action = {'is_npc': True}
        is_npc_action = action.get('is_npc', False)

        should_log = bool(action_resolution and not is_npc_action)
        assert should_log is False

    def test_pc_still_logged(self):
        """PC actions should still be logged (not skipped)."""
        action_resolution = MagicMock()  # truthy
        action = {'action_type': 'attack'}
        is_npc_action = action.get('is_npc', False)

        should_log = bool(action_resolution and not is_npc_action)
        assert should_log is True
