# NPC Escalation System - Quick Status (2025-11-05)

**TL;DR**: All code implemented (9 fixes, commit ed4a298), but UNTESTED due to prompt cache bug. Fresh session needed.

## What Was Fixed (Commit: ed4a298)

### Core Escalation System ✅
1. **Wired escalation processing** (`session.py:2477-2510`)
   - NPCs → Enemies when attacked/threatened
   - Integrated into round synthesis

2. **Fixed context bug** (`session.py:842`)
   - Changed "Combat ended" → "No active threats"
   - NPCs no longer confused about combat state

### Prompt Improvements ✅
3. **Universal Nexus morality** (`dm.yaml:622-627`)
   - Soulcredit from Nexus perspective (not PC faction)
   - Tempest infiltration = negative soulcredit

4. **Margin-based escalation triggers** (`dm_commands.yaml:150-177`)
   - Low margin (0-5) = high escalation chance
   - High margin (11+) = low chance (NPC too scared)

5. **Emphasized NPC spawns** (`dm_commands.yaml:105-116`)
   - DM reminded to populate world with NPCs

### Skill System Improvements ✅
6. **Player skill guidance** (`player.yaml:192-212`)
   - Intimidation → Charisma × Intimidation
   - Persuasion → Empathy × Charm

7. **DM skill override** (`dm.yaml:348-371`)
   - DM can substitute correct skill

8. **Skill mismatch logging** (`dm.py:2801-2820`, `action_resolution.py:258-261`)
   - Detects + logs skill overrides to JSONL

9. **NPC despawn docs** (`tactical_resolution.py:137-138`)
   - Future implementation guidance

## Critical Issue: Prompt Cache Bug ⚠️

**Problem**: PromptLoader caches YAML files in memory. Changes to prompts NOT loaded until Python process restarts.

**Evidence**:
- `dm.yaml` edited at 16:43
- Session ran at 21:10 (97 minutes later)
- Session still has OLD prompts (checked: "UNIVERSAL NEXUS MORALITY" not present)

**Fix**: Kill process before each test run
```bash
pkill -f run_multiagent_session
sleep 2
python3 scripts/run_multiagent_session.py <config>
```

## Test Results (Session 6f5b4fd0)

### What Works ✅
- NPCs integrated into rounds
- NPCs declare "dialogue" and "pass" actions
- No false escalations (correctly null when no triggers)

### What Didn't Work ❌
- Soulcredit still mission-oriented (old prompts)
- No escalations occurred (but scenario had no violence, so expected)

## Next Steps for Fresh Session

**BEFORE running test**:
```bash
pkill -f run_multiagent_session
sleep 2
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_npc_escalation_tempest.json
```

**TEST scenario needs**:
- Intimidation actions
- Violence against NPCs
- Low-margin social checks
- Tempest vs Nexus conflict

**VERIFY after test**:
```bash
# Get first DM LLM call line
python3 scripts/analyze_session.py <session>.jsonl --search event_type=llm_call agent_type=dm --index

# Check if new prompts loaded (replace <LINE> with actual line number)
sed -n '<LINE>p' <session>.jsonl | grep -o 'UNIVERSAL NEXUS MORALITY'
# Should output: UNIVERSAL NEXUS MORALITY
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
