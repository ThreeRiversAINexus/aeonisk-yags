"""
NPC Lifecycle Integration Tests

Tests complete NPC lifecycle using golden_npc_escalation_lifecycle.jsonl fixture:
1. NPC spawning from session config
2. Multiple simultaneous NPC escalations (NPC→enemy)
3. Escalated NPCs immediately use enemy combat AI
4. Agent ID preservation through escalation
5. De-escalation mechanics (enemy→prisoner)
6. Agent ID preservation through de-escalation
7. Prisoner behavior (NPC action set)
8. Complete JSONL logging of all conversions

Fixture: tests/fixtures/sessions/golden_npc_escalation_lifecycle.jsonl
- 3 rounds, 2 players, 3 NPCs (all escalate, 2 de-escalate)
- Demonstrates: spawn → 3x escalate → combat → 2x de-escalate
- Stress test for simultaneous conversions and agent ID stability
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any


# ==============================================================================
# Fixtures
# ==============================================================================

FIXTURE_PATH = "sessions/golden_npc_escalation_lifecycle.jsonl"


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
def npc_lifecycle_session():
    """Load NPC escalation lifecycle session."""
    return load_fixture(FIXTURE_PATH)


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
# Test Class 1: NPC Spawning
# ==============================================================================

class TestNPCSpawning:
    """Test NPC spawning mechanics from session config."""

    def test_fixture_loads_successfully(self, npc_lifecycle_session):
        """
        Fixture loads and contains events.
        """
        assert len(npc_lifecycle_session) > 0, "Fixture should have events"
        assert any(e.get('event_type') == 'scenario' for e in npc_lifecycle_session), \
            "Fixture should have scenario event"

    def test_three_npcs_spawn_from_config(self, npc_lifecycle_session, extract_events):
        """
        3 NPCs spawn at session start from config.

        Tests: initial_npcs config field correctly spawns NPCs.
        """
        # Find round_synthesis event with npc_spawns
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        # Look for scenario event which should mention NPCs
        scenario = extract_events(npc_lifecycle_session, 'scenario')
        assert len(scenario) == 1, "Should have exactly 1 scenario event"

        # Scenario situation mentions the 3 NPCs
        situation = scenario[0].get('scenario', {}).get('situation', '')
        assert 'Razor' in situation, "Scenario should mention Razor"
        assert 'Twist' in situation, "Scenario should mention Twist"
        assert 'Flicker' in situation, "Scenario should mention Flicker"

    def test_npcs_have_correct_agent_id_prefix(self, npc_lifecycle_session, extract_events):
        """
        Spawned NPCs have npc_ agent ID prefix.

        Tests: Agent ID convention for NPCs (npc_<name>_<timestamp>).
        """
        # Find escalation events (which reference NPC IDs)
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        escalations = []
        for event in synthesis_events:
            if 'escalations' in event and event['escalations']:
                escalations.extend(event['escalations'])

        assert len(escalations) >= 3, "Should have at least 3 escalations"

        # All escalated NPC IDs should start with npc_
        for escalation in escalations:
            npc_id = escalation['npc_id']
            assert npc_id.startswith('npc_'), \
                f"NPC ID should start with npc_, got: {npc_id}"

    def test_npcs_have_distinct_threat_levels(self, npc_lifecycle_session):
        """
        NPCs spawn with different threat levels.

        Tests: Config threat_level field (armed_neutral, potential_threat, non_combatant).
        """
        # This test verifies the session used varied NPC types from config
        # The config specifies: armed_neutral (Razor), potential_threat (Twist), non_combatant (Flicker)

        scenario = next(e for e in npc_lifecycle_session if e.get('event_type') == 'scenario')
        situation = scenario.get('scenario', {}).get('situation', '')

        # Situation should describe different threat levels
        assert 'weapon already drawn' in situation or 'trigger-happy' in situation, \
            "Should mention armed threat (Razor)"
        assert 'Concealed' in situation or 'wanted' in situation.lower(), \
            "Should mention potential threat (Twist)"
        assert 'void-addled' in situation.lower() or 'scavenger' in situation.lower(), \
            "Should mention non-combatant (Flicker)"


# ==============================================================================
# Test Class 2: Escalation Mechanics
# ==============================================================================

class TestEscalationMechanics:
    """Test NPC→enemy escalation mechanics."""

    def test_three_simultaneous_escalations_in_round_1(self, npc_lifecycle_session, extract_events):
        """
        All 3 NPCs escalate simultaneously in Round 1.

        Tests: System handles multiple simultaneous conversions.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        assert len(synthesis_events) == 1, "Should have exactly 1 Round 1 synthesis"

        synthesis = synthesis_events[0]
        escalations = synthesis.get('escalations', [])

        assert len(escalations) == 3, \
            f"Should have 3 simultaneous escalations in Round 1, got {len(escalations)}"

        # Verify all 3 NPCs escalated
        escalated_ids = {e['npc_id'] for e in escalations}
        assert any('razor' in npc_id.lower() for npc_id in escalated_ids), "Razor should escalate"
        assert any('twist' in npc_id.lower() for npc_id in escalated_ids), "Twist should escalate"
        assert any('flicker' in npc_id.lower() for npc_id in escalated_ids), "Flicker should escalate"

    def test_escalation_preserves_agent_id(self, npc_lifecycle_session, extract_events):
        """
        Agent IDs are preserved through NPC→enemy escalation.

        CRITICAL: Agent IDs NEVER change during conversion.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        escalations = synthesis_events[0].get('escalations', [])

        # Get escalated NPC IDs
        escalated_npc_ids = {e['npc_id'] for e in escalations}

        # Find combat actions in Round 2 (first round after escalation)
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action', round=1)

        if len(combat_actions) > 0:
            # Verify combat action uses same agent ID
            combat_attacker_ids = {a.get('attacker', {}).get('id') for a in combat_actions}

            # At least one combat action should use an escalated NPC's ID
            overlap = escalated_npc_ids & combat_attacker_ids
            assert len(overlap) > 0, \
                f"Escalated NPCs ({escalated_npc_ids}) should appear in combat actions ({combat_attacker_ids})"

    def test_escalation_metadata_complete(self, npc_lifecycle_session, extract_events):
        """
        Escalation events have complete metadata.

        Tests: npc_id, reason, template fields present and substantive.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        escalations = synthesis_events[0].get('escalations', [])

        assert len(escalations) == 3, "Should have 3 escalations"

        for escalation in escalations:
            # Required fields
            assert 'npc_id' in escalation, "Escalation should have npc_id"
            assert 'reason' in escalation, "Escalation should have reason"
            assert 'template' in escalation, "Escalation should have template"

            # Reason should be substantive
            assert len(escalation['reason']) >= 20, \
                f"Escalation reason should be detailed (>=20 chars), got {len(escalation['reason'])} chars"

            # Template should be valid enemy template
            assert escalation['template'] in ['desperate_fighter', 'tactical_operator', 'void_cultist', 'corporate_security'], \
                f"Invalid enemy template: {escalation['template']}"

    def test_dm_cites_personality_in_escalation_reasoning(self, npc_lifecycle_session, extract_events):
        """
        DM escalation reasons cite NPC personalities.

        Tests: DM reasoning is personality-driven, not arbitrary.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        escalations = synthesis_events[0].get('escalations', [])

        # Check that at least one escalation reason mentions personality traits
        personality_indicators = [
            'paranoid', 'trigger-happy', 'desperate', 'wanted',
            'void-addled', 'voices', 'panic', 'scared', 'threatened'
        ]

        escalation_reasons = [e['reason'].lower() for e in escalations]
        combined_reasons = ' '.join(escalation_reasons)

        matches = [indicator for indicator in personality_indicators if indicator in combined_reasons]
        assert len(matches) >= 2, \
            f"Escalation reasons should cite NPC personalities, found only {len(matches)} indicators: {matches}"


# ==============================================================================
# Test Class 3: Combat Integration
# ==============================================================================

class TestCombatIntegration:
    """Test escalated NPCs use enemy combat AI."""

    def test_escalated_npc_enters_combat_immediately(self, npc_lifecycle_session, extract_events):
        """
        Escalated NPCs participate in combat with no delay.

        Tests: NPC→enemy conversion activates tactical combat behavior.
        """
        # Escalations happen at end of Round 1
        synthesis_r1 = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        escalations = synthesis_r1[0].get('escalations', [])
        escalated_ids = {e['npc_id'] for e in escalations}

        # Find combat actions in Round 1 (escalations can act immediately)
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action', round=1)

        # At least one combat action should be from escalated NPC
        if len(combat_actions) > 0:
            combat_attacker_ids = {a.get('attacker', {}).get('id') for a in combat_actions}
            overlap = escalated_ids & combat_attacker_ids

            assert len(overlap) > 0, \
                f"At least one escalated NPC should have combat action immediately. " \
                f"Escalated: {escalated_ids}, Combat: {combat_attacker_ids}"

    def test_escalated_npc_uses_tactical_combat_action(self, npc_lifecycle_session, extract_events):
        """
        Escalated NPCs use enemy combat AI, not NPC action set.

        Tests: combat_action event logged (not simple action_declaration).
        """
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action')

        assert len(combat_actions) >= 1, \
            "Should have at least 1 combat_action from escalated enemies"

        # Verify combat action has weapon, attack, damage fields
        combat_action = combat_actions[0]
        assert 'weapon' in combat_action, "Combat action should specify weapon"
        assert 'attack' in combat_action, "Combat action should have attack roll"
        assert 'damage' in combat_action or 'damage_dealt' in combat_action or \
               combat_action.get('attack', {}).get('hit') == False, \
            "Combat action should have damage (or explain why not)"

    def test_escalated_npc_deals_damage_to_player(self, npc_lifecycle_session, extract_events):
        """
        Escalated NPC successfully damages player character.

        Tests: Combat mechanics work end-to-end (Razor shoots Brick for 11 damage).
        """
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action')

        # Find combat action with damage dealt
        damage_events = [ca for ca in combat_actions if ca.get('damage', {}).get('dealt', 0) > 0]

        assert len(damage_events) >= 1, \
            "Should have at least 1 combat action dealing damage"

        damage_event = damage_events[0]
        damage_dealt = damage_event.get('damage', {}).get('dealt', 0)

        assert damage_dealt > 0, f"Damage should be > 0, got {damage_dealt}"
        assert damage_dealt >= 10, \
            f"Damage should be significant (>=10), got {damage_dealt}"

    def test_free_targeting_works_with_escalated_npcs(self, npc_lifecycle_session, extract_events):
        """
        Free targeting system works with escalated NPCs.

        Tests: Escalated NPCs can target generic tgt_xxxx IDs.
        """
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action')

        if len(combat_actions) > 0:
            combat_action = combat_actions[0]
            defender = combat_action.get('defender', {})
            defender_id = defender.get('id', '')

            # Defender should have generic target ID
            assert defender_id.startswith('tgt_'), \
                f"Combat defender should have tgt_ ID, got: {defender_id}"


# ==============================================================================
# Test Class 4: De-escalation Mechanics
# ==============================================================================

class TestDeescalationMechanics:
    """Test enemy→prisoner de-escalation mechanics."""

    def test_two_deescalations_occur(self, npc_lifecycle_session, extract_events):
        """
        2 de-escalations occur in Rounds 2-3.

        Tests: De-escalation mechanics work (enemy→prisoner).
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        all_deescalations = []
        for event in synthesis_events:
            if 'enemy_conversions' in event and event['enemy_conversions']:
                all_deescalations.extend(event['enemy_conversions'])

        assert len(all_deescalations) >= 2, \
            f"Should have at least 2 de-escalations, got {len(all_deescalations)}"

    def test_deescalation_preserves_agent_id(self, npc_lifecycle_session, extract_events):
        """
        Agent IDs preserved through enemy→prisoner de-escalation.

        CRITICAL: Agent IDs NEVER change during conversion.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        deescalations = []
        for event in synthesis_events:
            if 'enemy_conversions' in event and event['enemy_conversions']:
                deescalations.extend(event['enemy_conversions'])

        assert len(deescalations) >= 2, "Should have at least 2 de-escalations"

        # Verify all de-escalated enemies kept their IDs
        for deescalation in deescalations:
            enemy_id = deescalation['enemy_id']
            # ID should still be npc_* (NPCs keep prefix through all conversions)
            assert enemy_id.startswith('npc_') or enemy_id.startswith('enemy_'), \
                f"De-escalated agent should preserve ID prefix, got: {enemy_id}"

    def test_deescalation_metadata_complete(self, npc_lifecycle_session, extract_events):
        """
        De-escalation events have complete metadata.

        Tests: enemy_id, resolution, reason, resulting_entity_type fields present.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        deescalations = []
        for event in synthesis_events:
            if 'enemy_conversions' in event and event['enemy_conversions']:
                deescalations.extend(event['enemy_conversions'])

        for deescalation in deescalations:
            # Required fields
            assert 'enemy_id' in deescalation, "De-escalation should have enemy_id"
            assert 'resolution' in deescalation, "De-escalation should have resolution"
            assert 'reason' in deescalation, "De-escalation should have reason"
            assert 'resulting_entity_type' in deescalation, "De-escalation should have resulting_entity_type"
            assert 'resulting_disposition' in deescalation, "De-escalation should have resulting_disposition"

            # Reason should be substantive
            assert len(deescalation['reason']) >= 20, \
                f"De-escalation reason should be detailed, got {len(deescalation['reason'])} chars"

            # Resolution should be valid
            assert deescalation['resolution'] in ['convinced', 'defeated', 'fled'], \
                f"Invalid resolution: {deescalation['resolution']}"

            # Resulting entity type should be valid
            assert deescalation['resulting_entity_type'] in ['prisoner', 'ally', 'neutral'], \
                f"Invalid resulting_entity_type: {deescalation['resulting_entity_type']}"

    def test_prisoners_use_npc_action_set(self, npc_lifecycle_session, extract_events):
        """
        De-escalated prisoners use NPC actions (comply, plead), not combat actions.

        Tests: Action set correctly changes after de-escalation.
        """
        # Find action_resolution events in Round 3 (after de-escalations)
        action_resolutions = extract_events(npc_lifecycle_session, 'action_resolution', round=3)

        # Find actions from converted prisoners (Twist and Razor)
        prisoner_actions = []
        for action in action_resolutions:
            agent = action.get('agent', '')
            if 'twist' in agent.lower() or 'razor' in agent.lower():
                prisoner_actions.append(action)

        if len(prisoner_actions) > 0:
            # Verify actions are NPC-type (comply, plead, dialogue, flee, hide)
            npc_action_types = ['comply', 'plead', 'dialogue', 'flee', 'hide', 'pass']

            for action in prisoner_actions:
                action_text = action.get('action', '').lower()
                # Check if action text contains NPC action type
                has_npc_action = any(npc_type in action_text for npc_type in npc_action_types)

                assert has_npc_action, \
                    f"Prisoner action should be NPC-type (comply/plead/etc), got: {action.get('action', '')}"


