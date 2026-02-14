# De-escalation System Review (Filed 2026-02-14)

## Status: Pending — Design work for a future pass

## Current State

The de-escalation system is **mechanically sound** (agent ID stable, stats preserved, NPC actions work)
but **lacks intelligence** for realistic decisions.

## Key Gaps

### 1. Enemy Personality Not in Tactical Prompts
- Enemies have personality traits (`surrender_if_cornered`, `flee_when_broken`, `fight_to_death`)
  stored on the `EnemyAgent` object
- These traits are **never injected into the tactical prompt** sent to the LLM
- An enemy with `surrender_if_cornered` still gets told to fight
- **Files:** `enemy_agent.py:323,432-439`, `enemy_prompts.py`

### 2. No Faction Context in Enemy Decisions
- Enemies know their faction but don't understand **why** factions are allied/hostile
- Tactical prompts show allies/hostiles as a filtered list but never explain relationships
- No "you work for ACG, aligned with Sovereign Nexus, opposing Tempest" context
- **Files:** `enemy_prompts.py`, `faction_utils.py`

### 3. De-escalation is 100% DM-Controlled
- Enemies have NO mechanism to volunteer surrender or negotiate
- Only the DM can force conversion via `ConversionDecisions.deescalations`
- Enemy action types: Attack, Shift, Retreat, Charge, Suppress, Push_Through, FLEE
- Missing: Parley, Surrender, Negotiate action types
- **Files:** `dm.py:3784-3809`, `enemy_combat.py`

### 4. No DM Decision Tree for De-escalation
- DM is told "use `deescalations` field" but gets no guidance on WHEN
- No health/morale thresholds suggested
- No personality-driven trigger recommendations
- **Files:** `dm_conversion_check.yaml`

### 5. NPC Faction Awareness Gap
- Converted NPCs don't make faction-aware decisions
- An ACG prisoner won't resist helping anti-Nexus PCs based on faction conflict
- **Files:** `npc_agent.py`

## What Works Well
- Agent ID stability through enemy<->NPC conversions
- Stat preservation (health, skills, weapons, soak, void_score)
- NPC autonomous action system with memory
- Faction relationship queries (`are_factions_allied()`)

## Recommended Future Work
1. Inject personality traits into enemy tactical prompts
2. Add faction relationship context to enemy and NPC prompts
3. Add "Surrender" or "Negotiate" as enemy action types (DM still validates)
4. Create DM decision tree for de-escalation triggers (health %, morale, personality)
5. Add faction-aware dialogue guidance for converted NPCs
