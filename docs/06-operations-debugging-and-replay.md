# 6. Operations, Debugging, and Replay

## 6.1 Log levels

The launcher defines custom levels in addition to standard Python logging:

```bash
python scripts/run_multiagent_session.py config.json --log-level INFO
python scripts/run_multiagent_session.py config.json --log-level DEBUG
python scripts/run_multiagent_session.py config.json --log-level LLM
python scripts/run_multiagent_session.py config.json --log-level TRACE
```

- `INFO`: normal progress and major lifecycle events.
- `DEBUG`: mechanics/state details without all HTTP chatter.
- `LLM`: provider/API activity.
- `TRACE`: extremely verbose parsing and transitions.

Use one focused level at a time. If the terminal is flooded, use JSONL and agent logs instead of immediately jumping to TRACE.

## 6.2 Reproducibility

`--random-seed` controls Python-side randomness for deterministic tests and comparisons:

```bash
python scripts/run_multiagent_session.py config.json --random-seed 42
```

A seed does not make an LLM deterministic across providers, model revisions, retries, proxy batching, or changed prompts. Reproducibility requires preserving:

- config file;
- seed;
- code revision/branch;
- prompt version and provider/model;
- dependency environment;
- proxy mode and URL, if used;
- fixture/input dataset;
- output JSONL and agent logs.

## 6.3 Replay and hybrid continuation

The main launcher can replay an existing JSONL:

```bash
python scripts/run_multiagent_session.py \
  --replay multiagent_output/session_ABC.jsonl

python scripts/run_multiagent_session.py \
  --replay multiagent_output/session_ABC.jsonl \
  --replay-to-round 3

python scripts/run_multiagent_session.py \
  --replay multiagent_output/session_ABC.jsonl \
  --continue-from-round 3
```

Replay reconstructs prior rounds and can execute them through cached responses. Hybrid mode reuses cached responses through a selected round, then calls live providers afterward. It is useful for testing a changed prompt or mechanics rule without paying to regenerate the stable opening.

Replay is only as faithful as the recorded inputs and reconstruction code. If a schema, target mapping, or state model changed, a replay may reveal a compatibility defect rather than reproduce the original exactly.

## 6.4 Failure triage

### The session stops before round one

Check config validation, provider credentials, model names, prompt file existence, and initialization stack traces. This is usually a setup failure, not a game-mechanics failure.

### An agent repeatedly emits invalid JSON

Enable agent prompt logging, inspect the exact schema/prompt pair, and check whether the provider supports the requested structured-output mode. Then run the schema/parser unit tests. Do not “fix” this by accepting arbitrary prose without adding a bounded fallback.

### Actions declare but nothing resolves

Search JSONL for `action_declared` and `action_resolution`, then inspect message handlers and timeout logs. The problem may be a missing handler, wrong recipient, an invalid action removed by the validator, or a DM structured-output failure.

### The story says an effect happened but state did not change

Trace the effect from the DM response through the session’s `_process_*` path into mechanics and then the snapshot. Transactions, transfers, consumption, checkpoint access, and attunements deliberately have pre-validation/ordering rules; confirm the effect was applied exactly once.

### An enemy acts after defeat

Inspect `ResolutionState`, `TargetIDMapper`, enemy `is_active`, health/stun/wound thresholds, and the post-resolution synchronization safety nets. The defeated actor should be marked before later declarations are executed.

### The run never ends

Inspect `max_turns`, terminal clock designation/progress, DM session-end structured output, and the end-condition checker. A terminal story status and a full clock are separate possible termination signals.

## 6.5 Useful repository tools

Analysis and audit scripts live in `scripts/`. Common categories:

- `analyze_session.py`, `analyze_success_metrics.py`, `analyze_consequence_salience.py`: inspect completed sessions and behavior.
- `analyze_prompt_tokens.py`, `cost_report.py`: estimate prompt/token/cost behavior.
- `replay_fixture.py`, `contract_replay.py`, `mechanics_replay.py`: replay or contract-check recorded behavior.
- `extract_fixture.py`, `diff_fixtures.py`, `state_reconstructor.py`: create and compare reproducible inputs/state.
- `audit_dm_prompts.py`, `verify_fixes.py`, `session_invariants.py`: focused validation/auditing.
- `datamine/`: bulk validation, rule-fidelity, analyzers, and formatters.

Read each script’s help or source before using it in bulk; several are experiment-specific and may write files.

## 6.6 Operational hygiene

- Keep API keys outside git.
- Give concurrent bulk experiments separate output roots.
- Never edit a historical JSONL in place; copy it and record the transformation.
- Treat generated datasets and fixtures as artifacts with provenance.
- Do not delete a failing run until the event stream and config have been archived.
- When changing prompts, record the prompt version and rerun the relevant evaluations.
