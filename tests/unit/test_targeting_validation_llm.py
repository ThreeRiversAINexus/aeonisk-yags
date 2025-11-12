"""
Unit tests for LLM-assisted targeting validation (Haiku fallback).

Tests async Haiku inference for ambiguous targeting cases that mechanical
correction cannot handle.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from scripts.aeonisk.multiagent.schemas.shared_types import DamageEffect


class TestTargetingValidationLLM:
    """Test LLM-assisted targeting correction using Haiku."""

    @pytest.mark.asyncio
    async def test_llm_inference_stale_id_from_narration(self):
        """Test Haiku infers correct target from DM narration."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(
            target="tgt_old9",  # Stale ID
            base_damage=15,
            soak=0,
            dealt=15,
            damage_type="kinetic"
        )

        action = {
            'agent_id': 'player_02',
            'intent': 'Shoot the heavy gunner with rifle',
            'target': None  # No declared target (mechanical correction failed)
        }

        available_targets = {
            "tgt_7a3f": "Ash Vex (player)",
            "tgt_9xz2": "Heavy Gunner (enemy)",
            "tgt_3bc1": "Scout (enemy)"
        }

        dm_narration = "Your kinetic round punches through the heavy gunner's armor plating, spinning them sideways."

        # Mock both AnthropicModel and Agent
        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model

            mock_result = Mock()
            mock_result.data = Mock()
            mock_result.data.corrected_target = "tgt_9xz2"
            mock_result.data.confidence = "high"
            mock_result.data.reasoning = "DM narration clearly mentions 'heavy gunner' which matches tgt_9xz2"

            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent_instance

            result = await llm_infer_correct_target(
                effect=effect,
                declared_action=action,
                available_targets=available_targets,
                error_description="Target ID tgt_old9 not found in mapper",
                dm_narration=dm_narration
            )

            # Verify Haiku inferred correct target from narration
            assert result.corrected_target == "tgt_9xz2"
            assert result.confidence == "high"
            assert "heavy gunner" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_llm_inference_ambiguous_name(self):
        """Test Haiku handles ambiguous character names."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(
            target="The Scout",  # Ambiguous - which scout?
            base_damage=12,
            soak=0,
            dealt=12
        )

        action = {
            'agent_id': 'player_01',
            'intent': 'Shoot the nearest scout',
            'target': None
        }

        available_targets = {
            "tgt_3bc1": "Scout Alpha (enemy)",
            "tgt_4de2": "Scout Beta (enemy)",
            "tgt_7a3f": "Ash Vex (player)"
        }

        dm_narration = "You aim at the first scout and fire, hitting Scout Alpha in the shoulder."

        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model
            mock_result = Mock()
            mock_result.data = Mock()
            mock_result.data.corrected_target = "tgt_3bc1"
            mock_result.data.confidence = "high"
            mock_result.data.reasoning = "Narration specifies 'Scout Alpha' hit, matching tgt_3bc1"

            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent_instance

            result = await llm_infer_correct_target(
                effect=effect,
                declared_action=action,
                available_targets=available_targets,
                error_description="Target 'The Scout' is not a valid ID",
                dm_narration=dm_narration
            )

            assert result.corrected_target == "tgt_3bc1"
            assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_llm_inference_medium_confidence(self):
        """Test Haiku returns medium confidence for probable but not certain matches."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(
            target="tgt_xyz9",
            base_damage=10,
            soak=0,
            dealt=10
        )

        action = {
            'agent_id': 'enemy_01',
            'intent': 'Attack',
            'target': None
        }

        available_targets = {
            "tgt_7a3f": "Ash Vex (player)",
            "tgt_b2d8": "Riven Kael (player)"
        }

        dm_narration = "The enemy fires at the nearest target."  # Vague narration

        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model
            mock_result = Mock()
            mock_result.data = Mock()
            mock_result.data.corrected_target = "tgt_7a3f"
            mock_result.data.confidence = "medium"
            mock_result.data.reasoning = "Narration is vague, but Ash is mentioned in earlier context"

            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent_instance

            result = await llm_infer_correct_target(
                effect=effect,
                declared_action=action,
                available_targets=available_targets,
                error_description="Target ID tgt_xyz not found",
                dm_narration=dm_narration
            )

            assert result.corrected_target == "tgt_7a3f"
            assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_llm_inference_low_confidence_guessing(self):
        """Test Haiku returns low confidence when truly ambiguous."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(
            target="",
            base_damage=8,
            soak=0,
            dealt=8
        )

        action = {
            'agent_id': 'enemy_02',
            'intent': 'Unknown',
            'target': None
        }

        available_targets = {
            "tgt_1a2b": "Target A (player)",
            "tgt_2c3d": "Target B (player)",
            "tgt_3e4f": "Target C (player)"
        }

        dm_narration = "Something happens."  # Extremely vague

        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model
            mock_result = Mock()
            mock_result.data = Mock()
            mock_result.data.corrected_target = "tgt_1a2b"
            mock_result.data.confidence = "low"
            mock_result.data.reasoning = "No clear indicators, defaulting to first target"

            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent_instance

            result = await llm_infer_correct_target(
                effect=effect,
                declared_action=action,
                available_targets=available_targets,
                error_description="Missing target field",
                dm_narration=dm_narration
            )

            assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_target_correction_result_schema(self):
        """Test TargetCorrectionResult schema validation."""
        from scripts.aeonisk.multiagent.targeting_validation import TargetCorrectionResult

        # Valid result
        result = TargetCorrectionResult(
            corrected_target="tgt_7a3f",
            confidence="high",
            reasoning="Clear match from narration context"
        )

        assert result.corrected_target == "tgt_7a3f"
        assert result.confidence == "high"
        assert len(result.reasoning) >= 20

    @pytest.mark.asyncio
    async def test_target_correction_result_schema_validation_errors(self):
        """Test TargetCorrectionResult rejects invalid data."""
        from scripts.aeonisk.multiagent.targeting_validation import TargetCorrectionResult
        from pydantic import ValidationError

        # Reasoning too short
        with pytest.raises(ValidationError):
            TargetCorrectionResult(
                corrected_target="tgt_7a3f",
                confidence="high",
                reasoning="Too short"  # < 20 chars
            )

        # Reasoning too long
        with pytest.raises(ValidationError):
            TargetCorrectionResult(
                corrected_target="tgt_7a3f",
                confidence="high",
                reasoning="x" * 201  # > 200 chars
            )

    @pytest.mark.asyncio
    async def test_llm_prompt_structure(self):
        """Test that LLM prompt includes all necessary context."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(
            target="tgt_xxxx",  # Invalid but correct format
            base_damage=10,
            soak=0,
            dealt=10,
            damage_type="kinetic"
        )

        action = {
            'agent_id': 'player_01',
            'intent': 'Attack with rifle',
            'target': 'tgt_old'
        }

        available_targets = {
            "tgt_7a3f": "Ash Vex (player)",
            "tgt_9xz2": "Heavy Gunner (enemy)"
        }

        dm_narration = "You fire at the enemy, hitting them center mass."

        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model
            mock_result = Mock()
            mock_result.data = Mock()
            mock_result.data.corrected_target = "tgt_9xz2"
            mock_result.data.confidence = "high"
            mock_result.data.reasoning = "Enemy mentioned in narration matches tgt_9xz2"

            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent_instance

            result = await llm_infer_correct_target(
                effect=effect,
                declared_action=action,
                available_targets=available_targets,
                error_description="Target ID tgt_invalid not found",
                dm_narration=dm_narration
            )

            # Verify Agent was called with correct parameters
            mock_agent_class.assert_called_once()
            call_args = mock_agent_class.call_args

            # Verify AnthropicModel was initialized with Haiku
            mock_model_class.assert_called_once_with('claude-haiku-4')

            # Check that Agent was initialized with mock model
            # First positional arg should be the model
            assert call_args[0][0] == mock_model

            # Verify run() was called (prompt was sent)
            mock_agent_instance.run.assert_called_once()
            prompt_arg = mock_agent_instance.run.call_args[0][0]

            # Verify prompt includes key context
            assert 'player_01' in prompt_arg  # Agent ID
            assert 'Attack with rifle' in prompt_arg  # Intent
            assert 'tgt_7a3f' in prompt_arg  # Available targets
            assert 'tgt_9xz2' in prompt_arg
            assert 'enemy, hitting them center mass' in prompt_arg  # Narration
            assert 'tgt_xxxx' in prompt_arg  # Error context

    @pytest.mark.asyncio
    async def test_llm_api_failure_handling(self):
        """Test graceful handling of LLM API failures."""
        from scripts.aeonisk.multiagent.targeting_validation import llm_infer_correct_target

        effect = DamageEffect(target="tgt_yyyy", base_damage=10, soak=0, dealt=10)
        action = {'agent_id': 'player_01', 'intent': 'Attack', 'target': None}
        available_targets = {"tgt_7a3f": "Ash Vex (player)"}
        dm_narration = "You attack."

        with patch('pydantic_ai.models.anthropic.AnthropicModel') as mock_model_class, \
             patch('pydantic_ai.Agent') as mock_agent_class:

            mock_model = Mock()
            mock_model_class.return_value = mock_model
            # Simulate API failure
            mock_agent_instance = AsyncMock()
            mock_agent_instance.run.side_effect = Exception("API timeout")
            mock_agent_class.return_value = mock_agent_instance

            with pytest.raises(Exception) as exc_info:
                await llm_infer_correct_target(
                    effect=effect,
                    declared_action=action,
                    available_targets=available_targets,
                    error_description="Target invalid",
                    dm_narration=dm_narration
                )

            assert "API timeout" in str(exc_info.value)
