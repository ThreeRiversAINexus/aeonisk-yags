"""Round-batch DM assessment of declared actions.

After the declaration phase, one DM call per round assesses every player
declaration: the authoritative difficulty, plus an optional override of
the player's attribute/skill framing when it is clearly mismatched to
the deed. The player's own difficulty_estimate stays logged in the
declaration event as a counterfactual - assessment never erases it.

Authority chain for the final DC:
  DM assessment -> calculate_dc floors (rituals >= CHALLENGING, etc.)
  -> roll. If the assessment call fails or omits an action, calculate_dc
  falls back to its category table, so sessions never stall on this.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .constants import ATTRIBUTES_STRING, YAGS_ATTRIBUTES
from .guard_log import record_guard_rejection

logger = logging.getLogger(__name__)


class ActionAssessment(BaseModel):
    """DM's ruling on one declared action."""

    character_name: str = Field(description="Exact declared character name")
    difficulty: int = Field(
        ge=5, le=40,
        description="Assessed DC from the fiction and stakes, not the "
                    "action category")
    attribute: Optional[str] = Field(
        default=None,
        description="Override ONLY if the player's attribute is clearly "
                    "wrong for the deed; null keeps the player's framing")
    skill: Optional[str] = Field(
        default=None,
        description="Override ONLY if the player's skill is clearly wrong "
                    "for the deed; null keeps the player's framing")
    reasoning: str = Field(
        min_length=10, max_length=300,
        description="Why this difficulty (and any reframing)")


class RoundAssessment(BaseModel):
    """DM's rulings for every player action declared this round."""

    assessments: List[ActionAssessment] = Field(default_factory=list)


def apply_assessments(
    declared_actions: Dict[str, List[Dict[str, Any]]],
    assessment: Optional[RoundAssessment],
    character_sheets: Dict[str, Tuple[Dict[str, int], Dict[str, int]]],
    mechanics: Any = None,
) -> List[str]:
    """Merge DM assessments into buffered action dicts, in place.

    Args:
        declared_actions: session._declared_actions - agent_id ->
            list of buffered {'action': {...}} dicts
        assessment: the DM's RoundAssessment (None = call failed; no-op)
        character_sheets: character_name -> (attributes, skills) for
            recomputing values when the DM reframes attribute/skill

    Returns:
        Human-readable change lines for logging (empty if nothing changed).

    Sets on each matched action dict:
        dm_assessed_difficulty - consumed as calculate_dc's proposed_dc
        dm_assessment_reason
        attribute/skill (+ recomputed attribute_value/skill_value) when
        the DM overrides the player's framing. A reframed skill the
        character lacks yields skill_value 0 - the unskilled rules apply,
        which is exactly the cost of misframing.
    """
    changes: List[str] = []
    if assessment is None or not assessment.assessments:
        return changes

    by_name = {a.character_name: a for a in assessment.assessments}

    for buffered_list in declared_actions.values():
        for buffered in buffered_list:
            action = buffered.get('action')
            if not isinstance(action, dict):
                continue
            name = (action.get('character_name') or action.get('character')
                    or '')
            ruling = by_name.get(name)
            if ruling is None:
                continue

            action['dm_assessed_difficulty'] = ruling.difficulty
            action['dm_assessment_reason'] = ruling.reasoning
            player_estimate = action.get('difficulty_estimate')
            if player_estimate and player_estimate != ruling.difficulty:
                changes.append(
                    f"{name}: difficulty {player_estimate} → "
                    f"{ruling.difficulty} (DM assessment)")

            attributes, skills = character_sheets.get(name, ({}, {}))

            if ruling.attribute and ruling.attribute != action.get('attribute'):
                if ruling.attribute not in YAGS_ATTRIBUTES:
                    # There are exactly eight attributes; a name outside that set
                    # cannot exist. Applying it anyway silently resolved to the
                    # `.get(..., 3)` default, rolling the action against a stat
                    # the character does not have (observed: "Presence").
                    # The player's framing stands; the difficulty ruling still does.
                    logger.warning(
                        f"Rejected DM attribute reframe for {name}: "
                        f"{ruling.attribute!r} is not a YAGS attribute "
                        f"({ATTRIBUTES_STRING})")
                    changes.append(
                        f"{name}: attribute reframe to {ruling.attribute} "
                        f"REJECTED (not a YAGS attribute)")
                    record_guard_rejection(
                        mechanics, getattr(mechanics, 'current_round', None),
                        guard='attribute_reframe', disposition='skipped',
                        requested=str(ruling.attribute),
                        reason=f'not one of the eight YAGS attributes '
                               f'({ATTRIBUTES_STRING})',
                        subject_id=name,
                        substituted=str(action.get('attribute')))
                else:
                    old = action.get('attribute')
                    action['attribute'] = ruling.attribute
                    action['attribute_value'] = attributes.get(ruling.attribute, 3)
                    changes.append(f"{name}: attribute {old} → {ruling.attribute} "
                                   f"(DM reframe)")

            if ruling.skill and ruling.skill != action.get('skill'):
                old = action.get('skill')
                action['skill'] = ruling.skill
                action['skill_value'] = skills.get(ruling.skill, 0)
                suffix = "" if action['skill_value'] else " - unskilled"
                changes.append(f"{name}: skill {old} → {ruling.skill} "
                               f"(DM reframe{suffix})")

    return changes
