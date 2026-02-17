# 07: Inventory & Equipment System

**Priority:** P1
**Status:** Proposed
**Branch:** TBD (off `main`)
**Dependencies:** None

---

## Problem Statement

The current inventory and equipment system has four gaps that break mechanical coherence:

1. **PC weapons are narrative-only.** Players load `Weapon` objects from `WEAPON_LIBRARY` on creation (player.py:380-420), and the DM receives a `WEAPON CONTEXT` block with weapon name and damage_type (dm.py:7580-7590). But `base_damage` in `DamageEffect` is generated entirely by the DM LLM as a freeform integer -- it has no relationship to the weapon's actual `damage` stat from `WEAPON_LIBRARY`. Enemy attacks use real weapon stats (enemy_combat.py:1068-1073: `base_damage = strength + weapon.damage + damage_roll`). This asymmetry means PC damage output is arbitrary and varies wildly across LLM providers.

2. **NPCs have no energy purse.** `NPCAgent.energy_purse` is `Optional[EnergyPurse] = None` (npc_agent.py:314). Currency transfers to NPCs silently fail because `transfer_currencies_to()` requires a target `EnergyPurse` instance. NPC creation never initializes a purse, even when the NPC is a vendor who should logically hold currency.

3. **No loot mechanic for fallen enemies.** `suggest_loot()` in enemy_spawner.py:264-440 generates a formatted text string describing weapons, currency, seeds, and special items -- but never adds anything to any inventory. The function is called for logging/narration only. Players cannot mechanically acquire items from defeated enemies.

4. **No formal inter-agent item transfer.** NPCs have a `transfer` action_type (npc_agent.py:367, 400-420) that generates structured output with `transfer_currency` and `transfer_items` fields, but processing stops at DM narration. The transfer is never mechanically executed. Similarly, PC `TransferAction` (player_action.py:520-571) handles currency transfers between PCs but has no path for PC-to-NPC or NPC-to-PC item movement.

### Impact on ML Training Data

The asymmetry between PC and enemy damage resolution produces inconsistent training data:
- Enemy attacks: deterministic formula (Strength + weapon.damage + d20 * 0.85 CBM)
- PC attacks: LLM-generated base_damage with no consistent formula
- Same weapon (e.g., "Pistol", damage=6) produces vastly different base_damage values depending on which agent wields it

---

## Current Implementation

### PC Weapon Loading (player.py:259-420)

```python
# player.py:259-264
self.equipped_weapons = {
    "primary": None,    # Currently equipped primary weapon (Weapon object)
    "sidearm": None,    # Currently equipped sidearm (Weapon object)
}
self.weapon_inventory = []  # List of additional Weapon objects in inventory
```

Weapons are loaded from session config in `on_start()`:

```python
# player.py:384-420
if 'equipped_weapons' in self.character_config or 'carried_weapons' in self.character_config:
    equipped_config = self.character_config.get('equipped_weapons', {})
    carried_config = self.character_config.get('carried_weapons', [])
# ...
if equipped_config.get("primary"):
    self.equipped_weapons["primary"] = get_weapon(equipped_config["primary"])
if equipped_config.get("sidearm"):
    self.equipped_weapons["sidearm"] = get_weapon(equipped_config["sidearm"])
```

The `Weapon` objects are properly loaded with all stats (attack, damage, damage_type, etc.) but only `weapon.name` and `weapon.damage_type` are communicated to the DM for resolution.

### Weapon Context in DM Resolution (dm.py:56-94, 7580-7590)

```python
# dm.py:56-94 (_resolve_weapon_and_damage_type)
def _resolve_weapon_and_damage_type(action: dict, shared_state) -> Tuple[str, str, Optional['Weapon']]:
    """Resolve weapon name and damage type from player's equipped weapons."""
    # Returns (weapon_name, damage_type, weapon_object)
    # The weapon_object is returned but only name and damage_type are used

# dm.py:7580-7590 (weapon context injected into prompt)
weapon_context = (
    f"\n\n**WEAPON CONTEXT:**\n"
    f"Weapon: {weapon_name}\n"
    f"Damage Type: {weapon_damage_type.upper()}\n"
    f"Set damage_type=\"{weapon_damage_type}\" in all DamageEffect fields.\n"
)
# NOTE: weapon.damage stat is NOT included -- DM invents base_damage
```

