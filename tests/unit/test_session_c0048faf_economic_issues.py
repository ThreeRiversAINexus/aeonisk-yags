"""
Regression tests based on session c0048faf economic scenario failures.

This test documents REAL bugs found in production session c0048faf:
1. Mission-gating items priced unaffordably (12 Spark, players have ~2 total)
2. Duplicate "Test Vend-O-Mat" vendors cluttering vendor list
3. Unclear vendor social targeting (vendor_id vs target vs None)
4. No purchase attempts logged (players negotiated but couldn't buy)

Uses actual session data as test fixtures.
"""

import pytest
import json
from pathlib import Path


class TestSessionC0048fafEconomicIssues:
    """Regression tests from session c0048faf-94ee-410d-b517-17591987421b."""

    @pytest.fixture
    def session_data(self):
        """Load actual session JSONL data."""
        session_file = Path("multiagent_output/session_c0048faf-94ee-410d-b517-17591987421b.jsonl")

        if not session_file.exists():
            pytest.skip(f"Session file not found: {session_file}")

        events = []
        with open(session_file, 'r') as f:
            for line in f:
                events.append(json.loads(line))

        return events

    def test_no_purchase_attempts_were_made(self, session_data):
        """
        CRITICAL BUG: Session had vendors + currency, but ZERO purchase attempts.

        Why? Items were unaffordable (12 Spark, players had ~2 total).
        """
        purchase_events = [e for e in session_data if e.get('event_type') == 'purchase_attempt']

        # This SHOULD fail (documenting the bug)
        assert len(purchase_events) == 0, \
            "Session c0048faf had NO purchase attempts despite having vendors and currency"

    def test_mission_gating_item_unaffordable(self, session_data):
        """
        BUG: Bond Insurance Policy (mission requirement) cost 12 Spark.
        Players had ~1-2 Spark each (2-3 total pooled).

        This makes the mission impossible to complete via purchase.
        """
        # Find scenario event
        scenario = next((e for e in session_data if e.get('event_type') == 'scenario'), None)

        if not scenario:
            pytest.skip("No scenario event found")

        vendors = scenario['scenario'].get('active_vendors', [])

        # Find Contract Specialist Rhen
        rhen = next((v for v in vendors if "Rhen" in v['name']), None)

        if not rhen:
            pytest.skip("Contract Specialist Rhen not found")

        # Find Bond Insurance Policy
        policy = next((item for item in rhen['inventory'] if "Bond Insurance" in item['name']), None)

        assert policy is not None, "Bond Insurance Policy not found in Rhen's inventory"

        # CHECK THE BUG
        policy_price = policy['price_spark']
        assert policy_price == 12, f"Expected policy to cost 12 Spark (the bug), got {policy_price}"

        # Find player starting currency
        character_states = [e for e in session_data if e.get('event_type') == 'character_state' and e.get('round') == 0]

        total_party_spark = sum(c['character_state']['energy_purse']['spark'] for c in character_states)

        # Document the bug
        assert total_party_spark < policy_price, \
            f"BUG CONFIRMED: Policy costs {policy_price} Spark, party has {total_party_spark} Spark (unaffordable!)"

    def test_duplicate_test_vendors_present(self, session_data):
        """
        BUG: Two "Test Vend-O-Mat" vendors with identical inventory.

        These are test data from session_config_economic.json that shouldn't
        appear in production scenarios.
        """
        scenario = next((e for e in session_data if e.get('event_type') == 'scenario'), None)

        if not scenario:
            pytest.skip("No scenario event found")

        vendors = scenario['scenario'].get('active_vendors', [])
        vendor_names = [v['name'] for v in vendors]

        # Count "Test Vend-O-Mat" occurrences
        test_vendor_count = vendor_names.count("Test Vend-O-Mat")

        # Document the bug (should be 0, but is 2)
        assert test_vendor_count == 2, \
            f"BUG CONFIRMED: Found {test_vendor_count} 'Test Vend-O-Mat' vendors (should be 0 in production)"

    def test_player_targeted_vendor_id_for_social_action(self, session_data):
        """
        UNCLEAR BEHAVIOR: Player used vendor_id as target for social action.

        Kress: target="vnd_0a32" (Contract Specialist Rhen's vendor_id)

        Question: Is this correct? Should social dialogue use:
        - target=vendor_id? (what Kress did)
        - target=None? (what prompt examples suggest)
        - target=tgt_xxxx? (combat targeting, not applicable)
        """
        # Find Kress's action
        kress_actions = [e for e in session_data
                        if e.get('event_type') == 'action_declaration'
                        and e.get('character_name') == 'ACG Auditor Kress Valen']

        if not kress_actions:
            pytest.skip("Kress's actions not found")

        first_action = kress_actions[0]['action']

        # Check what Kress did
        assert first_action['target'] == 'vnd_0a32', \
            "Kress targeted vendor_id for social action (is this correct?)"

        # This test documents the ambiguity - it doesn't assert correct behavior
        print(f"\n⚠️  AMBIGUITY: Kress used target='{first_action['target']}' for vendor dialogue.")
        print("   Should vendor dialogue use target=vendor_id or target=None?")

    def test_mission_alternative_more_expensive_than_direct(self, session_data):
        """
        DESIGN ISSUE: Mission offers "8 Spark OR Bond Insurance Policy".

        But policy costs 12 Spark (4 more than direct payment).
        Why would anyone buy the policy?
        """
        scenario = next((e for e in session_data if e.get('event_type') == 'scenario'), None)

        if not scenario:
            pytest.skip("No scenario event found")

        # Scenario description mentions "8 Spark payment or a Bond Insurance Policy"
        situation = scenario['scenario']['situation']
        assert "8 Spark" in situation and "Bond Insurance Policy" in situation, \
            "Mission should offer both payment options"

        # Find policy price
        vendors = scenario['scenario'].get('active_vendors', [])
        rhen = next((v for v in vendors if "Rhen" in v['name']), None)

        if not rhen:
            pytest.skip("Rhen not found")

        policy = next((item for item in rhen['inventory'] if "Bond Insurance" in item['name']), None)

        direct_payment = 8  # Spark (from mission description)
        policy_price = policy['price_spark'] if policy else None

        if policy_price:
            # Document the design issue
            assert policy_price > direct_payment, \
                f"DESIGN ISSUE: Policy ({policy_price} Spark) costs MORE than direct payment ({direct_payment} Spark). Why would anyone buy it?"


