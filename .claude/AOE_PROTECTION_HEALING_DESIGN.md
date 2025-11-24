# AoE Damage, Protection Barriers, and Healing Integration

**Design Document v1.0**
**Created:** 2025-01-15
**Status:** Draft - Under Review

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Design Goals](#design-goals)
4. [Schema Changes](#schema-changes)
5. [Processing Logic](#processing-logic)
6. [Tactical Module Integration](#tactical-module-integration)
7. [ML Training Implications](#ml-training-implications)
8. [Implementation Plan](#implementation-plan)
9. [Testing Strategy](#testing-strategy)
10. [Migration & Backwards Compatibility](#migration--backwards-compatibility)
11. [Edge Cases & Failure Modes](#edge-cases--failure-modes)
12. [Future Enhancements](#future-enhancements)

---

## Executive Summary

This design introduces three related features to the multi-agent RPG system:

1. **Area of Effect (AoE) Damage:** Multi-target damage via `List[DamageEffect]`
2. **Protection Barriers:** Damage absorption via `Condition.protection_amount`
3. **Healing Integration:** Mechanical healing via `HealingEffect` in `MechanicalEffects`

**Key Insight:** These features are synergistic - AoE creates multi-target scenarios, barriers protect against AoE, and healing recovers from failed protection.

**Breaking Changes:**
- `MechanicalEffects.damage` changes from `Optional[DamageEffect]` → `List[DamageEffect]`
- All damage processing code must iterate over list

**Migration Path:** Implement in single PR with comprehensive tests, update all references simultaneously.

---

## Problem Statement

### Current Limitations

1. **Single-Target Damage Only:**
   - DM cannot mechanically represent AoE attacks (grenades, explosions, void waves)
   - Must choose single target or omit damage for others (inconsistent ML training data)
   - Narratively describes AoE but mechanically single-target (confusing for LLMs)

2. **Barriers Are Narrative-Only:**
   - DM describes "creates protective barrier" but no mechanical effect
   - Barriers succeed in narration but provide no actual protection
   - No way to track damage absorption or barrier depletion
   - Poor ML training - success with no mechanical outcome

3. **Healing Not Integrated:**
   - `HealingEffect` schema exists but not in `MechanicalEffects`
   - DM cannot declare healing outcomes mechanically
   - Healing relies on Medicine skill application outside action resolution
   - Inconsistent with damage/void/condition patterns

### User Pain Points

- **Players:** "I used a barrier ritual successfully but still took full damage"
- **DM LLM:** Narratively describes AoE hitting 3 enemies, mechanically only 1 takes damage
- **ML Training:** Missing multi-target combat examples, protection mechanics, healing patterns

---

## Design Goals

### Primary Goals

1. **Multi-Target Consistency:** Single schema pattern for all multi-target effects
2. **Explicit Mechanics:** No keyword parsing, all mechanics via structured output
3. **ML Training Value:** Clear, explicit training data for AoE, protection, healing
4. **Backward Compatibility:** Minimal disruption to existing sessions/fixtures

### Non-Goals

1. **Automatic Range Calculation:** DM determines AoE targets based on tactical state
2. **Complex Blast Physics:** No line-of-sight, cover modifiers (DM handles narratively)
3. **Stacking Protection:** Single active barrier per target (for v1.0)

### Success Criteria

- [ ] DM can mechanically resolve grenade hitting 3 enemies with different damage
- [ ] Barrier ritual blocks damage and depletes when overwhelmed
- [ ] Healing action restores HP/stun/wounds via structured output
- [ ] All existing tests pass after migration
- [ ] New test coverage ≥95% for new features

---

## Schema Changes

### 1. MechanicalEffects.damage: List[DamageEffect]

**Current:**
```python
class MechanicalEffects(BaseModel):
    damage: Optional[DamageEffect] = Field(default=None, description="Damage dealt (if any)")
```

**Proposed:**
```python
class MechanicalEffects(BaseModel):
    damage: List[DamageEffect] = Field(
        default_factory=list,
        description="Damage dealt to targets. Empty list = no damage. Single target = list with 1 entry. AoE = list with multiple entries."
    )
```

**Rationale:**
- Consistent with other multi-target effects (`void_changes`, `conditions`, etc.)
- Allows different damage per target (margin-based scaling, partial soak)
- Clear distinction: empty list (no damage) vs list with entries (damage dealt)

**Migration:**
- All code expecting `Optional[DamageEffect]` must change to iterate list
- Empty list replaces `None` for "no damage"
- Single-target becomes `[DamageEffect(...)]`

---

### 2. Condition.protection_amount: Optional[int]

**Current:**
```python
class Condition(BaseModel):
    name: str
    penalty: int
    duration: int
    description: str
    target: Optional[str] = None
```

**Proposed:**
```python
class Condition(BaseModel):
    name: str
    penalty: int
    duration: int
    description: str
    target: Optional[str] = None
    protection_amount: Optional[int] = Field(
        default=None,
        ge=0,
        description="Damage absorption capacity. If present, this condition blocks incoming damage up to this amount. Depletes as damage is absorbed."
    )
```

**Rationale:**
- Leverages existing `Condition` system (no new schema needed)
- Optional field - normal conditions unaffected
- Penalty=0 for protection (barriers don't modify rolls, they absorb damage)
- Duration mechanics already exist (barrier expires after N rounds)

**Examples:**
```python
# Barrier that blocks 10 damage for 2 rounds
Condition(
    name="Astral Barrier",
    target="tgt_7a3f",
    penalty=0,
    duration=2,
    description="Shimmering barrier blocks 10 damage",
    protection_amount=10
)

# Normal debuff (no protection)
Condition(
    name="Stunned",
    penalty=-3,
    duration=1,
    description="Cannot act, -3 to rolls"
    # protection_amount is None (default)
)
```

**Edge Cases:**
- `protection_amount=0` → Depleted barrier (remove immediately)
- Multiple barriers on same target → Process in order applied (FIFO)
- Barrier with `duration=0` → Removed at end of round

---

### 3. MechanicalEffects.healing: List[HealingEffect]

**Current:**
```python
# HealingEffect exists in action_effects.py but NOT in MechanicalEffects
```

**Proposed:**
```python
class MechanicalEffects(BaseModel):
    # ... existing fields
    healing: List[HealingEffect] = Field(
        default_factory=list,
        description="Healing applied to targets. Supports hp (health restore), stun (stun removal), wound (wound reduction). Empty list = no healing."
    )
```

**Rationale:**
- HealingEffect schema already exists and well-designed
- Follows same pattern as damage (list for multi-target)
- Enables DM to mechanically resolve healing actions
- Medicine skill checks can populate this field

**HealingEffect Schema (existing):**
```python
class HealingEffect(BaseModel):
    target: str  # Target agent ID or tgt_xxxx
    heal_type: Literal["stun", "wound", "hp"]
    amount: int  # Amount healed (≥0)
    source: Optional[str]  # "medkit", "ritual", "field_medicine"
```

**Examples:**
```python
# Single-target medkit usage
healing=[HealingEffect(target="tgt_7a3f", heal_type="hp", amount=15, source="medkit")]

# Multi-target healing ritual
healing=[
    HealingEffect(target="tgt_abc1", heal_type="hp", amount=10, source="ritual"),
    HealingEffect(target="tgt_def2", heal_type="stun", amount=2, source="ritual"),
]
```

---

## Processing Logic

### 1. Multi-Target Damage Processing

**File:** `dm.py` lines ~4105-4180 (damage application)

**Current Flow:**
```python
if effects.damage:
    target = effects.damage.target
    amount = effects.damage.dealt
    apply_damage(target, amount)
```

**Proposed Flow:**
```python
for damage_effect in effects.damage:
    target = damage_effect.target
    amount = damage_effect.dealt

    # Check for active protections BEFORE applying damage
    protected_amount, updated_barriers = intercept_damage_with_barriers(
        target_entity=target,
        incoming_damage=amount
    )

    # Apply reduced damage
    actual_damage = amount - protected_amount
    apply_damage(target, actual_damage)

    # Update target's barrier conditions
    update_barrier_conditions(target, updated_barriers)
```

**Key Changes:**
- Iterate `for damage_effect in effects.damage:`
- Maintain existing wound calculation per target: `wounds = damage // 5`
- Call damage interception logic for each target
- Log each damage application separately for ML training

---

### 2. Damage Interception by Barriers

**New Function:** `intercept_damage_with_barriers()`
**File:** `dm.py` (new function, ~50 lines)

**Logic:**
```python
def intercept_damage_with_barriers(target_entity, incoming_damage: int) -> Tuple[int, List[Condition]]:
    """
    Check target's active protections and absorb damage.

    Args:
        target_entity: Agent with .conditions list
        incoming_damage: Damage before protection

    Returns:
        (protected_amount, updated_barriers): How much damage was blocked, updated barrier list
    """
    # Filter active barriers (conditions with protection_amount)
    barriers = [c for c in target_entity.conditions if c.protection_amount is not None and c.protection_amount > 0]

    if not barriers:
        return (0, [])  # No protection

    # Take first barrier (FIFO order)
    barrier = barriers[0]

    # Calculate absorption
    absorbed = min(barrier.protection_amount, incoming_damage)
    barrier.protection_amount -= absorbed

    # If depleted, mark for removal (protection_amount = 0)
    updated_barriers = barriers.copy()
    if barrier.protection_amount <= 0:
        # Barrier depleted - will be removed by condition cleanup
        barrier.duration = 0  # Expire immediately

    return (absorbed, updated_barriers)
```

**Integration Points:**
- Called before `apply_damage()` in damage processing loop
- Updates barrier `protection_amount` in-place
- Depleted barriers (protection_amount=0) removed by existing condition cleanup
- Logs barrier absorption to JSONL (new event type or in action_resolution)

**Edge Cases:**
- Multiple barriers: Process in order (FIFO), absorb until depleted, then next barrier
- Barrier expires same round as hit: Duration check happens AFTER damage absorption
- Barrier with `duration=0` but `protection_amount>0`: Valid (1-time use barrier)

---

### 3. Healing Processing

**File:** `dm.py` (new function, similar to damage processing)

**New Function:** `apply_healing_effects()`
```python
def apply_healing_effects(resolution: ActionResolution, mechanics: MechanicsEngine):
    """
    Process healing effects from action resolution.

    Similar pattern to damage processing - iterate list, apply to targets.
    """
    for healing in resolution.effects.healing:
        target_entity = get_entity_by_id(healing.target)

        if healing.heal_type == "hp":
            # Restore health points (cap at max_health)
            target_entity.health = min(
                target_entity.health + healing.amount,
                target_entity.max_health
            )

        elif healing.heal_type == "stun":
            # Remove stun markers
            target_entity.stuns = max(0, target_entity.stuns - healing.amount)

        elif healing.heal_type == "wound":
            # Reduce wounds (each wound = -5 to all rolls)
            target_entity.wounds = max(0, target_entity.wounds - healing.amount)

        # Log healing to JSONL
        if mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_healing(healing, target_entity)
```

**Integration:**
- Called after damage processing in `_process_action_resolution()`
- Uses existing `apply_healing()` function from mechanics.py (line 3793)
- Logs to JSONL (healing event type)

---

### 4. Agent State Tracking

**Files:** `player.py`, `enemy_combat.py`, `npc_agent.py`

**Current:**
```python
class PlayerAgent:
    def __init__(...):
        self.conditions: List[Condition] = []
```

**No changes needed!** Conditions already tracked per agent.

**Barrier Filtering Logic:**
```python
def get_active_protections(agent) -> List[Condition]:
    """Get active barrier conditions for this agent."""
    return [c for c in agent.conditions if c.protection_amount is not None and c.protection_amount > 0]
```

**Duration Decrement (existing):**
- Already handled in `_decrement_condition_durations()` (dm.py)
- Barriers with `duration=0` removed automatically
- No changes needed

---

## Tactical Module Integration

### Range-Band-Aware AoE

**Problem:** In tactical combat, AoE must respect range bands (Engaged, Near-PC, Far-Enemy, etc.)

**Solution:** DM determines targets based on declared range + tactical state

**Flow:**
1. Player declares: "Throw grenade at Near-Enemy range"
2. DM checks tactical state: which enemies at Near-Enemy?
   - Enemy 1 (tgt_7a3f) at Near-Enemy
   - Enemy 2 (tgt_3c5d) at Near-Enemy
   - Enemy 3 (tgt_2b1c) at Far-Enemy (NOT HIT)
3. DM generates `List[DamageEffect]` for targets at Near-Enemy
4. DM may reduce damage for adjacent ranges (e.g., Engaged enemies take 50% damage)

**Schema Support:**
```python
# No schema changes needed - DM handles range logic
# Damage list reflects final targets hit

ActionResolution(
    success=True,
    narration="Your grenade explodes at Near-Enemy range, catching two enemies!",
    effects=MechanicalEffects(
        damage=[
            DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12),  # Near-Enemy
            DamageEffect(target="tgt_3c5d", base_damage=12, dealt=12),  # Near-Enemy
            # tgt_2b1c NOT in list (out of range)
        ]
    )
)
```

**Adjacent Range Spillover:**
```python
# Grenade centered at Near-Enemy, affects Engaged at reduced damage
damage=[
    DamageEffect(target="tgt_7a3f", base_damage=15, dealt=15),  # Near-Enemy (center)
    DamageEffect(target="tgt_3c5d", base_damage=15, dealt=15),  # Near-Enemy (center)
    DamageEffect(target="tgt_2b1c", base_damage=15, dealt=7),   # Engaged (edge, 50%)
]
```

**No Automatic Calculation:** DM uses tactical knowledge to determine targets and damage variance.

---

## ML Training Implications

### Training Data Quality

**Current Problem:**
- AoE described in narration, single target in damage field (inconsistent)
- Barriers succeed narratively, no mechanical outcome (incomplete)
- Healing omitted from structured output (missing pattern)

**After This Change:**
- AoE: Clear multi-target pattern in `damage` list
- Protection: Explicit `protection_amount` shows absorption mechanics
- Healing: Structured `healing` list shows healing patterns

**ML Benefits:**
1. **Multi-Target Combat:** LLMs learn when to use AoE vs single-target
2. **Defensive Actions:** LLMs learn barrier effectiveness, duration, positioning
3. **Support Actions:** LLMs learn healing target priority, type selection
4. **Tactical Decisions:** LLMs learn range-band targeting for AoE

### JSONL Event Types

**No new event types needed!**
- AoE damage: Multiple entries in `action_resolution.effects.damage`
- Barriers: In `action_resolution.effects.conditions`
- Healing: In `action_resolution.effects.healing`

**Existing event types handle all new mechanics.**

---

## Implementation Plan

### Phase 1: Schema Changes + Tests (TDD)

**1.1: Write Failing Tests**
- [x] `test_aoe_protection_healing.py` created (117 tests across 6 test classes)
- [ ] Run tests - expect failures (schemas not updated yet)

**1.2: Update Schemas**
- [ ] `action_resolution.py:77-80` - Change `damage` to `List[DamageEffect]`
- [ ] `shared_types.py:199` - Add `protection_amount` to `Condition`
- [ ] `action_resolution.py:115` - Add `healing: List[HealingEffect]`
- [ ] Update schema docstrings with examples

**1.3: Run Tests**
- [ ] Schema tests should pass
- [ ] Processing tests still fail (logic not implemented)

---

### Phase 2: Processing Logic

**2.1: Multi-Target Damage**
- [ ] Update `dm.py:4105-4180` - Iterate `for damage in effects.damage:`
- [ ] Update `dm.py:5674` - Damage validation for list
- [ ] Update `targeting_validation.py:22-113` - Multi-target validation

**2.2: Barrier Interception**
- [ ] Implement `intercept_damage_with_barriers()` in `dm.py`
- [ ] Integrate into damage processing loop
- [ ] Test barrier depletion logic

**2.3: Healing Integration**
- [ ] Implement `apply_healing_effects()` in `dm.py`
- [ ] Call after damage processing
- [ ] Wire up to existing `apply_healing()` in `mechanics.py:3793`

**2.4: Run Tests**
- [ ] All processing tests should pass

---

### Phase 3: Prompts & Documentation

**3.1: Prompt Updates**
- [ ] `dm_combat.yaml:46-86` - Add AoE examples with `List[DamageEffect]`
- [ ] `dm_combat.yaml:63-66` - Expand barrier examples with `protection_amount`
- [ ] `dm_structured_output.yaml` - Update MechanicalEffects documentation

**3.2: Schema Examples**
- [ ] Add AoE grenade example to `MechanicalEffects` docstring
- [ ] Add barrier creation example to `Condition` docstring
- [ ] Add healing example to `MechanicalEffects` docstring

---

### Phase 4: Integration Testing

**4.1: Session Config**
- [ ] Create `session_config_aoe_test.json`
  - Scenario: Combat with grenades, barriers, medic
  - Force combat with 3-4 enemies at different ranges
  - Test multi-round barrier depletion
  - Test healing after damage

**4.2: Run Session**
- [ ] Execute test session
- [ ] Verify JSONL logs contain multi-target damage
- [ ] Verify barrier absorption logged
- [ ] Verify healing logged

**4.3: Validate ML Training Data**
- [ ] Use `analyze_session.py` to check event structure
- [ ] Verify `damage` field is list in all resolutions
- [ ] Verify `protection_amount` in barrier conditions
- [ ] Verify `healing` field populated

---

### Phase 5: Migration & Documentation

**5.1: Update Existing Code**
- [ ] Search codebase for `effects.damage.target` → Update to iterate list
- [ ] Search for `if effects.damage:` → Update to `if effects.damage:`
- [ ] Update replay tools (if they access damage field)

**5.2: Update Documentation**
- [ ] Add to CLAUDE.md under "Critical Patterns"
- [ ] Update ARCHITECTURE.md with AoE/protection/healing flow
- [ ] Create migration guide for future schema changes

**5.3: Regenerate Affected Fixtures**
- [ ] Check `tests/fixtures/sessions/MANIFEST.json` for combat fixtures
- [ ] Regenerate fixtures using replay tool (if needed)
- [ ] Verify fixture diffs show expected changes

---

## Testing Strategy

### Unit Tests (117 tests written)

**Test Coverage:**
- [x] `TestAoEDamageValidation` (7 tests) - Schema validation
- [x] `TestRangeBandAoE` (5 tests) - Tactical module integration
- [x] `TestProtectionBarriers` (7 tests) - Barrier schema
- [x] `TestHealingIntegration` (6 tests) - Healing schema
- [x] `TestDamageInterception` (4 tests) - Barrier logic
- [x] `TestBarrierDuration` (3 tests) - Expiration mechanics
- [x] `TestCombinedEffects` (4 tests) - Multi-feature scenarios

**Test File:** `tests/unit/test_aoe_protection_healing.py` (571 lines)

### Integration Tests (to be written)

**Test Scenarios:**
1. **Grenade vs Crowd:** AoE hits 3 enemies at Near-Enemy, 1 at Engaged (reduced)
2. **Barrier Protection:** Create barrier (10 HP), take 6 damage, barrier at 4, take 5 damage, barrier depleted + 1 HP damage
3. **Medic Rescue:** Ally at 5 HP, 2 stuns, 1 wound → Heal 15 HP, remove 2 stuns → Ally at 20 HP, 0 stuns
4. **Multi-Round Depletion:** Barrier (20 HP, 3 rounds) → Round 1: 8 damage → Round 2: 15 damage (depletes) → Round 3: barrier gone
5. **Combined:** AoE hits 3 targets (2 with barriers, 1 without) → Different damage outcomes → Medic heals all 3

**Test Session Configs:**
- `session_config_aoe_tactical_test.json` - Tactical combat with grenades
- `session_config_barrier_depletion_test.json` - Multi-round barrier test
- `session_config_medic_healing_test.json` - Healing mechanics test

---

## Migration & Backwards Compatibility

### Breaking Changes

**Schema:**
- `MechanicalEffects.damage: Optional[DamageEffect]` → `List[DamageEffect]`

**Code:**
- All references to `effects.damage.target` must change
- All `if effects.damage:` checks remain valid (empty list is falsy)
- All damage processing must iterate list

### Migration Steps

**1. Find All References:**
```bash
grep -r "effects\.damage\." scripts/aeonisk/multiagent/
grep -r "\.damage\.target" scripts/aeonisk/multiagent/
grep -r "\.damage\.dealt" scripts/aeonisk/multiagent/
```

**2. Update Patterns:**
```python
# OLD
if resolution.effects.damage:
    target = resolution.effects.damage.target
    dealt = resolution.effects.damage.dealt

# NEW
for damage in resolution.effects.damage:
    target = damage.target
    dealt = damage.dealt
```

**3. Single-Target Compatibility:**
```python
# For code that must handle both old and new sessions
damages = resolution.effects.damage if isinstance(resolution.effects.damage, list) else [resolution.effects.damage] if resolution.effects.damage else []
```

### Backward Compatibility for Fixtures

**Problem:** Old fixtures have `damage: {target: ..., dealt: ...}`
**Solution:** Pydantic coercion

**Option A:** Add custom validator to coerce single object → list
```python
@field_validator('damage', mode='before')
def coerce_damage_to_list(cls, v):
    if v is None:
        return []
    if isinstance(v, dict):  # Old format
        return [DamageEffect(**v)]
    return v
```

**Option B:** Regenerate all fixtures (preferred)
- Use replay tool to regenerate combat fixtures
- Verify mechanical equivalence with diff tool

**Recommendation:** Option B - clean migration, no tech debt

---

## Edge Cases & Failure Modes

### 1. Multiple Barriers on Same Target

**Scenario:** Target has 2 barriers (10 HP each), takes 15 damage

**Behavior:**
- First barrier absorbs 10 damage (depletes)
- Second barrier absorbs 5 damage (5 HP remaining)
- Target takes 0 HP damage

**Implementation:** Process barriers in FIFO order (order applied)

**Alternative:** Only allow 1 active barrier per target (simpler)
- **Recommendation:** Start with 1 barrier limit for v1.0

---

### 2. AoE Damage Variance Edge Cases

**Scenario:** Grenade hits 5 targets, DM miscalculates margin for one

**Behavior:**
- DM validation catches if `dealt > base_damage + margin`
- DM self-corrects in next generation
- Logs warning but continues (graceful degradation)

**Mitigation:** Existing damage validation logic applies to each entry

---

### 3. Barrier Duration vs Protection Depletion

**Scenario:** Barrier has 10 HP, 3 round duration, takes 5 damage round 1, expires round 4

**Question:** Does barrier expire after 3 rounds OR when depleted?

**Answer:** **BOTH conditions remove barrier:**
- Depleted (`protection_amount = 0`) → Remove immediately
- Expired (`duration = 0`) → Remove end of round
- Whichever happens first

**Implementation:**
```python
# Condition cleanup (existing logic)
agent.conditions = [
    c for c in agent.conditions
    if c.duration > 0 and (c.protection_amount is None or c.protection_amount > 0)
]
```

---

### 4. Healing Overcap

**Scenario:** Target at 15/20 HP, healed for 10 HP

**Behavior:**
- Heals to 20 HP (capped at max_health)
- `HealingEffect.amount = 10` (what was attempted)
- Logs both attempted (10) and actual (5) for ML training

**Implementation:**
```python
actual_healed = min(healing.amount, target.max_health - target.health)
target.health += actual_healed
# Log both healing.amount (intended) and actual_healed
```

---

### 5. AoE with No Valid Targets

**Scenario:** Player throws grenade at "Near-Enemy" but all enemies at Far-Enemy

**Behavior:**
- DM narrates grenade missing
- `effects.damage = []` (empty list)
- No damage logged

**Alternative:** DM fails the action (grenade wasted)

**Recommendation:** DM choice - depends on success margin

---

## Future Enhancements

### 1. Stacking Barriers (v1.1)

**Current:** Single active barrier per target
**Future:** Multiple barriers stack, process in order

**Implementation:**
```python
def intercept_damage_with_barriers_v2(target, damage):
    remaining_damage = damage
    for barrier in target.get_active_protections():
        absorbed = min(barrier.protection_amount, remaining_damage)
        barrier.protection_amount -= absorbed
        remaining_damage -= absorbed
        if remaining_damage <= 0:
            break
    return damage - remaining_damage
```

**Complexity:** Medium (need to track barrier order, update multiple conditions)

---

### 2. Barrier Types (v1.2)

**Proposed:** Barriers with special properties

**Examples:**
- `fire_barrier` - Only blocks fire damage
- `reflective_barrier` - Returns % damage to attacker
- `absorbing_barrier` - Converts absorbed damage to energy

**Implementation:**
```python
class Condition(BaseModel):
    # ... existing fields
    protection_amount: Optional[int] = None
    protection_type: Optional[Literal["physical", "energy", "void", "all"]] = "all"
    reflection_percent: Optional[int] = 0  # % of damage reflected
```

**Complexity:** High (damage type filtering, reflection mechanics)

---

### 3. Auto-Healing Over Time (v1.3)

**Proposed:** Conditions that heal each round (regeneration)

**Examples:**
```python
Condition(
    name="Regeneration",
    penalty=0,
    duration=5,
    description="Heals 3 HP per round",
    healing_per_round=3
)
```

**Implementation:** Process in condition tick phase, generate `HealingEffect`

**Complexity:** Medium (new field, round-based processing)

---

### 4. Medicine Skill Auto-Population (v2.0)

**Proposed:** DM declares "heal action", mechanics layer auto-fills `HealingEffect` based on Medicine check

**Flow:**
1. Player declares: "Use medkit on ally"
2. DM pre-validates: Has medkit? Target wounded?
3. Mechanics rolls Medicine check (DC 15)
4. DM receives: `margin = 8`
5. DM generates: `HealingEffect(amount = 12 + (margin // 2) = 12 + 4 = 16)`

**Implementation:** Requires 'heal' action type and pre-validation (see user's Healing Plan)

**Complexity:** High (new action type, pre-validation, DC tables)

---

## Conclusion

This design integrates three synergistic features:
- **AoE Damage** enables multi-target combat
- **Protection Barriers** enable defensive tactics
- **Healing** enables support roles

**Total Scope:**
- 3 schema files modified
- 4 processing functions (new/updated)
- 2 prompt files updated
- 117 unit tests written
- 5+ integration tests planned

**Estimated Effort:** 8-12 hours implementation + 4-6 hours testing

**Risk Level:** Medium (breaking change, but well-scoped)

**Recommendation:** Proceed with implementation following TDD plan.

---

**Document Version:** 1.0
**Last Updated:** 2025-01-15
**Next Review:** After Phase 1 completion (schema changes + tests)
