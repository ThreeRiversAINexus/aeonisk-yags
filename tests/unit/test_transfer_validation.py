"""
Unit tests for Soulcredit transfer validation.

Tests the validate_transfer() function in MechanicsEngine,
particularly multi-target rejection.
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse


class MockAgent:
    """Mock agent for testing."""
    def __init__(self, agent_id: str, name: str, energy_purse: EnergyPurse):
        self.agent_id = agent_id
        self.character_state = CharacterState(
            name=name,
            faction="Test",
            attributes={"strength": 3, "agility": 3, "intelligence": 3},
            skills={"combat": 2},
            void_score=0,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        self.character_state.energy_purse = energy_purse
        self.position = None  # No combat position for non-combat scenarios


@pytest.fixture
def mechanics_with_npcs():
    """Create a MechanicsEngine with SharedState containing NPCs."""
    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)

    # Create sender (player) with currency
    sender = MockAgent(
        agent_id="player_01",
        name="Ryn Thrace",
        energy_purse=EnergyPurse(grain=10, drip=50, spark=5, breath=20)
    )
    shared_state.player_agents.append(sender)

    # Create NPC recipients
    npc1 = MockAgent(
        agent_id="npc_001",
        name="Mira Solis",
        energy_purse=EnergyPurse(grain=0, drip=0, spark=0, breath=0)
    )
    npc2 = MockAgent(
        agent_id="npc_002",
        name="Sera Vex",
        energy_purse=EnergyPurse(grain=0, drip=0, spark=0, breath=0)
    )
    npc3 = MockAgent(
        agent_id="npc_003",
        name="Jace Kordell",
        energy_purse=EnergyPurse(grain=0, drip=0, spark=0, breath=0)
    )

    shared_state.npc_agents = [npc1, npc2, npc3]

    return mechanics, sender.character_state


class TestTransferValidationMultiTarget:
    """Test transfer validation rejects multi-target syntax."""

    def test_comma_separated_targets_rejected(self, mechanics_with_npcs):
        """Test that comma-separated targets are rejected."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Mira Solis, Sera Vex",
            transfer_currency={"grain": 1}
        )

        assert validation.is_valid is False
        assert "Multi-target transfers not supported" in validation.failure_reason
        assert "Mira Solis, Sera Vex" in validation.failure_reason

    def test_semicolon_separated_targets_rejected(self, mechanics_with_npcs):
        """Test that semicolon-separated targets are rejected."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Mira Solis; Sera Vex; Jace Kordell",
            transfer_currency={"drip": 10}
        )

        assert validation.is_valid is False
        assert "Multi-target transfers not supported" in validation.failure_reason
        assert "Mira Solis; Sera Vex; Jace Kordell" in validation.failure_reason

    def test_semicolon_with_target_ids_rejected(self, mechanics_with_npcs):
        """Test that semicolon-separated target IDs are rejected."""
        mechanics, sender_state = mechanics_with_npcs

        # This mimics the error from the session log:
        # "Mira Solis (tgt_9qov); Sera Vex (tgt_1i5j); Jace Kordell (tgt_dbkt)"
        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Mira Solis (tgt_9qov); Sera Vex (tgt_1i5j); Jace Kordell (tgt_dbkt)",
            transfer_currency={"grain": 1, "drip": 10}
        )

        assert validation.is_valid is False
        assert "Multi-target transfers not supported" in validation.failure_reason

    def test_single_target_accepted(self, mechanics_with_npcs):
        """Test that single target transfers are accepted."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Mira Solis",
            transfer_currency={"grain": 1}
        )

        assert validation.is_valid is True
        assert validation.receiver_name == "Mira Solis"
        assert validation.receiver_agent_id == "npc_001"

    def test_single_target_with_agent_id_accepted(self, mechanics_with_npcs):
        """Test that single target with agent_id is accepted."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="npc_002",
            transfer_currency={"drip": 10}
        )

        assert validation.is_valid is True
        assert validation.receiver_name == "Sera Vex"
        assert validation.receiver_agent_id == "npc_002"


class TestTransferValidationEdgeCases:
    """Test edge cases in transfer validation."""

    def test_empty_target_rejected(self, mechanics_with_npcs):
        """Test that empty target string is rejected."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="",
            transfer_currency={"grain": 1}
        )

        assert validation.is_valid is False
        assert "not found" in validation.failure_reason.lower()

    def test_nonexistent_target_rejected(self, mechanics_with_npcs):
        """Test that nonexistent target is rejected."""
        mechanics, sender_state = mechanics_with_npcs

        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Nonexistent NPC",
            transfer_currency={"grain": 1}
        )

        assert validation.is_valid is False
        assert "not found" in validation.failure_reason.lower()
        assert "Nonexistent NPC" in validation.failure_reason

    def test_insufficient_currency_rejected(self, mechanics_with_npcs):
        """Test that insufficient currency is rejected."""
        mechanics, sender_state = mechanics_with_npcs

        # Sender has only 10 grain, try to transfer 20
        validation = mechanics.validate_transfer(
            sender_state=sender_state,
            transfer_target="Mira Solis",
            transfer_currency={"grain": 20}
        )

        assert validation.is_valid is False
        assert "Insufficient currency" in validation.failure_reason
        assert validation.shortage == {"grain": 10}  # Short by 10
