"""
Test retry logic for DM scenario generation with Pydantic validation errors.

Tests that the DM retries scenario generation when the batch proxy returns
malformed responses that cause Pydantic validation errors or JSON decode errors.
"""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_scenario_generation_retries_on_pydantic_validation_error():
    """
    Test that DM retries scenario generation when Pydantic validation fails.

    Simulates batch proxy returning malformed data that causes ValidationError
    on first 2 attempts, then succeeds on 3rd attempt.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Create valid scenario to return on 3rd attempt
    from scripts.aeonisk.multiagent.schemas.story_events import NewClock

    valid_scenario = ScenarioSetup(
        theme="Test Scenario",
        location="Test Location",
        situation="A test situation scenario that provides enough detail to meet minimum character requirements for validation",
        void_level=3,
        starting_clocks=[
            NewClock(
                name="Test Clock",
                current_ticks=0,
                max_ticks=4,
                description="A test clock for validation",
                advance_meaning="clock progresses",
                regress_meaning="clock regresses",
                filled_consequence="test consequence occurs"
            )
        ],
        success_conditions="Successfully win the scenario by completing objectives",
        failure_consequences="Lose the scenario badly",
        initial_npcs=[],
        initial_enemies=[]
    )

    # Mock LLM provider
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider

    # First 2 calls raise ValidationError, 3rd succeeds
    # Note: We simulate the errors by actually creating invalid schemas first
    try:
        # This will raise ValidationError
        ScenarioSetup(theme="", location="", situation="", void_level=-1, starting_clocks=[], success_conditions="", failure_consequences="", initial_npcs=[], initial_enemies=[])
    except ValidationError as e:
        validation_error_1 = e

    try:
        # Another invalid scenario
        ScenarioSetup(theme="x"*300, location="x"*300, situation="x"*1000, void_level=99, starting_clocks=[], success_conditions="x", failure_consequences="x", initial_npcs=[], initial_enemies=[])
    except ValidationError as e:
        validation_error_2 = e

    mock_provider.generate_structured.side_effect = [
        validation_error_1,
        validation_error_2,
        valid_scenario
    ]

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation
    result = await dm._generate_scenario_structured(
        scenario_prompt="Generate test scenario",
        system_prompt="Test system prompt"
    )

    # Verify result is valid scenario
    assert result is not None
    assert result.theme == "Test Scenario"
    assert result.location == "Test Location"

    # Verify we made 3 attempts
    assert mock_provider.generate_structured.call_count == 3


@pytest.mark.asyncio
async def test_scenario_generation_fails_after_max_retries():
    """
    Test that DM fails after exhausting all retry attempts.

    Simulates batch proxy consistently returning malformed data.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Mock LLM provider that always fails
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider

    # All calls raise ValidationError
    mock_provider.generate_structured.side_effect = ValidationError.from_exception_data(
        "ScenarioSetup",
        [{"type": "list_type", "loc": ("vendor_inventory",), "msg": "Input should be a valid list"}]
    )

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation - should raise RuntimeError after 3 attempts
    with pytest.raises(RuntimeError, match="Scenario generation failed after 3 attempts"):
        await dm._generate_scenario_structured(
            scenario_prompt="Generate test scenario",
            system_prompt="Test system prompt"
        )

    # Verify we made exactly 3 attempts
    assert mock_provider.generate_structured.call_count == 3


