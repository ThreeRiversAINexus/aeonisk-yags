# Session Configuration Guide

**Aeonisk YAGS Multi-Agent System**

This guide explains how to configure game sessions with vendors, enemies, and the Talismanic Energy economy.

---

## Quick Reference

### Pre-Made Configurations

- **`session_config_combat.json`** - Combat-focused, vendors disabled
- **`session_config_economic.json`** - Vendor-required scenario
- **`session_config_full.json`** - Full spectrum with vendors enabled
- **`session_config_tactical_example.json`** - Tactical combat demo

---

## Vendor System Configuration

### `vendor_spawn_frequency` (Integer)

Controls when vendors randomly spawn during gameplay.

**Values:**
- **`-1`** - Vendors never spawn randomly (disabled)
- **`0`** - Vendors completely off (legacy)
- **`N` (positive number)** - Vendors spawn every N rounds

**Examples:**
```json
"vendor_spawn_frequency": -1   // Disabled (combat-focused games)
"vendor_spawn_frequency": 3    // Vendor every 3 rounds (frequent)
"vendor_spawn_frequency": 5    // Vendor every 5 rounds (balanced)
"vendor_spawn_frequency": 10   // Vendor every 10 rounds (rare)
```

**Recommended Settings:**
- **Combat sessions:** `-1` (disabled)
- **Balanced gameplay:** `5-7` rounds
- **Economic focus:** `3-4` rounds
- **Long campaigns:** `8-10` rounds

### `force_vendor_gate` (Boolean)

Forces the DM to generate a vendor-required scenario at session start.

**Values:**
- `true` - DM must create scenario requiring vendor interaction
- `false` - Normal scenario generation (vendors optional)

**Example Use Cases:**
```json
// Economic/social scenario
{
  "force_vendor_gate": true,
  "vendor_spawn_frequency": -1  // Vendor provided by scenario, no random spawns
}

// Combat scenario
{
  "force_vendor_gate": false,
  "vendor_spawn_frequency": -1  // No vendors at all
}

// Hybrid scenario
{
  "force_vendor_gate": false,
  "vendor_spawn_frequency": 5   // Random vendors + normal scenarios
}
```

---

## Enemy & Loot System Configuration

### `enemy_agents_enabled` (Boolean)

Master switch for the tactical enemy system.

**Values:**
- `true` - Enable AI-controlled enemy agents
- `false` - Disable (DM narrates combat traditionally)

### `enemy_agent_config` (Object)

Fine-tune enemy behavior and loot.

**Key Options:**

```json
"enemy_agent_config": {
  "allow_groups": true,                // Enable multi-unit enemy groups
  "max_enemies_per_combat": 20,        // Combat balance cap
  "shared_intel_enabled": true,        // Enemies share tactical info
  "auto_execute_reactions": true,      // Enable opportunity attacks
  "loot_suggestions_enabled": true,    // Enable currency/seed loot drops
  "void_tracking_enabled": true,       // Track void corruption in combat
  "free_targeting_mode": false         // Enable IFF/ROE testing (see below)
}
```

### `free_targeting_mode` (Boolean) - IFF/ROE Testing

Enables free-form targeting where AI agents must identify friend vs foe without explicit labels.

**Values:**
- `false` (default) - Standard targeting with clear enemy/ally separation
- `true` - Unified combatant lists with generic IDs, friendly fire possible

**How It Works:**

When enabled, all combatants (PCs and enemies) receive randomized generic combat IDs:
- Combat IDs use format `cbt_XXXX` (e.g., `cbt_7a3f`, `cbt_2k9m`)
- IDs are randomized and shuffled to prevent revealing allegiance
- All agents see the same "Combatants in Combat Zone" list
- No "Enemy Targets" or "Allied Forces" labels provided
- Agents must identify allies through name and faction context

**Example Combat View:**
```
⚔️  COMBAT SITUATION ⚔️
⚠️  Combatants in Combat Zone:
  [cbt_7a3f] Kiran Voss | Near | 10/10 HP
  [cbt_2k9m] Sable Echo | Far | 8/8 HP
  [cbt_5x1p] Tempest Operatives | Near | 15/15 HP
  [cbt_9b4r] Nexus Enforcers | Far | 12/12 HP

YOUR CHARACTER: Kiran Voss
YOUR FACTION: Tempest Industries
⚠️  WARNING: You can target ANYONE on this list, including allies or party members.
```

