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

## Economy System Overview

### Talismanic Energy Currency

**Currency Hierarchy** (smallest → largest):
- **Breath** (Air) - Thought, communication, change
- **Drip** (Water) - Emotion, secrecy, flow, healing
- **Grain** (Earth) - Stability, structure, grounding
- **Spark** (Fire) - Action, force, urgency, will

**Conversion Rates:**
- 10 Breath = 1 Drip
- 10 Drip = 1 Grain
- 10 Grain = 1 Spark

*Market rates vary by location (1 Spark ≈ 2-5 Drips in practice)*

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

Characters automatically initialize with `EnergyInventory`:

```python
# Default starting currency
energy_inventory = EnergyInventory(
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
1. `EnergyInventory` initialized for players
2. JSONL logging enabled in session
3. Currency transactions use `.spend_currency()` and `.add_currency()` methods

---

## See Also

- **Economy Guide**: `content/Aeonisk - Economy & Money-Making Guide - v1.2.3.md`
- **YAGS Module**: `content/Aeonisk - YAGS Module - v1.2.2.md`
- **Vendor System**: `scripts/aeonisk/multiagent/energy_economy.py`
- **Loot System**: `scripts/aeonisk/multiagent/enemy_spawner.py` (line 456)
- **CLAUDE.md**: Root-level project documentation

---

**Version:** 1.0.0 (2025-10-26)
**Compatibility:** Tactical Module v1.2.3+
