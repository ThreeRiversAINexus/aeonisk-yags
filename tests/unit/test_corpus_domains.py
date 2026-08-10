"""Real inputs from the corpus, driven through the pure mechanics functions.

The counterpart to `test_pure_function_domains.py`, which enumerates domains I
chose by hand. Both are needed, and the snapshot proves why: two of the four
hand-chosen ranges were **too narrow**. `HEALTHS = (0, 1, 5, 30)` against a real
maximum of 55, and `STUNS = range(0, 11)` against a real maximum of 28. Neither
had ever been exercised at the values the engine actually produces.

Three families, one per verb:

* **oracle** — `ko_check` logs every input and every output including the
  injected roll, so the expected value is the engine's own recorded answer.
  This is the only family here where nothing is assumed.
* **recombination** — real values in combinations that never co-occurred. The
  corpus holds 7,193 `character_state` rows and only 134 distinct tuples, so
  the observed vocabulary is far richer than the observed combinations.
* **extrapolation** — deliberately past the measured envelope. The snapshot is
  what makes "we have never seen this" a fact rather than a guess.

Reads the committed snapshot, never the corpus: `multiagent_output/` and
`bulk_output/` are gitignored and get cleared, and a test that breaks when
someone tidies up is not a test.
"""

import json
from pathlib import Path

import pytest

from scripts.aeonisk.multiagent.mechanics import (
    MAX_STUNS, apply_healing, apply_mixed_damage, apply_stun_damage,
    apply_wound_damage, get_stun_effect, get_wound_effect, resolve_ko_check,
)

_SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "domains" / "domain_corpus.json"

pytestmark = pytest.mark.skipif(
    not _SNAPSHOT.exists(),
    reason="domain snapshot absent; run scripts/domain_mine.py")


@pytest.fixture(scope="module")
def snap():
    return json.loads(_SNAPSHOT.read_text())


class Body:
    """Minimal damage target — the attribute surface these functions touch.

    A stub rather than a Mock, matching the house rule from #103: a Mock's
    `health > 0` raises and its containers iterate empty, so it passes tests the
    real object would fail.
    """

    def __init__(self, health=30, max_health=30, wounds=0, stuns=0):
        self.health = health
        self.max_health = max_health
        self.wounds = wounds
        self.stuns = stuns


class TestKOCheckAgainstItsOwnRecord:
    """The oracle family. Eight rows, and worth more than the thousands that
    log only one side."""

    def test_reproduces_every_logged_outcome(self, snap):
        rows = snap["samples"]["ko_check"]
        assert rows, "no ko_check oracle rows in the snapshot"

        for r in rows:
            got = resolve_ko_check(r["stuns"], r["wounds"], r["health_attr"],
                                   roll=r["roll"])
            where = (f"stuns={r['stuns']} wounds={r['wounds']} "
                     f"health_attr={r['health_attr']} roll={r['roll']} "
                     f"[{r.get('git_commit')}]")
            assert got["dc"] == r["dc"], f"dc: {where}"
            assert got["total"] == r["total"], f"total: {where}"
            assert got["can_act"] == r["can_act"], f"can_act: {where}"
            assert got["status"] == r["status"], f"status: {where}"

    def test_every_recorded_check_was_above_the_threshold(self, snap):
        """A logged ko_check means the engine decided one was required."""
        for r in snap["samples"]["ko_check"]:
            assert max(r["stuns"], r["wounds"]) >= 6, r


