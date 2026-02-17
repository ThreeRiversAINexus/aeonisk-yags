# 09: Range Band Awareness & Intra-Round Movement

**Priority:** P2
**Status:** Proposed
**Branch:** TBD (off `main`)
**Dependencies:** None

---

## Problem Statement

Range bands and movement are mechanically implemented but poorly communicated to AI agents. The result is that agents make decisions without understanding distances, penalties, and movement trade-offs:

1. **Agents do not see range penalties in their prompts.** The `Position` class (enemy_agent.py:44-188) implements a complete concentric ring model with range penalties (-2 Near, -4 Far, -6 Extreme), but this information is not surfaced in player or DM prompts. Players try to "move to the same range band as the enemy" (user observation) without understanding what that means mechanically.

2. **No movement action for players.** Enemies have Shift, Push_Through, Charge, and Retreat movement types (enemy_combat.py:1470, 1635, 1744). Players can set `target_position` in ExploreAction or CombatAction, but there is no dedicated movement action that trades attack opportunity for position change. Movement is a side effect of other actions, not a deliberate tactical choice.

3. **Movement does not affect subsequent resolutions within the same round.** If a player moves from Far-PC to Near-PC in their action, enemy attacks against them later in the same round still use the old position for range calculation. Intra-round position updates do not propagate to the resolution state.

4. **DM prompts lack distance context for combat.** The DM resolution prompt receives a combatant list with target IDs but no range/distance information. The DM cannot narrate range-appropriate combat ("long-range sniper duel" vs "point-blank firefight") because it does not know the distances involved.

### Impact on Tactical Depth

The concentric ring model (Tactical Module v1.2.3) is the foundation of tactical combat. Without range awareness:
- Players never exploit range advantages (staying at Far for sniper characters)
- Players never use movement to avoid attacks (moving to cover at Extreme range)
- The -6 Extreme penalty is invisible, causing confusion when "easy" shots fail
- Enemy Shift/Push_Through/Charge actions have no tactical context for the DM to narrate

---

## Current Implementation

### Position & Range System (enemy_agent.py:29-188)

```python
# enemy_agent.py:29-35
class RingBand(Enum):
    ENGAGED = "Engaged"
    NEAR = "Near"
    FAR = "Far"
    EXTREME = "Extreme"

# enemy_agent.py:37-41
class Hemisphere(Enum):
    PC = "PC"
    ENEMY = "Enemy"
```

The battlefield is a concentric ring model:

```
         [Enemy Hemisphere]
    +=========================+
    |  Extreme Ring           |
    |   +-Far Ring-----+      |
    |   |+-Near Ring-+|       |
    |   ||  ENGAGED  ||       |  <-- Center line
    |   |+-Near Ring-+|       |
    |   +-Far Ring-----+      |
    |  Extreme Ring           |
    +=========================+
         [PC Hemisphere]
```

### Range Calculation (enemy_agent.py:86-148)

```python
# enemy_agent.py:86-124
def calculate_range(self, other: 'Position') -> Tuple[str, int]:
    """
    Calculate range to another position using Tactical Module v1.2.3 rules.

    Rules:
    1. Both in Engaged band -> "Engaged" (0 penalty)
    2. Same ring, same side -> "Melee" (0 penalty)
    3. Different rings or sides -> Count through center
       - 1 ring apart = "Near" (-2)
       - 2 rings apart = "Far" (-4)
       - 3+ rings apart = "Extreme" (-6)

    Returns:
        (range_name, attack_penalty)
    """
```

The `_count_rings_between()` method (enemy_agent.py:126-147) counts distance through the center point when positions are on different sides. For example, Near-PC to Near-Enemy = 2 rings apart (through Engaged) = Far range (-4 penalty).

### Position Movement Methods (enemy_agent.py:149-188)

