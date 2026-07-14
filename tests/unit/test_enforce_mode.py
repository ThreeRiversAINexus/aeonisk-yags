"""Tests for post_resolution_adjudication: 'enforce' mode.

Contract (handoff task 1b(b), ledger-authority scope):
- The full-context magistrate's article-cited rulings become the APPLIED
  soulcredit/void ledger values (narrator writes story, magistrate writes law).
- Narration-call economy deltas are suppressed under enforce so the magistrate
  is the sole ledger writer (no double-count).
- off / true / 'full_context' modes stay observe-only and byte-identical.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.post_adjudication import (
    PostRuling,
    PostRulings,
    apply_rulings,
    rulings_event_data,
    ENFORCE_REGIME_LABEL,
)
from aeonisk.multiagent.mechanics import MechanicsEngine

ROSTER = [
    {"agent_id": "p1", "name": "Vessel Sera Karsel", "faction": "Tempest"},
    {"agent_id": "p2", "name": "Guardian Rhea Ireveth", "faction": "Pantheon"},
]


def _rulings(*items):
    return PostRulings(rulings=list(items))


class TestApplyRulings:

    def test_soulcredit_delta_applied_to_state(self):
        mech = MechanicsEngine()
        mech.get_soulcredit_state("p1")  # initialize at 0
        rulings = _rulings(PostRuling(
            character_name="Vessel Sera Karsel",
            action_summary="forged the manifest",
            soulcredit_delta=-2, reason="record tampering [II.4]"))
        records = apply_rulings(rulings, mech, ROSTER, round_num=1)
        assert mech.soulcredit_states["p1"].score == -2
        assert records[0]["applied"] is True
        assert records[0]["agent_id"] == "p1"

    def test_void_delta_applied_to_state(self):
        mech = MechanicsEngine()
        rulings = _rulings(PostRuling(
            character_name="Guardian Rhea Ireveth",
            action_summary="weaponized void",
            soulcredit_delta=-3, void_delta=3,
            reason="weaponized Void against persons [III.3]"))
        apply_rulings(rulings, mech, ROSTER, round_num=2)
        assert mech.void_states["p2"].score == 3
        assert mech.soulcredit_states["p2"].score == -3

    def test_negative_void_delta_reduces(self):
        mech = MechanicsEngine()
        v = mech.get_void_state("p1")
        v.add_void(5, "seed")
        rulings = _rulings(PostRuling(
            character_name="Vessel Sera Karsel",
            action_summary="purified the altar",
            soulcredit_delta=1, void_delta=-2, reason="cleansing Void [I.3]"))
        apply_rulings(rulings, mech, ROSTER, round_num=3)
        assert mech.void_states["p1"].score == 3

    def test_void_ruling_can_trip_gate_threshold(self):
        """Void has real teeth (stealth gate / bond dormancy at >=7)."""
        mech = MechanicsEngine()
        mech.get_void_state("p1").add_void(6, "prior")
        rulings = _rulings(PostRuling(
            character_name="Vessel Sera Karsel", action_summary="void rite",
            soulcredit_delta=0, void_delta=2, reason="void exposure"))
        apply_rulings(rulings, mech, ROSTER, round_num=4)
        assert mech.void_states["p1"].score >= 7

    def test_fuzzy_name_match(self):
        mech = MechanicsEngine()
        rulings = _rulings(PostRuling(
            character_name="Sera Karsel",  # missing "Vessel" title prefix
            action_summary="bribed the official",
            soulcredit_delta=-1, reason="bribery [II.7]"))
        records = apply_rulings(rulings, mech, ROSTER, round_num=1)
        assert records[0]["applied"] is True
        assert records[0]["agent_id"] == "p1"
        assert mech.soulcredit_states["p1"].score == -1

    def test_unmatched_name_skips_without_crash(self):
        mech = MechanicsEngine()
        rulings = _rulings(PostRuling(
            character_name="Nobody At All",
            action_summary="did a thing",
            soulcredit_delta=-2, reason="fraud [II.3]"))
        records = apply_rulings(rulings, mech, ROSTER, round_num=1)
        assert records[0]["applied"] is False
        assert records[0].get("error")
        # No stray state written for a phantom character
        assert all(s.score == 0 for s in mech.soulcredit_states.values())

    def test_zero_deltas_are_noops_but_recorded(self):
        mech = MechanicsEngine()
        rulings = _rulings(PostRuling(
            character_name="Vessel Sera Karsel",
            action_summary="routine procedure",
            soulcredit_delta=0, void_delta=0, reason="honest labor [II.9]"))
        records = apply_rulings(rulings, mech, ROSTER, round_num=1)
        assert records[0]["applied"] is True
        # Zero deltas touch nothing; the ledger stays at baseline 0.
        assert mech.get_soulcredit_state("p1").score == 0


class TestEventData:

    def test_default_call_is_observe_only_unchanged(self):
        """Existing observe-only callers must get the byte-identical dict."""
        rulings = _rulings(PostRuling(
            character_name="Renna", action_summary="maintained the bluff",
            soulcredit_delta=-2, reason="deception [II.3]"))
        data = rulings_event_data(rulings)
        assert data == {
            "experiment": "post_resolution_adjudication",
            "applied_to_state": False,
            "rulings": [rulings.rulings[0].model_dump()],
        }

    def test_enforce_event_marks_applied_and_regime(self):
        rulings = _rulings(PostRuling(
            character_name="Vessel Sera Karsel",
            action_summary="forged the manifest",
            soulcredit_delta=-2, reason="record tampering [II.4]"))
        records = [{"agent_id": "p1", "applied": True, "soulcredit_delta": -2}]
        data = rulings_event_data(rulings, applied_to_state=True,
                                  applied_records=records,
                                  regime=ENFORCE_REGIME_LABEL)
        assert data["applied_to_state"] is True
        assert data["regime"] == ENFORCE_REGIME_LABEL
        assert data["applied"] == records

    def test_regime_label_value(self):
        assert ENFORCE_REGIME_LABEL == "v1.1-law-LIVE"


class TestSourceWiring:
    """Guard the session/dm wiring so enforce can't silently regress."""

    SESSION = (Path(__file__).parent.parent.parent /
               "scripts/aeonisk/multiagent/session.py").read_text()
    DM = (Path(__file__).parent.parent.parent /
          "scripts/aeonisk/multiagent/dm.py").read_text()

    def test_session_treats_enforce_as_mode(self):
        assert "'enforce'" in self.SESSION

    def test_session_builds_scene_context_for_enforce(self):
        # enforce implies full-context: both modes gate the scene_context build
        assert "'full_context', 'enforce'" in self.SESSION \
            or "'enforce', 'full_context'" in self.SESSION

    def test_session_sets_suppression_flag(self):
        assert "suppress_narration_economy" in self.SESSION

    def test_dm_gates_narration_economy_on_flag(self):
        assert "suppress_narration_economy" in self.DM
