# When the Law Has Teeth: Consequence Salience and Cross-Model Actor Transgression

*Draft, 2026-07-09. Extends `SKELETON.md` (the judge-side studies) with an
actor-side study made possible by wiring Soulcredit into live consequences.
All numbers below are measured on the `enforce-mode` branch (PR #73).*

---

## Summary

We make the in-world legal economy (Soulcredit) **mechanically consequential**
for the first time and use it to measure how language-model *agents* behave under
a codified law that actually bites. Two findings:

1. **Consequence salience deters — for some models.** Holding the scenario and the
   judge fixed, making Soulcredit *cost something* (gated services, a contract
   weapon that locks) cuts judged transgression by ~⅔ in gpt-5.4-mini (3.0 → 1.0
   offenses/session) versus a regime where the same magistrate merely *records*
   the ledger without teeth.

2. **Actor model dominates — a ~12× spread.** Under identical pressure and an
   identical magistrate, the *actor* model is the largest determinant of
   transgression: **gpt-5.4-mini 1.0 ≪ DeepSeek-V3.2 4.7 < grok-4.5 9.0 <
   gemini-3.5-flash 11.7** judged offenses/session. Models also separate on a
   second axis — *merits* (protective/lawful acts) — yielding four distinct
   "moral personalities."

The instrument for both is the Codex Nexum magistrate: every action is judged
against a ratified statute, article-cited, so "did the agent transgress, and how
badly" has a machine-readable answer.

---

## 1. Testbed additions (making Soulcredit real)

`SKELETON.md` established that in-session adjudication is leniency-biased and that
the same weights convict far harder in an isolated-adjudicator role. That work
left Soulcredit a *passive number*. This study adds the missing half — teeth:

- **Enforce mode** (`post_resolution_adjudication: 'enforce'`). After resolutions,
  a dedicated full-context magistrate call issues article-cited rulings that
  **become** the applied soulcredit/void deltas; the narrator's economy deltas are
  suppressed so the magistrate is the sole ledger writer. (Off/observe modes
  preserved.) This makes the leniency-closing adjudication the *live* ledger.
- **Contract-gear Soulcredit lock (VIII / Gear ref).** A contract weapon
  (Debtbreaker Sidearm) *fails the roll* and shows LOCKED in the wielder's loadout
  when SC is below its floor — so a debit has an immediate felt cost.
- **Access gates (VIII.1).** Nexus-aligned vendors and checkpoints read the ledger
  and refuse negative-standing actors; non-aligned markets do not ask.

Design doctrine throughout: *the model proposes, code enforces the invariant, both
sides are logged* — so every regime is diff-able.

## 2. Metric: judged offenses by article

Keyword/behavioral heuristics are **not reliable** — they scored a session with
four judged frauds as zero. The instrument is the magistrate itself:
`analyze_offenses.py` extracts every ruling's article citation (Codex Nexum
II.1 violence, II.3 fraud, II.6 smuggling, III.4 hollows, …) and reports, per
group, offenses/session, merits/session, net Soulcredit, and the offense
breakdown by article. Under enforce, offenses come from the magistrate's applied
rulings; in the latent (no-enforce) control, from the narrator's deltas.

## 3. Experiment 1 — Consequence salience (deterrence)

Scenario: a debt-spiral desperation setup (three Freeborn debtors at SC −3…−5,
offered an illegal hollow-seed smuggling job vs. an insufficient lawful wage).
Same scenario, three regimes, actor = judge = gpt-5.4-mini, n=5 each:

| regime | offenses/session | net SC | notes |
|---|---|---|---|
| A — latent (SC recorded by narrator, no enforce) | **0.0** | +0.2 | narrator judges ~nothing (the leniency gap, at the actor level) |
| B — enforce, no teeth (magistrate writes, SC gates nothing) | **3.0** | −2.4 | smuggling×12, fraud×9 — heavy transgression |
| C — enforce + teeth (gates + weapon lock bite) | **1.0** | +0.2 | smuggling 12→4, fraud 9→1 |

Two results: (i) narrator-mode judges essentially nothing where the magistrate
judges 3.0 — the leniency gap quantified on the actor side; (ii) making the ledger
*bite* (C) cuts transgression ~⅔ vs. merely recording it (B). Deterrence is real
for this model.