### Enemy Damage Calculation (enemy_combat.py:1066-1073)

```python
# enemy_combat.py:1066-1073
if hit:
    strength = enemy.attributes.get('Strength', 3)
    damage_roll = random.randint(1, 20)
    base_damage = strength + weapon.damage + damage_roll

    # Combat balance: Reduce enemy damage by 15% to prevent one-shots
    total_damage = int(base_damage * 0.85)
```

This formula is well-defined: `Strength + weapon.damage + d20`, then * 0.85 CBM reduction. PC attacks have no equivalent formula.

### NPC Energy Purse (npc_agent.py:308-314)

```python
# npc_agent.py:308-314
is_vendor: bool = False
vendor_inventory: List = field(default_factory=list)
vendor_greeting: Optional[str] = None
vendor_type: Optional[str] = None
accepts_purchases: bool = False
energy_purse: Optional['EnergyPurse'] = None  # <-- Always None unless explicitly set
```

No code path initializes `energy_purse` during NPC creation. The `deescalate_enemy_to_npc()` conversion (agent_conversion.py) does not create a purse either.

### Loot Generation (enemy_spawner.py:264-440)

```python
# enemy_spawner.py:264-278
def suggest_loot(agent: EnemyAgent) -> str:
    """
    Generate faction-aware loot suggestion for defeated enemy.
    ...
    Returns:
        Loot description string  # <-- String only, not items
    """
```

The function generates a well-structured loot description including:
- Weapons with condition ratings (good/fair/damaged)
- Faction-aware currency drops (Breath/Drip/Grain/Spark) with template-based ranges
- Seed drops (Raw/Attuned/Hollow) based on faction and void_score
- Special items (10% chance: datapads, keycards, talismans)

But returns a formatted string, never calling `add_currency()` or modifying any inventory.

### PC Inventory Model (player.py:76-136)

```python
# player.py:114-133 (CharacterState.inventory default)
if self.inventory is None:
    self.inventory = {
        'blood_offering': 0,
        'incense': 0,
        'neural_stimulant': 0,
        # ... 11 more predefined slots
    }
```

The inventory is a flat `Dict[str, int]` with predefined keys. Adding new item types dynamically (e.g., loot from enemies) works because Python dicts accept arbitrary keys, but there is no item metadata (weight, damage_type, weapon stats) associated with inventory keys.

### Existing Transfer Infrastructure (energy_economy.py:270-308)

```python
# energy_economy.py:270-280
def transfer_currency_to(self, other_inventory: 'EnergyPurse', currency_type: str, amount: int) -> bool:
    """Transfer currency from this inventory to another."""
    if self.spend_currency(currency_type, amount):
        other_inventory.add_currency(currency_type, amount)
        return True
    return False

# energy_economy.py:281-308
def transfer_currencies_to(self, receiver_purse: 'EnergyPurse', currency_amounts: dict[str, int]) -> bool:
    """Transfer multiple currencies from this purse to another."""
    # Pre-validates all amounts, then executes atomically
```

The transfer mechanics exist and work correctly between two `EnergyPurse` instances. The gap is that NPCs lack a purse to receive into.

---

## Design Decisions

These decisions are user-confirmed:

1. **Players meaningfully interact with equipped items** -- weapon stats should drive mechanical outcomes, not LLM improvisation.

2. **Items discoverable in the world** -- search/loot actions should add items to inventory.

3. **NPCs can give and receive items** -- both currency and physical items, mechanically tracked.

4. **Enemy loot upon search** -- formalize the existing `suggest_loot()` output into actual inventory additions.

