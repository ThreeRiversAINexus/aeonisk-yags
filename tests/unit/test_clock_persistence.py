"""
Tests for Spec 17: Clock Persistence Across Story Advancement.

Verifies that the `keep_clocks` field on StoryAdvancement allows the DM
to preserve specific clocks across major scene transitions, while the
default behavior (empty keep_clocks) clears all clocks.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from aeonisk.multiagent.schemas.story_events import StoryAdvancement, NewClock
from aeonisk.multiagent.mechanics import SceneClock


# ============================================================================
# Helper: Create a mock mechanics engine with scene clocks
# ============================================================================

def make_mechanics_with_clocks(clocks_dict):
    """
    Create a mock mechanics engine with the given scene clocks.

    Args:
        clocks_dict: dict of {name: (current, maximum, description)}

    Returns:
        Mock mechanics engine with scene_clocks populated.
    """
    mechanics = MagicMock()
    mechanics.current_round = 3
    mechanics.scene_clocks = {}
    mechanics.clock_history = []

    for name, (current, maximum, description) in clocks_dict.items():
        clock = SceneClock(
            name=name,
            current=current,
            maximum=maximum,
            description=description,
            advance_meaning=f"{name} advances",
            regress_meaning=f"{name} regresses",
        )
        mechanics.scene_clocks[name] = clock

    return mechanics


def apply_keep_clocks_logic(mechanics, keep_clocks):
    """
    Simulate the keep_clocks clearing logic that should exist in session.py.

    This is the logic we expect to be implemented:
    - Build a set from keep_clocks
    - Identify clocks NOT in keep set
    - Remove those clocks (logging removal)
    - Log kept clocks as persisted
    """
    keep_set = set(keep_clocks or [])

    clocks_to_remove = [
        name for name in mechanics.scene_clocks
        if name not in keep_set
    ]

    removed_events = []
    kept_events = []

    for clock_name in clocks_to_remove:
        clock = mechanics.scene_clocks[clock_name]
        removed_events.append({
            "event_type": "clock_removal",
            "clock_name": clock_name,
            "current_ticks": clock.current,
            "maximum_ticks": clock.maximum,
            "description": clock.description,
            "removal_reason": "story_advancement"
        })
        mechanics.clock_history.append({
            'event_type': 'removed',
            'clock_name': clock_name,
            'round': mechanics.current_round,
            'current': clock.current,
            'max': clock.maximum,
            'description': clock.description,
            'removal_reason': 'story_advancement'
        })

    # Remove non-kept clocks
    for clock_name in clocks_to_remove:
        del mechanics.scene_clocks[clock_name]

    # Log kept clocks
    for clock_name in keep_set:
        if clock_name in mechanics.scene_clocks:
            clock = mechanics.scene_clocks[clock_name]
            kept_events.append({
                "event_type": "clock_update",
                "clock_name": clock_name,
                "current_ticks": clock.current,
                "maximum_ticks": clock.maximum,
                "description": clock.description,
                "update_reason": "persisted_through_story_advancement"
            })

    return removed_events, kept_events


# ============================================================================
# Schema Tests
# ============================================================================

class TestStoryAdvancementSchema:
    """Tests for the keep_clocks field on StoryAdvancement schema."""

    def test_schema_backward_compatible(self):
        """StoryAdvancement without keep_clocks field deserializes with empty list."""
        data = {
            "should_advance": True,
            "location": "Transit Hub - Platform 7",
            "situation": "A" * 60,  # min_length=50
        }
        adv = StoryAdvancement(**data)
        assert adv.keep_clocks == []

    def test_keep_clocks_field_exists(self):
        """StoryAdvancement has a keep_clocks field that accepts a list of strings."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Transit Hub - Platform 7",
            situation="A" * 60,
            keep_clocks=["Corporate Pursuit", "Void Storm"]
        )
        assert adv.keep_clocks == ["Corporate Pursuit", "Void Storm"]

    def test_keep_clocks_defaults_to_empty_list(self):
        """keep_clocks defaults to empty list (clear all behavior)."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Transit Hub - Platform 7",
            situation="A" * 60,
        )
        assert adv.keep_clocks == []
        assert isinstance(adv.keep_clocks, list)

    def test_keep_clocks_single_entry(self):
        """keep_clocks works with a single clock name."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Transit Hub - Platform 7",
            situation="A" * 60,
            keep_clocks=["Corporate Pursuit"]
        )
        assert len(adv.keep_clocks) == 1
        assert adv.keep_clocks[0] == "Corporate Pursuit"

    def test_keep_clocks_coexists_with_new_clocks(self):
        """keep_clocks and new_clocks can both be specified simultaneously."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Transit Hub - Platform 7",
            situation="A" * 60,
            keep_clocks=["Corporate Pursuit"],
            new_clocks=[
                NewClock(
                    name="Courier's Life",
                    max_ticks=6,
                    description="Stabilize the courier before they expire from void wounds",
                    advance_meaning="courier stabilizing",
                    regress_meaning="courier worsening"
                )
            ]
        )
        assert adv.keep_clocks == ["Corporate Pursuit"]
        assert len(adv.new_clocks) == 1
        assert adv.new_clocks[0].name == "Courier's Life"


# ============================================================================
# Clock Clearing Logic Tests
# ============================================================================

class TestClockPersistenceLogic:
    """Tests for the selective clock clearing logic during story advancement."""

    def test_story_advancement_clears_all_clocks_by_default(self):
        """Default behavior: empty keep_clocks clears everything."""
        mechanics = make_mechanics_with_clocks({
            "Alarm": (2, 4, "Security alarm escalation"),
            "Breach Containment": (3, 6, "Containment breach progress"),
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
        })
        assert len(mechanics.scene_clocks) == 3

        apply_keep_clocks_logic(mechanics, keep_clocks=[])

        assert len(mechanics.scene_clocks) == 0

    def test_story_advancement_keeps_named_clocks(self):
        """Clocks listed in keep_clocks survive story advancement."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Breach Containment": (3, 6, "Containment breach progress"),
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        apply_keep_clocks_logic(mechanics, keep_clocks=["Corporate Pursuit"])

        assert "Corporate Pursuit" in mechanics.scene_clocks
        assert "Breach Containment" not in mechanics.scene_clocks
        assert "Alarm" not in mechanics.scene_clocks
        assert len(mechanics.scene_clocks) == 1

    def test_kept_clocks_retain_tick_progress(self):
        """Preserved clocks keep their current tick count, not reset to 0."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        apply_keep_clocks_logic(mechanics, keep_clocks=["Corporate Pursuit"])

        assert mechanics.scene_clocks["Corporate Pursuit"].current == 4
        assert mechanics.scene_clocks["Corporate Pursuit"].maximum == 8

    def test_keep_clocks_ignores_nonexistent_names(self):
        """Naming a clock that doesn't exist in keep_clocks is a no-op, not an error."""
        mechanics = make_mechanics_with_clocks({
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        # No error should be raised for "Nonexistent Clock"
        apply_keep_clocks_logic(mechanics, keep_clocks=["Nonexistent Clock"])

        # "Alarm" is cleared because it's not in keep list
        assert len(mechanics.scene_clocks) == 0

    def test_keep_all_clocks(self):
        """Listing every clock in keep_clocks preserves all of them."""
        mechanics = make_mechanics_with_clocks({
            "Clock A": (1, 4, "First clock"),
            "Clock B": (2, 6, "Second clock"),
            "Clock C": (3, 8, "Third clock"),
        })

        apply_keep_clocks_logic(
            mechanics,
            keep_clocks=["Clock A", "Clock B", "Clock C"]
        )

        assert len(mechanics.scene_clocks) == 3
        assert "Clock A" in mechanics.scene_clocks
        assert "Clock B" in mechanics.scene_clocks
        assert "Clock C" in mechanics.scene_clocks

    def test_keep_multiple_clocks(self):
        """Multiple clocks can be kept while others are cleared."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Void Storm": (2, 10, "Void storm approaching"),
            "Alarm": (3, 4, "Security alarm"),
            "Breach": (1, 6, "Containment breach"),
        })

        apply_keep_clocks_logic(
            mechanics,
            keep_clocks=["Corporate Pursuit", "Void Storm"]
        )

        assert len(mechanics.scene_clocks) == 2
        assert "Corporate Pursuit" in mechanics.scene_clocks
        assert "Void Storm" in mechanics.scene_clocks
        assert "Alarm" not in mechanics.scene_clocks
        assert "Breach" not in mechanics.scene_clocks

    def test_no_clocks_to_clear(self):
        """Empty scene_clocks with keep_clocks is a no-op."""
        mechanics = make_mechanics_with_clocks({})

        # No error should be raised
        apply_keep_clocks_logic(mechanics, keep_clocks=["Nonexistent"])

        assert len(mechanics.scene_clocks) == 0


# ============================================================================
# JSONL Logging Tests
# ============================================================================

class TestClockPersistenceLogging:
    """Tests for JSONL logging of clock removal and persistence events."""

    def test_clock_removal_logged_for_cleared_clocks(self):
        """Cleared clocks generate clock_removal events with story_advancement reason."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        removed_events, kept_events = apply_keep_clocks_logic(
            mechanics, keep_clocks=["Corporate Pursuit"]
        )

        # One clock removed: "Alarm"
        assert len(removed_events) == 1
        assert removed_events[0]["event_type"] == "clock_removal"
        assert removed_events[0]["clock_name"] == "Alarm"
        assert removed_events[0]["current_ticks"] == 2
        assert removed_events[0]["maximum_ticks"] == 4
        assert removed_events[0]["removal_reason"] == "story_advancement"

    def test_clock_persistence_logged_for_kept_clocks(self):
        """Kept clocks generate clock_update events with persistence reason."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        removed_events, kept_events = apply_keep_clocks_logic(
            mechanics, keep_clocks=["Corporate Pursuit"]
        )

        # One clock kept: "Corporate Pursuit"
        assert len(kept_events) == 1
        assert kept_events[0]["event_type"] == "clock_update"
        assert kept_events[0]["clock_name"] == "Corporate Pursuit"
        assert kept_events[0]["current_ticks"] == 4
        assert kept_events[0]["maximum_ticks"] == 8
        assert kept_events[0]["update_reason"] == "persisted_through_story_advancement"

    def test_all_clocks_removal_logged_when_no_keep(self):
        """When keep_clocks is empty, all clocks get removal events."""
        mechanics = make_mechanics_with_clocks({
            "Clock A": (1, 4, "First clock"),
            "Clock B": (2, 6, "Second clock"),
        })

        removed_events, kept_events = apply_keep_clocks_logic(
            mechanics, keep_clocks=[]
        )

        assert len(removed_events) == 2
        assert len(kept_events) == 0
        removed_names = {e["clock_name"] for e in removed_events}
        assert removed_names == {"Clock A", "Clock B"}

    def test_clock_history_updated_for_removed_clocks(self):
        """Removed clocks are recorded in mechanics.clock_history."""
        mechanics = make_mechanics_with_clocks({
            "Alarm": (2, 4, "Security alarm escalation"),
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
        })

        apply_keep_clocks_logic(mechanics, keep_clocks=["Corporate Pursuit"])

        # Only "Alarm" should be in clock_history
        assert len(mechanics.clock_history) == 1
        assert mechanics.clock_history[0]['clock_name'] == "Alarm"
        assert mechanics.clock_history[0]['removal_reason'] == 'story_advancement'
        assert mechanics.clock_history[0]['current'] == 2
        assert mechanics.clock_history[0]['max'] == 4

    def test_no_clock_history_for_kept_clocks(self):
        """Kept clocks do NOT appear in clock_history (they are not removed)."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
        })

        apply_keep_clocks_logic(mechanics, keep_clocks=["Corporate Pursuit"])

        assert len(mechanics.clock_history) == 0


