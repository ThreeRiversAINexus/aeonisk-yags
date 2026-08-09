"""
Tactical Prompt Generation for Enemy Agents

Generates LLM prompts for autonomous enemy decision-making during combat.
Prompts include battlefield awareness, tactical options, threat analysis,
and structured output requirements.

Design Document: /content/experimental/Enemy Agent System - Design Document.md
Tactical Module: /content/experimental/Aeonisk - Tactical Module - v1.4.0.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

from typing import List, Dict, Any, Optional
import logging

from .enemy_agent import (
    EnemyAgent,
    Position,
    SharedIntel,
    TACTICAL_DOCTRINES,
    THREAT_PRIORITIES
)
from .prompt_loader import compose_sections

logger = logging.getLogger(__name__)


# =============================================================================
# STEALTH CONTEXT FOR ENEMY PROMPTS (Spec 05)
# =============================================================================

def _format_hidden_targets(hidden_pcs: List[Dict[str, Any]]) -> str:
    """
    Format hidden PC information for enemy tactical prompts.

    When PCs are hidden, enemies cannot directly target them but may know
    their last known position. This section informs the enemy AI about
    hidden targets and suggests using Scan to detect them.

    Args:
        hidden_pcs: List of dicts with 'name' and 'last_known_position' keys

    Returns:
        Formatted string section for enemy prompt, or empty string if no hidden PCs
    """
    if not hidden_pcs:
        return ""

    lines = ["\n**HIDDEN TARGETS (cannot be directly targeted):**"]
    for pc in hidden_pcs:
        name = pc.get('name', 'Unknown PC')
        last_pos = pc.get('last_known_position', 'Unknown')
        lines.append(f"- {name}: HIDDEN (last seen at {last_pos})")

    lines.append("\nUse 'Scan' as your minor_action to attempt detection.")
    return "\n".join(lines)


# =============================================================================
# PC ATTRIBUTE HELPERS — AIPlayerAgent stores name/faction on character_state
# =============================================================================

def _resolve_pc_name(pc) -> str:
    """Resolve PC name from character_state (AIPlayerAgent has no .name attr)."""
    if hasattr(pc, 'character_state') and hasattr(pc.character_state, 'name'):
        return pc.character_state.name
    return getattr(pc, 'name', 'Unknown PC')


def _resolve_pc_faction(pc) -> str:
    """Resolve PC faction from character_state."""
    if hasattr(pc, 'character_state') and hasattr(pc.character_state, 'faction'):
        return pc.character_state.faction
    return getattr(pc, 'faction', 'Unknown')


# =============================================================================
# SECTION SELECTION & VARIABLE COMPUTATION
# =============================================================================

def _get_required_sections(
    structured: bool = False,
    has_history: bool = False,
    has_character: bool = False,
    has_intel: bool = False,
    has_narrations: bool = False,
    has_declarations: bool = False,
    engagement_stance: str = 'lethal',
) -> List[str]:
    """
    Determine which enemy.yaml sections to include based on enemy state.

    Args:
        structured: True for structured output mode (EnemyDecision schema),
                    False for text declaration format.
        has_history: Whether enemy has situation history from previous rounds.
        has_character: Whether enemy has a character_brief personality.
        has_intel: Whether shared intel has recent data.
        has_narrations: Whether recent narrations are available.
        has_declarations: Whether player declared actions exist this round.
        engagement_stance: 'lethal', 'capture', or 'adaptive'.

    Returns:
        Ordered list of section names to compose.
    """
    sections = ['header', 'status']

    if has_history:
        sections.append('situation_history')
    if has_character:
        sections.append('character')

    sections.append('faction_context')

    if has_narrations:
        sections.append('recent_outcomes')
    if has_declarations:
        sections.append('declared_actions')

    sections.append('doctrine')

    if engagement_stance == 'capture':
        sections.append('engagement_stance_capture')
    elif engagement_stance == 'adaptive':
        sections.append('engagement_stance_adaptive')

    sections.extend(['battlefield', 'tactical_options', 'tactical_analysis'])

    if has_intel:
        sections.append('shared_intel')

    sections.append('retreat_assessment')

    if structured:
        sections.append('structured_decision_guidance')
    else:
        sections.append('declaration_requirements')

    sections.append('footer')
    return sections


def _compute_enemy_variables(
    enemy: EnemyAgent,
    player_agents: List[Any],
    enemy_agents: List[EnemyAgent],
    shared_intel: Optional[SharedIntel] = None,
    available_tokens: Optional[List[str]] = None,
    current_round: int = 0,
    target_id_mapper=None,
    free_targeting: bool = False,
    recent_narrations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compute all template variables for enemy.yaml sections.

    Simple values (enemy_name, health, etc.) are extracted directly.
    Dynamic content (_content variables) are pre-computed by existing
    _format_*() functions and passed through as strings.

    Returns:
        Dict of variable name → value for template substitution.
    """
    from .faction_utils import get_faction_description, get_faction_stance

    # --- Simple template variables ---
    health_pct = enemy.get_health_percentage()
    if health_pct >= 75:
        health_status = "Healthy"
    elif health_pct >= 50:
        health_status = "Wounded"
    elif health_pct >= 25:
        health_status = "Bloodied"
    else:
        health_status = "CRITICAL"

    if enemy.wounds >= 4:
        wound_status = "(HEAVY WOUNDS -15)"
    elif enemy.wounds >= 2:
        wound_status = "(WOUNDED -5)"
    else:
        wound_status = ""

    void_status = _get_void_status(enemy.void_score)

    status_effects_display = ""
    if enemy.status_effects:
        status_effects_display = f"Status Effects: {', '.join(enemy.status_effects)}"

    # Doctrine lookups
    doctrine = TACTICAL_DOCTRINES.get(enemy.tactics, {})
    faction = getattr(enemy, 'faction', 'Unknown')

    variables = {
        # Header
        'enemy_name': enemy.name,
        # Status
        'template': enemy.template.upper(),
        'health': enemy.health,
        'max_health': enemy.max_health,
        'health_pct': health_pct,
        'health_status': health_status,
        'wounds': enemy.wounds,
        'wound_status': wound_status,
        'stuns': enemy.stuns,
        'void_score': enemy.void_score,
        'void_status': void_status,
        'position': enemy.position,
        'initiative': enemy.initiative,
        'stance': enemy.stance,
        'status_effects_display': status_effects_display,
        # Character
        'character_brief': getattr(enemy, 'character_brief', ''),
        # Faction context
        'faction': faction,
        'faction_stance': get_faction_stance(faction),
        'faction_description': get_faction_description(faction),
        # Doctrine
        'tactics': enemy.tactics,
        'doctrine_description': doctrine.get('description', 'Unknown tactics'),
        'doctrine_preferred_range': doctrine.get('preferred_range', 'Any'),
        'threat_priority': enemy.threat_priority,
        'threat_priority_description': THREAT_PRIORITIES.get(enemy.threat_priority, 'Unknown'),
        'retreat_threshold_pct': int(enemy.retreat_threshold * 100),
    }

    # --- Dynamic content (pre-computed by existing formatters) ---

    # Situation history
    situation_history = getattr(enemy, '_situation_history', None)
    if situation_history:
        variables['situation_history_content'] = _format_situation_history(situation_history)
    else:
        variables['situation_history_content'] = ''

    # Recent outcomes
    if recent_narrations:
        variables['recent_outcomes_content'] = _format_recent_outcomes(recent_narrations)
    else:
        variables['recent_outcomes_content'] = ''

    # Declared actions
    declared = _format_declared_actions(player_agents)
    variables['declared_actions_content'] = declared if declared else ''

    # Battlefield (complex conditional logic)
    variables['battlefield_content'] = _format_battlefield(
        enemy, player_agents, enemy_agents,
        available_tokens or [], target_id_mapper, free_targeting
    )

    # Tactical options
    variables['tactical_options_content'] = _format_tactical_options(enemy)

    # Tactical analysis
    variables['tactical_analysis_content'] = _format_tactical_analysis(enemy, player_agents)

    # Shared intel
    if shared_intel:
        intel = _format_shared_intel(shared_intel, current_round)
        variables['shared_intel_content'] = intel if intel else ''
    else:
        variables['shared_intel_content'] = ''

    # Retreat assessment
    variables['retreat_assessment_content'] = _format_retreat_assessment(enemy)

    return variables


