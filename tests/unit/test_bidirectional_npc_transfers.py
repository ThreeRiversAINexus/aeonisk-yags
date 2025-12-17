"""
Unit tests for bidirectional NPC-PC transfers.

Tests:
1. PC->NPC transfer EXECUTION (validation works, execution fails)
2. NPC->PC transfer via new NPCAction transfer type
3. Edge cases (inventory creation, NPC senders)

TDD: These tests are written FIRST and should FAIL until implementation is complete.
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse
from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCAction


# =============================================================================
# FIXTURES
# =============================================================================

class MockPlayer:
    """Minimal player agent mock for testing."""
    def __init__(self, agent_id: str, character_state: CharacterState):
        self.agent_id = agent_id
        self.character_state = character_state
        self.position = None


@pytest.fixture
def player_with_currency():
    """Player with 20 drip, 5 spark."""
    state = CharacterState(
        name="TestPlayer",
        faction="ACG",
        attributes={"intelligence": 3},
        skills={"Combat": 2},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[],
        energy_purse=EnergyPurse(drip=20, spark=5),
        inventory={"Medkit": 2, "Ammo": 10}
    )
    return MockPlayer("player_01", state)


@pytest.fixture
def npc_vendor_with_currency():
    """Vendor NPC with 50 drip."""
    return NPCAgent(
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
        energy_purse=EnergyPurse(drip=50, spark=10)
    )


@pytest.fixture
def npc_without_inventory():
    """NPC without inventory attribute (should be created on transfer)."""
    return NPCAgent(
        agent_id="npc_civilian_01",
        name="Civilian",
        faction="Independent",
        entity_type="neutral",
        disposition="friendly",
        threat_level="non_combatant",
        description="Helpful civilian",
        health=10,
        max_health=10,
        soak=0,
        void_score=0,
        skills={},
        energy_purse=EnergyPurse(drip=10)
        # No inventory attribute
    )


@pytest.fixture
def shared_state_with_npc(player_with_currency, npc_vendor_with_currency):
    """Shared state with player and vendor NPC."""
    shared_state = SharedState()
    shared_state.player_agents = [player_with_currency]
    shared_state.npc_agents = [npc_vendor_with_currency]
    return shared_state


@pytest.fixture
def mechanics_with_npc(shared_state_with_npc):
    """Mechanics engine with NPC-enabled shared state."""
    return MechanicsEngine(shared_state=shared_state_with_npc)


# =============================================================================
# TEST: PC -> NPC TRANSFER EXECUTION
# =============================================================================

class TestPCToNPCTransferExecution:
    """
    Test that PC->NPC transfers EXECUTE after validation.

    Currently validation passes but execution fails because session.py
    only searches player_agents for the receiver (line 4527-4531).
    """

    def test_pc_to_npc_currency_transfer_executes(
        self, mechanics_with_npc, shared_state_with_npc,
        player_with_currency, npc_vendor_with_currency
    ):
        """Currency actually moves from PC purse to NPC purse."""
        # Initial state
        assert player_with_currency.character_state.energy_purse.drip == 20
        assert npc_vendor_with_currency.energy_purse.drip == 50

        # Validate transfer (this already works)
        validation = mechanics_with_npc.validate_transfer(
            sender_state=player_with_currency.character_state,
            transfer_target="Kael Voss",
            transfer_currency={"drip": 10}
        )
        assert validation.is_valid == True
        assert validation.receiver_agent_id == "npc_vendor_01"

        # Execute transfer using the helper we need to add
        # This simulates what session.py should do
        receiver_agent = _find_receiver_agent(
            shared_state_with_npc,
            validation.receiver_agent_id
        )

        # This is the critical assertion - receiver should be found
        assert receiver_agent is not None, \
            "Receiver agent not found - need to search npc_agents too"
        assert receiver_agent.agent_id == "npc_vendor_01"

        # Execute the actual transfer
        sender_purse = player_with_currency.character_state.energy_purse
        receiver_purse = _get_energy_purse(receiver_agent)

        assert receiver_purse is not None, \
            "Could not get NPC energy purse - need to handle NPC pattern"

        # Transfer currency
        sender_purse.transfer_currencies_to(
            receiver_purse=receiver_purse,
            currency_amounts={"drip": 10}
        )

        # Verify transfer executed
        assert player_with_currency.character_state.energy_purse.drip == 10
        assert npc_vendor_with_currency.energy_purse.drip == 60

    def test_pc_to_npc_item_transfer_executes(
        self, mechanics_with_npc, shared_state_with_npc,
        player_with_currency, npc_vendor_with_currency
    ):
        """Items move from PC inventory to NPC inventory."""
        # Initial state
        assert player_with_currency.character_state.inventory.get("Medkit", 0) == 2

        # NPC starts without inventory
        if not hasattr(npc_vendor_with_currency, 'inventory'):
            npc_vendor_with_currency.inventory = {}
        npc_vendor_with_currency.inventory = {}

        # Validate transfer
        validation = mechanics_with_npc.validate_transfer(
            sender_state=player_with_currency.character_state,
            transfer_target="Kael Voss",
            transfer_items={"Medkit": 1}
        )
        assert validation.is_valid == True

        # Find receiver
        receiver_agent = _find_receiver_agent(
            shared_state_with_npc,
            validation.receiver_agent_id
        )
        assert receiver_agent is not None

        # Execute item transfer
        sender_inv = player_with_currency.character_state.inventory
        receiver_inv = _get_inventory(receiver_agent)

        assert receiver_inv is not None, \
            "Could not get/create NPC inventory"

        # Transfer item
        sender_inv["Medkit"] -= 1
        receiver_inv["Medkit"] = receiver_inv.get("Medkit", 0) + 1

        # Verify
        assert player_with_currency.character_state.inventory["Medkit"] == 1
        assert receiver_inv["Medkit"] == 1

    def test_pc_to_npc_transfer_creates_npc_inventory(
        self, mechanics_with_npc, shared_state_with_npc,
        player_with_currency, npc_without_inventory
    ):
        """Item transfer creates NPC inventory dict if None."""
        # Add NPC without inventory to shared state
        shared_state_with_npc.npc_agents.append(npc_without_inventory)

        # NPC has no inventory
        assert not hasattr(npc_without_inventory, 'inventory') or \
               npc_without_inventory.inventory is None

        # Validate transfer
        validation = mechanics_with_npc.validate_transfer(
            sender_state=player_with_currency.character_state,
            transfer_target="Civilian",
            transfer_items={"Medkit": 1}
        )
        assert validation.is_valid == True

        # Get/create inventory for NPC
        receiver_inv = _get_inventory(npc_without_inventory)

        assert receiver_inv is not None, \
            "_get_inventory should create inventory for NPC"
        assert isinstance(receiver_inv, dict)

        # Transfer should be possible
        receiver_inv["Medkit"] = 1
        assert npc_without_inventory.inventory["Medkit"] == 1


# =============================================================================
# TEST: NPC ACTION TRANSFER SCHEMA
# =============================================================================

class TestNPCActionTransfer:
    """Test NPCAction schema supports transfer action type."""

    def test_npc_can_declare_transfer_action(self):
        """NPCAction schema accepts transfer action type."""
        action = NPCAction(
            action_type="transfer",
            reason="Giving spare medkit to injured player who helped me",
            transfer_target="player_01",
            transfer_items={"Medkit": 1}
        )
        assert action.action_type == "transfer"
        assert action.transfer_target == "player_01"
        assert action.transfer_items == {"Medkit": 1}

    def test_npc_transfer_with_currency(self):
        """NPC can transfer currency."""
        action = NPCAction(
            action_type="transfer",
            reason="Payment for escort services as promised",
            transfer_target="Ash Vex",
            transfer_currency={"drip": 15, "spark": 2}
        )
        assert action.transfer_currency == {"drip": 15, "spark": 2}

    def test_npc_transfer_with_both(self):
        """NPC can transfer both currency and items."""
        action = NPCAction(
            action_type="transfer",
            reason="Reward for completing the task",
            transfer_target="player_01",
            transfer_currency={"drip": 10},
            transfer_items={"KeyCard": 1}
        )
        assert action.transfer_currency == {"drip": 10}
        assert action.transfer_items == {"KeyCard": 1}

    def test_npc_transfer_requires_target(self):
        """Transfer action requires transfer_target."""
        with pytest.raises(ValidationError) as exc_info:
            NPCAction(
                action_type="transfer",
                reason="Transferring supplies to someone",
                transfer_currency={"drip": 5}
                # Missing transfer_target
            )
        assert "transfer_target" in str(exc_info.value).lower()

    def test_npc_transfer_requires_currency_or_items(self):
        """Transfer action requires at least one of currency/items."""
        with pytest.raises(ValidationError) as exc_info:
            NPCAction(
                action_type="transfer",
                reason="Empty transfer attempt",
                transfer_target="player_01"
                # Missing both transfer_currency and transfer_items
            )
        assert "currency" in str(exc_info.value).lower() or \
               "items" in str(exc_info.value).lower()

    def test_existing_npc_actions_still_work(self):
        """Existing NPC action types still work (backwards compatibility)."""
        # Dialogue action
        dialogue = NPCAction(
            action_type="dialogue",
            reason="Answering the player's question about the vault",
            dialogue_content="The vault is in the basement, past the security checkpoint."
        )
        assert dialogue.action_type == "dialogue"

        # Flee action
        flee = NPCAction(
            action_type="flee",
            reason="The combat is too dangerous, need to escape"
        )
        assert flee.action_type == "flee"

        # Pass action
        pass_action = NPCAction(
            action_type="pass",
            reason="Nothing to do this round, waiting for developments"
        )
        assert pass_action.action_type == "pass"


# =============================================================================
# TEST: NPC -> PC TRANSFER EXECUTION
# =============================================================================

class TestNPCToPlayerTransferExecution:
    """Test NPC-initiated transfers to players."""

    def test_npc_to_pc_currency_transfer_executes(
        self, shared_state_with_npc,
        player_with_currency, npc_vendor_with_currency
    ):
        """NPC-initiated currency transfer executes."""
        # Initial state
        assert npc_vendor_with_currency.energy_purse.drip == 50
        assert player_with_currency.character_state.energy_purse.drip == 20

        # Create NPC transfer action
        action = NPCAction(
            action_type="transfer",
            reason="Payment for helping defend the shop",
            transfer_target="player_01",
            transfer_currency={"drip": 20}
        )

        # Find receiver (player)
        receiver_agent = _find_receiver_agent(
            shared_state_with_npc,
            "player_01"
        )
        assert receiver_agent is not None
        assert receiver_agent.agent_id == "player_01"

        # Execute transfer
        sender_purse = _get_energy_purse(npc_vendor_with_currency)
        receiver_purse = _get_energy_purse(receiver_agent)

        assert sender_purse is not None
        assert receiver_purse is not None

        sender_purse.transfer_currencies_to(
            receiver_purse=receiver_purse,
            currency_amounts=action.transfer_currency
        )

        # Verify
        assert npc_vendor_with_currency.energy_purse.drip == 30
        assert player_with_currency.character_state.energy_purse.drip == 40

    def test_npc_to_pc_item_transfer_executes(
        self, shared_state_with_npc,
        player_with_currency, npc_vendor_with_currency
    ):
        """NPC-initiated item transfer executes."""
        # Give NPC some items
        npc_vendor_with_currency.inventory = {"HealthPack": 3}

        # Initial player inventory
        initial_hp = player_with_currency.character_state.inventory.get("HealthPack", 0)
        assert initial_hp == 0

        # Create NPC transfer action
        action = NPCAction(
            action_type="transfer",
            reason="Giving a health pack to the injured player",
            transfer_target="TestPlayer",
            transfer_items={"HealthPack": 1}
        )

        # Find receiver
        receiver_agent = _find_receiver_agent(
            shared_state_with_npc,
            "TestPlayer"  # By name this time
        )
        assert receiver_agent is not None

        # Execute item transfer
        sender_inv = _get_inventory(npc_vendor_with_currency)
        receiver_inv = _get_inventory(receiver_agent)

        # Transfer
        item_name = "HealthPack"
        amount = 1
        sender_inv[item_name] -= amount
        receiver_inv[item_name] = receiver_inv.get(item_name, 0) + amount

        # Verify
        assert npc_vendor_with_currency.inventory["HealthPack"] == 2
        assert player_with_currency.character_state.inventory["HealthPack"] == 1


# =============================================================================
# TEST: VALIDATE_TRANSFER FOR NPC SENDERS
# =============================================================================

class TestValidateTransferNPCSender:
    """Test validate_transfer works with NPC as sender."""

    def test_validate_npc_sender_currency(
        self, mechanics_with_npc, shared_state_with_npc,
        npc_vendor_with_currency
    ):
        """validate_transfer works with NPC sender."""
        # NPC has 50 drip, wants to send 20
        validation = mechanics_with_npc.validate_transfer(
            sender_state=npc_vendor_with_currency,  # NPC as sender
            transfer_target="TestPlayer",
            transfer_currency={"drip": 20}
        )

        assert validation.is_valid == True
        assert validation.receiver_name == "TestPlayer"

    def test_validate_npc_sender_insufficient_funds(
        self, mechanics_with_npc, shared_state_with_npc,
        npc_vendor_with_currency
    ):
        """NPC sender with insufficient funds fails validation."""
        # NPC has 50 drip, tries to send 100
        validation = mechanics_with_npc.validate_transfer(
            sender_state=npc_vendor_with_currency,
            transfer_target="TestPlayer",
            transfer_currency={"drip": 100}
        )

        assert validation.is_valid == False
        assert "insufficient" in validation.failure_reason.lower() or \
               "currency" in validation.failure_reason.lower()


# =============================================================================
# HELPER FUNCTIONS (to be moved to session.py)
# =============================================================================

def _find_receiver_agent(shared_state, identifier: str):
    """
    Find receiver agent by agent_id or name.
    Searches BOTH player_agents AND npc_agents.

    This helper simulates what session.py SHOULD do but currently doesn't.
    """
    # Search players first
    for agent in shared_state.player_agents:
        if agent.agent_id == identifier:
            return agent
        if hasattr(agent, 'character_state') and \
           agent.character_state.name.lower() == identifier.lower():
            return agent

    # Then search NPCs
    if hasattr(shared_state, 'npc_agents'):
        for npc in shared_state.npc_agents:
            if npc.agent_id == identifier:
                return npc
            if hasattr(npc, 'name') and npc.name.lower() == identifier.lower():
                return npc

    return None


def _get_energy_purse(agent):
    """
    Get energy purse from player or NPC agent.

    Handles both patterns:
    - Player: agent.character_state.energy_purse
    - NPC: agent.energy_purse
    """
    # Player pattern
    if hasattr(agent, 'character_state') and \
       hasattr(agent.character_state, 'energy_purse'):
        return agent.character_state.energy_purse

    # NPC pattern
    if hasattr(agent, 'energy_purse'):
        return agent.energy_purse

    return None


def _get_inventory(agent):
    """
    Get inventory dict from player or NPC, creating if needed.

    Handles both patterns:
    - Player: agent.character_state.inventory
    - NPC: agent.inventory (may need to create)
    """
    # Player pattern
    if hasattr(agent, 'character_state'):
        if not hasattr(agent.character_state, 'inventory') or \
           agent.character_state.inventory is None:
            agent.character_state.inventory = {}
        return agent.character_state.inventory

    # NPC pattern
    if not hasattr(agent, 'inventory') or agent.inventory is None:
        agent.inventory = {}
    return agent.inventory
