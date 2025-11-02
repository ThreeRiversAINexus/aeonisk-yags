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

## Development Philosophy

### Test-Driven Development (TDD) - MANDATORY

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

## ML Logging System

10 event types logged to JSONL: scenario, action_declaration/resolution, round_synthesis/summary, character_state, combat_action, enemy_spawn/defeat, mission_debrief. See `LOGGING_IMPLEMENTATION.md` for details.

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

#### Commentary: Is This Approach Valuable?

**TL;DR:** Yes for extract+diff, mixed on replay. The core insight is solid but execution complexity is high.

**What works well:**

1. **extract_fixture.py is genuinely useful** - Being able to isolate "the 3 rounds where the bug happens" from a 20-round session is valuable. Much better than "go read this 500KB JSONL file."

2. **diff_fixtures.py solves a real problem** - Before this, verifying a mechanics fix meant:
   - Run full session manually
   - Read through narrative looking for differences
   - Try to spot if damage/void/etc changed

   Now: `diff_fixtures.py --focus effects.damage.dealt` shows exactly what changed. This is huge.

3. **Real gameplay as test data** - Using actual LLM-generated scenarios as test cases is clever. You get edge cases you wouldn't think to write manually.

**What's harder than expected:**

1. **Replay complexity** - The replay tool is fighting against the architecture. Sessions weren't designed to be replayed with selective caching. The hang issue suggests deep assumptions about LLM client lifecycle.

2. **LLM call timing** - Player/enemy LLM calls having `round: null` reveals architectural assumptions (declaration happens "between" rounds). Had to add smart detection logic.

3. **Determinism challenges** - Even with caching, achieving byte-for-byte identical replay is hard. Random seeds, timestamps, async timing all matter.

**Practical workflow (without replay):**

Even without replay working, extract+diff is useful:
```bash
# Extract buggy session
extract_fixture.py session_bug.jsonl --rounds 2-4 --output before.jsonl

# Fix bug, run NEW session with same scenario
run_multiagent_session.py same_scenario_config.json

# Extract same rounds from new session
extract_fixture.py session_fixed.jsonl --rounds 2-4 --output after.jsonl

# Compare mechanical outcomes
diff_fixtures.py before.jsonl after.jsonl --focus effects.damage.dealt
```

This works because you can manually re-create similar scenarios, even if not byte-identical replay.

**Alternative: Unit tests with mocked LLM**

The fixture approach is expensive (real LLM calls). Could mock LLM responses for unit tests:
```python
def test_damage_extraction():
    mock_dm_response = "shoots enemy for 12 damage"
    result = parse_dm_response(mock_dm_response)
    assert result.damage.dealt == 12
```

But this misses emergent behavior from real LLM variance.

**Verdict:** Keep extract+diff, they're production-ready and solve real problems. Replay is architecturally interesting but may not be worth the debugging cost vs. just running new sessions.

## Fixture Management

### Fixture Naming Convention

All fixtures in `tests/fixtures/sessions/` follow this standard:

**Format:** `<purpose>_<scenario-type>_<descriptor>.jsonl`

- **purpose:** `golden` (reference fixture) | `regression` (bug reproduction) | `test` (integration test) | `baseline` (comparison baseline)
- **scenario-type:** `combat` | `social` | `investigation` | `ritual` | `mixed`
- **descriptor:** Brief kebab-case description (e.g., `status-effects`, `clock-removal`, `replay-fresh`)

**Examples:**
- `golden_replay_fresh.jsonl` - Reference implementation for replay system
- `regression_combat_action_type_bug.jsonl` - Reproduces action type misclassification
- `test_investigation_starting_clocks.jsonl` - Tests clock loading from config

### Fixture Lifecycle

**Active fixtures:**
- Used by current tests in `tests/unit/` or `tests/integration/`
- Documented in `tests/fixtures/sessions/MANIFEST.json`
- Must be regenerated after mechanics changes that affect their scenarios

**Deprecated fixtures:**
- Marked `"status": "deprecated"` in MANIFEST.json
- Can be deleted after verifying no tests reference them
- Typically deprecated when code they test is removed or fundamentally changed

**Golden fixtures:**
- Reference implementations (e.g., `replay_test_fresh.jsonl`)
- NEVER delete without team discussion
- Only regenerate when mechanics fundamentally change AND you verify mechanical equivalence

### Validating Fixtures

Before using a fixture for replay tests, verify it has complete LLM call data:

```bash
# Check fixture has player LLM calls (required for replay)
python scripts/analyze_session.py fixture.jsonl \
  --search event_type=llm_call source=player_llm_client --count
# Should show: "Found N matching events" (N > 0)

# Verify fixture structure and completeness
python scripts/analyze_session.py fixture.jsonl --mode summary
# Review: rounds, players, enemies, LLM calls
```

### Regenerating Fixtures After Code Changes

When mechanics change (e.g., damage calculation, void system), fixtures may need regeneration:

1. **Identify affected fixtures** (check MANIFEST.json for scenario types)
2. **Decide regeneration strategy:**
   - **Mechanics bug fix:** Create NEW fixture from fresh session (old fixture documents bug)
   - **Mechanics enhancement:** Regenerate existing fixture using replay tool

**Regeneration using replay (preserves player actions):**
```bash
python scripts/replay_fixture.py old_fixture.jsonl \
  --all-cached \
  --output new_fixture.jsonl
```

3. **Verify changes are expected:**
```bash
python scripts/diff_fixtures.py old_fixture.jsonl new_fixture.jsonl \
  --focus effects.damage.dealt effects.void_changes
```

4. **Update MANIFEST.json** with new `last_regenerated` date and commit hash

### Fixture Size Guidelines

- **Unit tests:** 1-3 rounds, ~50-200KB (fast, focused)
- **Integration tests:** 2-5 rounds, ~200-500KB (realistic scenarios)
- **Regression tests:** Minimal rounds to reproduce bug, ~100-300KB
- **Avoid:** >10 rounds or >1MB files (too slow, hard to debug)

If a fixture exceeds guidelines, extract minimal reproduction:
```bash
python scripts/extract_fixture.py large_session.jsonl \
  --rounds 7-9 \
  --output minimal_bug_repro.jsonl
```

### Fixture Metadata (MANIFEST.json)

All fixtures are cataloged in `tests/fixtures/sessions/MANIFEST.json` with:
- **created:** Date (YYYY-MM-DD)
- **created_by_commit:** Git SHA
- **purpose:** Why this fixture exists
- **scenario:** Brief description (e.g., "Gang Ambush (combat)")
- **rounds:** Number of rounds
- **has_player_llm_calls:** Boolean (required for replay)
- **last_regenerated:** Date + commit SHA (if regenerated)
- **status:** `active` | `deprecated`
- **used_by_tests:** List of test files referencing this fixture

See `tests/fixtures/sessions/MANIFEST.json` for current fixture inventory.

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
