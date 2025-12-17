# YAGS Conformance Audit - December 2025

## Executive Summary

**Overall Conformance: 65-70%**

Aeonisk-YAGS has a **solid foundation** with excellent attribute implementation but suffers from **skill system fragmentation** and **incomplete secondary stat handling**. The system is playable and produces good ML training data, but lacks the mechanical rigor of pure YAGS.

---

## 1. Attribute System - ✅ EXCELLENT (100%)

### Core YAGS Attributes (8 total)
**Status:** Fully compliant after Charisma migration

| YAGS Name | Aeonisk Name | Status | Notes |
|-----------|--------------|--------|-------|
| Strength | Strength | ✅ | Implemented correctly |
| Agility | Agility | ✅ | Implemented correctly |
| Health | **Endurance** | ✅ | Name change for Aeonisk flavor |
| Dexterity | Dexterity | ✅ | Recently added (Dec 2025) |
| Perception | Perception | ✅ | Implemented correctly |
| Intelligence | Intelligence | ✅ | Implemented correctly |
| Empathy | Empathy | ✅ | Replaced non-YAGS "Charisma" |
| Will | **Willpower** | ✅ | Name change for Aeonisk flavor |

**Attribute Ranges (Valid):**
```
Strength:      2-5 (avg 2.63) ✓ Within YAGS human range (1-6)
Agility:       2-5 (avg 3.53) ✓
Endurance:     2-5 (avg 3.22) ✓
Dexterity:     3-5 (avg 3.11) ✓
Perception:    2-5 (avg 4.03) ✓
Intelligence:  2-5 (avg 3.88) ✓
Empathy:       1-5 (avg 3.21) ✓
Willpower:     3-6 (avg 3.78) ✓
```

**Point Budgets (Reasonable):**
- Weak: 20 points (avg 2.5 per attribute)
- Typical: 24 points (avg 3.0)
- Heroic: 28 points (avg 3.5)
- Observed: 23-29 range (good distribution)

**Config Issues Found:**
- ❌ 64 characters still use deprecated `"Health"` instead of `"Endurance"`
- ⚠️ ~250 characters have lowercase attribute names (`"agility"` vs `"Agility"`)
- ✅ Zero Charisma references (migration successful)

**Files Checked:**
- `scripts/aeonisk/multiagent/mechanics.py:1864-1867` (canonical list)
- `scripts/session_configs/*.json` (267 character definitions)
- `tests/unit/test_attribute_migration.py` (13/13 tests pass)

---

## 2. Skill System - ⚠️ CRITICAL GAPS (40%)

### The Problem: Two Sources of Truth

**Skill Database (`skill_descriptions.py`):** 32 defined skills
**Actual Config Usage:** 63+ different skill names

**Result:** Half the skills in configs don't exist in the database.

### Missing YAGS Skills (Critical)

| Attribute | YAGS Skills Missing | Impact |
|-----------|---------------------|--------|
| **Strength** | Climbing, Swimming, Lifting, Throwing (heavy) | ❌ Strength has ZERO offensive skills |
| **Endurance** | Resistance, Fortitude, Running, Stamina | ❌ Endurance is purely HP pool |
| Agility | ✓ Has 5 skills | Good coverage |
| Dexterity | ✓ Has 4 skills | Good coverage |
| Perception | ✓ Has 4 skills | Good coverage |
| Intelligence | ✓ Has 10 skills | Over-represented |
| Empathy | ✓ Has 5 skills | Good coverage |
| Willpower | ✓ Has 4 skills | Good coverage |

**Distribution Problem:**
- Intelligence-based: 10 skills (31% of all skills)
- Strength-based: **0 skills** (0%)
- Endurance-based: **0 skills** (0%)

### Undefined Skills in Active Use (31+ total)

**Top Offenders:**

