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
        assert client.model == "gpt-4"  # Default model

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
        assert kwargs["model"] == "gpt-4"
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
