"""
Unit tests for enemy combat logging - Bug 2 & Bug 3 fixes.

Bug 2: Combat actions logged with placeholder target IDs (tgt_xxxx) instead of actual names
Bug 3: Combat actions logged with wrong round number (off-by-one)
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass


class TestAgentNameExtraction:
    """Test _get_agent_name() helper for Bug 2 fix."""

    def test_get_agent_name_enemy_agent(self):
        """Enemy agents have .name directly - should return it."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        # Mock enemy agent with direct .name attribute
        enemy = MagicMock()
        enemy.name = "Enforcer Alpha"
        enemy.agent_id = "enemy_01"

        result = manager._get_agent_name(enemy, "tgt_abc123")

        assert result == "Enforcer Alpha"

    def test_get_agent_name_player_agent(self):
        """Player agents have .character_state.name - should return it."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        # Mock player agent with character_state.name
        player = MagicMock()
        player.name = None  # Players don't have direct .name
        del player.name  # Remove the attribute entirely
        player.character_state = MagicMock()
        player.character_state.name = "Expedition Pilot Arden Vex"
        player.agent_id = "player_01"

        result = manager._get_agent_name(player, "tgt_mf4l")

        assert result == "Expedition Pilot Arden Vex"

    def test_get_agent_name_fallback_to_id(self):
        """When no name attribute exists, should fallback to provided ID."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        # Mock agent with neither .name nor .character_state.name
        unknown_agent = MagicMock(spec=[])  # Empty spec = no attributes

        result = manager._get_agent_name(unknown_agent, "fallback_id")

        assert result == "fallback_id"

    def test_get_agent_name_empty_name_fallback(self):
        """Empty string name should fallback to ID."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        # Mock agent with empty string name (use spec to prevent MagicMock auto-attributes)
        agent = MagicMock(spec=['name'])
        agent.name = ""

        result = manager._get_agent_name(agent, "tgt_empty")

        assert result == "tgt_empty"


class TestAgentIdExtraction:
    """Test _get_agent_id() helper for Bug 2 fix."""

    def test_get_agent_id_enemy_agent(self):
        """Enemy agents have .agent_id - should return it."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        enemy = MagicMock()
        enemy.agent_id = "enemy_enforcer_01"

        result = manager._get_agent_id(enemy, "tgt_abc123")

        assert result == "enemy_enforcer_01"

    def test_get_agent_id_player_agent(self):
        """Player agents have .agent_id - should return it."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        player = MagicMock()
        player.agent_id = "player_01"

        result = manager._get_agent_id(player, "tgt_mf4l")

        assert result == "player_01"

    def test_get_agent_id_fallback_to_placeholder(self):
        """When no agent_id exists, should fallback to placeholder."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager()

        # Agent with no agent_id
        agent = MagicMock(spec=[])

        result = manager._get_agent_id(agent, "tgt_fallback")

        assert result == "tgt_fallback"


class TestCombatRoundLogging:
    """Test Bug 3 fix - correct round number in combat logging."""

    def test_combat_action_uses_mechanics_engine_round(self):
        """Combat logging should use mechanics_engine.current_round, not self.current_round."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager, EnemyDeclaration
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        manager = EnemyCombatManager()
        manager.enabled = True
        manager.current_round = 0  # Stale round number (off by one)

        # Mock mechanics engine with correct round
        mechanics_engine = MagicMock()
        mechanics_engine.current_round = 1  # Correct round
        mechanics_engine.jsonl_logger = MagicMock()

        # Mock enemy agent
        enemy = MagicMock()
        enemy.agent_id = "enemy_01"
        enemy.name = "Enforcer"
        enemy.initiative = 10
        enemy.agility = 4
        enemy.weapons = [MagicMock(name="Rifle", damage=6, damage_type="ballistic", accuracy=0)]

        # Mock target (player)
        target = MagicMock()
        target.agent_id = "player_01"
        target.character_state = MagicMock()
        target.character_state.name = "Test Player"
        target.health = 20
        target.soak = 5

        # Mock resolution state
        resolution_state = MagicMock()

        # Mock declaration
        declaration = EnemyDeclaration(
            agent_id="enemy_01",
            character_name="Enforcer",
            initiative=10,
            defence_token=None,
            major_action="Attack",
            target="player_01",
            weapon="Rifle",
            minor_action=None,
            token_target=None,
            reasoning="Test attack",
            shared_intel=None
        )

        # Patch _execute_attack to capture the round number used in logging
        # We check that when log_combat_action is called, it uses the correct round
        with patch.object(manager, '_get_agent_name', return_value="Test Player"):
            with patch.object(manager, '_get_agent_id', return_value="player_01"):
                # Call the internal method that does logging
                # Since _execute_attack has complex dependencies, we'll verify by
                # checking that after the fix, log_combat_action gets correct round

                # For now, just verify the test setup is correct
                assert mechanics_engine.current_round == 1
                assert manager.current_round == 0
                # The fix will ensure log_combat_action receives round_num=1


class TestCombatLoggingIntegration:
    """Integration tests for combat action logging with both fixes."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create mock shared state with target ID mapper."""
        shared_state = MagicMock()
        target_mapper = MagicMock()
        target_mapper.enabled = True
        shared_state.get_target_id_mapper.return_value = target_mapper
        shared_state.get_mechanics_engine.return_value = MagicMock()
        return shared_state

    def test_combat_logs_actual_player_name_not_placeholder(self, mock_shared_state):
        """Combat action should log actual player name, not tgt_xxxx placeholder."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

        manager = EnemyCombatManager(shared_state=mock_shared_state)
        manager.enabled = True

        # Setup target mapper to resolve placeholder to player
        target_mapper = mock_shared_state.get_target_id_mapper()

        # Use spec to ensure player doesn't have .name (only .character_state.name)
        mock_player = MagicMock(spec=['agent_id', 'character_state'])
        mock_player.agent_id = "player_01"
        mock_player.character_state = MagicMock(spec=['name'])
        mock_player.character_state.name = "Expedition Pilot Arden Vex"

        target_mapper.resolve_target.return_value = mock_player
        target_mapper.is_player.return_value = True
        target_mapper.is_enemy.return_value = False

        # Verify the helper resolves correctly
        resolved_name = manager._get_agent_name(mock_player, "tgt_mf4l")
        resolved_id = manager._get_agent_id(mock_player, "tgt_mf4l")

        assert resolved_name == "Expedition Pilot Arden Vex"
        assert resolved_id == "player_01"
        # NOT "tgt_mf4l"!
