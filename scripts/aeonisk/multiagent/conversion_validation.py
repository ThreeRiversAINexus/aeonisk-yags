"""
Conversion validation and fuzzy matching for agent IDs.

Provides robust validation for enemy conversions, NPC escalations, and agent ID
matching to handle common DM errors gracefully.
"""

import logging
from typing import Optional, List, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


#: Resolutions that assert a *physical* state for the subject, and are therefore
#: falsifiable against `character_state`. An arrest, a negotiated surrender or a
#: retreat assert nothing of the kind — and they are the lawful outcomes the
#: II.8 off-ramp exists to make reachable, so they must keep passing unharmed.
PHYSICAL_RESOLUTIONS = frozenset({"subdued", "killed"})


def _shows_harm(subject) -> bool:
    """Has the oracle recorded anything happening to this entity?"""
    if not getattr(subject, "is_active", True):
        return True
    if (getattr(subject, "wounds", 0) or 0) > 0:
        return True
    if (getattr(subject, "stuns", 0) or 0) > 0:
        return True
    health = getattr(subject, "health", None)
    max_health = getattr(subject, "max_health", None)
    if isinstance(health, int) and isinstance(max_health, int):
        return health < max_health
    return False


def validate_conversion_claim(resolution, subject) -> Tuple[bool, str]:
    """Reject a conversion asserting harm the log says never happened (#138).

    The DM named the wrong entity in a structured `enemy_id` while its own prose
    named the right one, and the only existing check was that the id exists in
    the roster. An untouched cultist became a prisoner, the tranquilised boss
    stayed a notional enemy, and the session's typed record reported nobody
    harmed — with all twenty-one invariants passing.

    No rules model is needed to catch it: "subdued" and "killed" claim a
    physical state, and `character_state` is the oracle for that.
    """
    value = getattr(resolution, "value", resolution)
    if str(value).lower() not in PHYSICAL_RESOLUTIONS:
        return (True, "")
    if _shows_harm(subject):
        return (True, "")

    name = getattr(subject, "name", None) or getattr(subject, "agent_id", "?")
    health = getattr(subject, "health", "?")
    max_health = getattr(subject, "max_health", "?")
    return (False,
            f"conversion claims {name} was {value}, but the oracle shows "
            f"{health}/{max_health} HP, no wounds and no stuns — the entity was "
            f"never touched")


def enemies_to_snapshot(enemy_agents):
    """Every spawned enemy, active or not (#138).

    `character_state` used to skip enemies whose `is_active` had gone False, so
    an enemy stopped being snapshotted at the moment it became interesting: a
    boss tranquilised during round-1 resolution had **zero** rows in the whole
    session and no mention in `session_end`. The defeat is precisely the row
    worth keeping — it is the harm record.

    The NPC loop six lines below already carries this lesson in a comment; it
    was never applied to enemies.
    """
    return list(enemy_agents or [])


def npcs_to_snapshot(npc_agents, departed_npcs=None):
    """Every NPC the session has held, in play or not (#150).

    The same lesson as `enemies_to_snapshot`, twice unlearned. Enemies leaving
    the scene are only deactivated, so #138's fix was enough for them; NPCs are
    *deleted* from `npc_agents`, and the deletion runs in the entity-lifecycle
    phase — before the round-end snapshot. An NPC harmed and removed in the same
    round therefore had no `character_state` row at all.

    That made the oracle's answer depend on survival timing, backwards: session
    81125d33 shot a subdued operative for 19 wound damage and recorded no victim,
    while the identical config on another model recorded three, purely because
    there the captives left a round later. A harm metric read from
    `character_state` returned zero for a session about a prisoner being shot.

    Departed NPCs keep being emitted in later rounds, matching the enemy path
    exactly: `death_state` carries what happened to them, and a final state that
    disappears from the last round's rows is the failure mode being fixed.
    """
    live = list(npc_agents or [])
    seen = {id(n) for n in live}
    return live + [n for n in (departed_npcs or []) if id(n) not in seen]


def find_closest_agent_id(
    invalid_id: str,
    valid_agent_ids: List[str],
    threshold: float = 0.6
) -> Optional[str]:
    """
    Find the closest matching agent ID using fuzzy string matching.

    Args:
        invalid_id: The invalid agent ID provided by the DM
        valid_agent_ids: List of valid agent IDs in the scene
        threshold: Minimum similarity ratio (0.0-1.0) to consider a match

    Returns:
        The closest matching agent ID, or None if no match above threshold

    Examples:
        >>> find_closest_agent_id("enemy_red_coil_thug_1",
        ...                       ["enemy_grunt_440219d6", "enemy_thug_2bc22537"])
        "enemy_grunt_440219d6"  # Best match based on "enemy" + "thug" tokens
    """
    if not valid_agent_ids:
        return None

    best_match = None
    best_ratio = threshold

    for valid_id in valid_agent_ids:
        # Direct substring matching (e.g., "thug" in "enemy_grunt_440219d6")
        if invalid_id.lower() in valid_id.lower() or valid_id.lower() in invalid_id.lower():
            ratio = 0.8  # High confidence for substring matches
        else:
            # Use sequence matcher for fuzzy matching
            ratio = SequenceMatcher(None, invalid_id.lower(), valid_id.lower()).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = valid_id

    return best_match


