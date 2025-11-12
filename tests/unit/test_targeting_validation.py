"""
Unit tests for targeting validation system.

Tests mechanical correction of DM targeting errors without requiring LLM fallback.
Follows TDD approach - tests written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock
from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


class TestTargetingValidationMechanical:
    """Test mechanical targeting validation (no LLM)."""

    @pytest.fixture
    def setup_mapper(self):
        """Create TargetIDMapper with mock entities."""
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        mapper = TargetIDMapper()
        mapper.enable()

        # Mock player agent
        mock_player = Mock()
        mock_player.agent_id = "player_01"
        mock_player.character_state = Mock()
        mock_player.character_state.name = "Ash Vex"
        mock_player.character_state.max_health = 20
        mock_player.character_state.health = 15

        # Mock enemy agent (no character_state, just name)
        mock_enemy = Mock(spec=['agent_id', 'name', 'max_health', 'health'])
        mock_enemy.agent_id = "enemy_01"
        mock_enemy.name = "Heavy Gunner"
        mock_enemy.max_health = 12
        mock_enemy.health = 8

        # Mock NPC agent (no character_state, just name)
        mock_npc = Mock(spec=['agent_id', 'name'])
        mock_npc.agent_id = "npc_01"
        mock_npc.name = "Merchant"

        # Set up bidirectional mapping
        mapper.target_id_map = {
            "tgt_7a3f": mock_player,
            "tgt_9xz2": mock_enemy,
            "tgt_b1c4": mock_npc
        }
        mapper.reverse_map = {
            "player_01": "tgt_7a3f",
            "enemy_01": "tgt_9xz2",
            "npc_01": "tgt_b1c4"
        }

        return mapper

    def test_pattern_a_name_instead_of_id(self, setup_mapper):
        """Pattern A: DM uses character name instead of target ID."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="Ash Vex",  # ❌ Should be tgt_7a3f
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'enemy_01',
            'target': 'tgt_7a3f'  # Correct ID in action
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected is not None
        assert corrected.target == "tgt_7a3f"
        assert error is None

    def test_pattern_a_fuzzy_name_match(self, setup_mapper):
        """Pattern A: DM uses partial/fuzzy name match."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="Ash",  # ❌ Partial name
            base_damage=8,
            soak=2,
            dealt=6
        )

        action = {
            'agent_id': 'enemy_01',
            'target': 'tgt_7a3f'  # Full name "Ash Vex"
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected.target == "tgt_7a3f"

    def test_pattern_a_case_insensitive(self, setup_mapper):
        """Pattern A: DM uses different case."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="ASH VEX",  # ❌ Wrong case
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'enemy_01',
            'target': 'tgt_7a3f'
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected.target == "tgt_7a3f"

    def test_pattern_c_stale_target_id(self, setup_mapper):
        """Pattern C: DM uses stale/nonexistent target ID."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="tgt_old9",  # ❌ Doesn't exist in mapper
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': 'tgt_9xz2'  # Valid target in action
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected is not None
        assert corrected.target == "tgt_9xz2"
        assert error is None

    def test_pattern_d_missing_target(self, setup_mapper):
        """Pattern D: DM omits target field entirely."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="",  # ❌ Empty
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': 'tgt_9xz2'
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected is not None
        assert corrected.target == "tgt_9xz2"
        assert error is None

    def test_valid_targeting_unchanged(self, setup_mapper):
        """Valid targeting should pass through unchanged."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="tgt_7a3f",  # ✅ Valid
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'enemy_01',
            'target': 'tgt_7a3f'
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected.target == "tgt_7a3f"  # Unchanged
        assert error is None

    def test_mechanical_correction_failure_no_declared_target(self, setup_mapper):
        """When mechanical correction fails with no declared target."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="Unknown Character",  # Can't match to any target
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': None  # No declared target to fall back to
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=True  # Allow LLM fallback
        )

        assert is_valid is False
        assert corrected is None
        assert error is not None
        assert "Unknown Character" in error

    def test_mechanical_correction_failure_invalid_declared_target(self, setup_mapper):
        """When declared target is also invalid."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="tgt_old9",  # Stale ID
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': 'tgt_also_old'  # Also stale
        }

        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=True
        )

        assert is_valid is False
        assert corrected is None
        assert error is not None

    def test_targeting_validation_error_raised_when_strict(self, setup_mapper):
        """Should raise exception when allow_llm_fallback=False and correction fails."""
        from scripts.aeonisk.multiagent.targeting_validation import (
            validate_and_correct_targeting,
            TargetingValidationError
        )

        effect = DamageEffect(
            target="Invalid Target",
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': None
        }

        with pytest.raises(TargetingValidationError):
            validate_and_correct_targeting(
                effect=effect,
                declared_action=action,
                target_id_mapper=setup_mapper,
                allow_llm_fallback=False  # Strict mode
            )

    def test_get_entity_name_player(self, setup_mapper):
        """Test entity name extraction for player."""
        from scripts.aeonisk.multiagent.targeting_validation import _get_entity_name

        player = setup_mapper.target_id_map["tgt_7a3f"]
        name = _get_entity_name(player)

        assert name == "Ash Vex"

    def test_get_entity_name_enemy(self, setup_mapper):
        """Test entity name extraction for enemy."""
        from scripts.aeonisk.multiagent.targeting_validation import _get_entity_name

        enemy = setup_mapper.target_id_map["tgt_9xz2"]
        name = _get_entity_name(enemy)

        assert name == "Heavy Gunner"

    def test_get_entity_name_npc(self, setup_mapper):
        """Test entity name extraction for NPC."""
        from scripts.aeonisk.multiagent.targeting_validation import _get_entity_name

        npc = setup_mapper.target_id_map["tgt_b1c4"]
        name = _get_entity_name(npc)

        assert name == "Merchant"

    def test_get_entity_name_unknown(self):
        """Test entity name extraction for unknown entity type."""
        from scripts.aeonisk.multiagent.targeting_validation import _get_entity_name

        # Use spec=[] to prevent Mock from creating attributes
        unknown = Mock(spec=[])
        name = _get_entity_name(unknown)

        assert name == "Unknown"

    def test_mapper_disabled(self):
        """Should handle disabled target mapper gracefully."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        mapper = TargetIDMapper()
        # Don't call enable() - mapper is disabled

        effect = DamageEffect(
            target="tgt_7a3f",
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'player_01',
            'target': 'tgt_7a3f'
        }

        # Should not crash, but validation will fail (no entities in disabled mapper)
        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=mapper,
            allow_llm_fallback=True
        )

        # Disabled mapper means resolve_target returns None
        assert is_valid is False

    def test_enemy_targeting_enemy(self, setup_mapper):
        """Test enemy targeting another enemy (friendly fire)."""
        from scripts.aeonisk.multiagent.targeting_validation import validate_and_correct_targeting

        effect = DamageEffect(
            target="tgt_9xz2",  # Enemy targeting enemy
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'enemy_02',
            'target': 'tgt_9xz2'
        }

        # Valid targeting (even if unusual gameplay-wise)
        is_valid, corrected, error = validate_and_correct_targeting(
            effect=effect,
            declared_action=action,
            target_id_mapper=setup_mapper,
            allow_llm_fallback=False
        )

        assert is_valid is True
        assert corrected.target == "tgt_9xz2"
