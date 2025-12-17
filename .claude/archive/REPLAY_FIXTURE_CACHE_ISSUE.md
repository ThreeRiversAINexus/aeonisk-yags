# Replay Fixture LLM Cache Alignment Issue

**Date:** 2025-11-02
**Context:** Attempted to replay `regression_combat_cultist_spawn_bug.jsonl` with `--all-cached` mode
**Status:** Blocked - cache key misalignment

## Problem Summary

The replay tool (`scripts/replay_fixture.py`) fails to replay extracted fixtures due to LLM call cache key mismatches. Even in `--all-cached` mode (which should be deterministic), the MockLLM client reports cache misses.

## Error Pattern

```
❌ MockLLM: Cache miss for ('player_02', 0). Available keys: [('player_01', 7), ('player_04', 7), ('player_02', 10), ('player_03', 7), ('dm_01', 38)]...
Anthropic API error (non-retryable): 'No cached response for player_02 call #0. Replay has diverged from original session.'
```

**Key observation:** The MockLLM has keys like `('player_02', 10)` but is looking for `('player_02', 0)`. This suggests:
- Cache was populated with call indices from the **full session** (rounds 0-13)
- Replay is requesting calls starting from index **0** (expecting rounds 8-12 to be remapped)

## Root Cause Hypothesis

### Cache Key Structure
LLM calls are cached with keys: `(agent_id, call_index)`
- `call_index` = global call counter for that agent across the entire session
- Example: Round 8's first player call might be the agent's 10th call overall

### What `extract_fixture.py` Does
1. Extracts rounds 8-12 from full session
2. Includes LLM calls from those rounds
3. Saves LLM calls with **original call indices** (e.g., call #10, #11, #12...)

### What `replay_fixture.py` Expects
1. Loads cached LLM calls
2. Starts executing from round 8
3. **Requests calls starting from index 0** (assumes remapping happened)

### The Mismatch
- **Cache has:** `player_02` calls at indices [10, 11, 12, 13, ...]
- **Replay requests:** `player_02` call at index 0
- **Result:** Cache miss → replay fails

## Why This Happens

The `extract_fixture.py` tool correctly preserves original call indices (necessary for analyzing sessions), but `replay_fixture.py` assumes call indices are **sequential from 0** for the extracted range.

**Architectural assumption conflict:**
- Fixtures preserve **absolute call indices** (good for analysis)
- Replay expects **relative call indices** (good for deterministic replay)

## Potential Solutions

### Option 1: Remap Call Indices in `replay_fixture.py` (Recommended)
When loading a fixture for replay:
1. Detect minimum call index for each agent
2. Remap all indices: `new_index = old_index - min_index`
3. MockLLM uses remapped indices

**Pros:** Preserves fixture integrity, fixes replay
**Cons:** Adds complexity to replay loader

### Option 2: Extract with Remapped Indices
Modify `extract_fixture.py` to remap LLM call indices:
1. Find minimum call index per agent in extracted range
2. Subtract offset when writing fixture
3. Add metadata field: `llm_call_index_offset`

**Pros:** Simple replay logic
**Cons:** Loses original call indices (harder to correlate with source session)

### Option 3: Fixture Transformation Tool (Cleanest)
Create `scripts/transform_fixture.py`:
- Input: Fixture with absolute indices
- Output: Fixture with relative indices (or vice versa)
- Metadata: Records transformation applied

**Pros:** Separates concerns, preserves both formats
**Cons:** Extra tool to maintain

## Recommended Approach

**Option 3** (Fixture Transformation Tool) is cleanest long-term:
```bash
# Extract with original indices (for analysis)
python scripts/extract_fixture.py session.jsonl --rounds 8-12 --output baseline.jsonl

# Transform for replay (remap to relative indices)
python scripts/transform_fixture.py baseline.jsonl --remap-llm-indices --output baseline_replay.jsonl

# Replay works correctly
python scripts/replay_fixture.py baseline_replay.jsonl --all-cached --output replayed.jsonl
```

Alternatively, add `--remap-llm-indices` flag to `extract_fixture.py` to generate replay-ready fixtures directly.

## Immediate Workaround

For now, skip replay verification for extracted fixtures. Use:
1. **Unit tests** to verify code changes (no LLM calls needed)
2. **Fresh sessions** to test integrated behavior (generate new baseline)
3. **diff_fixtures.py** to compare mechanical outcomes between fixtures

The enemy spawn fix is already verified by comprehensive unit tests in `test_enemy_spawn_structured.py`.

## Testing Verification Status

- ✅ **Unit tests passing:** 6 tests in `test_enemy_spawn_structured.py` (0.21s)
- ✅ **Spawn fix verified:** Import error resolved, parameter mapping correct
- ⚠️ **Replay blocked:** LLM cache alignment issue (documented here)
- ✅ **Fixture extracted:** 1.8MB regression baseline for future use

## Related Files

- Fixture: `tests/fixtures/sessions/regression_combat_cultist_spawn_bug.jsonl`
- Extract tool: `scripts/extract_fixture.py`
- Replay tool: `scripts/replay_fixture.py`
- Unit tests: `tests/unit/test_enemy_spawn_structured.py`
- MANIFEST: `tests/fixtures/sessions/MANIFEST.json`

## Resolution (2025-11-02)

**Root Cause:** Fixture was extracted from rounds 8-12 (mid-session), causing LLM `call_sequence` to start from 7+ instead of 0.

**Solution:** Re-extracted fixture from rounds 0-12 using:
```bash
python scripts/extract_fixture.py \
  multiagent_output/session_2f34635a-24ee-4bf7-8c01-1faab6d42d25.jsonl \
  --rounds 0-12 \
  --output tests/fixtures/sessions/regression_combat_cultist_spawn_bug.jsonl \
  --overwrite
```

**Result:**
- ✅ LLM call_sequence now starts from 0
- ✅ Replay with --all-cached works successfully (114 LLM calls cached, no cache misses)
- ✅ Updated MANIFEST.json to reflect rounds 0-12

**Key Insight:** When extracting fixtures for replay testing, always extract from round 0 to ensure call_sequence indices are sequential from 0. This avoids cache key misalignment without requiring complex remapping logic.

---

**Note:** This issue doesn't block the enemy spawn bug fix (already tested and working via unit tests). It only affects replay-based verification workflows.