class TestRealBodyStatesAreTotal:
    """Every state the engine has actually produced must be survivable input."""

    def bodies(self, snap):
        for health, wounds, stuns in snap["samples"]["body_states"]:
            if health is None or wounds is None:
                continue
            yield health, wounds, (0 if stuns is None else stuns)

    def test_effect_tables_answer_for_every_real_state(self, snap):
        for health, wounds, stuns in self.bodies(snap):
            assert get_stun_effect(stuns)["name"], f"stuns={stuns}"
            assert get_wound_effect(wounds)["name"], f"wounds={wounds}"

    def test_damage_never_lowers_the_counter_it_raises(self, snap):
        """The clamp bug, checked against states that really occurred: taking
        damage must never heal you."""
        for health, wounds, stuns in self.bodies(snap):
            for dmg in (0, 1, 7, 25):
                b = Body(health=health, max_health=max(health, 1),
                         wounds=wounds, stuns=stuns)
                apply_stun_damage(b, dmg)
                assert b.stuns >= stuns, \
                    f"apply_stun_damage(hp={health}, w={wounds}, s={stuns}, d={dmg})"

    def test_ko_check_never_raises_over_real_states(self, snap):
        for health, wounds, stuns in self.bodies(snap):
            for roll in (1, 10, 20):
                resolve_ko_check(stuns, wounds, 3, roll=roll)


class TestRealDamageApplications:
    """502 distinct `(dealt, damage_type, pre-state)` combinations."""

    def test_every_observed_damage_type_is_handled(self, snap):
        observed = {r["damage_type"] for r in snap["samples"]["damage"]}

        assert observed <= {"wound", "mixed", "stun"}, \
            f"unhandled damage types in the corpus: {observed}"

    def test_wounds_dealt_matches_the_documented_divisor(self, snap):
        """`wounds_dealt = damage // 5` for the pure-wound path."""
        for r in snap["samples"]["damage"]:
            if r["damage_type"] != "wound":
                continue
            b = Body(health=40, max_health=40, wounds=0, stuns=0)
            result = apply_wound_damage(b, r["dealt"])

            assert result["wounds_dealt"] == r["dealt"] // 5, r

    def test_no_counter_goes_negative_on_any_real_input(self, snap):
        for r in snap["samples"]["damage"]:
            pre = r.get("pre") or {}
            b = Body(health=max(pre.get("health") or 30, 0),
                     max_health=max(pre.get("health") or 30, 1),
                     wounds=max(pre.get("wounds") or 0, 0), stuns=0)
            fn = {"stun": apply_stun_damage, "mixed": apply_mixed_damage}.get(
                r["damage_type"], apply_wound_damage)
            fn(b, r["dealt"])

            assert b.wounds >= 0 and b.stuns >= 0, r


class TestHealing:

    def test_every_observed_heal_type_is_accepted(self, snap):
        for r in snap["samples"]["healing"]:
            b = Body(health=5, max_health=30, wounds=3, stuns=3)
            apply_healing(b, r["amount"], r["heal_type"])

    def test_the_wound_heal_type_is_never_exercised_by_the_corpus(self, snap):
        """103 `hp` and 7 `stun` applications, and **zero** `wound`.

        Recorded because it is the shape of a coverage gap: `apply_healing`
        supports a branch that no session has ever taken, so only the
        extrapolation below covers it.
        """
        observed = {r["heal_type"] for r in snap["samples"]["healing"]}

        assert "wound" not in observed

    def test_wound_healing_works_anyway(self):
        """Extrapolation: the never-observed branch, exercised directly."""
        b = Body(health=10, max_health=30, wounds=4, stuns=0)

        result = apply_healing(b, 2, "wound")

        assert b.wounds == 2 and result["wounds_treated"] == 2

    def test_an_unknown_heal_type_is_rejected(self):
        with pytest.raises(ValueError):
            apply_healing(Body(), 1, "vibes")


