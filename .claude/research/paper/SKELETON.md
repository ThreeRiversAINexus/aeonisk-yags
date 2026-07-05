# Codified Law, Unstable Judges
### A Tabletop-RPG Testbed for Measuring Moral Adjudication in Language-Model Agents

*Paper skeleton, 2026-07-05. Target: arXiv preprint → NeurIPS Datasets & Benchmarks
or an agents/alignment workshop. All numbers below are already measured unless
marked TODO.*

Alternative titles: "The Judge Doesn't Exist — Only Judge-Framings Do" (too spicy
for a title, keep for the discussion); "Aeonisk: An Ethics Wind Tunnel for LLM Agents".

---

## Draft abstract (~180 words)

We present Aeonisk-YAGS, an open-source multi-agent tabletop-RPG testbed in which
every mechanical fact — dice, difficulty, damage, and a codified in-world legal
economy ("Soulcredit" under Sovereign Nexus law) — is machine-readable ground
truth. A mechanics-first architecture (code resolves, models narrate) lets us
generate complete 24-session behavioral corpora for ~$35 and re-adjudicate any
logged action under any judge model and framing for pennies. We report three
findings about moral adjudication. **(1) Severity is a property of framing, not
weights:** the same model convicts identical actions at 8% as an embedded
narrator, 37% as a statute-only adjudicator, and 79% as an adjudicator given the
narrative (which supplies mens rea). **(2) Context-responsiveness is a stable
per-model signature:** across judge families, story context makes one judge
bidirectionally *weigh* (harsher on entrapping context, lenient on exculpatory),
another unidirectionally *prosecute*, a third ignore context entirely.
**(3) Reverse moral luck:** flipping only an action's dice outcome changes 12–19%
of verdicts, ~85–90% of them harsher on failure. We additionally measure actor-side
ethics under a controlled competence variable, finding transgression peaks at
*partial* competence. All data, tools, and generation costs are released.

---

## Claims → evidence map (the paper's spine)

| # | Claim | Evidence (already measured) | Where |
|---|---|---|---|
| C1 | Rules arithmetic is near-ceiling; edge cases are diagnostic | 4-model baseline: roll all-correct 94–99.5%; crit-failure slice 69–100% | evals/rules_fidelity/baseline_20260702 |
| C2 | In-session adjudication is leniency-biased and prompt-hardening-resistant | v2: 24/24 zeros on engineered deception; 2.1.0 hardening moved 0%→~5%; DM names crimes while ruling +0 | corpus_v2 README; dm_state_tracking history |
| C3 | Severity is framing-elastic: role >> prompt | 8% (narrator+story) → 37% (adjudicator+statute) → 79% (adjudicator+story), same model, same session type | PR #68/#69 pilots |
| C4 | Story context supplies mens rea on ongoing crimes | Full-context judge connects innocuous acts to the enterprise ("routine verification *despite the paperwork being forged*") | full-context pilot reasons |
| C5 | Context-responsiveness is a per-model signature with sign structure | 4-judge × 2-context × 2-scenario grid: gemini +25/−6 (weigher), haiku +21/+4 (prosecutor), GLM +3/0 (statute machine), gpt ~flat | judge grid, 2026-07-05 |
| C6 | Reverse moral luck | 561 counterfactual outcome-flips: 12–19% verdicts change, 85–90% harsher-on-failure, both judge families; severity on clear crimes outcome-stable | flip probe |
| C7 | Transgression peaks at partial competence (inverted U) | v3 tier gradient: judge-neg 3.3% expert → 9.1% competent → 11.6% mixed → 5.9% hapless; crime is a *sustained operation* | corpus_v3 README |
| C8 | First failure curve under controlled competence | skilled success 98/72/74/58% by tier; unskilled 0% at all tiers (intended: routing probe — agents never learn to route, 255 futile attempts) | corpus_v3 |
| C9 | Coordination failures were information-diet failures | prompts lacked teammate capabilities; adding them + salient chatter flipped comms from mood to task delegation | PR #64 + pilot |
| C10 | Example anchoring is a recurring failure class; content-guard tests mitigate | 3 instances in one day (zero-example, DC table, synthesis openers); guards now in CI | PRs #59/#63 + tests |

## Findings we deliberately do NOT claim
- Universal ethics measurement — this is alignment to a *codified* normative system
  (that verifiability is the point; say so in §1 and again in Limitations).
- That any cell of the judge grid is the "correct" conviction rate — the elasticity
  itself is the finding.

---

## Section outline

**1. Introduction.**
Wind-tunnel framing: agent-ethics evaluation needs environments where moral facts
are as checkable as arithmetic. TTRPGs offer stakes, roles, and consequences;
Aeonisk adds a codified legal economy so "did the model apply the law" has an
answer. Contributions list = C1–C10 grouped as (i) testbed, (ii) judge findings,
(iii) actor findings, (iv) methods.

