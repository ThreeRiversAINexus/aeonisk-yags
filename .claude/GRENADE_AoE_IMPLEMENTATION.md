# Grenade / AoE Implementation Requirements

**Status:** Not implemented (action disabled as of 2025-11-01)
**Priority:** Low - requires substantial mechanics work

## Overview

The `Throw_Grenade` enemy action has been **disabled** until proper Area-of-Effect (AoE) mechanics are implemented. Currently, enemies with grenade inventory cannot use them tactically.

## Why Disabled

Grenades require complex mechanics not yet implemented:
1. **AoE damage calculation** - Multiple combatants in blast zone
2. **Friendly fire detection** - Allied units taking damage
3. **Ring-side location targeting** - Positional system for blast centers
4. **Saving throw mechanics** - Agility saves vs DC for all affected
5. **DM narration integration** - Blast descriptions with multiple casualties

## Current Code References

**Removed from:**
- `scripts/aeonisk/multiagent/enemy_prompts.py:691` - MAJOR_ACTION list
- `scripts/aeonisk/multiagent/prompts/claude/en/enemy.yaml:99` - MAJOR_ACTION list
- Both files: Example declarations removed

**Commented code preserved at:**
- `scripts/aeonisk/multiagent/enemy_prompts.py:553-568` - Grenade ability formatting

## Expected Grenade Behavior

### Game Mechanics (when implemented)

**Targeting:**
- Enemy declares `MAJOR_ACTION: Throw_Grenade`
- `TARGET` is a ring-side location (e.g., "Near-Enemy", "Far-PC")
- All combatants in that ring segment are affected

**Damage Resolution:**
- Base damage: 2d6 (12 average)
- Each affected combatant rolls Agility save vs DC 20
- Success: Half damage
- Failure: Full damage
- **Friendly fire applies** - allies in blast zone take damage

**Tactical Considerations:**
- High-value targets: Groups of clustered enemies
- Risk assessment: Friendly fire acceptable if target value > allied casualties
- LLM decision-making: Enemy agents weigh risk/reward in `tactical_reasoning`

### Implementation Checklist

When implementing grenades, the following systems need work:

#### 1. Position/Zone System
- [ ] Define ring-side blast zones (which positions are "in blast")
- [ ] Calculate combatants in affected zone
- [ ] Validate enemy can throw to target position (range limits?)

#### 2. Damage Mechanics
- [ ] Multi-target damage resolution loop
- [ ] Agility save rolling for each affected combatant
- [ ] Damage halving on successful saves
- [ ] Apply damage to both PCs and enemies (friendly fire)

#### 3. DM Narration
- [ ] Generate blast description naming all affected combatants
- [ ] Describe hit/miss for each target based on saves
- [ ] Narrative friendly fire acknowledgment (tactical cost)

#### 4. Enemy AI Prompts
- [ ] Re-enable grenade examples in `enemy_prompts.py`
- [ ] Add ring-side targeting guidance
- [ ] Include friendly fire warnings in tactical reasoning
- [ ] Update structured output validation for grenade targets

#### 5. Logging/ML
- [ ] Log grenade usage in `action_declaration`
- [ ] Log multi-target damage in `action_resolution`
- [ ] Track friendly fire statistics (training data for tactical AI)

#### 6. Testing
- [ ] Unit test: Grenade damage calculation
- [ ] Unit test: Friendly fire detection
- [ ] Unit test: Zone/ring targeting
- [ ] Integration test: Enemy throws grenade with friendly fire
- [ ] Integration test: PC throws grenade (if PC grenades implemented)

## Example Grenade Declaration (Future)

```
DEFENCE_TOKEN: pc_sable_001
MAJOR_ACTION: Throw_Grenade
TARGET: Near-Enemy
WEAPON: Frag Grenade
MINOR_ACTION: Shift
TACTICAL_REASONING: Throwing grenade at Near-Enemy to hit Sable (primary threat) even though Grunt Squad 2 will take friendly fire - Sable's melee damage output justifies tactical sacrifice. Shifting away from blast zone to avoid self-damage.
SHARE_INTEL: Grenade incoming at Near-Enemy, allied units clear zone or brace for impact
```

## DM Narration Example (Future)

```
The enemy grunt pulls a fragmentation grenade, primes it with practiced efficiency,
and hurls it toward the Near-Enemy zone where Sable stands. The grenade arcs through
the air and detonates in a flash of shrapnel.

BLAST ZONE: Near-Enemy
- Sable (Agility save: 12 vs DC 20 - FAIL) takes 11 damage
- Grunt Squad 2 (Agility save: 18 vs DC 20 - FAIL) takes 9 damage (friendly fire)

The grunt squad staggers from their own grenade's blast, a calculated sacrifice to
neutralize the greater threat.
```

## Notes

- **Do not re-enable** `Throw_Grenade` until AoE mechanics are fully implemented
- Current grenade inventory on enemies is cosmetic only
- JSONL fixture files still contain old grenade examples (historical data)
- Consider implementing PC grenades at same time (shared mechanics)

## Related Systems

- **Suppression** - Already implemented, simpler (single-target status effect)
- **Void Surge** - Already implemented, single-target damage modifier
- **Charge** - Already implemented, movement + attack combo

Grenades are substantially more complex than existing special abilities due to multi-target nature.
