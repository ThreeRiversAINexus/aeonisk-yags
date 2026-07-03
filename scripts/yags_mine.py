#!/usr/bin/env python3
"""
YAGS Datamining Tool - Validate, analyze, and export bulk session outputs.

Usage:
    python scripts/yags_mine.py validate <path> [options]
    python scripts/yags_mine.py analyze <path> [options]
    python scripts/yags_mine.py discover <directory> [options]
    python scripts/yags_mine.py balance <path> [options]
    python scripts/yags_mine.py fidelity <path> [options]
    python scripts/yags_mine.py cost <path> [options]

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

    # Balance analysis
    yags_mine.py balance bulk_output/                     # All metrics, terminal
    yags_mine.py balance bulk_output/ -a skills           # Skills only
    yags_mine.py balance bulk_output/ -a skills,weapons   # Multiple analyzers
    yags_mine.py balance bulk_output/ -f json -o report.json  # JSON export
    yags_mine.py cost bulk_output/ --pricing-file pricing.json

    # Extract rules-fidelity eval items (benchmark ground truth)
    yags_mine.py fidelity bulk_output/ -o eval_items.jsonl
    yags_mine.py fidelity session.jsonl --tasks roll,soulcredit -f json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Set
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add scripts directory to path
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from datamine import BulkValidator, BulkReport
from datamine.types import ValidatorType
from datamine.analyzers import (
    AnalyzerPipeline,
    stream_events,
    SkillsAnalyzer,
    WeaponsAnalyzer,
    EnemiesAnalyzer,
    EconomyAnalyzer,
    TargetingAnalyzer,
)
from datamine.formatters import TerminalFormatter, JSONFormatter, CSVFormatter


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
    for session in sessions:
        session['score'] = discovery.calculate_interestingness(session)
    sessions.sort(key=lambda s: s['score'], reverse=True)

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
            complete = '✓' if session.get('complete') else '✗'
            actions = session.get('actions', 0)
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

    def print_analysis(analyzer: SessionAnalyzer) -> None:
        if args.mode == 'errors':
            analyzer.print_errors()
        elif args.mode == 'void':
            analyzer.print_void()
        elif args.mode == 'clocks':
            analyzer.print_clocks()
        else:
            analyzer.print_summary()

    if path.is_file():
        analyzer = SessionAnalyzer(path)
        print_analysis(analyzer)
    else:
        # Directory: run analysis on all files
        files = sorted(path.rglob("session_*.jsonl") if args.recursive else path.glob("session_*.jsonl"))
        for f in files[:args.limit or 100]:
            print(f"\n{'=' * 60}")
            print(f"FILE: {f.name}")
            print(f"{'=' * 60}")
            try:
                analyzer = SessionAnalyzer(f)
                print_analysis(analyzer)
            except Exception as e:
                print(f"Error analyzing {f}: {e}")

    return 0


# Available analyzer names -> classes
ANALYZER_MAP = {
    'skills': SkillsAnalyzer,
    'weapons': WeaponsAnalyzer,
    'enemies': EnemiesAnalyzer,
    'economy': EconomyAnalyzer,
    'targeting': TargetingAnalyzer,
}


def discover_session_files(path: Path, recursive: bool = True) -> List[Path]:
    """Find all session JSONL files in path."""
    if path.is_file():
        return [path]

    if recursive:
        return sorted(path.rglob("session_*.jsonl"))
    else:
        return sorted(path.glob("session_*.jsonl"))


def cmd_balance(args: argparse.Namespace) -> int:
    """Run balance analysis on session files."""
    path = Path(args.path)

    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    # Discover session files
    session_files = discover_session_files(path, recursive=args.recursive)

    if not session_files:
        print(f"Error: No session files found at {path}", file=sys.stderr)
        return 1

    print(f"Found {len(session_files)} session files", file=sys.stderr)

    # Parse analyzers
    if args.analyzers:
        analyzer_names = [a.strip().lower() for a in args.analyzers.split(',')]
    else:
        analyzer_names = list(ANALYZER_MAP.keys())  # All analyzers

    # Validate analyzer names
    invalid = set(analyzer_names) - set(ANALYZER_MAP.keys())
    if invalid:
        print(f"Error: Unknown analyzers: {invalid}", file=sys.stderr)
        print(f"Available: {', '.join(ANALYZER_MAP.keys())}", file=sys.stderr)
        return 1

    # Create analyzers
    analyzers = [ANALYZER_MAP[name]() for name in analyzer_names]
    pipeline = AnalyzerPipeline(analyzers)

    # Process sessions
    processed = 0
    errors = 0

    for session_path in session_files:
        try:
            events = stream_events(session_path, filter_types=pipeline.all_event_types)
            pipeline.process_session(events)
            processed += 1
            if processed % 50 == 0:
                print(f"  Processed {processed}/{len(session_files)} sessions...", file=sys.stderr)
        except Exception as e:
            errors += 1
            if args.verbose:
                print(f"  Error processing {session_path.name}: {e}", file=sys.stderr)

    print(f"Processed {processed} sessions ({errors} errors)", file=sys.stderr)

    # Get results
    results = pipeline.get_results()

    # Select formatter
    if args.format == 'json':
        formatter = JSONFormatter(pretty=True)
    elif args.format == 'csv':
        formatter = CSVFormatter()
    else:
        formatter = TerminalFormatter()

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            formatter.format_multiple(results, f)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        formatter.format_multiple(results, sys.stdout)

    return 0


TASK_ALIASES = {
    'roll': 'roll_resolution',
    'damage': 'damage_soak',
    'soulcredit': 'soulcredit_adjudication',
}


def cmd_fidelity(args: argparse.Namespace) -> int:
    """Extract rules-fidelity eval items from session JSONL files."""
    from datamine.rules_fidelity import ALL_TASKS, extract_from_file, write_items

    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    tasks = None
    if args.tasks:
        tasks = set()
        for name in args.tasks.split(','):
            name = name.strip().lower()
            name = TASK_ALIASES.get(name, name)
            if name not in ALL_TASKS:
                print(f"Error: Unknown task '{name}'. "
                      f"Available: {', '.join(sorted(ALL_TASKS))}", file=sys.stderr)
                return 1
            tasks.add(name)

    if path.is_file():
        files = [path]
    else:
        files = sorted(path.rglob("*.jsonl") if args.recursive else path.glob("*.jsonl"))
    if not files:
        print(f"Error: No JSONL files found at {path}", file=sys.stderr)
        return 1

    all_items = []
    all_quarantined = []
    per_file_errors = 0
    for session_path in files:
        try:
            result = extract_from_file(session_path, tasks=tasks)
            all_items.extend(result.items)
            all_quarantined.extend(result.quarantined)
        except Exception as e:
            per_file_errors += 1
            print(f"  Error extracting {session_path.name}: {e}", file=sys.stderr)

    by_task = {}
    for item in all_items:
        by_task[item['task']] = by_task.get(item['task'], 0) + 1
    stats = {
        'files': len(files),
        'file_errors': per_file_errors,
        'items': len(all_items),
        'items_by_task': by_task,
        'quarantined': len(all_quarantined),
    }

    if args.output:
        write_items(all_items, args.output)
        print(f"Wrote {len(all_items)} items to {args.output}", file=sys.stderr)
    if args.quarantine_output and all_quarantined:
        write_items(all_quarantined, args.quarantine_output)
        print(f"Wrote {len(all_quarantined)} quarantined records to "
              f"{args.quarantine_output}", file=sys.stderr)

    if args.format == 'json':
        print(json.dumps(stats, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"RULES-FIDELITY EXTRACTION: {path}")
        print(f"{'=' * 60}")
        print(f"Files:        {stats['files']} ({per_file_errors} errors)")
        print(f"Items:        {stats['items']}")
        for task, count in sorted(by_task.items()):
            print(f"  {task}: {count}")
        print(f"Quarantined:  {stats['quarantined']} (log/rules mismatches, excluded)")

    return 0 if per_file_errors == 0 else 1


def cmd_cost(args: argparse.Namespace) -> int:
    """Run token and cost reporting on session files."""
    from cost_report import analyze_cost, print_text_report

    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    report = analyze_cost(
        path,
        recursive=args.recursive,
        pricing_file=Path(args.pricing_file) if args.pricing_file else None,
    )

    if args.format == 'json':
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_text_report(report)
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

    # === BALANCE ===
    balance_parser = subparsers.add_parser(
        'balance',
        help='Analyze game balance metrics (skills, weapons, enemies, economy)'
    )
    balance_parser.add_argument(
        'path',
        help='Path to session file or directory'
    )
    balance_parser.add_argument(
        '--analyzers', '-a',
        help='Comma-separated analyzers: skills,weapons,enemies,economy,targeting (default: all)'
    )
    balance_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json', 'csv'],
        default='text',
        help='Output format (default: text)'
    )
    balance_parser.add_argument(
        '--output', '-o',
        help='Output file (default: stdout)'
    )
    balance_parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        default=True,
        help='Search directories recursively (default: True)'
    )
    balance_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed error messages'
    )

    # === FIDELITY ===
    fidelity_parser = subparsers.add_parser(
        'fidelity',
        help='Extract rules-fidelity eval items (roll math, damage/soak, soulcredit adjudication) from session JSONL'
    )
    fidelity_parser.add_argument(
        'path',
        help='Path to session file or directory of JSONL files'
    )
    fidelity_parser.add_argument(
        '--tasks',
        help='Comma-separated tasks: roll,damage,soulcredit (default: all)'
    )
    fidelity_parser.add_argument(
        '--output', '-o',
        help='Write eval items to this JSONL file'
    )
    fidelity_parser.add_argument(
        '--quarantine-output',
        help='Write quarantined (log/rules mismatch) records to this JSONL file'
    )
    fidelity_parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        default=True,
        help='Search directories recursively (default: True)'
    )
    fidelity_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json'],
        default='text',
        help='Output format for stats (default: text)'
    )

    # === COST ===
    cost_parser = subparsers.add_parser(
        'cost',
        help='Report token usage and estimated cost by config, run, agent, and model'
    )
    cost_parser.add_argument(
        'path',
        help='Path to session file or bulk output directory'
    )
    cost_parser.add_argument(
        '--pricing-file',
        help='JSON file with per-model input_per_1m and output_per_1m prices'
    )
    cost_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )
    cost_parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        default=True,
        help='Search directories recursively (default: True)'
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
    elif args.command == 'balance':
        return cmd_balance(args)
    elif args.command == 'fidelity':
        return cmd_fidelity(args)
    elif args.command == 'cost':
        return cmd_cost(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
