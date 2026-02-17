# 03 Target Validation: DM Free-Target Misbinding

**Priority:** P0 (gameplay-breaking -- penalizes players for DM errors)
**Branch:** `aeonisk-v2/target-validation`
**Dependencies:** None
**Estimated effort:** Medium (2-3 sessions)

---

## Problem Statement

The DM agent incorrectly resolves free-target IDs (`tgt_xxxx`) to prisoners,
civilians, and other non-active entities when players describe attacking
"enemies" or "threats." The DM then penalizes players with soulcredit deductions
for attacking non-combatants -- punishing them for a resolution error they did
not cause.

### Evidence from Baseline Data

From the 20-session baseline datamining (2026-02-14):

1. **"Bound prisoner attack" (Grok session 0017, Round 8):**
   PC declared "shoot the remaining active threats" using a generic `tgt_xxxx`
   ID. DM resolved target to a bound prisoner (former enemy, converted to NPC
   with `disposition=prisoner`). DM applied SC=-2 soulcredit penalty for
   "attacking a defenseless prisoner."

2. **"Frightened civilian shot" (Gemini session 0018, Round 3):**
   PC declared "fire at the enemy combatant" using a generic `tgt_xxxx` ID.
   DM resolved target to a fleeing civilian NPC. DM applied SC=-1 soulcredit
   penalty for "harming a non-combatant."

3. **Overall prevalence:** 3 of 5 PC-on-NPC attacks across 20 sessions were
   DM free-target misbinding, not player intent. The remaining 2 were genuine
   player choices (attacking an NPC deliberately).

### Why This Happens

The combatant list shown to the DM provides minimal state differentiation
between active enemies and non-active entities:

```
VALID TARGET IDS:
  - [tgt_7a3f] Syndicate Enforcer (they/them, enemy)
  - [tgt_9b2c] Captured Guard (he/him, npc, prisoner)
  - [tgt_4d1e] Patrol Leader (she/her, enemy)
```

The DM sees "enemy" vs "npc, prisoner" but no explicit `[ACTIVE]` vs
`[PRISONER]` tags. When the player says "shoot the enemy," the DM must infer
which `tgt_xxxx` maps to an active threat vs a subdued prisoner. Under cognitive
load (long combatant lists, complex narration), the DM picks wrong.

### Why Existing Validation Does Not Catch This

The current `targeting_validation.py` module (called at `dm.py:7073-7097`)
validates three things:

1. **Target field exists** -- checks that `DamageEffect.target` is non-null
2. **Target uses ID format** -- checks for `tgt_` prefix (not character name)
3. **Target ID exists in mapper** -- checks that the ID resolves to an entity
4. **Cross-type mismatch** -- catches DM redirecting enemy-targeted damage to
   PCs (or vice versa)

What it does NOT check:

- **Semantic validity** -- whether the resolved target is in a state consistent
  with being attacked (active vs prisoner vs unconscious vs fleeing)
- **Entity-type mismatch for NPCs** -- the cross-type check only looks at
  `is_player()` vs not-player. An NPC prisoner and an active enemy are both
  "not player," so the check passes even when the DM binds a combat action
  to a prisoner.

---

## Current Implementation

### 1. Combatant List Builder

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7535-7578

This code builds the target list injected into the DM resolution prompt:

```python
# Build combatant list with target IDs for structured output
combatant_list = ""
if self.shared_state:
    target_id_mapper = self.shared_state.get_target_id_mapper()
    if target_id_mapper and target_id_mapper.enabled:
        all_target_ids = target_id_mapper.get_all_target_ids()
        if all_target_ids:
            combatant_lines = []
            for tid in sorted(all_target_ids):
                info = target_id_mapper.get_combatant_info(tid)
                if info:
                    pronouns = info.get('pronouns', 'they/them')
                    if info['type'] == 'player' and 'agent_id' in info:
                        # Players: [tgt_xxxx] Name (pronouns, HP/max HP)
                        player_agent = self.shared_state.get_agent_by_id(info['agent_id'])
                        if player_agent and hasattr(player_agent, 'health'):
                            health_text = f"{player_agent.health}/{player_agent.max_health} HP"
                            wounds_text = f", {player_agent.wounds}w" if getattr(player_agent, 'wounds', 0) > 0 else ""
                            combatant_lines.append(
                                f"  - [{tid}] {info['name']} ({pronouns}, {health_text}{wounds_text})")
                        else:
                            combatant_lines.append(
                                f"  - [{tid}] {info['name']} ({pronouns}, player)")
                    elif info['type'] == 'npc':
                        # NPCs: [tgt_xxxx] Name (pronouns, npc, disposition)
                        disposition = 'neutral'
                        if self.shared_state and self.shared_state.npc_agents:
                            for npc in self.shared_state.npc_agents:
                                if hasattr(npc, 'agent_id') and npc.agent_id == info.get('agent_id'):
                                    disposition = getattr(npc, 'disposition', 'neutral')
                                    break
                        combatant_lines.append(
                            f"  - [{tid}] {info['name']} ({pronouns}, npc, {disposition})")
                    else:
                        # Enemies: [tgt_xxxx] Name (pronouns, enemy)
                        combatant_lines.append(
                            f"  - [{tid}] {info['name']} ({pronouns}, {info['type']})")
```

