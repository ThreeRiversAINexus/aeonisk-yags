# Session Replay - Implementation Status

**Branch:** `feature/session-replay`
**Date:** 2025-10-24
**Commit:** 254a2f1

## Summary

The **infrastructure for session replay is now complete**. The system can:
- ✅ Track and log random seeds for deterministic dice rolls
- ✅ Provide framework for logging LLM calls (prompts + responses)
- ✅ Load and parse replay logs with validation
- ✅ Cache LLM responses for replay
- ⚠️ **Missing:** Actual instrumentation of LLM calls in agent code

## What Works Now

### 1. Random Seed System (✅ Complete)
```bash
# Run a session with fixed seed
python3 run_multiagent_session.py session_config.json --random-seed 42

# This will:
# - Set random.seed(42) for deterministic dice rolls
# - Log seed in session_start event
# - All d20 rolls will be identical on re-runs with same seed
```

The JSONL log will contain:
```json
{
  "event_type": "session_start",
  "random_seed": 42,
  "config": {...},
  ...
}
```

### 2. LLM Logging Infrastructure (✅ Complete)
Every agent (DM, Player, Enemy) receives an `LLMCallLogger` instance that can log:
```json
{
  "event_type": "llm_call",
  "agent_id": "dm_01",
  "agent_type": "dm",
  "call_sequence": 0,
  "prompt": [...],
  "response": "...",
  "model": "claude-3-5-sonnet-20241022",
  "temperature": 0.7,
  "tokens": {"input": 1234, "output": 567}
}
```

**Pattern to log an LLM call:**
```python
# After making LLM call in any agent:
if self.llm_logger:
    self.llm_logger._log_llm_call(
        messages=messages,
        response=response_text,
        model=model,
        temperature=temperature,
        tokens={'input': response.usage.input_tokens,
                'output': response.usage.output_tokens},
        current_round=self.current_round,  # if available
        call_sequence=self.llm_logger.call_count
    )
```

### 3. Replay Engine (✅ Infrastructure Complete)
```python
from aeonisk.multiagent.replay import replay_from_log

# Load and validate a log
result = replay_from_log("multiagent_output/session_xyz.jsonl", replay_to_round=3)
```

This will:
- Parse the JSONL log
- Extract session config and random seed
- Build LLM response cache
- Validate replay-ability
- Show what's missing (if anything)

**Standalone tool:**
```bash
cd scripts/aeonisk/multiagent
python3 replay.py ../../../multiagent_output/session_xyz.jsonl 3
```

## What's Missing (Critical Path)

### 1. Instrument LLM Calls in Agents ⚠️
Currently, agents make LLM calls but don't log them. Need to add logging after each `client.messages.create()` call.

**DM Agent (dm.py)** - 6 locations:
```python
# Line ~270: Scenario generation
response = await asyncio.to_thread(
    client.messages.create,
    model=model,
    max_tokens=500,
    temperature=0.9,
    messages=[{"role": "user", "content": scenario_prompt}]
)
llm_text = response.content[0].text.strip()

# ADD THIS BLOCK:
if self.llm_logger:
    self.llm_logger._log_llm_call(
        messages=[{"role": "user", "content": scenario_prompt}],
        response=llm_text,
        model=model,
        temperature=0.9,
        tokens={'input': response.usage.input_tokens,
                'output': response.usage.output_tokens},
        current_round=None,
        call_sequence=self.llm_logger.call_count
    )
```

**Locations to instrument:**
- `dm.py`: Lines ~270, 298, 1572, 2977, 3051, 3114
- `player.py`: TBD (search for `messages.create`)
- `enemy_agent.py`: TBD (search for `messages.create`)

**Helper script to find locations:**
```bash
grep -n "messages\.create" scripts/aeonisk/multiagent/*.py
```

### 2. Add Replay CLI Arguments
Add to `main.py`:
```python
parser.add_argument(
    '--replay',
    metavar='LOGFILE',
    help='Replay a session from JSONL log'
)

parser.add_argument(
    '--replay-to-round',
    type=int,
    default=999,
    help='Replay up to this round'
)
```

Wire to replay engine in `main()`:
```python
if args.replay:
    from .multiagent.replay import replay_from_log
    result = replay_from_log(args.replay, args.replay_to_round)
    return
```

### 3. Inject MockLLMClient During Replay
Currently agents create their own Anthropic clients. For replay, we need to:
1. Allow passing a custom LLM client to agent `__init__`
2. During replay, pass `MockLLMClient(llm_cache)` instead
3. MockLLMClient returns cached responses instead of calling API

## Testing Plan