```python
# enemy_agent.py:149-162
def shift_toward_center(self) -> Optional['Position']:
    """Move 1 ring toward Engaged band."""

# enemy_agent.py:164-177
def shift_away_from_center(self) -> Optional['Position']:
    """Move 1 ring away from Engaged band."""

# enemy_agent.py:179-188
def push_through(self) -> Optional['Position']:
    """Cross center line to opposite hemisphere (Major action)."""
    return Position(ring="Near", side=opposite_side)
```

### Enemy Movement Actions (enemy_combat.py:1470-1744)

```python
# enemy_combat.py:1470
def _execute_movement(self, enemy, declaration, resolution_state):
    """Execute Shift or Push_Through movement."""

# enemy_combat.py:1635
def _execute_charge(self, enemy, declaration, player_agents, mechanics_engine, resolution_state):
    """Execute Charge: Move to Engaged + attack in one action."""

# enemy_combat.py:1744
def _execute_retreat(self, enemy, declaration, resolution_state):
    """Execute Retreat: Move away from combat."""
```

Enemy agents can declare movement as their major action:
- **Shift:** Move 1 ring toward or away from center (minor action)
- **Push_Through:** Cross center line to opposite hemisphere (major action)
- **Charge:** Move to Engaged + attack in one action (major action, Agility+Athletics check)
- **Retreat:** Move 1 ring away from center, away from enemies
- **FLEE:** Attempt to leave combat entirely (moves to Extreme and exits)

### Player Position Fields (player_action.py)

```python
# player_action.py:198-201 (ExploreAction)
target_position: Optional[Position] = Field(
    default=None,
    description="Desired tactical position after movement (if applicable)"
)

# player_action.py:371-374 (CombatAction)
target_position: Optional[Position] = Field(
    default=None,
    description="Desired tactical position after action"
)
```

Players can specify `target_position` in several action types, but:
1. No prompt explains what positions are available or what they mean
2. No penalty/benefit for movement is communicated
3. Movement is always secondary to the primary action (no cost)

### Position Enum (shared_types.py:44-57)

```python
# shared_types.py:44-57
class Position(str, Enum):
    ENGAGED = "Engaged"
    NEAR_PC = "Near-PC"
    NEAR_ENEMY = "Near-Enemy"
    FAR_PC = "Far-PC"
    FAR_ENEMY = "Far-Enemy"
    EXTREME_PC = "Extreme-PC"
    EXTREME_ENEMY = "Extreme-Enemy"
```

Seven valid positions. The schema handles Unicode hyphen normalization (shared_types.py:59-100) because LLMs sometimes generate non-breaking hyphens.

### Tactical Doctrines (enemy_agent.py:202-261)

```python
# enemy_agent.py:202-251
TACTICAL_DOCTRINES = {
    "aggressive_melee": {"preferred_range": "Melee", ...},
    "defensive_ranged": {"preferred_range": "Far", ...},
    "tactical_ranged": {"preferred_range": "Near", ...},
    "extreme_range": {"preferred_range": "Extreme", ...},
    "ambush": {"preferred_range": "Melee", ...},
    "support": {"preferred_range": "Near", ...},
    "adaptive": {"preferred_range": "varies", ...},
    "berserk_void": {"preferred_range": "Melee", ...},
}
```

Enemies have preferred ranges based on doctrine. This information drives enemy AI decisions but is never shared with the DM or players.

### Where Position is Used in Combat (enemy_combat.py:1355-1364)

```python
# enemy_combat.py:1355-1364 (in _execute_suppress, same pattern in _execute_attack)
try:
    target_position = Position.from_string(str(target.position if hasattr(target, 'position') else "Near-PC"))
    range_name, range_penalty = enemy.position.calculate_range(target_position)
except:
    range_name, range_penalty = "Unknown", 0

attack_total = (attribute * skill) + weapon.attack + attack_roll + range_penalty
```

Range penalty is calculated and applied to enemy attack rolls. But the result (`range_name`, `range_penalty`) is only used internally -- not surfaced in narration or logged in structured output.

