# Bond System Design & Implementation

**Status:** Core mechanics complete (71 tests passing)
**Implementation Date:** 2025-01-24
**Branch:** `bulk-generation`

---

## Overview

The Bond system implements formal metaphysical connections between characters (and rarely, objects/entities) in Aeonisk. Bonds provide mechanical benefits, integrate with the Void corruption system, and create emergent narrative tension through automatic status transitions.

**Core Principle:** Bonds are tracked via Pydantic structured output, NOT keyword detection. All bond mechanics use schemas, validation, and explicit LLM-generated data.

---

## Schemas & Data Models

### Bond (shared_types.py)

```python
class Bond(BaseModel):
    bond_id: str                           # Unique identifier
    character_a: str                       # First participant
    character_b: str                       # Second participant (character/object/entity)
    bond_type: BondType                    # Kinship/Ascendancy/Debt/Voidward/Passion/Faction
    status: BondStatus                     # Active/Dormant/Severed/Void-Locked
    formed_round: int                      # When bond was created (0 = pre-story)
    witnessed_by: List[str]                # Witnesses (empty = taboo bond)
    bond_target_type: BondTargetType       # Character/Object/Entity (default: CHARACTER)
    codex_registered: bool                 # Officially registered (default: True)
    narrative_description: str             # How bond formed (LLM-generated for pre-story)
```

### Enums

**BondType** (6 types from lore):
- `KINSHIP` - Family bonds (Matron bonds, siblings, chosen family)
- `ASCENDANCY` - Subordination to higher Will (mentor, master, deity)
- `DEBT` - Spiritual/material obligation (ACG debt contracts)
- `VOIDWARD` - Alignment with Void forces (Tempest pacts, Dissolution theorists)
- `PASSION` - Emotional/creative entanglement (lovers, rivals, artists)
- `FACTION` - Institutional allegiance (Pantheon, ACG, Freeborn collectives)

**BondStatus** (4 states):
- `ACTIVE` - Full mechanical benefits (default)
- `DORMANT` - Strained or Void ≥ 7, no benefits (recoverable)
- `SEVERED` - Broken via sacrifice (-2 Soulcredit, requires cleansing ritual to restore)
- `VOID_LOCKED` - Void = 10 corruption, **permanent** (cannot recover)

**BondTargetType** (3 targets):
- `CHARACTER` - Standard character-character bond (99% of bonds)
- `OBJECT` - Rare/taboo bond with object (e.g., sanitation automata)
- `ENTITY` - Rare bond with non-character sapient (AI overseer, Tempest entity)

---

## Bond Formation

### Requirements

1. **Intimacy Ritual skill check** (Empathy × Intimacy Ritual + d20)
2. **Witnessed by ≥1 character** (standard practice, unwitnessed bonds are taboo)
3. **Codex registration** (Sovereign Nexus spiritual ledger)
4. **Both participants Void < 7** (cannot form if corrupted)

### Limits

- **Maximum 3 Bonds per character**
- **Freeborn origin: Maximum 1 Bond** (due to social rejection)
- **Dormant/Severed bonds count toward limit** (occupy "bond slots")

### Validation (`validate_bond_formation()`)

```python
result = mechanics.validate_bond_formation(
    character_name="Alice",
    target_name="Bob",
    character_bonds=alice.bonds,
    character_void=3,
    target_void=2,
    origin="standard",  # or "freeborn"
    witnesses=["Charlie", "Dana"]
)

# Returns: {'valid': bool, 'errors': dict, 'warnings': dict}
```

**Validation checks:**
- Bond limit (3 max, 1 for Freeborn)
- Void prerequisites (< 7 for both)
- Duplicate prevention (no re-bonding existing partners)
- Severed bond prevention (requires cleansing ritual first)
- Witnessed requirement (warning if empty)

### Action Routing

**RitualAction schema:**
```python
action = RitualAction(
    intent="Form a kinship bond with Bob through witnessed oath",
    bond_formation_target="Bob Karsel",  # Optional field
    has_offering=True,
    ...
)
```

**ActionRouter keywords:**
- "form a bond", "form bond", "create bond", "bond with"
- "bonding ritual", "oath with", "swear bond", "forge bond"

Routes to: `Empathy × Intimacy Ritual` (or unskilled Empathy if skill missing)

---

## Mechanical Benefits

### 1. Ritual Bonus (+2)

**When:** Performing rituals with bonded partner present
**Benefit:** +2 to Ritual Roll
**Stacking:** No (max +2 even with multiple bonded participants)

