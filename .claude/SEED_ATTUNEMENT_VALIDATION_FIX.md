# Seed Attunement Validation Fix

**Date:** 2025-11-20
**Issue:** Players attempting to attune seeds they don't possess
**Status:** ✅ FIXED

## Problem Statement

Players were declaring attunement actions even when they had zero Raw Seeds in their energy_purse. The validation function `validate_attunement()` existed but was never called in production code, only in unit tests. This caused:

1. Players wasting LLM API calls on impossible actions
2. Confusing error states when seed consumption failed
3. Actions reaching DM for adjudication despite being mechanically impossible
4. Runtime errors: "Failed to consume seed - no Raw Seeds in energy purse!"

## Root Cause Analysis

**Validation function existed but was orphaned:**
- `mechanics.py:2675-2831` - `validate_attunement()` function ✅ Implemented
- Only called in `tests/unit/test_attunement.py` ❌ Never used in production
- No integration between player action flow and validation layer ❌ Gap

**Similar to purchase validation pattern, but missed during implementation:**
- Purchase: `session.py:3484-3558` validates before DM ✅
- Transfer: `session.py:3559-3701` validates before DM ✅
- Attunement: **NO VALIDATION** ❌ **[BUG]**

## Solution Implemented

### 1. Session-Level Validation Hook (session.py:3460-3506)

Added pre-validation in `_handle_action_declared()` to check inventory BEFORE buffering action:

```python
# PRE-VALIDATE ATTUNEMENT ACTIONS (check inventory before buffering)
action_type = message.payload.get('action_type')
if action_type == 'attune':
    validation = mechanics.validate_attunement(
        character_state=player_agent.character_state,
        target_energy=target_energy,
        altar_id=altar_id,
        use_echo_calibrator=use_echo_calibrator
    )

    if not validation.is_valid:
        # REJECT action - don't buffer it, don't send to DM
        logger.warning(f"❌ ATTUNEMENT REJECTED: {validation.failure_reason}")
        print(f"\n❌ [{player_agent.character_state.name}] Attunement action INVALID: {validation.failure_reason}\n")
        return  # Early exit prevents buffering
```

**What this validates:**
- ✅ Player has at least one Raw Seed
- ✅ `target_energy` is specified
- ✅ Altar exists (if `altar_id` provided)
- ✅ Echo-Calibrator in inventory (if `use_echo_calibrator=True`)
- ✅ Sufficient Drip for upkeep (every 3rd calibrator use)

**Behavior:**
- Valid actions proceed normally to DM for adjudication
- Invalid actions are rejected immediately, never reach DM
- Player sees clear error message in console
- Session logs validation failure reason

### 2. Player Prompt Enhancement (player.py:1119-1128)

Added explicit warning when Raw Seeds = 0:

```python
if raw_count == 0:
    seeds_display = f"""⚠️ **NO RAW SEEDS AVAILABLE** - You CANNOT perform attunement!
- Raw Seeds: 0 (REQUIRED for attunement - acquire more via search/purchase)
- Attuned Seeds: {attuned_count} (stable, ritual fuel)
- Hollow Seeds: {hollow_count} (illicit, black market commodity)"""
```

**Impact:** LLM sees clear warning and should avoid declaring impossible actions.

### 3. Action Prompt Documentation (player_action_attune.yaml:16-22)

Added prerequisite check section:

```yaml
## ⚠️ PREREQUISITE CHECK

**REQUIRED:** You MUST possess at least ONE Raw Seed to attempt attunement.

- If you have zero Raw Seeds (check seeds_display below), you CANNOT declare this action.
- Choose a different action instead (search for seeds, purchase from vendor, explore environment).
- Attunement without seeds will be REJECTED by the session coordinator.
```

**Impact:** Attunement-specific prompt now explicitly states requirements.

### 4. Integration Tests (test_attunement_validation_integration.py)

Created comprehensive integration test suite documenting expected behavior:

- ✅ Validation called on attunement action declaration
- ✅ Actions rejected when no seeds
- ✅ Actions proceed when seeds available
- ✅ Altar validation
- ✅ Echo-Calibrator validation
- ✅ Clear error messages

### 5. Test Session Config (session_config_attunement_validation_test.json)

Created session config that specifically tests the validation:

- Player with Attunement skill 4, Willpower 5 (skilled attunement specialist)
- Player goal explicitly mentions attunement
- Functioning altar present in scenario (tempting but unusable)
- **Zero Raw Seeds** in energy_purse (hard requirement violation)
- Expected: Player should search/explore instead of attempting attunement

