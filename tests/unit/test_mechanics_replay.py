"""TDD spec for the mechanics-diff harness (scripts/mechanics_replay.py).

The harness re-runs the *current* pure mechanics functions over the mechanical
inputs recorded in a session's combat_action / action_resolution events, and
diffs the recomputed outcome against what was logged. Zero LLM involvement —
this is the token-free "did my formula change alter outcomes" tool.

Property: on a faithful session (formula unchanged) it reports ZERO diffs; if a
formula diverges from what produced the log, it flags the exact field.
"""
from scripts.mechanics_replay import (
    check_combat_damage,
    check_outcome_tier,
    replay_events,
    Diff,
)


def combat_wound(dealt, wounds_dealt, after_wounds, after_health, after_stuns=0):
    """A wound-type combat_action, internally consistent with the given deltas."""
    return {
        "event_type": "combat_action", "round": 1,
        "defender": {"id": "e1", "name": "Grunt"},
        "weapon": "Pistol",
        "damage": {"base_damage": dealt, "soak": 0, "dealt": dealt, "damage_type": "wound"},
        "wounds_dealt": wounds_dealt,
        "defender_state_after": {"health": after_health, "max_health": 30,
                                 "wounds": after_wounds, "stuns": after_stuns,
                                 "alive": after_wounds < 6, "status": "active"},
    }


def resolution(margin, tier):
    return {"event_type": "action_resolution", "round": 1, "agent": "Vane",
            "roll": {"margin": margin, "tier": tier, "success": margin >= 0}}


# --- outcome tier ----------------------------------------------------------
def test_tier_faithful_no_diff():
    # 19-point margin -> excellent (15..19); log agrees
    assert check_outcome_tier(resolution(17, "excellent")) == []
    assert check_outcome_tier(resolution(6, "moderate")) == []
    assert check_outcome_tier(resolution(-14, "failure")) == []


def test_tier_mismatch_flagged():
    # margin 6 is 'moderate', but the log claims 'excellent' (as if thresholds moved)
    diffs = check_outcome_tier(resolution(6, "excellent"))
    assert len(diffs) == 1
    assert diffs[0].field == "tier"
    assert diffs[0].logged == "excellent"
    assert diffs[0].recomputed == "moderate"


def test_tier_skips_unrolled_actions():
    # a 'wait' with no roll: tier None -> nothing to check
    assert check_outcome_tier(resolution(0, None)) == []
    assert check_outcome_tier({"event_type": "action_resolution", "roll": {}}) == []


# --- damage -> wounds ------------------------------------------------------
def test_wound_damage_faithful_no_diff():
    # dealt 19 -> 19//5 = 3 wounds; before_wounds 0, before_health 30 -> after 11
    ev = combat_wound(dealt=19, wounds_dealt=3, after_wounds=3, after_health=11)
    assert check_combat_damage(ev) == []


def test_wound_damage_mismatch_flagged():
    # log claims dealt 19 -> 4 wounds (an old/different formula); code computes 3
    ev = combat_wound(dealt=19, wounds_dealt=4, after_wounds=4, after_health=11)
    diffs = check_combat_damage(ev)
    fields = {d.field for d in diffs}
    assert "wounds_dealt" in fields
    recomputed = {d.field: d.recomputed for d in diffs}
    assert recomputed["wounds_dealt"] == 3


def test_wound_damage_skips_events_without_damage():
    ev = {"event_type": "combat_action", "damage": None,
          "defender_state_after": {"wounds": 0, "health": 30}}
    assert check_combat_damage(ev) == []


# --- aggregate -------------------------------------------------------------
def test_replay_events_aggregates_counts_and_diffs():
    events = [
        combat_wound(dealt=19, wounds_dealt=3, after_wounds=3, after_health=11),  # ok
        combat_wound(dealt=19, wounds_dealt=4, after_wounds=4, after_health=11),  # bad
        resolution(17, "excellent"),  # ok
        resolution(6, "excellent"),   # bad
    ]
    report = replay_events(events)
    assert report.combat_checked == 2
    assert report.tier_checked == 2
    assert len(report.diffs) >= 2          # at least the two injected divergences
    assert all(isinstance(d, Diff) for d in report.diffs)
    assert report.has_diffs is True