# =============================================================================
# PROMPT GENERATION
# =============================================================================

def generate_tactical_prompt(
    enemy: EnemyAgent,
    player_agents: List[Any],  # List of PlayerAgent instances
    enemy_agents: List[EnemyAgent],
    shared_intel: SharedIntel,
    available_tokens: List[str],
    current_round: int,
    target_id_mapper=None,
    free_targeting: bool = False,
    recent_narrations: List[str] = None
) -> str:
    """
    Generate complete tactical prompt for enemy agent.

    Computes variables from enemy state, selects required YAML sections,
    and composes them via prompt_loader.compose_sections().

    Args:
        enemy: The enemy agent making decisions
        player_agents: List of PC agents (targets)
        enemy_agents: List of other enemy agents (allies)
        shared_intel: Shared intelligence pool
        available_tokens: Unclaimed tactical tokens
        current_round: Current combat round
        target_id_mapper: Optional target ID mapper for free targeting mode
        free_targeting: Whether to use unified combatant list (no ally/enemy labels)
        recent_narrations: Recent action resolution narrations (from previous rounds)

    Returns:
        Complete tactical prompt string
    """
    variables = _compute_enemy_variables(
        enemy=enemy,
        player_agents=player_agents,
        enemy_agents=enemy_agents,
        shared_intel=shared_intel,
        available_tokens=available_tokens,
        current_round=current_round,
        target_id_mapper=target_id_mapper,
        free_targeting=free_targeting,
        recent_narrations=recent_narrations,
    )

    # Determine conditional flags
    situation_history = getattr(enemy, '_situation_history', None)
    engagement_stance = getattr(enemy, 'engagement_stance', 'lethal')

    has_intel = False
    if shared_intel:
        recent_intel = shared_intel.get_recent_intel(current_round, lookback=2)
        has_intel = bool(recent_intel)

    section_names = _get_required_sections(
        structured=False,
        has_history=bool(situation_history),
        has_character=bool(getattr(enemy, 'character_brief', '')),
        has_intel=has_intel,
        has_narrations=bool(recent_narrations),
        has_declarations=bool(variables['declared_actions_content']),
        engagement_stance=engagement_stance,
    )

    loaded = compose_sections('enemy', section_names, variables=variables)
    return loaded.content


def generate_tactical_prompt_structured(
    enemy: EnemyAgent,
    player_agents: List[Any],
    enemy_agents: List[EnemyAgent],
    shared_intel: SharedIntel,
    available_tokens: List[str],
    current_round: int,
    target_id_mapper=None,
    free_targeting: bool = False,
    recent_narrations: List[str] = None
) -> str:
    """
    Generate tactical prompt for structured output mode (EnemyDecision schema).

    Same as generate_tactical_prompt() but uses structured_decision_guidance
    instead of declaration_requirements.

    Args:
        Same as generate_tactical_prompt()

    Returns:
        Tactical prompt suitable for structured output mode
    """
    variables = _compute_enemy_variables(
        enemy=enemy,
        player_agents=player_agents,
        enemy_agents=enemy_agents,
        shared_intel=shared_intel,
        available_tokens=available_tokens,
        current_round=current_round,
        target_id_mapper=target_id_mapper,
        free_targeting=free_targeting,
        recent_narrations=recent_narrations,
    )

    situation_history = getattr(enemy, '_situation_history', None)
    engagement_stance = getattr(enemy, 'engagement_stance', 'lethal')

    has_intel = False
    if shared_intel:
        recent_intel = shared_intel.get_recent_intel(current_round, lookback=2)
        has_intel = bool(recent_intel)

    section_names = _get_required_sections(
        structured=True,
        has_history=bool(situation_history),
        has_character=bool(getattr(enemy, 'character_brief', '')),
        has_intel=has_intel,
        has_narrations=bool(recent_narrations),
        has_declarations=bool(variables['declared_actions_content']),
        engagement_stance=engagement_stance,
    )

    loaded = compose_sections('enemy', section_names, variables=variables)
    return loaded.content


