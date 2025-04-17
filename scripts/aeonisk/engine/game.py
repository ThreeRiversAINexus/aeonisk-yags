"""
Game engine module for the Aeonisk YAGS toolkit.

This module provides the core game mechanics and rules implementation for the YAGS system.
"""

import json
import random
import logging
import datetime
from typing import Dict, List, Any, Optional, Tuple, Union, cast

from pydantic import ValidationError

from aeonisk.core.models import (
    Character, NPC, Scenario, GameSession as GameSessionModel,
    PlayerAction, SkillCheck, DatasetEntry
)
from aeonisk.dataset.parser import DatasetParser
from aeonisk.openai import client as openai_client


# Configure logging
logger = logging.getLogger(__name__)


class GameSession:
    """Represents a game session."""
    
    def __init__(self):
        """Initialize the game session."""
        self._model = GameSessionModel()
        self._load_dataset()
    
    def _load_dataset(self):
        """Load the default dataset."""
        try:
            parser = DatasetParser()
            self.dataset = parser.parse_file("datasets/aeonisk-dataset-v1.0.1.txt")
            logger.info("Loaded default dataset")
        except Exception as e:
            logger.warning(f"Failed to load default dataset: {str(e)}")
            self.dataset = None
    
    @property
    def characters(self) -> List[Character]:
        """Get the characters in the session."""
        return self._model.characters
    
    @property
    def npcs(self) -> List[NPC]:
        """Get the NPCs in the session."""
        return self._model.npcs
    
    @property
    def scenario(self) -> Optional[Scenario]:
        """Get the current scenario."""
        return self._model.scenario
    
    @property
    def actions(self) -> List[PlayerAction]:
        """Get the player actions in the session."""
        return self._model.actions
    
    @property
    def current_character(self) -> Optional[Character]:
        """Get the currently selected character."""
        return self._model.current_character
    
    def load_character(self, file_path: str) -> Character:
        """
        Load a character from a file.
        
        Args:
            file_path: Path to the character file.
            
        Returns:
            The loaded character.
        """
        try:
            # Load the character from a file
            with open(file_path, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
            
            # Create a Character model from the data
            character = Character(**char_data)
            
            # Add the character to the session
            self._model.characters.append(character)
            
            # Set as current character if it's the first one
            if len(self._model.characters) == 1:
                self._model.current_character_index = 0
            
            return character
        except ValidationError as e:
            logger.error(f"Invalid character data: {str(e)}")
            raise ValueError(f"Invalid character data: {str(e)}")
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
        # Create a Character model with default values
        character = Character(name=name, concept=concept)
        
        # Add the character to the session
        self._model.characters.append(character)
        
        # Set as current character if it's the first one
        if len(self._model.characters) == 1:
            self._model.current_character_index = 0
        else:
            # Otherwise, set it as the current character
            self._model.current_character_index = len(self._model.characters) - 1
        
        return character
    
    def select_character(self, index: int) -> Optional[Character]:
        """
        Select a character by index.
        
        Args:
            index: The index of the character to select.
            
        Returns:
            The selected character, or None if the index is invalid.
        """
        if 0 <= index < len(self._model.characters):
            self._model.current_character_index = index
            return self._model.current_character
        return None
    
    def skill_check(
        self,
        character: Character,
        attribute: str,
        skill: str,
        difficulty: int
    ) -> Tuple[bool, int, str]:
        """
        Perform a manual skill check.
        
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
        # Get attribute and skill values
        attribute_value = character.attributes.get(attribute, 0)
        skill_value = character.skills.get(skill, 0)
        
        # Calculate ability
        ability = attribute_value * skill_value
        
        # Roll d20
        roll = random.randint(1, 20)
        
        # Check for fumble
        if roll == 1:
            success = False
            margin = difficulty - ability - roll
        else:
            # Calculate total
            total = ability + roll
            
            # Check for success
            success = total >= difficulty
            margin = total - difficulty
        
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
        
        # Create a SkillCheck model for the dataset
        skill_check = SkillCheck(
            character_name=character.name,
            attribute=attribute,
            skill=skill,
            attribute_value=attribute_value,
            skill_value=skill_value,
            difficulty=difficulty,
            roll=roll,
            total=ability + roll,
            success=success,
            margin=margin,
            description=description,
            timestamp=datetime.datetime.now().isoformat()
        )
        
        # Record the skill check in the dataset
        self._record_skill_check(skill_check)
        
        return success, margin, description
    
    def _record_skill_check(self, skill_check: SkillCheck):
        """
        Record a skill check in the dataset.
        
        Args:
            skill_check: The skill check to record.
        """
        # TODO: Implement dataset recording
        pass
    
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
            for character in self._model.characters:
                character_data.append({
                    "name": character.name,
                    "concept": character.concept
                })
            
            # Generate the scenario
            scenario_data = openai_client.generate_scenario(
                theme=theme,
                difficulty=difficulty,
                characters=character_data
            )
            
            # Create a Scenario model from the data
            try:
                self._model.scenario = Scenario(**scenario_data)
            except ValidationError:
                # If validation fails, store the raw data
                self._model.scenario = Scenario(raw_response=json.dumps(scenario_data))
            
            return scenario_data
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
            npc_data = openai_client.generate_npc(faction=faction, role=role)
            
            # Create an NPC model from the data
            try:
                npc = NPC(**npc_data)
                self._model.npcs.append(npc)
            except ValidationError:
                # If validation fails, create a basic NPC with the raw data
                npc = NPC(
                    name=npc_data.get("name", "Unknown NPC"),
                    faction=faction,
                    role=role,
                    description=json.dumps(npc_data)
                )
                self._model.npcs.append(npc)
            
            return npc_data
        except Exception as e:
            logger.error(f"Error generating NPC: {str(e)}")
            return {"error": str(e)}
    
    def process_player_action(self, character: Character, action_text: str) -> str:
        """
        Process a player action using the OpenAI API.
        
        Args:
            character: The character performing the action.
            action_text: The action to perform.
            
        Returns:
            A formatted description of the result.
        """
        if not character:
            return "Error: No character selected."
        
        try:
            # Convert character to a dictionary for the API
            character_dict = character.model_dump()
            
            # Convert scenario to a dictionary if available
            scenario_dict = None
            if self._model.scenario:
                scenario_dict = self._model.scenario.model_dump()
            
            # Convert previous actions to a list of dictionaries
            previous_actions = []
            for action in self._model.actions[-3:]:  # Include up to 3 most recent actions
                previous_actions.append(action.model_dump())
            
            # Analyze the player action
            action_result = openai_client.analyze_player_action(
                character=character_dict,
                action_text=action_text,
                scenario=scenario_dict,
                previous_actions=previous_actions
            )
            
            # Update character based on the action result
            void_change = action_result.get("void_change", 0)
            if void_change != 0:
                character.void_score += void_change
                # Ensure void_score stays within bounds
                character.void_score = max(0, min(10, character.void_score))
            
            sc_change = action_result.get("soulcredit_change", 0)
            if sc_change != 0:
                character.soulcredit += sc_change
                # Ensure soulcredit stays within bounds
                character.soulcredit = max(-10, min(10, character.soulcredit))
            
            # Create a PlayerAction model for the dataset
            player_action = PlayerAction(
                character_name=character.name,
                action_text=action_text,
                result_text=action_result.get("narrative_response", ""),
                void_change=void_change,
                soulcredit_change=sc_change,
                timestamp=datetime.datetime.now().isoformat()
            )
            
            # Add skill check if available
            if all(k in action_result for k in ["attribute", "skill", "roll", "difficulty"]):
                skill_check = SkillCheck(
                    character_name=character.name,
                    attribute=action_result["attribute"],
                    skill=action_result["skill"],
                    attribute_value=action_result.get("attribute_value", character.attributes.get(action_result["attribute"], 0)),
                    skill_value=action_result.get("skill_value", character.skills.get(action_result["skill"], 0)),
                    difficulty=action_result["difficulty"],
                    roll=action_result["roll"],
                    total=action_result.get("total", 0),
                    success=action_result.get("success", False),
                    margin=action_result.get("margin", 0),
                    description=action_result.get("narrative_response", ""),
                    timestamp=datetime.datetime.now().isoformat()
                )
                player_action.skill_checks.append(skill_check)
            
            # Record the player action in the dataset
            self._model.actions.append(player_action)
            
            # Format the response for display
            return openai_client.format_game_response(
                action_result=action_result,
                character=character_dict
            )
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
            # Convert the session model to a dictionary
            session_data = self._model.model_dump()
            
            # Save the session to a file
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
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Create a GameSession model from the data
            try:
                self._model = GameSessionModel(**session_data)
            except ValidationError as e:
                logger.error(f"Invalid session data: {str(e)}")
                return False
            
            logger.info(f"Session loaded from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading session: {str(e)}")
            return False
