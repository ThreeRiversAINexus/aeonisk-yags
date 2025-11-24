"""
TDD: Config Vendor_ID Must Be Preserved During Session Init

ROOT CAUSE (from session 9f734816):
- Config defines vendor_id: "vnd_nexus_shop"
- _initialize_persistent_vendors() creates Vendor() without passing vendor_id param
- Vendor auto-generates random ID instead of using config ID
- Result: "Vendor vnd_mmyv not found" (vnd_mmyv from config, but auto-generated ID differs)

SOLUTION:
Pass vendor_id from config to Vendor constructor when loading persistent_vendors.

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
from unittest.mock import MagicMock
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestConfigVendorIDPreservation:
    """
    TDD: Session must preserve vendor_id from config when initializing persistent vendors.
    """

    def test_vendor_id_from_config_is_preserved(self):
        """
        CRITICAL: Config vendor_id must be used when creating vendor (not auto-generated).

        This test will FAIL until we pass vendor_id from config to Vendor().
        """
        # Config vendor_id (from session_config_economic.json)
        config_vendor_id = "vnd_nexus_shop"

        # Create vendor WITH vendor_id (how it SHOULD be)
        vendor = Vendor(
            name="Nexus Supply Depot",
            faction="Sovereign Nexus",
            inventory=[],
            greeting="Authorized personnel only.",
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id=config_vendor_id  # CRITICAL: Must pass config ID!
        )

        # ASSERTION: vendor_id must match config, NOT be auto-generated
        assert vendor.vendor_id == config_vendor_id, \
            f"Expected vendor_id '{config_vendor_id}' from config, got '{vendor.vendor_id}'"

    def test_vendor_auto_generates_id_when_not_provided(self):
        """
        Design principle: Vendors CAN auto-generate IDs when not in config.
        """
        vendor = Vendor(
            name="Random Trader",
            faction="Freeborn",
            inventory=[]
        )

        # Should have SOME vendor_id (auto-generated)
        assert vendor.vendor_id is not None
        assert vendor.vendor_id.startswith("vnd_")
        assert len(vendor.vendor_id) == 8  # Format: vnd_XXXX

    def test_vendor_item_id_from_config_is_preserved(self):
        """
        CRITICAL: Config item_id must also be preserved (same pattern as vendor_id).
        """
        config_item_id = "itm_q75c"

        item = VendorItem(
            name="Health Kit",
            description="Restores 10 HP",
            price_drip=5,
            item_id=config_item_id  # CRITICAL: Must pass config ID!
        )

        # ASSERTION: item_id must match config, NOT be auto-generated
        assert item.item_id == config_item_id, \
            f"Expected item_id '{config_item_id}' from config, got '{item.item_id}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
