# 4. Architecture and Round Lifecycle

## 4.1 Startup sequence

The primary launcher enters `aeonisk.multiagent.main.main()`, which constructs `SelfPlayingSession` from the supplied config and calls `start_session()`. Startup is roughly:

```text
load config
  → validate and report routing
  → create coordinator/message bus
  → create SharedState and initialize services
  → configure mechanics, logger, retrieval, target IDs
  → create DM
  → create player agents
  → optionally create enemies/NPCs/vendors/altars
  → connect/register agents
  → DM generates opening scenario
  → begin rounds
```

The exact order has accumulated compatibility paths, so treat this as the conceptual order. When changing initialization, inspect `SelfPlayingSession.start_session()` and its nearby helper methods rather than adding setup in an agent constructor.

## 4.2 Message transport

`base.py` defines `MessageType`, `Message`, `MessageBus`, `Agent`, `GameState`, and `GameCoordinator`.

`Message` carries a type, sender, recipient, payload, timestamp/id information, and JSON serialization helpers. `MessageBus` registers handlers and routes messages. The implementation supports a Unix-socket server/client path, while the self-playing session uses the coordinator to manage the participating agents. This is why old diagrams that show direct function calls are incomplete: the important contract is the message type and payload, not only the Python call site.

Typical messages include scenario setup, turn requests, action declarations, action resolution, DM narration, round synthesis, character updates, and shutdown/ping messages. Search `MessageType` before inventing a new event; often an existing message with a more precise payload is safer.

## 4.3 SharedState is the service locator and state registry

`SharedState` holds session-wide objects and mutable facts. Important services include:

- `MechanicsEngine` for dice, effects, conditions, clocks, and logging.
- `ActionValidator` for duplicate/invalid declarations and target legality.
- Knowledge retrieval for rule/lore context.
- `TargetIDMapper` for stable names/IDs across prompts and resolution.
- Players, enemies, NPCs, vendors, altars, environmental objects, checkpoints, discoveries, stealth records, and DM notes.

Use accessors such as `shared_state.get_mechanics_engine()` instead of reaching into an agent or creating a second engine. A second mechanics object is a classic source of “the log says one thing, the live state says another.”

`SharedState.snapshot()` is the bridge between mutable runtime state and a reconstructable record. If you add a stateful feature, decide explicitly whether it belongs in snapshots and whether it needs its own event.

## 4.4 Agent responsibilities

### AIDMAgent

The DM loads prompts, receives declarations and context, estimates/resolves action outcomes, generates narration, manages clocks/story progression, and emits synthesis. It is the broadest agent and contains many compatibility paths. Keep mechanical decisions explicit in structured output; avoid making a new free-form marker when a schema field can express the state.

### AIPlayerAgent

The player builds context from character state, goals, personality, visible narrations, party state, tactical data, and available actions. It declares one action per turn through the player schema. Its output is proposed intent plus mechanical metadata—not a direct state mutation.

### EnemyCombatManager and enemy agents

The manager handles enemy grouping, declarations, tactics, morale, targeting, movement, reactions, and lifecycle. Individual enemy agents may share intelligence and may be LLM-driven. Combat resolution still passes through validation and tactical/mechanics gates.

### NPC agents

NPCs have memory, relationships, faction context, goals, dialogue/action schemas, and conversion/vendor behavior. NPC purchases, transfers, consumption, and checkpoint operations have pre-validation paths in the session because narration must not create phantom transactions.

## 4.5 The round as a state machine

The round is best understood as four conceptual phases, even though the implementation has many sub-phases:

```text
DECLARATION
  players/enemies/NPCs propose actions
        ↓
ADJUDICATION
  session validates → DM/mechanics resolve → effects apply
        ↓
SYNTHESIS
  DM receives resolutions and describes the round/story change
        ↓
CLEANUP
  enemy lifecycle, morale/conversions, state snapshots, clocks, logs
        ↓
next round or terminal session
```

### Declaration

Agents are given a context filtered by visibility and current state. Players and enemies declare asynchronously or in the session’s controlled order. The session buffers declarations and tracks initiative/order information where tactical rules require it.

### Adjudication

The session checks duplicates, defeated/incapacitated actors, target validity, inventory/currency/transfer/checkpoint constraints, and action-specific prerequisites. Deterministic operations—such as some purchases or consumption operations—may be applied before DM narration so that the DM sees the real result. Dice-based operations remain pending until resolution.

The DM’s structured resolution is then passed into mechanics. The code updates health, wounds, stuns, void, conditions, positions, clocks, inventory, energy, and entity activity as appropriate.

### Synthesis

The DM receives the action-resolution summary and prior narration, then produces the round’s narrative/structured synthesis. The session—not necessarily the DM module itself—is responsible for receiving that message and logging it. This separation is important when tracing missing synthesis events.

### Cleanup

The session checks defeat/incapacitation, morale, conversions, departures, new spawns, scene advancement, vendor/altar state, and round snapshots. It also decides whether the session ends because of a terminal clock, DM-declared status, error, or round cap.

## 4.6 Entity lifecycle

Entities can be created, act, become inactive, flee, surrender, be converted to NPCs, or be removed during scene transitions. Enemy conversion is not simply a narrative label: it changes which manager owns the entity and which action rules apply next round.

When adding a new entity type, define:

1. Its identity and stable target ID.
2. Where it is registered in `SharedState`.
3. How it appears in agent context and visibility filtering.
4. How it declares actions.
5. How it is validated and resolved.
6. How defeat/departure/conversion works.
7. Which snapshot and JSONL fields describe it.

## 4.7 What can go wrong architecturally

- **Narrative/engine divergence:** prose says an item was bought, but validation rejected it. Trace pre-validation and the transaction event.
- **Stale target IDs:** an enemy was defeated or converted but a buffered action still targets it. Trace `ResolutionState` and `TargetIDMapper`.
- **State exists but is invisible:** a field was added to an object but not to context building or snapshots.
- **A handler never fires:** the message type or registration ID differs. Search both `add_handler` and the sender’s `MessageType`.
- **Legacy path selected accidentally:** a fallback key or old schema shape is being loaded. Print effective config and inspect the branch in `launch_config.py`.
