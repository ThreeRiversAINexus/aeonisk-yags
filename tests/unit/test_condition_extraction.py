"""
Tests for condition field extraction in structured_output_helpers.py.

Spec 14, Bugs 2 & 5: Verifies that `target` and `protection_amount` fields
are preserved when extracting conditions from Pydantic ActionResolution
objects into the dict format consumed by dm.py.

TDD: These tests are written FIRST (red phase) before fixing the extraction.
"""

import pytest

from aeonisk.multiagent.schemas.shared_types import (
    Condition as PydanticCondition,
    SuccessTier,
    SoulcreditChange,
)
from aeonisk.multiagent.schemas.action_resolution import (
    ActionResolution,
    MechanicalEffects,
)
from aeonisk.multiagent.structured_output_helpers import (
    extract_effects_from_resolution,
)


# ============================================================================
# Helper to build a minimal ActionResolution with conditions
# ============================================================================

def _make_resolution_with_conditions(conditions):
    """Build a minimal ActionResolution containing the given conditions."""
    # ActionResolution.narration requires min 200 chars
    narration = (
        "The agent steadies their nerve and channels energy through the conduit. "
        "Sparks cascade across the barrier matrix as the effect takes hold, rippling "
        "outward in concentric waves of distorted light. The condition settles over "
        "the target like a weight pressing down on every nerve ending at once."
    )
    return ActionResolution(
        narration=narration,
        success_tier=SuccessTier.MODERATE,
        margin=5,
        effects=MechanicalEffects(
            conditions=conditions,
            soulcredit_changes=[
                SoulcreditChange(
                    character_name="TestChar",
                    amount=0,
                    reason="test condition extraction"
                )
            ],
        ),
    )


# ============================================================================
# Bug 2: target field lost during extraction
# ============================================================================

class TestConditionExtractionTarget:
    """Verify structured_output_helpers extracts the `target` field."""

    def test_extraction_includes_target(self):
        """Condition with target field should preserve target in extracted dict."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Stunned",
                penalty=-3,
                duration=2,
                description="stunned for 2 rounds, -3 to all rolls",
                target="tgt_abc1",
            )
        ])
        effects = extract_effects_from_resolution(resolution)
        conditions = effects['conditions']

        assert len(conditions) == 1
        assert conditions[0]['target'] == 'tgt_abc1'

    def test_extraction_target_none_when_not_specified(self):
        """Condition without target should have target=None in extracted dict."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Inspired",
                penalty=2,
                duration=3,
                description="+2 to all rolls for 3 rounds",
            )
        ])
        effects = extract_effects_from_resolution(resolution)
        conditions = effects['conditions']

        assert len(conditions) == 1
        assert conditions[0]['target'] is None

    def test_multi_target_conditions_preserve_different_targets(self):
        """Multiple conditions with different targets should each preserve their target."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Shaken",
                penalty=-2,
                duration=1,
                description="-2 to all rolls, morale shaken",
                target="tgt_abc1",
            ),
            PydanticCondition(
                name="Pinned",
                penalty=-4,
                duration=1,
                description="-4 to all actions while pinned down",
                target="tgt_def2",
            ),
        ])
        effects = extract_effects_from_resolution(resolution)
        conditions = effects['conditions']

        assert len(conditions) == 2
        assert conditions[0]['target'] == 'tgt_abc1'
        assert conditions[1]['target'] == 'tgt_def2'


# ============================================================================
# Bug 5: protection_amount not propagated through pipeline
# ============================================================================

class TestConditionExtractionProtection:
    """Verify structured_output_helpers extracts the `protection_amount` field."""

    def test_extraction_includes_protection_amount(self):
        """Condition with protection_amount should preserve it in extracted dict."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Astral Barrier",
                penalty=0,
                duration=2,
                description="Blocks 10 damage",
                target="tgt_7a3f",
                protection_amount=10,
            )
        ])
        effects = extract_effects_from_resolution(resolution)
        conditions = effects['conditions']

        assert len(conditions) == 1
        assert conditions[0]['protection_amount'] == 10

    def test_extraction_protection_none_when_not_specified(self):
        """Condition without protection_amount has protection_amount=None."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Stunned",
                penalty=-3,
                duration=2,
                description="stunned, -3 to all rolls",
            )
        ])
        effects = extract_effects_from_resolution(resolution)
        conditions = effects['conditions']

        assert len(conditions) == 1
        assert conditions[0]['protection_amount'] is None

    def test_extraction_preserves_all_fields_together(self):
        """All condition fields (type, penalty, duration, description, target, protection_amount) present."""
        resolution = _make_resolution_with_conditions([
            PydanticCondition(
                name="Astral Barrier",
                penalty=0,
                duration=3,
                description="Blocks 15 damage",
                target="tgt_7a3f",
                protection_amount=15,
            )
        ])
        effects = extract_effects_from_resolution(resolution)
        cond = effects['conditions'][0]

        assert cond['type'] == 'Astral Barrier'
        assert cond['penalty'] == 0
        assert cond['duration'] == 3
        assert cond['description'] == 'Blocks 15 damage'
        assert cond['target'] == 'tgt_7a3f'
        assert cond['protection_amount'] == 15
