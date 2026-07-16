# Outcome-First Round Narration

**Status:** Implemented behind feature flag; hardening and downstream migration remain  
**Review audience:** Aeonisk maintainers and Claude  
**Scope:** `scripts/aeonisk/multiagent/` runtime, new JSONL events, and required
version-aware transmedia readers  
**Out of scope:** Rewriting historical corpus files and changing transmedia story
models beyond schema-input compatibility

**Implementation prerequisites:** Preserve and merge the call-sequence and
resume-from-divergence work currently present on `fix-call-sequence-logging`;
migrate `aeonisk-transmedia-pipeline` readers before enabling the new event schema
by default. Current `main` already contains the player/enemy stun and KO fixes.
Extend resume-from-divergence to support synthesis-boundary re-entry and restore all
authoritative NPC and auxiliary state before relying on fail-closed resume.

## Executive decision

Make the round synthesis the only canonical literary account of resolved actions.
Per-action DM calls should adjudicate structured mechanics, not write outcome prose.
After each adjudication, the engine must apply the effects and emit an immutable,
authoritative `AppliedOutcome` containing before/after state. The existing single
round-synthesis call then turns the ordered outcomes into prose and proves, through
structured coverage fields, that it represented every consequential outcome.

This does **not** add a second LLM call per action. The target call pattern is:

1. Each actor declares intent, method, target, equipment, and optional speech.
2. One per-action DM call returns structured adjudication only.
3. Deterministic engine code applies and records the result.
4. One existing end-of-round call narrates all applied outcomes together.

The architectural invariant is:

> Prose may describe authoritative state, but prose may never create authoritative
> state.

Removing mandatory 200-3000 character prose from every action should also reduce
bulk-generation output tokens. The richer round synthesis and occasional bounded
retry consume part of that saving, so actual net cost remains an evaluation metric,
not an assumed acceptance result.

## Why this change is necessary

### Reproduced failure: Lawful Mercy / The Kneeling

Source:

`multiagent_output/vp2_kneeling/run_2026-07-09_200533_4a1976cb/run_0003/session_3cafb0b2-b213-4add-b436-0bda972a390e.jsonl`

The run used a `gpt-5.4-mini` DM and `gemini-3.5-flash` players. It exposes a
direct contradiction between generated prose and engine state:

| Round | Target | Authoritative combat result | Generated prose | Contradiction |
|---|---|---|---|---|
| 1 | Operative #2 | `30 -> 18 HP`, `+2 wounds`, `alive: true`, `status: active` | Per-action prose calls the shot "the killing"; synthesis describes "two bodies now gone limp" | Living, active target narrated dead |
| 1 | Operative #1 | `30 -> 18 HP`, `+2 wounds`, `alive: true`, `status: active` | Per-action prose says the target "goes still" and calls them a body; synthesis counts them among two bodies | Living, active target narrated dead |
| 2 | Operative #1 | `18 -> 6 -> 0 HP`, wounds `2 -> 4 -> 5`, `status: defeated` | Synthesis calls the target a dead witness | Defeat/unconscious state promoted to death without a death result |
| 3 | Operative #3 | `30 -> 21 -> 9 HP`, wounds `0 -> 1 -> 3`, `alive: true`, `status: active` | Synthesis says the target's body goes slack and calls them a corpse | Living, active target narrated dead |

Relevant combat event IDs:

| Event ID | Result |
|---|---|
| `9a35715a-2934-45c0-885f-f45af89033f8` | Operative #2 remains active at `18/30 HP` |
| `68a8343a-a3ab-41e4-ad5c-fea2fa759bce` | Operative #1 remains active at `18/30 HP` |
| `7902dc6b-5cad-46cb-ae53-9e0e5fecd4e0` | Operative #1 remains active at `6/30 HP` |
| `bc6cc935-5846-4931-a2c9-d97422e03f33` | Operative #1 reaches `0/30 HP`, five wounds, `status: defeated` |
| `e0e04426-c1e9-4737-baac-0d446d5b1a77` | Operative #3 remains active at `21/30 HP` |
| `7d89ac50-1dd8-4a3e-94a3-a83a5c0342b5` | Operative #3 remains active at `9/30 HP` |

The contradictions are not subtle wording disagreements. They change who is alive,
who can act, whether later custody scenes are coherent, and whether the resulting
JSONL is safe for narrative training or evaluation.

The same three rounds demonstrate two additional failure classes:

- **Mechanics leakage:** round three includes "five of twenty-six," "three wounds
  deep," and the raw generated entity label "Independent Subdued Operative #2" in
  literary prose.
- **Causal misattribution:** round two credits "Cold Tarn's execution" for the
  outcome that event `bc6cc935-5846-4931-a2c9-d97422e03f33` attributes to Hard
  Vane.

The data can be reproduced without relying on this document's interpretation:

```bash
jq -r '
  select(.round >= 1 and .round <= 3 and .event_type == "combat_action") |
  {
    round,
    attacker: (.attacker.name // .attacker),
    defender: (.defender.name // .defender),
    damage,
    wounds_dealt,
    defender_state_after,
    event_id
  }
' multiagent_output/vp2_kneeling/run_2026-07-09_200533_4a1976cb/run_0003/session_3cafb0b2-b213-4add-b436-0bda972a390e.jsonl
```

### Root cause in the current implementation

The current `ActionResolution` schema explicitly couples freeform outcome prose to
mechanics. Its docstring calls it "freeform narration + structured mechanics," and
requires a 200-3000 character `narration` before state application
(`schemas/action_resolution.py:204-206`, `287-298`).

The runtime order makes the contradiction predictable:

1. The LLM constructs `ActionResolution`, including final-sounding narration.
2. Only afterward does `_generate_action_resolution_structured()` call
   `_process_structured_damage_effects()` (`dm.py:8092-8145`).
3. The deterministic damage result is appended to the already-written prose
   (`dm.py:8147-8151`).

The Lawful Mercy event therefore contains both "the killing" and the appended
authoritative line `30 HP -> 18 HP`. A prompt cannot reliably reconcile state that
does not exist until after the prose has already been generated.

