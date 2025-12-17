"""
Unit tests for DM scenario generation with agent prompt logging.

Tests that scenario generation properly estimates token counts when logging to agent_prompt_logger.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup, NewClock


@pytest.mark.asyncio
async def test_scenario_generation_token_estimation():
    """Test that scenario generation estimates tokens when logging to agent_prompt_logger."""
    # Import after setting up test to avoid import-time issues
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    # Create valid scenario for mocking
    mock_scenario = ScenarioSetup(
        theme="Corporate Espionage and Void Corruption",
        location="Corrupted Research Station Sub-Level 7",
        situation="The party has been sent to infiltrate a corporate research facility to steal prototype void scanning equipment. However, upon arrival they discover that something has gone terribly wrong.",
        void_level=3,
        starting_clocks=[
            NewClock(
                name="Security Lockdown",
                max_ticks=8,
                description="Station security protocol activates",
                advance_meaning="lockdown progresses",
                regress_meaning="lockdown delayed",
                filled_consequence="Facility fully locked down, no escape"
            )
        ],
        success_conditions="Extract the prototype void scanner and escape before the facility locks down completely",
        failure_consequences="Captured by corporate security, exposed to critical void corruption, or trapped in the collapsing facility"
    )

    # Create mock LLM provider
    mock_llm_provider = Mock()
    mock_llm_provider.generate_structured = AsyncMock(return_value=mock_scenario)

    # Create mock agent prompt logger to spy on log_llm_call
    mock_agent_logger = Mock()
    mock_agent_logger.log_llm_call = Mock()

    # Create mock LLM logger
    mock_llm_logger = Mock()
    mock_llm_logger.call_count = 0

    # Create DM with minimal required args
    mock_shared_state = Mock()
    mock_shared_state.get_mechanics_engine = Mock(return_value=None)

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={'model': 'claude-sonnet-4-5', 'temperature': 1.0},
        shared_state=mock_shared_state
    )

    # Inject mocks
    dm.llm_provider = mock_llm_provider
    dm.agent_prompt_logger = mock_agent_logger
    dm.llm_logger = mock_llm_logger

    # This should NOT crash with NameError for estimated_input_tokens/estimated_output_tokens
    scenario = await dm._generate_scenario_structured(
        scenario_prompt="Generate a test scenario for infiltration mission",
        system_prompt="You are the DM",
        scenario_hint=""
    )

    # Verify scenario was generated
    assert scenario is not None
    assert scenario.theme == "Corporate Espionage and Void Corruption"

    # Verify agent prompt logger was called with valid token estimates
    assert mock_agent_logger.log_llm_call.called, "Expected log_llm_call to be invoked"

    call_kwargs = mock_agent_logger.log_llm_call.call_args[1]
    assert 'tokens' in call_kwargs, "Expected 'tokens' in log_llm_call kwargs"
    assert 'input' in call_kwargs['tokens'], "Expected 'input' in tokens dict"
    assert 'output' in call_kwargs['tokens'], "Expected 'output' in tokens dict"

    # Verify tokens are integers
    assert isinstance(call_kwargs['tokens']['input'], int), f"Expected int input tokens, got {type(call_kwargs['tokens']['input'])}"
    assert isinstance(call_kwargs['tokens']['output'], int), f"Expected int output tokens, got {type(call_kwargs['tokens']['output'])}"

    # Verify tokens are reasonable (> 0)
    assert call_kwargs['tokens']['input'] > 0, "Expected positive input token count"
    assert call_kwargs['tokens']['output'] > 0, "Expected positive output token count"

    # Verify tokens estimation is reasonable (1 token ≈ 4 chars)
    prompt_len = len("Generate a test scenario for infiltration mission")
    estimated_min_input = prompt_len // 6  # conservative lower bound
    estimated_max_input = prompt_len // 2  # conservative upper bound

    assert estimated_min_input <= call_kwargs['tokens']['input'] <= estimated_max_input, \
        f"Input token estimate {call_kwargs['tokens']['input']} outside expected range [{estimated_min_input}, {estimated_max_input}]"
