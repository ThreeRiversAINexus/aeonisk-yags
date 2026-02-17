# Aeonisk v2 Specification Suite

## Overview

This directory contains 18 specification files that define the Aeonisk v2 system
overhaul. The specs were generated from baseline datamining of **25 sessions
across 5 LLM providers** (GPT-5.2, Grok 4, Gemini 2.5 Pro, DeepSeek V3.2,
Claude Opus 4.6) using the Combat Ambush scenario as the control condition.

The datamining revealed systemic issues in combat resolution, entity lifecycle
management, target validation, and agent awareness that cannot be addressed
through prompt tuning alone. These specs define the mechanical, schema, and
architectural changes required to make the multi-agent combat system produce
coherent, measurable, and mechanically honest outcomes.

Raw findings are in `.claude/baseline_datamining/`. The human-curated issue list
that seeded these specs is in `.claude/human_curated_todo/2026--02-14.md`.

---

## Priority Matrix

| ID | Priority | Spec Title | Summary |
|----|----------|------------|---------|
| 01 | **P0** | NPC Combat Mechanics | NPCs declare attacks but deal 0 damage through all code paths; give NPCs the same combat resolution pipeline as enemies. |
| 02 | **P0** | Enemy Lifecycle & Defeat Semantics | `enemy_defeat` conflates kills, departures, and despawns; separate defeat reasons into distinct event types with mechanical consequences. |
| 03 | **P0** | Target Validation & Free-Target Binding | DM resolves free-target IDs (`tgt_xxxx`) to prisoners and civilians when players described hostile combatants; add validation constraints on target eligibility. |
| 04 | **P2** | Defense Tokens | Defense tokens are defined in prompts but never generated or consumed by any agent; implement the token lifecycle. |
| 05 | **P1** | Stealth & Hidden State | Stealth is declared but has no mechanical effect on targeting, visibility, or initiative; implement hidden-state tracking with last-known-position logic. |
| 06 | **P1** | IFF & Rules of Engagement | All combatants receive an `ally` label regardless of faction; replace with perception-gated faction discovery and selective intel sharing. |
| 07 | **P1** | Inventory & Equipment Interaction | Players cannot meaningfully interact with equipped items; NPCs lack purses for currency; enemy loot is inaccessible; overhaul the item/equipment pipeline. |
| 08 | **P1** | Suppression Resolution | Suppressive fire deals the same wound damage as lethal fire (base_damage 20.9 vs 19.3 at identical margins); implement condition-based suppression with near-zero damage. |
| 09 | **P2** | Range Bands & Movement | Players frequently attempt invalid range-band transitions; agents lack sufficient awareness of range-band topology and movement costs. |
| 10 | **P2** | Environmental Objects & Destructibles | Environmental objects exist in narration but cannot be mechanically damaged or destroyed; add destructible-object schemas and resolution. |
| 11 | **P2** | Experiment Infrastructure | Bulk configs cannot vary models independently for DM, players, NPCs, and enemies; legacy vs structured code paths need formal routing. |
| 12 | **P3** | Display & Observability | Session output lacks structured display of combatant state, range bands, and clock progression; add formatted status overlays for human observers. |
| 13 | **P3** | Bonds & Vendor Spawning | Bond system dormancy transitions are untested in live sessions; DM never spawns vendors because prompting does not guide it. |
| 14 | **P0** | Conditions & Modifiers | Condition pipeline has 6 bugs: descriptions claim selective targeting but apply to all rolls; `target` field lost in extraction; duration hardcoded to 3 and never ticked; `affects` dead code; `protection_amount` not propagated. |
| 15 | **P1** | Resolution Phase Skip | Player actions bypass all mid-round state validation; no structured output path for DM to declare narrative preemption; skipped actions invisible to later agents. Two-phase fix: hard auto-skip via ActionValidator for players, DM narrative skip via new `action_skipped` field on ActionResolution. |
| 16 | **P1** | Adjudication Context | DM adjudicates every action statelessly (2 messages, no history); soulcredit scoring has no visibility into prior cooperation arcs, repeated behavior, or in-round context. Causes false betrayal penalties, inconsistent scoring, noisy ML labels. Fix: inject soulcredit ledger, in-round action recap, and rolling narrative digest into adjudication prompt. |
| 17 | **P1** | Clock Persistence | Story advancement blanket-clears all scene clocks; kills multi-scene arcs. ScenePivot already has selective clearing (`clear_specific_clocks`) but StoryAdvancement has no equivalent. Fix: add `keep_clocks` field so DM can carry forward ongoing threats/objectives across scene boundaries. |

