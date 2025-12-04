"""
Unit tests for attacker/weapon context in damage effect logging.

Tests that _process_structured_damage_effects logs correct attacker info
instead of "Unknown Weapon" / "Unknown Attacker" when context is provided.

Root cause: Fallback damage logging at dm.py:296-307 didn't receive
player action context, so it logged hardcoded "Unknown" values.

Fix: Pass attacker context through to the logging function.
"""

import pytest
from unittest.mock import Mock, MagicMock, call
from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


class TestDamageLoggingAttackerContext:
    """Tests for attacker/weapon context in combat_action logging."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock SharedState with target ID mapper."""
        shared = Mock()

        # Create mock entity for target resolution
        mock_entity = Mock()
        mock_entity.agent_id = "enemy_grunt_1234"
        mock_entity.name = "Enemy Grunt #1"
        mock_entity.health = 30
        mock_entity.max_health = 30
        mock_entity.wounds = 0
        mock_entity.stun = 0
        mock_entity.soak = 5
        mock_entity.barriers = []
        mock_entity.status_effects = []  # No active barriers/shields
        # Mock take_damage method to return damage taken
        mock_entity.take_damage = Mock(return_value=10)

        # Mock target ID mapper
        mapper = Mock()
        mapper.enabled = True
        # resolve_target should return an entity, not a tuple
        mapper.resolve_target = Mock(return_value=mock_entity)
        mapper.is_player = Mock(return_value=False)  # Not friendly fire
        mapper.get_combatant_info = Mock(return_value={
            'id': 'enemy_grunt_1234',
            'name': 'Enemy Grunt #1',
            'type': 'enemy'
        })
        shared.get_target_id_mapper = Mock(return_value=mapper)

        # Mock get_entity for damage application
        shared.get_entity = Mock(return_value=mock_entity)

        # Mock enemy_combat (not used in this path but needs to exist)
        shared.enemy_combat = None

        return shared

    @pytest.fixture
    def mock_mechanics_with_logger(self):
        """Create a mock mechanics engine with JSONL logger."""
        mechanics = Mock()
        mechanics.jsonl_logger = Mock()
        mechanics.jsonl_logger.log_combat_action = Mock()
        return mechanics

    def test_logs_attacker_info_when_provided(self, mock_shared_state, mock_mechanics_with_logger):
        """When attacker context is provided, log_combat_action should use it."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        # Create damage effect
        damage_effects = [
            DamageEffect(
                target="tgt_1234",
                base_damage=15,
                dealt=10,
                soak=5
            )
        ]

        # Call with attacker context (NEW PARAMETERS)
        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=mock_shared_state,
            current_round=1,
            mechanics=mock_mechanics_with_logger,
            attacker_id="player_01",
            attacker_name="Ash Kordell",
            weapon="Void Blade"
        )

        # Verify log_combat_action was called with correct attacker info
        mock_mechanics_with_logger.jsonl_logger.log_combat_action.assert_called()
        call_kwargs = mock_mechanics_with_logger.jsonl_logger.log_combat_action.call_args

        # Should NOT use "Unknown" values
        assert call_kwargs.kwargs['attacker_id'] != "unknown", \
            f"Expected specific attacker_id, got: {call_kwargs.kwargs['attacker_id']}"
        assert call_kwargs.kwargs['attacker_name'] != "Unknown Attacker", \
            f"Expected specific attacker_name, got: {call_kwargs.kwargs['attacker_name']}"
        assert call_kwargs.kwargs['weapon'] != "Unknown Weapon", \
            f"Expected specific weapon, got: {call_kwargs.kwargs['weapon']}"

        # Should use provided values
        assert call_kwargs.kwargs['attacker_id'] == "player_01"
        assert call_kwargs.kwargs['attacker_name'] == "Ash Kordell"
        assert call_kwargs.kwargs['weapon'] == "Void Blade"

    def test_defaults_to_unknown_when_context_not_provided(self, mock_shared_state, mock_mechanics_with_logger):
        """When no attacker context provided, should still work with Unknown defaults."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        damage_effects = [
            DamageEffect(
                target="tgt_1234",
                base_damage=15,
                dealt=10,
                soak=5
            )
        ]

        # Call WITHOUT attacker context (backwards compatibility)
        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=mock_shared_state,
            current_round=1,
            mechanics=mock_mechanics_with_logger
            # No attacker_id, attacker_name, weapon provided
        )

        # Should still work, using defaults
        mock_mechanics_with_logger.jsonl_logger.log_combat_action.assert_called()
        call_kwargs = mock_mechanics_with_logger.jsonl_logger.log_combat_action.call_args

        # Defaults to Unknown (backwards compatible behavior)
        assert call_kwargs.kwargs['attacker_id'] == "unknown"
        assert call_kwargs.kwargs['attacker_name'] == "Unknown Attacker"
        assert call_kwargs.kwargs['weapon'] == "Unknown Weapon"

    def test_logs_weapon_from_action_context(self, mock_shared_state, mock_mechanics_with_logger):
        """Weapon should be extracted from action dict when available."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        damage_effects = [
            DamageEffect(
                target="tgt_1234",
                base_damage=20,
                dealt=15,
                soak=5
            )
        ]

        # Simulate combat action with rifle
        _process_structured_damage_effects(
            damage_effects=damage_effects,
            shared_state=mock_shared_state,
            current_round=2,
            mechanics=mock_mechanics_with_logger,
            attacker_id="player_02",
            attacker_name="Jace Kordell",
            weapon="Void Rifle"
        )

        call_kwargs = mock_mechanics_with_logger.jsonl_logger.log_combat_action.call_args
        assert call_kwargs.kwargs['weapon'] == "Void Rifle"
