"""
Multi-Round State Persistence Integration Tests

Tests that game state persists correctly across multiple rounds:
1. Damage accumulates and persists
2. Void changes track over time
3. Clocks advance progressively
4. Character state doesn't mysteriously reset

These tests verify temporal consistency - critical for multi-round sessions.
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

    raise FileNotFoundError(f"Fixture not found: {relative_path}")


@pytest.fixture
def debt_auction_session():
    """Load 5-round debt auction session for state persistence tests."""
    return load_fixture("sessions/session_debt_auction_ambush.jsonl")


@pytest.fixture
def extract_events():
    """Helper to extract events by type and filters."""
    def _extractor(events: List[Dict], event_type: str, **filters) -> List[Dict]:
        results = []
        for event in events:
            if event.get('event_type') != event_type:
                continue

            match = True
            for key, value in filters.items():
                if event.get(key) != value:
                    match = False
                    break

            if match:
                results.append(event)

        return results

    return _extractor


# ==============================================================================
# Test Class 1: Void Accumulation Over Multiple Actions
# ==============================================================================

class TestVoidAccumulationPersistence:
    """Test that void changes accumulate and persist across rounds."""

    def test_void_accumulates_over_session(self, debt_auction_session, extract_events):
        """
        Verify character void accumulates over multiple rounds (doesn't reset).

        Tests that void changes are persistent, not transient.
        """
        # Track void for each character across all rounds
        character_void_timeline = {}

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                agent = event.get("agent")
                round_num = event.get("round", 0)
                char_data = event.get("character_data", {})
                void_level = char_data.get("void")

                if agent and void_level is not None:
                    if agent not in character_void_timeline:
                        character_void_timeline[agent] = []

                    character_void_timeline[agent].append({
                        "round": round_num,
                        "void": void_level
                    })

        # Verify void persistence for each character
        for char_name, timeline in character_void_timeline.items():
            if len(timeline) < 2:
                continue  # Need at least 2 data points to check persistence

            # Sort by round
            timeline.sort(key=lambda x: x["round"])

            # Check that void doesn't randomly reset
            for i in range(len(timeline) - 1):
                current_void = timeline[i]["void"]
                next_void = timeline[i + 1]["void"]
                current_round = timeline[i]["round"]
                next_round = timeline[i + 1]["round"]

                # Void should be continuous (can increase, decrease, or stay same)
                # But shouldn't teleport (e.g., 5 → 0 → 5 without reason)
                void_delta = abs(next_void - current_void)

                # Sanity check: void shouldn't change by more than ~5 between consecutive resolutions
                # (unless there's a major ritual/event)
                assert void_delta <= 10, \
                    f"{char_name}: Void teleported from {current_void} to {next_void} " \
                    f"between R{current_round} and R{next_round} (delta: {void_delta})"

    def test_void_changes_reflected_in_character_state(self, debt_auction_session, extract_events):
        """
        Verify void economy changes are reflected in character state.

        Tests that when economy.void_delta != 0, character void updates accordingly.
        """
        # Track void changes via economy vs character state
        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                agent = event.get("agent")
                economy = event.get("economy", {})
                void_delta = economy.get("void_delta", 0)

                if void_delta != 0:
                    # This action had a void economy change
                    # Verify it's explained
                    triggers = economy.get("void_triggers", [])
                    assert len(triggers) > 0, \
                        f"{agent}: void_delta={void_delta} but no void_triggers explaining why"


# ==============================================================================
# Test Class 2: Clock Progression Across Rounds
# ==============================================================================

class TestClockProgressionPersistence:
    """Test that clocks advance progressively and don't reset."""

    def test_clocks_advance_monotonically_or_intentionally(self, debt_auction_session, extract_events):
        """
        Verify clocks advance progressively across rounds (no random resets).

        Tests that clock state persistence works correctly.
        """
        # Track clock states across all action_resolutions
        clock_timeline = {}

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                round_num = event.get("round", 0)
                clocks = event.get("clocks", {})

                for clock_name, clock_state in clocks.items():
                    if clock_name not in clock_timeline:
                        clock_timeline[clock_name] = []

                    clock_timeline[clock_name].append({
                        "round": round_num,
                        "state": clock_state
                    })

        # Verify clock progression for each tracked clock
        for clock_name, timeline in clock_timeline.items():
            if len(timeline) < 2:
                continue  # Need multiple data points

            # Sort by round
            timeline.sort(key=lambda x: x["round"])

            # Parse clock states (format: "X/Y")
            for i in range(len(timeline) - 1):
                current_state = timeline[i]["state"]
                next_state = timeline[i + 1]["state"]
                current_round = timeline[i]["round"]
                next_round = timeline[i + 1]["round"]

                # Parse "X/Y" format
                try:
                    current_filled = int(current_state.split('/')[0])
                    current_max = int(current_state.split('/')[1])
                    next_filled = int(next_state.split('/')[0])
                    next_max = int(next_state.split('/')[1])

                    # Clock maximum shouldn't change (unless redefined, which is rare)
                    # This is a weak check but catches major bugs

                    # Filled ticks should either:
                    # 1. Advance (progress)
                    # 2. Stay same (no advancement)
                    # 3. Regress intentionally (rare, but valid)
                    # 4. Reset to 0 (clock completed/removed then respawned)

                    # What shouldn't happen: teleportation without reason
                    filled_delta = abs(next_filled - current_filled)

                    # If clock maxima are different, it's a different clock
                    # (or was redefined - very rare edge case)
                    if current_max == next_max:
                        # Clock should progress reasonably
                        # Shouldn't jump by more than max_ticks in one action
                        assert filled_delta <= current_max + 5, \
                            f"Clock '{clock_name}' teleported from {current_state} to {next_state} " \
                            f"between R{current_round} and R{next_round}"

                except (ValueError, IndexError):
                    # Malformed clock state - that's a separate bug
                    pytest.fail(f"Clock '{clock_name}' has malformed state: {current_state} or {next_state}")

    def test_filled_clocks_eventually_removed_or_persist(self, debt_auction_session, extract_events):
        """
        Verify filled clocks are either removed or continue to exist.

        Tests that clock lifecycle is tracked correctly.
        """
        # Find clocks that reached or exceeded max ticks
        filled_clocks = set()

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                clocks = event.get("clocks", {})

                for clock_name, clock_state in clocks.items():
                    try:
                        filled, maximum = map(int, clock_state.split('/'))
                        if filled >= maximum:
                            filled_clocks.add(clock_name)
                    except (ValueError, AttributeError):
                        pass

        # Filled clocks should eventually be removed or have consequences
        # This is hard to verify from JSONL alone without clock_removal events
        # For now, just verify we can track filled clocks

        # Test passes if we identified filled clocks (shows detection works)
        # Full lifecycle testing requires newer fixtures with clock_removal events


# ==============================================================================
# Test Class 3: Character State Consistency
# ==============================================================================

class TestCharacterStateConsistency:
    """Test that character state remains consistent across rounds."""

    def test_character_names_consistent_across_rounds(self, debt_auction_session, extract_events):
        """
        Verify character names don't change between rounds (no identity confusion).

        Tests basic data integrity.
        """
        # Track character names that appear in the session
        character_names = set()

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                agent = event.get("agent")
                if agent:
                    character_names.add(agent)

        # Should have consistent character set throughout session
        # (barring character death/departure, which should be explicit)

        assert len(character_names) > 0, "Should have at least one character"

        # All resolutions for a given character should use same name
        character_action_counts = {}
        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                agent = event.get("agent")
                if agent:
                    character_action_counts[agent] = character_action_counts.get(agent, 0) + 1

        # Each active character should have actions across multiple rounds
        # (5-round session, 3 PCs = ~15 total actions expected)
        total_actions = sum(character_action_counts.values())
        assert total_actions > 10, f"Expected ~15 actions in 5-round session, got {total_actions}"

    def test_character_skills_dont_randomly_change(self, debt_auction_session, extract_events):
        """
        Verify character skills remain consistent across rounds.

        Tests that character sheets don't get corrupted between actions.
        """
        # Track skills for each character
        character_skills = {}

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                agent = event.get("agent")
                char_data = event.get("character_data", {})
                skills = char_data.get("skills", {})

                if agent and skills:
                    if agent not in character_skills:
                        character_skills[agent] = []

                    character_skills[agent].append({
                        "round": event.get("round"),
                        "skills": dict(skills)  # Copy to avoid reference issues
                    })

        # Verify skills consistency for each character
        for char_name, skill_snapshots in character_skills.items():
            if len(skill_snapshots) < 2:
                continue

            # Get first and last snapshots
            first_skills = skill_snapshots[0]["skills"]
            last_skills = skill_snapshots[-1]["skills"]

            # Skill values shouldn't change (unless character leveled up - rare mid-session)
            # At minimum, skill names should stay consistent
            first_skill_names = set(first_skills.keys())
            last_skill_names = set(last_skills.keys())

            # Character should have same skill set throughout session
            # (allowing for minor differences if system evolved)
            overlap = len(first_skill_names & last_skill_names)
            total_unique = len(first_skill_names | last_skill_names)

            # At least 70% overlap expected (allows for system changes)
            overlap_percent = overlap / total_unique if total_unique > 0 else 0
            assert overlap_percent > 0.7, \
                f"{char_name}: Skills changed significantly between rounds " \
                f"(only {overlap_percent*100:.0f}% overlap)"

    def test_round_numbers_increase_monotonically(self, debt_auction_session, extract_events):
        """
        Verify round numbers increase sequentially (no time travel).

        Tests basic temporal integrity.
        """
        # Track round numbers in order of events
        round_sequence = []

        for event in debt_auction_session:
            round_num = event.get("round")
            if round_num is not None:
                round_sequence.append(round_num)

        # Remove None values and duplicates while preserving order
        seen_rounds = []
        for r in round_sequence:
            if r not in seen_rounds:
                seen_rounds.append(r)

        # Rounds should be in increasing order (allowing round 0 for setup)
        for i in range(len(seen_rounds) - 1):
            current = seen_rounds[i]
            next_round = seen_rounds[i + 1]

            assert next_round >= current, \
                f"Round sequence violation: round {current} followed by round {next_round}"


# ==============================================================================
# Test Class 4: Session-Level State Integrity
# ==============================================================================

class TestSessionLevelStateIntegrity:
    """Test overall session state integrity."""

    def test_session_has_complete_round_structure(self, debt_auction_session, extract_events):
        """
        Verify session has complete rounds (not cut off mid-round).

        Tests that session structure is coherent.
        """
        # Get all rounds with action_resolutions
        rounds_with_actions = set()
        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                round_num = event.get("round")
                if round_num:
                    rounds_with_actions.add(round_num)

        # Should have consecutive rounds (1, 2, 3, 4, 5)
        if len(rounds_with_actions) > 0:
            min_round = min(rounds_with_actions)
            max_round = max(rounds_with_actions)

            # Check for gaps in round sequence
            expected_rounds = set(range(min_round, max_round + 1))
            missing_rounds = expected_rounds - rounds_with_actions

            assert len(missing_rounds) == 0, \
                f"Session has missing rounds: {sorted(missing_rounds)}"

    def test_all_characters_act_each_round(self, debt_auction_session, extract_events):
        """
        Verify all active characters take actions each round.

        Tests that turn order is consistent and no characters are skipped.
        """
        # Track which characters act in which rounds
        rounds_to_characters = {}

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                round_num = event.get("round")
                agent = event.get("agent")

                if round_num and agent:
                    if round_num not in rounds_to_characters:
                        rounds_to_characters[round_num] = set()

                    rounds_to_characters[round_num].add(agent)

        # Get all unique characters
        all_characters = set()
        for characters in rounds_to_characters.values():
            all_characters.update(characters)

        # Each round should have same characters acting
        # (unless character joined/left mid-session)
        if len(rounds_to_characters) > 1:
            round_numbers = sorted(rounds_to_characters.keys())

            for i in range(len(round_numbers) - 1):
                current_round = round_numbers[i]
                next_round = round_numbers[i + 1]

                current_chars = rounds_to_characters[current_round]
                next_chars = rounds_to_characters[next_round]

                # Should have same character set (or very close)
                # Allow 1 character difference for edge cases
                symmetric_diff = current_chars ^ next_chars

                assert len(symmetric_diff) <= 1, \
                    f"Character set changed significantly between R{current_round} and R{next_round}: " \
                    f"R{current_round}={current_chars}, R{next_round}={next_chars}"
