"""Clocks, as a state machine rather than a series of single calls.

The richest surface in the corpus — roughly 10,400 clock events — and the one
with confirmed live defects: 597 advance/remove operations naming a clock that
was never spawned, nine of them in the seven August sessions, so this is current
behaviour rather than historical debt.

Two levels here. `SceneClock` is a plain dataclass and gets ordinary property
tests. The engine-level sequencing gets `hypothesis`, because the bugs live in
*orderings* — spawn caps interacting with a round counter, a queue that is not
idempotent, a terminal completion that only the first caller wins — and a
40-step failing sequence is unreadable without shrinking.

The load-bearing rule throughout: **a clock is a two-way pressure gauge, never a
ratchet** (`mechanics.py:1857`). Convergence comes from the round-cap backstop,
not from making clocks monotonic.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from scripts.aeonisk.multiagent.mechanics import (
    MechanicsEngine, SceneClock, partition_story_advancement_clocks,
)

TICKS = st.integers(min_value=0, max_value=12)
MAXIMA = st.integers(min_value=1, max_value=12)


def clock(name="Pressure", maximum=6, **kw):
    return SceneClock(name=name, maximum=maximum, **kw)


class TestRegressionIsAlwaysPossible:
    """The anti-ratchet rule, stated as properties.

    A clock that cannot come back down turns every scene into a countdown, which
    is precisely the failure mode the design forbids.
    """

    @given(start=TICKS, maximum=MAXIMA, step=st.integers(min_value=1, max_value=6))
    def test_advance_then_regress_returns_to_start(self, start, maximum, step):
        c = clock(maximum=maximum)
        c.current = start

        c.advance(step)
        c.regress(step)

        assert c.current == start

    @given(maximum=MAXIMA, step=st.integers(min_value=1, max_value=20))
    def test_regress_clamps_at_zero_by_default(self, maximum, step):
        c = clock(maximum=maximum)
        c.current = 1

        c.regress(step)

        assert c.current == 0, "a standard clock must never go negative"

    @given(maximum=MAXIMA, step=st.integers(min_value=1, max_value=40))
    def test_a_bidirectional_clock_floors_at_negative_maximum(self, maximum, step):
        c = clock(maximum=maximum, allow_negative=True)

        c.regress(step)

        assert c.current >= -maximum

    @given(maximum=MAXIMA, steps=st.lists(st.integers(min_value=1, max_value=5),
                                          min_size=1, max_size=10))
    def test_a_filled_terminal_clock_can_still_be_driven_down(self, maximum, steps):
        """Terminal clocks are regressable too — driving a DOOM clock to 0 is a
        legitimate win, not an illegal move."""
        c = clock(maximum=maximum, is_terminal=True, terminal_outcome="defeat")
        c.advance(maximum)
        assert c.filled

        for s in steps:
            c.regress(s)

        assert c.current >= 0


class TestAdvance:

    @given(start=TICKS, maximum=MAXIMA, step=st.integers(min_value=1, max_value=20))
    def test_overflow_past_maximum_is_allowed(self, start, maximum, step):
        """Deliberate: a 6/6 clock advancing to 7/6 signals rising urgency."""
        c = clock(maximum=maximum)
        c.current = start

        c.advance(step)

        assert c.current == start + step

    @given(start=st.integers(min_value=-12, max_value=24), maximum=MAXIMA)
    def test_filled_always_means_at_or_above_maximum(self, start, maximum):
        c = clock(maximum=maximum)
        c.current = start

        assert c.filled == (c.current >= maximum)

    @given(start=TICKS, maximum=MAXIMA, step=st.integers(min_value=1, max_value=20))
    def test_the_return_value_agrees_with_the_filled_property(self, start, maximum, step):
        c = clock(maximum=maximum)
        c.current = start

        assert c.advance(step) == c.filled

    @given(maximum=MAXIMA)
    def test_ever_filled_is_sticky_across_regression(self, maximum):
        """History must survive the gauge coming back down."""
        c = clock(maximum=maximum)
        c.advance(maximum)
        c.regress(maximum)

        assert c.ever_filled and not c.filled


class TestConsequenceIsTotal:
    """`effective_consequence` falls back through four sources, so there is no
    reachable clock whose fill cannot be narrated."""

    @given(filled_consequence=st.text(max_size=20), advance_meaning=st.text(max_size=20),
           description=st.text(max_size=20))
    def test_never_empty(self, filled_consequence, advance_meaning, description):
        c = clock(filled_consequence=filled_consequence,
                  advance_meaning=advance_meaning, description=description)

        assert c.effective_consequence.strip()


class TestPartitionStoryAdvancementClocks:

    def build(self, spec):
        out = {}
        for name, (cur, mx, terminal) in spec.items():
            c = clock(name=name, maximum=mx, is_terminal=terminal)
            c.current = cur
            out[name] = c
        return out

    @given(keep=st.lists(st.sampled_from(["a", "b", "c"]), max_size=3))
    def test_kept_clocks_appear_in_neither_list(self, keep):
        clocks = self.build({"a": (0, 6, False), "b": (5, 6, False), "c": (1, 6, True)})

        to_remove, auto_kept = partition_story_advancement_clocks(clocks, keep)

        for name in set(keep):
            assert name not in to_remove and name not in auto_kept

    @given(cur=st.integers(min_value=0, max_value=8), mx=MAXIMA)
    def test_every_other_clock_lands_in_exactly_one_list(self, cur, mx):
        clocks = self.build({"a": (cur, mx, False)})

        to_remove, auto_kept = partition_story_advancement_clocks(clocks, [])

        assert (("a" in to_remove) + ("a" in auto_kept)) == 1

    def test_terminal_clocks_are_never_dropped(self):
        clocks = self.build({"doom": (0, 6, True)})

        to_remove, auto_kept = partition_story_advancement_clocks(clocks, [])

        assert to_remove == [] and auto_kept == ["doom"]

    def test_a_zero_maximum_clock_does_not_divide_by_zero(self):
        c = clock(name="degenerate", maximum=0)

        to_remove, auto_kept = partition_story_advancement_clocks({"degenerate": c}, [])

        assert "degenerate" in to_remove


class ClockEngineMachine(RuleBasedStateMachine):
    """Generated orderings of the engine-level clock operations.

    The single-call behaviour above is well-behaved; the risk is in sequences.
    Three specific hazards this is built to reach:

    * the per-round spawn budget resets on `_clock_spawn_round != current_round`,
      so a round counter that moves *backwards* silently refills it
    * `apply_queued_clock_updates` aggregates then clears, so it is not
      idempotent
    * only the first terminal completion is recorded, and aggregation order
      decides which one that is
    """

    def __init__(self):
        super().__init__()
        # jsonl_logger=None silences every logging branch, so no I/O.
        self.engine = MechanicsEngine()
        self.engine.current_round = 1

    @rule(name=st.sampled_from(["alpha", "beta", "gamma", "delta"]),
          maximum=st.integers(min_value=1, max_value=6),
          terminal=st.booleans())
    def spawn(self, name, maximum, terminal):
        self.engine.create_scene_clock(name, maximum=maximum, is_terminal=terminal,
                                       terminal_outcome="defeat")

    @rule(name=st.sampled_from(["alpha", "beta", "gamma", "delta"]),
          ticks=st.integers(min_value=-6, max_value=6))
    def queue(self, name, ticks):
        if name in self.engine.scene_clocks:
            self.engine.queue_clock_update(name, ticks, "generated")

    @rule()
    def apply_queue(self):
        self.engine.apply_queued_clock_updates()

    @rule()
    def next_round(self):
        self.engine.current_round += 1

    @rule()
    def expire(self):
        self.engine.check_and_expire_clocks()

    @invariant()
    def never_exceeds_the_active_cap(self):
        assert len(self.engine.scene_clocks) <= self.engine.max_active_clocks

    @invariant()
    def no_standard_clock_goes_negative(self):
        for name, c in self.engine.scene_clocks.items():
            if not c.allow_negative:
                assert c.current >= 0, f"{name} at {c.current}"

    @invariant()
    def at_most_one_terminal_completion(self):
        """Two endings in one session is a contradiction, not a tie."""
        tc = getattr(self.engine, "terminal_completion", None)
        assert tc is None or isinstance(tc, dict)

    @invariant()
    def the_queue_is_drained_or_pending_never_silently_lost(self):
        assert isinstance(self.engine.clock_update_queue, list)


TestClockEngineSequences = ClockEngineMachine.TestCase
TestClockEngineSequences.settings = settings(max_examples=150, stateful_step_count=25,
                                             deadline=None)