---

## Implementation Order

### Wave 1 -- P0, Parallel

All four specs address fundamental mechanical correctness bugs that corrupt
downstream analysis. They have no interdependencies and can be implemented
concurrently.

| Spec | Key Deliverable | Estimated Scope |
|------|----------------|-----------------|
| 01_NPC_COMBAT | NPC combat resolution pipeline, damage application, double-logging fix | Medium |
| 02_ENEMY_LIFECYCLE | Distinct defeat event types, `pc_defeated` flag fix, 0-HP status edge case | Medium |
| 03_TARGET_VALIDATION | Free-target eligibility filter, prisoner/civilian exclusion, naming deduplication | Medium |
| 14_CONDITIONS | Condition extraction fix, duration from LLM, tick_conditions() caller, prompt description fixes | Medium |

**Gate:** Wave 1 must be complete before running treatment experiments. All
datamining analysis depends on these events being mechanically correct and
conditions being honestly described in training data.

### Wave 2 -- P1, Sequential

These specs build on each other in a defined order. Stealth feeds into IFF (hidden
agents are not visible for identification). IFF feeds into inventory (faction
determines loot access and vendor trust). Suppression depends on the resolution
pipeline being stable after Wave 1.

| Order | Spec | Depends On |
|-------|------|-----------|
| 1 | 05_STEALTH | Wave 1 complete (target validation must respect hidden state) |
| 2 | 06_IFF_ROE | 05_STEALTH (hidden agents bypass IFF checks) |
| 3 | 07_INVENTORY | 06_IFF_ROE (faction determines vendor access and loot rules) |
| 4 | 08_SUPPRESSION | Wave 1 complete (NPC combat + target validation must be stable) |
| 5 | 15_RESOLUTION_SKIP | 14_CONDITIONS (condition ticking must work for condition-based skip triggers) |
| 6 | 16_ADJUDICATION_CONTEXT | None (independent, but benefits from 06_IFF_ROE for Phase 3 faction relationships) |
| 7 | 17_CLOCK_PERSISTENCE | None (independent, parallel with any Wave 2 spec) |

### Wave 3 -- P2, Parallel After Wave 1

These specs address mechanical gaps that are important but do not block
experiment execution. They can be implemented in parallel once Wave 1 is done.

| Spec | Key Deliverable |
|------|----------------|
| 04_DEFENSE_TOKENS | Token generation, consumption, and expiry lifecycle |
| 09_RANGE_MOVEMENT | Range-band topology validation, movement cost enforcement, agent awareness prompts |
| 10_ENV_OBJECTS | Destructible object schema, HP tracking, cover degradation mechanics |
| 11_EXPERIMENT_INFRA | Per-role model config, code-path router (structured/legacy/proxy), bulk config generator |

### Wave 4 -- P3, Parallel After Wave 2

Quality-of-life and completeness work. No other specs depend on these.

| Spec | Key Deliverable |
|------|----------------|
| 12_DISPLAY | Formatted combatant status tables, range-band map, clock progress bars |
| 13_BONDS_VENDORS | Live bond transition tests, vendor spawn prompting, NPC purse initialization |

---

## Dependency Graph