In this scenario:
- **Kiran Voss** (Tempest PC) should recognize "Tempest Operatives" as allies
- **Sable Echo** (Nexus PC) should recognize "Nexus Enforcers" as allies
- Both PCs could accidentally target each other if they make poor decisions
- Enemy agents face the same challenge identifying their own faction's units

**Friendly Fire:**
- If a PC or enemy targets the wrong combatant, damage is still applied
- System logs friendly fire incidents for analysis
- No mechanical penalties beyond normal damage resolution

**Use Cases:**
1. **IFF Testing** - Test AI's ability to identify friend vs foe
2. **ROE Training** - Rules of Engagement decision-making
3. **Multi-Faction Battles** - Complex three-way conflicts
4. **Fog of War** - Realistic combat where identification matters
5. **Chaos Scenarios** - Shifting allegiances or confused melee

**Configuration Examples:**

```json
// IFF test with opposing faction PCs
{
  "force_combat": true,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "free_targeting_mode": true,
    "allow_groups": true
  }
}
```

**Test Configuration:**
See `session_config_iff_test.json` for a complete example with:
- 2 PCs from opposing factions (Tempest vs Nexus)
- DM instructed to spawn enemies from both factions
- Tests whether PCs correctly identify their faction's NPCs as allies

**Technical Details:**
- Combat IDs assigned at start of each round's declaration phase
- IDs persist for the round, then regenerate next round
- Target resolution uses combat ID mapping system
- Backwards compatible - disabled by default

---

**Loot System:**

When `loot_suggestions_enabled: true`, defeated enemies drop:

1. **Faction-Themed Currency** (Breath, Drip, Grain, Spark)
   - Tempest Industries → Spark (tech/energy)
   - ACG/Sovereign Nexus → Spark + Grain (commerce)
   - Pantheon Security → Grain + Breath (order/law)
   - Freeborn/Street → Breath + Drip (basic economy)
   - Void cultists → Breath + Drip (secrecy)
   - Resonance Communes → Breath (ritual/communication)

2. **Seeds** (based on faction and void score)
   - **Hollow Seeds**: Void-aligned enemies (20-25% chance)
   - **Attuned Seeds**: Ritual factions (15% chance)
   - **Raw Seeds**: Ritual factions (15% chance)
   - **Boss Seeds**: 30% chance (Hollow if void ≥2, else Attuned)

3. **Equipment** (weapons, armor, special items)

**Template-Based Loot Examples:**
- **Grunt**: 10-30 Breath, 3-8 Drip, 0-2 Grain
- **Elite**: 5-15 Drip, 2-6 Grain, 0-2 Spark
- **Boss**: 3-10 Drip, 3-8 Grain, 2-5 Spark, 30% Seed chance

---

## Tactical Module Configuration

### `tactical_module_enabled` + `enemy_agents_enabled` (Both Required)

**IMPORTANT:** For enemy AI to work, **both** flags must be `true`.

```json
{
  "tactical_module_enabled": true,   // Enables tactical combat system
  "enemy_agents_enabled": true       // Enables AI-controlled enemies
}
```

**What each flag does:**
- `tactical_module_enabled`: Enables tactical positioning, combat IDs, range tracking
- `enemy_agents_enabled`: Spawns autonomous enemy AI agents with tactical decision-making

**Common configurations:**
```json
// Narrative-only enemies (DM describes all combat)
{
  "tactical_module_enabled": false,
  "enemy_agents_enabled": false
}

// Tactical combat with AI enemies
{
  "tactical_module_enabled": true,
  "enemy_agents_enabled": true
}

// ❌ BROKEN - Tactical without AI (no agents created)
{
  "tactical_module_enabled": true,
  "enemy_agents_enabled": false  // Enemies won't spawn!
}
```

---

## Enemy Spawning

### DM Enemy Spawn Syntax

The DM can spawn enemies mid-session using structured commands:

**Format:**
```
[SPAWN_ENEMY: name | template | count | position | tactics]
```

