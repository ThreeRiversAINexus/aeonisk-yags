"""
Unit tests for vendor status formatting in player prompts.

Tests that _format_vendor_status() includes:
1. Legacy Vendor objects (backward compatibility)
2. NPC vendors (is_vendor=True)
3. Inventory display with item IDs for both types
"""

import pytest
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.energy_economy import VendorItem


@pytest.fixture
def shared_state_with_npc_vendor():
    """Shared state with NPC vendor."""
    shared_state = SharedState()

    # Create NPC vendor with inventory
    vendor_items = [
        VendorItem(
            item_id="itm_medkit_01",
            name="Medkit",
            description="Standard medical supplies",
            price_drip=5,
            item_type="consumable"
        ),
        VendorItem(
            item_id="itm_scanner_02",
            name="Void Scanner",
            description="Handheld void detection device",
            price_drip=8,
            price_grain=1,
            item_type="tool"
        )
    ]

    npc_vendor = NPCAgent(
        agent_id="npc_trader_01",
        name="Supply Trader Vex",
        faction="Independent",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Grizzled trader selling medical supplies",
        health=25,
        max_health=25,
        soak=2,
        void_score=0,
        skills={"Negotiate": 4},
        is_vendor=True,
        vendor_inventory=vendor_items,
        vendor_greeting="Looking for supplies? Prices are fair.",
        vendor_type="human_trader",
        accepts_purchases=True
    )

    shared_state.npc_agents = [npc_vendor]
    return shared_state


@pytest.fixture
def player_agent(shared_state_with_npc_vendor):
    """Create minimal player agent for testing."""
    character_state = CharacterState(
        name="TestPlayer",
        faction="Freeborn",
        attributes={"intelligence": 3},
        skills={"Combat": 2},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[],
        energy_purse=EnergyPurse(drip=20)
    )

    # Create mock player with only the attributes we need
    class MockPlayer:
        def __init__(self, character_state, shared_state):
            self.character_state = character_state
            self.shared_state = shared_state

        def _format_vendor_status(self):
            """Import the real implementation from AIPlayerAgent."""
            # Import here to access the actual method
            import scripts.aeonisk.multiagent.player as player_module
            return player_module.AIPlayerAgent._format_vendor_status(self)

    return MockPlayer(character_state, shared_state_with_npc_vendor)


class TestVendorStatusFormatting:
    """Test that _format_vendor_status() shows NPC vendors."""

    def test_npc_vendor_shown_in_status(self, player_agent):
        """NPC vendor appears in vendor status output."""
        status = player_agent._format_vendor_status()

        assert "Supply Trader Vex" in status
        assert "npc_trader_01" in status  # Agent ID shown as vendor ID
        assert "human_trader" in status

    def test_npc_vendor_greeting_shown(self, player_agent):
        """NPC vendor greeting is displayed."""
        status = player_agent._format_vendor_status()

        assert "Looking for supplies? Prices are fair." in status

    def test_npc_vendor_inventory_shown(self, player_agent):
        """NPC vendor inventory is displayed with item IDs."""
        status = player_agent._format_vendor_status()

        # Check items are shown
        assert "Medkit" in status
        assert "Void Scanner" in status

        # Check item IDs are shown (critical for purchase validation)
        assert "itm_medkit_01" in status
        assert "itm_scanner_02" in status

        # Check prices are shown
        assert "5 Drip" in status
        # Note: price order is Grain first, then Drip (based on _format_vendor_status implementation)
        assert "1 Grain" in status and "8 Drip" in status

    def test_npc_vendor_inventory_count(self, player_agent):
        """NPC vendor inventory count is displayed."""
        status = player_agent._format_vendor_status()

        assert "Inventory (2 items)" in status

    def test_no_vendors_returns_message(self):
        """When no vendors present, returns 'No vendors present'."""
        shared_state = SharedState()

        class MockPlayer:
            def __init__(self, shared_state):
                self.shared_state = shared_state

            def _format_vendor_status(self):
                import scripts.aeonisk.multiagent.player as player_module
                return player_module.AIPlayerAgent._format_vendor_status(self)

        player = MockPlayer(shared_state)
        status = player._format_vendor_status()

        assert status == "No vendors present"

    def test_non_vendor_npc_not_shown(self, shared_state_with_npc_vendor):
        """NPCs without is_vendor=True are not shown."""
        # Add a non-vendor NPC
        civilian_npc = NPCAgent(
            agent_id="npc_civilian_01",
            name="Civilian Worker",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Civilian NPC",
            health=15,
            max_health=15,
            soak=0,
            void_score=0,
            skills={},
            is_vendor=False  # Not a vendor
        )
        shared_state_with_npc_vendor.npc_agents.append(civilian_npc)

        class MockPlayer:
            def __init__(self, shared_state):
                self.shared_state = shared_state

            def _format_vendor_status(self):
                import scripts.aeonisk.multiagent.player as player_module
                return player_module.AIPlayerAgent._format_vendor_status(self)

        player = MockPlayer(shared_state_with_npc_vendor)
        status = player._format_vendor_status()

        # Vendor NPC shown
        assert "Supply Trader Vex" in status

        # Civilian NPC not shown
        assert "Civilian Worker" not in status

    def test_npc_vendor_without_greeting(self, shared_state_with_npc_vendor):
        """NPC vendor without greeting still displays correctly."""
        # Add vendor without greeting (e.g., vending machine)
        vending_machine = NPCAgent(
            agent_id="npc_vending_01",
            name="Supply Dispenser",
            faction="Neutral",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Automated vending machine",
            health=80,
            max_health=80,
            soak=8,
            void_score=0,
            skills={},
            is_vendor=True,
            vendor_inventory=[
                VendorItem(
                    item_id="itm_energy_bar",
                    name="Energy Bar",
                    description="Nutrient bar",
                    price_drip=1,
                    item_type="consumable"
                )
            ],
            vendor_type="vending_machine",
            accepts_purchases=True
            # No vendor_greeting
        )
        shared_state_with_npc_vendor.npc_agents.append(vending_machine)

        class MockPlayer:
            def __init__(self, shared_state):
                self.shared_state = shared_state

            def _format_vendor_status(self):
                import scripts.aeonisk.multiagent.player as player_module
                return player_module.AIPlayerAgent._format_vendor_status(self)

        player = MockPlayer(shared_state_with_npc_vendor)
        status = player._format_vendor_status()

        # Both vendors shown
        assert "Supply Trader Vex" in status
        assert "Supply Dispenser" in status

        # Greeting only shown for vendor that has it
        assert "Looking for supplies?" in status

        # Both inventories shown
        assert "itm_medkit_01" in status
        assert "itm_energy_bar" in status