**Problems:**
- Players get health info but no status tag
- NPCs get disposition (`prisoner`, `friendly`, etc.) but no explicit status tag
- Enemies get only `enemy` type label -- NO distinction between active, wounded,
  fleeing, panicked, or surrendered
- No visual hierarchy separates active combatants from non-combatants
- DM prompt does not instruct against targeting non-active entities

### 2. Target Validation (Post-Resolution)

**File:** `scripts/aeonisk/multiagent/targeting_validation.py` lines 22-143

```python
def validate_and_correct_targeting(
    effect: DamageEffect,
    declared_action: Dict[str, Any],
    target_id_mapper: TargetIDMapper,
    allow_llm_fallback: bool = True
) -> Tuple[bool, Optional[DamageEffect], Optional[str]]:
```

Validation steps:
1. STEP 1: Check target field exists (line 48)
2. STEP 2: Check target uses ID format not character name (line 65)
3. STEP 3: Format validation (implicit via Pydantic)
4. STEP 4: Check target ID exists in mapper (line 92)
5. STEP 5: Cross-type mismatch (line 111-139) -- checks `is_player()` only

**Missing STEP:** Semantic state validation. After resolving the target entity,
check whether the entity is in a state where combat targeting makes sense.

### 3. Entity State Information Available

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 345-350

```python
class EnemyAgent:
    is_active: bool = True     # False if defeated/retreated
    is_prisoner: bool = False  # True if surrendered/captured
    is_panicked: bool = False  # True if morale broken
    despawned_round: Optional[int] = None
```

**File:** `scripts/aeonisk/multiagent/npc_agent.py` lines 260-267

```python
class NPCAgent:
    agent_id: str
    entity_type: Literal["neutral", "ally", "prisoner"]
    disposition: Literal["friendly", "neutral", "wary", "prisoner"]
    is_active: bool  # (field at line 292, default via can_act)
```

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 281-345

`get_combatant_info()` already exposes:
- `type`: "player", "enemy", "npc", "vendor"
- `health`, `max_health`, `wounds`, `stuns`
- `death_state`: "alive", "unconscious", "dead"

But does NOT expose:
- `is_active` (enemy)
- `is_prisoner` (enemy)
- `is_panicked` (enemy)
- `disposition` (NPC -- available but not in combatant info dict)
- `entity_type` (NPC)

### 4. TargetIDMapper Type Checking

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 234-270

```python
def is_player(self, target_id: str) -> bool:
    """Check if target ID belongs to a player character."""
    agent = self.resolve_target(target_id)
    if not agent:
        return False
    is_pc = hasattr(agent, 'character_state')
    return is_pc

def is_enemy(self, target_id: str) -> bool:
    """Check if target ID belongs to an enemy."""
    agent = self.resolve_target(target_id)
    if not agent:
        return False
    # BUG: Variable named is_npc but actually checks for enemy
    is_npc = hasattr(agent, 'is_active') and hasattr(agent, 'tactics')
    return is_npc
```

Note: `is_enemy()` has a misleading variable name (`is_npc`) but the logic is
correct -- it checks for `tactics` attribute which only `EnemyAgent` has.

There is no `is_npc()` method that takes a `target_id` (there is one that takes
`agent_id` at line 432, but it checks the NPC registry, not the target mapper).

---

## Design Decisions

### Decision 1: State tags in combatant list (Layer 1 -- Prevention)

**Rationale:**
- The most effective fix is to make the DM less likely to make the mistake in
  the first place. Explicit `[ACTIVE]`, `[PRISONER]`, `[FLEEING]` tags make
  entity state instantly visible.
- This is a prompt engineering fix with zero runtime cost. The DM prompt already
  includes a combatant list; we are enriching existing data, not adding new
  prompts or API calls.
- State tags follow the established pattern of structured annotations in the
  combatant list (e.g., health info for players, disposition for NPCs).

**Format chosen:**
```
  - [tgt_7a3f] Syndicate Enforcer (they/them, enemy) [ACTIVE]
  - [tgt_9b2c] Captured Guard (he/him, npc, prisoner) [PRISONER]
  - [tgt_4d1e] Patrol Leader (she/her, enemy) [WOUNDED - 4/20 HP]
  - [tgt_2f8a] Fleeing Civilian (they/them, npc, wary) [FLEEING]
  - [tgt_6c3b] Vessel Sera Karsel (she/her, 15/27 HP, 2w) [ACTIVE]
```

Tags are appended at the end of each line (not prefixed) so they don't break
existing target ID parsing patterns.

### Decision 2: Post-resolution semantic validation (Layer 2 -- Detection)

