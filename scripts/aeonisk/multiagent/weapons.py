"""
Weapon & Armor System for Aeonisk YAGS

Shared weapon and armor definitions used by both player and enemy agents.
Implements YAGS-compatible weapon stats with damage types (stun/wound/mixed).

YAGS Combat Reference: /converted_yagsbook/markdown/combat.md
Damage Types (combat.md:76-84):
- stun: Non-lethal bruises, heals quickly (brawl attacks)
- wound: Deadly damage, can kill (guns, swords)
- mixed: Split between stuns and wounds (clubs, knives)

Author: Three Rivers AI Nexus
Date: 2025-10-23
"""

from dataclasses import dataclass, field
from typing import Dict, List


# =============================================================================
# CORE DATA STRUCTURES
# =============================================================================

@dataclass
class Weapon:
    """
    YAGS weapon statistics.

    YAGS Core Weapon Stats:
    - attack: Bonus to attack rolls
    - defence: Bonus to defense rolls
    - damage: Bonus to damage rolls
    - reach: Weapon length (affects close combat)
    - load: Weight/bulkiness
    - damage_type: "stun" | "wound" | "mixed" (determines injury type)
    """
    name: str
    skill: str  # "Brawl", "Melee", "Guns", "Throw"
    attack: int  # Attack bonus
    defence: int  # Defence bonus (for melee)
    damage: int  # Damage bonus
    damage_type: str  # "stun", "mixed", "wound"
    reach: int = 0  # Weapon reach
    load: int = 0  # Weight

    # Ranged weapon stats
    is_ranged: bool = False
    short_range: int = 0  # meters
    medium_range: int = 0
    long_range: int = 0
    increment: int = 0  # Accuracy measure
    rof: int = 1  # Rate of fire
    recoil: int = 0
    capacity: int = 0  # Magazine size

    # Special properties
    special: List[str] = field(default_factory=list)  # ["suppress", "armor_piercing", etc.]


@dataclass
class Armor:
    """YAGS armor statistics."""
    name: str
    soak_bonus: int  # Added to base soak
    armor_type: str  # "light", "heavy", "bulletproof"
    load: int  # Weight penalty
    coverage: str = "full"  # "full", "partial", "head", etc.


# =============================================================================
# WEAPON LIBRARY (YAGS-compatible)
# =============================================================================

WEAPON_LIBRARY: Dict[str, Weapon] = {
    # =========================================================================
    # BRAWL WEAPONS (Non-Lethal)
    # =========================================================================
    "fists": Weapon(
        name="Fists",
        skill="Brawl",
        attack=0,
        defence=0,
        damage=0,
        damage_type="stun",
        reach=0,
        load=0
    ),

    "shock_baton": Weapon(
        name="Shock Baton",
        skill="Brawl",
        attack=2,
        defence=1,
        damage=3,
        damage_type="stun",  # Non-lethal electric weapon
        reach=1,
        load=1,
        special=["stun", "electric"]
    ),

    # =========================================================================
    # MELEE WEAPONS (Mixed Lethality)
    # =========================================================================
    "baton": Weapon(
        name="Baton",
        skill="Melee",
        attack=2,
        defence=1,
        damage=2,
        damage_type="mixed",
        reach=1,
        load=1
    ),

    "combat_knife": Weapon(
        name="Combat Knife",
        skill="Melee",
        attack=3,
        defence=2,
        damage=3,
        damage_type="mixed",
        reach=0,
        load=0
    ),

    "void_blade": Weapon(
        name="Void Blade",
        skill="Melee",
        attack=4,
        defence=3,
        damage=5,
        damage_type="wound",
        reach=1,
        load=2,
        special=["void_corrupted", "armor_piercing"]
    ),

    "ritual_blade": Weapon(
        name="Ritual Blade",
        skill="Melee",
        attack=3,
        defence=2,
        damage=4,
        damage_type="mixed",
        reach=0,
        load=1,
        special=["ritual_focus"]
    ),

    # =========================================================================
    # RANGED WEAPONS (Lethal)
    # =========================================================================
    "pistol": Weapon(
        name="Pistol",
        skill="Guns",
        attack=0,
        defence=0,
        damage=4,
        damage_type="wound",
        reach=0,
        load=1,
        is_ranged=True,
        short_range=5,
        medium_range=10,
        long_range=20,
        increment=5,
        rof=2,
        recoil=0,
        capacity=15
    ),

    "rifle": Weapon(
        name="Assault Rifle",
        skill="Guns",
        attack=0,
        defence=0,
        damage=5,
        damage_type="wound",
        reach=0,
        load=3,
        is_ranged=True,
        short_range=15,
        medium_range=50,
        long_range=100,
        increment=10,
        rof=3,
        recoil=-1,
        capacity=30,
        special=["suppress"]
    ),

    "sniper_rifle": Weapon(
        name="Sniper Rifle",
        skill="Guns",
        attack=2,
        defence=0,
        damage=8,
        damage_type="wound",
        reach=0,
        load=4,
        is_ranged=True,
        short_range=50,
        medium_range=200,
        long_range=500,
        increment=20,
        rof=1,
        recoil=-2,
        capacity=10,
        special=["armor_piercing"]
    ),

    "heavy_weapon": Weapon(
        name="Heavy Machine Gun",
        skill="Guns",
        attack=-1,
        defence=0,
        damage=6,
        damage_type="wound",
        reach=0,
        load=6,
        is_ranged=True,
        short_range=20,
        medium_range=100,
        long_range=300,
        increment=15,
        rof=5,
        recoil=-3,
        capacity=100,
        special=["suppress", "heavy"]
    ),

    "shotgun": Weapon(
        name="Shotgun",
        skill="Guns",
        attack=1,
        defence=0,
        damage=6,
        damage_type="wound",
        reach=0,
        load=3,
        is_ranged=True,
        short_range=5,
        medium_range=10,
        long_range=15,
        increment=3,
        rof=1,
        recoil=-1,
        capacity=8,
        special=["spread"]
    ),

    # =========================================================================
    # NON-LETHAL RANGED WEAPONS
    # =========================================================================
    "tranq_gun": Weapon(
        name="Tranquilizer Gun",
        skill="Guns",
        attack=0,
        defence=0,
        damage=2,  # Low damage, relies on sedative
        damage_type="stun",
        reach=0,
        load=1,
        is_ranged=True,
        short_range=5,
        medium_range=15,
        long_range=30,
        increment=5,
        rof=1,
        recoil=0,
        capacity=6,
        special=["stun", "sedative", "delayed_effect"]
    ),

    "stun_gun": Weapon(
        name="Stun Gun",
        skill="Guns",
        attack=0,
        defence=0,
        damage=4,
        damage_type="stun",
        reach=0,
        load=1,
        is_ranged=True,
        short_range=2,
        medium_range=5,
        long_range=8,
        increment=2,
        rof=1,
        recoil=0,
        capacity=12,
        special=["stun", "electric", "short_range"]
    ),

    # =========================================================================
    # SPECIAL WEAPONS
    # =========================================================================
    "grenade": Weapon(
        name="Frag Grenade",
        skill="Throw",
        attack=0,
        defence=0,
        damage=10,  # Base damage, AOE
        damage_type="wound",
        reach=0,
        load=0,
        is_ranged=True,
        short_range=5,
        medium_range=10,
        long_range=15,
        increment=5,
        rof=1,
        capacity=1,
        special=["aoe", "one_use"]
    ),

    "stun_grenade": Weapon(
        name="Stun Grenade",
        skill="Throw",
        attack=0,
        defence=0,
        damage=8,  # AOE stun effect
        damage_type="stun",
        reach=0,
        load=0,
        is_ranged=True,
        short_range=5,
        medium_range=10,
        long_range=15,
        increment=5,
        rof=1,
        capacity=1,
        special=["aoe", "one_use", "stun", "flashbang"]
    ),
}