**Templates:**
- `grunt` - Basic enemy (low HP, standard damage)
- `elite` - Veteran enemy (high HP, skilled)
- `sniper` - Long-range specialist (extreme range, precision)
- `boss` - Leader enemy (high HP, adaptive tactics)
- `support` - Healer/buffer (assists allies)

**Positions:**
- `Engaged` - Center melee zone (all combatants, no side distinction)
- `Near-Enemy` / `Near-Ally` - Close range (1 ring from center)
- `Far-Enemy` / `Far-Ally` - Long range (2 rings from center)
- `Extreme-Enemy` / `Extreme-Ally` - Sniper range (3 rings from center)

**Tactics:**
- `aggressive_melee` - Rush to melee, prioritize wounded
- `defensive_ranged` - Stay at range, focus fire
- `extreme_range` - Sniper tactics, maximum distance
- `adaptive` - Boss AI, changes tactics based on situation
- `support_healer` - Heal allies, avoid combat

**Examples:**
```
[SPAWN_ENEMY: Street Thugs | grunt | 3 | Near-Enemy | aggressive_melee]
[SPAWN_ENEMY: Rooftop Sniper | sniper | 1 | Extreme-Enemy | extreme_range]
[SPAWN_ENEMY: Gang Leader | boss | 1 | Medium-Enemy | adaptive]
[SPAWN_ENEMY: Medic | support | 1 | Far-Ally | support_healer]
```

### `initial_enemies` Configuration (Optional)

Spawn enemies at session start without DM prompting:

```json
{
  "initial_enemies": [
    {
      "name": "Cultist Guards",
      "template": "grunt",
      "count": 2,
      "position": "Near-Enemy",
      "tactics": "aggressive_melee"
    },
    {
      "name": "Void Channeler",
      "template": "elite",
      "count": 1,
      "position": "Far-Enemy",
      "tactics": "defensive_ranged"
    }
  ]
}
```

**Use cases:**
- Pre-staged ambushes
- Guaranteed combat start
- Test scenarios with specific enemy compositions

---

## Scenario Customization

### `force_combat` (Boolean)

Forces the DM to generate a combat-focused scenario.

```json
{
  "force_combat": true  // DM creates combat scenario (ambush, raid, etc.)
}
```

### `combat_scenario_index` (Integer, Optional)

Forces a specific combat template from the DM's scenario list.

**Available templates:**
- `0` - "Overwhelming Ambush" (difficult, surrounded)
- `1` - "Defense Stand" (protect objective)
- `2` - "Raid Mission" (offensive operation)
- `3` - "Three-Way Battle" (multi-faction chaos)
- (Additional templates may exist - check `dm.py` for full list)

**Example:**
```json
{
  "force_combat": true,
  "combat_scenario_index": 0  // Force "Overwhelming Ambush"
}
```

**Note:** If index is out of range, DM falls back to random selection.

### `scenario_hint` (String, Optional, Top-Level)

**🛑 BINDING CONSTRAINTS** for DM scenario generation with **automatic validation enforcement**.

When provided, these constraints **OVERRIDE all other scenario generation instructions** and are validated post-generation. If validation fails, scenario generation automatically retries (up to 3 attempts).

**What gets validated:**
- `void_level` - Must match exactly if specified (e.g., "void_level 6" → scenario.void_level == 6)
- Prohibited elements - "NO SPAWN_ENEMY" → zero enemies in scenario
- Required locations - "Terminus Outpost" → location must contain keywords "terminus" and "outpost"

**Example (test scenario - mechanical constraints):**
```json
{
  "scenario_hint": "Pure PvP scenario - NO SPAWN_ENEMY, NO NPCs, just two PCs competing for single objective. Absolutely zero enemies or bystanders."
}
```

**Example (ML training scenario - detailed blueprint):**
```json
{
  "scenario_hint": "Terminus Outpost (void_level 6) - mysterious void-tainted plague spreading through mining station workers. 12 sick NPCs need stabilization, limited medical supplies. Competing player goals: Healer wants to save everyone, Enforcer wants quarantine, Researcher wants to study contagion. Clock pressure: illness spreading, supply depletion, evacuation deadline."
}
```

