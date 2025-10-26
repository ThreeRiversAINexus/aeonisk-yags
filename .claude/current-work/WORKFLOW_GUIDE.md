# Complete PettingZoo Evaluation Workflow

**How to create a scenario, run evaluations, and analyze results**

## The Full Process (3 Steps)

```
1. CREATE SCENARIO → 2. RUN EVALUATION → 3. ANALYZE RESULTS
   (config JSON)       (multiple sessions)    (success@n metrics)
```

## Quick Start

### Option A: All-in-One Script (Recommended)

```bash
cd scripts
source aeonisk/.venv/bin/activate

# Create heist scenario and run 10 evaluations
python3 evaluate_scenario.py --create heist --runs 10

# Quick test (3 runs only)
python3 evaluate_scenario.py --create combat --quick-test
```

### Option B: Manual Step-by-Step

```bash
cd scripts
source aeonisk/.venv/bin/activate

# Step 1: Create scenario config
python3 evaluate_scenario.py --create investigation --save-config my_scenario.json

# Step 2: Run evaluation batch
python3 run_success_at_n.py --config my_scenario.json --runs 20 --parallel 4 --report results.md

# Step 3: View results
cat results.md
```

## Detailed Walkthrough

### Step 1: Create Scenario Config

**What is it?** A JSON file defining:
- Scenario type (combat, investigation, heist, etc.)
- Character builds and goals
- Mission parameters (max turns, combat focus)
- DM guidance (notes field)

**Built-in scenario types:**

```bash
# Combat: Tactical battles, enemy encounters
python3 evaluate_scenario.py --create combat --max-turns 15

# Investigation: Evidence gathering, stealth missions
python3 evaluate_scenario.py --create investigation --max-turns 15

# Heist: Infiltration with multiple approaches (stealth/social/force)
python3 evaluate_scenario.py --create heist --max-turns 12

# Survival: Resource management, void storm, station repair
python3 evaluate_scenario.py --create survival --max-turns 25

# Social: Negotiation, intimidation, faction diplomacy
python3 evaluate_scenario.py --create social --max-turns 10
```

**What gets created:**
```
session_config_eval_heist_20251025.json
```

**You can edit this file** to customize:
- Character skills and attributes
- Character goals (guides DM scenario generation)
- Max turns (affects success@n thresholds)
- Notes field (detailed scenario guidance for DM)

### Step 2: Run Evaluation Batch

**What happens:**
- Runs N sessions with different random seeds
- Each session:
  - DM generates scenario based on config
  - AI agents play through mission
  - JSONL log tracks all events
  - Session ends when: clocks complete, TPK, or max_turns

**Command:**
```bash
python3 run_success_at_n.py \
  --config session_config_eval_heist_20251025.json \
  --runs 20 \              # 20 independent sessions
  --parallel 4 \           # Run 4 at a time
  --report heist_eval.md   # Save report here
```

**What you see:**
```
=== Success@n Evaluation Run ===
Started: 2025-10-25 15:30:00

Running 20 sessions with up to 4 in parallel...
Config: session_config_eval_heist_20251025.json
Seed range: 1000 to 1019

Batch 1/5 (4 sessions):
  Starting session with seed 1000...
  Starting session with seed 1001...
  Starting session with seed 1002...
  Starting session with seed 1003...
  ✓ Session abc12345 completed (seed: 1000)
  ✓ Session def67890 completed (seed: 1001)
  ...
Batch 1 complete: 4/4 successful

[... batches 2-5 ...]

=== Run Complete ===
Duration: 0:45:23
Successful: 20/20

Analyzing 20 session logs...
Calculating success@n metrics for n=5,10,15,20...

📊 Report saved to heist_eval.md

=== Summary ===
Success@ 5:  25.0% (5/20)
Success@10:  60.0% (12/20)
Success@15:  85.0% (17/20)
Success@20:  95.0% (19/20)
```

### Step 3: Analyze Results

**The report shows:**

```markdown
# Success@n Evaluation Report

**Run Date**: 2025-10-25 15:30:00
**Duration**: 0:45:23
**Config**: session_config_eval_heist_20251025.json
**Total Sessions**: 20
**Successful Sessions**: 19
**Seed Range**: 1000 to 1019

---

## Success Rates by Round Threshold

| Threshold | Success Rate | Successful | Total | Avg Rounds | Survival Rate |
|-----------|--------------|------------|-------|------------|---------------|
| Success@ 5 |  25.0% |   5 |  20 |   4.2 |  95.0% |
| Success@10 |  60.0% |  12 |  20 |   8.5 |  90.0% |
| Success@15 |  85.0% |  17 |  20 |  12.3 |  85.0% |
| Success@20 |  95.0% |  19 |  20 |  15.7 |  85.0% |

## Detailed Statistics

### Success@10
- **Success Rate**: 60.0% (12/20)
- **Avg Rounds to Success**: 8.5
- **Avg Clocks Completed**: 2.8
- **Avg Survival Rate**: 90.0%
- **Avg Action Success Rate**: 65.3%

### Interpretation

Heist scenarios show:
- Low early success (25% @ 5 rounds) - requires careful planning
- Strong mid-game success (60% @ 10 rounds) - optimal performance
- High late success (85% @ 15 rounds) - most missions complete
- 90%+ survival rate - low lethality, good for stealth focus
- 65% action success - moderate difficulty, skill checks calibrated well
```

