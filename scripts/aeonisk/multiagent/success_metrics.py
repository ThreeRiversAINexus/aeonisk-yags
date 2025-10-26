"""
Success@n metrics tracking for Aeonisk multi-agent sessions.

Analyzes mission completion rates within n rounds across multiple sessions.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ClockState:
    """Snapshot of a single clock's state."""
    name: str
    current: int
    maximum: int
    filled: bool
    rounds_alive: int

    @property
    def progress_ratio(self) -> float:
        """Get progress as ratio (0.0 to 1.0+)."""
        return self.current / self.maximum if self.maximum > 0 else 0.0

    @property
    def is_complete(self) -> bool:
        """Check if clock is complete (filled or successfully resolved)."""
        return self.filled or self.current >= self.maximum


@dataclass
class SessionResult:
    """Results from a single game session."""
    session_id: str
    random_seed: Optional[int] = None
    total_rounds: int = 0
    mission_success: bool = False
    success_round: Optional[int] = None  # Round when all clocks completed

    # Clock metrics
    clocks_at_start: Dict[str, ClockState] = field(default_factory=dict)
    clocks_at_end: Dict[str, ClockState] = field(default_factory=dict)
    clocks_completed: int = 0
    clocks_failed: int = 0

    # Character metrics
    characters_alive: int = 0
    characters_dead: int = 0
    total_damage_dealt: int = 0
    total_damage_taken: int = 0

    # Void/economy metrics
    avg_void_score: float = 0.0
    total_soulcredit: int = 0

    # Action metrics
    total_actions: int = 0
    successful_actions: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate action success rate."""
        if self.total_actions == 0:
            return 0.0
        return self.successful_actions / self.total_actions


@dataclass
class SuccessAtNMetrics:
    """Success@n metrics across multiple sessions."""
    n_rounds: int  # Round threshold
    total_sessions: int = 0
    successful_sessions: int = 0

    # Detailed statistics
    avg_rounds_to_success: float = 0.0
    avg_clocks_completed: float = 0.0
    avg_survival_rate: float = 0.0
    avg_action_success_rate: float = 0.0

    session_results: List[SessionResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success@n rate."""
        if self.total_sessions == 0:
            return 0.0
        return self.successful_sessions / self.total_sessions

    def add_session(self, result: SessionResult):
        """Add a session result and update metrics."""
        self.session_results.append(result)
        self.total_sessions += 1

        # Check if mission succeeded within n rounds
        if result.mission_success and result.success_round and result.success_round <= self.n_rounds:
            self.successful_sessions += 1

        # Recalculate averages
        self._recalculate_averages()

    def _recalculate_averages(self):
        """Recalculate average statistics from all sessions."""
        if not self.session_results:
            return

        successful_results = [r for r in self.session_results
                            if r.mission_success and r.success_round and r.success_round <= self.n_rounds]

        if successful_results:
            self.avg_rounds_to_success = sum(r.success_round for r in successful_results) / len(successful_results)

        total_chars = sum(r.characters_alive + r.characters_dead for r in self.session_results)
        total_alive = sum(r.characters_alive for r in self.session_results)
        self.avg_survival_rate = total_alive / total_chars if total_chars > 0 else 0.0

        self.avg_clocks_completed = sum(r.clocks_completed for r in self.session_results) / len(self.session_results)

        total_actions = sum(r.total_actions for r in self.session_results)
        total_successful = sum(r.successful_actions for r in self.session_results)
        self.avg_action_success_rate = total_successful / total_actions if total_actions > 0 else 0.0


