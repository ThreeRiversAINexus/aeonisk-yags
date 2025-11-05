"""
Integration tests for NPC system using golden_npc_deescalation.jsonl fixture.

Tests verify end-to-end NPC functionality:
- NPC spawning with correct agent_id prefixes
- NPC action declarations via LLM client
- NPC action resolutions with lightweight adjudication
- Enemy→NPC de-escalation with stable agent_ids
- Complete JSONL logging (declaration + resolution events)

Fixture: tests/fixtures/sessions/golden_npc_deescalation.jsonl
- 3 rounds, 2 players, 3 enemies (de-escalate to prisoners), 1 civilian NPC
- Demonstrates: fresh NPC spawn, de-escalation mechanics, NPC actions
- Extracted from session 7ff2fba6-30b2-4654-b3e5-8afc3071a2a4 (commit 8edf124)
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any


GOLDEN_FIXTURE = "tests/fixtures/sessions/golden_npc_deescalation.jsonl"


def load_fixture_events() -> List[Dict[str, Any]]:
    """Load all events from golden fixture."""
    fixture_path = Path(GOLDEN_FIXTURE)
    assert fixture_path.exists(), f"Fixture not found: {GOLDEN_FIXTURE}"

    events = []
    with open(fixture_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    return events


def filter_events(events: List[Dict], event_type: str) -> List[Dict]:
    """Filter events by type."""
    return [e for e in events if e.get('event_type') == event_type]


def get_agent_ids_by_prefix(events: List[Dict], prefix: str) -> List[str]:
    """Extract unique agent_ids matching prefix from all events."""
    agent_ids = set()

    for event in events:
        # Check player_id field
        if 'player_id' in event and event['player_id'] and event['player_id'].startswith(prefix):
            agent_ids.add(event['player_id'])

        # Check agent field
        if 'agent' in event and event['agent'] and str(event['agent']).startswith(prefix):
            agent_ids.add(event['agent'])

        # Check agent_id field
        if 'agent_id' in event and event['agent_id'] and event['agent_id'].startswith(prefix):
            agent_ids.add(event['agent_id'])

    return sorted(list(agent_ids))


class TestNPCSystemIntegration:
    """Integration tests using golden_npc_deescalation.jsonl fixture."""

    def test_fixture_exists(self):
        """Golden fixture exists and is readable."""
        fixture_path = Path(GOLDEN_FIXTURE)
        assert fixture_path.exists(), f"Fixture not found: {GOLDEN_FIXTURE}"

        # Should have content
        size = fixture_path.stat().st_size
        assert size > 100_000, f"Fixture too small ({size} bytes), expected >100KB"

    def test_fixture_has_expected_structure(self):
        """Fixture contains expected event types and counts."""
        events = load_fixture_events()

        # Should have 100+ events (fixture has 101)
        assert len(events) >= 100, f"Expected 100+ events, got {len(events)}"

        # Check for key event types
        event_types = set(e.get('event_type') for e in events)
        required_types = {
            'session_start',
            'scenario',
            'enemy_spawn',
            'action_declaration',
            'action_resolution',
            'round_synthesis'
        }

        missing_types = required_types - event_types
        assert not missing_types, f"Missing event types: {missing_types}"

    def test_npc_spawning_uses_npc_prefix(self):
        """Fresh NPCs spawn with npc_ prefix (not enemy_)."""
        events = load_fixture_events()

        # Get all agent_ids starting with npc_
        npc_ids = get_agent_ids_by_prefix(events, 'npc_')

        # Should have at least 1 fresh NPC (Dock Worker Kassia)
        assert len(npc_ids) >= 1, f"Expected at least 1 npc_ agent, got {len(npc_ids)}: {npc_ids}"

        # Verify format: npc_<name>_<random_id>
        for npc_id in npc_ids:
            assert npc_id.startswith('npc_'), f"Invalid NPC ID format: {npc_id}"
            parts = npc_id.split('_')
            assert len(parts) >= 3, f"NPC ID should have at least 3 parts: {npc_id}"

    def test_converted_npcs_preserve_enemy_prefix(self):
        """NPCs converted from enemies keep their enemy_ prefix for stability."""
        events = load_fixture_events()

        # Look for enemy_conversions in round_synthesis events
        synthesis_events = filter_events(events, 'round_synthesis')

        conversions = []
        for event in synthesis_events:
            if 'enemy_conversions' in event:
                conversions.extend(event['enemy_conversions'])

        # Should have 3 conversions (3 raiders → prisoners)
        assert len(conversions) >= 3, f"Expected 3+ conversions, got {len(conversions)}"

        # All converted NPCs should keep enemy_ prefix
        for conversion in conversions:
            enemy_id = conversion.get('enemy_id')
            assert enemy_id, f"Conversion missing enemy_id: {conversion}"
            assert enemy_id.startswith('enemy_'), f"Converted NPC should keep enemy_ prefix: {enemy_id}"

            # Verify conversion metadata
            assert conversion.get('resolution') in ['convinced', 'surrendered', 'intimidated', 'fled'], \
                f"Invalid resolution type: {conversion.get('resolution')}"
            assert conversion.get('resulting_entity_type') == 'prisoner', \
                f"Expected prisoner, got {conversion.get('resulting_entity_type')}"

    def test_npc_action_declarations_logged(self):
        """NPCs generate action_declaration events."""
        events = load_fixture_events()
        declarations = filter_events(events, 'action_declaration')

        # Get NPC declarations (agent_ids starting with npc_ or enemy_ that are now NPCs)
        npc_declarations = []
        for decl in declarations:
            player_id = decl.get('player_id', '')
            char_name = decl.get('character_name', '')

            # NPC declarations have:
            # - player_id starting with npc_ OR
            # - character_name containing "Raider" (converted enemies) OR
            # - character_name containing "Dock Worker" (fresh NPC)
            if (player_id.startswith('npc_') or
                'Raider' in char_name or
                'Dock Worker' in char_name):
                npc_declarations.append(decl)

        # Should have multiple NPC declarations (civilian + 3 prisoners acting)
        assert len(npc_declarations) >= 4, \
            f"Expected 4+ NPC declarations, got {len(npc_declarations)}"

        # Verify declaration structure
        for decl in npc_declarations:
            assert 'player_id' in decl, "Declaration missing player_id"
            assert 'character_name' in decl, "Declaration missing character_name"
            assert 'action' in decl, "Declaration missing action"
            assert 'initiative' in decl, "Declaration missing initiative"

    def test_npc_action_resolutions_logged(self):
        """NPCs generate action_resolution events."""
        events = load_fixture_events()
        resolutions = filter_events(events, 'action_resolution')

        # Get NPC resolutions
        npc_resolutions = []
        for res in resolutions:
            agent = res.get('agent', '')

            # NPC resolutions have agent field with NPC character name
            if ('Raider' in agent or
                'Dock Worker' in agent or
                agent.startswith('npc_')):
                npc_resolutions.append(res)

        # Should have multiple NPC resolutions
        assert len(npc_resolutions) >= 4, \
            f"Expected 4+ NPC resolutions, got {len(npc_resolutions)}"

        # Verify resolution structure
        for res in npc_resolutions:
            assert 'agent' in res, "Resolution missing agent"
            assert 'action' in res, "Resolution missing action"
            assert 'roll' in res, "Resolution missing roll"

            # Verify NPC-specific roll characteristics (lightweight adjudication)
            roll = res['roll']
            assert roll.get('attr') in ['None', None], \
                f"NPC should have attr='None', got {roll.get('attr')}"
            assert roll.get('skill') in [None, ''], \
                f"NPC should have skill=None, got {roll.get('skill')}"
            assert roll.get('d20') == 0, \
                f"NPC should have d20=0 (no roll), got {roll.get('d20')}"
            assert roll.get('tier') == 'marginal', \
                f"NPC should have tier='marginal', got {roll.get('tier')}"

    def test_npc_action_types(self):
        """NPCs use appropriate action types (flee, plead, comply, dialogue)."""
        events = load_fixture_events()
        resolutions = filter_events(events, 'action_resolution')

        # Get NPC action types
        npc_actions = []
        for res in resolutions:
            agent = res.get('agent', '')
            if 'Raider' in agent or 'Dock Worker' in agent:
                action = res.get('action', '')
                if action:
                    npc_actions.append(action)

        # Should have flee, plead, comply, dialogue
        action_types = set(npc_actions)
        expected_types = {'flee', 'plead', 'comply', 'dialogue'}

        found_types = action_types & expected_types
        assert len(found_types) >= 3, \
            f"Expected at least 3 NPC action types from {expected_types}, got {found_types}"

    def test_npc_lightweight_adjudication(self):
        """NPCs use lightweight adjudication (no mechanics, simple narration)."""
        events = load_fixture_events()
        resolutions = filter_events(events, 'action_resolution')

        # Find NPC resolution
        npc_res = None
        for res in resolutions:
            if 'Dock Worker' in res.get('agent', ''):
                npc_res = res
                break

        assert npc_res is not None, "Could not find Dock Worker NPC resolution"

        # Verify lightweight adjudication characteristics
        roll = npc_res['roll']
        assert roll['total'] == 0, f"NPC roll total should be 0, got {roll['total']}"
        assert roll['dc'] == 0, f"NPC DC should be 0, got {roll['dc']}"
        assert roll['margin'] == 0, f"NPC margin should be 0, got {roll['margin']}"
        assert roll['success'] == True, "NPC actions should succeed"

        # Economy should have no changes (NPCs don't generate void/soulcredit)
        economy = npc_res.get('economy', {})
        assert economy.get('void_delta', 0) == 0, "NPCs shouldn't change void"
        assert economy.get('soulcredit_delta', 0) == 0, "NPCs shouldn't change soulcredit"

    def test_de_escalation_preserves_agent_ids(self):
        """Enemy→NPC conversion preserves agent_ids for stable tracking."""
        events = load_fixture_events()

        # Get enemy_spawn events (initial enemies)
        enemy_spawns = filter_events(events, 'enemy_spawn')
        assert len(enemy_spawns) >= 3, f"Expected 3+ enemy spawns, got {len(enemy_spawns)}"

        # Get round_synthesis with enemy_conversions
        synthesis_events = filter_events(events, 'round_synthesis')

        # Find conversion event
        conversion_event = None
        for event in synthesis_events:
            if 'enemy_conversions' in event and len(event['enemy_conversions']) > 0:
                conversion_event = event
                break

        assert conversion_event is not None, "No conversion event found"

        conversions = conversion_event['enemy_conversions']
        assert len(conversions) >= 3, f"Expected 3 conversions, got {len(conversions)}"

        # Verify each conversion preserves enemy_id format
        for conversion in conversions:
            enemy_id = conversion['enemy_id']

            # Should keep enemy_ prefix (stable ID)
            assert enemy_id.startswith('enemy_'), \
                f"Converted NPC should preserve enemy_ prefix: {enemy_id}"

            # Should have valid conversion metadata
            assert conversion['resolution'] in ['convinced', 'surrendered', 'intimidated'], \
                f"Invalid resolution: {conversion['resolution']}"
            assert conversion['resulting_entity_type'] == 'prisoner', \
                f"Should convert to prisoner, got {conversion['resulting_entity_type']}"
            assert conversion['resulting_disposition'] == 'prisoner', \
                f"Should have prisoner disposition, got {conversion['resulting_disposition']}"
            assert 'reason' in conversion, "Conversion missing reason"

    def test_npc_actions_after_conversion(self):
        """Converted NPCs can declare and resolve actions in subsequent rounds."""
        events = load_fixture_events()

        # Get round_synthesis to find when conversions happen
        synthesis_events = filter_events(events, 'round_synthesis')
        conversion_round = None

        for event in synthesis_events:
            if event.get('enemy_conversions'):
                conversion_round = event.get('round')
                break

        assert conversion_round is not None, "No conversion round found"

        # Find NPC actions in rounds AFTER conversion
        declarations = filter_events(events, 'action_declaration')
        post_conversion_actions = [
            d for d in declarations
            if d.get('round', 0) > conversion_round and 'Raider' in d.get('character_name', '')
        ]

        # Converted NPCs should act in later rounds
        assert len(post_conversion_actions) >= 2, \
            f"Expected 2+ NPC actions after conversion, got {len(post_conversion_actions)}"

        # Verify these are prisoner-appropriate actions (plead, comply)
        action_types = set()
        for action in post_conversion_actions:
            action_dict = action.get('action', {})
            if isinstance(action_dict, dict):
                major_action = action_dict.get('major_action', '')
                if major_action:
                    action_types.add(major_action)

        # Should be peaceful prisoner actions
        prisoner_actions = {'plead', 'comply', 'dialogue', 'pass'}
        assert len(action_types & prisoner_actions) > 0, \
            f"Expected prisoner actions from {prisoner_actions}, got {action_types}"

    def test_no_errors_in_session(self):
        """Session completes without errors or exceptions."""
        events = load_fixture_events()

        # Check for error indicators in JSONL
        for event in events:
            # Check if any event has error fields
            if 'error' in event:
                pytest.fail(f"Found error in event: {event}")

            # Check for exception strings in narration/output
            if 'narration' in event:
                narration = str(event['narration']).lower()
                error_keywords = ['traceback', 'exception', 'keyerror', 'attributeerror']
                for keyword in error_keywords:
                    if keyword in narration:
                        pytest.fail(f"Found error keyword '{keyword}' in narration: {event}")

    def test_session_completeness(self):
        """Session has complete data for all expected rounds."""
        events = load_fixture_events()

        # Should have session_start
        session_starts = filter_events(events, 'session_start')
        assert len(session_starts) == 1, "Should have exactly 1 session_start"

        # Should have scenario
        scenarios = filter_events(events, 'scenario')
        assert len(scenarios) == 1, "Should have exactly 1 scenario"

        # Should have round_start for rounds 1-3 (round 0 often missing)
        round_starts = filter_events(events, 'round_start')
        assert len(round_starts) >= 3, f"Expected 3+ round_starts, got {len(round_starts)}"

        # Should have round_synthesis for each round
        round_syntheses = filter_events(events, 'round_synthesis')
        assert len(round_syntheses) == 3, f"Expected 3 round_syntheses, got {len(round_syntheses)}"

        # Should have LLM calls
        llm_calls = filter_events(events, 'llm_call')
        assert len(llm_calls) >= 20, f"Expected 20+ LLM calls, got {len(llm_calls)}"
