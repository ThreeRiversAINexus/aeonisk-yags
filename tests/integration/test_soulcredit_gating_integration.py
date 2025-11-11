"""
SOULCREDIT GATING INTEGRATION TESTS

Tests the COMPLETE soulcredit vendor access flow through mechanics validation:
1. Characters with varying SC levels attempt purchases
2. Pre-validation runs with SC checks BEFORE currency checks
3. VENDING_MACHINE blocks low SC, allows neutral/high SC
4. SUPPLY_DRONE and EMERGENCY_CACHE allow all SC levels
5. Proper error messages with actual SC values

These tests verify the full integration of SC gating logic without requiring
full session/LLM infrastructure.
"""

import pytest
from unittest.mock import Mock
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.energy_economy import (
    Vendor, VendorItem, VendorType, EnergyPurse
)


class TestSoulcreditGatingIntegration:
    """
    Integration tests for soulcredit vendor gating.

    Tests the REAL code path: SharedState → MechanicsEngine → validate_purchase()
    """

    @pytest.fixture
    def shared_state_with_vendors(self):
        """Create SharedState with all vendor types."""
        shared_state = SharedState()

        # Vending Machine (SC ≥ -2 required)
        vm_vendor = Vendor(
            name="Nexus Medical VM-47",
            faction="Nexus",
            inventory=[
                VendorItem(
                    name="Med Kit",
                    description="Restores 15 HP",
                    item_id="itm_medkit",
                    price_drip=5
                )
            ],
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id="vnd_vm01"
        )

        # Supply Drone (no SC restrictions)
        drone_vendor = Vendor(
            name="Supply Drone SD-812",
            faction="Independent",
            inventory=[
                VendorItem(
                    name="Rations",
                    description="Emergency food",
                    item_id="itm_rations",
                    price_drip=3
                )
            ],
            vendor_type=VendorType.SUPPLY_DRONE,
            vendor_id="vnd_drone01"
        )

        # Emergency Cache (no SC restrictions)
        cache_vendor = Vendor(
            name="Emergency Cache EC-03",
            faction="Independent",
            inventory=[
                VendorItem(
                    name="First Aid",
                    description="Emergency supplies",
                    item_id="itm_firstaid",
                    price_drip=2
                )
            ],
            vendor_type=VendorType.EMERGENCY_CACHE,
            vendor_id="vnd_cache01"
        )

        shared_state.add_vendor(vm_vendor)
        shared_state.add_vendor(drone_vendor)
        shared_state.add_vendor(cache_vendor)

        return shared_state

    @pytest.fixture
    def mechanics(self, shared_state_with_vendors):
        """Create mechanics engine with shared state."""
        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state_with_vendors
        return mechanics

    def create_character(self, name: str, soulcredit: int, drip: int = 100):
        """Helper to create character with specified SC and currency."""
        char = Mock()
        char.name = name
        char.soulcredit = soulcredit
        char.energy_purse = EnergyPurse(
            breath=50,
            drip=drip,
            grain=5,
            spark=3
        )
        char.inventory = {}
        return char

    # ============================================================================
    # VENDING_MACHINE Integration Tests
    # ============================================================================

    def test_vending_machine_blocks_low_sc_character(self, mechanics):
        """
        INTEGRATION: Low SC character (SC -5) cannot purchase from vending machine.

        Verifies:
        - SharedState vendor lookup works
        - SC check happens BEFORE currency check
        - sc_blocked flag is set
        - Error message includes actual SC value
        """
        character = self.create_character("Outcast Rivan", soulcredit=-5, drip=100)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # CRITICAL ASSERTIONS
        assert validation.is_valid is False, \
            "Low SC should be blocked by vending machine"
        assert validation.sc_blocked is True, \
            "sc_blocked flag should be set for SC failures"
        assert "Soulcredit too low" in validation.failure_reason, \
            f"Expected SC error message, got: {validation.failure_reason}"
        assert "-5" in validation.failure_reason, \
            "Error should show actual SC value"

        # Should not check affordability when SC blocked
        assert validation.can_afford is False

    def test_vending_machine_allows_neutral_sc_character(self, mechanics):
        """
        INTEGRATION: Neutral SC character (SC 0) CAN purchase from vending machine.

        SC 0 meets the ≥-2 threshold.
        """
        character = self.create_character("Ash Vex", soulcredit=0, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # CRITICAL ASSERTIONS
        assert validation.is_valid is True, \
            f"Neutral SC (0) should pass vending machine threshold (≥-2). Error: {validation.failure_reason}"
        assert validation.sc_blocked is False
        assert validation.can_afford is True
        assert validation.item_name == "Med Kit"
        assert validation.cost == {'drip': 5}

    def test_vending_machine_allows_high_sc_character(self, mechanics):
        """
        INTEGRATION: High SC character (SC +6) easily passes vending machine threshold.
        """
        character = self.create_character("Agent Kress", soulcredit=6, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # CRITICAL ASSERTIONS
        assert validation.is_valid is True, \
            f"High SC should pass vending machine. Error: {validation.failure_reason}"
        assert validation.sc_blocked is False
        assert validation.can_afford is True

    def test_vending_machine_boundary_sc_minus_2(self, mechanics):
        """
        INTEGRATION: SC -2 is the EXACT threshold - should PASS.
        """
        character = self.create_character("Boundary Test", soulcredit=-2, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        assert validation.is_valid is True, \
            "SC -2 should pass (threshold is ≥-2)"
        assert validation.sc_blocked is False

    def test_vending_machine_boundary_sc_minus_3(self, mechanics):
        """
        INTEGRATION: SC -3 is below threshold - should FAIL.
        """
        character = self.create_character("Below Threshold", soulcredit=-3, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        assert validation.is_valid is False, \
            "SC -3 should fail (below ≥-2 threshold)"
        assert validation.sc_blocked is True

    # ============================================================================
    # SUPPLY_DRONE Integration Tests (Neutral Vendor)
    # ============================================================================

    def test_supply_drone_allows_low_sc_character(self, mechanics):
        """
        INTEGRATION: Supply drones are NEUTRAL - allow even very low SC (-5).
        """
        character = self.create_character("Outcast Rivan", soulcredit=-5, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )

        # CRITICAL ASSERTIONS
        assert validation.is_valid is True, \
            f"Supply drones should allow low SC. Error: {validation.failure_reason}"
        assert validation.sc_blocked is False, \
            "Supply drones should have no SC restrictions"
        assert validation.can_afford is True
        assert validation.item_name == "Rations"

    def test_supply_drone_allows_high_sc_character(self, mechanics):
        """
        INTEGRATION: Supply drones allow high SC (neutral vendor).
        """
        character = self.create_character("Agent Kress", soulcredit=6, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )

        assert validation.is_valid is True
        assert validation.sc_blocked is False

    # ============================================================================
    # EMERGENCY_CACHE Integration Tests (Crisis Override)
    # ============================================================================

    def test_emergency_cache_allows_low_sc_character(self, mechanics):
        """
        INTEGRATION: Emergency caches ignore SC restrictions (crisis override).
        """
        character = self.create_character("Desperate Survivor", soulcredit=-10, drip=20)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_cache01",
            item_id="itm_firstaid"
        )

        # CRITICAL ASSERTIONS
        assert validation.is_valid is True, \
            f"Emergency caches should allow any SC (crisis override). Error: {validation.failure_reason}"
        assert validation.sc_blocked is False
        assert validation.item_name == "First Aid"

    # ============================================================================
    # Priority Tests: SC Check Before Currency Check
    # ============================================================================

    def test_sc_failure_reported_before_currency_failure(self, mechanics):
        """
        INTEGRATION: When BOTH SC and currency fail, SC error takes priority.

        This ensures clear error messages: "access denied" vs "can't afford".
        """
        # Character with low SC AND no money
        character = self.create_character("Broke and Low SC", soulcredit=-5, drip=0)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # CRITICAL ASSERTION: Should get SC error, not currency error
        assert validation.sc_blocked is True, \
            "SC check should happen first"
        assert "Soulcredit" in validation.failure_reason, \
            f"Expected SC error, got: {validation.failure_reason}"
        assert validation.is_valid is False

    def test_currency_failure_when_sc_passes(self, mechanics):
        """
        INTEGRATION: When SC passes but currency fails, get currency error.
        """
        # Character with good SC but no money
        character = self.create_character("Good SC, No Money", soulcredit=5, drip=0)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Should get currency error (SC check passed)
        assert validation.sc_blocked is False, \
            "SC should pass"
        assert validation.is_valid is False, \
            "Should fail on currency"
        assert "Insufficient currency" in validation.failure_reason, \
            f"Expected currency error, got: {validation.failure_reason}"
        assert validation.shortage == {'drip': 5}

    # ============================================================================
    # Full Purchase Flow Integration
    # ============================================================================

    def test_complete_purchase_flow_with_sc_gating(self, mechanics, shared_state_with_vendors):
        """
        INTEGRATION: Complete purchase flow including SC check.

        Tests the ACTUAL flow:
        1. Lookup vendor by ID from SharedState
        2. SC gating check
        3. Currency affordability check
        4. Execute transaction (deduct currency, add item)
        """
        character = self.create_character("Successful Buyer", soulcredit=2, drip=10)
        initial_drip = character.energy_purse.drip

        # Step 1 & 2 & 3: Validate (includes SC check)
        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Verify validation succeeded
        assert validation.is_valid is True
        assert validation.sc_blocked is False
        assert validation.can_afford is True
        assert validation.cost == {'drip': 5}

        # Step 4: Execute transaction
        for currency_type, amount in validation.cost.items():
            character.energy_purse.spend_currency(currency_type, amount)

        inventory_key = validation.inventory_key
        character.inventory[inventory_key] = character.inventory.get(inventory_key, 0) + 1

        # FINAL ASSERTIONS
        assert character.energy_purse.drip == initial_drip - 5, \
            "Currency should be deducted"
        assert character.inventory[inventory_key] == 1, \
            "Item should be added to inventory"

    def test_vendor_type_determines_sc_behavior(self, mechanics, shared_state_with_vendors):
        """
        INTEGRATION: Verify different vendor types have correct SC behaviors.

        Same character, different vendor types → different access results.
        """
        # Low SC character
        character = self.create_character("Low SC Test", soulcredit=-5, drip=20)

        # Test 1: VENDING_MACHINE blocks low SC
        vm_validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )
        assert vm_validation.sc_blocked is True, \
            "Vending machine should block low SC"

        # Test 2: SUPPLY_DRONE allows low SC
        drone_validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )
        assert drone_validation.is_valid is True, \
            "Supply drone should allow low SC"
        assert drone_validation.sc_blocked is False

        # Test 3: EMERGENCY_CACHE allows low SC
        cache_validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_cache01",
            item_id="itm_firstaid"
        )
        assert cache_validation.is_valid is True, \
            "Emergency cache should allow low SC"
        assert cache_validation.sc_blocked is False


