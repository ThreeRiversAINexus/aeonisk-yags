# Explicit State Tracking Refactor - Task Brief

**Status:** Planned
**Priority:** High (affects ML training data quality)
**Created:** 2025-10-23
**Context:** See `.claude/DM_CONTROL_VS_HARDCODED.md` for full analysis

## Problem Statement

The current system uses **implicit keyword-based parsing** to track game state changes (clocks, void, soulcredit). This creates three major issues:

### 1. Ambiguous ML Training Labels
```python
# Current behavior:
DM narrates: "You find evidence of corruption"
Parser detects: "evidence" keyword
System auto-advances: Evidence Collection clock +1
```

**Problem:** We can't tell if:
- DM intended to advance this clock
- Parser guessed correctly
- Parser guessed wrong (DM meant different kind of evidence)

**ML Impact:** Training data has noisy labels. Model learns "evidence" → clock advance, but doesn't learn DM's actual decision-making process.

### 2. Inconsistent State Tracking
```python
# Scenario A:
DM: "You discover proof of the conspiracy"
Parser: "investigation" keyword → Evidence clock +1 ✓

# Scenario B:
DM: "You uncover documentation linking the magistrate"
Parser: No keyword match → Evidence clock +0 ✗
```

**Problem:** Same semantic action, different mechanical outcomes based on word choice.

**ML Impact:** Model can't learn reliable patterns because ground truth is inconsistent.

### 3. DM Loses Awareness
```python
# DM writes narration
# Parser runs in background
# Clock advances without DM knowing
# Next round, DM sees clock at 5/6 instead of 3/6
# DM confused: "When did that advance?"
```

**Problem:** DM doesn't have clear feedback loop about mechanical consequences of narration.

**Game Design Impact:** DM can't intentionally pace clock advancement.

---

## Current Implementation (What to Replace)

### Files Involved
- `scripts/aeonisk/multiagent/outcome_parser.py` - Keyword-based parsing
- `scripts/aeonisk/multiagent/dm.py` - DM narration generation
- `scripts/aeonisk/multiagent/mechanics.py` - State tracking (void, soulcredit)
- `scripts/aeonisk/multiagent/session.py` - Clock management

### Current Keyword Lists (BRITTLE)
```python
# outcome_parser.py (approximate)
danger_keywords = ['danger', 'threat', 'escalation', 'security', 'alert']
investigation_keywords = ['investigation', 'evidence', 'discovery', 'clue']
corruption_keywords = ['corruption', 'void', 'taint', 'contamination']

void_triggers = {
    'void_exposure': 1,
    'ritual_shortcut': 1,
    'bond_betrayal': 2,
    'void_manipulation': 1,
    'corrupted_tech': 1
}

soulcredit_gains = {
    'fulfill_contract': +1,
    'aid_ritual': +1,
    'void_cleansing': +2,  # or +3 if margin 10+
    'public_ritual': +2,
    'uphold_faction': +1
}
```

**Problem:** DM must use exact keywords or synonyms. "Peril" ≠ "danger", so parser misses it.

### Current Flow (IMPLICIT)
```
1. Player declares action
2. Mechanics resolves (dice + formula)
3. DM generates narration (LLM)
4. outcome_parser.parse_state_changes(narration) runs
   → Searches for keywords
   → Auto-advances clocks
   → Auto-tracks void
   → Auto-tracks soulcredit
5. Session applies changes
6. DM sees results next round
```

**No feedback to DM about what was detected!**

---

## Desired Solution: EXPLICIT MARKING SYSTEM

### Design Goals
1. **DM has full control** - Nothing happens without DM explicitly marking it
2. **Clear ML labels** - Training data shows DM's intent, not parser's guess
3. **Feedback loop** - DM sees what system detected, can confirm/override
4. **Backward compatible** - Can still fall back to parsing if DM doesn't mark

### Proposed Syntax: Structured Markers

#### Clock Advancement
```markdown
**DM Narration:**
Kael searches the magistrate's office, rifling through documents.
The evidence is damning - financial records showing payoffs from
the Void Syndicate.

📊 Evidence Collection: +2 (found financial records)
```

**Parser extracts:**
```python
{
  "clock_changes": [
    {
      "clock_name": "Evidence Collection",
      "delta": +2,
      "justification": "found financial records",
      "source": "dm_explicit"
    }
  ]
}
```

#### Void Tracking
```markdown
**DM Narration:**
The ritual backfires - corrupted energy surges through Zara's
hands, leaving void-taint marks on her palms.

⚫ Void: +1 (ritual backfire)
```

**Parser extracts:**
```python
{
  "void_changes": [
    {
      "character": "Zara Nightwhisper",
      "delta": +1,
      "trigger": "ritual backfire",
      "source": "dm_explicit"
    }
  ]
}
```

