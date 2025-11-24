"""
Tests for outcome modifiers display in action resolution stdout formatting.

Issue: Situational modifiers and synergy bonuses should be visible in the
stdout output during adjudication phase, but currently aren't shown.
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution, MechanicalEffects
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


class TestOutcomeModifiersDisplay:
    """Test that outcome modifiers are displayed in action resolution output."""

    def test_format_resolution_with_no_modifiers(self):
        """Test resolution formatting without modifiers (baseline)."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="You hack into the terminal successfully. Your neural interface slides through the security protocols like silk, each layer peeling back to reveal the corrupted data streams beneath. The screen flickers with decrypted access logs.",
            success_tier=SuccessTier.GOOD,
            margin=8,
            effects=MechanicalEffects()
        )

        # Add required fields for formatting
        resolution.intent = "Hack terminal"
        resolution.attribute = "Intelligence"
        resolution.skill = "Tech"
        resolution.attribute_value = 4
        resolution.skill_value = 3
        resolution.roll = 12
        resolution.total = 28
        resolution.difficulty = 20
        resolution.success = True
        resolution.outcome_tier = SuccessTier.GOOD

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

        resolution = ActionResolution(
            narration="Your elevated position gives you a clear shot.",
            success_tier=SuccessTier.GOOD,
            margin=10,
            effects=MechanicalEffects()
        )

        # Add required fields
        resolution.intent = "Snipe enemy"
        resolution.attribute = "Dexterity"
        resolution.skill = "Guns"
        resolution.attribute_value = 5
        resolution.skill_value = 4
        resolution.roll = 14
        resolution.total = 36
        resolution.difficulty = 26
        resolution.success = True
        resolution.outcome_tier = SuccessTier.GOOD

        modifiers = {"high_ground": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        # Should show modifiers line
        assert "Modifiers: [high_ground: +2]" in formatted or "Modifiers: high_ground +2" in formatted

    def test_format_resolution_with_multiple_modifiers(self):
        """Test resolution formatting with multiple modifiers (positive and negative)."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="Despite the darkness and cover, your shot finds its mark.",
            success_tier=SuccessTier.MODERATE,
            margin=3,
            effects=MechanicalEffects()
        )

        # Add required fields
        resolution.intent = "Attack through cover"
        resolution.attribute = "Dexterity"
        resolution.skill = "Guns"
        resolution.attribute_value = 5
        resolution.skill_value = 4
        resolution.roll = 11
        resolution.total = 28
        resolution.difficulty = 25
        resolution.success = True
        resolution.outcome_tier = SuccessTier.MODERATE

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

        resolution = ActionResolution(
            narration="Your knowledge of void theory enhances your perception.",
            success_tier=SuccessTier.EXCELLENT,
            margin=12,
            effects=MechanicalEffects()
        )

        # Add required fields
        resolution.intent = "Examine void-corrupted artifact"
        resolution.attribute = "Perception"
        resolution.skill = "Awareness"
        resolution.attribute_value = 4
        resolution.skill_value = 3
        resolution.roll = 15
        resolution.total = 29
        resolution.difficulty = 17
        resolution.success = True
        resolution.outcome_tier = SuccessTier.EXCELLENT

        # Synergy from Magick Theory assisting Awareness
        modifiers = {"synergy_magick_theory": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "synergy" in formatted.lower() or "magick_theory" in formatted
        assert "+2" in formatted

    def test_format_resolution_with_coordination_bonus(self):
        """Test that coordination bonuses from teamwork are shown."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="Your ally's covering fire creates an opening.",
            success_tier=SuccessTier.GOOD,
            margin=7,
            effects=MechanicalEffects()
        )

        # Add required fields
        resolution.intent = "Flank enemy position"
        resolution.attribute = "Dexterity"
        resolution.skill = "Combat"
        resolution.attribute_value = 4
        resolution.skill_value = 3
        resolution.roll = 13
        resolution.total = 28
        resolution.difficulty = 21
        resolution.success = True
        resolution.outcome_tier = SuccessTier.GOOD

        modifiers = {"coordination": 3}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "coordination" in formatted.lower()
        assert "+3" in formatted
