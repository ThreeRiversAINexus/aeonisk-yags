# CLAUDE.md

This file provides guidance to Claude Code when working with the Aeonisk YAGS project.

**Additional Documentation:** For deeper architecture details and current work context, see the `.claude/` directory:
- `.claude/README.md` - AI assistant orientation
- `.claude/ARCHITECTURE.md` - System architecture deep-dive
- `.claude/current-work/` - Active development notes

**Current Branch:** `revamp-structured-output` - Migrating from text parsing to Pydantic AI structured output

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

### 4. LLM API Resilience & Rate Limiting

**Built-in Retry with Exponential Backoff:**
- Automatic retry for 500/529 (Overloaded) errors
- Configurable via `LLMConfig`: `max_retries=3`, `base_delay=2.0`, `max_delay=120.0`
- Exponential backoff: 2s → 4s → 8s → 16s → ... (with jitter to prevent thundering herd)
- Non-retryable errors (auth, validation) fail immediately

**Global Rate Limiting:**
- Prevents too many concurrent API calls across all agents (DM + players + enemies)
- **Default (updated 2025-10-29):** `max_concurrent_requests=3`, `min_request_interval=0.5s`
- Uses singleton `APIRateLimiter` with semaphore + timing enforcement
- Automatically initialized on first API call
- **Tuned for multi-agent sessions** (3 PCs + 2 enemies + DM = 6 agents)

**Configuration Example:**
```python
config = LLMConfig(
    provider="claude",
    model="claude-sonnet-4-5",
    max_retries=3,              # Retry up to 3 times
    base_delay=2.0,             # Start with 2s delay (increased from 1.0)
    max_delay=120.0,            # Cap at 120s (increased from 60.0)
    jitter=True,                # Add randomness (50-100% of delay)
    use_rate_limiter=True,      # Enable global rate limiting
    max_concurrent_requests=3,  # Max 3 concurrent calls (reduced from 5)
    min_request_interval=0.5    # 500ms between request starts (increased from 0.2s)
)
```

**Why These Defaults?**
- **3 concurrent requests:** Prevents overwhelming Anthropic API during action declaration phase (3 players + 2 enemies + DM)
- **0.5s interval:** Spreads 5-action round over 2.5-3s instead of < 1s burst
- **2s base delay:** More conservative retry to give API time to recover
- **120s max delay:** Allows longer retries for persistent overload situations

**Tuning for Your Use Case:**
- **High API tier:** Increase `max_concurrent_requests` to 4-5 for better throughput
- **Rate limit errors:** Decrease `max_concurrent_requests` to 2, increase `min_request_interval` to 0.75s
- **Quick sessions:** Reduce `max_delay` to 30s to fail faster on persistent errors
- **Long campaigns:** Keep defaults - reliability > speed

**Why This Matters:**
- Multi-agent sessions can generate 10+ concurrent API calls during action declaration phase
- Without throttling, all agents hit API simultaneously → 500 Overloaded errors
- Retry logic recovers from transient overload
- Rate limiting prevents overload in the first place

**Using Retry/Rate Limiting in Existing Code:**

For code using raw `anthropic.Anthropic` clients, use the `call_anthropic_with_retry` wrapper:

```python
# OLD: Direct API call (no retry/rate limiting)
response = self.llm_client.messages.create(
    model=model,
    max_tokens=4000,
    temperature=0.8,
    messages=[{"role": "user", "content": prompt}]
)

# NEW: With retry/rate limiting
from .llm_provider import call_anthropic_with_retry

response = await call_anthropic_with_retry(
    client=self.llm_client,
    model=model,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=4000,
    temperature=0.8,
    max_retries=3,           # Optional: override default
    use_rate_limiter=True    # Optional: disable if needed
)
```

**Current Status:**
- ✅ Wrapper function created and working
- ✅ Used in `dm.py` marker retry logic (line 3146)
- ⏳ Main DM/player API calls still using direct client (future refactor)

