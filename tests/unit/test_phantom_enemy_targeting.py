"""Tests for phantom enemy targeting prevention (Layer 2).

When enemy combat is enabled but all enemies are cleared, the player's
entity list should include a "NO TARGETABLE ENEMIES" marker to prevent
the player LLM from declaring COMBAT against non-existent hostiles.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestEntityListNoEnemyMarker:
    """Test that _format_entities_present() shows 'no enemies' marker when appropriate."""

    def _make_player_agent(self, enemy_combat=None, player_agents=None, npc_agents=None):
        """Create a minimal AIPlayerAgent with mocked shared_state."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        # Build a minimal shared_state
        shared_state = MagicMock()
        shared_state.player_agents = player_agents or []
        shared_state.npc_agents = npc_agents or []
        shared_state.enemy_combat = enemy_combat
        shared_state.target_id_mapper = None
        shared_state.current_env_objects = []

        # Create a minimal AIPlayerAgent without full init
        agent = object.__new__(AIPlayerAgent)
        agent.agent_id = "player_1"
        agent.shared_state = shared_state

        return agent

    def _make_enemy_combat(self, enabled=True, enemies=None):
        """Create a mock enemy_combat object."""
        ec = MagicMock()
        ec.enabled = enabled
        ec.enemy_agents = enemies or []
        return ec

    def _make_active_enemy(self, name="Guard", agent_id="enemy_1", health=10, max_health=10):
        """Create a mock enemy agent."""
        enemy = MagicMock()
        enemy.name = name
        enemy.agent_id = agent_id
        enemy.health = health
        enemy.max_health = max_health
        enemy.pronouns = None
        enemy.is_defeated = False
        return enemy

    def test_marker_present_when_combat_enabled_and_no_enemies(self):
        """Marker should appear when enemy combat is active but all enemies are cleared."""
        enemy_combat = self._make_enemy_combat(enabled=True, enemies=[])
        agent = self._make_player_agent(enemy_combat=enemy_combat)

        with patch("scripts.aeonisk.multiagent.enemy_spawner.get_active_enemies", return_value=[]):
            result = agent._format_entities_present()

        assert "NO TARGETABLE ENEMIES" in result

    def test_marker_absent_when_active_enemies_exist(self):
        """Marker should NOT appear when there are active (non-defeated) enemies."""
        enemy = self._make_active_enemy()
        enemy_combat = self._make_enemy_combat(enabled=True, enemies=[enemy])
        agent = self._make_player_agent(enemy_combat=enemy_combat)

        with patch("scripts.aeonisk.multiagent.enemy_spawner.get_active_enemies", return_value=[enemy]):
            result = agent._format_entities_present()

        assert "NO TARGETABLE ENEMIES" not in result

    def test_marker_absent_when_enemy_combat_disabled(self):
        """Marker should NOT appear when enemy combat system is disabled."""
        enemy_combat = self._make_enemy_combat(enabled=False)
        agent = self._make_player_agent(enemy_combat=enemy_combat)

        result = agent._format_entities_present()

        assert "NO TARGETABLE ENEMIES" not in result

    def test_marker_absent_when_enemy_combat_is_none(self):
        """Marker should NOT appear when enemy_combat is None (non-combat session)."""
        agent = self._make_player_agent(enemy_combat=None)

        result = agent._format_entities_present()

        assert "NO TARGETABLE ENEMIES" not in result

    def test_marker_text_includes_neutralized_message(self):
        """Marker text should explain that hostiles have been neutralized/withdrawn."""
        enemy_combat = self._make_enemy_combat(enabled=True, enemies=[])
        agent = self._make_player_agent(enemy_combat=enemy_combat)

        with patch("scripts.aeonisk.multiagent.enemy_spawner.get_active_enemies", return_value=[]):
            result = agent._format_entities_present()

        assert "neutralized" in result.lower() or "withdrawn" in result.lower()

    def test_marker_present_with_defeated_enemies_only(self):
        """Marker SHOULD appear when all enemies are defeated (get_active_enemies returns [])."""
        defeated = self._make_active_enemy()
        defeated.is_defeated = True
        enemy_combat = self._make_enemy_combat(enabled=True, enemies=[defeated])
        agent = self._make_player_agent(enemy_combat=enemy_combat)

        # get_active_enemies filters out defeated enemies, returns []
        with patch("scripts.aeonisk.multiagent.enemy_spawner.get_active_enemies", return_value=[]):
            result = agent._format_entities_present()

        assert "NO TARGETABLE ENEMIES" in result
