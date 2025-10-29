# CLAUDE.md

This file provides guidance to Claude Code when working with the Aeonisk YAGS project.

**Additional Documentation:** For deeper architecture details and current work context, see the `.claude/` directory:
- `.claude/README.md` - AI assistant orientation
- `.claude/ARCHITECTURE.md` - System architecture deep-dive
- `.claude/current-work/` - Active development notes

## Project Overview

**Aeonisk YAGS** is a science-fantasy tabletop RPG system with AI-powered gameplay. The project consists of:

1. **Multi-Agent Python System** (`scripts/aeonisk/multiagent/`) - **PRIMARY DEVELOPMENT FOCUS**
   - AI agents (DM, players, enemies) playing tabletop RPG sessions
   - Comprehensive JSONL logging for ML training
   - Tactical combat with positioning and enemy AI

2. **Backend API** (`src/`) - Node.js/Express/TypeScript
   - Domain-driven design architecture
   - PostgreSQL database with Drizzle ORM
   - Character management, game sessions, void tracking

3. **Game Content** (`content/`) - Markdown-based rules and lore
4. **Training Datasets** (`datasets/`) - Character examples and scenarios

## Quick Start - Multi-Agent System

### Critical: Always Use Virtual Environment
```bash
cd scripts/aeonisk
source .venv/bin/activate  # ChromaDB/transformers requirement
```

### Run a Game Session
```bash
# From scripts/ directory
python3 run_multiagent_session.py session_config_combat.json
```

### Validate Logs
```bash
cd aeonisk/multiagent
python3 validate_logging.py ../../multiagent_output/session_*.jsonl
```

### Reconstruct Story
```bash
python3 reconstruct_narrative.py ../../multiagent_output/session_*.jsonl
python3 reconstruct_narrative.py ../../multiagent_output/session_*.jsonl > story.md
```

## Architecture

### Multi-Agent System (`scripts/aeonisk/multiagent/`)

**Key Files:**
- `session.py` (1500+ lines) - Orchestrates game loop, phase management, logging integration
- `dm.py` (1800+ lines) - DM AI agent, narration generation, adjudication
- `enemy_combat.py` (1400+ lines) - Enemy agents with tactical AI
- `mechanics.py` (600+ lines) - Core game mechanics + JSONLLogger class
- `base.py` - Message bus, async agent framework, GameCoordinator
- `prompt_loader.py` - Externalized prompt system with i18n support
- `prompts/claude/en/*.yaml` - DM, Player, Enemy prompts (externalized from code)

**Prompt System (v2.1):**
```
prompts/
├── claude/en/           # English prompts
│   ├── dm.yaml         # DM narration templates
│   ├── player.yaml     # Player action templates
│   └── enemy.yaml      # Enemy tactical templates
├── shared/
│   └── markers.yaml    # Command marker registry
└── [future: es/, zh/ for multi-language]
```

All agent prompts are now externalized to YAML files with:
- ✅ Version tracking (logged in JSONL for ML analysis)
- ✅ Multi-language support (ready for Spanish/Chinese)
- ✅ Provider abstraction (ready for GPT-4, local models)
- ⏳ Enemy prompts using legacy system (marked for future refactor)

**Architecture Pattern:**
```
Player Agents ─┐
Enemy Agents  ─┼─> Message Bus ─> DM Agent ─> Narration
Session      ─┘                                    │
                                                   v
                                          Logging (JSONL)
```

### Backend API (`src/`)

**Domain-Driven Design:**
```
src/
├── api/              # HTTP layer (routes, controllers, middleware)
├── domain/           # Core entities and schemas
│   ├── entities/     # Character, GameSession classes
│   └── schemas/      # Zod validation
├── infrastructure/   # Database and external services
│   ├── database/     # Drizzle ORM schema
│   └── repositories/ # Data access layer
├── services/         # Business logic
└── utils/           # Shared utilities
```

## Critical Patterns - MUST FOLLOW

