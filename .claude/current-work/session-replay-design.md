# Session Replay Feature - Design Document

**Branch:** `feature/session-replay`
**Status:** Planning Phase
**Date:** 2025-10-24

## Goal
Build a deterministic replay system that can replay multi-agent sessions from JSONL logs up to round N, reproducing the exact same gameplay for debugging and analysis.

## User Requirements
- **Use Case:** Debug/analyze specific scenarios
- **LLM Handling:** Cache LLM responses from original sessions for deterministic replay
- **Output:** New JSONL log file + console output
- **Control:** Ability to replay rounds 1-N (partial replay)

## Architecture

### Phase 1: Extend Logging to Capture LLM Calls
**Files to modify:**
- `scripts/aeonisk/multiagent/base.py` - Add LLM call wrapper
- `scripts/aeonisk/multiagent/mechanics.py` - Add random seed to session_start event

**New event types:**
```json
{
  "event_type": "llm_call",
  "ts": "...",
  "session": "...",
  "round": 1,
  "agent_id": "player_01",
  "agent_type": "player",
  "prompt": "...",  // Full prompt sent to LLM
  "response": "...", // Full response from LLM
  "model": "claude-3-5-sonnet-20241022",
  "temperature": 0.8,
  "tokens": {"input": 1234, "output": 567}
}

{
  "event_type": "session_start",
  "...": "...",
  "random_seed": 42  // NEW: Python random seed for session
}
```

**Implementation:**
1. Create `LLMCallLogger` class to wrap all LLM API calls
2. Inject into DM, Player, and Enemy agents
3. Log prompt + response for every LLM call
4. Add `--random-seed` arg to `run_multiagent_session.py`
5. Log seed in `session_start` event

### Phase 2: Build Replay Engine
**New file:** `scripts/aeonisk/multiagent/replay.py`

**Core classes:**
```python
class ReplaySession:
    """Replays a session from JSONL log up to round N."""

    def __init__(self, log_path: str, replay_to_round: int):
        self.log_path = log_path
        self.replay_to_round = replay_to_round
        self.events = []  # Loaded from JSONL
        self.llm_cache = {}  # agent_id + round -> response
        self.random_seed = None

    def load_log(self):
        """Parse JSONL and build replay state."""
        # Extract: session_start, scenario, llm_calls, actions, etc.
        # Build llm_cache for deterministic replay

    def replay(self):
        """Execute replay using cached LLM responses."""
        # Initialize session with same config
        # Set random.seed(self.random_seed)
        # Inject MockLLMClient that returns cached responses
        # Run session up to replay_to_round
```

**MockLLMClient:**
```python
class MockLLMClient:
    """Replays LLM responses from cache instead of making API calls."""

    def __init__(self, cache: dict):
        self.cache = cache
        self.call_index = {}  # Track which call we're on per agent

    async def send_message(self, messages, **kwargs):
        """Return cached response instead of calling API."""
        agent_id = kwargs.get('agent_id')  # Need to pass this
        call_num = self.call_index.get(agent_id, 0)
        response = self.cache[(agent_id, call_num)]
        self.call_index[agent_id] = call_num + 1
        return response
```

### Phase 3: CLI Integration
**File to modify:** `scripts/aeonisk/multiagent/main.py`

**New arguments:**
```python
parser.add_argument(
    '--replay',
    metavar='LOGFILE',
    help='Replay a session from JSONL log file'
)

parser.add_argument(
    '--replay-to-round',
    type=int,
    default=999,
    help='Replay up to this round (default: all)'
)

parser.add_argument(
    '--random-seed',
    type=int,
    help='Random seed for reproducible sessions'
)
```

**Usage:**
```bash
# Normal session with seed
python3 run_multiagent_session.py session_config.json --random-seed 42

# Replay first 3 rounds
python3 run_multiagent_session.py --replay multiagent_output/session_xyz.jsonl --replay-to-round 3
```

### Phase 4: Output and Analysis
**File to modify:** `scripts/aeonisk/multiagent/session.py`

**Features:**
- Generate new JSONL with `_replay` suffix: `session_xyz_replay.jsonl`
- Console output shows replay progress
- Optional: Diff mode showing differences from original

## Data Completeness Assessment

**What's currently logged (✓):**
- Session config
- Scenario details (theme, location, situation)
- Character stats and state
- Action declarations (intent, description, DC estimate)
- Action resolutions (d20 roll, total, margin, tier, narration)
- Enemy spawns (full stats, position, tactics)
- Combat damage (dealt, soaked, final)
- Void/soulcredit changes
- Clock states
- Round summaries

**What's missing (needs Phase 1):**
- ✗ LLM prompts and responses
- ✗ Random seed
- ✗ Enemy tactical decision reasoning
- ✗ DM adjudication prompts

## Implementation Roadmap

1. **Phase 1: LLM Logging** (PARTIALLY COMPLETE)
   - [x] Add `LLMCallLogger` class with logging infrastructure
   - [x] Add `MockLLMClient` for replay
   - [x] Add random seed to session config/logging
   - [x] Inject llm_logger instances into all agents (infrastructure ready)
   - [ ] **TODO:** Instrument individual LLM calls in agents (see below)
   - [ ] Test: Run session and verify llm_call events in JSONL

