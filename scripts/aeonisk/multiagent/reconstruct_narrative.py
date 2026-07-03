#!/usr/bin/env python3
"""
Narrative Reconstruction Tool

Reconstructs the full story from a JSONL session log by extracting all narrative
elements in chronological order.

Usage:
    python reconstruct_narrative.py session_abc123.jsonl
    python reconstruct_narrative.py session_abc123.jsonl > story.md

Features:
    - Player, NPC, and enemy action declarations
    - DM action resolutions with full narration
    - Clock tracking (spawn, advancement, completion, removal)
    - Character state progression (HP, void, soulcredit, wounds)
    - Entity lifecycle (NPC/enemy spawns, conversions, departures)
    - Round statistics (success rate, margins, damage, clocks)
    - Economy summaries (void/soulcredit deltas)
    - Round synthesis and mission debriefs
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict


def extract_narrative_elements(log_file: Path) -> List[Dict[str, Any]]:
    """Extract all narrative-bearing events from JSONL log."""
    narratives = []
    all_events = []

    # First pass: load all events
    with open(log_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                event = json.loads(line.strip())
                all_events.append(event)
            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON on line {line_num}", file=sys.stderr)
                continue

    # Second pass: extract narrative elements
    for event in all_events:
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

        # Action declaration (ALL actions: players, NPCs, enemies)
        elif event_type == 'action_declaration':
            action = event.get('action', {})
            character_name = event.get('character_name', 'Unknown')
            action_type = action.get('action_type', 'unknown')

            # Format based on action type
            if action_type == 'dialogue':
                # NPC dialogue - simpler format
                description = action.get('description', '')
                content = f"""#### {character_name} (dialogue):
{description if description else '*(No dialogue)*'}
"""
            elif action_type in ['pass', 'flee', 'hide', 'plead', 'comply', 'assist']:
                # NPC simple actions - one-liner
                description = action.get('description', action_type)
                content = f"""#### {character_name} ({action_type}): {description}
"""
            else:
                # Player/tactical actions - full format
                intent = action.get('intent', 'No intent specified')
                description = action.get('description', '')
                ambient_speech = action.get('ambient_speech')
                speech_text = ""
                if isinstance(ambient_speech, dict) and ambient_speech.get('line'):
                    delivery = ambient_speech.get('delivery', 'spoken')
                    target = ambient_speech.get('target')
                    target_type = ambient_speech.get('target_type', 'self')
                    target_text = f" to {target}" if target else f" to {target_type}"
                    speech_text = f"\n**Ambient speech ({delivery}{target_text}):** \"{ambient_speech['line']}\"\n"

                content = f"""#### {character_name} declares:
**Intent:** {intent}

{description if description else '*(No detailed description)*'}
{speech_text}

*Attribute:* {action.get('attribute', '?')} | *Skill:* {action.get('skill', '?')} | *Estimated DC:* {action.get('difficulty_estimate', '?')}
"""

            narratives.append({
                'type': 'action_declaration',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'character': character_name,
                'action_type': action_type,
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

        # Clock events
        elif event_type == 'clock_spawn':
            clock_name = event.get('clock_name', 'Unknown')
            current = event.get('current_ticks', 0)
            max_ticks = event.get('max_ticks', 0)
            direction = event.get('direction', 'progress')
            description = event.get('description', '')

            content = f"""**New Clock:** {clock_name} ({current}/{max_ticks}) - {direction}
