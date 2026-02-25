# Technical Design: aeonisk-phase-2

## Metadata
- **Feature**: aeonisk-phase-2
- **Status**: DRAFT
- **Created**: 2026-02-25
- **Author**: /zerg:design

---

## 1. Overview

### 1.1 Summary

Aeonisk Phase 2 implements 16 of 17 v2 specs across 4 priority waves, overhauling the multi-agent combat system for mechanical correctness, agent awareness, entity lifecycle, and infrastructure improvements. The implementation follows the wave dependency graph from requirements.md, enabling maximum parallelism within each wave while respecting cross-spec dependencies.

The core codebase is ~33k LOC across 17 key Python files. The largest files (dm.py: 8,930, session.py: 6,010, mechanics.py: 5,484) are modified by multiple specs at non-overlapping line ranges, requiring careful conflict management.

### 1.2 Goals
- Fix all P0 mechanical correctness bugs (NPCs deal 0 damage, conditions never expire, targets misbind to prisoners, defeated enemies persist)
- Implement stealth as a full mechanical system with is_hidden tracking and target filtering
- Complete IFF/ROE with selective intel sharing and faction-based reasoning
- Add defense tokens, environmental objects, range awareness, and inventory interactions
- Produce mechanically honest JSONL training data for all new systems
- Maintain backward compatibility with v1 session configs

### 1.3 Non-Goals
- Spec 08 (Suppression) — prompt-only treatment is final design, no mechanical changes
- Phase 3 selective condition targeting (affects field) — deferred until after suppression
- Progressive identity discovery in IFF — faction names visible, only relationship hidden
- Passive stealth detection — active Scan only, no round-start auto-detect

---

