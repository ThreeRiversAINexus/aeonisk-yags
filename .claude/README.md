# .claude/ Directory - AI Assistant Context

This directory contains documentation specifically for AI assistants (like Claude Code) working on the Aeonisk YAGS project.

## Purpose

The `.claude/` directory provides:
- **Quick orientation** for AI assistants joining the project
- **Implementation context** that complements the main CLAUDE.md
- **In-progress work tracking** in `current-work/`
- **Architecture details** that help understand system design

## Documentation Structure

### Core Documentation

- **`ARCHITECTURE.md`** - Multi-agent system architecture, async patterns, message flow
- **`current-work/`** - Active development notes, implementation journals, work-in-progress docs

### Settings

- **`settings.local.json`** - Local Claude Code settings (not committed to git)

## Related Documentation

**Main project documentation** (in root directory):
- **`CLAUDE.md`** - Primary guide, critical patterns, common pitfalls (AUTO-LOADED)

**Multi-agent specific** (in `scripts/aeonisk/multiagent/`):
- **`LOGGING_IMPLEMENTATION.md`** - Detailed ML logging system documentation
- **`schemas/README.md`** - Pydantic schema documentation

**Game content** (authoritative source):
- **`content/`** - Aeonisk game rules and lore (Markdown)
- **`converted_yagsbook/markdown/`** - Core YAGS mechanics

## Quick Reference

### Architecture
- **Single-process, asyncio-based** message bus
- DM + Players + Enemies as async agents
- Threading only for human interface CLI
- Mechanics engine in shared_state

### Common Patterns
```python
# Always access mechanics via shared_state
mechanics = self.shared_state.get_mechanics_engine()

# JSONL logging
if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
    mechanics.jsonl_logger.log_action_resolution(...)
```

### Project Focus
1. **Multi-agent simulations** - AI agents playing tabletop RPG sessions
2. **ML data generation** - JSONL logs for training datasets
3. **Game rule maintenance** - Content in `content/` and `converted_yagsbook/`
4. **Stress testing** - Validate game mechanics through simulation

## For AI Assistants

**Before starting work:**
1. Read `CLAUDE.md` (auto-loaded)
2. Read `ARCHITECTURE.md` (this directory)
3. Check recent git commits for context
4. Review `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` if working on logging

**During work:**
- Document complex features in `current-work/` as needed
- Delete completed feature docs when done
- Update CLAUDE.md if you find critical patterns
- Test with: `source .venv/bin/activate && python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json`

**Best practices:**
- No frontend (it's CLI only)
- Always activate venv before running Python
- Game rules in `content/` are canonical
- Check game.log for suppressed errors
- Validate JSONL with `validate_logging.py`

---

**Last Updated:** 2025-10-23 (Documentation reset)
