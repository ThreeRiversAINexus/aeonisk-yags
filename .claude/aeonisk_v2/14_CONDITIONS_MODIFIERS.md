# P0: Conditions & Modifiers Pipeline Bugs

**Priority:** P0 (mechanical correctness + ML data integrity)
**Branch:** `intention-lethality-mismatch`
**Evidence:** Code audit of condition pipeline from Pydantic schema through extraction, application, and enforcement
**Related specs:** 08_SUPPRESSION (suppression relies heavily on conditions for its mechanical effects)

---

## Problem Statement

Six interconnected bugs in the condition/modifier pipeline render the entire system
mechanically dishonest. Conditions are the primary way the DM applies buffs and
debuffs to agents (Stunned, Pinned, Inspired, Disarmed, etc.), but the pipeline
from Pydantic schema generation → structured_output_helpers extraction → dm.py
application → mechanics.py enforcement is broken at multiple points.

The result: every condition applied in every session is misleadingly described,
never expires, loses its target field, and cannot selectively target specific roll
types despite the mechanics engine supporting it.

This directly corrupts ML training data. JSONL logs record conditions with
descriptions claiming selective effects (e.g., "-3 to attacks") that never actually
happen (the penalty applies to ALL rolls). Condition durations are logged but never
enforced. Training models on this data teaches them that conditions are
cosmetic — their described effects have no relationship to their actual mechanical
impact.

### Bug 1: Misleading Condition Descriptions in Prompt Examples

Five prompt YAML files contain example conditions whose descriptions claim selective
targeting of specific roll types (e.g., "attacks", "Willpower checks", "Perception"),
but the mechanics engine applies the penalty to ALL rolls indiscriminately.

**Affected files and lines:**

| File | Line | Description Claims | Actual Behavior |
|------|------|--------------------|-----------------|
| `dm_resolution_combat.yaml` | 93 | `"dropped weapon, -3 to attacks until retrieved"` | -3 to ALL rolls |
| `dm_resolution_combat_suppression.yaml` | 48 | `"-4 to attacks and defense while pinned down"` | -4 to ALL rolls |
| `dm_resolution_combat_suppression.yaml` | 79 | `"-2 to Willpower checks, morale shaken"` | -2 to ALL rolls |
| `dm_resolution_support.yaml` | 54 | `"stimulant aftereffect, -1 Perception"` | -1 to ALL rolls |
| `schemas/shared_types.py` | 228 | `"+2 to next attack"` | +2 to ALL rolls |

**Impact:** LLMs trained on these examples generate conditions with misleading
descriptions. The DM sees "+2 to next attack" and generates a condition with that
description, but the engine applies +2 to the character's next Willpower check,
Perception roll, and everything else. The JSONL log faithfully records the
misleading description, creating training data where the stated effect contradicts
the mechanical outcome.

### Bug 2: `target` Field Lost During Extraction

The Pydantic `Condition` schema (shared_types.py:237) includes a `target` field
for specifying who receives the condition. However, the extraction step in
`structured_output_helpers.py` (lines 322-328) omits this field when converting
from Pydantic model to the dict consumed by dm.py.

```python
# structured_output_helpers.py lines 322-328 (CURRENT - target and protection_amount omitted)
'conditions': [
    {
        'type': cond.name,
        'penalty': cond.penalty,
        'duration': cond.duration,
        'description': cond.description
    }
    for cond in resolution.effects.conditions
],
```

Downstream in dm.py:5958, `condition_data.get('target')` returns `None` because
the field was never included in the dict. The condition falls back to the
action-level target (dm.py:5960) or defaults to the actor (dm.py:5962).

**Impact:** Multi-target conditions are silently broken. If the LLM generates
`Condition(target="tgt_abc1", ...)` and `Condition(target="tgt_def2", ...)`, both
conditions are applied to the same fallback target instead of their intended
recipients.

### Bug 3: Duration Hardcoded to 3, Never Ticked

Both condition creation sites in dm.py ignore the LLM-specified duration and
hardcode `duration=3`:

```python
# dm.py line 5952 (player action resolution)
duration=3,  # Default duration

# dm.py line 6424 (ritual resolution)
duration=3,  # Default duration
```

Even if the hardcoded value were replaced with the extracted duration, conditions
would still never expire because `tick_conditions()` (mechanics.py:4761) has
**zero production callers**:

