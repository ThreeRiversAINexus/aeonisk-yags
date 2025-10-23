#!/usr/bin/env python3
"""
Validation script for JSONL logging system.

Validates that all logged events conform to expected schemas and that
required fields are present for ML training and balance analysis.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Set
from collections import Counter, defaultdict


# Event type schemas - define required fields for each event type
EVENT_SCHEMAS = {
    "session_start": {
        "required": ["event_type", "ts", "session", "config", "version"],
        "optional": []
    },
    "scenario": {
        "required": ["event_type", "ts", "session", "scenario"],
        "optional": []
    },
    "round_start": {
        "required": ["event_type", "ts", "session", "round"],
        "optional": []
    },
    "action_resolution": {
        "required": ["event_type", "ts", "session", "round", "phase", "agent", "action", "roll", "economy", "clocks", "effects"],
        "optional": ["context"]
    },
    "combat_action": {
        "required": ["event_type", "ts", "session", "round", "attacker", "defender", "weapon", "attack"],
        "optional": ["damage", "wounds_dealt", "defender_state_after"]
    },
    "character_state": {
        "required": ["event_type", "ts", "session", "round", "character_id", "character_name", "health", "max_health", "wounds", "void_score", "soulcredit", "position", "conditions", "is_defeated"],
        "optional": []
    },
    "enemy_spawn": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "template", "stats", "position", "tactics"],
        "optional": []
    },
    "enemy_defeat": {
        "required": ["event_type", "ts", "session", "round", "enemy_id", "enemy_name", "defeat_reason", "rounds_survived"],
        "optional": []
    },
    "round_summary": {
        "required": ["event_type", "ts", "session", "round", "actions_attempted", "success_count", "success_rate", "average_margin"],
        "optional": ["damage_dealt_by_players", "damage_taken_by_players", "void_gained", "void_lost", "clocks_advanced", "clocks_filled", "active_enemies", "player_wounds_total"]
    },
    "clock_advancement": {
        "required": ["event_type", "ts", "session", "round", "clock_name", "old_value", "new_value", "maximum", "filled", "reason"],
        "optional": []
    },
    "void_change": {
        "required": ["event_type", "ts", "session", "round", "agent", "old_void", "new_void", "delta", "reason"],
        "optional": ["capped"]
    }
}


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_event(event: Dict[str, Any], line_num: int) -> List[str]:
    """
    Validate a single event against its schema.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check event_type exists
    if "event_type" not in event:
        errors.append(f"Line {line_num}: Missing 'event_type' field")
        return errors

    event_type = event["event_type"]

    # Check if event type is known
    if event_type not in EVENT_SCHEMAS:
        # Generic events are allowed but noted
        if event_type not in ["action_declaration", "adjudication_start", "declaration_phase_start", "clock_spawn", "round_synthesis", "mission_debrief", "session_end"]:
            errors.append(f"Line {line_num}: Unknown event_type '{event_type}' (may be legacy or generic)")
        return errors

    schema = EVENT_SCHEMAS[event_type]

    # Check required fields
    for field in schema["required"]:
        if field not in event:
            errors.append(f"Line {line_num}: Event '{event_type}' missing required field '{field}'")

    # Validate specific field types for new events
    if event_type == "combat_action":
        # Validate attack roll structure
        if "attack" in event:
            attack = event["attack"]
            required_attack_fields = ["attr", "attr_val", "skill", "skill_val", "d20", "total", "dc", "hit", "margin"]
            for field in required_attack_fields:
                if field not in attack:
                    errors.append(f"Line {line_num}: combat_action.attack missing field '{field}'")

        # Validate damage roll structure (if present)
        if "damage" in event and event["damage"] is not None:
            damage = event["damage"]
            required_damage_fields = ["strength", "weapon_dmg", "d20", "total", "soak", "dealt"]
            for field in required_damage_fields:
                if field not in damage:
                    errors.append(f"Line {line_num}: combat_action.damage missing field '{field}'")

    elif event_type == "character_state":
        # Validate numeric fields
        for field in ["health", "max_health", "wounds", "void_score", "soulcredit"]:
            if field in event and not isinstance(event[field], (int, float)):
                errors.append(f"Line {line_num}: character_state.{field} should be numeric, got {type(event[field])}")

    elif event_type == "enemy_spawn":
        # Validate stats structure
        if "stats" in event:
            stats = event["stats"]
            required_stats_fields = ["health", "max_health", "soak", "attributes", "skills"]
            for field in required_stats_fields:
                if field not in stats:
                    errors.append(f"Line {line_num}: enemy_spawn.stats missing field '{field}'")

    return errors