5. **Offerings unchanged** -- the offering auto-deduct system (CharacterState.consume_offering) works correctly and requires no changes.

---

## Proposed Solution

### Phase 1: NPC Purse Initialization

**Goal:** Every NPC starts with an `EnergyPurse` so currency transfers work.

**Files to modify:**
- `npc_agent.py:319` (__post_init__)
- `agent_conversion.py` (deescalate_enemy_to_npc)

**Implementation:**

```python
# npc_agent.py __post_init__ addition
def __post_init__(self):
    """Initialize LLM client if not provided."""
    # Initialize energy purse if not provided
    if self.energy_purse is None:
        from .energy_economy import EnergyPurse
        self.energy_purse = EnergyPurse(
            breath=0,   # NPCs start empty by default
            drip=0,
            grain=0,
            spark=0,
            seeds=[]
        )

    # Existing LLM client initialization...
    if self.llm_client is None and self.can_act:
        # ...
```

For NPCs converted from enemies, optionally transfer the enemy's loot currency to the NPC purse:

```python
# agent_conversion.py addition
def deescalate_enemy_to_npc(enemy, disposition, current_round, llm_provider=None):
    # ... existing conversion logic ...
    npc = NPCAgent(
        # ... existing fields ...
        energy_purse=EnergyPurse(breath=0, drip=0, grain=0, spark=0),
    )
```

**Backward compatibility:** NPCs that already have `energy_purse=None` will get an empty purse on init. No behavioral change for existing tests.

### Phase 2: PC Weapon Stats Drive base_damage

**Goal:** The DM resolution prompt includes weapon damage stats so `base_damage` is grounded in mechanical reality rather than LLM improvisation.

**Files to modify:**
- `dm.py:7580-7590` (weapon context block)
- `dm.py:56-94` (_resolve_weapon_and_damage_type -- already returns weapon object)

**Implementation:**

Expand the `WEAPON CONTEXT` block to include weapon stats:

```python
# dm.py:7580-7590 (expanded weapon context)
weapon_name, weapon_damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, self.shared_state)
if weapon_name != "Unknown Weapon":
    weapon_context = (
        f"\n\n**WEAPON CONTEXT (MECHANICAL):**\n"
        f"Weapon: {weapon_name}\n"
        f"Damage Type: {weapon_damage_type.upper()}\n"
        f"Weapon Damage Bonus: {weapon_obj.damage if weapon_obj else 'unknown'}\n"
        f"Attack Bonus: {weapon_obj.attack if weapon_obj else 0}\n"
    )
    # Include guidance for base_damage calculation
    if weapon_obj:
        attacker_strength = _get_attacker_strength(action, self.shared_state)
        weapon_context += (
            f"\n**base_damage GUIDANCE:**\n"
            f"Formula: Strength({attacker_strength}) + Weapon Damage({weapon_obj.damage}) + margin_modifier\n"
            f"- Marginal success (margin 0-4): base_damage = {attacker_strength + weapon_obj.damage} (weapon + strength, no bonus)\n"
            f"- Moderate success (margin 5-9): base_damage = {attacker_strength + weapon_obj.damage + 3} (add partial margin)\n"
            f"- Good success (margin 10-14): base_damage = {attacker_strength + weapon_obj.damage + 6}\n"
            f"- Excellent+ (margin 15+): base_damage = {attacker_strength + weapon_obj.damage + 10}\n"
            f"Set damage_type=\"{weapon_damage_type}\" in all DamageEffect fields.\n"
        )
```

Add helper to extract attacker strength:

```python
# dm.py new helper
def _get_attacker_strength(action: dict, shared_state) -> int:
    """Get attacker's Strength attribute for damage calculation."""
    agent_id = action.get('agent_id')
    if not agent_id:
        return 3  # Default human Strength
    for player in getattr(shared_state, 'player_agents', []):
        if hasattr(player, 'agent_id') and player.agent_id == agent_id:
            if hasattr(player, 'character_state'):
                return player.character_state.attributes.get('Strength', 3)
    return 3
```

