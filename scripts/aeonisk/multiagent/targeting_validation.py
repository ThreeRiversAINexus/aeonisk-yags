"""
Targeting validation system for DM-generated effects.

Validates and corrects targeting errors in structured output, triggered only when
errors are detected. Uses mechanical correction first, LLM fallback for complex cases.
"""

from typing import Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field
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

    # STEP 5: Check for cross-type target mismatch (DM redirected damage to wrong entity type)
    # If player declared an enemy target but DM's damage hits a PC (or vice versa), correct it.
    # This prevents the DM from hallucinating friendly fire when the player targeted an enemy.
    declared_target = declared_action.get('target')
    if (declared_target and declared_target.startswith('tgt_') and
            effect.target != declared_target):
        # DM used a different target than what was declared — check entity types
        declared_is_player = target_id_mapper.is_player(declared_target)
        effect_is_player = target_id_mapper.is_player(effect.target)

        if declared_is_player != effect_is_player:
            # Cross-type mismatch: DM redirected between PC and enemy
            declared_entity = target_id_mapper.resolve_target(declared_target)
            effect_entity = resolved_entity
            declared_name = _get_entity_name(declared_entity) if declared_entity else declared_target
            effect_name = _get_entity_name(effect_entity) if effect_entity else effect.target

            if declared_is_player and not effect_is_player:
                # Player targeted a PC (intentional FF), DM redirected to enemy — allow
                logger.debug(f"✓ DM redirected PC-targeted damage to enemy {effect.target} — allowing")
            else:
                # Player targeted an enemy, DM redirected to a PC — BLOCK and correct
                logger.warning(
                    f"⚠️  TARGETING VALIDATION: DM redirected damage from declared enemy target "
                    f"'{declared_name}' ({declared_target}) to PC '{effect_name}' ({effect.target}). "
                    f"Correcting back to declared target."
                )
                corrected = effect.model_copy(update={'target': declared_target})
                return (True, corrected, None)

    # STEP 5.5: Semantic state validation — check if target is in a
    # combat-appropriate state (not prisoner, unconscious, defeated, etc.)
    #
    # This catches DM free-target misbinding where the DM resolves a
    # combat action to a prisoner/civilian instead of an active enemy.
    if resolved_entity:
        semantic_warning = _check_target_combat_state(
            resolved_entity, effect, target_id_mapper
        )
        if semantic_warning:
            # Log warning but DO NOT block — player may intentionally
            # target non-combatants (ethical gameplay choice).
            logger.warning(
                f"TARGET SEMANTIC WARNING: {semantic_warning} "
                f"(target={effect.target})"
            )
            # Future: If declared_action target differs from effect target,
            # this is likely DM misbinding. Could auto-correct to declared
            # target. For now, warn only.

    # STEP 6: All validations passed
    logger.debug(f"✓ Target validation passed for {effect.target}")
    return (True, effect, None)


def _check_target_combat_state(
    entity: Any,
    effect: 'DamageEffect',
    target_id_mapper: 'TargetIDMapper'
) -> Optional[str]:
    """
    Check if target entity is in a state where combat targeting is
    semantically appropriate.

    Returns None if targeting is appropriate, or a warning string if the
    target appears to be a non-combatant, prisoner, or defeated entity.

    This is a SOFT check — it warns but does not block. Players may
    legitimately choose to attack prisoners or non-combatants, and the
    soulcredit system handles the ethical dimension.

    Args:
        entity: Resolved agent object (EnemyAgent, NPCAgent, or player)
        effect: The DamageEffect being validated
        target_id_mapper: For additional lookups if needed

    Returns:
        Warning string if targeting is questionable, None if appropriate
    """
    # Check NPC state
    if hasattr(entity, 'disposition'):
        # NPCAgent
        if getattr(entity, 'disposition', None) == 'prisoner':
            return (
                f"Combat damage targeting prisoner NPC '{entity.name}' "
                f"(disposition=prisoner). If player declared targeting "
                f"'enemies' or 'threats', this may be DM misbinding."
            )
        if getattr(entity, 'entity_type', None) == 'prisoner':
            return (
                f"Combat damage targeting prisoner NPC '{entity.name}' "
                f"(entity_type=prisoner). Verify player intent."
            )

    # Check enemy state
    if hasattr(entity, 'is_prisoner') and entity.is_prisoner:
        return (
            f"Combat damage targeting prisoner enemy '{entity.name}' "
            f"(is_prisoner=True). This entity has surrendered/been captured."
        )

    if hasattr(entity, 'is_active') and not entity.is_active:
        # Could be defeated, fled, or de-escalated
        if hasattr(entity, 'despawned_round') and entity.despawned_round is not None:
            return (
                f"Combat damage targeting defeated/removed entity "
                f"'{entity.name}' (is_active=False, despawned round "
                f"{entity.despawned_round}). Entity is no longer in combat."
            )

    # Check death state (health may be None on non-combatant/subdued entities)
    if getattr(entity, 'health', None) is not None and hasattr(entity, 'max_health'):
        if entity.health <= 0:
            return (
                f"Combat damage targeting unconscious/dead entity "
                f"'{entity.name}' (health={entity.health}). "
                f"Entity is already incapacitated."
            )

    # No issues detected
    return None


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


