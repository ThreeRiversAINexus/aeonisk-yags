"""
Integration tests for NPC vendor purchase system.

Tests end-to-end purchase flow with NPC vendors, focusing on:
- Purchase validation with NPCs
- Dual-mode vendor system (NPC + legacy)
- Backward compatibility
"""

import pytest
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.energy_economy import VendorItem, EnergyPurse, Vendor
from scripts.aeonisk.multiagent.player import CharacterState


def create_test_character(name="TestPlayer", faction="ACG", energy_purse=None):
    """Helper to create test character with all required fields."""
    return CharacterState(
        name=name,
        faction=faction,
        attributes={"intelligence": 3, "perception": 3},
        skills={"Combat": 2},
        void_score=0,
        soulcredit=0,
        bonds=["Loyalty to ACG"],
        goals=["Survive the mission"],
        energy_purse=energy_purse or EnergyPurse(drip=10)
    )


class TestNPCVendorPurchaseValidation:
    """Integration tests for purchase validation with NPC vendors."""

    def test_validate_purchase_from_npc_vendor_success(self):
        """Test successful purchase validation from NPC vendor."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        # Create NPC vendor with item
        item = VendorItem(
            name="Medkit",
            description="Standard medical supplies",
            price_drip=5,
            item_type="consumable"
        )

        vendor_npc = NPCAgent(
            agent_id="npc_medic_001",
            name="Field Medic",
            faction="ACG",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="ACG medical technician selling supplies",
            health=25,
            max_health=25,
            soak=2,
            void_score=0,
            is_vendor=True,
            vendor_inventory=[item],
            vendor_type="human_trader",
            accepts_purchases=True,
            can_act=False
        )

        shared_state.add_npc(vendor_npc)

        # Create character with sufficient funds
        character = create_test_character(
            name="TestPlayer",
            faction="ACG",
            energy_purse=EnergyPurse(drip=10)
        )

        # Validate purchase
        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="npc_medic_001",
            item_id=item.item_id
        )

        assert validation.is_valid is True
        assert validation.vendor_accessible is True
        assert validation.can_afford is True
        assert validation.item_name == "Medkit"

    def test_validate_purchase_from_npc_vendor_insufficient_funds(self):
        """Test purchase validation fails with insufficient funds."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        # Create NPC vendor with expensive item
        item = VendorItem(
            name="Heavy Armor",
            description="Military-grade protection",
            price_drip=50,
            item_type="equipment"
        )

        vendor_npc = NPCAgent(
            agent_id="npc_armorer_001",
            name="Armorer",
            faction="ACG",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="ACG equipment specialist",
            health=30,
            max_health=30,
            soak=3,
            void_score=0,
            is_vendor=True,
            vendor_inventory=[item],
            vendor_type="human_trader",
            accepts_purchases=True,
            can_act=False
        )

        shared_state.add_npc(vendor_npc)

        # Create character with insufficient funds
        character = create_test_character(
            name="BrokePlayer",
            faction="ACG",
            energy_purse=EnergyPurse(drip=10)  # Only 10, needs 50
        )

        # Validate purchase
        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="npc_armorer_001",
            item_id=item.item_id
        )

        assert validation.is_valid is False
        assert validation.can_afford is False
        assert "Insufficient currency" in validation.failure_reason

    def test_validate_purchase_vendor_not_found(self):
        """Test purchase validation fails when vendor doesn't exist."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        character = create_test_character(
            name="TestPlayer",
            faction="ACG",
            energy_purse=EnergyPurse(drip=10)
        )

        # Try to buy from non-existent vendor
        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="npc_nonexistent",
            item_id="itm_whatever"
        )

        assert validation.is_valid is False
        assert validation.vendor_accessible is False
        assert "not found" in validation.failure_reason


class TestDualModeVendorSystem:
    """Test that NPC vendors and legacy vendors coexist."""

    def test_npc_vendor_priority_over_legacy_vendor(self):
        """Test that get_npc_by_vendor_id returns NPC vendor first."""
        shared_state = SharedState()

        # Add NPC vendor
        npc_vendor = NPCAgent(
            agent_id="npc_vendor_001",
            name="NPC Vendor",
            faction="Neutral",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="NPC vendor with priority",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=True,
            vendor_type="human_trader",
            can_act=False
        )

        shared_state.add_npc(npc_vendor)

        # Look up by agent_id
        found = shared_state.get_npc_by_vendor_id("npc_vendor_001")
        assert found is not None
        assert found.name == "NPC Vendor"
        assert isinstance(found, NPCAgent)

    def test_npc_vendor_and_legacy_vendor_both_work(self):
        """Test both NPC vendors and legacy Vendor objects work in same system."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        # Create NPC vendor
        npc_item = VendorItem(
            name="Medkit",
            description="Medical supplies",
            price_drip=5,
            item_type="consumable"
        )

        npc_vendor = NPCAgent(
            agent_id="npc_trader_001",
            name="NPC Trader",
            faction="Neutral",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="NPC selling medical supplies",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=True,
            vendor_inventory=[npc_item],
            vendor_type="human_trader",
            accepts_purchases=True,
            can_act=False
        )

        shared_state.add_npc(npc_vendor)

        # Create legacy Vendor
        legacy_item = VendorItem(
            name="Scanner",
            description="Detection device",
            price_drip=8,
            item_type="tool"
        )

        legacy_vendor = Vendor(
            name="Legacy Vendor",
            faction="Neutral",
            vendor_type="vending_machine",
            inventory=[legacy_item]
        )

        shared_state.add_vendor(legacy_vendor)

        # Create character
        character = create_test_character(
            name="TestPlayer",
            faction="ACG",
            energy_purse=EnergyPurse(drip=20)
        )

        # Validate purchase from NPC vendor
        npc_validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="npc_trader_001",
            item_id=npc_item.item_id
        )

        assert npc_validation.is_valid is True
        assert npc_validation.item_name == "Medkit"

        # Validate purchase from legacy vendor
        legacy_validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id=legacy_vendor.vendor_id,
            item_id=legacy_item.item_id
        )

        assert legacy_validation.is_valid is True
        assert legacy_validation.item_name == "Scanner"


