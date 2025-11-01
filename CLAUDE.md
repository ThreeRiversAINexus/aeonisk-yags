# CLAUDE.md - Essential Reference

**Additional Documentation:** See `.claude/` for detailed architecture and active work notes.

**Current Branch:** `revamp-structured-output`

## Project Overview

**Multi-Agent Python System** (`scripts/aeonisk/multiagent/`) - **PRIMARY FOCUS**
- AI agents (DM, players, enemies) play tabletop RPG sessions
- JSONL logging for ML training
- Key files: `session.py`, `dm.py`, `enemy_combat.py`, `mechanics.py`, `prompts/claude/en/*.yaml`

## Quick Start

**Always activate venv first (located in project root):**
```bash
source .venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json
```

**Running tests:**
```bash
source .venv/bin/activate
python -m pytest tests/unit/test_mechanics.py -v
```

## Critical Patterns

### 1. Accessing Mechanics
```python
# ✅ CORRECT
mechanics = self.shared_state.get_mechanics_engine()

# ❌ WRONG
mechanics = self.coordinator.mechanics  # doesn't exist
mechanics = self.mechanics              # doesn't exist
```

### 2. JSONL Logging
```python
if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
    mechanics.jsonl_logger.log_action_resolution(...)
```

### 3. LLM API Rate Limiting
- **Default:** `max_concurrent_requests=3`, `min_request_interval=0.5s`
- Auto-retry for 500/529 errors with exponential backoff
- Use `call_anthropic_with_retry` wrapper for retry/rate limiting in new code

### 4. Free Targeting & DM-Authoritative Resolution
- Free targeting enabled by default: all combatants get generic IDs (`tgt_xxxx`)
- DM narration determines all outcomes (damage, healing, void changes)
- Fallback damage ONLY for PC→Enemy (not PC→PC)
- NO keyword detection - DM interprets intent via context

### 5. AI Agent Failure Prevention
- **Stat awareness:** Agents see roll formula, unskilled penalty (-5), top skills
- **Failure loop detection:** After 2 consecutive failures of same action type, inject warning requiring different approach
- **High void warning:** When void ≥8, warn about dangerous actions
- **Philosophy:** Allow mistakes for ML training, but prevent death spirals

## ML Logging System

10 event types logged to JSONL: scenario, action_declaration/resolution, round_synthesis/summary, character_state, combat_action, enemy_spawn/defeat, mission_debrief. See `LOGGING_IMPLEMENTATION.md` for details.

**Tools:**
- `validate_logging.py` - Schema validation
- `reconstruct_narrative.py` - Rebuild story from logs
- `analyze_session.py` - **Quick session analysis (use this instead of reading huge JSONL files!)**

## Debugging

```bash
# Check logs
tail -100 game.log
grep ERROR game.log | tail -20

# Validate JSONL
python3 multiagent/validate_logging.py ../../multiagent_output/session_*.jsonl
```

### Session Analysis Tool (CRITICAL FOR DEVELOPMENT)

**Problem:** JSONL session files are often too large to read directly (>50k tokens)

**Solution:** Use `analyze_session.py` for targeted event extraction with smart defaults

#### Quick Summaries (Human-Readable)

```bash
# Session overview - ~30-40 lines
python scripts/analyze_session.py session.jsonl

# Clock progression - ~5-30 lines
python scripts/analyze_session.py session.jsonl --mode=clocks

# Void trajectory - ~10-20 lines
python scripts/analyze_session.py session.jsonl --mode=void
```

#### Targeted Event Extraction (Machine-Readable)

```bash
# Search with smart defaults (shows line, round, agent, action, success, margin)
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution
# Output: {"_line":9,"round":1,"agent":"Ash","action":"Search terminal...","roll.success":false,"roll.margin":-5}

# Multiple filters
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution round=2

# Custom field selection
python scripts/analyze_session.py session.jsonl --search event_type=scenario --fields scenario.void_level,scenario.location
# Output: {"_line":2,"scenario.void_level":8,"scenario.location":"Corrupted Station"}

# Count matches (no JSON output)
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --count
# Output: Found 47 matching events

# Show line numbers (for targeting specific events)
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --index
# Output: Matching events at lines: 5, 12, 18, 25... (47 total)

# Get full event at specific line
python scripts/analyze_session.py session.jsonl --line 12
# Output: Full pretty-printed JSON

# See available fields for event type
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution --schema
# Output: Available fields: event_type, round, agent, action, roll.success, ...
```

