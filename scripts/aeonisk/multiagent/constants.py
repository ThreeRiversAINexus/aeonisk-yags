"""
Canonical game constants - SINGLE SOURCE OF TRUTH.

This file prevents drift like the "Charisma creep" incident where attributes
were hardcoded in 9 different locations, causing inconsistencies.

When modifying attributes, skills, or other game constants:
1. Update this file ONLY
2. Run: python -m pytest tests/unit/test_constants_alignment.py
3. The test will verify all references remain correct

See .claude/SINGLE_SOURCE_OF_TRUTH.md for architecture philosophy.
"""

# ======================
# YAGS CORE ATTRIBUTES
# ======================

YAGS_ATTRIBUTES = [
    "Strength",
    "Agility",
    "Endurance",
    "Dexterity",
    "Perception",
    "Intelligence",
    "Empathy",
    "Willpower"
]

# Helper for Pydantic Field descriptions
ATTRIBUTES_STRING = ", ".join(YAGS_ATTRIBUTES)

# ======================
# YAGS SECONDARY STATS
# ======================

YAGS_SECONDARY_STATS = ["Size"]

# ======================
# DIFFICULTY SCALES
# ======================

DIFFICULTY_RANGES = {
    10: "Easy",
    15: "Moderate",
    20: "Challenging",
    25: "Hard",
    30: "Very Hard",
    35: "Extremely Hard",
    40: "Nearly Impossible"
}

# Helper for prompt generation
DIFFICULTY_GUIDANCE = "\n".join([
    f"- {dc}: {desc}" for dc, desc in DIFFICULTY_RANGES.items()
])

# ======================
# ATTRIBUTE DEFAULTS
# ======================

# Default attribute values for incomplete configs (backwards compatibility)
DEFAULT_ATTRIBUTES = {
    "Strength": 3,
    "Agility": 3,
    "Endurance": 3,
    "Dexterity": 3,
    "Perception": 3,
    "Intelligence": 3,
    "Empathy": 3,
    "Willpower": 3,
    "Size": 5  # Secondary stat default
}
