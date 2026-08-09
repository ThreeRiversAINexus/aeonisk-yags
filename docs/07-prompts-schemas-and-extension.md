# 7. Prompts, Schemas, and Extension

## 7.1 The model contract

An agent interaction has four contracts:

1. **Context contract:** what the agent is allowed to see and what the caller places in the prompt.
2. **Prompt contract:** instructions, examples, rules vocabulary, and output requirements.
3. **Schema contract:** the accepted structured shape and field validation.
4. **State contract:** which accepted fields are actually applied and logged.

Changing only one of these creates silent failure. Adding `cover_target` to a Pydantic model does not make the DM use it, and documenting a new action in YAML does not make the validator accept it.

## 7.2 Prompt layout

Prompts live under `scripts/aeonisk/multiagent/prompts/<provider>/<language>/`. The directory contains role files such as `dm.yaml`, `player.yaml`, and `enemy.yaml`, with nested sections for specialized actions.

`PromptLoader` reads YAML, caches files, extracts metadata/version, loads complete prompts or named sections, composes sections, and performs simple variable substitution. Specialized and conditional sections are supported. The loader returns `LoadedPrompt` plus `PromptMetadata`, which makes prompt version available for auditing.

Prefer adding a named section and composing it at the caller over copying a large prompt into another file. Keep provider/language variants synchronized where the project claims support for them.

## 7.3 Structured schemas

The schema package contains shared types and action/effect/story models. Important families include player actions, action resolutions/effects, enemy decisions, shared position/target/status types, story events/lifecycle decisions, and vendor interactions.

Pydantic catches missing fields, wrong types, invalid enum values, and some cross-field errors. It cannot guarantee that an action is legal in the current game state; that remains the session/mechanics validator’s job.

When changing a schema:

1. Search all constructors and `.model_dump()`/dictionary consumers.
2. Update prompt descriptions and examples.
3. Update `scripts/schema_contract.json` if the external contract is represented there.
4. Add unit tests for valid and invalid instances.
5. Add a fixture or integration test for the state change.
6. Check replay and JSONL compatibility.

## 7.4 Adding a new player action

Use this sequence:

1. Define the action vocabulary in the relevant schema/shared type.
2. Describe when it should be selected in the player YAML/action sections.
3. Add parsing/normalization in `action_schema.py` or the current conversion path.
4. Add validation for actor, target, position, inventory, resource, and timing constraints.
5. Decide whether the operation is deterministic or dice-based.
6. Add the mechanics effect and make it idempotent where retries are possible.
7. Route it through DM adjudication or the appropriate tactical resolver.
8. Add a JSONL event or extend an existing event with stable fields.
9. Add unit, integration, and replay/fixture coverage.
10. Update documentation and dataset guidelines.

A transfer-like action, for example, must validate both parties, available quantity, permissions, and cutoff/checkpoint rules before narration can claim success.

## 7.5 Adding state

Put durable facts in `SharedState` or the mechanics engine, not only on an agent. Give it explicit methods such as `add_discovery()`, `record_void_spike()`, or `advance_ritual()`.

Then expose the state deliberately to DM context, player/enemy/NPC context where visibility allows, `snapshot()`, JSONL events, replay reconstruction, and analysis scripts. Avoid undocumented public dictionaries: they are convenient initially but make ownership and compatibility difficult to audit.

## 7.6 Adding mechanics

Keep the random roll and derived values in one function. Return a structured result with raw inputs and outputs. Do not let one caller roll once to decide success and again to describe the margin. Use a seedable random source where feasible.

Specify inputs/defaults, roll notation, threshold, margin/tier mapping, critical/fumble rules, state effects, conditions/duration, retry/idempotency behavior, event payload, and malformed-output behavior. Add known-roll regression tests.

## 7.7 Extending the DM

The DM is large and has structured-output and legacy-marker paths. Prefer a new structured field/story event, a narrow helper, explicit session-boundary logging, and a fixture. Keep prompt parsing focused on normalization/validation; state mutation belongs in the session/mechanics layer.

## 7.8 Extending providers

Provider behavior is distributed across `llm_provider.py`, `unified_llm_client.py`, batch/proxy support, and provider-specific clients. A provider must account for credentials, structured output, retries/timeouts, token/cost metadata, error normalization, proxy fallback, prompt/response logging, and offline tests.

Add it at the client/routing layer rather than copying an agent. Exercise it with a mocked completion before using a live key.

## 7.9 The single-source-of-truth trap

Attributes and similar vocabularies are represented in multiple validators, Pydantic descriptions, action schemas, and YAML prompt prose. This is documented in `.claude/SINGLE_SOURCE_OF_TRUTH.md`.

Until that refactor is complete, changing a vocabulary means searching the whole repository:

```bash
rg -n 'Strength|Agility|Endurance|Dexterity|Perception|Intelligence|Empathy|Willpower' scripts/aeonisk/multiagent tests
```

Update runtime lists, schema descriptions, prompt text, fixtures, and tests together.
