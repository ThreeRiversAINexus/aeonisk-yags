"""
Enemy Agent System for Aeonisk Tactical Combat

Implements autonomous AI-controlled enemy combatants that participate in
tactical combat using the Tactical Module v1.2.3 rules. Enemy agents make
their own tactical decisions via LLM prompts and integrate with the existing
declare/resolve combat flow.

Design Document: /content/experimental/Enemy Agent System - Design Document.md
Tactical Module: /content/experimental/Aeonisk - Tactical Module - v1.2.3.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum
import random
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# POSITION & RANGE CALCULATION (Tactical Module v1.2.3)
# =============================================================================

class RingBand(Enum):
    """Range bands in concentric circle model."""
    ENGAGED = "Engaged"
    NEAR = "Near"
    FAR = "Far"
    EXTREME = "Extreme"


class Hemisphere(Enum):
    """Battlefield sides in concentric circle model."""
    PC = "PC"
    ENEMY = "Enemy"


@dataclass
class Position:
    """
    Location in concentric ring battlefield (Tactical Module v1.2.3).

    Physical Model:
             [Enemy Hemisphere]
        ╔═══════════════════════╗
        ║  Extreme Ring         ║
        ║   ┌─Far Ring──┐      ║
        ║   │┌Near Ring┐│      ║
        ║   ││ENGAGED  ││      ║ ← Center line (the Action)
        ║   │└Near Ring┘│      ║
        ║   └─Far Ring──┘      ║
        ║  Extreme Ring         ║
        ╚═══════════════════════╝
             [PC Hemisphere]
    """
    ring: str  # "Engaged", "Near", "Far", "Extreme"
    side: str  # "PC", "Enemy"

    def __str__(self) -> str:
        return f"{self.ring}-{self.side}"

    def __repr__(self) -> str:
        return f"Position(ring='{self.ring}', side='{self.side}')"

    @classmethod
    def from_string(cls, position_str: str) -> 'Position':
        """
        Parse position from string format "Ring-Side".

        Examples:
            "Near-Enemy" -> Position(ring="Near", side="Enemy")
            "Engaged" -> Position(ring="Engaged", side="PC")  # Default to PC
        """
        if '-' in position_str:
            ring, side = position_str.split('-')
            return cls(ring=ring.strip(), side=side.strip())
        else:
            # Engaged band doesn't have side distinction (center)
            return cls(ring=position_str.strip(), side="PC")

    def calculate_range(self, other: 'Position') -> Tuple[str, int]:
        """
        Calculate range to another position using Tactical Module v1.2.3 rules.

        Rules:
        1. Both in Engaged band → "Engaged" (0 penalty)
        2. Same ring, same side → "Melee" (0 penalty)
        3. Different rings or sides → Count through center
           - 1 ring apart = "Near" (-2)
           - 2 rings apart = "Far" (-4)
           - 3+ rings apart = "Extreme" (-6)

        Returns:
            (range_name, attack_penalty)

        Examples:
            Near-PC to Near-PC -> ("Melee", 0)
            Near-PC to Engaged -> ("Near", -2)
            Near-PC to Near-Enemy -> ("Far", -4)
        """
        # Rule 1: Both in Engaged band
        if self.ring == "Engaged" and other.ring == "Engaged":
            return ("Engaged", 0)

        # Rule 2: Same ring, same side = Melee range
        if self.ring == other.ring and self.side == other.side:
            return ("Melee", 0)

        # Rule 3: Different rings or sides - calculate through center
        rings_apart = self._count_rings_between(other)

        if rings_apart == 0:
            return ("Engaged", 0)
        elif rings_apart == 1:
            return ("Near", -2)
        elif rings_apart == 2:
            return ("Far", -4)
        else:  # 3+
            return ("Extreme", -6)

    def _count_rings_between(self, other: 'Position') -> int:
        """
        Count number of rings between two positions.

        If on different sides, count through center (Engaged band).
        """
        ring_order = ["Engaged", "Near", "Far", "Extreme"]

        try:
            self_idx = ring_order.index(self.ring)
            other_idx = ring_order.index(other.ring)
        except ValueError as e:
            logger.error(f"Invalid ring name: {e}")
            return 3  # Default to Extreme range

        # Same side: direct distance
        if self.side == other.side:
            return abs(self_idx - other_idx)

        # Different sides: path through center (Engaged = 0)
        # Distance = rings to center + rings from center
        return self_idx + other_idx

    def shift_toward_center(self) -> Optional['Position']:
        """Move 1 ring toward Engaged band."""
        ring_sequence = ["Extreme", "Far", "Near", "Engaged"]

        try:
            current_idx = ring_sequence.index(self.ring)
        except ValueError:
            return None

        if current_idx < len(ring_sequence) - 1:
            new_ring = ring_sequence[current_idx + 1]
            return Position(ring=new_ring, side=self.side)

        return None  # Already at Engaged

    def shift_away_from_center(self) -> Optional['Position']:
        """Move 1 ring away from Engaged band."""
        ring_sequence = ["Engaged", "Near", "Far", "Extreme"]

        try:
            current_idx = ring_sequence.index(self.ring)
        except ValueError:
            return None

        if current_idx < len(ring_sequence) - 1:
            new_ring = ring_sequence[current_idx + 1]
            return Position(ring=new_ring, side=self.side)

        return None  # Already at Extreme

    def push_through(self) -> Optional['Position']:
        """
        Cross center line to opposite hemisphere (Major action).

        Must pass through Engaged band.
        Returns position on opposite side at Near range.
        """
        opposite_side = "Enemy" if self.side == "PC" else "PC"
        return Position(ring="Near", side=opposite_side)


# =============================================================================
# WEAPONS & ARMOR (YAGS-compatible)
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
# TACTICAL DOCTRINES & THREAT PRIORITIES
# =============================================================================

TACTICAL_DOCTRINES = {
    "aggressive_melee": {
        "description": "Close to melee range and engage directly",
        "preferred_range": "Melee",
        "preferred_actions": ["Charge", "Attack_Melee"],
        "defence_priority": "closest_threat"
    },
    "defensive_ranged": {
        "description": "Maintain distance, use cover, suppress targets",
        "preferred_range": "Far",
        "preferred_actions": ["Attack_Ranged", "Suppress", "Claim_Cover"],
        "defence_priority": "highest_threat"
    },
    "tactical_ranged": {
        "description": "Balanced ranged tactics with positioning",
        "preferred_range": "Near",
        "preferred_actions": ["Attack_Ranged", "Shift", "Claim_Token"],
        "defence_priority": "optimal_target"
    },
    "extreme_range": {
        "description": "Stay at maximum distance, snipe priority targets",
        "preferred_range": "Extreme",
        "preferred_actions": ["Attack_Ranged", "Shift_Away"],
        "defence_priority": "high_value_target"
    },
    "ambush": {
        "description": "Infiltrate enemy side, strike vulnerable targets",
        "preferred_range": "Melee",
        "preferred_actions": ["Push_Through", "Attack", "Stealth"],
        "defence_priority": "weakest_target"
    },
    "support": {
        "description": "Provide covering fire, claim tactical positions",
        "preferred_range": "Near",
        "preferred_actions": ["Suppress", "Claim_Token", "Overwatch"],
        "defence_priority": "assist_allies"
    },
    "adaptive": {
        "description": "Respond dynamically to battlefield conditions",
        "preferred_range": "varies",
        "preferred_actions": ["any"],
        "defence_priority": "context_dependent"
    },
    "berserk_void": {
        "description": "Void-possessed, uncontrolled aggression",
        "preferred_range": "Melee",
        "preferred_actions": ["Charge", "Attack"],
        "defence_priority": "closest_threat"
    }
}

THREAT_PRIORITIES = {
    "highest_threat": "Target PC with highest damage output or immediate danger",
    "weakest_target": "Target PC with lowest health or defenses",
    "objective_focus": "Prioritize tactical objectives over opportunistic targets",
    "closest_threat": "Target nearest PC in range",
    "high_value_target": "Target support/caster PCs over frontline",
    "assist_allies": "Coordinate with allied enemy agents",
    "optimal_target": "Target PCs not watching you (Flanking bonus)"
}


# =============================================================================
# ENEMY AGENT DATACLASS
# =============================================================================

@dataclass
class EnemyAgent:
    """
    Represents an enemy or group of enemies in tactical combat.

    Autonomous AI participant with LLM-driven decision making.
    Integrates with Tactical Module v1.2.3 and YAGS core combat.
    """

    # =========================================================================
    # IDENTITY
    # =========================================================================
    agent_id: str  # Unique ID, e.g., "enemy_grunt_squad_1"
    name: str  # Display name, e.g., "Syndicate Enforcers"
    template: str  # Template key, e.g., "grunt", "elite", "boss"

    # =========================================================================
    # GROUP MECHANICS
    # =========================================================================
    is_group: bool  # True if representing multiple enemies
    unit_count: int  # How many individuals (1 if solo)
    original_unit_count: int  # Starting count for attrition tracking

    # =========================================================================
    # COMBAT STATS (YAGS-compatible)
    # =========================================================================

    # YAGS Attributes (1-5 for humans, 6+ superhuman)
    attributes: Dict[str, int]  # Agility, Strength, Perception, Intelligence, Empathy, Willpower

    # YAGS Skills (0-5 typical, 6+ master)
    skills: Dict[str, int]  # Brawl, Melee, Guns, Awareness, Athletics, etc.

    # Health & Damage
    health: int  # Current health
    max_health: int  # Maximum health
    soak: int  # Damage resistance (base + armor)
    wounds: int  # Wound count (Tactical Module wound ladder)

    # =========================================================================
    # TACTICAL STATE (Tactical Module v1.2.3)
    # =========================================================================
    position: Position  # Current ring-side location
    initiative: int  # Current round initiative (re-rolled each round)

    # Fields with defaults (must come after required fields)
    faction: str = "Unknown"  # Faction allegiance (e.g., "Nexus", "Tempest", "Freeborn")
    stuns: int = 0  # Stun damage (YAGS)
    fatigue: int = 0  # Fatigue levels (YAGS)
    defence_token: Optional[str] = None  # Which PC agent_id are they watching?
    tactical_token: Optional[str] = None  # Claimed terrain advantage

    # =========================================================================
    # DOCTRINE & BEHAVIOR
    # =========================================================================
    tactics: str = "aggressive_melee"  # Combat doctrine
    threat_priority: str = "closest_threat"  # Target selection strategy
    retreat_threshold: float = 0.3  # Morale % (0.0-1.0)

    # =========================================================================
    # AEONISK-SPECIFIC
    # =========================================================================
    void_score: int = 0  # 0-10 void tracking
    void_threshold: int = 8  # Void level that triggers effects

    # =========================================================================
    # EQUIPMENT
    # =========================================================================
    weapons: List[Weapon] = field(default_factory=list)
    armor: Optional[Armor] = None
    special_abilities: List[str] = field(default_factory=list)  # ["void_surge", "grenade", "suppress"]
    ammo: Dict[str, int] = field(default_factory=dict)  # Ammo tracking per weapon

    # =========================================================================
    # STATE TRACKING
    # =========================================================================
    status_effects: List[str] = field(default_factory=list)  # ["stunned", "prone", "suppressed"]
    is_active: bool = True  # False if defeated/retreated
    spawned_round: int = 0  # When they entered combat
    despawned_round: Optional[int] = None  # When they left combat

    # =========================================================================
    # COMMUNICATION (Shared Intel)
    # =========================================================================
    shared_intel: Dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # YAGS COMPATIBILITY
    # =========================================================================

    # Body & Size (YAGS)
    size: int = 5  # Human default
    body_levels: int = 5  # Typically = size

    # Movement (YAGS)
    move: int = 10  # Movement in meters per round

    # Combat state (YAGS)
    stance: str = "normal"  # "normal", "aggressive", "defensive", "prone"
    defences_declared: int = 0  # Number of active defences this round

    def __post_init__(self):
        """Initialize derived stats."""
        # Calculate base soak if not set
        if self.soak == 0:
            self.soak = self._calculate_base_soak()

        # Add armor bonus to soak
        if self.armor:
            self.soak += self.armor.soak_bonus

    def _calculate_base_soak(self) -> int:
        """
        Calculate base soak (YAGS).

        Base Soak = (Health × 2) / 5
        For size 5 humans with typical health: 12
        """
        health_attr = self.attributes.get('Health', self.size)
        return int((health_attr * 2) / 5) * 5  # Round to nearest 5

    def get_health_percentage(self) -> int:
        """Get current health as percentage."""
        if self.max_health == 0:
            return 0
        return int((self.health / self.max_health) * 100)

    def is_below_retreat_threshold(self) -> bool:
        """Check if health is below retreat threshold."""
        health_pct = self.get_health_percentage() / 100.0
        return health_pct <= self.retreat_threshold

    def apply_damage(self, damage: int, damage_type: str = "wound") -> int:
        """
        Apply damage using YAGS rules.

        YAGS: Damage - Soak, every 5 points = 1 stun/wound
        Tactical Module: 1 wound per hit ≥ Soak, +1 per +5 over

        Args:
            damage: Raw damage roll
            damage_type: "stun", "mixed", or "wound"

        Returns:
            Number of wounds/stuns inflicted
        """
        if damage < self.soak:
            logger.debug(f"{self.name}: Damage {damage} < Soak {self.soak}, no effect")
            return 0

        damage_over_soak = damage - self.soak

        # Tactical Module v1.2.3: 1 wound per hit ≥ Soak, +1 per +5 over
        wounds_inflicted = 1 + (damage_over_soak // 5)

        if damage_type == "wound":
            self.wounds += wounds_inflicted
            self.health -= (wounds_inflicted * 5)  # Approximate health reduction
        elif damage_type == "stun":
            self.stuns += wounds_inflicted
        elif damage_type == "mixed":
            # Split: odd to stuns, even to wounds
            stuns = (wounds_inflicted + 1) // 2
            wounds = wounds_inflicted // 2
            self.stuns += stuns
            self.wounds += wounds
            self.health -= (wounds * 5)

        logger.info(f"{self.name}: Took {wounds_inflicted} {damage_type} damage ({damage} vs soak {self.soak})")

        return wounds_inflicted

    def apply_group_attrition(self):
        """
        Reduce unit count based on health loss.

        Formula:
            Units Lost = floor((Max Health - Current Health) / (Max Health / Original Unit Count))
            Current Unit Count = Original Unit Count - Units Lost
        """
        if not self.is_group or self.original_unit_count <= 1:
            return

        health_lost = self.max_health - self.health
        health_per_unit = self.max_health / self.original_unit_count

        units_lost = int(health_lost / health_per_unit)
        new_unit_count = max(0, self.original_unit_count - units_lost)

        if new_unit_count != self.unit_count:
            logger.info(f"{self.name}: Unit count reduced from {self.unit_count} to {new_unit_count}")
            self.unit_count = new_unit_count

    def get_group_damage_bonus(self) -> int:
        """
        Calculate damage bonus for groups.

        +2 per additional unit (max +6)
        """
        if not self.is_group:
            return 0

        bonus = (self.unit_count - 1) * 2
        return min(bonus, 6)

    def roll_initiative(self) -> int:
        """
        Roll initiative for this enemy.

        Tactical Module v1.2.3: (Agility × 4) + d20 (re-rolled each round)
        Natural 1 = Initiative 0
        """
        agility = self.attributes.get('Agility', 2)
        roll = random.randint(1, 20)

        if roll == 1:
            logger.debug(f"{self.name}: Fumbled initiative (natural 1)")
            return 0

        init = (agility * 4) + roll
        logger.debug(f"{self.name}: Initiative {init} (Agility {agility} × 4 + d20({roll}))")

        return init

    def can_use_void_surge(self) -> bool:
        """Check if can use Void Surge ability."""
        return (
            "void_surge" in self.special_abilities and
            self.void_score < self.void_threshold
        )

    def use_void_surge(self) -> int:
        """
        Use Void Surge ability.

        Effect: +4 damage, auto-Shock, +1 Stun to self, +1 Void
        Returns: Damage bonus
        """
        if not self.can_use_void_surge():
            logger.warning(f"{self.name}: Cannot use Void Surge (void score {self.void_score})")
            return 0

        self.void_score += 1
        self.stuns += 1

        logger.info(f"{self.name}: Used Void Surge (void now {self.void_score}, gained 1 stun)")

        return 4  # +4 damage bonus

    def check_void_possession(self) -> bool:
        """
        Check if void score has reached possession level.

        Returns: True if possessed
        """
        if self.void_score >= 10:
            logger.warning(f"{self.name}: VOID POSSESSION at void score {self.void_score}")
            self.status_effects.append("void_possessed")
            self.tactics = "berserk_void"
            self.retreat_threshold = 0.0  # Never retreats
            return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for state persistence."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "template": self.template,
            "is_group": self.is_group,
            "unit_count": self.unit_count,
            "health": self.health,
            "max_health": self.max_health,
            "wounds": self.wounds,
            "position": str(self.position),
            "initiative": self.initiative,
            "void_score": self.void_score,
            "is_active": self.is_active,
            "status_effects": self.status_effects
        }


# =============================================================================
# SHARED INTEL SYSTEM
# =============================================================================

@dataclass
class IntelItem:
    """Single piece of shared tactical intelligence."""
    source_agent: str
    intel: str
    round: int


class SharedIntel:
    """
    Tactical information shared between enemy agents.

    Enables coordination without explicit DM control.
    """

    def __init__(self):
        self.intel_pool: List[IntelItem] = []

    def add_intel(self, source_agent: str, intel: str, round_num: int):
        """Add intelligence from an enemy agent."""
        if intel and intel.strip():
            item = IntelItem(
                source_agent=source_agent,
                intel=intel.strip(),
                round=round_num
            )
            self.intel_pool.append(item)
            logger.debug(f"Shared intel added from {source_agent}: {intel}")

    def get_recent_intel(self, current_round: int, lookback: int = 2) -> List[str]:
        """
        Get intel from recent rounds.

        Args:
            current_round: Current combat round
            lookback: How many rounds back to include

        Returns:
            List of formatted intel strings
        """
        recent = [
            f"From {item.source_agent}: {item.intel}"
            for item in self.intel_pool
            if current_round - item.round <= lookback
        ]
        return recent

    def clear_old_intel(self, current_round: int, max_age: int = 3):
        """Remove stale intelligence."""
        self.intel_pool = [
            item for item in self.intel_pool
            if current_round - item.round <= max_age
        ]
        logger.debug(f"Cleared old intel, {len(self.intel_pool)} items remain")

    def clear_all(self):
        """Clear all intelligence (combat ended)."""
        self.intel_pool.clear()
        logger.debug("All shared intel cleared")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'Position',
    'RingBand',
    'Hemisphere',
    'Weapon',
    'Armor',
    'EnemyAgent',
    'SharedIntel',
    'IntelItem',
    'TACTICAL_DOCTRINES',
    'THREAT_PRIORITIES'
]
