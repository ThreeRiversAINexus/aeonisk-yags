# Next Session Prompt - Environmental Void Level Updates

## Context

We just finished fixing Bug #2 (environmental void targeting) and discovered a design gap: **environmental void_level can't currently change during a session**.

**Current state:**
- `scenario.void_level` is set in config, never changes
- Players affect environment via scene clocks
- No mechanism to update void_level when story advances

**Read these docs first:**
- `tests/ENVIRONMENTAL_VOID_DESIGN.md` - Full design documentation
- `tests/SESSION_NOTES.md` - Recent work history
- `CLAUDE.md` - Project philosophy and patterns

## The Task: Enable void_level Updates During Story Advancement

### Goal

Allow DM to update environmental void_level when advancing the story (e.g., when purification clocks complete).

### Recommended Approach

**Phase 1: Add optional `new_void_level` field to story advancement**

1. **Update schema** (`scripts/aeonisk/multiagent/schemas/story_events.py`):
   ```python
   class AdvanceStory(BaseModel):
       new_location: str
       situation: str
       new_void_level: Optional[int] = Field(None, ge=0, le=10, description="New environmental void level (0-10), if changed")
       new_clocks: List[NewClock] = []
   ```

2. **Process updates** in story advancement handler:
   - When DM includes `new_void_level`, update scenario state
   - Log the change for visibility
   - Persist to new scenario state

3. **Update DM prompt** with guidance:
   - When to reduce void_level (major purification achievements, area cleansed)
   - When to increase void_level (corruption spreading, containment failure)
   - Examples of story advancement with void_level changes

### Test-Driven Development Workflow

**Our proven methodology:**

1. **Write unit tests first** (TDD)
   - Test story advancement with new_void_level specified
   - Test story advancement without new_void_level (unchanged)
   - Test validation (void_level bounds 0-10)

2. **Implement the feature**
   - Update schema
   - Update story advancement handler
   - Update DM prompt

3. **Create contrived session config** (1-2 rounds)
   - Setup: High void_level (8), purification clock
   - Player completes purification clock
   - DM advances story with new_void_level (3)

4. **Run actual game session**
   - Generate logs in `multiagent_output/` and `archive/logs/`
   - Review DM behavior

5. **Evaluate logs**
   - ✅ If correct: Convert to test fixture in `tests/fixtures/sessions/`
   - ❌ If incorrect: Iterate on tests/code

6. **Update documentation**
   - `tests/SESSION_NOTES.md` - Add session entry
   - Commit with clear message

### Success Criteria

- [ ] `AdvanceStory` schema has `new_void_level` field
- [ ] Story advancement updates scenario.void_level when specified
- [ ] Unit tests pass (story advancement with/without void_level update)
- [ ] DM prompt includes void_level update guidance
- [ ] Test session config created and run
- [ ] Generated logs show correct behavior
- [ ] Test fixture created from session logs
- [ ] Documentation updated

### Test Config Template

```json
{
  "session_name": "environmental_void_story_advancement_test",
  "max_turns": 2,
  "scenario": {
    "theme": "Void Cleansing Mission",
    "location": "Corrupted Research Station",
    "situation": "The station is saturated with void corruption (8/10). Your mission is to purify this sector and make it safe again.",
    "void_level": 8
  },
  "mission_objectives": [
    {
      "description": "Purify the station's void corruption",
      "type": "ritual",
      "required": true
    }
  ]
}
```

**Expected flow:**
- Round 1: Player performs environmental cleansing, advances "Purification" clock
- Round 2: Clock completes (10/10), DM advances story
  - New location: "Cleansed Research Bay"
  - `new_void_level: 3` (down from 8)
  - Verify: scenario.void_level actually updates

### Key Files to Modify

1. `scripts/aeonisk/multiagent/schemas/story_events.py`
   - Add `new_void_level` field to `AdvanceStory`

2. `scripts/aeonisk/multiagent/dm.py`
   - Update story advancement handler to process `new_void_level`
   - Look for `[ADVANCE_STORY]` processing logic

3. `scripts/aeonisk/multiagent/prompts/claude/en/dm.yaml`
   - Add guidance on when/how to update void_level during story advancement

4. `tests/unit/test_story_advancement.py` (create if needed)
   - Unit tests for void_level updates

### Notes

- **Philosophy:** Environmental void changes via story advancement, not individual actions
- **Clocks:** Players influence via clocks, DM controls when void_level changes
- **Optional:** DM can choose NOT to update void_level (carries over unchanged)
- **Validation:** Ensure 0-10 bounds via Pydantic Field validator

### Questions to Consider

1. Should void_level auto-update from certain clock types? (Phase 2 - probably not initially)
2. Should we track void_level history? (Probably not needed)
3. How often should void_level realistically change? (Rarely - major story beats only)

### Time Estimate

**Total: 2-3 hours**
- Schema + handler: 45 min
- Unit tests: 30 min
- DM prompt updates: 30 min
- Test config + session run: 30 min
- Fixture creation + docs: 30 min

---

**Good luck! Follow the test-driven workflow and you'll knock this out quickly.** 🎯