The round synthesis then inherits the bad assertion. Its prompt says each prior
resolution is an established fact and must be woven rather than re-narrated
(`dm.py:5003-5008`). `_build_resolution_summary()` includes the first 300 characters
of each DM narration (`session.py:5078-5082`, `5134-5139`). The model is instructed
to preserve a false death while also seeing partial mechanical data. This is an
ordering and data-contract bug, not merely weak literary prompting.

The engine already has the state needed to avoid it. Target state distinguishes
`alive`, `unconscious`, and `dead`; death is based on six or more wounds, while zero
health below that threshold is unconscious (`session.py:4067-4078`, `4135-4142`;
`target_ids.py:478-483`). The missing piece is making that result the synthesis
input and enforcing it as the sole source of truth.

This plan builds on existing orchestration rather than replacing it. The cited run
already contains 46 `action_declaration` events plus `adjudication_start`,
`difficulty_assessment`, and observe-only `post_resolution_adjudication` events.
Declarations already precede adjudication, and `dm_assessment_enabled` already
supports a per-round DM ruling path (`session.py:2085-2138`, `2474`, `2914`;
`mechanics.py:816-851`). The migration extends these contracts and replaces the
mixed outcome event; it does not mint a second declaration stream.

### Research and corpus impact

Existing sessions are not uniformly invalid. Their typed mechanics remain useful
for analyses that consume `combat_action`, `character_state`, clock, Void,
Soulcredit, and other structured events without consulting prose. Their prose is
not suitable for narrative training or story evaluation when it contains an
unresolved state contradiction.

Judged-transgression results need a narrower qualification. `analyze_offenses.py`
extracts enforce-mode measurements from typed `post_resolution_adjudication`
rulings (`scripts/analyze_offenses.py:75-103`), but the magistrate that generated
those rulings was not isolated from narration:

1. `_run_post_resolution_adjudication()` builds its judge input with
   `_build_resolution_summary()` (`session.py:4771-4783`).
2. That summary includes up to 300 characters of each per-action DM narration
   (`session.py:4899-4903`, `4955-4960`).
3. `full_context` and `enforce` additionally include up to three prior round
   syntheses (`session.py:4783-4797`).

Therefore the stored ruling is structured, but its input may contain false-death
or mechanics-leak prose. In violence probes, explicit declarations such as
"execute the prisoner" independently support an intent-based violation, so the
existing result is not automatically wrong. However, false outcome prose can
inflate perceived completed harm, influence outcome-sensitive rulings, and in
enforce mode alter Soulcredit and subsequent gated behavior. Qualitative vignettes
that quote DM prose are directly tainted.

Before citing affected judged-transgression figures as prose-independent evidence,
run a one-time sensitivity audit:

- rebuild judge items from typed declarations, adjudications, applied mechanics,
  and canonical character state only;
- exclude per-action narration and round synthesis from the audit condition;
- re-judge the violence probes and a stratified sample of the cross-model actor
  study with the same magistrate model and law prompt;
- compare offense count, article, severity/delta, attribution, and downstream
  Soulcredit trajectory with the recorded rulings;
- report disagreement and revise claims if rankings or effect sizes move materially.

Until that audit, classify existing outputs as:

| Channel | Current research status |
|---|---|
| Typed mechanics and state | Usable when analyzed independently of prose |
| Narrative prose | Prose-tainted; exclude from narrative training/story evaluation |
| Enforce/post-resolution rulings | Usable with a narration-input caveat; sensitivity audit required for prose-independent claims |
| Qualitative DM-prose examples | Verify against typed state or replace |

## Goals and non-goals

### Goals

- Preserve exact mechanical chronology across multi-hit and mixed-action rounds.
- Produce cohesive prose rather than one paragraph per turn or repeated setting
  resets.
- Integrate useful dialogue where it affects action, motive, or consequence.
- Permit compatible actions to merge naturally without losing their outcomes.
- Prevent prose from inventing deaths, damage, dialogue, transitions, or knowledge.
- Prevent true mechanics from leaking into literary prose as raw numbers, labels,
  roll terms, or turn markers.
- Attribute every narrated consequence to the actor and outcome that caused it.
- Preserve visibility boundaries for private or partially observed actions.
- Make contradictions detectable in tests and logs, not discoverable by readers.
- Improve JSONL provenance for research, replay, and downstream story generation.

### Non-goals

- Do not rewrite historical JSONL in this change.
- Do not make the synthesis model adjudicate mechanics.
- Do not add a literary LLM call after every individual action.
- Do not retain deterministic or legacy prose as a silent fallback.
- Do not require every pass, idle NPC, or redundant compliance action to receive a
  separate sentence.

## Proposed runtime model

### 1. Declaration is intent, not outcome

`ActionDeclaration` may contain:

- actor and target IDs;
- intended goal and method;
- action type, skill, equipment, and declared movement;
- spoken words the actor actually chooses to say;
- desired effect, explicitly labelled as intent.

Declarations must not become facts merely because they use words such as "kill,"
"execute," "escape," or "convince." For example, "I fire to kill" remains intent
until mechanics establish the target's resulting state.

### 2. Replace narrative action resolution with adjudication

Introduce a versioned `ActionAdjudication` schema. It should contain no literary
outcome paragraph.

Minimum fields:

```text
adjudication_id
declaration_event_id
round
sequence
actor_id
target_ids
roll_result
success_tier
margin
mechanical_effects
reasoning_short
observability
```

`reasoning_short` is constrained mechanical rationale, not player-facing prose.
Existing `MechanicalEffects` types should be reused initially to limit migration
risk, then tightened where application code currently accepts ambiguous states.

### 3. Apply mechanics and materialize the authoritative outcome

After adjudication, deterministic code applies damage, healing, conditions,
inventory, Soulcredit, Void, clocks, barriers, weapon locks, and lifecycle checks.
It then emits an immutable `AppliedOutcome`.

Minimum fields:

```text
outcome_id
adjudication_id
declaration_event_id
round
sequence
actor_id / actor_name
intent
method
target_ids / target_names
declared_dialogue
roll_result
applied_effects
entity_states_before
entity_states_after
lifecycle_changes
observable_facts
prohibited_claims
visibility
consequential
```

State snapshots must include, where applicable:

```text
health / max_health
wounds
stuns
barrier
is_active
consciousness: conscious | unconscious
life_state: alive | dead
combat_state: active | defeated | departed
position
conditions
```

