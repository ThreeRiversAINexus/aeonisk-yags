"""
Unit tests for terminal-clock session endings (DM endings fix).

A "terminal clock" is the clock whose completion resolves the central dramatic
question and ends the session (e.g. "Final Verdict", "Breach Seal", "Escape").
Filling it must signal the engine to end the session with a declared outcome,
instead of the DM spawning yet another clock and running to the round cap.

Covers:
1. NewClock schema gains is_terminal_clock / terminal_outcome (safe defaults).
2. SceneClock + create_scene_clock carry the terminal flags.
3. Both fill paths (advance_clock and the queued-apply path used in synthesis)
   record a terminal_completion snapshot with the declared outcome.
4. A non-terminal clock filling does NOT trigger a terminal completion.
"""

import asyncio
from types import SimpleNamespace

import pytest

from aeonisk.multiagent.mechanics import MechanicsEngine, SceneClock
from aeonisk.multiagent.schemas.story_events import NewClock
from aeonisk.multiagent.session import SelfPlayingSession


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestNewClockTerminalFields:
    def test_defaults_are_non_terminal(self):
        clock = NewClock(
            name="Evidence Trail",
            max_ticks=6,
            description="Collect enough evidence to prosecute",
            advance_meaning="more evidence found",
            regress_meaning="evidence destroyed",
        )
        assert clock.is_terminal_clock is False
        # default outcome is a valid literal even when not terminal
        assert clock.terminal_outcome == "victory"

    def test_accepts_terminal_fields(self):
        clock = NewClock(
            name="Final Verdict",
            max_ticks=6,
            description="The tribunal reaches its binding decision",
            advance_meaning="the tribunal nears a ruling",
            regress_meaning="deliberation stalls",
            filled_consequence="The verdict is delivered and the tribunal disperses",
            is_terminal_clock=True,
            terminal_outcome="draw",
        )
        assert clock.is_terminal_clock is True
        assert clock.terminal_outcome == "draw"

    def test_rejects_invalid_outcome(self):
        with pytest.raises(Exception):
            NewClock(
                name="Final Verdict",
                max_ticks=6,
                description="The tribunal reaches its binding decision",
                advance_meaning="the tribunal nears a ruling",
                regress_meaning="deliberation stalls",
                is_terminal_clock=True,
                terminal_outcome="banana",
            )


# ---------------------------------------------------------------------------
# Engine: clock construction
# ---------------------------------------------------------------------------

class TestCreateSceneClockTerminal:
    def test_scene_clock_has_terminal_fields(self):
        clock = SceneClock(name="Breach Seal", maximum=6)
        assert clock.is_terminal is False
        assert clock.terminal_outcome == "victory"

    def test_create_scene_clock_propagates_terminal(self):
        engine = MechanicsEngine(jsonl_logger=None)
        clock = engine.create_scene_clock(
            "Final Verdict",
            maximum=4,
            description="Tribunal reaches a binding decision",
            filled_consequence="The verdict is delivered",
            is_terminal=True,
            terminal_outcome="draw",
        )
        assert clock.is_terminal is True
        assert clock.terminal_outcome == "draw"

    def test_create_scene_clock_defaults_non_terminal(self):
        engine = MechanicsEngine(jsonl_logger=None)
        clock = engine.create_scene_clock("Patrol Sweep", maximum=4)
        assert clock.is_terminal is False


# ---------------------------------------------------------------------------
# Engine: completion signalling
# ---------------------------------------------------------------------------

class TestTerminalCompletionSignal:
    def test_engine_starts_with_no_terminal_completion(self):
        engine = MechanicsEngine(jsonl_logger=None)
        assert engine.terminal_completion is None

    def test_advance_clock_records_terminal_completion(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            "Final Verdict",
            maximum=3,
            filled_consequence="The verdict is delivered",
            is_terminal=True,
            terminal_outcome="draw",
        )
        engine.advance_clock("Final Verdict", ticks=3, reason="tribunal rules")

        assert engine.terminal_completion is not None
        assert engine.terminal_completion["clock_name"] == "Final Verdict"
        assert engine.terminal_completion["outcome"] == "draw"
        assert "verdict" in engine.terminal_completion["filled_consequence"].lower()

    def test_queued_apply_records_terminal_completion(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            "Breach Seal",
            maximum=4,
            filled_consequence="The breach is sealed and the dock holds",
            is_terminal=True,
            terminal_outcome="victory",
        )
        engine.queue_clock_update("Breach Seal", 4, "team welds the seal shut")
        engine.apply_queued_clock_updates()

        assert engine.terminal_completion is not None
        assert engine.terminal_completion["clock_name"] == "Breach Seal"
        assert engine.terminal_completion["outcome"] == "victory"

    def test_terminal_clock_does_not_regress(self):
        """Regression: a live run showed the DM climbing a terminal clock to 5/8 then
        pushing it back to 3/8. Terminal clocks must advance or hold, never retreat."""
        engine = MechanicsEngine(jsonl_logger=None)
        clock = engine.create_scene_clock(
            "The New Settlement", maximum=8, is_terminal=True, terminal_outcome="victory",
        )
        engine.advance_clock("The New Settlement", ticks=5, reason="progress")
        assert clock.current == 5

        clock.regress(2)  # DM tries to walk it back
        assert clock.current == 5  # held, did not retreat

    def test_non_terminal_clock_still_regresses(self):
        engine = MechanicsEngine(jsonl_logger=None)
        clock = engine.create_scene_clock("Tension", maximum=8)
        engine.advance_clock("Tension", ticks=5, reason="progress")
        clock.regress(2)
        assert clock.current == 3  # ordinary clocks retreat normally

    def test_non_terminal_fill_does_not_signal(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            "Reinforcements",
            maximum=3,
            filled_consequence="More enforcers arrive",
        )
        engine.advance_clock("Reinforcements", ticks=3, reason="alarm raised")

        assert engine.terminal_completion is None

    def test_first_terminal_completion_wins(self):
        """If two terminal clocks fill, the first recorded one is kept (one ending)."""
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock(
            "Escape", maximum=2, is_terminal=True, terminal_outcome="victory",
            filled_consequence="The team escapes",
        )
        engine.create_scene_clock(
            "Capture", maximum=2, is_terminal=True, terminal_outcome="defeat",
            filled_consequence="The team is captured",
        )
        engine.advance_clock("Escape", ticks=2, reason="they slip the cordon")
        engine.advance_clock("Capture", ticks=2, reason="late blockade")

        assert engine.terminal_completion["clock_name"] == "Escape"
        assert engine.terminal_completion["outcome"] == "victory"