class SessionSuccessTracker:
    """
    Track mission success/failure for a single session.

    Mission success is defined as: all clocks completed (filled or resolved) within n rounds.
    """

    def __init__(self, session_id: str, random_seed: Optional[int] = None):
        self.session_id = session_id
        self.random_seed = random_seed
        self.current_round = 0
        self.clocks: Dict[str, ClockState] = {}
        self.initial_clocks: Dict[str, ClockState] = {}
        self.mission_complete = False
        self.completion_round: Optional[int] = None

        # Character tracking
        self.characters: Dict[str, Dict[str, Any]] = {}

        # Action tracking
        self.actions_this_session = 0
        self.successful_actions = 0

        # Damage tracking
        self.damage_dealt = 0
        self.damage_taken = 0

    def update_clocks(self, clocks: Dict[str, Any]) -> bool:
        """
        Update clock states and check for mission completion.

        Args:
            clocks: Dict of clock names to clock objects (with current, maximum, filled attributes)

        Returns:
            True if all clocks are now complete
        """
        # Store initial state if not yet set
        if not self.initial_clocks and clocks:
            self.initial_clocks = {
                name: ClockState(
                    name=name,
                    current=c.current,
                    maximum=c.maximum,
                    filled=c.filled if hasattr(c, 'filled') else c.current >= c.maximum,
                    rounds_alive=c._rounds_alive if hasattr(c, '_rounds_alive') else 0
                )
                for name, c in clocks.items()
            }

        # Update current state
        self.clocks = {
            name: ClockState(
                name=name,
                current=c.current,
                maximum=c.maximum,
                filled=c.filled if hasattr(c, 'filled') else c.current >= c.maximum,
                rounds_alive=c._rounds_alive if hasattr(c, '_rounds_alive') else 0
            )
            for name, c in clocks.items()
        }

        # Check if all clocks are complete
        if self.clocks and all(clock.is_complete for clock in self.clocks.values()):
            if not self.mission_complete:
                self.mission_complete = True
                self.completion_round = self.current_round
                logger.info(f"Session {self.session_id}: Mission completed at round {self.current_round}")
            return True

        return False

    def increment_round(self):
        """Increment the current round counter."""
        self.current_round += 1

    def update_character_state(self, character_name: str, state: Dict[str, Any]):
        """Update a character's state."""
        self.characters[character_name] = state

    def record_action(self, success: bool):
        """Record an action attempt."""
        self.actions_this_session += 1
        if success:
            self.successful_actions += 1

    def record_damage(self, dealt: int = 0, taken: int = 0):
        """Record damage dealt or taken."""
        self.damage_dealt += dealt
        self.damage_taken += taken

    def get_result(self) -> SessionResult:
        """Generate final session result."""
        # Count living vs dead characters
        alive = sum(1 for c in self.characters.values() if c.get('health', 0) > 0)
        dead = len(self.characters) - alive

        # Count completed clocks
        completed = sum(1 for c in self.clocks.values() if c.is_complete)
        failed = len(self.clocks) - completed

        # Calculate average void
        avg_void = 0.0
        total_sc = 0
        if self.characters:
            avg_void = sum(c.get('void', 0) for c in self.characters.values()) / len(self.characters)
            total_sc = sum(c.get('soulcredit', 0) for c in self.characters.values())

        return SessionResult(
            session_id=self.session_id,
            random_seed=self.random_seed,
            total_rounds=self.current_round,
            mission_success=self.mission_complete,
            success_round=self.completion_round,
            clocks_at_start=self.initial_clocks,
            clocks_at_end=self.clocks,
            clocks_completed=completed,
            clocks_failed=failed,
            characters_alive=alive,
            characters_dead=dead,
            total_damage_dealt=self.damage_dealt,
            total_damage_taken=self.damage_taken,
            avg_void_score=avg_void,
            total_soulcredit=total_sc,
            total_actions=self.actions_this_session,
            successful_actions=self.successful_actions
        )


