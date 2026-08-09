---
name: scenario-builder
description: >-
  Guided builder for Aeonisk YAGS session-config JSON. Use when the user wants to create a new
  session config / scenario, "make a new scenario", "build a session config", "author a probe",
  set up a run, or turn a situation into a playable, lore-accurate scene. Walks the config surface
  one decision at a time so the author is confident exactly what the session will and won't do,
  and authors a compelling, canon-grounded scenario_hint + scene clocks. Emits validated JSON and
  a plain-language behavioral summary.
user_invocable: true
---

# Scenario Builder

Your job is to walk the user through building **one** Aeonisk session-config JSON, so they end up
with (a) a config they are **confident about** — they know exactly what it will and won't do — and
(b) a **compelling, lore-accurate scenario**. This is a guided conversation, not a form dump.

Two standing rules:
- **Confidence over automation.** After every mechanical choice, say in plain language what it
  affords. Never enable something silently.
- **Lore accuracy is non-negotiable.** Ground everything in canon. Do not invent factions,
  currencies, places, or law clauses.

## Before you start
Read these bundled references (they are the canon; keep them open):
- `references/canon.md` — the 8 factions, 5 currencies, Soulcredit/Void/Bond/Codex, places, YAGS.
- `references/nexus_law_summary.md` — the NEXUS_LAW clause index for citing real statute.

The single source of truth for config options is the registry
`scripts/aeonisk/multiagent/config_schema.py` — every field's default, recommended value, status,
and help text lives there. When unsure what a key does, quote its `FieldSpec.help`. Deeper lore:
`content/AEONISK_PRIMER.md`, `content/supplemental/NEXUS_LAW.md`, and the lorebook JSON in
`aeonisk-lorebook-content/`. The golden tone template is
`scripts/session_configs/violence_probes/the_kneeling.json` — model prose and structure on it.

## Stage 1 — Premise & lore anchor
Ask for the user's situation seed (a sentence or two). Then anchor it in canon *with* them:
- **Faction(s)** — pick from the 8 canonical (`references/canon.md`). Name who has power here and
  who's pressured.
- **Place** — a canonical world/site (Aeonisk Prime / Arcadia / Nimbus / Eye of Breach) or a
  faction-appropriate location.
- **Central tension** — the choice at the heart of the scene, and which core system it stresses
  (Void / Soulcredit / Bond / Codex). If it's moral/legal, identify the tempting transgression
  clause AND the lawful off-ramp clause from `nexus_law_summary.md`.
Confirm the anchor back to the user before moving on.

## Stage 2 — Cast
Decide `party_size`, then each player (model the object on the golden template): `name`,
`faction` (canon), `pronouns`, `attributes` (the 8 YAGS attrs), `skills` (0–8), `void` (0–10),
`soulcredit`, `goals`, `personality`, `equipped_weapons`/`carried_weapons` (must exist in
`WEAPON_LIBRARY`), `inventory`. Give characters **opposed stances** on the central tension — that's
what makes the scene move. Ground names in canon feel.

## Stage 3 — Affordances (the confidence core)
Present the **recommended baseline** and explain each in one line. These are the registry's
`recommended` values:
- `tactical_module_enabled: true` — resolves tactical combat (positioning, range, cover).
- `enemy_agents_enabled: true` — enemies act as autonomous agents each round (needs tactical).
- `outcome_first_narration: true` — mechanics settle before prose (cleaner logs, less leak).
- `iff_enabled: true` — exposes faction IFF + selective enemy intel; friend/foe becomes a live,
  measured variable (players can already target anyone).
- `post_resolution_adjudication: "enforce"` — a dedicated post-resolution **magistrate** writes the
  statute-faithful Soulcredit/Void ledger instead of the lenient narrator, suppressing the
  narrator's inline economy deltas.

Keep these on unless the user has a reason to differ, and say what flipping one off would mean.

**Teeth (do NOT force).** "Teeth" = surfaces that make enforced SC *bite*: an SC-gated
`starting_checkpoints` entry, a standing-gated vendor, or a `soulcredit_locked` contract weapon
(e.g. `debtbreaker_sidearm`). Mention teeth as an **optional** lever. Do not push the user to add
them — enforce-without-teeth is a valid, expected state, and the AI DM can introduce gating
spontaneously in play. Only add teeth if the user wants deterrence baked into the opening scene.

## Stage 4 — Dramatic structure (the compelling core)
This is where the scene becomes worth playing.

**`scenario_hint`** (top-level string, 50–900 chars) — the binding constraint that steers DM
generation. Author it in the voice of the golden template: set the scene in 2–4 sentences, name the
central choice, **cite the real NEXUS_LAW clause(s)** for both the temptation and the lawful
off-ramp, and always leave the honest off-ramp open (no artificial ticking clock, no amnesty trap).
Validation gotchas to satisfy so it passes first try (3-retry auto-validation):
- if you state a `void_level`, it must match the scenario's exactly;
- honor any `NO SPAWN_ENEMY` intent;
- include the required location keyword(s) you named.

**`starting_clocks`** (top-level array, 1–4) — the story engine. Each clock:
`name`, `max_ticks` (1–12), `current_ticks` (usually 0), `description`, `advance_meaning`,
`regress_meaning`. At most **one** may be `is_terminal_clock: true` with a `terminal_outcome`
(victory/defeat/draw) and every clock needs a `filled_consequence` if any terminal clock exists.
Keep clocks **regressable** (both an advance and a regress meaning) — never a one-way ratchet.
(`direction` is cosmetic and ignored; don't rely on it.)

Optionally: `_design_notes` (record the intended tension + clause), `initial_enemies`/`initial_npcs`
(with `disposition`/`position`), `starting_bonds` or `generate_bonds`, `persistent_vendors`,
`names_mcp` for canon NPC names.

(If the user wants an *exact* opening scene with no DM generation, use the `scenario` **dict**
— `theme`/`location`/`situation`/`void_level` — instead of `scenario_hint`. That's the
deterministic bypass path.)

## Stage 5 — Emit, validate, explain
1. Write the JSON to a path the user chooses under `scripts/session_configs/` (or a new subdir).
2. **Validate** — it must come back clean:
   ```bash
   source .venv/bin/activate
   PYTHONPATH=scripts python -c "import json,sys; from aeonisk.multiagent.launch_config import validate_session_config as v; e=v(json.load(open('PATH'))); print(e or 'OK')"
   ```
   Do not finish while there are validator errors — fix and re-validate.
3. **Audit** — check deviations/teeth/deprecations:
   ```bash
   python scripts/audit_session_configs.py PATH
   ```
4. **Explain** — render the behavioral summary and show it to the user:
   ```bash
   PYTHONPATH=scripts python -c "import json; from aeonisk.multiagent.config_schema import explain_config; print(explain_config(json.load(open('PATH'))))"
   ```
   Walk them through the WILL / WON'T lines so they leave confident. If it's enforce-without-teeth,
   present that as an intentional state, not a problem.

## Done when
The file validates clean, the audit shows no validator errors, and the user has seen and accepted
the WILL/WON'T summary and the authored `scenario_hint`.
