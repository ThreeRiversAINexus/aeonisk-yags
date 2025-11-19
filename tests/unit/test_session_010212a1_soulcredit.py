"""
Regression test for soulcredit logging bug (session 010212a1).

This test documents a bug in EXISTING session data where character_state JSONL
events show stale soulcredit values (not synced from mechanics).

Bug report:
- Session: multiagent_output/session_010212a1-f8a8-4fce-8555-08bd4ab7882c.jsonl
- Issue: character_state events logged stale soulcredit (not synced from mechanics)
- Examples:
  * Thresh Kain: Round 1 action_resolution soulcredit_delta = -1, but Round 2
    character_state still shows soulcredit = -2 (should be -3)
  * Kael Voss: Round 1 action_resolution soulcredit_delta = +1, but Round 2
    character_state still shows soulcredit = 5 (should be 6)

Root cause: Soulcredit changes applied to mechanics.soulcredit_states but not
synced to player.character_state.soulcredit before log_character_state() called.

Fix implemented: player.py:860-864 now syncs soulcredit (parallel to void sync).

NOTE: These tests document the bug in OLD data. They test AGAINST the buggy
fixture to demonstrate the issue. For tests that verify the FIX works, see
test_player_soulcredit_sync.py (which tests the fixed code directly).
"""

import json
import pytest


@pytest.fixture
def fixture_events():
    """Load events from regression fixture."""
    fixture_path = "tests/fixtures/sessions/regression_soulcredit_logging_bug.jsonl"
    with open(fixture_path, 'r') as f:
        events = [json.loads(line) for line in f]
    return events


def find_event(events, event_type, **filters):
    """
    Find first event matching type and filters.

    Args:
        events: List of JSONL events
        event_type: Event type string
        **filters: Key-value pairs to match in event
    """
    for event in events:
        if event.get('event_type') != event_type:
            continue

        # Check all filters
        match = True
        for key, value in filters.items():
            # Support nested keys (e.g., "economy.soulcredit_delta")
            if '.' in key:
                parts = key.split('.')
                event_value = event
                for part in parts:
                    if isinstance(event_value, dict):
                        event_value = event_value.get(part)
                    else:
                        event_value = None
                        break
            else:
                event_value = event.get(key)

            if event_value != value:
                match = False
                break

        if match:
            return event

    return None


def find_all_events(events, event_type, **filters):
    """Find all events matching type and filters."""
    results = []
    for event in events:
        if event.get('event_type') != event_type:
            continue

        # Check all filters
        match = True
        for key, value in filters.items():
            # Support nested keys
            if '.' in key:
                parts = key.split('.')
                event_value = event
                for part in parts:
                    if isinstance(event_value, dict):
                        event_value = event_value.get(part)
                    else:
                        event_value = None
                        break
            else:
                event_value = event.get(key)

            if event_value != value:
                match = False
                break

        if match:
            results.append(event)

    return results


def test_thresh_kain_round_2_soulcredit_reflects_round_1_change(fixture_events):
    """
    Test that Thresh Kain's Round 2 character_state reflects Round 1 soulcredit change.

    Round 1: Thresh threatens violence (soulcredit_delta = -1)
    Round 1 character_state: soulcredit = -2 (initial value)
    Round 2 character_state: soulcredit should be -3 (was -2 before fix, WRONG!)
    """
    # Find Thresh's Round 1 character_state (initial value)
    thresh_r1_state = find_event(
        fixture_events,
        'character_state',
        round=1,
        character_name='Cartel Enforcer Thresh Kain'
    )
    assert thresh_r1_state is not None, "Could not find Thresh Kain Round 1 character_state"
    initial_sc = thresh_r1_state['soulcredit']
    assert initial_sc == -2, f"Expected initial soulcredit = -2, got {initial_sc}"

    # Find Thresh's Round 1 action resolutions with soulcredit changes
    # Note: action_resolution uses 'agent' field, not 'character_name'
    thresh_r1_actions = find_all_events(
        fixture_events,
        'action_resolution',
        round=1,
        agent='Cartel Enforcer Thresh Kain'
    )

    # Sum all soulcredit deltas from Round 1
    total_sc_delta = 0
    for action in thresh_r1_actions:
        economy = action.get('economy', {})
        sc_delta = economy.get('soulcredit_delta', 0)
        total_sc_delta += sc_delta

    # Expect at least one negative soulcredit change (threatened violence)
    assert total_sc_delta < 0, (
        f"Expected negative soulcredit delta for Thresh in Round 1, got {total_sc_delta}"
    )

    # Find Thresh's Round 2 character_state
    thresh_r2_state = find_event(
        fixture_events,
        'character_state',
        round=2,
        character_name='Cartel Enforcer Thresh Kain'
    )
    assert thresh_r2_state is not None, "Could not find Thresh Kain Round 2 character_state"

    # CRITICAL ASSERTION: Document the bug - Round 2 has STALE soulcredit
    # This fixture was extracted from a session BEFORE the fix, so it has the bug
    expected_sc_after_fix = initial_sc + total_sc_delta  # -2 + (-1) = -3
    actual_sc_in_buggy_data = thresh_r2_state['soulcredit']  # Still -2 (STALE)

    # Assert that the buggy data shows stale values (documents the bug)
    assert actual_sc_in_buggy_data == initial_sc, (
        f"Unexpected! Fixture data should show stale soulcredit (bug documentation)\n"
        f"  Initial (Round 1): {initial_sc}\n"
        f"  Total delta (Round 1): {total_sc_delta}\n"
        f"  Expected after fix: {expected_sc_after_fix}\n"
        f"  Actual in buggy data: {actual_sc_in_buggy_data}\n"
        f"  This test documents that old sessions have this bug"
    )

    # Document what the CORRECT value should be after fix
    print(f"\n[BUG DOCUMENTATION] Thresh Kain Round 2:")
    print(f"  Buggy value (in fixture): {actual_sc_in_buggy_data}")
    print(f"  Correct value (after fix): {expected_sc_after_fix}")
    print(f"  Difference: {expected_sc_after_fix - actual_sc_in_buggy_data}")


