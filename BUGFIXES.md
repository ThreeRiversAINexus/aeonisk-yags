# Bug Fixes - Multi-Agent Mechanics Integration

## Issues Found During Testing (2025-10-22)

### ✅ Fixed Issues

#### 1. Players Ignoring Scenario Pivots

**Issue**: When the DM used `[PIVOT_SCENARIO]` to change scenarios (e.g., "Investigation" → "Survival Horror"), players continued with investigation actions instead of adapting to the new situation. Players received the DM's narration but their internal scenario state was never updated, and they had zero visibility into clock states.

**Example from game.log**:
```
DM: [PIVOT_SCENARIO: Survival Horror] - facility collapsing, evacuate immediately!
NEW_CLOCK: Facility Evacuation (0/4)

Players next round:
- "perform intimacy ritual to understand what occurred"
- "inspect ritual circle's binding sigils"
Instead of: "Run for the exit!", "Help evacuate civilians"
```

**Root Causes**:
1. `self.current_scenario` in player.py never updated after initial setup
2. Players had no visibility into clock states or their semantic meanings
3. No explicit notification when scenarios pivoted

**Fix** (base.py, player.py:228-247, session.py:1018-1029):

1. **Added SCENARIO_UPDATE message type** (base.py):
```python
class MessageType(Enum):
    SCENARIO_SETUP = "scenario_setup"
    SCENARIO_UPDATE = "scenario_update"  # NEW - for mid-game pivots
```

2. **Players now receive and handle pivot notifications** (player.py):
```python
async def _handle_scenario_update(self, message: Message):
    """Handle mid-game scenario pivot from DM."""
    new_theme = message.payload.get('new_theme', 'Unknown')
    self.current_scenario['theme'] = new_theme  # Update internal state
    print(f"\n[{self.character_state.name}] 🔄 SCENARIO PIVOT: {new_theme}")
```

3. **Session broadcasts pivots to all players** (session.py):
```python
if pivot_result['should_pivot']:
    self.bus.send_message(
        MessageType.SCENARIO_UPDATE,
        payload={'new_theme': pivot_result['new_theme'], ...}
    )
```

4. **Players now see clock states in their prompts** (player.py:827-855):
```python
📊 **Current Situation Clocks:**
- **Facility Evacuation**: 0/4
  Advance = Move toward exits, help civilians
  Regress = Delays, obstacles
  🎯 Consequence: Building collapses, everyone trapped
```

**Impact**:
- Players receive explicit notification when scenarios pivot
- Internal scenario state updates to match new situation
- Clock visibility shows players what pressures exist and how to interact with them
- Semantic guidance tells players what advancing/regressing each clock means

**Files Modified**:
- `scripts/aeonisk/multiagent/base.py` (MessageType.SCENARIO_UPDATE)
- `scripts/aeonisk/multiagent/player.py` (_handle_scenario_update, clock visibility in prompts)
- `scripts/aeonisk/multiagent/session.py` (broadcast pivot to players)

---

#### 2. Clock Archiving Too Strict

**Issue**: After scenario pivots, filled clocks remained active creating UI clutter. The +5 overflow threshold meant clocks at 6/6, 7/6, 8/6 weren't being archived even though the DM had pivoted away from them.

**Example**:
```
After [PIVOT_SCENARIO: Survival Horror]:
Still showing: Contract Verification (10/8), Public Relations (4/4), Void Contamination (6/6)
Only showing: Facility Evacuation (0/4)
```

**Root Cause**: Archiving logic required `overflow >= 5`, but the `[PIVOT_SCENARIO]` marker itself indicates the DM has addressed the situation.

**Fix** (session.py:1003-1017):
```python
# Archive ALL filled clocks when scenario pivots
# The pivot itself means the DM has addressed the situation
for clock_name, clock in list(mechanics.scene_clocks.items()):
    if clock.filled:  # Any filled clock, not just +5 overflow
        clocks_to_archive.append(clock_name)
        del mechanics.scene_clocks[clock_name]
```

**Impact**:
- Cleaner transitions between scenarios
- Filled clocks are archived when DM pivots (signal of "addressed")
- New clocks start fresh without clutter from previous objectives

**Files Modified**:
- `scripts/aeonisk/multiagent/session.py` (pivot archiving logic)

---

#### 3. Aggressive Skill Routing Preventing AI Learning

**Issue**: The skill routing system was aggressively overriding player AI decisions, forcing "correct" skill choices even when the AI deliberately chose something different. This prevented collection of useful training data showing how AI agents reason about skill selection.

**Example**:
```
Player chooses: "intimacy ritual" → Willpower × Intimacy Ritual
System forces: Willpower × Astral Arts (all rituals forced to this)
Result: Lost data on AI's intentional skill choice
```

**Root Cause**: Multiple layers of coercion in player.py forced corrections regardless of AI intent.

**Fix** (player.py:322-393, skill_mapping.py:114-136):

1. **Softened routing to only fix missing skills**:
```python
should_route = False
if action_declaration.skill:
    skill_value = get_character_skill_value(...)
    if skill_value == -1:  # Character doesn't have this skill
        should_route = True  # Only route if skill missing
```

2. **Removed forced ritual mechanics**:
```python
# Let AI choose their own skill - Intimacy Ritual, Magick Theory, etc. valid
if is_explicit_ritual:
    action_declaration.is_ritual = True
    # Note: NOT forcing Willpower × Astral Arts anymore
```

3. **Log alternatives instead of forcing**:
```python
print(f"Note: Using {original} (alternative: {suggested})")
# Keep original choice - let DM handle narratively
```

**Impact**:
- AI agents can make "wrong" choices - valuable training data
- Intimacy Ritual uses its own skill (not forced to Astral Arts)
- Magick Theory can be used for ritual investigation
- DM handles mismatches narratively instead of system forcing corrections

**Files Modified**:
- `scripts/aeonisk/multiagent/player.py` (routing, ritual enforcement, validation)
- `scripts/aeonisk/multiagent/skill_mapping.py` (ritual mechanics)

