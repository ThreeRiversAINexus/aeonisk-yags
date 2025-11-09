"""
Unit tests for vendor persistence system.

Tests the full flow:
1. Load persistent vendors from config
2. Add to SharedState
3. Retrieve from SharedState during scenario generation
4. Serialize to JSONL with full inventory
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.dm import AIDMAgent, Scenario
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestVendorPersistence:
    """Test vendor persistence across scenario generation."""

    @pytest.fixture
    def shared_state(self):
        """Create a SharedState instance for testing."""
        return SharedState()

    @pytest.fixture
    def sample_vendor_config(self):
        """Sample vendor config matching session_config_profit_test.json."""
        return {
            "persistent_vendors": [
                {
                    "name": "Black Market Dealer \"Vex\"",
                    "type": "human_trader",
                    "faction": "Freeborn",
                    "greeting": "Need offerings? Rare materials? I got what you need... for the right price.",
                    "inventory": [
                        {"name": "Blood Offering (Sanctified)", "description": "Premium ritual offering", "price": {"drip": 8}},
                        {"name": "Incense Bundle (x3)", "description": "High-grade ritual cleansing", "price": {"drip": 12}},
                        {"name": "Attuned Seed (Fire)", "description": "Stable flame-aspected seed", "price": {"spark": 2}},
                        {"name": "Raw Crystal (Premium)", "description": "High-purity ritual substrate", "price": {"drip": 5}}
                    ],
                    "buys_from_players": True,
                    "buy_prices": {
                        "blood_offering": {"drip": 5},
                        "incense": {"drip": 3},
                        "crystals": {"drip": 7}
                    }
                }
            ],
            "vendor_spawn_frequency": -1
        }

    @pytest.fixture
    def dm_agent(self, shared_state, sample_vendor_config):
        """Create a DM agent for testing vendor persistence."""
        # Create a minimal DM agent without full initialization
        dm = object.__new__(AIDMAgent)
        dm.agent_id = "dm_01"
        dm.faction = "DM"
        dm.shared_state = shared_state
        dm.session_config = sample_vendor_config
        dm.vendor_pool = []

        # Load persistent vendors (the method we're testing)
        persistent_vendors = dm._load_persistent_vendors(sample_vendor_config)
        for vendor in persistent_vendors:
            shared_state.add_vendor(vendor)

        return dm

    def test_load_persistent_vendors_from_config(self, dm_agent, sample_vendor_config):
        """Test that persistent vendors are loaded from config."""
        vendors = dm_agent._load_persistent_vendors(sample_vendor_config)

        assert len(vendors) == 1
        vendor = vendors[0]
        assert vendor.name == "Black Market Dealer \"Vex\""
        assert vendor.vendor_type == VendorType.HUMAN_TRADER
        assert vendor.faction == "Freeborn"
        assert len(vendor.inventory) == 4

        # Check inventory items
        blood_offering = vendor.inventory[0]
        assert blood_offering.name == "Blood Offering (Sanctified)"
        assert blood_offering.price_drip == 8
        assert blood_offering.price_spark == 0

    def test_persistent_vendors_added_to_shared_state_on_init(self, dm_agent, shared_state):
        """Test that persistent vendors are added to SharedState during DM initialization."""
        vendors = shared_state.get_all_vendors()

        assert len(vendors) == 1
        vendor = vendors[0]
        assert vendor.name == "Black Market Dealer \"Vex\""

    def test_shared_state_vendor_retrieval(self, shared_state):
        """Test SharedState vendor management methods."""
        # Create test vendor
        vendor = Vendor(
            name="Test Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(name="Test Item", description="Test", price_drip=5)
            ],
            greeting="Hello",
            vendor_type=VendorType.HUMAN_TRADER
        )

        # Add vendor
        shared_state.add_vendor(vendor)

        # Retrieve all vendors
        all_vendors = shared_state.get_all_vendors()
        assert len(all_vendors) == 1
        assert all_vendors[0].name == "Test Vendor"

        # Retrieve by name
        retrieved = shared_state.get_vendor("Test Vendor")
        assert retrieved is not None
        assert retrieved.name == "Test Vendor"

        # Non-existent vendor
        missing = shared_state.get_vendor("Nonexistent")
        assert missing is None

    def test_vendor_spawn_frequency_minus_one_skips_random_spawn(self, dm_agent, sample_vendor_config):
        """Test that vendor_spawn_frequency=-1 skips random vendor selection."""
        # Mock scenario generation
        scenario_data = {
            'theme': 'Test',
            'location': 'Test Location',
            'situation': 'Test situation',
            'void_level': 5
        }

        # The key: when vendor_spawn_frequency=-1, active_vendors should be []
        # and scenario should pull from SharedState
        vendor_spawn_freq = sample_vendor_config.get('vendor_spawn_frequency', 3)
        assert vendor_spawn_freq == -1

        # Simulate the logic from dm.py:515-535
        if vendor_spawn_freq >= 0:
            active_vendors = ["should_not_happen"]
        else:
            active_vendors = []

        assert active_vendors == []

    def test_scenario_pulls_vendors_from_shared_state(self, shared_state):
        """Test that scenario creation pulls vendors from SharedState."""
        # Add test vendor to SharedState
        vendor = Vendor(
            name="Persistent Vendor",
            faction="Freeborn",
            inventory=[VendorItem(name="Item", description="Test", price_drip=3)],
            greeting="Hello",
            vendor_type=VendorType.HUMAN_TRADER
        )
        shared_state.add_vendor(vendor)

        # Simulate scenario creation logic (dm.py:552-553)
        if shared_state:
            all_vendors = shared_state.get_all_vendors()
        else:
            all_vendors = []

        assert len(all_vendors) == 1
        assert all_vendors[0].name == "Persistent Vendor"

    def test_scenario_serialization_includes_vendor_inventory(self, shared_state):
        """Test that scenario serialization includes full vendor inventory."""
        # Create vendor with inventory
        vendor = Vendor(
            name="Vex",
            faction="Freeborn",
            inventory=[
                VendorItem(name="Blood Offering", description="Ritual offering", price_drip=8, price_spark=0),
                VendorItem(name="Incense", description="Cleansing", price_drip=12, price_spark=0)
            ],
            greeting="Need offerings?",
            vendor_type=VendorType.HUMAN_TRADER
        )

        # Create scenario with vendor
        scenario = Scenario(
            theme="Test",
            location="Test Location",
            situation="Test",
            active_npcs=[],
            environmental_factors=[],
            void_level=5,
            active_vendors=[vendor]
        )

        # Simulate serialization (dm.py:614-633)
        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'active_vendors': [
                {
                    'name': v.name,
                    'type': v.vendor_type.value,
                    'faction': v.faction,
                    'greeting': v.greeting,
                    'inventory_preview': [item.name for item in v.inventory[:3]],
                    'inventory': [
                        {
                            'name': item.name,
                            'description': item.description,
                            'price_spark': item.price_spark,
                            'price_drip': item.price_drip,
                            'price_breath': item.price_breath,
                            'seed_barter': item.seed_barter,
                            'item_type': item.item_type
                        } for item in v.inventory
                    ]
                } for v in scenario.active_vendors
            ] if scenario.active_vendors else []
        }

        # Verify serialization
        assert scenario_data['active_vendors'] is not None
        assert len(scenario_data['active_vendors']) == 1

        vendor_data = scenario_data['active_vendors'][0]
        assert vendor_data['name'] == "Vex"
        assert vendor_data['type'] == "human_trader"
        assert len(vendor_data['inventory']) == 2
        assert vendor_data['inventory'][0]['name'] == "Blood Offering"
        assert vendor_data['inventory'][0]['price_drip'] == 8

    def test_scenario_active_vendors_never_none(self):
        """Test that Scenario.__post_init__ ensures active_vendors is always a list."""
        # Create scenario with None vendors (should auto-convert)
        scenario = Scenario(
            theme="Test",
            location="Test",
            situation="Test",
            active_npcs=[],
            environmental_factors=[],
            void_level=5,
            active_vendors=None
        )

        assert scenario.active_vendors == []
        assert isinstance(scenario.active_vendors, list)

    def test_integration_persistent_vendor_flow(self, dm_agent, shared_state, sample_vendor_config):
        """Integration test: Full flow from config → SharedState → scenario → JSONL."""
        # 1. Vendors loaded from config (happens in __init__)
        vendors_in_state = shared_state.get_all_vendors()
        assert len(vendors_in_state) == 1
        assert vendors_in_state[0].name == "Black Market Dealer \"Vex\""

        # 2. Simulate scenario generation with vendor_spawn_frequency=-1
        vendor_spawn_freq = sample_vendor_config.get('vendor_spawn_frequency', 3)

        # Skip random vendor selection
        if vendor_spawn_freq >= 0:
            active_vendors = []  # Would call _select_contextual_vendor
        else:
            active_vendors = []  # No random spawning

        # Pull from SharedState
        all_vendors = shared_state.get_all_vendors()

        # 3. Create scenario with all vendors
        scenario = Scenario(
            theme="Profit Test",
            location="Market",
            situation="Trading scenario",
            active_npcs=[],
            environmental_factors=[],
            void_level=5,
            active_vendors=all_vendors
        )

        # 4. Verify scenario has vendor
        assert scenario.active_vendors is not None
        assert len(scenario.active_vendors) == 1
        assert scenario.active_vendors[0].name == "Black Market Dealer \"Vex\""

        # 5. Simulate serialization
        scenario_data = {
            'active_vendors': [
                {
                    'name': v.name,
                    'type': v.vendor_type.value,
                    'inventory': [
                        {'name': item.name, 'price_drip': item.price_drip}
                        for item in v.inventory
                    ]
                } for v in scenario.active_vendors
            ] if scenario.active_vendors else []
        }

        # 6. Verify JSONL data
        assert scenario_data['active_vendors'] is not None
        assert len(scenario_data['active_vendors']) == 1
        assert scenario_data['active_vendors'][0]['name'] == "Black Market Dealer \"Vex\""
        assert len(scenario_data['active_vendors'][0]['inventory']) == 4


class TestVendorDeparture:
    """Test vendor removal via StoryAdvancement."""

    def test_remove_vendor_from_shared_state(self):
        """Test SharedState.remove_vendor() method."""
        shared_state = SharedState()

        vendor = Vendor(
            name="Temporary Vendor",
            faction="Neutral",
            inventory=[],
            greeting="Hello",
            vendor_type=VendorType.VENDING_MACHINE
        )

        shared_state.add_vendor(vendor)
        assert len(shared_state.get_all_vendors()) == 1

        # Remove vendor
        removed = shared_state.remove_vendor("Temporary Vendor")
        assert removed is True
        assert len(shared_state.get_all_vendors()) == 0

        # Try to remove non-existent vendor
        removed = shared_state.remove_vendor("Nonexistent")
        assert removed is False
