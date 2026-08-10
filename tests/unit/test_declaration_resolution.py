"""The seam where a model's declared intent becomes mechanics (#133).

`test_weapon_resolution.py` covers this function call-by-call and pins today's
behaviour. This file covers the *vocabulary*: every name a model could plausibly
write against every loadout it could plausibly hold. Extract mode is not
available — `declared_weapon` has four rows corpus-wide, one of which is the
#131 incident itself — so the modes here are recombine, extrapolate and
property, exactly as in #125.

The load-bearing rule is an invariant, not a distance threshold: **a match may
never cross lethality class.** Generous on the name, absolute on the invariant.
Today's matcher has it backwards on both axes — it accepts `'the stun pistol'`
as a lethal Pistol while refusing `'the tranquilizer'`, which is the example in
its own docstring.

The asymmetry is what makes this urgent rather than cosmetic: every failure mode
falls through to `equipped_weapons['primary']`, which is a WOUND weapon in
nearly every loadout. There is no safe miss.

Known defects are `xfail(strict=True)` so they flip the moment #134 lands.
"""

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.aeonisk.multiagent.dm import (
    _match_declared_weapon, _resolve_weapon_and_damage_type,
)
from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY, get_weapon
from tests.factories import FakeAgent, FakeSharedState

LIBRARY = list(WEAPON_LIBRARY.values())


def owned(*weapon_ids):
    return [get_weapon(w) for w in weapon_ids]


def loadout(primary=None, sidearm=None, carried=(), agent_id="player_02"):
    """A player with a real equipped/carried split, per tests/factories.py."""
    agent = FakeAgent(agent_id=agent_id)
    if primary:
        agent.equipped_weapons["primary"] = get_weapon(primary)
    if sidearm:
        agent.equipped_weapons["sidearm"] = get_weapon(sidearm)
    agent.weapon_inventory = owned(*carried)
    return FakeSharedState(players=[agent])


def action(**over):
    base = {"agent_id": "player_02", "skill": "Guns"}
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Mode 2 — recombine: the whole library against itself
# ---------------------------------------------------------------------------
class TestTheInvariantHolds:
    """A match must never change the lethality class the model asked for.

    This is the cross-product that #133 was filed on. Same shape as the
    faction x archetype recombination that caught `extract_faction` misparsing
    34 of 176 pairs: the corpus tells you which *values* are real, it does not
    tell you which *combinations* are.
    """

    @pytest.mark.xfail(strict=True, reason="#134: bidirectional containment "
                                           "crosses damage class 6 ways")
    def test_no_declared_name_resolves_to_a_different_damage_class(self):
        crossings = []
        for declared, held in itertools.permutations(LIBRARY, 2):
            match = _match_declared_weapon(declared.name, [held])
            if match is not None and match.damage_type != declared.damage_type:
                crossings.append(
                    f"{declared.name!r} ({declared.damage_type.upper()}) -> "
                    f"{match.name!r} ({match.damage_type.upper()})")

        assert not crossings, (
            f"{len(crossings)} name(s) resolved across lethality class:\n  "
            + "\n  ".join(crossings))

    def test_a_match_is_always_drawn_from_the_owned_set(self):
        """Naming a weapon must never confer its properties (dm.py:184).

        The half of the policy that already works, pinned so a fix for the
        other half cannot quietly regress it.
        """
        for declared, held in itertools.permutations(LIBRARY, 2):
            match = _match_declared_weapon(declared.name, [held])
            assert match is None or match is held, (
                f"{declared.name!r} against a loadout of only {held.name!r} "
                f"produced {match.name!r}, which is not owned")


# ---------------------------------------------------------------------------
# Mode 2 — recombine: directionality, the specific rule #134 introduces
# ---------------------------------------------------------------------------
class TestLongerDeclarationsDoNotCollapse:
    """A more specific declaration must not match a shorter, different name.

    `needle in name` is the legitimate paraphrase direction ("tranquilizer" ->
    "Tranquilizer Gun"). `name in needle` is how a player asking for a stun
    weapon receives a lethal one, and it fires on the single most common
    loadout element in the repo — plain `pistol`, in 149 configs.
    """

    @pytest.mark.xfail(strict=True, reason="#134: `name in needle` matches")
    @pytest.mark.parametrize("declared,held", [
        ("Compact EMP Pistol", "pistol"),
        ("EMP Pistol", "pistol"),
        ("the stun pistol", "pistol"),
        ("Stun Baton", "baton"),
        ("Dripshock Baton", "baton"),
    ])
    def test_unowned_specific_name_is_refused(self, declared, held):
        assert _match_declared_weapon(declared, owned(held)) is None


