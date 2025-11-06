# NPC Escalation System - Quick Status (2025-11-05)

**TL;DR**: All code implemented (9 fixes, commit ed4a298), prompt loading issue FIXED. Ready for testing.

**UPDATE**: Issue was NOT caching - Phase 10 changes were made to monolithic `dm.yaml` but DM loads modular prompts from `dm/` directory. Fixed by moving changes to correct modular files.

## What Was Fixed (Commit: ed4a298)

### Core Escalation System ✅
1. **Wired escalation processing** (`session.py:2477-2510`)
   - NPCs → Enemies when attacked/threatened
   - Integrated into round synthesis

2. **Fixed context bug** (`session.py:842`)
   - Changed "Combat ended" → "No active threats"
   - NPCs no longer confused about combat state

### Prompt Improvements ✅
3. **Universal Nexus morality** ~~(`dm.yaml:622-627`)~~ → **NOW IN `dm/dm_state_tracking.yaml`**
   - Soulcredit from Nexus perspective (not PC faction)
   - Tempest infiltration = negative soulcredit

4. **Margin-based escalation triggers** (`dm/dm_commands.yaml:150-177`)
   - Low margin (0-5) = high escalation chance
   - High margin (11+) = low chance (NPC too scared)

5. **Emphasized NPC spawns** (`dm/dm_commands.yaml:105-116`)
   - DM reminded to populate world with NPCs

### Skill System Improvements ✅
6. **Player skill guidance** (`player.yaml:192-212`)
   - Intimidation → Charisma × Intimidation
   - Persuasion → Empathy × Charm

7. **DM skill override** ~~(`dm.yaml:348-371`)~~ → **NOW IN `dm/dm_core.yaml`**
   - DM can substitute correct skill

8. **Skill mismatch logging** (`dm.py:2801-2820`, `action_resolution.py:258-261`)
   - Detects + logs skill overrides to JSONL

9. **NPC despawn docs** (`tactical_resolution.py:137-138`)
   - Future implementation guidance

## Critical Issue: Wrong Prompt Files ⚠️ → ✅ FIXED

**Problem**: Phase 10 changes were made to **monolithic `dm.yaml`** but DM actually loads **modular prompts** from `dm/` directory.

**Root Cause Analysis**:
- DM uses `load_modular_prompt()` which loads from `dm/dm_core.yaml`, `dm/dm_commands.yaml`, etc.
- Changes were made to `dm.yaml:622-627` (Nexus morality) and `dm.yaml:348-371` (skill override)
- These sections in `dm.yaml` are NOT loaded during gameplay (only used for specialized task templates)
- Result: Changes never reached the DM system prompts

**Fix Applied (2025-11-05)**:
1. ✅ Moved Nexus morality to `dm/dm_state_tracking.yaml` (loaded when clocks present)
2. ✅ Moved skill override guidance to `dm/dm_core.yaml` (always loaded)
3. ✅ Verified escalation triggers already in `dm/dm_commands.yaml` (correct location)
4. ✅ Cleaned up `dm.yaml` - removed 900+ lines of redundant sections, kept only task templates
5. ✅ Added clear comments explaining modular system to prevent future confusion

**Files Changed**:
- `dm/dm_state_tracking.yaml` - Added UNIVERSAL NEXUS MORALITY section
- `dm/dm_core.yaml` - Added skill override guidance
- `dm.yaml` - Removed redundant sections (1034 lines → 86 lines), added navigation comments

## Test Results (Session 6f5b4fd0) - OLD TEST WITH WRONG PROMPTS

**Note**: This test used the wrong prompts (from monolithic dm.yaml). Ignore results - need fresh test with modular prompts.

### What Worked in Old Test ✅
- NPCs integrated into rounds
- NPCs declare "dialogue" and "pass" actions
- No false escalations (correctly null when no triggers)

### What Didn't Work (due to wrong prompts) ❌
- Soulcredit still mission-oriented (because UNIVERSAL NEXUS MORALITY wasn't loaded)
- No escalations occurred (scenario had no violence, so inconclusive)

## Next Steps for Fresh Test

**Test scenario config**: `scripts/session_configs/session_config_npc_escalation_tempest.json`

**What to test**:
- Intimidation actions (test skill selection + escalation triggers)
- Violence against NPCs (test immediate escalation)
- Low-margin social actions (test margin-based escalation)
- Tempest vs Nexus actions (test Nexus morality framework)

**How to run**:
```bash
source .venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_npc_escalation_tempest.json
```

**Verify prompts loaded correctly**:
```bash
# Get latest session file
SESSION=$(ls -t multiagent_output/session_*.jsonl | head -1)

# Check if UNIVERSAL NEXUS MORALITY text appears in DM prompts
python3 scripts/analyze_session.py $SESSION --search event_type=llm_call agent_type=dm --line 1 | grep -q "UNIVERSAL NEXUS MORALITY" && echo "✅ New prompts loaded" || echo "❌ Old prompts still loading"

# Check soulcredit scoring in action resolutions
python3 scripts/analyze_session.py $SESSION --search event_type=action_resolution --fields soulcredit_delta,soulcredit_reasons
```

## Files Changed (8 files, 203 additions, 45 deletions)

- `session.py` - Escalation processing loop
- `dm.py` - Skill mismatch detection
- `dm.yaml` - Nexus morality + skill override guidance
- `dm_commands.yaml` - Margin-based escalation triggers
- `player.yaml` - Skill selection guidance
- `action_resolution.py` - skill_override schema field
- `tactical_resolution.py` - Despawn docs
- `session_config_npc_escalation_tempest.json` - Test config

## Related Docs

- **Full design**: `.claude/NPC_ENTITY_DEESCALATION_DESIGN.md` (Phase 10 section)
- **Commit**: `ed4a298552d160da6b500ce9d9a9e12b21306a16`
- **Branch**: `npcs-and-deescalation`

## Key Git Commands

```bash
# View commit details
git show ed4a298 --stat

# See all NPC-related commits
git log --oneline --grep="NPC\|escalation" --since="2025-11-04"

# Check current branch
git status
```

---

**Status**: Implementation complete, awaiting fresh test run to verify prompt loading.
