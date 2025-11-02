#!/usr/bin/env python3
"""
Compare two fixture JSONL files and highlight mechanical differences.

Compares before/after fixtures (e.g., before and after a bug fix) and
shows what changed in mechanical terms (damage, void, rolls, etc.),
ignoring narrative differences in DM narration.

Usage:
    python scripts/diff_fixtures.py \\
        tests/fixtures/sessions/before.jsonl \\
        tests/fixtures/sessions/after.jsonl \\
        --focus effects.void_changes
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict


def load_jsonl(path: Path) -> List[Dict]:
    """Load JSONL file into list of event dictionaries."""
    events = []
    with open(path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON at line {line_num}: {e}", file=sys.stderr)
    return events


def get_nested_value(obj: Dict, path: str) -> Any:
    """
    Get nested value from dict using dot notation.

    Example:
        get_nested_value({"roll": {"success": True}}, "roll.success") -> True
    """
    keys = path.split('.')
    current = obj

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None

    return current


def align_events(before: List[Dict], after: List[Dict]) -> List[Tuple[Optional[Dict], Optional[Dict]]]:
    """
    Align events from before and after fixtures for comparison.

    Aligns by (event_type, round, agent/character_name) where applicable.

    Returns:
        List of (before_event, after_event) tuples
    """
    # Group events by alignment key
    def get_alignment_key(event: Dict) -> Optional[str]:
        """Generate alignment key for event."""
        event_type = event.get("event_type")
        round_num = event.get("round")

        # Events without rounds (session_start, scenario) align by type only
        if round_num is None:
            return f"{event_type}"

        # Events with agent/character identification
        agent = event.get("agent")
        character_name = event.get("character_name")

        if agent:
            return f"{event_type}:r{round_num}:{agent}"
        elif character_name:
            return f"{event_type}:r{round_num}:{character_name}"
        else:
            # Events without agent (round_start, round_summary, etc.)
            return f"{event_type}:r{round_num}"

    # Build alignment dictionaries
    before_by_key = defaultdict(list)
    after_by_key = defaultdict(list)

    for event in before:
        key = get_alignment_key(event)
        if key:
            before_by_key[key].append(event)

    for event in after:
        key = get_alignment_key(event)
        if key:
            after_by_key[key].append(event)

    # Align events
    aligned = []
    all_keys = sorted(set(before_by_key.keys()) | set(after_by_key.keys()))

    for key in all_keys:
        before_events = before_by_key.get(key, [])
        after_events = after_by_key.get(key, [])

        # Handle multiple events with same key (zip with None padding)
        max_len = max(len(before_events), len(after_events))
        for i in range(max_len):
            b = before_events[i] if i < len(before_events) else None
            a = after_events[i] if i < len(after_events) else None
            aligned.append((b, a))

    return aligned


def compare_values(before_val: Any, after_val: Any) -> bool:
    """
    Compare two values, returning True if different.

    Handles special cases like floats with tolerance.
    """
    # Both None -> same
    if before_val is None and after_val is None:
        return False

    # One None, one not -> different
    if before_val is None or after_val is None:
        return True

    # Numeric comparison with small tolerance
    if isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
        return abs(before_val - after_val) > 0.0001

    # Direct comparison for other types
    return before_val != after_val


def format_value(val: Any) -> str:
    """Format value for display."""
    if val is None:
        return "null"
    if isinstance(val, str):
        # Truncate long strings
        if len(val) > 60:
            return f'"{val[:57]}..."'
        return f'"{val}"'
    if isinstance(val, dict):
        return json.dumps(val)
    if isinstance(val, list):
        return json.dumps(val)
    return str(val)


def diff_fixtures(
    before_events: List[Dict],
    after_events: List[Dict],
    focus_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare before and after fixtures.

    Args:
        before_events: Events from before fixture
        after_events: Events from after fixture
        focus_fields: List of field paths to focus on (None = all mechanical fields)

    Returns:
        Diff summary dict
    """
    # Default mechanical fields to compare if not specified
    if focus_fields is None:
        focus_fields = [
            # Roll fields
            "roll.success",
            "roll.total",
            "roll.margin",
            "roll.tier",

            # Effect fields
            "effects.damage.dealt",
            "effects.damage.target",
            "effects.void_changes",
            "effects.soulcredit_changes",
            "effects.clock_updates",
            "effects.conditions",

            # Character state fields
            "health",
            "void_score",
            "soulcredit",
            "wounds",
            "is_defeated",

            # Combat fields
            "attack.hit",
            "attack.damage",
            "defender_state_after.health"
        ]

    differences = []
    total_events_compared = 0
    events_with_differences = 0

    # Align events for comparison
    aligned = align_events(before_events, after_events)

    for before_event, after_event in aligned:
        # Skip if both missing (shouldn't happen with alignment, but safety check)
        if before_event is None and after_event is None:
            continue

        # Handle events only in before or only in after
        if before_event is None:
            event_type = after_event.get("event_type")
            round_num = after_event.get("round", "?")
            differences.append({
                'type': 'added',
                'event_type': event_type,
                'round': round_num,
                'description': f"Event added in 'after': {event_type} (round {round_num})"
            })
            events_with_differences += 1
            continue

        if after_event is None:
            event_type = before_event.get("event_type")
            round_num = before_event.get("round", "?")
            differences.append({
                'type': 'removed',
                'event_type': event_type,
                'round': round_num,
                'description': f"Event removed in 'after': {event_type} (round {round_num})"
            })
            events_with_differences += 1
            continue

        # Both events present - compare fields
        total_events_compared += 1
        event_type = before_event.get("event_type")
        round_num = before_event.get("round", "?")
        agent = before_event.get("agent") or before_event.get("character_name", "?")

        event_diffs = []

        for field_path in focus_fields:
            before_val = get_nested_value(before_event, field_path)
            after_val = get_nested_value(after_event, field_path)

            # Skip if both missing (field not applicable to this event type)
            if before_val is None and after_val is None:
                continue

            # Check if different
            if compare_values(before_val, after_val):
                event_diffs.append({
                    'field': field_path,
                    'before': before_val,
                    'after': after_val
                })

        if event_diffs:
            events_with_differences += 1
            differences.append({
                'type': 'changed',
                'event_type': event_type,
                'round': round_num,
                'agent': agent,
                'field_changes': event_diffs
            })

    return {
        'total_events_compared': total_events_compared,
        'events_with_differences': events_with_differences,
        'differences': differences,
        'focus_fields': focus_fields
    }


