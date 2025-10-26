#!/usr/bin/env python3
"""
Analyze success@n metrics from existing JSONL session logs.

Usage:
    python3 analyze_success_metrics.py [--output report.md] [--n-values 3,5,10] [log_dir]

Examples:
    # Analyze all logs in default multiagent_output directory
    python3 analyze_success_metrics.py

    # Analyze specific directory
    python3 analyze_success_metrics.py ./custom_output

    # Custom n-values and output file
    python3 analyze_success_metrics.py --n-values 3,5,10,15,20 --output metrics.md

    # Analyze single session
    python3 analyze_success_metrics.py multiagent_output/session_abc123.jsonl
"""

import argparse
import sys
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'aeonisk'))

from aeonisk.multiagent.success_metrics import (
    analyze_jsonl_log,
    calculate_success_at_n,
    format_metrics_report,
    SessionResult
)


def find_session_logs(path: Path) -> List[Path]:
    """
    Find all JSONL session logs in a directory or return single file.

    Args:
        path: Directory or file path

    Returns:
        List of JSONL log paths
    """
    if path.is_file():
        return [path] if path.suffix == '.jsonl' else []

    if path.is_dir():
        return sorted(path.glob("session_*.jsonl"))

    return []


def main():
    parser = argparse.ArgumentParser(
        description="Analyze success@n metrics from Aeonisk session logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'log_path',
        nargs='?',
        default='./multiagent_output',
        help='Directory containing JSONL logs or single JSONL file (default: ./multiagent_output)'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output markdown file path (default: print to stdout)'
    )

    parser.add_argument(
        '--n-values', '-n',
        type=str,
        default='3,5,10,15,20',
        help='Comma-separated list of n-values for success@n (default: 3,5,10,15,20)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed progress information'
    )

    args = parser.parse_args()

    # Parse n-values
    try:
        n_values = [int(n.strip()) for n in args.n_values.split(',')]
    except ValueError:
        print(f"Error: Invalid n-values format: {args.n_values}", file=sys.stderr)
        print("Expected comma-separated integers like: 3,5,10", file=sys.stderr)
        return 1

    # Find log files
    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"Error: Path not found: {log_path}", file=sys.stderr)
        return 1

    log_files = find_session_logs(log_path)
    if not log_files:
        print(f"Error: No JSONL session logs found in {log_path}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Found {len(log_files)} session log(s) to analyze", file=sys.stderr)

    # Analyze each log
    results: List[SessionResult] = []
    for log_file in log_files:
        if args.verbose:
            print(f"Analyzing {log_file.name}...", file=sys.stderr)

        try:
            result = analyze_jsonl_log(log_file)
            results.append(result)

            if args.verbose:
                status = "SUCCESS" if result.mission_success else "INCOMPLETE"
                print(f"  Session: {result.session_id[:8]} | "
                      f"Rounds: {result.total_rounds} | "
                      f"Status: {status} | "
                      f"Clocks: {result.clocks_completed}/{result.clocks_completed + result.clocks_failed}",
                      file=sys.stderr)

        except Exception as e:
            print(f"Error analyzing {log_file.name}: {e}", file=sys.stderr)
            continue

    if not results:
        print("Error: No sessions could be analyzed successfully", file=sys.stderr)
        return 1

    # Calculate success@n metrics
    metrics = calculate_success_at_n(results, n_values)

    # Generate report
    report = format_metrics_report(metrics)

    # Add session summary at the top
    summary_lines = [
        "# Success@n Analysis Report\n",
        f"**Total Sessions Analyzed**: {len(results)}  ",
        f"**Analysis Date**: {Path(__file__).parent}  ",
        f"**Log Source**: {log_path}  ",
        "\n---\n"
    ]

    full_report = "\n".join(summary_lines) + "\n" + report

    # Add individual session details
    if args.verbose:
        full_report += "\n## Individual Session Results\n\n"
        for result in results:
            full_report += f"### Session `{result.session_id[:8]}`\n"
            full_report += f"- **Seed**: {result.random_seed}\n"
            full_report += f"- **Rounds**: {result.total_rounds}\n"
            full_report += f"- **Status**: {'SUCCESS' if result.mission_success else 'INCOMPLETE'}\n"
            if result.success_round:
                full_report += f"- **Success Round**: {result.success_round}\n"
            full_report += f"- **Clocks**: {result.clocks_completed} completed, {result.clocks_failed} failed\n"
            full_report += f"- **Characters**: {result.characters_alive} alive, {result.characters_dead} dead\n"
            full_report += f"- **Actions**: {result.successful_actions}/{result.total_actions} ({result.success_rate:.1%})\n"
            full_report += f"- **Damage**: {result.total_damage_dealt} dealt, {result.total_damage_taken} taken\n"
            full_report += "\n"

    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(full_report)
        print(f"Report written to {output_path}")
    else:
        print(full_report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