### PC Position Tracking (session.py:3538-3544)

```python
# session.py:3538-3544 (in combatant list generation)
if hasattr(agent, 'equipped_weapons'):
    # ... weapon context for combatant list ...
    if agent.equipped_weapons.get('primary'):
        wpn = agent.equipped_weapons['primary']
    # ...
# NOTE: agent.position is NOT included in the combatant list
```

The combatant list that goes into the DM prompt includes target IDs, names, health, and weapon info -- but NOT position. The DM does not know where anyone is on the battlefield.

---

## Design Decisions

User-confirmed:

1. **Agents know exact range bands from Tactical Module** -- qualitative ("Near", "Far") but sufficient information. Not exact meter distances.

2. **Qualitative but sufficient info** -- show range band names and penalty magnitudes, not grid coordinates or meter values.

3. **Movement allows avoidance of later resolutions** -- if a player moves early in the round, subsequent attacks against them should use the new position for range calculation.

4. **Misunderstanding corrected via prompting** -- agents confused about range bands should be guided by prompt content showing what each band means, not by additional schema constraints.

---

## Proposed Solution

### Phase 1: Range Penalty Display in Combat Prompts

**Goal:** Show each combatant's position and range penalty to every target in the combatant list.

**Files to modify:**
- `session.py:3538-3544` (combatant list generation)
- `dm.py` (DM resolution prompt -- add range context)
- Player action prompts (show available positions and costs)

**Implementation:**

Expand combatant list to include position and range:

```python
# session.py (combatant list generation, expanded)
def _build_combatant_list_with_range(self, acting_agent_id: str) -> str:
    """
    Build combatant list with range information for the acting agent.

    Shows each combatant with:
    - Target ID, name, faction, health
    - Position (ring-side)
    - Range from acting agent (Engaged/Near/Far/Extreme)
    - Attack penalty at that range
    """
    lines = []
    acting_position = self._get_agent_position(acting_agent_id)

    for combatant in self._get_all_combatants():
        target_position = self._get_agent_position(combatant.agent_id)
        range_name, range_penalty = acting_position.calculate_range(target_position)

        penalty_str = f"({range_penalty:+d})" if range_penalty != 0 else "(no penalty)"
        position_str = str(target_position) if target_position else "Unknown"

        line = (
            f"  {combatant.target_id} | {combatant.name} | "
            f"HP: {combatant.health}/{combatant.max_health} | "
            f"Position: {position_str} | "
            f"Range: {range_name} {penalty_str}"
        )
        lines.append(line)

    return "\n".join(lines)
```

Example output in prompt:

```
VALID TARGET IDS:
  tgt_7a3f | Street Gang Alpha | HP: 18/18 | Position: Near-Enemy | Range: Far (-4)
  tgt_2k9m | Street Gang Beta  | HP: 18/18 | Position: Far-Enemy  | Range: Extreme (-6)
  tgt_c3x1 | Enforcer Kael     | HP: 26/26 | Position: Near-PC    | Range: Engaged (no penalty)
```

### Phase 2: Movement Rules in Prompts

**Goal:** Teach agents what movement costs and options exist.

**Files to modify:**
- `prompts/claude/en/player/player_action_combat.yaml` (or new movement-specific prompt)
- `prompts/claude/en/dm/dm_combat.yaml` (range context for DM)

**Implementation:**

Add movement reference section to player combat prompt:

```yaml
# player_action_combat.yaml addition
## MOVEMENT OPTIONS

Movement is part of your action. You may include `target_position` to move during your action.

| Movement | Cost | Result |
|----------|------|--------|
| Shift (1 ring toward center) | Free with action | Move closer to enemies |
| Shift (1 ring away from center) | Free with action | Move farther from enemies |
| Charge (to Engaged) | Requires Agility+Athletics check | Move to melee range + attack |
| Push Through (cross center) | Major action (no attack) | Cross to enemy hemisphere |
| Retreat (1 ring away) | Free with action | Disengage from enemies |

**Range Penalties (applied to all ranged attacks):**
| Range | Penalty | When |
|-------|---------|------|
| Engaged/Melee | 0 | Same ring, same side (or both Engaged) |
| Near | -2 | 1 ring apart |
| Far | -4 | 2 rings apart |
| Extreme | -6 | 3+ rings apart |

**Trade-off:** Moving gives you better range for future actions but does NOT change
range penalties for attacks already targeting you THIS round (enemies already aimed).
```

### Phase 3: Position Display for Players

**Goal:** Players see their own position and distances to all targets before declaring actions.

**Files to modify:**
- `player.py` (player prompt building)
- `session.py` (context injection)

**Implementation:**

Add position context to player turn prompt:

```python
# player.py (in _build_turn_prompt or equivalent)
def _build_position_context(self) -> str:
    """
    Build position context showing player's current location and ranges.
    """
    if not hasattr(self, 'position') or not self.position:
        return ""

    lines = [f"**Your Position:** {self.position}"]

    # Calculate ranges to all known targets
    target_ranges = []
    if self.shared_state:
        for enemy in self.shared_state.get_active_enemies():
            range_name, penalty = self.position.calculate_range(enemy.position)
            target_ranges.append(f"  - {enemy.name}: {range_name} ({penalty:+d} to attack)")

        for player in self.shared_state.get_other_players(self.agent_id):
            if hasattr(player, 'position') and player.position:
                range_name, penalty = self.position.calculate_range(player.position)
                target_ranges.append(f"  - {player.character_state.name}: {range_name} (ally)")

    if target_ranges:
        lines.append("**Distances:**")
        lines.extend(target_ranges)

    return "\n".join(lines)
```

**Requires:** Player agents need a `position` attribute. Currently, players have no explicit position tracked at the session level. Enemy positions are tracked (enemy_agent.py:306) and NPC positions are tracked (npc_agent.py:282), but player positions are implicit.

Add player position initialization and tracking:

```python
# player.py addition
async def on_start(self):
    # ... existing initialization ...

    # Initialize tactical position (default: Near-PC for PCs)
    from .enemy_agent import Position as TacticalPosition
    self.position = TacticalPosition(ring="Near", side="PC")
```

Update position when DM resolves position changes:

```python
# dm.py (in position change processing)
def _apply_position_change(self, character_name: str, new_position_str: str):
    """Apply position change to the correct agent."""
    # Find player
    for player in self.shared_state.player_agents:
        if player.character_state.name == character_name:
            player.position = Position.from_string(new_position_str)
            return
    # Find enemy
    for enemy in self.shared_state.get_active_enemies():
        if enemy.name == character_name:
            enemy.position = Position.from_string(new_position_str)
            return
```

### Phase 4: Intra-Round Position Updates

**Goal:** When a player moves, subsequent attacks against them use the new position for range calculation.

**Files to modify:**
- `session.py` (resolution order tracking)
- `enemy_combat.py` (range recalculation for attacks)
- `dm.py` (position change application timing)

**Implementation:**

The key insight is that position changes must be applied *immediately* when resolved, not batched at end-of-round. The current resolution flow is:

1. All players declare actions (may include target_position)
2. All enemies declare actions (includes movement declarations)
3. DM resolves each action in initiative order
4. Position changes are narrated but may not be mechanically applied

The fix is to apply `PositionChange` effects from `ActionResolution` immediately during step 3:

```python
# dm.py (in action resolution processing)
async def _resolve_action(self, action, resolution):
    """Resolve a single action and apply effects immediately."""
    # ... existing resolution logic ...

    # Apply position changes IMMEDIATELY (affects subsequent resolutions)
    if resolution and resolution.effects:
        for pos_change in (resolution.effects.position_changes or []):
            self._apply_position_change(
                pos_change.character_name,
                pos_change.new_position.value
            )
            logger.info(
                f"Intra-round position update: {pos_change.character_name} "
                f"-> {pos_change.new_position.value}"
            )
```

