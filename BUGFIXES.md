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

## Verification

All fixes have been applied. The system should now:

✅ Send messages without JSON serialization errors
✅ Show meaningful clock status instead of placeholder spam
✅ Handle any attribute capitalization from LLM
✅ Only use skills characters actually possess

## Testing

Run the test again:

```bash
cd /home/p/Coding/aeonisk-yags
source scripts/aeonisk/.venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_config.json
```

Expected improvements:
- No JSON errors in logs
- DM turns show clock status: `📊 Sanctuary Corruption: 2/6 | ...`
- No attribute validation failures
- All actions use skills the character actually has

## Files Modified

1. `scripts/aeonisk/multiagent/dm.py`
   - Lines 359-379: JSON serialization fix
   - Lines 418-450: DM turn status reporting

2. `scripts/aeonisk/multiagent/player.py`
   - Lines 373-397: Attribute normalization
   - Lines 431-489: Skill availability checking

## Related Documentation

- See `INTEGRATION_COMPLETE.md` for full testing guide
- See `QUICK_START_MECHANICS.md` for usage patterns
- See `MULTIAGENT_MECHANICS_UPGRADE.md` for architecture
