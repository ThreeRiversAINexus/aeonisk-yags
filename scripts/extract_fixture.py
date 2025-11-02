#!/usr/bin/env python3
"""
Extract fixture from production session JSONL files.

Extracts a round range from a session log, including all dependencies
(session_start, llm_calls, enemy_spawns) to create a self-contained
fixture for testing.

Usage:
    python scripts/extract_fixture.py \\
        multiagent_output/session_bug.jsonl \\
        --rounds 0-3 \\
        --output tests/fixtures/sessions/bug_baseline.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


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


def write_jsonl(events: List[Dict], path: Path, overwrite: bool = False):
    """Write events to JSONL file."""
    if path.exists() and not overwrite:
        print(f"Error: Output file {path} already exists. Use --overwrite to replace.", file=sys.stderr)
        sys.exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')


def parse_round_range(round_spec: str) -> Tuple[int, Optional[int]]:
    """
    Parse round specification into (start, end) tuple.

    Examples:
        "0-3" -> (0, 3)
        "2-5" -> (2, 5)
        "all" -> (0, None)
    """
    if round_spec.lower() == "all":
        return (0, None)

    if '-' not in round_spec:
        # Single round: "3" -> (3, 3)
        round_num = int(round_spec)
        return (round_num, round_num)

    start_str, end_str = round_spec.split('-', 1)
    start = int(start_str)
    end = int(end_str) if end_str else None

    return (start, end)


def extract_fixture(events: List[Dict], start_round: int, end_round: Optional[int]) -> List[Dict]:
    """
    Extract events for specified round range, including all dependencies.

    Always includes:
    - session_start event (config, random_seed)
    - scenario event
    - All events from rounds [start_round, end_round]
    - All llm_call events for included rounds (including declaration LLM calls with round=null)
    - All enemy_spawn events up through end_round
    """
    fixture_events = []
    seen_event_types = set()
    included_rounds = set()

    # First pass: identify all rounds we're including and collect agent IDs that act in those rounds
    agents_in_included_rounds = set()
    for event in events:
        event_type = event.get("event_type")
        round_num = event.get("round")

        if round_num is not None:
            if round_num >= start_round and (end_round is None or round_num <= end_round):
                included_rounds.add(round_num)

                # Track agents that declare actions in included rounds
                if event_type == "action_declaration":
                    # Extract agent ID from declaration
                    action = event.get("action", {})
                    agent_id = action.get("agent_id")
                    if agent_id:
                        agents_in_included_rounds.add(agent_id)

    # Second pass: collect events
    for i, event in enumerate(events):
        event_type = event.get("event_type")
        round_num = event.get("round")

        # Always include session_start and scenario
        if event_type in ("session_start", "scenario"):
            fixture_events.append(event)
            seen_event_types.add(event_type)
            continue

        # Include events from selected rounds
        if round_num is not None and round_num in included_rounds:
            fixture_events.append(event)
            seen_event_types.add(event_type)
            continue

        # Include llm_call events for selected rounds
        # This includes both:
        # 1. LLM calls with round number set (DM adjudication calls)
        # 2. LLM calls with round=null that are followed by action_declaration for included rounds
        if event_type == "llm_call":
            # Check if round is in included rounds
            if round_num in included_rounds:
                fixture_events.append(event)
                continue

            # Check if this is a declaration LLM call (round=null) followed by action_declaration in included rounds
            if round_num is None and i + 1 < len(events):
                next_event = events[i + 1]
                if next_event.get("event_type") == "action_declaration":
                    decl_round = next_event.get("round")
                    if decl_round in included_rounds:
                        fixture_events.append(event)
                        continue

        # Include enemy_spawn events up through end_round
        if event_type == "enemy_spawn":
            if round_num is None or round_num in included_rounds:
                fixture_events.append(event)
                continue

    return fixture_events


def validate_fixture(events: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Validate that extracted fixture is complete and replayable.

    Returns:
        (is_valid, warnings) tuple
    """
    warnings = []
    has_session_start = False
    has_scenario = False
    has_random_seed = False
    rounds_seen = set()
    event_types_seen = set()

    for event in events:
        event_type = event.get("event_type")
        event_types_seen.add(event_type)

        if event_type == "session_start":
            has_session_start = True
            if "random_seed" in event:
                has_random_seed = True
            else:
                warnings.append("session_start event missing random_seed")

        if event_type == "scenario":
            has_scenario = True

        if "round" in event and event["round"] is not None:
            rounds_seen.add(event["round"])

    # Check required events
    if not has_session_start:
        warnings.append("Missing session_start event (CRITICAL)")
        return (False, warnings)

    if not has_scenario:
        warnings.append("Missing scenario event (recommended)")

    if not has_random_seed:
        warnings.append("Missing random_seed in session_start (replay will not be deterministic)")

    # Check for round completeness
    if rounds_seen:
        min_round = min(rounds_seen)
        max_round = max(rounds_seen)

        # Check if we have round_start for each round
        round_starts = set()
        for event in events:
            if event.get("event_type") == "round_start":
                round_starts.add(event["round"])

        missing_round_starts = rounds_seen - round_starts
        if missing_round_starts:
            warnings.append(f"Missing round_start events for rounds: {sorted(missing_round_starts)}")

        # Check for gaps in round sequence
        expected_rounds = set(range(min_round, max_round + 1))
        missing_rounds = expected_rounds - rounds_seen
        if missing_rounds:
            warnings.append(f"Gap in round sequence, missing rounds: {sorted(missing_rounds)}")

    # Check for LLM calls
    has_llm_calls = "llm_call" in event_types_seen
    if not has_llm_calls:
        warnings.append("No llm_call events found (replay will require live LLM calls)")

    is_valid = has_session_start and has_random_seed
    return (is_valid, warnings)


