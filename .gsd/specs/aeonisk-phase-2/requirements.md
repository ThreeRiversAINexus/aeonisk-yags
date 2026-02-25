# Aeonisk Phase 2 — Requirements

**Status:** APPROVED
**Feature:** aeonisk-phase-2
**Created:** 2026-02-25
**Branch:** TBD (new branch from updated main)

---

## 1. Summary

Aeonisk Phase 2 implements the v2 specification suite (`.claude/aeonisk_v2/`) — 16 of 17 specs covering mechanical correctness, combat systems, agent awareness, entity lifecycle, and infrastructure improvements. Suppression (Spec 08) is excluded (prompt-only treatment already complete).

This is a comprehensive overhaul of the multi-agent combat system to produce coherent, measurable, and mechanically honest outcomes for ML training data.

---

## 2. Scope — Included Specs (16 of 17)

### Wave 1 — P0, Parallel (Fundamental Correctness)

| Spec | Title | Summary |
|------|-------|---------|
| 01 | NPC Combat Mechanics | NPCs declare attacks but deal 0 damage; give NPCs the same combat resolution pipeline as enemies |
| 02 | Enemy Lifecycle & Defeat Semantics | `enemy_defeat` conflates kills/departures/despawns; separate into distinct event types with mechanical consequences |
| 03 | Target Validation & Free-Target Binding | DM resolves `tgt_xxxx` to prisoners/civilians when players described hostiles; add eligibility constraints |
| 14 | Conditions & Modifiers | 6 bugs: descriptions claim selective targeting but apply to all rolls; `target` field lost; duration hardcoded to 3 and never ticked; `affects` dead code; `protection_amount` not propagated |

**Gate:** Wave 1 must be complete before treatment experiments. All datamining depends on these events being mechanically correct.

### Wave 2 — P1, Sequential Chain + Independents

| Spec | Title | Depends On |
|------|-------|-----------|
| 05 | Stealth & Hidden State | Wave 1 complete |
| 06 | IFF & Rules of Engagement | 05 Stealth (hidden agents bypass IFF) |
| 07 | Inventory & Equipment Interaction | 06 IFF (faction determines vendor access/loot) |
| 15 | Resolution Phase Skip (condition triggers) | 14 Conditions (condition-based incapacitation) |
| 16 | Adjudication Context | Independent (benefits from 06 IFF) |
| 17 | Clock Persistence | Independent, small scope |

### Wave 3 — P2, Parallel After Wave 1

| Spec | Title |
|------|-------|
| 04 | Defense Tokens |
| 09 | Range Bands & Movement |
| 10 | Environmental Objects & Destructibles |
| 11 | Experiment Infrastructure |

### Wave 4 — P3, Parallel After Wave 2

| Spec | Title |
|------|-------|
| 12 | Display & Observability |
| 13 | Bonds & Vendor Spawning |

### Excluded

| Spec | Title | Reason |
|------|-------|--------|
| 08 | Suppression Resolution | Prompt-only treatment complete (v1-v3 iterations). No mechanical changes desired. |

---

## 3. Key Design Decisions

### 3.1 Stealth — Active Detection Only

- **No passive detection at round start.** Enemies must spend a Scan minor action to attempt detection.
- Hidden agents stay hidden until actively searched or stealth is broken by attack.
- Full 7-phase implementation: `is_hidden` flag, opposed checks (Agility×Stealth vs Perception×Awareness), target filtering, stealth breaking on attack, search/detection via Scan, last-known-position tracking, prompt updates.
- Void interaction: void_score >= 7 gives detectors +5 bonus; void_score 10 = stealth impossible.
- First Strike: +2 damage mechanical modifier on first attack from hidden (structured output, not narrative).
- NPC `hide` action mechanically sets `is_hidden` via stealth check.

### 3.2 IFF/ROE — Finish Steps 5-8

- **Step 5:** Refactor SharedIntel from global broadcast → explicit `recipients: Set[str]` (tgt_xxxx IDs). Battlefield-wide pool.
- **Step 6:** `intel_recipients: Optional[List[str]]` on EnemyDecision schema. LLM picks recipients by faction reasoning.
- **Step 7:** `_get_intercepted_intel_for_pc()` — enemy intel accidentally shared with PC appears as "INTERCEPTED COMMUNICATIONS".
- **Step 8:** Enemy faction context prompt ("You are ACG. Determine allegiance from faction names.") + PC party context (party member tgt_xxxx list).
- `iff_enabled` config flag (default false) gates all changes. Legacy behavior preserved when disabled.

### 3.3 Resolution Skip — Add Condition-Based Triggers

- Spec 15 Phase 1 + Phase 2 are already implemented.
- **New work:** After Spec 14 (conditions) is implemented, add auto-skip for agents with incapacitating conditions (e.g., Stunned penalty >= -6).
- This is additive to existing `ResolutionState.is_incapacitated()` check.

### 3.4 Suppression — Excluded

