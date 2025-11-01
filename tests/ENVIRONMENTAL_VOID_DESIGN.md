# Environmental Void Design Documentation

## Current State (As of 2025-10-31)

### What Environmental Void IS

**`scenario.void_level`** (0-10 scale) represents ambient void corruption in a location:
- Narrative setting/atmosphere ("This station is soaked in void corruption")
- Potential Eye of Breach trigger (when env void reaches high levels)
- Background hazard level (sets tone, may affect ritual difficulty in future)

**Key insight:** Environmental void is **setting/backdrop**, not **player currency**.

### What Environmental Void IS NOT

- ❌ NOT directly targetable by players via `VoidChange`
- ❌ NOT reduced by individual player actions
- ❌ NOT a player-actionable resource like character void

**Schema validation explicitly rejects:**
- `VoidChange(character_name="Environmental Void", ...)`
- Any environmental keywords: "environment", "area", "ambient", "chamber", etc.

### How Players Affect Environmental Void

**Players interact with environmental void via SCENE CLOCKS:**

**Example flow:**
```
Initial state: void_level: 8 (heavy corruption)

Player action: "I perform environmental cleansing ritual"
DM response:
  - Narration: "You create a bubble of purified space..."
  - clock_updates=[ClockUpdate(clock_name="Purification Progress", ticks=3)]
  - NO void_changes (environmental effects use clocks, not VoidChange)

Clock completes: "Purification Progress" reaches 10/10
DM: [ADVANCE_STORY] → New scenario state
  - New location: "Cleansed Inner Sanctum"
  - void_level: 3 (reduced from 8 via story advancement)
  - New clocks, new challenges
```

**The pattern:**
1. Players perform environmental rituals
2. DM advances clocks (Purification, Containment, Stabilization, etc.)
3. Clocks complete → DM advances story
4. Story advancement changes void_level in new scenario

### Design Philosophy

**Environmental void changes via story progression, not individual actions:**
- ✅ Clocks track player progress toward environmental change
- ✅ Story advancement (when clocks complete) updates void_level
- ✅ Maintains narrative weight (can't just "fix" decades of corruption in one ritual)
- ✅ DM controls pacing of environmental changes

**This aligns with:**
- Clocks as player-influenceable progress tracking
- Story advancement as major scenario state changes
- No keyword detection (environmental effects use structured clock updates)

## The Problem (To Be Addressed)

### Current Gap

**Issue:** `void_level` is currently **write-once** - set in scenario config, never changes during session.

**What's missing:**
1. **No mechanism to update void_level during story advancement**
   - DM can advance story with `[ADVANCE_STORY]`
   - But void_level doesn't update automatically
   - No way to specify "new void_level" in story advancement

2. **No guidance on when/how environmental void should change**
   - Should it change automatically when purification clocks complete?
   - Should DM manually specify new void_level in advancement?
   - What's the threshold for change?

3. **Eye of Breach environmental triggers unclear**
   - Does high environmental void (8+) spawn Eye of Breach?
   - Or only character void 10?
   - Current code logged `env=8` trigger - is that intended?

### What Needs Implementation

**Option A: Manual Story Advancement with void_level**
- DM specifies new void_level when using `[ADVANCE_STORY]`
- Example: `[ADVANCE_STORY: void_level=3]`
- Requires parsing story advancement markers to extract void_level

**Option B: Automatic void_level Updates from Clocks**
- When "Purification" type clock completes → reduce void_level by X
- When "Corruption Spreading" type clock completes → increase void_level by X
- Requires clock → void_level mapping logic

**Option C: Hybrid (Recommended)**
- Clocks track progress (as they do now)
- Story advancement CAN specify new void_level (optional)
- If not specified, void_level carries over to new scenario
- DM decides when environmental changes warrant void_level update

## Recommended Approach

### Phase 1: Story Advancement with void_level (Simple)

**Allow DM to specify new void_level in story advancement:**

```python
# In StoryEvents schema
class AdvanceStory(BaseModel):
    new_location: str
    situation: str
    new_void_level: Optional[int] = None  # NEW: Allow void_level updates
    new_clocks: List[NewClock] = []
```

**When processing story advancement:**
```python
if story_event.new_void_level is not None:
    scenario.void_level = story_event.new_void_level
    logger.info(f"Environmental void updated: {old_level} → {story_event.new_void_level}")
```

**Benefits:**
- ✅ Simple implementation
- ✅ DM has explicit control
- ✅ No magic/automatic behavior
- ✅ Aligns with existing story advancement system

### Phase 2: DM Prompt Guidance (Later)

**Add to DM prompt:**
- When to consider reducing void_level (major purification achievements)
- When to consider increasing void_level (corruption spreading, ritual failures)
- Suggested void_level changes based on clock completions

### Phase 3: Automatic Clock → void_level Mapping (Optional)

**If pattern emerges, automate it:**
- Certain clock types auto-adjust void_level on completion
- DM can override via explicit new_void_level
- Requires careful design to avoid surprise behavior

## Testing Strategy

### Test Cases Needed

1. **Self-cleansing ritual** (void_target_character=null)
   - Config: Player with void=7, performs self-cleansing
   - Expected: Player void reduces, environmental void unchanged

2. **Collaborative cleansing** (void_target_character="Ally Name")
   - Config: Two players, one cleanses the other
   - Expected: Target's void reduces, environmental void unchanged

3. **Environmental cleansing via clocks** (no void_changes)
   - Config: Environmental void=8, player cleanses environment
   - Expected: Clock advances, NO VoidChange, environmental void unchanged (until story advancement)

4. **Story advancement with void_level change** (future)
   - Config: Clock completes, DM advances story with new_void_level
   - Expected: Environmental void_level updates to new value

### Methodology

**Test-Driven Development Flow:**
1. Write unit tests for desired behavior
2. Fix bugs as found
3. Create contrived session configs (1-round scenarios)
4. Run actual game sessions to generate logs
5. Review logs - if behavior is correct, convert to test fixtures
6. If incorrect, iterate on tests/code

**Fixture Management:**
- Keep fixtures in `tests/fixtures/sessions/`
- Clean fixtures = regression tests
- Buggy fixtures = documentation of issues found

## Current Status

**Completed:**
- ✅ Bug #2 fixed: Environmental void targeting blocked
- ✅ Schema validation rejects environmental keywords
- ✅ Runtime keyword detection removed
- ✅ DM prompt updated with environmental void guidance
- ✅ Philosophy documented in CLAUDE.md

**Pending:**
- ⏸️ Mechanism for updating void_level during story advancement
- ⏸️ DM guidance on when to change environmental void
- ⏸️ Test fixtures for environmental cleansing scenarios

## Related Files

- `scripts/aeonisk/multiagent/dm.py` - Void change application (lines 2778-2856, 3197-3275)
- `scripts/aeonisk/multiagent/schemas/shared_types.py` - VoidChange model with validator
- `scripts/aeonisk/multiagent/schemas/story_events.py` - AdvanceStory schema (to be updated)
- `scripts/aeonisk/multiagent/prompts/claude/en/dm.yaml` - DM guidance (lines 72-81)
- `CLAUDE.md` - Design philosophy (lines 82-105)
- `tests/VOID_CHANGE_BUG_FIX_SUMMARY.md` - Bug #2 documentation

## Next Steps

See `tests/NEXT_SESSION_ENVIRONMENTAL_VOID_PROMPT.md` for detailed implementation plan.