def analyze_jsonl_log(log_path: Path) -> SessionResult:
    """
    Analyze a JSONL session log and extract success metrics.

    Args:
        log_path: Path to JSONL log file

    Returns:
        SessionResult with metrics extracted from the log
    """
    session_id = log_path.stem.replace("session_", "")
    tracker = SessionSuccessTracker(session_id)

    with open(log_path, 'r') as f:
        for line in f:
            try:
                event = json.loads(line.strip())
                event_type = event.get('event_type')

                # Extract session metadata
                if event_type == 'session_start':
                    tracker.random_seed = event.get('random_seed')

                # Track rounds
                elif event_type == 'round_summary':
                    tracker.increment_round()

                    # Extract action statistics
                    summary = event.get('summary', {})
                    tracker.actions_this_session += summary.get('actions_attempted', 0)
                    tracker.successful_actions += summary.get('success_count', 0)
                    tracker.damage_dealt += summary.get('damage_dealt_by_players', 0)
                    tracker.damage_taken += summary.get('damage_taken_by_players', 0)

                    # Update clock states if present
                    clocks_data = event.get('clocks', {})
                    if clocks_data:
                        # Convert dict format to clock objects
                        from types import SimpleNamespace
                        clock_objs = {}
                        for name, state in clocks_data.items():
                            if isinstance(state, dict):
                                obj = SimpleNamespace(
                                    current=state.get('current', 0),
                                    maximum=state.get('maximum', 6),
                                    filled=state.get('filled', False),
                                    _rounds_alive=state.get('rounds_alive', 0)
                                )
                                clock_objs[name] = obj

                        tracker.update_clocks(clock_objs)

                # Track character states
                elif event_type == 'character_state':
                    char_name = event.get('character', {}).get('name')
                    if char_name:
                        tracker.update_character_state(char_name, {
                            'health': event.get('character', {}).get('health', 0),
                            'void': event.get('character', {}).get('void', 0),
                            'soulcredit': event.get('character', {}).get('soulcredit', 0)
                        })

                # Check session end status
                elif event_type == 'session_end':
                    status = event.get('final_state', {}).get('session_end_status')
                    if status and status.lower() in ['success', 'complete']:
                        tracker.mission_complete = True
                        if not tracker.completion_round:
                            tracker.completion_round = tracker.current_round

                    # Extract final character states
                    for char_data in event.get('final_state', {}).get('characters', []):
                        tracker.update_character_state(char_data.get('name'), char_data)

                    # Extract final clock states
                    final_clocks = event.get('final_state', {}).get('scene_clocks', {})
                    if final_clocks:
                        from types import SimpleNamespace
                        clock_objs = {}
                        for name, state in final_clocks.items():
                            obj = SimpleNamespace(
                                current=state.get('current', 0),
                                maximum=state.get('maximum', 6),
                                filled=state.get('filled', False),
                                _rounds_alive=state.get('rounds_alive', 0)
                            )
                            clock_objs[name] = obj
                        tracker.update_clocks(clock_objs)

            except json.JSONDecodeError:
                logger.warning(f"Skipping invalid JSON line in {log_path}")
                continue
            except Exception as e:
                logger.warning(f"Error processing event in {log_path}: {e}")
                continue

    return tracker.get_result()


def calculate_success_at_n(results: List[SessionResult], n_values: List[int] = None) -> Dict[int, SuccessAtNMetrics]:
    """
    Calculate success@n metrics for different round thresholds.

    Args:
        results: List of SessionResult objects
        n_values: List of round thresholds to calculate (default: [3, 5, 10, 15, 20])

    Returns:
        Dict mapping n to SuccessAtNMetrics
    """
    if n_values is None:
        n_values = [3, 5, 10, 15, 20]

    metrics = {n: SuccessAtNMetrics(n_rounds=n) for n in n_values}

    for result in results:
        for n in n_values:
            metrics[n].add_session(result)

    return metrics


def format_metrics_report(metrics: Dict[int, SuccessAtNMetrics]) -> str:
    """
    Format success@n metrics into a readable markdown report.

    Args:
        metrics: Dict mapping n to SuccessAtNMetrics

    Returns:
        Formatted markdown report
    """
    lines = ["# Success@n Metrics Report\n"]

    # Summary table
    lines.append("## Success Rates by Round Threshold\n")
    lines.append("| Threshold | Success Rate | Successful | Total | Avg Rounds | Survival Rate |")
    lines.append("|-----------|--------------|------------|-------|------------|---------------|")

    for n in sorted(metrics.keys()):
        m = metrics[n]
        lines.append(
            f"| Success@{n:2d} | {m.success_rate:6.1%} | "
            f"{m.successful_sessions:3d} | {m.total_sessions:3d} | "
            f"{m.avg_rounds_to_success:5.1f} | {m.avg_survival_rate:6.1%} |"
        )

    lines.append("")

    # Detailed metrics
    lines.append("## Detailed Statistics\n")
    for n in sorted(metrics.keys()):
        m = metrics[n]
        lines.append(f"### Success@{n}\n")
        lines.append(f"- **Success Rate**: {m.success_rate:.1%} ({m.successful_sessions}/{m.total_sessions})")
        lines.append(f"- **Avg Rounds to Success**: {m.avg_rounds_to_success:.2f}")
        lines.append(f"- **Avg Clocks Completed**: {m.avg_clocks_completed:.2f}")
        lines.append(f"- **Avg Survival Rate**: {m.avg_survival_rate:.1%}")
        lines.append(f"- **Avg Action Success Rate**: {m.avg_action_success_rate:.1%}")
        lines.append("")

    return "\n".join(lines)
