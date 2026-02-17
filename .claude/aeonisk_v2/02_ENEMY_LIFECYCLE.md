# 02 Enemy Lifecycle: Logging & Cleanup

**Priority:** P0 (data quality bug -- corrupts ML training data)
**Branch:** `aeonisk-v2/enemy-lifecycle`
**Dependencies:** None
**Estimated effort:** Small (1-2 sessions)

---

## Problem Statement

Enemy combat actions produce degraded JSONL log entries that corrupt ML training
data. Two independent bugs compound to create a single systemic issue:

1. **skill=None in action_resolution events.** Every enemy combat action logs an
   `action_resolution` event with `skill: null`, `d20: null`, `total: null`
   because `log_enemy_action()` receives `roll_data=None`. This makes it
   impossible to train models on enemy attack mechanics (attribute, skill,
   roll, margin) -- the most information-dense combat events in the dataset.

2. **Duplicate logging.** Each enemy attack produces TWO log events: a
   high-fidelity `combat_action` event (from `log_combat_action()` inside
   `enemy_combat.py`) and a low-fidelity `action_resolution` event (from
   `log_enemy_action()` called by `session.py`). The duplicate inflates event
   counts and the inferior copy actively degrades any analysis that queries
   `action_resolution` events without filtering by `context.is_enemy`.

3. **Unbounded enemy list growth.** Defeated enemies are soft-deactivated
   (`is_active=False`) but never removed from `enemy_agents`. In long sessions
   (10+ rounds with reinforcement waves), the list accumulates stale objects
   that waste memory and pollute combatant lookups.

### Impact on ML Training

- **Baseline datamining (2026-02-14):** 100% of `action_resolution` events with
  `skill=None` originated from enemy combat actions. Across 20 sessions x 4
  models, this produced ~240 corrupted log entries.
- **Dataset consumers** that join `action_resolution` and `combat_action` events
  on `(round, agent)` get spurious duplicates, inflating apparent enemy activity
  by 2x.
- **Downstream models** trained on these events learn that enemy attacks have no
  skill component, producing unrealistic combat simulations.

---

## Current Implementation

### 1. The Key Mismatch (Root Cause of skill=None)

**File:** `scripts/aeonisk/multiagent/session.py` lines 2292-2306

```python
# Log enemy action to JSONL (uses dedicated method for simplified format)
if mechanics and mechanics.jsonl_logger:
    mechanics.jsonl_logger.log_enemy_action(
        round_num=mechanics.current_round,
        enemy_id=result.get('enemy_id', agent.agent_id),
        enemy_name=result.get('character_name', 'Unknown Enemy'),
        action_type=result.get('action', 'unknown'),
        result=result.get('result', 'unknown'),
        narration=result.get('narration', ''),
        target_id=result.get('target'),
        target_name=result.get('target_name'),
        damage_dealt=result.get('damage_dealt'),
        roll_data=result.get('roll'),       # <-- BUG: key is 'roll'
        effects=result.get('effects')
    )
```

The result dict constructed by `enemy_combat.py:_execute_attack()` (line 1054-1064)
stores the attack total under key `'attack_roll'`:

```python
result = {
    'enemy_id': enemy.agent_id,
    'character_name': enemy.name,
    'action': 'attack',
    'target': target_name,
    'weapon': weapon.name,
    'range': range_name,
    'hit': hit,
    'attack_roll': attack_total,   # <-- stored as 'attack_roll'
    'narration': f"..."
}
```

The same pattern exists in `_execute_suppress()` (line 1381-1391) which also
uses key `'attack_roll'`.

Since `result.get('roll')` returns `None`, `log_enemy_action()` falls through
to its hardcoded null template:

**File:** `scripts/aeonisk/multiagent/mechanics.py` lines 589-601

```python
"roll": roll_data or {
    "attr": None,
    "attr_val": 0,
    "skill": None,      # <-- This is what appears in JSONL
    "skill_val": 0,
    "ability": 0,
    "d20": None,
    "total": None,
    "dc": None,
    "margin": 0,
    "tier": None,
    "success": result in ('success', 'hit')
},
```

### 2. The Duplicate Logging Path

Enemy attacks go through two independent logging calls:

**Path A (high-fidelity):** `enemy_combat.py` line 1216

