"""
Enemy Templates for Aeonisk Tactical Combat

Predefined enemy stat blocks with YAGS-compatible weapons and armor.
Templates define base stats, equipment, and default tactical behavior.

Design Document: /content/experimental/Enemy Agent System - Design Document.md
YAGS Combat: /converted_yagsbook/markdown/combat.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

from typing import Dict, List, Any
from .weapons import Weapon, Armor, WEAPON_LIBRARY, ARMOR_LIBRARY

# NOTE: WEAPON_LIBRARY and ARMOR_LIBRARY are now imported from weapons.py
# This makes weapon definitions shared between players and enemies.

# =============================================================================
# ENEMY TEMPLATES
# =============================================================================

ENEMY_TEMPLATES: Dict[str, Dict[str, Any]] = {

    # =========================================================================
    # GRUNT - Basic enemy combatant
    # =========================================================================
    "grunt": {
        "description": "Basic enemy combatant with minimal training",

        # YAGS Attributes (1-5 for humans)
        "attributes": {
            "Agility": 3,
            "Strength": 3,
            "Perception": 2,
            "Intelligence": 2,
            "Empathy": 2,
            "Willpower": 2,
            "Health": 3  # YAGS health attribute
        },

        # YAGS Skills (0-5 typical)
        "skills": {
            "Brawl": 2,
            "Guns": 3,
            "Awareness": 2,
            "Athletics": 2,
            "Melee": 1
        },

        # Combat Stats
        "health": 12,  # Base health (before group scaling) - reduced for balance
        "soak": 0,  # Will be calculated: base + armor
        "void_score": 1,
        "size": 5,
        "move": 10,

        # Equipment
        "weapons": ["pistol", "baton"],
        "armor": "light_armor",

        # Tactical Behavior
        "default_tactics": "aggressive_melee",
        "threat_priority": "closest_threat",
        "retreat_threshold": 0.3,  # 30% health

        # Special Abilities
        "special_abilities": []
    },

    # =========================================================================
    # ELITE - Veteran combatant
    # =========================================================================
    "elite": {
        "description": "Veteran combatant with advanced training and equipment",

        "attributes": {
            "Agility": 4,
            "Strength": 4,
            "Perception": 4,
            "Intelligence": 3,
            "Empathy": 3,
            "Willpower": 3,
            "Health": 4
        },

        "skills": {
            "Brawl": 3,
            "Guns": 4,
            "Awareness": 4,
            "Athletics": 3,
            "Melee": 3,
            "Stealth": 3
        },

        "health": 20,
        "soak": 0,
        "void_score": 2,
        "size": 5,
        "move": 12,

        "weapons": ["rifle", "combat_knife", "grenade"],
        "armor": "medium_armor",

        "default_tactics": "tactical_ranged",
        "threat_priority": "optimal_target",
        "retreat_threshold": 0.2,

        "special_abilities": ["suppress", "grenade"]
    },

    # =========================================================================
    # SNIPER - Long-range specialist
    # =========================================================================
    "sniper": {
        "description": "Long-range specialist with enhanced perception",

        "attributes": {
            "Agility": 3,
            "Strength": 2,
            "Perception": 5,
            "Intelligence": 3,
            "Empathy": 2,
            "Willpower": 3,
            "Health": 3
        },

        "skills": {
            "Guns": 5,
            "Awareness": 5,
            "Stealth": 4,
            "Athletics": 2,
            "Brawl": 1
        },

        "health": 12,
        "soak": 0,
        "void_score": 1,
        "size": 5,
        "move": 10,

        "weapons": ["sniper_rifle", "pistol"],
        "armor": "light_armor",

        "default_tactics": "extreme_range",
        "threat_priority": "high_value_target",
        "retreat_threshold": 0.5,  # Retreats early

        "special_abilities": []
    },

    # =========================================================================
    # BOSS - Major threat
    # =========================================================================
    "boss": {
        "description": "Major threat with superior stats and equipment",

        "attributes": {
            "Agility": 5,
            "Strength": 5,
            "Perception": 5,
            "Intelligence": 4,
            "Empathy": 4,
            "Willpower": 5,
            "Health": 5
        },

        "skills": {
            "Brawl": 4,
            "Melee": 4,
            "Guns": 5,
            "Awareness": 5,
            "Astral Arts": 4,
            "Athletics": 4
        },

        "health": 30,
        "soak": 0,
        "void_score": 3,
        "size": 5,
        "move": 12,

        "weapons": ["heavy_weapon", "void_blade"],
        "armor": "heavy_armor",

        "default_tactics": "adaptive",
        "threat_priority": "objective_focus",
        "retreat_threshold": 0.1,  # Fights to near-death

        "special_abilities": ["void_surge", "suppress", "grenade"]
    },

    # =========================================================================
    # VOID CULTIST - Ritual specialist
    # =========================================================================
    "void_cultist": {
        "description": "Void-corrupted ritual specialist",

        "attributes": {
            "Agility": 3,
            "Strength": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 4,
            "Willpower": 5,
            "Health": 3
        },

        "skills": {
            "Brawl": 2,
            "Melee": 2,
            "Astral Arts": 5,
            "Intimacy Ritual": 4,
            "Awareness": 3,
            "Magick Theory": 4
        },

        "health": 15,
        "soak": 0,
        "void_score": 5,  # Already corrupted
        "size": 5,
        "move": 10,

        "weapons": ["ritual_blade", "pistol"],
        "armor": "robes",

        "default_tactics": "support",
        "threat_priority": "high_value_target",
        "retreat_threshold": 0.2,

        "special_abilities": ["void_surge", "ritual_attack"]
    },

    # =========================================================================
    # ENFORCER - Melee specialist
    # =========================================================================
    "enforcer": {
        "description": "Close-combat specialist with heavy armor",

        "attributes": {
            "Agility": 3,
            "Strength": 5,
            "Perception": 3,
            "Intelligence": 2,
            "Empathy": 2,
            "Willpower": 4,
            "Health": 4
        },

        "skills": {
            "Brawl": 4,
            "Melee": 4,
            "Guns": 2,
            "Athletics": 3,
            "Awareness": 2
        },

        "health": 22,
        "soak": 0,
        "void_score": 2,
        "size": 5,
        "move": 10,

        "weapons": ["void_blade", "shotgun"],
        "armor": "heavy_armor",

        "default_tactics": "aggressive_melee",
        "threat_priority": "closest_threat",
        "retreat_threshold": 0.15,

        "special_abilities": ["charge"]
    },

    # =========================================================================
    # SUPPORT - Tactical support unit
    # =========================================================================
    "support": {
        "description": "Tactical support unit with suppression weapons",

        "attributes": {
            "Agility": 3,
            "Strength": 3,
            "Perception": 4,
            "Intelligence": 3,
            "Empathy": 3,
            "Willpower": 3,
            "Health": 3
        },

        "skills": {
            "Guns": 4,
            "Awareness": 4,
            "Athletics": 2,
            "Brawl": 2,
            "Stealth": 3
        },

        "health": 15,
        "soak": 0,
        "void_score": 1,
        "size": 5,
        "move": 10,

        "weapons": ["rifle", "pistol", "grenade"],
        "armor": "tactical_vest",

        "default_tactics": "support",
        "threat_priority": "assist_allies",
        "retreat_threshold": 0.3,

        "special_abilities": ["suppress", "overwatch", "grenade"]
    },

    # =========================================================================
    # AMBUSHER - Infiltration specialist
    # =========================================================================
    "ambusher": {
        "description": "Infiltration specialist for ambush tactics",

        "attributes": {
            "Agility": 4,
            "Strength": 3,
            "Perception": 4,
            "Intelligence": 3,
            "Empathy": 2,
            "Willpower": 3,
            "Health": 3
        },

        "skills": {
            "Stealth": 5,
            "Guns": 3,
            "Brawl": 3,
            "Melee": 3,
            "Awareness": 4,
            "Athletics": 3
        },

        "health": 14,
        "soak": 0,
        "void_score": 1,
        "size": 5,
        "move": 12,

        "weapons": ["combat_knife", "pistol"],
        "armor": "light_armor",

        "default_tactics": "ambush",
        "threat_priority": "weakest_target",
        "retreat_threshold": 0.4,  # Retreats quickly

        "special_abilities": ["backstab"]
    },
}


# =============================================================================
# TEMPLATE UTILITY FUNCTIONS
# =============================================================================

def get_template(template_key: str) -> Dict[str, Any]:
    """
    Get enemy template by key.

    Args:
        template_key: Template name (e.g., "grunt", "elite")

    Returns:
        Template dictionary

    Raises:
        KeyError: If template not found
    """
    if template_key not in ENEMY_TEMPLATES:
        raise KeyError(f"Unknown enemy template: {template_key}")

    return ENEMY_TEMPLATES[template_key].copy()


def get_weapon(weapon_key: str) -> Weapon:
    """
    Get weapon by key.

    Args:
        weapon_key: Weapon name (e.g., "pistol", "rifle")

    Returns:
        Weapon instance

    Raises:
        KeyError: If weapon not found
    """
    if weapon_key not in WEAPON_LIBRARY:
        raise KeyError(f"Unknown weapon: {weapon_key}")

    # Return copy to avoid mutations
    weapon_data = WEAPON_LIBRARY[weapon_key]
    return Weapon(
        name=weapon_data.name,
        skill=weapon_data.skill,
        attack=weapon_data.attack,
        defence=weapon_data.defence,
        damage=weapon_data.damage,
        damage_type=weapon_data.damage_type,
        reach=weapon_data.reach,
        load=weapon_data.load,
        is_ranged=weapon_data.is_ranged,
        short_range=weapon_data.short_range,
        medium_range=weapon_data.medium_range,
        long_range=weapon_data.long_range,
        increment=weapon_data.increment,
        rof=weapon_data.rof,
        recoil=weapon_data.recoil,
        capacity=weapon_data.capacity,
        special=weapon_data.special.copy()
    )


def get_armor(armor_key: str) -> Armor:
    """
    Get armor by key.

    Args:
        armor_key: Armor name (e.g., "light_armor", "heavy_armor")

    Returns:
        Armor instance

    Raises:
        KeyError: If armor not found
    """
    if armor_key not in ARMOR_LIBRARY:
        raise KeyError(f"Unknown armor: {armor_key}")

    armor_data = ARMOR_LIBRARY[armor_key]
    return Armor(
        name=armor_data.name,
        soak_bonus=armor_data.soak_bonus,
        armor_type=armor_data.armor_type,
        load=armor_data.load,
        coverage=armor_data.coverage
    )


def load_weapons(weapon_keys: List[str]) -> List[Weapon]:
    """Load multiple weapons from keys."""
    return [get_weapon(key) for key in weapon_keys]


def get_available_templates() -> List[str]:
    """Get list of available template keys."""
    return list(ENEMY_TEMPLATES.keys())


def get_template_description(template_key: str) -> str:
    """Get description of a template."""
    template = get_template(template_key)
    return template.get("description", "No description available")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'ENEMY_TEMPLATES',
    'WEAPON_LIBRARY',
    'ARMOR_LIBRARY',
    'get_template',
    'get_weapon',
    'get_armor',
    'load_weapons',
    'get_available_templates',
    'get_template_description'
]
