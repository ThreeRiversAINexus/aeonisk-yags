# Test Fixtures Guide

This directory contains test data for the Aeonisk YAGS testing suite.

## Directory Structure

```
fixtures/
├── README.md                    # This file
├── sample_logs/                 # Real JSONL session logs for testing
│   └── combat_session_sample.jsonl
├── llm_responses/               # LLM response fixtures (future)
│   ├── manual/                  # Hand-crafted responses
│   └── recorded/                # Captured from real sessions
└── session_configs/             # Session configuration files (future)
```

## Generating Test Fixtures

### Automated Fixture Generation (Recommended)

**Use the fixture tools** for extracting, replaying, and comparing fixtures:

```bash
# 1. Run a session and find interesting moments
python scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json
# Output: multiagent_output/session_20250131_combat.jsonl

# 2. Extract specific rounds as fixture
python scripts/extract_fixture.py \
  multiagent_output/session_20250131_combat.jsonl \
  --rounds 0-3 \
  --output tests/fixtures/sessions/combat_rounds_0_3.jsonl

# 3. Verify code fixes (after making changes)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/combat_rounds_0_3.jsonl \
  --cache-player-actions \
  --output tests/fixtures/sessions/combat_after_fix.jsonl

# 4. Compare before/after
python scripts/diff_fixtures.py \
  tests/fixtures/sessions/combat_rounds_0_3.jsonl \
  tests/fixtures/sessions/combat_after_fix.jsonl \
  --focus effects.damage.dealt
```

**See CLAUDE.md → "Fixture Tools" section for complete documentation**

### 1. Capture JSONL Session Logs (Manual Method)

Run a multiagent session and capture the JSONL output:

```bash
cd scripts/aeonisk
source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_configs/session_config_combat.json
```

**Output location:** `multiagent_output/session_<session_id>.jsonl`

**Extract to fixtures using extract_fixture.py:**
```bash
python scripts/extract_fixture.py \
  multiagent_output/session_<session_id>.jsonl \
  --rounds 0-5 \
  --output tests/fixtures/sessions/session_descriptive_name.jsonl
```

### 2. Create Scenario-Specific Sessions

Generate different types of sessions for testing:

**Combat scenarios:**
```bash
# Short combat (2 rounds)
python3 ../run_multiagent_session.py ../session_configs/session_config_combat.json

# Extended combat (5+ rounds)
# Edit session_config_combat.json: "max_turns": 5
```

**Social scenarios:**
```bash
# Edit session config: "force_combat": false
python3 ../run_multiagent_session.py ../session_configs/session_config_full.json
```

**Ritual/Void scenarios:**
```bash
# Characters with high void performing rituals
# (Configure characters with void ≥ 3 in session config)
```

### 3. Extract LLM Responses (Future)

To create fixtures from JSONL logs:

```python
# Example extraction script (to be implemented)
import json

with open('session_abc123.jsonl', 'r') as f:
    for line in f:
        event = json.loads(line)

        if event['event_type'] == 'llm_call':
            # Extract prompt and response
            fixture = {
                'agent_type': event['agent_type'],
                'prompt': event['prompt'],
                'response': event['response'],
                'context': event.get('round', 'scenario_gen')
            }

            # Save to llm_responses/recorded/
            # ...
```

## Using Fixtures in Tests

### Load JSONL Event Log

```python
import pytest
import json
from pathlib import Path

@pytest.fixture
def combat_events():
    """Load combat session events."""
    jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events

def test_something(combat_events):
    # Filter events
    declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']
    assert len(declarations) > 0
```

### Load LLM Response Fixtures (Future)

```python
@pytest.fixture
def dm_scenario_response(load_llm_fixture):
    """Load DM scenario generation response."""
    return load_llm_fixture('dm_scenario_basic.json')
```

## JSONL Event Types

From a typical combat session:

- `session_start` - Session initialization
- `scenario` - DM-generated scenario
- `enemy_spawn` - Enemy spawning
- `round_start` - Combat round begins
- `declaration_phase_start` - Declaration phase
- `action_declaration` - Character declares action
- `adjudication_start` - DM begins adjudication
- `action_resolution` - Action resolved by DM
- `llm_call` - LLM API call (prompt + response)
- `character_state` - Character state snapshot
- `round_synthesis` - Round summary
- `round_summary` - End of round
- `mission_debrief` - Session conclusion
- `session_end` - Session complete
- `structured_output_metrics` - Structured output stats

## Event Structure Examples