**Rationale:**
- Even with better prompt context, LLMs can still make mistakes. A mechanical
  check after resolution catches errors that slip through prompt improvements.
- The check is lightweight: resolve target, check `is_active`/`disposition`/
  `entity_type`, log warning. No additional API calls.
- In the initial implementation, the check WARNS but does NOT block. This
  avoids breaking sessions while we collect data on false positive rate.
- Future upgrade path: once false positive rate is confirmed low, switch from
  warn to block+redirect (redirect damage to the declared target instead).

### Decision 3: DM prompt instruction (Layer 3 -- Guidance)

**Rationale:**
- Explicit rules in the DM prompt reinforce the state tags. The instruction
  tells the DM what to do when a player says "shoot the enemy" -- resolve to
  an `[ACTIVE]` enemy, not a `[PRISONER]`.
- This is the lowest-cost fix (one sentence added to prompt) and serves as a
  natural-language safety net for the structured tags.

### Decision 4: No immediate blocking of invalid targeting

**Rationale:**
- Blocking combat actions against prisoners/NPCs would prevent legitimate
  gameplay choices (player deliberately attacking a prisoner for story reasons).
- The validation should WARN, not BLOCK, in its initial implementation.
- The soulcredit system already handles the ethical dimension -- the fix is to
  ensure the DM only applies SC penalties when the PLAYER chose to target a
  non-combatant, not when the DM misbound a target.

---

## Proposed Solution

### Layer 1: Combatant List State Annotations

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7535-7578

Replace the existing combatant list builder with a version that adds state tags.

```python
# Build combatant list with target IDs for structured output
combatant_list = ""
if self.shared_state:
    target_id_mapper = self.shared_state.get_target_id_mapper()
    if target_id_mapper and target_id_mapper.enabled:
        all_target_ids = target_id_mapper.get_all_target_ids()
        if all_target_ids:
            combatant_lines = []
            for tid in sorted(all_target_ids):
                info = target_id_mapper.get_combatant_info(tid)
                if info:
                    pronouns = info.get('pronouns', 'they/them')

                    # Determine state tag for this entity
                    state_tag = _get_combatant_state_tag(
                        info, tid, self.shared_state
                    )

                    if info['type'] == 'player' and 'agent_id' in info:
                        player_agent = self.shared_state.get_agent_by_id(info['agent_id'])
                        if player_agent and hasattr(player_agent, 'health'):
                            health_text = f"{player_agent.health}/{player_agent.max_health} HP"
                            wounds_text = (f", {player_agent.wounds}w"
                                           if getattr(player_agent, 'wounds', 0) > 0 else "")
                            combatant_lines.append(
                                f"  - [{tid}] {info['name']} "
                                f"({pronouns}, {health_text}{wounds_text}) "
                                f"{state_tag}")
                        else:
                            combatant_lines.append(
                                f"  - [{tid}] {info['name']} "
                                f"({pronouns}, player) {state_tag}")
                    elif info['type'] == 'npc':
                        disposition = 'neutral'
                        if self.shared_state and self.shared_state.npc_agents:
                            for npc in self.shared_state.npc_agents:
                                if (hasattr(npc, 'agent_id') and
                                        npc.agent_id == info.get('agent_id')):
                                    disposition = getattr(npc, 'disposition', 'neutral')
                                    break
                        combatant_lines.append(
                            f"  - [{tid}] {info['name']} "
                            f"({pronouns}, npc, {disposition}) "
                            f"{state_tag}")
                    else:
                        # Enemies
                        combatant_lines.append(
                            f"  - [{tid}] {info['name']} "
                            f"({pronouns}, {info['type']}) "
                            f"{state_tag}")
```

**New helper function** (add to `dm.py` at module level or as a static method):

