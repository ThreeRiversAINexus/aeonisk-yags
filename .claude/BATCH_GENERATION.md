# Batch Generation Architecture

**Status:** ✅ Production Ready
**Created:** 2025-11-26
**Last Updated:** 2025-11-26

## Overview

Batch generation support enables cost-optimized bulk execution of aeonisk-yags multi-agent sessions by routing LLM requests through a batching proxy server. This provides 50% cost reduction for large-scale training data generation runs.

## Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Bulk Session Runner (bulk_session_runner.py)               │
│  - Orchestrates N parallel sessions via ProcessPoolExecutor │
│  - Automatic proxy health checks                            │
│  - Resume capability for failed runs                         │
└────────────┬─────────────────────────────────────────────────┘
             │ spawns N subprocesses
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Individual Session (run_multiagent_session.py)             │
│  - DM, Players, Enemies each use LLM providers              │
└────────────┬─────────────────────────────────────────────────┘
             │ provider="batch_proxy"
             ▼
┌──────────────────────────────────────────────────────────────┐
│  BatchProxyProvider (llm_batch_provider.py)                  │
│  - Wraps UnifiedAIClient                                     │
│  - Implements LLMProvider interface                          │
│  - Handles structured output via JSON schema                 │
└────────────┬─────────────────────────────────────────────────┘
             │ use_proxy=true
             ▼
┌──────────────────────────────────────────────────────────────┐
│  UnifiedAIClient (unified_llm_client.py)                     │
│  - Provider abstraction (OpenAI/Anthropic)                   │
│  - Proxy routing with automatic fallback                     │
│  - 3 retries with exponential backoff                        │
└────────────┬─────────────────────────────────────────────────┘
             │ HTTP POST /submit
             ▼
┌──────────────────────────────────────────────────────────────┐
│  LLM Batching Proxy (aeonisk-transmedia-pipeline)            │
│  - Queues requests by provider                               │
│  - Batches when threshold reached (100 reqs or 5min)         │
│  - Submits to provider Batch APIs                            │
│  - Polls for completion, returns results                     │
└────────────┬─────────────────────────────────────────────────┘
             │ Batch API
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Provider APIs (OpenAI / Anthropic)                          │
│  - 50% cost reduction via Batch APIs                         │
│  - Processing time: <24 hours                                │
└──────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Copy vs Import for UnifiedAIClient

**Decision:** Copy code from transmedia-pipeline (not import as dependency)

**Rationale:**
- **Standalone:** No cross-project dependency
- **Flexibility:** Can adapt client for aeonisk-yags needs
- **Stability:** Changes to transmedia-pipeline won't break this project
- **Trade-off:** Code duplication (~300 lines), but acceptable for isolation

### 2. Keep Existing Providers

**Decision:** Batch proxy as new provider, keep Anthropic/OpenAI providers

**Rationale:**
- **Backward compatibility:** All existing session configs work unchanged
- **Direct fallback:** If proxy unavailable, can switch to direct provider
- **Testing:** Can compare batch vs direct results
- **Flexibility:** Mix providers (e.g., DM via proxy, players direct)

### 3. Subprocess vs Async for Orchestrator

**Decision:** Use subprocess-based parallelism (ProcessPoolExecutor)

**Rationale:**
- **No refactoring:** Existing session code is synchronous
- **Isolation:** Each session runs in separate process (crash isolation)
- **True parallelism:** Not limited by GIL
- **Trade-off:** Higher memory usage (multiple Python interpreters)

**Alternative considered:** Async with `asyncio.gather()` would require:
- Converting all session code to async/await
- Refactoring DM, Player, Enemy agents
- Risk of breaking existing functionality
- Estimated effort: 20-40 hours

### 4. Structured Output via JSON Schema

**Decision:** Augment system prompt with JSON schema, parse response

**Rationale:**
- **Provider-agnostic:** Works with any LLM backend
- **No Pydantic AI dependency:** Simpler client implementation
- **Known limitation:** Batch APIs may not support native structured output
- **Fallback:** Prompt engineering proven to work in testing

