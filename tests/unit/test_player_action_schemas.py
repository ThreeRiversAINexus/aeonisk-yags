"""
Test Two-Phase Action Declaration Schemas

Tests for discriminated union action schemas:
- PlayerActionBase (shared fields)
- ActionIntent (Phase 1 output)
- 12 action-specific schemas (Phase 2 output)
- PlayerActionDetails (discriminated union)

Following TDD: These tests are written BEFORE implementation.
"""

import pytest
from pydantic import ValidationError, TypeAdapter
from scripts.aeonisk.multiagent.schemas.player_action import (
    PlayerActionBase,
    ActionIntent,
    ExploreAction,
    InvestigateAction,
    RitualAction,
    SocialAction,
    CombatAction,
    TechnicalAction,
    PerceptionAction,
    SupportAction,
    PurchaseAction,
    TransferAction,
    AttuneAction,
    CustomAction,
    PlayerActionDetails,
    ACTION_TYPE_SCHEMA_MAP,
)
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType, Position

# Type adapter for discriminated union parsing
player_action_details_adapter = TypeAdapter(PlayerActionDetails)


class TestActionIntent:
    """Test Phase 1 output: ActionIntent schema."""

    def test_valid_action_intent(self):
        """Valid action intent should parse successfully."""
        intent = ActionIntent(
            intent="Scan void corruption patterns",
            action_type=ActionType.TECHNICAL,
            reasoning="Technical skills are best suited for analyzing anomalous data"
        )

        assert intent.intent == "Scan void corruption patterns"
        assert intent.action_type == ActionType.TECHNICAL
        assert intent.reasoning == "Technical skills are best suited for analyzing anomalous data"

    def test_intent_min_length_validation(self):
        """Intent must be at least 10 characters."""
        with pytest.raises(ValidationError) as exc_info:
            ActionIntent(
                intent="Too short",  # Only 9 chars
                action_type=ActionType.INVESTIGATE,
                reasoning="Test"
            )

        assert "at least 10 characters" in str(exc_info.value).lower()

    def test_intent_max_length_validation(self):
        """Intent must not exceed 200 characters."""
        long_intent = "A" * 201

        with pytest.raises(ValidationError) as exc_info:
            ActionIntent(
                intent=long_intent,
                action_type=ActionType.COMBAT,
                reasoning="Test"
            )

        assert "at most 200 characters" in str(exc_info.value).lower()

    def test_action_type_required(self):
        """action_type is required."""
        with pytest.raises(ValidationError):
            ActionIntent(
                intent="Valid intent here",
                reasoning="Test"
                # action_type missing
            )


class TestPlayerActionBase:
    """Test base schema with shared fields."""

    def test_base_schema_has_core_fields(self):
        """PlayerActionBase should have all core shared fields."""
        # Note: PlayerActionBase is abstract, so we test via a concrete implementation
        # This test will verify the fields exist when we implement AttuneAction, etc.
        pass  # Implementation verified via action-specific tests


class TestExploreAction:
    """Test EXPLORE action schema."""

    def test_valid_explore_action(self):
        """Valid explore action should parse successfully."""
        action = ExploreAction(
            intent="Search northwest corridor for exit",
            description="Moving carefully through the darkened hallway, checking for void corruption or structural damage. Testing air quality with portable scanner.",
            attribute="Perception",
            skill="Investigation",
            difficulty_estimate=15,
            difficulty_justification="Moderate difficulty due to poor lighting but straightforward exploration",
            action_type=ActionType.EXPLORE,
            target_position=Position.NEAR_PC
        )

        assert action.action_type == ActionType.EXPLORE
        assert action.attribute == "Perception"
        assert action.target_position == Position.NEAR_PC

    def test_explore_action_type_must_be_explore(self):
        """action_type must be 'explore' literal."""
        with pytest.raises(ValidationError):
            ExploreAction(
                intent="Search area",
                description="Looking around the room carefully for clues or hidden passages.",
                attribute="Perception",
                skill=None,
                difficulty_estimate=12,
                difficulty_justification="Easy exploration",
                action_type=ActionType.COMBAT  # Wrong type
            )


