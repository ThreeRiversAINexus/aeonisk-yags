#!/usr/bin/env python3
"""
Narrative Reconstruction Tool

Reconstructs the full story from a JSONL session log by extracting all narrative
elements in chronological order.

Usage:
    python reconstruct_narrative.py session_abc123.jsonl
    python reconstruct_narrative.py session_abc123.jsonl > story.md
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List


def extract_narrative_elements(log_file: Path) -> List[Dict[str, Any]]:
    """Extract all narrative-bearing events from JSONL log."""
    narratives = []

    with open(log_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                event = json.loads(line.strip())
                event_type = event.get('event_type')

                # Session start
                if event_type == 'session_start':
                    narratives.append({
                        'type': 'session_start',
                        'round': 0,
                        'timestamp': event.get('ts'),
                        'content': f"Session: {event.get('config', {}).get('session_name', 'Unknown')}"
                    })

                # Scenario setup
                elif event_type == 'scenario':
                    scenario = event.get('scenario', {})
                    content = f"""## Scenario: {scenario.get('theme', 'Unknown')}
**Location:** {scenario.get('location', 'Unknown')}
**Void Level:** {scenario.get('void_level', 0)}

{scenario.get('situation', 'No description available')}
"""
                    narratives.append({
                        'type': 'scenario',
                        'round': 0,
                        'timestamp': event.get('ts'),
                        'content': content
                    })

                # Round start
                elif event_type == 'round_start':
                    narratives.append({
                        'type': 'round_start',
                        'round': event.get('round'),
                        'timestamp': event.get('ts'),
                        'content': f"\n---\n# Round {event.get('round')}\n"
                    })

                # Action resolution (main narrative)
                elif event_type == 'action_resolution':
                    context = event.get('context', {})
                    narration = context.get('narration', 'No narration')

                    content = f"""### {event.get('agent', 'Unknown')}
**Action:** {event.get('action', 'Unknown action')}

{narration}
"""
                    narratives.append({
                        'type': 'action_resolution',
                        'round': event.get('round'),
                        'timestamp': event.get('ts'),
                        'agent': event.get('agent'),
                        'content': content
                    })

                # Round synthesis (DM summary of round)
                elif event_type == 'round_synthesis':
                    synthesis = event.get('synthesis', 'No synthesis')

                    content = f"""### Round {event.get('round')} Summary

{synthesis}
"""
                    narratives.append({
                        'type': 'round_synthesis',
                        'round': event.get('round'),
                        'timestamp': event.get('ts'),
                        'content': content
                    })

                # Mission debrief
                elif event_type == 'mission_debrief':
                    character = event.get('character', 'Unknown')
                    debrief = event.get('debrief', event.get('narrative', 'No debrief'))

                    content = f"""### {character}'s Debrief

{debrief}
"""
                    narratives.append({
                        'type': 'mission_debrief',
                        'round': event.get('round', 999),
                        'timestamp': event.get('ts'),
                        'content': content
                    })

            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON on line {line_num}", file=sys.stderr)
                continue

    return narratives


def print_narrative(narratives: List[Dict[str, Any]]):
    """Print narrative elements in story order."""
    print("# Campaign Session Narrative\n")
    print("*Reconstructed from JSONL event log*\n")
    print("="*80)
    print()

    for element in narratives:
        print(element['content'])
        print()


def print_statistics(narratives: List[Dict[str, Any]]):
    """Print narrative statistics."""
    from collections import Counter

    type_counts = Counter(n['type'] for n in narratives)
    rounds = max(n['round'] for n in narratives if n['round'] != 999)
    actions = len([n for n in narratives if n['type'] == 'action_resolution'])

    print("\n" + "="*80)
    print("## Narrative Statistics\n")
    print(f"- Total rounds: {rounds}")
    print(f"- Total actions: {actions}")
    print(f"- Scenario setup: {type_counts.get('scenario', 0)}")
    print(f"- Mission debriefs: {type_counts.get('mission_debrief', 0)}")
    print(f"- Total narrative elements: {len(narratives)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python reconstruct_narrative.py <session_file.jsonl>", file=sys.stderr)
        print("\nExamples:", file=sys.stderr)
        print("  python reconstruct_narrative.py session_abc123.jsonl", file=sys.stderr)
        print("  python reconstruct_narrative.py session_abc123.jsonl > story.md", file=sys.stderr)
        sys.exit(1)

    log_file = Path(sys.argv[1])

    if not log_file.exists():
        print(f"Error: File not found: {log_file}", file=sys.stderr)
        sys.exit(1)

    narratives = extract_narrative_elements(log_file)
    print_narrative(narratives)
    print_statistics(narratives)


if __name__ == '__main__':
    main()