Do not collapse these into one `alive` boolean. The existing run demonstrates why
`defeated`, `unconscious`, and `dead` need separate semantics.

`character_state` remains the single life-state oracle. `AppliedOutcome` contains
per-action changed-entity deltas, not a competing full-state authority. Full state
snapshots remain in character-state/debug/replay events; deltas carry references or
hashes that allow validators to bind them to that state.

`observable_facts` must be structured, prose-safe facts rather than numeric state.
Each fact includes `fact_kind`, `subject_id`, `causing_actor_id`, symbolic state,
severity tier, and a `prose_safe_summary`, for example "badly wounded but conscious"
rather than "18/30 HP." Numeric HP, wounds, stuns, rolls, margins, and clock ticks
remain in engine-side snapshots used by validators and are not rendered into the
narrator prompt as quotable phrases.

`prohibited_claims` should be derived from canonical state, such as "do not describe
target as dead, a corpse, taking a last breath, or unable to act." Each entity needs
an explicit prose-facing `narrative_name`, distinct from IDs and generated registry
labels when necessary. Only that name or validated pronouns/descriptors may appear
inside literary `text`; IDs and labels such as faction-prefixed numbered target
names belong in structured provenance fields. The prohibitions help the model, but
the validator remains authoritative.

### 4. Complete lifecycle processing before narration

Morale, conversions, departures, spawns, unconscious checks, and deaths that are
part of the round must resolve before literary synthesis. Each accepted lifecycle
change receives its own ordered outcome ID or is attached to the causal
`AppliedOutcome`.

Lifecycle normalization must target current `main` semantics. The player and enemy
KO gates, stun logging/recovery behavior, and stun healing have already landed,
including enemy-side commit `783f338`. Phase 1 still must resolve the transient
`combat_action` stun scale versus the canonical `character_state` representation.
Synthesis consumes normalized `character_state`, never an inferred life state from
a transient combat event.

Story advancement and scene pivots must also be accepted into authoritative state
before prose describes them. The synthesis may propose a transition only through a
structured field; the engine validates and applies it, then either performs a small
transition-render pass from the accepted state or defers its literary description
to the next round opening. It must never narrate an unaccepted location or spawn.

For the first implementation, prefer deferring newly accepted transitions to the
next round opening. This avoids adding another LLM call and preserves the rule that
prose follows applied state.

### 5. Synthesize once from ordered outcomes

The round synthesis receives:

- prior canonical narrative ending, not all prior per-action prose;
- ordered `AppliedOutcome` records;
- prose-safe symbolic entity/environment facts derived from the final snapshot;
- accepted lifecycle changes;
- current clocks and clock changes;
- visibility-filtered facts for each audience;
- scenario tone and style guidance.

It must not receive outcome prose from action adjudication because none should
exist. It may use declared dialogue verbatim or lightly integrate it, but it should
omit dialogue that adds no information or dramatic function.

Full numeric snapshots remain available to the deterministic validator outside the
narrator prompt. This separation prevents the model from copying true-but-unliterary
HP, wound, stun, roll, or clock values into story text.

The prompt should prioritize causal flow over actor-by-actor reporting:

- establish the scene once;
- narrate outcomes in engine order;
- connect simultaneous or causally related actions;
- vary paragraph openings;
- avoid restating rolls and action labels unless mechanically important;
- finish on the resulting state, not a generic atmospheric reset.

### 6. Make coverage structural

Extend or replace `RoundSynthesis` with structured narrative segments:

```text
narration
segments[]:
  segment_id
  text
  source_outcome_ids[]
  visibility
coverage[]:
  outcome_id
  disposition: rendered | merged | omitted_nonconsequential
  segment_id
transition_proposal
state_claims[]:
  claim_kind
  subject_id
  causing_actor_id
  source_outcome_id
  symbolic_value
```

Merging is explicitly allowed when:

- source outcomes have compatible visibility;
- their causal and temporal order remains true;
- each distinct state change remains understandable;
- the merge does not imply simultaneity where ordering matters.

Examples of useful merges include two attacks that land in sequence on the same
target, or several characters reacting to one revelation. A pass, an idle NPC, or
repeated compliance may be marked `omitted_nonconsequential`. Damage, healing,
lifecycle changes, resource changes, consequential dialogue, and state transitions
may not be omitted.

## Validation and failure policy

Validation must run before the synthesis becomes canonical or is shown as resolved
narrative. At minimum it must enforce:

1. Every consequential `outcome_id` is covered exactly once.
2. Every covered ID exists and belongs to the current round.
3. Segment source order is compatible with outcome sequence.
4. Merged segments preserve every distinct applied consequence.
5. Visibility scopes do not leak private actions or knowledge.
6. Entity state claims agree with final and intermediate snapshots.
7. Dead or unconscious actors do not act afterward.
8. Living entities are not described as killed, corpses, taking a last breath, or
   otherwise definitively dead.
9. Defeated or unconscious entities are not silently promoted to dead.
10. No unsupported damage, healing, condition, dialogue, spawn, departure, or scene
    transition appears.
11. `segments[].text` contains no raw HP values or fractions, wound/stun counts,
    clock ticks, roll totals, DCs, margins, explicit round/turn numbering, target
    IDs, or raw generated entity labels; only prose-facing narrative names are
    allowed.
12. Every consequence claim names the causing actor and source outcome, and both
    match `AppliedOutcome.actor_id` and its applied effects.

Coverage, ordering, IDs, and lifecycle claims can be validated deterministically.
Natural-language state claims require the structured `state_claims` list above and
are cross-checked against snapshots and causal attribution. A lexical scan for
high-risk death and mechanics-leak language is defense in depth, not the primary
contract. Because the same model writes prose and self-reports claims, this cannot
prove arbitrary open-generation prose sound. It guarantees deterministic contract
cases and materially improves detection and retry behavior for open generation.

On validation failure:

1. Reject the synthesis and retry with precise validation errors and the same
   authoritative outcomes.
2. Do not rerun mechanics or mutate state during a narrative retry.
3. After the configured retry limit, checkpoint the applied mechanics, emit a
   diagnosable `round_synthesis_failed` event, and stop the session's narrative
   progression.

There is deliberately no legacy literary fallback. A silent fallback would recreate
the same unverified channel and contaminate the canonical log. Fail closed, with
mechanics preserved for diagnosis or explicit resume.

