# Handoff: Unit Test Implementation for Replay System

**Date:** 2025-11-02
**Branch:** `test-driven-development`
**Last Commit:** `75bf130` - test: skip slow integration tests, document for future use
**Context:** Fresh context recommended (current: 119k/200k tokens used)

---

## 🚨 CRITICAL: USER HAS LIVE SESSION RUNNING

**DO NOT MODIFY GAME CODE** (`scripts/aeonisk/multiagent/*.py`) until the user confirms their session has completed!

**Running session:**
```bash
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_golden_comprehensive.json
```

This is a 20-turn comprehensive session with 4 players testing all game mechanics. Expected runtime: 30-60 minutes.

**What you CAN safely modify:**
- ✅ Test files (`tests/**/*.py`)
- ✅ Test mocks (`tests/mocks/*.py`)
- ✅ Analysis/tooling scripts (`scripts/analyze_session.py`, `scripts/extract_fixture.py`, etc.)
- ✅ Documentation files

**What you MUST NOT touch:**
- ❌ Core game logic (`scripts/aeonisk/multiagent/session.py`, `dm.py`, `mechanics.py`, etc.)
- ❌ LLM clients (`scripts/aeonisk/multiagent/llm_provider.py`)
- ❌ Prompt templates (`scripts/aeonisk/multiagent/prompts/**`)

---

## Current Status

### ✅ Completed Work (4 commits)

**Commit `ed62101` - Priority 1: Deleted deprecated fixture**
- Removed `player_llm_logging_baseline.jsonl` (782KB deprecated)
- Updated MANIFEST.json statistics

**Commit `417e800` - Priority 3: Created golden comprehensive session config**
- `session_config_golden_comprehensive.json` with 4 diverse players
- 20 turns, mixed scenario (investigation → social → combat → ritual)
- Vendor system, tactical module, 4 bidirectional clocks
- Designed to capture maximum mechanics variety for ML training

**Commit `b8b4e3e` - Priority 2: Merged validation logic**
- Added `--validate-fixture` mode to `analyze_session.py`
- New `FixtureValidator` class for schema + replay-readiness checks
- Exit codes: 0=pass, 1=fail (CI-friendly)
- Deprecated `validate_logging.py`

**Commit `75bf130` - Skipped slow integration tests**
- Marked `tests/integration/test_replay_system.py` tests as `@pytest.mark.skip`
- Documented why (5-10 min runtime, live API calls)
- Preserved for future comprehensive E2E validation

### 🔄 In Progress: Priority 4 - Mocked Unit Tests

**Goal:** Eliminate live LLM calls from tests, reduce runtime from 5.5min to <90s

**Current approach:**
- Skip slow integration tests (✅ done)
- Create fast unit tests in `tests/unit/test_replay_mocked.py` (⏳ pending)
- Use MockLLMClient with pre-recorded responses from fixtures

---

## Task: Implement Mocked Unit Tests for Replay System

### Context

**Problem:**
- Current integration tests in `test_replay_system.py` shell out to `replay_fixture.py` as subprocess
- Each test takes 5-10 minutes due to live API calls with rate limiting
- Total test runtime: ~15-30 minutes for 3 tests
- Expensive, slow, flaky

**Solution:**
- Write unit tests that directly import and test replay logic
- Use MockLLMClient to return pre-recorded responses
- Target runtime: <90 seconds total

### Architecture Overview

**Two mock implementations exist:**

1. **Production mock** (`scripts/aeonisk/multiagent/llm_logger.py`):
   - Used by replay system for cached responses
   - Simple interface: returns cached JSON responses

2. **Test mock** (`tests/mocks/mock_llm_client.py`):
   - Richer features for unit testing
   - Can simulate specific scenarios
   - More flexible assertion capabilities

**Key insight:** Tests should directly import replay logic and inject mocked LLM clients, NOT shell out to scripts.

### Files to Read (in order)

1. **`tests/mocks/mock_llm_client.py`** - Understand test mock API
2. **`scripts/aeonisk/multiagent/llm_logger.py`** - Find MockLLMClient class
3. **`scripts/replay_fixture.py`** - Identify testable functions/classes
4. **`tests/fixtures/sessions/replay_test_fresh.jsonl`** - Sample fixture for test data

### Unit Test Design Strategy

**Test coverage areas:**

1. **Fixture Loading** (`test_fixture_loading.py` or in main test file)
   - Load fixture JSONL
   - Parse session_start, scenario events
   - Extract LLM call cache
   - Validate fixture structure

2. **LLM Caching** (`test_llm_caching.py` or in main test file)
   - MockLLMClient returns cached response
   - Correct response selected by agent_id
   - Cache miss handling

3. **Replay Logic** (`test_replay_logic.py` or main file)
   - Replay single round with all-cached mode
   - Replay with hybrid mode (cache-until-round)
   - Verify mechanical outcomes (damage, void, clocks)

**Recommended structure:**

```python
# tests/unit/test_replay_mocked.py

import pytest
from pathlib import Path
from tests.mocks.mock_llm_client import MockLLMClient
# Import replay logic directly (not subprocess)
# This may require refactoring replay_fixture.py to be more modular

class TestFixtureLoading:
    def test_load_fixture_parses_session_start(self):
        # Load replay_test_fresh.jsonl
        # Assert session_start event exists
        # Assert config is parsed correctly
        pass

    def test_load_fixture_extracts_llm_cache(self):
        # Load fixture
        # Assert player LLM calls extracted
        # Assert DM LLM calls extracted
        pass

class TestLLMCaching:
    def test_mock_returns_cached_response(self):
        # Create MockLLMClient with fixture cache
        # Request response for specific agent_id
        # Assert correct cached response returned
        pass

class TestReplayLogic:
    def test_replay_single_round_all_cached(self):
        # Load fixture
        # Create session with MockLLMClient
        # Replay round 1
        # Assert mechanical outcomes match original
        pass

    def test_replay_hybrid_mode_cache_until_round(self):
        # Test cache-until-round=1
        # Round 0-1: cached, Round 2: live (mocked)
        pass
```

