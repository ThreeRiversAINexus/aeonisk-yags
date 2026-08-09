"""`--create-config` is the first config most people ever see. Keep it honest.

Before this test, EXAMPLE_CONFIG failed validation with five errors and was not
canon: Body/Mind/Soul attributes instead of the eight YAGS ones, model "gpt-4",
soulcredit 15 and 12 (the range is -10..+10), deprecated void_score, no
party_size, no per-player llm, and "Resonance Communes" used as a faction tag
when it is a Freeborn subfaction. Anyone following the docs hit that first.
"""

import pytest

from scripts.aeonisk.multiagent.session import EXAMPLE_CONFIG
from scripts.aeonisk.multiagent.launch_config import validate_session_config
from scripts.aeonisk.multiagent import config_schema as cs

# The 8 canonical factions (content/supplemental/FACTION_REFERENCE.md, LOCKED).
CANON_FACTIONS = {
    "Sovereign Nexus", "Pantheon Security", "Astral Commerce Group",
    "Arcane Genetics", "House of Vox", "Aether Dynamics",
    "Tempest Industries", "Freeborn",
}

# The 8 YAGS attributes as Aeonisk names them (Endurance not Health, Willpower not Will).
YAGS_ATTRIBUTES = {
    "Strength", "Agility", "Endurance", "Dexterity",
    "Perception", "Intelligence", "Empathy", "Willpower",
}

PLAYERS = EXAMPLE_CONFIG["agents"]["players"]


def test_example_config_validates_clean():
    assert validate_session_config(EXAMPLE_CONFIG) == []


def test_example_config_carries_the_recommended_baseline():
    """No recommended-deviations — the bootstrap should model the research default."""
    for key, recommended in cs.recommended_overrides().items():
        assert EXAMPLE_CONFIG.get(key, cs.by_path(key).default) == recommended, (
            f"{key} deviates from the recommended baseline"
        )


def test_example_config_uses_no_unknown_or_vestigial_keys():
    unknown = {k for k in EXAMPLE_CONFIG
               if k not in cs.top_level_keys() and not cs.is_meta_key(k)}
    assert not unknown, f"unknown top-level keys: {sorted(unknown)}"
    for dotted in cs.vestigial_keys():
        head = dotted.split(".")[0]
        assert head not in EXAMPLE_CONFIG, f"sets vestigial {dotted}"


@pytest.mark.parametrize("player", PLAYERS, ids=lambda p: p["name"])
def test_players_are_canon(player):
    assert player["faction"] in CANON_FACTIONS
    assert set(player["attributes"]) == YAGS_ATTRIBUTES
    assert -10 <= player["soulcredit"] <= 10
    assert 0 <= player["void"] <= 10
    assert "void_score" not in player, "void_score is deprecated; use void"


@pytest.mark.parametrize("player", PLAYERS, ids=lambda p: p["name"])
def test_player_weapons_exist(player):
    from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY
    for weapon_id in (player.get("equipped_weapons") or {}).values():
        assert weapon_id in WEAPON_LIBRARY, f"{weapon_id} not in WEAPON_LIBRARY"


def test_smoke_sized_and_non_interactive():
    """Cheap enough to run on a whim, and it must not block on an stdin prompt."""
    assert EXAMPLE_CONFIG["max_turns"] <= 3
    assert EXAMPLE_CONFIG["enable_human_interface"] is False
    assert EXAMPLE_CONFIG["party_size"] == len(PLAYERS)


def test_clocks_are_regressable():
    """Never a one-way ratchet — every clock needs both directions."""
    for clock in EXAMPLE_CONFIG.get("starting_clocks", []):
        assert clock.get("advance_meaning", "").strip()
        assert clock.get("regress_meaning", "").strip()
