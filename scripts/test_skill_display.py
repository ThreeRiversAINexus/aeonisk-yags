#!/usr/bin/env python3
"""
Test script for new tiered skill display.
"""

import sys
sys.path.insert(0, '/home/p/Coding/aeonisk-yags/scripts')

from aeonisk.multiagent.enhanced_prompts import _format_tiered_skills

# Test with a sample character
test_character_skills = {
    "Charm": 5,
    "Awareness": 4,
    "Astral Arts": 4,
    "Intimacy Ritual": 3,
    "Systems": 3,
    "Magick Theory": 2,
    "Stealth": 2,
    "Brawl": 2
}

print("=" * 80)
print("TIERED SKILL DISPLAY TEST")
print("=" * 80)
print()

skills_output = _format_tiered_skills(test_character_skills)
print(skills_output)

print()
print("=" * 80)
print("Token count estimate:", len(skills_output.split()))
print("=" * 80)