```
$ grep -rn tick_conditions
tests/unit/test_mechanics.py:457:    def test_tick_conditions    # Test caller 1
tests/unit/test_mechanics.py:469:        mechanics_engine.tick_conditions  # Test caller 2
tests/unit/test_mechanics.py:486:        mechanics_engine.tick_conditions  # Test caller 3
tests/unit/test_mechanics.py:674:        mechanics_engine.tick_conditions  # Test caller 4
scripts/aeonisk/multiagent/mechanics.py:4761:    def tick_conditions  # Definition only
```

**Impact:** Every condition persists for the entire session regardless of the
LLM-specified duration. A "Stunned for 1 round" debuff remains active until
session end. This makes conditions far more punishing than intended and creates
impossible game states in JSONL logs (a character "stunned for 1 round" still
carrying the stun penalty in round 10).

### Bug 4: `affects` Field Dead Code (Selective Targeting Unused)

The mechanics.py `Condition` dataclass (line 1654) has an `affects: List[str]`
field designed for selective roll targeting:

```python
@dataclass
class Condition:
    name: str
    type: str
    penalty: int
    description: str
    duration: int = -1
    affects: List[str] = field(default_factory=list)  # which attributes/skills affected

    def applies_to(self, attribute: str, skill: Optional[str] = None) -> bool:
        if not self.affects:
            return True  # Affects everything
        if attribute in self.affects:
            return True
        if skill and skill in self.affects:
            return True
        return False
```

This is well-implemented and correctly integrated into roll resolution
(mechanics.py:2088 calls `condition.applies_to(attribute, skill)`). However:

1. **dm.py always passes `affects=[]`** (lines 5953 and 6425), making
   `applies_to()` always return `True`.
2. **The Pydantic Condition schema has no `affects` field** — the LLM cannot
   specify which rolls a condition should target even if the engine supported it.
3. **No extraction** — structured_output_helpers.py doesn't extract an `affects`
   field because the Pydantic schema doesn't define one.

The entire `applies_to()` / `affects` system is dead code in production.

**Impact:** The mechanics engine has a perfectly functional selective targeting
system that is completely bypassed. Every condition affects every roll type.

### Bug 5: `protection_amount` Not Propagated Through Pipeline

The Pydantic `Condition` schema includes `protection_amount: Optional[int]` for
damage-absorbing barriers (shared_types.py:238). The field is fully documented in
the schema with examples and validators. However:

1. **Not extracted** — structured_output_helpers.py:322-328 omits
   `protection_amount` from the condition dict.
2. **No field on dataclass** — The mechanics.py `Condition` dataclass has no
   `protection_amount` field.
3. **dm.py barrier functions expect it** — dm.py lines 101-175 implement barrier
   absorption logic that reads `barrier.protection_amount`, but this only works for
   conditions created directly from Pydantic objects, not conditions that pass
   through the extraction → dict → dataclass pipeline.

**Impact:** If the LLM generates a barrier condition
(`Condition(name="Astral Barrier", protection_amount=10, ...)`), the
`protection_amount` is silently discarded during extraction. The resulting
mechanics.py Condition has no absorption capability. The barrier becomes a regular
condition with `penalty=0` — mechanically useless.

### Bug 6: Two Condition Classes With Divergent Schemas

The system has two `Condition` classes that serve different roles but share the
same name, leading to confusion and data loss during conversion:

| Field | Pydantic (shared_types.py:206) | Dataclass (mechanics.py:1647) | Mapping in dm.py |
|-------|-------------------------------|------------------------------|-------------------|
| `name` | Name of condition | Name of condition | `cond.name` → `name` |
| `type` | *(not present)* | Category (mental_strain, etc.) | `cond.name` → `type` (name used as type!) |
| `penalty` | Roll modifier | Roll modifier | Direct copy |
| `description` | What it does | What it does | Direct copy |
| `duration` | Rounds remaining | Rounds remaining (-1 = permanent) | **Hardcoded to 3** (ignores Pydantic value) |
| `target` | Who receives it | *(not present)* | **Lost during extraction** |
| `protection_amount` | Barrier capacity | *(not present)* | **Lost during extraction** |
| `affects` | *(not present)* | Roll types affected | **Always `[]`** |

The dm.py conversion (lines 5947-5953) maps Pydantic `name` to both dataclass
`name` and `type`, meaning `type` carries no independent information. The three
fields unique to each class (`target`, `protection_amount`, `affects`) are all
silently lost or unused.

---

## Current Implementation

### Condition Pipeline Flow