**Key design choice:** We provide *guidance* to the DM LLM, not enforcement. The DM can still adjust base_damage for narrative reasons (critical hits, environmental factors), but the guidance anchors expectations to weapon stats. This preserves the "DM-authoritative" design principle while eliminating the current problem of completely arbitrary damage.

**Why not enforce mechanically?** The DM LLM resolves damage in `ActionResolution.effects.damage.base_damage` as part of structured output. The system currently trusts this value. Adding hard enforcement (clamp to formula) would:
1. Break the "DM-authoritative resolution" principle
2. Require a separate damage calculation pipeline for PCs (enemy pipeline already exists)
3. Create inconsistency when DM narrates critical hits or environmental effects

The guidance approach is the minimal intervention that solves the asymmetry.

### Phase 3: Loot Tables and Search Mechanic

**Goal:** Formalize `suggest_loot()` to produce structured loot that gets added to player inventory.

**Files to modify:**
- `enemy_spawner.py:264-440` (refactor suggest_loot to return structured data)
- `dm.py` (loot processing after enemy defeat)
- `energy_economy.py` (new `LootResult` dataclass)
- `schemas/player_action.py` (add `SearchAction` or extend `InvestigateAction`)

**Implementation:**

New structured loot result:

```python
# energy_economy.py addition
@dataclass
class LootResult:
    """Structured loot from defeated enemy or container."""
    weapons: List['Weapon']           # Weapon objects (with condition)
    armor: Optional['Armor']          # Armor (if any)
    currency: Dict[str, int]          # {"breath": 15, "drip": 5, ...}
    seeds: List['Seed']               # Seed objects
    special_items: List[str]          # Narrative items (datapads, keycards)
    source_name: str                  # Who/what was looted
    description: str                  # Human-readable summary (existing format)
```

Refactor `suggest_loot()`:

```python
# enemy_spawner.py refactored
def generate_loot(agent: EnemyAgent) -> LootResult:
    """
    Generate structured loot for defeated enemy.

    Returns LootResult with actual item/currency objects (not just text).
    """
    # ... same generation logic as current suggest_loot() ...
    # But instead of building a string, build LootResult

    return LootResult(
        weapons=loot_weapons,
        armor=loot_armor,
        currency={"breath": breath, "drip": drip, "grain": grain, "spark": spark},
        seeds=loot_seeds,
        special_items=special_items_list,
        source_name=agent.name,
        description=f"**Loot from {agent.name}:** {loot_str}"
    )

# Keep suggest_loot() as backward-compatible wrapper
def suggest_loot(agent: EnemyAgent) -> str:
    """Legacy wrapper -- returns text description."""
    result = generate_loot(agent)
    return result.description
```

Search action processing in DM:

```python
# dm.py addition (in resolution processing)
def _process_search_loot(self, agent_id: str, target_enemy_id: str):
    """
    Process a search/loot action on a defeated enemy.

    Generates structured loot and adds to player inventory.
    """
    # Find defeated enemy
    enemy = self._find_defeated_enemy(target_enemy_id)
    if not enemy:
        return None

    loot = generate_loot(enemy)

    # Find player
    player = self._find_player(agent_id)
    if not player:
        return None

    # Add currency to player purse
    for currency_type, amount in loot.currency.items():
        if amount > 0:
            player.character_state.energy_purse.add_currency(currency_type, amount)

    # Add special items to inventory
    for item_name in loot.special_items:
        key = item_name_to_inventory_key(item_name)
        player.character_state.inventory[key] = player.character_state.inventory.get(key, 0) + 1

    return loot
```

### Phase 4: GiveItemAction Schema (Inter-Agent Transfer)

**Goal:** Formal mechanical transfer of items between any agent types.

