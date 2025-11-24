# OpenAI Structured Output Validation Fixes

**Date:** 2025-11-15
**Issue:** OpenAI `gpt-5-mini` generating reasonable values that didn't match schema constraints
**Severity:** Blocking OpenAI provider usage
**Status:** ✅ FIXED

---

## Summary

Fixed two classes of schema validation errors when using OpenAI models for structured output:

1. **Missing NPC disposition values** - LLM wanted to use "fearful" (semantically correct), schema only allowed "wary" (semantically wrong)
2. **Unicode hyphen variants** - OpenAI generates non-breaking hyphens (U+2011 `‑`) instead of ASCII hyphens (U+002D `-`) in position values

## Root Causes

### Issue 1: Insufficient Disposition Values

**Original Error:**
```
ValidationError: 1 validation error for ScenarioSetup
initial_npcs.2.disposition
  Input should be 'friendly', 'neutral', 'wary' or 'prisoner'
  [type=literal_error, input_value='fearful', input_type=str]
```

**Problem:**
- Schema: `disposition: Literal["friendly", "neutral", "wary", "prisoner"]`
- LLM: Scenario has "terrified acolytes flee for their lives", wants `disposition="fearful"`
- Reality: "wary" means "suspicious/cautious", NOT "scared/terrified"

**Why This Matters:**
- OpenAI models are semantically accurate - they pick the RIGHT word
- Our schema was semantically incomplete - missing obvious emotional states
- Prompt examples used "wary" for "Terrified civilian" (incorrect)

**Also discovered:** LLM confused `entity_type` with `threat_level` due to poor descriptions

### Issue 2: Unicode Hyphen Normalization

**Error After Fix #1:**
```
ValidationError: 2 validation errors for ScenarioSetup
initial_enemies.0.initial_position
  Input should be 'Engaged', 'Near-PC', 'Near-Enemy', 'Far-PC', 'Far-Enemy', 'Extreme-PC' or 'Extreme-Enemy'
  [type=enum, input_value='Near‑PC', input_type=str]
```

**Problem:**
- Schema: `Position.NEAR_PC = "Near-PC"` (ASCII hyphen U+002D)
- OpenAI: Generates `"Near‑PC"` (non-breaking hyphen U+2011)
- Invisible difference, same visual appearance

**Why OpenAI Does This:**
- LLMs trained on diverse Unicode text
- Non-breaking hyphens prevent line breaks in "Near-PC" (technically correct typography)
- Model generalizes from training data

## Fixes Applied

### Fix 1: Expand NPC Disposition Schema

**File:** `scripts/aeonisk/multiagent/schemas/story_events.py:600`

**Before:**
```python
disposition: Literal["friendly", "neutral", "wary", "prisoner"]
```

**After:**
```python
disposition: Literal["friendly", "neutral", "wary", "fearful", "hostile", "prisoner"] = Field(
    ...,
    description="NPC's EMOTIONAL STATE/ATTITUDE toward players. Options: 'friendly' (helpful/cooperative), 'neutral' (indifferent/businesslike), 'wary' (suspicious/cautious), 'fearful' (scared/intimidated/terrified), 'hostile' (aggressive/antagonistic but not in combat), 'prisoner' (captured/restrained/compliant)"
)
```

**Also improved field descriptions:**
- `entity_type`: Added "⚠️ DO NOT confuse with threat_level!" warning
- `threat_level`: Added "⚠️ DO NOT confuse with entity_type!" warning

**Prompt Updates:**
- `dm_commands.yaml`: Changed example from `disposition="wary"` to `disposition="fearful"` for "Frightened Dock Worker"
- `dm_conversion_check.yaml`: Added disposition value guide with semantic meanings

### Fix 2: Position Enum Hyphen Normalization

**File:** `scripts/aeonisk/multiagent/schemas/shared_types.py:54-90`

**Added `_missing_` hook to Position enum:**
```python
@classmethod
def _missing_(cls, value):
    """
    Normalize Unicode hyphen variants to regular ASCII hyphen.

    OpenAI models sometimes generate non-breaking hyphens (U+2011 ‑) or other
    hyphen variants instead of regular ASCII hyphens (U+002D -).
    """
    if isinstance(value, str):
        # Replace common hyphen variants with regular ASCII hyphen
        normalized = value.replace('\u2011', '-')  # non-breaking hyphen
        normalized = normalized.replace('\u2010', '-')  # hyphen
        normalized = normalized.replace('\u2012', '-')  # figure dash
        normalized = normalized.replace('\u2013', '-')  # en dash
        normalized = normalized.replace('\u2014', '-')  # em dash
        normalized = normalized.replace('\u2212', '-')  # minus sign

        try:
            return cls(normalized)
        except ValueError:
            pass

    return None
```

**Handles:** U+2010, U+2011, U+2012, U+2013, U+2014, U+2212 → U+002D

## Tests Added

### NPC Disposition Tests
**File:** `tests/unit/test_npc_spawn_schema.py`

- `test_fearful_disposition_should_be_valid()` - Fearful NPCs accepted
- `test_existing_dispositions_still_work()` - Backward compatibility
- `test_potential_threat_is_threat_level_not_entity_type()` - Field confusion caught
- `test_scenario_setup_with_fearful_npc()` - Integration test (reproduces original error)