```
LLM generates Pydantic Condition
    │
    ▼
structured_output_helpers.py:322-328  ← Extracts to dict (LOSES target, protection_amount)
    │
    ▼
Dict: {type, penalty, duration, description}  ← 4 fields only
    │
    ▼
dm.py:5944-5964 / 6416-6436  ← Creates mechanics.py Condition
    │                            (HARDCODES duration=3, affects=[])
    ▼
mechanics.py Condition dataclass  ← Missing target, protection_amount
    │                                affects=[] → applies_to() always True
    ▼
mechanics.py:2086-2095  ← Applies penalty to ALL rolls
    │
    ▼
NEVER TICKED  ← tick_conditions() has 0 production callers
    │
    ▼
Condition persists until session end
```

### Roll Resolution With Conditions (mechanics.py:2080-2095)

```python
# Apply condition penalties and collect modifiers for logging
if agent_id and agent_id in self.conditions:
    for condition in self.conditions[agent_id]:
        if condition.applies_to(attribute, skill):  # Always True when affects=[]
            modifiers[condition.name] = condition.penalty
            modifiers_applied.append(RollModifier(
                source="condition",
                value=condition.penalty,
                details={"name": condition.name}
            ))
```

This code is correct — it properly checks `applies_to()` and logs modifiers. The
bug is upstream: `affects` is never populated, so `applies_to()` is a no-op.

### Condition Creation Sites

**Site 1: Player action resolution (dm.py:5944-5964)**
```python
for condition_data in state_changes.get('conditions', []):
    condition = Condition(
        name=condition_data['type'],       # 'type' key (from extraction mapping)
        type=condition_data['type'],       # Duplicated
        penalty=condition_data['penalty'],
        description=condition_data['description'],
        duration=3,                        # BUG: Hardcoded, ignores condition_data['duration']
        affects=[]                         # BUG: Never populated from LLM output
    )
    target_id = condition_data.get('target')  # BUG: Always None (not extracted)
```

**Site 2: Ritual resolution (dm.py:6416-6436)**
Identical code, same bugs.

### Condition Management (mechanics.py:4735-4775)

```python
def add_condition(self, agent_id, condition):
    # Deduplication by name (correct)
    for existing in self.conditions[agent_id]:
        if existing.name == condition.name:
            return  # Skip duplicate

def tick_conditions(self, agent_id):
    # Decrements duration, removes expired conditions
    # NEVER CALLED IN PRODUCTION
    for condition in self.conditions[agent_id]:
        if condition.duration > 0:
            condition.duration -= 1
            if condition.duration == 0:
                logger.info(f"Condition expired: {condition.name}")
    self.conditions[agent_id] = [
        c for c in self.conditions[agent_id] if c.duration != 0
    ]
```

The tick logic is correct. It just has no callers. The session.py round cleanup
(lines 3203-3224) resets round stats, clears action buffers, and resets free
action slots, but never calls `tick_conditions()`.

---

## Design Decisions

### D1: Fix Extraction to Include All Pydantic Fields

**Decision:** Update `structured_output_helpers.py:322-328` to include `target`
and `protection_amount` in the extracted condition dict.

**Rationale:**
- These fields exist on the Pydantic schema. The LLM generates them. The DM
  prompts show examples with `target=` specified. Silently dropping them is a
  data-loss bug, not a design choice.
- dm.py already has code at line 5958 to read `condition_data.get('target')`. It
  works correctly — it just always gets `None` because extraction dropped the field.
- No schema changes needed. This is a pure extraction fix.

### D2: Use LLM-Specified Duration Instead of Hardcoding 3

**Decision:** Replace `duration=3` with `duration=condition_data.get('duration', 3)`
at both creation sites.

**Rationale:**
- The Pydantic schema has `duration: int = Field(default=1, ge=0)`. The LLM
  specifies durations (1-round stun, 2-round pin, etc.). These values are correctly
  extracted by structured_output_helpers. The dm.py code simply ignores them.
- Default fallback of 3 preserves current behavior for any edge case where duration
  is missing from the dict.

### D3: Add `tick_conditions()` Call to Session Round Cleanup

**Decision:** Call `tick_conditions()` for all active agents at the end of each
round, after all resolutions and state changes are applied but before the next
round begins.

**Rationale:**
- `tick_conditions()` is fully implemented and tested (4 test callers in
  test_mechanics.py). It correctly decrements durations and removes expired
  conditions. It just needs a production caller.
- **Tick granularity: per-round** (not per-action). Per-action ticking would make
  conditions expire too quickly (a 2-round condition used by 4 agents in the round
  would tick 4 times and expire mid-round). Per-round matches the natural YAGS
  round structure and the `duration` field semantics ("lasts N rounds").
- The call site is session.py:3219 (after round summary logging, before clearing
  the action buffer for next round).