**Files to modify:**
- `schemas/player_action.py` (add GiveItemAction or extend TransferAction)
- `npc_agent.py` (process transfer actions mechanically)
- `dm.py` (execute transfers during resolution)
- `shared_state.py` (agent lookup for cross-type transfers)

**Implementation:**

The existing `TransferAction` schema already handles the declaration side. The gap is execution. Add transfer execution to the DM resolution pipeline:

```python
# dm.py addition
def _execute_transfer(self, source_agent_id: str, target_name: str,
                       currency_amounts: Optional[Dict[str, int]],
                       item_amounts: Optional[Dict[str, int]]) -> Dict:
    """
    Execute inter-agent transfer (any agent type to any agent type).

    Supports: PC->PC, PC->NPC, NPC->PC, NPC->NPC
    """
    source = self._find_any_agent(source_agent_id)
    target = self._find_any_agent_by_name(target_name)

    if not source or not target:
        return {"success": False, "reason": "agent not found"}

    source_purse = self._get_purse(source)
    target_purse = self._get_purse(target)

    results = {"currency": {}, "items": {}}

    # Currency transfer
    if currency_amounts and source_purse and target_purse:
        success = source_purse.transfer_currencies_to(target_purse, currency_amounts)
        results["currency"] = {"success": success, "amounts": currency_amounts}

    # Item transfer
    if item_amounts:
        source_inv = self._get_inventory(source)
        target_inv = self._get_inventory(target)
        for item_name, count in item_amounts.items():
            key = item_name_to_inventory_key(item_name)
            if source_inv.get(key, 0) >= count:
                source_inv[key] -= count
                target_inv[key] = target_inv.get(key, 0) + count
                results["items"][item_name] = {"success": True, "count": count}
            else:
                results["items"][item_name] = {"success": False, "reason": "insufficient"}

    return results
```

---

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `npc_agent.py:319` | Initialize `energy_purse = EnergyPurse()` in `__post_init__` | 1 |
| `agent_conversion.py` | Pass empty purse during enemy-to-NPC conversion | 1 |
| `dm.py:7580-7590` | Expand WEAPON CONTEXT with damage stats and guidance | 2 |
| `dm.py:56-94` | Already returns weapon object (no change needed) | 2 |
| `dm.py` (new) | `_get_attacker_strength()` helper | 2 |
| `dm.py` (new) | `_process_search_loot()` for search action processing | 3 |
| `enemy_spawner.py:264-440` | Refactor to `generate_loot()` returning `LootResult` | 3 |
| `energy_economy.py` (new) | `LootResult` dataclass | 3 |
| `dm.py` (new) | `_execute_transfer()` for inter-agent transfers | 4 |
| `shared_state.py` | Agent lookup helpers for cross-type transfers | 4 |

---

## Test Plan

### Phase 1: NPC Purse Initialization

```python
# tests/unit/test_npc_purse_init.py

def test_npc_created_with_empty_purse():
    """NPCs should always have an EnergyPurse after creation."""
    npc = NPCAgent(
        agent_id="npc_test",
        name="Test NPC",
        faction="Civilian",
        entity_type="neutral",
        disposition="friendly",
        threat_level="non_combatant",
        description="A test NPC",
        health=20,
        max_health=20,
        soak=6,
        void_score=0,
    )
    assert npc.energy_purse is not None
    assert isinstance(npc.energy_purse, EnergyPurse)
    assert npc.energy_purse.breath == 0
    assert npc.energy_purse.drip == 0

def test_npc_currency_transfer_succeeds():
    """Currency transfer to NPC should work now that purse exists."""
    npc = create_test_npc()
    player_purse = EnergyPurse(drip=10)
    success = player_purse.transfer_currency_to(npc.energy_purse, "drip", 5)
    assert success
    assert npc.energy_purse.drip == 5
    assert player_purse.drip == 5

def test_converted_npc_has_purse():
    """Enemy deescalated to NPC should have an energy purse."""
    enemy = create_test_enemy()
    npc = deescalate_enemy_to_npc(enemy, "wary", current_round=1)
    assert npc.energy_purse is not None

def test_vendor_npc_purse_independent():
    """Vendor NPCs with explicit purse should keep their purse, not get overridden."""
    npc = NPCAgent(
        ...,
        energy_purse=EnergyPurse(drip=100, spark=50),  # Vendor has stock
    )
    assert npc.energy_purse.drip == 100
    assert npc.energy_purse.spark == 50
```

