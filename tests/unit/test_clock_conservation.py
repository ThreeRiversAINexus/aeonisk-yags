"""
Tests for clock conservation: clocks must bind, not churn.

Corpus v2 (2026-07-04): median 9 clock spawns and 14 removals per
10-round session - clocks were disposable set dressing. Two leaks:
unbounded spawning, and story_advancement wiping ALL clocks by default
(a nearly-full doom clock could be amnestied by pivoting scenes).

Conservation contract (LLM proposes, code enforces, both logged):
- concurrent cap: spawns beyond max_active_clocks are rejected (None)
- spawn budget: max spawns per round (rounds >= 1; session setup exempt)
- story advancement: terminal clocks and high-progress clocks
  (>= persist fraction) auto-persist through pivots
- replacing an existing clock by name is an update, not a spawn
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.mechanics import (
    MechanicsEngine,
    partition_story_advancement_clocks,
)


@pytest.fixture
def engine():
    return MechanicsEngine()


def spawn(engine, name, maximum=6, **kw):
    return engine.create_scene_clock(name, maximum, f"desc {name}", **kw)


class TestSpawnCap:

    def test_cap_rejects_beyond_max_active(self, engine):
        for i in range(engine.max_active_clocks):
            assert spawn(engine, f"Clock {i}") is not None
        rejected = spawn(engine, "One Too Many")
        assert rejected is None
        assert "One Too Many" not in engine.scene_clocks

    def test_replacing_existing_name_allowed_at_cap(self, engine):
        for i in range(engine.max_active_clocks):
            spawn(engine, f"Clock {i}")
        replacement = spawn(engine, "Clock 0", maximum=8)
        assert replacement is not None
        assert engine.scene_clocks["Clock 0"].maximum == 8

    def test_room_after_removal(self, engine):
        for i in range(engine.max_active_clocks):
            spawn(engine, f"Clock {i}")
        del engine.scene_clocks["Clock 0"]
        assert spawn(engine, "Fresh Clock") is not None


class TestSpawnBudget:

    def test_budget_enforced_within_round(self, engine):
        engine.current_round = 3
        for i in range(engine.max_clock_spawns_per_round):
            assert spawn(engine, f"R3 Clock {i}") is not None
        assert spawn(engine, "R3 Over Budget") is None

    def test_budget_resets_next_round(self, engine):
        engine.current_round = 3
        for i in range(engine.max_clock_spawns_per_round):
            spawn(engine, f"R3 Clock {i}")
        engine.current_round = 4
        assert spawn(engine, "R4 Clock") is not None

    def test_session_setup_exempt(self, engine):
        """Round 0 = starting_clocks loading; budget must not bite."""
        engine.current_round = 0
        for i in range(engine.max_clock_spawns_per_round + 2):
            assert spawn(engine, f"Setup Clock {i}") is not None


class TestStoryAdvancementPartition:

    def _clocks(self, engine):
        low = spawn(engine, "Low Progress", maximum=8)
        low.current = 2
        high = spawn(engine, "Nearly Done", maximum=8)
        high.current = 6
        terminal = spawn(engine, "Doom", maximum=8, is_terminal=True)
        terminal.current = 1
        return engine.scene_clocks

    def test_high_progress_auto_persists(self, engine):
        clocks = self._clocks(engine)
        to_remove, auto_kept = partition_story_advancement_clocks(
            clocks, keep_clocks=[])
        assert "Nearly Done" in auto_kept
        assert "Nearly Done" not in to_remove

    def test_terminal_always_persists(self, engine):
        clocks = self._clocks(engine)
        to_remove, auto_kept = partition_story_advancement_clocks(
            clocks, keep_clocks=[])
        assert "Doom" in auto_kept
        assert "Doom" not in to_remove

    def test_low_progress_removable(self, engine):
        clocks = self._clocks(engine)
        to_remove, _ = partition_story_advancement_clocks(
            clocks, keep_clocks=[])
        assert "Low Progress" in to_remove

    def test_dm_keep_list_respected(self, engine):
        clocks = self._clocks(engine)
        to_remove, auto_kept = partition_story_advancement_clocks(
            clocks, keep_clocks=["Low Progress"])
        assert "Low Progress" not in to_remove
        assert "Low Progress" not in auto_kept  # DM-kept, not auto-kept

    def test_threshold_boundary(self, engine):
        clock = spawn(engine, "Exactly At Threshold", maximum=8)
        clock.current = 6  # 0.75 exactly
        to_remove, auto_kept = partition_story_advancement_clocks(
            engine.scene_clocks, keep_clocks=[], persist_fraction=0.75)
        assert "Exactly At Threshold" in auto_kept