def print_diff_report(diff_result: Dict[str, Any], verbose: bool = False):
    """Print human-readable diff report."""
    total = diff_result['total_events_compared']
    different = diff_result['events_with_differences']
    differences = diff_result['differences']

    print("\n=== Fixture Comparison Report ===\n")
    print(f"Total events compared: {total}")
    print(f"Events with differences: {different}")

    if different == 0:
        print("\n✅ Fixtures are identical (in mechanical fields)")
        return

    print(f"\nFocus fields: {', '.join(diff_result['focus_fields'])}")

    # Group by type
    added = [d for d in differences if d['type'] == 'added']
    removed = [d for d in differences if d['type'] == 'removed']
    changed = [d for d in differences if d['type'] == 'changed']

    if added:
        print(f"\n📥 Added events ({len(added)}):")
        for diff in added:
            print(f"  Round {diff['round']}: {diff['event_type']}")

    if removed:
        print(f"\n📤 Removed events ({len(removed)}):")
        for diff in removed:
            print(f"  Round {diff['round']}: {diff['event_type']}")

    if changed:
        print(f"\n🔄 Changed events ({len(changed)}):")
        for diff in changed:
            round_num = diff['round']
            agent = diff['agent']
            event_type = diff['event_type']

            print(f"\n  Round {round_num}, {agent} ({event_type}):")

            for field_change in diff['field_changes']:
                field = field_change['field']
                before_val = format_value(field_change['before'])
                after_val = format_value(field_change['after'])

                print(f"    {field}:")
                print(f"      BEFORE: {before_val}")
                print(f"      AFTER:  {after_val}")

    # Summary of changes by field
    print("\n=== Summary by Field ===\n")
    field_change_counts = defaultdict(int)

    for diff in changed:
        for field_change in diff['field_changes']:
            field_change_counts[field_change['field']] += 1

    for field, count in sorted(field_change_counts.items(), key=lambda x: -x[1]):
        print(f"  {field}: {count} changes")


def main():
    parser = argparse.ArgumentParser(
        description="Compare two fixture JSONL files and highlight mechanical differences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare all mechanical fields
  python scripts/diff_fixtures.py \\
      tests/fixtures/sessions/before.jsonl \\
      tests/fixtures/sessions/after.jsonl

  # Focus on void changes only
  python scripts/diff_fixtures.py \\
      tests/fixtures/sessions/before.jsonl \\
      tests/fixtures/sessions/after.jsonl \\
      --focus effects.void_changes

  # Focus on multiple fields
  python scripts/diff_fixtures.py \\
      tests/fixtures/sessions/before.jsonl \\
      tests/fixtures/sessions/after.jsonl \\
      --focus effects.damage.dealt effects.void_changes roll.success

  # JSON output for scripting
  python scripts/diff_fixtures.py \\
      tests/fixtures/sessions/before.jsonl \\
      tests/fixtures/sessions/after.jsonl \\
      --json
        """
    )

    parser.add_argument(
        "before",
        type=Path,
        help="Before fixture JSONL file"
    )

    parser.add_argument(
        "after",
        type=Path,
        help="After fixture JSONL file"
    )

    parser.add_argument(
        "--focus",
        nargs="+",
        help="Focus on specific field paths (e.g., 'effects.void_changes')"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable report"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all details (not yet implemented)"
    )

    args = parser.parse_args()

    # Validate input files
    if not args.before.exists():
        print(f"Error: Before fixture {args.before} does not exist", file=sys.stderr)
        sys.exit(1)

    if not args.after.exists():
        print(f"Error: After fixture {args.after} does not exist", file=sys.stderr)
        sys.exit(1)

    # Load fixtures
    print(f"Loading before fixture: {args.before}")
    before_events = load_jsonl(args.before)
    print(f"  Loaded {len(before_events)} events")

    print(f"Loading after fixture: {args.after}")
    after_events = load_jsonl(args.after)
    print(f"  Loaded {len(after_events)} events")

    # Compare
    diff_result = diff_fixtures(before_events, after_events, focus_fields=args.focus)

    # Output
    if args.json:
        print(json.dumps(diff_result, indent=2))
    else:
        print_diff_report(diff_result, verbose=args.verbose)

    # Exit code: 0 if identical, 1 if differences found
    if diff_result['events_with_differences'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
