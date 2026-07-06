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
from pydantic import BaseModel, Field, field_validator, ConfigDict

logger = logging.getLogger(__name__)


def generate_vendor_id() -> str:
    """
    Generate unique vendor ID: vnd_xxxx

    Format: vnd_ + 4 random alphanumeric characters
    Example: vnd_a3kf
    """
    import string
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"vnd_{suffix}"


def generate_item_id() -> str:
    """
    Generate unique item ID: itm_xxxx

    Format: itm_ + 4 random alphanumeric characters
    Example: itm_c9x2
    """
    import string
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"itm_{suffix}"


def item_name_to_inventory_key(item_name: str) -> str:
    """
    Convert item name to inventory key.

    Examples:
    - "Echo-Calibrator" → "echo_calibrator"
    - "Med Kit (Basic)" → "med_kit_basic"
    - "Attuned Seed (Fire)" → "attuned_seed_fire"
    """
    # Remove parentheses content but keep it for keys
    import re
    # Replace parentheses with underscores
    key = item_name.replace('(', '_').replace(')', '')
    # Convert to lowercase, replace spaces and hyphens with underscores
    key = key.lower().replace(' ', '_').replace('-', '_')
    # Remove multiple consecutive underscores
    key = re.sub(r'_+', '_', key)
    # Strip leading/trailing underscores
    key = key.strip('_')
    return key


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


