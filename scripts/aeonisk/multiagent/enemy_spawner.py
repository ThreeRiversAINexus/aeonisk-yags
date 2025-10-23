"""
Enemy Spawner for Aeonisk Tactical Combat

Handles parsing spawn markers from DM narration and creating enemy agents.

Spawn Syntax:
    [SPAWN_ENEMY: name | template | count | position | tactics]

Example:
    [SPAWN_ENEMY: Syndicate Grunts | grunt | 3 | Near-Enemy | aggressive_melee]

Design Document: /content/experimental/Enemy Agent System - Design Document.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import replace

from .enemy_agent import EnemyAgent, Position
from .enemy_templates import (
    get_template,
    get_weapon,
    get_armor,
    load_weapons,
    get_available_templates
)

logger = logging.getLogger(__name__)


# =============================================================================
# SPAWN MARKER REGEX
# =============================================================================

# Pattern: [SPAWN_ENEMY: name | template | count | position | tactics (optional)]
SPAWN_PATTERN = re.compile(
    r'\[SPAWN_ENEMY:\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|\]]+)(?:\s*\|\s*([^|\]]+))?\]',
    re.IGNORECASE
)

# Pattern: [DESPAWN_ENEMY: agent_id | reason]
DESPAWN_PATTERN = re.compile(
    r'\[DESPAWN_ENEMY:\s*([^|]+)\s*\|\s*([^\]]+)\]',
    re.IGNORECASE
)


# =============================================================================
# SPAWN PROCESSING
# =============================================================================

def parse_spawn_markers(text: str) -> List[Tuple[str, str, int, str, Optional[str]]]:
    """
    Parse all spawn markers from DM narration.

    Args:
        text: DM narration text

    Returns:
        List of (name, template, count, position, tactics) tuples
    """
    matches = SPAWN_PATTERN.findall(text)

    parsed = []
    for match in matches:
        name = match[0].strip()
        template = match[1].strip()
        count = int(match[2].strip())
        position = match[3].strip()
        tactics = match[4].strip() if match[4] else None

        # Hard cap spawns at 2 units max (combat balance)
        if count > 2:
            logger.warning(f"Spawn count {count} exceeds max (2) - capping to 2 units for {name}")
            count = 2

        parsed.append((name, template, count, position, tactics))
        logger.info(f"Found spawn marker: {name} ({template} × {count}) at {position}")

    return parsed


def parse_despawn_markers(text: str) -> List[Tuple[str, str]]:
    """
    Parse all despawn markers from DM narration.

    Args:
        text: DM narration text

    Returns:
        List of (agent_id, reason) tuples
    """
    matches = DESPAWN_PATTERN.findall(text)

    parsed = []
    for match in matches:
        agent_id = match[0].strip()
        reason = match[1].strip()

        parsed.append((agent_id, reason))
        logger.info(f"Found despawn marker: {agent_id} (reason: {reason})")

    return parsed


def spawn_enemy(
    name: str,
    template_key: str,
    count: int,
    position_str: str,
    tactics_override: Optional[str] = None,
    current_round: int = 0
) -> EnemyAgent:
    """
    Create an enemy agent from spawn parameters.

    Args:
        name: Display name for the agent/group
        template_key: Template to load (e.g., "grunt", "elite")
        count: Number of enemies (>1 creates group)
        position_str: Initial position (e.g., "Near-Enemy")
        tactics_override: Override template's default tactics
        current_round: Current combat round

    Returns:
        Configured EnemyAgent instance

    Raises:
        KeyError: If template not found
        ValueError: If invalid parameters
    """
    # Validate count
    if count < 1:
        raise ValueError(f"Invalid enemy count: {count} (must be ≥ 1)")

    # Load template
    try:
        template = get_template(template_key)
    except KeyError:
        available = ", ".join(get_available_templates())
        raise KeyError(
            f"Unknown template '{template_key}'. "
            f"Available templates: {available}"
        )

    # Parse position
    try:
        position = Position.from_string(position_str)
    except Exception as e:
        raise ValueError(f"Invalid position '{position_str}': {e}")

    # Generate unique agent ID
    import uuid
    agent_id = f"enemy_{template_key}_{uuid.uuid4().hex[:8]}"

    # Determine if group
    is_group = count > 1

    # Calculate health (with group scaling)
    base_health = template["health"]
    if is_group:
        # Group health = base × count × 0.7
        max_health = int(base_health * count * 0.7)
        logger.debug(
            f"Group health scaling: {base_health} × {count} × 0.7 = {max_health}"
        )
    else:
        max_health = base_health

    # Load weapons
    weapon_keys = template["weapons"]
    weapons = load_weapons(weapon_keys)

    # Load armor
    armor_key = template["armor"]
    armor = get_armor(armor_key)

    # Determine tactics
    tactics = tactics_override or template["default_tactics"]

    # Extract faction from name
    from .faction_utils import extract_faction
    faction = extract_faction(name)

    # Initialize ammo
    ammo = {}
    for weapon in weapons:
        if weapon.is_ranged and weapon.capacity > 0:
            ammo[weapon.name] = weapon.capacity

    # Create agent
    agent = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template=template_key,
        faction=faction,
        is_group=is_group,
        unit_count=count,
        original_unit_count=count,
        attributes=template["attributes"].copy(),
        skills=template["skills"].copy(),
        health=max_health,
        max_health=max_health,
        soak=template.get("soak", 0),  # Will be calculated in __post_init__
        wounds=0,
        position=position,
        initiative=0,  # Will be rolled
        tactics=tactics,
        threat_priority=template["threat_priority"],
        retreat_threshold=template["retreat_threshold"],
        void_score=template.get("void_score", 0),
        weapons=weapons,
        armor=armor,
        special_abilities=template.get("special_abilities", []).copy(),
        ammo=ammo,
        spawned_round=current_round,
        size=template.get("size", 5),
        move=template.get("move", 10)
    )

    # Roll initial initiative
    agent.initiative = agent.roll_initiative()

    logger.info(
        f"Spawned {agent.name} "
        f"(template={template_key}, "
        f"count={count}, "
        f"health={max_health}, "
        f"position={position}, "
        f"initiative={agent.initiative})"
    )

    return agent


def spawn_from_marker(
    marker_text: str,
    current_round: int = 0
) -> List[EnemyAgent]:
    """
    Parse spawn marker and create enemy agent(s).

    Args:
        marker_text: Full DM narration text containing markers
        current_round: Current combat round

    Returns:
        List of spawned EnemyAgent instances
    """
    markers = parse_spawn_markers(marker_text)

    agents = []
    for name, template, count, position, tactics in markers:
        try:
            agent = spawn_enemy(
                name=name,
                template_key=template,
                count=count,
                position_str=position,
                tactics_override=tactics,
                current_round=current_round
            )
            agents.append(agent)
        except Exception as e:
            logger.error(f"Failed to spawn {name}: {e}")
            # Continue processing other markers

    return agents


# =============================================================================
# DESPAWN PROCESSING
# =============================================================================

def despawn_enemy(
    agent_id: str,
    agents: List[EnemyAgent],
    reason: str = "defeated",
    current_round: int = 0
) -> Optional[EnemyAgent]:
    """
    Mark enemy agent as inactive (despawned).

    Args:
        agent_id: ID of agent to despawn
        agents: List of all enemy agents
        reason: Reason for despawn
        current_round: Current combat round

    Returns:
        Despawned agent, or None if not found
    """
    for agent in agents:
        if agent.agent_id == agent_id:
            agent.is_active = False
            agent.despawned_round = current_round

            logger.info(
                f"Despawned {agent.name} "
                f"(ID={agent_id}, reason={reason}, round={current_round})"
            )

            return agent

    logger.warning(f"Could not find agent to despawn: {agent_id}")
    return None


def despawn_from_markers(
    marker_text: str,
    agents: List[EnemyAgent],
    current_round: int = 0
) -> List[EnemyAgent]:
    """
    Parse despawn markers and despawn agents.

    Args:
        marker_text: DM narration text containing markers
        agents: List of all enemy agents
        current_round: Current combat round

    Returns:
        List of despawned agents
    """
    markers = parse_despawn_markers(marker_text)

    despawned = []
    for agent_id, reason in markers:
        agent = despawn_enemy(
            agent_id=agent_id,
            agents=agents,
            reason=reason,
            current_round=current_round
        )
        if agent:
            despawned.append(agent)

    return despawned


def auto_despawn_defeated(
    agents: List[EnemyAgent],
    current_round: int = 0
) -> List[EnemyAgent]:
    """
    Automatically despawn enemies with health ≤ 0 or unit_count = 0.

    Args:
        agents: List of all enemy agents
        current_round: Current combat round

    Returns:
        List of auto-despawned agents
    """
    despawned = []

    for agent in agents:
        if not agent.is_active:
            continue

        # Check health
        if agent.health <= 0:
            agent.is_active = False
            agent.despawned_round = current_round
            despawned.append(agent)
            logger.info(
                f"Auto-despawned {agent.name} (health ≤ 0, round={current_round})"
            )
            continue

        # Check group attrition
        if agent.is_group and agent.unit_count <= 0:
            agent.is_active = False
            agent.despawned_round = current_round
            despawned.append(agent)
            logger.info(
                f"Auto-despawned {agent.name} (unit count = 0, round={current_round})"
            )
            continue

    return despawned


# =============================================================================
# LOOT GENERATION
# =============================================================================

def suggest_loot(agent: EnemyAgent) -> str:
    """
    Generate loot suggestion for defeated enemy.

    DM can override or expand.

    Args:
        agent: Defeated enemy agent

    Returns:
        Loot description string
    """
    import random

    if not agent.weapons:
        return f"Defeated {agent.name}: No loot"

    loot_items = []

    # Weapons
    for weapon in agent.weapons:
        # Condition based on enemy state
        if agent.health > 0:
            condition = "good"
        elif agent.wounds <= 2:
            condition = "fair"
        else:
            condition = "damaged"

        loot_items.append(f"{weapon.name} ({condition})")

    # Armor
    if agent.armor and agent.armor.name != "No Armor":
        if agent.wounds > 3:
            condition = "heavily damaged"
        elif agent.wounds > 1:
            condition = "damaged"
        else:
            condition = "fair"

        loot_items.append(f"{agent.armor.name} ({condition})")

    # Credits (scaled by template type and unit count)
    credit_base = {
        "grunt": 20,
        "elite": 50,
        "sniper": 40,
        "boss": 200,
        "void_cultist": 30,
        "enforcer": 60,
        "support": 40,
        "ambusher": 35
    }

    base = credit_base.get(agent.template, 25)
    credits = random.randint(base // 2, base * 2) * agent.unit_count
    loot_items.append(f"{credits} credits")

    # Special items (10% chance per unit)
    special_chance = 0.1 * agent.unit_count
    if random.random() < special_chance:
        special_items = [
            "encrypted datapad",
            "faction insignia",
            "coded message",
            "security keycard",
            "ritual talisman" if agent.void_score > 3 else None
        ]
        special = random.choice([i for i in special_items if i])
        loot_items.append(special)

    loot_str = ", ".join(loot_items)

    return f"**Loot from {agent.name}:** {loot_str}"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_active_enemies(agents: List[EnemyAgent]) -> List[EnemyAgent]:
    """Filter for active enemies only."""
    return [a for a in agents if a.is_active]


def get_enemies_by_position(
    agents: List[EnemyAgent],
    position: Position
) -> List[EnemyAgent]:
    """Get all active enemies at a specific position."""
    return [
        a for a in agents
        if a.is_active and a.position.ring == position.ring and a.position.side == position.side
    ]


def count_active_units(agents: List[EnemyAgent]) -> int:
    """Count total active enemy units (accounting for groups)."""
    return sum(a.unit_count for a in agents if a.is_active)


def validate_spawn_syntax(marker_text: str) -> Tuple[bool, Optional[str]]:
    """
    Validate spawn marker syntax.

    Args:
        marker_text: Marker text to validate

    Returns:
        (is_valid, error_message)
    """
    markers = parse_spawn_markers(marker_text)

    if not markers:
        return False, "No spawn markers found"

    for name, template, count, position, tactics in markers:
        # Validate template
        available = get_available_templates()
        if template not in available:
            return False, f"Unknown template '{template}'. Available: {', '.join(available)}"

        # Validate count
        if count < 1:
            return False, f"Invalid count {count} (must be ≥ 1)"

        # Validate position
        try:
            Position.from_string(position)
        except Exception as e:
            return False, f"Invalid position '{position}': {e}"

        # Validate tactics (optional)
        if tactics:
            from .enemy_agent import TACTICAL_DOCTRINES
            if tactics not in TACTICAL_DOCTRINES:
                return False, f"Unknown tactics '{tactics}'"

    return True, None


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'parse_spawn_markers',
    'parse_despawn_markers',
    'spawn_enemy',
    'spawn_from_marker',
    'despawn_enemy',
    'despawn_from_markers',
    'auto_despawn_defeated',
    'suggest_loot',
    'get_active_enemies',
    'get_enemies_by_position',
    'count_active_units',
    'validate_spawn_syntax'
]