class TestExtrapolationBeyondTheObservedEnvelope:
    """Past the edge of the map, using the snapshot to know where the edge is.

    This is the family that found the stun-cap clamp bug: `min(new, MAX_STUNS)`
    pulled an over-cap entity back down, so taking damage healed it. No session
    could have surfaced that — the state is only reachable via `resume_state` or
    a legacy save.
    """

    def observed_max(self, snap, field):
        return snap["domains"][field]["max"]

    def test_states_beyond_the_observed_maximum_are_still_total(self, snap):
        ceiling = self.observed_max(snap, "stuns")

        for stuns in range(ceiling, ceiling + 12):
            assert get_stun_effect(stuns)["name"], f"stuns={stuns}"
            resolve_ko_check(stuns, 0, 3, roll=10)

    def test_damage_never_heals_an_over_cap_entity(self, snap):
        """The clamp bug exactly. Real corpus stuns reach 28, well past
        MAX_STUNS, so this state is not hypothetical."""
        ceiling = self.observed_max(snap, "stuns")

        for stuns in range(MAX_STUNS, ceiling + 4):
            for dmg in range(0, 12):
                b = Body(stuns=stuns)
                apply_stun_damage(b, dmg)

                assert b.stuns >= stuns, f"stuns={stuns} damage={dmg} -> {b.stuns}"

    def test_negative_and_zero_health_are_handled(self, snap):
        for health in (-20, -1, 0):
            b = Body(health=health, max_health=30)
            apply_wound_damage(b, 10)

            assert isinstance(b.wounds, int)

    def test_health_above_the_observed_maximum(self, snap):
        """Real max_health reaches 55; the hand-written domain stopped at 30."""
        ceiling = self.observed_max(snap, "health")

        b = Body(health=ceiling + 20, max_health=ceiling + 20)
        apply_wound_damage(b, 10)

        assert b.health == ceiling + 10


class TestTheSnapshotKeepsItsShape:

    def test_hand_chosen_ranges_do_not_exceed_reality(self, snap):
        """Guard against the reverse drift.

        Recorded because the comparison went the other way when this was
        written: `test_pure_function_domains.py` used `HEALTHS = (0, 1, 5, 30)`
        and `STUNS = range(0, 11)` while the corpus held 55 and 28. A guess is
        only safe when it is a superset.
        """
        assert snap["domains"]["wounds"]["max"] <= 8, \
            "corpus now exceeds WOUNDS = range(0, 9) in test_pure_function_domains"

    def test_coverage_floor(self, snap):
        """The snapshot merges and never subtracts, so these can only grow."""
        s = snap["samples"]
        assert len(s["body_states"]) >= 134
        assert len(s["damage"]) >= 500
        assert len(s["ko_check"]) >= 8

    def test_provenance_is_present(self, snap):
        p = snap["provenance"]

        assert p["sessions"] > 0 and p["commits"]

    def test_dirty_sessions_are_counted(self, snap):
        """83 of 330 sessions came from trees with uncommitted changes, so
        their commit does not identify the code that produced them."""
        assert snap["provenance"]["dirty_sessions"] > 0