def print_fixture_summary(events: List[Dict], rounds_extracted: Set[int]):
    """Print summary of extracted fixture."""
    event_counts = {}
    characters = set()
    enemies = set()
    random_seed = None
    git_commit = None

    for event in events:
        event_type = event.get("event_type")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

        if event_type == "session_start":
            random_seed = event.get("random_seed")
            git_commit = event.get("git_commit")
            # Extract character names from config
            config = event.get("config", {})
            agents = config.get("agents", {})
            players = agents.get("players", [])
            for player in players:
                characters.add(player.get("name", "Unknown"))

        if event_type == "enemy_spawn":
            enemy_id = event.get("enemy_id")
            if enemy_id:
                enemies.add(enemy_id)

        if event_type == "action_declaration":
            char_name = event.get("character_name")
            if char_name:
                characters.add(char_name)

    print("\nFixture Summary:")
    print(f"  Rounds: {sorted([r for r in rounds_extracted if r is not None])}")
    print(f"  Total events: {len(events)}")
    print(f"  Characters: {len(characters)} ({', '.join(sorted(characters))})")
    print(f"  Enemies: {len(enemies)}")
    if random_seed:
        print(f"  Random seed: {random_seed}")
    if git_commit:
        print(f"  Git commit: {git_commit}")

    print("\n  Event type breakdown:")
    for event_type in sorted(event_counts.keys()):
        print(f"    {event_type}: {event_counts[event_type]}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract fixture from production session JSONL files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract rounds 0-3 from session
  python scripts/extract_fixture.py \\
      multiagent_output/session_bug.jsonl \\
      --rounds 0-3 \\
      --output tests/fixtures/sessions/bug_baseline.jsonl

  # Extract single round
  python scripts/extract_fixture.py \\
      multiagent_output/session.jsonl \\
      --rounds 2 \\
      --output tests/fixtures/sessions/round2.jsonl

  # Extract all rounds (entire session)
  python scripts/extract_fixture.py \\
      multiagent_output/session.jsonl \\
      --rounds all \\
      --output tests/fixtures/sessions/full_session.jsonl

  # Validate only (don't write output)
  python scripts/extract_fixture.py \\
      multiagent_output/session.jsonl \\
      --rounds 0-3 \\
      --validate-only
        """
    )

    parser.add_argument(
        "input_jsonl",
        type=Path,
        help="Source JSONL session log file"
    )

    parser.add_argument(
        "--rounds",
        type=str,
        required=True,
        help="Round range to extract (e.g., '0-3', '2', 'all')"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output fixture path (required unless --validate-only)"
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file"
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Check extractability without writing output"
    )

    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Description of this fixture (for documentation)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.validate_only and not args.output:
        parser.error("--output is required unless --validate-only is specified")

    if not args.input_jsonl.exists():
        print(f"Error: Input file {args.input_jsonl} does not exist", file=sys.stderr)
        sys.exit(1)

    # Parse round range
    try:
        start_round, end_round = parse_round_range(args.rounds)
    except ValueError as e:
        print(f"Error: Invalid round specification '{args.rounds}': {e}", file=sys.stderr)
        sys.exit(1)

    # Load source session
    print(f"Loading source session: {args.input_jsonl}")
    events = load_jsonl(args.input_jsonl)
    print(f"Loaded {len(events)} events")

    # Extract fixture
    round_desc = f"{start_round}-{end_round}" if end_round is not None else f"{start_round}+"
    print(f"\nExtracting rounds {round_desc}...")

    fixture_events = extract_fixture(events, start_round, end_round)

    # Determine which rounds were actually included
    included_rounds = set()
    for event in fixture_events:
        if "round" in event:
            included_rounds.add(event["round"])

    print(f"Extracted {len(fixture_events)} events")

    # Validate fixture
    print("\nValidating fixture...")
    is_valid, warnings = validate_fixture(fixture_events)

    if warnings:
        print("\nValidation warnings:")
        for warning in warnings:
            print(f"  ⚠ {warning}")

    if not is_valid:
        print("\n✗ Fixture is NOT valid for replay", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n✓ Fixture is valid for replay")

    # Print summary
    print_fixture_summary(fixture_events, included_rounds)

    # Write output (unless validate-only)
    if not args.validate_only:
        print(f"\nWriting fixture to: {args.output}")
        write_jsonl(fixture_events, args.output, overwrite=args.overwrite)

        # Calculate file size
        file_size = args.output.stat().st_size
        size_kb = file_size / 1024
        print(f"✓ Fixture saved ({size_kb:.1f} KB)")

        if args.description:
            print(f"\nDescription: {args.description}")
            print("(Note: Description not embedded in fixture. Add to fixture catalog manually.)")
    else:
        print("\n(Validate-only mode: No output written)")


if __name__ == "__main__":
    main()
