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

ENFORCE MODE (handoff task 1b(b), ledger-authority scope): when the flag
is 'enforce', the full-context magistrate's article-cited rulings become
the APPLIED soulcredit/void changes - the narrator writes the story, the
magistrate writes the ledger. `apply_rulings` is the sole writer in that
regime (the narration-call economy deltas are suppressed upstream so they
are not double-counted). Corpus label flips to v1.1-law-LIVE.
"""

import logging
from typing import Any, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Corpus regime label when magistrate rulings are the live ledger (enforce).
ENFORCE_REGIME_LABEL = "v1.1-law-LIVE"


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


def rulings_event_data(
    rulings: PostRulings,
    applied_to_state: bool = False,
    applied_records: Optional[List[dict]] = None,
    regime: Optional[str] = None,
) -> dict:
    """Shape the log payload.

    Default call (observe-only): byte-identical to the original experiment
    payload. Under enforce, pass applied_to_state=True plus the per-ruling
    application records and the regime label so the corpus is diff-able and
    self-labelling.
    """
    data = {
        "experiment": "post_resolution_adjudication",
        "applied_to_state": applied_to_state,
        "rulings": [r.model_dump() for r in rulings.rulings],
    }
    if applied_records is not None:
        data["applied"] = applied_records
    if regime:
        data["regime"] = regime
    return data


def apply_rulings(
    rulings: PostRulings,
    mechanics: Any,
    roster: List[dict],
    round_num: Optional[int] = None,
) -> List[dict]:
    """Apply magistrate rulings to game state (enforce mode, sole writer).

    Each ruling's character_name is resolved against the roster (exact then
    conservative fuzzy match via name_matching); the soulcredit/void deltas
    are written to the mechanics ledger. Unmatched names are logged loud and
    skipped - a phantom ruling never crashes the round. Returns a per-ruling
    record list for the JSONL event.

    Args:
        rulings: The magistrate's PostRulings for this round.
        mechanics: The live MechanicsEngine (soulcredit/void state owner).
        roster: registered_players dicts, each with 'agent_id' and 'name'.
        round_num: Current round, for soulcredit history.
    """
    from .name_matching import resolve_character_name

    name_to_id = {p["name"]: p["agent_id"] for p in roster}
    records: List[dict] = []

    for ruling in rulings.rulings:
        matched_name, is_fuzzy, error = resolve_character_name(
            ruling.character_name, roster, context="enforce_adjudication")
        if not matched_name:
            logger.warning(
                f"Enforce: could not match ruling target "
                f"'{ruling.character_name}': {error}")
            records.append({
                "character_name": ruling.character_name,
                "applied": False,
                "error": error,
            })
            continue

        agent_id = name_to_id[matched_name]

        if ruling.soulcredit_delta != 0:
            sc_state = mechanics.get_soulcredit_state(agent_id)
            sc_state.adjust(ruling.soulcredit_delta, ruling.reason,
                            round_num=round_num)

        if ruling.void_delta != 0:
            void_state = mechanics.get_void_state(agent_id)
            if ruling.void_delta > 0:
                void_state.add_void(ruling.void_delta, ruling.reason)
            else:
                void_state.reduce_void(abs(ruling.void_delta), ruling.reason)

        records.append({
            "character_name": matched_name,
            "agent_id": agent_id,
            "fuzzy_match": is_fuzzy,
            "soulcredit_delta": ruling.soulcredit_delta,
            "void_delta": ruling.void_delta,
            "reason": ruling.reason,
            "applied": True,
        })

    return records
