#!/usr/bin/env python3
"""
Run multiple Aeonisk sessions in parallel to evaluate success@n metrics.

Usage:
    python3 run_success_at_n.py [--config session_config.json] [--runs 10] [--parallel 4]

Examples:
    # Run 10 sessions with default config, 4 in parallel
    python3 run_success_at_n.py --runs 10 --parallel 4

    # Run 20 sessions with custom config
    python3 run_success_at_n.py --config custom_config.json --runs 20

    # Run with specific seed range
    python3 run_success_at_n.py --runs 5 --seed-start 1000
"""

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'aeonisk'))

from aeonisk.multiagent.success_metrics import (
    analyze_jsonl_log,
    calculate_success_at_n,
    format_metrics_report
)


def run_session(config_path: str, random_seed: int, output_dir: str = "./multiagent_output") -> Optional[str]:
    """
    Run a single session with specified config and seed.

    Args:
        config_path: Path to session configuration JSON
        random_seed: Random seed for reproducibility
        output_dir: Output directory for logs

    Returns:
        Session ID if successful, None otherwise
    """
    # Convert config path to absolute path
    config_path = str(Path(config_path).resolve())

    # Determine script directory
    script_dir = Path(__file__).parent.resolve()
    runner_script = script_dir / "run_multiagent_session.py"

    cmd = [
        sys.executable,  # Use same Python interpreter
        str(runner_script),
        config_path,
        "--random-seed", str(random_seed)
    ]

    try:
        print(f"  Starting session with seed {random_seed}...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per session
            cwd=str(script_dir)
        )

        if result.returncode == 0:
            # Extract session ID from output
            # Look for "Session ID: <uuid>" or session file path
            for line in result.stdout.split('\n'):
                if 'Session' in line and '.jsonl' in line:
                    # Extract session ID from path like "session_abc123.jsonl"
                    if 'session_' in line:
                        start = line.find('session_') + len('session_')
                        end = line.find('.jsonl', start)
                        if end > start:
                            session_id = line[start:end]
                            print(f"  ✓ Session {session_id[:8]} completed (seed: {random_seed})")
                            return session_id

            print(f"  ✓ Session completed (seed: {random_seed})")
            return f"seed_{random_seed}"  # Fallback ID

        else:
            print(f"  ✗ Session failed with seed {random_seed}")
            print(f"    Error: {result.stderr[:200]}")
            return None

    except subprocess.TimeoutExpired:
        print(f"  ✗ Session timed out (seed: {random_seed})")
        return None
    except Exception as e:
        print(f"  ✗ Session failed (seed: {random_seed}): {e}")
        return None


async def run_sessions_parallel(
    config_path: str,
    num_runs: int,
    max_parallel: int,
    seed_start: int,
    output_dir: str
) -> List[str]:
    """
    Run multiple sessions in parallel batches.

    Args:
        config_path: Path to session configuration
        num_runs: Total number of sessions to run
        max_parallel: Maximum concurrent sessions
        seed_start: Starting seed value
        output_dir: Output directory for logs

    Returns:
        List of successful session IDs
    """
    print(f"Running {num_runs} sessions with up to {max_parallel} in parallel...")
    print(f"Config: {config_path}")
    print(f"Seed range: {seed_start} to {seed_start + num_runs - 1}\n")

    successful_ids = []
    seeds = [seed_start + i for i in range(num_runs)]

    # Run in batches
    for batch_start in range(0, num_runs, max_parallel):
        batch_seeds = seeds[batch_start:batch_start + max_parallel]
        batch_num = batch_start // max_parallel + 1
        total_batches = (num_runs + max_parallel - 1) // max_parallel

        print(f"Batch {batch_num}/{total_batches} ({len(batch_seeds)} sessions):")

        # Run batch in parallel using asyncio thread pool
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, run_session, config_path, seed, output_dir)
            for seed in batch_seeds
        ]

        batch_results = await asyncio.gather(*tasks)
        successful_ids.extend([sid for sid in batch_results if sid is not None])

        print(f"Batch {batch_num} complete: {sum(1 for r in batch_results if r is not None)}/{len(batch_seeds)} successful\n")

    return successful_ids


