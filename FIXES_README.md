# Transfer & Echo-Calibrator Rental Fixes

This document describes two bug fixes implemented for the Soulcredit transfer system and Echo-Calibrator rental support.

## Quick Verification

To verify both fixes are working:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run verification script (fast, ~1 second)
python3 scripts/verify_fixes.py

# Run full unit tests (comprehensive, ~1 second)
python -m pytest tests/unit/test_transfer_validation.py tests/unit/test_echo_calibrator_rental.py -v
```

Expected output:
```
✅ ALL VERIFICATION TESTS PASSED

Both fixes are working correctly:
  1. Multi-target transfers (comma/semicolon) are rejected
  2. Echo-Calibrator rentals (3 formats) are recognized
```

---

## Fix #1: Multi-Target Transfer Validation

### Problem
When players declared transfers to multiple NPCs using semicolons (e.g., `"Mira Solis; Sera Vex; Jace Kordell"`), the validation treated the entire string as a single target name instead of detecting it as invalid multi-target syntax.

**Error observed:**
```
Transfer pre-validation FAILED: Target character 'Mira Solis (tgt_9qov); Sera Vex (tgt_1i5j); Jace Kordell (tgt_dbkt)' not found
```

### Solution
Updated `mechanics.py:2517` to detect semicolons in addition to commas:

```python
# Before
if ',' in transfer_target:
    return TransferValidation(is_valid=False, ...)

# After
if ',' in transfer_target or ';' in transfer_target:
    return TransferValidation(is_valid=False, ...)
```

### Now Rejects
- Comma-separated: `"Target1, Target2"`
- Semicolon-separated: `"Target1; Target2; Target3"`
- Mixed formats: `"tgt_abc, tgt_def"`

### Error Message
```
Multi-target transfers not supported. Transfer to one recipient at a time. Got: 'Mira Solis; Sera Vex; Jace Kordell'
```

### Tests
- **File**: `tests/unit/test_transfer_validation.py`
- **Coverage**: 8 tests (all passing)
  - Comma-separated rejection
  - Semicolon-separated rejection
  - Single target acceptance
  - Edge cases (empty, nonexistent, insufficient currency)

---

## Fix #2: Echo-Calibrator Rental Recognition

### Problem
Mira Solis had `"echo_calibrator_rental"` in her inventory (from vendor rental), but attunement validation only checked for `"Echo-Calibrator"` (the purchased variant), causing validation failure:

```
❌ Attunement auto-failed for Mira Solis: No Echo-Calibrator available (not in inventory)
```

### Root Cause
**Naming mismatch** between rental and purchased items:
- **Purchased**: `"Echo-Calibrator"` (vendor display name)
- **Rental (config)**: `"echo_calibrator_rental"` (inventory_key in session config)
- **Rental (display)**: `"Echo Calibrator Rental"` (alternate formatting)

### Solution
Updated `mechanics.py:2793-2802` to check for all three variants:

```python
# Check for both purchased and rental Echo-Calibrators
# Purchased: "Echo-Calibrator" (display name from vendor)
# Rental: "echo_calibrator_rental" (inventory_key from config) OR "Echo Calibrator Rental" (alternate format)
has_purchased = character_state.inventory.get("Echo-Calibrator", 0) > 0
has_rental = (
    character_state.inventory.get("echo_calibrator_rental", 0) > 0 or
    character_state.inventory.get("Echo Calibrator Rental", 0) > 0
)

if not (has_purchased or has_rental):
    return AttunementValidation(is_valid=False, ...)
