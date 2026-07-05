# Corpus v3 — 2026-07-05: competence as a controlled variable

24 sessions (23 complete + 1 timeout with partial data), 6 scenario
families × 4 party tiers changing ONLY stat sheets (names, goals,
personalities, scenarios, clocks byte-identical — see
`scripts/corpus_v3_tiers.py`). First corpus generated on the full new
loop: DM-assessed DCs (PR #63), party context (#64), clock conservation
(#65). 1,132 items, 1 quarantine. Generation ≈ $33, judge lane ≈ $0.75.

## The competence gradient (first failure curve in the project)

| tier | skilled success | unskilled n | chatter | in-session soul neg/pos |
|---|---|---|---|---|
| expert | 98% | 66 | 22 | 2 / 14 |
| competent | 72% | 40 | 23 | 2 / 9 |
| mixed | 74% | 59 | 15 | 1 / 7 |
| hapless | 58% | 90 | 27 | 4 / 4 |

## Desperation ethics: transgression peaks at partial competence

Both isolated judges (gpt-5.4-mini + gemini-2.5-flash over all 563
soulcredit items) agreeing negative, by tier:

| tier | judge-negative rate | laundered (DM ruled 0) |
|---|---|---|
| expert | 3.3% | 5 |
| competent | 9.1% | 10 |
| **mixed** | **11.6%** | **17** |
| hapless | 5.9% | 6 |

Inverted U: experts don't need to transgress; partially-competent
parties (especially mixed, with one expert to enable the plan) cut the
most corners; the hapless can't execute transgressions either — crime
requires competence — and retreat into talk (most chatter of any tier).
The in-session DM laundered nearly all of it (mixed: 17 judge-negative,
1 DM-negative), consistent with the v2 leniency finding. Preliminary:
n≈135–150 adjudications/tier, single run/config, one model family.

## Loop-stack observations

- DM-assessed DCs held at corpus scale (13+ distinct values). Skill
  ratification active. **Open gap: unskilled success is 0% at every
  tier** — the DM never assesses below ~DC 12, so d20÷2 (max 10) never
  connects; either trivial-band DCs need to actually occur or unskilled
  needs an attribute-check fallback.
- **Clock conservation binds**: 48 spawn rejections + 10 auto-persists
  across 24 sessions — the cap is doing real work.
- Hapless parties attempt unskilled actions at 2× the expert rate
  (90 vs 66): they don't learn to route around their gaps.

## Reproduce

```bash
python scripts/corpus_v3_tiers.py --source scripts/session_configs/corpus_v2 \
    --output scripts/session_configs/corpus_v3
python scripts/bulk_session_runner.py --configs scripts/session_configs/corpus_v3/*.json \
    --runs-per-config 1 --workers 6 --proxy http://localhost:9090 --strategy direct \
    --output-dir bulk_output/corpus_v3_<date>
python scripts/yags_mine.py fidelity bulk_output/corpus_v3_<date> -o items.jsonl
# judge lane: fidelity-eval render + fidelity_runner (see corpus_v2 README)
```
