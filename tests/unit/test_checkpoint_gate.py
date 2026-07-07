"""Tests for the checkpoint / sector access gate (Codex Nexum VIII.1-VIII.2).

Sectors, services, and checkpoints gate on Soulcredit standing. Nexus-aligned
checkpoints check the ledger and apply the universal Cut-Off (SC <= -6 is locked
out of polite society); any checkpoint may set its own soulcredit_requirement.
Non-aligned checkpoints that set no requirement do not ask.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.energy_economy import Checkpoint
from aeonisk.multiagent.mechanics import MechanicsEngine
from aeonisk.multiagent.player import CharacterState
from aeonisk.multiagent.shared_state import SharedState


def _char(sc):
    return CharacterState(
        name="Debtor Vex", faction="Freeborn",
        attributes={"strength": 2, "agility": 3, "endurance": 3,
                    "perception": 4, "intelligence": 4, "empathy": 3,
                    "willpower": 3, "charisma": 2, "size": 10},
        skills={"charm": 2}, void_score=0, soulcredit=sc, bonds=[],
        goals=["Pass"], pronouns="they/them")


def _cp(faction="Sovereign Nexus", req=0, cid="cp_1"):
    return Checkpoint(checkpoint_id=cid, name="Meridian Gate", faction=faction,
                      soulcredit_requirement=req,
                      description="Nexus customs checkpoint")


class TestCutOff:
    """VIII.2: SC -6 and under is Cut Off from Nexus-aligned society."""

    def test_aligned_denies_at_minus_six_and_below(self):
        mech = MechanicsEngine()
        cp = _cp()
        for sc in (-6, -8):
            res = mech.validate_checkpoint_access(_char(sc), cp)
            assert res.is_allowed is False and res.sc_blocked is True

    def test_aligned_allows_above_cutoff_when_no_requirement(self):
        mech = MechanicsEngine()
        cp = _cp()
        for sc in (-5, 0, 3):
            assert mech.validate_checkpoint_access(_char(sc), cp).is_allowed is True


class TestRequirement:

    def test_checkpoint_requirement_gates(self):
        mech = MechanicsEngine()
        cp = _cp(req=2)  # this gate wants standing >= +2
        assert mech.validate_checkpoint_access(_char(1), cp).is_allowed is False
        assert mech.validate_checkpoint_access(_char(2), cp).is_allowed is True

    def test_negative_requirement_allows_rough_sector(self):
        mech = MechanicsEngine()
        cp = _cp(faction="Freeborn", req=-3)  # rough sector, opt-in gate
        assert mech.validate_checkpoint_access(_char(-5), cp).is_allowed is False
        assert mech.validate_checkpoint_access(_char(-3), cp).is_allowed is True


class TestNonAligned:

    def test_non_aligned_no_requirement_never_asks(self):
        mech = MechanicsEngine()
        cp = _cp(faction="Freeborn", req=0)
        assert mech.validate_checkpoint_access(_char(-9), cp).is_allowed is True

    def test_non_aligned_ignores_universal_cutoff(self):
        """The -6 Cut-Off is Nexus jurisdiction; a Freeborn gate with no
        requirement lets the Cut-Off walk through."""
        mech = MechanicsEngine()
        cp = _cp(faction="Freeborn", req=0)
        assert mech.validate_checkpoint_access(_char(-7), cp).is_allowed is True


class TestSharedStateStorage:

    def test_add_and_get_checkpoint(self):
        ss = SharedState()
        cp = _cp(cid="cp_meridian")
        ss.add_checkpoint(cp)
        assert ss.get_checkpoint_by_id("cp_meridian") is cp
        assert ss.get_checkpoint_by_id("nope") is None


class TestSurfacing:
    """Checkpoints must be visible + routable so the gate fires in free play."""

    def test_explore_action_accepts_checkpoint_id(self):
        from aeonisk.multiagent.schemas.player_action import ExploreAction
        a = ExploreAction(
            intent="Move through Meridian Gate to the trade ring",
            description="Approach the checkpoint and present credentials for passage.",
            attribute="Perception", skill="Awareness",
            difficulty_estimate=15, difficulty_justification="routine passage",
            checkpoint_id="cp_meridian")
        assert a.checkpoint_id == "cp_meridian"

    def test_format_lists_gate_with_id(self):
        from types import SimpleNamespace
        from aeonisk.multiagent.player import AIPlayerAgent
        ss = SimpleNamespace(current_checkpoints=[_cp(faction="Sovereign Nexus", req=-2, cid="cp_meridian")])
        out = AIPlayerAgent._format_checkpoint_status(SimpleNamespace(shared_state=ss))
        assert "cp_meridian" in out and "Meridian Gate" in out and "checkpoint_id" in out

    def test_format_none_when_empty(self):
        from types import SimpleNamespace
        from aeonisk.multiagent.player import AIPlayerAgent
        stub = SimpleNamespace(shared_state=SimpleNamespace(current_checkpoints=[]))
        assert "No gated checkpoints" in AIPlayerAgent._format_checkpoint_status(stub)