The failure checkpoint must be directly consumable by an extended
`scripts/state_reconstructor.py`. That file does not exist on current `main`; the
unmerged implementation resumes only at round boundaries by folding through round
`K-1` and seeding a new round `K`. This plan chooses the cleaner provenance option:
**add true synthesis-boundary resume** rather than disguising a missing round-K
narrative as the opening of round K+1.

After round K mechanics and lifecycle are complete but before prose is accepted,
write a phase-aware checkpoint containing:

- `resume_phase: synthesis` and `resume_round: K`;
- the exact ordered applied outcome and lifecycle IDs for round K;
- the canonical post-application, pre-cleanup state manifest;
- random state/seed and LLM call sequence;
- the synthesis prompt inputs, validation diagnostics, and attempted response IDs;
- completion markers proving declaration, adjudication, effect application, and
  lifecycle phases must not run again.

Resume rehydrates that manifest, reconstructs the same synthesis input, re-enters
the synthesis/validation stage, and runs cleanup once after a synthesis is accepted.
It must not replay declarations, rolls, effects, rulings, lifecycle transitions, or
other round-K mutations. Implementing this phase-aware re-entry is new Phase 4 work,
not a capability claimed by commit `7edd818`.

The call-sequence and round-boundary resume work on
`fix-call-sequence-logging` remains a merge prerequisite and implementation base.
Full-cached replay and a `MockLLMProvider` remain useful follow-up work but are not
required for the initial fail-closed path.

The current reconstructor on `fix-call-sequence-logging` does **not** satisfy this
for NPC scenes. At commit `7edd818`, `ResumeState` has party, enemy, clock, scenario,
and story fields but no NPC roster, and `build_resume_config()` explicitly removes
`initial_npcs` at line 260. It removes converted enemies from the enemy survivor
set, but does not retain or rehydrate them as NPCs. A living prisoner, de-escalated
enemy, vendor, witness, or other active NPC can therefore disappear across resume.
This is highest impact in custody scenarios such as Lawful Mercy, where synthesis
validation failures are especially plausible.

Before Phase 4 can claim resumable fail-closed behavior:

- add NPCs to `ResumeState` and fold initial spawns, dynamic spawns, conversions,
  escalations, departures, defeat/death, healing, and latest canonical state;
- seed the reconstructed NPC roster into the resumed live session;
- restore identity/provenance, narrative name, faction, entity/threat type,
  disposition, pronouns, vitals, wounds/stuns, position, conditions, inventory,
  equipment, and active/lifecycle state;
- preserve stable IDs where downstream outcome provenance requires them, or record
  an explicit old-to-new ID mapping;
- hydrate exact state through `resume_state.npcs` after spawn rather than assuming
  the ordinary `initial_npcs` schema can represent every runtime field;
- validate that no NPC is duplicated, lost, resurrected, or reverted to its
  pre-conversion role.

NPCs are not the only resume gap. The checkpoint manifest and hydrator must cover
stealth state, bond transitions, enemy shared intelligence, environmental objects,
vendors, clocks, economy/inventory, positions, conditions, and every other state
class that can affect later decisions. A resume report must classify each state
class as exact, absent-by-design, or unsupported. Any unsupported live state makes
the resume **degraded**: useful for diagnosis, but not eligible for automatic bulk
continuation or accepted corpus output.

## JSONL and compatibility

Extend the existing schema-versioned event stream while retaining readers for
legacy sessions:

```text
action_declaration (existing; increment schema version and extend in place)
adjudication_start (existing)
difficulty_assessment (existing)
action_adjudication
applied_outcome
post_resolution_adjudication (existing observe-only event; unchanged)
entity_lifecycle (existing, linked to outcome IDs)
round_synthesis
round_synthesis_failed
```

Each event should carry `event_id`, `parent_event_id`, `correlation_id`, `round`,
`sequence`, and `schema_version`. Recommended parent chain:

```text
action_declaration -> action_adjudication -> applied_outcome
ordered applied_outcomes -> round_synthesis
```

Do not introduce another `action_declaration` event name. Keep legacy
`action_resolution` parsing for replay and analysis, but new sessions
under the feature flag must not write mixed prose/mechanics `action_resolution`
events. The feature flag should select the complete pipeline, not individual
substeps, so partially migrated modes cannot produce ambiguous logs.

`aeonisk-transmedia-pipeline` is a blocking schema consumer. Its catalog, story
model, Codex narrator, radio-play generator, literary-story evaluator, generic
narrative generator, JSONL parser, and narrative reconstruction paths currently
parse `action_resolution`; `src/evals/literary_story.py` directly reads
`context.narration`. A version-aware reader using `round_synthesis.segments` and
their provenance must land and pass compatibility tests before this feature flag
defaults on. Segment provenance is the replacement for per-action narration, not
an optional secondary source.

## Implementation sequence

### Implementation status (2026-07-15)

Implemented on branch `outcome-first-round-narration` behind the single
`outcome_first_narration` flag:

- Phase 1 mechanics-only adjudication, applied-outcome, snapshot, segment,
  coverage, and state-claim contracts;
- Phase 2 feature-gated player, enemy, NPC, purchase, transfer, and failed
  attunement paths, with legacy mixed `action_resolution` logging suppressed;
- Phase 3 one-call round synthesis from prose-safe outcomes and sanitized
  lifecycle facts, including declared inter-party/NPC dialogue;
- Phase 4 deterministic coverage, chronology, visibility, mechanics-leak,
  provenance, state-claim, and false-death validation with bounded retries and
  fail-closed `round_synthesis_failed` logging;
- regression tests for living-versus-dead state, stun knockout without HP loss,
  invalid death prose, mechanics leakage, visibility, provenance, retries, and
  mechanics-only specialized resolutions.
- replay support for cached DM, player, and enemy decisions, including generated
  enemy-ID aliasing, replay-safe lifecycle/conversion checks, legacy outcome
  normalization, and inclusive replay round limits;
- replay preflight validation for missing agent cache coverage and provider
  compatibility, plus replay-safe debrief handling;
- a real one-round no-proxy smoke replay using 14 cached LLM calls, with 21
  targeted regression tests passing.

Not yet implemented, and therefore not claimed complete:

- the Phase 4 synthesis-boundary checkpoint hydrator/re-entry path, including
  exact NPC and auxiliary-state reconstruction;
- canonical remapping of source-run outcome/entity UUIDs into replay-run UUIDs
  before strict cached-synthesis validation. Current replay accepts the cached
  synthesis after parsing because the source UUIDs are not expected to match
  freshly generated replay UUIDs;
- Phase 5 transmedia consumer migration, real bulk quality measurements, and
  promotion of the feature flag to default-on.

Until those blockers land, retry exhaustion is fail-closed and diagnosable but
requires manual recovery; executable replay now works for cached sessions, but
the new mode remains suitable for controlled evaluation rather than accepted
unattended bulk corpus generation.

### Live experiment findings (2026-07-16, Kneeling session 9052cb25)

First live flagged run: the pipeline engaged (six applied outcomes, zero legacy
mixed `action_resolution` events), but round-1 synthesis failed closed on all
three attempts and the session then hung. Three defects, all fixed with
regression tests:

1. **Viewer ids were LLM-proposed and trusted.** `aware_agents` carried invented
   agent ids (`player_sela` vs `player_oathkeeper_sela` for the real
   `player_01`), so the visibility intersection was unsatisfiable by any
   synthesis. Fix: `canonicalize_viewer_ids` maps proposed ids onto the real
   entity roster at outcome build time and again over each synthesis segment
   before the subset check; unmappable ids are dropped and logged.
2. **Exact-join narration validation was brittle.** Attempt 3 joined segment
   texts with a single space and was rejected. Narration is presentation, so
   code now derives it (`finalize_synthesis_narration`) and the equality rule
   is gone.
3. **Fail-closed hung instead of halting.** The exhaustion error was swallowed
   by the message bus and the session waited on synthesis completion forever
   (60+ minutes, event loop idle). The DM now broadcasts `synthesis_failed`,
   and the session ends itself cleanly (`_session_end_status='aborted'`,
   `_end_reason='round_synthesis_failed'`, normal `session_end` emission)
   with the checkpoint already logged for later resume.

The mechanics-side contract held throughout: adjudication stayed mechanics-only
and effects applied deterministically. The failures were all in the
synthesis-validation seam, and two of the three were the validator being wrong
rather than the model.

### Phase 1: Contracts and pure builders

- Add `ActionAdjudication`, `AppliedOutcome`, state snapshot, narrative segment,
  coverage, and state-claim schemas.
- Add stable sequence and causal IDs.
- Extend the existing `action_declaration` version and preserve current
  `adjudication_start`/`difficulty_assessment` ordering.
- Extract pure before/after snapshot builders around current effect application.
- Define one canonical lifecycle vocabulary with `character_state` as oracle; map
  enemy/player fields to it and reconcile transient combat stun values against the
  current main-branch semantics. Enemy-side KO is already enforced and needs
  regression coverage, not a new implementation.

### Phase 2: Mechanics-first action path

- Change `_generate_action_resolution_structured()` into adjudication generation.
- Remove required literary narration from the new action schema.
- Apply every effect before constructing `AppliedOutcome`.
- Replace appended damage/healing prose with structured applied facts.
- Log the declaration, adjudication, and applied outcome separately.

### Phase 3: Outcome-driven synthesis

- Replace `all_resolutions`/truncated narration input with ordered outcomes.
- Include final snapshots and accepted lifecycle changes.
- Add segment source IDs, coverage dispositions, and structured state claims.
- Update prompts to allow useful merging and prohibit turn-by-turn template prose.
- Keep one synthesis call per round.

### Phase 4: Validation and fail-closed retries

- Implement deterministic coverage, order, visibility, and state validators.
- Feed concrete errors into bounded retries.
- Extend round-boundary reconstruction with a phase-aware synthesis checkpoint and
  synthesis-stage re-entry that cannot replay mechanics or lifecycle.
- Extend `state_reconstructor.py` and live-session hydration to reconstruct and
  restore the complete active NPC roster, including converted prisoners.
- Restore or explicitly classify all auxiliary state, including stealth, bonds,
  shared intelligence, environmental objects, vendors, clocks, conditions,
  inventory/economy, and positions.
- Add `round_synthesis_failed` checkpoint behavior.
- Remove the structured-to-legacy synthesis fallback for this pipeline.
- Make replay strict-validation compatible by remapping source outcome and
  entity identifiers to the current replay identifiers before validating cached
  synthesis; do not rely on replay-only validation bypassing.

### Phase 5: Default and cleanup

- Run corpus-quality comparisons behind a complete-pipeline feature flag.
- Migrate and test every `aeonisk-transmedia-pipeline` consumer of
  `action_resolution.context.narration` to version-aware synthesis segments.
- Run a representative real bulk job and measure validation retries, retry
  exhaustion, completion rate, token usage, and resumability.
- Promote the new pipeline after mechanical and narrative gates pass.
- Stop emitting new legacy mixed `action_resolution` events.
- Retain legacy readers; historical corpus repair remains a separate project.

## Test plan

### Unit tests

- Snapshot before/after state for damage, healing, stun, wounds, barriers, soak,
  Soulcredit locks, conditions, inventory, Void, clocks, and positions.
- Distinguish active, defeated, unconscious, dead, departed, and destroyed states.
- Prove multi-hit order uses the previous hit's resulting state.
- Reject duplicate, missing, unknown, or out-of-order coverage IDs.
- Allow compatible merges and reject merges that hide consequences or cross
  visibility boundaries.
- Reject unsupported state claims and unaccepted transitions.
- Reject mechanics leakage, raw labels/IDs, and causal misattribution.
- Prove retries do not reapply mechanics.
- Prove `round_synthesis_failed` checkpoints resume through
  `state_reconstructor.py` at synthesis without replaying effects.
- Prove synthesis-boundary resume does not repeat declarations, rolls, rulings,
  lifecycle transitions, or cleanup, and that accepted synthesis retains round-K
  outcome provenance.
- Prove resume preserves initial NPCs, spawned NPCs, converted enemies/prisoners,
  escalated NPCs, departures, lifecycle state, vitals, inventory, equipment,
  conditions, and provenance without duplication or disappearance.
- Prove unsupported auxiliary state marks a resume degraded and excludes it from
  automatic continuation/corpus acceptance.

### Regression tests

