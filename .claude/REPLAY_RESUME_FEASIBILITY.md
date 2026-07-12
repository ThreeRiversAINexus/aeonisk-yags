# Resume-from-Divergence Feasibility Study

**Date:** 2026-07-12 · **Verdict: GO (with scoped caveats)**

## Question

Can we reconstruct engine state at a round boundary K−1 from a recorded
session's events alone, and seed a **live** session from there — so a code
change is verified by paying tokens only for rounds K..end instead of a full
re-run? (User design call: replay halts at first divergence and *plays* from
there; the prefix is **loaded, not replayed** — no MockLLMProvider needed for
the prefix.)

Method: inventory of what the engine needs at a round boundary vs. what the
JSONL actually carries, verified against a current-code smoke session
(`session_5bffc2cf…`) and the 41-event-type schema contract. Findings below are
observed, not assumed.

## What IS reconstructible (verified present)

| State | Source | Quality |
|---|---|---|
| Session config incl. full character sheets (attributes, skills, inventory, weapons, goals, personality, llm) | `session_start.config` | complete |
| Party vitals per round: health/max, wounds, **stuns**, void, soulcredit, position, death_state | `character_state` (every PC, every round) | complete |
| Party economy: energy purse (5 currencies) + seeds | `character_state.energy/seeds` | complete |
| Party conditions | `character_state.conditions` — **was hardcoded `[]` (TODO); fixed this change** | complete going forward; empty in historical corpus |
| Enemy base stats | `enemy_spawn.stats` (health, attributes, skills, soak, armor, weapons) | complete |
| Enemy vitals per round | `character_state` (agent=enemy, all *active* enemies each round) + fold `combat_action.defender_state_after`, `healing_applied`, `enemy_defeat`, `morale_check`, `agent_conversion`, `entity_lifecycle` | good; roster-transition rounds can miss a snapshot but the fold covers them |
| Scene clocks | `clock_spawn/advancement/removal/update/completion` fold, cross-checkable vs `action_resolution.clocks` ("cur/max" strings) | complete |
| Environmental void | `void_level_update` events | complete |
| Narrative context for the DM | `scenario` + `round_synthesis` history | complete |
| Player narrative memory | `narrative_memory` (per player, per round: locations, beats, summary) | complete |
| NPC/prisoner roster | `agent_conversion`, `npc_departure`, `entity_lifecycle` fold | good |

## What is NOT reconstructible (honest gaps)

1. **RNG stream position.** `random_seed` is logged but the stream offset at
   round K is lost. *Acceptable by design*: the resumed tail is live/new — this
   is a warm start, not a determinism claim.
2. **Historical conditions.** Pre-fix corpus logged `conditions: []`; only
   sessions recorded after this change carry them.
3. **Enemy shared-intel pool & morale flags mid-round.** Partially derivable
   from declarations + `morale_check`; enemies are short-lived, low impact.
4. **Stealth/visibility state** (hidden PCs). No dedicated event. Rare; a
   resumed PC re-hides if it matters.
5. **Bond status transitions** mid-session (dormant/void-locked). Not
   per-round logged. Matters only for bond-heavy scenarios.
6. **Per-round transients** (defence tokens, declared actions, initiative).
   *Not a gap*: resuming **only at round boundaries** sidesteps them — they are
   rebuilt at round start by construction.

## Implementation sketch (rung 3, when built)

1. `state_reconstructor.py`: load session → fold to end of round K−1 →
   emit a **resume config**. Most seeding rides *existing* config surfaces:
   - clocks → `starting_clocks` (supports `current_ticks`) ✓ exists
   - enemies → `initial_enemies` ✓ exists (needs a small current-hp/wounds
     override extension)
   - scenario/narrative → `force_scenario` + `_scenario_hint` ✓ exists
   - party vitals/purse → **new** small hook: apply overrides to
     `character_state` after agent creation (the one genuinely new seam)
2. Divergence detection chooses K: mechanics-diff harness (formula changes) or
   first semantic-cache miss via `call_type` (flow changes).
3. Session runs live from round K with `max_turns` shortened accordingly.

Token economics: for a change diverging at round K of an N-round session, cost
≈ (N−K+1)/N of a full run — e.g. verify a round-6 divergence in a 10-round
session for ~half price, with zero re-record of the prefix.

## Prerequisites already shipped (this branch)

- call_sequence contiguity (all 3 agent types) + invariant gate
- `call_type` semantic tag on all llm_calls (3 structured paths + text paths)
- phantom DM adjudication double-log removed
- `ko_check` events + condition serialization (this doc's fix)
- mechanics-diff harness (rung 1) + contract replay (rung 2) as the cheap
  divergence detectors that decide K
