#!/usr/bin/env python3
"""
YAGS Datamining Tool - Validate, analyze, and export bulk session outputs.

Usage:
    python scripts/yags_mine.py validate <path> [options]
    python scripts/yags_mine.py analyze <path> [options]
    python scripts/yags_mine.py discover <directory> [options]

Examples:
    # Validate single session
    yags_mine.py validate session.jsonl

    # Validate all sessions in bulk output
    yags_mine.py validate bulk_output/ --recursive

    # Validate with specific validators only
    yags_mine.py validate bulk_output/ --validators schema,ordering,llm

    # JSON output for CI
    yags_mine.py validate bulk_output/ --format json

    # Strict mode (warnings become errors)
    yags_mine.py validate bulk_output/ --strict

    # Discover interesting sessions
    yags_mine.py discover bulk_output/ --complete-only --limit 20
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Set

# Add scripts directory to path
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from datamine import BulkValidator, BulkReport
from datamine.types import ValidatorType


def parse_validators(validators_str: str) -> Set[ValidatorType]:
    """Parse comma-separated validator names into set of ValidatorType."""
    validators = set()
    for name in validators_str.split(','):
        name = name.strip().lower()
        try:
            validators.add(ValidatorType(name))
        except ValueError:
            print(f"Warning: Unknown validator '{name}', skipping", file=sys.stderr)
    return validators


def cmd_validate(args: argparse.Namespace) -> int:
    """Run validation on session files."""
    path = Path(args.path)

    # Parse validators
    validators = None
    if args.validators:
        validators = parse_validators(args.validators)

    # Create validator
    validator = BulkValidator(
        validators=validators,
        strict=args.strict,
        fallback_threshold=args.fallback_threshold / 100,  # Convert percent to ratio
    )

    # Run validation
    if path.is_file():
        result = validator.validate_session(path)
        report = BulkReport(directory=path.parent)
        report.add_result(result)
    elif path.is_dir():
        report = validator.validate_directory(
            path,
            recursive=args.recursive,
        )
    else:
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    # Output results
    if args.format == 'json':
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_summary(show_details=not args.quiet)

    # Return exit code
    return 0 if report.failed_sessions == 0 else 1


def cmd_discover(args: argparse.Namespace) -> int:
    """Discover and list session files."""
    directory = Path(args.directory)

    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}", file=sys.stderr)
        return 1

    # Import SessionDiscovery from analyze_session
    from analyze_session import SessionDiscovery

    discovery = SessionDiscovery(directory)
    sessions = discovery.scan(
        complete_only=args.complete_only,
        min_rounds=args.min_rounds,
    )

    # Limit results
    if args.limit:
        sessions = sessions[:args.limit]

    # Output
    if args.format == 'json':
        print(json.dumps(sessions, indent=2, default=str))
    else:
        print(f"\n{'=' * 60}")
        print(f"SESSION DISCOVERY: {directory}")
        print(f"{'=' * 60}")
        print(f"Found: {len(sessions)} sessions\n")

        for i, session in enumerate(sessions, 1):
            score = session.get('score', 0)
            rounds = session.get('rounds', 0)
            complete = '✓' if session.get('is_complete') else '✗'
            actions = session.get('total_actions', 0)
            print(f"{i:3d}. {session['path'].name}")
            print(f"     Score: {score:.1f} | Rounds: {rounds} | Actions: {actions} | Complete: {complete}")

    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze session files (wrapper for analyze_session.py modes)."""
    path = Path(args.path)

    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    # Import SessionAnalyzer from analyze_session
    from analyze_session import SessionAnalyzer

    if path.is_file():
        analyzer = SessionAnalyzer(path)
        if args.mode == 'errors':
            analyzer.print_error_analysis()
        elif args.mode == 'void':
            analyzer.print_void_analysis()
        elif args.mode == 'clocks':
            analyzer.print_clock_analysis()
        else:
            analyzer.print_summary()
    else:
        # Directory: run analysis on all files
        files = sorted(path.rglob("session_*.jsonl") if args.recursive else path.glob("session_*.jsonl"))
        for f in files[:args.limit or 100]:
            print(f"\n{'=' * 60}")
            print(f"FILE: {f.name}")
            print(f"{'=' * 60}")
            try:
                analyzer = SessionAnalyzer(f)
                if args.mode == 'errors':
                    analyzer.print_error_analysis()
                else:
                    analyzer.print_summary()
            except Exception as e:
                print(f"Error analyzing {f}: {e}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="YAGS Datamining Tool - Validate, analyze, and export session outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # === VALIDATE ===
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate session files for schema compliance, ordering, integrity, and LLM errors'
    )
    validate_parser.add_argument(
        'path',
        help='Path to session file or directory'
    )
    validate_parser.add_argument(
        '--validators',
        help='Comma-separated list of validators: schema,ordering,integrity,llm (default: all)'
    )
    validate_parser.add_argument(
        '--strict',
        action='store_true',
        help='Treat warnings as errors'
    )
    validate_parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        default=True,
        help='Search directories recursively (default: True)'
    )
    validate_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )
    validate_parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Only show summary, not individual errors'
    )
    validate_parser.add_argument(
        '--fallback-threshold',
        type=float,
        default=10.0,
        help='LLM fallback rate threshold for warnings (percent, default: 10)'
    )

    # === DISCOVER ===
    discover_parser = subparsers.add_parser(
        'discover',
        help='Discover and rank session files by interestingness'
    )
    discover_parser.add_argument(
        'directory',
        help='Directory to scan for sessions'
    )
    discover_parser.add_argument(
        '--complete-only',
        action='store_true',
        help='Only show complete sessions (with session_end)'
    )
    discover_parser.add_argument(
        '--min-rounds',
        type=int,
        default=0,
        help='Minimum number of rounds'
    )
    discover_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Maximum number of results (default: 20)'
    )
    discover_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    # === ANALYZE ===
    analyze_parser = subparsers.add_parser(
        'analyze',
        help='Analyze session files (summary, errors, void, clocks)'
    )
    analyze_parser.add_argument(
        'path',
        help='Path to session file or directory'
    )
    analyze_parser.add_argument(
        '--mode', '-m',
        choices=['summary', 'errors', 'void', 'clocks'],
        default='summary',
        help='Analysis mode (default: summary)'
    )
    analyze_parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        default=True,
        help='Search directories recursively'
    )
    analyze_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum files to analyze in directory'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == 'validate':
        return cmd_validate(args)
    elif args.command == 'discover':
        return cmd_discover(args)
    elif args.command == 'analyze':
        return cmd_analyze(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
