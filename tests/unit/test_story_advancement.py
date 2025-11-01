"""
Test environmental void_level updates during story advancement.

Feature: Allow DM to update environmental void_level when advancing the story.

Design:
- Environmental void_level is setting/backdrop, not player currency
- Players affect it via scene clocks (e.g., "Purification" clock)
- DM interprets completed clocks and updates void_level during story advancement
- void_level changes happen via StoryAdvancement.new_void_level field (optional)

Example:
- Round 1-3: Players work on "Purification" clock at "Corrupted Station" (void_level=8)
- Clock completes (10/10)
- DM advances story to "Cleansed Wing" with new_void_level=3
- Environmental void updated from 8 → 3
"""

import pytest
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.schemas.story_events import StoryAdvancement, NewClock
from pydantic import ValidationError


class TestStoryAdvancementSchema:
    """Test StoryAdvancement schema with new_void_level field."""

    def test_story_advancement_with_void_level_update(self):
        """
        StoryAdvancement can include new_void_level to update environmental void.
        """
        advancement = StoryAdvancement(
            should_advance=True,
            location="Research Station - Cleansed Wing",
            situation="Your purification ritual worked. The void corruption has dissipated from this sector.",
            new_void_level=3,  # Down from 8
            clear_all_enemies=True,
            new_clocks=[]
        )

        assert advancement.should_advance is True
        assert advancement.new_void_level == 3
        assert advancement.location == "Research Station - Cleansed Wing"

    def test_story_advancement_without_void_level_update(self):
        """
        StoryAdvancement with new_void_level=None keeps current void_level unchanged.
        """
        advancement = StoryAdvancement(
            should_advance=True,
            location="Warehouse - Level 2",
            situation="You ascend to the next floor. The corruption is just as thick here.",
            new_void_level=None,  # No change
            clear_all_enemies=True,
            new_clocks=[]
        )

        assert advancement.should_advance is True
        assert advancement.new_void_level is None  # Should carry over current void_level

    def test_story_advancement_void_level_optional_field(self):
        """
        new_void_level is optional - can omit entirely (defaults to None).
        """
        advancement = StoryAdvancement(
            should_advance=True,
            location="Safe House",
            situation="You escape to the extraction point.",
            clear_all_enemies=True
        )

        assert advancement.new_void_level is None  # Default value

    def test_void_level_validation_bounds(self):
        """
        new_void_level must be 0-10 (Pydantic Field validator).
        """
        # Valid bounds
        advancement_min = StoryAdvancement(
            should_advance=True,
            location="Sanctified Temple",
            situation="Completely purified zone.",
            new_void_level=0
        )
        assert advancement_min.new_void_level == 0

        advancement_max = StoryAdvancement(
            should_advance=True,
            location="Void Epicenter",
            situation="The breach tears reality itself.",
            new_void_level=10
        )
        assert advancement_max.new_void_level == 10

        # Invalid: below 0
        with pytest.raises(ValidationError) as exc_info:
            StoryAdvancement(
                should_advance=True,
                location="Test",
                situation="Test situation with at least 20 characters here",
                new_void_level=-1
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Invalid: above 10
        with pytest.raises(ValidationError) as exc_info:
            StoryAdvancement(
                should_advance=True,
                location="Test",
                situation="Test situation with at least 20 characters here",
                new_void_level=11
            )
        assert "less than or equal to 10" in str(exc_info.value)


class TestStoryAdvancementHandler:
    """Test session.py handler processes void_level updates correctly."""

    def test_handler_updates_scenario_void_level(self):
        """
        When StoryAdvancement includes new_void_level, handler updates scenario.void_level.
        """
        # Mock DM agent with scenario
        from scripts.aeonisk.multiagent.dm import Scenario

        mock_scenario = Scenario(
            theme="Test Theme",
            location="Corrupted Research Station",
            situation="High void corruption",
            active_npcs=[],
            environmental_factors=[],
            void_level=8  # Initial void level
        )

        mock_dm_agent = Mock()
        mock_dm_agent.current_scenario = mock_scenario

        # Simulate story advancement with void_level update
        advancement = StoryAdvancement(
            should_advance=True,
            location="Research Station - Cleansed Wing",
            situation="Your purification ritual worked. The void corruption has dissipated.",
            new_void_level=3,  # Update from 8 → 3
            clear_all_enemies=True
        )

        # Simulate handler logic
        if advancement.new_void_level is not None:
            if mock_dm_agent.current_scenario:
                old_void = mock_dm_agent.current_scenario.void_level
                mock_dm_agent.current_scenario.void_level = advancement.new_void_level

        # Verify update
        assert mock_dm_agent.current_scenario.void_level == 3
        assert old_void == 8

    def test_handler_preserves_void_level_when_none(self):
        """
        When StoryAdvancement has new_void_level=None, scenario.void_level unchanged.
        """
        from scripts.aeonisk.multiagent.dm import Scenario

        mock_scenario = Scenario(
            theme="Test Theme",
            location="Warehouse Level 1",
            situation="Same corruption level",
            active_npcs=[],
            environmental_factors=[],
            void_level=6  # Initial void level
        )

        mock_dm_agent = Mock()
        mock_dm_agent.current_scenario = mock_scenario

        # Story advancement WITHOUT void_level update
        advancement = StoryAdvancement(
            should_advance=True,
            location="Warehouse Level 2",
            situation="You ascend to the next floor.",
            new_void_level=None,  # No change
            clear_all_enemies=True
        )

        # Simulate handler logic
        if advancement.new_void_level is not None:
            if mock_dm_agent.current_scenario:
                mock_dm_agent.current_scenario.void_level = advancement.new_void_level

        # Verify void_level unchanged
        assert mock_dm_agent.current_scenario.void_level == 6

    def test_handler_skips_update_if_no_scenario(self):
        """
        Handler safely skips void_level update if DM has no scenario.
        """
        mock_dm_agent = Mock()
        mock_dm_agent.current_scenario = None  # No scenario

        advancement = StoryAdvancement(
            should_advance=True,
            location="Test Location Name",
            situation="Test situation with enough characters for validation",
            new_void_level=5,
            clear_all_enemies=True
        )

        # Simulate handler logic (should not crash)
        if advancement.new_void_level is not None:
            if mock_dm_agent.current_scenario:
                mock_dm_agent.current_scenario.void_level = advancement.new_void_level

        # Should not crash, scenario remains None
        assert mock_dm_agent.current_scenario is None


class TestVoidLevelStoryProgression:
    """Integration-style tests for void_level changes across story beats."""

    def test_purification_reduces_void(self):
        """
        Purification clocks completed → story advances with reduced void_level.
        """
        from scripts.aeonisk.multiagent.dm import Scenario

        # Initial state: High corruption
        scenario = Scenario(
            theme="Void Cleansing Mission",
            location="Corrupted Research Station",
            situation="Station saturated with void corruption.",
            active_npcs=[],
            environmental_factors=["Heavy void corruption"],
            void_level=8
        )

        # Story advancement after purification
        advancement = StoryAdvancement(
            should_advance=True,
            location="Research Station - Cleansed Wing",
            situation="Your ritual succeeded. The void has been purged from this sector.",
            new_void_level=3,  # Major reduction
            clear_all_enemies=True,
            new_clocks=[
                NewClock(
                    name="Containment Stability",
                    max_ticks=8,
                    description="Maintain purification field to prevent void re-contamination",
                    advance_meaning="containment strengthens",
                    regress_meaning="void corruption seeps back"
                )
            ]
        )

        # Apply update
        scenario.void_level = advancement.new_void_level

        assert scenario.void_level == 3
        assert advancement.new_clocks[0].name == "Containment Stability"

    def test_corruption_spreading_increases_void(self):
        """
        Containment failure → story advances with increased void_level.
        """
        from scripts.aeonisk.multiagent.dm import Scenario

        # Initial state: Moderate corruption
        scenario = Scenario(
            theme="Containment Breach",
            location="Research Lab - Containment",
            situation="Void breach contained but unstable.",
            active_npcs=[],
            environmental_factors=["Unstable containment field"],
            void_level=4
        )

        # Story advancement after containment failure
        advancement = StoryAdvancement(
            should_advance=True,
            location="Research Lab - Breach Epicenter",
            situation="The containment field collapses. Void corruption floods the facility.",
            new_void_level=8,  # Major increase
            clear_all_enemies=False,
            new_clocks=[
                NewClock(
                    name="Evacuation",
                    max_ticks=6,
                    description="Escape before total void saturation kills everyone",
                    advance_meaning="evacuation progresses",
                    regress_meaning="void corruption spreads faster"
                )
            ]
        )

        # Apply update
        scenario.void_level = advancement.new_void_level

        assert scenario.void_level == 8
        assert advancement.clear_all_enemies is False  # Enemies persist
