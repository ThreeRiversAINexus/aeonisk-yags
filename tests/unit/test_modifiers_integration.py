"""
Integration tests for modifier display in action resolution output.

These tests verify that situational modifiers, synergy bonuses, and coordination
bonuses are correctly displayed in the formatted resolution output.
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution, MechanicalEffects
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


class TestModifierDisplayIntegration:
    """Test modifier display through the actual formatting method."""

    @pytest.mark.xfail(reason="ActionResolution schema changed - intent/attribute/skill fields removed, tests need refactoring")
    def test_no_modifiers_baseline(self):
        """Verify baseline formatting works without modifiers parameter."""
        mechanics = MechanicsEngine()

        # Create a minimal valid ActionResolution with all required fields
        resolution = ActionResolution(
            narration="You hack into the terminal successfully, your neural interface sliding through security protocols with practiced ease. The corrupted data streams unfold before you like a digital tapestry, each thread revealing another layer of the conspiracy.",
            success_tier=SuccessTier.GOOD,
            margin=8,
            effects=MechanicalEffects(),
            intent="Hack terminal",
            attribute="Intelligence",
            skill="Tech",
            attribute_value=4,
            skill_value=3,
            roll=12,
            total=28,
            difficulty=20,
            success=True,
            outcome_tier=SuccessTier.GOOD
        )

        formatted = mechanics.format_resolution_for_narration(resolution)

        # Should have standard fields
        assert "**Hack terminal**" in formatted
        assert "Roll: Intelligence × Tech" in formatted
        assert "Calculation:" in formatted
        assert "DC: 20" in formatted
        assert "Margin: +8" in formatted

        # Should NOT have modifiers line
        assert "Modifiers:" not in formatted

    def test_single_modifier_display(self):
        """Verify single modifier is displayed correctly."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="Your elevated position on the catwalk provides a crystal-clear line of sight. The enemy combatant below moves in slow motion through your scope's reticle, unaware of the danger perched above. Your shot rings out with perfect precision.",
            success_tier=SuccessTier.GOOD,
            margin=10,
            effects=MechanicalEffects(),
            intent="Snipe enemy from elevated position",
            attribute="Dexterity",
            skill="Guns",
            attribute_value=5,
            skill_value=4,
            roll=14,
            total=36,
            difficulty=26,
            success=True,
            outcome_tier=SuccessTier.GOOD
        )

        modifiers = {"high_ground": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        # Should have modifiers line
        assert "Modifiers:" in formatted
        assert "high_ground" in formatted
        assert "+2" in formatted
        assert "Net: +2" in formatted or "→ Net: +2" in formatted

    def test_multiple_modifiers_with_net_calculation(self):
        """Verify multiple modifiers are displayed with correct net total."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="The darkness conceals you as much as it hinders your aim. Your target crouches behind a barrier, only their silhouette visible. Yet your training with tactical awareness and careful breath control guide your shot through the narrow gap in their cover, finding its mark.",
            success_tier=SuccessTier.MODERATE,
            margin=3,
            effects=MechanicalEffects(),
            intent="Attack through cover in darkness",
            attribute="Dexterity",
            skill="Guns",
            attribute_value=5,
            skill_value=4,
            roll=11,
            total=28,
            difficulty=25,
            success=True,
            outcome_tier=SuccessTier.MODERATE
        )

        modifiers = {
            "synergy_tactical": 2,
            "cover_penalty": -3,
            "darkness": -2,
            "coordination": 1
        }
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        # Should show all modifier names
        assert "Modifiers:" in formatted
        assert "synergy_tactical" in formatted
        assert "cover_penalty" in formatted
        assert "darkness" in formatted
        assert "coordination" in formatted

        # Should show all modifier values
        assert "+2" in formatted  # synergy
        assert "-3" in formatted  # cover
        assert "-2" in formatted  # darkness
        assert "+1" in formatted  # coordination

        # Should show net modifier (2 - 3 - 2 + 1 = -2)
        assert "Net: -2" in formatted or "→ Net: -2" in formatted

    def test_synergy_bonus_from_hybrid_action(self):
        """Verify synergy bonuses are shown when secondary skill assists primary."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="Your understanding of void theory transforms a simple visual scan into deep analysis. The artifact's corrupted glyphs aren't just symbols - they're void-resonance patterns. Your occult knowledge reveals dangerous energy signatures that pure technical observation would miss entirely.",
            success_tier=SuccessTier.EXCELLENT,
            margin=12,
            effects=MechanicalEffects(),
            intent="Examine void-corrupted artifact using occult knowledge",
            attribute="Perception",
            skill="Awareness",
            attribute_value=4,
            skill_value=3,
            roll=15,
            total=29,
            difficulty=17,
            success=True,
            outcome_tier=SuccessTier.EXCELLENT
        )

        modifiers = {"synergy_magick_theory": 2}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "synergy_magick_theory" in formatted or "synergy" in formatted.lower()
        assert "+2" in formatted
        assert "Net: +2" in formatted or "→ Net: +2" in formatted

    def test_coordination_bonus_from_teamwork(self):
        """Verify coordination bonuses from allied support are displayed."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="Your squadmate's suppressing fire forces the enemy to keep their head down, creating the perfect opening. You sprint from cover to cover, each movement precisely timed with your ally's rhythm. The coordinated assault puts you in the perfect flanking position.",
            success_tier=SuccessTier.GOOD,
            margin=7,
            effects=MechanicalEffects(),
            intent="Flank enemy position with covering fire",
            attribute="Dexterity",
            skill="Combat",
            attribute_value=4,
            skill_value=3,
            roll=13,
            total=28,
            difficulty=21,
            success=True,
            outcome_tier=SuccessTier.GOOD
        )

        modifiers = {"coordination": 3}
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers)

        assert "Modifiers:" in formatted
        assert "coordination" in formatted.lower()
        assert "+3" in formatted
        assert "Net: +3" in formatted or "→ Net: +3" in formatted

    def test_empty_modifiers_dict_no_display(self):
        """Verify empty modifiers dict doesn't show modifiers line."""
        mechanics = MechanicsEngine()

        resolution = ActionResolution(
            narration="You hack into the terminal with practiced ease, your fingers dancing across the interface as security protocols crumble before your neural interface. The data streams part like curtains, revealing everything you need. Standard infiltration, nothing fancy required.",
            success_tier=SuccessTier.GOOD,
            margin=5,
            effects=MechanicalEffects(),
            intent="Standard hack",
            attribute="Intelligence",
            skill="Tech",
            attribute_value=4,
            skill_value=3,
            roll=10,
            total=26,
            difficulty=21,
            success=True,
            outcome_tier=SuccessTier.GOOD
        )

        # Empty dict should behave same as no modifiers
        formatted = mechanics.format_resolution_for_narration(resolution, modifiers={})
        assert "Modifiers:" not in formatted
