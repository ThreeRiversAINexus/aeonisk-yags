#!/usr/bin/env python3
"""Analyze source attribution in JSONL logs."""
import json
import sys
from collections import Counter

sources = {'void': Counter(), 'soulcredit': Counter(), 'clocks': Counter()}

for line in sys.stdin:
    event = json.loads(line)
    if event.get('event_type') == 'action_resolution':
        economy = event.get('economy', {})

        # Track void sources
        if economy.get('void_delta', 0) != 0:
            void_src = economy.get('void_source', 'MISSING')
            sources['void'][void_src] += 1

        # Track soulcredit sources
        if economy.get('soulcredit_delta', 0) != 0:
            sc_src = economy.get('soulcredit_source', 'MISSING')
            sources['soulcredit'][sc_src] += 1

        # Track clock sources
        context = event.get('context', {})
        for clock_name, src in context.get('clock_sources', {}).items():
            sources['clocks'][src] += 1

print('=== SOURCE ATTRIBUTION STATS ===')
print()
print('VOID CHANGES:')
if sources['void']:
    for src, count in sources['void'].items():
        print(f'  {src}: {count}')
else:
    print('  (none)')
print()
print('SOULCREDIT CHANGES:')
if sources['soulcredit']:
    for src, count in sources['soulcredit'].items():
        print(f'  {src}: {count}')
else:
    print('  ⚠️  NO SOULCREDIT CHANGES DETECTED')
print()
print('CLOCK CHANGES:')
if sources['clocks']:
    for src, count in sources['clocks'].items():
        print(f'  {src}: {count}')
else:
    print('  (none)')