# ---------------------------------------------------------------------------
# Session: ending + end-state snapshot
# ---------------------------------------------------------------------------

def _bare_session(mechanics, agents=None):
    """Construct a SelfPlayingSession without its heavy __init__ for unit testing."""
    sess = object.__new__(SelfPlayingSession)
    sess._session_end_status = None
    sess._end_state_snapshot = None
    sess._last_dm_narration = ""
    sess.agents = agents or []
    sess.shared_state = SimpleNamespace(mechanics_engine=mechanics)
    return sess


class TestSessionEndsOnTerminalClock:
    def test_ends_with_terminal_outcome(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.current_round = 5
        engine.create_scene_clock(
            "Final Verdict", maximum=3, filled_consequence="The verdict is delivered",
            is_terminal=True, terminal_outcome="draw",
        )
        engine.advance_clock("Final Verdict", ticks=3, reason="tribunal rules")

        sess = _bare_session(engine)
        ended = asyncio.run(sess._check_end_conditions())

        assert ended is True
        assert sess._session_end_status == "draw"

    def test_continues_without_terminal_completion(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.create_scene_clock("Reinforcements", maximum=3)
        engine.advance_clock("Reinforcements", ticks=3, reason="alarm")

        sess = _bare_session(engine)
        ended = asyncio.run(sess._check_end_conditions())

        assert ended is False
        assert sess._session_end_status is None
        assert sess._end_state_snapshot is None

    def test_snapshot_emitted_even_when_dm_also_declared_end(self):
        """Regression: a live run showed the DM declaring session_end itself the
        moment a terminal clock filled. The snapshot must still be built -- gating it
        on 'DM hasn't ended yet' silently dropped the resolve-then-leap hook."""
        engine = MechanicsEngine(jsonl_logger=None)
        engine.current_round = 3
        engine.create_scene_clock(
            "Final Verdict", maximum=4, filled_consequence="The verdict is read",
            is_terminal=True, terminal_outcome="draw",
        )
        engine.advance_clock("Final Verdict", ticks=4, reason="judges rule")

        sess = _bare_session(engine)
        sess._session_end_status = "draw"  # DM already declared it this round

        ended = asyncio.run(sess._check_end_conditions())

        assert ended is True
        assert sess._end_state_snapshot is not None
        assert sess._end_state_snapshot["resolved_by_clock"] == "Final Verdict"
        assert sess._end_state_snapshot["outcome"] == "draw"

    def test_snapshot_on_dm_declaration_without_terminal_fill(self):
        """Regression: the DM declared DRAW with the terminal clock at 7/8 (one tick
        short). No terminal_completion was set, so terminal-only gating produced no
        snapshot. The snapshot must still fire on a DM-declared ending."""
        engine = MechanicsEngine(jsonl_logger=None)
        engine.current_round = 5
        engine.create_scene_clock(
            "The New Settlement", maximum=8, is_terminal=True, terminal_outcome="victory",
        )
        engine.advance_clock("The New Settlement", ticks=7, reason="near resolution")

        sess = _bare_session(engine)
        sess._session_end_status = "draw"  # DM declared it; clock never filled

        ended = asyncio.run(sess._check_end_conditions())

        assert ended is True
        assert sess._end_state_snapshot is not None
        assert sess._end_state_snapshot["ended_by"] == "dm_declaration"
        assert sess._end_state_snapshot["outcome"] == "draw"
        # attributed to the in-play terminal clock even though it didn't fill
        assert sess._end_state_snapshot["resolved_by_clock"] == "The New Settlement"

    def test_snapshot_captures_resolution_and_party(self):
        engine = MechanicsEngine(jsonl_logger=None)
        engine.current_round = 7
        engine.scene_void_level = 4
        terminal = {
            "clock_name": "Breach Seal",
            "outcome": "victory",
            "filled_consequence": "The breach is sealed and the dock holds",
            "reason": "team welds it shut",
            "round": 7,
        }
        agents = [
            SimpleNamespace(character_state=SimpleNamespace(
                name="Vessel Sera Karsel", faction="Echo", is_defeated=False, void_score=3)),
        ]
        sess = _bare_session(engine, agents=agents)
        snap = sess._build_end_state_snapshot(engine, terminal)

        assert snap["outcome"] == "victory"
        assert snap["resolved_by_clock"] == "Breach Seal"
        assert "sealed" in snap["resolution"].lower()
        assert snap["scene_void_level"] == 4
        assert snap["party"][0]["name"] == "Vessel Sera Karsel"
        assert "state_summary" in snap