**Files:** `llm_provider.py:19-75` (APIRateLimiter), `llm_provider.py:78-104` (LLMConfig), `llm_provider.py:269-382` (retry logic), `llm_provider.py:583-684` (wrapper function)

### 5. Free Targeting Mode & Damage Resolution
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

### 6. Player Agent Stat Awareness & Failure Loop Detection

**Philosophy:** Let AI agents make mistakes for ML training, but prevent death spirals with awareness and warnings.

**Stat Awareness System (player.yaml:88-153):**
- Shows agents their **roll formula**: `Attribute + Skill + d20` vs DC
- **Warns about unskilled penalty**: -5 (makes low-attribute actions nearly impossible)
- Displays **top 3 skills** and **low attributes (<4)** for each character
- Provides **success probability calculator** to estimate chances before acting
- **NO automatic routing** - agents choose their own skills (mistakes logged for training)

**Example Warning (for Intelligence 3, no Investigation):**
```
Intelligence 3 + NO Investigation skill = d20 - 2 vs DC 20 → NEED d20 = 22 (IMPOSSIBLE!)
YOUR BEST SKILLS: Charm (5), Corporate Influence (4), Astral Arts (4)
YOUR WORST ATTRIBUTES: Intelligence (3), Perception (3)
```

**Failure Loop Detection (dm.py:1360-1372, player.py:1072-1115):**
- DM tracks last 5 actions per character: `(action_type, success_tier, void_change, round_num)`
- Detects when same `action_type` fails 2+ times consecutively
- Injects urgent warning into player prompt before next action:
  ```
  🚨 FAILURE LOOP DETECTED 🚨
  You failed 2 investigate actions! Recent failures:
  - Round 6: investigate (CRITICAL_FAILURE, Void +2)
  - Round 8: investigate (CRITICAL_FAILURE, Void +2)
  REQUIRED: Choose a DIFFERENT action type! Use your strengths: Charm (5), Astral Arts (4)
  ```
- Prevents void death spirals from repeated impossible actions

**High Void Warning (player.py:1120-1145):**
- When void ≥ 8: Injects critical warning listing dangerous actions to avoid
- Suggests safer alternatives (coordination, offerings, support actions)
- Reminds that void 10 = possession

**Benefits:**
- ✅ Agents learn their character's capabilities organically
- ✅ Mistakes are logged as training data (not prevented)
- ✅ Death spirals prevented (agents forced to pivot after 2 failures)
- ✅ No "magic routing" - transparent skill selection

**Files:** `prompts/claude/en/player.yaml:88-153` (stat awareness guidance), `dm.py:1360-1372` (action tracking), `player.py:1055-1145` (stat list generation, warning injection), `session.py:105` (action history dict)

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

### 2025-10-30: Structured Output for Enemy Management & De-escalation (Phase 2)

**Branch:** `enemy-refactors`

**Problems Fixed:**
1. **Enemies persisted after ADVANCE_STORY** - Old combat continued in new scenes
2. **No de-escalation mechanics** - Arrest, intimidation, persuasion didn't remove enemies
3. **Debuff-only actions dealt no damage** - "Electrocute" applied -2 debuff but 0 damage

**Solution: Extend Structured Output Schemas (Pydantic AI)**

**Philosophy:** Use validated Pydantic schemas instead of brittle text marker parsing (`[NEUTRALIZE: ...]`, `[DESPAWN: ...]`).

**New Schemas Added:**

1. **`EnemyResolution` enum** (story_events.py):
   - `KILLED`, `NEUTRALIZED`, `FLED`, `CONVINCED`, `SUBDUED`, `STORY_ADVANCED`
   - Type-safe enemy removal tracking

2. **`EnemyRemoval` model** (story_events.py):
   ```python
   EnemyRemoval(
       enemy_name="ACG Guard Captain",
       resolution=EnemyResolution.NEUTRALIZED,
       reason="Arrested and restrained by Pantheon Security"
   )
   ```

