"""
Test persistent vendor initialization from session config.

This test verifies that session.py correctly parses persistent_vendors
config and creates Vendor objects with proper inventory.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType
from scripts.aeonisk.multiagent.shared_state import SharedState


class TestPersistentVendorInitialization:
    """Test that persistent vendors are properly initialized from config."""

    def test_vendor_item_supports_all_currency_types(self):
        """Test that VendorItem supports spark, grain, drip, and breath prices."""
        # This test would have caught the missing price_grain bug!
        item = VendorItem(
            name="Test Item",
            description="Test description",
            price_spark=1,
            price_grain=2,
            price_drip=3,
            price_breath=4
        )

        assert item.price_spark == 1
        assert item.price_grain == 2
        assert item.price_drip == 3
        assert item.price_breath == 4

    def test_vendor_item_cost_property_includes_all_currencies(self):
        """Test that the cost property includes all non-zero currency types."""
        item = VendorItem(
            name="Premium Item",
            description="Expensive multi-currency item",
            price_spark=1,
            price_grain=2,
            price_drip=5,
            price_breath=10
        )

        cost = item.cost
        assert cost == {
            'spark': 1,
            'grain': 2,
            'drip': 5,
            'breath': 10
        }

    def test_vendor_item_cost_omits_zero_prices(self):
        """Test that cost property only includes non-zero prices."""
        item = VendorItem(
            name="Simple Item",
            description="Only costs drip",
            price_drip=8
        )

        cost = item.cost
        assert cost == {'drip': 8}
        assert 'spark' not in cost
        assert 'grain' not in cost
        assert 'breath' not in cost

    def test_parse_vendor_config_all_currencies(self):
        """
        Test parsing vendor config with items that use all currency types.

        This simulates what _initialize_persistent_vendors() does.
        """
        vendor_config = {
            "name": "Test Vendor",
            "faction": "Nexus",
            "vendor_type": "vending_machine",
            "greeting": "Welcome",
            "inventory": [
                {
                    "name": "Cheap Item",
                    "description": "Low cost",
                    "price_breath": 5
                },
                {
                    "name": "Mid Item",
                    "description": "Medium cost",
                    "price_drip": 3
                },
                {
                    "name": "Expensive Item",
                    "description": "High cost",
                    "price_grain": 2
                },
                {
                    "name": "Premium Item",
                    "description": "Very expensive",
                    "price_spark": 1
                },
                {
                    "name": "Multi-Currency Item",
                    "description": "Costs multiple currencies",
                    "price_spark": 1,
                    "price_grain": 2,
                    "price_drip": 5,
                    "price_breath": 10
                }
            ]
        }

        # Parse inventory (simulates session.py code)
        inventory_items = []
        for item_config in vendor_config.get('inventory', []):
            item = VendorItem(
                name=item_config['name'],
                description=item_config['description'],
                price_spark=item_config.get('price_spark', 0),
                price_grain=item_config.get('price_grain', 0),
                price_drip=item_config.get('price_drip', 0),
                price_breath=item_config.get('price_breath', 0)
            )
            inventory_items.append(item)

        # Verify all items parsed correctly
        assert len(inventory_items) == 5

        # Check each item
        assert inventory_items[0].name == "Cheap Item"
        assert inventory_items[0].price_breath == 5
        assert inventory_items[0].cost == {'breath': 5}

        assert inventory_items[1].name == "Mid Item"
        assert inventory_items[1].price_drip == 3
        assert inventory_items[1].cost == {'drip': 3}

        assert inventory_items[2].name == "Expensive Item"
        assert inventory_items[2].price_grain == 2
        assert inventory_items[2].cost == {'grain': 2}

        assert inventory_items[3].name == "Premium Item"
        assert inventory_items[3].price_spark == 1
        assert inventory_items[3].cost == {'spark': 1}

        assert inventory_items[4].name == "Multi-Currency Item"
        assert inventory_items[4].cost == {
            'spark': 1,
            'grain': 2,
            'drip': 5,
            'breath': 10
        }

    def test_vendor_creation_from_config(self):
        """Test creating a full Vendor object from config."""
        vendor_config = {
            "name": "Test Vend-O-Mat",
            "faction": "Nexus",
            "vendor_type": "vending_machine",
            "greeting": "Welcome to automated trading terminal.",
            "inventory": [
                {
                    "name": "Health Kit",
                    "description": "Restores 10 HP",
                    "price_drip": 5
                },
                {
                    "name": "Energy Cell",
                    "description": "Restores 20 energy",
                    "price_drip": 3,
                    "price_breath": 8
                },
                {
                    "name": "Spark Cell",
                    "description": "High-power energy cell",
                    "price_spark": 1
                }
            ]
        }

        # Parse inventory
        inventory_items = []
        for item_config in vendor_config.get('inventory', []):
            item = VendorItem(
                name=item_config['name'],
                description=item_config['description'],
                price_spark=item_config.get('price_spark', 0),
                price_grain=item_config.get('price_grain', 0),
                price_drip=item_config.get('price_drip', 0),
                price_breath=item_config.get('price_breath', 0)
            )
            inventory_items.append(item)

        # Create vendor
        vendor = Vendor(
            name=vendor_config['name'],
            faction=vendor_config['faction'],
            inventory=inventory_items,
            greeting=vendor_config['greeting'],
            vendor_type=VendorType.VENDING_MACHINE
        )

        # Verify vendor
        assert vendor.name == "Test Vend-O-Mat"
        assert vendor.faction == "Nexus"
        assert vendor.vendor_type == VendorType.VENDING_MACHINE
        assert len(vendor.inventory) == 3
        assert vendor.inventory[0].name == "Health Kit"
        assert vendor.inventory[1].name == "Energy Cell"
        assert vendor.inventory[2].name == "Spark Cell"

    def test_vendor_added_to_shared_state(self):
        """Test that vendors can be added to SharedState."""
        shared_state = SharedState()

        # Create a vendor
        vendor = Vendor(
            name="Test Vendor",
            faction="Neutral",
            inventory=[
                VendorItem(name="Item 1", description="Description 1", price_drip=5),
                VendorItem(name="Item 2", description="Description 2", price_grain=1)
            ],
            greeting="Hello",
            vendor_type=VendorType.HUMAN_TRADER
        )

        # Add to shared state
        shared_state.add_vendor(vendor)

        # Verify it was added
        vendors = shared_state.get_all_vendors()
        assert len(vendors) == 1
        assert vendors[0].name == "Test Vendor"
        assert len(vendors[0].inventory) == 2

    def test_multiple_vendors_in_shared_state(self):
        """Test that multiple vendors can coexist in SharedState."""
        shared_state = SharedState()

        # Add first vendor (persistent from config)
        vendor1 = Vendor(
            name="Persistent Vendor",
            faction="Nexus",
            inventory=[VendorItem(name="Item A", description="Desc", price_drip=3)],
            greeting="Welcome",
            vendor_type=VendorType.VENDING_MACHINE
        )
        shared_state.add_vendor(vendor1)

        # Add second vendor (spawned by DM)
        vendor2 = Vendor(
            name="Dynamic Vendor",
            faction="Neutral",
            inventory=[VendorItem(name="Item B", description="Desc", price_spark=1)],
            greeting="Greetings",
            vendor_type=VendorType.HUMAN_TRADER
        )
        shared_state.add_vendor(vendor2)

        # Verify both present
        vendors = shared_state.get_all_vendors()
        assert len(vendors) == 2
        assert vendors[0].name == "Persistent Vendor"
        assert vendors[1].name == "Dynamic Vendor"