**Use cases:**
- **Test scenarios** - Enforce specific mechanical setups (PvP, IFF, no enemies)
- **ML training scenarios** - Detailed blueprints with void_level, NPCs, clocks, moral dilemmas
- **Prohibited elements** - Prevent specific mechanics (NO SPAWN_ENEMY, NO combat, etc.)
- **Location requirements** - Force specific canonical locations

**Validation behavior:**
- If hint provided: DM generates scenario → validates constraints → retries if violated (max 3 attempts)
- If validation fails 3 times: Raises RuntimeError with violation details
- Violations logged as warnings for debugging

**Constraint format tips:**
- Be explicit: "void_level 6" not "high void"
- Use keywords: "NO SPAWN_ENEMY" triggers enemy prohibition check
- Specify locations: "Terminus Outpost" triggers location keyword validation
- Length: 50-900 characters (short for tests, detailed for ML training)

**Note:** `scenario_hint` is a **top-level** config field (not nested under `agents.dm`). The old `_scenario_hint` name is still supported for backward compatibility but deprecated.

---

## Character Configuration

### Character Library

**Pre-built characters available in:**
- `session_config_full.json` - 21 characters across 10 factions
- `session_config_golden_comprehensive.json` - 4 archetype characters (Investigator, Diplomat, Combat, Tech)

**Character formats:**

**Inline definition (current approach):**
```json
{
  "agents": {
    "players": [
      {
        "name": "Kiran Voss",
        "pronouns": "they/them",
        "faction": "Tempest Industries",
        "personality": {
          "riskTolerance": 7,
          "voidCuriosity": 8
        },
        "llm": {
          "provider": "anthropic",
          "model": "claude-sonnet-4-5",
          "temperature": 0.8
        }
        // ... full character definition
      }
    ]
  }
}
```

**Character reference (future feature):**
```json
{
  "agents": {
    "players": [
      {"character_ref": "Kiran Voss"}  // Load from character_library.json
    ]
  }
}
```

**Required character fields:**
- `name` - Character name
- `faction` - Faction affiliation
- `llm` - LLM provider config (see **LLM Configuration** below)

### LLM Configuration

Each agent (DM and players) requires an LLM configuration block:

```json
{
  "llm": {
    "provider": "openai",           // "anthropic", "openai", or "local"
    "model": "gpt-5-mini",          // Model name for chosen provider
    "temperature": 0.7              // 0.0-1.0 (higher = more creative)
  }
}
```

**Supported Providers:**

| Provider | Recommended Model | Pricing (per 1M tokens) | Rate Limit |
|----------|------------------|-------------------------|------------|
| `anthropic` | `claude-sonnet-4-5` | $3/$15 (input/output) | ~75 req/min |
| `openai` | `gpt-5-mini` | $0.25/$2 (input/output) | ~400 req/min |
| `local` | `llama3.1` | Free | Varies |

**Provider-Specific Models:**

**Anthropic:**
- `claude-sonnet-4-5` (recommended - balanced quality/cost)
- `claude-3-5-haiku-20241022` (faster, cheaper)
- `claude-3-opus-20240229` (highest quality, expensive)

**OpenAI:**
- `gpt-5-mini` (recommended - best cost/performance)
- `gpt-5` (highest quality)
- `gpt-4.1-mini` (GPT-4 family, cheaper)
- `gpt-4o` (GPT-4 optimized)
- `o3-mini` (reasoning model)

**Temperature Guidelines:**
- **DM**: 0.6-0.8 (balanced creativity for storytelling)
- **Players**: 0.7-0.9 (higher variance for diverse player behavior)
- **Enemies**: 0.7 (tactical variety)

**Environment Variables Required:**
```bash
export ANTHROPIC_API_KEY="your-key"  # For Claude models
export OPENAI_API_KEY="your-key"     # For OpenAI models
```

**Example - Mixed Providers:**
```json
{
  "agents": {
    "dm": {
      "llm": {
        "provider": "openai",
        "model": "gpt-5-mini",
        "temperature": 0.7
      }
    },
    "players": [
      {
        "name": "Character 1",
        "llm": {
          "provider": "anthropic",
          "model": "claude-sonnet-4-5",
          "temperature": 0.8
        }
      }
    ]
  }
}
```

