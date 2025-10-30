# Graded Outcomes ML Logging Implementation

**Status:** In Progress (Phase 1 Complete)
**Date Started:** 2025-10-29
**Purpose:** Enhance JSONL logging to match dataset guidelines for ML training with counterfactual outcomes

## Overview

Adding dataset-compliant graded outcome logging that captures:
1. **Counterfactual outcomes**: All 6 possible outcome tiers for every action (critical_failure → exceptional_success)
2. **Player expectations**: What AI agents think will happen before DM resolves
3. **LLM format errors**: Track and label mistakes for fine-tuning data

## Design Decisions (User Confirmed)

- ✅ **Add new events** (not replace existing logging)
- ✅ **Both error approaches** (separate event + embedded flags)
- ✅ **Generate all 6 tiers at logging time** (DM creates counterfactuals)
- ✅ **Adapt YAML schema for JSONL** (streaming-friendly format)
- ✅ **Player actions only** (not enemies)
- ✅ **Generate all 6 every time** (no skipping unlikely tiers)
- ✅ **Use ritual margin table** for rituals, YAGS degrees for skills

## Phase 1: Core Infrastructure ✅ COMPLETE

### 1. New Logging Methods (mechanics.py)

**Added two new logging methods to JSONLLogger class:**

#### `log_graded_outcome()`
Logs graded outcome with all 6 counterfactual tiers for ML training.

**Schema:**
```json
{
  "event_type": "graded_outcome",
  "ts": "ISO-8601",
  "session": "uuid",
  "round": 3,
  "agent": "Enforcer Kael Dren",
  "action_id": "uuid",

  // Context (from dataset guidelines)
  "scenario_context": "Analyzing void containment system...",
  "environment": "Corrupted monitoring systems, rising void resonance",
  "stakes": "Information vs. detection and void exposure",
  "goal": "Identify system tampering without triggering alerts",

  // Roll mechanics
  "attribute_used": "Intelligence",
  "skill_used": "Systems",
  "roll_formula": "3 × 3 = 9; 9 + d20",
  "difficulty_guess": 20,
  "actual_roll": {
    "d20": 3,
    "total": 12,
    "margin": -8
  },

  // COUNTERFACTUAL OUTCOMES (all 6 tiers)
  "outcome_explanation": {
    "critical_failure": {
      "threshold": "margin ≤ -10 OR natural 1",
      "narrative": "DM-generated dramatic failure...",
      "mechanical_effect": "+2 Void, system lockout, alarm",
      "occurred": false
    },
    "failure": {
      "threshold": "margin -9 to -1",
      "narrative": "...",
      "mechanical_effect": "+1 Void, corrupted data",
      "occurred": true  // ← What actually happened
    },
    // ... 4 more tiers
  },

  // Rationale and quality tracking
  "rationale": "Intelligence × Systems for technical analysis. DC 20...",
  "llm_generation_quality": {
    "format_valid": true,
    "retry_count": 0,
    "missing_tiers": [],
    "validation_warnings": []
  }
}
```

#### `log_llm_format_error()`
Logs LLM format errors for fine-tuning data.

**Schema:**
```json
{
  "event_type": "llm_format_error",
  "ts": "ISO-8601",
  "session": "uuid",
  "round": 3,
  "agent_type": "dm",
  "error_type": "missing_outcome_tier",
  "details": {
    "missing_tiers": ["excellent_success", "exceptional_success"]
  },
  "raw_response": "First 500 chars...",
  "retry_attempt": 1,
  "retry_prompt": "You must provide ALL 6 outcome tiers...",
  "resolution": "retry_successful"  // or "fallback_used", "skipped"
}
```

**Files Modified:**
- `scripts/aeonisk/multiagent/mechanics.py` (+117 lines)

### 2. DM Prompt Enhancement (prompts/claude/en/dm.yaml)

**Added new `graded_outcomes` section with comprehensive instructions:**

