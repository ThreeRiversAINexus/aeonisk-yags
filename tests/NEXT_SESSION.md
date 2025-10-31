# Testing Session - Next Steps

**Last Updated:** 2025-10-31

## 📊 Current Status

**Total Tests:** 199
**Passing:** 148 (74% pass rate)
**Failing:** 46
**XFail:** 1
**XPass:** 4

### New Tests Added This Session

Added **37 new passing tests** across 4 new test files:

- ✅ `test_logging_completeness.py` - 13 tests (11 passing, 2 failing)
- ✅ `test_agent_context.py` - 9 tests (5 passing, 3 failing, 1 xfail)
- ✅ `test_yags_compliance.py` - 14 tests (13 passing, 1 failing)
- ✅ `test_tactical_module.py` - 10 tests (all passing!)

**Infrastructure:**
- ✅ Fixed Makefile to use correct venv path (`.venv/bin/activate` instead of `scripts/aeonisk/.venv`)
- ✅ Created `tests/fixtures/README.md` - Guide for generating and using test fixtures

---

## 🐛 Failing Tests Summary

### Category 1: Data Structure Mismatches (Easy Fixes)

These failures are due to actual event structure differing from expected format:

**test_logging_completeness.py:**
- `test_every_declaration_has_resolution` - Agent identifier matching logic needs refinement
- `test_all_rounds_have_synthesis` - Round 0 exists but no synthesis (edge case)
- `test_all_rounds_have_round_start` - Round 0 missing round_start event

**test_agent_context.py:**
- `test_dm_has_character_states` - DM prompt structure different than expected
- `test_enemy_sees_player_characters` - Player name extraction logic needs work
- `test_context_reflects_previous_round` - Assertion too strict for round 0
- `test_clocks_visible_to_relevant_agents` - Clock mention pattern needs adjustment

**test_yags_compliance.py:**
- `test_roll_calculation_correct` - One roll has unexpected ability value (needs investigation)

**Recommendation:** Review actual JSONL structure and adjust test expectations. Most are INFO/WARNING soft checks rather than critical failures.

---

### Category 2: Pre-Existing Test Failures (Known Issues)

These were already failing before this session:

**test_mechanics.py (33 failures):**
- Tests assume MechanicsEngine API that doesn't match actual implementation
- Functions like `get_difficulty_recommendation()`, `calculate_dc()` don't exist
- Clock/condition/void APIs have different signatures
- **Action:** Align tests with actual MechanicsEngine interface OR implement missing methods

**test_outcome_parser.py (4 failures):**
- Legacy text parsing tests fail (expected - we moved to structured output)
- `test_roundtrip_structured_to_legacy` - Conversion not implemented
- **Action:** Either fix legacy parsing or mark as xfail/skip

**test_jsonl_validation.py (2 failures):**
- `test_timestamps_monotonic` - Async operations cause timestamp overlap (known limitation)
- `test_action_declaration_events` - Field name mismatch
- **Action:** Relax timestamp assertions, fix field checks

---

## 🎯 High-Priority Next Steps

### 1. Fix New Test Failures (1-2 hours)

**Quick wins to get to ~155+ passing tests:**

```python
# test_logging_completeness.py fixes:
# - Add round 0 handling (skip synthesis check or expect different structure)
# - Improve agent identifier matching (handle player_id vs character_name variations)

# test_agent_context.py fixes:
# - Make player name extraction more robust
# - Add round 0 guard clauses
# - Relax "should mention" checks to soft warnings

# test_yags_compliance.py:
# - Investigate the one roll calculation mismatch (might be legitimate bug)
```

### 2. Expand YAGS Compliance Testing (2-4 hours)

**Current:** 14 tests
**Potential:** 30-50 tests

**Missing critical tests:**
- Difficulty tier ranges (Trivial=8, Easy=12, Moderate=18, Hard=23, Formidable=28, Ludicrous=33+)
- Skill usage validation (is correct skill used for action type?)
- Attribute selection (does combat use Agility/Strength appropriately?)
- Unskilled penalty (-5 when skill_val = 0)
- Critical success/failure thresholds (margin ≥15, margin ≤-10)
- Wound mechanics (if taking damage > threshold)
- Energy/fatigue tracking
- Initiative calculation (Perception × Awareness + d20)
- Success tier narration matching (excellent success should have excellent narrative)

**Example test to add:**

```python
def test_difficulty_tiers_correct():
    """Validate DC values match YAGS difficulty tiers."""
    tier_ranges = {
        'trivial': (0, 8),
        'easy': (9, 12),
        'moderate': (13, 18),
        'hard': (19, 23),
        'formidable': (24, 28),
        'ludicrous': (29, float('inf'))
    }
    # Check resolutions use correct DC for stated difficulty
```

### 3. Tactical Module Expansion (1-2 hours)

