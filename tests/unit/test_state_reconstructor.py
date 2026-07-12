"""TDD spec for resume-from-divergence state reconstruction (rung 3).

scripts/state_reconstructor.py folds a recorded session's events to the end of
round K-1 and emits (a) a ResumeState snapshot and (b) a resume config that
seeds a LIVE session at round K — the prefix is loaded, never replayed.

Feasibility findings this encodes (see .claude/REPLAY_RESUME_FEASIBILITY.md):
party state comes exact from per-round character_state; enemy state folds
spawn stats -> latest enemy character_state -> later defender_state_after;
clocks fold from action_resolution.clocks strings + advancement metadata;
defeated/departed enemies are excluded from the roster.
"""
import copy
import json

import pytest

from scripts.state_reconstructor import reconstruct, build_resume_config


# --- synthetic event builders (real JSONL shapes) ---------------------------
def cstate(rnd, name, cid="player_01", agent="player", health=27, max_health=27,
           wounds=0, stuns=0, void=0, sc=5, position="Near-Enemy",
           energy=None, seeds=None, conditions=None):
    return {"event_type": "character_state", "round": rnd, "character_id": cid,
            "character_name": name, "health": health, "max_health": max_health,
            "wounds": wounds, "stuns": stuns, "void_score": void, "soulcredit": sc,
            "position": position, "agent": agent, "is_defeated": False,
            "death_state": "alive",
            "energy": energy or {"breath": 15, "drip": 7, "grain": 1, "spark": 1, "hollow": 0},
            "seeds": seeds or {"raw": 0, "attuned": 1, "hollow": 0},
            "conditions": conditions or []}


def espawn(rnd, eid, name, faction="Independent", template="Grunt",
           health=30, position="Near-Enemy"):
    return {"event_type": "enemy_spawn", "round": rnd, "enemy_id": eid,
            "enemy_name": name, "template": template, "faction": faction,
            "position": position,
            "stats": {"health": health, "max_health": health, "soak": 9,
                      "attributes": {"Health": 3}, "skills": {"Guns": 3},
                      "weapons": [{"name": "Pistol", "attack": 0, "damage": 6,
                                   "skill": "Guns"}]}}


