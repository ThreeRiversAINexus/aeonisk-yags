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

                # Action declaration (player intentions)
                elif event_type == 'action_declaration':
                    # Only log player actions (not enemy tactical actions)
                    player_id = event.get('player_id', '')
                    if player_id.startswith('player_'):
                        action = event.get('action', {})
                        intent = action.get('intent', 'No intent specified')
                        description = action.get('description', '')

                        content = f"""#### {event.get('character_name', 'Unknown')} declares:
**Intent:** {intent}

{description if description else '*(No detailed description)*'}

*Attribute:* {action.get('attribute', '?')} | *Skill:* {action.get('skill', '?')} | *Estimated DC:* {action.get('difficulty_estimate', '?')}
"""
                        narratives.append({
                            'type': 'action_declaration',
                            'round': event.get('round'),
                            'timestamp': event.get('ts'),
                            'character': event.get('character_name'),
                            'content': content
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

                    content_parts = [f"""### Round {event.get('round')} Summary

{synthesis}
"""]

                    # Add structured story elements if present
                    if 'story_advancement' in event:
                        adv = event['story_advancement']
                        content_parts.append(f"""
**STORY ADVANCEMENT**
- New Location: {adv.get('location', 'Unknown')}
- New Situation: {adv.get('situation', 'Unknown')}
- Void Level: {adv.get('new_void_level', '?')}
""")
                        if adv.get('clear_all_enemies'):
                            content_parts.append("- *All enemies cleared*\n")
                        if adv.get('new_clocks'):
                            content_parts.append("- New Clocks: " + ", ".join(c['name'] for c in adv['new_clocks']) + "\n")

                    if 'scene_pivot' in event:
                        pivot = event['scene_pivot']
                        content_parts.append(f"""
**SCENE PIVOT**
- New Room: {pivot.get('new_room', 'Unknown')}
- Situation Change: {pivot.get('situation_change', 'Unknown')}
""")
                        if pivot.get('clear_specific_clocks'):
                            content_parts.append("- Clocks Cleared: " + ", ".join(pivot['clear_specific_clocks']) + "\n")
                        if pivot.get('new_clocks'):
                            content_parts.append("- New Clocks: " + ", ".join(c['name'] for c in pivot['new_clocks']) + "\n")

                    if 'enemy_spawns' in event and event['enemy_spawns']:
                        spawns = event['enemy_spawns']
                        content_parts.append(f"\n**NEW ENEMIES:** {len(spawns)} spawned\n")

                    if 'npc_spawns' in event and event['npc_spawns']:
                        spawns = event['npc_spawns']
                        content_parts.append(f"\n**NEW NPCs:** {len(spawns)} appeared\n")

                    if 'escalations' in event and event['escalations']:
                        esc = event['escalations']
                        content_parts.append(f"\n**ESCALATIONS:** {len(esc)} NPCs became hostile\n")

                    if 'clocks_filled' in event and event['clocks_filled']:
                        filled = event['clocks_filled']
                        content_parts.append(f"\n**CLOCKS FILLED:** {', '.join(filled)}\n")

                    if 'clocks_expired' in event and event['clocks_expired']:
                        expired = event['clocks_expired']
                        content_parts.append(f"\n**CLOCKS EXPIRED:** {', '.join(expired)}\n")

                    if event.get('session_end'):
                        reason = event.get('session_end_reason', 'Unknown')
                        content_parts.append(f"\n**SESSION END:** {reason}\n")

                    content = "".join(content_parts)

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
    declarations = len([n for n in narratives if n['type'] == 'action_declaration'])

    print("\n" + "="*80)
    print("## Narrative Statistics\n")
    print(f"- Total rounds: {rounds}")
    print(f"- Player action declarations: {declarations}")
    print(f"- Action resolutions: {actions}")
    print(f"- Scenario setup: {type_counts.get('scenario', 0)}")
    print(f"- Round syntheses: {type_counts.get('round_synthesis', 0)}")
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
