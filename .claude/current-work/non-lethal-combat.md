# Non-Lethal Combat & De-Escalation System

**Branch:** `feature/non-lethal-deescalation`
**Started:** 2025-10-23
**Status:** In Progress

## Overview

Implementing weapon-driven damage types (stun/wound/mixed) and social de-escalation mechanics for the Aeonisk multi-agent combat system.

## Core Design Decisions

### Weapon-Driven Damage (Not Intent-Based)
**Rationale:** Follows YAGS canon (combat.md:76-84). Weapon type determines damage type automatically:
- **Fists/shock batons** → stun damage (non-lethal)
- **Batons/knives** → mixed damage (split stuns/wounds)
- **Guns/swords** → wound damage (lethal)

**Implementation:** Players equip weapons from inventory, damage resolution uses `weapon.damage_type`

### Rituals & Astral Arts
**Special case:** Rituals (e.g., Astral Arts) are open-ended and context-dependent:
- When targeting enemies offensively → typically wound damage (as lethal as gunfire)
- Can produce other effects (buffs, debuffs, environmental manipulation)
- Damage type inferred from narrative effect, not weapon stats
- **TODO:** Add ritual damage type resolution logic to DM adjudication

### Enemy Weapons
**Asymmetry:** Enemies have abstract weapon types (no inventory swapping), players get full inventory system.
- Simpler AI (enemies don't need to manage gear)
- Players get tactical depth (swap to non-lethal loadout for mercy runs)

## Implementation Progress

### Phase 1: Weapon System ✅ (Complete - Commit c7bcaca)
- ✅ Created `weapons.py` - shared Weapon/Armor dataclasses
- ✅ Added non-lethal weapons: shock_baton, tranq_gun, stun_gun, stun_grenade
- ✅ Helper functions: get_weapon(), list_weapons_by_type()
- ✅ Player weapon inventory with equipped/carried slots
- ✅ Initialize from character config with defaults (pistol + combat_knife)

### Phase 2-3: Damage Resolution & Stun Tracking ✅ (Complete - Commit 845587f)
- ✅ Added damage calculation functions to mechanics.py:
  - get_stun_effect(), get_wound_effect()
  - apply_stun_damage() - Non-cumulative YAGS rules
  - apply_wound_damage() - Cumulative (every 5 points = 1 wound)
  - apply_mixed_damage() - Split (odd → stuns, even → wounds)
- ✅ Updated enemy_combat.py to use weapon.damage_type
- ✅ Stun/wound thresholds with penalties and checks
- ✅ Unconscious check at 6+ stuns (Beaten)
- ✅ Death check at 6+ wounds (Fatal)

### Phase 4: Morale & Retreat/Escape ✅ (Complete - Commit 9e70c40)
- ✅ Added check_morale() to EnemyAgent (Willpower × d20 vs DC 20)
- ✅ Morale triggers: HP < 25%, last survivor, critical stuns (5+)
- ✅ Personality types: flee_when_broken, surrender_if_cornered, fight_to_death
- ✅ Prisoner status for surrendered enemies
- ✅ Fixed retreat/escape clock interaction:
  - Voluntary retreat: +3 to Escape Route clock
  - Morale flee: +2 to Escape Route clock
  - Semantics: Clock fills = escaped, partial = scattered
- ✅ Log morale_check events to JSONL
- ✅ Fixed JSONLLogger.log_event() signature bug (enemy_combat.py:1354)
- ✅ **TESTED**: Session 186bbfba (2025-10-23) - Morale system working correctly
  - Freeborn Pirates triggered morale check (last_survivor)
  - Roll: Willpower 2 + d20(3) = 5 vs DC 20 → FAILURE → flee
  - Successfully logged to JSONL with correct signature

### Phase 5: Social De-Escalation (Deferred)
**Status:** Not critical for initial testing, can add later
- ⏸️ Intimidate/Persuade player actions
- ⏸️ DM adjudication for social actions
- ⏸️ Mid-combat negotiation mechanics

### Phase 6: Enemy Morality & Soulcredit (Deferred)
**Status:** System works without this, can refine later
- ⏸️ Enemy morality tags (innocent/desperate/hostile/evil)
- ⏸️ Context-dependent soulcredit rewards
- ⏸️ Void penalties for excessive brutality

## Key Files Modified

### New Files
- `scripts/aeonisk/multiagent/weapons.py` - Weapon/armor library

### Modified Files (Planned)
- `player.py` - Weapon inventory
- `enemy_combat.py` - Damage resolution, morale
- `enemy_templates.py` - Import from weapons.py instead of enemy_agent.py
- `enemy_agent.py` - Remove Weapon/Armor classes (moved to weapons.py)
- `dm.py` - Social actions, morality system
- `session.py` - Prisoner tracking
- `mechanics.py` - Stun threshold calculations
- `validate_logging.py` - New event types

## YAGS Damage Rules Reference

### Stun Damage (combat.md:424-471)
**Non-cumulative:** If new stuns > current stuns, replace. Else if new stuns >= half current, +1.
```
Example: Currently 3 stuns, take 5 stuns → now 5 stuns
Currently 3 stuns, take 2 stuns → now 4 stuns (+1 only)
Currently 3 stuns, take 1 stun → no change
```

**Thresholds:**
- 0 = OK
- 1-2 = Light (-0/-5)
- 3-4 = Moderate (-10)
- 5 = Critical (-25)
- 6+ = Beaten (unconscious check, Willpower × d20 vs 20)

### Wound Damage (combat.md:390-422)
**Cumulative:** Every 5 points of damage = 1 wound. Wounds add together.
```
Damage 14 - Soak 12 = 2 dealt → 0 wounds (need 5 for 1 wound)
Damage 17 - Soak 12 = 5 dealt → 1 wound
Damage 24 - Soak 12 = 12 dealt → 2 wounds
```

**Thresholds:**
- 0 = OK
- 1-2 = Light (-0/-5)
- 3-4 = Moderate (-10)
- 5 = Critical (-25)
- 6+ = Fatal (death check, Health × d20 vs 20+)

### Mixed Damage (combat.md:477-482)
**Split:** First damage goes to stuns (cumulative), then wounds.
```
Mixed damage 7 → 4 stuns, 3 dealt as wounds (0 wounds, need 5)
Mixed damage 11 → 6 stuns, 5 dealt as wounds (1 wound)
```

**Odd damage goes to stuns:** 7 damage = 4 stuns, 3 wounds (not 3.5/3.5)

## Notes & Edge Cases

### Ritual Damage
- Rituals (Astral Arts, Void Manipulation) don't use weapon system
- DM determines damage type based on narrative effect
- Default: wound damage (as lethal as mundane attacks)
- Could be stun (binding spell), mixed (curse), or wound (void blast)
- **Implementation:** DM adjudication should check action description for ritual keywords, allow override of damage type

### Weapon Swapping Cost
**Question:** How much does weapon swapping cost?
- Option A: Free once per round (encourages tactical switching)
- Option B: Minor action (TBD if we track minor/major)
- Option C: Full action (discourages swapping)
- **Decision pending user input**

### Ammo Tracking
**Question:** Track ammo count or abstract?
- Option A: Full tracking (count shots, reloading)
- Option B: Abstract (unlimited ammo, just narrative flavor)
- **Decision pending user input**

### Non-Lethal Loadouts
Players can now build mercy-focused characters:
- **Enforcer (Non-Lethal):** Shock baton + stun gun + stun grenades
- **Enforcer (Lethal):** Pistol + rifle + frag grenades
- **Mixed:** Pistol (lethal backup) + shock baton (subdue)

### Morale System Design

**Triggers:**
1. HP < 25% of max
2. All allies defeated/retreated (last survivor)
3. Stunned to Critical (5+ stuns)
4. Leader defeated (if enemy has leadership structure)

**Check:** Willpower × d20 vs DC 20
- Success: Keep fighting
- Failure: Surrender or flee (based on enemy `personality` flag)

**Enemy Personality Types:**
- `fight_to_death` - Never surrenders (void cultists, fanatics)
- `flee_when_broken` - Runs when morale fails (gang members, thugs)
- `surrender_if_cornered` - Gives up if trapped (desperate criminals)

### Retreat/Escape Clock Alignment

**Current bug:** Enemy retreats → removed from combat, but "Escape Route" clock keeps ticking independently. Narrative confusion (did they escape? are they hiding?).

**Fix:** When enemy retreats:
1. Remove from combat (`is_active = False`)
2. Auto-advance "Escape Route" clock by +2 or +3
3. If clock fills → escaped successfully (enemy win condition)
4. If clock doesn't fill by mission end → partial escape (scattered, hiding)

**Semantics:**
- Retreat = enemy attempts to flee
- Clock advance = progress toward successful escape
- Clock filled = they got away clean
- Clock partial = they're still in the area, scattered

### Prisoner Interrogation

Surrendered enemies become prisoners:
- Track in `session.prisoners[]`
- Post-combat interrogation (during debrief phase)
- Intel rewards (advance investigation clocks, reveal faction secrets)
- Reputation impact (word spreads you take prisoners)
- Soulcredit bonus (mercy in justified combat)

**Execution of prisoners:** Huge soulcredit/void penalty (unless justified by enemy morality)

## Testing Plan

### Completed Tests ✅

**Test 1: Morale System & Retreat Mechanics** (Session 186bbfba-9914-4c1f-9164-6103a424ccb2)
- ✅ Freeborn Pirates spawned as grunts (2 units, tactical_ranged)
- ✅ One unit defeated in Round 1 combat
- ✅ Last survivor triggered morale check (last_survivor trigger)
- ✅ Morale check: Willpower 2 + d20(3) = 5 vs DC 20 → FAILURE
- ✅ Result: Enemy fled (personality: flee_when_broken)
- ✅ Escape Route clock advanced, enemy successfully escaped
- ✅ JSONL logging verified: morale_check and flee events logged correctly
- **Status**: Morale and retreat system working as designed

### Pending Tests
1. **Stun-only combat:** Player with shock baton vs gang members (test non-lethal weapons)
2. **Mixed loadout:** Pistol vs rifle, swap to stun gun for capture (test weapon swapping)
3. **Surrender scenario:** Enemy with surrender_if_cornered personality
4. **Social de-escalation:** Intimidate check mid-combat (Phase 5 feature)
5. **Ritual damage:** Astral Arts attack, verify wound damage application
6. **Soulcredit tracking:** Lethal vs non-lethal outcomes

## Open Questions

1. Weapon swapping cost (free / minor action / full action)?
2. Ammo tracking (full / abstract)?
3. Should players see enemy morale checks (transparent) or hidden (DM only)?
4. Ritual damage type - DM discretion or predefined per ritual?
