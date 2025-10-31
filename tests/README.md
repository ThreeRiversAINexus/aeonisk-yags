# Aeonisk YAGS Testing Suite

Comprehensive test suite for the multi-agent tabletop RPG system.

## Overview

This testing infrastructure provides:

- **Unit Tests** - Fast, isolated tests for individual components (no LLM calls)
- **Integration Tests** - End-to-end tests with mocked LLM responses
- **Mock Infrastructure** - Deterministic LLM mocking for reproducible tests
- **Test Automation** - Makefile targets for easy testing workflows
- **Coverage Reports** - HTML/terminal coverage analysis

## Quick Start

```bash
# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run with coverage report
make test-cov

# Run specific test suites
make test-schemas
make test-mechanics
```

## Directory Structure

```
tests/
├── conftest.py                    # Pytest configuration & shared fixtures
├── README.md                      # This file
├── fixtures/                      # Test data and LLM responses
│   ├── llm_responses/
│   │   ├── manual/               # Hand-crafted LLM responses
│   │   └── recorded/             # Real LLM responses captured from sessions
│   ├── session_configs/          # Test session configurations
│   └── sample_logs/              # Sample JSONL logs for replay testing
├── mocks/                         # Mock implementations
│   ├── __init__.py
│   ├── mock_llm_client.py        # MockLLMClient, MockLLMProvider
│   └── (future: mock_message_bus.py, etc.)
├── helpers/                       # Test utilities
│   ├── __init__.py
│   ├── async_helpers.py          # Async test utilities
│   └── session_builder.py        # TestSessionBuilder for easy test setup
├── unit/                          # Unit tests (no external dependencies)
│   ├── __init__.py
│   ├── test_schemas.py           # Pydantic schema validation (37 tests)
│   ├── test_mechanics.py         # Dice, clocks, conditions, void
│   └── (future: test_outcome_parser.py, test_shared_state.py, etc.)
└── integration/                   # Integration tests (with mocked LLM)
    ├── __init__.py
    └── (future: test_session_flow.py, test_combat_round.py, etc.)
```

## Test Categories

### Unit Tests (`tests/unit/`)

Fast, deterministic tests with no external dependencies:

- **Schema Validation** (`test_schemas.py`) - 37 tests
  - Pydantic model validation
  - ActionResolution, PlayerAction, EnemyDecision schemas
  - Shared types (VoidChange, ClockUpdate, Condition, DamageEffect)
  - Factory functions and serialization

- **Mechanics** (`test_mechanics.py`)
  - Dice rolling (with seeded random)
  - Difficulty calculations
  - Action resolution
  - Scene clock mechanics
  - Condition/status effects
  - Void progression

- **TODO: Outcome Parser** (`test_outcome_parser.py`)
  - Marker detection (⚫ Void, 📊 Clock)
  - Enemy spawn/removal parsing
  - Text parsing utilities

- **TODO: Shared State** (`test_shared_state.py`)
  - Character state management
  - Coordination bonuses
  - State synchronization

### Integration Tests (`tests/integration/`)

End-to-end tests with mocked LLM clients:

- **TODO: Session Flow** (`test_session_flow.py`)
  - Scenario generation → Player declarations → DM resolution cycle
  - Multi-round gameplay

- **TODO: Combat Round** (`test_combat_round.py`)
  - Complete combat round with players + enemies
  - Initiative, declarations, resolutions

- **TODO: Structured Output** (`test_structured_output_flow.py`)
  - End-to-end Pydantic schema usage
  - DM resolution → Player action → Enemy decision flow

## Running Tests

### Using Makefile (Recommended)

```bash
# Run all tests
make test

# Run only unit tests (fast, no LLM dependencies)
make test-unit

# Run only integration tests
make test-integration

# Run tests with coverage report (HTML + terminal)
make test-cov
# View at: scripts/aeonisk/htmlcov/index.html

# Run tests with minimal output (for CI)
make test-fast

# Run specific test suites
make test-schemas        # Schema validation tests
make test-mechanics      # Mechanics engine tests

# Code quality
make lint                # Run flake8 linter
make format              # Format code with black + isort
make format-check        # Check formatting without changes

# Cleanup
make clean-test          # Remove test artifacts (__pycache__, .pytest_cache, etc.)
```

### Using pytest Directly

```bash
# Activate venv (from project root)
cd scripts
source aeonisk/.venv/bin/activate

# Run all tests
python -m pytest ../tests/ -v

# Run specific test file
python -m pytest ../tests/unit/test_schemas.py -v

# Run specific test class
python -m pytest ../tests/unit/test_schemas.py::TestSharedTypes -v

# Run specific test
python -m pytest ../tests/unit/test_schemas.py::TestSharedTypes::test_void_change_valid -v

# Run with coverage
python -m pytest ../tests/ --cov=aeonisk/multiagent --cov-report=html

# Run async tests
python -m pytest ../tests/integration/ -v --asyncio-mode=auto
```

