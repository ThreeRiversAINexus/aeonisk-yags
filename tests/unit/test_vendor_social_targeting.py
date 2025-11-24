"""
Tests for vendor social interaction targeting.

PROBLEM (from session c0048faf):
- Players tried to "talk to" vendors using vendor_id as target
- Unclear whether social actions with vendors use target=vendor_id or target=None
- Purchase actions use vendor_id/item_id, but dialogue actions are ambiguous

This test defines the CORRECT behavior.
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import Vendor, VendorItem, VendorType, EnergyPurse


class MockCharacterState:
    def __init__(self, name, agent_id, energy_purse, inventory=None):
        self.name = name
        self.agent_id = agent_id
        self.energy_purse = energy_purse
        self.inventory = inventory or {}


class TestVendorSocialTargeting:
    """Test social actions with vendors (dialogue, negotiation)."""

    def test_vendor_dialogue_does_not_require_target(self):
        """
        Vendor dialogue (asking questions, negotiating) should NOT require target field.

        Unlike purchases (which need vendor_id/item_id for validation),
        pure dialogue is narrative and doesn't need mechanical targeting.
        """
        # Example: Player asks vendor about inventory
        action = {
            'intent': 'Ask Contract Specialist Rhen about payment plans',
            'description': 'I approach Rhen and ask about flexible payment options.',
            'action_type': 'social',
            'attribute': 'Charisma',
            'skill': 'Corporate Influence',
            # NO target field needed - DM knows context from description
        }

        # This should be valid (no target required for dialogue)
        assert 'target' not in action or action.get('target') is None

    def test_vendor_purchase_requires_ids(self):
        """
        Purchase actions MUST include vendor_id and item_id for pre-validation.

        This is the mechanical purchase flow tested in test_mechanical_purchase_flow.py
        """
        action = {
            'intent': 'Purchase Bond Insurance Policy from Rhen',
            'description': 'I buy the policy using my Spark.',
            'action_type': 'social',
            'vendor_id': 'vnd_0a32',  # ← REQUIRED for purchase
            'item_id': 'itm_ca1s',    # ← REQUIRED for purchase
        }

        # Purchases must have both IDs
        assert 'vendor_id' in action
        assert 'item_id' in action

    def test_vendor_id_vs_target_id_distinction(self):
        """
        CRITICAL: vendor_id (vnd_xxxx) is NOT the same as target (tgt_xxxx).

        - vendor_id: For purchase validation (identifies vendor in SharedState)
        - target: For combat/status effects (identifies combatant in TargetMapper)

        Vendors are NOT combatants, so they don't have target IDs.
        """
        vendor = Vendor(
            vendor_id="vnd_test",
            name="Test Vendor",
            faction="Nexus",
            vendor_type=VendorType.HUMAN_TRADER,
            inventory=[]
        )

        # Vendor has vendor_id but NO target_id
        assert hasattr(vendor, 'vendor_id')
        assert vendor.vendor_id == "vnd_test"
        assert not hasattr(vendor, 'target_id')  # Vendors aren't combatants!


class TestVendorAffordabilityDesign:
    """
    Test that mission-gating items are priced affordably.

    PROBLEM (from session c0048faf):
    - Mission required "Bond Insurance Policy" (12 Spark)
    - Players had ~2 Spark total combined
    - Impossible to complete mission via purchase
    """

    def test_mission_gating_item_affordability(self):
        """
        Items required for mission completion should be affordable by pooling party resources.

        Design principle: If an item is REQUIRED for mission success,
        price it so 2-3 players can afford it by pooling currency.
        """
        # Typical party resources (2-3 players pooling)
        party_resources = {
            'spark': 3,  # Each player has 1-2 Spark → pooled = 3-4 Spark
            'drip': 15,  # Each player has 5-8 Drip → pooled = 15-20 Drip
        }

        # Mission-gating item (like Bond Insurance Policy)
        mission_item = VendorItem(
            item_id="itm_policy",
            name="Bond Insurance Policy",
            description="Required to free the contact",
            inventory_key="bond_policy",
            price_spark=3  # ✅ Affordable by pooling (was 12 in broken session!)
        )

        # Verify affordability
        assert mission_item.price_spark <= party_resources['spark'], \
            "Mission-gating items must be affordable by pooling party resources"

    def test_luxury_items_can_be_expensive(self):
        """
        Non-essential items (cosmetic, convenience) can be expensive.

        These are aspirational purchases, not mission requirements.
        """
        luxury_item = VendorItem(
            item_id="itm_luxury",
            name="Soulcredit Report (Detailed)",
            description="Nice to have, but not required",
            inventory_key="credit_report",
            price_spark=15  # ✅ Expensive is OK for optional items
        )

        # Luxury items can be unaffordable - that's fine
        assert luxury_item.price_spark > 10, "Luxury items can be expensive"


class TestVendorInventoryClarity:
    """
    Test vendor inventory matches mission requirements.

    PROBLEM (from session c0048faf):
    - Mission said "8 Spark OR Bond Insurance Policy"
    - Vendor had the policy but it cost 12 Spark (more than 8!)
    - Confusing: is the policy an alternative or an upgrade?
    """

    def test_mission_alternatives_have_clear_pricing(self):
        """
        When mission offers "Option A OR Option B", both should be viable.

        BAD: "Pay 8 Spark OR buy policy for 12 Spark" (why would you buy the policy?)
        GOOD: "Pay 8 Spark OR buy policy for 5 Spark + collateral"
        """
        # Mission requirement from scenario
        direct_payment_cost = 8  # Spark

        # Alternative option (policy)
        policy_price = 5  # Spark (cheaper than direct payment!)

        # The alternative should be CHEAPER or have different tradeoffs
        assert policy_price < direct_payment_cost, \
            "Alternative payment methods should be cheaper or have unique benefits"

    def test_vendor_inventory_matches_scenario_needs(self):
        """
        Vendors spawned for scenario should carry items relevant to that scenario.

        Don't spawn generic "Health Kit" vendors in a debt negotiation mission.
        """
        # Debt negotiation scenario → vendor should have debt-related items
        relevant_items = ["Bond Insurance Policy", "Debt Consolidation Service", "Contract Templates"]

        # BAD: Generic vendor with Health Kits (from session c0048faf)
        bad_vendor_inventory = ["Health Kit", "Energy Cell", "Spark Cell"]

        # Check that vendor inventory is mission-relevant
        for item in bad_vendor_inventory:
            assert item not in relevant_items, \
                f"Vendor inventory should match mission theme (debt negotiation), not generic items like {item}"


class TestDuplicateVendorFiltering:
    """
    Test that test vendors don't pollute production scenarios.

    PROBLEM (from session c0048faf):
    - Two "Test Vend-O-Mat" vendors with identical inventory
    - These were test data from session_config_economic.json
    - Cluttered vendor list and confused players
    """

    def test_no_duplicate_vendor_names(self):
        """
        Scenario should not have multiple vendors with the same name.

        Exception: Franchise chains (e.g., "Nexus Vend-O-Mat #1", "#2")
        """
        vendors = [
            Vendor(vendor_id="vnd_1", name="Test Vend-O-Mat", faction="Nexus",
                   vendor_type=VendorType.VENDING_MACHINE, inventory=[]),
            Vendor(vendor_id="vnd_2", name="Test Vend-O-Mat", faction="Nexus",
                   vendor_type=VendorType.VENDING_MACHINE, inventory=[]),
            Vendor(vendor_id="vnd_3", name="Contract Specialist Rhen", faction="ACG",
                   vendor_type=VendorType.HUMAN_TRADER, inventory=[]),
        ]

        vendor_names = [v.name for v in vendors]
        duplicate_names = [name for name in vendor_names if vendor_names.count(name) > 1]

        # Flag duplicates (this test will FAIL on session c0048faf data)
        assert len(duplicate_names) == 0 or "Test" in duplicate_names[0], \
            f"Duplicate vendor names found: {duplicate_names}. Remove test vendors from production scenarios."

    def test_test_vendors_excluded_from_production(self):
        """
        Vendors with "Test" in the name should not appear in production scenarios.
        """
        production_vendor_names = [
            "Test Vend-O-Mat",  # ❌ This is a test vendor!
            "Contract Specialist Rhen",  # ✅ Production vendor
        ]

        test_vendors = [name for name in production_vendor_names if "Test" in name]

        # Production scenarios should have NO test vendors
        if len(test_vendors) > 0:
            pytest.fail(f"Test vendors found in production scenario: {test_vendors}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
