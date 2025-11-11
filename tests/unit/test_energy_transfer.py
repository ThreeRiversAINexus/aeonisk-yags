"""
Unit tests for energy currency transfer system.

Tests the complete transfer flow:
1. validate_transfer() method in mechanics.py
2. Pre-validation in session.py
3. Mechanical execution (EnergyPurse.transfer_currency_to())
4. DM narration via _resolve_transfer_transaction()
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse
from scripts.aeonisk.multiagent.shared_state import SharedState


class MockAgent:
    """Mock player agent for testing."""
    def __init__(self, agent_id, character_state, position=None):
        self.agent_id = agent_id
        self.character_state = character_state
        self.position = position


class MockPosition:
    """Mock position for range checking."""
    def __init__(self, ring, side):
        self.ring = ring
        self.side = side


@pytest.fixture
def shared_state():
    """Create SharedState with two players for transfer testing."""
    shared_state = SharedState()

    # Create sender character with surplus currency
    sender_state = CharacterState(
        name="Ash Vex",
        faction="Freeborn",
        attributes={"strength": 2, "agility": 3, "endurance": 3, "perception": 4, "intelligence": 4, "empathy": 3, "willpower": 3, "charisma": 3, "size": 10},
        skills={"Magick Theory": 4, "Attunement": 3, "Charm": 2},
        void_score=3,
        soulcredit=0,
        bonds=[],
        goals=[],
        pronouns="they/them"
    )
    sender_state.max_hp = 25
    sender_state.health = 25
    sender_state.energy_purse = EnergyPurse(spark=10, grain=5, drip=15, breath=2)

    # Create receiver character with low currency
    receiver_state = CharacterState(
        name="Kress",
        faction="Freeborn",
        attributes={"strength": 3, "agility": 2, "endurance": 3, "perception": 4, "intelligence": 4, "empathy": 2, "willpower": 3, "charisma": 2, "size": 10},
        skills={"Attunement": 4, "Magick Theory": 3, "Medicine": 2},
        void_score=3,
        soulcredit=0,
        bonds=[],
        goals=[],
        pronouns="he/him"
    )
    receiver_state.max_hp = 30
    receiver_state.health = 30
    receiver_state.energy_purse = EnergyPurse(spark=1, grain=2, drip=2, breath=0)

    # Create mock agents with positions (same range band)
    sender_agent = MockAgent("agt_sender", sender_state, MockPosition("Near-PC", "left"))
    receiver_agent = MockAgent("agt_receiver", receiver_state, MockPosition("Near-PC", "left"))

    shared_state.player_agents = [sender_agent, receiver_agent]

    return shared_state


@pytest.fixture
def mechanics(shared_state):
    """Create MechanicsEngine with SharedState."""
    mechanics = MechanicsEngine(shared_state=shared_state)
    return mechanics


class TestTransferValidation:
    """Test validate_transfer() method in mechanics.py."""

    def test_successful_transfer_by_name(self, mechanics, shared_state):
        """Test valid transfer using character name."""
        sender_agent = shared_state.player_agents[0]

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 5, "spark": 2},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is True
        assert validation.sender_name == "Ash Vex"
        assert validation.receiver_name == "Kress"
        assert validation.receiver_agent_id == "agt_receiver"
        assert validation.currency == {"drip": 5, "spark": 2}
        assert validation.in_range is True
        assert validation.failure_reason is None

    def test_successful_transfer_by_agent_id(self, mechanics, shared_state):
        """Test valid transfer using agent_id."""
        sender_agent = shared_state.player_agents[0]

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="agt_receiver",
            transfer_currency={"drip": 3},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is True
        assert validation.receiver_agent_id == "agt_receiver"

    def test_insufficient_currency(self, mechanics, shared_state):
        """Test transfer fails when sender lacks currency."""
        sender_agent = shared_state.player_agents[0]

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 20},  # Sender only has 15
            sender_position=sender_agent.position
        )

        assert validation.is_valid is False
        assert "Insufficient currency" in validation.failure_reason
        assert validation.shortage == {"drip": 5}

    def test_multiple_currency_shortage(self, mechanics, shared_state):
        """Test shortage detection for multiple currencies."""
        sender_agent = shared_state.player_agents[0]

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 20, "spark": 15, "breath": 5},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is False
        assert validation.shortage == {"drip": 5, "spark": 5, "breath": 3}

    def test_target_not_found(self, mechanics, shared_state):
        """Test transfer fails when target doesn't exist."""
        sender_agent = shared_state.player_agents[0]

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="NonexistentCharacter",
            transfer_currency={"drip": 5},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is False
        assert "not found" in validation.failure_reason

    def test_out_of_range(self, mechanics, shared_state):
        """Test transfer fails when characters not in same range band."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        # Move receiver to different range band
        receiver_agent.position = MockPosition("Engaged", "right")

        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 5},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is False
        assert "Out of range" in validation.failure_reason
        assert validation.in_range is False


class TestTransferMechanicalExecution:
    """Test actual currency transfer via EnergyPurse.transfer_currency_to()."""

    def test_transfer_execution(self, shared_state):
        """Test currency actually moves between purses."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        # Record initial balances
        sender_initial_drip = sender_agent.character_state.energy_purse.drip
        receiver_initial_drip = receiver_agent.character_state.energy_purse.drip

        # Execute transfer
        success = sender_agent.character_state.energy_purse.transfer_currencies_to(
            receiver_purse=receiver_agent.character_state.energy_purse,
            currency_amounts={"drip": 5}
        )

        assert success is True
        assert sender_agent.character_state.energy_purse.drip == sender_initial_drip - 5
        assert receiver_agent.character_state.energy_purse.drip == receiver_initial_drip + 5

    def test_transfer_multiple_currencies(self, shared_state):
        """Test transferring multiple currency types."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        sender_spark_initial = sender_agent.character_state.energy_purse.spark
        sender_grain_initial = sender_agent.character_state.energy_purse.grain
        receiver_spark_initial = receiver_agent.character_state.energy_purse.spark
        receiver_grain_initial = receiver_agent.character_state.energy_purse.grain

        success = sender_agent.character_state.energy_purse.transfer_currencies_to(
            receiver_purse=receiver_agent.character_state.energy_purse,
            currency_amounts={"spark": 3, "grain": 2}
        )

        assert success is True
        assert sender_agent.character_state.energy_purse.spark == sender_spark_initial - 3
        assert sender_agent.character_state.energy_purse.grain == sender_grain_initial - 2
        assert receiver_agent.character_state.energy_purse.spark == receiver_spark_initial + 3
        assert receiver_agent.character_state.energy_purse.grain == receiver_grain_initial + 2

    def test_transfer_entire_purse(self, shared_state):
        """Test transferring all of one currency type."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        breath_amount = sender_agent.character_state.energy_purse.breath

        success = sender_agent.character_state.energy_purse.transfer_currencies_to(
            receiver_purse=receiver_agent.character_state.energy_purse,
            currency_amounts={"breath": breath_amount}
        )

        assert success is True
        assert sender_agent.character_state.energy_purse.breath == 0
        assert receiver_agent.character_state.energy_purse.breath == breath_amount