```python
bonus = mechanics.get_bond_ritual_bonus(
    caster_name="Alice",
    caster_bonds=alice.bonds,
    participants=["Bob", "Charlie"]  # Bob is bonded
)
# Returns: 2 if Bob is bonded partner with ACTIVE status, else 0
```

### 2. Soak Bonus (+1)

**When:** Defending bonded partner from attacks
**Benefit:** +1 Soak
**Condition:** Only applies when attacker targets bonded partner (NOT defender)

```python
bonus = mechanics.get_bond_soak_bonus(
    defender_name="Alice",
    defender_bonds=alice.bonds,
    attacker_target="Bob"  # Bob is being attacked
)
# Returns: 1 if Bob is bonded partner with ACTIVE status, else 0
```

### 3. Bond Sacrifice

**Trigger:** Once per session per bond (player choice)
**Benefit:** +5 to current Willpower-based roll
**Costs:**
- Bond status → SEVERED (cannot re-form without cleansing ritual)
- +1 Void
- +1 Soul Debt (owed to severed partner)
- -1 Empathy penalty for the scene

```python
result = mechanics.process_bond_sacrifice(
    character_name="Alice",
    character_bonds=alice.bonds,
    bond_target="Bob",
    current_round=5
)

# Returns: {
#   'success': bool,
#   'willpower_bonus': 5,
#   'void_change': 1,
#   'soul_debt_target': "Bob",
#   'soul_debt_change': 1,
#   'empathy_penalty': -1,
#   'empathy_condition': {...},
#   'bond_status': BondStatus.SEVERED,
#   'narrative': "..."
# }
```

**Strategic implications:**
- **Risk-reward calculation:** +5 bonus can turn critical failures into successes
- **Void threshold danger:** If at Void 6, sacrifice pushes to Void 7 → ALL bonds go Dormant
- **Soul Debt leverage:** Severed partner gains spiritual leverage (future narrative hook)
- **Empathy penalty:** Social actions weakened for rest of scene

---

## Bond Status Tracking

### Automatic Transitions (`check_bond_dormancy()`)

Called after Void score changes (void_changes applied, ritual outcomes, etc.)

**Void ≥ 7: ACTIVE → DORMANT**
- Trigger: Character reaches Void threshold
- Effect: All ACTIVE bonds become DORMANT (no mechanical benefits)
- Recoverable: Yes (when Void drops below 7)

**Void < 7: DORMANT → ACTIVE**
- Trigger: Character cleanses Void below threshold
- Effect: All DORMANT bonds reactivate (benefits restored)
- Narrative: "Warmth floods back, connections surge to life..."

**Void = 10: ACTIVE/DORMANT → VOID_LOCKED**
- Trigger: Character hits maximum Void corruption
- Effect: All non-severed bonds become VOID_LOCKED
- Recoverable: **NO** (permanent corruption, even if Void cleanses to 0)
- Narrative: "The bonds twist and corrupt, blackened by void energy..."

### Transition Logic

```python
result = mechanics.check_bond_dormancy(
    character_name="Alice",
    character_bonds=alice.bonds,
    current_void=7,    # Just reached threshold
    previous_void=6
)

# Returns: {
#   'status_changed': True,
#   'transitions': 2,        # ACTIVE → DORMANT count
#   'reactivations': 0,      # DORMANT → ACTIVE count
#   'void_locked': False,    # VOID_LOCKED count
#   'changes': [             # For JSONL logging
#       {
#           'bond_id': "bond_001",
#           'character_a': "Alice",
#           'character_b': "Bob",
#           'old_status': BondStatus.ACTIVE,
#           'new_status': BondStatus.DORMANT,
#           'reason': "void_threshold",
#           'void_score': 7
#       },
#       ...
#   ]
# }
```

### Status Transition Rules

| Current Status | Void ≥ 7 | Void < 7 | Void = 10 | Notes |
|----------------|----------|----------|-----------|-------|
| ACTIVE         | → DORMANT | No change | → VOID_LOCKED | Benefits lost at threshold |
| DORMANT        | No change | → ACTIVE | → VOID_LOCKED | Reactivates when cleansed |
| SEVERED        | No change | No change | No change | Requires cleansing ritual to restore |
| VOID_LOCKED    | No change | No change | No change | **Permanent** corruption |

---

## DM Integration

### RoundSynthesis Schema

```python
class BondStatusChange(BaseModel):
    character_name: str
    bond_partner: str
    bond_type: Literal["kinship", "ascendancy", "debt", "voidward", "passion", "faction"]
    old_status: Literal["active", "dormant", "severed", "void_locked"]
    new_status: Literal["active", "dormant", "severed", "void_locked"]
    trigger: Literal["void_threshold", "void_recovery", "void_corruption", "sacrifice", "manual"]
    void_score: int
    narrative: str  # 20-300 chars, emotional/sensory description
```

