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

Nine of the ten defects this file was filed on are fixed by #134's resolver and
now assert directly. The tenth — an unresolvable declaration still falling
through to the equipped slot rather than the declared damage class — is #134
step 3 and remains `xfail(strict=True)`.
"""

import itertools
from collections import namedtuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.aeonisk.multiagent.dm import (
    _match_declared_weapon, _resolve_declared_weapon,
    _resolve_weapon_and_damage_type,
)
from scripts.aeonisk.multiagent.resolution import Policy, resolve
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

    @pytest.mark.parametrize("declared", [
        "the tranquilizer",   # the example the old matcher refused
        "tranq gun",          # abbreviation, reached by prefix rather than fuzzing
        "my tranquilizer gun",
    ])
    def test_recognised_since_134(self, declared):
        match = _match_declared_weapon(declared, owned("tranq_gun"))
        assert match is not None and match.damage_type == "stun"


class TestAmbiguityIsRefused:
    """Exactly one surviving candidate, or nothing — `name_matching.py`'s rule.

    The weapon matcher has no ambiguity check at all: it returns the first
    containment hit in iteration order, so which weapon you get depends on
    inventory ordering.
    """

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
# The resolver's own branches, isolated
# ---------------------------------------------------------------------------
class TestResolverMechanics:
    """Two guards in `resolution.py` are unreachable through the weapon policy,
    because another guard refuses first.

    Mutation testing found both. Making token matching bidirectional again
    changed nothing, because every weapon case that *looks* directional is
    actually refused for having an extra token; and letting the first
    containment hit win changed nothing, because the damage-class invariant
    refused it anyway. Two checks that could not fail.

    So they are exercised here against a synthetic domain with no invariant,
    which is the honest way round: `resolution.py` is general machinery, and
    these are its rules rather than the weapon policy's.
    """

    Thing = namedtuple("Thing", "name")
    PLAIN = Policy(name_of=lambda t: t.name)

    def test_a_declared_token_never_matches_a_shorter_candidate_token(self):
        """The directional rule. `declared.startswith(candidate)` is the
        direction that lets a short, different name answer a long, specific
        request — the shape behind `'the stun pistol'` -> Pistol."""
        result = resolve("tranquilizer", [self.Thing("Tranq")], self.PLAIN)

        assert result.value is None
        assert result.path == "refused"

    def test_a_declared_token_may_match_a_longer_candidate_token(self):
        """The generous direction, kept: abbreviations resolve."""
        result = resolve("tranq", [self.Thing("Tranquilizer Gun")], self.PLAIN)

        assert result.value is not None
        assert result.path == "token_subset"

    def test_a_prefix_shorter_than_the_floor_is_refused(self):
        """Three characters would let 'gun' reach anything gun-shaped."""
        assert resolve("tra", [self.Thing("Tranquilizer")], self.PLAIN).value is None

    def test_two_candidates_matching_the_same_stem_refuse(self):
        result = resolve("baton", [self.Thing("Shock Baton"),
                                   self.Thing("Drip Baton")], self.PLAIN)

        assert result.value is None
        assert "ambiguous" in (result.reason or "")

    def test_an_exact_name_beats_an_ambiguous_stem(self):
        result = resolve("Baton", [self.Thing("Baton"),
                                   self.Thing("Shock Baton")], self.PLAIN)

        assert result.value.name == "Baton"
        assert result.path == "exact"


class TestPathIsReported:
    """`path` is the auditability contract: an analysis must be able to restrict
    to exactly-resolved rows and check whether a finding survives without the
    inferred ones. That only works if the paths are distinguishable."""

    @pytest.mark.parametrize("declared,expected", [
        ("Tranquilizer Gun", "exact"),
        ("the Tranquilizer Gun!", "normalized"),
        ("tranquilizer", "token_subset"),
        ("Shrike Cannon", "refused"),
    ])
    def test_each_route_is_labelled(self, declared, expected):
        result = _resolve_declared_weapon(declared, owned("tranq_gun"))

        assert result.path == expected


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