### D4: Fix Prompt Descriptions to Match Actual Behavior (Phase 1)

**Decision:** In Phase 1, update all prompt YAML examples to describe conditions
honestly — as affecting "all rolls" rather than claiming selective targeting.

**Rationale:**
- Phase 1 has no schema changes. The engine applies penalties to all rolls. The
  descriptions should match.
- This prevents LLMs from generating misleading descriptions that end up in JSONL
  training data.
- If Phase 3 adds selective targeting, the descriptions can be updated again to
  reflect the new capability.

**Examples of description fixes:**

| Before | After |
|--------|-------|
| `"dropped weapon, -3 to attacks until retrieved"` | `"dropped weapon, -3 to all rolls until retrieved"` |
| `"-4 to attacks and defense while pinned down"` | `"-4 to all actions while pinned down"` |
| `"-2 to Willpower checks, morale shaken"` | `"-2 to all rolls, morale shaken"` |
| `"stimulant aftereffect, -1 Perception"` | `"stimulant aftereffect, -1 to all rolls"` |
| `"+2 to next attack"` | `"+2 to all rolls"` |

### D5: Defer Selective Targeting (Phase 3) With Option Evaluation

**Decision:** Phase 3 is a design decision that should be evaluated after Phase 1
and Phase 2 are stable. Three options:

**Option A: Add `affects` to Pydantic Schema**
- Add `affects: Optional[List[str]] = None` to Pydantic Condition.
- Extract in structured_output_helpers.
- Populate in dm.py when creating mechanics.py Condition.
- The mechanics engine already supports it via `applies_to()`.
- **Pro:** Full selective targeting. LLMs can generate "-3 to attacks" and it works.
- **Con:** LLMs must correctly identify which attributes/skills map to "attacks"
  vs "defense" vs "Willpower checks". Hallucination risk. Requires prompt engineering.

**Option B: Remove `affects` From Dataclass, Simplify to "All Rolls"**
- Delete the `affects` field and `applies_to()` method from the dataclass.
- All conditions affect all rolls (make the code match the behavior).
- Update prompt descriptions permanently (not just Phase 1 workaround).
- **Pro:** Honest, simple, no hallucination risk.
- **Con:** Loses selective targeting capability forever. "Disarmed" affecting
  Willpower checks is weird.

**Option C: Keep Dead Code, Document as Future Work**
- Leave `affects` and `applies_to()` in place but unused.
- Document it as designed-but-not-connected.
- **Pro:** No code changes, preserves optionality.
- **Con:** Dead code accumulates. Future developer assumes it works.

**Recommendation:** Option A in the long term (selective targeting is the correct
YAGS behavior), but only after Spec 08_SUPPRESSION is implemented (suppression
conditions are the primary use case for selective targeting). In the interim,
Phase 1 fixes make the system honest about its limitations.

### D6: Add `protection_amount` to Mechanics Dataclass

**Decision:** Add `protection_amount: Optional[int] = None` to the mechanics.py
`Condition` dataclass. Propagate through extraction and creation.

**Rationale:**
- dm.py already has barrier absorption logic (lines 101-175) that reads
  `barrier.protection_amount`. This logic currently only works for conditions
  created directly from Pydantic objects (bypassing the extraction pipeline).
- Adding the field to the dataclass and extraction makes barriers work through
  the standard pipeline.
- The Pydantic schema already validates `ge=0` on the field.

---

## Proposed Solution

### Phase 1: Immediate Fixes (No Schema Changes)

#### 1.1 Fix Extraction (structured_output_helpers.py)

```python
# structured_output_helpers.py lines 322-328
# BEFORE:
'conditions': [
    {
        'type': cond.name,
        'penalty': cond.penalty,
        'duration': cond.duration,
        'description': cond.description
    }
    for cond in resolution.effects.conditions
],

# AFTER:
'conditions': [
    {
        'type': cond.name,
        'penalty': cond.penalty,
        'duration': cond.duration,
        'description': cond.description,
        'target': cond.target,
        'protection_amount': cond.protection_amount
    }
    for cond in resolution.effects.conditions
],
```

#### 1.2 Fix Duration and Protection in dm.py Condition Creation

Apply to **both** creation sites (dm.py:5947-5953 and dm.py:6419-6425):