| Skill | Configs Using | Maps To | Status | Fix |
|-------|---------------|---------|--------|-----|
| **Insight** | 27 | Perception? Empathy? | ❌ Undefined | Add to DB or alias to Awareness |
| **Persuasion** | 21 | Empathy | ❌ Undefined | Alias to Charm or add separate |
| **Void Lore** | 17 | Intelligence | ❌ Undefined | Add (Aeonisk-specific) |
| **Engineering** | 16 | Intelligence | ❌ Undefined | Add or alias to Tech/Craft |
| **Hacking** | 8 | Intelligence | ❌ Undefined | Add (tech skill) |
| **Tactics** | 7 | Intelligence | ❌ Undefined | Add (combat planning) |
| **Meditation** | 5 | Willpower | ❌ Undefined | Add or alias to Discipline |
| **Ritual Lore** | 5 | Intelligence | ❌ Undefined | Add (Aeonisk knowledge) |
| **Deception** | 2 | Empathy | ❌ Undefined | Should use Guile |
| **Observation** | 1 | Perception | ❌ Undefined | Should use Awareness |

**Examples from Configs:**

```json
// session_config_golden_comprehensive.json:63-70
{
  "name": "Cipher",
  "skills": {
    "Investigation": 5,      // ✓ Valid
    "Observation": 5,        // ❌ UNDEFINED → should be "Awareness"
    "Insight": 4,            // ❌ UNDEFINED → no clear mapping
    "Hacking": 3             // ❌ UNDEFINED → should exist as skill
  }
}

// session_config_full.json:155
{
  "name": "Vesper Karsel",
  "skills": {
    "Social": 5              // ❌ UNDEFINED → too vague, use Charm/Guile
  }
}
```

**Current Validator Output:**
```
Void Archive Researcher Cipher: VALID (0 errors, 3 warnings)
  WARNINGS:
    ⚠️  Unknown skill 'Observation' (not in SKILL_DATABASE)
    ⚠️  Unknown skill 'Insight' (not in SKILL_DATABASE)
    ⚠️  Unknown skill 'Hacking' (not in SKILL_DATABASE)
```

**Why This Matters:**
- Inconsistent ML training data (undefined skills have no mechanical grounding)
- LLMs don't know which attribute to use for undefined skills
- Validator warnings on 80%+ of configs (noise obscures real issues)

**Files Affected:**
- `scripts/aeonisk/multiagent/skill_descriptions.py:22-331` (database)
- `scripts/session_configs/*.json` (73 configs with undefined skills)
- `scripts/aeonisk/multiagent/action_router.py:61-103` (skill routing)

---

## 3. Secondary Stats - ⚠️ PARTIAL (50%)

### Size (Secondary Stat) - ✅ Recognized

**Status:** Validator treats Size as valid secondary stat (not core attribute)

**Usage:**
- 52/267 characters (19%) have Size defined
- Range: 4-6 (standard human range)
- Missing from: 215 older characters

**Issue:** Inconsistent application across configs

**YAGS Standard:**
- Size 4: Small human (child, petite adult)
- Size 5: Average human ✓ Most common
- Size 6: Large human (tall, bulky)
- Size 7+: Non-human (ogres, etc.)

### HP/Wounds System - ✅ Implemented

**Formula:** `HP = (Size × 2) + Endurance + 13`

**Location:** `player.py:305-312`

```python
endurance = self.character_state.attributes.get('Endurance', 3)
size = character_config.get('Size', 5)
self.max_health = (size * 2) + endurance + 13  # +13 balance bonus
self.health = self.max_health
self.wounds = 0
```

**Deviation from YAGS:**
- YAGS uses: `HP = (Size + Endurance) × 3`
- Aeonisk uses: `HP = (Size × 2) + Endurance + 13`
- **Reasoning:** Balance tweaks for Aeonisk combat expectations

**Verdict:** ✓ Acceptable deviation (intentional design choice)

### Soak (Armor Value) - ⚠️ Hardcoded

**YAGS Formula:** `Soak = Size + Strength + Agility + 1`

**Aeonisk Implementation:**
```python
# player.py:316
self.soak = 10  # ❌ HARDCODED for all characters
```

**Expected Range (if calculated):**
- Min: 6 (Size 4 + Str 1 + Agi 1 + 1)
- Avg: 9 (Size 5 + Str 3 + Agi 3 + 1)
- Max: 12 (Size 6 + Str 5 + Agi 5 + 1)

