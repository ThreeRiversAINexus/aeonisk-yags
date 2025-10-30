"""
Structured Output Migration Helpers

Provides wrapper functions for gradual migration from text parsing to structured output.
Allows dual-mode operation during transition period.

Usage:
    # Old code:
    narration = await dm._generate_llm_response(...)
    state_changes = parse_state_changes(narration, ...)

    # New code (with fallback):
    resolution = await generate_dm_resolution_structured(
        provider=dm.llm_provider,
        prompt=prompt,
        fallback_to_text=True  # Falls back to text parsing if structured fails
    )
    narration = resolution.narration
    effects = resolution.effects

Author: Three Rivers AI Nexus
Date: 2025-10-29
"""

import logging
from typing import Optional, Union, Dict, Any
from .llm_provider import ClaudeProvider, LLMProvider, LLMConfig, create_claude_provider
from .schemas.action_resolution import ActionResolution, MechanicalEffects, create_combat_resolution, SuccessTier
from .schemas.player_action import PlayerAction, FreeAction
from .schemas.enemy_decision import EnemyDecision
from .schemas.story_events import RoundSynthesis, StoryAdvancement, EnemySpawn, NewClock

logger = logging.getLogger(__name__)


async def generate_dm_resolution_structured(
    provider: Optional[LLMProvider],
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 2000,
    temperature: float = 0.8,
    fallback_to_text: bool = False,  # Changed default: NO silent fallbacks
    **kwargs
) -> Union[ActionResolution, str]:
    """
    Generate DM action resolution with structured output.

    **IMPORTANT:** Default behavior is NO FALLBACK. Structured output failures will raise
    exceptions instead of silently falling back to text parsing. Use fallback_to_text=True
    only for gradual migration or testing.

    Args:
        provider: LLM provider (ClaudeProvider, OpenAIProvider, etc.)
        prompt: User prompt with action context
        system_prompt: Optional system prompt
        max_tokens: Max tokens to generate
        temperature: Sampling temperature
        fallback_to_text: If True, falls back to text generation on error (DEFAULT: False)
        **kwargs: Additional provider-specific params

    Returns:
        ActionResolution instance (if successful) or text string (if fallback enabled)

    Raises:
        ValueError: If provider is None and can't create default
        AttributeError: If provider doesn't support generate_structured
        Exception: Any error from structured output generation (unless fallback enabled)

    Example:
        ```python
        # Strict mode (default) - breaks on error
        resolution = await generate_dm_resolution_structured(
            provider=dm.llm_provider,
            prompt="Resolve: Echo scans void corruption...",
            system_prompt="You are the DM..."
        )  # Raises exception on any failure

        # Permissive mode - falls back to text
        resolution = await generate_dm_resolution_structured(
            provider=dm.llm_provider,
            prompt="...",
            fallback_to_text=True  # Explicitly opt-in to fallback
        )
        ```
    """
    # Create default provider if none provided
    if provider is None:
        try:
            logger.warning("No provider specified, creating default ClaudeProvider")
            provider = create_claude_provider(
                model="claude-sonnet-4-5",
                max_tokens=max_tokens,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Failed to create default provider: {e}")
            if fallback_to_text:
                logger.warning("Fallback enabled: returning prompt as text")
                return prompt
            raise ValueError(f"No provider available and failed to create default: {e}")

    # Verify provider supports structured output
    if not hasattr(provider, 'generate_structured'):
        error_msg = f"Provider {type(provider).__name__} doesn't support generate_structured()"
        logger.error(error_msg)
        if fallback_to_text:
            logger.warning("Fallback enabled: attempting legacy text generation")
            # Fall through to text generation below
        else:
            raise AttributeError(error_msg)

    # Try structured output (with built-in retry/backoff from ClaudeProvider)
    else:
        try:
            logger.debug("Attempting structured output with ActionResolution schema")
            resolution: ActionResolution = await provider.generate_structured(
                prompt=prompt,
                result_type=ActionResolution,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            logger.debug(f"✓ Structured resolution: {resolution.success_tier}, {len(resolution.narration)} chars, {len(resolution.effects.void_changes)} void changes")
            return resolution

        except Exception as e:
            # Log full error details
            logger.error(f"Structured output failed: {type(e).__name__}: {e}")

            if not fallback_to_text:
                # Strict mode: re-raise immediately
                logger.error("Structured output REQUIRED (fallback_to_text=False), re-raising exception")
                raise

            # Permissive mode: warn and continue to text fallback
            logger.warning(f"Fallback enabled: structured output failed, trying legacy text generation")

    # Fallback to text generation (only if fallback_to_text=True)
    if fallback_to_text:
        try:
            logger.warning("Attempting legacy text generation as fallback")
            response = await provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            logger.info(f"✓ Legacy text generation: {len(response.text)} chars")
            return response.text
        except Exception as e:
            logger.error(f"Legacy text generation also failed: {e}")
            raise RuntimeError(f"Both structured and text generation failed: {e}")

    # Should never reach here
    raise RuntimeError("Logic error: reached unreachable code in generate_dm_resolution_structured")


async def generate_player_action_structured(
    provider: Optional[LLMProvider],
    prompt: str,
    system_prompt: Optional[str] = None,
    character_name: str = "Player",
    agent_id: str = "player_unknown",
    max_tokens: int = 1000,
    temperature: float = 0.7,
    fallback_to_text: bool = True,
    **kwargs
) -> Union[PlayerAction, Dict[str, Any]]:
    """
    Generate player action declaration with structured output.

    Args:
        provider: LLM provider
        prompt: Action declaration prompt
        system_prompt: Optional system prompt
        character_name: Character name (for fallback)
        agent_id: Agent ID (for fallback)
        max_tokens: Max tokens
        temperature: Sampling temperature
        fallback_to_text: Fall back to dict parsing if structured fails
        **kwargs: Additional params

    Returns:
        PlayerAction instance or legacy dict

    Example:
        ```python
        action = await generate_player_action_structured(
            provider=player.llm_provider,
            prompt="Declare your action",
            system_prompt="You are Ash Vex...",
            character_name="Ash Vex",
            agent_id="player_ash"
        )

        if isinstance(action, PlayerAction):
            print(action.get_summary())
        else:
            # Legacy dict format
            print(action['intent'])
        ```
    """
    if provider is None:
        provider = create_claude_provider(max_tokens=max_tokens, temperature=temperature)

    # Try structured output
    try:
        if hasattr(provider, 'generate_structured'):
            logger.debug("Attempting structured PlayerAction")
            action: PlayerAction = await provider.generate_structured(
                prompt=prompt,
                result_type=PlayerAction,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            logger.debug(f"✓ Structured action: {action.get_summary()}")
            return action
        else:
            if not fallback_to_text:
                raise AttributeError("Provider doesn't support generate_structured")

    except Exception as e:
        logger.error(f"Structured player action failed: {e}")
        if not fallback_to_text:
            raise

    # Fallback to text parsing
    if fallback_to_text:
        logger.warning("Falling back to legacy action dict parsing")
        try:
            response = await provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            # Parse text into legacy dict format (very basic)
            # In real code, this would call the existing parser
            return {
                'intent': response.text[:200] if response.text else "Unknown action",
                'description': response.text,
                'character_name': character_name,
                'agent_id': agent_id,
                'attribute': 'Perception',
                'skill': None,
                'difficulty_estimate': 20,
                'difficulty_justification': 'Inferred from context',
                'action_type': 'custom'
            }
        except Exception as e:
            logger.error(f"Fallback parsing failed: {e}")
            raise

    raise RuntimeError("Both structured and fallback failed")


def extract_effects_from_resolution(
    resolution: Union[ActionResolution, str],
    legacy_parser_func: Optional[callable] = None
) -> Dict[str, Any]:
    """
    Extract mechanical effects from resolution (structured or text).

    Dual-mode helper: handles both ActionResolution objects and text strings.

    Args:
        resolution: ActionResolution instance or text string
        legacy_parser_func: Function to parse text (e.g., parse_state_changes)

    Returns:
        Dict with effects (normalized format)

    Example:
        ```python
        from outcome_parser import parse_state_changes

        effects = extract_effects_from_resolution(
            resolution=resolution,  # Could be ActionResolution or text
            legacy_parser_func=parse_state_changes
        )

        # effects dict has unified format regardless of source
        print(effects['void_change'])
        print(effects['clock_triggers'])
        ```
    """
    if isinstance(resolution, ActionResolution):
        # Structured output - direct extraction
        logger.debug("Extracting effects from structured ActionResolution")
        return {
            'void_change': sum(vc.amount for vc in resolution.effects.void_changes),
            'void_reasons': [vc.reason for vc in resolution.effects.void_changes],
            'void_target_character': resolution.effects.void_changes[0].character_name if resolution.effects.void_changes else None,
            'soulcredit_change': sum(sc.amount for sc in resolution.effects.soulcredit_changes),
            'soulcredit_reasons': [sc.reason for sc in resolution.effects.soulcredit_changes],
            'clock_triggers': [
                (cu.clock_name, cu.ticks, cu.reason, "structured_output")
                for cu in resolution.effects.clock_updates
            ],
            'conditions': [
                {
                    'type': cond.name,
                    'penalty': cond.penalty,
                    'duration': cond.duration,
                    'description': cond.description
                }
                for cond in resolution.effects.conditions
            ],
            'damage': resolution.effects.damage.dealt if resolution.effects.damage else 0,
            'damage_target': resolution.effects.damage.target if resolution.effects.damage else None,
            'position_changes': [
                {
                    'character_name': pc.character_name,
                    'new_position': pc.new_position.value,
                    'reason': pc.reason
                }
                for pc in resolution.effects.position_changes
            ],
            'notes': resolution.effects.notes
        }

    elif isinstance(resolution, str):
        # Text output - legacy parsing
        logger.debug("Falling back to legacy text parsing")
        if legacy_parser_func:
            # Use provided parser (e.g., parse_state_changes from outcome_parser)
            return legacy_parser_func(resolution)
        else:
            # Minimal fallback
            logger.warning("No legacy parser provided - returning empty effects")
            return {
                'void_change': 0,
                'void_reasons': [],
                'soulcredit_change': 0,
                'clock_triggers': [],
                'conditions': [],
                'damage': 0,
                'notes': []
            }

    else:
        logger.error(f"Unknown resolution type: {type(resolution)}")
        return {}


def convert_legacy_action_to_pydantic(legacy_action: Dict[str, Any]) -> PlayerAction:
    """
    Convert legacy action dict to Pydantic PlayerAction.

    Useful for gradual migration - allows old code to produce dicts,
    then convert to Pydantic for validation.

    Args:
        legacy_action: Dict with intent, attribute, skill, etc.

    Returns:
        Validated PlayerAction instance

    Example:
        ```python
        # Old code produces dict
        legacy_dict = {
            'intent': 'Scan corruption',
            'description': 'Using neural interface...',
            'attribute': 'Intelligence',
            'skill': 'Systems',
            ...
        }

        # Convert to Pydantic for validation
        action = convert_legacy_action_to_pydantic(legacy_dict)
        errors = action.validate()
        if errors:
            print(f"Validation errors: {errors}")
        ```
    """
    from .schemas.player_action import ActionType

    # Map action_type string to enum
    action_type_str = legacy_action.get('action_type', 'custom')
    try:
        action_type = ActionType(action_type_str)
    except ValueError:
        action_type = ActionType.CUSTOM

    return PlayerAction(
        intent=legacy_action.get('intent', 'Unknown action'),
        description=legacy_action.get('description', ''),
        attribute=legacy_action.get('attribute', 'Perception'),
        skill=legacy_action.get('skill'),
        difficulty_estimate=legacy_action.get('difficulty_estimate', 20),
        difficulty_justification=legacy_action.get('difficulty_justification', 'Not provided'),
        action_type=action_type,
        character_name=legacy_action.get('character_name', 'Unknown'),
        agent_id=legacy_action.get('agent_id', 'unknown'),
        target=legacy_action.get('target'),
        target_position=legacy_action.get('target_position'),
        is_ritual=legacy_action.get('is_ritual', False),
        has_primary_tool=legacy_action.get('has_primary_tool', False),
        has_offering=legacy_action.get('has_offering', False),
        ritual_components=legacy_action.get('ritual_components'),
        situational_modifiers=legacy_action.get('situational_modifiers', {})
    )


# Convenience function for enabling/disabling structured output globally
_USE_STRUCTURED_OUTPUT = True  # Global flag


def set_structured_output_enabled(enabled: bool):
    """
    Globally enable/disable structured output.

    Useful for testing or gradual rollout.

    Args:
        enabled: True to use structured output, False for legacy text parsing
    """
    global _USE_STRUCTURED_OUTPUT
    _USE_STRUCTURED_OUTPUT = enabled
    logger.info(f"Structured output {'ENABLED' if enabled else 'DISABLED'} globally")


def is_structured_output_enabled() -> bool:
    """Check if structured output is enabled globally."""
    return _USE_STRUCTURED_OUTPUT
