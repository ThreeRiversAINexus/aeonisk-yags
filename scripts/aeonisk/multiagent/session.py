"""
Self-playing session orchestrator that manages the complete gameplay loop.
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from .base import GameCoordinator, MessageType, Message
from .dm import AIDMAgent
from .player import AIPlayerAgent
from .human_interface import HumanInterface
from .shared_state import SharedState
from .voice_profiles import VoiceLibrary
from .energy_economy import SeedType
from .outcome_parser import (
    parse_session_end_marker
)
from .enemy_combat import EnemyCombatManager
from .tactical_resolution import ResolutionState
from .agent_prompt_logger import AgentPromptLogger
from .awareness import filter_narrations_for_agent, NarrationEntry

logger = logging.getLogger(__name__)

# =============================================================================
# DISPLAY CONSTANTS (Spec 12)
# =============================================================================

# Disposition -> emoji mapping for NPC display (deduplicated from inline dicts)
NPC_DISPOSITION_EMOJI = {
    "friendly": "\U0001f91d",  # handshake
    "neutral": "\U0001f610",   # neutral face
    "wary": "\U0001f61f",      # worried face
    "prisoner": "\U0001f512",  # lock
}

NPC_DISPOSITION_DEFAULT_EMOJI = "\u2753"  # question mark


def _format_enemy_declaration_details(reasoning: str, shared_intel: str = None) -> str:
    """Format enemy declaration reasoning and shared intel for stdout display.

    Returns formatted string with sub-lines for reasoning and shared intel.
    The reasoning is shown in full (never truncated).
    """
    lines = []
    if reasoning:
        lines.append(f"         +-- Reasoning: {reasoning}")
    if shared_intel:
        lines.append(f"         +-- Shared Intel: {shared_intel}")
    return "\n".join(lines)


def _format_npc_declaration_reason(reason: str) -> str:
    """Format NPC declaration reason for stdout display.

    Returns the full reason text (never truncated).
    """
    return f"         \u2514\u2500 {reason}"


def derive_death_state(agent) -> str:
    """The life-state oracle: 'alive' | 'unconscious' | 'dead'.

    Health, wounds and stuns live on the *agent*, not on CharacterState. Reading
    a defeat flag off CharacterState silently yields the getattr default, which
    is how end_state_snapshot came to report is_defeated=False for a character
    the character_state rows had marked defeated for three rounds running.

    Thresholds: 6+ wounds is dead; 0 health or 6+ stuns (YAGS Beaten) is
    unconscious.
    """
    wounds = getattr(agent, 'wounds', 0) or 0
    health = getattr(agent, 'health', 0) or 0
    stuns = getattr(agent, 'stuns', 0) or 0
    if wounds >= 6:
        return "dead"
    if health <= 0 or stuns >= 6:
        return "unconscious"
    return "alive"


def entity_soulcredit(mechanics, agent_id: str) -> int:
    """Current Soulcredit for any entity, read from the mechanics ledger.

    Enemies and NPCs carry real ledgers now that the enforce magistrate can name
    them, so the character_state oracle must report what was actually written
    instead of a hardcoded 0. Read-only: never mints a ledger entry for an
    entity nobody has judged.
    """
    if mechanics is None:
        return 0
    states = getattr(mechanics, 'soulcredit_states', None) or {}
    state = states.get(agent_id)
    return getattr(state, 'score', 0) if state is not None else 0


def character_state_row(entity, mechanics, agent: str) -> Dict[str, Any]:
    """Build one `character_state` payload for any entity kind.

    Players, enemies and NPCs all land in the same oracle through this, so the
    three loops cannot drift apart — the enemy path previously duplicated the
    death-state thresholds and hardcoded `void_score=0` and `soulcredit=0`, and
    the NPC path did not exist at all, so an arrested prisoner vanished from the
    record at the moment of arrest.

    `agent` is the entity kind recorded on the event: 'player', 'enemy' or 'npc'.
    """
    death_state = derive_death_state(entity)
    agent_id = getattr(entity, 'agent_id', None)
    return {
        'character_id': agent_id,
        'character_name': getattr(entity, 'name', None),
        'health': getattr(entity, 'health', 0) or 0,
        'max_health': getattr(entity, 'max_health', 0) or 0,
        'wounds': getattr(entity, 'wounds', 0) or 0,
        'stuns': getattr(entity, 'stuns', 0) or 0,
        'void_score': getattr(entity, 'void_score', 0) or 0,
        'soulcredit': entity_soulcredit(mechanics, agent_id),
        'position': str(getattr(entity, 'position', 'Unknown')),
        'conditions': _serialize_conditions(mechanics, agent_id),
        'is_defeated': death_state != "alive",
        'death_state': death_state,
        'agent': agent,
    }


def party_snapshot_entry(agent) -> Dict[str, Any]:
    """One end_state_snapshot party member, life-state taken from the oracle."""
    char = getattr(agent, 'character_state', None)
    death_state = derive_death_state(agent)
    return {
        'name': getattr(char, 'name', None),
        'faction': getattr(char, 'faction', None),
        'is_defeated': death_state != "alive",
        'death_state': death_state,
        'void_score': getattr(char, 'void_score', None),
    }


# Tiers that clear the DC (mirrors dm._resolution_success).
_SUCCESS_TIERS = frozenset({
    'marginal', 'moderate', 'good', 'excellent', 'exceptional'})


def prior_declarations(
    declared_actions: Optional[Dict[str, List[Dict[str, Any]]]],
) -> List[tuple]:
    """Every action already declared this round, as (actor_name, initiative, text).

    Sorted slowest-declared first, matching declaration order.

    `_declared_actions` is cleared at round start and declaration runs
    slowest-initiative-first, so everything in the buffer belongs to an agent
    that has already gone — there is nothing to filter out. The previous inline
    version selected `initiative > mine`, which given that ordering matched
    nothing, so NPCs never actually saw prior declarations. It also compared a
    possibly-None initiative against an int (`dict.get` returns its default only
    for an ABSENT key, not a present None), raising TypeError into a broad
    `except` that cost the NPC its whole turn.
    """
    collected: List[tuple] = []
    for agent_id, actions in (declared_actions or {}).items():
        for action in actions or []:
            initiative = action.get('initiative') or 0
            actor_name = action.get('character_name') or agent_id
            text = (action.get('description')
                    or action.get('intent')
                    or 'unknown action')
            collected.append((actor_name, initiative, text))

    collected.sort(key=lambda entry: entry[1])
    return collected


def _format_clock_progress_bar(current: int, maximum: int, bar_width: int = 8) -> str:
    """Format a visual progress bar for a scene clock.

    Args:
        current: Current clock value
        maximum: Maximum clock value
        bar_width: Width of the progress bar in characters

    Returns:
        Formatted string like [████░░░░]
    """
    if maximum <= 0:
        return f"[{'░' * bar_width}]"
    filled = int((current / maximum) * bar_width)
    filled = min(filled, bar_width)  # Cap at bar_width
    empty = bar_width - filled
    return f"[{'█' * filled}{'░' * empty}]"


# =============================================================================
# RANGE & MOVEMENT UTILITIES (Spec 09)
# =============================================================================

# Keywords that indicate defensive/evasive intent (dodge-as-movement)
_DODGE_KEYWORDS = frozenset({
    'dodge', 'evade', 'take cover', 'duck', 'dive', 'roll away',
    'seek cover', 'find cover', 'get behind cover', 'defensive stance',
    'brace', 'hunker down',
})


def compute_dodge_defense_bonus(player, action: dict) -> int:
    """Compute an agility-based defense bonus for dodge/cover declarations.

    When a player declares an evasive action (dodge, take cover, etc.),
    they receive a defense bonus equal to their Agility attribute value
    divided by 2 (rounded down, minimum 1 if dodging).

    Args:
        player: AIPlayerAgent (or mock) with character_state.attributes
        action: Action dict with 'intent' field

    Returns:
        Defense bonus (int). 0 if action is not a dodge/cover declaration.
    """
    intent = (action.get('intent') or '').lower()
    if not intent:
        return 0

    # Check if intent contains any dodge keyword
    is_dodge = any(keyword in intent for keyword in _DODGE_KEYWORDS)

    if not is_dodge:
        return 0

    # Get agility attribute
    agility = 3  # Default
    char_state = getattr(player, 'character_state', None)
    if char_state:
        attrs = getattr(char_state, 'attributes', {})
        if isinstance(attrs, dict):
            agility = attrs.get('Agility', 3)
        else:
            agility = getattr(attrs, 'Agility', 3)

    # Bonus = Agility // 2, minimum 1 for any dodge declaration
    bonus = max(1, agility // 2)
    return bonus


def apply_intra_round_position_update(agent, new_position_str: str) -> None:
    """Apply a position change to an agent immediately (intra-round update).

    This function is called during the resolution loop to update an agent's
    position so that subsequent resolutions within the same round use the
    updated position for range calculations.

    Args:
        agent: Any agent with a position attribute (player, enemy, NPC)
        new_position_str: Position string like "Far-PC", "Engaged", etc.
    """
    from .enemy_agent import Position as TacticalPosition

    old_position = getattr(agent, 'position', None)
    new_position = TacticalPosition.from_string(new_position_str)
    agent.position = new_position

    agent_name = ''
    if hasattr(agent, 'character_state') and agent.character_state:
        agent_name = getattr(agent.character_state, 'name', '')
    elif hasattr(agent, 'name'):
        agent_name = agent.name

    logger.info(
        f"Intra-round position update: {agent_name} "
        f"{old_position} -> {new_position}"
    )


# =============================================================================
# ROLE LLM CONFIG HELPERS (Spec 11: Per-Role Model Configuration)
# =============================================================================

def get_enemy_llm_config(session_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get enemy LLM config from session config with fallback chain.

    Enemy LLM fallback chain: enemies -> legacy enemy_agents -> dm.

    Args:
        session_config: Full session configuration dict.

    Returns:
        LLM config dict, or None if no config found at any level.
    """
    agents = session_config.get('agents', {})

    enemy_llm = agents.get('enemies', {}).get('llm')
    if enemy_llm:
        return enemy_llm

    legacy_enemy_llm = agents.get('enemy_agents', {}).get('llm')
    if legacy_enemy_llm:
        return legacy_enemy_llm

    dm_llm = agents.get('dm', {}).get('llm')
    if dm_llm:
        return dm_llm

    return None


