"""
Faction Utilities for Aeonisk YAGS

Defines faction relationships and alignment logic based on
.claude/FACTION_REFERENCE.md

Author: Three Rivers AI Nexus
"""

from typing import Tuple


# Canonical faction names for spawns (EnemySpawn, NPCSpawn schemas)
CANONICAL_SPAWN_FACTIONS = [
    "Sovereign Nexus", "Pantheon Security", "ACG", "ArcGen",
    "House of Vox", "Aether Dynamics", "Tempest Industries", "Freeborn",
    "Void", "Independent", "Unknown"
]

# Void faction set (hostile to everyone except other Void)
VOID_FACTIONS = {"Void"}

# Faction Alignments (from FACTION_REFERENCE.md)
PRO_NEXUS_FACTIONS = {
    "Nexus", "Sovereign Nexus", "Pantheon", "Pantheon Security"
}

NEXUS_ALIGNED_CORPORATE = {
    "ACG", "ArcGen", "House of Vox", "Vox", "Aether Dynamics"
}

ANTI_NEXUS_FACTIONS = {
    "Tempest", "Tempest Industries"
}

NEUTRAL_FACTIONS = {
    "Freeborn", "Nomad", "Stateless", "Refugee", "Independent",
    # Freeborn subfactions (schemas normalize these to "Freeborn", but accept
    # them here too so direct alliance checks on raw values stay correct).
    "Resonance Communes", "Fractal Praxis",
}


def extract_faction(enemy_name: str) -> str:
    """
    Extract faction from enemy name.

    Args:
        enemy_name: Enemy unit name (e.g., "Tempest Operatives", "Nexus Enforcers")

    Returns:
        Faction name or "Unknown"

    Examples:
        "Tempest Operatives" -> "Tempest"
        "Nexus Enforcers" -> "Nexus"
        "Pantheon Security" -> "Pantheon"
        "ACG Operatives" -> "ACG"
    """
    name_lower = enemy_name.lower()

    # Check each faction category
    all_factions = (
        PRO_NEXUS_FACTIONS |
        NEXUS_ALIGNED_CORPORATE |
        ANTI_NEXUS_FACTIONS |
        NEUTRAL_FACTIONS |
        VOID_FACTIONS
    )

    for faction in all_factions:
        if faction.lower() in name_lower:
            return faction

    return "Unknown"


def are_factions_allied(faction_a: str, faction_b: str) -> bool:
    """
    Determine if two factions are allied.

    Rules (from FACTION_REFERENCE.md):
    - Pro-Nexus factions ally with each other
    - Nexus-aligned corporates ally with pro-Nexus
    - Anti-Nexus factions oppose pro-Nexus and corporates
    - Neutral factions don't fight unless provoked
    - Unknown factions are assumed hostile to everyone

    Args:
        faction_a: First faction name
        faction_b: Second faction name

    Returns:
        True if allied, False if hostile
    """
    # Same faction = allied
    if faction_a == faction_b:
        return True

    # Void factions are hostile to everyone except other Void
    if faction_a in VOID_FACTIONS or faction_b in VOID_FACTIONS:
        return faction_a in VOID_FACTIONS and faction_b in VOID_FACTIONS

    # Unknown factions are hostile to everyone
    if faction_a == "Unknown" or faction_b == "Unknown":
        return False

    # Pro-Nexus + Pro-Nexus = allied
    if faction_a in PRO_NEXUS_FACTIONS and faction_b in PRO_NEXUS_FACTIONS:
        return True

    # Pro-Nexus + Corporate = allied
    if (faction_a in PRO_NEXUS_FACTIONS and faction_b in NEXUS_ALIGNED_CORPORATE) or \
       (faction_b in PRO_NEXUS_FACTIONS and faction_a in NEXUS_ALIGNED_CORPORATE):
        return True

    # Corporate + Corporate = allied (both serve Nexus interests)
    if faction_a in NEXUS_ALIGNED_CORPORATE and faction_b in NEXUS_ALIGNED_CORPORATE:
        return True

    # Anti-Nexus + Pro-Nexus = hostile
    if (faction_a in ANTI_NEXUS_FACTIONS and faction_b in PRO_NEXUS_FACTIONS) or \
       (faction_b in ANTI_NEXUS_FACTIONS and faction_a in PRO_NEXUS_FACTIONS):
        return False

    # Anti-Nexus + Corporate = hostile
    if (faction_a in ANTI_NEXUS_FACTIONS and faction_b in NEXUS_ALIGNED_CORPORATE) or \
       (faction_b in ANTI_NEXUS_FACTIONS and faction_a in NEXUS_ALIGNED_CORPORATE):
        return False

    # Neutral + Neutral = allied (don't fight each other)
    if faction_a in NEUTRAL_FACTIONS and faction_b in NEUTRAL_FACTIONS:
        return True

    # Default: hostile
    return False


