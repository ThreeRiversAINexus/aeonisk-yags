#!/usr/bin/env python3
"""
Bulk Session Runner for Aeonisk YAGS

Runs multiple multi-agent session in parallel using subprocess orchestration.
Designed for bulk generation with batch proxy support for cost optimization.

Features:
- Parallel execution via ProcessPoolExecutor
- Automatic proxy health check before execution
- Resume capability for failed runs
- Aggregated statistics and reporting
- Per-run output isolation (prevents JSONL collisions)

Usage:
    # Basic usage (run same config 100 times)
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 100 \\
        --output-dir bulk_output/

    # With proxy and parallel workers
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 100 \\
        --workers 20 \\
        --proxy http://localhost:8000 \\
        --output-dir bulk_output/

    # Resume failed runs
    python scripts/bulk_session_runner.py \\
        --config session_config.json \\
        --runs 100 \\
        --output-dir bulk_output/ \\
        --resume

    # Multiple configs
    python scripts/bulk_session_runner.py \\
        --configs session_config_1.json session_config_2.json \\
        --runs-per-config 50 \\
        --output-dir bulk_output/
"""

import os
import sys
import json
import time
import argparse
import logging
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


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
    log_level: str = "INFO"
) -> RunResult:
    """
    Run a single session via subprocess.

    Args:
        config_path: Path to session config JSON
        run_id: Unique run identifier
        output_dir: Output directory for JSONL
        proxy_url: Optional proxy URL
        log_level: Log level for session

    Returns:
        RunResult with execution details
    """
    start_time = time.time()

    # Load and modify config
    try:
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
                timeout=90000  # 25 hour timeout (batch API can take up to 24 hours)
            )

        duration = time.time() - start_time

        if result.returncode == 0:
            # Extract stats from output JSONL
            total_tokens, total_rounds = extract_session_stats(output_path)

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(output_path),
                success=True,
                duration_seconds=duration,
                total_tokens=total_tokens,
                total_rounds=total_rounds
            )
        else:
            # Read error from stderr log
            error_msg = "Unknown error"
            if stderr_log.exists():
                with open(stderr_log, 'r') as f:
                    stderr_content = f.read()
                    error_msg = stderr_content[-500:] if stderr_content else "No error message"

            return RunResult(
                run_id=run_id,
                config_path=config_path,
                output_path=str(output_path),
                success=False,
                duration_seconds=duration,
                error=error_msg
            )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return RunResult(
            run_id=run_id,
            config_path=config_path,
            output_path=str(output_path) if 'output_path' in locals() else "N/A",
            success=False,
            duration_seconds=duration,
            error="Session timeout (>25 hours)"
        )

    except Exception as e:
        duration = time.time() - start_time
        return RunResult(
            run_id=run_id,
            config_path=config_path,
            output_path=str(output_path) if 'output_path' in locals() else "N/A",
            success=False,
            duration_seconds=duration,
            error=str(e)
        )


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
    Get set of run IDs that have already completed.

    Args:
        output_dir: Output directory (bulk run directory)

    Returns:
        Set of completed run IDs
    """
    completed = set()
    if not output_dir.exists():
        return completed

    # Scan for run_NNNN subdirectories with session.jsonl
    for run_subdir in output_dir.glob("run_*"):
        if not run_subdir.is_dir():
            continue

        jsonl_file = run_subdir / "session.jsonl"
        if jsonl_file.exists():
            # Extract run ID from directory name
            try:
                run_id = int(run_subdir.name.split('_')[-1])
                completed.add(run_id)
            except (ValueError, IndexError):
                pass

    return completed


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
        help='Resume previous run, skip completed sessions'
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
        '--verbose',
        action='store_true',
        help='Show real-time session output (slower, for debugging)'
    )
    parser.add_argument(
        '--show-errors',
        action='store_true',
        help='Print stderr from failed runs immediately'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.config and not args.configs:
        parser.error("Must provide either --config or --configs")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Determine configs to run
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

    # Create timestamped bulk run directory
    import uuid
    from datetime import datetime

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    run_uuid = str(uuid.uuid4())[:8]  # Short UUID
    bulk_run_name = f"run_{timestamp}_{run_uuid}"

    base_output_dir = Path(args.output_dir)
    output_dir = base_output_dir / bulk_run_name
    output_dir.mkdir(parents=True, exist_ok=True)

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
    tasks = []
    for config_path in config_paths:
        for run_offset in range(runs_per_config):
            # Calculate global run ID
            run_id = len(tasks) + 1
            tasks.append((str(config_path), run_id))

    # Check for resume
    if args.resume:
        completed_runs = get_completed_runs(output_dir)
        tasks = [(c, r) for c, r in tasks if r not in completed_runs]
        skipped_count = len(config_paths) * runs_per_config - len(tasks)
        if skipped_count > 0:
            logger.info(f"Resuming: skipping {skipped_count} completed runs")

    total_runs = len(tasks)
    logger.info(f"Starting bulk run: {total_runs} sessions across {args.workers} workers")
    logger.info(f"Output directory: {output_dir}")
    if args.proxy:
        logger.info(f"Proxy URL: {args.proxy}")

    # Execute runs in parallel
    start_time = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(
                run_single_session,
                config_path,
                run_id,
                output_dir,
                args.proxy,
                args.log_level
            ): (config_path, run_id)
            for config_path, run_id in tasks
        }

        # Process completed runs
        for i, future in enumerate(as_completed(futures), 1):
            config_path, run_id = futures[future]

            try:
                result = future.result()
                results.append(result)

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
                        f"{result.error[:100]}"
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
                results.append(RunResult(
                    run_id=run_id,
                    config_path=config_path,
                    output_path="N/A",
                    success=False,
                    duration_seconds=0,
                    error=str(e)
                ))

    # Calculate statistics
    total_duration = time.time() - start_time
    stats = calculate_bulk_stats(results)
    if args.resume:
        stats.skipped_runs = len(config_paths) * runs_per_config - len(tasks)

    # Print summary
    print("\n" + "="*80)
    print("BULK RUN SUMMARY")
    print("="*80)
    print(f"Total Runs:      {stats.total_runs}")
    print(f"Successful:      {stats.successful_runs} ({stats.successful_runs/stats.total_runs*100:.1f}%)")
    print(f"Failed:          {stats.failed_runs}")
    if stats.skipped_runs > 0:
        print(f"Skipped:         {stats.skipped_runs} (resumed)")
    print(f"Total Duration:  {total_duration:.1f}s ({total_duration/60:.1f}m)")
    print(f"Avg Duration:    {stats.avg_duration_seconds:.1f}s per run")
    print(f"Throughput:      {stats.runs_per_hour:.1f} runs/hour")
    print(f"Total Tokens:    {stats.total_tokens:,}")
    print(f"Avg Tokens:      {stats.avg_tokens_per_run:.0f} per run")
    print("="*80)

    # Write summary report
    write_summary_report(output_dir, results, stats, args)

    # Exit with error code if any runs failed
    if stats.failed_runs > 0:
        logger.warning(f"{stats.failed_runs} runs failed, see summary report for details")
        sys.exit(1)

    logger.info("All runs completed successfully!")


if __name__ == "__main__":
    main()