*{description}*
"""
            narratives.append({
                'type': 'clock_spawn',
                'round': event.get('round', 0),
                'timestamp': event.get('ts'),
                'clock_name': clock_name,
                'content': content
            })

        elif event_type == 'clock_advancement':
            # Clock data is nested in 'data' field
            data = event.get('data', {})
            clock_name = data.get('clock_name', 'Unknown')
            previous = data.get('before_ticks', 0)
            new = data.get('after_ticks', 0)
            max_ticks = data.get('maximum_ticks', 0)
            delta = data.get('delta', 0)
            direction = data.get('direction', '↑')

            # Determine if advanced or regressed
            symbol = direction if direction in ['↑', '↓'] else ('↑' if delta > 0 else '↓')

            narratives.append({
                'type': 'clock_advancement',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'clock_name': clock_name,
                'previous': previous,
                'new': new,
                'max': max_ticks,
                'delta': delta,
                'symbol': symbol,
                'content': f"- {clock_name}: {previous}/{max_ticks} → {new}/{max_ticks} ({symbol}{abs(delta)})"
            })

        elif event_type == 'clock_completion':
            # Clock data is nested in 'data' field
            data = event.get('data', {})
            clock_name = data.get('clock_name', 'Unknown')
            final_ticks = data.get('final_ticks', 0)
            max_ticks = data.get('maximum_ticks', 0)
            consequence = data.get('filled_consequence', '')

            content = f"🔔 **{clock_name}** filled ({final_ticks}/{max_ticks})!"
            if consequence:
                content += f"\n*Consequence:* {consequence}"

            narratives.append({
                'type': 'clock_completion',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'clock_name': clock_name,
                'content': content
            })

        elif event_type == 'clock_removal':
            # Clock data is nested in 'data' field
            data = event.get('data', {})
            clock_name = data.get('clock_name', 'Unknown')
            removal_reason = data.get('removal_reason', 'removed')
            current_ticks = data.get('current_ticks', 0)
            max_ticks = data.get('maximum_ticks', 0)

            narratives.append({
                'type': 'clock_removal',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'clock_name': clock_name,
                'content': f"⊗ **{clock_name}** removed ({removal_reason}, was {current_ticks}/{max_ticks})"
            })

        # Character state
        elif event_type == 'character_state':
            narratives.append({
                'type': 'character_state',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'character_id': event.get('character_id'),
                'character_name': event.get('character_name', 'Unknown'),
                'health': event.get('health', 0),
                'max_health': event.get('max_health', 0),
                'wounds': event.get('wounds', 0),
                'void_score': event.get('void_score', 0),
                'soulcredit': event.get('soulcredit', 0),
                'conditions': event.get('conditions', []),
                'is_defeated': event.get('is_defeated', False),
                'content': ''  # Formatted later
            })

        # Round summary (statistics)
        elif event_type == 'round_summary':
            narratives.append({
                'type': 'round_summary',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'actions_attempted': event.get('actions_attempted', 0),
                'success_count': event.get('success_count', 0),
                'success_rate': event.get('success_rate', 0.0),
                'average_margin': event.get('average_margin', 0.0),
                'damage_dealt': event.get('damage_dealt_by_players', 0),
                'damage_taken': event.get('damage_taken_by_players', 0),
                'void_gained': event.get('void_gained', 0),
                'void_lost': event.get('void_lost', 0),
                'clocks_advanced': event.get('clocks_advanced', 0),
                'clocks_regressed': event.get('clocks_regressed', 0),
                'total_ticks_advanced': event.get('total_ticks_advanced', 0),
                'total_ticks_regressed': event.get('total_ticks_regressed', 0),
                'active_enemies': event.get('active_enemies', 0),
                'player_wounds_total': event.get('player_wounds_total', 0),
                'content': ''  # Formatted later
            })

        # Entity lifecycle
        elif event_type == 'entity_lifecycle':
            data = event.get('data', {})
            narratives.append({
                'type': 'entity_lifecycle',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'npcs_spawned': data.get('npcs_spawned', []),
                'enemies_spawned': data.get('enemies_spawned', []),
                'enemies_converted': data.get('enemies_converted', []),
                'npcs_escalated': data.get('npcs_escalated', []),
                'npcs_departed': data.get('npcs_departed', []),
                'conversion_reasoning': data.get('conversion_reasoning', ''),
                'content': ''  # Formatted later
            })

        # NPC departure
        elif event_type == 'npc_departure':
            npc_name = event.get('npc_name', 'Unknown NPC')
            reason = event.get('departure_reason', 'unknown')

            narratives.append({
                'type': 'npc_departure',
                'round': event.get('round'),
                'timestamp': event.get('ts'),
                'npc_name': npc_name,
                'reason': reason,
                'content': f"👋 **{npc_name}** departed ({reason})"
            })

        # Round synthesis (DM summary of round)
        elif event_type == 'round_synthesis':
            synthesis = event.get('synthesis', 'No synthesis')
            round_num = event.get('round')

            content_parts = [f"""### Round {round_num} Synthesis

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
                total_enemies = sum(spawn.get('count', 1) for spawn in spawns)
                content_parts.append(f"\n**NEW ENEMIES:** {total_enemies} spawned\n")

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
                'round': round_num,
                'timestamp': event.get('ts'),
                'content': content
            })

        # Mission debrief
        elif event_type == 'mission_debrief':
            character = event.get('character', 'Unknown')
            debrief = event.get('debrief', event.get('narrative', 'No debrief'))
            final_state = event.get('final_state', {})

            content = f"""### {character}'s Debrief

{debrief}

**Final State:** Void {final_state.get('void_score', '?')} | Soulcredit {final_state.get('soulcredit', '?')}
"""
            narratives.append({
                'type': 'mission_debrief',
                'round': event.get('round', 999),
                'timestamp': event.get('ts'),
                'content': content
            })

    # Third pass: add round-level summaries
    narratives = add_round_summaries(narratives, all_events)

    return narratives