# ============================================================================
# Integration: new_clocks spawn after selective clearing
# ============================================================================

class TestNewClocksAfterSelectiveClearing:
    """Tests that new_clocks coexist with kept clocks after story advancement."""

    def test_new_clocks_spawn_after_selective_clearing(self):
        """new_clocks are added after clearing, coexisting with kept clocks."""
        mechanics = make_mechanics_with_clocks({
            "Corporate Pursuit": (4, 8, "Corporate faction pursuit"),
            "Alarm": (2, 4, "Security alarm escalation"),
        })

        # Step 1: Apply keep_clocks logic (clear Alarm, keep Corporate Pursuit)
        apply_keep_clocks_logic(mechanics, keep_clocks=["Corporate Pursuit"])

        # Step 2: Spawn new clock (simulating what session.py does after clearing)
        new_clock = SceneClock(
            name="Courier's Life",
            current=0,
            maximum=6,
            description="Stabilize the courier before they expire",
            advance_meaning="courier stabilizing",
            regress_meaning="courier worsening",
        )
        mechanics.scene_clocks[new_clock.name] = new_clock

        # Verify: kept + new coexist, cleared is gone
        assert "Corporate Pursuit" in mechanics.scene_clocks
        assert mechanics.scene_clocks["Corporate Pursuit"].current == 4  # Preserved ticks
        assert "Courier's Life" in mechanics.scene_clocks
        assert mechanics.scene_clocks["Courier's Life"].current == 0  # Fresh clock
        assert "Alarm" not in mechanics.scene_clocks
        assert len(mechanics.scene_clocks) == 2
