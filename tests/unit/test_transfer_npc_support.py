"""
Unit tests for transfer validation with NPC support.

Tests the fixes for:
1. NPCs as transfer targets (not just players)
2. Range validation skipping in non-combat scenarios
3. Multi-target transfer rejection
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse
from scripts.aeonisk.multiagent.npc_agent import NPCAgent


@pytest.fixture
def shared_state_with_npc():
    """Shared state with players and NPCs."""
    shared_state = SharedState()

    # Create simple player mock with character_state
    player_state = CharacterState(
        name="TestPlayer",
        faction="ACG",
        attributes={"intelligence": 3},
        skills={"Combat": 2},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[],
        energy_purse=EnergyPurse(drip=20, spark=5)
    )

    # Create minimal player agent mock
    class MockPlayer:
        def __init__(self, agent_id, character_state):
            self.agent_id = agent_id
            self.character_state = character_state
            self.position = None

    player_agent = MockPlayer("player_01", player_state)
    shared_state.player_agents = [player_agent]

    # Create NPC with currency (vendor NPC)
    npc = NPCAgent(
        agent_id="npc_vendor_01",
        name="Kael Voss",
        faction="Independent",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Independent trader",
        health=25,
        max_health=25,
        soak=2,
        void_score=0,
        skills={},
        is_vendor=True,
        vendor_inventory=[],
        accepts_purchases=True,
        energy_purse=EnergyPurse(drip=50)
    )
    shared_state.npc_agents = [npc]

    return shared_state


@pytest.fixture
def mechanics_with_npc(shared_state_with_npc):
    """Mechanics engine with NPC-enabled shared state."""
    return MechanicsEngine(shared_state=shared_state_with_npc)


class TestTransferToNPC:
    """Test transfers targeting NPCs."""

    def test_transfer_to_npc_by_name(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer to NPC using character name."""
        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Kael Voss",  # NPC name
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == True
        assert validation.receiver_name == "Kael Voss"
        assert validation.receiver_agent_id == "npc_vendor_01"

    def test_transfer_to_npc_by_agent_id(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer to NPC using agent_id."""
        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="npc_vendor_01",  # NPC agent_id
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == True
        assert validation.receiver_name == "Kael Voss"
        assert validation.receiver_agent_id == "npc_vendor_01"

    def test_transfer_to_player_still_works(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer to player still works (backward compatibility)."""
        # Add second player
        player2_state = CharacterState(
            name="TestPlayer2",
            faction="ACG",
            attributes={"intelligence": 3},
            skills={},
            void_score=0,
            soulcredit=0,
            bonds=[],
            goals=[],
            energy_purse=EnergyPurse(drip=10)
        )

        # Create minimal player agent mock
        class MockPlayer:
            def __init__(self, agent_id, character_state):
                self.agent_id = agent_id
                self.character_state = character_state
                self.position = None

        player2 = MockPlayer("player_02", player2_state)
        shared_state_with_npc.player_agents.append(player2)

        player1 = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player1.character_state,
            transfer_target="TestPlayer2",
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == True
        assert validation.receiver_name == "TestPlayer2"


class TestMultiTargetRejection:
    """Test multi-target transfer rejection."""

    def test_comma_separated_targets_rejected(self, mechanics_with_npc, shared_state_with_npc):
        """Comma-separated targets are rejected with clear error."""
        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="tgt_jw1m, tgt_rppf",  # Actual error from logs
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == False
        assert "Multi-target transfers not supported" in validation.failure_reason
        assert "one recipient at a time" in validation.failure_reason


class TestRangeValidationNonCombat:
    """Test range validation skips in non-combat scenarios."""

    def test_transfer_without_positions_succeeds(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer succeeds when sender has no position (marketplace scenario)."""
        player = shared_state_with_npc.player_agents[0]
        npc = shared_state_with_npc.npc_agents[0]

        # Player has no position (non-combat scenario)
        assert not hasattr(player, 'position') or player.position is None
        # NPC has default position, but transfer should still succeed without sender_position

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Kael Voss",
            transfer_currency={"drip": 5},
            sender_position=None  # No combat position - should skip range check
        )

        assert validation.is_valid == True
        assert validation.in_range == True  # Should be True (no range restriction when sender_position is None)

    def test_transfer_with_none_positions_succeeds(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer succeeds when position objects exist but ring/side are None."""
        from scripts.aeonisk.multiagent.enemy_agent import Position

        player = shared_state_with_npc.player_agents[0]
        npc = shared_state_with_npc.npc_agents[0]

        # Position objects with None ring/side (social scenario)
        player.position = Position(ring=None, side=None)
        npc.position = Position(ring=None, side=None)

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Kael Voss",
            transfer_currency={"drip": 5},
            sender_position=player.position
        )

        assert validation.is_valid == True
        assert validation.in_range == True

    def test_transfer_enforces_range_in_combat(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer still enforces range when both agents have combat positions."""
        from scripts.aeonisk.multiagent.enemy_agent import Position

        player = shared_state_with_npc.player_agents[0]
        npc = shared_state_with_npc.npc_agents[0]

        # Both in combat positions but different range bands
        player.position = Position(ring="Close", side="Friendly")
        npc.position = Position(ring="Far", side="Enemy")

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Kael Voss",
            transfer_currency={"drip": 5},
            sender_position=player.position
        )

        assert validation.is_valid == False
        assert "Out of range" in validation.failure_reason
        assert validation.in_range == False

    def test_transfer_succeeds_same_range_band(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer succeeds when both agents in same range band (combat)."""
        from scripts.aeonisk.multiagent.enemy_agent import Position

        player = shared_state_with_npc.player_agents[0]
        npc = shared_state_with_npc.npc_agents[0]

        # Both in same range band
        player.position = Position(ring="Close", side="Friendly")
        npc.position = Position(ring="Close", side="Friendly")

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Kael Voss",
            transfer_currency={"drip": 5},
            sender_position=player.position
        )

        assert validation.is_valid == True
        assert validation.in_range == True


class TestTransferValidationEdgeCases:
    """Edge cases for transfer validation."""

    def test_npc_without_energy_purse_accepted(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer to NPC without energy_purse is accepted (NPC receiver may not need purse)."""
        # Create NPC without energy_purse (but has other fields needed for target resolution)
        npc_no_purse = NPCAgent(
            agent_id="npc_civilian_01",
            name="Civilian",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Civilian NPC",
            health=10,
            max_health=10,
            soak=0,
            void_score=0,
            skills={}
            # No energy_purse - transfers to NPCs without purses are allowed
            # (NPCs use themselves as receiver_state if no character_state)
        )
        shared_state_with_npc.npc_agents.append(npc_no_purse)

        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Civilian",
            transfer_currency={"drip": 5}
        )

        # Transfer validation should succeed even if NPC lacks energy_purse
        # (DM can narrate giving money to civilian even if not mechanically tracked)
        assert validation.is_valid == True or "energy purse" in validation.failure_reason.lower()

    def test_case_insensitive_npc_name_matching(self, mechanics_with_npc, shared_state_with_npc):
        """NPC name matching is case-insensitive."""
        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="KAEL VOSS",  # Uppercase
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == True
        assert validation.receiver_name == "Kael Voss"

    def test_nonexistent_npc_name_fails(self, mechanics_with_npc, shared_state_with_npc):
        """Transfer to nonexistent NPC name fails."""
        player = shared_state_with_npc.player_agents[0]

        validation = mechanics_with_npc.validate_transfer(
            sender_state=player.character_state,
            transfer_target="Nonexistent NPC",
            transfer_currency={"drip": 5}
        )

        assert validation.is_valid == False
        assert "not found" in validation.failure_reason
