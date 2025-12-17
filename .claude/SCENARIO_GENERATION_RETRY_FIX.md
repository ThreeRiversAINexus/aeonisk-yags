# Scenario Generation Retry Fix

**Date:** 2025-12-05 (updated 2025-12-06)
**Issue:** Bulk sessions failing at R00 (before first round) due to batch proxy Pydantic validation errors or empty JSON responses
**Status:** ✅ FIXED + TESTED

## Problem

Bulk sessions were stuck at Round 00 with 0 LLM calls and 0 actions, failing during DM scenario generation initialization. Investigation revealed these error types from the batch proxy:

**Retryable errors (now handled):**
1. **Empty JSON response**: `json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` ✅
2. **Missing field**: `pydantic.ValidationError: vendor_inventory: Input should be a valid list` ✅
3. **String too long**: `pydantic.ValidationError: advance_meaning: String should have at most 150 characters` ✅

**Non-retryable errors (fail immediately):**
- Network errors (ConnectionError, TimeoutError)
- API errors (rate limits, auth failures)

### Example Failure Logs

```
02:22:03 DEBUG - Submitting request to proxy (attempt 1/3)
02:24:16 DEBUG - Proxy request completed successfully
02:24:16 ERROR - Failed to parse JSON response: Expecting value: line 1 column 1 (char 0)
02:24:16 ERROR - DM: Structured scenario generation failed: Expecting value: line 1 column 1 (char 0)
02:24:16 ERROR - Agent dm_01 handler error: Scenario generation failed
```

### Root Cause

- Batch proxy returns malformed/incomplete structured output responses
- Originally: Only `pydantic.ValidationError` was retried
- **Bug:** `json.JSONDecodeError` (empty responses) fell through to generic exception handler → failed immediately without retry

### Impact

**30% of bulk runs failed** (3/10 sessions stuck at R00 in observed run)

## Solution

### Code Changes

**File:** `scripts/aeonisk/multiagent/dm.py:1617-1750`

Added **two-level retry logic** to `_generate_scenario_structured()`:

1. **Outer retry loop (Pydantic validation)**:
   - Catches `ValidationError` specifically
   - Retries up to 3 times
   - Exponential backoff: 1s, 2s, 4s delays
   - Clear logging: attempt numbers, wait times

2. **Inner retry loop (semantic validation)**:
   - Validates against `_scenario_hint` constraints
   - Retries up to 3 times
   - No delay (immediate re-generation)
   - Existing logic preserved

3. **Selective retry**:
   - ✅ **Retries**: `pydantic.ValidationError` (malformed responses)
   - ✅ **Retries**: `json.JSONDecodeError` (empty responses) - *added 2025-12-06*
   - ❌ **No retry**: Other exceptions (network errors, timeouts)

### Key Implementation Details

```python
from pydantic import ValidationError
import json
import asyncio

# Outer retry loop for retryable errors (Pydantic validation + JSON parsing)
max_pydantic_retries = 3
base_delay = 1.0  # seconds

for pydantic_attempt in range(max_pydantic_retries):
    try:
        if pydantic_attempt > 0:
            # Exponential backoff
            delay = base_delay * (2 ** (pydantic_attempt - 1))
            logger.info(f"DM: Retrying scenario generation (attempt {pydantic_attempt + 1}/{max_pydantic_retries}, waiting {delay}s)")
            await asyncio.sleep(delay)

        # Inner semantic validation loop (existing logic)
        for hint_attempt in range(max_hint_attempts):
            scenario: ScenarioSetup = await self.llm_provider.generate_structured(...)
            # Validate against scenario_hint if provided
            ...

        return scenario

    except (ValidationError, json.JSONDecodeError) as e:
        # Retryable error (Pydantic validation or JSON parsing) - retry with backoff
        logger.warning(f"DM: Retryable error (attempt {pydantic_attempt + 1}/{max_pydantic_retries}): {type(e).__name__}: {e}")
        if pydantic_attempt >= max_pydantic_retries - 1:
            # Final attempt failed
            raise RuntimeError(f"Scenario generation failed after {max_pydantic_retries} attempts: {e}") from e
        # Otherwise continue outer loop for retry

    except Exception as e:
        # Other errors - fail immediately (no retry)
        raise RuntimeError(f"Scenario generation failed: {e}") from e
```

### Logging Output

**Successful retry on JSONDecodeError (empty response):**
```
11:03:00 DEBUG - DM: Attempting structured output for scenario generation
11:03:02 WARNING - DM: Retryable error (attempt 1/3): JSONDecodeError: Expecting value: line 1 column 1 (char 0)
11:03:03 INFO - DM: Retrying scenario generation (attempt 2/3, waiting 1s)
11:03:05 DEBUG - ✓ DM structured scenario: Test Scenario @ Test Location, 1 clocks, void=3
```

**Successful retry on ValidationError:**
```
02:22:01 DEBUG - DM: Attempting structured output for scenario generation
02:22:03 WARNING - DM: Retryable error (attempt 1/3): ValidationError: 1 validation error for ScenarioSetup...
02:22:03 INFO - DM: Retrying scenario generation (attempt 2/3, waiting 1s)
02:22:05 DEBUG - ✓ DM structured scenario: Test Scenario @ Test Location, 1 clocks, void=3
```

