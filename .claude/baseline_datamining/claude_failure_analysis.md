# Claude Opus 4.6 Failure Analysis

## Summary

All 5 Anthropic Claude Opus 4.6 runs failed with identical error:
```
Structured output generation failed: Failed to generate valid ActionResolution after 3 attempts:
Expecting value: line 1 column 1 (char 0)
```

**100% failure rate.** Claude is the only model that failed. All other models (GPT-5.2, Grok 4, Gemini 2.5 Pro, DeepSeek V3.2) had 100% success.

## Failure Pattern

| Run | Round | Empty Response Attempts | Successful Calls Before | Started | Failed |
|-----|-------|------------------------|------------------------|---------|--------|
| 0004 | R2 | 6 (3 intermittent + 3 fatal) | 21 | 11:32 | 11:40 |
| 0009 | R1 | 3 (all fatal) | 8 | 12:08 | 12:12 |
| 0014 | R1 | 3 (all fatal) | 8 | 13:06 | 13:09 |
| 0019 | R1 | 3 (all fatal) | 8 | 13:47 | 13:50 |
| 0024 | R1 | 3 (all fatal) | 8 | 14:26 | 14:29 |

Run 0004 got further (Round 2) because some earlier DM calls succeeded intermittently. The other 4 all failed at the first ActionResolution attempt.

## Root Cause: Intermittent Empty Responses from Anthropic API

**NOT markdown wrapping** (the `llm_batch_provider.py` already strips ```json``` fences at lines 212-219). The actual error chain:

1. Session calls DM structured output (ActionResolution) through proxy -> Anthropic API
2. Anthropic API responds HTTP 200 but **content is empty or whitespace-only**
3. Proxy returns `{"status": "completed", "content": "<whitespace>"}` — doesn't detect empty content (non-null)
4. YAGS client passes `if not content` check (whitespace is truthy in Python)
5. After markdown stripping + `.strip()`, content becomes `""`
6. `json.loads("")` raises `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
7. After 3 consecutive failed retries, session crashes

### Key Evidence

**Provider-specific:** 18 empty response attempts total, ALL from Anthropic Claude Opus 4.6. Zero from any other provider across ~2,500 successful API calls.

**Prompt-size correlated:** Smaller prompts (player actions, ~4K tokens) always succeeded. Large DM ActionResolution prompts (~28K input tokens) failed ~50% of the time.

**Not load-related:** Claude runs were sequential (spread over 3 hours, 11:32-14:29). No concurrent sessions competing for API quota.

**Not reproducible post-experiment:** Testing the same prompts through the same proxy after the run yields 100% success (8/8 attempts). Suggests Anthropic service degradation during the experiment window.

**Proxy stats confirm:** 19 failed requests out of 2,545 total (0.75%). 18 correspond to the empty response attempts in Claude runs.

## Event Sequence in JSONL (Run 0004, Round 2)

```
Line 68: llm_call (player_01, round 2) — player action succeeds
Line 69: action_declaration (round 2) — player action declared
Line 70: adjudication_start (round 2) — DM begins adjudicating
Line 71: structured_output_metrics (dm_01, round 2) — structured output attempted
Line 72: pydantic_validation_failure (dm_01, round 2) — JSON parse fails
Line 73: session_error (round 2) — session crashes
```

## Defensive Improvements

1. **Better empty content detection** in `unified_llm_client.py` (line 285-291): Check `if not content or not content.strip()` instead of just `if not content`. This catches whitespace-only responses and triggers direct API fallback.

2. **Same fix in structured output retry** (`llm_batch_provider.py` line 207): `if not content or not content.strip()` to catch whitespace before attempting JSON parse.

3. **Debug logging for parse failures** (`llm_batch_provider.py` line 227-233): Log `repr(content[:200])` when JSON parsing fails so we can diagnose exactly what was returned.

4. **Direct API fallback on empty content**: When proxy returns empty content, automatically fall back to `_direct_completion` instead of retrying through the same proxy.

## Relevant Files

- **Client proxy code:** `scripts/aeonisk/multiagent/unified_llm_client.py` (lines 236-358: `_proxy_completion`)
- **Structured output retry:** `scripts/aeonisk/multiagent/llm_batch_provider.py` (lines 182-307: `generate_structured`)
- **DM resolution entry:** `scripts/aeonisk/multiagent/structured_output_helpers.py` (lines 36-165)

## Impact on Experiment

- Claude Opus 4.6 has **zero usable combat data** from this batch
- The failure is likely transient API degradation, not a fundamental incompatibility
- The 20 successful sessions across 4 models provide valid baseline data
- Retry with defensive fixes above before attributing behavioral differences to Claude
