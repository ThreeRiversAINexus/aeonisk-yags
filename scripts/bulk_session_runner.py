#!/usr/bin/env python3
"""
Bulk Session Runner for Aeonisk YAGS

Runs multiple multi-agent sessions in parallel using subprocess orchestration.
Designed for bulk generation with batch proxy support for cost optimization.

Features:
- Parallel execution via ProcessPoolExecutor
- Automatic proxy health check before execution
- Resume capability for failed runs (based on session_end event in JSONL)
- Real-time progress dashboard
- Aggregated statistics and reporting
- Per-run output isolation (prevents JSONL collisions)

Usage:
    # Basic usage (run same config 10 times with 4 workers)
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 10 \\
        --workers 4

    # With progress dashboard (updates every 10s)
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

    # Resume failed runs from existing directory (no --config needed!)
    python scripts/bulk_session_runner.py \\
        --resume \\
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

Options:
    --config FILE           Session config JSON file (not required with --resume)
    --configs FILE [FILE]   Multiple config files (not required with --resume)
    --runs N                Number of runs (default: 1)
    --runs-per-config N     Runs per config (with --configs)
    --workers N             Parallel workers (default: 4)
    --output-dir DIR        Output directory (default: bulk_output/)
    --proxy URL             Batch proxy URL (e.g., http://localhost:8000)
    --resume                Resume from --run-dir, skip completed sessions.
                            Config loaded from metadata.json in run directory.
    --run-dir DIR           Existing run directory for --resume
    --progress              Show real-time progress dashboard
    --progress-interval N   Progress update interval in seconds (default: 10)
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
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class ProgressMonitor:
    """
    Monitor and display progress of running sessions.

    Periodically scans JSONL files to show:
    - Current round for each session
    - Number of LLM calls made
    - Session status (running/complete/failed)
    """

    def __init__(self, output_dir: Path, total_runs: int, refresh_interval: float = 5.0):
        self.output_dir = output_dir
        self.total_runs = total_runs
        self.refresh_interval = refresh_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._completed_runs: Set[int] = set()
        self._failed_runs: Set[int] = set()

    def start(self):
        """Start the progress monitor thread."""
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the progress monitor thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def mark_completed(self, run_id: int):
        """Mark a run as completed."""
        self._completed_runs.add(run_id)

    def mark_failed(self, run_id: int):
        """Mark a run as failed."""
        self._failed_runs.add(run_id)

    def _monitor_loop(self):
        """Main monitoring loop."""
        while not self._stop_event.wait(self.refresh_interval):
            try:
                self._display_progress()
            except Exception as e:
                logger.debug(f"Progress monitor error: {e}")

    def _display_progress(self):
        """Scan JSONL files and display current progress."""
        progress_lines = []

        for run_id in range(1, self.total_runs + 1):
            run_dir = self.output_dir / f"run_{run_id:04d}"

            if run_id in self._completed_runs:
                status = "✓ DONE"
                round_info = ""
            elif run_id in self._failed_runs:
                status = "✗ FAIL"
                round_info = ""
            elif not run_dir.exists():
                status = "⏳ pending"
                round_info = ""
            else:
                # Scan JSONL for progress
                jsonl_files = list(run_dir.glob("session_*.jsonl"))
                if jsonl_files:
                    stats = self._get_session_progress(jsonl_files[0])
                    status = "▶ running"
                    round_info = f"R{stats['round']:02d} | {stats['llm_calls']:3d} calls | {stats['actions']:3d} actions"
                else:
                    status = "▶ starting"
                    round_info = ""

            progress_lines.append(f"  [{run_id:02d}] {status:12s} {round_info}")

        # Build display
        completed = len(self._completed_runs)
        failed = len(self._failed_runs)
        running = self.total_runs - completed - failed

        header = (
            f"\n{'='*70}\n"
            f"PROGRESS: {completed}/{self.total_runs} complete | "
            f"{running} running | {failed} failed | "
            f"{datetime.now().strftime('%H:%M:%S')}\n"
            f"{'='*70}"
        )

        print(header)
        for line in progress_lines:
            print(line)
        print(f"{'='*70}\n")

    def _get_session_progress(self, jsonl_path: Path) -> Dict:
        """Extract progress stats from JSONL file."""
        stats = {'round': 0, 'llm_calls': 0, 'actions': 0}

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


def modify_config_for_bulk_run(
    config: Dict,
    run_id: int,
    output_path: str,
    proxy_url: Optional[str] = None
) -> Dict:
    """
    Modify session config for bulk run.

    Args:
        config: Original session config
        run_id: Unique run identifier
        output_path: Output JSONL path for this run
        proxy_url: Optional proxy URL to inject

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

    # If proxy_url provided, inject into all agent LLM configs
    if proxy_url:
        modified = inject_proxy_config(modified, proxy_url)

    return modified


