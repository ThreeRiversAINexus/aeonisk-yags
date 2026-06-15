"""
Skill normalization and validation for Aeonisk YAGS.
"""

from typing import Dict, Optional, Tuple

# YAGS Core Skills + Aeonisk-Specific Skills
# Based on Aeonisk v1.2.2 module
SKILL_ALIASES = {
    # Social skills (YAGS Base Talents)
    'social': 'Charm',
    'charm': 'Charm',
    'guile': 'Guile',
    'deception': 'Guile',
    'persuasion': 'Charm',  # 21 configs use this
    'empathy': 'Charm',  # As a skill action

    # Investigation skills (YAGS Base)
    'investigation': 'Awareness',
    'investigate': 'Awareness',
    'awareness': 'Awareness',
    'perception': 'Awareness',  # As a skill action
    'search': 'Awareness',
    'observation': 'Awareness',  # 1 config uses this

    # Combat skills (YAGS Base)
    'combat': 'Combat',
    'melee': 'Melee',
    'brawl': 'Brawl',
    'guns': 'Guns',

    # Movement skills (YAGS Base)
    'athletics': 'Athletics',
    'stealth': 'Stealth',

    # Astral/Ritual skills (Aeonisk-Specific)
    'astral arts': 'Astral Arts',
    'astral': 'Astral Arts',
    'ritual': 'Astral Arts',
    'attunement': 'Attunement',  # Optional Aeonisk skill for sensing/ritual attuning

    # Technical skills (YAGS Base + Aeonisk)
    'tech/craft': 'Tech/Craft',
    'tech': 'Tech/Craft',
    'craft': 'Tech/Craft',
    'technology': 'Tech/Craft',
    'engineering': 'Tech/Craft',  # 16 configs use this
    'systems': 'Systems',  # Technical systems operation
    'drone operation': 'Drone Operation',  # Aeonisk-Specific
    'pilot': 'Pilot',  # Aeonisk-Specific

    # Knowledge skills (YAGS Base + Aeonisk)
    'magic theory': 'Magic Theory',
    'magick theory': 'Magic Theory',
    'theory': 'Magic Theory',

    # Aeonisk-Specific Social/Economic Skills
    'corporate influence': 'Corporate Influence',
    'debt law': 'Debt Law',
    'intimacy ritual': 'Intimacy Ritual',

    # Counseling/Support (YAGS Base or custom)
    'counsel': 'Counsel',
    'counseling': 'Counsel',
    'healing': 'Healing',

    # Willpower skills
    'discipline': 'Discipline',
    'meditation': 'Discipline',  # 5 configs use this
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
    Enforce ritual mechanics rules with proper skill routing.

    Ritual Rules:
    - Void manipulation rituals: Willpower × Astral Arts
    - Intimacy/social rituals: Use Intimacy Ritual skill (if specified)
    - Investigation of rituals: Use Magic Theory (not Astral Arts)
    - Default rituals: Willpower × Astral Arts

    Args:
        action_type: Type of action
        attribute: Proposed attribute
        skill: Proposed skill (may already be normalized)

    Returns:
        Tuple of (corrected_attribute, corrected_skill)
    """
    if action_type == 'ritual':
        # Normalize skill to check what was intended
        normalized_skill = normalize_skill(skill) if skill else None

        # Intimacy rituals use their own skill
        if normalized_skill == 'Intimacy Ritual':
            return (RITUAL_ATTRIBUTE, normalized_skill)

        # Magic Theory is for investigating/analyzing rituals, not performing them
        # If someone is "investigating a ritual", it's not action_type='ritual'
        # So if we're here with Magic Theory, it's likely misclassified
        # Keep it but flag for review
        if normalized_skill == 'Magic Theory':
            return (attribute, normalized_skill)  # Don't force Willpower for investigation

        # All other rituals (void manipulation, binding, etc.) use Astral Arts
        if normalized_skill != 'Astral Arts':
            return (RITUAL_ATTRIBUTE, RITUAL_SKILL)

        # Already using Astral Arts, ensure Willpower
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

    # IMPORTANT: Social actions should use social attributes (Empathy or Willpower), not Perception
    # If skill is social (Charm/Guile) or action_type is social, ensure appropriate attribute
    if corrected_skill in ['Charm', 'Guile'] or action_type == 'social':
        if corrected_attr not in ['Empathy', 'Willpower']:
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


# =============================================================================
# SESSION CONFIG SKILL VALIDATION
# =============================================================================

# Non-canonical skill names that are commonly misused, with their canonical equivalents
NON_CANONICAL_SKILL_MAP = {
    # Common mistakes - Social
    "Notice": "Awareness",
    "Deception": "Guile",
    "Persuasion": "Charm",
    "Empathy": "Charm",  # Empathy is an attribute, Charm is the skill
    "Social": "Charm",
    "Negotiation": "Charm",
    "Negotiate": "Charm",

    # Observation/Investigation variants
    "Observation": "Awareness",
    "Perception": "Awareness",  # As a skill (not attribute)
    "Search": "Awareness",
    "Investigate": "Awareness",  # Use Investigation for the skill, Awareness for passive

    # Technical variants
    "Engineering": "Tech/Craft",
    "Computers": "Systems",

    # Combat variants
    "Small Arms": "Guns",
    "Melee Combat": "Melee",

    # Knowledge variants
    "Magick Theory": "Magic Theory",
    "Meditation": "Discipline",
    "Ritual Knowledge": "Ritual Lore",
    "Occult": "Magic Theory",
    "Void Sense": "Attunement",  # Sensing void energies

    # Aeonisk ritual variants
    "Astral Rituals": "Astral Arts",

    # Survival (not in YAGS - map to closest)
    "Survival": "Resistance",

    # For documentation - these ARE canonical
    # "Investigation": "Investigation",
}


def get_canonical_skills() -> set:
    """
    Get the set of all canonical skill names from the skill database.

    Returns:
        Set of canonical skill names
    """
    from .skill_descriptions import SKILL_DATABASE
    return set(SKILL_DATABASE.keys())


def is_canonical_skill(skill_name: str) -> bool:
    """
    Check if a skill name is in the canonical skill database.

    Args:
        skill_name: Skill name to check

    Returns:
        True if canonical, False otherwise
    """
    canonical_skills = get_canonical_skills()
    return skill_name in canonical_skills


def get_canonical_suggestion(skill_name: str) -> Optional[str]:
    """
    Get the canonical skill name suggestion for a non-canonical skill.

    Args:
        skill_name: Non-canonical skill name

    Returns:
        Suggested canonical skill name, or None if no suggestion
    """
    # Check known non-canonical mappings first
    if skill_name in NON_CANONICAL_SKILL_MAP:
        return NON_CANONICAL_SKILL_MAP[skill_name]

    # Try the normalize function
    normalized = normalize_skill(skill_name)
    if normalized and is_canonical_skill(normalized):
        return normalized

    return None


def validate_character_skills(
    character_name: str,
    skills: Dict[str, int],
    raise_on_error: bool = True
) -> Tuple[bool, list]:
    """
    Validate that all skills in a character's skill dict use canonical names.

    Args:
        character_name: Name of the character (for error messages)
        skills: Character's skill dict {skill_name: level}
        raise_on_error: If True, raise ValueError on non-canonical skills

    Returns:
        Tuple of (is_valid, list of error messages)

    Raises:
        ValueError: If raise_on_error=True and non-canonical skills found
    """
    canonical_skills = get_canonical_skills()
    errors = []

    for skill_name in skills.keys():
        if skill_name not in canonical_skills:
            suggestion = get_canonical_suggestion(skill_name)
            if suggestion:
                msg = f"Character '{character_name}' uses non-canonical skill '{skill_name}'. Use '{suggestion}' instead."
            else:
                msg = f"Character '{character_name}' uses unknown skill '{skill_name}'. Valid skills: {sorted(canonical_skills)[:10]}..."
            errors.append(msg)

    is_valid = len(errors) == 0

    if not is_valid and raise_on_error:
        raise ValueError("\n".join(errors))

    return is_valid, errors


def validate_session_config_skills(config: dict, raise_on_error: bool = True) -> Tuple[bool, list]:
    """
    Validate all character skills in a session config use canonical names.

    Args:
        config: Session config dict
        raise_on_error: If True, raise ValueError on non-canonical skills

    Returns:
        Tuple of (is_valid, list of all error messages)

    Raises:
        ValueError: If raise_on_error=True and non-canonical skills found
    """
    all_errors = []

    # Check player characters
    agents = config.get('agents', {})
    players = agents.get('players', [])

    for player in players:
        name = player.get('name', 'Unknown')
        skills = player.get('skills', {})
        is_valid, errors = validate_character_skills(name, skills, raise_on_error=False)
        all_errors.extend(errors)

    is_valid = len(all_errors) == 0

    if not is_valid and raise_on_error:
        raise ValueError(f"Session config has non-canonical skill names:\n" + "\n".join(all_errors))

    return is_valid, all_errors