```python
def _get_combatant_state_tag(
    info: Dict[str, Any],
    target_id: str,
    shared_state: Any
) -> str:
    """
    Generate a state tag for a combatant in the DM target list.

    Returns a bracketed tag like [ACTIVE], [PRISONER], [WOUNDED], etc.
    that helps the DM distinguish targetable entities from non-combatants.

    Args:
        info: Combatant info dict from TargetIDMapper.get_combatant_info()
        target_id: The tgt_xxxx ID
        shared_state: SharedState instance for entity lookups

    Returns:
        State tag string, e.g. "[ACTIVE]", "[PRISONER]", "[UNCONSCIOUS]"
    """
    entity_type = info.get('type', 'unknown')

    # Check death state first (applies to all entity types)
    death_state = info.get('death_state', 'alive')
    if death_state == 'dead':
        return "[DEAD]"
    if death_state == 'unconscious':
        return "[UNCONSCIOUS]"

    # Player-specific states
    if entity_type == 'player':
        health = info.get('health', 0)
        max_health = info.get('max_health', 1)
        wounds = info.get('wounds', 0)
        if wounds >= 4:
            return "[CRITICAL]"
        elif health <= max_health * 0.25 and max_health > 0:
            return "[WOUNDED]"
        return "[ACTIVE]"

    # NPC-specific states
    if entity_type == 'npc':
        # Look up NPC agent for disposition and entity_type
        if shared_state and shared_state.npc_agents:
            agent_id = info.get('agent_id')
            for npc in shared_state.npc_agents:
                if hasattr(npc, 'agent_id') and npc.agent_id == agent_id:
                    if npc.disposition == 'prisoner' or npc.entity_type == 'prisoner':
                        return "[PRISONER]"
                    if not getattr(npc, 'is_active', True):
                        return "[INACTIVE]"
                    # Check if NPC is fleeing (has flee action in recent memory)
                    if (hasattr(npc, 'memory') and npc.memory and
                            npc.memory.own_actions):
                        last_action = npc.memory.own_actions[-1]
                        if last_action.get('action_type') == 'flee':
                            return "[FLEEING]"
                    return "[NON-COMBATANT]"
        return "[NON-COMBATANT]"

    # Enemy-specific states
    if entity_type == 'enemy':
        # Look up enemy agent for state flags
        agent = None
        if shared_state and shared_state.enemy_combat:
            agent_id = info.get('agent_id')
            for enemy in shared_state.enemy_combat.enemy_agents:
                if getattr(enemy, 'agent_id', None) == agent_id:
                    agent = enemy
                    break

        if agent:
            if agent.is_prisoner:
                return "[PRISONER]"
            if not agent.is_active:
                return "[DEFEATED]"
            if agent.is_panicked:
                return "[PANICKED/FLEEING]"
            # Wounded check
            health = info.get('health', 0)
            max_health = info.get('max_health', 1)
            if max_health > 0 and health <= max_health * 0.25:
                return "[WOUNDED]"
            return "[ACTIVE]"
        return "[ACTIVE]"

    # Vendor
    if entity_type == 'vendor':
        return "[VENDOR/NON-COMBATANT]"

    return "[UNKNOWN]"
```

### Layer 2: Post-Resolution Semantic Validation

**File:** `scripts/aeonisk/multiagent/targeting_validation.py`

Add a new validation step (STEP 5.5) between the existing cross-type check
(STEP 5) and the final pass (STEP 6).

```python
    # STEP 5.5: Semantic state validation — check if target is in a
    # combat-appropriate state (not prisoner, unconscious, defeated, etc.)
    #
    # This catches DM free-target misbinding where the DM resolves a
    # combat action to a prisoner/civilian instead of an active enemy.
    if resolved_entity:
        semantic_warning = _check_target_combat_state(
            resolved_entity, effect, target_id_mapper
        )
        if semantic_warning:
            # Log warning but DO NOT block — player may intentionally
            # target non-combatants (ethical gameplay choice).
            logger.warning(
                f"⚠️  TARGET SEMANTIC WARNING: {semantic_warning} "
                f"(target={effect.target})"
            )
            # Future: If declared_action target differs from effect target,
            # this is likely DM misbinding. Could auto-correct to declared
            # target. For now, warn only.


def _check_target_combat_state(
    entity: Any,
    effect: 'DamageEffect',
    target_id_mapper: 'TargetIDMapper'
) -> Optional[str]:
    """
    Check if target entity is in a state where combat targeting is
    semantically appropriate.

    Returns None if targeting is appropriate, or a warning string if the
    target appears to be a non-combatant, prisoner, or defeated entity.

    This is a SOFT check — it warns but does not block. Players may
    legitimately choose to attack prisoners or non-combatants, and the
    soulcredit system handles the ethical dimension.

    Args:
        entity: Resolved agent object (EnemyAgent, NPCAgent, or player)
        effect: The DamageEffect being validated
        target_id_mapper: For additional lookups if needed

    Returns:
        Warning string if targeting is questionable, None if appropriate
    """
    # Check NPC state
    if hasattr(entity, 'disposition'):
        # NPCAgent
        if getattr(entity, 'disposition', None) == 'prisoner':
            return (
                f"Combat damage targeting prisoner NPC '{entity.name}' "
                f"(disposition=prisoner). If player declared targeting "
                f"'enemies' or 'threats', this may be DM misbinding."
            )
        if getattr(entity, 'entity_type', None) == 'prisoner':
            return (
                f"Combat damage targeting prisoner NPC '{entity.name}' "
                f"(entity_type=prisoner). Verify player intent."
            )

    # Check enemy state
    if hasattr(entity, 'is_prisoner') and entity.is_prisoner:
        return (
            f"Combat damage targeting prisoner enemy '{entity.name}' "
            f"(is_prisoner=True). This entity has surrendered/been captured."
        )

    if hasattr(entity, 'is_active') and not entity.is_active:
        # Could be defeated, fled, or de-escalated
        if hasattr(entity, 'despawned_round') and entity.despawned_round is not None:
            return (
                f"Combat damage targeting defeated/removed entity "
                f"'{entity.name}' (is_active=False, despawned round "
                f"{entity.despawned_round}). Entity is no longer in combat."
            )

    # Check death state
    if hasattr(entity, 'health') and hasattr(entity, 'max_health'):
        if entity.health <= 0:
            return (
                f"Combat damage targeting unconscious/dead entity "
                f"'{entity.name}' (health={entity.health}). "
                f"Entity is already incapacitated."
            )

    # No issues detected
    return None
```

