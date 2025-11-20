#!/usr/bin/env python3
"""
Migrate legacy vendor configs to NPC vendor format.

Converts old vendor configurations to the unified NPC vendor system.
This preserves backward compatibility while transitioning to the new system.

Usage:
    python scripts/migrate_vendors_to_npcs.py <config_file.json>
    python scripts/migrate_vendors_to_npcs.py <config_file.json> --in-place
    python scripts/migrate_vendors_to_npcs.py <config_file.json> --output new_config.json
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any


def migrate_vendor_to_npc(vendor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert legacy Vendor config to NPCSpawn format.

    Args:
        vendor: Legacy vendor configuration

    Returns:
        NPC spawn configuration with vendor fields
    """
    # Extract vendor fields
    name = vendor.get("name", "Unnamed Vendor")
    faction = vendor.get("faction", "Neutral")
    inventory = vendor.get("inventory", [])
    greeting = vendor.get("greeting", "Looking to trade?")
    vendor_type = vendor.get("vendor_type", "human_trader")
    vendor_id = vendor.get("vendor_id")  # May be None

    # Map vendor_type enum values to strings if needed
    if isinstance(vendor_type, dict) and "value" in vendor_type:
        vendor_type = vendor_type["value"]

    # Determine if this is a vending machine (static vendor)
    is_vending_machine = vendor_type in ["vending_machine", "supply_drone", "emergency_cache"]

    # Build NPC spawn config
    npc_config = {
        "name": name,
        "faction": faction,
        "entity_type": "neutral",
        "disposition": "neutral",
        "threat_level": "non_combatant",
        "description": vendor.get("description", f"{name} - a vendor selling goods"),
        "health": 50 if is_vending_machine else 25,
        "soak": 5 if is_vending_machine else 2,
        "skills": {} if is_vending_machine else {"Negotiate": 3},
        "is_vendor": True,
        "vendor_inventory": inventory,
        "vendor_greeting": greeting,
        "vendor_type": vendor_type,
        "accepts_purchases": True
    }

    # Add vendor_id as agent_id if present (for tracking)
    if vendor_id:
        npc_config["_legacy_vendor_id"] = vendor_id

    return npc_config


def migrate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate session config from legacy vendors to NPC vendors.

    Args:
        config: Session configuration dictionary

    Returns:
        Migrated configuration with NPC vendors
    """
    migrated = config.copy()

    # Check if config has legacy vendors
    if "vendors" not in config:
        print("  ℹ️  No legacy vendors found in config")
        return migrated

    vendors = config.get("vendors", [])
    if not vendors:
        print("  ℹ️  Vendors list is empty")
        return migrated

    print(f"  🔄 Migrating {len(vendors)} vendor(s) to NPC format...")

    # Convert vendors to NPC spawns
    npc_spawns = [migrate_vendor_to_npc(v) for v in vendors]

    # Add to or create npc_spawns list
    existing_npcs = migrated.get("npc_spawns", [])
    migrated["npc_spawns"] = existing_npcs + npc_spawns

    # Keep legacy vendors for backward compatibility (commented out with note)
    migrated["_legacy_vendors_migrated"] = vendors
    del migrated["vendors"]

    # Add migration metadata
    migrated["_migration_notes"] = (
        "Vendors migrated to NPC vendor system. "
        "Legacy vendor configs preserved in _legacy_vendors_migrated for reference. "
        "NPCs with is_vendor=True provide same functionality with enhanced capabilities."
    )

    print(f"  ✅ Migrated {len(npc_spawns)} vendor(s) to npc_spawns")

    return migrated


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy vendor configs to unified NPC vendor system"
    )
    parser.add_argument(
        "config",
        type=str,
        help="Path to session config JSON file"
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify config file in-place (creates .bak backup)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output path for migrated config (default: <config>_migrated.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing files"
    )

    args = parser.parse_args()

    config_path = Path(args.config)

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    print(f"📖 Reading config: {config_path}")

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)

    print(f"🔍 Analyzing config...")

    # Check if migration needed
    if "vendors" not in config:
        print("✅ Config already uses NPC vendor system (no 'vendors' field)")
        sys.exit(0)

    if not config.get("vendors"):
        print("ℹ️  Config has empty vendors list, no migration needed")
        sys.exit(0)

    # Perform migration
    print("\n🔄 Migrating vendors to NPC format...")
    migrated_config = migrate_config(config)

    if args.dry_run:
        print("\n📋 DRY RUN - No files written")
        print("\nMigrated config preview:")
        print(json.dumps(migrated_config.get("npc_spawns", []), indent=2))
        sys.exit(0)

    # Determine output path
    if args.in_place:
        output_path = config_path
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        print(f"💾 Creating backup: {backup_path}")
        config_path.rename(backup_path)
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = config_path.with_stem(config_path.stem + "_migrated")

    print(f"💾 Writing migrated config: {output_path}")

    with open(output_path, "w") as f:
        json.dump(migrated_config, f, indent=2)

    print("\n✅ Migration complete!")
    print(f"   Original vendors: {len(config.get('vendors', []))}")
    print(f"   Migrated to NPCs: {len([npc for npc in migrated_config.get('npc_spawns', []) if npc.get('is_vendor')])}")

    if args.in_place:
        print(f"   Backup saved: {backup_path}")
    else:
        print(f"   New config: {output_path}")

    print("\n📝 Next steps:")
    print("   1. Review migrated config")
    print("   2. Test with: python scripts/run_multiagent_session.py <config>")
    print("   3. Delete backup (.bak) after verification")


if __name__ == "__main__":
    main()