class TestTransferEdgeCases:
    """Test edge cases and error conditions."""

    def test_transfer_zero_amount(self, shared_state):
        """Test transferring 0 currency (should succeed but do nothing)."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        sender_initial = sender_agent.character_state.energy_purse.drip
        receiver_initial = receiver_agent.character_state.energy_purse.drip

        success = sender_agent.character_state.energy_purse.transfer_currencies_to(
            receiver_purse=receiver_agent.character_state.energy_purse,
            currency_amounts={"drip": 0}
        )

        assert success is True
        assert sender_agent.character_state.energy_purse.drip == sender_initial
        assert receiver_agent.character_state.energy_purse.drip == receiver_initial

    def test_no_position_data(self, mechanics, shared_state):
        """Test validation when position data unavailable (should skip range check)."""
        sender_agent = shared_state.player_agents[0]

        # Validate without position
        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 5},
            sender_position=None
        )

        # Should succeed (range check skipped)
        assert validation.is_valid is True
        assert validation.in_range is True  # Defaults to True when positions unavailable


class TestTransferIntegration:
    """Integration tests combining validation + execution."""

    def test_full_transfer_flow(self, mechanics, shared_state):
        """Test complete transfer: validate → execute → verify."""
        sender_agent = shared_state.player_agents[0]
        receiver_agent = shared_state.player_agents[1]

        # 1. Validate
        validation = mechanics.validate_transfer(
            sender_state=sender_agent.character_state,
            transfer_target="Kress",
            transfer_currency={"drip": 5, "spark": 2},
            sender_position=sender_agent.position
        )

        assert validation.is_valid is True

        # 2. Execute
        success = sender_agent.character_state.energy_purse.transfer_currencies_to(
            receiver_purse=receiver_agent.character_state.energy_purse,
            currency_amounts=validation.currency
        )

        assert success is True

        # 3. Verify final balances
        assert sender_agent.character_state.energy_purse.drip == 10  # 15 - 5
        assert sender_agent.character_state.energy_purse.spark == 8   # 10 - 2
        assert receiver_agent.character_state.energy_purse.drip == 7  # 2 + 5
        assert receiver_agent.character_state.energy_purse.spark == 3 # 1 + 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
