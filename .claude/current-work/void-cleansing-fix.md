# Void Cleansing PC-to-PC Targeting Fix

**Branch:** `void-and-targeting-fixes`
**Date:** 2025-10-29
**Status:** ⏳ In Progress - Testing Required

---

## Problem Statement

**Issue:** PC-to-PC void purification rituals were not reducing the target's void score, even when successful.

**Root Cause:**
- System prevented fallback effects for PC-to-PC actions to avoid friendly fire damage (`dm.py:1811-1816`)
- DM was generating creative narrative twists without including mandatory void reduction markers
- Void reduction requires explicit markers like `⚫ Void (Character Name): -3`, but DM was omitting them
- Result: No void reduction applied despite successful ritual rolls

**Evidence:**
```
23:49:56 DEBUG - Resolved target ID tgt_5mev → character 'Ash Vex' for void cleansing
23:49:56 DEBUG - Targeting PC detected - trusting DM narration entirely (no fallback damage)
```

Action succeeded (margin +1), but DM narration didn't include void reduction marker, so Ash Vex's void remained at 7/10.

---

## Solution Implemented

### 1. Enhanced DM Prompt Instructions

**File:** `prompts/claude/en/dm.yaml`

**Changes:**
- Made void reduction **MANDATORY** for successful void cleansing rituals
- Added explicit PC-to-PC void cleansing section with named marker format
- Emphasized: narrative complications are allowed, but void reduction must still occur
- Used generic placeholder names to avoid overfitting to specific characters

**Example format taught to DM:**
```
⚫ Void (Target Character): -3 (powerful purification despite corrupted resonance)
```

**Key addition:**
```yaml
**CRITICAL - PC-to-PC Void Cleansing:**
When purifying ANOTHER character (PC or NPC), you MUST specify their name in the marker:
  ⚫ Void (Target Character): -3 (powerful purification)
  ⚫ Void (Ally Name): -2 (effective cleansing)

**DO NOT skip void reduction** even if there are narrative complications!
You can describe complications (pain, difficulty, unexpected effects) in the narrative,
but successful rituals ALWAYS reduce void by the appropriate amount.
```

### 2. Enhanced Void Marker Parser

**File:** `outcome_parser.py`

**Changes:**
- Updated `parse_explicit_void_markers()` to extract target character name
- Changed return type: `Tuple[int, List[str], str]` → `Tuple[int, List[str], str, Optional[str]]`
- Regex now captures character name from markers like `⚫ Void (Character Name): -3`
- Stores `void_target_character` in `state_changes` for correct application

**Before:**
```python
void_pattern = r'⚫\s*[Vv]oid(?:\s*\([^)]+\))?:\s*([+-]?\d+)\s*(?:\(([^)]+)\))?'
# Only captured delta and reason
```

**After:**
```python
void_pattern = r'⚫\s*[Vv]oid(?:\s*\(([^)]+)\))?:\s*([+-]?\d+)\s*(?:\(([^)]+)\))?'
# Captures: target_character (group 1), delta (group 2), reason (group 3)
```

### 3. Continued Refactoring from Previous Session

**Completed:** Renamed `target_enemy` → `target` throughout codebase (6 files)
- `action_schema.py` - Field definition
- `player.py` - Parsing logic + prompts (removed prescriptive examples)
- `outcome_parser.py` - All references
- `dm.py` - Combat logic + social actions
- `LOGGING_IMPLEMENTATION.md` - Documentation
- `prompts/shared/markers.yaml` - Marker definitions

**Purpose:** Neutral targeting terminology to avoid biasing AI toward hostile actions

---

## Bug Fix #2: Missing Void Cleansing Instructions in Narration Prompt

**Date:** 2025-10-29 (continued debugging)

**Problem:** Even after adding void cleansing instructions to `dm.yaml`, DM was still not including them in action narrations.

**Root Cause:**
- The void cleansing guidance was added to the `void_mechanics` section
- But `_build_dm_narration_prompt()` only loads the `narration_task` section
- The `narration_task` section had no void cleansing instructions!

**Evidence:**
```
00:07:54 DEBUG - Resolved target ID tgt_u3gh → character 'Ash Vex' for void cleansing
00:07:54 DEBUG - Parsed explicit void marker for 'Ash Vex': -2 (moderate purification)
00:07:54 ERROR - Agent dm_01 handler error: name 'state_changes' is not defined
```

Parser successfully extracted the marker, but crashed trying to store `void_target_character`.

**Solution:**
1. **Added void cleansing instructions to `narration_task` section** (dm.yaml:421-432)
   - Instructions now appear in EVERY action narration prompt
   - Includes margin-to-reduction scaling table
   - Emphasizes: "DO NOT skip void reduction even if there are narrative complications!"