**Alternative considered:** Native structured output via `response_format`:
- OpenAI Batch API: Unclear if supported (docs don't mention)
- Anthropic Message Batches: No structured output support
- Would require per-provider implementations

### 5. Session Config Strategy

**Decision:** Explicit proxy config in session JSON, environment fallback

**Rationale:**
- **Per-agent control:** Each agent can use different proxy strategy
- **Environment override:** `USE_LLM_PROXY=true` as global enable
- **Explicit config wins:** Session config overrides environment
- **Example use case:** DM via proxy (normal priority), players direct (high priority)

## Implementation Details

### BatchProxyProvider Interface

```python
class BatchProxyProvider(LLMProvider):
    """LLM provider that routes through batching proxy."""

    async def generate(self, prompt, system_prompt, ...) -> LLMResponse:
        """Generate text via proxy (unstructured)."""

    async def generate_structured(self, prompt, result_type, ...) -> BaseModel:
        """Generate Pydantic-validated structured output."""

    def get_prompt_dir(self) -> str:
        """Return underlying provider's prompt directory."""

    def health_check(self) -> Dict:
        """Check proxy server health."""
```

### Bulk Session Runner Features

**Parallel Execution:**
- `ProcessPoolExecutor` with configurable worker count
- Each worker spawns `run_multiagent_session.py` subprocess
- Timeout per session: 1 hour (configurable)

**Resume Capability:**
- Scans output directory for `session_run_NNNN.jsonl` files
- Extracts completed run IDs from filenames
- Skips completed runs when `--resume` flag set
- Useful for recovering from crashes or resource limits

**Health Check:**
- Pre-flight proxy health check via `/health` endpoint
- 5-second timeout for reachability test
- Fails fast if proxy unavailable (unless `--skip-health-check`)

**Statistics Tracking:**
- Per-run: duration, tokens, rounds, success/failure
- Aggregated: success rate, avg duration, throughput (runs/hour)
- Summary report written to `bulk_run_summary.json`

### Token Estimation for Batch Proxy

**Problem:** Proxy mode doesn't return token counts synchronously

**Solution:** Estimate tokens for logging:
```python
# Rough approximation: 1 token ≈ 4 characters
estimated_tokens = {
    'input': (len(system_prompt) + len(prompt)) // 4,
    'output': len(response) // 4,
    'total': (len(system_prompt) + len(prompt) + len(response)) // 4
}
```

**Accuracy:** ~80% accurate for English text (OpenAI tokenizer averages 1 token = 4 chars)

**Alternative:** Could fetch actual token counts from proxy `/batches/{batch_id}` endpoint after batch completes, but requires async polling

## Configuration Examples

### Single Session with Batch Proxy

```json
{
  "session_name": "batch_test",
  "max_turns": 5,
  "agents": {
    "dm": {
      "llm": {
        "provider": "batch_proxy",
        "model": "gpt-5-mini",
        "underlying_provider": "openai",
        "use_proxy": true,
        "proxy_url": "http://localhost:8000",
        "proxy_strategy": "auto"
      }
    },
    "players": [
      {
        "name": "Character",
        "llm": {
          "provider": "batch_proxy",
          "model": "gpt-5-mini",
          "underlying_provider": "openai",
          "use_proxy": true
        }
      }
    ]
  }
}
```

### Bulk Run with 100 Sessions

```bash
# Start proxy in transmedia-pipeline
cd ../aeonisk-transmedia-pipeline
python main.py proxy-start --batch-threshold 50 --batch-timeout 300

# Run bulk generation in aeonisk-yags
cd ../aeonisk-yags
python scripts/bulk_session_runner.py \
  --config scripts/session_configs/session_config_batch_proxy_test.json \
  --runs 100 \
  --workers 20 \
  --proxy http://localhost:8000 \
  --output-dir bulk_output/
```

### Hybrid Configuration (Mixed Providers)

```json
{
  "agents": {
    "dm": {
      "llm": {
        "provider": "batch_proxy",
        "model": "gpt-5-mini",
        "underlying_provider": "openai",
        "proxy_priority": "normal"
      }
    },
    "players": [
      {
        "name": "Player1",
        "llm": {
          "provider": "openai",
          "model": "gpt-5-mini"
        }
      },
      {
        "name": "Player2",
        "llm": {
          "provider": "batch_proxy",
          "model": "claude-sonnet-4-5",
          "underlying_provider": "anthropic",
          "proxy_priority": "low"
        }
      }
    ]
  }
}
```

## Performance Characteristics

### Cost Comparison (1000 Sessions, 5000 tokens/session)

| Mode | Provider | Time | Cost | Calculation |
|------|----------|------|------|-------------|
| **Direct (no proxy)** | OpenAI gpt-5-mini | 2-4 hours | $12.50 | 5M tokens × $2.50/M (blended) |
| **Batch (80% batched)** | OpenAI gpt-5-mini | ~24 hours | $7.50 | 4M × $1.25/M + 1M × $2.50/M |
| **Batch (100% batched)** | OpenAI gpt-5-mini | ~24 hours | $6.25 | 5M × $1.25/M |

**Savings:** 40-50% cost reduction
**Trade-off:** 6-12x longer execution time

### Throughput Estimates

**Single Session:**
- Direct API: 5-15 minutes per session (rate-limited)
- Batch proxy: 30-90 minutes per session (includes queue time)

**Bulk Run (100 sessions, 20 workers):**
- Direct API: 250-750 requests total, ~30-90 minutes (parallel rate-limited)
- Batch proxy: 250-750 requests batched in 2-3 batches, ~24 hours (queue + batch processing)

**Optimal Use Case:**
- Bulk runs with 100+ sessions
- Overnight or weekend generation
- Cost > speed priority

## Testing Strategy

### Unit Tests

**test_batch_proxy_provider.py (14 tests):**
- Provider initialization (OpenAI/Anthropic backends)
- Text generation with mocked client
- Structured output with JSON parsing
- Markdown code block stripping
- Error handling (invalid JSON, schema mismatch)
- Token logging integration
- Health check delegation
- Factory function

**test_bulk_runner.py (16 tests):**
- Proxy health check (healthy, unhealthy, timeout)
- Config loading and modification
- Proxy config injection (DM, players)
- Session stats extraction from JSONL
- Resume capability (completed run detection)
- Statistics calculation (success rate, throughput)
- Dataclass construction

### Integration Tests

**Manual Integration Test:**
```bash
# 1. Start proxy
cd ../aeonisk-transmedia-pipeline
python main.py proxy-start

# 2. Verify health
curl http://localhost:8000/health

# 3. Run single session
cd ../aeonisk-yags
source .venv/bin/activate
python scripts/run_multiagent_session.py \
  scripts/session_configs/session_config_batch_proxy_test.json

# 4. Run bulk (3 sessions, 2 workers)
python scripts/bulk_session_runner.py \
  --config scripts/session_configs/session_config_batch_proxy_test.json \
  --runs 3 \
  --workers 2 \
  --proxy http://localhost:8000 \
  --output-dir /tmp/bulk_test

# 5. Verify results
ls -la /tmp/bulk_test/
python scripts/analyze_session.py /tmp/bulk_test/session_run_*.jsonl
cat /tmp/bulk_test/bulk_run_summary.json | jq
```

## Error Handling

### Proxy Unavailable

**Scenario:** Proxy server not running or unreachable

**Behavior:**
1. UnifiedAIClient attempts 3 retries with exponential backoff (5s, 10s, 20s)
2. After 3 failures, falls back to direct API
3. Session completes successfully via direct API
4. Logs warning: "Cannot connect to proxy, falling back to direct API"

**Cost impact:** Session pays full API cost (no savings), but doesn't fail

### Partial Batch Failure

**Scenario:** Some requests in batch succeed, others fail

**Behavior:**
1. Proxy downloads batch results
2. Individual request errors logged per request
3. Failed requests return error in `result.error` field
4. Successful requests return content normally

**Session impact:** Individual agent LLM calls may fail, triggering retry logic in ClaudeProvider/OpenAIProvider

### Session Timeout

**Scenario:** Individual session exceeds 1 hour timeout

**Behavior:**
1. `subprocess.run()` raises `TimeoutExpired`
2. Bulk runner catches exception, marks run as failed
3. Other concurrent runs continue unaffected
4. Summary report includes failure with "timeout" error

**Resume:** Timed-out run will be retried on `--resume`

### Proxy HTTP Errors

**Scenario:** Proxy returns 4xx/5xx HTTP errors

**Behavior:**
1. UnifiedAIClient immediately falls back to direct API (no retries)
2. Logs error: "Proxy HTTP error: ..., falling back to direct API"
3. Session completes via direct API

**Reason:** HTTP errors indicate proxy misconfiguration or overload, retrying wastes time

## Future Enhancements

### 1. Async Client Support (Not Implemented)

**Goal:** Reduce latency for bulk operations by using async HTTP

**Implementation:**
```python
async def chat_completion_async(self, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{self.proxy_url}/submit", json=request) as resp:
            return await resp.json()
```

**Benefits:**
- Non-blocking I/O for proxy requests
- Higher concurrency (1000+ concurrent requests)
- Reduced memory footprint vs subprocesses

**Blockers:**
- Requires refactoring session code to async
- Estimated effort: 20-40 hours
- Risk of breaking existing functionality

### 2. Native Structured Output Support

**Goal:** Use provider's native structured output APIs instead of prompt engineering

**Requirements:**
- Test if OpenAI Batch API supports `response_format` parameter
- Confirm Anthropic Message Batches don't support structured output
- Implement provider-specific structured output paths

**Benefits:**
- More reliable JSON parsing (guaranteed valid)
- Reduced prompt tokens (no schema in prompt)
- Better validation errors from provider

### 3. Webhook Callbacks (Instead of Polling)

**Goal:** Eliminate polling overhead by using webhooks for batch completion

**Implementation:**
- Proxy registers webhook URL with provider
- Provider POSTs to webhook when batch completes
- Proxy immediately processes results

**Benefits:**
- Faster result delivery (no 60s poll interval)
- Reduced API requests (no status polling)
- Lower latency for high-priority requests

**Blockers:**
- Requires publicly accessible webhook endpoint
- Complex for local development (ngrok/tunneling)
- Provider webhook support varies

### 4. Cross-Session Request Batching

**Goal:** Batch requests across multiple concurrent sessions for larger batches

**Implementation:**
- Shared request queue across all session subprocesses
- Coordinator process collects requests, submits batches
- Uses IPC (Redis/ZMQ) for cross-process communication

**Benefits:**
- Larger batches (100+ requests) → faster queue flush
- Better cost efficiency (more requests per batch)
- Reduced batch processing time

**Blockers:**
- Complex IPC architecture
- Requires stateful coordinator process
- Difficult to debug cross-process issues

## Limitations

### Current Limitations

1. **Synchronous Proxy Requests:** UnifiedAIClient uses `requests` (blocking I/O)
2. **Estimated Token Counts:** No actual token counts from proxy in sync mode
3. **No Native Structured Output:** Uses prompt engineering, not provider APIs
4. **Subprocess Overhead:** High memory usage for large bulk runs (20+ workers)
5. **Single Proxy Instance:** No load balancing or failover

### Known Issues

1. **No Native Structured Output (CRITICAL):** The batch proxy uses prompt engineering to request JSON, NOT OpenAI's native `response_format: {type: "json_schema"}` feature. This means:
   - LLM may generate truncated JSON (if max_tokens reached)
   - LLM may generate invalid JSON (unescaped characters, malformed structure)
   - JSON repair logic added (Dec 2025) but cannot fix all cases
   - For guaranteed valid JSON, use direct OpenAI provider (not batch proxy)

2. **Empty Proxy Responses:** Proxy may return empty content when batch "completes" but output file is missing. Added fallback to direct API for this case (Dec 2025).

3. **JSON Parsing Fragility:** If LLM doesn't return valid JSON, request fails (no retry)
4. **Long Polling:** Requests block until batch completes (up to 24 hours)
5. **No Progress Tracking:** Can't query proxy for request status during execution
6. **Hard-Coded Timeouts:** 1 hour per session, not configurable per-run

## Files

### New Files (Created)
- `scripts/aeonisk/multiagent/unified_llm_client.py` - Proxy client (~400 lines)
- `scripts/aeonisk/multiagent/llm_batch_provider.py` - Provider wrapper (~250 lines)
- `scripts/bulk_session_runner.py` - Orchestrator (~600 lines)
- `scripts/session_configs/session_config_batch_proxy_test.json` - Test config
- `tests/unit/test_batch_proxy_provider.py` - Unit tests (~200 lines)
- `tests/unit/test_bulk_runner.py` - Unit tests (~300 lines)
- `.claude/BATCH_GENERATION.md` - This document

### Modified Files
- `scripts/aeonisk/multiagent/llm_provider.py` - Added batch_proxy to registry (~30 lines)
- `CLAUDE.md` - Added batch provider documentation (~100 lines)

**Total:** ~1,880 lines added

## References

- **Anthropic Message Batches API:** https://docs.anthropic.com/en/docs/build-with-claude/message-batches
- **OpenAI Batch API:** https://platform.openai.com/docs/guides/batch
- **aeonisk-transmedia-pipeline:** `../aeonisk-transmedia-pipeline/src/services/llm_proxy/`
- **LLM Provider Architecture:** `scripts/aeonisk/multiagent/llm_provider.py:236-298`

## Changelog

**2025-12-06 - Bulk Run Failure Investigation & Fixes**
- ✅ Fixed COMPLETED_REASONS: Added `'completed'` (sessions were falsely marked as failed)
- ✅ Fixed Position enum validation: Graceful handling of invalid values like `'cover'`
- ✅ Fixed proxy retry loop: Detect "Batch ended with status: completed" bug, fallback to direct API
- ✅ Fixed dm_resolution_movement.yaml prompt: Corrected schema (character_name/new_position vs target/from_zone)
- ✅ Relaxed string limits: goal (200→500), roll_formula (200→300), rationale (500→800)
- ✅ Added JSON repair logic: Handle truncated JSON and invalid control characters
- ✅ Updated proxy error message in transmedia-pipeline for missing output file
- ✅ Updated unit tests: Added termination_reason, fixed mock order, changed round_end→round_start
- ✅ Documented structured output limitation (prompt engineering, not native response_format)

**2025-11-26 - Initial Implementation**
- ✅ Copy UnifiedAIClient from transmedia-pipeline
- ✅ Create BatchProxyProvider wrapper
- ✅ Register in provider registry
- ✅ Implement structured output via JSON schema
- ✅ Create bulk_session_runner.py orchestrator
- ✅ Add resume capability
- ✅ Add proxy health checks
- ✅ Write unit tests (30 tests total)
- ✅ Update documentation
