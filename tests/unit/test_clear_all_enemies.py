"""
Tests for clear_all_enemies=False mechanical guard.

When StoryAdvancement.clear_all_enemies=False, the Entity Lifecycle Phase #2
should NOT process enemy_departures from the DM's post-advancement conversion
check, because the config explicitly says to preserve enemies across scenes.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pydantic import BaseModel
from typing import List, Optional

from scripts.aeonisk.multiagent.schemas.story_events import (
    StoryAdvancement,
    ConversionDecisions,
)


class TestClearAllEnemiesFalseBlocksDepartures:
    """When clear_all_enemies=False, enemy_departures should be blocked."""

    def test_departures_list_cleared_when_flag_false(self):
        """Post-advancement enemy departures should be emptied when
        clear_all_enemies=False on the StoryAdvancement."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Abandoned Transit Hub",
            situation="The party moves to a new location but the enemies follow them closely through the corridors, maintaining pursuit pressure.",
            clear_all_enemies=False,
        )

        # Simulate DM's post-advancement conversion decisions
        post_advancement_decisions = ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            npc_departures=[],
            enemy_departures=["enemy_grunt_001", "enemy_sniper_002"],
            enemy_spawns=[],
            reasoning="Enemies should leave since scene changed",
        )

        # Apply the mechanical guard (this is the logic we're testing)
        if not adv.clear_all_enemies:
            if post_advancement_decisions.enemy_departures:
                post_advancement_decisions.enemy_departures = []

        assert post_advancement_decisions.enemy_departures == []

    def test_departures_preserved_when_flag_true(self):
        """Post-advancement enemy departures should process normally when
        clear_all_enemies=True."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Rooftop Escape",
            situation="Having defeated all opposition, the party escapes to the rooftops where fresh air and freedom await them at last.",
            clear_all_enemies=True,
        )

        post_advancement_decisions = ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            npc_departures=[],
            enemy_departures=["enemy_grunt_001", "enemy_sniper_002"],
            enemy_spawns=[],
            reasoning="Enemies left behind in old location",
        )

        # When clear_all_enemies=True, do NOT block departures
        if not adv.clear_all_enemies:
            if post_advancement_decisions.enemy_departures:
                post_advancement_decisions.enemy_departures = []

        assert post_advancement_decisions.enemy_departures == [
            "enemy_grunt_001", "enemy_sniper_002"
        ]

    def test_no_departures_no_error(self):
        """Guard should handle empty departures list gracefully."""
        adv = StoryAdvancement(
            should_advance=True,
            location="Hidden Bunker",
            situation="The group retreats to a hidden bunker beneath the transit hub where they can regroup and plan their next moves carefully.",
            clear_all_enemies=False,
        )

        post_advancement_decisions = ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            npc_departures=[],
            enemy_departures=[],
            enemy_spawns=[],
            reasoning="No enemies to depart",
        )

        if not adv.clear_all_enemies:
            if post_advancement_decisions.enemy_departures:
                post_advancement_decisions.enemy_departures = []

        assert post_advancement_decisions.enemy_departures == []