#### Soulcredit Tracking
```markdown
**DM Narration:**
Kael fulfills his oath to the Pantheon, despite the personal
cost. The spiritual resonance is palpable.

⚖️ Soulcredit: +1 (oath fulfilled)
```

**Parser extracts:**
```python
{
  "soulcredit_changes": [
    {
      "character": "Kael Dren",
      "delta": +1,
      "trigger": "oath fulfilled",
      "source": "dm_explicit"
    }
  ]
}
```

### Fallback: Keyword Detection (Optional)

If DM doesn't mark explicitly, parser can still attempt detection BUT:
- Log it as `"source": "inferred_by_parser"`
- Show DM what was detected in next round's prompt
- Ask DM to confirm or override

```python
# In DM's next prompt:
"""
⚠️ INFERRED STATE CHANGES (please confirm):
- Evidence Collection: +1 (detected "evidence" keyword)
- Void (Zara): +1 (detected "corruption" keyword)

Include these markers in your narration if correct:
📊 Evidence Collection: +1 ✓
⚫ Void (Zara): +1 ✓

Or correct them:
📊 Evidence Collection: +0 (was false positive)
"""
```

---

## Implementation Plan

### Phase 1: Parser Refactor
**Goal:** Support explicit markers, log both explicit + inferred

**Files to modify:**
- `scripts/aeonisk/multiagent/outcome_parser.py`

**Changes:**
1. Add regex patterns for emoji markers:
   - `📊 (Clock Name): ([+-]\d+) \((.*?)\)`
   - `⚫ Void(?: \((.*?)\))?: ([+-]\d+) \((.*?)\)`
   - `⚖️ Soulcredit(?: \((.*?)\))?: ([+-]\d+) \((.*?)\)`

2. Create dual extraction:
   ```python
   def parse_state_changes(narration, context):
       explicit = extract_explicit_markers(narration)
       inferred = extract_keyword_patterns(narration) if not explicit else {}

       return {
           "explicit": explicit,
           "inferred": inferred,
           "source": "dm_explicit" if explicit else "inferred"
       }
   ```

3. Log both to JSONL:
   ```python
   {
       "event_type": "state_change",
       "round": 2,
       "narration": "...",
       "explicit_markers": [...],
       "inferred_markers": [...],
       "applied_changes": [...]  # What actually got applied
   }
   ```

### Phase 2: DM Prompt Enhancement
**Goal:** Teach DM to use explicit markers

**Files to modify:**
- `scripts/aeonisk/multiagent/dm.py` (narration generation prompts)

**Changes:**
1. Add to action adjudication prompt:
   ```
   After your narrative description, explicitly mark any state changes:

   📊 Clock: +N (reason) - Advance a clock
   ⚫ Void: +N (reason) - Character gains void
   ⚖️ Soulcredit: +N (reason) - Character gains/loses soulcredit

   Example:
   "Kael finds the evidence hidden in the safe.

   📊 Evidence Collection: +2 (discovered hidden documents)"
   ```

2. Add to round synthesis prompt:
   ```
   Review any filled clocks and their consequences.
   If spawning enemies, include the marker exactly as shown:
   [SPAWN_ENEMY: name | template | count | position | tactics]
   ```

3. Add feedback loop to next round's prompt:
   ```
   ⚠️ Last round, the system detected:
   - Evidence Collection: +1 (inferred from keyword)

   If this is incorrect, mark the correction:
   📊 Evidence Collection: -1 (false positive, reverting)
   ```

### Phase 3: JSONL Logging Enhancement
**Goal:** Separate explicit from inferred in training data

**Files to modify:**
- `scripts/aeonisk/multiagent/mechanics.py` (JSONLLogger class)

**Changes:**
1. Add `state_change` event type:
   ```python
   {
       "event_type": "state_change",
       "ts": "...",
       "round": 2,
       "agent": "dm",
       "narration": "...",
       "changes": [
           {
               "type": "clock",
               "clock_name": "Evidence Collection",
               "delta": +2,
               "justification": "found documents",
               "source": "dm_explicit"
           }
       ]
   }
   ```

2. Add `source` field to existing events:
   ```python
   # In action_resolution events
   {
       "void_changes": {
           "delta": +1,
           "trigger": "ritual backfire",
           "source": "dm_explicit"  # or "inferred_by_parser"
       }
   }
   ```

### Phase 4: Validation & Testing
**Goal:** Ensure explicit marking works, fallback still functions

**Tasks:**
1. Run session with explicit marking enabled
2. Check JSONL logs for `source` field consistency
3. Validate that DM receives feedback about inferred changes
4. Test fallback behavior when DM forgets to mark

