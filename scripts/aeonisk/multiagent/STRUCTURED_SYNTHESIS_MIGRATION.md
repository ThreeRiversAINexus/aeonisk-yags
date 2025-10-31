# Structured Synthesis Migration - Phase 5

**Date:** 2025-10-31
**Status:** ✅ Complete
**Issue Fixed:** Enemy spawning bug during story advancement

---

## Problem

The AI DM wanted to spawn enemies while advancing the scenario, but the timing was wrong:

1. DM generates `[ADVANCE_STORY: location | situation]` marker
2. Session handler parses marker → **clears ALL enemies**
3. DM's `[SPAWN_ENEMY: ...]` marker is parsed → spawns new enemies
4. **BUG:** New enemies were sometimes cleared before they could act

**Root Cause:** Text marker parsing created a race condition where enemies were cleared before/after spawning, depending on parsing order.

---

## Solution

Migrated from **text marker parsing** to **structured output** using existing Pydantic schemas:

- `RoundSynthesis` - DM's round summary (already existed, but not used)
- `StoryAdvancement` - Story progression with `clear_all_enemies` flag
- `EnemySpawn` - Structured enemy spawning
- `EnemyRemoval` - Non-combat enemy exits (fled, convinced, neutralized)
- `NewClock` - Clock creation with semantic meaning

**Key Fix:** `StoryAdvancement.clear_all_enemies` flag allows DM to control enemy clearing:
- `clear_all_enemies=True` (default) - Clear all enemies when story advances
- `clear_all_enemies=False` - Preserve enemies when spawning new ones

---

## Changes Made

### 1. DM Agent (`dm.py`)

**Modified `_synthesize_round_outcome()`:**
- Returns `RoundSynthesis` object instead of converting to text markers
- Removed marker conversion logic (lines 2116-2139)

**Modified `_handle_synthesis()`:**
- Detects structured vs legacy synthesis
- Passes `RoundSynthesis` object in message payload as `structured_synthesis`

**Impact:**
- DM now generates structured output by default
- Falls back to legacy text generation if structured output fails

---

### 2. Session Handler (`session.py`)

**New Method: `_process_structured_synthesis()`**
- Handles `RoundSynthesis` objects without parsing
- Processes story advancement with conditional enemy clearing
- Spawns enemies AFTER story advancement (correct order)
- Handles enemy removals (fled, convinced, neutralized)
- Spawns new clocks with semantic meaning

**New Method: `_process_legacy_markers()`**
- Extracts legacy marker parsing to separate method
- Used as fallback for non-structured synthesis

**Modified `_handle_dm_narration()`:**
- Checks for `structured_synthesis` in payload
- Routes to structured or legacy processing

**New Method: `_spawn_new_clocks_structured()`**
- Spawns clocks from `NewClock` objects
- Includes semantic meaning (advance_meaning, regress_meaning)

---

### 3. Enemy Combat System (`enemy_combat.py`)

**New Method: `spawn_from_structured()`**
- Spawns enemies from `List[EnemySpawn]`
- No regex parsing required
- Logs JSONL events with spawn_reason

**New Method: `remove_from_structured()`**
- Removes enemies from `List[EnemyRemoval]`
- Handles non-combat exits (fled, convinced, neutralized)
- Logs JSONL events with removal reason

**Impact:**
- Type-safe enemy spawning
- Better ML training data (structured spawn reasons)

---

### 4. Unit Tests (`test_structured_synthesis.py`)

**21 tests covering:**
- Story advancement with/without enemy clearing
- Enemy spawning (basic, with traits, multiple count)
- Enemy removal (fled, convinced, neutralized)
- Round synthesis with multiple components
- Scene pivots (minor room transitions)
- Clock creation with semantic meaning
- Integration tests for bug fix scenario

**All tests pass ✅**

---

## Benefits

### ✅ **Bug Fix**
- DM can now spawn enemies while advancing story
- `clear_all_enemies=False` preserves newly spawned enemies
- No more race conditions from marker parsing order

### ✅ **Type Safety**
- Pydantic validation at generation time
- No invalid markers (eliminates retry logic)
- Compile-time errors for schema violations

### ✅ **Better ML Training Data**
- Structured JSONL events with spawn reasons
- Removal reasons (fled, convinced, neutralized)
- Clock semantics (advance_meaning, regress_meaning)