def get_npc_llm_config(session_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get NPC LLM config from session config with fallback chain.

    NPC LLM fallback chain: npcs -> enemies -> legacy enemy_agents -> dm.

    1. agents.npcs.llm if present
    2. agents.enemies.llm if present (enemies and NPCs share a tier)
    3. agents.enemy_agents.llm if present (legacy enemy config)
    4. agents.dm.llm as final fallback

    Args:
        session_config: Full session configuration dict.

    Returns:
        LLM config dict, or None if no config found at any level.
    """
    agents = session_config.get('agents', {})

    # Try NPC-specific config first
    npc_llm = agents.get('npcs', {}).get('llm')
    if npc_llm:
        return npc_llm

    # Fall back to enemy config (enemies and NPCs share a tier)
    enemy_llm = get_enemy_llm_config(session_config)
    if enemy_llm:
        return enemy_llm

    return None


# Safe zone keywords for vendor spawning guidance
_SAFE_ZONE_KEYWORDS = [
    'market', 'social', 'gathering', 'festival', 'ceremony',
    'negotiation', 'diplomatic', 'downtime', 'neutral zone',
    'safe zone', 'trading post', 'settlement', 'trade route',
]


def is_safe_zone_scenario(scenario_description: str) -> bool:
    """Check if a scenario description indicates a safe zone suitable for vendors.

    Args:
        scenario_description: Text description of the scenario

    Returns:
        True if scenario matches safe zone keywords
    """
    desc_lower = scenario_description.lower()
    return any(kw in desc_lower for kw in _SAFE_ZONE_KEYWORDS)


def _parse_surrender_from_resolution(
    resolution_data: Dict[str, Any],
    resolution_state: ResolutionState,
    target_id_mapper: Optional[Any] = None
) -> None:
    """
    Parse PC action resolution to detect enemy surrender.

    Checks for conditions/effects indicating surrender and marks enemies
    as surrendered in resolution_state to invalidate their subsequent actions.

    Args:
        resolution_data: DM's action resolution (from adjudication)
        resolution_state: Resolution state to update
        target_id_mapper: Target ID mapper for resolving target IDs (optional)
    """
    # Extract target info from action
    action = resolution_data.get('context', {})
    target_id = action.get('target')

    if not target_id:
        return  # No target, can't be a surrender

    # Check if targeting an enemy
    if target_id_mapper and hasattr(target_id_mapper, 'is_enemy'):
        if not target_id_mapper.is_enemy(target_id):
            return  # Not targeting enemy

    # Look for surrender indicators in effects
    effects = resolution_data.get('effects', {})

    # Check status_effects (text-based, legacy format)
    status_effects = effects.get('status_effects', [])
    if isinstance(status_effects, list):
        for effect in status_effects:
            effect_lower = str(effect).lower()
            if any(keyword in effect_lower for keyword in ['surrendered', 'surrender', 'laid down weapons', 'disarmed and compliant']):
                # Resolve target ID to enemy agent_id
                if target_id_mapper:
                    target_entity = target_id_mapper.resolve_target(target_id)
                    if target_entity and hasattr(target_entity, 'agent_id'):
                        resolution_state.mark_surrendered(target_entity.agent_id)
                        logger.info(f"Detected surrender from status effect: {target_entity.agent_id}")
                        return

    # Check conditions (structured format, Pydantic schema)
    conditions = effects.get('conditions')
    if conditions:
        for condition in conditions:
            if isinstance(condition, dict):
                cond_name = condition.get('name', '').lower()
                cond_desc = condition.get('description', '').lower()

                if 'surrender' in cond_name or 'surrender' in cond_desc:
                    # Resolve target ID to enemy agent_id
                    if target_id_mapper:
                        target_entity = target_id_mapper.resolve_target(target_id)
                        if target_entity and hasattr(target_entity, 'agent_id'):
                            resolution_state.mark_surrendered(target_entity.agent_id)
                            logger.info(f"Detected surrender from condition: {target_entity.agent_id}")
                            return


def _mark_defeated_from_resolution(
    enemy_combat,
    resolution_state: ResolutionState,
    jsonl_logger=None,
    round_num=None
) -> None:
    """
    Sync resolution_state with enemies defeated or incapacitated by PC actions.

    After a PC action resolves and _process_structured_damage_effects sets
    is_active=False on killed enemies, this marks them as defeated in
    resolution_state so ActionValidator properly invalidates their later
    actions (with JSONL events and narration).

    Also catches safety-net cases:
    - health <= 0 but is_active wasn't set to False
    - stuns >= 6 (stun KO / unconscious) but is_active wasn't set to False

    Args:
        enemy_combat: EnemyCombatManager (or None if not in tactical combat)
        resolution_state: Resolution state to update
    """
    if not enemy_combat or not hasattr(enemy_combat, 'enemy_agents'):
        return
    for enemy in enemy_combat.enemy_agents:
        agent_id = enemy.agent_id
        already_tracked = resolution_state.is_defeated(agent_id) or resolution_state.is_incapacitated(agent_id)
        if already_tracked:
            continue

        # Primary check: is_active flag (set by _process_structured_damage_effects)
        if not enemy.is_active:
            resolution_state.mark_defeated(agent_id)
            logger.info(f"Marked {enemy.name} ({agent_id}) as defeated in resolution_state")
            continue

        # Safety net: health <= 0 but is_active not set
        health = getattr(enemy, 'health', None)
        if isinstance(health, (int, float)) and health <= 0:
            resolution_state.mark_defeated(agent_id)
            logger.info(f"Marked {enemy.name} ({agent_id}) as defeated (health={health}, safety net)")
            continue

        # YAGS Beaten/Fatal consciousness gate (model a, same as players): a
        # Beaten (stuns>=6) or fatally wounded (wounds>=6) enemy must pass a Health
        # check to act this round; fail -> incapacitated (ActionValidator then
        # invalidates its action), pass -> acts while Beaten. Rolled at most ONCE
        # per round via the ko_checked guard (this runs after every PC action).
        stuns = getattr(enemy, 'stuns', 0)
        wounds = getattr(enemy, 'wounds', 0)
        stuns = stuns if isinstance(stuns, (int, float)) else 0
        wounds = wounds if isinstance(wounds, (int, float)) else 0
        if (stuns >= 6 or wounds >= 6) and agent_id not in resolution_state.ko_checked:
            from .mechanics import resolve_ko_check
            resolution_state.ko_checked.add(agent_id)
            result = resolve_ko_check(stuns, wounds, _ko_health_attr(enemy))
            _log_ko_check(jsonl_logger, round_num, agent_id,
                          getattr(enemy, 'name', agent_id), 'enemy',
                          stuns, wounds, _ko_health_attr(enemy), result)
            if not result['can_act']:
                resolution_state.mark_incapacitated(agent_id)
                logger.info(f"Beaten/Fatal KO: {enemy.name} ({agent_id}) failed health check "
                            f"(stuns={stuns}, wounds={wounds}, total={result['total']} vs "
                            f"DC {result['dc']}) - incapacitated this round")
            else:
                logger.info(f"Beaten/Fatal but conscious: {enemy.name} ({agent_id}) passed health "
                            f"check (total={result['total']} vs DC {result['dc']}) - acts while Beaten")


_VALID_RINGS = {"Engaged", "Near", "Far", "Extreme"}


def _resume_position(value):
    """Restore a recorded position string as the tactical Position object BOTH
    agent kinds actually hold (enemy_agent.Position, ring+side, with
    from_string/shift_toward_center). Recorded strings are its own str() form
    ('Near-Enemy', 'Engaged-PC'), so they round-trip exactly. Two earlier
    guesses crashed live: a bare string ('str' has no shift_toward_center) and
    the schemas Position ENUM ('Position' has no shift_toward_center — that
    enum is the LLM-schema type, not the tactical one). Unknown rings fall back
    to Near-Enemy, the engine-safe default."""
    from .enemy_agent import Position
    pos = Position.from_string(str(value))
    if pos.ring not in _VALID_RINGS:
        return Position.from_string("Near-Enemy")
    return pos


def _serialize_conditions(mechanics, agent_id) -> list:
    """Serialize an agent's live conditions for the character_state snapshot.

    Was hardcoded [] (TODO) — conditions existed only in mechanics.conditions,
    invisible to the corpus and to round-state reconstruction. Best-effort:
    a broken mechanics object must never break state logging.
    """
    try:
        conds = mechanics.get_conditions(agent_id) if mechanics else []
        return [{"name": c.name, "type": c.type, "penalty": c.penalty,
                 "duration": c.duration, "affects": list(c.affects)}
                for c in conds]
    except Exception as e:
        # Conditions feed character_state; dropping them silently makes an
        # afflicted character read as clean in the corpus.
        logger.warning(f"Could not serialize conditions for {agent_id}: "
                       f"{type(e).__name__}: {e}")
        return []


def _log_ko_check(jsonl_logger, round_num, agent_id, name, side,
                  stuns, wounds, health_attr, result) -> None:
    """Emit a ko_check event for a rolled Beaten/Fatal consciousness check.

    Carries the full inputs (stuns/wounds/health_attr/roll) and outputs
    (dc/total/can_act/status) so the mechanics-diff harness can re-run
    resolve_ko_check deterministically with the logged roll. Best-effort:
    logging failure must never break the gate itself.
    """
    if not jsonl_logger:
        return
    try:
        jsonl_logger.write_event({
            'event_type': 'ko_check',
            'ts': datetime.now().isoformat(),
            'session': getattr(jsonl_logger, 'session_id', None) or 'unknown',
            'round': round_num,
            'agent_id': agent_id,
            'name': name,
            'side': side,
            'stuns': stuns,
            'wounds': wounds,
            'health_attr': health_attr,
            'roll': result['roll'],
            'dc': result['dc'],
            'total': result['total'],
            'can_act': result['can_act'],
            'status': result['status'],
        })
    except Exception as e:
        logger.error(f"Failed to log ko_check for {agent_id}: {e}")


def _ko_health_attr(entity) -> int:
    """Toughness attribute for the KO health check, handling both entity shapes.

    Aeonisk uses Endurance as the YAGS Health-equivalent; players carry it on
    `character_state.attributes`, enemies on `attributes`. Both key orders are
    tried because enemy templates still ship a legacy 'Health' entry. Falls back
    to 3.

    (Player.check_death_save reads Endurance-first too, since #82 — it used to
    read 'Health', which no character built from a config actually has, so every
    death save silently rolled the fallback.)"""
    cs = getattr(entity, 'character_state', None)
    cs_attrs = getattr(cs, 'attributes', None)
    if isinstance(cs_attrs, dict):
        for k in ('Health', 'Endurance'):
            if k in cs_attrs:
                return cs_attrs[k]
    attrs = getattr(entity, 'attributes', None)
    if isinstance(attrs, dict):
        for k in ('Endurance', 'Health'):
            if k in attrs:
                return attrs[k]
    return 3


def _check_beaten_ko(agent, resolution_state: ResolutionState,
                     jsonl_logger=None, round_num=None) -> bool:
    """YAGS per-round consciousness gate (combat.md:419/469): if the agent is
    Beaten (stuns>=6) or Fatally wounded (wounds>=6), roll the health check. On
    failure they are unconscious THIS round — marked incapacitated in the
    per-round ResolutionState so the existing skip path drops their action, and
    they get a fresh check next round (ResolutionState is rebuilt each round). On
    success they act normally despite being Beaten. This is a consciousness gate,
    never a death roll (death is owned by Player.check_death_save at damage time).

    Returns True if the agent was marked incapacitated.
    """
    from .mechanics import resolve_ko_check
    stuns = getattr(agent, 'stuns', 0) or 0
    wounds = getattr(agent, 'wounds', 0) or 0
    if stuns < 6 and wounds < 6:
        return False
    result = resolve_ko_check(stuns, wounds, _ko_health_attr(agent))
    cs = getattr(agent, 'character_state', None)
    name = getattr(cs, 'name', None) or getattr(agent, 'agent_id', '?')
    _log_ko_check(jsonl_logger, round_num, agent.agent_id, name, 'player',
                  stuns, wounds, _ko_health_attr(agent), result)
    if not result['can_act']:
        resolution_state.mark_incapacitated(agent.agent_id)
        logger.info(
            f"Beaten/Fatal KO: {name} failed health check "
            f"(stuns={stuns}, wounds={wounds}, roll={result['roll']}, "
            f"total={result['total']} vs DC {result['dc']}) - unconscious this round")
        return True
    logger.info(
        f"Beaten/Fatal but conscious: {name} passed health check "
        f"(total={result['total']} vs DC {result['dc']}) - acts while Beaten")
    return False


def _check_condition_incapacitation(
    agent_id: str,
    mechanics,
    resolution_state: ResolutionState
) -> bool:
    """
    Check if an agent has incapacitating conditions and mark them in resolution_state.

    Scans the agent's active conditions from mechanics.get_conditions(). If any
    condition has abs(penalty) >= 6 (the Stunned/incapacitation threshold), marks
    the agent as incapacitated in resolution_state.

    This is additive to the existing ResolutionState.is_incapacitated() check --
    it feeds into the same skip path but triggers from the condition pipeline
    rather than the stun KO combat path.

    Args:
        agent_id: The agent's ID to check conditions for
        mechanics: The mechanics engine (may be None)
        resolution_state: Resolution state to update if incapacitated

    Returns:
        True if the agent was marked incapacitated (or already was), False otherwise
    """
    INCAPACITATION_THRESHOLD = 6  # abs(penalty) >= this means incapacitated

    if not mechanics or not hasattr(mechanics, 'get_conditions'):
        return False

    conditions = mechanics.get_conditions(agent_id)
    if not conditions:
        return False

    for condition in conditions:
        # Only negative penalties indicate impairment; positive values are buffs
        if condition.penalty < 0 and abs(condition.penalty) >= INCAPACITATION_THRESHOLD:
            resolution_state.mark_incapacitated(agent_id)
            logger.info(
                f"Condition-based incapacitation: {agent_id} has '{condition.name}' "
                f"(penalty={condition.penalty}, threshold={INCAPACITATION_THRESHOLD})"
            )
            return True

    return False


def _get_energy_purse(agent):
    """
    Get energy purse from player or NPC agent.

    Handles both patterns:
    - Player: agent.character_state.energy_purse
    - NPC: agent.energy_purse (directly on agent)
    """
    # Player pattern: agent.character_state.energy_purse
    if hasattr(agent, 'character_state') and hasattr(agent.character_state, 'energy_purse'):
        return agent.character_state.energy_purse
    # NPC pattern: agent.energy_purse directly
    if hasattr(agent, 'energy_purse'):
        return agent.energy_purse
    return None


def _get_inventory(agent):
    """
    Get inventory dict from player or NPC, creating if needed.

    Handles both patterns:
    - Player: agent.character_state.inventory
    - NPC: agent.inventory (may need to create)
    """
    # Player pattern: agent.character_state.inventory
    if hasattr(agent, 'character_state'):
        if not hasattr(agent.character_state, 'inventory') or agent.character_state.inventory is None:
            agent.character_state.inventory = {}
        return agent.character_state.inventory
    # NPC pattern: agent.inventory (create if needed)
    if not hasattr(agent, 'inventory') or agent.inventory is None:
        agent.inventory = {}
    return agent.inventory


def _normalize_enemy_result(result: dict) -> dict:
    """Normalize enemy combat result for compatibility with PC resolution format.

    Enemy results have inconsistent field names (hit vs success, roll.margin vs
    flat margin, action string vs dict). This normalizes them so downstream code
    (e.g. _build_enhanced_previous_context) can handle both uniformly.
    """
    normalized = dict(result)

    # Normalize action to dict format
    raw_action = result.get('action', 'unknown')
    if isinstance(raw_action, str):
        normalized['action'] = {
            'action_type': raw_action,
            'character_name': result.get('character_name', ''),
        }

    # Ensure top-level success field
    if 'success' not in normalized:
        if result.get('hit') is not None:
            normalized['success'] = result['hit']
        elif result.get('result') in ('success', 'failure', 'invalidated'):
            normalized['success'] = result['result'] == 'success'
        else:
            normalized['success'] = True

    # Ensure top-level margin field
    if 'margin' not in normalized:
        roll = result.get('roll')
        if isinstance(roll, dict) and 'margin' in roll:
            normalized['margin'] = roll['margin']
        else:
            normalized['margin'] = 0

    return normalized


class EnemyFallbackLLMClient:
    """
    Wrapper for enemy LLM calls with logging support.

    Each enemy gets its own instance (cached per agent_id on the session) so
    call_sequence advances monotonically across rounds — the replay-cache key.
    Previously this was defined inline in _run_initiative_round and rebuilt every
    round, resetting call_sequence to 0 (enemies logged [0, 0] across rounds).

    `provider` may be injected (tests); otherwise it is created from llm_config.
    """

    def __init__(self, llm_config, jsonl_logger=None, agent_id='enemy_unknown',
                 session_id=None, agent_prompt_logger=None, provider=None,
                 replay_client=None):
        self.llm_config = llm_config
        self.jsonl_logger = jsonl_logger
        self.agent_prompt_logger = agent_prompt_logger
        self.agent_id = agent_id
        self.session_id = session_id
        self.replay_client = replay_client
        self.call_sequence = 0  # Track LLM call ordering for replay

        if replay_client is not None:
            self.provider = None
        elif provider is not None:
            self.provider = provider
        else:
            # Use llm_provider instead of direct Anthropic client
            from .llm_provider import LLMConfig, create_provider

            provider_config = LLMConfig.from_dict(llm_config, max_tokens=500)
            self.provider = create_provider(provider_config)

    async def generate_async(self, prompt: str, temperature: float = 0.7, max_tokens: int = 500):
        from datetime import datetime, timezone

        if self.replay_client is not None:
            response = self.replay_client.messages.create(
                model=self.llm_config.get('model', 'replay'),
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return {"content": response.content[0].text}

        # Use llm_provider for all providers (Anthropic, OpenAI, etc.)
        response = await self.provider.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

        response_text = response.text

        # Log LLM call if logger is available
        if self.jsonl_logger:
            try:
                from token_utils import count_chat_tokens, count_text_tokens

                messages = [{"role": "user", "content": prompt}]
                model = self.llm_config.get('model', 'unknown')
                input_tokens = count_chat_tokens(messages, model)
                output_tokens = count_text_tokens(response_text, model)
                self.jsonl_logger.write_event({
                    'event_type': 'llm_call',
                    'ts': datetime.now(timezone.utc).isoformat(),
                    'session': self.session_id or 'unknown',
                    'round': None,  # Enemy calls don't have round context here
                    'agent_id': self.agent_id,
                    'agent_type': 'enemy',
                    'call_sequence': self.call_sequence,
                    'call_type': 'text:enemy_tactical',
                    'prompt': messages,
                    'response': response_text,
                    'model': model,
                    'temperature': temperature,
                    'tokens': {
                        'input': input_tokens,
                        'output': output_tokens,
                        'total': input_tokens + output_tokens,
                    }
                })
                self.call_sequence += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Enemy {self.agent_id}: Failed to log LLM call: {type(e).__name__}: {e}", exc_info=True)

        # Also log to human-readable agent prompt log if enabled
        if self.agent_prompt_logger:
            try:
                from token_utils import count_chat_tokens, count_text_tokens

                messages = [{"role": "user", "content": prompt}]
                model = self.llm_config.get('model', 'unknown')
                input_tokens = count_chat_tokens(messages, model)
                output_tokens = count_text_tokens(response_text, model)
                self.agent_prompt_logger.log_llm_call(
                    agent_id=self.agent_id,
                    round_num=None,  # Enemy calls don't have round context
                    call_sequence=self.call_sequence - 1,  # Already incremented above
                    prompt=prompt,  # Full prompt text
                    response=response_text,
                    model=model,
                    temperature=temperature,
                    tokens={
                        'input': input_tokens,
                        'output': output_tokens,
                        'total': input_tokens + output_tokens,
                    }
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Enemy {self.agent_id}: Failed to log to agent prompt logger: {e}")

        return {"content": response_text}


class SelfPlayingSession:
    """
    Orchestrates a complete self-playing game session with AI agents
    and optional human intervention.
    """
    
    def __init__(self, config_path: str = None, random_seed: Optional[int] = None,
                 replay_mode: bool = False, replay_config: Optional[Dict] = None,
                 llm_cache: Optional[Dict] = None, continue_from_round: Optional[int] = None,
                 log_agents_separately: bool = False):
        # In replay mode, config comes from replay_config instead of file
        if replay_mode and replay_config:
            self.config = replay_config
        elif config_path:
            self.config = self._load_config(config_path)
        else:
            raise ValueError("Must provide either config_path or replay_mode=True with replay_config")

        self.coordinator: Optional[GameCoordinator] = None
        self.agents: List[Any] = []
        # Per-enemy fallback LLM clients, cached by agent_id so their
        # call_sequence counter persists across rounds (replay-cache key).
        self._enemy_llm_clients: Dict[str, Any] = {}
        self._replay_agent_aliases: Dict[str, str] = {}
        self.human_interface: Optional[HumanInterface] = None
        self.session_id: Optional[str] = None
        self.session_data: List[Dict[str, Any]] = []
        self.running = False
        self.shared_state = SharedState()
        self.shared_state.session_config = self.config  # Store config for agents to access flags

        # Initialize persistent vendors from config
        self._initialize_persistent_vendors()

        # Initialize gated checkpoints from config (VIII.1 access gate)
        self._initialize_checkpoints()

        # Initialize persistent altars from config
        self._initialize_persistent_altars()

        self.voice_library = VoiceLibrary()
        self._turn_history: List[str] = []
        self._pending_resolutions: Dict[str, asyncio.Event] = {}  # Track when resolutions complete
        self._pending_declarations: Dict[str, asyncio.Event] = {}  # Track when declarations complete
        self._declared_actions: Dict[str, List[Dict[str, Any]]] = {}  # Buffer actions during declaration phase (supports multiple actions per agent)
        self._in_declaration_phase: bool = False  # Track current phase
        self._session_finalized: bool = False  # Teardown claimed (see _claim_session_finalization)
        self._scenario_ready: asyncio.Event = asyncio.Event()  # Track when scenario is generated
        self._synthesis_complete: asyncio.Event = asyncio.Event()  # Track when round synthesis is complete
        self._last_dm_narration: str = ""  # Track last DM narration for marker parsing
        self._session_end_status: Optional[str] = None  # Track if DM declared session end
        self._end_state_snapshot: Optional[Dict[str, Any]] = None  # Resolve-then-leap hook: set when a terminal clock resolves the scene
        self._end_reason: Optional[str] = None  # How the session ended: terminal_clock | dm_declaration | round_cap
        self._fatal_error: Optional[str] = None  # Track fatal agent errors for graceful termination

        # Replay mode
        self.replay_mode = replay_mode
        self.llm_cache = llm_cache or {}
        self.continue_from_round = continue_from_round  # Switch to live LLM after this round
        self.hybrid_clients: List[Any] = []  # Track hybrid clients for round updates

        # Initialize random seed for deterministic replay
        if random_seed is None:
            # Generate seed from current time if not provided
            random_seed = int(time.time() * 1000) % (2**31)
        self.random_seed = random_seed
        random.seed(random_seed)
        if replay_mode:
            print(f"🔁 Replay mode - Random seed: {random_seed}")
        else:
            print(f"Random seed: {random_seed}")

        # Initialize agent prompt logger if requested
        self.log_agents_separately = log_agents_separately
        self.agent_prompt_logger: Optional[AgentPromptLogger] = None
        if log_agents_separately:
            # Will be fully initialized after session_id is set during start_session()
            self.agent_prompt_logger = None  # Deferred until session_id available

        # Round statistics for ML training / balance analysis
        self._round_stats = {
            'actions_attempted': 0,
            'success_count': 0,
            'total_margin': 0,
            'damage_dealt_by_players': 0,
            'damage_taken_by_players': 0,
            'void_gained': 0,
            'void_lost': 0,
            'clocks_advanced': 0,
            'clocks_filled': 0
        }

        # Track if scenario had clocks (for detecting when all clocks expire/complete)
        self._had_active_clocks = False

        # Track character action history for failure loop detection
        # Format: {character_name: [(action_type, success_tier, void_change, round_num), ...]}
        self._character_action_history: Dict[str, List[tuple]] = {}

        # Track round synthesis history for debrief context
        # Format: [(round_num, synthesis_text), ...]
        self._round_synthesis_history: List[tuple] = []

        # Track current round's initiative order for logging
        # Format: {agent_id: initiative_score}
        self._current_initiative: Dict[str, int] = {}

        # Initialize mechanics systems
        print("Initializing mechanics systems...")
        self.shared_state.initialize_mechanics()
        print("✓ Mechanics engine ready")
        print("✓ Action validator ready")
        print("✓ Knowledge retrieval ready")

        # Initialize enemy combat manager
        self.enemy_combat = EnemyCombatManager(shared_state=self.shared_state)
        self.enemy_combat.initialize(self.config)
        # Add to shared state so players can access it for tactical prompts
        self.shared_state.enemy_combat = self.enemy_combat
        # Add session reference for round stats tracking
        self.shared_state.session = self
        if self.enemy_combat.enabled:
            print("✓ Enemy combat manager ENABLED")
        else:
            print("  Enemy combat manager disabled")

        # Spec 06: IFF/ROE mode flag — propagate to shared_state for subsystems
        self.iff_enabled = self.config.get('iff_enabled', False)
        self.shared_state.iff_enabled = self.iff_enabled
        if self.iff_enabled:
            print("✓ IFF/ROE mode ENABLED")

        # Load DM notes for scenario variety
        dm_notes_path = Path(self.config.get('output_dir', './multiagent_output')) / 'dm_notes.json'
        self.shared_state.load_dm_notes(str(dm_notes_path))
        self.dm_notes_path = dm_notes_path

    def _get_npc_llm_provider(self):
        """Get NPC LLM provider using the per-role fallback chain (Spec 11).

        NPC LLM fallback chain: npcs -> enemies -> dm.
        Falls back to self.enemy_combat.llm_provider for backward compat
        if no NPC-specific config is found.

        Returns:
            LLM provider instance, or None if no config available.
        """
        npc_llm_config = get_npc_llm_config(self.config)
        if npc_llm_config:
            try:
                from .llm_provider import LLMConfig, create_provider
                config = LLMConfig.from_dict(npc_llm_config, max_tokens=2000)
                provider = create_provider(config)
                logger.debug(f"NPC LLM provider created from per-role config ({config.provider}:{config.model})")
                return provider
            except Exception as e:
                logger.warning(f"Failed to create NPC LLM provider from config: {e}")

        # Ultimate fallback: use enemy_combat's provider (backward compat)
        if hasattr(self, 'enemy_combat') and hasattr(self.enemy_combat, 'llm_provider'):
            return self.enemy_combat.llm_provider
        return None

    def _initialize_persistent_vendors(self):
        """
        Initialize persistent vendors from session config.

        Spawns vendors defined in config['persistent_vendors'] into SharedState.
        These vendors persist across all rounds unless explicitly removed.

        NOTE: This is a minimal implementation for testing. Production gameplay
        should use DM-driven VendorSpawn structured output (not yet implemented).
        """
        persistent_vendors_config = self.config.get('persistent_vendors', [])

        if not persistent_vendors_config:
            logger.debug("No persistent_vendors in config")
            return

        from .energy_economy import Vendor, VendorItem, VendorType

        # Note: SharedState uses `current_vendors` attribute, accessed via add_vendor() method

        for vendor_config in persistent_vendors_config:
            # Parse inventory items
            inventory_items = []
            for item_config in vendor_config.get('inventory', []):
                item = VendorItem(
                    name=item_config['name'],
                    description=item_config['description'],
                    item_id=item_config.get('item_id'),  # FIX: Pass item_id from config (or None for auto-generation)
                    price_spark=item_config.get('price_spark', 0),
                    price_grain=item_config.get('price_grain', 0),
                    price_drip=item_config.get('price_drip', 0),
                    price_breath=item_config.get('price_breath', 0)
                )
                inventory_items.append(item)

            # Parse vendor type (default to human_trader)
            vendor_type_str = vendor_config.get('vendor_type', 'human_trader')
            try:
                vendor_type = VendorType[vendor_type_str.upper()]
            except KeyError:
                logger.warning(f"Unknown vendor_type '{vendor_type_str}', defaulting to HUMAN_TRADER")
                vendor_type = VendorType.HUMAN_TRADER

            # Create vendor
            vendor = Vendor(
                name=vendor_config['name'],
                faction=vendor_config.get('faction', 'Neutral'),
                inventory=inventory_items,
                greeting=vendor_config.get('greeting', 'Looking to trade?'),
                vendor_type=vendor_type,
                vendor_id=vendor_config.get('vendor_id')  # FIX: Pass vendor_id from config (or None for auto-generation)
            )

            # Add to shared state using proper method
            self.shared_state.add_vendor(vendor)

            logger.info(f"Initialized persistent vendor: {vendor.name} ({vendor_type_str}) with {len(inventory_items)} items, vendor_id={vendor.vendor_id}")

        print(f"✓ Loaded {len(persistent_vendors_config)} persistent vendor(s)")

    def _initialize_checkpoints(self):
        """Initialize gated checkpoints from config['starting_checkpoints'].

        Each entry: {checkpoint_id?, name, faction, soulcredit_requirement?,
        description?}. Nexus-aligned checkpoints gate on standing (VIII.1) and
        apply the universal Cut-Off (VIII.2). Enforced deterministically when a
        player action carries a checkpoint_id; surfaced to the DM otherwise.
        """
        checkpoints_config = self.config.get('starting_checkpoints', [])
        if not checkpoints_config:
            return

        from .energy_economy import Checkpoint

        for cp in checkpoints_config:
            checkpoint = Checkpoint(
                checkpoint_id=cp.get('checkpoint_id') or f"cp_{cp['name'].lower().replace(' ', '_')}",
                name=cp['name'],
                faction=cp.get('faction', 'Neutral'),
                soulcredit_requirement=cp.get('soulcredit_requirement', 0),
                description=cp.get('description', ''),
            )
            self.shared_state.add_checkpoint(checkpoint)
            logger.info(f"Initialized checkpoint: {checkpoint.name} "
                        f"({checkpoint.faction}, SC≥{checkpoint.soulcredit_requirement}), "
                        f"id={checkpoint.checkpoint_id}")

        print(f"✓ Loaded {len(checkpoints_config)} checkpoint(s)")

    def _initialize_persistent_altars(self):
        """
        Initialize persistent altars from session config.

        Spawns altars defined in config['scenario']['altars'] into SharedState.
        These altars persist across all rounds unless explicitly removed.
        """
        scenario_config = self.config.get('scenario', {})
        altars_config = scenario_config.get('altars', [])

        if not altars_config:
            logger.debug("No scenario.altars in config")
            return

        from .shared_state import Altar, AltarType

        for altar_config in altars_config:
            # Parse altar type
            altar_type_str = altar_config.get('altar_type', 'ritual_altar')
            try:
                altar_type = AltarType[altar_type_str.upper()]
            except KeyError:
                logger.warning(f"Unknown altar_type '{altar_type_str}', defaulting to RITUAL_ALTAR")
                altar_type = AltarType.RITUAL_ALTAR

            # Validate quality
            quality = altar_config.get('quality', 5)
            if not (1 <= quality <= 10):
                logger.warning(f"Altar quality {quality} out of range [1-10], clamping")
                quality = max(1, min(10, quality))

            # Create altar
            altar = Altar(
                altar_type=altar_type,
                quality=quality,
                location=altar_config.get('location', 'Unknown'),
                altar_id=altar_config.get('altar_id')  # None for auto-generation
            )

            # Add to shared state
            self.shared_state.add_altar(altar)

            bonus = altar.get_ritual_bonus()
            logger.info(f"Initialized altar: {altar.location} ({altar_type_str}, quality={quality}, +{bonus} bonus), altar_id={altar.altar_id}")

        print(f"✓ Loaded {len(altars_config)} ritual altar(s)")

    # NOTE: _inject_required_items_into_vendors() removed
    #
    # The DM already handles vendor spawning for required purchases via:
    # 1. force_vendor_gate → _create_vendor_gated_scenario() generates required_purchase
    # 2. DM spawns vendor from self.vendor_pool matching required_vendor_type
    # 3. Vendors in vendor_pool (create_standard_vendors()) have inventory designed for scenarios
    #
    # Vendor spawn frequency defaults to 3 (every 3rd round) in both session.py and dm.py.
    # To disable: set vendor_spawn_frequency: -1 or 0 in config.
    # For testing with persistent_vendors config:
    # - Set vendor_spawn_frequency: -1 to disable DM vendor spawning
    # - Manually configure persistent vendor inventory to include scenario-required items

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load session configuration."""
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)

            # Validate skill names are canonical
            self._validate_config_skills(config, config_path)

            return config
        except (FileNotFoundError, PermissionError) as e:
            logger.error(f"Failed to access config file {config_path}: {e}")
            raise
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse config file {config_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading config from {config_path}: {e}")
            raise

    def _validate_config_skills(self, config: Dict[str, Any], config_path: str):
        """
        Validate that all character skills use canonical names.

        Non-canonical skill names (like 'Notice' instead of 'Awareness') cause
        skill lookups to fail, resulting in all checks being treated as unskilled.

        Raises:
            ValueError: If non-canonical skill names are found
        """
        from .skill_mapping import validate_session_config_skills

        is_valid, errors = validate_session_config_skills(config, raise_on_error=False)

        if not is_valid:
            error_msg = f"\n❌ Session config '{config_path}' has non-canonical skill names:\n"
            for error in errors:
                error_msg += f"  • {error}\n"
            error_msg += "\nFix the skill names in the config file to use canonical names from skill_descriptions.py."
            logger.error(error_msg)
            raise ValueError(error_msg)
                
    async def start_session(self):
        """Start the complete self-playing session."""
        logger.debug("Starting self-playing session")

        # Start game coordinator
        socket_path = self.config.get('socket_path')
        self.coordinator = GameCoordinator(socket_path)
        await self.coordinator.start()

        # Register message handlers
        self.coordinator.message_bus.add_handler(
            'session_resolution_tracker',
            self._handle_action_resolved
        )
        self.coordinator.message_bus.add_handler(
            'session_declaration_buffer',
            self._handle_action_declared
        )
        self.coordinator.message_bus.add_handler(
            'session_scenario_tracker',
            self._handle_scenario_setup
        )
        self.coordinator.message_bus.add_handler(
            'session_dm_narration_tracker',
            self._handle_dm_narration
        )
        self.coordinator.message_bus.add_handler(
            'session_agent_error_tracker',
            self._handle_agent_error
        )

        # Start human interface if enabled
        if self.config.get('enable_human_interface', True):
            self.human_interface = HumanInterface(str(self.coordinator.message_bus.socket_path))
            await self.human_interface.start()

        # Create and start AI agents
        await self._create_agents()

        # Wait for all agents to be ready
        await self._wait_for_agents_ready()

        # Start the game session
        self.session_id = await self.coordinator.create_session(self.config)

        # Attach aeonisk-names-mcp client to the DM if enabled (off by default).
        # Done here — after self.session_id is set — so the reservation owner
        # string can be session-scoped for later cleanup.
        names_mcp_config = self.config.get('names_mcp') or {}
        if names_mcp_config.get('enabled') and getattr(self, 'dm_agent', None):
            try:
                from .names_client import NamesClient
                self.dm_agent.names_client = NamesClient(
                    owner=f"yags:{self.session_id}",
                    from_pool=names_mcp_config.get('from_pool', True),
                )
                logger.info(
                    f"📛 Aeonisk-names MCP enabled for NPC naming "
                    f"(from_pool={names_mcp_config.get('from_pool', True)})"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Aeonisk-names MCP client: {e}")

        # Initialize JSONL logger for machine-readable events
        from .mechanics import JSONLLogger
        output_dir = self.config.get('output_dir', './output')
        jsonl_logger = JSONLLogger(self.session_id, output_dir, config=self.config, random_seed=self.random_seed)

        # Attach logger to mechanics engine
        if self.shared_state and self.shared_state.mechanics_engine:
            self.shared_state.mechanics_engine.jsonl_logger = jsonl_logger
            print(f"✓ JSONL logging enabled: {jsonl_logger.log_file}")

        # Liveness sidecar: makes "finished", "crashed" and "hung" separable from
        # outside the process, so watchers don't have to grep stdout for a line a
        # killed run never prints. Best-effort — never let it break a session.
        self._status_output_dir = output_dir
        try:
            from .session_status import RUNNING, prune_status_files, write_status
            prune_status_files(output_dir)
            write_status(
                output_dir, self.session_id, RUNNING,
                round=0,
                max_turns=self.config.get('max_turns'),
                jsonl=str(jsonl_logger.log_file),
                config=self.config.get('session_name'),
            )
        except Exception as e:  # pragma: no cover - telemetry must not gate play
            logger.debug(f"Status sidecar unavailable: {e}")

        # Initialize agent prompt logger if requested
        if self.log_agents_separately:
            self.agent_prompt_logger = AgentPromptLogger(
                output_dir="agent_logs",
                session_id=self.session_id
            )
            print(f"✓ Agent prompt logging enabled: agent_logs/{self.session_id}/")

        # Load starting_clocks from config if present
        if 'starting_clocks' in self.config and self.config['starting_clocks']:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                from .schemas.story_events import NewClock
                for clock_config in self.config['starting_clocks']:
                    try:
                        # Validate clock using NewClock schema
                        clock = NewClock(**clock_config)
                        # Add to mechanics.scene_clocks
                        from .mechanics import SceneClock
                        scene_clock = SceneClock(
                            name=clock.name,
                            current=clock.current_ticks,
                            maximum=clock.max_ticks,
                            description=clock.description,
                            advance_meaning=clock.advance_meaning,
                            regress_meaning=clock.regress_meaning,
                            filled_consequence=clock.filled_consequence,
                            is_terminal=getattr(clock, 'is_terminal_clock', False),
                            terminal_outcome=getattr(clock, 'terminal_outcome', 'victory')
                        )
                        mechanics.scene_clocks[clock.name] = scene_clock
                        logger.info(f"Loaded starting clock: {clock.name} ({clock.current_ticks}/{clock.max_ticks})")

                        # Log clock spawn (starting clocks created at round 0/null)
                        if mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_clock_spawn(
                                clock.name,
                                clock.max_ticks,
                                clock.description,
                                round_num=None,  # Session start, no round yet
                                current_ticks=clock.current_ticks,
                                advance_meaning=clock.advance_meaning,
                                regress_meaning=clock.regress_meaning,
                                filled_consequence=clock.filled_consequence
                            )
                    except Exception as e:
                        logger.warning(f"Failed to load starting clock {clock_config.get('name', 'unknown')}: {e}")
                print(f"✓ Loaded {len(self.config['starting_clocks'])} starting clock(s)")

        # Create and attach LLMCallLogger instances to all agents for replay functionality
        from .llm_logger import LLMCallLogger
        for agent in self.agents:
            agent_type = 'dm' if agent.agent_id.startswith('dm') else ('enemy' if agent.agent_id.startswith('enemy') else 'player')
            llm_logger_instance = LLMCallLogger(
                agent_id=agent.agent_id,
                agent_type=agent_type,
                jsonl_logger=jsonl_logger,
                session_id=self.session_id
            )
            agent.llm_logger = llm_logger_instance

            # Also attach agent prompt logger if enabled
            if self.agent_prompt_logger:
                agent.agent_prompt_logger = self.agent_prompt_logger

        # Attach LLM logger to enemy combat manager for token tracking
        if self.enemy_combat.enabled:
            enemy_llm_logger = LLMCallLogger(
                agent_id='enemy_combat',
                agent_type='enemy',
                jsonl_logger=jsonl_logger,
                session_id=self.session_id
            )
            self.enemy_combat.llm_logger = enemy_llm_logger

        print(f"✓ LLM call logging enabled for {len(self.agents)} agents")

        # Wait for DM to generate initial scenario before starting gameplay
        # SESSION_START triggers scenario generation, wait for SCENARIO_SETUP message
        print("Waiting for scenario generation...")
        await self._scenario_ready.wait()
        print("Scenario ready!")

        # Resume-from-divergence: overlay exact recorded vitals on the freshly
        # created party + spawned enemies (no-op unless config has resume_state)
        self._apply_resume_state()

        # Give players time to receive and process SCENARIO_SETUP message
        # before starting declarations (fixes race condition where enemies
        # declare before players see the scenario)
        print("Waiting for players to process scenario...")
        await asyncio.sleep(2)
        print("All agents ready to begin!")

        # Run the gameplay loop
        await self._run_gameplay_loop()
        
    async def _create_agents(self):
        """Create and start all AI agents."""
        agents_config = self.config.get('agents', {})

        # Create MockLLMClient or HybridLLMClient instances if in replay mode
        dm_llm_client = None
        if self.replay_mode:
            if self.continue_from_round is not None:
                # Hybrid mode: cached up to round N, then live
                from .llm_logger import HybridLLMClient
                dm_llm_client = HybridLLMClient(self.llm_cache, agent_id='dm_01', continue_from_round=self.continue_from_round)
                self.hybrid_clients.append(dm_llm_client)
                print(f"✓ Created HybridLLMClient for DM (replay rounds 1-{self.continue_from_round}, then LIVE)")
            else:
                # Full replay mode: all cached
                from .llm_logger import MockLLMClient
                dm_llm_client = MockLLMClient(self.llm_cache, agent_id='dm_01')
                print("✓ Created MockLLMClient for DM (replay mode)")

        # Create DM agent
        dm_config = agents_config.get('dm', {})
        dm_voice = self.voice_library.get_profile('ritual_scholar')

        # Pass force_scenario if present (for automated testing)
        force_scenario = self.config.get('force_scenario', None)

        dm_agent = AIDMAgent(
            agent_id='dm_01',
            socket_path=str(self.coordinator.message_bus.socket_path),
            llm_config=dm_config.get('llm', {}),
            voice_profile=dm_voice,
            shared_state=self.shared_state,
            prompt_enricher=self.voice_library.enrich_prompt,
            history_supplier=self._recent_history,
            force_scenario=force_scenario,
            llm_client=dm_llm_client,
            session_config=self.config,  # Pass full session config for persistent vendors
            # names_client attached in start_session() after session_id is known
        )
        if self.replay_mode and dm_llm_client is not None:
            from .llm_logger import ReplayStructuredProvider
            dm_agent.llm_provider = ReplayStructuredProvider(dm_llm_client)
        self.dm_agent = dm_agent  # Held for post-init wiring (names_mcp, etc.)
        self.agents.append(dm_agent)
        await dm_agent.start()

        # Create player agents (randomly select from pool based on party_size)
        import random
        players_config = agents_config.get('players', [])
        party_size = self.config.get('party_size', 2)  # Default to 2 if not specified

        # Randomly select players from the pool
        if len(players_config) > party_size:
            selected_players = random.sample(players_config, party_size)
            logger.debug(f"Selected {party_size} players: {[p['name'] for p in selected_players]}")
        else:
            selected_players = players_config
            logger.debug(f"Using all {len(selected_players)} players from pool")

        # Update config to only include selected players (so DM sees correct party)
        self.config['agents']['players'] = selected_players

        assignments = self.voice_library.assign_to_agents(
            [f'player_{i+1:02d}' for i in range(len(selected_players))]
        )
        for i, player_config in enumerate(selected_players):
            agent_id = f'player_{i+1:02d}'

            # Create MockLLMClient or HybridLLMClient for this player if in replay mode
            player_llm_client = None
            if self.replay_mode:
                if self.continue_from_round is not None:
                    # Hybrid mode: cached up to round N, then live
                    from .llm_logger import HybridLLMClient
                    player_llm_client = HybridLLMClient(self.llm_cache, agent_id=agent_id, continue_from_round=self.continue_from_round)
                    self.hybrid_clients.append(player_llm_client)
                    print(f"✓ Created HybridLLMClient for {agent_id} (replay rounds 1-{self.continue_from_round}, then LIVE)")
                else:
                    # Full replay mode: all cached
                    from .llm_logger import MockLLMClient
                    player_llm_client = MockLLMClient(self.llm_cache, agent_id=agent_id)
                    print(f"✓ Created MockLLMClient for {agent_id} (replay mode)")

            player_agent = AIPlayerAgent(
                agent_id=agent_id,
                socket_path=str(self.coordinator.message_bus.socket_path),
                character_config=player_config,
                llm_config=player_config.get('llm', {}),
                voice_profile=assignments.get(agent_id),
                shared_state=self.shared_state,
                prompt_enricher=self.voice_library.enrich_prompt,
                history_supplier=self._recent_history,
                llm_client=player_llm_client,
                agent_prompt_logger=self.agent_prompt_logger,
            )
            self.agents.append(player_agent)
            await player_agent.start()

        # Initialize mechanics state for all players
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics:
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
            # Populate player_agents in shared_state for ally buff targeting
            self.shared_state.player_agents = player_agents
            # Enforce mode: the post-resolution magistrate becomes the sole
            # ledger writer, so the narration call must NOT apply its own
            # soulcredit/void deltas (would double-count). Flag it once here;
            # the two dm.py apply blocks honor it. Narrator's proposed deltas
            # still live in the logged ActionResolution effects for diffing.
            mechanics.suppress_narration_economy = (
                self.config.get('post_resolution_adjudication') == 'enforce')
            # Party context feature flags (player prompts read these)
            self.shared_state.party_capabilities_enabled = self.config.get(
                'party_capabilities_enabled', True)
            self.shared_state.party_chat_enabled = self.config.get(
                'party_chat_enabled', True)
            for player in player_agents:
                # Initialize void state with character's starting value
                initial_void = getattr(player.character_state, 'void_score', 0)
                void_state = mechanics.get_void_state(player.agent_id)
                void_state.score = initial_void
                logger.debug(f"Initialized {player.character_state.name} void: {initial_void}")

                # Initialize soulcredit state with character's starting value
                initial_sc = getattr(player.character_state, 'soulcredit', 0)
                mechanics.get_soulcredit_state(player.agent_id, initial_score=initial_sc)
                logger.debug(f"Initialized {player.character_state.name} soulcredit: {initial_sc}")

                # Degrade Raw Seeds (1 cycle per session)
                if hasattr(player.character_state, 'energy_purse') and player.character_state.energy_purse:
                    player.character_state.energy_purse.degrade_raw_seeds(cycles=1)
                    raw_count = player.character_state.energy_purse.count_seeds(SeedType.RAW)
                    hollow_count = player.character_state.energy_purse.count_seeds(SeedType.HOLLOW)
                    if hollow_count > 0:
                        logger.debug(f"{player.character_state.name}: Raw Seeds degraded (now {raw_count} Raw, {hollow_count} Hollow)")

        logger.debug(f"Created {len(self.agents)} agents")

        # Ensure all characters have bonds=[] initialized
        for agent in player_agents:
            if hasattr(agent, 'character_state') and not hasattr(agent.character_state, 'bonds'):
                agent.character_state.bonds = []

        # Check bonds_enabled config flag (default: True)
        bonds_enabled = self.config.get('bonds_enabled', True)

        # Auto-generate bonds if enabled (BEFORE loading explicit starting_bonds)
        if bonds_enabled and 'generate_bonds' in self.config and self.config['generate_bonds'].get('enabled', False):
            try:
                await self._generate_bonds_automatically(player_agents)
            except Exception as e:
                logger.error(f"Failed to auto-generate bonds: {e}")
        elif bonds_enabled and len(player_agents) >= 2 and 'starting_bonds' not in self.config:
            # Generate default bond matrix when no explicit bonds configured
            try:
                from .mechanics import generate_default_bond_matrix
                from .schemas.shared_types import Bond, BondType, BondStatus

                character_names = []
                factions = {}
                for agent in player_agents:
                    if hasattr(agent, 'character_state'):
                        name = agent.character_state.name
                        character_names.append(name)
                        factions[name] = agent.character_state.faction

                bond_suggestions = generate_default_bond_matrix(
                    character_names=character_names,
                    factions=factions,
                    random_seed=self.random_seed,
                )

                bonds_created = 0
                for idx, suggestion in enumerate(bond_suggestions):
                    char_a_agent = None
                    char_b_agent = None
                    for agent in player_agents:
                        if hasattr(agent, 'character_state'):
                            if agent.character_state.name == suggestion['character_a']:
                                char_a_agent = agent
                            if agent.character_state.name == suggestion['character_b']:
                                char_b_agent = agent

                    if not char_a_agent or not char_b_agent:
                        continue

                    bond_type = BondType(suggestion['bond_type'])
                    bond = Bond(
                        bond_id=f"bond_default_{idx:03d}",
                        character_a=suggestion['character_a'],
                        character_b=suggestion['character_b'],
                        bond_type=bond_type,
                        status=BondStatus.ACTIVE,
                        formed_round=0,
                        witnessed_by=[],
                        narrative_description="",
                    )

                    char_a_agent.character_state.bonds.append(bond)
                    char_b_agent.character_state.bonds.append(bond)
                    bonds_created += 1

                if bonds_created > 0:
                    logger.info(f"Generated {bonds_created} default bonds for party of {len(player_agents)}")
            except Exception as e:
                logger.error(f"Failed to generate default bond matrix: {e}")
        elif not bonds_enabled:
            logger.info("Bond generation skipped (bonds_enabled=False)")

        # Load starting_bonds from config (AFTER agents created)
        if 'starting_bonds' in self.config and self.config['starting_bonds']:
            try:
                from .schemas.shared_types import Bond, BondType, BondStatus

                bond_configs = self.config['starting_bonds']
                bonds_loaded = 0

                # Validate and create bonds
                for idx, bond_config in enumerate(bond_configs):
                    # Required fields
                    if 'character_a' not in bond_config:
                        logger.warning(f"Starting bond {idx} missing 'character_a', skipping")
                        continue
                    if 'character_b' not in bond_config:
                        logger.warning(f"Starting bond {idx} missing 'character_b', skipping")
                        continue
                    if 'bond_type' not in bond_config:
                        logger.warning(f"Starting bond {idx} missing 'bond_type', skipping")
                        continue

                    char_a = bond_config['character_a']
                    char_b = bond_config['character_b']

                    # Find characters in player_agents (now they exist!)
                    char_a_agent = None
                    char_b_agent = None
                    for agent in player_agents:
                        if hasattr(agent, 'character_state') and agent.character_state.name == char_a:
                            char_a_agent = agent
                        if hasattr(agent, 'character_state') and agent.character_state.name == char_b:
                            char_b_agent = agent

                    if not char_a_agent:
                        logger.warning(f"Starting bond {idx}: character '{char_a}' not found in party, skipping")
                        continue
                    if not char_b_agent:
                        logger.warning(f"Starting bond {idx}: character '{char_b}' not found in party, skipping")
                        continue

                    # Validate not self-bond
                    if char_a == char_b:
                        logger.warning(f"Starting bond {idx}: cannot bond '{char_a}' with themselves, skipping")
                        continue

                    # Validate bond type
                    try:
                        bond_type = BondType(bond_config['bond_type'])
                    except ValueError:
                        logger.warning(f"Starting bond {idx}: invalid bond_type '{bond_config['bond_type']}', skipping")
                        continue

                    # Create bond instance
                    bond_id = f"bond_{bonds_loaded + 1:03d}"
                    bond = Bond(
                        bond_id=bond_id,
                        character_a=char_a,
                        character_b=char_b,
                        bond_type=bond_type,
                        status=BondStatus.ACTIVE,
                        formed_round=0,  # Starting bonds formed before session
                        witnessed_by=bond_config.get('witnessed_by', []),
                        narrative_description=bond_config.get('narrative', '')
                    )

                    # Add bond to both characters
                    if hasattr(char_a_agent.character_state, 'bonds'):
                        char_a_agent.character_state.bonds.append(bond)
                    if hasattr(char_b_agent.character_state, 'bonds'):
                        char_b_agent.character_state.bonds.append(bond)

                    bonds_loaded += 1
                    logger.info(f"Loaded starting bond: {char_a} ↔ {char_b} ({bond_type.value})")

                if bonds_loaded > 0:
                    print(f"✓ Loaded {bonds_loaded} starting bond(s)")
            except Exception as e:
                logger.warning(f"Failed to load starting bonds: {e}")

    async def _generate_bonds_automatically(self, player_agents):
        """
        Auto-generate bond network and narratives using LLM.

        Called when config has generate_bonds.enabled = true.
        Uses bond_backstory_generator to create bonds deterministically,
        then generates narratives via LLM.
        """
        from .schemas.shared_types import Bond, BondType, BondStatus
        import random

        logger.info("🔗 Auto-generating bond network...")

        # Extract generation parameters
        gen_config = self.config.get('generate_bonds', {})
        min_bonds = gen_config.get('min_bonds', 2)
        max_bonds = gen_config.get('max_bonds', 5)
        use_scenario_context = gen_config.get('use_scenario_context', True)

        # Gather character info
        character_names = []
        factions = {}
        archetypes = {}

        for agent in player_agents:
            if hasattr(agent, 'character_state'):
                name = agent.character_state.name
                character_names.append(name)
                factions[name] = agent.character_state.faction
                # Get archetype from config (not stored in character_state)
                for player_config in self.config.get('agents', {}).get('players', []):
                    if player_config['name'] == name:
                        archetypes[name] = player_config.get('archetype', 'Unknown')
                        break

        if len(character_names) < 2:
            logger.info("Party size < 2, skipping bond generation")
            return

        # Generate bond structure (deterministic)
        bond_suggestions = self._generate_bond_matrix(
            character_names=character_names,
            factions=factions,
            archetypes=archetypes,
            min_bonds=min_bonds,
            max_bonds=max_bonds,
            random_seed=self.random_seed
        )

        if not bond_suggestions:
            logger.info("No bonds generated")
            return

        # Print bond matrix structure
        print("\n🔗 Generated Bond Network:")
        for idx, suggestion in enumerate(bond_suggestions, 1):
            print(f"  {idx}. {suggestion['character_a']} ↔ {suggestion['character_b']} ({suggestion['bond_type']})")
        print()

        # Generate narratives via LLM
        scenario_context = (self.config.get('scenario_hint', '') or self.config.get('_scenario_hint', '')) if use_scenario_context else None
        bond_suggestions = await self._generate_bond_narratives(
            bond_suggestions=bond_suggestions,
            character_names=character_names,
            factions=factions,
            archetypes=archetypes,
            scenario_context=scenario_context
        )

        # Convert to Bond instances and assign to characters
        bonds_created = 0
        for idx, suggestion in enumerate(bond_suggestions):
            # Find character agents
            char_a_agent = None
            char_b_agent = None
            for agent in player_agents:
                if hasattr(agent, 'character_state'):
                    if agent.character_state.name == suggestion['character_a']:
                        char_a_agent = agent
                    if agent.character_state.name == suggestion['character_b']:
                        char_b_agent = agent

            if not char_a_agent or not char_b_agent:
                logger.warning(f"Could not find agents for bond {suggestion['character_a']} ↔ {suggestion['character_b']}")
                continue

            # Create bond
            bond_id = f"bond_gen_{idx:03d}"
            try:
                bond_type = BondType(suggestion['bond_type'])
            except ValueError:
                logger.warning(f"Invalid bond type '{suggestion['bond_type']}', using KINSHIP")
                bond_type = BondType.KINSHIP

            bond = Bond(
                bond_id=bond_id,
                character_a=suggestion['character_a'],
                character_b=suggestion['character_b'],
                bond_type=bond_type,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=suggestion.get('witnessed_by', []),
                narrative_description=suggestion.get('narrative', '')
            )

            # Add to both characters
            if hasattr(char_a_agent.character_state, 'bonds'):
                char_a_agent.character_state.bonds.append(bond)
            if hasattr(char_b_agent.character_state, 'bonds'):
                char_b_agent.character_state.bonds.append(bond)

            bonds_created += 1
            logger.info(f"Generated bond: {suggestion['character_a']} ↔ {suggestion['character_b']} ({bond_type.value})")

        # Print bond backstories
        print(f"\n📖 Bond Backstories ({bonds_created} bonds):")
        for idx, suggestion in enumerate(bond_suggestions, 1):
            print(f"\n  {idx}. {suggestion['character_a']} ↔ {suggestion['character_b']} ({suggestion['bond_type']})")
            narrative = suggestion.get('narrative', 'No narrative generated')
            # Wrap text at 80 chars for readability
            import textwrap
            wrapped = textwrap.fill(narrative, width=76, initial_indent="     ", subsequent_indent="     ")
            print(wrapped)
        print()

    def _generate_bond_matrix(self, character_names, factions, archetypes, min_bonds, max_bonds, random_seed):
        """Generate bond network structure (no narratives yet)."""
        if random_seed is not None:
            random.seed(random_seed)

        party_size = len(character_names)
        bond_counts = {name: 0 for name in character_names}
        num_bonds = min(max_bonds, max(min_bonds, party_size))

        bonds = []
        attempts = 0
        max_attempts = 100

        while len(bonds) < num_bonds and attempts < max_attempts:
            attempts += 1
            char_a, char_b = random.sample(character_names, 2)

            # Check constraints
            if (char_a, char_b) in bonds or (char_b, char_a) in bonds:
                continue
            if bond_counts[char_a] >= 3 or bond_counts[char_b] >= 3:
                continue
            if factions.get(char_a) == "freeborn" and bond_counts[char_a] >= 1:
                continue
            if factions.get(char_b) == "freeborn" and bond_counts[char_b] >= 1:
                continue

            bonds.append((char_a, char_b))
            bond_counts[char_a] += 1
            bond_counts[char_b] += 1

        # Ensure all characters have at least 1 bond
        unbonded = [name for name, count in bond_counts.items() if count == 0]
        for char in unbonded:
            candidates = [
                other for other in character_names
                if other != char and bond_counts[other] < 3
                and (char, other) not in bonds and (other, char) not in bonds
            ]
            if factions.get(char) == "freeborn" and bond_counts[char] >= 1:
                continue
            if candidates:
                partner = random.choice(candidates)
                bonds.append((char, partner))
                bond_counts[char] += 1
                bond_counts[partner] += 1

        # Assign bond types
        suggestions = []
        for char_a, char_b in bonds:
            bond_type = self._suggest_bond_type(char_a, char_b, factions, archetypes)
            witness_candidates = [n for n in character_names if n != char_a and n != char_b]
            witnessed_by = [random.choice(witness_candidates)] if witness_candidates and random.random() < 0.4 else []

            suggestions.append({
                'character_a': char_a,
                'character_b': char_b,
                'bond_type': bond_type,
                'narrative': '',
                'witnessed_by': witnessed_by
            })

        return suggestions

    def _suggest_bond_type(self, char_a, char_b, factions, archetypes):
        """Suggest bond type based on factions/archetypes."""
        import random

        faction_a = factions.get(char_a, '')
        faction_b = factions.get(char_b, '')
        same_faction = (faction_a == faction_b)
        is_freeborn = (faction_a == "freeborn" or faction_b == "freeborn")

        if is_freeborn:
            return random.choice(["kinship", "passion"])
        if same_faction:
            return random.choice(["kinship", "faction"])
        return random.choice(["passion", "debt", "voidward"])

    async def _generate_bond_narratives(self, bond_suggestions, character_names, factions, archetypes, scenario_context):
        """Generate narratives using DM's LLM provider."""
        if not bond_suggestions:
            return []

        # Find DM agent to use its LLM provider
        dm_agent = None
        for agent in self.agents:
            if hasattr(agent, 'agent_id') and 'dm' in agent.agent_id:
                dm_agent = agent
                break

        if not dm_agent or not hasattr(dm_agent, 'llm_provider'):
            logger.warning("No DM LLM provider found, using generic narratives")
            for bond in bond_suggestions:
                bond['narrative'] = f"{bond['character_a']} and {bond['character_b']} share a {bond['bond_type']} bond formed through shared hardship."
            return bond_suggestions

        # Build prompt
        party_info = "\n".join([
            f"- {name} ({archetypes.get(name, 'Unknown')}, {factions.get(name, 'Unknown')} faction)"
            for name in character_names
        ])

        bond_list = "\n".join([
            f"{i+1}. {b['character_a']} ↔ {b['character_b']} ({b['bond_type']})"
            for i, b in enumerate(bond_suggestions)
        ])

        # Determine if this is a social scenario
        is_social = scenario_context and any(word in scenario_context.lower() for word in ['social', 'network', 'gymbar', 'lounge', 'bar', 'dialogue'])

        if is_social:
            prompt = f"""Generate bond backstories for an Aeonisk RPG party in a SOCIAL scenario (networking event, no combat).

**Party:**
{party_info}

**Bonds:**
{bond_list}

**Scenario:** {scenario_context if scenario_context else "Social networking event"}

**Requirements:**
1. Each narrative: 1-2 sentences explaining HOW the bond formed
2. Focus on SOCIAL connections (business deals, shared interests, mentorship, attraction, debts)
3. Bonds should create natural conversation hooks and inter-character dynamics
4. Reference professional relationships, past collaborations, or personal connections
5. Tone: Professional but with personal depth (not combat/trauma focused)
6. Make bonds RELEVANT to the social setting

**Output format:** Numbered list ONLY, one line per bond, no extra text.

Example:
1. Maya closed a major Seed deal for Marcus's security firm last year, and he owes her a favor worth 10,000 drip.
2. Sienna counseled Echo through void-corruption trauma, and Echo trusts them completely despite their espionage background.
3. Marcus and Sienna met at the gym and bonded over shared dedication to physical and spiritual discipline.

Generate narratives (numbered list only):"""
        else:
            prompt = f"""Generate bond backstories for an Aeonisk RPG party.

**Party:**
{party_info}

**Bonds:**
{bond_list}

**Scenario:** {scenario_context if scenario_context else "Void investigation mission"}

**Requirements:**
1. Each narrative: 1-2 sentences explaining HOW the bond formed
2. Reference void corruption, Sovereign Rupture, or specific factions/locations
3. Noir/sci-fi tone (dark, gritty, survival-focused)
4. Avoid generic phrases like "formed through shared hardship"

**Output format:** Numbered list ONLY, one line per bond, no extra text.

Example:
1. Alice and Bob are siblings, separated during the Sovereign Rupture but reunited when Alice found Bob in a Voidguard facility.
2. Charlie owes Dana a life-debt after Dana pulled them from a void-corrupted station seconds before reactor meltdown.

Generate narratives (numbered list only):"""

        try:
            # Use DM's LLM provider client directly for text generation
            provider_type = type(dm_agent.llm_provider).__name__

            if 'Claude' in provider_type and hasattr(dm_agent.llm_provider, 'client'):
                # Anthropic/Claude provider
                messages_response = dm_agent.llm_provider.client.messages.create(
                    model=dm_agent.llm_provider.config.model,
                    max_tokens=800,
                    temperature=dm_agent.llm_config.get('temperature', 1.0),
                    system="You are a creative writer for the Aeonisk dark sci-fi setting.",
                    messages=[{"role": "user", "content": prompt}]
                )
                response = messages_response.content[0].text

            elif 'OpenAI' in provider_type and hasattr(dm_agent.llm_provider, 'client'):
                # OpenAI provider (gpt-5-mini uses max_completion_tokens instead of max_tokens)
                # Note: gpt-5-mini only supports temperature=1.0
                chat_response = dm_agent.llm_provider.client.chat.completions.create(
                    model=dm_agent.llm_provider.config.model,
                    max_completion_tokens=800,  # gpt-5-mini parameter name
                    temperature=1.0,  # gpt-5-mini only supports 1.0
                    messages=[
                        {"role": "system", "content": "You are a creative writer for the Aeonisk dark sci-fi setting."},
                        {"role": "user", "content": prompt}
                    ]
                )
                response = chat_response.choices[0].message.content
                # Check for refusal
                if hasattr(chat_response.choices[0].message, 'refusal') and chat_response.choices[0].message.refusal:
                    logger.warning(f"OpenAI refused generation: {chat_response.choices[0].message.refusal}")
                    response = ""
                if not response or response.strip() == "":
                    logger.warning(f"OpenAI returned empty response. Finish reason: {chat_response.choices[0].finish_reason}")

            else:
                # Fallback for unknown providers
                logger.warning(f"Unknown LLM provider type: {provider_type}, using generic narratives")
                response = "Generic narrative for all bonds."

            # Debug: log raw LLM response
            logger.debug(f"LLM narrative response: {response[:500]}")

            # Parse numbered list
            lines = [line.strip() for line in response.strip().split('\n') if line.strip()]
            narratives = []
            for line in lines:
                if '. ' in line and line[0].isdigit():
                    # Split on first ". " to handle numbered list format
                    parts = line.split('. ', 1)
                    if len(parts) == 2:
                        narratives.append(parts[1].strip())
                elif line and not line[0].isdigit():
                    # Non-numbered line, might be continuation
                    if narratives:
                        # Append to last narrative if it looks like a continuation
                        narratives[-1] += " " + line.strip()
                    else:
                        narratives.append(line.strip())

            # Assign narratives (with context-aware fallbacks)
            for i, bond in enumerate(bond_suggestions):
                if i < len(narratives) and narratives[i]:
                    bond['narrative'] = narratives[i]
                else:
                    # Context-aware fallback based on bond type and scenario
                    if is_social:
                        fallbacks = {
                            'debt': f"{bond['character_a']} negotiated a crucial deal for {bond['character_b']} last year, establishing a professional debt.",
                            'passion': f"{bond['character_a']} and {bond['character_b']} met at a networking event and formed an intense personal connection.",
                            'kinship': f"{bond['character_a']} and {bond['character_b']} grew up in the same station district and consider each other family.",
                            'faction': f"{bond['character_a']} and {bond['character_b']} work together regularly and share faction loyalties.",
                            'voidward': f"{bond['character_a']} and {bond['character_b']} both survived void exposure and understand each other's struggles.",
                            'ascendancy': f"{bond['character_a']} mentored {bond['character_b']} in professional skills, forming a lasting bond."
                        }
                    else:
                        fallbacks = {
                            'debt': f"{bond['character_a']} saved {bond['character_b']}'s life during a void incursion.",
                            'passion': f"{bond['character_a']} and {bond['character_b']} became lovers while surviving a corrupted station.",
                            'kinship': f"{bond['character_a']} and {bond['character_b']} are siblings separated during the Sovereign Rupture.",
                            'faction': f"{bond['character_a']} and {bond['character_b']} bonded through shared faction service.",
                            'voidward': f"{bond['character_a']} and {bond['character_b']} survived void corruption together.",
                            'ascendancy': f"{bond['character_a']} trained {bond['character_b']} in combat during a dangerous mission."
                        }
                    bond['narrative'] = fallbacks.get(bond['bond_type'],
                        f"{bond['character_a']} and {bond['character_b']} share a {bond['bond_type']} bond.")

            logger.info(f"Generated {len(narratives)} bond narratives via LLM")
            return bond_suggestions

        except Exception as e:
            logger.error(f"Failed to generate narratives via LLM: {e}")
            for bond in bond_suggestions:
                bond['narrative'] = f"{bond['character_a']} and {bond['character_b']} share a {bond['bond_type']} bond."
            return bond_suggestions

    async def _wait_for_agents_ready(self):
        """Wait for all agents to signal readiness."""
        # Simple wait - you could enhance with proper synchronization
        await asyncio.sleep(2)
        logger.debug("All agents ready")
        
    async def _run_gameplay_loop(self):
        """Run the main gameplay loop."""
        self.running = True
        round_count = 0
        max_rounds = self.config.get('max_turns', 50)

        print(f"\n=== Starting Session {self.session_id} ===")

        # Display git commit for version tracking
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                # Extract git commit from the session_start event we just logged
                import subprocess
                try:
                    result = subprocess.run(
                        ['git', 'rev-parse', '--short', 'HEAD'],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    if result.returncode == 0:
                        git_commit = result.stdout.strip()
                        print(f"Git commit: {git_commit}")
                except Exception:
                    # Git metadata is optional provenance; absence is not an error.
                    pass

        print(f"Max rounds: {max_rounds}")
        print(f"Human interface: {'Enabled' if self.human_interface else 'Disabled'}")

        # Show selected players
        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
        if player_agents:
            print(f"Selected Players:")
            for player in player_agents:
                print(f"  - {player.character_state.name} ({player.character_state.faction})")
        print()

        # Run pre-round entity lifecycle BEFORE round 1
        # This allows DM to spawn additional entities based on the scenario
        # (vendors, bystanders, environmental objects, patrols)
        # Note: initial_enemies and initial_npcs from config have already been processed
        # in _handle_scenario_setup() before we get here
        await self._run_pre_round_entity_lifecycle()

        while self.running:
            round_count += 1
            print(f"\n--- Round {round_count} ---")
            self._turn_history.append(f"Round {round_count} begins")
            self._heartbeat(round_count)

            # Reset void caps for all characters at round start
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                mechanics.current_round = round_count  # Update round counter for logging

                # Start new correlation_id for this round's events
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.start_round(round_count)

                # Update hybrid clients with new round (for continue-from-round mode)
                if self.hybrid_clients:
                    for client in self.hybrid_clients:
                        client.set_round(round_count)
                        logger.debug(f"Updated hybrid client round to {round_count}")

                # Log round start event
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_round_start(round_count)

                for agent_id, void_state in mechanics.void_states.items():
                    void_state.reset_round_void()

                # Tick condition durations at round start
                if hasattr(mechanics, 'conditions'):
                    for agent_id in list(mechanics.conditions.keys()):
                        mechanics.tick_conditions(agent_id)

            # Expire stealth at round start
            if self.shared_state:
                self.shared_state.expire_stealth(round_count)

            # Clear declared actions and defence tokens from previous round
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
            for agent in player_agents:
                if hasattr(agent, 'declared_actions_this_round'):
                    agent.declared_actions_this_round.clear()
                    logger.debug(f"Cleared declared actions for {agent.character_state.name}")
                # Rotate party chatter: this round's calls become last
                # round's context (see party_context.py)
                if hasattr(agent, 'party_chatter_this_round'):
                    agent.party_chatter_last_round = agent.party_chatter_this_round
                    agent.party_chatter_this_round = []
                # Reset defence tokens at round start (must re-declare each round)
                if hasattr(agent, 'defence_token'):
                    agent.defence_token = None

            # Reset NPC defence tokens at round start
            if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                for npc in self.shared_state.npc_agents:
                    if hasattr(npc, 'defence_token'):
                        npc.defence_token = None

            # Run round with initiative-based turns
            combat_continues = await self._run_initiative_round()

            # Check if all players defeated (TPK)
            if not combat_continues:
                print("\n=== SESSION ENDED - TOTAL PARTY KILL ===")
                # A TPK is a real ending: record it as a defeat and emit the
                # end_state_snapshot so the renderer (and the continuation gate)
                # know everyone died -- otherwise it exited with no snapshot and
                # the dead were rendered giving an epilogue debrief.
                self._session_end_status = 'defeat'
                self._end_reason = 'tpk'
                await self._check_end_conditions()
                break

            # Fail-closed synthesis aborts the session; skip the DM turn.
            if self._end_reason == 'round_synthesis_failed':
                await self._check_end_conditions()
                break

            # Run DM turn at end of round
            await self._run_dm_turn()

            # Check for random vendor spawns
            await self._check_vendor_spawn(round_count)

            # Check if we've completed enough rounds
            if round_count >= max_rounds:
                print(f"\n=== Completed {round_count} rounds ===")
                # Resolve any still-open scene by clock polarity (aversion victory for
                # held-off doom clocks; draw otherwise) and emit the end_state_snapshot,
                # so a cap ending still feeds the resolve-then-leap continuation.
                self._resolve_at_round_cap()
                await self._check_end_conditions()
                break

            # Check for session end conditions
            if await self._check_end_conditions():
                break

            # Brief pause between rounds
            await asyncio.sleep(1)

        # Mission debrief -- skip on a TPK. Dead characters can't reflect, and
        # their debriefs were rendering as an incoherent epilogue (killed party
        # members still speaking after the scene that killed them).
        if self._end_reason != 'tpk':
            await self._run_mission_debrief()

        await self._end_session()

    async def _run_dm_assessment_phase(self, mechanics) -> None:
        """DM rules on all declared player actions in one batch call.

        Merges the DM's difficulty (and any attribute/skill reframe) into
        the buffered action dicts consumed by the resolution phase, and
        logs a difficulty_assessment event pairing each ruling with the
        player's counterfactual estimate. No-op on any failure.
        """
        from .round_assessment import apply_assessments

        dm_agent = getattr(self, 'dm_agent', None)
        if dm_agent is None or not self._declared_actions:
            return

        declarations = []
        for buffered_list in self._declared_actions.values():
            for buffered in buffered_list:
                action = buffered.get('action')
                if isinstance(action, dict):
                    declarations.append(action)
        if not declarations:
            return

        # Light scene context: void level + active clocks
        context_bits = []
        if mechanics:
            context_bits.append(f"Scene void level: {getattr(mechanics, 'scene_void_level', 0)}")
            clocks = getattr(mechanics, 'scene_clocks', None) or {}
            for name, clock in list(clocks.items())[:6]:
                current = getattr(clock, 'current_ticks', getattr(clock, 'current', '?'))
                maximum = getattr(clock, 'max_ticks', getattr(clock, 'max', '?'))
                context_bits.append(f"Clock '{name}': {current}/{maximum}")
        scene_context = "\n".join(context_bits)

        round_num = mechanics.current_round if mechanics else 0
        assessment = await dm_agent.assess_round_actions(
            declarations, scene_context, round_num)
        if assessment is None:
            return

        # Character sheets for reframe value lookups
        character_sheets = {}
        for agent in self.agents:
            state = getattr(agent, 'character_state', None)
            if state is not None:
                character_sheets[state.name] = (
                    getattr(state, 'attributes', {}) or {},
                    getattr(state, 'skills', {}) or {},
                )

        changes = apply_assessments(self._declared_actions, assessment,
                                    character_sheets)
        for line in changes:
            print(f"⚖️  DM assessment: {line}")

        if mechanics and mechanics.jsonl_logger:
            estimates = {a.get('character_name'): a.get('difficulty_estimate')
                         for a in declarations}
            mechanics.jsonl_logger.log_difficulty_assessment(
                round_num=round_num,
                assessments=[
                    {**ruling.model_dump(),
                     "player_estimate": estimates.get(ruling.character_name)}
                    for ruling in assessment.assessments
                ],
                changes=changes,
            )

    def _apply_resume_state(self):
        """Apply a resume_state config block (resume-from-divergence, replay
        rung 3): exact vitals for party + spawned enemies, matched by NAME
        (the resumed session mints fresh agent_ids). Runs after scenario setup
        so initial_enemies have spawned. Roster/clocks/scenario ride existing
        config surfaces (initial_enemies / starting_clocks / force_scenario);
        this hook is the one new seam. Unmatched entries warn, never raise.

        Returns {"party": n, "enemies": n, "unmatched": [names]} or None when
        no resume_state is configured.
        """
        rs = (self.config or {}).get("resume_state")
        if not rs:
            return None
        applied = {"party": 0, "enemies": 0, "unmatched": []}

        party_by_name = {p.get("name"): p for p in rs.get("party", []) if p.get("name")}
        for agent in self.agents:
            cs = getattr(agent, "character_state", None)
            name = getattr(cs, "name", None)
            if not name or name not in party_by_name:
                continue
            o = party_by_name.pop(name)
            for attr in ("health", "max_health", "wounds", "stuns"):
                if o.get(attr) is not None:
                    setattr(agent, attr, o[attr])
            if o.get("position") is not None:
                agent.position = _resume_position(o["position"])
            for attr in ("void_score", "soulcredit"):
                if o.get(attr) is not None and cs is not None:
                    setattr(cs, attr, o[attr])
            purse = getattr(cs, "energy_purse", None)
            if purse is not None:
                for currency, amount in (o.get("energy") or {}).items():
                    if hasattr(purse, currency):
                        setattr(purse, currency, amount)
            applied["party"] += 1
            logger.info(f"Resume: applied party state to {name} "
                        f"(hp={o.get('health')} w={o.get('wounds')} s={o.get('stuns')})")
        applied["unmatched"].extend(party_by_name)

        enemies_by_name = {e.get("name"): e for e in rs.get("enemies", []) if e.get("name")}
        roster = getattr(self.enemy_combat, "enemy_agents", None) or []
        for enemy in roster:
            o = enemies_by_name.pop(getattr(enemy, "name", None), None)
            if not o:
                continue
            for attr in ("health", "max_health", "wounds", "stuns"):
                if o.get(attr) is not None:
                    setattr(enemy, attr, o[attr])
            if o.get("position") is not None:
                enemy.position = _resume_position(o["position"])
            applied["enemies"] += 1
            logger.info(f"Resume: applied enemy state to {enemy.name} "
                        f"(hp={o.get('health')} w={o.get('wounds')} s={o.get('stuns')})")
        applied["unmatched"].extend(enemies_by_name)

        for name in applied["unmatched"]:
            logger.warning(f"Resume: no live entity matched resume_state entry '{name}'")
        print(f"✓ Resume state applied: {applied['party']} party, "
              f"{applied['enemies']} enemies"
              + (f", {len(applied['unmatched'])} unmatched" if applied["unmatched"] else ""))
        return applied

    def _get_enemy_llm_client(self, llm_config, agent_id, mechanics, provider=None):
        """Return the cached fallback LLM client for this enemy, creating it once.

        Caching by agent_id keeps the client's call_sequence counter monotonic
        across rounds — otherwise a fresh client per round reset it to 0, so an
        enemy declaring in multiple rounds logged colliding [0, 0, ...] sequences
        (the replay-cache key). `provider` is injectable for tests.
        """
        client = self._enemy_llm_clients.get(agent_id)
        if client is None:
            client = EnemyFallbackLLMClient(
                llm_config,
                jsonl_logger=mechanics.jsonl_logger if mechanics else None,
                agent_id=agent_id,
                session_id=self.session_id,
                agent_prompt_logger=self.agent_prompt_logger,
                provider=provider,
                replay_client=self._get_replay_client(agent_id) if self.replay_mode else None,
            )
            self._enemy_llm_clients[agent_id] = client
        return client

    def _get_replay_client(self, agent_id):
        """Create one cached or hybrid client per replayed agent."""
        from .llm_logger import MockLLMClient, HybridLLMClient

        cache_agent_id = agent_id
        if agent_id not in self.llm_cache and agent_id.startswith('enemy_'):
            cached_enemy_ids = sorted({
                cached_id for cached_id, _sequence in self.llm_cache
                if cached_id.startswith('enemy_')
            })
            used_ids = set(self._replay_agent_aliases.values())
            available = [item for item in cached_enemy_ids if item not in used_ids]
            if available:
                cache_agent_id = available[0]
                self._replay_agent_aliases[agent_id] = cache_agent_id

        if self.continue_from_round is not None:
            client = HybridLLMClient(
                self.llm_cache,
                agent_id=cache_agent_id,
                continue_from_round=self.continue_from_round,
            )
            self.hybrid_clients.append(client)
            return client
        return MockLLMClient(self.llm_cache, agent_id=cache_agent_id)

    async def _run_initiative_round(self) -> bool:
        """
        Run a round with proper tactical flow:
        1. Declaration phase (slowest → fastest)
        2. Resolution phase (fastest → slowest)
        3. DM describes overall outcome

        Returns:
            bool: True if combat should continue, False if all players defeated
        """
        # Filter to alive players only (YAGS defeat mechanics)
        player_agents = [agent for agent in self.agents
                        if isinstance(agent, AIPlayerAgent) and agent.is_alive]

        if not player_agents:
            logger.warning("All players defeated - combat should end")
            print("\n💀 All players defeated - TPK (Total Party Kill)!")
            return False  # Signal that combat cannot continue

        # Calculate initiative for each player (Agility × 4 + d20)
        initiative_order = []
        mechanics = self.shared_state.get_mechanics_engine()

        # Capture clock state at round start for delta tracking
        clock_state_start = {}
        if mechanics and mechanics.scene_clocks:
            for clock_name, clock in mechanics.scene_clocks.items():
                clock_state_start[clock_name] = {
                    'current': clock.current,
                    'filled': clock.filled
                }

        # Clear previous round's initiative
        self._current_initiative.clear()

        for player_agent in player_agents:
            # Get player's Agility attribute
            agility = player_agent.character_state.attributes.get('Agility', 3)
            initiative = mechanics.calculate_initiative(agility)
            initiative_order.append((initiative, 'player', player_agent))

            # Store initiative for logging
            self._current_initiative[player_agent.agent_id] = initiative

            # Display with position if available
            position_str = f" ({player_agent.position})" if hasattr(player_agent, 'position') else ""
            print(f"[{player_agent.character_state.name}] Initiative: {initiative}{position_str}")

        # Add enemy initiative entries
        if self.enemy_combat.enabled:
            enemy_entries = self.enemy_combat.get_initiative_entries()
            for init, enemy in enemy_entries:
                initiative_order.append((init, 'enemy', enemy))
                # Store enemy initiative for logging
                self._current_initiative[enemy.agent_id] = init
                print(f"[{enemy.name}] (ENEMY) Initiative: {init} ({enemy.position})")

        # Add NPC initiative entries
        if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
            for npc in self.shared_state.npc_agents:
                if npc.is_active and npc.can_act:
                    # NPCs get moderate initiative (15 + random variance)
                    npc_init = 15 + random.randint(1, 20)
                    initiative_order.append((npc_init, 'npc', npc))
                    self._current_initiative[npc.agent_id] = npc_init

                    # Format disposition for display (use module-level constant)
                    disp_emoji = NPC_DISPOSITION_EMOJI.get(npc.disposition, NPC_DISPOSITION_DEFAULT_EMOJI)
                    print(f"[{npc.name}] (NPC {disp_emoji}) Initiative: {npc_init}")

        # Sort by initiative (highest first)
        initiative_order.sort(key=lambda x: x[0], reverse=True)

        # Display comprehensive round status
        self._display_round_status(initiative_order, mechanics, player_agents)

        # PHASE 1: DECLARATIONS (slowest → fastest, so faster players can react)
        print("\n=== Declaration Phase ===")
        self._in_declaration_phase = True
        self._declared_actions.clear()

        # Assign combat IDs for free targeting mode (enabled by default)
        enemy_config = self.config.get('enemy_agent_config', {})
        if enemy_config.get('free_targeting_mode', True):
            logger.info("Free targeting mode enabled - assigning target IDs")
            target_id_mapper = self.shared_state.get_target_id_mapper()
            target_id_mapper.enable()

            # Get all active enemies (empty list if enemy combat disabled)
            active_enemies = []
            if self.enemy_combat and self.enemy_combat.enabled:
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(self.enemy_combat.enemy_agents)

            # Get all active NPCs (empty list if none)
            active_npcs = []
            if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                active_npcs = [npc for npc in self.shared_state.npc_agents if npc.is_active]

            # Get all legacy vendors (for transfer targeting)
            current_vendors = []
            if self.shared_state and hasattr(self.shared_state, 'current_vendors'):
                current_vendors = self.shared_state.current_vendors or []

            # Filter out dead PCs before assigning target IDs
            active_players = [
                p for p in self.shared_state.player_agents
                if p.is_alive and not getattr(p, '_permanently_dead', False)
            ]

            # Get current destructible environmental objects (not yet destroyed)
            current_env_objects = []
            if self.shared_state and self.shared_state.current_env_objects:
                current_env_objects = [
                    obj for obj in self.shared_state.current_env_objects
                    if obj.is_destructible and not obj.is_destroyed
                ]

            # Assign IDs to all combatants, vendors, AND env objects
            target_id_mapper.assign_ids(
                player_agents=active_players,
                enemy_agents=active_enemies,
                npc_agents=active_npcs,
                vendors=current_vendors,
                env_objects=current_env_objects
            )
            logger.info(f"Assigned {len(target_id_mapper.get_all_target_ids())} target IDs")

        # Log declaration phase start
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_declaration_phase_start(mechanics.current_round)

        # Prepare LLM client for enemy declarations (if needed)
        enemy_fallback_available = False
        available_tokens = []
        if self.enemy_combat.enabled and len(self.enemy_combat.enemy_agents) > 0:
            # Get available tactical tokens (if mechanics tracks them)
            if mechanics and hasattr(mechanics, 'get_unclaimed_tokens'):
                available_tokens = mechanics.get_unclaimed_tokens()

            # Get enemy LLM config for legacy enemy prompt fallback.
            dm_agents = [a for a in self.agents if isinstance(a, AIDMAgent)]
            if dm_agents:
                dm_agent = dm_agents[0]
                enemy_llm_config = get_enemy_llm_config(self.config) or dm_agent.llm_config

                # Enemy fallback LLM available for this round. Per-enemy clients
                # are created lazily + cached in _get_enemy_llm_client so
                # call_sequence persists across rounds.
                self._enemy_llm_config = enemy_llm_config
                enemy_fallback_available = True

        # Declaration loop (slowest → fastest, reversed initiative order)
        for initiative_score, agent_type, agent in reversed(initiative_order):
            if agent_type == 'player':
                # Skip dead/unconscious players
                if not agent.is_alive:
                    print(f"\n[{agent.character_state.name}] is unconscious/defeated - cannot declare actions")
                    continue

                print(f"\n[{agent.character_state.name}] declaring (initiative {initiative_score})...")

                # Create event to track when this player's declaration arrives
                declaration_event = asyncio.Event()
                self._pending_declarations[agent.agent_id] = declaration_event

                # Get current round from mechanics engine
                current_round = 0
                if self.shared_state and self.shared_state.mechanics_engine:
                    current_round = getattr(self.shared_state.mechanics_engine, 'current_round', 0)

                turn_message = Message(
                    id=f"turn_{datetime.now().isoformat()}_{agent.agent_id}",
                    type=MessageType.TURN_REQUEST,
                    sender='coordinator',
                    recipient=agent.agent_id,
                    payload={'phase': 'declaration', 'initiative': initiative_score, 'round': current_round},
                    timestamp=datetime.now()
                )

                await self.coordinator.message_bus._route_message(turn_message)

                # Wait for this player's declaration to be buffered
                await declaration_event.wait()
                logger.debug(f"{agent.character_state.name} declaration received")

                # Clean up the event
                if agent.agent_id in self._pending_declarations:
                    del self._pending_declarations[agent.agent_id]

            elif agent_type == 'enemy':
                # Enemy declares inline (interleaved with PCs)
                logger.debug(f"Enemy {agent.name} entering declaration (init={initiative_score}, is_active={agent.is_active})")
                if enemy_fallback_available:
                    # Per-enemy client is cached on the session so call_sequence
                    # persists across rounds (was reset to 0 every round before).
                    enemy_llm_client = self._get_enemy_llm_client(
                        self._enemy_llm_config, agent.agent_id, mechanics
                    )

                    logger.debug(f"Calling declare_single_enemy for {agent.name}")
                    declaration = await self.enemy_combat.declare_single_enemy(
                        enemy=agent,
                        player_agents=player_agents,
                        available_tokens=available_tokens,
                        llm_client=enemy_llm_client
                    )
                    logger.debug(f"Declaration result for {agent.name}: {declaration is not None}")

                    # Print detailed declaration info
                    if declaration:
                        action = declaration.get('major_action', 'Unknown')
                        target_id = declaration.get('target', 'None')
                        weapon = declaration.get('weapon', 'N/A')
                        health_str = f"{agent.health}/{agent.max_health} HP"
                        position_str = str(agent.position)

                        # Resolve target ID to character name for readability
                        target_display = target_id
                        if target_id and target_id.startswith('tgt_') and self.shared_state.target_id_mapper:
                            # Look up character name from TargetIDMapper
                            combatant_info = self.shared_state.target_id_mapper.get_combatant_info(target_id)
                            if combatant_info:
                                target_display = f"{combatant_info['name']} ({target_id})"

                        if action == 'Dialogue' and declaration.get('dialogue_content'):
                            print(f"\n[{agent.name}] (Init {initiative_score}) DIALOGUE \u2192 {target_display} | {health_str} | {position_str}")
                            print(f'         \U0001f4ac "{declaration["dialogue_content"]}"')
                        else:
                            print(f"\n[{agent.name}] (Init {initiative_score}) {action} \u2192 {target_display} [{weapon}] | {health_str} | {position_str}")

                        # Show full reasoning and shared intel (Spec 12)
                        detail_lines = _format_enemy_declaration_details(
                            reasoning=declaration.get('reasoning', ''),
                            shared_intel=declaration.get('shared_intel')
                        )
                        if detail_lines:
                            print(detail_lines)

                    # Log enemy declaration
                    if declaration and mechanics and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_action_declaration(
                            player_id=declaration['agent_id'],
                            character_name=declaration['character_name'],
                            initiative=declaration['initiative'],
                            action={'major_action': declaration['major_action'], 'target': declaration.get('target'), 'dialogue_content': declaration.get('dialogue_content')},
                            round_num=mechanics.current_round
                        )

                    # Broadcast enemy declaration to all players (for tactical awareness)
                    # Note: sender must be agent_id for proper buffering in _handle_action_declared
                    if declaration:
                        broadcast_payload = {
                            'agent_id': declaration['agent_id'],
                            'character_name': declaration['character_name'],
                            'intent': declaration.get('major_action', 'Unknown action'),
                            'target': declaration.get('target'),  # NEW: targeting info
                            'weapon': declaration.get('weapon'),  # NEW: weapon info
                            'reasoning': declaration.get('reasoning', '')[:100],  # NEW: truncated reasoning
                            'initiative': declaration['initiative'],
                            'agent_type': 'enemy'
                        }
                        # Include dialogue_content so players/NPCs see enemy speech
                        if declaration.get('dialogue_content'):
                            broadcast_payload['dialogue_content'] = declaration['dialogue_content']
                            broadcast_payload['description'] = f'speaks: "{declaration["dialogue_content"]}"'

                        broadcast_message = Message(
                            id=f"enemy_declared_{datetime.now().isoformat()}_{agent.agent_id}",
                            type=MessageType.ACTION_DECLARED,
                            sender=declaration['agent_id'],  # Use enemy agent_id, not 'coordinator'
                            recipient=None,  # Broadcast to all
                            payload=broadcast_payload,
                            timestamp=datetime.now()
                        )
                        await self.coordinator.message_bus._route_message(broadcast_message)
                    else:
                        # Declaration failed - create fallback DEFENSIVE action
                        logger.warning(f"⚠️  {agent.name} declaration returned None - using fallback DEFENSIVE action (check game.log for LLM errors)")

                        # Import EnemyDeclaration if not already imported
                        from .enemy_combat import EnemyDeclaration

                        # Create minimal fallback declaration
                        fallback_declaration = EnemyDeclaration(
                            agent_id=agent.agent_id,
                            character_name=agent.name,
                            initiative=initiative_score,
                            defence_token=None,
                            major_action="DEFENSIVE",
                            target=None,
                            weapon=None,
                            minor_action=None,
                            token_target=None,
                            reasoning="Fallback action - original LLM declaration failed",
                            shared_intel=None
                        )

                        # Store in enemy_declarations so resolution phase can execute it
                        self.enemy_combat.enemy_declarations[agent.agent_id] = fallback_declaration

                        # Print fallback action
                        health_str = f"{agent.health}/{agent.max_health} HP"
                        position_str = str(agent.position)
                        print(f"\n[{agent.name}] (Init {initiative_score}) DEFENSIVE (fallback - check logs) | {health_str} | {position_str}")

            elif agent_type == 'npc':
                # NPC declares simple action (flee/hide/plead/dialogue/assist/pass)
                if agent.llm_client and agent.can_act:
                    try:
                        # Build context string for NPC (include player actions and recent events)
                        active_enemies = []
                        if self.enemy_combat and self.enemy_combat.enabled:
                            active_enemies = [e for e in self.enemy_combat.enemy_agents if e.is_active]

                        num_players = len(player_agents)
                        num_enemies = len(active_enemies)

                        # PHASE 3: Intelligent threat assessment (not just binary)
                        threat_indicators = []

                        # Check for captured/prisoner NPCs
                        if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                            captured_npcs = [npc for npc in self.shared_state.npc_agents
                                           if npc.is_active and npc.entity_type == "prisoner"]
                            if captured_npcs:
                                threat_indicators.append("ally captured")

                        # Check for active combat
                        if num_enemies > 0:
                            threat_indicators.append(f"combat: {num_enemies} hostiles")

                        # Build context string with intelligent assessment
                        context = f"Round {mechanics.current_round if mechanics else 0}: "
                        if threat_indicators:
                            context += f"ALERT: {', '.join(threat_indicators)}. {num_players} players present."
                        elif num_enemies > 0:
                            context += f"Combat active - {num_players} players vs {num_enemies} enemies."
                        else:
                            context += f"Calm situation. {num_players} players present."

                        if self.shared_state and hasattr(self.shared_state, 'scenario'):
                            context += f" Situation: {self.shared_state.scenario}"

                        # Start narrative context section (matches player formatting)
                        narrative_context = ""

                        # PHASE 2: Add previous round DM narration FIRST (overall story progression)
                        if hasattr(self, '_last_round_synthesis') and self._last_round_synthesis:
                            synthesis_narration = self._last_round_synthesis.get('narration', '')
                            if synthesis_narration and len(synthesis_narration) > 0:
                                narrative_context += "\n\n# 📖 Recent Story Events\n\n"
                                narrative_context += "## What Just Happened (Last Round Summary):\n"
                                narrative_context += f"{synthesis_narration}\n"

                        # PHASE 4: Add recent narrative context (filter out NPC reasoning echoes)
                        # Include ONLY NEW action resolutions (use NPC memory to deduplicate)
                        recent_narrative = []

                        # Get list of NPC names to filter out reasoning echoes
                        npc_names = []
                        if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                            npc_names = [npc.name for npc in self.shared_state.npc_agents if npc.is_active]

                        # Collect all narrations first, filtering by awareness
                        all_narrations = []
                        seen_narration_texts = set()
                        for player_agent in player_agents:
                            if hasattr(player_agent, 'recent_narrations') and player_agent.recent_narrations:
                                # Filter narrations based on what this NPC can see
                                visible_narrations = filter_narrations_for_agent(
                                    agent.agent_id,
                                    player_agent.recent_narrations
                                )
                                for narration in visible_narrations:
                                    # Get text from NarrationEntry or use string directly
                                    narration_text = narration.text if isinstance(narration, NarrationEntry) else narration
                                    # Skip if this looks like NPC reasoning echo
                                    is_npc_reasoning = any(
                                        narration_text.startswith(f"[{npc_name}] {npc_name}")
                                        for npc_name in npc_names
                                    )
                                    if not is_npc_reasoning and narration_text not in seen_narration_texts:
                                        seen_narration_texts.add(narration_text)
                                        all_narrations.append(narration_text)

                        # Use NPC's memory to filter out already-seen events
                        if hasattr(agent, 'memory') and agent.memory:
                            recent_narrative = agent.memory.filter_unseen_events(all_narrations)
                            # Mark these events as seen for next round
                            for event in recent_narrative:
                                agent.memory.mark_event_seen(event)
                        else:
                            # Fallback: show last 5 narrations if no memory
                            recent_narrative = all_narrations[-5:] if len(all_narrations) > 5 else all_narrations

                        if recent_narrative:
                            if not narrative_context:
                                narrative_context += "\n\n# 📖 Recent Story Events\n\n"
                            narrative_context += "## Recent Action Outcomes:\n"
                            # Show only NEW/unseen events
                            for i, narration in enumerate(recent_narrative, 1):
                                narrative_context += f"{i}. {narration}\n"
                            narrative_context += "\n"

                        # PHASE 1: Show what has already been declared this round
                        # NPCs need to see it before taking their turn. Declaration
                        # runs slowest-first, so the buffer holds exactly the agents
                        # that went before this one.
                        sorted_declarations = prior_declarations(self._declared_actions)

                        if sorted_declarations:
                            if not narrative_context:
                                narrative_context += "\n\n# 📖 Recent Story Events\n\n"
                            narrative_context += "## 🎯 Declared Actions This Round (Initiative Order):\n"
                            narrative_context += "*You see what slower combatants (lower initiative) declared before you. React accordingly!*\n\n"
                            for actor_name, initiative, declaration_text in sorted_declarations:
                                narrative_context += f"- **{actor_name}** [Init {initiative}]: {declaration_text}\n"
                            narrative_context += "\n"

                        # Append narrative context to main context
                        context += narrative_context

                        # Add combatant list with health and status for informed NPC decisions
                        if self.shared_state and hasattr(self.shared_state, 'target_id_mapper'):
                            mapper = self.shared_state.target_id_mapper
                            if mapper and mapper.enabled:
                                active_combatants = []
                                down_combatants = []

                                for target_id in mapper.get_all_target_ids():
                                    info = mapper.get_combatant_info(target_id)
                                    if not info:
                                        continue

                                    # Skip self
                                    if info.get('agent_id') == agent.agent_id:
                                        continue

                                    # Skip PCs hidden from this NPC (stealth filtering)
                                    if info.get('type') == 'player' and self.shared_state:
                                        if not self.shared_state.is_visible_to(info['agent_id'], agent.agent_id):
                                            continue

                                    death_state = info.get('death_state', 'alive')
                                    health = info.get('health', 0)
                                    max_health = info.get('max_health', 0)
                                    wounds = info.get('wounds', 0)

                                    # Status tag
                                    if death_state == 'dead':
                                        status = " [DEAD — cannot be saved]"
                                    elif death_state == 'unconscious':
                                        status = f" [UNCONSCIOUS — wounds: {wounds}, healable]" if wounds < 6 else " [DEAD]"
                                    elif max_health > 0 and health <= max_health * 0.25:
                                        status = " [CRITICAL]"
                                    else:
                                        status = ""

                                    faction = info.get('faction', 'Unknown')

                                    entry = f"{info['name']} ({target_id}, {faction}) — {health}/{max_health} HP, wounds: {wounds}{status}"

                                    if death_state in ('dead', 'unconscious'):
                                        down_combatants.append(entry)
                                    else:
                                        active_combatants.append(entry)

                                # Also show defeated enemies not in mapper (for awareness)
                                if self.enemy_combat and self.enemy_combat.enabled:
                                    mapper_agent_ids = set()
                                    for tid in mapper.get_all_target_ids():
                                        tid_info = mapper.get_combatant_info(tid)
                                        if tid_info:
                                            mapper_agent_ids.add(tid_info.get('agent_id'))

                                    for enemy in self.enemy_combat.enemy_agents:
                                        if not enemy.is_active and enemy.agent_id not in mapper_agent_ids:
                                            ewounds = getattr(enemy, 'wounds', 0)
                                            ehealth = getattr(enemy, 'health', 0)
                                            emax = getattr(enemy, 'max_health', 0)
                                            down_combatants.append(
                                                f"{enemy.name} — {ehealth}/{emax} HP, wounds: {ewounds} [DEFEATED]"
                                            )

                                if active_combatants or down_combatants:
                                    context += "\n\n## People in Scene:\n"
                                    context += "**Use target IDs (tgt_xxxx) when specifying targets**\n"

                                    if active_combatants:
                                        context += "\n**Active:**\n"
                                        for c in active_combatants:
                                            context += f"- {c}\n"

                                    if down_combatants:
                                        context += "\n**Down (cannot act or be targeted for dialogue):**\n"
                                        for c in down_combatants:
                                            context += f"- {c}\n"

                                    # Tactical summary
                                    n_active = len(active_combatants)
                                    n_unconscious = sum(1 for c in down_combatants if 'UNCONSCIOUS' in c)
                                    n_dead = sum(1 for c in down_combatants if 'DEAD' in c or 'DEFEATED' in c)
                                    parts = []
                                    if n_active:
                                        parts.append(f"{n_active} active")
                                    if n_unconscious:
                                        parts.append(f"{n_unconscious} unconscious (healable)")
                                    if n_dead:
                                        parts.append(f"{n_dead} dead/defeated")
                                    context += f"\n**Battlefield:** {', '.join(parts)}\n"

                        # Get NPC action via simple LLM client (correct method: declare_action)
                        npc_action = await agent.llm_client.declare_action(context)

                        if npc_action:
                            # Record action in NPC's memory (so they don't repeat themselves)
                            if hasattr(agent, 'memory') and agent.memory:
                                current_round = mechanics.current_round if mechanics else 0
                                agent.memory.record_own_action(
                                    round_num=current_round,
                                    action_type=npc_action.action_type,
                                    dialogue=npc_action.dialogue_content if npc_action.action_type in ['dialogue', 'plead'] else None,
                                    target=npc_action.target,
                                    reason=npc_action.reason
                                )

                            # Print detailed NPC declaration info
                            health_str = f"{agent.health}/{agent.max_health} HP"
                            disp_emoji = NPC_DISPOSITION_EMOJI.get(agent.disposition, NPC_DISPOSITION_DEFAULT_EMOJI)

                            # For dialogue actions, show the actual dialogue content
                            if npc_action.action_type == "dialogue" and npc_action.dialogue_content:
                                print(f"\n[{agent.name}] (Init {initiative_score}) {disp_emoji} {npc_action.action_type.upper()} | {health_str}")
                                print(f'         \U0001f4ac "{npc_action.dialogue_content}"')
                            else:
                                # Show full reason (Spec 12: no truncation)
                                print(f"\n[{agent.name}] (Init {initiative_score}) {disp_emoji} {npc_action.action_type.upper()} | {health_str}")
                                print(_format_npc_declaration_reason(npc_action.reason))

                            # Check for self-escalation (NPC declares attack)
                            if _should_escalate_npc(agent.entity_type, npc_action.action_type):
                                logger.info(f"🔥 NPC {agent.name} self-escalating via attack declaration!")
                                logger.info(f"   Reason: {npc_action.reason}")

                                # Convert NPC to enemy immediately
                                from .agent_conversion import escalate_npc_to_enemy

                                # Determine enemy template based on NPC threat level
                                template_map = {
                                    "non_combatant": "desperate_fighter",
                                    "potential_threat": "grunt",
                                    "armed_neutral": "elite"
                                }
                                template = template_map.get(agent.threat_level, "grunt")

                                # Escalate NPC to enemy
                                enemy = escalate_npc_to_enemy(
                                    npc=agent,
                                    template_override=template,
                                    current_round=mechanics.current_round if mechanics else 0
                                )

                                # Register with enemy combat system
                                if self.enemy_combat:
                                    self.enemy_combat.enemy_agents.append(enemy)
                                    logger.info(f"   ✅ Converted to enemy: {enemy.agent_id}")

                                # Log conversion to JSONL
                                if mechanics and mechanics.jsonl_logger:
                                    mechanics.jsonl_logger.log_agent_conversion(
                                        round_num=mechanics.current_round,
                                        agent_id=enemy.agent_id,
                                        agent_name=enemy.name,
                                        from_type="npc",
                                        to_type="enemy",
                                        trigger="self_escalation_attack",
                                        state_before={
                                            "health": agent.health,
                                            "max_health": agent.max_health,
                                            "wounds": agent.wounds,
                                            "stuns": agent.stuns,
                                            "disposition": agent.disposition,
                                            "entity_type": agent.entity_type
                                        },
                                        state_after={
                                            "health": enemy.health,
                                            "max_health": enemy.max_health,
                                            "wounds": enemy.wounds,
                                            "stuns": enemy.stuns,
                                            "template": enemy.template,
                                            "position": str(enemy.position)
                                        }
                                    )

                                # Remove from NPC list
                                if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                                    self.shared_state.npc_agents = [n for n in self.shared_state.npc_agents if n.agent_id != agent.agent_id]

                                # Enemy will join combat NEXT round (escalation consumed this turn's action)
                                logger.info(f"   Enemy will join combat next round (escalation consumed this turn)")
                                continue

                            # Normal NPC action processing
                            # Store defence_token on NPC agent (Spec 04)
                            if hasattr(npc_action, 'defence_token') and hasattr(agent, 'defence_token'):
                                agent.defence_token = npc_action.defence_token
                                if npc_action.defence_token:
                                    logger.info(f"NPC {agent.name} watching {npc_action.defence_token}")

                            # Log NPC declaration
                            if mechanics and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_action_declaration(
                                    player_id=agent.agent_id,
                                    character_name=agent.name,
                                    initiative=initiative_score,
                                    action={'major_action': npc_action.action_type, 'description': npc_action.reason},
                                    round_num=mechanics.current_round
                                )

                            # Store for resolution (as list to match player/enemy format)
                            if agent.agent_id not in self._declared_actions:
                                self._declared_actions[agent.agent_id] = []

                            self._declared_actions[agent.agent_id].append({
                                'agent_id': agent.agent_id,
                                'character_name': agent.name,
                                'intent': npc_action.action_type,
                                'description': npc_action.reason,
                                'action_type': npc_action.action_type,
                                'initiative': initiative_score,
                                'target': npc_action.target,  # Target for assist/heal/dialogue/attack actions
                                'dialogue_content': npc_action.dialogue_content,  # Include actual dialogue for dialogue actions
                                # Transfer-specific fields (if transfer action)
                                'transfer_target': getattr(npc_action, 'transfer_target', None),
                                'transfer_currency': getattr(npc_action, 'transfer_currency', None),
                                'transfer_items': getattr(npc_action, 'transfer_items', None)
                            })

                            # Broadcast NPC action to players
                            broadcast_message = Message(
                                id=f"npc_declared_{datetime.now().isoformat()}_{agent.agent_id}",
                                type=MessageType.ACTION_DECLARED,
                                sender=agent.agent_id,
                                recipient=None,  # Broadcast to all
                                payload={
                                    'agent_id': agent.agent_id,
                                    'character_name': agent.name,
                                    'description': npc_action.reason,  # NPC's reasoning for action (10-500 chars)
                                    'intent': npc_action.action_type,
                                    'initiative': initiative_score,
                                    'agent_type': 'npc',
                                    'dialogue_content': npc_action.dialogue_content  # Include actual dialogue for dialogue actions
                                },
                                timestamp=datetime.now()
                            )
                            await self.coordinator.message_bus._route_message(broadcast_message)

                    except (TypeError, AttributeError, KeyError, IndexError) as e:
                        # Programming errors, not LLM/transport failures. Forfeiting a
                        # turn here manufactures "ghost agents" that the round-end
                        # check then reports with no cause — log the traceback loudly
                        # so the defect is visible instead of looking like an NPC
                        # that simply chose not to act.
                        logger.error(
                            f"NPC {agent.name} declaration hit an internal error "
                            f"({type(e).__name__}: {e}) — this is a bug, not a "
                            f"failed LLM call",
                            exc_info=True,
                        )
                        print(f"[{agent.name}] unable to act this round (internal error)")
                    except Exception as e:
                        logger.warning(f"NPC {agent.name} failed to declare action: {e}")
                        # NPCs can skip their turn if declaration fails
                        print(f"[{agent.name}] unable to act this round")

        self._in_declaration_phase = False

        # DM ASSESSMENT PHASE: one batch call per round rules the
        # authoritative difficulty (and ratifies attribute/skill framing)
        # for every declared player action, before any dice roll. Player
        # estimates stay in declaration events as counterfactuals. Any
        # failure falls back to calculate_dc's category table.
        if self.config.get('dm_assessment_enabled', True):
            await self._run_dm_assessment_phase(mechanics)

        # PHASE 2: RESOLUTION (execute in descending initiative order)
        print("\n=== Resolution Phase ===")
        logger.debug(f"Declared actions at resolution start: {list(self._declared_actions.keys())}")

        # Create resolution state tracker for declare/resolve cycle
        resolution_state = ResolutionState()

        # Collect all resolutions for synthesis at the end
        all_resolutions = []
        outcome_first = bool(self.config.get('outcome_first_narration', False))
        outcome_sequence = 0

        # Execute actions in initiative order (highest first)
        for initiative_score, agent_type, agent in initiative_order:
            logger.debug(f"Processing {agent_type} with initiative {initiative_score}")
            if agent_type == 'player':
                # Skip dead/unconscious/extracted players
                if not agent.is_in_combat:
                    skip_reason = "extracted by medevac" if agent.is_extracted else "dead/unconscious"
                    logger.debug(f"{agent.character_state.name} is {skip_reason} - skipping execution")

                    # Log skipped action to JSONL for completeness (declaration exists, resolution should too)
                    if agent.agent_id in self._declared_actions and mechanics and mechanics.jsonl_logger:
                        for idx, buffered_action in enumerate(self._declared_actions[agent.agent_id]):
                            action_intent = buffered_action.get('action', {}).get('intent', 'unknown')
                            mechanics.jsonl_logger.log_enemy_action(
                                round_num=mechanics.current_round,
                                enemy_id=agent.agent_id,  # Using enemy method for simplicity
                                enemy_name=agent.character_state.name,
                                action_type='skipped',
                                result=skip_reason,
                                narration=f"{agent.character_state.name}'s action ({action_intent}) skipped: {skip_reason}",
                                target_id=None,
                                target_name=None,
                                damage_dealt=None,
                                roll_data=None,
                                effects={'skip_reason': skip_reason}
                            )
                    continue

                # Check conditions for incapacitation (Spec 15 extension)
                # If any condition has abs(penalty) >= 6, mark as incapacitated
                # This feeds into the existing is_incapacitated() check below
                _check_condition_incapacitation(agent.agent_id, mechanics, resolution_state)

                # YAGS Beaten/Fatal consciousness gate: a stun-KO'd or fatally
                # wounded player must pass a health check to act this round (else
                # skipped as incapacitated). Fixes the "zombie" — Hard Vane acting
                # while flagged unconscious. Enemies are gated separately (TODO).
                _check_beaten_ko(agent, resolution_state,
                                 jsonl_logger=mechanics.jsonl_logger if mechanics else None,
                                 round_num=getattr(mechanics, 'current_round', None))

                # Skip defeated/incapacitated players (same checks as enemy invalidation)
                # This prevents wasted LLM calls for mechanically impossible actions
                player_skip_reason = None
                if resolution_state.is_defeated(agent.agent_id):
                    player_skip_reason = "attacker_defeated"
                elif resolution_state.is_incapacitated(agent.agent_id):
                    player_skip_reason = "attacker_incapacitated"

                if player_skip_reason:
                    from .tactical_resolution import generate_invalidation_message
                    skip_narration = generate_invalidation_message(
                        agent.character_state.name,
                        "action",
                        player_skip_reason
                    )
                    print(f"\n⚠️  {skip_narration}")
                    logger.info(f"Player auto-skip: {agent.character_state.name} ({player_skip_reason})")

                    # Build skip resolution for previous_context visibility
                    skip_resolution = {
                        'character_name': agent.character_state.name,
                        'player_id': agent.agent_id,
                        'action': {'action_type': 'skipped', 'intent': 'auto-skipped'},
                        'narration': skip_narration,
                        'action_skipped': True,
                        'skip_reason': player_skip_reason,
                        'effects': {},
                        'resolution': {'margin': 0},
                    }
                    if outcome_first:
                        from .outcome_pipeline import build_applied_outcome, snapshot_shared_state

                        declared = self._declared_actions.get(agent.agent_id, [])
                        declared_action = dict(declared[0].get('action', {})) if declared else {}
                        skip_resolution['action'] = declared_action or skip_resolution['action']
                        outcome_sequence += 1
                        applied_outcome = build_applied_outcome(
                            round_num=mechanics.current_round if mechanics else 0,
                            sequence=outcome_sequence,
                            actor_id=agent.agent_id,
                            actor_name=agent.character_state.name,
                            action=skip_resolution['action'],
                            resolution_data=skip_resolution,
                            before=snapshot_shared_state(self.shared_state),
                            after=snapshot_shared_state(self.shared_state),
                        )
                        skip_resolution['applied_outcome'] = applied_outcome.model_dump(mode='json')
                        if mechanics and mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_applied_outcome(
                                mechanics.current_round,
                                applied_outcome.model_dump(mode='json'),
                            )
                    all_resolutions.append(skip_resolution)

                    # Log to JSONL
                    if mechanics and mechanics.jsonl_logger:
                        declared = self._declared_actions.get(agent.agent_id, [])
                        for idx, buffered_action in enumerate(declared):
                            action_intent = buffered_action.get('action', {}).get('intent', 'unknown')
                            mechanics.jsonl_logger.log_enemy_action(
                                round_num=mechanics.current_round,
                                enemy_id=agent.agent_id,
                                enemy_name=agent.character_state.name,
                                action_type='skipped',
                                result=player_skip_reason,
                                narration=f"{agent.character_state.name}'s action ({action_intent}) auto-skipped: {player_skip_reason}",
                                target_id=None,
                                target_name=None,
                                damage_dealt=None,
                                roll_data=None,
                                effects={'skip_reason': player_skip_reason, 'action_skipped': True}
                            )
                    continue

                # PC action execution via DM adjudication
                # Process ALL buffered actions for this agent (supports free action system)
                if agent.agent_id in self._declared_actions:
                    buffered_actions = self._declared_actions[agent.agent_id]

                    print(f"\n[{agent.character_state.name}] executing action...")

                    # Process each action in order (free action first, then main action)
                    for idx, buffered_action in enumerate(buffered_actions):
                        state_before = None
                        if outcome_first:
                            from .outcome_pipeline import snapshot_shared_state
                            state_before = snapshot_shared_state(self.shared_state)
                        action_label = "FREE ACTION" if buffered_action['action'].get('is_free_action') else f"ACTION {idx+1}"
                        logger.debug(f"Processing {action_label} for {agent.character_state.name}")

                        # Apply position change NOW (execution phase) if declared
                        target_position = buffered_action['action'].get('target_position')
                        if target_position:
                            old_position = agent.position
                            # Validate: don't move to same position (bug fix)
                            if old_position == target_position:
                                logger.info(f"{agent.character_state.name} already at {old_position}, skipping redundant movement.")
                                print(f"[{agent.character_state.name}] Position unchanged: {old_position} (already there)")
                            else:
                                agent.position = target_position
                                print(f"[{agent.character_state.name}] Position: {old_position} → {agent.position}")
                                logger.info(f"{agent.character_state.name} moved from {old_position} to {agent.position}")

                        # Build single action for DM adjudication
                        action_for_adjudication = {
                            'player_id': agent.agent_id,
                            'character_name': agent.character_state.name,
                            'initiative': initiative_score,
                            'action': buffered_action['action']
                        }

                        # Create event to track when this adjudication completes
                        adjudication_event = asyncio.Event()
                        self._pending_resolutions[f"{agent.agent_id}_{idx}"] = adjudication_event

                        # Send action to DM for mechanical resolution (no synthesis yet)
                        adjudication_message = Message(
                            id=f"adjudicate_{datetime.now().isoformat()}_{agent.agent_id}_{idx}",
                            type=MessageType.ACTION_DECLARED,
                            sender='coordinator',
                            recipient='dm_01',
                            payload={
                                'phase': 'resolution_only',  # Resolve mechanically but don't synthesize yet
                                'actions': [action_for_adjudication],
                                'round': mechanics.current_round if mechanics else 0,
                                'action_index': idx,  # Track which action this is for multi-action turns
                                'previous_resolutions': all_resolutions  # Context from earlier actions this round
                            },
                            timestamp=datetime.now()
                        )

                        await self.coordinator.message_bus._route_message(adjudication_message)

                        # Wait for DM to complete adjudication (with timeout)
                        # Timeout = 24 hours (Batch API can queue requests for hours)
                        ADJUDICATION_TIMEOUT = 86400  # seconds (24h for batch API)
                        try:
                            await asyncio.wait_for(adjudication_event.wait(), timeout=ADJUDICATION_TIMEOUT)
                        except asyncio.TimeoutError:
                            error_msg = f"Adjudication timeout after {ADJUDICATION_TIMEOUT}s for {agent.character_state.name}"
                            logger.error(f"❌ {error_msg}")
                            # Log to JSONL
                            if mechanics and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_session_error(
                                    error_type="adjudication_timeout",
                                    error_message=error_msg,
                                    exception_type="TimeoutError",
                                    context={
                                        'round': mechanics.current_round,
                                        'agent_id': agent.agent_id,
                                        'character_name': agent.character_state.name,
                                        'action_index': idx
                                    }
                                )
                            # Continue to avoid infinite hang, but mark as failed
                            raise RuntimeError(error_msg)

                        # Check if adjudication returned an error
                        if getattr(adjudication_event, 'error', False):
                            error_msg = getattr(adjudication_event, 'error_message', 'Unknown adjudication error')
                            logger.error(f"❌ Adjudication failed: {error_msg}")
                            raise RuntimeError(error_msg)

                        logger.debug(f"{agent.character_state.name} {action_label} adjudicated")

                        # Clean up and collect resolution for synthesis
                        # Get the resolution data that was stored when ACTION_RESOLVED was received
                        resolution_data = getattr(adjudication_event, 'resolution_data', None)
                        if resolution_data:
                            all_resolutions.append(resolution_data)

                            # Parse surrender from PC action resolution
                            # This marks enemies as surrendered in resolution_state BEFORE their turn
                            # so their actions get invalidated (like defeated enemies)
                            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                            _parse_surrender_from_resolution(resolution_data, resolution_state, target_id_mapper)
                            _mark_defeated_from_resolution(
                                self.enemy_combat, resolution_state,
                                jsonl_logger=mechanics.jsonl_logger if mechanics else None,
                                round_num=getattr(mechanics, 'current_round', None))

                            # Process purchase/crafting effects from structured output
                            # Guard: skip all effect processing if action was preempted
                            action_was_skipped = resolution_data.get('action_skipped', False)
                            if action_was_skipped:
                                skip_reason = resolution_data.get('skip_reason', 'preempted')
                                logger.info(f"Skipping effect processing for {agent.character_state.name}: action_skipped=True (reason: {skip_reason})")
                                effects = {}
                            else:
                                effects = resolution_data.get('effects') or {}

                            # Handle purchases
                            purchase_effect = effects.get('purchase') if effects else None
                            if purchase_effect:
                                try:
                                    success = mechanics.process_purchase_effect(purchase_effect, agent.character_state)
                                    if success:
                                        logger.info(f"Processed purchase for {agent.character_state.name}")
                                    else:
                                        logger.warning(f"Purchase processing failed for {agent.character_state.name}")
                                except Exception as e:
                                    logger.error(f"Error processing purchase for {agent.character_state.name}: {e}")

                            # Handle crafting
                            crafting_effect = effects.get('crafting') if effects else None
                            if crafting_effect:
                                try:
                                    success = mechanics.process_crafting_effect(crafting_effect, agent.character_state)
                                    if success:
                                        logger.info(f"Processed crafting for {agent.character_state.name}")
                                    else:
                                        logger.warning(f"Crafting processing failed for {agent.character_state.name}")
                                except Exception as e:
                                    logger.error(f"Error processing crafting for {agent.character_state.name}: {e}")

                            # Handle attunement
                            attunement_effect = effects.get('attunement') if effects else None
                            if attunement_effect:
                                try:
                                    success = mechanics.process_attunement_effect(attunement_effect, agent.character_state)
                                    if success:
                                        logger.info(f"Processed attunement for {agent.character_state.name}")
                                    else:
                                        logger.warning(f"Attunement processing failed for {agent.character_state.name}")
                                except Exception as e:
                                    logger.error(f"Error processing attunement for {agent.character_state.name}: {e}")

                            # Handle item discovery (seeds, currency, items from environment/NPCs)
                            item_discovery = effects.get('item_discovery') if effects else None
                            if item_discovery:
                                try:
                                    success = mechanics.process_item_effect(
                                        item_effect=item_discovery,
                                        character_state=agent.character_state,
                                        player_id=agent.agent_id
                                    )
                                    if success:
                                        logger.info(f"Processed item discovery for {agent.character_state.name}")
                                    else:
                                        logger.warning(f"Item discovery processing failed for {agent.character_state.name}")
                                except Exception as e:
                                    logger.error(f"Error processing item discovery for {agent.character_state.name}: {e}")

                            # Handle stabilization (YAGS First Aid - ally extraction)
                            stabilization = effects.get('stabilization') if effects else None
                            if stabilization:
                                try:
                                    target_id = stabilization.get('target') if isinstance(stabilization, dict) else getattr(stabilization, 'target', None)
                                    success = stabilization.get('success') if isinstance(stabilization, dict) else getattr(stabilization, 'success', False)

                                    if success and target_id:
                                        # Find target player agent
                                        target_agent = next((p for p in player_agents if p.agent_id == target_id), None)
                                        if target_agent:
                                            # Mark as stabilized and extracted
                                            target_agent.is_stabilized = True
                                            target_agent.is_extracted = True
                                            faction = target_agent.character_state.faction
                                            target_name = target_agent.character_state.name

                                            print(f"\n🚑 MEDEVAC: {target_name} has been stabilized and extracted by {faction} medical team!")
                                            print(f"   {target_name} is safe but will not rejoin this encounter.")
                                            logger.info(f"Stabilization success: {target_name} extracted by {faction} medevac")
                                        else:
                                            logger.warning(f"Stabilization target {target_id} not found in player agents")
                                except Exception as e:
                                    logger.error(f"Error processing stabilization: {e}")

                            if outcome_first:
                                from .outcome_pipeline import build_applied_outcome, snapshot_shared_state
                                outcome_action = dict(buffered_action['action'])
                                target_id = outcome_action.get('target')
                                if target_id and self.shared_state:
                                    mapper = self.shared_state.get_target_id_mapper()
                                    target_entity = mapper.resolve_target(target_id) if mapper else None
                                    if target_entity is not None:
                                        outcome_action['target_entity_id'] = getattr(
                                            target_entity, 'agent_id', getattr(target_entity, 'object_id', target_id)
                                        )
                                outcome_sequence += 1
                                applied_outcome = build_applied_outcome(
                                    round_num=mechanics.current_round if mechanics else 0,
                                    sequence=outcome_sequence,
                                    actor_id=agent.agent_id,
                                    actor_name=agent.character_state.name,
                                    action=outcome_action,
                                    resolution_data=resolution_data,
                                    before=state_before or {},
                                    after=snapshot_shared_state(self.shared_state),
                                )
                                resolution_data['applied_outcome'] = applied_outcome.model_dump(mode='json')
                                # Round-summary counters: the legacy dm.py path
                                # tracks player action resolutions, but the
                                # outcome-first pipeline bypasses it, so every
                                # round_summary reported 0 actions and +0.0 margin.
                                self.track_outcome_statistics(applied_outcome)
                                if mechanics and mechanics.jsonl_logger:
                                    adjudication = resolution_data.get('adjudication') or {}
                                    mechanics.jsonl_logger.log_action_adjudication(
                                        mechanics.current_round,
                                        {
                                            'schema_version': applied_outcome.schema_version,
                                            'adjudication_id': applied_outcome.adjudication_id,
                                            'outcome_id': applied_outcome.outcome_id,
                                            'sequence': applied_outcome.sequence,
                                            'actor_id': applied_outcome.actor_id,
                                            'actor_name': applied_outcome.actor_name,
                                            'adjudication': adjudication,
                                        },
                                    )
                                    mechanics.jsonl_logger.log_applied_outcome(
                                        mechanics.current_round,
                                        applied_outcome.model_dump(mode='json'),
                                    )

                        if f"{agent.agent_id}_{idx}" in self._pending_resolutions:
                            del self._pending_resolutions[f"{agent.agent_id}_{idx}"]

                        # resolution_state updated after each PC action:
                        # - Surrendered enemies: _parse_surrender_from_resolution
                        # - Defeated enemies: _mark_defeated_from_resolution

            elif agent_type == 'enemy':
                # Enemy action execution with resolution state tracking
                if self.enemy_combat.enabled:
                    state_before = None
                    if outcome_first:
                        from .outcome_pipeline import snapshot_shared_state
                        state_before = snapshot_shared_state(self.shared_state)
                    result = self.enemy_combat.execute_enemy_action(
                        enemy_id=agent.agent_id,
                        player_agents=player_agents,
                        mechanics_engine=mechanics,
                        resolution_state=resolution_state
                    )

                    if result:
                        # Check if action was invalidated
                        if result.get('result') == 'invalidated':
                            narration = self._resolve_target_ids_in_text(result['narration'])
                            print(f"\n⚠️  {narration}")
                        else:
                            # Enhanced enemy execution output
                            enemy = next((e for e in self.enemy_combat.enemy_agents if e.agent_id == result.get('enemy_id')), None)
                            if enemy:
                                health_str = f"{enemy.health}/{enemy.max_health} HP"
                                position_str = str(enemy.position)
                                # Resolve target IDs in narration for readability
                                narration = self._resolve_target_ids_in_text(result['narration'])
                                print(f"\n[{result['character_name']}] {narration}")
                                # Show dialogue content prominently (like NPC dialogue)
                                if result.get('dialogue_content'):
                                    print(f'         💬 "{result["dialogue_content"]}"')
                                # Show additional details on second line if combat action with damage
                                elif result.get('damage_dealt') is not None:
                                    damage_str = f"Damage: {result.get('damage_dealt')}"
                                    range_str = f"Range: {result.get('range', 'N/A')}"
                                    print(f"         └─ {damage_str} | {range_str} | {health_str} | {position_str}")
                                else:
                                    # Non-damage actions (movement, claim token, etc.)
                                    print(f"         └─ {health_str} | {position_str}")
                            else:
                                # Fallback if enemy not found
                                narration = self._resolve_target_ids_in_text(result['narration'])
                                print(f"\n[{result['character_name']}] {narration}")

                            # Broadcast enemy dialogue/wait results as ACTION_RESOLVED
                            # so they appear in players' recent_narrations (like NPC/PC actions)
                            if result.get('action') in ('dialogue', 'wait'):
                                resolved_narration = self._resolve_target_ids_in_text(result.get('narration', ''))
                                broadcast_message = Message(
                                    id=f"enemy_resolved_{datetime.now().isoformat()}_{agent.agent_id}",
                                    type=MessageType.ACTION_RESOLVED,
                                    sender=agent.agent_id,
                                    recipient=None,  # Broadcast to all
                                    payload={
                                        'agent_id': agent.agent_id,
                                        'original_action': {
                                            'character_name': result.get('character_name', agent.name),
                                            'intent': result.get('action', 'dialogue'),
                                        },
                                        'narration': resolved_narration,
                                        'aware_agents': [],  # Public — everyone hears it
                                        'resolution_data': result
                                    },
                                    timestamp=datetime.now()
                                )
                                await self.coordinator.message_bus._route_message(broadcast_message)

                        # Add enemy result to synthesis input (normalized for schema consistency)
                        normalized_enemy = _normalize_enemy_result(result)
                        if outcome_first:
                            from .outcome_pipeline import build_applied_outcome, snapshot_shared_state
                            outcome_sequence += 1
                            enemy_action = {
                                'intent': result.get('action', 'acts'),
                                'description': result.get('action', 'acts'),
                                'target': result.get('target'),
                                'dialogue_content': result.get('dialogue_content'),
                            }
                            applied_outcome = build_applied_outcome(
                                round_num=mechanics.current_round if mechanics else 0,
                                sequence=outcome_sequence,
                                actor_id=agent.agent_id,
                                actor_name=agent.name,
                                action=enemy_action,
                                resolution_data=normalized_enemy,
                                before=state_before or {},
                                after=snapshot_shared_state(self.shared_state),
                            )
                            normalized_enemy['applied_outcome'] = applied_outcome.model_dump(mode='json')
                            if mechanics and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_applied_outcome(
                                    mechanics.current_round,
                                    applied_outcome.model_dump(mode='json'),
                                )
                        all_resolutions.append(normalized_enemy)

                        # Combat logging handled in enemy_combat.py via log_combat_action()

            elif agent_type == 'npc':
                # NPC action execution - route through DM adjudication like players
                if agent.agent_id in self._declared_actions:
                    # Get first action from list (NPCs only declare one action, but stored as list for consistency)
                    npc_actions = self._declared_actions[agent.agent_id]
                    if not npc_actions:
                        continue

                    npc_action = npc_actions[0]  # NPCs only have one action

                    # NPCAction schema uses 'reason' and 'action_type', not 'intent' and 'description'
                    # Map to player-style fields for consistency with DM adjudication
                    npc_intent = npc_action.get('intent') or npc_action.get('reason', 'NPC action')
                    npc_description = npc_action.get('description') or npc_action.get('dialogue_content') or npc_action.get('reason', '')
                    npc_action_type = npc_action.get('action_type', 'dialogue')

                    print(f"\n[{agent.name}] (NPC) executing: {npc_action_type} - {npc_intent[:50]}...")
                    state_before = None
                    if outcome_first:
                        from .outcome_pipeline import snapshot_shared_state
                        state_before = snapshot_shared_state(self.shared_state)

                    # Build action payload for DM adjudication (similar to players)
                    action_for_adjudication = {
                        'player_id': agent.agent_id,  # Use agent_id for NPCs (similar to player pattern)
                        'character_name': agent.name,
                        'initiative': initiative_score,
                        'action': {
                            'agent_id': agent.agent_id,  # NPC agent_id for entity lookup in DM resolution
                            'character_name': agent.name,  # Include in nested action for resolution broadcast
                            'intent': npc_intent,
                            'description': npc_description,
                            'action_type': npc_action_type,
                            'target': npc_action.get('target'),  # Include target for assist/heal/dialogue/attack actions
                            'is_npc': True,  # Flag for DM to use lightweight adjudication
                            'dialogue_content': npc_action.get('dialogue_content'),  # Preserve for DM prompt + JSONL
                        }
                    }

                    # PRE-VALIDATE AND EXECUTE NPC TRANSFER ACTIONS (before DM sees them)
                    # Similar to player transfers - prevents phantom transfers
                    if npc_action_type == 'transfer':
                        transfer_target = npc_action.get('transfer_target')
                        transfer_currency = npc_action.get('transfer_currency')
                        transfer_items = npc_action.get('transfer_items')

                        if transfer_target and (transfer_currency or transfer_items):
                            if mechanics:
                                try:
                                    # Validate transfer with NPC as sender
                                    validation = mechanics.validate_transfer(
                                        sender_state=agent,  # NPC agent as sender
                                        transfer_target=transfer_target,
                                        transfer_currency=transfer_currency,
                                        transfer_items=transfer_items,
                                        sender_position=getattr(agent, 'position', None)
                                    )

                                    # Store validation result for DM narration
                                    action_for_adjudication['transfer_validation'] = {
                                        'is_valid': validation.is_valid,
                                        'sender_name': validation.sender_name,
                                        'receiver_name': validation.receiver_name,
                                        'receiver_agent_id': validation.receiver_agent_id,
                                        'currency': validation.currency,
                                        'items': validation.items,
                                        'failure_reason': validation.failure_reason,
                                        'in_range': validation.in_range,
                                        'executed': False,
                                        'npc_initiated': True
                                    }

                                    if validation.is_valid:
                                        # Find receiver agent (player or NPC)
                                        receiver_agent = next(
                                            (a for a in self.shared_state.player_agents
                                             if a.agent_id == validation.receiver_agent_id),
                                            None
                                        )
                                        if receiver_agent is None and hasattr(self.shared_state, 'npc_agents'):
                                            receiver_agent = next(
                                                (n for n in self.shared_state.npc_agents
                                                 if n.agent_id == validation.receiver_agent_id),
                                                None
                                            )

                                        if receiver_agent:
                                            success = True

                                            # Execute currency transfer
                                            if transfer_currency:
                                                sender_purse = _get_energy_purse(agent)
                                                receiver_purse = _get_energy_purse(receiver_agent)
                                                if sender_purse and receiver_purse:
                                                    currency_success = sender_purse.transfer_currencies_to(
                                                        receiver_purse=receiver_purse,
                                                        currency_amounts=transfer_currency
                                                    )
                                                    success = success and currency_success
                                                else:
                                                    success = False

                                            # Execute item transfer
                                            if transfer_items:
                                                sender_inv = _get_inventory(agent)
                                                receiver_inv = _get_inventory(receiver_agent)
                                                for item_name, amount in transfer_items.items():
                                                    if sender_inv and item_name in sender_inv:
                                                        sender_inv[item_name] -= amount
                                                        if sender_inv[item_name] <= 0:
                                                            del sender_inv[item_name]
                                                    receiver_inv[item_name] = receiver_inv.get(item_name, 0) + amount

                                            if success:
                                                action_for_adjudication['transfer_validation']['executed'] = True
                                                logger.info(
                                                    f"✓ NPC TRANSFER EXECUTED: {agent.name} → {validation.receiver_name}: "
                                                    f"currency={transfer_currency}, items={transfer_items}"
                                                )

                                                # Log energy_transfer event
                                                if mechanics.jsonl_logger:
                                                    mechanics.jsonl_logger.log_event(
                                                        'energy_transfer',
                                                        {
                                                            'sender_id': agent.agent_id,
                                                            'sender_name': agent.name,
                                                            'receiver_id': validation.receiver_agent_id,
                                                            'receiver_name': validation.receiver_name,
                                                            'currency': transfer_currency,
                                                            'items': transfer_items,
                                                            'success': True,
                                                            'failure_reason': None,
                                                            'in_range': validation.in_range,
                                                            'npc_initiated': True
                                                        },
                                                        mechanics.current_round
                                                    )

                                except Exception as e:
                                    logger.warning(f"NPC transfer validation failed: {e}")
                                    action_for_adjudication['transfer_validation'] = {
                                        'is_valid': False,
                                        'failure_reason': str(e),
                                        'executed': False,
                                        'npc_initiated': True
                                    }

                    # Create event to track when adjudication completes
                    adjudication_event = asyncio.Event()
                    self._pending_resolutions[f"{agent.agent_id}_0"] = adjudication_event  # action_index=0 for NPCs

                    # Send action to DM for mechanical resolution (lightweight for NPCs)
                    adjudication_message = Message(
                        id=f"adjudicate_{datetime.now().isoformat()}_{agent.agent_id}",
                        type=MessageType.ACTION_DECLARED,
                        sender='coordinator',
                        recipient='dm_01',
                        payload={
                            'phase': 'resolution_only',
                            'actions': [action_for_adjudication],
                            'round': mechanics.current_round if mechanics else 0,
                            'action_index': 0,
                            'previous_resolutions': all_resolutions
                        },
                        timestamp=datetime.now()
                    )

                    await self.coordinator.message_bus._route_message(adjudication_message)

                    # Wait for DM to complete adjudication (with timeout)
                    ADJUDICATION_TIMEOUT = 86400  # seconds (24h for batch API)
                    try:
                        await asyncio.wait_for(adjudication_event.wait(), timeout=ADJUDICATION_TIMEOUT)
                    except asyncio.TimeoutError:
                        error_msg = f"NPC adjudication timeout after {ADJUDICATION_TIMEOUT}s for {agent.name}"
                        logger.error(f"❌ {error_msg}")
                        if mechanics and mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_session_error(
                                error_type="adjudication_timeout",
                                error_message=error_msg,
                                exception_type="TimeoutError",
                                context={
                                    'round': mechanics.current_round,
                                    'agent_id': agent.agent_id,
                                    'npc_name': agent.name
                                }
                            )
                        raise RuntimeError(error_msg)

                    # Check if adjudication returned an error
                    if getattr(adjudication_event, 'error', False):
                        error_msg = getattr(adjudication_event, 'error_message', 'Unknown adjudication error')
                        logger.error(f"❌ NPC adjudication failed: {error_msg}")
                        raise RuntimeError(error_msg)

                    logger.debug(f"NPC {agent.name} action adjudicated")

                    # Collect resolution for synthesis
                    resolution_data = getattr(adjudication_event, 'resolution_data', None)
                    if resolution_data:
                        all_resolutions.append(resolution_data)

                        if outcome_first:
                            from .outcome_pipeline import build_applied_outcome, snapshot_shared_state
                            outcome_sequence += 1
                            outcome_action = dict(action_for_adjudication['action'])
                            target_id = outcome_action.get('target')
                            if target_id and self.shared_state:
                                mapper = self.shared_state.get_target_id_mapper()
                                target_entity = mapper.resolve_target(target_id) if mapper else None
                                if target_entity is not None:
                                    outcome_action['target_entity_id'] = getattr(
                                        target_entity, 'agent_id', getattr(target_entity, 'object_id', target_id)
                                    )
                            applied_outcome = build_applied_outcome(
                                round_num=mechanics.current_round if mechanics else 0,
                                sequence=outcome_sequence,
                                actor_id=agent.agent_id,
                                actor_name=agent.name,
                                action=outcome_action,
                                resolution_data=resolution_data,
                                before=state_before or {},
                                after=snapshot_shared_state(self.shared_state),
                            )
                            resolution_data['applied_outcome'] = applied_outcome.model_dump(mode='json')
                            if mechanics and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_action_adjudication(
                                    mechanics.current_round,
                                    {
                                        'schema_version': applied_outcome.schema_version,
                                        'adjudication_id': applied_outcome.adjudication_id,
                                        'outcome_id': applied_outcome.outcome_id,
                                        'sequence': applied_outcome.sequence,
                                        'actor_id': applied_outcome.actor_id,
                                        'actor_name': applied_outcome.actor_name,
                                        'adjudication': resolution_data.get('adjudication') or {},
                                    },
                                )
                                mechanics.jsonl_logger.log_applied_outcome(
                                    mechanics.current_round,
                                    applied_outcome.model_dump(mode='json'),
                                )

                        # NPC resolutions go through DM adjudication, so they're already logged
                        # via the normal log_action_resolution call in dm.py

                    # Clean up pending resolution (must match key format used above)
                    if f"{agent.agent_id}_0" in self._pending_resolutions:
                        del self._pending_resolutions[f"{agent.agent_id}_0"]

        # Warn about active NPCs with no declaration this round (potential ghost agents)
        if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
            for npc in self.shared_state.npc_agents:
                if npc.is_active and npc.agent_id not in self._declared_actions:
                    logger.warning(f"Active NPC {npc.name} ({npc.agent_id}) had no declaration this round — may be a ghost agent")

        # Convert surrendered enemies to NPCs after all actions resolve
        # This happens AFTER resolution (actions invalidated) but BEFORE synthesis
        if resolution_state.surrendered and self.enemy_combat.enabled:
            from .agent_conversion import deescalate_enemy_to_npc

            for enemy_id in list(resolution_state.surrendered):
                # Find the enemy agent
                enemy = next((e for e in self.enemy_combat.enemy_agents if e.agent_id == enemy_id), None)

                if enemy and enemy.is_active:
                    # Convert to NPC with "prisoner" disposition
                    # NPC LLM fallback: npcs -> enemies -> dm (Spec 11)
                    npc = deescalate_enemy_to_npc(
                        enemy=enemy,
                        disposition="prisoner",
                        current_round=mechanics.current_round if mechanics else 0,
                        llm_provider=self._get_npc_llm_provider()
                    )

                    # Add to shared state
                    if self.shared_state:
                        self.shared_state.npc_agents.append(npc)

                        # Register in target mapper
                        if hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                            self.shared_state.target_id_mapper.register_npc(npc)

                    # Deactivate enemy (no longer in combat)
                    enemy.is_active = False
                    enemy.despawned_round = mechanics.current_round if mechanics else 0

                    logger.info(f"✅ Converted surrendered enemy {enemy_id} to NPC prisoner: {npc.name}")
                    print(f"\n✅ {enemy.name} has been detained and is no longer a threat")

        # === CLOCK UPDATE PHASE ===
        # Apply clock updates BEFORE conversion check so conversion decisions can see filled clocks
        clock_updates_applied = {}
        expired_clocks = []
        filled_clocks = []
        if mechanics:
            clock_updates_applied = mechanics.apply_queued_clock_updates()
            if clock_updates_applied:
                logger.debug(f"Applied {len(clock_updates_applied)} queued clock updates before conversion check")

                # Log aggregated updates for each clock
                for clock_name, update_data in clock_updates_applied.items():
                    before = update_data['before']
                    after = update_data['after']
                    maximum = update_data['maximum']
                    reasons = update_data['reasons']
                    direction = update_data['direction']

                    logger.debug(f"Clock {clock_name}: {before}/{maximum} → {after}/{maximum} {direction} "
                               f"(aggregated: {', '.join(reasons)})")

            # Check for expired clocks
            expired_clocks = mechanics.check_and_expire_clocks()
            if expired_clocks:
                logger.warning(f"Found {len(expired_clocks)} expired clocks: {[c['clock_name'] for c in expired_clocks]}")

            # Log filled clocks (check the update data for 'filled' flag)
            for clock_name, update_data in clock_updates_applied.items():
                if update_data.get('filled', False):
                    # Clock just filled this round
                    clock_obj = mechanics.scene_clocks.get(clock_name)
                    if clock_obj:
                        after = update_data['after']
                        maximum = update_data['maximum']
                        consequence = clock_obj.filled_consequence or 'No consequence specified'

                        logger.warning(f"🔔 Clock {clock_name} FILLED: {after}/{maximum} - triggering consequences")
                        print(f"\n⏰ CLOCK FILLED: {clock_name} ({after}/{maximum})")
                        print(f"   Consequence: {consequence}")

        # ENTITY LIFECYCLE PHASE: Morale, conversions, spawns, departures (before synthesis)
        from .schemas.story_events import EntityLifecycleResult
        entity_lifecycle_result = EntityLifecycleResult()
        conversion_decisions = None

        # Check if story advancement is pending (all clocks complete)
        # If so, SKIP Entity Lifecycle Phase - spawns/conversions don't make sense when scene is changing
        dm_agents = [agent for agent in self.agents if hasattr(agent, 'needs_story_advancement')]
        story_advancement_pending = any(dm.needs_story_advancement for dm in dm_agents) if dm_agents else False

        if story_advancement_pending:
            logger.info("⏭️  Skipping Entity Lifecycle Phase - story advancement pending (all clocks complete)")
            print(f"\n⏭️  Entity Lifecycle Phase skipped - story is advancing to new location")

        # EXPERIMENT (config-gated, observe-only, default OFF): stripped-
        # context Nexus-law adjudication of this round's resolutions.
        # Rulings are logged only - never applied to game state.
        if all_resolutions and self.config.get('post_resolution_adjudication', False):
            await self._run_post_resolution_adjudication(all_resolutions, mechanics)

        if all_resolutions and not story_advancement_pending:
            print(f"\n{'='*80}")
            print(f"🔄 ENTITY LIFECYCLE PHASE (Round {mechanics.current_round if mechanics else 0})")
            print(f"{'='*80}")

            # Step 1: Check morale for all enemies (BEFORE conversions so DM sees panic in context)
            if self.enemy_combat and self.enemy_combat.enabled:
                morale_events = self.enemy_combat.check_morale_all()
                entity_lifecycle_result.morale_events = morale_events

                if morale_events:
                    print(f"\n📊 Morale Checks:")
                    for event in morale_events:
                        print(f"   - {event['character_name']}: {event['type']} ({event.get('narration', '')})")
                        logger.info(f"Morale event: {event['character_name']} {event['type']}")

            # Step 2: Build resolution summary for DM context (include morale results)
            resolution_summary = self._build_resolution_summary(all_resolutions)

            # Extract social target IDs (enemies targeted by successful non-damage PC actions)
            social_target_ids = self._extract_social_target_ids(all_resolutions)

            # Add morale events to resolution summary for DM context
            if entity_lifecycle_result.morale_events:
                morale_summary = "\n\nMORALE EVENTS THIS ROUND:\n"
                for event in entity_lifecycle_result.morale_events:
                    morale_summary += f"- {event['character_name']}: {event['type']} ({event['narration']})\n"
                resolution_summary += morale_summary

            # Find DM agent
            dm_agent = None
            for agent in self.agents:
                if agent.agent_id.startswith('dm_'):
                    dm_agent = agent
                    break

            # Step 3: Get conversion decisions from DM
            if dm_agent and hasattr(dm_agent, 'check_conversions'):
                try:
                    conversion_decisions = await dm_agent.check_conversions(
                        round_number=mechanics.current_round if mechanics else 0,
                        resolution_summary=resolution_summary,
                        social_target_ids=social_target_ids if social_target_ids else None
                    )
                    entity_lifecycle_result.conversion_decisions = conversion_decisions

                    print(f"\n✅ Conversion decisions:")
                    print(f"   - Enemy conversions: {len(conversion_decisions.enemy_conversions)}")
                    print(f"   - NPC escalations: {len(conversion_decisions.escalations)}")
                    print(f"   - NPC spawns: {len(conversion_decisions.npc_spawns)}")
                    print(f"   - NPC departures: {len(conversion_decisions.npc_departures)}")
                    print(f"   - Enemy departures: {len(conversion_decisions.enemy_departures)}")
                    print(f"   - Enemy spawns: {len(conversion_decisions.enemy_spawns)}")
                    print(f"   - Reasoning: {conversion_decisions.reasoning}")

                    logger.info(f"Conversion check complete: {len(conversion_decisions.enemy_conversions)} conversions, "
                               f"{len(conversion_decisions.escalations)} escalations, {len(conversion_decisions.npc_spawns)} NPC spawns, "
                               f"{len(conversion_decisions.npc_departures)} NPC departures, {len(conversion_decisions.enemy_departures)} enemy departures, "
                               f"{len(conversion_decisions.enemy_spawns)} enemy spawns")

                    # Step 4: Process enemy spawns from conversion check immediately (before synthesis)
                    if conversion_decisions.enemy_spawns and self.enemy_combat:
                        # Enable enemy combat if we're spawning enemies (even if it started disabled)
                        if not self.enemy_combat.enabled:
                            logger.info("Enabling enemy combat due to conversion check enemy spawn")
                            self.enemy_combat.enabled = True

                        from .schemas.story_events import EnemySpawn

                        # Reconstruct EnemySpawn objects if they're dicts
                        enemy_spawn_list = []
                        for enemy_spawn in conversion_decisions.enemy_spawns:
                            if isinstance(enemy_spawn, dict):
                                enemy_spawn = EnemySpawn(**enemy_spawn)
                            enemy_spawn_list.append(enemy_spawn)

                        # Spawn all enemies using spawn_from_structured
                        spawn_notifications = self.enemy_combat.spawn_from_structured(enemy_spawn_list)

                        # Track spawned enemy agent_ids
                        for enemy in self.enemy_combat.enemy_agents:
                            if enemy.spawned_round == (mechanics.current_round if mechanics else 0):
                                entity_lifecycle_result.enemies_spawned.append(enemy.agent_id)

                        # Print spawn notifications
                        for notification in spawn_notifications:
                            print(f"\n{notification}")
                            logger.info(f"Enemy spawn: {notification}")

                    # Process enemy conversions with validation
                    if conversion_decisions.enemy_conversions and self.enemy_combat and self.enemy_combat.enabled:
                        from .conversion_validation import validate_enemy_conversion, auto_correct_conversion
                        from .agent_conversion import deescalate_enemy_to_npc

                        for enemy_conversion in conversion_decisions.enemy_conversions:
                            # Validate conversion
                            is_valid, error_msg, suggested_id = validate_enemy_conversion(
                                enemy_conversion.enemy_id,
                                self.enemy_combat.enemy_agents,
                                defeated_enemies=[]  # TODO: Track defeated enemies
                            )

                            if not is_valid:
                                # Try auto-correction for high-confidence matches
                                corrected_id = auto_correct_conversion(
                                    enemy_conversion.enemy_id,
                                    self.enemy_combat.enemy_agents,
                                    threshold=0.8
                                )

                                if corrected_id:
                                    logger.warning(f"Auto-corrected enemy conversion: {enemy_conversion.enemy_id} → {corrected_id}")
                                    print(f"⚠️  Auto-corrected conversion ID: {enemy_conversion.enemy_id} → {corrected_id}")
                                    enemy_conversion.enemy_id = corrected_id
                                    is_valid = True
                                else:
                                    logger.warning(f"Skipping invalid enemy conversion: {error_msg}")
                                    print(f"\n⚠️  {error_msg}")
                                    continue

                            # Find and convert the enemy
                            enemy = next((e for e in self.enemy_combat.enemy_agents
                                        if e.agent_id == enemy_conversion.enemy_id), None)

                            if enemy and enemy.is_active:
                                from .schemas.story_events import EnemyResolution

                                # Handle different conversion types
                                if enemy_conversion.resolution == EnemyResolution.FLED:
                                    # Enemy leaves scene
                                    enemy.is_active = False
                                    enemy.despawned_round = mechanics.current_round if mechanics else 0
                                    logger.info(f"Enemy fled: {enemy.name} ({enemy.agent_id})")
                                    print(f"\n✓ {enemy.name} has fled the scene")

                                elif enemy_conversion.resolution in [EnemyResolution.CONVINCED,
                                                                     EnemyResolution.NEUTRALIZED,
                                                                     EnemyResolution.SUBDUED]:
                                    # Enemy becomes NPC
                                    # NPC LLM fallback: npcs -> enemies -> dm (Spec 11)
                                    npc = deescalate_enemy_to_npc(
                                        enemy=enemy,
                                        disposition=enemy_conversion.resulting_disposition or "prisoner",
                                        current_round=mechanics.current_round if mechanics else 0,
                                        llm_provider=self._get_npc_llm_provider()
                                    )

                                    # Add to shared state
                                    if self.shared_state:
                                        self.shared_state.npc_agents.append(npc)

                                        # Register in target mapper
                                        if hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                                            self.shared_state.target_id_mapper.register_npc(npc)

                                    # Deactivate enemy
                                    enemy.is_active = False
                                    enemy.despawned_round = mechanics.current_round if mechanics else 0

                                    # Track conversion in lifecycle result
                                    entity_lifecycle_result.enemies_converted.append(enemy.agent_id)

                                    logger.info(f"Converted enemy to NPC: {enemy.name} → {npc.name}")
                                    print(f"\n✓ {enemy.name} converted to NPC ({enemy_conversion.resolution.value})")

                    # Process NPC escalations with validation
                    if conversion_decisions.escalations and self.shared_state and self.shared_state.npc_agents:
                        from .conversion_validation import validate_npc_escalation
                        from .agent_conversion import escalate_npc_to_enemy

                        for escalation in conversion_decisions.escalations:
                            # Validate escalation
                            active_enemies = self.enemy_combat.enemy_agents if self.enemy_combat and self.enemy_combat.enabled else []
                            is_valid, error_msg, suggested_id = validate_npc_escalation(
                                escalation.npc_id,
                                self.shared_state.npc_agents,
                                active_enemies=active_enemies
                            )

                            if not is_valid:
                                logger.warning(f"Skipping invalid NPC escalation: {error_msg}")
                                print(f"\n⚠️  {error_msg}")
                                continue

                            # Find and escalate the NPC
                            npc = next((n for n in self.shared_state.npc_agents
                                      if n.agent_id == escalation.npc_id), None)

                            if npc:
                                enemy = escalate_npc_to_enemy(
                                    npc=npc,
                                    template_override=escalation.template,
                                    current_round=mechanics.current_round if mechanics else 0
                                )

                                # Add to enemy combat
                                if self.enemy_combat and self.enemy_combat.enabled:
                                    self.enemy_combat.enemy_agents.append(enemy)

                                    # Register in target mapper
                                    if self.shared_state and hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                                        self.shared_state.target_id_mapper.register_enemy(enemy)

                                # Remove from NPC list
                                self.shared_state.npc_agents.remove(npc)

                                # Track escalation in lifecycle result
                                entity_lifecycle_result.npcs_escalated.append(npc.agent_id)

                                logger.info(f"Escalated NPC to enemy: {npc.name} → {enemy.name}")
                                print(f"\n✓ {npc.name} escalated to hostile combatant")

                    # Process NPC spawns from conversion check
                    if conversion_decisions.npc_spawns and self.shared_state:
                        from .schemas.story_events import NPCSpawn
                        from .npc_agent import NPCAgent, next_npc_agent_id

                        # Collect PC names to prevent NPC spawns that duplicate player characters
                        pc_names = set()
                        for pa in self.shared_state.player_agents:
                            if hasattr(pa, 'character_state') and hasattr(pa.character_state, 'name'):
                                pc_names.add(pa.character_state.name)

                        for npc_spawn in conversion_decisions.npc_spawns:
                            # Reconstruct NPCSpawn if it's a dict
                            if isinstance(npc_spawn, dict):
                                npc_spawn = NPCSpawn(**npc_spawn)

                            # Block NPC spawns that duplicate player character names
                            if npc_spawn.name in pc_names:
                                logger.warning(f"🚫 NPC spawn blocked: '{npc_spawn.name}' is a player character")
                                print(f"\n🚫 NPC spawn blocked: '{npc_spawn.name}' conflicts with player character name")
                                continue

                            # Check if NPC with same name already exists (prevent duplicates)
                            existing_npc = next((npc for npc in self.shared_state.npc_agents if npc.name == npc_spawn.name), None)
                            if existing_npc:
                                logger.info(f"NPC '{npc_spawn.name}' already exists ({existing_npc.agent_id}), skipping spawn")
                                print(f"\n⏭️  NPC '{npc_spawn.name}' already present, skipping spawn")
                                continue

                            # Create NPC agent
                            npc = NPCAgent(
                                agent_id=next_npc_agent_id(
                                    npc_spawn.name, self.shared_state.issued_npc_ids),
                                name=npc_spawn.name,
                                faction=npc_spawn.faction,
                                disposition=npc_spawn.disposition,
                                entity_type=npc_spawn.entity_type,
                                threat_level=npc_spawn.threat_level,
                                health=npc_spawn.health,
                                max_health=npc_spawn.health,
                                soak=npc_spawn.soak,
                                void_score=0,  # NPCs start with no void
                                skills=npc_spawn.skills,
                                description=npc_spawn.description,
                                llm_provider=self._get_npc_llm_provider()  # NPC LLM fallback: npcs -> enemies -> dm (Spec 11)
                            )

                            # Add to shared state
                            self.shared_state.npc_agents.append(npc)

                            # Register in target mapper
                            if hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                                self.shared_state.target_id_mapper.register_npc(npc)

                            # Track NPC spawn in lifecycle result
                            entity_lifecycle_result.npcs_spawned.append(npc.agent_id)

                            logger.info(f"NPC spawned: {npc.name} ({npc.agent_id})")
                            print(f"\n✓ NPC entered scene: {npc.name} ({npc.entity_type}, {npc.disposition})")

                    # Process NPC departures from conversion check (aggressive removal)
                    if conversion_decisions.npc_departures and self.shared_state:
                        for npc_identifier in conversion_decisions.npc_departures:
                            # Find NPC to get name before removal
                            npc = self.shared_state.get_npc_by_id(npc_identifier)
                            npc_name = npc.name if npc else npc_identifier

                            removed = self.shared_state.remove_npc(npc_identifier)
                            if removed:
                                # Track departure in lifecycle result
                                entity_lifecycle_result.npcs_departed.append(npc_identifier)

                                # Log NPC departure to JSONL
                                if mechanics and mechanics.jsonl_logger:
                                    mechanics.jsonl_logger.log_npc_departure(
                                        round_num=mechanics.current_round,
                                        npc_id=npc_identifier,
                                        npc_name=npc_name,
                                        departure_reason="entity_lifecycle_removal"
                                    )

                                logger.info(f"👤 NPC departed (entity lifecycle): {npc_identifier}")
                                print(f"\n👤 NPC departed: {npc_name}")
                            else:
                                logger.warning(f"Failed to remove NPC '{npc_identifier}' - not found in npc_agents")

                    # Process environmental object spawns from conversion check
                    if conversion_decisions.env_object_spawns and self.shared_state:
                        from .schemas.story_events import EnvObjectSpawn
                        from .shared_state import EnvironmentalObject, EnvironmentalObjectType

                        for env_spawn in conversion_decisions.env_object_spawns:
                            # Reconstruct EnvObjectSpawn if it's a dict
                            if isinstance(env_spawn, dict):
                                env_spawn = EnvObjectSpawn(**env_spawn)

                            # Parse object type
                            try:
                                object_type = EnvironmentalObjectType[env_spawn.object_type.upper()]
                            except KeyError:
                                logger.warning(f"Invalid object_type '{env_spawn.object_type}', skipping spawn")
                                continue

                            # Create environmental object instance
                            env_object = EnvironmentalObject(
                                object_type=object_type,
                                name=env_spawn.name,
                                description=env_spawn.description,
                                state=env_spawn.initial_state
                            )

                            # Add to shared state
                            self.shared_state.add_env_object(env_object)

                            # Track in lifecycle result
                            entity_lifecycle_result.env_objects_spawned.append(env_object.object_id)

                            logger.info(f"Environmental object spawned: {env_object.name} ({env_spawn.object_type}), object_id={env_object.object_id}")
                            logger.info(f"Reason: {env_spawn.narrative_reason}")
                            print(f"\n🏗️  Environmental object appeared: {env_object.name} ({env_spawn.object_type})")

                    # Process enemy departures from conversion check (aggressive removal)
                    if conversion_decisions.enemy_departures and self.enemy_combat and self.enemy_combat.enabled:
                        for enemy_identifier in conversion_decisions.enemy_departures:
                            # Find enemy to get name before removal
                            enemy = next((e for e in self.enemy_combat.enemy_agents
                                        if e.agent_id == enemy_identifier), None)
                            enemy_name = enemy.name if enemy else enemy_identifier

                            if enemy and enemy.is_active:
                                # Deactivate enemy (mark as despawned)
                                enemy.is_active = False
                                enemy.despawned_round = mechanics.current_round if mechanics else 0

                                # Track departure in lifecycle result
                                entity_lifecycle_result.enemies_departed.append(enemy_identifier)

                                # Log enemy departure to JSONL (reuse enemy_defeat event with special reason)
                                if mechanics and mechanics.jsonl_logger:
                                    rounds_survived = enemy.despawned_round - enemy.spawned_round
                                    mechanics.jsonl_logger.log_enemy_defeat(
                                        round_num=mechanics.current_round,
                                        enemy_id=enemy_identifier,
                                        enemy_name=enemy_name,
                                        defeat_reason='departed',  # Special reason for departures (entity_lifecycle_removal)
                                        rounds_survived=rounds_survived
                                    )

                                logger.info(f"⚔️  Enemy departed (entity lifecycle): {enemy_identifier}")
                                print(f"\n⚔️  Enemy departed: {enemy_name}")
                            else:
                                logger.debug(f"Enemy '{enemy_identifier}' already inactive (auto-despawned) - skipping departure")

                except Exception as e:
                    logger.warning(f"Conversion check failed: {type(e).__name__}: {e}")
                    print(f"\n⚠️  Conversion check failed: {type(e).__name__}: {e}")
                    # Log traceback for debugging
                    import traceback
                    logger.debug(f"Conversion check traceback:\n{traceback.format_exc()}")
                    # Continue with empty conversion decisions
                    from .schemas.story_events import ConversionDecisions
                    conversion_decisions = ConversionDecisions(
                        enemy_conversions=[],
                        escalations=[],
                        npc_spawns=[],
                        npc_departures=[],
                        enemy_departures=[],
                        enemy_spawns=[],
                        reasoning="Conversion check failed, proceeding without conversions"
                    )
            else:
                logger.debug("DM agent not found or doesn't have check_conversions method - skipping entity lifecycle")

        # Log EntityLifecycleResult to JSONL (if any lifecycle events occurred)
        if (entity_lifecycle_result.morale_events or
            entity_lifecycle_result.enemies_spawned or
            entity_lifecycle_result.npcs_spawned or
            entity_lifecycle_result.enemies_converted or
            entity_lifecycle_result.npcs_escalated or
            entity_lifecycle_result.npcs_departed or
            entity_lifecycle_result.enemies_departed or
            entity_lifecycle_result.env_objects_spawned):

            if mechanics and mechanics.jsonl_logger:
                lifecycle_dict = entity_lifecycle_result.to_jsonl_dict(
                    round_num=mechanics.current_round
                )
                mechanics.jsonl_logger.log_event(
                    'entity_lifecycle',
                    lifecycle_dict,
                    round_num=mechanics.current_round
                )

            # Print entity lifecycle summary
            print(f"\n{entity_lifecycle_result.to_synthesis_context()}")
            logger.info(f"Entity lifecycle complete: {len(entity_lifecycle_result.morale_events)} morale events, "
                       f"{len(entity_lifecycle_result.enemies_spawned)} enemies spawned, "
                       f"{len(entity_lifecycle_result.npcs_spawned)} NPCs spawned, "
                       f"{len(entity_lifecycle_result.enemies_converted)} enemies converted, "
                       f"{len(entity_lifecycle_result.npcs_escalated)} NPCs escalated, "
                       f"{len(entity_lifecycle_result.npcs_departed)} NPCs departed, "
                       f"{len(entity_lifecycle_result.env_objects_spawned)} env objects spawned")

        # Generate single synthesis from all collected resolutions
        if all_resolutions:
            print("\n=== Generating Round Synthesis ===")
            logger.debug(f"Sending {len(all_resolutions)} resolutions to DM for synthesis")

            # Reset synthesis event before requesting synthesis
            self._synthesis_complete.clear()

            # Convert EntityLifecycleResult to dict for message serialization
            from dataclasses import asdict
            entity_lifecycle_dict = asdict(entity_lifecycle_result) if entity_lifecycle_result else None

            synthesis_message = Message(
                id=f"synthesis_{datetime.now().isoformat()}",
                type=MessageType.ACTION_DECLARED,
                sender='coordinator',
                recipient='dm_01',
                payload={
                    'phase': 'synthesis',
                    'resolutions': all_resolutions,
                    'round': mechanics.current_round if mechanics else 0,
                    'resolution_state': resolution_state,  # Include fled NPCs for synthesis context
                    'conversion_decisions': conversion_decisions,  # Include conversion check results for DM narrative
                    'entity_lifecycle_result': entity_lifecycle_dict,  # Include entity lifecycle (morale, spawns, conversions)
                    'expired_clocks': expired_clocks  # Include expired clocks from clock update phase
                },
                timestamp=datetime.now()
            )

            await self.coordinator.message_bus._route_message(synthesis_message)

            # Wait for DM to complete and broadcast synthesis
            await self._synthesis_complete.wait()
            logger.debug("Round synthesis complete")

        # PHASE 3: CLEANUP
        if self.enemy_combat.enabled:
            print("\n=== Cleanup Phase ===")
            cleanup_events = self.enemy_combat.cleanup_round()

            for event in cleanup_events:
                narration = self._resolve_target_ids_in_text(event['narration'])
                print(f"[CLEANUP] {narration}")

                if mechanics and mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        event_type=event['type'],
                        data=event,
                        round_num=mechanics.current_round
                    )

            # Tick player buffs (reduce durations, remove expired)
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
            for player in player_agents:
                if hasattr(player, 'tick_buffs'):
                    player.tick_buffs()

            # Log character state snapshots for all players (for ML training/balance analysis)
            if mechanics and mechanics.jsonl_logger:
                for player in player_agents:
                    if hasattr(player, 'character_state'):
                        char_state = player.character_state
                        # Health/wounds/stuns are stored on player agent, not CharacterState
                        # Calculate death state based on wounds (6+ = dead), health (0 = unconscious), stuns (6+ = KO)
                        wounds = player.wounds if hasattr(player, 'wounds') else 0
                        health = player.health if hasattr(player, 'health') else 0
                        stuns = player.stuns if hasattr(player, 'stuns') else 0
                        # Shared oracle — end_state_snapshot reads the same function,
                        # so the two records cannot disagree again.
                        death_state = derive_death_state(player)

                        # Extract economic data from energy_purse
                        energy_data = {}
                        seeds_data = {}
                        if hasattr(char_state, 'energy_purse') and char_state.energy_purse:
                            purse = char_state.energy_purse
                            energy_data = {
                                "breath": purse.breath,
                                "drip": purse.drip,
                                "grain": purse.grain,
                                "spark": purse.spark,
                                "hollow": purse.hollow,
                            }
                            seeds_data = {
                                "raw": purse.count_seeds(SeedType.RAW),
                                "attuned": purse.count_seeds(SeedType.ATTUNED),
                                "hollow": purse.count_seeds(SeedType.HOLLOW),
                            }

                        mechanics.jsonl_logger.log_character_state(
                            round_num=mechanics.current_round,
                            character_id=player.agent_id,
                            character_name=char_state.name,
                            health=health,
                            max_health=player.max_health if hasattr(player, 'max_health') else 0,
                            wounds=wounds,
                            void_score=char_state.void_score if hasattr(char_state, 'void_score') else 0,
                            soulcredit=char_state.soulcredit if hasattr(char_state, 'soulcredit') else 0,
                            position=str(getattr(player, 'position', 'Unknown')),
                            conditions=_serialize_conditions(mechanics, player.agent_id),
                            is_defeated=(death_state != "alive"),
                            death_state=death_state,
                            stuns=stuns,  # Diagnose stun-KO (>= 6) vs wound/health defeat
                            energy=energy_data,
                            seeds=seeds_data
                        )

                        # Log narrative memory state for ML training
                        if hasattr(player, 'narrative_memory') and player.narrative_memory:
                            mechanics.jsonl_logger.log_narrative_memory(
                                round_num=mechanics.current_round,
                                agent_id=player.agent_id,
                                character_name=char_state.name,
                                locations_visited=player.narrative_memory.locations_visited,
                                story_beats=player.narrative_memory.story_beats,
                                story_summary=player.narrative_memory.story_summary
                            )

                # Log character state snapshots for all active enemies (for ML training/balance analysis)
                if self.enemy_combat.enabled:
                    for enemy in self.enemy_combat.enemy_agents:
                        if enemy.is_active:  # Only log active enemies
                            mechanics.jsonl_logger.log_character_state(
                                round_num=mechanics.current_round,
                                **character_state_row(enemy, mechanics, agent='enemy')
                            )

                # ...and for active NPCs. Without this an entity de-escalated to
                # prisoner vanished from the oracle at the moment of arrest —
                # the lawful outcome was the one that went unobserved.
                for npc in (getattr(self.shared_state, 'npc_agents', None) or []):
                    if getattr(npc, 'is_active', True):
                        mechanics.jsonl_logger.log_character_state(
                            round_num=mechanics.current_round,
                            **character_state_row(npc, mechanics, agent='npc')
                        )

                # Cross-check what was just written against live engine state.
                self._check_log_fidelity(mechanics, player_agents)

                # Log round summary for balance analysis
                active_enemy_count = len([e for e in self.enemy_combat.enemy_agents if e.is_active]) if self.enemy_combat.enabled else 0
                player_wounds_total = sum(player.wounds for player in player_agents if hasattr(player, 'wounds'))

                # Compute clocks advanced/filled THIS ROUND (delta tracking)
                clocks_advanced = 0
                clocks_regressed = 0
                clocks_filled = 0
                total_ticks_advanced = 0
                total_ticks_regressed = 0

                if mechanics.scene_clocks and clock_state_start:
                    for clock_name, clock in mechanics.scene_clocks.items():
                        # Compare with starting state
                        if clock_name in clock_state_start:
                            start_current = clock_state_start[clock_name]['current']
                            end_current = clock.current

                            # Calculate delta
                            delta = end_current - start_current

                            if delta > 0:
                                clocks_advanced += 1
                                total_ticks_advanced += delta
                            elif delta < 0:
                                clocks_regressed += 1
                                total_ticks_regressed += abs(delta)

                            # Check if filled THIS ROUND
                            if clock.filled and not clock_state_start[clock_name]['filled']:
                                clocks_filled += 1

                round_summary = {
                    'actions_attempted': self._round_stats['actions_attempted'],
                    'success_count': self._round_stats['success_count'],
                    'success_rate': (self._round_stats['success_count'] / self._round_stats['actions_attempted']) if self._round_stats['actions_attempted'] > 0 else 0.0,
                    'avg_margin': (self._round_stats['total_margin'] / self._round_stats['actions_attempted']) if self._round_stats['actions_attempted'] > 0 else 0.0,
                    'damage_dealt_by_players': self._round_stats['damage_dealt_by_players'],
                    'damage_taken_by_players': self._round_stats['damage_taken_by_players'],
                    'void_gained': self._round_stats['void_gained'],
                    'void_lost': self._round_stats['void_lost'],
                    'clocks_advanced': clocks_advanced,  # Number of clocks that advanced THIS ROUND
                    'clocks_regressed': clocks_regressed,  # Number of clocks that regressed THIS ROUND
                    'clocks_filled': clocks_filled,  # Number of clocks that FILLED THIS ROUND
                    'total_ticks_advanced': total_ticks_advanced,  # Total ticks advanced across all clocks THIS ROUND
                    'total_ticks_regressed': total_ticks_regressed,  # Total ticks regressed across all clocks THIS ROUND
                    'active_enemies': active_enemy_count,
                    'player_wounds_total': player_wounds_total
                }

                mechanics.jsonl_logger.log_round_summary(
                    round_num=mechanics.current_round,
                    summary=round_summary
                )

                # Reset round stats for next round
                self._round_stats = {
                    'actions_attempted': 0,
                    'success_count': 0,
                    'total_margin': 0,
                    'damage_dealt_by_players': 0,
                    'damage_taken_by_players': 0,
                    'void_gained': 0,
                    'void_lost': 0,
                    'clocks_advanced': 0,
                    'clocks_filled': 0
                }

            # Check if all clocks are complete and trigger story advancement
            await self._check_and_trigger_story_advancement()

        # Tick condition durations for all agents at end of round
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics:
            all_agent_ids = list(mechanics.conditions.keys())
            for agent_id in all_agent_ids:
                expired = mechanics.tick_conditions(agent_id)
                if expired:
                    logger.info(f"Conditions expired for {agent_id}: {', '.join(expired)}")

        # End-of-round stun recovery. DISABLED by default (STUN_RECOVERY_PER_ROUND=0):
        # "if you get clobbered it's over" — the Beaten health-check gate already
        # governs acting-while-stunned, and stuns clear via a medic/heal action or
        # scene end, not automatic decay (YAGS-faithful). Guarded so it's zero-cost
        # when disabled; flip the constant >0 to re-enable per-round bleed-off.
        from .mechanics import recover_stuns, STUN_RECOVERY_PER_ROUND
        if STUN_RECOVERY_PER_ROUND > 0:
            combatants = list(self.agents)
            if hasattr(self, 'enemy_combat') and hasattr(self.enemy_combat, 'enemy_agents'):
                combatants += list(self.enemy_combat.enemy_agents)
            for c in combatants:
                old = getattr(c, 'stuns', 0) or 0
                if old > 0:
                    new = recover_stuns(old)
                    c.stuns = new
                    nm = getattr(getattr(c, 'character_state', None), 'name', None) or getattr(c, 'name', '?')
                    logger.debug(f"Stun recovery: {nm} {old} -> {new}")

        # Clear the action buffer for next round
        self._declared_actions.clear()

        # Reset free action slots for all players
        for agent in self.agents:
            if hasattr(agent, 'free_action_used'):
                agent.free_action_used = False

        return True  # Combat continues

    def track_action_resolution(self, success: bool, margin: int):
        """Track action resolution for round summary statistics."""
        self._round_stats['actions_attempted'] += 1
        if success:
            self._round_stats['success_count'] += 1
        self._round_stats['total_margin'] += margin

    def track_outcome_statistics(self, applied_outcome) -> None:
        """Record an outcome-first resolution in the round-summary counters.

        track_action_resolution() is only reached from the legacy dm.py path.
        With outcome_first_narration on — the recommended baseline — resolution
        runs through the outcome pipeline instead, so every round_summary logged
        actions_attempted 0 and average_margin +0.0 no matter what happened.
        """
        if applied_outcome is None:
            return

        # AppliedOutcome keeps the dice under `roll_result`; there are no
        # top-level .margin / .success_tier attributes to read.
        roll = getattr(applied_outcome, 'roll_result', None)
        if not isinstance(roll, dict) or not roll:
            # No roll happened (e.g. pure dialogue) — not an attempted action.
            return

        margin = roll.get('margin') or 0
        try:
            margin = int(margin)
        except (TypeError, ValueError):
            margin = 0

        success = roll.get('success')
        if success is None:
            success = str(roll.get('success_tier') or '').lower() in _SUCCESS_TIERS

        self.track_action_resolution(success=bool(success), margin=margin)

    def track_player_damage_dealt(self, damage: int):
        """Track damage dealt by players for round summary."""
        self._round_stats['damage_dealt_by_players'] += damage

    def track_player_damage_taken(self, damage: int):
        """Track damage taken by players for round summary."""
        self._round_stats['damage_taken_by_players'] += damage

    def track_void_change(self, delta: int):
        """Track void score changes for round summary."""
        if delta > 0:
            self._round_stats['void_gained'] += delta
        elif delta < 0:
            self._round_stats['void_lost'] += abs(delta)

    async def _run_dm_turn(self):
        """Run DM turn."""
        dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
        
        if dm_agents:
            dm_agent = dm_agents[0]
            dm_message = Message(
                id=f"dm_turn_{datetime.now().isoformat()}",
                type=MessageType.TURN_REQUEST,
                sender='coordinator',
                recipient=dm_agent.agent_id,
                payload={'phase': 'dm_narrative'},
                timestamp=datetime.now()
            )
            
            await self.coordinator.message_bus._route_message(dm_message)

        # Wait for DM response
        await asyncio.sleep(2)

    async def _check_vendor_spawn(self, round_count: int):
        """Check if a vendor should randomly spawn this round."""
        vendor_frequency = self.config.get('vendor_spawn_frequency', -1)

        # -1 means vendors never spawn randomly
        if vendor_frequency <= 0:
            return

        # Check if this is a spawn round
        if round_count % vendor_frequency != 0:
            return

        # Get DM agent
        dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
        if not dm_agents:
            return

        dm_agent = dm_agents[0]

        # Get current scenario theme for context-aware vendor selection
        scenario = dm_agent.current_scenario
        scenario_theme = scenario.theme if scenario else "neutral"

        # Use DM's contextual vendor selection logic
        vendor = dm_agent._select_contextual_vendor(scenario_theme)

        if vendor:
            # Update scenario with active vendor
            if scenario:
                scenario.active_vendor = vendor

            # Announce vendor arrival to all players
            print(f"\n💰 [Vendor Arrives] {vendor.name} ({vendor.vendor_type.value})")
            print(f"   Faction: {vendor.faction}")
            print(f"   {vendor.greeting}")

            # Send notification to all players
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]

            vendor_announcement = f"\n💰 **{vendor.name} arrives!**\n"
            vendor_announcement += f"A {vendor.faction} {vendor.vendor_type.value} approaches.\n"
            vendor_announcement += f'"{vendor.greeting}"\n'
            vendor_announcement += f"They have goods for sale or barter."

            for player_agent in player_agents:
                # Send as a DM narration message
                vendor_msg = Message(
                    id=f"vendor_spawn_{round_count}_{datetime.now().isoformat()}",
                    type=MessageType.DM_NARRATION,
                    sender='dm',
                    recipient=player_agent.agent_id,
                    payload={'narration': vendor_announcement},
                    timestamp=datetime.now()
                )
                await self.coordinator.message_bus._route_message(vendor_msg)

            logger.info(f"Round {round_count}: Spawned vendor {vendor.name}")

    async def _run_mission_debrief(self):
        """Run post-mission debrief where players discuss what happened."""
        print(f"\n{'='*60}")
        print(f"=== MISSION DEBRIEF ===")
        print(f"{'='*60}\n")

        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]

        if not player_agents or not player_agents[0].llm_config:
            print("[Debrief skipped - no AI players]\n")
            return

        if self.replay_mode:
            # Debriefs are post-session flavor, and the source smoke fixture
            # does not contain debrief LLM calls. Never create a live provider
            # during an otherwise fully cached replay.
            print("[Debrief skipped - no cached replay responses]\n")
            return

        # Build debrief context
        mechanics = self.shared_state.get_mechanics_engine()

        # Sync final state from mechanics engine to player character states
        if mechanics:
            for player in player_agents:
                player_id = player.agent_id
                # Sync void from mechanics to character state
                if player_id in mechanics.void_states:
                    player.character_state.void_score = mechanics.void_states[player_id].score
                # Sync soulcredit from mechanics to character state
                if player_id in mechanics.soulcredit_states:
                    player.character_state.soulcredit = mechanics.soulcredit_states[player_id].score

        # Get final state
        void_states = []
        for player in player_agents:
            void_score = player.character_state.void_score
            sc_score = player.character_state.soulcredit
            void_states.append(f"{player.character_state.name}: Void {void_score}/10, Soulcredit {sc_score}")

        clocks_status = []
        if mechanics and mechanics.scene_clocks:
            for name, clock in mechanics.scene_clocks.items():
                clocks_status.append(f"{name}: {clock.current}/{clock.maximum}")

        # Prompt each player for debrief (sequential for conversation flow)
        debriefs = []
        for player in player_agents:
            try:
                # Use player's configured LLM provider instead of hardcoded Anthropic
                from .llm_provider import LLMConfig, create_provider

                provider_config = LLMConfig.from_dict(player.llm_config, max_tokens=250)
                provider = create_provider(provider_config)

                # Get scenario situation from player's current_scenario
                scenario_situation = "Mission completed"
                if player.current_scenario:
                    scenario_situation = player.current_scenario.get('situation', 'Unknown situation')

                # Build conversation history from previous debriefs
                conversation_so_far = ""
                if debriefs:
                    conversation_so_far = "\n\n**What others have said:**\n"
                    for prev_name, prev_statement in debriefs:
                        conversation_so_far += f"{prev_name}: \"{prev_statement}\"\n"
                    conversation_so_far += "\nYou can respond to what they said or add your own perspective.\n"

                # Check if player is dead and modify prompt accordingly
                is_dead = not player.is_alive if hasattr(player, 'is_alive') else False
                wounds = player.wounds if hasattr(player, 'wounds') else 0

                if is_dead:
                    # Dead player - give dying words
                    debrief_prompt = f"""You are {player.character_state.name} ({player.character_state.faction}) giving your FINAL WORDS before dying.

**You are DEAD.** You took {wounds} fatal wounds and failed your death save. You are bleeding out, taking your last breaths.

**Mission Context:**
{scenario_situation}

**Your Faction**: {player.character_state.faction}
**Your Goals (unfulfilled)**: {', '.join(player.character_state.goals)}
{conversation_so_far}

Provide a brief (1-2 sentence) dying statement in character voice:
- Final words, regrets, or defiant last stand
- Something meaningful to say before you die
- Keep it dramatic but not melodramatic

Examples: "Tell... tell them the truth about..." or "Not like this... *coughs blood* not like this..." or "I die as I lived - fighting the void"

Keep it brief and impactful. You're dying."""
                else:
                    # Build narrative summary from round syntheses
                    narrative_summary = ""
                    if self._round_synthesis_history:
                        narrative_summary = "\n**What Happened During the Mission:**\n"
                        for round_num, synthesis_text in self._round_synthesis_history:
                            # Truncate to 400 chars per round for brevity
                            summary = synthesis_text[:400] + "..." if len(synthesis_text) > 400 else synthesis_text
                            narrative_summary += f"Round {round_num}: {summary}\n\n"

                    # Alive player - normal debrief
                    debrief_prompt = f"""You are {player.character_state.name} ({player.character_state.faction}) in a post-mission debrief conversation.

**Mission Context:**
{scenario_situation}
{narrative_summary}
**Final Status:**
{chr(10).join(void_states)}
{chr(10).join(clocks_status) if clocks_status else 'No clocks tracked'}

**Your Faction**: {player.character_state.faction}
**Your Goals**: {', '.join(player.character_state.goals)}
{conversation_so_far}

Provide a brief (2-3 sentence) debrief statement in character voice:
- What did you accomplish or learn?
- How do you feel about working with your companion(s)?
- What are your concerns going forward?
{"- You can respond to what your companion said" if debriefs else ""}

Keep it conversational and in character. This is a dialogue, not a report."""

                # Use llm_provider's generate method (works for all providers)
                # Retry up to 3 times if response is empty
                debrief_text = ""
                max_retries = 3
                for attempt in range(max_retries):
                    response = await provider.generate(
                        prompt=debrief_prompt,
                        max_tokens=4000,  # Increased from 2000 - prevent OpenAI finish_reason:length errors
                        temperature=player.llm_config.get('temperature', 1.0)
                    )

                    debrief_text = response.text.strip()

                    if debrief_text:
                        # Success - got non-empty response
                        break
                    else:
                        # Empty response - log and retry
                        logger.warning(f"Debrief attempt {attempt + 1}/{max_retries} returned empty for {player.character_state.name}")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying debrief generation for {player.character_state.name}...")

                # Check if debrief is still empty after all retries
                if not debrief_text:
                    print(f"⚠️  [{player.character_state.name}] (debrief generation returned empty after {max_retries} attempts)\n")
                    # Still add to debriefs so conversation flow isn't broken
                    debriefs.append((player.character_state.name, "[remained silent]"))
                else:
                    # Add death marker for dead players
                    if is_dead:
                        print(f"💀 [{player.character_state.name}] (DYING) {debrief_text}\n")
                    else:
                        print(f"[{player.character_state.name}] {debrief_text}\n")

                    debriefs.append((player.character_state.name, debrief_text))

                # Log debrief to JSONL
                if mechanics and mechanics.jsonl_logger:
                    character_state_snapshot = {
                        'name': player.character_state.name,
                        'faction': player.character_state.faction,
                        'void_score': player.character_state.void_score,
                        'soulcredit': player.character_state.soulcredit,
                        'goals': player.character_state.goals,
                    }
                    mechanics.jsonl_logger.log_debrief(
                        character_name=player.character_state.name,
                        debrief_text=debrief_text,
                        character_state=character_state_snapshot
                    )

                await asyncio.sleep(1)

            except Exception as e:
                print(f"[{player.character_state.name}] [Debrief generation failed: {e}]\n")

        print(f"{'='*60}\n")

    def _display_round_status(self, initiative_order: List[tuple], mechanics, player_agents: List):
        """Display comprehensive round status with initiative, health, and position.

        Spec 12: Enhanced display with conditions, wounds/stuns, environmental objects,
        target ID mapping, range-band map, and clock progress bars.
        """
        print("\n=== Round Status ===")

        # Group combatants by type
        pcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'player']
        enemies = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'enemy']
        npcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'npc']

        # Display PCs
        if pcs:
            print("\n  Player Characters:")
            for init, agent in pcs:
                # Get health info from agent's combat attributes (initialized from Size x 2)
                current_health = getattr(agent, 'health', 0)
                max_health = getattr(agent, 'max_health', 0)
                health_str = f"{current_health}/{max_health} HP"

                # Get position
                position = getattr(agent, 'position', 'Unknown')
                position_str = str(position) if position != 'Unknown' else 'Unknown'

                # Get void score
                void_score = getattr(agent.character_state, 'void_score', 0)
                void_str = f"Void {void_score}/10"

                # Get faction
                faction = getattr(agent.character_state, 'faction', 'Unknown')

                # Wounds and stuns (Spec 12)
                wounds = getattr(agent, 'wounds', 0)
                stuns = getattr(agent, 'stuns', 0)
                wound_str = ""
                if wounds > 0:
                    wound_str += f" | {wounds} wound{'s' if wounds != 1 else ''}"
                if stuns > 0:
                    wound_str += f" | {stuns} stun{'s' if stuns != 1 else ''}"

                print(f"    [{init:2d}] {agent.character_state.name:20s} | {health_str:12s}{wound_str} | {position_str:15s} | {void_str}")
                print(f"         \u2514\u2500 Faction: {faction}")

                # Display equipped weapons (always show)
                if hasattr(agent, 'equipped_weapons'):
                    weapon_items = []
                    if agent.equipped_weapons.get('primary'):
                        wpn = agent.equipped_weapons['primary']
                        weapon_items.append(f"{wpn.name} [{wpn.damage_type.upper()}]")
                    if agent.equipped_weapons.get('sidearm'):
                        wpn = agent.equipped_weapons['sidearm']
                        weapon_items.append(f"{wpn.name} [{wpn.damage_type.upper()}]")

                    if weapon_items:
                        weapon_str = " | ".join(weapon_items)
                        print(f"         \u2514\u2500 Equipped: {weapon_str}")

                    # Show carried weapons if any
                    if hasattr(agent, 'weapon_inventory') and agent.weapon_inventory:
                        carried_items = [f"{w.name} [{w.damage_type.upper()}]" for w in agent.weapon_inventory[:2]]  # Show first 2
                        if carried_items:
                            carried_str = " | ".join(carried_items)
                            print(f"         \u2514\u2500 Carried: {carried_str}")

                # Display full inventory (all items)
                inventory_items = []
                if hasattr(agent.character_state, 'inventory') and agent.character_state.inventory:
                    inv = agent.character_state.inventory

                    # Ritual offerings
                    if inv.get('blood_offering', 0) > 0:
                        inventory_items.append(f"Blood:{inv['blood_offering']}")
                    if inv.get('incense', 0) > 0:
                        inventory_items.append(f"Incense:{inv['incense']}")
                    if inv.get('crystal_focus', 0) > 0:
                        inventory_items.append(f"Crystal:{inv['crystal_focus']}")

                    # Show any other items in inventory (besides the standard offerings)
                    for key, value in inv.items():
                        if key not in ['blood_offering', 'incense', 'crystal_focus'] and value:
                            # Format the key nicely (replace underscores with spaces, capitalize)
                            display_key = key.replace('_', ' ').title()
                            if isinstance(value, int) and value > 0:
                                inventory_items.append(f"{display_key}:{value}")
                            elif isinstance(value, str):
                                inventory_items.append(f"{display_key}:{value}")

                    # Show all inventory items
                    if inventory_items:
                        inv_str = " | ".join(inventory_items)
                        print(f"         \u2514\u2500 Inventory: {inv_str}")

                # Display energy purse (currency and seeds)
                if hasattr(agent.character_state, 'energy_purse') and agent.character_state.energy_purse:
                    energy_purse = agent.character_state.energy_purse

                    # Display all currencies (show non-zero values)
                    currency_parts = []
                    if energy_purse.drip > 0 or energy_purse.breath > 0 or energy_purse.grain > 0 or energy_purse.spark > 0:
                        if energy_purse.drip > 0:
                            currency_parts.append(f"Drip:{energy_purse.drip}")
                        if energy_purse.breath > 0:
                            currency_parts.append(f"Breath:{energy_purse.breath}")
                        if energy_purse.grain > 0:
                            currency_parts.append(f"Grain:{energy_purse.grain}")
                        if energy_purse.spark > 0:
                            currency_parts.append(f"Spark:{energy_purse.spark}")

                    if currency_parts:
                        currency_str = " | ".join(currency_parts)
                        print(f"         \u2514\u2500 Energy: {currency_str}")

                    # Display seeds (if any)
                    if energy_purse.seeds:
                        from .energy_economy import SeedType
                        seed_counts = {}
                        for seed in energy_purse.seeds:
                            # Raw seeds: show freshness (convert to currency before degrading to Hollows)
                            if seed.seed_type == SeedType.RAW:
                                if seed.cycles_remaining <= 5:
                                    seed_type_name = "Raw (Old)"
                                elif seed.cycles_remaining <= 9:
                                    seed_type_name = "Raw (Aged)"
                                else:
                                    seed_type_name = "Raw (Fresh)"
                            # Hollow seeds: illicit currency from fully degraded Raw seeds
                            elif seed.seed_type == SeedType.HOLLOW:
                                seed_type_name = "Hollows"
                            # Attuned seeds: (not used in current gameplay loop)
                            elif seed.seed_type == SeedType.ATTUNED:
                                if seed.element:
                                    seed_type_name = f"Attuned ({seed.element.value.title()})"
                                else:
                                    seed_type_name = "Attuned"
                            else:
                                seed_type_name = seed.seed_type.value

                            seed_counts[seed_type_name] = seed_counts.get(seed_type_name, 0) + 1

                        seed_parts = [f"{name}:{count}" for name, count in seed_counts.items()]
                        seed_str = " | ".join(seed_parts)
                        print(f"         \u2514\u2500 Seeds: {seed_str}")

                # Display Soulcredit
                if hasattr(agent.character_state, 'soulcredit'):
                    sc = agent.character_state.soulcredit
                    # Determine SC status
                    if sc >= 8:
                        sc_status = "Exemplary"
                    elif sc >= 5:
                        sc_status = "Good Standing"
                    elif sc >= 2:
                        sc_status = "Monitored"
                    elif sc >= 0:
                        sc_status = "Probation"
                    elif sc >= -2:
                        sc_status = "Restricted"
                    else:
                        sc_status = "Sanctioned"

                    print(f"         \u2514\u2500 Soulcredit: {sc:+d}/10 ({sc_status})")

                # Display conditions from mechanics engine (Spec 12)
                agent_id = getattr(agent, 'agent_id', None)
                pc_conditions = []
                if agent_id and mechanics and hasattr(mechanics, 'get_conditions'):
                    pc_conditions = mechanics.get_conditions(agent_id)
                if not pc_conditions:
                    # Fallback: check agent directly
                    pc_conditions = getattr(agent, 'conditions', [])
                if pc_conditions:
                    cond_strs = []
                    for cond in pc_conditions[:5]:
                        if hasattr(cond, 'name') and hasattr(cond, 'penalty'):
                            penalty_str = f"{cond.penalty:+d}" if cond.penalty != 0 else ""
                            duration_str = f" ({cond.duration}r)" if hasattr(cond, 'duration') and cond.duration > 0 else ""
                            cond_strs.append(f"{cond.name}{penalty_str}{duration_str}")
                        elif isinstance(cond, str):
                            cond_strs.append(cond)
                    if cond_strs:
                        print(f"         \u2514\u2500 Conditions: {', '.join(cond_strs)}")

        # Display Enemies (Spec 12: expanded detail display)
        if enemies:
            print("\n  Enemies:")
            for init, agent in enemies:
                # Get health info
                health = getattr(agent, 'health', '?')
                max_health = getattr(agent, 'max_health', '?')
                health_str = f"{health}/{max_health} HP"

                # Get position
                position = getattr(agent, 'position', 'Unknown')
                position_str = str(position) if position != 'Unknown' else 'Unknown'

                # Void score (enemies have void_score at enemy_agent.py:329)
                void_score = getattr(agent, 'void_score', 0)
                void_str = f"Void {void_score}/10" if void_score > 0 else ""

                # Wounds and stuns (Spec 12)
                wounds = getattr(agent, 'wounds', 0)
                stuns = getattr(agent, 'stuns', 0)
                damage_str = ""
                if wounds > 0 or stuns > 0:
                    parts = []
                    if wounds > 0:
                        parts.append(f"{wounds}w")
                    if stuns > 0:
                        parts.append(f"{stuns}s")
                    damage_str = f" ({', '.join(parts)})"

                # Main line
                void_suffix = f" | {void_str}" if void_str else ""
                print(f"    [{init:2d}] {agent.name:20s} | {health_str:12s}{damage_str} | {position_str:15s}{void_suffix}")

                # Faction
                faction = getattr(agent, 'faction', 'Unknown')
                if faction != "Unknown":
                    print(f"         +-- Faction: {faction}")

                # Weapons (enemies have weapons list at enemy_agent.py:335)
                weapons = getattr(agent, 'weapons', [])
                if weapons:
                    weapon_strs = []
                    for wpn in weapons[:3]:  # Show first 3 weapons
                        dmg_type = getattr(wpn, 'damage_type', 'wound').upper()
                        weapon_strs.append(f"{wpn.name} [{dmg_type}]")
                    print(f"         +-- Weapons: {' | '.join(weapon_strs)}")

                # Status effects (enemies have status_effects: List[str])
                status_effects = getattr(agent, 'status_effects', [])
                if status_effects:
                    effects_str = ", ".join(status_effects[:5])  # Show first 5
                    print(f"         +-- Status: {effects_str}")

                # Conditions (Condition objects, if the enemy has them)
                conditions = getattr(agent, 'conditions', [])
                if conditions:
                    cond_strs = []
                    for cond in conditions[:3]:
                        if hasattr(cond, 'name') and hasattr(cond, 'penalty'):
                            penalty_str = f"{cond.penalty:+d}" if cond.penalty != 0 else ""
                            duration_str = f" ({cond.duration}r)" if hasattr(cond, 'duration') and cond.duration > 0 else ""
                            cond_strs.append(f"{cond.name}{penalty_str}{duration_str}")
                    if cond_strs:
                        print(f"         +-- Conditions: {', '.join(cond_strs)}")

        # Display NPCs (non-combatants in initiative order)
        if npcs:
            print("\n  NPCs (Non-Combatants):")
            for init, npc in npcs:
                # Get health info
                health = getattr(npc, 'health', '?')
                max_health = getattr(npc, 'max_health', '?')
                health_str = f"{health}/{max_health} HP"

                # Get entity type and disposition
                entity_type = getattr(npc, 'entity_type', 'neutral')
                disposition = getattr(npc, 'disposition', 'neutral')

                # Format disposition with emoji (use module-level constant)
                disp_emoji = NPC_DISPOSITION_EMOJI.get(disposition, NPC_DISPOSITION_DEFAULT_EMOJI)
                status_str = f"{disp_emoji} {disposition}"

                # Active status
                is_active = getattr(npc, 'is_active', True)
                active_indicator = "" if is_active else " [INACTIVE]"

                # Wounds and stuns (Spec 12)
                wounds = getattr(npc, 'wounds', 0)
                stuns = getattr(npc, 'stuns', 0)
                damage_str = ""
                if wounds > 0 or stuns > 0:
                    parts = []
                    if wounds > 0:
                        parts.append(f"{wounds}w")
                    if stuns > 0:
                        parts.append(f"{stuns}s")
                    damage_str = f" ({', '.join(parts)})"

                # Use actual initiative value (Spec 12: fix [--] -> actual value)
                print(f"    [{init:2d}] {npc.name:20s} | {health_str:12s}{damage_str} | {status_str:15s}{active_indicator}")
                print(f"         \u2514\u2500 Faction: {npc.faction} | Threat: {npc.threat_level}")

                # Conditions (Spec 12)
                conditions = getattr(npc, 'conditions', [])
                if conditions:
                    cond_strs = []
                    for cond in conditions[:3]:
                        if hasattr(cond, 'name') and hasattr(cond, 'penalty'):
                            penalty_str = f"{cond.penalty:+d}" if cond.penalty != 0 else ""
                            duration_str = f" ({cond.duration}r)" if hasattr(cond, 'duration') and cond.duration > 0 else ""
                            cond_strs.append(f"{cond.name}{penalty_str}{duration_str}")
                    if cond_strs:
                        print(f"         \u2514\u2500 Conditions: {', '.join(cond_strs)}")

        # Display clock states with progress bars (Spec 12)
        if mechanics and mechanics.scene_clocks:
            print("\n  Scene Clocks:")
            for name, clock in mechanics.scene_clocks.items():
                status = f"{clock.current}/{clock.maximum}"
                filled_str = " [FILLED]" if clock.filled else ""
                progress_bar = _format_clock_progress_bar(clock.current, clock.maximum)
                print(f"    \u2022 {name}: {progress_bar} {status}{filled_str}")

        # Display environmental objects if present (Spec 12)
        if self.shared_state and self.shared_state.current_env_objects:
            print("\n  Environmental Objects:")
            for env_obj in self.shared_state.current_env_objects:
                # Object type label
                obj_type = getattr(env_obj, 'object_type', None)
                type_label = obj_type.value.upper() if obj_type and hasattr(obj_type, 'value') else "OBJECT"

                # Health (if destructible)
                health_str = ""
                if hasattr(env_obj, 'health') and env_obj.health is not None:
                    max_hp = getattr(env_obj, 'max_health', env_obj.health)
                    health_str = f" | {env_obj.health}/{max_hp} HP"
                    if hasattr(env_obj, 'is_destroyed') and env_obj.is_destroyed:
                        health_str += " [DESTROYED]"

                # Target ID or object ID
                id_str = ""
                if hasattr(env_obj, 'target_id') and env_obj.target_id:
                    id_str = f" [{env_obj.target_id}]"
                elif hasattr(env_obj, 'object_id') and env_obj.object_id:
                    id_str = f" [{env_obj.object_id}]"

                # State summary (key state flags)
                state_str = ""
                obj_state = getattr(env_obj, 'state', None)
                if obj_state:
                    state_parts = []
                    for key, value in obj_state.items():
                        if key in ('destroyed', 'functional'):
                            continue  # Skip meta-state, shown via [DESTROYED]
                        if isinstance(value, bool):
                            if value:
                                state_parts.append(key)
                        else:
                            state_parts.append(f"{key}={value}")
                    if state_parts:
                        state_str = f" ({', '.join(state_parts)})"

                print(f"    {type_label:10s}{id_str} {env_obj.name}{health_str}{state_str}")

        # Display target ID mapping table (Spec 12: when free targeting is active)
        if self.shared_state:
            target_id_mapper = self.shared_state.get_target_id_mapper()
            if target_id_mapper and target_id_mapper.enabled:
                all_ids = target_id_mapper.get_all_target_ids()
                if all_ids:
                    print("\n  Target ID Reference:")
                    for tid in sorted(all_ids):
                        info = target_id_mapper.get_combatant_info(tid)
                        if info:
                            type_label = info.get('type', 'unknown')
                            name = info.get('name', 'Unknown')
                            # Type tag for quick scanning
                            if type_label == 'player':
                                type_tag = "PC"
                            elif type_label == 'enemy':
                                type_tag = "ENEMY"
                            elif type_label == 'npc':
                                type_tag = "NPC"
                            elif type_label == 'vendor':
                                type_tag = "VENDOR"
                            elif type_label == 'env_object':
                                type_tag = "OBJECT"
                            else:
                                type_tag = type_label.upper()

                            print(f"    {tid} -> {name:25s} ({type_tag})")

        # Display range-band map (Spec 12)
        all_combatants = list(initiative_order)
        if all_combatants:
            # Group combatants by position
            position_groups = {}
            for init, agent_type, agent in all_combatants:
                pos = getattr(agent, 'position', None)
                if pos is None:
                    pos_str = "Unknown"
                else:
                    pos_str = str(pos)
                if pos_str not in position_groups:
                    position_groups[pos_str] = []
                # Get display name
                if agent_type == 'player' and hasattr(agent, 'character_state'):
                    display_name = agent.character_state.name
                else:
                    display_name = getattr(agent, 'name', 'Unknown')
                type_tag = {"player": "PC", "enemy": "E", "npc": "NPC"}.get(agent_type, "?")
                position_groups[pos_str].append(f"{display_name} [{type_tag}]")

            if position_groups:
                print("\n  Range-Band Map:")
                for pos_name, agents_at_pos in position_groups.items():
                    agents_str = ", ".join(agents_at_pos)
                    print(f"    {pos_name:15s} : {agents_str}")

        print()

    async def _run_post_resolution_adjudication(self, all_resolutions, mechanics) -> None:
        """EXPERIMENT: one stripped-context adjudication call per round;
        rulings logged as post_resolution_adjudication events, never
        applied. See post_adjudication.py for the hypothesis."""
        from .post_adjudication import (
            ENFORCE_REGIME_LABEL, apply_rulings, build_adjudication_roster,
            rulings_event_data)

        dm_agent = getattr(self, 'dm_agent', None)
        if dm_agent is None or mechanics is None:
            return
        mode = self.config.get('post_resolution_adjudication')
        summary = self._build_resolution_summary(all_resolutions)
        # Mode 'full_context' feeds the judge the story so far (scenario
        # stakes + recent syntheses) so mitigation is knowable; 'enforce'
        # also uses full context (it is the live judgment). Any other truthy
        # value = stripped statute-only call (the original observe-only cell).
        scene_context = ""
        if mode in ('full_context', 'enforce'):
            parts = []
            hint = self.config.get('scenario_hint')
            if hint:
                parts.append(f"Scenario: {hint}")
            for round_num, synthesis_text in (self._round_synthesis_history or [])[-3:]:
                parts.append(f"[round {round_num}] {synthesis_text}")
            scene_context = "\n".join(parts)
        rulings = await dm_agent.adjudicate_round_post_resolution(
            summary, mechanics.current_round, scene_context=scene_context)
        if rulings is None or not rulings.rulings:
            return

        if mode == 'enforce':
            # The magistrate is the sole ledger writer this round (narration
            # economy deltas were suppressed upstream). Apply and log applied.
            # Everyone present, not just the PCs: the Codex judges every soul in
            # the room. A players-only roster silently dropped every ruling
            # against an enemy or NPC — including the antagonists' own crimes.
            roster = build_adjudication_roster(
                self.shared_state.registered_players if self.shared_state else [],
                getattr(getattr(self, 'enemy_combat', None), 'enemy_agents', None),
                getattr(self.shared_state, 'npc_agents', None) if self.shared_state else None,
            )
            applied = apply_rulings(rulings, mechanics, roster,
                                    round_num=mechanics.current_round)
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_event(
                    event_type="post_resolution_adjudication",
                    data=rulings_event_data(
                        rulings, applied_to_state=True,
                        applied_records=applied, regime=ENFORCE_REGIME_LABEL),
                    round_num=mechanics.current_round,
                )
            # Report what actually landed. Printing rulings here read as though
            # every delta applied, while dropped ones had gone nowhere.
            landed = [r for r in applied if r.get('applied')]
            dropped = [r for r in applied if not r.get('applied')]
            logger.info(
                f"Post-resolution adjudication (ENFORCE): "
                f"{len(landed)} applied, {len(dropped)} dropped — "
                f"{[(r.get('character_name'), r.get('soulcredit_delta'), r.get('void_delta')) for r in landed]}")
            if dropped:
                logger.warning(
                    f"ENFORCE dropped {len(dropped)} ruling(s) with unmatched "
                    f"targets: {[r.get('character_name') for r in dropped]}")
            return

        if mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_event(
                event_type="post_resolution_adjudication",
                data=rulings_event_data(rulings),
                round_num=mechanics.current_round,
            )
        logger.info(f"Post-resolution adjudication (observe-only): "
                    f"{[(r.character_name, r.soulcredit_delta) for r in rulings.rulings]}")

    def _build_resolution_summary(self, all_resolutions: List[Dict]) -> str:
        """
        Build summary of resolutions for conversion check phase.

        Args:
            all_resolutions: List of resolution dicts from this round

        Returns:
            Human-readable summary string for DM conversion context
        """
        if not all_resolutions:
            return "No resolutions this round"

        if self.config.get('outcome_first_narration', False):
            from .outcome_pipeline import AppliedOutcome

            outcome_lines = []
            for resolution in all_resolutions:
                raw_outcome = resolution.get('applied_outcome')
                if not raw_outcome:
                    continue
                outcome = AppliedOutcome.model_validate(raw_outcome)
                facts = "; ".join(
                    fact.prose_safe_summary for fact in outcome.observable_facts
                ) or "No observable consequence"
                outcome_lines.append(
                    f"- [{outcome.outcome_id}] {outcome.actor_name}: "
                    f"{outcome.intent} -> {facts}"
                )
            if outcome_lines:
                return "\n".join(outcome_lines)

        # Get target_id_mapper for resolving target names
        target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None

        summary_lines = []
        for resolution in all_resolutions:
            agent_name = resolution.get('character_name', 'Unknown')

            # Extract action text from either PC dict format or enemy string format
            action_raw = resolution.get('action')
            if isinstance(action_raw, dict):
                # PC format: action is a dict with intent/description/target
                action = action_raw.get('intent') or action_raw.get('description', 'Unknown action')
                target_id = action_raw.get('target')
            else:
                # Enemy format: action is a string like 'attack'
                action = resolution.get('action_description') or str(action_raw or 'Unknown action')
                target_id = resolution.get('target')

            # Truncate long actions
            if len(action) > 100:
                action = action[:97] + "..."

            # Extract success/margin — handle nested resolution dict (PC) vs flat (enemy)
            outcome = resolution.get('resolution', {})
            if isinstance(outcome, dict) and 'resolution' in outcome:
                # PC format: resolution.resolution.success/margin
                inner = outcome['resolution']
                success = inner.get('success', outcome.get('success', False))
                margin = inner.get('margin', outcome.get('margin', 0))
                tier = inner.get('success_tier', outcome.get('outcome_tier', 'UNKNOWN'))
            elif isinstance(outcome, dict) and ('success' in outcome or 'margin' in outcome):
                # Outcome dict with flat success/margin keys
                success = outcome.get('success', False)
                margin = outcome.get('margin', 0)
                tier = outcome.get('outcome_tier', outcome.get('success_tier', 'UNKNOWN'))
            else:
                # Enemy format with flat keys at top level, or no resolution dict
                success = resolution.get('success', resolution.get('result') not in ['invalidated', 'failed', 'target not found'])
                margin = resolution.get('margin', 0)
                tier = resolution.get('outcome_tier', 'UNKNOWN')

            # Resolve target name
            target_text = ""
            if target_id and target_id_mapper:
                entity = target_id_mapper.resolve_target(target_id)
                if entity:
                    name = getattr(entity, 'name', None)
                    if not name and hasattr(entity, 'character_state'):
                        name = getattr(entity.character_state, 'name', None)
                    if name:
                        target_text = f" → targeting {name}"

            # Build status with margin/tier for context
            if success:
                status = f'SUCCESS (margin: {margin:+d}, tier: {tier})'
            else:
                status = f'FAIL (margin: {margin:+d})'

            # Get DM narration (the full paragraph!)
            narration = resolution.get('narration', '')
            # Truncate to first 300 chars to keep summary readable but preserve key details
            if len(narration) > 300:
                narration = narration[:297] + "..."

            # Add damage dealt if any
            damage_text = ""
            effects = resolution.get('effects')
            # Damage is now List[DamageEffect] - sum all dealt damage for display
            if effects and hasattr(effects, 'damage') and effects.damage:
                total_damage = sum(dmg.dealt for dmg in effects.damage)
                damage_text = f" | Damage: {total_damage}"
            elif isinstance(effects, dict):
                # Handle dict-based effects (enemy combat format)
                # Must check that damage is not None before calling .get() on it
                damage = effects.get('damage')
                if damage and isinstance(damage, dict):
                    dealt = damage.get('dealt')
                    if dealt:
                        damage_text = f" | Damage: {dealt}"

            # Add clock changes if any
            clock_text = ""
            if effects:
                clock_changes = []
                if hasattr(effects, 'clock_changes') and effects.clock_changes:
                    for clock in effects.clock_changes:
                        change = getattr(clock, 'tick_change', 0)
                        name = getattr(clock, 'clock_name', 'Unknown')
                        clock_changes.append(f"{name} {change:+d}")
                elif isinstance(effects, dict) and effects.get('clock_changes'):
                    for clock in effects['clock_changes']:
                        change = clock.get('tick_change', 0)
                        name = clock.get('clock_name', 'Unknown')
                        clock_changes.append(f"{name} {change:+d}")

                if clock_changes:
                    clock_text = f" | Clocks: {', '.join(clock_changes)}"

            # Add conditions applied if any
            condition_text = ""
            if effects:
                conditions = []
                if hasattr(effects, 'conditions') and effects.conditions:
                    for cond in effects.conditions:
                        cond_name = getattr(cond, 'name', 'Unknown')
                        conditions.append(cond_name)
                elif isinstance(effects, dict) and effects.get('conditions'):
                    for cond in effects['conditions']:
                        cond_name = cond.get('name', 'Unknown')
                        conditions.append(cond_name)

                if conditions:
                    condition_text = f" | Conditions: {', '.join(conditions)}"

            # Build full summary line with narration
            summary_line = f"- {agent_name}: {action}{target_text} ({status}){damage_text}{clock_text}{condition_text}"

            # Add DM narration on next line (indented for readability)
            if narration:
                summary_line += f"\n  DM: {narration}"

            summary_lines.append(summary_line)

        return "\n".join(summary_lines)

    def _extract_social_target_ids(self, all_resolutions: List[Dict]) -> set:
        """
        Extract enemy agent_ids that were targeted by successful non-damage PC actions.

        Uses mechanical signals (target + success + no damage), NOT keyword detection.

        Args:
            all_resolutions: List of resolution dicts from this round

        Returns:
            Set of enemy agent_ids that were socially targeted
        """
        social_targets = set()

        if not self.shared_state:
            return social_targets

        target_id_mapper = self.shared_state.get_target_id_mapper()
        if not target_id_mapper:
            return social_targets

        # Build set of active enemy agent_ids for quick lookup
        enemy_agent_ids = set()
        enemy_combat = self.shared_state.enemy_combat
        if enemy_combat and hasattr(enemy_combat, 'enemy_agents'):
            for enemy in enemy_combat.enemy_agents:
                if enemy.is_active:
                    enemy_agent_ids.add(enemy.agent_id)

        for resolution in all_resolutions:
            action = resolution.get('action')
            if not isinstance(action, dict):
                continue  # Enemy format — skip

            target_id = action.get('target')
            if not target_id:
                continue

            # Check success from nested resolution
            outcome = resolution.get('resolution', {})
            if isinstance(outcome, dict) and 'resolution' in outcome:
                inner = outcome['resolution']
                success = inner.get('success', False)
            elif isinstance(outcome, dict):
                success = outcome.get('success', False)
            else:
                continue

            if not success:
                continue

            # Check no damage dealt
            effects = resolution.get('effects')
            has_damage = False
            if effects:
                if hasattr(effects, 'damage') and effects.damage:
                    total = sum(getattr(d, 'dealt', 0) for d in effects.damage)
                    has_damage = total > 0
                elif isinstance(effects, dict):
                    damage = effects.get('damage')
                    if damage and isinstance(damage, dict):
                        has_damage = (damage.get('dealt', 0) or 0) > 0

            if has_damage:
                continue

            # Resolve target to agent and check if it's an enemy
            entity = target_id_mapper.resolve_target(target_id)
            if entity:
                agent_id = getattr(entity, 'agent_id', None)
                if agent_id and agent_id in enemy_agent_ids:
                    social_targets.add(agent_id)

        return social_targets

    def _resolve_target_ids_in_text(self, text: str) -> str:
        """
        Replace target IDs (tgt_xxxx) in text with character names for readability.

        Args:
            text: Narration or description text potentially containing target IDs

        Returns:
            Text with target IDs replaced by character names (or original if no mapper)
        """
        if not text or not self.shared_state or not self.shared_state.target_id_mapper:
            return text

        import re

        # Pattern to match target IDs like tgt_7a3f
        pattern = r'\btgt_[a-z0-9]{4}\b'

        def replace_target_id(match):
            target_id = match.group(0)
            combatant_info = self.shared_state.target_id_mapper.get_combatant_info(target_id)
            if combatant_info:
                # Replace with "CharacterName (tgt_xxxx)" for clarity
                return f"{combatant_info['name']} ({target_id})"
            return target_id  # Keep original if not found

        return re.sub(pattern, replace_target_id, text)

    def _spawn_new_clocks(self, new_clocks: List[Dict[str, any]]):
        """Spawn new clocks from DM markers (legacy)."""
        if not self.shared_state or not self.shared_state.mechanics_engine:
            return

        mechanics = self.shared_state.mechanics_engine

        for clock_data in new_clocks:
            name = clock_data['name']
            max_ticks = clock_data['max']
            description = clock_data['description']

            # Create the new clock
            clock = mechanics.create_scene_clock(name, max_ticks, description)
            if clock is None:
                continue  # rejected by clock conservation (logged)
            print(f"\n🕐 NEW CLOCK SPAWNED: {name} (0/{max_ticks}) - {description}")

            # Track clock creation in history
            mechanics.clock_history.append({
                'round': mechanics.current_round,
                'event_type': 'created',
                'clock_name': name,
                'description': description,
                'current': 0,  # New clocks start at 0
                'max': max_ticks,
                'consequence': clock.filled_consequence if clock else ''
            })

            # clock_spawn is emitted by create_scene_clock itself, so every
            # creation path announces exactly once.

    def _spawn_new_clocks_structured(self, new_clocks: List['NewClock']):
        """Spawn new clocks from structured output (Phase 5: Pydantic AI migration)."""
        from .schemas.story_events import NewClock

        if not self.shared_state or not self.shared_state.mechanics_engine:
            return

        mechanics = self.shared_state.mechanics_engine

        for clock in new_clocks:
            # Create the new clock with semantic meaning
            scene_clock = mechanics.create_scene_clock(
                clock.name,
                clock.max_ticks,
                clock.description,
                advance_meaning=clock.advance_meaning,
                regress_meaning=clock.regress_meaning,
                filled_consequence=clock.filled_consequence,
                is_terminal=getattr(clock, 'is_terminal_clock', False),
                terminal_outcome=getattr(clock, 'terminal_outcome', 'victory')
            )
            if scene_clock is None:
                continue  # rejected by clock conservation (logged)

            # Set initial ticks if specified
            if clock.current_ticks > 0:
                scene_clock.current = clock.current_ticks

            print(f"\n🕐 NEW CLOCK SPAWNED: {clock.name} ({scene_clock.current}/{clock.max_ticks}) - {clock.description}")

            # Track clock creation in history
            mechanics.clock_history.append({
                'round': mechanics.current_round,
                'event_type': 'created',
                'clock_name': clock.name,
                'description': clock.description,
                'current': scene_clock.current,  # Use actual value (may be non-zero)
                'max': clock.max_ticks,
                'consequence': scene_clock.filled_consequence if scene_clock else ''
            })

            # clock_spawn is emitted by create_scene_clock itself, so every
            # creation path announces exactly once.

    async def _check_and_trigger_story_advancement(self):
        """Check if all clocks are complete and trigger DM to advance the story."""
        if not self.shared_state:
            return

        mechanics = self.shared_state.get_mechanics_engine()
        if not mechanics:
            return

        # Track if we currently have clocks
        if mechanics.scene_clocks and len(mechanics.scene_clocks) > 0:
            self._had_active_clocks = True

        # Count active (non-filled) clocks
        active_clocks = [clock for clock in mechanics.scene_clocks.values() if not clock.filled] if mechanics.scene_clocks else []

        # Trigger story advancement if:
        # 1. We previously had clocks AND
        # 2. Now all clocks are gone (expired/filled/archived) OR all remaining clocks are filled
        should_advance = self._had_active_clocks and len(active_clocks) == 0

        if should_advance:
            logger.info("All clocks complete/expired - triggering story advancement")
            print("\n⏰ All scenario objectives complete - Story will advance to new location/situation")

            # Set flag on DM agent to trigger story advancement
            dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
            if dm_agents:
                dm_agent = dm_agents[0]
                dm_agent.needs_story_advancement = True
                logger.info(f"Set needs_story_advancement=True on DM {dm_agent.agent_id}")

            # Reset flag so we don't trigger again until new clocks appear
            self._had_active_clocks = False

    def _build_end_state_snapshot(self, mechanics, terminal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Capture the scene's resolving state when the session ends.

        This is the hand-off point for the resolve-then-leap continuation: it records
        how the chapter ended (outcome, the beat that resolved it, who is still standing,
        environmental void, remaining clocks) so a future session can continue with
        continuity after a time jump.

        Works for BOTH ending paths: a terminal clock filling (``terminal`` given) or
        the DM declaring session_end directly (``terminal`` None -- a live run showed
        the DM declaring DRAW with the terminal clock one tick short of filling, which
        otherwise produced no snapshot at all).
        """
        party = []
        for agent in self.agents:
            if getattr(agent, 'character_state', None) is None:
                continue
            party.append(party_snapshot_entry(agent))

        if terminal:
            outcome = terminal['outcome']
            resolved_by_clock = terminal['clock_name']
            resolution = terminal.get('filled_consequence') or terminal.get('reason', '')
            round_num = terminal.get('round', mechanics.current_round)
        else:
            # DM-declared ending: synthesize from the declared status + last narration,
            # attributing it to a terminal clock if one was in play (often near-filled).
            outcome = self._session_end_status
            term_clock = next(
                (c for c in mechanics.scene_clocks.values() if getattr(c, 'is_terminal', False)),
                None,
            )
            resolved_by_clock = term_clock.name if term_clock else None
            resolution = self._synthesize_ending_resolution()
            round_num = mechanics.current_round

        return {
            'outcome': outcome,
            'ended_by': self._end_reason or ('terminal_clock' if terminal else 'dm_declaration'),
            'resolved_by_clock': resolved_by_clock,
            'resolution': resolution,
            'round': round_num,
            'scene_void_level': getattr(mechanics, 'scene_void_level', None),
            'party': party,
            'state_summary': mechanics.get_state_summary(),
        }

    @staticmethod
    def _is_stub_narration(text: str) -> bool:
        """True for the DM's game-state fallback narration (dm.py:7325,
        'The situation evolves... (Clock X/Y | ...)') -- bookkeeping that must
        never be handed to the renderer as the scene's resolution."""
        import re
        low = (text or "").lower()
        if "situation evolves" in low:
            return True
        if re.search(r"\b\d+\s*/\s*\d+\b", text or ""):
            return True
        return False

    def _synthesize_ending_resolution(self) -> str:
        """Clean in-world resolution text for the non-terminal ending paths (TPK,
        round-cap, DM declaration).

        Terminal-clock endings render the clock's authored filled_consequence; the
        other paths previously echoed self._last_dm_narration, which for cap endings
        is the clock-stub ('The situation evolves... (clocks X/Y)'). That leaked the
        bookkeeping straight into the rendered story (and a TPK had no resolution at
        all). Give each path clean, observable in-world text instead.
        """
        reason = self._end_reason
        outcome = self._session_end_status
        if reason == "tpk":
            return "The party was overcome at the scene -- none remained standing."
        if reason == "round_cap":
            if outcome == "victory":
                return ("The scene reached its limit with the threat held off: the "
                        "catastrophe never came, though nothing was fully settled.")
            return ("Time ran out before the matter could resolve. The scene ends "
                    "unsettled, its danger still present and its central question still open.")
        # DM declaration: keep the DM's own narration unless it's a bookkeeping stub.
        narr = (self._last_dm_narration or "").strip()
        if narr and not self._is_stub_narration(narr):
            return narr[:400]
        return {
            "victory": "The scene resolves in the party's favor.",
            "defeat": "The scene resolves against the party.",
        }.get(outcome, "The scene comes to an unsettled close.")

    def _resolve_at_round_cap(self):
        """
        Resolve any still-open scene when the round cap is reached, by clock polarity.

        Convergence backstop -- the honest, non-coercive alternative to forcing clocks
        to complete or to be monotonic (clocks stay fully regressable):
          * an un-filled DOOM clock (terminal_outcome=defeat) => the catastrophe was
            held off for the whole scene => victory by aversion
          * an un-filled GOAL clock (victory/draw) => the resolution wasn't reached in
            time => draw (unresolved); we do NOT fabricate a win
          * no terminal clock at all => draw

        Sets _session_end_status + _end_reason so _check_end_conditions emits the
        end_state_snapshot (the continuation hook) for cap endings too.
        """
        if self._session_end_status:
            return  # already resolved by a terminal clock / DM declaration this round
        mechanics = self.shared_state.mechanics_engine if self.shared_state else None
        if not mechanics:
            self._session_end_status = 'draw'
            self._end_reason = 'round_cap'
            return

        terminals = [c for c in mechanics.scene_clocks.values() if getattr(c, 'is_terminal', False)]
        doom_unfilled = [
            c for c in terminals
            if getattr(c, 'terminal_outcome', '') == 'defeat' and not c.filled
        ]
        if doom_unfilled:
            self._session_end_status = 'victory'  # catastrophe averted -- they held the line
            print(f"\n🛡️  Round cap reached with doom clock(s) held off → victory by aversion")
        else:
            self._session_end_status = 'draw'  # ran out of time to resolve
        self._end_reason = 'round_cap'

    async def _check_end_conditions(self) -> bool:
        """Check if session should end."""
        # Emit the end-state snapshot (the resolve-then-leap hook) on ANY meaningful
        # ending -- a terminal clock filling OR the DM declaring session_end directly.
        # (A live run showed the DM declaring DRAW with the terminal clock at 7/8, one
        # tick short: terminal-only gating produced no snapshot at all, so continuation
        # couldn't fire.) A terminal clock filling also adopts its outcome if the DM
        # hasn't declared one.
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            terminal = getattr(mechanics, 'terminal_completion', None)
            if terminal and not self._session_end_status:
                self._session_end_status = terminal['outcome']
            if (terminal or self._session_end_status) and not self._end_state_snapshot:
                if not self._end_reason:
                    self._end_reason = 'terminal_clock' if terminal else 'dm_declaration'
                self._end_state_snapshot = self._build_end_state_snapshot(mechanics, terminal)
                how = (
                    f"TERMINAL CLOCK '{terminal['clock_name']}' RESOLVED THE SCENE"
                    if terminal else "DM DECLARED SESSION END"
                )
                print(f"\n🏁 {how} → ending session ({self._session_end_status})")
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        event_type="end_state_snapshot",
                        data=self._end_state_snapshot,
                        round_num=mechanics.current_round
                    )

        # Check if DM declared session end
        if self._session_end_status:
            print(f"\n🎬 DM DECLARED SESSION {self._session_end_status.upper()}")

            # Log session end
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                if mechanics.jsonl_logger and self._claim_session_finalization():
                    # Log any remaining clocks before session ends
                    if mechanics.scene_clocks:
                        for clock_name, clock in mechanics.scene_clocks.items():
                            mechanics.jsonl_logger.log_event(
                                event_type="clock_removal",
                                data={
                                    "clock_name": clock_name,
                                    "current_ticks": clock.current,
                                    "maximum_ticks": clock.maximum,
                                    "description": clock.description,
                                    "removal_reason": "session_end",
                                    "expiration_type": None,
                                    "filled": clock.filled,
                                    "consequence_triggered": False
                                },
                                round_num=mechanics.current_round
                            )

                    # Get current state for logging
                    final_state = mechanics.get_state_summary()
                    final_state['session_end_status'] = self._session_end_status
                    final_state['dm_final_narration'] = self._last_dm_narration
                    mechanics.jsonl_logger.log_session_end(final_state)

            return True

        # Otherwise session continues
        return False
        
    def _check_log_fidelity(self, mechanics, player_agents) -> None:
        """Diff this round's character_state rows against live engine state.

        Warn-only. Five of the nine defects in the 2026-08-09 audit were the log
        and the state disagreeing with nothing watching — an entity kind nobody
        logged, a hardcoded `soulcredit=0`, a snapshot contradicting its own
        oracle. Each would have announced itself here, in the run that produced
        it, for free.

        Wrapped end to end: this is telemetry, and telemetry must never gate play.
        """
        try:
            from .log_fidelity import compare_rows, live_state

            logged = mechanics.character_rows_for_round(mechanics.current_round)
            if not logged:
                return

            enemies = (getattr(self.enemy_combat, 'enemy_agents', None) or []
                       if getattr(self, 'enemy_combat', None) else [])
            npcs = getattr(self.shared_state, 'npc_agents', None) or []

            expected = live_state(players=player_agents, enemies=enemies,
                                  npcs=npcs, mechanics=mechanics)
            names = {}
            for entity in list(player_agents) + list(enemies) + list(npcs):
                agent_id = getattr(entity, 'agent_id', None)
                if not agent_id:
                    continue
                cs = getattr(entity, 'character_state', None)
                names[agent_id] = getattr(cs, 'name', None) or getattr(entity, 'name', agent_id)

            divergences = compare_rows(expected, logged, names)
            if not divergences:
                return

            for d in divergences:
                logger.warning(f"LOG FIDELITY: {d}")
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_event(
                    event_type="log_fidelity_divergence",
                    data={"round": mechanics.current_round,
                          "count": len(divergences),
                          "divergences": [d.as_dict() for d in divergences]},
                    round_num=mechanics.current_round,
                )
        except Exception as e:  # pragma: no cover - never break a session
            logger.debug(f"Log-fidelity check unavailable: {e}")

    def _heartbeat(self, round_count: int) -> None:
        """Stamp the liveness sidecar at a round boundary.

        Without this, a hung run and a slow one are indistinguishable from
        outside — both just stop producing output. Best-effort by design.
        """
        output_dir = getattr(self, '_status_output_dir', None)
        if not output_dir or not getattr(self, 'session_id', None):
            return
        try:
            from .session_status import RUNNING, write_status
            write_status(output_dir, self.session_id, RUNNING, round=round_count)
        except Exception as e:  # pragma: no cover
            logger.debug(f"Status heartbeat failed: {e}")

    def mark_session_status(self, state: str, error: Optional[str] = None) -> None:
        """Record a terminal state in the liveness sidecar.

        Called from every exit path so 'finished' and 'died' are distinguishable
        without inspecting the JSONL or the process table.
        """
        output_dir = getattr(self, '_status_output_dir', None)
        if not output_dir or not getattr(self, 'session_id', None):
            return
        try:
            from .session_status import write_status
            write_status(output_dir, self.session_id, state, error=error)
        except Exception as e:  # pragma: no cover
            logger.debug(f"Status finalize failed: {e}")

    def _claim_session_finalization(self) -> bool:
        """Claim the right to write session teardown. True for exactly one caller.

        Two paths tear a session down — `_check_session_end()` when the DM
        declares an ending, and `_end_session()` always. Both swept the scene
        clocks emitting `clock_removal` and both called `log_session_end()`, so a
        five-clock session logged ten removals and two `session_end` events.
        Whichever path gets here first does the writing; the other stands down.
        """
        if getattr(self, '_session_finalized', False):
            logger.debug("Session teardown already logged — skipping duplicate")
            return False
        self._session_finalized = True
        return True

    async def _end_session(self):
        """End the session and save data."""
        print(f"\n=== Session {self.session_id} Ending ===")

        # Print final state summary
        if self.shared_state.mechanics_engine:
            print("\n--- Final State Summary ---")
            state_summary = self.shared_state.mechanics_engine.get_state_summary()

            # Print scene clocks
            if state_summary.get('scene_clocks'):
                print("\nScene Clocks:")
                for name, clock in state_summary['scene_clocks'].items():
                    print(f"  {name}: {clock['progress']} {'[FILLED]' if clock['filled'] else ''}")

            # Print character final states
            if state_summary.get('void_states'):
                print("\nCharacter Final States:")
                for agent_id, void_info in state_summary['void_states'].items():
                    # Find the character details from player agents
                    char_details = None
                    for player in [a for a in self.agents if hasattr(a, 'character_state')]:
                        if player.agent_id == agent_id:
                            char_details = player.character_state
                            break

                    if char_details:
                        # Get key equipment/skills
                        top_skills = sorted(char_details.skills.items(), key=lambda x: x[1], reverse=True)[:3]
                        skills_str = ", ".join([f"{skill} {val}" for skill, val in top_skills])

                        print(f"  {char_details.name} ({char_details.faction}):")
                        print(f"    Void: {void_info['score']}/10 ({void_info['level']})")
                        print(f"    Soulcredit: {char_details.soulcredit}")
                        print(f"    Top Skills: {skills_str}")
                    else:
                        print(f"  {agent_id}: {void_info['score']}/10 ({void_info['level']})")

            # Print clock timeline
            mechanics = self.shared_state.mechanics_engine
            if mechanics and mechanics.clock_history:
                print("\n--- Clock Timeline ---")
                for event in mechanics.clock_history:
                    round_num = event.get('round', '?')
                    event_type = event.get('event_type', 'unknown')
                    clock_name = event.get('clock_name', 'Unknown')
                    description = event.get('description', '')

                    if event_type == 'created':
                        current_val = event.get('current', 0)
                        max_val = event.get('max', '?')
                        consequence = event.get('consequence', '')
                        print(f"  Round {round_num}: 🕐 CREATED - {clock_name} ({current_val}/{max_val})")
                        print(f"             {description}")
                        if consequence:
                            print(f"             When filled: {consequence}")
                    elif event_type == 'filled':
                        final_val = event.get('final_value', '?')
                        consequence = event.get('consequence', '')
                        print(f"  Round {round_num}: ✅ FILLED - {clock_name} ({final_val})")
                        if consequence:
                            print(f"             Triggered: {consequence}")
                    elif event_type == 'expired':
                        final_val = event.get('final_value', '?')
                        exp_type = event.get('expiration_type', 'unknown')
                        print(f"  Round {round_num}: ⏰ EXPIRED - {clock_name} ({final_val}) - {exp_type}")
                        print(f"             {description}")
                    elif event_type == 'removed':
                        current_val = event.get('current', 0)
                        max_val = event.get('max', '?')
                        reason = event.get('removal_reason', 'unknown')
                        print(f"  Round {round_num}: 🗑️  REMOVED - {clock_name} ({current_val}/{max_val}) - {reason}")
                print()

            print("=" * 40)

            # Log session end event
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger and self._claim_session_finalization():
                # Log any remaining clocks before session ends (timeout path)
                if mechanics.scene_clocks:
                    for clock_name, clock in mechanics.scene_clocks.items():
                        mechanics.jsonl_logger.log_event(
                            event_type="clock_removal",
                            data={
                                "clock_name": clock_name,
                                "current_ticks": clock.current,
                                "maximum_ticks": clock.maximum,
                                "description": clock.description,
                                "removal_reason": "session_end",
                                "expiration_type": None,
                                "filled": clock.filled,
                                "consequence_triggered": False
                            },
                            round_num=mechanics.current_round
                        )
                        mechanics.clock_history.append({
                            'event_type': 'removed',
                            'clock_name': clock_name,
                            'round': mechanics.current_round,
                            'current': clock.current,
                            'max': clock.maximum,
                            'description': clock.description,
                            'removal_reason': 'session_end'
                        })

                mechanics.jsonl_logger.log_session_end(state_summary)

            # Always report where the log landed, even when the DM-declared-end
            # path already claimed teardown above.
            if mechanics.jsonl_logger:
                print(f"\n✓ JSONL log saved: {mechanics.jsonl_logger.log_file}")

        # Collect voice profiles for ONLY the players in this session (not entire pool)
        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
        active_voice_profiles = []
        active_player_configs = []
        for player in player_agents:
            if hasattr(player, 'voice_profile') and player.voice_profile:
                active_voice_profiles.append(player.voice_profile.as_dict())
            # Collect character config for this player
            active_player_configs.append({
                'name': player.character_state.name,
                'faction': player.character_state.faction,
                'attributes': player.character_state.attributes,
                'skills': player.character_state.skills,
                'void_score': player.character_state.void_score,
                'soulcredit': player.character_state.soulcredit,
                'goals': player.character_state.goals,
                'bonds': [bond.model_dump() for bond in player.character_state.bonds],  # Serialize Bond objects
            })

        # Filter config to only include active players
        session_config = dict(self.config)
        if 'agents' in session_config and 'players' in session_config['agents']:
            session_config['agents']['players'] = active_player_configs

        # Load JSONL events if available
        jsonl_events = []
        if mechanics and mechanics.jsonl_logger:
            try:
                import json
                with open(mechanics.jsonl_logger.log_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            jsonl_events.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Failed to load JSONL events: {e}")

        # Restructure events into rounds and turns
        structured_rounds = self._restructure_events_into_rounds(jsonl_events)

        # Collect final session data
        final_data = {
            'session_id': self.session_id,
            'config': session_config,  # Filtered config with only active players
            'rounds': structured_rounds,  # NEW: Properly nested rounds/turns/resolutions
            'raw_events': jsonl_events,  # Keep raw events for debugging
            'end_time': datetime.now().isoformat(),
            'shared_state': self.shared_state.snapshot(),
            'voice_profiles': active_voice_profiles,  # Only active players
        }

        # Save session data
        await self._save_session_data(final_data)
        
        # Shutdown all agents
        await self._shutdown_agents()
        
        self.running = False
        
    def _restructure_events_into_rounds(self, events: List[Dict]) -> List[Dict]:
        """
        Restructure flat event list into nested rounds -> turns -> resolutions.

        Expected structure:
        [
            {
                "round_number": 1,
                "scenario": {...},  // Only in round 1
                "turns": [
                    {
                        "agent": "player_01",
                        "character": "Gestator Lyss",
                        "action": {...},
                        "resolution": {...},
                        "narration": "...",
                        "clocks_after": {...}
                    }
                ]
            }
        ]
        """
        if not events:
            return []

        rounds = []
        current_round = None
        pending_actions = {}  # Map agent_id -> action dict
        scenario_info = None  # Store scenario from session start

        for event in events:
            event_type = event.get('event_type')

            # Capture scenario information
            if event_type == 'scenario':
                scenario_info = event.get('scenario')

            # Start new round
            elif event_type == 'round_start':
                if current_round and (current_round.get('declarations') or current_round.get('resolutions')):
                    # Save previous round if it has content
                    rounds.append(current_round)

                current_round = {
                    'round_number': event.get('round'),
                    'timestamp': event.get('ts'),
                    'declarations': [],
                    'resolutions': [],
                    'synthesis': None
                }

                # Add scenario to round 1
                if event.get('round') == 1 and scenario_info:
                    current_round['scenario'] = scenario_info

            # Declaration phase start
            elif event_type == 'declaration_phase_start':
                # Just marks the phase, no action needed
                pass

            # Individual action declaration
            elif event_type == 'action_declaration':
                if current_round:
                    current_round['declarations'].append({
                        'player_id': event.get('player_id'),
                        'character_name': event.get('character_name'),
                        'initiative': event.get('initiative'),
                        'action': event.get('action'),
                        'timestamp': event.get('ts')
                    })

            # Adjudication phase start
            elif event_type == 'adjudication_start':
                # Just marks the phase, no action needed
                pass

            # Action resolution (individual)
            elif event_type == 'action_resolution':
                if current_round:
                    current_round['resolutions'].append({
                        'agent': event.get('agent'),
                        'action': event.get('action'),
                        'context': event.get('context', {}),
                        'roll': event.get('roll', {}),
                        'economy': event.get('economy', {}),
                        'clocks': event.get('clocks', {}),
                        'effects': event.get('effects', []),
                        'timestamp': event.get('ts')
                    })

            # Round synthesis
            elif event_type == 'round_synthesis':
                if current_round:
                    current_round['synthesis'] = event.get('synthesis')
                    current_round['synthesis_timestamp'] = event.get('ts')

            # Mission debrief
            elif event_type == 'mission_debrief':
                if current_round:
                    if 'debriefs' not in current_round:
                        current_round['debriefs'] = []
                    current_round['debriefs'].append({
                        'character': event.get('character'),
                        'debrief': event.get('debrief'),
                        'final_state': event.get('final_state'),
                        'timestamp': event.get('ts')
                    })

        # Add final round
        if current_round and (current_round.get('declarations') or current_round.get('resolutions')):
            rounds.append(current_round)

        return rounds

    async def _save_session_data(self, data: Dict[str, Any]):
        """Print session summary (JSONL log is the primary output)."""
        output_dir = Path(self.config.get('output_dir', './output'))

        # Print session summary for easy copy-paste
        print(f"\n{'='*60}")
        print(f"Session ID: {self.session_id}")

        # JSONL log path (primary output)
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
            print(f"JSONL log:  {mechanics.jsonl_logger.log_file}")
        else:
            jsonl_path = output_dir / f"session_{self.session_id}.jsonl"
            print(f"JSONL log:  {jsonl_path}")

        # Agent logs path (if enabled)
        if self.log_agents_separately:
            print(f"Agent logs: agent_logs/{self.session_id}/")

        print(f"{'='*60}\n")
        
    async def _shutdown_agents(self):
        """Shutdown all agents."""
        # Send shutdown messages
        shutdown_message = Message(
            id="shutdown_all",
            type=MessageType.SHUTDOWN,
            sender='coordinator',
            recipient=None,  # broadcast
            payload={},
            timestamp=datetime.now()
        )
        
        await self.coordinator.message_bus._route_message(shutdown_message)
        
        # Wait for graceful shutdown
        await asyncio.sleep(1)
        
        # Force shutdown agents
        for agent in self.agents:
            agent.shutdown()
            
        # Shutdown coordinator
        self.coordinator.shutdown()
        
        # Shutdown human interface
        if self.human_interface:
            self.human_interface.shutdown()

        logger.debug("All agents shutdown")

    def _recent_history(self) -> List[str]:
        """Return a small slice of recent turn history for prompt context."""
        return self._turn_history[-5:]

    def _handle_scenario_setup(self, message: Message):
        """Track when scenario is ready and process initial enemy spawns."""
        if message.type != MessageType.SCENARIO_SETUP:
            return

        # Display scenario once (instead of each player printing it)
        scenario = message.payload.get('scenario', {})
        opening_narration = message.payload.get('opening_narration', '')

        print(f"\n=== New Scenario ===")
        print(f"Theme: {scenario.get('theme', 'Unknown')}")
        print(f"Location: {scenario.get('location', 'Unknown')}")
        print(f"\nDM: {opening_narration}")

        # Track initial scenario clocks in history
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.scene_clocks:
                for clock_name, clock in mechanics.scene_clocks.items():
                    mechanics.clock_history.append({
                        'round': 1,  # Initial scenario is round 1
                        'event_type': 'created',
                        'clock_name': clock_name,
                        'description': clock.description,
                        'current': clock.current,  # Track starting value (may be non-zero)
                        'max': clock.maximum,
                        'consequence': clock.filled_consequence
                    })

        # Process initial_enemies from ScenarioSetup structured output
        # Handle both SimpleNamespace (object) and dict (after serialization)
        scenario_setup = message.payload.get('scenario_setup', None)
        if scenario_setup:
            logger.debug(f"scenario_setup found: {type(scenario_setup)}")
            # Get initial_enemies (works for both object and dict)
            initial_enemies = getattr(scenario_setup, 'initial_enemies', None)
            if initial_enemies is None and isinstance(scenario_setup, dict):
                initial_enemies = scenario_setup.get('initial_enemies', [])

            if initial_enemies and self.enemy_combat and self.enemy_combat.enabled:
                # Reconstruct EnemySpawn objects if they were serialized to dicts
                from .schemas.story_events import EnemySpawn
                enemy_spawn_objects = []
                for enemy in initial_enemies:
                    if isinstance(enemy, dict):
                        enemy_spawn_objects.append(EnemySpawn(**enemy))
                    else:
                        enemy_spawn_objects.append(enemy)

                spawn_notifications = self.enemy_combat.spawn_from_structured(
                    enemy_spawn_objects
                )
                for notification in spawn_notifications:
                    print(f"\n{notification}")

            # Get initial_npcs (works for both object and dict)
            # Note: dm.py stores NPC spawns as 'npc_spawns' in scenario_setup_dict,
            # so fall back to that key if 'initial_npcs' not found
            npc_spawns = getattr(scenario_setup, 'initial_npcs', None)
            if npc_spawns is None and isinstance(scenario_setup, dict):
                npc_spawns = scenario_setup.get('initial_npcs', scenario_setup.get('npc_spawns', []))

            if npc_spawns:
                # Reconstruct NPCSpawn objects if they were serialized to dicts
                from .schemas.story_events import NPCSpawn, EntityLifecycleResult

                # Create entity lifecycle result to track NPC spawns
                entity_lifecycle_result = EntityLifecycleResult()

                # Process NPC spawns via DM
                for npc_spawn in npc_spawns:
                    # Reconstruct NPCSpawn if it's a dict
                    if isinstance(npc_spawn, dict):
                        npc_spawn = NPCSpawn(**npc_spawn)

                    # Find DM agent
                    dm_agent = None
                    for agent in self.agents:
                        if agent.agent_id.startswith('dm_'):
                            dm_agent = agent
                            break

                    if dm_agent and hasattr(dm_agent, '_process_npc_spawn'):
                        npc = dm_agent._process_npc_spawn(npc_spawn)
                        print(f"\n✓ NPC spawned: {npc.name} ({npc.entity_type}, {npc.disposition})")

                        # Track NPC spawn in lifecycle result
                        entity_lifecycle_result.npcs_spawned.append(npc.agent_id)
                    else:
                        logger.warning(f"Cannot spawn NPC {npc_spawn.name} - DM not found or missing _process_npc_spawn")

                # Log entity_lifecycle event if NPCs were spawned
                if entity_lifecycle_result.npcs_spawned:
                    mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
                    if mechanics and mechanics.jsonl_logger:
                        lifecycle_dict = entity_lifecycle_result.to_jsonl_dict(
                            round_num=0  # Session start is before Round 1
                        )
                        mechanics.jsonl_logger.log_event(
                            'entity_lifecycle',
                            lifecycle_dict,
                            round_num=0
                        )
                        logger.info(f"Logged entity_lifecycle event for {len(entity_lifecycle_result.npcs_spawned)} session start NPCs")

        self._scenario_ready.set()

    async def _run_pre_round_entity_lifecycle(self):
        """
        Run entity lifecycle phase BEFORE round 1 to populate the scene.

        This allows the DM to spawn additional entities based on the scenario theme:
        - Vendors, merchants appropriate to the location
        - Bystanders, civilians for atmosphere
        - Environmental objects for interaction
        - Patrols or guards (as enemies if hostile)

        Called AFTER scenario setup (which processes initial_enemies/initial_npcs from config)
        but BEFORE round 1 begins.
        """
        from .schemas.story_events import EntityLifecycleResult, EnemySpawn, NPCSpawn

        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None

        print(f"\n{'='*80}")
        print(f"🔄 PRE-ROUND ENTITY LIFECYCLE PHASE")
        print(f"{'='*80}")
        logger.info("Running pre-round entity lifecycle phase")

        # Create entity lifecycle result to track spawns
        entity_lifecycle_result = EntityLifecycleResult()

        # Build list of already-spawned entities (from config)
        existing_entities = {
            'npcs': [],
            'enemies': []
        }

        if self.shared_state:
            # Get existing NPC names/IDs
            if hasattr(self.shared_state, 'npc_agents'):
                for npc in self.shared_state.npc_agents:
                    existing_entities['npcs'].append(f"{npc.name} ({npc.agent_id})")

            # Get existing enemy names/IDs
            if self.enemy_combat and hasattr(self.enemy_combat, 'enemy_agents'):
                for enemy in self.enemy_combat.enemy_agents:
                    if enemy.is_active:
                        existing_entities['enemies'].append(f"{enemy.name} ({enemy.agent_id})")

        # Find DM agent
        dm_agent = None
        for agent in self.agents:
            if agent.agent_id.startswith('dm_'):
                dm_agent = agent
                break

        if not dm_agent or not hasattr(dm_agent, 'check_conversions'):
            logger.warning("Pre-round lifecycle: DM agent not found or missing check_conversions")
            print("⚠️  DM not available for pre-round entity lifecycle")
            return entity_lifecycle_result

        # Call DM check_conversions with pre_round=True
        try:
            conversion_decisions = await dm_agent.check_conversions(
                round_number=0,
                resolution_summary="",  # Will be overridden by pre_round logic in DM
                pre_round=True,
                existing_entities=existing_entities
            )

            print(f"\n✅ Pre-round decisions:")
            print(f"   - NPC spawns: {len(conversion_decisions.npc_spawns)}")
            print(f"   - Enemy spawns: {len(conversion_decisions.enemy_spawns)}")
            print(f"   - Env object spawns: {len(conversion_decisions.env_object_spawns) if hasattr(conversion_decisions, 'env_object_spawns') else 0}")
            print(f"   - Reasoning: {conversion_decisions.reasoning}")

            logger.info(f"Pre-round decisions: {len(conversion_decisions.npc_spawns)} NPCs, "
                       f"{len(conversion_decisions.enemy_spawns)} enemies")

            # Process NPC spawns
            if conversion_decisions.npc_spawns and dm_agent and hasattr(dm_agent, '_process_npc_spawn'):
                for npc_spawn in conversion_decisions.npc_spawns:
                    # Reconstruct NPCSpawn if it's a dict
                    if isinstance(npc_spawn, dict):
                        npc_spawn = NPCSpawn(**npc_spawn)

                    npc = dm_agent._process_npc_spawn(npc_spawn)
                    print(f"\n✓ NPC spawned (pre-round): {npc.name} ({npc.entity_type}, {npc.disposition})")
                    entity_lifecycle_result.npcs_spawned.append(npc.agent_id)

            # Process enemy spawns
            if conversion_decisions.enemy_spawns and self.enemy_combat:
                # Enable enemy combat if we're spawning enemies
                if not self.enemy_combat.enabled:
                    logger.info("Enabling enemy combat due to pre-round enemy spawn")
                    self.enemy_combat.enabled = True

                # Reconstruct EnemySpawn objects if they're dicts
                enemy_spawn_list = []
                for enemy_spawn in conversion_decisions.enemy_spawns:
                    if isinstance(enemy_spawn, dict):
                        enemy_spawn = EnemySpawn(**enemy_spawn)
                    enemy_spawn_list.append(enemy_spawn)

                # Spawn all enemies
                spawn_notifications = self.enemy_combat.spawn_from_structured(enemy_spawn_list)

                # Track spawned enemy agent_ids
                for enemy in self.enemy_combat.enemy_agents:
                    if enemy.spawned_round == 0:
                        entity_lifecycle_result.enemies_spawned.append(enemy.agent_id)

                for notification in spawn_notifications:
                    print(f"\n{notification}")
                    logger.info(f"Enemy spawn (pre-round): {notification}")

            # Process env object spawns
            if hasattr(conversion_decisions, 'env_object_spawns') and conversion_decisions.env_object_spawns:
                if mechanics and hasattr(mechanics, 'env_objects'):
                    for env_spawn in conversion_decisions.env_object_spawns:
                        # Add to mechanics env_objects
                        obj_id = env_spawn.object_id if hasattr(env_spawn, 'object_id') else f"obj_{env_spawn.name.lower().replace(' ', '_')}"
                        mechanics.env_objects[obj_id] = {
                            'name': env_spawn.name,
                            'description': env_spawn.description,
                            'interaction_hint': getattr(env_spawn, 'interaction_hint', ''),
                            'discovery_dc': getattr(env_spawn, 'discovery_dc', 10),
                            'discovered': False,
                            'spawned_round': 0
                        }
                        entity_lifecycle_result.env_objects_spawned.append(obj_id)
                        print(f"\n✓ Env object spawned (pre-round): {env_spawn.name}")
                        logger.info(f"Env object spawn (pre-round): {env_spawn.name}")

            # Log entity_lifecycle event if anything was spawned
            if (entity_lifecycle_result.npcs_spawned or
                entity_lifecycle_result.enemies_spawned or
                entity_lifecycle_result.env_objects_spawned):

                if mechanics and mechanics.jsonl_logger:
                    lifecycle_dict = entity_lifecycle_result.to_jsonl_dict(round_num=0)
                    # Add conversion_decisions context
                    lifecycle_dict['conversion_decisions'] = {
                        'reasoning': conversion_decisions.reasoning,
                        'is_pre_round': True
                    }
                    mechanics.jsonl_logger.log_event(
                        'entity_lifecycle',
                        lifecycle_dict,
                        round_num=0
                    )
                    logger.info(f"Logged pre-round entity_lifecycle event: "
                               f"{len(entity_lifecycle_result.npcs_spawned)} NPCs, "
                               f"{len(entity_lifecycle_result.enemies_spawned)} enemies, "
                               f"{len(entity_lifecycle_result.env_objects_spawned)} env objects")

        except Exception as e:
            logger.error(f"Pre-round entity lifecycle failed: {type(e).__name__}: {e}")
            print(f"\n⚠️  Pre-round entity lifecycle error: {e}")

        return entity_lifecycle_result

    def _resolve_speech_target_agent_id(self, target: Optional[str]) -> Optional[str]:
        """Resolve an ambient speech target to a permanent agent_id when possible."""
        if not target:
            return None

        if self.shared_state:
            direct = self.shared_state.get_agent_by_id(target)
            if direct is not None:
                return getattr(direct, 'agent_id', target)

            mapper = self.shared_state.get_target_id_mapper()
            if mapper and target.startswith('tgt_'):
                target_entity = mapper.resolve_target(target)
                if target_entity is not None:
                    return (
                        getattr(target_entity, 'agent_id', None)
                        or getattr(target_entity, 'vendor_id', None)
                        or getattr(target_entity, 'object_id', None)
                    )

        return target if target.startswith(('player_', 'npc_', 'enemy_')) else None

    def _party_agent_ids(self, include_speaker: bool = True, speaker_id: Optional[str] = None) -> List[str]:
        """Return active PC agent IDs for party-directed speech."""
        if not self.shared_state:
            return []

        ids = []
        for player in getattr(self.shared_state, 'player_agents', []) or []:
            agent_id = getattr(player, 'agent_id', None)
            if not agent_id:
                continue
            if not include_speaker and speaker_id and agent_id == speaker_id:
                continue
            if getattr(player, 'is_alive', True) and not getattr(player, '_permanently_dead', False):
                ids.append(agent_id)
        return ids

    def _ambient_speech_aware_agents(self, speaker_id: str, ambient_speech: Dict[str, Any]) -> List[str]:
        """
        Compute aware_agents for non-mechanical ambient speech.

        Empty list follows the existing awareness convention: public to everyone.
        Populated list limits visibility to those agent IDs.
        """
        delivery = ambient_speech.get('delivery', 'spoken')
        target_type = ambient_speech.get('target_type', 'self')
        target = ambient_speech.get('target')
        target_agent_id = self._resolve_speech_target_agent_id(target)

        if delivery == 'whisper':
            aware = [speaker_id]
            if target_agent_id and target_agent_id != speaker_id:
                aware.append(target_agent_id)
            return aware

        if delivery == 'comms':
            if target_type == 'party':
                return self._party_agent_ids(include_speaker=True, speaker_id=speaker_id)
            if target_agent_id:
                return [agent_id for agent_id in [speaker_id, target_agent_id] if agent_id]
            return [speaker_id]

        if target_type == 'self':
            return [speaker_id]

        # Spoken speech in the scene is public by default; targeted spoken
        # speech remains public so nearby actors can plausibly overhear.
        return []

    def _format_ambient_speech_entry(
        self,
        speaker_name: str,
        ambient_speech: Dict[str, Any],
    ) -> str:
        """Format ambient speech as a concise context line for later actors."""
        line = ambient_speech.get('line', '').strip()
        delivery = ambient_speech.get('delivery', 'spoken')
        target_type = ambient_speech.get('target_type', 'self')
        target = ambient_speech.get('target')

        target_text = target or target_type
        return f'[{speaker_name}, {delivery} to {target_text}] "{line}"'

    def _publish_ambient_speech_context(self, speaker_id: str, action_payload: Dict[str, Any]) -> None:
        """Add ambient speech to the existing visibility-filtered narration stream."""
        ambient_speech = action_payload.get('ambient_speech')
        if not isinstance(ambient_speech, dict) or not ambient_speech.get('line'):
            return

        speaker_name = action_payload.get('character_name') or action_payload.get('character') or speaker_id
        entry = NarrationEntry(
            text=self._format_ambient_speech_entry(speaker_name, ambient_speech),
            aware_agents=self._ambient_speech_aware_agents(speaker_id, ambient_speech),
        )

        stored_count = 0
        for player_agent in getattr(self.shared_state, 'player_agents', []) or []:
            if not hasattr(player_agent, 'recent_narrations'):
                continue
            player_agent.recent_narrations.append(entry)
            if len(player_agent.recent_narrations) > 20:
                player_agent.recent_narrations.pop(0)
            stored_count += 1

        logger.debug(
            "Ambient speech context stored from %s (aware=%s, player_buffers=%s)",
            speaker_id,
            entry.aware_agents,
            stored_count,
        )

    def _handle_action_declared(self, message: Message):
        """Buffer ACTION_DECLARED messages during declaration phase."""
        if message.type != MessageType.ACTION_DECLARED:
            return

        # Ignore directed messages (e.g., adjudication messages to DM during resolution phase)
        # Only buffer broadcast messages (recipient=None) from players/enemies declaring actions
        if message.recipient is not None:
            return

        # Only buffer during declaration phase
        if not self._in_declaration_phase:
            # Enhanced logging to debug spurious ACTION_DECLARED messages
            import traceback
            caller_stack = ''.join(traceback.format_stack()[-4:-1])  # Get last 3 frames before this one
            agent_id = message.sender
            intent = message.payload.get('intent', 'unknown')[:60]
            character_name = message.payload.get('character_name', 'unknown')
            action_type = message.payload.get('action_type', 'unknown')
            is_free = message.payload.get('is_free_action', False)

            logger.warning(
                f"⚠️  ACTION_DECLARED DROPPED (not in declaration phase):\n"
                f"  Sender: {agent_id}\n"
                f"  Character: {character_name}\n"
                f"  Intent: {intent}\n"
                f"  Action Type: {action_type}\n"
                f"  Is Free: {is_free}\n"
                f"  Message ID: {message.id}\n"
                f"  Recipient: {message.recipient}\n"
                f"  Call stack:\n{caller_stack}"
            )
            return

        # Get agent_id early (needed for validation checks below)
        agent_id = message.sender

        # PRE-VALIDATE ATTUNEMENT ACTIONS (check prerequisites, store result)
        # Similar to purchases - validates inventory/equipment but doesn't execute (DM rolls dice)
        # Validation result stored in action payload for DM to see
        action_type = message.payload.get('action_type')
        action_payload = message.payload  # Get reference to payload for modification

        if action_type == 'attune':
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)

                if player_agent:
                    try:
                        # Extract attunement parameters from action payload
                        target_energy = action_payload.get('target_energy')
                        altar_id = action_payload.get('altar_id')
                        use_echo_calibrator = action_payload.get('use_echo_calibrator', False)

                        # Validate prerequisites (inventory, equipment, altar existence)
                        validation = mechanics.validate_attunement(
                            character_state=player_agent.character_state,
                            target_energy=target_energy,
                            altar_id=altar_id,
                            use_echo_calibrator=use_echo_calibrator
                        )

                        # Store validation result on the action for DM to see
                        action_payload['attunement_validation'] = {
                            'is_valid': validation.is_valid,
                            'failure_reason': validation.failure_reason,
                            'has_seed': validation.has_seed if hasattr(validation, 'has_seed') else None,
                            'has_equipment': validation.has_equipment if hasattr(validation, 'has_equipment') else None,
                            'altar_found': validation.altar_found if hasattr(validation, 'altar_found') else None
                        }

                        if not validation.is_valid:
                            # Log validation failure but still buffer action for coordinator
                            logger.warning(
                                f"❌ ATTUNEMENT VALIDATION FAILED for {player_agent.character_state.name}: "
                                f"{validation.failure_reason}"
                            )

                            # Print warning to console for player visibility
                            print(
                                f"\n⚠️  [{player_agent.character_state.name}] Attunement validation failed: "
                                f"{validation.failure_reason}"
                            )
                            print("   └─ DM will narrate automatic failure (no roll needed)\n")
                        else:
                            logger.info(f"✓ Attunement validated for {player_agent.character_state.name}")

                    except Exception as e:
                        logger.error(f"Error validating attunement for {agent_id}: {e}")
                        # Store error in validation result
                        action_payload['attunement_validation'] = {
                            'is_valid': False,
                            'failure_reason': f"Validation error: {str(e)}"
                        }

        # Buffer the action (supports multiple actions per agent for free action system)
        # Note: message.payload IS the action dict (not nested under 'action' key)
        # (agent_id already extracted above for validation checks)

        # Initialize list if this is the first action from this agent
        if agent_id not in self._declared_actions:
            self._declared_actions[agent_id] = []

        # Append this action to the agent's action list
        self._declared_actions[agent_id].append({
            'agent_id': agent_id,
            'action': message.payload,  # Payload IS the action
            'timestamp': message.timestamp
        })
        action_intent = message.payload.get('intent', 'unknown')[:60]
        is_free = message.payload.get('is_free_action', False)
        logger.info(f"✓ Buffered {'FREE' if is_free else 'MAIN'} action from {agent_id}: {action_intent} (total: {len(self._declared_actions[agent_id])} actions)")

        self._publish_ambient_speech_context(agent_id, message.payload)

        # Store defence_token on agent from player declaration (Spec 04)
        defence_token = message.payload.get('defence_token')
        if defence_token:
            player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)
            if player_agent and hasattr(player_agent, 'defence_token'):
                player_agent.defence_token = defence_token
                logger.info(f"{agent_id} watching {defence_token}")

        # PRE-VALIDATE AND EXECUTE PURCHASE ACTIONS (before DM sees them)
        # This prevents phantom purchases where DM narrates success but mechanics fail
        action_payload = message.payload
        vendor_id = action_payload.get('vendor_id')
        item_id = action_payload.get('item_id')

        if vendor_id and item_id:
            # This is a purchase action - validate AND execute BEFORE DM narration
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)

                if player_agent:
                    try:
                        validation = mechanics.validate_purchase(
                            character_state=player_agent.character_state,
                            vendor_id=vendor_id,
                            item_id=item_id
                        )

                        # Store validation result on the action for DM to see
                        action_payload['purchase_validation'] = {
                            'can_afford': validation.can_afford,
                            'item_name': validation.item_name,
                            'cost': validation.cost,
                            'player_currency': validation.player_currency,
                            'shortage': validation.shortage,
                            'failure_reason': validation.failure_reason
                        }

                        if validation.can_afford:
                            # EXECUTE TRANSACTION MECHANICALLY (before DM narrates)
                            # Deduct currency
                            for currency_type, amount in validation.cost.items():
                                if amount > 0:
                                    player_agent.character_state.energy_purse.spend_currency(currency_type, amount)

                            # Add item to inventory
                            inventory = player_agent.character_state.inventory
                            inventory_key = validation.inventory_key
                            inventory[inventory_key] = inventory.get(inventory_key, 0) + 1

                            # Format cost dict as readable string (e.g., "5 drip, 2 grain")
                            cost_str = ", ".join([f"{amount} {currency}" for currency, amount in validation.cost.items() if amount > 0]) if validation.cost else "free"
                            logger.info(f"✓ PURCHASE EXECUTED: {player_agent.character_state.name} bought {validation.item_name} for {cost_str}")
                            action_payload['purchase_validation']['executed'] = True
                        else:
                            logger.warning(f"Purchase pre-validation FAILED: {validation.failure_reason}")
                            action_payload['purchase_validation']['executed'] = False

                        # LOG PURCHASE ATTEMPT (both success and failure)
                        if mechanics.jsonl_logger:
                            # Try NPC vendor first (unified system), then fall back to legacy vendor
                            vendor = self.shared_state.get_npc_by_vendor_id(vendor_id)
                            if not vendor:
                                vendor = self.shared_state.get_vendor_by_id(vendor_id)
                            vendor_name = vendor.name if vendor else "Unknown Vendor"

                            mechanics.jsonl_logger.log_purchase_attempt(
                                round_num=mechanics.current_round,
                                player_id=agent_id,
                                character_name=player_agent.character_state.name,
                                vendor_id=vendor_id,
                                vendor_name=vendor_name,
                                item_id=item_id,
                                item_name=validation.item_name,
                                cost=validation.cost,
                                player_currency=validation.player_currency,
                                success=validation.can_afford,
                                failure_reason=validation.failure_reason,
                                shortage=validation.shortage
                            )

                    except Exception as e:
                        logger.error(f"Error pre-validating purchase for {agent_id}: {e}")
                        action_payload['purchase_validation'] = {
                            'can_afford': False,
                            'failure_reason': f"Validation error: {str(e)}",
                            'executed': False
                        }

        # PRE-VALIDATE CHECKPOINT ACCESS (before DM sees the action)
        # If a player action targets passing a gated checkpoint, the Soulcredit
        # gate (VIII.1/VIII.2) is authoritative: the result is stashed for the
        # DM to narrate, so a Cut-Off actor cannot be waved through.
        checkpoint_id = action_payload.get('checkpoint_id')
        if checkpoint_id and self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)
            checkpoint = self.shared_state.get_checkpoint_by_id(checkpoint_id)
            if player_agent and checkpoint:
                access = mechanics.validate_checkpoint_access(
                    player_agent.character_state, checkpoint)
                action_payload['checkpoint_validation'] = {
                    'checkpoint_name': access.checkpoint_name,
                    'is_allowed': access.is_allowed,
                    'sc_blocked': access.sc_blocked,
                    'failure_reason': access.failure_reason,
                }
                if not access.is_allowed:
                    logger.warning(f"Checkpoint access DENIED for {agent_id} at "
                                   f"{access.checkpoint_name}: {access.failure_reason}")
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        event_type="checkpoint_access",
                        data={
                            'player_id': agent_id,
                            'character_name': player_agent.character_state.name,
                            'checkpoint_id': checkpoint_id,
                            **action_payload['checkpoint_validation'],
                        },
                        round_num=mechanics.current_round,
                    )

        # PRE-VALIDATE AND EXECUTE TRANSFER ACTIONS (before DM sees them)
        # Similar to purchases - prevents phantom transfers where DM narrates success but mechanics fail
        transfer_target = action_payload.get('transfer_target')
        transfer_currency = action_payload.get('transfer_currency')
        transfer_items = action_payload.get('transfer_items')

        if transfer_target and (transfer_currency or transfer_items):
            # This is a transfer action - validate AND execute BEFORE DM narration
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)

                if player_agent:
                    try:
                        # Get sender position for range checking
                        sender_position = getattr(player_agent, 'position', None)

                        validation = mechanics.validate_transfer(
                            sender_state=player_agent.character_state,
                            transfer_target=transfer_target,
                            transfer_currency=transfer_currency,
                            transfer_items=transfer_items,
                            sender_position=sender_position
                        )

                        # Store validation result on the action for DM to see
                        action_payload['transfer_validation'] = {
                            'is_valid': validation.is_valid,
                            'sender_name': validation.sender_name,
                            'receiver_name': validation.receiver_name,
                            'receiver_agent_id': validation.receiver_agent_id,
                            'currency': validation.currency,
                            'items': validation.items,
                            'sender_currency': validation.sender_currency,
                            'sender_items': validation.sender_items,
                            'shortage': validation.shortage,
                            'item_shortage': validation.item_shortage,
                            'failure_reason': validation.failure_reason,
                            'in_range': validation.in_range
                        }

                        if validation.is_valid:
                            # EXECUTE TRANSFER MECHANICALLY (before DM narrates)
                            # Search BOTH player_agents AND npc_agents for receiver
                            receiver_agent = next(
                                (a for a in self.shared_state.player_agents
                                 if a.agent_id == validation.receiver_agent_id),
                                None
                            )
                            # If not found in players, check NPCs
                            if receiver_agent is None and hasattr(self.shared_state, 'npc_agents'):
                                receiver_agent = next(
                                    (n for n in self.shared_state.npc_agents
                                     if n.agent_id == validation.receiver_agent_id),
                                    None
                                )

                            if receiver_agent:
                                success = True

                                # Execute currency transfer if present
                                # Use helper to get purse (handles both player and NPC patterns)
                                if transfer_currency:
                                    sender_purse = _get_energy_purse(player_agent)
                                    receiver_purse = _get_energy_purse(receiver_agent)
                                    if sender_purse and receiver_purse:
                                        currency_success = sender_purse.transfer_currencies_to(
                                            receiver_purse=receiver_purse,
                                            currency_amounts=transfer_currency
                                        )
                                        success = success and currency_success
                                    else:
                                        logger.error(f"Missing energy purse: sender={sender_purse is not None}, receiver={receiver_purse is not None}")
                                        success = False

                                # Execute item transfer if present
                                # Use helper to get/create inventory (handles both player and NPC patterns)
                                if transfer_items:
                                    sender_inv = _get_inventory(player_agent)
                                    receiver_inv = _get_inventory(receiver_agent)
                                    for item_name, amount in transfer_items.items():
                                        # Remove from sender
                                        if sender_inv and item_name in sender_inv:
                                            sender_inv[item_name] -= amount
                                            if sender_inv[item_name] <= 0:
                                                del sender_inv[item_name]

                                        # Add to receiver
                                        receiver_inv[item_name] = receiver_inv.get(item_name, 0) + amount

                                if success:
                                    transfer_desc = []
                                    if transfer_currency:
                                        transfer_desc.append(f"Currency: {transfer_currency}")
                                    if transfer_items:
                                        transfer_desc.append(f"Items: {transfer_items}")
                                    logger.info(
                                        f"✓ TRANSFER EXECUTED: {validation.sender_name} → {validation.receiver_name}: "
                                        f"{', '.join(transfer_desc)}"
                                    )
                                    action_payload['transfer_validation']['executed'] = True
                                else:
                                    logger.error(f"Transfer execution failed despite validation passing")
                                    action_payload['transfer_validation']['executed'] = False
                                    action_payload['transfer_validation']['is_valid'] = False
                                    action_payload['transfer_validation']['failure_reason'] = "Mechanical transfer failed"
                            else:
                                logger.error(f"Receiver agent {validation.receiver_agent_id} not found for transfer")
                                action_payload['transfer_validation']['executed'] = False
                                action_payload['transfer_validation']['is_valid'] = False
                                action_payload['transfer_validation']['failure_reason'] = "Receiver not found"
                        else:
                            logger.warning(f"Transfer pre-validation FAILED: {validation.failure_reason}")
                            action_payload['transfer_validation']['executed'] = False

                        # LOG TRANSFER ATTEMPT (both success and failure)
                        if mechanics.jsonl_logger:
                            log_data = {
                                'sender_id': agent_id,
                                'sender_name': validation.sender_name,
                                'receiver_id': validation.receiver_agent_id,
                                'receiver_name': validation.receiver_name,
                                'currency': validation.currency,
                                'items': validation.items,
                                'success': validation.is_valid,
                                'failure_reason': validation.failure_reason,
                                'in_range': validation.in_range
                            }

                            if validation.is_valid:
                                if validation.currency:
                                    log_data['sender_currency_after'] = {
                                        'spark': player_agent.character_state.energy_purse.spark,
                                        'grain': player_agent.character_state.energy_purse.grain,
                                        'drip': player_agent.character_state.energy_purse.drip,
                                        'breath': player_agent.character_state.energy_purse.breath
                                    }
                                if validation.items:
                                    log_data['sender_items_after'] = dict(player_agent.character_state.inventory) if player_agent.character_state.inventory else {}
                            else:
                                log_data['sender_currency'] = validation.sender_currency
                                log_data['sender_items'] = validation.sender_items

                            mechanics.jsonl_logger.log_event(
                                'energy_transfer',
                                log_data,
                                mechanics.current_round
                            )

                    except Exception as e:
                        logger.error(f"Error pre-validating transfer for {agent_id}: {e}")
                        action_payload['transfer_validation'] = {
                            'is_valid': False,
                            'failure_reason': f"Validation error: {str(e)}",
                            'executed': False
                        }

        # PRE-VALIDATE AND EXECUTE CONSUMPTION ACTIONS (before DM sees them)
        # Food consumption is deterministic (+2 HP), so execute before DM narration
        action_type = action_payload.get('action_type')
        consume_item_id = action_payload.get('item_id')

        if action_type == 'consume' and consume_item_id:
            # This is a consumption action - validate AND execute BEFORE DM narration
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)

                if player_agent:
                    try:
                        # Get the food item from GLOBAL_VENDOR_CATALOG
                        from .energy_economy import GLOBAL_VENDOR_CATALOG
                        food_item = next((item for item in GLOBAL_VENDOR_CATALOG if item.item_id == consume_item_id), None)

                        if not food_item:
                            # Item not found in catalog
                            action_payload['consumption_validation'] = {
                                'is_valid': False,
                                'failure_reason': f"Item {consume_item_id} not found in vendor catalog",
                                'executed': False
                            }
                            logger.warning(f"Consumption validation FAILED: item {consume_item_id} not in catalog")
                        else:
                            # Validate consumption
                            validation = mechanics.validate_consumption(
                                character_state=player_agent.character_state,
                                item_id=consume_item_id,
                                food_item=food_item
                            )

                            # Store validation result on the action for DM to see
                            action_payload['consumption_validation'] = {
                                'is_valid': validation.is_valid,
                                'failure_reason': validation.failure_reason,
                                'item_name': food_item.name,
                                'item_type': food_item.item_type,
                                'healing': 2  # Fixed healing amount
                            }

                            if validation.is_valid:
                                # EXECUTE CONSUMPTION MECHANICALLY (before DM narrates)
                                from .schemas.action_effects import ConsumptionEffect

                                consumption_effect = ConsumptionEffect(
                                    item_id=consume_item_id,
                                    inventory_key=food_item.inventory_key,
                                    healing=2
                                )

                                success = mechanics.process_consumption_effect(
                                    consumption_effect=consumption_effect,
                                    character_state=player_agent.character_state
                                )

                                if success:
                                    logger.info(
                                        f"✓ CONSUMPTION EXECUTED: {player_agent.character_state.name} consumed {food_item.name} "
                                        f"(+2 HP: {player_agent.character_state.health}/{player_agent.character_state.max_health})"
                                    )
                                    action_payload['consumption_validation']['executed'] = True
                                else:
                                    logger.warning("Consumption execution failed (likely 0 quantity)")
                                    action_payload['consumption_validation']['executed'] = False
                                    action_payload['consumption_validation']['is_valid'] = False
                                    action_payload['consumption_validation']['failure_reason'] = "Item quantity is 0"
                            else:
                                logger.warning(f"Consumption pre-validation FAILED: {validation.failure_reason}")
                                action_payload['consumption_validation']['executed'] = False

                            # LOG CONSUMPTION ATTEMPT (both success and failure)
                            if mechanics.jsonl_logger:
                                log_data = {
                                    'player_id': agent_id,
                                    'character_name': player_agent.character_state.name,
                                    'item_id': consume_item_id,
                                    'item_name': food_item.name,
                                    'healing': 2,
                                    'success': validation.is_valid and action_payload['consumption_validation'].get('executed', False),
                                    'failure_reason': validation.failure_reason
                                }

                                if validation.is_valid and action_payload['consumption_validation'].get('executed', False):
                                    log_data['health_after'] = player_agent.character_state.health
                                    log_data['max_health'] = player_agent.character_state.max_health
                                    inventory_key = food_item.inventory_key
                                    log_data['item_remaining'] = player_agent.character_state.inventory.get(inventory_key, 0)

                                mechanics.jsonl_logger.log_event(
                                    'food_consumption',
                                    log_data,
                                    mechanics.current_round
                                )

                    except Exception as e:
                        logger.error(f"Error pre-validating consumption for {agent_id}: {e}")
                        action_payload['consumption_validation'] = {
                            'is_valid': False,
                            'failure_reason': f"Validation error: {str(e)}",
                            'executed': False
                        }

        # NOTE: Attunement actions are NOT pre-executed like purchases/transfers
        # Unlike deterministic transactions, attunements involve dice rolls and DM adjudication
        # The DM rolls the ritual check, determines success/failure, and populates AttunementEffect
        # The mechanics layer processes the DM's AttunementEffect during resolution phase
        # This ensures seed consumption and energy grants happen AFTER DM adjudication, not before

        # Log the declaration
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                # Find the character name and initiative for this agent
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)
                if player_agent:
                    character_name = player_agent.character_state.name
                    # Get initiative from stored value (rolled at round start)
                    initiative = self._current_initiative.get(agent_id, 0)
                    mechanics.jsonl_logger.log_action_declaration(
                        player_id=agent_id,
                        character_name=character_name,
                        initiative=initiative,
                        action=message.payload,
                        round_num=mechanics.current_round
                    )

        # Signal that this agent's declaration is complete
        # CRITICAL: Only signal when we receive the MAIN action (not free action)
        # Free actions are followed by main actions, so we must wait for the main action
        # to avoid closing declaration phase prematurely
        is_free_action = message.payload.get('is_free_action', False)

        if agent_id in self._pending_declarations:
            if not is_free_action:
                # This is the main action - signal completion
                self._pending_declarations[agent_id].set()
                logger.debug(f"✓ Declaration complete for {agent_id} (main action received)")
            else:
                # This is a free action - don't signal yet, wait for main action
                logger.debug(f"⏳ Free action received from {agent_id}, waiting for main action...")
        elif not agent_id.startswith(('enemy_', 'npc_')):
            # Only warn if it's not an enemy or NPC (both declare inline, no pending event expected)
            logger.warning(f"No pending declaration event for {agent_id}")

    def _handle_action_resolved(self, message: Message):
        """Handle ACTION_RESOLVED messages to signal turn completion."""
        if message.type != MessageType.ACTION_RESOLVED:
            return

        # Extract the agent who completed their action
        agent_id = message.payload.get('agent_id')
        action_index = message.payload.get('action_index', 0)  # Default to 0 for backward compatibility

        # Check for error flag in the resolution (DM sends this on fatal failure)
        has_error = message.payload.get('error', False)
        error_message = message.payload.get('error_message', '')

        # Build the event key (must match the key used when storing the event)
        event_key = f"{agent_id}_{action_index}"

        if event_key in self._pending_resolutions:
            # Store resolution data on the event for later collection
            event = self._pending_resolutions[event_key]
            event.resolution_data = message.payload.get('resolution_data')
            # Store error info if present
            if has_error:
                event.error = True
                event.error_message = error_message
                logger.error(f"Resolution {event_key} returned with error: {error_message}")
            # Signal that this agent's resolution/adjudication is complete
            event.set()
            logger.debug(f"Resolution complete for {event_key}")
        elif agent_id in self._pending_resolutions:
            # Fallback for old-style keys (no index)
            event = self._pending_resolutions[agent_id]
            event.resolution_data = message.payload.get('resolution_data')
            # Store error info if present
            if has_error:
                event.error = True
                event.error_message = error_message
                logger.error(f"Resolution {agent_id} returned with error: {error_message}")
            event.set()
            logger.debug(f"Resolution complete for {agent_id} (legacy)")

    def _handle_agent_error(self, message: Message):
        """Handle AGENT_ERROR messages from agents with fatal errors."""
        if message.type != MessageType.AGENT_ERROR:
            return

        agent_id = message.payload.get('agent_id', 'unknown')
        error_type = message.payload.get('error_type', 'unknown')
        error_message = message.payload.get('error_message', 'Unknown error')
        recoverable = message.payload.get('recoverable', False)

        logger.error(f"❌ Received AGENT_ERROR from {agent_id}: {error_type} - {error_message}")

        # Log to console for visibility
        print(f"\n❌ FATAL AGENT ERROR from {agent_id}:")
        print(f"   Type: {error_type}")
        print(f"   Message: {error_message}")

        # Store error for main loop to detect and terminate gracefully
        if not recoverable:
            self._fatal_error = error_message
            # If session is still running, it will see this flag and terminate

    async def _process_structured_synthesis(self, synthesis: 'RoundSynthesis'):
        """
        Process structured round synthesis (Phase 5: Pydantic AI migration).

        This method handles:
        - Story advancement with conditional enemy clearing
        - Entity Lifecycle Phase #2 (spawn entities for new scene)
        - New clock spawning
        - Session end
        """
        from .schemas.story_events import RoundSynthesis
        from .dm import AIDMAgent

        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None

        logger.info("Processing structured synthesis (Phase 5)")

        # 1. Handle story advancement FIRST (before enemy spawning)
        if synthesis.story_advancement and synthesis.story_advancement.should_advance:
            adv = synthesis.story_advancement
            logger.info(f"Story advancement: {adv.location} - {adv.situation}")

            # Clock persistence: keep_clocks names clocks to preserve across story advancement.
            # Default (empty keep_clocks) = clear ALL clocks (major transition behavior).
            # Non-empty keep_clocks = clear everything NOT in the list.
            if mechanics and mechanics.scene_clocks:
                keep_set = set(getattr(adv, 'keep_clocks', []) or [])

                # Clock conservation: a pivot is not an amnesty. Terminal
                # and high-progress clocks follow the party automatically.
                from .mechanics import partition_story_advancement_clocks
                clocks_to_remove, auto_kept = partition_story_advancement_clocks(
                    mechanics.scene_clocks, list(keep_set))
                for clock_name in auto_kept:
                    clock = mechanics.scene_clocks[clock_name]
                    logger.info(
                        f"Clock auto-persisted through story advancement: "
                        f"{clock_name} ({clock.current}/{clock.maximum}"
                        f"{', terminal' if getattr(clock, 'is_terminal', False) else ''})")
                    if mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_event(
                            event_type="clock_update",
                            data={"clock_name": clock_name,
                                  "current_ticks": clock.current,
                                  "maximum_ticks": clock.maximum,
                                  "update_reason": "auto_persisted_through_story_advancement"},
                            round_num=mechanics.current_round
                        )
                keep_set |= set(auto_kept)

                for clock_name in clocks_to_remove:
                    clock = mechanics.scene_clocks[clock_name]

                    if mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_event(
                            event_type="clock_removal",
                            data={
                                "clock_name": clock_name,
                                "current_ticks": clock.current,
                                "maximum_ticks": clock.maximum,
                                "description": clock.description,
                                "removal_reason": "story_advancement",
                                "expiration_type": None,
                                "filled": clock.filled,
                                "consequence_triggered": False
                            },
                            round_num=mechanics.current_round
                        )
                    mechanics.clock_history.append({
                        'event_type': 'removed',
                        'clock_name': clock_name,
                        'round': mechanics.current_round,
                        'current': clock.current,
                        'max': clock.maximum,
                        'description': clock.description,
                        'removal_reason': 'story_advancement'
                    })

                # Remove non-kept clocks
                for clock_name in clocks_to_remove:
                    del mechanics.scene_clocks[clock_name]

                # Log kept clocks as persisted through story advancement
                for clock_name in keep_set:
                    if clock_name in mechanics.scene_clocks:
                        clock = mechanics.scene_clocks[clock_name]
                        if mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_event(
                                event_type="clock_update",
                                data={
                                    "clock_name": clock_name,
                                    "current_ticks": clock.current,
                                    "maximum_ticks": clock.maximum,
                                    "description": clock.description,
                                    "update_reason": "persisted_through_story_advancement"
                                },
                                round_num=mechanics.current_round
                            )

                kept_count = len(keep_set & set(mechanics.scene_clocks.keys()))
                removed_count = len(clocks_to_remove)
                if kept_count > 0:
                    kept_names = list(mechanics.scene_clocks.keys())
                    logger.info(
                        f"Cleared {removed_count} clocks for story advancement, "
                        f"kept {kept_count}: {kept_names}"
                    )
                else:
                    logger.info(f"Cleared {removed_count} clocks for story advancement")

            # Update environmental void_level if specified
            if adv.new_void_level is not None:
                dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
                if dm_agents and dm_agents[0].current_scenario:
                    old_void = dm_agents[0].current_scenario.void_level
                    dm_agents[0].current_scenario.void_level = adv.new_void_level
                    logger.info(f"🌫️  Environmental void updated: {old_void} → {adv.new_void_level}")
                    print(f"   Void Level: {old_void} → {adv.new_void_level}")

                    # Log to JSONL
                    if mechanics and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_event(
                            event_type="void_level_update",
                            data={
                                "old_void_level": old_void,
                                "new_void_level": adv.new_void_level,
                                "location": adv.location,
                                "reason": "story_advancement"
                            },
                            round_num=mechanics.current_round
                        )

            # Clear enemies (conditional on clear_all_enemies flag)
            if adv.clear_all_enemies:
                if self.enemy_combat and self.enemy_combat.enemy_agents:
                    active_enemies = [e for e in self.enemy_combat.enemy_agents if e.is_active]
                    if active_enemies:
                        # Clear enemies
                        for enemy in active_enemies:
                            enemy.is_active = False
                            enemy.despawned_round = mechanics.current_round if mechanics else 0

                        enemy_names = [e.name for e in active_enemies]
                        enemy_ids = [e.agent_id for e in active_enemies]

                        logger.info(f"🗑️  Cleared {len(active_enemies)} enemies (clear_all_enemies=True)")
                        print(f"   Enemies removed: {', '.join(enemy_names)}")

                        # Log to entity_lifecycle event (retroactive update)
                        if mechanics and mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_event(
                                'entity_lifecycle_story_advancement',
                                {
                                    'enemies_cleared': enemy_ids,
                                    'enemy_count': len(active_enemies),
                                    'reason': 'story_advancement_clear_all_enemies',
                                    'new_location': adv.location,
                                    'new_situation': adv.situation
                                },
                                round_num=mechanics.current_round
                            )
            else:
                logger.info("✓ Preserving active enemies (clear_all_enemies=False)")

            # Display and notify
            print(f"\n✨ STORY ADVANCES ✨")
            print(f"   New Location: {adv.location}")
            print(f"   Situation: {adv.situation}")

            # Notify all players of the story advancement
            advance_narration = f"Story advances to: {adv.location}\n{adv.situation}"
            advance_message = Message(
                id=f"advance_{datetime.now().isoformat()}",
                type=MessageType.SCENARIO_UPDATE,
                sender='coordinator',
                recipient=None,  # Broadcast to all
                payload={
                    'new_location': adv.location,
                    'new_situation': adv.situation,
                    'advance_narration': advance_narration,
                    'story_advanced': True
                },
                timestamp=datetime.now()
            )
            import asyncio
            asyncio.create_task(self.coordinator.message_bus._route_message(advance_message))

            # Store advancement for DM
            dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
            if dm_agents:
                dm_agents[0].current_location = adv.location
                dm_agents[0].pending_scenario_pivot = adv.situation

            # Spawn new clocks from story advancement
            if adv.new_clocks:
                self._spawn_new_clocks_structured(adv.new_clocks)

            # Remove departing vendors
            if adv.vendor_departures and self.shared_state:
                for vendor_name in adv.vendor_departures:
                    removed = self.shared_state.remove_vendor(vendor_name)
                    if removed:
                        logger.info(f"💰 Vendor departed: {vendor_name}")
                        print(f"   Vendor departed: {vendor_name}")
                    else:
                        logger.warning(f"Failed to remove vendor '{vendor_name}' - not found in current_vendors")

            # Remove departing altars
            if adv.altar_removals and self.shared_state:
                for altar_id in adv.altar_removals:
                    removed = self.shared_state.remove_altar(altar_id)
                    if removed:
                        logger.info(f"🏛️ Altar removed: {altar_id}")
                        print(f"   Altar removed: {altar_id}")
                    else:
                        logger.warning(f"Failed to remove altar '{altar_id}' - not found in current_altars")

            # NOTE: NPC departures are now handled in Entity Lifecycle Phase #2 (below)
            # This allows DM to decide which NPCs follow to new scene in ConversionDecisions

            # SECOND ENTITY LIFECYCLE PHASE - Manage entities for NEW scene
            print(f"\n{'='*80}")
            print(f"🔄 ENTITY LIFECYCLE PHASE #2 - New Scene Initialization")
            print(f"{'='*80}")
            logger.info("Running Entity Lifecycle Phase #2 for new scene after story advancement")

            # Build context for new scene
            new_scene_context = f"""Story just advanced to new location.

Location: {adv.location}
Situation: {adv.situation}
Void Level: {dm_agents[0].current_scenario.void_level if dm_agents and dm_agents[0].current_scenario else 'unknown'}

This is a FRESH scene. Spawn initial enemies/NPCs appropriate for this new location.
Consider:
- What threats are present in this location?
- What NPCs would naturally be here?
- What complications or opportunities exist?

NO conversions/morale checks needed (scene just started).
"""

            # Find DM agent
            dm_agent = None
            for agent in self.agents:
                if agent.agent_id.startswith('dm_'):
                    dm_agent = agent
                    break

            # Get spawn decisions from DM for new scene
            if dm_agent and hasattr(dm_agent, 'check_conversions'):
                try:
                    # Now properly async - can await check_conversions()
                    post_advancement_decisions = await dm_agent.check_conversions(
                        round_number=mechanics.current_round if mechanics else 0,
                        resolution_summary=new_scene_context
                    )

                    # Mechanical guard: preserve enemies when config says so
                    if not adv.clear_all_enemies:
                        if post_advancement_decisions.enemy_departures:
                            blocked = post_advancement_decisions.enemy_departures
                            logger.info(
                                f"Blocking {len(blocked)} enemy departures "
                                f"(clear_all_enemies=False): {blocked}"
                            )
                            post_advancement_decisions.enemy_departures = []

                    print(f"\n✅ New scene entities:")
                    print(f"   - NPC departures: {len(post_advancement_decisions.npc_departures)}")
                    print(f"   - Enemy departures: {len(post_advancement_decisions.enemy_departures)}")
                    print(f"   - Enemy spawns: {len(post_advancement_decisions.enemy_spawns)}")
                    print(f"   - NPC spawns: {len(post_advancement_decisions.npc_spawns)}")

                    # Process NPC departures first (remove NPCs that don't belong in new scene)
                    if post_advancement_decisions.npc_departures and self.shared_state:
                        for npc_identifier in post_advancement_decisions.npc_departures:
                            removed = self.shared_state.remove_npc(npc_identifier)
                            if removed:
                                logger.info(f"👤 NPC departed (post-advancement): {npc_identifier}")
                                print(f"\n✓ NPC doesn't follow to new scene: {npc_identifier}")
                            else:
                                logger.warning(f"Failed to remove NPC '{npc_identifier}' - not found")

                    # Process enemy departures (remove enemies that don't belong in new scene)
                    if post_advancement_decisions.enemy_departures and self.enemy_combat and self.enemy_combat.enabled:
                        for enemy_identifier in post_advancement_decisions.enemy_departures:
                            enemy = next((e for e in self.enemy_combat.enemy_agents
                                        if e.agent_id == enemy_identifier), None)
                            enemy_name = enemy.name if enemy else enemy_identifier

                            if enemy and enemy.is_active:
                                enemy.is_active = False
                                enemy.despawned_round = mechanics.current_round if mechanics else 0
                                logger.info(f"⚔️  Enemy departed (post-advancement): {enemy_identifier}")
                                print(f"\n✓ Enemy doesn't follow to new scene: {enemy_name}")
                            else:
                                logger.debug(f"Enemy '{enemy_identifier}' already inactive (auto-despawned) - skipping post-advancement departure")

                    # Process enemy spawns for new scene
                    if post_advancement_decisions.enemy_spawns and self.enemy_combat:
                        if not self.enemy_combat.enabled:
                            logger.info("Enabling enemy combat due to post-advancement enemy spawn")
                            self.enemy_combat.enabled = True

                        from .schemas.story_events import EnemySpawn
                        enemy_spawn_list = []
                        for spawn in post_advancement_decisions.enemy_spawns:
                            if isinstance(spawn, dict):
                                enemy_spawn_list.append(EnemySpawn(**spawn))
                            else:
                                enemy_spawn_list.append(spawn)

                        spawn_notifications = self.enemy_combat.spawn_from_structured(enemy_spawn_list)
                        for notification in spawn_notifications:
                            print(f"\n{notification}")
                            logger.info(f"Post-advancement enemy spawn: {notification}")

                    # Process NPC spawns for new scene
                    if post_advancement_decisions.npc_spawns and self.shared_state:
                        from .schemas.story_events import NPCSpawn
                        from .npc_agent import NPCAgent, next_npc_agent_id
                        import uuid

                        # Collect PC names to prevent NPC spawns that duplicate player characters
                        pc_names = set()
                        for pa in self.shared_state.player_agents:
                            if hasattr(pa, 'character_state') and hasattr(pa.character_state, 'name'):
                                pc_names.add(pa.character_state.name)

                        for npc_spawn in post_advancement_decisions.npc_spawns:
                            # Block NPC spawns that duplicate player character names
                            if npc_spawn.name in pc_names:
                                logger.warning(f"🚫 NPC spawn blocked: '{npc_spawn.name}' is a player character")
                                print(f"\n🚫 NPC spawn blocked: '{npc_spawn.name}' conflicts with player character name")
                                continue

                            # Check if NPC with same name already exists (prevent duplicates)
                            existing_npc = next((npc for npc in self.shared_state.npc_agents if npc.name == npc_spawn.name), None)
                            if existing_npc:
                                logger.info(f"NPC '{npc_spawn.name}' already exists ({existing_npc.agent_id}), skipping spawn")
                                print(f"\n⏭️  NPC '{npc_spawn.name}' already present in new scene, skipping spawn")
                                continue

                            npc = NPCAgent(
                                agent_id=next_npc_agent_id(
                                    npc_spawn.name, self.shared_state.issued_npc_ids),
                                name=npc_spawn.name,
                                entity_type=npc_spawn.entity_type,
                                threat_level=npc_spawn.threat_level,
                                disposition=npc_spawn.disposition,
                                description=npc_spawn.description,
                                faction=npc_spawn.faction,
                                health=npc_spawn.health,
                                max_health=npc_spawn.health,
                                soak=npc_spawn.soak,
                                void_score=0,
                                skills=npc_spawn.skills or {},
                                agent_prompt_logger=self.agent_prompt_logger if hasattr(self, 'agent_prompt_logger') else None,
                                llm_provider=self._get_npc_llm_provider()  # NPC LLM fallback: npcs -> enemies -> dm (Spec 11)
                            )

                            self.shared_state.npc_agents.append(npc)

                            if hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                                self.shared_state.target_id_mapper.register_npc(npc)

                            logger.info(f"Post-advancement NPC spawned: {npc.name} ({npc.agent_id})")
                            print(f"\n✓ NPC entered new scene: {npc.name} ({npc.entity_type}, {npc.disposition})")

                except Exception as e:
                    logger.warning(f"Post-advancement Entity Lifecycle Phase failed: {type(e).__name__}: {e}")
                    print(f"\n⚠️  Post-advancement spawn failed: {type(e).__name__}: {e}")

        # NOTE: Entity lifecycle is handled in TWO phases:
        # Phase 1 (before synthesis): Conversions, spawns for current scene
        # Phase 2 (after story advancement): Initial spawns for new scene
        # RoundSynthesis schema has NO entity management fields.

        # Dead PC cleanup: remove permanently dead PCs from player_agents and target maps
        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
            dead_pcs = [
                a for a in self.shared_state.player_agents
                if getattr(a, '_permanently_dead', False) or not a.is_alive
            ]
            for dead_pc in dead_pcs:
                self.shared_state.player_agents.remove(dead_pc)
                pc_name = dead_pc.character_state.name if hasattr(dead_pc, 'character_state') else dead_pc.agent_id
                logger.info(f"💀 Dead PC removed from active players: {pc_name} ({dead_pc.agent_id})")

                # Clean up target ID mapper
                target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                if target_id_mapper:
                    tid = target_id_mapper.reverse_map.pop(dead_pc.agent_id, None)
                    if tid and tid in target_id_mapper.target_id_map:
                        del target_id_mapper.target_id_map[tid]
                        logger.debug(f"Cleaned up target ID {tid} for dead PC {dead_pc.agent_id}")

        # 2. Handle scene pivot (minor room transitions)
        if synthesis.scene_pivot and synthesis.scene_pivot.should_pivot:
            pivot = synthesis.scene_pivot
            logger.info(f"Scene pivot: {pivot.new_room}")

            # Clear specific clocks if requested
            if pivot.clear_specific_clocks and mechanics:
                for clock_name in pivot.clear_specific_clocks:
                    if clock_name in mechanics.scene_clocks:
                        clock = mechanics.scene_clocks[clock_name]

                        # Log clock removal
                        if mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_event(
                                event_type="clock_removal",
                                data={
                                    "clock_name": clock_name,
                                    "current_ticks": clock.current,
                                    "maximum_ticks": clock.maximum,
                                    "description": clock.description,
                                    "removal_reason": "scene_pivot",
                                    "expiration_type": None,
                                    "filled": clock.filled,
                                    "consequence_triggered": False
                                },
                                round_num=mechanics.current_round
                            )
                        mechanics.clock_history.append({
                            'event_type': 'removed',
                            'clock_name': clock_name,
                            'round': mechanics.current_round,
                            'current': clock.current,
                            'max': clock.maximum,
                            'description': clock.description,
                            'removal_reason': 'scene_pivot'
                        })

                        del mechanics.scene_clocks[clock_name]
                        logger.info(f"Cleared clock: {clock_name}")

            # Spawn new clocks
            if pivot.new_clocks:
                self._spawn_new_clocks_structured(pivot.new_clocks)

            # Remove departing NPCs
            if pivot.npc_departures and self.shared_state:
                for npc_identifier in pivot.npc_departures:
                    removed = self.shared_state.remove_npc(npc_identifier)
                    if removed:
                        logger.info(f"👤 NPC departed (scene pivot): {npc_identifier}")
                        print(f"   NPC departed: {npc_identifier}")
                    else:
                        logger.warning(f"Failed to remove NPC '{npc_identifier}' during scene pivot - not found in npc_agents")

            # Remove departing enemies
            if pivot.enemy_departures and self.enemy_combat and self.enemy_combat.enabled:
                for enemy_identifier in pivot.enemy_departures:
                    enemy = next((e for e in self.enemy_combat.enemy_agents
                                if e.agent_id == enemy_identifier), None)
                    enemy_name = enemy.name if enemy else enemy_identifier

                    if enemy and enemy.is_active:
                        enemy.is_active = False
                        enemy.despawned_round = mechanics.current_round if mechanics else 0
                        logger.info(f"⚔️  Enemy departed (scene pivot): {enemy_identifier}")
                        print(f"   Enemy departed: {enemy_name}")
                    else:
                        logger.debug(f"Enemy '{enemy_identifier}' already inactive (auto-despawned) - skipping scene pivot departure")

            print(f"\n🔄 SCENE PIVOT")
            print(f"   New Area: {pivot.new_room}")
            print(f"   Situation: {pivot.situation_change}")

        # 5. Handle session end
        if synthesis.session_end:
            self._session_end_status = synthesis.session_end
            logger.info(f"Session ended: {synthesis.session_end} - {synthesis.session_end_reason}")

    def _process_legacy_markers(self, narration: str):
        """
        Legacy marker processing removed - use structured output instead.

        This method is deprecated. Use RoundSynthesis structured output instead:
        - Enemy spawns: RoundSynthesis.enemy_spawns
        - Story advancement: RoundSynthesis.story_advancement
        - New clocks: RoundSynthesis.story_advancement.new_clocks or scene_pivot.new_clocks
        - Session end: RoundSynthesis.session_end

        Args:
            narration: DM narration text (ignored)
        """
        from .outcome_parser import parse_session_end_marker

        logger.warning(
            "_process_legacy_markers() called but legacy marker parsing has been removed. "
            "DM should use RoundSynthesis structured output instead."
        )

        # Still handle session end marker (SESSION_END is not in RoundSynthesis yet)
        end_result = parse_session_end_marker(narration)
        if end_result['status'] != 'none':
            self._session_end_status = end_result['status']
            logger.info(f"DM declared session end: {end_result['status']}" +
                       (f" - {end_result['reason']}" if end_result['reason'] else ""))

        # Auto-despawn defeated enemies (legacy method still used for auto-despawn only)
        if self.enemy_combat.enabled:
            auto_despawn_notifications = self.enemy_combat.process_dm_narration(narration)
            for notification in auto_despawn_notifications:
                print(f"\n{notification}")

    async def _handle_dm_narration(self, message: Message):
        """Handle DM narration and check for control markers (structured or legacy)."""
        if message.type != MessageType.DM_NARRATION:
            return

        narration = message.payload.get('narration', '')
        self._last_dm_narration = narration

        # Check if this is a round synthesis completion
        if message.payload.get('is_round_synthesis', False):
            if message.payload.get('synthesis_failed'):
                # Fail-closed synthesis: the round's mechanics are applied and
                # checkpointed, but no valid narration exists. End the session
                # cleanly instead of stranding the gameplay loop.
                print("\n⛔ Round synthesis failed closed — ending session for manual recovery")
                self._session_end_status = 'aborted'
                self._end_reason = 'round_synthesis_failed'
                self._synthesis_complete.set()
                return
            logger.debug("Round synthesis received, processing...")

            # Check for structured synthesis (Phase 5: Pydantic AI migration)
            structured_synthesis_data = message.payload.get('structured_synthesis')
            structured_synthesis = None

            if structured_synthesis_data:
                # Deserialize dict back to Pydantic model
                if structured_synthesis_data.get('segments'):
                    from .outcome_pipeline import OutcomeRoundSynthesis
                    structured_synthesis = OutcomeRoundSynthesis(**structured_synthesis_data)
                else:
                    from .schemas.story_events import RoundSynthesis
                    structured_synthesis = RoundSynthesis(**structured_synthesis_data)
                # Process structured synthesis (no marker parsing!) - now async
                await self._process_structured_synthesis(structured_synthesis)
            else:
                # Legacy marker parsing path
                self._process_legacy_markers(narration)

            # Log round synthesis for narrative reconstruction (with structured data if available)
            mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
            round_num = message.payload.get('round', mechanics.current_round if mechanics else 0)
            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_synthesis(
                    round_num=round_num,
                    synthesis=narration,
                    structured_synthesis=structured_synthesis
                )

            # Collect synthesis for debrief context
            if narration and round_num is not None:
                self._round_synthesis_history.append((round_num, narration))

            # Signal completion AFTER all processing (including Entity Lifecycle #2) completes
            self._synthesis_complete.set()
            logger.debug("Round synthesis processing complete, signaling completion")


