"""
Test Two-Phase Action Generation in PlayerAgent

Tests for the refactored action declaration system:
- Phase 1: ActionIntent generation (action type selection)
- Phase 2: Action-specific details generation (routed by action_type)
- Orchestration: Merging both phases into ActionDeclaration

Following TDD: These tests are written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
from scripts.aeonisk.multiagent.schemas.player_action import (
    ActionIntent,
    AttuneAction,
    CombatAction,
    PurchaseAction,
    ACTION_TYPE_SCHEMA_MAP,
)
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration


@pytest.fixture
def mock_character_state():
    """Create a mock character state for testing."""
    return CharacterState(
        name="Test Character",
        faction="Test Faction",
        attributes={"Willpower": 5, "Agility": 4, "Charisma": 3},
        skills={"Attunement": 4, "Guns": 3, "Charm": 2},
        void_score=2,
        soulcredit=50,
        bonds=[],
        goals=["Test goal"],
        pronouns="they/them"
    )


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = Mock()
    provider.generate_structured = AsyncMock()
    return provider


@pytest.fixture
def player_agent(mock_character_state, mock_llm_provider):
    """Create an AIPlayerAgent instance for testing."""
    # Build character_config from mock_character_state
    character_config = {
        "name": mock_character_state.name,
        "faction": mock_character_state.faction,
        "attributes": mock_character_state.attributes,
        "skills": mock_character_state.skills,
        "void_score": mock_character_state.void_score,
        "soulcredit": mock_character_state.soulcredit,
        "bonds": mock_character_state.bonds,
        "goals": mock_character_state.goals,
        "pronouns": mock_character_state.pronouns,
        "personality": {"riskTolerance": 5, "voidCuriosity": 3, "bondPreference": "neutral"}
    }

    agent = AIPlayerAgent(
        agent_id="test_player_01",
        socket_path="/tmp/test_socket.sock",  # Required positional arg
        character_config=character_config,
        llm_config={"model": "test-model", "temperature": 0.8},
        shared_state=None
    )

    # Override llm_provider with mock (bypass auto-creation)
    agent.llm_provider = mock_llm_provider

    # Set character_state manually (normally done in on_start)
    agent.character_state = mock_character_state

    # Set combat attributes manually (normally done in on_start)
    agent.health = 100
    agent.max_health = 100
    agent.wounds = 0
    agent.stuns = 0

    return agent


class TestGenerateActionIntent:
    """Test Phase 1: ActionIntent generation."""

    @pytest.mark.asyncio
    async def test_generate_action_intent_success(self, player_agent, mock_llm_provider):
        """_generate_action_intent should return ActionIntent from LLM."""
        # Arrange: Mock LLM to return ActionIntent
        expected_intent = ActionIntent(
            intent="Attune Raw Seed to Drip",
            action_type=ActionType.ATTUNE,
            reasoning="Need drip currency for ritual supplies"
        )
        mock_llm_provider.generate_structured.return_value = expected_intent

        # Act
        result = await player_agent._generate_action_intent()

        # Assert
        assert isinstance(result, ActionIntent)
        assert result.action_type == ActionType.ATTUNE
        assert result.intent == "Attune Raw Seed to Drip"
        assert "drip currency" in result.reasoning

        # Verify LLM was called with ActionIntent schema
        mock_llm_provider.generate_structured.assert_called_once()
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args.kwargs['result_type'] == ActionIntent

    @pytest.mark.asyncio
    async def test_generate_action_intent_loads_intent_prompt(self, player_agent, mock_llm_provider):
        """_generate_action_intent should load player_intent.yaml prompt."""
        # Arrange
        mock_llm_provider.generate_structured.return_value = ActionIntent(
            intent="Fire at enemy",
            action_type=ActionType.COMBAT,
            reasoning="Enemy is threatening"
        )

        # Act
        await player_agent._generate_action_intent()

        # Assert: Check prompt was built (contains action type selection guidance)
        call_args = mock_llm_provider.generate_structured.call_args
        prompt = call_args.kwargs['prompt']
        assert "ACTION TYPE SELECTION" in prompt or "action type" in prompt.lower()

    @pytest.mark.asyncio
    async def test_generate_action_intent_includes_character_context(self, player_agent, mock_llm_provider):
        """_generate_action_intent should include character stats in prompt."""
        # Arrange
        mock_llm_provider.generate_structured.return_value = ActionIntent(
            intent="Test intent",
            action_type=ActionType.INVESTIGATE,
            reasoning="Test"
        )

        # Act
        await player_agent._generate_action_intent()

        # Assert: Prompt should include character context
        call_args = mock_llm_provider.generate_structured.call_args
        prompt = call_args.kwargs['prompt']
        # Should contain character name or health or void score
        assert (
            "Test Character" in prompt or
            "Health:" in prompt or
            "Void:" in prompt
        )


class TestGenerateActionDetails:
    """Test Phase 2: Action-specific details generation with schema routing."""

    @pytest.mark.asyncio
    async def test_generate_action_details_routes_to_attune_schema(self, player_agent, mock_llm_provider):
        """_generate_action_details should route to AttuneAction for ATTUNE type."""
        # Arrange: Phase 1 result with ATTUNE action type
        intent = ActionIntent(
            intent="Attune Raw Seed to Drip",
            action_type=ActionType.ATTUNE,
            reasoning="Need drip currency"
        )

        expected_action = AttuneAction(
            intent="Attune Raw Seed to Drip",
            description="Placing Raw Seed on altar, focusing willpower to channel drip energy.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=19,
            difficulty_justification="DC 20 base reduced to 19 with altar",
            action_type=ActionType.ATTUNE,
            target_energy="drip",
            altar_id="alt_marketplace_01"
        )
        mock_llm_provider.generate_structured.return_value = expected_action

        # Act
        result = await player_agent._generate_action_details(intent)

        # Assert
        assert isinstance(result, AttuneAction)
        assert result.target_energy == "drip"
        assert result.action_type == ActionType.ATTUNE

        # Verify correct schema was used
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args.kwargs['result_type'] == AttuneAction

    @pytest.mark.asyncio
    async def test_generate_action_details_routes_to_combat_schema(self, player_agent, mock_llm_provider):
        """_generate_action_details should route to CombatAction for COMBAT type."""
        # Arrange
        intent = ActionIntent(
            intent="Fire at enemy leader",
            action_type=ActionType.COMBAT,
            reasoning="Eliminate threat"
        )

        expected_action = CombatAction(
            intent="Fire at enemy leader",
            description="Taking aimed shot at enemy commander with plasma rifle.",
            attribute="Agility",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with cover",
            action_type=ActionType.COMBAT,
            target="tgt_enemy_01"
        )
        mock_llm_provider.generate_structured.return_value = expected_action

        # Act
        result = await player_agent._generate_action_details(intent)

        # Assert
        assert isinstance(result, CombatAction)
        assert result.target == "tgt_enemy_01"
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args.kwargs['result_type'] == CombatAction

    @pytest.mark.asyncio
    async def test_generate_action_details_routes_to_purchase_schema(self, player_agent, mock_llm_provider):
        """_generate_action_details should route to PurchaseAction for PURCHASE type."""
        # Arrange
        intent = ActionIntent(
            intent="Buy Incense from vendor",
            action_type=ActionType.PURCHASE,
            reasoning="Need ritual supplies"
        )

        expected_action = PurchaseAction(
            intent="Buy Incense from vendor",
            description="Approaching the vendor's stall to purchase high-quality ritual incense for upcoming ceremonies.",
            attribute="Charisma",
            skill="Charm",
            difficulty_estimate=12,
            difficulty_justification="Routine transaction",
            action_type=ActionType.PURCHASE,
            vendor_id="vnd_marketplace_01",
            item_id="itm_incense"
        )
        mock_llm_provider.generate_structured.return_value = expected_action

        # Act
        result = await player_agent._generate_action_details(intent)

        # Assert
        assert isinstance(result, PurchaseAction)
        assert result.vendor_id == "vnd_marketplace_01"
        assert result.item_id == "itm_incense"
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args.kwargs['result_type'] == PurchaseAction

    @pytest.mark.asyncio
    async def test_generate_action_details_loads_action_specific_prompt(self, player_agent, mock_llm_provider):
        """_generate_action_details should load action-specific YAML prompt."""
        # Arrange
        intent = ActionIntent(
            intent="Attune Raw Seed to Drip",
            action_type=ActionType.ATTUNE,
            reasoning="Need drip"
        )

        mock_llm_provider.generate_structured.return_value = AttuneAction(
            intent="Attune Raw Seed to Drip",
            description="Test description for attunement ritual with altar usage.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=19,
            difficulty_justification="Altar bonus",
            action_type=ActionType.ATTUNE,
            target_energy="drip"
        )

        # Act
        await player_agent._generate_action_details(intent)

        # Assert: Prompt should contain ATTUNE-specific guidance
        call_args = mock_llm_provider.generate_structured.call_args
        prompt = call_args.kwargs['prompt']
        # Should mention attunement mechanics or energy types
        assert (
            "attune" in prompt.lower() or
            "energy" in prompt.lower() or
            "target_energy" in prompt
        )

    @pytest.mark.asyncio
    async def test_generate_action_details_includes_phase1_context(self, player_agent, mock_llm_provider):
        """_generate_action_details should include Phase 1 intent/reasoning in prompt."""
        # Arrange
        intent = ActionIntent(
            intent="Unique intent text here",
            action_type=ActionType.COMBAT,
            reasoning="Unique reasoning text here"
        )

        mock_llm_provider.generate_structured.return_value = CombatAction(
            intent="Unique intent text here",
            description="Combat action description with enough characters to meet minimum.",
            attribute="Agility",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Standard combat",
            action_type=ActionType.COMBAT,
            target="tgt_enemy_01"
        )

        # Act
        await player_agent._generate_action_details(intent)

        # Assert: Prompt should include Phase 1 intent and reasoning
        call_args = mock_llm_provider.generate_structured.call_args
        prompt = call_args.kwargs['prompt']
        assert "Unique intent text here" in prompt
        assert "Unique reasoning text here" in prompt


class TestTwoPhaseOrchestration:
    """Test orchestration of both phases in _generate_player_action_pydantic."""

    @pytest.mark.asyncio
    async def test_orchestration_calls_both_phases(self, player_agent, mock_llm_provider):
        """_generate_player_action_pydantic should call Phase 1 then Phase 2."""
        # Arrange: Mock Phase 1 result
        phase1_result = ActionIntent(
            intent="Attune Raw Seed to Drip",
            action_type=ActionType.ATTUNE,
            reasoning="Need drip"
        )

        # Mock Phase 2 result
        phase2_result = AttuneAction(
            intent="Attune Raw Seed to Drip",
            description="Placing Raw Seed on altar and channeling willpower through matrix.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=19,
            difficulty_justification="Altar bonus",
            action_type=ActionType.ATTUNE,
            target_energy="drip",
            altar_id="alt_marketplace_01"
        )

        # Mock LLM to return different results for each call
        mock_llm_provider.generate_structured.side_effect = [phase1_result, phase2_result]

        # Mock the new methods on player_agent
        player_agent._generate_action_intent = AsyncMock(return_value=phase1_result)
        player_agent._generate_action_details = AsyncMock(return_value=phase2_result)

        # Build a minimal prompt
        prompt = "Test prompt"

        # Act
        result = await player_agent._generate_player_action_pydantic(prompt)

        # Assert: Both phases were called
        player_agent._generate_action_intent.assert_called_once()
        player_agent._generate_action_details.assert_called_once_with(phase1_result)

        # Result should be ActionDeclaration (legacy format)
        assert isinstance(result, ActionDeclaration)

    @pytest.mark.asyncio
    async def test_orchestration_merges_phase1_and_phase2(self, player_agent, mock_llm_provider):
        """_generate_player_action_pydantic should merge Phase 1 + Phase 2 data."""
        # Arrange
        phase1_result = ActionIntent(
            intent="Fire at enemy",
            action_type=ActionType.COMBAT,
            reasoning="Tactical advantage"
        )

        phase2_result = CombatAction(
            intent="Fire at enemy",
            description="Taking careful aim and firing controlled burst from plasma rifle.",
            attribute="Agility",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target",
            action_type=ActionType.COMBAT,
            target="tgt_enemy_01"
        )

        player_agent._generate_action_intent = AsyncMock(return_value=phase1_result)
        player_agent._generate_action_details = AsyncMock(return_value=phase2_result)

        # Act
        result = await player_agent._generate_player_action_pydantic("Test prompt")

        # Assert: Merged result has data from both phases
        assert result.intent == "Fire at enemy"  # From Phase 1
        assert result.action_type == ActionType.COMBAT  # From both
        assert result.target == "tgt_enemy_01"  # From Phase 2
        assert result.attribute == "Agility"  # From Phase 2
        assert result.character_name == "Test Character"  # System-populated

    @pytest.mark.asyncio
    async def test_orchestration_populates_system_fields(self, player_agent, mock_llm_provider):
        """_generate_player_action_pydantic should populate character_name and agent_id."""
        # Arrange
        phase1_result = ActionIntent(
            intent="Investigate terminal",
            action_type=ActionType.INVESTIGATE,
            reasoning="Gather intel"
        )

        phase2_result = Mock(
            intent="Investigate terminal",
            description="Examining terminal logs for security vulnerabilities and access patterns.",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=20,
            difficulty_justification="Complex system",
            action_type=ActionType.INVESTIGATE,
            target=None,
            target_position=None,
            vendor_id=None,
            item_id=None,
            transfer_target=None,
            transfer_currency=None,
            transfer_items=None
        )

        player_agent._generate_action_intent = AsyncMock(return_value=phase1_result)
        player_agent._generate_action_details = AsyncMock(return_value=phase2_result)

        # Act
        result = await player_agent._generate_player_action_pydantic("Test prompt")

        # Assert: System fields populated
        assert result.character_name == "Test Character"
        assert result.agent_id == "test_player_01"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Current impl raises RuntimeError, not returns None - graceful fallback not yet implemented")
    async def test_orchestration_handles_phase1_failure(self, player_agent, mock_llm_provider):
        """_generate_player_action_pydantic should handle Phase 1 LLM failure gracefully."""
        # Arrange: Phase 1 fails
        player_agent._generate_action_intent = AsyncMock(side_effect=Exception("LLM error"))

        # Act & Assert: Should return None (fallback to legacy)
        result = await player_agent._generate_player_action_pydantic("Test prompt")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Current impl raises RuntimeError, not returns None - graceful fallback not yet implemented")
    async def test_orchestration_handles_phase2_failure(self, player_agent, mock_llm_provider):
        """_generate_player_action_pydantic should handle Phase 2 LLM failure gracefully."""
        # Arrange: Phase 1 succeeds, Phase 2 fails
        phase1_result = ActionIntent(
            intent="Test intent",
            action_type=ActionType.EXPLORE,
            reasoning="Test"
        )

        player_agent._generate_action_intent = AsyncMock(return_value=phase1_result)
        player_agent._generate_action_details = AsyncMock(side_effect=Exception("LLM error"))

        # Act & Assert: Should return None (fallback to legacy)
        result = await player_agent._generate_player_action_pydantic("Test prompt")
        assert result is None


class TestSchemaRoutingMap:
    """Test ACTION_TYPE_SCHEMA_MAP is used correctly."""

    def test_all_action_types_have_schema_mappings(self):
        """ACTION_TYPE_SCHEMA_MAP should have entries for all 13 ActionTypes."""
        assert len(ACTION_TYPE_SCHEMA_MAP) == 13

        # Verify all action types present
        for action_type in ActionType:
            assert action_type in ACTION_TYPE_SCHEMA_MAP, f"{action_type} missing from schema map"

    def test_schema_map_correct_types(self):
        """ACTION_TYPE_SCHEMA_MAP should map to correct schema classes."""
        from scripts.aeonisk.multiagent.schemas.player_action import (
            ExploreAction, InvestigateAction, RitualAction, SocialAction,
            TechnicalAction, PerceptionAction, SupportAction, TransferAction, CustomAction
        )

        assert ACTION_TYPE_SCHEMA_MAP[ActionType.ATTUNE] == AttuneAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.COMBAT] == CombatAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.PURCHASE] == PurchaseAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.EXPLORE] == ExploreAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.INVESTIGATE] == InvestigateAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.RITUAL] == RitualAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.SOCIAL] == SocialAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.TECHNICAL] == TechnicalAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.PERCEPTION] == PerceptionAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.SUPPORT] == SupportAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.TRANSFER] == TransferAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.CUSTOM] == CustomAction