This means that if Player A (initiative 18) moves from Near-PC to Far-PC, and Enemy B (initiative 12) attacks Player A later in the same round, Enemy B's attack uses Far range (-4 penalty) instead of Near range (-2 penalty).

### Phase 5: MoveAction Schema (Optional)

**Goal:** Add a dedicated movement action type for players who want to move without attacking.

**Files to modify:**
- `schemas/shared_types.py` (add MOVE to ActionType enum)
- `schemas/player_action.py` (add MoveAction schema)
- Action routing in session.py and dm.py

**Implementation:**

```python
# schemas/shared_types.py
class ActionType(str, Enum):
    # ... existing ...
    MOVE = "move"  # Dedicated movement action (trade attack for position)

# schemas/player_action.py
class MoveAction(PlayerActionBase):
    """
    MOVE action: Dedicated tactical repositioning.

    Trade your attack action for guaranteed movement to a new position.
    Unlike target_position on other actions, MoveAction always succeeds
    (no roll needed) and can move up to 2 rings in one action.

    Use when:
    - You need to cross the center line (Push Through)
    - You need to reach Extreme range for sniper advantage
    - You need to close to Engaged for melee combat
    - You want to move without the risk of failing another action
    """
    action_type: Literal[ActionType.MOVE] = ActionType.MOVE

    target_position: Position = Field(
        ...,
        description="REQUIRED: Position to move to. Must be within 2 rings of current position."
    )

    movement_type: Optional[Literal["shift", "push_through", "charge", "retreat"]] = Field(
        default="shift",
        description=(
            "How you're moving:\n"
            "- shift: Move 1 ring toward or away from center (safe)\n"
            "- push_through: Cross center line to opposite hemisphere (risky, Athletics check)\n"
            "- charge: Rush to Engaged range (risky, Athletics check, +2 melee next attack)\n"
            "- retreat: Move away while disengaging (safe, but enemies get opportunity attack)"
        )
    )
```

**Note:** This is Phase 5 (optional) because movement currently works via `target_position` on existing actions. A dedicated MoveAction provides clearer intent for ML training but is not required for the range awareness improvements in Phases 1-4.

---

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `session.py:3538-3544` | Add position and range to combatant list | 1 |
| `dm.py` (resolution prompt) | Add range context for DM narration | 1 |
| `prompts/claude/en/player/player_action_combat.yaml` | Movement rules reference table | 2 |
| `prompts/claude/en/dm/dm_combat.yaml` | Range context for DM | 2 |
| `player.py` | Add `position` attribute, build position context | 3 |
| `player.py:283` (on_start) | Initialize player position (Near-PC default) | 3 |
| `dm.py` | `_apply_position_change()` for immediate position updates | 4 |
| `session.py` | Resolution order tracking for intra-round updates | 4 |
| `enemy_combat.py` | Range recalculation using updated positions | 4 |
| `schemas/shared_types.py` | Add `MOVE` to ActionType enum (optional) | 5 |
| `schemas/player_action.py` | Add MoveAction schema (optional) | 5 |

---

## Test Plan

### Phase 1: Range Display Tests