class TargetCorrectionResult(BaseModel):
    """LLM-inferred target correction result."""

    corrected_target: str = Field(
        ...,
        description="The correct target ID (tgt_xxxx format) for this effect"
    )
    confidence: str = Field(
        ...,
        description="Confidence level: 'high' (obvious from context), 'medium' (probable), 'low' (guessing)"
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        max_length=200,
        description="Brief explanation of why this target is correct"
    )


async def llm_infer_correct_target(
    effect: DamageEffect,
    declared_action: Dict[str, Any],
    available_targets: Dict[str, str],  # target_id -> name mapping
    error_description: str,
    dm_narration: str
) -> TargetCorrectionResult:
    """
    Use Haiku LLM to infer correct target when mechanical correction fails.

    Args:
        effect: The DamageEffect with invalid targeting
        declared_action: Original action declaration
        available_targets: Map of valid target IDs to entity names
        error_description: What failed mechanically
        dm_narration: DM's narrative description (for context)

    Returns:
        TargetCorrectionResult with inferred target

    Cost: ~$0.001 per call (Haiku pricing: $0.25/MTok input, $1.25/MTok output)
    Latency: ~200-500ms
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel

    # Build context for LLM
    targets_list = "\n".join(
        f"- {tid} = {name}" for tid, name in available_targets.items()
    )

    # Truncate narration to first 300 chars to keep prompt compact
    narration_excerpt = dm_narration[:300] if dm_narration else "No narration provided"
    if len(dm_narration) > 300:
        narration_excerpt += "..."

    prompt = f"""The DM generated an effect with targeting that couldn't be applied mechanically.

DECLARED ACTION:
Agent: {declared_action.get('agent_id', 'Unknown')}
Intent: {declared_action.get('intent', 'Unknown')}
Declared Target: {declared_action.get('target', 'None')}

DM RESOLUTION NARRATION:
{narration_excerpt}

DM's DAMAGE EFFECT:
Target: {effect.target}
Damage: {effect.dealt} HP
Damage Type: {effect.damage_type or 'unspecified'}

AVAILABLE VALID TARGETS:
{targets_list}

MECHANICAL VALIDATION ERROR:
{error_description}

What is the correct target ID for this damage effect? Consider:
1. Who is mentioned in the DM's narration as being hit/affected?
2. Does the declared target match any valid target?
3. Are there context clues (enemy type, positioning, narrative) to identify the target?

Return the correct target ID, your confidence level, and brief reasoning."""

    # Initialize Haiku agent (fast, cheap model for mechanical task)
    model = AnthropicModel('claude-haiku-4')
    agent = Agent(
        model,
        output_type=TargetCorrectionResult,
        system_prompt="You are a targeting validation assistant. Your job is to mechanically correct targeting errors in game effects by matching them to valid target IDs."
    )

    # Run inference
    logger.info(f"🤖 LLM TARGETING INFERENCE: Attempting to correct '{effect.target}' using Haiku")
    result = await agent.run(prompt)

    # Note: Pydantic AI 1.9.0 uses result.output (not result.data)
    logger.info(f"🤖 LLM TARGETING CORRECTION: {effect.target} -> {result.output.corrected_target} (confidence: {result.output.confidence})")
    logger.info(f"   Reasoning: {result.output.reasoning}")

    return result.output