**Current:** 10 tests (all passing!)
**Potential:** 20-30 tests

**Missing tests:**
- Range-based weapon effectiveness (melee at Extreme should fail)
- Cover mechanics (if implemented)
- Flanking/positioning bonuses
- Movement action economy (Shift_1 = free, Shift_2+ = main action?)
- Position transition validation (can't jump Engaged → Far in one move)
- Area-of-effect position requirements
- Targeting restrictions by range

### 4. Integration Tests (3-5 hours)

**Currently:** Empty `tests/integration/` directory

**High-value integration tests:**
- `test_combat_round_flow.py` - Full declare→adjudicate→synthesize cycle
- `test_multi_round_session.py` - State persistence across rounds
- `test_enemy_agent_behavior.py` - Enemy AI decision making
- `test_dm_adjudication.py` - DM resolution patterns
- `test_clock_progression.py` - Clocks advancing through actual gameplay
- `test_void_escalation.py` - Void tracking in ritual scenarios

**Example:**

```python
@pytest.mark.asyncio
async def test_complete_combat_round(mock_llm):
    """Test full combat round with real session flow."""
    # Setup 2 PCs, 1 enemy, mock LLM responses
    # Run round 1: declarations → resolutions → synthesis
    # Verify JSONL logging complete
    # Verify state updates propagated
```

### 5. Fixture Generation Automation (2-3 hours)

**Goal:** Make it easy to generate test fixtures on demand

**Create:**
- `scripts/generate_test_fixture.py` - Run session, capture JSONL, save to fixtures
- Scenario templates for common test cases:
  - `combat_2pc_vs_3enemies.json`
  - `social_negotiation.json`
  - `ritual_high_void.json`
  - `tactical_positioning.json`

**Usage:**

```bash
python generate_test_fixture.py --scenario combat_2pc_vs_3enemies --rounds 3 --output combat_basic.jsonl
```

---

## 📋 Known Bugs Documented via @pytest.mark.xfail

These tests document known issues:

1. **test_void_ceiling_enforced** - Void can exceed 8 (should be capped)
2. **test_environmental_changes_persist** - Environmental state doesn't propagate across rounds
3. **test_extreme_range_has_penalty** - Range modifiers not consistently applied
4. **test_one_main_action_per_round** - Action economy tracking has gaps
5. **test_void_tracking_completeness** - Void changes not always logged (XPASS - might be fixed!)

**Action:** Create GitHub issues for each, prioritize fixes.

---

## 🧪 Test Categories by Priority

### Must Have (Blocking release)
- ✅ Schema validation (37/37) - **COMPLETE**
- ✅ Shared state (37/37) - **COMPLETE**
- ✅ JSONL validation (22/24) - **NEARLY COMPLETE**
- 🟡 Logging completeness (11/13) - **FIX 2 TESTS**
- 🟡 YAGS compliance (13/14) - **FIX 1 TEST**

### Should Have (Important for quality)
- ✅ Tactical module (10/10) - **COMPLETE**
- 🟡 Agent context (5/9) - **FIX 4 TESTS**
- ❌ Integration tests (0/0) - **START HERE**

### Nice to Have (Future work)
- 🟡 Mechanics (7/40) - **ALIGN WITH ACTUAL API**
- 🟡 Outcome parser (8/19) - **FIX LEGACY OR REMOVE**
- ❌ Performance tests - **NOT STARTED**
- ❌ Stress tests (high void, many enemies) - **NOT STARTED**

---

## 🔍 Specific Failing Test Details

### test_logging_completeness.py

**test_every_declaration_has_resolution**
```
AssertionError: Declaration by Siege Perimeter in round 1 has no resolution
```
Issue: Agent identifier "Siege Perimeter" (character_name) doesn't match resolution agent field.
Fix: Improve matching logic to check character_name, player_id, and agent fields.

**test_all_rounds_have_synthesis**
```
AssertionError: Round 0 missing round_synthesis/summary
```
Issue: Round 0 is used for scenario generation, no actual combat.
Fix: Skip round 0 or expect different event structure.

**test_all_rounds_have_round_start**
```
AssertionError: Round 0 missing round_start
```
Same as above - round 0 is special case.

---

### test_agent_context.py

**test_dm_has_character_states**
```
WARNING: DM prompt missing character state in round 1
```
Issue: Character state might be in context differently than expected.
Fix: Check actual DM prompt structure, adjust search pattern.

**test_enemy_sees_player_characters**
```
Assertion failed - enemy prompt doesn't mention players
```
Issue: Player name extraction from events may be incomplete.
Fix: Improve character name collection logic.

**test_context_reflects_previous_round**
```
AssertionError: Round 2 prompt for enemy suspiciously short
```
Issue: Prompt length check too strict or round 2 doesn't exist in fixture.
Fix: Check if round 2 exists before testing, or use different fixture.

**test_clocks_visible_to_relevant_agents**
```
INFO: Clocks exist but never mentioned in prompts
```
Issue: Clock data exists but not surfaced in prompts (possible design issue).
Fix: Soft warning only - may be expected behavior.

---

### test_yags_compliance.py

**test_roll_calculation_correct**
```
AssertionError: Ability calculation wrong
```
Issue: One action_resolution has attr_val × skill_val ≠ ability.
Fix: Investigate specific event - might be legitimate bug or special case (ritual? untrained?).

---

## 🛠️ Recommended Work Session Flow

**Session Goal:** Get to 165+ passing tests (from 148)

**Phase 1: Quick Wins (30 min)**
1. Fix round 0 handling in logging/context tests (+3 tests)
2. Improve agent identifier matching (+1 test)
3. Relax context checks to soft warnings (+2 tests)
4. Investigate roll calculation mismatch (+1 test potentially)

**Phase 2: YAGS Expansion (1-2 hours)**
5. Add difficulty tier validation tests (+5-8 tests)
6. Add skill/attribute usage tests (+3-5 tests)
7. Add unskilled penalty tests (+2 tests)
8. Add success tier validation (+3 tests)

**Phase 3: Integration (1-2 hours)**
9. Create basic combat round integration test (+1 test)
10. Add state persistence test (+1 test)
11. Add JSONL replay test (+1 test)

**Expected outcome:** 165-175 passing tests, clear path to 200+

---

## 📚 Resources

### Test Patterns

**Loading combat events:**
```python
@pytest.fixture
def combat_events():
    jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events
```

**Grouping by round:**
```python
def parse_into_rounds(events):
    rounds = {}
    for event in events:
        if 'round' in event:
            round_num = event['round']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(event)
    return rounds
```

**Flexible field checking:**
```python
# Handle multiple possible field names
agent = (event.get('agent') or
         event.get('character_name') or
         event.get('player_id'))
```

### Documentation

- `tests/README.md` - Testing guide and infrastructure
- `tests/fixtures/README.md` - Fixture generation guide
- `content/Aeonisk - YAGS Module - v1.2.2.md` - Game rules reference
- `content/experimental/Aeonisk - Tactical Module - v1.2.3.md` - Positioning rules
- `CLAUDE.md` - Project patterns (access mechanics, JSONL logging, etc.)

### Running Tests

```bash
# All tests
make test

# Just unit tests
make test-unit

# Specific file
make test-schemas
source .venv/bin/activate && cd scripts && python -m pytest ../tests/unit/test_yags_compliance.py -v

# With coverage
make test-cov

# Specific test with verbose output
source .venv/bin/activate && cd scripts && python -m pytest ../tests/unit/test_logging_completeness.py::TestRoundCompleteness::test_all_rounds_have_synthesis -vv -s
```

---

## 🎯 Success Metrics

### Current Session Achievements
- ✅ Added 37 new passing tests
- ✅ Created 4 new test suites
- ✅ Fixed Makefile venv paths
- ✅ Documented fixture generation process
- ✅ Established YAGS/Tactical compliance testing foundation

### Next Session Targets
- 🎯 165+ passing tests (from 148)
- 🎯 All new tests passing (fix 7 failing tests)
- 🎯 At least 1 integration test working
- 🎯 Clear documentation of remaining work

### Long-term Goals
- 🎯 200+ passing tests
- 🎯 80%+ pass rate
- 🎯 Full YAGS rule coverage
- 🎯 Integration test suite
- 🎯 Automated fixture generation
- 🎯 CI/CD pipeline ready

---

## 💡 Ideas for Future Tests

### Rule Edge Cases
- What happens when void = 10? (corruption threshold)
- What happens with 0 health/wounds?
- Can clocks go negative?
- What if initiative ties?
- Ritual failure consequences
- Soulcredit overflow (if capped)

### Gameplay Scenarios
- 4+ player coordination
- Enemy group tactics
- Environmental hazards (fire, void zones)
- Multi-target attacks
- Healing/support actions
- Retreat/escape attempts
- Negotiation during combat

### System Stress Tests
- 10+ enemies spawned
- 20+ round combat
- Rapid void accumulation
- Multiple clocks advancing simultaneously
- High-stakes ritual with multiple participants

### ML Training Data Quality
- Prompt diversity across sessions
- Response variety by agent type
- Token usage distribution
- Event sequence patterns
- State transition coverage

---

## 🚀 Quick Start for Next Session

1. **Review this document** - Understand current state
2. **Pick a category** - Quick wins, YAGS expansion, or integration
3. **Fix/add tests** - Follow patterns in existing files
4. **Run `make test-unit`** - Verify progress
5. **Update this doc** - Document changes and new priorities

---

**Questions? Check `tests/README.md` or ping in project chat.**

Good luck! 🎲
