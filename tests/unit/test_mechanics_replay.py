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


# --- forward-fold state + stun/mixed ---------------------------------------
def spawn(eid, name, health):
    return {"event_type": "enemy_spawn", "round": 0, "enemy_id": eid,
            "enemy_name": name, "stats": {"health": health}}


def combat(defender_id, name, dealt, dtype, after, wounds_dealt=None, rnd=1):
    d = {"dealt": dealt, "soak": 0, "base_damage": dealt, "damage_type": dtype}
    ev = {"event_type": "combat_action", "round": rnd,
          "defender": {"id": defender_id, "name": name},
          "damage": d, "defender_state_after": after}
    if wounds_dealt is not None:
        ev["wounds_dealt"] = wounds_dealt
    return ev


def test_stun_faithful_no_diff():
    # pure stun (non-cumulative): before stuns 0, dealt 6 -> stuns 6, health/wounds untouched
    events = [spawn("e1", "Grunt", 26),
              combat("e1", "Grunt", dealt=6, dtype="stun",
                     after={"wounds": 0, "stuns": 6, "health": 26})]
    assert replay_events(events).diffs == []


def test_stun_mismatch_flagged():
    events = [spawn("e1", "Grunt", 26),
              combat("e1", "Grunt", dealt=6, dtype="stun",
                     after={"wounds": 0, "stuns": 8, "health": 26})]  # log claims 8
    diffs = replay_events(events).diffs
    assert any(d.field == "stuns_after" and d.recomputed == 6 for d in diffs)


def test_mixed_faithful_no_diff():
    # dealt 8 -> stun (8+1)//2=4, wound 8//2=4 -> wounds 4//5=0, health -4
    events = [spawn("e1", "Grunt", 26),
              combat("e1", "Grunt", dealt=8, dtype="mixed",
                     after={"wounds": 0, "stuns": 4, "health": 22})]
    assert replay_events(events).diffs == []


def test_forward_fold_stun_non_cumulative_uses_running_state():
    # PROVES folding: 2nd stun's outcome depends on the 1st's result (old_stuns=4).
    # dealt 3 with old_stuns 4 -> 3<4 but 3>=4//2 -> +1 -> stuns 5.
    # Without folding (old_stuns=0) it'd recompute stuns 3 and diff.
    events = [spawn("e1", "Grunt", 26),
              combat("e1", "Grunt", dealt=4, dtype="stun",
                     after={"wounds": 0, "stuns": 4, "health": 26}, rnd=1),
              combat("e1", "Grunt", dealt=3, dtype="stun",
                     after={"wounds": 0, "stuns": 5, "health": 26}, rnd=2)]
    assert replay_events(events).diffs == []


def test_health_clamp_divergence_detected():
    # the real corpus signal: current code clamps health at 0; a buggy log had -5
    events = [spawn("e1", "Grunt", 5),
              combat("e1", "Grunt", dealt=10, dtype="wound", wounds_dealt=2,
                     after={"wounds": 2, "stuns": 0, "health": -5})]
    diffs = replay_events(events).diffs
    assert any(d.field == "health_after" and d.logged == -5 and d.recomputed == 0
               for d in diffs)


# --- corpus mode -----------------------------------------------------------
def test_replay_paths_aggregates(tmp_path):
    from scripts.mechanics_replay import replay_paths
    import json
    good = tmp_path / "good.jsonl"
    bad = tmp_path / "bad.jsonl"
    good.write_text("\n".join(json.dumps(e) for e in [
        spawn("e1", "Grunt", 26),
        combat("e1", "Grunt", dealt=10, dtype="wound", wounds_dealt=2,
               after={"wounds": 2, "stuns": 0, "health": 16}),
    ]))
    bad.write_text("\n".join(json.dumps(e) for e in [
        spawn("e1", "Grunt", 26),
        combat("e1", "Grunt", dealt=10, dtype="wound", wounds_dealt=9,
               after={"wounds": 9, "stuns": 0, "health": 16}),
    ]))
    per_file = replay_paths([str(good), str(bad)])
    assert per_file[str(good)].has_diffs is False
    assert per_file[str(bad)].has_diffs is True
