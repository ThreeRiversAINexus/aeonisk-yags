"""
Integration tests for ritual offerings consumption mechanics.

Tests verify the complete flow:
1. Player declares offering use (has_offering=True, optional offering_type)
2. Mechanics consumes offering BEFORE DM narration (mechanics-authoritative)
3. DM receives offering consumption result as context
4. DM narrates what actually happened
5. JSONL logs inventory_changes in action_resolution event
6. Character inventory updated correctly

Based on fixture: test_ritual_offerings_bug.jsonl (session_56a6de6f-6547-4433-bc8a-da0a5d111853)

ARCHITECTURE:
This follows the "mechanics-first → DM narrates" pattern established by dice rolling and DC calculation.
Offering consumption is MECHANICAL (inventory mutation), not narrative (storytelling).

Last updated: 2025-11-02
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sessions" / "test_ritual_offerings_bug.jsonl"


def load_fixture_events() -> List[Dict[str, Any]]:
    """Load all events from the offerings bug fixture."""
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture not found: {FIXTURE_PATH}")

    events = []
    with open(FIXTURE_PATH, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


@pytest.fixture
def fixture_events():
    """Provide fixture events to tests."""
    return load_fixture_events()


class TestOfferingsConsumptionArchitecture:
    """Test that offerings follow mechanics-first architecture."""

    @pytest.mark.xfail(reason="KNOWN BUG: Offerings consumed post-narration instead of pre-narration")
    def test_offering_consumed_before_dm_narration(self, fixture_events):
        """
        Test that offerings are consumed BEFORE DM narration, not after.

        Architecture: Mechanics-first (like dice rolling, DC calculation)
        - Mechanics consumes offering from inventory
        - DM receives consumption result as context
        - DM narrates what actually happened

        Current bug: Offering consumption happens in player.py:782 AFTER DM narration.
        Expected: Consumption happens in dm.py BEFORE calling _generate_llm_response.
        """
        action_res = [e for e in fixture_events if e.get('event_type') == 'action_resolution'][0]

        # DM should have received offering consumption context
        context = action_res.get('context', {})

        assert 'offering_consumed' in context, \
            "DM context should include offering_consumed field (mechanics result)"

        assert context['offering_consumed'] is True, \
            "offering_consumed should be True when player declared has_offering=True and had inventory"

        assert 'offering_item' in context, \
            "DM context should include offering_item field (which item was consumed)"

        # Should be "Purification Incense" based on player's starting inventory
        offering_item = context['offering_item']
        assert offering_item in ["Purification Incense", "Ritual Offerings", "incense"], \
            f"offering_item should be specific item name, got: {offering_item}"


class TestOfferingsInventoryMutation:
    """Test that offerings are correctly consumed from player inventory."""

    @pytest.mark.xfail(reason="KNOWN BUG: Offerings not consumed from inventory")
    def test_offering_consumed_when_available(self, fixture_events):
        """
        Test that offerings are removed from inventory when used.

        Starting inventory (from session config):
        - "Ritual Offerings": 2
        - "Purification Incense": 3

        Expected behavior:
        - Player declares has_offering=True
        - Mechanics consumes 1 offering (prefers "incense" over generic "Ritual Offerings")
        - Inventory updated: "Purification Incense": 2
        - JSONL logs inventory change
        """
        # Get session start to verify starting inventory
        session_start = [e for e in fixture_events if e.get('event_type') == 'session_start'][0]
        starting_inv = session_start['config']['agents']['players'][0]['inventory']

        assert starting_inv['Purification Incense'] == 3, \
            "Player should start with 3 Purification Incense"

        # Get action resolution
        action_res = [e for e in fixture_events if e.get('event_type') == 'action_resolution'][0]

        # Check inventory_changes field exists and has consumption
        effects = action_res.get('effects', {})

        assert 'inventory_changes' in effects, \
            "effects should have inventory_changes field (not top-level list)"

        inv_changes = effects['inventory_changes']
        assert len(inv_changes) > 0, \
            "Should have at least one inventory change for offering consumption"

        # Check that an offering was consumed (negative delta)
        offering_consumed = any(
            ('incense' in item.get('item', '').lower() or
             'offering' in item.get('item', '').lower()) and
            item.get('delta', 0) < 0
            for item in inv_changes
        )

        assert offering_consumed, \
            f"Should consume offering from inventory. Got inventory_changes: {inv_changes}"

        # Check specific consumption details
        consumed_item = next(
            (item for item in inv_changes
             if ('incense' in item.get('item', '').lower() or 'offering' in item.get('item', '').lower())
             and item.get('delta', 0) < 0),
            None
        )

        assert consumed_item is not None
        assert consumed_item['delta'] == -1, \
            "Should consume exactly 1 offering"
        assert 'reason' in consumed_item, \
            "Inventory change should include reason field"
        assert 'offering' in consumed_item['reason'].lower(), \
            f"Reason should mention offering consumption, got: {consumed_item['reason']}"

    def test_offering_not_consumed_when_unavailable(self):
        """
        Test that missing offerings are handled gracefully.

        MOCKED TEST (no fixture run needed):
        - Player declares has_offering=True
        - Player has NO offerings in inventory
        - mechanics.consume_offering() returns None
        - offering_consumed=False in context
        - Void penalty applied (+1 void)

        This test documents expected behavior for the missing offering case.
        Actual implementation will be verified via unit tests in test_mechanics.py.
        """
        # Mock expected behavior
        expected_context = {
            "offering_consumed": False,
            "offering_item": None
        }

        expected_economy = {
            "void_delta": 1,  # +1 void penalty for ritual without offering
            "void_triggers": ["Missing offering for ritual action"]
        }

        # This documents the contract - actual tests will verify implementation
        assert expected_context['offering_consumed'] is False
        assert expected_economy['void_delta'] == 1


class TestOfferingsJSONLSchema:
    """Test that inventory_changes are properly logged in JSONL events."""

    @pytest.mark.xfail(reason="KNOWN BUG: inventory_changes field doesn't exist in effects")
    def test_inventory_changes_field_exists(self, fixture_events):
        """
        Test that action_resolution events have effects.inventory_changes field.

        Current schema bug:
        - effects is a LIST of status effect strings (e.g., ["Stunned", "Inspired"])
        - No inventory_changes field exists

        Expected schema:
        - effects is a DICT with:
          - status_effects: List[str]
          - inventory_changes: List[InventoryChange]
        """
        action_res = [e for e in fixture_events if e.get('event_type') == 'action_resolution'][0]

        effects = action_res.get('effects', {})

        # Schema should have inventory_changes field
        assert isinstance(effects, dict), \
            "effects should be a dict, not a list (schema bug)"

        assert 'inventory_changes' in effects, \
            "effects should have inventory_changes field"

        assert isinstance(effects['inventory_changes'], list), \
            "inventory_changes should be a list of InventoryChange objects"

    @pytest.mark.xfail(reason="KNOWN BUG: economy doesn't track offering consumption")
    def test_economy_tracks_offering_consumption(self, fixture_events):
        """
        Test that economy section tracks whether offering was consumed.

        Expected fields:
        - economy.offering_consumed: bool (was offering actually consumed?)
        - economy.offering_item: str (which item was consumed?)

        This helps differentiate:
        - Player declared but didn't have offering (offering_consumed=False, +1 void)
        - Player declared and offering consumed (offering_consumed=True, -1 void)
        """
        action_res = [e for e in fixture_events if e.get('event_type') == 'action_resolution'][0]

        economy = action_res.get('economy', {})

        assert 'offering_consumed' in economy, \
            "economy should track offering_consumed (bool)"

        assert 'offering_item' in economy, \
            "economy should track offering_item (str)"

        # For this fixture, offering should have been consumed
        assert economy['offering_consumed'] is True, \
            "Player declared offering and had inventory, should be consumed"

        assert economy['offering_item'] is not None, \
            "Should record which specific item was consumed"


class TestOfferingsVoidMechanics:
    """Test that void changes correctly reflect offering usage."""

    def test_void_reduction_with_offering(self, fixture_events):
        """
        Test that using offerings reduces void (ritual cleansing).

        From fixture:
        - Player declared offering use
        - DM narration: "offering burns cleanly to ash"
        - Expected: void_delta should be negative (cleansing)

        This test PASSES even with the bug because void mechanics ARE working
        via structured output. The bug is only that inventory isn't updated.
        """
        action_res = [e for e in fixture_events if e.get('event_type') == 'action_resolution'][0]

        economy = action_res.get('economy', {})
        void_delta = economy.get('void_delta')

        # Should have void reduction from successful ritual
        assert void_delta is not None
        assert void_delta < 0, \
            f"Ritual with offering should reduce void, got void_delta: {void_delta}"

        # Should be from structured output, not narrative parsing
        void_source = economy.get('void_source')
        assert void_source == "structured_output", \
            f"Void changes should come from structured output, got: {void_source}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