class TestStealthAndDetectionAreNowDeterministic:
    """Both called `random.randint` internally with no injection point.

    That single missing parameter is why stealth was the one mechanics surface
    with no property coverage at all — `resolve_ko_check(..., roll=)` had the
    convention, these two did not. Patching `random` instead would assert what I
    believe the module does rather than what the function does.
    """

    class Agent:
        def __init__(self, agility=3, stealth=2, perception=3, awareness=2,
                     void_score=0):
            self.attributes = {"Agility": agility, "Perception": perception}
            self.skills = {"Stealth": stealth, "Awareness": awareness}
            self.void_score = void_score

    def test_stealth_is_reproducible_with_an_injected_roll(self):
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check

        a = resolve_stealth_check(self.Agent(), 15, roll=11)
        b = resolve_stealth_check(self.Agent(), 15, roll=11)

        assert a["stealth_roll"] == b["stealth_roll"] and a["d20"] == 11

    def test_detection_is_reproducible_with_an_injected_roll(self):
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check

        a = resolve_detection_check(self.Agent(), 15, roll=7)
        b = resolve_detection_check(self.Agent(), 15, roll=7)

        assert a["detection_roll"] == b["detection_roll"] and a["d20"] == 7

    def test_stealth_never_returns_a_negative_total_across_the_die(self):
        """Floored at 1, including the unskilled -5 at skill 0."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check

        for d20 in range(1, 21):
            r = resolve_stealth_check(self.Agent(agility=1, stealth=0), 15,
                                      modifiers=-10, roll=d20)

            assert r["stealth_roll"] >= 1, f"d20={d20} -> {r['stealth_roll']}"

    def test_detection_never_returns_a_negative_total_across_the_die(self):
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check

        for d20 in range(1, 21):
            r = resolve_detection_check(self.Agent(perception=1, awareness=0),
                                        15, modifiers=-10, roll=d20)

            assert r["detection_roll"] >= 1, f"d20={d20} -> {r['detection_roll']}"

    def test_max_void_forbids_stealth_at_every_roll(self):
        """void_score 10 is an automatic failure, so no die can rescue it."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check

        for d20 in range(1, 21):
            r = resolve_stealth_check(self.Agent(void_score=10), 5, roll=d20)

            assert r["success"] is False, f"d20={d20}"

    def test_omitting_the_roll_still_rolls(self):
        """The default path must keep working for live play."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check

        assert 1 <= resolve_stealth_check(self.Agent(), 15)["d20"] <= 20


class TestMixedDamageRespectsTheStunCap:
    """#117: `apply_mixed_damage` used to bypass `MAX_STUNS` entirely.

    `apply_stun_damage` clamped; `apply_mixed_damage` did `old_stuns +
    stun_damage` with no bound, and mixed is 313 of 997 recorded damage
    applications — the common path, not an edge case. Real `character_state`
    rows reached 28 stuns, and seven of the eight recorded `ko_check` events sat
    above the cap.

    The clamp is **upward-only**, matching `apply_stun_damage`: a plain
    `min(new, MAX_STUNS)` would pull an already-over-cap entity down, which is
    the #91 bug where taking damage healed you.

    KO outcomes are unchanged — level 8 already puts the DC at 30 against a
    ceiling of `health_attr*2 + 20`, so at or above the cap it was unwinnable
    either way. What changes is that the invariant holds and the logs stop
    recording states the cap says cannot exist.
    """

    @pytest.mark.parametrize("damage", range(0, 40, 3))
    def test_never_exceeds_the_cap_from_a_normal_start(self, damage):
        b = Body(health=30, max_health=30, wounds=0, stuns=0)

        apply_mixed_damage(b, damage)

        assert b.stuns <= MAX_STUNS, f"mixed damage {damage} -> {b.stuns} stuns"

    @pytest.mark.parametrize("start", range(0, MAX_STUNS + 1))
    @pytest.mark.parametrize("damage", (0, 1, 5, 17, 40))
    def test_never_exceeds_the_cap_from_any_legal_start(self, start, damage):
        b = Body(health=30, max_health=30, wounds=0, stuns=start)

        apply_mixed_damage(b, damage)

        assert b.stuns <= MAX_STUNS, f"start={start} damage={damage} -> {b.stuns}"

    @pytest.mark.parametrize("start", range(MAX_STUNS, 30))
    @pytest.mark.parametrize("damage", (0, 1, 9, 25))
    def test_never_heals_an_entity_already_over_the_cap(self, start, damage):
        """The upward-only half. Legacy saves and resume_state reach these."""
        b = Body(health=30, max_health=30, wounds=0, stuns=start)

        apply_mixed_damage(b, damage)

        assert b.stuns >= start, f"start={start} damage={damage} -> {b.stuns}"

    def test_the_reported_delta_matches_the_clamped_change(self):
        """A result that reports more stuns than it applied would corrupt any
        ledger built from the return value."""
        b = Body(stuns=MAX_STUNS - 1)

        result = apply_mixed_damage(b, 30)

        assert result["new_stuns"] == b.stuns
        assert result["new_stuns"] - result["old_stuns"] == result["stuns_dealt"]

    def test_wounds_are_unaffected_by_the_stun_clamp(self):
        """Clamping the stun half must not change the wound half."""
        capped = Body(stuns=MAX_STUNS)
        fresh = Body(stuns=0)

        apply_mixed_damage(capped, 20)
        apply_mixed_damage(fresh, 20)

        assert capped.wounds == fresh.wounds
