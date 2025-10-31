"""
Unit tests for JSONL log validation.

Tests reading and validating JSONL event logs:
- Event structure validation
- Required fields
- Event type consistency
- Timestamp ordering
- Session ID consistency
- Token tracking
- Round progression
"""

import pytest
import json
from pathlib import Path
from datetime import datetime


# ============================================================================
# JSONL Loading Tests
# ============================================================================

class TestJSONLLoading:
    """Test loading and parsing JSONL files."""

    def test_load_combat_session_jsonl(self):
        """Test loading the real combat session JSONL."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"

        assert jsonl_path.exists(), f"Combat JSONL not found at {jsonl_path}"

        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    event = json.loads(line)
                    events.append(event)

        assert len(events) > 0, "No events loaded"
        assert len(events) == 44, f"Expected 44 events, got {len(events)}"

    def test_all_lines_valid_json(self):
        """Test all lines are valid JSON."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"

        with open(jsonl_path, 'r') as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        pytest.fail(f"Line {i} is not valid JSON: {e}")


# ============================================================================
# Event Structure Tests
# ============================================================================

class TestEventStructure:
    """Test event structure and required fields."""

    @pytest.fixture
    def combat_events(self):
        """Load combat session events."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_all_events_have_event_type(self, combat_events):
        """Test all events have event_type field."""
        for i, event in enumerate(combat_events):
            assert 'event_type' in event, f"Event {i} missing event_type"
            assert event['event_type'], f"Event {i} has empty event_type"

    def test_all_events_have_timestamp(self, combat_events):
        """Test all events have timestamp."""
        for i, event in enumerate(combat_events):
            assert 'ts' in event, f"Event {i} missing timestamp"

    def test_all_events_have_session_id(self, combat_events):
        """Test all events have session ID."""
        for i, event in enumerate(combat_events):
            assert 'session' in event, f"Event {i} missing session ID"

    def test_session_id_consistent(self, combat_events):
        """Test session ID is consistent across all events."""
        session_ids = {event.get('session') for event in combat_events}

        assert len(session_ids) == 1, f"Multiple session IDs found: {session_ids}"

    def test_timestamps_parseable(self, combat_events):
        """Test timestamps are valid ISO format."""
        for i, event in enumerate(combat_events):
            ts_str = event.get('ts')
            try:
                datetime.fromisoformat(ts_str)
            except (ValueError, TypeError) as e:
                pytest.fail(f"Event {i} has invalid timestamp '{ts_str}': {e}")

    def test_timestamps_monotonic(self, combat_events):
        """Test timestamps generally increase (allowing some tolerance)."""
        previous_ts = None

        for event in combat_events:
            ts = datetime.fromisoformat(event['ts'])

            if previous_ts is not None:
                # Allow minor out-of-order (within 5 seconds)
                # Due to async operations and parallel processing, perfect ordering not guaranteed
                assert (ts - previous_ts).total_seconds() >= -5.0, \
                    f"Timestamp decreased too much: {previous_ts} -> {ts}"

            previous_ts = ts


# ============================================================================
# Event Type Tests
# ============================================================================

class TestEventTypes:
    """Test event type categorization and content."""

    @pytest.fixture
    def combat_events(self):
        """Load combat session events."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_session_start_event(self, combat_events):
        """Test session_start event structure."""
        start_event = combat_events[0]

        assert start_event['event_type'] == 'session_start'
        assert 'config' in start_event
        assert isinstance(start_event['config'], dict)

    def test_llm_call_events(self, combat_events):
        """Test llm_call events have required fields."""
        llm_events = [e for e in combat_events if e.get('event_type') == 'llm_call']

        assert len(llm_events) > 0, "No LLM call events found"

        for event in llm_events:
            assert 'agent_id' in event or 'agent_type' in event, "LLM call missing agent info"
            assert 'response' in event, "LLM call missing response"
            assert 'model' in event, "LLM call missing model"
            assert 'tokens' in event, "LLM call missing token count"

    def test_action_declaration_events(self, combat_events):
        """Test action_declaration events."""
        action_decls = [e for e in combat_events if e.get('event_type') == 'action_declaration']

        assert len(action_decls) > 0, "No action declarations found"

        for event in action_decls:
            assert 'agent_id' in event or 'character' in event or 'agent' in event, "Missing character info"
            assert 'action' in event or 'declaration' in event, "Missing action content"

    def test_action_resolution_events(self, combat_events):
        """Test action_resolution events."""
        resolutions = [e for e in combat_events if e.get('event_type') == 'action_resolution']

        assert len(resolutions) > 0, "No action resolutions found"

        for event in resolutions:
            assert 'character' in event or 'agent_id' in event or 'agent' in event, "Missing character info"

    def test_round_events(self, combat_events):
        """Test round progression events."""
        round_events = [e for e in combat_events if 'round' in e.get('event_type', '')]

        assert len(round_events) > 0, "No round events found"

    def test_enemy_spawn_events(self, combat_events):
        """Test enemy_spawn events."""
        enemy_events = [e for e in combat_events if e.get('event_type') == 'enemy_spawn']

        # Combat session should have enemies
        assert len(enemy_events) > 0, "No enemy spawn events in combat session"

        for event in enemy_events:
            assert 'enemy' in event or 'enemies' in event or 'enemy_id' in event or 'enemy_name' in event, \
                "Enemy event missing enemy data"