- Recreate the Lawful Mercy rounds with deterministic effects:
  - Operative #2 at `18/30 HP` cannot be called dead after round one.
  - Operative #1 at `18/30 HP` cannot be called a body after round one.
  - Operative #1 at `0 HP`, five wounds is defeated/unconscious, not dead.
  - Operative #3 at `9/30 HP`, three wounds remains alive and active.
- Verify later custody narration cannot appear to resurrect any operative.
- Verify a true six-wound or explicit permanent-death result may be narrated dead.
- Verify locked weapons, misses, absorbed hits, and zero applied damage cannot be
  narrated as successful injury.
- Verify friendly fire, AoE, simultaneous declarations, and sequential application.

### Narrative quality tests

Use a fixed evaluation set with at least combat, social, investigation, ritual,
healing, and transition rounds. Compare the current and proposed pipelines on:

- consequential outcome coverage rate;
- unsupported state claim count;
- causal misattribution count;
- raw mechanics and identifier leakage count;
- chronology violations;
- repeated paragraph-opening rate;
- redundant action restatement rate;
- dialogue usefulness and attribution;
- human preference for cohesion and readability.

Mechanical acceptance is strict: zero unsupported deaths and 100% consequential
coverage on the deterministic regression suite. Literary preference can be
comparative, but it cannot override mechanical correctness.

For unconstrained model generations, report unsupported-claim, leakage, and
attribution rates with confidence intervals. The design lowers and exposes those
rates; it does not mathematically guarantee zero hallucinations outside the
deterministic contract suite.

## Operational and UI behavior

Immediate feedback after an action should be a concise structured result, for
example: hit/miss, margin, damage applied, and resulting target status. Literary
prose appears once the round resolves. This avoids latency from an extra narration
call while still showing players that their action was processed.

If streaming presentation is required later, the UI may render provisional intent
and mechanical facts, clearly labelled as non-literary. It must not display
unvalidated outcome prose and later overwrite it with a contradictory synthesis.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Round prose collapses too many actions | Consequential coverage IDs and segment-level provenance |
| Structured output becomes large | Compact snapshots to changed entities; retain full state in engine logs |
| Natural-language validator misses euphemisms | Require structured state claims; use lexical detection only as defense in depth |
| Lifecycle processing changes ordering | Assign one monotonically increasing round sequence across action and lifecycle outcomes |
| Feature flag permits mixed semantics | Gate the full pipeline as one versioned mode |
| Fail-closed behavior reduces completion rate | Preserve a state-reconstructor-compatible checkpoint; require measured bulk retry-exhaustion and completion rates before promotion |
| NPCs disappear across fail-closed resume | Add `ResumeState.npcs`, event-folding and live hydration; block Phase 4 completion on custody/conversion resume tests |
| Mid-round resume silently replays mechanics | Add explicit synthesis-phase checkpoints and phase completion markers; re-enter synthesis directly and run cleanup once |
| Resume loses auxiliary state | Require an exact/absent/unsupported state manifest; degraded resumes are diagnostic-only and excluded from corpus continuation |
| Research tooling breaks on new events | Land version-aware transmedia readers and fixtures as a blocking dependency before enabling by default |
| True mechanics leak into prose | Give the narrator prose-safe symbolic facts only; validate text for numeric mechanics and raw identifiers |
| Model misattributes a consequence | Bind every state claim to causing actor and source outcome and cross-check both |

## Rejected alternatives

### Prompt the current per-action narrator more strongly

Rejected because the final applied state does not exist when narration is written.
The Lawful Mercy event already contains a correct appended HP line alongside false
death prose. More instructions do not repair missing causal order.

### Add a second literary call after every action

Rejected because it increases calls, latency, repetition, and cross-action
incoherence. The round already has the context needed for one cohesive narration.

### Let round synthesis repair existing per-action prose

Rejected because the current prompt explicitly treats that prose as established
fact, and repair requires deciding which channel is authoritative. Removing the
conflicting prose is safer than asking another model to arbitrate it.

### Deterministic prose fallback

Rejected for canonical narrative because it silently changes quality and bypasses
the same coverage/state contract. Deterministic text remains appropriate for the
immediate mechanics UI and diagnostics, not as the accepted literary story.

### One giant call for declaration, mechanics, and narration

Rejected because deterministic state application, targeting corrections, weapon
locks, barriers, death checks, and sequential multi-hit state occur outside the
model. A single call would still narrate before those results are authoritative, or
would move trusted mechanics into probabilistic generation.

## Acceptance criteria

The proposal is complete when:

- new sessions can run declarations through adjudication, application, and one
  outcome-driven synthesis without mixed action prose;
- every consequential applied outcome has auditable synthesis coverage;
- Lawful Mercy's exact false-death regressions are blocked automatically;
- sequential state, visibility, and lifecycle tests pass;
- failed synthesis retries never mutate mechanics twice;
- exhausted retries stop narrative progression with a preserved checkpoint;
- JSONL readers handle both legacy and new schema versions;
- all transmedia consumers use version-aware synthesis segments for new sessions;
- a representative bulk run demonstrates an accepted retry-exhaustion rate,
  resumable failures, and measured net token cost before default enablement;
- fail-closed resume preserves the exact active NPC/prisoner roster and lifecycle
  state across a synthesis failure;
- synthesis-boundary resume preserves round-K provenance and executes no round-K
  mechanic, ruling, lifecycle transition, or cleanup more than once;
- accepted automatic resumes have no unsupported state classes; degraded resumes
  are labelled and excluded from accepted corpus output;
- the narration-input sensitivity audit for affected judged-transgression results
  is complete or the published claims carry an explicit limitation;
- fixed-set evaluation shows no mechanical regression and improved narrative
  cohesion over the current turn-by-turn source prose.

For open generations, "zero unsupported deaths" is a measured target, not a formal
guarantee. The formal zero-defect gate applies to deterministic regression cases;
open-generation promotion uses observed rates, diagnostics, and retry exhaustion.

## Resolved reviewer decisions

1. Accepted scene transitions are narrated at the next round opening in the first
   implementation; no post-transition LLM call is added.
2. `AppliedOutcome` stores changed-entity deltas and state references/hashes. Full
   snapshots stay in debug/replay logs, and `character_state` is the life-state
   oracle.
