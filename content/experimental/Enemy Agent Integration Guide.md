# Enemy Agent System - Integration Guide

**Status:** Phase 2 Complete - Ready for Integration
**Date:** 2025-10-22
**Author:** Three Rivers AI Nexus

---

## Overview

The Enemy Agent System is now ready for integration into the existing multi-agent combat flow. This guide explains how to integrate `EnemyCombatManager` into `session.py` and `dm.py`.

## Phase 2 Modules

### `enemy_combat.py` (690 lines)

**Purpose:** Combat integration bridge between enemy agents and existing combat system.

**Key Classes:**
- `EnemyCombatManager`: Main manager for enemy combat lifecycle
- `EnemyDeclaration`: Parsed enemy tactical declaration
- `parse_enemy_declaration()`: Parse LLM output into structured format

**Capabilities:**
- Process DM spawn/despawn markers
- Generate initiative entries for enemies
- Generate tactical prompts during declaration
- Parse enemy declarations
- Execute enemy actions (attack, movement, charge, retreat, grenade)
- Cleanup (attrition, despawn, loot)

---

## Integration Steps

### 1. Initialize Enemy Combat Manager in Session

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** In `GameSession.__init__()` method

```python
from .enemy_combat import EnemyCombatManager

class GameSession:
    def __init__(self, config: Dict[str, Any]):
        # ... existing initialization ...

        # Initialize enemy combat manager
        self.enemy_combat = EnemyCombatManager()
        self.enemy_combat.initialize(config)

        logger.info(f"Enemy combat: {'ENABLED' if self.enemy_combat.enabled else 'DISABLED'}")
```

---

### 2. Process Spawn Markers in DM Narration

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** After DM narration is received

**Current Code:** (Approximate location - after DM turn)
```python
async def _run_dm_turn(self):
    # ... DM generates narration ...
    narration = dm_response.get('narration', '')

    # **ADD HERE: Process spawn markers**
    if self.enemy_combat.enabled:
        spawn_notifications = self.enemy_combat.process_dm_narration(narration)
        for notification in spawn_notifications:
            print(f"\n{notification}")
```

---

### 3. Integrate Enemies into Initiative Order

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** In `_run_initiative_round()` method

**Current Code:**
```python
async def _run_initiative_round(self):
    player_agents = [a for a in self.agents if isinstance(a, PlayerAgent)]
    if not player_agents:
        return

    # Calculate initiative for each player
    initiative_order = []
    mechanics = self.shared_state.get_mechanics_engine()

    for player_agent in player_agents:
        agility = player_agent.character_state.attributes.get('Agility', 3)
        initiative = mechanics.calculate_initiative(agility)
        initiative_order.append((initiative, player_agent))
```

**MODIFIED Code:**
```python
async def _run_initiative_round(self):
    player_agents = [a for a in self.agents if isinstance(a, PlayerAgent)]
    if not player_agents:
        return

    # Calculate initiative for players
    initiative_order = []
    mechanics = self.shared_state.get_mechanics_engine()

    for player_agent in player_agents:
        agility = player_agent.character_state.attributes.get('Agility', 3)
        initiative = mechanics.calculate_initiative(agility)
        initiative_order.append((initiative, 'player', player_agent))
        print(f"[{player_agent.character_state.name}] Initiative: {initiative}")

    # **ADD: Get enemy initiative entries**
    if self.enemy_combat.enabled:
        enemy_entries = self.enemy_combat.get_initiative_entries()
        for init, enemy in enemy_entries:
            initiative_order.append((init, 'enemy', enemy))
            print(f"[{enemy.name}] Initiative: {init}")

    # Sort by initiative (highest first)
    initiative_order.sort(key=lambda x: x[0], reverse=True)
```

---

### 4. Enemy Declaration Phase

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** In `_run_initiative_round()`, after PC declarations

**Current Code:**
```python
    # PHASE 1: DECLARATIONS (slowest → fastest)
    print("\n=== Declaration Phase ===")

    for initiative_score, player_agent in reversed(initiative_order):
        print(f"\n[{player_agent.character_state.name}] declaring (initiative {initiative_score})...")
        # ... PC declaration logic ...
```