```python
synthesis = RoundSynthesis(
    narration="...",
    bond_status_changes=[
        BondStatusChange(
            character_name="Alice Vex",
            bond_partner="Bob Karsel",
            bond_type="kinship",
            old_status="active",
            new_status="dormant",
            trigger="void_threshold",
            void_score=7,
            narrative="Alice's bond with Bob strains under void corruption, warmth fading to distant cold"
        )
    ],
    ...
)
```

### DM Prompts (TODO)

- **dm_bond_formation.yaml** - How to adjudicate bond formation rituals
- **dm_bond_status.yaml** - When to suggest bond strain/severance
- **dm_bond_context.yaml** - Include party bond matrix in DM context

---

## Pre-Story Bond Matrix (Hybrid Approach)

### Session Config Format

```json
{
  "starting_bonds": [
    {
      "character_a": "Sera Karsel",
      "character_b": "Thane Vael",
      "bond_type": "kinship",
      "relationship_hint": "Matron bond (mothers to same child)"
    },
    {
      "character_a": "Ash Vex",
      "character_b": "Kael Rift",
      "bond_type": "passion",
      "relationship_hint": "Former rivals, competitive respect"
    }
  ]
}
```

### LLM Backstory Generation (TODO)

**bond_backstory_generator.py:**
1. Load session config with `starting_bonds`
2. Feed character sheets + bond structure to LLM
3. Generate narrative description of how each bond formed:
   - Witness details (who, where, when)
   - Oath spoken (exact words if ceremonial)
   - Emotional context (why they bonded)
4. Store in `Bond.narrative_description` field
5. Log to JSONL as `event_type: bond_backstory`

**Design choice:** Config defines structure (who, type), LLM generates flavor (how, why)

---

## Testing

### Test Coverage (71 tests passing)

**test_bond_schema.py** (23 tests):
- Bond model validation
- BondType, BondStatus, BondTargetType enums
- Character-character bonds
- Object bonds (rare/taboo)
- Default values

**test_bond_formation_validation.py** (17 tests):
- Bond limit enforcement (3 max, Freeborn 1)
- Void prerequisites (< 7)
- Duplicate prevention
- Witnessed requirement
- Complex validation scenarios

**test_bond_benefits.py** (17 tests):
- Ritual bonus (+2)
- Soak bonus (+1)
- Bond sacrifice mechanic
- Benefits only apply to ACTIVE bonds

**test_bond_status_tracking.py** (14 tests):
- Void 7 dormancy
- Void recovery reactivation
- Void 10 locking (permanent)
- Complex transition trajectories
- JSONL change tracking

### Test Session Configs (TODO)

- `session_config_bond_formation_test.json` - Empty matrix, form bonds during play
- `session_config_bond_matrix_test.json` - Pre-story bonds with backstories
- `session_config_bond_sacrifice_test.json` - Test sacrifice mechanic

---

## CLAUDE.md Patterns (TODO)

### Bond Formation

```python
# ✅ CORRECT: Detect bond formation via intent keywords
if any(kw in intent_lower for kw in BOND_FORMATION_KEYWORDS):
    return ('Empathy', 'Intimacy Ritual', 'Bond formation ritual')

# ❌ WRONG: Keyword detection in narration
if 'bond' in dm_narration:  # DON'T DO THIS
    create_bond()
```

### Bond Benefits

```python
# ✅ CORRECT: Check bond status before applying bonus
bonus = mechanics.get_bond_ritual_bonus(caster_name, caster_bonds, participants)
total_bonus += bonus

# ❌ WRONG: Hardcoded +2 bonus without checking bond status
if 'Bob' in participants:  # DON'T DO THIS
    total_bonus += 2
```

### Bond Status Tracking

```python
# ✅ CORRECT: Call check_bond_dormancy after Void changes
if void_changed:
    result = mechanics.check_bond_dormancy(
        character_name, character_bonds, current_void, previous_void
    )
    if result['status_changed']:
        # Log to JSONL, add to RoundSynthesis.bond_status_changes
```

---

## Files Modified/Created