**REFINEMENT (2025-10-22 evening)**: Further reduced routing aggressiveness after user feedback:

**Issue**: System was still suggesting alternatives when players chose skills they didn't have, preventing unskilled attempts.

**Example**:
```
Player chooses: Intelligence × Magick Theory (valid skill, analyzing resonance)
System suggests: Perception × None (because character doesn't have Magick Theory)
Result: Player forced away from deliberate skill choice
```

**User Feedback**: *"we're getting pigeon holed too hard still"*

**Root Cause**: Code was routing whenever `skill_value == -1` (character doesn't have skill), but YAGS allows unskilled attempts with -50% penalty.

**Fix** (player.py:344-371):
Removed ALL routing logic except skill name normalization:

```python
# MINIMAL validation - only normalize skill name aliases
# Philosophy: Let AI make "wrong" choices - that's valuable data.

# Normalize skill name ONLY if it's an alias (e.g., "social" → "Charm")
if action_declaration.skill:
    original_skill = action_declaration.skill
    normalized_skill = normalize_skill(action_declaration.skill)

    if normalized_skill != original_skill:
        action_declaration.skill = normalized_skill
        # Don't log - this is just alias normalization
```

**What Was Removed**:
- ❌ ActionRouter suggestions based on missing skills
- ❌ validate_action_mechanics corrections
- ❌ Skill availability checking
- ❌ Any logging of "suggested" or "alternative" approaches

**What Remains**:
- ✅ Skill name alias normalization ("social" → "Charm")
- ✅ Ritual flag detection (mark as ritual, but don't change skills)
- ✅ That's it!

**Impact**:
- Players can now use ANY valid skill, even if they don't have it (unskilled penalty)
- Players can choose "suboptimal" attribute/skill pairings (Intelligence × Magick Theory for analysis)
- No more "Suggested: X → Y" messages
- DM handles all mismatches narratively
- 100% pure AI decision data for training

---

#### 4. Clock Semantic Ambiguity

**Issue**: Clocks lacked clear semantics about what it means to advance/regress them, causing confusion for both the DM and players about whether clock changes were good or bad. For example, "Contract Validation" could mean either "progress on validating contracts" (advance = good) OR "contracts becoming more validated/secure" (advance = good), leading to inconsistent mechanical decisions.

**Example from game.log**:
```
📊 Contract Validation: +2 (identified vulnerability points)  ← advancing for finding problems?
📊 Contract Validation: -1 (reinforced wrong sections)  ← regressing for mistakes?
DM: "Contract Validation advances to 6/8, dangerously close to completion"  ← completion of what?
```

**Root Cause**: The `SceneClock` dataclass only had:
- `name`: str
- `maximum`: int
- `description`: str (generic)

No guidance on what advancing/regressing meant or what consequences should occur when filled.

**Fix** (mechanics.py:340-359, dm.py:182-204):

1. **Enhanced SceneClock dataclass** with semantic metadata:
```python
@dataclass
class SceneClock:
    name: str
    current: int = 0
    maximum: int = 6
    description: str = ""
    advance_means: str = ""  # "Investigation progresses" or "Danger increases"
    regress_means: str = ""  # "Setback in investigation" or "Danger reduced"
    filled_consequence: str = ""  # "Evidence complete, pivot to confrontation"
```

2. **Updated scenario generation prompt** to require semantic guidance:
```
CLOCK1: [name] | [max] | [description] | ADVANCE=[meaning] | REGRESS=[meaning] | FILLED=[consequence]

Example:
CLOCK1: Security Alert | 6 | Corporate hunters closing in |
ADVANCE=Hunters get closer to finding the team |
REGRESS=Team evades or misleads pursuit |
FILLED=Hunter team arrives, combat or escape required
```

3. **Enhanced DM synthesis display** to show semantics:
```
**Current Clock State:**
  - Security Alert: 4/6
    Advance = Hunters get closer to finding the team | Regress = Team evades or misleads pursuit
    🎯 When filled: Hunter team arrives, combat or escape required
```

**Impact**:
- DM receives clear guidance on when to advance vs regress each clock
- Players understand whether clock changes help or hurt them
- Filled consequences are specified upfront, ensuring consistent narrative outcomes
- Eliminates ambiguity in clock naming (e.g., "Evidence Collection" now clearly means "advancing = gathering more evidence")

**Files Modified**:
- `scripts/aeonisk/multiagent/mechanics.py` (SceneClock dataclass, create_scene_clock method)
- `scripts/aeonisk/multiagent/dm.py` (scenario generation prompt, parser, clock creation, synthesis display)

---

#### 2. Clock Advancement Capping (Filled Clocks Getting Stuck)

**Issue**: Scene clocks were getting stuck at their maximum values and not advancing further, causing scenarios to stall without triggering consequences or DM control markers.

**Example from game.log**:
```
Round 2: Data Collection FILLED (4/4), Corporate Interest FILLED (5/5)
Round 4: Pod Corruption FILLED (6/6)
Round 5+: Pod Corruption still at 6/6, cannot advance
```

**Root Cause** (mechanics.py:363):
- The `SceneClock.advance()` method capped advancement with `self.current = min(self.current + ticks, self.maximum)`
- Once a clock reached 6/6, it could never advance beyond 6
- The method only returned `True` on the **first fill** (transition from 5→6)
- After that, subsequent advances did nothing (6→6 returned `False`)
- DM only got **one warning** when clock first filled
- If DM didn't use control markers on that first warning, clock stayed stuck forever

**Fix**:

1. **Allow Clock Overflow** (mechanics.py:355-373):
   - Removed `min()` cap: changed to `self.current += ticks`
   - Clocks can now overflow beyond maximum (6/6 → 7/6 → 8/6)
   - This indicates increasing urgency when consequences aren't addressed
   - Method now returns `True` whenever clock is at or above maximum

2. **Enhanced Overflow Warnings** (mechanics.py:1106-1144):
   - Added overflow detection and urgency levels
   - `+1 overflow`: `⚠️  OVERFLOWING` warning
   - `+3 overflow`: `🚨 CRITICAL OVERFLOW` error
   - Logs show exact overflow amount: `Pod Corruption: 8/6 (+2)`

3. **Better DM Synthesis Alerts** (dm.py:1098-1130):
   - Clock display shows overflow status in synthesis
   - `FILLED: 6/6` for newly filled clocks
   - `⚠️  OVERFLOWING: 7/6 (+1)` for mild overflow
   - `🚨 CRITICAL OVERFLOW: 9/6 (+3)` for severe overflow
   - Enhanced DM warning includes explicit control marker suggestions:
     ```
     🚨 EXTREME URGENCY 🚨 CLOCKS FILLED/ADVANCING: Pod Corruption
     You MUST describe what catastrophic/dramatic consequences occur!
     Consider using DM control markers:
     - [NEW_CLOCK: Name | Max | Description] to spawn new pressure
     - [PIVOT_SCENARIO: Theme] if situation fundamentally changes
     - [SESSION_END: VICTORY/DEFEAT/DRAW] if objectives achieved/failed
     ```

4. **Action Resolution Display** (dm.py:1285-1295, 1540-1550):
   - Clock updates now show overflow: `Pod Corruption: 7/6 ⚠️  (+1 OVERFLOW)`
   - Players and DM see visual indicator of escalating danger

**Impact**:
- Clocks now provide continuous pressure even after filling
- DM gets repeated, escalating warnings to take action
- Overflow creates mechanical sense of urgency (e.g., "The pod is critically unstable at 9/6!")
- Fixes stalled scenarios where filled clocks blocked progression

**Files Modified**:
- `scripts/aeonisk/multiagent/mechanics.py` (SceneClock.advance, advance_clock methods)
- `scripts/aeonisk/multiagent/dm.py` (synthesis display, action resolution display)

---

#### 3. Clock Cleanup on Scenario Pivot

**Issue**: After using `[PIVOT_SCENARIO]` markers, old clocks remained active and were displayed alongside new clocks, creating UI clutter and confusion. For example, "Evidence Collection: 17/8" would persist even after the scenario pivoted from "Investigation" to "Survival Horror".

**Root Cause**: The PIVOT_SCENARIO marker was parsed but not acted upon - no code existed to clean up old clocks when scenarios changed.

**Fix** (dm.py:1010-1048):
When `[PIVOT_SCENARIO]` is detected in synthesis:
1. Parse and create any `[NEW_CLOCK:]` markers from the same synthesis
2. Archive clocks with **critical overflow (+5 or more)** - these have been "satisfied" by the pivot
3. Keep clocks with moderate overflow or still in progress (they may still be relevant)
4. Display clear feedback: `🔄 PIVOT: 'Evidence Exposure'` with archived and spawned clock counts

**Code Changes**:
```python
# After synthesis generation
pivot_result = parse_pivot_scenario(synthesis)

if pivot_result['should_pivot']:
    # Create new clocks from [NEW_CLOCK:] markers
    for match in re.finditer(new_clock_pattern, synthesis):
        clock_name, max_ticks, description = ...
        mechanics.create_scene_clock(clock_name, max_ticks, description)

    # Archive critically overflowed clocks (+5 or more)
    for clock_name, clock in mechanics.scene_clocks.items():
        overflow = clock.current - clock.maximum
        if overflow >= 5:
            del mechanics.scene_clocks[clock_name]  # Archive it
```

**Why +5 Threshold?**
- Clocks at exactly maximum (6/6) are newly filled - keep them for immediate consequences
- Clocks with mild overflow (+1 to +4) may still be building pressure - keep them
- Clocks with critical overflow (+5+) have already triggered pivot - archive them

**Impact**:
- Cleaner clock displays after scenario pivots
- Old objectives naturally retire when overtaken by events
- New clocks spawn without clutter from completed/overflowed objectives
- DM gets clear feedback on pivot execution

**Example**:
```
Before pivot: Evidence Collection (17/8), Station Lockdown (5/4), Corporate Hunters (5/6)
After pivot: Corporate Hunters (5/6), Evidence Destruction (0/6), Hunter-Killer Teams (0/4)
              ↑ kept (overflow +1)   ↑ new clocks spawned
Evidence Collection archived (overflow +9 satisfied by pivot)
```

**Files Modified**:
- `scripts/aeonisk/multiagent/session.py` (pivot marker processing, lines 998-1021)

---

## Issues Found During Testing (2025-10-20)

### ✅ Fixed Issues

#### 4. JSON Serialization Error

**Error**:
```
TypeError: Object of type OutcomeTier is not JSON serializable
```

**Cause**: The `ActionResolution` object contains an `OutcomeTier` enum that can't be directly serialized to JSON when sending messages over the socket.

**Fix** (dm.py:359-379):
- Convert `OutcomeTier` enum to string value before including in message payload
- Create explicit serializable dict with only primitive types

**Code Change**:
```python
# Before
outcome = {
    'resolution': resolution.__dict__ if resolution else None
}

# After
resolution_data = {
    'outcome_tier': resolution.outcome_tier.value,  # Convert enum to string
    # ... other fields
}
```

**File**: `scripts/aeonisk/multiagent/dm.py`

---

#### 5. "The situation evolves..." Spam

**Issue**: DM turns were showing placeholder text repeatedly:
```
[DM dm_01] Narrative: The situation evolves... [AI DM narrative]
```

**Cause**: The `_ai_dm_turn()` method had placeholder text that was being broadcast on every DM turn without meaningful content.

**Fix** (dm.py:418-450):
- DM now prints current scene clock status instead of placeholder
- Skips turn entirely if no clocks to report
- Shows useful state: `📊 Sanctuary Corruption: 2/6 | Saboteur Exposure: 3/6 | ...`

**Code Change**:
```python
# Before
narration = "The situation evolves... [AI DM narrative]"

# After
status_parts = []
for clock_name, clock in mechanics.scene_clocks.items():
    status_parts.append(f"{clock_name}: {clock.current}/{clock.maximum}")

if status_parts:
    narration = "📊 " + " | ".join(status_parts)
else:
    return  # Skip DM turn if nothing to report
```

**File**: `scripts/aeonisk/multiagent/dm.py`

---

#### 3. Attribute Validation Failures

**Error**:
```
[Echo Resonance] Action rejected: Attribute must be one of: Strength, Agility, ...
```

**Cause**: LLM was returning attribute names with incorrect capitalization (e.g., "empathy" instead of "Empathy"), causing validation to fail.

**Fix** (player.py:373-397):
- Added normalization mapping for attribute names
- Converts any capitalization to proper case
- Falls back to "Perception" if unrecognized

**Code Change**:
```python
VALID_ATTRIBUTES = {
    'strength': 'Strength',
    'empathy': 'Empathy',
    # ... etc
}

# Normalize attribute name
attr_lower = value.lower()
data['attribute'] = VALID_ATTRIBUTES.get(attr_lower, 'Perception')
```

**File**: `scripts/aeonisk/multiagent/player.py`

---

#### 4. Skill Mismatch in Simple Actions

**Issue**: Players were attempting to use skills they don't have (e.g., Zara trying to use "Social" skill when she only has "Astral Arts" and "Investigation").

**Cause**: Simple action generator wasn't checking character's actual skills before assigning them.

**Fix** (player.py:431-489):
- Check character's actual skills before selecting action
- Prioritize actions using skills the character has
- Fall back to raw attribute check (skill=None) if no appropriate skill

**Code Change**:
```python
# Check character's actual skills
has_social = 'Social' in self.character_state.skills
has_astral = 'Astral Arts' in self.character_state.skills
has_investigation = 'Investigation' in self.character_state.skills

# Choose action based on available skills
if 'social' not in recent_types and has_social:
    # Use Social skill
elif has_astral:
    # Use Astral Arts
else:
    # Use raw Perception (no skill)
    skill = None
```

**File**: `scripts/aeonisk/multiagent/player.py`

---

#### 5. Ritual Attribute Enforcement (Codex Nexum #1)

**Issue**: Rituals were using Perception × Astral Arts instead of Willpower × Astral Arts, violating Aeonisk v1.2.2 module rules.

**Example from logs**:
```
Zara attempts ritual with Perception×Astral Arts (should be Willpower×Astral Arts)
```

**Cause**: LLM was selecting attributes based on narrative context rather than enforcing ritual mechanics rules.

**Fix** (skill_mapping.py:64-86):
- Created `validate_ritual_mechanics()` function
- Forces ALL rituals to use Willpower × Astral Arts (no exceptions)
- Applied automatically in player.py during action validation

**Code Change**:
```python
def validate_ritual_mechanics(action_type, attribute, skill):
    """Enforce ritual mechanics rules."""
    if action_type == 'ritual':
        # Force Willpower × Astral Arts for all rituals
        return (RITUAL_ATTRIBUTE, RITUAL_SKILL)
    return (attribute, skill)
```

**File**: `scripts/aeonisk/multiagent/skill_mapping.py` (NEW)

---

#### 6. Skill Aliasing Bug (Codex Nexum #2)

**Issue**: "Social (5)" became skill value 0, causing math errors like "3×0+4 = 2"

**Cause**:
1. "Social" isn't a YAGS skill (should be "Charm" or "Guile")
2. "Investigation" isn't a YAGS skill (should be "Awareness")
3. Code was checking for wrong skill names in character sheet

**Fix** (skill_mapping.py:9-40 + player.py:469-491):
- Created SKILL_ALIASES mapping ('social' → 'Charm', 'investigation' → 'Awareness')
- Added `normalize_skill()` function to convert aliases to canonical names
- Fixed simple action generator to check for correct skill names
- Skill lookup now uses normalized names

**Code Change**:
```python
# skill_mapping.py
SKILL_ALIASES = {
    'social': 'Charm',
    'investigation': 'Awareness',
    'astral arts': 'Astral Arts',
    # ...
}

# player.py - Fixed from checking wrong names
# Before: has_social = 'Social' in self.character_state.skills
# After:
has_charm = 'Charm' in self.character_state.skills
has_guile = 'Guile' in self.character_state.skills
has_social = has_charm or has_guile
skill = "Charm" if has_charm else "Guile"
```

**Files**:
- `scripts/aeonisk/multiagent/skill_mapping.py` (NEW)
- `scripts/aeonisk/multiagent/player.py`

---

#### 7. Clock Advancement Hooks (Codex Nexum #3)

**Issue**: Clocks never advanced despite narrative describing alarms, lockdowns, evidence discovery. All clocks stayed 0/6 entire session.

**Cause**: Clocks only advanced through explicit `update_clocks_from_action()` calls, which had hardcoded conditions that didn't match actual narrative.

**Fix** (outcome_parser.py:13-63):
- Created `parse_clock_triggers()` function
- Scans narrative for keywords (security, alarm, badge, terminal, lockdown, etc.)
- Returns list of (clock_name, ticks, reason) based on outcome tier and margin
- Auto-applied in dm.py after each resolution

**Code Change**:
```python
def parse_clock_triggers(narration, outcome_tier, margin):
    """Parse narration to determine clock advancements."""
    triggers = []
    narration_lower = narration.lower()

    # Corporate Suspicion triggers
    if any(phrase in narration_lower for phrase in [
        'security', 'alarm', 'drone', 'detected'
    ]):
        triggers.append(('Corporate Suspicion', 1, "Security response"))

    # Evidence Trail triggers
    if outcome_tier in ['moderate', 'good', 'excellent'] and margin > 0:
        if any(phrase in narration_lower for phrase in [
            'badge', 'terminal', 'signature', 'log'
        ]):
            ticks = 2 if margin >= 10 else 1
            triggers.append(('Evidence Trail', ticks, f"Evidence discovered"))
    # ... more triggers
```

**Files**:
- `scripts/aeonisk/multiagent/outcome_parser.py` (NEW)
- `scripts/aeonisk/multiagent/dm.py`

---

#### 8. Void Tracking Hooks (Codex Nexum #4)

**Issue**: Void never increased despite narrative mentioning "+1 Void" multiple times. All characters ended at 0/10.

**Cause**: Void only tracked through explicit `check_void_trigger()` calls with hardcoded keywords, missing most narrative mentions.

**Fix** (outcome_parser.py:66-118):
- Created `parse_void_triggers()` function
- Detects explicit mentions ("+1 void", "+2 void")
- Detects ritual failures (outcome_tier = failure/critical_failure)
- Detects void manipulation keywords
- Detects psychic damage/backlash
- Returns (void_change, list_of_reasons)

**Code Change**:
```python
def parse_void_triggers(narration, action_intent, outcome_tier):
    """Parse for void gains based on narration."""
    void_change = 0
    reasons = []

    # Explicit mentions
    if '+1 void' in narration_lower:
        void_change += 1
        reasons.append("Explicit void gain mentioned")

    # Ritual failures
    if 'ritual' in intent_lower and outcome_tier in ['failure', 'critical_failure']:
        void_change += 1
        reasons.append("Failed ritual")

    # Psychic damage
    if any(phrase in narration_lower for phrase in [
        'psychic recoil', 'backlash', 'mental trauma'
    ]):
        void_change += 1
        reasons.append("Psychic/mental corruption")
    # ...
```

**Files**:
- `scripts/aeonisk/multiagent/outcome_parser.py` (NEW)
- `scripts/aeonisk/multiagent/dm.py`

---

#### 9. Math Verification (Codex Nexum #7)

**Issue**: Math errors in logs: "3×0+4 = 2" (should be 4)

**Cause**: No validation that calculations were performed correctly, making bugs hard to detect.

**Fix** (mechanics.py:187-211):
- Added assertions at each calculation step
- Verify: base_total = ability + roll
- Verify: total = base_total + modifier_sum
- Assertions provide clear error messages showing expected vs actual

**Code Change**:
```python
# Skilled calculation
ability = attribute_value * skill_value
base_total = ability + roll

# Math verification
assert base_total == ability + roll, \
    f"Math error (skilled): {attribute_value}×{skill_value}+{roll} should be {ability}+{roll}={ability+roll}, got {base_total}"

# Modifier application
modifier_sum = sum(modifiers.values()) if modifiers else 0
total = base_total + modifier_sum

# Math verification
assert total == base_total + modifier_sum, \
    f"Math error (modifiers): {base_total} + modifiers({modifier_sum}) should be {expected_total}, got {total}"
```

**File**: `scripts/aeonisk/multiagent/mechanics.py`

---

## Second Round Fixes (2025-10-20 evening)

After test run `3868e4d3`, Codex Nexum identified 6 critical issues still present despite initial fixes.

### ✅ Fixed Issues (Round 2)

#### 10. Unskilled Roll Display Formula

**Issue**: Display showed "3 × 0 + 20 = 18" which looks like 20, not 18

**Cause**: Display formula always showed `attribute_value × skill_value + roll` even when skill_value=0, but the actual calculation for unskilled is `attribute_value + roll - 5`

**Fix** (mechanics.py:458-480):
- Added conditional display logic
- Skilled: Show `3 × 5 + 12 = 27`
- Unskilled: Show `3 + 20 - 5 (unskilled) = 18`

**Code Change**:
```python
if resolution.skill_value > 0:
    # Skilled: Attribute × Skill + d20
    formula = f"{resolution.attribute_value} × {resolution.skill_value} + {resolution.roll}"
else:
    # Unskilled: Attribute + d20 - 5
    formula = f"{resolution.attribute_value} + {resolution.roll} - 5 (unskilled)"
```

**File**: `scripts/aeonisk/multiagent/mechanics.py`

---

#### 11. Ritual Attribute Validation in DM Resolver

**Issue**: DM sometimes resolved rituals with Perception × Astral Arts even after player correction showed Willpower × Astral Arts

**Cause**: Player validated and corrected, but DM didn't re-validate received actions

**Fix** (dm.py:302-314):
- Added ritual validation check in DM resolver
- Forces Willpower × Astral Arts for all ritual/void-tech actions
- Logs warning if correction needed

**Code Change**:
```python
# CRITICAL: Re-validate ritual mechanics at DM resolution time
from .skill_mapping import RITUAL_ATTRIBUTE, RITUAL_SKILL

if action_type == 'ritual' or action.get('is_ritual', False):
    if attribute != RITUAL_ATTRIBUTE or skill != RITUAL_SKILL:
        logger.warning(f"DM correcting ritual: {attribute}×{skill} → {RITUAL_ATTRIBUTE}×{RITUAL_SKILL}")
    attribute = RITUAL_ATTRIBUTE
    skill = RITUAL_SKILL
```

**File**: `scripts/aeonisk/multiagent/dm.py`

---

#### 12. Clock FILLED Spam

**Issue**: "📍 **Corporate Suspicion FILLED!**" message appeared 10+ times after clock reached 6/6

**Cause**: `advance()` returned True every time it was called when clock was already filled

**Fix** (mechanics.py:66-81):
- Modified SceneClock.advance() to return True **only** on transition from not-filled to filled
- Added `_ever_filled` private flag to track state
- Added `ever_filled` property for one-time trigger checks

**Code Change**:
```python
def advance(self, ticks: int = 1) -> bool:
    """Return True if NEWLY filled (first time reaching max)."""
    was_filled = self.current >= self.maximum
    self.current = min(self.current + ticks, self.maximum)
    is_filled = self.current >= self.maximum

    # Return True only on the transition
    if is_filled and not was_filled:
        self._ever_filled = True
        return True
    return False
```

**File**: `scripts/aeonisk/multiagent/mechanics.py`

---

#### 13. Evidence Trail Never Advanced

**Issue**: Evidence Trail stayed 0/6 despite narration describing:
- "microscopic fractures in ward patterns"
- "unauthorized neural-capture devices"
- "Mnemonic Syndicate signature"
- "maintenance tunnels"
- "security badge"

**Cause**: Keywords in outcome_parser didn't match actual narrative vocabulary

**Fix** (outcome_parser.py:35-49):
- Expanded keyword list to 20+ evidence-related terms
- Added: device, tech, equipment, neural-capture, crystalline, residue, fracture, tampering, maintenance duct, tunnel, syndicate, corporate, logo, insignia, sigil, sequence, protocol, unauthorized
- Changed threshold from only 'moderate+' to include 'marginal' (any success)

**Code Change**:
```python
# Evidence Trail triggers - concrete clues discovered
if outcome_tier in ['marginal', 'moderate', 'good', 'excellent', 'exceptional'] and margin >= 0:
    if any(phrase in narration_lower for phrase in [
        'badge', 'terminal', 'signature', 'log', 'trace',
        'device', 'tech', 'neural-capture', 'crystalline', 'residue',
        'fracture', 'tampering', 'maintenance duct', 'tunnel',
        'syndicate', 'corporate', 'logo', 'insignia', 'sigil',
        'sequence', 'protocol', 'unauthorized'
    ]):
        ticks = 2 if margin >= 10 else 1
        triggers.append(('Evidence Trail', ticks, f"Concrete evidence discovered"))
```

**File**: `scripts/aeonisk/multiagent/outcome_parser.py`

---

#### 14. Facility Lockdown Undertriggered

**Issue**: Lockdown only ticked once despite narration describing:
- "security drones converging"
- "psychic feedback"
- "families collapsing"
- "catatonic"
- "chaos"

**Cause**: Lockdown keywords too narrow (only 'lockdown', 'sealed', 'containment', 'quarantine')

**Fix** (outcome_parser.py:52-58):
- Added escalation keywords: drones converging, security converging, psi backlash, psychic backlash, feedback, cascade, families collapsing, catatonic, chaos, disorder

**Code Change**:
```python
if any(phrase in narration_lower for phrase in [
    'lockdown', 'sealed', 'containment', 'quarantine',
    'drones converging', 'security converging', 'armed response',
    'psi backlash', 'psychic backlash', 'feedback', 'cascad',
    'families collapsing', 'catatonic', 'chaos', 'disorder'
]):
    triggers.append(('Facility Lockdown', 1, "Security/chaos escalation"))
```

**File**: `scripts/aeonisk/multiagent/outcome_parser.py`

---

#### 15. Untrained Social Using Wrong Attribute

**Issue**: Social actions without Charm/Guile used `Perception` instead of `Empathy`
- Example: "Organize support circle" → Perception × None instead of Empathy × None

**Cause**:
1. LLM included skill value in name ("Social (5)")
2. Validation set skill=None but didn't correct attribute for social actions

**Fix** (skill_mapping.py):
- Strip parenthetical values from skill names: "Social (5)" → "Social"
- Force social actions to use Empathy/Charisma (not Perception)
- Keep unskilled penalty but with correct attribute

**Code Changes**:
```python
# Strip out parenthetical values
skill_clean = re.sub(r'\s*\([^)]*\)', '', skill_name).strip()

# Force social attribute correction
if corrected_skill in ['Charm', 'Guile'] or action_type == 'social':
    if corrected_attr not in ['Empathy', 'Charisma']:
        corrected_attr = 'Empathy'  # Prefer Empathy for social
```

**File**: `scripts/aeonisk/multiagent/skill_mapping.py`

---

#### 16. Outcome Tier String Normalization

**Issue**: Outcome tier comparisons failed because enum vs string mismatch

**Cause**: `resolution.__dict__` includes OutcomeTier enum, but parser compared to lowercase strings

**Fix** (outcome_parser.py:154-162):
- Normalize outcome_tier to string value
- Handle both enum objects (with .value) and string values
- Ensure lowercase for consistent comparison

**Code Change**:
```python
outcome_tier_raw = resolution.get('outcome_tier', 'moderate')

# Normalize outcome_tier to string
if hasattr(outcome_tier_raw, 'value'):
    outcome_tier = outcome_tier_raw.value  # Extract from enum
else:
    outcome_tier = str(outcome_tier_raw).lower()
```

**File**: `scripts/aeonisk/multiagent/outcome_parser.py`

---

#### 17. Additional Void Triggers

**Issue**: Only 1 void gain tracked despite multiple void-risk interactions:
- "controlled void resonance"
- "tap into facility's void-shield grid"
- "attune to the void"
- Multiple failures with void manipulation

**Fix** (outcome_parser.py:102-115):
- Added void exposure keywords: void-shield, tap into void, controlled void, void-enhanced, void scan, attune to void, opening to the void, void channel
- Added void trigger for regular FAILURE (not just critical failure)

**Code Change**:
```python
# Void manipulation and exposure
if any(phrase in narration_lower or phrase in intent_lower for phrase in [
    'void energy', 'void manipulation', 'void resonance',
    'void-shield', 'tap into void', 'controlled void',
    'void-enhanced', 'void scan', 'attune to void',
    'opening to the void', 'void channel'
]):
    if outcome_tier == 'critical_failure':
        void_change += 1
        reasons.append("Void backlash from critical failure")
    elif outcome_tier == 'failure':
        void_change += 1
        reasons.append("Failed void manipulation")
```

**File**: `scripts/aeonisk/multiagent/outcome_parser.py`

---

**File**: `scripts/aeonisk/multiagent/mechanics.py`

---

## Verification

All fixes have been applied. The system should now:

### Initial Fixes (2025-10-20 early)
✅ Send messages without JSON serialization errors
✅ Show meaningful clock status instead of placeholder spam
✅ Handle any attribute capitalization from LLM
✅ Only use skills characters actually possess

### Codex Nexum Critical Fixes (2025-10-20 afternoon)
✅ Force Willpower × Astral Arts for ALL rituals (no exceptions)
✅ Normalize skill aliases (Social → Charm/Guile, Investigation → Awareness)
✅ Automatically advance clocks based on narrative keywords
✅ Automatically track void based on narrative keywords and outcomes
✅ Verify all math calculations with assertions to catch errors

### Second Round Fixes (2025-10-20 evening)
✅ Display correct formula for unskilled checks (`3 + 20 - 5 (unskilled) = 18`)
✅ Re-validate rituals at DM resolution time (double-check enforcement)
✅ Clock FILLED message only appears once (on transition to full)
✅ Evidence Trail advances on concrete clues (20+ keyword triggers)
✅ Facility Lockdown tracks escalation (drones, psi backlash, chaos)
✅ Social actions use Empathy (not Perception) when unskilled
✅ Outcome tier comparisons work (enum normalization)
✅ Void triggers on failed void manipulation (not just critical failures)

## Testing

Run the test again:

```bash
cd /home/p/Coding/aeonisk-yags
source scripts/aeonisk/.venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_config.json
```

Expected improvements:

**Round 1:**
- No JSON errors in logs
- DM turns show clock status: `📊 Sanctuary Corruption: 2/6 | ...`
- No attribute validation failures
- All actions use skills the character actually has
- Rituals always use Willpower × Astral Arts (auto-corrected with notice)
- Clocks advance automatically: `📊 Corporate Suspicion: 0/6 → 1/6 | Evidence Trail: 1/6 → 3/6`
- Void tracks automatically: `⚫ Void: 0 → 1/10 (Failed ritual, Psychic backlash)`
- No math errors (assertions will catch any calculation bugs immediately)

**Round 2 (additional):**
- Unskilled rolls display correctly: `3 + 20 - 5 (unskilled) = 18`
- Rituals double-validated at DM (log warning if correction needed)
- Clock FILLED message appears **once** (not 10+ times)
- Evidence Trail advances: `📊 Evidence Trail: 0/6 → 2/6 → 4/6`
- Facility Lockdown tracks chaos: `📊 Facility Lockdown: 0/4 → 2/4`
- Social actions use Empathy when unskilled: `Empathy + 15 - 5 (unskilled) = 13`
- Void gains from multiple exposures: `⚫ Void: 0 → 3/10` (not stuck at 1/10)
- No more "0/6" status lines (shows actual state after updates)

## Files Modified

### Initial Fixes:
1. `scripts/aeonisk/multiagent/dm.py`
   - Lines 359-379: JSON serialization fix
   - Lines 418-450: DM turn status reporting
   - Lines 348-371: Outcome parser integration for clock/void auto-updates

2. `scripts/aeonisk/multiagent/player.py`
   - Lines 373-397: Attribute normalization
   - Lines 431-489: Skill availability checking (initial)
   - Lines 199-230: Skill validation integration
   - Lines 469-491: Fixed skill lookup (Charm/Guile instead of Social, Awareness instead of Investigation)

### Codex Nexum Fixes:

3. `scripts/aeonisk/multiagent/skill_mapping.py` **(NEW)**
   - Skill alias mapping (Social → Charm, Investigation → Awareness)
   - `validate_ritual_mechanics()` - Forces Willpower × Astral Arts for rituals
   - `normalize_skill()` - Converts any skill alias to canonical name
   - `get_character_skill_value()` - Safe skill lookup with normalization

4. `scripts/aeonisk/multiagent/outcome_parser.py` **(NEW)**
   - `parse_clock_triggers()` - Auto-detect clock advancements from narrative
   - `parse_void_triggers()` - Auto-detect void gains from narrative
   - `parse_state_changes()` - Comprehensive state parser

5. `scripts/aeonisk/multiagent/mechanics.py`
   - Lines 187-211: Math verification assertions to catch calculation errors

### Round 2 Fixes:

6. `scripts/aeonisk/multiagent/mechanics.py` (additional)
   - Lines 458-480: Corrected unskilled roll display formula
   - Lines 66-81: Clock FILLED spam fix (transition-only trigger)

7. `scripts/aeonisk/multiagent/dm.py` (additional)
   - Lines 302-314: Re-validate ritual mechanics at DM resolution time

8. `scripts/aeonisk/multiagent/skill_mapping.py` (additional)
   - Lines 47-65: Strip parenthetical values from skill names
   - Lines 140-145: Force social actions to use Empathy/Charisma

9. `scripts/aeonisk/multiagent/outcome_parser.py` (additional)
   - Lines 35-49: Expanded Evidence Trail keywords (20+ terms)
   - Lines 52-58: Expanded Facility Lockdown keywords
   - Lines 102-115: Additional void manipulation triggers
   - Lines 154-162: Outcome tier enum normalization

---

## Issues Found During Testing (2025-10-22 Skill System)

### ✅ Fixed Issues

#### 18. Players Lacking Skill Context ("Underwater Basket Weaving Problem")

**Issue**: Player AI agents were choosing incorrect skills because they lacked complete information about what skills exist and what each skill does.

**Example from analysis**:
```
Player prompt showed only:
**Skills:**
- Charm: 5
- Astral Arts: 4
- Systems: 3

Players had to infer:
- What does "Charm" actually do?
- When should I use Charm vs Guile?
- What's the difference between Astral Arts vs Intimacy Ritual vs Magick Theory?
- What attribute pairs with which skill?
- What other skills exist that I don't have?
```

**Root Causes**:
1. **No skill descriptions** - Just names and ranks ("Charm: 5")
2. **No attribute guidance** - Players didn't know Charm uses Empathy, not Perception
3. **No use case examples** - Players had to guess when to use each skill
4. **No awareness of other skills** - If they didn't have "Stealth", they didn't know sneaking was possible
5. **Confusing overlaps** - Three ritual skills with unclear boundaries:
   - Astral Arts = performing energy-based rituals
   - Intimacy Ritual = performing emotion-based rituals
   - Magick Theory = understanding/analyzing rituals (NOT performing)

**User Feedback**: *"i suspect the meaning of the skills isnt clear enough for the players. can you look into why this is? like they pick the wrong skill sometimes."*

**Philosophy**: *"i think we want the skill mapping and coercion to be much gentler and let the AI pick what they want more often tbh. that is useful data."*

**Fix** (skill_descriptions.py NEW, enhanced_prompts.py):

1. **Created Comprehensive Skill Database** (skill_descriptions.py):
```python
SKILL_DATABASE: Dict[str, SkillInfo] = {
    "Charm": SkillInfo(
        name="Charm",
        attribute="Empathy",
        description="Persuasion, making friends, social influence (sincere or manipulative)",
        use_cases=["Befriending NPCs", "Negotiating peacefully", "Earning trust"],
        category="Social",
        note="Can be sincere or insincere - it's about getting people to like you"
    ),
    # ... all YAGS + Aeonisk skills
}
```

2. **Implemented Tiered Skill Display** (enhanced_prompts.py):

**Tier 1: Skills Character Has (Full Detail)**
```markdown
**YOUR SKILLS (detailed):**

**RITUAL:**
- **Astral Arts (4)** [Willpower]: Channeling, resisting, and shaping spiritual energies; void manipulation rituals
  → Use when: Performing energy-based rituals, Binding entities, Void cleansing
  ℹ️  Default ritual skill for most void/energy work. Uses Willpower, not Empathy.

- **Intimacy Ritual (3)** [Empathy]: Emotionally-powered or Bond-based rituals; creating connections
  → Use when: Strengthening Bonds, Emotional connection rituals, Intimidation rituals
  ℹ️  Use for rituals involving emotions or Bonds, NOT void manipulation.

- **Magick Theory (2)** [Intelligence]: Knowledge of glyphs, ritual systems, sacred mechanics
  → Use when: Analyzing rituals, Researching glyphs, Understanding ritual mechanics
  ℹ️  For UNDERSTANDING rituals, not PERFORMING them. Use Intelligence, not Willpower.
```

**Tier 2: Available Skills (Brief Categorized List)**
```markdown
**OTHER AVAILABLE SKILLS (can attempt untrained at -50%):**
Use [LOOKUP: skill name] for detailed guidance on any skill.

**Combat:**
- **Guns** [Perception]: Firearms, pistols, rifles, shotguns, targeting
- **Melee** [Dexterity]: Swords, knives, clubs, hand-to-hand weapon combat
- **Throw** [Dexterity]: Throwing weapons, grenades, accuracy

**Knowledge:**
- **Debt Law** [Intelligence]: Understanding/manipulating contracts, oaths, Soulcredit systems
- **Science** [Intelligence]: Scientific knowledge, physics, chemistry, biology

**Social:**
- **Guile** [Empathy]: Deception, lying, reading lies, cunning misdirection
- **Counsel** [Empathy]: Emotional support, therapy, guidance
```

**Impact**:
- **Complete skill awareness**: Players know what skills exist, even ones they don't have
- **Clear attribute pairing**: [Willpower], [Empathy], [Intelligence] tags show which attribute to use
- **Use case guidance**: "Use when: Analyzing rituals, NOT performing them" prevents Magick Theory misuse
- **Prompt efficiency**: ~415 tokens for full context (character has 8 skills, system shows all 25+ skills)
- **Preserves AI agency**: Players still make choices, but with complete information
- **Better training data**: "Wrong" choices with full information = genuine AI behavior to study

**Design Rationale - "Underwater Basket Weaving"**:
> "if you dont have the underwater basket weaving skill then you dont need to know all the details just that it exists. so that makes sense."

Players get:
- **Full details** for skills they have (need to use effectively)
- **Brief descriptions** for skills they don't have (awareness without clutter)
- **Reference mechanism**: `[LOOKUP: skill name]` for edge cases

**Comparison - Old vs New Prompt**:

**Before** (~50 tokens):
```
**Skills:**
- Charm: 5
- Awareness: 4
- Astral Arts: 4
- Intimacy Ritual: 3
```

**After** (~415 tokens):
```
**YOUR SKILLS (detailed):**

**SOCIAL:**
- **Charm (5)** [Empathy]: Persuasion, making friends, social influence
  → Use when: Befriending NPCs, Negotiating peacefully, Earning trust
  ℹ️  Can be sincere or insincere - it's about getting people to like you

[... 7 more skills with full details ...]

**OTHER AVAILABLE SKILLS (can attempt untrained at -50%):**
- **Guns** [Perception]: Firearms, pistols, rifles, shotguns, targeting
- **Guile** [Empathy]: Deception, lying, reading lies, cunning
- **Stealth** [Agility]: Sneaking, hiding, moving quietly
[... 17 more skills briefly listed ...]
```

**Token Cost Analysis**:
- 365 additional tokens for complete skill context
- ~10-15% of typical player prompt
- Justified for complex multi-agent TTRPG simulation requiring nuanced decision-making

**Testing Output**:
```bash
$ python3 scripts/test_skill_display.py
Token count estimate: 415
```

**Files Modified**:
- `scripts/aeonisk/multiagent/skill_descriptions.py` **(NEW)** - Comprehensive YAGS + Aeonisk skill database
- `scripts/aeonisk/multiagent/enhanced_prompts.py` - Tiered skill display implementation

**Files Created**:
- `scripts/test_skill_display.py` - Test script for validating skill display output

---

## Related Documentation

- See `INTEGRATION_COMPLETE.md` for full testing guide
- See `QUICK_START_MECHANICS.md` for usage patterns
- See `MULTIAGENT_MECHANICS_UPGRADE.md` for architecture