## Validation Pattern

All hard-requirement inventory validations now follow consistent pattern:

```python
# 1. Detect action type requiring inventory
if action_type == 'TARGET_TYPE':
    # 2. Extract parameters and validate
    validation = mechanics.validate_XXX(character_state, ...)

    # 3. Reject if invalid (before buffering)
    if not validation.is_valid:
        logger.warning(f"❌ {ACTION} REJECTED: {validation.failure_reason}")
        print(f"\n❌ [...] {validation.failure_reason}\n")
        return  # Prevents buffering and DM adjudication

    # 4. If valid, continue to buffering
```

**Actions using this pattern:**
- ✅ Purchase (currency validation)
- ✅ Transfer (item/currency validation)
- ✅ Attunement (seed/equipment validation) **[NEWLY ADDED]**

## Files Modified

1. **session.py:3460-3506** - Added attunement validation hook
2. **player.py:1119-1128** - Added zero-seed warning to seeds_display
3. **player_action_attune.yaml:16-22** - Added prerequisite check section
4. **test_attunement_validation_integration.py** - NEW FILE - Integration tests
5. **session_config_attunement_validation_test.json** - NEW FILE - Test config
6. **INVENTORY_VALIDATION_AUDIT.md** - NEW FILE - Comprehensive audit

## Testing Strategy

### Unit Tests
```bash
# Existing validation function tests (already passing)
python -m pytest tests/unit/test_attunement.py::TestAttunementValidation -v
```

### Integration Tests
```bash
# New session flow tests (documenting expected behavior)
python -m pytest tests/unit/test_attunement_validation_integration.py -v
```

### Session Test
```bash
# Manual verification with contrived scenario
source .venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_attunement_validation_test.json
```

**Expected outcome:**
1. Player sees ⚠️ warning in seeds_display
2. Player chooses search/explore action (not attunement)
3. If player attempts attunement anyway, console shows rejection message
4. No attunement action appears in JSONL logs

## Verification Against User's Report

**Original Issue:** "players keep trying to attune seeds they dont have"

**Fix prevents this by:**
1. **Player-side warning** - LLM sees explicit "NO RAW SEEDS AVAILABLE" message
2. **Session-side rejection** - Invalid actions blocked before DM sees them
3. **Clear error feedback** - Console shows why action was rejected
4. **No wasted API calls** - DM never processes impossible actions

**Before fix:**
```
Player → Declares attunement (0 seeds) → DM adjudicates → Seed consumption → ERROR
```

**After fix:**
```
Player → Sees warning (0 seeds) → Chooses different action
   OR
Player → Declares attunement anyway → Session validation → REJECTED (before DM)
```

## Related Work

### Comprehensive Inventory Audit

Created `INVENTORY_VALIDATION_AUDIT.md` documenting validation coverage for ALL inventory-dependent actions:

**Actions with hard requirements (all validated):**
- ✅ Purchase - Currency must be available
- ✅ Transfer - Items/currency must be owned
- ✅ Attunement - Raw Seeds required

**Actions with soft requirements (intentionally not validated):**
- Rituals - Can proceed without tools/offerings (applies penalties)
- Combat - Weapons optional (narrative effectiveness)
- Support - Consumables optional (DM adjudicates)

**Conclusion:** No further validation gaps identified.

## Future Enhancements (Optional)

### Player Re-declaration Mechanism
Currently, rejected actions cause player to effectively pass turn. Future work could implement message-based re-declaration request to prompt player for alternative action.

### Ritual Offering Warnings
Consider adding soft warnings (like void warnings) when players have low offerings, guiding LLM decision-making without blocking actions.

## Success Criteria

✅ Players cannot declare attunement without Raw Seeds (blocked at session level)
✅ Player prompts warn when seeds unavailable (LLM guidance)
✅ Validation follows purchase/transfer pattern (consistency)
✅ No wasted DM API calls for impossible actions (efficiency)
✅ Clear error messages (user experience)
✅ Comprehensive test coverage (reliability)
✅ All inventory actions audited (completeness)

## Conclusion

The seed attunement validation gap has been closed. The fix follows established patterns (purchase/transfer validation), provides clear user feedback, and prevents the reported issue of players attempting impossible attunement actions.

**All hard-requirement inventory validations are now complete.**
