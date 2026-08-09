# 2. Installation and First Run

## 2.1 Prerequisites

The project expects Python 3.12 or newer. Use a virtual environment; this is especially important for ChromaDB/vector-store dependencies and for keeping the simulator’s package versions separate from other projects.

```bash
cd aeonisk-yags
python3 -m venv .venv
source .venv/bin/activate
python --version
pip install -r requirements.txt
```

Development and test-only dependencies are in `requirements-dev.txt`. A pinned environment is represented by `requirements-lock.txt`; use it when reproducing an older experiment and use the project’s normal requirements file when developing against the current tree.

## 2.2 API credentials

The provider is chosen per agent in the session config. Typical environment variables are:

```bash
export ANTHROPIC_API_KEY='...'
export OPENAI_API_KEY='...'
```

The launcher also loads dotenv files. Do not commit secrets. If a `.env` file is used locally, confirm it is ignored before adding credentials.

The DM, players, and enemies can use different providers/models. A missing enemy-specific configuration falls back through the runtime’s compatibility chain to legacy enemy configuration and then the DM configuration.

## 2.3 Run a normal session

From the repository root:

```bash
source .venv/bin/activate
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/session_config_combat.json
```

The launcher performs these useful preflight actions:

1. Loads JSON or YAML config data.
2. Validates required fields and known compatibility constraints.
3. Prints effective LLM routing before agents start.
4. Configures the selected log level.
5. Starts the async self-playing session.

The result is normally written beneath the configured `output_dir`, with a filename similar to `session_<id>.jsonl`.

Useful options:

```bash
python3 scripts/run_multiagent_session.py config.json --log-level DEBUG
python3 scripts/run_multiagent_session.py config.json --random-seed 42
python3 scripts/run_multiagent_session.py config.json --log-agents-separately
python3 scripts/run_multiagent_session.py --create-config /tmp/example.json
```

Use `--skip-validation` only when intentionally running a legacy or experimental config. It removes a valuable safety net and does not repair the config.

## 2.4 Read the output immediately

Do not judge a run only by its terminal prose. Inspect the JSONL:

```bash
head -n 5 multiagent_output/session_*.jsonl
rg -n '"event_type"|"error"|"session_end"' multiagent_output/session_*.jsonl
```

Each line is a complete JSON object. The most useful first checks are:

- Is there a scenario/setup event?
- Are actions being declared?
- Are resolutions and round synthesis events present?
- Did the session end normally or terminate with an error?
- Are state snapshots changing as expected?

If you enable `--log-agents-separately`, the human-readable prompt/response traces are written under `agent_logs/<session_id>/`. These are invaluable for diagnosing a model contract failure, but the JSONL remains the canonical machine-readable record.

## 2.5 The older interactive CLI

There is also a simple command-line game surface:

```bash
python3 scripts/aeonisk_game.py
```

It supports commands such as `start`, `create`, `list`, `select`, `scenario`, `look`, `talk`, `do`, `check`, `save`, and `load`. Its `GameSession` lives in `scripts/aeonisk/engine/game.py` and uses the simpler `scripts/aeonisk/core/models.py` model set. It is useful for manual exploration and legacy tests, but it is not the same execution path as `run_multiagent_session.py` and does not provide the full autonomous multi-agent lifecycle.

## 2.6 No-network development loop

For code changes that do not need live model calls:

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
```

Use fixtures and mocks first. Live API tests are expensive, slow, and provider-dependent. Search for test names containing `LiveAPI`, `direct`, or provider names before running them.

## 2.7 Common first-run failures

### Import errors

Run from `aeonisk-yags/`, activate `.venv`, and use the supplied launcher. Several scripts add `scripts/` to `sys.path` themselves; invoking a deep module from another working directory can bypass those assumptions.

### Config validation errors

Read the full list, not only the first error. Common causes include missing `session_name`, `max_turns`, `party_size`, `agents.dm`, or a non-empty `agents.players` list; enabling enemies without the tactical module; deprecated `scenario.initial_clocks`; and malformed clocks or player fields.

### Provider errors

Check the printed effective-routing banner, the corresponding API key, the model name, and whether a proxy is being selected by config or environment. `LLM_PROXY_MODE`, `USE_LLM_PROXY`, and `LLM_PROXY_URL` can influence routing beneath the config layer.

### Output collisions

Use a distinct `output_dir` for concurrent experiments. The bulk runner provides stronger per-run isolation than manually starting many processes against one directory.