def combat(rnd, did, dname, dealt, after):
    return {"event_type": "combat_action", "round": rnd,
            "attacker": {"id": "player_01", "name": "Kael"},
            "defender": {"id": did, "name": dname},
            "damage": {"base_damage": dealt, "soak": 0, "dealt": dealt,
                       "damage_type": "wound"},
            "wounds_dealt": dealt // 5, "defender_state_after": after}


def defeat(rnd, eid, name, reason="killed"):
    return {"event_type": "enemy_defeat", "round": rnd, "enemy_id": eid,
            "enemy_name": name, "defeat_reason": reason}


def resolution_clocks(rnd, clocks):
    return {"event_type": "action_resolution", "round": rnd, "agent": "Kael",
            "roll": {}, "clocks": clocks, "context": {}}


def synthesis(rnd, text):
    return {"event_type": "round_synthesis", "round": rnd, "synthesis": text}


def scenario(theme="Ambush", location="Transit Hub", situation="Trap sprung.",
             void_level=4):
    return {"event_type": "scenario",
            "scenario": {"theme": theme, "location": location,
                         "situation": situation, "void_level": void_level,
                         "active_vendors": []}}


def base_config():
    return {"session_name": "smoke", "max_turns": 5, "party_size": 2,
            "tactical_module_enabled": True, "enemy_agents_enabled": True,
            "agents": {"dm": {"llm": {"provider": "openai", "model": "gpt-5-mini"}},
                       "players": [{"name": "Kael", "faction": "Pantheon Security",
                                    "attributes": {}, "skills": {},
                                    "llm": {"provider": "openai", "model": "gpt-5-mini"}}]},
            "initial_enemies": [{"name": "Thug", "faction": "Independent",
                                 "template": "grunt", "count": 3}]}


def sample_session():
    return [
        {"event_type": "session_start", "config": base_config(), "random_seed": 7},
        scenario(),
        espawn(0, "e1", "Independent Thug #1"),
        espawn(0, "e2", "Independent Thug #2"),
        cstate(1, "Kael", health=27),
        cstate(1, "Independent Thug #1", cid="e1", agent="enemy", health=12,
               wounds=3, max_health=30, position="Engaged-PC"),
        cstate(1, "Independent Thug #2", cid="e2", agent="enemy", health=30,
               max_health=30),
        resolution_clocks(1, {"Doom": "1/6"}),
        synthesis(1, "Round one: blood on the deck."),
        # round 2: thug 2 takes a hit AFTER its last char_state; thug 1 dies
        combat(2, "e2", "Independent Thug #2", dealt=10,
               after={"health": 20, "max_health": 30, "wounds": 2, "stuns": 0,
                      "alive": True, "status": "active"}),
        defeat(2, "e1", "Independent Thug #1"),
        cstate(2, "Kael", health=22, wounds=1, stuns=2),
        resolution_clocks(2, {"Doom": "3/6"}),
        synthesis(2, "Round two: the tide turns."),
        cstate(3, "Kael", health=22, wounds=1, stuns=2),
    ]


# --- reconstruct -------------------------------------------------------------
def test_party_state_is_end_of_round_k_minus_1():
    rs = reconstruct(sample_session(), resume_round=3)
    kael = next(p for p in rs.party if p["name"] == "Kael")
    assert kael["health"] == 22 and kael["wounds"] == 1 and kael["stuns"] == 2
    assert kael["energy"]["breath"] == 15  # purse carried


def test_enemy_roster_excludes_defeated():
    rs = reconstruct(sample_session(), resume_round=3)
    names = {e["name"] for e in rs.enemies}
    assert names == {"Independent Thug #2"}  # #1 defeated in r2


def test_enemy_state_folds_combat_after_last_snapshot():
    rs = reconstruct(sample_session(), resume_round=3)
    e2 = next(e for e in rs.enemies if e["name"] == "Independent Thug #2")
    # last char_state said 30hp (r1); the r2 combat hit -> 20hp/2 wounds wins
    assert e2["health"] == 20 and e2["wounds"] == 2
    # template lowercased for the initial_enemies surface (_TEMPLATE_MAP keys)
    assert e2["faction"] == "Independent" and e2["template"] == "grunt"


def test_clocks_fold_to_latest_reading():
    rs = reconstruct(sample_session(), resume_round=3)
    doom = next(c for c in rs.clocks if c["name"] == "Doom")
    assert doom["current_ticks"] == 3 and doom["max_ticks"] == 6


def test_resume_round_2_uses_round_1_state():
    rs = reconstruct(sample_session(), resume_round=2)
    kael = next(p for p in rs.party if p["name"] == "Kael")
    assert kael["health"] == 27 and kael["wounds"] == 0
    names = {e["name"] for e in rs.enemies}
    assert names == {"Independent Thug #1", "Independent Thug #2"}  # both alive after r1
    doom = next(c for c in rs.clocks if c["name"] == "Doom")
    assert doom["current_ticks"] == 1


def test_scenario_and_story_so_far():
    rs = reconstruct(sample_session(), resume_round=3)
    assert rs.scenario["theme"] == "Ambush"
    assert rs.void_level == 4
    assert "tide turns" in rs.story_so_far  # r2 synthesis included
    assert "blood on the deck" in rs.story_so_far


# --- build_resume_config -----------------------------------------------------
def test_resume_config_shape():
    events = sample_session()
    rs = reconstruct(events, resume_round=3)
    cfg = build_resume_config(base_config(), rs)
    assert cfg["max_turns"] == 3  # 5 - (3-1)
    assert cfg["session_name"].endswith("_resume_r3")
    # clocks ride the existing starting_clocks surface
    assert any(c["name"] == "Doom" and c["current_ticks"] == 3
               for c in cfg["starting_clocks"])
    # enemies: one entry per survivor, archetype carries the exact name suffix
    entries = cfg["initial_enemies"]
    assert len(entries) == 1
    e = entries[0]
    assert e["count"] == 1 and e["faction"] == "Independent"
    assert e["archetype"] == "Thug #2"  # f"{faction} {archetype}" == recorded name
    # the live-session hook block
    assert cfg["resume_state"]["party"][0]["name"] == "Kael"
    assert cfg["resume_state"]["enemies"][0]["name"] == "Independent Thug #2"
    assert cfg["resume_state"]["enemies"][0]["health"] == 20
    # scenario forced with story-so-far so the DM has continuity
    fs = cfg["force_scenario"]
    assert isinstance(fs, dict) and fs["theme"] == "Ambush"
    assert "tide turns" in fs["situation"]


def test_stale_spawn_markers_stripped_from_situation():
    # the recorded situation may carry legacy [SPAWN_ENEMY: ...] markers; the
    # resumed roster comes from initial_enemies, so replaying the marker would
    # double-spawn
    events = sample_session()
    events[1] = scenario(situation="Trap! [SPAWN_ENEMY: Assault Team | grunt | Near-Enemy | melee] Go.")
    cfg = build_resume_config(base_config(), reconstruct(events, resume_round=3))
    assert "[SPAWN_ENEMY" not in cfg["force_scenario"]["situation"]
    assert "Trap!" in cfg["force_scenario"]["situation"]


def test_resume_config_does_not_mutate_original():
    events = sample_session()
    original = base_config()
    frozen = copy.deepcopy(original)
    build_resume_config(original, reconstruct(events, resume_round=3))
    assert original == frozen