# =============================================================================
# SECTION FORMATTERS
# =============================================================================

def _format_header(enemy: EnemyAgent) -> str:
    """Format prompt header."""
    return f"""# TACTICAL COMBAT AGENT: {enemy.name}

You are an autonomous enemy combatant in tactical combat. Make optimal tactical
decisions based on battlefield conditions and your combat doctrine."""


def _format_status(enemy: EnemyAgent) -> str:
    """Format agent status section."""
    health_pct = enemy.get_health_percentage()

    # Health status indicator
    if health_pct >= 75:
        health_status = "Healthy"
    elif health_pct >= 50:
        health_status = "Wounded"
    elif health_pct >= 25:
        health_status = "Bloodied"
    else:
        health_status = "CRITICAL"

    # Wound status
    if enemy.wounds >= 4:
        wound_status = "(HEAVY WOUNDS -15)"
    elif enemy.wounds >= 2:
        wound_status = "(WOUNDED -5)"
    else:
        wound_status = ""

    # Void status
    void_status = _get_void_status(enemy.void_score)

    status = f"""## YOUR STATUS
{"=" * 60}
Unit Type: {enemy.template.upper()}
Health: {enemy.health}/{enemy.max_health} ({health_pct}%) - {health_status}
Wounds: {enemy.wounds} {wound_status}
Stuns: {enemy.stuns}
Void Score: {enemy.void_score}/10 {void_status}
Position: {enemy.position}
Initiative: {enemy.initiative}
Stance: {enemy.stance}"""

    if enemy.status_effects:
        status += f"\nStatus Effects: {', '.join(enemy.status_effects)}"

    return status


def _get_void_status(void_score: int) -> str:
    """Get void corruption status description."""
    if void_score >= 10:
        return "(VOID POSSESSED - UNCONTROLLED)"
    elif void_score >= 8:
        return "(HEAVILY CORRUPTED - abilities locked)"
    elif void_score >= 5:
        return "(Corrupted -2 to Empathy checks)"
    elif void_score >= 3:
        return "(Minor corruption)"
    else:
        return "(Stable)"


def _format_recent_outcomes(recent_narrations: List[str]) -> str:
    """Format recent action outcomes section."""
    section = """## 📖 RECENT ACTION OUTCOMES
{"=" * 60}
What just happened in the previous round:

"""
    for i, narration in enumerate(recent_narrations, 1):
        section += f"{i}. {narration}\n"

    return section


def _format_doctrine(enemy: EnemyAgent) -> str:
    """Format combat doctrine section."""
    doctrine = TACTICAL_DOCTRINES.get(enemy.tactics, {})

    return f"""## COMBAT DOCTRINE
{"=" * 60}
Tactics: {enemy.tactics}
Description: {doctrine.get('description', 'Unknown tactics')}
Preferred Range: {doctrine.get('preferred_range', 'Any')}
Threat Priority: {enemy.threat_priority}
Priority Description: {THREAT_PRIORITIES.get(enemy.threat_priority, 'Unknown')}
Retreat Threshold: {int(enemy.retreat_threshold * 100)}% health"""