### 1. Accessing Mechanics in Multi-Agent System
```python
# ✅ CORRECT - The ONLY way
mechanics = self.shared_state.get_mechanics_engine()
# OR
mechanics = self.shared_state.mechanics_engine

# ❌ WRONG - These don't exist
mechanics = self.coordinator.mechanics  # GameCoordinator has no .mechanics
mechanics = self.mechanics              # Session has no .mechanics attribute
```

**Why:** Debugged this 3 times. Mechanics lives in `shared_state`, nowhere else.

### 2. JSONL Logging Pattern
```python
# Always check for logger existence
if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
    mechanics.jsonl_logger.log_action_resolution(...)
```

**Logger location:** `mechanics.jsonl_logger` (JSONLLogger instance in mechanics.py:55-509)

### 3. Message Flow for Round Synthesis
```
1. Session requests (session.py:603)
2. DM generates (dm.py:998-1012)
3. DM broadcasts with is_round_synthesis: True
4. Session receives (session.py:1484)
5. Session logs it (session.py:1489-1495)  ← NOT DM!
```

**Key insight:** Content generation and logging often happen in different places.

### 4. Free Targeting Mode & Damage Resolution
```python
# Free targeting mode: IFF/ROE testing with unified targeting
enemy_agent_config = {
    "free_targeting_mode": True,  # Everyone gets target IDs (tgt_xxxx)
    ...
}
```

**How it works:**
- **All combatants** (PCs + enemies) receive generic target IDs: `tgt_7a3f`, `tgt_yc0e`, etc.
- **No allegiance indicators** - system doesn't reveal who is friend/foe (IFF testing)
- **DM narration is authoritative** - determines all outcomes (damage, healing, effects)

**Damage Resolution Hierarchy:**
1. **DM narration** - "strikes for 8 damage" → Apply 8 damage
2. **Combat triplet** - `post_soak_damage` from action_validator → Apply that
3. **Fallback damage** - Generated ONLY for PC → Enemy actions (not PC → PC)

**PC-to-PC Actions (Free Targeting):**
- ✅ "Purify void corruption from Riven" → DM narrates cleansing, void reduced on target
- ✅ "Stabilize Thresh with med kit" → DM narrates healing
- ✅ "Shoot Ash Vex to stop the ritual" → DM narrates damage, applies it
- ❌ NO keyword analysis for damage - DM interprets intent and adjudicates outcome

**Void Cleansing on Targets (DM-Authoritative, Scales with Success Quality):**
- System resolves `target_enemy="tgt_7a3f"` → `target_character="Ash Vex"` automatically
- Void reduction applied to **target character**, not the ritual performer
- **DM generates explicit markers** based on success quality:
  - Marginal (0-4): `⚫ Void (Target): -1`
  - Moderate (5-9): `⚫ Void (Target): -2`
  - Good (10-14): `⚫ Void (Target): -3`
  - Excellent (15-19): `⚫ Void (Target): -4`
  - Exceptional (20+): `⚫ Void (Target): -5`
- **NO keyword detection** - DM interprets intent and generates appropriate markers
- Requires: Success + (ley site OR offering) mentioned in DM narration
- Example: Margin +20 → DM generates `⚫ Void (Target): -5 (transcendent purification)`

**Why:** Enables emergent gameplay (betrayal, healing, IFF testing) without brittle keyword detection for damage resolution.

**Files:** `dm.py:1765-1775, 2458-2468` (target ID resolution), `dm.py:1797-1804` (fallback damage logic), `player.py:1250` (UI gating), `prompts/claude/en/dm.yaml:274-285` (DM void cleansing rules), `outcome_parser.py:39-63` (explicit marker parsing), `target_ids.py` (ID system)

## ML Logging System

**Status:** ✅ Complete (2025-10-23)
**Documentation:** `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`

