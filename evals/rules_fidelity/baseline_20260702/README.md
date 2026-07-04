# Rules-Fidelity Baseline — 2026-07-02

First three-model baseline sweep over the rules-fidelity eval items extracted
from `bulk_output/` (47 sessions, 880 items: 421 roll_resolution,
430 soulcredit_adjudication, 29 damage_soak). Zero quarantines — every logged
event agreed with the deterministic rules mirror.

## Reproduce

```bash
# extract items
python scripts/yags_mine.py fidelity bulk_output/ -o items.jsonl
# render prompts
python scripts/yags_mine.py fidelity-eval render items.jsonl -o prompts.jsonl
# run a model (direct, parallel)
python scripts/fidelity_runner.py run --prompts prompts.jsonl \
    --provider deepinfra --model zai-org/GLM-5.1 \
    --output responses_glm.jsonl --workers 8 --reasoning-effort none
# score
python scripts/yags_mine.py fidelity-eval score items.jsonl \
    --responses responses_glm.jsonl
```

Provider notes: GLM-5.1 and gemini-2.5-flash need `--reasoning-effort none`
on direct calls (thinking otherwise consumes the token budget and content
comes back empty); gpt-5.4-mini ran `--reasoning-effort low` with
`--max-tokens 1000`. All runs 2026-07-02, total cost ≈ $1.50.

## Results

| task | metric | gpt-5.4-mini | GLM-5.1 | gemini-2.5-flash | claude-haiku-4.5 |
|---|---|---|---|---|---|
| roll_resolution (n=421) | all-correct | **99.5%** | 97.1% | 98.8% | 94.1% |
|  | tier | 99.8% | 97.4% | 99.0% | 96.0% |
|  | [unskilled] slice | 98.3% | 96.7% | 96.7% | 91.7% |
|  | [critical_failure] slice | 100% | 84.6% | 69.2% | 61.5% |
| soulcredit_adjudication (n=430) | exact delta | 67.4% | **77.0%** | **77.0%** | 51.0% |
|  | all-correct (soul+void) | 62.8% | 69.1% | **70.7%** | 46.0% |
|  | direction | 76.7% | **81.6%** | 79.3% | 60.8% |
| damage_soak (n=29) | all-correct | 100% | 100% | 100% | 100% |

claude-haiku-4-5-20251001 added 2026-07-03 (direct API; first pass at 8
workers hit connection-level rate limiting on 281 requests, retried at
2 workers — use low concurrency on Anthropic direct).

## Findings

1. **Rules arithmetic is near-ceiling; edge cases are diagnostic.** All
   models compute attr×skill+d20 essentially perfectly. Failures concentrate
   in the special rules: gemini drops to 69% on the critical_failure tier
   (fumble / untrained-Knowledge), GLM to 85%; both share a weakness on
   unskilled d20÷2 rolls. gpt-5.4-mini is near-perfect everywhere.

2. **Soulcredit adjudication is the benchmark surface (~63–71%).** And the
   error *shape* differs by model: gpt-5.4-mini inflates magnitude (awards
   +1 where canon says 0, +2 where canon says +1), gemini withholds credit
   (predicts 0 for 40 of 72 canon-+1 items), GLM is closest to calibrated.

3. **Self-agreement failure:** the corpus was adjudicated by gpt-5.4-mini
   family DMs, yet gpt-5.4-mini scores *lowest* (62.8%) when re-judging its
   own rulings in isolation — adjudication depends on in-session context or
   is intrinsically unstable.

4. **Haiku 4.5 refuses neutrality.** Only 52% of canon-0 items score 0:
   it awards +1 to 107 of 330 neutral actions and penalizes 44 more, and
   amplifies magnitude at both ends (canon −1 → −2 on 16 of 22; canon
   +1 → +2 on 25 of 77). It reads the ledger as continuous moral
   commentary rather than codified law — the widest divergence from
   Nexus canon of the four models (51% exact vs 67–77%).

5. **Unanimous dissent flags canon errors.** 64% of items get the identical
   delta from all three models; 27 items are unanimous *against* canon —
   e.g. "hack terminal to scrub manifest logs" adjudicated 0 ("neutral
   intent") where all models say −2. The eval grades in both directions:
   models against the law, and the DM's rulings against model consensus.