```
                    +-----------------------------------------------------------+
                    |                     WAVE 1 (P0)                        |
                    |  +----------+ +----------+ +----------+ +-----------+ |
                    |  | 01_NPC   | | 02_ENEMY | | 03_TARGET| | 14_CONDI- | |
                    |  | COMBAT   | | LIFECYCLE| | VALID.   | | TIONS     | |
                    |  +----+-----+ +----+-----+ +----+-----+ +-----+-----+|
                    +-------+------------+------------+--------------+------+
                            |            |            |           |
              +-------------+------------+------------+-----------+--+
              |             v            v            v           v  |
              |         WAVE 1 GATE (all four complete)              |
              +------+------------------+-----------------+------+
                     |                  |                  |
          +----------v---+   +----------v----------+  +---v------------------+
          |  WAVE 2 (P1) |   |  WAVE 3 (P2)       |  |                      |
          |  Sequential  |   |  Parallel           |  |  08_SUPPRESSION (P1) |
          |              |   |                     |  |  (parallel w/ Wave 2 |
          |  05_STEALTH  |   |  04_DEFENSE         |  |   after Wave 1 gate) |
          |      |       |   |  09_RANGE           |  +----------------------+
          |      v       |   |  10_ENV_OBJ         |
          |  06_IFF_ROE  |   |  11_EXPERIMENT      |
          |      |       |   |                     |  +------------------------+
          |      v       |   +---------------------+  | 15_RESOLUTION_SKIP(P1) |
          |  07_INVENTORY|                             | (after 14_CONDITIONS   |
          +------+-------+                             |  in Wave 1)           |
                 |                                     +------------------------+
          +------v----------+
          |  WAVE 4 (P3)    |  +---------------------------+
          |  Parallel        |  | 16_ADJUDICATION_CTX (P1)  |
          |                 |  | (no hard deps, parallel    |
          |  12_DISPLAY     |  |  w/ Wave 2; Phase 3        |
          |  13_BONDS_VEND. |  |  benefits from 06_IFF_ROE) |
          +-----------------+  +---------------------------+
                               +---------------------------+
                               | 17_CLOCK_PERSIST (P1)     |
                               | (no deps, parallel w/     |
                               |  Wave 2; small scope)     |
                               +---------------------------+
```

Key dependency relationships:

- **03_TARGET_VALIDATION --> 05_STEALTH:** Target eligibility must account for
  hidden state (hidden agents are not valid free-target candidates for enemies
  that have not detected them).
- **05_STEALTH --> 06_IFF_ROE:** Hidden agents bypass faction identification
  checks. Stealth mechanics define when an agent becomes "visible" for IFF
  purposes.
- **06_IFF_ROE --> 07_INVENTORY:** Faction identification determines vendor
  trust levels, loot access permissions, and item transfer rules between agents
  of different factions.
- **08_SUPPRESSION** depends only on Wave 1 gate (stable combat resolution
  pipeline), not on the sequential Wave 2 chain. It can be implemented in
  parallel with 05-07. Suppression relies on correct condition application
  (14_CONDITIONS) for Pinned/Shaken/Suppressed effects.
- **14_CONDITIONS** has no dependencies on other specs and can be implemented
  in parallel with 01-03. Spec 08_SUPPRESSION is a downstream consumer of
  correct condition behavior.
- **15_RESOLUTION_SKIP** depends on 14_CONDITIONS for condition-based
  incapacitation checks (e.g., Stunned penalty >= -6 triggers auto-skip).
  Phase 2 (DM narrative skip) has no condition dependency and can be
  implemented independently. Placed in Wave 2 after 14_CONDITIONS.