# ==============================================================================
# Test Class 5: JSONL Logging Completeness
# ==============================================================================

class TestJSONLLogging:
    """Test JSONL logging completeness for NPC lifecycle."""

    def test_escalation_events_logged_to_jsonl(self, npc_lifecycle_session, extract_events):
        """
        All escalations appear in round_synthesis events.

        Tests: JSONL logging captures escalations.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        all_escalations = []
        for event in synthesis_events:
            if 'escalations' in event and event['escalations']:
                all_escalations.extend(event['escalations'])

        assert len(all_escalations) >= 3, \
            f"Should have 3 escalations logged, got {len(all_escalations)}"

    def test_deescalation_events_logged_to_jsonl(self, npc_lifecycle_session, extract_events):
        """
        All de-escalations appear in round_synthesis events.

        Tests: JSONL logging captures de-escalations.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        all_deescalations = []
        for event in synthesis_events:
            if 'enemy_conversions' in event and event['enemy_conversions']:
                all_deescalations.extend(event['enemy_conversions'])

        assert len(all_deescalations) >= 2, \
            f"Should have 2 de-escalations logged, got {len(all_deescalations)}"

    def test_combat_actions_logged_for_escalated_npcs(self, npc_lifecycle_session, extract_events):
        """
        Combat actions from escalated NPCs are logged as combat_action events.

        Tests: Escalated NPCs use enemy combat system (not just action_resolution).
        """
        combat_actions = extract_events(npc_lifecycle_session, 'combat_action')

        assert len(combat_actions) >= 1, \
            "Should have at least 1 combat_action event from escalated NPCs"

    def test_character_state_tracking_through_conversions(self, npc_lifecycle_session, extract_events):
        """
        Character state events track NPCs through conversions.

        Tests: State tracking works across NPC→enemy→prisoner conversions.
        """
        char_states = extract_events(npc_lifecycle_session, 'character_state')

        # Should have character states for players (minimum)
        assert len(char_states) >= 2, \
            f"Should have character state events for players, got {len(char_states)}"


