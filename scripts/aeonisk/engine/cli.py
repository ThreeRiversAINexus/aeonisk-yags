"""
Command-line interface for the game engine.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

from aeonisk.engine.game import GameSession, Character


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GameCLI:
    """Command-line interface for the game engine."""

    def __init__(self):
        """Initialize the CLI."""
        self.session = GameSession()
        self.current_character = None

    def start(self):
        """Start the CLI."""
        print("Welcome to the Aeonisk YAGS Game!")
        print("Type 'help' for a list of commands.")
        
        while True:
            try:
                command = input("\n> ").strip()
                
                if not command:
                    continue
                
                if command.lower() == "exit" or command.lower() == "quit":
                    print("Goodbye!")
                    break
                
                self.process_command(command)
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error: {str(e)}")
                print(f"Error: {str(e)}")

    def process_command(self, command: str):
        """
        Process a command.
        
        Args:
            command: The command to process.
        """
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            self.show_help()
        elif cmd == "create":
            self.create_character(args)
        elif cmd == "load":
            self.load_character(args)
        elif cmd == "list":
            self.list_characters()
        elif cmd == "select":
            self.select_character(args)
        elif cmd == "check":
            self.skill_check(args)
        elif cmd == "scenario":
            self.generate_scenario(args)
        elif cmd == "npc":
            self.generate_npc(args)
        elif cmd == "action":
            self.process_action(args)
        elif cmd == "save":
            self.save_session(args)
        elif cmd == "load_session":
            self.load_session(args)
        else:
            print(f"Unknown command: {cmd}")
            print("Type 'help' for a list of commands.")

    def show_help(self):
        """Show help information."""
        print("\nAvailable commands:")
        print("  help                  - Show this help message")
        print("  create <name> <concept> - Create a new character")
        print("  load <file>           - Load a character from a file")
        print("  list                  - List all characters")
        print("  select <index>        - Select a character")
        print("  check <attr> <skill> <diff> - Perform a skill check")
        print("  scenario [theme] [difficulty] - Generate a scenario")
        print("  npc [faction] [role]  - Generate an NPC")
        print("  action <text>         - Process a player action")
        print("  save <file>           - Save the current session")
        print("  load_session <file>   - Load a session")
        print("  exit/quit             - Exit the game")

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
        self.current_character = character
        
        print(f"Created character: {character.name} ({character.concept})")
        print("This character is now selected.")

    def load_character(self, args: List[str]):
        """
        Load a character from a file.
        
        Args:
            args: Command arguments.
        """
        if len(args) < 1:
            print("Usage: load <file>")
            return
        
        file_path = args[0]
        
        try:
            character = self.session.load_character(file_path)
            self.current_character = character
            
            print(f"Loaded character: {character.name} ({character.concept})")
            print("This character is now selected.")
        except Exception as e:
            print(f"Error loading character: {str(e)}")

    def list_characters(self):
        """List all characters in the session."""
        if not self.session.characters:
            print("No characters in the session.")
            return
        
        print("\nCharacters:")
        for i, character in enumerate(self.session.characters):
            print(f"  {i}: {character.name} ({character.concept})")
        
        if self.current_character:
            current_index = self.session.characters.index(self.current_character)
            print(f"\nCurrent character: {current_index}: {self.current_character.name}")

    def select_character(self, args: List[str]):
        """
        Select a character.
        
        Args:
            args: Command arguments.
        """
        if len(args) < 1:
            print("Usage: select <index>")
            return
        
        try:
            index = int(args[0])
            if index < 0 or index >= len(self.session.characters):
                print(f"Invalid index: {index}")
                return
            
            self.current_character = self.session.characters[index]
            print(f"Selected character: {self.current_character.name} ({self.current_character.concept})")
        except ValueError:
            print(f"Invalid index: {args[0]}")

    def skill_check(self, args: List[str]):
        """
        Perform a skill check.
        
        Args:
            args: Command arguments.
        """
        if not self.current_character:
            print("No character selected. Use 'select' to select a character.")
            return
        
        if len(args) < 3:
            print("Usage: check <attribute> <skill> <difficulty>")
            return
        
        try:
            attribute = args[0]
            skill = args[1]
            difficulty = int(args[2])
            
            success, margin, description = self.session.skill_check(
                self.current_character, attribute, skill, difficulty
            )
            
            print(f"\n{description}")
            print(f"Success: {success}, Margin: {margin}")
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
        
        if "raw_response" in scenario:
            print("\nGenerated scenario:")
            print(scenario["raw_response"])
            return
        
        print("\nGenerated scenario:")
        if "title" in scenario:
            print(f"Title: {scenario['title']}")
        if "overview" in scenario:
            print(f"\nOverview: {scenario['overview']}")
        if "setting" in scenario:
            print(f"\nSetting: {scenario['setting']}")
        if "npcs" in scenario:
            print("\nNPCs:")
            for npc in scenario["npcs"]:
                print(f"  - {npc.get('name', 'Unknown')}: {npc.get('role', 'Unknown')}")
        
        print("\nUse 'save <file>' to save the session with this scenario.")

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
        
        if "raw_response" in npc:
            print("\nGenerated NPC:")
            print(npc["raw_response"])
            return
        
        print("\nGenerated NPC:")
        if "name" in npc:
            print(f"Name: {npc['name']}")
        if "faction" in npc:
            print(f"Faction: {npc['faction']}")
        if "concept" in npc:
            print(f"Concept: {npc['concept']}")
        if "attributes" in npc:
            print("\nAttributes:")
            for attr, value in npc["attributes"].items():
                print(f"  {attr}: {value}")
        
        print("\nUse 'save <file>' to save the session with this NPC.")

    def process_action(self, args: List[str]):
        """
        Process a player action.
        
        Args:
            args: Command arguments.
        """
        if not self.current_character:
            print("No character selected. Use 'select' to select a character.")
            return
        
        if len(args) < 1:
            print("Usage: action <text>")
            return
        
        action = " ".join(args)
        
        print(f"Processing action: {action}...")
        
        result = self.session.process_player_action(self.current_character, action)
        
        print("\nResult:")
        print(result)

    def save_session(self, args: List[str]):
        """
        Save the current session.
        
        Args:
            args: Command arguments.
        """
        if len(args) < 1:
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
        if len(args) < 1:
            print("Usage: load_session <file>")
            return
        
        file_path = args[0]
        
        success = self.session.load_session(file_path)
        
        if success:
            print(f"Session loaded from {file_path}")
            if self.session.characters:
                self.current_character = self.session.characters[0]
                print(f"Selected character: {self.current_character.name} ({self.current_character.concept})")
        else:
            print(f"Error loading session from {file_path}")


def main():
    """Main entry point for the CLI."""
    cli = GameCLI()
    cli.start()


if __name__ == "__main__":
    main()
