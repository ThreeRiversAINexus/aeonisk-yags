"""Enumerate the input domains of the pure mechanics functions.

Why this file exists (#99): replaying real sessions verifies only what happened.
`mechanics_replay.py` over 29 recorded sessions checks **156 transitions** — for
hours of API spend. Enumerating one function's domain checks 533 in 0.001s, and
that is how the stun-cap clamp bug was found in code merged the same morning:

    start=9 stuns, take 0 damage -> ends at 8

`min(new, MAX_STUNS)` pulled an entity already above the cap back down, so taking
damage healed it. **No live session could have surfaced it** — the engine cannot
itself produce stuns above the cap, so the state is only reachable via
resume_state or a legacy save.

These tests assert *properties over whole domains* rather than picking examples.
Where a domain is too large to enumerate, sample it densely rather than guessing
a narrow range.
"""

import pytest

from scripts.aeonisk.multiagent.faction_utils import (
    CANONICAL_SPAWN_FACTIONS, extract_faction,
)
from scripts.aeonisk.multiagent.mechanics import (
    MAX_STUNS, apply_healing, apply_mixed_damage, apply_stun_damage,
    apply_wound_damage, get_stun_effect, get_wound_effect, recover_stuns,
    resolve_ko_check,
)


class Body:
    """Minimal damage target: the attribute surface these functions touch."""

    def __init__(self, health=30, max_health=30, wounds=0, stuns=0):
        self.health = health
        self.max_health = max_health
        self.wounds = wounds
        self.stuns = stuns


# Dense but bounded: the full cross-product below is ~44k cases per function and
# runs in well under a second.
HEALTHS = (0, 1, 5, 30)
WOUNDS = range(0, 9)
STUNS = range(0, 11)
DAMAGES = range(0, 41)


def damage_cases():
    for hp in HEALTHS:
        for w in WOUNDS:
            for s in STUNS:
                for dmg in DAMAGES:
                    yield hp, w, s, dmg


@pytest.mark.parametrize("fn", [apply_wound_damage, apply_mixed_damage,
                                apply_stun_damage],
                         ids=lambda f: f.__name__)
class TestDamageFunctionsOverTheirDomain:
    """Properties every damage application must satisfy, everywhere."""

    def test_counters_never_go_negative(self, fn):
        for hp, w, s, dmg in damage_cases():
            t = Body(hp, 30, w, s)
            fn(t, dmg)
            assert t.health >= 0 and t.wounds >= 0 and t.stuns >= 0, (
                f"{fn.__name__}(hp={hp}, w={w}, s={s}, dmg={dmg})")

    def test_damage_never_reduces_what_it_raises(self, fn):
        """The clamp bug: a cap that pulled an over-cap entity down, so being
        shot healed it."""
        for hp, w, s, dmg in damage_cases():
            t = Body(hp, 30, w, s)
            fn(t, dmg)
            assert t.wounds >= w and t.stuns >= s, (
                f"{fn.__name__}(hp={hp}, w={w}, s={s}, dmg={dmg}) "
                f"reduced a counter")

    def test_reported_deltas_match_reality(self, fn):
        """A caller tallying the reported delta must not drift from the state."""
        for hp, w, s, dmg in damage_cases():
            t = Body(hp, 30, w, s)
            result = fn(t, dmg)
            assert result.get("wounds_dealt", 0) == t.wounds - w
            if "stuns_dealt" in result:
                assert result["stuns_dealt"] == t.stuns - s

    def test_health_never_rises_from_damage(self, fn):
        for hp, w, s, dmg in damage_cases():
            t = Body(hp, 30, w, s)
            fn(t, dmg)
            assert t.health <= hp


class TestStunSpecificProperties:

    def test_fresh_entities_never_exceed_the_cap(self):
        for start in range(0, MAX_STUNS + 1):
            for dmg in DAMAGES:
                t = Body(stuns=start)
                apply_stun_damage(t, dmg)
                assert t.stuns <= MAX_STUNS

    def test_over_cap_entities_are_held_not_healed(self):
        """Reachable only from outside the engine — resume_state, legacy saves."""
        for start in range(MAX_STUNS + 1, 20):
            for dmg in DAMAGES:
                t = Body(stuns=start)
                apply_stun_damage(t, dmg)
                assert t.stuns == start, f"start={start} dmg={dmg} -> {t.stuns}"

    def test_stun_damage_never_touches_wounds_or_health(self):
        """Non-lethal must be non-lethal — the whole basis of the II.8 path."""
        for hp, w, s, dmg in damage_cases():
            t = Body(hp, 30, w, s)
            apply_stun_damage(t, dmg)
            assert t.wounds == w and t.health == hp


class TestHealingOverItsDomain:

    def test_healing_never_harms_and_never_overfills(self):
        cases = 0
        for hp in range(0, 31, 3):
            for w in range(0, 9):
                for s in range(0, 11):
                    for amount in range(0, 41, 2):
                        for kind in ("stun", "wound", "hp"):
                            t = Body(hp, 30, w, s)
                            apply_healing(t, amount, kind)
                            cases += 1
                            assert 0 <= t.health <= t.max_health
                            assert t.health >= hp
                            assert t.wounds <= w and t.stuns <= s
                            assert t.wounds >= 0 and t.stuns >= 0
        assert cases > 60000, "domain coverage shrank unexpectedly"

    @pytest.mark.parametrize("kind,untouched", [("stun", "wounds"),
                                                ("wound", "stuns")])
    def test_healing_one_track_leaves_the_other_alone(self, kind, untouched):
        for w in range(0, 9):
            for s in range(0, 11):
                for amount in range(0, 21):
                    t = Body(20, 30, w, s)
                    apply_healing(t, amount, kind)
                    assert getattr(t, untouched) == (w if untouched == "wounds" else s)


