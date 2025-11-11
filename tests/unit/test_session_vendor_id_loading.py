"""
TDD: Session._initialize_persistent_vendors() Must Pass vendor_id From Config

ROOT CAUSE (from session 9f734816):
- Config specifies vendor_id: "vnd_nexus_shop"
- _initialize_persistent_vendors() creates Vendor() WITHOUT passing vendor_id
- Vendor auto-generates random ID instead
- Players provide vnd_nexus_shop, but actual vendor has random ID like vnd_ab12
- Result: "Vendor vnd_nexus_shop not found"

SOLUTION:
Update session.py line 256 to pass vendor_id from config to Vendor constructor.

TEST FIRST, FIX SECOND (TDD)
"""

import pytest
import tempfile
import json
from pathlib import Path
from scripts.aeonisk.multiagent.session import SelfPlayingSession


class TestSessionVendorIDLoading:
    """
    TDD: Session must pass vendor_id from config to Vendor constructor.
    """

    def test_session_preserves_config_vendor_id(self):
        """
        CRITICAL: Config vendor_id must be preserved when loading persistent_vendors.

        This test will FAIL until we update _initialize_persistent_vendors() to pass vendor_id.
        """
        # Create temporary config with specific vendor_id
        config = {
            "session_name": "test_vendor_id",
            "max_turns": 1,
            "party_size": 1,
            "output_dir": "./multiagent_output",
            "persistent_vendors": [
                {
                    "vendor_id": "vnd_test_12ab",  # CRITICAL: Specific ID from config
                    "name": "Test Vendor",
                    "faction": "Neutral",
                    "vendor_type": "vending_machine",
                    "greeting": "Test greeting",
                    "inventory": [
                        {
                            "item_id": "itm_test_56cd",  # CRITICAL: Specific item ID
                            "name": "Test Item",
                            "description": "Test item description",
                            "price_drip": 5
                        }
                    ]
                }
            ],
            "agents": {
                "dm": {
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.7
                    }
                },
                "players": []
            }
        }

        # Write config to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        try:
            # Create session (triggers _initialize_persistent_vendors)
            session = SelfPlayingSession(config_path)

            # Check that vendor was loaded with correct ID
            vendor = session.shared_state.get_vendor_by_id("vnd_test_12ab")

            # ASSERTION: Vendor must be found with config ID
            assert vendor is not None, \
                f"Vendor with config ID 'vnd_test_12ab' not found! " \
                f"Available vendors: {[v.vendor_id for v in session.shared_state.get_all_vendors()]}"

            # ASSERTION: Vendor ID must match config exactly
            assert vendor.vendor_id == "vnd_test_12ab", \
                f"Expected vendor_id 'vnd_test_12ab' from config, got '{vendor.vendor_id}'"

            # ASSERTION: Vendor name must also match
            assert vendor.name == "Test Vendor"

            # ASSERTION: Item ID must also be preserved
            item = vendor.get_item_by_id("itm_test_56cd")
            assert item is not None, \
                f"Item with config ID 'itm_test_56cd' not found! " \
                f"Available items: {[i.item_id for i in vendor.inventory]}"
            assert item.item_id == "itm_test_56cd"
            assert item.name == "Test Item"

        finally:
            # Cleanup
            Path(config_path).unlink()

    def test_session_auto_generates_vendor_id_when_not_in_config(self):
        """
        Design principle: Vendors without vendor_id in config should auto-generate IDs.
        """
        config = {
            "session_name": "test_auto_vendor_id",
            "max_turns": 1,
            "party_size": 1,
            "output_dir": "./multiagent_output",
            "persistent_vendors": [
                {
                    # NO vendor_id specified - should auto-generate
                    "name": "Auto Vendor",
                    "faction": "Neutral",
                    "vendor_type": "human_trader",
                    "greeting": "Hello",
                    "inventory": []
                }
            ],
            "agents": {
                "dm": {
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.7
                    }
                },
                "players": []
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        try:
            session = SelfPlayingSession(config_path)
            vendors = session.shared_state.get_all_vendors()

            assert len(vendors) == 1
            vendor = vendors[0]

            # Should have auto-generated vendor_id
            assert vendor.vendor_id is not None
            assert vendor.vendor_id.startswith("vnd_")
            assert vendor.name == "Auto Vendor"

        finally:
            Path(config_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