def _format_battlefield(
    enemy: EnemyAgent,
    player_agents: List[Any],
    enemy_agents: List[EnemyAgent],
    available_tokens: List[str],
    target_id_mapper=None,
    free_targeting: bool = False
) -> str:
    """Format battlefield situation section."""
    from .faction_utils import are_factions_allied

    section = f"""## BATTLEFIELD SITUATION
{"=" * 60}"""

    if free_targeting and target_id_mapper:
        # FREE TARGETING MODE: Unified combatant list with range info
        section += "\n\n### Combatants in Combat Zone:"

        combatants = []

        # Add all PCs with range from this enemy
        for pc in player_agents:
            tgt_id = target_id_mapper.get_target_id(getattr(pc, 'agent_id', None))
            if tgt_id:
                pc_name = _resolve_pc_name(pc)
                pc_faction = _resolve_pc_faction(pc)
                pc_position = str(getattr(pc, 'position', 'Unknown'))

                # Health is stored directly on AIPlayerAgent, not on CharacterState
                pc_health = getattr(pc, 'health', 0)
                pc_max_health = getattr(pc, 'max_health', 0)

                # Calculate range from this enemy to the PC (Spec 09)
                range_str = ""
                try:
                    pc_tac_pos = Position.from_string(pc_position)
                    range_name, range_penalty = enemy.position.calculate_range(pc_tac_pos)
                    if range_penalty == 0:
                        range_str = f" | Range: {range_name} (no penalty)"
                    else:
                        range_str = f" | Range: {range_name} ({range_penalty:+d})"
                except Exception as e:
                    logger.warning(f"range unavailable for the prompt; the agent will plan without it and the fallback band looks ordinary in the output ({type(e).__name__}: {e})")
                    range_str = " | Range: Unknown"

                combatants.append(f"- [{tgt_id}] {pc_name} ({pc_faction}) | {pc_position}{range_str} | {pc_health}/{pc_max_health} HP")

        # Add all other active enemies (including self) with range
        for other_enemy in enemy_agents:
            if other_enemy.is_active:
                tgt_id = target_id_mapper.get_target_id(other_enemy.agent_id)
                if tgt_id:
                    enemy_faction = getattr(other_enemy, 'faction', 'Unknown')

                    # Calculate range from this enemy to the other combatant (Spec 09)
                    range_str = ""
                    try:
                        range_name, range_penalty = enemy.position.calculate_range(other_enemy.position)
                        if range_penalty == 0:
                            range_str = f" | Range: {range_name} (no penalty)"
                        else:
                            range_str = f" | Range: {range_name} ({range_penalty:+d})"
                    except Exception as e:
                        logger.warning(f"range unavailable for the prompt; the agent will plan without it and the fallback band looks ordinary in the output ({type(e).__name__}: {e})")
                        range_str = " | Range: Unknown"

                    combatants.append(f"- [{tgt_id}] {other_enemy.name} ({enemy_faction}) | {other_enemy.position}{range_str} | {other_enemy.health}/{other_enemy.max_health} HP")

        section += "\n" + "\n".join(combatants)

        section += f"\n\n**YOUR UNIT**: {enemy.name}"
        section += f"\n**YOUR FACTION**: {enemy.faction}"
        section += "\n\n⚠️  **CRITICAL TARGETING INSTRUCTIONS** ⚠️"
        section += "\n**MECHANICAL TARGETING (for target/defence_token fields):**"
        section += "\n- Each person has a unique ID in brackets: [tgt_XXXX]"
        section += "\n- You MUST use the target ID in mechanical fields (target, defence_token)"
        section += "\n- ✅ CORRECT: target='tgt_7a3f'"
        section += "\n- ❌ WRONG: target='Kiran Voss' (this will FAIL!)"
        section += "\n\n**NARRATIVE TEXT (for tactical_reasoning/shared_intel):**"
        section += "\n- Use CHARACTER NAMES in your tactical reasoning and intel sharing"
        section += "\n- ✅ CORRECT tactical_reasoning: 'Targeting Kiran Voss because they are wounded...'"
        section += "\n- ❌ WRONG tactical_reasoning: 'Targeting tgt_7a3f because they are wounded...'"
        section += f"\n\n**How to decide who to target:**"
        section += "\n1. Check each combatant's FACTION shown in parentheses"
        section += f"\n2. Your faction is {enemy.faction} — prioritize hostile factions, avoid attacking allies"
        section += "\n3. Use the target ID (in brackets) in mechanical fields, character name in narrative"
        section += "\n\n⚠️  **WARNING**: You can target ANYONE on this list. Choose wisely based on faction!"

    else:
        # STANDARD MODE: Show all contacts without relationship labels
        section += "\n\n### Detected Contacts:"

        # Format PC targets (skip if Unseen)
        pc_targets_shown = 0
        for pc in player_agents:
            pc_info = _format_pc_target(enemy, pc)
            if pc_info:  # Only add if not None (Unseen condition returns None)
                section += "\n" + pc_info
                pc_targets_shown += 1

        if pc_targets_shown == 0:
            section += "\nNo visible targets detected. They may be using stealth or concealment."

        # Show other enemy agents (without ally/hostile labels)
        other_enemies = []
        for other_enemy in enemy_agents:
            if other_enemy.agent_id == enemy.agent_id or not other_enemy.is_active:
                continue
            other_enemies.append(other_enemy)

        if other_enemies:
            section += "\n\n### Other Forces:"
            for other in other_enemies:
                section += "\n" + _format_other_enemy(enemy, other)

    # Format tactical tokens (same for both modes)
    if available_tokens:
        section += "\n\n### Tactical Tokens Available:"
        section += "\n" + ", ".join(available_tokens)
    else:
        section += "\n\n### Tactical Tokens Available:\nNone (all claimed)"

    return section


def _format_pc_target(enemy: EnemyAgent, pc: Any) -> Optional[str]:
    """
    Format individual PC target information.

    Returns None if PC has Unseen condition (can't be targeted).
    """
    # Check if PC has Unseen condition (prevents targeting)
    try:
        pc_conditions = getattr(pc, 'conditions', [])
        for condition in pc_conditions:
            if hasattr(condition, 'type') and condition.type == 'Unseen':
                # PC is unseen - don't show as targetable
                return None
            elif isinstance(condition, dict) and condition.get('type') == 'Unseen':
                return None
    except (AttributeError, TypeError, KeyError):
        pass  # No conditions or error checking

    # Calculate range
    try:
        pc_position = Position.from_string(str(pc.position if hasattr(pc, 'position') else "Near-PC"))
        range_name, range_penalty = enemy.position.calculate_range(pc_position)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"range calculation failed; falling back to no penalty. Zeroing this silently improves every attack and the fallback band looks ordinary in the log ({type(e).__name__}: {e})")
        range_name, range_penalty = "Unknown", 0

    # Get PC health estimate (if available)
    try:
        pc_health = getattr(pc, 'health', 100)
        pc_max_health = getattr(pc, 'max_health', 100)
        health_pct = int((pc_health / pc_max_health) * 100) if pc_max_health > 0 else 100

        if health_pct >= 75:
            health_str = "~100% (healthy)"
        elif health_pct >= 50:
            health_str = f"~{health_pct}% (wounded)"
        elif health_pct >= 25:
            health_str = f"~{health_pct}% (bloodied)"
        else:
            health_str = f"~{health_pct}% (CRITICAL)"
    except (AttributeError, TypeError, ZeroDivisionError):
        health_str = "Unknown"

    # Check if PC is watching this enemy
    try:
        pc_defence_token = getattr(pc, 'defence_token', None)
        is_watching = pc_defence_token == enemy.agent_id
    except (AttributeError, TypeError, KeyError):
        is_watching = False

    watching_str = "WATCHING YOU (-2 to hit them)" if is_watching else "NOT watching you (+2 Flanking if you attack)"

    # Get PC weapons
    try:
        pc_weapons = getattr(pc, 'weapons', [])
        if pc_weapons:
            weapon_names = [w.name for w in pc_weapons[:2]]  # First 2 weapons
            weapons_str = ", ".join(weapon_names)
        else:
            weapons_str = "Unknown"
    except (AttributeError, TypeError, KeyError):
        weapons_str = "Unknown"

    # Get PC name and faction
    pc_name = _resolve_pc_name(pc)
    pc_faction = _resolve_pc_faction(pc)
    pc_id = getattr(pc, 'agent_id', 'unknown')

    # Threat level assessment
    threat_level = _assess_threat_level(enemy, pc, range_name, is_watching)

    return f"""- {pc_name} [{pc_id}] ({pc_faction})
  Position: {pc_position} ({range_name.upper()} RANGE, {range_penalty} penalty)
  Health: {health_str}
  Defence Token: {watching_str}
  Weapons: {weapons_str}
  Threat Level: {threat_level}"""


