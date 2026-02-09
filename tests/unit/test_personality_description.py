"""
Tests for personality.description field integration.

This feature adds a 'description' field inside the personality object that:
1. Player agents can use for roleplay guidance
2. DM can access for personality-appropriate narration
3. All party personalities are visible to the DM
"""

import pytest
from unittest.mock import Mock, MagicMock


class TestPlayerAgentPersonalityDescription:
    """Test AIPlayerAgent reading personality.description from config."""

    def test_reads_personality_description_from_personality_object(self):
        """Player agent should read description from personality.description."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        config = {
            'name': 'Test Character',
            'faction': 'Test Faction',
            'personality': {
                'riskTolerance': 5,
                'voidCuriosity': 3,
                'description': 'A brave warrior with a heart of gold.'
            },
            'attributes': {'Strength': 3, 'Agility': 3, 'Endurance': 3, 'Dexterity': 3,
                          'Perception': 3, 'Intelligence': 3, 'Empathy': 3, 'Willpower': 3},
            'skills': {},
            'goals': ['Test goal']
        }

        agent = AIPlayerAgent(
            agent_id='test_agent',
            socket_path='/tmp/test.sock',
            character_config=config
        )

        assert agent.personality_description == 'A brave warrior with a heart of gold.'

    def test_fallback_to_legacy_personality_notes(self):
        """Player agent should fall back to _personality_notes if description not in personality object."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        config = {
            'name': 'Test Character',
            'faction': 'Test Faction',
            'personality': {
                'riskTolerance': 5,
                'voidCuriosity': 3
                # No 'description' field
            },
            '_personality_notes': 'Legacy personality notes here.',
            'attributes': {'Strength': 3, 'Agility': 3, 'Endurance': 3, 'Dexterity': 3,
                          'Perception': 3, 'Intelligence': 3, 'Empathy': 3, 'Willpower': 3},
            'skills': {},
            'goals': ['Test goal']
        }

        agent = AIPlayerAgent(
            agent_id='test_agent',
            socket_path='/tmp/test.sock',
            character_config=config
        )

        assert agent.personality_description == 'Legacy personality notes here.'

    def test_empty_when_no_personality_description(self):
        """Player agent should have empty personality_description if neither field present."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        config = {
            'name': 'Test Character',
            'faction': 'Test Faction',
            'personality': {
                'riskTolerance': 5
            },
            'attributes': {'Strength': 3, 'Agility': 3, 'Endurance': 3, 'Dexterity': 3,
                          'Perception': 3, 'Intelligence': 3, 'Empathy': 3, 'Willpower': 3},
            'skills': {},
            'goals': ['Test goal']
        }

        agent = AIPlayerAgent(
            agent_id='test_agent',
            socket_path='/tmp/test.sock',
            character_config=config
        )

        assert agent.personality_description == ''

    def test_personality_description_preferred_over_legacy(self):
        """personality.description should take precedence over _personality_notes."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        config = {
            'name': 'Test Character',
            'faction': 'Test Faction',
            'personality': {
                'riskTolerance': 5,
                'description': 'New style description.'
            },
            '_personality_notes': 'Old style notes (should be ignored).',
            'attributes': {'Strength': 3, 'Agility': 3, 'Endurance': 3, 'Dexterity': 3,
                          'Perception': 3, 'Intelligence': 3, 'Empathy': 3, 'Willpower': 3},
            'skills': {},
            'goals': ['Test goal']
        }

        agent = AIPlayerAgent(
            agent_id='test_agent',
            socket_path='/tmp/test.sock',
            character_config=config
        )

        assert agent.personality_description == 'New style description.'


class TestSharedStatePersonalityDescription:
    """Test SharedState.register_player storing personality_description."""

    def test_register_player_stores_personality_description(self):
        """register_player should store personality_description in registered_players."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        shared_state.register_player(
            agent_id='p1',
            name='Hero McHeroface',
            faction='Heroes Guild',
            personality_description='A sarcastic hero who secretly cares.'
        )

        assert len(shared_state.registered_players) == 1
        player = shared_state.registered_players[0]
        assert player['agent_id'] == 'p1'
        assert player['name'] == 'Hero McHeroface'
        assert player['faction'] == 'Heroes Guild'
        assert player['personality_description'] == 'A sarcastic hero who secretly cares.'

    def test_register_player_default_empty_personality(self):
        """register_player should default to empty personality_description."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        shared_state.register_player(
            agent_id='p1',
            name='Silent Bob',
            faction='Quiet Ones'
        )

        player = shared_state.registered_players[0]
        assert player.get('personality_description', '') == ''

    def test_register_player_backward_compatible(self):
        """register_player should work without personality_description (backward compat)."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        # Old-style call without personality_description
        shared_state.register_player('p1', 'Old Timer', 'Old Faction')

        assert len(shared_state.registered_players) == 1
        player = shared_state.registered_players[0]
        assert player['name'] == 'Old Timer'


class TestDMPartyPersonalities:
    """Test DM access to party personalities."""

    def test_get_party_personalities_returns_all_descriptions(self):
        """_get_party_personalities should return all party member descriptions."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        shared_state.register_player('p1', 'Brave Knight', 'Knights', 'Valiant and honorable.')
        shared_state.register_player('p2', 'Sneaky Rogue', 'Thieves', 'Cunning and greedy.')
        shared_state.register_player('p3', 'Wise Mage', 'Academy', 'Scholarly and aloof.')

        dm = AIDMAgent(
            agent_id='dm',
            socket_path='/tmp/test.sock',
            llm_config={},  # Empty config for testing
            shared_state=shared_state
        )

        result = dm._get_party_personalities()

        assert 'Brave Knight' in result
        assert 'Valiant and honorable' in result
        assert 'Sneaky Rogue' in result
        assert 'Cunning and greedy' in result
        assert 'Wise Mage' in result
        assert 'Scholarly and aloof' in result

    def test_get_party_personalities_empty_when_no_descriptions(self):
        """_get_party_personalities should return empty string when no descriptions."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        shared_state.register_player('p1', 'Mystery Man', 'Unknown')  # No description

        dm = AIDMAgent(
            agent_id='dm',
            socket_path='/tmp/test.sock',
            llm_config={},
            shared_state=shared_state
        )

        result = dm._get_party_personalities()
        assert result == ''

    def test_get_party_personalities_skips_empty_descriptions(self):
        """_get_party_personalities should skip characters without descriptions."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        shared_state.register_player('p1', 'Has Description', 'Faction', 'Very descriptive.')
        shared_state.register_player('p2', 'No Description', 'Faction')  # No description

        dm = AIDMAgent(
            agent_id='dm',
            socket_path='/tmp/test.sock',
            llm_config={},
            shared_state=shared_state
        )

        result = dm._get_party_personalities()

        assert 'Has Description' in result
        assert 'Very descriptive' in result
        assert 'No Description' not in result

    def test_get_party_personalities_no_shared_state(self):
        """_get_party_personalities should handle missing shared_state gracefully."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        dm = AIDMAgent(
            agent_id='dm',
            socket_path='/tmp/test.sock',
            llm_config={},
            shared_state=None
        )

        result = dm._get_party_personalities()
        assert result == ''