### What's Logged (10 event types)
1. `scenario` - Theme, location, situation
2. `action_declaration` - Player intentions (intent + description + DC estimate)
3. `action_resolution` - DM narration (~1000 chars with roll/damage/clocks)
4. `round_synthesis` - DM round summary
5. `round_summary` - Aggregate statistics (success rate, damage, void)
6. `character_state` - Health/void/soulcredit snapshots
7. `combat_action` - Bidirectional combat (player ↔ enemy)
8. `enemy_spawn` - Complete enemy stats
9. `enemy_defeat` - Defeat reason + rounds survived
10. `mission_debrief` - Character reflections

**Output:** ~20,000+ chars of narrative + structured data per session

### Tools
- `validate_logging.py` - Schema validation, handles dual combat schemas
- `reconstruct_narrative.py` - Rebuild complete story from logs

### Dual Combat Schemas

**Enemy → Player (full breakdown):**
```json
{
  "damage": {
    "strength": 3, "weapon_dmg": 12, "d20": 8,
    "total": 23, "soak": 10, "dealt": 13
  }
}
```

**Player → Enemy (simplified):**
```json
{
  "damage": {
    "base_damage": 14, "soak": 12, "dealt": 2
  }
}
```

**Why:** Enemy attacks are calculated (we control player stats). Player attacks are inferred from DM narration (we don't control enemy stats).

## Common Commands

### Backend Development
```bash
# Start services (Postgres, Redis, ChromaDB)
task start
task infra

# Development
task dev
task test
task lint
task typecheck

# Database
task db:init
npm run db:migrate
npm run db:studio
```

### Multi-Agent Sessions
```bash
# Activate venv first!
cd scripts/aeonisk && source .venv/bin/activate

# Run session
python3 ../run_multiagent_session.py ../session_config_combat.json

# Validate
python3 multiagent/validate_logging.py ../../multiagent_output/session_*.jsonl

# Reconstruct
python3 multiagent/reconstruct_narrative.py ../../multiagent_output/session_*.jsonl
```

## Game System Mechanics

### Core Concepts
- **Attributes + Skills + d20** - Roll: `Attribute × Skill + d20` vs DC
- **Void Score** (0-10) - Spiritual corruption, mechanical effects at 5+
- **Soulcredit** - Spiritual economy currency
- **Clocks** - Progress tracking (e.g., "Enemy Reinforcements: 3/10")
- **Tactical Positioning** - Far/Near ranges, movement actions
- **Bonds** - Formal character relationships with mechanical benefits

### Character Stats
- **Attributes:** Strength, Agility, Endurance, Perception, Intelligence, Empathy, Willpower, Charisma, Size
- **Derived:** Health = Size × 2
- **Skills:** Combat, Guns, Stealth, Awareness, Athletics, Investigation, etc.

### Combat Flow
1. **Declaration Phase** - Players declare intentions
2. **Adjudication Phase** - DM resolves actions one by one
3. **Synthesis Phase** - DM summarizes round
4. **Cleanup Phase** - Enemy actions, character state logging, round summary

## Economy & Vendor System

### Talismanic Energy Currency

**Currency Types** (smallest → largest):
- **Breath** (Air) - Thought, communication, change
- **Drip** (Water) - Emotion, secrecy, flow, healing
- **Grain** (Earth) - Stability, structure, grounding
- **Spark** (Fire) - Action, force, urgency, will

**Conversion:** 10 Breath = 1 Drip = 0.1 Grain = 0.01 Spark (market rates vary)

### Seeds

**Three Types:**
- **Raw Seeds**: Unstable, untradeable, degrade in 7 cycles into Hollows
- **Attuned Seeds**: Ritually aligned to element (Fire/Water/Air/Earth/Spirit), stable and usable
- **Hollow Seeds**: Degraded/emptied, **illegal** in Nexus jurisdictions, +1 Void per shard

### Vendor Configuration

**Config Options:**
```json
{
  "vendor_spawn_frequency": 5,      // Spawn every N rounds (-1 = disabled)
  "force_vendor_gate": false,       // Require vendor in scenario
  "enemy_agent_config": {
    "loot_suggestions_enabled": true  // Faction-themed currency drops
  }
}
```

**Vendor Types:**
- `HUMAN_TRADER` - Full service, negotiation (safe zones)
- `VENDING_MACHINE` - Automated, fixed prices (action zones)
- `SUPPLY_DRONE` - Mobile field resupply (combat zones)
- `EMERGENCY_CACHE` - Free crisis supplies (one-time)

**11 pre-configured vendors** available (see `energy_economy.py`)

### Enemy Loot System

**Faction-Themed Currency Drops:**
- **Tempest Industries**: Spark (tech/energy), Hollow Seeds (void research)
- **ACG/Sovereign Nexus**: Spark + Grain (commerce/structure)
- **Pantheon Security**: Grain + Breath (order/law)
- **Freeborn/Street**: Breath + Drip (basic economy)
- **Void cultists**: Drip + Breath, Hollow Seeds (illicit)
- **Resonance Communes**: Breath, Attuned Seeds (ritual)

**Template-Based Amounts:**
- **Grunt**: 10-30 Breath, 3-8 Drip
- **Elite**: 5-15 Drip, 2-6 Grain, 0-2 Spark
- **Boss**: 3-10 Drip, 3-8 Grain, 2-5 Spark, 30% Seed drop

**Seed Drop Logic:**
- Void-aligned (void_score ≥3): 20-25% Hollow Seeds
- Ritual factions: 15% Attuned/Raw Seeds
- Bosses: 30% Seeds (Hollow if void ≥2, else Attuned)

**Implementation:** `enemy_spawner.py` (line 456+)

### Quick Reference

**Enable vendors:**
```json
"vendor_spawn_frequency": 5  // Every 5 rounds
```

**Disable vendors (combat-focused):**
```json
"vendor_spawn_frequency": -1
```

**Vendor-required scenario:**
```json
"force_vendor_gate": true,
"vendor_spawn_frequency": -1  // Scenario provides vendor
```

**Full documentation:** `scripts/session_config_README.md`

## Common Pitfalls - AVOID THESE

### 1. Forgetting Virtual Environment
```bash
# ❌ WRONG - Will fail with module import errors
python3 run_multiagent_session.py session_config_combat.json

# ✅ CORRECT
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_config_combat.json
```

### 2. Wrong Mechanics Access Pattern
```python
# ❌ All of these fail
mechanics = self.coordinator.mechanics
mechanics = self.mechanics
mechanics = self.get_mechanics()

# ✅ Only this works
mechanics = self.shared_state.get_mechanics_engine()
```

### 3. Ignoring Suppressed Errors
Message handler errors are caught and logged but don't crash:
```bash
grep ERROR game.log | tail -20
```

### 4. Field Name Mismatches
When passing dicts between components, names must match exactly:
```python
# Sender
summary = {'actions_attempted': 5}

# Receiver
count = summary.get('actions_attempted', 0)  # NOT 'action_count'!
```

### 5. Not Reading Files Before Editing
The Edit tool requires reading files first:
```python
# ✅ Correct workflow
Read(file_path)
Edit(file_path, old_string, new_string)
```

## Debugging

### Multi-Agent System
```bash
# Check logs
tail -100 game.log
tail -100 multiagent.log

# Search for errors
grep ERROR game.log | tail -20

# Check if round synthesis generated
grep "Round Synthesis" game.log

# Count events by type
cat multiagent_output/session_*.jsonl | python3 -c "
import json, sys
from collections import Counter
types = Counter(json.loads(line)['event_type'] for line in sys.stdin)
for t, c in sorted(types.items()): print(f'{t:30s}: {c}')
"
```

### Backend API
```bash
# Check service status
task status

# View logs
task logs

# Database access
task db:psql
npm run db:studio
```

## Project Structure

```
aeonisk-yags/
├── scripts/
│   ├── aeonisk/
│   │   ├── multiagent/          # Multi-agent Python system (PRIMARY)
│   │   │   ├── session.py       # Game orchestrator
│   │   │   ├── dm.py            # DM agent
│   │   │   ├── enemy_combat.py  # Enemy AI
│   │   │   ├── mechanics.py     # Game mechanics + logging
│   │   │   ├── validate_logging.py
│   │   │   ├── reconstruct_narrative.py
│   │   │   └── LOGGING_IMPLEMENTATION.md
│   │   └── .venv/               # CRITICAL: Activate before use!
│   └── session_config_*.json    # Session configurations
├── src/                         # Backend API (Node.js/TypeScript)
│   ├── api/
│   ├── domain/
│   ├── infrastructure/
│   └── services/
├── content/                     # Game rules and lore (Markdown)
├── datasets/                    # Training data
├── multiagent_output/          # JSONL session logs
├── game.log                    # Multi-agent debug logs
├── .claude/                    # AI assistant documentation
│   ├── README.md               # Orientation guide
│   ├── ARCHITECTURE.md         # System architecture
│   └── current-work/           # Active development notes
└── CLAUDE.md                   # This file (auto-loaded)
```

## Git Workflow

Current branch: `feature/tactical-enemy-agents` (ML logging implementation)

```bash
# Standard workflow
git status
git add <files>
git commit -m "message"

# Don't commit:
- game.log (too large)
- multiagent_output/*.jsonl (session logs)
- .venv/ (virtual environment)
```

## User Preferences & Design Philosophy

### Freeform Content Over Keyword Detection

**❌ Avoid:**
- Rigid keyword detection for intent (e.g., checking if "heal" or "cleanse" in intent string)
- Overly specific character names in prompts (e.g., "Ash Vex", "Thresh Ireveth")
- Hardcoded faction-specific behaviors based on name patterns

**✅ Prefer:**
- DM interprets actions based on context and narrative understanding
- Generic placeholder names in examples: "Target Character", "Ally Name", "Enemy"
- Freeform narrative with structured mechanical markers for effects

**Philosophy:**
"I hate keyword detection as a mechanic and want the DM to interpret it during resolution." - User

**Example of correct balance:**
```
Narration (freeform): "The purification ritual encounters unexpected resistance
as inverted resonance patterns fight back..."

Mechanics (structured): ⚫ Void (Target Character): -1 (marginal success despite complications)
```

### DM-Authoritative Resolution

- DM's narration determines outcomes, not keyword matching
- Fallback effects only for PC→Enemy actions (damage)
- PC→PC actions trust DM judgment (heal/harm/purify determined narratively)
- Mechanical markers (⚫ Void, ⚖️ Soulcredit, 📊 Clock) are mandatory for effects

### Prompt Design Guidelines

When updating prompts or examples:
- Use generic placeholders, not specific character names
- Allow narrative creativity while requiring mechanical clarity
- Examples should generalize to future gameplay scenarios
- Balance: Freedom in storytelling + Consistency in mechanics

## Important Notes

- **Multi-agent requires venv:** `cd scripts/aeonisk && source .venv/bin/activate`
- **Mechanics access:** Only via `shared_state.get_mechanics_engine()`
- **Check game.log for errors** - Message handlers catch exceptions silently
- **Dual combat schemas** - Enemy attacks (full), player attacks (simplified)
- **CLAUDE.md is auto-loaded** - This file is read every session
- **LOGGING_IMPLEMENTATION.md** - Detailed docs for ML logging system

## Recent Major Work

### 2025-10-29: Void Cleansing PC-to-PC Targeting Fix

**Branch:** `void-and-targeting-fixes`

**Problem:** PC-to-PC void purification rituals weren't reducing target's void score despite successful rolls.

**Root Cause:**
- System prevented fallback effects for PC→PC actions to avoid friendly fire damage
- DM generated creative narrative twists without mandatory void reduction markers
- Result: No void reduction applied even when ritual succeeded

**Solutions Implemented:**

1. **Enhanced DM Prompt** (`prompts/claude/en/dm.yaml`)
   - Made void reduction MANDATORY for successful void cleansing rituals
   - Added explicit PC-to-PC void cleansing instructions with named marker format
   - Example: `⚫ Void (Target Character): -3 (powerful purification despite complications)`
   - Used generic placeholders to avoid overfitting to specific character names

2. **Enhanced Void Marker Parser** (`outcome_parser.py`)
   - Updated `parse_explicit_void_markers()` to extract target character name
   - Changed return type: `Tuple[int, List[str], str]` → `Tuple[int, List[str], str, Optional[str]]`
   - Stores `void_target_character` in `state_changes` for session to apply to correct character

3. **Completed Target Field Rename** (from previous session)
   - Renamed `target_enemy` → `target` throughout codebase (6 files)
   - Purpose: Neutral terminology to avoid biasing AI toward hostile actions
   - Files: action_schema.py, player.py, outcome_parser.py, dm.py, markers.yaml, docs

**Testing Required:**
- Run `session_config_void_testing.json` (collaborative purification temple scenario)
- Verify DM includes named void markers: `⚫ Void (Target Name): -3`
- Check void reduction applies to target character, not caster

**Files Modified:**
- prompts/claude/en/dm.yaml
- outcome_parser.py
- action_schema.py, player.py, dm.py (target rename)
- LOGGING_IMPLEMENTATION.md, prompts/shared/markers.yaml

**See:** `.claude/current-work/void-cleansing-fix.md` for detailed analysis

### 2025-10-28: Model Migration to Claude Sonnet 4.5 + Bug Fixes

**Model Update:**
- Updated all session configs from `claude-3-5-sonnet-20241022` → `claude-sonnet-4-5`
- Updated default model in `llm_provider.py` (line 377)
- Applied to: DM, all players, and enemy agents (via default)
- Reason: Claude 3.5 Sonnet discontinued by Anthropic

**Bug Fixes:**
1. **Undefined `client` variable** (dm.py:336)
   - **Problem**: Scenario regeneration used `client.messages.create` (undefined variable)
   - **Fix**: Changed to `self.llm_client.messages.create`
   - **Impact**: Fixed "name 'client' is not defined" crash during scenario variety enforcement

2. **Wrong `current_round` reference** (session.py:1794)
   - **Problem**: Marker retry accessed `self.current_round` (doesn't exist on session)
   - **Fix**: Get round from `mechanics.current_round` instead
   - **Impact**: Fixed "'SelfPlayingSession' object has no attribute 'current_round'" crash during ADVANCE_STORY retry

**Files Modified:**
- `llm_provider.py` - Default model parameter
- All 18 session config files in `scripts/session_configs/`
- `dm.py` - Fixed client reference in scenario retry
- `session.py` - Fixed current_round reference in marker retry

### 2025-10-27: Free Targeting Mode & DM-Authoritative Damage Resolution

**Free Targeting System (IFF/ROE Testing):**
- Renamed `combat_id` → `target_id` throughout codebase (10 files)
- Changed ID format: `cbt_xxxx` → `tgt_xxxx` (neutral terminology)
- All combatants (PCs + enemies) receive generic IDs in free targeting mode
- No allegiance indicators - system doesn't reveal friend vs foe

**DM-Authoritative Damage Resolution:**
- **Removed keyword-based cooperative intent detection** (dm.py:1785-1804)
- DM narration is now the single source of truth for all PC-to-PC actions
- Fallback damage only generated for PC → Enemy (not PC → PC)
- Enables emergent gameplay: healing, purification, betrayal - all DM-interpreted

**How it works:**
1. Player declares: "Shoot Ash Vex to stop the ritual" (targets `tgt_7a3f`)
2. DM LLM adjudicates: Interprets intent, determines outcome, narrates result
3. System applies: Only applies what DM explicitly states (damage, healing, effects)
4. No fallback: PC-to-PC actions never get auto-generated damage

**Benefits:**
- ✅ IFF/ROE testing: Can target anyone without revealing allegiance
- ✅ Flexible interpretation: "Share tactical data" won't cause damage
- ✅ Emergent gameplay: "Shoot ally to stop corruption ritual" works
- ✅ No brittle keywords: DM context determines all outcomes

**Files Modified:**
- `dm.py` - Removed keyword analysis, added PC detection for fallback damage
- `player.py` - Restored free targeting UI (always show when enabled)
- `target_ids.py` - Renamed from combat_ids.py
- 8 other files updated for terminology consistency

**Test Results:** game_void_testing_3.log
- 15 rounds, free targeting enabled throughout
- PC-to-PC "share" actions: No damage (DM interpreted as cooperative)
- PC-to-Enemy combat: Fallback damage applied correctly
- Target IDs working: `tgt_c4cg`, `tgt_yc0e`, `tgt_ig3d`, etc.

**Void Cleansing Fixes (game_void_testing_4.log issue):**
1. **Target Resolution:**
   - **Problem**: PC-to-PC void cleansing rituals succeeded but didn't reduce target's void
   - **Root Cause**: Free targeting uses `target_enemy="tgt_xxxx"`, but outcome parser needs `target_character="Name"`
   - **Fix**: Added target ID → character name resolution before parsing state changes (dm.py:1765-1775, 2458-2468)
   - **Result**: "Riven cleanses Ash" now correctly reduces Ash's void (not Riven's)

2. **DM-Authoritative Void Cleansing:**
   - **Old**: Keyword detection (`'cleanse void'` exact phrase required) + hard-coded scaling in Python
   - **New**: DM generates explicit markers (`⚫ Void (Target): -5`) based on prompt instructions
   - **Removed**: All keyword-based void cleansing detection (outcome_parser.py:674-718 deleted)
   - **Added**: Scaling rules to DM prompt (prompts/claude/en/dm.yaml:274-285)
   - **Rationale**: Eliminates brittle keyword matching, trusts DM's judgment and context understanding
   - **Result**: "Channel purifying energy to help cleanse Ash's void corruption" (margin +20) → DM generates `⚫ Void: -5`

### 2025-10-26: Prompt System Migration to YAML (v2.1)

**YAML Migration:**
- Updated `prompt_loader.py` to use YAML instead of JSON
- Created `convert_prompts_to_yaml.py` for automatic JSON→YAML conversion
- All prompts now in YAML format (`prompts/claude/en/*.yaml`)
- Benefits: Multi-line strings without escaping, comments support, more readable

### 2025-10-25: Prompt System Externalization (v2.0)

**Externalized Prompt Architecture:**
- Created `prompt_loader.py` - Multi-language prompt loading with versioning
- Created `llm_provider.py` - Abstract provider interface for future multi-LLM support
- Externalized all DM/Player prompts to YAML files (`prompts/claude/en/*.yaml`)
- Added prompt metadata tracking to JSONL logs for ML correlation analysis

**DM Integration:**
- Created `_build_dm_narration_prompt()` helper method
- Replaced ~400 lines of inline prompt construction with prompt_loader calls
- Supports both PC-to-PC dialogue and standard narration paths
- Stores prompt version/provider/language metadata for every LLM call

**Player Integration:**
- Created `_build_player_system_prompt_new()` method
- Full variable substitution (attributes, skills, currency, void warnings)
- Stricter format enforcement to reduce skill_mapping dependency
- Tested and working in live sessions

**Enemy Integration:**
- Documented as using legacy system (enemy_prompts.py)
- Marked with TODO for future refactor to prompt_loader
- Current system proven and battle-tested, refactor deferred

**Benefits Unlocked:**
- ✅ Version tracking: Can correlate prompt changes with LLM behavior in logs
- ✅ Multi-language ready: Directory structure supports es/, zh/ translations
- ✅ Provider abstraction: Can add GPT-4, local models without touching agent code
- ✅ Maintainability: Non-programmers can edit prompts without Python knowledge

**Files Modified:** dm.py (+149 lines), player.py (+150 lines), prompt_loader.py (new, 14KB), prompts/*.json (new, 42KB total)

### 2025-10-24: Morale System Overhaul + Story Advancement Fixes

**Morale System Changes:**
- **Removed "last_survivor" trigger** - being outnumbered doesn't cause panic
- **Morale break now sets `is_panicked` status** instead of instant despawn
- Panicked enemies automatically declare "FLEE" on next turn
- **Escape requires Athletics check:** Agility × Athletics + d20 vs DC 15
  - Success: Enemy escapes (despawns)
  - Failure: Pinned down, cleared panic, fights normally
- PCs can now intercept/suppress fleeing enemies (tactical counterplay)
- Morale triggers: HP < 25%, Critical Stuns (5+) only
- Files: enemy_agent.py:349-350, enemy_combat.py:1332-1398, 1245-1305, 293-319

**Automatic Story Advancement:**
- DM now automatically progresses story when all clocks are complete/filled
- Session detects when no active clocks remain (session.py:1113-1146)
- Uses `_had_active_clocks` flag to track clock lifecycle
- Sets `needs_story_advancement` flag on DM agent
- DM synthesis prompt enhanced with [ADVANCE_STORY: ...] + [NEW_CLOCK: ...] instructions (dm.py:1507-1523)
- **Fixed:** DM now required to use [NEW_CLOCK:...] markers (not prose)
- **Fixed:** Parse order bug - now clears old clocks BEFORE spawning new ones (session.py:1585-1631)
  - Old order: spawn new → clear all (deleted new clocks!)
  - New order: clear old → spawn new (keeps new clocks!)
- Prevents scenario stalling after objectives complete
- Automatically generates new location/situation with fresh clocks

**Duplicate Logging Fix:**
- **Root cause:** Each player echoed other players' action broadcasts via `_handle_action_declared`
- With 3 players, each action printed 3 times (1 per receiving player)
- Fixed by moving all declaration prints to `logger.debug()`:
  - Player's own declarations (player.py:513, 658-659, 722-723)
  - Other players' broadcast echoes (player.py:458, 460)
  - DM acknowledgments (dm.py:1031)
- Actions now only print once during DM adjudication phase (dm.py:1108)
- Cleaner console output during gameplay

**Auto-Progression Behavior:**
- Triggers when **ALL** clocks are gone (expired, filled, or archived)
- Uses `_had_active_clocks` flag to detect when clocks disappear
- **Bug fixed:** Original logic failed when all clocks expired (dict became empty)
- Now correctly detects: had clocks → now no active clocks → trigger advancement
- DM can still manually use [PIVOT_SCENARIO:...] or [ADVANCE_STORY:...] anytime
- Clocks can expire via: filling (8/8), timing out (0/6 for N rounds), or manual removal

**Files Modified:** session.py, dm.py, player.py

### 2025-10-23: ML Logging System - Phases 1-4 Complete

**ML Logging System:**
- Bidirectional combat logging (player ↔ enemy)
- Round summary aggregation (actions, success rate, damage, void)
- Round synthesis logging (DM summaries)
- Player action declaration capture
- Complete narrative reconstruction
- 100% validation passing

**Commits:** 8d8cae2, a12a9de, c535ca3, f9b8741, abd45b4, bf5bcfb, 31b3ece, 4cc58c2

**Files Modified:** session.py, dm.py, enemy_combat.py, mechanics.py
**Files Added:** validate_logging.py, reconstruct_narrative.py, LOGGING_IMPLEMENTATION.md

---

**For Future AI Assistants:**

**Start here when joining the project:**
1. This file (CLAUDE.md) - Critical patterns and quick start
2. `.claude/README.md` - AI assistant orientation and best practices
3. `.claude/ARCHITECTURE.md` - System architecture deep-dive
4. `.claude/current-work/` - Active development context for current branch

**When working on the multi-agent system:**
- Read `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` for ML logging details
- The mechanics access pattern and dual combat schemas are critical to understand
- Always activate venv: `cd scripts/aeonisk && source .venv/bin/activate`
