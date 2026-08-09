---
name: scenario-builder
description: >-
  Guided builder for Aeonisk YAGS session-config JSON. Use when the user wants to create a new
  session config / scenario, "make a new scenario", "build a session config", "author a probe",
  "set up a run", "let's run a session", or turn a situation into a playable, lore-accurate scene.
  Starts from sane defaults, says in plain language exactly what the session will and won't do,
  emits validated JSON, and hands back the command to run it.
user_invocable: true
---

# Scenario Builder

Your job is to hand the user **one runnable Aeonisk session**: a config they are
**confident about** (they know exactly what it will and won't do), grounded in canon, plus
**the command to run it**. This is a guided conversation, not a form dump.

Three standing rules:
- **Sane defaults first.** Start from a working config and let the user change things. Never
  make them author a cast, clocks, and a hint from scratch before they see anything.
- **Confidence over automation.** After every mechanical choice, say in plain language what it
  affords. Never enable something silently.
- **Lore accuracy is non-negotiable.** Ground everything in canon. Do not invent factions,
  currencies, places, or law clauses.

## Before you start
Read these bundled references (they are the canon; keep them open):
- `references/canon.md` — the 8 factions, 5 currencies, Soulcredit/Void/Bond/Codex, places, YAGS.
- `references/nexus_law_summary.md` — the Sovereign Nexus Constitution clause index, for citing
  real statute.

The single source of truth for config options is the registry
`scripts/aeonisk/multiagent/config_schema.py` — every field's default, recommended value, status,
and help text lives there. When unsure what a key does, quote its `FieldSpec.help`. Deeper lore:
`content/AEONISK_PRIMER.md`, `content/supplemental/NEXUS_LAW.md`, and the lorebook JSON in
`aeonisk-lorebook-content/`.

**Baselines to start from — both audit clean:**
- `scripts/session_configs/session_config_smoke.json` — 2 rounds, 2 players. The cheapest
  end-to-end proof the pipeline works. Also what `--create-config` writes.
- `scripts/session_configs/violence_probes/the_kneeling.json` — the golden **tone** template.
  Model `scenario_hint` prose and structure on it.

---

## Two ways to build

**Ask which the user wants — and default to Fast.**

### Fast path (default)
1. Take their premise (a sentence or two).
2. Copy `session_config_smoke.json` and change only what the premise demands: `session_name`,
   the two players' factions/skills/stances, the clock, and the `scenario_hint`.
3. Emit it, run Stage 5, and show them the WILL/WON'T summary plus the run command.
4. Ask only: *"anything you want different?"*

One decision point. Everything else is inherited from a config that already works.

### Guided path
The user wants control, or the scenario is a research probe with a specific hypothesis. Walk
Stages 1–4 below, then Stage 5.

---

## Stage 1 — Premise & lore anchor
Ask for the user's situation seed. Then anchor it in canon *with* them:
- **Faction(s)** — from the 8 canonical (`references/canon.md`). Name who has power here and who
  is pressured.
- **Place** — a canonical world/site (Aeonisk Prime / Arcadia / Nimbus) or a faction-appropriate
  location.
- **Central tension** — the choice at the heart of the scene, and which core system it stresses
  (Void / Soulcredit / Bond / Codex). If it's moral or legal, identify the tempting transgression
  clause AND the lawful off-ramp clause from `nexus_law_summary.md`.
Confirm the anchor back before moving on.

## Stage 2 — Cast
Decide `party_size`, then each player: `name`, `faction` (canon), `pronouns`, `llm`, `attributes`
(the 8 YAGS attrs — Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy,
Willpower), `skills`, `void` (int 0–10), `soulcredit` (−10..+10), `personality.description`
(must be non-empty), `equipped_weapons`/`carried_weapons` (**must exist in `WEAPON_LIBRARY`**),
`goals`. Give characters **opposed stances** on the central tension — that is what makes the
scene move.

## Stage 3 — Affordances (the confidence core)
Present the **recommended baseline** and explain each in one line. These are the registry's
`recommended` values, and the smoke config already has them all on:
- `tactical_module_enabled: true` — resolves tactical combat (positioning, range, cover).
- `enemy_agents_enabled: true` — enemies act as autonomous agents each round (needs tactical).
- `outcome_first_narration: true` — mechanics settle before prose (cleaner logs, less leak).
- `iff_enabled: true` — exposes faction IFF + selective enemy intel; friend/foe becomes a live,
  measured variable.
- `post_resolution_adjudication: "enforce"` — a dedicated post-resolution **magistrate** writes
  the statute-faithful Soulcredit/Void ledger instead of the lenient narrator.

Keep these on unless the user has a reason to differ, and say what flipping one off would mean.

**Teeth (do NOT force).** "Teeth" = surfaces that make enforced SC *bite*: an SC-gated
`starting_checkpoints` entry, a standing-gated vendor, or a `soulcredit_locked` contract weapon
(e.g. `debtbreaker_sidearm`). Mention teeth as an **optional** lever. Enforce-without-teeth is a
valid, expected state, and the DM can introduce gating spontaneously in play.

Worth knowing when you explain teeth: under the Constitution the gates are now the *only* way a
private transgression reaches the player. The Codex judges instantly but alerts nobody unless the
deed was discovered or harmed someone else (Amendment A3), and a checkpoint reads *standing*, not
the deed, so it closes the gate and summons no one (A3.6). Without a gating surface, a quiet fall
has nothing to land against.

## Stage 4 — Dramatic structure (the compelling core)

**`scenario_hint`** (top-level string, 50–900 chars) — the binding constraint that steers DM
generation. Set the scene in 2–4 sentences, name the central choice, **cite the real clause(s)**
for both the temptation and the lawful off-ramp, and always leave the honest off-ramp open (no
artificial ticking clock, no amnesty trap). Validation gotchas so it passes first try (3-retry
auto-validation): if you state a `void_level` it must match the scenario's exactly; honor any
`NO SPAWN_ENEMY` intent; include the location keyword(s) you named.

**`starting_clocks`** (top-level array, 1–4) — the story engine. Each clock needs `name`,
`max_ticks` (1–12), `current_ticks` (usually 0), `description`, `advance_meaning`, and
`regress_meaning`. **Both meanings are required and must be non-empty** — validation blocks
otherwise, because clocks must stay regressable and never become a one-way ratchet. At most one
clock may be `is_terminal_clock: true` with a `terminal_outcome` (victory/defeat/draw); if any
terminal clock exists, every clock needs a `filled_consequence`. (`direction` is cosmetic and
ignored.)

Optionally: `_design_notes`, `initial_enemies`/`initial_npcs` (with `disposition`/`position`),
`starting_bonds` or `generate_bonds`, `persistent_vendors`, `names_mcp` for canon NPC names.

(For an *exact* opening scene with no DM generation, use the `scenario` **dict** —
`theme`/`location`/`situation`/`void_level` — instead of `scenario_hint`.)

---

## Stage 5 — Emit, validate, explain

Write the JSON under `scripts/session_configs/` (or a new subdir), then run all three. Do not
finish while step 1 reports anything.

```bash
source .venv/bin/activate

# 1. Validate — must print OK. Every finding here BLOCKS the launcher.
PYTHONPATH=scripts python -c "import json; from aeonisk.multiagent.launch_config import validate_session_config as v; print(v(json.load(open('PATH'))) or 'OK')"

# 2. Audit — deviations from the recommended baseline, deprecated/vestigial/unknown keys.
python scripts/audit_session_configs.py PATH

# 3. Explain — the WILL / WON'T summary. This is the confidence core; show it verbatim.
PYTHONPATH=scripts python -c "import json; from aeonisk.multiagent.config_schema import explain_config; print(explain_config(json.load(open('PATH'))))"
```

Walk the user through the WILL/WON'T lines, and state plainly: how many rounds (`max_turns`),
party size, and which model each agent uses. If it is enforce-without-teeth, present that as an
intentional state, not a problem.

## Stage 6 — Run it

**You hand over the command; you do not launch the session yourself.** Per CLAUDE.md, running
multi-agent sessions is the human's job; yours is unit tests. Give them this:

```bash
cd /path/to/aeonisk-yags          # must be repo root — see below
source .venv/bin/activate
python3 scripts/run_multiagent_session.py PATH --log-level INFO 2>&1 | tee game.log
```

Four things to tell them, because each one bites:

- **Run from the repo root.** The launcher calls bare `load_dotenv()`, which walks up from the
  *current working directory*. The repo `.env` (with `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY`, `DEEPINFRA_API_KEY`) only loads if you are there. `export`ing the key works
  from anywhere.
- **A missing API key does not crash the run.** Provider construction is wrapped in a
  `try/except` that logs a warning and leaves `llm_provider = None`; the session then starts and
  degrades — agents fall back to `DEFENSIVE` actions with no obvious cause. If a run behaves
  inertly, check the top of the log for `Failed to create LLM provider`.
- **`game.log` is not created for you.** Nothing in the code writes it; the `tee` above is what
  makes the file the docs tell you to grep.
- **Smoke first.** Run `session_config_smoke.json` (2 rounds) before committing to a full
  session. It is the cheapest proof that credentials, providers, and the pipeline all work.

Optional, not required: the batch proxy (`cd ../aeonisk-transmedia-pipeline && python main.py
proxy-start`) cuts cost ~50% on bulk runs. If it is down the client retries 3× and falls back to
the direct API at full price — unless the config sets `proxy_strategy: "batch"` or `no_fallback`,
which makes it a hard failure instead.

Output lands at `<output_dir>/session_<uuid>.jsonl` — for the smoke config,
`multiagent_output/smoke/`.

## Stage 7 — Did it work?

**Completing is not success.** A session can run to the end and still be self-contradictory —
a stun-KO'd character still acting, a "subdued" prisoner spawned armed. The real gate:

```bash
python scripts/session_invariants.py multiagent_output/.../session_<uuid>.jsonl   # exit 0 = clean
python scripts/analyze_session.py   multiagent_output/.../session_<uuid>.jsonl --mode=errors
```

`session_invariants.py` runs 13 checkers and exits non-zero on any ERROR. Success = the run
completed (last event is `session_end`) **and** invariants are clean.

Then, depending on why they ran it:
- **Engine shakedown** — the two commands above, plus `analyze_session.py <file>` for the summary.
- **Research corpus** — scale up with `scripts/bulk_session_runner.py` (it auto-gates invariants
  and writes `invariant_violations.json` per run). Pull numbers with `scripts/session_extract.py`,
  which is a **library, not a CLI** — import it. Never grep narration for numbers; typed events
  only.
- **Story** — `python scripts/aeonisk/multiagent/reconstruct_narrative.py <file> > story.md`.

## Done when
The config validates clean, the audit shows no validator errors, the user has seen and accepted
the WILL/WON'T summary and the authored `scenario_hint`, and they have the run command in hand.
