"""The resume_state seam: exact vitals applied to a live session after setup.

build_resume_config seeds roster/clocks/scenario via existing config surfaces,
but exact vitals (current hp/wounds/stuns/void/purse) need one new hook:
session._apply_resume_state, run after scenario setup (players created,
initial enemies spawned). Matching is by character/enemy NAME — the resumed
session mints new agent_ids. Unmatched entries must warn, never raise.

dm.py's force_scenario gains dict support via the pure helper
_forced_scenario_fields (string form stays legacy-compatible).
"""
import types

from aeonisk.multiagent.session import SelfPlayingSession
from aeonisk.multiagent.dm import _forced_scenario_fields


def _player(name, health=27):
    cs = types.SimpleNamespace(
        name=name, void_score=0, soulcredit=0,
        energy_purse=types.SimpleNamespace(breath=0, drip=0, grain=0, spark=0, hollow=0),
    )
    return types.SimpleNamespace(agent_id=f"p_{name}", character_state=cs,
                                 health=health, max_health=health, wounds=0,
                                 stuns=0, position="Near-PC")


def _enemy(name, health=30):
    return types.SimpleNamespace(agent_id=f"e_{name}", name=name, health=health,
                                 max_health=health, wounds=0, stuns=0,
                                 position="Near-Enemy", is_active=True)


def _session(players, enemies, resume_state):
    s = SelfPlayingSession.__new__(SelfPlayingSession)
    s.config = {"resume_state": resume_state}
    s.agents = list(players)
    s.enemy_combat = types.SimpleNamespace(enabled=True, enemy_agents=list(enemies))
    return s


def test_party_vitals_applied_by_name():
    p = _player("Kael")
    s = _session([p], [], {
        "resume_round": 3,
        "party": [{"name": "Kael", "health": 22, "max_health": 27, "wounds": 1,
                   "stuns": 2, "void_score": 1, "soulcredit": 4,
                   "position": "Engaged",
                   "energy": {"breath": 9, "drip": 3, "grain": 0, "spark": 1, "hollow": 0},
                   "seeds": {}, "conditions": []}],
        "enemies": [],
    })
    applied = s._apply_resume_state()
    from aeonisk.multiagent.schemas.shared_types import Position
    assert applied["party"] == 1
    assert p.health == 22 and p.wounds == 1 and p.stuns == 2
    assert p.position is Position.ENGAGED  # ENUM, not str — engine calls enum methods
    assert p.character_state.void_score == 1
    assert p.character_state.soulcredit == 4
    assert p.character_state.energy_purse.breath == 9
    assert p.character_state.energy_purse.drip == 3


def test_enemy_vitals_applied_by_name():
    e = _enemy("Independent Thug #2")
    s = _session([], [e], {
        "resume_round": 3, "party": [],
        "enemies": [{"name": "Independent Thug #2", "health": 20, "max_health": 30,
                     "wounds": 2, "stuns": 0, "position": "Engaged-PC"}],
    })
    from aeonisk.multiagent.schemas.shared_types import Position
    applied = s._apply_resume_state()
    assert applied["enemies"] == 1
    assert e.health == 20 and e.wounds == 2
    # 'Engaged-PC' is not a Position member: falls back to the pre-hyphen ring,
    # and MUST be an enum (live crash: str has no shift_toward_center)
    assert e.position is Position.ENGAGED


def test_garbage_position_falls_back_to_safe_enum():
    from aeonisk.multiagent.session import _resume_position
    from aeonisk.multiagent.schemas.shared_types import Position
    assert _resume_position("Near-PC") is Position.NEAR_PC
    assert _resume_position("Engaged-PC") is Position.ENGAGED
    assert _resume_position("???") is Position.NEAR_ENEMY


def test_unmatched_names_warn_not_raise():
    s = _session([_player("Kael")], [], {
        "resume_round": 3,
        "party": [{"name": "Nobody Here", "health": 1}],
        "enemies": [{"name": "Ghost Enemy", "health": 1}],
    })
    applied = s._apply_resume_state()
    assert applied["party"] == 0 and applied["enemies"] == 0
    assert len(applied["unmatched"]) == 2


def test_no_resume_state_is_noop():
    s = _session([_player("Kael")], [], None)
    s.config = {}
    assert s._apply_resume_state() is None


# --- dm force_scenario dict support ------------------------------------------
def test_forced_scenario_dict_fields():
    out = _forced_scenario_fields({"theme": "Ambush", "location": "Hub",
                                   "situation": "Trap. STORY SO FAR...",
                                   "void_level": 4})
    assert out["theme"] == "Ambush" and out["location"] == "Hub"
    assert out["void_level"] == 4
    assert "STORY SO FAR" in out["situation"]


def test_forced_scenario_string_stays_legacy():
    out = _forced_scenario_fields("[SPAWN_ENEMY: X | grunt | Near | melee]")
    assert out["theme"] == "Test Scenario"
    assert out["location"] == "Test Location"
    assert out["situation"].startswith("[SPAWN_ENEMY")
    assert out["void_level"] == 0