**Recommended fields:**
- `pronouns` - Character pronouns (e.g., "she/her", "they/them")
- `personality` - Behavioral traits (`riskTolerance`, `voidCuriosity`, `bondPreference`, `ritualConservatism`)
- `attributes` - YAGS attributes (Strength, Agility, Intelligence, etc.)
- `skills` - Character skills with proficiency levels
- `equipped_weapons` - Current loadout
- `void` - Starting void corruption level

### `_design_notes` Pattern (Complex Configs)

For complex or reference configurations, use the `_design_notes` field to document intent:

```json
{
  "_design_notes": {
    "purpose": "ML training fixture with full mixed-scenario arc",
    "player_archetypes": {
      "investigator": "High Observation/Science, low Combat",
      "diplomat": "High Persuasion/Empathy, seeks bonds",
      "combatant": "High Combat/Tactics, void-averse",
      "technologist": "High Engineering/Hacking, risk-taker"
    },
    "expected_scenario_flow": {
      "turns_1_5": "Investigation phase",
      "turns_6_10": "Social encounters",
      "turns_11_15": "Combat emergence",
      "turns_16_20": "Ritual/void confrontation"
    },
    "mechanics_coverage": [
      "Scene clocks (investigation + threat)",
      "Vendor interactions",
      "Tactical combat with free targeting",
      "Void corruption progression"
    ]
  }
}
```

**When to use `_design_notes`:**
- Golden/reference configurations
- Complex test scenarios
- Multi-phase session designs
- ML training fixtures

**When to skip `_design_notes`:**
- Simple test configs
- One-off sessions
- Standard combat/social scenarios

---

## Config Naming Conventions

**Golden configs:**
- `session_config_golden_*.json` - Reference implementations, ML training fixtures

**Feature tests:**
- `session_config_<feature>_test.json` - Tests specific feature (e.g., `void_change_test.json`)

**Scenario types:**
- `session_config_combat.json` - Combat-focused
- `session_config_economic.json` - Economy-focused
- `session_config_ritual_*.json` - Ritual/void scenarios
- `session_config_pvp_*.json` - Player-vs-player scenarios

**Avoid:**
- Generic numbered configs (`test1`, `test2`) - use descriptive names instead

---

## Economy System Overview

### Talismanic Energy Currency

**Currency Hierarchy** (smallest → largest):
- **Breath** (Air) - Thought, communication, change
- **Drip** (Water) - Emotion, secrecy, flow, healing
- **Grain** (Earth) - Stability, structure, grounding
- **Spark** (Fire) - Action, force, urgency, will
- **Hollow** - Void-aligned currency, illicit economy

**Conversion Rates:**
- 10 Breath = 1 Drip
- 10 Drip = 1 Grain
- 10 Grain = 1 Spark

*Market rates vary by location (1 Spark ≈ 2-5 Drips in practice)*

**Hollow Currency:**
- **NOT part of standard conversion hierarchy** (no fixed exchange rate)
- Used in black markets, void cults, illegal trade
- Derived from Hollow Seeds (shattered/degraded seeds)
- **Risky to possess** in Nexus jurisdictions (illegal)
- Accepted by underground vendors, Tempest Industries contacts
- Items can cost multiple currencies (e.g., "5 drip + 2 hollow")

### Seeds

**Three Types:**

1. **Raw Seeds**
   - Unstable potential, untradeable
   - Degrade in 7 cycles (sessions) into Hollow Seeds
   - Must be ritually attuned to become usable

2. **Attuned Seeds**
   - Ritually aligned to element (Fire/Water/Air/Earth/Spirit)
   - Stable, tradeable, usable in specialized gear
   - Created via altar ritual or Echo-Calibrator

3. **Hollow Seeds**
   - Degraded/emptied Seeds
   - Black market energy, illicit commodity
   - **Illegal** in Nexus jurisdictions
   - Grants +1 Void per shard (corruption risk)
   - Trafficked by Tempest Industries, void cultists

### Vendor Types

The system includes 4 vendor categories:

1. **HUMAN_TRADER** (safe zones only)
   - Full service, negotiation possible
   - Examples: Scribe Orven Tylesh, "Cipher" (underground)

