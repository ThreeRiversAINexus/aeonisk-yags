#!/usr/bin/env python3
"""
Bulk Session Runner for Aeonisk YAGS

Runs multiple multi-agent sessions in parallel using subprocess orchestration.
Designed for bulk generation with batch proxy support for cost optimization.

Features:
- Parallel execution via ProcessPoolExecutor
- Automatic proxy health check before execution
- Resume capability for failed runs (based on session_end event in JSONL)
- Replay-resume: Use cached LLM calls to save ~60-70% API cost on retries
- Progress dashboard with change detection (only updates when state changes)
- Timing info: total runtime, per-run duration, time since last change
- Aggregated statistics and reporting
- Per-run output isolation (prevents JSONL collisions)

Usage:
    # Basic usage (run same config 10 times with 4 workers)
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 10 \\
        --workers 4

    # With progress dashboard (updates only on state changes)
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 10 \\
        --workers 10 \\
        --progress

    # With batch proxy for 50% cost savings
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 100 \\
        --workers 20 \\
        --proxy http://localhost:8000

    # With proxy in direct mode (no batching, immediate API calls)
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 10 \\
        --workers 4 \\
        --proxy http://localhost:8000 \\
        --strategy direct

    # Preview effective routing + validation without launching anything
    python scripts/bulk_session_runner.py \\
        --configs config1.json config2.json \\
        --proxy http://localhost:8000 \\
        --dry-run

    # Resume failed runs (replay enabled by default - saves API cost)
    python scripts/bulk_session_runner.py \\
        --resume \\
        --run-dir bulk_output/run_2025-11-28_212301_ff68f5ff

    # Resume without replay (restart from scratch, costs more)
    python scripts/bulk_session_runner.py \\
        --resume --no-replay \\
        --run-dir bulk_output/run_2025-11-28_212301_ff68f5ff

    # Multiple configs with custom output dir
    python scripts/bulk_session_runner.py \\
        --configs config1.json config2.json \\
        --runs-per-config 50 \\
        --output-dir my_bulk_output/

    # Show errors and faster progress updates
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 10 \\
        --progress \\
        --progress-interval 5 \\
        --show-errors

    # Regenerate all test fixtures (one command!)
    python scripts/bulk_session_runner.py --regenerate-fixtures

    # Regenerate AND auto-extract fixtures (fully automated!)
    python scripts/bulk_session_runner.py --regenerate-fixtures --extract

Options:
    --config FILE           Session config JSON file (not required with --resume)
    --configs FILE [FILE]   Multiple config files (not required with --resume)
    --runs N                Number of runs (default: 1)
    --runs-per-config N     Runs per config (with --configs)
    --workers N             Parallel workers (default: 4)
    --output-dir DIR        Output directory (default: bulk_output/)
    --proxy URL             Batch proxy URL (e.g., http://localhost:8000)
    --strategy MODE         Explicit proxy strategy override (auto/direct/batch).
                            Omitted = each config's own proxy_strategy is honored.
    --direct                Deprecated alias for --strategy direct
    --dry-run               Validate + print effective routing, then exit
    --resume                Resume from --run-dir, skip completed sessions.
                            Config loaded from metadata.json in run directory.
                            By default uses replay (cached LLM calls) to save cost.
    --no-replay             Disable replay when resuming. Restart failed sessions
                            from scratch instead of using cached LLM calls.
    --run-dir DIR           Existing run directory for --resume
    --progress              Show progress dashboard (updates only on state change)
    --progress-interval N   Poll interval in seconds for change detection (default: 10)
    --log-level LEVEL       Session log level (DEBUG/INFO/WARNING/ERROR/LLM/TRACE)
    --show-errors           Print stderr from failed runs immediately
    --skip-health-check     Skip proxy health check
"""

import os
import sys
import json
import time
import argparse
import logging
import subprocess
import threading
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add scripts/ so the aeonisk package is importable
sys.path.insert(0, str(Path(__file__).parent))

from aeonisk.multiagent.launch_config import (
    LOG_LEVEL_CHOICES,
    PROXY_STRATEGY_CHOICES,
    apply_proxy_overrides,
    effective_routing_report,
    iter_agent_llm_configs,
    validate_session_config,
)

logger = logging.getLogger(__name__)


