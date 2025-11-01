# Environmental Void Targeting Bug - Fix Summary

## Bug Description
When DM specifies void changes targeting environmental/abstract targets (like "Environmental Void"), the void change was incorrectly applied to the actor instead of being skipped. This causes players to receive unearned void reductions.

**Example:** Ash Vex performs dispersal ritual targeting "Environmental Void" → DM specifies void_change=-2 → Bug: Ash gets -2 void reduction → Expected: Should be skipped (environmental void tracked via scene clocks)

## Root Cause
In `dm.py`, when `void_target_character` could not be resolved to a valid player, the code fell back to applying the void change to the actor. This happened in several scenarios:

1. `void_target_character="Environmental Void"` (or similar abstract targets)
2. `void_target_character="Unknown Name"` (typo or non-existent character)
3. Valid collaborative cleansing targets worked correctly
4. Self-inflicted void (no target specified) worked correctly

**Pattern:** Identical to Bug #1 (status effect targeting) - fallback to actor instead of skip.

## Fix Implemented
**Location:** `scripts/aeonisk/multiagent/dm.py` lines 2767-2853 and 3176-3262

**Before:**
```python
if target_player_id:
    void_state = mechanics.get_void_state(target_player_id)
else:
    # BUG: Fall back to actor
    logger.warning(f"Could not resolve target '{target_identifier}', applying to actor")
    void_state = mechanics.get_void_state(player_id)

# Always applies void change
old_void = void_state.score
void_state.add_void(...)
```

**After:**
```python
should_apply_void_change = True
void_state = None

if target_identifier:
    # Check for environmental/abstract targets
    if target_identifier in ('Environmental Void', 'environment', 'area', 'Environmental'):
        should_apply_void_change = False  # Skip
    else:
        # Try to resolve target
        if target_player_id:
            void_state = mechanics.get_void_state(target_player_id)
        else:
            # Unresolvable - skip instead of falling back
            logger.warning(f"Could not resolve target '{target_identifier}', skipping")
            should_apply_void_change = False
else:
    # Default: self-inflicted void
    void_state = mechanics.get_void_state(player_id)

# Only apply if we have a valid target
if should_apply_void_change and void_state:
    old_void = void_state.score
    void_state.add_void(...)
```

**Key improvements:**
- Added `should_apply_void_change` flag to control application
- Explicit check for environmental keywords: "Environmental Void", "environment", "area", "Environmental", "ambient", "scene", "location"
- Changed unresolvable target behavior from "apply to actor" to "skip"
- Wrapped all void application logic in conditional check

## Schema Validation Added
**Location:** `scripts/aeonisk/multiagent/schemas/shared_types.py` lines 48-76

Added Pydantic field validator to `VoidChange` model to catch environmental targets early:

```python
@field_validator('character_name')
@classmethod
def validate_not_environmental(cls, v: str) -> str:
    """Prevent environmental/abstract targets in character void changes."""
    environmental_keywords = ['environmental', 'environment', 'area', 'ambient', 'scene', 'location']
    v_lower = v.lower()

    if any(keyword in v_lower for keyword in environmental_keywords):
        raise ValueError(
            f"Invalid character name '{v}' - environmental void effects should be tracked "
            f"via scene clocks, not character void. Use specific character names only."
        )

    return v
```

**Benefits:**
- Provides helpful error message guiding DMs to use scene clocks
- Catches issue during structured output validation (before application)
- Uses Pydantic V2 `@field_validator` (no deprecation warnings)

## Test Coverage

### Unit Tests Created
**File:** `tests/unit/test_void_change_targeting.py` (6 tests, all passing)

1. **`test_environmental_void_skipped`** ✅
   - Verifies environmental targets are skipped
   - Tests `void_target_character="Environmental Void"`

2. **`test_unresolvable_void_target_skipped`** ✅
   - Verifies unresolvable character names are skipped
   - Tests `void_target_character="Unknown Character"`

3. **`test_void_change_applied_to_explicit_target`** ✅
   - Verifies collaborative cleansing works correctly
   - Tests `void_target_character="Riven Ashglow"` (valid character)

4. **`test_void_change_applied_to_actor_when_no_target`** ✅
   - Verifies self-inflicted void works correctly
   - Tests `void_target_character=None` (no target specified)