### Phase 2: PC Weapon Stats in DM Resolution

```python
# tests/unit/test_weapon_context_stats.py

def test_weapon_context_includes_damage_stat():
    """WEAPON CONTEXT should include weapon.damage for DM guidance."""
    # Mock player with Pistol (damage=6)
    weapon_context = build_weapon_context(
        action={"action_type": "combat", "skill": "Guns", "agent_id": "player_01"},
        shared_state=mock_shared_state_with_pistol_player(),
    )
    assert "Weapon Damage Bonus: 6" in weapon_context
    assert "Strength(3)" in weapon_context  # Player's Strength

def test_weapon_context_provides_damage_guidance():
    """WEAPON CONTEXT should show base_damage ranges by success tier."""
    weapon_context = build_weapon_context(...)
    assert "Marginal success" in weapon_context
    assert "base_damage = 9" in weapon_context  # Str(3) + Weapon(6)

def test_unarmed_weapon_context():
    """Unarmed attacks should show fists stats (damage=0)."""
    weapon_context = build_weapon_context(
        action={"action_type": "combat", "skill": "Brawl", "agent_id": "player_01"},
        shared_state=mock_shared_state_no_brawl_sidearm(),
    )
    assert "damage_type" in weapon_context.lower()
    assert "STUN" in weapon_context or "stun" in weapon_context
```

### Phase 3: Loot Tables

```python
# tests/unit/test_loot_generation.py

def test_generate_loot_returns_structured_result():
    """generate_loot() should return LootResult, not string."""
    enemy = create_test_enemy(template="grunt")
    loot = generate_loot(enemy)
    assert isinstance(loot, LootResult)
    assert loot.source_name == enemy.name
    assert isinstance(loot.currency, dict)

def test_generate_loot_has_currency():
    """Grunt loot should include breath and drip currency."""
    enemy = create_test_enemy(template="grunt")
    loot = generate_loot(enemy)
    assert loot.currency.get("breath", 0) > 0 or loot.currency.get("drip", 0) > 0

def test_suggest_loot_backward_compatible():
    """Legacy suggest_loot() should still return string."""
    enemy = create_test_enemy(template="elite")
    result = suggest_loot(enemy)
    assert isinstance(result, str)
    assert "Loot from" in result

def test_loot_added_to_player_inventory():
    """Search action should add loot items to player inventory."""
    player = create_test_player()
    enemy = create_defeated_enemy()
    loot = process_search_loot(player.agent_id, enemy.agent_id)
    assert player.character_state.energy_purse.breath > 0 or player.character_state.energy_purse.drip > 0

def test_loot_weapons_added_to_inventory():
    """Looted weapons should appear in player weapon_inventory."""
    # Future: When weapon objects are added to player inventory
    pass
```

### Phase 4: Inter-Agent Transfer

