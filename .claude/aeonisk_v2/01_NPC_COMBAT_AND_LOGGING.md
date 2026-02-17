# P0: NPC Combat & Logging Bug Fixes

**Priority:** P0 (data integrity + mechanical correctness)
**Branch:** `intention-lethality-mismatch`
**Evidence:** Baseline datamining, 25 sessions x 5 models (GPT-5.2, Grok 4, Gemini 2.5 Pro, DeepSeek V3.2, Claude Opus 4.6)
**Analysis docs:** `.claude/baseline_datamining/enemy_npc_analysis.md`, `.claude/baseline_datamining/research_observations.md`

---

## Problem Statement

Three related bugs were surfaced during baseline datamining of 25 combat ambush sessions across 5 LLM models. Together they corrupt NPC-related training data (double-counted events, zero-damage attacks) and allow impossible game states (0 HP + conscious).

### Bug 1: NPC Action Double-Logging

Every NPC action produces two `action_resolution` JSONL events instead of one. The first is logged under phase `adjudicate_npc` with `is_npc: true` context (correct). The second is logged under phase `adjudicate` without any NPC marker (incorrect duplicate). This inflates NPC action counts in all downstream ML analysis and makes event deduplication a manual step.

**Impact:** All 155 NPC action events across 25 sessions are doubled. Analysis required manual deduplication by checking `is_npc` flag.

### Bug 2: NPC Attacks Deal 0 Damage

All 18 NPC attack declarations across 25 sessions (Grok: 7, DeepSeek: 6, Gemini: 3, Claude: 2) resolved with 0 damage dealt. No `combat_action` events are logged with an NPC as attacker. NPC healing works correctly (264 HP healed across 6 applications in Grok run_0017), but NPC combat is non-functional.

**Impact:** NPCs converted from enemies via `deescalate_enemy_to_npc()` lose all combat effectiveness despite preserving full stats (skills, weapons, health, soak). A Pantheon Security officer with Guns=3, Melee=3, and a Pistol deals exactly the same 0 damage as an unarmed civilian.

### Bug 3: 0 HP + Conscious Edge Cases

Several sessions ended with PCs at 0 HP but `death_state: "alive"` in `character_state` logs (Grok runs 0007/0022, DeepSeek runs 0005/0020). YAGS rules specify: 0 HP with wounds < 6 should trigger death saves, and the character should be either unconscious, critically conscious (good success on death save), or dead -- never simply "alive" at 0 HP.

**Impact:** Impossible game states in training data. ML models trained on this data learn that 0 HP is a valid conscious state.

---

## Current Implementation

### Bug 1: Double-Logging Flow

The adjudication pipeline processes actions through two stages:

1. `_handle_adjudication_inner()` (dm.py:2846) iterates over all actions and calls `_resolve_action_mechanically()` for each.
2. `_resolve_action_mechanically()` (dm.py:4689) checks `action.get('is_npc')` at line 4722. For NPC actions, it runs the full NPC adjudication path (narration, healing, attack) and logs to JSONL at line 5109-5119 with `phase="adjudicate_npc"`.
3. After `_resolve_action_mechanically()` returns, `_handle_adjudication_inner()` unconditionally logs the same resolution again at lines 2884-3036 with `phase="adjudicate"`.

The NPC path returns a resolution dict containing a valid `action_resolution` object (line 5122-5139). Back in `_handle_adjudication_inner()`, the conditional at line 2892 (`if action_resolution:`) is true, so the generic logging block fires a second time.

```
_handle_adjudication_inner()
  for action_entry in actions:
    resolution = await _resolve_action_mechanically(action)
      if action.get('is_npc'):           # NPC path
        ...
        jsonl_logger.log_action_resolution(   # LOG 1: phase="adjudicate_npc", is_npc=True
          phase="adjudicate_npc", ...)
        return {resolution, narration, ...}

    # Back in _handle_adjudication_inner:
    if action_resolution:                     # Always true for NPCs
      jsonl_logger.log_action_resolution(     # LOG 2: phase="adjudicate", no is_npc flag
        phase="adjudicate", ...)
```

### Bug 2: NPC Attack Combat Math

The NPC attack path (dm.py:4942-5058) uses a simplified combat calculation with hardcoded attribute values:

```python
# dm.py lines 4994-5023 (current NPC attack path)
if weapon.skill == "Guns":
    attr_value = 3  # Default NPC Perception
elif weapon.skill == "Melee":
    attr_value = 3  # Default NPC Dexterity
else:  # Brawl
    attr_value = 3  # Default NPC Agility

combat_skill = npc_entity.skills.get(weapon.skill, 0)
unskilled_penalty = -5 if combat_skill == 0 else 0
skill_value = max(combat_skill, 1)
base_attack = attr_value * skill_value + weapon.attack + unskilled_penalty
# ...
strength = 3  # Default NPC Strength
damage_d20 = random.randint(1, 20)
base_damage = strength + weapon.damage + damage_d20
total_damage = int(base_damage * 0.85)  # CBM reduction
target_soak = getattr(target_entity, 'soak', 0)
damage_dealt = max(0, total_damage - target_soak)
```