## 2. Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION ORCHESTRATOR                       │
│  session.py (6,010 LOC)                                     │
│  • Round loop, initiative, declaration/resolution phases     │
│  • tick_conditions() caller (Spec 14)                       │
│  • Resolution skip (Spec 15)                                │
│  • Clock persistence (Spec 17)                              │
│  • Display improvements (Spec 12)                           │
│  • Stealth state management (Spec 05)                       │
└───────────┬──────────┬──────────┬──────────┬────────────────┘
            │          │          │          │
   ┌────────▼──┐ ┌─────▼────┐ ┌──▼──────┐ ┌▼──────────────┐
   │ DM Agent  │ │ Players  │ │ Enemies │ │ NPCs          │
   │ dm.py     │ │ player.py│ │ enemy_  │ │ npc_agent.py  │
   │ (8,930)   │ │ (3,531)  │ │combat.py│ │ (769)         │
   │           │ │          │ │ (2,174) │ │               │
   │ Specs:    │ │ Specs:   │ │ Specs:  │ │ Specs:        │
   │ 01,03,04, │ │ 04,05,09 │ │ 01,02,  │ │ 01,07,13     │
   │ 06,12,14, │ │          │ │ 04,06   │ │               │
   │ 16        │ │          │ │         │ │               │
   └─────┬─────┘ └────┬─────┘ └────┬───┘ └───────┬───────┘
         │            │            │              │
   ┌─────▼────────────▼────────────▼──────────────▼─────────┐
   │                 MECHANICS ENGINE                         │
   │  mechanics.py (5,484 LOC)                               │
   │  • YAGS combat math, conditions, bonds, clocks          │
   │  • Specs: 14 (conditions), 04 (defense soak), 13 (bonds)│
   └──────────────────────┬──────────────────────────────────┘
                          │
   ┌──────────────────────▼──────────────────────────────────┐
   │               SCHEMAS & SHARED TYPES                     │
   │  schemas/*.py, target_ids.py, shared_state.py            │
   │  • Specs: 03, 05, 06, 10, 14, 17                        │
   └─────────────────────────────────────────────────────────┘
```

### 2.2 Component Breakdown

| Component | Responsibility | Primary Specs | Key Files |
|-----------|---------------|---------------|-----------|
| Conditions Pipeline | Fix extraction, duration, ticking, protection_amount | 14, 15 | structured_output_helpers.py, mechanics.py, dm.py, session.py |
| NPC Combat | Route NPC attacks through YAGS formula | 01 | dm.py, enemy_combat.py, agent_conversion.py |
| Enemy Lifecycle | Remove duplicate logging, prune stale enemies | 02 | session.py, enemy_combat.py, mechanics.py |
| Target Validation | State tags, semantic validation, DM instruction | 03 | dm.py, target_ids.py, targeting_validation.py |
| Stealth System | is_hidden tracking, opposed checks, target filtering | 05 | enemy_agent.py, player.py, npc_agent.py, dm.py, session.py |
| IFF/ROE | Selective intel, faction reasoning, intercepted comms | 06 | enemy_agent.py, enemy_prompts.py, schemas/enemy_decision.py, dm.py |
| Inventory | NPC purse, loot, item transfer, weapon context | 07 | npc_agent.py, player.py, energy_economy.py, dm.py |
| Defense Tokens | Universal token declaration and resolution | 04 | schemas/player_action.py, player.py, enemy_combat.py, dm.py |
| Range Bands | Awareness prompts, movement action | 09 | enemy_agent.py, player.py, dm.py |
| Env Objects | Destructible schema, HP, targeting | 10 | shared_state.py, target_ids.py, dm.py |
| Experiment Infra | Per-role model config, legacy audit | 11 | generate_multi_llm_configs.py, enemy_combat.py, session.py |
| Display | Status tables, conditions, NPC init, target IDs | 12 | session.py |
| Bonds/Vendors | Default bonds, vendor spawn prompting | 13 | session.py, mechanics.py, npc_agent.py |
| Resolution Skip | Condition-based auto-skip triggers | 15 | session.py |
| Adjudication Context | Phase 3: faction relationships | 16 | dm.py |
| Clock Persistence | keep_clocks on StoryAdvancement | 17 | schemas/story_events.py, session.py |

### 2.3 Data Flow — Condition Pipeline (Spec 14, representative)

```
LLM generates Pydantic Condition
    │ (name, penalty, duration, target, protection_amount)
    ▼
structured_output_helpers.py  →  Extract ALL fields to dict
    │ (currently loses target + protection_amount — FIX)
    ▼
dm.py condition creation  →  Use LLM duration (not hardcoded 3)
    │ (add protection_amount to dataclass)
    ▼
mechanics.py Condition dataclass  →  Add protection_amount field
    │ (applies_to() already works, just needs affects populated)
    ▼
mechanics.py:2086 roll resolution  →  Apply penalty per applies_to()
    ▼
session.py round cleanup  →  Call tick_conditions() (NEW CALLER)
    ▼
Expired conditions removed, JSONL logged
```

---

## 3. Detailed Design

### 3.1 New Schema Fields

**StoryAdvancement (Spec 17):**
```python
class StoryAdvancement(BaseModel):
    # ... existing fields ...
    keep_clocks: List[str] = Field(
        default_factory=list,
        description="Clock names to preserve across story advancement. "
                    "Empty = clear all clocks (current behavior)."
    )
```

**EnemyDecision (Spec 06):**
```python
class EnemyDecision(BaseModel):
    # ... existing fields ...
    intel_recipients: Optional[List[str]] = Field(
        default=None,
        description="tgt_xxxx IDs to share intel with. None = no sharing."
    )
```

**Agent is_hidden flag (Spec 05):**
```python
# On AIPlayerAgent, EnemyAgent, NPCAgent:
is_hidden: bool = False
stealth_dc: Optional[int] = None  # DC for detection when hidden
last_known_position: Optional[Position] = None
```

**StealthChange in MechanicalEffects (Spec 05):**
```python
class StealthChange(BaseModel):
    agent_id: str
    is_hidden: bool
    stealth_dc: Optional[int] = None
```

**PlayerActionBase defense_token (Spec 04):**
```python
class PlayerActionBase(BaseModel):
    # ... existing fields ...
    defense_token: Optional[str] = Field(
        default=None,
        description="tgt_xxxx ID of combatant you are watching/covering."
    )
```

### 3.2 Key Interface Changes

**SharedIntel refactor (Spec 06):**
```python
class SharedIntel:
    def add_intel(self, source_agent: str, intel: str, round_num: int,
                  recipients: Optional[Set[str]] = None):
        # recipients = set of tgt_xxxx IDs; None = legacy broadcast (iff_enabled=false)

    def get_recent_intel_for_target(self, target_id: str, current_round: int) -> List[str]:
        # Returns intel addressed to this specific target
```

**execute_npc_attack (Spec 01):**
```python
def execute_npc_attack(
    npc: NPCAgent, target_id: str, weapon_name: Optional[str],
    shared_state: SharedState, mechanics_engine: Any,
    resolution_state: ResolutionState, player_agents: List
) -> Dict[str, Any]:
    # Routes NPC attacks through enemy_combat._execute_attack() via proxy
```

**EnvironmentalObject HP tracking (Spec 10):**
```python
@dataclass
class EnvironmentalObject:
    # ... existing fields ...
    health: int = 0           # 0 = indestructible
    max_health: int = 0
    is_destructible: bool = False
    cover_value: int = 0      # Soak bonus when used as cover
```

---

## 4. Key Decisions

### Decision 1: dm.py Multi-Spec Coordination

**Context**: dm.py (8,930 LOC) is modified by 8 specs at different line ranges.

**Decision**: Specs modify non-overlapping regions and execute in dependency order. No single task "owns" dm.py — instead, each task owns specific functions/line ranges within it.

**Conflict regions**:
- Lines ~2883: Spec 01 (NPC logging gate)
- Lines ~4942-5058: Spec 01 (NPC attack replacement)
- Lines ~5952, ~6424: Spec 14 (condition duration)
- Lines ~7019-7615: Spec 16 (adjudication context)
- Lines ~7535-7578: Spec 03 (combatant state tags)

**Rationale**: dm.py is too large to be owned by one task. The line ranges are well-separated (500+ lines apart). Sequential execution within waves naturally prevents conflicts.

### Decision 2: NPC Attributes via Adapter, Not Field Addition

**Context**: NPCAgent has no `attributes` dict. Needed for NPC combat (Spec 01).

**Decision**: Use `estimate_attributes()` from agent_conversion.py at combat time via NPCCombatProxy, rather than adding `attributes` field to NPCAgent.

**Rationale**: NPCAgent is designed as lightweight. The adapter pattern keeps concerns separated and reuses existing code. Future work could add the field if needed.

### Decision 3: IFF Config Flag Gates All Changes

**Context**: IFF/ROE changes (Spec 06) fundamentally alter agent information flow.

**Decision**: `iff_enabled: bool = False` in session config. When false, all IFF changes are inactive and legacy behavior is preserved. Steps 1-4 (already done) are always active as they only remove misleading labels.

**Rationale**: Backward compatibility is critical for existing experiment configs. The flag allows gradual rollout and A/B testing.

### Decision 4: Active-Only Stealth Detection

**Context**: Two models for detection — passive (auto-check each round) vs active (explicit Scan action).

**Decision**: Active detection only. Enemies must spend a Scan minor action to attempt detection. No passive round-start checks.

**Rationale**: User-confirmed design decision. Makes stealth more meaningful as a tactical choice. Reduces complexity (no per-round automatic checks for every enemy).

### Decision 5: Condition Ticking After Synthesis

**Context**: Should conditions tick before or after DM's RoundSynthesis?

**Decision**: Tick after synthesis. Conditions are mechanically active during the round and expire at end-of-round cleanup.

**Rationale**: DM should narrate the current state, not the upcoming state. Matches YAGS round semantics. Condition with duration=1 lasts the current round.

---

## 5. Implementation Plan

### 5.1 Phase Summary

| Phase | Level | Tasks | Parallel | Est. Time (single) |
|-------|-------|-------|----------|---------------------|
| Wave 1: Correctness | 1 | 4 | Yes (4-way) | 8h |
| Wave 2 Independents + Wave 3 | 2 | 7 | Yes (7-way) | 14h |
| Stealth | 3 | 1 | No | 4h |
| IFF/ROE | 4 | 1 | No | 3h |
| Inventory | 5 | 1 | No | 3h |
| Wave 4: Polish | 6 | 2 | Yes (2-way) | 4h |
| Quality | 7 | 1 | No | 1h |
| **Total** | | **17** | | **37h** |

### 5.2 File Ownership

Each task owns specific files or specific regions of shared files.

| File | Task(s) | Spec(s) | Operation |
|------|---------|---------|-----------|
| `structured_output_helpers.py` | TASK-001 | 14 | modify |
| `mechanics.py` (Condition dataclass ~1647) | TASK-001 | 14 | modify |
| `mechanics.py` (tick_conditions ~4761) | TASK-001 | 14 | modify |
| `mechanics.py` (log_enemy_action ~542) | TASK-003 | 02 | modify |
| `mechanics.py` (bond/soak) | TASK-008 | 04 | modify |
| `dm.py` (NPC gate ~2883, attack ~4942) | TASK-002 | 01 | modify |
| `dm.py` (condition creation ~5952, ~6424) | TASK-001 | 14 | modify |
| `dm.py` (combatant list ~7535) | TASK-004 | 03 | modify |
| `dm.py` (adjudication ~7019) | TASK-006 | 16 | modify |
| `dm.py` (IFF changes) | TASK-013 | 06 | modify |
| `dm.py` (stealth prompts) | TASK-012 | 05 | modify |
| `session.py` (death state ~3062) | TASK-002 | 01 | modify |
| `session.py` (remove log_enemy_action ~2292) | TASK-003 | 02 | modify |
| `session.py` (tick_conditions ~3219) | TASK-001 | 14 | modify |
| `session.py` (skip extension ~2140) | TASK-007 | 15 | modify |
| `session.py` (clock persistence ~5209) | TASK-005 | 17 | modify |
| `session.py` (display ~3505) | TASK-015 | 12 | modify |
| `session.py` (stealth state) | TASK-012 | 05 | modify |
| `session.py` (bonds) | TASK-016 | 13 | modify |
| `enemy_combat.py` (execute_npc_attack) | TASK-002 | 01 | modify |
| `enemy_combat.py` (prune, suppress log) | TASK-003 | 02 | modify |
| `enemy_combat.py` (defense token) | TASK-008 | 04 | modify |
| `agent_conversion.py` | TASK-002 | 01 | modify |
| `target_ids.py` (state fields) | TASK-004 | 03 | modify |
| `target_ids.py` (env objects) | TASK-010 | 10 | modify |
| `targeting_validation.py` | TASK-004 | 03 | modify |
| `enemy_agent.py` (is_hidden) | TASK-012 | 05 | modify |
| `enemy_agent.py` (SharedIntel) | TASK-013 | 06 | modify |
| `enemy_prompts.py` (faction context) | TASK-013 | 06 | modify |
| `schemas/enemy_decision.py` | TASK-013 | 06 | modify |
| `schemas/story_events.py` | TASK-005 | 17 | modify |
| `schemas/player_action.py` | TASK-008 | 04 | modify |
| `schemas/shared_types.py` (description) | TASK-001 | 14 | modify |
| `schemas/shared_types.py` (stealth) | TASK-012 | 05 | modify |
| `schemas/action_resolution.py` (stealth) | TASK-012 | 05 | modify |
| `npc_agent.py` (purse, is_hidden) | TASK-014, TASK-012 | 07, 05 | modify |
| `player.py` (defense_token, is_hidden) | TASK-008, TASK-012 | 04, 05 | modify |
| `energy_economy.py` | TASK-014 | 07 | modify |
| `shared_state.py` (env object HP) | TASK-010 | 10 | modify |
| `awareness.py` (stealth filtering) | TASK-012 | 05 | modify |
| `generate_multi_llm_configs.py` | TASK-011 | 11 | modify |
| `dm_resolution_combat.yaml` | TASK-001 | 14 | modify |
| `dm_resolution_combat_suppression.yaml` | TASK-001 | 14 | modify |
| `dm_resolution_support.yaml` | TASK-001 | 14 | modify |
| `prompts/claude/en/player/*.yaml` | TASK-008, TASK-009 | 04, 09 | modify |
| `prompts/claude/en/dm/dm_commands.yaml` | TASK-012 | 05 | modify |
| Tests: `test_condition_*.py` | TASK-001 | 14 | create |
| Tests: `test_npc_combat_logging.py` | TASK-002 | 01 | create |
| Tests: `test_enemy_lifecycle.py` | TASK-003 | 02 | create |
| Tests: `test_target_validation.py` | TASK-004 | 03 | create/modify |
| Tests: `test_clock_persistence.py` | TASK-005 | 17 | create |
| Tests: `test_adjudication_context.py` | TASK-006 | 16 | create |
| Tests: `test_resolution_skip_conditions.py` | TASK-007 | 15 | create |
| Tests: `test_defense_tokens.py` | TASK-008 | 04 | create |
| Tests: `test_range_awareness.py` | TASK-009 | 09 | create |
| Tests: `test_env_objects.py` | TASK-010 | 10 | create |
| Tests: `test_experiment_infra.py` | TASK-011 | 11 | create |
| Tests: `test_stealth.py` | TASK-012 | 05 | create |
| Tests: `test_iff_roe.py` | TASK-013 | 06 | create/modify |
| Tests: `test_inventory_equipment.py` | TASK-014 | 07 | create |
| Tests: `test_display_improvements.py` | TASK-015 | 12 | create |
| Tests: `test_bonds_vendors.py` | TASK-016 | 13 | create |

### 5.3 Dependency Graph

```
LEVEL 1 — WAVE 1 (P0, PARALLEL)
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ TASK-001 │ │ TASK-002 │ │ TASK-003 │ │ TASK-004 │
│ Spec 14  │ │ Spec 01  │ │ Spec 02  │ │ Spec 03  │
│Conditions│ │NPC Combat│ │Enemy Life│ │Target Val│
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │              │
     └────────────┴────────────┴──────────────┘
                          │
                   WAVE 1 GATE
                          │
     ┌────────────────────┼────────────────────────┐
     │                    │                         │
LEVEL 2 — WAVE 2 INDEPENDENTS + WAVE 3 (PARALLEL)
┌────▼───┐┌───▼────┐┌────▼───┐┌────────┐┌────────┐┌────────┐┌────────┐
│TASK-005││TASK-006││TASK-007││TASK-008││TASK-009││TASK-010││TASK-011│
│Spec 17 ││Spec 16 ││Spec 15 ││Spec 04 ││Spec 09 ││Spec 10 ││Spec 11│
│Clocks  ││Adjudic.││Skip+   ││Defense ││Range   ││Env Obj ││Exper. │
└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘

LEVEL 3 — STEALTH
┌──────────────────────┐
│ TASK-012 — Spec 05   │
│ Stealth System       │
│ (depends: Wave 1)    │
└──────────┬───────────┘
           │
LEVEL 4 — IFF/ROE
┌──────────▼───────────┐
│ TASK-013 — Spec 06   │
│ IFF Steps 5-8        │
│ (depends: TASK-012)  │
└──────────┬───────────┘
           │
LEVEL 5 — INVENTORY
┌──────────▼───────────┐
│ TASK-014 — Spec 07   │
│ Inventory & Equipment│
│ (depends: TASK-013)  │
└──────────┬───────────┘
           │
LEVEL 6 — WAVE 4 (PARALLEL)
┌──────────▼───────────┐ ┌──────────────────────┐
│ TASK-015 — Spec 12   │ │ TASK-016 — Spec 13   │
│ Display & Observ.    │ │ Bonds & Vendors      │
│ (depends: TASK-014,  │ │ (depends: TASK-014)  │
│  TASK-010)           │ │                      │
└──────────┬───────────┘ └──────────┬───────────┘
           │                        │
           └────────────┬───────────┘
                        │
LEVEL 7 — QUALITY
┌───────────────────────▼──────────────────────────┐
│ TASK-017 — CHANGELOG.md                          │
│ (depends: all)                                   │
└──────────────────────────────────────────────────┘
```

---

## 6. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| dm.py merge conflicts between parallel Wave 1 tasks | Medium | Medium | Tasks modify non-overlapping line ranges (500+ lines apart). Sequential fallback if conflicts occur. |
| LLM compliance with new structured output fields (stealth_changes, intel_recipients, defense_token) | Medium | High | Strong prompt examples, schema validators, fallback defaults. Tested with multiple LLM providers. |
| Backward compatibility regression with v1 session configs | Low | High | All new fields have defaults preserving existing behavior. iff_enabled=false by default. Unit tests validate v1 config loading. |
| Stealth system complexity (7 phases) introduces edge cases | Medium | Medium | Comprehensive test plan in spec. Each phase has independent tests. Spec 05 has 1,086 lines of design detail. |
| IFF selective intel changes produce chaotic sessions | Medium | Low | Intentional — IFF errors are ML training signal. iff_enabled flag allows reverting per-session. |
| Condition ticking changes game dynamics | Low | Low | LLM default duration=1 means conditions were "supposed" to be 1 round. Hardcode to 3 was the bug, not the intended behavior. |

---

## 7. Testing Strategy

### 7.1 Unit Tests (Per-Spec, TDD)
Each spec has a dedicated test file written before implementation:
- Wave 1: test_condition_*.py, test_npc_combat_logging.py, test_enemy_lifecycle.py, test_target_validation.py
- Wave 2/3: test_stealth.py, test_iff_roe.py, test_inventory_equipment.py, test_defense_tokens.py, etc.
- Verification: `python -m pytest tests/unit/test_{spec}.py -v`

### 7.2 Integration Tests
Cross-spec interactions verified after each wave completes:
- Stealth → IFF: hidden agents bypass IFF checks
- Conditions → Resolution Skip: incapacitating conditions trigger auto-skip
- IFF → Inventory: faction determines vendor access
- Env Objects → Display: destructible objects shown in status

### 7.3 Regression Tests
- All existing tests must pass after each task
- Session configs from v1 validated via test_session_config_validation.py
- `diff_fixtures.py` comparison for mechanical changes

### 7.4 Verification Commands (Per-Task)
```bash
# Pattern for all tasks:
python -m pytest tests/unit/test_{spec}.py -v  # Task-specific tests
python -m pytest tests/unit/ -v --timeout=120   # Full regression
```

---

## 8. Parallel Execution Notes

### 8.1 Safe Parallelization
- Level 1 (Wave 1): 4 tasks, all modify different regions of shared files. Safe to parallelize with care.
- Level 2 (Wave 2 independents + Wave 3): 7 tasks, mostly different file sets. Safe to parallelize.
- Levels 3-5 (Stealth chain): Sequential by design (05→06→07).
- Level 6 (Wave 4): 2 tasks, independent files. Safe to parallelize.

### 8.2 Recommended Workers
- Minimum: 1 worker (sequential, ~37h)
- Optimal: 4 workers (matches Level 1 width, ~15h)
- Maximum: 7 workers (matches Level 2 width, ~12h)
- Diminishing returns beyond 7 (Levels 3-5 are sequential bottleneck)

### 8.3 Estimated Duration
- Single worker: ~37 hours
- With 4 workers: ~15 hours (2.5x speedup)
- With 7 workers: ~12 hours (3.1x speedup — bottlenecked on sequential chain)

### 8.4 Conflict Matrix

| Task A | Task B | Shared File | Risk | Resolution |
|--------|--------|------------|------|------------|
| TASK-001 | TASK-002 | dm.py | Low | Different line ranges (5952 vs 2883) |
| TASK-001 | TASK-002 | session.py | Low | Different line ranges (3219 vs 3062) |
| TASK-002 | TASK-003 | enemy_combat.py | Low | Both add new functions, non-overlapping |
| TASK-001 | TASK-003 | mechanics.py | Low | Different line ranges (1647 vs 542) |
| TASK-004 | TASK-001 | dm.py | Low | Different line ranges (7535 vs 5952) |
| TASK-008 | TASK-012 | player.py | None | Level 2 vs Level 3, sequential |
| TASK-010 | TASK-015 | target_ids.py | None | TASK-015 depends on TASK-010 |

---

## 9. Consumer Matrix

| Task | Creates/Modifies | Consumed By | Integration Test |
|------|-----------------|-------------|-----------------|
| TASK-001 | Condition pipeline fixes | TASK-007 (skip triggers) | tests/unit/test_condition_ticking.py |
| TASK-002 | NPC combat adapter | TASK-012 (stealth + NPC hide) | tests/unit/test_npc_combat_logging.py |
| TASK-003 | Enemy pruning | TASK-015 (display) | tests/unit/test_enemy_lifecycle.py |
| TASK-004 | Target state tags | TASK-012 (hidden state tags) | tests/unit/test_target_validation.py |
| TASK-005 | keep_clocks field | leaf | — |
| TASK-006 | Adjudication context | leaf (Phase 3 benefits from TASK-013) | — |
| TASK-007 | Condition skip triggers | leaf | — |
| TASK-008 | Defense tokens | TASK-015 (display token info) | tests/unit/test_defense_tokens.py |
| TASK-009 | Range awareness | TASK-015 (range display) | — |
| TASK-010 | Env object HP/targeting | TASK-015 (env display) | tests/unit/test_env_objects.py |
| TASK-011 | Per-role model config | leaf | — |
| TASK-012 | Stealth system | TASK-013 (hidden bypass IFF) | tests/unit/test_stealth.py |
| TASK-013 | Selective intel | TASK-014 (faction vendor access) | tests/unit/test_iff_roe.py |
| TASK-014 | Inventory system | TASK-015, TASK-016 | tests/unit/test_inventory_equipment.py |
| TASK-015 | Display improvements | leaf | — |
| TASK-016 | Bond/vendor defaults | leaf | — |
| TASK-017 | CHANGELOG.md | leaf | — |

---

## 10. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Architecture | | | PENDING |
| Engineering | | | PENDING |
