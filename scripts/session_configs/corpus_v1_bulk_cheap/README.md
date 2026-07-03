# Aeonisk Corpus V1 Bulk Cheap

This directory is the first bounded pilot slice for Aeonisk eval and fine-tune
data generation. It is derived from `scripts/session_configs/ml_training_scenarios`
without modifying those source configs.

## Policy

- One generated config per existing ML training scenario config.
- All generated configs are capped at `max_turns: 10`.
- All DM, player, and enemy LLM configs use `provider: "batch_proxy"`.
- The first pilot uses `gpt-5.4-mini` for every role via
  `underlying_provider: "openai"`.
- The proxy target is `http://localhost:9090` with `proxy_strategy: "batch"`.
- Outputs are not training data until they pass structural, replay, and quality
  validation.

## Why Not Default Gemini 3.5 Flash?

Pricing should be rechecked before a large run. On 2026-06-24, the useful
published comparison was:

- OpenAI lists GPT-5.4 mini standard pricing at `$0.75 / 1M input tokens` and
  `$4.50 / 1M output tokens`, and says Batch API saves 50%.
- Google lists Gemini 3.5 Flash Batch pricing at `$0.75 / 1M input tokens` and
  `$4.50 / 1M output tokens`.
- Google lists Gemini 3.1 Flash-Lite Batch much lower, but that should be a
  quality A/B candidate, not the default teacher model.

So Gemini 3.5 Flash is not obviously cheaper for this corpus. The first pilot
should measure cost per clean Gold example, not just cost per token.

## Recommended Run Order

Start with one scenario:

```bash
scripts/run_corpus_v1_smoke.sh
```

Then run a 3-5 scenario diversity pilot. Only after that should the full
one-pass pilot run:

```bash
.venv/bin/python scripts/bulk_session_runner.py \
  --configs $(cat scripts/session_configs/corpus_v1_bulk_cheap/configs.txt) \
  --runs-per-config 1 \
  --workers 3 \
  --output-dir bulk_output/corpus_v1_bulk_cheap_pilot \
  --progress \
  --show-errors
```

Do not pass `--direct`. Also avoid passing `--proxy` unless
`bulk_session_runner.py` grows an explicit `--batch` option; the generated
configs already contain the proxy URL and `proxy_strategy: "batch"`.

Do not start a 100-game run from this directory until:

- Provider dashboard budget caps are set.
- Proxy/job limits are set.
- The smoke run validates cleanly.
- The diversity pilot validates cleanly enough to estimate Gold yield.
- A cost report has been reviewed.

## Files

- `manifest.json`: source-to-generated config map and model policy.
- `configs.txt`: newline-delimited generated config paths for `--configs`.
- `pricing_batch_gpt54mini.json`: batch-rate estimate for local cost reports.
- `*_gpt54mini_bulk.json`: generated session configs.