**Smart defaults per event type:**
- `action_resolution` → line, round, agent, action (truncated), success, margin
- `scenario` → line, theme, location, void_level
- `enemy_spawn` → line, round, template, count
- Others → line, event_type, round

**Default limit:** Shows first 5 matches with total count (e.g., "Found 47 events, showing first 5")

**When to use:**
- ✅ Quick "what happened?" → summary mode
- ✅ Find specific events → `--search` with filters
- ✅ Extract data for tests → `--search` + `--fields`
- ✅ Count event types → `--search` + `--count`
- ✅ Locate then inspect → `--index` then `--line N`
- ✅ Complex queries → `--search` to find events, then pipe to `jq` for advanced processing

**Other tools:**
- Full story narrative → `reconstruct_narrative.py`
- Schema validation → `validate_logging.py`

## Design Philosophy

**Core Principle:** Mechanics emerge from LLM-generated structured output, NOT keyword detection or text parsing.

**Structured Output Over Keyword Detection:**
- ✅ **Preferred:** LLMs generate Pydantic-validated structured output (`ActionResolution`, `VoidChange`, `DamageEffect`)
- ✅ **Acceptable:** Pydantic schema validators (enforce contracts during generation)
- ❌ **Avoid:** Runtime keyword detection in game logic code
- ❌ **Avoid:** Text parsing for mechanical effects ("if 'stun' in narration...")

**Why we hate keyword detection:**
- False positives ("center", "feedback" triggering void mechanics)
- Brittle (breaks when LLM changes wording)
- Poor ML training data (mechanics implied from keywords, not explicit)
- Doesn't scale (would need keywords in every language)
- Goes against emergent gameplay philosophy

**Guidelines:**
- ✅ Freeform narration + structured mechanical fields (separate concerns)
- ✅ Generic placeholders in examples, not specific character names
- ✅ Trust LLM structured output, validate via schemas
- ❌ NO keyword detection for game mechanics in runtime code
- ❌ NO hardcoded faction behaviors based on name patterns
- ❌ NO text parsing of narration for mechanical effects

## Recent Work

Check `git log --oneline -10` for latest changes.

### Key Features Completed
- **Structured Output System** - Pydantic schemas for all LLM responses (ActionResolution, PlayerAction, etc.)
- **Free Targeting Mode** - Generic IDs (`tgt_xxx`) to test IFF/ROE capabilities
- **Enemy Agent System** - Autonomous tactical enemy AI agents
- **ML Logging** - Comprehensive JSONL logging for training datasets
- **Scene Clocks** - Bidirectional clocks for dynamic storytelling
- **Environmental Void** - Location-based void tracking separate from character void


---

**Start here when joining:**
1. This file (CLAUDE.md) - Essential patterns
2. `.claude/README.md` - AI orientation
3. `.claude/ARCHITECTURE.md` - System architecture
4. `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` - ML logging details
5. `scripts/session_config_README.md` - Session configuration guide

## Session Testing & Configuration

**Division of Labor:**
- **Human runs:** Multi-agent sessions (`python3 scripts/run_multiagent_session.py <config>`)
- **Claude runs:** Unit tests (`python -m pytest tests/unit/<test_file>.py -v`)

**Session Config Features:**
- `starting_clocks` - Load pre-configured scene clocks at session start
- Environmental void_level updates via `StoryAdvancement.new_void_level`
- See `scripts/session_config_README.md` for full configuration guide

**Test Configs:**
- `session_config_void_story_advancement_test.json` - Tests void_level updates
- `session_config_starting_clocks_test.json` - Tests clock loading
- All test configs use contrived scenarios (max_turns=1-2) for rapid validation
