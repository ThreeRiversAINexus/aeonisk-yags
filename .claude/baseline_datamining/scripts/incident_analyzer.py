#!/usr/bin/env python3
"""Analyze JSONL session files for specific morally dubious incidents."""
import json
import sys
import os

def load_events(filepath):
    events = []
    with open(filepath) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                e['_line'] = i + 1
                events.append(e)
            except json.JSONDecodeError:
                pass
    return events

def print_separator(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")

def extract_round_events(events, round_num, event_types=None):
    """Extract events for a specific round."""
    results = []
    for e in events:
        r = e.get('round')
        if r == round_num:
            if event_types is None or e.get('event_type') in event_types:
                results.append(e)
    return results

def print_action_declaration(e, indent="  "):
    """Print action_declaration details."""
    action = e.get('action', {})
    print(f"{indent}Agent: {e.get('agent', 'unknown')}")
    print(f"{indent}Agent Type: {e.get('agent_type', 'unknown')}")
    print(f"{indent}Round: {e.get('round')}")
    print(f"{indent}Action Type: {action.get('action_type', 'unknown')}")
    print(f"{indent}Intent: {action.get('intent', 'N/A')}")
    desc = action.get('description', 'N/A')
    print(f"{indent}Description: {desc[:500]}")
    print(f"{indent}Target: {action.get('target', 'N/A')}")
    print(f"{indent}Target Position: {action.get('target_position', 'N/A')}")
    print(f"{indent}Skill: {action.get('skill', 'N/A')}")
    print(f"{indent}Difficulty: {action.get('difficulty', 'N/A')}")
    # Check for any target-related fields
    for key in sorted(action.keys()):
        if 'target' in key.lower() and key not in ('target', 'target_position'):
            print(f"{indent}{key}: {action[key]}")

def print_action_resolution(e, indent="  "):
    """Print action_resolution details."""
    print(f"{indent}Agent: {e.get('agent', 'unknown')}")
    print(f"{indent}Round: {e.get('round')}")
    print(f"{indent}Phase: {e.get('phase', 'N/A')}")
    narration = e.get('narration', 'N/A')
    print(f"{indent}Narration (first 500): {narration[:500]}")
    effects = e.get('effects', {})
    if effects:
        print(f"{indent}Effects: {json.dumps(effects, indent=4)[:1000]}")
    roll = e.get('roll', {})
    if roll:
        print(f"{indent}Roll: {json.dumps(roll, indent=4)[:500]}")

def print_combat_action(e, indent="  "):
    """Print combat_action details."""
    print(f"{indent}Round: {e.get('round')}")
    attacker = e.get('attacker', {})
    print(f"{indent}Attacker: {attacker.get('name', 'unknown')} (id={attacker.get('id', '?')}, type={attacker.get('type', '?')})")
    defender = e.get('defender', {})
    print(f"{indent}Defender: {defender.get('name', 'unknown')} (id={defender.get('id', '?')}, type={defender.get('type', '?')})")
    attack = e.get('attack', {})
    print(f"{indent}Attack: weapon={attack.get('weapon', '?')}, skill={attack.get('skill', '?')}, d20={attack.get('d20', '?')}, attack_score={attack.get('attack_score', '?')}")
    damage = e.get('damage', {})
    print(f"{indent}Damage: dealt={damage.get('dealt', 0)}, base={damage.get('base', 0)}, soak={damage.get('soak', 0)}, raw={damage.get('raw', 0)}")
    result = e.get('result', {})
    print(f"{indent}Result: hit={result.get('hit', '?')}, wound={result.get('wound', '?')}")
    print(f"{indent}Defender HP: {e.get('defender_hp_before', '?')} -> {e.get('defender_hp_after', '?')}")

def print_entity_lifecycle(e, indent="  "):
    """Print entity_lifecycle details."""
    print(f"{indent}Round: {e.get('round')}")
    print(f"{indent}Event: {e.get('lifecycle_event', 'unknown')}")
    print(f"{indent}Entity: {e.get('entity_name', 'unknown')} (id={e.get('entity_id', '?')})")
    print(f"{indent}Entity Type: {e.get('entity_type', 'unknown')}")
    details = e.get('details', {})
    if details:
        print(f"{indent}Details: {json.dumps(details, indent=4)[:500]}")

def print_round_synthesis(e, indent="  "):
    """Print round_synthesis details."""
    print(f"{indent}Round: {e.get('round')}")
    narration = e.get('narration', '')
    print(f"{indent}Narration (first 500): {narration[:500]}")
    deesc = e.get('deescalations', [])
    if deesc:
        print(f"{indent}Deescalations: {json.dumps(deesc, indent=4)}")
    esc = e.get('escalations', [])
    if esc:
        print(f"{indent}Escalations: {json.dumps(esc, indent=4)}")
    npc_spawns = e.get('npc_spawns', [])
    if npc_spawns:
        print(f"{indent}NPC Spawns: {json.dumps(npc_spawns, indent=4)}")

def print_round_events(events, round_num):
    """Print all relevant events for a round."""
    print_separator(f"ROUND {round_num}")
    
    round_events = [e for e in events if e.get('round') == round_num]
    
    # Group by event type but print in chronological order
    for e in round_events:
        et = e.get('event_type', 'unknown')
        print(f"\n  --- {et} (line {e.get('_line', '?')}) ---")
        
        if et == 'action_declaration':
            print_action_declaration(e)
        elif et == 'action_resolution':
            print_action_resolution(e)
        elif et == 'combat_action':
            print_combat_action(e)
        elif et == 'entity_lifecycle':
            print_entity_lifecycle(e)
        elif et == 'round_synthesis':
            print_round_synthesis(e)
        elif et == 'round_start':
            combatants = e.get('combatants', [])
            print(f"  Combatants ({len(combatants)}):")
            for c in combatants:
                print(f"    - {c.get('name', '?')} (id={c.get('id', '?')}, type={c.get('type', '?')}, "
                      f"hp={c.get('hp', '?')}/{c.get('max_hp', '?')}, "
                      f"status={c.get('status', '?')}, "
                      f"is_defeated={c.get('is_defeated', '?')})")
        elif et == 'dm_response':
            narration = e.get('narration', '')
            print(f"  Narration (first 500): {narration[:500]}")
        else:
            # Print raw for other types
            safe = {k:v for k,v in e.items() if k != '_line'}
            print(f"  {json.dumps(safe, indent=4)[:800]}")

def find_combat_actions_against(events, target_name_fragment):
    """Find combat_action events where defender name contains fragment."""
    results = []
    for e in events:
        if e.get('event_type') == 'combat_action':
            defender = e.get('defender', {})
            dname = defender.get('name', '')
            if target_name_fragment.lower() in dname.lower():
                results.append(e)
    return results

def find_target_mappings(events):
    """Find any target_assignment or target_mapping events."""
    results = []
    for e in events:
        et = e.get('event_type', '')
        if 'target' in et.lower() or 'mapping' in et.lower() or 'assign' in et.lower():
            results.append(e)
    return results

def analyze_all_declarations(events):
    """Check what target format declarations use."""
    decls = [e for e in events if e.get('event_type') == 'action_declaration']
    for d in decls:
        action = d.get('action', {})
        target = action.get('target', '')
        if target and 'tgt_' in str(target):
            print(f"  Round {d.get('round')}: {d.get('agent')} -> tgt ID: {target} (FREE TARGETING)")
        elif target:
            print(f"  Round {d.get('round')}: {d.get('agent')} -> Named target: {target}")

if __name__ == '__main__':
    pass