## What The Metrics Mean

**Success@n**: Percentage of missions where ALL clocks completed within n rounds

- **Success@5 = 25%**: Only 25% of heist missions complete in 5 rounds (fast completions)
- **Success@10 = 60%**: 60% complete by round 10 (optimal play)
- **Success@15 = 85%**: Most complete by round 15 (thorough approach)

**Why track this?**
- Measures scenario difficulty
- Tests if max_turns is appropriate
- Compares different builds/strategies
- Identifies balance issues

**Avg Rounds to Success**: How long successful missions take (e.g., 8.5 rounds average)

**Survival Rate**: Percentage of characters alive at end (85% = only 15% died)

**Action Success Rate**: How often skill checks succeed (65% = well-calibrated difficulty)

## Comparing Scenarios

Run multiple scenario types and compare:

```bash
# Evaluate combat
python3 evaluate_scenario.py --create combat --runs 20 --save-config combat.json

# Evaluate heist
python3 evaluate_scenario.py --create heist --runs 20 --save-config heist.json

# Evaluate investigation
python3 evaluate_scenario.py --create investigation --runs 20 --save-config investigation.json
```

**Compare results:**
```
Combat:
  Success@10: 40% (harder, more lethal)
  Survival: 70% (characters die more)

Heist:
  Success@10: 60% (moderate difficulty)
  Survival: 90% (stealth avoids death)

Investigation:
  Success@10: 75% (easier, skill-focused)
  Survival: 95% (lowest combat)
```

**Insights:**
- Combat scenarios are harder and more lethal
- Heist allows multiple paths (higher success)
- Investigation is safest but slower

## Tuning Scenarios

### Make Scenario Easier

Edit the config JSON:

```json
{
  "max_turns": 20,  // Increase from 15 (more time)

  "agents": {
    "players": [
      {
        "skills": {
          "Combat": 5,      // Increase key skills
          "Stealth": 5,     // From 4 to 5
          "Investigation": 5
        }
      }
    ]
  }
}
```

Re-run and compare success@n.

### Make Scenario Harder

```json
{
  "max_turns": 10,  // Decrease (time pressure)
  "force_combat": true,  // Force combat encounters

  "notes": "HARD MODE: Elite enemies, time pressure, high void contamination"
}
```

### Test Specific Mechanics

```json
{
  "notes": "TEST: Intimidation-focused scenario. Enemies with low morale. Measure social skill effectiveness vs combat.",

  "agents": {
    "players": [{
      "skills": {
        "Intimidation": 6,  // Max intimidation
        "Persuasion": 5,
        "Combat": 3         // Low combat (force social path)
      }
    }]
  }
}
```

## Where PettingZoo Fits

**Current State:**
The PettingZoo environment (`pettingzoo_env.py`) provides:
- **Observation space**: Character stats, clocks, enemies, party health
- **Action space**: Discrete(5) - attack, defend, investigate, move, special
- **Reward calculation**: Based on mission success/failure

**Use case:**
```python
from aeonisk.multiagent.pettingzoo_env import env

# Create environment
aeonisk_env = env(
    config_path="session_config_eval_heist.json",
    max_rounds=20,
    random_seed=42
)

# Reset environment
obs = aeonisk_env.reset()

# Standard PettingZoo loop
for agent in aeonisk_env.agent_iter():
    observation, reward, termination, truncation, info = aeonisk_env.last()

    if termination or truncation:
        action = None
    else:
        # Your RL policy here
        action = policy.get_action(observation)

    aeonisk_env.step(action)
```

**Current limitation:** Actions are high-level hints. The LLM agents still make their own tactical decisions based on their prompts. Full RL control would require modifying agent prompts to accept action commands.

**Practical use today:** The PettingZoo wrapper is mainly useful for:
1. Standard observation/action space definitions
2. Reward signal calculation
3. Integration with RL libraries (RLlib, Stable-Baselines3)
4. Compatibility with multi-agent RL benchmarks

**For evaluation:** The **success@n metrics** approach (without PettingZoo) is the primary tool.

