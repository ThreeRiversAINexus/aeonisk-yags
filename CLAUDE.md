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

**Log levels (for debugging):**
```bash
# Standard mode (INFO) - clean logs, session progress only
python3 scripts/run_multiagent_session.py config.json --log-level INFO

# Debug mechanics without LLM spam (DEBUG) - mechanics details, hides API calls
python3 scripts/run_multiagent_session.py config.json --log-level DEBUG

# Debug API calls only (LLM) - shows API activity, hides mechanics
python3 scripts/run_multiagent_session.py config.json --log-level LLM

# Ultra-verbose (TRACE) - line-by-line parsing, state transitions
python3 scripts/run_multiagent_session.py config.json --log-level TRACE
```
See `.claude/CUSTOM_LOG_LEVELS.md` for details on custom log levels.

## Multi-Provider LLM Support

**Current default:** `gpt-5-mini` via OpenAI or Batch Proxy (for bulk generation). Rate limits auto-apply per provider.

### API Keys

```bash
export OPENAI_API_KEY="your-key-here"     # For GPT models (primary)
export ANTHROPIC_API_KEY="your-key-here"  # For Claude models (if needed)
```

### Session Config

```json
{
  "agents": {
    "dm": {
      "llm": {
        "provider": "openai",
        "model": "gpt-5-mini",
        "temperature": 0.7
      }
    }
  }
}
```

### Switching Providers

To switch an existing session config from Claude to OpenAI:
1. Change `"provider": "anthropic"` → `"provider": "openai"`
2. Change `"model": "claude-sonnet-4-5"` → `"model": "gpt-5-mini"`
3. Set `OPENAI_API_KEY` environment variable
4. Run session normally - rate limits auto-adjust

**Example:**
```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run with OpenAI provider
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_openai_test.json
```

### Testing

```bash
# Unit tests for OpenAI provider
python -m pytest tests/unit/test_openai_provider.py -v

# Live API test (requires OPENAI_API_KEY)
python -m pytest tests/unit/test_openai_provider.py::TestOpenAIProviderLiveAPI -v
```

### Batch Proxy Provider (Cost Optimization)

**Purpose:** Route LLM requests through a batching proxy server for 50% cost reduction on bulk operations.

The batch proxy provider wraps the UnifiedAIClient from aeonisk-transmedia-pipeline, enabling cost-optimized LLM calls by queueing and batching requests together.

**Supported Backends:**
- OpenAI (gpt-5-mini, gpt-4o-mini, etc.)
- Anthropic (claude-sonnet-4-5, etc.)

**Cost Savings:**
- **50% reduction** via provider Batch APIs
- **Trade-off:** Higher latency (requests queued until batch threshold reached)
- **Best for:** Bulk generation runs (100+ sessions), overnight training data generation

**In session config JSON:**
```json
{
  "agents": {
    "dm": {
      "llm": {
        "provider": "batch_proxy",
        "model": "gpt-5-mini",
        "temperature": 0.7,
        "underlying_provider": "openai",
        "use_proxy": true,
        "proxy_url": "http://localhost:8000",
        "proxy_priority": "normal",
        "proxy_strategy": "auto"
      }
    }
  }
}
```

