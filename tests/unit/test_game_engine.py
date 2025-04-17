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

    def test_get_attribute(self):
        """Test getting an attribute value."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 3, "Agility": 4},
            skills={}
        )
        
        assert character.get_attribute("Strength") == 3
        assert character.get_attribute("Agility") == 4
        assert character.get_attribute("Nonexistent") == 0

    def test_get_skill(self):
        """Test getting a skill value."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={},
            skills={"Athletics": 2, "Stealth": 3}
        )
        
        assert character.get_skill("Athletics") == 2
        assert character.get_skill("Stealth") == 3
        assert character.get_skill("Nonexistent") == 0

    @patch("random.randint")
    def test_skill_check_success(self, mock_randint):
        """Test a successful skill check."""
        # Mock the die roll to return 10
        mock_randint.return_value = 10
        
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 3},
            skills={"Athletics": 2}
        )
        
        # Ability = 3 * 2 = 6, Roll = 10, Total = 16
        # Difficulty = 15, so this should succeed
        success, margin = character.skill_check("Strength", "Athletics", 15)
        
        assert success is True
        assert margin == 1
        mock_randint.assert_called_once_with(1, 20)

    @patch("random.randint")
    def test_skill_check_failure(self, mock_randint):
        """Test a failed skill check."""
        # Mock the die roll to return 5
        mock_randint.return_value = 5
        
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 3},
            skills={"Athletics": 2}
        )
        
        # Ability = 3 * 2 = 6, Roll = 5, Total = 11
        # Difficulty = 15, so this should fail
        success, margin = character.skill_check("Strength", "Athletics", 15)
        
        assert success is False
        assert margin == -4
        mock_randint.assert_called_once_with(1, 20)

    @patch("random.randint")
    def test_skill_check_fumble(self, mock_randint):
        """Test a fumbled skill check."""
        # Mock the die roll to return 1 (fumble)
        mock_randint.return_value = 1
        
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 3},
            skills={"Athletics": 2}
        )
        
        # Ability = 3 * 2 = 6, Roll = 1, but this is a fumble
        # Difficulty = 15, so this should fail
        success, margin = character.skill_check("Strength", "Athletics", 15)
        
        assert success is False
        assert margin == 8  # difficulty - ability - roll = 15 - 6 - 1 = 8
        mock_randint.assert_called_once_with(1, 20)


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

    @patch("aeonisk.engine.game.Character.skill_check")
    def test_skill_check(self, mock_skill_check):
        """Test performing a skill check."""
        # Mock the character's skill_check method
        mock_skill_check.return_value = (True, 5)
        
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        success, margin, description = session.skill_check(character, "Strength", "Athletics", 15)
        
        assert success is True
        assert margin == 5
        assert "Success!" in description
        mock_skill_check.assert_called_once_with("Strength", "Athletics", 15)

    @patch("aeonisk.openai.client.generate_scenario")
    def test_generate_scenario(self, mock_generate_scenario):
        """Test generating a scenario."""
        # Mock the OpenAI client's generate_scenario function
        mock_generate_scenario.return_value = {"title": "Test Scenario"}
        
        session = GameSession()
        scenario = session.generate_scenario(theme="test", difficulty="easy")
        
        assert scenario == {"title": "Test Scenario"}
        assert session.scenario == {"title": "Test Scenario"}
        mock_generate_scenario.assert_called_once_with(theme="test", difficulty="easy", characters=[])

    @patch("aeonisk.openai.client.generate_npc")
    def test_generate_npc(self, mock_generate_npc):
        """Test generating an NPC."""
        # Mock the OpenAI client's generate_npc function
        mock_generate_npc.return_value = {"name": "Test NPC"}
        
        session = GameSession()
        npc = session.generate_npc(faction="test", role="test")
        
        assert npc == {"name": "Test NPC"}
        assert session.npcs == [{"name": "Test NPC"}]
        mock_generate_npc.assert_called_once_with(faction="test", role="test")

    @patch("aeonisk.openai.client.get_client")
    def test_process_player_action(self, mock_get_client):
        """Test processing a player action."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "Test result"
        mock_get_client.return_value = mock_client
        
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        result = session.process_player_action(character, "Test action")
        
        assert result == "Test result"
        mock_client.generate_text.assert_called_once()
        args, kwargs = mock_client.generate_text.call_args
        assert kwargs["prompt"].startswith("Character: Test Character (Test Concept)")
        assert "Action: Test action" in kwargs["prompt"]

    def test_save_and_load_session(self, tmp_path):
        """Test saving and loading a session."""
        # Create a session with a character and scenario
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        session.scenario = {"title": "Test Scenario"}
        session.npcs = [{"name": "Test NPC"}]
        
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
        assert new_session.scenario == {"title": "Test Scenario"}
        assert new_session.npcs == [{"name": "Test NPC"}]