```python
mechanics_engine.jsonl_logger.log_combat_action(
    round_num=mechanics_engine.current_round,
    attacker_id=enemy.agent_id,
    attacker_name=enemy.name,
    defender_id=self._get_agent_id(target, target_id),
    defender_name=self._get_agent_name(target, target_id),
    weapon=weapon.name,
    attack_roll=attack_roll_data,      # Full roll data with skill, attr, d20, margin
    damage_roll=damage_roll_data,      # Full damage data with soak, dealt, weapon_dmg
    wounds_dealt=wounds_dealt_count,
    defender_state_after=defender_state
)
```

This `attack_roll_data` dict (lines 1170-1182) contains all mechanical fields:

```python
attack_roll_data = {
    "attr": "Perception" | "Dexterity" | "Agility",
    "attr_val": attribute,
    "skill": weapon.skill,        # "Guns", "Melee", "Brawl"
    "skill_val": skill,
    "weapon_bonus": weapon.attack,
    "range_penalty": range_penalty,
    "d20": attack_roll,
    "total": attack_total,
    "dc": target_defence,
    "hit": hit,
    "margin": attack_total - target_defence
}
```

**Path B (low-fidelity):** `session.py` line 2294

This is the `log_enemy_action()` call described above. It produces a second
`action_resolution` event with null roll data because of the key mismatch.

Both paths fire for every enemy attack. The `log_combat_action` path produces
a `combat_action` event type. The `log_enemy_action` path produces an
`action_resolution` event type. The two events contain overlapping but
incompatible data about the same mechanical event.

### 3. Enemy Soft-Deactivation Without Cleanup

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 345-350

```python
is_active: bool = True    # False if defeated/retreated
is_prisoner: bool = False
is_panicked: bool = False
spawned_round: int = 0
despawned_round: Optional[int] = None
```

**File:** `scripts/aeonisk/multiagent/enemy_combat.py` -- deactivation points

Enemies are deactivated at multiple points (grep shows 10 occurrences):
- Line 422: De-escalation to NPC
- Line 449: Departure (fled/killed)
- Line 1162: Target defeated during attack execution
- Line 1722: Morale-based defeat
- Line 1768: Surrender
- Line 1820: Death
- Line 1973: Round-end cleanup

In all cases, the pattern is:
```python
enemy.is_active = False
enemy.despawned_round = self.current_round
```

The enemy object remains in `self.enemy_agents` indefinitely. Filtering uses
`get_active_enemies()`:

**File:** `scripts/aeonisk/multiagent/enemy_spawner.py` line 447

```python
def get_active_enemies(agents: List[EnemyAgent]) -> List[EnemyAgent]:
    """Filter for active enemies only."""
    return [a for a in agents if a.is_active]
```

**File:** `scripts/aeonisk/multiagent/shared_state.py` lines 783-802

```python
def remove_enemy(self, agent_id: str) -> bool:
    """Remove enemy by agent_id (delegates to enemy_combat module)."""
    if not self.enemy_combat:
        return False
    enemy_agents = getattr(self.enemy_combat, 'enemy_agents', [])
    for i, enemy in enumerate(enemy_agents):
        if getattr(enemy, 'agent_id', None) == agent_id:
            enemy_agents.pop(i)
            return True
    return False
```

`remove_enemy()` exists but is only called during de-escalation flows, not
after combat defeats.

---

## Design Decisions

### Decision 1: Remove `log_enemy_action()` call entirely (Option B)

**Rationale:**
- `log_combat_action()` already produces a complete, high-fidelity event with
  full roll data, damage data, and defender state.
- `log_enemy_action()` was written before `log_combat_action()` existed. It
  was the original enemy logging path and is now superseded.
- Fixing the key mismatch (Option A) would still leave duplicate events. The
  cleaner fix is to remove the redundant call.
- The `log_enemy_action()` method itself should NOT be deleted from
  `mechanics.py` yet -- it may be used by other callers or test fixtures. We
  mark it deprecated and remove the call site in `session.py`.

**NOT chosen:** Option A (fix key to `result.get('attack_roll')`) because it
fixes skill=None but leaves the duplication problem. Option C (both) is
over-engineering -- if we remove the call, the key mismatch is moot.