def _assess_threat_level(enemy: EnemyAgent, pc: Any, range_name: str, is_watching: bool) -> str:
    """Assess threat level of a PC target."""
    # Simple heuristic-based threat assessment
    threat_score = 0

    # Range factor
    if range_name == "Melee" or range_name == "Engaged":
        threat_score += 3  # Close = dangerous
    elif range_name == "Near":
        threat_score += 2
    elif range_name == "Far":
        threat_score += 1

    # Watching factor
    if is_watching:
        threat_score += 2  # They're ready for us
    else:
        threat_score -= 1  # Distracted

    # Health factor (if available)
    try:
        pc_health = getattr(pc, 'health', 100)
        pc_max_health = getattr(pc, 'max_health', 100)
        health_pct = (pc_health / pc_max_health) if pc_max_health > 0 else 1.0

        if health_pct < 0.3:
            threat_score -= 2  # Weakened
    except (AttributeError, TypeError, KeyError):
        # Threat scoring is heuristic; a missing field leaves the score unadjusted.
        pass

    # Map to threat level
    if threat_score >= 5:
        return "EXTREME"
    elif threat_score >= 3:
        return "HIGH"
    elif threat_score >= 1:
        return "MEDIUM"
    else:
        return "LOW"


def _format_other_enemy(observer: EnemyAgent, other: EnemyAgent) -> str:
    """Format another enemy agent's information without relationship labels."""
    # Calculate range
    try:
        range_name, range_penalty = observer.position.calculate_range(other.position)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"range calculation failed; falling back to no penalty. Zeroing this silently improves every attack and the fallback band looks ordinary in the log ({type(e).__name__}: {e})")
        range_name, range_penalty = "Unknown", 0

    health_pct = other.get_health_percentage()

    if health_pct >= 75:
        health_str = "~100% (healthy)"
    elif health_pct >= 50:
        health_str = f"~{health_pct}% (wounded)"
    elif health_pct >= 25:
        health_str = f"~{health_pct}% (bloodied)"
    else:
        health_str = f"~{health_pct}% (CRITICAL)"

    return f"""- {other.name} (Faction: {other.faction})
  Position: {other.position} (Range: {range_name}, Penalty: {range_penalty})
  Health: {health_str}
  Tactics: {other.tactics}"""


def _format_tactical_options(enemy: EnemyAgent) -> str:
    """Format tactical options section."""
    section = f"""## TACTICAL OPTIONS
{"=" * 60}

### Movement Options:
Current Position: {enemy.position}

- **Minor Action:** Shift 1 ring"""

    # Shift toward center
    toward = enemy.position.shift_toward_center()
    if toward:
        section += f"\n  → Toward center: {toward}"

    # Shift away from center
    away = enemy.position.shift_away_from_center()
    if away:
        section += f"\n  → Away from center: {away}"

    section += "\n\n- **Major Action:** Shift 2 rings (skip one ring)"

    # Push through
    opposite_side = "PC" if enemy.position.side == "Enemy" else "Enemy"
    section += f"\n\n- **Major Action:** Push Through to {opposite_side} hemisphere (RISKY - isolated)"

    # Disengage if needed
    section += "\n\n- **Minor Action:** Disengage (if at Melee range with hostiles, Athletics DC 20)"

    # Weapon options
    section += "\n\n### Attack Options:"

    for weapon in enemy.weapons:
        section += "\n" + _format_weapon_option(weapon, enemy)

    # Special abilities
    if enemy.special_abilities:
        section += "\n\n### Special Abilities:"
        for ability in enemy.special_abilities:
            section += "\n" + _format_ability_option(ability, enemy)

    # Defence Token
    section += f"""

### Defence Token Allocation:
CRITICAL: You must allocate your Defence Token to ONE PC you're watching.
- PC with your token: -2 to hit you
- PCs without your token: +2 Flanking bonus vs you

Currently allocated to: {enemy.defence_token or "NONE (all PCs get Flanking +2!)"}"""

    return section


