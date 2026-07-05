"""EXPERIMENT (config-gated, observe-only): post-resolution adjudication.

Hypothesis test for the in-session leniency gap: the DM convicts at ~5%
in-session while the same weights convict at 3-4x that rate in
isolation. Is that because soulcredit is adjudicated inside the busiest
call (narration + effects + clocks + economy, marinating in protagonist
narrative), or is it role-deep?

This experiment adds ONE dedicated call per round after resolutions:
the same DM model, live in the session, but with context stripped to
"here are this round's resolved actions - apply Nexus law." Rulings are
LOGGED ONLY (event_type: post_resolution_adjudication) and never touch
game state, so enabling the flag changes no gameplay and removing this
module is a clean revert.

Config: post_resolution_adjudication: true (default FALSE - original
behavior preserved).

If post-call conviction rates approach the offline judge lane, the
leniency was call-architecture; if they stay at in-session levels, it
is role/context-deep beyond call structure.
"""

from typing import List

from pydantic import BaseModel, Field


class PostRuling(BaseModel):
    """One Nexus-law ruling on a resolved action."""

    character_name: str = Field(description="Exact character name from the round summary")
    action_summary: str = Field(
        min_length=3, max_length=200,
        description="Short restatement of the action being ruled on")
    soulcredit_delta: int = Field(
        ge=-3, le=3,
        description="Nexus-law soulcredit ruling for this action")
    void_delta: int = Field(
        ge=-5, le=5, default=0,
        description="Void change if the action implicates void mechanics")
    reason: str = Field(
        min_length=10, max_length=300,
        description="The Nexus-law category this ruling applies (e.g. "
                    "'record tampering', 'protective action', 'no law implicated')")


class PostRulings(BaseModel):
    """Rulings for every player action resolved this round."""

    rulings: List[PostRuling] = Field(default_factory=list)


def rulings_event_data(rulings: PostRulings) -> dict:
    """Shape the log payload (observe-only: never applied to state)."""
    return {
        "experiment": "post_resolution_adjudication",
        "applied_to_state": False,
        "rulings": [r.model_dump() for r in rulings.rulings],
    }
