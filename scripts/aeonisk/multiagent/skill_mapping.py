"""
Skill normalization and validation for Aeonisk YAGS.
"""

from typing import Dict, Optional, Tuple

# YAGS Core Skills
# Based on Aeonisk v1.2.2 module
SKILL_ALIASES = {
    # Social skills
    'social': 'Charm',
    'charm': 'Charm',
    'guile': 'Guile',
    'deception': 'Guile',
    'persuasion': 'Charm',
    'empathy': 'Charm',  # As a skill action

    # Investigation skills
    'investigation': 'Awareness',
    'investigate': 'Awareness',
    'awareness': 'Awareness',
    'perception': 'Awareness',  # As a skill action
    'search': 'Awareness',

    # Astral/Ritual skills
    'astral arts': 'Astral Arts',
    'astral': 'Astral Arts',
    'ritual': 'Astral Arts',

    # Technical skills
    'tech/craft': 'Tech/Craft',
    'tech': 'Tech/Craft',
    'craft': 'Tech/Craft',
    'technology': 'Tech/Craft',

    # Knowledge skills
    'magick theory': 'Magick Theory',
    'magic theory': 'Magick Theory',
    'theory': 'Magick Theory',
}

# Ritual rules: MUST use Willpower
RITUAL_ATTRIBUTE = 'Willpower'
RITUAL_SKILL = 'Astral Arts'


def normalize_skill(skill_name: Optional[str]) -> Optional[str]:
    """
    Normalize a skill name to its canonical form.

    Args:
        skill_name: Raw skill name from LLM or user (may include values like "Charm (5)")

    Returns:
        Canonical skill name, or None if skill_name is None
    """
    if skill_name is None:
        return None

    # Strip out any parenthetical values (e.g., "Social (5)" → "Social")
    import re
    skill_clean = re.sub(r'\s*\([^)]*\)', '', skill_name).strip()

    skill_lower = skill_clean.lower().strip()
    return SKILL_ALIASES.get(skill_lower, skill_clean)  # Return cleaned name if not found in aliases


def validate_ritual_mechanics(
    action_type: str,
    attribute: str,
    skill: Optional[str]
) -> Tuple[str, str]:
    """
    Enforce ritual mechanics rules.

    Aeonisk Module Rule: Rituals MUST use Willpower × Astral Arts

    Args:
        action_type: Type of action
        attribute: Proposed attribute
        skill: Proposed skill

    Returns:
        Tuple of (corrected_attribute, corrected_skill)
    """
    if action_type == 'ritual':
        # Force Willpower × Astral Arts for all rituals
        return (RITUAL_ATTRIBUTE, RITUAL_SKILL)

    return (attribute, skill)


def get_character_skill_value(
    character_skills: Dict[str, int],
    skill_name: Optional[str],
    fallback_value: int = 0
) -> int:
    """
    Get skill value from character sheet with normalization.

    Args:
        character_skills: Character's skill dict
        skill_name: Skill to look up (will be normalized)
        fallback_value: Value if skill not found

    Returns:
        Skill level
    """
    if skill_name is None:
        return fallback_value

    # Try exact match first
    if skill_name in character_skills:
        return character_skills[skill_name]

    # Try normalized match
    normalized = normalize_skill(skill_name)
    if normalized and normalized in character_skills:
        return character_skills[normalized]

    # No match - character doesn't have this skill
    return fallback_value


def validate_action_mechanics(
    action_type: str,
    attribute: str,
    skill: Optional[str],
    character_skills: Dict[str, int]
) -> Tuple[str, Optional[str], bool, str]:
    """
    Validate and correct action mechanics.

    Returns:
        Tuple of (corrected_attribute, corrected_skill, is_valid, error_message)
    """
    # Apply ritual rules
    corrected_attr, corrected_skill = validate_ritual_mechanics(action_type, attribute, skill)

    # Normalize skill
    if corrected_skill:
        corrected_skill = normalize_skill(corrected_skill)

    # IMPORTANT: Social actions should use social attributes (Empathy/Charisma), not Perception
    # If skill is social (Charm/Guile) or action_type is social, ensure appropriate attribute
    if corrected_skill in ['Charm', 'Guile'] or action_type == 'social':
        if corrected_attr not in ['Empathy', 'Charisma']:
            # Prefer Empathy for most social interactions
            corrected_attr = 'Empathy'

    # Check if character has the skill
    if corrected_skill:
        skill_value = get_character_skill_value(character_skills, corrected_skill, 0)
        if skill_value == 0:
            # Character doesn't have this skill - use unskilled with correct attribute
            # Keep the appropriate attribute for the action type
            return (
                corrected_attr,
                None,  # Use raw attribute check (unskilled penalty applies)
                True,
                f"Character lacks {corrected_skill}, using raw {corrected_attr} check"
            )

    # Ensure we never return string "None" as a skill
    if corrected_skill and corrected_skill.lower() == 'none':
        corrected_skill = None

    return (corrected_attr, corrected_skill, True, "")
