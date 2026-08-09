# 8. Testing and Repository Map

## 8.1 Test layers

Run the focused layers with:

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/unit/test_mechanics.py -v
```

Unit tests isolate mechanics, schemas, validators, providers, prompts, logging, tactical rules, economy, and helpers. Integration tests exercise session flows, message handling, structured outputs, entity lifecycle, replay, and combinations of systems. `tests/fixtures/` contains sample logs and session inputs; fixtures are executable documentation. `tests/unit/yags/` checks behavior against converted/reference YAGS materials.

## 8.2 Verification matrix

| Change | Minimum verification |
|---|---|
| Prompt wording | Prompt loader tests, prompt audit, one mocked agent call if available. |
| Schema field | Schema tests, prompt contract, affected integration fixture. |
| Mechanics formula | Known-roll tests, mechanics replay, affected integration flow. |
| New action | Schema + validator + mechanics + JSONL + end-to-end fixture. |
| Session lifecycle | Session integration, replay/resume, session invariants. |
| Config key/field | Add the `FieldSpec` to `config_schema.py`; `test_config_schema.py` drift guard + `audit_session_configs.py` sweep. |
| Provider/routing | Mock provider tests, launch validation, dry-run report. |
| Bulk runner | Runner tests, `--dry-run`, one small isolated batch. |
| Dataset format | Parser/normalization tests and analysis smoke test. |

## 8.3 Repository map

```text
aeonisk-yags/
├── docs/                         # This book
├── .claude/skills/               # Repo-local skills (e.g. scenario-builder)
├── scripts/
│   ├── run_multiagent_session.py # Main simulator launcher
│   ├── bulk_session_runner.py    # Parallel/replayable batch runner
│   ├── audit_session_configs.py  # Read-only config audit (deviations/deprecated/teeth)
│   ├── aeonisk/multiagent/       # Primary runtime
│   │   ├── session.py            # Round orchestration/lifecycle
│   │   ├── base.py               # Messages, bus, agents, coordinator
│   │   ├── shared_state.py       # Shared services and mutable state
│   │   ├── mechanics.py          # Rules, effects, JSONL logger
│   │   ├── dm.py                 # DM agent
│   │   ├── player.py             # Player agent
│   │   ├── enemy_*.py            # Tactical enemy system
│   │   ├── npc_agent.py          # NPC/vendor/conversion behavior
│   │   ├── schemas/              # Structured output contracts
│   │   ├── prompts/              # Provider/language YAML prompts
│   │   ├── replay.py             # Replay and continuation
│   │   ├── config_schema.py      # Config single-source-of-truth registry (+ explain_config)
│   │   └── launch_config.py      # Config validation/routing (derives from config_schema)
│   ├── aeonisk/engine/           # Older interactive engine
│   ├── aeonisk/core/             # Older domain models
│   ├── datamine/                 # Bulk validation and analysis
│   └── session_configs/          # Experiment configs
├── tests/                        # Unit, integration, fixtures, helpers
├── content/                      # Aeonisk lore/rules modules
├── datasets/                     # Training corpora and normalized data
├── ai_pack/                      # Prompt/content distribution pack
├── evals/                        # Fidelity and model evaluations
├── plantuml/                     # Architecture diagrams and notes
├── converted_yagsbook/           # Converted YAGS reference chapters
└── yags/                         # YAGS source/reference assets
```

## 8.4 Where to look

| Question | Start here |
|---|---|
| What does a config key do / is a config valid? | `config_schema.py` (`FieldSpec` help/default/status), then `audit_session_configs.py` and `explain_config` — see chapter 3.2/3.7. |
| Why did the session end? | `session.py` end conditions, terminal clocks, DM session-end output, final JSONL events. |
| Why was an action rejected? | Session pre-validation, `action_router.py`, `targeting_validation.py`, `character_validator.py`. |
| Why was a roll wrong? | `mechanics.py`, then resolution schema and action context. |
| Why did narration see too much/little? | `awareness.py`, context builders, agent prompt builders. |
| Why did the model return invalid data? | Prompt YAML, `prompt_loader.py`, relevant schema, structured-output helper. |
| Why did combat positioning break? | Tactical `Position`, `tactical_resolution.py`, session position helpers. |
| Why did a transaction duplicate? | Session pre-validation, mechanics transaction path, JSONL events. |
| Why is a field absent from analysis? | `SharedState.snapshot()`, logger event construction, serialization, analysis parser. |

## 8.5 Maintenance checklist

Before merging a meaningful change:

1. Add/update the narrowest unit test.
2. Run the relevant integration flow.
3. Search for duplicated vocabulary/field names.
4. Check prompt/schema alignment.
5. Confirm state mutation occurs once in the authoritative layer.
6. Confirm JSONL/replay behavior.
7. Run a small seeded session or fixture replay.
8. Update this book or the nearest focused README.
9. Record compatibility/deprecation notes if old configs may still exist.

## 8.6 Final orientation

If you feel lost, start at `SelfPlayingSession.start_session()`, then follow one action through `AIPlayerAgent` → `Message` → session handler → DM resolution → `MechanicsEngine` → `SharedState.snapshot()`/`JSONLLogger`. That vertical slice teaches more about the project than reading every module in isolation.