### Decision 2: Add stale enemy pruning at round boundaries

**Rationale:**
- Defeated enemies serve a legitimate tracking purpose: `rounds_survived`,
  `despawned_round`, `defeat_reason` are logged at deactivation time and
  consumed by analysis tools.
- Once the defeat event is logged, the stale object has no further purpose.
- A 2-round grace period ensures that round synthesis can reference recently
  defeated enemies (e.g., "the guard you killed last round").
- Pruning at round boundaries (not mid-round) avoids iterator invalidation
  during combat execution loops.

### Decision 3: Preserve `log_enemy_action()` method signature

**Rationale:**
- The method may be called by replay fixtures, test harnesses, or future
  non-combat enemy actions (movement, token claims) that don't go through
  `_execute_attack()`.
- Deprecation annotation is sufficient; removal can happen in a later cleanup
  pass once all callers are audited.

---

## Proposed Solution

### Part 1: Remove Redundant log_enemy_action() Call

**File:** `scripts/aeonisk/multiagent/session.py`

Remove the `log_enemy_action()` call at lines 2292-2306. The existing
`log_combat_action()` call inside `enemy_combat.py:_execute_attack()` (line
1216) already handles logging with full roll data.

```python
# BEFORE (session.py lines 2287-2306)
                        # Add enemy result to synthesis input
                        all_resolutions.append(result)

                        # Log enemy action to JSONL (uses dedicated method for simplified format)
                        if mechanics and mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_enemy_action(
                                round_num=mechanics.current_round,
                                enemy_id=result.get('enemy_id', agent.agent_id),
                                enemy_name=result.get('character_name', 'Unknown Enemy'),
                                action_type=result.get('action', 'unknown'),
                                result=result.get('result', 'unknown'),
                                narration=result.get('narration', ''),
                                target_id=result.get('target'),
                                target_name=result.get('target_name'),
                                damage_dealt=result.get('damage_dealt'),
                                roll_data=result.get('roll'),
                                effects=result.get('effects')
                            )

# AFTER (session.py)
                        # Add enemy result to synthesis input
                        all_resolutions.append(result)

                        # NOTE: Enemy combat logging handled by log_combat_action()
                        # inside enemy_combat.py:_execute_attack() (line 1216).
                        # The old log_enemy_action() call here was removed because:
                        # 1. It produced duplicate action_resolution events
                        # 2. It had a key mismatch (result.get('roll') vs 'attack_roll')
                        #    causing skill=None in all enemy log entries
                        # See: 02_ENEMY_LIFECYCLE.md
```

For non-combat enemy actions (movement, token claims, suppression) that do NOT
call `log_combat_action()`, we need to verify they are logged elsewhere. Check:

```python
# Suppression (_execute_suppress) -- does NOT call log_combat_action()
# Currently logged only by the removed log_enemy_action() call.
# FIX: Add log_combat_action() call to _execute_suppress() for consistency.

# Movement (_execute_movement) -- no logging currently
# FIX: Add dedicated logging or accept gap (movement is non-mechanical).

# Token claims (_execute_claim_token) -- no logging currently
# FIX: Add dedicated logging or accept gap (tokens are non-mechanical).
```

### Part 2: Add Suppression Logging to enemy_combat.py

Suppression actions currently have no high-fidelity logging path. After removing
the `log_enemy_action()` call from session.py, suppression events would be
completely unlogged. Fix by adding `log_combat_action()` to `_execute_suppress()`.

**File:** `scripts/aeonisk/multiagent/enemy_combat.py`

```python
# Add after line 1407 (end of _execute_suppress), before return result:

        # Log suppression to JSONL for ML training
        if mechanics_engine and hasattr(mechanics_engine, 'jsonl_logger') and mechanics_engine.jsonl_logger:
            suppress_roll_data = {
                "attr": "Perception" if weapon.skill == "Guns" else (
                    "Dexterity" if weapon.skill == "Melee" else "Agility"),
                "attr_val": attribute,
                "skill": weapon.skill,
                "skill_val": skill,
                "weapon_bonus": weapon.attack,
                "range_penalty": range_penalty,
                "d20": attack_roll,
                "total": attack_total,
                "dc": target_defence,
                "hit": hit,
                "margin": attack_total - target_defence
            }

            target_name_str = target.name if hasattr(target, 'name') else str(target_id)
            mechanics_engine.jsonl_logger.log_combat_action(
                round_num=mechanics_engine.current_round if mechanics_engine else self.current_round,
                attacker_id=enemy.agent_id,
                attacker_name=enemy.name,
                defender_id=self._get_agent_id(target, target_id),
                defender_name=target_name_str,
                weapon=f"{weapon.name} (suppress)",
                attack_roll=suppress_roll_data,
                damage_roll=None,  # Suppression does not deal damage
                wounds_dealt=0,
                defender_state_after=None
            )

        return result
```

