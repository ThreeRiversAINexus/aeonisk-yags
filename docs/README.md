# Aeonisk-YAGS: The Field Guide

This directory is a standalone book for the Aeonisk-YAGS repository. It has two audiences:

- **Users and operators** who want to install the project, configure agents, run sessions, inspect logs, replay failures, and generate batches.
- **Developers and researchers** who need to understand the architecture, mechanics, schemas, prompts, tests, and safe extension points.

The documentation is intentionally organized as a guided tour rather than a list of API pages. Start with [01 - Mental Model](01-mental-model.md), then choose the path that matches your goal.

## Reading paths

### I want to run one session

1. [02 - Installation and First Run](02-installation-and-first-run.md)
2. [03 - Sessions, Configuration, and Output](03-sessions-configuration-and-output.md)
3. [06 - Operations, Debugging, and Replay](06-operations-debugging-and-replay.md)

### I want to generate research data

1. [01 - Mental Model](01-mental-model.md)
2. [03 - Sessions, Configuration, and Output](03-sessions-configuration-and-output.md)
3. [05 - Mechanics, State, and JSONL](05-mechanics-state-and-jsonl.md)
4. [06 - Operations, Debugging, and Replay](06-operations-debugging-and-replay.md)

### I want to change the code

1. [01 - Mental Model](01-mental-model.md)
2. [04 - Architecture and Round Lifecycle](04-architecture-and-round-lifecycle.md)
3. [05 - Mechanics, State, and JSONL](05-mechanics-state-and-jsonl.md)
4. [07 - Prompts, Schemas, and Extension](07-prompts-schemas-and-extension.md)
5. [08 - Testing and Repository Map](08-testing-and-repository-map.md)

## Contents

| Chapter | Purpose |
|---|---|
| [01 - Mental Model](01-mental-model.md) | What the repository is, which subsystem is primary, and the vocabulary used throughout the book. |
| [02 - Installation and First Run](02-installation-and-first-run.md) | Environment setup, API keys, commands, interactive CLI, and common first-run failures. |
| [03 - Sessions, Configuration, and Output](03-sessions-configuration-and-output.md) | Session config anatomy, the config-schema registry (single source of truth), the recommended baseline, adjudication/teeth, `scenario_hint` authoring, validate/audit/explain tooling, the scenario-builder skill, provider routing, bulk runs, and output. |
| [04 - Architecture and Round Lifecycle](04-architecture-and-round-lifecycle.md) | Components, message transport, agent responsibilities, and the exact shape of a round. |
| [05 - Mechanics, State, and JSONL](05-mechanics-state-and-jsonl.md) | YAGS resolution, combat, clocks, void/economy systems, state ownership, and event provenance. |
| [06 - Operations, Debugging, and Replay](06-operations-debugging-and-replay.md) | Logging, deterministic seeds, replay/resume, analysis scripts, and diagnosing bad sessions. |
| [07 - Prompts, Schemas, and Extension](07-prompts-schemas-and-extension.md) | LLM contract, YAML prompt composition, Pydantic models, adding actions, and changing agents. |
| [08 - Testing and Repository Map](08-testing-and-repository-map.md) | Test strategy, commands, source map, data assets, and a maintenance checklist. |

## Important scope note

Aeonisk-YAGS contains more than one playable surface. The **current primary system** is the structured multi-agent simulator in `scripts/aeonisk/multiagent/`, launched by `scripts/run_multiagent_session.py`. The repository also contains an older, simpler interactive CLI in `scripts/aeonisk/engine/` and `scripts/aeonisk_game.py`, plus the original YAGS source material under `yags/` and converted books under `converted_yagsbook/`.

Those layers share vocabulary but do not share every implementation detail. When this book says “the simulator,” it means the multi-agent system.

## How this book was written

The descriptions are based on the current source tree, especially `session.py`, `base.py`, `shared_state.py`, `mechanics.py`, the agent modules, schemas, prompt loader, launch validation, tests, and example configurations. Historical files in `.claude/`, `plantuml/`, and old planning documents are useful context, but source code wins when they disagree.

## Source conventions

Paths are relative to `aeonisk-yags/`. Commands assume the shell is in that directory and that `.venv` is active.

The codebase is under active development. Treat configuration keys and event payloads as versioned contracts: inspect the relevant schema and tests before changing them.
