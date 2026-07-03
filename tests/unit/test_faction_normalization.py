"""
Faction values the DM emits must never crash scenario/NPC structured output.

Regression: the ritual scenario is set among the Resonance Communes, so the DM
emitted NPCSpawn.faction="Resonance Communes" -- a canonical Freeborn SUBFACTION
(faction_utils.py:144) that the faction Literal did not list. Pydantic rejected
it, the DM burned 7 retries, and the session hung. The taxonomy is top-level
(names_client.FACTION_MAP maps the parent "Freeborn", not the subfaction), so the
fix normalizes subfactions/aliases to their canonical parent and falls back to
"Independent" for anything unrecognized -- the field can no longer reject a value.

Also syncs the enum with faction_utils.CANONICAL_SPAWN_FACTIONS (adds the
previously-missing "Aether Dynamics").
"""

import pytest

from aeonisk.multiagent.schemas.story_events import _normalize_faction, NPCSpawn


def _npc(faction):
    return NPCSpawn(
        name="Elder Maelin",
        faction=faction,
        entity_type="neutral",
        disposition="neutral",
        description="A calm commune elder presiding over the dissolution rite.",
        health=12,
        soak=0,
    )


class TestNormalizeFaction:
    def test_canonical_pass_through(self):
        for f in ("Sovereign Nexus", "Pantheon Security", "ACG", "ArcGen",
                  "House of Vox", "Aether Dynamics", "Tempest Industries",
                  "Freeborn", "Void", "Independent", "Unknown"):
            assert _normalize_faction(f) == f

    def test_freeborn_subfactions_map_to_parent(self):
        assert _normalize_faction("Resonance Communes") == "Freeborn"
        assert _normalize_faction("Fractal Praxis") == "Freeborn"

    def test_common_aliases_map_to_canonical(self):
        assert _normalize_faction("Nexus") == "Sovereign Nexus"
        assert _normalize_faction("Astral Commerce Group") == "ACG"
        assert _normalize_faction("Arcane Genetics") == "ArcGen"

    def test_unknown_falls_back_to_independent(self):
        # the key property: never reject -> never hang
        assert _normalize_faction("Glorbo Cartel of Mars") == "Independent"

    def test_whitespace_tolerated(self):
        assert _normalize_faction("  Resonance Communes  ") == "Freeborn"


class TestNPCSpawnFactionValidation:
    def test_resonance_communes_no_longer_raises(self):
        # the exact value that hung the ritual session
        npc = _npc("Resonance Communes")
        assert npc.faction == "Freeborn"

    def test_aether_dynamics_accepted(self):
        assert _npc("Aether Dynamics").faction == "Aether Dynamics"

    def test_unknown_faction_coerced_not_rejected(self):
        assert _npc("Some Made-Up Cabal").faction == "Independent"

    def test_canonical_still_works(self):
        assert _npc("Freeborn").faction == "Freeborn"