```python
# tests/unit/test_range_display.py

def test_combatant_list_includes_position():
    """Combatant list should show position for each target."""
    combatant_list = build_combatant_list_with_range(
        acting_agent_id="player_01",
        acting_position=Position(ring="Near", side="PC"),
        combatants=[
            MockCombatant("tgt_7a3f", "Street Gang", position=Position(ring="Near", side="Enemy"))
        ]
    )
    assert "Position: Near-Enemy" in combatant_list

def test_combatant_list_includes_range_penalty():
    """Combatant list should show range penalty for each target."""
    combatant_list = build_combatant_list_with_range(
        acting_agent_id="player_01",
        acting_position=Position(ring="Near", side="PC"),
        combatants=[
            MockCombatant("tgt_7a3f", "Street Gang", position=Position(ring="Near", side="Enemy"))
        ]
    )
    # Near-PC to Near-Enemy = 2 rings apart = Far (-4)
    assert "Far" in combatant_list
    assert "-4" in combatant_list

def test_combatant_list_engaged_no_penalty():
    """Engaged combatants should show no penalty."""
    combatant_list = build_combatant_list_with_range(
        acting_agent_id="player_01",
        acting_position=Position(ring="Engaged", side="PC"),
        combatants=[
            MockCombatant("tgt_7a3f", "Thug", position=Position(ring="Engaged", side="Enemy"))
        ]
    )
    assert "Engaged" in combatant_list
    assert "no penalty" in combatant_list or "+0" in combatant_list

def test_combatant_list_extreme_penalty():
    """Extreme range should show -6 penalty."""
    combatant_list = build_combatant_list_with_range(
        acting_agent_id="player_01",
        acting_position=Position(ring="Far", side="PC"),
        combatants=[
            MockCombatant("tgt_sniper", "Sniper", position=Position(ring="Extreme", side="Enemy"))
        ]
    )
    # ring_order = ["Engaged", "Near", "Far", "Extreme"] → indices 0, 1, 2, 3
    # Far-PC (index 2) + Extreme-Enemy (index 3), different sides → distance = 2 + 3 = 5
    # Distance 5 → clamp to Extreme band → -6 penalty
    assert "Extreme" in combatant_list
    assert "-6" in combatant_list
```

### Phase 2: Movement Rules Tests

```python
# tests/unit/test_movement_rules.py

def test_movement_reference_in_combat_prompt():
    """Player combat prompt should include movement options table."""
    prompt = build_player_combat_prompt(...)
    assert "Movement" in prompt or "movement" in prompt
    assert "Shift" in prompt
    assert "Push Through" in prompt or "push_through" in prompt

def test_range_penalties_in_combat_prompt():
    """Player combat prompt should include range penalty table."""
    prompt = build_player_combat_prompt(...)
    assert "Near" in prompt
    assert "-2" in prompt
    assert "Far" in prompt
    assert "-4" in prompt
    assert "Extreme" in prompt
    assert "-6" in prompt
```

### Phase 3: Player Position Tests

```python
# tests/unit/test_player_position.py

def test_player_initialized_at_near_pc():
    """Players should start at Near-PC position."""
    player = create_test_player()
    assert hasattr(player, 'position')
    assert player.position.ring == "Near"
    assert player.position.side == "PC"

def test_position_context_shows_distances():
    """Position context should show range to all enemies."""
    player = create_test_player()
    shared_state = create_test_shared_state(
        enemies=[
            MockEnemy("Alpha", position=Position(ring="Near", side="Enemy")),
            MockEnemy("Beta", position=Position(ring="Far", side="Enemy")),
        ]
    )
    player.shared_state = shared_state
    context = player._build_position_context()
    assert "Alpha" in context
    assert "Beta" in context
    assert "Far" in context  # Near-PC to Near-Enemy = Far range

def test_position_context_empty_no_position():
    """Position context should be empty if player has no position."""
    player = create_test_player()
    delattr(player, 'position')
    context = player._build_position_context()
    assert context == ""
```

### Phase 4: Intra-Round Position Update Tests