class TestInvestigateAction:
    """Test INVESTIGATE action schema."""

    def test_valid_investigate_action(self):
        """Valid investigate action should parse successfully."""
        action = InvestigateAction(
            intent="Analyze void corruption terminal",
            description="Using technical knowledge to examine the corrupted data logs and trace their origin point.",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=22,
            difficulty_justification="Complex technical analysis under pressure",
            action_type=ActionType.INVESTIGATE,
            target="tgt_terminal_01"
        )

        assert action.action_type == ActionType.INVESTIGATE
        assert action.target == "tgt_terminal_01"


class TestCombatAction:
    """Test COMBAT action schema with required target."""

    def test_valid_combat_action_with_required_target(self):
        """Combat action requires target field."""
        action = CombatAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at the enemy leader's center mass, compensating for movement and cover.",
            attribute="Agility",
            skill="Firearms",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_enemy_01",  # REQUIRED
            target_position=Position.NEAR_ENEMY,
            situational_modifiers={"high_ground": 2}
        )

        assert action.target == "tgt_enemy_01"
        assert action.situational_modifiers == {"high_ground": 2}

    def test_combat_action_missing_target_fails(self):
        """Combat action without target should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            CombatAction(
                intent="Fire plasma rifle",
                description="Taking careful aim and firing.",
                attribute="Agility",
                skill="Firearms",
                difficulty_estimate=18,
                difficulty_justification="Standard combat",
                action_type=ActionType.COMBAT
                # target missing - should fail
            )

        assert "target" in str(exc_info.value).lower()


class TestSupportAction:
    """Test SUPPORT action schema with required target."""

    def test_valid_support_action_with_required_target(self):
        """Support action requires target field."""
        action = SupportAction(
            intent="Provide covering fire for Thresh",
            description="Suppressing enemy positions while Thresh advances to better cover.",
            attribute="Agility",
            skill="Firearms",
            difficulty_estimate=15,
            difficulty_justification="Suppression fire is easier than precision shots",
            action_type=ActionType.SUPPORT,
            target="Thresh Ireveth"  # REQUIRED
        )

        assert action.target == "Thresh Ireveth"

    def test_support_action_missing_target_fails(self):
        """Support action without target should fail validation."""
        with pytest.raises(ValidationError):
            SupportAction(
                intent="Provide covering fire",
                description="Suppressing enemy positions.",
                attribute="Agility",
                skill="Firearms",
                difficulty_estimate=15,
                difficulty_justification="Standard support",
                action_type=ActionType.SUPPORT
                # target missing - should fail
            )


class TestPurchaseAction:
    """Test PURCHASE action schema with required vendor_id and item_id."""

    def test_valid_purchase_action_with_required_fields(self):
        """Purchase action requires vendor_id and item_id."""
        action = PurchaseAction(
            intent="Buy Incense from marketplace vendor",
            description="Approaching the vendor stall and negotiating for ritual incense supplies.",
            attribute="Charisma",
            skill="Negotiation",
            difficulty_estimate=12,
            difficulty_justification="Routine transaction at established market",
            action_type=ActionType.PURCHASE,
            vendor_id="vnd_marketplace_01",  # REQUIRED
            item_id="itm_incense"  # REQUIRED
        )

        assert action.vendor_id == "vnd_marketplace_01"
        assert action.item_id == "itm_incense"

    def test_purchase_action_missing_vendor_id_fails(self):
        """Purchase action without vendor_id should fail."""
        with pytest.raises(ValidationError):
            PurchaseAction(
                intent="Buy Incense",
                description="Purchasing incense from vendor.",
                attribute="Charisma",
                skill=None,
                difficulty_estimate=10,
                difficulty_justification="Simple purchase",
                action_type=ActionType.PURCHASE,
                # vendor_id missing
                item_id="itm_incense"
            )

    def test_purchase_action_missing_item_id_fails(self):
        """Purchase action without item_id should fail."""
        with pytest.raises(ValidationError):
            PurchaseAction(
                intent="Buy Incense",
                description="Purchasing incense from vendor.",
                attribute="Charisma",
                skill=None,
                difficulty_estimate=10,
                difficulty_justification="Simple purchase",
                action_type=ActionType.PURCHASE,
                vendor_id="vnd_marketplace_01"
                # item_id missing
            )


class TestAttuneAction:
    """Test ATTUNE action schema with required target_energy."""

    def test_valid_attune_action_with_required_target_energy(self):
        """Attune action requires target_energy field."""
        action = AttuneAction(
            intent="Attune Raw Seed to Drip at basic altar",
            description="Placing the Raw Seed on the altar's resonance plate, focusing willpower to channel drip energy through the crystalline matrix.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=19,
            difficulty_justification="DC 20 base reduced to 19 with altar bonus",
            action_type=ActionType.ATTUNE,
            target_energy="drip",  # REQUIRED
            altar_id="alt_marketplace_01",
            use_echo_calibrator=False
        )

        assert action.target_energy == "drip"
        assert action.altar_id == "alt_marketplace_01"
        assert action.use_echo_calibrator is False

    def test_attune_action_missing_target_energy_fails(self):
        """Attune action without target_energy should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            AttuneAction(
                intent="Attune Raw Seed at altar",
                description="Placing the Raw Seed on the altar.",
                attribute="Willpower",
                skill="Attunement",
                difficulty_estimate=20,
                difficulty_justification="Standard attunement",
                action_type=ActionType.ATTUNE,
                altar_id="alt_marketplace_01"
                # target_energy missing - should fail
            )

        assert "target_energy" in str(exc_info.value).lower()

    def test_attune_action_invalid_target_energy_fails(self):
        """target_energy must be one of: breath, grain, drip, spark."""
        with pytest.raises(ValidationError):
            AttuneAction(
                intent="Attune Raw Seed",
                description="Attuning seed to invalid energy type.",
                attribute="Willpower",
                skill="Attunement",
                difficulty_estimate=20,
                difficulty_justification="Standard attunement",
                action_type=ActionType.ATTUNE,
                target_energy="void"  # Invalid - not in Literal types
            )

    def test_attune_action_altar_id_optional(self):
        """altar_id is optional (for portable Echo-Calibrator use)."""
        action = AttuneAction(
            intent="Attune Raw Seed using Echo-Calibrator",
            description="Using the portable Echo-Calibrator to attune seed in field conditions.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=25,
            difficulty_justification="No altar bonus, higher difficulty",
            action_type=ActionType.ATTUNE,
            target_energy="spark",
            use_echo_calibrator=True
            # altar_id omitted - should be valid
        )

        assert action.altar_id is None
        assert action.use_echo_calibrator is True


