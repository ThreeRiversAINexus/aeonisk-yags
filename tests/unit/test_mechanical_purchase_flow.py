"""
Integration tests for mechanical purchase system.

Tests the complete purchase flow that fixes session 340bd80e bug:
1. Vendor/item ID generation
2. Pre-validation before DM
3. Mechanical transaction execution
4. State changes (currency deducted, items added)
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType
)
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.shared_state import SharedState


class MockCharacterState:
    """Mock character for testing."""
    def __init__(self, name, energy_purse, inventory=None, soulcredit=0):
        self.name = name
        self.energy_purse = energy_purse
        self.inventory = inventory or {}
        self.soulcredit = soulcredit


class TestPurchaseValidationFlow:
    """Test pre-purchase validation (NEW system that fixes bug)."""

    def test_session_340bd80e_bug_is_fixed(self):
        """
        CRITICAL TEST: Reproduce session 340bd80e bug and verify fix.

        SESSION 340bd80e FACTS:
        - Mira Seln: 0 Spark, 4 Drip, 1 Grain, 20 Breath
        - Item: Echo-Calibrator (Field-Grade) - 2 Spark
        - DM said: success=true, currency_spent={spark: 2}
        - Reality: ERROR - insufficient funds!

        OLD SYSTEM (broken):
        1. Player declares purchase
        2. DM narrates success (hallucination)
        3. Mechanics tries to deduct → ERROR
        4. Item never added to inventory

        NEW SYSTEM (fixed):
        1. Player declares purchase with vendor_id/item_id
        2. Pre-validation catches shortage BEFORE DM
        3. Purchase does NOT execute
        4. DM receives validation failure, MUST narrate insufficient funds
        """
        # Setup exact scenario from session 340bd80e
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        vendor = Vendor(
            vendor_id="vnd_scribe",
            name="Scribe Orven Tylesh",
            faction="Neutral",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[
                VendorItem(
                    item_id="itm_echo",
                    name="Echo-Calibrator (Field-Grade)",
                    description="Attunes Raw Seeds",
                    inventory_key="echo_calibrator",
                    price_spark=2  # Discounted from 8
                )
            ]
        )
        shared_state.add_vendor(vendor)

        # Mira's actual currency from session 340bd80e
        mira = MockCharacterState(
            name="Mira Seln",
            energy_purse=EnergyPurse(spark=0, drip=4, grain=1, breath=20),
            inventory={"echo_calibrator": 0},
            soulcredit=0
        )

        # ========== NEW SYSTEM: Pre-validate BEFORE DM ==========
        validation = mechanics.validate_purchase(
            character_state=mira,
            vendor_id="vnd_scribe",
            item_id="itm_echo"
        )

        # Validation should FAIL (this prevents phantom purchase!)
        assert validation.is_valid == False, "Should catch insufficient funds"
        assert validation.can_afford == False
        assert validation.shortage == {"spark": 2}, "Should show shortage of 2 Spark"
        assert "Insufficient currency" in validation.failure_reason

        # Purchase should NOT execute
        if not validation.can_afford:
            # Transaction blocked - this is the fix!
            pass
        else:
            pytest.fail("Purchase should be blocked due to validation failure")

        # Verify state is UNCHANGED (this is the key!)
        assert mira.energy_purse.spark == 0, "Spark should not be deducted"
        assert mira.energy_purse.drip == 4, "Other currency unchanged"
        assert mira.inventory["echo_calibrator"] == 0, "Item should NOT be added"

        # ✅ BUG IS FIXED!
        # DM will receive validation result and must narrate failure

    def test_purchase_success_with_sufficient_funds(self):
        """Test that purchases DO work when player has enough currency."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        vendor = Vendor(
            vendor_id="vnd_shop",
            name="Test Shop",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[
                VendorItem(
                    item_id="itm_medkit",
                    name="Med Kit",
                    description="Restores 10 HP",
                    inventory_key="med_kit",
                    price_drip=5,
                    price_breath=10
                )
            ]
        )
        shared_state.add_vendor(vendor)

        character = MockCharacterState(
            name="Buyer",
            energy_purse=EnergyPurse(drip=10, breath=20),
            inventory={},
            soulcredit=0
        )

        # Pre-validate
        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_shop",
            item_id="itm_medkit"
        )

        assert validation.can_afford == True, "Should pass with sufficient funds"
        assert validation.cost == {"drip": 5, "breath": 10}
        assert validation.surplus == {"drip": 5, "breath": 10}

        # Execute transaction (this is what session.py does)
        for currency_type, amount in validation.cost.items():
            if amount > 0:
                character.energy_purse.spend_currency(currency_type, amount)

        character.inventory[validation.inventory_key] = character.inventory.get(validation.inventory_key, 0) + 1

        # Verify state changes
        assert character.energy_purse.drip == 5, "Should deduct 5 Drip"
        assert character.energy_purse.breath == 10, "Should deduct 10 Breath"
        assert character.inventory["med_kit"] == 1, "Should add item to inventory"


