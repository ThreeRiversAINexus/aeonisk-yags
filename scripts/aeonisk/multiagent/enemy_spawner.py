"""
Enemy Spawner for Aeonisk Tactical Combat

Handles creating enemy agents from structured output (EnemySpawn schema).

Each enemy is a single combat unit. Groups (e.g., "Heavy Gunners Squad")
are single units with one HP pool. DM narrates casualties based on HP percentage.

Design Document: /content/experimental/Enemy Agent System - Design Document.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

import logging
from typing import List, Optional
from dataclasses import replace

from .enemy_agent import EnemyAgent, Position
from .enemy_templates import (
    get_template,
    get_weapon,
    get_armor,
    load_weapons,
    get_available_templates
)
from .energy_economy import Seed, SeedType, Element, create_raw_seed

logger = logging.getLogger(__name__)


# =============================================================================
# SPAWN PROCESSING
# =============================================================================


def spawn_enemy(
    name: str,
    template_key: str,
    position_str: str,
    tactics_override: Optional[str] = None,
    personality_override: Optional[str] = None,
    current_round: int = 0
) -> EnemyAgent:
    """
    Create an enemy agent from spawn parameters.

    Each enemy is a single combat unit regardless of narrative description.
    Groups (e.g., "Heavy Gunners Squad") are treated as individual units with
    one HP pool. The DM can narrate casualties based on HP percentage.

    Args:
        name: Display name for the unit (e.g., "Elite Squad", "Heavy Gunners")
        template_key: Template to load (e.g., "grunt", "elite")
        position_str: Initial position (e.g., "Near-Enemy")
        tactics_override: Override template's default tactics
        personality_override: Override default personality (flee_when_broken | surrender_if_cornered | fight_to_death)
        current_round: Current combat round

    Returns:
        Configured EnemyAgent instance

    Raises:
        KeyError: If template not found
        ValueError: If invalid parameters
    """

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

    # Use template health as-is (no scaling)
    max_health = template["health"]

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

    # Determine personality (use override if provided, else default)
    personality = personality_override if personality_override else "flee_when_broken"

    # Create agent
    agent = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template=template_key,
        faction=faction,
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
        personality=personality,
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
        f"health={max_health}, "
        f"position={position}, "
        f"initiative={agent.initiative})"
    )

    return agent


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
        agent_id: ID or name of agent to despawn
        agents: List of all enemy agents
        reason: Reason for despawn
        current_round: Current combat round

    Returns:
        Despawned agent, or None if not found
    """
    # First try to match by agent_id
    for agent in agents:
        if agent.agent_id == agent_id:
            # Safety check: skip if already inactive or defeated
            if not agent.is_active:
                logger.debug(f"Agent {agent.name} already inactive, skipping despawn")
                return None
            if agent.health <= 0:
                logger.debug(f"Agent {agent.name} already defeated (HP ≤ 0), skipping despawn")
                return None

            agent.is_active = False
            agent.despawned_round = current_round

            logger.info(
                f"Despawned {agent.name} "
                f"(ID={agent_id}, reason={reason}, round={current_round})"
            )

            return agent

    # If not found by ID, try to match by name
    for agent in agents:
        if agent.name == agent_id:
            # Safety check: skip if already inactive or defeated
            if not agent.is_active:
                logger.debug(f"Agent {agent.name} already inactive, skipping despawn")
                return None
            if agent.health <= 0:
                logger.debug(f"Agent {agent.name} already defeated (HP ≤ 0), skipping despawn")
                return None

            agent.is_active = False
            agent.despawned_round = current_round

            logger.info(
                f"Despawned {agent.name} "
                f"(matched by name, reason={reason}, round={current_round})"
            )

            return agent

    logger.warning(f"Could not find agent to despawn: {agent_id} (tried ID and name matching)")
    return None


