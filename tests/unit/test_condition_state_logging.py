"""character_state.conditions must carry the live condition list, not [].

The per-round character_state snapshot hardcoded `conditions: []` (a literal
TODO) while conditions (Winded, barriers, strain) lived only in
mechanics.conditions — invisible to the corpus, to the invariant checker, and
to any state reconstruction (resume-from-round needs them). The serializer is
a module-level helper so it stays unit-testable.
"""
import types

from aeonisk.multiagent.session import _serialize_conditions
from aeonisk.multiagent.mechanics import Condition


def _mech(conds_by_agent):
    return types.SimpleNamespace(get_conditions=lambda aid: conds_by_agent.get(aid, []))


def test_no_conditions_is_empty_list():
    assert _serialize_conditions(_mech({}), "player_01") == []


def test_conditions_serialize_with_mechanical_fields():
    c = Condition(name="Winded", type="stun", penalty=-2,
                  description="out of breath", duration=2, affects=["Agility"])
    out = _serialize_conditions(_mech({"player_01": [c]}), "player_01")
    assert out == [{"name": "Winded", "type": "stun", "penalty": -2,
                    "duration": 2, "affects": ["Agility"]}]


def test_missing_mechanics_is_safe():
    assert _serialize_conditions(None, "player_01") == []


def test_serializer_never_raises():
    broken = types.SimpleNamespace(get_conditions=lambda aid: 1 / 0)
    assert _serialize_conditions(broken, "player_01") == []
