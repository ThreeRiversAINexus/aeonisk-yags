# Charisma Attribute Eradication - Complete Audit

## Problem

LLMs were generating `"attribute": "Charisma"` in structured output responses, causing Pydantic validation failures. The root cause: **Pydantic JSON schema descriptions** were listing "Charisma" as a valid attribute.

## Root Cause

Pydantic auto-generates JSON schemas from Field descriptions and sends them to LLMs. The schema included:
```python
attribute: str = Field(
    description="Attribute used: ...Charisma"  # ← LLMs saw this!
)
```

This told LLMs that "Charisma" was valid, even though validation would reject it.

## Files Fixed

### Core Schema Files (JSON schema generation)
1. **`scripts/aeonisk/multiagent/schemas/player_action.py`** (lines 107, 815)
   - ✅ Fixed: `"Charisma"` → `"Dexterity"` in Field descriptions
   - Impact: LLMs no longer see "Charisma" in JSON schema

2. **`scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_purchase.yaml`** (line 71)
   - ✅ Fixed: `{charisma}` → `{empathy}` template variable
   - Matches actual variable name in `player.py:2006`

### Utility Scripts
3. **`scripts/evaluate_scenario.py`** (lines 150, 182)
   - ✅ Fixed: Charisma → removed, Dexterity added to test character templates

### Test Files (9 files)
4. **Test fixtures and data** (bulk replaced)
   - ✅ Fixed: All test files using "Charisma" in attribute dicts
   - Files:
     - `tests/conftest.py`
     - `tests/unit/test_player_action_conversion.py`
     - `tests/unit/test_two_phase_action_generation.py`
     - `tests/unit/test_player_conditional_sections.py`
     - `tests/unit/test_vendor_social_targeting.py`
     - `tests/unit/test_action_validator_purchase.py`
     - `tests/unit/test_action_declaration_purchase_fields.py`
     - `tests/unit/test_player_action_schemas.py`
     - `tests/integration/test_prompt_conditional_loading.py`

## Verification

```bash
# Test that Charisma is properly excluded
python -m pytest tests/unit/test_attribute_migration.py -v
# Result: ✅ All 13 tests pass

# Verify no Charisma in active code (excluding validators/docs)
grep -rn "Charisma" scripts/ tests/ --include="*.py" --include="*.yaml" \
  | grep -v "character_validator.py" \
  | grep -v "bulk_replace_charisma.py" \
  | grep -v "test_attribute_migration.py" \
  | grep -v "NORMALIZED_BALANCE_ANALYSIS"
# Result: ✅ No matches (clean!)
```

## What Remains (Intentional)

**Validator:**
- `scripts/aeonisk/multiagent/character_validator.py` - **Intentionally** detects Charisma and suggests replacement

**Documentation:**
- `scripts/NORMALIZED_BALANCE_ANALYSIS.md` - Historical analysis data (archived)

**Migration tools:**
- `scripts/bulk_replace_charisma.py` - Tool for batch conversion (kept for reference)

**Test files:**
- `tests/unit/test_attribute_migration.py` - **Tests that Charisma is rejected** (regression tests)

**Log files:**
- `scripts/aeonisk/multiagent.log` - Old cached log data (will age out)

## Impact

**Before:**
- LLMs saw `"Charisma"` in JSON schema → generated `"attribute": "Charisma"`
- Pydantic validation rejected it → action failed after 3 retries
- Error: `Value error, Attribute must be one of: ...Willpower [input_value='Charisma']`

**After:**
- LLMs see `"Dexterity"` in JSON schema → will generate valid YAGS attributes
- Pydantic validation accepts all 8 YAGS attributes
- No more Charisma-related validation failures

## YAGS Standard Attributes (8 total)

Aeonisk uses YAGS core attributes with minor name changes:

| YAGS Name | Aeonisk Name | Usage |
|-----------|--------------|-------|
| Strength | Strength | Melee power, carrying |
| Agility | Agility | Movement, dodging |
| Health | **Endurance** | HP, stamina |
| Dexterity | Dexterity | Manual dexterity, fine motor |
| Perception | Perception | Awareness, senses |
| Intelligence | Intelligence | Knowledge, reasoning |
| Empathy | Empathy | Social, understanding |
| Will | **Willpower** | Mental fortitude, rituals |

**Non-standard (removed):**
- ❌ Charisma - Not in YAGS, replaced with Empathy

## Related Work

- **Attribute Migration** (Dec 2025): Removed "Charisma" from 73 session configs
- **Skill Remapping**: Guile, Corporate Influence → Empathy; Command, Intimidation → Willpower
- **Test Coverage**: `test_attribute_migration.py` has 13 regression tests

## Future Prevention

**Schema validation approach:**
- Pydantic Field descriptions drive JSON schema generation
- LLMs see these schemas → must be accurate!
- Any Field description listing attributes must match `MechanicsEngine.ATTRIBUTES`

**Check before PRs:**
```bash
# Ensure no Charisma in schema descriptions
grep -r "Charisma" scripts/aeonisk/multiagent/schemas/ --include="*.py"
# Should return: nothing (or only comments)
```

## Related Files

- `.claude/ATTRIBUTE_SYSTEM_CONFORMANCE.md` - Full attribute migration doc
- `tests/unit/test_attribute_migration.py` - Regression test suite
- `scripts/aeonisk/multiagent/character_validator.py` - Catches Charisma in configs
