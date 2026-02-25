"""
Agent conversion mechanics (Enemy ↔ NPC).

Handles conversion between enemy and NPC agent types while preserving:
- agent_id (STABLE - never changes)
- ALL stats (health, soak, skills, void_score)
- Current damage (stuns, wounds)
- Conditions (all buffs/debuffs)
- Faction

Critical principle: Conversion is changing behavior mode, not creating a new agent.
"""

from typing import Optional, Literal, Dict
import logging

from .npc_agent import NPCAgent, ConversionRecord
from .enemy_agent import EnemyAgent, Position
from .energy_economy import EnergyPurse

logger = logging.getLogger(__name__)


def deescalate_enemy_to_npc(
    enemy: EnemyAgent,
    disposition: Literal["friendly", "neutral", "wary", "prisoner"],
    current_round: Optional[int] = None,
    agent_prompt_logger=None,
    llm_provider=None
) -> NPCAgent:
    """
    Convert enemy to NPC after successful diplomacy/intimidation/voluntary surrender.

    Preserves (IDENTICAL state):
    - agent_id (STABLE - never changes)
    - Stats (health, soak, skills, void_score)
    - Current damage (stuns, wounds)
    - Conditions (all buffs/debuffs)
    - Faction
    - Position (tactical location preserved)

    Removes:
    - Tactics (no longer combat AI)
    - Enemy LLM client (if any)

    Adds:
    - NPC LLM client (simple action declarations)
    - entity_type (neutral/ally/prisoner based on disposition)
    - threat_level (determined from enemy type/template)
    - Disposition (behavior guide)
    - Conversion tracking

    Args:
        enemy: EnemyAgent to convert
        disposition: NPC's attitude (friendly/neutral/wary/prisoner)
        current_round: Round number for conversion history (optional)

    Returns:
        NPCAgent with stable agent_id and preserved state

    Example:
        >>> enemy = EnemyAgent(agent_id="enemy_pirate_1", health=15, ...)
        >>> npc = deescalate_enemy_to_npc(enemy, disposition="prisoner")
        >>> assert npc.agent_id == "enemy_pirate_1"  # ✅ STABLE ID
        >>> assert npc.health == 15  # Preserved
    """
    logger.info(f"De-escalating enemy {enemy.agent_id} ({enemy.name}) to NPC with disposition '{disposition}'")

    # Determine entity_type from disposition
    if disposition == "friendly":
        entity_type = "ally"
    elif disposition in ["neutral", "wary"]:
        entity_type = "neutral"
    else:  # prisoner
        entity_type = "prisoner"

    # Determine threat_level from enemy template/personality
    threat_level = _determine_threat_level_from_enemy(enemy)

    # Create conversion record
    conversion = ConversionRecord(
        round=current_round or 0,
        from_type="enemy",
        to_type="npc",
        trigger="deescalation",  # Can be more specific in DM integration
        state_snapshot={
            "health": enemy.health,
            "max_health": enemy.max_health,
            "stuns": getattr(enemy, 'stuns', 0),
            "wounds": getattr(enemy, 'wounds', 0),
            "conditions": [c.name for c in getattr(enemy, 'conditions', [])]
        }
    )

    # Copy conditions (deep copy to avoid reference issues)
    conditions_copy = []
    if hasattr(enemy, 'conditions'):
        for cond in enemy.conditions:
            # Condition is a Pydantic model, so we can reconstruct
            from .schemas.shared_types import Condition
            conditions_copy.append(Condition(
                name=cond.name,
                penalty=cond.penalty,
                description=cond.description,
                duration=getattr(cond, 'duration', None)
            ))

    # Create NPC with stable ID and preserved state
    npc = NPCAgent(
        agent_id=enemy.agent_id,  # ✅ STABLE - never changes
        name=enemy.name,
        faction=getattr(enemy, 'faction', "Unknown"),
        entity_type=entity_type,
        disposition=disposition,
        threat_level=threat_level,
        description=getattr(enemy, 'description', f"Former {getattr(enemy, 'template', 'enemy')}, now {disposition}"),

        # Copy ALL state (not just some)
        health=enemy.health,
        max_health=enemy.max_health,
        soak=getattr(enemy, 'soak', 0),
        void_score=getattr(enemy, 'void_score', 0),
        skills=dict(getattr(enemy, 'skills', {})),  # Copy dict
        stuns=getattr(enemy, 'stuns', 0),
        wounds=getattr(enemy, 'wounds', 0),
        conditions=conditions_copy,

        # Position (preserve from enemy, default to Near-Enemy if missing)
        position=getattr(enemy, 'position', None) or _default_npc_position(),

        # Equipment (preserve from enemy)
        weapons=list(getattr(enemy, 'weapons', [])),

        # Economy (empty purse so NPC can receive currency transfers)
        energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0, seeds=[]),

        # Conversion tracking (for reverse operation)
        converted_from_enemy=True,
        original_enemy_template=getattr(enemy, 'template', None),
        conversion_history=[conversion],

        # Logging
        agent_prompt_logger=agent_prompt_logger,

        # LLM provider
        llm_provider=llm_provider
    )

    # Pre-seed NPC memory with conversion context
    if npc.memory:
        if disposition == "prisoner":
            conversion_note = "You surrendered or were subdued. You are a captive."
        elif disposition == "friendly":
            conversion_note = "You chose to cooperate after the conflict."
        elif disposition == "wary":
            conversion_note = "You stopped fighting but remain cautious and wary."
        else:  # neutral
            conversion_note = "You stopped fighting. The situation has de-escalated."
        npc.memory.set_goal(f"Converted from enemy ({disposition}). {conversion_note}")

    logger.debug(f"✅ De-escalated {enemy.agent_id}: {enemy.name} → NPC ({disposition})")
    return npc