def add_round_summaries(narratives: List[Dict[str, Any]], all_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add formatted round-level summary sections after round_synthesis."""

    # Group events by round
    rounds_with_synthesis = set()
    for n in narratives:
        if n['type'] == 'round_synthesis':
            rounds_with_synthesis.add(n['round'])

    # For each round with synthesis, add summary sections
    result = []
    for i, narrative in enumerate(narratives):
        result.append(narrative)

        # After round_synthesis, add summaries
        if narrative['type'] == 'round_synthesis':
            round_num = narrative['round']

            # Clock changes
            clock_summary = format_clock_summary(round_num, narratives)
            if clock_summary:
                result.append({
                    'type': 'clock_summary',
                    'round': round_num,
                    'timestamp': narrative['timestamp'],
                    'content': clock_summary
                })

            # Entity lifecycle
            entity_summary = format_entity_summary(round_num, narratives)
            if entity_summary:
                result.append({
                    'type': 'entity_summary',
                    'round': round_num,
                    'timestamp': narrative['timestamp'],
                    'content': entity_summary
                })

            # Character states
            character_summary = format_character_summary(round_num, narratives)
            if character_summary:
                result.append({
                    'type': 'character_summary',
                    'round': round_num,
                    'timestamp': narrative['timestamp'],
                    'content': character_summary
                })

            # Economy summary
            economy_summary = format_economy_summary(round_num, all_events)
            if economy_summary:
                result.append({
                    'type': 'economy_summary',
                    'round': round_num,
                    'timestamp': narrative['timestamp'],
                    'content': economy_summary
                })

            # Round statistics
            stats_summary = format_statistics_summary(round_num, narratives)
            if stats_summary:
                result.append({
                    'type': 'statistics_summary',
                    'round': round_num,
                    'timestamp': narrative['timestamp'],
                    'content': stats_summary
                })

    return result


def format_clock_summary(round_num: int, narratives: List[Dict[str, Any]]) -> str:
    """Format clock changes for a round."""
    advancements = [n for n in narratives if n['type'] == 'clock_advancement' and n.get('round') == round_num]
    completions = [n for n in narratives if n['type'] == 'clock_completion' and n.get('round') == round_num]
    removals = [n for n in narratives if n['type'] == 'clock_removal' and n.get('round') == round_num]

    if not (advancements or completions or removals):
        return ""

    lines = ["\n**Clock Changes:**\n"]

    for adv in advancements:
        lines.append(adv['content'] + "\n")

    for comp in completions:
        lines.append(comp['content'] + "\n")

    for rem in removals:
        lines.append(rem['content'] + "\n")

    return "".join(lines)


def format_entity_summary(round_num: int, narratives: List[Dict[str, Any]]) -> str:
    """Format entity lifecycle events for a round."""
    lifecycles = [n for n in narratives if n['type'] == 'entity_lifecycle' and n.get('round') == round_num]
    departures = [n for n in narratives if n['type'] == 'npc_departure' and n.get('round') == round_num]

    if not lifecycles and not departures:
        return ""

    lines = ["\n**Entity Lifecycle:**\n"]

    for lifecycle in lifecycles:
        if lifecycle['npcs_spawned']:
            lines.append(f"- NPCs Spawned: {len(lifecycle['npcs_spawned'])}\n")
        if lifecycle['enemies_spawned']:
            lines.append(f"- Enemies Spawned: {len(lifecycle['enemies_spawned'])}\n")
        if lifecycle['enemies_converted']:
            lines.append(f"- De-escalations: {len(lifecycle['enemies_converted'])} (enemy → NPC)\n")
        if lifecycle['npcs_escalated']:
            lines.append(f"- Escalations: {len(lifecycle['npcs_escalated'])} (NPC → enemy)\n")
        if lifecycle['conversion_reasoning']:
            lines.append(f"- *Reasoning:* {lifecycle['conversion_reasoning']}\n")

    for departure in departures:
        lines.append(departure['content'] + "\n")

    return "".join(lines)


def format_character_summary(round_num: int, narratives: List[Dict[str, Any]]) -> str:
    """Format character state table for a round."""
    states = [n for n in narratives if n['type'] == 'character_state' and n.get('round') == round_num]

    if not states:
        return ""

    lines = ["\n**Character Status:**\n"]
    lines.append("| Character | HP | Void | SC | Wounds | Conditions |\n")
    lines.append("|-----------|----|----|----|----|------------|\n")

    for state in states:
        name = state['character_name']
        hp = f"{state['health']}/{state['max_health']}"
        void = state['void_score']
        sc = state['soulcredit']
        wounds = state['wounds']
        conditions = ', '.join(state['conditions']) if state['conditions'] else '—'

        defeated_marker = " ⚠️" if state['is_defeated'] else ""

        lines.append(f"| {name}{defeated_marker} | {hp} | {void} | {sc} | {wounds} | {conditions} |\n")

    return "".join(lines)


def format_economy_summary(round_num: int, all_events: List[Dict[str, Any]]) -> str:
    """Format void and soulcredit economy changes for a round."""
    resolutions = [e for e in all_events
                   if e.get('event_type') == 'action_resolution'
                   and e.get('round') == round_num]

    if not resolutions:
        return ""

    total_void = sum(e.get('economy', {}).get('void_delta', 0) for e in resolutions)
    total_sc = sum(e.get('economy', {}).get('soulcredit_delta', 0) for e in resolutions)

    # Collect soulcredit reasons
    sc_reasons = []
    for res in resolutions:
        economy = res.get('economy', {})
        delta = economy.get('soulcredit_delta', 0)
        reasons = economy.get('soulcredit_reasons', [])
        agent = res.get('agent', 'Unknown')

        if delta != 0 and reasons:
            sc_reasons.append(f"  - {agent} ({delta:+d}): {reasons[0]}")

    if total_void == 0 and total_sc == 0:
        return ""

    lines = ["\n**Economy Changes:**\n"]

    if total_void != 0:
        lines.append(f"- Void: {total_void:+d}\n")

    if total_sc != 0:
        lines.append(f"- Soulcredit: {total_sc:+d}\n")
        if sc_reasons:
            lines.extend([reason + "\n" for reason in sc_reasons])

    return "".join(lines)


def format_statistics_summary(round_num: int, narratives: List[Dict[str, Any]]) -> str:
    """Format round statistics summary."""
    summaries = [n for n in narratives if n['type'] == 'round_summary' and n.get('round') == round_num]

    if not summaries:
        return ""

    summary = summaries[0]  # Should only be one per round

    lines = ["\n**Round Statistics:**\n"]

    # Actions
    attempted = summary['actions_attempted']
    succeeded = summary['success_count']
    success_rate = summary['success_rate'] * 100
    avg_margin = summary['average_margin']

    lines.append(f"- Actions: {attempted} attempted, {succeeded} succeeded ({success_rate:.0f}%)\n")
    lines.append(f"- Average margin: {avg_margin:+.1f}\n")

    # Combat
    dealt = summary['damage_dealt']
    taken = summary['damage_taken']
    if dealt > 0 or taken > 0:
        lines.append(f"- Damage: {dealt} dealt, {taken} taken\n")

    # Void
    void_gained = summary['void_gained']
    void_lost = summary['void_lost']
    if void_gained > 0 or void_lost > 0:
        net_void = void_gained - void_lost
        lines.append(f"- Void: {void_gained} gained, {void_lost} lost (net {net_void:+d})\n")

    # Clocks
    clocks_adv = summary['clocks_advanced']
    clocks_reg = summary['clocks_regressed']
    ticks_adv = summary['total_ticks_advanced']
    ticks_reg = summary['total_ticks_regressed']

    if clocks_adv > 0 or clocks_reg > 0:
        lines.append(f"- Clocks: {clocks_adv} advanced (+{ticks_adv} ticks), {clocks_reg} regressed (-{ticks_reg} ticks)\n")

    # Enemies
    active_enemies = summary['active_enemies']
    if active_enemies > 0:
        lines.append(f"- Active enemies: {active_enemies}\n")

    # Wounds
    total_wounds = summary['player_wounds_total']
    if total_wounds > 0:
        lines.append(f"- Total player wounds: {total_wounds}\n")

    return "".join(lines)


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
    """Print overall session statistics."""
    from collections import Counter

    type_counts = Counter(n['type'] for n in narratives)
    rounds = max((n['round'] for n in narratives if n.get('round') and n['round'] != 999), default=0)
    actions = len([n for n in narratives if n['type'] == 'action_resolution'])
    declarations = len([n for n in narratives if n['type'] == 'action_declaration'])

    # Count NPCs vs players
    player_declarations = len([n for n in narratives
                               if n['type'] == 'action_declaration'
                               and n.get('action_type') not in ['dialogue', 'pass', 'flee', 'hide', 'plead']])
    npc_actions = declarations - player_declarations

    print("\n" + "="*80)
    print("## Session Statistics\n")
    print(f"- Total rounds: {rounds}")
    print(f"- Player action declarations: {player_declarations}")
    print(f"- NPC actions: {npc_actions}")
    print(f"- Action resolutions: {actions}")
    print(f"- Scenario setup: {type_counts.get('scenario', 0)}")
    print(f"- Round syntheses: {type_counts.get('round_synthesis', 0)}")
    print(f"- Mission debriefs: {type_counts.get('mission_debrief', 0)}")
    print(f"- Clock events: {type_counts.get('clock_advancement', 0)} advancements, {type_counts.get('clock_completion', 0)} completions")
    print(f"- Entity lifecycle events: {type_counts.get('entity_lifecycle', 0)}")
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