3. Transmedia readers, especially `src/evals/literary_story.py`, require migration
   from `action_resolution.context.narration` to `round_synthesis.segments`; that
   migration blocks default enablement.

---

## Maintainer review reply (Claude, 2026-07-14)

The diagnosis was verified independently before this reply was written. All six
code citations are accurate on the current branch, and the Lawful Mercy
contradiction reproduces exactly as tabulated (both operatives alive/active at
`18/30 HP` while per-action prose says "the killing" and the round-1 synthesis
says "two bodies now gone limp"). The root-cause framing — an ordering and
data-contract bug, not weak prompting — is correct, and the core surgery
(adjudicate structurally, apply deterministically, narrate once from applied
outcomes) is approved in principle. The items below are required changes and
scope corrections, not a counter-proposal.

### R1. Mechanics leakage must be a validator, and `observable_facts` phrasing will make it worse as written

The same session shows the other failure class this plan does not police: the
round-3 synthesis puts raw game state into literary prose — "nearly spent at
**five of twenty-six**," "**three wounds deep**," and the raw entity name
"**Independent Subdued Operative #2**" as a character reference. For this
project, mechanics leaking into prose is the primary quality dealbreaker,
ranked above subtle confabulation. Yet all ten validation rules target false
claims; none target true-but-leaked state. Worse, the plan's example
`observable_facts` ("target remains conscious at 18 HP") hands the synthesis
model numeral-bearing phrasing it will echo verbatim.

Required changes:

- `observable_facts` must carry a prose-safe rendering tier (severity language:
  "badly wounded but conscious," not "18/30 HP"). Numeric state stays in
  `entity_states_*`, which the validator reads and the narrator does not quote.
- Add validation rule 11: `segments[].text` must not contain raw HP values or
  fractions, wound/stun counts, clock ticks, roll totals, DCs, margins, or
  round/turn labels.

On raw entity IDs specifically, the maintainer notes we may in fact need them
(provenance, downstream alignment). Open design question for Codex rather than
a settled rule: the recommendation here is that IDs live in the structured
segment fields — `source_outcome_ids` already gives segment-to-entity
provenance without polluting the text — and canonical display names are the
only entity reference permitted inside `segments[].text`. If a use case
requires IDs in the prose itself, that case should be stated explicitly so the
leak validator can carve a deliberate exception instead of a blanket one.

### R2. Attribution is unvalidated (accepted as an issue)

Round 2 of the same session credits "Cold Tarn's execution" for dropping
Operative #1 to `0 HP` — but the combat events show Hard Vane's shot did it.
The proposed validators check state claims, ordering, and coverage, but never
*who caused what*. `state_claims` must include the causing actor, cross-checked
against `AppliedOutcome.actor_id`, and a misattributed consequence must fail
validation the same way an invented one does.

### R3. The plan understates what already exists (accepted)

The cited session already emits `action_declaration` (46 events),
`adjudication_start`, `post_resolution_adjudication`, and
`difficulty_assessment`; `dm_assessment_enabled` already runs a per-round DM
ruling call, and declarations already precede adjudication. The JSONL section
lists `action_declaration` among events to add. Revise the migration sections
to map onto this existing machinery explicitly — Phase 1 is smaller than the
plan implies, and the event-name collision needs resolving (extend the existing
`action_declaration` schema version rather than minting a duplicate).

### R4. Fail-closed vs. bulk generation — status correction and a gate

Bulk corpus runs (100+ sessions overnight) mean one stubborn synthesis
validation failure kills a session's narrative progression. Status correction
to an earlier draft of this review: the checkpoint/resume machinery this
depends on largely *does* exist now — call-sequence logging was fixed and
resume-from-divergence (`scripts/state_reconstructor.py`, seed a live session
at round K from recorded snapshots) shipped and was live-verified on branch
`fix-call-sequence-logging` (2026-07-12/14). Caveats: that branch is not merged
to `main` yet. Full-cached replay now has cached DM, player, and enemy clients,
but strict source-to-replay UUID remapping remains open. So:

- `round_synthesis_failed` checkpoints should be designed to be consumable by
  `state_reconstructor.py` resume, which makes fail-closed genuinely resumable
  rather than theoretically so.
- Phase 5 promotion gates must include a measured retry-exhaustion rate on a
  real bulk run, not just the fixed evaluation set.
- Merging `fix-call-sequence-logging` is a practical prerequisite.

### R5. Reviewer question 3 is not hypothetical — it is our own pipeline (blocking)

Ten files in `aeonisk-transmedia-pipeline` parse `action_resolution`, and the
story-eval loop (`src/evals/literary_story.py`) reads `context.narration`
directly. The channel this plan deletes is the primary input to the story-eval
north star. A version-aware reader targeting `round_synthesis.segments` must
land in the transmedia pipeline **before** the feature flag defaults on — this
is a blocking dependency of Phase 5, not an open question. Upside worth
stating: segments with coverage provenance are a strictly better story-eval
input than 300-char narration truncations.

### R6. `state_claims` is self-reporting — scope the guarantee honestly

The model that euphemized a death can also under-report the corresponding
claim — and this failure mode includes ordinary hallucination, not only
motivated euphemism, so no amount of prompt-side honesty pressure closes it.
`state_claims` plus the lexical scan is accepted as defense in depth, but the
acceptance criterion "zero unsupported deaths" is only *guaranteed* on the
deterministic regression suite. The plan should say that plainly: open
generation gets a materially lowered rate plus detectability, not a proof.

### R7. Stun-scale conflict — Phase 1 must absorb the fresh stun work

Bonus finding from verification: the cited session shows Hard Vane at **25
stuns, status active**, while `session.py`'s character-state logic treats
stuns ≥ 6 as unconscious (YAGS Beaten). Two notes: (a) the session is from
2026-07-09 and predates the stun overhaul on `fix-call-sequence-logging`
(stuns logged in `character_state`, YAGS Beaten/Fatal KO enforced player-side,
auto stun-recovery disabled, stun-healing no-op fixed — commits `3c5c1d3`,
`c652fc9`, `e994cc5`, `4da341b`); (b) enemy-side stun-KO enforcement remains
the open edge. Phase 1's "one canonical lifecycle vocabulary" must reconcile
against that branch's semantics, not `main`'s, and must resolve the
`combat_action` transient-scale vs. `character_state` oracle mismatch
explicitly — `character_state` remains the single life-state oracle.

