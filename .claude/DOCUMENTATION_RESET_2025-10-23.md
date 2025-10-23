# Documentation Reset - 2025-10-23

## Summary

Performed a comprehensive documentation cleanup to align all AI assistant documentation with current project reality.

## Changes Made

### Deleted - Outdated Root-Level Docs

**Removed files:**
- `README_MULTIAGENT.md` - Described old IPC/multi-process architecture (now asyncio single-process)
- `INTEGRATION_COMPLETE.md` - Old iteration completion doc
- `DEVELOPMENT_ISSUES_RESOLVED.md` - Frontend/backend issues (project is now CLI-only)
- `BUGFIXES.md` - Outdated bugfix tracking
- `MULTIAGENT_MECHANICS_UPGRADE.md` - Old architecture docs (info consolidated)

**Reason:** These docs described obsolete architectures and implementations that would confuse AI assistants.

### Deleted - .claude/ Old Tracking Docs

**Removed 23 files:**
- Implementation tracking: `PHASE_A_COMPLETE.md`, `PRD_IMPLEMENTATION_PLAN.md`, `IMPROVEMENTS_SUMMARY.md`
- Fix summaries: `CODEX_NEXUM_CRITICAL_FIXES.md`, `GAMEPLAY_QUALITY_FIXES.md`, `IMMEDIATE_FIXES_SUMMARY.md`, etc.
- Bug tracking: `DEFEATED_PLAYER_BUG.md`, `POSITION_TRACKING_BUG.md`, `COMBAT_BUGS_SUMMARY.md`, etc.
- Old feature docs: `SOULCREDIT_IMPLEMENTATION.md`, `FREE_DIALOGUE_IMPLEMENTATION.md`, etc.
- Duplicate references: `CHARACTER_POOL.md`, `FACTION_REFERENCE.md`, `SPAWN_MARKER_REFERENCE.md`

**Reason:** Historical implementation tracking that's no longer relevant. Info is now in current docs or git history.

### Deleted - Content

**Removed:**
- `content/supplemental/CHARACTER_POOL.md` - Not useful, handled by RAG system

### Created - New .claude/ Structure

```
.claude/
├── README.md                      # Overview for AI assistants
├── ARCHITECTURE.md                # Multi-agent system architecture (comprehensive)
├── current-work/
│   ├── README.md                  # Active development context
│   ├── Enemy Agent System - Design Document.md
│   └── Enemy Agent Integration Guide.md
└── settings.local.json            # Local settings
```

**Purpose:** Clean, focused documentation structure with:
- **README.md** - Quick orientation and best practices
- **ARCHITECTURE.md** - Deep dive into system design, message flow, components
- **current-work/** - Active development docs for current branch

### Updated - Root-Level Docs

**QUICK_START_MECHANICS.md:**
- Updated installation instructions (emphasize venv requirement)
- Updated commands to reflect current directory structure
- Added validation and testing commands
- Removed outdated API references
- Added current troubleshooting tips

### Kept - Important Docs

**Root level (kept as-is):**
- `CLAUDE.md` - Main guide, recently updated, auto-loaded ✅
- `AEONISK_BENCHMARK_SYSTEM_SUMMARY.md` - Still relevant for ML benchmarking ✅
- `README.md` - Project overview (backend API) ✅
- `README.yags_conversion.md` - Historical context ✅

**Content (game rules - canonical):**
- `content/` - Aeonisk game rules and lore
- `converted_yagsbook/markdown/` - Core YAGS mechanics
- `content/experimental/Aeonisk - Tactical Module - v1.2.3.md`

**Multiagent-specific:**
- `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` - ML logging system docs ✅

## New Documentation Philosophy

### .claude/ Directory Purpose

1. **Quick onboarding** for AI assistants joining the project
2. **Architecture reference** that complements CLAUDE.md
3. **Current work tracking** in `current-work/` subdirectory
4. **Implementation context** without clutter from old iterations

### What Goes Where

**Root level:**
- User-facing documentation (README.md, QUICK_START_MECHANICS.md)
- Main AI assistant guide (CLAUDE.md - auto-loaded)
- High-level project summaries

**.claude/:**
- AI assistant orientation (README.md)
- System architecture deep-dive (ARCHITECTURE.md)
- Active development notes (current-work/)

**Multiagent-specific:**
- Detailed implementation docs (LOGGING_IMPLEMENTATION.md)

**Content:**
- Game rules (canonical source of truth)

**Git history:**
- Old implementation details, bug tracking, historical context

## Key Insights Documented

### Architecture Clarifications

**Old docs said:** Multi-process IPC with Unix Domain Sockets
**Reality:** Single-process asyncio with in-memory message bus
**Documented in:** `.claude/ARCHITECTURE.md`

**Old docs said:** Frontend (aeonisk-assistant) is part of project
**Reality:** Project is CLI-only, focuses on multi-agent simulations and ML data generation
**Documented in:** `.claude/README.md`, `CLAUDE.md`

### Critical Patterns Preserved

1. **Mechanics access:** Only via `shared_state.get_mechanics_engine()`
2. **JSONL logging:** Content generation ≠ logging location
3. **Virtual environment:** Required for ChromaDB/sentence-transformers
4. **Game rules:** `content/` + `converted_yagsbook/` are canonical

**All documented in:** `CLAUDE.md`, `.claude/ARCHITECTURE.md`

## For Future AI Assistants

**Start here:**
1. `CLAUDE.md` (auto-loaded) - Critical patterns, quick start
2. `.claude/README.md` - Orientation and best practices
3. `.claude/ARCHITECTURE.md` - System design deep-dive
4. `.claude/current-work/` - Active development context

**During development:**
- Document complex changes in `.claude/current-work/`
- Update `CLAUDE.md` if you find critical new patterns
- Don't recreate old tracking docs - use git for history

**Testing:**
```bash
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_config_combat.json
python3 multiagent/validate_logging.py ../../multiagent_output/session_*.jsonl
```

## Statistics

**Before cleanup:**
- Root docs: 10 all-caps .md files (5 outdated)
- .claude/ docs: 24 files (23 old tracking, 1 settings)
- Total: ~40+ documentation files

**After cleanup:**
- Root docs: 5 all-caps .md files (all current)
- .claude/ docs: 6 files (4 current guides, 2 in-progress docs, 1 settings)
- Total: ~20 documentation files

**Reduction:** ~50% fewer docs, 100% current and accurate

## Commit Message

```
docs: Complete documentation reset for AI assistants

- Delete outdated root docs (IPC architecture, old integrations)
- Clean up .claude/ (remove 23 old tracking/fix docs)
- Create new .claude/ structure (README, ARCHITECTURE, current-work/)
- Update QUICK_START_MECHANICS.md to current API
- Move enemy agent docs to current-work/
- Preserve canonical game content and recent ML logging docs

Result: 50% fewer docs, all current and accurate.
Closes documentation debt from multiple implementation iterations.
```

---

**Documentation reset complete.** Project documentation now accurately reflects current architecture and implementation as of 2025-10-23.
