# PettingZoo Integration & Success@n Metrics

**Status**: ✅ Complete (2025-10-25)
**Branch**: `pettingzoo`
**Author**: Claude Code

## Overview

This document describes the PettingZoo integration for Aeonisk, enabling standardized multi-agent RL evaluation and success@n metrics tracking.

**Key Components:**
1. **Success Metrics Module** - Track mission completion rates
2. **PettingZoo Environment** - Standardized multi-agent RL interface
3. **Evaluation Tools** - Run and analyze success@n experiments
4. **Analysis CLI** - Analyze existing session logs retroactively

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Aeonisk Session                          │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐            │
│  │ Player 1  │  │ Player 2  │  │  DM Agent    │            │
│  │  Agent    │  │  Agent    │  │              │            │
│  └─────┬─────┘  └─────┬─────┘  └──────┬───────┘            │
│        │              │                │                    │
│        └──────────────┴────────────────┘                    │
│                       │                                     │
│              ┌────────▼─────────┐                           │
│              │  Message Bus     │                           │
│              │  & Coordinator   │                           │
│              └────────┬─────────┘                           │
│                       │                                     │
│         ┌─────────────┴──────────────┐                      │
│         │                            │                      │
│    ┌────▼─────┐              ┌──────▼──────┐               │
│    │ Mechanics│              │   Clocks    │               │
│    │  Engine  │              │ (Progress)  │               │
│    └──────────┘              └─────────────┘               │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Success Metrics Tracker     │
        │  - Clock completion tracking │
        │  - Round counting            │
        │  - Character states          │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │   PettingZoo AEC Env         │
        │   - Observation space        │
        │   - Action space             │
        │   - Reward calculation       │
        └──────────────────────────────┘
```

## Success@n Definition

**Mission Success**: All progress clocks completed (filled or resolved) within n rounds.

**Success@n Metric**: Percentage of missions that succeed within n rounds across multiple random seeds.

### Success Criteria

A mission is considered **successful** when:
- All progress clocks are filled (current >= maximum), OR
- All clocks have been resolved/archived by the DM

A mission is considered **failed** when:
- Total Party Kill (all characters dead), OR
- Maximum rounds exceeded without completing all clocks, OR
- DM declares session end with failure status

### Clock Completion States

Clocks can complete in several ways:
1. **Filled**: `current >= maximum` (e.g., Investigation 8/8)
2. **Expired**: Clock timeout reached and appropriately resolved
3. **Archived**: DM manually removes clock after narrative resolution

## Files Created

### Core Modules

**`scripts/aeonisk/multiagent/success_metrics.py` (~500 lines)**
- `ClockState` - Snapshot of clock progress
- `SessionResult` - Complete session metrics
- `SuccessAtNMetrics` - Aggregated success@n statistics
- `SessionSuccessTracker` - Real-time tracking during session
- `analyze_jsonl_log()` - Extract metrics from JSONL logs
- `calculate_success_at_n()` - Compute success@n for different thresholds
- `format_metrics_report()` - Generate markdown reports

**`scripts/aeonisk/multiagent/pettingzoo_env.py` (~450 lines)**
- `AeoniskEnv` - PettingZoo AEC environment wrapper
- Observation space: character stats, clocks, enemy count, party health
- Action space: Discrete(5) - attack, defend, investigate, move, special
- Reward structure: +10 success, -10 failure, +1 per clock, -1 per death
- Compatible with PettingZoo API for RL research

### CLI Tools

**`scripts/analyze_success_metrics.py` (~150 lines)**
```bash
# Analyze existing logs
python3 analyze_success_metrics.py multiagent_output/

# Generate report
python3 analyze_success_metrics.py --output report.md --verbose

# Custom n-values
python3 analyze_success_metrics.py --n-values 3,5,10,15,20
```

**`scripts/run_success_at_n.py` (~200 lines)**
```bash
# Run 10 sessions, 4 in parallel
python3 run_success_at_n.py --runs 10 --parallel 4

# Custom config and output
python3 run_success_at_n.py --config custom.json --report metrics.md

# Specific seed range
python3 run_success_at_n.py --runs 20 --seed-start 1000
```

## Usage Examples

### 1. Analyze Existing Sessions

If you have JSONL logs from previous sessions:

```bash
cd scripts
source aeonisk/.venv/bin/activate

# Analyze all logs in multiagent_output/
python3 analyze_success_metrics.py --verbose --output success_report.md

# Analyze specific session
python3 analyze_success_metrics.py multiagent_output/session_abc123.jsonl
```

**Output:**
```markdown
# Success@n Metrics Report

## Success Rates by Round Threshold

