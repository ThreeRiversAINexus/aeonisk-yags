"""
Dataset manager module for the Aeonisk YAGS toolkit.

This module provides tools for managing and recording dataset entries.
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from aeonisk.core.models import SkillCheck, PlayerAction, DatasetEntry
from aeonisk.utils.file_utils import (
    ensure_directory_exists,
    get_session_dataset_directory,
    get_skill_checks_file,
    get_player_actions_file
)

# Configure logging
logger = logging.getLogger(__name__)


class DatasetManager:
    """Manager for dataset recording and retrieval."""
    
    def __init__(self, session_name: Optional[str] = None):
        """
        Initialize the dataset manager.
        
        Args:
            session_name: Optional name of the session. If not provided, a timestamp will be used.
        """
        self.session_name = session_name
        self.session_dir = get_session_dataset_directory(session_name)
        self.skill_checks: List[Dict[str, Any]] = []
        self.player_actions: List[Dict[str, Any]] = []
        
        # Load existing data if available
        self._load_skill_checks()
        self._load_player_actions()
    
    def _load_skill_checks(self):
        """Load skill checks from the skill checks file."""
        skill_checks_file = get_skill_checks_file(self.session_dir)
        
        if os.path.exists(skill_checks_file):
            try:
                with open(skill_checks_file, 'r', encoding='utf-8') as f:
                    self.skill_checks = json.load(f)
                logger.info(f"Loaded {len(self.skill_checks)} skill checks from {skill_checks_file}")
            except Exception as e:
                logger.error(f"Error loading skill checks: {str(e)}")
    
    def _load_player_actions(self):
        """Load player actions from the player actions file."""
        player_actions_file = get_player_actions_file(self.session_dir)
        
        if os.path.exists(player_actions_file):
            try:
                with open(player_actions_file, 'r', encoding='utf-8') as f:
                    self.player_actions = json.load(f)
                logger.info(f"Loaded {len(self.player_actions)} player actions from {player_actions_file}")
            except Exception as e:
                logger.error(f"Error loading player actions: {str(e)}")
    
    def record_skill_check(self, skill_check: SkillCheck) -> bool:
        """
        Record a skill check to the dataset.
        
        Args:
            skill_check: The skill check to record.
            
        Returns:
            True if the skill check was recorded successfully, False otherwise.
        """
        try:
            # Convert the skill check to a dictionary
            skill_check_dict = skill_check.model_dump()
            
            # Add the skill check to the list
            self.skill_checks.append(skill_check_dict)
            
            # Save the skill checks to the file
            skill_checks_file = get_skill_checks_file(self.session_dir)
            with open(skill_checks_file, 'w', encoding='utf-8') as f:
                json.dump(self.skill_checks, f, indent=2)
            
            logger.debug(f"Recorded skill check to {skill_checks_file}")
            return True
        except Exception as e:
            logger.error(f"Error recording skill check: {str(e)}")
            return False
    
    def record_player_action(self, player_action: PlayerAction) -> bool:
        """
        Record a player action to the dataset.
        
        Args:
            player_action: The player action to record.
            
        Returns:
            True if the player action was recorded successfully, False otherwise.
        """
        try:
            # Convert the player action to a dictionary
            player_action_dict = player_action.model_dump()
            
            # Add the player action to the list
            self.player_actions.append(player_action_dict)
            
            # Save the player actions to the file
            player_actions_file = get_player_actions_file(self.session_dir)
            with open(player_actions_file, 'w', encoding='utf-8') as f:
                json.dump(self.player_actions, f, indent=2)
            
            logger.debug(f"Recorded player action to {player_actions_file}")
            return True
        except Exception as e:
            logger.error(f"Error recording player action: {str(e)}")
            return False
    
    def create_dataset_entry(self) -> Optional[DatasetEntry]:
        """
        Create a dataset entry from the recorded skill checks and player actions.
        
        Returns:
            A DatasetEntry object, or None if there are no skill checks or player actions.
        """
        if not self.skill_checks and not self.player_actions:
            return None
        
        try:
            # Create a task ID based on the session name and timestamp
            task_id = f"YAGS-SESSION-{self.session_name or datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Extract character information from the player actions
            characters = []
            for action in self.player_actions:
                character_name = action.get("character_name")
                if character_name and not any(c.get("name") == character_name for c in characters):
                    characters.append({"name": character_name})
            
            # Create a dataset entry
            dataset_entry = DatasetEntry(
                task_id=task_id,
                domain={"core": "gameplay", "subdomain": "session"},
                scenario="Session gameplay",
                environment="Aeonisk YAGS game",
                stakes="Player actions and skill checks",
                characters=characters,
                goal="Record gameplay data",
                expected_fields=["character_name", "action_text", "result_text", "skill_checks"],
                gold_answer={
                    "player_actions": self.player_actions,
                    "skill_checks": self.skill_checks
                }
            )
            
            return dataset_entry
        except Exception as e:
            logger.error(f"Error creating dataset entry: {str(e)}")
            return None
    
    def save_dataset_entry(self, dataset_entry: DatasetEntry) -> bool:
        """
        Save a dataset entry to a file.
        
        Args:
            dataset_entry: The dataset entry to save.
            
        Returns:
            True if the dataset entry was saved successfully, False otherwise.
        """
        try:
            # Convert the dataset entry to a dictionary
            dataset_entry_dict = dataset_entry.model_dump()
            
            # Save the dataset entry to a file
            dataset_file = os.path.join(self.session_dir, f"{dataset_entry.task_id}.json")
            with open(dataset_file, 'w', encoding='utf-8') as f:
                json.dump(dataset_entry_dict, f, indent=2)
            
            logger.info(f"Saved dataset entry to {dataset_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving dataset entry: {str(e)}")
            return False