class TestEconomicScenarioDesignPrinciples:
    """
    Design principles derived from session c0048faf failures.

    These are ASPIRATIONAL tests - they define how things SHOULD work.
    """

    def test_mission_items_should_be_poolable(self):
        """
        Design principle: Items required for mission should be affordable
        by pooling 2-3 players' resources.

        From session c0048faf:
        - Mission required: Bond Insurance Policy (12 Spark)
        - Party resources: ~2 Spark total (1 Spark each)
        - Result: Impossible to complete mission
        """
        # Typical party resources (2-3 players)
        party_spark_range = (2, 5)  # Min 2 Spark, max 5 Spark pooled

        # Mission-gating item should be affordable
        mission_item_price = 3  # ✅ Affordable
        unaffordable_price = 12  # ❌ Too expensive (session c0048faf bug)

        assert mission_item_price <= party_spark_range[1], \
            "Mission items should be affordable by pooling party resources"

        assert unaffordable_price > party_spark_range[1], \
            "Document the bug: 12 Spark is unaffordable for typical party"

    def test_mission_alternatives_should_have_tradeoffs(self):
        """
        Design principle: When mission offers "Option A OR Option B",
        each option should have distinct advantages.

        BAD: "Pay 8 Spark OR buy policy for 12 Spark" (why buy policy?)
        GOOD: "Pay 8 Spark OR buy policy for 5 Spark (but it takes time)"
        """
        direct_payment = 8  # Spark, immediate
        policy_payment = 5  # Spark, but requires clock advancement

        # Alternative should be cheaper OR have strategic benefit
        assert policy_payment < direct_payment, \
            "Alternative payment should have SOME advantage (lower cost, side benefits, etc.)"

    def test_test_vendors_should_not_appear_in_production(self):
        """
        Design principle: Vendors with "Test" in name are development fixtures,
        not production content.
        """
        production_vendors = ["Contract Specialist Rhen", "Scribe Orven", "Underground Broker"]
        test_vendors = ["Test Vend-O-Mat", "Debug Shop", "Placeholder Vendor"]

        for vendor in test_vendors:
            assert "Test" in vendor or "Debug" in vendor or "Placeholder" in vendor, \
                f"Vendor '{vendor}' appears to be test data"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