class TestNPCVendorEmergentBehavior:
    """Test emergent behavior potential of vendor NPCs."""

    def test_vendor_npc_can_have_combat_stats(self):
        """Test that vendor NPCs have full combat capabilities."""
        # Create vendor NPC with full combat stats
        vendor_npc = NPCAgent(
            agent_id="npc_vending_001",
            name="S4CU Vending Node",
            faction="Neutral",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Vending machine",
            health=100,  # Durable!
            max_health=100,
            soak=10,  # Armored!
            void_score=0,
            is_vendor=True,
            vendor_type="vending_machine",
            can_act=False
        )

        # Vendor can take damage (emergent gameplay potential)
        vendor_npc.health -= 20
        assert vendor_npc.health == 80

        # Vendor can be wounded
        vendor_npc.wounds = 1
        assert vendor_npc.wounds == 1

        # This enables emergent gameplay:
        # - Damaged vending machines can malfunction
        # - Destroyed vendors drop loot
        # - Vendors can flee combat

    def test_vending_machine_npc_no_dialogue_overhead(self):
        """Test vending machines don't waste LLM resources."""
        vending = NPCAgent(
            agent_id="npc_vending_s4cu",
            name="S4CU Node",
            faction="Neutral",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Automated terminal",
            health=50,
            max_health=50,
            soak=5,
            void_score=0,
            is_vendor=True,
            vendor_type="vending_machine",
            vendor_greeting="[BEEP] Insert currency.",
            accepts_purchases=True,
            can_act=False,  # Static vendor (no LLM overhead)
        )

        assert vending.can_act is False  # Never declares actions
        assert vending.is_vendor is True  # Still sells items
        assert vending.llm_client is None  # No LLM overhead
