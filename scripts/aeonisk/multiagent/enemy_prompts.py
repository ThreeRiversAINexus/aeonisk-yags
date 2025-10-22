"""
Tactical Prompt Generation for Enemy Agents

Generates LLM prompts for autonomous enemy decision-making during combat.
Prompts include battlefield awareness, tactical options, threat analysis,
and structured output requirements.

Design Document: /content/experimental/Enemy Agent System - Design Document.md
Tactical Module: /content/experimental/Aeonisk - Tactical Module - v1.2.3.md

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

logger = logging.getLogger(__name__)


# =============================================================================
# PROMPT GENERATION
# =============================================================================

def generate_tactical_prompt(
    enemy: EnemyAgent,
    player_agents: List[Any],  # List of PlayerAgent instances
    enemy_agents: List[EnemyAgent],
    shared_intel: SharedIntel,
    available_tokens: List[str],
    current_round: int
) -> str:
    """
    Generate complete tactical prompt for enemy agent.

    Args:
        enemy: The enemy agent making decisions
        player_agents: List of PC agents (targets)
        enemy_agents: List of other enemy agents (allies)
        shared_intel: Shared intelligence pool
        available_tokens: Unclaimed tactical tokens
        current_round: Current combat round

    Returns:
        Complete tactical prompt string
    """

    sections = []

    # Header
    sections.append(_format_header(enemy))

    # Status
    sections.append(_format_status(enemy))

    # Combat Doctrine
    sections.append(_format_doctrine(enemy))

    # Battlefield Situation
    sections.append(_format_battlefield(enemy, player_agents, enemy_agents, available_tokens))

    # Tactical Options
    sections.append(_format_tactical_options(enemy))

    # Tactical Analysis
    sections.append(_format_tactical_analysis(enemy, player_agents))

    # Shared Intel
    if shared_intel:
        intel_section = _format_shared_intel(shared_intel, current_round)
        if intel_section:
            sections.append(intel_section)

    # Retreat Assessment
    sections.append(_format_retreat_assessment(enemy))

    # Declaration Format
    sections.append(_format_declaration_requirements())

    # Footer
    sections.append(_format_footer())

    return "\n\n".join(sections)


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
Unit Count: {enemy.unit_count} {"units" if enemy.unit_count > 1 else "unit"}"""

    if enemy.is_group and enemy.unit_count < enemy.original_unit_count:
        status += f" (started with {enemy.original_unit_count})"

    status += f"""
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
    available_tokens: List[str]
) -> str:
    """Format battlefield situation section."""
    section = f"""## BATTLEFIELD SITUATION
{"=" * 60}

### Enemy Targets (Player Characters):"""

    # Format PC targets
    for pc in player_agents:
        section += "\n" + _format_pc_target(enemy, pc)

    # Format allied enemies
    if enemy_agents:
        section += "\n\n### Allied Forces (Other Enemy Agents):"
        for ally in enemy_agents:
            if ally.agent_id != enemy.agent_id and ally.is_active:
                section += "\n" + _format_allied_enemy(ally)

    # Format tactical tokens
    if available_tokens:
        section += "\n\n### Tactical Tokens Available:"
        section += "\n" + ", ".join(available_tokens)
    else:
        section += "\n\n### Tactical Tokens Available:\nNone (all claimed)"

    return section


