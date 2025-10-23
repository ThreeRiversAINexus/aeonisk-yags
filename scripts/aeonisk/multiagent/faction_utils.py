"""
Faction Utilities for Aeonisk YAGS

Defines faction relationships and alignment logic based on
.claude/FACTION_REFERENCE.md

Author: Three Rivers AI Nexus
"""

from typing import Tuple


# Faction Alignments (from FACTION_REFERENCE.md)
PRO_NEXUS_FACTIONS = {
    "Nexus", "Sovereign Nexus", "Pantheon", "Pantheon Security"
}

NEXUS_ALIGNED_CORPORATE = {
    "ACG", "ArcGen", "House of Vox", "Vox"
}

ANTI_NEXUS_FACTIONS = {
    "Tempest", "Tempest Industries"
}

NEUTRAL_FACTIONS = {
    "Freeborn", "Nomad", "Stateless", "Refugee", "Independent"
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
        NEUTRAL_FACTIONS
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

    # Neutral + Others = allied (neutral doesn't initiate hostility)
    if faction_a in NEUTRAL_FACTIONS or faction_b in NEUTRAL_FACTIONS:
        return True

    # Default: hostile
    return False


def get_faction_stance(faction: str) -> str:
    """
    Get the political stance of a faction.

    Returns:
        "Pro-Nexus", "Anti-Nexus", "Neutral", or "Unknown"
    """
    if faction in PRO_NEXUS_FACTIONS or faction in NEXUS_ALIGNED_CORPORATE:
        return "Pro-Nexus"
    elif faction in ANTI_NEXUS_FACTIONS:
        return "Anti-Nexus"
    elif faction in NEUTRAL_FACTIONS:
        return "Neutral"
    else:
        return "Unknown"
