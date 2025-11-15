# Enemy Departures Feature

**Status:** ✅ Implemented and tested

## Problem

The DM tried to remove enemies who "stood down" after diplomacy by using `npc_departures`, but this silently failed because:
1. `npc_departures` only processes NPCs from `shared_state.npc_agents`
2. Enemies are tracked separately in `enemy_combat.enemy_agents`
3. The only way to remove enemies was `enemy_conversions` with complex resolution types (FLED, STORY_ADVANCED)

**Real-world failure case (from session log):**
```
Entity Lifecycle Phase #2 output:
- npc_departures: ["enemy_grunt_8cb76347", "enemy_grunt_4b00689d", "enemy_grunt_6c226863"]
- Reasoning: "Cathedral Security stood down - no hostile intent shown"

Result: Processing silently failed, enemies stayed in scene
```

## Solution

Added `enemy_departures` field parallel to `npc_departures` for **simple enemy removal** without narrative transformation.

### Design Philosophy

**Two ways to remove enemies:**

1. **`enemy_departures`** (Simple removal):
   - Guards finish inspection and leave
   - Patrol moves on
   - Security confirms authorization and stands down
   - Just list agent IDs, no complex reasoning required

2. **`enemy_conversions`** (Narrative transformation):
   - Surrender (→ prisoner NPC)
   - Flee in terror (FLED)
   - Knocked unconscious (SUBDUED)
   - Requires resolution type + reason + optional NPC fields

### Decision Matrix

| Scenario | Use |
|----------|-----|
| Guards check credentials, stand down, leave | `enemy_departures` |
| Raider surrenders, becomes prisoner | `enemy_conversions` (CONVINCED) |
| Thug flees in terror | `enemy_conversions` (FLED) |
| Patrol moves on | `enemy_departures` |
| Security responds to alarm, situation resolved | `enemy_departures` |

## Implementation

### Schema Changes

**ConversionDecisions** (`schemas/story_events.py:855-874`):
```python
enemy_departures: List[str] = Field(
    default_factory=list,
    description="Enemy agent_ids to remove from scene (fled, stood down, left)"
)
```

**EntityLifecycleResult** (`schemas/story_events.py:927-928`):
```python
enemies_departed: List[str] = field(default_factory=list)
```

**ScenePivot** (`schemas/story_events.py:167-170`):
```python
enemy_departures: List[str] = Field(
    default_factory=list,
    description="Enemy agent_ids to remove during scene pivot"
)
```

### Processing Locations

Enemy departures are processed in **3 locations**:

1. **Entity Lifecycle Phase #1** (`session.py:1780-1810`):
   - Regular conversion check during combat
   - Marks enemies as inactive: `enemy.is_active = False`
   - Logs to JSONL using `enemy_defeat` event with `resolution='departed'`

2. **Entity Lifecycle Phase #2** (`session.py:3703-3716`):
   - Post-story-advancement (new scene initialization)
   - Removes enemies who don't follow to new location
   - Used when scene changes after `StoryAdvancement`

3. **Scene Pivot** (`session.py:3829-3842`):
   - Minor scene changes (same location, different room)
   - Removes enemies during tactical repositioning
   - Used when scene changes within same chapter

### Logging Updates

- Print statements show `enemy_departures` count
- Logger includes enemy departures in conversion check summary
- EntityLifecycleResult tracks and logs departed enemies to JSONL
- `to_synthesis_context()` mentions "X enemy(ies) departed"

### Prompt Updates

**dm_conversion_check.yaml** (`lines 133-156`):
- New section: "Enemy Departures vs Enemy Conversions"
- Decision matrix with examples
- Clear guidance: Use `enemy_departures` for stand-down scenarios
- Example reasoning: "Cathedral Security confirmed authorization, stood down and departed"

## Testing

**Unit tests** (`tests/unit/test_enemy_departures.py`):
- ✅ ConversionDecisions has `enemy_departures` field
- ✅ Defaults to empty list
- ✅ Accepts multiple enemy IDs
- ✅ EntityLifecycleResult tracks `enemies_departed`
- ✅ JSONL output includes `enemies_departed`
- ✅ Synthesis context mentions departed enemies
- ✅ ScenePivot has `enemy_departures` field

All 8 tests pass.

## Example Usage

### Before (Failed Silently)
```python
ConversionDecisions(
    npc_departures=["enemy_grunt_abc123"],  # WRONG! This is an enemy, not NPC
    reasoning="Guards stood down"
)
# Result: Enemy stays in scene (processing ignored enemy IDs)
```

### After (Works Correctly)
```python
ConversionDecisions(
    enemy_departures=["enemy_grunt_abc123"],  # CORRECT! Simple removal
    reasoning="Guards confirmed authorization and departed"
)
# Result: Enemy marked inactive and removed from scene
```

### Complex Transformation (Still Use enemy_conversions)
```python
ConversionDecisions(
    enemy_conversions=[
        EnemyConversion(
            enemy_id="enemy_raider_xyz",
            resolution=EnemyResolution.CONVINCED,
            reason="Surrendered after low HP",
            resulting_entity_type="prisoner",
            resulting_disposition="prisoner"
        )
    ],
    reasoning="Raider surrendered and became prisoner NPC"
)
# Result: Enemy converted to prisoner NPC, stays in scene
```

## Files Changed

- `scripts/aeonisk/multiagent/schemas/story_events.py` - Added fields to ConversionDecisions, EntityLifecycleResult, ScenePivot
- `scripts/aeonisk/multiagent/session.py` - Processing in 3 locations (lifecycle #1, #2, pivot)
- `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_conversion_check.yaml` - Decision matrix and guidance
- `tests/unit/test_enemy_departures.py` - 8 unit tests (all passing)

## Commits

1. `13a814b` - fix: Add Pydantic validation logging and test infrastructure
2. `f41b140` - feat: Add enemy_departures field for simple enemy removal
3. `5dfaee3` - test: Add unit tests for enemy_departures feature

## Next Steps

The feature is complete and tested. The DM should now correctly use `enemy_departures` for stand-down scenarios instead of trying to use `npc_departures` for enemies.

**Monitor in future sessions:** Watch for DM using `enemy_departures` vs `enemy_conversions` appropriately based on the decision matrix.
