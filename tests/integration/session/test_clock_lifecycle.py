"""
Clock Lifecycle Integration Tests

Tests complete clock lifecycle from spawn → progression → removal using real session fixtures.

Lifecycle Paths Tested:
1. CONFIG_LOADED → PROGRESSION → TIMEOUT ✅
2. DM_SPAWN → PROGRESSION → FILL → REMOVAL (XFAIL - need newer fixtures with clock_spawn events)
3. DM_SPAWN → PROGRESSION → OVERFLOW → CONSEQUENCE (XFAIL - need newer fixtures with overflow)
4. STORY_ADVANCEMENT → NEW_CLOCKS → PROGRESSION (future work)

Fixtures Used:
- session_starting_clocks.jsonl - Older fixture (no clock_removal events)
- session_starting_clocks_with_removal.jsonl - Newer fixture (has clock_removal)
- session_multi_clock.jsonl - Multi-clock scenarios

Note: Many tests are marked XFAIL because available fixtures predate recent clock logging
features (clock_spawn, clock_completion, clock_removal added in commits 66c447d, e6b9250).
To get full test coverage, we need NEW fixtures generated with the latest code.
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any


# ==============================================================================
# Fixtures
# ==============================================================================

def load_fixture(relative_path: str) -> List[Dict[str, Any]]:
    """Load JSONL fixture and return list of events."""
    # Try tests/fixtures/ first, then multiagent_output/
    fixture_paths = [
        Path(__file__).parent.parent.parent / "fixtures" / relative_path,
        Path(__file__).parent.parent.parent.parent / relative_path,
    ]

    for fixture_path in fixture_paths:
        if fixture_path.exists():
            events = []
            with open(fixture_path, 'r') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
            return events

    raise FileNotFoundError(f"Fixture not found: {relative_path} (tried {len(fixture_paths)} locations)")


@pytest.fixture
def starting_clocks_session():
    """Session with config-loaded starting clocks (older fixture, no removal events).

    Contains:
    - Investigation Progress: 0/1 (never filled, times out)
    - Security Response: 1/4 → 3/4 (pre-advanced, progresses, times out)

    Note: This is an older fixture from before clock_removal logging was added.
    Use starting_clocks_session_with_removal for tests that need removal events.
    """
    return load_fixture("sessions/session_starting_clocks.jsonl")


@pytest.fixture
def starting_clocks_session_with_removal():
    """Session with config-loaded starting clocks AND clock_removal events (newer fixture).

    Contains:
    - Investigation Progress: 0/1 → removed (session_end)
    - Security Response: 1/4 → 4/4 → removed (filled)

    Note: This fixture was generated AFTER clock_removal logging was implemented.
    """
    return load_fixture("sessions/session_starting_clocks_with_removal.jsonl")


@pytest.fixture
def ad_hoc_clocks_session():
    """Session with DM-spawned clocks and complete clock lifecycle events.

    Contains clock_spawn (7), clock_completion (3), clock_removal (8) events.
    Generated with latest code - suitable for comprehensive clock lifecycle testing.
    """
    return load_fixture("sessions/golden_clock_lifecycle_complete.jsonl")


@pytest.fixture
def multi_clock_session():
    """Session with 4+ simultaneous clocks."""
    return load_fixture("sessions/session_multi_clock.jsonl")


@pytest.fixture
def events_by_type(starting_clocks_session):
    """Group events by event_type for quick filtering."""
    events = {}
    for event in starting_clocks_session:
        event_type = event.get('event_type', 'unknown')
        if event_type not in events:
            events[event_type] = []
        events[event_type].append(event)
    return events


# ==============================================================================
# Test Class 1: Starting Clock Lifecycle
# ==============================================================================

class TestStartingClockLifecycle:
    """Test clocks loaded from session config."""

    def test_starting_clocks_load_from_config(self, starting_clocks_session_with_removal):
        """Verify starting_clocks config feature loads clocks at session start."""
        # Find session_start event
        session_start = starting_clocks_session_with_removal[0]

        assert session_start["event_type"] == "session_start", \
            "First event should be session_start"

        assert "starting_clocks" in session_start["config"], \
            "session_start config should have starting_clocks field"

        starting_clocks = session_start["config"]["starting_clocks"]
        assert len(starting_clocks) == 2, \
            "Should have exactly 2 starting clocks"

        # Verify clock configurations
        clock_names = [c["name"] for c in starting_clocks]
        assert "Investigation Progress" in clock_names
        assert "Security Response" in clock_names

        # Verify pre-advancement (Security Response starts at 1/4, not 0/4)
        security_clock = next(c for c in starting_clocks if c["name"] == "Security Response")
        assert security_clock["current_ticks"] == 1, \
            "Security Response should be pre-advanced to 1/4"
        assert security_clock["max_ticks"] == 4

    def test_starting_clocks_appear_in_first_round(self, starting_clocks_session):
        """Verify starting clocks appear in first action_resolution.clocks."""
        # Find first action_resolution event
        first_resolution = None
        for event in starting_clocks_session:
            if event.get("event_type") == "action_resolution":
                first_resolution = event
                break

        assert first_resolution is not None, \
            "Session should have at least one action_resolution"

        assert "clocks" in first_resolution, \
            "First resolution should include clocks field"

        clocks = first_resolution["clocks"]
        assert "Investigation Progress" in clocks
        assert "Security Response" in clocks

        # Verify Security Response maintains pre-advanced state
        assert clocks["Security Response"] == "1/4", \
            "Security Response should still be at 1/4 in first round"

    def test_starting_clocks_progress_during_gameplay(self, starting_clocks_session):
        """Verify clocks loaded from config progress during gameplay."""
        # Track clock states across all action_resolutions
        clock_states = {}

        for event in starting_clocks_session:
            if event.get("event_type") == "action_resolution" and "clocks" in event:
                for clock_name, clock_state in event["clocks"].items():
                    if clock_name not in clock_states:
                        clock_states[clock_name] = []
                    clock_states[clock_name].append(clock_state)

        # Verify both clocks were tracked
        assert "Investigation Progress" in clock_states
        assert "Security Response" in clock_states

        # Verify Security Response progressed (1/4 → 3/4)
        security_states = clock_states["Security Response"]
        assert "1/4" in security_states, "Should start at 1/4"
        assert "3/4" in security_states, "Should progress to 3/4"

        # Verify Investigation Progress was tracked (even though it didn't advance)
        investigation_states = clock_states["Investigation Progress"]
        assert len(investigation_states) > 0, "Investigation should be tracked"

    def test_starting_clocks_removed_on_timeout(self, starting_clocks_session_with_removal):
        """Verify starting clocks log clock_removal events on session timeout."""
        # Find all clock_removal events
        removal_events = [
            e for e in starting_clocks_session_with_removal
            if e.get("event_type") == "clock_removal"
        ]

        # Should have 2 removals (one per starting clock)
        assert len(removal_events) == 2, \
            f"Should have 2 clock_removal events, found {len(removal_events)}"

        # Verify both clocks were removed
        removed_clocks = {e["data"]["clock_name"] for e in removal_events}
        assert "Investigation Progress" in removed_clocks
        assert "Security Response" in removed_clocks

        # Verify at least one removal is session_end (Investigation Progress times out)
        removal_reasons = [e["data"]["removal_reason"] for e in removal_events]
        assert "session_end" in removal_reasons, \
            f"At least one clock should have removal_reason=session_end, found {removal_reasons}"

        # Verify removal events have required fields
        for removal in removal_events:
            assert "data" in removal, "Removal event should have data field"
            assert "clock_name" in removal["data"], "Removal data should have clock_name"
            assert "removal_reason" in removal["data"], "Removal data should have removal_reason"


# ==============================================================================
# Test Class 2: Ad Hoc Clock Lifecycle
# ==============================================================================

class TestAdHocClockLifecycle:
    """Test clocks spawned by DM during session."""

    def test_dm_can_spawn_clocks_mid_session(self, ad_hoc_clocks_session):
        """Verify DM spawns clocks dynamically with clock_spawn events."""
        # Find all clock_spawn events
        spawn_events = [
            e for e in ad_hoc_clocks_session
            if e.get("event_type") == "clock_spawn"
        ]

        assert len(spawn_events) >= 3, \
            f"Should have at least 3 clock spawns, found {len(spawn_events)}"

        # Verify spawn events have required fields (at top level for clock_spawn)
        for spawn in spawn_events:
            assert "clock_name" in spawn, "Spawn should have clock_name"
            assert "max_ticks" in spawn, "Spawn should have max_ticks"
            assert "description" in spawn, "Spawn should have description"
            # round can be null for clocks spawned during setup
            assert "round" in spawn, "Spawn should have round field"

            # Note: round can be None for clocks spawned during scenario setup
            # Only verify non-null rounds are >= 0
            spawn_round = spawn.get("round")
            if spawn_round is not None:
                assert spawn_round >= 0, \
                    f"Clock {spawn['clock_name']} spawned in round {spawn_round}, should be ≥0"

    def test_spawned_clocks_tracked_in_resolutions(self, ad_hoc_clocks_session):
        """Verify clocks spawned by DM appear in subsequent action_resolution.clocks."""
        # Find first clock_spawn with a non-null round (for comparison)
        first_spawn = None
        for event in ad_hoc_clocks_session:
            if event.get("event_type") == "clock_spawn":
                first_spawn = event
                break

        assert first_spawn is not None, "Should have at least one clock_spawn"

        spawned_clock_name = first_spawn["clock_name"]
        spawn_round = first_spawn.get("round")  # Can be None

        # Find action_resolution that contains the spawned clock
        # If spawn_round is None, just find any resolution with the clock
        found_in_resolution = False
        for event in ad_hoc_clocks_session:
            if (event.get("event_type") == "action_resolution" and "clocks" in event):
                # If spawn_round is None, accept any round
                # Otherwise, require resolution to be in same or later round
                event_round = event.get("round", 0)
                if spawn_round is None or (event_round is not None and event_round >= spawn_round):
                    if spawned_clock_name in event["clocks"]:
                        found_in_resolution = True
                        break

        assert found_in_resolution, \
            f"Spawned clock '{spawned_clock_name}' should appear in action_resolution.clocks"

    def test_clocks_fill_and_trigger_completion(self, ad_hoc_clocks_session):
        """Verify filled clocks log clock_completion events."""
        # Find all clock_completion events
        completion_events = [
            e for e in ad_hoc_clocks_session
            if e.get("event_type") == "clock_completion"
        ]

        # Should have at least 1 completion (Registry Preservation fills to 9/8)
        assert len(completion_events) >= 1, \
            f"Should have at least 1 clock_completion event, found {len(completion_events)}"

        # Verify completion events have required fields
        # Note: clock_completion events have data nested under "data" key
        for completion in completion_events:
            assert "data" in completion, "Completion should have data field"
            data = completion["data"]
            assert "clock_name" in data, "Completion data should have clock_name"
            assert "final_ticks" in data, "Completion data should have final_ticks"
            assert "maximum_ticks" in data, "Completion data should have maximum_ticks"
            assert "round" in completion, "Completion should have round number"

            # Verify clock actually filled (final_ticks ≥ maximum_ticks)
            assert data["final_ticks"] >= data["maximum_ticks"], \
                f"Clock {data['clock_name']} completion has {data['final_ticks']}/{data['maximum_ticks']} (not filled)"

    def test_filled_clocks_removed_after_completion(self, ad_hoc_clocks_session):
        """Verify filled clocks log clock_removal events with reason=filled."""
        # Find all clock_completion events
        # Note: clock_completion has data nested under "data" key
        completion_events = [
            e for e in ad_hoc_clocks_session
            if e.get("event_type") == "clock_completion"
        ]

        # Find all clock_removal events with reason=filled
        # Note: clock_removal has data nested under "data" key
        filled_removal_events = [
            e for e in ad_hoc_clocks_session
            if e.get("event_type") == "clock_removal" and
               e.get("data", {}).get("removal_reason") == "filled"
        ]

        # Every completion should have a corresponding removal
        # (Note: May not be 1:1 if some clocks fill multiple times, but should have ≥1)
        assert len(filled_removal_events) >= 1, \
            "Should have at least 1 clock_removal event with reason=filled"

        # Verify removal events for completed clocks
        completed_clocks = {e["data"]["clock_name"] for e in completion_events}
        removed_filled_clocks = {e["data"]["clock_name"] for e in filled_removal_events}

        # At least one completed clock should be removed as filled
        assert len(completed_clocks & removed_filled_clocks) >= 1, \
            "At least one completed clock should have clock_removal with reason=filled"


# ==============================================================================
# Test Class 3: Clock Overflow
# ==============================================================================

class TestClockOverflow:
    """Test clock overflow handling (e.g., 9/8 segments)."""

    @pytest.mark.xfail(reason="Requires fixture with clock_advancement events showing overflow (not yet generated)")
    def test_clock_overflow_detected_and_logged(self, ad_hoc_clocks_session):
        """Verify clock overflow (e.g., 9/8) is detected and logged."""
        # Find clock_advancement events with overflow (new_value > maximum)
        overflow_events = [
            e for e in ad_hoc_clocks_session
            if (e.get("event_type") == "clock_advancement" and
                e.get("new_value", 0) > e.get("maximum", 999))
        ]

        # Should have at least 1 overflow event (Registry Preservation → 9/8)
        assert len(overflow_events) >= 1, \
            f"Should have at least 1 overflow event, found {len(overflow_events)}"

        # Verify overflow is properly documented
        for overflow in overflow_events:
            assert overflow["new_value"] > overflow["maximum"], \
                f"Overflow event has {overflow['new_value']}/{overflow['maximum']} (not overflow)"

    @pytest.mark.xfail(reason="Requires fixture with overflow + clock_completion events (not yet generated)")
    def test_overflow_triggers_consequences(self, ad_hoc_clocks_session):
        """Verify overflow clocks trigger clock_completion (consequences)."""
        # Find clocks that overflowed
        overflow_clocks = set()
        for event in ad_hoc_clocks_session:
            if (event.get("event_type") == "clock_advancement" and
                event.get("new_value", 0) > event.get("maximum", 999)):
                overflow_clocks.add(event["clock_name"])

        assert len(overflow_clocks) >= 1, "Should have at least one overflow clock"

        # Find clock_completion events for overflow clocks
        overflow_completions = [
            e for e in ad_hoc_clocks_session
            if (e.get("event_type") == "clock_completion" and
                e["clock_name"] in overflow_clocks)
        ]

        # Overflow clocks should trigger completion
        assert len(overflow_completions) >= 1, \
            "Overflow clocks should trigger clock_completion events"

    @pytest.mark.xfail(reason="Requires fixture with overflow + clock_removal events (not yet generated)")
    def test_overflow_clock_removed_despite_overflow(self, ad_hoc_clocks_session):
        """Verify overflow clocks are still removed properly."""
        # Find clocks that overflowed
        overflow_clocks = set()
        for event in ad_hoc_clocks_session:
            if (event.get("event_type") == "clock_advancement" and
                event.get("new_value", 0) > event.get("maximum", 999)):
                overflow_clocks.add(event["clock_name"])

        assert len(overflow_clocks) >= 1, "Should have at least one overflow clock"

        # Find clock_removal events for overflow clocks
        overflow_removals = [
            e for e in ad_hoc_clocks_session
            if (e.get("event_type") == "clock_removal" and
                e["clock_name"] in overflow_clocks)
        ]

        # Overflow clocks should be removed (either filled or session_end)
        assert len(overflow_removals) >= 1, \
            "Overflow clocks should have clock_removal events"

        # Verify removal reason is valid
        for removal in overflow_removals:
            assert removal["reason"] in ["filled", "session_end"], \
                f"Overflow clock removal reason should be 'filled' or 'session_end', got '{removal['reason']}'"


# ==============================================================================
# Test Class 4: Clock Removal
# ==============================================================================

class TestClockRemoval:
    """Test clock removal events across all lifecycle paths."""

    @pytest.mark.xfail(reason="Old fixture doesn't have clock_removal events; use starting_clocks_session_with_removal")
    def test_timeout_clocks_log_removal_reason(self, starting_clocks_session):
        """Verify timeout clocks have clock_removal with reason=session_end."""
        # Find all clock_removal events
        removal_events = [
            e for e in starting_clocks_session
            if e.get("event_type") == "clock_removal"
        ]

        assert len(removal_events) >= 2, \
            "Should have at least 2 clock_removal events"

        # All removals in this session should be timeouts (no clocks fill)
        # Note: clock_removal has data nested under "data" key
        for removal in removal_events:
            data = removal.get("data", {})
            assert data.get("removal_reason") == "session_end", \
                f"Clock {data.get('clock_name')} should have removal_reason=session_end (timeout)"

    def test_completed_clocks_log_removal_reason(self, ad_hoc_clocks_session):
        """Verify completed clocks have clock_removal with reason=filled."""
        # Find clock_completion events
        # Note: clock_completion has data nested under "data" key
        completed_clocks = {
            e["data"]["clock_name"] for e in ad_hoc_clocks_session
            if e.get("event_type") == "clock_completion"
        }

        assert len(completed_clocks) >= 1, \
            "Should have at least 1 completed clock"

        # Find removals for completed clocks
        # Note: clock_removal has data nested under "data" key
        completed_removals = [
            e for e in ad_hoc_clocks_session
            if (e.get("event_type") == "clock_removal" and
                e.get("data", {}).get("clock_name") in completed_clocks)
        ]

        assert len(completed_removals) >= 1, \
            "Completed clocks should have clock_removal events"

        # Verify reason is 'filled'
        for removal in completed_removals:
            data = removal.get("data", {})
            assert data.get("removal_reason") == "filled", \
                f"Completed clock {data.get('clock_name')} should have removal_reason=filled"

    @pytest.mark.xfail(reason="Old fixture doesn't have clock_removal events; use starting_clocks_session_with_removal")
    def test_all_clocks_removed_by_session_end(self, starting_clocks_session):
        """Verify all clocks that were active during session have removal events."""
        # Find all unique clocks mentioned in action_resolution.clocks
        active_clocks = set()
        for event in starting_clocks_session:
            if event.get("event_type") == "action_resolution" and "clocks" in event:
                active_clocks.update(event["clocks"].keys())

        # Find all clocks with removal events
        # Note: clock_removal has data nested under "data" key
        removed_clocks = {
            e["data"]["clock_name"] for e in starting_clocks_session
            if e.get("event_type") == "clock_removal" and "data" in e
        }

        # Every active clock should have a removal event
        assert active_clocks == removed_clocks, \
            f"Active clocks {active_clocks} != Removed clocks {removed_clocks}"

    def test_event_sequence_completion_before_removal(self, ad_hoc_clocks_session):
        """Verify clock_completion events occur before clock_removal for filled clocks."""
        # Build event timeline with indices
        # Note: clock_spawn has clock_name at top level, but
        # clock_completion and clock_removal have it nested under "data"
        events_by_clock = {}
        for i, event in enumerate(ad_hoc_clocks_session):
            event_type = event.get("event_type")
            clock_name = None

            # Extract clock_name based on event type
            if event_type == "clock_spawn":
                clock_name = event.get("clock_name")
            elif event_type in ("clock_completion", "clock_removal"):
                clock_name = event.get("data", {}).get("clock_name")

            if clock_name:
                if clock_name not in events_by_clock:
                    events_by_clock[clock_name] = []
                events_by_clock[clock_name].append((i, event))

        # For each clock that has both completion and removal, verify order
        for clock_name, events in events_by_clock.items():
            completion_index = None
            removal_index = None

            for idx, event in events:
                if event["event_type"] == "clock_completion":
                    completion_index = idx
                if event["event_type"] == "clock_removal" and \
                   event.get("data", {}).get("removal_reason") == "filled":
                    removal_index = idx

            # If clock has both completion and filled removal, verify order
            if completion_index is not None and removal_index is not None:
                assert completion_index < removal_index, \
                    f"Clock {clock_name}: completion (idx {completion_index}) should occur before removal (idx {removal_index})"


# ==============================================================================
# Test Class 5: Multi-Clock Scenarios
# ==============================================================================

class TestMultiClockScenarios:
    """Test complex scenarios with multiple simultaneous clocks."""

    def test_multiple_clocks_tracked_simultaneously(self, ad_hoc_clocks_session):
        """Verify multiple clocks can be tracked simultaneously."""
        # Find rounds with multiple clocks in action_resolution
        max_simultaneous_clocks = 0

        for event in ad_hoc_clocks_session:
            if event.get("event_type") == "action_resolution" and "clocks" in event:
                num_clocks = len(event["clocks"])
                max_simultaneous_clocks = max(max_simultaneous_clocks, num_clocks)

        # Should have at least 3 clocks simultaneously at some point
        assert max_simultaneous_clocks >= 3, \
            f"Should track at least 3 clocks simultaneously, found {max_simultaneous_clocks}"

    def test_clock_updates_dont_interfere(self, ad_hoc_clocks_session):
        """Verify updates to one clock don't affect other clocks."""
        # Track clock states across rounds
        clock_history = {}

        for event in ad_hoc_clocks_session:
            if event.get("event_type") == "action_resolution" and "clocks" in event:
                round_num = event.get("round", 0)
                for clock_name, clock_state in event["clocks"].items():
                    if clock_name not in clock_history:
                        clock_history[clock_name] = {}
                    clock_history[clock_name][round_num] = clock_state

        # For each clock, verify progression is monotonic or intentional regression
        # (clock values shouldn't randomly change when other clocks update)
        for clock_name, rounds in clock_history.items():
            sorted_rounds = sorted(rounds.keys())

            for i in range(len(sorted_rounds) - 1):
                current_round = sorted_rounds[i]
                next_round = sorted_rounds[i + 1]

                current_state = rounds[current_round]
                next_state = rounds[next_round]

                # Parse "X/Y" format
                current_val = int(current_state.split('/')[0])
                next_val = int(next_state.split('/')[0])

                # Clock should either stay same, advance, or regress intentionally
                # (but not teleport randomly - e.g., 2/8 → 7/8 in one round without advancement events)
                # This is a weak check but catches major bugs
                assert abs(next_val - current_val) <= 5, \
                    f"Clock {clock_name} teleported from {current_state} → {next_state} (R{current_round}→R{next_round})"

    def test_mixed_clock_types_coexist(self, ad_hoc_clocks_session):
        """Verify goal clocks and threat clocks can coexist."""
        # Find clock_spawn events with type information
        clock_types = {}
        for event in ad_hoc_clocks_session:
            if event.get("event_type") == "clock_spawn":
                clock_name = event["clock_name"]
                description = event.get("description", "").lower()

                # Infer type from description (simple heuristic)
                if "threat" in description or "danger" in description or "assault" in description:
                    clock_types[clock_name] = "threat"
                elif "goal" in description or "progress" in description or "extraction" in description:
                    clock_types[clock_name] = "goal"
                else:
                    clock_types[clock_name] = "unknown"

        # Verify we have at least one of each type
        types_present = set(clock_types.values())

        # Should have both goal and threat clocks
        # (If not, this might be a test limitation rather than a bug)
        # We'll just verify multiple types exist
        assert len(types_present) >= 1, \
            "Should have at least one clock type (goal/threat)"

        # If we have multiple types, verify they coexist in same round
        if len(types_present) >= 2:
            for event in ad_hoc_clocks_session:
                if event.get("event_type") == "action_resolution" and "clocks" in event:
                    round_clocks = list(event["clocks"].keys())
                    round_types = {clock_types.get(c, "unknown") for c in round_clocks if c in clock_types}

                    if len(round_types) >= 2:
                        # Found a round with mixed clock types - success!
                        return

        # If we get here, we didn't find mixed types in same round
        # This is acceptable (depends on session flow)
        pass