**Validation script:**
```python
# scripts/aeonisk/multiagent/validate_explicit_marking.py
def validate_session(jsonl_path):
    explicit_count = 0
    inferred_count = 0

    for event in read_jsonl(jsonl_path):
        if 'source' in event:
            if event['source'] == 'dm_explicit':
                explicit_count += 1
            elif event['source'] == 'inferred_by_parser':
                inferred_count += 1

    print(f"Explicit markings: {explicit_count}")
    print(f"Inferred markings: {inferred_count}")
    print(f"Explicit ratio: {explicit_count / (explicit_count + inferred_count):.2%}")
```

---

## Success Criteria

### Must Have
- ✅ Parser can extract explicit emoji markers (📊, ⚫, ⚖️)
- ✅ JSONL logs include `source` field distinguishing explicit vs inferred
- ✅ DM prompt teaches explicit marking syntax
- ✅ System still works if DM doesn't use markers (fallback to keywords)

### Nice to Have
- ✅ DM receives feedback about what was inferred last round
- ✅ Validation script measures explicit vs inferred ratio
- ✅ Documentation shows example narrations with markers

### Stretch Goals
- ⚙️ Session config flag: `require_explicit_marking: true` (strict mode, no fallback)
- ⚙️ Real-time DM feedback during narration (show detected markers before applying)
- ⚙️ Semantic similarity instead of keywords for fallback (use embeddings)

---

## Testing Plan

### Test Case 1: Explicit Marking Works
```python
narration = """
Kael finds damning evidence.

📊 Evidence Collection: +2 (financial records)
⚫ Void (Kael): +1 (void exposure)
⚖️ Soulcredit (Kael): -1 (questionable ethics)
"""

result = parse_state_changes(narration, context)
assert result['explicit']['clock_changes'][0]['delta'] == 2
assert result['explicit']['void_changes'][0]['delta'] == 1
assert result['explicit']['soulcredit_changes'][0]['delta'] == -1
assert all(c['source'] == 'dm_explicit' for c in result['explicit'].values())
```

### Test Case 2: Fallback to Keywords
```python
narration = """
Kael discovers evidence of corruption in the void-tainted records.
"""

result = parse_state_changes(narration, context)
assert result['inferred']['clock_changes']  # Should detect "evidence"
assert result['inferred']['void_changes']   # Should detect "void"
assert all(c['source'] == 'inferred_by_parser' for c in result['inferred'].values())
```

### Test Case 3: Mixed Explicit + Inferred
```python
narration = """
Kael finds the documents.

📊 Evidence Collection: +2 (explicit)

He also stumbles upon void-corrupted tech.
"""

result = parse_state_changes(narration, context)
assert result['explicit']['clock_changes'][0]['delta'] == 2
assert result['inferred']['void_changes']  # Should detect "void-corrupted"
```

---

## Migration Strategy

### Step 1: Add Support (No Breaking Changes)
- Implement explicit marker parsing
- Keep keyword fallback working
- Log both `source` fields

### Step 2: Train DM to Use Markers
- Update prompts to teach syntax
- Run sessions, monitor explicit ratio
- Fix any issues with marker detection

### Step 3: Evaluate
- After 10+ sessions, check explicit vs inferred ratio
- If >80% explicit, keyword fallback is working as safety net
- If <50% explicit, DM prompt needs improvement

### Step 4: Optional Strict Mode
- Add config flag to disable keyword fallback
- Only use explicit markers
- Fail loudly if DM doesn't mark state changes

---

## Open Questions for Next Agent

1. **Should we keep keyword fallback long-term?**
   - Pro: Safety net if DM forgets
   - Con: Creates mixed training data (some explicit, some inferred)

2. **Should inferred changes be applied automatically?**
   - Option A: Apply immediately, log as inferred
   - Option B: Queue for DM confirmation next round
   - Option C: Only apply if confidence > threshold

3. **How to handle character-specific state (void, soulcredit)?**
   - Marker format: `⚫ Void (Kael): +1` or `⚫ Void: Kael +1`?
   - Multiple characters in one action?

4. **Should we use semantic similarity instead of keywords?**
   - Could use sentence embeddings to detect similar concepts
   - More robust than exact keyword matching
   - But requires ChromaDB/transformers (already in venv)

5. **Validation: Should we warn DM about missing markers?**
   - Example: Clock should advance (based on context) but no marker
   - Show warning: "⚠️ Evidence clock didn't advance this round. Intentional?"

---

## References

- **Current implementation:** `scripts/aeonisk/multiagent/outcome_parser.py`
- **Analysis:** `.claude/DM_CONTROL_VS_HARDCODED.md` (Part 2.2, 2.5)
- **ML logging:** `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`
- **Validation tools:** `scripts/aeonisk/multiagent/validate_logging.py`

---

## Notes to Next Agent

- This is a **refactor**, not a rewrite. Keep the existing system working.
- The goal is **clearer ML training labels**, not just cleaner code.
- **Explicit > Implicit** for training data quality.
- Keep keyword fallback as safety net during transition.
- Measure success by `explicit_ratio` in validation script.

Good luck! This will significantly improve training data quality.