- **Format specification** for `[GRADED_OUTCOMES]...[/GRADED_OUTCOMES]` marker
- **Threshold guidelines** for skill checks vs. rituals:
  - Skill checks: Natural 1, margin tiers, natural 20
  - Rituals: Ritual margin table (-10, -9 to -1, 0-4, 5-9, 10-14, 15+)
- **Mechanical effects must be specific** (examples of good vs. bad)
- **Narrative requirements** (each tier should feel DISTINCT)
- **Rationale** for why we collect this data (counterfactual reasoning)

**Example format shown to DM:**
```
[GRADED_OUTCOMES]
CRITICAL_FAILURE (margin ≤ -10 OR natural 1):
Narrative: [2-3 sentence dramatic failure]
Mechanics: [+2 Void, item broken, major setback]

FAILURE (margin -9 to -1):
Narrative: [2-3 sentence failure with complications]
Mechanics: [+1 Void, minor penalty, attention drawn]

... (4 more tiers)
[/GRADED_OUTCOMES]
```

**Files Modified:**
- `scripts/aeonisk/multiagent/prompts/claude/en/dm.yaml` (+80 lines)
- Updated `section_order` to include `graded_outcomes`

### 3. Outcome Parser (outcome_parser.py)

**Added `parse_graded_outcomes()` function:**

- Extracts content between `[GRADED_OUTCOMES]` and `[/GRADED_OUTCOMES]` markers
- Parses all 6 tiers with their narratives and mechanical effects
- Returns dict with keys: `critical_failure`, `failure`, `moderate_success`, `good_success`, `excellent_success`, `exceptional_success`
- Each tier contains: `narrative` (str), `mechanical_effect` (str)
- Returns `None` if marker not found
- Returns partial data if some tiers missing (caller handles validation)

**Files Modified:**
- `scripts/aeonisk/multiagent/outcome_parser.py` (+127 lines)

## Phase 2: Player Predicted Outcomes ✅ COMPLETE

### Player Prompt Enhancement

**Added `outcome_prediction` section to player.yaml:**
- Instructions for generating `[PREDICTED_OUTCOMES]` marker
- All 6 tiers with narrative + mechanics format
- Detailed example (hacking corporate terminal)
- Guidelines: be specific, scale appropriately, think like character
- Explains ML training value (player predictions vs. DM ground truth)

**Files Modified:**
- `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml` (+106 lines)
- Updated `section_order` to include `outcome_prediction`

### Player Code Integration

**Modified player.py to parse predicted outcomes:**
- Extract `[PREDICTED_OUTCOMES]` from LLM response
- Reuse `parse_graded_outcomes()` (with marker replacement)
- Store outcomes in action object: `action._predicted_outcomes`

**Modified mechanics.py logging:**
- Updated `log_action_declaration()` to accept `predicted_outcomes` parameter
- Conditionally includes predicted outcomes in event if present

**Modified session.py:**
- Extract `_predicted_outcomes` from action payload
- Pass to `log_action_declaration()` for JSONL logging

**Result:** Player action_declaration events now include:
```json
{
  "event_type": "action_declaration",
  ...
  "action": {...},
  "predicted_outcomes": {
    "critical_failure": {
      "narrative": "Player's prediction...",
      "mechanical_effect": "Player's expected mechanics..."
    },
    // ... 5 more tiers
  }
}
```

**Files Modified:**
- `scripts/aeonisk/multiagent/player.py` (+8 lines)
- `scripts/aeonisk/multiagent/mechanics.py` (+5 lines)
- `scripts/aeonisk/multiagent/session.py` (+7 lines)

## Phase 3: DM Graded Outcomes ✅ COMPLETE

### DM Prompt Integration

**Modified `_build_dm_narration_prompt()` in dm.py:**
- Added graded_outcomes section to DM prompt (loaded from YAML)
- Section appears after narration_task for every action resolution
- DM now receives instructions to generate all 6 outcome tiers