# ============================================================================
# Token Tracking Tests
# ============================================================================

class TestTokenTracking:
    """Test token usage is tracked correctly."""

    @pytest.fixture
    def combat_events(self):
        """Load combat session events."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_llm_calls_have_token_counts(self, combat_events):
        """Test LLM calls track token usage."""
        llm_events = [e for e in combat_events if e.get('event_type') == 'llm_call']

        for event in llm_events:
            assert 'tokens' in event, "LLM call missing token data"
            tokens = event['tokens']

            assert 'input' in tokens or 'input_tokens' in tokens, "Missing input tokens"
            assert 'output' in tokens or 'output_tokens' in tokens, "Missing output tokens"

    def test_token_counts_are_positive(self, combat_events):
        """Test token counts are positive numbers."""
        llm_events = [e for e in combat_events if e.get('event_type') == 'llm_call']

        for event in llm_events:
            tokens = event['tokens']

            input_tokens = tokens.get('input') or tokens.get('input_tokens', 0)
            output_tokens = tokens.get('output') or tokens.get('output_tokens', 0)

            assert input_tokens >= 0, f"Negative input tokens: {input_tokens}"
            assert output_tokens >= 0, f"Negative output tokens: {output_tokens}"

    def test_total_token_usage(self, combat_events):
        """Test we can calculate total token usage."""
        llm_events = [e for e in combat_events if e.get('event_type') == 'llm_call']

        total_input = 0
        total_output = 0

        for event in llm_events:
            tokens = event['tokens']
            input_tokens = tokens.get('input') or tokens.get('input_tokens', 0)
            output_tokens = tokens.get('output') or tokens.get('output_tokens', 0)

            total_input += input_tokens
            total_output += output_tokens

        # Sanity check - should have used some tokens
        assert total_input > 0, "No input tokens recorded"
        assert total_output > 0, "No output tokens recorded"


# ============================================================================
# Round Progression Tests
# ============================================================================

class TestRoundProgression:
    """Test round numbering and progression."""

    @pytest.fixture
    def combat_events(self):
        """Load combat session events."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_rounds_start_at_one_or_zero(self, combat_events):
        """Test first round number is 0 or 1."""
        round_events = [e for e in combat_events if 'round' in e]

        if round_events:
            first_round = round_events[0]['round']
            assert first_round in [0, 1], f"First round is {first_round}, expected 0 or 1"

    def test_round_numbers_sequential(self, combat_events):
        """Test round numbers increase sequentially."""
        round_events = [e for e in combat_events if 'round' in e and isinstance(e.get('round'), int)]

        if len(round_events) < 2:
            pytest.skip("Not enough round events to test progression")

        previous_round = None

        for event in round_events:
            current_round = event['round']

            if previous_round is not None:
                # Round should be same or increment by 1
                assert current_round in [previous_round, previous_round + 1], \
                    f"Round jumped from {previous_round} to {current_round}"

            previous_round = current_round

    def test_round_start_events(self, combat_events):
        """Test round_start events mark new rounds."""
        round_starts = [e for e in combat_events if e.get('event_type') == 'round_start']

        # Should have at least one round start
        assert len(round_starts) >= 1, "No round_start events found"

        for event in round_starts:
            assert 'round' in event, "round_start missing round number"


# ============================================================================
# Integration Tests
# ============================================================================

class TestJSONLIntegration:
    """Test complete JSONL file integrity."""

    @pytest.fixture
    def combat_events(self):
        """Load combat session events."""
        jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
        events = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def test_session_lifecycle(self, combat_events):
        """Test session has start event."""
        event_types = [e.get('event_type') for e in combat_events]

        assert 'session_start' in event_types, "No session_start event"
        assert event_types[0] == 'session_start', "session_start not first event"

    def test_combat_flow(self, combat_events):
        """Test combat session has expected flow."""
        event_types = [e.get('event_type') for e in combat_events]

        # Should have combat-related events
        assert 'enemy_spawn' in event_types, "Combat session missing enemy_spawn"
        assert 'action_declaration' in event_types, "No action declarations"
        assert 'action_resolution' in event_types, "No action resolutions"

    def test_event_type_distribution(self, combat_events):
        """Test reasonable distribution of event types."""
        from collections import Counter

        event_types = [e.get('event_type') for e in combat_events]
        type_counts = Counter(event_types)

        # Should have multiple of each key event type
        assert type_counts.get('llm_call', 0) >= 5, "Too few LLM calls"
        assert type_counts.get('action_declaration', 0) >= 2, "Too few declarations"

    def test_no_malformed_events(self, combat_events):
        """Test no events are severely malformed."""
        required_fields = ['event_type', 'ts', 'session']

        for i, event in enumerate(combat_events):
            for field in required_fields:
                assert field in event, f"Event {i} missing required field '{field}'"
                assert event[field], f"Event {i} has empty '{field}'"


# ============================================================================
# Utility Functions
# ============================================================================

def get_events_by_type(events: list, event_type: str) -> list:
    """Helper to filter events by type."""
    return [e for e in events if e.get('event_type') == event_type]


def get_event_timeline(events: list) -> list:
    """Helper to get ordered event types."""
    return [e.get('event_type') for e in events]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