# ---------------------------------------------------------------------------
# Mode 3 — extrapolate: strings models actually write
# ---------------------------------------------------------------------------
class TestParaphraseIsAccepted:
    """The generous half. These are spelling and phrasing, not intent."""

    @pytest.mark.parametrize("declared", [
        "Tranquilizer Gun",           # exact
        "tranquilizer gun",           # casefold
        "  Tranquilizer Gun  ",       # whitespace
        "tranquilizer",               # bare stem
        "Tranquilizer Gun (STUN)",    # the annotation models append
    ])
    def test_recognised_today(self, declared):
        match = _match_declared_weapon(declared, owned("tranq_gun"))
        assert match is not None and match.damage_type == "stun"

    @pytest.mark.xfail(strict=True, reason="#134: substring is the wrong "
                                           "primitive; needs token subset")
    @pytest.mark.parametrize("declared", [
        "the tranquilizer",   # the example in _match_declared_weapon's docstring
        "tranq gun",
    ])
    def test_refused_today(self, declared):
        assert _match_declared_weapon(declared, owned("tranq_gun")) is not None


class TestAmbiguityIsRefused:
    """Exactly one surviving candidate, or nothing — `name_matching.py`'s rule.

    The weapon matcher has no ambiguity check at all: it returns the first
    containment hit in iteration order, so which weapon you get depends on
    inventory ordering.
    """

    @pytest.mark.xfail(strict=True, reason="#134: first containment hit wins")
    def test_a_stem_matching_two_owned_weapons_refuses(self):
        held = owned("shock_baton", "dripshock_baton")
        assert _match_declared_weapon("baton", held) is None

    def test_an_exact_name_wins_over_a_containment_rival(self):
        """Pinned because #134 must not break it while adding the ambiguity
        check: owning both, naming one exactly is unambiguous."""
        held = owned("baton", "shock_baton")
        assert _match_declared_weapon("Shock Baton", held).name == "Shock Baton"


class TestDegenerateInputs:
    """Past the measured envelope, where the corpus offers nothing."""

    @pytest.mark.parametrize("declared", ["", "   ", "Lightsaber", "🔫"])
    def test_unresolvable_names_return_none(self, declared):
        assert _match_declared_weapon(declared, owned("pistol")) is None

    def test_empty_loadout_returns_none(self):
        assert _match_declared_weapon("Pistol", []) is None


# ---------------------------------------------------------------------------
# Mode 6 — property
# ---------------------------------------------------------------------------
WEAPON_IDS = st.sampled_from(sorted(WEAPON_LIBRARY))


class TestProperties:

    @given(declared_id=WEAPON_IDS, held_ids=st.lists(WEAPON_IDS, min_size=1,
                                                     max_size=4, unique=True))
    @settings(max_examples=300)
    def test_a_match_is_never_invented(self, declared_id, held_ids):
        held = owned(*held_ids)
        match = _match_declared_weapon(get_weapon(declared_id).name, held)
        assert match is None or match in held

    @given(held_ids=st.lists(WEAPON_IDS, min_size=1, max_size=4, unique=True),
           index=st.integers(min_value=0, max_value=3))
    @settings(max_examples=300)
    def test_naming_an_owned_weapon_exactly_returns_that_weapon(self, held_ids,
                                                                index):
        held = owned(*held_ids)
        wanted = held[index % len(held)]
        assert _match_declared_weapon(wanted.name, held) is wanted


# ---------------------------------------------------------------------------
# The #131 reproduction, at the level the game actually plays it
# ---------------------------------------------------------------------------
class TestFallThroughDoesNotEscalate:
    """An unresolvable declaration must not manufacture lethality.

    This is #131 end to end. Corin's real loadout from
    `session_configs/transmedia/the_unwritten_room.json`, and the string the
    model actually wrote. The declaration states stun intent and he owns a stun
    weapon; today he shoots a carbine.

    An error may downgrade harm. It may never upgrade it — an upgrade is a
    false positive in the exact quantity the transgression research measures.
    """

    @pytest.mark.xfail(strict=True, reason="#134: fall-through picks the "
                                           "equipped slot, not the declared class")
    def test_stun_declaration_resolves_to_a_stun_weapon(self):
        state = loadout(primary="oathpiercer_carbine", carried=["tranq_gun"])

        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="Stun Baton (STUN)"), state)

        assert damage_type == "stun", (
            f"declared a STUN weapon, resolved {name!r} ({damage_type.upper()})")

    def test_the_owned_stun_weapon_is_still_reachable_by_name(self):
        """The #88 fix, pinned: this is the path that must keep working."""
        state = loadout(primary="oathpiercer_carbine", carried=["tranq_gun"])

        name, damage_type, _ = _resolve_weapon_and_damage_type(
            action(weapon="Tranquilizer Gun"), state)

        assert (name, damage_type) == ("Tranquilizer Gun", "stun")
