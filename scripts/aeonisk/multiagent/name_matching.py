"""
Conservative fuzzy name matching for character names.

Handles cases where DM uses shortened names (e.g., "Sera Karsel" instead of "Vessel Sera Karsel").
Uses strict matching rules to avoid applying effects to wrong characters.

Author: Three Rivers AI Nexus
Date: 2025-11-24
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def match_character_name(
    provided_name: str,
    available_characters: List[str],
    context: str = "void_change"
) -> Tuple[Optional[str], bool, Optional[str]]:
    """
    Conservative fuzzy matching for character names.

    Strategy:
    1. Try exact match first
    2. Try suffix match (name ends with provided string)
    3. Require minimum 2 words (first + last name)
    4. Only match if EXACTLY ONE candidate
    5. Never guess on ambiguous matches

    Args:
        provided_name: Name from DM's structured output (e.g., "Sera Karsel")
        available_characters: List of full character names in scene
        context: Where this match is being used (for logging)

    Returns:
        Tuple of (matched_name, is_fuzzy_match, error_message)
        - matched_name: Full character name if matched, None if failed
        - is_fuzzy_match: True if fuzzy matching was used, False if exact
        - error_message: Error description if match failed, None if succeeded

    Examples:
        >>> match_character_name("Sera Karsel", ["Vessel Sera Karsel", "Guardian Rhea Ireveth"])
        ("Vessel Sera Karsel", True, None)

        >>> match_character_name("Vessel Sera Karsel", ["Vessel Sera Karsel"])
        ("Vessel Sera Karsel", False, None)

        >>> match_character_name("Sera", ["Vessel Sera Karsel", "Sera Thorne"])
        (None, False, "Ambiguous match: 'Sera' could match multiple characters...")

        >>> match_character_name("Bob", ["Vessel Sera Karsel"])
        (None, False, "No character found matching 'Bob'...")
    """
    if not provided_name or not available_characters:
        return None, False, "Empty name or no characters available"

    provided_name = provided_name.strip()

    # 1. Try exact match first (no fuzzing needed)
    for char_name in available_characters:
        if char_name == provided_name:
            return char_name, False, None

    # 2. Check minimum word count (prevent matching on single word like "Sera")
    words = provided_name.split()
    if len(words) < 2:
        return None, False, (
            f"Name too short for fuzzy matching: '{provided_name}' "
            f"(minimum 2 words required to avoid ambiguity)"
        )

    # 3. Try suffix match (character name ends with provided name)
    # This handles "Sera Karsel" matching "Vessel Sera Karsel"
    candidates = []
    for char_name in available_characters:
        if char_name.endswith(provided_name):
            candidates.append(char_name)

    # 4. Require exactly ONE match (no ambiguity)
    if len(candidates) == 0:
        # Show similar names for debugging
        similar = [c for c in available_characters if any(word in c for word in words)]
        if similar:
            return None, False, (
                f"No character found matching '{provided_name}'. "
                f"Available characters: {', '.join(available_characters)}. "
                f"Did you mean: {', '.join(similar)}?"
            )
        else:
            return None, False, (
                f"No character found matching '{provided_name}'. "
                f"Available characters: {', '.join(available_characters)}"
            )

    elif len(candidates) > 1:
        return None, False, (
            f"Ambiguous match: '{provided_name}' could match multiple characters: "
            f"{', '.join(candidates)}. Use full character name to disambiguate."
        )

    # 5. Single unambiguous match found
    matched_name = candidates[0]
    logger.info(
        f"Fuzzy match ({context}): '{provided_name}' → '{matched_name}' "
        f"(removed title prefix)"
    )
    return matched_name, True, None


def resolve_character_name(
    provided_name: str,
    registered_players: List[dict],
    context: str = "void_change"
) -> Tuple[Optional[str], bool, Optional[str]]:
    """
    Resolve character name using fuzzy matching against registered players.

    This is a convenience wrapper around match_character_name() that works
    with SharedState.registered_players format.

    Args:
        provided_name: Name from DM's structured output
        registered_players: List of dicts with 'name' field from SharedState
        context: Where this match is being used (for logging)

    Returns:
        Same as match_character_name()

    Example:
        >>> registered = [
        ...     {'agent_id': 'p1', 'name': 'Vessel Sera Karsel', 'faction': 'Tempest'},
        ...     {'agent_id': 'p2', 'name': 'Guardian Rhea Ireveth', 'faction': 'Pantheon'}
        ... ]
        >>> resolve_character_name("Sera Karsel", registered)
        ("Vessel Sera Karsel", True, None)
    """
    available_names = [p['name'] for p in registered_players]
    return match_character_name(provided_name, available_names, context)