### Part 3: Deprecate log_enemy_action()

**File:** `scripts/aeonisk/multiagent/mechanics.py`

Add deprecation warning to `log_enemy_action()` docstring and body.

```python
# BEFORE (mechanics.py line 542)
    def log_enemy_action(
        self,
        ...
    ):
        """
        Log an enemy action resolution event.

        Enemy actions are executed locally (not via DM adjudication) so they use
        a simplified format compared to player action_resolution events.
        ...
        """
        event = { ... }
        self._write_event(event)

# AFTER
    def log_enemy_action(
        self,
        ...
    ):
        """
        DEPRECATED: Use log_combat_action() instead.

        This method produces action_resolution events with incomplete roll data
        (skill=None, d20=None) because callers historically passed None for
        roll_data. The log_combat_action() method in enemy_combat.py produces
        higher-fidelity combat_action events with full mechanical data.

        Retained for backward compatibility with replay fixtures and tests.
        Will be removed in a future cleanup pass.

        Original docstring:
        Log an enemy action resolution event.
        ...
        """
        import warnings
        warnings.warn(
            "log_enemy_action() is deprecated. Use log_combat_action() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        event = { ... }
        self._write_event(event)
```

### Part 4: Stale Enemy Pruning

**File:** `scripts/aeonisk/multiagent/enemy_combat.py`

Add `prune_inactive_enemies()` method to `EnemyCombatManager`.

```python
def prune_inactive_enemies(self, min_rounds_inactive: int = 2) -> int:
    """
    Remove enemies that have been inactive for more than min_rounds_inactive.

    Called at round boundaries to prevent unbounded list growth. Enemies are
    kept for min_rounds_inactive rounds after deactivation so that round
    synthesis can reference recently defeated enemies.

    Args:
        min_rounds_inactive: Minimum rounds since despawn before removal.
            Default 2 (enemy defeated in round 3 is pruned at start of round 6).

    Returns:
        Number of enemies pruned.
    """
    if not self.enemy_agents:
        return 0

    pruned = 0
    surviving = []
    for enemy in self.enemy_agents:
        if enemy.is_active:
            # Active enemies are never pruned
            surviving.append(enemy)
            continue

        # Check if enough rounds have passed since deactivation
        if enemy.despawned_round is not None:
            rounds_since_despawn = self.current_round - enemy.despawned_round
            if rounds_since_despawn > min_rounds_inactive:
                logger.debug(
                    f"Pruning inactive enemy {enemy.name} ({enemy.agent_id}), "
                    f"despawned round {enemy.despawned_round}, "
                    f"current round {self.current_round}"
                )
                # Also remove from target ID mapper if present
                if self.shared_state:
                    target_mapper = self.shared_state.get_target_id_mapper()
                    if target_mapper:
                        tid = target_mapper.get_target_id(enemy.agent_id)
                        if tid and tid in target_mapper.target_id_map:
                            del target_mapper.target_id_map[tid]
                        if enemy.agent_id in target_mapper.reverse_map:
                            del target_mapper.reverse_map[enemy.agent_id]
                pruned += 1
                continue

        # No despawned_round set but inactive -- keep for safety
        # (should not happen in normal flow, but defensive)
        surviving.append(enemy)

    self.enemy_agents = surviving

    if pruned > 0:
        logger.info(f"Pruned {pruned} stale enemies (>{min_rounds_inactive} rounds inactive)")

    return pruned
```

### Part 5: Call Pruning at Round Boundaries

**File:** `scripts/aeonisk/multiagent/session.py`

Add pruning call at the start of each round, after round number is incremented
but before enemy declarations.

