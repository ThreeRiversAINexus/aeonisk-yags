# Combat Damage Bug - Root Cause Analysis & Fix Plan

## Problem Statement

**Symptom:** Damage is not being applied to enemies during combat, even though the DM generates narrative descriptions of damage.

**Example from JSONL:**
```json
{
  "effects": [
    "Critically Wounded: Chest destroyed, dying, cannot take offensive actions",
    "Mangled Arm: Severe tissue damage to second cultist, reduced combat effectiveness"
  ]
}
```

These are **string descriptions**, not structured data that the game engine can process.

## Root Cause

### Issue 1: Missing Damage Extraction (PRIMARY BUG)

**File:** `scripts/aeonisk/multiagent/outcome_parser.py`
**Function:** `extract_from_structured_resolution()` (lines 16-107)

This function converts Pydantic `ActionResolution` objects to legacy `state_changes` dict format, but it's **missing damage extraction**:

```python
# CURRENT CODE (lines 67-107)
# Extract conditions
conditions = [...]  # ✓ Extracted

# Extract position changes
position_change = ...  # ✓ Extracted

# Build state_changes dict
state_changes = {
    'clock_triggers': clock_triggers,  # ✓
    'void_change': void_change,  # ✓
    'conditions': conditions,  # ✓
    'position_change': position_change,  # ✓
    'soulcredit_change': soulcredit_change,  # ✓
    # ❌ MISSING: 'damage' field!
}
```

The `ActionResolution.effects` object has a `damage` field (`DamageEffect` or `None`), but it's never extracted.

### Issue 2: Effects Field Format Confusion (SECONDARY)

**File:** Session JSONL output
**Field:** `effects` array containing strings

The JSONL shows:
```json
"effects": [
  "Critically Wounded: Chest destroyed, dying, cannot take offensive actions",
  "Mangled Arm: Severe tissue damage to second cultist, reduced combat effectiveness"
]
```

These appear to be coming from a legacy text-parsing path, NOT from structured output. Need to verify:
1. Is the DM actually generating structured `ActionResolution` with proper `MechanicalEffects`?
2. Or is it falling back to text generation and parsing narrative strings?

## Fix Plan

### Phase 1: Diagnostic (Determine Current State)

1. **Check if structured output is being used**
   - Add logging to `dm.py:_generate_llm_response()` (line ~4060) to confirm `_last_structured_resolution` is set
   - Check if `resolution_obj.effects.damage` exists and is populated
   - Verify the DM is actually returning `ActionResolution` objects, not falling back to text

2. **Check what's in the structured resolution**
   - Log `resolution_obj.effects.damage` to see if DamageEffect objects exist
   - Log `resolution_obj.effects.conditions` to compare with JSONL output

### Phase 2: Fix Damage Extraction (PRIMARY FIX)

**File:** `scripts/aeonisk/multiagent/outcome_parser.py`

Add damage extraction to `extract_from_structured_resolution()`:

```python
# After line 76 (after extracting conditions)

# Extract damage effects
damage_effects = []
if resolution_obj.effects.damage:
    damage_effects.append({
        'target': resolution_obj.effects.damage.target,
        'base_damage': resolution_obj.effects.damage.base_damage,
        'soak': resolution_obj.effects.damage.soak,
        'dealt': resolution_obj.effects.damage.dealt,
        'damage_type': resolution_obj.effects.damage.damage_type
    })

# Then add to state_changes dict (line 90)
state_changes = {
    'clock_triggers': clock_triggers,
    'void_change': void_change,
    # ... existing fields ...
    'damage_effects': damage_effects,  # ← ADD THIS
    'conditions': conditions,
    # ...
}
```

### Phase 3: Verify Damage Application (DOWNSTREAM CHECK)

**Files to check:**
- `scripts/aeonisk/multiagent/coordinator.py` - Where state_changes is consumed
- `scripts/aeonisk/multiagent/mechanics.py` - Where damage is applied to character state

**Questions:**
1. Does the code that applies damage expect a `damage_effects` field in state_changes?
2. Or does it look for a different field name?
3. Is there existing code that handles damage from `DamageEffect` objects?

**Search for:**
- `state_changes['damage']`
- `state_changes['damage_effects']`
- `apply_damage` functions
- Where combat damage is actually subtracted from HP

### Phase 4: Test & Verify

1. Run `session_config_lethal_combat_test.json` again
2. Check JSONL for:
   - `effects.damage` field populated (not null)
   - Enemy HP decreasing in `character_data` snapshots
   - Proper enemy_defeat events when HP reaches 0

## Open Questions

1. **Where does the string-based `effects` array come from?**
   - Is this a separate legacy field?
   - Or is it being populated by a different code path?

2. **Is there existing damage application code?**
   - Need to find where damage is supposed to be applied
   - May need to add new code if it doesn't exist

3. **What about multi-target damage?**
   - Current `MechanicalEffects` schema has `damage: Optional[DamageEffect]` (single target)
   - But shotgun blast hits multiple enemies
   - Do we need `damage_effects: List[DamageEffect]` instead?
   - This might be a schema design issue

4. **Feature flag cleanup?**
   - User mentioned "many feature flags muddled the codebase"
   - Should we identify and remove unused feature flags as part of this work?
   - Or keep that as a separate cleanup task?

## Next Steps

1. Start with Phase 1 diagnostic logging
2. Determine if structured output is actually being used
3. Check the ActionResolution schema to confirm damage field structure
4. Implement Phase 2 fix
5. Find and verify Phase 3 downstream damage application
6. Test with lethal combat config

## Related Files

- `scripts/aeonisk/multiagent/outcome_parser.py` - Extraction bug (PRIMARY)
- `scripts/aeonisk/multiagent/dm.py` - DM resolution generation
- `scripts/aeonisk/multiagent/schemas/action_resolution.py` - ActionResolution schema
- `scripts/aeonisk/multiagent/schemas/shared_types.py` - DamageEffect schema
- `scripts/aeonisk/multiagent/coordinator.py` - State application (need to check)
- `scripts/aeonisk/multiagent/mechanics.py` - Damage application (need to check)
