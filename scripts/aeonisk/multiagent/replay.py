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

    def __init__(self, log_path: str, replay_to_round: int = 999):
        """
        Initialize replay session.

        Args:
            log_path: Path to the JSONL log file to replay
            replay_to_round: Stop replay after this round (default: replay entire session)
        """
        self.log_path = Path(log_path)
        self.replay_to_round = replay_to_round

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
            for line in f:
                event = json.loads(line)
                self.events.append(event)
                event_count += 1

                # Extract session metadata
                if event['event_type'] == 'session_start':
                    self.session_id = event['session']
                    self.config = event.get('config', {})
                    self.random_seed = event.get('random_seed')
                    print(f"  Session ID: {self.session_id}")
                    print(f"  Random seed: {self.random_seed}")

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
                llm_cache=self.llm_cache
            )

            # Modify config to limit rounds if specified
            if self.replay_to_round < 999:
                session.config['max_turns'] = self.replay_to_round
                print(f"✓ Limited replay to {self.replay_to_round} rounds")

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


async def replay_from_log(log_path: str, replay_to_round: int = 999, execute: bool = True):
    """
    Convenience function to replay a session from a log file.

    Args:
        log_path: Path to JSONL log file
        replay_to_round: Stop after this round
        execute: If True, actually execute the replay. If False, just validate.

    Returns:
        ReplayResult
    """
    replay = ReplaySession(log_path, replay_to_round)
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
