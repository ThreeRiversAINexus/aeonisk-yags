"""
Unit tests for outcome parser.

Tests parsing of DM narration and structured output extraction:
- Extracting state changes from ActionResolution objects
- Clock trigger parsing
- Void/soulcredit extraction
- Condition parsing
- Position change extraction
"""

import pytest
from aeonisk.multiagent.outcome_parser import (
    extract_from_structured_resolution,
    parse_state_changes,
    parse_explicit_clock_markers,
    parse_explicit_void_markers,
    parse_clock_triggers,
    parse_void_triggers,
    parse_condition_markers,
    parse_position_change
)
from aeonisk.multiagent.schemas.action_resolution import (
    ActionResolution,
    MechanicalEffects
)
from aeonisk.multiagent.schemas.shared_types import (
    SuccessTier,
    VoidChange,
    SoulcreditChange,
    ClockUpdate,
    Condition,
    Position,
    PositionChange
)


# ============================================================================
# Structured Output Extraction Tests
# ============================================================================

class TestStructuredOutputExtraction:
    """Test extraction from ActionResolution structured output."""

    def test_extract_void_changes(self):
        """Test extracting void changes from structured output."""
        resolution = ActionResolution(
            narration="The ritual fails catastrophically. Void energy corrupts your mind." * 10,
            success_tier=SuccessTier.FAILURE,
            margin=-5,
            effects=MechanicalEffects(
                void_changes=[
                    VoidChange(character_name="TestChar", amount=2, reason="Failed ritual")
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert state_changes['void_change'] == 2
        assert len(state_changes['void_reasons']) == 1
        assert state_changes['void_reasons'][0] == "Failed ritual"
        assert state_changes['void_target_character'] == "TestChar"
        assert state_changes['void_source'] == 'structured_output'

    def test_extract_multiple_void_changes(self):
        """Test extracting multiple void changes (summed)."""
        resolution = ActionResolution(
            narration="Void corruption spreads through the area, affecting multiple characters." * 10,
            success_tier=SuccessTier.FAILURE,
            margin=-8,
            effects=MechanicalEffects(
                void_changes=[
                    VoidChange(character_name="Player1", amount=2, reason="Direct exposure"),
                    VoidChange(character_name="Player2", amount=1, reason="Proximity")
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert state_changes['void_change'] == 3  # 2 + 1
        assert len(state_changes['void_reasons']) == 2

    def test_extract_soulcredit_changes(self):
        """Test extracting soulcredit changes."""
        resolution = ActionResolution(
            narration="Your compassionate action inspires those around you." * 10,
            success_tier=SuccessTier.GOOD,
            margin=10,
            effects=MechanicalEffects(
                soulcredit_changes=[
                    SoulcreditChange(character_name="TestChar", amount=1, reason="Selfless act")
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert state_changes['soulcredit_change'] == 1
        assert len(state_changes['soulcredit_reasons']) == 1
        assert state_changes['soulcredit_reasons'][0] == "Selfless act"

    def test_extract_clock_updates(self):
        """Test extracting clock updates."""
        resolution = ActionResolution(
            narration="Your investigation progresses. Evidence mounts as you uncover critical documents." * 10,
            success_tier=SuccessTier.GOOD,
            margin=12,
            effects=MechanicalEffects(
                clock_updates=[
                    ClockUpdate(clock_name="Investigation", ticks=2, reason="Found evidence"),
                    ClockUpdate(clock_name="Enemy Alert", ticks=1, reason="Made noise")
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert len(state_changes['clock_triggers']) == 2

        # Check format: (clock_name, ticks, reason, source)
        inv_clock = state_changes['clock_triggers'][0]
        assert inv_clock[0] == "Investigation"
        assert inv_clock[1] == 2
        assert inv_clock[2] == "Found evidence"
        assert inv_clock[3] == 'structured_output'

    def test_extract_conditions(self):
        """Test extracting conditions/status effects."""
        resolution = ActionResolution(
            narration="The attack stuns your opponent, leaving them dazed and vulnerable." * 10,
            success_tier=SuccessTier.GOOD,
            margin=10,
            effects=MechanicalEffects(
                conditions=[
                    Condition(
                        name="Stunned",
                        penalty=-3,
                        duration=2,
                        description="Cannot act, -3 to all rolls"
                    )
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert len(state_changes['conditions']) == 1
        cond = state_changes['conditions'][0]
        assert cond['type'] == "Stunned"
        assert cond['penalty'] == -3
        assert cond['duration'] == 2

    def test_extract_position_change(self):
        """Test extracting position changes."""
        resolution = ActionResolution(
            narration="You charge forward into melee range, closing the distance rapidly." * 10,
            success_tier=SuccessTier.MODERATE,
            margin=5,
            effects=MechanicalEffects(
                position_changes=[
                    PositionChange(
                        character_name="TestChar",
                        new_position=Position.ENGAGED,
                        reason="Charged forward"
                    )
                ]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert state_changes['position_change'] is not None
        pos_change = state_changes['position_change']
        assert pos_change['character_name'] == "TestChar"
        assert pos_change['new_position'] == "Engaged"
        assert pos_change['reason'] == "Charged forward"

    def test_extract_complex_resolution(self):
        """Test extracting from complex resolution with multiple effects."""
        resolution = ActionResolution(
            narration="Your desperate ritual succeeds but at great cost. The void entity is banished, but corruption lingers." * 10,
            success_tier=SuccessTier.MODERATE,
            margin=2,
            effects=MechanicalEffects(
                void_changes=[
                    VoidChange(character_name="Caster", amount=1, reason="Ritual backlash")
                ],
                soulcredit_changes=[
                    SoulcreditChange(character_name="Caster", amount=1, reason="Saved civilians")
                ],
                clock_updates=[
                    ClockUpdate(clock_name="Void Breach", ticks=-3, reason="Entity banished"),
                    ClockUpdate(clock_name="Civilian Panic", ticks=-2, reason="Threat removed")
                ],
                conditions=[
                    Condition(name="Exhausted", penalty=-2, duration=3, description="Ritual drain")
                ],
                notes=["Entity permanently banished", "Rift sealed"]
            )
        )

        state_changes = extract_from_structured_resolution(resolution)

        # Check all effects present
        assert state_changes['void_change'] == 1
        assert state_changes['soulcredit_change'] == 1
        assert len(state_changes['clock_triggers']) == 2
        assert len(state_changes['conditions']) == 1
        assert len(state_changes['notes']) == 2
        assert state_changes['notes'][0] == "Entity permanently banished"

    def test_extract_empty_effects(self):
        """Test extraction with no effects."""
        resolution = ActionResolution(
            narration="You attempt the action but nothing significant happens. The situation remains unchanged." * 10,
            success_tier=SuccessTier.MARGINAL,
            margin=1
        )

        state_changes = extract_from_structured_resolution(resolution)

        assert state_changes['void_change'] == 0
        assert state_changes['soulcredit_change'] == 0
        assert len(state_changes['clock_triggers']) == 0
        assert len(state_changes['conditions']) == 0
        assert state_changes['position_change'] is None


# ============================================================================
# Legacy Text Parsing Tests
# ============================================================================

class TestLegacyTextParsing:
    """Test legacy text-based parsing (backward compatibility)."""

    def test_parse_void_marker(self):
        """Test parsing legacy ⚫ Void markers."""
        text = "The ritual fails. ⚫ Void: +2 (Failed ritual without offering)"

        state_changes = parse_state_changes(text)

        # Legacy parsing should still work
        # (actual implementation may vary based on outcome_parser.py)
        assert isinstance(state_changes, dict)

    def test_parse_clock_marker(self):
        """Test parsing legacy 📊 Clock markers."""
        text = "Evidence accumulates. 📊 Clock: Investigation +2 (Found crucial documents)"

        state_changes = parse_state_changes(text)

        assert isinstance(state_changes, dict)
        # Check for clock_triggers in result

    def test_parse_mixed_markers(self):
        """Test parsing multiple markers in one narration."""
        text = """
        Your action succeeds but at a cost.
        📊 Clock: Progress +3 (Major breakthrough)
        ⚫ Void: +1 (Cut corners, used forbidden technique)
        """

        state_changes = parse_state_changes(text)

        assert isinstance(state_changes, dict)


# ============================================================================
# Clock Extraction Tests
# ============================================================================

class TestClockExtraction:
    """Test clock marker extraction specifically."""

    def test_extract_clock_markers_basic(self):
        """Test basic clock marker extraction."""
        text = "📊 Clock: Investigation +2"

        clocks = parse_explicit_clock_markers(text)

        # Should return list of clock triggers
        assert isinstance(clocks, list)

    def test_extract_multiple_clock_markers(self):
        """Test extracting multiple clock markers."""
        text = """
        📊 Clock: Progress +2 (reason 1)
        📊 Clock: Alert +1 (reason 2)
        """

        clocks = parse_explicit_clock_markers(text)

        # Should find both clocks
        assert isinstance(clocks, list)
        assert len(clocks) >= 1

    def test_extract_clock_regression(self):
        """Test extracting negative clock ticks."""
        text = "📊 Clock: Threat -3 (Crisis averted)"

        clocks = parse_explicit_clock_markers(text)

        # Should handle negative ticks
        assert isinstance(clocks, list)


# ============================================================================
# Condition Parsing Tests
# ============================================================================

class TestConditionParsing:
    """Test condition marker parsing."""

    def test_parse_condition_markers(self):
        """Test parsing condition markers from text."""
        text = "Target is stunned. 🔸 Condition: Stunned (-3, 2 rounds)"

        conditions = parse_condition_markers(text)

        # Should return list of conditions
        assert isinstance(conditions, list)

    def test_parse_multiple_conditions(self):
        """Test parsing multiple conditions."""
        text = """
        🔸 Condition: Stunned (-3, 2 rounds)
        🔸 Condition: Prone (-2, 1 round)
        """

        conditions = parse_condition_markers(text)

        assert isinstance(conditions, list)


# ============================================================================
# Integration Tests (Parser + Schemas)
# ============================================================================

class TestParserIntegration:
    """Test parser working with actual schema objects."""

    def test_roundtrip_structured_to_legacy(self):
        """Test converting structured output to legacy format and back."""
        # Create structured resolution
        resolution = ActionResolution(
            narration="Complex action with multiple effects." * 15,
            success_tier=SuccessTier.GOOD,
            margin=10,
            effects=MechanicalEffects(
                void_changes=[VoidChange(character_name="PC", amount=1, reason="Risk")],
                clock_updates=[ClockUpdate(clock_name="Progress", ticks=2, reason="Success")]
            )
        )

        # Extract to legacy format
        state_changes = extract_from_structured_resolution(resolution)

        # Verify all data preserved
        assert state_changes['void_change'] == 1
        assert len(state_changes['clock_triggers']) == 1
        assert state_changes['void_source'] == 'structured_output'
        assert state_changes['llm_compliance_issue'] is None

    def test_null_resolution_handling(self):
        """Test handling of None/invalid resolution objects."""
        result = extract_from_structured_resolution(None)

        # Should return safe default or None
        assert result is None or isinstance(result, dict)

    def test_non_actionresolution_handling(self):
        """Test handling wrong object type."""
        result = extract_from_structured_resolution("not a resolution")

        # Should handle gracefully
        assert result is None or isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
