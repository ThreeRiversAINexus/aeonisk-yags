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

## Debugging

```bash
# Check logs
tail -100 game.log
grep ERROR game.log | tail -20

# Validate JSONL
python3 multiagent/validate_logging.py ../../multiagent_output/session_*.jsonl
```

## Design Philosophy

**Core Principle:** DM interprets actions via context, NOT keyword detection.

**Guidelines:**
- ✅ Freeform narration + structured mechanical markers (`⚫ Void`, `📊 Clock`)
- ✅ Generic placeholders in examples, not specific character names
- ❌ NO keyword detection for game mechanics
- ❌ NO hardcoded faction behaviors based on name patterns

## Recent Work (See `.claude/current-work/` for details)

### 2025-10-30: Structured Output Phase 2
- Added Pydantic schemas for enemy removal/de-escalation (`EnemyResolution`, `EnemyRemoval`)
- Auto-clear enemies on `ADVANCE_STORY` (fixes persistence bug)
- All debuff actions now deal damage + debuff

### 2025-10-29: Structured Output Phase 1
- Created Pydantic schema system (`schemas/`: ActionResolution, PlayerAction, EnemyDecision, StoryEvents)
- Extended `llm_provider.py` with `generate_structured()` method
- Philosophy: Freeform narration + structured mechanics (NO keyword detection)
- Multi-provider ready (Claude, GPT-4, local models)

### 2025-10-29: Keyword Detection Removal
- Disabled ALL keyword-based void detection (false positives from "center", "feedback", etc.)
- Now rely ONLY on DM explicit markers: `⚫ Void: +X (reason)`
- Removed skill routing - agents choose skills (mistakes = ML training data)


---

**For detailed work history and active development context, see `.claude/current-work/`**

**Start here when joining:**
1. This file (CLAUDE.md) - Essential patterns
2. `.claude/README.md` - AI orientation
3. `.claude/ARCHITECTURE.md` - System architecture
4. `LOGGING_IMPLEMENTATION.md` - ML logging details