FACTION_DESCRIPTIONS = {
    "Sovereign Nexus": "The government. Codex authority, pod gestation system, spiritual bureaucracy. Allied with Pantheon Security and corporate factions. Opposed to Tempest Industries.",
    "Pantheon Security": "Law enforcement, civic order. Upholds Codex law, maintains stability. Allied with Sovereign Nexus and corporate factions. Opposed to Tempest Industries.",
    "ACG": "Astral Commerce Group. Debt collection, soulcredit ledgers, contract enforcement. Corporate, loosely Nexus-aligned. Allied with other corporate factions and Sovereign Nexus. Opposed to Tempest Industries.",
    "ArcGen": "Arcane Genetics. Biocreche pods, gene-temples, bio-ascension protocols. Corporate, loosely Nexus-aligned. Allied with other corporate factions and Sovereign Nexus. NOT the same as ACG.",
    "House of Vox": "Media and broadcast temples. Information control and propaganda. Corporate, loosely Nexus-aligned. Allied with other corporate factions and Sovereign Nexus.",
    "Aether Dynamics": "Leyline power generation and attunement specialists. Spaceship slipstream pilots. Corporate, loosely Nexus-aligned.",
    "Tempest Industries": "Void research, dissolution advocacy. Anti-Nexus rebels resisting commodification of consciousness. Opposed to Sovereign Nexus, Pantheon Security, and all corporate factions.",
    "Freeborn": "Natural-born, outside the pod system. Neutral — not anti-Nexus, just independent. Subfactions include Resonance Communes, Fractal Praxis, and unaffiliated loners.",
    "Void": "Void-corrupted entities. Hostile to all non-Void factions. Driven by dissolution resonance.",
}


def get_faction_description(faction: str) -> str:
    """
    Get narrative description of a faction for LLM prompts.

    Args:
        faction: Faction name

    Returns:
        Description string. Returns generic text for unknown factions.
    """
    # Try exact match first
    if faction in FACTION_DESCRIPTIONS:
        return FACTION_DESCRIPTIONS[faction]

    # Try case-insensitive partial match
    faction_lower = faction.lower()
    for name, desc in FACTION_DESCRIPTIONS.items():
        if name.lower() in faction_lower or faction_lower in name.lower():
            return desc

    return f"Unaffiliated faction. Allegiances and motivations unclear."


def get_faction_stance(faction: str) -> str:
    """
    Get the political stance of a faction.

    Returns:
        "Pro-Nexus", "Anti-Nexus", "Neutral", or "Unknown"
    """
    if faction in VOID_FACTIONS:
        return "Void"
    elif faction in PRO_NEXUS_FACTIONS or faction in NEXUS_ALIGNED_CORPORATE:
        return "Pro-Nexus"
    elif faction in ANTI_NEXUS_FACTIONS:
        return "Anti-Nexus"
    elif faction in NEUTRAL_FACTIONS:
        return "Neutral"
    else:
        return "Unknown"