**MODIFIED Code:**
```python
    # PHASE 1: DECLARATIONS (slowest → fastest)
    print("\n=== Declaration Phase ===")

    for initiative_score, agent_type, agent in reversed(initiative_order):
        if agent_type == 'player':
            print(f"\n[{agent.character_state.name}] declaring (initiative {initiative_score})...")
            # ... existing PC declaration logic ...

        elif agent_type == 'enemy':
            print(f"\n[{agent.name}] (ENEMY) declaring (initiative {initiative_score})...")

            # **ADD: Enemy declaration**
            if self.enemy_combat.enabled:
                # Get available tactical tokens
                available_tokens = mechanics.get_unclaimed_tokens() if mechanics else []

                # Get LLM client (from DM agent)
                dm_agent = next((a for a in self.agents if isinstance(a, AIDMAgent)), None)
                if dm_agent and hasattr(dm_agent, 'llm_client'):
                    enemy_declarations = await self.enemy_combat.declare_actions(
                        player_agents=player_agents,
                        available_tokens=available_tokens,
                        llm_client=dm_agent.llm_client
                    )

                    # Log declarations
                    if mechanics and mechanics.jsonl_logger:
                        for decl in enemy_declarations:
                            mechanics.jsonl_logger.log_action_declaration(
                                player_id=decl['agent_id'],
                                character_name=decl['character_name'],
                                initiative=decl['initiative'],
                                action={'major_action': decl['major_action'], 'target': decl['target']},
                                round_num=mechanics.current_round
                            )
```

---

### 5. Enemy Action Execution

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** In `_run_initiative_round()`, resolution phase

**Current Code:**
```python
    # PHASE 2: RESOLUTION (fastest → slowest)
    print("\n=== Resolution Phase ===")
    print("DM adjudicating all actions...")

    # Build list of all actions
    actions_for_adjudication = []
    for initiative_score, player_agent in initiative_order:
        if player_agent.agent_id in self._declared_actions:
            buffered_action = self._declared_actions[player_agent.agent_id]
            actions_for_adjudication.append({
                'player_id': player_agent.agent_id,
                'character_name': player_agent.character_state.name,
                'initiative': initiative_score,
                'action': buffered_action['action']
            })

    # Send to DM for adjudication
    # ... DM adjudication logic ...
```

**MODIFIED Code:**
```python
    # PHASE 2: RESOLUTION (fastest → slowest)
    print("\n=== Resolution Phase ===")
    print("Executing all actions...")

    # Execute actions in initiative order (descending)
    for initiative_score, agent_type, agent in initiative_order:
        if agent_type == 'player':
            # Existing PC action execution
            if agent.agent_id in self._declared_actions:
                buffered_action = self._declared_actions[agent.agent_id]
                # ... existing DM adjudication ...

        elif agent_type == 'enemy':
            # **ADD: Enemy action execution**
            if self.enemy_combat.enabled:
                result = self.enemy_combat.execute_enemy_action(
                    enemy_id=agent.agent_id,
                    player_agents=player_agents,
                    mechanics_engine=mechanics
                )

                if result:
                    print(f"\n[{result['character_name']}] {result['narration']}")

                    # Log result
                    if mechanics and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_action_resolution(
                            player_id=result['enemy_id'],
                            character_name=result['character_name'],
                            action_result=result,
                            round_num=mechanics.current_round
                        )
```

---

### 6. CRITICAL: Using ResolutionState for Declare/Resolve Cycle

**⚠️ IMPORTANT:** The declare/resolve cycle requires proper action invalidation handling. Declarations are **intentions**, but resolution phase determines **reality**. Earlier actors (higher initiative) can invalidate later actors' declared actions.

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** In resolution phase loop

**Import Required:**
```python
from .tactical_resolution import ResolutionState
```