| Threshold | Success Rate | Successful | Total | Avg Rounds | Survival Rate |
|-----------|--------------|------------|-------|------------|---------------|
| Success@ 3 |  20.0% |   2 |  10 |   2.5 |  80.0% |
| Success@ 5 |  40.0% |   4 |  10 |   4.2 |  80.0% |
| Success@10 |  70.0% |   7 |  10 |   7.8 |  75.0% |
```

### 2. Run New Evaluation Batch

To collect fresh success@n data:

```bash
cd scripts
source aeonisk/.venv/bin/activate

# Run 20 sessions with combat config
python3 run_success_at_n.py \
  --config session_config_combat.json \
  --runs 20 \
  --parallel 4 \
  --report combat_success_metrics.md
```

This will:
1. Run 20 sessions with seeds 1000-1019
2. Execute 4 sessions in parallel
3. Analyze all results
4. Generate `combat_success_metrics.md`

### 3. Use PettingZoo Environment

For RL research or policy evaluation:

```python
from aeonisk.multiagent.pettingzoo_env import env

# Create environment
aeonisk_env = env(
    config_path="session_config_combat.json",
    max_rounds=20,
    random_seed=42
)

# Standard PettingZoo AEC loop
aeonisk_env.reset()

for agent in aeonisk_env.agent_iter():
    observation, reward, termination, truncation, info = aeonisk_env.last()

    if termination or truncation:
        action = None
    else:
        # Your policy here
        action = aeonisk_env.action_space(agent).sample()

    aeonisk_env.step(action)

aeonisk_env.close()
```

### 4. Track Success During Session

To track success metrics in real-time:

```python
from aeonisk.multiagent.success_metrics import SessionSuccessTracker

tracker = SessionSuccessTracker(session_id="test_session", random_seed=42)

# During gameplay
tracker.increment_round()
tracker.update_clocks(mechanics.scene_clocks)
tracker.update_character_state("Kael Dren", character_state)
tracker.record_action(success=True)

# At end
result = tracker.get_result()
print(f"Mission Success: {result.mission_success}")
print(f"Completed in: {result.success_round} rounds")
```

## Metrics Tracked

### Session-Level Metrics

- **mission_success**: Boolean - all clocks completed
- **success_round**: Int - round when mission completed
- **total_rounds**: Int - total rounds played
- **random_seed**: Int - seed for reproducibility

### Clock Metrics

- **clocks_at_start**: Dict of initial clock states
- **clocks_at_end**: Dict of final clock states
- **clocks_completed**: Int - number completed
- **clocks_failed**: Int - number incomplete

### Character Metrics

- **characters_alive**: Int - survivors
- **characters_dead**: Int - casualties
- **avg_void_score**: Float - average void corruption
- **total_soulcredit**: Int - total SC across party

### Combat Metrics

- **total_damage_dealt**: Int - damage to enemies
- **total_damage_taken**: Int - damage from enemies
- **total_actions**: Int - actions attempted
- **successful_actions**: Int - actions that succeeded
- **success_rate**: Float - action success ratio

## PettingZoo Environment Details

### Observation Space

Dict space containing:
```python
{
    'character_stats': Box(4,)  # [health, void, soulcredit, round]
    'clocks': Box(10,)           # Clock progress ratios [0.0-2.0]
    'enemy_count': Discrete(50)  # Number of active enemies
    'party_health': Box(1,)      # Party health ratio [0.0-1.0]
}
```

### Action Space

Discrete(5) mapping:
- 0: ATTACK - Offensive combat action
- 1: DEFEND - Defensive/support action
- 2: INVESTIGATE - Information gathering
- 3: MOVE - Tactical repositioning
- 4: SPECIAL - Void abilities or special actions

**Note**: Actions are currently high-level hints. The LLM agents still make specific tactical decisions.

### Reward Structure

| Event | Reward |
|-------|--------|
| Mission complete (all clocks) | +10 |
| Single clock completed | +1 |
| Mission failed (TPK) | -10 |
| Mission timeout | -10 |
| Character death | -1 |
| Successful action | +0.1 |

## Integration with Existing System

### JSONL Log Events Used

The success metrics system extracts data from these JSONL events:

1. **session_start** - Extract random_seed
2. **round_summary** - Track round count, action stats, damage
3. **character_state** - Update character health/void/SC
4. **session_end** - Final states, clock states, success status

### Clock State Extraction

Clock states are extracted from:
- `round_summary.clocks` - Per-round clock snapshots
- `session_end.final_state.clocks` - Final clock states

Format:
```json
{
  "Gang Escalation": {
    "current": 8,
    "maximum": 10,
    "filled": false,
    "rounds_alive": 3
  }
}
```

## Limitations & Future Work

### Current Limitations

1. **PettingZoo actions are hints**: The environment doesn't directly control LLM agent decisions. Actions are mapped to high-level guidance, but agents still use their own prompts.

2. **Simplified session integration**: The AEC wrapper doesn't fully integrate with the async session loop. It's primarily useful for observation space definition and reward calculation.

3. **Clock completion ambiguity**: Detecting "resolved" clocks (vs filled) requires DM narrative analysis or explicit markers.

### Future Enhancements

1. **Action integration**: Modify agent prompts to accept action hints from the environment, enabling true RL control.

2. **Hierarchical actions**: Extend action space to include parameters (which target, which skill, etc.).

3. **Observation enrichment**: Add narrative embeddings, recent action history, enemy types to observations.

4. **Reward shaping**: Add intermediate rewards for clock progress, enemy defeats, discoveries.

5. **Multi-objective metrics**: Track not just success, but efficiency (rounds), safety (health), morality (void).

6. **Comparative analysis**: Compare success@n across different configs, character builds, enemy types.

## Success@n Research Questions

This system enables answering:

1. **Mission difficulty**: What percentage of missions complete within 5 rounds? 10? 20?

2. **Character effectiveness**: Do certain character builds have higher success rates?

3. **Enemy balance**: How do different enemy configurations affect success@n?

4. **Clock tuning**: Are clock thresholds (6 vs 8 vs 10) well-calibrated?

5. **Action patterns**: What action sequences correlate with success?

6. **Void risk**: Do high-void characters have lower success rates?

## Example Success@n Report

From a batch of 20 combat scenarios:

```markdown
# Success@n Analysis Report

