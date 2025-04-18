"""
Unit tests for the OpenAI client module.
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from aeonisk.openai.client import OpenAIClient, generate_scenario, generate_npc


class TestOpenAIClient:
    """Test suite for the OpenAIClient class."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    def test_client_initialization(self):
        """Test that the client can be initialized with environment variables."""
        client = OpenAIClient()
        assert client.api_key == "test_key"
        assert client.model == "gpt-4o"  # Check for new default model

    def test_client_initialization_with_params(self):
        """Test that the client can be initialized with parameters."""
        client = OpenAIClient(api_key="custom_key", model="gpt-3.5-turbo", api_url="https://custom.openai.com")
        assert client.api_key == "custom_key"
        assert client.model == "gpt-3.5-turbo"
        assert client.api_url == "https://custom.openai.com"

    def test_client_initialization_without_key(self):
        """Test that the client raises an error when no API key is provided."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                OpenAIClient()

    @patch("openai.chat.completions.create")
    def test_generate_text(self, mock_create):
        """Test generating text with the OpenAI API."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text"
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        result = client.generate_text("Test prompt", system_message="Test system message")

        assert result == "Generated text"
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert kwargs["model"] == "gpt-4o" # Check for new default model
        assert len(kwargs["messages"]) == 2
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1]["role"] == "user"

    @patch("openai.chat.completions.create")
    def test_generate_scenario(self, mock_create):
        """Test generating a scenario."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "title": "Test Scenario",
            "overview": "This is a test scenario",
            "setting": "Aeonisk",
            "npcs": [
                {
                    "name": "Test NPC",
                    "role": "Antagonist"
                }
            ]
        }
        """
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario(theme="test", difficulty="easy")

        assert "title" in result
        assert result["title"] == "Test Scenario"
        assert "npcs" in result
        assert len(result["npcs"]) == 1
        mock_create.assert_called_once()

    @patch("openai.chat.completions.create")
    def test_generate_scenario_invalid_json(self, mock_create):
        """Test generating a scenario with invalid JSON response."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not valid JSON"
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        result = client.generate_scenario()

        assert "raw_response" in result
        assert result["raw_response"] == "This is not valid JSON"
        mock_create.assert_called_once()

    @patch("openai.chat.completions.create")
    def test_generate_npc(self, mock_create):
        """Test generating an NPC."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "name": "Test NPC",
            "faction": "Sovereign Nexus",
            "attributes": {
                "strength": 3,
                "agility": 4
            }
        }
        """
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        result = client.generate_npc(faction="Sovereign Nexus", role="enforcer")

        assert "name" in result
        assert result["name"] == "Test NPC"
        assert "attributes" in result
        assert result["attributes"]["strength"] == 3
        mock_create.assert_called_once()

    @patch("openai.chat.completions.create")
    def test_analyze_player_action_seed_attunement(self, mock_create):
        """Test analyzing a player action involving Seed attunement."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "attribute": "Willpower",
            "skill": "Attunement",
            "attribute_value": 3,
            "skill_value": 2,
            "difficulty": 18,
            "roll": 15,
            "total": 21,
            "success": true,
            "margin": 3,
            "narrative_response": "You successfully attune the Seed to Spark.",
            "void_change": 0,
            "soulcredit_change": 0
        }
        """
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        character_data = {
            "name": "Test Character",
            "attributes": {"Willpower": 3},
            "skills": {"Attunement": 2},
            "raw_seeds": [{"id": "seed1", "acquisition_cycle": 1}]
        }
        action_text = "Attune raw seed seed1 to Spark"
        result = client.analyze_player_action(character=character_data, action_text=action_text)

        assert result["skill"] == "Attunement"
        assert result["success"] is True
        assert "attune" in result["narrative_response"].lower()
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        # Check the user message content within the messages list
        user_message = next((m['content'] for m in kwargs['messages'] if m['role'] == 'user'), None)
        assert user_message is not None
        assert "Attune raw seed" in user_message

    @patch("openai.chat.completions.create")
    def test_analyze_player_action_dreamwork(self, mock_create):
        """Test analyzing a player action involving Dreamwork."""
        # Mock the OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "attribute": "Willpower",
            "skill": "Dreamwork",
            "attribute_value": 3,
            "skill_value": 2,
            "difficulty": 16,
            "roll": 10,
            "total": 16,
            "success": true,
            "margin": 0,
            "narrative_response": "You manage to gain some control over the dream.",
            "void_change": -1,
            "soulcredit_change": 0
        }
        """
        mock_create.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        character_data = {
            "name": "Test Character",
            "attributes": {"Willpower": 3},
            "skills": {"Dreamwork": 2},
            "void_score": 2
        }
        action_text = "Attempt to control the nightmare"
        result = client.analyze_player_action(character=character_data, action_text=action_text)

        assert result["skill"] == "Dreamwork"
        assert result["success"] is True
        assert result["void_change"] == -1
        assert "dream" in result["narrative_response"].lower()
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        # Check the user message content within the messages list
        user_message = next((m['content'] for m in kwargs['messages'] if m['role'] == 'user'), None)
        assert user_message is not None
        assert "nightmare" in user_message

    @patch("aeonisk.openai.client.OpenAIClient")
    def test_generate_scenario_function(self, mock_client_class):
        """Test the generate_scenario function."""
        # Mock the OpenAIClient instance
        mock_client = MagicMock()
        mock_client.generate_scenario.return_value = {"title": "Test Scenario"}
        mock_client_class.return_value = mock_client

        # Patch the get_client function to return our mock
        with patch("aeonisk.openai.client.get_client", return_value=mock_client):
            result = generate_scenario(theme="test")

        assert result == {"title": "Test Scenario"}
        mock_client.generate_scenario.assert_called_once_with(theme="test")

    @patch("aeonisk.openai.client.OpenAIClient")
    def test_generate_npc_function(self, mock_client_class):
        """Test the generate_npc function."""
        # Mock the OpenAIClient instance
        mock_client = MagicMock()
        mock_client.generate_npc.return_value = {"name": "Test NPC"}
        mock_client_class.return_value = mock_client

        # Patch the get_client function to return our mock
        with patch("aeonisk.openai.client.get_client", return_value=mock_client):
            result = generate_npc(faction="test")

        assert result == {"name": "Test NPC"}
        mock_client.generate_npc.assert_called_once_with(faction="test")
