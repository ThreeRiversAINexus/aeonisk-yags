"""Stun healing must actually reduce the stun track — on both sides.

The bug: _process_structured_healing_effects had a no-op `stun` branch (it built a
"-N stun" narration string but never mutated target.stuns), while the event logged
`stun_removed: amount` as if it had. With the KO design (recovery off, clobbered =
over), a medic clearing stuns is the ONLY way back from Beaten, so this has to work.
"""
import types

import pytest

from aeonisk.multiagent.dm import _process_structured_healing_effects
from aeonisk.multiagent.schemas.action_effects import HealingEffect


def _capture_logger():
    events = []
    jl = types.SimpleNamespace(log_event=lambda et, data, rnd: events.append((et, data)))
    return types.SimpleNamespace(jsonl_logger=jl), events


def _shared_state(players=(), enemies=(), npcs=()):
    ec = types.SimpleNamespace(enemy_agents=list(enemies)) if enemies else None
    return types.SimpleNamespace(get_target_id_mapper=lambda: None,
                                 player_agents=list(players),
                                 enemy_combat=ec, npc_agents=list(npcs))


def _player(name="Enforcer Kael Dren", stuns=8, wounds=1, health=20, max_health=27):
    cs = types.SimpleNamespace(name=name)
    return types.SimpleNamespace(character_state=cs, agent_id="player_01",
                                 stuns=stuns, wounds=wounds, health=health, max_health=max_health)


def _enemy(name="Independent Brawler #1", stuns=8, wounds=0, health=25, max_health=30):
    return types.SimpleNamespace(name=name, agent_id="enemy_grunt_1", is_active=True,
                                 stuns=stuns, wounds=wounds, health=health, max_health=max_health)


def test_stun_heal_reduces_player_stuns():
    p = _player(stuns=8)
    mech, events = _capture_logger()
    _process_structured_healing_effects(
        [HealingEffect(target=p.character_state.name, heal_type="stun", amount=3, source="medkit")],
        _shared_state(players=[p]), 2, mechanics=mech)
    assert p.stuns == 5  # 8 - 3, the whole point
    ev = dict(events)["healing_applied"]
    assert ev["stun_removed"] == 3               # reports ACTUAL removal, not requested
    assert ev["target_state_after"]["stuns"] == 5  # post-heal stun state is visible


def test_stun_heal_reduces_enemy_stuns_too():
    # "on both sides" — the target resolver + mutation work for enemies as well
    e = _enemy(stuns=10)
    mech, events = _capture_logger()
    _process_structured_healing_effects(
        [HealingEffect(target=e.name, heal_type="stun", amount=6, source="field medicine")],
        _shared_state(enemies=[e]), 3, mechanics=mech)
    assert e.stuns == 4
    assert dict(events)["healing_applied"]["stun_removed"] == 6


def test_stun_heal_floors_at_zero_and_reports_actual():
    p = _player(stuns=2)
    mech, events = _capture_logger()
    _process_structured_healing_effects(
        [HealingEffect(target=p.character_state.name, heal_type="stun", amount=5)],
        _shared_state(players=[p]), 1, mechanics=mech)
    assert p.stuns == 0
    assert dict(events)["healing_applied"]["stun_removed"] == 2  # only 2 were actually there


def test_stun_heal_lifts_beaten_so_actor_can_recover():
    # Beaten (>=6) -> healed below 6 -> no longer auto-Beaten
    p = _player(stuns=7)
    mech, _ = _capture_logger()
    _process_structured_healing_effects(
        [HealingEffect(target=p.character_state.name, heal_type="stun", amount=4)],
        _shared_state(players=[p]), 1, mechanics=mech)
    assert p.stuns == 3 and p.stuns < 6  # can pass a health check / act freely again


def test_hp_heal_still_works_regression():
    p = _player(stuns=0, health=20, max_health=27)
    mech, events = _capture_logger()
    _process_structured_healing_effects(
        [HealingEffect(target=p.character_state.name, heal_type="hp", amount=5)],
        _shared_state(players=[p]), 1, mechanics=mech)
    assert p.health == 25
    assert dict(events)["healing_applied"]["hp_restored"] == 5