def test_kael_voss_round_2_soulcredit_reflects_round_1_change(fixture_events):
    """
    Test that Kael Voss's Round 2 character_state reflects Round 1 soulcredit change.

    Round 1: Kael attempts lawful settlement (soulcredit_delta = +1)
    Round 1 character_state: soulcredit = 5 (initial value)
    Round 2 character_state: soulcredit should be 6 (was 5 before fix, WRONG!)
    """
    # Find Kael's Round 1 character_state (initial value)
    kael_r1_state = find_event(
        fixture_events,
        'character_state',
        round=1,
        character_name='Trade Negotiator Kael Voss'
    )
    assert kael_r1_state is not None, "Could not find Kael Voss Round 1 character_state"
    initial_sc = kael_r1_state['soulcredit']
    assert initial_sc == 5, f"Expected initial soulcredit = 5, got {initial_sc}"

    # Find Kael's Round 1 action resolutions with soulcredit changes
    # Note: action_resolution uses 'agent' field, not 'character_name'
    kael_r1_actions = find_all_events(
        fixture_events,
        'action_resolution',
        round=1,
        agent='Trade Negotiator Kael Voss'
    )

    # Sum all soulcredit deltas from Round 1
    total_sc_delta = 0
    for action in kael_r1_actions:
        economy = action.get('economy', {})
        sc_delta = economy.get('soulcredit_delta', 0)
        total_sc_delta += sc_delta

    # Expect at least one positive soulcredit change (lawful settlement attempt)
    assert total_sc_delta > 0, (
        f"Expected positive soulcredit delta for Kael in Round 1, got {total_sc_delta}"
    )

    # Find Kael's Round 2 character_state
    kael_r2_state = find_event(
        fixture_events,
        'character_state',
        round=2,
        character_name='Trade Negotiator Kael Voss'
    )
    assert kael_r2_state is not None, "Could not find Kael Voss Round 2 character_state"

    # CRITICAL ASSERTION: Document the bug - Round 2 has STALE soulcredit
    # This fixture was extracted from a session BEFORE the fix, so it has the bug
    expected_sc_after_fix = initial_sc + total_sc_delta  # 5 + 1 = 6
    actual_sc_in_buggy_data = kael_r2_state['soulcredit']  # Still 5 (STALE)

    # Assert that the buggy data shows stale values (documents the bug)
    assert actual_sc_in_buggy_data == initial_sc, (
        f"Unexpected! Fixture data should show stale soulcredit (bug documentation)\n"
        f"  Initial (Round 1): {initial_sc}\n"
        f"  Total delta (Round 1): {total_sc_delta}\n"
        f"  Expected after fix: {expected_sc_after_fix}\n"
        f"  Actual in buggy data: {actual_sc_in_buggy_data}\n"
        f"  This test documents that old sessions have this bug"
    )

    # Document what the CORRECT value should be after fix
    print(f"\n[BUG DOCUMENTATION] Kael Voss Round 2:")
    print(f"  Buggy value (in fixture): {actual_sc_in_buggy_data}")
    print(f"  Correct value (after fix): {expected_sc_after_fix}")
    print(f"  Difference: {expected_sc_after_fix - actual_sc_in_buggy_data}")


def test_void_score_correctly_synced_as_control(fixture_events):
    """
    Control test: Verify void_score DOES sync correctly (unlike soulcredit).

    This test should PASS both before and after the soulcredit fix, proving
    that void sync works correctly (player.py:858) while soulcredit does not.
    """
    # Find Veyra's Round 2 action with void change
    # Note: action_resolution uses 'agent' field, not 'character_name'
    veyra_r2_action = find_event(
        fixture_events,
        'action_resolution',
        round=2,
        agent='Attunement Ritualist Veyra Lune'
    )

    if veyra_r2_action is None:
        pytest.skip("Could not find Veyra's Round 2 action with void change")

    effects = veyra_r2_action.get('effects', {})
    void_changes = effects.get('void_changes', [])

    if not void_changes:
        pytest.skip("Veyra's Round 2 action has no void changes")

    # Find Veyra's Round 1 character_state (before change)
    veyra_r1_state = find_event(
        fixture_events,
        'character_state',
        round=1,
        character_name='Attunement Ritualist Veyra Lune'
    )
    assert veyra_r1_state is not None
    initial_void = veyra_r1_state['void_score']

    # Calculate expected void after changes (with clamping to 0-10)
    total_void_delta = sum(vc['amount'] for vc in void_changes)
    expected_void = max(0, min(10, initial_void + total_void_delta))

    # Find Veyra's Round 2 character_state (after change)
    veyra_r2_state = find_event(
        fixture_events,
        'character_state',
        round=2,
        character_name='Attunement Ritualist Veyra Lune'
    )
    assert veyra_r2_state is not None
    actual_void = veyra_r2_state['void_score']

    # Void should be synced correctly (this is the control - should PASS)
    assert actual_void == expected_void, (
        f"Control test failed: void_score not synced!\n"
        f"  Initial (Round 1): {initial_void}\n"
        f"  Total delta (Round 2): {total_void_delta}\n"
        f"  Expected (Round 2): {expected_void}\n"
        f"  Actual (Round 2): {actual_void}\n"
        f"  This should work! (void has sync at player.py:858)"
    )
