"""
Energy Economy System for Aeonisk YAGS multi-agent gameplay.

Handles:
- Talismanic currencies (Breath, Drip, Grain, Spark)
- Seed lifecycle (Raw → Attuned or → Hollow)
- Ritual altar attunement
- Fuel consumption for powered gear
- Vendor/trader encounters
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SeedType(Enum):
    """Types of Seeds in the Aeonisk economy."""
    RAW = "raw"  # Unstable, degrades over weeks (individual timers: 3-14 sessions)
    ATTUNED = "attuned"  # Ritually stabilized, element-aspected (doesn't decay)
    HOLLOW = "hollow"  # Illicit, from degraded Raw Seeds or forbidden rituals (stable)


class Element(Enum):
    """Elemental aspects for Attuned Seeds."""
    FIRE = "fire"
    WATER = "water"
    AIR = "air"
    EARTH = "earth"
    VOID = "void"  # Dangerous but powerful
    SPIRIT = "spirit"


class VendorType(Enum):
    """Types of vendors/supply sources."""
    HUMAN_TRADER = "human_trader"  # Full service, only in safe zones
    VENDING_MACHINE = "vending_machine"  # Automated, limited selection
    SUPPLY_DRONE = "supply_drone"  # Mobile, works in neutral zones
    EMERGENCY_CACHE = "emergency_cache"  # One-time use, appears in crises


@dataclass
class Seed:
    """
    Represents a single Seed in inventory.

    Each Raw Seed has an individual decay timer (cycles_remaining).
    Seeds degrade 1 cycle per session (week), adding urgency to attunement.
    """
    seed_type: SeedType
    element: Optional[Element] = None  # Only for ATTUNED seeds
    cycles_remaining: int = 10  # For RAW seeds (varies: fresh=10-14, aged=3-6)
    origin: str = "unknown"  # Where it came from

    def degrade(self, cycles: int = 1) -> bool:
        """
        Degrade a Raw Seed by given cycles (1 cycle = 1 session/week).
        Returns True if it becomes a Hollow.
        """
        if self.seed_type != SeedType.RAW:
            return False

        self.cycles_remaining -= cycles

        if self.cycles_remaining <= 0:
            self.seed_type = SeedType.HOLLOW
            self.element = None
            logger.info(f"Raw Seed degraded into Hollow (origin: {self.origin})")
            return True

        return False

    def as_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'type': self.seed_type.value,
            'element': self.element.value if self.element else None,
            'cycles_remaining': self.cycles_remaining if self.seed_type == SeedType.RAW else None,
            'origin': self.origin
        }


def create_raw_seed(origin: str, freshness: str = "random") -> Seed:
    """
    Create a Raw Seed with varying freshness.

    Args:
        origin: Where the seed came from
        freshness: "fresh", "aged", "old", or "random"

    Returns:
        Seed with appropriate cycles_remaining (3-14 sessions)
    """
    if freshness == "fresh":
        cycles = random.randint(10, 14)
        quality = "fresh"
    elif freshness == "aged":
        cycles = random.randint(6, 9)
        quality = "aged"
    elif freshness == "old":
        cycles = random.randint(3, 5)
        quality = "old"
    else:  # random
        cycles = random.randint(3, 14)
        # Determine quality label based on cycles
        if cycles >= 10:
            quality = "fresh"
        elif cycles >= 6:
            quality = "aged"
        else:
            quality = "old"

    logger.info(f"Created {quality} Raw Seed ({cycles} cycles remaining, origin: {origin})")

    return Seed(
        seed_type=SeedType.RAW,
        cycles_remaining=cycles,
        origin=origin
    )


@dataclass
class EnergyInventory:
    """
    Tracks all energy currencies and seeds for a character.

    Currency hierarchy (smallest → largest):
    - Breath (smallest)
    - Drip
    - Grain
    - Spark (largest standard unit)

    Market rate: 1 Spark ≈ 2-5 Drips (varies by location)
    """
    # Talismanic currencies
    breath: int = 5
    drip: int = 10
    grain: int = 3
    spark: int = 2

    # Seeds (list of Seed objects)
    seeds: List[Seed] = field(default_factory=list)

    # Conversion rates (for standard markets)
    drips_per_spark: int = 3  # Market-dependent (2-5 range)
    grains_per_spark: int = 2
    breaths_per_drip: int = 4

    def add_currency(self, currency_type: str, amount: int):
        """Add currency to inventory."""
        if currency_type == "breath":
            self.breath += amount
        elif currency_type == "drip":
            self.drip += amount
        elif currency_type == "grain":
            self.grain += amount
        elif currency_type == "spark":
            self.spark += amount
        logger.info(f"Added {amount} {currency_type} to inventory")

    def spend_currency(self, currency_type: str, amount: int) -> bool:
        """
        Spend currency from inventory.
        Returns True if successful, False if insufficient funds.
        """
        if currency_type == "breath":
            if self.breath >= amount:
                self.breath -= amount
                logger.info(f"Spent {amount} breath")
                return True
        elif currency_type == "drip":
            if self.drip >= amount:
                self.drip -= amount
                logger.info(f"Spent {amount} drip")
                return True
        elif currency_type == "grain":
            if self.grain >= amount:
                self.grain -= amount
                logger.info(f"Spent {amount} grain")
                return True
        elif currency_type == "spark":
            if self.spark >= amount:
                self.spark -= amount
                logger.info(f"Spent {amount} spark")
                return True

        logger.warning(f"Insufficient {currency_type} (needed {amount})")
        return False

    def transfer_currency_to(self, other_inventory: 'EnergyInventory', currency_type: str, amount: int) -> bool:
        """
        Transfer currency from this inventory to another.
        Returns True if successful, False if insufficient funds.
        """
        if self.spend_currency(currency_type, amount):
            other_inventory.add_currency(currency_type, amount)
            logger.info(f"Transferred {amount} {currency_type} to another character")
            return True
        return False

    def convert_currency(self, from_type: str, to_type: str, amount: int) -> bool:
        """
        Convert between currency types using market rates.
        Also supports Hollow Seeds as tradeable commodities.
        Returns True if successful.
        """
        # Handle Hollow Seed conversions (illicit energy commodity)
        if from_type == "hollow":
            # 1 Hollow Seed ≈ 4-6 Drips (black market rate)
            hollow_value_drips = 5
            seed = self.consume_seed(SeedType.HOLLOW)
            if not seed:
                logger.warning("No Hollow Seed available to trade")
                return False

            # Convert to target currency
            if to_type == "drip":
                self.add_currency("drip", hollow_value_drips * amount)
            elif to_type == "spark":
                sparks = (hollow_value_drips * amount) // self.drips_per_spark
                self.add_currency("spark", sparks)
            elif to_type == "breath":
                breaths = hollow_value_drips * amount * self.breaths_per_drip
                self.add_currency("breath", breaths)
            else:
                logger.error(f"Cannot convert Hollow to {to_type}")
                # Refund the seed
                self.add_seed(seed)
                return False

            logger.info(f"Traded Hollow Seed for {to_type}")
            return True

        # Standard currency conversions
        conversions = {
            ('spark', 'drip'): lambda x: x * self.drips_per_spark,
            ('drip', 'spark'): lambda x: x // self.drips_per_spark,
            ('spark', 'grain'): lambda x: x * self.grains_per_spark,
            ('grain', 'spark'): lambda x: x // self.grains_per_spark,
            ('drip', 'breath'): lambda x: x * self.breaths_per_drip,
            ('breath', 'drip'): lambda x: x // self.breaths_per_drip,
            ('grain', 'drip'): lambda x: x * 2,  # 1 Grain ≈ 2 Drips
            ('drip', 'grain'): lambda x: x // 2,
            ('spark', 'breath'): lambda x: x * self.drips_per_spark * self.breaths_per_drip,
            ('breath', 'spark'): lambda x: x // (self.drips_per_spark * self.breaths_per_drip),
            ('grain', 'breath'): lambda x: x * 2 * self.breaths_per_drip,
            ('breath', 'grain'): lambda x: x // (2 * self.breaths_per_drip),
        }

        conversion_key = (from_type, to_type)
        if conversion_key not in conversions:
            logger.error(f"No conversion path from {from_type} to {to_type}")
            return False

        # Check if we have enough to convert
        if not self.spend_currency(from_type, amount):
            return False

        # Calculate converted amount
        converted = conversions[conversion_key](amount)
        if converted == 0:
            logger.warning(f"Conversion too small: {amount} {from_type} → 0 {to_type}")
            # Refund
            self.add_currency(from_type, amount)
            return False

        self.add_currency(to_type, converted)
        logger.info(f"Converted {amount} {from_type} → {converted} {to_type}")
        return True

    def add_seed(self, seed: Seed):
        """Add a Seed to inventory."""
        self.seeds.append(seed)
        logger.info(f"Added {seed.seed_type.value} seed to inventory")

    def consume_seed(self, seed_type: SeedType, element: Optional[Element] = None) -> Optional[Seed]:
        """
        Consume a seed from inventory.
        Returns the Seed if found, None otherwise.
        """
        for i, seed in enumerate(self.seeds):
            if seed.seed_type == seed_type:
                # If requesting Attuned, check element match
                if seed_type == SeedType.ATTUNED:
                    if element and seed.element != element:
                        continue
                # Found matching seed
                return self.seeds.pop(i)

        logger.warning(f"No {seed_type.value} seed available")
        return None

    def degrade_raw_seeds(self, cycles: int = 1):
        """
        Degrade all Raw Seeds by given cycles (1 cycle = 1 session/week).

        Each Raw Seed has an individual timer, so some may become Hollow
        while others remain viable. Seeds purchased or found might already
        be partially degraded, adding urgency to attunement.

        Called automatically at the start of each game session.
        """
        for seed in self.seeds:
            if seed.seed_type == SeedType.RAW:
                seed.degrade(cycles)

    def count_seeds(self, seed_type: SeedType, element: Optional[Element] = None) -> int:
        """Count seeds of a given type (and element if specified)."""
        count = 0
        for seed in self.seeds:
            if seed.seed_type == seed_type:
                if element is None or seed.element == element:
                    count += 1
        return count

    def as_dict(self) -> Dict[str, Any]:
        """Serialize inventory to dictionary."""
        return {
            'currencies': {
                'breath': self.breath,
                'drip': self.drip,
                'grain': self.grain,
                'spark': self.spark
            },
            'seeds': [seed.as_dict() for seed in self.seeds],
            'seed_counts': {
                'raw': self.count_seeds(SeedType.RAW),
                'attuned': self.count_seeds(SeedType.ATTUNED),
                'hollow': self.count_seeds(SeedType.HOLLOW)
            }
        }


@dataclass
class VendorItem:
    """Item available for purchase from a vendor."""
    name: str
    description: str
    price_spark: int = 0
    price_drip: int = 0
    price_breath: int = 0
    seed_barter: bool = False  # Can trade seeds for this
    item_type: str = "consumable"  # consumable, tool, seed, etc.

    def get_price_string(self) -> str:
        """Get formatted price string."""
        prices = []
        if self.price_spark > 0:
            prices.append(f"{self.price_spark} Spark")
        if self.price_drip > 0:
            prices.append(f"{self.price_drip} Drip")
        if self.price_breath > 0:
            prices.append(f"{self.price_breath} Breath")
        if self.seed_barter:
            prices.append("1 Attuned Seed")
        return " or ".join(prices) if prices else "Free"


class Vendor:
    """
    Represents a trader/merchant that characters can encounter.
    """
    def __init__(
        self,
        name: str,
        faction: str,
        inventory: List[VendorItem],
        greeting: str = "Looking to trade?",
        vendor_type: VendorType = VendorType.HUMAN_TRADER
    ):
        self.name = name
        self.faction = faction
        self.inventory = inventory
        self.greeting = greeting
        self.vendor_type = vendor_type

    def get_inventory_display(self) -> str:
        """Get formatted vendor inventory for display."""
        lines = [f"[{self.name}] {self.greeting}\n"]
        lines.append("=== Inventory ===")

        for i, item in enumerate(self.inventory, 1):
            lines.append(f"{i}. {item.name} - {item.get_price_string()}")
            lines.append(f"   {item.description}")

        return "\n".join(lines)

    def sell_item(self, item_index: int, buyer_inventory: EnergyInventory) -> Optional[VendorItem]:
        """
        Attempt to sell an item to the buyer.
        Returns the item if successful, None if transaction failed.
        """
        if item_index < 0 or item_index >= len(self.inventory):
            logger.error(f"Invalid item index: {item_index}")
            return None

        item = self.inventory[item_index]

        # Try paying with Spark first
        if item.price_spark > 0:
            if buyer_inventory.spend_currency('spark', item.price_spark):
                logger.info(f"Purchased {item.name} for {item.price_spark} Spark")
                return item

        # Try paying with Drip
        if item.price_drip > 0:
            if buyer_inventory.spend_currency('drip', item.price_drip):
                logger.info(f"Purchased {item.name} for {item.price_drip} Drip")
                return item

        # Try paying with Breath
        if item.price_breath > 0:
            if buyer_inventory.spend_currency('breath', item.price_breath):
                logger.info(f"Purchased {item.name} for {item.price_breath} Breath")
                return item

        # Try Seed barter
        if item.seed_barter:
            seed = buyer_inventory.consume_seed(SeedType.ATTUNED)
            if seed:
                logger.info(f"Bartered {item.name} for Attuned Seed")
                return item

        logger.warning(f"Transaction failed: insufficient funds for {item.name}")
        return None


def create_standard_vendors() -> List[Vendor]:
    """Create a pool of standard vendors for encounters."""
    vendors = []

    # ===== HUMAN TRADERS (Safe zones only) =====

    # Ritual Merchant (Neutral)
    ritual_merchant = Vendor(
        name="Scribe Orven Tylesh",
        faction="Neutral",
        vendor_type=VendorType.HUMAN_TRADER,
        inventory=[
            VendorItem("Echo-Calibrator", "Tech alternative to altar (DC 16 Dex+Tech)", price_spark=8),
            VendorItem("Purification Incense (Bundle)", "High-grade ritual cleansing", price_drip=8),
            VendorItem("Talisman Blanks (x5)", "Premium ritual substrates", price_spark=1),
            VendorItem("Attuned Seed (Fire)", "Stable flame-aspected seed", price_spark=2, item_type="seed"),
            VendorItem("Attuned Seed (Water)", "Stable water-aspected seed", price_spark=2, item_type="seed"),
            VendorItem("Echo Shard", "Stores one dream echo", price_spark=3),
            VendorItem("Ley-Reader Compass", "Points to nearest ley node", price_spark=4),
            VendorItem("Warding Cord", "Repels minor mnemonic bleed", price_drip=6),
        ],
        greeting="Seeking clarity? I trade in resonance and remembrance."
    )
    vendors.append(ritual_merchant)

    # Underground Broker (Freeborn)
    underground_broker = Vendor(
        name="\"Cipher\" (masked)",
        faction="Freeborn",
        vendor_type=VendorType.HUMAN_TRADER,
        inventory=[
            VendorItem("Hollow Seed", "Raw void energy (unstable)", price_drip=5, item_type="seed"),
            VendorItem("Void Cloak", "Harder to track spiritually", price_spark=6),
            VendorItem("Scrambled ID Chip", "Temporary anonymity", price_spark=4),
            VendorItem("Memory Wipe Kit", "Erase recent events (risky)", price_spark=10),
            VendorItem("Breach Compass", "Navigates unstable void zones", price_drip=15),
            VendorItem("Null Dampener", "Suppresses ritual signatures", price_spark=7),
        ],
        greeting="*Static whisper* Looking for what the Codex won't sell you?"
    )
    vendors.append(underground_broker)

    # Corporate Liaison (ACG)
    corporate_liaison = Vendor(
        name="Contract Specialist Rhen",
        faction="Astral Commerce Group",
        vendor_type=VendorType.HUMAN_TRADER,
        inventory=[
            VendorItem("Soulcredit Report (Detailed)", "Full ledger analysis", price_spark=3),
            VendorItem("Bond Insurance Policy", "Protect against bond damage", price_spark=12),
            VendorItem("Debt Consolidation Service", "Restructure obligations", price_spark=15),
            VendorItem("Spark Vault (Small)", "Secure energy storage", price_spark=5),
            VendorItem("Contract Templates (Legal)", "Pre-approved bond forms", price_drip=8),
        ],
        greeting="Let's optimize your spiritual portfolio. Everything's negotiable."
    )
    vendors.append(corporate_liaison)

    # Currency Exchange (Neutral)
    currency_exchange = Vendor(
        name="Talisman Exchanger Vess",
        faction="Neutral",
        vendor_type=VendorType.HUMAN_TRADER,
        inventory=[
            VendorItem("Currency Exchange Service", "Convert Spark/Drip/Grain/Breath (small fee)", price_breath=5),
            VendorItem("Hollow Seed (Buy)", "Purchase illicit energy", price_drip=6, item_type="seed"),
            VendorItem("Hollow Seed (Sell)", "Trade Hollow for Drips (5 Drip each)", price_drip=0, item_type="exchange"),
            VendorItem("Spark Vault", "Secure high-value storage", price_spark=4),
            VendorItem("Drip Canister (x10)", "Portable liquid energy", price_spark=2),
            VendorItem("Breath Compressor", "Store gaseous energy", price_drip=8),
        ],
        greeting="Fair rates, clean ledger. Spark to Drip? Drip to Breath? I handle it all."
    )
    vendors.append(currency_exchange)

    # ===== VENDING MACHINES (Neutral/action zones) =====

    # General supplies vending
    general_vending = Vendor(
        name="S4CU Vending Node (Supplies)",
        faction="Neutral",
        vendor_type=VendorType.VENDING_MACHINE,
        inventory=[
            VendorItem("Breathwater Flask", "Distilled air-essence, calming", price_drip=2),
            VendorItem("Dripfruit Chews", "Mood-softening candy", price_drip=1),
            VendorItem("Med Kit (Basic)", "Emergency medical supplies", price_drip=5),
            VendorItem("Ration Pack", "Standard survival rations", price_drip=2),
            VendorItem("Glowsticks (x3)", "Emergency lighting", price_breath=8),
            VendorItem("Comm Unit (Disposable)", "One-use communicator", price_drip=3),
        ],
        greeting="[S4CU-STANDARD] Currency accepted. Product dispensed. Thank you."
    )
    vendors.append(general_vending)

    # Ritual supplies vending
    ritual_vending = Vendor(
        name="Temple Node (Ritual Goods)",
        faction="Sovereign Nexus",
        vendor_type=VendorType.VENDING_MACHINE,
        inventory=[
            VendorItem("Ritual Altar Access (1hr)", "Temple altar booking", price_spark=1),
            VendorItem("Incense Stick (Single)", "Basic ritual cleansing", price_breath=10),
            VendorItem("Ley-Chalk (3pk)", "Temporary glyph drawing", price_drip=2),
            VendorItem("Whisper Wax Tablet", "Breath-activated recording", price_breath=15),
            VendorItem("Talisman Blank", "Single ritual substrate", price_drip=3),
            VendorItem("Blessing Sponge", "Altar preparation cloth", price_breath=6),
            VendorItem("Mini-Bond Bowl", "Portable ritual altar", price_drip=10, seed_barter=True),
        ],
        greeting="[TEMPLE-NODE-7] Sanctified goods available. Soulcredit verified."
    )
    vendors.append(ritual_vending)

    # Food/entertainment vending
    food_vending = Vendor(
        name="SnackHub Express",
        faction="Neutral",
        vendor_type=VendorType.VENDING_MACHINE,
        inventory=[
            VendorItem("Echo-Crackers", "Joy-infused crunchy snack", price_breath=4),
            VendorItem("Glowpeel Noodles (Instant)", "Spark-dust spiced noodles", price_drip=2),
            VendorItem("Hollow Cone (Dessert)", "Void-cream ice cream cone", price_drip=3),
            VendorItem("Ley Pop (Sourwave)", "Fizzes near emotions", price_breath=5),
            VendorItem("Sparksticks", "Addictive buzz twigs", price_breath=3),
            VendorItem("Reviv-Essence Lozenges", "Stimulant tabs", price_drip=4),
        ],
        greeting="[SNACKHUB] Fresh today! Insert Drips for instant gratification."
    )
    vendors.append(food_vending)

    # Specialized tech vending
    tech_vending = Vendor(
        name="ArcGen BioTech Dispenser",
        faction="Arcane Genetics",
        vendor_type=VendorType.VENDING_MACHINE,
        inventory=[
            VendorItem("Echo-Calibrator (Compact)", "Portable seed stabilizer (DC 16)", price_spark=7),
            VendorItem("Neural Stimulant", "Cognitive boost (4hr)", price_drip=4),
            VendorItem("Genetic Sample Kit", "DNA collection tools", price_drip=6),
            VendorItem("Resonance Tuner (Portable)", "Adjust personal frequencies", price_spark=3),
            VendorItem("Bio-Sensor Patch", "Monitors vital signs", price_drip=5),
            VendorItem("Void-Cut Tea (Synthetic)", "Forbidden ritual simulacrum", price_drip=2),
        ],
        greeting="[ARCGEN-BIOTECH] Premium enhancement products. Waiver required."
    )
    vendors.append(tech_vending)

    # ===== SUPPLY DRONES (Action zones, mobile) =====

    security_drone = Vendor(
        name="Pantheon Field Supply Drone P-19",
        faction="Pantheon Security",
        vendor_type=VendorType.SUPPLY_DRONE,
        inventory=[
            VendorItem("Union Heavy Pistol", "Standard issue sidearm", price_spark=6),
            VendorItem("Riot Carapace (Armor)", "Blast-resistant body armor", price_spark=10),
            VendorItem("Dripshock Baton", "Non-lethal crowd control", price_spark=3),
            VendorItem("Med Kit (Tactical)", "Combat-grade medical", price_drip=6),
            VendorItem("Restraint Cuffs", "Detain suspects", price_drip=8),
            VendorItem("Void Scanner (Basic)", "Detect corruption", price_spark=4),
            VendorItem("Signal Flare", "Call for backup", price_drip=4),
        ],
        greeting="[P-19 FIELD UNIT] Authorized personnel: state requisition code."
    )
    vendors.append(security_drone)

    delivery_drone = Vendor(
        name="House of Vox Courier Drone",
        faction="House of Vox",
        vendor_type=VendorType.SUPPLY_DRONE,
        inventory=[
            VendorItem("Data Slate (Encrypted)", "Secure information storage", price_drip=10),
            VendorItem("Whisper Capsules", "Ambient dream audio", price_drip=5),
            VendorItem("Broadcast Access Chip (Temp)", "1-hour media access", price_spark=2),
            VendorItem("Echo-Quill", "Writes intent, not words", price_drip=7),
            VendorItem("Glow-Beads (x10)", "React to emotional agitation", price_breath=12),
        ],
        greeting="[VOX-COURIER] Express delivery. Subscription discount available."
    )
    vendors.append(delivery_drone)

    # ===== EMERGENCY CACHE (Crisis only, one-time) =====

    emergency_cache = Vendor(
        name="Emergency Supply Cache (Pantheon)",
        faction="Pantheon Security",
        vendor_type=VendorType.EMERGENCY_CACHE,
        inventory=[
            VendorItem("Med Kit", "Emergency medical supplies", price_drip=0),
            VendorItem("Ration Pack (x3)", "Survival rations", price_drip=0),
            VendorItem("Signal Flare", "Call for help", price_drip=0),
            VendorItem("Purification Incense", "Ritual cleansing", price_drip=0),
        ],
        greeting="[EMERGENCY CACHE] Crisis protocol active. Take what you need."
    )
    vendors.append(emergency_cache)

    return vendors


# Export key classes
__all__ = [
    'SeedType',
    'Element',
    'VendorType',
    'Seed',
    'EnergyInventory',
    'VendorItem',
    'Vendor',
    'create_standard_vendors'
]