class TestTransferAction:
    """Test TRANSFER action schema with required transfer_target and currency/items."""

    def test_valid_transfer_action_with_currency(self):
        """Transfer action requires transfer_target and at least currency or items."""
        action = TransferAction(
            intent="Transfer 5 drip to Thresh",
            description="Handing over 5 drip energy tokens to Thresh for their ritual preparations.",
            attribute="Charisma",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Simple friendly transfer",
            action_type=ActionType.TRANSFER,
            transfer_target="Thresh Ireveth",  # REQUIRED
            transfer_currency={"drip": 5}  # At least one of currency/items required
        )

        assert action.transfer_target == "Thresh Ireveth"
        assert action.transfer_currency == {"drip": 5}

    def test_valid_transfer_action_with_items(self):
        """Transfer action can transfer items instead of currency."""
        action = TransferAction(
            intent="Give Incense to ally",
            description="Handing ritual incense to ally for their ceremony.",
            attribute="Charisma",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Simple transfer",
            action_type=ActionType.TRANSFER,
            transfer_target="player_02",
            transfer_items={"Incense": 2}
        )

        assert action.transfer_items == {"Incense": 2}

    def test_transfer_action_missing_transfer_target_fails(self):
        """Transfer action without transfer_target should fail."""
        with pytest.raises(ValidationError):
            TransferAction(
                intent="Transfer drip",
                description="Transferring energy.",
                attribute="Charisma",
                skill=None,
                difficulty_estimate=10,
                difficulty_justification="Simple transfer",
                action_type=ActionType.TRANSFER,
                # transfer_target missing
                transfer_currency={"drip": 5}
            )


