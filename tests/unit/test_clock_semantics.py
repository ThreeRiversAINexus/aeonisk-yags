"""
Test clock semantic fields (advance_meaning, regress_meaning, filled_consequence).

This test verifies that:
1. NewClock schema includes all semantic fields
2. SceneClock dataclass includes all semantic fields
3. Field names are consistent across schemas and runtime
4. Clocks created from configs preserve semantic information
"""

import pytest
from scripts.aeonisk.multiagent.schemas.story_events import NewClock
from scripts.aeonisk.multiagent.mechanics import SceneClock, MechanicsEngine


class TestClockSemantics:
    """Test clock semantic field consistency."""

    def test_new_clock_schema_has_semantic_fields(self):
        """NewClock schema should include all three semantic fields."""
        clock = NewClock(
            name="Test Clock",
            max_ticks=6,
            description="Test description",
            advance_meaning="progress made",
            regress_meaning="setback occurs",
            filled_consequence="goal achieved"
        )

        assert clock.advance_meaning == "progress made"
        assert clock.regress_meaning == "setback occurs"
        assert clock.filled_consequence == "goal achieved"

    def test_new_clock_filled_consequence_optional(self):
        """filled_consequence should be optional with empty string default."""
        clock = NewClock(
            name="Test Clock",
            max_ticks=6,
            description="Test description",
            advance_meaning="progress made",
            regress_meaning="setback occurs"
        )

        assert clock.filled_consequence == ""

    def test_scene_clock_has_semantic_fields(self):
        """SceneClock dataclass should have all semantic fields."""
        clock = SceneClock(
            name="Investigation",
            maximum=8,
            description="Gather evidence",
            advance_meaning="more evidence found",
            regress_meaning="evidence destroyed",
            filled_consequence="Case ready for prosecution"
        )

        assert clock.advance_meaning == "more evidence found"
        assert clock.regress_meaning == "evidence destroyed"
        assert clock.filled_consequence == "Case ready for prosecution"

    def test_mechanics_engine_creates_clock_with_semantics(self):
        """MechanicsEngine.create_scene_clock should accept semantic parameters."""
        mechanics = MechanicsEngine()

        clock = mechanics.create_scene_clock(
            name="Security Alert",
            maximum=6,
            description="Corporate hunters closing in",
            advance_meaning="hunters get closer",
            regress_meaning="team evades pursuit",
            filled_consequence="Hunter team arrives"
        )

        assert clock.advance_meaning == "hunters get closer"
        assert clock.regress_meaning == "team evades pursuit"
        assert clock.filled_consequence == "Hunter team arrives"

    def test_field_name_consistency(self):
        """Field names should match between NewClock and SceneClock."""
        # NewClock uses these field names
        new_clock = NewClock(
            name="Test Clock",
            max_ticks=6,
            description="Test clock description",
            advance_meaning="advance progress",
            regress_meaning="regress setback",
            filled_consequence="filled goal"
        )

        # SceneClock should use the same field names
        scene_clock = SceneClock(
            name="Test Clock",
            maximum=6,
            description="Test clock description",
            advance_meaning="advance progress",
            regress_meaning="regress setback",
            filled_consequence="filled goal"
        )

        # Verify same field names work for both
        assert new_clock.advance_meaning == scene_clock.advance_meaning
        assert new_clock.regress_meaning == scene_clock.regress_meaning
        assert new_clock.filled_consequence == scene_clock.filled_consequence

    def test_clock_semantics_preserved_through_mechanics(self):
        """Semantics should be preserved when creating clocks via mechanics engine."""
        mechanics = MechanicsEngine()

        # Create clock with full semantics
        original = mechanics.create_scene_clock(
            name="Evacuation Progress",
            maximum=8,
            description="Civilians escaping danger zone",
            advance_meaning="civilians evacuated",
            regress_meaning="evacuation blocked",
            filled_consequence="All civilians safe, transport arrives"
        )

        # Retrieve clock from mechanics
        retrieved = mechanics.scene_clocks["Evacuation Progress"]

        # Verify semantics preserved
        assert retrieved.advance_meaning == "civilians evacuated"
        assert retrieved.regress_meaning == "evacuation blocked"
        assert retrieved.filled_consequence == "All civilians safe, transport arrives"