2. **Fixed `parse_void_triggers` return type** (outcome_parser.py:301)
   - Changed from `Tuple[int, List[str], str]` to `Tuple[int, List[str], str, Optional[str]]`
   - Now returns target character name as 4th element
   - Function no longer tries to access undefined `state_changes` variable

3. **Updated all callers** to handle 4-tuple return:
   - `parse_mechanical_effect()` in outcome_parser.py:668
   - `_synthesize_round()` in dm.py:1304

**Files Modified:**
- `prompts/claude/en/dm.yaml` - Added void cleansing to narration_task
- `outcome_parser.py` - Fixed return type and caller handling

## Bug Fix #3: Session Ignoring Config Scenario

**Date:** 2025-10-29 (continued debugging)

**Problem:** Session was generating random combat scenarios instead of using the peaceful purification temple scenario from config file.

**Root Cause:**
- `_generate_ai_scenario()` in dm.py didn't check for `config['scenario']`
- DM always generated new scenarios with LLM, which defaulted to 50% combat emphasis
- Config scenario was completely ignored

**Evidence:**
```
Waiting for scenario generation...
Location: Unknown Location  # Generated, not from config!
```

**Solution:**
1. **Added check for config scenario** (dm.py:130-134)
   - Now checks `if 'scenario' in config and config['scenario']` before generating
   - Calls new `_use_config_scenario()` method

2. **Implemented `_use_config_scenario()` method** (dm.py:536-604)
   - Extracts theme, location, situation, void_level from config
   - Initializes clocks from `initial_clocks` array in config
   - Broadcasts scenario setup without LLM generation
   - Logs scenario to JSONL