def auto_despawn_defeated(
    agents: List[EnemyAgent],
    current_round: int = 0
) -> List[EnemyAgent]:
    """
    Automatically despawn enemies with health ≤ 0.

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

    return despawned


# =============================================================================
# LOOT GENERATION
# =============================================================================

def suggest_loot(agent: EnemyAgent) -> str:
    """
    Generate faction-aware loot suggestion for defeated enemy.

    Drops thematically appropriate Talismanic Energy currency (Breath/Drip/Grain/Spark)
    and Seeds based on enemy faction and template.

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

    # =========================================================================
    # FACTION-AWARE CURRENCY DROPS (Breath, Drip, Grain, Spark)
    # =========================================================================

    # Template-based currency amounts (base values)
    template_currency = {
        # Format: (breath_min, breath_max, drip_min, drip_max, grain_min, grain_max, spark_min, spark_max)
        "grunt":       (10, 30,  3,  8,  0, 2,  0, 0),  # Low-value street thugs
        "elite":       ( 0,  5,  5, 15,  2, 6,  0, 2),  # Professional combatants
        "sniper":      ( 0,  5,  8, 20,  1, 4,  0, 1),  # Specialists
        "boss":        ( 0,  0,  3, 10,  3, 8,  2, 5),  # High-value targets
        "void_cultist":(15, 40,  2, 10,  0, 3,  0, 1),  # Void-aligned (more Breath)
        "enforcer":    ( 0,  5,  5, 15,  2, 5,  0, 2),  # Security forces
        "support":     ( 5, 20,  8, 20,  1, 4,  0, 1),  # Support units
        "ambusher":    (10, 25,  5, 12,  0, 3,  0, 1),  # Stealth units
    }

    # Get base currency for this template
    base_currency = template_currency.get(agent.template, (5, 15, 2, 8, 0, 2, 0, 0))

    # Unpack base values
    breath_min, breath_max, drip_min, drip_max, grain_min, grain_max, spark_min, spark_max = base_currency

    # Faction-specific currency theme modifiers
    faction_lower = agent.faction.lower()

    # Initialize currency counts
    breath = random.randint(breath_min, breath_max) if breath_max > 0 else 0
    drip = random.randint(drip_min, drip_max) if drip_max > 0 else 0
    grain = random.randint(grain_min, grain_max) if grain_max > 0 else 0
    spark = random.randint(spark_min, spark_max) if spark_max > 0 else 0

    # Faction theme adjustments
    if "tempest" in faction_lower or "tempest industries" in faction_lower:
        # Tempest: Tech/energy focus → boost Spark
        spark += random.randint(0, 2)

    elif "acg" in faction_lower or "commerce" in faction_lower or "sovereign nexus" in faction_lower:
        # ACG/Nexus: Commerce/structure → boost Spark + Grain
        spark += random.randint(0, 1)
        grain += random.randint(0, 2)

    elif "pantheon" in faction_lower or "security" in faction_lower:
        # Pantheon Security: Order/law → boost Grain + Breath
        grain += random.randint(0, 2)
        breath += random.randint(0, 5)

    elif "freeborn" in faction_lower or "street" in faction_lower or "gang" in faction_lower:
        # Freeborn/Street: Basic economy → boost Breath + Drip
        breath += random.randint(5, 15)
        drip += random.randint(0, 5)

    elif "resonance" in faction_lower or "commune" in faction_lower:
        # Resonance Communes: Ritual/communication → boost Breath + Drip
        breath += random.randint(5, 10)
        drip += random.randint(0, 3)

    elif "void" in faction_lower or "cult" in faction_lower:
        # Void cultists: Secrecy/corruption → boost Drip + Breath
        drip += random.randint(0, 5)
        breath += random.randint(10, 20)

    # Build currency loot string
    currency_parts = []
    if breath > 0:
        currency_parts.append(f"{breath} Breath")
    if drip > 0:
        currency_parts.append(f"{drip} Drip")
    if grain > 0:
        currency_parts.append(f"{grain} Grain")
    if spark > 0:
        currency_parts.append(f"{spark} Spark")

    if currency_parts:
        loot_items.append(", ".join(currency_parts))

    # =========================================================================
    # SEED DROPS (Raw/Attuned/Hollow based on faction and void score)
    # =========================================================================

    seed_dropped = False

    # Void-aligned enemies (void_score >= 3): Hollow Seeds (illicit black market)
    if agent.void_score >= 3:
        # 25% for Tempest (they traffic Hollows), 20% for others
        hollow_chance = 0.25 if "tempest" in faction_lower else 0.20
        if random.random() < hollow_chance:
            loot_items.append("1 Hollow Seed (illicit void energy)")
            seed_dropped = True

    # Ritual factions: Attuned or Raw Seeds
    if not seed_dropped and ("resonance" in faction_lower or "nexus" in faction_lower or "commune" in faction_lower):
        if random.random() < 0.15:  # 15% chance
            # 50/50 between Attuned (ritually prepared) or Raw (unstable)
            if random.random() < 0.5:
                elements = ["Fire", "Water", "Air", "Earth"]
                element = random.choice(elements)
                loot_items.append(f"1 Attuned Seed ({element})")
            else:
                loot_items.append("1 Raw Seed (unstable, 7-cycle decay)")
            seed_dropped = True

    # Boss enemies: Higher chance of Seeds
    if not seed_dropped and agent.template == "boss":
        if random.random() < 0.30:  # 30% chance for bosses
            if agent.void_score >= 2:
                loot_items.append("1 Hollow Seed (illicit void energy)")
            else:
                elements = ["Fire", "Water", "Air", "Earth", "Spirit"]
                element = random.choice(elements)
                loot_items.append(f"1 Attuned Seed ({element})")
            seed_dropped = True

    # =========================================================================
    # SPECIAL ITEMS (10% chance per unit)
    # =========================================================================

    special_chance = 0.1
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
    """Count total active enemy units."""
    return sum(1 for a in agents if a.is_active)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'spawn_enemy',
    'despawn_enemy',
    'auto_despawn_defeated',
    'suggest_loot',
    'get_active_enemies',
    'get_enemies_by_position',
    'count_active_units'
]