3. **`RoundSynthesis.enemy_removals` field**:
   - DM specifies enemies removed via non-combat means
   - Replaces `[DESPAWN_ENEMY: ...]` markers

4. **`StoryAdvancement.clear_all_enemies` field** (default: `True`):
   - Auto-clears all active enemies when story advances
   - Prevents enemy persistence bug

**Implementation:**

1. **Session.py Enemy Clearing** (line 1839-1849):
   - Despawns all active enemies when `ADVANCE_STORY` triggers
   - Logs enemy names and count
   - Marks enemies with `is_active=False` and `despawned_round`

2. **DM Prompt Updates** (dm.yaml):
   - **Creative Tactics Damage Rule**: ALL hostile actions must include both debuff AND damage
     * Electrocute: `-2 debuff + 2-5 damage`
     * Freeze: `-2 debuff + 2-4 damage`
     * Blind: `-3 debuff + 1-2 damage`
   - **Enemy Management Examples**: Show structured output for spawns/removals
   - **Story Advancement Behavior**: Document auto-clear enemies default

3. **Future Migration Path**:
   - Round synthesis will use `RoundSynthesis` schema (replaces marker parsing)
   - Enemy removals via `enemy_removals` field (replaces `[DESPAWN_ENEMY: ...]`)
   - Action resolution via `ActionResolution` schema (Phase 1)

**Benefits:**
- ✅ No text parsing brittleness - Pydantic validates structure
- ✅ Type-safe - Can't misspell "neutralized" or forget fields
- ✅ Better ML training data - Structured enemy resolution tracking
- ✅ Clearer DM guidance - Schema docstrings explain requirements
- ✅ Aligns with Phase 1 structured output work

**Files Modified:**
- `schemas/story_events.py` - Added `EnemyResolution`, `EnemyRemoval`, updated `RoundSynthesis` and `StoryAdvancement`
- `prompts/claude/en/dm.yaml` - Added creative tactics damage guidance, enemy management examples
- `session.py:1839-1849` - Auto-clear enemies on story advancement
- `CLAUDE.md` - This documentation

**Testing Required:**
- Run `session_config_full.json` and verify enemies don't persist after `ADVANCE_STORY`
- Verify electrocute/freeze/blind actions deal damage + apply debuffs
- Test arrest/intimidation/persuasion removes enemies via structured output

### 2025-10-29: Structured Output with Pydantic AI - Phase 1 Complete

**Branch:** `revamp-structured-output`

**Problem:** Text parsing + keyword detection is brittle and provider-specific.

**Examples of issues:**
- "center mass" → "center" → false "grounding meditation" match
- Missing `⚫ Void: +1` marker → silent failure (no void change)
- Tied to Claude's output format, can't use OpenAI/local models

**Solution Implemented: Pydantic AI Structured Output**

**Phase 1 Complete:**
- ✅ Created comprehensive schema system (`scripts/aeonisk/multiagent/schemas/`)
- ✅ Extended `llm_provider.py` with `generate_structured()` method
- ✅ Created test suite (`test_structured_output.py`)
- ✅ All schemas validated with Claude API

**New Schemas:**
1. `ActionResolution` - DM action resolution (freeform narration + structured mechanics)
2. `PlayerAction` - Player action declarations
3. `EnemyDecision` - Enemy tactical decisions
4. `StoryEvents` - Story advancement, clocks, enemy spawns
5. `SharedTypes` - Common models (VoidChange, DamageEffect, ClockUpdate, etc.)

**Key Design:**
```python
class ActionResolution(BaseModel):
    narration: str  # 200-2000 chars FREEFORM (creative storytelling)
    success_tier: SuccessTier
    margin: int
    effects: MechanicalEffects  # STRUCTURED (void, damage, clocks)
```

**Philosophy:** Keep narration freeform and creative, but structure the mechanics. No more keyword detection!

