# Current Work

This directory contains work-in-progress documentation.

**Current Branch:** `economy-and-vending`

## Active Documentation

**Economy System:** See `ECONOMY_STATUS.md` for comprehensive status of purchase, transfer, and vendor systems (80% complete as of 2025-01-11)

**Archived Docs:** See `.claude/archive/` for superseded implementation notes

## Active Development

Check `git status` and recent commits to see what's being worked on.

## For AI Assistants

When starting new work:
1. Check `git status` for uncommitted changes
2. Review recent commits (`git log --oneline -10`)
3. Read `CLAUDE.md` for critical patterns
4. Create new markdown docs here for complex features as needed
5. Clean up completed work docs when features are done

## Testing

Run sessions:
```bash
source .venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json
```

Run unit tests:
```bash
source .venv/bin/activate
python -m pytest tests/unit/ -v
```