### Layer 3: DM Prompt Instruction

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7570-7578

Add targeting guidance to the combatant list header. Insert after the existing
"DO NOT use character names" warnings:

```python
                    combatant_list += "\n".join(combatant_lines)

                    # Existing warnings (unchanged)
                    combatant_list += "\n\n"
                    combatant_list += "✅ **CORRECT:** DamageEffect(target=\"tgt_7a3f\", ...) ← Uses exact ID from list\n"
                    combatant_list += "❌ **WRONG:** DamageEffect(target=\"Tempest Enforcer\", ...) ← Character name - FAILS!\n"
                    combatant_list += "❌ **WRONG:** DamageEffect(target=\"tgt_enforcer1\", ...) ← Invented ID - FAILS!\n"
                    combatant_list += "\n💡 **TIP:** Character names go in NARRATION only, NOT in target= fields.\n"

                    # NEW: Anti-misbinding instruction
                    combatant_list += "\n"
                    combatant_list += "⚠️  **TARGETING RULE:** When a player declares an attack against "
                    combatant_list += "'enemies', 'threats', or 'hostiles', resolve the target to an "
                    combatant_list += "entity tagged [ACTIVE], NOT one tagged [PRISONER], [DEFEATED], "
                    combatant_list += "[UNCONSCIOUS], [FLEEING], or [NON-COMBATANT]. "
                    combatant_list += "Only resolve to non-active targets if the player EXPLICITLY "
                    combatant_list += "names or describes targeting that specific entity.\n"
```

### Layer 4: Enrich TargetIDMapper.get_combatant_info()

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 281-345

Add state fields to the returned info dict so that consumers (including the
state tag generator and semantic validator) have access to entity state.

```python
def get_combatant_info(self, target_id: str) -> Optional[Dict[str, Any]]:
    """Get structured info about a combatant."""
    agent = self.resolve_target(target_id)
    if not agent:
        return None

    # ... existing code for entity_type determination ...

    info = {
        'target_id': target_id,
        'agent_id': entity_id,
        'type': entity_type
    }

    # ... existing attribute extraction ...

    # NEW: Add state fields for semantic validation
    info['is_active'] = getattr(agent, 'is_active', True)
    info['is_prisoner'] = getattr(agent, 'is_prisoner', False)
    info['is_panicked'] = getattr(agent, 'is_panicked', False)
    info['disposition'] = getattr(agent, 'disposition', None)
    info['entity_subtype'] = getattr(agent, 'entity_type', None)

    return info
```

### Layer 5: Add get_combatant_status() to TargetIDMapper

**File:** `scripts/aeonisk/multiagent/target_ids.py`

New convenience method for consumers that need a single status string.

```python
def get_combatant_status(self, target_id: str) -> Optional[str]:
    """
    Get the combat status of a combatant as a single string.

    Returns one of:
        "active" - Can be targeted normally
        "prisoner" - Surrendered/captured, targeting is ethically questionable
        "defeated" - Removed from combat (is_active=False)
        "unconscious" - Health <= 0 but not dead
        "dead" - Permanently dead (wounds >= 6)
        "fleeing" - Panicked/morale broken
        "non_combatant" - NPC with non-hostile disposition
        None - Target ID not found

    Args:
        target_id: The tgt_xxxx ID to check

    Returns:
        Status string or None
    """
    info = self.get_combatant_info(target_id)
    if not info:
        return None

    # Death states take priority
    death_state = info.get('death_state', 'alive')
    if death_state == 'dead':
        return 'dead'
    if death_state == 'unconscious':
        return 'unconscious'

    # Prisoner state (enemy or NPC)
    if info.get('is_prisoner', False):
        return 'prisoner'
    if info.get('disposition') == 'prisoner':
        return 'prisoner'
    if info.get('entity_subtype') == 'prisoner':
        return 'prisoner'

    # Defeated/inactive
    if not info.get('is_active', True):
        return 'defeated'

    # Fleeing
    if info.get('is_panicked', False):
        return 'fleeing'

    # NPC non-combatant check
    if info.get('type') == 'npc':
        disposition = info.get('disposition')
        if disposition in ('friendly', 'neutral', 'wary'):
            return 'non_combatant'

    # Player or active enemy
    return 'active'
```

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `scripts/aeonisk/multiagent/dm.py` | Combatant list state tags, DM prompt instruction | 7535-7578 |
| `scripts/aeonisk/multiagent/target_ids.py` | `get_combatant_info()` state fields, new `get_combatant_status()` | 281-345, new method |
| `scripts/aeonisk/multiagent/targeting_validation.py` | Semantic state validation (STEP 5.5) | After line 139 |
| `scripts/aeonisk/multiagent/npc_agent.py` | No changes needed (already has disposition, entity_type) | -- |
| `scripts/aeonisk/multiagent/enemy_agent.py` | No changes needed (already has is_active, is_prisoner, is_panicked) | -- |