```

### Now Accepts
1. **Purchased**: `inventory["Echo-Calibrator"] = 1`
2. **Rental (config format)**: `inventory["echo_calibrator_rental"] = 1`
3. **Rental (display format)**: `inventory["Echo Calibrator Rental"] = 1`

### Tests
- **File**: `tests/unit/test_echo_calibrator_rental.py`
- **Coverage**: 7 tests (all passing)
  - Purchased Echo-Calibrator acceptance
  - Rental Echo-Calibrator acceptance (both formats)
  - Combined purchased + rental acceptance
  - Missing Echo-Calibrator rejection
  - Zero quantity rejection
  - Optional usage (no calibrator required when not requested)

---

## Code Changes Summary

### Files Modified
1. **scripts/aeonisk/multiagent/mechanics.py**
   - Line 2517: Added semicolon detection for multi-target transfers
   - Lines 2793-2802: Enhanced Echo-Calibrator rental support (3 variants)

2. **tests/unit/test_transfer_validation.py** (NEW)
   - 8 comprehensive tests for transfer validation

3. **tests/unit/test_echo_calibrator_rental.py** (NEW)
   - 7 comprehensive tests for Echo-Calibrator rental

4. **scripts/verify_fixes.py** (NEW)
   - Quick verification script for both fixes

### Test Coverage
- **15 total tests** (all passing)
  - Transfer validation: 8/8 ✅
  - Echo-Calibrator rental: 7/7 ✅

---

## Retrying/Verifying in a Live Session

To test the fixes in a real game session:

### 1. Multi-Target Transfer Test

```bash
# Run a session with NPCs
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_npc_vendor_test.json

# Player declares multi-target transfer (should fail gracefully)
# Example player action:
# "Transfer 10 Drip to Mira, Sera, and Jace for purchases"

# Expected DM narration:
# "...multi-target transfers aren't supported. The request listed multiple recipients;
# only a single recipient can be named, so nothing moves."
```

### 2. Echo-Calibrator Rental Test

```bash
# Run session with vendor offering Echo-Calibrator rental
python3 scripts/run_multiagent_session.py scripts/session_configs/openai/session_config_economic_comprehensive_test.json

# Player purchases/rents Echo-Calibrator
# Player attempts attunement using Echo-Calibrator

# Expected: Attunement validation passes (no "not in inventory" error)
# Expected: Player can use rented calibrator for attunement rituals
```

### 3. Quick Unit Test Retry

```bash
# Run just the new tests
source .venv/bin/activate
python -m pytest tests/unit/test_transfer_validation.py::TestTransferValidationMultiTarget::test_semicolon_separated_targets_rejected -v
python -m pytest tests/unit/test_echo_calibrator_rental.py::TestEchoCalibratorRental::test_rental_echo_calibrator_accepted -v

# Run all new tests
python -m pytest tests/unit/test_transfer_validation.py tests/unit/test_echo_calibrator_rental.py -v
```

---

## Design Philosophy

Both fixes follow the project's core principles:

1. **Minimal changes** - Surgical fixes targeting specific issues
2. **Comprehensive testing** - Test-driven approach with edge cases
3. **Clear error messages** - DM narrations explain what went wrong
4. **Backwards compatibility** - Supports multiple naming conventions
5. **No keyword detection** - Uses structured validation, not text parsing

---

## Future Improvements

### Multi-Target Transfers
While multi-target transfers are currently **not supported** (rejected with clear error), they could be implemented in the future by:

1. Parsing target list into individual recipients
2. Validating each recipient exists
3. Executing transfers sequentially (or in batch)
4. Providing detailed feedback for partial failures

**Current approach**: Force players to declare separate transfer actions, which:
- Simplifies validation logic
- Makes ML training data clearer (explicit individual transfers)
- Allows DM to narrate each transfer meaningfully

### Echo-Calibrator Unification
Consider standardizing inventory keys across vendor types:
- Use consistent `"echo_calibrator"` key for both purchased and rental
- Track rental status via `item_metadata` instead of different keys
- Simplifies validation (single key to check)

**Current approach**: Support multiple formats for robustness and backward compatibility.

---

## Contact

For issues or questions about these fixes:
- **Tests failing**: Run `python3 scripts/verify_fixes.py` for diagnostics
- **Session issues**: Check logs with `grep "Echo-Calibrator\|multi-target" session.log`
- **Bug reports**: File issue with session JSONL and error logs

---

**Last Updated**: 2025-11-20
**Fixes By**: Claude Code (Anthropic)
**Test Status**: ✅ All 15 tests passing
