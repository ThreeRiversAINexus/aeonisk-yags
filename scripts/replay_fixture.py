#!/usr/bin/env python3
"""
Replay fixture with selective LLM caching.

Replays a fixture scenario with NEW code, using selective LLM caching
to control which agents use cached responses vs live LLM calls.

Primary use case: Verify code fixes by replaying buggy sessions with
player actions cached (same behavior) but DM using live LLM (tests new mechanics).

Usage:
    # Replay with all caching (should match original exactly)
    python scripts/replay_fixture.py \\
        tests/fixtures/sessions/bug_baseline.jsonl \\
        --all-cached \\
        --output tests/fixtures/sessions/replay_check.jsonl

    # Replay with live DM (tests code fixes)
    python scripts/replay_fixture.py \\
        tests/fixtures/sessions/bug_baseline.jsonl \\
        --cache-player-actions \\
        --live-dm-resolutions \\
        --output tests/fixtures/sessions/bug_after_fix.jsonl
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Load environment variables (.env file)
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from aeonisk.multiagent.replay import ReplaySession


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


def extract_cache_for_agents(
    events: List[Dict],
    agent_ids: Optional[Set[str]] = None
) -> Dict[Tuple[str, int], Dict]:
    """
    Extract LLM cache for specific agents only.

    Args:
        events: List of events from fixture
        agent_ids: Set of agent IDs to include in cache (None = all agents)

    Returns:
        LLM cache dict: (agent_id, call_sequence) -> response dict
    """
    cache = {}

    for event in events:
        if event.get("event_type") != "llm_call":
            continue

        agent_id = event.get("agent_id")
        call_seq = event.get("call_sequence")

        # Filter by agent if specified
        if agent_ids is not None and agent_id not in agent_ids:
            continue

        cache_key = (agent_id, call_seq)
        cache[cache_key] = {
            'prompt': event['prompt'],
            'response': event['response'],
            'model': event['model'],
            'temperature': event['temperature'],
            'tokens': event.get('tokens', {})
        }

    return cache


def identify_player_agent_ids(events: List[Dict]) -> Set[str]:
    """
    Identify all player agent IDs from fixture events.

    Looks for:
    - action_declaration events with agent IDs
    - llm_call events from player agents (agent_id pattern: "player_*")

    Returns:
        Set of player agent IDs
    """
    player_ids = set()

    for event in events:
        # From action declarations
        if event.get("event_type") == "action_declaration":
            agent_id = event.get("action", {}).get("agent_id")
            if agent_id:
                player_ids.add(agent_id)

        # From LLM calls (pattern matching)
        if event.get("event_type") == "llm_call":
            agent_id = event.get("agent_id")
            if agent_id and agent_id.startswith("player_"):
                player_ids.add(agent_id)

    return player_ids


def identify_enemy_agent_ids(events: List[Dict]) -> Set[str]:
    """
    Identify all enemy agent IDs from fixture events.

    Looks for llm_call events from enemy agents (agent_id pattern: "enemy_agent_*")

    Returns:
        Set of enemy agent IDs
    """
    enemy_ids = set()

    for event in events:
        if event.get("event_type") == "llm_call":
            agent_id = event.get("agent_id")
            if agent_id and agent_id.startswith("enemy_agent_"):
                enemy_ids.add(agent_id)

    return enemy_ids


async def replay_fixture(
    fixture_path: Path,
    output_path: Optional[Path] = None,
    cache_mode: str = "all",
    max_rounds: Optional[int] = None,
    cache_until_round: Optional[int] = None,
    start_from_round: int = 0
):
    """
    Replay a fixture with selective LLM caching.

    Args:
        fixture_path: Path to fixture JSONL file
        output_path: Path for output JSONL (None = stdout summary only)
        cache_mode: "all", "players-only", "none"
        max_rounds: Limit replay to N rounds (None = all rounds in fixture)
        cache_until_round: Cache all agents until round N, then go live (None = disabled)
        start_from_round: Skip rounds 0 to N-1, start replay from round N (default: 0)

    Returns:
        Replay result dict
    """
    print(f"Loading fixture: {fixture_path}")
    events = load_jsonl(fixture_path)
    print(f"Loaded {len(events)} events")

    # Extract session metadata
    session_start = next((e for e in events if e.get("event_type") == "session_start"), None)
    if not session_start:
        print("Error: Fixture missing session_start event", file=sys.stderr)
        sys.exit(1)

    config = session_start.get("config", {})
    random_seed = session_start.get("random_seed")
    git_commit = session_start.get("git_commit")

    print(f"  Session config: {config.get('session_name', 'unnamed')}")
    print(f"  Random seed: {random_seed}")
    print(f"  Git commit: {git_commit}")

    # Determine which agents to cache
    player_ids = identify_player_agent_ids(events)
    enemy_ids = identify_enemy_agent_ids(events)

    print(f"\n  Player agents: {len(player_ids)}")
    print(f"  Enemy agents: {len(enemy_ids)}")

    if cache_mode == "all":
        cached_agents = None  # None = cache all
        print(f"\nCache mode: ALL agents cached (deterministic replay)")
    elif cache_mode == "players-only":
        cached_agents = player_ids | enemy_ids  # Cache players AND enemies, only DM will be live
        print(f"\nCache mode: Player + Enemy actions cached, DM uses LIVE LLM")
        print(f"  Cached agents: {len(cached_agents)} total")
    elif cache_mode == "none":
        cached_agents = set()  # Empty set = cache nothing
        print(f"\nCache mode: NO caching, all agents use LIVE LLM")
    else:
        print(f"Error: Unknown cache mode '{cache_mode}'", file=sys.stderr)
        sys.exit(1)

    # Extract LLM cache
    llm_cache = extract_cache_for_agents(events, cached_agents)
    total_cached_calls = len(llm_cache)

    # Count total LLM calls in fixture for comparison
    total_llm_calls = sum(1 for e in events if e.get("event_type") == "llm_call")

    print(f"  LLM calls in fixture: {total_llm_calls}")
    print(f"  LLM calls cached: {total_cached_calls}")
    print(f"  LLM calls that will be LIVE: {total_llm_calls - total_cached_calls}")

    # Create a temporary output directory for the replay
    import tempfile
    import uuid

    temp_dir = Path(tempfile.gettempdir())
    replay_session_id = str(uuid.uuid4())[:8]

    # Modify config for replay
    config = config.copy()
    config['output_dir'] = str(temp_dir)
    config['session_name'] = f"replay_{replay_session_id}"
    if max_rounds:
        config['max_turns'] = max_rounds

    print(f"\n=== Starting Replay ===")
    print(f"Replay rounds: {max_rounds if max_rounds else 'all'}")

    # Use existing ReplaySession infrastructure
    replay = ReplaySession(
        log_path=str(fixture_path),
        replay_to_round=max_rounds if max_rounds else 999,
        continue_from_round=cache_until_round,  # Hybrid mode: cache until round N, then live
        start_from_round=start_from_round  # Skip early rounds
    )
    replay.load_log()

    # Replace LLM cache with filtered version
    replay.llm_cache = llm_cache
    replay.config = config

    try:
        # Run the replay
        result = await replay.replay()

        print("\n✅ Replay completed successfully!")

        # If output path specified, find and move the generated log
        if output_path:
            # Find the generated JSONL file
            generated_log = temp_dir / f"session_{replay_session_id}.jsonl"

            # Session might generate with different naming, search for it
            if not generated_log.exists():
                # Look for any session file created recently in temp dir
                possible_files = list(temp_dir.glob("session_*.jsonl"))
                if possible_files:
                    # Sort by modification time, take most recent
                    possible_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    generated_log = possible_files[0]

            if generated_log.exists():
                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy(str(generated_log), str(output_path))
                print(f"\n✓ Output saved to: {output_path}")

                # Calculate file size
                file_size = output_path.stat().st_size
                size_kb = file_size / 1024
                print(f"  File size: {size_kb:.1f} KB")

                # Clean up temp file
                generated_log.unlink()
            else:
                print(f"\nWarning: Could not find generated replay log", file=sys.stderr)
                print(f"  Looked in: {temp_dir}", file=sys.stderr)

        return {
            'status': 'success',
            'random_seed': random_seed,
            'llm_calls_cached': total_cached_calls,
            'llm_calls_live': total_llm_calls - total_cached_calls,
            'rounds_replayed': max_rounds if max_rounds else 'all'
        }

    except Exception as e:
        print(f"\n❌ Replay failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'error': str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description="Replay fixture with selective LLM caching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replay with all caching (verify deterministic replay)
  python scripts/replay_fixture.py \\
      tests/fixtures/sessions/bug_baseline.jsonl \\
      --all-cached \\
      --output /tmp/replay_check.jsonl

  # Replay with live DM (test code fixes)
  python scripts/replay_fixture.py \\
      tests/fixtures/sessions/bug_baseline.jsonl \\
      --cache-player-actions \\
      --output tests/fixtures/sessions/bug_after_fix.jsonl

  # Replay with no caching (all live LLM calls)
  python scripts/replay_fixture.py \\
      tests/fixtures/sessions/baseline.jsonl \\
      --no-cache \\
      --output tests/fixtures/sessions/all_live.jsonl

  # Limit to first 3 rounds
  python scripts/replay_fixture.py \\
      tests/fixtures/sessions/baseline.jsonl \\
      --cache-player-actions \\
      --max-rounds 3 \\
      --output tests/fixtures/sessions/rounds_0_3.jsonl
        """
    )

    parser.add_argument(
        "fixture",
        type=Path,
        help="Fixture JSONL file to replay"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for replay results (JSONL)"
    )

    # Cache mode flags (mutually exclusive)
    cache_group = parser.add_mutually_exclusive_group(required=True)
    cache_group.add_argument(
        "--all-cached",
        action="store_const",
        const="all",
        dest="cache_mode",
        help="Cache all agents (deterministic replay)"
    )
    cache_group.add_argument(
        "--cache-player-actions",
        action="store_const",
        const="players-only",
        dest="cache_mode",
        help="Cache player actions, DM uses live LLM (test mechanics fixes)"
    )
    cache_group.add_argument(
        "--no-cache",
        action="store_const",
        const="none",
        dest="cache_mode",
        help="No caching, all agents use live LLM"
    )

    parser.add_argument(
        "--max-rounds",
        type=int,
        help="Limit replay to N rounds"
    )

    parser.add_argument(
        "--cache-until-round",
        type=int,
        help="Cache all agents until round N, then switch to live LLM (hybrid mode)"
    )

    parser.add_argument(
        "--start-from-round",
        type=int,
        default=0,
        help="Skip rounds 0 to N-1, start replay from round N (useful for isolating specific rounds)"
    )

    args = parser.parse_args()

    # Validate fixture exists
    if not args.fixture.exists():
        print(f"Error: Fixture file {args.fixture} does not exist", file=sys.stderr)
        sys.exit(1)

    # Run replay
    result = asyncio.run(replay_fixture(
        fixture_path=args.fixture,
        output_path=args.output,
        cache_mode=args.cache_mode,
        max_rounds=args.max_rounds,
        cache_until_round=args.cache_until_round,
        start_from_round=args.start_from_round
    ))

    print(f"\n=== Replay Result ===")
    print(f"Status: {result['status']}")
    if result['status'] == 'failed':
        print(f"Error: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