@pytest.mark.asyncio
async def test_scenario_generation_succeeds_on_first_try():
    """
    Test that DM succeeds immediately when no validation errors occur.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Create valid scenario
    from scripts.aeonisk.multiagent.schemas.story_events import NewClock

    valid_scenario = ScenarioSetup(
        theme="Test Scenario",
        location="Test Location",
        situation="A test situation scenario that provides enough detail to meet minimum character requirements for validation",
        void_level=3,
        starting_clocks=[
            NewClock(
                name="Test Clock",
                current_ticks=0,
                max_ticks=4,
                description="A test clock for validation",
                advance_meaning="clock progresses",
                regress_meaning="clock regresses",
                filled_consequence="test consequence occurs"
            )
        ],
        success_conditions="Successfully win the scenario by completing objectives",
        failure_consequences="Lose the scenario badly",
        initial_npcs=[],
        initial_enemies=[]
    )

    # Mock LLM provider
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider
    mock_provider.generate_structured.return_value = valid_scenario

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation
    result = await dm._generate_scenario_structured(
        scenario_prompt="Generate test scenario",
        system_prompt="Test system prompt"
    )

    # Verify result
    assert result is not None
    assert result.theme == "Test Scenario"

    # Verify only 1 attempt was made
    assert mock_provider.generate_structured.call_count == 1


@pytest.mark.asyncio
async def test_scenario_generation_non_validation_error_fails_immediately():
    """
    Test that non-ValidationError exceptions fail immediately without retry.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Mock LLM provider that raises network error
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider
    mock_provider.generate_structured.side_effect = ConnectionError("Network failure")

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation - should fail immediately
    with pytest.raises(RuntimeError, match="Scenario generation failed"):
        await dm._generate_scenario_structured(
            scenario_prompt="Generate test scenario",
            system_prompt="Test system prompt"
        )

    # Verify only 1 attempt was made (no retry for non-validation errors)
    assert mock_provider.generate_structured.call_count == 1


@pytest.mark.asyncio
async def test_scenario_generation_retries_on_json_decode_error():
    """
    Test that DM retries scenario generation when JSON decoding fails.

    Simulates batch proxy returning empty response that causes JSONDecodeError
    on first 2 attempts, then succeeds on 3rd attempt.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent
    from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup, NewClock

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Create valid scenario to return on 3rd attempt
    valid_scenario = ScenarioSetup(
        theme="Test Scenario",
        location="Test Location",
        situation="A test situation scenario that provides enough detail to meet minimum character requirements for validation",
        void_level=3,
        starting_clocks=[
            NewClock(
                name="Test Clock",
                current_ticks=0,
                max_ticks=4,
                description="A test clock for validation",
                advance_meaning="clock progresses",
                regress_meaning="clock regresses",
                filled_consequence="test consequence occurs"
            )
        ],
        success_conditions="Successfully win the scenario by completing objectives",
        failure_consequences="Lose the scenario badly",
        initial_npcs=[],
        initial_enemies=[]
    )

    # Mock LLM provider
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider

    # Create JSONDecodeError (simulates empty response from batch proxy)
    json_error_1 = json.JSONDecodeError("Expecting value", "", 0)
    json_error_2 = json.JSONDecodeError("Expecting value", "", 0)

    # First 2 calls raise JSONDecodeError, 3rd succeeds
    mock_provider.generate_structured.side_effect = [
        json_error_1,
        json_error_2,
        valid_scenario
    ]

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation
    result = await dm._generate_scenario_structured(
        scenario_prompt="Generate test scenario",
        system_prompt="Test system prompt"
    )

    # Verify result is valid scenario
    assert result is not None
    assert result.theme == "Test Scenario"
    assert result.location == "Test Location"

    # Verify we made 3 attempts
    assert mock_provider.generate_structured.call_count == 3


@pytest.mark.asyncio
async def test_scenario_generation_fails_after_max_json_decode_retries():
    """
    Test that DM fails after exhausting all retry attempts on JSONDecodeError.

    Simulates batch proxy consistently returning empty responses.
    """
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    # Create mock DM
    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test_dm.sock",
        llm_config={'provider': 'openai', 'model': 'gpt-5-mini', 'temperature': 1.0},
        shared_state=None
    )

    # Mock LLM provider that always returns empty response
    mock_provider = AsyncMock()
    dm.llm_provider = mock_provider

    # All calls raise JSONDecodeError (simulates persistent empty responses)
    mock_provider.generate_structured.side_effect = json.JSONDecodeError(
        "Expecting value: line 1 column 1 (char 0)", "", 0
    )

    # Mock llm_logger
    dm.llm_logger = MagicMock()
    dm.llm_logger.call_count = 0

    # Call scenario generation - should raise RuntimeError after 3 attempts
    with pytest.raises(RuntimeError, match="Scenario generation failed after 3 attempts"):
        await dm._generate_scenario_structured(
            scenario_prompt="Generate test scenario",
            system_prompt="Test system prompt"
        )

    # Verify we made exactly 3 attempts
    assert mock_provider.generate_structured.call_count == 3
