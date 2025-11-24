"""
Test-Driven Development: Soulcredit Vendor Gating

Tests for vendor-specific soulcredit access rules:
- VENDING_MACHINE: SC ≥ -2 required (Nexus automated vendors)
- SUPPLY_DRONE: No SC requirements (neutral vendors)
- EMERGENCY_CACHE: No SC requirements (crisis override)
- Tempest (future): Inverted SC (blocks SC ≥ 5, prefers SC < -2)
- HUMAN_TRADER (Phase 2): SC-based pricing modifiers (not in this test)

Design Reference: .claude/archive/PURCHASE_VENDING_SYSTEM_DESIGN.md
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import (
    Vendor, VendorItem, VendorType, EnergyPurse
)
from scripts.aeonisk.multiagent.shared_state import SharedState


class TestSoulcreditVendorGating:
    """
    Test soulcredit-based vendor access control.

    Tests are written FIRST to define correct behavior, then implementation follows.
    """

    @pytest.fixture
    def shared_state(self):
        """Create shared state for vendor tracking."""
        return SharedState()

    @pytest.fixture
    def mechanics(self, shared_state):
        """Create mechanics engine with shared state."""
        engine = MechanicsEngine(jsonl_logger=None)
        engine.shared_state = shared_state
        return engine

    @pytest.fixture
    def character_low_sc(self):
        """Create character with very low soulcredit (SC -5)."""
        char = CharacterState(
            name="Outcast Rivan",
            faction="Freeborn",
            attributes={
                "strength": 2, "agility": 3, "endurance": 3,
                "perception": 4, "intelligence": 4, "empathy": 3,
                "willpower": 3, "charisma": 2, "size": 10
            },
            skills={"charm": 2},
            void_score=0,
            soulcredit=-5,  # Very low SC
            bonds=[],
            goals=["Survive"],
            pronouns="they/them"
        )

        # Initialize energy_purse with sufficient currency
        char.energy_purse = EnergyPurse()
        char.energy_purse.drip = 100

        return char

    @pytest.fixture
    def character_high_sc(self):
        """Create character with high soulcredit (SC 6)."""
        char = CharacterState(
            name="Agent Kress",
            faction="Nexus",
            attributes={
                "strength": 2, "agility": 3, "endurance": 3,
                "perception": 4, "intelligence": 4, "empathy": 3,
                "willpower": 3, "charisma": 5, "size": 10
            },
            skills={"charm": 5},
            void_score=0,
            soulcredit=6,  # High SC
            bonds=[],
            goals=["Maintain order"],
            pronouns="they/them"
        )

        # Initialize energy_purse with sufficient currency
        char.energy_purse = EnergyPurse()
        char.energy_purse.drip = 100

        return char

    @pytest.fixture
    def character_neutral_sc(self):
        """Create character with neutral soulcredit (SC 0)."""
        char = CharacterState(
            name="Ash Vex",
            faction="Independent",
            attributes={
                "strength": 2, "agility": 3, "endurance": 3,
                "perception": 4, "intelligence": 4, "empathy": 3,
                "willpower": 3, "charisma": 3, "size": 10
            },
            skills={"charm": 3},
            void_score=0,
            soulcredit=0,  # Neutral SC
            bonds=[],
            goals=["Stay independent"],
            pronouns="they/them"
        )

        # Initialize energy_purse with sufficient currency
        char.energy_purse = EnergyPurse()
        char.energy_purse.drip = 100

        return char

    @pytest.fixture
    def vending_machine_vendor(self, shared_state):
        """Create automated Nexus vending machine and add to shared state."""
        medkit = VendorItem(
            name="Med Kit",
            description="Restores 15 HP",
            item_id="itm_medkit",
            price_drip=5
        )
        vendor = Vendor(
            vendor_id="vnd_vm01",
            name="Nexus Medical Station VM-47",
            faction="Nexus",
            vendor_type=VendorType.VENDING_MACHINE,
            inventory=[medkit],
            greeting="NEXUS AUTHORIZED ACCESS ONLY. SOULCREDIT VERIFICATION REQUIRED."
        )
        shared_state.add_vendor(vendor)
        return vendor

    @pytest.fixture
    def supply_drone_vendor(self, shared_state):
        """Create neutral supply drone and add to shared state."""
        rations = VendorItem(
            name="Rations",
            description="Emergency food supply",
            item_id="itm_rations",
            price_drip=3
        )
        vendor = Vendor(
            vendor_id="vnd_drone01",
            name="Supply Drone SD-812",
            faction="Independent",
            vendor_type=VendorType.SUPPLY_DRONE,
            inventory=[rations],
            greeting="Neutral zone delivery. All factions accepted."
        )
        shared_state.add_vendor(vendor)
        return vendor

    @pytest.fixture
    def emergency_cache_vendor(self, shared_state):
        """Create emergency crisis cache and add to shared state."""
        first_aid = VendorItem(
            name="First Aid Kit",
            description="Emergency medical supplies",
            item_id="itm_firstaid",
            price_drip=2
        )
        vendor = Vendor(
            vendor_id="vnd_cache01",
            name="Emergency Cache EC-03",
            faction="Independent",
            vendor_type=VendorType.EMERGENCY_CACHE,
            inventory=[first_aid],
            greeting="EMERGENCY CRISIS OVERRIDE. ACCESS GRANTED TO ALL."
        )
        shared_state.add_vendor(vendor)
        return vendor

    # ============================================================================
    # VENDING_MACHINE Tests (SC ≥ -2 required)
    # ============================================================================

    def test_vending_machine_blocks_low_sc(self, mechanics, character_low_sc, vending_machine_vendor):
        """
        VENDING_MACHINE vendors require SC ≥ -2.

        Low SC characters (SC -5) should be BLOCKED with sc_blocked=True.
        """
        validation = mechanics.validate_purchase(
            character_state=character_low_sc,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Assertions
        assert validation.is_valid is False, "Low SC should be blocked by vending machine"
        assert validation.sc_blocked is True, "Should set sc_blocked flag"
        assert "Soulcredit too low" in validation.failure_reason
        assert "-5" in validation.failure_reason  # Should show actual SC

    def test_vending_machine_allows_neutral_sc(self, mechanics, character_neutral_sc, vending_machine_vendor):
        """
        VENDING_MACHINE vendors allow SC 0 (meets threshold of SC ≥ -2).
        """
        validation = mechanics.validate_purchase(
            character_state=character_neutral_sc,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Assertions
        assert validation.is_valid is True, "Neutral SC should pass vending machine threshold"
        assert validation.sc_blocked is False

    def test_vending_machine_allows_high_sc(self, mechanics, character_high_sc, vending_machine_vendor):
        """
        VENDING_MACHINE vendors allow high SC (SC 6 >> -2).
        """
        validation = mechanics.validate_purchase(
            character_state=character_high_sc,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Assertions
        assert validation.is_valid is True, "High SC should easily pass vending machine"
        assert validation.sc_blocked is False

    # ============================================================================
    # SUPPLY_DRONE Tests (No SC requirements - neutral vendors)
    # ============================================================================

    def test_supply_drone_allows_low_sc(self, mechanics, character_low_sc, supply_drone_vendor):
        """
        SUPPLY_DRONE vendors have NO SC requirements (neutral zones).

        Even very low SC (SC -5) should be allowed.
        """
        validation = mechanics.validate_purchase(
            character_state=character_low_sc,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )

        # Assertions
        assert validation.is_valid is True, "Supply drones should allow low SC"
        assert validation.sc_blocked is False, "No SC blocking for neutral vendors"

    def test_supply_drone_allows_neutral_sc(self, mechanics, character_neutral_sc, supply_drone_vendor):
        """SUPPLY_DRONE allows neutral SC."""
        validation = mechanics.validate_purchase(
            character_state=character_neutral_sc,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )

        assert validation.is_valid is True
        assert validation.sc_blocked is False

    def test_supply_drone_allows_high_sc(self, mechanics, character_high_sc, supply_drone_vendor):
        """SUPPLY_DRONE allows high SC (neutral vendor, no preferences)."""
        validation = mechanics.validate_purchase(
            character_state=character_high_sc,
            vendor_id="vnd_drone01",
            item_id="itm_rations"
        )

        assert validation.is_valid is True
        assert validation.sc_blocked is False

    # ============================================================================
    # EMERGENCY_CACHE Tests (No SC requirements - crisis override)
    # ============================================================================

    def test_emergency_cache_allows_low_sc(self, mechanics, character_low_sc, emergency_cache_vendor):
        """
        EMERGENCY_CACHE vendors ignore SC (crisis override).

        Even very low SC (SC -5) should have access in emergencies.
        """
        validation = mechanics.validate_purchase(
            character_state=character_low_sc,
            vendor_id="vnd_cache01",
            item_id="itm_firstaid"
        )

        # Assertions
        assert validation.is_valid is True, "Emergency caches override SC restrictions"
        assert validation.sc_blocked is False, "No SC blocking in crisis situations"

    def test_emergency_cache_allows_neutral_sc(self, mechanics, character_neutral_sc, emergency_cache_vendor):
        """EMERGENCY_CACHE allows neutral SC."""
        validation = mechanics.validate_purchase(
            character_state=character_neutral_sc,
            vendor_id="vnd_cache01",
            item_id="itm_firstaid"
        )

        assert validation.is_valid is True
        assert validation.sc_blocked is False

    def test_emergency_cache_allows_high_sc(self, mechanics, character_high_sc, emergency_cache_vendor):
        """EMERGENCY_CACHE allows high SC."""
        validation = mechanics.validate_purchase(
            character_state=character_high_sc,
            vendor_id="vnd_cache01",
            item_id="itm_firstaid"
        )

        assert validation.is_valid is True
        assert validation.sc_blocked is False

    # ============================================================================
    # Edge Cases
    # ============================================================================

    def test_sc_gating_happens_before_currency_check(self, mechanics, character_low_sc, vending_machine_vendor):
        """
        SC gating should fail BEFORE checking currency sufficiency.

        This ensures clear failure messages (SC blocked, not "insufficient funds").
        """
        # Remove all currency
        character_low_sc.energy_purse.drip = 0

        validation = mechanics.validate_purchase(
            character_state=character_low_sc,
            vendor_id="vnd_vm01",
            item_id="itm_medkit"
        )

        # Should fail on SC, not currency
        assert validation.is_valid is False
        assert validation.sc_blocked is True, "Should fail on SC before checking currency"
        assert "Soulcredit" in validation.failure_reason, "Failure reason should mention SC"


class TestVendorTypeCoverage:
    """Ensure all VendorType enum values have defined SC behavior."""

    def test_all_vendor_types_have_sc_rules(self):
        """
        Document SC rules for all vendor types (implementation checkpoint).

        This test serves as documentation of SC gating completeness:

        ✅ VENDING_MACHINE: SC ≥ -2 (implemented)
        ✅ SUPPLY_DRONE: No SC requirements (Phase 1 target)
        ✅ EMERGENCY_CACHE: No SC requirements (Phase 1 target)
        ❌ HUMAN_TRADER: SC-based pricing (Phase 2)
        ❌ Tempest (faction-based): Inverted SC (Phase 2)
        """
        from scripts.aeonisk.multiagent.energy_economy import VendorType

        defined_vendor_types = [
            VendorType.VENDING_MACHINE,
            VendorType.SUPPLY_DRONE,
            VendorType.EMERGENCY_CACHE,
            VendorType.HUMAN_TRADER,
        ]

        # Verify all enum values are accounted for
        for vendor_type in VendorType:
            assert vendor_type in defined_vendor_types, \
                f"Vendor type {vendor_type} missing from SC gating rules documentation"