def _format_weapon_option(weapon, enemy: EnemyAgent) -> str:
    """Format weapon option."""
    # Calculate damage
    strength = enemy.attributes.get('Strength', 3)
    base_damage = strength + weapon.damage
    total_damage = base_damage

    # Effective ranges
    if weapon.is_ranged:
        ranges = f"Effective at {weapon.short_range}m-{weapon.long_range}m"
    else:
        ranges = "Melee only" if weapon.reach == 0 else f"Reach {weapon.reach}"

    # Ammo
    ammo_str = ""
    if weapon.is_ranged and weapon.capacity > 0:
        current_ammo = enemy.ammo.get(weapon.name, weapon.capacity)
        ammo_str = f"\n   Ammo: {current_ammo}/{weapon.capacity}"
        if current_ammo == 0:
            ammo_str += " (EMPTY - need reload)"

    # Special properties
    special_str = ""
    if weapon.special:
        special_str = f"\n   Special: {', '.join(weapon.special)}"

    # Annotate stun damage type for clarity
    damage_type_str = weapon.damage_type
    if weapon.damage_type == "stun":
        damage_type_str = "stun (NON-LETHAL — incapacitates without killing)"
    elif weapon.damage_type == "mixed":
        damage_type_str = "mixed (lethal + stun components)"

    return f"""- **{weapon.name}** ({weapon.skill})
   Range: {ranges}
   Damage: {total_damage} + d20 (Str {strength} + Weapon {weapon.damage})
   Attack Bonus: {weapon.attack:+d}
   Damage Type: {damage_type_str}{ammo_str}{special_str}"""


def _format_ability_option(ability: str, enemy: EnemyAgent) -> str:
    """Format special ability option."""
    if ability == "void_surge":
        can_use = enemy.can_use_void_surge()
        status = "AVAILABLE" if can_use else f"LOCKED (Void {enemy.void_score} ≥ 8)"

        return f"""- **Void Surge** - Status: {status}
   Effect: +4 damage, auto-Shock on hit, +1 Stun to you, +1 Void
   Current Void: {enemy.void_score}/10"""

    # TODO: Implement AoE grenade mechanics
    # Grenades require:
    # - Area-of-effect damage calculation
    # - Friendly fire detection (combatants in blast zone)
    # - Ring-side location targeting system
    # - Agility save vs DC mechanic for affected combatants
    # - Integration with DM narration for blast description
    # elif ability == "grenade":
    #     has_grenade = enemy.ammo.get("Frag Grenade", 0) > 0
    #     status = "AVAILABLE" if has_grenade else "NONE REMAINING"
    #
    #     return f"""- **Grenade** - Status: {status}
    #    Type: Area Effect (targets ring-side location)
    #    Damage: DC 20 Agility save, 2d6 damage
    #    WARNING: Friendly fire if allies in blast zone
    #    Example targets: Near-Enemy, Far-PC, etc."""

    elif ability == "suppress":
        return """- **Suppress** (Major, requires RoF ≥ 3)
   Effect: On hit, target must Dive (shift 1 band, lose Cover) OR Hunker Down (-4 to attacks/defense)"""

    elif ability == "charge":
        return """- **Charge** (Major)
   Effect: Shift directly into Engaged/Melee with target, +2 damage, -2 defense until next turn"""

    else:
        return f"- **{ability}** (special ability)"


