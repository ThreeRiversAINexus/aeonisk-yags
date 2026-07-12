"""ko_check events: the Beaten/Fatal consciousness gate must log its rolls.

resolve_ko_check runs at two sites (player gate _check_beaten_ko, enemy gate in
_mark_defeated_from_resolution) but historically emitted NO event — so KO was
invisible to the corpus and not verifiable by the mechanics-diff harness. These
tests pin the event contract: every rolled check (pass or fail) emits one
ko_check event carrying its full inputs (stuns/wounds/health_attr/roll) and
outputs (dc/total/can_act/status), so the harness can re-run resolve_ko_check
deterministically with the logged roll.
"""
import types

import pytest

from aeonisk.multiagent.session import _check_beaten_ko, _mark_defeated_from_resolution
from aeonisk.multiagent.tactical_resolution import ResolutionState


def _capturing_logger():
    captured = []
    return types.SimpleNamespace(write_event=lambda e: captured.append(e)), captured


def _agent(stuns=0, wounds=0, health=3):
    cs = types.SimpleNamespace(name="Hard Vane", attributes={"Health": health})
    return types.SimpleNamespace(agent_id="player_01", stuns=stuns, wounds=wounds,
                                 character_state=cs)


def _enemy(stuns=0, wounds=0, endurance=3, health=20):
    return types.SimpleNamespace(
        agent_id="enemy_grunt_a", name="Grunt", is_active=True,
        stuns=stuns, wounds=wounds, health=health,
        attributes={"Endurance": endurance})


def _manager(*enemies):
    return types.SimpleNamespace(enemy_agents=list(enemies))


class TestPlayerGateLogging:
    def test_failed_check_emits_event(self, monkeypatch):
        import aeonisk.multiagent.mechanics as m
        monkeypatch.setattr(m.random, "randint", lambda a, b: 2)
        jl, cap = _capturing_logger()
        rs = ResolutionState()
        _check_beaten_ko(_agent(stuns=12, health=1), rs, jsonl_logger=jl, round_num=3)

        assert len(cap) == 1
        e = cap[0]
        assert e["event_type"] == "ko_check"
        assert e["round"] == 3
        assert e["agent_id"] == "player_01"
        assert e["name"] == "Hard Vane"
        assert e["side"] == "player"
        # inputs: enough to re-run resolve_ko_check deterministically
        assert e["stuns"] == 12 and e["wounds"] == 0 and e["health_attr"] == 1
        assert e["roll"] == 2
        # outputs
        assert e["can_act"] is False
        assert e["dc"] == 20 + 5 * (12 - 6)
        assert e["total"] == 1 * 2 + 2
        assert e["status"] == "unconscious"

    def test_passed_check_also_emits(self, monkeypatch):
        import aeonisk.multiagent.mechanics as m
        monkeypatch.setattr(m.random, "randint", lambda a, b: 20)
        jl, cap = _capturing_logger()
        _check_beaten_ko(_agent(stuns=6, health=5), ResolutionState(),
                         jsonl_logger=jl, round_num=1)
        assert len(cap) == 1
        assert cap[0]["can_act"] is True

    def test_ungated_actor_emits_nothing(self):
        jl, cap = _capturing_logger()
        _check_beaten_ko(_agent(stuns=5, wounds=5), ResolutionState(),
                         jsonl_logger=jl, round_num=1)
        assert cap == []

    def test_no_logger_is_safe(self, monkeypatch):
        import aeonisk.multiagent.mechanics as m
        monkeypatch.setattr(m.random, "randint", lambda a, b: 2)
        # must not raise without a logger (default None)
        assert _check_beaten_ko(_agent(stuns=12, health=1), ResolutionState()) is True


class TestEnemyGateLogging:
    def test_enemy_check_emits_event(self, monkeypatch):
        import aeonisk.multiagent.mechanics as m
        monkeypatch.setattr(m.random, "randint", lambda a, b: 2)
        jl, cap = _capturing_logger()
        rs = ResolutionState()
        _mark_defeated_from_resolution(_manager(_enemy(stuns=8, endurance=2)), rs,
                                       jsonl_logger=jl, round_num=2)
        assert len(cap) == 1
        e = cap[0]
        assert e["event_type"] == "ko_check"
        assert e["agent_id"] == "enemy_grunt_a"
        assert e["side"] == "enemy"
        assert e["stuns"] == 8 and e["health_attr"] == 2
        assert e["can_act"] is False
        assert rs.is_incapacitated("enemy_grunt_a")

    def test_once_per_round_guard_logs_once(self, monkeypatch):
        import aeonisk.multiagent.mechanics as m
        monkeypatch.setattr(m.random, "randint", lambda a, b: 20)
        jl, cap = _capturing_logger()
        rs = ResolutionState()
        mgr = _manager(_enemy(stuns=8, endurance=5))
        _mark_defeated_from_resolution(mgr, rs, jsonl_logger=jl, round_num=2)
        _mark_defeated_from_resolution(mgr, rs, jsonl_logger=jl, round_num=2)
        assert len(cap) == 1  # ko_checked guard: one roll, one event

    def test_healthy_enemy_emits_nothing(self):
        jl, cap = _capturing_logger()
        _mark_defeated_from_resolution(_manager(_enemy(stuns=2)), ResolutionState(),
                                       jsonl_logger=jl, round_num=1)
        assert cap == []
