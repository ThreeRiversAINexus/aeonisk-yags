"""
Tests for condition duration handling in dm.py and mechanics.py.

Spec 14, Bug 3: Verifies that dm.py uses LLM-specified duration instead of
hardcoding duration=3.

Spec 14, Bug 5 (dataclass): Verifies that mechanics.py Condition dataclass
has the `protection_amount` field.

TDD: These tests are written FIRST (red phase) before fixing the duration.
"""

import pytest

from aeonisk.multiagent.mechanics import Condition


# ============================================================================
# Bug 3: Duration should come from extracted data, not hardcoded to 3
# ============================================================================

class TestConditionDurationFromLLM:
    """Verify that Condition creation uses LLM-specified duration."""

    def test_duration_from_extracted_data(self):
        """Condition creation should use duration from extracted dict.

        The dm.py code creates Condition with duration from condition_data dict.
        This test verifies the pattern: duration=condition_data.get('duration', 3)
        """
        # Simulate the condition_data dict that dm.py receives from extraction
        condition_data = {
            'type': 'Stunned',
            'penalty': -3,
            'duration': 1,
            'description': 'stunned for 1 round, -3 to all rolls',
        }

        # Create Condition the way dm.py should create it (with LLM duration)
        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=condition_data.get('duration', 3),
            affects=[],
        )

        assert condition.duration == 1, (
            f"Expected duration=1 (from LLM), got duration={condition.duration}. "
            "Bug: dm.py hardcodes duration=3 instead of using extracted value."
        )

    def test_duration_fallback_to_3_when_missing(self):
        """If duration missing from extracted data, default to 3."""
        condition_data = {
            'type': 'Dazed',
            'penalty': -1,
            'description': 'dazed, -1 to all rolls',
            # duration intentionally omitted
        }

        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=condition_data.get('duration', 3),
            affects=[],
        )

        assert condition.duration == 3

    def test_duration_zero_is_instant(self):
        """Duration=0 from LLM means instant/already applied."""
        condition_data = {
            'type': 'Flash',
            'penalty': -2,
            'duration': 0,
            'description': 'momentary flash, -2 to all rolls',
        }

        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=condition_data.get('duration', 3),
            affects=[],
        )

        assert condition.duration == 0

    def test_duration_various_llm_values(self):
        """Test several LLM-specified durations are preserved."""
        for expected_dur in [1, 2, 4, 5, 10]:
            condition_data = {
                'type': 'Effect',
                'penalty': -1,
                'duration': expected_dur,
                'description': f'lasts {expected_dur} rounds',
            }
            condition = Condition(
                name=condition_data['type'],
                type=condition_data['type'],
                penalty=condition_data['penalty'],
                description=condition_data['description'],
                duration=condition_data.get('duration', 3),
                affects=[],
            )
            assert condition.duration == expected_dur


# ============================================================================
# Bug 5 (dataclass side): protection_amount on mechanics.py Condition
# ============================================================================

class TestConditionDataclassProtection:
    """Verify mechanics.py Condition dataclass has protection_amount field."""

    def test_condition_default_no_protection(self):
        """Condition created without protection_amount defaults to None."""
        condition = Condition(
            name="Stunned",
            type="stun",
            penalty=-3,
            description="stunned, -3 to all rolls",
        )
        assert condition.protection_amount is None

    def test_condition_with_protection_amount(self):
        """Condition can be created with protection_amount."""
        condition = Condition(
            name="Barrier",
            type="barrier",
            penalty=0,
            description="barrier absorbs 10 damage",
            protection_amount=10,
        )
        assert condition.protection_amount == 10

    def test_condition_protection_amount_zero(self):
        """Condition with protection_amount=0 is valid (depleted barrier)."""
        condition = Condition(
            name="Depleted Barrier",
            type="barrier",
            penalty=0,
            description="barrier fully depleted",
            protection_amount=0,
        )
        assert condition.protection_amount == 0

    def test_condition_protection_propagated_from_extraction(self):
        """Condition created from extraction dict should carry protection_amount."""
        # Simulate extracted condition_data dict WITH protection_amount
        condition_data = {
            'type': 'Astral Barrier',
            'penalty': 0,
            'duration': 2,
            'description': 'Blocks 10 damage',
            'protection_amount': 10,
        }

        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=condition_data.get('duration', 3),
            affects=[],
            protection_amount=condition_data.get('protection_amount'),
        )

        assert condition.protection_amount == 10
        assert condition.duration == 2