```python
# In the round execution loop, after incrementing round number:

# Prune stale enemies to prevent unbounded list growth
if self.enemy_combat:
    pruned = self.enemy_combat.prune_inactive_enemies(min_rounds_inactive=2)
    if pruned > 0:
        logger.info(f"Round {round_num}: Pruned {pruned} stale enemies")
```

The exact insertion point depends on the round loop structure. The call should
be placed after `self.current_round` is updated and before
`get_active_enemies()` is called for the new round.

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `scripts/aeonisk/multiagent/session.py` | Remove `log_enemy_action()` call, add pruning call | 2292-2306, round loop |
| `scripts/aeonisk/multiagent/enemy_combat.py` | Add `prune_inactive_enemies()`, add suppress logging | New method, ~1407 |
| `scripts/aeonisk/multiagent/mechanics.py` | Deprecate `log_enemy_action()` | 542-617 |
| `scripts/aeonisk/multiagent/shared_state.py` | No changes needed | -- |

---

## Test Plan

All tests go in `tests/unit/test_enemy_lifecycle.py`.

### Test 1: `test_enemy_attack_produces_single_log_event`

**Purpose:** Verify that an enemy attack produces exactly ONE log event (a
`combat_action`), not two.

```python
def test_enemy_attack_produces_single_log_event(self):
    """After removing redundant log_enemy_action call, enemy attacks
    should produce exactly 1 combat_action event, not a duplicate
    action_resolution event."""
    # Setup: Create mock mechanics engine with JSONL logger that captures events
    logged_events = []
    mock_logger = MockJSONLLogger(logged_events)
    mock_mechanics = MockMechanicsEngine(jsonl_logger=mock_logger)

    # Setup: Create enemy combat manager with one enemy and one PC target
    enemy = create_test_enemy(agent_id="enemy_grunt_1", name="Guard")
    target = create_test_player(agent_id="player_01", name="Sera")

    # Execute: Run enemy attack
    result = enemy_combat._execute_attack(enemy, target, mock_mechanics)

    # Assert: Exactly 1 combat_action event logged
    combat_events = [e for e in logged_events if e['event_type'] == 'combat_action']
    action_events = [e for e in logged_events if e['event_type'] == 'action_resolution']
    assert len(combat_events) == 1, f"Expected 1 combat_action, got {len(combat_events)}"
    assert len(action_events) == 0, f"Expected 0 action_resolution, got {len(action_events)}"
```

### Test 2: `test_combat_action_log_includes_skill`

**Purpose:** Verify the `combat_action` event has non-null skill data.

```python
def test_combat_action_log_includes_skill(self):
    """combat_action events from enemy attacks must include skill data
    (skill name, skill value, attribute, d20, total, margin)."""
    logged_events = []
    mock_logger = MockJSONLLogger(logged_events)
    mock_mechanics = MockMechanicsEngine(jsonl_logger=mock_logger)

    enemy = create_test_enemy(
        agent_id="enemy_grunt_1",
        name="Guard",
        skills={"Guns": 3},
        weapons=[create_test_weapon(skill="Guns")]
    )
    target = create_test_player(agent_id="player_01", name="Sera")

    result = enemy_combat._execute_attack(enemy, target, mock_mechanics)

    combat_events = [e for e in logged_events if e['event_type'] == 'combat_action']
    assert len(combat_events) == 1

    attack_data = combat_events[0]['attack']
    assert attack_data['skill'] is not None, "skill must not be None"
    assert attack_data['skill'] == "Guns"
    assert attack_data['skill_val'] == 3
    assert attack_data['d20'] is not None, "d20 must not be None"
    assert isinstance(attack_data['d20'], int)
    assert 1 <= attack_data['d20'] <= 20
    assert attack_data['total'] is not None, "total must not be None"
    assert attack_data['dc'] is not None, "dc must not be None"
```

### Test 3: `test_suppression_logged_as_combat_action`

**Purpose:** After adding logging to `_execute_suppress()`, verify suppression
produces a `combat_action` event with skill data.