def escalate_npc_to_enemy(
    npc: NPCAgent,
    template_override: Optional[str] = None,
    current_round: Optional[int] = None
):
    """
    Convert NPC to enemy after being attacked/threatened.

    Preserves (IDENTICAL state):
    - agent_id (STABLE - never changes)
    - Stats, damage, conditions
    - Position (tactical location preserved, or default if none)

    Adds:
    - Tactics (use original template or "desperate_fighter" default)
    - Combat AI (enemy action declarations)

    Args:
        npc: NPCAgent to convert
        template_override: Optional enemy template (overrides original)
        current_round: Round number for conversion history (optional)

    Returns:
        EnemyAgent with stable agent_id and preserved state

    Example:
        >>> npc = NPCAgent(agent_id="enemy_civilian_1", health=20, ...)
        >>> enemy = escalate_npc_to_enemy(npc)
        >>> assert enemy.agent_id == "enemy_civilian_1"  # ✅ STABLE ID
        >>> assert enemy.health == 20  # Preserved
    """
    logger.info(f"Escalating NPC {npc.agent_id} ({npc.name}) to enemy")

    # Determine template
    template = template_override or npc.original_enemy_template or "desperate_fighter"

    # Create conversion record
    conversion = ConversionRecord(
        round=current_round or 0,
        from_type="npc",
        to_type="enemy",
        trigger="escalation",  # Can be more specific in DM integration
        state_snapshot={
            "health": npc.health,
            "max_health": npc.max_health,
            "stuns": npc.stuns,
            "wounds": npc.wounds,
            "conditions": [c.name for c in npc.conditions]
        }
    )

    # Convert NPC conditions (List[Condition]) to enemy status_effects (List[str])
    status_effects = []
    if hasattr(npc, 'conditions') and npc.conditions:
        for condition in npc.conditions:
            status_effects.append(condition.name.lower())

    # Synthesize attributes from skills (NPCs only have skills, not attributes)
    # Estimate based on skill levels or use defaults
    def estimate_attributes(skills: Dict[str, int]) -> Dict[str, int]:
        """Estimate YAGS attributes from NPC skills."""
        # Agility: Based on Athletics, Guns, or default 3
        agility = max(
            skills.get('Athletics', 0) // 2 + 2,
            skills.get('Guns', 0) // 2 + 2,
            3
        )
        # Strength: Based on Brawl, Melee, or default 3
        strength = max(
            skills.get('Brawl', 0) // 2 + 2,
            skills.get('Melee', 0) // 2 + 2,
            3
        )
        # Other attributes: defaults (3 = average human)
        return {
            'Agility': min(agility, 5),  # Cap at 5 (human max normally)
            'Strength': min(strength, 5),
            'Perception': skills.get('Awareness', 0) // 2 + 2,
            'Intelligence': 3,
            'Empathy': 2,
            'Willpower': 3,
            'Size': 5  # Average human
        }

    attributes = estimate_attributes(npc.skills)

    # Create enemy with stable ID and preserved state
    enemy = EnemyAgent(
        agent_id=npc.agent_id,  # ✅ STABLE - never changes
        name=npc.name,
        faction=npc.faction,

        # Copy ALL state
        health=npc.health,
        max_health=npc.max_health,
        soak=npc.soak,
        void_score=npc.void_score,
        skills=dict(npc.skills),  # Copy dict
        attributes=attributes,  # Synthesized from skills
        stuns=npc.stuns,
        wounds=npc.wounds,
        status_effects=status_effects,  # Converted from NPC conditions

        # Equipment (preserve from NPC)
        weapons=list(npc.weapons) if hasattr(npc, 'weapons') and npc.weapons else [],

        # Enemy-specific
        template=template,
        morale_behavior=_derive_personality_from_template(template),
        position=npc.position,  # Position is required, will always exist
        initiative=0,  # Will be rolled at start of round

        # State tracking
        spawned_round=current_round or 0
    )

    logger.debug(f"✅ Escalated {npc.agent_id}: {npc.name} → Enemy ({template})")
    return enemy


