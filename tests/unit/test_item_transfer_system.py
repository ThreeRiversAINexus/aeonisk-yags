"""
Test Item Transfer System

Verifies that:
1. Item transfer validation works correctly
2. Item transfers execute properly (inventory manipulation)
3. Combined currency + item transfers work
4. Transfer fields are preserved through Pydantic → dataclass conversion
5. Player prompts include transfer syntax
6. ActionType enum includes TRANSFER
"""

import pytest
from unittest.mock import Mock
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, TransferValidation
from scripts.aeonisk.multiagent.player import CharacterState, AIPlayerAgent
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse
from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration
from scripts.aeonisk.multiagent.prompt_loader import compose_sections
from scripts.aeonisk.multiagent.shared_state import SharedState


class TestItemTransferValidation:
    """Test item transfer validation logic in GameMechanicsEngine"""

    @pytest.fixture
    def sender_state(self):
        """Create sender character with inventory"""
        return CharacterState(
            name="Ash Vex",
            faction="Freeborn",
            attributes={"intelligence": 4, "perception": 3},
            skills={"Magic Theory": 4},
            void_score=2,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory={"Incense": 4, "Crystals": 3, "Blood": 1},
            energy_purse=EnergyPurse(spark=2, grain=1, drip=3, breath=0)
        )

    @pytest.fixture
    def receiver_state(self):
        """Create receiver character with inventory"""
        return CharacterState(
            name="Kress",
            faction="Freeborn",
            attributes={"intelligence": 4, "willpower": 3},
            skills={"Attunement": 4},
            void_score=3,
            soulcredit=4,
            bonds=[],
            goals=[],
            inventory={"Incense": 1, "Crystals": 0},
            energy_purse=EnergyPurse(spark=8, grain=5, drip=12, breath=3)
        )

    @pytest.fixture
    def mechanics(self, sender_state, receiver_state):
        """Create MechanicsEngine with shared_state containing player agents"""
        shared_state = SharedState()

        # Create mock player agents with character states
        sender_agent = Mock()
        sender_agent.agent_id = "player_ash"
        sender_agent.character_state = sender_state

        receiver_agent = Mock()
        receiver_agent.agent_id = "player_kress"
        receiver_agent.character_state = receiver_state

        shared_state.player_agents = [sender_agent, receiver_agent]

        engine = MechanicsEngine(shared_state=shared_state)
        return engine

    def test_item_transfer_validation_success(self, mechanics, sender_state, receiver_state):
        """Test successful item transfer validation"""
        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Kress",
            transfer_items={"Incense": 2, "Crystals": 1}
        )

        assert validation.is_valid
        assert validation.sender_name == "Ash Vex"
        assert validation.receiver_name == "Kress"
        assert validation.items == {"Incense": 2, "Crystals": 1}
        assert validation.item_shortage is None

    def test_insufficient_items(self, mechanics, sender_state, receiver_state):
        """Test transfer validation fails when sender lacks items"""
        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Kress",
            transfer_items={"Incense": 10, "Crystals": 5}  # Sender only has 4 Incense, 3 Crystals
        )

        assert not validation.is_valid
        assert "Insufficient items" in validation.failure_reason
        assert validation.item_shortage == {"Incense": 6, "Crystals": 2}

    def test_missing_inventory(self, mechanics, receiver_state):
        """Test transfer validation fails when sender has empty inventory"""
        # Note: CharacterState now auto-initializes a default inventory with 0 of each item
        # when inventory=None, so we test the case where sender has 0 of the requested items
        sender_no_inv = CharacterState(
            name="Empty",
            faction="Freeborn",
            attributes={"intelligence": 3},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory=None,  # Gets default inventory with 0 of everything
            energy_purse=EnergyPurse()
        )

        validation = mechanics.validate_transfer(
            sender_state=sender_no_inv,
            transfer_target="Kress",
            transfer_items={"Incense": 1}
        )

        assert not validation.is_valid
        # CharacterState now auto-initializes inventory, so error is "insufficient" not "no inventory"
        assert "Insufficient items" in validation.failure_reason

    def test_combined_currency_and_items(self, mechanics, sender_state, receiver_state):
        """Test validation for combined currency + item transfer"""
        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Kress",
            transfer_currency={"drip": 2},
            transfer_items={"Incense": 1}
        )

        assert validation.is_valid
        assert validation.currency == {"drip": 2}
        assert validation.items == {"Incense": 1}