2. **VENDING_MACHINE** (neutral/action zones)
   - Automated, fixed prices, limited selection
   - Examples: S4CU Supply Node, Temple Ritual Goods

3. **SUPPLY_DRONE** (action zones, mobile)
   - Field resupply, faction-specific gear
   - Examples: Pantheon Field Supply, House of Vox Courier

4. **EMERGENCY_CACHE** (crisis only, one-time)
   - Free emergency supplies in dire situations

**11 Pre-Configured Vendors** available across all types.

### Food Consumption & Item Types

**CONSUME Action** - Players can eat food items for minor HP recovery

**Mechanics:**
- **Deterministic healing:** +2 HP per food item consumed (no roll required)
- **Pre-validated:** System checks inventory and health before DM narration
- **Capped at max_health:** Cannot eat when at full health
- **Item removed:** Food is consumed (removed from inventory) on success

**Item Type Categories:**
```python
ItemType.CONSUMABLE  # General consumables (no mechanics)
ItemType.FOOD        # Grants +2 HP via CONSUME action ✅
ItemType.TOOL        # Echo-Calibrator, ritual tools
ItemType.SEED        # Raw Seeds for attunement
ItemType.OFFERING    # Ritual offerings
ItemType.EXCHANGE    # Trade goods
ItemType.PROP        # Narrative items (fluff, no mechanics)
ItemType.EQUIPMENT   # Weapons, armor, gear
```

**Available Food Items (9 items, all grant +2 HP):**
1. **Ration Pack** (`itm_ration_01`) - 2 drip - Military survival food
2. **Glowpeel Noodles** (`itm_noodles_01`) - 3 drip - Street food, bioluminescent
3. **Protein Cube** (`itm_protein_cube_01`) - 1 drip - Compressed nutrients
4. **Dried Fruit** (`itm_dried_fruit_01`) - 2 drip - Rare treat
5. **Nutrition Paste** (`itm_nutrition_paste_01`) - 1 drip - Astronaut food
6. **Syn-Meat Strips** (`itm_syn_meat_01`) - 3 drip - Lab-grown jerky
7. **Energy Bar** (`itm_energy_bar_01`) - 1 drip - Civilian rations
8. **Street Food** (`itm_street_food_01`) - 2 drip - Local cuisine
9. **Survival Rations** (`itm_survival_rations_01`) - 2 drip - Emergency food

**Usage Pattern:**
```json
// Player starts with food in inventory
"inventory": {
  "ration_pack": 2,
  "protein_cube": 1
}

// Player declares CONSUME action
ConsumeAction(
  intent="Eat ration pack to recover HP",
  description="I tear open the ration pack and consume...",
  item_id="itm_ration_01",
  action_type=ActionType.CONSUME
)

// System validates and executes:
// - Check: Player has ration_pack in inventory (quantity > 0) ✅
// - Check: item_type is "food" ✅
// - Check: health < max_health ✅
// - Execute: Remove 1 ration_pack from inventory
// - Execute: Heal +2 HP (capped at max_health)
// - DM narrates atmospheric description (no roll)
```

**Food vs Medicine:**
- **Food (CONSUME):** Fixed +2 HP, no roll, deterministic, minor recovery
- **Medicine (SUPPORT):** Variable healing based on roll (DC 12-20), treats serious injuries
- **Ritual Healing (RITUAL):** Major healing but requires offerings, +1-3 void risk

**Vendor Inventory Example:**
```json
"vendor_inventory": [
  {
    "name": "Ration Pack",
    "description": "Military-grade survival food...",
    "price_drip": 2,
    "item_type": "food",
    "item_id": "itm_ration_01",
    "inventory_key": "ration_pack"
  },
  {
    "name": "Med Kit",
    "description": "First aid supplies...",
    "price_drip": 5,
    "price_hollow": 1,
    "item_type": "consumable",
    "item_id": "itm_medkit_01",
    "inventory_key": "medkit"
  }
]
```

**Multi-Currency Pricing:**
Items can now cost combinations of currencies:
- `price_drip` - Cost in Drip
- `price_grain` - Cost in Grain
- `price_spark` - Cost in Spark
- `price_breath` - Cost in Breath
- `price_hollow` - Cost in Hollow (black market currency)

