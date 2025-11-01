# "Target Has Moved" Bug - Quick Fix Guide

## Problem
Enemies attacking PCs show "attacks but target has moved" even when PCs didn't move.

## Root Cause
**File:** `enemy_combat.py:772`

```python
# Find target PC
target = next((p for p in player_agents if p.agent_id == target_id), None)
if not target:
    return {'narration': f"{enemy.name} attacks but target has moved"}
```

**Issue:** Enemy uses free targeting IDs (`tgt_xxxx`) but code looks for exact `agent_id` match (`player_01`).

## Fix
Need to resolve target IDs through the target ID mapper before lookup.

**Location:** `enemy_combat.py:_execute_attack()` around line 768-780

**Add before line 772:**
```python
# Resolve target ID if using free targeting mode
if target_id and target_id.startswith('tgt_'):
    # Get target mapper from shared state
    target_mapper = resolution_state.get_target_id_mapper()  # or however it's accessed
    if target_mapper:
        resolved_entity = target_mapper.resolve_target(target_id)
        if resolved_entity and hasattr(resolved_entity, 'agent_id'):
            target_id = resolved_entity.agent_id  # Use real agent_id
```

**Same fix needed in:**
- `_execute_suppress()` line 1034-1040
- Any other enemy actions that look up targets

## Grenade Multi-Target Issue
Player noted grenades showing multiple targets but damage not implemented.

**Solution:** Remove grenade action from enemy options for now, add TODO for multi-target damage support.

## Next Session Tasks
1. Fix target ID resolution in enemy_combat.py
2. Remove or disable grenade actions temporarily
3. Test impossible combat again
4. Verify damage is actually being applied to PCs
