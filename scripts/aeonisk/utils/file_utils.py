"""
File utility functions for the Aeonisk YAGS toolkit.

This module provides utility functions for file operations.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)


def ensure_directory_exists(directory_path: str) -> bool:
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory_path: The path to the directory.
        
    Returns:
        True if the directory exists or was created, False otherwise.
    """
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating directory {directory_path}: {str(e)}")
        return False


def get_dataset_directory() -> str:
    """
    Get the path to the dataset directory.
    
    Returns:
        The path to the dataset directory.
    """
    # Use the datasets directory in the project root
    return "datasets"


def get_session_dataset_directory(session_name: Optional[str] = None) -> str:
    """
    Get the path to the session dataset directory.
    
    Args:
        session_name: Optional name of the session. If not provided, a timestamp will be used.
        
    Returns:
        The path to the session dataset directory.
    """
    dataset_dir = get_dataset_directory()
    
    if session_name:
        # Sanitize the session name to be a valid directory name
        session_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_name)
    else:
        # Use a timestamp if no session name is provided
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    session_dir = os.path.join(dataset_dir, "sessions", session_name)
    ensure_directory_exists(session_dir)
    
    return session_dir


def get_skill_checks_file(session_dir: str) -> str:
    """
    Get the path to the skill checks file for a session.
    
    Args:
        session_dir: The path to the session directory.
        
    Returns:
        The path to the skill checks file.
    """
    return os.path.join(session_dir, "skill_checks.json")


def get_player_actions_file(session_dir: str) -> str:
    """
    Get the path to the player actions file for a session.
    
    Args:
        session_dir: The path to the session directory.
        
    Returns:
        The path to the player actions file.
    """
    return os.path.join(session_dir, "player_actions.json")


def get_session_file(session_dir: str) -> str:
    """
    Get the path to the session file.
    
    Args:
        session_dir: The path to the session directory.
        
    Returns:
        The path to the session file.
    """
    return os.path.join(session_dir, "session.json")