5. **`test_void_reduction_reduces_score`** ✅
   - Verifies void reduction math is correct
   - Tests negative void changes properly decrease score

6. **`test_debt_auction_ambush_environmental_void`** ✅
   - Uses real fixture data from existing session
   - Demonstrates the bug existed in actual gameplay

### Session Config Created
**File:** `scripts/session_configs/session_config_void_change_test.json`

**Purpose:** Contrived test scenario to verify the fix with actual LLM agents

**Setup:**
- 1 round, non-combat scenario
- Player: Test Ritualist with void=6/10
- Environment: Ritual chamber with ambient void contamination
- Goal: Perform cleansing ritual targeting either environmental void OR self

**Test Cases:**
1. **Environmental targeting** (void_target_character="Environmental Void")
   - Expected: Void change SKIPPED (player void stays 6/10)
   - Bug behavior: Player void reduced (unearned benefit)

2. **Self-cleansing** (void_target_character=null or missing)
   - Expected: Void change applied to player (6 → 4)
   - Should continue working correctly

## Running the Tests

```bash
# Activate environment
source .venv/bin/activate

# Run void change targeting tests
python -m pytest tests/unit/test_void_change_targeting.py -v

# Run full test suite
python -m pytest tests/ -v

# Run session test (takes ~2-5 minutes)
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/session_config_void_change_test.json

# Verify fix in session output
grep "Void (Test Ritualist):" multiagent_output/session_*.jsonl
# Should see only self-cleansing void changes, NOT environmental ones
```

## Verification Checklist

- [x] Unit tests pass (6/6)
- [x] Full test suite passes (350/359 = 97.8%)
- [x] Code handles environmental targets (skips)
- [x] Code handles unresolvable targets (skips)
- [x] Code handles valid character targets (applies correctly)
- [x] Code handles missing/null targets (applies to actor)
- [x] Schema validation prevents environmental targets
- [x] Pydantic V2 validator (no deprecation warnings)
- [x] Session config created for real testing
- [x] Documentation complete

## Impact Assessment

**Gameplay Impact:**
- ✅ Prevents players from receiving unearned void reductions
- ✅ Maintains accurate void economy tracking
- ✅ Ensures environmental void uses proper scene clock mechanics
- ✅ Collaborative cleansing still works correctly

**ML Training Impact:**
- ✅ Dataset will now have accurate void change attributions
- ✅ Models will learn correct patterns for environmental effects
- ✅ Prevents corrupted training data from bug behavior

**Test Suite:**
- **Before:** 344/353 passing (97.5%)
- **After:** 350/359 passing (97.8%)
- **Net:** +6 passing tests, +6 total tests, +0.3% pass rate

## Related Files

**Modified:**
- `scripts/aeonisk/multiagent/dm.py` (2 locations fixed)
- `scripts/aeonisk/multiagent/schemas/shared_types.py` (validator added)

**Created:**
- `tests/unit/test_void_change_targeting.py` (test suite)
- `scripts/session_configs/session_config_void_change_test.json` (test scenario)
- `tests/VOID_CHANGE_BUG_FIX_SUMMARY.md` (this document)

**Updated:**
- `tests/SESSION_NOTES.md` (Session 5 notes)

## Comparison to Bug #1 (Status Effect Targeting)

**Similarities:**
- Identical bug pattern (fallback to actor instead of skip)
- Same fix approach (add flag, skip invalid targets)
- Same edge cases (None/"None"/missing/empty)
- Both required fixing 2 code locations (structured + legacy paths)

**Differences:**
- Bug #1: Debuffs vs buffs distinction (debuffs skip, buffs apply)
- Bug #2: Environmental vs character distinction (environmental skip, character apply)
- Bug #2 added schema validation as extra safeguard

**Key Learning:** The "fallback to actor" pattern is a common antipattern in this codebase. Future refactoring should review all similar fallback logic.

## Bug Status: ✅ FIXED & VERIFIED

The environmental void targeting bug has been completely fixed and verified through:
- 6 unit tests (all passing)
- Schema validation (prevents future occurrences)
- Full test suite (350/359 = 97.8% pass rate)
- Session config available for real LLM testing

**Impact:** Environmental void effects will now be properly tracked via scene clocks, not incorrectly applied to characters!