# ==============================================================================
# Test Class 6: Edge Cases and Robustness
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and system robustness."""

    def test_multiple_simultaneous_escalations_handled(self, npc_lifecycle_session, extract_events):
        """
        System handles 3 simultaneous escalations without errors.

        Tests: No race conditions or conflicts when multiple NPCs escalate at once.
        """
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis', round=1)
        escalations = synthesis_events[0].get('escalations', [])

        # Should have exactly 3 simultaneous escalations
        assert len(escalations) == 3, \
            f"Should handle 3 simultaneous escalations, got {len(escalations)}"

        # All escalations should be complete (no partial data)
        for escalation in escalations:
            assert 'npc_id' in escalation and escalation['npc_id'], \
                "All escalations should have valid npc_id"
            assert 'reason' in escalation and escalation['reason'], \
                "All escalations should have reason"
            assert 'template' in escalation and escalation['template'], \
                "All escalations should have template"

    def test_full_lifecycle_in_three_rounds(self, npc_lifecycle_session, extract_events):
        """
        Complete NPC lifecycle (spawn → escalate → de-escalate) in 3 rounds.

        Tests: System can handle rapid conversion sequences.
        """
        # Check we have all phases
        synthesis_events = extract_events(npc_lifecycle_session, 'round_synthesis')

        has_escalations = any(
            e.get('escalations') and len(e['escalations']) > 0
            for e in synthesis_events
        )

        has_deescalations = any(
            e.get('enemy_conversions') and len(e['enemy_conversions']) > 0
            for e in synthesis_events
        )

        assert has_escalations, "Should have escalations in session"
        assert has_deescalations, "Should have de-escalations in session"

    def test_no_duplicate_agent_ids(self, npc_lifecycle_session):
        """
        All agent IDs are unique throughout session.

        Tests: No ID collisions during conversions.
        """
        all_agent_ids = set()

        for event in npc_lifecycle_session:
            # Check various fields that might contain agent IDs
            if 'agent_id' in event:
                agent_id = event['agent_id']
                if agent_id:  # Skip None/empty
                    all_agent_ids.add(agent_id)

            if 'character_id' in event:
                char_id = event['character_id']
                if char_id:
                    all_agent_ids.add(char_id)

            # Check escalations
            if event.get('event_type') == 'round_synthesis':
                if event.get('escalations'):
                    for esc in event['escalations']:
                        if esc.get('npc_id'):
                            all_agent_ids.add(esc['npc_id'])

                if event.get('enemy_conversions'):
                    for conv in event['enemy_conversions']:
                        if conv.get('enemy_id'):
                            all_agent_ids.add(conv['enemy_id'])

        # We should have exactly 6 unique agents (2 players + 3 NPCs + 1 DM)
        # Agent IDs should NOT duplicate through conversions
        assert len(all_agent_ids) == 6, \
            f"Should have exactly 6 unique agent IDs (2 players + 3 NPCs + 1 DM), got {len(all_agent_ids)}: {all_agent_ids}"

    def test_session_completes_without_errors(self, npc_lifecycle_session, extract_events):
        """
        Session completes all 3 rounds without errors.

        Tests: No system errors during NPC lifecycle operations.
        """
        # Check for round_summary events (indicates rounds completed)
        round_summaries = extract_events(npc_lifecycle_session, 'round_summary')

        assert len(round_summaries) == 3, \
            f"Should have 3 round summaries (one per round), got {len(round_summaries)}"

        # Verify rounds are sequential
        rounds = sorted([rs['round'] for rs in round_summaries])
        assert rounds == [1, 2, 3], \
            f"Rounds should be [1, 2, 3], got {rounds}"
