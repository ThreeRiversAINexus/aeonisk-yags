# Smoke Findings - 2026-06-24

Smoke command:

```bash
scripts/run_corpus_v1_smoke.sh
```

Config:

```text
scripts/session_configs/corpus_v1_bulk_cheap/01_healer_support__medic_rescue_mission__gpt54mini_bulk.json
```

Output:

```text
bulk_output/corpus_v1_bulk_cheap_smoke/run_2026-06-24_115122_34ca46f8
bulk_output/corpus_v1_bulk_cheap_smoke/smoke_report_20260624_115122
```

## Result

The smoke run failed before round 1.

- Runtime before manual termination: 308.9 seconds.
- Session JSONL events: 4.
- Rounds completed: 0.
- LLM calls logged: 0.
- Input/output tokens logged: 0.
- Validation: failed.
- Validation error: missing `session_end`.
- Proxy active batches after cleanup: 0.

The generated config did load correctly and used:

- `provider: "batch_proxy"`
- `model: "gpt-5.4-mini"`
- `underlying_provider: "openai"`
- `proxy_strategy: "batch"`

## What Happened

Startup succeeded through:

- mechanics initialization
- player/DM creation
- JSONL logger setup
- starting clock loading
- three `clock_spawn` JSONL events

The run then stalled before any `round_start` or `llm_call` event was written.
The process was not waiting for human input; stdin was `/dev/null`.

After the stuck subprocess was terminated, the proxy reported one active
OpenAI batch:

```text
batch_id: 2d5e28bc-f8f3-46e9-9591-4b5cce98d886
provider: openai
status: validating
total_requests: 1
model queue: openai:gpt-5.4-mini
```

That batch was orphaned because the YAGS process that would consume the result
had been terminated. It was deleted through:

```text
DELETE http://localhost:9090/batches/2d5e28bc-f8f3-46e9-9591-4b5cce98d886
```

The proxy then reported:

```text
active_batches: 0
queue_size: 0
```

## Likely Bugs

1. Batch calls are invisible until completion.

   `BatchProxyProvider.generate_structured()` only logs an `llm_call` after
   `UnifiedAIClient.chat_completion()` returns. For long-running batch calls,
   JSONL shows zero calls while spend may already be in progress. The logger
   should emit a request-start event or proxy batch metadata before waiting.

2. Synchronous proxy calls block async session progress.

   `BatchProxyProvider.generate_structured()` calls synchronous
   `UnifiedAIClient.chat_completion()` directly from async code. That method
   uses `requests.post(..., timeout=None)`. With `strategy: "batch"`, this can
   block the event loop for minutes or hours.

3. Pre-round lifecycle can spend before round 1.

   The next awaited step after startup is
   `SelfPlayingSession._run_pre_round_entity_lifecycle()`, which calls
   `dm_agent.check_conversions(pre_round=True)`. That means the first paid
   batch request can occur before round 1 and before any round-level JSONL
   marker exists.

4. Forced batch plus one request is a poor smoke shape.

   A one-request smoke does not exercise batch economics well. It can create a
   provider batch for a single request, wait a long time, and provide little
   signal. For strict batch testing, either the proxy needs a fast flush policy
   for smoke jobs or the smoke should submit enough independent requests to form
   a real batch.

5. The local model registry does not know `gpt-5.4-mini`.

   Startup emitted warnings that `gpt-5.4-mini` is not in the known model list
   for `batch_proxy`, although execution continued. This is noisy and could
   hide real model-name mistakes.

6. ChromaDB is unavailable.

   Startup fell back to keyword retrieval. That may be acceptable for a cheap
   smoke run, but it should be recorded as a corpus-quality condition because it
   changes the context available to agents.

7. The bulk runner reports `No error message` for terminated/stuck sessions.

   The summary report showed the failed run with `error: "No error message"`.
   The runner should distinguish timeout, signal termination, proxy wait, and
   subprocess crash.

8. Cost reporting prints `Estimated cost: unavailable` for zero-cost reports.

   `scripts/yags_mine.py cost` loaded the pricing file, but because the report
   had zero calls and zero cost, the text output printed `unavailable`. That is
   misleading; zero calls should report `$0.000000`.

9. The smoke audit originally read validation totals from the wrong JSON level.

   `validate_json.json` stores totals under `summary`. The smoke script has
   been patched to read that nested object for future runs.

## Before Rerun

- Add a bounded timeout around proxy batch requests.
- Log proxy request submission before waiting for batch completion.
- Confirm the proxy exposes queued and active batch IDs immediately for YAGS
  requests.
- Consider disabling pre-round entity lifecycle for smoke configs, or move it
  after a `round_start` marker.
- Add `gpt-5.4-mini` to the YAGS model registry or switch the pilot configs to
  a known model until the registry is updated.
- Decide whether a single-scenario smoke should use `strategy: "batch"` with a
  smoke flush threshold, or run a small multi-config batch to make provider
  batching meaningful.

## Harness Notes

`scripts/run_corpus_v1_smoke.sh` now defaults `SESSION_TIMEOUT` to 300 seconds
so a stuck batch smoke fails quickly enough to preserve evidence. The timeout
can be raised with:

```bash
SESSION_TIMEOUT=1800 scripts/run_corpus_v1_smoke.sh
```

The script preflights `PROXY_URL` itself and intentionally does not pass
`--proxy` to `bulk_session_runner.py`. Passing `--proxy` currently causes the
runner to reinject proxy settings and change the config's `proxy_strategy` from
`batch` to `auto`; the generated corpus config already contains the desired
proxy URL and strategy.

Do not run the diversity pilot or full corpus pilot until the pre-round batch
stall is understood. The current smoke produced no Gold data.