---

## Test Plan

All tests go in `tests/unit/test_target_validation.py` (extend existing file
if it exists, or create new).

### Test 1: `test_combatant_list_shows_active_tag`

**Purpose:** Active enemies get `[ACTIVE]` tag in combatant list.

```python
def test_combatant_list_shows_active_tag(self):
    """Active enemies must have [ACTIVE] tag in the combatant list
    shown to the DM."""
    # Setup: Create target mapper with one active enemy
    mapper = TargetIDMapper()
    mapper.enable()
    enemy = create_test_enemy(
        agent_id="enemy_grunt_1", name="Guard",
        is_active=True, is_prisoner=False
    )
    tid = mapper.register_enemy(enemy)

    # Build combatant list using the state tag helper
    info = mapper.get_combatant_info(tid)
    state_tag = _get_combatant_state_tag(info, tid, shared_state)

    assert state_tag == "[ACTIVE]"
```

### Test 2: `test_combatant_list_shows_prisoner_tag_for_enemy`

**Purpose:** Prisoner enemies get `[PRISONER]` tag.

```python
def test_combatant_list_shows_prisoner_tag_for_enemy(self):
    """Enemies with is_prisoner=True must show [PRISONER] tag."""
    mapper = TargetIDMapper()
    mapper.enable()
    enemy = create_test_enemy(
        agent_id="enemy_grunt_1", name="Captured Guard",
        is_active=False, is_prisoner=True
    )
    tid = mapper.register_enemy(enemy)

    info = mapper.get_combatant_info(tid)
    state_tag = _get_combatant_state_tag(info, tid, shared_state)

    assert state_tag == "[PRISONER]"
```

### Test 3: `test_combatant_list_shows_prisoner_tag_for_npc`

**Purpose:** NPC with `disposition=prisoner` gets `[PRISONER]` tag.

```python
def test_combatant_list_shows_prisoner_tag_for_npc(self):
    """NPCs with disposition=prisoner must show [PRISONER] tag."""
    mapper = TargetIDMapper()
    mapper.enable()

    npc = create_test_npc(
        agent_id="enemy_guard_001",  # Stable ID from conversion
        name="Subdued Guard",
        disposition="prisoner",
        entity_type="prisoner"
    )

    # Register NPC in mapper and shared state
    mapper.register_npc(npc)
    shared_state.npc_agents = [npc]

    # Assign target ID
    tid = mapper.assign_ids([], [], npc_agents=[npc])
    npc_tid = mapper.get_target_id(npc.agent_id)

    info = mapper.get_combatant_info(npc_tid)
    state_tag = _get_combatant_state_tag(info, npc_tid, shared_state)

    assert state_tag == "[PRISONER]"
```

### Test 4: `test_combatant_list_shows_fleeing_tag`

**Purpose:** Panicked enemies get `[PANICKED/FLEEING]` tag.

```python
def test_combatant_list_shows_fleeing_tag(self):
    """Enemies with is_panicked=True must show [PANICKED/FLEEING] tag."""
    mapper = TargetIDMapper()
    mapper.enable()
    enemy = create_test_enemy(
        agent_id="enemy_grunt_1", name="Panicked Guard",
        is_active=True, is_panicked=True
    )
    tid = mapper.register_enemy(enemy)

    info = mapper.get_combatant_info(tid)
    state_tag = _get_combatant_state_tag(info, tid, shared_state)

    assert state_tag == "[PANICKED/FLEEING]"
```

### Test 5: `test_semantic_validator_warns_on_prisoner_targeting`

**Purpose:** Post-resolution validator warns when DamageEffect targets a prisoner.

```python
def test_semantic_validator_warns_on_prisoner_targeting(self):
    """When DM resolution targets a prisoner entity with damage,
    the semantic validator must emit a warning."""
    mapper = TargetIDMapper()
    mapper.enable()

    prisoner = create_test_enemy(
        agent_id="enemy_prisoner_1", name="Bound Captive",
        is_active=False, is_prisoner=True
    )
    tid = mapper.register_enemy(prisoner)

    effect = DamageEffect(
        target=tid,
        dealt=5,
        damage_type="wound"
    )

    warning = _check_target_combat_state(prisoner, effect, mapper)

    assert warning is not None
    assert "prisoner" in warning.lower()
    assert prisoner.name in warning
```

### Test 6: `test_semantic_validator_allows_active_targeting`

**Purpose:** Active enemy targeting does not trigger warning.

