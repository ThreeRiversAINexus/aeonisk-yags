#!/usr/bin/env python3
"""
Fix test_yags_conformance.py to use correct resolve_action() signature.
"""

import re
from pathlib import Path

def fix_test_file():
    file_path = Path("tests/unit/test_yags_conformance.py")
    content = file_path.read_text()

    # Pattern to match resolve_action calls with old signature
    # This pattern captures the entire resolve_action call
    pattern = r'mechanics\.resolve_action\(\s*character_name="[^"]*",\s*attribute="([^"]*)",\s*skill=(None|"[^"]*"),\s*difficulty=(\d+),\s*intent="([^"]*)",\s*character_state=(\w+)\s*\)'

    def replacement(match):
        attribute = match.group(1)
        skill = match.group(2)
        difficulty = match.group(3)
        intent = match.group(4)
        char_state_var = match.group(5)

        # Extract attribute value and skill value from the character_state
        # We need to find these in the context
        return f'mechanics.resolve_action(\n                intent="{intent}",\n                attribute="{attribute}",\n                skill={skill},\n                attribute_value=NEED_VALUE,\n                skill_value=NEED_VALUE,\n                difficulty={difficulty}\n            )'

    # Actually, this is complex - let me just do manual replacements for each test
    # Let's read and understand the structure better

    lines = content.split('\n')

    # Track what needs to be fixed
    for i, line in enumerate(lines):
        if 'character_name=' in line and 'resolve_action' in lines[max(0, i-3):i+1]:
            print(f"Line {i+1}: {line.strip()[:80]}")

    print("\n\nTotal lines:", len(lines))
    print("character_state = Mock() occurrences:", content.count('character_state = Mock()'))
    print("resolve_action calls:", content.count('resolve_action('))

if __name__ == '__main__':
    fix_test_file()
