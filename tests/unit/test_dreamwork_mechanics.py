"""
Unit tests for the Dreamwork mechanics in the game engine.
"""

import pytest
from unittest.mock import patch, MagicMock
from aeonisk.engine.game import GameSession, Character


class TestDreamworkMechanics:
    """Test suite for Dreamwork mechanics."""

    def test_dream_occurrence_during_rest(self):
        """Test that a dream can occur during rest."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Mock the random chance for a dream to occur
        with patch("random.random", return_value=0.1):  # Assume 10% chance
            # Mock the dream outcome to ensure it contains "dream" in the message
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "void_change", "change": 1, "message": "A dream message"}):
                dream_event = session.handle_rest(character)
                
                assert dream_event is not None
                assert "dream" in dream_event.lower()

    def test_no_dream_occurrence_during_rest(self):
        """Test that a dream might not occur during rest."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Mock the random chance for no dream to occur
        with patch("random.random", return_value=0.9):  # Assume 90% chance of no dream
            dream_event = session.handle_rest(character)
            
            assert "peacefully" in dream_event.lower() or "no dreams" in dream_event.lower()

    def test_dream_effects_bond_shift(self):
        """Test that a dream can cause a Bond shift."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a Bond to the character
        bond = {"name": "Test Bond", "type": "Kinship", "strength": 2}
        character.bonds.append(bond)
        
        # Mock both random chance and dream outcome
        with patch("random.random", return_value=0.1):  # Ensure dream occurs
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "bond_shift", "target_bond": "Test Bond", "change": 1, "message": "Bond shift message"}):
                dream_event = session.handle_rest(character)
                
                assert "bond" in dream_event.lower()
                assert character.bonds[0]["strength"] == 3

    def test_dream_effects_void_gain(self):
        """Test that a dream can cause Void gain."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 1
        
        # Mock both random chance and dream outcome
        with patch("random.random", return_value=0.1):  # Ensure dream occurs
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "void_change", "change": 1, "message": "Void gain message"}):
                dream_event = session.handle_rest(character)
                
                assert "void" in dream_event.lower()
                assert "increase" in dream_event.lower()
                assert character.void_score == 2

    def test_dream_effects_void_loss(self):
        """Test that a dream can cause Void loss."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 3
        
        # Mock both random chance and dream outcome
        with patch("random.random", return_value=0.1):  # Ensure dream occurs
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "void_change", "change": -1, "message": "Void loss message"}):
                dream_event = session.handle_rest(character)
                
                assert "void" in dream_event.lower()
                assert "decrease" in dream_event.lower()
                assert character.void_score == 2

    def test_dream_effects_insight(self):
        """Test that a dream can provide insight."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Mock both random chance and dream outcome
        with patch("random.random", return_value=0.1):  # Ensure dream occurs
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "insight", "message": "Test insight"}):
                dream_event = session.handle_rest(character)
                
                assert "insight" in dream_event.lower()
                assert "Test insight" in dream_event

    def test_dreamwork_skill_check(self):
        """Test that Dreamwork skill can be used to influence dreams."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.skills["Dreamwork"] = 4
        
        # Mock the skill check to succeed
        with patch.object(session, 'skill_check', return_value=(True, 5, "Success")):
            # Mock the dream outcome generation
            with patch.object(session, '_generate_dream_outcome') as mock_generate:
                session.handle_dream_event(character, "lucid_dreaming")
                
                # Verify that skill_check was called with Dreamwork skill
                session.skill_check.assert_called_once_with(
                    character, "Willpower", "Dreamwork", pytest.approx(18, abs=4)
                )
                
                # Verify that the dream outcome was influenced (e.g., more positive)
                # This requires more complex mocking of _generate_dream_outcome based on skill check result
                # For now, just assert that the skill check was made
                assert mock_generate.called

    def test_shared_dream(self):
        """Test that Bonded characters can experience shared dreams."""
        session = GameSession()
        char1 = session.create_character("Char1", "Concept1")
        char2 = session.create_character("Char2", "Concept2")
        
        # Create a Bond between the characters
        bond1 = {"name": "Bond1", "type": "Kinship", "partner": "Char2"}
        bond2 = {"name": "Bond1", "type": "Kinship", "partner": "Char1"}
        char1.bonds.append(bond1)
        char2.bonds.append(bond2)
        
        # Mock both random chance and dream generation
        with patch("random.random", return_value=0.1):  # Ensure dream occurs
            with patch.object(session, '_generate_dream_outcome', return_value={"effect": "shared_dream", "participants": ["Char1", "Char2"], "scene": "Shared dream scene", "message": "Shared dream scene"}):
                dream_event1 = session.handle_rest(char1)
                
                assert "shared dream" in dream_event1.lower()
                assert "shared dream scene" in dream_event1.lower()
                # In a real implementation, ensure both characters get the same shared dream event
                # This might require tracking active shared dreams in the session
