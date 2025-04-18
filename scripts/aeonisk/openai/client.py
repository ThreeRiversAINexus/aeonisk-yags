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
        
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o") # Default to gpt-4o
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

    def analyze_player_action(
        self,
        character: Dict[str, Any],
        action_text: str,
        scenario: Optional[Dict[str, Any]] = None,
        previous_actions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a player action to determine appropriate skill checks and narrative response.

        Args:
            character: The character performing the action.
            action_text: The text description of the action.
            scenario: Optional scenario context.
            previous_actions: Optional list of previous actions for context.

        Returns:
            A dictionary containing the analysis results, including:
            - narrative_response: The narrative description of the action result
            - skill_check: Information about the skill check (if applicable)
            - void_change: Any change to the character's Void score
            - soulcredit_change: Any change to the character's Soulcredit
        """
        system_message = (
            "You are the game master for an Aeonisk YAGS game. "
            "Your task is to analyze a player action, determine the appropriate skill check, "
            "and provide a narrative response. "
            "Follow the YAGS system rules for determining skill checks: attribute × skill + d20 vs difficulty."
        )
        
        # Build the prompt with character information and action
        prompt_parts = ["# Character Information"]
        prompt_parts.append(f"Name: {character.get('name', 'Unknown')}")
        prompt_parts.append(f"Concept: {character.get('concept', 'Unknown')}")
        
        # Add attributes
        prompt_parts.append("\n## Attributes")
        for attr, value in character.get('attributes', {}).items():
            prompt_parts.append(f"{attr}: {value}")
        
        # Add skills
        prompt_parts.append("\n## Skills")
        for skill, value in character.get('skills', {}).items():
            prompt_parts.append(f"{skill}: {value}")
        
        # Add other character information
        prompt_parts.append(f"\nVoid Score: {character.get('void_score', 0)}")
        prompt_parts.append(f"Soulcredit: {character.get('soulcredit', 0)}")
        
        # Add scenario context if available
        if scenario:
            prompt_parts.append("\n# Scenario Context")
            if 'overview' in scenario:
                prompt_parts.append(f"Overview: {scenario['overview']}")
            if 'setting' in scenario and isinstance(scenario['setting'], dict):
                setting = scenario['setting']
                if 'location' in setting:
                    prompt_parts.append(f"Location: {setting['location']}")
                if 'atmosphere' in setting:
                    prompt_parts.append(f"Atmosphere: {setting['atmosphere']}")
        
        # Add previous actions for context if available
        if previous_actions:
            prompt_parts.append("\n# Previous Actions")
            for i, action in enumerate(previous_actions[-3:]):  # Include up to 3 most recent actions
                prompt_parts.append(f"{i+1}. {action.get('action_text', 'Unknown')}")
                prompt_parts.append(f"   Result: {action.get('result_text', 'Unknown')}")
        
        # Add the current action
        prompt_parts.append("\n# Current Action")
        prompt_parts.append(action_text)
        
        # Add instructions for the response format
        prompt_parts.append("\n# Instructions")
        prompt_parts.append("Analyze the action and determine:")
        prompt_parts.append("1. The most appropriate attribute and skill for this action")
        prompt_parts.append("2. A suitable difficulty level (10=Trivial, 15=Easy, 20=Moderate, 24=Challenging, 28=Difficult, 32=Formidable)")
        prompt_parts.append("3. A d20 roll result (1-20)")
        prompt_parts.append("4. A narrative description of the outcome")
        prompt_parts.append("5. Any changes to Void Score or Soulcredit")
        
        prompt_parts.append("\nFormat your response as JSON with the following structure:")
        prompt_parts.append("""
{
  "attribute": "AttributeName",
  "skill": "SkillName",
  "attribute_value": 3,
  "skill_value": 2,
  "difficulty": 20,
  "roll": 15,
  "total": 21,
  "success": true,
  "margin": 1,
  "narrative_response": "Detailed description of what happens...",
  "void_change": 0,
  "soulcredit_change": 0
}
""")
        
        prompt = "\n".join(prompt_parts)
        
        try:
            response_text = self.generate_text(
                prompt=prompt,
                system_message=system_message,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Extract JSON from the response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                # If JSON parsing fails, return a basic response
                logger.warning("Failed to parse JSON from action analysis response")
                return {
                    "narrative_response": response_text,
                    "success": True,
                    "void_change": 0,
                    "soulcredit_change": 0
                }
                
        except Exception as e:
            logger.error(f"Error analyzing player action: {str(e)}")
            return {
                "error": str(e),
                "narrative_response": f"Error processing action: {str(e)}",
                "success": False,
                "void_change": 0,
                "soulcredit_change": 0
            }

    def format_game_response(
        self,
        action_result: Dict[str, Any],
        character: Dict[str, Any],
        include_mechanics: bool = True
    ) -> str:
        """
        Format the game response for display to the player.

        Args:
            action_result: The result of the action analysis.
            character: The character performing the action.
            include_mechanics: Whether to include mechanical details in the response.

        Returns:
            A formatted string response.
        """
        response_parts = []
        
        # Add the narrative response
        response_parts.append("[NARRATIVE]")
        response_parts.append(action_result.get("narrative_response", "No narrative response available."))
        
        # Add mechanical details if requested
        if include_mechanics:
            response_parts.append("\n[MECHANICS]")
            
            # Add skill check details if available
            if all(k in action_result for k in ["attribute", "skill", "roll", "difficulty"]):
                attr = action_result["attribute"]
                skill = action_result["skill"]
                attr_val = action_result.get("attribute_value", character.get("attributes", {}).get(attr, 0))
                skill_val = action_result.get("skill_value", character.get("skills", {}).get(skill, 0))
                roll = action_result["roll"]
                total = action_result.get("total", (attr_val * skill_val) + roll)
                diff = action_result["difficulty"]
                success = action_result.get("success", total >= diff)
                
                check_str = f"• {attr} + {skill} check: {attr_val}×{skill_val} + {roll} = {total} vs difficulty {diff}"
                check_str += f" ({'SUCCESS' if success else 'FAILURE'})"
                response_parts.append(check_str)
                
                # Add margin of success/failure if available
                if "margin" in action_result:
                    margin = action_result["margin"]
                    if margin > 0:
                        response_parts.append(f"• Success margin: +{margin}")
                    else:
                        response_parts.append(f"• Failure margin: {margin}")
            
            # Add void and soulcredit changes if any
            void_change = action_result.get("void_change", 0)
            if void_change != 0:
                new_void = character.get("void_score", 0) + void_change
                response_parts.append(f"• Void Score: {new_void} ({'+' if void_change > 0 else ''}{void_change})")
            else:
                response_parts.append(f"• Void Score: {character.get('void_score', 0)} (unchanged)")
                
            sc_change = action_result.get("soulcredit_change", 0)
            if sc_change != 0:
                new_sc = character.get("soulcredit", 0) + sc_change
                response_parts.append(f"• Soulcredit: {new_sc} ({'+' if sc_change > 0 else ''}{sc_change})")
            else:
                response_parts.append(f"• Soulcredit: {character.get('soulcredit', 0)} (unchanged)")
        
        # Add dataset recording confirmation
        response_parts.append("\n[Dataset entry recorded]")
        
        return "\n".join(response_parts)

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


def analyze_player_action(**kwargs) -> Dict[str, Any]:
    """
    Analyze a player action using the default client.

    Args:
        **kwargs: Keyword arguments to pass to the analyze_player_action method.

    Returns:
        A dictionary containing the analysis results.
    """
    return get_client().analyze_player_action(**kwargs)


def format_game_response(**kwargs) -> str:
    """
    Format a game response using the default client.

    Args:
        **kwargs: Keyword arguments to pass to the format_game_response method.

    Returns:
        A formatted string response.
    """
    return get_client().format_game_response(**kwargs)
