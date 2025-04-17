"""
Game engine module for the Aeonisk YAGS toolkit.

This module provides the core game mechanics and rules implementation for the YAGS system.
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union

from aeonisk.dataset.parser import DatasetParser
from aeonisk.openai import client as openai_client


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Character:
    """Represents a character in the game."""
    name: str
    concept: str
    attributes: Dict[str, int]
    skills: Dict[str, int]
    void_score: int = 0
    soulcredit: int = 0
    bonds: List[Dict[str, Any]] = field(default_factory=list)
    true_will: Optional[str] = None
    equipment: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_attribute(self, name: str) -> int:
        """Get the value of an attribute."""
        return self.attributes.get(name, 0)
    
    def get_skill(self, name: str) -> int:
        """Get the value of a skill."""
        return self.skills.get(name, 0)
    
    def skill_check(self, attribute: str, skill: str, difficulty: int) -> Tuple[bool, int]:
        """
        Perform a skill check.
        
        Args:
            attribute: The attribute to use.
            skill: The skill to use.
            difficulty: The difficulty of the check.
            
        Returns:
            A tuple of (success, margin), where success is a boolean indicating
            whether the check succeeded, and margin is the amount by which the
            check succeeded or failed.
        """
        attribute_value = self.get_attribute(attribute)
        skill_value = self.get_skill(skill)
        
        # Calculate ability
        ability = attribute_value * skill_value
        
        # Roll d20
        roll = random.randint(1, 20)
        
        # Check for fumble
        if roll == 1:
            return False, difficulty - ability - roll
        
        # Calculate total
        total = ability + roll
        
        # Check for success
        success = total >= difficulty
        margin = total - difficulty
        
        return success, margin


@dataclass
class GameSession:
    """Represents a game session."""
    characters: List[Character] = field(default_factory=list)
    npcs: List[Dict[str, Any]] = field(default_factory=list)
    scenario: Optional[Dict[str, Any]] = None
    dataset: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize the game session."""
        # Load the dataset if not provided
        if self.dataset is None:
            try:
                parser = DatasetParser()
                self.dataset = parser.parse_file("datasets/aeonisk-dataset-v1.0.1.txt")
                logger.info("Loaded default dataset")
            except Exception as e:
                logger.warning(f"Failed to load default dataset: {str(e)}")
    
    def load_character(self, file_path: str) -> Character:
        """
        Load a character from a file.
        
        Args:
            file_path: Path to the character file.
            
        Returns:
            The loaded character.
        """
        try:
            # For now, we'll just create a simple character
            # In a real implementation, this would parse the character file
            character = Character(
                name="Example Character",
                concept="Test Character",
                attributes={
                    "Strength": 3,
                    "Health": 3,
                    "Agility": 3,
                    "Dexterity": 3,
                    "Perception": 3,
                    "Intelligence": 3,
                    "Empathy": 3,
                    "Willpower": 3
                },
                skills={
                    "Athletics": 2,
                    "Awareness": 2,
                    "Brawl": 2,
                    "Charm": 2,
                    "Guile": 2,
                    "Sleight": 2,
                    "Stealth": 2,
                    "Throw": 2,
                    "Astral_Arts": 1
                }
            )
            self.characters.append(character)
            return character
        except Exception as e:
            logger.error(f"Error loading character: {str(e)}")
            raise
    
    def create_character(self, name: str, concept: str) -> Character:
        """
        Create a new character.
        
        Args:
            name: The character's name.
            concept: The character's concept.
            
        Returns:
            The created character.
        """
        # Create a basic character with default values
        character = Character(
            name=name,
            concept=concept,
            attributes={
                "Strength": 3,
                "Health": 3,
                "Agility": 3,
                "Dexterity": 3,
                "Perception": 3,
                "Intelligence": 3,
                "Empathy": 3,
                "Willpower": 3
            },
            skills={
                "Athletics": 2,
                "Awareness": 2,
                "Brawl": 2,
                "Charm": 2,
                "Guile": 2,
                "Sleight": 2,
                "Stealth": 2,
                "Throw": 2
            }
        )
        self.characters.append(character)
        return character
    
    def skill_check(
        self,
        character: Character,
        attribute: str,
        skill: str,
        difficulty: int
    ) -> Tuple[bool, int, str]:
        """
        Perform a skill check.
        
        Args:
            character: The character performing the check.
            attribute: The attribute to use.
            skill: The skill to use.
            difficulty: The difficulty of the check.
            
        Returns:
            A tuple of (success, margin, description), where success is a boolean indicating
            whether the check succeeded, margin is the amount by which the check succeeded
            or failed, and description is a text description of the result.
        """
        success, margin = character.skill_check(attribute, skill, difficulty)
        
        # Generate a description of the result
        if success:
            if margin >= 30:
                description = f"Amazing success! {character.name} performs the task with incredible skill and finesse."
            elif margin >= 20:
                description = f"Excellent success! {character.name} performs the task with great skill."
            elif margin >= 10:
                description = f"Good success! {character.name} performs the task well."
            else:
                description = f"Success! {character.name} performs the task adequately."
        else:
            if margin <= -20:
                description = f"Critical failure! {character.name} fails the task spectacularly."
            elif margin <= -10:
                description = f"Significant failure! {character.name} fails the task badly."
            else:
                description = f"Failure! {character.name} fails to perform the task."
        
        return success, margin, description
    
    def generate_scenario(self, theme: Optional[str] = None, difficulty: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a scenario using the OpenAI API.
        
        Args:
            theme: Optional theme for the scenario.
            difficulty: Optional difficulty level.
            
        Returns:
            The generated scenario.
        """
        try:
            # Convert characters to a format suitable for the OpenAI API
            character_data = []
            for character in self.characters:
                character_data.append({
                    "name": character.name,
                    "concept": character.concept
                })
            
            # Generate the scenario
            self.scenario = openai_client.generate_scenario(
                theme=theme,
                difficulty=difficulty,
                characters=character_data
            )
            
            return self.scenario
        except Exception as e:
            logger.error(f"Error generating scenario: {str(e)}")
            return {"error": str(e)}
    
    def generate_npc(self, faction: Optional[str] = None, role: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate an NPC using the OpenAI API.
        
        Args:
            faction: Optional faction the NPC belongs to.
            role: Optional role of the NPC.
            
        Returns:
            The generated NPC data.
        """
        try:
            npc = openai_client.generate_npc(faction=faction, role=role)
            self.npcs.append(npc)
            return npc
        except Exception as e:
            logger.error(f"Error generating NPC: {str(e)}")
            return {"error": str(e)}
    
    def process_player_action(self, character: Character, action: str) -> str:
        """
        Process a player action using the OpenAI API.
        
        Args:
            character: The character performing the action.
            action: The action to perform.
            
        Returns:
            A description of the result.
        """
        try:
            # Create a system message that describes the game state
            system_message = (
                f"You are the game master for an Aeonisk YAGS game. "
                f"The character {character.name} ({character.concept}) is performing an action. "
                f"Respond with a description of the result, considering the character's attributes and skills, "
                f"and the core mechanics of Will, Bond, Void, and Soulcredit."
            )
            
            # Create a prompt that describes the action
            prompt = (
                f"Character: {character.name} ({character.concept})\n"
                f"Action: {action}\n\n"
                f"Describe the result of this action, considering the character's attributes and skills:"
            )
            
            # For each attribute and skill, add it to the prompt
            prompt += "\n\nAttributes:"
            for attr, value in character.attributes.items():
                prompt += f"\n- {attr}: {value}"
            
            prompt += "\n\nSkills:"
            for skill, value in character.skills.items():
                prompt += f"\n- {skill}: {value}"
            
            # Add additional character information
            prompt += f"\n\nVoid Score: {character.void_score}"
            prompt += f"\nSoulcredit: {character.soulcredit}"
            
            if character.true_will:
                prompt += f"\nTrue Will: {character.true_will}"
            
            if character.bonds:
                prompt += "\n\nBonds:"
                for bond in character.bonds:
                    prompt += f"\n- {bond.get('name', 'Unknown')}: {bond.get('type', 'Unknown')}"
            
            # Generate the result
            result = openai_client.get_client().generate_text(
                prompt=prompt,
                system_message=system_message,
                temperature=0.7,
                max_tokens=500
            )
            
            return result
        except Exception as e:
            logger.error(f"Error processing player action: {str(e)}")
            return f"Error: {str(e)}"
    
    def save_session(self, file_path: str) -> bool:
        """
        Save the current session to a file.
        
        Args:
            file_path: Path to save the session to.
            
        Returns:
            True if the session was saved successfully, False otherwise.
        """
        try:
            # Convert the session to a dictionary
            session_data = {
                "characters": [
                    {
                        "name": character.name,
                        "concept": character.concept,
                        "attributes": character.attributes,
                        "skills": character.skills,
                        "void_score": character.void_score,
                        "soulcredit": character.soulcredit,
                        "bonds": character.bonds,
                        "true_will": character.true_will,
                        "equipment": character.equipment
                    }
                    for character in self.characters
                ],
                "npcs": self.npcs,
                "scenario": self.scenario
            }
            
            # Save the session to a file
            import json
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
            
            logger.info(f"Session saved to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving session: {str(e)}")
            return False
    
    def load_session(self, file_path: str) -> bool:
        """
        Load a session from a file.
        
        Args:
            file_path: Path to load the session from.
            
        Returns:
            True if the session was loaded successfully, False otherwise.
        """
        try:
            # Load the session from a file
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Convert the dictionary to a session
            self.characters = [
                Character(
                    name=char_data["name"],
                    concept=char_data["concept"],
                    attributes=char_data["attributes"],
                    skills=char_data["skills"],
                    void_score=char_data.get("void_score", 0),
                    soulcredit=char_data.get("soulcredit", 0),
                    bonds=char_data.get("bonds", []),
                    true_will=char_data.get("true_will"),
                    equipment=char_data.get("equipment", [])
                )
                for char_data in session_data.get("characters", [])
            ]
            
            self.npcs = session_data.get("npcs", [])
            self.scenario = session_data.get("scenario")
            
            logger.info(f"Session loaded from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading session: {str(e)}")
            return False
