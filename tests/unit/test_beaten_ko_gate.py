"""The player-turn Beaten/Fatal consciousness gate wiring (_check_beaten_ko).

Unit-tests the helper against a mock agent + a real ResolutionState, forcing the
health-check outcome by patching the RNG. The full turn-loop integration (a
skipped action producing the right JSONL) is verified by a live session run.
"""
import types

import pytest

from aeonisk.multiagent.session import _check_beaten_ko
from aeonisk.multiagent.tactical_resolution import ResolutionState


def _agent(stuns=0, wounds=0, health=3):
    cs = types.SimpleNamespace(name="Hard Vane", attributes={"Health": health})
    return types.SimpleNamespace(agent_id="player_01", stuns=stuns, wounds=wounds,
                                 character_state=cs)


def test_healthy_actor_not_gated():
    rs = ResolutionState()
    assert _check_beaten_ko(_agent(stuns=5, wounds=5), rs) is False
    assert not rs.is_incapacitated("player_01")


def test_beaten_failure_marks_incapacitated(monkeypatch):
    import aeonisk.multiagent.mechanics as m
    monkeypatch.setattr(m.random, "randint", lambda a, b: 2)  # low roll -> fail
    rs = ResolutionState()
    assert _check_beaten_ko(_agent(stuns=12, health=1), rs) is True
    assert rs.is_incapacitated("player_01")


def test_beaten_success_leaves_actor_standing(monkeypatch):
    import aeonisk.multiagent.mechanics as m
    monkeypatch.setattr(m.random, "randint", lambda a, b: 20)  # high roll -> pass
    rs = ResolutionState()
    assert _check_beaten_ko(_agent(stuns=6, health=5), rs) is False
    assert not rs.is_incapacitated("player_01")


def test_fatal_wounds_gate_too(monkeypatch):
    import aeonisk.multiagent.mechanics as m
    monkeypatch.setattr(m.random, "randint", lambda a, b: 2)
    rs = ResolutionState()
    assert _check_beaten_ko(_agent(wounds=6, health=1), rs) is True
    assert rs.is_incapacitated("player_01")
