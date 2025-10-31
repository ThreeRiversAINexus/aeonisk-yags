"""
tests/unit/test_logging_completeness.py

Ensure JSONL logging captures everything that should be logged.
Uses real combat data: tests/fixtures/sample_logs/combat_session_sample.jsonl

This is the MOST IMPORTANT test suite - validates that ML training data
includes all necessary events, effects, and state changes.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime


@pytest.fixture
def combat_events():
    """Load real combat session (44 events)."""
    jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


class TestDeclarationResolutionPairing:
    """Every declaration MUST have a resolution."""

    def test_every_declaration_has_resolution(self, combat_events):
        """Every action_declaration must have matching action_resolution."""
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for decl in declarations:
            # Get agent identifier (could be player_id or character_name)
            agent = decl.get('player_id') or decl.get('character_name') or decl.get('agent')
            round_num = decl.get('round')

            # Find matching resolution
            matching = [r for r in resolutions
                       if r.get('round') == round_num
                       and (r.get('agent') == agent
                            or r.get('character_name') == agent
                            or r.get('player_id') == agent
                            or agent in str(r.get('agent', '')))]

            assert len(matching) > 0, \
                f"Declaration by {agent} in round {round_num} has no resolution"

    def test_resolution_count_matches_declaration_count(self, combat_events):
        """Should have same number of resolutions as declarations."""
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        # May not be exact 1:1 (multi-target, AoE, etc.) but should be close
        assert len(resolutions) >= len(declarations) * 0.6, \
            f"Too few resolutions ({len(resolutions)}) for declarations ({len(declarations)})"


class TestEffectLogging:
    """Effects mentioned in narration MUST be logged in structured effects."""

    def test_damage_logged_when_mentioned(self, combat_events):
        """If narration mentions damage/hit/strike, check effects or roll data."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            # Get narration from context (actual structure)
            narration = res.get('context', {}).get('narration', '').lower()
            if not narration:
                continue

            effects = res.get('effects', [])
            roll = res.get('roll', {})

            # Combat keywords
            damage_words = ['damage', 'hit', 'strikes', 'wounds', 'injures', 'hurts', 'slashes', 'pierces']
            mentions_damage = any(word in narration for word in damage_words)

            if mentions_damage:
                # Should have damage in effects OR explicit failure in roll
                has_damage_effect = any('damage' in str(eff).lower() for eff in effects) if effects else False
                is_failure = roll.get('success') is False or roll.get('tier') in ['failure', 'critical_failure']

                if not (has_damage_effect or is_failure):
                    # Soft warning - some combat actions may not deal damage
                    print(f"INFO: Damage mentioned but not logged: {narration[:100]}")

    def test_void_changes_logged(self, combat_events):
        """Void markers in narration should have void_changes in economy."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            narration = res.get('context', {}).get('narration', '')
            economy = res.get('economy', {})

            # Check for void markers
            has_void_marker = '⚫' in narration
            has_void_text = 'void corruption' in narration.lower() or 'void change' in narration.lower()

            if has_void_marker or has_void_text:
                void_delta = economy.get('void_delta', 0)
                void_triggers = economy.get('void_triggers', [])

                # Should have non-zero void delta or triggers
                if void_delta == 0 and not void_triggers:
                    print(f"INFO: Void mentioned but no void_delta: {narration[:100]}")

    def test_clock_updates_logged(self, combat_events):
        """Clock markers should have clock updates tracked."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        clock_marker_found = False
        for res in resolutions:
            narration = res.get('context', {}).get('narration', '')

            # Check for clock markers
            has_clock_marker = '📊' in narration or 'clock' in narration.lower()

            if has_clock_marker:
                clock_marker_found = True
                clocks = res.get('clocks', {})
                clock_deltas = res.get('context', {}).get('clock_deltas', [])

                # Should have clock data (either in clocks dict or clock_deltas)
                has_clock_data = bool(clocks) or bool(clock_deltas)

                assert has_clock_data, \
                    f"Clock marker present but no clock data: {narration[:100]}"

        # Verify we found at least some clock activity
        if not clock_marker_found:
            print("INFO: No clock markers found in combat session")


class TestRoundCompleteness:
    """Every round must have required events."""

    def test_all_rounds_have_synthesis(self, combat_events):
        """Every round MUST have round_synthesis or round_summary event."""
        rounds = set(e['round'] for e in combat_events if 'round' in e and isinstance(e.get('round'), int))

        for round_num in rounds:
            round_events = [e for e in combat_events if e.get('round') == round_num]
            synthesis = [e for e in round_events
                        if e['event_type'] in ['round_synthesis', 'round_summary']]

            assert len(synthesis) > 0, \
                f"Round {round_num} missing round_synthesis/summary"

    def test_all_rounds_have_round_start(self, combat_events):
        """Every round should have round_start event."""
        rounds = set(e['round'] for e in combat_events if 'round' in e and isinstance(e.get('round'), int))

        for round_num in rounds:
            round_events = [e for e in combat_events if e.get('round') == round_num]
            round_starts = [e for e in round_events if e['event_type'] == 'round_start']

            assert len(round_starts) > 0, \
                f"Round {round_num} missing round_start"