def subdue_enemy_to_prisoner(
    enemy,  # EnemyAgent type
    current_round: Optional[int] = None,
    agent_prompt_logger=None
) -> NPCAgent:
    """
    Convert enemy to prisoner via non-lethal takedown (stun, subdue).

    Special entity_type: "prisoner" (distinct from neutral/ally).
    Prisoners are restrained, cannot act independently.

    Triggers when:
    - Enemy reduced to 0 HP via stun damage + capture_intent
    - Successful "subdue" action
    - Successful "capture" after enemy flees/surrenders

    Args:
        enemy: EnemyAgent to convert to prisoner
        current_round: Round number for conversion history (optional)

    Returns:
        NPCAgent with entity_type="prisoner" and stable agent_id

    Example:
        >>> enemy = EnemyAgent(agent_id="enemy_guard_1", health=0, stuns=5, ...)
        >>> prisoner = subdue_enemy_to_prisoner(enemy)
        >>> assert prisoner.entity_type == "prisoner"
        >>> assert prisoner.agent_id == "enemy_guard_1"  # ✅ STABLE ID
    """
    logger.info(f"Subduing enemy {enemy.agent_id} ({enemy.name}) to prisoner")

    return deescalate_enemy_to_npc(
        enemy,
        disposition="prisoner",
        current_round=current_round,
        agent_prompt_logger=agent_prompt_logger
    )


def _determine_threat_level_from_enemy(enemy: EnemyAgent) -> Literal["non_combatant", "potential_threat", "armed_neutral"]:
    """
    Determine NPC threat_level from enemy template/type.

    Threat level affects enemy targeting behavior:
    - non_combatant: Most enemies ignore (unless ruthless)
    - potential_threat: Professional enemies might engage
    - armed_neutral: Most enemies treat as threat

    Args:
        enemy: EnemyAgent to analyze

    Returns:
        threat_level string
    """
    template = getattr(enemy, 'template', '').lower()

    # Civilians/bystanders are non-combatants
    if 'civilian' in template or 'bystander' in template:
        return "non_combatant"

    # Combat-trained enemies become armed neutrals when surrendered
    if any(keyword in template for keyword in ['soldier', 'guard', 'raider', 'pirate', 'mercenary']):
        return "armed_neutral"

    # Default: potential threat
    return "potential_threat"


def _derive_personality_from_template(template: str) -> str:
    """
    Derive enemy morale behavior from template name.

    Used when escalating NPC back to enemy.

    Args:
        template: Enemy template name

    Returns:
        personality string (morale behavior: "flee_when_broken", "surrender_if_cornered", "fight_to_death")
    """
    template_lower = template.lower()

    # Pirates/raiders are likely to flee when losing
    if 'pirate' in template_lower or 'raider' in template_lower:
        return "flee_when_broken"
    # Professional soldiers surrender when tactically defeated
    elif 'soldier' in template_lower or 'guard' in template_lower or 'elite' in template_lower:
        return "surrender_if_cornered"
    # Desperate fighters (default escalation) flee when broken
    else:
        return "flee_when_broken"


def _default_npc_position():
    """
    Get default position for NPCs when position is missing.

    Returns Near-Enemy as sensible default (close but not Engaged).
    """
    from .enemy_agent import Position
    return Position(ring="Near", side="Enemy")
