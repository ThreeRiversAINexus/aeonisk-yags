"""
Comprehensive test suite for the Aeonisk YAGS OpenAI client.

This test suite covers the OpenAI API integration, including scenario generation,
character analysis, and NPC creation. All API calls are mocked to prevent costs.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from aeonisk.aeonisk_openai.client import OpenAIClient, get_client


class TestOpenAIClient:
    """Test suite for the OpenAI client functionality."""
    
    def test_client_initialization_with_api_key(self):
        """Test client initialization with provided API key."""
        client = OpenAIClient(api_key="test_key", model="gpt-4")
        
        assert client.api_key == "test_key"
        assert client.model == "gpt-4"
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'env_test_key'})
    def test_client_initialization_from_env(self):
        """Test client initialization from environment variable."""
        client = OpenAIClient()
        
        assert client.api_key == "env_test_key"
        assert client.model == "gpt-4o"  # Default model
    
    def test_client_initialization_no_api_key(self):
        """Test client initialization without API key raises error."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI API key is required"):
                OpenAIClient()
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_text_success(self, mock_openai_create):
        """Test successful text generation."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Generated text response"
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_text("Test prompt")
        
        assert result == "Generated text response"
        mock_openai_create.assert_called_once()
        
        # Check the call arguments
        call_args = mock_openai_create.call_args
        assert call_args[1]['model'] == "gpt-4o"
        assert len(call_args[1]['messages']) == 1
        assert call_args[1]['messages'][0]['content'] == "Test prompt"
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_text_with_system_message(self, mock_openai_create):
        """Test text generation with system message."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Generated text response"
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_text("Test prompt", system_message="You are a helpful assistant")
        
        assert result == "Generated text response"
        mock_openai_create.assert_called_once()
        
        # Check the call arguments
        call_args = mock_openai_create.call_args
        assert len(call_args[1]['messages']) == 2
        assert call_args[1]['messages'][0]['role'] == 'system'
        assert call_args[1]['messages'][0]['content'] == "You are a helpful assistant"
        assert call_args[1]['messages'][1]['role'] == 'user'
        assert call_args[1]['messages'][1]['content'] == "Test prompt"
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_text_error(self, mock_openai_create):
        """Test text generation with API error."""
        mock_openai_create.side_effect = Exception("API Error")
        
        client = OpenAIClient(api_key="test_key")
        
        with pytest.raises(Exception, match="API Error"):
            client.generate_text("Test prompt")
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_scenario_success(self, mock_openai_create):
        """Test successful scenario generation."""
        # Mock OpenAI response with JSON
        scenario_json = {
            "Scenario Overview": {
                "Theme": "Cyberpunk",
                "Difficulty": "Moderate",
                "Setting": "Neo-Tokyo",
                "Objective": "Infiltrate the corporation"
            },
            "Setting Description": {
                "Location": "Corporate tower",
                "Atmosphere": "High-tech dystopia"
            },
            "Key NPCs": {
                "Corporate Executive": {
                    "Role": "Antagonist"
                }
            },
            "Plot Hooks": [
                "Mysterious data breach",
                "Missing person"
            ]
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = f"Here's the scenario: {json.dumps(scenario_json)}"
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario(theme="cyberpunk", difficulty="moderate")
        
        assert result == scenario_json
        mock_openai_create.assert_called_once()
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_scenario_invalid_json(self, mock_openai_create):
        """Test scenario generation with invalid JSON response."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is not valid JSON content"
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario(theme="cyberpunk")
        
        # Should return raw response when JSON parsing fails
        assert "raw_response" in result
        assert result["raw_response"] == "This is not valid JSON content"
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_scenario_with_characters(self, mock_openai_create):
        """Test scenario generation with character list."""
        scenario_json = {
            "Scenario Overview": {
                "Theme": "Adventure",
                "Difficulty": "Easy"
            }
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(scenario_json)
        mock_openai_create.return_value = mock_response
        
        characters = [
            {"name": "Alice", "concept": "Hacker"},
            {"name": "Bob", "concept": "Warrior"}
        ]
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario(
            theme="adventure",
            difficulty="easy",
            characters=characters
        )
        
        assert result == scenario_json
        mock_openai_create.assert_called_once()
        
        # Check that characters were included in the prompt
        call_args = mock_openai_create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "Alice" in prompt
        assert "Bob" in prompt
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_analyze_player_action_success(self, mock_openai_create):
        """Test successful player action analysis."""
        analysis_json = {
            "attribute": "Agility",
            "skill": "Stealth",
            "attribute_value": 3,
            "skill_value": 4,
            "difficulty": 18,
            "roll": 15,
            "total": 27,
            "success": True,
            "margin": 9,
            "narrative_response": "The character moves silently through the shadows.",
            "void_change": 0,
            "soulcredit_change": 1
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(analysis_json)
        mock_openai_create.return_value = mock_response
        
        character = {
            "name": "TestChar",
            "concept": "Stealthy operative",
            "attributes": {"Agility": 3, "Strength": 2},
            "skills": {"Stealth": 4, "Athletics": 2},
            "void_score": 0,
            "soulcredit": 5
        }
        
        client = OpenAIClient(api_key="test_key")
        result = client.analyze_player_action(character, "sneak past the guards")
        
        assert result == analysis_json
        mock_openai_create.assert_called_once()
        
        # Check that character information was included
        call_args = mock_openai_create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "TestChar" in prompt
        assert "Stealthy operative" in prompt
        assert "sneak past the guards" in prompt
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_analyze_player_action_with_scenario(self, mock_openai_create):
        """Test player action analysis with scenario context."""
        analysis_json = {
            "attribute": "Intelligence",
            "skill": "Hacking",
            "narrative_response": "The character attempts to hack the security system.",
            "success": True,
            "void_change": 0,
            "soulcredit_change": 0
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(analysis_json)
        mock_openai_create.return_value = mock_response
        
        character = {
            "name": "Hacker",
            "concept": "Digital infiltrator",
            "attributes": {"Intelligence": 5},
            "skills": {"Hacking": 6},
            "void_score": 0,
            "soulcredit": 0
        }
        
        scenario = {
            "overview": "Corporate infiltration mission",
            "setting": {
                "location": "Corporate headquarters",
                "atmosphere": "High security"
            }
        }
        
        client = OpenAIClient(api_key="test_key")
        result = client.analyze_player_action(
            character,
            "hack the security system",
            scenario=scenario
        )
        
        assert result == analysis_json
        mock_openai_create.assert_called_once()
        
        # Check that scenario information was included
        call_args = mock_openai_create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "Corporate infiltration" in prompt
        assert "Corporate headquarters" in prompt
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_analyze_player_action_invalid_json(self, mock_openai_create):
        """Test player action analysis with invalid JSON response."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Invalid response format"
        mock_openai_create.return_value = mock_response
        
        character = {
            "name": "TestChar",
            "concept": "Test concept",
            "attributes": {"Agility": 3},
            "skills": {"Stealth": 2},
            "void_score": 0,
            "soulcredit": 0
        }
        
        client = OpenAIClient(api_key="test_key")
        result = client.analyze_player_action(character, "test action")
        
        # Should return fallback response when JSON parsing fails
        assert "narrative_response" in result
        assert result["narrative_response"] == "Invalid response format"
        assert result["success"] is True
        assert result["void_change"] == 0
        assert result["soulcredit_change"] == 0
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_npc_success(self, mock_openai_create):
        """Test successful NPC generation."""
        npc_json = {
            "name": "Marcus Steel",
            "faction": "Corporate Security",
            "concept": "Veteran enforcer",
            "description": "A grizzled security chief with cybernetic implants",
            "attributes": {
                "Strength": 4,
                "Health": 5,
                "Agility": 3,
                "Intelligence": 3
            },
            "skills": {
                "Combat": 5,
                "Security": 4,
                "Intimidation": 4
            },
            "motivation": "Protect corporate interests",
            "background": "Former military, now corporate security"
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(npc_json)
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_npc(
            faction="Corporate Security",
            role="Security Chief",
            importance="major"
        )
        
        assert result == npc_json
        mock_openai_create.assert_called_once()
        
        # Check that parameters were included in the prompt
        call_args = mock_openai_create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "Corporate Security" in prompt
        assert "Security Chief" in prompt
        assert "major" in prompt
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_npc_minimal_params(self, mock_openai_create):
        """Test NPC generation with minimal parameters."""
        npc_json = {
            "name": "Random Person",
            "concept": "Ordinary citizen"
        }
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(npc_json)
        mock_openai_create.return_value = mock_response
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_npc()
        
        assert result == npc_json
        mock_openai_create.assert_called_once()
    
    def test_format_game_response_basic(self):
        """Test basic game response formatting."""
        client = OpenAIClient(api_key="test_key")
        
        action_result = {
            "narrative_response": "The character successfully completes the action."
        }
        
        character = {
            "void_score": 2,
            "soulcredit": 3
        }
        
        result = client.format_game_response(action_result, character, include_mechanics=False)
        
        assert "[NARRATIVE]" in result
        assert "successfully completes" in result
        assert "[Dataset entry recorded]" in result
        # Should not include mechanics
        assert "[MECHANICS]" not in result
    
    def test_format_game_response_with_mechanics(self):
        """Test game response formatting with mechanics."""
        client = OpenAIClient(api_key="test_key")
        
        action_result = {
            "narrative_response": "The character attempts a skill check.",
            "attribute": "Agility",
            "skill": "Athletics",
            "attribute_value": 3,
            "skill_value": 4,
            "roll": 15,
            "total": 27,
            "difficulty": 20,
            "success": True,
            "margin": 7,
            "void_change": 1,
            "soulcredit_change": -1
        }
        
        character = {
            "void_score": 2,
            "soulcredit": 3,
            "attributes": {"Agility": 3},
            "skills": {"Athletics": 4}
        }
        
        result = client.format_game_response(action_result, character, include_mechanics=True)
        
        assert "[NARRATIVE]" in result
        assert "[MECHANICS]" in result
        assert "Agility + Athletics" in result
        assert "3×4 + 15 = 27" in result
        assert "vs difficulty 20" in result
        assert "SUCCESS" in result
        assert "Success margin: +7" in result
        assert "Void Score: 3 (+1)" in result
        assert "Soulcredit: 2 (-1)" in result


class TestOpenAIClientGlobals:
    """Test suite for global OpenAI client functions."""
    
    @patch('aeonisk.aeonisk_openai.client.OpenAIClient')
    def test_get_client(self, mock_client_class):
        """Test getting the default client."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Reset the global client
        import aeonisk.aeonisk_openai.client
        aeonisk.aeonisk_openai.client.default_client = None
        
        client = get_client()
        
        assert client == mock_client
        mock_client_class.assert_called_once()
    
    @patch('aeonisk.aeonisk_openai.client.get_client')
    def test_generate_scenario_global(self, mock_get_client):
        """Test global generate_scenario function."""
        from aeonisk.aeonisk_openai.client import generate_scenario
        
        mock_client = Mock()
        mock_client.generate_scenario.return_value = {"test": "scenario"}
        mock_get_client.return_value = mock_client
        
        result = generate_scenario(theme="test", difficulty="easy")
        
        assert result == {"test": "scenario"}
        mock_client.generate_scenario.assert_called_once_with(theme="test", difficulty="easy")
    
    @patch('aeonisk.aeonisk_openai.client.get_client')
    def test_generate_npc_global(self, mock_get_client):
        """Test global generate_npc function."""
        from aeonisk.aeonisk_openai.client import generate_npc
        
        mock_client = Mock()
        mock_client.generate_npc.return_value = {"test": "npc"}
        mock_get_client.return_value = mock_client
        
        result = generate_npc(faction="test_faction")
        
        assert result == {"test": "npc"}
        mock_client.generate_npc.assert_called_once_with(faction="test_faction")
    
    @patch('aeonisk.aeonisk_openai.client.get_client')
    def test_analyze_player_action_global(self, mock_get_client):
        """Test global analyze_player_action function."""
        from aeonisk.aeonisk_openai.client import analyze_player_action
        
        mock_client = Mock()
        mock_client.analyze_player_action.return_value = {"test": "analysis"}
        mock_get_client.return_value = mock_client
        
        character = {"name": "TestChar"}
        result = analyze_player_action(character=character, action_text="test action")
        
        assert result == {"test": "analysis"}
        mock_client.analyze_player_action.assert_called_once_with(
            character=character,
            action_text="test action"
        )
    
    @patch('aeonisk.aeonisk_openai.client.get_client')
    def test_format_game_response_global(self, mock_get_client):
        """Test global format_game_response function."""
        from aeonisk.aeonisk_openai.client import format_game_response
        
        mock_client = Mock()
        mock_client.format_game_response.return_value = "formatted response"
        mock_get_client.return_value = mock_client
        
        action_result = {"test": "result"}
        character = {"name": "TestChar"}
        
        result = format_game_response(
            action_result=action_result,
            character=character,
            include_mechanics=True
        )
        
        assert result == "formatted response"
        mock_client.format_game_response.assert_called_once_with(
            action_result=action_result,
            character=character,
            include_mechanics=True
        )


class TestOpenAIClientErrorHandling:
    """Test suite for error handling in OpenAI client."""
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_scenario_api_error(self, mock_openai_create):
        """Test scenario generation with API error."""
        mock_openai_create.side_effect = Exception("API Error")
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario(theme="test")
        
        assert "error" in result
        assert "API Error" in result["error"]
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_analyze_player_action_api_error(self, mock_openai_create):
        """Test player action analysis with API error."""
        mock_openai_create.side_effect = Exception("API Error")
        
        character = {
            "name": "TestChar",
            "concept": "Test",
            "attributes": {"Agility": 3},
            "skills": {"Stealth": 2},
            "void_score": 0,
            "soulcredit": 0
        }
        
        client = OpenAIClient(api_key="test_key")
        result = client.analyze_player_action(character, "test action")
        
        assert "error" in result
        assert "API Error" in result["error"]
        assert result["success"] is False
        assert result["void_change"] == 0
        assert result["soulcredit_change"] == 0
    
    @patch('aeonisk.aeonisk_openai.client.openai.chat.completions.create')
    def test_generate_npc_api_error(self, mock_openai_create):
        """Test NPC generation with API error."""
        mock_openai_create.side_effect = Exception("API Error")
        
        client = OpenAIClient(api_key="test_key")
        result = client.generate_npc(faction="test")
        
        assert "error" in result
        assert "API Error" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])