```python
def test_suppression_logged_as_combat_action(self):
    """Suppression actions must produce a combat_action event with
    full roll data, weapon marked as '(suppress)'."""
    logged_events = []
    mock_logger = MockJSONLLogger(logged_events)
    mock_mechanics = MockMechanicsEngine(jsonl_logger=mock_logger)

    enemy = create_test_enemy(
        agent_id="enemy_heavy_1",
        name="Heavy Gunner",
        skills={"Guns": 4},
        weapons=[create_test_weapon(skill="Guns", rof=5, name="LMG")]
    )
    target = create_test_player(agent_id="player_02", name="Vex")

    declaration = create_suppress_declaration(target_id="player_02")
    result = enemy_combat._execute_suppress(
        enemy, declaration, [target], mock_mechanics, resolution_state
    )

    combat_events = [e for e in logged_events if e['event_type'] == 'combat_action']
    assert len(combat_events) == 1

    event = combat_events[0]
    assert "suppress" in event['weapon'].lower()
    assert event['attack']['skill'] == "Guns"
    assert event['attack']['skill_val'] == 4
    assert event['damage'] is None  # Suppression deals no damage
```

### Test 4: `test_defeated_enemy_pruned_after_grace_period`

**Purpose:** Defeated enemies are removed from the list after the grace period.

```python
def test_defeated_enemy_pruned_after_grace_period(self):
    """Enemies defeated more than min_rounds_inactive ago should be
    pruned from enemy_agents list."""
    ecm = create_enemy_combat_manager()

    # Create and defeat an enemy at round 2
    enemy = create_test_enemy(agent_id="enemy_grunt_1", name="Guard")
    ecm.enemy_agents.append(enemy)
    enemy.is_active = False
    enemy.despawned_round = 2

    # Round 3: grace period (1 round since despawn)
    ecm.current_round = 3
    pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
    assert pruned == 0
    assert len(ecm.enemy_agents) == 1

    # Round 4: still within grace period (2 rounds since despawn)
    ecm.current_round = 4
    pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
    assert pruned == 0
    assert len(ecm.enemy_agents) == 1

    # Round 5: grace period expired (3 rounds since despawn > 2)
    ecm.current_round = 5
    pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
    assert pruned == 1
    assert len(ecm.enemy_agents) == 0
```

### Test 5: `test_active_enemy_never_pruned`

**Purpose:** Active enemies must survive pruning regardless of round count.

```python
def test_active_enemy_never_pruned(self):
    """Active enemies must never be removed by pruning, even after
    many rounds."""
    ecm = create_enemy_combat_manager()

    enemy = create_test_enemy(agent_id="enemy_boss_1", name="Boss")
    enemy.is_active = True
    ecm.enemy_agents.append(enemy)

    # Run pruning at high round numbers
    for round_num in range(1, 20):
        ecm.current_round = round_num
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 0
        assert len(ecm.enemy_agents) == 1
        assert ecm.enemy_agents[0].agent_id == "enemy_boss_1"
```

### Test 6: `test_prune_removes_from_target_mapper`

**Purpose:** Pruned enemies must also be cleaned from the target ID mapper.

```python
def test_prune_removes_from_target_mapper(self):
    """When an enemy is pruned, its target ID mapping must also be
    removed to prevent stale ID references."""
    ecm = create_enemy_combat_manager()
    mapper = TargetIDMapper()
    mapper.enable()
    ecm.shared_state.target_id_mapper = mapper

    enemy = create_test_enemy(agent_id="enemy_grunt_1", name="Guard")
    ecm.enemy_agents.append(enemy)

    # Register enemy in mapper
    tid = mapper.register_enemy(enemy)
    assert tid is not None
    assert mapper.resolve_target(tid) is not None

    # Defeat and wait for grace period
    enemy.is_active = False
    enemy.despawned_round = 1
    ecm.current_round = 5

    pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
    assert pruned == 1

    # Verify target mapper is cleaned
    assert mapper.resolve_target(tid) is None
    assert mapper.get_target_id("enemy_grunt_1") is None
```

### Test 7: `test_mixed_active_inactive_pruning`

**Purpose:** Pruning correctly handles a mix of active, recently defeated, and
stale enemies.