**Configuration Parameters:**
- `underlying_provider`: "openai" or "anthropic" (determines fallback API and model catalog)
- `use_proxy`: Enable proxy routing (default: true for batch_proxy provider)
- `proxy_url`: Proxy server URL (default: http://localhost:8000)
- `proxy_priority`: Request priority - "high" (direct API), "normal" (auto-route), "low" (always batch)
- `proxy_strategy`: Routing strategy - "auto" (proxy decides), "direct" (force immediate), "batch" (force batching)

**Environment Variables (Alternative):**
```bash
export USE_LLM_PROXY=true
export LLM_PROXY_URL=http://localhost:8000
export LLM_PROXY_MODE=auto  # auto, direct, or batch
```

**Automatic Fallback:**
- If proxy unreachable, automatically falls back to direct API (3 retries with exponential backoff)
- No code changes needed, transparent routing

**Bulk Session Runner:**

Run multiple sessions in parallel with batch proxy support:

```bash
# Basic bulk run (100 sessions, 20 workers)
python scripts/bulk_session_runner.py \
  --config session_config.json \
  --runs 100 \
  --workers 20 \
  --output-dir bulk_output/

# With proxy (cost optimization)
python scripts/bulk_session_runner.py \
  --config session_config.json \
  --runs 100 \
  --workers 20 \
  --proxy http://localhost:8000 \
  --output-dir bulk_output/

# Preview effective routing + validate configs WITHOUT launching anything
python scripts/bulk_session_runner.py \
  --configs config1.json config2.json \
  --proxy http://localhost:8000 \
  --dry-run

# Resume failed runs
python scripts/bulk_session_runner.py \
  --config session_config.json \
  --runs 100 \
  --output-dir bulk_output/ \
  --resume

# Multiple configs
python scripts/bulk_session_runner.py \
  --configs config1.json config2.json \
  --runs-per-config 50 \
  --output-dir bulk_output/
```

**Flag vs config precedence (IMPORTANT):** the session config JSON is
authoritative. CLI flags only take effect when explicitly passed, and every
override of a config value is logged per agent. In particular, `--proxy`
alone does NOT touch `proxy_strategy` — each config's own strategy is
honored. To force a strategy across all configs, pass
`--strategy direct|batch|auto` (`--direct` is a deprecated alias). Every
launch prints an "Effective routing" banner showing each agent's
provider/model/strategy and where the strategy came from; `--dry-run` shows
it without launching. Configs are validated at launch
(`launch_config.validate_session_config`, same checks as the unit tests);
`--skip-validation` bypasses (needed for some legacy configs under
`session_configs/experiment/` and `session_configs/openai/`).

**Orchestrator Features:**
- Parallel execution via ProcessPoolExecutor (subprocess-based, crash isolation)
- Automatic proxy health check before execution
- Preflight config validation + effective-routing banner (see above)
- Resume capability (skip completed runs)
- Aggregated statistics (success rate, tokens, throughput)
- Per-run output isolation (prevents JSONL collisions)
- Summary report generation (JSON format)

**Test Config:** `scripts/session_configs/session_config_batch_proxy_test.json`

**Testing:**
```bash
python -m pytest tests/unit/test_batch_proxy_provider.py -v
python -m pytest tests/unit/test_bulk_runner.py -v
```

**Design Documentation:** See `.claude/BATCH_GENERATION.md` for architecture details

**Prerequisites:**
1. Start batch proxy server in aeonisk-transmedia-pipeline:
   ```bash
   cd ../aeonisk-transmedia-pipeline
   python main.py proxy-start
   ```
2. Verify proxy health:
   ```bash
   curl http://localhost:8000/health
   ```

## Development Philosophy

### Test-Driven Development (TDD) - MANDATORY

**How this engine is tested: see `.claude/TESTING_PRACTICE.md`.** It documents the
six modes (extract / recombine / extrapolate / oracle rows / mutation / property)
and the standing rules. Read it before adding tests to a new surface.

The one rule, because a green suite is not evidence: **a check that cannot fail
is worse than no check.** Nine engine defects were found in one audit while the
suite was green at 4,317 tests, and three of those tests were concealing bugs.
Every test family must be *shown* to fail — break the thing it guards, watch it
go red, put it back.

**CRITICAL:** All code changes MUST be driven by tests written FIRST.

1. **Write failing tests BEFORE writing implementation code**
   - Define desired behavior through tests
   - Run tests to confirm they fail (red phase)
   - Only then implement code to make tests pass (green phase)

2. **No code changes without tests**
   - Refactoring existing code? Write characterization tests first
   - Adding new features? Write feature tests first
   - Fixing bugs? Write regression tests that reproduce the bug first

3. **Test location:**
   - Unit tests: `tests/unit/test_*.py`
   - Integration tests: `tests/integration/test_*.py`
   - Run with: `python -m pytest tests/unit/test_file.py -v`

**Example TDD workflow:**
```bash
# 1. Write failing tests
vim tests/unit/test_new_feature.py
python -m pytest tests/unit/test_new_feature.py -v  # Expect failures

# 2. Implement minimum code to pass tests
vim scripts/aeonisk/multiagent/module.py

# 3. Run tests again
python -m pytest tests/unit/test_new_feature.py -v  # Expect passes
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

### 6. NPC & De-escalation System
**Core Principle:** agent_id is STABLE across ALL conversions (never changes)

- **Conversion:** `deescalate_enemy_to_npc()`, `escalate_npc_to_enemy()`, `subdue_enemy_to_prisoner()`
- **NPC Actions:** flee, hide, plead, comply, dialogue, assist, pass (no attack/tactical)
- **DM declares** via `RoundSynthesis.deescalations` / `escalations` / `npc_spawns`
- **Files:** `npc_agent.py`, `agent_conversion.py`, `schemas/story_events.py`
- **Tests:** `python -m pytest tests/unit/test_npc*.py tests/unit/test_agent_conversion.py -v`

### 7. Economy & Vendor System
**Core Principle:** Pre-validated deterministic transactions (executed before DM narration)

- **5 Currencies** (`EnergyPurse`): breath, grain, drip, spark, hollow
- **Item Types:** consumable, food (+2 HP), tool, seed, offering, exchange, prop, equipment
- **Transaction Flow:** Pre-validate → Execute → DM narrates (atmospheric only)
- **Files:** `energy_economy.py`, `player_action.py`, `mechanics.py:2974+`
- **Tests:** `python -m pytest tests/unit/test_vendor*.py tests/unit/test_item_type*.py -v`

## ML Logging System

**Authoritative Schema Reference:** `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`
- Read this when working on JSONL logging, adding events, or understanding schema structure
- 19 event types with full JSON schemas and use cases
- Includes narrative reconstruction guide

**Tools:**
- `analyze_session.py` - **Quick session analysis (use this instead of reading huge JSONL files!)**
- `extract_fixture.py` - Extract round ranges from sessions for testing
- `diff_fixtures.py` - Compare fixtures to verify bug fixes
- `replay_fixture.py` - Replay fixtures with selective LLM caching ✅ **Production Ready**
  - **Timing:** Intentionally slow (300-600s for 1-2 rounds) due to API rate limiting (0.5s/request, max 3 concurrent)
  - Use long timeouts in tests to avoid false failures
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

# Error analysis - ~10-50 lines
python scripts/analyze_session.py session.jsonl --mode=errors
```

#### Targeted Event Extraction

```bash
# Search events
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution
python scripts/analyze_session.py session.jsonl --search event_type=action_resolution round=2 --count

# Get specific line
python scripts/analyze_session.py session.jsonl --line 12
```

**Error analysis:** `--mode=errors` finds validation warnings, LLM fallbacks, action failures

### Fixture Tools (Test Regression & Code Verification)

**Problem:** When fixing bugs, how do you verify the fix actually changed behavior?

**Solution:** Extract-Replay-Diff workflow using real gameplay sessions as test cases

#### Workflow: Verify Code Fixes

```bash
# 1. Extract buggy session rounds
python scripts/extract_fixture.py \
  multiagent_output/session_void_bug.jsonl \
  --rounds 0-3 \
  --output tests/golden/void_bug_before.jsonl

# 2. Fix bug in code (edit mechanics.py, dm.py, etc.)

# 3. Replay with fix (players cached, DM uses live LLM with new code)
python scripts/replay_fixture.py \
  tests/golden/void_bug_before.jsonl \
  --cache-player-actions \
  --output tests/golden/void_bug_after.jsonl

# 4. Compare results
python scripts/diff_fixtures.py \
  tests/golden/void_bug_before.jsonl \
  tests/golden/void_bug_after.jsonl \
  --focus effects.void_changes

# Output shows exactly what changed due to your fix
```

#### Tool 1: extract_fixture.py ✅ Production Ready

**Purpose:** Extract round ranges from production sessions → test fixtures

```bash
# Extract rounds 0-3 (includes all dependencies: session_start, llm_calls, enemies)
python scripts/extract_fixture.py \
  multiagent_output/session_bug.jsonl \
  --rounds 0-3 \
  --output tests/fixtures/sessions/bug_baseline.jsonl

# Extract single round
python scripts/extract_fixture.py session.jsonl --rounds 2 --output round2.jsonl

# Validate without writing
python scripts/extract_fixture.py session.jsonl --rounds 0-3 --validate-only
```

**What it does:**
- Extracts specified round range with all dependencies
- **Smart LLM call inclusion:** Captures player/enemy declaration LLM calls even though they have `round: null` (occur before round starts)
- Validates completeness (random_seed, required events, LLM cache)
- Outputs standard JSONL fixture ready for replay or tests

**Recent fixes:**
- Now correctly includes player/enemy LLM calls (was only including DM calls)
- Handles `None` round values in validation

#### Tool 2: replay_fixture.py ✅ Production Ready

**Purpose:** Replay fixture scenario with NEW code, selective LLM caching

```bash
# All cached (verify deterministic replay - should match original exactly)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/baseline.jsonl \
  --all-cached \
  --output /tmp/replay_check.jsonl

# Players cached, DM live (test mechanics fixes)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/baseline.jsonl \
  --cache-player-actions \
  --output tests/fixtures/sessions/after_fix.jsonl

# Hybrid mode: Cache rounds 0-1, generate round 2 live, stop after round 2
python scripts/replay_fixture.py \
  tests/fixtures/sessions/baseline.jsonl \
  --all-cached \
  --cache-until-round 1 \
  --max-rounds 2 \
  --output /tmp/round2_live.jsonl

# Start from specific round (skip early rounds for targeted debugging)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/baseline.jsonl \
  --all-cached \
  --start-from-round 2 \
  --max-rounds 3 \
  --output /tmp/rounds_2_3.jsonl

# No caching (all live LLM - expensive!)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/baseline.jsonl \
  --no-cache \
  --output /tmp/all_live.jsonl
```

**Key features:**
- `--cache-player-actions`: Cache players/enemies, DM uses live LLM (test mechanics fixes)
- `--cache-until-round N`: Cache all agents until round N, then switch to live (hybrid mode)
- `--max-rounds N`: Stop after N rounds (useful for testing specific rounds)
- `--start-from-round N`: Skip rounds 0 to N-1, start from round N (isolate specific rounds)
- `--all-cached`: Full deterministic replay (should match original exactly)
- `--no-cache`: All live LLM calls (expensive)

**Key insight:** Players do same actions (cached), DM adjudicates with new mechanics (live LLM)

**Requires:** Anthropic API key (for live DM calls)

**Known issues:**
- ✅ Pydantic AI API updated (fixed RunResult → AgentRunResult, .data → .output)
- ✅ Anthropic import error fixed (lazy initialization in DMLLMClient)
- ✅ Hybrid mode works (--cache-until-round tested and functional)
- ⚠️ Replay takes 5-10 minutes even with --max-rounds 1 (use appropriate timeouts)
- ⚠️ Live LLM generation may misclassify combat actions as 'investigate' (see test_action_type_classification.py)

#### Tool 3: diff_fixtures.py ✅ Production Ready

**Purpose:** Compare before/after fixtures, highlight mechanical changes

```bash
# Compare all mechanical fields
python scripts/diff_fixtures.py before.jsonl after.jsonl

# Focus on specific fields
python scripts/diff_fixtures.py before.jsonl after.jsonl --focus effects.void_changes

# Multiple focus fields
python scripts/diff_fixtures.py before.jsonl after.jsonl \
  --focus effects.damage.dealt effects.void_changes roll.success

# JSON output for scripting
python scripts/diff_fixtures.py before.jsonl after.jsonl --json
```

**What it compares:**
- Mechanical fields: damage, void, rolls, health, clocks
- **Ignores:** DM narration flavor text (expected to differ)
- Exit code: 0 if identical, 1 if differences (useful for CI/scripting)

**Default focus fields:**
- `roll.success`, `roll.total`, `roll.margin`, `roll.tier`
- `effects.damage.dealt`, `effects.void_changes`, `effects.soulcredit_changes`
- `health`, `void_score`, `wounds`, `is_defeated`

**Verified working:**
- ✅ Correctly identifies identical fixtures (exit 0)
- ✅ Detects mechanical differences between fixtures (exit 1)
- ✅ Event alignment works for comparing different round ranges

#### Use Cases

**Verify bug fix:**
```bash
# Bug: Void changes doubled when void_level > 5
extract_fixture.py session_void8.jsonl --rounds 0-3 --output before.jsonl
# (fix bug in mechanics.py)
replay_fixture.py before.jsonl --cache-player-actions --output after.jsonl
diff_fixtures.py before.jsonl after.jsonl --focus effects.void_changes
# Shows: void +6 → +3 ✓ FIXED
```

**Create minimal test fixture:**
```bash
# Extract just the rounds that reproduce a bug
extract_fixture.py huge_session.jsonl --rounds 7-9 --output bug_reproduction.jsonl
# Use in tests/integration/ for regression test
```

**Validate deterministic replay:**
```bash
replay_fixture.py fixture.jsonl --all-cached --output replay.jsonl
diff_fixtures.py fixture.jsonl replay.jsonl
# Should show: "✅ Fixtures are identical"
```

See `tests/fixtures/README.md` for fixture naming conventions, lifecycle, and management.

### 8. Conservative Fuzzy Name Matching
**Purpose:** Automatically resolve shortened character names in void_changes/soulcredit_changes

**Problem it solves:** DM uses "Sera Karsel" instead of "Vessel Sera Karsel" → validation warnings

**How it works:**
```python
# DM returns shortened name
VoidChange(character_name="Sera Karsel", amount=-1, reason="purification")

# System fuzzy matches to full name
Matched: "Sera Karsel" → "Vessel Sera Karsel" ✓

# Applied to correct character
```

**Safety rules:**
1. Exact match first (no fuzzing if name matches exactly)
2. Suffix match only (provided name must be end of full name)
3. Minimum 2 words required (rejects "Sera" - too ambiguous)
4. Single candidate only (rejects if multiple characters match)
5. Never guess (ambiguous = FAIL with clear error)

**Files:**
- Core: `name_matching.py` (match_character_name, resolve_character_name)
- Processing: `outcome_parser.py:59-86` (void_target_character fuzzy matching)
- Validation: `structured_output_helpers.py:525-552` (validation warnings)
- Tests: `tests/unit/test_name_matching.py` (16 tests, all pass)

**When it triggers:** Automatically on every void_change processing (no config needed)

**Logging:**
- INFO: `"Fuzzy matched void target: 'Sera Karsel' → 'Vessel Sera Karsel'"`
- WARNING: `"Could not match void target 'Bob Smith': No character found..."`

### 9. NPC Name Generation (Aeonisk Names MCP)
**Purpose:** Replace the DM's hallucinated `NPCSpawn.name` with a canonically-grounded Pattern B name from `aeonisk-names-mcp`.

**Enable in session config:**
```json
{
  "names_mcp": { "enabled": true, "from_pool": true }
}
```

**Behavior:**
- Hook lives in `dm.py:_process_npc_spawn` (single chokepoint for all DM-spawned NPCs).
- Maps yags faction display name → MCP kebab id, and `NPCSpawn.pronouns` → gender (she/her→feminine, he/him→masculine, else→ambiguous).
- Non-canon yags factions (Void / Independent / Unknown) skip the MCP entirely — LLM name stands.
- Any MCP failure (exception, empty pool, repeated reservation conflict) fails open to the LLM name.
- Reservations recorded with `owner=f"yags:{session_id}"`; cleanup via `aeonisk-names-bank purge`.

**Install (editable):**
```bash
source .venv/bin/activate
pip install -e ../aeonisk-names-mcp/
```

**Files:** `names_client.py` (wrapper), `dm.py:9377+` (hook), `session.py:974+` (config wiring).
**Tests:** `tests/unit/test_names_client.py`, `tests/unit/test_dm_npc_spawn_naming.py`.

### 10. Bond System
**Core Principle:** Structured output schemas drive all bond mechanics with automatic Void-driven transitions

- **Bond Types:** Kinship, Ascendancy, Debt, Voidward, Passion, Faction
- **Bond Status:** Active → Dormant (Void ≥7) → Void-Locked (Void=10, permanent); Severed (sacrificed)
- **Benefits:** +2 ritual bonus (bonded participant), +1 Soak (defending partner), sacrifice for +5 Willpower
- **Auto-transitions:** Void changes trigger dormancy/recovery automatically
- **Files:** `schemas/shared_types.py`, `mechanics.py`, `action_router.py`
- **Tests:** `python -m pytest tests/unit/test_bond*.py -v`
- **Design doc:** `.claude/BOND_SYSTEM_DESIGN.md`

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

### Attribute System Conformance (Dec 2025)

**YAGS Standard Attributes (8 total):**
- Strength, Agility, Endurance (Aeonisk uses this instead of YAGS "Health"), Dexterity
- Perception, Intelligence, Empathy, Willpower (Aeonisk uses this instead of YAGS "Will")

**Migration completed:** Removed non-standard "Charisma" attribute that had crept into configs/code.

**Skill remapping:**
- Guile, Corporate Influence → Empathy (social/political understanding)
- Command, Intimidation → Willpower (mental domination/leadership)

All 73 session configs and 8 Python modules now conform to YAGS + Aeonisk standard. See `tests/unit/test_attribute_migration.py` for regression tests.

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
2. `.claude/ARCHITECTURE.md` - System architecture
3. `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` - ML logging/schema details

## Session Testing & Configuration

**Division of Labor:**
- **Claude runs:** Unit tests (`python -m pytest tests/unit/<test_file>.py -v`)
- **Multi-agent sessions:** either party. Claude may run them when asked — these
  cost real API spend, so confirm scope first and prefer the 2-round smoke config
  over a full run. Use `scripts/session_status.py <dir> --wait` to detect
  completion or a stall (exit-coded); do not poll with `pgrep`, which matches the
  polling command itself.
- **Free alternatives before spending:** replay a recorded session
  (`"provider": "scripted"`), mine the corpus (`scripts/domain_mine.py`), or run
  the invariants over existing output. Most questions do not need a new session.

### Session Config Validation (TDD)

Session configs are automatically validated via `tests/unit/test_session_config_validation.py`:

```bash
# Run all session config validation tests
python -m pytest tests/unit/test_session_config_validation.py -v
```

**What's validated:**
- Required fields (session_name, max_turns, agents, party_size)
- Deprecated patterns (`scenario.initial_clocks` → `starting_clocks`)
- Tactical module dependencies (both `tactical_module_enabled` + `enemy_agents_enabled` required)
- Character schema compliance (name, faction, llm config)
- Clock format (supports both `current/max` and `current_ticks/max_ticks`)

**TDD workflow for configs:**
1. Tests written FIRST to define expected structure
2. Configs validated against tests
3. Failing tests indicate config issues (red → green)

### Character Library

**Pre-built characters:**
- `session_config_full.json` - 21 characters across 10 factions (canonical pool)
- `session_config_golden_comprehensive.json` - 4 archetype characters (Investigator, Diplomat, Combat, Tech)
- `datasets/aeonisk_character_examples.yaml` - Full YAGS character sheets (archival reference, not used in sessions)

**Character referencing (future):**
- Planned: `{"character_ref": "Character Name"}` to load from shared library
- Current: Inline character definitions only

**Session Config Features:**
- `party_capabilities_enabled` (default true) - player prompts include teammates' top skills/attributes so agents can route tasks; `party_chat_enabled` (default true) - party-directed ambient speech renders as a dedicated "Party chatter" block (same-round for faster declarers, carried into next round)
- `dm_assessment_enabled` (default true) - one DM call per round rules authoritative difficulty + ratifies attribute/skill framing before dice; player difficulty_estimate stays a logged counterfactual
- `starting_clocks` - Load pre-configured scene clocks at session start
- `initial_enemies` - Spawn enemies at session start without DM prompting
- Environmental void_level updates via `StoryAdvancement.new_void_level`
- `force_combat` + `combat_scenario_index` - Force specific combat scenarios
- `_scenario_hint` - Guidance for DM scenario generation
- `_design_notes` - Document complex config intent (golden configs only)
- See `scripts/session_config_README.md` for full configuration guide (v1.2.0+)

**Test Configs:**
- `session_config_void_story_advancement_test.json` - Tests void_level updates
- `session_config_starting_clocks_test.json` - Tests clock loading
- All test configs use contrived scenarios (max_turns=1-2) for rapid validation

## Known Issues

### dm_commands.yaml Section 6 Outdated
**File**: `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_commands.yaml` lines 93-200

**Issue**: "6. NPC Management" section contains 107 lines of outdated instructions about spawning/converting entities in RoundSynthesis.

**Why it's safe to ignore**: 
- RoundSynthesis schema no longer has entity management fields
- Pydantic will reject any attempts to use removed fields
- Entity lifecycle has dedicated prompts in `dm_conversion_check.yaml`
- DM physically cannot follow those instructions anymore

**Future work**: Remove section 6 and replace with minimal note directing to Entity Lifecycle Phase prompts.

