#!/usr/bin/env python3
"""
Migrate session configs: Health → Endurance

Affected: 17 config files, 64 characters total (according to audit)
Safe: JSON-aware, validates after migration, idempotent
"""

import json
import sys
from pathlib import Path
from typing import Dict, List


def find_configs_with_health() -> List[Path]:
    """Find all session configs using deprecated 'Health' attribute"""
    configs_dir = Path("scripts/session_configs")
    affected = []

    for config_file in configs_dir.glob("*.json"):
        with open(config_file) as f:
            data = json.load(f)

        # Check all character definitions
        if has_health_attribute(data):
            affected.append(config_file)

    return affected


def has_health_attribute(config: Dict) -> bool:
    """Check if config uses deprecated 'Health' attribute"""
    # Check player characters
    for player in config.get("agents", {}).get("players", []):
        if "Health" in player.get("attributes", {}):
            return True

    # Check NPCs
    for npc in config.get("npcs", []):
        if "Health" in npc.get("attributes", {}):
            return True

    # Check enemies
    for enemy in config.get("initial_enemies", []):
        if "Health" in enemy.get("attributes", {}):
            return True

    return False


def migrate_config(config_file: Path) -> int:
    """Migrate a single config file, return number of changes"""
    with open(config_file) as f:
        data = json.load(f)

    changes = 0

    # Migrate player characters
    for player in data.get("agents", {}).get("players", []):
        attrs = player.get("attributes", {})
        if "Health" in attrs:
            attrs["Endurance"] = attrs.pop("Health")
            changes += 1
            print(f"  Migrated player: {player.get('name', 'Unknown')}")

    # Migrate NPCs
    for npc in data.get("npcs", []):
        attrs = npc.get("attributes", {})
        if "Health" in attrs:
            attrs["Endurance"] = attrs.pop("Health")
            changes += 1
            print(f"  Migrated NPC: {npc.get('name', 'Unknown')}")

    # Migrate enemies
    for enemy in data.get("initial_enemies", []):
        attrs = enemy.get("attributes", {})
        if "Health" in attrs:
            attrs["Endurance"] = attrs.pop("Health")
            changes += 1
            print(f"  Migrated enemy: {enemy.get('name', 'Unknown')}")

    # Write back with formatting preserved
    with open(config_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')  # Trailing newline

    return changes


def validate_config(config_file: Path) -> bool:
    """Validate config after migration (basic check)"""
    try:
        with open(config_file) as f:
            data = json.load(f)

        # Check no "Health" remains
        if has_health_attribute(data):
            print(f"  ❌ VALIDATION FAILED: {config_file} still has 'Health'")
            return False

        print(f"  ✓ Validation passed")
        return True
    except Exception as e:
        print(f"  ❌ VALIDATION FAILED: {config_file} - {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate Health → Endurance in session configs")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm migration")
    args = parser.parse_args()

    print("=== Health → Endurance Migration ===\n")

    # Find affected configs
    affected = find_configs_with_health()
    print(f"Found {len(affected)} configs with 'Health' attribute:\n")
    for cfg in affected:
        print(f"  - {cfg.name}")

    if not affected:
        print("✓ No configs need migration!")
        return 0

    # Confirm
    print(f"\nWill migrate {len(affected)} files.")
    if not args.yes:
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return 1
    else:
        print("Auto-confirming (--yes flag)")

    # Migrate each file
    total_changes = 0
    failed = []

    for config_file in affected:
        print(f"\n{config_file.name}:")
        changes = migrate_config(config_file)
        total_changes += changes

        if not validate_config(config_file):
            failed.append(config_file)

    if failed:
        print(f"\n❌ Migration failed for {len(failed)} files:")
        for f in failed:
            print(f"  - {f.name}")
        print("\nReview errors above and fix manually.")
        return 1

    print(f"\n=== Migration Complete ===")
    print(f"Files modified: {len(affected)}")
    print(f"Attributes migrated: {total_changes}")
    print("\nNext steps:")
    print("  1. Review: git diff scripts/session_configs/")
    print("  2. Test: Run a migrated config to verify")
    print("  3. Commit: git commit -m 'migrate: Health → Endurance in session configs'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