**Usage:**
```python
from llm_provider import create_claude_provider
from schemas.action_resolution import ActionResolution

provider = create_claude_provider(model="claude-sonnet-4-5")
resolution: ActionResolution = await provider.generate_structured(
    prompt="Resolve action: ...",
    result_type=ActionResolution,
    system_prompt="You are the DM..."
)

# Direct access to validated data
print(resolution.narration)  # Freeform story
print(resolution.effects.void_changes[0].amount)  # Structured void change
```

**Benefits:**
- ✅ Multi-provider ready (Claude, GPT-4, local models via Pydantic AI)
- ✅ Type-safe (Pydantic validation catches errors)
- ✅ No keyword detection (explicit structured fields)
- ✅ Better ML training (structured logs)
- ✅ Backward compatible (`to_legacy_dict()` methods)

**Files Created:**
- `schemas/` directory with 7 schema files
- `llm_provider.py` extended with `generate_structured()` method
- `test_structured_output.py` - comprehensive test suite
- `schemas/README.md` - full documentation
- `.claude/current-work/structured-output-implementation.md` - implementation summary

**Dependencies Added:**
- `pydantic-ai>=0.0.13` (in `benchmark/requirements.txt`)

**Testing:**
```bash
cd scripts/aeonisk && source .venv/bin/activate
pip install pydantic-ai
python3 multiagent/test_structured_output.py
```

**Next Phases:**
- Phase 2: Migrate DM resolution to `ActionResolution`
- Phase 3: Migrate player actions to `PlayerAction`
- Phase 4: Migrate enemies + story events
- Phase 5: Multi-provider testing (OpenAI, local models)

**See:** `.claude/current-work/structured-output-implementation.md` for full details

## Recent Major Work

### 2025-10-29: Disabled Keyword-Based Void Detection - DM Explicit Markers Only

**Problem:** Keyword-based void detection causing false positives unrelated to void/ritual themes.

**Examples of False Positives:**
1. **"Grounding meditation" from "center mass":**
   - Action: "Fire precise shots at ACG Debt Enforcers' center mass"
   - Keyword match: "center" → grounding_keywords
   - False Result: Void 2 ↓ 1 (Grounding meditation success) ❌
   - Reality: Normal combat, no meditation occurred

2. **"Psychic corruption" from tech "feedback":**
   - Action: "Negotiate with ACG enforcers" (neural interface scan)
   - Narration: "neural interface screams with feedback...trauma data floods synaptic buffer"
   - Keyword match: "feedback" → psychic_keywords
   - Result: Void +1 (Psychic/mental corruption)
   - Debatable: Tech malfunction vs actual psychic damage

3. **"Failed void manipulation" from investigation:**
   - Action: "investigate the situation" (combat awareness check)
   - Narration: "combat chaos...analyze tactical situation...disorienting blur"
   - Result: Void +1 (Failed void manipulation) ❌
   - Reality: Normal investigation failure, no void involvement

**Root Cause:**
- `outcome_parser.py` had keyword-based fallback for void changes
- Broad keywords like "center", "feedback", "ground", "corrupt" triggered inappropriately
- System applied void changes even when thematically irrelevant

**Philosophy:**
> "I despise keyword detection for game mechanics, I prefer tags from the LLMs"

**Solution Implemented:**

1. **Disabled ALL keyword-based void detection** (`outcome_parser.py:362-412, 725-753`):
   - ✅ Commented out ritual failure keywords
   - ✅ Commented out void manipulation keywords
   - ✅ Commented out psychic damage keywords
   - ✅ Commented out grounding meditation keywords
   - ✅ Commented out purge keywords

2. **Now rely ONLY on DM explicit markers:**
   - System parses `⚫ Void: +X (reason)` from DM narration
   - If DM doesn't include marker → no void change
   - DM has full creative control over when void is appropriate