class TestEffectTablesAreTotal:
    """No input in a plausible range may fall off the end of a lookup."""

    @pytest.mark.parametrize("value", range(-5, 30))
    def test_stun_effect_is_defined_everywhere(self, value):
        effect = get_stun_effect(value)
        assert isinstance(effect, dict) and "unconscious_check" in effect

    @pytest.mark.parametrize("value", range(-5, 30))
    def test_wound_effect_is_defined_everywhere(self, value):
        assert isinstance(get_wound_effect(value), dict)

    def test_recovery_never_increases_or_goes_negative(self):
        for stuns in range(-5, 30):
            for per_round in range(0, 6):
                result = recover_stuns(stuns, per_round)
                assert result >= 0
                if stuns > 0:
                    assert result <= stuns


class TestKOCheckIsAlwaysARoll:
    """#91: DC scaled without limit while the roll had a ceiling, so past a
    point the check was arithmetic, not dice."""

    def test_typical_characters_can_pass_below_the_cap(self):
        """Endurance 3-5 must retain a chance at every level under the ceiling."""
        for endurance in (3, 4, 5):
            for level in range(6, MAX_STUNS):
                winnable = any(
                    resolve_ko_check(level, 0, endurance, roll=r)["can_act"]
                    for r in range(2, 21))
                assert winnable, (
                    f"Endurance {endurance} cannot pass at level {level}")

    def test_the_cap_is_a_knockout_for_ordinary_characters(self):
        """The design: at the ceiling an ordinary character stays down."""
        assert not resolve_ko_check(MAX_STUNS, 0, 3, roll=20)["can_act"]

    def test_the_tough_still_get_a_chance_at_the_cap(self):
        assert resolve_ko_check(MAX_STUNS, 0, 8, roll=20)["can_act"]

    def test_below_the_threshold_no_check_is_required(self):
        for level in range(0, 6):
            for endurance in range(1, 9):
                assert resolve_ko_check(level, level, endurance)["required"] is False

    def test_never_raises_across_the_grid(self):
        for endurance in range(1, 9):
            for stuns in range(0, 13):
                for wounds in range(0, 13):
                    result = resolve_ko_check(stuns, wounds, endurance, roll=10)
                    assert result["status"] in {"ok", "acts", "unconscious"}


class TestFactionExtraction:
    """#79 was caused here: extract_faction("Tempest Industries Void Theorist")
    returned "Void", because the archetype word outranked the faction words.

    The spawner now passes faction explicitly, but this remains the fallback for
    legacy callers — and it was wrong for 34 of 176 faction x archetype
    combinations, including *every* House of Vox unit.
    """

    # Roles a unit can plausibly hold. Deliberately excludes archetypes that
    # embed a *rival* faction's name ("Tempest Operative", "Vox Broadcaster"):
    # pairing those with an opposed faction produces units that cannot exist —
    # are_factions_allied('ArcGen', 'Tempest Industries') is False — and
    # asserting behaviour over impossible inputs is the same mistake as the
    # death-save fixture that carried both 'Health' and 'Endurance'.
    #
    # "Void Theorist"/"Void Cultist" stay: Void is a role and a corruption
    # state, not a rival corporation, so any faction can field one.
    ARCHETYPES = ("Void Theorist", "Void Cultist", "Enforcer", "Sniper", "Grunt",
                  "Elite", "Boss", "Security Drone", "Ritualist", "Scanner",
                  "Medic", "Technician", "Operative", "Broker", "Warden",
                  "Archivist")

    @pytest.mark.parametrize("faction", sorted(
        f for f in CANONICAL_SPAWN_FACTIONS if f != "Unknown"))
    def test_faction_survives_every_archetype(self, faction):
        for archetype in self.ARCHETYPES:
            assert extract_faction(f"{faction} {archetype}") == faction, (
                f"{faction} {archetype!r} misparsed")

    def test_house_of_vox_is_not_shortened_to_its_alias(self):
        """'Vox' is an alias, not a canonical faction. Every House of Vox unit
        used to come back as 'Vox' — 16 archetypes, all wrong."""
        assert extract_faction("House of Vox Enforcer") == "House of Vox"

    def test_a_short_faction_name_beats_a_longer_archetype_word(self):
        """Why position matters, and not merely specificity.

        Longest-match alone reads 'ACG Void Theorist' as Void, because 'Void'
        (4) outranks 'ACG' (3). A commerce house employing a Void theorist is
        entirely plausible, so the leading name has to win.
        """
        assert extract_faction("ACG Void Theorist") == "ACG"
        assert extract_faction("ACG Void Cultist") == "ACG"

    def test_result_is_deterministic(self):
        """The old implementation iterated a set, so which alias won depended on
        iteration order rather than on the name."""
        name = "House of Vox Void Theorist"
        assert len({extract_faction(name) for _ in range(50)}) == 1

    @pytest.mark.parametrize("name,expected", [
        ("Tempest Operatives", "Tempest"),
        ("Nexus Enforcers", "Nexus"),
        ("ACG Operatives", "ACG"),
    ])
    def test_documented_examples_still_hold(self, name, expected):
        assert extract_faction(name) == expected

    def test_unrecognised_names_are_unknown(self):
        assert extract_faction("Wandering Peddler") == "Unknown"
        assert extract_faction("") == "Unknown"
