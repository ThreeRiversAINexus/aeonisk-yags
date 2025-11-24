"""
Test mechanical purchase system with vendor/item IDs.

Tests the deterministic purchase flow:
1. Pre-validation BEFORE DM narration
2. Mechanical transaction execution
3. JSONL logging of all attempts (success and failure)

Uses vending machines for testing (deterministic, no negotiation).
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType, generate_vendor_id, generate_item_id
)


class TestIDGeneration:
    """Test vendor and item ID generation."""

    def test_vendor_id_format(self):
        """Test that vendor IDs are well-formed."""
        vendor_id = generate_vendor_id()
        assert vendor_id.startswith("vnd_")
        assert len(vendor_id) == 8  # vnd_xxxx (4 char suffix)

    def test_item_id_format(self):
        """Test that item IDs are well-formed."""
        item_id = generate_item_id()
        assert item_id.startswith("itm_")
        assert len(item_id) == 8  # itm_xxxx (4 char suffix)

    def test_vendor_ids_unique(self):
        """Test that generated vendor IDs are unique."""
        ids = [generate_vendor_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_item_ids_unique(self):
        """Test that generated item IDs are unique."""
        ids = [generate_item_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique


class TestVendorItemWithIDs:
    """Test VendorItem with item_id and inventory_key fields."""

    def test_vendor_item_has_id(self):
        """Test that VendorItem includes item_id."""
        item = VendorItem(
            item_id="itm_test1",
            name="Echo-Calibrator",
            description="Attunes Raw Seeds",
            inventory_key="echo_calibrator",
            price_spark=8
        )

        assert item.item_id == "itm_test1"
        assert item.inventory_key == "echo_calibrator"

    def test_vendor_item_cost_property(self):
        """Test that cost property includes all currency types."""
        item = VendorItem(
            item_id="itm_test2",
            name="Health Kit",
            description="Restores HP",
            inventory_key="med_kit",
            price_spark=1,
            price_grain=2,
            price_drip=5,
            price_breath=10
        )

        cost = item.cost
        assert cost == {"spark": 1, "grain": 2, "drip": 5, "breath": 10}

    def test_vendor_item_cost_excludes_zero(self):
        """Test that cost property excludes zero amounts."""
        item = VendorItem(
            item_id="itm_test3",
            name="Incense",
            description="Ritual offering",
            inventory_key="incense",
            price_spark=0,
            price_drip=3,
            price_breath=0
        )

        cost = item.cost
        assert cost == {"drip": 3}
        assert "spark" not in cost
        assert "breath" not in cost


class TestVendorWithID:
    """Test Vendor with vendor_id and item lookup."""

    def test_vendor_has_id(self):
        """Test that Vendor includes vendor_id."""
        vendor = Vendor(
            vendor_id="vnd_test1",
            name="Test Vend-O-Mat",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[],
            greeting="Welcome"
        )

        assert vendor.vendor_id == "vnd_test1"

    def test_vendor_get_item_by_id(self):
        """Test that vendor can lookup items by ID."""
        item1 = VendorItem(
            item_id="itm_a1",
            name="Echo-Calibrator",
            description="Attunes Seeds",
            inventory_key="echo_calibrator",
            price_spark=8
        )
        item2 = VendorItem(
            item_id="itm_a2",
            name="Health Kit",
            description="Restores HP",
            inventory_key="med_kit",
            price_drip=5
        )

        vendor = Vendor(
            vendor_id="vnd_test1",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[item1, item2],
            greeting="Welcome"
        )

        found = vendor.get_item_by_id("itm_a1")
        assert found is not None
        assert found.name == "Echo-Calibrator"
        assert found.price_spark == 8

    def test_vendor_get_item_by_id_not_found(self):
        """Test that get_item_by_id returns None for missing items."""
        vendor = Vendor(
            vendor_id="vnd_test1",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[],
            greeting="Welcome"
        )

        found = vendor.get_item_by_id("itm_missing")
        assert found is None


class TestPurchaseValidation:
    """Test pre-purchase validation."""

    def test_validate_purchase_success(self):
        """Test validation for affordable purchase."""
        # This will fail until we implement validate_purchase in mechanics
        pytest.skip("TODO: Implement validate_purchase in mechanics.py")

    def test_validate_purchase_failure_insufficient_funds(self):
        """Test validation for unaffordable purchase."""
        pytest.skip("TODO: Implement validate_purchase in mechanics.py")

    def test_validate_purchase_failure_vendor_not_found(self):
        """Test validation when vendor doesn't exist."""
        pytest.skip("TODO: Implement validate_purchase in mechanics.py")

    def test_validate_purchase_failure_item_not_found(self):
        """Test validation when item not in vendor inventory."""
        pytest.skip("TODO: Implement validate_purchase in mechanics.py")


class TestMechanicalPurchaseExecution:
    """Test that purchases execute mechanically before DM narration."""

    def test_currency_deducted_before_dm(self):
        """Test that currency is deducted mechanically."""
        pytest.skip("TODO: Implement purchase execution in session.py")

    def test_item_added_to_inventory_before_dm(self):
        """Test that item is added to inventory mechanically."""
        pytest.skip("TODO: Implement purchase execution in session.py")

    def test_failed_purchase_no_changes(self):
        """Test that failed purchase doesn't modify state."""
        pytest.skip("TODO: Implement purchase execution in session.py")


class TestPurchaseJSONLLogging:
    """Test JSONL logging of purchase attempts."""

    def test_purchase_success_logged(self):
        """Test that successful purchases are logged."""
        pytest.skip("TODO: Implement JSONL logging for purchases")

    def test_purchase_failure_logged(self):
        """Test that failed purchase attempts are logged."""
        pytest.skip("TODO: Implement JSONL logging for purchases")

    def test_purchase_log_includes_all_fields(self):
        """Test that purchase logs include required fields."""
        pytest.skip("TODO: Implement JSONL logging for purchases")


# Helper to create test vending machine vendor
def create_vending_machine_vendor() -> Vendor:
    """
    Create test vending machine vendor (NOT human trader).

    Vending machines are deterministic - no negotiation, credit, or creative solutions.
    """
    return Vendor(
        vendor_id="vnd_test1",
        name="Test Vend-O-Mat",
        faction="Nexus",
        vendor_type=VendorType.VENDING_MACHINE,
        greeting="Welcome to automated trading terminal.",
        inventory=[
            VendorItem(
                item_id="itm_test1",
                name="Echo-Calibrator",
                description="Attunes Raw Seeds",
                inventory_key="echo_calibrator",
                price_spark=8
            ),
            VendorItem(
                item_id="itm_test2",
                name="Health Kit",
                description="Restores 10 HP",
                inventory_key="med_kit",
                price_drip=5
            )
        ]
    )
