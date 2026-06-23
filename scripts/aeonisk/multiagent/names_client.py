"""yags-side wrapper around aeonisk-names-mcp.

Direct Python import (not MCP stdio/HTTP) — both repos are Python, the
generator is sync, and yags has no existing MCP-client infrastructure to
mirror. Adds two thin layers on top of the MCP library:

  * faction display-name -> kebab-id mapping (yags uses display names like
    "Pantheon Security"; the MCP keys on "pantheon-security"). Three yags
    factions (Void / Independent / Unknown) have no MCP counterpart and are
    intentionally absent from the map — the caller treats absence as "skip
    MCP, keep the LLM-generated name".

  * pronouns -> gender filter mapping for the MCP's gender-aware generator
    (she/her -> feminine, he/him -> masculine, everything else -> ambiguous,
    which is the dense bucket and the canonical default in Aeonisk).

Fails open: any exception, partial-result edge case, or repeated reservation
conflict returns None, letting the DM's hallucinated name stand.
"""

from __future__ import annotations

import logging
from typing import Optional

from aeonisk_names_mcp.generator import generate_baseline_names
from aeonisk_names_mcp.server import tool_reserve

logger = logging.getLogger(__name__)


FACTION_MAP: dict[str, str] = {
    "Sovereign Nexus": "sovereign-nexus",
    "Pantheon Security": "pantheon-security",
    "ACG": "astral-commerce-group",
    "ArcGen": "arcane-genetics",
    "House of Vox": "house-of-vox",
    "Tempest Industries": "tempest-industries",
    "Freeborn": "freeborn",
}

PRONOUN_GENDER_MAP: dict[str, str] = {
    "she/her": "feminine",
    "he/him": "masculine",
}


def pronouns_to_gender(pronouns: Optional[str]) -> str:
    if not pronouns:
        return "ambiguous"
    return PRONOUN_GENDER_MAP.get(pronouns.strip().lower(), "ambiguous")


class NamesClient:
    """Sync MCP wrapper, one instance per session.

    `owner` is the reservation-owner string the MCP records against each
    claimed name; convention is "yags:<session_id>" so the cleanup CLI can
    find session-scoped rows later.
    """

    _MAX_RESERVATION_RETRIES = 1  # one retry after first conflict, then give up

    def __init__(
        self,
        *,
        owner: str = "yags",
        from_pool: bool = True,
    ) -> None:
        self._owner = owner
        self._from_pool = from_pool

    def generate_npc_name(
        self,
        *,
        faction: str,
        pronouns: str,
        context: Optional[str] = None,
    ) -> Optional[str]:
        mapped_faction = FACTION_MAP.get(faction)
        if mapped_faction is None:
            return None

        gender = pronouns_to_gender(pronouns)
        exclude: list[str] = []

        for attempt in range(self._MAX_RESERVATION_RETRIES + 1):
            try:
                result = generate_baseline_names(
                    faction=mapped_faction,
                    count=1,
                    gender=gender,
                    from_pool=self._from_pool,
                    exclude=exclude,
                )
            except Exception as exc:
                logger.warning(
                    "Aeonisk-names MCP raised during generate (%s/%s): %s — "
                    "falling back to LLM-generated NPC name",
                    faction,
                    gender,
                    exc,
                )
                return None

            if not result.names:
                logger.warning(
                    "Aeonisk-names MCP returned no names for %s/%s — falling back",
                    faction,
                    gender,
                )
                return None

            name = result.names[0]["name"]

            try:
                reservation = tool_reserve(
                    name=name,
                    owner=self._owner,
                    context=context,
                )
            except Exception as exc:
                logger.warning(
                    "Aeonisk-names MCP raised during reserve for %r: %s — "
                    "falling back to LLM-generated NPC name",
                    name,
                    exc,
                )
                return None

            if reservation.get("reserved"):
                return name

            logger.info(
                "Reservation conflict for %r (attempt %d): %s",
                name,
                attempt + 1,
                reservation.get("conflict", "unknown"),
            )
            exclude.append(name)

        logger.warning(
            "Exhausted reservation retries for %s/%s — falling back to LLM name",
            faction,
            gender,
        )
        return None