### action_declaration
```json
{
    "event_type": "action_declaration",
    "ts": "2025-10-31T15:32:37.680821",
    "session": "5fe45c0e-760a-49f8-b051-78a8b6eebd04",
    "round": 1,
    "player_id": "player_kael_dren",
    "character_name": "Enforcer Kael Dren",
    "initiative": 28,
    "action": {
        "major_action": "Attack",
        "target": "grunt_8e2f"
    }
}
```

### action_resolution
```json
{
    "event_type": "action_resolution",
    "round": 1,
    "agent": "Enforcer Kael Dren",
    "action": "Attack siege perimeter guard",
    "roll": {
        "attr": "Agility",
        "attr_val": 4,
        "skill": "Combat",
        "skill_val": 5,
        "d20": 13,
        "total": 33,
        "dc": 18,
        "margin": 15,
        "tier": "excellent",
        "success": true
    },
    "economy": {
        "void_delta": 0,
        "soulcredit_delta": 1
    },
    "clocks": {
        "Breach Attempt": "2/3"
    },
    "effects": []
}
```

### llm_call
```json
{
    "event_type": "llm_call",
    "round": 1,
    "agent_id": "dm",
    "agent_type": "dm",
    "prompt": "...",
    "response": "...",
    "model": "claude-sonnet-4-5",
    "tokens": {
        "input": 1807,
        "output": 379
    }
}
```

## Fixture Naming Conventions

### JSONL Session Logs (`fixtures/sessions/`)
- `combat_session_<descriptor>.jsonl` - Combat scenarios
- `social_session_<descriptor>.jsonl` - Social/investigation
- `ritual_session_<descriptor>.jsonl` - Ritual/void mechanics
- `mixed_session_<descriptor>.jsonl` - Mixed gameplay
- `<bug_name>_bug.jsonl` - Regression test fixtures documenting specific bugs

### LLM Response Fixtures (Future)
- `dm_scenario_<type>.json` - Scenario generation
- `player_<name>_<action_type>.json` - Player declarations
- `enemy_<type>_decision.json` - Enemy AI decisions
- `dm_resolution_<tier>.json` - DM resolutions by success tier

## Best Practices

### Generating Fixtures
- **Keep sessions short** - 2-5 rounds for combat, focused scenarios
- **Vary parameters** - Different party sizes, enemy types, tactical positions
- **Document context** - Add README notes explaining what each fixture tests
- **Version control** - Commit fixtures with descriptive messages

### Using Fixtures
- **Read-only** - Never modify fixtures in tests
- **Isolation** - Each test should work with any valid fixture
- **Validation** - Use schema validation on loaded fixtures
- **Documentation** - Comment what aspect of the fixture matters for the test

## Updating Fixtures

When game mechanics change:

1. **Replay existing fixture** with new code:
   ```bash
   python scripts/replay_fixture.py \
     tests/fixtures/sessions/old_fixture.jsonl \
     --all-cached \
     --output tests/fixtures/sessions/new_fixture.jsonl
   ```

2. **Compare with old fixture** to verify changes:
   ```bash
   python scripts/diff_fixtures.py \
     tests/fixtures/sessions/old_fixture.jsonl \
     tests/fixtures/sessions/new_fixture.jsonl
   ```

3. **Review mechanical differences** - verify they match expected code changes

4. **Update fixture** - Replace old with new if changes are correct

5. **Document changes** in commit messages

## Fixture Stability

**Note:** Fixtures may be regenerated frequently during development. Tests should:
- Handle minor variations in event structure
- Use flexible assertions for non-critical fields
- Focus on testing invariants (e.g., "all declarations have resolutions")
- Not hardcode specific values from fixtures

## Fixture Lifecycle & Naming

**Naming Format:** `<purpose>_<scenario-type>_<descriptor>.jsonl`
- **purpose:** `golden` | `regression` | `test` | `baseline`
- **scenario-type:** `combat` | `social` | `investigation` | `ritual` | `mixed`

**Lifecycle:**
- **Active:** Used by current tests, documented in MANIFEST.json
- **Deprecated:** Marked in MANIFEST.json, delete after verifying no test references
- **Golden:** Reference implementations, never delete without discussion

**Size Guidelines:**
- Unit tests: 1-3 rounds, ~50-200KB
- Integration tests: 2-5 rounds, ~200-500KB
- Avoid: >10 rounds or >1MB files

## Future Additions

- **Recorded LLM responses** - Capture real Claude responses for replay
- **Session config templates** - Pre-built configs for common test scenarios
- **Fixture validation** - Schema validation for all fixtures
- **Automated generation** - Scripts to generate fixtures on demand
- **Fixture catalog** - Index of available fixtures and their characteristics

## Questions?

See `tests/README.md` for testing patterns and examples.