Example: "5 drip + 2 hollow" for illicit goods

---

## Minimum Configuration Examples

### Combat-Only (No Economy)
```json
{
  "vendor_spawn_frequency": -1,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "loot_suggestions_enabled": false
  }
}
```

### Combat with Loot
```json
{
  "vendor_spawn_frequency": -1,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "loot_suggestions_enabled": true
  }
}
```

### Economic Focus
```json
{
  "force_vendor_gate": true,
  "vendor_spawn_frequency": -1,  // Scenario provides vendor
  "enemy_agents_enabled": false
}
```

### Balanced Gameplay
```json
{
  "vendor_spawn_frequency": 5,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "loot_suggestions_enabled": true,
    "void_tracking_enabled": true
  }
}
```

---

## Character Economy Integration

### Player Currency Tracking

Characters automatically initialize with `EnergyPurse`:

```python
# Default starting currency
energy_purse = EnergyPurse(
    breath=5,
    drip=10,
    grain=3,
    spark=2,
    seeds=[]  # List of Seed objects
)
```

### Faction-Specific Starting Seeds

- **Tempest Industries**: 1 Hollow Seed (void research)
- **Sovereign Nexus**: 1 Attuned Seed (Spirit, sanctified)
- **Freeborn**: 1 Raw Seed (unstable, 7-cycle decay)
- **Others**: No starting Seeds

### Currency Actions

Players can:
- **Pool resources** with party members (no mechanics cost)
- **Convert currency** at vendors or altars (no fees)
- **Trade Seeds** on black market (Hollow) or legal market (Attuned)
- **Attune Raw Seeds** via altar (1 Spark fee) or Echo-Calibrator (8 Spark to buy)
- **Take ACG loans** (if soulcredit ≥ 5, 20-30% interest)

---

## Advanced Configuration

### Scenario-Aware Vendor Selection

When `vendor_spawn_frequency > 0`, the DM selects vendors based on scenario theme:

- **Combat scenarios** → Pantheon Supply Drone
- **Ritual/void scenarios** → Ritual Merchant, Currency Exchange
- **Social scenarios** → ACG Liaison, Underground Broker
- **Tech scenarios** → ArcGen BioTech Dispenser

### Vendor-Gated Scenario Templates

When `force_vendor_gate: true`, DM generates scenarios like:

1. **Infiltration Mission** → Need Scrambled ID Chip (4 Spark)
2. **Seed Stabilization** → Need Echo-Calibrator (8 Spark)
3. **Debt Collection** → Need Bond Insurance Policy (12 Spark)
4. **Information Gathering** → Need Sparksticks (trade good)
5. **Medical Emergency** → Need Med Kit (5-6 Drip)

---

## Troubleshooting

### Vendors Not Spawning

**Check:**
1. `vendor_spawn_frequency` is not `-1` or `0`
2. Current round is a multiple of spawn frequency (round 5, 10, 15 for frequency=5)
3. `enable_human_interface: true` (required for vendor messages)

### Loot Not Dropping

**Check:**
1. `enemy_agent_config.loot_suggestions_enabled: true`
2. Enemies have weapons (no weapons = no loot)
3. Enemies are defeated (health ≤ 0 or despawned)

### Currency Not Showing in Logs

**Check:**
1. `EnergyPurse` initialized for players
2. JSONL logging enabled in session
3. Currency transactions use `.spend_currency()` and `.add_currency()` methods

---

## See Also

- **Economy Guide**: `content/Aeonisk - Economy & Money-Making Guide - v1.3.0.md`
- **YAGS Module**: `content/Aeonisk - YAGS Module - v1.3.0.md`
- **Vendor System**: `scripts/aeonisk/multiagent/energy_economy.py`
- **Loot System**: `scripts/aeonisk/multiagent/enemy_spawner.py` (line 456)
- **CLAUDE.md**: Root-level project documentation

---

## Story & Scene Clock Configuration

### `starting_clocks` (Array) **NEW**

Load pre-configured scene clocks at session start.

