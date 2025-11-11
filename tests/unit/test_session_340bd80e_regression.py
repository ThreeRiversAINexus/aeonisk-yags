"""
Regression test for session 340bd80e purchase bug.

BUG: DM narrated successful purchase for 2 Spark when Mira had 0 Spark.
NEW SYSTEM: Pre-validation catches this BEFORE DM narration.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType
)


class TestSession340bd80ePurchaseBug:
    """
    Regression test for the exact scenario from session 340bd80e.

    Session facts:
    - Mira Seln: 0 Spark, 4 Drip, 1 Grain, 20 Breath
    - Vendor: Scribe Orven Tylesh
    - Item: Echo-Calibrator (Field-Grade) - 2 Spark (discounted from 8)
    - DM said: success=true, currency_spent={spark: 2}
    - Reality: Mira had 0 Spark → mechanics ERROR
    """

    def test_mira_starting_currency(self):
        """Document Mira's actual starting currency from session."""
        mira_purse = EnergyPurse(
            spark=0,  # ← THE PROBLEM
            grain=1,
            drip=4,
            breath=20
        )

        assert mira_purse.spark == 0
        assert mira_purse.drip == 4

    def test_vendor_and_item_setup(self):
        """Document the vendor and item from session."""
        vendor = Vendor(
            vendor_id="vnd_test_scribe",
            name="Scribe Orven Tylesh",
            faction="Neutral",
            vendor_type=VendorType.HUMAN_TRADER,
            greeting="Seeking clarity? I trade in resonance and remembrance.",
            inventory=[
                VendorItem(
                    item_id="itm_echo_cal",
                    name="Echo-Calibrator (Field-Grade)",
                    description="Attunes Raw Seeds, field-grade quality",
                    inventory_key="echo_calibrator",
                    price_spark=2  # Discounted price after negotiation
                )
            ]
        )

        item = vendor.get_item_by_id("itm_echo_cal")
        assert item is not None
        assert item.name == "Echo-Calibrator (Field-Grade)"
        assert item.price_spark == 2

    def test_old_system_dm_narrates_impossible_purchase(self):
        """
        OLD SYSTEM: DM narrated success without checking player currency.

        This documents what ACTUALLY HAPPENED in session 340bd80e.
        """
        # Setup
        mira_purse = EnergyPurse(spark=0, drip=4, grain=1, breath=20)

        # DM narrated this (from effects.purchase in JSONL):
        dm_narration_says = {
            "success": True,  # ← DM said purchase succeeded
            "currency_spent": {"spark": 2},  # ← DM said 2 Spark spent
            "items_purchased": ["Echo-Calibrator (Field-Grade)"]
        }

        # But mechanics code tried to deduct:
        needed_spark = 2
        has_spark = mira_purse.spark

        # This is why it failed:
        assert has_spark < needed_spark  # 0 < 2
        assert dm_narration_says["success"] == True  # But DM said success!

        # Result: ERROR in logs, no inventory update
        # This is the bug we're fixing.

    def test_new_system_pre_validation_catches_shortage(self):
        """
        NEW SYSTEM: Pre-validation catches shortage BEFORE DM narrates.

        This will pass once we implement validate_purchase().
        """
        pytest.skip("TODO: Implement validate_purchase() to make this pass")

        # Setup
        mira_purse = EnergyPurse(spark=0, drip=4, grain=1, breath=20)
        vendor = Vendor(
            vendor_id="vnd_test",
            name="Scribe Orven Tylesh",
            faction="Neutral",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[
                VendorItem(
                    item_id="itm_echo",
                    name="Echo-Calibrator",
                    inventory_key="echo_calibrator",
                    price_spark=2
                )
            ]
        )

        # NEW SYSTEM: Pre-validate BEFORE DM
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        mechanics = MechanicsEngine(shared_state=None)

        validation = mechanics.validate_purchase(
            character=MockCharacter(energy_purse=mira_purse),
            vendor_id="vnd_test",
            item_id="itm_echo"
        )

        # Should catch the shortage
        assert validation.can_afford == False
        assert validation.shortage == {"spark": 2}
        assert "need 2 Spark, have 0 Spark" in validation.failure_reason

        # NOW DM gets constraint:
        # "MUST narrate insufficient funds. Player needs 2 Spark but has 0."
        # DM can narrate failure, suggest pooling resources, etc.
        # But purchase does NOT execute mechanically.

    def test_new_system_with_pooled_resources(self):
        """
        NEW SYSTEM: If Kress pools 1 Spark, validation should succeed.

        This is what SHOULD have happened in session 340bd80e.
        """
        pytest.skip("TODO: Implement validate_purchase() + resource pooling")

        # Mira starts with 0 Spark
        mira_purse = EnergyPurse(spark=0, drip=4)

        # Kress pools 1 Spark with Mira (now Mira has 1)
        # (This would be a separate "transfer currency" action)
        mira_purse.spark = 1

        # Vendor offers discounted 2 Spark price
        vendor = Vendor(
            vendor_id="vnd_test",
            name="Scribe Orven Tylesh",
            faction="Neutral",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[
                VendorItem(
                    item_id="itm_echo",
                    name="Echo-Calibrator",
                    inventory_key="echo_calibrator",
                    price_spark=2
                )
            ]
        )

        # Pre-validate
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        mechanics = MechanicsEngine(shared_state=None)

        validation = mechanics.validate_purchase(
            character=MockCharacter(energy_purse=mira_purse),
            vendor_id="vnd_test",
            item_id="itm_echo"
        )

        # STILL short 1 Spark
        assert validation.can_afford == False
        assert validation.shortage == {"spark": 1}

        # If Kress pools ANOTHER Spark:
        mira_purse.spark = 2

        validation2 = mechanics.validate_purchase(
            character=MockCharacter(energy_purse=mira_purse),
            vendor_id="vnd_test",
            item_id="itm_echo"
        )

        # NOW it works!
        assert validation2.can_afford == True
        assert validation2.shortage is None

    def test_new_system_execution_flow(self):
        """
        NEW SYSTEM: Full flow with mechanical execution.

        Tests that transaction executes BEFORE DM narrates.
        """
        pytest.skip("TODO: Implement full purchase execution flow")

        # Setup: Mira has 2 Spark
        mira_purse = EnergyPurse(spark=2, drip=4)
        mira_inventory = {"echo_calibrator": 0}

        vendor = Vendor(
            vendor_id="vnd_test",
            name="Scribe",
            faction="Neutral",
            vendor_type=VendorType.VENDING_MACHINE,  # Use machine for deterministic test
            inventory=[
                VendorItem(
                    item_id="itm_echo",
                    name="Echo-Calibrator",
                    inventory_key="echo_calibrator",
                    price_spark=2
                )
            ]
        )

        # 1. Pre-validate
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        mechanics = MechanicsEngine(shared_state=None)

        validation = mechanics.validate_purchase(
            character=MockCharacter(energy_purse=mira_purse, inventory=mira_inventory),
            vendor_id="vnd_test",
            item_id="itm_echo"
        )

        assert validation.can_afford == True

        # 2. Execute transaction BEFORE DM
        mira_purse.spend_currency("spark", validation.cost["spark"])
        mira_inventory[validation.inventory_key] += 1

        # 3. Verify state changed
        assert mira_purse.spark == 0  # 2 - 2
        assert mira_inventory["echo_calibrator"] == 1

        # 4. NOW DM narrates with constraint
        # "Purchase already completed. Narrate the social/atmospheric aspects."
        # DM cannot change the mechanics - it already happened.


class MockCharacter:
    """Mock character for testing."""
    def __init__(self, energy_purse, inventory=None):
        self.energy_purse = energy_purse
        self.inventory = inventory or {}
        self.name = "Test Character"