**Implementation:**
```python
    # PHASE 2: RESOLUTION (fastest → slowest)
    print("\n=== Resolution Phase ===")

    # **CRITICAL: Create resolution state tracker**
    from .tactical_resolution import ResolutionState
    resolution_state = ResolutionState()

    # Execute actions in initiative order (descending)
    for initiative_score, agent_type, agent in initiative_order:
        if agent_type == 'player':
            # PC action execution
            if agent.agent_id in self._declared_actions:
                buffered_action = self._declared_actions[agent.agent_id]

                # **VALIDATE PC ACTION PREREQUISITES**
                # Example: Check if target still alive, token still available
                # (Implementation depends on existing PC action system)

                # Execute PC action via DM adjudication
                # ... existing logic ...

                # **UPDATE RESOLUTION STATE**
                # If PC claims a token:
                #   resolution_state.claim_token(token_name, agent.agent_id)
                # If PC defeats an enemy:
                #   resolution_state.mark_defeated(enemy_id)
                # If PC moves:
                #   resolution_state.record_position_change(agent.agent_id, new_pos)

        elif agent_type == 'enemy':
            # **ENEMY ACTION EXECUTION WITH RESOLUTION STATE**
            if self.enemy_combat.enabled:
                result = self.enemy_combat.execute_enemy_action(
                    enemy_id=agent.agent_id,
                    player_agents=player_agents,
                    mechanics_engine=mechanics,
                    resolution_state=resolution_state  # ← Pass state tracker
                )

                if result:
                    # Check if action was invalidated
                    if result.get('result') == 'invalidated':
                        print(f"\n⚠️  {result['narration']}")
                    else:
                        print(f"\n[{result['character_name']}] {result['narration']}")

                    # Log result
                    if mechanics and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_action_resolution(
                            player_id=result['enemy_id'],
                            character_name=result['character_name'],
                            action_result=result,
                            round_num=mechanics.current_round
                        )
```

**Why This Matters:**

The user's scenario example:
> "Player A declares defense token 1, enemy A chooses to shoot player A, enemy B goes for defense token 1. The resolution phase will matter for who ends up with token 1"

**Declaration Phase (ascending initiative: 12, 18, 22):**
1. Player A (init 12): "Claim Cover token"
2. Enemy A (init 18): "Attack Player A"
3. Enemy B (init 22): "Claim Cover token"

**Resolution Phase (descending initiative: 22, 18, 12):**
1. Enemy B (22): Claims Cover token → **SUCCESS**, `resolution_state.claim_token("Cover", "enemy_b_001")`
2. Enemy A (18): Attacks Player A → executes normally, might kill Player A
3. Player A (12): Tries to claim Cover → **FAILS** - "❌ Player A cannot claim Cover - enemy_b_001 claimed it first"

**Key Features:**
- `ResolutionState` tracks claimed tokens, defeated combatants, position changes
- `ActionValidator` checks prerequisites before executing actions
- `generate_invalidation_message()` provides narrative feedback
- Earlier actors' state changes invalidate later actors' declared actions

**Action Invalidation Examples:**
- ❌ Target was killed by earlier actor → attack fails
- ❌ Token was claimed by earlier actor → claim fails
- ❌ Actor was killed before their turn → all actions fail
- ❌ Target moved out of range → attack might fail (if implemented)

---

### 7. Cleanup Phase

**File:** `scripts/aeonisk/multiagent/session.py`

**Location:** After resolution phase, before next round

**ADD New Code:**
```python
    # PHASE 3: CLEANUP
    if self.enemy_combat.enabled:
        cleanup_events = self.enemy_combat.cleanup_round()

        for event in cleanup_events:
            print(f"\n[CLEANUP] {event['narration']}")

            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_event(
                    event_type=event['type'],
                    data=event,
                    round_num=mechanics.current_round
                )
```

---

## Configuration

### Session Config Requirements

**File:** `session_config_tactical_example.json`

```json
{
  "tactical_module_enabled": true,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "allow_groups": true,
    "max_enemies_per_combat": 20,
    "shared_intel_enabled": true,
    "auto_execute_reactions": true,
    "loot_suggestions_enabled": true,
    "void_tracking_enabled": true
  }
}
```

---

## DM Usage

### Spawning Enemies

DM includes spawn markers in narration:

```
"Three armed guards burst through the door!"
[SPAWN_ENEMY: Security Guards | grunt | 3 | Near-Enemy | aggressive_melee]
```

**Syntax:**
```
[SPAWN_ENEMY: name | template | count | position | tactics]
```

