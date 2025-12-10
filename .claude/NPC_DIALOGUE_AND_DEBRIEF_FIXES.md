# NPC Dialogue Target None & Debrief llm_config Fixes

**Date**: 2025-12-05
**Branch**: bulk-generation (fixes will be merged to main)

## Issues Fixed

### Issue 1: NPC Dialogue with No Target Shows "None" in Narration

**Symptom**: When an NPC performs a dialogue action with no specific target (e.g., addressing everyone in a room), the DM narration would reference "None" as if it were a character name.

**Example**:
```
Cranehand Jax pivots, fingers resting on the maintenance-hatch lever, eyes hooded
with wary calculation as he looks past the empty doorway and addresses 'None'—
naming absence like a witness.
```

**Root Cause**:
- Location: `dm.py:4454`
- Code set `target_display = 'None'` (string literal) when `target` was `None`
- This string was then interpolated into the LLM prompt as `**Target:** None`
- The DM LLM interpreted "None" as a character name or entity

**Fix**:
- Changed `target_display = 'None'` to `target_display = 'no specific target'`
- Now the prompt shows `**Target:** no specific target`, which the DM correctly interprets as a general address

**Test Coverage**:
- `tests/unit/test_npc_dialogue_target_none.py`
- Documents expected behavior (no literal "None" string in prompts)

---

### Issue 2: Mission Debrief Generation Crashes with AttributeError

**Symptom**: When generating mission debriefs at session end, the system crashes with:
```
[Debrief generation failed: 'SelfPlayingSession' object has no attribute 'llm_config']
```

**Root Cause**:
- Location: `session.py:3080`
- Code attempted to access `self.llm_config.get('temperature', 1.0)`
- `SelfPlayingSession` does not have an `llm_config` attribute
- Only individual agents (players, enemies, DM) have `llm_config`

**Fix**:
- Changed `self.llm_config.get('temperature', 1.0)` to `player.llm_config.get('temperature', 1.0)`
- Now correctly uses the player's LLM configuration instead of a non-existent session config

**Context**:
```python
# Before (line 3080):
provider_config = LLMConfig(
    provider=player.llm_config.get('provider', 'anthropic'),
    model=player.llm_config.get('model', 'claude-sonnet-4-5'),
    temperature=self.llm_config.get('temperature', 1.0),  # ❌ AttributeError
    max_tokens=250
)

# After (line 3080):
provider_config = LLMConfig(
    provider=player.llm_config.get('provider', 'anthropic'),
    model=player.llm_config.get('model', 'claude-sonnet-4-5'),
    temperature=player.llm_config.get('temperature', 1.0),  # ✅ Correct
    max_tokens=250
)
```

**Test Coverage**:
- `tests/unit/test_session_debrief_llm_config.py`
- Documents architecture constraint (session has no llm_config)

---

## Files Modified

1. **scripts/aeonisk/multiagent/dm.py** (line 4454)
   - Changed NPC dialogue target display from 'None' to 'no specific target'

2. **scripts/aeonisk/multiagent/session.py** (line 3080)
   - Fixed debrief temperature to use player.llm_config instead of self.llm_config

3. **tests/unit/test_npc_dialogue_target_none.py** (new)
   - Regression test for NPC dialogue target display

4. **tests/unit/test_session_debrief_llm_config.py** (new)
   - Regression test for debrief llm_config usage

---

## Test Results

**Before fixes**:
- Issue 1: DM would narrate NPCs addressing "None" as a character
- Issue 2: Debrief generation raised AttributeError and failed

**After fixes**:
- All 633 unit tests pass (NPC and session tests)
- 60 tests skipped (character library tests - expected)
- No regressions introduced

**Test command**:
```bash
python -m pytest tests/unit/test_npc*.py tests/unit/test_session*.py -v
```

---

## Impact

### Issue 1 Impact
- **Before**: NPCs with target=None produced weird/confusing narration
- **After**: NPCs addressing general area now produce natural narration
- **ML training**: Cleaner training data (no more "addressing None" in JSONL logs)

### Issue 2 Impact
- **Before**: Mission debriefs always crashed for all players
- **After**: Mission debriefs generate successfully
- **User experience**: Players now see end-of-mission character reflections

---

## Verification

To verify these fixes in a live session:

**Test Issue 1 (NPC Dialogue)**:
1. Run a session with NPCs that have dialogue actions
2. Check that NPCs addressing no specific target produce natural narration
3. Verify JSONL logs don't contain "Target: None" in NPC action prompts

**Test Issue 2 (Debrief)**:
1. Run a session to completion
2. Verify mission debrief section appears without errors
3. Check that each player character gets a debrief statement

---

## Design Philosophy Alignment

Both fixes align with core design principles:

1. **Structured Output Over Keyword Detection**:
   - Issue 1 fix prevents DM from keyword-matching "None" as a name
   - Prompts now use clear descriptive phrases

2. **Per-Agent Configuration**:
   - Issue 2 fix respects the architecture where llm_config is per-agent
   - Session object remains stateless regarding LLM configuration

3. **ML Training Data Quality**:
   - Issue 1 fix improves JSONL log quality (no more weird "None" references)
   - Issue 2 fix ensures debriefs are actually logged for training

---

## Related Documentation

- **NPC System**: `.claude/NPC_SYSTEM_DESIGN.md` (if exists)
- **Session Architecture**: `scripts/aeonisk/multiagent/session.py` docstrings
- **ML Logging**: `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`
