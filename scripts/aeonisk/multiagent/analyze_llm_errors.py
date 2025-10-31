#!/usr/bin/env python3
"""
Analyze LLM errors and validation issues from JSONL session logs.

Usage:
    python analyze_llm_errors.py <path_to_jsonl_file>
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


def analyze_jsonl_errors(jsonl_path: Path):
    """Extract and categorize all LLM errors, validation issues, and problems from JSONL log."""

    errors = {
        'validation_warnings': [],
        'structured_output_failures': [],
        'fallback_triggers': [],
        'parsing_errors': [],
        'llm_api_errors': [],
        'other_errors': []
    }

    stats = {
        'total_events': 0,
        'total_llm_calls': 0,
        'structured_output_success': 0,
        'structured_output_fail': 0,
        'validation_warnings_count': 0,
        'fallback_triggers_count': 0
    }

    with open(jsonl_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                event = json.loads(line)
                stats['total_events'] += 1

                event_type = event.get('event_type')

                # Check structured output metrics
                if event_type == 'structured_output_metrics':
                    stats['total_llm_calls'] += 1

                    if event.get('structured_output_success'):
                        stats['structured_output_success'] += 1
                    else:
                        stats['structured_output_fail'] += 1
                        errors['structured_output_failures'].append({
                            'round': event.get('round'),
                            'agent_type': event.get('agent_type'),
                            'agent_id': event.get('agent_id'),
                            'error': 'Structured output failed'
                        })

                    # Check validation warnings
                    validation_warnings = event.get('validation_warnings', [])
                    if validation_warnings:
                        stats['validation_warnings_count'] += len(validation_warnings)
                        errors['validation_warnings'].append({
                            'round': event.get('round'),
                            'agent_type': event.get('agent_type'),
                            'agent_id': event.get('agent_id'),
                            'warnings': validation_warnings,
                            'completeness_score': event.get('completeness_score', 0)
                        })

                    # Check fallback triggered
                    if event.get('fallback_triggered'):
                        stats['fallback_triggers_count'] += 1
                        errors['fallback_triggers'].append({
                            'round': event.get('round'),
                            'agent_type': event.get('agent_type'),
                            'agent_id': event.get('agent_id')
                        })

                # Check for error fields in other event types
                if 'error' in event:
                    errors['other_errors'].append({
                        'line': line_num,
                        'event_type': event_type,
                        'error': event['error']
                    })

            except json.JSONDecodeError as e:
                errors['parsing_errors'].append({
                    'line': line_num,
                    'error': str(e)
                })
            except Exception as e:
                errors['other_errors'].append({
                    'line': line_num,
                    'error': f"Unexpected error: {e}"
                })

    return errors, stats


def print_report(errors, stats, jsonl_path):
    """Print a formatted report of errors and issues."""

    print(f"\n{'='*80}")
    print(f"LLM ERROR ANALYSIS: {jsonl_path.name}")
    print(f"{'='*80}\n")

    # Stats summary
    print("📊 SUMMARY STATISTICS")
    print(f"{'─'*80}")
    print(f"Total events in log: {stats['total_events']}")
    print(f"Total LLM calls: {stats['total_llm_calls']}")
    print(f"Structured output success: {stats['structured_output_success']} ({stats['structured_output_success']/max(stats['total_llm_calls'],1)*100:.1f}%)")
    print(f"Structured output failures: {stats['structured_output_fail']}")
    print(f"Validation warnings: {stats['validation_warnings_count']}")
    print(f"Fallback triggers: {stats['fallback_triggers_count']}")
    print()

    # Validation warnings
    if errors['validation_warnings']:
        print(f"\n⚠️  VALIDATION WARNINGS ({len(errors['validation_warnings'])} occurrences)")
        print(f"{'─'*80}")

        # Group by warning type
        warning_counts = defaultdict(int)
        for entry in errors['validation_warnings']:
            for warning in entry['warnings']:
                warning_counts[warning] += 1

        print("\nWarning frequency:")
        for warning, count in sorted(warning_counts.items(), key=lambda x: -x[1]):
            print(f"  [{count}x] {warning}")

        print("\nDetailed occurrences:")
        for entry in errors['validation_warnings']:
            print(f"\n  Round {entry['round']} | {entry['agent_type']} ({entry['agent_id']})")
            print(f"  Completeness: {entry['completeness_score']:.2f}")
            for warning in entry['warnings']:
                print(f"    - {warning}")

    # Structured output failures
    if errors['structured_output_failures']:
        print(f"\n❌ STRUCTURED OUTPUT FAILURES ({len(errors['structured_output_failures'])} occurrences)")
        print(f"{'─'*80}")
        for entry in errors['structured_output_failures']:
            print(f"  Round {entry['round']} | {entry['agent_type']} ({entry['agent_id']})")
            print(f"    Error: {entry['error']}")

    # Fallback triggers
    if errors['fallback_triggers']:
        print(f"\n🔄 FALLBACK TRIGGERS ({len(errors['fallback_triggers'])} occurrences)")
        print(f"{'─'*80}")

        # Group by agent type
        by_agent = defaultdict(int)
        for entry in errors['fallback_triggers']:
            by_agent[entry['agent_type']] += 1

        print("\nBy agent type:")
        for agent_type, count in sorted(by_agent.items(), key=lambda x: -x[1]):
            print(f"  {agent_type}: {count}x")

    # Parsing errors
    if errors['parsing_errors']:
        print(f"\n🔴 PARSING ERRORS ({len(errors['parsing_errors'])} occurrences)")
        print(f"{'─'*80}")
        for entry in errors['parsing_errors']:
            print(f"  Line {entry['line']}: {entry['error']}")

    # Other errors
    if errors['other_errors']:
        print(f"\n⚠️  OTHER ERRORS ({len(errors['other_errors'])} occurrences)")
        print(f"{'─'*80}")
        for entry in errors['other_errors'][:10]:  # Limit to first 10
            print(f"  Line {entry.get('line', 'N/A')} [{entry.get('event_type', 'unknown')}]: {entry['error']}")
        if len(errors['other_errors']) > 10:
            print(f"  ... and {len(errors['other_errors']) - 10} more")

    # Summary
    print(f"\n{'='*80}")
    total_issues = (
        len(errors['validation_warnings']) +
        len(errors['structured_output_failures']) +
        len(errors['fallback_triggers']) +
        len(errors['parsing_errors']) +
        len(errors['other_errors'])
    )

    if total_issues == 0:
        print("✅ NO ERRORS FOUND - Session ran cleanly!")
    else:
        print(f"Total issues found: {total_issues}")
        print("\nRecommendations:")
        if errors['validation_warnings']:
            print("  • Review DM prompt to emphasize populating all required fields")
        if errors['fallback_triggers']:
            print("  • Fallback triggers indicate incomplete structured output - check schema docs")
        if errors['parsing_errors']:
            print("  • JSON parsing errors may indicate corrupted log file")

    print(f"{'='*80}\n")


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_llm_errors.py <path_to_jsonl_file>")
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])

    if not jsonl_path.exists():
        print(f"Error: File not found: {jsonl_path}")
        sys.exit(1)

    errors, stats = analyze_jsonl_errors(jsonl_path)
    print_report(errors, stats, jsonl_path)


if __name__ == '__main__':
    main()
