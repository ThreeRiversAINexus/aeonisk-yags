"""
Command-line interface for the Aeonisk YAGS game.

This module provides an enhanced CLI interface with clear separation between
narrative and mechanical elements, automatic skill checks, and dataset recording.
"""

import argparse
import json
import logging
import os
import sys
import shlex
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Union

from aeonisk.core.models import Character, NPC, Scenario, PlayerAction, SkillCheck
from aeonisk.engine.game import GameSession


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GameCLI:
    """Enhanced command-line interface for the Aeonisk YAGS game."""

    BANNER = """
    █████╗ ███████╗ ██████╗ ███╗   ██╗██╗███████╗██╗  ██╗    ██╗   ██╗ █████╗  ██████╗ ███████╗
   ██╔══██╗██╔════╝██╔═══██╗████╗  ██║██║██╔════╝██║ ██╔╝    ╚██╗ ██╔╝██╔══██╗██╔════╝ ██╔════╝
   ███████║█████╗  ██║   ██║██╔██╗ ██║██║███████╗█████╔╝      ╚████╔╝ ███████║██║  ███╗███████╗
   ██╔══██║██╔══╝  ██║   ██║██║╚██╗██║██║╚════██║██╔═██╗       ╚██╔╝  ██╔══██║██║   ██║╚════██║
   ██║  ██║███████╗╚██████╔╝██║ ╚████║██║███████║██║  ██╗       ██║   ██║  ██║╚██████╔╝███████║
   ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝       ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
                                                                                                
    """

    def __init__(self):
        """Initialize the CLI."""
        self.session = GameSession()
        self.show_mechanics = True
    
    def start(self):
        """Start the CLI."""
        print(self.BANNER)
        print("Welcome to the Aeonisk YAGS Game!")
        print("Type 'help' for a list of commands.")
        
        while True:
            try:
                command = input("\n> ").strip()
                
                if not command:
                    continue
                
                if command.lower() in ["exit", "quit"]:
                    print("Goodbye!")
                    break
                
                self.process_command(command)
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error: {str(e)}")
                print(f"Error: {str(e)}")
    
    def process_command(self, command_str: str):
        """
        Process a command.
        
        Args:
            command_str: The command string to process.
        """
        try:
            # Use shlex to handle quoted arguments properly
            parts = shlex.split(command_str)
            if not parts:
                return
            
            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            # Core commands
            if cmd == "help":
                self.show_help()
            elif cmd == "start":
                self.start_game(args)
            elif cmd == "load":
                self.load_session(args)
            
            # Character management
            elif cmd == "create":
                self.create_character(args)
            elif cmd == "list":
                self.list_characters()
            elif cmd == "select":
                self.select_character(args)
            elif cmd == "character":
                self.show_character()
            
            # Game actions
            elif cmd in ["look", "examine", "inspect"]:
                self.perform_action(f"look at {' '.join(args)}" if args else "look around")
            elif cmd == "talk":
                if not args:
                    print("Usage: talk <npc> [message]")
                    return
                npc = args[0]
                message = " ".join(args[1:]) if len(args) > 1 else ""
                self.perform_action(f"talk to {npc}{' saying ' + message if message else ''}")
            elif cmd == "do":
                if not args:
                    print("Usage: do <action>")
                    return
                self.perform_action(" ".join(args))
            elif cmd == "go":
                if not args:
                    print("Usage: go <location>")
                    return
                self.perform_action(f"go to {' '.join(args)}")
            elif cmd == "use":
                if not args:
                    print("Usage: use <item> [on <target>]")
                    return
                if len(args) > 2 and args[1].lower() == "on":
                    self.perform_action(f"use {args[0]} on {' '.join(args[2:])}")
                else:
                    self.perform_action(f"use {' '.join(args)}")
            
            # Manual skill check
            elif cmd == "check":
                self.skill_check(args)
            
            # Scenario and NPC generation
            elif cmd == "scenario":
                self.generate_scenario(args)
            elif cmd == "npc":
                self.generate_npc(args)
            
            # Session management
            elif cmd == "save":
                self.save_session(args)
            
            # Display options
            elif cmd == "mechanics":
                self.toggle_mechanics()
            
            # Unknown command
            else:
                # If not a recognized command, treat it as an action
                self.perform_action(command_str)
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")
            print(f"Error: {str(e)}")
    
    def show_help(self):
        """Show help information."""
        print("\nAvailable commands:")
        print("\n# Core commands")
        print("  start <name>           - Start a new game with a name")
        print("  load <name>            - Load a saved game")
        print("  help                   - Show this help message")
        print("  exit/quit              - Exit the game")
        
        print("\n# Character commands")
        print("  create <name> <concept> - Create a new character")
        print("  list                   - List all characters")
        print("  select <index>         - Select a character")
        print("  character              - View character details")
        
        print("\n# Game actions")
        print("  look/examine [object]  - Look around or examine something")
        print("  talk <npc> [message]   - Talk to an NPC")
        print("  do <action>            - Perform an action")
        print("  go <location>          - Move to a location")
        print("  use <item> [on <target>] - Use an item, possibly on a target")
        
        print("\n# Advanced commands")
        print("  check <attr> <skill> <diff> - Perform a manual skill check")
        print("  scenario [theme] [difficulty] - Generate a scenario")
        print("  npc [faction] [role]  - Generate an NPC")
        print("  save <file>           - Save the current session")
        print("  mechanics             - Toggle display of mechanical details")
    
    def start_game(self, args: List[str]):
        """
        Start a new game.
        
        Args:
            args: Command arguments.
        """
        if not args:
            print("Usage: start <name>")
            return
        
        name = args[0]
        
        # Check if a save file with this name exists
        if os.path.exists(name):
            print(f"A saved game named '{name}' already exists.")
            print("Use 'load {name}' to load it, or choose a different name.")
            return
        
        # Create a new session
        self.session = GameSession()
        
        print(f"Started a new game: {name}")
        print("Use 'create <name> <concept>' to create a character.")
    
    def create_character(self, args: List[str]):
        """
        Create a new character.
        
        Args:
            args: Command arguments.
        """
        if len(args) < 2:
            print("Usage: create <name> <concept>")
            return
        
        name = args[0]
        concept = " ".join(args[1:])
        
        character = self.session.create_character(name, concept)
        
        print(f"Created character: {character.name} ({character.concept})")
        print("This character is now selected.")
        
        # If no scenario exists, suggest generating one
        if not self.session.scenario:
            print("\nTip: Use 'scenario [theme] [difficulty]' to generate a scenario.")
    
    def list_characters(self):
        """List all characters in the session."""
        if not self.session.characters:
            print("No characters in the session.")
            print("Use 'create <name> <concept>' to create a character.")
            return
        
        print("\nCharacters:")
        for i, character in enumerate(self.session.characters):
            print(f"  {i}: {character.name} ({character.concept})")
        
        if self.session.current_character:
            print(f"\nCurrent character: {self.session.current_character.name}")
    
    def select_character(self, args: List[str]):
        """
        Select a character.
        
        Args:
            args: Command arguments.
        """
        if not args:
            print("Usage: select <index>")
            return
        
        try:
            index = int(args[0])
            character = self.session.select_character(index)
            
            if character:
                print(f"Selected character: {character.name} ({character.concept})")
            else:
                print(f"Invalid index: {index}")
        except ValueError:
            print(f"Invalid index: {args[0]}")
    
    def show_character(self):
        """Show details of the current character."""
        character = self.session.current_character
        
        if not character:
            print("No character selected. Use 'select <index>' to select a character.")
            return
        
        print(f"\nCharacter: {character.name} ({character.concept})")
        
        print("\nAttributes:")
        for attr, value in character.attributes.items():
            print(f"  {attr}: {value}")
        
        print("\nSkills:")
        for skill, value in character.skills.items():
            print(f"  {skill}: {value}")
        
        print(f"\nVoid Score: {character.void_score}")
        print(f"Soulcredit: {character.soulcredit}")
        
        if character.true_will:
            print(f"True Will: {character.true_will}")
        
        if character.bonds:
            print("\nBonds:")
            for bond in character.bonds:
                print(f"  {bond.get('name', 'Unknown')}: {bond.get('type', 'Unknown')}")
        
        if character.equipment:
            print("\nEquipment:")
            for item in character.equipment:
                print(f"  {item.get('name', 'Unknown')}")
    
    def skill_check(self, args: List[str]):
        """
        Perform a manual skill check.
        
        Args:
            args: Command arguments.
        """
        character = self.session.current_character
        
        if not character:
            print("No character selected. Use 'select <index>' to select a character.")
            return
        
        if len(args) < 3:
            print("Usage: check <attribute> <skill> <difficulty>")
            return
        
        try:
            attribute = args[0]
            skill = args[1]
            difficulty = int(args[2])
            
            success, margin, description = self.session.skill_check(
                character, attribute, skill, difficulty
            )
            
            print("\n[NARRATIVE]")
            print(description)
            
            if self.show_mechanics:
                print("\n[MECHANICS]")
                attr_val = character.attributes.get(attribute, 0)
                skill_val = character.skills.get(skill, 0)
                ability = attr_val * skill_val
                print(f"• {attribute} + {skill} check: {attr_val}×{skill_val} + d20 = {ability + margin + difficulty} vs difficulty {difficulty}")
                print(f"• {'SUCCESS' if success else 'FAILURE'} (margin: {'+' if margin > 0 else ''}{margin})")
            
            print("\n[Dataset entry recorded]")
        except ValueError:
            print(f"Invalid difficulty: {args[2]}")
        except Exception as e:
            print(f"Error performing skill check: {str(e)}")
    
    def generate_scenario(self, args: List[str]):
        """
        Generate a scenario.
        
        Args:
            args: Command arguments.
        """
        theme = args[0] if len(args) > 0 else None
        difficulty = args[1] if len(args) > 1 else None
        
        print(f"Generating scenario{' with theme: ' + theme if theme else ''}{' and difficulty: ' + difficulty if difficulty else ''}...")
        
        scenario = self.session.generate_scenario(theme=theme, difficulty=difficulty)
        
        if "error" in scenario:
            print(f"Error generating scenario: {scenario['error']}")
            return
        
        print("\n[SCENARIO]")
        
        # Display scenario overview
        if "Scenario Overview" in scenario:
            overview = scenario["Scenario Overview"]
            if isinstance(overview, dict):
                if "Theme" in overview:
                    print(f"Theme: {overview['Theme']}")
                if "Difficulty" in overview:
                    print(f"Difficulty: {overview['Difficulty']}")
                if "Setting" in overview:
                    print(f"Setting: {overview['Setting']}")
                if "Objective" in overview:
                    print(f"\nObjective: {overview['Objective']}")
        
        # Display setting description
        if "Setting Description" in scenario:
            setting = scenario["Setting Description"]
            if isinstance(setting, dict):
                if "Location" in setting:
                    print(f"\nLocation: {setting['Location']}")
                if "Atmosphere" in setting:
                    print(f"Atmosphere: {setting['Atmosphere']}")
        
        # Display NPCs
        if "Key NPCs" in scenario:
            npcs = scenario["Key NPCs"]
            if isinstance(npcs, dict):
                print("\nKey NPCs:")
                for name, npc in npcs.items():
                    if isinstance(npc, dict):
                        print(f"  {name}: {npc.get('Role', 'Unknown')}")
        
        # Display plot hooks
        if "Plot Hooks" in scenario and isinstance(scenario["Plot Hooks"], list):
            print("\nPlot Hooks:")
            for hook in scenario["Plot Hooks"]:
                print(f"  • {hook}")
        
        print("\nUse 'save <file>' to save the session with this scenario.")
        print("Try 'look around' to begin exploring.")
    
    def generate_npc(self, args: List[str]):
        """
        Generate an NPC.
        
        Args:
            args: Command arguments.
        """
        faction = args[0] if len(args) > 0 else None
        role = args[1] if len(args) > 1 else None
        
        print(f"Generating NPC{' from faction: ' + faction if faction else ''}{' with role: ' + role if role else ''}...")
        
        npc = self.session.generate_npc(faction=faction, role=role)
        
        if "error" in npc:
            print(f"Error generating NPC: {npc['error']}")
            return
        
        print("\n[NPC]")
        
        if "name" in npc:
            print(f"Name: {npc['name']}")
        if "faction" in npc:
            print(f"Faction: {npc['faction']}")
        if "concept" in npc:
            print(f"Concept: {npc['concept']}")
        if "description" in npc:
            print(f"\nDescription: {npc['description']}")
        
        if self.show_mechanics:
            if "attributes" in npc and isinstance(npc["attributes"], dict):
                print("\nAttributes:")
                for attr, value in npc["attributes"].items():
                    print(f"  {attr}: {value}")
            
            if "skills" in npc and isinstance(npc["skills"], dict):
                print("\nSkills:")
                for skill, value in npc["skills"].items():
                    print(f"  {skill}: {value}")
        
        print("\nUse 'save <file>' to save the session with this NPC.")
        print("Try 'talk <npc name>' to interact with the NPC.")
    
    def perform_action(self, action_text: str):
        """
        Perform a player action.
        
        Args:
            action_text: The action text.
        """
        character = self.session.current_character
        
        if not character:
            print("No character selected. Use 'select <index>' to select a character.")
            return
        
        print(f"Performing action: {action_text}...")
        
        result = self.session.process_player_action(character, action_text)
        
        print(result)
    
    def save_session(self, args: List[str]):
        """
        Save the current session.
        
        Args:
            args: Command arguments.
        """
        if not args:
            print("Usage: save <file>")
            return
        
        file_path = args[0]
        
        success = self.session.save_session(file_path)
        
        if success:
            print(f"Session saved to {file_path}")
        else:
            print(f"Error saving session to {file_path}")
    
    def load_session(self, args: List[str]):
        """
        Load a session.
        
        Args:
            args: Command arguments.
        """
        if not args:
            print("Usage: load <file>")
            return
        
        file_path = args[0]
        
        success = self.session.load_session(file_path)
        
        if success:
            print(f"Session loaded from {file_path}")
            if self.session.current_character:
                print(f"Selected character: {self.session.current_character.name}")
        else:
            print(f"Error loading session from {file_path}")
    
    def toggle_mechanics(self):
        """Toggle the display of mechanical details."""
        self.show_mechanics = not self.show_mechanics
        print(f"Mechanical details {'shown' if self.show_mechanics else 'hidden'}.")


def main():
    """Main entry point for the CLI."""
    cli = GameCLI()
    cli.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