**Available Templates:**
- `grunt`: Basic combatants
- `elite`: Veterans
- `sniper`: Long-range specialists
- `boss`: Major threats
- `void_cultist`: Ritual specialists
- `enforcer`: Melee specialists
- `support`: Tactical support
- `ambusher`: Infiltration specialists

**Available Tactics:**
- `aggressive_melee`: Close and engage
- `defensive_ranged`: Maintain distance
- `tactical_ranged`: Balanced positioning
- `extreme_range`: Sniper tactics
- `ambush`: Infiltrate enemy side
- `support`: Covering fire
- `adaptive`: Dynamic response

**Positions:**
- `Engaged`: Center action zone
- `Near-PC`, `Near-Enemy`: First ring
- `Far-PC`, `Far-Enemy`: Second ring
- `Extreme-PC`, `Extreme-Enemy`: Outermost ring

### Manual Despawn

```
"The sniper falls back through the maintenance shaft."
[DESPAWN_ENEMY: enemy_sniper_001 | tactical withdrawal]
```

---

## Combat Flow Example

### Round 1

**1. DM Narration with Spawn:**
```
DM: "Armed enforcers emerge from the cargo containers!"
[SPAWN_ENEMY: Syndicate Enforcers | grunt | 3 | Near-Enemy | aggressive_melee]
```

**System:**
```
⚔️  Syndicate Enforcers spawned! (3 units, 25 HP, Near-Enemy, tactics: aggressive_melee)
```

**2. Initiative Order:**
```
[Echo] Initiative: 28
[Syndicate Enforcers] Initiative: 22
[Sable] Initiative: 18
[Nyx] Initiative: 12
```

**3. Declaration Phase (ascending):**
```
[Nyx] declaring (initiative 12)...
  → Moving to Near-PC, attacking Enforcers, Defence Token on Enforcers

[Sable] declaring (initiative 18)...
  → Charging Enforcers, Defence Token on Enforcers

[Syndicate Enforcers] (ENEMY) declaring (initiative 22)...
  [LLM generates tactical prompt...]
  → DEFENCE_TOKEN: pc_sable_001
  → MAJOR_ACTION: Attack
  → TARGET: pc_sable_001
  → WEAPON: Rifle
  → TACTICAL_REASONING: Sable charging is primary threat, coordinating fire

[Echo] declaring (initiative 28)...
  → Covering Sable, rifle aimed at Enforcers, Defence Token on Enforcers
```

**4. Resolution Phase (descending):**
```
[Echo] Attacks Enforcers
  → Roll: 30, Hit! Damage: 15
  → Enforcers: 25 → 10 HP

[Syndicate Enforcers] Attack Sable (coordinated fire, +4 group bonus)
  → Roll: 20 vs Sable defence 24, MISS

[Sable] Charges Enforcers
  → Roll: 38, Hit! Damage: 26
  → Enforcers: 10 → 0 HP

[Nyx] Action resolves...
```

**5. Cleanup Phase:**
```
[CLEANUP] Syndicate Enforcers defeated! Loot from Syndicate Enforcers: Pistol (fair), Baton (damaged), Light Combat Armor (damaged), 45 credits
```

---

## Testing Checklist

- [ ] Enemy agents spawn from DM markers
- [ ] Enemies roll initiative and appear in initiative order
- [ ] Enemies receive tactical prompts during declaration
- [ ] Enemy declarations parse correctly
- [ ] Enemy actions execute (attack, movement, retreat)
- [ ] YAGS combat mechanics work (attack rolls, damage, soak)
- [ ] Range calculation uses v1.2.3 rules
- [ ] Group mechanics work (damage bonus, attrition)
- [ ] Defeated enemies despawn and generate loot
- [ ] Void tracking works for enemies
- [ ] Shared intel appears in subsequent prompts
- [ ] Cleanup phase runs correctly

---

## Known Limitations

**Phase 2 provides basic combat integration. Future phases will add:**

**Phase 3 - Advanced Group Mechanics:**
- Refined attrition calculations
- Unit count display in prompts
- Group coordination bonuses

