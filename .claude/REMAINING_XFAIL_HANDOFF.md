# Remaining XFailed Tests - Handoff Document

**Date:** 2025-12-01
**Branch:** `bulk-generation`
**Previous Work:** Resolved 20 xfailed tests (commit e4b6826)

## Current Test Suite Status

- **Passed:** 2147
- **Skipped:** 107
- **XFailed:** 13 (down from 15 after removing obsolete tests)
- **Pass Rate:** 99.96%

---

## Priority 1: ActionResolution Schema Refactoring

**File:** `tests/unit/test_outcome_modifiers_display.py`
**Tests:** 3 (entire `TestOutcomeModifiersDisplay` class)
**Reason:** "ActionResolution schema changed - no longer allows setting fields directly; needs refactoring"

### Problem

The tests try to set fields on `ActionResolution` after construction:

```python
resolution = ActionResolution(
    narration="...",
    success_tier=SuccessTier.GOOD,
    margin=8,
    effects=MechanicalEffects()
)

# These lines FAIL - fields are frozen/computed after Pydantic hardening
resolution.intent = "Hack terminal"
resolution.attribute = "Intelligence"
resolution.skill = "Tech"
resolution.roll = 12
# etc.
```

### Fix Required

Refactor tests to construct `ActionResolution` with all required fields upfront. Check the `ActionResolution` schema in `schemas/action_resolution.py` for:
- Which fields are required at construction
- Which are computed properties
- Which have default values

Example fix pattern:
```python
resolution = ActionResolution(
    narration="...",
    success_tier=SuccessTier.GOOD,
    margin=8,
    effects=MechanicalEffects(),
    # Add all fields needed for format_resolution_for_narration()
    intent="Hack terminal",
    attribute="Intelligence",
    skill="Tech",
    # ... etc
)
```

---

## Priority 2: Environmental Changes Propagation Bug

**File:** `tests/unit/test_agent_context.py`
**Test:** `test_environmental_changes_persist`
**Reason:** "Known bug: Environmental changes may not always propagate to next round context"

### Problem

When the DM describes environmental changes in narration (fire, smoke, debris, cover, darkness), those changes don't consistently appear in the next round's player/enemy context prompts.

### Root Cause Investigation

1. Check `session.py` - how is round context built?
2. Check `dm.py` - does DM output environmental state?
3. Check `SharedState` - is there an `environment` or `scene_state` field?
4. Check prompt templates - do they include environmental context?

### Likely Fix Areas

- **Option A:** Add `environmental_state` field to `RoundSynthesis` schema for DM to populate
- **Option B:** Parse environmental keywords from narration and track in `SharedState`
- **Option C:** Add explicit `SceneState` tracking in mechanics engine

The test itself documents what should happen:
```python
# Look for environment mentions in round 1
for res in round1_resolutions:
    narration = res.get('context', {}).get('narration', '')
    if any(word in narration.lower() for word in ['fire', 'smoke', 'debris', 'cover', 'darkness']):
        env_changes.append(narration[:100])

# These should appear in round 2 prompts
```

---

## Priority 3: DM Behavior / Prompt Engineering

**File:** `tests/unit/test_enemy_group_removal.py`
**Tests:** 2 in `TestKnownTargetingBugs` class

### Bug 1: DM Invents Target IDs

**Test:** `test_dm_uses_actual_target_ids`

DM creates semantic IDs like `tgt_heavy_gunners` instead of using the actual randomized IDs from the `target_id_mapper` (e.g., `tgt_9i1b`).

**Fix:** Improve DM prompts to emphasize using EXACT target IDs from the provided combatant list. Check:
- `prompts/claude/en/dm/dm_action_resolution.yaml`
- `prompts/openai/en/dm/dm_action_resolution.yaml`

Add explicit instruction like:
```
IMPORTANT: Use the EXACT target_id values provided (e.g., 'tgt_9i1b').
Do NOT invent descriptive IDs like 'tgt_heavy_gunners'.
```

### Bug 2: DM Not Using Structured Damage Effects

**Test:** `test_dm_uses_structured_damage_effects`

DM mentions damage in narration text but doesn't populate the `effects.damage` field in `ActionResolution`.

**Fix:** Improve DM prompts to always fill structured output fields when mechanical effects occur. Check `ActionResolution` schema examples in prompts.

Add explicit instruction like:
```
When damage is dealt, you MUST populate effects.damage with:
- dealt: numeric damage value
- target: target_id of damaged entity
- damage_type: weapon/void/environmental
```

---

## Remaining XFailed Tests (Lower Priority)

### test_action_type_classification.py (3 tests)

**Reason:** Historical fixture contains LLM misclassification

These tests use a recorded fixture (`action_type_investigate_bug.jsonl`) that captured an LLM bug where combat actions were classified as "investigate". The fixture is historical evidence of the bug.

**Fix options:**
1. Regenerate fixture with improved prompts (already done in `player_intent.yaml`)
2. Delete tests if the fixture is no longer needed for regression tracking
3. Keep as documentation of historical LLM behavior

---

## Files Modified in Previous Session

For reference, these files were changed to fix 20 xfailed tests:

| File | Change |
|------|--------|
| `scripts/aeonisk/multiagent/player.py` | Added 3-retry with exponential backoff |
| `scripts/aeonisk/multiagent/prompts/claude/en/player/player_intent.yaml` | Combat classification improvements |
| `tests/unit/test_bulk_runner.py` | Fixed directory structure expectations |
| `tests/unit/test_batch_proxy_provider.py` | Updated logger field assertion |
| `tests/unit/test_vendor_social_targeting.py` | Removed self-failing test data |
| `tests/unit/test_dm_npc_integration.py` | Schema migration to ConversionDecisions |
| `tests/unit/test_modifiers_integration.py` | Deleted obsolete test |
| `tests/unit/test_pre_round_entity_lifecycle.py` | Converted to pytest-asyncio |
| `tests/unit/test_openai_provider.py` | Fixed mock target path |
| `tests/unit/test_two_phase_action_generation.py` | Removed xfail (retry logic added) |
| `tests/unit/test_outcome_parser.py` | Deleted obsolete legacy text parsing tests |

---

## Quick Start for Next Session

```bash
# Check current xfail count
grep -r "pytest.mark.xfail" tests/unit/ --include="*.py" | wc -l

# Run specific failing test file
python -m pytest tests/unit/test_outcome_modifiers_display.py -v

# Run full suite to verify
python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```