```python
# tests/unit/test_intra_round_movement.py

def test_position_change_applied_immediately():
    """Position changes should take effect for subsequent resolutions."""
    player = create_test_player(position=Position(ring="Near", side="PC"))
    enemy = create_test_enemy(position=Position(ring="Near", side="Enemy"))

    # Initial range: Near-PC to Near-Enemy = Far (-4)
    range_name, penalty = player.position.calculate_range(enemy.position)
    assert range_name == "Far"
    assert penalty == -4

    # Player moves to Far-PC
    apply_position_change(player, "Far-PC")

    # New range: Far-PC to Near-Enemy = Extreme (-6)
    range_name, penalty = player.position.calculate_range(enemy.position)
    assert range_name == "Extreme"
    assert penalty == -6

def test_enemy_attack_uses_updated_position():
    """Enemy attack after player movement should use new range."""
    # Round order: Player (init 18) -> Enemy (init 12)
    player = create_test_player(position=Position(ring="Near", side="PC"))
    enemy = create_test_enemy(position=Position(ring="Near", side="Enemy"))

    # Player moves to Far-PC during their action
    apply_position_change(player, "Far-PC")

    # Enemy attacks player (should use Far-PC, not Near-PC)
    range_name, penalty = enemy.position.calculate_range(player.position)
    assert range_name == "Extreme"  # Near-Enemy to Far-PC = Extreme
    assert penalty == -6

def test_position_change_does_not_affect_earlier_resolutions():
    """Position changes should not retroactively affect already-resolved actions."""
    # This is guaranteed by sequential resolution -- earlier actions are already done
    # Test is conceptual: ensure no "undo" mechanism exists
    pass

def test_multiple_position_changes_in_round():
    """Multiple agents moving in one round should all be tracked."""
    player_a = create_test_player(position=Position(ring="Near", side="PC"))
    player_b = create_test_player(position=Position(ring="Near", side="PC"))

    apply_position_change(player_a, "Far-PC")
    apply_position_change(player_b, "Engaged")

    assert player_a.position.ring == "Far"
    assert player_b.position.ring == "Engaged"
```

### Phase 5: MoveAction Schema Tests (Optional)

```python
# tests/unit/test_move_action.py

def test_move_action_requires_target_position():
    """MoveAction should require target_position."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        MoveAction(
            intent="Move to better cover position",
            description="Repositioning to get a clear line of fire.",
            attribute="Agility",
            skill="Athletics",
            difficulty_estimate=10,
            difficulty_justification="Simple movement, no obstacles",
            # Missing target_position
        )

def test_move_action_accepts_valid_position():
    """MoveAction should accept valid Position enum values."""
    action = MoveAction(
        intent="Move to far range for sniper advantage",
        description="Falling back to use superior range discipline.",
        attribute="Agility",
        skill="Athletics",
        difficulty_estimate=10,
        difficulty_justification="Open ground, easy retreat",
        target_position=Position.FAR_PC,
        movement_type="retreat"
    )
    assert action.target_position == Position.FAR_PC
    assert action.movement_type == "retreat"

def test_move_action_in_discriminated_union():
    """MoveAction should be routable via PlayerActionDetails union."""
    data = {
        "intent": "Push through to enemy side",
        "description": "Sprinting across the center line to reach the enemy hemisphere.",
        "attribute": "Agility",
        "skill": "Athletics",
        "difficulty_estimate": 18,
        "difficulty_justification": "Crossing open ground under fire",
        "action_type": "move",
        "target_position": "Near-Enemy",
        "movement_type": "push_through"
    }
    action = PlayerActionDetails(**data)
    assert isinstance(action, MoveAction)

def test_move_action_type_in_enum():
    """ActionType enum should include MOVE."""
    assert ActionType.MOVE == "move"
```

---

## Dependencies

None. This feature builds on existing infrastructure (Position class, range calculation, combatant lists) without requiring any other v2 features.

**Interacts with but does not depend on:**
- 08_SUPPRESSION_NONLETHAL (suppressive fire range interacts with movement -- suppression at Far range is different from suppression at Near range)
- 07_INVENTORY_EQUIPMENT Phase 2 (weapon stats in WEAPON CONTEXT could include range stats like short_range/medium_range/long_range for more detailed range guidance)

---

## Open Questions

### Q1: Should PC positions be tracked explicitly or inferred from target_position?

