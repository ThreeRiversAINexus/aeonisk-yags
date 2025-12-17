#!/usr/bin/env python3
"""
Add Dexterity attribute to all characters in session configs.

Adds Dexterity=3 (typical human value) to any character missing it.
Preserves existing Dexterity values if already present.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


def add_dexterity_to_character(character: Dict[str, Any]) -> bool:
    """
    Add Dexterity to a character if missing.

    Args:
        character: Character dict

    Returns:
        True if Dexterity was added, False if already present
    """
    attributes = character.get('attributes', {})

    if 'Dexterity' in attributes:
        return False  # Already has Dexterity

    # Add Dexterity=3 (typical human value)
    attributes['Dexterity'] = 3
    character['attributes'] = attributes

    return True


def process_config(config_path: Path, dry_run: bool = True) -> Tuple[bool, int, List[str]]:
    """
    Process a single session config file.

    Args:
        config_path: Path to config file
        dry_run: If True, don't write changes

    Returns:
        Tuple of (success, num_characters_modified, list of character names)
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        return (False, 0, [f"Error reading: {e}"])

    modified_characters = []

    # Get characters from all possible locations
    all_characters = []

    # agents.players
    agents = config.get('agents', {})
    players = agents.get('players', [])
    all_characters.extend(players)

    # party (old structure)
    party = config.get('party', [])
    all_characters.extend(party)

    # npcs
    npcs = config.get('npcs', [])
    all_characters.extend(npcs)

    # Add Dexterity to each character
    for character in all_characters:
        if add_dexterity_to_character(character):
            char_name = character.get('name', 'Unknown')
            modified_characters.append(char_name)

    if not modified_characters:
        return (True, 0, [])

    if dry_run:
        return (True, len(modified_characters), modified_characters)

    # Write back to file
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write('\n')

        # Validate JSON
        with open(config_path, 'r', encoding='utf-8') as f:
            json.load(f)

        return (True, len(modified_characters), modified_characters)
    except Exception as e:
        return (False, 0, [f"Error writing: {e}"])


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Add Dexterity attribute to characters in session configs')
    parser.add_argument('--path', default='scripts/session_configs', help='Path to configs directory')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without modifying files')
    parser.add_argument('--verbose', action='store_true', help='Show all modified characters')

    args = parser.parse_args()

    config_dir = Path(args.path)
    if not config_dir.exists():
        print(f"❌ Directory not found: {config_dir}")
        sys.exit(1)

    # Find all JSON files recursively
    json_files = list(config_dir.rglob('*.json'))

    if not json_files:
        print(f"❌ No JSON files found in {config_dir}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Adding Dexterity to session configs")
    print(f"Path: {config_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else '🔥 LIVE 🔥'}")
    print(f"Found {len(json_files)} JSON files")
    print(f"{'='*60}\n")

    if not args.dry_run:
        response = input("⚠️  LIVE MODE - This will modify files. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
        print()

    total_files_modified = 0
    total_characters_modified = 0
    errors = []

    for config_path in sorted(json_files):
        success, num_modified, details = process_config(config_path, dry_run=args.dry_run)

        if not success:
            errors.append(f"{config_path.name}: {details[0]}")
            continue

        if num_modified > 0:
            total_files_modified += 1
            total_characters_modified += num_modified

            icon = '📋' if args.dry_run else '✅'
            print(f"{icon} {config_path.name}: {num_modified} characters modified")

            if args.verbose and details:
                for char_name in details:
                    print(f"     → {char_name}")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Files modified: {total_files_modified}")
    print(f"  Characters modified: {total_characters_modified}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for error in errors:
            print(f"    ❌ {error}")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("💡 Run without --dry-run to apply changes")
    else:
        print("✅ Changes applied successfully")

    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