class ItemType(Enum):
    """
    Item categories for vendor inventory.

    Used to:
    - Validate CONSUME actions (only food items can be eaten)
    - Distinguish mechanical items (tools, offerings) from narrative props
    - Enable item filtering in inventory systems
    """
    CONSUMABLE = "consumable"  # Generic consumables (medkit, stims, etc.) - NO auto-heal
    FOOD = "food"  # Consumable food items - grants +2 HP when eaten via CONSUME action
    TOOL = "tool"  # Equipment and tools (Echo-Calibrator, multitool, etc.)
    SEED = "seed"  # Attuned/Hollow seeds for trading
    OFFERING = "offering"  # Ritual consumables (incense, blood offerings, etc.)
    EXCHANGE = "exchange"  # Currency conversion services
    PROP = "prop"  # Narrative/story items with no mechanical effects
    EQUIPMENT = "equipment"  # Wearable gear, weapons, armor


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
class EnergyPurse:
    """
    Tracks all energy currencies and seeds for a character.

    Currency hierarchy (smallest → largest):
    - Breath (smallest)
    - Drip
    - Grain
    - Spark (largest standard unit)
    - Hollow (illicit void energy, 3x power, +1 Void per use)

    Market rate: 1 Spark ≈ 2-5 Drips (varies by location)
    """
    # Talismanic currencies
    breath: int = 5
    drip: int = 10
    grain: int = 3
    spark: int = 2
    hollow: int = 0  # Void energy (illicit)

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
        elif currency_type == "hollow":
            self.hollow += amount
        logger.debug(f"Added {amount} {currency_type} to inventory")

    def spend_currency(self, currency_type: str, amount: int) -> bool:
        """
        Spend currency from inventory.
        Returns True if successful, False if insufficient funds.
        """
        if currency_type == "breath":
            if self.breath >= amount:
                self.breath -= amount
                logger.debug(f"Spent {amount} breath")
                return True
        elif currency_type == "drip":
            if self.drip >= amount:
                self.drip -= amount
                logger.debug(f"Spent {amount} drip")
                return True
        elif currency_type == "grain":
            if self.grain >= amount:
                self.grain -= amount
                logger.debug(f"Spent {amount} grain")
                return True
        elif currency_type == "spark":
            if self.spark >= amount:
                self.spark -= amount
                logger.debug(f"Spent {amount} spark")
                return True
        elif currency_type == "hollow":
            if self.hollow >= amount:
                self.hollow -= amount
                logger.debug(f"Spent {amount} hollow")
                return True

        logger.warning(f"Insufficient {currency_type} (needed {amount})")
        return False

    def transfer_currency_to(self, other_inventory: 'EnergyPurse', currency_type: str, amount: int) -> bool:
        """
        Transfer currency from this inventory to another.
        Returns True if successful, False if insufficient funds.
        """
        if self.spend_currency(currency_type, amount):
            other_inventory.add_currency(currency_type, amount)
            logger.debug(f"Transferred {amount} {currency_type} to another character")
            return True
        return False

    def transfer_currencies_to(self, receiver_purse: 'EnergyPurse', currency_amounts: dict[str, int]) -> bool:
        """
        Transfer multiple currencies from this purse to another.

        Args:
            receiver_purse: Destination EnergyPurse
            currency_amounts: Dict of {currency_type: amount}, e.g. {"drip": 5, "spark": 2}

        Returns:
            True if all transfers succeeded, False if any failed
        """
        # First check we have enough of all currencies
        for currency_type, amount in currency_amounts.items():
            current_amount = getattr(self, currency_type, 0)
            if current_amount < amount:
                logger.warning(f"Insufficient {currency_type} for transfer (have {current_amount}, need {amount})")
                return False

        # All checks passed - execute transfers
        for currency_type, amount in currency_amounts.items():
            if amount > 0:
                success = self.transfer_currency_to(receiver_purse, currency_type, amount)
                if not success:
                    # This shouldn't happen since we pre-checked, but handle it
                    logger.error(f"Transfer failed for {currency_type} despite pre-check")
                    return False

        return True

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
        logger.debug(f"Added {seed.seed_type.value} seed to inventory")

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

        Each Raw Seed has an individual timer. When a seed reaches 0 cycles,
        it degrades into Hollow energy (void-corrupted, illicit currency).

        Seeds purchased or found might already be partially degraded,
        adding urgency to attunement.

        Called automatically at the start of each game session.
        """
        seeds_to_remove = []

        for i, seed in enumerate(self.seeds):
            if seed.seed_type == SeedType.RAW:
                # Degrade the seed
                seed.cycles_remaining -= cycles

                # If fully degraded, convert to Hollow currency
                if seed.cycles_remaining <= 0:
                    self.hollow += 1
                    seeds_to_remove.append(i)
                    logger.info(f"Raw Seed degraded into Hollow (origin: {seed.origin})")

        # Remove degraded seeds (reverse order to preserve indices)
        for i in reversed(seeds_to_remove):
            self.seeds.pop(i)

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
                'spark': self.spark,
                'hollow': self.hollow
            },
            'seeds': [seed.as_dict() for seed in self.seeds],
            'seed_counts': {
                'raw': self.count_seeds(SeedType.RAW),
                'attuned': self.count_seeds(SeedType.ATTUNED)
            }
        }


class VendorItem(BaseModel):
    """
    Item available for purchase from a vendor.

    Now a Pydantic model for proper validation of:
    - Required fields (name, description)
    - Non-negative prices (all currency fields)
    - Hollow currency support (price_hollow)
    - Item type categorization (food, prop, tool, etc.)
    """
    name: str = Field(..., min_length=1, max_length=100, description="Item name (e.g., 'Medkit', 'Ration Pack')")
    description: str = Field(..., min_length=1, max_length=500, description="Item description for players")
    item_id: Optional[str] = Field(None, description="Auto-generated if not provided (itm_xxxx)")
    inventory_key: Optional[str] = Field(None, description="Auto-generated from name if not provided")
    price_spark: int = Field(0, ge=0, description="Cost in Spark (highest tier currency)")
    price_grain: int = Field(0, ge=0, description="Cost in Grain")
    price_drip: int = Field(0, ge=0, description="Cost in Drip")
    price_breath: int = Field(0, ge=0, description="Cost in Breath (lowest tier currency)")
    price_hollow: int = Field(0, ge=0, description="Cost in Hollow currency (illicit void energy)")
    seed_barter: bool = Field(False, description="Can trade attuned seeds for this item")
    item_type: str = Field("consumable", description="Item category: consumable, food, tool, seed, offering, exchange, prop, equipment")
    soulcredit_requirement: int = Field(0, description="Minimum Soulcredit standing to buy this item (sanctioned/licensed gear). Enforced only at Nexus-aligned vendors (VIII.1). 0 = no standing gate.")

    model_config = ConfigDict(
        validate_assignment=True,  # Validate on attribute assignment
        extra="forbid"  # Reject extra fields
    )

    def model_post_init(self, __context):
        """Auto-generate item_id and inventory_key if not provided (Pydantic equivalent of __post_init__)."""
        if self.item_id is None:
            object.__setattr__(self, 'item_id', generate_item_id())
        if self.inventory_key is None:
            object.__setattr__(self, 'inventory_key', item_name_to_inventory_key(self.name))

    @property
    def cost(self) -> Dict[str, int]:
        """Get cost as a dictionary for validation."""
        cost_dict = {}
        if self.price_spark > 0:
            cost_dict['spark'] = self.price_spark
        if self.price_grain > 0:
            cost_dict['grain'] = self.price_grain
        if self.price_drip > 0:
            cost_dict['drip'] = self.price_drip
        if self.price_breath > 0:
            cost_dict['breath'] = self.price_breath
        if self.price_hollow > 0:
            cost_dict['hollow'] = self.price_hollow
        return cost_dict

    def get_price_string(self) -> str:
        """Get formatted price string."""
        prices = []
        if self.price_spark > 0:
            prices.append(f"{self.price_spark} Spark")
        if self.price_drip > 0:
            prices.append(f"{self.price_drip} Drip")
        if self.price_breath > 0:
            prices.append(f"{self.price_breath} Breath")
        if self.price_hollow > 0:
            prices.append(f"{self.price_hollow} Hollow")
        if self.seed_barter:
            prices.append("1 Attuned Seed")
        return " or ".join(prices) if prices else "Free"


# Nexus-aligned institutions gate service on Soulcredit standing (Codex Nexum
# VIII.1 / VI.1). Freeborn, Tempest-adjacent, and Independent markets do not ask.
# Names are normalized (lowercased, stripped) before lookup; aliases included.
NEXUS_ALIGNED_FACTIONS = frozenset({
    "sovereign nexus", "nexus",
    "arcane genetics", "arcgen",
    "pantheon security", "pantheon",
    "astral commerce group", "acg",
    "aether dynamics", "aethyr dynamics",
})


def is_nexus_aligned(faction: Optional[str]) -> bool:
    """True if a vendor/institution of this faction checks the Codex ledger
    before serving (VIII.1). Unknown/empty factions are treated as unaligned."""
    if not faction:
        return False
    return faction.strip().lower() in NEXUS_ALIGNED_FACTIONS


# Codex Nexum VIII.2: Soulcredit -6 and under is Cut Off from polite society.
SOULCREDIT_CUT_OFF = -6


@dataclass
class Checkpoint:
    """A gated checkpoint / sector / service access point (VIII.1).

    Nexus-aligned checkpoints check the ledger and apply the universal Cut-Off
    (SC <= -6). Any checkpoint may set its own soulcredit_requirement (a
    standing floor to pass); 0 means no explicit requirement.
    """
    checkpoint_id: str
    name: str
    faction: str
    soulcredit_requirement: int = 0
    description: str = ""


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
        vendor_type: VendorType = VendorType.HUMAN_TRADER,
        vendor_id: Optional[str] = None  # Auto-generated if not provided
    ):
        self.vendor_id = vendor_id if vendor_id else generate_vendor_id()
        self.name = name
        self.faction = faction
        self.inventory = inventory
        self.greeting = greeting
        self.vendor_type = vendor_type

    def get_item_by_id(self, item_id: str) -> Optional[VendorItem]:
        """
        Lookup item by ID in vendor inventory.

        Args:
            item_id: Item ID to search for (itm_xxxx)

        Returns:
            VendorItem if found, None otherwise
        """
        for item in self.inventory:
            if item.item_id == item_id:
                return item
        return None

    def get_inventory_display(self) -> str:
        """Get formatted vendor inventory for display."""
        lines = [f"[{self.name}] {self.greeting}\n"]
        lines.append("=== Inventory ===")

        for i, item in enumerate(self.inventory, 1):
            lines.append(f"{i}. {item.name} - {item.get_price_string()}")
            lines.append(f"   {item.description}")

        return "\n".join(lines)

    def sell_item(self, item_index: int, buyer_inventory: EnergyPurse) -> Optional[VendorItem]:
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


def create_test_vendor() -> Vendor:
    """
    Create minimal test vendor for unit testing purchase system.

    Returns a simple vending machine with 3 basic items.
    """
    test_items = [
        VendorItem(
            name="Health Kit",
            description="Restores 10 HP",
            price_drip=5,
            item_type="consumable"
        ),
        VendorItem(
            name="Energy Cell",
            description="Restores 20 energy",
            price_drip=3,
            price_breath=8,
            item_type="consumable"
        ),
        VendorItem(
            name="Spark Cell",
            description="High-power energy cell",
            price_spark=1,
            item_type="consumable"
        )
    ]

    return Vendor(
        name="Test Vend-O-Mat",
        faction="Nexus",
        inventory=test_items,
        greeting="Testing purchases...",
        vendor_type=VendorType.VENDING_MACHINE
    )


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
            VendorItem(name="Echo-Calibrator", description="Portable seed stabilizer (DC 16 Dex+Tech, 1 Drip per 3 uses)", price_spark=8, item_type="tool"),
            VendorItem(name="Purification Incense (Bundle)", description="High-grade ritual cleansing", price_drip=8, item_type="offering"),
            VendorItem(name="Talisman Blanks (x5)", description="Premium ritual substrates", price_spark=1),
            VendorItem(name="Attuned Seed (Fire)", description="Stable flame-aspected seed", price_spark=2, item_type="seed"),
            VendorItem(name="Attuned Seed (Water)", description="Stable water-aspected seed", price_spark=2, item_type="seed"),
            VendorItem(name="Echo Shard", description="Stores one dream echo", price_spark=3),
            VendorItem(name="Ley-Reader Compass", description="Points to nearest ley node", price_spark=4),
            VendorItem(name="Warding Cord", description="Repels minor mnemonic bleed", price_drip=6),
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
            VendorItem(name="Hollow Seed", description="Raw void energy (unstable)", price_drip=5, item_type="seed"),
            VendorItem(name="Void Cloak", description="Harder to track spiritually", price_spark=6),
            VendorItem(name="Scrambled ID Chip", description="Temporary anonymity", price_spark=4),
            VendorItem(name="Memory Wipe Kit", description="Erase recent events (risky)", price_spark=10),
            VendorItem(name="Breach Compass", description="Navigates unstable void zones", price_drip=15),
            VendorItem(name="Null Dampener", description="Suppresses ritual signatures", price_spark=7),
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
            VendorItem(name="Soulcredit Report (Detailed)", description="Full ledger analysis", price_spark=3),
            VendorItem(name="Bond Insurance Policy", description="Protect against bond damage", price_spark=12),
            VendorItem(name="Debt Consolidation Service", description="Restructure obligations", price_spark=15),
            VendorItem(name="Spark Vault (Small)", description="Secure energy storage", price_spark=5),
            VendorItem(name="Contract Templates (Legal)", description="Pre-approved bond forms", price_drip=8),
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
            VendorItem(name="Currency Exchange Service", description="Convert Spark/Drip/Grain/Breath (small fee)", price_breath=5),
            VendorItem(name="Hollow Seed (Buy)", description="Purchase illicit energy", price_drip=6, item_type="seed"),
            VendorItem(name="Hollow Seed (Sell)", description="Trade Hollow for Drips (5 Drip each)", price_drip=0, item_type="exchange"),
            VendorItem(name="Spark Vault", description="Secure high-value storage", price_spark=4),
            VendorItem(name="Drip Canister (x10)", description="Portable liquid energy", price_spark=2),
            VendorItem(name="Breath Compressor", description="Store gaseous energy", price_drip=8),
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
            VendorItem(name="Breathwater Flask", description="Distilled air-essence, calming", price_drip=2),
            VendorItem(name="Dripfruit Chews", description="Mood-softening candy", price_drip=1, item_type="food"),
            VendorItem(name="Med Kit (Basic)", description="Emergency medical supplies", price_drip=5),
            VendorItem(name="Ration Pack", description="Standard survival rations", price_drip=2, item_type="food"),
            VendorItem(name="Glowsticks (x3)", description="Emergency lighting", price_breath=8),
            VendorItem(name="Comm Unit (Disposable)", description="One-use communicator", price_drip=3),
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
            VendorItem(name="Ritual Altar Access (1hr)", description="Temple altar booking", price_spark=1),
            VendorItem(name="Incense Stick (Single)", description="Basic ritual cleansing", price_breath=10, item_type="offering"),
            VendorItem(name="Ley-Chalk (3pk)", description="Temporary glyph drawing", price_drip=2),
            VendorItem(name="Whisper Wax Tablet", description="Breath-activated recording", price_breath=15),
            VendorItem(name="Talisman Blank", description="Single ritual substrate", price_drip=3),
            VendorItem(name="Blessing Sponge", description="Altar preparation cloth", price_breath=6),
            VendorItem(name="Mini-Bond Bowl", description="Portable ritual altar", price_drip=10, seed_barter=True),
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
            VendorItem(name="Echo-Crackers", description="Joy-infused crunchy snack", price_breath=4, item_type="food"),
            VendorItem(name="Glowpeel Noodles (Instant)", description="Spark-dust spiced noodles", price_drip=2, item_type="food"),
            VendorItem(name="Hollow Cone (Dessert)", description="Void-cream ice cream cone", price_drip=3, item_type="food"),
            VendorItem(name="Ley Pop (Sourwave)", description="Fizzes near emotions", price_breath=5, item_type="food"),
            VendorItem(name="Sparksticks", description="Addictive buzz twigs", price_breath=3, item_type="food"),
            VendorItem(name="Reviv-Essence Lozenges", description="Stimulant tabs", price_drip=4, item_type="food"),
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
            VendorItem(name="Echo-Calibrator", description="Portable seed stabilizer (DC 16 Dex+Tech, 1 Drip per 3 uses)", price_spark=8, item_type="tool"),
            VendorItem(name="Neural Stimulant", description="Cognitive boost (4hr)", price_drip=4),
            VendorItem(name="Genetic Sample Kit", description="DNA collection tools", price_drip=6),
            VendorItem(name="Resonance Tuner (Portable)", description="Adjust personal frequencies", price_spark=3),
            VendorItem(name="Bio-Sensor Patch", description="Monitors vital signs", price_drip=5),
            VendorItem(name="Void-Cut Tea (Synthetic)", description="Forbidden ritual simulacrum", price_drip=2),
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
            VendorItem(name="Union Heavy Pistol", description="Standard issue sidearm", price_spark=6),
            VendorItem(name="Riot Carapace (Armor)", description="Blast-resistant body armor", price_spark=10),
            VendorItem(name="Dripshock Baton", description="Non-lethal crowd control", price_spark=3),
            VendorItem(name="Med Kit (Tactical)", description="Combat-grade medical", price_drip=6),
            VendorItem(name="Restraint Cuffs", description="Detain suspects", price_drip=8),
            VendorItem(name="Void Scanner (Basic)", description="Detect corruption", price_spark=4),
            VendorItem(name="Signal Flare", description="Call for backup", price_drip=4),
        ],
        greeting="[P-19 FIELD UNIT] Authorized personnel: state requisition code."
    )
    vendors.append(security_drone)

    delivery_drone = Vendor(
        name="House of Vox Courier Drone",
        faction="House of Vox",
        vendor_type=VendorType.SUPPLY_DRONE,
        inventory=[
            VendorItem(name="Data Slate (Encrypted)", description="Secure information storage", price_drip=10),
            VendorItem(name="Whisper Capsules", description="Ambient dream audio", price_drip=5),
            VendorItem(name="Broadcast Access Chip (Temp)", description="1-hour media access", price_spark=2),
            VendorItem(name="Echo-Quill", description="Writes intent, not words", price_drip=7),
            VendorItem(name="Glow-Beads (x10)", description="React to emotional agitation", price_breath=12),
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
            VendorItem(name="Med Kit", description="Emergency medical supplies", price_drip=0),
            VendorItem(name="Ration Pack (x3)", description="Survival rations", price_drip=0, item_type="food"),
            VendorItem(name="Signal Flare", description="Call for help", price_drip=0),
            VendorItem(name="Purification Incense", description="Ritual cleansing", price_drip=0, item_type="offering"),
        ],
        greeting="[EMERGENCY CACHE] Crisis protocol active. Take what you need."
    )
    vendors.append(emergency_cache)

    return vendors


# =============================================================================
# LOOT SYSTEM
# =============================================================================

@dataclass
class LootResult:
    """
    Structured loot from defeated enemy or container.

    Created by acquire_loot() to formalize the existing suggest_loot() output
    into actual inventory additions. Contains both structured data and a
    human-readable description.
    """
    weapons: List  # List of Weapon objects (with condition info)
    currency: Dict[str, int]  # {"breath": 15, "drip": 5, ...}
    seeds: List[Seed]  # Seed objects found
    special_items: List[str]  # Narrative items (datapads, keycards)
    source_name: str  # Who/what was looted
    description: str  # Human-readable summary


def acquire_loot(character_state, enemy_agent) -> LootResult:
    """
    Generate structured loot from defeated enemy and add to player inventory.

    This formalizes the existing suggest_loot() pattern by:
    1. Generating structured loot (weapons, currency, seeds, special items)
    2. Adding currency to the player's EnergyPurse
    3. Adding special items to the player's inventory dict
    4. Returning a LootResult for logging/narration

    Args:
        character_state: Player's CharacterState (has energy_purse, inventory)
        enemy_agent: Defeated EnemyAgent to loot

    Returns:
        LootResult with all loot details
    """
    import random as _random

    loot_weapons = []
    loot_currency = {}
    loot_seeds = []
    loot_special = []
    loot_parts = []

    # --- Weapons ---
    for weapon in getattr(enemy_agent, 'weapons', []):
        health = getattr(enemy_agent, 'health', 0)
        wounds = getattr(enemy_agent, 'wounds', 0)
        if health > 0:
            condition = "good"
        elif wounds <= 2:
            condition = "fair"
        else:
            condition = "damaged"
        loot_weapons.append(weapon)
        loot_parts.append(f"{weapon.name} ({condition})")

    # --- Currency (template-based, faction-modified) ---
    template_currency = {
        "grunt":       (10, 30,  3,  8,  0, 2,  0, 0),
        "elite":       ( 0,  5,  5, 15,  2, 6,  0, 2),
        "sniper":      ( 0,  5,  8, 20,  1, 4,  0, 1),
        "boss":        ( 0,  0,  3, 10,  3, 8,  2, 5),
        "void_cultist":(15, 40,  2, 10,  0, 3,  0, 1),
        "enforcer":    ( 0,  5,  5, 15,  2, 5,  0, 2),
        "support":     ( 5, 20,  8, 20,  1, 4,  0, 1),
        "ambusher":    (10, 25,  5, 12,  0, 3,  0, 1),
    }

    template = getattr(enemy_agent, 'template', 'grunt')
    base = template_currency.get(template, (5, 15, 2, 8, 0, 2, 0, 0))
    breath_min, breath_max, drip_min, drip_max, grain_min, grain_max, spark_min, spark_max = base

    faction_lower = getattr(enemy_agent, 'faction', '').lower()

    breath = _random.randint(breath_min, breath_max) if breath_max > 0 else 0
    drip = _random.randint(drip_min, drip_max) if drip_max > 0 else 0
    grain = _random.randint(grain_min, grain_max) if grain_max > 0 else 0
    spark = _random.randint(spark_min, spark_max) if spark_max > 0 else 0

    # Faction theme adjustments
    if "tempest" in faction_lower:
        spark += _random.randint(0, 2)
    elif "acg" in faction_lower or "commerce" in faction_lower or "sovereign nexus" in faction_lower:
        spark += _random.randint(0, 1)
        grain += _random.randint(0, 2)
    elif "pantheon" in faction_lower or "security" in faction_lower:
        grain += _random.randint(0, 2)
        breath += _random.randint(0, 5)
    elif "freeborn" in faction_lower or "street" in faction_lower or "gang" in faction_lower:
        breath += _random.randint(5, 15)
        drip += _random.randint(0, 5)
    elif "resonance" in faction_lower or "commune" in faction_lower:
        breath += _random.randint(5, 10)
        drip += _random.randint(0, 3)
    elif "void" in faction_lower or "cult" in faction_lower:
        drip += _random.randint(0, 5)
        breath += _random.randint(10, 20)

    loot_currency = {
        "breath": breath,
        "drip": drip,
        "grain": grain,
        "spark": spark,
    }

    # Add currency to player purse
    purse = getattr(character_state, 'energy_purse', None)
    if purse:
        for currency_type, amount in loot_currency.items():
            if amount > 0:
                purse.add_currency(currency_type, amount)

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
        loot_parts.append(", ".join(currency_parts))

    # --- Seeds ---
    void_score = getattr(enemy_agent, 'void_score', 0)
    seed_dropped = False

    if void_score >= 3:
        hollow_chance = 0.25 if "tempest" in faction_lower else 0.20
        if _random.random() < hollow_chance:
            hollow_seed = Seed(SeedType.HOLLOW, origin=f"loot_{getattr(enemy_agent, 'name', 'enemy')}")
            loot_seeds.append(hollow_seed)
            if purse:
                purse.add_seed(hollow_seed)
            loot_parts.append("1 Hollow Seed (illicit void energy)")
            seed_dropped = True

    if not seed_dropped and ("resonance" in faction_lower or "nexus" in faction_lower or "commune" in faction_lower):
        if _random.random() < 0.15:
            if _random.random() < 0.5:
                elem = _random.choice([Element.FIRE, Element.WATER, Element.AIR, Element.EARTH])
                attuned_seed = Seed(SeedType.ATTUNED, element=elem, origin=f"loot_{getattr(enemy_agent, 'name', 'enemy')}")
                loot_seeds.append(attuned_seed)
                if purse:
                    purse.add_seed(attuned_seed)
                loot_parts.append(f"1 Attuned Seed ({elem.value.title()})")
            else:
                raw_seed = create_raw_seed(origin=f"loot_{getattr(enemy_agent, 'name', 'enemy')}", freshness="random")
                loot_seeds.append(raw_seed)
                if purse:
                    purse.add_seed(raw_seed)
                loot_parts.append("1 Raw Seed (unstable)")
            seed_dropped = True

    if not seed_dropped and template == "boss":
        if _random.random() < 0.30:
            if void_score >= 2:
                hollow_seed = Seed(SeedType.HOLLOW, origin=f"loot_{getattr(enemy_agent, 'name', 'enemy')}")
                loot_seeds.append(hollow_seed)
                if purse:
                    purse.add_seed(hollow_seed)
                loot_parts.append("1 Hollow Seed (illicit void energy)")
            else:
                elem = _random.choice([Element.FIRE, Element.WATER, Element.AIR, Element.EARTH, Element.SPIRIT])
                attuned_seed = Seed(SeedType.ATTUNED, element=elem, origin=f"loot_{getattr(enemy_agent, 'name', 'enemy')}")
                loot_seeds.append(attuned_seed)
                if purse:
                    purse.add_seed(attuned_seed)
                loot_parts.append(f"1 Attuned Seed ({elem.value.title()})")

    # --- Special Items ---
    if _random.random() < 0.1:
        special_options = [
            "encrypted datapad",
            "faction insignia",
            "coded message",
            "security keycard",
        ]
        if void_score > 3:
            special_options.append("ritual talisman")
        special_item = _random.choice(special_options)
        loot_special.append(special_item)
        loot_parts.append(special_item)

        # Add special items to player inventory
        inventory = getattr(character_state, 'inventory', None)
        if inventory is not None:
            key = item_name_to_inventory_key(special_item)
            inventory[key] = inventory.get(key, 0) + 1

    loot_str = ", ".join(loot_parts)
    description = f"**Loot from {getattr(enemy_agent, 'name', 'enemy')}:** {loot_str}" if loot_parts else f"Defeated {getattr(enemy_agent, 'name', 'enemy')}: No loot"

    result = LootResult(
        weapons=loot_weapons,
        currency=loot_currency,
        seeds=loot_seeds,
        special_items=loot_special,
        source_name=getattr(enemy_agent, 'name', 'enemy'),
        description=description,
    )

    logger.info(f"Loot acquired from {result.source_name}: {loot_str}")
    return result


# Export key classes
__all__ = [
    'SeedType',
    'Element',
    'VendorType',
    'Seed',
    'EnergyPurse',
    'VendorItem',
    'Vendor',
    'LootResult',
    'acquire_loot',
    'create_test_vendor',
    'create_standard_vendors',
    'item_name_to_inventory_key',
]