**Phase 4 - Tactical Depth:**
- Doctrine-specific action suggestions
- Advanced threat analysis
- Auto-reaction system (parry, overwatch)
- Defence Token optimization

**Phase 5 - Void & Polish:**
- Void possession transformations
- Advanced loot generation
- Prompt optimization (token reduction)
- Performance tuning

**Current Simplifications:**
- Enemies use simplified attack resolution (vs passive defence 15)
- Reactions are not fully implemented
- Grenade AoE damage is not fully calculated (targets identified, but damage/saves not rolled)

**Declare/Resolve Cycle Features (NEW):**
- ✓ Action prerequisite validation (target alive, actor alive, token available)
- ✓ Tactical token claiming with initiative-based resolution
- ✓ Action invalidation messages
- ✓ ResolutionState tracking for all state changes during resolution

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                         GameSession                           │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           _run_initiative_round()                       │  │
│  │                                                          │  │
│  │  1. Calculate Initiative                                │  │
│  │     - Players: mechanics.calculate_initiative()         │  │
│  │     - Enemies: enemy_combat.get_initiative_entries()    │  │
│  │     - Sort combined list (descending)                   │  │
│  │                                                          │  │
│  │  2. Declaration Phase (ascending initiative)            │  │
│  │     - Players: existing PC declaration logic            │  │
│  │     - Enemies: enemy_combat.declare_actions()           │  │
│  │                 ↓                                        │  │
│  │          generate_tactical_prompt()                     │  │
│  │                 ↓                                        │  │
│  │          LLM generates declaration                      │  │
│  │                 ↓                                        │  │
│  │          parse_enemy_declaration()                      │  │
│  │                                                          │  │
│  │  3. Resolution Phase (descending initiative)            │  │
│  │     - Players: existing DM adjudication                 │  │
│  │     - Enemies: enemy_combat.execute_enemy_action()      │  │
│  │                 (with ResolutionState tracking)         │  │
│  │                 ↓                                        │  │
│  │          _execute_attack()                              │  │
│  │          _execute_claim_token() ← NEW                   │  │
│  │          _execute_movement()                            │  │
│  │          _execute_charge()                              │  │
│  │          _execute_retreat()                             │  │
│  │          _execute_grenade()                             │  │
│  │                 ↓                                        │  │
│  │          ActionValidator checks prerequisites           │  │
│  │          ResolutionState tracks state changes           │  │
│  │                                                          │  │
│  │  4. Cleanup Phase                                       │  │
│  │     - enemy_combat.cleanup_round()                      │  │
│  │                 ↓                                        │  │
│  │          apply_group_attrition()                        │  │
│  │          auto_despawn_defeated()                        │  │
│  │          suggest_loot()                                 │  │
│  │          clear_old_intel()                              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           _run_dm_turn()                                │  │
│  │                                                          │  │
│  │  - DM generates narration                               │  │
│  │  - enemy_combat.process_dm_narration()                  │  │
│  │         ↓                                                │  │
│  │    spawn_from_marker()                                  │  │
│  │    despawn_from_markers()                               │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                   EnemyCombatManager                          │
│                                                               │
│  Properties:                                                  │
│  - enemy_agents: List[EnemyAgent]                            │
│  - shared_intel: SharedIntel                                 │
│  - enemy_declarations: Dict[str, EnemyDeclaration]           │
│  - current_round: int                                        │
│  - enabled: bool                                             │
│                                                               │
│  Methods:                                                     │
│  - initialize(config)                                        │
│  - process_dm_narration(text) → spawn/despawn notifications  │
│  - get_initiative_entries() → List[(init, enemy)]            │
│  - declare_actions(players, tokens, llm) → declarations      │
│  - execute_enemy_action(enemy_id, players, mechanics)        │
│  - cleanup_round() → cleanup events                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Summary

Phase 2 provides a complete combat integration system that is **ready to plug into the existing session flow**. The `EnemyCombatManager` handles all enemy combat logic and provides clean integration points for:

1. Spawn/despawn processing
2. Initiative ordering
3. Declaration generation
4. Action execution
5. Cleanup

**Next step:** Modify `session.py` following the integration steps above, then test with `session_config_tactical_example.json`.

---

**End of Integration Guide**