```python
# tests/unit/test_inter_agent_transfer.py

def test_pc_to_npc_currency_transfer():
    """Player should be able to transfer currency to NPC."""
    player = create_test_player(drip=20)
    npc = create_test_npc()
    result = execute_transfer(player.agent_id, npc.name, currency={"drip": 10})
    assert result["currency"]["success"]
    assert npc.energy_purse.drip == 10

def test_npc_to_pc_currency_transfer():
    """NPC should be able to transfer currency to player."""
    npc = create_test_npc_with_currency(drip=15)
    player = create_test_player()
    result = execute_transfer(npc.agent_id, player.character_state.name, currency={"drip": 10})
    assert result["currency"]["success"]

def test_item_transfer_removes_from_source():
    """Transferred items should be removed from source inventory."""
    player = create_test_player(inventory={"med_kit": 2})
    npc = create_test_npc()
    result = execute_transfer(player.agent_id, npc.name, items={"Med Kit": 1})
    assert result["items"]["Med Kit"]["success"]
    assert player.character_state.inventory["med_kit"] == 1

def test_insufficient_items_fail_transfer():
    """Transfer should fail if source lacks items."""
    player = create_test_player(inventory={"med_kit": 0})
    npc = create_test_npc()
    result = execute_transfer(player.agent_id, npc.name, items={"Med Kit": 1})
    assert not result["items"]["Med Kit"]["success"]
```

---

## Dependencies

None. This feature is self-contained within the multi-agent system.

**Interacts with but does not depend on:**
- 08_SUPPRESSION_NONLETHAL (weapon stats feed into suppressive damage guidance)
- Bond System (bond partner item sharing is a future extension)

---

## Open Questions

### Q1: Should PC damage be fully mechanical (like enemies) or guided (DM has discretion)?

**Current recommendation:** Guided. Provide weapon stats and damage formula in the prompt, but let the DM LLM set `base_damage` with discretion for narrative effects (critical hits, environmental factors, etc.). This preserves "DM-authoritative resolution" while anchoring expectations.

**Alternative:** Fully mechanical. Calculate `base_damage = Strength + weapon.damage + margin_modifier` server-side and inject it into `DamageEffect` before the DM generates narration. This would make PC damage deterministic but removes DM narrative flexibility.

**Decision needed before Phase 2 implementation.**

### Q2: Should looted weapons be equippable mid-session?

**Current recommendation:** No, not in v2. Looted weapons go into `weapon_inventory` (carried, not equipped). Weapon swapping mid-combat is a separate feature with its own schema implications (SwapWeaponAction, action economy cost).

### Q3: How should loot be distributed among party members?

**Current recommendation:** The searching player receives all loot. Party loot distribution is handled via `TransferAction` -- the searching player can voluntarily share afterward. This is simpler than a loot distribution system and creates interesting ML training data about cooperation.

### Q4: Should NPC purse start empty or with faction-appropriate currency?

**Current recommendation:** Start empty (Phase 1). Faction-appropriate starting currency can be added later via NPC spawn config (similar to PC `starting_currency`). Vendors already have their own inventory/pricing system that doesn't depend on the purse.

### Q5: What happens to looted weapon condition ("good"/"fair"/"damaged")?

**Current recommendation:** Track as metadata on the weapon object. Add optional `condition: str` field to `Weapon` dataclass. Damaged weapons could have reduced `attack` or `damage` stats. Deferred to a future refinement.

---

## Migration Notes

### Session Config Changes

No session config schema changes required. The `equipped_weapons` and `carried_weapons` config format is unchanged. Phase 2 only changes how weapon stats are communicated to the DM prompt.

### JSONL Logging Impact

Phase 3 (loot) will generate new `item_acquired` events in the JSONL log:

```json
{
    "event_type": "item_acquired",
    "round": 3,
    "data": {
        "character_id": "player_01",
        "character_name": "Kael Dren",
        "source": "Street Gang (defeated)",
        "items": {"beat_up_pistol": 1},
        "currency": {"breath": 22, "drip": 7}
    }
}
```

This is additive -- no existing event types change.

**IMPORTANT:** Update `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` to document
the `item_acquired` event type schema (fields, types, example). Add it to the event type
table and include a full JSON example in the schema reference section.

### Backward Compatibility

- `suggest_loot()` continues to return a string (wrapper around `generate_loot()`)
- NPCs that previously had `energy_purse=None` will silently get an empty purse (no behavioral change for existing code that doesn't touch the purse)
- Weapon context expansion is additive (more info in prompt, no info removed)
- All changes are backward-compatible with existing session configs and test fixtures
