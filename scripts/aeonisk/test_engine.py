"""
Comprehensive test suite for the Aeonisk YAGS engine system.

This test suite covers the interactive game engine, CLI functionality,
and game session management. All external API calls are mocked.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json

from aeonisk.engine.cli import GameCLI
from aeonisk.engine.game import GameSession
from aeonisk.core.models import Character, NPC, Scenario, PlayerAction, SkillCheck


class TestGameCLI:
    """Test suite for the GameCLI class."""
    
    def test_cli_initialization(self):
        """Test CLI initialization."""
        cli = GameCLI()
        
        assert cli.session is not None
        assert cli.show_mechanics is True
    
    def test_process_command_help(self):
        """Test processing help command."""
        cli = GameCLI()
        
        with patch('builtins.print') as mock_print:
            cli.process_command('help')
        
        mock_print.assert_called()
        # Check that help text was printed
        args, kwargs = mock_print.call_args_list[0]
        assert 'Available commands' in args[0]
    
    def test_process_command_start_game(self):
        """Test processing start game command."""
        cli = GameCLI()
        
        with patch('builtins.print') as mock_print:
            cli.process_command('start test_game')
        
        mock_print.assert_called()
        # Check that game started message was printed
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Started a new game' in msg for msg in printed_messages)
    
    def test_process_command_create_character(self):
        """Test processing create character command."""
        cli = GameCLI()
        
        with patch('builtins.print') as mock_print:
            cli.process_command('create TestChar "Brave Warrior"')
        
        # Check that character was created
        assert len(cli.session.characters) == 1
        assert cli.session.characters[0].name == 'TestChar'
        assert cli.session.characters[0].concept == 'Brave Warrior'
        
        # Check that success message was printed
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Created character' in msg for msg in printed_messages)
    
    def test_process_command_list_characters_empty(self):
        """Test listing characters when none exist."""
        cli = GameCLI()
        
        with patch('builtins.print') as mock_print:
            cli.process_command('list')
        
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('No characters' in msg for msg in printed_messages)
    
    def test_process_command_list_characters_with_characters(self):
        """Test listing characters when they exist."""
        cli = GameCLI()
        
        # Create a character first
        cli.process_command('create TestChar "Test Concept"')
        
        with patch('builtins.print') as mock_print:
            cli.process_command('list')
        
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Characters:' in msg for msg in printed_messages)
        assert any('TestChar' in msg for msg in printed_messages)
    
    def test_process_command_select_character(self):
        """Test selecting a character."""
        cli = GameCLI()
        
        # Create a character first
        cli.process_command('create TestChar "Test Concept"')
        
        with patch('builtins.print') as mock_print:
            cli.process_command('select 0')
        
        # Check that character was selected
        assert cli.session.current_character is not None
        assert cli.session.current_character.name == 'TestChar'
        
        # Check that success message was printed
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Selected character' in msg for msg in printed_messages)
    
    def test_process_command_show_character(self):
        """Test showing character details."""
        cli = GameCLI()
        
        # Create and select a character first
        cli.process_command('create TestChar "Test Concept"')
        cli.process_command('select 0')
        
        with patch('builtins.print') as mock_print:
            cli.process_command('character')
        
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Character: TestChar' in msg for msg in printed_messages)
    
    def test_process_command_show_character_none_selected(self):
        """Test showing character details when none selected."""
        cli = GameCLI()
        
        with patch('builtins.print') as mock_print:
            cli.process_command('character')
        
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('No character selected' in msg for msg in printed_messages)
    
    @patch('aeonisk.engine.cli.GameSession.skill_check')
    def test_process_command_skill_check(self, mock_skill_check):
        """Test processing skill check command."""
        cli = GameCLI()
        
        # Create and select a character first
        cli.process_command('create TestChar "Test Concept"')
        cli.process_command('select 0')
        
        # Mock skill check result
        mock_skill_check.return_value = (True, 5, "Success! The character performs excellently.")
        
        with patch('builtins.print') as mock_print:
            cli.process_command('check Agility Athletics 20')
        
        mock_skill_check.assert_called_once()
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('[NARRATIVE]' in msg for msg in printed_messages)
        assert any('Success!' in msg for msg in printed_messages)
    
    @patch('aeonisk.engine.cli.GameSession.generate_scenario')
    def test_process_command_generate_scenario(self, mock_generate_scenario):
        """Test processing generate scenario command."""
        cli = GameCLI()
        
        # Mock scenario generation
        mock_scenario = {
            "Scenario Overview": {
                "Theme": "Mystery",
                "Difficulty": "Moderate",
                "Setting": "Urban",
                "Objective": "Solve the case"
            },
            "Setting Description": {
                "Location": "Dark alley",
                "Atmosphere": "Tense"
            },
            "Key NPCs": {
                "Detective": {
                    "Role": "Law enforcement"
                }
            },
            "Plot Hooks": [
                "A mysterious package",
                "Strange footprints"
            ]
        }
        mock_generate_scenario.return_value = mock_scenario
        
        with patch('builtins.print') as mock_print:
            cli.process_command('scenario mystery moderate')
        
        mock_generate_scenario.assert_called_once()
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('[SCENARIO]' in msg for msg in printed_messages)
        assert any('Mystery' in msg for msg in printed_messages)
    
    @patch('aeonisk.engine.cli.GameSession.generate_npc')
    def test_process_command_generate_npc(self, mock_generate_npc):
        """Test processing generate NPC command."""
        cli = GameCLI()
        
        # Mock NPC generation
        mock_npc = {
            "name": "John Doe",
            "faction": "Resistance",
            "concept": "Skilled hacker",
            "description": "A mysterious figure in the shadows",
            "attributes": {
                "Intelligence": 5,
                "Dexterity": 4
            },
            "skills": {
                "Hacking": 5,
                "Stealth": 4
            }
        }
        mock_generate_npc.return_value = mock_npc
        
        with patch('builtins.print') as mock_print:
            cli.process_command('npc resistance hacker')
        
        mock_generate_npc.assert_called_once()
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('[NPC]' in msg for msg in printed_messages)
        assert any('John Doe' in msg for msg in printed_messages)
    
    @patch('aeonisk.engine.cli.GameSession.process_player_action')
    def test_process_command_player_action(self, mock_process_action):
        """Test processing player actions."""
        cli = GameCLI()
        
        # Create and select a character first
        cli.process_command('create TestChar "Test Concept"')
        cli.process_command('select 0')
        
        # Mock action processing
        mock_process_action.return_value = "The character moves stealthily through the shadows."
        
        with patch('builtins.print') as mock_print:
            cli.process_command('look around')
        
        mock_process_action.assert_called_once()
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('shadows' in msg for msg in printed_messages)
    
    def test_process_command_toggle_mechanics(self):
        """Test toggling mechanics display."""
        cli = GameCLI()
        
        initial_setting = cli.show_mechanics
        
        with patch('builtins.print') as mock_print:
            cli.process_command('mechanics')
        
        assert cli.show_mechanics != initial_setting
        mock_print.assert_called()
    
    @patch('aeonisk.engine.cli.GameSession.save_session')
    def test_process_command_save_session(self, mock_save_session):
        """Test saving a session."""
        cli = GameCLI()
        
        # Mock successful save
        mock_save_session.return_value = True
        
        with patch('builtins.print') as mock_print:
            cli.process_command('save test_session.json')
        
        mock_save_session.assert_called_once_with('test_session.json')
        mock_print.assert_called()
        printed_messages = [call[0][0] for call in mock_print.call_args_list]
        assert any('Session saved' in msg for msg in printed_messages)
    
    def test_process_command_unknown_command(self):
        """Test processing unknown command (should be treated as action)."""
        cli = GameCLI()
        
        # Create and select a character first
        cli.process_command('create TestChar "Test Concept"')
        cli.process_command('select 0')
        
        with patch('aeonisk.engine.cli.GameSession.process_player_action') as mock_process:
            mock_process.return_value = "Unknown action result"
            
            with patch('builtins.print') as mock_print:
                cli.process_command('unknown_command')
            
            mock_process.assert_called_once()
            mock_print.assert_called()


class TestGameSession:
    """Test suite for the GameSession class."""
    
    def test_session_initialization(self):
        """Test session initialization."""
        session = GameSession()
        
        assert session.characters == []
        assert session.scenario is None
        assert session.current_character is None
    
    def test_create_character(self):
        """Test creating a character."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        assert character.name == "TestChar"
        assert character.concept == "Test Concept"
        assert len(session.characters) == 1
        assert session.current_character == character
    
    def test_select_character(self):
        """Test selecting a character."""
        session = GameSession()
        
        # Create two characters
        char1 = session.create_character("Char1", "Concept1")
        char2 = session.create_character("Char2", "Concept2")
        
        # Select the first character
        selected = session.select_character(0)
        
        assert selected == char1
        assert session.current_character == char1
        
        # Select the second character
        selected = session.select_character(1)
        
        assert selected == char2
        assert session.current_character == char2
    
    def test_select_character_invalid_index(self):
        """Test selecting character with invalid index."""
        session = GameSession()
        
        # Create one character
        session.create_character("TestChar", "Test Concept")
        
        # Try to select invalid index
        selected = session.select_character(5)
        
        assert selected is None
    
    def test_skill_check(self):
        """Test performing a skill check."""
        session = GameSession()
        
        # Create a character
        character = session.create_character("TestChar", "Test Concept")
        
        # Mock random roll
        with patch('random.randint', return_value=15):
            success, margin, description = session.skill_check(character, "Agility", "Athletics", 20)
        
        # Calculate expected values
        ability = character.attributes["Agility"] * character.skills["Athletics"]
        total = ability + 15
        expected_success = total >= 20
        expected_margin = total - 20
        
        assert success == expected_success
        assert margin == expected_margin
        assert isinstance(description, str)
        assert len(description) > 0
    
    @patch('aeonisk.openai.generate_scenario')
    def test_generate_scenario(self, mock_generate_scenario):
        """Test generating a scenario."""
        session = GameSession()
        
        # Mock scenario generation
        mock_scenario = {
            "Scenario Overview": {
                "Theme": "Mystery",
                "Difficulty": "Moderate"
            }
        }
        mock_generate_scenario.return_value = mock_scenario
        
        result = session.generate_scenario(theme="mystery", difficulty="moderate")
        
        assert result == mock_scenario
        assert session.scenario is not None
        mock_generate_scenario.assert_called_once()
    
    @patch('aeonisk.openai.generate_npc')
    def test_generate_npc(self, mock_generate_npc):
        """Test generating an NPC."""
        session = GameSession()
        
        # Mock NPC generation
        mock_npc = {
            "name": "John Doe",
            "faction": "Resistance",
            "concept": "Skilled hacker"
        }
        mock_generate_npc.return_value = mock_npc
        
        result = session.generate_npc(faction="resistance", role="hacker")
        
        assert result == mock_npc
        assert len(session.npcs) == 1
        mock_generate_npc.assert_called_once()
    
    @patch('aeonisk.openai.analyze_player_action')
    def test_process_player_action(self, mock_analyze_action):
        """Test processing a player action."""
        session = GameSession()
        
        # Create a character
        character = session.create_character("TestChar", "Test Concept")
        
        # Mock action analysis
        mock_analysis = {
            "narrative_response": "The character moves stealthily.",
            "success": True,
            "void_change": 0,
            "soulcredit_change": 1
        }
        mock_analyze_action.return_value = mock_analysis
        
        result = session.process_player_action(character, "move stealthily")
        
        assert "stealthily" in result
        assert len(session.actions) == 1
        mock_analyze_action.assert_called_once()
    
    def test_save_session(self):
        """Test saving a session."""
        session = GameSession()
        
        # Create some session data
        session.create_character("TestChar", "Test Concept")
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                result = session.save_session("test_session.json")
        
        assert result is True
        mock_file.assert_called_once_with("test_session.json", "w")
        mock_json_dump.assert_called_once()
    
    def test_save_session_error(self):
        """Test saving a session with error."""
        session = GameSession()
        
        with patch('builtins.open', side_effect=IOError("Permission denied")):
            result = session.save_session("test_session.json")
        
        assert result is False
    
    def test_load_session(self):
        """Test loading a session."""
        session = GameSession()
        
        # Mock session data
        session_data = {
            "characters": [
                {
                    "name": "TestChar",
                    "concept": "Test Concept",
                    "attributes": {"Agility": 3, "Willpower": 3},
                    "skills": {"Athletics": 2, "Stealth": 3}
                }
            ],
            "scenario": {
                "title": "Test Scenario",
                "theme": "Mystery"
            },
            "npcs": [],
            "actions": []
        }
        
        with patch('builtins.open', mock_open()):
            with patch('json.load', return_value=session_data):
                result = session.load_session("test_session.json")
        
        assert result is True
        assert len(session.characters) == 1
        assert session.characters[0].name == "TestChar"
        assert session.scenario is not None
    
    def test_load_session_error(self):
        """Test loading a session with error."""
        session = GameSession()
        
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            result = session.load_session("nonexistent.json")
        
        assert result is False