**Current recommendation:** Explicitly tracked. Add `position` attribute to PlayerAgent (Phase 3), initialized to Near-PC by default. The DM updates it via PositionChange effects in ActionResolution. This is consistent with how enemy positions work (enemy_agent.py:306).

**Alternative:** Infer from `target_position` on the most recent action. Simpler but loses position tracking between rounds (what if the player doesn't specify target_position?).

### Q2: Should movement cost an action or be free?

**Current recommendation:** Movement via `target_position` on an existing action is free (as it is now). Dedicated MoveAction (Phase 5) costs the player's major action but allows 2-ring movement and guarantees success. This creates a meaningful trade-off: move for free (1 ring, might fail) or dedicate your action to movement (2 rings, guaranteed).

**Alternative:** All movement is free. Simple but removes tactical trade-offs. Players can always be at optimal range with no cost.

### Q3: Should range penalties apply to melee attacks?

**Current recommendation:** No. Melee attacks at non-Engaged range should fail (can't swing a sword from Far range), not suffer a penalty. The action should be invalidated or the player should be told to Charge first. This is consistent with YAGS rules where melee requires Engaged/Melee range.

### Q4: How detailed should range information be for players?

**Current recommendation:** Qualitative range bands (Engaged/Near/Far/Extreme) with numeric penalties (-2/-4/-6). Not meter distances. Not weapon-specific effective ranges (even though weapon stats include short_range/medium_range/long_range). The qualitative system matches the Tactical Module v1.2.3 design and is simpler for LLMs to process.

**Future extension:** Weapon-specific range suitability (e.g., "Pistol effective at Near, reduced at Far, useless at Extreme" based on weapon.short_range/medium_range/long_range). Deferred to avoid prompt bloat.

### Q5: What should the default player position be?

**Current recommendation:** Near-PC. Most combat scenarios start with PCs in the Near band on the PC hemisphere. This is consistent with the session config initial_enemies that typically spawn at Near-Enemy.

**Alternative:** Configurable via session config. Add `starting_position` to character config:
```json
{
    "name": "Sniper Sara",
    "starting_position": "Far-PC"
}
```

This would allow scenario designers to place characters at specific positions, but adds config complexity. Deferred to Phase 5.

### Q6: How should the DM narrate range in resolutions?

The DM currently does not know about range. With Phase 1, the DM will see range in the combatant list. We should add guidance:

```yaml
# dm_resolution_combat.yaml (range narration guidance)
# Use range context to describe the combat:
# - Engaged: Close quarters, hand-to-hand, point-blank. "Lunges at", "grapples with"
# - Near: Close combat, pistol range. "Fires at close range", "dashes toward"
# - Far: Moderate distance, rifle range. "Takes careful aim", "exchanges fire across"
# - Extreme: Long distance, sniper range. "Barely visible in the distance", "the shot echoes across"
```

This is a prompt-only change (no code required) and can be included in Phase 2.

---

## Migration Notes

### Session Config Changes

Phase 5 (optional): New `ActionType.MOVE` added to the enum. Old configs are unaffected because they never reference this action type.

Phase 3: Optional `starting_position` in character config. Old configs default to Near-PC.

### JSONL Logging Impact

Phase 4: Position changes are already logged via `PositionChange` in ActionResolution effects. No new event types needed. Existing analysis tools (`analyze_session.py`) already parse position_changes in effects.

Phase 5: New `action_type: "move"` in action_declaration events. Additive change.

### Backward Compatibility

- Phase 1: Combatant list expansion is additive (more info, no info removed)
- Phase 2: Prompt additions are additive
- Phase 3: Player `position` attribute is new. Code that does not access `player.position` is unaffected. `hasattr(player, 'position')` guards used where needed.
- Phase 4: Position change application timing moves from end-of-round to immediate. This changes behavior (subsequent attacks use new range) but is the correct behavior per game rules.
- Phase 5: New ActionType and schema. Discriminated union is extended (additive). Old replays parse correctly (no MOVE actions in old data).
