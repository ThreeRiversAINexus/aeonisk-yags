"""Enemy-side YAGS Beaten/Fatal KO gate in _mark_defeated_from_resolution.

Enemies get the same model-(a) health-check-to-act as players (was a model-(b)
auto-KO at stuns>=6). The wrinkle: _mark_defeated_from_resolution runs after EACH
PC action, so a Beaten enemy must be checked at most ONCE per round (ResolutionState
is per-round; a `ko_checked` guard prevents re-rolls that would inflate the KO rate).
"""
import types

import pytest

from aeonisk.multiagent.session import _mark_defeated_from_resolution, _ko_health_attr
from aeonisk.multiagent.tactical_resolution import ResolutionState
import aeonisk.multiagent.mechanics as m


def _enemy(agent_id="enemy_grunt_1", stuns=0, wounds=0, health=20, endurance=3, is_active=True):
    return types.SimpleNamespace(agent_id=agent_id, name="Thug", is_active=is_active,
                                 health=health, stuns=stuns, wounds=wounds,
                                 attributes={"Endurance": endurance})


def _combat(*enemies):
    return types.SimpleNamespace(enemy_agents=list(enemies))


def test_beaten_enemy_failing_check_is_incapacitated(monkeypatch):
    monkeypatch.setattr(m.random, "randint", lambda a, b: 2)  # low roll -> fail DC 40 at 10 stuns
    rs = ResolutionState()
    e = _enemy(stuns=10, endurance=1)
    _mark_defeated_from_resolution(_combat(e), rs)
    assert rs.is_incapacitated(e.agent_id)


def test_beaten_enemy_passing_check_acts(monkeypatch):
    monkeypatch.setattr(m.random, "randint", lambda a, b: 20)  # high roll -> pass DC 20 at 6 stuns
    rs = ResolutionState()
    e = _enemy(stuns=6, endurance=5)
    _mark_defeated_from_resolution(_combat(e), rs)
    assert not rs.is_incapacitated(e.agent_id)
    assert e.agent_id in rs.ko_checked  # recorded so it won't re-roll this round


def test_check_happens_at_most_once_per_round(monkeypatch):
    # enemy passes on the first call; a second call (next PC action, same round)
    # must NOT re-roll even though the RNG would now fail.
    rolls = iter([20, 1])  # first pass, then a would-be fumble
    monkeypatch.setattr(m.random, "randint", lambda a, b: next(rolls))
    rs = ResolutionState()
    e = _enemy(stuns=6, endurance=5)
    _mark_defeated_from_resolution(_combat(e), rs)
    _mark_defeated_from_resolution(_combat(e), rs)
    assert not rs.is_incapacitated(e.agent_id)  # not re-rolled into a KO


def test_healthy_enemy_not_checked():
    rs = ResolutionState()
    e = _enemy(stuns=3, wounds=2)
    _mark_defeated_from_resolution(_combat(e), rs)
    assert not rs.is_incapacitated(e.agent_id)
    assert e.agent_id not in rs.ko_checked


def test_dead_enemy_marked_defeated_not_ko_checked():
    rs = ResolutionState()
    e = _enemy(health=0, stuns=10)
    _mark_defeated_from_resolution(_combat(e), rs)
    assert rs.is_defeated(e.agent_id)  # death path wins; not a stun-KO


def test_fatal_wounds_gate_enemy(monkeypatch):
    monkeypatch.setattr(m.random, "randint", lambda a, b: 2)
    rs = ResolutionState()
    e = _enemy(wounds=6, health=5, endurance=1)  # fatally wounded but health>0 edge
    _mark_defeated_from_resolution(_combat(e), rs)
    assert rs.is_incapacitated(e.agent_id)


class TestHealthAttrExtraction:
    def test_enemy_uses_endurance(self):
        assert _ko_health_attr(_enemy(endurance=5)) == 5

    def test_player_uses_character_state_health(self):
        cs = types.SimpleNamespace(attributes={"Health": 4})
        agent = types.SimpleNamespace(character_state=cs)
        assert _ko_health_attr(agent) == 4

    def test_fallback_when_absent(self):
        assert _ko_health_attr(types.SimpleNamespace()) == 3
