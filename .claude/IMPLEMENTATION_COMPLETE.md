# Graded Outcomes ML Logging - IMPLEMENTATION COMPLETE

**Date:** 2025-10-29
**Status:** ✅ Core implementation done, ready for testing

## What We Built

**Dual graded outcomes system** that captures player predictions vs. DM ground truth for ML training.

### Key Features

1. **Player Predictions** - Players predict all 6 outcome tiers when declaring actions
2. **DM Ground Truth** - DM generates authoritative 6 tiers when resolving
3. **Linking** - action_id UUIDs connect player predictions to DM outcomes
4. **Error Tracking** - Logs LLM format mistakes for fine-tuning
5. **Dataset Ready** - Captures all fields needed for normalized YAML export

## New Event Types

### 1. Enhanced `action_declaration`
```json
{
  "event_type": "action_declaration",
  "predicted_outcomes": {
    "critical_failure": {"narrative": "...", "mechanical_effect": "..."},
    "failure": {"narrative": "...", "mechanical_effect": "..."},
    // ... 4 more tiers
  }
}
```

### 2. NEW `graded_outcome`
```json
{
  "event_type": "graded_outcome",
  "action_id": "uuid-here",
  "scenario_context": "...",
  "environment": "...",
  "stakes": "...",
  "goal": "...",
  "attribute_used": "Intelligence",
  "skill_used": "Systems",
  "roll_formula": "3 × 3 = 9; 9 + d20",
  "difficulty_guess": 20,
  "actual_roll": {"d20": 3, "total": 12, "margin": -8},
  "outcome_explanation": {
    "critical_failure": {"threshold": "...", "narrative": "...", "mechanical_effect": "...", "occurred": false},
    // ... 6 tiers total, one marked occurred: true
  },
  "rationale": "...",
  "llm_generation_quality": {"format_valid": true, "retry_count": 0, ...}
}
```

### 3. NEW `llm_format_error`
```json
{
  "event_type": "llm_format_error",
  "agent_type": "dm",
  "error_type": "missing_outcome_tier",
  "details": {"missing_tiers": ["excellent_success"]},
  "raw_response": "...",
  "retry_attempt": 0,
  "resolution": "logged_partial"
}
```

## Files Modified (7 files)

1. **mechanics.py** - Added log_graded_outcome(), log_llm_format_error(), updated log_action_declaration()
2. **dm.yaml** - Added graded_outcomes section (80 lines)
3. **player.yaml** - Added outcome_prediction section (106 lines)
4. **outcome_parser.py** - Added parse_graded_outcomes() function
5. **player.py** - Parse predicted outcomes from LLM response
6. **session.py** - Pass predicted outcomes to logger
7. **dm.py** - Generate, parse, log DM graded outcomes (+157 lines)

## Testing Status

- ✅ Code compiles
- ⏳ Need to run test session to verify:
  - Players generate predicted outcomes
  - DM generates graded outcomes
  - Events log correctly to JSONL
  - No format errors

## Next Steps (Priority Order)

1. **Test with actual session** - Run `session_config_combat.json` and check logs
2. **Add validation** - Update validate_logging.py with new schemas
3. **Create export script** - export_dataset.py (JSONL → normalized YAML)

## Quick Test Command

```bash
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_configs/session_config_combat.json

# Check logs
grep '"event_type":"graded_outcome"' ../../multiagent_output/session_*.jsonl | wc -l
grep '"predicted_outcomes"' ../../multiagent_output/session_*.jsonl | wc -l
```

## Known Limitations

- No session config flag (always generates graded outcomes)
- No retry logic for incomplete DM outcomes (just logs error)
- Player predictions optional (won't crash if missing)
- Export script not yet created

## ML Training Value

**What we can train on:**
- Action selection (right attribute/skill?)
- DC calibration (player estimate vs. DM actual)
- Outcome prediction accuracy (player vs. DM narratives)
- Consequence understanding (mechanical effects scaling)
- Counterfactual reasoning ("what if margin was different?")
