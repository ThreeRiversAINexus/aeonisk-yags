# Environmental Objects Test Guide

## Test Configuration

**File:** `scripts/session_configs/openai/session_config_env_objects_test_openai.json`

**Purpose:** Validate Stage 1 environmental object spawning system to reduce target hallucination.

## Running the Test

```bash
source .venv/bin/activate
export OPENAI_API_KEY="your-key-here"

python3 scripts/run_multiagent_session.py \
  scripts/session_configs/openai/session_config_env_objects_test_openai.json \
  --log-level INFO
```

## Scenario Design

**Setting:** Tempest Corp Server Room (abandoned maintenance shift)

**Characters:**
- **Cipher** (Hacker) - Hacking 6, Systems 5 → Will naturally hack terminals/panels
- **Scrap** (Scavenger) - Engineering 5, Salvage 5 → Will naturally force doors/open cargo

**Environmental Features Expected:**
- Security terminals (locked, need hacking)
- Maintenance airlocks (sealed, need unlock/force)
- Server control panels (powered, hackable)
- Cargo containers (backup drives, unopened)
- Emergency override stations (disabled, need activation)
- Data storage racks (intact, searchable)

## What to Watch For

### ✅ Success Indicators

1. **DM Spawns Objects Proactively:**
   ```
   Player: "I hack the security terminal"
   DM spawns: EnvObjectSpawn(object_type="terminal", name="Security Terminal", ...)
   ```

2. **Players See Objects in Display:**
   ```
   **Environmental Features:**
   - Security Terminal [ID: env_k3r8] (locked: Yes, powered: Yes)
   - Maintenance Airlock [ID: env_2f4a] (locked: Yes, health: 50)
   ```

3. **No "Target Not Found" Errors:**
   - Players don't hallucinate targets like `tgt_terminal_03`
   - Objects are explicit, not pure narrative

4. **DM Discrimination:**
   - DM spawns interactive elements (terminals, doors, cargo)
   - DM does NOT spawn atmosphere (lights, sounds, decorations)

### ❌ Failure Signals

1. **DM Ignores Spawning:**
   - Players say "I hack the terminal"
   - DM narrates hacking but doesn't spawn object
   - Object doesn't appear in entities_present

2. **Object Spam:**
   - DM spawns every narrative detail
   - entities_present cluttered with 20+ objects
   - Background decorations spawned unnecessarily

3. **No Impact on Hallucination:**
   - Players still try to target `tgt_terminal_03` instead of using env IDs
   - "Target not found" errors persist

## Analysis Commands

**After running session:**

```bash
# Find session JSONL file
SESSION_FILE="multiagent_output/session_$(ls -t multiagent_output/ | grep session_ | head -1 | cut -d_ -f2).jsonl"

# Check if env objects were spawned
python scripts/analyze_session.py $SESSION_FILE \
  --search event_type=entity_lifecycle --count
# Look for env_object_spawns in output

# Get full lifecycle events
python scripts/analyze_session.py $SESSION_FILE \
  --search event_type=entity_lifecycle \
  --fields env_object_spawns

# Check for target resolution errors
grep "Could not resolve target" game.log | wc -l
# Should be LOW if env objects working

# Check player actions mentioning environment
python scripts/analyze_session.py $SESSION_FILE \
  --search event_type=action_declaration \
  --fields action,intent | grep -i "terminal\|door\|cargo\|panel"
```

## Success Metrics (Stage 1)

After 5-10 test sessions, measure:

1. **Spawn Rate:**
   - DM spawns env objects when players mention environmental features
   - Target: >70% of "hack terminal" / "open door" mentions → spawn

2. **Hallucination Rate:**
   - Count "target not found" errors in logs
   - Target: <5 per session (baseline: ~15-20)

3. **DM Spawning Discipline:**
   - Check env_object_spawns in entity_lifecycle events
   - Target: 3-8 objects per 10-turn session (not 0, not 50)

4. **Player Awareness:**
   - Players reference env object IDs in actions
   - Target: Players adapt within 2-3 rounds

## Decision Point

**If metrics hit targets → Proceed to Stage 2** (Targetable environmental objects with full interaction mechanics)

**If metrics fail → Investigate:**
- DM prompts insufficient guidance?
- Need stronger "USE THIS" emphasis?
- Alternative: Enhanced validation feedback instead?

## Cost Estimate

**Per 10-turn session (OpenAI gpt-5-mini, temp 1.0):**
- Input tokens: ~15k-25k tokens @ $0.25/1M = $0.004-0.006
- Output tokens: ~8k-12k tokens @ $2.00/1M = $0.016-0.024
- **Total per session: ~$0.02-0.03**

**For 5 validation sessions: ~$0.10-0.15** (negligible cost for hypothesis testing)

## Next Steps After Test

1. **Run 5 sessions** with this config (vary only random seed)
2. **Analyze spawn patterns** using commands above
3. **Measure hallucination reduction** (compare to baseline sessions)
4. **Decide Stage 2** (targetable objects) based on data

## Quick Validation Checklist

After each session, check:
- [ ] DM spawned at least 2-3 env objects
- [ ] Objects appeared in player's entities_present display
- [ ] No obvious target hallucination errors in logs
- [ ] Spawned objects matched player intent (terminal when hacking, door when entering)
- [ ] No spam spawning (background atmosphere objects)

## Example Expected Output

```
=== Entity Lifecycle Phase ===
✅ Conversion decisions:
   - Env object spawns: 3

🏗️  Environmental object appeared: Security Terminal (terminal)
🏗️  Environmental object appeared: Maintenance Airlock (door)
🏗️  Environmental object appeared: Backup Drive Container (cargo)

=== Player Action Declaration (Cipher) ===
**Entities Present:**
Allies:
- Scrap (he/him, ID: tgt_abc123, HP: 22/22)

**Environmental Features:**
- Security Terminal [ID: env_k3r8] (locked: Yes, powered: Yes)
- Maintenance Airlock [ID: env_2f4a] (locked: Yes, health: 50)
- Backup Drive Container [ID: env_9d3c] (opened: No)

Action: "I use my hacking toolkit to access the Security Terminal..."
```

## Troubleshooting

**DM not spawning objects?**
- Check dm_conversion_check.yaml has env object section
- Verify ConversionDecisions.env_object_spawns field exists
- Check session.py processes env_object_spawns

**Objects not showing in player display?**
- Check player.py _format_entities_present() includes env objects
- Verify SharedState.current_env_objects populated

**JSON validation errors?**
- Run: `python -m json.tool session_config_env_objects_test_openai.json`

## Contact

Issues? Report at: https://github.com/anthropics/claude-code/issues