## Writing Tests

### Basic Test Structure

```python
import pytest
from aeonisk.multiagent.schemas.action_resolution import ActionResolution, MechanicalEffects
from aeonisk.multiagent.schemas.shared_types import SuccessTier, VoidChange

def test_action_resolution_with_void():
    """Test ActionResolution with void corruption."""
    resolution = ActionResolution(
        narration="The ritual fails. Void energy corrupts your mind." * 10,
        success_tier=SuccessTier.FAILURE,
        margin=-5,
        effects=MechanicalEffects(
            void_changes=[
                VoidChange(character_name="TestChar", amount=2, reason="Failed ritual")
            ]
        )
    )

    assert resolution.success_tier == SuccessTier.FAILURE
    assert len(resolution.effects.void_changes) == 1
    assert resolution.effects.void_changes[0].amount == 2
```

### Using Fixtures

```python
def test_with_mechanics_engine(mechanics_engine):
    """Test using the mechanics_engine fixture."""
    # mechanics_engine is automatically initialized without logging
    resolution = mechanics_engine.resolve_action(
        attribute_value=4,
        skill_value=3,
        difficulty=20
    )

    assert resolution is not None
    assert hasattr(resolution, 'total')
```

### Using Mock LLM Client

```python
from tests.mocks import MockLLMClient, MockLLMProvider

@pytest.mark.asyncio
async def test_with_mock_llm():
    """Test with mocked LLM responses."""
    # Create mock with canned responses
    mock_llm = MockLLMProvider(
        responses=[
            "First response from LLM",
            "Second response from LLM"
        ]
    )

    # Use in test
    response1 = await mock_llm.generate(
        messages=[{"role": "user", "content": "Test prompt"}]
    )

    assert response1 == "First response from LLM"
    assert mock_llm.client.call_count == 1
```

### Testing Async Code

```python
import pytest
from tests.helpers import wait_for_condition, run_with_timeout

@pytest.mark.asyncio
async def test_async_functionality():
    """Test async code."""
    result = await some_async_function()

    # Wait for condition
    await wait_for_condition(
        condition=lambda: result.status == "complete",
        timeout=5.0
    )

    assert result.status == "complete"
```

## Test Fixtures

### Provided by `conftest.py`

- `test_data_dir` - Path to `tests/fixtures/`
- `llm_responses_dir` - Path to `tests/fixtures/llm_responses/`
- `sample_session_config` - Minimal session config for testing
- `sample_character_state` - Sample CharacterState instance
- `sample_enemy_state` - Sample enemy state dict
- `sample_clock` - Sample scene clock dict
- `mock_mechanics_engine` - Mocked MechanicsEngine
- `real_mechanics_engine` - Real MechanicsEngine (async, no logging)
- `mock_llm_response` - Sample LLM response structure
- `mock_anthropic_client` - Mocked Anthropic API client
- `load_llm_fixture` - Helper to load LLM response fixtures from JSON
- `mock_shared_state` - Mocked SharedState with test characters
- `assert_valid_jsonl` - Helper to validate JSONL log entries
- `seed_random` - Seed random for deterministic tests

### Custom Fixtures

Create custom fixtures in `conftest.py` or in individual test files:

```python
@pytest.fixture
def custom_character():
    """Create a custom character for testing."""
    from tests.helpers import CharacterBuilder

    return CharacterBuilder()        .with_name("TestHero")
        .with_class("Witch")
        .with_skill("Occult", 4)
        .with_void(3)
        .build()
```

## Mock Infrastructure

### MockLLMClient

Deterministic LLM client for testing:

```python
from tests.mocks import MockLLMClient

# Fixed response
client = MockLLMClient(responses="Fixed response")

# Sequential responses
client = MockLLMClient(responses=[
    "First response",
    "Second response",
    "Third response"
])

# Response cache (keyed by prompt hash)
client = MockLLMClient(response_cache={
    "prompt_hash_123": "Cached response for specific prompt"
})

# Load from fixtures
client = MockLLMClient(fixtures_dir=Path("tests/fixtures/llm_responses"))
```

### MockLLMProvider

Matches the real LLMProvider interface:

```python
from tests.mocks import MockLLMProvider

provider = MockLLMProvider(
    responses=["DM narration here", "Player action", "Enemy decision"]
)

# Use like real provider
response = await provider.generate(
    messages=[{"role": "user", "content": "Your prompt"}],
    system_prompt="System instructions"
)

# Check call history
assert provider.client.call_count == 1
assert provider.client.call_history[0]["temperature"] == 1.0
```

## Test Helpers

### SessionBuilder

Easily construct test sessions:

```python
from tests.helpers import TestSessionBuilder

session = await TestSessionBuilder()
    .with_players(2, names=["Alice", "Bob"])
    .with_enemies("shadow_creature", count=1)
    .with_scenario({"theme": "combat_test"})
    .with_mock_llm(mock_client)
    .with_max_rounds(3)
    .disable_logging()
    .build()
```

### CharacterBuilder

Build test characters:

```python
from tests.helpers import CharacterBuilder

char = CharacterBuilder()
    .with_name("TestHero")
    .with_class("Hacker")
    .with_level(3)
    .with_skill("Technical", 4)
    .with_skill("Notice", 3)
    .with_void(2)
    .with_bond("Ally", level=2)
    .build()
```

### Async Helpers

```python
from tests.helpers import (
    wait_for_condition,
    run_with_timeout,
    collect_async_results
)

# Wait for condition
await wait_for_condition(
    condition=lambda: game_state.round_number == 3,
    timeout=5.0
)

# Run with timeout
result = await run_with_timeout(slow_operation(), timeout=2.0, default=None)

# Collect from async generator
results = await collect_async_results(async_gen, max_items=10)
```

## Creating Test Fixtures

### Hand-Crafted LLM Responses

Create JSON files in `tests/fixtures/llm_responses/manual/`:

```json
{
  "fixture_name": "dm_scenario_basic",
  "description": "Basic DM scenario generation",
  "prompt": "Generate a scenario for 2 players...",
  "response": "You find yourselves in a dimly lit cargo bay..."
}
```

### Recorded LLM Responses

Run real sessions and save responses to `tests/fixtures/llm_responses/recorded/`:

```bash
# TODO: Add recording script
python scripts/record_llm_responses.py --session-id test_001 --output tests/fixtures/llm_responses/recorded/
```

## Continuous Integration

### GitHub Actions (Example)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: make install-test-deps
      - name: Run tests
        run: make test-cov
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Best Practices

### Do's

✅ **Use fixtures** - Leverage `conftest.py` fixtures for common setup
✅ **Mock LLM calls** - Never make real API calls in tests
✅ **Seed random** - Use `seed_random` fixture for deterministic dice rolls
✅ **Test edge cases** - Test boundary conditions, empty inputs, invalid data
✅ **Use descriptive names** - `test_action_resolution_with_void_corruption` not `test_1`
✅ **Keep tests fast** - Unit tests should run in milliseconds
✅ **Assert specific values** - `assert result == 5` not `assert result > 0`

### Don'ts

❌ **Don't call real LLM APIs** - Always use mocks
❌ **Don't use time.sleep()** - Use async await or mocked timers
❌ **Don't test implementation details** - Test behavior, not internals
❌ **Don't create large test files** - Split by component (schemas, mechanics, etc.)
❌ **Don't skip cleanup** - Use fixtures with yield or try/finally
❌ **Don't use hardcoded paths** - Use `test_data_dir` fixture or Path(__file__)

## Debugging Tests

### Run with verbose output

```bash
make test -v
```

### Run single test with debugging

```bash
cd scripts
source aeonisk/.venv/bin/activate
python -m pytest ../tests/unit/test_schemas.py::test_void_change_valid -vv -s
```

### Use pytest debugging

```bash
# Drop into debugger on failure
python -m pytest ../tests/ --pdb

# Drop into debugger at start of test
python -m pytest ../tests/ --trace
```

### Check test collection

```bash
# List all tests without running
python -m pytest ../tests/ --collect-only
```

## Coverage Goals

Current test coverage:

- ✅ **Schemas** - 37 tests, comprehensive coverage
- 🟡 **Mechanics** - Basic coverage, needs expansion
- ❌ **Outcome Parser** - Not yet tested
- ❌ **Shared State** - Not yet tested
- ❌ **Integration** - No tests yet

**Target: 80%+ coverage of core multi-agent system**

## Contributing

When adding new features:

1. **Write tests first** (TDD approach)
2. **Add unit tests** for new functions/classes
3. **Add integration tests** for new workflows
4. **Update fixtures** if new LLM responses needed
5. **Run full test suite** before committing
6. **Check coverage** - aim for 80%+ on new code

```bash
# Before committing
make test
make lint
make format-check
```

## Troubleshooting

### Import Errors

```
ModuleNotFoundError: No module named 'aeonisk'
```

**Solution**: Run tests from `scripts/` directory or use Makefile

### Async Test Warnings

```
Warning: pytest-asyncio not configured
```

**Solution**: Add `--asyncio-mode=auto` or use `make test-integration`

### Coverage Not Working

**Solution**: Ensure pytest-cov is installed:

```bash
make install-test-deps
```

### Tests Hanging

**Solution**: Check for missing `await` in async tests or infinite loops

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Pydantic Testing](https://docs.pydantic.dev/latest/concepts/testing/)
- [unittest.mock Guide](https://docs.python.org/3/library/unittest.mock.html)

## License

Same as project license (see root LICENSE file).
