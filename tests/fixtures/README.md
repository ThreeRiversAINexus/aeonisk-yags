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

### 1. Capture JSONL Session Logs

Run a multiagent session and capture the JSONL output:

```bash
cd scripts/aeonisk
source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_configs/session_config_combat.json
```

**Output location:** `multiagent_output/session_<session_id>.jsonl`

**Copy to fixtures:**
```bash
cp multiagent_output/session_<session_id>.jsonl ../../tests/fixtures/sample_logs/
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

### JSONL Session Logs
- `combat_session_<descriptor>.jsonl` - Combat scenarios
- `social_session_<descriptor>.jsonl` - Social/investigation
- `ritual_session_<descriptor>.jsonl` - Ritual/void mechanics
- `mixed_session_<descriptor>.jsonl` - Mixed gameplay

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

1. **Regenerate sessions** with new code
2. **Compare with old fixtures** to verify backward compatibility
3. **Update or add new fixtures** as needed
4. **Document changes** in commit messages

## Fixture Stability

**Note:** Fixtures may be regenerated frequently during development. Tests should:
- Handle minor variations in event structure
- Use flexible assertions for non-critical fields
- Focus on testing invariants (e.g., "all declarations have resolutions")
- Not hardcode specific values from fixtures

## Future Additions

- **Recorded LLM responses** - Capture real Claude responses for replay
- **Session config templates** - Pre-built configs for common test scenarios
- **Fixture validation** - Schema validation for all fixtures
- **Automated generation** - Scripts to generate fixtures on demand
- **Fixture catalog** - Index of available fixtures and their characteristics

## Questions?

See `tests/README.md` for testing patterns and examples.
