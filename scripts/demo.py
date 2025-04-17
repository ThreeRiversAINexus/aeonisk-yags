#!/usr/bin/env python3
"""
Demo script for the Aeonisk YAGS game.

This script demonstrates the functionality of the improved game by running
through a simple scenario.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aeonisk.engine.game import GameSession
from aeonisk.core.models import Character


def print_with_delay(text, delay=0.5):
    """Print text with a delay between lines."""
    for line in text.split('\n'):
        print(line)
        time.sleep(delay)


def main():
    """Run the demo."""
    print_with_delay("""
    █████╗ ███████╗ ██████╗ ███╗   ██╗██╗███████╗██╗  ██╗    ██╗   ██╗ █████╗  ██████╗ ███████╗
   ██╔══██╗██╔════╝██╔═══██╗████╗  ██║██║██╔════╝██║ ██╔╝    ╚██╗ ██╔╝██╔══██╗██╔════╝ ██╔════╝
   ███████║█████╗  ██║   ██║██╔██╗ ██║██║███████╗█████╔╝      ╚████╔╝ ███████║██║  ███╗███████╗
   ██╔══██║██╔══╝  ██║   ██║██║╚██╗██║██║╚════██║██╔═██╗       ╚██╔╝  ██╔══██║██║   ██║╚════██║
   ██║  ██║███████╗╚██████╔╝██║ ╚████║██║███████║██║  ██╗       ██║   ██║  ██║╚██████╔╝███████║
   ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝       ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
                                                                                                
    """, delay=0.1)
    
    print_with_delay("Welcome to the Aeonisk YAGS Game Demo!")
    print_with_delay("This demo will walk you through the basic functionality of the game.")
    print_with_delay("Press Ctrl+C at any time to exit.")
    print()
    
    # Initialize the game session
    print_with_delay("Initializing game session...")
    session = GameSession()
    
    # Create a character
    print_with_delay("\nCreating a character...")
    character = session.create_character("Heru", "Astral Commerce Group agent")
    print_with_delay(f"Created character: {character.name} ({character.concept})")
    
    # Generate a scenario
    print_with_delay("\nGenerating a scenario...")
    scenario = session.generate_scenario(theme="rave", difficulty="easy")
    
    # Display the scenario
    print_with_delay("\n[SCENARIO]")
    if "Scenario Overview" in scenario:
        overview = scenario["Scenario Overview"]
        if isinstance(overview, dict):
            if "Theme" in overview:
                print_with_delay(f"Theme: {overview['Theme']}")
            if "Difficulty" in overview:
                print_with_delay(f"Difficulty: {overview['Difficulty']}")
            if "Setting" in overview:
                print_with_delay(f"Setting: {overview['Setting']}")
            if "Objective" in overview:
                print_with_delay(f"\nObjective: {overview['Objective']}")
    
    # Perform an action
    print_with_delay("\nPerforming an action: 'look around'")
    result = session.process_player_action(character, "look around")
    print_with_delay(result)
    
    # Perform another action
    print_with_delay("\nPerforming an action: 'talk to DJ Lumina'")
    result = session.process_player_action(character, "talk to DJ Lumina")
    print_with_delay(result)
    
    # Save the session
    print_with_delay("\nSaving the session...")
    session.save_session("demo_session.json")
    print_with_delay("Session saved to demo_session.json")
    
    # End the demo
    print_with_delay("\nDemo complete! To play the full game, run:")
    print_with_delay("python scripts/aeonisk_game.py")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo interrupted. Goodbye!")
        sys.exit(0)
