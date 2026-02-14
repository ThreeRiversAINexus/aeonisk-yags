"""
Unit tests for YAGS death save mechanics and permanent death flag.

Tests verify:
- check_death_save() sets _permanently_dead on failure
- is_alive returns False when _permanently_dead is True
- is_alive returns False even if health is somehow set > 0 after death
- Death save only triggers at 5+ wounds
"""

import pytest
from unittest.mock import patch, MagicMock

from scripts.aeonisk.multiagent.player import AIPlayerAgent


def create_test_player(health=25, max_health=25, wounds=0, health_attr=3):
    """Create a minimal AIPlayerAgent for testing death saves."""
    config = {
        'name': 'Test Character',
        'faction': 'Freeborn',
        'attributes': {
            'Strength': 3, 'Agility': 3, 'Endurance': 3, 'Dexterity': 3,
            'Perception': 3, 'Intelligence': 3, 'Empathy': 3, 'Willpower': 3,
            'Health': health_attr,
        },
        'skills': {'Guns': 3, 'Awareness': 2},
        'personality': {'description': 'Test'},
    }
    # Create with minimal init - mock the socket/agent infrastructure
    agent = AIPlayerAgent.__new__(AIPlayerAgent)
    agent.agent_id = "player_test"
    agent.health = health
    agent.max_health = max_health
    agent.wounds = wounds
    agent.stuns = 0
    agent.is_stabilized = False
    agent.is_extracted = False
    agent._permanently_dead = False

    # Create character_state mock with attributes
    agent.character_state = MagicMock()
    agent.character_state.name = "Test Character"
    agent.character_state.attributes = config['attributes']

    return agent


class TestDeathSave:
    """Tests for check_death_save() and permanent death flag."""

    def test_no_death_save_below_5_wounds(self):
        """Characters with < 5 wounds don't need death saves."""
        player = create_test_player(health=0, wounds=4)

        alive, status = player.check_death_save()

        assert alive is True
        assert status == "conscious"
        assert player._permanently_dead is False

    def test_death_save_failure_sets_permanently_dead(self):
        """Failed death save sets _permanently_dead = True."""
        player = create_test_player(health=0, wounds=5, health_attr=1)

        # Force a low roll that will fail (DC=20, total=1*2+roll)
        with patch('scripts.aeonisk.multiagent.player.random.randint', return_value=2):
            alive, status = player.check_death_save()

        assert alive is False
        assert status == "dead"
        assert player._permanently_dead is True

    def test_death_save_fumble_sets_permanently_dead(self):
        """Natural 1 fumble sets _permanently_dead = True."""
        player = create_test_player(health=0, wounds=5)

        with patch('scripts.aeonisk.multiagent.player.random.randint', return_value=1):
            alive, status = player.check_death_save()

        assert alive is False
        assert status == "dead"
        assert player._permanently_dead is True

    def test_death_save_success_does_not_set_permanently_dead(self):
        """Successful death save leaves _permanently_dead = False."""
        player = create_test_player(health=0, wounds=5, health_attr=5)

        # High roll: total = 5*2 + 20 = 30, DC = 20 → success
        with patch('scripts.aeonisk.multiagent.player.random.randint', return_value=20):
            alive, status = player.check_death_save()

        assert alive is True
        assert status in ("conscious", "unconscious")
        assert player._permanently_dead is False

    def test_death_save_unconscious_does_not_set_permanently_dead(self):
        """Unconscious result leaves _permanently_dead = False."""
        player = create_test_player(health=0, wounds=5, health_attr=3)

        # Roll that passes DC but not by 10: total = 3*2 + 15 = 21, DC = 20 → success (unconscious)
        with patch('scripts.aeonisk.multiagent.player.random.randint', return_value=15):
            alive, status = player.check_death_save()

        assert alive is True
        assert status == "unconscious"
        assert player._permanently_dead is False


class TestIsAliveWithPermanentDeath:
    """Tests for is_alive property respecting _permanently_dead flag."""

    def test_is_alive_normal(self):
        """Normal living character is alive."""
        player = create_test_player(health=25)

        assert player.is_alive is True

    def test_is_alive_zero_hp(self):
        """Character at 0 HP is not alive."""
        player = create_test_player(health=0)

        assert player.is_alive is False

    def test_is_alive_permanently_dead(self):
        """Permanently dead character is never alive, even if health > 0."""
        player = create_test_player(health=25)
        player._permanently_dead = True

        assert player.is_alive is False

    def test_is_alive_permanently_dead_after_heal_attempt(self):
        """Permanently dead character remains dead even if health is set to 1.

        This is the resurrection bug scenario: character fails death save,
        then someone heals them to 1 HP. is_alive must still return False.
        """
        player = create_test_player(health=0, wounds=5)
        player._permanently_dead = True

        # Simulate what the healing pipeline WOULD do if the guard didn't catch it
        # (for defense in depth — is_alive should still report False)
        player.health = 1

        assert player.is_alive is False

    def test_is_conscious_permanently_dead(self):
        """Permanently dead character is not conscious."""
        player = create_test_player(health=25)
        player._permanently_dead = True

        assert player.is_conscious is False

    def test_is_in_combat_permanently_dead(self):
        """Permanently dead character is not in combat."""
        player = create_test_player(health=25)
        player._permanently_dead = True

        assert player.is_in_combat is False