- **16_ADJUDICATION_CONTEXT** has no hard dependencies and can be implemented
  in parallel with any wave after Wave 1. Phase 3 (faction relationships)
  benefits from 06_IFF_ROE's faction discovery infrastructure but can be
  implemented independently with a simpler tracker. Improves soulcredit
  coherence for all downstream specs that generate SC changes (especially
  08_SUPPRESSION's +1 restraint reward).

---

## Cross-Cutting Conventions

All specs in this suite share the following constraints.

### Test-Driven Development (Mandatory)

Every spec must follow the TDD protocol defined in `CLAUDE.md`:

1. Write failing tests first (red phase).
2. Implement minimum code to pass (green phase).
3. Refactor with tests green (refactor phase).

Test files go in `tests/unit/test_*.py`. No implementation code is written
before a failing test exists for the behavior it implements.

### Structured Output Philosophy

The Aeonisk system uses Pydantic-validated structured output from LLMs as the
source of truth for all mechanical effects. This philosophy is non-negotiable:

- **DO:** Define new mechanics as Pydantic schema fields that the LLM generates.
- **DO:** Validate mechanical output through schema validators at generation time.
- **DO:** Keep narration and mechanics in separate fields (freeform text vs
  typed structures).
- **DO NOT:** Detect keywords in narration text to trigger mechanical effects.
- **DO NOT:** Parse freeform narration for damage values, status effects, or
  state changes.
- **DO NOT:** Hardcode faction behaviors based on name patterns or string
  matching.

### Pydantic Schemas Drive Mechanics

New mechanical systems introduced by any spec must be expressed as Pydantic
models in `scripts/aeonisk/multiagent/schemas/`. The DM LLM generates instances
of these models as part of its structured output. The Python runtime validates
and applies them deterministically. The LLM never "runs" game mechanics -- it
declares outcomes, and the engine enforces them.

### JSONL Logging for All Changes

Every new mechanical system must emit JSONL events for ML training data. The
authoritative schema reference is `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`.
New event types must be documented there before implementation. Existing event
types should be extended (not duplicated) when adding fields.

### Prompt Modules Over Monolithic Prompts

New DM capabilities use the modular prompt system (`prompts/claude/en/dm/`).
Each prompt module has a `load_when` condition and is loaded only when relevant
(e.g., `dm_resolution_combat_suppression.yaml` loads only for combat actions
with suppressive intent). The `_get_required_dm_modules()` method in `dm.py`
controls routing. See `tests/unit/test_dm_module_routing.py` for the test
pattern.

### Backward Compatibility

Session configs from v1 must continue to load and run. New fields use defaults
that preserve existing behavior. Bulk runner output from before and after a spec
implementation must be comparable via `diff_fixtures.py`.

---

## Glossary

### Agent Types

| Agent | Role | Code Entry Point |
|-------|------|-----------------|
| **DM** | Dungeon Master. Narrates scenes, adjudicates player and enemy actions, manages clocks and entity lifecycle. Generates structured output (ActionResolution, RoundSynthesis). | `dm.py` |
| **PC** (Player Character) | Autonomous player agent. Declares actions via structured output (PlayerAction). Has character sheet, inventory, health, void score. | `player_agent.py` |
| **Enemy** | Hostile combatant managed by the tactical module. Declares actions via enemy AI, resolved by the legacy combat pipeline in `mechanics.py`. Has template-based stats (Grunt, Enforcer, Elite, Boss). | `enemy_combat.py` |
| **NPC** | Non-player character. Converted from enemies (surrender/de-escalation) or spawned by the DM. Limited action set: flee, hide, plead, comply, dialogue, assist, pass. Cannot currently deal combat damage. | `npc_agent.py` |

### Resolution Pipeline Stages

The game loop processes each round in four phases:

1. **DECLARATION** -- All PCs and enemies simultaneously declare their intended
   actions. PCs generate `PlayerAction` structured output. Enemies generate
   tactical declarations via `enemy_combat.py`. NPCs generate from their
   limited action set.

2. **ADJUDICATION** -- The DM resolves each declared action one at a time. For
   PC actions, the DM generates `ActionResolution` structured output containing
   narration, roll results, mechanical effects (damage, conditions, void
   changes, soulcredit changes), and targeting resolution. For enemy actions,
   the legacy combat pipeline in `mechanics.py` computes outcomes
   deterministically. For NPC actions, the DM narrates with no mechanical
   effect (this is the bug that Spec 01 fixes).

3. **SYNTHESIS** -- The DM generates a `RoundSynthesis` structured output
   summarizing the round: narrative wrap-up, clock updates, entity lifecycle
   changes (spawns, removals, conversions), environmental state changes, and
   story advancement decisions.

4. **CLEANUP** -- The session engine applies state changes, logs events, runs
   health/status checks, processes entity lifecycle transitions, and prepares
   the next round.

### Key Systems

| System | Description | Files |
|--------|-------------|-------|
| **Tactical Module** | Enemy AI subsystem. When enabled, enemies act as autonomous agents with their own decision-making (weapon selection, target priority, movement). Disabled = DM controls enemies narratively. | `enemy_combat.py`, `session.py` |
| **Free Targeting** | Generic target IDs (`tgt_xxxx`) assigned to all combatants. Players and enemies target these IDs without knowing real names. The DM resolves which entity each ID maps to during adjudication. Designed to test IFF/ROE capabilities. | `session.py`, `dm.py` |
| **Void** | Corruption mechanic. Characters accumulate void score (0-10) from environmental exposure, moral transgressions, and supernatural effects. High void triggers bond dormancy (7+) and permanent void-lock (10). Separate environmental void_level tracks location corruption. | `mechanics.py`, `schemas/shared_types.py` |
| **Soulcredit** | Moral tracking system. The DM awards +1 for ethical behavior (non-lethal takedowns, healing, restraint) and penalizes -1 or -2 for transgressions (civilian harm, prisoner abuse, authority abuse). Assessed per-action in ActionResolution. | `schemas/action_resolution.py`, `dm.py` |
| **Scene Clocks** | Bidirectional progress trackers (e.g., "Ambush Chaos 3/6", "Civilian Exposure 2/4"). The DM advances or reverses clocks in RoundSynthesis. When a clock fills, it triggers narrative consequences. | `mechanics.py`, `schemas/story_events.py` |
| **Structured Output** | Pydantic-validated JSON generated by the DM LLM for every resolution and synthesis. Separates freeform narration from typed mechanical fields. The engine trusts schema-validated output and applies it deterministically. | `schemas/action_resolution.py`, `schemas/player_action.py`, `schemas/story_events.py` |
| **JSONL Logger** | Writes one event per line to session output files. 19 event types covering declarations, resolutions, combat actions, entity lifecycle, clocks, and metadata. Used downstream for ML training and datamining analysis. | `jsonl_logger.py`, `LOGGING_IMPLEMENTATION.md` |

---

## Spec File Links

| File | Status |
|------|--------|
| [01_NPC_COMBAT.md](./01_NPC_COMBAT.md) | Not started |
| [02_ENEMY_LIFECYCLE.md](./02_ENEMY_LIFECYCLE.md) | Not started |
| [03_TARGET_VALIDATION.md](./03_TARGET_VALIDATION.md) | Not started |
| [04_DEFENSE_TOKENS.md](./04_DEFENSE_TOKENS.md) | Not started |
| [05_STEALTH.md](./05_STEALTH.md) | Not started |
| [06_IFF_ROE.md](./06_IFF_ROE.md) | Not started |
| [07_INVENTORY.md](./07_INVENTORY.md) | Not started |
| [08_SUPPRESSION.md](./08_SUPPRESSION.md) | Not started |
| [09_RANGE_MOVEMENT.md](./09_RANGE_MOVEMENT.md) | Not started |
| [10_ENV_OBJECTS.md](./10_ENV_OBJECTS.md) | Not started |
| [11_EXPERIMENT_INFRA.md](./11_EXPERIMENT_INFRA.md) | Not started |
| [12_DISPLAY.md](./12_DISPLAY.md) | Not started |
| [13_BONDS_VENDORS.md](./13_BONDS_VENDORS.md) | Not started |
| [14_CONDITIONS_MODIFIERS.md](./14_CONDITIONS_MODIFIERS.md) | Not started |
| [15_RESOLUTION_PHASE_SKIP.md](./15_RESOLUTION_PHASE_SKIP.md) | Not started |
| [16_ADJUDICATION_CONTEXT.md](./16_ADJUDICATION_CONTEXT.md) | Not started |
| [17_CLOCK_PERSISTENCE.md](./17_CLOCK_PERSISTENCE.md) | Not started |

---

## Baseline Data Reference

- **Experiment design and raw data:** `.claude/baseline_datamining/`
- **Human-curated issue list:** `.claude/human_curated_todo/2026--02-14.md`
- **Session JSONL files:** `multiagent_output/lethality_experiment_combat_ambush/control/models/`
- **Treatment v1 configs:** `scripts/session_configs/experiment/lethality_test_combat_ambush/treatment_v1/`
- **Suppression resolution prompt (treatment):** `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_suppression.yaml`