The problem is twofold:

1. **Skills default to 0:** NPCAgent preserves `skills` from enemy conversion (e.g., `{"Guns": 3, "Melee": 3}`) but the lookup `npc_entity.skills.get(weapon.skill, 0)` returns 0 when the NPC entity lookup fails (npc_entity is None) or when the skill key does not match the weapon skill name exactly.

2. **No damage logging:** Unlike `enemy_combat.py:_execute_attack()` which calls `mechanics_engine.jsonl_logger.log_combat_action()` (line 1216), the NPC attack path never logs a `combat_action` event. It only creates `DamageEffect` objects for the `action_resolution` event.

3. **Hardcoded attribute=3 and strength=3:** Enemy agents have actual attribute dicts (e.g., `{"Perception": 4, "Strength": 4, "Dexterity": 3}`). NPCAgent does NOT have an `attributes` field at all -- only `skills`. The hardcoded values are always 3 regardless of the original enemy's actual stats.

4. **No death save / defeat tracking:** The NPC attack path applies damage (lines 5028-5038) but never checks `check_death_save()` or calls `resolution_state.mark_defeated()`. If an NPC kills a target, the target remains "active" in the combat system.

Meanwhile, `enemy_combat.py:_execute_attack()` (lines 919-1228) implements the full YAGS formula correctly:

```python
# enemy_combat.py lines 1025-1036 (enemy attack path - correct)
if weapon.skill == "Guns":
    attribute = enemy.attributes.get('Perception', 3)
elif weapon.skill == "Melee":
    attribute = enemy.attributes.get('Dexterity', 3)
else:  # Brawl
    attribute = enemy.attributes.get('Agility', 3)

skill = enemy.skills.get(weapon.skill, 2)  # Default 2, not 0
attack_roll = random.randint(1, 20)
attack_total = (attribute * skill) + weapon.attack + attack_roll + range_penalty
```

Key differences:
- Uses actual `enemy.attributes` dict (not hardcoded 3)
- Default skill is 2 (not 0) -- enemies always have some training
- Includes `range_penalty` from position calculation
- Includes defence token modifier (+2 flanking / -2 watched)
- Full death save + defeat tracking
- Full `combat_action` JSONL logging with attack roll, damage roll, and defender state

### Bug 3: 0 HP + Conscious Death State

The `character_state` snapshot is logged in `session.py` (lines 3056-3105) at the end of each round:

```python
# session.py lines 3062-3070
wounds = player.wounds if hasattr(player, 'wounds') else 0
health = player.health if hasattr(player, 'health') else 0
if wounds >= 6:
    death_state = "dead"
elif health <= 0:
    death_state = "unconscious"
else:
    death_state = "alive"
```

This logic is correct in isolation. The possible failure modes are:

1. **Damage applied after state snapshot:** If damage is applied during round synthesis (after the character_state log), the snapshot shows pre-damage HP. Next round's snapshot would show the correct 0 HP state, but if the session ends this round, only the pre-damage snapshot exists.

2. **HP reduced without wound increment:** YAGS wound damage formula is `wounds_dealt = damage_dealt // 5` (every 5 points = 1 wound). So 4 damage reduces HP by 4 but adds 0 wounds. With `wounds=0` and `health=0`, the character should be "unconscious" by the code above. But the `check_death_save()` method (player.py:545-593) only triggers at `wounds >= 5`. A character at 0 HP with 0-4 wounds gets `health <= 0` -> `death_state = "unconscious"` in the snapshot, which is correct.

3. **Stun damage does not reduce HP:** `apply_stun_damage()` only modifies `target.stuns`, not `target.health`. A character beaten by stuns has full HP but is unconscious. The snapshot checks `health <= 0` which is False, then returns "alive". This is a legitimate bug path: stun KO results in `death_state: "alive"` instead of "unconscious".

4. **Death save returns "conscious":** `check_death_save()` can return `(True, "conscious")` when the roll exceeds DC by 10+. This is a valid YAGS outcome ("good success -- can keep fighting"). The character is at 0 HP, wounds >= 5, but status "conscious". The session.py snapshot logic does not call `check_death_save()` -- it uses the simple `health <= 0` check. So a character who was "conscious" after a death save would show `death_state: "unconscious"` in the snapshot (because health <= 0). This is actually incorrect in the other direction -- the character passed a death save to stay conscious but the snapshot says unconscious.

5. **Race condition in HP tracking:** Player has `health` attribute on the agent object. Damage is applied by `apply_wound_damage()` which sets `target.health = max(0, target.health - damage_dealt)`. If the snapshot reads `player.health` before the damage function completes in another coroutine, it could see stale HP. However, Python's GIL and the await-based coroutine model make this unlikely within a single round's processing.

