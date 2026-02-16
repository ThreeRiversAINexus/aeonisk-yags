import json, glob, os

base = 'multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_113048_5276cf26'
runs = ['run_0001','run_0002','run_0003','run_0005','run_0006','run_0007','run_0008','run_0010','run_0011','run_0012','run_0013','run_0015','run_0016','run_0017','run_0018','run_0020','run_0021','run_0022','run_0023','run_0025']

model_map = {}
for r in runs:
    num = int(r.split('_')[1])
    if num in [1,6,11,16,21]: model_map[r] = 'GPT-5.2'
    elif num in [2,7,12,17,22]: model_map[r] = 'Grok 4'
    elif num in [3,8,13,18,23]: model_map[r] = 'Gemini 2.5 Pro'
    elif num in [5,10,15,20,25]: model_map[r] = 'DeepSeek V3.2'

for run in runs:
    jsonl_files = glob.glob(os.path.join(base, run, 'session_*.jsonl'))
    if not jsonl_files: continue
    
    events = []
    with open(jsonl_files[0]) as f:
        for line in f:
            events.append(json.loads(line.strip()))
    
    # Find NPC attack declarations
    npc_attacks = []
    for e in events:
        if e.get('event_type') != 'action_declaration': continue
        pid = e.get('player_id', '')
        if not pid.startswith('npc_'): continue
        action = e.get('action', {})
        if not isinstance(action, dict): continue
        major = action.get('major_action', '')
        if major.lower() != 'attack': continue
        npc_attacks.append({
            'run': run,
            'model': model_map[run],
            'round': e.get('round'),
            'npc_id': pid,
            'npc_name': e.get('character_name', pid),
            'target': action.get('target', 'unknown'),
            'description': (action.get('description', '') or '')[:250],
        })
    
    # Find NPC action_resolution events (phase adjudicate_npc) that might be attacks
    npc_resolutions = []
    for e in events:
        if e.get('event_type') != 'action_resolution': continue
        phase = e.get('phase', '')
        if 'npc' not in phase: continue
        agent = e.get('agent', '')
        effects = e.get('effects', {}) or {}
        damage = effects.get('damage', {}) or {}
        damage_effects = effects.get('damage_effects', []) or []
        status_effects = effects.get('status_effects', []) or []
        context = e.get('context', {}) or {}
        ctx_dmg = context.get('damage_effects', []) or []
        action_type = context.get('action_type', '')
        narration = e.get('narration', '') or e.get('description', '') or ''
        
        dealt = damage.get('dealt', 0) or 0
        is_attack = dealt > 0 or action_type == 'attack' or any((d.get('damage_dealt', 0) or 0) > 0 for d in ctx_dmg if isinstance(d, dict))
        
        if not is_attack:
            combined = (narration + str(context)).lower()
            if any(kw in combined for kw in ['attack', 'fire', 'shoot', 'strike', 'blast', 'slash']):
                is_attack = True
        
        if is_attack or action_type == 'attack':
            npc_resolutions.append({
                'run': run,
                'model': model_map[run],
                'round': e.get('round'),
                'agent': agent,
                'action_type': action_type,
                'damage_dealt': dealt,
                'damage_target': damage.get('target', 'none'),
                'ctx_damage_effects': ctx_dmg,
                'status_effects': status_effects,
                'narration': narration[:300],
            })
    
    # Find entity_lifecycle events for NPC escalations
    npc_escalations = []
    for e in events:
        if e.get('event_type') != 'entity_lifecycle': continue
        details = e.get('details', {}) or {}
        conversions = details.get('conversion_decisions', {}) or {}
        escalations = conversions.get('escalations', []) or []
        for esc in escalations:
            npc_escalations.append({
                'run': run,
                'model': model_map[run],
                'round': e.get('round'),
                'entity': esc if isinstance(esc, str) else json.dumps(esc)[:200],
            })
    
    if npc_attacks or npc_resolutions or npc_escalations:
        print(f'\n{"="*80}')
        print(f'{run} ({model_map[run]})')
        print(f'{"="*80}')
    
    if npc_attacks:
        print(f'\n  NPC ATTACK DECLARATIONS ({len(npc_attacks)}):')
        for a in npc_attacks:
            print(f'    R{a["round"]} | {a["npc_name"]}')
            print(f'      Target: {a["target"]}')
            print(f'      Description: {a["description"][:200]}')
            print()
    
    if npc_resolutions:
        print(f'  NPC ATTACK RESOLUTIONS ({len(npc_resolutions)}):')
        for r_item in npc_resolutions:
            print(f'    R{r_item["round"]} | {r_item["agent"]} | action_type={r_item["action_type"]}')
            print(f'      Damage dealt: {r_item["damage_dealt"]} to {r_item["damage_target"]}')
            if r_item['ctx_damage_effects']:
                print(f'      ctx.damage_effects: {json.dumps(r_item["ctx_damage_effects"])[:200]}')
            if r_item['status_effects']:
                print(f'      Status effects: {r_item["status_effects"]}')
            print(f'      Narration: {r_item["narration"][:250]}')
            print()
    
    if npc_escalations:
        print(f'  NPC ESCALATIONS ({len(npc_escalations)}):')
        for esc in npc_escalations:
            print(f'    R{esc["round"]} | {esc["entity"]}')
            print()

# Also check combat_action events for NPC involvement
print(f'\n{"="*80}')
print('COMBAT_ACTION events involving NPCs')
print(f'{"="*80}')

found_any = False
for run in runs:
    jsonl_files = glob.glob(os.path.join(base, run, 'session_*.jsonl'))
    if not jsonl_files: continue
    
    with open(jsonl_files[0]) as f:
        for line in f:
            e = json.loads(line.strip())
            if e.get('event_type') != 'combat_action': continue
            attacker = e.get('attacker', {}) or {}
            defender = e.get('defender', {}) or {}
            att_id = attacker.get('id', '') or ''
            def_id = defender.get('id', '') or ''
            if att_id.startswith('npc_') or def_id.startswith('npc_'):
                found_any = True
                damage = e.get('damage', {}) or {}
                weapon = e.get('weapon', {})
                if isinstance(weapon, dict):
                    weapon_name = weapon.get('name', 'unknown')
                else:
                    weapon_name = str(weapon)
                print(f'  {run} ({model_map[run]}) R{e.get("round")}:')
                print(f'    Attacker: {attacker.get("name", att_id)} ({att_id})')
                print(f'    Defender: {defender.get("name", def_id)} ({def_id})')
                print(f'    Weapon: {weapon_name}')
                print(f'    Result: {e.get("result", "unknown")}, Damage dealt: {damage.get("dealt", 0)}')
                print()

if not found_any:
    print('  (none found)')
