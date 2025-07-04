"""
Unit tests for the game engine module.
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from aeonisk.engine.game import Character, GameSession


class TestCharacter:
    """Test suite for the Character class."""

    def test_character_initialization(self):
        """Test that a character can be initialized."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 3, "Agility": 4},
            skills={"Athletics": 2, "Stealth": 3}
        )
        
        assert character.name == "Test Character"
        assert character.concept == "Test Concept"
        assert character.attributes["Strength"] == 3
        assert character.attributes["Agility"] == 4
        assert character.skills["Athletics"] == 2
        assert character.skills["Stealth"] == 3
        assert character.void_score == 0
        assert character.soulcredit == 0
        assert character.bonds == []
        assert character.true_will is None
        assert character.equipment == []


class TestGameSession:
    """Test suite for the GameSession class."""


    def test_session_initialization(self):
        """Test that a session can be initialized."""
        session = GameSession()
        
        assert session.characters == []
        assert session.npcs == []
        assert session.scenario is None

    @patch("aeonisk.engine.game.DatasetParser")
    def test_session_initialization_with_dataset(self, mock_parser_class):
        """Test that a session can be initialized with a dataset."""
        # Mock the dataset parser
        mock_parser = MagicMock()
        mock_parser.parse_file.return_value = {"test": "data"}
        mock_parser_class.return_value = mock_parser
        
        session = GameSession()
        
        assert session.dataset == {"test": "data"}
        mock_parser.parse_file.assert_called_once_with("datasets/aeonisk-dataset-v1.0.1.txt")

    def test_create_character(self):
        """Test creating a character."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        assert character.name == "Test Character"
        assert character.concept == "Test Concept"
        assert character in session.characters
        assert len(session.characters) == 1
        assert session.current_character == character # Ensure new character is selected

    @patch("random.randint")
    def test_skill_check(self, mock_randint):
        """Test performing a skill check via the GameSession."""
        # Mock the die roll
        mock_randint.return_value = 10
        
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.attributes["Strength"] = 3
        character.skills["Athletics"] = 2
        
        # Ability = 3 * 2 = 6, Roll = 10, Total = 16
        # Difficulty = 15, so this should succeed
        success, margin, description = session.skill_check(character, "Strength", "Athletics", 15)
        
        assert success is True
        assert margin == 1
        assert "Success!" in description
        mock_randint.assert_called_once_with(1, 20)

    def test_generate_scenario(self):
        """Test generating a scenario."""
        # Create a session with a character
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Mock the OpenAI client's generate_scenario function
        with patch("aeonisk.aeonisk_openai.client.generate_scenario") as mock_generate_scenario:
            mock_generate_scenario.return_value = {"title": "Test Scenario"}
            
            # Generate the scenario
            scenario = session.generate_scenario(theme="test", difficulty="easy")
            
            # Check the results
            assert scenario == {"title": "Test Scenario"}
            assert session.scenario.title == "Test Scenario" # Check model attribute
            mock_generate_scenario.assert_called_once()
            # Check that the call included the expected arguments
            args, kwargs = mock_generate_scenario.call_args
            assert kwargs["theme"] == "test"
            assert kwargs["difficulty"] == "easy"
            assert len(kwargs["characters"]) == 1
            assert kwargs["characters"][0]["name"] == "Test Character"

    @patch("aeonisk.aeonisk_openai.client.generate_npc")
    def test_generate_npc(self, mock_generate_npc):
        """Test generating an NPC."""
        # Mock the OpenAI client's generate_npc function
        mock_generate_npc.return_value = {"name": "Test NPC"}
        
        session = GameSession()
        npc = session.generate_npc(faction="test", role="test")
        
        assert npc == {"name": "Test NPC"}
        assert len(session.npcs) == 1
        assert session.npcs[0].name == "Test NPC" # Check model attribute
        mock_generate_npc.assert_called_once_with(faction="test", role="test")

    @patch("aeonisk.aeonisk_openai.client.analyze_player_action")
    @patch("aeonisk.aeonisk_openai.client.format_game_response")
    def test_process_player_action(self, mock_format_response, mock_analyze_action):
        """Test processing a player action."""
        # Mock the OpenAI client functions
        mock_analyze_action.return_value = {
            "narrative_response": "Narrative result",
            "void_change": 1,
            "soulcredit_change": -1,
            "attribute": "Strength",
            "skill": "Brawl",
            "difficulty": 15,
            "roll": 12,
            "total": 18, # Assuming Str 3, Brawl 2 -> 3*2=6 + 12 = 18
            "success": True,
            "margin": 3
        }
        mock_format_response.return_value = "Formatted result"
        
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.attributes["Strength"] = 3
        character.skills["Brawl"] = 2
        initial_void = character.void_score
        initial_sc = character.soulcredit
        
        result = session.process_player_action(character, "Punch the guard")
        
        assert result == "Formatted result"
        mock_analyze_action.assert_called_once()
        # Check that character state was updated
        assert character.void_score == initial_void + 1
        assert character.soulcredit == initial_sc - 1
        # Check that action was recorded
        assert len(session.actions) == 1
        assert session.actions[0].action_text == "Punch the guard"
        assert session.actions[0].void_change == 1
        assert len(session.actions[0].skill_checks) == 1
        assert session.actions[0].skill_checks[0].skill == "Brawl"

    def test_save_and_load_session(self, tmp_path):
        """Test saving and loading a session."""
        # Create a session with a character and scenario
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        # Use the generate_scenario method to set the scenario model correctly
        with patch("aeonisk.aeonisk_openai.client.generate_scenario") as mock_gen_scenario:
            mock_gen_scenario.return_value = {"title": "Test Scenario"}
            session.generate_scenario() 
        # Use the generate_npc method to add NPC model correctly
        with patch("aeonisk.aeonisk_openai.client.generate_npc") as mock_gen_npc:
            mock_gen_npc.return_value = {"name": "Test NPC"}
            session.generate_npc()
        
        # Save the session
        file_path = tmp_path / "test_session.json"
        success = session.save_session(file_path)
        
        assert success is True
        assert file_path.exists()
        
        # Create a new session and load the saved session
        new_session = GameSession()
        success = new_session.load_session(file_path)
        
        assert success is True
        assert len(new_session.characters) == 1
        assert new_session.characters[0].name == "Test Character"
        assert new_session.characters[0].concept == "Test Concept"
        assert new_session.scenario.title == "Test Scenario" # Check model attribute
        assert len(new_session.npcs) == 1
        assert new_session.npcs[0].name == "Test NPC" # Check model attribute