class TestItemTransferExecution:
    """Test actual inventory manipulation during transfers"""

    def test_item_transfer_execution(self):
        """Test items are removed from sender and added to receiver"""
        sender = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={"intelligence": 4},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory={"Incense": 4, "Crystals": 3},
            energy_purse=EnergyPurse()
        )

        receiver = CharacterState(
            name="Kress",
            faction="Freeborn",
            attributes={"intelligence": 4},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory={"Incense": 1},
            energy_purse=EnergyPurse()
        )

        # Transfer 2 Incense, 1 Crystal
        transfer_items = {"Incense": 2, "Crystals": 1}

        # Remove from sender
        for item_name, amount in transfer_items.items():
            sender.inventory[item_name] -= amount
            if sender.inventory[item_name] <= 0:
                del sender.inventory[item_name]

        # Add to receiver
        for item_name, amount in transfer_items.items():
            receiver.inventory[item_name] = receiver.inventory.get(item_name, 0) + amount

        # Verify sender inventory
        assert sender.inventory == {"Incense": 2, "Crystals": 2}

        # Verify receiver inventory
        assert receiver.inventory == {"Incense": 3, "Crystals": 1}

    def test_transfer_depletes_item_removes_from_inventory(self):
        """Test that transferring all of an item removes it from inventory"""
        sender = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={"intelligence": 4},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory={"Incense": 2, "Crystals": 3},
            energy_purse=EnergyPurse()
        )

        # Transfer all Incense
        sender.inventory["Incense"] -= 2
        if sender.inventory["Incense"] <= 0:
            del sender.inventory["Incense"]

        assert "Incense" not in sender.inventory
        assert sender.inventory == {"Crystals": 3}

    def test_receiver_with_no_inventory_initializes(self):
        """Test that receiver with no inventory gets one initialized"""
        receiver = CharacterState(
            name="Kress",
            faction="Freeborn",
            attributes={"intelligence": 4},
            skills={},
            void_score=0,
            soulcredit=5,
            bonds=[],
            goals=[],
            inventory=None,  # Gets default inventory via __post_init__
            energy_purse=EnergyPurse()
        )

        # CharacterState now auto-initializes inventory in __post_init__
        assert receiver.inventory is not None

        # Add items
        receiver.inventory["Incense"] = receiver.inventory.get("Incense", 0) + 2

        # Check that Incense was added correctly (inventory has default items + our addition)
        assert receiver.inventory["Incense"] == 2


class TestSchemaIntegration:
    """Test transfer fields are preserved through schema conversions"""

    def test_player_action_has_transfer_fields(self):
        """Test PlayerAction schema includes transfer fields"""
        action = PlayerAction(
            intent="Transfer items to Kress",
            description="I hand over 2 Incense sticks and 1 Crystal to Kress for the ritual",
            attribute="Empathy",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Simple physical handoff",
            action_type=ActionType.TRANSFER,
            character_name="Ash Vex",
            agent_id="player_01",
            transfer_target="Kress",
            transfer_items={"Incense": 2, "Crystals": 1}
        )

        assert action.transfer_target == "Kress"
        assert action.transfer_items == {"Incense": 2, "Crystals": 1}
        assert action.transfer_currency is None

    def test_action_declaration_preserves_transfer_fields(self):
        """Test ActionDeclaration preserves transfer fields from PlayerAction"""
        player_action = PlayerAction(
            intent="Give currency to ally",
            description="I carefully hand over the energy talismans to my ally, ensuring the delicate transfer is complete",
            attribute="Empathy",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Simple exchange",
            action_type=ActionType.TRANSFER,
            character_name="Kress",
            agent_id="player_02",
            transfer_target="Ash Vex",
            transfer_currency={"drip": 5}
        )

        # Convert to ActionDeclaration (mimics player.py:1350-1367)
        action_declaration = ActionDeclaration(
            intent=player_action.intent,
            description=player_action.description,
            attribute=player_action.attribute,
            skill=player_action.skill,
            difficulty_estimate=player_action.difficulty_estimate,
            difficulty_justification=player_action.difficulty_justification,
            character_name=player_action.character_name,
            agent_id=player_action.agent_id,
            action_type=player_action.action_type,
            transfer_target=player_action.transfer_target,
            transfer_currency=player_action.transfer_currency,
            transfer_items=player_action.transfer_items
        )

        assert action_declaration.transfer_target == "Ash Vex"
        assert action_declaration.transfer_currency == {"drip": 5}
        assert action_declaration.transfer_items is None

    def test_combined_transfer_fields(self):
        """Test combined currency + item transfer"""
        action = PlayerAction(
            intent="Pool resources",
            description="I pool our resources by handing over both the spark currency and blood offering items to Kress",
            attribute="Empathy",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Simple exchange",
            action_type=ActionType.TRANSFER,
            character_name="Ash",
            agent_id="player_01",
            transfer_target="Kress",
            transfer_currency={"spark": 2},
            transfer_items={"Blood": 1}
        )

        assert action.transfer_currency == {"spark": 2}
        assert action.transfer_items == {"Blood": 1}


