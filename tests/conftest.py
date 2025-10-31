"""
Pytest configuration and shared fixtures for multi-agent testing.

This module provides:
- Path configuration for importing aeonisk modules
- Async test support via pytest-asyncio
- Common fixtures for characters, mechanics, sessions
- Mock LLM client fixtures
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add scripts directory to Python path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Configure asyncio mode for pytest-asyncio
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for all async tests."""
    return asyncio.get_event_loop_policy()


# ============================================================================
# Path and Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_data_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def llm_responses_dir(test_data_dir):
    """Path to LLM response fixtures."""
    return test_data_dir / "llm_responses"


@pytest.fixture
def sample_session_config(test_data_dir):
    """Load a minimal session configuration for testing."""
    config = {
        "num_players": 2,
        "max_rounds": 3,
        "scenario_theme": "test_combat",
        "player_names": ["TestPlayer1", "TestPlayer2"],
        "log_dir": str(test_data_dir / "sample_logs"),
        "enable_enemies": True,
        "max_enemies": 2,
        "llm_provider": "mock"
    }
    return config


# ============================================================================
# Character and Game State Fixtures
# ============================================================================

@pytest.fixture
def sample_character_state():
    """Create a sample CharacterState for testing."""
    from aeonisk.multiagent.base import CharacterState

    return CharacterState(
        name="TestCharacter",
        role="player",
        character_class="Witch",
        level=3,
        max_energy=12,
        current_energy=8,
        max_health=20,
        current_health=15,
        void=3,
        stress=2,
        skills={
            "Fight": 2,
            "Occult": 4,
            "Notice": 3,
            "Athletics": 1,
            "Empathy": 2
        },
        bonds=[
            {"name": "TestPlayer2", "level": 2}
        ],
        inventory=["Ritual Chalk", "Notebook"],
        conditions=[],
        background="A curious student of the arcane arts"
    )


@pytest.fixture
def sample_enemy_state():
    """Create a sample enemy state for testing."""
    return {
        "id": "enemy_test_001",
        "name": "Shadow Creature",
        "description": "A writhing mass of darkness",
        "threat_level": 2,
        "max_health": 15,
        "current_health": 15,
        "tags": ["void-touched", "aggressive"],
        "active": True
    }


@pytest.fixture
def sample_clock():
    """Create a sample scene clock for testing."""
    return {
        "id": "clock_test_001",
        "name": "Ritual Completion",
        "segments": 6,
        "filled": 3,
        "type": "progress",
        "description": "The ritual nears completion"
    }


# ============================================================================
# Mechanics Engine Fixtures
# ============================================================================

@pytest.fixture
def mock_mechanics_engine():
    """Create a mock MechanicsEngine for testing."""
    from unittest.mock import MagicMock

    mechanics = MagicMock()
    mechanics.roll_dice = MagicMock(return_value=(15, [3, 4, 2]))  # Default roll
    mechanics.resolve_skill_check = MagicMock(return_value={
        "total": 15,
        "dice": [3, 4, 2],
        "success": True,
        "margin": 5
    })
    mechanics.apply_damage = MagicMock(return_value={"damage_dealt": 8, "new_health": 7})
    mechanics.advance_clock = MagicMock(return_value={"segments_filled": 4, "complete": False})
    mechanics.jsonl_logger = None  # No logging in unit tests

    return mechanics


@pytest.fixture
async def real_mechanics_engine(tmp_path):
    """Create a real MechanicsEngine instance for integration tests."""
    from aeonisk.multiagent.mechanics import MechanicsEngine

    log_file = tmp_path / "test_session.jsonl"
    mechanics = MechanicsEngine(
        session_id="test_session_001",
        log_file=str(log_file),
        enable_logging=False  # Disable for faster tests
    )

    yield mechanics

    # Cleanup
    if log_file.exists():
        log_file.unlink()