**Modified `_resolve_action_mechanically()` in dm.py:**
- Parse `[GRADED_OUTCOMES]` from DM narration using `parse_graded_outcomes()`
- Determine which tier actually occurred (based on margin/natural rolls)
- Build complete outcome_explanation with thresholds for all 6 tiers
- Generate unique action_id (UUID) for linking to player predictions
- Extract scenario context, stakes, environment for dataset export
- Build roll formula string from resolution data
- Call `log_graded_outcome()` to log DM's authoritative outcomes
- Log `llm_format_error` event if tiers are missing
- Validate all 6 tiers present, track missing tiers

### Outcome Tier Determination

**Skill Checks:**
- critical_failure: Natural 1
- failure: Did not meet DC
- moderate_success: Margin 0-4
- good_success: Margin 5-9
- excellent_success: Margin 10-14
- exceptional_success: Margin 15+ OR natural 20

**Rituals (uses ritual margin table):**
- critical_failure: Margin ≤ -10
- failure: Margin -9 to -1
- moderate_success: Margin 0-4
- good_success: Margin 5-9
- excellent_success: Margin 10-14
- exceptional_success: Margin 15+

### ML Training Data Captured

**For each action, we now log:**

1. **Player Prediction** (action_declaration event):
   - What player thinks will happen at all 6 outcome tiers
   - Player's narrative + mechanical expectations

2. **DM Ground Truth** (graded_outcome event):
   - What DM says should happen at all 6 outcome tiers
   - DM's authoritative narrative + mechanics
   - Which tier actually occurred (marked with `occurred: true`)
   - Complete resolution data (rolls, margin, DC)

3. **Scenario Context**:
   - Theme, location, situation
   - Stakes and environment
   - Goal of the action
   - Attribute/skill used and roll formula

### Files Modified

- `scripts/aeonisk/multiagent/dm.py` (+157 lines)
  - Modified `_build_dm_narration_prompt()` to include graded_outcomes section
  - Modified `_resolve_action_mechanically()` to parse and log DM outcomes

## Summary: What We Have Now

### Complete ML Training Pipeline ✅

**1. Player declares action** →
- Predicts 6 outcome tiers (what they think will happen)
- Logged in `action_declaration` event with `predicted_outcomes` field

**2. DM resolves action** →
- Generates 6 authoritative outcome tiers (ground truth)
- Marks which tier occurred (based on actual roll)
- Logged in `graded_outcome` event

**3. Comparison for ML** →
- action_id links player prediction to DM ground truth
- Train on: Did player understand risks? Calibrate DC well? Predict outcomes accurately?

### Benefits for ML

✅ **Counterfactual Reasoning**: "If margin was +10 instead of +5, what changes?"
✅ **Difficulty Calibration**: Player DC estimate vs. DM actual DC
✅ **Outcome Prediction**: Player expectations vs. DM ground truth narratives
✅ **Action Selection**: Did player choose right attribute/skill?
✅ **Consequence Understanding**: Player vs. DM mechanical effect predictions
✅ **Error Labeling**: Track LLM format mistakes for fine-tuning

### Example Training Data

**Player predicts (action_declaration):**
```json
{
  "predicted_outcomes": {
    "failure": {
      "narrative": "Encryption too strong, terminal logs intrusion...",
      "mechanical_effect": "+1 Void, Security clock +1"
    }
  }
}
```

**DM resolves (graded_outcome):**
```json
{
  "outcome_explanation": {
    "failure": {
      "narrative": "ICE countermeasures activate, forcing disconnect...",
      "mechanical_effect": "+1 Void, Security clock +2, terminal locked",
      "occurred": true
    }
  }
}
```

**ML can learn:**
- Player underestimated consequences (clock +1 vs +2, terminal not locked)
- Both predicted +1 Void (correct!)
- DM added terminal lockout (player missed this risk)

## Remaining Tasks

1. ⏳ **Update documentation** - Document the implementation in CLAUDE.md
2. ⏳ **Update validate_logging.py** - Add graded_outcome + llm_format_error schemas
3. ⏳ **Create export_dataset.py** - Convert JSONL → normalized YAML dataset format
4. ⏳ **Test with sample session** - Run a session and verify dual graded outcomes work

## Files Modified Summary