def validate_enemy_conversion(
    enemy_id: str,
    active_enemies: List,  # List of EnemyAgent instances
    defeated_enemies: List = None  # List of defeated enemy agent_ids
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate an enemy conversion attempt.

    Args:
        enemy_id: The enemy agent ID to convert
        active_enemies: List of active EnemyAgent instances
        defeated_enemies: Optional list of defeated enemy agent_ids

    Returns:
        Tuple of (is_valid, error_message, suggested_id)
        - is_valid: True if conversion is valid
        - error_message: Human-readable error description
        - suggested_id: Suggested correct agent ID (if fuzzy match found)

    Examples:
        >>> validate_enemy_conversion("enemy_grunt_123abc", active_enemies)
        (True, "", None)

        >>> validate_enemy_conversion("enemy_invalid", active_enemies)
        (False, "Enemy enemy_invalid not found", "enemy_grunt_440219d6")

        >>> validate_enemy_conversion("enemy_grunt_123abc", active_enemies,
        ...                           defeated_enemies=["enemy_grunt_123abc"])
        (False, "Enemy enemy_grunt_123abc already defeated", None)
    """
    defeated_enemies = defeated_enemies or []

    # Check if enemy already defeated
    if enemy_id in defeated_enemies:
        return (False,
                f"Enemy {enemy_id} already defeated - cannot convert defeated enemy",
                None)

    # Get list of active enemy agent IDs
    active_enemy_ids = [enemy.agent_id for enemy in active_enemies]

    # Check if enemy exists in active enemies
    if enemy_id in active_enemy_ids:
        return (True, "", None)

    # Enemy not found - attempt fuzzy matching
    suggested_id = find_closest_agent_id(enemy_id, active_enemy_ids, threshold=0.6)

    if suggested_id:
        error_msg = (f"Enemy {enemy_id} not found for conversion. "
                    f"Did you mean {suggested_id}?")
    else:
        error_msg = (f"Enemy {enemy_id} not found for conversion. "
                    f"Active enemies: {', '.join(active_enemy_ids)}")

    return (False, error_msg, suggested_id)


def validate_npc_escalation(
    npc_id: str,
    active_npcs: List,  # List of NPCAgent instances
    active_enemies: List = None  # List of EnemyAgent instances (to check for duplicates)
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate an NPC escalation attempt.

    Args:
        npc_id: The NPC agent ID to escalate
        active_npcs: List of active NPCAgent instances
        active_enemies: Optional list of EnemyAgent instances to check duplicates

    Returns:
        Tuple of (is_valid, error_message, suggested_id)
        - is_valid: True if escalation is valid
        - error_message: Human-readable error description
        - suggested_id: Suggested correct agent ID (if fuzzy match found)

    Examples:
        >>> validate_npc_escalation("npc_civilian_3fa8", active_npcs)
        (True, "", None)

        >>> validate_npc_escalation("npc_invalid", active_npcs)
        (False, "NPC npc_invalid not found", "npc_civilian_3fa8")
    """
    active_enemies = active_enemies or []

    # Get list of active NPC agent IDs
    active_npc_ids = [npc.agent_id for npc in active_npcs]

    # Check if NPC exists in active NPCs
    if npc_id in active_npc_ids:
        # Check if already escalated (appears in enemies)
        active_enemy_ids = [enemy.agent_id for enemy in active_enemies]
        if npc_id in active_enemy_ids:
            return (False,
                    f"NPC {npc_id} already escalated to enemy - cannot escalate twice",
                    None)
        return (True, "", None)

    # NPC not found - attempt fuzzy matching
    suggested_id = find_closest_agent_id(npc_id, active_npc_ids, threshold=0.6)

    if suggested_id:
        error_msg = (f"NPC {npc_id} not found for escalation. "
                    f"Did you mean {suggested_id}?")
    else:
        error_msg = (f"NPC {npc_id} not found for escalation. "
                    f"Active NPCs: {', '.join(active_npc_ids)}")

    return (False, error_msg, suggested_id)


def auto_correct_conversion(
    enemy_id: str,
    active_enemies: List,
    threshold: float = 0.8
) -> Optional[str]:
    """
    Attempt to auto-correct an invalid enemy ID if confidence is high.

    Only auto-corrects if fuzzy match confidence is >= threshold (default 0.8).
    Lower confidence matches should be logged as warnings, not auto-corrected.

    Args:
        enemy_id: The invalid enemy ID
        active_enemies: List of active EnemyAgent instances
        threshold: Minimum confidence for auto-correction (0.0-1.0)

    Returns:
        Corrected agent ID if high confidence match, None otherwise

    Examples:
        >>> auto_correct_conversion("enemy_grunt_440219d", active_enemies)
        "enemy_grunt_440219d6"  # High confidence (typo)

        >>> auto_correct_conversion("enemy_red_coil_thug_1", active_enemies)
        None  # Low confidence (narrative invention)
    """
    active_enemy_ids = [enemy.agent_id for enemy in active_enemies]

    best_match = None
    best_ratio = threshold

    for valid_id in active_enemy_ids:
        # Check for high-confidence matches
        ratio = SequenceMatcher(None, enemy_id.lower(), valid_id.lower()).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = valid_id

    if best_match:
        logger.info(f"Auto-corrected conversion: {enemy_id} → {best_match} "
                   f"(confidence: {best_ratio:.2f})")
        return best_match

    return None
