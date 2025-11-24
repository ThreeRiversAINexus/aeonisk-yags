# Custom Log Levels for Aeonisk Multi-Agent System

## Overview

Two custom log levels have been added to reduce noise and enable targeted debugging:

- **LLM (15)** - API calls, prompts, responses, tokens, rate limiting, cache operations
- **TRACE (5)** - Ultra-verbose debugging: stacktraces, line-by-line parsing, state transitions

## Log Level Hierarchy

```
TRACE (5) < DEBUG (10) < LLM (15) < INFO (20) < WARNING (30) < ERROR (40) < CRITICAL (50)
```

## Usage

### Command Line

```bash
# Show only LLM API calls (no mechanics debug)
python3 scripts/run_multiagent_session.py config.json --log-level LLM

# Show ultra-verbose debugging
python3 scripts/run_multiagent_session.py config.json --log-level TRACE

# Show everything including LLM calls
python3 scripts/run_multiagent_session.py config.json --log-level DEBUG

# Standard mode (no LLM or debug spam)
python3 scripts/run_multiagent_session.py config.json --log-level INFO
```

### In Code

```python
# Import custom log levels (required before using)
from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401

import logging
logger = logging.getLogger(__name__)

# Use LLM level for API operations
logger.llm("API call to Claude: prompt_length=1500, model=sonnet-4")
logger.llm(f"✓ API retry succeeded after {attempt} attempts")
logger.llm(f"Cache hit for {agent_id}, returning {len(response)} chars")

# Use TRACE level for ultra-verbose debugging
logger.trace("Entering damage extraction loop")
logger.trace(f"Token claim state: {token_state}")
logger.trace(f"Parsing line: {line_content}")
```

### Setting Log Level Programmatically

```python
import logging
from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401

# Set logger to LLM level
logger = logging.getLogger('my_module')
logger.setLevel(logging.LLM)

# Set logger to TRACE level
logger.setLevel(logging.TRACE)
```

## Use Cases

### Scenario 1: Debug Mechanics Without LLM Spam

**Problem:** You're debugging damage calculation but logs are flooded with API calls.

**Solution:** Use DEBUG level (shows mechanics, hides LLM)

```bash
python3 scripts/run_multiagent_session.py config.json --log-level DEBUG
```

**Output:** Mechanics debug messages visible, LLM calls hidden.

### Scenario 2: Monitor API Usage Only

**Problem:** You want to see API calls, rate limiting, and cache behavior without mechanics spam.

**Solution:** Use LLM level (shows API, hides mechanics debug)

```bash
python3 scripts/run_multiagent_session.py config.json --log-level LLM
```

**Output:** LLM operations visible, mechanics debug hidden.

### Scenario 3: Deep Debugging Session Hangs

**Problem:** Session hangs during parsing, need line-by-line trace.

**Solution:** Use TRACE level (ultra-verbose)

```bash
python3 scripts/run_multiagent_session.py config.json --log-level TRACE
```

**Output:** Every parsing step, state transition, and internal operation logged.

### Scenario 4: Production Mode

**Problem:** Want clean logs with only important events.

**Solution:** Use INFO level (default)

```bash
python3 scripts/run_multiagent_session.py config.json --log-level INFO
```

**Output:** Session progress, warnings, errors only. No debug or LLM spam.

## Log Analysis

### Extract LLM Calls from Log File

```bash
# All LLM operations
grep "LLM" multiagent.log

# API retries only
grep "✓.*retries" multiagent.log

# Cache hits
grep "Cache hit" multiagent.log

# Rate limiter info
grep "APIRateLimiter" multiagent.log
```

### Extract TRACE Messages

```bash
# All TRACE level messages
grep "TRACE" multiagent.log

# Parsing operations
grep "TRACE.*parsing" multiagent.log -i

# State transitions
grep "TRACE.*state" multiagent.log -i
```

## Migration Guide

### Converting Existing Logs

When you find log statements that should use custom levels:

**LLM-related (INFO → LLM):**
```python
# BEFORE
logger.info(f"ClaudeProvider initialized: model={model}")

# AFTER
logger.llm(f"ClaudeProvider initialized: model={model}")
```

**Deep debugging (DEBUG → TRACE):**
```python
# BEFORE
logger.debug(f"Parsing damage from line: {line}")

# AFTER
logger.trace(f"Parsing damage from line: {line}")
```

### Files Already Updated