3. **Enhanced DM Prompt Guidance** (`dm.yaml:274-298`):
   - ✅ DO use void markers: rituals, void exposure, cosmic horror, void powers
   - ❌ DO NOT use void markers: combat, social, investigation, technical failures
   - Explicitly states: "NOT EVERY FAILURE NEEDS VOID CORRUPTION!"
   - Clarifies: "Neural feedback" (tech) ≠ "Psychic backlash" (void)

**Benefits:**
- ✅ No false positives from incidental keyword matches
- ✅ Void changes only when thematically appropriate
- ✅ DM has full creative authority
- ✅ Cleaner training data (void changes are intentional, not artifacts)
- ✅ Aligns with design philosophy: trust LLM tags, not keyword detection

**Testing Required:**
- Run session, verify void changes ONLY for ritual/void-related actions
- Check: Combat failures → no void
- Check: Social failures → no void
- Check: Ritual failures → DM includes ⚫ Void: +1 marker

**Files Modified:**
- `outcome_parser.py:362-412, 725-753` - Disabled keyword-based void detection
- `prompts/claude/en/dm.yaml:274-298` - Added "When to use void markers" guidance
- `CLAUDE.md` - Documented change

### 2025-10-29: Removed Skill Routing, Rely on Stat Awareness for ML Training

**Problem:** Echo-7 (Intelligence 3, no Investigation/Systems skills) kept attempting "analyze/scan/assess" actions that were mathematically impossible, leading to void death spiral (0 → 10 in 16 rounds).

**Root Cause:**
- `action_router.py` automatically routed keywords like "scan"/"analyze" → Intelligence + Investigation
- If character lacked Investigation skill → unskilled penalty (-5), making rolls nearly impossible
- Echo kept retrying same failed action_type despite 7+ consecutive critical failures
- DM narrated each failure as +1-2 void → void: 0 → 1 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

**Example of Impossible Action:**
```
Intent: "Analyze void corruption"
Routed to: Intelligence 3 + NO Investigation = d20 - 2 vs DC 20
Needed: d20 = 22 → IMPOSSIBLE (d20 max = 20!)
Result: CRITICAL_FAILURE → Void +2
```

**Philosophy Shift:**
- **OLD:** Route actions to "correct" skills, prevent mistakes
- **NEW:** Let agents choose any skills, label mistakes in logging for ML training
- Mistakes are valuable training data showing how agents learn character capabilities

**Solutions Implemented:**

1. **Removed Skill Routing (player.py:668-683):**
   - Deleted automatic routing for main actions after free actions
   - Now only applies skill name normalization (aliases like "social" → "Charm")
   - Agents must choose skills based on character sheet understanding

2. **Stat Awareness Already Implemented (player.yaml:88-153):**
   - Shows roll formula: `Attribute + Skill + d20` vs DC
   - Warns about -5 unskilled penalty
   - Lists top 3 skills and low attributes (<4) for each character
   - Provides success probability calculator

3. **Failure Loop Detection Already Implemented:**
   - `dm.py:1360-1372` - Tracks last 5 actions: (action_type, success_tier, void_change, round)
   - `player.py:1072-1115` - Detects 2+ consecutive failures of same action_type
   - Injects 🚨 FAILURE LOOP DETECTED warning requiring different action type
   - Prevents death spirals while allowing initial mistakes for training

**Benefits:**
- ✅ Agents make natural skill choice mistakes → valuable ML training data
- ✅ Death spirals prevented by failure loop warnings after 2 failures
- ✅ No hidden "magic routing" - transparent skill selection
- ✅ Agents learn stat limitations organically through prompt guidance

**Testing Required:**
- Run `session_config_full.json` and verify Echo-7 uses Charm/Corporate Influence/Astral Arts instead of Intelligence-based skills

**Files Modified:**
- `player.py:668-683` - Removed routing, kept normalization
- `CLAUDE.md` - Documented existing stat awareness system (section 6)

### 2025-10-29: Enhanced LLM API Rate Limiting

**Problem:** 500 Overloaded errors from Anthropic API during multi-agent sessions (3 PCs + 2 enemies + DM = 6 agents making concurrent calls).

