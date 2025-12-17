# Unknown Weapons Investigation

## Problem Summary

32.4% of `combat_action` events (712 out of 2197) have `weapon: "Unknown Weapon"` or missing weapon field, causing inaccurate weapon effectiveness metrics in the balance analyzer.

## Data Source

**Event type:** `combat_action`
**Location:** `bulk_output/session_*.jsonl` (245 sessions, recursive)
**Analyzer:** `scripts/datamine/analyzers/weapons.py`

## How to Reproduce

```bash
# Run targeting analyzer to see the stats
source .venv/bin/activate
python scripts/yags_mine.py balance bulk_output/ -a targeting

# Direct inspection of combat_action events
find bulk_output -name "session_*.jsonl" -exec cat {} \; | \
  grep '"event_type": "combat_action"' | \
  python3 -c "
import json, sys
from collections import Counter
weapons = Counter()
for line in sys.stdin:
    e = json.loads(line)
    weapons[e.get('weapon', 'MISSING')] += 1
for w, c in weapons.most_common(20):
    print(f'{c:>5} {w}')
"
```

## Sample combat_action Event (Good)

From `bulk_output/` - this is what a properly populated event looks like:

```json
{
  "event_type": "combat_action",
  "attacker": {
    "id": "enemy_security_drone_a1f7dcde",
    "name": "Sovereign Nexus Security Automated Patrol #2"
  },
  "defender": {
    "id": "player_02",
    "name": "Jace Kordell"
  },
  "weapon": "Stun Gun",           // <-- GOOD: weapon populated
  "attack": {
    "attr": "Perception",
    "skill": "Guns",
    "hit": true,
    "margin": 24
  },
  "damage": {
    "dealt": 7,
    "damage_type": "stun"
  }
}
```

## Where combat_action Events Are Logged

**File:** `scripts/aeonisk/multiagent/mechanics.py`

Search for `jsonl_logger.log_combat_action` to find the logging call. The weapon field should be populated from the attack resolution context.

**Related files:**
- `scripts/aeonisk/multiagent/enemy_combat.py` - Enemy attack logic
- `scripts/aeonisk/multiagent/dm.py` - DM action resolution
- `scripts/aeonisk/multiagent/action_router.py` - Action routing

## Root Cause: Fallback Damage System

**All 712 unknown weapon events are from the fallback damage system.**

Key evidence from sample event:
- `attacker.id: "unknown"`, `attacker.name: "Unknown Attacker"`
- `attack: {}` - empty attack block (no roll data)
- `weapon: "Unknown Weapon"`
- But damage IS applied to a valid defender

This happens when:
1. Player declares a combat action against an enemy
2. DM adjudicates but doesn't provide structured damage output
3. Fallback system applies damage mechanically
4. No weapon/attacker context is available in fallback path

## Sample Fallback Damage Event

```json
{
  "event_type": "combat_action",
  "attacker": {
    "id": "unknown",
    "name": "Unknown Attacker"
  },
  "defender": {
    "id": "enemy_grunt_23bc4aa4",
    "name": "Station Security Guards #1"
  },
  "weapon": "Unknown Weapon",
  "attack": {},
  "damage": {
    "base_damage": 18,
    "soak": 6,
    "dealt": 12
  },
  "wounds_dealt": 2,
  "defender_state_after": {
    "health": 18,
    "max_health": 30,
    "wounds": 2,
    "alive": true,
    "status": "active"
  }
}
```

## Key Insight

**100% of the 712 "Unknown Weapon" events also have "Unknown Attacker"** - this is not a weapon-specific issue, it's the fallback damage path missing all attacker context.

## Investigation Commands

```bash
# Check which sessions have the most unknown weapons
find bulk_output -name "session_*.jsonl" -exec sh -c '
  count=$(grep -c "Unknown Weapon" "$1" 2>/dev/null || echo 0)
  if [ "$count" -gt 0 ]; then echo "$count $1"; fi
' _ {} \; | sort -rn | head -10

# Look at a specific unknown weapon event
find bulk_output -name "session_*.jsonl" -exec cat {} \; | \
  grep '"weapon": "Unknown Weapon"' | head -1 | python3 -m json.tool

# Check if unknown weapons correlate with specific attacker types
find bulk_output -name "session_*.jsonl" -exec cat {} \; | \
  grep '"event_type": "combat_action"' | \
  python3 -c "
import json, sys
from collections import Counter
by_attacker = Counter()
for line in sys.stdin:
    e = json.loads(line)
    weapon = e.get('weapon', 'MISSING')
    if weapon in ('unknown', 'Unknown Weapon', None, ''):
        attacker = e.get('attacker', {})
        attacker_id = attacker.get('id', 'no_id') if isinstance(attacker, dict) else 'no_attacker'
        # Get prefix (player_, enemy_, npc_)
        prefix = attacker_id.split('_')[0] if '_' in attacker_id else attacker_id
        by_attacker[prefix] += 1
for a, c in by_attacker.most_common():
    print(f'{c:>5} {a}')
"
```