### Phase 1: Test Random Seed (Ready Now)
```bash
# Run same config with same seed twice
python3 run_multiagent_session.py session_config.json --random-seed 42
mv multiagent_output/session_*.jsonl session_run1.jsonl

python3 run_multiagent_session.py session_config.json --random-seed 42
mv multiagent_output/session_*.jsonl session_run2.jsonl

# Compare d20 rolls - should be identical
diff <(jq -c 'select(.event_type=="action_resolution") | .roll.d20' session_run1.jsonl) \
     <(jq -c 'select(.event_type=="action_resolution") | .roll.d20' session_run2.jsonl)
```

**Expected:** No differences (identical dice rolls)

### Phase 2: Test LLM Logging (After Instrumentation)
```bash
python3 run_multiagent_session.py session_config.json --random-seed 42

# Check for llm_call events
jq 'select(.event_type=="llm_call")' multiagent_output/session_*.jsonl | head -5
```

**Expected:** Should see llm_call events with prompts and responses

### Phase 3: Test Full Replay (After All Steps Complete)
```bash
# Create original session
python3 run_multiagent_session.py session_config.json --random-seed 42
LOG_FILE=$(ls -t multiagent_output/*.jsonl | head -1)

# Replay first 3 rounds
python3 run_multiagent_session.py --replay $LOG_FILE --replay-to-round 3

# Compare
diff $LOG_FILE multiagent_output/*_replay.jsonl
```

**Expected:** Identical events through round 3

## File Structure

```
scripts/aeonisk/multiagent/
├── llm_logger.py          # NEW: LLMCallLogger + MockLLMClient
├── replay.py              # NEW: ReplaySession + validation
├── session.py             # MODIFIED: random_seed, llm_logger injection
├── mechanics.py           # MODIFIED: JSONLLogger accepts seed
├── main.py                # MODIFIED: --random-seed arg
├── dm.py                  # MODIFIED: llm_logger param
├── player.py              # TODO: Add llm_logger param + instrumentation
└── enemy_agent.py         # TODO: Add llm_logger param + instrumentation
```

## Next Steps (Priority Order)

1. **[HIGH] Instrument DM LLM calls** (~30 min)
   - Add logging after all 6 `client.messages.create` calls in dm.py
   - Test: Verify llm_call events appear in JSONL

2. **[HIGH] Instrument Player LLM calls** (~20 min)
   - Find all LLM calls in player.py
   - Add logging (same pattern as DM)

3. **[MEDIUM] Instrument Enemy LLM calls** (~20 min)
   - Find all LLM calls in enemy_agent.py
   - Add logging

4. **[HIGH] Add replay CLI args** (~10 min)
   - `--replay` and `--replay-to-round`
   - Wire to replay.replay_from_log()

5. **[MEDIUM] Refactor for MockLLMClient** (~1 hour)
   - Allow custom LLM client in agent __init__
   - Inject MockLLMClient during replay

6. **[LOW] Test and validate** (~1 hour)
   - Run full test suite
   - Compare original vs replay
   - Document any edge cases

## Estimated Time to Complete
- **With instrumentation done:** 2-3 hours to fully working replay
- **Current infrastructure:** Ready for incremental instrumentation

## Usage Examples (When Complete)

### Create Reproducible Session
```bash
python3 run_multiagent_session.py config.json --random-seed 12345
```

### Replay Entire Session
```bash
python3 run_multiagent_session.py --replay session_abc.jsonl
```

### Replay First 5 Rounds (for debugging)
```bash
python3 run_multiagent_session.py --replay session_abc.jsonl --replay-to-round 5
```

### Validate Replay
```bash
cd scripts/aeonisk/multiagent
python3 replay.py ../../../multiagent_output/session_abc.jsonl
```

## Known Limitations

1. **LLM non-determinism:** Even with caching, if prompts change between versions, replay will diverge
   - Mitigation: Log full prompts, not just responses
   - Already implemented ✓

2. **Time-based behaviors:** Any code using `time.time()` won't replay exactly
   - Current audit: No time-based game logic found
   - Random seed uses time only for default seed generation

3. **Log size:** LLM prompts/responses can be large (1-5KB each)
   - A 10-round session with 20 LLM calls = ~50-100KB extra log data
   - Acceptable trade-off for replay functionality

4. **Async timing:** Agent message ordering may vary slightly
   - Replay should handle this via event sequencing
   - Needs testing to confirm

## References

- **Full Design:** `.claude/current-work/session-replay-design.md`
- **LLM Logger:** `scripts/aeonisk/multiagent/llm_logger.py`
- **Replay Engine:** `scripts/aeonisk/multiagent/replay.py`
- **Commit:** 254a2f1 - "feat: Add session replay infrastructure (Phase 1 - Foundation)"