def analyze_log_file(log_file_path: Path) -> Dict[str, Any]:
    """
    Analyze a JSONL log file and return statistics and validation results.

    Returns:
        Dictionary with analysis results
    """
    results = {
        "file": str(log_file_path),
        "total_events": 0,
        "valid_events": 0,
        "invalid_events": 0,
        "event_type_counts": Counter(),
        "errors": [],
        "warnings": [],
        "rounds": set(),
        "characters": set(),
        "enemies_spawned": set(),
        "enemies_defeated": set(),
        "combat_actions": 0,
        "character_state_snapshots": 0
    }

    try:
        with open(log_file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    results["total_events"] += 1

                    # Validate event
                    errors = validate_event(event, line_num)
                    if errors:
                        results["invalid_events"] += 1
                        results["errors"].extend(errors)
                    else:
                        results["valid_events"] += 1

                    # Count event types
                    event_type = event.get("event_type", "unknown")
                    results["event_type_counts"][event_type] += 1

                    # Track rounds
                    if "round" in event:
                        results["rounds"].add(event["round"])

                    # Track specific events
                    if event_type == "combat_action":
                        results["combat_actions"] += 1
                        results["characters"].add(event.get("attacker", {}).get("name", "unknown"))
                        results["characters"].add(event.get("defender", {}).get("name", "unknown"))

                    elif event_type == "character_state":
                        results["character_state_snapshots"] += 1
                        results["characters"].add(event.get("character_name", "unknown"))

                    elif event_type == "enemy_spawn":
                        results["enemies_spawned"].add(event.get("enemy_name", "unknown"))

                    elif event_type == "enemy_defeat":
                        results["enemies_defeated"].add(event.get("enemy_name", "unknown"))

                except json.JSONDecodeError as e:
                    results["invalid_events"] += 1
                    results["errors"].append(f"Line {line_num}: JSON parse error: {e}")

    except FileNotFoundError:
        results["errors"].append(f"File not found: {log_file_path}")
        return results

    # Generate warnings
    if results["combat_actions"] == 0 and "enemy_spawn" in results["event_type_counts"]:
        results["warnings"].append("Enemies spawned but no combat_action events found (combat logging may not be working)")

    if len(results["rounds"]) > 0 and results["character_state_snapshots"] < len(results["rounds"]):
        results["warnings"].append(f"Only {results["character_state_snapshots"]} character state snapshots for {len(results['rounds'])} rounds (should have one per character per round)")

    return results


def print_analysis_report(results: Dict[str, Any]):
    """Print a formatted analysis report."""
    print("\n" + "=" * 80)
    print("JSONL LOG VALIDATION REPORT")
    print("=" * 80)
    print(f"\nFile: {results['file']}")
    print(f"Total Events: {results['total_events']}")
    print(f"Valid Events: {results['valid_events']} ({results['valid_events']/results['total_events']*100 if results['total_events'] > 0 else 0:.1f}%)")
    print(f"Invalid Events: {results['invalid_events']}")

    print("\n--- Event Type Distribution ---")
    for event_type, count in results["event_type_counts"].most_common():
        print(f"  {event_type:30s}: {count:4d}")

    print(f"\n--- Session Statistics ---")
    print(f"Rounds: {len(results['rounds'])}")
    print(f"Characters: {len(results['characters'])}")
    print(f"Combat Actions Logged: {results['combat_actions']}")
    print(f"Character State Snapshots: {results['character_state_snapshots']}")
    print(f"Enemies Spawned: {len(results['enemies_spawned'])}")
    print(f"Enemies Defeated: {len(results['enemies_defeated'])}")

    if results["errors"]:
        print(f"\n--- Validation Errors ({len(results['errors'])}) ---")
        for error in results["errors"][:20]:  # Limit to first 20
            print(f"  ❌ {error}")
        if len(results["errors"]) > 20:
            print(f"  ... and {len(results['errors']) - 20} more errors")

    if results["warnings"]:
        print(f"\n--- Warnings ({len(results['warnings'])}) ---")
        for warning in results["warnings"]:
            print(f"  ⚠️  {warning}")

    print("\n" + "=" * 80)

    # Return status code
    if results["errors"]:
        print("\n❌ VALIDATION FAILED")
        return 1
    elif results["warnings"]:
        print("\n⚠️  VALIDATION PASSED WITH WARNINGS")
        return 0
    else:
        print("\n✅ VALIDATION PASSED")
        return 0


def main():
    """Main validation script."""
    if len(sys.argv) < 2:
        print("Usage: python validate_logging.py <path_to_jsonl_file>")
        print("   or: python validate_logging.py <directory>  (validates all .jsonl files)")
        sys.exit(1)

    path = Path(sys.argv[1])

    if path.is_file():
        results = analyze_log_file(path)
        exit_code = print_analysis_report(results)
        sys.exit(exit_code)

    elif path.is_dir():
        print(f"Validating all JSONL files in {path}...")
        jsonl_files = list(path.glob("*.jsonl"))

        if not jsonl_files:
            print(f"No .jsonl files found in {path}")
            sys.exit(1)

        print(f"Found {len(jsonl_files)} files\n")

        all_results = []
        for jsonl_file in sorted(jsonl_files):
            print(f"\nAnalyzing: {jsonl_file.name}")
            results = analyze_log_file(jsonl_file)
            all_results.append(results)

            # Print brief summary
            print(f"  Events: {results['total_events']}, Valid: {results['valid_events']}, Errors: {len(results['errors'])}, Warnings: {len(results['warnings'])}")

        # Print aggregate summary
        print("\n" + "=" * 80)
        print("AGGREGATE SUMMARY")
        print("=" * 80)
        total_events = sum(r["total_events"] for r in all_results)
        total_valid = sum(r["valid_events"] for r in all_results)
        total_errors = sum(len(r["errors"]) for r in all_results)
        total_warnings = sum(len(r["warnings"]) for r in all_results)

        print(f"Files Analyzed: {len(all_results)}")
        print(f"Total Events: {total_events}")
        print(f"Total Valid: {total_valid} ({total_valid/total_events*100 if total_events > 0 else 0:.1f}%)")
        print(f"Total Errors: {total_errors}")
        print(f"Total Warnings: {total_warnings}")

        if total_errors > 0:
            print("\n❌ VALIDATION FAILED")
            sys.exit(1)
        elif total_warnings > 0:
            print("\n⚠️  VALIDATION PASSED WITH WARNINGS")
            sys.exit(0)
        else:
            print("\n✅ ALL FILES VALID")
            sys.exit(0)

    else:
        print(f"Error: {path} is not a file or directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