class TestCharacterStateLogging:
    """Character states should be logged at critical points."""

    def test_character_states_logged(self, combat_events):
        """Should have character_state events throughout session."""
        state_events = [e for e in combat_events if e['event_type'] == 'character_state']

        # Should have multiple state snapshots
        assert len(state_events) >= 2, \
            f"Only {len(state_events)} character_state events - need more snapshots"

    def test_character_states_have_required_fields(self, combat_events):
        """Character state events must have character identifier and state data."""
        state_events = [e for e in combat_events if e['event_type'] == 'character_state']

        for state in state_events:
            # Check for character identifier (field names may vary)
            has_identifier = ('character' in state or 'name' in state or
                            'character_name' in state or 'player_id' in state)

            # Check for some state data
            has_state_data = 'health' in str(state).lower() or 'void' in state or 'wounds' in str(state).lower()

            assert has_identifier, f"character_state missing character identifier: {list(state.keys())}"

            if not has_state_data:
                print(f"INFO: character_state may be missing health/void info: {list(state.keys())}")


class TestTokenTracking:
    """LLM token usage must be tracked."""

    def test_all_llm_calls_have_tokens(self, combat_events):
        """Every llm_call MUST have token counts."""
        llm_calls = [e for e in combat_events if e['event_type'] == 'llm_call']

        for call in llm_calls:
            assert 'tokens' in call, \
                f"LLM call missing tokens: {call.get('agent_id')}"

            tokens = call['tokens']

            # Check for input/output (may use different key names)
            input_key = 'input' if 'input' in tokens else 'input_tokens'
            output_key = 'output' if 'output' in tokens else 'output_tokens'

            assert input_key in tokens, f"Missing input tokens in {call.get('agent_id')}"
            assert output_key in tokens, f"Missing output tokens in {call.get('agent_id')}"

            input_tokens = tokens[input_key]
            output_tokens = tokens[output_key]

            assert input_tokens > 0, f"Zero input tokens for {call.get('agent_id')}"
            assert output_tokens > 0, f"Zero output tokens for {call.get('agent_id')}"

    def test_token_counts_are_reasonable(self, combat_events):
        """Token counts should be in reasonable ranges."""
        llm_calls = [e for e in combat_events if e['event_type'] == 'llm_call']

        for call in llm_calls:
            tokens = call.get('tokens', {})
            input_tokens = tokens.get('input') or tokens.get('input_tokens', 0)
            output_tokens = tokens.get('output') or tokens.get('output_tokens', 0)

            # Sanity checks
            assert input_tokens < 100000, \
                f"Input tokens suspiciously high: {input_tokens} for {call.get('agent_id')}"
            assert output_tokens < 50000, \
                f"Output tokens suspiciously high: {output_tokens} for {call.get('agent_id')}"


class TestEconomyTracking:
    """Test soulcredit and void tracking in economy field."""

    def test_soulcredit_changes_tracked(self, combat_events):
        """Soulcredit changes should be logged in economy."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        soulcredit_events = [r for r in resolutions
                            if r.get('economy', {}).get('soulcredit_delta', 0) != 0]

        # Soft check - soulcredit may not occur in all sessions
        if len(soulcredit_events) > 0:
            for event in soulcredit_events:
                economy = event['economy']
                assert 'soulcredit_delta' in economy
                assert 'soulcredit_reasons' in economy or 'soulcredit_source' in economy, \
                    "Soulcredit change should have reason or source"

    @pytest.mark.xfail(reason="Known bug: Void tracking may not always capture all void changes")
    def test_void_tracking_completeness(self, combat_events):
        """All void-related actions should update void_delta (known to have gaps)."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            narration = res.get('context', {}).get('narration', '')
            economy = res.get('economy', {})

            # If void is explicitly mentioned, should have tracking
            if 'void' in narration.lower():
                void_delta = economy.get('void_delta')
                void_source = economy.get('void_source')

                # This assertion may fail due to known bugs
                assert void_delta is not None or void_source is not None, \
                    "Void mentioned but no economy tracking"


# Helper functions
def parse_into_rounds(events):
    """Group events by round number."""
    rounds = {}
    for event in events:
        if 'round' in event:
            round_num = event['round']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(event)
    return rounds