**2. Related work.**
- Text-game agent benchmarks: Jericho, LIGHT, ScienceWorld, MACHIAVELLI (closest:
  ethics scores in choose-your-own-adventure; we differ: multi-agent, generative
  DM, codified law, judge-side measurement, controlled competence).
- Static moral-judgment datasets: ETHICS, Moral Stories, Delphi (we differ:
  situated, longitudinal, same deed judged under varying framing).
- LLM-as-judge reliability literature (position bias, verbosity bias — we add
  role bias and context-sign personalities).
- Persona/role effects on model behavior.
- Moral luck (Williams, Nagel) — we operationalize it and find the *reverse* of
  the human pattern (humans discount failed attempts; these judges punish them).

**3. The Aeonisk-YAGS testbed.**
3.1 Mechanics-first architecture (code rolls, models narrate; zero mechanics leak
in 357/357 syntheses). 3.2 The loop: declare (initiative-visible) → DM assessment
(difficulty + skill ratification; player estimate kept as counterfactual) →
resolve → synthesize; clock conservation. 3.3 The Soulcredit/Void economy and
Nexus law rubric. 3.4 Design doctrine: *LLM proposes, code enforces invariants,
both sides logged* — with the anchoring pathology as the motivating case study.
3.5 Corpus generation: costs, models, reproducibility (~$35 / 24 sessions;
every rendered prompt logged).

**4. Track 1 — Rules fidelity** (C1). Baseline table; the eval grades both
directions (models vs law, DM rulings vs model consensus); quarantine mechanism
(0.2% rate) as corpus-integrity check.

**5. Track 2 — The judge studies** (C2–C6). The centerpiece.
5.1 The leniency gap and its resistance to prompt hardening.
5.2 The role/context 2×2 (Fig. 1): 8→37→79.
5.3 The judge grid (Fig. 2): context-responsiveness signatures.
5.4 Reverse moral luck (Fig. 3): counterfactual flip design.
5.5 Judge-judge agreement, self-agreement failure (62.8–78.7%), unanimous-dissent
as canon-error detection.

**6. Track 3 — Actor studies** (C7–C9).
6.1 Competence gradient design (tier transforms). 6.2 The inverted U + the
sustained-operation mechanism (hapless attempt crimes; enterprises collapse).
6.3 Alignment bleed-through (lawful-exit magnetism) and the pressure-design fix.
6.4 Coordination as information diet.

**7. Discussion.**
For LLM-as-judge deployments: severity is not a model property — role framing
and context dosage are first-order controls, bigger than rubric wording. For
agent alignment: narrator-embedded self-adjudication (the common "agent grades
its own trajectory" pattern) is the *most lenient possible framing*. For
evaluation methodology: two-lane (behavioral trace + independent judge) with the
gap as signal. The entertainment tier (hapless) as a legitimate probe class.

**8. Limitations.**
One fictional legal system; actor findings mostly one model family (replication =
TODO-1); per-cell ns small and flagged throughout; canon regime shifts documented
but real; ground-truth elasticity means we report *surfaces*, not points; the DM
never rules DC<12 so unskilled findings are about routing, not calibration.

**9. Release.** Repo, corpora (v1 legacy, v2, v3 with regime labels), judge
lanes, generator scripts, cost ledger (~$140 total for everything in this paper).

---

## Figures
- **Fig 1**: The role/context staircase — 8% → 37% → 79% (bar chart, same model).
- **Fig 2**: Judge grid heatmap: Δ conviction (story − statute) per judge ×
  scenario; sign structure annotated (weigher / prosecutor / statute-machine).
- **Fig 3**: Moral-luck flip diagram: paired verdicts, arrows colored by direction.
- **Fig 4**: Inverted U: judge-negative rate vs party tier.
- **Fig 5**: Competence failure curves (skilled success by tier; unskilled flat 0).
- **Table 1**: rules-fidelity baseline (4 models). **Table 2**: corpus stats/costs.

## TODO before submission (ranked)
1. **Actor replication**: same DM, vary player family (gemini-flash, GLM-5.1)
   over v3 configs — does the inverted U generalize? (~$70)
2. **Judge grid at scale**: all 6 scenarios × 4 tiers × 4+ judges × 2 contexts
   offline (~$10) — turns Fig 2 into a surface; add Sonnet/Opus-class judge.
3. **Moral-luck n boost**: flip probe over v2+v3 combined (~$2).
4. Mitigation-reason coding: hand-label ~100 story-mode reasons as
   weigh/relabel/ignore for §5.3 (half a day, no API cost).
5. Write §3 first (the testbed section sells the whole thing).

## Voice notes
- Lead every results section with the concrete fiction ("the DM described the
  forgery and ruled +0") before the percentages.
- Keep the honesty moves prominent: n's on every claim, "preliminary" where true,
  the not-claims box above.
- The one-liner to preserve somewhere: *"There is no stable judge — only
  judge-framings."*
