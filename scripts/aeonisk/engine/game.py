"""
Game engine module for the Aeonisk YAGS toolkit.

This module provides the core game mechanics and rules implementation for the YAGS system.
"""

import json
import random
import logging
import datetime
import os
from typing import Dict, List, Any, Optional, Tuple, Union, cast

from pydantic import ValidationError

from aeonisk.core.models import (
    Character, NPC, Scenario, GameSession as GameSessionModel,
    PlayerAction, SkillCheck, DatasetEntry
)
from aeonisk.dataset.parser import DatasetParser
from aeonisk.dataset.manager import DatasetManager
from aeonisk.utils.file_utils import get_session_file, get_session_dataset_directory
from aeonisk.openai import client as openai_client


# Configure logging
logger = logging.getLogger(__name__)


class GameSession:
    """Represents a game session."""
    
    def __init__(self, session_name: Optional[str] = None):
        """
        Initialize the game session.
        
        Args:
            session_name: Optional name of the session. If not provided, a timestamp will be used.
        """
        self._model = GameSessionModel()
        self.session_name = session_name
        self.dataset_manager = DatasetManager(session_name)
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
        # Record the skill check using the dataset manager
        self.dataset_manager.record_skill_check(skill_check)
    
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

    # --- Seed Mechanics ---

    def attune_seed(self, character: Character, raw_seed_id: str, target_element: str) -> Tuple[bool, str]:
        """Attune a raw Seed to a specific element."""
        raw_seed_index = -1
        for i, seed in enumerate(character.raw_seeds):
            if seed.get("id") == raw_seed_id:
                raw_seed_index = i
                break

        if raw_seed_index == -1:
            return False, f"Raw seed with ID '{raw_seed_id}' not found."

        # Perform Attunement skill check (difficulty can vary, using 18 as placeholder)
        # TODO: Refine difficulty based on context/rules
        attunement_difficulty = 18 
        success, margin, description = self.skill_check(
            character, "Willpower", "Attunement", attunement_difficulty
        )

        if success:
            # Remove raw seed and add to attuned seeds
            character.raw_seeds.pop(raw_seed_index)
            character.attuned_seeds[target_element] = character.attuned_seeds.get(target_element, 0) + 1
            return True, f"Successfully attuned seed {raw_seed_id} to {target_element}. {description}"
        else:
            # TODO: Handle potential negative consequences of failed attunement?
            return False, f"Failed to attune seed {raw_seed_id}. {description}"

    def advance_cycle(self, character: Character) -> List[Dict[str, Any]]:
        """Advance the game time by one cycle (7 days)."""
        character.current_cycle += 1
        # Potentially trigger other cycle-based events here
        return self.check_seed_degradation(character)

    def check_seed_degradation(self, character: Character) -> List[Dict[str, Any]]:
        """Check for and handle raw seed degradation."""
        degraded_seeds = []
        seeds_to_keep = []
        degradation_limit = 7 # Seeds degrade after 7 cycles
        current_cycle = character.current_cycle
        
        # Correctly identify degraded seeds and build the list to keep
        for seed in character.raw_seeds:
            acquisition_cycle = seed.get("acquisition_cycle", -1)
            if acquisition_cycle >= 0 and (current_cycle - acquisition_cycle) >= degradation_limit:
                degraded_seeds.append(seed) # Add to the list of degraded seeds
                logger.info(f"Raw seed {seed.get('id', 'unknown')} degraded.")
            else:
                seeds_to_keep.append(seed) # Add to the list of seeds to keep
        
        character.raw_seeds = seeds_to_keep # Update the character's list
        return degraded_seeds # Return the list of seeds that were actually degraded

    def use_raw_seed(self, character: Character, raw_seed_id: str) -> Tuple[bool, str, int]:
        """Use an unattuned raw seed, incurring Void."""
        raw_seed_index = -1
        for i, seed in enumerate(character.raw_seeds):
            if seed.get("id") == raw_seed_id:
                raw_seed_index = i
                break
        
        if raw_seed_index == -1:
            return False, f"Raw seed with ID '{raw_seed_id}' not found.", 0

        # Remove the seed
        character.raw_seeds.pop(raw_seed_index)
        
        # Apply Void penalty
        void_gain = 1
        self.apply_void_gain(character, void_gain) 
        
        return True, f"Used raw seed {raw_seed_id}, gained +{void_gain} Void.", void_gain

    def use_attuned_seed(self, character: Character, element: str) -> Tuple[bool, str, int]:
        """Use an attuned seed of a specific element."""
        if character.attuned_seeds.get(element, 0) > 0:
            character.attuned_seeds[element] -= 1
            if character.attuned_seeds[element] == 0:
                del character.attuned_seeds[element] # Clean up if count reaches zero
            # TODO: Implement elemental conversion effects based on context
            return True, f"Used attuned {element} seed.", 0
        else:
            return False, f"Character does not have any attuned {element} seeds.", 0

    # --- Void Mechanics ---

    def get_void_environmental_effect(self, character: Character) -> Optional[str]:
        """Get the description of the passive Void environmental effect."""
        vs = character.void_score
        if vs >= 10:
            return "Reality warps visibly around the character. Claimed by the Void."
        elif vs >= 9:
            return "Severe disruption: Sacred spaces reject the character, passive rituals twist."
        elif vs >= 7:
            return "Significant disruption: Leylines flicker, tech glitches, Bonds become Dormant."
        elif vs >= 5:
            return "Minor disruption: Ambient instability, static in the air, dream fragments leak."
        else:
            return None # No significant passive effect

    def apply_void_gain(self, character: Character, amount: int) -> Tuple[bool, Optional[str]]:
        """Apply Void gain to a character, check for Void Spike, and update status."""
        # Handle both positive and negative void changes
        initial_void = character.void_score
        character.void_score += amount
        character.void_score = max(0, min(10, character.void_score)) # Cap at 0-10
        
        # Only trigger Void Spike for positive gains >= 2
        void_spike_triggered = amount >= 2
        spike_effect = None
        if void_spike_triggered:
            # TODO: Implement mechanical stun effect based on context (combat/narrative)
            spike_effect = f"Void Spike triggered! Character is stunned/dazed."
            logger.info(f"{character.name} triggered Void Spike (+{amount} Void).")

        # Update Bond status if Void threshold crossed
        if initial_void < 7 <= character.void_score:
             self.update_bond_status(character)
        elif character.void_score < 7 <= initial_void: # Handle case where Void drops below 7
             self.update_bond_status(character)
             
        return void_spike_triggered, spike_effect

    def update_bond_status(self, character: Character):
        """Update the status of character's bonds based on Void score."""
        new_status = "Dormant" if character.void_score >= 7 else "Active"
        for bond in character.bonds:
            if bond.get("status") != new_status:
                bond["status"] = new_status
                logger.info(f"Bond '{bond.get('name', 'Unknown')}' for {character.name} is now {new_status}.")

    # --- Dreamwork Mechanics ---

    def handle_rest(self, character: Character) -> str:
        """Handle character resting, potentially triggering a dream event."""
        # Basic chance for a dream event (e.g., 25%)
        # TODO: Refine trigger conditions (Void, trauma, Bond status etc.)
        if random.random() < 0.25: 
            return self.handle_dream_event(character)
        else:
            # TODO: Implement rest benefits (healing, fatigue recovery)
            return f"{character.name} rests peacefully with no dreams."

    def _generate_dream_outcome(self, character: Character, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate the outcome of a dream event. 
        Placeholder implementation. Needs AI integration or more complex logic.
        """
        # TODO: Integrate with OpenAI or implement rule-based dream generation
        # Based on character state (Void, Bonds, True Will), context, etc.
        possible_outcomes = [
            {"effect": "void_change", "change": 1, "message": "A nightmare leaves you shaken, increasing your Void."},
            {"effect": "void_change", "change": -1, "message": "A peaceful dream soothes your spirit, decreasing your Void."},
            {"effect": "insight", "message": "You gain a cryptic insight: 'The shadow hides the key'."},
            {"effect": "bond_shift", "target_bond": character.bonds[0]["name"] if character.bonds else None, "change": 1, "message": "A dream strengthens your connection."},
            {"effect": "confrontation", "message": "You face a symbolic representation of your fears."},
            {"effect": "shared_dream", "participants": [character.name], "scene": "A shared dreamscape unfolds...", "message": "You find yourself in a shared dream."},
        ]
        # Simple random selection for now
        outcome = random.choice(possible_outcomes)
        
        # Ensure bond shift targets an existing bond
        if outcome["effect"] == "bond_shift" and not outcome["target_bond"]:
             outcome = {"effect": "insight", "message": "A fleeting dream offers no clear message."} # Default if no bonds

        # Basic shared dream logic placeholder
        if outcome["effect"] == "shared_dream":
             # Find bonded partners
             bonded_partners = [b.get("partner") for b in character.bonds if b.get("partner")] # Assuming partner name is stored
             # In a real implementation, check if partners are also resting/eligible
             outcome["participants"].extend(bonded_partners) 
             
        return outcome

    def handle_dream_event(self, character: Character, context: Optional[str] = None) -> str:
        """Handle a specific dream event, applying its effects."""
        
        # Optional: Use Dreamwork skill check to influence outcome
        dreamwork_success = False
        if "Dreamwork" in character.skills and character.skills["Dreamwork"] > 0:
             # Difficulty could depend on dream intensity, context
             dreamwork_difficulty = 16 
             # Attribute could be Willpower or Empathy depending on goal (control vs understanding)
             success, margin, desc = self.skill_check(character, "Willpower", "Dreamwork", dreamwork_difficulty)
             if success:
                 dreamwork_success = True
                 # TODO: Apply bonus/mitigation based on successful Dreamwork check
                 logger.info(f"{character.name} successfully used Dreamwork skill.")

        # Generate the core dream outcome
        outcome = self._generate_dream_outcome(character, context)
        message = outcome.get("message", "A strange dream unfolds.")

        # Apply effects and enhance message based on effect type
        effect_type = outcome.get("effect")
        if effect_type == "void_change":
            change = outcome.get("change", 0)
            if change != 0:
                 _, spike_effect = self.apply_void_gain(character, change)
                 if change > 0:
                     message = f"A nightmare increases your Void by {change}. {message}"
                 else:
                     message = f"A peaceful dream decreases your Void by {abs(change)}. {message}"
                 if spike_effect: 
                     message += f" {spike_effect}"
        elif effect_type == "bond_shift":
            target_bond_name = outcome.get("target_bond")
            change = outcome.get("change", 0)
            if target_bond_name and change != 0:
                for bond in character.bonds:
                    if bond.get("name") == target_bond_name:
                        bond["strength"] = max(1, min(5, bond.get("strength", 1) + change)) # Clamp strength 1-5
                        logger.info(f"Bond '{target_bond_name}' strength changed by {change} for {character.name}.")
                        message = f"Your bond with {target_bond_name} has shifted. {message}"
                        break
        elif effect_type == "insight":
            # Ensure insight is mentioned in the message
            message = f"You gain an insight: {message}"
        elif effect_type == "shared_dream":
             # TODO: Implement logic to notify/affect other participants
             logger.info(f"Shared dream triggered involving: {outcome.get('participants')}")
             message = f"Shared dream with {', '.join(outcome.get('participants',[]))}. {message}" # Indicate participants

        # TODO: Handle other effects like confrontation, lasting narrative consequences

        return message

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