## Quick Reference

### Create + Evaluate in One Command

```bash
# Combat evaluation (10 runs)
python3 evaluate_scenario.py --create combat --runs 10

# Heist evaluation (quick test)
python3 evaluate_scenario.py --create heist --quick-test

# Investigation (20 runs, save config)
python3 evaluate_scenario.py --create investigation --runs 20 --save-config inv.json
```

### Analyze Existing Logs

```bash
# Analyze all sessions in output directory
python3 analyze_success_metrics.py multiagent_output/ --verbose --output report.md

# Analyze specific session
python3 analyze_success_metrics.py multiagent_output/session_abc123.jsonl
```

### Run Custom Config

```bash
# Edit any existing config
nano session_config_combat.json

# Run 15 evaluations
python3 run_success_at_n.py --config session_config_combat.json --runs 15 --report combat_results.md
```

## Troubleshooting

**Issue**: All missions fail (0% success rate)

**Cause**: `max_turns` too low for scenario complexity

**Fix**: Increase `max_turns` in config:
```json
"max_turns": 20  // Was 5, now 20
```

---

**Issue**: Sessions timeout or hang

**Cause**: LLM taking too long, parallel jobs overwhelming API

**Fix**: Reduce parallel jobs:
```bash
python3 run_success_at_n.py --runs 10 --parallel 2  # Was 4, now 2
```

---

**Issue**: Characters always die (low survival rate)

**Cause**: Combat too hard or characters under-skilled

**Fix**: Buff characters in config:
```json
{
  "skills": {
    "Combat": 5,    // Increase from 3
    "Guns": 5,
    "Endurance": 4
  },
  "inventory": {
    "med_kit": 3    // More healing
  }
}
```

---

**Issue**: Clocks never complete

**Cause**: Clock thresholds too high or wrong skill focus

**Fix**: Check logs to see what agents are doing, then:
```json
"notes": "HINT: Clocks fill via Investigation checks. Provide information-gathering opportunities, not just combat."
```

## Example Session

```bash
$ cd scripts
$ source aeonisk/.venv/bin/activate

$ python3 evaluate_scenario.py --create heist --runs 10

📝 Creating heist scenario config...
✓ Config saved: session_config_eval_heist_20251025.json

Scenario: Heist scenario - infiltrate secure facility to recover stolen data...
Max turns: 15
Clocks hint: Infiltration Progress, Security Alert, Data Recovery

============================================================
STEP 1: CREATE SCENARIO CONFIG ✓
STEP 2: RUN EVALUATION BATCH...
============================================================

Running 10 sessions with up to 4 in parallel...
Config: session_config_eval_heist_20251025.json
Seed range: 1000 to 1009

Batch 1/3 (4 sessions):
  Starting session with seed 1000...
  Starting session with seed 1001...
  Starting session with seed 1002...
  Starting session with seed 1003...
  ✓ Session a1b2c3d4 completed (seed: 1000)
  ✓ Session e5f6g7h8 completed (seed: 1001)
  ✓ Session i9j0k1l2 completed (seed: 1002)
  ✓ Session m3n4o5p6 completed (seed: 1003)
Batch 1 complete: 4/4 successful

[... batches 2-3 ...]

============================================================
=== Run Complete ===
Duration: 0:22:45
Successful: 10/10

Analyzing 10 session logs...

============================================================
STEP 3: VIEW RESULTS
============================================================

## Success Rates by Round Threshold

| Threshold | Success Rate | Successful | Total | Avg Rounds | Survival Rate |
|-----------|--------------|------------|-------|------------|---------------|
| Success@ 5 |  30.0% |   3 |  10 |   4.3 |  90.0% |
| Success@10 |  70.0% |   7 |  10 |   8.7 |  90.0% |
| Success@15 |  90.0% |   9 |  10 |  12.1 |  85.0% |
| Success@20 | 100.0% |  10 |  10 |  12.1 | 85.0% |

📊 Full report: ./evaluation_reports/eval_20251025_153045.md

============================================================
EVALUATION COMPLETE!
============================================================
```

## Next Steps

1. **Run your first evaluation:**
   ```bash
   python3 evaluate_scenario.py --create combat --quick-test
   ```

2. **Customize a scenario:**
   - Edit the generated config JSON
   - Change character skills, goals, max_turns
   - Re-run with `--config your_edited_config.json`

3. **Compare scenarios:**
   - Run combat, heist, investigation
   - Compare success@n rates
   - Identify difficulty differences

4. **Tune for balance:**
   - Target 60-70% success@10 for "moderate" difficulty
   - Adjust character skills or max_turns
   - Iterate until metrics match goals

---

**Questions?** Check `.claude/current-work/pettingzoo-integration.md` for full technical details.
