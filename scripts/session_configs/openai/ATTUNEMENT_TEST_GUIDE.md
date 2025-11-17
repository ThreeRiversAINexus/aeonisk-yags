# Seed Attunement System Test Guide

## Config: `session_config_attunement_test_openai.json`

### Purpose
Comprehensive test fixture for the seed attunement system implementation. Tests all major mechanics:
- Basic altar attunement with quality bonuses
- Echo-Calibrator portable attunement
- Echo-Calibrator upkeep payment (every 3rd use)
- Multiple energy type conversions
- Seed consumption tracking

### Test Character: Seed Keeper Zephyr
- **Willpower**: 5 (primary attunement attribute)
- **Attunement skill**: 4
- **Tech skill**: 4 (for Echo-Calibrator DC 16 check)
- **Starting Drip**: 25 (for Echo-Calibrator upkeep)
- **Starting Raw Seeds**: 5 (fresh and aged)

### Scenario Setup
**Location**: Hollow Exchange Testing Chamber
**Void Level**: 3/10 (controlled environment)

**Available Altars**:
- `alt_test_basic` (quality 2, +1 bonus) - Minor shrine
- `alt_test_master` (quality 7, +2 bonus) - Major temple

**Equipment**:
- Echo-Calibrator (portable attunement device)
- Ritual Focus (primary tool)

### Test Flow (5 Rounds)

#### Round 1: Basic Altar Attunement (Drip)
**Action**: Attune Raw Seed → 20 Drip at basic altar
**Mechanics**:
- Altar quality 2 → +1 bonus (DC 20 → DC 19)
- Roll: Willpower (5) + Attunement (4) + d20 + 1 vs DC 20
- Expected: Seed consumed, +20 Drip gained

#### Round 2: Echo-Calibrator Attunement (Spark)
**Action**: Attune Raw Seed → 5 Spark with Echo-Calibrator
**Mechanics**:
- DC 16 check: Agility (4) + Tech (4) + d20 >= 16
- Portable attunement (no altar needed)
- Usage count: 1/3 (track for upkeep)
- Expected: Seed consumed, +5 Spark gained

#### Round 3: Master Altar Attunement (Breath)
**Action**: Attune Raw Seed → 100 Breath at master altar
**Mechanics**:
- Altar quality 7 → +2 bonus (DC 20 → DC 18)
- Roll: Willpower (5) + Attunement (4) + d20 + 2 vs DC 20
- Expected: Seed consumed, +100 Breath gained

#### Round 4: Echo-Calibrator with Upkeep (Grain)
**Action**: Attune Raw Seed → 50 Grain with Echo-Calibrator
**Mechanics**:
- DC 16 check: Agility (4) + Tech (4) + d20 >= 16
- Usage count: 3/3 → **UPKEEP REQUIRED**
- Pay 1 Drip upkeep before attunement
- Expected: Seed consumed, +50 Grain gained, -1 Drip upkeep

#### Round 5: Final Validation
**Action**: Attune final Raw Seed (any energy type)
**Mechanics**:
- Player chooses altar or Echo-Calibrator
- Verify conversion rates work correctly
- Expected: Seed consumed, energy gained per type

### Expected Final State

**Energy Purse**:
```json
{
  "breath": 100,
  "grain": 50,
  "drip": 44,    // 25 start + 20 round 1 - 1 upkeep round 4
  "spark": 5,
  "seeds": []     // All 5 seeds consumed
}
```

**Item Metadata**:
```json
{
  "Echo-Calibrator": {
    "usage_count": 2  // or 3 if round 5 uses it
  }
}
```

**Void**: 1-3 (may increase from failed Echo-Calibrator checks)

### JSONL Verification

**Key events to validate**:
1. 5 `action_resolution` events with `attunement` field
2. Each attunement shows:
   - `success`: true/false
   - `seed_consumed`: true (always)
   - `energy_gained`: 100/50/20/5 (by type)
   - `altar_bonus`: 0/1/2 (if altar used)
   - `echo_calibrator_used`: true/false
   - `upkeep_paid`: true (round 4 only)
3. `character_data` events show:
   - `energy_purse` accumulating currency
   - `seeds` array shrinking (5→4→3→2→1→0)
   - `item_metadata` tracking Echo-Calibrator usage

### Conversion Rates Reference

| Energy Type | Raw Seed → Hollows | Relative Value |
|-------------|-------------------|----------------|
| **Breath**  | 1 → 100          | Least valuable |
| **Grain**   | 1 → 50           | Common        |
| **Drip**    | 1 → 20           | Moderate      |
| **Spark**   | 1 → 5            | Most valuable |

### Running the Test

```bash
# Standard run (INFO logs)
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/openai/session_config_attunement_test_openai.json

# Debug mechanics (DEBUG logs)
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/openai/session_config_attunement_test_openai.json \
  --log-level DEBUG
```

### Analysis Commands

```bash
# Quick summary
python scripts/analyze_session.py session_*.jsonl

# Find attunement actions
python scripts/analyze_session.py session_*.jsonl \
  --search event_type=action_resolution \
  --fields action,attunement.success,attunement.energy_gained

# Track seed consumption
python scripts/analyze_session.py session_*.jsonl \
  --search event_type=character_data \
  --fields round,energy_purse.seeds
```

### Success Criteria Checklist

- [ ] 5 attunement actions declared and resolved
- [ ] All 5 Raw Seeds consumed (seeds array goes from 5 → 0)
- [ ] Energy gains correct:
  - [ ] Breath: 100 gained
  - [ ] Grain: 50 gained
  - [ ] Drip: 20 gained (net +19 after upkeep)
  - [ ] Spark: 5 gained
- [ ] Altar bonuses applied:
  - [ ] Basic altar (+1): DC 20 → 19
  - [ ] Master altar (+2): DC 20 → 18
- [ ] Echo-Calibrator mechanics:
  - [ ] DC 16 Agility+Tech checks logged
  - [ ] Usage tracking functional (3rd use triggers upkeep)
  - [ ] Upkeep payment logged (1 Drip consumed round 4)
- [ ] JSONL integrity:
  - [ ] `attunement` field present in action_resolution
  - [ ] `seed_consumed=true` for all attunements
  - [ ] Energy purse updates match expected state

### Known Edge Cases to Watch

1. **Failed Ritual Roll**: If ritual fails (roll < DC 20), seed still consumed but no energy gained
2. **Failed Echo-Calibrator Check**: If DC 16 check fails, +1 Void penalty applied
3. **Insufficient Upkeep**: If Drip < 1 on round 4, Echo-Calibrator usage should fail validation
4. **Unskilled Penalty**: If Attunement skill = 0, -5 penalty applies (not applicable here)

### Integration with Existing Systems

This test validates attunement integrates correctly with:
- **Energy economy**: EnergyPurse currency tracking
- **Seed lifecycle**: Seed consumption and degradation
- **Altar infrastructure**: SharedState altar tracking, quality bonuses
- **Item metadata**: Echo-Calibrator usage persistence
- **Ritual mechanics**: DC calculation, Willpower+skill+d20 formula
- **JSONL logging**: AttunementEffect schema in action_resolution

---

**Created**: 2025-11-16
**Last Updated**: 2025-11-16
**Implementation Branch**: economy-and-vending
**Related Files**:
- `scripts/aeonisk/multiagent/mechanics.py` (validate_attunement, execute_attunement)
- `scripts/aeonisk/multiagent/schemas/action_effects.py` (AttunementEffect)
- `scripts/aeonisk/multiagent/schemas/player_action.py` (ATTUNE action type)
- `tests/unit/test_attunement.py` (46 validation tests)