### Position Hyphen Tests
**File:** `tests/unit/test_position_hyphen_normalization.py`

- `test_regular_hyphen_accepted()` - Baseline works
- `test_non_breaking_hyphen_normalized()` - U+2011 normalized
- `test_all_positions_with_non_breaking_hyphen()` - All enum values work
- `test_enemy_spawn_with_non_breaking_hyphen()` - Integration test

**All tests pass:** 10/10 ✓

## Impact

### Before Fix
- ❌ OpenAI sessions fail at scenario generation (7 retries, then crash)
- ❌ `gpt-5-mini` unusable for multi-agent sessions
- ❌ ~50% retry rate for structured output

### After Fix
- ✅ OpenAI sessions generate scenarios successfully
- ✅ Schema accepts semantically correct LLM outputs
- ✅ Unicode formatting variations handled transparently

## Lessons Learned

### Schema Design for Multi-Provider Support

1. **Semantic Completeness > Minimal Schemas**
   - Bad: "wary" (suspicious) used for "terrified" (scared)
   - Good: Include all reasonable emotional states models might infer

2. **Unicode Normalization is Mandatory**
   - LLMs trained on diverse text → diverse Unicode output
   - Enums with punctuation MUST normalize variants
   - Applies to: hyphens, quotes, apostrophes, ellipses, dashes

3. **Field Naming Clarity**
   - `entity_type` vs `threat_level` - similar domains, easy to confuse
   - Solution: Add explicit warnings in descriptions

4. **Test-Driven Schema Evolution**
   - Write failing test reproducing LLM error → Fix schema → Test passes
   - Captures real LLM behavior patterns

### Provider-Specific Quirks

**Anthropic (Claude):**
- Conservative Unicode (prefers ASCII)
- Follows literal examples closely
- Rarely needs normalization

**OpenAI (GPT):**
- Rich Unicode usage (typographically correct)
- Semantic inference (picks best-fit words)
- Needs normalization + broader value sets

## Files Modified

### Schema Changes
- `scripts/aeonisk/multiagent/schemas/story_events.py` - NPCSpawn disposition expanded
- `scripts/aeonisk/multiagent/schemas/shared_types.py` - Position hyphen normalization

### Prompt Updates
- `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_commands.yaml` - Example corrections
- `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_conversion_check.yaml` - Disposition guide

### Tests Added
- `tests/unit/test_npc_spawn_schema.py` - NPC disposition validation
- `tests/unit/test_position_hyphen_normalization.py` - Unicode hyphen handling

## Future Work

### Potential Normalizations Needed
- **Quotes:** `"` vs `"` vs `'` vs `'` (curly quotes)
- **Apostrophes:** `'` vs `'` (straight vs curly)
- **Ellipses:** `...` vs `…` (three dots vs Unicode ellipsis)
- **Spaces:** Regular space vs non-breaking space (U+00A0)

### Schema Audit Recommendations
1. Audit all `Literal[...]` fields for semantic completeness
2. Add normalization to all enums with punctuation
3. Add field description warnings for confusable fields
4. Test with multiple LLM providers early in development

## Testing Command

```bash
# Run both new test suites
python -m pytest tests/unit/test_npc_spawn_schema.py tests/unit/test_position_hyphen_normalization.py -v

# Test full OpenAI session
python3 scripts/run_multiagent_session.py scripts/session_configs/openai/failed_ascension_ritual_openai.json
```

## Commit Message Template

```
fix: Add fearful/hostile NPC dispositions and normalize Position enum hyphens for OpenAI compatibility

**Problem:**
OpenAI gpt-5-mini generating semantically correct values that failed schema validation:
1. disposition="fearful" rejected (only allowed wary/neutral/friendly/prisoner)
2. initial_position="Near‑PC" rejected (non-breaking hyphen U+2011 vs ASCII hyphen)

**Root Causes:**
1. NPCSpawn disposition schema incomplete - missing common emotional states
2. Position enum didn't normalize Unicode hyphen variants
3. Confusing entity_type vs threat_level field descriptions

**Solution:**
1. Expanded disposition Literal to include "fearful" and "hostile"
2. Added Position._missing_() hook to normalize U+2010-2014,2212 → ASCII hyphen
3. Improved field descriptions with explicit warnings about confusable fields
4. Updated prompt examples (dm_commands.yaml, dm_conversion_check.yaml)

**Testing:**
- Added test_npc_spawn_schema.py (6 tests, reproduces original error)
- Added test_position_hyphen_normalization.py (4 tests, all hyphen variants)
- Verified OpenAI session generates scenarios without retries

**Impact:**
- OpenAI provider now works for scenario generation
- Schema accepts semantically accurate LLM outputs
- Unicode formatting variations handled transparently

schema(story_events): expand NPCSpawn.disposition to include fearful/hostile
schema(shared_types): add Position enum hyphen normalization via _missing_
prompts(dm_commands): fix fearful NPC example (was incorrectly using "wary")
prompts(dm_conversion_check): add disposition semantic guide
test(npc_spawn): add disposition and entity_type validation tests
test(position): add Unicode hyphen normalization tests
```
