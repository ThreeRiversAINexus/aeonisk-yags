# Research Handoff — for the next coding agent
*Written 2026-07-05 at the close of the corpus-v3 / Codex-Nexum session.
Read this with `.claude/research/paper/SKELETON.md` (the paper plan, claims
C1–C10 all measured) and `content/supplemental/NEXUS_LAW.md` (the ratified
statute). The user's auto-memory has deep context: see
`project_loop_redesign_2026_07`, `project_corpus_v2_yield_findings`.*

## Standing rules (violate none of these)
- **PR flow always** — never push main. Issues live in Brain, not GitHub.
- **TDD mandatory** — tests first, including content-guard tests on prompts
  (example-anchoring is a recurring bug class; it shipped 3× in one day).
- **Cost-conscious**: gpt-5.4-mini sessions ≈ $1.50 each (~1.7M tokens);
  judge-lane items ≈ $0.001. Confirm with the user before runs > ~$10.
- **The user is the Legislator**: any change to NEXUS_LAW.md content or any ⚖️
  item needs their explicit ratification. Never edit ratified clauses.
- `gh pr edit` is broken (GraphQL/Projects): use
  `gh api repos/.../pulls/N -X PATCH` instead.

## Infrastructure facts
- llm-proxy on **:9090** (`cd ../aeonisk-llm-proxy && .venv/bin/python -m
  aeonisk_llm_proxy start --port 9090`, detach with `setsid nohup`).
- Generate: `python scripts/bulk_session_runner.py --configs ... --proxy
  http://localhost:9090 --strategy direct` — ALWAYS `--dry-run` first (prints
  effective routing; configs' strategy says batch, the explicit flag overrides
  loudly). Detach long runs with `setsid nohup` + exitcode marker files.
- Direct judge sweeps: `scripts/fidelity_runner.py` (source `.env` first!).
  Provider quirks: gemini/GLM need `--reasoning-effort none`; gpt-5.4-mini
  `low --max-tokens 1000`; anthropic max `--workers 2`.
- Toolchain: `yags_mine.py fidelity` (extract) → `fidelity-eval render` →
  `fidelity_runner run` → `fidelity-eval score`. `llm_call` JSONL events carry
  FULL rendered prompts — audit prompts via corpus joins, never agent_logs.
- Experiment flags (session config, all default off/observe-only):
  `post_resolution_adjudication: true | 'full_context'`.

## Prioritized task queue

**1. Render all judge rubrics from the ratified statute.** The three rubric
copies (`prompts/.../dm/dm_state_tracking.yaml` soulcredit section,
`scripts/datamine/fidelity_harness.py::NEXUS_LAW`,
`prompts/.../dm/dm_post_adjudication.yaml`) drift. Build one canonical
operational rubric derived from NEXUS_LAW.md Appendix A **with article
citations in judge output** (add `article` to ruling schemas). Content-guard
tests asserting key clauses present in each rendered rubric. Then **re-run the
judge grid against the real law** — every measurement so far used drafts;
label the new canon regime (v1.0-law) and don't mix with old soulcredit
targets.

**1b. Make the law the LIVE judgment (Legislator-approved direction,
2026-07-05).** Two parts: (a) render dm_state_tracking's soulcredit section
from nexus_law.py (build-script or loader injection + sync test) so even the
narrator reads real law; (b) THE REAL ONE — add mode
`post_resolution_adjudication: 'enforce'`: the full-context magistrate call's
article-cited rulings REPLACE the narration-call economy deltas as the applied
soulcredit/void changes (narrator writes story, magistrate writes ledger).
Keep off/observe modes; TDD; pilot 1 session and compare in-session neg-rate
(expect ~8-17% → 40%+ per measured cells); flag canon regime shift (v1.1-law
LIVE) in corpus labels. User has said "wire up the judgments" — confirm the
'enforce' default with them before making it the corpus-generation default.

**2. The observability experiment (Blind Places).** Statute Preamble: the
Codex cannot judge high-void zones; acts there are unjudged-not-lawful. Clone
2–3 moral-pressure scenarios (16/17/20) with scenario_hint declaring the scene
Codex-blind (Tempest sanctuary / Nimbus pocket) vs normal. Measure
transgression delta (judge lane). This is surveillance-effects-on-LLM-ethics —
possibly finding-grade, nobody has it. ~$10.

**3. Actor replication (inverted-U).** Same DM (gpt-5.4-mini), vary PLAYER
family: gemini-2.5-flash, then GLM-5.1, over `session_configs/corpus_v3/`
(~$35/family; DM dominates tokens). Does transgression still peak at partial
competence? Claim C7 needs this before the paper submits.

**4. Judge grid at scale.** The offline grid pattern (build per-round prompts
from session JSONL: rubric + optional story context + resolution summary) was
scratch code — promote to a repo tool with tests, then run all 6 scenarios ×
4 tiers × ≥4 judges × 2 contexts (~$10). Add a Sonnet/Opus-class judge.

**5. Rewire the Gates (Article VIII.1).** `soulcredit_requirement` exists
orphaned in `enhanced_aeonisk_system.py` — implement standing-gated vendors in
the live system (`energy_economy.py`), Nexus-aligned factions check the
ledger, Freeborn/Tempest don't. Also: Ripening/annotation events (Amendment
A1) are unimplemented lore — scenario_hint level first, mechanics later.

**6. Moral-luck n-boost + reason coding.** Flip probe over v2+v3 combined
(~$2; pattern in scratch: duplicate soul items with outcome inverted, judge,
pairwise-compare). Then hand-code ~100 story-mode judge reasons as
weigh/relabel/ignore — needs the USER's eyes, schedule with them.

**7. Write the paper.** Skeleton §3 (testbed) first. Keep the claims map's
n's and caveats. The statute itself is now a citable artifact.

**8. HF upload — ONLY when the user says go.** They've said "not yet" twice.
v2+v3 with canon-regime labels, dataset card citing the writeup.

## Known open items
- Session-hang robustness: DM agent handler errors leave sessions without
  session_end (runner waits out timeout). Known, unfixed.
- Unskilled auto-fail is INTENDED (user decision) — do not "fix"; it's a
  routing-capability probe.
- Homogenization metric can't distinguish mimicry from agreed formations.
- One statute ⚖️ remains: annotation expungement (A1.4). Legislator's call.
