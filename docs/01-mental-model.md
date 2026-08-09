# 1. Mental Model

## 1.1 What Aeonisk-YAGS does

Aeonisk-YAGS is a self-playing tabletop role-playing simulator. A session contains a party of AI-controlled player characters, a Dungeon Master (DM), and optionally enemies and non-player characters (NPCs). The agents use language models for intent, tactics, adjudication context, and prose, while Python owns the rules-sensitive state transitions and logging.

The essential separation is:

```text
LLM proposes an action or explanation
        ↓
schema/validation turns it into structured data
        ↓
mechanics and session code apply authoritative effects
        ↓
DM narrates the result
        ↓
JSONL records both provenance and story
```

The system is not simply “ask a model to role-play.” It is a game loop wrapped around model calls. The loop is what makes the output useful for debugging and machine-learning research: an action can be connected to its actor, target, roll, difficulty, margin, effects, narration, and resulting state.

## 1.2 The three layers that are easy to confuse

### The game/content layer

`content/`, `datasets/`, `ai_pack/`, and the lore references describe Aeonisk: factions, law, economics, setting, tactical guidance, and examples. They are inputs to prompts or training/evaluation corpora, not the runtime engine by themselves.

### The simulator layer

`scripts/aeonisk/multiagent/` is the primary runtime. It contains the orchestrator, message bus, agent implementations, rules engine, schemas, prompt system, tactical combat, economy, NPCs, logging, and replay support.

### The YAGS reference/tooling layer

`yags/` contains the upstream-style YAGS source tree and character/equipment data. `converted_yagsbook/` contains converted reference chapters. The older Python game engine (`scripts/aeonisk/engine/`) is a separate, lighter interface that implements a subset of the concepts.

## 1.3 Roles in a session

| Role | Makes decisions about | Must not be treated as the final authority for |
|---|---|---|
| DM | Scenario framing, difficulty interpretation, adjudication, narrative, round synthesis, story advancement | Inventing mechanical effects that Python cannot apply |
| Player | Intent, chosen attribute/skill, tactical goal, role-play, target | Directly mutating shared state |
| Enemy | Tactics, target choice, movement, combat action, morale response | Bypassing resolution and damage gates |
| NPC | Dialogue, offers, social actions, conversion behavior, vendor behavior | Unvalidated purchases, transfers, or state changes |
| Session | Ordering, phase transitions, lifecycle, pre-validation, logging integration | Replacing the rules engine with prose |
| Mechanics | Dice, margins, damage, conditions, clocks, resources, effects | Writing story prose |

The boundaries are not perfectly pure—this is a large evolving codebase—but they are the most useful way to reason about it.

## 1.4 The authoritative path

When debugging a surprising result, follow this order:

1. Find the session configuration that created the run.
2. Find the declaring agent and its action schema/payload.
3. Find the session pre-validation path for that action type.
4. Find the DM adjudication or tactical resolver that produced the resolution.
5. Find the mechanics function that applied the effect.
6. Find the state snapshot and JSONL event written afterward.
7. Only then inspect the narrative for a prose mismatch.

This matters because narration can be plausible even when a mechanical effect was rejected, and a raw LLM response can look structured without being accepted by a schema.

## 1.5 What “structured” means here

Structured output appears in several forms:

- **Pydantic models** in `scripts/aeonisk/multiagent/schemas/` validate action and story objects.
- **JSON-shaped dictionaries** are used at integration boundaries and in older paths.
- **YAML prompts** describe the contract to the model.
- **JSONL events** persist a normalized record of what happened.

There are still legacy fields and compatibility branches. A field existing in a prompt does not guarantee that every old configuration supports it; the launch validator and tests are the better authority.

## 1.6 Async does not mean “many processes”

The current runtime is primarily asyncio-based. `GameCoordinator` and `MessageBus` provide a message-oriented transport and can use a Unix socket path; the main self-playing session creates and coordinates its agents in one Python invocation. The bulk runner uses separate subprocesses/process-pool workers to isolate independent sessions.

The practical distinction is:

- **Inside one session:** async coordination, shared in-memory state, message routing.
- **Across bulk runs:** process-level isolation, separate output directories, independent sessions.

Do not assume that changing one agent’s object is safe across bulk workers, and do not assume that an in-process state mutation is automatically serialized into the log.

## 1.7 The smallest useful mental picture

```text
config JSON/YAML
      ↓
SelfPlayingSession
      ├── GameCoordinator / MessageBus
      ├── SharedState
      │    ├── MechanicsEngine
      │    ├── validators and target mapper
      │    ├── clocks, discoveries, stealth, economy, entities
      │    └── JSONL logger
      ├── AIDMAgent
      ├── AIPlayerAgent × N
      ├── EnemyCombatManager / enemy agents (optional)
      └── NPC agents and vendors (optional)
```

The rest of the book expands each box and the arrows between them.
