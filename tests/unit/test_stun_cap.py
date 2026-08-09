"""Stuns cap at the knockout threshold so the consciousness check stays rollable.

Regression origin (session a8ca2b7f, 2026-08-09):

    Beaten/Fatal KO: Nera Mereth failed health check (stuns=10, wounds=3, roll=8, total=14 vs DC 40)

`resolve_ko_check` scales `DC = 20 + 5*(level-6)` without limit, while the roll
is `Endurance*2 + d20` — a hard ceiling of 26 at Endurance 3, 30 at 5, 36 at 8.
Past level 7 the check stops being a roll at all:

    level  DC   End 3        End 5        End 8
        6   20  35%          55%          85%
        7   25  10%          30%          60%
        8   30  knocked out  5%           35%
        9   35  knocked out  knocked out  10%
       10   40  knocked out  knocked out  knocked out

Stuns reach 10 because `apply_stun_damage` follows the YAGS non-cumulative rule
`if damage_dealt > old_stuns: new_stuns = damage_dealt` — one heavy hit *sets*
the counter rather than adding to it, with no ceiling.

Capping at 8 keeps a genuine knockout reachable (an ordinary character put to 8
is out for the scene) while leaving a tough one a long shot at rallying. A lower
cap would make non-lethal takedowns unreliable, which matters because stun
damage is how a lawful subdue-and-arrest is supposed to work (#88).
"""

import pytest

from scripts.aeonisk.multiagent.mechanics import (
    KO_CHECK_THRESHOLD, MAX_STUNS, apply_stun_damage, resolve_ko_check,
)


class Target:
    def __init__(self, stuns=0):
        self.stuns = stuns


class TestStunCap:

    def test_cap_is_above_the_beaten_threshold(self):
        """A knockout state must exist beyond merely Beaten, or non-lethal
        takedowns can never stick."""
        assert MAX_STUNS > KO_CHECK_THRESHOLD

    def test_single_massive_hit_is_clamped(self):
        """The observed case: one blow set stuns straight to 10."""
        target = Target()

        apply_stun_damage(target, 25)

        assert target.stuns == MAX_STUNS

    def test_repeated_hits_climb_then_stop(self):
        """Five tranquilizer darts (4 damage each) subdue; further darts do not
        push the target into unrollable territory."""
        target = Target()
        seen = []
        for _ in range(8):
            apply_stun_damage(target, 4)
            seen.append(target.stuns)

        assert seen[:5] == [4, 5, 6, 7, 8]
        assert max(seen) == MAX_STUNS

    def test_reported_stuns_dealt_reflects_the_clamp(self):
        """A caller adding stuns_dealt to its own tally must not exceed the cap."""
        target = Target(stuns=MAX_STUNS)

        result = apply_stun_damage(target, 30)

        assert target.stuns == MAX_STUNS
        assert result["stuns_dealt"] == 0
        assert result["new_stuns"] == MAX_STUNS

    def test_below_the_cap_is_untouched(self):
        """The YAGS non-cumulative rule still governs everything under the cap."""
        target = Target()

        apply_stun_damage(target, 5)

        assert target.stuns == 5

    def test_unconscious_check_still_flagged_at_the_cap(self):
        target = Target()

        result = apply_stun_damage(target, 20)

        assert result["unconscious_check_needed"] is True


class TestKOCheckStaysRollable:
    """With the cap in place, no character faces an arithmetically dead roll."""

    @pytest.mark.parametrize("endurance", [3, 4, 5, 8])
    def test_capped_stuns_are_never_impossible_for_the_tough(self, endurance):
        """At the cap the DC is 30; Endurance 5+ retains a chance."""
        dc = 20 + 5 * (MAX_STUNS - KO_CHECK_THRESHOLD)
        best_possible = endurance * 2 + 20

        if endurance >= 5:
            assert best_possible >= dc, (
                f"Endurance {endurance} should retain a chance at the cap")

    def test_a_natural_20_at_the_cap_wakes_a_tough_character(self):
        result = resolve_ko_check(
            stuns=MAX_STUNS, wounds=0, health_attr=8, roll=20)

        assert result["can_act"] is True

    def test_an_ordinary_character_stays_down_at_the_cap(self):
        """'Totally knocked out' has to be reachable, or arrests never stick."""
        result = resolve_ko_check(
            stuns=MAX_STUNS, wounds=0, health_attr=3, roll=20)

        assert result["can_act"] is False
        assert result["status"] == "unconscious"

    def test_beaten_but_not_capped_is_a_real_roll(self):
        """At the Beaten threshold itself the check must remain winnable."""
        passed = resolve_ko_check(
            stuns=KO_CHECK_THRESHOLD, wounds=0, health_attr=3, roll=18)
        failed = resolve_ko_check(
            stuns=KO_CHECK_THRESHOLD, wounds=0, health_attr=3, roll=2)

        assert passed["can_act"] is True
        assert failed["can_act"] is False


class TestCapNeverHeals:
    """Taking damage must never reduce stuns.

    Found by exhaustively enumerating apply_stun_damage over its whole input
    domain (13 starting values x 41 damage values = 533 cases, 0.001s). The first
    version of the cap used min(new, MAX_STUNS), which pulled an entity already
    above the cap back down to it — so a character loaded at 9 stuns via
    resume_state got *healed* by being shot. 164 of the 533 cases violated it,
    and no live session would have surfaced it, because the engine cannot itself
    produce stuns above the cap any more.
    """

    def test_over_cap_entity_is_not_healed_by_damage(self):
        target = Target(stuns=10)

        apply_stun_damage(target, 0)

        assert target.stuns == 10

    def test_over_cap_entity_is_not_healed_by_a_big_hit(self):
        target = Target(stuns=12)

        apply_stun_damage(target, 30)

        assert target.stuns == 12

    @pytest.mark.parametrize("start", range(0, 13))
    @pytest.mark.parametrize("damage", [0, 1, 4, 7, 12, 25, 40])
    def test_stuns_never_decrease(self, start, damage):
        """The property, over the full domain."""
        target = Target(stuns=start)

        apply_stun_damage(target, damage)

        assert target.stuns >= start

    @pytest.mark.parametrize("start", range(0, 13))
    @pytest.mark.parametrize("damage", [0, 3, 9, 20, 40])
    def test_reported_delta_always_matches_reality(self, start, damage):
        target = Target(stuns=start)

        result = apply_stun_damage(target, damage)

        assert result["stuns_dealt"] == target.stuns - start

    @pytest.mark.parametrize("damage", [0, 5, 15, 40])
    def test_fresh_entities_still_cap_at_max(self, damage):
        """The cap must still bite for anything starting at or below it."""
        target = Target(stuns=0)

        apply_stun_damage(target, damage)

        assert target.stuns <= MAX_STUNS
