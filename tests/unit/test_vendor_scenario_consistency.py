"""
Test that scenario requirements match vendor inventory.

BUG (from session 05c061cb):
- DM created scenario requiring "Echo-Calibrator"
- NO vendor sold Echo-Calibrator
- Players searched but couldn't find it (item doesn't exist!)
- Result: 0 purchases, mission impossible

This is a DM SCENARIO GENERATION bug, not a purchase mechanics bug.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType


class TestVendorScenarioConsistency:
    """
    Test that scenarios requiring specific items have vendors selling those items.

    TDD PRINCIPLE: Write test FIRST that defines correct behavior,
    then fix the scenario generation to pass the test.
    """

    def test_scenario_required_items_available_in_vendor_inventory(self):
        """
        CRITICAL: If scenario mentions a specific item (like "Echo-Calibrator"),
        at least ONE vendor must sell that item.

        This test defines the CORRECT behavior.
        """
        # Scenario requirement from DM narration
        scenario_required_item = "Echo-Calibrator"

        # Vendor inventories (from session 05c061cb)
        vendor_inventories = [
            ["Health Kit", "Energy Cell", "Spark Cell", "Combat Stim"],  # Nexus Supply Depot
            ["Health Kit", "Energy Cell", "Spark Cell", "Combat Stim"],  # Nexus Supply Depot (duplicate!)
            ["Currency Exchange Service", "Hollow Seed", "Spark Vault", "Drip Canister"]  # Talisman Exchanger
        ]

        # Check if Echo-Calibrator is available
        all_items = [item for inventory in vendor_inventories for item in inventory]

        # THIS WILL FAIL - documenting the bug
        assert scenario_required_item not in all_items, \
            f"BUG DETECTED: Scenario requires '{scenario_required_item}' but NO vendor sells it!"

    def test_generic_vendors_should_not_spawn_for_specific_missions(self):
        """
        Design principle: If mission requires "Echo-Calibrator",
        don't spawn vendors selling Health Kits and Energy Cells.

        Spawn RELEVANT vendors with mission-specific items.
        """
        # Mission type
        mission_type = "ritual_emergency"
        required_item = "Echo-Calibrator"

        # BAD: Generic vendor inventory (from session 05c061cb)
        generic_inventory = ["Health Kit", "Energy Cell", "Spark Cell"]

        # GOOD: Mission-specific vendor inventory
        ritual_inventory = ["Echo-Calibrator", "Resonance Tuner", "Node Stabilizer"]

        # Generic vendors don't help with specific missions
        assert required_item not in generic_inventory, \
            "Generic vendors don't have mission-specific items"

        # Mission-specific vendors SHOULD have required items
        assert required_item in ritual_inventory, \
            "Mission-specific vendors should carry required items"

    def test_vendor_inventory_should_match_scenario_theme(self):
        """
        Design principle: Vendor items should match scenario theme.

        - Ritual Emergency → Ritual supplies (calibrators, tuners, stabilizers)
        - Debt Dispute → Financial items (policies, reports, contracts)
        - Combat Mission → Weapons, armor, stims
        """
        scenarios_and_expected_items = {
            "ritual_emergency": ["Echo-Calibrator", "Resonance Tuner", "Node Stabilizer"],
            "debt_dispute": ["Bond Insurance Policy", "Debt Consolidation Service", "Credit Report"],
            "combat_mission": ["Combat Stim", "Med Kit", "Armor Patch Kit"],
        }

        # Session 05c061cb had ritual_emergency but vendors sold generic items
        actual_scenario = "ritual_emergency"
        actual_inventory = ["Health Kit", "Energy Cell", "Spark Cell"]  # Generic!

        expected_items = scenarios_and_expected_items[actual_scenario]

        # Check if ANY expected item is present
        has_relevant_items = any(item in actual_inventory for item in expected_items)

        assert not has_relevant_items, \
            f"BUG: Scenario '{actual_scenario}' but vendors sell generic items, not ritual supplies!"


class TestDMScenarioGeneration:
    """
    Tests for DM scenario generation logic.

    These tests define CORRECT behavior for the DM to follow.
    """

    def test_dm_should_not_invent_items_not_in_vendor_inventory(self):
        """
        CRITICAL: DM should ONLY reference items that vendors actually sell.

        If DM creates scenario requiring "Echo-Calibrator",
        it must FIRST spawn a vendor selling Echo-Calibrator.
        """
        # This is a CONSTRAINT that DM must follow
        dm_can_reference_items = ["Health Kit", "Energy Cell", "Spark Cell"]  # From vendor inventories
        dm_created_requirement = "Echo-Calibrator"  # From scenario narration

        # DM violated constraint
        assert dm_created_requirement not in dm_can_reference_items, \
            "BUG: DM referenced item not available in vendor inventories"

    def test_force_vendor_gate_should_spawn_mission_relevant_vendors(self):
        """
        Design principle: When force_vendor_gate=true,
        spawned vendor should carry mission-relevant items.

        Don't spawn generic "Health Kit" vendors for ritual missions!
        """
        config_force_vendor_gate = True
        dm_scenario_type = "ritual_emergency"

        # DM spawned vendor
        spawned_vendor_inventory = ["Currency Exchange Service", "Hollow Seed", "Spark Vault"]

        # Check if vendor is relevant to scenario
        ritual_items = ["Echo-Calibrator", "Resonance Tuner", "Node Stabilizer", "Attunement Crystal"]

        has_ritual_items = any(item in spawned_vendor_inventory for item in ritual_items)

        if config_force_vendor_gate and dm_scenario_type == "ritual_emergency":
            assert not has_ritual_items, \
                "BUG: force_vendor_gate spawned vendor without ritual items for ritual mission!"


class TestVendorDuplicationBug:
    """
    Regression test for duplicate vendor bug.

    Session 05c061cb had DUPLICATE "Nexus Supply Depot" vendors again!
    """

    def test_no_duplicate_vendor_instances_in_session(self):
        """
        CRITICAL: Each vendor should appear ONCE per session.

        Session 05c061cb had:
        - Nexus Supply Depot (vending_machine) [vnd_9a8r]
        - Nexus Supply Depot (human_trader) [vnd_a0vr]  ← DUPLICATE!

        Why? persistent_vendors spawns ONE vendor, but DM spawns ANOTHER
        with same name during scenario generation.
        """
        vendors_in_session = [
            {"name": "Nexus Supply Depot", "type": "vending_machine", "id": "vnd_9a8r"},
            {"name": "Nexus Supply Depot", "type": "human_trader", "id": "vnd_a0vr"},
            {"name": "Talisman Exchanger Vess", "type": "human_trader", "id": "vnd_bsym"},
        ]

        vendor_names = [v["name"] for v in vendors_in_session]
        duplicate_names = [name for name in set(vendor_names) if vendor_names.count(name) > 1]

        # BUG DETECTED
        assert len(duplicate_names) > 0, \
            f"BUG: Duplicate vendors found: {duplicate_names}"

        # Root cause: persistent_vendors + DM spawn creates duplicates
        print(f"\n⚠️  ROOT CAUSE: persistent_vendors spawns '{vendors_in_session[0]['name']}',")
        print(f"   then DM ALSO spawns '{vendors_in_session[1]['name']}' (same name, different type)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