class ProgressMonitor:
    """
    Monitor and display progress of running sessions.

    Only updates output when state changes (event-driven with polling for detection).
    Shows timing info: total runtime, per-run duration, time since last change.
    """

    def __init__(self, output_dir: Path, total_runs: int, refresh_interval: float = 5.0,
                 bulk_run_name: Optional[str] = None):
        self.output_dir = output_dir
        self.total_runs = total_runs
        self.refresh_interval = refresh_interval
        self.bulk_run_name = bulk_run_name or output_dir.name
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._completed_runs: Set[int] = set()
        self._failed_runs: Set[int] = set()

        # Timing tracking
        self._bulk_start_time: float = time.time()
        self._run_start_times: Dict[int, float] = {}
        self._run_final_durations: Dict[int, float] = {}  # Actual duration for completed runs
        self._last_change_time: float = time.time()
        self._prev_change_time: float = time.time()  # Track previous change for meaningful "time since"

        # Change detection
        self._last_state_hash: Optional[str] = None
        self._previous_state: Dict[int, Dict] = {}  # For highlighting changes

    def start(self):
        """Start the progress monitor thread."""
        self._bulk_start_time = time.time()
        self._last_change_time = time.time()
        self._prev_change_time = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the progress monitor thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def mark_started(self, run_id: int):
        """Mark a run as started (for timing)."""
        self._run_start_times[run_id] = time.time()

    def mark_completed(self, run_id: int, duration: Optional[float] = None):
        """Mark a run as completed with optional actual duration."""
        self._completed_runs.add(run_id)
        if duration is not None:
            self._run_final_durations[run_id] = duration

    def mark_failed(self, run_id: int, duration: Optional[float] = None):
        """Mark a run as failed with optional actual duration."""
        self._failed_runs.add(run_id)
        if duration is not None:
            self._run_final_durations[run_id] = duration

    def _format_duration(self, seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m{secs:02d}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h{mins:02d}m"

    def _monitor_loop(self):
        """Main monitoring loop - only prints when state changes."""
        while not self._stop_event.wait(self.refresh_interval):
            try:
                self._check_and_display_progress()
            except Exception as e:
                logger.debug(f"Progress monitor error: {e}")

    def _get_current_state(self) -> Tuple[Dict[int, Dict], str]:
        """
        Gather current state of all runs.

        Returns:
            Tuple of (state_dict, state_hash) where state_dict maps run_id to status info
        """
        state = {}

        for run_id in range(1, self.total_runs + 1):
            run_dir = self.output_dir / f"run_{run_id:04d}"

            if run_id in self._completed_runs:
                state[run_id] = {'status': 'done'}
            elif run_id in self._failed_runs:
                state[run_id] = {'status': 'failed'}
            elif not run_dir.exists():
                state[run_id] = {'status': 'queued'}
            else:
                # Scan JSONL for progress
                jsonl_files = list(run_dir.glob("session_*.jsonl"))
                if jsonl_files:
                    stats = self._get_session_progress(jsonl_files[0])
                    state[run_id] = {
                        'status': 'running',
                        'round': stats['round'],
                        'llm_calls': stats['llm_calls'],
                        'actions': stats['actions'],
                        'has_error': stats.get('has_error', False),
                        'error_type': stats.get('error_type'),
                        'error_message': stats.get('error_message')
                    }
                    # Track start time if not already tracked
                    if run_id not in self._run_start_times:
                        self._run_start_times[run_id] = time.time()
                else:
                    state[run_id] = {'status': 'starting'}
                    if run_id not in self._run_start_times:
                        self._run_start_times[run_id] = time.time()

        # Create hash for change detection (exclude timing, just status/progress)
        state_hash = str(sorted([(k, tuple(sorted(v.items()))) for k, v in state.items()]))

        return state, state_hash

    def _check_and_display_progress(self):
        """Check for state changes and display if changed."""
        state, state_hash = self._get_current_state()

        if state_hash != self._last_state_hash:
            # Update timestamps AFTER display so time_since_change is meaningful
            self._prev_change_time = self._last_change_time
            self._last_change_time = time.time()
            self._last_state_hash = state_hash
            self._display_progress(state, self._previous_state)
            self._previous_state = state.copy()

    def _display_progress(self, state: Dict[int, Dict], previous_state: Dict[int, Dict]):
        """Display current progress with timing info, highlighting changes."""
        now = time.time()
        total_runtime = now - self._bulk_start_time
        time_since_change = now - self._prev_change_time  # Time since PREVIOUS change
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Sort runs by status: running/starting first, then completed/failed, then queued
        status_order = {'running': 0, 'starting': 1, 'done': 2, 'failed': 3, 'queued': 4}
        sorted_run_ids = sorted(
            range(1, self.total_runs + 1),
            key=lambda rid: (status_order.get(state.get(rid, {}).get('status', 'queued'), 5), rid)
        )

        progress_lines = []

        for run_id in sorted_run_ids:
            run_state = state.get(run_id, {'status': 'queued'})
            prev_state = previous_state.get(run_id, {})
            status = run_state['status']
            prev_status = prev_state.get('status', '')

            # Check what changed
            status_changed = status != prev_status

            # Calculate run duration
            run_duration = ""
            if run_id in self._run_final_durations:
                # Use actual duration for completed/failed runs
                duration_secs = self._run_final_durations[run_id]
                run_duration = f" [{self._format_duration(duration_secs)}]"
            elif run_id in self._run_start_times:
                # Estimate for running sessions
                duration_secs = now - self._run_start_times[run_id]
                run_duration = f" [{self._format_duration(duration_secs)}]"

            if status == 'done':
                status_str = "**✓ DONE**" if status_changed else "✓ DONE"
                detail = run_duration
            elif status == 'failed':
                status_str = "**✗ FAIL**" if status_changed else "✗ FAIL"
                detail = run_duration
            elif status == 'queued':
                status_str = "**⏳ queued**" if status_changed else "⏳ queued"
                detail = ""
            elif status == 'starting':
                status_str = "**▶ starting**" if status_changed else "▶ starting"
                detail = run_duration
            else:  # running
                # Check if session has encountered an error
                has_error = run_state.get('has_error', False)
                if has_error:
                    status_str = "**⚠ ERROR**" if status_changed else "⚠ ERROR"
                else:
                    status_str = "**▶ running**" if status_changed else "▶ running"

                r = run_state.get('round', 0)
                calls = run_state.get('llm_calls', 0)
                actions = run_state.get('actions', 0)
                prev_r = prev_state.get('round', 0)
                prev_calls = prev_state.get('llm_calls', 0)
                prev_actions = prev_state.get('actions', 0)

                # Build detail with highlights for changed values
                r_str = f"**R{r:02d}**" if r != prev_r else f"R{r:02d}"
                calls_str = f"**{calls:3d}**" if calls != prev_calls else f"{calls:3d}"
                actions_str = f"**{actions:3d}**" if actions != prev_actions else f"{actions:3d}"
                detail = f"{r_str} | {calls_str} calls | {actions_str} actions{run_duration}"

                # Add error indicator
                if has_error:
                    error_type = run_state.get('error_type', 'unknown')
                    detail += f" [ERR: {error_type}]"

            progress_lines.append(f"  [{run_id:02d}] {status_str:20s} {detail}")

        # Build display
        completed = len(self._completed_runs)
        failed = len(self._failed_runs)
        queued_count = sum(1 for s in state.values() if s.get('status') == 'queued')
        active_count = self.total_runs - completed - failed - queued_count

        header = (
            f"\n{'='*78}\n"
            f"[{timestamp}] {self.bulk_run_name}\n"
            f"PROGRESS: {completed}/{self.total_runs} complete | "
            f"{active_count} active | {queued_count} queued | {failed} failed\n"
            f"Runtime: {self._format_duration(total_runtime)} | "
            f"Last change: {self._format_duration(time_since_change)} ago\n"
            f"{'='*78}"
        )

        print(header)
        for line in progress_lines:
            print(line)
        print(f"{'='*78}\n")

    def _get_session_progress(self, jsonl_path: Path) -> Dict:
        """Extract progress stats from JSONL file."""
        stats = {
            'round': 0,
            'llm_calls': 0,
            'actions': 0,
            'has_error': False,
            'error_type': None,
            'error_message': None
        }

        try:
            with open(jsonl_path, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        event_type = event.get('event_type')

                        # Track round
                        round_num = event.get('round')
                        if round_num is not None and round_num > stats['round']:
                            stats['round'] = round_num

                        # Count LLM calls
                        if event_type == 'llm_call':
                            stats['llm_calls'] += 1

                        # Count actions
                        if event_type in ('action_declaration', 'action_resolution'):
                            stats['actions'] += 1

                        # Detect session errors
                        if event_type == 'session_error':
                            stats['has_error'] = True
                            stats['error_type'] = event.get('error_type', 'unknown')
                            stats['error_message'] = event.get('error_message', 'Unknown error')

                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass

        return stats


@dataclass
class RunResult:
    """Result of a single session run."""
    run_id: int
    config_path: str
    output_path: str
    success: bool
    duration_seconds: float
    error: Optional[str] = None
    total_tokens: Optional[int] = None
    total_rounds: Optional[int] = None
    # Post-session mechanical integrity gate (scripts/session_invariants.py).
    # A completed session can still be self-contradictory (stun-KO'd actor still
    # acting, "subdued" prisoner spawned armed); quarantined flags that so the
    # session is excluded from datasets even though it ran to completion.
    quarantined: bool = False
    violations: Optional[List[Dict[str, Any]]] = None


@dataclass
class BulkRunStats:
    """Aggregated statistics for bulk run."""
    total_runs: int
    successful_runs: int
    failed_runs: int
    skipped_runs: int
    total_duration_seconds: float
    avg_duration_seconds: float
    total_tokens: int
    avg_tokens_per_run: float
    runs_per_hour: float


def check_proxy_health(proxy_url: str, timeout: int = 5) -> Tuple[bool, str]:
    """
    Check if proxy server is reachable and healthy.

    Args:
        proxy_url: Proxy server URL
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_healthy, status_message)
    """
    try:
        response = requests.get(f"{proxy_url}/health", timeout=timeout)
        if response.status_code == 200:
            return True, "Proxy server healthy"
        else:
            return False, f"Proxy returned HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to proxy at {proxy_url}"
    except requests.exceptions.Timeout:
        return False, f"Proxy health check timeout (>{timeout}s)"
    except Exception as e:
        return False, f"Proxy health check error: {e}"


def load_session_config(config_path: str) -> Dict:
    """Load and parse session config JSON."""
    with open(config_path, 'r') as f:
        return json.load(f)


def extract_model_from_config(config_path: str, _cache: Dict[str, str] = {}) -> str:
    """Extract DM model name from session config for logging.

    Caches results per config path since multiple runs share the same config.

    Args:
        config_path: Path to session config JSON

    Returns:
        Model name string (e.g. 'gpt-5.2-2025-12-11') or 'unknown' on failure
    """
    if config_path in _cache:
        return _cache[config_path]

    try:
        config = load_session_config(config_path)
        model = config.get('agents', {}).get('dm', {}).get('llm', {}).get('model', 'unknown')
        _cache[config_path] = model
        return model
    except Exception:
        _cache[config_path] = 'unknown'
        return 'unknown'


def modify_config_for_bulk_run(
    config: Dict,
    run_id: int,
    output_path: str,
    proxy_url: Optional[str] = None,
    proxy_strategy: Optional[str] = None,
    force_truncate: bool = False
) -> Dict:
    """
    Modify session config for bulk run.

    Args:
        config: Original session config
        run_id: Unique run identifier
        output_path: Output JSONL path for this run
        proxy_url: Optional proxy URL to inject
        proxy_strategy: Explicit proxy routing strategy override
            ('auto', 'direct', 'batch'). None means honor the config's
            own proxy_strategy — never overwrite it with a default.
        force_truncate: If True, inject force_truncate into all agent LLM configs

    Returns:
        Modified config dict
    """
    modified = config.copy()

    # Set unique session name
    original_name = modified.get('session_name', 'session')
    modified['session_name'] = f"{original_name}_run_{run_id:04d}"

    # Set unique random seed (if not already set)
    if 'random_seed' not in modified:
        modified['random_seed'] = run_id * 1000  # Deterministic but unique per run

    # Override output_dir to use the dedicated output path for this run
    # Extract just the directory from output_path
    from pathlib import Path
    output_dir_path = str(Path(output_path).parent)
    modified['output_dir'] = output_dir_path

    # Apply explicitly-passed proxy flags; unset flags never touch config
    # values (see launch_config precedence contract)
    if proxy_url or proxy_strategy:
        apply_proxy_overrides(modified, proxy_url, proxy_strategy)

    # If force_truncate, inject into all agent LLM configs
    if force_truncate:
        modified = inject_force_truncate(modified)

    # Disable human interface for bulk runs (prevents Observer> prompt spam)
    modified['enable_human_interface'] = False

    return modified


def inject_proxy_config(config: Dict, proxy_url: str,
                        proxy_strategy: Optional[str] = None) -> Dict:
    """
    Inject proxy configuration into all agents' LLM configs.

    Thin wrapper around launch_config.apply_proxy_overrides, kept for
    backward compatibility. proxy_strategy=None honors each agent's
    config value instead of overwriting it.
    """
    apply_proxy_overrides(config, proxy_url, proxy_strategy)
    return config


def inject_force_truncate(config: Dict) -> Dict:
    """
    Inject force_truncate=True into all agent LLM configs.

    When enabled, providers truncate string fields to their maxLength limits
    on first attempt instead of retrying the entire LLM call.

    Args:
        config: Session config dict

    Returns:
        Modified config dict
    """
    for _label, llm_config in iter_agent_llm_configs(config):
        llm_config['force_truncate'] = True

    return config


def preflight_configs(
    config_paths: List,
    proxy_url: Optional[str],
    proxy_strategy: Optional[str],
    skip_validation: bool = False
) -> bool:
    """
    Validate configs and log the effective LLM routing per unique config.

    Logs explicit flag overrides at WARNING (a flag changing a config
    value) and the final per-agent routing at INFO, so nothing about how
    requests will route is silent. Returns False if any config fails
    validation or cannot be loaded.
    """
    import copy as _copy

    all_ok = True
    for config_path in dict.fromkeys(str(c) for c in config_paths):
        name = Path(config_path).name
        try:
            config = load_session_config(config_path)
        except Exception as e:
            logger.error(f"✗ {name}: failed to load config: {e}")
            all_ok = False
            continue

        if not skip_validation:
            errors = validate_session_config(config, path=config_path)
            if errors:
                logger.error(f"✗ {name}: {len(errors)} validation error(s):")
                for err in errors:
                    logger.error(f"    {err}")
                all_ok = False
                continue

        preview = _copy.deepcopy(config)
        changes = apply_proxy_overrides(preview, proxy_url, proxy_strategy)
        for line in changes:
            logger.warning(f"  OVERRIDE {line}")

        logger.info(f"Effective routing for {name}:")
        for line in effective_routing_report(preview):
            logger.info(line)

        proxied_strategies = [
            llm.get('proxy_strategy') or 'auto'
            for _label, llm in iter_agent_llm_configs(preview)
            if llm.get('provider') == 'batch_proxy' or llm.get('use_proxy')
        ]
        if any(s in ('auto', 'batch') for s in proxied_strategies):
            logger.warning(
                f"  {name}: strategy auto/batch may route requests to the "
                f"provider batch queue (minutes-per-request latency); pass "
                f"--strategy direct for interactive-speed sessions")

    if all_ok:
        logger.info(
            "Per-run mutations: session_name += _run_NNNN; output_dir → "
            "run_NNNN/; enable_human_interface=False; random_seed = "
            "run_id*1000 unless set in config")
    return all_ok


def gate_session_invariants(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Run the mechanical-integrity checker on a completed session.

    Returns the ERROR-severity violations as plain dicts (empty = clean). Also
    writes a per-run `invariant_violations.json` sidecar next to the session so a
    quarantined run is self-describing. Never raises — a checker failure must not
    fail the run it is auditing (logged as a soft note instead).
    """
    try:
        from scripts.session_invariants import check_file  # lazy: keep subprocess import cheap
        violations = check_file(str(jsonl_path))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Invariant checker failed on {jsonl_path.name}: {exc!r}")
        return []
    errors = [v for v in violations if v.severity == "error"]
    if violations:
        sidecar = jsonl_path.parent / "invariant_violations.json"
        try:
            with open(sidecar, "w") as fh:
                json.dump([{"invariant": v.invariant, "severity": v.severity,
                            "round": v.round, "entity": v.entity, "message": v.message}
                           for v in violations], fh, indent=2)
        except OSError:
            pass
    return [{"invariant": v.invariant, "severity": v.severity, "round": v.round,
             "entity": v.entity, "message": v.message} for v in errors]


def run_single_session(
    config_path: str,
    run_id: int,
    output_dir: Path,
    proxy_url: Optional[str] = None,
    log_level: str = "INFO",
    use_stored_config: bool = False,
    session_timeout: int = 90000,
    attempt_replay: bool = False,
    proxy_strategy: Optional[str] = None,
    force_truncate: bool = False,
    check_invariants: bool = True,
    fail_on_invariant: bool = False
) -> RunResult:
    """
    Run a single session via subprocess.

    Args:
        config_path: Path to session config JSON
        run_id: Unique run identifier
        output_dir: Output directory for JSONL
        proxy_url: Optional proxy URL
        log_level: Log level for session
        use_stored_config: If True, config_path points to an already-modified
            config in run_NNNN/config.json (used for resume fallback mode)
        session_timeout: Timeout in seconds for subprocess (default: 90000 = 25 hours)
        attempt_replay: If True, try to resume via replay before falling back to restart.
            Requires partial JSONL with cached LLM calls to exist.

    Returns:
        RunResult with execution details
    """
    start_time = time.time()

    # Attempt replay-based resume if requested
    run_dir = output_dir / f"run_{run_id:04d}"
    if attempt_replay and run_dir.exists():
        # Find partial JSONL
        partial_jsonls = list(run_dir.glob("session_*.jsonl"))
        if partial_jsonls:
            # Pick the largest file (most progress made) in case there are multiple
            partial_jsonl = max(partial_jsonls, key=lambda p: p.stat().st_size)
            last_round = get_last_successful_round(partial_jsonl)

            if last_round is not None and last_round >= 1:
                # Try replay from round N-1 (cache 0 to N-1, live from N)
                continue_from = last_round - 1
                replay_output = run_dir / f"session_replay_{run_id:04d}.jsonl"

                logger.info(f"Run {run_id}: Partial session found (completed round {last_round})")

                replay_success, replay_error = try_replay_session(
                    partial_jsonl=partial_jsonl,
                    output_path=replay_output,
                    continue_from_round=continue_from,
                    timeout=session_timeout
                )

                if replay_success:
                    duration = time.time() - start_time
                    total_tokens, total_rounds = extract_session_stats(replay_output)
                    logger.info(f"  ✓ Replay succeeded! (rounds 0-{continue_from} cached, {continue_from+1}+ live)")

                    return RunResult(
                        run_id=run_id,
                        config_path=config_path,
                        output_path=str(replay_output),
                        success=True,
                        duration_seconds=duration,
                        total_tokens=total_tokens,
                        total_rounds=total_rounds
                    )
                else:
                    logger.warning(f"  ⚠ Replay failed: {replay_error}")
                    logger.info(f"  ↳ Falling back to fresh restart...")
            else:
                logger.info(f"Run {run_id}: Partial session has no completed rounds, using fresh restart")

    # Load and modify config
    try:
        if use_stored_config:
            # Config is already modified and in place (resume fallback mode)
            # config_path is already run_NNNN/config.json
            temp_config_path = Path(config_path)
            run_dir = temp_config_path.parent
        else:
            config = load_session_config(config_path)

            # Create subdirectory for this run
            run_dir = output_dir / f"run_{run_id:04d}"
            run_dir.mkdir(exist_ok=True)

            output_path = run_dir / "session.jsonl"

            # Modify config for this run
            modified_config = modify_config_for_bulk_run(
                config, run_id, str(output_path), proxy_url, proxy_strategy,
                force_truncate
            )

            # Write modified config to run directory
            temp_config_path = run_dir / "config.json"
            with open(temp_config_path, 'w') as f:
                json.dump(modified_config, f, indent=2)

        # Run session via subprocess
        cmd = [
            sys.executable,
            "scripts/run_multiagent_session.py",
            str(temp_config_path),
            "--log-level", log_level
        ]

        # Log stderr/stdout to run directory
        stderr_log = run_dir / "stderr.log"
        stdout_log = run_dir / "stdout.log"

        with open(stdout_log, 'w') as stdout_f, open(stderr_log, 'w') as stderr_f:
            result = subprocess.run(
                cmd,
                stdout=stdout_f,
                stderr=stderr_f,
                text=True,
                timeout=session_timeout
            )

        duration = time.time() - start_time

        # Find actual JSONL file (session uses UUID in filename)
        jsonl_files = list(run_dir.glob("session_*.jsonl"))
        actual_jsonl = jsonl_files[0] if jsonl_files else output_path

        # Check session completion via JSONL (authoritative, ignores spurious exit errors)
        session_completed = check_session_completed(actual_jsonl)

        if session_completed:
            # Session completed successfully - extract stats
            total_tokens, total_rounds = extract_session_stats(actual_jsonl)

            # Log if exit code was non-zero but session still completed
            if result.returncode != 0:
                logger.debug(
                    f"Run {run_id}: Session completed despite non-zero exit code "
                    f"(likely spurious shutdown error)"
                )

            # Post-session mechanical-integrity gate. The session RAN, but may be
            # self-contradictory; quarantine it so it never silently enters a dataset.
            error_violations = gate_session_invariants(actual_jsonl) if check_invariants else []
            quarantined = bool(error_violations)
            if quarantined:
                inv_names = sorted({v["invariant"] for v in error_violations})
                logger.warning(
                    f"Run {run_id}: QUARANTINED — {len(error_violations)} invariant "
                    f"violation(s): {', '.join(inv_names)} (see invariant_violations.json)"
                )

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(actual_jsonl),
                # A quarantined run is not a usable success when gating is strict.
                success=not (quarantined and fail_on_invariant),
                duration_seconds=duration,
                error=(f"Quarantined: invariant violations "
                       f"({', '.join(sorted({v['invariant'] for v in error_violations}))})"
                       if quarantined and fail_on_invariant else None),
                total_tokens=total_tokens,
                total_rounds=total_rounds,
                quarantined=quarantined,
                violations=error_violations or None
            )
        elif result.returncode == 0:
            # Exit code 0 but no session_end - partial completion
            total_tokens, total_rounds = extract_session_stats(actual_jsonl)

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(actual_jsonl),
                success=False,
                duration_seconds=duration,
                error="Session exited cleanly but no session_end event found (incomplete)",
                total_tokens=total_tokens,
                total_rounds=total_rounds
            )
        else:
            # Session failed - read error from stderr log
            error_msg = "Unknown error"
            if stderr_log.exists():
                with open(stderr_log, 'r') as f:
                    stderr_content = f.read()
                    error_msg = stderr_content[-500:] if stderr_content else "No error message"

            # Still extract stats if JSONL exists (partial data)
            total_tokens, total_rounds = extract_session_stats(actual_jsonl)

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(actual_jsonl),
                success=False,
                duration_seconds=duration,
                error=error_msg,
                total_tokens=total_tokens,
                total_rounds=total_rounds
            )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time

        # Check if session completed before timeout (data may still be valid)
        if 'run_dir' in locals():
            jsonl_files = list(run_dir.glob("session_*.jsonl"))
            if jsonl_files:
                actual_jsonl = jsonl_files[0]
                if check_session_completed(actual_jsonl):
                    # Session completed despite timeout (probably hung during cleanup)
                    total_tokens, total_rounds = extract_session_stats(actual_jsonl)
                    logger.debug(
                        f"Run {run_id}: Session completed but process timed out "
                        f"(hung during cleanup)"
                    )
                    return RunResult(
                        run_id=run_id,
                        config_path=config_path,
                        output_path=str(actual_jsonl),
                        success=True,
                        duration_seconds=duration,
                        total_tokens=total_tokens,
                        total_rounds=total_rounds
                    )

                # Partial data available
                total_tokens, total_rounds = extract_session_stats(actual_jsonl)
                return RunResult(
                    run_id=run_id,
                    config_path=config_path,
                    output_path=str(actual_jsonl),
                    success=False,
                    duration_seconds=duration,
                    error=f"Session timeout (>{session_timeout}s) - partial data saved",
                    total_tokens=total_tokens,
                    total_rounds=total_rounds
                )

        return RunResult(
            run_id=run_id,
            config_path=config_path,
            output_path=str(output_path) if 'output_path' in locals() else "N/A",
            success=False,
            duration_seconds=duration,
            error=f"Session timeout (>{session_timeout}s)"
        )

    except Exception as e:
        duration = time.time() - start_time

        # Check if session completed before exception
        if 'run_dir' in locals():
            jsonl_files = list(run_dir.glob("session_*.jsonl"))
            if jsonl_files:
                actual_jsonl = jsonl_files[0]
                if check_session_completed(actual_jsonl):
                    total_tokens, total_rounds = extract_session_stats(actual_jsonl)
                    logger.debug(
                        f"Run {run_id}: Session completed but exception during cleanup: {e}"
                    )
                    return RunResult(
                        run_id=run_id,
                        config_path=config_path,
                        output_path=str(actual_jsonl),
                        success=True,
                        duration_seconds=duration,
                        total_tokens=total_tokens,
                        total_rounds=total_rounds
                    )

        return RunResult(
            run_id=run_id,
            config_path=config_path,
            output_path=str(output_path) if 'output_path' in locals() else "N/A",
            success=False,
            duration_seconds=duration,
            error=str(e)
        )


def check_session_completed(jsonl_path: Path) -> bool:
    """
    Check if session completed successfully by looking for session_end event in JSONL.

    This is the authoritative check for session success - exit codes can be
    unreliable due to spurious shutdown errors (e.g., stdin lock issues).

    A session is only considered "completed" if it has a session_end event with
    a successful termination reason (victory, defeat, draw, max_turns_reached).
    Interrupted or errored sessions are NOT considered completed and should be
    resumed.

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        True if session completed successfully, False otherwise
    """
    # Termination reasons that indicate successful completion
    COMPLETED_REASONS = {'victory', 'defeat', 'draw', 'completed'}

    try:
        if not jsonl_path.exists():
            return False

        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get('event_type') == 'session_end':
                        reason = event.get('termination_reason', '')
                        # Only count as completed if it's a successful termination
                        if reason in COMPLETED_REASONS:
                            return True
                        # Interrupted/errored sessions should be resumed
                        return False
                except json.JSONDecodeError:
                    continue

        return False

    except Exception as e:
        logger.warning(f"Failed to check session completion for {jsonl_path}: {e}")
        return False


def check_session_errors(jsonl_path: Path) -> List[Dict]:
    """
    Check for session_error events in JSONL (fatal errors during session).

    Used for detecting crashed/errored sessions in bulk runs.

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        List of session_error event dicts found (empty if none)
    """
    errors = []
    try:
        if not jsonl_path.exists():
            return errors

        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get('event_type') == 'session_error':
                        errors.append(event)
                except json.JSONDecodeError:
                    continue

        return errors

    except Exception as e:
        logger.warning(f"Failed to check session errors for {jsonl_path}: {e}")
        return errors


def get_session_status(jsonl_path: Path) -> Tuple[str, Optional[str]]:
    """
    Get comprehensive session status from JSONL file.

    Checks for completion, errors, and termination status.

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        Tuple of (status, error_message) where:
        - status: "completed", "errored", "crashed", "incomplete", "missing"
        - error_message: Error details if applicable, None otherwise
    """
    try:
        if not jsonl_path.exists():
            return ("missing", None)

        has_session_end = False
        termination_reason = None
        errors = []
        last_round = 0

        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_type = event.get('event_type')

                    if event_type == 'session_end':
                        has_session_end = True
                        termination_reason = event.get('termination_reason', 'unknown')

                    elif event_type == 'session_error':
                        errors.append(event)

                    elif event_type == 'round_start':
                        last_round = max(last_round, event.get('round', 0))

                except json.JSONDecodeError:
                    continue

        # Determine status
        if has_session_end:
            if termination_reason == 'completed':
                return ("completed", None)
            elif termination_reason == 'interrupted':
                return ("crashed", f"Interrupted at round {last_round}")
            else:
                return ("completed", f"Ended: {termination_reason}")

        if errors:
            error_msg = errors[-1].get('error_message', 'Unknown error')
            return ("errored", error_msg)

        if last_round > 0:
            return ("incomplete", f"Stopped at round {last_round}")

        return ("incomplete", "No rounds started")

    except Exception as e:
        logger.warning(f"Failed to get session status for {jsonl_path}: {e}")
        return ("missing", str(e))


def get_last_successful_round(jsonl_path: Path) -> Optional[int]:
    """
    Find the last round that completed successfully.

    Since round_end events are not logged, we infer completion: if round N+1
    started (has round_start event), then round N must have completed.

    Used for replay-based resume: we replay up to round N-1 from cache,
    then continue live from round N.

    Args:
        jsonl_path: Path to partial session JSONL file

    Returns:
        Highest completed round number, or None if no rounds completed.
        (e.g., if max round_start is 5, returns 4 since round 5 is incomplete)
    """
    try:
        if not jsonl_path.exists():
            return None

        rounds_started = set()

        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get('event_type') == 'round_start':
                        round_num = event.get('round')
                        if round_num is not None:
                            rounds_started.add(round_num)
                except json.JSONDecodeError:
                    continue

        if not rounds_started:
            return None

        # If round N started, then round N-1 completed (assuming rounds are sequential)
        # If max started round is 1, then 0 rounds completed (round 1 is in progress)
        max_started = max(rounds_started)
        if max_started <= 1:
            return None  # Round 1 in progress, no completed rounds

        return max_started - 1

    except Exception as e:
        logger.warning(f"Failed to get last successful round for {jsonl_path}: {e}")
        return None


def count_llm_calls_in_jsonl(jsonl_path: Path) -> int:
    """
    Count number of LLM calls logged in JSONL (needed for replay validation).

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        Number of llm_call events found
    """
    try:
        if not jsonl_path.exists():
            return 0

        count = 0
        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get('event_type') == 'llm_call':
                        count += 1
                except json.JSONDecodeError:
                    continue

        return count

    except Exception as e:
        logger.warning(f"Failed to count LLM calls for {jsonl_path}: {e}")
        return 0


def try_replay_session(
    partial_jsonl: Path,
    output_path: Path,
    continue_from_round: int,
    timeout: int = 90000
) -> Tuple[bool, Optional[str]]:
    """
    Attempt to resume a failed session using replay with cached LLM calls.

    Uses replay_fixture.py with --all-cached and --cache-until-round to
    replay rounds 0 to N deterministically from cache (all agents), then
    continue live from round N+1 (all agents make new LLM calls).

    This saves API costs proportional to how far the session got before failing.
    E.g., if session failed at round 10, replaying rounds 0-9 from cache saves
    ~90% of the API cost for those rounds.

    Args:
        partial_jsonl: Path to the partial session JSONL (has cached LLM calls)
        output_path: Path for the resumed session output
        continue_from_round: Cache rounds 0 to N, go live from N+1
        timeout: Subprocess timeout in seconds

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Validate we have enough LLM calls cached for replay
        llm_call_count = count_llm_calls_in_jsonl(partial_jsonl)
        if llm_call_count < 3:  # Minimum: at least scenario + 1 round
            return False, f"Insufficient LLM calls for replay ({llm_call_count} found)"

        # Build replay command
        # Use --all-cached with --cache-until-round: ALL agents cached for rounds 0-N,
        # then ALL agents go live from round N+1. This is the correct behavior for
        # resuming a failed session (deterministic replay of completed rounds, then
        # continue live).
        # Note: --cache-player-actions would filter out DM calls, causing cache misses
        # when HybridLLMClient tries to use cache for DM in rounds 0-N.
        cmd = [
            sys.executable,
            "scripts/replay_fixture.py",
            str(partial_jsonl),
            "--all-cached",  # All agents cached (players, enemies, AND DM)
            "--cache-until-round", str(continue_from_round),
            "--output", str(output_path)
        ]

        logger.info(f"  🔄 Attempting replay (all agents cached rounds 0-{continue_from_round}, all live from {continue_from_round + 1})")

        # Run replay
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0:
            # Verify output was created and has session_end
            if output_path.exists() and check_session_completed(output_path):
                return True, None
            else:
                return False, "Replay completed but output missing session_end"
        else:
            error_snippet = result.stderr[-300:] if result.stderr else "No error output"
            return False, f"Replay failed (exit {result.returncode}): {error_snippet}"

    except subprocess.TimeoutExpired:
        return False, f"Replay timeout (>{timeout}s)"
    except Exception as e:
        return False, f"Replay exception: {e}"


def extract_session_stats(jsonl_path: Path) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract statistics from session JSONL output.

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        Tuple of (total_tokens, total_rounds)
    """
    try:
        if not jsonl_path.exists():
            return None, None

        total_tokens = 0
        max_round = 0

        with open(jsonl_path, 'r') as f:
            for line in f:
                event = json.loads(line)

                # Count tokens from llm_call events
                if event.get('event_type') == 'llm_call':
                    tokens = event.get('tokens', {})
                    total_tokens += tokens.get('total', 0)

                # Track max round number
                round_num = event.get('round')
                if round_num is not None and round_num > max_round:
                    max_round = round_num

        return total_tokens, max_round

    except Exception as e:
        logger.warning(f"Failed to extract stats from {jsonl_path}: {e}")
        return None, None


def get_completed_runs(output_dir: Path) -> set:
    """
    Get set of run IDs that have already completed successfully.

    Uses session_end event as authoritative completion marker, not just
    file existence.

    Args:
        output_dir: Output directory (bulk run directory)

    Returns:
        Set of completed run IDs
    """
    completed = set()
    if not output_dir.exists():
        return completed

    # Scan for run_NNNN subdirectories with session_*.jsonl
    for run_subdir in output_dir.glob("run_*"):
        if not run_subdir.is_dir():
            continue

        # Find actual JSONL file (uses UUID in filename)
        jsonl_files = list(run_subdir.glob("session_*.jsonl"))
        if not jsonl_files:
            continue

        # Check if session actually completed (has session_end event)
        jsonl_file = jsonl_files[0]
        if check_session_completed(jsonl_file):
            # Extract run ID from directory name
            try:
                run_id = int(run_subdir.name.split('_')[-1])
                completed.add(run_id)
            except (ValueError, IndexError):
                pass

    return completed


def write_bulk_run_metadata(
    output_dir: Path,
    config_paths: List[str],
    runs_per_config: int,
    args: argparse.Namespace
) -> None:
    """
    Write metadata at bulk run start for resume capability.

    This file is written BEFORE any sessions run, so resume always has
    access to the original configuration even if the run was interrupted.

    Args:
        output_dir: Bulk run output directory
        config_paths: List of original config file paths
        runs_per_config: Number of runs per config
        args: Parsed command-line arguments
    """
    metadata = {
        'config_paths': config_paths,
        'runs_per_config': runs_per_config,
        'total_runs': len(config_paths) * runs_per_config,
        'workers': args.workers,
        'proxy_url': args.proxy,
        'log_level': args.log_level,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    metadata_path = output_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.debug(f"Wrote bulk run metadata to {metadata_path}")


def load_bulk_run_metadata(output_dir: Path) -> Optional[Dict]:
    """
    Load metadata from existing bulk run directory.

    Args:
        output_dir: Bulk run output directory

    Returns:
        Metadata dict or None if not found
    """
    metadata_path = output_dir / 'metadata.json'
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            return json.load(f)
    return None


def discover_run_metadata_from_dirs(output_dir: Path) -> Tuple[int, List[Tuple[Path, int]]]:
    """
    Discover total runs and incomplete run configs from existing run directories.

    Used as fallback when metadata.json doesn't exist (older bulk runs).
    Total runs = highest run_NNNN directory number found.

    Args:
        output_dir: Bulk run output directory

    Returns:
        Tuple of (total_runs, list of (config_path, run_id) for incomplete runs)
    """
    max_run_id = 0
    incomplete_runs = []

    for run_dir in sorted(output_dir.glob("run_*")):
        if not run_dir.is_dir():
            continue

        # Extract run ID from directory name
        try:
            run_id = int(run_dir.name.split('_')[-1])
            max_run_id = max(max_run_id, run_id)
        except (ValueError, IndexError):
            continue

        config_path = run_dir / "config.json"
        if not config_path.exists():
            # No config - can't resume this run, but still count it toward total
            continue

        # Check if incomplete
        jsonl_files = list(run_dir.glob("session_*.jsonl"))
        if jsonl_files and check_session_completed(jsonl_files[0]):
            continue  # Skip completed

        incomplete_runs.append((config_path, run_id))

    if max_run_id == 0:
        raise ValueError(f"No run directories found in {output_dir}")

    return max_run_id, incomplete_runs


def calculate_bulk_stats(results: List[RunResult]) -> BulkRunStats:
    """
    Calculate aggregated statistics from run results.

    Args:
        results: List of RunResult instances

    Returns:
        BulkRunStats with aggregated metrics
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    total_duration = sum(r.duration_seconds for r in results)
    total_tokens = sum(r.total_tokens for r in successful if r.total_tokens)

    avg_duration = total_duration / len(results) if results else 0
    avg_tokens = total_tokens / len(successful) if successful else 0

    # Calculate throughput (runs per hour)
    if total_duration > 0:
        runs_per_hour = (len(results) / total_duration) * 3600
    else:
        runs_per_hour = 0

    return BulkRunStats(
        total_runs=len(results),
        successful_runs=len(successful),
        failed_runs=len(failed),
        skipped_runs=0,  # Filled in by caller
        total_duration_seconds=total_duration,
        avg_duration_seconds=avg_duration,
        total_tokens=total_tokens,
        avg_tokens_per_run=avg_tokens,
        runs_per_hour=runs_per_hour
    )


def write_summary_report(
    output_dir: Path,
    results: List[RunResult],
    stats: BulkRunStats,
    args: argparse.Namespace
):
    """
    Write summary report to JSON file.

    Args:
        output_dir: Output directory (bulk run directory)
        results: List of run results
        stats: Bulk run statistics
        args: Command-line arguments
    """
    report_path = output_dir / "summary.json"

    # Determine config paths
    if hasattr(args, 'configs') and args.configs:
        config_paths = [str(p) for p in args.configs]
    elif args.config:
        config_paths = [args.config]
    else:
        config_paths = []

    # Analyze session errors from JSONL files
    errored_runs = []
    for result in results:
        if not result.success and result.output_path and result.output_path != "N/A":
            jsonl_path = Path(result.output_path)
            if jsonl_path.exists():
                errors = check_session_errors(jsonl_path)
                if errors:
                    errored_runs.append({
                        'run_id': result.run_id,
                        'error_type': errors[-1].get('error_type'),
                        'error_message': errors[-1].get('error_message'),
                        'exception_type': errors[-1].get('exception_type'),
                        'context': errors[-1].get('context', {})
                    })

    # Aggregate the mechanical-integrity quarantine across the batch.
    quarantined = [r for r in results if getattr(r, 'quarantined', False)]
    inv_tally: Dict[str, int] = {}
    for r in quarantined:
        for v in (r.violations or []):
            inv_tally[v['invariant']] = inv_tally.get(v['invariant'], 0) + 1

    report = {
        'metadata': {
            'command': ' '.join(sys.argv),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'config_paths': config_paths,
            'total_requested_runs': args.runs,
            'workers': args.workers,
            'proxy_url': args.proxy,
            'resumed': args.resume
        },
        'statistics': asdict(stats),
        'quarantine': {
            'quarantined_runs': len(quarantined),
            'invariant_tally': inv_tally,
            'run_ids': [r.run_id for r in quarantined],
        } if quarantined else None,
        'runs': [asdict(r) for r in results],
        'errored_sessions': errored_runs if errored_runs else None
    }

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Summary report written to: {report_path}")

    # Standalone quarantine manifest — the exclude-list for downstream analysis.
    if quarantined:
        manifest_path = output_dir / "invariant_quarantine.json"
        with open(manifest_path, 'w') as f:
            json.dump({
                'quarantined_runs': len(quarantined),
                'total_runs': len(results),
                'invariant_tally': inv_tally,
                'sessions': [{'run_id': r.run_id, 'output_path': r.output_path,
                              'violations': r.violations} for r in quarantined],
            }, f, indent=2)
        logger.warning(
            f"QUARANTINE: {len(quarantined)}/{len(results)} completed sessions failed "
            f"mechanical-integrity checks -> {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Run multiple Aeonisk YAGS sessions in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Required arguments
    parser.add_argument(
        '--config',
        type=str,
        help='Path to session config JSON'
    )
    parser.add_argument(
        '--configs',
        type=str,
        nargs='+',
        action='extend',
        help='Multiple config paths (alternative to --config). Can repeat: --configs a.json --configs b.json'
    )
    parser.add_argument(
        '--runs',
        type=int,
        default=1,
        help='Number of runs to execute (default: 1)'
    )
    parser.add_argument(
        '--runs-per-config',
        type=int,
        help='Runs per config when using --configs (overrides --runs)'
    )

    # Optional arguments
    parser.add_argument(
        '--output-dir',
        type=str,
        default='bulk_output',
        help='Output directory for JSONL files (default: bulk_output)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers (default: 4)'
    )
    parser.add_argument(
        '--proxy',
        type=str,
        help='Proxy server URL (e.g., http://localhost:8000)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume previous run, skip completed sessions. Requires --run-dir. '
             'By default, uses replay with cached LLM calls (saves API cost). '
             'Use --no-replay to disable and restart from scratch.'
    )
    parser.add_argument(
        '--no-replay',
        action='store_true',
        help='When resuming, skip replay and restart failed sessions from scratch. '
             'Without this flag, --resume tries to replay using cached LLM calls first.'
    )
    parser.add_argument(
        '--run-dir',
        type=str,
        help='Existing run directory to resume (e.g., bulk_output/run_2025-11-28_212301_ff68f5ff)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=LOG_LEVEL_CHOICES,
        help='Log level for sessions (default: INFO)'
    )
    parser.add_argument(
        '--strategy',
        type=str,
        default=None,
        choices=list(PROXY_STRATEGY_CHOICES),
        help='Explicitly override each config\'s proxy_strategy '
             '(auto/direct/batch). When omitted, the strategy in each '
             'session config is honored — the runner never substitutes '
             'a default. Overrides are logged per agent.'
    )
    parser.add_argument(
        '--direct',
        action='store_true',
        help='Deprecated alias for --strategy direct.'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configs, print the effective per-agent LLM routing '
             'and run matrix, then exit without launching any session.'
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip session config preflight validation (not recommended)'
    )
    parser.add_argument(
        '--skip-health-check',
        action='store_true',
        help='Skip proxy health check'
    )
    parser.add_argument(
        '--progress',
        action='store_true',
        help='Show progress dashboard (updates only when state changes)'
    )
    parser.add_argument(
        '--progress-interval',
        type=float,
        default=10.0,
        help='Progress poll interval in seconds - only prints on change (default: 10)'
    )
    parser.add_argument(
        '--show-errors',
        action='store_true',
        help='Print stderr from failed runs immediately'
    )
    parser.add_argument(
        '--no-invariant-check',
        action='store_true',
        help='Skip the post-session mechanical-integrity gate '
             '(scripts/session_invariants.py). By default every completed session '
             'is checked and self-contradictory ones are quarantined.'
    )
    parser.add_argument(
        '--fail-on-invariant',
        action='store_true',
        help='Treat a quarantined (invariant-violating) session as a failed run '
             'rather than a completed-but-flagged one. Use in CI to hard-gate.'
    )
    parser.add_argument(
        '--session-timeout',
        type=int,
        default=90000,
        help='Session timeout in seconds (default: 90000 = 25 hours for batch API)'
    )
    parser.add_argument(
        '--regenerate-fixtures',
        action='store_true',
        help='Regenerate all test fixtures. Auto-discovers configs from '
             'scripts/session_configs/fixtures/openai/, runs each once with 9 workers, '
             'outputs to bulk_output/fixtures/. Shortcut for: '
             '--configs scripts/session_configs/fixtures/openai/*.json '
             '--runs-per-config 1 --workers 9 --output-dir bulk_output/fixtures --progress'
    )
    parser.add_argument(
        '--extract',
        action='store_true',
        help='Auto-extract fixtures after generation (use with --regenerate-fixtures). '
             'Reads _fixture_target from configs and extracts to tests/fixtures/sessions/.'
    )
    parser.add_argument(
        '--truncate',
        action='store_true',
        help='Force-truncate long string fields instead of retrying LLM calls. '
             'Saves tokens in bulk runs. Truncation events logged to stdout.log.'
    )

    args = parser.parse_args()

    # Handle --regenerate-fixtures shortcut
    if args.regenerate_fixtures:
        fixture_config_dir = Path(__file__).parent / "session_configs" / "fixtures" / "openai"
        fixture_configs = sorted(fixture_config_dir.glob("*.json"))

        if not fixture_configs:
            logger.error(f"No fixture configs found in {fixture_config_dir}")
            sys.exit(1)

        # Build fixture mapping (config -> target fixture)
        fixture_mapping = {}
        for config_path in fixture_configs:
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    target = config_data.get('_fixture_target', 'unknown')
                    rounds = config_data.get('max_turns', '?')
                    fixture_mapping[str(config_path)] = {
                        'target': target,
                        'rounds': rounds,
                        'config_name': config_path.name
                    }
            except Exception as e:
                fixture_mapping[str(config_path)] = {
                    'target': f'error: {e}',
                    'rounds': '?',
                    'config_name': config_path.name
                }

        # Store mapping for later use
        args._fixture_mapping = fixture_mapping

        # Override args with fixture defaults
        args.configs = [str(c) for c in fixture_configs]
        args.runs_per_config = 1
        args.workers = min(len(fixture_configs), 9)  # Cap at 9 or number of configs
        args.output_dir = "bulk_output/fixtures"
        args.progress = True
        args.config = None  # Clear single config if set

        logger.info(f"=== FIXTURE REGENERATION MODE ===")
        logger.info(f"Found {len(fixture_configs)} fixture configs:")
        for i, c in enumerate(fixture_configs, 1):
            info = fixture_mapping.get(str(c), {})
            target = Path(info.get('target', 'unknown')).name
            rounds = info.get('rounds', '?')
            logger.info(f"  [{i:02d}] {c.name}")
            logger.info(f"       -> {target} ({rounds} rounds)")

    # Validate arguments
    if args.resume:
        # Resume mode: --run-dir required, --config optional (will load from metadata)
        if not args.run_dir:
            parser.error("--resume requires --run-dir to specify which run to resume")
    elif not args.regenerate_fixtures:
        # Normal mode: --config or --configs required (unless using --regenerate-fixtures)
        if not args.config and not args.configs:
            parser.error("Must provide either --config, --configs, or --regenerate-fixtures")

    # Resolve proxy strategy from explicit flags only. None means "honor
    # each config's own proxy_strategy" — the runner must never substitute
    # a default for a value the config already chose.
    if args.direct and args.strategy and args.strategy != 'direct':
        parser.error(f"--direct conflicts with --strategy {args.strategy}")
    proxy_strategy = 'direct' if args.direct else args.strategy

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    if args.direct:
        logger.warning("--direct is deprecated; use --strategy direct")

    # Import UUID and datetime for directory naming
    import uuid
    from datetime import datetime

    # Initialize variables
    config_paths: List[Path] = []
    runs_per_config: int = 0
    resume_tasks: Optional[List[Tuple[Path, int]]] = None  # For resume mode fallback

    if args.resume:
        # Resume mode: load config info from existing run directory
        output_dir = Path(args.run_dir)
        if not output_dir.exists():
            logger.error(f"Run directory not found: {output_dir}")
            sys.exit(1)
        bulk_run_name = output_dir.name
        logger.info(f"Resuming run: {bulk_run_name}")

        # Try to load metadata.json
        metadata = load_bulk_run_metadata(output_dir)

        if metadata:
            # Use stored config paths (unless overridden by command line)
            if args.config or args.configs:
                # User provided config override - use those
                if args.configs:
                    config_paths = [Path(c) for c in args.configs]
                    runs_per_config = args.runs_per_config or args.runs
                else:
                    config_paths = [Path(args.config)]
                    runs_per_config = args.runs
                logger.info(f"Using command-line config override")
            else:
                # Use configs from metadata
                config_paths = [Path(c) for c in metadata['config_paths']]
                runs_per_config = metadata['runs_per_config']
                logger.info(f"Loaded config from metadata.json: {metadata['config_paths']}")
        else:
            # Fallback: discover from run directories (older bulk runs without metadata.json)
            if args.config or args.configs:
                # User provided config - use it
                if args.configs:
                    config_paths = [Path(c) for c in args.configs]
                    runs_per_config = args.runs_per_config or args.runs
                else:
                    config_paths = [Path(args.config)]
                    runs_per_config = args.runs
                logger.info(f"Using command-line config (no metadata.json found)")
            else:
                # Discover from run directories
                logger.info("No metadata.json found, discovering from run directories...")
                try:
                    total_runs, incomplete_runs = discover_run_metadata_from_dirs(output_dir)
                    # Use discovered incomplete runs directly as tasks
                    resume_tasks = incomplete_runs
                    # Set dummy values for config_paths/runs_per_config (won't be used)
                    config_paths = []
                    runs_per_config = total_runs
                    logger.info(f"Discovered {len(incomplete_runs)} incomplete runs out of {total_runs} total")
                except ValueError as e:
                    logger.error(f"Failed to discover run metadata: {e}")
                    sys.exit(1)

        # Validate configs exist (if we have paths to validate)
        for config_path in config_paths:
            if not config_path.exists():
                logger.error(f"Config file not found: {config_path}")
                sys.exit(1)

        # Preflight: validation + effective routing banner
        if config_paths and not preflight_configs(
                config_paths, args.proxy, proxy_strategy,
                args.skip_validation):
            sys.exit(1)

        if args.dry_run:
            logger.info("DRY RUN: resume preflight complete, exiting "
                        "without launching sessions")
            sys.exit(0)

    else:
        # Normal mode: use command-line configs
        if args.configs:
            config_paths = [Path(c) for c in args.configs]
            runs_per_config = args.runs_per_config or args.runs
        else:
            config_paths = [Path(args.config)]
            runs_per_config = args.runs

        # Validate configs exist
        for config_path in config_paths:
            if not config_path.exists():
                logger.error(f"Config file not found: {config_path}")
                sys.exit(1)

        # Preflight: validation + effective routing banner (before any
        # directories are created, so --dry-run is side-effect free)
        if not preflight_configs(config_paths, args.proxy, proxy_strategy,
                                 args.skip_validation):
            sys.exit(1)

        if args.dry_run:
            logger.info(
                f"DRY RUN: would launch {len(config_paths) * runs_per_config} "
                f"session(s) ({len(config_paths)} config(s) × "
                f"{runs_per_config} run(s)) across {args.workers} workers "
                f"into {args.output_dir}/")
            sys.exit(0)

        # Create new timestamped bulk run directory
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        run_uuid = str(uuid.uuid4())[:8]  # Short UUID
        bulk_run_name = f"run_{timestamp}_{run_uuid}"

        base_output_dir = Path(args.output_dir)
        output_dir = base_output_dir / bulk_run_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata.json for future resume capability
        write_bulk_run_metadata(
            output_dir,
            [str(c) for c in config_paths],
            runs_per_config,
            args
        )

        logger.info(f"Bulk run ID: {bulk_run_name}")

    # Check proxy health if enabled
    if args.proxy and not args.skip_health_check:
        logger.info(f"Checking proxy health: {args.proxy}")
        is_healthy, status_msg = check_proxy_health(args.proxy)
        if not is_healthy:
            logger.error(f"Proxy health check failed: {status_msg}")
            logger.error("Use --skip-health-check to bypass, or start proxy server first")
            sys.exit(1)
        logger.info(f"✓ {status_msg}")

    # Generate run tasks
    # Task format: (config_path, run_id, use_stored_config)
    tasks: List[Tuple[str, int, bool]] = []
    skipped_count = 0

    if resume_tasks is not None:
        # Fallback resume mode: use discovered incomplete runs directly
        # These already have stored configs at run_NNNN/config.json
        for config_path, run_id in resume_tasks:
            tasks.append((str(config_path), run_id, True))  # use_stored_config=True
        skipped_count = runs_per_config - len(resume_tasks)
        if skipped_count > 0:
            logger.info(f"Resuming: skipping {skipped_count} completed runs (discovered)")
    else:
        # Normal task generation from config_paths
        # Interleave configs (round-robin) so workers run diverse models concurrently.
        # With configs [A, B, C] × 3 runs each, task order is: A1, B1, C1, A2, B2, C2, ...
        # This ensures workers pick up different models before doubling up on one.
        for run_offset in range(runs_per_config):
            for config_path in config_paths:
                run_id = len(tasks) + 1
                tasks.append((str(config_path), run_id, False))  # use_stored_config=False

        # Check for resume (when we have config paths from metadata or command line)
        if args.resume:
            completed_runs = get_completed_runs(output_dir)
            original_count = len(tasks)
            tasks = [(c, r, s) for c, r, s in tasks if r not in completed_runs]
            skipped_count = original_count - len(tasks)
            if skipped_count > 0:
                logger.info(f"Resuming: skipping {skipped_count} completed runs")

    total_runs = len(tasks)
    logger.info(f"Starting bulk run: {total_runs} sessions across {args.workers} workers")
    logger.info(f"Output directory: {output_dir}")
    if args.proxy:
        logger.info(f"Proxy URL: {args.proxy} "
                    f"(strategy: {proxy_strategy or 'per-config'})")
    if args.resume and not args.no_replay:
        logger.info(f"🔄 Replay enabled: will try cached LLM replay before fresh restart")
    elif args.resume and args.no_replay:
        logger.info(f"⏭️  Replay disabled: will restart failed sessions from scratch")
    if args.progress:
        logger.info(f"Progress dashboard enabled (updates on change, polls every {args.progress_interval}s)")

    # Execute runs in parallel
    start_time = time.time()
    results = []

    # Start progress monitor if enabled
    progress_monitor = None
    if args.progress:
        progress_monitor = ProgressMonitor(
            output_dir=output_dir,
            total_runs=total_runs,
            refresh_interval=args.progress_interval,
            bulk_run_name=bulk_run_name
        )
        progress_monitor.start()

    try:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            # Submit all tasks
            # Note: attempt_replay is only meaningful when resuming incomplete sessions
            # Replay is enabled by default when resuming, unless --no-replay is specified
            attempt_replay = args.resume and not args.no_replay
            force_truncate = getattr(args, 'truncate', False)
            # Build model lookup for logging and submit tasks
            task_models: Dict[Tuple[str, int], str] = {}
            futures = {}
            for config_path, run_id, use_stored_config in tasks:
                model = extract_model_from_config(config_path)
                task_models[(config_path, run_id)] = model
                logger.info(f"Launching run {run_id} ({model})")
                future = executor.submit(
                    run_single_session,
                    config_path,
                    run_id,
                    output_dir,
                    args.proxy,
                    args.log_level,
                    use_stored_config,
                    args.session_timeout,
                    attempt_replay,
                    proxy_strategy,
                    force_truncate,
                    not args.no_invariant_check,
                    args.fail_on_invariant
                )
                futures[future] = (config_path, run_id)

            # Process completed runs
            for i, future in enumerate(as_completed(futures), 1):
                config_path, run_id = futures[future]

                try:
                    result = future.result()
                    results.append(result)

                    # Update progress monitor
                    if progress_monitor:
                        if result.success:
                            progress_monitor.mark_completed(result.run_id, result.duration_seconds)
                        else:
                            progress_monitor.mark_failed(result.run_id, result.duration_seconds)

                    model = task_models.get((config_path, run_id), 'unknown')
                    if result.success:
                        logger.info(
                            f"[{i}/{total_runs}] ✓ Run {result.run_id} completed "
                            f"({model}, {result.duration_seconds:.1f}s, "
                            f"{result.total_tokens or 0} tokens, "
                            f"{result.total_rounds or 0} rounds)"
                        )
                    else:
                        logger.error(
                            f"[{i}/{total_runs}] ✗ Run {result.run_id} failed "
                            f"({model}): "
                            f"{result.error[:100] if result.error else 'Unknown error'}"
                        )

                        # Print full error if --show-errors flag set
                        if args.show_errors and result.error:
                            print(f"\n{'='*80}")
                            print(f"STDERR from run {result.run_id}:")
                            print(f"{'='*80}")
                            print(result.error)
                            print(f"{'='*80}\n")

                except Exception as e:
                    logger.error(f"[{i}/{total_runs}] ✗ Run {run_id} exception: {e}")
                    if progress_monitor:
                        progress_monitor.mark_failed(run_id)
                    results.append(RunResult(
                        run_id=run_id,
                        config_path=config_path,
                        output_path="N/A",
                        success=False,
                        duration_seconds=0,
                        error=str(e)
                    ))

    finally:
        # Stop progress monitor
        if progress_monitor:
            progress_monitor.stop()

        # Always write summary report (even on Ctrl+C) if we have any results
        if results:
            total_duration = time.time() - start_time
            stats = calculate_bulk_stats(results)
            stats.skipped_runs = skipped_count  # Set from resume logic (0 if not resuming)

            # Print summary
            print("\n" + "="*80)
            print("BULK RUN SUMMARY")
            print("="*80)
            print(f"Total Runs:      {stats.total_runs}")
            if stats.total_runs > 0:
                print(f"Successful:      {stats.successful_runs} ({stats.successful_runs/stats.total_runs*100:.1f}%)")
            else:
                print(f"Successful:      {stats.successful_runs}")
            print(f"Failed:          {stats.failed_runs}")
            if stats.skipped_runs > 0:
                print(f"Skipped:         {stats.skipped_runs} (resumed)")
            print(f"Total Duration:  {total_duration:.1f}s ({total_duration/60:.1f}m)")
            print(f"Avg Duration:    {stats.avg_duration_seconds:.1f}s per run")
            print(f"Throughput:      {stats.runs_per_hour:.1f} runs/hour")
            print(f"Total Tokens:    {stats.total_tokens:,}")
            print(f"Avg Tokens:      {stats.avg_tokens_per_run:.0f} per run")
            print("="*80)

            # If fixture regeneration mode, print extraction commands
            if hasattr(args, '_fixture_mapping') and args._fixture_mapping:
                print("\n" + "="*80)
                print("FIXTURE EXTRACTION COMMANDS")
                print("="*80)
                print(f"Run directory: {output_dir}\n")

                # Build run_id -> config mapping from results
                for result in sorted(results, key=lambda r: r.run_id):
                    if result.success:
                        config_path = result.config_path
                        info = args._fixture_mapping.get(config_path, {})
                        target = info.get('target', 'unknown')

                        # Read actual session to find real round range
                        max_round = '?'
                        try:
                            session_path = Path(result.output_path)
                            if session_path.exists():
                                with open(session_path, 'r') as f:
                                    rounds_seen = set()
                                    for line in f:
                                        try:
                                            event = json.loads(line)
                                            r = event.get('round')
                                            if r is not None and isinstance(r, int):
                                                rounds_seen.add(r)
                                        except json.JSONDecodeError:
                                            pass
                                    if rounds_seen:
                                        max_round = max(rounds_seen)
                        except Exception:
                            # Fall back to config value
                            config_rounds = info.get('rounds', '?')
                            max_round = config_rounds - 1 if isinstance(config_rounds, int) else '?'

                        print(f"# Run {result.run_id:02d}: {info.get('config_name', 'unknown')}")
                        print(f"python scripts/extract_fixture.py \\")
                        print(f"  {result.output_path} \\")
                        print(f"  --rounds 0-{max_round} \\")
                        print(f"  --output {target}")
                        print()
                    else:
                        config_path = result.config_path
                        info = args._fixture_mapping.get(config_path, {})
                        print(f"# Run {result.run_id:02d}: {info.get('config_name', 'unknown')} - FAILED")
                        print()

                print("# Validate all fixtures:")
                print("python scripts/analyze_session.py tests/fixtures/sessions/*.jsonl --validate-fixture")
                print("="*80)

                # Auto-extract if --extract flag is set
                if args.extract:
                    print("\n" + "="*80)
                    print("AUTO-EXTRACTING FIXTURES")
                    print("="*80 + "\n")

                    extract_script = Path(__file__).parent / "extract_fixture.py"
                    extracted_count = 0
                    failed_extracts = []

                    for result in sorted(results, key=lambda r: r.run_id):
                        if not result.success:
                            continue

                        config_path = result.config_path
                        info = args._fixture_mapping.get(config_path, {})
                        target = info.get('target', None)

                        if not target or target == 'unknown':
                            logger.warning(f"Run {result.run_id}: No _fixture_target in config, skipping extraction")
                            continue

                        # Find actual max round in session
                        max_round = 0
                        try:
                            session_path = Path(result.output_path)
                            if session_path.exists():
                                with open(session_path, 'r') as f:
                                    for line in f:
                                        try:
                                            event = json.loads(line)
                                            r = event.get('round')
                                            if r is not None and isinstance(r, int):
                                                max_round = max(max_round, r)
                                        except json.JSONDecodeError:
                                            pass
                        except Exception as e:
                            logger.warning(f"Run {result.run_id}: Could not read session for round detection: {e}")
                            continue

                        # Run extraction
                        cmd = [
                            sys.executable, str(extract_script),
                            result.output_path,
                            "--rounds", f"0-{max_round}",
                            "--output", target,
                            "--overwrite"
                        ]

                        logger.info(f"Extracting: {Path(target).name} (rounds 0-{max_round})")
                        try:
                            extract_result = subprocess.run(
                                cmd,
                                capture_output=True,
                                text=True,
                                timeout=60
                            )
                            if extract_result.returncode == 0:
                                extracted_count += 1
                                print(f"  ✓ {Path(target).name}")
                            else:
                                failed_extracts.append((target, extract_result.stderr[:200]))
                                print(f"  ✗ {Path(target).name}: {extract_result.stderr[:100]}")
                        except Exception as e:
                            failed_extracts.append((target, str(e)))
                            print(f"  ✗ {Path(target).name}: {e}")

                    print(f"\nExtracted: {extracted_count}/{len([r for r in results if r.success])} fixtures")

                    if failed_extracts:
                        print(f"Failed: {len(failed_extracts)}")
                        for target, err in failed_extracts:
                            print(f"  - {Path(target).name}: {err[:80]}")

                    # Run validation
                    print("\n" + "-"*40)
                    print("VALIDATING FIXTURES")
                    print("-"*40)
                    analyze_script = Path(__file__).parent / "analyze_session.py"
                    validate_result = subprocess.run(
                        [sys.executable, str(analyze_script), "--validate-fixtures"],
                        capture_output=False
                    )
                    print("="*80)

            # Write summary report (persists even on early termination)
            write_summary_report(output_dir, results, stats, args)

    # Exit with error code if any runs failed (only reached on normal completion)
    if results and any(not r.success for r in results):
        failed_count = sum(1 for r in results if not r.success)
        logger.warning(f"{failed_count} runs failed, see summary report for details")
        sys.exit(1)

    if results:
        logger.info("All runs completed successfully!")


if __name__ == "__main__":
    main()