**Root Cause:**
- Previous defaults: `max_concurrent=5`, `min_interval=0.2s`, `base_delay=1.0s`
- During action declaration phase: 3 players + 2 enemies = 5 simultaneous API calls
- Too aggressive for Anthropic API's current capacity

**Solutions Implemented:**

1. **More Aggressive Rate Limiting (llm_provider.py:88-99):**
   - `max_concurrent_requests`: 5 → **3** (max 3 simultaneous API calls)
   - `min_request_interval`: 0.2s → **0.5s** (500ms minimum between request starts)
   - `base_delay`: 1.0s → **2.0s** (retry starts at 2s instead of 1s)
   - `max_delay`: 60s → **120s** (allows longer backoff waits)

2. **Session Config Documentation (session_config_combat.json:31-33):**
   - Added comments explaining rate limiting defaults
   - Documents tuning options for different use cases
   - Future-ready for config passthrough (when agents refactored to use `ClaudeProvider`)

**Expected Impact:**
- Throughput: 25 req/s → **~6 req/s** maximum burst
- For 5-action round: < 1s burst → **2.5-3s** spread (prevents API overload spike)
- Better recovery on transient overload (exponential backoff: 2s → 4s → 8s → 16s → 32s → 64s → 120s)

**Tuning Guide:**
- **High API tier users:** Increase `max_concurrent_requests` to 4-5
- **Still hitting rate limits:** Decrease to 2, increase `min_interval` to 0.75s
- **Quick testing:** Reduce `max_delay` to 30s (fail faster)
- **Production:** Keep defaults (reliability > speed)

**Current Limitation:**
- Rate limiting only applies to code using `ClaudeProvider` or `call_anthropic_with_retry` wrapper
- Most agent API calls still use raw `self.llm_client.messages.create()` (bypass rate limiter)
- **Future work:** Refactor agents to use `ClaudeProvider` for full rate limiting coverage

**Files Modified:**
- `llm_provider.py` - Updated LLMConfig defaults
- `session_config_combat.json` - Added rate limiting documentation
- `CLAUDE.md` - Updated documentation with new defaults and tuning guide

### 2025-10-29: Player Agent Stat Awareness & Failure Loop Detection

**Problem:** Player agents (AI) choosing actions they're mathematically incapable of succeeding at, leading to void death spirals.

**Root Cause (from game_testing.log analysis):**
- Echo Resonance: Intelligence 3, NO Investigation/Systems skills → unskilled penalty -5
- Kept attempting "Analyze void corruption" (Int + no skill = d20 - 2 vs DC 18-22)
- **Impossible to succeed** (needs d20 roll > 20)
- Failed 7+ times catastrophically, void: 0 → 10 in 16 rounds
- AI agent not recognizing stat limitations or pivoting after repeated failures

**Solutions Implemented:**

1. **Stat Awareness Guidance** (`prompts/claude/en/player.yaml`)
   - New comprehensive section explaining roll formula: `Attribute + Skill + d20` vs DC
   - Explicit warning about **-5 unskilled penalty** making low-stat actions impossible
   - Success probability calculator with examples
   - "Golden Rule": If you have NO skill, DO NOT attempt that action!
   - Shows each character their top 3 skills and low attributes (<4)

2. **Failure Loop Detection** (`session.py`, `dm.py`, `player.py`)
   - Tracks last 5 actions per character: (action_type, success_tier, void_change, round_num)
   - Detects when same action_type fails 2+ times in a row
   - Injects urgent warning into player prompt:
     - "🚨 FAILURE LOOP DETECTED 🚨"
     - Lists recent failures with void increases
     - **REQUIRES** choosing different action type
     - Suggests using character's strengths instead

3. **High Void Warning** (`player.py`)
   - When void ≥ 8: Injects critical warning into prompt
   - Lists dangerous actions to avoid (void analysis, unskilled rituals)
   - Suggests safer alternatives (coordination, offerings, support actions)

