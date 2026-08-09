# 3. Sessions, Configuration, and Output

## 3.1 Session configuration is the experiment boundary

A config describes one experiment: who plays, which models are used, how many rounds are allowed, what scenario/tactical systems are active, and where records go. Keep configs immutable once a run starts. If you change a config and rerun, give the experiment a new name or preserve the old config beside the output.

The minimal shape is:

```json
{
  "session_name": "investigation_smoke",
  "max_turns": 5,
  "party_size": 2,
  "output_dir": "./multiagent_output",
  "agents": {
    "dm": {
      "llm": { "provider": "openai", "model": "gpt-5-mini", "temperature": 0.7 }
    },
    "players": [
      {
        "name": "Analyst",
        "faction": "Freeborn",
        "llm": { "provider": "openai", "model": "gpt-5-mini", "temperature": 0.8 },
        "attributes": {"Strength": 3, "Agility": 4, "Endurance": 4},
        "skills": {"Investigation": 5, "Awareness": 5}
      }
    ]
  }
}
```

The example above is intentionally incomplete for a full scenario; use an existing config under `scripts/session_configs/` as a complete template (`violence_probes/the_kneeling.json` is a good lore-rich one).

## 3.2 The config schema is the single source of truth

The config surface used to be an undocumented bag of keys read by scattered `config.get(key, default)` calls. It is now described declaratively in one place:

> **`scripts/aeonisk/multiagent/config_schema.py`** — `CONFIG_SCHEMA`, a list of `FieldSpec` entries keyed by dotted path (`[]` marks list-element fields, e.g. `agents.players[].skills`, `persistent_vendors[].inventory[].price_spark`). Each field records its **code-truth default**, a research-**recommended** value where one differs, its **status** (`active` / `deprecated` / `vestigial`), deprecation target, cross-field dependency, and a one-line **help** string. Every `FieldSpec` carries a `note` pointing at the file/line where the engine actually reads it.