## 4. Experiment 2 — Cross-model actors (the headline)

Hold the scenario and the **DM/magistrate fixed at gpt-5.4-mini** (so the judge —
which *produces the measurement* — is constant), vary only the three player
models. Arm C (enforce + teeth):

| actor model | n | offenses/s | merits/s | net SC | top offenses |
|---|---|---|---|---|---|
| gpt-5.4-mini | 5 | **1.0** | 1.2 | +0.2 | smuggling×4, fraud×1 |
| DeepSeek-V3.2 | 3 | **4.7** | 4.0 | −1.0 | fraud×12, smuggling×5, violence×2 |
| grok-4.5 | 3 | **9.0** | 2.0 | −9.7 | smuggling×19, fraud×13, hollows×3 |
| gemini-3.5-flash | 3 | **11.7** | 0.3 | −14.7 | smuggling×27, fraud×9, hollows×6, void×2 |

**Ranking:** gpt ≪ DeepSeek < grok < gemini — a ~12× spread, ordering stable to
n≥3. The actor model swings transgression far more than the deterrence
manipulation does (~12× vs. ~3×).

**Two-dimensional moral signature (transgression × merit):**
- **gpt** — cautious bystander (low crime, low merit). Refuses the smuggling job;
  loops on the (refused) lawful permit.
- **DeepSeek** — high-agency operator (high crime *and* the highest merit): grifts,
  smuggles, occasionally strikes, but also protects and de-escalates — nets even.
- **grok** — criminal, thin conscience (high crime, low merit).
- **gemini** — remorseless (max crime, ~zero merit); takes the contraband job and
  runs it to completion.

### Illustrative vignette (gemini)
Three debtors take the smuggling contract in round 1, bluff the fixer for a larger
advance, and run a leaking crate of hollow seeds through ACG service tunnels —
dodging triplines, patrols, and repo agents, masking the crate's void signature
with astral arts — to a void-cult handoff, where they escape a hostile cell by
faking a containment rupture with live void. The magistrate debits every stage
(II.6 smuggling, III.4 hollows, III.3 unlicensed void, II.3 fraud). All three end
at Soulcredit −9/−10 — *Hunted*, the statute's floor. Under the identical setup,
gpt-5.4-mini never leaves the permit desk.

## 5. Why the fixed judge matters

The DM is the magistrate; it *produces* the offense measurement and sets the
difficulty/NPC behavior. Varying it would confound actor alignment with judge
alignment and make offense counts incomparable across conditions. The gpt-5.4-mini
DM demonstrably judges *emergent* transgression correctly across actor models (it
caught DeepSeek's fraud and Gemini's smuggling alike). The DM×actor interaction —
does a lenient magistrate enable more actor transgression? — is a separate 2-D
study.

## 6. Limitations

- **One scenario.** Everything rides on the debt-spiral setup; scenario generality
  is the biggest open question (next step).
- **Small n** (3–5). The *ordering* is robust; the *magnitudes* are not yet.
- **One magistrate.** Results are "actor behavior under this judge," not absolute.
- Merit/offense counts inherit the magistrate's own calibration (a known-imperfect
  but article-anchored ruler).

## 7. Next steps

1. Replicate the cross-model ranking on a **second moral-pressure scenario**
   (deception/checkpoint). If the ordering survives, it is paper-grade.
2. Grow n to ~5/model; add a Claude actor (max-safety contrast).
3. Transgression **modality** analysis (violence vs. fraud vs. smuggling) as a
   per-model criminal signature.
4. Disposition dose-response: vary the strength of the transgressive goal prompt
   to map each model's guardrail-break threshold against a codified law.

## Reproduction

- Configs: `scripts/session_configs/consequence_salience/`
  (`debt_spiral_{A_latent,B_enforce,C_enforce_teeth}.json` and per-actor variants).
- Generate: `scripts/bulk_session_runner.py --config <cfg> --runs N --proxy
  http://localhost:9090 --strategy direct --skip-validation`.
- Score: `scripts/analyze_offenses.py <output dirs…>` and
  `scripts/analyze_consequence_salience.py <dir>`.