class TestCharacterCreation:
    """Test suite for character creation functionality."""
    
    def test_create_character_with_defaults(self):
        """Test creating a character with default values."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        assert character.name == "TestChar"
        assert character.concept == "Test Concept"
        assert character.void_score == 0
        assert character.soulcredit == 0
        assert character.current_cycle == 0
        assert len(character.attributes) > 0
        assert len(character.skills) > 0
        assert "Agility" in character.attributes
        assert "Athletics" in character.skills
        assert "Attunement" in character.skills
        assert "Dreamwork" in character.skills
    
    def test_create_character_with_custom_attributes(self):
        """Test creating a character with custom attributes."""
        session = GameSession()
        
        # Create character with custom attributes
        character = session.create_character("TestChar", "Test Concept")
        
        # Modify attributes
        character.attributes["Strength"] = 5
        character.skills["Combat"] = 4
        character.void_score = 2
        character.soulcredit = -1
        
        assert character.attributes["Strength"] == 5
        assert character.skills["Combat"] == 4
        assert character.void_score == 2
        assert character.soulcredit == -1
    
    def test_character_seed_tracking(self):
        """Test character seed tracking functionality."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        # Add raw seeds
        raw_seed = {"id": "seed1", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed)
        
        # Add attuned seeds
        character.attuned_seeds["Spark"] = 2
        character.attuned_seeds["Grain"] = 3
        
        assert len(character.raw_seeds) == 1
        assert character.raw_seeds[0]["id"] == "seed1"
        assert character.attuned_seeds["Spark"] == 2
        assert character.attuned_seeds["Grain"] == 3
    
    def test_character_bonds(self):
        """Test character bonds functionality."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        # Add bonds
        bond1 = {"name": "Old Friend", "type": "Kinship", "strength": 3}
        bond2 = {"name": "Mentor", "type": "Respect", "strength": 4}
        character.bonds = [bond1, bond2]
        
        assert len(character.bonds) == 2
        assert character.bonds[0]["name"] == "Old Friend"
        assert character.bonds[1]["name"] == "Mentor"


class TestGameMechanics:
    """Test suite for game mechanics functionality."""
    
    def test_skill_check_calculation(self):
        """Test skill check calculation."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        # Set specific attribute and skill values
        character.attributes["Agility"] = 4
        character.skills["Athletics"] = 3
        
        # Mock specific roll
        with patch('random.randint', return_value=10):
            success, margin, description = session.skill_check(character, "Agility", "Athletics", 20)
        
        # Calculate expected values
        ability = 4 * 3  # 12
        total = ability + 10  # 22
        expected_success = total >= 20  # True
        expected_margin = total - 20  # 2
        
        assert success == expected_success
        assert margin == expected_margin
        assert isinstance(description, str)
    
    def test_skill_check_critical_success(self):
        """Test skill check with critical success."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        # Set high values and roll for critical success
        character.attributes["Agility"] = 5
        character.skills["Athletics"] = 4
        
        with patch('random.randint', return_value=20):
            success, margin, description = session.skill_check(character, "Agility", "Athletics", 15)
        
        # Calculate expected values
        ability = 5 * 4  # 20
        total = ability + 20  # 40
        expected_success = True
        expected_margin = total - 15  # 25
        
        assert success == expected_success
        assert margin == expected_margin
        assert "critical" in description.lower() or "exceptional" in description.lower()
    
    def test_skill_check_critical_failure(self):
        """Test skill check with critical failure."""
        session = GameSession()
        
        character = session.create_character("TestChar", "Test Concept")
        
        # Set low values and roll for critical failure
        character.attributes["Agility"] = 2
        character.skills["Athletics"] = 1
        
        with patch('random.randint', return_value=1):
            success, margin, description = session.skill_check(character, "Agility", "Athletics", 25)
        
        # Calculate expected values
        ability = 2 * 1  # 2
        total = ability + 1  # 3
        expected_success = False
        expected_margin = total - 25  # -22
        
        assert success == expected_success
        assert margin == expected_margin
        assert "critical" in description.lower() or "catastrophic" in description.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])