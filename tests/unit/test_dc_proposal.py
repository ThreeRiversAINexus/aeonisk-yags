"""
Tests for LLM-proposed difficulty with mechanical floor enforcement.

Corpus v2 finding (2026-07-04): 91% of all rolls used DC 18 because
calculate_dc assigns difficulty purely from a hardcoded action-type table
- skilled characters succeeded 98% of rolls, unskilled 0%. The design
intent was always LLM-controlled difficulty estimation; the table now
serves as one-directional guardrails (floors) over the proposal instead
of the answer.

Contract:
- proposed_dc=None -> legacy table behavior, unchanged
- proposed_dc given -> dc = clamp(proposed, floor=category_floor, 40)
- floors are one-directional: proposals may raise difficulty freely,
  but can never drop rituals below CHALLENGING (Astral Arts x Willpower
  stays priced) nor anything below TRIVIAL-adjacent bounds
- void-level pressure still applies on top of the proposal
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.mechanics import MechanicsEngine, Difficulty


@pytest.fixture
def engine():
    return MechanicsEngine()


class TestLegacyPathUnchanged:
    """No proposal -> the category table answers, exactly as before."""

    def test_combat_default(self, engine):
        assert engine.calculate_dc(intent="shoot the guard",
                                   action_type="combat") == 18

    def test_technical_default(self, engine):
        assert engine.calculate_dc(intent="splice the panel",
                                   action_type="technical") == 20

    def test_ritual_default(self, engine):
        assert engine.calculate_dc(intent="commune with the ley line",
                                   action_type="ritual", is_ritual=True) == 22


class TestProposedDifficulty:

    def test_proposal_below_table_is_honored(self, engine):
        """An easy task can finally be easy: fiction beats category."""
        dc = engine.calculate_dc(intent="pick the rusted lock in an empty room",
                                 action_type="technical", proposed_dc=12)
        assert dc == 12

    def test_proposal_above_table_is_honored(self, engine):
        dc = engine.calculate_dc(intent="disarm the bomb blindfolded",
                                 action_type="technical", proposed_dc=30)
        assert dc == 30

    def test_ritual_floor_enforced(self, engine):
        """Rituals can never be proposed down below CHALLENGING."""
        dc = engine.calculate_dc(intent="quick divination",
                                 action_type="ritual", is_ritual=True,
                                 proposed_dc=10)
        assert dc == Difficulty.CHALLENGING.value

    def test_ritual_proposal_above_floor_honored(self, engine):
        dc = engine.calculate_dc(intent="rewrite a soul-bond",
                                 action_type="ritual", is_ritual=True,
                                 proposed_dc=30)
        assert dc == 30

    def test_general_floor_is_trivial(self, engine):
        """Non-ritual proposals floor at TRIVIAL - no DC 3 gimmes."""
        dc = engine.calculate_dc(intent="open an unlocked door dramatically",
                                 action_type="exploration", proposed_dc=3)
        assert dc == Difficulty.TRIVIAL.value

    def test_ceiling_is_legendary(self, engine):
        dc = engine.calculate_dc(intent="impossible feat",
                                 action_type="combat", proposed_dc=99)
        assert dc == Difficulty.LEGENDARY.value

    def test_extreme_flag_still_raises_floor(self, engine):
        """is_extreme keeps its guardrail even against a low proposal."""
        dc = engine.calculate_dc(intent="leap between moving trains",
                                 action_type="combat", is_extreme=True,
                                 proposed_dc=12)
        assert dc >= Difficulty.DIFFICULT.value

    def test_void_pressure_applies_on_top_of_proposal(self, engine):
        engine.scene_void_level = 7
        dc = engine.calculate_dc(intent="steady hands in the breach zone",
                                 action_type="technical", proposed_dc=14)
        assert dc == 18  # 14 + 4 void pressure

    def test_zero_or_negative_proposal_treated_as_absent(self, engine):
        """Players sometimes emit difficulty_estimate=0 for free actions;
        that is not a proposal to make things trivial."""
        dc = engine.calculate_dc(intent="scan the room",
                                 action_type="sensing", proposed_dc=0)
        assert dc == 20  # legacy table