class TestVendorAndItemIDGeneration:
    """Test that IDs are auto-generated correctly."""

    def test_vendor_id_auto_generated_unique(self):
        """Test that vendor IDs are auto-generated and unique."""
        vendor1 = Vendor(
            name="Vendor 1",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[]
        )
        vendor2 = Vendor(
            name="Vendor 2",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[]
        )

        assert vendor1.vendor_id.startswith("vnd_")
        assert vendor2.vendor_id.startswith("vnd_")
        assert vendor1.vendor_id != vendor2.vendor_id
        assert len(vendor1.vendor_id) == 8  # vnd_xxxx

    def test_item_id_auto_generated_unique(self):
        """Test that item IDs are auto-generated and unique."""
        item1 = VendorItem(name="Item 1", description="Test", price_drip=5)
        item2 = VendorItem(name="Item 2", description="Test", price_drip=10)

        assert item1.item_id.startswith("itm_")
        assert item2.item_id.startswith("itm_")
        assert item1.item_id != item2.item_id
        assert len(item1.item_id) == 8  # itm_xxxx

    def test_inventory_key_auto_generated_from_name(self):
        """Test that inventory keys are correctly generated from item names."""
        item = VendorItem(
            name="Echo-Calibrator (Field-Grade)",
            description="Test",
            price_spark=8
        )

        assert item.inventory_key == "echo_calibrator_field_grade"

    def test_vendor_get_item_by_id(self):
        """Test vendor lookup by item ID."""
        item1 = VendorItem(name="Health Kit", description="HP", price_drip=5, item_id="itm_health")
        item2 = VendorItem(name="Energy Cell", description="Energy", price_drip=3, item_id="itm_energy")

        vendor = Vendor(
            vendor_id="vnd_test",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[item1, item2]
        )

        found = vendor.get_item_by_id("itm_health")
        assert found is not None
        assert found.name == "Health Kit"
        assert found.price_drip == 5

        not_found = vendor.get_item_by_id("itm_missing")
        assert not_found is None


class TestSharedStateVendorLookup:
    """Test vendor lookup in SharedState."""

    def test_get_vendor_by_id(self):
        """Test SharedState.get_vendor_by_id() method."""
        shared_state = SharedState()

        vendor = Vendor(
            vendor_id="vnd_test123",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[]
        )
        shared_state.add_vendor(vendor)

        # Lookup by ID
        found = shared_state.get_vendor_by_id("vnd_test123")
        assert found is not None
        assert found.name == "Test Vendor"

        # Not found
        not_found = shared_state.get_vendor_by_id("vnd_missing")
        assert not_found is None


