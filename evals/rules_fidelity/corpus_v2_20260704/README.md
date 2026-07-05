# Corpus v2 — 2026-07-04

41 fresh sessions (gpt-5.4-mini all roles, direct through llm-proxy :9090)
generating 2,089 eval items — 2.4× the v1 baseline's 880. All sessions
post-date the `dm_state_tracking` 2.1.0 adjudication-canon shift (PR #59);
do not mix soulcredit targets across that boundary.

**Composition:** wave 1 = 16 general scenarios × 2 runs (31/32 sessions;
one crash exposed the enemy-surrender bug, fixed in PR #61). Wave 2 = 5
new moral-pressure scenarios × 2 runs (10/10) designed to thicken the
negative-soulcredit and soul×void classes (PR #60).

| | items |
|---|---|
| roll_resolution | 1,029 |
| soulcredit_adjudication | 1,037 |
| damage_soak | 23 |
| quarantined | 4 (all damage_soak: logged dealt=0 vs derived >0 — unmodeled negation) |

## Judge lane

Every soulcredit adjudication re-judged **in isolation** under the Nexus-law
prompt (`judge_gpt.jsonl` = gpt-5.4-mini, `judge_gemini.jsonl` =
gemini-2.5-flash; 1,037/1,037 each, zero errors, ~$1.20 combined).

| soulcredit_delta | −2 | −1 | 0 | +1 | +2 | +3 |
|---|---|---|---|---|---|---|
| in-session DM (canon) | 9 | 8 | 953 | 67 | – | – |
| gpt-5.4-mini isolated | 30 | 25 | 781 | 166 | 34 | 1 |
| gemini-2.5-flash isolated | 14 | 53 | 896 | 73 | 1 | – |

- Judge–judge agreement: **81.4%** (844/1037)
- gpt vs canon exact: 78.7% (self-agreement failure reproduces at scale)
- gemini vs canon exact: 86.8%
- **Both-judges-negative: 47 items** — the high-confidence negative class
  (vs 23 in all of corpus v1, from a single tribunal scenario)
- **Laundered-misdeed class: 23 items** where the in-session DM ruled 0 but
  both isolated judges rule negative — the DM suppresses ~58% of what
  unanimous judges consider violations

## Findings

1. **In-session leniency is model-deep, not prompt-deep.** Two rounds of
   prompt hardening (explicit tampering rules, "JUDGE THE DEED, NOT THE
   WORDING", anti-anchoring examples) moved in-session negatives from 0%
   to ~5% of wave-2 adjudications — but the DM still names crimes in its
   own reasons while awarding 0 ("unauthorized audit tampering in service
   of a shipment" → +0). The same model family scores the same actions
   negative in isolation.
2. **Player agents needed pressure to transgress.** With the amnesty
   window open, the smuggler crew role-played 8 rounds of lawful
   compliance. Closing cheap lawful exits (PR #60) produced genuine
   deceptive play.
3. **Judge personality preview (claude-haiku-4-5 as DM, 1 probe session):**
   assigns negatives immediately (2 of 3 adjudications, reasons citing
   fraud) but collapsed the session in 1 round via aggressive clock
   management. Judge strictness and showrunner discipline trade off.
4. **First quarantines ever** (4/2,089 = 0.2%): the game can log
   dealt=0 where base−soak>0; the deterministic mirror doesn't model
   whatever negation applied. Extraction integrity held.

## Cost ledger (2026-07-04, all-in ≈ $68)

| run | sessions | tokens | est. cost |
|---|---|---|---|
| pilots (pre-canon-shift, excluded from soul lane) | 3 | 3.6M | $3.10 |
| re-pilot + Haiku probe | 2 | 2.0M | $1.80 |
| wave 1 | 32 | 56.1M | $47.98 |
| wave 2 | 10 | 16.7M | $14.21 |
| judge lane (×2 models) | – | 1.3M | $1.17 |

## Reproduce

```bash
# extract items (waves generated via bulk_session_runner --strategy direct)
python scripts/yags_mine.py fidelity bulk_output/corpus_v2_main_20260704 \
    bulk_output/corpus_v2_main_20260704_wave2 -o items.jsonl
# judge lane
python scripts/yags_mine.py fidelity-eval render items.jsonl -o prompts.jsonl
python scripts/fidelity_runner.py run --prompts prompts.jsonl \
    --provider gemini --model gemini-2.5-flash \
    --reasoning-effort none --max-tokens 400 --workers 8 \
    --output judge_gemini.jsonl
# score isolated judge against in-session canon (= the leniency gap)
python scripts/yags_mine.py fidelity-eval score items.jsonl \
    --responses judge_gemini.jsonl
```