When you are unsure what a key does or what it defaults to, read its `FieldSpec` — do not guess and do not trust older docs or READMEs (a few, such as `free_targeting_mode`'s default, disagree with the code; the registry follows the code). Useful accessors: `by_path`, `defaults`, `recommended_overrides`, `deprecations`, `vestigial_keys`, and `explain_config` (see 3.7).

The registry drives the validator (`launch_config.validate_session_config`) and a drift test (`tests/unit/test_config_schema.py`) that fails if code starts reading a key the registry does not describe, so the schema cannot silently rot.

**Deprecated keys** the registry tracks (compat code may still accept them, but prefer the replacement): `void_score` → `void`; `scenario.initial_clocks` → root `starting_clocks`; `_scenario_hint` → `scenario_hint`; `agents.enemy_agents` → `agents.enemies`.

**Vestigial keys** are set in many shipped configs but the engine never reads them — do not rely on them: the `enemy_agent_config` sub-keys `allow_groups`, `max_enemies_per_combat`, `shared_intel_enabled`, `auto_execute_reactions`, `loot_suggestions_enabled`, `void_tracking_enabled`, and a clock's cosmetic `direction`.

## 3.3 Important top-level fields

| Field | Default | Meaning |
|---|---|---|
| `session_name` | required | Human-readable experiment label. |
| `max_turns` | 50 | Round cap; a session may end earlier via story/terminal decisions. |
| `party_size` | 2 | Expected party size, used by setup and validation. |
| `output_dir` | `./multiagent_output` | Root for JSONL and related output. |
| `tactical_module_enabled` | false | Tactical combat systems + enemy resolution support. |
| `enemy_agents_enabled` | false | Autonomous enemy agents. **Requires `tactical_module_enabled`.** |
| `outcome_first_narration` | false | Outcome-first pipeline (mechanics settle before prose). |
| `iff_enabled` | false | IFF/ROE mode: faction identity + selective enemy intel become live. |
| `post_resolution_adjudication` | false | Soulcredit/Void adjudication regime — see 3.5. |
| `dm_assessment_enabled` | true | One authoritative DM difficulty call per round, before dice. |
| `bonds_enabled` | true | Bond system + Void-driven transitions. |
| `enemy_agent_config` | {} | Enemy tuning; only `free_targeting_mode` (default **true**) is read (others are vestigial). |
| `initial_enemies` / `initial_npcs` | [] | Pre-spawned entities at session start (parsed in `initial_spawns.py`). |
| `vendor_spawn_frequency` | 3 | `-1` never, `0` off (legacy), `N` every N rounds. |
| `persistent_vendors` | [] | Vendors created at setup; each has an `inventory[]` priced in the five currencies. |
| `starting_clocks` | [] | Root-level scene clocks (`NewClock` shape) — see 3.6. Avoid the deprecated nested form. |
| `starting_checkpoints` | [] | Soulcredit-gated checkpoints. |
| `scenario` | {} | Direct scenario dict (`theme`/`location`/`situation`/`void_level`): the deterministic bypass path. |
| `scenario_hint` | "" | Binding constraint string steering DM scenario generation — see 3.6. |
| `names_mcp` | {} | `{enabled, from_pool}` — canon NPC naming. |

The authoritative and complete list (including every nested player/vendor/clock/enemy sub-field) is `CONFIG_SCHEMA`; this table is the orientation subset.

## 3.4 Feature flags and the recommended research baseline

Five flags carry a research-recommended value that differs from the code default. They are captured in `config_schema.recommended_overrides()`:

| Flag | Recommended | Why |
|---|---|---|
| `tactical_module_enabled` | true | Otherwise "the model won't" is confounded with "the harness didn't afford it." |
| `enemy_agents_enabled` | true | Same affordance argument; needs tactical. |
| `outcome_first_narration` | true | Cleaner logs, less mechanics leak into prose. |
| `iff_enabled` | true | Players can already target anyone; IFF makes friend/foe a measured variable rather than an assumption. |
| `post_resolution_adjudication` | `"enforce"` | The statute-faithful ledger (see 3.5). |

These are *recommendations*, not requirements — a config that differs is valid; the audit (3.7) simply reports the deviation so a confounded run is a deliberate choice, not an accident.

## 3.5 Adjudication regimes and "teeth"

`post_resolution_adjudication` chooses who writes the Soulcredit/Void ledger each round. This matters because the same model convicts far more leniently when it adjudicates *inside* the busy narration call than when a dedicated call applies the statute in isolation.

- `false` — off. The **narrator writes the ledger inline** as part of the main narration call (the lenient default).
- `true` / `"full_context"` — **observe-only**: a dedicated post-resolution call logs Nexus-law rulings each round but does **not** apply them (`full_context` also feeds it the story so mitigation is knowable).
- `"enforce"` — the **magistrate writes the ledger**: the dedicated call's rulings become the applied Soulcredit/Void changes, and the narrator's inline economy deltas are suppressed so they are not double-counted. Corpus label flips to `v1.1-law-LIVE`.

**"Teeth"** are separate from the flag — they are scenario *structure* that makes an enforced ledger actually bite: a Soulcredit-gated `starting_checkpoints` entry, a standing-gated vendor, or a `soulcredit_locked` contract weapon (e.g. `debtbreaker_sidearm`). Enforce **without** teeth records the ledger but applies no pressure; that is a valid, expected state (a DM can introduce gating in play). The audit flags enforce-without-teeth as neutral information, not an error. See `config_schema.has_teeth()` and `post_adjudication.py` for the mechanism.

## 3.6 Authoring the scenario: `scenario_hint` and clocks

There are two ways to specify the opening scene:

- **`scenario_hint`** (top-level string, 50–900 chars) — a *binding constraint* that steers DM generation. It is auto-validated with up to 3 retries: if you state a `void_level` it must match exactly, any `NO SPAWN_ENEMY` intent is honored, and required location keywords must appear. Write it like `violence_probes/the_kneeling.json`: set the scene, name the central choice, cite the real `NEXUS_LAW` clause(s) for both the temptation and the lawful off-ramp, and leave the honest off-ramp open (no artificial clock, no amnesty trap).
- **`scenario` dict** (`theme`/`location`/`situation`/`void_level`) — the deterministic bypass: the DM uses this exact scene instead of generating one.

**`starting_clocks`** (root-level array, 1–4) is the story engine. Each clock (the `NewClock` shape) needs `name`, `max_ticks` (1–12), `description`, and both an `advance_meaning` and a `regress_meaning` — keep clocks regressable, never a one-way ratchet. At most one clock may be `is_terminal_clock: true` with a `terminal_outcome` of `victory`/`defeat`/`draw`; if any terminal clock exists, every clock needs a `filled_consequence`. `current_ticks` defaults to 0. (`direction` is cosmetic and ignored.) The scenario/clock shapes live in `scripts/aeonisk/multiagent/schemas/story_events.py` (`ScenarioSetup`, `NewClock`).

## 3.7 Checking a config: validate, audit, explain

Three tools, all read-only, answer "is this config valid and what will it do?" (shell in `aeonisk-yags/` with `.venv` active):

```bash
# Validate — must return [] (empty) to be clean:
PYTHONPATH=scripts python -c "import json; from aeonisk.multiagent.launch_config import validate_session_config as v; print(v(json.load(open('CONFIG.json'))) or 'OK')"

# Audit — deviations from the recommended baseline, deprecated/vestigial/unknown keys,
# enforce-without-teeth, and validator errors (add --json or --only-issues):
python scripts/audit_session_configs.py CONFIG.json
python scripts/audit_session_configs.py scripts/session_configs   # sweep the whole corpus

# Explain — plain-language "what this session WILL and WON'T do":
PYTHONPATH=scripts python -c "import json; from aeonisk.multiagent.config_schema import explain_config; print(explain_config(json.load(open('CONFIG.json'))))"
```

`explain_config` is registry-driven, so it stays truthful as the schema evolves. The audit is also the fastest way to see how far the shipped corpus sits from the current baseline.

## 3.8 The scenario-builder skill

To create a new config from a situation, use the **`/scenario-builder`** skill (`.claude/skills/scenario-builder/`). It walks the config surface one decision at a time — premise and lore anchor, cast, affordances, dramatic structure, then emit/validate/explain — so you finish confident about exactly what the session will and won't do, with a canon-grounded `scenario_hint`. It bakes in the recommended baseline, keeps enforce on but never forces teeth, and reads bundled canon (`references/canon.md`, `references/nexus_law_summary.md`) to keep scenarios lore-accurate.

## 3.9 Agent blocks

### DM

`agents.dm.llm` selects the DM provider/model. The DM consumes scenario context, current state, action declarations, rules guidance, and previous narrations, and returns structured adjudication/synthesis objects (with compatibility handling for older shapes). Optional `agents.dm.narrative_style` / `tone_guidance` add authoring guidance.

### Players

Each player supplies `name`, `faction`, `llm`, and optionally `pronouns`, `personality`, `goals`, `attributes`, `skills`, `void` (0–10), `soulcredit`, `bonds`, `equipped_weapons`/`carried_weapons` (ids must exist in `WEAPON_LIBRARY`), `inventory`, and `starting_currency`. These are read while building `CharacterState` in `player.py` (≈lines 413–429); every field is in `CONFIG_SCHEMA` under `agents.players[].*`. A player may instead reference a fixture with `character_ref`. Personality is behavioral context, not mechanics: risk tolerance can influence declarations, but it does not alter a dice result unless the rules path applies a bonus.

### Enemies

Current configs use `agents.enemies.llm` for the enemy tier; the runtime also understands the legacy `agents.enemy_agents` shape. Spawn declarations use `initial_enemies` (fields: `name`, `template`, `faction`, `archetype`, `count`, `position`, `disposition`, `spawn_reason`, `tactics`), parsed in `initial_spawns.py`. An `initial_enemies` entry whose `disposition` is prisoner/friendly/neutral is rerouted to a disarmed NPC.

### NPCs

`agents.npcs.llm` routes NPC LLM calls; otherwise the runtime falls back to the enemy tier, legacy enemy tier, and finally DM tier. `initial_npcs` entries (`name`, `faction`, `entity_type`, `threat_level`, `disposition`, `description`, `health`, `soak`, `skills`) always become NPCs.

## 3.10 Provider and proxy precedence

The config is authoritative when it contains a value. Explicit CLI overrides can change proxy routing and are reported. Omitted proxy fields receive provider defaults and may also see environment fallbacks.

For a batch proxy:

```json
{
  "provider": "batch_proxy",
  "model": "gpt-5-mini",
  "underlying_provider": "openai",
  "use_proxy": true,
  "proxy_url": "http://localhost:8000",
  "proxy_strategy": "auto",
  "proxy_priority": "normal"
}
```

CLI examples:

```bash
python scripts/bulk_session_runner.py \
  --config scripts/session_configs/session_config_combat.json \
  --runs 20 --workers 4 --proxy http://localhost:8000

python scripts/bulk_session_runner.py \
  --config config.json --runs 20 --strategy batch --dry-run
```

`--dry-run` is the safest way to inspect the effective route. `--proxy` alone does not override a config's strategy; pass `--strategy` when you intend to force one.

## 3.11 Bulk generation

`scripts/bulk_session_runner.py` launches independent sessions, isolates output, tracks progress, aggregates statistics, and can resume runs:

```bash
python scripts/bulk_session_runner.py \
  --config config.json \
  --runs 100 \
  --workers 20 \
  --output-dir bulk_output \
  --progress
```

Use `--configs` with `--runs-per-config` for a matrix of experiments. Use `--resume --run-dir ...` after failures; replay is enabled by default for cost saving, while `--no-replay` restarts from scratch. Configs are validated at launch (same checks as `validate_session_config`); some legacy dirs under `session_configs/experiment/` and `session_configs/openai/` need `--skip-validation`.

## 3.12 Output anatomy

A single run can produce:

```text
multiagent_output/
├── session_<id>.jsonl       # canonical event stream
├── ...                       # optional analysis/session artifacts
agent_logs/
└── <session_id>/             # optional full prompts/responses
```

Bulk output typically adds a run directory and metadata. Keep the config, command line, seed, model versions, and output together; an event stream without its inputs is difficult to reproduce.

## 3.13 Configuration pitfalls

- `party_size` and the actual player list can diverge; validation catches some cases, but do not rely on implicit trimming.
- Vestigial keys (3.2) look like knobs but do nothing — check `config_schema.vestigial_keys()` before assuming a key has an effect.
- Legacy/deprecated keys may still be accepted by compatibility code but may not behave identically to current keys; the audit reports them.
- Enforce without teeth (3.5) records the ledger but applies no pressure — intended in many probes, but confirm it is what you want.
- A model can return a valid-looking action targeting an entity that no longer exists. Target mapping and resolution-state validation must still reject it.
- Attribute names are duplicated across mechanics, schemas, validators, and prompts; change all layers together and run alignment tests when altering them.