class TestSoulcreditGatingEdgeCases:
    """Edge cases for SC gating integration."""

    def test_character_with_no_sc_attribute_defaults_to_zero(self):
        """
        INTEGRATION: Characters without explicit soulcredit should default to 0.

        Legacy characters or new characters might not have SC set.
        """
        shared_state = SharedState()

        vendor = Vendor(
            name="Test Vendor",
            faction="Nexus",
            inventory=[VendorItem(
                name="Item",
                description="Test",
                item_id="itm_test",
                price_drip=2
            )],
            vendor_type=VendorType.VENDING_MACHINE,
            vendor_id="vnd_test"
        )
        shared_state.add_vendor(vendor)

        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state

        # Character WITHOUT soulcredit attribute
        character = Mock()
        character.name = "Legacy Character"
        # Explicitly delete soulcredit attribute if it exists
        if hasattr(character, 'soulcredit'):
            delattr(character, 'soulcredit')

        character.energy_purse = EnergyPurse(drip=10)
        character.inventory = {}

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_test",
            item_id="itm_test"
        )

        # Should default to SC 0, which passes vending machine threshold (≥-2)
        assert validation.is_valid is True, \
            f"Missing SC should default to 0. Error: {validation.failure_reason}"
        assert validation.sc_blocked is False

    def test_vendor_not_found_returns_proper_error(self):
        """
        INTEGRATION: Invalid vendor_id should return clear error.
        """
        shared_state = SharedState()
        mechanics = MechanicsEngine()
        mechanics.shared_state = shared_state

        character = Mock()
        character.name = "Test"
        character.soulcredit = 5
        character.energy_purse = EnergyPurse(drip=100)

        validation = mechanics.validate_purchase(
            character_state=character,
            vendor_id="vnd_nonexistent",
            item_id="itm_whatever"
        )

        assert validation.is_valid is False
        assert "not found" in validation.failure_reason.lower()