```python
# BEFORE:
condition = Condition(
    name=condition_data['type'],
    type=condition_data['type'],
    penalty=condition_data['penalty'],
    description=condition_data['description'],
    duration=3,   # Default duration
    affects=[]    # Affects all by default
)

# AFTER:
condition = Condition(
    name=condition_data['type'],
    type=condition_data['type'],
    penalty=condition_data['penalty'],
    description=condition_data['description'],
    duration=condition_data.get('duration', 3),
    affects=[],  # Phase 3: populate from LLM output
    protection_amount=condition_data.get('protection_amount')
)
```

#### 1.3 Add `protection_amount` to Mechanics Condition Dataclass

```python
# mechanics.py Condition dataclass
# BEFORE:
@dataclass
class Condition:
    name: str
    type: str
    penalty: int
    description: str
    duration: int = -1
    affects: List[str] = field(default_factory=list)

# AFTER:
@dataclass
class Condition:
    name: str
    type: str
    penalty: int
    description: str
    duration: int = -1
    affects: List[str] = field(default_factory=list)
    protection_amount: Optional[int] = None
```

#### 1.4 Fix Misleading Prompt Descriptions

Update all five locations to describe conditions honestly:

**dm_resolution_combat.yaml:89-94:**
```yaml
# BEFORE:
conditions=[Condition(
    name="Disarmed",
    penalty=-3,
    duration=1,
    description="dropped weapon, -3 to attacks until retrieved",
    target="tgt_7a3f"
)]

# AFTER:
conditions=[Condition(
    name="Disarmed",
    penalty=-3,
    duration=1,
    description="dropped weapon, -3 to all rolls until retrieved",
    target="tgt_7a3f"
)]
```

**dm_resolution_combat_suppression.yaml:44-49:**
```yaml
# BEFORE:
conditions=[Condition(
    name="Pinned",
    penalty=-4,
    duration=1,
    description="-4 to attacks and defense while pinned down",
    target="tgt_7a3f"
)]

# AFTER:
conditions=[Condition(
    name="Pinned",
    penalty=-4,
    duration=1,
    description="-4 to all actions while pinned down",
    target="tgt_7a3f"
)]
```

**dm_resolution_combat_suppression.yaml:76-80:**
```yaml
# BEFORE:
Condition(
    name="Shaken",
    penalty=-2,
    duration=1,
    description="-2 to Willpower checks, morale shaken",
    target="tgt_2k9m"
)

# AFTER:
Condition(
    name="Shaken",
    penalty=-2,
    duration=1,
    description="-2 to all rolls, morale shaken",
    target="tgt_2k9m"
)
```

**dm_resolution_support.yaml:50-54:**
```yaml
# BEFORE:
conditions=[Condition(
    name="Jittery",
    penalty=-1,
    duration=1,
    description="stimulant aftereffect, -1 Perception",
    target="tgt_ash"
)]

# AFTER:
conditions=[Condition(
    name="Jittery",
    penalty=-1,
    duration=1,
    description="stimulant aftereffect, -1 to all rolls",
    target="tgt_ash"
)]
```

**schemas/shared_types.py:228:**
```python
# BEFORE:
- Condition(name="Inspired", penalty=2, duration=3, description="+2 to next attack")

# AFTER:
- Condition(name="Inspired", penalty=2, duration=3, description="+2 to all rolls for 3 rounds")
```

### Phase 2: Duration Ticking

#### 2.1 Add `tick_conditions()` to Session Round Cleanup

Insert after round summary logging (session.py:3201) and before clearing the
action buffer (session.py:3219):

```python
# session.py, after round summary logging, before action buffer clear
# Tick condition durations for all agents
mechanics = self.shared_state.get_mechanics_engine()
if mechanics:
    all_agent_ids = list(mechanics.conditions.keys())
    for agent_id in all_agent_ids:
        mechanics.tick_conditions(agent_id)
```

**Tick granularity:** Per-round. Each condition's duration decrements by 1 at the
end of every round. A condition with `duration=2` lasts for the round it was
applied and one additional round, then expires at the end of that round.

**Edge cases:**
- `duration=0` in Pydantic schema means "instant / already applied" — these should
  be immediately removed after creation. The current `tick_conditions()` already
  handles this: `if condition.duration == 0` triggers removal.
- `duration=-1` in the dataclass means "until resolved" (permanent). The current
  `tick_conditions()` correctly skips these: `if condition.duration > 0` excludes
  negative values.
- New conditions applied mid-round: They will be ticked at the end of that same
  round. A `duration=1` condition applied in round 3 will be removed at end of
  round 3. This is consistent: "lasts 1 round" means "lasts the current round."

#### 2.2 Log Condition Expiry

When `tick_conditions()` removes an expired condition, log it to JSONL for ML
training data:

```python
def tick_conditions(self, agent_id: str):
    if agent_id not in self.conditions:
        return

    expired = []
    for condition in self.conditions[agent_id]:
        if condition.duration > 0:
            condition.duration -= 1
            if condition.duration == 0:
                logger.info(f"Condition expired: {condition.name} for {agent_id}")
                expired.append(condition.name)

    self.conditions[agent_id] = [
        c for c in self.conditions[agent_id] if c.duration != 0
    ]
    return expired  # Caller can log these
```

The session.py caller logs expired conditions:

```python
for agent_id in all_agent_ids:
    expired = mechanics.tick_conditions(agent_id)
    if expired:
        logger.info(f"Conditions expired for {agent_id}: {', '.join(expired)}")
```

### Phase 3: Selective Targeting (Deferred — Design Decision)

Phase 3 adds the ability for conditions to selectively target specific roll types
(e.g., "Disarmed" only affects attack rolls, not Willpower checks). This requires:

1. Add `affects: Optional[List[str]] = None` to Pydantic Condition schema.
2. Extract `affects` in structured_output_helpers.py.
3. Populate `affects` in dm.py condition creation.
4. Update prompt examples to use the field.
5. Define the vocabulary of valid `affects` values (attribute names? skill names?
   categories like "attack"/"defense"?).

**Prerequisite:** Spec 08_SUPPRESSION should be implemented first, as suppression
conditions ("Pinned") are the primary use case for selective targeting. The
suppression design will inform which `affects` vocabulary is most useful.

**Not blocking:** Phase 1 and Phase 2 are complete without Phase 3. The system
will honestly apply all conditions to all rolls, with correct durations and
correct targeting. Phase 3 adds granularity, not correctness.

---

## Files to Modify

### Phase 1

| File | Lines | Change |
|------|-------|--------|
| `structured_output_helpers.py` | 322-328 | Add `target` and `protection_amount` to condition extraction dict |
| `dm.py` | 5952 | Replace `duration=3` with `condition_data.get('duration', 3)` |
| `dm.py` | 5953 | Add `protection_amount=condition_data.get('protection_amount')` |
| `dm.py` | 6424 | Replace `duration=3` with `condition_data.get('duration', 3)` |
| `dm.py` | 6425 | Add `protection_amount=condition_data.get('protection_amount')` |
| `mechanics.py` | 1647-1654 | Add `protection_amount: Optional[int] = None` to Condition dataclass |
| `dm_resolution_combat.yaml` | 93 | Fix description: "attacks" → "all rolls" |
| `dm_resolution_combat_suppression.yaml` | 48 | Fix description: "attacks and defense" → "all actions" |
| `dm_resolution_combat_suppression.yaml` | 79 | Fix description: "Willpower checks" → "all rolls" |
| `dm_resolution_support.yaml` | 54 | Fix description: "Perception" → "all rolls" |
| `schemas/shared_types.py` | 228 | Fix example description: "next attack" → "all rolls" |

### Phase 2

| File | Lines | Change |
|------|-------|--------|
| `session.py` | ~3219 | Add `tick_conditions()` call for all agents at end of round |
| `mechanics.py` | 4761-4775 | Return expired condition names from `tick_conditions()` |

### Phase 3 (Deferred)

| File | Change |
|------|--------|
| `schemas/shared_types.py` | Add `affects: Optional[List[str]]` to Pydantic Condition |
| `structured_output_helpers.py` | Extract `affects` field |
| `dm.py` | Populate `affects` in Condition creation |
| All prompt YAMLs | Update descriptions to claim selective targeting (once it works) |

---

## Test Plan (TDD)

### Phase 1 Tests

#### Test Class: `TestConditionExtraction` (test_condition_extraction.py)

```python
class TestConditionExtraction:
    """Verify structured_output_helpers extracts all Pydantic Condition fields."""

    def test_extraction_includes_target(self):
        """Condition with target field should preserve target in extracted dict."""
        # Create Pydantic Condition with target="tgt_abc1"
        # Extract via structured_output_helpers
        # Assert extracted dict has 'target': 'tgt_abc1'

    def test_extraction_includes_protection_amount(self):
        """Condition with protection_amount should preserve it in extracted dict."""
        # Create Pydantic Condition with protection_amount=10
        # Extract via structured_output_helpers
        # Assert extracted dict has 'protection_amount': 10

    def test_extraction_target_none_when_not_specified(self):
        """Condition without target should have target=None in extracted dict."""
        # Create Pydantic Condition without target
        # Extract via structured_output_helpers
        # Assert extracted dict has 'target': None

    def test_extraction_protection_none_when_not_specified(self):
        """Condition without protection_amount has protection_amount=None."""
        # Create Pydantic Condition without protection_amount
        # Assert extracted dict has 'protection_amount': None
```

