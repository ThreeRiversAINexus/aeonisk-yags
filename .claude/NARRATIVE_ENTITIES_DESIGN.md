# Narrative Entities Design

**Status**: Planning (Future Phase - Split from NPC work)
**Created**: 2025-11-04
**Priority**: Low (phantom targeting acceptable for now, can defer)

## Executive Summary

This document outlines a system for targetable environmental objects that players can interact with mechanically. Examples include doors, terminals, cargo crates, cryo-pods, and other environmental elements that affect gameplay.

**Key insight**: Narrative entities are **environment**, not **agents**. They don't act, don't have agency, and serve as mechanical targets for player/NPC/enemy actions.

## Motivation

### Current Issue: Phantom Targeting

Players reference narrative elements in their actions:
- "I hack the security terminal"
- "I blow open the vault door"
- "I secure the cargo crates"
- "I destroy the Exchange crystal"

**Problem**: These objects don't exist as targetable entities.

**Current workaround**: DM interprets narrative intent, resolves freeform.

**Limitations**:
- No persistent state tracking (is door locked? hacked? destroyed?)
- No structured output (DM invents results)
- No ML training data for environmental interactions
- Replay ambiguity (what was the door's state?)

### Why Split from NPC Work?

**Different use case**:
- NPCs are agents with stats, LLM clients, agency
- Entities are objects with state, no agency

**Can implement independently**:
- NPC system doesn't depend on entities
- Entity system doesn't depend on NPCs
- Clean separation of concerns

**Lower priority**:
- Phantom targeting works for current ML training goals
- NPCs solve more pressing gameplay issues (de-escalation, healing)
- Can add entities later without architectural changes

## Design Goals

### Primary Goal: Persistent Environmental State

Track mechanical state of environmental objects:
- Doors: locked/unlocked/hacked/destroyed
- Terminals: online/offline/hacked/corrupted
- Cargo: sealed/opened/secured/destroyed
- Cryo-pods: stable/failing/opened/corrupted

### Secondary Goals
1. **Structured interactions** - DM uses schemas to mark entity state changes
2. **ML training data** - Log environmental interactions for dataset
3. **Replay support** - Entity state changes logged in JSONL
4. **Destructible objects** - Some entities have HP-equivalent (structural_integrity)

## Proposed Architecture

### NarrativeEntity Structure

```python
class NarrativeEntity:
    """
    Environmental object tracked for mechanical interaction.

    Examples:
    - "Vault Door" (locked/hacked/blown open)
    - "Security Terminal" (offline/hacked/overloaded)
    - "Cargo Crate" (sealed/opened/destroyed)
    - "Cryo-Pod" (stable/failing/corrupted)
    - "Exchange Crystal" (intact/cracked/shattered)

    Entities:
    - Have state (tracked in state_dict)
    - Can have conditions (e.g., "Locked", "Hacked")
    - Can be damaged (optional structural_integrity)
    - Cannot act (no LLM, no agency)
    """
    # Identity
    entity_id: str                     # "entity_<name>_<seq>"
    name: str
    description: str

    # State tracking
    state_dict: Dict[str, Any]         # Custom state (e.g., {"locked": True})
    conditions: List[Condition]        # Track mechanical state

    # Optional: damage tracking for destructible objects
    structural_integrity: Optional[int] = None
    max_integrity: Optional[int] = None

    # Metadata
    entity_type: str = "object"        # Could extend: "door", "terminal", "cargo", etc.
    destructible: bool = False
```

**Lightweight design**: Entities are just named targets with state. DM interprets interactions narratively.

**No combat stats**: Entities don't have health/soak/skills like NPCs. They have structural_integrity if destructible.

### State Tracking Examples

**Vault Door**:
```python
door = NarrativeEntity(
    entity_id="entity_vault_door_1",
    name="Vault Door",
    description="Reinforced titanium door with electronic lock",
    state_dict={
        "locked": True,
        "alarm_active": True,
        "hack_attempts": 0
    },
    structural_integrity=50,
    max_integrity=50,
    destructible=True
)

# Player hacks door
door.state_dict["locked"] = False
door.state_dict["hack_attempts"] = 1
door.conditions.append(Condition(name="Hacked", penalty=0))

# Player breaches door with explosives
door.structural_integrity -= 30
if door.structural_integrity <= 0:
    door.conditions.append(Condition(name="Destroyed", penalty=-999))
```

**Security Terminal**:
```python
terminal = NarrativeEntity(
    entity_id="entity_terminal_1",
    name="Security Terminal",
    description="Wall-mounted terminal controlling station defenses",
    state_dict={
        "active": True,
        "security_level": 3,
        "alarm_enabled": True
    },
    structural_integrity=None,  # Not destructible
    destructible=False
)

# Player hacks terminal
terminal.state_dict["security_level"] = 0
terminal.state_dict["alarm_enabled"] = False
terminal.conditions.append(Condition(name="Compromised", penalty=0))
```

**Cargo Crates**:
```python
crate = NarrativeEntity(
    entity_id="entity_cargo_1",
    name="Soulcredit Cargo",
    description="Sealed container of ACG Soulcredit reserves",
    state_dict={
        "sealed": True,
        "contents_value": 500,  # Soulcredit
        "secured_by": "ACG"
    },
    structural_integrity=10,
    max_integrity=10,
    destructible=True
)

# Player opens crate
crate.state_dict["sealed"] = False
# (DM narration grants Soulcredit reward)
```

## Targeting System

**Who can target entities**:
```
Player   → Entity (yes)
Enemy    → Entity (rarely, DM decides)
NPC      → Entity (no, NPCs can't act on environment)
```

**Validation in `target_ids.py`**:
```python
def can_target_entity(self, source_id: str, entity_id: str) -> bool:
    """
    Check if source agent can target entity.

    Rules:
    - Players can target entities
    - Enemies rarely target entities (DM decides)
    - NPCs cannot target (non-combatants)
    """
    source = self.resolve_target(source_id)

    # Players can target entities
    if self.is_player(source_id):
        return True

    # Enemies might target entities (context-dependent)
    if self.is_enemy(source_id):
        # DM decides (e.g., enemy destroys evidence)
        return True  # Permissive, DM validates in resolution

    # NPCs cannot act on entities
    return False
```

**Entity IDs**: `entity_<name>_<seq>` format distinguishes from agents.

## Structured Output Schema

### EntitySpawn

```python
class EntitySpawn(BaseModel):
    """
    Spawn a targetable environmental object.

    Use when:
    - Players need to interact with specific objects
    - Environmental obstacles have mechanical state
    - Scene has destructible/hackable/openable elements

    Example:
    ```python
    entity = EntitySpawn(
        name="Vault Door",
        description="Reinforced titanium door, electronic lock",
        state={"locked": True, "alarm_active": False},
        structural_integrity=50
    )
    ```
    """
    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., min_length=20, max_length=300)
    entity_type: str = Field("object", description="Type: door, terminal, cargo, etc.")
    state: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom state tracking (locked, hacked, etc.)"
    )
    structural_integrity: Optional[int] = Field(
        None,
        ge=0,
        description="HP-equivalent for destructible objects"
    )
    destructible: bool = Field(
        False,
        description="Can this entity be destroyed?"
    )
```

### EntityStateChange

```python
class EntityStateChange(BaseModel):
    """
    Track changes to entity state.

    Example:
    ```python
    change = EntityStateChange(
        entity_id="entity_vault_door_1",
        state_changes={"locked": False},
        conditions_added=["Hacked"],
        structural_damage=0
    )
    ```
    """
    entity_id: str = Field(..., description="Entity being modified")
    state_changes: Dict[str, Any] = Field(
        default_factory=dict,
        description="State fields that changed"
    )
    conditions_added: List[str] = Field(
        default_factory=list,
        description="New conditions applied"
    )
    structural_damage: int = Field(
        0,
        ge=0,
        description="Damage dealt to structural_integrity"
    )
    narrative: str = Field(
        ...,
        description="How entity state changed narratively"
    )
```

### StoryAdvancement Extension

```python
class StoryAdvancement(BaseModel):
    # ... existing fields

    # NEW: Entity spawning
    entities_spawned: Optional[List[EntitySpawn]] = None

    # NEW: Entity state changes
    entity_changes: Optional[List[EntityStateChange]] = None
```

## Session Config Support

**starting_entities** (new field):
```json
{
  "session_name": "Vault Heist",
  "scenario": {
    "theme": "heist",
    "_scenario_hint": "Players must bypass vault security"
  },
  "starting_entities": [
    {
      "name": "Vault Door",
      "description": "Reinforced titanium door with electronic lock",
      "entity_type": "door",
      "state": {
        "locked": true,
        "alarm_active": true
      },
      "structural_integrity": 50,
      "destructible": true
    },
    {
      "name": "Security Terminal",
      "description": "Wall-mounted terminal controlling vault access",
      "entity_type": "terminal",
      "state": {
        "active": true,
        "alarm_enabled": true
      },
      "destructible": false
    }
  ]
}
```

## JSONL Logging

### New Event: entity_spawn

```json
{
  "event_type": "entity_spawn",
  "round": 0,
  "entity_id": "entity_vault_door_1",
  "name": "Vault Door",
  "entity_type": "door",
  "state": {"locked": true, "alarm_active": true},
  "structural_integrity": 50,
  "destructible": true
}
```

### New Event: entity_state_change

```json
{
  "event_type": "entity_state_change",
  "round": 3,
  "entity_id": "entity_vault_door_1",
  "state_changes": {"locked": false, "hack_attempts": 1},
  "conditions_added": ["Hacked"],
  "structural_damage": 0,
  "narrative": "The lock disengages with a satisfying click"
}
```

### Existing Events: action_resolution

**Entities as targets**:
```json
{
  "event_type": "action_resolution",
  "round": 3,
  "agent_id": "player_01",
  "agent_type": "player",
  "action": "Hack the vault terminal",
  "target": "entity_terminal_1",
  "action_type": "technical",
  "success": true,
  "roll": {"total": 18, "success": true},
  "effects": {
    "entity_changes": [
      {
        "entity_id": "entity_terminal_1",
        "state_changes": {"security_level": 0},
        "conditions_added": ["Compromised"]
      }
    ]
  }
}
```

## Implementation Plan

### Phase 1: Core Data Structure (TDD)

**Test file**: `tests/unit/test_narrative_entity.py`

Write tests FIRST:
```python
def test_entity_creation():
    """Entities have state but no agency."""
    entity = NarrativeEntity(
        entity_id="entity_door_1",
        name="Vault Door",
        description="Reinforced door",
        state_dict={"locked": True}
    )
    assert entity.state_dict["locked"] == True
    assert not hasattr(entity, 'llm_client')
    assert not hasattr(entity, 'health')

def test_entity_state_tracking():
    """Entities track custom state."""
    entity = NarrativeEntity(
        name="Vault Door",
        description="Reinforced door",
        state_dict={"locked": True, "alarm_active": False}
    )
    entity.state_dict["locked"] = False
    entity.state_dict["hack_attempts"] = 1
    assert entity.state_dict["locked"] == False
    assert entity.state_dict["hack_attempts"] == 1

def test_entity_conditions():
    """Entities can have conditions."""
    entity = NarrativeEntity(name="Terminal", ...)
    entity.conditions.append(Condition(name="Hacked", penalty=0))
    assert len(entity.conditions) == 1
    assert entity.conditions[0].name == "Hacked"

def test_entity_structural_integrity():
    """Destructible entities have integrity."""
    entity = NarrativeEntity(
        name="Cargo Crate",
        description="Sealed container",
        structural_integrity=10,
        max_integrity=10,
        destructible=True
    )
    entity.structural_integrity -= 5
    assert entity.structural_integrity == 5
    assert entity.destructible == True
```

**Implementation**:
1. Create `scripts/aeonisk/multiagent/narrative_entity.py`
2. Create `NarrativeEntity` class (structure shown above)

### Phase 2: State Tracking & Targeting

**Test file**: `tests/unit/test_shared_state_entities.py`

Write tests FIRST:
```python
def test_shared_state_tracks_entities():
    """SharedState maintains entity pool."""
    state = SharedState()
    entity = NarrativeEntity(entity_id="entity_door_1", name="Door", ...)
    state.add_entity(entity)
    assert len(state.narrative_entities) == 1

def test_get_entity_by_id():
    """SharedState can retrieve entities."""
    state = SharedState()
    entity = NarrativeEntity(entity_id="entity_terminal_1", ...)
    state.add_entity(entity)

    retrieved = state.get_entity("entity_terminal_1")
    assert retrieved.entity_id == "entity_terminal_1"
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/shared_state.py`
2. Add `narrative_entities: List[NarrativeEntity] = []`
3. Add methods: `add_entity()`, `remove_entity()`, `get_entity()`

**Test file**: `tests/unit/test_target_ids_entities.py`

Write tests FIRST:
```python
def test_assign_entity_ids():
    """TargetIDMapper assigns IDs to entities."""
    mapper = TargetIDMapper()
    entities = [NarrativeEntity(name="Vault Door")]
    mapper.assign_entity_ids(entities)

    door_id = mapper.get_id_by_name("Vault Door")
    assert door_id.startswith("entity_")

def test_can_target_entity():
    """Players can target entities."""
    mapper = TargetIDMapper()
    assert mapper.can_target("player_01", "entity_door_1") == True

def test_entity_cannot_act():
    """Entities have no source targeting (can't act)."""
    mapper = TargetIDMapper()
    # Entities as sources should fail validation
    assert mapper.can_target("entity_door_1", "player_01") == False
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/target_ids.py`
2. Add `assign_entity_ids(entities: List[NarrativeEntity])`
3. Update `is_valid_target()` to include entities
4. Add entity-specific validation

### Phase 3: Structured Output Schemas

**Test file**: `tests/unit/test_entity_schemas.py`

Write tests FIRST:
```python
def test_entity_spawn_schema_validation():
    """EntitySpawn validates correctly."""
    spawn = EntitySpawn(
        name="Vault Door",
        description="Reinforced titanium",
        entity_type="door",
        state={"locked": True},
        structural_integrity=50,
        destructible=True
    )
    assert spawn.state["locked"] == True
    assert spawn.destructible == True

def test_entity_state_change_schema():
    """EntityStateChange validates correctly."""
    change = EntityStateChange(
        entity_id="entity_door_1",
        state_changes={"locked": False},
        conditions_added=["Hacked"],
        structural_damage=0,
        narrative="Door unlocked via hacking"
    )
    assert change.state_changes["locked"] == False
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/schemas/story_events.py`
2. Add `EntitySpawn` schema
3. Add `EntityStateChange` schema
4. Modify `StoryAdvancement` to include entity fields

### Phase 4: DM Integration

**Test file**: `tests/unit/test_dm_entity_handling.py`

Write tests FIRST:
```python
def test_dm_spawns_entity_from_structured_output():
    """DM processes EntitySpawn from structured output."""
    story_adv = StoryAdvancement(
        narration="You see a locked vault door",
        entities_spawned=[EntitySpawn(
            name="Vault Door",
            description="Reinforced door",
            state={"locked": True},
            structural_integrity=50
        )]
    )

    dm._process_story_advancement(story_adv)

    assert len(shared_state.narrative_entities) == 1
    assert shared_state.narrative_entities[0].name == "Vault Door"

def test_dm_updates_entity_state():
    """DM processes EntityStateChange."""
    entity = NarrativeEntity(
        entity_id="entity_door_1",
        state_dict={"locked": True}
    )
    shared_state.add_entity(entity)

    story_adv = StoryAdvancement(
        narration="The lock disengages",
        entity_changes=[EntityStateChange(
            entity_id="entity_door_1",
            state_changes={"locked": False},
            conditions_added=["Hacked"],
            narrative="Door hacked"
        )]
    )

    dm._process_story_advancement(story_adv)

    assert entity.state_dict["locked"] == False
    assert len(entity.conditions) == 1
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/dm.py`
2. Update `_process_story_advancement()` to handle:
   - `entities_spawned` (create NarrativeEntity, add to SharedState)
   - `entity_changes` (update entity state, log changes)
3. Add helper methods:
   - `_spawn_entity(spawn: EntitySpawn) -> NarrativeEntity`
   - `_apply_entity_changes(change: EntityStateChange)`
   - `_log_entity_state_change(entity, change)`

### Phase 5: Session Config & Documentation

**Create test config**:

`scripts/session_configs/session_config_entity_test.json`:
```json
{
  "session_name": "Entity Interaction Test",
  "max_turns": 2,
  "scenario": {
    "theme": "heist",
    "_scenario_hint": "Locked vault with terminal, test environmental interaction"
  },
  "starting_entities": [
    {
      "name": "Vault Door",
      "description": "Reinforced titanium door with electronic lock",
      "entity_type": "door",
      "state": {"locked": true, "alarm_active": false},
      "structural_integrity": 50,
      "destructible": true
    },
    {
      "name": "Security Terminal",
      "description": "Wall-mounted terminal controlling vault access",
      "entity_type": "terminal",
      "state": {"active": true, "alarm_enabled": true},
      "destructible": false
    }
  ]
}
```

**Update documentation**:

Add to `CLAUDE.md`:
```markdown
## Narrative Entities (Environmental Objects)

**Status**: Future phase (split from NPC work)

### What Are Entities?

Targetable environmental objects with persistent state:
- Doors (locked/unlocked/destroyed)
- Terminals (online/offline/hacked)
- Cargo (sealed/opened/secured)
- Cryo-pods (stable/failing)

### Entity Properties

- **Have state**: Tracked in state_dict
- **Can have conditions**: "Locked", "Hacked", "Destroyed"
- **Can be damaged**: Optional structural_integrity
- **Cannot act**: No LLM, no agency

### Why Split from NPCs?

- Different use case (environment vs agents)
- Can implement independently
- Lower priority (phantom targeting acceptable for now)
```

## Use Cases

### Heist Scenario

**Starting entities**:
- Vault Door (locked, reinforced)
- Security Terminal (active, alarm enabled)
- Cargo Crates (sealed, valuable contents)

**Player actions**:
1. Hack terminal to disable alarm
2. Unlock vault door via terminal
3. Blow door open if hack fails
4. Secure cargo crates

**Entity state tracking**:
- Terminal: active → compromised
- Door: locked → unlocked OR intact → destroyed
- Cargo: sealed → opened, contents acquired

### Corrupted Station Scenario

**Starting entities**:
- Cryo-Pods (failing, void-corrupted)
- Exchange Crystal (intact, unstable)
- Airlock Doors (sealed, emergency lockdown)

**Player actions**:
1. Stabilize cryo-pods (prevent deaths)
2. Destroy Exchange crystal (void source)
3. Override airlock (escape route)

**Entity state tracking**:
- Cryo-pods: failing → stabilized
- Crystal: intact → cracked → shattered
- Airlock: sealed → overridden → opened

## Relationship to IFF/ROE Vision

**Entities are environment, not agents**:
- No hostility considerations
- No faction allegiance
- Works in both tactical and narrative modes

**Tactical mode**: Entities on grid, can provide cover
**Narrative mode**: Entities off-grid, free-form positioning

## Estimated Implementation Scope

- **Lines of code**: ~150-200 (very lightweight)
- **Test files**: 4-5 unit tests, 1-2 integration tests
- **Risk**: Low (minimal integration points)
- **Dependencies**: None (can add after NPC work complete)

## Success Criteria

✅ **Entities can be spawned**: DM spawns entities via structured output
✅ **State tracking works**: Entity state persists across rounds
✅ **Players can target**: Players can hack/open/destroy entities
✅ **JSONL logging works**: Entity spawns/changes logged for replay
✅ **Session configs work**: starting_entities field loads entities

## Related Documents

- `.claude/NPC_DEESCALATION_DESIGN.md` - NPC and de-escalation system (separate feature)
- `.claude/ARCHITECTURE.md` - Multi-agent system architecture
- `CLAUDE.md` - Main development guide
- `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` - JSONL event schemas

---

**Next Steps**: Implement NPC system first, then add narrative entities as separate phase.