2. **Phase 2: Replay Engine** (INFRASTRUCTURE COMPLETE)
   - [x] Create `replay.py` with `ReplaySession` class
   - [x] Implement log parser and LLM cache builder
   - [x] Add validation for replay completeness
   - [ ] **TODO:** Refactor session to accept custom LLM client
   - [ ] Test: Replay a simple 1-round session

3. **Phase 3: CLI Integration** (COMPLETE)
   - [x] Add `--random-seed` arg to main.py
   - [ ] **TODO:** Add `--replay`, `--replay-to-round` args
   - [ ] Wire up ReplaySession to main.py
   - [ ] Test: End-to-end replay from CLI

4. **Phase 4: Polish** (NOT STARTED)
   - [ ] Add console output formatting
   - [ ] Generate replay JSONL output
   - [ ] Add validation (compare original vs replay)
   - [ ] Write documentation

## Current Status (2025-10-24)

### ✅ Complete
1. **Random seed infrastructure**
   - Session accepts `random_seed` parameter
   - Seed logged in `session_start` event
   - CLI argument `--random-seed` working
   - `random.seed()` called on session init

2. **LLM logging infrastructure**
   - `LLMCallLogger` class created (llm_logger.py)
   - `MockLLMClient` class created for replay
   - `JSONLLogger.write_event()` public method added
   - All agents receive `llm_logger` instance automatically

3. **Replay engine core**
   - `ReplaySession` class loads and parses JSONL logs
   - Extracts config, random seed, LLM cache
   - Validates log completeness
   - Ready to execute replay (pending LLM instrumentation)

### 🚧 In Progress
1. **LLM call instrumentation**
   - Need to wrap actual `client.messages.create` calls
   - DM agent: 6 call sites identified
   - Player agents: TBD
   - Enemy agents: TBD

### 📋 TODO
1. **Instrument LLM calls** (Critical Path)
   - Add logging after each `client.messages.create` call
   - Pattern (example for DM agent line 270):
     ```python
     response = await asyncio.to_thread(
         client.messages.create,
         model=model,
         max_tokens=500,
         temperature=0.9,
         messages=[{"role": "user", "content": scenario_prompt}]
     )
     llm_text = response.content[0].text.strip()

     # ADD THIS:
     if self.llm_logger:
         self.llm_logger._log_llm_call(
             messages=[{"role": "user", "content": scenario_prompt}],
             response=llm_text,
             model=model,
             temperature=0.9,
             tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
             current_round=None,  # or actual round if available
             call_sequence=self.llm_logger.call_count
         )
     ```

   - **DM agent** (dm.py):
     - Line 270: Scenario generation
     - Line 298: Scenario retry
     - Line 1572: Action adjudication (main)
     - Line 2977: Round synthesis
     - Line 3051: Unknown context
     - Line 3114: Unknown context

   - **Player agents** (player.py): TBD
   - **Enemy agents** (enemy_agent.py): TBD

2. **Refactor session for custom LLM client**
   - Allow injecting MockLLMClient during replay
   - Modify agent creation to use custom client

3. **Add replay CLI integration**
   - `--replay LOGFILE` argument
   - `--replay-to-round N` argument
   - Wire to `replay.replay_from_log()`

4. **Testing**
   - Run session with `--random-seed 42`
   - Verify JSONL contains `random_seed` and `llm_call` events
   - Run replay and compare outputs

## Testing Strategy

**Test Suite:**
1. **Logging test:** Run session with `--random-seed 42`, verify llm_call events logged
2. **Replay test:** Replay the session, verify identical events
3. **Partial replay test:** Replay to round 2 of 5-round session
4. **Seed test:** Two sessions with same seed should have identical rolls
5. **Combat test:** Replay combat session with enemy agents

## Known Limitations

1. **Log size:** LLM prompts/responses can be large (1-5KB each)
   - Mitigation: Optional flag `--log-llm-calls` (default: true)

2. **API changes:** If prompts change between versions, replay may diverge
   - Mitigation: Log version number in session_start

3. **Time-based behaviors:** Any code using `time.time()` won't replay exactly
   - Current code review: No time-based game logic found

## Open Questions

1. Should we compress LLM responses in the log? (gzip)
2. Do we need a "replay debugger" that can pause/inspect state?
3. Should replay support "branch from round N" to test alternative outcomes?

## File Structure

```
scripts/
├── aeonisk/
│   └── multiagent/
│       ├── replay.py           # NEW: Replay engine
│       ├── llm_logger.py       # NEW: LLM call logging wrapper
│       ├── base.py             # MODIFY: Add LLM logging hooks
│       ├── main.py             # MODIFY: Add replay CLI args
│       ├── session.py          # MODIFY: Support replay mode
│       └── mechanics.py        # MODIFY: Add seed to session_start
└── run_multiagent_session.py  # Entry point (no changes)

.claude/
└── current-work/
    └── session-replay-design.md  # This document
```

## Success Criteria

✓ Can replay any session from JSONL log
✓ Replay produces identical d20 rolls (via seed)
✓ Replay produces identical LLM responses (via cache)
✓ Can replay partial sessions (rounds 1-N)
✓ Generates new JSONL log for comparison
✓ Console output shows replay progress
✓ Works with combat scenarios (enemy agents)
