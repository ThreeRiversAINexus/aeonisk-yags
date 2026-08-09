"""Unit tests for the session-finalization guard.

Regression origin (session fa9d2891, 2026-08-09): two independent teardown
blocks each swept `mechanics.scene_clocks` emitting `clock_removal` and then
called `log_session_end()` —

  * `_check_session_end()` (the DM-declared-end path), and
  * `_end_session()`

Both ran, neither guarded. Five clocks produced **ten** `clock_removal` events
and **two** `session_end` events in one JSONL file. Any consumer that counts
clock lifecycles or splits a file on `session_end` double-counts.

The guard lets exactly one caller claim finalization per session.
"""

import pytest

from scripts.aeonisk.multiagent.session import SelfPlayingSession


def make_session():
    """A bare session object — the guard must not depend on any other state."""
    return SelfPlayingSession.__new__(SelfPlayingSession)


class TestSessionFinalizationGuard:

    def test_first_claim_succeeds(self):
        session = make_session()

        assert session._claim_session_finalization() is True

    def test_second_claim_is_refused(self):
        """The second teardown path must be told to stand down."""
        session = make_session()

        first = session._claim_session_finalization()
        second = session._claim_session_finalization()

        assert first is True
        assert second is False

    def test_repeated_claims_stay_refused(self):
        session = make_session()
        session._claim_session_finalization()

        assert [session._claim_session_finalization() for _ in range(3)] == [
            False, False, False,
        ]

    def test_sessions_are_independent(self):
        """One session finalizing must not suppress another's teardown."""
        a, b = make_session(), make_session()

        a._claim_session_finalization()

        assert b._claim_session_finalization() is True

    def test_works_without_prior_initialization(self):
        """Guard is read defensively: an object that never ran __init__ (or a
        session constructed before the attribute existed) must still claim."""
        session = make_session()
        assert not hasattr(session, '_session_finalized')

        assert session._claim_session_finalization() is True
        assert session._session_finalized is True
