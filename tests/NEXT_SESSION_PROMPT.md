# Next Session Prompt - Bug Fix #2 or Feature Work

Copy this prompt to start the next testing/bug-fixing session:

---

## Session Prompt

I'm working on the **aeonisk-yags** project (multi-agent AI tabletop RPG system). We just finished fixing Bug #1 (status effects incorrectly applied to actors). The test suite is at **97.5% pass rate (344/353 tests passing)**.

**Current Branch:** `test-driven-development`

### Context Documents
- Read `tests/NEXT_SESSION.md` for recommendations and priorities
- Read `tests/STATUS_EFFECT_BUG_FIX_SUMMARY.md` for reference on our last successful bug fix approach
- Read `CLAUDE.md` for project patterns and critical code locations

### Recommended Next Task: Fix Bug #2 - Environmental Void Changes

**Issue:** Similar to Bug #1, environmental void changes might be applied to actor instead of proper targets when `target="None"` or missing.

**What I need you to do:**

1. **Investigate** (`dm.py` around void change application)
   - Search for void change application code
   - Check if it has the same targeting bug pattern as Bug #1
   - Look for `void_changes` handling in action resolution

2. **Create failing test first** (TDD approach)
   - Create `tests/unit/test_environmental_void_targeting.py`
   - Write test that reproduces the bug
   - Mark as `@pytest.mark.xfail` initially

3. **Fix the bug**
   - Apply similar pattern to Bug #1 fix
   - Handle all edge cases: `target="None"`, `target=None`, missing, empty
   - Distinguish between void changes that should apply to actor vs environment

4. **Verify with real session**
   - Create test config (adapt from `session_config_status_effect_test.json`)
   - Run session and verify void changes apply correctly
   - Save as test fixture if successful

5. **Document and commit**
   - Update `tests/SESSION_NOTES.md`
   - Commit with clear message following our established pattern

### Alternative Tasks (if Bug #2 doesn't exist or is trivial)

**Option A:** Review the 5 XFail tests to see if any now pass or need updating

**Option B:** Implement ritual system improvements (see `tests/DESIGN_OBSERVATIONS.md` Section 4)

**Option C:** Add more fixture-based integration tests using existing session data

### Success Criteria
- [ ] Bug identified and fixed (or confirmed not to exist)
- [ ] Tests written and passing
- [ ] Test suite remains at 97%+ pass rate
- [ ] Changes committed with clear message
- [ ] Documentation updated

### Key Patterns to Follow
- Always activate venv: `source .venv/bin/activate`
- Test-driven approach: Write failing test first
- Use fixtures for integration tests
- Follow commit message format from Bug #1 fix
- Keep test pass rate above 97%

---

**Let me know if you have any questions or need clarification on the codebase!**
