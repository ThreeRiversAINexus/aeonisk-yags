"""TDD spec for the YAGS 'health check to act' KO gate and per-round stun recovery.

Verified YAGS rules (converted_yagsbook/markdown/combat.md):
- combat.md:469 — "If your stuns ever reach Beaten [6], you must make a health
  check to remain conscious every round you wish to act; failure makes you
  unconscious, success leaves you standing."
- combat.md:419 — the same, for Fatal wounds (6+).
So KO is NOT automatic: a Beaten/Fatal actor rolls each round; pass -> acts (still
Beaten), fail -> unconscious this round. It is a per-round consciousness gate and
never kills (death at the moment of wounding is owned by check_death_save).

Stun recovery is an Aeonisk HOUSE RULE (YAGS recovers over days; ~10-round scenes
need faster bleed-off so a Beaten combatant isn't frozen the whole fight).
"""
import pytest

from aeonisk.multiagent.mechanics import (
    resolve_ko_check, recover_stuns, STUN_RECOVERY_PER_ROUND, KO_CHECK_THRESHOLD,
)


class TestResolveKoCheck:
    def test_below_threshold_not_required(self):
        r = resolve_ko_check(stuns=5, wounds=5, health_attr=3)
        assert r["required"] is False and r["can_act"] is True and r["status"] == "ok"

    def test_beaten_pass_lets_actor_act(self):
        # DC 20 at exactly Beaten; Health 4 (*2=8) + roll 18 = 26 >= 20 -> acts
        r = resolve_ko_check(stuns=6, wounds=0, health_attr=4, roll=18)
        assert r["required"] and r["can_act"] and r["status"] == "acts" and r["dc"] == 20

    def test_beaten_fail_is_unconscious_not_dead(self):
        r = resolve_ko_check(stuns=6, wounds=0, health_attr=1, roll=3)  # 2+3=5 < 20
        assert r["can_act"] is False and r["status"] == "unconscious"

    def test_natural_one_auto_fails(self):
        r = resolve_ko_check(stuns=6, wounds=0, health_attr=10, roll=1)  # would pass on total
        assert r["can_act"] is False and r["status"] == "unconscious"

    def test_dc_scales_with_severity(self):
        # 8 stuns -> two beyond the 6th -> DC 20 + 5*2 = 30
        r = resolve_ko_check(stuns=8, wounds=0, health_attr=3, roll=20)  # 6+20=26 < 30 -> fail
        assert r["dc"] == 30 and r["can_act"] is False

    def test_fatal_wounds_also_gate(self):
        r = resolve_ko_check(stuns=0, wounds=6, health_attr=1, roll=2)
        assert r["required"] and r["can_act"] is False

    def test_uses_worse_of_the_two_tracks(self):
        # stuns 6 (DC 20) and wounds 8 (DC 30) -> the wound severity dominates
        assert resolve_ko_check(stuns=6, wounds=8, health_attr=3, roll=20)["dc"] == 30

    def test_never_returns_dead(self):
        for roll in range(1, 21):
            assert resolve_ko_check(9, 9, 1, roll=roll)["status"] in ("acts", "unconscious")


class TestRecoverStuns:
    def test_default_rate_is_disabled(self):
        # auto-recovery is off by default ("if you get clobbered it's over")
        assert STUN_RECOVERY_PER_ROUND == 0
        assert recover_stuns(12) == 12  # no bleed-off at the default rate

    def test_floors_at_zero(self):
        assert recover_stuns(1, per_round=2) == 0
        assert recover_stuns(0, per_round=2) == 0

    def test_negative_or_bad_input_is_zero(self):
        assert recover_stuns(-3, per_round=2) == 0

    def test_custom_rate(self):
        assert recover_stuns(10, per_round=4) == 6

    def test_threshold_constant_is_six(self):
        assert KO_CHECK_THRESHOLD == 6