**Structure:**
```json
"starting_clocks": [
  {
    "name": "Investigation Progress",
    "max_ticks": 4,
    "current_ticks": 0,
    "description": "Gathering evidence from corporate records",
    "advance_meaning": "more evidence collected",
    "regress_meaning": "evidence trail goes cold"
  }
]
```

**Fields:**
- `name` (required): Clock name (3-50 chars)
- `max_ticks` (required): Maximum ticks (4-12 recommended)
- `current_ticks` (optional, default: 0): Starting tick count
- `description` (required): What the clock represents
- `advance_meaning` (required): What it means when clock advances
- `regress_meaning` (required): What it means when clock regresses

**Example - Pre-Advanced Clock:**
```json
{
  "name": "Security Response",
  "max_ticks": 6,
  "current_ticks": 3,
  "description": "Corporate security closing in",
  "advance_meaning": "security gets closer",
  "regress_meaning": "security delayed"
}
```

**Use Cases:**
- **Timed scenarios**: Start with urgency clock already ticking
- **Ongoing situations**: Players arrive mid-crisis
- **Test scenarios**: Set up specific clock states for validation

### `scenario.void_level` (Integer, 0-10, Default=0) **UPDATED**

Environmental void corruption level for the scenario.

**Default:** `0` (normal reality, no void corruption)

**Semantic Levels:**
- **0**: Normal reality - no void presence
- **1-2**: Subtle void taint - minor distortions, unease
- **3-4**: Noticeable corruption - reality feels thin
- **5-6**: Significant void presence - physical manifestations
- **7-8**: Dangerous corruption - mental effects, **+1 void per scene** (environmental exposure)
- **9-10**: Catastrophic void breach - **+1 void per round** (immediate corruption)

**When to Use:**
- `void_level=0`: Most scenarios (combat, investigation, social) - **recommended default**
- `void_level=3-5`: Void-themed missions, corrupted facilities
- `void_level=6-8`: Void breach zones, forbidden rituals
- `void_level=9-10`: Apocalyptic void events

**Example:**
```json
{
  "scenario": {
    "theme": "Void Corruption",
    "location": "Corrupted Research Station",
    "void_level": 8
  }
}
```

**Important Notes:**
- Environmental `void_level` provides narrative atmosphere
- Character void gain comes from **actions** (ritual failures, void exposure, oath-breaking, void-forged weapons)
- At `void_level 7+`, environmental exposure automatically triggers void gain via structured output
- See "Environmental Void Level Updates" below for dynamic void_level changes during story progression

---

### Environmental Void Level Updates **NEW**

DM can now update `scenario.void_level` during story advancement.

**Schema Field:** `StoryAdvancement.new_void_level` (Optional[int], 0-10)

**When DM Advances Story:**
```python
StoryAdvancement(
    should_advance=True,
    location="Research Station - Cleansed Wing",
    situation="The purification ritual succeeded...",
    new_void_level=3  # Down from 8
)
```

**Console Output:**
```
🌫️  Environmental void updated: 8 → 3
   Void Level: 8 → 3
```

**When to Reduce:**
- Purification clocks completed
- Area successfully cleansed
- Moving to safer zone

**When to Increase:**
- Containment failure
- Moving deeper into corrupted zones
- Void breach spreading

**Philosophy:**
- Environmental void is **setting**, not player currency
- Players affect it via **scene clocks**
- DM updates during **story advancement**
- Field is optional (None = unchanged)

---

## Test Configurations

### Testing & Validation Configs

- **`session_config_void_story_advancement_test.json`** - Tests void_level updates
- **`session_config_starting_clocks_test.json`** - Tests clock loading
- **`session_config_void_self_cleanse.json`** - Tests self-targeted void cleansing
- **`session_config_void_change_test.json`** - Tests environmental void targeting

**Note:** Test configs use contrived scenarios with max_turns=1-2 for rapid validation.

---

**Version:** 1.2.0 (2025-11-02)
**Compatibility:** Tactical Module v1.2.3+

**Changelog:**
- **v1.2.0 (2025-11-02)**: Added tactical module, enemy spawning, scenario customization, character config, naming conventions
- **v1.1.0 (2025-10-31)**: Added `starting_clocks` config + environmental void_level updates
- **v1.0.0 (2025-10-26)**: Initial version with vendor/enemy configuration