class TestRitualAction:
    """Test RITUAL action schema."""

    def test_valid_ritual_action(self):
        """Ritual action should have is_ritual=True."""
        action = RitualAction(
            intent="Perform void cleansing ritual",
            description="Drawing protective circle with incense, invoking cleansing mantras to push back corruption.",
            attribute="Willpower",
            skill="Astral Arts",
            difficulty_estimate=25,
            difficulty_justification="High-power ritual in corrupted zone",
            action_type=ActionType.RITUAL,
            is_ritual=True,  # REQUIRED for ritual actions
            has_primary_tool=True,
            has_offering=True,
            offering_type="incense",
            ritual_components="Incense, blessed salt, protective circle"
        )

        assert action.is_ritual is True
        assert action.has_offering is True
        assert action.offering_type == "incense"


class TestSocialAction:
    """Test SOCIAL action schema."""

    def test_valid_social_action(self):
        """Social action should parse successfully."""
        action = SocialAction(
            intent="Negotiate with gang leader",
            description="Using diplomatic skills to de-escalate confrontation and find common ground.",
            attribute="Charisma",
            skill="Diplomacy",
            difficulty_estimate=20,
            difficulty_justification="Hostile faction, tense situation",
            action_type=ActionType.SOCIAL,
            target="tgt_gang_leader"
        )

        assert action.action_type == ActionType.SOCIAL
        assert action.target == "tgt_gang_leader"


class TestTechnicalAction:
    """Test TECHNICAL action schema."""

    def test_valid_technical_action(self):
        """Technical action should parse successfully."""
        action = TechnicalAction(
            intent="Hack security terminal",
            description="Bypassing security protocols using neural interface and custom exploit code.",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=22,
            difficulty_justification="Advanced security, time pressure",
            action_type=ActionType.TECHNICAL
        )

        assert action.action_type == ActionType.TECHNICAL


class TestPerceptionAction:
    """Test PERCEPTION action schema."""

    def test_valid_perception_action(self):
        """Perception action should parse successfully."""
        action = PerceptionAction(
            intent="Scan area for hidden threats",
            description="Using enhanced senses to detect concealed enemies or void anomalies.",
            attribute="Perception",
            skill="Awareness",
            difficulty_estimate=18,
            difficulty_justification="Poor visibility, active concealment",
            action_type=ActionType.PERCEPTION
        )

        assert action.action_type == ActionType.PERCEPTION


class TestCustomAction:
    """Test CUSTOM action schema."""

    def test_valid_custom_action(self):
        """Custom action should parse successfully."""
        action = CustomAction(
            intent="Improvise unique solution",
            description="Using creative thinking to solve problem in unexpected way.",
            attribute="Intelligence",
            skill=None,
            difficulty_estimate=20,
            difficulty_justification="Novel approach, uncertain outcome",
            action_type=ActionType.CUSTOM
        )

        assert action.action_type == ActionType.CUSTOM