# ============================================================================
# LLM Provider Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_response():
    """Create a sample LLM response structure."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "This is a test response from the mock LLM."
            }
        ],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    }


@pytest.fixture
def mock_anthropic_client(mock_llm_response):
    """Create a mock Anthropic client that returns canned responses."""
    client = MagicMock()

    # Mock the messages.create method
    async def mock_create(*args, **kwargs):
        response = AsyncMock()
        response.id = mock_llm_response["id"]
        response.type = mock_llm_response["type"]
        response.role = mock_llm_response["role"]
        response.content = [MagicMock(type="text", text=mock_llm_response["content"][0]["text"])]
        response.model = mock_llm_response["model"]
        response.stop_reason = mock_llm_response["stop_reason"]
        response.usage = MagicMock(
            input_tokens=mock_llm_response["usage"]["input_tokens"],
            output_tokens=mock_llm_response["usage"]["output_tokens"]
        )
        return response

    client.messages.create = AsyncMock(side_effect=mock_create)

    return client


@pytest.fixture
def load_llm_fixture(llm_responses_dir):
    """Helper to load LLM response fixtures from JSON files."""
    def _loader(fixture_name: str, source: str = "manual") -> Dict[str, Any]:
        """
        Load an LLM response fixture.

        Args:
            fixture_name: Name of the fixture file (without .json)
            source: 'manual' or 'recorded'

        Returns:
            Dict containing the LLM response
        """
        fixture_path = llm_responses_dir / source / f"{fixture_name}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")

        with open(fixture_path, 'r') as f:
            return json.load(f)

    return _loader


# ============================================================================
# Shared State Fixtures
# ============================================================================

@pytest.fixture
async def mock_shared_state(mock_mechanics_engine, sample_character_state):
    """Create a mock SharedState for testing."""
    from aeonisk.multiagent.shared_state import SharedState

    shared_state = SharedState()

    # Add test characters
    shared_state.characters = {
        "TestPlayer1": sample_character_state,
        "TestPlayer2": {**sample_character_state.__dict__, "name": "TestPlayer2"}
    }

    # Mock mechanics engine access
    shared_state.get_mechanics_engine = MagicMock(return_value=mock_mechanics_engine)

    # Initialize basic state
    shared_state.current_scenario = {
        "description": "A test scenario for unit testing",
        "location": "Test Chamber",
        "initial_situation": "Characters find themselves in a test environment"
    }

    shared_state.scene_clocks = []
    shared_state.enemies = []
    shared_state.round_number = 1

    return shared_state


# ============================================================================
# Utility Functions
# ============================================================================

@pytest.fixture
def assert_valid_jsonl():
    """Helper to validate JSONL log entries."""
    def _validator(log_entries: list, expected_event_types: list = None):
        """
        Validate JSONL log entries.

        Args:
            log_entries: List of log entry dicts
            expected_event_types: Optional list of event types to check for
        """
        assert len(log_entries) > 0, "No log entries found"

        for entry in log_entries:
            assert "timestamp" in entry, "Missing timestamp"
            assert "event_type" in entry, "Missing event_type"
            assert "session_id" in entry, "Missing session_id"

        if expected_event_types:
            event_types = {entry["event_type"] for entry in log_entries}
            for expected in expected_event_types:
                assert expected in event_types, f"Expected event type '{expected}' not found"

    return _validator


@pytest.fixture
def seed_random():
    """Seed random number generator for deterministic tests."""
    import random
    random.seed(42)
    yield
    # Reset to non-deterministic after test
    random.seed()


# ============================================================================
# Session Fixture Loaders
# ============================================================================

@pytest.fixture
def load_jsonl_fixture():
    """Helper to load JSONL session fixtures."""
    def _loader(fixture_path: Path) -> list:
        """
        Load a JSONL session fixture.

        Args:
            fixture_path: Path to the JSONL fixture file

        Returns:
            List of event dicts
        """
        events = []
        with open(fixture_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    return _loader


@pytest.fixture
def combat_session_sample(test_data_dir, load_jsonl_fixture):
    """Load combat session sample fixture (original 1-round fixture)."""
    fixture_path = test_data_dir / "combat_session_sample.jsonl"
    return load_jsonl_fixture(fixture_path)


@pytest.fixture
def full_session_fixture(test_data_dir, load_jsonl_fixture):
    """
    Load full 5-round session fixture with mixed actions.

    Session: Debt Auction Ambush (session_9247da3c-0ccd-41b3-a3b1-739c83ac3152)
    - 123 events across 5 rounds
    - 100% action completion (15 declarations, 15 resolutions)
    - Mixed actions: combat, social, investigation, technical, ritual
    - Contains documented bugs (Bug #1: status effect targeting, Bug #2: environmental void)

    See tests/FIXTURE_ANALYSIS.md for comprehensive analysis.
    """
    fixture_path = test_data_dir / "sessions" / "session_debt_auction_ambush.jsonl"
    return load_jsonl_fixture(fixture_path)