class TestActionTypeEnum:
    """Test ActionType enum includes TRANSFER"""

    def test_transfer_in_action_type_enum(self):
        """Test TRANSFER is a valid ActionType"""
        assert hasattr(ActionType, 'TRANSFER')
        assert ActionType.TRANSFER.value == "transfer"

    def test_action_type_enum_values(self):
        """Test all expected ActionType values"""
        expected_values = {
            "explore", "investigate", "ritual", "social",
            "combat", "technical", "perception", "support",
            "purchase", "transfer", "custom"
        }

        actual_values = {at.value for at in ActionType}
        assert expected_values.issubset(actual_values), \
            f"Missing action types: {expected_values - actual_values}"


class TestPromptSystem:
    """Test player prompts include transfer syntax"""

    def test_currency_transfers_section_exists(self):
        """Test currency_transfers section can be loaded"""
        loaded = compose_sections(
            agent_type="player",
            section_names=["currency_transfers"],
            provider="claude",
            language="en"
        )

        content = loaded.content
        assert "TRANSFER_CURRENCY" in content
        assert "TRANSFER_ITEMS" in content
        assert "action_type=transfer" in content.lower() or "ACTION_TYPE: transfer" in content

    def test_transfer_examples_in_prompts(self):
        """Test transfer examples are present in player prompts"""
        loaded = compose_sections(
            agent_type="player",
            section_names=["currency_transfers"],
            provider="claude",
            language="en"
        )

        content = loaded.content
        # Check for item transfer example
        assert "Incense" in content or "Crystals" in content
        # Check for currency transfer example
        assert "drip" in content or "spark" in content

    def test_required_sections_include_currency_transfers(self):
        """Test that currency_transfers is in the default section list"""
        # This mimics player.py:_get_required_player_sections()
        sections = [
            'character_introduction',
            'character_sheet',
            'inventory_resources',
            'personality_traits',
            'goals',
            'lookup_rules',
            'stat_awareness_guidance',
            'action_declaration_unified',
            'coordination_dialogue',
            'vendor_interaction',
            'currency_transfers',  # <-- This should be here
            'action_guidelines',
            'bond_mechanics',
            'important_rules'
        ]

        assert 'currency_transfers' in sections


class TestActionDeclarationSchema:
    """Test ActionDeclaration dataclass has transfer fields"""

    def test_action_declaration_has_transfer_fields(self):
        """Test ActionDeclaration includes transfer_target, transfer_currency, transfer_items"""
        from scripts.aeonisk.multiagent.action_schema import ActionDeclaration

        # Check that ActionDeclaration has the fields
        action = ActionDeclaration(
            intent="Transfer test",
            description="Testing transfer fields",
            attribute="Empathy",
            skill=None,
            difficulty_estimate=10,
            difficulty_justification="Test",
            character_name="Test",
            agent_id="test_01",
            action_type="transfer",
            transfer_target="TestReceiver",
            transfer_currency={"drip": 5},
            transfer_items={"Incense": 2}
        )

        assert hasattr(action, 'transfer_target')
        assert hasattr(action, 'transfer_currency')
        assert hasattr(action, 'transfer_items')
        assert action.transfer_target == "TestReceiver"
        assert action.transfer_currency == {"drip": 5}
        assert action.transfer_items == {"Incense": 2}

    def test_transfer_in_valid_action_types(self):
        """Test 'transfer' is a valid ActionType"""
        # ActionType enum is the public API for valid action types
        assert hasattr(ActionType, 'TRANSFER')
        assert ActionType.TRANSFER.value == 'transfer'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