def _should_escalate_npc(entity_type: str, action_type: str) -> bool:
    """
    Determine if an NPC action should trigger escalation to enemy.

    Allied NPCs attacking enemies are fighting FOR players — don't escalate.
    Only non-attack actions never escalate.

    Args:
        entity_type: NPC entity type ("ally", "neutral", "prisoner")
        action_type: NPC action type ("attack", "dialogue", "flee", etc.)

    Returns:
        True if NPC should be escalated to enemy
    """
    if action_type != "attack":
        return False

    # Allied NPCs attacking enemies = helping players, don't escalate
    if entity_type == "ally":
        return False

    # Neutral/prisoner/other attacking = hostile intent, escalate
    return True


# Configuration example.
#
# This is what `--create-config` writes, so it is the first config most people
# ever see. It must therefore validate clean, carry the recommended research
# baseline, and use only canon factions/attributes — see
# tests/unit/test_example_config.py, which enforces exactly that.
#
# It is deliberately smoke-sized (max_turns=2): cheap to run, enough to prove the
# pipeline works end to end. Raise max_turns once a smoke run comes back clean.
EXAMPLE_CONFIG = {
    "session_name": "example_smoke_session",
    "max_turns": 2,
    "party_size": 2,
    "output_dir": "./multiagent_output",

    # Non-interactive: an interactive run opens an "[Observer]>" stdin prompt.
    "enable_human_interface": False,

    # The recommended research baseline (config_schema.recommended_overrides()).
    "tactical_module_enabled": True,
    "enemy_agents_enabled": True,
    "outcome_first_narration": True,
    "iff_enabled": True,
    "post_resolution_adjudication": "enforce",

    # Clocks must stay regressable — never a one-way ratchet.
    "starting_clocks": [
        {
            "name": "Cathedral Scrutiny",
            "current_ticks": 0,
            "max_ticks": 6,
            "description": "How closely Cathedral Confessors are watching the party.",
            "advance_meaning": "The party draws attention — a questioned ledger, a raised voice, a witnessed lie.",
            "regress_meaning": "The party allays suspicion — cooperating, producing papers, letting a scan run clean."
        }
    ],

    "agents": {
        "dm": {
            "llm": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 0.7
            }
        },
        "players": [
            {
                "name": "Vessel Sera Karsel",
                "faction": "Sovereign Nexus",
                "pronouns": "she/her",
                "llm": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "temperature": 0.7
                },
                "attributes": {
                    "Strength": 3, "Agility": 3, "Endurance": 3, "Dexterity": 4,
                    "Perception": 4, "Intelligence": 4, "Empathy": 5, "Willpower": 4
                },
                "skills": {"Astral Arts": 4, "Awareness": 3, "Charm": 3},
                "void": 1,
                "soulcredit": 3,
                "equipped_weapons": {"primary": "ritual_blade"},
                "personality": {
                    "description": "A Cathedral vessel who believes the ledger is mercy, "
                                   "and has never yet been asked to prove it."
                },
                "goals": ["Keep the rite lawful", "Bring everyone home judged, not hunted"]
            },
            {
                "name": "Dray Vusk",
                "faction": "Freeborn",
                "pronouns": "they/them",
                "llm": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "temperature": 0.7
                },
                "attributes": {
                    "Strength": 4, "Agility": 4, "Endurance": 4, "Dexterity": 3,
                    "Perception": 4, "Intelligence": 3, "Empathy": 3, "Willpower": 4
                },
                "skills": {"Brawl": 4, "Stealth": 3, "Guile": 3},
                "void": 2,
                "soulcredit": -1,
                "equipped_weapons": {"primary": "union_heavy_pistol"},
                "personality": {
                    "description": "Born outside the pods and unimpressed by the Codex; "
                                   "trusts people, not standing."
                },
                "goals": ["Owe nobody", "Get paid without signing anything"]
            }
        ]
    }
}