✅ `scripts/aeonisk/multiagent/mechanics.py` - Added log_graded_outcome(), log_llm_format_error(), updated log_action_declaration()
✅ `scripts/aeonisk/multiagent/prompts/claude/en/dm.yaml` - Added graded_outcomes section
✅ `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml` - Added outcome_prediction section
✅ `scripts/aeonisk/multiagent/outcome_parser.py` - Added parse_graded_outcomes()
✅ `scripts/aeonisk/multiagent/player.py` - Parse and store predicted outcomes
✅ `scripts/aeonisk/multiagent/session.py` - Pass predicted outcomes to logger
✅ `scripts/aeonisk/multiagent/dm.py` - Generate, parse, and log DM graded outcomes

⏳ `scripts/aeonisk/multiagent/validate_logging.py` - Pending
⏳ `scripts/aeonisk/multiagent/export_dataset.py` - Pending (NEW file)
   - Modify `_generate_llm_response()` to include graded outcomes section when ML mode enabled
   - Parse graded outcomes from DM response using `parse_graded_outcomes()`
   - Validate all 6 tiers present, retry if incomplete
   - Log `llm_format_error` event if retry needed
   - Call `log_graded_outcome()` after action resolution
   - Generate unique `action_id` UUID for linking events

2. **Add session config flag** ⏳
   - Add `generate_graded_outcomes: boolean` to session config schema
   - Default to `false` (opt-in feature due to latency/cost)
   - Pass flag to DM agent via shared_state
   - Only include graded_outcomes section in prompt when enabled

3. **Add player expectation logging** ⏳
   - Modify player prompt to ask: "What do you think will happen if you succeed? If you fail?"
   - Capture expectations in action_declaration event
   - Add fields: `expected_success_outcome`, `expected_failure_outcome`

4. **Update validate_logging.py** ⏳
   - Add schema validation for `graded_outcome` event type
   - Add schema validation for `llm_format_error` event type
   - Check all 6 tiers present in outcome_explanation
   - Validate threshold formats, narrative/mechanics not empty

5. **Create export_dataset.py script** ⏳
   - Convert JSONL graded_outcome events → YAML dataset format
   - Map fields to dataset guidelines schema
   - Generate task_id sequentially
   - Include aeonisk_extra_data with module version
   - Support batch export of full sessions

6. **Test with sample session** ⏳
   - Run session with `generate_graded_outcomes: true`
   - Verify DM generates all 6 tiers
   - Check retry logic if tier missing
   - Validate JSONL output
   - Export to YAML and verify format

## Benefits

✅ **Counterfactual training data**: "What if the roll was +5 higher?"
✅ **Outcome quality grading**: Train models on success tier differentiation
✅ **Error labeling**: Track LLM format compliance for fine-tuning
✅ **Dataset export**: One-command conversion to dataset YAML format
✅ **Backward compatible**: Existing events untouched

## Risks & Mitigations

⚠️ **LLM latency**: Generating 6 outcomes per action → slower
   - Mitigation: Make it optional via session config flag `generate_graded_outcomes: true`

⚠️ **Prompt complexity**: DM prompt gets much longer
   - Mitigation: Use external YAML prompts (already implemented)

⚠️ **Token cost**: 6× narrative generation
   - Mitigation: Limit narratives to 2-3 sentences per tier, optional feature

## Files Modified

✅ `scripts/aeonisk/multiagent/mechanics.py` - Added log_graded_outcome(), log_llm_format_error()
✅ `scripts/aeonisk/multiagent/prompts/claude/en/dm.yaml` - Added graded_outcomes section
✅ `scripts/aeonisk/multiagent/outcome_parser.py` - Added parse_graded_outcomes()
⏳ `scripts/aeonisk/multiagent/dm.py` - Integration pending
⏳ `scripts/aeonisk/multiagent/player.py` - Expectation logging pending
⏳ `scripts/aeonisk/multiagent/validate_logging.py` - Schema validation pending
⏳ `scripts/aeonisk/multiagent/export_dataset.py` - NEW, pending creation

## Next Steps

Continue Phase 2 implementation starting with dm.py integration.