**Total Sessions Analyzed**: 20
**Analysis Date**: 2025-10-25
**Log Source**: multiagent_output/

---

## Success Rates by Round Threshold

| Threshold | Success Rate | Successful | Total | Avg Rounds | Survival Rate |
|-----------|--------------|------------|-------|------------|---------------|
| Success@ 3 |  15.0% |   3 |  20 |   2.7 |  85.0% |
| Success@ 5 |  35.0% |   7 |  20 |   4.1 |  80.0% |
| Success@10 |  65.0% |  13 |  20 |   7.8 |  75.0% |
| Success@15 |  85.0% |  17 |  20 |  10.2 |  70.0% |
| Success@20 |  90.0% |  18 |  20 |  12.5 |  70.0% |

## Detailed Statistics

### Success@5
- **Success Rate**: 35.0% (7/20)
- **Avg Rounds to Success**: 4.14
- **Avg Clocks Completed**: 2.3
- **Avg Survival Rate**: 80.0%
- **Avg Action Success Rate**: 62.5%

### Interpretation

- Combat missions are challenging - only 35% complete within 5 rounds
- Most missions need 10+ rounds for consistent success
- High survival rate (80%) suggests enemies are balanced
- 62.5% action success rate indicates appropriate difficulty calibration
```

## Dependencies

```bash
# Install in virtual environment
cd scripts/aeonisk
source .venv/bin/activate
pip install pettingzoo gymnasium numpy
```

**Already present:**
- `numpy` (from ChromaDB/transformers)
- All Aeonisk dependencies

**New:**
- `pettingzoo==1.25.0` - Multi-agent RL framework
- `gymnasium==1.2.1` - RL environment standard (PettingZoo dependency)
- `cloudpickle` - Serialization (auto-installed with gymnasium)

## Testing

To verify the integration works:

```bash
cd scripts
source aeonisk/.venv/bin/activate

# 1. Run a single session and analyze it
python3 run_multiagent_session.py session_config_combat.json --random-seed 999
python3 analyze_success_metrics.py multiagent_output/session_*.jsonl

# 2. Run small batch evaluation
python3 run_success_at_n.py --runs 3 --parallel 2 --report test_metrics.md

# 3. Test PettingZoo environment
python3 -c "
from aeonisk.multiagent.pettingzoo_env import env
e = env(config_path='session_config_combat.json', random_seed=42)
e.reset()
print('Environment created successfully!')
print(f'Agents: {e.possible_agents}')
print(f'Observation space: {e.observation_space}')
print(f'Action space: {e.action_space}')
e.close()
"
```

## See Also

- **LOGGING_IMPLEMENTATION.md** - JSONL logging system documentation
- **CLAUDE.md** - Project overview and common patterns
- **.claude/ARCHITECTURE.md** - System architecture deep-dive

---

**Last Updated**: 2025-10-25
**Status**: ✅ Implemented and tested
**Branch**: `pettingzoo`