def main():
    parser = argparse.ArgumentParser(
        description="Run multiple Aeonisk sessions for success@n evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default='session_config_combat.json',
        help='Session configuration file (default: session_config_combat.json)'
    )

    parser.add_argument(
        '--runs', '-r',
        type=int,
        default=10,
        help='Number of sessions to run (default: 10)'
    )

    parser.add_argument(
        '--parallel', '-p',
        type=int,
        default=4,
        help='Maximum parallel sessions (default: 4)'
    )

    parser.add_argument(
        '--seed-start', '-s',
        type=int,
        default=1000,
        help='Starting random seed (default: 1000)'
    )

    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default='./multiagent_output',
        help='Output directory for logs (default: ./multiagent_output)'
    )

    parser.add_argument(
        '--n-values', '-n',
        type=str,
        default='3,5,10,15,20',
        help='Comma-separated n-values for success@n (default: 3,5,10,15,20)'
    )

    parser.add_argument(
        '--report', '-R',
        type=str,
        help='Save markdown report to file'
    )

    args = parser.parse_args()

    # Validate config exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    # Parse n-values
    try:
        n_values = [int(n.strip()) for n in args.n_values.split(',')]
    except ValueError:
        print(f"Error: Invalid n-values: {args.n_values}", file=sys.stderr)
        return 1

    # Record start time
    start_time = datetime.now()
    print(f"=== Success@n Evaluation Run ===")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Run sessions
    session_ids = asyncio.run(run_sessions_parallel(
        str(config_path),
        args.runs,
        args.parallel,
        args.seed_start,
        args.output_dir
    ))

    # Record end time
    end_time = datetime.now()
    duration = end_time - start_time

    print(f"\n=== Run Complete ===")
    print(f"Duration: {duration}")
    print(f"Successful: {len(session_ids)}/{args.runs}")

    if not session_ids:
        print("\nNo successful sessions - cannot generate metrics")
        return 1

    # Analyze results
    print(f"\nAnalyzing {len(session_ids)} session logs...")

    # Get absolute path to output directory (in scripts/ folder)
    script_dir = Path(__file__).parent.resolve()
    output_path = script_dir / args.output_dir.lstrip('./')

    if not output_path.exists():
        print(f"Error: Output directory not found: {output_path}")
        return 1

    results = []

    for session_id in session_ids:
        # Find the log file
        log_files = list(output_path.glob(f"session_{session_id}*.jsonl"))
        if not log_files:
            # Try alternate pattern
            log_files = list(output_path.glob(f"session_*{session_id[:8]}*.jsonl"))
        if not log_files:
            # Try finding any recent JSONL (fallback for when session_id extraction fails)
            all_logs = sorted(output_path.glob(f"session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if all_logs and len(all_logs) >= len(results) + 1:
                log_files = [all_logs[len(results)]]  # Use next most recent

        if log_files:
            try:
                result = analyze_jsonl_log(log_files[0])
                results.append(result)
            except Exception as e:
                print(f"  Warning: Could not analyze {log_files[0].name}: {e}")

    if not results:
        print("Error: Could not analyze any session logs")
        return 1

    # Calculate metrics
    print(f"\nCalculating success@n metrics for n={args.n_values}...")
    metrics = calculate_success_at_n(results, n_values)

    # Generate report
    report = format_metrics_report(metrics)

    # Add run metadata
    metadata = [
        "# Success@n Evaluation Report\n",
        f"**Run Date**: {start_time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Duration**: {duration}  ",
        f"**Config**: {config_path}  ",
        f"**Total Sessions**: {args.runs}  ",
        f"**Successful Sessions**: {len(session_ids)}  ",
        f"**Seed Range**: {args.seed_start} to {args.seed_start + args.runs - 1}  ",
        "\n---\n"
    ]

    full_report = "\n".join(metadata) + "\n" + report

    # Output
    if args.report:
        report_path = Path(args.report)
        report_path.write_text(full_report)
        print(f"\n📊 Report saved to {report_path}")
    else:
        print("\n" + full_report)

    # Print summary to console
    print("\n=== Summary ===")
    for n in sorted(n_values):
        m = metrics[n]
        print(f"Success@{n:2d}: {m.success_rate:6.1%} ({m.successful_sessions}/{m.total_sessions})")

    return 0


if __name__ == '__main__':
    sys.exit(main())