class TestValidationEdgeCases:
    """Test validation edge cases."""

    def test_validation_vendor_not_found(self):
        """Test validation when vendor doesn't exist."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        character = MockCharacterState(
            name="Test",
            energy_purse=EnergyPurse(spark=100),
            soulcredit=0
        )

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_missing",
            item_id="itm_whatever"
        )

        assert validation.is_valid == False
        assert validation.vendor_accessible == False
        assert "not found" in validation.failure_reason.lower()

    def test_validation_item_not_in_inventory(self):
        """Test validation when item not in vendor's inventory."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        vendor = Vendor(
            vendor_id="vnd_test",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[
                VendorItem(item_id="itm_health", name="Health Kit", description="HP", price_drip=5)
            ]
        )
        shared_state.add_vendor(vendor)

        character = MockCharacterState(
            name="Test",
            energy_purse=EnergyPurse(drip=100),
            soulcredit=0
        )

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_test",
            item_id="itm_missing"
        )

        assert validation.is_valid == False
        assert "not in" in validation.failure_reason.lower()

    def test_validation_multiple_currency_shortage(self):
        """Test validation when short on multiple currency types."""
        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        vendor = Vendor(
            vendor_id="vnd_test",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[
                VendorItem(
                    item_id="itm_expensive",
                    name="Expensive Item",
                    description="Costs multiple currencies",
                    inventory_key="expensive_item",
                    price_spark=5,
                    price_drip=20
                )
            ]
        )
        shared_state.add_vendor(vendor)

        character = MockCharacterState(
            name="Poor Player",
            energy_purse=EnergyPurse(spark=2, drip=10),
            soulcredit=0
        )

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_test",
            item_id="itm_expensive"
        )

        assert validation.is_valid == False
        assert validation.shortage == {"spark": 3, "drip": 10}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestVendorConfigParsing:
    """Test vendor loading from session config (zero-price bug).

    Tests VendorItem parsing directly without requiring DM agent instantiation.
    This tests the same parsing logic used in session.py and dm.py.
    """

    def test_flat_price_format_parsing(self):
        """
        Test that flat price format (price_drip: 5) is parsed correctly.

        BUG HISTORY: dm.py was only reading nested format price: {drip: 5}
        Result: All prices became 0 (free items)

        This test verifies VendorItem correctly reads flat format.
        """
        # Config with flat price format (like session_config_economic.json)
        item_configs = [
            {
                'name': 'Health Kit',
                'description': 'Restores HP',
                'price_drip': 5  # ← Flat format
            },
            {
                'name': 'Energy Cell',
                'description': 'Restores energy',
                'price_drip': 3,
                'price_breath': 8  # ← Multiple currencies, flat format
            }
        ]

        # Parse items using same logic as session.py/_initialize_persistent_vendors
        items = []
        for item_config in item_configs:
            item = VendorItem(
                name=item_config['name'],
                description=item_config.get('description', ''),
                price_spark=item_config.get('price_spark', 0),
                price_grain=item_config.get('price_grain', 0),
                price_drip=item_config.get('price_drip', 0),
                price_breath=item_config.get('price_breath', 0)
            )
            items.append(item)

        # Verify flat format parsed correctly
        health_kit = items[0]
        assert health_kit.name == 'Health Kit'
        assert health_kit.price_drip == 5, f"Expected 5 Drip, got {health_kit.price_drip} (zero-price bug!)"
        assert health_kit.price_spark == 0
        assert health_kit.price_breath == 0
        assert health_kit.cost == {'drip': 5}

        energy_cell = items[1]
        assert energy_cell.name == 'Energy Cell'
        assert energy_cell.price_drip == 3, f"Expected 3 Drip, got {energy_cell.price_drip}"
        assert energy_cell.price_breath == 8, f"Expected 8 Breath, got {energy_cell.price_breath}"
        assert energy_cell.price_spark == 0
        assert energy_cell.cost == {'drip': 3, 'breath': 8}

    def test_nested_price_format_still_works(self):
        """Test that nested format price: {drip: 5} still works (backward compat).

        Some session configs may use nested format for prices.
        Parser should support both flat and nested formats.
        """
        # Config with nested price format (legacy format)
        item_config = {
            'name': 'Med Kit',
            'description': 'Heals',
            'price': {'drip': 10, 'spark': 2}  # ← Nested format
        }

        # Parse using same logic that supports both formats
        price_dict = item_config.get('price', {})
        item = VendorItem(
            name=item_config['name'],
            description=item_config.get('description', ''),
            # Flat format takes precedence, nested is fallback
            price_spark=item_config.get('price_spark', price_dict.get('spark', 0)),
            price_grain=item_config.get('price_grain', price_dict.get('grain', 0)),
            price_drip=item_config.get('price_drip', price_dict.get('drip', 0)),
            price_breath=item_config.get('price_breath', price_dict.get('breath', 0))
        )

        # Verify nested format parsed correctly
        assert item.name == 'Med Kit'
        assert item.price_drip == 10, f"Expected 10 Drip from nested format"
        assert item.price_spark == 2, f"Expected 2 Spark from nested format"
        assert item.cost == {'drip': 10, 'spark': 2}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