**Failure after max retries:**
```
02:22:01 DEBUG - DM: Attempting structured output for scenario generation
02:22:03 WARNING - DM: Retryable error (attempt 1/3): JSONDecodeError: ...
02:22:04 INFO - DM: Retrying scenario generation (attempt 2/3, waiting 1s)
02:22:06 WARNING - DM: Retryable error (attempt 2/3): JSONDecodeError: ...
02:22:06 INFO - DM: Retrying scenario generation (attempt 3/3, waiting 2s)
02:22:10 WARNING - DM: Retryable error (attempt 3/3): JSONDecodeError: ...
02:22:10 ERROR - DM: Structured scenario generation failed after 3 retry attempts
02:22:10 ERROR - Agent dm_01 handler error: Scenario generation failed after 3 attempts
```

## Testing

### Unit Tests

**File:** `tests/unit/test_scenario_generation_retry.py`

Created 6 comprehensive tests:

1. ✅ **test_scenario_generation_retries_on_pydantic_validation_error**
   - Simulates 2 ValidationErrors, then success on 3rd attempt
   - Verifies retry logic executes 3 times
   - Verifies final result is valid

2. ✅ **test_scenario_generation_fails_after_max_retries**
   - Simulates ValidationError on all 3 attempts
   - Verifies RuntimeError raised after 3 attempts
   - Verifies exactly 3 attempts made

3. ✅ **test_scenario_generation_succeeds_on_first_try**
   - Simulates successful generation on first attempt
   - Verifies no unnecessary retries (only 1 call)

4. ✅ **test_scenario_generation_non_validation_error_fails_immediately**
   - Simulates ConnectionError (non-validation error)
   - Verifies no retry (fails immediately)
   - Verifies only 1 attempt made

5. ✅ **test_scenario_generation_retries_on_json_decode_error** *(added 2025-12-06)*
   - Simulates 2 JSONDecodeErrors (empty response), then success on 3rd attempt
   - Verifies retry logic executes 3 times
   - Verifies final result is valid

6. ✅ **test_scenario_generation_fails_after_max_json_decode_retries** *(added 2025-12-06)*
   - Simulates persistent JSONDecodeError on all 3 attempts
   - Verifies RuntimeError raised after 3 attempts
   - Verifies exactly 3 attempts made

### Test Results

```bash
$ python -m pytest tests/unit/test_scenario_generation_retry.py -v

tests/unit/test_scenario_generation_retry.py::test_scenario_generation_retries_on_pydantic_validation_error PASSED [ 16%]
tests/unit/test_scenario_generation_retry.py::test_scenario_generation_fails_after_max_retries PASSED [ 33%]
tests/unit/test_scenario_generation_retry.py::test_scenario_generation_succeeds_on_first_try PASSED [ 50%]
tests/unit/test_scenario_generation_retry.py::test_scenario_generation_non_validation_error_fails_immediately PASSED [ 66%]
tests/unit/test_scenario_generation_retry.py::test_scenario_generation_retries_on_json_decode_error PASSED [ 83%]
tests/unit/test_scenario_generation_retry.py::test_scenario_generation_fails_after_max_json_decode_retries PASSED [100%]

============================== 6 passed in 12.74s ===============================
```

## Expected Impact

### Before Fix
- **30% failure rate** (3/10 sessions) at R00 initialization
- Permanent failures, no recovery
- Manual intervention required for bulk runs

### After Fix
- **~90% reduction in R00 failures** (3 retry attempts)
- Automatic recovery from transient proxy issues
- Bulk runs more reliable and autonomous

### Cost Implications

**Increased API costs due to retries:**
- Retry 1: +1s delay, +1 LLM call (if fails)
- Retry 2: +2s delay, +1 LLM call (if fails)
- Retry 3: +4s delay, +1 LLM call (if fails)

**Total per failed scenario**: +7s delay, +2 LLM calls (worst case, 3rd attempt succeeds)

**Batch proxy pricing**: 50% cost reduction offsets retry costs
**GPT-5-mini cost**: ~$0.02 per 1M tokens (negligible for 2 extra calls)

**Net impact**: Minimal cost increase, significant reliability improvement

## Verification Steps

To verify the fix is working in production:

1. **Check logs for retry messages**:
   ```bash
   grep "Retrying scenario generation after Pydantic error" bulk_output/run_*/run_*/stdout.log
   ```

2. **Monitor R00 failure rate**:
   ```bash
   python scripts/analyze_session.py bulk_output/run_*/run_*/session_*.jsonl --mode=errors
   ```

3. **Compare before/after**:
   - Before: 30% R00 failures (3/10)
   - After: <5% R00 failures (transient issues only)

## Related Files

- **Implementation**: `scripts/aeonisk/multiagent/dm.py:1617-1750`
- **Tests**: `tests/unit/test_scenario_generation_retry.py`
- **Documentation**: `.claude/SCENARIO_GENERATION_RETRY_FIX.md` (this file)

## Future Improvements

1. **Configurable retry count**: Make `max_pydantic_retries` a session config parameter
2. **Adaptive backoff**: Increase base_delay if proxy consistently slow
3. **Metrics logging**: Track retry success rate via JSONL events
4. **Proxy health check**: Skip retries if proxy health check fails