### Core Implementation
- `scripts/aeonisk/multiagent/schemas/shared_types.py` - Bond, BondType, BondStatus, BondTargetType
- `scripts/aeonisk/multiagent/schemas/player_action.py` - RitualAction.bond_formation_target
- `scripts/aeonisk/multiagent/schemas/story_events.py` - BondStatusChange, RoundSynthesis.bond_status_changes
- `scripts/aeonisk/multiagent/player.py` - CharacterState.bonds (List[Bond])
- `scripts/aeonisk/multiagent/mechanics.py` - validate_bond_formation(), get_bond_ritual_bonus(), get_bond_soak_bonus(), process_bond_sacrifice(), check_bond_dormancy()
- `scripts/aeonisk/multiagent/action_router.py` - BOND_FORMATION_KEYWORDS, bond formation routing
- `scripts/aeonisk/multiagent/session.py` - Bond serialization to JSONL

### Tests
- `tests/unit/test_bond_schema.py` (23 tests)
- `tests/unit/test_bond_formation_validation.py` (17 tests)
- `tests/unit/test_bond_benefits.py` (17 tests)
- `tests/unit/test_bond_status_tracking.py` (14 tests)

### Documentation
- `.claude/BOND_SYSTEM_DESIGN.md` (this file)

---

## Implementation Status

### ✅ Complete (Phases 1-4)

- [x] Core schemas (Bond, enums)
- [x] Character state integration
- [x] Bond formation validation
- [x] RitualAction extension
- [x] Action router detection
- [x] Ritual bonus (+2)
- [x] Soak bonus (+1)
- [x] Bond sacrifice mechanic
- [x] Status tracking (Dormant/Void-Locked)
- [x] RoundSynthesis integration (BondStatusChange)

### ⏳ Remaining (Phases 5-8)

- [ ] Session config bond loading
- [ ] LLM backstory generation
- [ ] DM prompts (bond formation, bond status)
- [ ] DM context (bond matrix visibility)
- [ ] Integration tests
- [ ] Test session configs
- [ ] CLAUDE.md pattern documentation

### Progress: ~50% Complete

**Core mechanics done.** The foundation is solid with 71 passing tests. Remaining work is integration (DM prompts, pre-story matrix) and polish (docs, integration tests).

---

## Design Insights

### Why This Works

1. **Structured Output Philosophy:** Bonds use Pydantic schemas, not keyword detection. The LLM generates `BondStatusChange` objects, not "Alice's bond seems strained..." narrative text that we parse.

2. **Emergent Tragedy:** The Void 7 threshold creates automatic dramatic tension. Characters don't *choose* when bonds go Dormant—it's a mechanical consequence of corruption. This creates emergent "oh no" moments.

3. **Permanent Scars:** Void 10 → VOID_LOCKED is irreversible. This gives weight to max Void corruption beyond just mechanical penalties. It's a narrative scar that persists even after cleansing.

4. **Strategic Sacrifice:** Bond sacrifice isn't just "+5 bonus"—it's a Sophie's Choice. The Void cost can trigger cascading bond loss (Void 6 → 7 from sacrifice = ALL bonds go Dormant).

5. **Bond Types for ML Training:** The 6 bond types give AI agents semantic hooks. A Passion bond might be sacrificed in a moment of desperation, but a Kinship bond? That's a harder call. The AI learns to weigh these differently.

### Why Bonded Weapons Aren't Bonds

**Critical distinction:** "Bonded weapons" (attuned gear, +1 Attack) are NOT capital-B Bonds. They're:
- Weapon attunement (Attunement ritual skill)
- Unlimited (no 3-bond limit)
- Monthly maintenance required
- Loss = -2 to Ritual Rolls if Primary Ritual Item

This prevents confusion: "Can I bond with my sword?" → "You can attune it (weapon property), but that's not a metaphysical Bond (character connection)."

### Future Enhancements (Maybe)

1. **Type-Specific Mechanics:** Right now all bond types give same benefits. Could add:
   - Voidward bonds: Corrupt slower (Void 8 threshold instead of 7?)
   - Ascendancy bonds: +2 to rolls when following bond partner's orders?
   - Debt bonds: Can transfer Soul Debt via bond?

2. **Bond Restoration Rituals:** Severed bonds require cleansing ritual to restore. Could formalize this:
   - Intimacy Ritual check (DC 20)
   - Requires offering + both participants Void < 5
   - -1 Soulcredit cost to both participants

3. **Void-Locked Corruption Effects:** VOID_LOCKED bonds could have mechanical penalties:
   - -2 penalty when acting against former bond partner?
   - Void +1 when bond partner is nearby (corrupted connection actively harms)?

---

## Contact

Implementation by Claude (Sonnet 4.5) on 2025-01-24.
Questions/issues: Check `.claude/README.md` or `CLAUDE.md` patterns.