### ✅ **Simpler Code**
- No regex parsing for structured path
- Legacy parsers kept as fallback only
- Clearer intent (structured objects vs text)

### ✅ **Flexibility**
- `clear_all_enemies` flag for conditional clearing
- `scene_pivot` for minor room transitions (separate from story advancement)
- `enemy_removals` for non-combat exits

---

## Usage Examples

### Example 1: Story Advancement WITHOUT Enemy Clearing

```python
synthesis = RoundSynthesis(
    narration="The facility alarms blare as security converges...",
    story_advancement=StoryAdvancement(
        should_advance=True,
        location="Data Vault - Level 3",
        situation="Breached the vault, security responding",
        clear_all_enemies=False,  # Preserve enemies!
        new_clocks=[...]
    ),
    enemy_spawns=[
        EnemySpawn(
            template="Elite",
            faction="ACG Security",
            archetype="Tactical Response",
            count=2,
            spawn_reason="Vault breach triggered deployment",
            initial_position=Position.FAR_ENEMY
        )
    ]
)
```

**Result:** Story advances, old enemies stay active, new enemies spawn.

---

### Example 2: Story Advancement WITH Enemy Clearing (Default)

```python
synthesis = RoundSynthesis(
    narration="You escape to the safe house...",
    story_advancement=StoryAdvancement(
        should_advance=True,
        location="Underground Safe House",
        situation="Escaped. Time to regroup.",
        clear_all_enemies=True,  # Default
        new_clocks=[...]
    ),
    enemy_spawns=[]  # No new enemies
)
```

**Result:** Story advances, all enemies cleared, fresh start.

---

### Example 3: Enemy Removal (Non-Combat)

```python
synthesis = RoundSynthesis(
    narration="The cultist leader flees through a void rift...",
    story_advancement=StoryAdvancement(should_advance=False),
    enemy_removals=[
        EnemyRemoval(
            enemy_name="Void Cult Leader",
            resolution=EnemyResolution.FLED,
            reason="Escaped through void rift after ritual failure"
        )
    ]
)
```

**Result:** Enemy removed via non-combat means, logged to JSONL.

---

## Testing

Run the test suite:

```bash
cd scripts/aeonisk
source .venv/bin/activate
python3 multiagent/test_structured_synthesis.py
```

**Expected Output:**
```
Ran 21 tests in 0.001s

OK
```

---

## Backward Compatibility

**Legacy marker parsing is still supported:**
- If DM doesn't generate structured output, falls back to text markers
- `_process_legacy_markers()` handles old flow
- No breaking changes for existing sessions

**Migration is gradual:**
- DM tries structured output first
- Falls back to legacy if structured fails
- Both paths work simultaneously

---

## Next Steps (Optional)

### Future Enhancements (Not Required Now)

1. **Remove legacy parsing (clean cutover):**
   - Delete `outcome_parser.py` marker functions
   - Delete `enemy_spawner.py` marker parsing
   - Remove `_retry_invalid_markers()` from dm.py

2. **Extend structured output:**
   - Use structured output for action resolution (already exists)
   - Use structured output for scenario generation (already exists)
   - Migrate all DM outputs to structured

3. **Schema versioning:**
   - Add schema version field to RoundSynthesis
   - Track schema changes for ML training compatibility

---

## Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `dm.py` | Return structured object, updated handler | ~40 |
| `session.py` | Structured/legacy processing, new spawn method | ~230 |
| `enemy_combat.py` | Structured spawn/removal methods | ~130 |
| `test_structured_synthesis.py` | 21 unit tests | 440 (new) |

**Total:** ~840 lines changed/added

---

## Validation

**Manual Testing:**
1. Run combat session: `python3 ../run_multiagent_session.py ../session_configs/session_config_combat.json`
2. Watch for "Processing structured synthesis (Phase 5)" in logs
3. Verify enemies spawn during story advancement
4. Check JSONL logs for structured spawn data

**Automated Testing:**
```bash
python3 multiagent/test_structured_synthesis.py
```

All 21 tests pass ✅

---

## Conclusion

The structured synthesis migration successfully fixes the enemy spawning bug while improving type safety, ML training data quality, and code maintainability. The system now uses validated Pydantic schemas instead of fragile text marker parsing, with full backward compatibility for legacy sessions.

**Bug Status:** ✅ **FIXED**
**Tests:** ✅ **21/21 PASSING**
**Backward Compatibility:** ✅ **MAINTAINED**