## Exact Code Locations

**Fallback damage logging (the source of unknown weapons):**
- `scripts/aeonisk/multiagent/dm.py:299-302` - Sets "Unknown Attacker" and "Unknown Weapon"
- `scripts/aeonisk/multiagent/dm.py:4961` - Another fallback path

```python
# dm.py:299-302 (fallback damage logging)
attacker_name="Unknown Attacker",
attacker_id="unknown",
weapon="Unknown Weapon",
```

**To fix:** Pass the actual player/character context into the fallback damage path.

## Files to Check

1. **`scripts/aeonisk/multiagent/dm.py`** (PRIMARY)
   - Line 299-302: Fallback damage logging with hardcoded "Unknown Weapon"
   - Line 4961: Another unknown weapon fallback
   - Need to pass player action context to these paths

2. **`scripts/aeonisk/multiagent/mechanics.py`**
   - Search for `log_combat_action`
   - Check what `weapon` parameter is passed

3. **`scripts/aeonisk/multiagent/outcome_parser.py`**
   - Contains fallback damage logic
   - May need to preserve weapon context

4. **`scripts/datamine/analyzers/weapons.py`**
   - Line 69-106: `_process_combat_action` - main processing
   - Line 108-137: `_process_action_resolution` - fallback path

## Code Context (dm.py:296-307)

```python
# Note: attack_roll data would need to be passed from resolution context
# For now, log minimal combat action
mechanics.jsonl_logger.log_combat_action(
    round_num=current_round,
    attacker_id="unknown",  # Would need from resolution context
    attacker_name="Unknown Attacker",
    defender_id=target_entity.agent_id,
    defender_name=target_name,
    weapon="Unknown Weapon",
    attack_roll={},  # Would need from resolution context
    damage_roll=damage_roll_data,
    wounds_dealt=wounds_dealt,
    defender_state_after=defender_state
)
```

**The comments in the code acknowledge the problem!** The resolution context has the attacker info, but it's not being passed down to this function.

## FIX IMPLEMENTED ✅

**Date:** 2025-12-01
**Branch:** `bulk-generation`

### What Was Done

1. **Updated `_process_structured_damage_effects` signature** (`dm.py:125-133`)
   - Added three new parameters with defaults for backwards compatibility:
     - `attacker_id: str = "unknown"`
     - `attacker_name: str = "Unknown Attacker"`
     - `weapon: str = "Unknown Weapon"`

2. **Updated call site** (`dm.py:6698-6711`)
   - Extract attacker context from `action` dict:
     - `action.get('agent_id', 'unknown')` → `attacker_id`
     - `action.get('character_name', 'Unknown Attacker')` → `attacker_name`
     - `action.get('weapon', 'Unknown Weapon')` → `weapon`

3. **Updated logging call** (`dm.py:302-308`)
   - Now uses the passed parameters instead of hardcoded "Unknown" values

### Test Coverage

New test file: `tests/unit/test_damage_logging_attacker_context.py`
- `test_logs_attacker_info_when_provided` - Verifies correct logging when context provided
- `test_defaults_to_unknown_when_context_not_provided` - Backwards compatibility
- `test_logs_weapon_from_action_context` - Weapon extraction works

Run with: `python -m pytest tests/unit/test_damage_logging_attacker_context.py -v`

### Verification

After this fix, **new sessions** will have proper attacker/weapon info in combat_action events.

Existing bulk_output data still has "Unknown Weapon" because it was generated before the fix.

## Historical Context (Potential Fixes)

The following options were considered:

1. ✅ **Pass resolution context to `_process_structured_damage_effects`** (IMPLEMENTED)
   - The function now receives attacker context from the action dict
   - Extract weapon from `action.get('weapon')`
   - Extract attacker from `action.get('agent_id')` and `action.get('character_name')`

2. **Alternative: Look up from action declaration**
   - The `action_declaration` event logged earlier has the weapon info
   - Could correlate by `correlation_id` to find the original action

3. **Analyzer-side workaround** - Filter out "Unknown Weapon" events from weapon effectiveness stats (they represent fallback damage, not actual weapon usage)

4. **Validation warning** - Add structured output validation that warns when DM doesn't provide damage effects for combat actions (forcing more structured output compliance)

## Related Issues

The weapons analyzer was also fixed in this session for a different issue:
- **Original bug:** Reading `hit` from top-level instead of `attack.hit`
- **Fix location:** `scripts/datamine/analyzers/weapons.py:74-78`
- **Commit:** Check recent commits on `bulk-generation` branch

## Context From This Session

This investigation was done as part of expanding `yags_mine.py balance` command. The targeting analyzer was created to find these kinds of data quality issues. Run `yags_mine.py balance bulk_output/ -a targeting` to see the full targeting analysis including weapon issues.
