# Aeonisk Agent Fine-Tune Quality Plan

Created: 2026-06-24

## Purpose

The fine-tune target is broader than a DM-only model. Aeonisk should build a versioned, quality-gated, multi-role agent corpus from session JSONL so one model can reliably wear explicit Aeonisk roles:

- DM
- player
- enemy
- NPC

The first priority is not volume. The blocker is trust: the generated data must be mechanically accurate, role-correct, drift-aware, and useful for fine-tuning without teaching stale or broken game behavior.

## Core Principle

Do not treat raw JSONL as training data. Treat it as evidence.

Every training example must be derived from a validated session, assigned a role/task family, checked against that task's output contract, and recorded with enough provenance to explain why it was included.

## Role And Task Families

### DM

Candidate tasks:

- Scenario generation
- Action adjudication / `ActionResolution`
- Conversion and lifecycle decisions / `ConversionDecisions`
- Round synthesis
- Clock and story consequences
- NPC, enemy, altar, and environment spawning
- Purchase, transfer, ritual, void, soulcredit, and clock enforcement

Primary DM quality risks:

- Invalid or missing structured mechanics
- Wrong target IDs or name-as-target errors
- Unspawned invented entities
- Duplicate enemy/NPC/environment spawns
- Incorrect void, soulcredit, economy, or clock changes
- Schema fallback or pydantic validation failures
- Output that sounds good but contradicts the logged mechanics

### Player

Candidate tasks:

- Intent selection
- Action declaration
- Tactical cooperation
- Ritual, purchase, transfer, consume, support, and investigation declarations
- Character-goal-driven choices
- Mission debrief voice

Primary player quality risks:

- Impossible actions
- Inventory, skill, or position misuse
- Invalid target IDs
- Ignoring stated goals or personality
- Player output trying to adjudicate DM mechanics

### Enemy

Candidate tasks:

- Tactical combat declaration
- Target selection
- Weapon and range choice
- Morale, surrender, retreat, and shared-intel behavior

Primary enemy quality risks:

- Illegal target, range, or weapon use
- Omniscient or out-of-role decisions
- Ignoring morale or retreat thresholds
- Tactical declaration format drift
- Hostile behavior after surrender/compliance should have occurred

### NPC

Candidate tasks:

- Dialogue actions
- Civilian panic/cooperation
- Vendor behavior
- Faction-aligned social behavior
- Escalation/de-escalation when threatened

Primary NPC quality risks:

- Acting like a full player or enemy without lifecycle escalation
- Inventing major world state changes
- Vendor inventory or price violations
- Ignoring disposition, faction, or threat level

## Dataset Shape

The corpus should be multi-role and multi-task, but never anonymous.

Every example must carry or imply a stable task identity:

```text
AEONISK_AGENT_ROLE: dm | player | enemy | npc
AEONISK_AGENT_TASK: action_resolution | conversion_check | tactical_declaration | ...
OUTPUT_CONTRACT: exact expected shape for that task
```

The final training JSONL may be combined, but the manifest must preserve:

- Role
- Task family
- Source session path
- Source line/event id
- Game git commit
- Prompt fingerprint or prompt version
- Teacher provider/model
- Scenario/config family
- Validation status
- Inclusion or rejection reason

## Data Tiers

### Gold

Eligible for training.

Requirements:

- Completed session
- No schema, ordering, integrity, or LLM validation errors
- No pydantic failures
- No fallback-triggered structured outputs
- Example-level role/task contract passes
- Current or explicitly versioned game/prompt/model slice

### Silver

Not automatically eligible.

Structurally valid, but contains warnings or behavior concerns that need review or regeneration. Silver examples may be promoted only by an explicit allowlist with a reason.

### Quarantine

Not eligible for training.

Examples:

- Incomplete session
- Crashed session
- Schema drift
- Validator crash
- Unpaired LLM call and downstream event
- Missing required mechanics
- Warning-bearing mechanics such as missing ritual void consequences
- Invalid target IDs

### Eval-Only

Useful hard cases, not training examples.

Examples:

- Past failure cases
- Warning sessions
- Weird but instructive edge cases
- Regressions we want the fine-tuned model to avoid

## Drift Policy

Never silently blend across game or model drift.

Corpus slices should be keyed by:

```text
game_commit + prompt_fingerprint + role + task + teacher_model + scenario_family + generation_date
```

Blended corpora must have their own manifest and list every component slice. If two slices encode contradictory rules, they should not be blended for training.

## Validation Strategy

Quality gates must be layered.

### Session-Level Gates

Use existing tools first:

- `scripts/yags_mine.py validate`
- schema validator
- ordering validator
- integrity validator
- LLM fallback and pydantic failure checks

Hard reject sessions with:

- Missing `session_end`
- Real validator errors
- Structured output fallback
- Pydantic validation failures
- Unhandled schema drift

### Example-Level Gates

Each role/task family needs its own detector, target builder, and quality checks.

Examples:

- DM action resolution must pair a DM `llm_call` with an `action_resolution`.
- DM conversion must pair with lifecycle/entity events where possible.
- Player action must pair with `action_declaration`.
- Enemy tactical output must pair with `action_declaration` or `combat_action`.
- NPC dialogue must pair with NPC action/lifecycle context where available.

### Distribution And Balance Review

Validation is not balance.

Run balance and distribution reports per slice:

- Skill success rates
- Outcome-tier distribution
- Action type distribution
- Scenario family distribution
- Role/task distribution
- Targeting anomalies
- Void and soulcredit movement
- Clock advancement/regression behavior
- Enemy lethality and survival
- Purchase/economy behavior

These reports should usually warn rather than hard reject, unless they reveal concrete mechanical invalidity.

## Target Construction

Do not assume one target strategy fits all roles.

Possible targets:

- Raw logged model response
- Canonical structured object reconstructed from downstream JSONL
- Hybrid target using raw narration plus canonical mechanics

Recommended starting policy:

- DM action resolution: canonical structured target where possible, because mechanical truth matters more than teacher prose.
- DM conversion: canonical `ConversionDecisions`.
- DM round synthesis: structured response if available, otherwise raw bounded narration.
- Scenario generation: raw structured scenario only if constraints can be machine-checked.
- Player action declaration: raw structured declaration if it validates against game state.
- Enemy tactical declaration: raw tactical declaration if paired with legal downstream action/combat.
- NPC dialogue: raw prose can be acceptable, but only with strict role/context checks.

## Implementation Direction

Build a task registry rather than a one-off exporter.

Each task definition should contain:

- `role`
- `task`
- detector for relevant `llm_call` events
- pairing logic for downstream JSONL events
- target builder
- hard quality checks
- warning checks
- manifest metadata extractor
- eval metrics

The exporter should produce:

- `train.jsonl`
- `validation.jsonl`
- `manifest.json`
- `examples_manifest.jsonl`
- `quarantine.jsonl`
- `quality_report.md`

Train/validation split must be by session, not individual example, to avoid leakage.

## Recommended V1

Start with a core mechanics corpus, not all prose.

V1 role/task families:

- `dm/action_resolution`
- `dm/conversion_check`
- `enemy/tactical_declaration`
- `player/action_declaration`

V1 should exclude or keep eval-only:

- Mission debriefs
- Long narrative-only NPC prose
- Scenario generation without constraint-checking
- Warning-bearing ritual/void examples

After V1 quality is proven, expand to:

- `dm/round_synthesis`
- `dm/scenario_generation`
- `npc/dialogue_action`
- `dm/clock_consequence`

## Current Repo Facts From Initial Audit

Observed in current `bulk_output` sample:

- 28 session JSONL files
- 1,528 total `llm_call` events
- 886 DM calls
- 514 player calls
- 128 enemy calls
- DM call families roughly detected:
  - 561 action-resolution-like calls
  - 145 dialogue/narration/other calls
  - 134 conversion-check calls
  - 39 round-synthesis calls
  - 7 scenario-generation calls

The corpus already contains many useful event types beyond `llm_call`, including:

- `action_declaration`
- `action_resolution`
- `structured_output_metrics`
- `clock_advancement`
- `round_synthesis`
- `combat_action`
- `enemy_spawn`
- `clock_spawn`
- `entity_lifecycle`
- `purchase_attempt`
- `mission_debrief`

This confirms the fine-tune should use the full JSONL event graph for quality and target construction, not just prompt/response pairs.

## Open Questions

- Which current commit/prompt/model slice should be the first canonical generation target?
- Should role/task tags be injected into fine-tune prompts, or only recorded in manifests when existing prompts already imply them?
- Which warnings are ever promotable from Silver to Gold?
- Should canonical structured targets exactly match runtime schemas, or use a simplified training schema?
- How much narrative data should be mixed into a mechanics-first corpus without diluting reliability?

## North Star

The goal is a fine-tuned Aeonisk agent model that can run the game loop more reliably than a general model because it has learned the role boundaries, mechanics, JSON contracts, and pacing rules of Aeonisk from trusted, versioned, validated examples.

If data quality is uncertain, do not train on it. Quarantine it, fix the generator or prompts, regenerate, then revalidate.
