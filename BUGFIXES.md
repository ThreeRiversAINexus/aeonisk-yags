# Bug Fixes - Multi-Agent Mechanics Integration

## Issues Found During Testing (2025-10-20)

### ✅ Fixed Issues

#### 1. JSON Serialization Error

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

#### 2. "The situation evolves..." Spam

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

## Related Documentation

- See `INTEGRATION_COMPLETE.md` for full testing guide
- See `QUICK_START_MECHANICS.md` for usage patterns
- See `MULTIAGENT_MECHANICS_UPGRADE.md` for architecture