**Current:** Everyone has Soak 10 regardless of attributes

**Impact:**
- No defensive differentiation between agile vs strong characters
- Character building less meaningful (attributes don't affect survivability)

**Fix Required:** Calculate dynamically from attributes

### Move Speed - ❌ Not Implemented

**YAGS Formula:** `Move = Size + Strength + Agility + 1`

**Status:** Not tracked in character state

**Expected Range:**
- Min: 6 yards/turn (Size 4 + Str 1 + Agi 1 + 1)
- Avg: 10 yards/turn (Size 5 + Str 3 + Agi 3 + 1)
- Max: 13 yards/turn (Size 6 + Str 5 + Agi 5 + 1)

**Impact:** Combat movement uses ad-hoc distances instead of calculated values

### Fatigue/Stun Tracks - ❌ Not Implemented

**YAGS Systems:**
- **Fatigue Track:** Based on Endurance (exhaustion, stamina drain)
- **Stun Track:** Based on Health (knockout, unconsciousness)

**Status:** Neither implemented in Aeonisk

**Impact:** No mechanical representation of exhaustion or stunning

---

## 4. Character Balance - ✅ GOOD (95%)

### Archetype Analysis (from `session_config_golden_comprehensive.json`)

Well-designed archetypes with clear mechanical differentiation:

| Character | Role | Str | Agl | End | Dex | Per | Int | Emp | Wil | Total | Key Skills |
|-----------|------|-----|-----|-----|-----|-----|-----|-----|-----|-------|------------|
| **Cipher** | Investigator | 2 | 3 | 3 | 3 | 5 | 5 | 3 | 4 | 28 | Investigation 5, Science 5, Awareness 4 |
| **Mercy** | Diplomat | 3 | 3 | 3 | 3 | 4 | 4 | 5 | 4 | 29 | Charm 5, Counsel 5, Corporate Influence 4 |
| **Raze** | Combat | 4 | 4 | 5 | 3 | 4 | 3 | 2 | 4 | 29 | Combat 5, Guns 5, Athletics 4 |
| **Spark** | Tech | 2 | 4 | 3 | 3 | 4 | 5 | 4 | 3 | 28 | Systems 5, Tech/Craft 5, Hacking* 4 |

**Assessment:**
- ✓ Point totals balanced (28-29 range)
- ✓ Clear specialization (each has 2-3 skills at rank 5)
- ✓ Role differentiation (combat, social, technical, analytical)
- ⚠️ Spark uses undefined "Hacking" skill

**Attribute Stat Distribution (267 characters):**
- **Most dumped:** Strength (avg 2.63) - least mechanically useful
- **Most valued:** Perception (avg 4.03), Intelligence (avg 3.88) - investigation/knowledge
- **Balanced:** Agility (3.53), Willpower (3.78), Empathy (3.21)

**Pattern:** Characters optimize for **Investigation > Combat > Social** skills
- Makes sense for Aeonisk narrative focus (mysteries, void phenomena)
- Strength undervalued because no offensive skills exist for it

---

## 5. Validation System - ✅ WORKING (100%)

### Character Validator Status

**File:** `scripts/aeonisk/multiagent/character_validator.py`

**Function:** ✓ Correctly validates character definitions

**What It Catches:**
- ✓ Non-YAGS attributes (e.g., "Charisma", "Health")
- ✓ Missing Dexterity (WARNING, not ERROR for backwards compatibility)
- ✓ Undefined skills (WARNINGS for all 31+ undefined skills)
- ✓ Recognizes Size as valid secondary stat
- ✓ Suggests corrections for common mistakes

**Example Output:**
```
Character: Void Archive Researcher Cipher
Status: VALID (0 errors, 3 warnings)

WARNINGS:
  ⚠️  Unknown skill 'Observation' (not in SKILL_DATABASE)
      Suggestion: Use 'Awareness' instead
  ⚠️  Unknown skill 'Insight' (not in SKILL_DATABASE)
  ⚠️  Unknown skill 'Hacking' (not in SKILL_DATABASE)
      Suggestion: Add to skill database or use 'Systems'

INFO:
  ℹ️  'Size' is a YAGS secondary stat (not a core attribute)
  ℹ️  Character has 28 attribute points (heroic/elite tier)
```

**Tests:** 13/13 passing in `tests/unit/test_attribute_migration.py`

**Issue:** Validator works correctly, but **configs ignore warnings**
- 80%+ of configs have skill warnings
- Warnings are treated as advisory, not blocking
- Creates low-quality data for ML training

---

## 6. Recommended Actions (Prioritized)

### TIER 1: Critical (Blocks Mechanical Depth)

**1.1: Add Strength-Based Skills**
```python
# In skill_descriptions.py, add:
"Climbing": SkillInfo(
    name="Climbing",
    attribute="Strength",
    description="Scaling walls, cliffs, ropes, vertical obstacles",
    use_cases=["Climbing terrain", "Rope climbing", "Scaling walls"],
    category="Movement"
),
"Swimming": SkillInfo(
    name="Swimming",
    attribute="Strength",
    description="Swimming, diving, underwater movement",
    use_cases=["Swimming", "Diving", "Water rescue"],
    category="Movement"
),
"Lifting": SkillInfo(
    name="Lifting",
    attribute="Strength",
    description="Lifting, carrying, moving heavy objects",
    use_cases=["Breaking down doors", "Moving obstacles", "Carrying wounded"],
    category="Physical"
),
```

**1.2: Add Endurance-Based Skills**
```python
"Resistance": SkillInfo(
    name="Resistance",
    attribute="Endurance",
    description="Resisting toxins, disease, environmental hazards",
    use_cases=["Poison resistance", "Disease immunity", "Environmental extremes"],
    category="Survival"
),
"Stamina": SkillInfo(
    name="Stamina",
    attribute="Endurance",
    description="Long-distance running, sustained physical effort",
    use_cases=["Marathon running", "Prolonged combat", "Extended exertion"],
    category="Physical"
),
```

**1.3: Resolve Top 10 Undefined Skills**

Add these heavily-used skills to database:
1. **Insight** (27 configs) → Add as Empathy-based "reading people/situations"
2. **Persuasion** (21 configs) → Add as Empathy-based or alias to Charm
3. **Void Lore** (17 configs) → Add as Intelligence-based Aeonisk knowledge
4. **Engineering** (16 configs) → Add as Intelligence-based or alias to Tech/Craft
5. **Hacking** (8 configs) → Add as Intelligence-based tech skill
6. **Tactics** (7 configs) → Add as Intelligence-based combat planning
7. **Meditation** (5 configs) → Add as Willpower-based or alias to Discipline
8. **Ritual Lore** (5 configs) → Add as Intelligence-based ritual knowledge
9. **Deception** (2 configs) → Alias to existing Guile skill
10. **Observation** (1 config) → Alias to existing Awareness skill

**Estimated Effort:** 4-6 hours (research YAGS skills, write descriptions, update routing)

---

### TIER 2: High Priority (Config Quality)

**2.1: Migrate "Health" to "Endurance"**

**Affected:** 64 characters across multiple configs

**Fix:**
```bash
# Automated migration script
for f in scripts/session_configs/*.json; do
  sed -i 's/"Health":/"Endurance":/g' "$f"
done
```

**Verification:**
```bash
python scripts/aeonisk/multiagent/character_validator.py scripts/session_configs/*.json
```

**2.2: Add Size to All Characters**

**Current:** Only 52/267 (19%) have Size defined

**Recommended:**
- Default Size: 5 (average human)
- Small humans: Size 4 (children, petite)
- Large humans: Size 6 (tall, bulky)

**Script:**
```python
# Add "Size": 5 to all character dicts missing it
for config_file in session_configs:
    for character in config['agents']['players']:
        if 'Size' not in character.get('attributes', {}):
            character['attributes']['Size'] = 5
```

**2.3: Standardize Attribute Capitalization**

**Issue:** ~250 characters have lowercase (`"agility"` vs `"Agility"`)

**Fix:** Validator auto-normalizes, but configs should be clean

---

### TIER 3: Medium Priority (Mechanical Depth)

**3.1: Implement Dynamic Soak**

**Current Code:**
```python
# player.py:316
self.soak = 10  # ❌ Hardcoded
```

**Fix:**
```python
# player.py:316
size = self.character_state.attributes.get('Size', 5)
strength = self.character_state.attributes.get('Strength', 3)
agility = self.character_state.attributes.get('Agility', 3)
self.soak = size + strength + agility + 1  # YAGS standard
```

**Impact:** Characters with high Str/Agi become more defensive (range 6-12 instead of fixed 10)

**3.2: Implement Move Calculation**

**Add to Character State:**
```python
# player.py (after soak calculation)
self.move = size + strength + agility + 1  # YAGS move distance
```

**3.3: Add Fatigue Track (Optional)**

Endurance-based exhaustion system for prolonged exertion:
```python
self.max_fatigue = endurance * 2
self.fatigue = 0  # 0 = fresh, max = exhausted
```

---

### TIER 4: Low Priority (Polish)

**4.1: Document Skill-to-Attribute Mappings**

Create reference table in `.claude/SKILL_ATTRIBUTE_REFERENCE.md`

**4.2: Update Character Creation Guide**

Add checklist:
- [ ] All 8 core attributes (Str, Agi, End, Dex, Per, Int, Emp, Wil)
- [ ] Size secondary stat (default 5 for humans)
- [ ] Skills from validated database only
- [ ] Capitalize all attribute names

**4.3: Add Pre-Commit Hook**

Validate configs before committing:
```bash
#!/bin/bash
# .git/hooks/pre-commit
python scripts/aeonisk/multiagent/character_validator.py --strict $(git diff --cached --name-only | grep session_config)
```

---

## 7. Files to Examine/Modify

| File | Current Issue | Recommended Fix | Priority |
|------|---------------|-----------------|----------|
| `skill_descriptions.py:22-331` | Missing Strength/Endurance skills, 31+ undefined skills | Add ~15 missing skills | TIER 1 |
| `action_router.py:61-103` | No routing for new skills | Update skill-to-attribute mappings | TIER 1 |
| `session_configs/*.json` | "Health" instead of "Endurance" (64 chars) | Global search/replace | TIER 2 |
| `session_configs/*.json` | Missing Size (215 chars) | Add Size: 5 default | TIER 2 |
| `player.py:316` | Hardcoded soak = 10 | Calculate from Size+Str+Agi+1 | TIER 3 |
| `player.py:318` | No Move calculation | Add move = Size+Str+Agi+1 | TIER 3 |
| `character_validator.py:30-38` | Only validates Size | Add Move, Soak, Fatigue | TIER 4 |
| `datasets/aeonisk_character_examples.yaml` | Uses "health" attribute | Migrate to "Endurance" | TIER 2 |

---

## 8. Conformance Summary Table

| Aspect | Status | % Complete | Gap Description |
|--------|--------|------------|-----------------|
| **Core Attributes (8)** | ✅ Excellent | 100% | Perfect YAGS alignment |
| Attribute Ranges | ✅ Valid | 100% | Within YAGS human norms (1-6) |
| Point Budgets | ✅ Reasonable | 95% | Good balance, slight high-end bias |
| **Skills in Database** | ⚠️ Incomplete | 40% | 31+ undefined skills in active use |
| Strength Skills | ❌ Missing | 0% | Zero Strength-based skills |
| Endurance Skills | ❌ Missing | 0% | Zero Endurance-based skills |
| Other Attribute Skills | ✅ Good | 75% | Agility/Int/Empathy well-covered |
| **Size (Secondary)** | ✅ Recognized | 100% | Validator correct, 19% usage |
| HP System | ✅ Functional | 95% | Implemented with balance tweaks |
| Soak System | ⚠️ Hardcoded | 50% | Fixed at 10, should be dynamic |
| Move System | ❌ Missing | 0% | Not calculated |
| Fatigue/Stun | ❌ Missing | 0% | Not implemented |
| **Character Archetypes** | ✅ Excellent | 95% | Well-balanced, clear roles |
| Config Validation | ✅ Working | 100% | 13/13 tests pass |
| Config Quality | ⚠️ Inconsistent | 60% | Many deprecated/undefined references |

**Overall YAGS Conformance: 65-70%**

---

## 9. Key Insights

### What's Working
1. **Attribute foundation is rock-solid** - 100% YAGS compliant
2. **Character archetypes are well-designed** - Clear mechanical roles
3. **Validation catches issues** - Warnings highlight problems
4. **HP system is functional** - Works for gameplay

### What's Broken
1. **Skill system is fragmented** - Two sources of truth, half undefined
2. **Strength/Endurance have no offensive skills** - Mechanically shallow
3. **Secondary stats half-implemented** - Soak hardcoded, Move missing
4. **Config quality is low** - 80%+ have validation warnings

### Root Cause
**Permissive validation** - Warnings don't block execution, so configs drift from standards

**Philosophy tension:**
- YAGS emphasizes **mechanical rigor** (strict skill definitions, calculated stats)
- Aeonisk emphasizes **narrative flexibility** (LLMs improvise, loose validation)

**Result:** Hybrid system that's neither strict YAGS nor fully emergent

### Strategic Question
**Do you want:**
- **Strict YAGS conformance** → More work, but better mechanical depth
- **Loose narrative system** → Less work, but ML data quality suffers
- **Hybrid approach** → Current state (65-70% conformance)

---

## 10. Recommended Path Forward

### Option A: Tighten to 85-90% YAGS Conformance (Recommended)

**Effort:** 2-3 days
**Benefit:** Mechanical depth, consistent ML data, skill system clarity

**Actions:**
1. Add 15 missing skills to database (TIER 1)
2. Fix config issues (Health→Endurance, add Size) (TIER 2)
3. Implement dynamic Soak and Move (TIER 3)

**Trade-off:** More initial work, but system becomes self-consistent

### Option B: Accept Current State (65-70%)

**Effort:** 0 hours
**Benefit:** No disruption to existing configs/workflows

**Actions:** None (document current state, accept warnings)

**Trade-off:** Skill warnings persist, ML data quality lower, mechanical depth limited

### Option C: Loosen Further (50% conformance)

**Effort:** 1 day (remove validation, make system fully permissive)
**Benefit:** LLMs can improvise any skill, full narrative freedom

**Actions:**
1. Disable skill validation warnings
2. Allow any skill name (LLM decides attribute mapping on-the-fly)
3. Remove YAGS skill database entirely

**Trade-off:** Lose mechanical grounding, harder to balance, inconsistent ML training data

---

## My Recommendation: **Option A (Tighten to 85-90%)**

**Why:**
- You've already done the hard work (attribute migration, validation system)
- Adding 15 skills is straightforward (4-6 hours)
- Dynamic Soak/Move improves character differentiation
- Higher quality ML training data
- Closer to YAGS = easier to reference rulebook for balance

**Next Steps:**
1. Review this audit with team
2. Decide on conformance target (85-90% vs current 65-70%)
3. If tightening: Execute TIER 1 actions (add skills)
4. If staying loose: Document current state, accept warnings

---

## Appendix: YAGS Reference

**Official YAGS SRD:** https://www.notasnark.net/yags/

**Core Books:**
- YAGS Core (system mechanics)
- YAGS Fantasy (medieval fantasy)
- YAGS Modern (contemporary settings)
- YAGS High Tech (sci-fi) ← Most relevant for Aeonisk

**Key Aeonisk Deviations:**
- HP calculation (balance tweaks)
- Skill names (flavor changes: Health→Endurance, Will→Willpower)
- Void mechanics (entirely custom, not in YAGS)
- Ritual system (Aeonisk-specific)

**Where YAGS Applies:**
- Attribute system (1-6 range, 8 core attributes)
- Skill resolution (attribute + skill vs DC)
- Secondary stats (Size, Move, Soak formulas)
- Character creation (point-buy budgets)

**Where Aeonisk Diverges:**
- Narrative-first LLM adjudication (YAGS is player-facing dice)
- Void corruption system (no YAGS equivalent)
- Energy economy (breath/drip/grain/spark - not in YAGS)
- Ritual mechanics (Aeonisk-specific magic system)