#### Test Class: `TestConditionDurationFromLLM` (test_condition_duration.py)

```python
class TestConditionDurationFromLLM:
    """Verify dm.py uses LLM-specified duration instead of hardcoding 3."""

    def test_duration_from_extracted_data(self):
        """Condition creation should use duration from extracted dict."""
        # Provide condition_data with duration=1
        # Create Condition via dm.py logic
        # Assert condition.duration == 1 (not 3)

    def test_duration_fallback_to_3_when_missing(self):
        """If duration missing from extracted data, default to 3."""
        # Provide condition_data without duration key
        # Create Condition via dm.py logic
        # Assert condition.duration == 3

    def test_duration_zero_is_instant(self):
        """Duration=0 from LLM means instant/already applied."""
        # Provide condition_data with duration=0
        # Create Condition
        # Assert condition.duration == 0
```

#### Test Class: `TestConditionDataclassProtection` (test_condition_protection.py)

```python
class TestConditionDataclassProtection:
    """Verify mechanics.py Condition dataclass has protection_amount."""

    def test_condition_default_no_protection(self):
        """Condition created without protection_amount defaults to None."""
        condition = Condition(name="Stunned", type="stun", penalty=-3,
                            description="stunned")
        assert condition.protection_amount is None

    def test_condition_with_protection_amount(self):
        """Condition can be created with protection_amount."""
        condition = Condition(name="Barrier", type="barrier", penalty=0,
                            description="barrier", protection_amount=10)
        assert condition.protection_amount == 10
```

### Phase 2 Tests

#### Test Class: `TestConditionTicking` (test_condition_ticking.py)

```python
class TestConditionTicking:
    """Verify conditions are ticked at end of each round in session."""

    def test_tick_called_at_round_end(self):
        """tick_conditions() is called for each agent at end of round."""
        # Mock mechanics engine
        # Run one round
        # Assert tick_conditions was called for each agent

    def test_condition_expires_after_duration(self):
        """A condition with duration=2 should expire after 2 rounds."""
        # Add condition with duration=2
        # Tick once: condition still present, duration=1
        # Tick twice: condition removed

    def test_permanent_condition_not_ticked(self):
        """A condition with duration=-1 persists through ticking."""
        # Add condition with duration=-1
        # Tick multiple times
        # Condition still present

    def test_tick_returns_expired_names(self):
        """tick_conditions() returns list of expired condition names."""
        # Add condition with duration=1
        # Tick once
        # Assert return value includes expired condition name

    def test_zero_duration_removed_immediately(self):
        """Duration=0 condition removed on first tick."""
        # Add condition with duration=0
        # Tick once
        # Condition removed
```

### Existing Tests to Verify (No Changes)

The following existing tests in `test_mechanics.py` already test the core
condition logic and should continue to pass after all phases:

- `test_add_condition` (line ~440) — condition creation and deduplication
- `test_remove_condition` (line ~450) — explicit condition removal
- `test_tick_conditions` (line ~457) — duration decrement and expiry
- `test_condition_effects_on_rolls` (line ~665) — penalty application during rolls

---

## Dependencies

### Internal Dependencies

- **None for Phase 1 and Phase 2.** These are standalone fixes to the existing
  pipeline with no dependencies on other specs.

### Dependencies ON This Spec

- **08_SUPPRESSION_NONLETHAL** — Suppression relies on conditions (Pinned, Shaken,
  Suppressed) as its primary mechanical output. Correct condition duration and
  application are prerequisites for suppression to work as designed.

- **01_NPC_COMBAT** — If NPCs are routed through the combat pipeline (Spec 01),
  they will need conditions applied correctly during NPC combat resolution.

### Backward Compatibility

- **Phase 1:** Existing conditions change from hardcoded duration=3 to
  LLM-specified durations. Default fallback is still 3, so conditions that were
  previously created without explicit duration continue to work. Extraction adds
  new fields to the dict but doesn't remove existing ones.

- **Phase 2:** Conditions that currently persist forever will now expire. This
  changes game behavior. Conditions that were "accidentally permanent" will now
  expire as intended. Any sessions that rely on permanent conditions should use
  `duration=-1` (which is respected by `tick_conditions()`). Since LLMs generate
  `duration=1` by default in the Pydantic schema, this change makes the system
  more honest, not more restrictive.