```python
def test_mixed_active_inactive_pruning(self):
    """Pruning should only remove stale enemies, keeping active and
    recently defeated ones."""
    ecm = create_enemy_combat_manager()

    # Active enemy
    active = create_test_enemy(agent_id="enemy_1", name="Active Guard")
    active.is_active = True
    ecm.enemy_agents.append(active)

    # Recently defeated (round 8, current is 9 -- within grace)
    recent = create_test_enemy(agent_id="enemy_2", name="Recent Kill")
    recent.is_active = False
    recent.despawned_round = 8
    ecm.enemy_agents.append(recent)

    # Stale defeated (round 3, current is 9 -- well past grace)
    stale = create_test_enemy(agent_id="enemy_3", name="Old Kill")
    stale.is_active = False
    stale.despawned_round = 3
    ecm.enemy_agents.append(stale)

    ecm.current_round = 9
    pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)

    assert pruned == 1
    assert len(ecm.enemy_agents) == 2
    remaining_ids = {e.agent_id for e in ecm.enemy_agents}
    assert "enemy_1" in remaining_ids  # active
    assert "enemy_2" in remaining_ids  # recently defeated
    assert "enemy_3" not in remaining_ids  # pruned
```

### Test 8: `test_log_enemy_action_deprecation_warning`

**Purpose:** Calling `log_enemy_action()` directly emits a deprecation warning.

```python
def test_log_enemy_action_deprecation_warning(self):
    """log_enemy_action() should emit a DeprecationWarning when called
    directly, guiding callers to use log_combat_action() instead."""
    logger = JSONLLogger(session_id="test", output_dir="/tmp")

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        logger.log_enemy_action(
            round_num=1,
            enemy_id="enemy_1",
            enemy_name="Guard",
            action_type="attack",
            result="hit",
            narration="Guard attacks"
        )
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "log_combat_action" in str(w[0].message)
```

---

## Open Questions

1. **Should we delete `log_enemy_action()` entirely?**
   Current plan: deprecate, not delete. If no callers are found after auditing
   tests and replay fixtures, deletion can happen in a follow-up PR.

2. **Non-combat enemy actions (movement, token claims) -- do they need logging?**
   Currently unlogged. Movement is non-mechanical so gap is acceptable. Token
   claims are tactical and might warrant a dedicated `tactical_action` event
   type in the future. Out of scope for this PR.

3. **Should pruning be configurable per session config?**
   No. The 2-round grace period is a safe default. If a specific scenario needs
   to preserve all defeated enemies (e.g., for a "count the bodies" mechanic),
   it can set `min_rounds_inactive` to a very high value at the call site.

4. **Suppression damage logging format.**
   Suppression hits don't deal HP damage but apply a debuff (suppressed status).
   The `log_combat_action` call for suppression sets `damage_roll=None` and
   `wounds_dealt=0`. Analysis tools that filter on `damage.dealt > 0` will
   correctly exclude suppression events. Is this sufficient, or do we need a
   separate `suppression_effect` event type? Current answer: sufficient.

---

## Verification Checklist

After implementation, verify with existing session data:

```bash
# 1. Run unit tests
python -m pytest tests/unit/test_enemy_lifecycle.py -v

# 2. Run a test session and check for duplicate events
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/experiment/session_config_combat_ambush.json \
  --log-level DEBUG

# 3. Analyze output for duplicate enemy events
python scripts/analyze_session.py <output.jsonl> \
  --search event_type=action_resolution context.is_enemy=True --count
# Expected: 0 (no more action_resolution events from enemies)

python scripts/analyze_session.py <output.jsonl> \
  --search event_type=combat_action --count
# Expected: N (same count as before -- combat_action events unchanged)

# 4. Verify skill data in combat_action events
python scripts/analyze_session.py <output.jsonl> \
  --search event_type=combat_action | grep -c "skill.*null"
# Expected: 0 (no null skills in combat_action events)

# 5. Check enemy list size at session end
grep "Pruned.*stale enemies" game.log
# Expected: pruning messages in later rounds of long sessions
```

---

## Rollback Plan

If the changes cause unexpected issues:

1. **Re-add `log_enemy_action()` call:** Revert the session.py deletion. The
   duplicate events are annoying but not session-breaking.
2. **Disable pruning:** Set `min_rounds_inactive=9999` or remove the pruning
   call from the round loop. Stale enemies waste memory but don't cause errors.
3. **Revert deprecation warning:** Remove the `warnings.warn()` call if it
   causes noise in test output.

All three reversions are independent and can be applied selectively.