- Treatment v1-v3 prompt iterations are complete.
- No mechanical `base_damage=0` enforcement.
- Existing prompt-level approach is the final design.

### 3.5 Implementation Priority — Parallel Waves

- Wave 1 specs implemented in parallel (no interdependencies).
- Wave 2 + Wave 3 in parallel where no dependency conflicts:
  - 05→06→07 chain is sequential.
  - 15 (condition triggers) follows 14.
  - 16 (adjudication context), 17 (clock persistence) are independent — parallel with anything.
  - Wave 3 specs (04, 09, 10, 11) are independent — parallel with Wave 2.
- Wave 4 last (12 display, 13 bonds/vendors).

---

## 4. Functional Requirements

### FR-01: NPC Combat Mechanics (Spec 01)
- NPCs must deal mechanical damage when attacking (same resolution pipeline as enemies).
- NPC double-healing bug must be fixed.
- NPC double-logging bug must be fixed (adjudicate_npc + adjudicate phases).

### FR-02: Enemy Lifecycle (Spec 02)
- `enemy_defeat` events must distinguish killed, fled, retreated, subdued, departed, despawned.
- `pc_defeated` flag must reflect actual combat outcomes (currently always false).
- 0 HP + "conscious" status edge case must be resolved.
- Defeated enemies must be fully removed from internal lists (stop log spam).

### FR-03: Target Validation (Spec 03)
- Free-target IDs must not resolve to prisoners or civilians when player described active hostiles.
- Eligibility filter on target binding: prisoners, surrendered, and civilians excluded from hostile-intent resolutions.
- Naming deduplication: prevent NPC spawns that duplicate PC names.

### FR-04: Conditions & Modifiers (Spec 14)
- Condition descriptions must not claim selective targeting (penalty applies to ALL rolls).
- `target` field must be preserved through extraction pipeline.
- Duration must come from LLM (not hardcoded to 3).
- `tick_conditions()` must be called each round.
- `affects` field dead code must be removed or implemented.
- `protection_amount` must be propagated correctly.

### FR-05: Stealth System (Spec 05)
- `is_hidden` boolean flag on AIPlayerAgent, EnemyAgent, NPCAgent.
- Opposed check: Agility × Stealth + d20 vs Environment DC (hide); Perception × Awareness + d20 vs stealth_dc (detect).
- Hidden agents excluded from target lists for opposing agents (allies still see each other).
- Attack from hidden auto-breaks stealth.
- Detection via active Scan minor action only (no passive round-start detection).
- Last known position stored when agent hides; enemies reference it.
- DM sets `is_hidden` via `StealthChange` in `MechanicalEffects` structured output.
- `search_for_hidden` field on PerceptionAction for PC detection.
- Void >= 7: +5 detection bonus. Void 10: stealth impossible.
- First Strike: +2 damage modifier on first attack from hidden.
- NPC `hide` action triggers mechanical stealth check.

### FR-06: IFF & Rules of Engagement (Spec 06)
- Steps 5-8 as described in Section 3.2.
- `iff_enabled` config flag (default false).
- SharedIntel refactored to tgt_xxxx-based selective recipients.
- EnemyDecision `intel_recipients` field.
- Intercepted communications for PCs on IFF errors.
- Enemy faction context and PC party context prompts.
- Backward compat: `iff_enabled=false` preserves legacy behavior.

### FR-07: Inventory & Equipment (Spec 07)
- Players can interact with equipped items (primary, sidearm, gear).
- Item finding in the world.
- NPC giving/receiving items.
- Enemy loot on search.
- NPCs can receive currency (purse initialization).
- Offerings already deduct automatically (no change needed).

### FR-08: Defense Tokens (Spec 04)
- Token generation, consumption, and expiry lifecycle.
- Each agent can assign one defense token to another agent per declaration.
- Mechanical effect: +1 Soak when defending partner.

### FR-09: Range Bands & Movement (Spec 09)
- Range-band topology validation.
- Movement cost enforcement.
- Improved agent awareness prompts for range reasoning.
- Corrected via prompting (not failure mode).
- Dodge-as-movement: players can use agility to avoid incoming damage (movement in response to later resolutions).

### FR-10: Environmental Objects (Spec 10)
- Destructible object schema with HP tracking.
- Cover degradation mechanics.
- Objects are targets (can be attacked/interacted with).
- Show HP and descriptions/hints.

### FR-11: Experiment Infrastructure (Spec 11)
- Per-role model config (DM, players, NPCs, enemies independently configurable).
- Legacy code path audit and routing (direct/proxy/pydantic/parsing).
- Bulk config generator supports per-role model variation.

### FR-12: Resolution Skip — Condition Triggers (Spec 15 extension)
- After Spec 14 implementation, add auto-skip for agents with incapacitating conditions.
- Stunned penalty >= -6 → mark incapacitated in resolution_state → auto-skip.
- Additive to existing Phase 1 hard auto-skip.