The most likely root cause for the observed "0 HP + alive" state is **stun damage path** (#3) or **snapshot timing** (#1). Deep investigation is needed with specific session JSONL analysis.

---

## Design Decisions

### D1: Route NPC attacks through enemy_combat.py:_execute_attack()

**Decision:** Create an adapter that wraps NPCAgent to be compatible with `_execute_attack()`, rather than duplicating the combat formula in dm.py.

**Rationale:**
- Single source of truth for YAGS combat math (attribute x skill + weapon + d20 + modifiers)
- Enemy agents were already balanced (Melee skill 1->3, +3 weapon damage in commit 585bcce). NPCs will automatically benefit from any future balance changes.
- `_execute_attack()` already handles: target resolution, faction validation, range penalties, defence tokens, death saves, defeat tracking, and JSONL combat_action logging.
- NPCAgent preserves all required stats from enemy conversion: skills, weapons, health, soak, position, stuns, wounds, conditions.

**What the adapter needs to bridge:**
- NPCAgent has `skills: Dict[str, int]` but no `attributes: Dict[str, int]`. The adapter must synthesize attributes from skills or use defaults.
- NPCAgent has no `initiative: int` field. The adapter can use 0 or derive from Agility.
- NPCAgent has no `template: str`. The adapter can use `original_enemy_template` or "npc".
- NPCAgent has no `tactics`, `threat_priority`, `retreat_threshold`, `morale_behavior`, `character_brief`. These are behavioral fields used only for LLM prompting, not combat math.
- `_execute_attack()` expects `EnemyDeclaration` for the declaration parameter. The adapter must construct one from NPC action data.

**Stats required by _execute_attack():**
- `enemy.agent_id` -- NPCAgent has this (stable across conversion)
- `enemy.name` -- NPCAgent has this
- `enemy.faction` -- NPCAgent has this
- `enemy.attributes` -- NPCAgent MISSING. Must synthesize.
- `enemy.skills` -- NPCAgent has this
- `enemy.weapons` -- NPCAgent has this
- `enemy.position` -- NPCAgent has this
- `enemy.health`, `max_health`, `soak`, `wounds`, `stuns` -- NPCAgent has all of these
- `enemy.is_active` -- NPCAgent has this

### D2: Synthesize NPC attributes using agent_conversion.py pattern

`agent_conversion.py:escalate_npc_to_enemy()` already has an `estimate_attributes()` function (lines 217-240) that derives YAGS attributes from NPC skills:

```python
def estimate_attributes(skills: Dict[str, int]) -> Dict[str, int]:
    agility = max(skills.get('Athletics', 0) // 2 + 2, skills.get('Guns', 0) // 2 + 2, 3)
    strength = max(skills.get('Brawl', 0) // 2 + 2, skills.get('Melee', 0) // 2 + 2, 3)
    return {
        'Agility': min(agility, 5),
        'Strength': min(strength, 5),
        'Perception': skills.get('Awareness', 0) // 2 + 2,
        'Intelligence': 3,
        'Empathy': 2,
        'Willpower': 3,
        'Size': 5
    }
```

**Decision:** Extract this into a shared utility (or keep using it from agent_conversion) rather than hardcoding `attr_value = 3` everywhere. This gives NPCs with Guns=3 a Perception of 3 (default) and Strength of 3+, rather than the broken all-3 hardcode.

**Alternative considered:** Add `attributes` field to NPCAgent. Rejected because:
- NPCAgent is designed as a lightweight agent -- adding attributes increases constructor complexity
- agent_conversion already handles attribute synthesis for escalation
- The adapter pattern keeps NPC and Enemy concerns separated

### D3: Skip generic log for NPC actions

**Decision:** In `_handle_adjudication_inner()`, check `action.get('is_npc')` before the generic logging block. If true, skip it entirely -- the NPC path already logged with better context (is_npc flag, heal roll data, etc.).

**Alternative considered:** Remove logging from the NPC path in `_resolve_action_mechanically()` and let the generic path handle it. Rejected because:
- The NPC path adds NPC-specific context fields (is_npc, heal_target, heal_amount, npc_roll) that the generic path does not know about.
- The NPC phase name `adjudicate_npc` is more descriptive for ML filtering.

### D4: Add stun KO tracking to death_state determination

**Decision:** Extend the death_state logic in session.py to check stun-based unconsciousness:

```python
if wounds >= 6:
    death_state = "dead"
elif health <= 0:
    death_state = "unconscious"
elif stuns >= 6:          # NEW: Stun KO
    death_state = "unconscious"
else:
    death_state = "alive"
```

This matches the YAGS rule (combat.md:437-456): stuns >= 6 = "Beaten" = unconscious check needed.

### D5: Deep investigation for snapshot timing (Bug 3)

**Decision:** Write targeted test cases that reproduce the 0 HP + conscious edge cases, then trace the exact failure mode. Do not speculatively change snapshot timing without evidence. The stun KO fix (D4) is the most likely root cause and should be implemented first. If 0 HP + alive states still appear in new sessions, investigate snapshot timing with real session JSONL analysis.

---

## Proposed Solution

### Fix 1: NPC Action Double-Logging Gate

**File:** `dm.py`
**Location:** `_handle_adjudication_inner()`, lines 2883-3036

Add an early-continue guard that skips the generic logging block when the action is an NPC action (already logged by the NPC path).

```python
# dm.py: _handle_adjudication_inner(), after resolution = await _resolve_action_mechanically(...)

# Print the resolution
print(f"\n{resolution['narration']}")
print("=" * 40)

# Log the resolution -- SKIP for NPC actions (already logged in adjudicate_npc phase)
if action.get('is_npc'):
    # NPC actions are fully logged inside _resolve_action_mechanically()
    # with phase="adjudicate_npc" and NPC-specific context (is_npc, heal data, etc.)
    # Skip generic logging to prevent double-counting in JSONL.
    resolutions.append({
        'player_id': player_id,
        'character_name': character_name,
        'initiative': initiative,
        'action': action,
        'resolution': resolution,
        'state_changes': {}
    })
    continue  # Skip to next action -- no generic logging for NPCs

if mechanics and mechanics.jsonl_logger:
    # ... existing generic logging block (unchanged) ...
```

**Why `continue` instead of an `if not is_npc` wrapper:** The existing logging block is 150+ lines of deeply nested code. Wrapping it in another conditional would increase indentation and reduce readability. A `continue` at the top is clearer: "NPC actions are done, move on."

### Fix 2: NPC Attack via enemy_combat.py Adapter

**File:** `enemy_combat.py` -- new public method
**File:** `dm.py` -- replace NPC attack block

#### Step 2a: Create NPC-to-EnemyAgent combat adapter

Add a new function to `enemy_combat.py` (or a new `npc_combat_adapter.py`) that wraps NPCAgent for combat:

```python
# enemy_combat.py (or npc_combat_adapter.py)

def execute_npc_attack(
    npc: 'NPCAgent',
    target_id: str,
    weapon_name: Optional[str],
    shared_state: 'SharedState',
    mechanics_engine: Any,
    resolution_state: 'ResolutionState',
    player_agents: List[Any]
) -> Dict[str, Any]:
    """
    Execute NPC attack using the full YAGS combat formula from _execute_attack().

    Creates a lightweight adapter that wraps NPCAgent with the fields
    _execute_attack() expects, then delegates to the enemy combat path.

    Args:
        npc: NPCAgent with preserved combat stats (skills, weapons, health, soak)
        target_id: Target identifier (tgt_xxxx or agent_id)
        weapon_name: Weapon to use (or None for first available)
        shared_state: Session shared state (for target resolution)
        mechanics_engine: Mechanics engine (for JSONL logging)
        resolution_state: Tactical resolution state (for defeat tracking)
        player_agents: List of player agents (for target resolution)

    Returns:
        Combat result dict matching _execute_attack() output format:
        {enemy_id, character_name, action, target, weapon, hit, attack_roll,
         damage, damage_dealt, narration, target_defeated, ...}
    """
    from .agent_conversion import estimate_attributes  # Reuse existing logic

    # Synthesize attributes from NPC skills
    attributes = estimate_attributes(npc.skills)

    # Build minimal EnemyAgent-compatible wrapper
    # Only the fields _execute_attack() actually reads
    class NPCCombatProxy:
        """Lightweight proxy that makes NPCAgent look like EnemyAgent for combat."""
        def __init__(self, npc_agent, attrs):
            self.agent_id = npc_agent.agent_id
            self.name = npc_agent.name
            self.faction = npc_agent.faction
            self.attributes = attrs
            self.skills = npc_agent.skills
            self.weapons = npc_agent.weapons
            self.position = npc_agent.position
            self.health = npc_agent.health
            self.max_health = npc_agent.max_health
            self.soak = npc_agent.soak
            self.wounds = npc_agent.wounds
            self.stuns = npc_agent.stuns
            self.is_active = npc_agent.is_active
            # Not used in combat math, but _execute_attack accesses these:
            self.defence_token = None
            self.tactical_token = None

    proxy = NPCCombatProxy(npc, attributes)

    # Build EnemyDeclaration from NPC action
    declaration = EnemyDeclaration(
        agent_id=npc.agent_id,
        character_name=npc.name,
        initiative=0,  # NPCs don't roll initiative
        defence_token=None,
        major_action="Attack",
        target=target_id,
        weapon=weapon_name,
        minor_action=None,
        token_target=None,
        reasoning="NPC attack action",
        shared_intel=None
    )

    # Delegate to the full YAGS combat path
    # _execute_attack is a method on EnemyCombatManager -- we need the instance
    combat_manager = None
    if shared_state and hasattr(shared_state, 'session') and shared_state.session:
        combat_manager = getattr(shared_state.session, 'enemy_combat', None)

    if combat_manager:
        result = combat_manager._execute_attack(
            enemy=proxy,
            declaration=declaration,
            player_agents=player_agents,
            mechanics_engine=mechanics_engine,
            resolution_state=resolution_state
        )
    else:
        # Fallback: no combat manager available
        result = {
            'enemy_id': npc.agent_id,
            'character_name': npc.name,
            'action': 'attack',
            'result': 'no combat system',
            'narration': f"{npc.name} attempts to attack but the combat system is unavailable."
        }

    # Note: _execute_attack modifies the TARGET (damage, defeat), not the attacker.
    # No need to sync state back to NPCAgent.

    return result
```

#### Step 2b: Extract estimate_attributes to shared location

Move `estimate_attributes()` from inside `escalate_npc_to_enemy()` to module level in `agent_conversion.py` so it can be imported:

```python
# agent_conversion.py -- move to module level (currently nested inside escalate_npc_to_enemy)

def estimate_attributes(skills: Dict[str, int]) -> Dict[str, int]:
    """
    Estimate YAGS attributes from NPC skills.

    Used when converting NPC -> Enemy (escalation) and for NPC combat calculations.
    NPCs only store skills, not attributes. This function derives reasonable
    attribute values from skill levels.

    Args:
        skills: NPC's skill dict (e.g., {"Guns": 3, "Melee": 2, "Medicine": 1})

    Returns:
        Dict of YAGS attributes with estimated values (3 = average human default)
    """
    agility = max(
        skills.get('Athletics', 0) // 2 + 2,
        skills.get('Guns', 0) // 2 + 2,
        3
    )
    strength = max(
        skills.get('Brawl', 0) // 2 + 2,
        skills.get('Melee', 0) // 2 + 2,
        3
    )
    perception = max(skills.get('Awareness', 0) // 2 + 2, 3)
    dexterity = max(skills.get('Melee', 0) // 2 + 2, 3)
    return {
        'Agility': min(agility, 5),
        'Strength': min(strength, 5),
        'Perception': min(perception, 5),
        'Dexterity': min(dexterity, 5),
        'Intelligence': 3,
        'Empathy': 2,
        'Willpower': 3,
        'Endurance': 3,
    }
```

Note: The current `estimate_attributes` is missing `Dexterity` (used by Melee combat) and `Endurance` (YAGS standard). The extracted version adds these. Also caps Perception at 5 (was uncapped).

#### Step 2c: Replace NPC attack block in dm.py

Replace the 100-line NPC attack block (dm.py:4942-5058) with a call to the adapter:

```python
# dm.py: inside _resolve_action_mechanically(), NPC attack handler
elif npc_action_type == 'attack' and target:
    # Route NPC attacks through enemy_combat.py's full YAGS combat path
    # This gives NPCs: proper attribute*skill formula, range penalties,
    # defence tokens, death saves, defeat tracking, and combat_action JSONL logging.
    from .enemy_combat import execute_npc_attack
    from .tactical_resolution import ResolutionState

    # Get or create resolution state for this round
    resolution_state = getattr(self, '_current_resolution_state', None)
    if not resolution_state:
        resolution_state = ResolutionState()

    player_agents = getattr(self.shared_state, 'player_agents', [])

    combat_result = execute_npc_attack(
        npc=npc_entity,
        target_id=target,
        weapon_name=None,  # Use first available weapon
        shared_state=self.shared_state,
        mechanics_engine=self.shared_state.mechanics_engine if self.shared_state else None,
        resolution_state=resolution_state,
        player_agents=player_agents
    )

    # Map combat result to NPC resolution format
    hit = combat_result.get('hit', False)
    damage_dealt = combat_result.get('damage_dealt', 0)
    target_name = combat_result.get('target', 'unknown')

    if hit and damage_dealt > 0:
        success_tier = SuccessTier.MODERATE
        margin = combat_result.get('attack_roll', 0) - 15
        narration += f"\n\n{combat_result.get('narration', '')}"
    elif hit:
        success_tier = SuccessTier.MARGINAL
        margin = 0
        narration += f"\n\n{combat_result.get('narration', '')}"
    else:
        success_tier = SuccessTier.FAILURE
        margin = -5
        narration += f"\n\n{combat_result.get('narration', '')}"

    # combat_action JSONL logging is handled inside _execute_attack()
    # -- no need to duplicate here
```

### Fix 3: Death State Stun KO + Investigation

**File:** `session.py`
**Location:** Character state snapshot logging, lines 3062-3070

#### Step 3a: Add stun KO check

```python
# session.py: character_state snapshot (lines 3062-3070)
wounds = player.wounds if hasattr(player, 'wounds') else 0
health = player.health if hasattr(player, 'health') else 0
stuns = player.stuns if hasattr(player, 'stuns') else 0

if wounds >= 6:
    death_state = "dead"
elif health <= 0:
    death_state = "unconscious"
elif stuns >= 6:
    death_state = "unconscious"  # Stun KO: Beaten threshold per YAGS
else:
    death_state = "alive"
```

Apply the same fix to the enemy state snapshot (lines 3123-3130):

```python
# session.py: enemy character_state snapshot (lines 3123-3130)
enemy_wounds = enemy.wounds if hasattr(enemy, 'wounds') else 0
enemy_health = enemy.health if hasattr(enemy, 'health') else 0
enemy_stuns = enemy.stuns if hasattr(enemy, 'stuns') else 0

if enemy_wounds >= 6:
    enemy_death_state = "dead"
elif enemy_health <= 0:
    enemy_death_state = "unconscious"
elif enemy_stuns >= 6:
    enemy_death_state = "unconscious"  # Stun KO
else:
    enemy_death_state = "alive"
```

#### Step 3b: Investigate snapshot timing

After implementing 3a, if "0 HP + alive" states still appear in new sessions, investigate:

1. Whether round synthesis applies damage after the character_state snapshot
2. Whether `apply_wound_damage()` health reduction and the snapshot are in different async phases
3. Whether stun damage from DM narration (structured output `damage_effects`) applies correctly

This investigation requires running new sessions and analyzing the JSONL output, not code changes. The test plan below includes tests that verify the deterministic path.

---

## Files to Modify

### Primary Changes

| File | Change | Lines |
|------|--------|-------|
| `dm.py` | Add `is_npc` guard in `_handle_adjudication_inner()` to skip generic logging | ~2883 |
| `dm.py` | Replace NPC attack block with `execute_npc_attack()` call | ~4942-5058 |
| `enemy_combat.py` | Add `execute_npc_attack()` public function | new, after line ~1228 |
| `agent_conversion.py` | Extract `estimate_attributes()` to module level | ~217-240 |
| `session.py` | Add stun KO check to player death_state logic | ~3062-3070 |
| `session.py` | Add stun KO check to enemy death_state logic | ~3123-3130 |

### Test Files (New)

| File | Purpose |
|------|---------|
| `tests/unit/test_npc_combat_logging.py` | Tests for Bugs 1, 2, and 3 |

### Files Referenced (No Changes)

| File | Role |
|------|------|
| `npc_agent.py` | NPCAgent dataclass -- already has all required fields |
| `mechanics.py` | `apply_stun_damage`, `apply_wound_damage`, `get_wound_effect`, `get_stun_effect` |
| `player.py` | `check_death_save()` implementation |
| `tactical_resolution.py` | `ResolutionState`, `ActionValidator` |

---

## Test Plan (TDD)

Write all tests FIRST, verify they fail (red), then implement fixes (green).

### Test File: `tests/unit/test_npc_combat_logging.py`

### Bug 1 Tests: NPC Single-Logging

```python
class TestNPCSingleLog:
    """Verify NPC actions produce exactly 1 JSONL log event, not 2."""

    def test_npc_action_logged_once(self):
        """
        Mock NPC action through _handle_adjudication_inner().
        Verify log_action_resolution is called exactly once.

        Setup:
        - Create action_entry with action['is_npc'] = True
        - Mock _resolve_action_mechanically to return NPC resolution dict
        - Mock mechanics.jsonl_logger.log_action_resolution
        - Call _handle_adjudication_inner()

        Assert:
        - log_action_resolution called exactly 1 time (not 2)
        - The single call has phase="adjudicate_npc"
        - The single call has is_npc=True in context
        """

    def test_player_action_still_logged(self):
        """
        Verify that player actions (is_npc=False) still produce log events
        through the generic path (regression guard).

        Setup:
        - Create action_entry WITHOUT is_npc flag
        - Mock _resolve_action_mechanically to return player resolution dict

        Assert:
        - log_action_resolution called at least once
        - Call has phase="adjudicate"
        """

    def test_mixed_npc_and_player_actions(self):
        """
        When a round has both NPC and player actions, verify:
        - NPC action: 1 log event (phase="adjudicate_npc")
        - Player action: 1 log event (phase="adjudicate")
        - Total: 2 events (not 3)
        """
```

### Bug 2 Tests: NPC Attack Damage

```python
class TestNPCAttackDealsDamage:
    """Verify NPC attacks use full YAGS formula and deal nonzero damage."""

    def test_npc_attack_deals_damage(self):
        """
        Create NPC with Melee=3, combat_knife (damage=5), Strength-derived=3.
        Seed random so attack hits (high d20).
        Verify damage_dealt > 0 against target with soak=4.

        Attack: Dexterity(3) * Melee(3) + knife.attack(3) + d20(15) = 27 vs DC 15 -> hit
        Damage: Strength(3) + knife.damage(5) + d20(10) = 18, * 0.85 = 15
        After soak(4): 11 damage dealt

        Assert: damage_dealt == 11 (or close, depending on CBM rounding)
        """

    def test_npc_attack_uses_yags_formula(self):
        """
        Verify NPC attack uses attribute*skill + weapon.attack + d20 + range_penalty
        (not the broken hardcoded path).

        Create NPC with Guns=4 (-> Perception estimate = 4).
        Verify attack_total = 4*4 + weapon.attack + d20, not 3*1 + weapon.attack + d20 - 5.
        """

    def test_npc_preserved_stats_used(self):
        """
        Convert EnemyAgent to NPCAgent via deescalate_enemy_to_npc().
        Then execute NPC attack.
        Verify the attack uses the preserved skills and weapons, not defaults.

        Setup:
        - Create EnemyAgent with Guns=4, Perception=4, weapons=[assault_rifle]
        - Convert to NPC via deescalate_enemy_to_npc()
        - Execute attack via execute_npc_attack()

        Assert:
        - NPC has skills["Guns"] == 4
        - NPC has weapons[0].name == "Assault Rifle"
        - Attack calculation uses skill=4 (not 0 or 1)
        """

    def test_npc_attack_logs_combat_action(self):
        """
        Verify NPC attack produces a combat_action JSONL event
        (via _execute_attack's logging), not just an action_resolution event.

        Mock mechanics_engine.jsonl_logger.log_combat_action.
        Execute NPC attack.
        Assert log_combat_action called once with correct attacker_id.
        """

    def test_npc_attack_no_weapon_fails_gracefully(self):
        """
        NPC with empty weapons list should get a failure result,
        not crash or deal damage.
        """

    def test_npc_attack_handles_target_defeat(self):
        """
        NPC attack that kills target should mark target as defeated
        via resolution_state.mark_defeated().

        Setup:
        - Create target with health=1, soak=0
        - Seed random for guaranteed hit + high damage

        Assert:
        - result['target_defeated'] == True
        - resolution_state.mark_defeated() called with target_id
        """

    def test_estimate_attributes_from_skills(self):
        """
        Verify estimate_attributes() produces reasonable values.

        Input: {"Guns": 4, "Melee": 3, "Awareness": 2, "Athletics": 1}
        Expected:
        - Perception >= 3 (from Awareness=2: 2//2+2 = 3)
        - Dexterity >= 3 (from Melee=3: 3//2+2 = 3)
        - Strength >= 3 (from Melee=3: 3//2+2 = 3)
        - Agility >= 3 (from Guns=4: 4//2+2 = 4)
        - All values <= 5 (human cap)
        """

    def test_estimate_attributes_empty_skills(self):
        """
        NPC with empty skills={} should get all-default attributes (3).
        """
```

### Bug 3 Tests: Death State Determination

```python
class TestDeathStateDetermination:
    """Verify correct death_state assignment in character_state snapshots."""

    def test_zero_hp_is_unconscious(self):
        """
        Player with health=0, wounds<6, stuns<6 should be death_state="unconscious".

        Setup: Mock player with health=0, wounds=3, stuns=0
        Assert: death_state == "unconscious"
        """

    def test_fatal_wounds_is_dead(self):
        """
        Player with wounds>=6 should be death_state="dead" regardless of HP.

        Setup: Mock player with health=10, wounds=7
        Assert: death_state == "dead"
        """

    def test_stun_ko_is_unconscious(self):
        """
        Player with stuns>=6 (Beaten threshold) should be death_state="unconscious"
        even if health > 0 and wounds < 6.

        Setup: Mock player with health=20, wounds=0, stuns=7
        Assert: death_state == "unconscious"

        This is the primary Bug 3 fix: stun KO was previously reported as "alive".
        """

    def test_healthy_is_alive(self):
        """
        Player with health>0, wounds<6, stuns<6 should be death_state="alive".
        Regression guard for normal case.
        """

    def test_damage_without_wound_increment(self):
        """
        Apply 4 wound damage (< 5 threshold). Verify:
        - HP reduced by 4
        - wounds unchanged (4 // 5 = 0)
        - death_state depends on remaining HP

        This tests the edge case where HP reaches 0 without any wounds,
        which should still result in "unconscious".
        """

    def test_stun_damage_does_not_reduce_hp(self):
        """
        Verify apply_stun_damage() does NOT modify target.health.
        This confirms that stun KO can only be detected via stuns >= 6,
        not via health <= 0.
        """

    def test_state_snapshot_reflects_post_damage_hp(self):
        """
        Apply damage to player, then check that the death_state logic
        uses the post-damage HP value (not a stale pre-damage value).

        Setup:
        - Create player with health=5, wounds=0
        - Apply 5 wound damage (health -> 0, wounds -> 1)
        - Run death_state determination logic

        Assert: death_state == "unconscious" (health is now 0)
        """

    def test_enemy_stun_ko_is_unconscious(self):
        """
        Same as test_stun_ko_is_unconscious but for enemy agents.
        Verify the fix is applied to both player and enemy snapshot paths.
        """
```

### Test Execution Order

```bash
# 1. Write tests (all should FAIL initially)
python -m pytest tests/unit/test_npc_combat_logging.py -v

# 2. Implement Fix 1 (double-logging gate)
python -m pytest tests/unit/test_npc_combat_logging.py::TestNPCSingleLog -v

# 3. Implement Fix 2 (NPC attack adapter)
python -m pytest tests/unit/test_npc_combat_logging.py::TestNPCAttackDealsDamage -v

# 4. Implement Fix 3 (death state)
python -m pytest tests/unit/test_npc_combat_logging.py::TestDeathStateDetermination -v

# 5. Run existing NPC tests (regression)
python -m pytest tests/unit/test_npc_attack.py tests/unit/test_npc_agent.py tests/unit/test_npc_healing.py -v

# 6. Run full agent conversion tests (regression)
python -m pytest tests/unit/test_agent_conversion.py -v

# 7. Run DM module routing tests (regression)
python -m pytest tests/unit/test_dm_module_routing.py -v
```

---

## Dependencies

### Internal Dependencies

- **agent_conversion.py** must export `estimate_attributes()` at module level (currently nested)
- **enemy_combat.py:EnemyCombatManager._execute_attack()** must be accessible. Currently it is an instance method. The adapter either needs the EnemyCombatManager instance (via `shared_state.session.enemy_combat`) or `_execute_attack()` must be refactored to accept the manager as a parameter. The proposed solution uses the instance via shared_state.
- **tactical_resolution.py:ResolutionState** must be available for NPC attack defeat tracking. The DM may not have a resolution_state for NPC actions -- need to create one or pass through from the round's state.

### External Dependencies

None. All changes are internal to the multiagent system.

### Backward Compatibility

- JSONL schema is unchanged. Events that previously had duplicate entries will now have single entries. Downstream analysis scripts that filtered by `is_npc` will still work (the single remaining event has `is_npc: true`). Scripts that counted raw `action_resolution` events will see corrected (lower) counts.
- `character_state` events gain correct `death_state` values. No schema change, but some entries that were `"alive"` will now correctly be `"unconscious"`. Downstream analysis that filters on death_state will see more accurate results.
- NPC attacks that previously dealt 0 damage will now deal mechanical damage. This changes combat dynamics -- NPCs converted from enemies become meaningful combatants. This is the intended behavior.

---

## Open Questions

### Q1: Should `execute_npc_attack()` be a free function or a method on EnemyCombatManager?

**Current proposal:** Free function in `enemy_combat.py` that accesses `_execute_attack()` via the EnemyCombatManager instance from shared_state.

**Alternative:** Make it a method on EnemyCombatManager. Pro: cleaner access to `_execute_attack()` (self method). Con: couples NPC combat to the enemy combat manager's lifecycle.

**Recommendation:** Free function. NPCs can attack even when enemy_combat module is disabled (e.g., NPC-only scenario with no enemies). The function should gracefully handle the case where EnemyCombatManager is not available.

### Q2: Should NPCAgent gain an `attributes` field?

**Current proposal:** No. Use `estimate_attributes()` on-the-fly when NPC attacks.

**Alternative:** Add `attributes: Dict[str, int] = field(default_factory=dict)` to NPCAgent dataclass. Populate during `deescalate_enemy_to_npc()` from enemy's actual attributes (which are known at conversion time).

**Trade-off:** Adding attributes to NPCAgent is simpler and preserves the original enemy's exact stats. But it adds constructor complexity and changes the NPCAgent contract. The adapter approach keeps NPCAgent lightweight.

**Decision needed before implementation.** If the team prefers attributes on NPCAgent, the adapter simplifies to just passing `npc.attributes` directly instead of calling `estimate_attributes()`.

### Q3: ResolutionState lifecycle for NPC attacks

The NPC attack path in dm.py currently has no `ResolutionState`. The `_execute_attack()` method uses it for:
- `ActionValidator.can_attack()` -- checks if attacker/target are valid
- `resolution_state.mark_defeated()` -- marks defeated targets
- `resolution_state.mark_incapacitated()` -- marks stun KO targets

**Question:** Where does the ResolutionState come from for NPC actions? Options:
1. Create a new ResolutionState per NPC action (loses cross-action validation)
2. Store the round's ResolutionState on the DM agent and pass it through
3. Access it from session.py's round processing

**Recommendation:** Option 2. The DM already manages `_current_resolution_state` for enemy combat. Extend this to NPC combat.

### Q4: What about NPC-on-NPC attacks?

The current `_execute_attack()` handles enemy-on-enemy (hostile factions) and enemy-on-player targeting. NPC-on-NPC attacks would need target resolution for NPC targets. The target resolution code in `_execute_attack()` (lines 931-964) already handles non-player targets via the target_id_mapper. No changes needed if NPCs are registered in the target_id_mapper.

**Verify:** Are NPCs registered in the target_id_mapper? If not, NPC-on-NPC attacks will fail with "target not found". This is acceptable for now (NPC-on-NPC combat is rare and not observed in baseline data).

### Q5: Should the NPC attack path inherit the 0.85 CBM (Combat Balance Modifier)?

The 0.85 multiplier in `_execute_attack()` (line 1073) was introduced to prevent enemy one-shots against PCs. For NPCs attacking enemies, this reduction may be too conservative (NPCs are already weaker than dedicated enemy agents).

**Current proposal:** Keep the 0.85 CBM. NPCs use the same combat formula as enemies -- consistency is more important than NPC-specific tuning at this stage. Can be revisited after collecting NPC combat data from treatment sessions.

### Q6: Stun KO and the "good success" death save path

A character with wounds >= 5 who passes a death save with "good success" (DC+10) returns `(True, "conscious")`. This character is at 0 HP but can keep fighting. The snapshot logic would say `death_state = "unconscious"` (because health <= 0). Should this case be special-handled?

**Current proposal:** No. The snapshot captures instantaneous state. A character at 0 HP is objectively at 0 HP -- the "conscious despite fatal wounds" state is a YAGS exception that should be tracked separately (e.g., via a `critically_wounded_conscious` condition). The death_state field captures the mechanical state, not the narrative state. This keeps the snapshot simple and consistent.

**Future work:** Add a `conditions` list entry for "Critically Wounded (Conscious)" when death save returns good success. This would allow downstream analysis to distinguish between unconscious (failed/marginal save) and fighting-through (good save).