class TestPlayerActionDetails:
    """Test discriminated union that routes to correct schema based on action_type."""

    def test_discriminated_union_routes_to_attune_action(self):
        """Discriminated union should route to AttuneAction when action_type='attune'."""
        data = {
            "intent": "Attune Raw Seed to Drip",
            "description": "Using altar to channel drip energy into Raw Seed, focusing willpower through crystalline matrix.",
            "attribute": "Willpower",
            "skill": "Attunement",
            "difficulty_estimate": 19,
            "difficulty_justification": "Altar reduces DC from 20 to 19",
            "action_type": "attune",
            "target_energy": "drip",
            "altar_id": "alt_marketplace_01"
        }

        action = player_action_details_adapter.validate_python(data)

        assert isinstance(action, AttuneAction)
        assert action.target_energy == "drip"

    def test_discriminated_union_routes_to_combat_action(self):
        """Discriminated union should route to CombatAction when action_type='combat'."""
        data = {
            "intent": "Fire at enemy",
            "description": "Taking aimed shot at enemy combatant with plasma rifle.",
            "attribute": "Agility",
            "skill": "Firearms",
            "difficulty_estimate": 18,
            "difficulty_justification": "Moving target",
            "action_type": "combat",
            "target": "tgt_enemy_01"
        }

        action = player_action_details_adapter.validate_python(data)

        assert isinstance(action, CombatAction)
        assert action.target == "tgt_enemy_01"

    def test_discriminated_union_routes_to_purchase_action(self):
        """Discriminated union should route to PurchaseAction when action_type='purchase'."""
        data = {
            "intent": "Buy Incense",
            "description": "Purchasing ritual incense from marketplace vendor.",
            "attribute": "Charisma",
            "skill": None,
            "difficulty_estimate": 10,
            "difficulty_justification": "Standard transaction",
            "action_type": "purchase",
            "vendor_id": "vnd_marketplace_01",
            "item_id": "itm_incense"
        }

        action = player_action_details_adapter.validate_python(data)

        assert isinstance(action, PurchaseAction)
        assert action.vendor_id == "vnd_marketplace_01"

    def test_discriminated_union_enforces_required_fields(self):
        """Discriminated union should enforce action-specific required fields."""
        # AttuneAction missing required target_energy
        data = {
            "intent": "Attune Raw Seed",
            "description": "Attempting attunement without specifying energy type.",
            "attribute": "Willpower",
            "skill": "Attunement",
            "difficulty_estimate": 20,
            "difficulty_justification": "Standard attunement",
            "action_type": "attune"
            # target_energy missing - should fail
        }

        with pytest.raises(ValidationError) as exc_info:
            player_action_details_adapter.validate_python(data)

        assert "target_energy" in str(exc_info.value).lower()


class TestActionTypeSchemaMap:
    """Test ACTION_TYPE_SCHEMA_MAP routing dictionary."""

    def test_schema_map_has_all_action_types(self):
        """Schema map should have entries for all 13 action types."""
        assert len(ACTION_TYPE_SCHEMA_MAP) == 13

        expected_types = {
            ActionType.EXPLORE,
            ActionType.INVESTIGATE,
            ActionType.RITUAL,
            ActionType.SOCIAL,
            ActionType.COMBAT,
            ActionType.TECHNICAL,
            ActionType.PERCEPTION,
            ActionType.SUPPORT,
            ActionType.PURCHASE,
            ActionType.TRANSFER,
            ActionType.ATTUNE,
            ActionType.CONSUME,
            ActionType.CUSTOM,
        }

        assert set(ACTION_TYPE_SCHEMA_MAP.keys()) == expected_types

    def test_schema_map_routes_correctly(self):
        """Schema map should route action types to correct schemas."""
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.ATTUNE] == AttuneAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.COMBAT] == CombatAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.PURCHASE] == PurchaseAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.TRANSFER] == TransferAction
        assert ACTION_TYPE_SCHEMA_MAP[ActionType.RITUAL] == RitualAction