def _format_pc_target(enemy: EnemyAgent, pc: Any) -> str:
    """Format individual PC target information."""
    # Calculate range
    try:
        pc_position = Position.from_string(str(pc.position if hasattr(pc, 'position') else "Near-PC"))
        range_name, range_penalty = enemy.position.calculate_range(pc_position)
    except:
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
    except:
        health_str = "Unknown"

    # Check if PC is watching this enemy
    try:
        pc_defence_token = getattr(pc, 'defence_token', None)
        is_watching = pc_defence_token == enemy.agent_id
    except:
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
    except:
        weapons_str = "Unknown"

    # Get PC name
    pc_name = getattr(pc, 'name', getattr(pc, 'agent_id', 'Unknown PC'))
    pc_id = getattr(pc, 'agent_id', 'unknown')

    # Threat level assessment
    threat_level = _assess_threat_level(enemy, pc, range_name, is_watching)

    return f"""- {pc_name} [{pc_id}]
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
    except:
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


def _format_allied_enemy(ally: EnemyAgent) -> str:
    """Format allied enemy information."""
    health_pct = ally.get_health_percentage()

    if health_pct >= 75:
        health_str = "~100% (healthy)"
    elif health_pct >= 50:
        health_str = f"~{health_pct}% (wounded)"
    elif health_pct >= 25:
        health_str = f"~{health_pct}% (bloodied)"
    else:
        health_str = f"~{health_pct}% (CRITICAL)"

    unit_str = f"{ally.unit_count} units" if ally.is_group else "1 unit"
    if ally.is_group and ally.unit_count < ally.original_unit_count:
        unit_str += f" (down from {ally.original_unit_count})"

    return f"""- {ally.name} [{ally.agent_id}]
  Position: {ally.position}
  Unit Count: {unit_str}
  Health: {health_str}
  Tactics: {ally.tactics}"""


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
    group_bonus = enemy.get_group_damage_bonus()

    total_damage = base_damage + group_bonus

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

    return f"""- **{weapon.name}** ({weapon.skill})
   Range: {ranges}
   Damage: {total_damage} + d20 (Str {strength} + Weapon {weapon.damage} + Group {group_bonus})
   Attack Bonus: {weapon.attack:+d}
   Damage Type: {weapon.damage_type}{ammo_str}{special_str}"""


def _format_ability_option(ability: str, enemy: EnemyAgent) -> str:
    """Format special ability option."""
    if ability == "void_surge":
        can_use = enemy.can_use_void_surge()
        status = "AVAILABLE" if can_use else f"LOCKED (Void {enemy.void_score} ≥ 8)"

        return f"""- **Void Surge** - Status: {status}
   Effect: +4 damage, auto-Shock on hit, +1 Stun to you, +1 Void
   Current Void: {enemy.void_score}/10"""

    elif ability == "grenade":
        has_grenade = enemy.ammo.get("Frag Grenade", 0) > 0
        status = "AVAILABLE" if has_grenade else "NONE REMAINING"

        return f"""- **Grenade** - Status: {status}
   Type: Area Effect (targets ring-side location)
   Damage: DC 20 Agility save, 2d6 damage
   WARNING: Friendly fire if allies in blast zone
   Example targets: Near-Enemy, Far-PC, etc."""

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
            pc_name = getattr(pc, 'name', 'Unknown PC')
            range_counts[range_name].append(pc_name)
        except:
            pass

    for range_name, pcs in range_counts.items():
        if pcs:
            section += f"\n- {range_name.upper()} RANGE: {', '.join(pcs)}"

    # Doctrine alignment
    preferred_range = TACTICAL_DOCTRINES.get(enemy.tactics, {}).get('preferred_range', 'Any')
    section += f"\n\nDoctrine '{enemy.tactics}' prefers: {preferred_range} range"

    # Threat assessment
    section += "\n\n### Threat Assessment:"
    section += f"\nBased on priority '{enemy.threat_priority}':\n"

    # Sort targets by threat
    threat_order = []
    for pc in player_agents:
        pc_name = getattr(pc, 'name', 'Unknown PC')
        try:
            pc_position = Position.from_string(str(getattr(pc, 'position', "Near-PC")))
            range_name, _ = enemy.position.calculate_range(pc_position)

            pc_defence_token = getattr(pc, 'defence_token', None)
            is_watching = pc_defence_token == enemy.agent_id

            threat = _assess_threat_level(enemy, pc, range_name, is_watching)
            threat_order.append((threat, pc_name, range_name, is_watching))
        except:
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


def _format_retreat_assessment(enemy: EnemyAgent) -> str:
    """Format retreat assessment section."""
    health_pct = enemy.get_health_percentage()
    threshold_pct = int(enemy.retreat_threshold * 100)

    below_threshold = enemy.is_below_retreat_threshold()

    section = f"""## RETREAT ASSESSMENT
{"=" * 60}
Current Health: {health_pct}%
Retreat Threshold: {threshold_pct}%

Status: """

    if below_threshold:
        section += "**CRITICAL - RETREAT RECOMMENDED**\n\nYou may choose to retreat this round by declaring:\nMAJOR_ACTION: Retreat\n\nProvide brief tactical narration explaining your withdrawal.\nAllied enemies will be informed via shared intel."
    else:
        section += "HOLDING (health above threshold)\n\nContinue fighting. Retreat is not recommended at this time."

    return section


def _format_declaration_requirements() -> str:
    """Format declaration output requirements."""
    return """## YOUR DECLARATION
{"=" * 60}

Provide your tactical decision in this EXACT format:

DEFENCE_TOKEN: [PC agent_id you're watching - REQUIRED]
MAJOR_ACTION: [Attack / Shift / Shift_2 / Charge / Suppress / Push_Through / Throw_Grenade / Retreat]
TARGET: [PC agent_id OR ring-side location if AoE]
WEAPON: [weapon name if attacking]
MINOR_ACTION: [Shift / Claim_Token / Reload / Disengage / None]
TOKEN_TARGET: [token name if claiming]
TACTICAL_REASONING: [1-2 sentences explaining your choice]
SHARE_INTEL: [Optional: info to share with allied enemies]

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

**Grenade with Friendly Fire:**
```
DEFENCE_TOKEN: pc_sable_001
MAJOR_ACTION: Throw_Grenade
TARGET: Near-Enemy
WEAPON: Grenade
MINOR_ACTION: Shift
TACTICAL_REASONING: Throwing grenade at Near-Enemy to hit Sable even though Grunt Squad 2 will take friendly fire - Sable is too dangerous to leave active. Shifting away from blast zone.
SHARE_INTEL: Grenade incoming at Near-Enemy, allied units clear zone
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
```"""


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
    'estimate_prompt_tokens'
]