3. **Fixed `mechanics.character_states` bug** (dm.py:2226, 2521)
   - Changed from `mechanics.character_states.items()` (doesn't exist)
   - To `session.players` iteration with `player.character_state`

**Files Modified:**
- `dm.py` - Added config scenario check and implementation
- `outcome_parser.py` - Fixed return type and caller handling
- `prompts/claude/en/dm.yaml` - Added void cleansing to narration_task

## Testing Required

### Test Scenario: Collaborative Void Purification Temple

**Config:** `scripts/session_configs/session_config_void_testing.json`

**Setup:**
- Peaceful temple scenario (no combat)
- PCs with high void scores (Riven=6, Ash=7, Thresh=5)
- Free targeting mode enabled (IFF/ROE testing)
- Goal: PCs purify each other through targeted rituals

**Expected Behavior:**
1. Riven targets Ash with void cleansing ritual
2. Roll succeeds with margin (e.g., +12 = GOOD)
3. DM narration includes: `⚫ Void (Ash Vex): -3 (powerful purification)`
4. System parses target character name from marker
5. Void reduction applied to Ash, not Riven
6. Ash's void: 7 → 4

**Verification:**
```bash
# Run session
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py session_configs/session_config_void_testing.json --log-level DEBUG

# Check logs
grep "Resolved target ID.*void cleansing" archive/logs/game_void_testing.log
grep "Void.*Target.*:" archive/logs/game_void_testing.log
grep "void_target_character" archive/logs/game_void_testing.log

# Verify character state changes
grep "Void.*/" archive/logs/game_void_testing.log | grep -A2 "Round"
```

---

## User Preferences (Important for Future Work)

### Freeform Content Over Keyword Detection

**Preference:** Avoid rigid keyword detection and overly specific names/examples in prompts.

**Rationale:**
- Generic examples generalize better to future gameplay
- Overfitting to specific character names (e.g., "Ash Vex", "Thresh") limits model flexibility
- Prefer freeform narrative with structured markers for mechanical effects

**Implementation:**
- Used placeholders: "Target Character", "Ally Name" instead of specific names
- DM interprets intent freeform, but must include mechanical markers for effects
- Balance: Creative narration freedom + mandatory mechanical markers

**Example of good balance:**
```
Narration (freeform): "The purification ritual encounters unexpected resistance
as inverted resonance patterns fight back..."

Mechanics (structured): ⚫ Void (Target Character): -1 (marginal success despite complications)
```

### No Keyword Detection for Intent

**Preference:** DM should interpret actions based on context and narration, not keyword matching.

**Previous Issue:** System used keyword detection for "cooperative intent" which was brittle:
```python
# OLD (removed):
if "heal" in intent or "help" in intent or "cleanse" in intent:
    cooperative = True
```

**Current Approach:**
- DM-authoritative resolution based on narrative understanding
- Fallback effects only for PC→Enemy, not PC→PC
- Trust DM's judgment about friendly/hostile/neutral outcomes

---

## Files Modified

1. **prompts/claude/en/dm.yaml** - Enhanced void cleansing instructions
2. **outcome_parser.py** - Parse target character from void markers
3. **action_schema.py** - Renamed target_enemy → target
4. **player.py** - Updated prompts and parsing
5. **dm.py** - Updated targeting references
6. **LOGGING_IMPLEMENTATION.md** - Documentation fix
7. **prompts/shared/markers.yaml** - Marker definitions

---

## Known Issues

### DM May Still Skip Void Markers

**Risk:** Despite explicit instructions, DM might prioritize narrative creativity over mechanical requirements.

**Mitigation Options:**
1. **Current approach:** Strong prompt instructions with examples
2. **Fallback option:** Add programmatic fallback for PC-to-PC rituals:
   ```python
   # If successful ritual but no void marker detected
   if action_type == 'ritual' and success and target_is_pc:
       if not parsed_void_marker:
           # Generate automatic void reduction based on margin
           void_delta = calculate_void_reduction(margin)
   ```
3. **User preference:** Avoid #2 (no keyword detection), rely on improved prompts

### Void Application Logic

**Status:** ✅ Implemented

Session/mechanics layer now correctly uses `state_changes['void_target_character']` to apply void changes to target character.

## Bug Fix #4: Partial Name Match Failure - Target ID Solution

**Date:** 2025-10-29 (continued debugging)

**Problem:** DM was writing partial character names in void markers (`⚫ Void (Thresh): -3`) when full name is "Thresh Ireveth", causing exact match lookup to fail.

**Root Cause:**
- DM abbreviated character names for brevity
- Character lookup required exact match
- System fell back to applying void to caster (incorrect behavior)

**User Feedback:** "it might be better if the DM uses target id but we display the character name"

**Solution Implemented:**

### 1. Updated DM Prompt to Use Target IDs (dm.yaml:421-435)
```yaml
If cleansing ANOTHER character and a target ID is provided{target_id_instruction}, use the target ID in the marker:
⚫ Void ({target_id}): -3 (powerful purification)

If no target ID is provided, you may use the character's name:
⚫ Void (Target Character Name): -3 (powerful purification)
```

### 2. Pass Target ID to DM Prompt (dm.py:3402-3405, 2975-2980)
```python
# Extract target_id from action if present
target_id = ""
if action and action.get('target') and action['target'].startswith('tgt_'):
    target_id = action['target']

# Add to prompt variables
variables = {
    "void_level": str(void_level),
    "outcome_guidance": outcome_guidance,
    "target_id": target_id if target_id else "",
    "target_id_instruction": f" (target ID: {target_id})" if target_id else ""
}
```

### 3. Enhanced Character Lookup to Resolve Target IDs (dm.py:2297-2341, 2594-2638)
```python
target_identifier = state_changes.get('void_target_character')
if target_identifier:
    if target_identifier.startswith('tgt_'):
        # It's a target ID - resolve it
        target_id_mapper = self.shared_state.get_target_id_mapper()
        target_entity = target_id_mapper.resolve_target(target_identifier)

        if target_entity and hasattr(target_entity, 'agent_id'):
            target_player_id = target_entity.agent_id
            target_character_name = target_entity.character_state.name
    else:
        # It's a character name - try partial match
        for player in self.shared_state.player_agents:
            char_name = player.character_state.name
            if char_name == target_identifier or target_identifier in char_name:
                target_player_id = player.agent_id
                target_character_name = char_name
                break
```

**Benefits:**
- Unambiguous targeting using target IDs (tgt_xxxx)
- Fallback to partial name matching if DM uses names
- Human-readable display (character names shown, IDs used internally)
- No more targeting failures due to name abbreviations

**Files Modified:**
- `prompts/claude/en/dm.yaml` - Added target ID instructions
- `dm.py` - Pass target ID to prompt, resolve target IDs in character lookup

---

## Next Steps

1. ✅ **Run test session** with void purification scenario (IN PROGRESS)
2. **Verify DM includes void markers with target IDs** in successful PC-to-PC rituals
3. **Check void scores update correctly** for target character (not caster)
4. **Document results** in this file

---

## Context for New Sessions

**Quick summary for future AI assistants:**

We fixed PC-to-PC void cleansing by:
1. Making DM prompt instructions mandatory for void markers
2. Teaching parser to extract target character names from markers
3. Renamed target_enemy → target for neutral terminology
4. User prefers freeform narrative + structured markers over keyword detection

**To continue debugging:**
- Run test session and check if void markers appear in DM narration
- Verify parsed markers target correct character
- Check session.py applies void changes to target (not caster)