### FR-13: Adjudication Context (Spec 16)
- SC ledger, pronouns, narrative digest injected into adjudication prompt.
- Phases 0-2 already implemented (commit `ee3305c8`).
- Remaining: Phase 3 faction relationships (benefits from 06 IFF).

### FR-14: Clock Persistence (Spec 17)
- `keep_clocks` field on StoryAdvancement so DM can carry clocks across scene boundaries.
- ScenePivot already has `clear_specific_clocks`; StoryAdvancement needs equivalent.

### FR-15: Display & Observability (Spec 12)
- Formatted combatant status tables.
- Range-band map display.
- Clock progress bars.
- Full enemy action declarations in stdout.
- NPC action declarations (not truncated).
- Conditions shown in normal output.
- NPC initiative values in stdout.
- Active targeting ID mapping in round status.
- Environmental objects in round summary.

### FR-16: Bonds & Vendor Spawning (Spec 13)
- Bonds exist by default on character creation (even if empty).
- Bond matrix generated by default (opt-out via config).
- Bond formation/breaking as explicit actions (intimacy ritual skill or NPC mediation).
- Agents prompted with bond matrix context.
- DM prompted to spawn vendors in appropriate scenes.
- Live bond transition testing.

---

## 5. Non-Functional Requirements

### NFR-01: TDD Mandatory
All code changes must follow TDD protocol: failing tests first (red), implementation to pass (green), refactor. No implementation code without a failing test.

### NFR-02: Structured Output Philosophy
All new mechanics expressed as Pydantic schema fields. No keyword detection. No text parsing for mechanical effects. Freeform narration and typed mechanics in separate fields.

### NFR-03: JSONL Logging
Every new mechanical system emits JSONL events. New event types documented in LOGGING_IMPLEMENTATION.md before implementation. Existing event types extended, not duplicated.

### NFR-04: Backward Compatibility
Session configs from v1 must continue to load and run. New fields use defaults preserving existing behavior. Bulk runner output comparable via `diff_fixtures.py`.

### NFR-05: Prompt Modularity
New DM capabilities use modular prompt system (`prompts/claude/en/dm/`). Each module has `load_when` condition.

---

## 6. Acceptance Criteria

1. All 16 included specs pass their unit test plans (from spec files).
2. Integration tests verify cross-spec interactions (stealth→IFF, conditions→skip).
3. Session configs from v1 run without errors (backward compat).
4. `iff_enabled: true` sessions produce faction-based IFF reasoning (no relationship labels leak).
5. Hidden agents are excluded from opposing target lists.
6. NPCs deal mechanical damage when attacking.
7. Conditions tick each round with LLM-determined durations.
8. Defeated enemies fully removed from internal tracking.
9. Free-target IDs never resolve to prisoners/civilians for hostile-intent actions.
10. JSONL events for all new mechanics are valid per schema.

---

## 7. Infrastructure Requirements

- No new external services or dependencies.
- No new environment variables.
- New session config fields: `iff_enabled` (bool, default false), `keep_clocks` (on StoryAdvancement).
- New branch from updated main.

---

## 8. Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Suppression mechanical? | No. Prompt-only. Excluded from phase 2. |
| Stealth passive detection? | No. Active Scan only. |
| Resolution skip scope? | Add condition-based triggers after Spec 14. |
| Wave ordering? | Parallel where possible. |
| Branch strategy? | New branch from main (faction-politics merged). |

---

## 9. Dependency Graph

```
                    WAVE 1 (P0) — PARALLEL
    ┌──────────┬──────────┬──────────┬──────────┐
    │ 01 NPC   │ 02 Enemy │ 03 Target│ 14 Condi-│
    │ Combat   │ Lifecycle│ Valid.   │ tions    │
    └────┬─────┴────┬─────┴────┬─────┴────┬─────┘
         └──────────┴──────────┴──────────┘
                         │
                    WAVE 1 GATE
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    WAVE 2 (P1)    WAVE 3 (P2)    INDEPENDENTS
    Sequential      Parallel        Parallel
         │               │               │
    05 Stealth      04 Defense     16 Adjudication
         │          09 Range       17 Clocks
    06 IFF/ROE      10 Env Obj     15 Skip+Conds
         │          11 Experiment      (after 14)
    07 Inventory         │
         │               │
         └───────┬───────┘
                 │
            WAVE 4 (P3)
            Parallel
                 │
         ┌───────┴───────┐
    12 Display    13 Bonds/Vendors
```

---

## 10. Risks

1. **Scope size:** 16 specs is a large undertaking. Mitigate with parallel implementation and clear wave gating.
2. **LLM compliance:** New structured output fields (action_skipped, stealth_changes, intel_recipients) depend on LLMs populating them correctly. Mitigate with strong prompt examples and schema validators.
3. **Backward compat:** Extensive changes to core systems (dm.py, session.py, mechanics.py). Mitigate with comprehensive unit tests and existing fixture tools.
4. **IFF complexity:** Selective intel sharing creates new failure modes (wrong recipients). This is intentional (ML training signal) but may produce chaotic sessions initially.
