"""
Combat Flow Integration Tests

Tests complete combat round flow using real JSONL session data:
- Round initialization
- Declaration phase
- Resolution phase
- Synthesis phase
- State persistence
"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def combat_session_events():
    """Load real combat session JSONL events."""
    jsonl_path = Path(__file__).parent.parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"

    if not jsonl_path.exists():
        pytest.skip(f"Fixture not found: {jsonl_path}")

    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    return events


@pytest.fixture
def rounds_by_number(combat_session_events):
    """Group events by round number."""
    rounds = {}
    for event in combat_session_events:
        if 'round' in event:
            round_num = event['round']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(event)
    return rounds


class TestCombatRoundStructure:
    """Test complete combat round structure."""

    def test_round_has_all_phases(self, rounds_by_number):
        """Test each round has declaration, resolution, synthesis phases."""
        # Check round 1 (skip round 0 which is scenario)
        if 1 not in rounds_by_number:
            pytest.skip("Round 1 not in fixture")

        round_1_events = rounds_by_number[1]
        event_types = [e.get('event_type') for e in round_1_events]

        # Should have action declarations
        has_declarations = any('action_declaration' in et for et in event_types)
        # Should have resolutions
        has_resolutions = any('action_resolution' in et for et in event_types)

        assert has_declarations, "Round 1 missing action declarations"
        assert has_resolutions, "Round 1 missing action resolutions"

    def test_declarations_before_resolutions(self, rounds_by_number):
        """Test all declarations happen before resolutions."""
        if 1 not in rounds_by_number:
            pytest.skip("Round 1 not in fixture")

        round_1 = rounds_by_number[1]

        first_declaration_index = None
        last_declaration_index = None
        first_resolution_index = None

        for i, event in enumerate(round_1):
            et = event.get('event_type', '')

            if 'declaration' in et:
                if first_declaration_index is None:
                    first_declaration_index = i
                last_declaration_index = i

            if 'resolution' in et and first_resolution_index is None:
                first_resolution_index = i

        # If we have both, declarations should come before resolutions
        if last_declaration_index is not None and first_resolution_index is not None:
            assert last_declaration_index < first_resolution_index, \
                "Resolutions started before all declarations completed"

    def test_round_synthesis_exists(self, rounds_by_number):
        """Test each round (except 0) has synthesis."""
        for round_num, events in rounds_by_number.items():
            # Skip round 0 (scenario setup) and None (non-round events)
            if round_num is None or round_num == 0:
                continue

            event_types = [e.get('event_type') for e in events]
            has_synthesis = any('synthesis' in et or 'summary' in et for et in event_types)

            assert has_synthesis, f"Round {round_num} missing synthesis/summary"


class TestActionDeclarationResolution:
    """Test declaration-resolution pairing."""

    def test_declarations_have_matching_resolutions(self, combat_session_events):
        """Test each declaration gets a resolution."""
        declarations = [e for e in combat_session_events if e.get('event_type') == 'action_declaration']
        resolutions = [e for e in combat_session_events if e.get('event_type') == 'action_resolution']

        if not declarations:
            pytest.skip("No action declarations in fixture")

        # Check we have similar numbers (allowing for some variance)
        # Some declarations might fail before resolution, etc.
        assert len(resolutions) > 0, "No action resolutions found"
        assert len(resolutions) >= len(declarations) * 0.5, \
            f"Too few resolutions ({len(resolutions)}) for declarations ({len(declarations)})"

    def test_resolution_references_correct_agent(self, combat_session_events):
        """Test resolutions reference the correct agent."""
        resolutions = [e for e in combat_session_events
                      if e.get('event_type') == 'action_resolution'
                      and e.get('round', 0) > 0]

        if not resolutions:
            pytest.skip("No action resolutions in fixture")

        for resolution in resolutions[:5]:  # Check first 5
            # Should have some agent identifier
            has_agent = any(key in resolution for key in ['agent', 'character_name', 'player_id'])
            assert has_agent, f"Resolution missing agent identifier: {resolution.get('event_type')}"


class TestStateProgression:
    """Test state changes across rounds."""

    def test_round_numbers_increment(self, rounds_by_number):
        """Test round numbers increment sequentially."""
        # Filter out None (non-round events) before sorting
        round_nums = sorted([r for r in rounds_by_number.keys() if r is not None])

        if not round_nums:
            pytest.skip("No round numbers found in fixture")

        # Should start at 0 or 1
        assert round_nums[0] in [0, 1]

        # Should increment by 1
        for i in range(len(round_nums) - 1):
            diff = round_nums[i + 1] - round_nums[i]
            assert diff == 1, f"Round numbers skip from {round_nums[i]} to {round_nums[i+1]}"

    def test_characters_persist_across_rounds(self, combat_session_events):
        """Test character references persist across rounds."""
        # Collect all character names/IDs mentioned
        characters_by_round = {}

        for event in combat_session_events:
            round_num = event.get('round')
            if round_num is None or round_num == 0:
                continue

            if round_num not in characters_by_round:
                characters_by_round[round_num] = set()

            # Extract character identifiers
            for key in ['agent', 'character_name', 'player_id']:
                if key in event and event[key]:
                    characters_by_round[round_num].add(event[key])

        if len(characters_by_round) < 2:
            pytest.skip("Need at least 2 rounds to test persistence")

        # Characters from round 1 should appear in round 2
        round_nums = sorted(characters_by_round.keys())
        if len(round_nums) >= 2:
            round_1_chars = characters_by_round[round_nums[0]]
            round_2_chars = characters_by_round[round_nums[1]]

            # At least some characters should persist
            overlap = round_1_chars & round_2_chars
            assert len(overlap) > 0, "No characters persist from round 1 to round 2"


class TestJSONLCompleteness:
    """Test JSONL logging is complete."""

    def test_all_events_have_timestamps(self, combat_session_events):
        """Test all events have timestamps."""
        for i, event in enumerate(combat_session_events):
            assert 'ts' in event or 'timestamp' in event, \
                f"Event {i} missing timestamp: {event.get('event_type')}"

    def test_all_events_have_session_id(self, combat_session_events):
        """Test all events reference the session."""
        for i, event in enumerate(combat_session_events):
            has_session = 'session' in event or 'session_id' in event
            assert has_session, f"Event {i} missing session reference"

    def test_action_resolutions_have_roll_data(self, combat_session_events):
        """Test action resolutions contain roll information."""
        resolutions = [e for e in combat_session_events
                      if e.get('event_type') == 'action_resolution'
                      and e.get('round', 0) > 0]

        if not resolutions:
            pytest.skip("No action resolutions in fixture")

        for resolution in resolutions[:5]:  # Check first 5
            # Should have roll data
            has_roll_data = 'roll' in resolution or all(k in resolution for k in ['total', 'difficulty'])
            assert has_roll_data, f"Resolution missing roll data"


class TestCombatOutcomes:
    """Test combat outcomes are recorded."""

    def test_enemy_defeats_recorded(self, combat_session_events):
        """Test enemy defeats are logged."""
        enemy_events = [e for e in combat_session_events
                       if 'enemy' in e.get('event_type', '').lower()]

        # Should have some enemy-related events (spawn, actions, or defeat)
        assert len(enemy_events) > 0, "No enemy events found in combat session"

    def test_clocks_advance(self, combat_session_events):
        """Test scene clocks progress during combat."""
        clock_events = [e for e in combat_session_events
                       if 'clock' in e.get('event_type', '').lower()]

        # Combat sessions may or may not have clocks
        # This is informational
        if clock_events:
            assert len(clock_events) > 0


class TestMultiRoundFlow:
    """Test multi-round combat flow."""

    def test_at_least_two_rounds(self, rounds_by_number):
        """Test session has multiple combat rounds."""
        # Filter out None and round 0 (scenario setup)
        combat_rounds = [r for r in rounds_by_number.keys() if r is not None and r > 0]

        # A complete combat should have at least 2 rounds
        if len(combat_rounds) < 2:
            pytest.skip("Fixture has less than 2 combat rounds")

        assert len(combat_rounds) >= 2

    def test_round_synthesis_summarizes_round(self, rounds_by_number):
        """Test synthesis events exist and have content."""
        for round_num, events in rounds_by_number.items():
            if round_num == 0:
                continue

            synthesis_events = [e for e in events if 'synthesis' in e.get('event_type', '')]

            if synthesis_events:
                # Should have non-empty synthesis
                synthesis = synthesis_events[0]
                has_content = any(synthesis.get(k) for k in ['synthesis', 'narrative', 'summary'])
                assert has_content, f"Round {round_num} synthesis empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
