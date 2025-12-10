#!/usr/bin/env python3
"""
Automated fix for test_yags_conformance.py signatures.
Replaces old character_state pattern with direct attribute/skill values.
"""

import re
from pathlib import Path

def extract_attribute_value(text, before_resolve_idx, attr_name):
    """Extract attribute value from character_state.attributes definition."""
    # Look backwards from resolve_action call to find character_state.attributes
    lines_before = text[:before_resolve_idx].split('\n')
    for line in reversed(lines_before[-20:]):  # Check last 20 lines
        if f'"{attr_name}":' in line:
            match = re.search(rf'"{attr_name}":\s*(\d+)', line)
            if match:
                return int(match.group(1))
    return None

def extract_skill_value(text, before_resolve_idx, skill_name):
    """Extract skill value from character_state.skills definition."""
    if not skill_name or skill_name == 'None':
        return 0

    lines_before = text[:before_resolve_idx].split('\n')
    for line in reversed(lines_before[-20:]):
        if f'"{skill_name}":' in line:
            match = re.search(rf'"{skill_name}":\s*(\d+)', line)
            if match:
                return int(match.group(1))
    return 0  # Unskilled if not found

def fix_test_signatures():
    file_path = Path("tests/unit/test_yags_conformance.py")
    content = file_path.read_text()

    # Pattern to match old-style resolve_action calls
    pattern = re.compile(
        r'mechanics\.resolve_action\(\s*'
        r'character_name="[^"]*",\s*'
        r'attribute="([^"]*)",\s*'
        r'skill=(None|"[^"]*"),\s*'
        r'difficulty=(\d+),\s*'
        r'intent="([^"]*)",\s*'
        r'character_state=\w+\s*'
        r'\)',
        re.DOTALL
    )

    def replacement(match):
        attribute = match.group(1)
        skill_raw = match.group(2)
        difficulty = match.group(3)
        intent = match.group(4)

        # Extract skill name
        skill_name = None if skill_raw == 'None' else skill_raw.strip('"')

        # Find attribute and skill values from context
        before_match_idx = match.start()
        attr_value = extract_attribute_value(content, before_match_idx, attribute)
        skill_value = extract_skill_value(content, before_match_idx, skill_name)

        if attr_value is None:
            print(f"WARNING: Could not find {attribute} value, using placeholder")
            attr_value = "UNKNOWN"

        # Format skill parameter
        skill_param = "None" if skill_name is None else f'"{skill_name}"'

        return (
            f'mechanics.resolve_action(\n'
            f'                intent="{intent}",\n'
            f'                attribute="{attribute}",\n'
            f'                skill={skill_param},\n'
            f'                attribute_value={attr_value},\n'
            f'                skill_value={skill_value},\n'
            f'                difficulty={difficulty}\n'
            f'            )'
        )

    # Apply replacements
    new_content = pattern.sub(replacement, content)

    # Remove character_state Mock definitions (now unused)
    # Keep only the mechanics = MechanicsEngine() lines
    new_content = re.sub(
        r'\n\s*character_state = Mock\(\)\s*\n'
        r'\s*character_state\.name = "[^"]*"\s*\n'
        r'\s*character_state\.attributes = \{[^}]*\}\s*\n'
        r'(\s*character_state\.skills = \{[^}]*\}\s*\n)?',
        '\n',
        new_content
    )

    # Write fixed content
    file_path.write_text(new_content)
    print(f"✓ Fixed {file_path}")
    print(f"  Original resolve_action calls: {len(pattern.findall(content))}")
    print(f"  character_state definitions removed")

if __name__ == '__main__':
    fix_test_signatures()
