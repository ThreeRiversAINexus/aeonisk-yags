"""
Targeting validation system for DM-generated effects.

Validates and corrects targeting errors in structured output, triggered only when
errors are detected. Uses mechanical correction first, LLM fallback for complex cases.
"""

from typing import Optional, Tuple, Dict, Any
from .schemas.shared_types import DamageEffect
from .target_ids import TargetIDMapper
import logging

logger = logging.getLogger(__name__)


class TargetingValidationError(Exception):
    """Raised when targeting cannot be mechanically corrected and LLM fallback disabled."""
    pass


def validate_and_correct_targeting(
    effect: DamageEffect,
    declared_action: Dict[str, Any],
    target_id_mapper: TargetIDMapper,
    allow_llm_fallback: bool = True
) -> Tuple[bool, Optional[DamageEffect], Optional[str]]:
    """
    Validate effect targeting and attempt mechanical correction.

    Args:
        effect: DamageEffect from DM's structured output
        declared_action: Original action dict with declared target
        target_id_mapper: TargetIDMapper instance for resolution
        allow_llm_fallback: If True, return error for LLM correction; if False, raise

    Returns:
        (is_valid, corrected_effect, error_description)
        - is_valid: True if no correction needed OR successfully corrected
        - corrected_effect: Corrected DamageEffect (or None if failed)
        - error_description: None if valid, string describing error otherwise

    Raises:
        TargetingValidationError: If allow_llm_fallback=False and validation fails
    """

    # STEP 1: Check if target field exists
    if not effect.target:
        error = "Missing target field in DamageEffect"
        logger.warning(f"⚠️  TARGETING VALIDATION: {error}")

        # Try to extract from declared action
        declared_target = declared_action.get('target')
        if declared_target and declared_target.startswith('tgt_'):
            logger.info(f"✓ MECHANICAL CORRECTION: Using declared target {declared_target}")
            corrected = effect.model_copy(update={'target': declared_target})
            return (True, corrected, None)

        # Mechanical correction failed
        if allow_llm_fallback:
            return (False, None, error)
        raise TargetingValidationError(error)

    # STEP 2: Check if target uses character name instead of ID (Pattern A)
    if not effect.target.startswith('tgt_'):
        error = f"Target uses character name '{effect.target}' instead of target ID"
        logger.warning(f"⚠️  TARGETING VALIDATION: {error}")

        # MECHANICAL CORRECTION: Match name to declared target
        declared_target = declared_action.get('target')
        if declared_target and declared_target.startswith('tgt_'):
            # Verify the declared target matches the character name
            resolved_entity = target_id_mapper.resolve_target(declared_target)
            if resolved_entity:
                entity_name = _get_entity_name(resolved_entity)
                # Fuzzy match (case-insensitive substring)
                if (effect.target.lower() in entity_name.lower() or
                    entity_name.lower() in effect.target.lower()):
                    logger.info(f"✓ MECHANICAL CORRECTION: Matched '{effect.target}' to {declared_target}")
                    corrected = effect.model_copy(update={'target': declared_target})
                    return (True, corrected, None)

        # Mechanical correction failed - need LLM inference
        if allow_llm_fallback:
            return (False, None, error)
        raise TargetingValidationError(error)

    # STEP 3: Check if target ID format is valid (Pattern B caught by Pydantic)
    # If we reach here, Pydantic validation passed, so format is correct

    # STEP 4: Check if target ID exists in mapper (Pattern C)
    resolved_entity = target_id_mapper.resolve_target(effect.target)
    if not resolved_entity:
        error = f"Target ID '{effect.target}' not found in target mapper"
        logger.warning(f"⚠️  TARGETING VALIDATION: {error}")

        # MECHANICAL CORRECTION: Check if declared target is valid
        declared_target = declared_action.get('target')
        if declared_target and declared_target.startswith('tgt_'):
            check_entity = target_id_mapper.resolve_target(declared_target)
            if check_entity:
                logger.info(f"✓ MECHANICAL CORRECTION: Using declared target {declared_target} instead of stale {effect.target}")
                corrected = effect.model_copy(update={'target': declared_target})
                return (True, corrected, None)

        # Mechanical correction failed
        if allow_llm_fallback:
            return (False, None, error)
        raise TargetingValidationError(error)

    # STEP 5: All validations passed
    logger.debug(f"✓ Target validation passed for {effect.target}")
    return (True, effect, None)


def _get_entity_name(entity: Any) -> str:
    """
    Extract name from entity (handles players, enemies, NPCs).

    Args:
        entity: Agent object (player, enemy, or NPC)

    Returns:
        Entity name string, or "Unknown" if name cannot be determined
    """
    # Try player format (has character_state)
    if hasattr(entity, 'character_state') and hasattr(entity.character_state, 'name'):
        return entity.character_state.name

    # Try enemy/NPC format (has name directly)
    if hasattr(entity, 'name'):
        return entity.name

    # Unknown entity type
    return "Unknown"
