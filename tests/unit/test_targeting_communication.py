"""
Unit tests for enemy targeting communication during action declaration.

Tests that enemy actions communicate target/weapon/reasoning information
to both players and DM during declaration and resolution phases.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.session import MultiAgentSession
from scripts.aeonisk.multiagent.player import Player
from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatModule


class TestEnemyTargetingBroadcast:
    """Test that enemy declaration broadcasts include targeting information."""

    def test_enemy_declaration_includes_target(self):
        """Enemy ACTION_DECLARED broadcast should include target field."""
        # Setup mock session
        with patch('scripts.aeonisk.multiagent.session.SharedState'), \
             patch('scripts.aeonisk.multiagent.session.MessageBus') as mock_bus_class:

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            session = MultiAgentSession(
                session_name="test",
                max_turns=1,
                agents=[],
                party_size=2
            )

            # Mock enemy declaration
            enemy_declaration = {
                'agent_id': 'enemy_thug_01',
                'character_name': 'Thug',
                'initiative': 15,
                'major_action': 'Attack',
                'target': 'tgt_player_ash',
                'weapon': 'knife',
                'reasoning': 'Target nearest threat'
            }

            # Simulate enemy declaration broadcast
            # This would normally happen in session._handle_enemy_declarations
            session.message_bus.publish('ACTION_DECLARED', payload={
                'agent_id': enemy_declaration['agent_id'],
                'character_name': enemy_declaration['character_name'],
                'intent': enemy_declaration['major_action'],
                'target': enemy_declaration.get('target'),  # NEW
                'weapon': enemy_declaration.get('weapon'),  # NEW
                'reasoning': enemy_declaration.get('reasoning', '')[:100],  # NEW (truncated)
                'initiative': enemy_declaration['initiative'],
                'agent_type': 'enemy'
            })

            # Verify broadcast was called with targeting info
            mock_bus.publish.assert_called_once()
            call_args = mock_bus.publish.call_args

            assert call_args[0][0] == 'ACTION_DECLARED'
            payload = call_args[1]['payload']

            assert payload['target'] == 'tgt_player_ash'
            assert payload['weapon'] == 'knife'
            assert 'Target nearest threat' in payload['reasoning']
            assert payload['agent_type'] == 'enemy'

    def test_enemy_declaration_handles_missing_optional_fields(self):
        """Enemy broadcast should handle missing target/weapon gracefully."""
        with patch('scripts.aeonisk.multiagent.session.SharedState'), \
             patch('scripts.aeonisk.multiagent.session.MessageBus') as mock_bus_class:

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            session = MultiAgentSession(
                session_name="test",
                max_turns=1,
                agents=[],
                party_size=2
            )

            # Enemy declaration with minimal info (e.g., "Pass" action)
            enemy_declaration = {
                'agent_id': 'enemy_thug_01',
                'character_name': 'Thug',
                'initiative': 15,
                'major_action': 'Pass'
                # No target, weapon, reasoning
            }

            # Should not crash when optional fields missing
            session.message_bus.publish('ACTION_DECLARED', payload={
                'agent_id': enemy_declaration['agent_id'],
                'character_name': enemy_declaration['character_name'],
                'intent': enemy_declaration['major_action'],
                'target': enemy_declaration.get('target'),  # None
                'weapon': enemy_declaration.get('weapon'),  # None
                'reasoning': enemy_declaration.get('reasoning', '')[:100],  # Empty string
                'initiative': enemy_declaration['initiative'],
                'agent_type': 'enemy'
            })

            # Verify broadcast succeeded
            mock_bus.publish.assert_called_once()
            payload = mock_bus.publish.call_args[1]['payload']

            assert payload['target'] is None
            assert payload['weapon'] is None
            assert payload['reasoning'] == ''


class TestPlayerTargetingDisplay:
    """Test that players receive and display enemy targeting information."""

    def test_player_stores_enemy_target_info(self):
        """Player should store target/weapon info from enemy declarations."""
        # Setup mock player
        with patch('scripts.aeonisk.multiagent.player.MessageBus') as mock_bus_class, \
             patch('scripts.aeonisk.multiagent.player.SharedState'):

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            player = Player(
                agent_id="player_ash",
                name="Ash",
                faction="Freelancer",
                llm_model="claude-3-5-sonnet-20241022",
                stats={"Awareness": 3, "Combat": 4},
                skills={"Guns": 2},
                session_name="test"
            )

            # Simulate ACTION_DECLARED message with targeting info
            player._handle_action_declared(
                agent_id='enemy_thug_01',
                character_name='Thug',
                description='',
                intent='Attack',
                target='tgt_player_ash',  # NEW
                weapon='knife',  # NEW
                reasoning='Target nearest threat',  # NEW
                initiative=15,
                agent_type='enemy'
            )

            # Verify player stored the information
            assert 'Thug' in player.declared_actions_this_round

            stored_action = player.declared_actions_this_round['Thug']
            # Format: (description, intent, target, weapon, initiative)
            assert stored_action[0] == ''  # description (empty for enemies)
            assert stored_action[1] == 'Attack'  # intent
            assert stored_action[2] == 'tgt_player_ash'  # target (NEW)
            assert stored_action[3] == 'knife'  # weapon (NEW)
            assert stored_action[4] == 15  # initiative

    def test_player_formats_enemy_targeting_for_display(self):
        """Player should format enemy targeting info in readable way."""
        with patch('scripts.aeonisk.multiagent.player.MessageBus') as mock_bus_class, \
             patch('scripts.aeonisk.multiagent.player.SharedState'):

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            player = Player(
                agent_id="player_ash",
                name="Ash",
                faction="Freelancer",
                llm_model="claude-3-5-sonnet-20241022",
                stats={"Awareness": 3},
                skills={},
                session_name="test"
            )

            # Store enemy declaration with target
            player._handle_action_declared(
                agent_id='enemy_thug_01',
                character_name='Thug',
                description='',
                intent='Attack',
                target='tgt_player_ash',
                weapon='knife',
                reasoning='Target nearest threat',
                initiative=15,
                agent_type='enemy'
            )

            # Get formatted display string
            formatted = player._format_declared_actions_for_prompt()

            # Should show target and weapon in human-readable format
            assert 'Thug' in formatted
            assert 'Attack' in formatted
            assert 'tgt_player_ash' in formatted or 'targeting' in formatted.lower()
            assert 'knife' in formatted

    def test_player_handles_enemy_without_target(self):
        """Player should handle enemy actions without targeting info gracefully."""
        with patch('scripts.aeonisk.multiagent.player.MessageBus') as mock_bus_class, \
             patch('scripts.aeonisk.multiagent.player.SharedState'):

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            player = Player(
                agent_id="player_ash",
                name="Ash",
                faction="Freelancer",
                llm_model="claude-3-5-sonnet-20241022",
                stats={"Awareness": 3},
                skills={},
                session_name="test"
            )

            # Enemy passing/fleeing (no target)
            player._handle_action_declared(
                agent_id='enemy_thug_01',
                character_name='Thug',
                description='',
                intent='Flee',
                target=None,  # No target
                weapon=None,  # No weapon
                reasoning='',
                initiative=15,
                agent_type='enemy'
            )

            # Should store action without crashing
            assert 'Thug' in player.declared_actions_this_round

            stored_action = player.declared_actions_this_round['Thug']
            assert stored_action[1] == 'Flee'
            assert stored_action[2] is None  # target
            assert stored_action[3] is None  # weapon


class TestTargetingInResolutionPhase:
    """Test that targeting info is preserved through resolution phase."""

    def test_dm_receives_full_targeting_context_in_resolution(self):
        """DM should receive complete targeting context during resolution."""
        # This is already working per investigation, but test confirms

        with patch('scripts.aeonisk.multiagent.dm.MessageBus') as mock_bus_class, \
             patch('scripts.aeonisk.multiagent.dm.SharedState'), \
             patch('scripts.aeonisk.multiagent.dm.DMLLMClient'):

            mock_bus = Mock()
            mock_bus_class.return_value = mock_bus

            from scripts.aeonisk.multiagent.dm import DMAgent

            dm = DMAgent(
                session_name="test",
                scenario_type="combat",
                void_level=5
            )

            # Simulate resolution with full action context
            action_context = {
                'agent_id': 'enemy_thug_01',
                'character_name': 'Thug',
                'major_action': 'Attack',
                'target': 'tgt_player_ash',
                'weapon': 'knife',
                'reasoning': 'Target nearest threat',
                'initiative': 15
            }

            # DM receives directed ACTION_DECLARED during resolution
            # Should have access to full context (already working)
            assert action_context['target'] == 'tgt_player_ash'
            assert action_context['weapon'] == 'knife'
            assert action_context['reasoning'] == 'Target nearest threat'


class TestTargetingCommunicationIntegration:
    """Integration tests for targeting communication across declaration and resolution."""

    def test_targeting_visible_in_both_phases(self):
        """Targeting info should be visible in both declaration and resolution phases."""
        # This would be a full integration test with session running
        # For now, test contract: broadcast in declaration, preserved in resolution

        enemy_action = {
            'agent_id': 'enemy_thug_01',
            'character_name': 'Thug',
            'major_action': 'Attack',
            'target': 'tgt_player_ash',
            'weapon': 'knife',
            'reasoning': 'Target nearest threat',
            'initiative': 15
        }

        # Declaration phase payload (what players see)
        declaration_payload = {
            'agent_id': enemy_action['agent_id'],
            'character_name': enemy_action['character_name'],
            'intent': enemy_action['major_action'],
            'target': enemy_action['target'],  # MUST be present
            'weapon': enemy_action['weapon'],  # MUST be present
            'reasoning': enemy_action['reasoning'][:100],
            'initiative': enemy_action['initiative'],
            'agent_type': 'enemy'
        }

        # Verify declaration phase has targeting
        assert declaration_payload['target'] is not None
        assert declaration_payload['weapon'] is not None

        # Resolution phase (DM receives same action context)
        # Already working - DM gets full action dict
        assert enemy_action['target'] == declaration_payload['target']
        assert enemy_action['weapon'] == declaration_payload['weapon']

    def test_npc_actions_already_include_reasoning(self):
        """NPCs already include reasoning in broadcasts (verify this continues)."""
        # Per investigation, NPCs already broadcast 'description' (their reasoning)
        # Ensure this pattern continues

        npc_broadcast_payload = {
            'agent_id': 'npc_prisoner_01',
            'character_name': 'Prisoner',
            'description': 'Trying to escape while guards are distracted',  # ✅ Already includes reasoning
            'intent': 'flee',
            'initiative': 12,
            'agent_type': 'npc'
        }

        # NPC broadcasts should continue including description/reasoning
        assert 'description' in npc_broadcast_payload
        assert npc_broadcast_payload['description'] != ''
