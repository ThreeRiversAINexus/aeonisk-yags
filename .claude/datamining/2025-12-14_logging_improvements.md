# Logging Improvements Recommended

**Date:** 2025-12-14
**Based on:** Datamining analysis of 92 bulk sessions

---

## 1. Roll Modifiers Not Logged (HIGH PRIORITY)

**Problem:** 315 rolls have hidden modifiers (ability + d20 ≠ total) but modifiers aren't logged as structured data.

**Evidence:**
```
Astral Arts: ability 25 + d20 1 = 26, but total is 21 (hidden -5)
Systems: ability 30 + d20 2 = 32, but total is 40 (hidden +8)
```

**Current schema:**
```json
"roll": {
  "ability": 25,
  "d20": 1,
  "total": 21,  // Where did -5 come from?
  "dc": 22
}
```

**Recommended schema:**
```json
"roll": {
  "ability": 25,
  "d20": 1,
  "modifiers": [
    {"source": "void_penalty", "value": -2, "details": {"void_level": 1}},
    {"source": "no_offering", "value": -2},
    {"source": "condition", "value": -1, "details": {"name": "Psychic Strain"}}
  ],
  "modifier_total": -5,
  "total": 21,
  "dc": 22
}
```

**Files to modify:**
- `mechanics.py:log_action_resolution()` - Add modifiers parameter
- `dm.py` - Pass modifiers when calling log_action_resolution
- Wherever roll calculation happens - collect modifiers into array

---

## 2. Combat Defeats Not Logged (HIGH PRIORITY)

**Problem:** When enemies are defeated in combat (HP ≤ 0), no `enemy_defeat` event is generated. Only narrative "departed" defeats are logged.

**Evidence:**
- void_cultist: 86 spawns, 0 defeats logged
- Sample cultist reaches `HP -10, status=defeated` but no defeat event

**Current behavior:** Only `deescalate_enemy_to_npc()` and similar generate defeat events.

**Recommended fix:**
Add defeat event generation when combat reduces enemy HP to 0:

```python
# In combat resolution (mechanics.py or enemy_combat.py)
if defender.health <= 0 and not defeat_logged:
    self.jsonl_logger.log_enemy_defeat(
        round_num=round_num,
        enemy_id=defender.agent_id,
        enemy_name=defender.name,
        defeat_reason="killed",  # vs "fled", "subdued", "departed"
        killer_id=attacker.agent_id,
        killer_name=attacker.name,
        final_damage=damage_dealt
    )
```

**Files to modify:**
- `mechanics.py` - Add `log_enemy_defeat()` method
- `enemy_combat.py` or combat resolution code - Call it on HP ≤ 0

---

## 3. Player Weapon Names Not Logged (MEDIUM)

**Problem:** 629 combat_action events have `weapon: "Unknown Weapon"` for player attacks.

**Evidence:**
- Breaker: 326 "Unknown Weapon" attacks
- Cipher: 63, Ghost: 39

**Current:** Weapon data captured for enemies but not players.

**Recommended fix:**
When logging player combat_action, extract weapon from action context:

```python
# In combat_action logging
weapon_name = action.get('weapon') or action.get('context', {}).get('weapon') or "Unarmed"
```

**Files to modify:**
- `mechanics.py:log_combat_action()` or wherever player attacks are logged

---

## 4. Skills Analyzer Counting NPC Actions (FIXED)

**Problem:** 66% of "skill rolls" were actually NPC actions (flee, hide, plead) with null roll data.

**Fix applied:** `scripts/datamine/analyzers/skills.py:121-124`
```python
# Skip NPC actions that don't have actual skill checks
if roll.get("attr") is None:
    return
```

**Status:** ✅ Fixed 2025-12-14

---

## 5. Altar ID Fragmentation (LOW)

**Problem:** Same altars logged with inconsistent IDs:
```
alt_nexus_sanctified
alt_nexus_sanctified_01
alt_nexus_sanctified_master
nexus_sanctified_altar_01
```

**Impact:** Hard to aggregate altar performance stats.

**Recommended fix:** Standardize altar ID generation or add `altar_type` field for grouping.

---

## 6. Empty Item Names in Purchase Failures (LOW)

**Problem:** 3 purchase failures logged with `item: ""`

**Recommended fix:** Validate item name before logging, use "Unknown Item" fallback.

---

## Summary Table

| Issue | Priority | Impact | Effort |
|-------|----------|--------|--------|
| Roll modifiers not logged | HIGH | Can't analyze penalty/bonus effects | Medium |
| Combat defeats not logged | HIGH | Missing kill data for ML training | Low |
| Player weapons not logged | MEDIUM | Can't analyze player weapon usage | Low |
| Skills analyzer NPC filter | - | ✅ Fixed | - |
| Altar ID fragmentation | LOW | Aggregation difficulty | Low |
| Empty item names | LOW | Data quality | Trivial |

---

## Implementation Order

1. **Roll modifiers** - Most impactful for understanding game balance
2. **Combat defeats** - Essential for combat ML training data
3. **Player weapons** - Quick fix, improves combat analysis
4. Altar IDs and item names - Nice to have

---

## Schema Additions Needed

### For `action_resolution.roll`:
```python
class RollModifier(BaseModel):
    source: str  # "void_penalty", "altar_bonus", "condition", "no_offering", etc.
    value: int   # +3, -2, etc.
    details: Optional[Dict[str, Any]] = None  # {"void_level": 2}, {"altar_id": "..."}, etc.

# Add to roll dict:
"modifiers": List[RollModifier]
"modifier_total": int  # Sum of all modifiers
```

### For `enemy_defeat`:
```python
class EnemyDefeat(BaseModel):
    enemy_id: str
    enemy_name: str
    defeat_reason: Literal["killed", "fled", "subdued", "convinced", "departed"]
    killer_id: Optional[str] = None  # For combat kills
    killer_name: Optional[str] = None
    final_damage: Optional[int] = None
    round: int
```
