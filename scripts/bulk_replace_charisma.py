#!/usr/bin/env python3
"""
Bulk replace "Charisma" → "Empathy" in session config JSON files.
Handles both "Charisma" and "charisma" (case-sensitive).
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

def replace_in_dict(obj, replacements: List[str]) -> None:
    """Recursively replace Charisma → Empathy in dict keys."""
    if isinstance(obj, dict):
        keys_to_replace = []
        for key in obj.keys():
            if key == "Charisma":
                keys_to_replace.append((key, "Empathy"))
            elif key == "charisma":
                keys_to_replace.append((key, "empathy"))

        for old_key, new_key in keys_to_replace:
            obj[new_key] = obj.pop(old_key)
            replacements.append(f"{old_key} → {new_key}")

        for value in obj.values():
            replace_in_dict(value, replacements)
    elif isinstance(obj, list):
        for item in obj:
            replace_in_dict(item, replacements)

def process_file(filepath: Path, dry_run: bool = True) -> Tuple[bool, List[str]]:
    """Process single JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        replacements = []
        replace_in_dict(data, replacements)

        if not replacements:
            return (True, [])

        if dry_run:
            return (True, replacements)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')

        # Validate
        with open(filepath, 'r', encoding='utf-8') as f:
            json.load(f)

        return (True, replacements)
    except Exception as e:
        return (False, [f"Error: {e}"])

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--path', default='scripts/session_configs', help='Path to search for JSON files')
    args = parser.parse_args()

    json_files = list(Path(args.path).rglob('*.json'))
    print(f"Found {len(json_files)} JSON files in {args.path}")
    print(f"Mode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE (will modify files)'}\n")

    if not args.dry_run:
        response = input("⚠️  LIVE MODE - Files will be modified. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    modified = 0
    errors = 0

    for filepath in json_files:
        success, replacements = process_file(filepath, args.dry_run)
        if not success:
            print(f"❌ {filepath}: {replacements[0]}")
            errors += 1
        elif replacements:
            print(f"{'📋' if args.dry_run else '✅'} {filepath.name}: {len(replacements)} changes")
            modified += 1

    print(f"\nSummary: {modified} files with replacements, {errors} errors")
    sys.exit(1 if errors > 0 else 0)

if __name__ == '__main__':
    main()
