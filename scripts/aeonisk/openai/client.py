"""
OpenAI client module for the Aeonisk YAGS toolkit.

This module provides tools for integrating with the OpenAI API for generating
game content and facilitating playtesting.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Union

import openai
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for interacting with the OpenAI API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        """
        Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY environment variable.
            model: OpenAI model to use. If None, uses OPENAI_MODEL environment variable or "gpt-4".
            api_url: OpenAI API URL. If None, uses OPENAI_API_URL environment variable or default.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key.")
        
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4")
        self.api_url = api_url or os.getenv("OPENAI_API_URL")
        
        # Configure the OpenAI client
        if self.api_url:
            openai.base_url = self.api_url
        openai.api_key = self.api_key
        
        logger.info(f"Initialized OpenAI client with model: {self.model}")

    def generate_text(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """
        Generate text using the OpenAI API.

        Args:
            prompt: The prompt to generate text from.
            system_message: Optional system message to set the context.
            temperature: Controls randomness. Higher values (e.g., 0.8) make output more random,
                         lower values (e.g., 0.2) make it more focused and deterministic.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text.
        """
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
            
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.debug(f"Sending request to OpenAI API with prompt: {prompt[:100]}...")
            
            response = openai.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating text: {str(e)}")
            raise

    def generate_scenario(
        self,
        theme: Optional[str] = None,
        difficulty: Optional[str] = None,
        setting: Optional[str] = "Aeonisk",
        characters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a game scenario.

        Args:
            theme: Optional theme for the scenario (e.g., "cyberpunk", "ritual", "void").
            difficulty: Optional difficulty level (e.g., "easy", "moderate", "hard").
            setting: Optional setting name. Defaults to "Aeonisk".
            characters: Optional list of character data to include in the scenario.

        Returns:
            A dictionary containing the generated scenario.
        """
        system_message = (
            "You are a game master for the Aeonisk RPG setting using the YAGS system. "
            "Create a detailed scenario that emphasizes the core mechanics: "
            "Will, Bond, Void, and Soulcredit."
        )
        
        prompt_parts = ["Generate a detailed RPG scenario with the following structure:"]
        
        if theme:
            prompt_parts.append(f"Theme: {theme}")
        if difficulty:
            prompt_parts.append(f"Difficulty: {difficulty}")
        if setting:
            prompt_parts.append(f"Setting: {setting}")
        if characters:
            prompt_parts.append("Characters:")
            for character in characters:
                prompt_parts.append(f"- {character.get('name', 'Unknown')}: {character.get('concept', 'No concept')}")
        
        prompt_parts.append("\nInclude the following sections:")
        prompt_parts.append("1. Scenario Overview")
        prompt_parts.append("2. Setting Description")
        prompt_parts.append("3. Key NPCs")
        prompt_parts.append("4. Plot Hooks")
        prompt_parts.append("5. Challenges and Skill Checks")
        prompt_parts.append("6. Potential Outcomes")
        prompt_parts.append("\nFormat the response as JSON.")
        
        prompt = "\n".join(prompt_parts)
        
        try:
            response_text = self.generate_text(
                prompt=prompt,
                system_message=system_message,
                temperature=0.8,
                max_tokens=2000
            )
            
            # Extract JSON from the response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                # If JSON parsing fails, return the raw text
                return {"raw_response": response_text}
                
        except Exception as e:
            logger.error(f"Error generating scenario: {str(e)}")
            return {"error": str(e)}

    def generate_npc(
        self,
        faction: Optional[str] = None,
        role: Optional[str] = None,
        importance: Optional[str] = "minor"
    ) -> Dict[str, Any]:
        """
        Generate an NPC for the game.

        Args:
            faction: Optional faction the NPC belongs to.
            role: Optional role of the NPC.
            importance: Optional importance of the NPC ("minor", "major", "villain").

        Returns:
            A dictionary containing the generated NPC data.
        """
        system_message = (
            "You are a character creator for the Aeonisk RPG setting using the YAGS system. "
            "Create a detailed NPC with appropriate attributes, skills, and background."
        )
        
        prompt_parts = ["Generate a detailed NPC with the following parameters:"]
        
        if faction:
            prompt_parts.append(f"Faction: {faction}")
        if role:
            prompt_parts.append(f"Role: {role}")
        if importance:
            prompt_parts.append(f"Importance: {importance}")
        
        prompt_parts.append("\nInclude the following sections:")
        prompt_parts.append("1. Basic Information (name, concept, appearance)")
        prompt_parts.append("2. Attributes (Strength, Health, Agility, etc.)")
        prompt_parts.append("3. Skills (relevant to their role)")
        prompt_parts.append("4. Background and Motivation")
        prompt_parts.append("5. Bonds and Relationships")
        prompt_parts.append("6. Void Score and Soulcredit")
        prompt_parts.append("7. Equipment and Resources")
        prompt_parts.append("\nFormat the response as JSON.")
        
        prompt = "\n".join(prompt_parts)
        
        try:
            response_text = self.generate_text(
                prompt=prompt,
                system_message=system_message,
                temperature=0.7,
                max_tokens=1500
            )
            
            # Extract JSON from the response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                # If JSON parsing fails, return the raw text
                return {"raw_response": response_text}
                
        except Exception as e:
            logger.error(f"Error generating NPC: {str(e)}")
            return {"error": str(e)}


# Create a default client instance
default_client = None

def get_client() -> OpenAIClient:
    """
    Get the default OpenAI client instance.

    Returns:
        The default OpenAI client instance.
    """
    global default_client
    if default_client is None:
        try:
            default_client = OpenAIClient()
        except ValueError as e:
            logger.error(f"Failed to initialize default OpenAI client: {str(e)}")
            raise
    return default_client


def generate_scenario(**kwargs) -> Dict[str, Any]:
    """
    Generate a game scenario using the default client.

    Args:
        **kwargs: Keyword arguments to pass to the generate_scenario method.

    Returns:
        A dictionary containing the generated scenario.
    """
    return get_client().generate_scenario(**kwargs)


def generate_npc(**kwargs) -> Dict[str, Any]:
    """
    Generate an NPC using the default client.

    Args:
        **kwargs: Keyword arguments to pass to the generate_npc method.

    Returns:
        A dictionary containing the generated NPC data.
    """
    return get_client().generate_npc(**kwargs)