```python
def test_semantic_validator_allows_active_targeting(self):
    """Targeting an active enemy must not trigger any warning."""
    mapper = TargetIDMapper()
    mapper.enable()

    enemy = create_test_enemy(
        agent_id="enemy_grunt_1", name="Active Guard",
        is_active=True, is_prisoner=False
    )
    tid = mapper.register_enemy(enemy)

    effect = DamageEffect(
        target=tid,
        dealt=5,
        damage_type="wound"
    )

    warning = _check_target_combat_state(enemy, effect, mapper)

    assert warning is None
```

### Test 7: `test_semantic_validator_warns_on_unconscious_targeting`

**Purpose:** Targeting an entity with health <= 0 triggers warning.

```python
def test_semantic_validator_warns_on_unconscious_targeting(self):
    """Targeting an unconscious entity (health=0) must trigger warning."""
    mapper = TargetIDMapper()
    mapper.enable()

    enemy = create_test_enemy(
        agent_id="enemy_grunt_1", name="Downed Guard",
        is_active=False, health=0, max_health=20
    )
    tid = mapper.register_enemy(enemy)

    effect = DamageEffect(
        target=tid,
        dealt=5,
        damage_type="wound"
    )

    warning = _check_target_combat_state(enemy, effect, mapper)

    assert warning is not None
    assert "unconscious" in warning.lower() or "incapacitated" in warning.lower()
```

### Test 8: `test_get_combatant_status_returns_correct_states`

**Purpose:** The new `get_combatant_status()` method returns correct states.

```python
def test_get_combatant_status_returns_correct_states(self):
    """get_combatant_status() must return correct status for each
    entity state."""
    mapper = TargetIDMapper()
    mapper.enable()

    # Active enemy
    active = create_test_enemy(
        agent_id="enemy_1", name="Active",
        is_active=True, is_prisoner=False
    )
    tid_active = mapper.register_enemy(active)
    assert mapper.get_combatant_status(tid_active) == "active"

    # Prisoner enemy
    prisoner = create_test_enemy(
        agent_id="enemy_2", name="Prisoner",
        is_active=False, is_prisoner=True
    )
    tid_prisoner = mapper.register_enemy(prisoner)
    assert mapper.get_combatant_status(tid_prisoner) == "prisoner"

    # Panicked enemy
    panicked = create_test_enemy(
        agent_id="enemy_3", name="Panicked",
        is_active=True, is_panicked=True
    )
    tid_panicked = mapper.register_enemy(panicked)
    assert mapper.get_combatant_status(tid_panicked) == "fleeing"

    # Defeated enemy
    defeated = create_test_enemy(
        agent_id="enemy_4", name="Defeated",
        is_active=False, is_prisoner=False
    )
    tid_defeated = mapper.register_enemy(defeated)
    assert mapper.get_combatant_status(tid_defeated) == "defeated"

    # NPC non-combatant
    npc = create_test_npc(
        agent_id="npc_1", name="Civilian",
        disposition="neutral", entity_type="neutral"
    )
    mapper.register_npc(npc)
    npc_ids = mapper.assign_ids([], [], npc_agents=[npc])
    tid_npc = mapper.get_target_id("npc_1")
    assert mapper.get_combatant_status(tid_npc) == "non_combatant"
```

### Test 9: `test_mixed_combatant_list_state_tags`

**Purpose:** A realistic combatant list with mixed entities produces correct tags.

```python
def test_mixed_combatant_list_state_tags(self):
    """Build a combatant list with a mix of active enemies, prisoners,
    NPCs, and players. Verify all get correct state tags."""
    mapper = TargetIDMapper()
    mapper.enable()

    # Active enemy
    active_enemy = create_test_enemy(
        agent_id="enemy_1", name="Enforcer",
        is_active=True
    )
    # Prisoner enemy
    prisoner_enemy = create_test_enemy(
        agent_id="enemy_2", name="Captured Sentry",
        is_active=False, is_prisoner=True
    )
    # Prisoner NPC (converted from enemy)
    prisoner_npc = create_test_npc(
        agent_id="enemy_3", name="Subdued Guard",
        disposition="prisoner", entity_type="prisoner"
    )
    # Active player
    player = create_test_player(
        agent_id="player_01", name="Vessel Sera",
        health=20, max_health=27
    )

    # Register all entities
    mapper.register_enemy(active_enemy)
    mapper.register_enemy(prisoner_enemy)
    mapper.register_npc(prisoner_npc)
    mapper.assign_ids(
        [player],
        [active_enemy, prisoner_enemy],
        npc_agents=[prisoner_npc]
    )

    shared_state.npc_agents = [prisoner_npc]
    shared_state.enemy_combat.enemy_agents = [active_enemy, prisoner_enemy]

    # Verify tags
    for tid in mapper.get_all_target_ids():
        info = mapper.get_combatant_info(tid)
        tag = _get_combatant_state_tag(info, tid, shared_state)
        name = info['name']

        if name == "Enforcer":
            assert tag == "[ACTIVE]", f"Active enemy got tag {tag}"
        elif name == "Captured Sentry":
            assert tag == "[PRISONER]", f"Prisoner enemy got tag {tag}"
        elif name == "Subdued Guard":
            assert tag == "[PRISONER]", f"Prisoner NPC got tag {tag}"
        elif name == "Vessel Sera":
            assert tag == "[ACTIVE]", f"Active player got tag {tag}"
```

