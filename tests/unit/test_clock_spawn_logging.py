"""Every scene clock announces its own birth.

Regression origin (sessions fa9d2891 and a8ca2b7f, 2026-08-09): clocks the DM
created during scenario generation emitted no `clock_spawn` event at all. They
appeared in the log only via `clock_advancement` and `clock_removal`, so a
lifecycle reconstruction had them materializing from nothing — three per run,
both runs.

Cause: `clock_spawn` was logged by the *callers* that happened to remember
(the round-synthesis path in session.py), not by clock creation itself. The DM's
scenario-generation path called `create_scene_clock()` directly and logged
nothing.

Logging now lives in `create_scene_clock`, the single chokepoint every creation
path goes through.
"""

import pytest

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


class _Logger:
    def __init__(self):
        self.events = []

    def log_clock_spawn(self, clock_name, max_ticks, description,
                        round_num=None, current_ticks=0, advance_meaning=None,
                        regress_meaning=None, filled_consequence=None):
        self.events.append({
            "clock_name": clock_name,
            "max_ticks": max_ticks,
            "current_ticks": current_ticks,
            "description": description,
            "round_num": round_num,
        })


def make_engine():
    engine = MechanicsEngine()
    engine.jsonl_logger = _Logger()
    return engine


class TestCreateSceneClockLogsSpawn:

    def test_creation_emits_clock_spawn(self):
        engine = make_engine()

        engine.create_scene_clock("Coven Subdual", 6, "Progress toward arrest")

        assert [e["clock_name"] for e in engine.jsonl_logger.events] == ["Coven Subdual"]

    def test_spawn_carries_the_maximum(self):
        """max_ticks is the field name clock_spawn uses (clock_removal says
        maximum_ticks — they are different keys, do not conflate them)."""
        engine = make_engine()

        engine.create_scene_clock("Lattice Stability", 8, "desc")

        assert engine.jsonl_logger.events[0]["max_ticks"] == 8

    def test_every_clock_gets_exactly_one_spawn(self):
        engine = make_engine()

        for name in ("A", "B", "C"):
            engine.create_scene_clock(name, 6, "desc")

        assert len(engine.jsonl_logger.events) == 3
        assert [e["clock_name"] for e in engine.jsonl_logger.events] == ["A", "B", "C"]

    def test_no_logger_does_not_raise(self):
        engine = MechanicsEngine()
        engine.jsonl_logger = None

        engine.create_scene_clock("Silent", 6, "desc")

        assert "Silent" in engine.scene_clocks

    def test_spawn_records_the_current_round(self):
        engine = make_engine()
        engine.current_round = 3

        engine.create_scene_clock("Temptation's Whisper", 6, "desc")

        assert engine.jsonl_logger.events[0]["round_num"] == 3
