# Pydantic AI Validation Error Debugging

**Date:** 2025-11-14
**Author:** Claude Code
**Purpose:** Enhanced debugging for Pydantic AI structured output validation failures

## Problem Statement

When Pydantic AI fails to validate LLM-generated structured output, the original error logging was minimal:

```
WARNING - Structured output failed (attempt 1/4), retrying in 3.13s: Exceeded maximum retries (1) for output validation
ERROR - DM: Structured output failed: Exceeded maximum retries (1) for output validation
```

This didn't tell us:
1. **What** specific field/value failed validation
2. **What** the raw model output was that couldn't be validated
3. **Why** the validation failed (underlying Pydantic error)
4. **Which** schema was being validated

Making debugging nearly impossible.

## Solution

Added comprehensive error logging at multiple levels:

### 1. Enhanced Stdout Logging (`llm_provider.py:540-601`)

**New output format:**
```
🔴 STRUCTURED OUTPUT VALIDATION ERROR (attempt 1/4):
  Exception: UnexpectedModelBehavior
  Message: Exceeded maximum retries (1) for output validation
  Schema: ActionResolution
  Model: claude-sonnet-4-5
  Underlying: ValidationError: Invalid enum value INVALID_ENUM_VALUE
  Raw response available: YES (1247 chars)

📋 Raw model response that failed validation:
{"narration": "...", "success_tier": "INVALID_VALUE", ...}
```

**Key improvements:**
- Exception type clearly labeled
- Schema name shown (e.g., `ActionResolution`)
- Underlying Pydantic validation error extracted from `__cause__`
- Raw model response extracted from `UnexpectedModelBehavior.body`
- Emoji markers for quick visual scanning (🔴, ⚠️, ❌)

### 2. JSONL Event Logging (`mechanics.py:1204-1271`)

**New event type: `pydantic_validation_failure`**

```json
{
  "event_type": "pydantic_validation_failure",
  "ts": "2025-11-14T15:46:20.535404",
  "session": "1b283999-9f94-4419-9f34-4c1773f50878",
  "round": 5,
  "agent_type": "dm",
  "agent_id": "dm_01",
  "schema_name": "ActionResolution",
  "exception_type": "UnexpectedModelBehavior",
  "error_message": "Exceeded maximum retries (1) for output validation",
  "attempt_number": 3,
  "max_attempts": 4,
  "is_final_attempt": false,
  "raw_model_response": "{\"narration\": \"...\", \"success_tier\": \"INVALID_ENUM_VALUE\"}",
  "underlying_error": "ValidationError: Invalid enum value INVALID_ENUM_VALUE",
  "action_context": {
    "action_type": "social",
    "player_id": "player_01",
    "description": "Provide spiritual counsel to Senior Ritualist..."
  }
}
```

**Benefits:**
- Machine-readable debugging data
- Searchable via `analyze_session.py`
- Correlates with specific rounds/actions
- Includes action context for reproduction

### 3. DM-Level Error Handling (`dm.py:5535-5605`)

**Enhanced exception handler:**
- Extracts raw response from `UnexpectedModelBehavior.body`
- Extracts underlying error from `__cause__`
- Logs to BOTH `structured_output_metrics` (general) and `pydantic_validation_failure` (detailed)
- Includes action context (type, player, description)

## Usage

### Analyzing Validation Failures in Sessions

```bash
# Find all validation failures
python scripts/analyze_session.py session.jsonl \
  --search event_type=pydantic_validation_failure \
  --fields schema_name,exception_type,attempt_number,raw_model_response

# Count failures by schema
python scripts/analyze_session.py session.jsonl \
  --search event_type=pydantic_validation_failure \
  --fields schema_name --count

# Get full details of a specific failure
python scripts/analyze_session.py session.jsonl \
  --search event_type=pydantic_validation_failure round=5 \
  --line <line_number>
```

### Testing the Logging

```bash
# Run validation logging test
python3 test_validation_logging.py

# Expected output:
# ✓ log_pydantic_validation_failure executed without error
# ✓ JSONL file contains 2 events
# ✓ Found pydantic_validation_failure event in JSONL
```

## Files Modified

1. **`scripts/aeonisk/multiagent/llm_provider.py`** (lines 540-601)
   - Enhanced exception handling in `generate_structured()` retry loop
   - Extracts raw response from `UnexpectedModelBehavior.body`
   - Logs detailed error info with emoji markers

2. **`scripts/aeonisk/multiagent/mechanics.py`** (lines 1204-1271)
   - New method: `log_pydantic_validation_failure()`
   - Captures comprehensive validation failure details
   - Logs to JSONL with `pydantic_validation_failure` event type

3. **`scripts/aeonisk/multiagent/dm.py`** (lines 5535-5605)
   - Enhanced exception handler in `_generate_llm_response_structured()`
   - Extracts raw response and underlying error
   - Logs to JSONL for ML analysis

## Example: Debugging a Real Failure

**User's original error:**
```
15:46:20 ERROR - Structured output failed: UnexpectedModelBehavior: Exceeded maximum retries (1) for output validation
```

**With new logging:**
```bash
# Check what failed
python scripts/analyze_session.py session_1b283999.jsonl \
  --search event_type=pydantic_validation_failure \
  --fields schema_name,raw_model_response

# Output shows:
{
  "schema_name": "ActionResolution",
  "raw_model_response": "{\"success_tier\": \"CRITICAL\", ...}"
}

# Diagnosis: Model used "CRITICAL" instead of "CRITICAL_FAILURE" enum value
# Fix: Update prompt to clarify enum values or adjust schema
```

## Common Validation Failures

Based on this logging, we can now identify patterns:

1. **Invalid enum values** - Model generates `CRITICAL` instead of `CRITICAL_FAILURE`
2. **Missing required fields** - Model omits `soulcredit_changes` (should be `[]` if empty)
3. **Type mismatches** - Model returns string where int expected
4. **Nested validation errors** - Issues in complex objects like `MechanicalEffects`

## Future Improvements

- [ ] Add retry attempt number to each retry log (currently only shows "attempt 1/4")
- [ ] Create analysis tool to aggregate common validation errors across sessions
- [ ] Add automatic schema suggestion when validation fails (e.g., "Did you mean CRITICAL_FAILURE?")
- [ ] Export validation failures to separate debugging log for offline analysis

## Related Documentation

- `.claude/CUSTOM_LOG_LEVELS.md` - Logging level documentation
- `scripts/aeonisk/multiagent/schemas/action_resolution.py` - ActionResolution schema
- `scripts/analyze_session.py` - Session analysis tool
- `test_validation_logging.py` - Test script demonstrating the logging
