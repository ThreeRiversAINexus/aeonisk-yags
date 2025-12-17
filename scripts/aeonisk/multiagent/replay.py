"""
Session Replay Engine - Replays multi-agent sessions from JSONL logs.

This module enables deterministic replay of game sessions for debugging,
analysis, and testing by:
1. Restoring random seed for identical dice rolls
2. Caching and replaying LLM responses to reproduce agent decisions
3. Reconstructing game state up to a specific round

Usage:
    python3 run_multiagent_session.py --replay session_xyz.jsonl --replay-to-round 3
"""

import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class ReplaySession:
    """
    Replays a game session from a JSONL log file up to round N.

    The replay uses:
    - The original random seed to reproduce dice rolls
    - Cached LLM responses to reproduce agent decisions
    - The original session config to recreate the same setup
    """

    def __init__(self, log_path: str, replay_to_round: int = 999, continue_from_round: int = None, start_from_round: int = 0):
        """
        Initialize replay session.

        Args:
            log_path: Path to the JSONL log file to replay
            replay_to_round: Stop replay after this round (default: replay entire session)
            continue_from_round: Switch to live LLM calls after this round (default: None = full replay)
            start_from_round: Skip rounds 0 to N-1, start replay from round N (default: 0 = replay from beginning)

                WARNING: start_from_round is currently BROKEN for LLM cache replay.
                The issue: LLM cache is keyed by (agent_id, call_sequence) where call_sequence
                starts at 0 and increments per-agent. If we "skip" to round N, the session
                still starts internally at round 0, so the first LLM call looks for sequence 0
                in cache - but round N's calls are at sequence M (where M = calls made in
                rounds 0 to N-1). Result: cache miss and crash.

                Use continue_from_round instead: it replays ALL rounds from 0, using cache
                for rounds 0-N (sequences align correctly), then switches to live LLM for N+1+.
                This costs computation time but no API cost for cached rounds.

                To fix start_from_round properly would require either:
                1. Offset the call_sequence counter to start where round N begins, OR
                2. Re-key the cache by (agent_id, round, intra_round_sequence)
        """
        self.log_path = Path(log_path)
        self.replay_to_round = replay_to_round
        self.continue_from_round = continue_from_round
        self.start_from_round = start_from_round

        # Loaded from log
        self.session_id: Optional[str] = None
        self.config: Optional[Dict[str, Any]] = None
        self.random_seed: Optional[int] = None
        self.events: List[Dict[str, Any]] = []

        # LLM response cache: (agent_id, call_sequence) -> response
        self.llm_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}

        # Validation
        if not self.log_path.exists():
            raise FileNotFoundError(f"Log file not found: {log_path}")

    def load_log(self):
        """
        Load and parse the JSONL log file.

        Extracts:
        - Session configuration and random seed
        - All game events (actions, resolutions, etc.)
        - LLM call cache for deterministic replay
        """
        print(f"Loading replay log: {self.log_path}")

        event_count = 0
        llm_call_count = 0

        with open(self.log_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Try to parse line - may contain single or multiple JSON objects
                events_in_line = []
                try:
                    # Normal case: one JSON object per line
                    event = json.loads(line)
                    events_in_line.append(event)
                except json.JSONDecodeError as e:
                    # Handle malformed JSONL (concatenated/truncated events from Ctrl+C interrupts)
                    if '{"event_type"' in line[1:]:
                        import re
                        matches = list(re.finditer(r'\{"event_type":\s*"(\w+)"', line))
                        if len(matches) > 1:
                            print(f"Warning: Line {line_num} has {len(matches)} JSON fragments, attempting recovery...", file=sys.stderr)
                            decoder = json.JSONDecoder()
                            for i, match in enumerate(matches):
                                try:
                                    obj, _ = decoder.raw_decode(line, match.start())
                                    events_in_line.append(obj)
                                except json.JSONDecodeError:
                                    print(f"  Skipped malformed fragment {i+1}: {match.group(1)}", file=sys.stderr)

                    # If still no valid events, skip this line
                    if not events_in_line:
                        print(f"Warning: Skipping invalid JSON at line {line_num}: {e}", file=sys.stderr)
                        continue

                # Process all events from this line
                for event in events_in_line:
                    self.events.append(event)
                    event_count += 1

                    # Extract session metadata
                    if event['event_type'] == 'session_start':
                        self.session_id = event['session']
                        self.config = event.get('config', {})
                        self.random_seed = event.get('random_seed')
                        git_commit = event.get('git_commit')
                        print(f"  Session ID: {self.session_id}")
                        print(f"  Random seed: {self.random_seed}")
                        if git_commit:
                            print(f"  Git commit: {git_commit}")

                    # Build LLM response cache
                    elif event['event_type'] == 'llm_call':
                        agent_id = event['agent_id']
                        call_seq = event['call_sequence']
                        cache_key = (agent_id, call_seq)
                        self.llm_cache[cache_key] = {
                            'prompt': event['prompt'],
                            'response': event['response'],
                            'model': event['model'],
                            'temperature': event['temperature'],
                            'tokens': event.get('tokens', {})
                        }
                        llm_call_count += 1

        print(f"  Loaded {event_count} events")
        print(f"  Cached {llm_call_count} LLM calls for replay")

        # Validation
        if self.session_id is None:
            raise ValueError("Log file missing session_start event")

        if self.random_seed is None:
            logger.warning("No random seed in log - replay may not be deterministic")

    def validate_completeness(self) -> Dict[str, Any]:
        """
        Check if the log has enough data for complete replay.

        Returns:
            Dict with validation results and warnings
        """
        issues = []
        warnings = []

        # Check for random seed
        if self.random_seed is None:
            issues.append("Missing random seed - dice rolls will not match")

        # Check for LLM calls
        if not self.llm_cache:
            issues.append("No LLM calls logged - agent decisions cannot be replayed")

        # Count events by type
        event_types = defaultdict(int)
        for event in self.events:
            event_types[event['event_type']] += 1

        # Check for minimum required events
        required_events = ['session_start', 'scenario', 'round_start']
        for event_type in required_events:
            if event_types[event_type] == 0:
                issues.append(f"Missing required event type: {event_type}")

        return {
            'can_replay': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'event_summary': dict(event_types),
            'llm_calls_cached': len(self.llm_cache)
        }

    def get_rounds_in_session(self) -> List[int]:
        """
        Get list of all round numbers in the session.

        Returns:
            Sorted list of round numbers
        """
        rounds = set()
        for event in self.events:
            if 'round' in event and event['round'] is not None:
                rounds.add(event['round'])
        return sorted(list(rounds))

    def get_events_for_round_range(self, start_round: int, end_round: int) -> List[Dict[str, Any]]:
        """
        Extract events for a specific round range.

        Args:
            start_round: First round to include (inclusive)
            end_round: Last round to include (inclusive)

        Returns:
            List of events within the round range
        """
        filtered_events = []
        for event in self.events:
            round_num = event.get('round')

            # Include events with null round (pre-round declarations)
            if round_num is None:
                continue

            # Include events within range
            if start_round <= round_num <= end_round:
                filtered_events.append(event)

        return filtered_events

    def get_events_to_replay(self) -> List[Dict[str, Any]]:
        """
        Get filtered list of events to replay based on start_from_round.

        When start_from_round > 0, this filters out early rounds but
        preserves critical dependencies like session_start and scenario.

        Returns:
            List of events to replay
        """
        if self.start_from_round == 0:
            # No filtering needed - replay everything
            return self.events

        # Always include these event types regardless of round
        critical_event_types = {
            'session_start',
            'scenario',
            'enemy_spawn',  # Enemies may spawn in earlier rounds but remain active
        }

        filtered_events = []
        for event in self.events:
            event_type = event.get('event_type')
            round_num = event.get('round')

            # Always include critical events
            if event_type in critical_event_types:
                filtered_events.append(event)
                continue

            # Include events with null round (pre-round declarations like LLM calls)
            # Note: We keep ALL LLM calls because agents are stateful
            if round_num is None:
                filtered_events.append(event)
                continue

            # Include events from start_from_round onwards
            if round_num >= self.start_from_round:
                filtered_events.append(event)

        return filtered_events

    def get_mock_llm_client(self):
        """
        Create a MockLLMClient that returns cached responses.

        Returns:
            MockLLMClient instance configured with this replay's cache
        """
        from .llm_logger import MockLLMClient
        return MockLLMClient(self.llm_cache)

    async def replay(self):
        """
        Execute the replay.

        This creates a new session using the original config,
        sets the random seed, and injects the MockLLMClient
        to replay all agent decisions.

        Returns:
            ReplayResult with statistics and comparison to original
        """
        if not self.config:
            raise ValueError("Must call load_log() before replay()")

        print(f"\n=== Starting Replay Execution ===")
        if self.start_from_round > 0:
            print(f"⏩ SKIP MODE: Starting from round {self.start_from_round} (skipping rounds 0-{self.start_from_round - 1})")
        if self.continue_from_round is not None:
            print(f"🔄 HYBRID MODE: Cached rounds 1-{self.continue_from_round}, then LIVE from round {self.continue_from_round + 1}")
        else:
            print(f"Replaying up to round: {self.replay_to_round}")
        print(f"Random seed: {self.random_seed}")
        print(f"LLM calls cached: {len(self.llm_cache)}")
        print()

        # Create session in replay mode
        from .session import SelfPlayingSession

        try:
            session = SelfPlayingSession(
                replay_mode=True,
                replay_config=self.config,
                random_seed=self.random_seed,
                llm_cache=self.llm_cache,
                continue_from_round=self.continue_from_round
            )

            # Modify config to limit rounds if specified
            # When start_from_round is used, adjust max_turns to account for skipped rounds
            if self.replay_to_round < 999:
                # If starting from round N and replaying to round M, only run M-N+1 rounds
                actual_rounds_to_run = self.replay_to_round - self.start_from_round + 1
                session.config['max_turns'] = actual_rounds_to_run
                print(f"✓ Limited replay to rounds {self.start_from_round}-{self.replay_to_round} ({actual_rounds_to_run} rounds)")
            elif self.start_from_round > 0:
                # If starting from round N but no end specified, still need to configure
                # The session will run normally from round N onwards
                print(f"✓ Starting from round {self.start_from_round}, running to end of session")

            # Run the session
            await session.start_session()

            print("\n✅ Replay completed successfully!")
            return {
                'status': 'success',
                'random_seed': self.random_seed,
                'llm_calls_used': len(self.llm_cache),
                'rounds_replayed': self.replay_to_round
            }

        except Exception as e:
            print(f"\n❌ Replay failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'failed',
                'error': str(e)
            }


async def replay_from_log(log_path: str, replay_to_round: int = 999, continue_from_round: int = None, start_from_round: int = 0, execute: bool = True):
    """
    Convenience function to replay a session from a log file.

    Args:
        log_path: Path to JSONL log file
        replay_to_round: Stop after this round
        continue_from_round: Switch to live LLM calls after this round (hybrid mode)
        start_from_round: Skip rounds 0 to N-1, start from round N
        execute: If True, actually execute the replay. If False, just validate.

    Returns:
        ReplayResult
    """
    replay = ReplaySession(log_path, replay_to_round, continue_from_round, start_from_round)
    replay.load_log()

    # Validate
    validation = replay.validate_completeness()
    print("\n=== Replay Validation ===")
    print(f"Can replay: {validation['can_replay']}")

    if validation['issues']:
        print("\n❌ Issues:")
        for issue in validation['issues']:
            print(f"  - {issue}")

    if validation['warnings']:
        print("\n⚠ Warnings:")
        for warning in validation['warnings']:
            print(f"  - {warning}")

    print(f"\nEvent summary:")
    for event_type, count in sorted(validation['event_summary'].items()):
        print(f"  {event_type:30s}: {count}")

    print(f"\nLLM calls cached: {validation['llm_calls_cached']}")

    if not validation['can_replay']:
        print("\n❌ Cannot replay - missing required data")
        return None

    # Execute replay if requested
    if execute:
        return await replay.replay()
    else:
        return validation


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python replay.py <log_file.jsonl> [replay_to_round]")
        sys.exit(1)

    log_file = sys.argv[1]
    replay_to_round = int(sys.argv[2]) if len(sys.argv) > 2 else 999

    result = replay_from_log(log_file, replay_to_round)
    print(f"\nReplay result: {result}")