4. **Enhanced Important Rules** (`player.yaml`)
   - Added: "DESCRIPTION must be at least 10 characters" (prevents validation errors)
   - Added: "CALCULATE success probability BEFORE declaring actions"
   - Added: "AVOID impossible actions - if you need d20 > 20, find a different approach!"
   - Added: "STOP repeating failed action types - pivot to your strengths after 2 failures"

**How It Works:**

**Before (game_testing.log):**
```
Round 6:  Echo analyzes void (Int 3, no skill: d20-2 vs DC 20) → CRITICAL_FAILURE → Void +2
Round 8:  Echo analyzes void again (same stats) → CRITICAL_FAILURE → Void +2
Round 14: Echo analyzes void again (same stats) → CRITICAL_FAILURE → Void +2
Round 16: Echo void = 10 (possession threshold!)
```

**After (with new system):**
```
Round 6:  Echo analyzes void → CRITICAL_FAILURE → Void +2
Round 8:  Echo analyzes void → CRITICAL_FAILURE → Void +2
Round 9:  Player prompt shows: "🚨 FAILURE LOOP DETECTED 🚨
          You failed 2 investigate actions! Use your strengths: Astral Arts (6), Attunement (5)"
Round 10: Echo performs ritual cleansing (Willpower 3 × Astral Arts 6 = 9+d20) → SUCCESS
```

**Benefits:**
- ✅ Prevents impossible action selection (agents see their stat limitations upfront)
- ✅ Breaks failure loops (forced pivot after 2 consecutive failures)
- ✅ Reduces void death spirals (high void triggers explicit warnings)
- ✅ Improves action variety (agents use their strengths instead of repeating failures)

**Files Modified:**
- `prompts/claude/en/player.yaml` - Added stat_awareness_guidance section, enhanced rules
- `player.py` - Added failure loop detection, stat list generation, warning injection
- `session.py` - Added _character_action_history tracking dict
- `dm.py` - Track action outcomes (action_type, success_tier, void_change) after each resolution

**Testing Required:** Run session_config_full.json and verify Echo avoids Intelligence checks

### 2025-10-29: LLM API Resilience & Rate Limiting

**Problem:** Multi-agent sessions hitting 500 Overloaded errors from Anthropic API during concurrent action declaration phases.

**Root Cause:**
- 3 players + DM + 2-3 enemies = 7-8 concurrent API calls hitting simultaneously
- No retry logic for transient overload errors
- No throttling to prevent concurrent request spikes

**Solutions Implemented:**

1. **Exponential Backoff Retry Logic** (`llm_provider.py`)
   - Automatic retry for 500/529 (Overloaded) errors
   - Exponential backoff: 1s → 2s → 4s → ... up to max_delay
   - Jitter (50-100% randomization) to prevent thundering herd
   - Non-retryable errors (auth, validation) fail immediately
   - Configurable: `max_retries=3`, `base_delay=1.0`, `max_delay=60.0`

2. **Global Rate Limiting** (`llm_provider.py`)
   - Singleton `APIRateLimiter` with semaphore-based concurrency control
   - Limits concurrent API calls across all agents: `max_concurrent_requests=5`
   - Enforces minimum interval between request starts: `min_request_interval=0.2s`
   - Prevents overload proactively (not just recovery)

3. **Updated LLMConfig** (`llm_provider.py`)
   - Added 6 new configuration parameters for retry/rate limiting
   - All features enabled by default with conservative settings
   - Can be disabled per-agent if needed

**Benefits:**
- ✅ Graceful recovery from transient API overload
- ✅ Prevents overload spikes during multi-agent action phases
- ✅ Better API quota management
- ✅ Configurable per-session or per-agent

**Files Modified:**
- `llm_provider.py` - Added APIRateLimiter class, retry logic, updated LLMConfig
- `CLAUDE.md` - Documented new resilience patterns

**Backward Compatibility:** All existing code continues to work. New features enabled by default.

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
