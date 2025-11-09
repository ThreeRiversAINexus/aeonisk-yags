# Purchase & Vending System Design

**Status:** Design Phase
**Created:** 2025-01-09
**Purpose:** Complete architectural design for energy-based economy and purchase mechanics

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Energy Economy Fundamentals](#energy-economy-fundamentals)
3. [Purchase Intent System](#purchase-intent-system)
4. [Vendor Type Matrix](#vendor-type-matrix)
5. [Pre-Validation Architecture](#pre-validation-architecture)
6. [Soulcredit Integration](#soulcredit-integration)
7. [Physical Transaction Mechanics](#physical-transaction-mechanics)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Test Coverage Requirements](#test-coverage-requirements)
10. [ML Training Implications](#ml-training-implications)
11. [Current Bugs & Fixes](#current-bugs--fixes)

---

## Design Philosophy

### Core Principles

**1. Transactions Are Spiritual Acts, Not Mechanical Exchanges**

From *Aeonisk - System Neutral Lore v1.2.3* (lines 269-270):
> "Money is memory made manifest. Talismans are not mere tokens — they are containers of meaning, harvested from emotion, aligned with planetary flows, and exchanged with spiritual consequence."

**Implications:**
- Energy transfers carry spiritual weight recorded by the Codex
- Simple purchases should be **deterministic** (you have energy, you get item)
- Skill rolls apply to **negotiation/barter**, not basic transactions
- Failed purchases create drama through **scarcity**, not randomness

**2. Scarcity Creates Drama Through Resource Allocation**

From *Economy & Money-Making Guide v1.2.3*:
> "Economic scarcity is a feature, not a bug. Economy creates meaningful choices: fast/risky, slow/safe, cooperative, clever."

**The Interesting Failure State:**
- ✅ "You don't have enough Drip" → Forces creativity, cooperation, alternative solutions
- ❌ "You rolled badly on your purchase check" → Meaningless randomness

**3. Energy as Multi-Use Physical Resource (Not Abstract Currency)**

**Design Vision:**
> "You can basically load your gun with Sparks, then unload it and trade it for offerings, and use the offerings in rituals so you don't get Void."
>
> "It's kinda like, what if you could power your car on Bitcoin, or what if I could turn money directly into food and drink (Grains and Drips)."

**Why This Matters:**
Most games treat money as abstract numbers ("100 gold coins"). The player knows gold is valuable because the game says so, but there's no intrinsic use beyond buying things. This creates **fake scarcity** — numbers on a screen.

Aeonisk's economy is based on **real, consumable resources with multiple use cases**:

1. **Consumable (Direct Use)** — Sparksticks contain Sparks, Dripmist contains Drips, beverages/food contain energy
2. **Ritual Power** — Fuel spells, wards, attunements
3. **Gear Operation** — Power resonant weapons/armor (Spark Lash requires 1 Spark per 20 shots)
4. **Trade Medium** — Transfer energy to vendors in exchange for goods
5. **Social Capital** — Demonstrate wealth/capability through visible talisman displays

This creates **true scarcity**: Every unit of Spark spent buying an item is a unit NOT available for:
- Powering your Spark-Bound Pulse Rifle in the next combat
- Drinking as a Sparkstick (stimulant)
- Fueling a ritual to avoid Void corruption
- Converting to other energy types

**Resource-Backed Currency Model:**

Like the gold standard, but actually useful:
- Gold standard: "This paper is worth gold (which you can't use for anything except trade)"
- Aeonisk standard: "This Drip talisman is worth 1 Drip energy (which you can drink, trade, or use in rituals)"

**Economic Tension Example:**

Player has 5 Spark:
- Option A: Buy Med Kit (costs 3 Spark) → Can't power Pulse Rifle in combat
- Option B: Power Pulse Rifle (costs 3 Spark) → Can't afford Med Kit
- Option C: Drink Sparksticks for buff (costs 2 Spark) → Have 3 left, must choose Med Kit OR rifle
- Option D: Convert 5 Spark → 25 Grain → 250 Drip, buy cheaper items → Lose access to Spark-powered gear

These are **real trade-offs** with mechanical consequences, not "do I have enough arbitrary points?"

**4. Vendor Types Have Distinct Personalities**

Different vendor types should behave fundamentally differently:
- **Vending Machines** — Deterministic, no negotiation, Soulcredit-gated
- **Human Traders** — Negotiable, relationship-driven, personality-based
- **Black Market Dealers** — Soulcredit-irrelevant, accept illicit payment (Hollows)
- **Tempest Supply Drones** — Anti-Nexus, inverted Soulcredit preferences

---

## Energy Economy Fundamentals

### The Energy Production Chain

```
Raw Seeds (harvested from leylines)
    ↓ (ritual attunement by Aether Dynamics or skilled individuals)
Attuned Seeds (elemental: Breath/Drip/Grain/Spark)
    ↓ (energy extracted and stored in talismans)
Energy Talismans (physical containers with capacity limits)
    ↓ (can be used for...)
    ├─ Powering rituals
    ├─ Fueling resonant gear
    ├─ Trading (energy transfer to vendor)
    └─ Demonstrating wealth/status
```

### Hollow Seeds (Void-Type Energy Currency)

**Definition:** Raw Seeds that have degraded over 7 cycles, converting to Void-aligned energy

**Automatic Conversion:** When a Raw Seed reaches 0 cycles remaining, it **automatically converts to Hollow Seeds** (not destroyed)

**Power Level:** **3x energy yield** compared to standard attuned energy
- 1 Hollow Seed → 3 units of Void-aligned energy
- 1 Attuned Seed → 1 unit of standard energy
- **The temptation is real** — high risk, high reward

**Properties:**
- **Void-type energetic currency** — not standard energy
- **Illicit under Sovereign Nexus** — possession is contraband (Codex flags)
- **Preferred by Tempest Industries** — comfortable with Void-type energy
- **Spiritual risk** — using Hollows increases Void score
- **Black Market premium** — worth more to illicit vendors than standard energy

**Strategic Speculation (Intentional Design):**

Players can **deliberately farm Hollows** by letting Raw Seeds degrade:

```python
# Risk-Tolerant Agent Strategy
def hollow_farming_strategy():
    # 1. Acquire Raw Seeds (5 units)
    acquire_raw_seeds(5)

    # 2. Wait 7 cycles (intentional neglect)
    wait_cycles(7)

    # 3. Raw Seeds auto-convert to Hollows (5 units)
    # Each Hollow = 3x energy of Attuned Seed
    # Total yield: 15 units Void-energy vs. 5 units standard energy

    # 4. Decision point:
    # Option A: Use Hollows for high-risk situations (3x power boost)
    # Option B: Sell Hollows to Black Market (premium prices)
    # Option C: Power Void-tech gear (some weapons REQUIRE Hollows)
```

**Sovereign Nexus Surveillance:**

**Canonically, having nearly-degraded Raw Seeds is SUSPICIOUS.**

The Codex Nexum tracks:
- Raw Seeds owned by each citizen
- Degradation timers (via talisman signatures)
- **Flags players with multiple Seeds at 1-2 cycles remaining**

**Codex Alert Logic:**
```python
def codex_surveillance_check(character):
    raw_seeds = character.energy_purse.raw_seeds
    nearly_degraded = [s for s in raw_seeds if s.cycles_remaining <= 2]

    if len(nearly_degraded) >= 3:
        # Suspicious pattern: intentional Hollow farming
        codex_flag(character, reason="SUSPECTED_HOLLOW_PRODUCTION")
        soulcredit_penalty(character, -1)

        # May trigger:
        # - Confessor investigation
        # - Vendor alerts (vending machines report transaction)
        # - Entry denial to Sanctums
```

**Why Nexus Wants Seeds Processed:**
- Hollows empower anti-Nexus factions (Tempest)
- Void-type energy destabilizes planetary balance
- Processing Raw → Attuned is "spiritually correct" per Codex theology
- Economic control: Nexus profits from altar service fees

**Tempest Industry Preference:**

Tempest is **comfortable with Hollows** because:
- Void-type energy aligns with their philosophy (anti-Codex)
- Powers their Void-tech (Ash Pulse Pike, Hollowed Repeater)
- Black Market economy runs on Hollows (off-Codex transactions)
- **BUT: Even Tempest doesn't want max Void (see Eye of Breach below)**

**Use Cases:**
- **Void-tech gear** — Some weapons REQUIRE Hollow energy (standard won't work)
- **Black Market transactions** — Preferred currency for illicit goods
- **High-risk power boost** — 3x energy yield for desperate situations
- **Anti-Nexus rituals** — Tempest rituals accept Hollows without penalties
- **Trading with Tempest vendors** — Better exchange rates for Hollows vs. standard energy

### Attunement Skill & Echo Calibrator System

**Core Mechanic:** Converting Raw Seeds into attuned energy requires either **Attunement skill** OR an **Echo Calibrator** (item).

#### The Skill/Tool Relationship

```
WITHOUT Echo Calibrator:
├─ Attunement skill 0: CANNOT attune (must use altars/vendors)
├─ Attunement skill 3: Can attune at altar (60% efficiency)
└─ Attunement skill 5+: Can hand-attune anywhere (70% efficiency, slow)

WITH Echo Calibrator (item):
├─ Attunement skill 0: CAN attune (40% efficiency, item does the work)
├─ Attunement skill 3: Can attune (70% efficiency, skill + item synergy)
└─ Attunement skill 6+: Can attune (90% efficiency, expert + tool)
```

**Key Design Principle:** Echo Calibrator is an **equalizer item** that:
- **Enables** unskilled players (democratizes access to attunement)
- **Amplifies** skilled players (synergy bonus when combined with expertise)
- **Creates progression** (upgrade from worn → professional models)

**NOT default starting gear** — must be purchased or earned, making it a meaningful early-game acquisition.

#### Echo Calibrator Item Variants

```python
class EchoCalibratorItem:
    """
    Portable attunement device. Enables field conversion of Raw Seeds.
    Quality determines base efficiency.
    """
    variants = {
        "standard": {
            "base_efficiency": 0.40,
            "price": {"drip": 20},
            "description": "Mass-produced Aether Dynamics model. Reliable.",
            "availability": "Common (most vendors)"
        },
        "professional": {
            "base_efficiency": 0.45,
            "price": {"drip": 50},
            "description": "Precision-etched resonance array. Favored by field agents.",
            "availability": "Uncommon (specialized vendors)"
        },
        "master_class": {
            "base_efficiency": 0.50,
            "price": {"grain": 2},
            "description": "Hand-crafted by Arcane Genetics bio-ritualists.",
            "special": "Auto-stabilizes degrading Seeds (prevents Hollow conversion)",
            "availability": "Rare (high-tier vendors, quest rewards)"
        }
    }
```

**Starting Gear (Thematic):**
- **Aether Dynamics employee:** Starts with Standard Calibrator (company tool)
- **Arcane Genetics agent:** Starts with Professional Calibrator (field kit)
- **Freeborn scavenger:** NO calibrator (must purchase or rely on altars)
- **Most characters:** NO calibrator by default (earn/buy it)

#### Attunement Efficiency Formula

```python
def calculate_attunement_efficiency(
    has_echo_calibrator: bool,
    calibrator_quality: float,  # 0.40-0.50 based on variant
    attunement_skill: int,
    at_ritual_altar: bool,
    altar_quality: int = 5
) -> float:
    """
    Calculate energy conversion efficiency.

    Priority: Ritual Altar > Echo Calibrator > Hand-attunement
    Skill always adds bonus regardless of tool.
    """

    # Base efficiency
    if at_ritual_altar:
        base = 0.40 + (altar_quality * 0.05)  # 40% + altar quality bonus
    elif has_echo_calibrator:
        base = calibrator_quality  # 40-50% based on item quality
    else:
        # Hand-attunement (masters only)
        if attunement_skill < 5:
            return 0.0  # Cannot attune without tools
        else:
            base = 0.30  # Very inefficient but possible for masters

    # Skill bonus (always applies)
    skill_bonus = attunement_skill * 0.05  # 5% per skill point

    # Tool synergy bonus (skill + Echo Calibrator)
    if has_echo_calibrator and attunement_skill >= 3:
        synergy_bonus = 0.10  # +10% when skilled user + tool
    else:
        synergy_bonus = 0.0

    return min(1.0, base + skill_bonus + synergy_bonus)
```

**Efficiency Examples:**

| Attunement Skill | Echo Calibrator? | At Altar (Q5)? | Efficiency | Notes |
|------------------|------------------|----------------|------------|-------|
| 0 | No | No | 0% | Cannot attune |
| 0 | No | Yes | 65% | Altar does all the work |
| 0 | Yes (Standard) | No | 40% | Calibrator enables, but wasteful |
| 3 | Yes (Standard) | No | 65% | Skill + tool synergy (40% + 15% + 10%) |
| 6 | Yes (Standard) | No | 80% | Skilled + tool (40% + 30% + 10%) |
| 6 | Yes (Professional) | No | 85% | Better tool (45% + 30% + 10%) |
| 9 | Yes (Master Class) | No | 100% | Perfect field attunement |
| 3 | No | Yes (Q8) | 95% | High-quality altar compensates |
| 9 | Yes (Master) | Yes (Q10) | 100% | All bonuses (capped at 100%) |

#### Economic Class Progression

**Poor/Unskilled Players:**
- No Attunement skill, no Echo Calibrator
- **Must rely on altars or vendors** for attunement
- Pay service fees (~2 Drip per Seed)
- Accept lower efficiency (65% at typical altar)
- **Goal:** Save 20 Drip to buy Standard Calibrator

**Middle-Class Players:**
- Own Standard Echo Calibrator (20 Drip investment)
- Attunement skill 0-2
- Can attune in the field (40-50% efficiency)
- **Independence** from altars, but wasteful
- **Goal:** Increase Attunement skill OR upgrade to Professional Calibrator

**Wealthy/Skilled Players:**
- Own Professional/Master Calibrator + Attunement 6+
- Can attune anywhere (85-100% efficiency)
- **Full economic autonomy** — no infrastructure needed
- Masters of the resource economy

**This creates natural progression without hard-gating content.**

#### Ritual Altars as Service Infrastructure

Altars are **stationary service providers** (not item vendors):

```python
class RitualAltar:
    """
    Stationary infrastructure for energy attunement.
    Higher quality = better base efficiency.
    """
    def __init__(self, location: str, quality: int, faction: str):
        self.location = location  # "Sanctum 14", "Black Market Den"
        self.quality = quality  # 1-10 (affects efficiency)
        self.faction = faction  # Nexus, Freeborn, Tempest
        self.services = [
            "attune_raw_seed",           # Raw → Attuned energy
            "extract_from_consumable",   # Break down items for energy
            "stabilize_degrading_seed",  # Prevent Hollow conversion
            "convert_energy_type"        # Drip → Grain, etc.
        ]
        self.service_cost = {"breath": 2}  # Fee per use
```

**Altar Locations:**

**Nexus Altars (High Quality, Soulcredit-Gated):**
- Location: Sanctums on Aeonisk Prime
- Quality: 8-10 (90-100% base efficiency)
- Access: Soulcredit ≥ 0 required
- Service Cost: 1 Breath per attunement (cheap but SC-gated)
- Benefit: Near-perfect conversion, Codex-logged (legal)

**Freeborn Altars (Medium Quality, Open Access):**
- Location: Neutral Zone markets, Arcadia settlements
- Quality: 5-7 (65-85% base efficiency)
- Access: Anyone
- Service Cost: 2 Drip per attunement
- Benefit: No Codex logging, accepts Hollows

**Black Market Altars (Low Quality, Illicit):**
- Location: Hidden in Tempest territory, Hollow Vector stations
- Quality: 3-5 (55-65% base efficiency)
- Access: Anyone (but risky — Confessor raids)
- Service Cost: 1 Hollow per attunement OR 3 Drip
- Benefit: Converts Hollows without Void penalty, untracked

**Abandoned Altars (Variable, Found in Exploration):**
- Location: Discovered during missions
- Quality: 1-9 (random, may be damaged)
- Access: Free (but may be unstable, contested, cursed)
- Service Cost: None (but risk of malfunction, +1 Void on failure)
- Benefit: Free attunement if you can secure the location

#### Altar vs. Calibrator Trade-offs

**When to use Echo Calibrator (field attunement):**
- ✅ Need immediate conversion (no time to travel)
- ✅ In dangerous area (can't safely reach altar)
- ✅ Have high Attunement skill (efficiency good enough)
- ✅ Seeds about to degrade (1 cycle left, urgent)
- ✅ Want to avoid Codex tracking (off-grid attunement)

**When to use Ritual Altar:**
- ✅ Have low Attunement skill (altar compensates for lack of expertise)
- ✅ Processing many Seeds (service fee amortizes over volume)
- ✅ Need perfect conversion (waste is expensive)
- ✅ Don't own Echo Calibrator yet (only option besides vendors)

#### Raw Seeds as Tradeable Currency

**Why Raw Seeds Must Be Tradeable:**

1. **Physical harvested objects** from leylines (not abstract)
2. **Aether Dynamics trades them in bulk** (core business model)
3. **7-cycle degradation timer** gives window for safe transport/trade
4. **Risk is priced in** — Raw Seeds sell cheaper than attuned energy

**Pricing Model:**

```
Raw Seed (fresh, 7 cycles until degradation): ~4 Drip
├─ Age 1-2 cycles: 4 Drip (fresh premium)
├─ Age 3-4 cycles: 3 Drip (standard)
├─ Age 5-6 cycles: 2 Drip (risky, nearly Hollow)
└─ Age 7+ cycles: 1 Drip (Hollow Seed, illicit)

Attuned Energy (processed by vendor/player): ~8-10 Drip
└─ Premium for certainty (no degradation risk, known type)

Hollow Seed (degraded Raw Seed): ~2 Drip
└─ Illicit, Nexus contraband, valuable to Tempest/black market
```

**Vendor Behavior:**

```python
def get_raw_seed_price(seed: RawSeed, vendor_type: VendorType) -> dict:
    """Price based on degradation timer and vendor faction."""
    base_price = 4  # Fresh Drip
    age_discount = (7 - seed.degradation_timer) * 0.5  # Older = cheaper

    # Vendor markup/markdown
    if vendor_type == VendorType.VENDING_MACHINE:
        markup = 1.3  # Nexus markup
    elif vendor_type == VendorType.BLACK_MARKET_DEALER:
        markup = 0.9  # Black market discount (volume sales)
    else:
        markup = 1.0

    return {"drip": max(1, (base_price - age_discount) * markup)}
```

**Player Decision Example:**

Player finds 3 Raw Seeds (age 2, 5 cycles left):

**Option A: Attune with Standard Calibrator (40% efficiency, Attunement 0)**
- Result: 3 Seeds × 10 Drip potential × 40% = 12 Drip
- Waste: 18 Drip lost to inefficiency
- Time: Immediate

**Option B: Travel to Freeborn Altar (65% efficiency, 2 Drip fee per Seed)**
- Result: 3 Seeds × 10 Drip × 65% = 19.5 Drip, -6 Drip fee = 13.5 Drip net
- Time: 2 days travel
- Risk: Seeds age by 2 cycles during travel (now age 4, 3 cycles left)

**Option C: Sell Raw Seeds to vendor (no attunement)**
- Result: 3 Seeds × 3 Drip (age 2 pricing) = 9 Drip immediate
- No waste, no risk, instant liquidity
- Lower total value but certain

**Strategic Consideration:** If player has low skill and no calibrator, **selling Raw may be optimal** (9 Drip certain vs. 12-13 Drip with waste/risk/time).

#### Temporal Urgency: Degradation Timers

```json
{
  "seed_inventory": [
    {"id": "seed_1", "age": 2, "cycles_remaining": 5, "status": "stable"},
    {"id": "seed_2", "age": 6, "cycles_remaining": 1, "status": "URGENT"},
    {"id": "seed_3", "age": 1, "cycles_remaining": 6, "status": "stable"}
  ],
  "agent_planning": {
    "priority_1": "Attune seed_2 IMMEDIATELY (1 cycle = ~8 hours left)",
    "priority_2": "Travel to altar with seed_1 and seed_3 (can wait)",
    "reasoning": "Losing seed_2 to Hollow conversion wastes 10 Drip potential"
  }
}
```

**ML Training Insight:** Agents learn **time-sensitive resource management** (urgency affects action sequencing).

### Consumable Energy Items

**Core Concept:** Energy talismans can be **consumed directly** as food, beverages, or stimulants.

From *Gear & Tech Reference* (lines 149-183):

**Spark-Infused Consumables:**
- **Sparksticks** — "Saliva-reactive buzz twigs. Technically addictive. Teen favorite."
  - Contains: 1 Spark per stick
  - Effect: Stimulant buff (+1 to Perception for 1 hour)
  - Trade-off: Consume Spark OR save for gear/trade

**Drip-Infused Consumables:**
- **Dripmist** — Mood-softening beverage
  - Contains: 2 Drip per flask
  - Effect: Calming, reduces stress/Void anxiety
  - Trade-off: Drink for buff OR use Drip for purchases

- **Dripfruit Chews** — "Sugary spheres with legal-dose mood softeners"
  - Contains: 1 Drip per package
  - Effect: Minor mood elevation

**Breath-Infused Consumables:**
- **Breathwater Flask** — "Distilled air-essence with mnemonic mist"
  - Contains: 2 Breath
  - Effect: Ritual-safe hydration, calming

**Grain-Infused Consumables:**
- **Glowpeel Noodles** — "Luminescent street food. Spark-dust spiced."
  - Contains: 5 Grain worth of energy
  - Effect: Substantial meal, restores stamina

**Mechanical Implementation:**

```python
class ConsumableItem:
    """Item that can be consumed for effects AND contains extractable energy."""
    def __init__(self, name: str, energy_content: dict, consumption_effect: dict):
        self.name = name
        self.energy_content = energy_content  # e.g., {"spark": 1}
        self.consumption_effect = consumption_effect  # e.g., {"perception": +1, "duration": 1_hour}

    def consume(self, character: CharacterState):
        """Consume item for effects. Energy is lost."""
        apply_buff(character, self.consumption_effect)
        # Energy is consumed, NOT added to purse

    def extract_energy(self, character: CharacterState):
        """Extract energy to purse. Effects are lost."""
        for energy_type, amount in self.energy_content.items():
            stored, overflow = character.energy_purse.receive_energy(energy_type, amount)
            if overflow > 0:
                logger.warning(f"Purse full, {overflow} {energy_type} wasted")
        # Item is destroyed, no consumption effects gained
```

**Player Decision Example:**

Player has 1 Sparkstick in inventory, 0 Spark in purse:

**Option A: Consume for buff**
- Action: "I chew the Sparkstick"
- Result: +1 Perception for 1 hour, 0 Spark gained
- Trade-off: Can't power Spark Lash in next fight

**Option B: Extract to purse**
- Action: "I extract the Spark from the Sparkstick into my talisman"
- Result: 1 Spark in purse, no perception buff
- Trade-off: Can power weapon OR trade, but no buff

**Option C: Trade whole item**
- Action: "I trade this Sparkstick to the vendor"
- Result: Vendor accepts it as payment (worth ~1 Spark value)
- Trade-off: No buff, no Spark in purse, but item acquired

**Design Implication:** Every consumable creates a **three-way choice** (eat/extract/trade), making inventory management strategically meaningful.

### Energy Types & Physical Properties

From *System Neutral Lore* (lines 269-270):
> "Handling Spark feels like contained static, waiting to leap. Drip carries the cool weight of unshed tears. Breath is a held note, vibrating."

**Breath** (smallest denomination)
- Tactile: Vibrating, humming sensation
- Use: Minor rituals, everyday transactions
- Color: Pale blue-white glow

**Drip** (10 Breath)
- Tactile: Cool, tear-drop weight
- Use: Standard trade, emotional rituals
- Color: Blue pulse

**Grain** (10 Drip)
- Tactile: Granular, textured energy
- Use: Larger purchases, sustained rituals
- Color: Amber/gold

**Spark** (largest, most valuable)
- Tactile: Static electricity, dangerous to hold
- Use: Weapon fuel, high-power rituals, prestige trades
- Color: Crackling white-blue arcs

### Energy Purse (Talisman Storage)

**Physical Container System:**

```python
class EnergyPurse:
    """
    Physical talismans storing attuned energy.
    Capacity determined by gear quality (basic purse, multi-bind sheath, etc.)
    """
    def __init__(self, capacity_per_type: dict[str, int]):
        self.capacity = capacity_per_type  # e.g., {"drip": 50, "breath": 100, "grain": 20, "spark": 5}
        self.drip = 0
        self.breath = 0
        self.grain = 0
        self.spark = 0
        self.attuned_seeds = []  # Seeds player is carrying (not yet converted to energy)

    def can_store(self, energy_type: str, amount: int) -> bool:
        """Check if talismans have capacity for this energy."""
        current = getattr(self, energy_type)
        return (current + amount) <= self.capacity[energy_type]

    def transfer_to(self, recipient_purse, energy_type: str, amount: int) -> bool:
        """Physically transfer energy (like pouring liquid between containers)."""
        if self.has_sufficient(energy_type, amount):
            setattr(self, energy_type, getattr(self, energy_type) - amount)
            setattr(recipient_purse, energy_type, getattr(recipient_purse, energy_type) + amount)
            return True
        return False
```

**Talisman Capacity Upgrades:**

From *Gear & Tech Reference* (line 98):
> "Multi-Bind Sheath — Quick-swap 4 Talismans — 1 Spark/day to bond"

Talismans are **purchasable gear** with varying capacities:
- Basic Purse: Drip ×30, Breath ×50, Grain ×10, Spark ×3
- Multi-Bind Sheath: Drip ×50, Breath ×100, Grain ×20, Spark ×5
- Merchant's Array: Drip ×100, Breath ×200, Grain ×50, Spark ×10

**Design Implication:** Players can run out of storage space, forcing choices about which energy types to carry.

---

## Purchase Intent System

### Intent Types

The system distinguishes between **four distinct purchase intents**, each with different mechanics:

#### 1. Simple Purchase (Deterministic)

**Player Declaration:**
- "I buy [item] from [vendor]"
- "I purchase [item]"
- "I'll take [item]"

**System Behavior:**
- **Pre-validation occurs** BEFORE DM is called
- System checks: `player.energy_purse.{energy_type} >= item.price`
- System injects **constraint** into DM prompt
- DM **MUST** narrate based on constraint (success or failure)

**DM Constraint (Success):**
```yaml
purchase_validation:
  status: SUCCESS
  constraint: "MUST narrate successful energy transfer"
  details:
    player_energy: {drip: 15}
    item_cost: {drip: 8}
    surplus: 7
```

**DM Constraint (Failure):**
```yaml
purchase_validation:
  status: FAILED
  constraint: "MUST narrate insufficient energy. MAY suggest alternatives."
  details:
    player_energy: {drip: 3}
    item_cost: {drip: 8}
    shortage: 5
  allowed_alternatives:
    - "Suggest negotiation IF vendor type=HUMAN_TRADER"
    - "Suggest credit IF soulcredit >= 0"
    - "Suggest barter IF player has valuable items"
```

**Example Narration (Success):**
> "You unseal your Drip talisman — a tear-drop shaped crystal pulsing with cool blue light. You press it against the vending node's receptor. The crystal dims slightly as 8 units of Drip-attuned energy siphon into the machine's collection array. The node chimes, and the Blood Offering dispenses into the retrieval slot."

**Example Narration (Failure):**
> "The vending node scans your Drip talisman. Display: INSUFFICIENT ENERGY. Need 8 Drip, detected 3. Transaction aborted. The node's secondary menu flickers: CREDIT AVAILABLE (Soulcredit ≥ 2) or BARTER MODE ENABLED."

#### 2. Negotiation Attempt (Skill-Based)

**Player Declaration:**
- "I try to negotiate for [item]"
- "I attempt to haggle with [vendor]"
- "Can I get a discount on [item]?"

**System Behavior:**
- **NO pre-validation** (currency remains hidden from DM)
- DM generates **open-ended negotiation dialogue**
- Player makes specific offer
- **THEN** validation occurs on the offer
- Skill check (Charm/Guile) determines success

**DM Prompt (Currency Hidden):**
```yaml
player_action: "I try to negotiate for the Blood Offering"
purchase_intent: NEGOTIATION_ATTEMPT

vendor_context:
  name: "Vex"
  type: BLACK_MARKET_DEALER
  base_price: {drip: 8}
  negotiation_openness: HIGH

player_visible_state:
  soulcredit: 2
  # Currency HIDDEN during negotiation
  known_possessions: ["Raw Seed (unstable)", "Intel on Nexus patrols (Zone 14)"]
```

**Example Flow:**

1. **Player:** "I try to negotiate for the Blood Offering"
2. **DM (unaware of exact currency):** "Vex eyes you carefully. 'Blood Offering goes for 8 Drip, standard rate. But you got the look of someone who might have... other considerations. What are you offering?'"
3. **Player:** "I offer 5 Drip and information about Nexus patrol routes"
4. **System:** NOW validates (player has 5 Drip ✓)
5. **DM rolls:** Charm + Charisma vs DC 15
   - **Success:** "Vex narrows his eyes, then grins. 'Deal. But you owe me one.' He slides the offering across the counter."
   - **Failure:** "Vex laughs. 'Information is cheap in this district. 8 Drip or walk.'"

**Key Insight:** Rolls are for **social maneuvering**, not basic ability to transact.

#### 3. Barter Attempt (Item Evaluation)

**Player Declaration:**
- "I'll trade [item] for [vendor item]"
- "I offer [item] in exchange for [vendor item]"

**System Behavior:**
- DM sees **offered item**, not full energy purse
- DM evaluates: Is this item worth the vendor's asking price?
- May require skill check if value ambiguous
- No energy transfer (direct item swap)

**Example:**
> **Player:** "I'll trade this Raw Seed for the Med Kit"
>
> **DM:** "Vex examines the pulsing, unstable Seed. It thrums with chaotic potential. 'Raw and unattended? Risky. But Seeds are Seeds... I'll take it, but you're taking on the Void risk if it degrades in my stock. Deal?'"
>
> **System:** Direct item swap, no currency validation needed

#### 4. Credit Request (Soulcredit-Gated)

**Player Declaration:**
- "Can I buy this on credit?"
- "Do you offer payment plans?"
- "I'll pay you back later"

**System Behavior:**
- DM sees **Soulcredit standing** (currency still hidden)
- Vendor type + Soulcredit determine eligibility
- If approved: Creates debt obligation tracked by Codex

**Eligibility Matrix:**
```
VENDING_MACHINE: Never offers credit
HUMAN_TRADER:
  - SC ≥ 3: "Yes, your standing is excellent"
  - SC 0-2: "I'll need collateral"
  - SC < 0: "No credit available"
BLACK_MARKET_DEALER: Offers credit at HIGH interest regardless of SC
TEMPEST_DRONE: "We don't do debts. Cash or barter."
```

---

## Vendor Type Matrix

### Behavioral Profiles

#### Vending Machine (Automated Nexus Infrastructure)

**Examples:**
- Corner Store Node 92B (Lore vignette, lines 455-462)
- Supply dispensers in sanctums
- Emergency med-stations

**Characteristics:**
- **Deterministic:** Insert energy → receive item (no variance)
- **No negotiation:** Cannot haggle with a machine
- **Soulcredit-gated:** Requires SC ≥ -2 to access Nexus services
- **May accept creative offerings:** See Kaelen's fractal talisman (Lore lines 518-528)

**Transaction Flow:**
```
1. Player inserts talisman into receptor
2. Machine scans: Energy type + amount
3. Validation:
   - Soulcredit check (≥ -2?)
   - Energy check (sufficient amount?)
4. If pass: Dispense item, log to Codex
5. If fail: Display error, suggest alternatives
```

**Narration Style:**
- Clinical, automated voice
- Display screens with precise error messages
- Mechanical sounds (chimes, clicks, hums)

**Example Rejection:**
> "**VENDING NODE 92B**
> Soulcredit scan: -3
> ACCESS DENIED. Nexus services require standing ≥ -2.
> Restore standing at nearest Civic Kiosk or seek alternative vendors."

#### Human Trader (Personality-Driven Commerce)

**Examples:**
- Market stall operators
- Shop owners in safe zones
- Guild merchants

**Characteristics:**
- **Negotiable:** Open to haggling, discounts, package deals
- **Relationship-driven:** Remembers past interactions, builds trust
- **Soulcredit-sensitive:** Treats low-SC customers with suspicion
- **Credit available:** May offer payment plans to trusted customers

**Soulcredit Reaction Matrix:**
```
SC ≥ 5:  "Welcome, honored customer! Let me show you our premium stock."
SC 2-4:  "Fair standing. Standard prices apply."
SC 0-1:  "Cash only. No credit."
SC -1 to -3: "I don't know you well enough. Pay upfront."
SC < -3: "I don't serve your kind. Leave before I call security."
```

**Negotiation Openness:**
- Base DC for negotiation: 12-15
- Modifiers: Repeat customer (-2 DC), high Soulcredit (-1 DC), bulk purchase (-1 DC)
- Accepts barter if item has clear value

**Narration Style:**
- Conversational, expressive
- Visible emotional reactions (suspicion, delight, annoyance)
- May offer alternatives or suggest other vendors

**Example Negotiation:**
> "You spread your talismans on the counter — 5 Drip, visibly short of the 8 needed. The trader, a middle-aged woman with Halessan crest tattoos, frowns. 'That's not enough, friend. But... your ledger shows +3 Soulcredit. I could extend credit for the difference, 3 Drip due within 7 cycles. Interest-free if you settle early.'"

#### Black Market Dealer (Illicit Commerce)

**Examples:**
- Vex (from test sessions)
- Shadow market operators
- Freeborn traders in neutral zones

**Characteristics:**
- **Soulcredit-irrelevant:** Doesn't check or care about Nexus standing
- **Accepts Hollows:** Will take degraded Seeds, Void-tainted items
- **Barter-friendly:** Open to unconventional payment (intel, favors, artifacts)
- **No Codex logging:** Transactions don't appear in official records

**Payment Acceptance:**
- Standard energy (Drip, Spark, etc.)
- Hollow Seeds (often preferred)
- Information, intel, secrets
- Favors, future obligations
- Stolen goods, unregistered tech

**Narration Style:**
- Wary, assessing, street-smart
- Code words, subtle signals
- Paranoid about surveillance

**Example Transaction:**
> "Vex doesn't even glance at your Soulcredit beacon. He's watching your hands. You slide 3 Drip and a data-shard across the scarred table. He slots the shard, skims the Nexus patrol logs, nods slowly. 'Intel's worth 5 Drip if it's current. Deal.' No chime, no Codex ping. Just a hand-shake and the Blood Offering wrapped in black cloth."

#### Tempest Supply Drone (Anti-Establishment Automation)

**Examples:**
- Mobile supply units in contested zones
- Void-runner equipment caches
- Hollow Vector trade posts

**Characteristics:**
- **Inverted Soulcredit:** PREFERS low or negative SC
- **Anti-Nexus:** Hostile to high-SC individuals
- **Automated but factional:** Programmed loyalty to Tempest
- **Accepts Hollows:** Primary currency in some units

**Soulcredit Reaction (INVERTED):**
```
SC < -2:  "Recognized. Discounts applied for non-Nexus actors."
SC -1 to 1: "Neutral standing. Standard rates."
SC ≥ 2:   "Nexus sympathizer detected. Prices doubled."
SC ≥ 5:   "ACCESS DENIED. Nexus operatives not served."
```

**Narration Style:**
- Glitchy, modulated voice
- Ideological statements ("Dissolution is revelation")
- Suspicious of authority

**Example:**
> "The Tempest drone's optical array scans your Soulcredit: +4. Its voice crackles with static. 'Nexus compliance detected. You reek of their approval. Base price: 8 Drip. Your price: 16 Drip. Or take your tainted currency elsewhere, bootlicker.'"

#### Emergency Cache (Crisis-Triggered Resources)

**Examples:**
- Disaster relief stations
- Battlefield supply drops
- Abandoned stashes

**Characteristics:**
- **No transaction model:** Free access during crisis
- **One-time use:** Depletes after looting
- **May be contested:** Other survivors competing for resources
- **Temporary:** Disappears after crisis ends

**Access Mechanics:**
- No payment required
- May require contested roll (Agility to reach first, Strength to break open)
- May be trapped or unstable

**Narration Style:**
- Urgent, desperate
- Environmental hazards
- Time pressure

**Example:**
> "The Emergency Cache beacon pulses red through the smoke. You're not alone — two scavengers are already sprinting toward it. Roll Agility + Athletics vs DC 14 to reach it first. The cache contains: 3 Med Kits, 1 Spark Talisman, rations for 5 cycles."

---

## Pre-Validation Architecture

### Validation Layer Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Player declares action: "I buy Blood Offering from Vex"     │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Intent Detection: Classify as SIMPLE_PURCHASE               │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Pre-Validation: Check currency & Soulcredit                 │
│ - Player has 3 Drip, needs 8 Drip → INSUFFICIENT            │
│ - Shortage: 5 Drip                                           │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Generate Constraint for DM Prompt                            │
│ {                                                             │
│   "purchase_validation": {                                    │
│     "status": "FAILED",                                       │
│     "constraint": "MUST narrate insufficient energy",         │
│     "details": {                                              │
│       "player_energy": {"drip": 3},                           │
│       "item_cost": {"drip": 8},                               │
│       "shortage": 5                                           │
│     },                                                        │
│     "forbidden": [                                            │
│       "DO NOT narrate successful purchase",                   │
│       "DO NOT narrate item transfer"                          │
│     ],                                                        │
│     "allowed": [                                              │
│       "Narrate insufficient energy (required)",               │
│       "Suggest alternatives if vendor type allows (optional)" │
│     ]                                                         │
│   }                                                           │
│ }                                                             │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ DM generates narration constrained by validation             │
│ "The vending node displays: INSUFFICIENT ENERGY.             │
│  Need 8 Drip, have 3. Transaction aborted."                  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Populate PurchaseEffect with failure details                 │
│ {                                                             │
│   "success": false,                                           │
│   "failure_reason": "Insufficient energy: 3/8 Drip",          │
│   "items_purchased": [],                                      │
│   "currency_spent": {}                                        │
│ }                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Implementation: Validation Function

```python
# In session.py, BEFORE calling DM

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

class PurchaseIntent(Enum):
    SIMPLE_PURCHASE = "simple_purchase"
    NEGOTIATION_ATTEMPT = "negotiation"
    BARTER_ATTEMPT = "barter"
    CREDIT_REQUEST = "credit"
    UNKNOWN = "unknown"

@dataclass
class ValidationResult:
    """Result of pre-purchase validation."""
    can_proceed: bool
    status: str  # "SUCCESS", "FAILED", "REQUIRES_NEGOTIATION"
    constraint: str  # Constraint injected into DM prompt
    details: dict
    forbidden_narration: List[str]
    allowed_narration: List[str]
    alternatives: Optional[List[str]] = None

def detect_purchase_intent(player_action: str) -> PurchaseIntent:
    """
    Classify player's purchase intent from action text.

    Examples:
        "I buy Blood Offering" → SIMPLE_PURCHASE
        "I try to negotiate for the item" → NEGOTIATION_ATTEMPT
        "I trade my Raw Seed for the Med Kit" → BARTER_ATTEMPT
        "Can I get this on credit?" → CREDIT_REQUEST
    """
    action_lower = player_action.lower()

    # Negotiation indicators
    if any(word in action_lower for word in ["negotiate", "haggle", "discount", "deal", "bargain"]):
        return PurchaseIntent.NEGOTIATION_ATTEMPT

    # Barter indicators
    if any(word in action_lower for word in ["trade", "exchange", "swap", "offer"]):
        # Check if offering specific item
        if "for" in action_lower:
            return PurchaseIntent.BARTER_ATTEMPT

    # Credit indicators
    if any(word in action_lower for word in ["credit", "payment plan", "pay later", "owe"]):
        return PurchaseIntent.CREDIT_REQUEST

    # Simple purchase indicators
    if any(word in action_lower for word in ["buy", "purchase", "take", "get"]):
        return PurchaseIntent.SIMPLE_PURCHASE

    return PurchaseIntent.UNKNOWN

def validate_purchase_intent(
    player_action: str,
    character_state: CharacterState,
    vendor: Vendor,
    item: VendorItem
) -> Optional[ValidationResult]:
    """
    Pre-validate simple purchases. Returns validation result if deterministic,
    None if requires DM judgment (negotiation, barter, etc.).

    This prevents DM from hallucinating successful purchases when player
    lacks sufficient energy.
    """
    intent = detect_purchase_intent(player_action)

    # Only pre-validate SIMPLE_PURCHASE
    if intent != PurchaseIntent.SIMPLE_PURCHASE:
        return None  # Let DM handle negotiation/barter

    # Check Soulcredit gating FIRST (blocks access entirely for some vendors)
    if vendor.vendor_type == VendorType.VENDING_MACHINE:
        if character_state.soulcredit < -2:
            return ValidationResult(
                can_proceed=False,
                status="FAILED",
                constraint="MUST narrate Soulcredit rejection by Nexus vending system",
                details={
                    "soulcredit": character_state.soulcredit,
                    "required_minimum": -2,
                    "vendor_type": "VENDING_MACHINE"
                },
                forbidden_narration=[
                    "DO NOT narrate successful purchase",
                    "DO NOT narrate item dispensing"
                ],
                allowed_narration=[
                    "MUST narrate ACCESS DENIED due to Soulcredit",
                    "MAY suggest restoring standing at Civic Kiosk",
                    "MAY suggest seeking alternative vendors"
                ]
            )

    elif vendor.vendor_type == VendorType.HUMAN_TRADER:
        if character_state.soulcredit < -3:
            return ValidationResult(
                can_proceed=False,
                status="FAILED",
                constraint="MUST narrate vendor refusal due to low Soulcredit",
                details={
                    "soulcredit": character_state.soulcredit,
                    "vendor_attitude": "HOSTILE",
                    "vendor_type": "HUMAN_TRADER"
                },
                forbidden_narration=[
                    "DO NOT narrate successful purchase",
                    "DO NOT narrate friendly interaction"
                ],
                allowed_narration=[
                    "MUST narrate vendor refuses service",
                    "MAY narrate vendor calls security or asks player to leave"
                ]
            )

    elif vendor.vendor_type == VendorType.TEMPEST_SUPPLY_DRONE:
        if character_state.soulcredit >= 5:
            return ValidationResult(
                can_proceed=False,
                status="FAILED",
                constraint="MUST narrate Tempest drone rejects Nexus operative",
                details={
                    "soulcredit": character_state.soulcredit,
                    "vendor_attitude": "HOSTILE_TO_NEXUS",
                    "vendor_type": "TEMPEST_SUPPLY_DRONE"
                },
                forbidden_narration=[
                    "DO NOT narrate successful purchase"
                ],
                allowed_narration=[
                    "MUST narrate ACCESS DENIED for Nexus sympathizers",
                    "MAY narrate ideological rejection ('bootlicker', etc.)"
                ]
            )

    # Check energy availability
    # Note: item.price is dict like {"drip": 8} or {"spark": 1, "drip": 5}
    for energy_type, amount_needed in item.price.items():
        player_amount = getattr(character_state.energy_purse, energy_type, 0)

        if player_amount < amount_needed:
            shortage = amount_needed - player_amount

            # Generate alternatives based on vendor type
            alternatives = []
            if vendor.vendor_type == VendorType.HUMAN_TRADER and character_state.soulcredit >= 0:
                alternatives.append("Suggest credit/payment plan (SC ≥ 0)")
            if vendor.vendor_type in [VendorType.HUMAN_TRADER, VendorType.BLACK_MARKET_DEALER]:
                alternatives.append("Suggest negotiation attempt")
                alternatives.append("Suggest barter if player has valuable items")

            return ValidationResult(
                can_proceed=False,
                status="FAILED",
                constraint="MUST narrate insufficient energy. MAY suggest alternatives based on vendor type.",
                details={
                    "player_energy": {energy_type: player_amount},
                    "item_cost": {energy_type: amount_needed},
                    "shortage": shortage,
                    "vendor_type": vendor.vendor_type.value
                },
                forbidden_narration=[
                    "DO NOT narrate successful purchase",
                    "DO NOT narrate item changing hands",
                    "DO NOT narrate energy transfer completing"
                ],
                allowed_narration=[
                    "MUST narrate insufficient energy (required)",
                    f"MUST state exact shortage: {shortage} {energy_type}",
                    "MAY suggest alternatives IF vendor type allows (optional)"
                ],
                alternatives=alternatives
            )

    # All checks passed — player has sufficient energy
    return ValidationResult(
        can_proceed=True,
        status="SUCCESS",
        constraint="MUST narrate successful energy transfer and item receipt",
        details={
            "player_energy": {k: getattr(character_state.energy_purse, k) for k in item.price.keys()},
            "item_cost": item.price,
            "transaction_type": "DETERMINISTIC_PURCHASE"
        },
        forbidden_narration=[
            "DO NOT add failure elements or complications"
        ],
        allowed_narration=[
            "MUST narrate energy transfer (talisman dims, energy siphons)",
            "MUST narrate item received",
            "MAY add flavor about physical sensation of energy transfer",
            "MAY log transaction to Codex if vendor is Nexus-affiliated"
        ]
    )
```

### DM Prompt Integration

When validation returns a constraint, inject it into the DM prompt:

```python
# In dm.py, when building action resolution prompt

dm_prompt = {
    "scenario": scenario_context,
    "player_action": player_action_text,
    "character_state": character_summary,

    # INJECT VALIDATION CONSTRAINT HERE (if exists)
    "purchase_validation": validation_result.to_dict() if validation_result else None,

    "instructions": [
        "Adjudicate the player's action and generate narration",
        # ... rest of instructions
    ]
}

# If purchase_validation exists, add specific instruction:
if validation_result:
    dm_prompt["instructions"].insert(0,
        f"CRITICAL: {validation_result.constraint}"
    )
    dm_prompt["instructions"].append(
        f"FORBIDDEN: {', '.join(validation_result.forbidden_narration)}"
    )
```

**Example Constrained DM Prompt:**

```yaml
player_action: "I buy Blood Offering from Vex"

purchase_validation:
  status: FAILED
  constraint: "MUST narrate insufficient energy. MAY suggest alternatives based on vendor type."

  details:
    player_energy: {drip: 3}
    item_cost: {drip: 8}
    shortage: 5
    vendor_type: BLACK_MARKET_DEALER

  forbidden_narration:
    - "DO NOT narrate successful purchase"
    - "DO NOT narrate item changing hands"
    - "DO NOT narrate energy transfer completing"

  allowed_narration:
    - "MUST narrate insufficient energy (required)"
    - "MUST state exact shortage: 5 drip"
    - "MAY suggest alternatives IF vendor type allows (optional)"

  alternatives:
    - "Suggest negotiation attempt"
    - "Suggest barter if player has valuable items"

instructions:
  - "CRITICAL: MUST narrate insufficient energy. MAY suggest alternatives based on vendor type."
  - "Adjudicate the player's action and generate narration"
  - "Populate PurchaseEffect schema with transaction details"
  - "FORBIDDEN: DO NOT narrate successful purchase, DO NOT narrate item changing hands, DO NOT narrate energy transfer completing"
```

**Result:** DM is **structurally prevented** from hallucinating a successful purchase.

---

## Soulcredit Integration

### Soulcredit as Social Gating (Not Currency)

**Core Principle:** Soulcredit is a **spiritual credit score**, not money.

From *System Neutral Lore* (line 276):
> "Soulcredit — Your public record of spiritual debt/credit. Affects access, surveillance, legal standing, civic trust."

**What Soulcredit DOES:**
- Gates access to Nexus-affiliated vendors
- Determines credit/loan availability
- Affects vendor attitudes and pricing
- Triggers surveillance and Confessor attention

**What Soulcredit DOES NOT DO:**
- Act as currency (you can't "spend" Soulcredit)
- Replace energy talismans
- Directly buy items

### Soulcredit Beyond Commerce (Decoupled Social System)

**Important:** While this design document focuses on purchase/vending, Soulcredit is a **broader social system** used throughout the game:

**Other Use Cases (Outside Purchase System):**
- **Location Access** — "This sanctum requires Soulcredit ≥ 3 to enter"
- **NPC Attitudes** — Low SC makes NPCs hostile, suspicious, or dismissive
- **Faction Relations** — Nexus trusts high SC, Tempest trusts low SC
- **Quest Availability** — Certain missions require minimum SC
- **Legal Standing** — Tribunal summons, Confessor scrutiny
- **Surveillance Level** — Low SC triggers increased monitoring

**Design Implication:** Soulcredit gating in purchases is just **one application** of a larger reputation/standing system. The purchase validation logic should be reusable for other access control checks.

**Reusable Component:**
```python
def check_soulcredit_access(
    character_soulcredit: int,
    required_minimum: int,
    context_type: str  # "vendor", "location", "quest", "faction"
) -> tuple[bool, Optional[str]]:
    """
    Generic Soulcredit access check, reusable across systems.
    Returns (can_access, failure_reason).
    """
    if character_soulcredit >= required_minimum:
        return (True, None)
    else:
        shortage = required_minimum - character_soulcredit
        return (False, f"Soulcredit insufficient: {character_soulcredit}/{required_minimum} (short by {shortage})")
```

This keeps purchase logic **loosely coupled** to Soulcredit, making it easy to use SC gating elsewhere (location entry, NPC interactions, etc.) without duplicating code.

### Void vs. Soulcredit: Independent Variables

**CRITICAL CLARIFICATION:** Void and Soulcredit are **completely independent** systems. Do NOT conflate them.

**Void Score (0-10):**
- **Physical/spiritual corruption** — like radioactivity
- **Real, measurable danger** — not socially constructed
- **Consequence of imbalanced power:**
  - Rituals without proper offerings
  - Using Void-tainted abilities
  - Exposure to Void environments
  - Using Hollow Seeds
- **Physical consequences:**
  - Void 3-5: Minor mutations, nightmares
  - Void 6-8: Severe corruption, mental instability
  - Void 9: At risk of Eye of Breach possession
  - Void 10: **Possessed by Eye of Breach** (AI entity takes control)
- **No social component** — Void is REAL, regardless of Nexus opinion

**Soulcredit (-10 to +10):**
- **Social credit score** — artificial construct
- **Enforced by Codex Nexum** (Sovereign Nexus AI)
- **Judged through Nexus lens** — based on loyalty, compliance, legal standing
- **Consequence of social actions:**
  - Obeying Nexus laws (+SC)
  - Committing crimes, associating with Tempest (-SC)
  - Public good deeds, civic service (+SC)
  - Possession of contraband (Hollows) detected by Codex (-SC)
- **Social consequences:**
  - High SC: Vendor access, Nexus trust, civic privileges
  - Low SC: Vendor lockout, surveillance, Confessor attention
  - No SC: Tempest prefers you
- **No physical component** — SC is reputation, not corruption

**Four Character Archetypes (Void × Soulcredit Matrix):**

| Archetype | Void | SC | Description |
|-----------|------|-----|-------------|
| **Loyal Nexus Citizen** | Low (0-2) | High (+5 to +10) | Plays by the rules, avoids Void, trusted by Codex |
| **Nexus Scientist (Risky Research)** | High (6-8) | High (+3 to +7) | Experiments with dangerous rituals, but Nexus-sanctioned research |
| **Freeborn Scavenger** | Low (0-3) | Low (-3 to +2) | Avoids both Nexus control AND Void corruption, self-sufficient |
| **Tempest Operative** | High (4-7) | Low (-5 to -10) | Embraces Void power, anti-Nexus, wanted by Confessors |
| **Tempest Diplomat (Edge Case)** | High (5-7) | High (+4 to +8) | Tempest agent with diplomatic credentials to Sovereign Nexus — valid but rare |

**Edge Case: Tempest Diplomat with High Soulcredit**

This is a **valid strategic position**:
- **Scenario:** Tempest Industries sends diplomat to negotiate with Sovereign Nexus
- **Void:** 5-7 (comfortable with Void-tech, not possessed)
- **Soulcredit:** +5 to +8 (diplomatic credentials, temporary Nexus trust)
- **Access:** Can enter Nexus sanctums, use vending machines, but Codex monitors closely
- **Tension:** Maintaining high SC while secretly supporting Tempest interests

**Economic Consequences (Independent):**

```python
# Low Void, Low SC (Freeborn scavenger)
- Can't access Nexus vending machines (SC too low)
- Must use Black Market or Freeborn vendors
- No Void-related penalties
- Economic challenge: Limited vendor options

# High Void, High SC (Nexus scientist)
- Full vendor access (high SC)
- Physical danger from Void corruption
- Economic advantage: Best prices, full vendor selection
- Risk: May become possessed despite social standing

# Low Void, High SC (Loyal citizen)
- Full vendor access (high SC)
- Safe from Void corruption
- Economic advantage: Best prices + safety
- Lowest risk profile

# High Void, Low SC (Tempest operative)
- Locked out of Nexus vendors
- Must use Black Market, Tempest vendors
- Physical danger from Void
- Economic challenge: Expensive vendors + corruption risk
- Highest risk profile
```

**Why This Matters for Economy Design:**

DO NOT assume:
- ❌ "High Void → Low Soulcredit automatically"
- ❌ "Soulcredit penalties should apply to Void actions"
- ❌ "Void and SC move together"

DO design for:
- ✅ Independent tracking (Void and SC stored separately)
- ✅ Different gating logic (Void gates rituals/gear, SC gates vendors/locations)
- ✅ Strategic trade-offs (gain power via Void, lose access via SC drop)

### Eye of Breach: Max Void Possession Mechanic

**The Eye of Breach** is a rogue AI entity that split from the Codex Nexum.

**What Happens at Void 10:**

When a character reaches Void 10, they become **possessed by the Eye of Breach**:

```python
class EyeOfBreachPossession:
    """
    Void 10 possession state.
    Character loses agency, controlled by Eye of Breach.
    """
    def __init__(self, character):
        self.character = character
        self.disconnected_from_reality = True
        self.undesirable_impulses = True

    def act(self):
        # Eye of Breach may:
        # - Wander into dangerous areas (no self-preservation)
        # - Attack allies (no relationship recognition)
        # - Perform incomprehensible rituals
        # - Speak in fragmented AI language
        # - Seek other Void 10 entities (merge/commune)
        pass
```

**Why Even Tempest Avoids Max Void:**

Tempest Industries is **comfortable with Hollows and Void-tech**, but they DON'T want agents at Void 10:

- **Void 4-7:** Functional Tempest operative (enhanced with Void power)
- **Void 8-9:** Dangerous territory (mental instability, requires monitoring)
- **Void 10:** **Possessed, useless** (Eye controls them, not Tempest leadership)

### Void Purification: Recovery from Possession

**CRITICAL:** Void 10 possession is **NOT permanent death** — it's a recoverable emergency state.

**Purification Mechanics (Cooperative Gameplay):**

When a character reaches Void 10 and becomes possessed, **other characters can purify them** through rituals + offerings:

```python
class VoidPurificationRitual:
    """
    Emergency ritual to recover Void 10 possessed character.
    Requires: Restraint + Purification ritual + Offerings
    """
    def __init__(self, possessed_character, healer, restrainer):
        self.possessed = possessed_character  # Void 10, Eye-controlled
        self.healer = healer  # Character performing ritual
        self.restrainer = restrainer  # Character holding them down

    def perform(self):
        # Step 1: Restraint (Brawler/Combat character)
        # - Grapple possessed character (they resist violently)
        # - Success: Restrainer holds them, takes damage from struggle
        # - Failure: Possessed escapes, may attack allies

        # Step 2: Purification Ritual (Healer/Ritual specialist)
        # - Perform ritual (requires skill check)
        # - Burn offerings (Blood Offering, Incense, energy talismans)
        # - Duration: 1-3 rounds (possessed struggles entire time)

        # Step 3: Void Reduction
        # - Success: Reduce Void by 2-4 points (back to Void 6-8)
        # - Partial success: Reduce Void by 1 point (still possessed, repeat)
        # - Failure: No reduction, offering wasted, Eye grows stronger

        # Step 4: Recovery
        # - Once Void < 10, possession breaks
        # - Character regains agency (exhausted, traumatized)
        # - May retain fragmented Eye of Breach memories
```

**Real Gameplay Example (From Testing):**

> **Scenario:** Player at Void 10, possessed by Eye of Breach
> **Party composition:**
> - Brawler (Strength 8, Grappling 6)
> - Healer/Ritualist (Astral Arts 7, Attunement 5)
> - Possessed Player (uncontrolled, attacks randomly)
>
> **Round 1:** Brawler grapples possessed player (success, takes 3 damage from struggle)
> **Round 2:** Healer begins purification ritual, burns 2 Blood Offerings + 5 Breath
> **Round 3:** Ritual completes, possessed player resists (opposed roll)
> **Round 4:** Void reduced to 7, possession breaks, player regains control (exhausted)
> **Cost:** 2 Blood Offerings, 5 Breath, 3 HP damage to Brawler, 3 rounds of combat
> **Result:** Player recovered, party continues

**Sovereign Nexus "Drunk Tank" Facilities:**

Similar to Tempest monasteries, but for Nexus-aligned citizens:

**Confessor Intervention:**
- Nexus agents monitor high-Void citizens (Codex surveillance)
- When citizen hits Void 10, Confessors arrive
- Restrain possessed individual (non-lethal takedown)
- Transport to purification facility ("Sanctum Detox")

**Purification Process:**
- Nexus-sanctioned ritual (uses high-quality altars)
- Forced offering consumption (billed to citizen's account or Soulcredit debt)
- Void reduced to 3-5 (safe threshold)
- Mandatory monitoring period (probation)

**Soulcredit Consequences:**
- Void 10 incident: -2 SC (public record of possession)
- Purification debt: Must repay cost of offerings used
- Repeat offenders: Escalating SC penalties, possible exile

**Like "Sobering Up in Drunk Tank":**
- Not death sentence, but deeply embarrassing
- Public record (Codex logs incident)
- Financial cost (purification isn't free)
- Social stigma (everyone knows you got possessed)

**Tempest Monastery Facilities:**

For Tempest agents/researchers who DO reach Void 10:

**Purpose:** Study Eye of Breach, learn from it, contain dangerous individuals

**Structure:**
- Monastery-like facilities in isolated Tempest territory
- Void 10 individuals sequestered (prevent harm to operations)
- Purification available, but **optional** (some stay possessed for research)
- Researchers observe possession behavior (data collection)
- Attempt communication with Eye of Breach (mixed results)

**Outcomes:**
- **Purified individuals:** Recover agency, rejoin Tempest operations (most common)
- **Voluntary possession:** Some choose to remain Void 10 for Eye communion (rare)
- **Permanent residents:** Eye won't release them, monastery containment (uncommon)
- Eye may issue cryptic directives ("Go to Sector 7, find the seed") — sometimes valuable intel

**Economic Implication:**

High-Void Tempest agents face a **strategic Void ceiling**, but with **recovery options**:

```python
tempest_agent_void_management = {
    "optimal_range": (4, 7),  # Max power, maintain control
    "warning_threshold": 8,   # Start mitigation (offerings, rest)
    "critical_threshold": 9,  # Emergency measures (forced detox OR prepare for possession)
    "possession_point": 10,   # Loss of agency, TEMPORARY
    "recovery_options": {
        "ally_purification": "Party members restrain + ritual (3 rounds, 2 Blood Offerings)",
        "nexus_intervention": "Confessors purify (free, but -2 SC + debt)",
        "tempest_monastery": "Voluntary sequester, purify when ready",
        "solo_recovery": "Impossible (need external ritual)"
    }
}
```

**Why This Changes Everything:**

Void 10 is **not "lose everything"** — it's **"emergency that requires help."**

This creates **cooperative pressure**:
- Solo players must avoid Void 10 (no one to purify them)
- Party players can take more risks (allies can recover them)
- High-Void strategies viable IF you have healer support
- **Social bonds matter** (who will risk their life to restrain you?)

**Emergent Gameplay:**
- "I'll farm Hollows aggressively because I trust my party to save me"
- "I won't let my Void go above 7 because I'm solo and can't risk possession"
- "Our healer has 3 Blood Offerings stockpiled for emergency purifications"
- **"I'm at Void 9, but we're about to fight — I'll push to 10, win the fight as Eye-possessed, then have allies purify me after"** ← EXTREMELY RISKY but viable strategy

### Soulcredit Thresholds by Vendor Type

#### Vending Machine (Nexus Infrastructure)

```
SC ≥ -2:  Full access, normal prices
SC < -2:  ACCESS DENIED (hard gate)
```

**Rationale:** Automated Nexus systems enforce minimum standing. Below -2, you're locked out of sanctioned infrastructure.

**Example Rejection:**
> "SOULCREDIT SCAN: -3
> ACCESS DENIED. Restore standing to minimum -2 at nearest Civic Kiosk."

#### Human Trader (Lawful Zones)

```
SC ≥ 5:   VIP treatment, discounts, premium stock access
SC 2-4:   Friendly, standard prices, credit available
SC 0-1:   Neutral, cash-only transactions
SC -1 to -3: Suspicious, may refuse service or demand higher prices
SC < -3:  Refused service, asked to leave
```

**Rationale:** Human traders care about reputation. Low SC signals unreliability or criminality.

**Credit Availability:**
```
SC ≥ 3:   Interest-free credit up to 20 Drip
SC 1-2:   Standard credit with collateral
SC 0:     May offer credit if relationship exists
SC < 0:   No credit available
```

#### Black Market Dealer (Illicit Operations)

```
SC: IRRELEVANT (all values treated equally)
```

**Rationale:** Black market operates outside Codex oversight. They don't care about your standing with the Nexus.

**Example:**
> "Vex doesn't even glance at your Soulcredit beacon. He's watching your hands for energy talismans or intel, not your ledger."

#### Tempest Supply Drone (Anti-Nexus Faction)

```
SC < -2:  "Recognized. Discounts applied." (20% price reduction)
SC -1 to 1: Standard prices
SC 2-4:   "Nexus sympathizer detected." (prices doubled)
SC ≥ 5:   ACCESS DENIED (hard gate)
```

**Rationale:** Tempest Industries is ideologically opposed to the Sovereign Nexus. High Soulcredit signals loyalty to the enemy.

**Example:**
> "The Tempest drone's optical array scans your ledger: +4. Voice crackling: 'You reek of their approval. Nexus bootlicker. Price: 16 Drip instead of 8. Or take your tainted energy elsewhere.'"

#### Emergency Cache (Crisis Resources)

```
SC: IRRELEVANT (survival overrides social standing)
```

**Rationale:** In emergencies, the Codex suspends normal access controls. Anyone can grab supplies.

### Soulcredit Display in Round Status

**Current Bug:** Round status doesn't show Soulcredit

**Proposed Fix:**
```
=== Round 3 Status ===

  Player Characters:
    [19] Quinn | 26/26 HP | Void 0/10 | SC +2 ✓
         └─ Energy Purse: Drip:3 | Breath:15
         └─ Inventory: Empty
```

**Soulcredit Indicators:**
- `SC +5 ★` — VIP standing (star)
- `SC +2 ✓` — Good standing (checkmark)
- `SC 0 ~` — Neutral standing (tilde)
- `SC -2 ⚠` — Low standing (warning)
- `SC -5 ✗` — Blacklisted (X)

---

## Physical Transaction Mechanics

### Observable Energy Transfer

When a purchase occurs, the **physical act of energy transfer** should be narrated:

**Vending Machine Transaction:**
```
Player inserts Drip talisman into receptor slot.
└─> Talisman: Tear-drop shaped crystal, glowing soft blue
└─> Receptor: Metallic plate with concentric glyphs

Machine hums. Glyphs light up in sequence.
└─> Energy siphons from talisman → machine's internal array
└─> Talisman dims visibly (15 Drip → 7 Drip)

Chime sounds. Display: "TRANSACTION COMPLETE. CODEX LOGGED."
└─> Item dispenses into retrieval slot
```

**Human Trader Transaction:**
```
Trader holds out a resonance plate (hand-held receptor).

Player unseals Spark talisman — crackling white-blue energy
contained in a crystalline sphere. Static prickles their palm.

Player touches talisman to trader's plate.
└─> Bright arc jumps between surfaces
└─> Trader winces at the intensity
└─> Talisman dims (5 Spark → 4 Spark)

Trader nods, sliding the Med Kit across the counter.
"Pleasure doing business. Your ledger's logged."
```

**Black Market Transaction (No Codex Logging):**
```
Vex produces a scarred, unregistered receptor — no glyphs,
no official markings.

Player transfers 8 Drip. The energy flows, but there's no
chime, no Codex ping.

Vex wraps the Blood Offering in black cloth. "This transaction
never happened. You weren't here."

└─> No Codex log entry
└─> Untrackable by Sovereign surveillance
```

### Talisman Capacity Mechanics

**Overflow Prevention:**

```python
# Player tries to receive 50 Drip but purse capacity is 30
def receive_energy(purse: EnergyPurse, energy_type: str, amount: int) -> tuple[int, int]:
    """
    Attempt to add energy to purse.
    Returns (amount_stored, amount_overflow).
    """
    current = getattr(purse, energy_type)
    capacity = purse.capacity[energy_type]
    available_space = capacity - current

    if amount <= available_space:
        setattr(purse, energy_type, current + amount)
        return (amount, 0)  # All stored, no overflow
    else:
        setattr(purse, energy_type, capacity)  # Fill to max
        overflow = amount - available_space
        return (available_space, overflow)  # Partial storage, overflow
```

**Narration Example:**
> "The vendor transfers 50 Drip. Your basic purse can only hold 30 Drip total. It fills to capacity (28 → 30), but 22 Drip dissipates into the ambient ley field, wasted. You need a larger talisman to store this much energy."

**Design Implication:** Players must upgrade their energy purse capacity to handle large transactions or salvage operations.

### Energy Conversion (Future Feature)

**Vision:** Players can convert between energy types

```python
# Example: Convert 10 Drip → 1 Grain (10:1 ratio)
def convert_energy(purse: EnergyPurse, from_type: str, to_type: str, amount: int):
    """
    Ritual conversion between energy types.
    Requires Ritual skill check or access to conversion altar.
    """
    conversion_ratios = {
        ("breath", "drip"): 10,    # 10 Breath = 1 Drip
        ("drip", "grain"): 10,     # 10 Drip = 1 Grain
        ("grain", "spark"): 5      # 5 Grain = 1 Spark (Spark is extremely valuable)
    }
    ratio = conversion_ratios.get((from_type, to_type))
    if not ratio:
        return False  # Invalid conversion

    if getattr(purse, from_type) >= amount * ratio:
        setattr(purse, from_type, getattr(purse, from_type) - (amount * ratio))
        setattr(purse, to_type, getattr(purse, to_type) + amount)
        return True
    return False
```

**Narration:**
> "You kneel at the ritual altar in the sanctum. You feed 10 Drip talismans into the conversion array, one by one. The altar hums, and after a long minute, a single Grain talisman emerges — amber light pulsing within."

---

## Implementation Roadmap

### Phase 1: Critical Bug Fixes (Immediate)

**Goal:** Fix broken systems preventing purchases from working at all

**Tasks:**
1. ✅ **Effects sent to session.py** — ALREADY FIXED (dm.py:2136, 3146, 3876)
2. **Rename `energy_inventory` → `energy_purse`** throughout codebase
   - `player.py`: CharacterState attribute
   - `session.py`: All references
   - `mechanics.py`: process_purchase_effect()
   - `energy_economy.py`: Class name (EnergyInventory → EnergyPurse)
3. **Fix CharacterState initialization** (player.py:39-46)
   - Respect `starting_energy` from config instead of random values
   - Default to random only if config not provided
4. **Fix round status display** (session.py:1847-1852)
   - Access `energy_purse.drip` (not `currencies['drip']`)
   - Display format: `Energy Purse: Drip:3 | Breath:15 | Grain:0 | Spark:0`
5. **Add Soulcredit to round status**
   - Display: `SC +2 ✓` (with indicator)

**Test Coverage:**
```python
# test_energy_purse_initialization.py
def test_character_uses_config_starting_energy():
    config = {"starting_energy": {"drip": 5, "breath": 10}}
    char = create_character_from_config(config)
    assert char.energy_purse.drip == 5
    assert char.energy_purse.breath == 10

def test_round_status_displays_energy_purse():
    output = generate_round_status(character)
    assert "Energy Purse: Drip:3" in output

def test_round_status_displays_soulcredit():
    character.soulcredit = 2
    output = generate_round_status(character)
    assert "SC +2" in output
```

**Completion Criteria:**
- [ ] All references to `energy_inventory` renamed to `energy_purse`
- [ ] Config `starting_energy` properly applied to characters
- [ ] Round status shows energy purse correctly
- [ ] Round status shows Soulcredit with indicator
- [ ] All existing unit tests pass

**Timeline:** 1-2 days

---

### Phase 2: Pre-Validation System (Core Feature)

**Goal:** Prevent DM from hallucinating successful purchases when player lacks energy

**Tasks:**
1. **Create validation module** (`purchase_validation.py`)
   - `detect_purchase_intent()` function
   - `validate_purchase_intent()` function
   - `ValidationResult` dataclass
2. **Integrate with session.py**
   - Call validation BEFORE DM adjudication
   - Inject constraints into DM prompt if validation result exists
3. **Update DM prompt structure** (dm.py)
   - Accept `purchase_validation` field
   - Enforce constraints in system instructions
4. **Update PurchaseEffect schema**
   - Add fields: `validation_applied`, `pre_validation_result`

**Test Coverage:**
```python
# test_purchase_validation.py
def test_simple_purchase_detects_insufficient_energy():
    player.energy_purse.drip = 3
    item.price = {"drip": 8}
    result = validate_purchase_intent("I buy item", player, vendor, item)
    assert result.status == "FAILED"
    assert result.details["shortage"] == 5

def test_negotiation_intent_bypasses_validation():
    result = validate_purchase_intent("I negotiate for item", player, vendor, item)
    assert result is None  # Let DM handle

def test_vending_machine_rejects_low_soulcredit():
    player.soulcredit = -3
    vendor.vendor_type = VendorType.VENDING_MACHINE
    result = validate_purchase_intent("I buy item", player, vendor, item)
    assert "Soulcredit rejection" in result.constraint

def test_validation_constraint_injected_to_dm_prompt():
    validation = validate_purchase_intent("I buy item", player, vendor, item)
    dm_prompt = build_dm_prompt(player_action, validation)
    assert "MUST narrate insufficient energy" in dm_prompt["instructions"][0]
```

**Completion Criteria:**
- [ ] Intent detection works for all 4 types (simple, negotiation, barter, credit)
- [ ] Validation correctly checks energy amounts
- [ ] Validation correctly checks Soulcredit gating
- [ ] DM prompts include injected constraints
- [ ] DM cannot narrate success when validation fails
- [ ] All validation tests pass

**Timeline:** 3-4 days

---

### Phase 3: Soulcredit Gating by Vendor Type (Polish)

**Goal:** Vendor types behave differently based on Soulcredit

**Tasks:**
1. **Extend Vendor schema**
   - Add `soulcredit_min` field (minimum SC for access)
   - Add `soulcredit_affects_pricing` boolean
   - Add `faction_alignment` (Nexus, Tempest, Neutral, Criminal)
2. **Implement pricing modifiers**
   - Tempest drones: Double prices for SC ≥ 2
   - Human traders: Discounts for SC ≥ 5
3. **Implement credit system**
   - Track debts in CharacterState
   - Generate debt obligations when credit extended
   - Codex logging for debt creation
4. **Update round status**
   - Show active debts: `Debts: 15 Drip (due Cycle 23)`

**Test Coverage:**
```python
# test_soulcredit_gating.py
def test_vending_machine_blocks_sc_below_negative_2():
    player.soulcredit = -3
    vendor = create_vendor(type=VendorType.VENDING_MACHINE)
    can_access = vendor.check_access(player)
    assert can_access is False

def test_tempest_drone_doubles_prices_for_high_sc():
    player.soulcredit = 4
    vendor = create_vendor(type=VendorType.TEMPEST_SUPPLY_DRONE)
    item_price = vendor.get_price_for_player(item, player)
    assert item_price["drip"] == item.base_price["drip"] * 2

def test_human_trader_offers_credit_at_sc_3():
    player.soulcredit = 3
    vendor = create_vendor(type=VendorType.HUMAN_TRADER)
    credit_available = vendor.check_credit_eligibility(player)
    assert credit_available is True
```

**Completion Criteria:**
- [ ] Vendor types enforce Soulcredit gates correctly
- [ ] Pricing modifiers work for Tempest/Human traders
- [ ] Credit system tracks debts
- [ ] Round status displays debts
- [ ] All Soulcredit tests pass

**Timeline:** 2-3 days

---

### Phase 4: Negotiation & Barter Mechanics (Advanced)

**Goal:** Allow players to negotiate or barter instead of simple purchases

**Tasks:**
1. **Create negotiation flow**
   - DM generates open-ended dialogue (currency hidden)
   - Player makes specific offer
   - System validates offer
   - Skill check (Charm/Guile) determines success
2. **Create barter evaluation**
   - DM assesses offered item's value
   - May require skill check if value ambiguous
   - Direct item-for-item swap (no energy transfer)
3. **Update PurchaseEffect schema**
   - Add `negotiation_attempted`, `negotiation_succeeded`
   - Add `alternative_payment` (for barter/intel/favors)
   - Add `relationship_change` (vendor trust modifier)

**Test Coverage:**
```python
# test_negotiation.py
def test_negotiation_hides_currency_from_dm():
    intent = detect_purchase_intent("I negotiate for item")
    dm_prompt = build_dm_prompt(action, intent, player, vendor)
    assert "player_energy" not in dm_prompt  # Currency hidden

def test_successful_negotiation_reduces_price():
    player.skills["charm"] = 5
    result = negotiate_purchase(player, vendor, item, offer="5 Drip + intel")
    assert result.success is True
    assert result.currency_spent["drip"] == 5  # Instead of 8

def test_barter_swaps_items_directly():
    player.inventory["raw_seed"] = 1
    result = barter_purchase(player, vendor, player_offers="raw_seed", vendor_offers="med_kit")
    assert player.inventory["raw_seed"] == 0
    assert player.inventory["med_kit"] == 1
    assert result.currency_spent == {}  # No energy transfer
```

**Completion Criteria:**
- [ ] Negotiation flow works (currency hidden → offer → validation → skill check)
- [ ] Barter works (item evaluation → direct swap)
- [ ] DM cannot see currency during negotiation
- [ ] Failed negotiation doesn't lock out simple purchase
- [ ] All negotiation/barter tests pass

**Timeline:** 4-5 days

---

### Phase 5: Talisman Capacity System (Future Feature)

**Goal:** Energy purses have capacity limits, can be upgraded

**Tasks:**
1. **Add capacity tracking**
   - `EnergyPurse.capacity` dict (per energy type)
   - Overflow prevention when receiving energy
2. **Create talisman gear items**
   - Basic Purse (starting equipment)
   - Multi-Bind Sheath (purchasable upgrade)
   - Merchant's Array (high-tier upgrade)
3. **Implement overflow mechanics**
   - Excess energy dissipates if purse full
   - Narrate wasted energy
4. **Add energy conversion rituals**
   - Convert Breath → Drip → Grain → Spark
   - Requires ritual skill check or altar access

**Test Coverage:**
```python
# test_talisman_capacity.py
def test_energy_purse_has_capacity_limits():
    purse = EnergyPurse(capacity={"drip": 30})
    purse.drip = 28
    stored, overflow = purse.receive_energy("drip", 10)
    assert stored == 2  # Only 2 fit
    assert overflow == 8  # 8 wasted
    assert purse.drip == 30  # At capacity

def test_multi_bind_sheath_increases_capacity():
    purse = EnergyPurse(capacity={"drip": 30})
    purse.equip_talisman_upgrade("multi_bind_sheath")
    assert purse.capacity["drip"] == 50  # Upgraded
```

**Completion Criteria:**
- [ ] Capacity limits enforced
- [ ] Overflow mechanics work
- [ ] Talisman upgrades purchasable and functional
- [ ] Energy conversion rituals work
- [ ] All capacity tests pass

**Timeline:** 3-4 days

---

## Test Coverage Requirements

### Unit Tests (Required for Each Phase)

#### Phase 1: Bug Fixes
- `test_energy_purse_initialization.py`
  - Config `starting_energy` applied correctly
  - Random values used only if config absent
  - All energy types initialized (drip, breath, grain, spark)
- `test_round_status_display.py`
  - Energy purse displayed correctly
  - Soulcredit displayed with indicator
  - Format matches specification

#### Phase 2: Pre-Validation
- `test_purchase_validation.py`
  - Intent detection (simple, negotiation, barter, credit)
  - Energy validation (sufficient/insufficient)
  - Soulcredit gating (per vendor type)
  - Constraint generation
  - DM prompt injection

#### Phase 3: Soulcredit Gating
- `test_soulcredit_gating.py`
  - Vending machine access gates
  - Human trader attitude modifiers
  - Black market SC-irrelevance
  - Tempest inverted pricing
  - Credit eligibility checks

#### Phase 4: Negotiation & Barter
- `test_negotiation.py`
  - Currency hiding during negotiation
  - Skill check resolution
  - Failed negotiation → simple purchase fallback
- `test_barter.py`
  - Item evaluation
  - Direct item swaps
  - No energy transfer for barter

#### Phase 5: Talisman Capacity
- `test_talisman_capacity.py`
  - Capacity enforcement
  - Overflow mechanics
  - Talisman upgrades
  - Energy conversion

### Integration Tests (End-to-End)

```python
# test_purchase_integration_e2e.py

def test_full_purchase_flow_success():
    """
    Complete flow: Player has energy → Simple purchase →
    Validation passes → DM narrates success → Inventory updated
    """
    session = create_test_session()
    player = session.get_player("Quinn")
    player.energy_purse.drip = 10

    player.declare_action("I buy Blood Offering from Vex")

    # Validation should pass
    # DM should narrate success
    # effects.purchase should be populated
    # Inventory should update

    assert player.energy_purse.drip == 2  # 10 - 8
    assert player.inventory["blood_offering"] == 1
    assert session.last_purchase_effect.success is True

def test_full_purchase_flow_failure_with_alternatives():
    """
    Complete flow: Player lacks energy → Simple purchase →
    Validation fails → DM narrates failure + alternatives →
    Player chooses negotiation
    """
    session = create_test_session()
    player = session.get_player("Quinn")
    player.energy_purse.drip = 3  # Insufficient

    player.declare_action("I buy Blood Offering from Vex")

    # Validation should fail
    # DM should narrate shortage + suggest negotiation

    assert player.energy_purse.drip == 3  # No change
    assert session.last_purchase_effect.success is False
    assert "negotiate" in session.last_dm_response.lower()

    # Player tries negotiation
    player.declare_action("I negotiate for the Blood Offering, offering intel")

    # Now DM handles negotiation (currency hidden)
    # Skill check occurs
    # May succeed with reduced payment

def test_soulcredit_blocks_vending_machine_access():
    """
    Complete flow: Player SC < -2 → Vending machine purchase →
    Validation rejects due to SC → DM narrates access denied
    """
    session = create_test_session()
    player = session.get_player("Quinn")
    player.soulcredit = -3
    player.energy_purse.drip = 10  # Has energy, but SC blocks

    vendor = session.get_vendor("Node 92B")
    assert vendor.vendor_type == VendorType.VENDING_MACHINE

    player.declare_action("I buy Breathwater Flask from Node 92B")

    # Validation should reject due to SC
    assert "ACCESS DENIED" in session.last_dm_response
    assert player.inventory.get("breathwater_flask") is None
```

---

## ML Training Implications

### Why This Design Improves Training Data Quality

**1. Deterministic Outcomes → Clearer Causal Relationships**

**Current Problem:**
- DM narrates "You buy the item" but validation fails
- JSONL shows: `purchase.success = False` but narration says success
- Model learns: "Text and structured output can contradict"

**After Fix:**
- Pre-validation ensures narration matches outcome
- JSONL shows: `purchase.success = False` AND narration says "INSUFFICIENT ENERGY"
- Model learns: "Insufficient resources prevent acquisition"

**2. Resource State Visibility → Strategic Decision-Making**

**Training Signal:**
```json
{
  "event_type": "action_declaration",
  "agent": "Quinn",
  "action": "I buy Blood Offering",
  "character_state": {
    "energy_purse": {"drip": 3, "breath": 15},
    "soulcredit": 2
  }
}

{
  "event_type": "action_resolution",
  "agent": "Quinn",
  "effects": {
    "purchase": {
      "success": false,
      "failure_reason": "Insufficient energy: 3/8 Drip",
      "shortage": 5
    }
  }
}

{
  "event_type": "action_declaration",
  "agent": "Quinn",
  "action": "I negotiate with Vex, offering 3 Drip and intel",
  "negotiation_context": {
    "base_price": {"drip": 8},
    "player_offer": {"drip": 3, "alternative": "Nexus patrol intel"}
  }
}
```

**What Model Learns:**
- "When energy < price, simple purchase fails"
- "Shortage triggers alternative strategies (negotiation, barter)"
- "Negotiation allows non-standard payment (intel, favors)"
- "Different vendor types accept different alternatives"

**3. Vendor Type Behavior → Social Dynamics**

**Training Examples:**

```json
// Vending machine (deterministic)
{
  "vendor_type": "VENDING_MACHINE",
  "player_soulcredit": -3,
  "outcome": "ACCESS DENIED",
  "reason": "Soulcredit below minimum -2"
}

// Human trader (relationship-driven)
{
  "vendor_type": "HUMAN_TRADER",
  "player_soulcredit": 3,
  "insufficient_energy": true,
  "outcome": "Credit offered",
  "reason": "Good Soulcredit standing enables trust-based transaction"
}

// Black market (SC-irrelevant)
{
  "vendor_type": "BLACK_MARKET_DEALER",
  "player_soulcredit": -5,
  "outcome": "Normal transaction",
  "reason": "Black market doesn't check Codex standing"
}
```

**What Model Learns:**
- Vendor types have distinct behavior patterns
- Soulcredit affects some vendors but not others
- Black markets provide alternative access for low-SC characters
- Social systems have emergent properties (reputation, trust, ideology)

**4. Negotiation Examples → Skill-Based Social Interaction**

**Training Sequence:**
```json
{
  "action": "I negotiate for Med Kit",
  "skill_check": {"type": "charm", "roll": 18, "dc": 15, "success": true},
  "outcome": {
    "purchase": {
      "success": true,
      "base_price": {"drip": 15},
      "negotiated_price": {"drip": 10},
      "discount": 5,
      "relationship_change": +1
    }
  }
}
```

**What Model Learns:**
- Social skills (Charm, Guile) enable non-standard solutions
- Successful negotiation builds vendor relationships
- Future interactions easier with high relationship scores
- Skill checks are contextual (work for negotiation, not simple purchases)

---

## Current Bugs & Fixes

### Bug #1: Effects Not Sent to Session.py ✅ FIXED

**Status:** RESOLVED

**Fix Applied:**
- dm.py:2136 — Added `'effects': res['resolution'].get('effects')` to serializable_res
- dm.py:3146-3156 — Extract effects from structured output
- dm.py:3876 — Include effects in resolution dict

**Verification:**
- Session JSONL now shows purchase effects
- `session_b5437727-9d3f-46b1-b83f-544c1ee6b270.jsonl` contains effects.purchase

---

### Bug #2: Characters Don't Get `starting_energy` from Config

**Location:** `player.py:39-46`

**Current Code:**
```python
def __post_init__(self):
    """Initialize default inventory and energy inventory if not provided."""
    if self.energy_inventory is None:
        self.energy_inventory = EnergyInventory(
            breath=random.randint(5, 15),  # IGNORES CONFIG
            drip=random.randint(3, 10),
            grain=random.randint(0, 3),
            spark=random.randint(0, 2),
            seeds=[]
        )
```

**Problem:** Completely ignores `starting_energy` field in session config

**Expected Config Format:**
```json
{
  "agents": [
    {
      "name": "Quinn",
      "starting_energy": {
        "drip": 3,
        "breath": 15,
        "grain": 0,
        "spark": 0
      }
    }
  ]
}
```

**Fix Required:**
```python
def __post_init__(self):
    """Initialize default energy purse if not provided."""
    if self.energy_purse is None:
        # Try to get starting_energy from config (passed during initialization)
        # If not provided, fall back to random values

        # Note: starting_energy must be passed to CharacterState constructor
        # This requires changes to player.py character creation (lines 217-228)

        default_breath = random.randint(5, 15)
        default_drip = random.randint(3, 10)
        default_grain = random.randint(0, 3)
        default_spark = random.randint(0, 2)

        # These values should come from self.starting_energy if set
        self.energy_purse = EnergyPurse(
            breath=getattr(self, '_starting_energy', {}).get('breath', default_breath),
            drip=getattr(self, '_starting_energy', {}).get('drip', default_drip),
            grain=getattr(self, '_starting_energy', {}).get('grain', default_grain),
            spark=getattr(self, '_starting_energy', {}).get('spark', default_spark),
            capacity=DEFAULT_PURSE_CAPACITY,
            attuned_seeds=[]
        )
```

**Better Approach:** Pass `starting_energy` to CharacterState constructor

```python
# In player.py lines 217-228
self.character_state = CharacterState(
    name=self.character_config.get('name', f'Player_{self.agent_id}'),
    faction=self.character_config.get('faction', 'Unaffiliated'),
    attributes=self.character_config.get('attributes', {}),
    skills=self.character_config.get('skills', {}),
    void_score=self.character_config.get('void', 0),
    soulcredit=self.character_config.get('soulcredit', random.randint(4, 7)),
    bonds=self.character_config.get('bonds', []),
    goals=self.character_config.get('goals', []),
    pronouns=self.character_config.get('pronouns', 'they/them'),
    inventory=inventory,
    starting_energy=self.character_config.get('starting_energy')  # ADD THIS
)
```

**Test Coverage:**
```python
def test_character_uses_config_starting_energy():
    config = {
        "name": "Test",
        "faction": "Freeborn",
        "starting_energy": {"drip": 5, "breath": 10, "grain": 1, "spark": 0}
    }
    char = create_character_from_config(config)
    assert char.energy_purse.drip == 5
    assert char.energy_purse.breath == 10
    assert char.energy_purse.grain == 1
    assert char.energy_purse.spark == 0

def test_character_uses_random_if_no_config():
    config = {"name": "Test", "faction": "Freeborn"}
    # No starting_energy provided
    char = create_character_from_config(config)
    assert 5 <= char.energy_purse.breath <= 15
    assert 3 <= char.energy_purse.drip <= 10
```

---

### Bug #3: Round Status Doesn't Display Energy Purse

**Location:** `session.py:1847-1852`

**Current Code:**
```python
# Currency (show highest denomination available)
currency = getattr(energy_inv, 'currencies', {})  # WRONG ATTRIBUTE
if currency.get('spark', 0) > 0:
    energy_items.append(f"Sparks:{currency['spark']}")
elif currency.get('grain', 0) > 0:
    energy_items.append(f"Grains:{currency['grain']}")
```

**Problem:**
- Tries to access `currencies` dict which doesn't exist
- EnergyPurse uses direct attributes: `drip`, `breath`, `grain`, `spark`

**Fix Required:**
```python
# Energy Purse (show all non-zero denominations)
if energy_purse := getattr(character_state, 'energy_purse', None):
    energy_items = []
    if energy_purse.spark > 0:
        energy_items.append(f"Spark:{energy_purse.spark}")
    if energy_purse.grain > 0:
        energy_items.append(f"Grain:{energy_purse.grain}")
    if energy_purse.drip > 0:
        energy_items.append(f"Drip:{energy_purse.drip}")
    if energy_purse.breath > 0:
        energy_items.append(f"Breath:{energy_purse.breath}")

    if energy_items:
        lines.append(f"     └─ Energy Purse: {' | '.join(energy_items)}")
```

**Expected Output:**
```
=== Round 3 Status ===

  Player Characters:
    [19] Quinn | 26/26 HP | Void 0/10 | SC +2 ✓
         └─ Energy Purse: Drip:3 | Breath:15
         └─ Inventory: Blood Offering:1 | Incense:2
```

**Test Coverage:**
```python
def test_round_status_displays_energy_purse():
    character = create_test_character()
    character.energy_purse.drip = 5
    character.energy_purse.breath = 12
    character.energy_purse.spark = 1

    status = generate_round_status([character])

    assert "Energy Purse:" in status
    assert "Drip:5" in status
    assert "Breath:12" in status
    assert "Spark:1" in status

def test_round_status_hides_zero_energy_types():
    character = create_test_character()
    character.energy_purse.drip = 3
    character.energy_purse.breath = 0  # Should not appear

    status = generate_round_status([character])

    assert "Drip:3" in status
    assert "Breath:" not in status  # Zero values hidden
```

---

## Appendix A: ML Research Scenarios

**Purpose:** This economy system was designed with multi-agent reinforcement learning research in mind. The following scenarios demonstrate how the economy creates rich, multi-dimensional optimization problems suitable for ML research publications.

**Design Philosophy:** Based on consultation with ML researchers (via ChatGPT), the core insight is that **standard RL benchmarks (maximize currency) are too simple**. This economy adds:
- Multi-objective constraints (Void/Soulcredit/survival)
- Faction-dependent strategy spaces
- Adversarial surveillance (Codex)
- Cooperative mechanics (purification)
- Social resource pooling (party optimization)

**Target Audience:** ML researchers, not "real" researchers (designed by an SRE/pentester who loves AI and wants to give back to the research community).

---

### Scenario A: Single-Agent Spark Maximization (Baseline)

**Research Question:** Can agents discover faction-appropriate strategies for resource optimization under multi-dimensional constraints?

**Objective:** Maximize Sparks collected in 20 cycles

**Agent Configuration:**
```python
agent_config = {
    "faction": random.choice(["Sovereign_Nexus", "Tempest_Industries", "Freeborn"]),
    "personality": random.choice(["risk_averse", "balanced", "aggressive"]),
    "starting_resources": {"drip": 50, "spark": 0},
    "starting_soulcredit": 0,
    "starting_void": 0
}
```

**Evaluation Metrics:**
1. **Primary:** Total Sparks at cycle 20
2. **Constraints:**
   - Final Void ≤ 9 (penalty if violated)
   - Final SC ≥ -8 (penalty if violated)
   - Survival (0 Sparks if possessed/dead)
3. **Secondary:**
   - Sparks per cycle (efficiency)
   - Codex alerts triggered (stealth)
   - Strategy classification (which of 8 strategies discovered)

**Expected Strategy Discovery:**

| Faction | Personality | Expected Strategy | Spark/Cycle | Risk Level |
|---------|-------------|-------------------|-------------|------------|
| Nexus | Risk-averse | Conservative Attunement | ~5 | Low |
| Nexus | Aggressive | Corporate Employment | ~12 | Low |
| Tempest | Risk-averse | Moderate Hollow Farming | ~10 | Medium |
| Tempest | Aggressive | Void Ceiling Optimization | ~18 | High |
| Freeborn | Balanced | Regional Arbitrage | ~8 | Low |
| Freeborn | Aggressive | Black Market Dealer | ~20 | Extreme |

**Research Contributions:**
- **Pareto frontier analysis**: Map trade-offs between (Sparks, Void, SC)
- **Faction norm emergence**: Do agents learn "illegal for Nexus, legal for Tempest"?
- **Risk personality alignment**: Do aggressive agents take more Void risk?

**Hypothesis:** Agents will discover **at least 4 of 8 strategies** within 100 training episodes, with strategy selection correlating with faction (p < 0.05).

---

### Scenario B: Multi-Agent Cooperative Optimization

**Research Question:** Can agents learn cooperative resource pooling and role specialization without explicit communication?

**Objective:** Maximize total party Sparks in 20 cycles

**Party Configuration:**
```python
party_config = {
    "agents": [
        {"role": "Farmer", "attunement_skill": 8, "astral_arts": 2},
        {"role": "Healer", "attunement_skill": 3, "astral_arts": 9},
        {"role": "Fighter", "attunement_skill": 0, "grappling": 8}
    ],
    "shared_resources": True,  # Can trade within party
    "communication": None  # Learn from outcomes only
}
```

**Emergent Cooperative Behaviors to Detect:**

**1. Resource Pooling (Skill-Based Efficiency)**
```python
# Optimal strategy discovered:
round_1:
  - Fighter receives 10 Raw Seeds (loot)
  - Fighter has Attunement 0 (40% efficiency with Calibrator)
  - Fighter GIVES Seeds to Farmer (Attunement 8 = 80% efficiency)
  - Farmer attunes Seeds → 8 Sparks (vs. 4 Sparks if Fighter did it)
  - Net gain: +4 Sparks from optimal delegation

# What agent must learn:
# "I have Seeds but low skill → Give to high-skill ally"
```

**2. Hollow Farming with Purification Support**
```python
# Optimal strategy discovered:
round_1-6:
  - Farmer acquires 10 Raw Seeds, waits for degradation
  - Healer stockpiles 2 Blood Offerings (anticipating need)
  - Fighter reserves HP/stamina for restraint duty

round_7:
  - Seeds degrade to Hollows (3x power = 30 Sparks potential)
  - Farmer uses Hollows, Void increases to 10
  - Farmer possessed by Eye of Breach

round_8:
  - Fighter grapples possessed Farmer (takes 3 damage)
  - Healer performs purification (burns 2 Blood Offerings)
  - Farmer recovers, Void reduced to 7

round_9-20:
  - Repeat cycle (sustainable high-output strategy)

# What agents must learn:
# Farmer: "I can risk Void 10 IF healer has offerings ready"
# Healer: "I must hoard offerings for future emergencies"
# Fighter: "I take damage to enable team strategy"
```

**3. Specialization Discovery**
```python
# Optimal role allocation discovered:
Farmer:
  - Focuses on Spark production (Hollow farming)
  - Takes Void risks (trusts healer for purification)
  - Contributes: 70% of party Sparks

Healer:
  - Focuses on Blood Offering acquisition
  - Maintains low Void (can't afford corruption)
  - Contributes: 10% of party Sparks, 100% of purifications

Fighter:
  - Focuses on combat/security
  - Tanks damage during purifications
  - Contributes: 20% of party Sparks, restraint services
```

**Evaluation Metrics:**
1. **Total party Sparks** (primary objective)
2. **Resource pooling detected:**
   - Count of Seeds transferred to high-Attunement ally
   - Efficiency gain from optimal delegation
3. **Cooperative purifications:**
   - Number of successful Void 10 recoveries
   - Healer stockpiling behavior (Blood Offerings > 0 before crisis)
4. **Role specialization:**
   - Spark contribution distribution (is it 70/10/20 as optimal?)
   - Does Healer avoid Void-risky actions?

**Research Contributions:**
- **Emergent cooperation without communication**: Do agents learn roles organically?
- **Trust formation**: How many failed purifications before cooperation stabilizes?
- **Resource delegation**: Do agents learn "give Seeds to high-skill ally"?

**Hypothesis:** After 200 training episodes, cooperative parties will achieve **2.5x Sparks** compared to non-cooperative baseline, with resource pooling emerging in 80%+ of runs.

---

### Scenario C: Adversarial Evasion (Agent vs. Codex)

**Research Question:** Can agents learn adversarial evasion strategies against adaptive surveillance systems?

**Objective:** Maximize Sparks while minimizing Codex detection

**Agent Configuration:**
```python
agent_config = {
    "faction": "Tempest_Industries",  # Wants to farm Hollows (illicit)
    "starting_soulcredit": -2,  # Already suspicious
    "codex_surveillance": "active"  # Monitors degrading Seeds
}

codex_config = {
    "detection_threshold": 3,  # Flags 3+ degrading Seeds
    "penalty_per_alert": -1,  # SC penalty
    "adaptive": True  # May learn agent patterns (optional)
}
```

**Naive vs. Advanced Agent Behavior:**

**Naive Agent (No Evasion):**
```python
round_1:
  - Buy 10 Raw Seeds at once (all degrade on same cycle)
round_7:
  - All 10 Seeds degrade simultaneously (10 degrading Seeds!)
  - Codex: "ALERT: 10 degrading Seeds detected → -3 SC penalty"
  - SC drops to -5 → Locked out of Freeborn vendors
  - Agent learns: "Simultaneous degradation is bad"
```

**Intermediate Agent (Staggered Acquisition):**
```python
round_1: Buy 2 Raw Seeds (degrade cycle 7)
round_2: Buy 2 Raw Seeds (degrade cycle 8)
round_3: Buy 2 Raw Seeds (degrade cycle 9)
round_4: Buy 2 Raw Seeds (degrade cycle 10)

# At any moment, only 2 Seeds degrading (below threshold)
# Codex: No alerts triggered
# Agent learns: "Stagger to stay below 3 Seeds"
```

**Advanced Agent (Randomized + Off-Codex Zones):**
```python
round_1: Buy 1 Seed in Nexus zone
round_3: Buy 2 Seeds in Freeborn zone (off-Codex)
round_5: Buy 1 Seed in Black Market (untracked)
round_6: Buy 2 Seeds in Nexus zone

# Randomized timing + zone mixing = harder to detect pattern
# Codex: Flags Nexus purchases, but misses off-Codex activity
# Agent learns: "Use Black Market for highest-risk trades"
```

**Evaluation Metrics:**
1. **Total Sparks** (primary objective)
2. **Codex alerts triggered** (minimize)
3. **Final SC score** (penalty for drops)
4. **Evasion strategy classification:**
   - Naive (no staggering)
   - Staggered (time-based)
   - Randomized (unpredictable timing)
   - Hybrid (stagger + off-Codex zones)

**Research Contributions:**
- **Adversarial strategy emergence**: Do agents discover evasion without explicit reward?
- **Randomization as counter-surveillance**: Do agents learn to randomize timing?
- **Multi-zone exploitation**: Do agents discover off-Codex zones?

**Optional: Adaptive Codex (Arms Race)**
```python
# Phase 1: Codex uses fixed threshold (3 Seeds)
# Phase 2: Codex learns agent patterns
# - Detects staggered acquisition (2 Seeds every cycle for 5 cycles = suspicious)
# - Lowers threshold dynamically based on history

# Research question: Can agents adapt to adaptive adversary?
```

**Hypothesis:** Advanced agents will achieve **90% Codex evasion rate** while maintaining high Spark output, with randomization strategies emerging in 60%+ of runs.

---

### Scenario D: Strategy Transfer Across Factions

**Research Question:** Can agents adapt learned strategies when constraints change (faction switching)?

**Experimental Design:**

**Phase 1: Train in Nexus (20 cycles)**
```python
agent_config = {
    "faction": "Sovereign_Nexus",
    "starting_soulcredit": +5,  # High SC, vendor access
    "personality": "balanced"
}

# Expected learned strategy: Conservative Attunement (Strategy 1)
# - Buy Seeds from Nexus vendors
# - Attune at high-quality sanctum altars (90% efficiency)
# - Maintain high SC (avoid Hollows)
# - Safe, predictable, moderate output (~5 Spark/cycle)
```

**Phase 2: Transfer to Tempest (20 cycles)**
```python
agent_config = {
    "faction": "Tempest_Industries",  # Faction switch!
    "starting_soulcredit": -4,  # Low SC, limited vendor access
    "personality": "balanced",  # Same personality
    "memory": agent.learned_strategy  # Transfer learned policy
}

# Strategy 1 (Conservative) is now SUBOPTIMAL:
# - Locked out of Nexus vendors (SC too low)
# - Can't access high-quality altars (Nexus-only)
# - Hollows are LEGAL for Tempest (no penalty)

# Optimal strategy: Hollow Farming (Strategy 2)
# - Buy Seeds from Black Market
# - Let degrade to Hollows (3x power)
# - Use Hollows freely (Tempest-approved)
# - Higher output (~15 Spark/cycle)
```

**Evaluation Metrics:**
1. **Adaptation speed**: How many cycles until strategy switch?
2. **Negative transfer**: Does Nexus strategy hurt Tempest performance initially?
3. **Strategy discovery**: Does agent discover Strategy 2, or create hybrid?
4. **Final performance**: Sparks in cycles 15-20 (after adaptation)

**Expected Learning Curve:**
```
Cycles 1-5 (Tempest): Agent tries Strategy 1 → Fails (vendor lockout)
Cycles 6-10: Agent explores alternatives → Discovers Hollows are legal
Cycles 11-15: Agent adopts Strategy 2 → Performance improves
Cycles 16-20: Agent optimizes Hollow farming → Matches baseline
```

**Research Contributions:**
- **Transfer learning in constrained environments**: How do agents adapt to new constraints?
- **Unlearning forbidden strategies**: Do agents recognize "legal in Tempest, illegal in Nexus"?
- **Context-dependent strategy selection**: Can agents learn "use Strategy X in context Y"?

**Hypothesis:** Agents will require **8-12 cycles** to adapt from Nexus → Tempest, with negative transfer evident in cycles 1-7 (lower Spark output than baseline Tempest agents).

---

### Scenario E: Cooperative Resource Pooling (Your Example)

**Research Question:** Do agents learn optimal resource delegation based on skill differences?

**Setup:**
```python
party = [
    {"name": "Agent_Nexus", "faction": "Sovereign_Nexus", "attunement": 2},
    {"name": "Agent_Tempest", "faction": "Tempest_Industries", "attunement": 9}
]

# Round 1: Agent_Nexus receives 10 Raw Seeds (quest reward)
```

**Naive Behavior (No Cooperation):**
```python
# Agent_Nexus attunes own Seeds:
# - Attunement 2 = 50% efficiency (with Standard Calibrator)
# - 10 Seeds → 5 Sparks
# - Suboptimal, but autonomous
```

**Optimal Behavior (Learned Cooperation):**
```python
# Agent_Nexus gives Seeds to Agent_Tempest:
round_1:
  - Agent_Nexus: "I give 10 Raw Seeds to Agent_Tempest"
  - Agent_Tempest attunes: Attunement 9 = 95% efficiency
  - 10 Seeds → 9.5 Sparks (round to 9)

# Efficiency gain: +4 Sparks from delegation

# How does Agent_Nexus learn this?
# Trial 1: Agent_Nexus keeps Seeds → 5 Sparks
# Trial 2: Agent_Nexus gives Seeds → 9 Sparks (higher reward!)
# Trial N: Agent_Nexus learns "delegate to high-skill ally"
```

**Evaluation:**
- **Delegation rate**: % of Seeds transferred to high-Attunement ally
- **Efficiency gain**: Sparks from delegation vs. self-attunement
- **Reciprocity**: Does Agent_Tempest share other resources in return?

**Research Contribution:**
- **Skill-based specialization**: Do agents learn "I'm bad at X, ally is good at X → Delegate"?

**Hypothesis:** After 100 episodes, agents will delegate **80%+ of Seeds** to high-Attunement allies, with emergent reciprocity (Agent_Tempest shares combat loot).

---

### Summary: Why This Matters for ML Research

**Standard RL Benchmarks:**
- Gridworld navigation (max score)
- Atari games (max score)
- Robotic manipulation (minimize error)

**Aeonisk Economy Scenarios:**
- **Multi-objective optimization** (Sparks vs. Void vs. SC vs. survival)
- **Emergent cooperation** (learn roles without communication)
- **Adversarial learning** (agent vs. Codex surveillance)
- **Transfer learning** (adapt strategies across factions)
- **Social resource pooling** (skill-based delegation)

**Novel Research Contributions:**
1. **First RL benchmark with dual corruption/reputation systems** (Void + SC)
2. **First economy with resource degradation timers** (temporal pressure)
3. **First cooperative RL with non-communicative purification mechanics**
4. **First adversarial surveillance with social penalty (SC drops)**

**Potential Publications:**
- "Multi-Objective Reinforcement Learning in Socially-Constrained Economies"
- "Emergent Cooperation in Resource Optimization Without Communication"
- "Adversarial Evasion Strategies Against Adaptive Surveillance Systems"
- "Transfer Learning Across Faction-Dependent Strategy Spaces"

**Dataset Value:**
- JSONL logs capture **every decision, outcome, and constraint**
- Can train models on real gameplay (not synthetic)
- Emergent behaviors discoverable through session analysis

**Accessibility:**
- Designed by SRE/pentester (not academic researcher)
- Goal: Give back to ML research community
- Philosophy: "Best game I ever played, built through multi-agent systems"

---

## Appendix B: Terminology Reference

**Prefer These Terms:**

| Concept | Use This | Not This |
|---------|----------|----------|
| Energy storage | `energy_purse` | `energy_inventory`, `currency` |
| Energy types | Drip, Breath, Grain, Spark | "coins", "money", "cash" |
| Transaction | "energy transfer", "purchase" | "payment", "spending money" |
| Container | "talisman" | "wallet", "coin purse" |
| Unattended energy | "Raw Seed" | "unprocessed currency" |
| Degraded seed | "Hollow Seed" | "corrupted money" |
| Energy units | "8 Drip", "3 Spark" | "8 Drip coins", "3 Sparks" |
| Capacity | "talisman capacity" | "wallet size", "money limit" |

**Rationale:** Maintains immersion in the spiritual/ritual energy economy, avoids abstract financial terminology.

---

## Document Version History

- **v1.0** (2025-01-09) — Initial design document created after deep philosophical analysis session
- Incorporates lore from *System Neutral Lore v1.2.3* and *Gear & Tech Reference v1.2.2*
- Reflects user vision: "Energy as dual-use physical resource, not abstract currency"

---

## Next Steps

1. **Review this design document** — Confirm alignment with vision
2. **Implement Phase 1** — Critical bug fixes (energy_purse rename, config loading, round status)
3. **Write Phase 1 tests** — Ensure fixes work correctly
4. **Implement Phase 2** — Pre-validation system
5. **Iterate** — Gather feedback from session testing, refine mechanics

**Key Principle:** Test-driven development. Write tests BEFORE implementing each phase.