# =============================================================================
# ARMOR LIBRARY (YAGS-compatible)
# =============================================================================

ARMOR_LIBRARY: Dict[str, Armor] = {
    "none": Armor(
        name="No Armor",
        soak_bonus=0,
        armor_type="light",
        load=0
    ),

    "robes": Armor(
        name="Ritual Robes",
        soak_bonus=1,
        armor_type="light",
        load=0,
        coverage="full"
    ),

    "light_armor": Armor(
        name="Light Combat Armor",
        soak_bonus=3,
        armor_type="light",
        load=2,
        coverage="full"
    ),

    "medium_armor": Armor(
        name="Medium Combat Armor",
        soak_bonus=5,
        armor_type="heavy",
        load=4,
        coverage="full"
    ),

    "heavy_armor": Armor(
        name="Heavy Combat Armor",
        soak_bonus=8,
        armor_type="bulletproof",
        load=6,
        coverage="full"
    ),

    "tactical_vest": Armor(
        name="Tactical Vest",
        soak_bonus=4,
        armor_type="bulletproof",
        load=2,
        coverage="partial"
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_weapon(weapon_id: str) -> Weapon:
    """
    Get weapon by ID from library.

    Args:
        weapon_id: String key from WEAPON_LIBRARY

    Returns:
        Weapon object

    Raises:
        KeyError if weapon not found
    """
    if weapon_id not in WEAPON_LIBRARY:
        raise KeyError(f"Weapon '{weapon_id}' not found in WEAPON_LIBRARY")
    return WEAPON_LIBRARY[weapon_id]


def get_armor(armor_id: str) -> Armor:
    """
    Get armor by ID from library.

    Args:
        armor_id: String key from ARMOR_LIBRARY

    Returns:
        Armor object

    Raises:
        KeyError if armor not found
    """
    if armor_id not in ARMOR_LIBRARY:
        raise KeyError(f"Armor '{armor_id}' not found in ARMOR_LIBRARY")
    return ARMOR_LIBRARY[armor_id]


def list_weapons_by_type(damage_type: str = None) -> List[str]:
    """
    List all weapons, optionally filtered by damage type.

    Args:
        damage_type: Optional filter ("stun", "wound", "mixed")

    Returns:
        List of weapon IDs
    """
    if damage_type:
        return [wid for wid, weapon in WEAPON_LIBRARY.items()
                if weapon.damage_type == damage_type]
    return list(WEAPON_LIBRARY.keys())
