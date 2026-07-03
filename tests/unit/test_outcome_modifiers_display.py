"""
Tests for outcome modifiers display in action resolution stdout formatting.

Issue: Situational modifiers and synergy bonuses should be visible in the
stdout output during adjudication phase, but currently aren't shown.
"""

import pytest
from types import SimpleNamespace
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


def make_resolution_mock(
    intent: str,
    attribute: str,
    skill: str,
    attribute_value: int,
    skill_value: int,
    roll: int,
    total: int,
    difficulty: int,
    margin: int,
    success: bool,
    outcome_tier: SuccessTier,
    narration: str = ""
) -> SimpleNamespace:
    """
    Create a mock resolution object for testing format_resolution_for_narration().

    The format_resolution_for_narration() function uses getattr() with defaults,
    so it works with any object that has the right attributes - doesn't require
    a real ActionResolution Pydantic model.
    """
    return SimpleNamespace(
        intent=intent,
        attribute=attribute,
        skill=skill,
        attribute_value=attribute_value,
        skill_value=skill_value,
        roll=roll,
        total=total,
        difficulty=difficulty,
        margin=margin,
        success=success,
        outcome_tier=outcome_tier,
        narration=narration,
    )


class TestOutcomeModifiersDisplay:
    """Test that outcome modifiers are displayed in action resolution output."""

    def test_format_resolution_with_no_modifiers(self):
        """Test resolution formatting without modifiers (baseline)."""
        mechanics = MechanicsEngine()

        resolution = make_resolution_mock(
            intent="Hack terminal",
            attribute="Intelligence",
            skill="Tech",
            attribute_value=4,
            skill_value=3,
            roll=12,
            total=28,
            difficulty=20,
            margin=8,
            success=True,
            outcome_tier=SuccessTier.GOOD,
            narration="You hack into the terminal successfully."
        )

        formatted = mechanics.format_resolution_for_narration(resolution)

        # Should show standard output without modifiers line
        assert "**Hack terminal**" in formatted
        assert "Roll: Intelligence × Tech" in formatted
        assert "Calculation: 4 × 3 + d20(12) = **28**" in formatted
        assert "DC: 20 | Margin: +8 | Tier: **GOOD**" in formatted
        assert "Modifiers:" not in formatted  # No modifiers line when empty

    def test_format_resolution_with_single_modifier(self):
        """Test resolution formatting with one situational modifier."""
        mechanics = MechanicsEngine()

        resolution = make_resolution_mock(
            intent="Snipe enemy",
            attribute="Dexterity",
            skill="Guns",
            attribute_value=5,
            skill_value=4,
            roll=14,
            total=36,
            difficulty=26,
            margin=10,
            success=True,
            outcome_tier=SuccessTier.GOOD,
        )

        modifiers = {"high_ground": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        # Should show modifiers line
        assert "Modifiers: [high_ground: +2]" in formatted or "Modifiers: high_ground +2" in formatted

    def test_format_resolution_with_multiple_modifiers(self):
        """Test resolution formatting with multiple modifiers (positive and negative)."""
        mechanics = MechanicsEngine()

        resolution = make_resolution_mock(
            intent="Attack through cover",
            attribute="Dexterity",
            skill="Guns",
            attribute_value=5,
            skill_value=4,
            roll=11,
            total=28,
            difficulty=25,
            margin=3,
            success=True,
            outcome_tier=SuccessTier.MODERATE,
        )

        modifiers = {
            "synergy_tactical": 2,
            "cover_penalty": -3,
            "darkness": -2,
            "coordination": 1
        }
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        # Should show all modifiers
        assert "Modifiers:" in formatted
        assert "synergy_tactical" in formatted or "tactical" in formatted
        assert "+2" in formatted  # synergy bonus
        assert "-3" in formatted  # cover penalty
        assert "-2" in formatted  # darkness penalty
        assert "+1" in formatted or "coordination" in formatted  # coordination bonus

        # Should show net modifier (2 - 3 - 2 + 1 = -2)
        assert "Net: -2" in formatted or "Total: -2" in formatted

    def test_format_resolution_with_synergy_bonus(self):
        """Test that synergy bonuses from hybrid actions are shown."""
        mechanics = MechanicsEngine()

        resolution = make_resolution_mock(
            intent="Examine void-corrupted artifact",
            attribute="Perception",
            skill="Awareness",
            attribute_value=4,
            skill_value=3,
            roll=15,
            total=29,
            difficulty=17,
            margin=12,
            success=True,
            outcome_tier=SuccessTier.EXCELLENT,
        )

        # Synergy from Magic Theory assisting Awareness
        modifiers = {"synergy_magic_theory": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "synergy" in formatted.lower() or "magic_theory" in formatted
        assert "+2" in formatted

    def test_format_resolution_with_coordination_bonus(self):
        """Test that coordination bonuses from teamwork are shown."""
        mechanics = MechanicsEngine()

        resolution = make_resolution_mock(
            intent="Flank enemy position",
            attribute="Dexterity",
            skill="Combat",
            attribute_value=4,
            skill_value=3,
            roll=13,
            total=28,
            difficulty=21,
            margin=7,
            success=True,
            outcome_tier=SuccessTier.GOOD,
        )

        modifiers = {"coordination": 3}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "coordination" in formatted.lower()
        assert "+3" in formatted
