"""
TDD: Prevent Duplicate Vendor Loading

BUG (from session dcbc3d6a):
- session.py:_initialize_persistent_vendors() adds vendor to SharedState
- dm.py:_load_persistent_vendors() adds SAME vendor AGAIN
- Result: SharedState has 2 copies of "Field Medic Jara" with different IDs

TEST FIRST, FIX SECOND
"""

import pytest
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestDuplicateVendorPrevention:
    """TDD: Prevent duplicate vendors in SharedState."""

    def test_add_vendor_prevents_duplicates_by_name(self):
        """
        CRITICAL: add_vendor() should not add vendor if same name already exists.

        This prevents session.py + dm.py from creating duplicates.
        """
        shared_state = SharedState()

        # Add vendor once
        vendor1 = Vendor(
            name="Field Medic Jara",
            faction="Independent",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )
        shared_state.add_vendor(vendor1)
        assert len(shared_state.current_vendors) == 1

        # Try to add same vendor again (by name)
        vendor2 = Vendor(
            name="Field Medic Jara",  # SAME NAME
            faction="Independent",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )
        shared_state.add_vendor(vendor2)

        # ASSERTION: Should still have only 1 vendor
        assert len(shared_state.current_vendors) == 1, \
            "add_vendor() should prevent duplicate vendors by name"
        assert shared_state.current_vendors[0].name == "Field Medic Jara"

    def test_add_vendor_allows_different_vendors(self):
        """
        Design principle: Different vendors (by name) should be allowed.
        """
        shared_state = SharedState()

        vendor1 = Vendor(
            name="Field Medic Jara",
            faction="Independent",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )
        vendor2 = Vendor(
            name="Scribe Orven",  # DIFFERENT NAME
            faction="Nexus",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )

        shared_state.add_vendor(vendor1)
        shared_state.add_vendor(vendor2)

        # Should have both vendors
        assert len(shared_state.current_vendors) == 2
        names = [v.name for v in shared_state.current_vendors]
        assert "Field Medic Jara" in names
        assert "Scribe Orven" in names

    def test_get_all_vendors_returns_unique_vendors(self):
        """
        Verify get_all_vendors() returns deduplicated list.
        """
        shared_state = SharedState()

        vendor = Vendor(
            name="Field Medic Jara",
            faction="Independent",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )

        # Add twice (simulating session.py + dm.py)
        shared_state.add_vendor(vendor)
        shared_state.add_vendor(vendor)

        vendors = shared_state.get_all_vendors()
        assert len(vendors) == 1, "get_all_vendors() should return unique vendors"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