### Potential Refactoring Needed

**Problem:** `replay_fixture.py` is a CLI script, not a library

**Solution options:**

1. **Extract core logic to library module**
   - Create `scripts/aeonisk/multiagent/replay.py`
   - Move `load_fixture()`, `ReplaySession()` class to library
   - Keep `replay_fixture.py` as thin CLI wrapper
   - Tests import from library module

2. **Test via subprocess but with mocked environment**
   - Set environment variable to use mock LLM client
   - Still subprocess-based but avoids real API calls
   - Less ideal but simpler (no refactoring)

**Recommendation:** Option 1 (extract to library) if replay logic is complex, Option 2 (env var mock) if quick win needed.

---

## Implementation Checklist

**Phase 1: Research (30 min)**
- [ ] Read `tests/mocks/mock_llm_client.py` - understand API
- [ ] Read `scripts/aeonisk/multiagent/llm_logger.py` - find MockLLMClient
- [ ] Read `scripts/replay_fixture.py` - map testable units
- [ ] Read `replay_test_fresh.jsonl` - understand fixture structure

**Phase 2: Design (15 min)**
- [ ] Decide: refactor to library vs env var mock
- [ ] Design test class structure
- [ ] Identify which functions to test directly
- [ ] Plan test data (use replay_test_fresh.jsonl)

**Phase 3: Implementation (1-2 hours)**
- [ ] (If refactoring) Extract replay logic to library module
- [ ] Create `tests/unit/test_replay_mocked.py`
- [ ] Implement fixture loading tests
- [ ] Implement LLM caching tests
- [ ] Implement replay logic tests
- [ ] Ensure comprehensive coverage (not just happy path)

**Phase 4: Validation (15 min)**
- [ ] Run tests: `python -m pytest tests/unit/test_replay_mocked.py -v`
- [ ] Verify runtime <90s
- [ ] Verify all tests pass
- [ ] Verify no live API calls made (check logs)

**Phase 5: Commit**
- [ ] Git commit with detailed message explaining changes
- [ ] Update todo list

---

## Success Criteria

✅ Unit tests run in <90 seconds total
✅ No live API calls made during tests
✅ Tests cover fixture loading, LLM caching, replay logic
✅ Tests use MockLLMClient with pre-recorded responses
✅ All tests pass consistently
✅ Integration tests remain skipped but documented for future use

---

## After Tests Complete: Golden Fixture Extraction

**Once the user's session finishes:**

1. **Locate session output**
   ```bash
   ls -lh multiagent_output/session_golden_comprehensive_*.jsonl
   ```

2. **Validate fixture**
   ```bash
   python scripts/analyze_session.py multiagent_output/session_golden_*.jsonl --validate-fixture
   ```

3. **Extract to fixtures directory**
   ```bash
   python scripts/extract_fixture.py \
     multiagent_output/session_golden_*.jsonl \
     --rounds 0-19 \
     --output tests/fixtures/sessions/golden_comprehensive_mixed.jsonl
   ```

4. **Update MANIFEST.json**
   ```json
   "golden_comprehensive_mixed.jsonl": {
     "created": "2025-11-02",
     "created_by_commit": "<commit-sha>",
     "purpose": "Comprehensive golden fixture covering all mechanics",
     "scenario": "Void Convergence Investigation (mixed)",
     "rounds": 20,
     "players": 4,
     "has_player_llm_calls": true,
     "status": "active",
     "category": "golden"
   }
   ```

5. **Update statistics**
   ```json
   "statistics": {
     "total_fixtures": 9,
     "active": 9,
     "with_player_llm_calls": 2,
     "categories": {
       "golden": 2,
       "regression": 1,
       "test": 6
     }
   }
   ```

---

## Notes from User

- "make me proud!" - high expectations, thorough work appreciated
- Hobby project + magnum opus - this is passion project, treat with care
- Don't be intimidated - user values collaboration and learning
- SRE/red-team/AI power user background - appreciates clean architecture

---

## Git Status

**Current branch:** `test-driven-development`

**Recent commits:**
```
75bf130 test: skip slow integration tests, document for future use
b8b4e3e feat: add --validate-fixture mode to analyze_session.py
88b6259 tune: adjust rate limiting for large multi-agent sessions
417e800 feat: add golden comprehensive session config
29cd4bb chore: delete deprecated player_llm_logging_baseline fixture
```

**Clean working tree** (all changes committed)

---

## Resources

**Documentation:**
- `CLAUDE.md` - Essential patterns and quick start
- `tests/fixtures/sessions/MANIFEST.json` - Fixture catalog
- `.claude/ARCHITECTURE.md` - System architecture

**Key commands:**
```bash
# Run unit tests
python -m pytest tests/unit/test_replay_mocked.py -v

# Validate fixture
python scripts/analyze_session.py <fixture.jsonl> --validate-fixture

# Extract fixture
python scripts/extract_fixture.py <session.jsonl> --rounds 0-N --output <output.jsonl>
```

---

## Final Notes

**TDD philosophy:** Write tests FIRST, then implement to make them pass. The user values test-driven development.

**Don't break existing functionality:** Refactoring is allowed to make code testable, but preserve all existing behavior. Run existing tests after refactoring.

**Be thorough but efficient:** Comprehensive tests are good, but don't over-engineer. Aim for <90s runtime while covering critical paths.

Good luck! Make the user proud! 🚀