- **Phase 3:** Would add a new optional field to the Pydantic schema. LLMs that
  don't populate it get `affects=None` → `affects=[]` → all rolls (current
  behavior). No breakage.

---

## Open Questions

### Q1: Should Phase 2 Ticking Log a JSONL Event?

**Context:** When a condition expires, should we emit a new JSONL event type
(e.g., `condition_expired`) or extend `action_resolution` context?

**Options:**
- **A: New event type `condition_expired`** — Clean, explicit, easy to query.
  Adds a new event type to the logging schema (requires LOGGING_IMPLEMENTATION.md
  update).
- **B: Log in `round_summary`** — Add expired conditions to the round summary
  dict. No new event type. Less discoverable.
- **C: Python logger only** — Don't emit JSONL, just log to game.log. Simple
  but loses ML training signal.

**Recommendation:** Option A for ML training value (knowing when conditions expire
is useful for learning condition impact). But this can be deferred to Phase 2
implementation.

### Q2: Should Duration Tick Before or After Round Synthesis?

**Context:** If a condition expires at the end of a round, should the DM's
RoundSynthesis narrative reference the condition as still active or already
expired?

**Options:**
- **A: Tick after synthesis** — DM sees condition as active during synthesis,
  narrates accordingly, then it expires. Player sees "the stun wears off" in next
  round's narration.
- **B: Tick before synthesis** — DM sees condition as expired, can narrate the
  recovery. More natural storytelling.

**Recommendation:** Option A (tick after synthesis). The DM should narrate the
current state, not the upcoming state. The condition is mechanically active during
the round and expires at the end. This matches YAGS round semantics.

### Q3: Should We Unify the Two Condition Classes?

**Context:** Having Pydantic and dataclass Condition classes with divergent schemas
is a source of bugs. Should Phase 1 unify them?

**Options:**
- **A: Replace dataclass with Pydantic** — mechanics.py uses the Pydantic
  Condition directly. Eliminates conversion step. Risk: mechanics.py has no other
  Pydantic dependencies, introducing one creates coupling.
- **B: Keep both, align fields** — Add missing fields to dataclass
  (`protection_amount`). Keep Pydantic for LLM validation, dataclass for engine.
  Risk: Fields can drift again.
- **C: Defer to future refactor** — Phase 1 adds `protection_amount` to dataclass
  (minimum fix). Full unification is a larger architectural decision.

**Recommendation:** Option B for Phase 1 (add `protection_amount`, keep both
classes but aligned). Option A is the right long-term answer but requires broader
refactoring of mechanics.py's data layer.

### Q4: Phase 3 Vocabulary — What Values Should `affects` Accept?

**Context:** If we add `affects` to the Pydantic schema, what strings are valid?

**Options:**
- **A: Attribute names** — `["Perception", "Dexterity", "Strength"]`. Maps directly
  to `applies_to(attribute)`. LLMs must know YAGS attributes.
- **B: Skill names** — `["Guns", "Melee", "Athletics"]`. Maps to
  `applies_to(skill=)`. More specific but larger vocabulary.
- **C: Category labels** — `["attack", "defense", "social", "perception"]`. Easier
  for LLMs, but requires a mapping layer from categories to attributes/skills.
- **D: Mixed** — Allow both attribute and skill names. Flexible but potentially
  confusing.

**Recommendation:** Defer until Spec 08_SUPPRESSION defines which conditions need
selective targeting. The suppression design will clarify the vocabulary needs.

### Q5: Should `protection_amount` Depletion Remove the Condition?

**Context:** When a barrier's `protection_amount` reaches 0 after absorbing damage,
should the condition be automatically removed?

**Current behavior:** dm.py:165 calls `remove_condition()` when
`barrier.protection_amount <= 0`. This works for barriers managed through the
dm.py path but not through the standard `tick_conditions()` cleanup.

**Recommendation:** Yes, add a check to `tick_conditions()` or a separate
`cleanup_depleted_barriers()` method. But this can be handled during Phase 1
implementation rather than being a blocking design question.

### Q6: How Do Conditions Interact With Enemy Combat?

**Context:** Enemy agents resolve combat through `enemy_combat.py:_execute_attack()`,
which uses its own roll resolution path. Does this path check conditions?

**Current status:** Enemy combat calls `mechanics.resolve_action()` which calls
`_check_and_apply_roll()` (mechanics.py:2080) which checks conditions. So enemy
rolls ARE affected by conditions — the same `applies_to()` logic applies. This is
correct and should continue to work after Phase 1 fixes.

**No changes needed.** Just documenting that the fix automatically applies to both
PC and enemy resolution paths.