def inject_proxy_config(config: Dict, proxy_url: str) -> Dict:
    """
    Inject proxy configuration into all agents' LLM configs.

    Args:
        config: Session config dict
        proxy_url: Proxy server URL

    Returns:
        Modified config dict
    """
    # Inject into DM
    if 'agents' in config and 'dm' in config['agents']:
        dm_llm = config['agents']['dm'].get('llm', {})
        dm_llm['use_proxy'] = True
        dm_llm['proxy_url'] = proxy_url
        config['agents']['dm']['llm'] = dm_llm

    # Inject into players
    if 'agents' in config and 'players' in config['agents']:
        for player in config['agents']['players']:
            player_llm = player.get('llm', {})
            player_llm['use_proxy'] = True
            player_llm['proxy_url'] = proxy_url
            player['llm'] = player_llm

    return config


def run_single_session(
    config_path: str,
    run_id: int,
    output_dir: Path,
    proxy_url: Optional[str] = None,
    log_level: str = "INFO",
    use_stored_config: bool = False,
    session_timeout: int = 90000
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

    Returns:
        RunResult with execution details
    """
    start_time = time.time()

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
                config, run_id, str(output_path), proxy_url
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

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(actual_jsonl),
                success=True,
                duration_seconds=duration,
                total_tokens=total_tokens,
                total_rounds=total_rounds
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
    Check if session completed by looking for session_end event in JSONL.

    This is the authoritative check for session success - exit codes can be
    unreliable due to spurious shutdown errors (e.g., stdin lock issues).

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        True if session_end event found, False otherwise
    """
    try:
        if not jsonl_path.exists():
            return False

        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get('event_type') == 'session_end':
                        return True
                except json.JSONDecodeError:
                    continue

        return False

    except Exception as e:
        logger.warning(f"Failed to check session completion for {jsonl_path}: {e}")
        return False


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
        'runs': [asdict(r) for r in results]
    }

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Summary report written to: {report_path}")


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
        help='Multiple config paths (alternative to --config)'
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
        help='Resume previous run, skip completed sessions. Requires --run-dir.'
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
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'LLM', 'TRACE'],
        help='Log level for sessions (default: INFO)'
    )
    parser.add_argument(
        '--skip-health-check',
        action='store_true',
        help='Skip proxy health check'
    )
    parser.add_argument(
        '--progress',
        action='store_true',
        help='Show real-time progress dashboard (round, LLM calls, actions per session)'
    )
    parser.add_argument(
        '--progress-interval',
        type=float,
        default=10.0,
        help='Progress update interval in seconds (default: 10)'
    )
    parser.add_argument(
        '--show-errors',
        action='store_true',
        help='Print stderr from failed runs immediately'
    )
    parser.add_argument(
        '--session-timeout',
        type=int,
        default=90000,
        help='Session timeout in seconds (default: 90000 = 25 hours for batch API)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.resume:
        # Resume mode: --run-dir required, --config optional (will load from metadata)
        if not args.run_dir:
            parser.error("--resume requires --run-dir to specify which run to resume")
    else:
        # Normal mode: --config or --configs required
        if not args.config and not args.configs:
            parser.error("Must provide either --config or --configs")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

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
        for config_path in config_paths:
            for run_offset in range(runs_per_config):
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
        logger.info(f"Proxy URL: {args.proxy}")
    if args.progress:
        logger.info(f"Progress updates every {args.progress_interval}s (--progress enabled)")

    # Execute runs in parallel
    start_time = time.time()
    results = []

    # Start progress monitor if enabled
    progress_monitor = None
    if args.progress:
        progress_monitor = ProgressMonitor(
            output_dir=output_dir,
            total_runs=total_runs,
            refresh_interval=args.progress_interval
        )
        progress_monitor.start()

    try:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    run_single_session,
                    config_path,
                    run_id,
                    output_dir,
                    args.proxy,
                    args.log_level,
                    use_stored_config,
                    args.session_timeout
                ): (config_path, run_id)
                for config_path, run_id, use_stored_config in tasks
            }

            # Process completed runs
            for i, future in enumerate(as_completed(futures), 1):
                config_path, run_id = futures[future]

                try:
                    result = future.result()
                    results.append(result)

                    # Update progress monitor
                    if progress_monitor:
                        if result.success:
                            progress_monitor.mark_completed(result.run_id)
                        else:
                            progress_monitor.mark_failed(result.run_id)

                    if result.success:
                        logger.info(
                            f"[{i}/{total_runs}] ✓ Run {result.run_id} completed "
                            f"({result.duration_seconds:.1f}s, "
                            f"{result.total_tokens or 0} tokens, "
                            f"{result.total_rounds or 0} rounds)"
                        )
                    else:
                        logger.error(
                            f"[{i}/{total_runs}] ✗ Run {result.run_id} failed: "
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