class TestSharedFieldValidation:
    """Test shared field validation across all action schemas."""

    def test_attribute_validation_enforced(self):
        """All action schemas should validate attribute is one of canonical 8."""
        with pytest.raises(ValidationError):
            CombatAction(
                intent="Attack enemy",
                description="Attacking with melee weapon in close quarters.",
                attribute="InvalidAttribute",  # Not in canonical set
                skill="Melee",
                difficulty_estimate=15,
                difficulty_justification="Close combat",
                action_type=ActionType.COMBAT,
                target="tgt_enemy_01"
            )

    def test_difficulty_estimate_range_validation(self):
        """difficulty_estimate must be between 5 and 50."""
        # Too low
        with pytest.raises(ValidationError):
            ExploreAction(
                intent="Simple exploration",
                description="Walking through safe, well-lit corridor.",
                attribute="Perception",
                skill=None,
                difficulty_estimate=2,  # Too low
                difficulty_justification="Very easy",
                action_type=ActionType.EXPLORE
            )

        # Too high
        with pytest.raises(ValidationError):
            ExploreAction(
                intent="Impossible task",
                description="Attempting something beyond mortal capability.",
                attribute="Perception",
                skill=None,
                difficulty_estimate=60,  # Too high
                difficulty_justification="Impossibly hard",
                action_type=ActionType.EXPLORE
            )

    def test_description_min_length_validation(self):
        """description must be at least 50 characters."""
        with pytest.raises(ValidationError):
            InvestigateAction(
                intent="Examine terminal",
                description="Short description.",  # Only 18 chars, need 50+
                attribute="Intelligence",
                skill="Systems",
                difficulty_estimate=15,
                difficulty_justification="Standard investigation",
                action_type=ActionType.INVESTIGATE
            )


class TestSystemPopulatedFields:
    """Test that character_name and agent_id can be populated by system."""

    def test_character_name_and_agent_id_optional(self):
        """character_name and agent_id should be optional (system-populated)."""
        action = ExploreAction(
            intent="Search northwest corridor",
            description="Moving carefully through the darkened hallway, checking for structural damage.",
            attribute="Perception",
            skill="Investigation",
            difficulty_estimate=15,
            difficulty_justification="Moderate difficulty due to poor lighting",
            action_type=ActionType.EXPLORE
            # character_name and agent_id omitted - should be valid
        )

        assert action.character_name is None
        assert action.agent_id is None

    def test_character_name_and_agent_id_can_be_set(self):
        """System should be able to populate character_name and agent_id."""
        action = ExploreAction(
            intent="Search corridor",
            description="Carefully exploring the darkened hallway for exits or threats.",
            attribute="Perception",
            skill="Investigation",
            difficulty_estimate=15,
            difficulty_justification="Poor lighting",
            action_type=ActionType.EXPLORE,
            character_name="Echo Resonance",
            agent_id="player_01"
        )

        assert action.character_name == "Echo Resonance"
        assert action.agent_id == "player_01"


class TestReasoningField:
    """Test optional reasoning field for ML training."""

    def test_reasoning_optional_across_all_schemas(self):
        """reasoning field should be optional in all action schemas."""
        # Test a few representative schemas
        attune = AttuneAction(
            intent="Attune seed",
            description="Using altar resonance to channel drip energy into Raw Seed structure.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=19,
            difficulty_justification="Altar bonus",
            action_type=ActionType.ATTUNE,
            target_energy="drip"
            # reasoning omitted
        )

        assert attune.reasoning is None

    def test_reasoning_can_be_populated(self):
        """reasoning can be populated for ML training purposes."""
        action = CombatAction(
            intent="Fire at enemy leader",
            description="Targeting the enemy commander to disrupt their tactical coordination.",
            attribute="Agility",
            skill="Firearms",
            difficulty_estimate=20,
            difficulty_justification="Moving target with cover",
            action_type=ActionType.COMBAT,
            target="tgt_enemy_leader",
            reasoning="Eliminating the leader will cause confusion in enemy ranks, making it easier to escape or negotiate"
        )

        assert "eliminat" in action.reasoning.lower()
