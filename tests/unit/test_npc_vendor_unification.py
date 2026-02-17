"""
Tests for NPC-Vendor Unification System.

Verifies that NPCs can act as vendors with inventory, accept purchases,
and integrate seamlessly with the purchase system.
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.schemas.story_events import NPCSpawn
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import VendorItem, VendorType


class TestNPCAgentVendorFields:
    """Test vendor fields on NPCAgent."""

    def test_npc_with_vendor_fields(self):
        """Test creating NPC with vendor functionality enabled."""
        # Create vendor item
        item = VendorItem(
            name="Medkit",
            description="Standard medical supplies",
            price_drip=5,
            item_type="consumable"
        )

        npc = NPCAgent(
            agent_id="npc_trader_001",
            name="Black Market Dealer",
            faction="Freeborn",
            entity_type="neutral",
            disposition="wary",
            threat_level="armed_neutral",
            description="Hooded figure with cybernetic eyes",
            health=30,
            max_health=30,
            soak=3,
            void_score=2,
            is_vendor=True,
            vendor_inventory=[item],
            vendor_greeting="Keep your voice down. What do you need?",
            vendor_type="human_trader",
            accepts_purchases=True,
            can_act=False  # Disable LLM for tests
        )

        assert npc.is_vendor is True
        assert len(npc.vendor_inventory) == 1
        assert npc.vendor_inventory[0].name == "Medkit"
        assert npc.vendor_greeting == "Keep your voice down. What do you need?"
        assert npc.vendor_type == "human_trader"
        assert npc.accepts_purchases is True

    def test_npc_without_vendor_fields(self):
        """Test regular NPC without vendor functionality."""
        npc = NPCAgent(
            agent_id="npc_civilian_001",
            name="Freeborn Navigator",
            faction="Freeborn",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Weathered woman with neural optics",
            health=20,
            max_health=20,
            soak=2,
            void_score=0,
            can_act=False
        )

        assert npc.is_vendor is False
        assert len(npc.vendor_inventory) == 0
        assert npc.vendor_greeting is None
        assert npc.vendor_type is None
        assert npc.accepts_purchases is False

    def test_get_vendor_item_by_id(self):
        """Test getting vendor items by ID."""
        item1 = VendorItem(
            name="Medkit",
            description="Standard medical supplies",
            price_drip=5,
            item_type="consumable"
        )
        item2 = VendorItem(
            name="Scanner",
            description="Portable detection scanner",
            price_grain=2,
            item_type="tool"
        )

        npc = NPCAgent(
            agent_id="npc_vendor_001",
            name="Supply Merchant",
            faction="ACG",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Professional trader in ACG uniform",
            health=25,
            max_health=25,
            soak=2,
            void_score=0,
            is_vendor=True,
            vendor_inventory=[item1, item2],
            can_act=False
        )

        # Find items by ID
        found_item1 = npc.get_vendor_item_by_id(item1.item_id)
        found_item2 = npc.get_vendor_item_by_id(item2.item_id)

        assert found_item1 is not None
        assert found_item1.name == "Medkit"
        assert found_item2 is not None
        assert found_item2.name == "Scanner"

    def test_get_vendor_item_by_id_not_found(self):
        """Test getting non-existent item returns None."""
        npc = NPCAgent(
            agent_id="npc_vendor_001",
            name="Empty Vendor",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Vendor with no stock",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=True,
            vendor_inventory=[],
            can_act=False
        )

        result = npc.get_vendor_item_by_id("itm_nonexistent")
        assert result is None

    def test_get_vendor_item_on_non_vendor_npc(self):
        """Test calling get_vendor_item_by_id on non-vendor NPC."""
        npc = NPCAgent(
            agent_id="npc_civilian_001",
            name="Regular NPC",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Not a vendor",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=False,
            can_act=False
        )

        result = npc.get_vendor_item_by_id("itm_anything")
        assert result is None  # Should return None with warning


class TestNPCSpawnVendorFields:
    """Test NPCSpawn schema with vendor fields."""

    def test_npc_spawn_with_vendor_fields(self):
        """Test spawning NPC with vendor functionality."""
        item = VendorItem(
            name="Echo-Calibrator",
            description="Astral tuning device",
            price_spark=2,
            item_type="tool"
        )

        spawn = NPCSpawn(
            name="Tech Supplier",
            faction="ACG",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="ACG technician selling equipment",
            health=25,
            soak=2,
            skills={"engineering": 8},
            is_vendor=True,
            vendor_inventory=[item],
            vendor_greeting="ACG certified equipment. What do you need?",
            vendor_type="human_trader",
            accepts_purchases=True
        )

        assert spawn.is_vendor is True
        assert len(spawn.vendor_inventory) == 1
        assert spawn.vendor_inventory[0].name == "Echo-Calibrator"
        assert spawn.vendor_type == "human_trader"

    def test_npc_spawn_regular_npc(self):
        """Test spawning regular NPC without vendor fields."""
        spawn = NPCSpawn(
            name="Guide",
            faction="Freeborn",
            entity_type="ally",
            disposition="friendly",
            threat_level="non_combatant",
            description="Helpful guide offering navigation assistance",
            health=20,
            soak=1
        )

        assert spawn.is_vendor is False
        assert len(spawn.vendor_inventory) == 0
        assert spawn.vendor_greeting is None

    def test_npc_spawn_vending_machine(self):
        """Test spawning vending machine NPC (static vendor)."""
        item = VendorItem(
            name="Energy Bar",
            description="Nutrient ration",
            price_drip=1,
            item_type="consumable"
        )

        spawn = NPCSpawn(
            name="S4CU Vending Node",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Automated vending machine",
            health=50,
            soak=5,  # Durable
            is_vendor=True,
            vendor_inventory=[item],
            vendor_greeting="[BEEP] Select item and insert currency.",
            vendor_type="vending_machine",
            accepts_purchases=True
        )

        assert spawn.is_vendor is True
        assert spawn.vendor_type == "vending_machine"
        assert "BEEP" in spawn.vendor_greeting


class TestSharedStateNPCVendorLookup:
    """Test SharedState.get_npc_by_vendor_id()."""

    def test_find_vendor_npc_by_agent_id(self):
        """Test finding vendor NPC by agent_id."""
        shared_state = SharedState()

        vendor_npc = NPCAgent(
            agent_id="npc_trader_a1b2",
            name="Trader",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Merchant",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=True,
            can_act=False
        )

        shared_state.add_npc(vendor_npc)

        # Should find by agent_id
        found = shared_state.get_npc_by_vendor_id("npc_trader_a1b2")
        assert found is not None
        assert found.agent_id == "npc_trader_a1b2"
        assert found.is_vendor is True

    def test_non_vendor_npc_not_found_as_vendor(self):
        """Test that non-vendor NPCs are not returned."""
        shared_state = SharedState()

        regular_npc = NPCAgent(
            agent_id="npc_civilian_001",
            name="Civilian",
            faction="Independent",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="Regular person",
            health=15,
            max_health=15,
            soak=0,
            void_score=0,
            is_vendor=False,  # NOT a vendor
            can_act=False
        )

        shared_state.add_npc(regular_npc)

        # Should NOT find because is_vendor=False
        found = shared_state.get_npc_by_vendor_id("npc_civilian_001")
        assert found is None

    def test_nonexistent_vendor_id_returns_none(self):
        """Test looking up non-existent vendor ID."""
        shared_state = SharedState()

        found = shared_state.get_npc_by_vendor_id("npc_doesnt_exist")
        assert found is None

    def test_multiple_vendor_npcs(self):
        """Test with multiple vendor NPCs in state."""
        shared_state = SharedState()

        vendor1 = NPCAgent(
            agent_id="npc_trader_001",
            name="Trader 1",
            faction="ACG",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="First trader",
            health=20,
            max_health=20,
            soak=1,
            void_score=0,
            is_vendor=True,
            can_act=False
        )

        vendor2 = NPCAgent(
            agent_id="npc_trader_002",
            name="Trader 2",
            faction="Freeborn",
            entity_type="neutral",
            disposition="wary",
            threat_level="armed_neutral",
            description="Second trader",
            health=25,
            max_health=25,
            soak=2,
            void_score=0,
            is_vendor=True,
            can_act=False
        )

        regular_npc = NPCAgent(
            agent_id="npc_guide_001",
            name="Guide",
            faction="Independent",
            entity_type="ally",
            disposition="friendly",
            threat_level="non_combatant",
            description="Helpful guide",
            health=15,
            max_health=15,
            soak=0,
            void_score=0,
            is_vendor=False,
            can_act=False
        )

        shared_state.add_npc(vendor1)
        shared_state.add_npc(vendor2)
        shared_state.add_npc(regular_npc)

        # Should find both vendors
        found1 = shared_state.get_npc_by_vendor_id("npc_trader_001")
        found2 = shared_state.get_npc_by_vendor_id("npc_trader_002")

        assert found1 is not None
        assert found1.name == "Trader 1"
        assert found2 is not None
        assert found2.name == "Trader 2"

        # Should NOT find regular NPC
        found_guide = shared_state.get_npc_by_vendor_id("npc_guide_001")
        assert found_guide is None


class TestVendorNPCIntegration:
    """Integration tests for vendor NPC functionality."""

    def test_vendor_npc_has_combat_stats(self):
        """Test that vendor NPCs have full combat stats (funny but useful)."""
        vendor_npc = NPCAgent(
            agent_id="npc_vending_001",
            name="S4CU Vending Node",
            faction="Independent",
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

        # Vendor can take damage
        vendor_npc.health -= 20
        assert vendor_npc.health == 80

        # Vendor can be stunned
        vendor_npc.stuns = 2
        assert vendor_npc.stuns == 2

        # Vendor can be wounded
        vendor_npc.wounds = 1
        assert vendor_npc.wounds == 1

        # This is hilarious but allows emergent gameplay like:
        # - Damaged vending machines malfunction
        # - Destroyed vending machines drop loot
        # - Vendors fleeing combat

    def test_human_trader_can_dialogue(self):
        """Test human trader NPCs can have LLM client for dialogue."""
        trader = NPCAgent(
            agent_id="npc_trader_001",
            name="Experienced Trader",
            faction="Freeborn",
            entity_type="neutral",
            disposition="neutral",
            threat_level="armed_neutral",
            description="Grizzled merchant with bodyguards",
            health=30,
            max_health=30,
            soak=3,
            void_score=0,
            is_vendor=True,
            vendor_type="human_trader",
            vendor_greeting="Welcome, traveler. Fine wares for discerning customers.",
            accepts_purchases=True,
            can_act=True,  # Can dialogue
            llm_client=None  # Would be initialized in __post_init__ with llm_provider
        )

        assert trader.can_act is True  # Can declare dialogue actions
        assert trader.is_vendor is True  # Also sells items

    def test_vending_machine_no_dialogue(self):
        """Test vending machines don't act (static vendors)."""
        vending = NPCAgent(
            agent_id="npc_vending_001",
            name="S4CU Node",
            faction="Independent",
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
            llm_client=None
        )

        assert vending.can_act is False  # Never declares actions
        assert vending.is_vendor is True  # Still sells items
        assert vending.llm_client is None  # No LLM overhead