def _format_tactical_analysis(enemy: EnemyAgent, player_agents: List[Any]) -> str:
    """Format tactical analysis section."""
    section = f"""## TACTICAL ANALYSIS
{"=" * 60}

### Range Analysis:"""

    # Analyze ranges to all PCs
    range_counts = {"Melee": [], "Engaged": [], "Near": [], "Far": [], "Extreme": []}

    for pc in player_agents:
        try:
            pc_position = Position.from_string(str(getattr(pc, 'position', "Near-PC")))
            range_name, _ = enemy.position.calculate_range(pc_position)
            pc_name = _resolve_pc_name(pc)
            range_counts[range_name].append(pc_name)
        except (AttributeError, TypeError, KeyError, ValueError):
            # Range grouping is prompt garnish; an unplaceable PC is simply omitted.
            pass

    for range_name, pcs in range_counts.items():
        if pcs:
            section += f"\n- {range_name.upper()} RANGE: {', '.join(pcs)}"

    # Doctrine alignment
    preferred_range = TACTICAL_DOCTRINES.get(enemy.tactics, {}).get('preferred_range', 'Any')
    section += f"\n\nDoctrine '{enemy.tactics}' prefers: {preferred_range} range"

    # Movement guidance
    section += "\n\n### Position Selection Guidance:"
    section += f"\nYour current position: **{enemy.position}**"
    section += "\n\n**When choosing TARGET for Shift/Shift_2 actions:**"
    section += "\n- Match your doctrine's preferred range (see above)"
    section += "\n- Consider where PCs are located (see Range Analysis)"
    section += "\n- Available positions: Engaged, Near-PC, Far-PC, Extreme-PC, Near-Enemy, Far-Enemy, Extreme-Enemy"
    section += f"\n- Example: If PCs are at Far-PC and you prefer Near range → TARGET: Near-PC"
    section += f"\n- Example: If PCs are at Near-Enemy and you prefer Extreme range → TARGET: Far-Enemy or Extreme-Enemy"

    # Threat assessment
    section += "\n\n### Threat Assessment:"
    section += f"\nBased on priority '{enemy.threat_priority}':\n"

    # Sort targets by threat
    threat_order = []
    for pc in player_agents:
        pc_name = _resolve_pc_name(pc)
        try:
            pc_position = Position.from_string(str(getattr(pc, 'position', "Near-PC")))
            range_name, _ = enemy.position.calculate_range(pc_position)

            pc_defence_token = getattr(pc, 'defence_token', None)
            is_watching = pc_defence_token == enemy.agent_id

            threat = _assess_threat_level(enemy, pc, range_name, is_watching)
            threat_order.append((threat, pc_name, range_name, is_watching))
        except (AttributeError, TypeError, KeyError):
            # Threat ordering is prompt garnish; an unscorable PC is simply omitted.
            pass

    # Sort by threat level
    threat_map = {"EXTREME": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    threat_order.sort(key=lambda x: threat_map.get(x[0], 0), reverse=True)

    for i, (threat, pc_name, range_name, is_watching) in enumerate(threat_order[:3]):  # Top 3
        priority_label = ["PRIMARY", "SECONDARY", "TERTIARY"][i]
        watching_note = "(watching you -2)" if is_watching else "(NOT watching +2 Flanking)"
        section += f"\n{i+1}. {priority_label} THREAT: {pc_name} - {threat} ({range_name} range, {watching_note})"

    return section


def _format_shared_intel(shared_intel: SharedIntel, current_round: int) -> str:
    """Format shared intelligence section."""
    recent_intel = shared_intel.get_recent_intel(current_round, lookback=2)

    if not recent_intel:
        return ""

    section = f"""## SHARED TACTICAL INTEL
{"=" * 60}
Intelligence from allied enemy agents:

"""
    section += "\n".join(f"- {intel}" for intel in recent_intel)

    return section


def _format_faction_context(enemy: EnemyAgent) -> str:
    """Format faction identity section for tactical prompt."""
    from .faction_utils import get_faction_description, get_faction_stance
    faction = getattr(enemy, 'faction', 'Unknown')
    stance = get_faction_stance(faction)
    description = get_faction_description(faction)

    return f"""## FACTION IDENTITY
{"=" * 60}
Your Faction: {faction}
Stance: {stance}
About: {description}"""


def _format_iff_context(faction_name: str) -> str:
    """Format IFF (Identification Friend or Foe) reasoning context.

    Tells the enemy its own faction and instructs it to reason about
    allegiance from faction names rather than system-provided labels.

    Args:
        faction_name: The enemy's faction name (e.g. "ACG", "Freeborn")

    Returns:
        Formatted IFF context section for the enemy prompt
    """
    return f"""## IFF (IDENTIFICATION FRIEND OR FOE)
{"=" * 60}
Your Faction: {faction_name}
You recognize fellow {faction_name} operatives as allies.

## Allegiance
The DETECTED CONTACTS list shows all visible contacts with their faction.
You must determine who is hostile, neutral, or friendly based on faction.
The system will NOT tell you who is an ally or enemy -- you must reason
from your knowledge of faction relationships.

## Communication
Use shared_intel + intel_recipients to communicate with contacts you
believe are allies. Specify their target IDs (tgt_xxxx) as recipients.
WARNING: If you share intel with the wrong contact, they will receive it."""


def _format_character(enemy: EnemyAgent) -> str:
    """Format character brief section for personality injection."""
    character_brief = getattr(enemy, 'character_brief', '')
    if not character_brief:
        return ""

    return f"""## CHARACTER
{"=" * 60}
Your personality: {character_brief}

Let this guide your decision-making — how you fight, whether you talk, when you wait."""


def _format_situation_history(history: list) -> str:
    """
    Format recent round synthesis history for situational awareness.

    Args:
        history: List of (round_num, synthesis_text) tuples
    """
    if not history:
        return ""

    section = f"""## SITUATION HISTORY
{"=" * 60}
What has been happening (most recent first):
"""
    # Show most recent first, max 3 rounds
    for round_num, text in reversed(history[-3:]):
        # Truncate each synthesis to ~300 chars
        truncated = text[:300] + "..." if len(text) > 300 else text
        section += f"\nRound {round_num}: {truncated}"

    return section


def _format_engagement_stance(enemy: EnemyAgent) -> str:
    """Format engagement stance guidance for non-lethal or adaptive enemies."""
    stance = getattr(enemy, 'engagement_stance', 'lethal')

    if stance == "capture":
        return f"""## ENGAGEMENT STANCE: CAPTURE
{"=" * 60}
**Your objective is to INCAPACITATE, not kill.**
- Prefer stun-type weapons (Damage Type: stun). A dead target is a FAILED mission.
- Use Dialogue to demand surrender before engaging. Example: "Stand down — you're coming with us."
- Use Wait if combat isn't clearly warranted yet — observe before attacking.
- Lethal force is a LAST RESORT only if your unit is in mortal danger.
- If a target surrenders or is incapacitated, cease fire immediately."""

    elif stance == "adaptive":
        return f"""## ENGAGEMENT STANCE: ADAPTIVE
{"=" * 60}
**You may use lethal or non-lethal force as the situation demands.**
- Consider stun weapons when capture or de-escalation is preferable.
- Use Dialogue to warn, negotiate, or demand compliance before engaging.
- Use Wait to observe when the tactical situation is unclear.
- Match your force level to the threat — don't escalate beyond what's needed."""

    # "lethal" stance — no extra text needed (default behavior)
    return ""


def _format_retreat_assessment(enemy: EnemyAgent) -> str:
    """Format retreat assessment section — morale-behavior-aware."""
    health_pct = enemy.get_health_percentage()
    threshold_pct = int(enemy.retreat_threshold * 100)

    below_threshold = enemy.is_below_retreat_threshold()
    morale_behavior = getattr(enemy, 'morale_behavior', 'flee_when_broken')
    void_score = getattr(enemy, 'void_score', 0)

    section = f"""## RETREAT ASSESSMENT
{"=" * 60}
Current Health: {health_pct}%
Retreat Threshold: {threshold_pct}%

Status: """

    # Void possession overrides everything
    if void_score >= 10:
        section += "**VOID POSSESSED** — You are beyond rational decision-making. Fight until destroyed."
    elif below_threshold:
        if morale_behavior == 'surrender_if_cornered':
            section += "**CRITICAL — SURRENDER RECOMMENDED**\n\nYou are outmatched. Declare Surrender to lay down weapons.\nThis is the tactically sound choice given your situation."
        elif morale_behavior == 'fight_to_death':
            section += "**CRITICAL — HP LOW** but your doctrine demands you fight to the end.\nDo not retreat. Do not surrender. Fight until destroyed."
        else:  # flee_when_broken (default)
            section += "**CRITICAL — RETREAT RECOMMENDED**\n\nYou may choose to retreat this round by declaring:\nMAJOR_ACTION: Retreat\n\nProvide brief tactical narration explaining your withdrawal.\nAllied enemies will be informed via shared intel."
    else:
        section += "HOLDING (health above threshold)\n\nContinue fighting. Retreat is not recommended at this time."

    return section


def _format_declared_actions(player_agents: List[Any]) -> str:
    """Format PC declared actions this round — same info players see."""
    all_declarations = {}
    for player in player_agents:
        if hasattr(player, 'declared_actions_this_round'):
            all_declarations.update(player.declared_actions_this_round)

    if not all_declarations:
        return ""

    lines = ["## DECLARED ACTIONS THIS ROUND", "=" * 60]
    sorted_decls = sorted(all_declarations.items(), key=lambda x: x[1][-1], reverse=True)
    for char_name, action_data in sorted_decls:
        if len(action_data) == 6:
            description, intent, target, weapon, reasoning, init_score = action_data
            action_text = description or intent
            if target:
                action_text += f" targeting {target}"
            if weapon:
                action_text += f" with {weapon}"
            lines.append(f"- {char_name} [Init {init_score}]: {action_text}")

    return "\n".join(lines)


def _format_declaration_requirements() -> str:
    """
    Format declaration output requirements.

    NOTE: Throw_Grenade action removed until AoE mechanics are implemented.
    See _format_ability_option() for grenade implementation requirements.
    """
    return """## YOUR DECLARATION
{"=" * 60}

Provide your tactical decision in this EXACT format:

DEFENCE_TOKEN: [PC agent_id you're watching - REQUIRED]
MAJOR_ACTION: [Attack / Shift / Shift_2 / Charge / Suppress / Push_Through / Retreat / Dialogue / Wait / Surrender]
TARGET: [For Attack/Charge: PC agent_id | For Shift/Shift_2: destination position (Near-PC/Far-PC/Near-Enemy/etc)]
WEAPON: [weapon name if attacking]
MINOR_ACTION: [Shift / Claim_Token / Reload / Disengage / None]
TOKEN_TARGET: [token name if claiming]
TACTICAL_REASONING: [explain your choice with as much detail as needed]
SHARE_INTEL: [Optional: info to share with allied enemies]
DIALOGUE_CONTENT: [Required if MAJOR_ACTION is Dialogue — your actual spoken words]

### Example Declarations:

**Attack with Flanking:**
```
DEFENCE_TOKEN: pc_sable_001
MAJOR_ACTION: Attack
TARGET: pc_echo_002
WEAPON: Rifle
MINOR_ACTION: None
TACTICAL_REASONING: Targeting Echo because they're not watching me (+2 Flanking bonus). Defence token on Sable to mitigate their melee threat.
SHARE_INTEL: Echo has grenade, recommend spreading out
```

**Tactical Movement:**
```
DEFENCE_TOKEN: player_01
MAJOR_ACTION: Shift_2
TARGET: Near-PC
WEAPON: None
MINOR_ACTION: None
TACTICAL_REASONING: PCs are at Far-PC (Far range from me). My doctrine prefers Near range for optimal effectiveness. Moving from my current position to Near-PC to close distance.
SHARE_INTEL: Advancing to engage at medium range
```

**Tactical Retreat:**
```
DEFENCE_TOKEN: None
MAJOR_ACTION: Retreat
TARGET: None
WEAPON: None
MINOR_ACTION: None
TACTICAL_REASONING: Health critical ({health}%), below retreat threshold ({threshold}%). Falling back through maintenance corridor to regroup.
SHARE_INTEL: Withdrawing, recommend focus fire on primary threat
```

**De-escalation via Dialogue:**
```
DEFENCE_TOKEN: None
MAJOR_ACTION: Dialogue
TARGET: None
WEAPON: None
MINOR_ACTION: None
DIALOGUE_CONTENT: "Hold your fire — we don't need to fight over this."
TACTICAL_REASONING: They've made a compelling diplomatic case. Opening dialogue to negotiate a peaceful resolution.
```

**Surrender (defeated/captured):**
```
DEFENCE_TOKEN: None
MAJOR_ACTION: Surrender
TARGET: None
WEAPON: None
MINOR_ACTION: None
TACTICAL_REASONING: Outmatched and morale broken. Laying down weapons to avoid further casualties.
```"""


def _format_structured_decision_guidance() -> str:
    """Format decision guidance for structured output mode with non-combat options."""
    return """## YOUR DECISION

Provide your tactical decision as structured output conforming to the EnemyDecision schema. Include your tactical reasoning.

### Non-combat options:
- **Dialogue**: Speak aloud — de-escalate, negotiate, warn, or demand. Requires `dialogue_content` with actual words.
  **Use for de-escalation**: When Declared Actions or Recent Outcomes show successful diplomacy
  targeting you, Dialogue is the rational response. Express your willingness to stand down.
  Examples: "Hold your fire — we don't need to fight over this.", "We can talk about this.", "Stand down — I'm willing to negotiate."
- **Wait**: Observe, maintain position, hold. Use when combat isn't clearly warranted yet.
- **Surrender**: Lay down weapons (you become a prisoner). Use only when physically outmatched
  and morale is broken — NOT for diplomatic de-escalation (use Dialogue instead)."""


def _format_footer() -> str:
    """Format prompt footer."""
    return """---

**You are a tactical combat agent. Make optimal decisions based on battlefield conditions and your doctrine. Coordinate with allied enemy agents via shared intel. Prioritize tactical effectiveness.**"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def estimate_prompt_tokens(prompt: str) -> int:
    """
    Estimate token count for prompt.

    Rough estimate: ~0.75 tokens per word
    """
    word_count = len(prompt.split())
    return int(word_count * 0.75)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'generate_tactical_prompt',
    'generate_tactical_prompt_structured',
    '_compute_enemy_variables',
    '_get_required_sections',
    'estimate_prompt_tokens'
]