- `scripts/aeonisk/multiagent/llm_provider.py` - All API initialization and retry logs use `logger.llm()`
- `scripts/aeonisk/multiagent/llm_logger.py` - Cache operations use `logger.llm()`
- `scripts/aeonisk/multiagent/main.py` - CLI accepts TRACE/LLM levels

### Files To Update (TODO)

**TRACE candidates (deep debugging):**
- `outcome_parser.py` - Line-by-line parsing operations
- `tactical_resolution.py` - Token claim/release state
- `mechanics.py` - Inventory item-by-item operations
- `dm.py` - Scenario parsing details

**LLM candidates:**
- `player.py` - Player LLM calls (currently DEBUG)
- `enemy_combat.py` - Enemy tactical LLM calls (currently DEBUG)
- `dm.py` - DM LLM calls (currently DEBUG)

## Testing

```bash
# Test custom log levels work
python -m pytest tests/unit/test_custom_log_levels.py -v

# Test integration with real modules
python -m pytest tests/unit/test_log_level_integration.py -v
```

## Design Philosophy

### Why Custom Levels?

1. **Noise Reduction** - DEBUG logs are often polluted with API spam OR missing API details
2. **Targeted Debugging** - Enable LLM debugging without mechanics noise, or vice versa
3. **Production Clarity** - Separate "interesting for developers" from "interesting for ML"
4. **Log Analysis** - Easy to grep for specific subsystem activity

### Why These Specific Levels?

**LLM (15) between DEBUG (10) and INFO (20):**
- Less verbose than DEBUG (won't show every mechanics calculation)
- More verbose than INFO (captures all API activity)
- Allows: `--log-level DEBUG` shows mechanics + LLM, `--log-level LLM` shows only LLM

**TRACE (5) below DEBUG (10):**
- More verbose than DEBUG (shows internal parsing loops)
- Only enabled when explicitly requested
- Follows convention used by logging frameworks (log4j, serilog)

### Guidelines for Log Level Selection

- **TRACE** - Would only be useful when hunting specific bug (parsing, state machines)
- **DEBUG** - Useful for general development (mechanics, game flow)
- **LLM** - Useful for API debugging (prompts, responses, caching)
- **INFO** - Useful for session monitoring (rounds, spawns, victories)
- **WARNING** - Unexpected but recoverable (retries, missing data)
- **ERROR** - Failure requiring attention (API exhaustion, invalid state)

## Implementation Details

### Module Structure

```
scripts/aeonisk/multiagent/
├── custom_log_levels.py    # Defines TRACE=5, LLM=15, adds logger methods
├── main.py                 # Imports custom_log_levels, CLI accepts new levels
├── llm_provider.py         # Imports custom_log_levels, uses logger.llm()
└── llm_logger.py           # Imports custom_log_levels, uses logger.llm()
```

### Import Order (Critical!)

Custom log levels MUST be imported before any logging calls:

```python
# ✅ CORRECT
from scripts.aeonisk.multiagent import custom_log_levels  # noqa: F401
import logging
logger = logging.getLogger(__name__)
logger.llm("This works!")

# ❌ WRONG
import logging
logger = logging.getLogger(__name__)
logger.llm("AttributeError: 'Logger' object has no attribute 'llm'")
from scripts.aeonisk.multiagent import custom_log_levels  # Too late!
```

### Logger Method Injection

Custom log levels add convenience methods to `logging.Logger`:

```python
# These methods are added automatically:
logging.Logger.trace = trace  # Logs at TRACE level (5)
logging.Logger.llm = llm      # Logs at LLM level (15)

# Equivalent to:
logger.log(logging.TRACE, "message")  # Verbose
logger.trace("message")               # Concise
```

### Performance

- **No overhead** - `isEnabledFor()` check prevents message formatting if filtered
- **No branching** - Log level comparison uses native Python logging (C extension)
- **Safe** - Works with all existing logging handlers, formatters, filters

## Future Enhancements

**Possible additions:**
- `NARRATIVE (12)` - DM story narration separate from mechanics
- `TACTICAL (8)` - Enemy AI decision-making between TRACE and DEBUG
- Environment variable: `AEONISK_LOG_LEVEL=LLM` for CI/testing

**Not recommended:**
- Too many levels create confusion
- Current 2 custom levels solve 90% of noise issues
- Additional levels should have clear, distinct use cases

## References

- Python logging docs: https://docs.python.org/3/library/logging.html#logging-levels
- Custom levels: https://docs.python.org/3/howto/logging.html#custom-levels
- Test coverage: `tests/unit/test_custom_log_levels.py` (15 tests)
- Integration tests: `tests/unit/test_log_level_integration.py` (6 tests)