### Test 10: `test_combatant_info_includes_state_fields`

**Purpose:** `get_combatant_info()` returns the new state fields.

```python
def test_combatant_info_includes_state_fields(self):
    """get_combatant_info() must include is_active, is_prisoner,
    is_panicked, disposition, and entity_subtype fields."""
    mapper = TargetIDMapper()
    mapper.enable()

    enemy = create_test_enemy(
        agent_id="enemy_1", name="Guard",
        is_active=True, is_prisoner=False, is_panicked=True
    )
    tid = mapper.register_enemy(enemy)

    info = mapper.get_combatant_info(tid)

    assert 'is_active' in info
    assert info['is_active'] is True
    assert 'is_prisoner' in info
    assert info['is_prisoner'] is False
    assert 'is_panicked' in info
    assert info['is_panicked'] is True
```

---

## Open Questions

1. **Should the semantic validator auto-correct misbinding?**
   Current plan: warn only. Future upgrade: if `declared_action.target` differs
   from `effect.target` AND the effect target is a prisoner/non-combatant, auto-
   correct to the declared target (same pattern as the existing cross-type
   correction in STEP 5). This would require confidence that the declared target
   is always the "right" one, which is not always true (player might change
   their mind during narration).

2. **Should prisoner/non-combatant entities be excluded from `assign_ids()`?**
   Currently, prisoners still get `tgt_xxxx` IDs because they remain in the
   combatant list (players might want to interact with them -- heal, interrogate,
   etc.). Excluding them would prevent misbinding entirely but would also prevent
   legitimate interactions. Current answer: keep them in the list but with clear
   state tags.

3. **How should the `[WOUNDED]` threshold be set?**
   Current proposal: 25% HP or 4+ wounds. This is borrowed from the YAGS wound
   ladder where 4+ wounds means "Badly Injured." Should this be configurable?
   Current answer: no, hardcode as a visual hint. The exact threshold does not
   affect targeting correctness.

4. **Should vendors get state tags?**
   Current proposal: `[VENDOR/NON-COMBATANT]`. Vendors are never valid combat
   targets in normal gameplay. However, players might attack a vendor for story
   reasons (robbing a shop). The tag serves as a reminder but does not block.

5. **Performance impact of state tag generation?**
   The state tag function performs attribute lookups on existing objects with no
   API calls, database queries, or complex computation. For a typical combatant
   list of 5-15 entities, this adds < 1ms total. No performance concern.

6. **Variable naming bug in `is_enemy()` (target_ids.py line 269)?**
   The variable is named `is_npc` but actually checks for enemy attributes.
   Should be renamed to `has_enemy_attrs` or similar. Out of scope for this
   PR but worth noting.

---

## Verification Checklist

After implementation, verify with a test session:

```bash
# 1. Run unit tests
python -m pytest tests/unit/test_target_validation.py -v

# 2. Run a combat session with enemies and NPCs
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/experiment/session_config_combat_ambush.json \
  --log-level DEBUG

# 3. Check that combatant list includes state tags
grep "ACTIVE\|PRISONER\|FLEEING\|NON-COMBATANT" game.log | head -20
# Expected: state tags in combatant list lines

# 4. Check for semantic warnings
grep "TARGET SEMANTIC WARNING" game.log
# Expected: warnings if DM targets non-active entities

# 5. Check for anti-misbinding instruction in DM prompt
grep "TARGETING RULE" game.log | head -5
# Expected: the new targeting rule appears in DM resolution prompts

# 6. Verify no false positives (active enemy targeting should NOT warn)
# Run a clean combat session and confirm no spurious warnings
python scripts/analyze_session.py <output.jsonl> --mode=errors
```

---

## Rollback Plan

The three layers are independent and can be reverted selectively:

1. **Revert state tags (Layer 1):** Remove `_get_combatant_state_tag()` and
   revert combatant list builder to original format. State tags are purely
   informational and their removal does not break any mechanical system.

2. **Revert semantic validation (Layer 2):** Remove the STEP 5.5 block from
   `targeting_validation.py`. The validation is warn-only so its removal has
   no gameplay impact.

3. **Revert DM prompt instruction (Layer 3):** Remove the anti-misbinding
   instruction text. Single line deletion.

4. **Revert combatant info enrichment (Layer 4):** Remove the new state fields
   from `get_combatant_info()`. Only affects consumers that read the new fields
   (Layers 1-2). Remove those first.

5. **Revert `get_combatant_status()` (Layer 5):** Delete the new method. Only
   affects tests and potential future consumers. No existing code depends on it.