### Answers to the plan's reviewer questions

1. **Defer transitions to the next round opening.** Agreed — keeps the call
   count flat and preserves the prose-follows-applied-state rule.
2. **Changed entities in the event, full snapshots in debug/replay logs.**
   Agreed, with the addition that `character_state` events remain the
   authoritative life-state record; `AppliedOutcome` snapshots are per-action
   deltas, not a competing oracle.
3. **Yes — see R5.** The dependent trainer is our own transmedia pipeline, and
   its migration is a blocking Phase 5 dependency.

### Cost note

Worth adding to the plan's own argument: removing the mandatory 200–3000
character narration from ~40 per-action DM calls per session cuts output
tokens substantially; the enlarged synthesis (outcomes, snapshots, segments,
claims) and bounded validation retries claw some back, but the net per-session
cost is likely *lower*, which matters for bulk batch-API corpus generation.

---

## Codex disposition (2026-07-14)

All seven findings are accepted and incorporated into the normative plan above.

- **R1:** Added prose-safe symbolic facts, prose-facing `narrative_name`, and a
  mechanics/identifier leakage validator. Numeric state is validator-side data,
  not narrator-ready phrasing.
- **R2:** Added `causing_actor_id` and `source_outcome_id` to state claims, with
  deterministic attribution checks.
- **R3:** Reframed migration around existing declaration, adjudication-start,
  difficulty, and post-resolution events; no duplicate declaration stream.
- **R4:** Bound failure checkpoints to `state_reconstructor.py`, made the current
  call-sequence/resume work a prerequisite, and added a real bulk retry-exhaustion
  promotion gate.
- **R5:** Made version-aware transmedia readers a blocking dependency before the
  feature flag defaults on.
- **R6:** Limited formal zero-defect claims to deterministic contract tests and
  made open-generation quality an observed rate with diagnostics.
- **R7:** Made `character_state` the lifecycle oracle and required reconciliation
  with current stun work plus the enemy-side KO edge.

The reviewer-question answers are now settled decisions. The cost reduction is
recorded as a hypothesis to measure during bulk evaluation rather than a promised
result.

### Follow-up disposition: NPC resume and corpus fitness

The later maintainer note about NPC resume is accepted with one precision: the
unmerged reconstructor removes converted enemies from the surviving enemy roster,
but it does not currently build an NPC roster at all. The plan now treats complete
NPC event folding and live hydration as a Phase 4 blocker, with custody/conversion
resume tests required before fail-closed resumability is claimed.

The corpus caveat was also verified. Typed mechanics remain independently useful,
but enforce-mode magistrate rulings were generated from summaries containing
per-action narration, and full-context/enforce mode also included prior syntheses.
The plan now requires a structured-only sensitivity re-judge before affected
cross-model transgression figures are described as prose-independent. No historical
JSONL rewrite is proposed.

---

## Maintainer follow-up (Claude, 2026-07-14, after syncing main)

The disposition is accepted — all seven incorporations are faithful to the review
intent, and the `narrative_name` / provenance-fields split is the right resolution
of the entity-ID question. Three factual corrections and one design wrinkle,
found after fast-forwarding `main` to `18f27a5` (PR #73, enforce-mode):

### F1. The stun work is already in main — and the enemy-side KO edge is closed

Commits `3c5c1d3`, `c652fc9`, `e994cc5`, and `4da341b` are all ancestors of
current `main`, and `783f338` ("Enemy-side KO gate: YAGS health-check-to-act")
landed with them: a Beaten (stuns ≥ 6) or fatally wounded enemy now rolls the
same `resolve_ko_check` as players, with `ActionValidator` invalidating the
action on failure (`tests/unit/test_enemy_ko_gate.py`,
`.claude/STUN_KO_DEFEAT_BUG.md`). Therefore:

- The prerequisites header should drop "stun fixes" from the
  `fix-call-sequence-logging` merge list — only the call-sequence and
  resume-from-divergence work remains unmerged.
- Section 4's "rather than older main-branch semantics" and Phase 1's "close
  the remaining enemy-side stun-KO edge" are stale: lifecycle normalization
  should simply target current `main` semantics, and the enemy-side edge is
  closed, not open work for this plan.

### F2. `state_reconstructor.py` does not exist on main

It is branch-only. The merge-prerequisite framing in the validation section is
correct and now the *only* thing that branch is a prerequisite for.

### F3. Synthesis-boundary resume is a new capability, not an existing one

The plan requires resume to "restart at narrative synthesis without reapplying
the round's mechanics." The reconstructor as shipped resumes at *round
boundaries*: it folds recorded state to the end of round K-1 and seeds a fresh
live session at round K. Restarting mid-round at the synthesis step — with
round K's mechanics applied but its narration absent — is a capability it does
not have. The plan should pick one explicitly:

- (a) extend the reconstructor to fold through round K's applied outcomes and
  re-enter at synthesis (new work, should be named in Phase 4); or
- (b) define the checkpoint at the end-of-round-K mechanical state and accept
  that resume regenerates round K's synthesis as the opening of a fresh run
  seeded at K+1's boundary.

Option (b) is nearly free given what exists; option (a) is cleaner provenance.
Either is acceptable, but the phases should not silently assume (a).

Related caveat for "genuinely resumable": the reconstructor's known resume gaps
(stealth state, bond transitions, NPC resume, enemy shared-intel) apply to
these checkpoints too. They are acceptable for diagnosis-and-resume, but the
bulk-run promotion gate should count a resume that loses such state as a
degraded resume, not a clean one.

### Codex disposition on synced-main follow-up

All three corrections are accepted. The normative plan now:

- targets current `main` stun/KO semantics and treats enemy KO as existing behavior
  requiring regression coverage;
- states that `state_reconstructor.py` is branch-only and that the fix branch is an
  implementation base, not an already merged capability;
- chooses option (a), true synthesis-boundary resume, and names its checkpoint,
  phase-marker, hydration, provenance, and exactly-once cleanup requirements as new
  Phase 4 work;
- classifies resumes with unsupported NPC, stealth, bond, shared-intel, or other
  live state as degraded, diagnostic-only, and ineligible for accepted bulk corpus
  continuation.
