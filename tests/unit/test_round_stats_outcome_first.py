"""Round-summary statistics must be recorded by the outcome-first pipeline too.

Regression origin (session fa9d2891, 2026-08-09): every `round_summary` event
reported `actions_attempted: 0`, `success_count: 0`, `average_margin: 0.0`, for
rounds in which actions actually resolved with margins of -12, -18, +10, +2, -5.
`reconstruct_narrative.py` faithfully printed "Average margin: +0.0" — the
reader was fine, the producer was empty.

Cause: `track_action_resolution()` was only called from the legacy resolution
path in dm.py. With `outcome_first_narration` enabled — the recommended
baseline — resolution runs through the outcome pipeline instead, which emits
`action_adjudication` / `applied_outcome` and never touched the counters. That
session logged 8 adjudications and 1 action_resolution.

(`damage_taken_by_players` was correct at 20, because that tracker is called
from enemy_combat, a path that still ran.)
"""

import pytest

from scripts.aeonisk.multiagent.session import SelfPlayingSession
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


class _Outcome:
    """Stand-in for AppliedOutcome.

    The dice live under `roll_result` — AppliedOutcome has no top-level
    .margin or .success_tier. Reading those attributes returned nothing, so
    every action was scored margin 0 and, via the "assume success" fallback in
    _resolution_success, a success. The first live rerun showed
    attempted=2 success=2 avg_margin=0.0 for rounds whose rolls were real.
    """

    def __init__(self, tier, margin, success=None):
        roll = {}
        if tier is not None:
            roll['success_tier'] = tier.value if hasattr(tier, 'value') else tier
        if margin is not None:
            roll['margin'] = margin
        if success is not None:
            roll['success'] = success
        self.roll_result = roll


def make_session():
    session = SelfPlayingSession.__new__(SelfPlayingSession)
    session._round_stats = {
        'actions_attempted': 0, 'success_count': 0, 'total_margin': 0,
        'damage_dealt_by_players': 0, 'damage_taken_by_players': 0,
        'void_gained': 0, 'void_lost': 0, 'clocks_advanced': 0,
        'clocks_filled': 0,
    }
    return session


class TestTrackOutcomeStatistics:

    def test_counts_the_attempt(self):
        session = make_session()

        session.track_outcome_statistics(_Outcome(SuccessTier.FAILURE, -12))

        assert session._round_stats['actions_attempted'] == 1

    def test_accumulates_margin_including_negatives(self):
        """The observed session's margins were mostly negative; a summary that
        reports +0.0 for them is worse than no summary."""
        session = make_session()

        for margin in (-12, -18, 10, 2, -5):
            session.track_outcome_statistics(_Outcome(SuccessTier.FAILURE, margin))

        assert session._round_stats['actions_attempted'] == 5
        assert session._round_stats['total_margin'] == -23

    @pytest.mark.parametrize("tier", [
        SuccessTier.MARGINAL, SuccessTier.MODERATE, SuccessTier.GOOD,
        SuccessTier.EXCELLENT, SuccessTier.EXCEPTIONAL,
    ])
    def test_successful_tiers_count_as_success(self, tier):
        """MARGINAL counts: it still clears the DC (see _resolution_success)."""
        session = make_session()

        session.track_outcome_statistics(_Outcome(tier, 5))

        assert session._round_stats['success_count'] == 1

    @pytest.mark.parametrize("tier", [
        SuccessTier.CRITICAL_FAILURE, SuccessTier.FAILURE,
    ])
    def test_unsuccessful_tiers_do_not(self, tier):
        session = make_session()

        session.track_outcome_statistics(_Outcome(tier, -3))

        assert session._round_stats['success_count'] == 0
        assert session._round_stats['actions_attempted'] == 1

    def test_missing_margin_is_treated_as_zero(self):
        session = make_session()

        session.track_outcome_statistics(_Outcome(SuccessTier.FAILURE, None))

        assert session._round_stats['total_margin'] == 0
        assert session._round_stats['actions_attempted'] == 1

    def test_none_outcome_is_ignored(self):
        session = make_session()

        session.track_outcome_statistics(None)

        assert session._round_stats['actions_attempted'] == 0

    def test_outcome_without_a_roll_is_not_an_attempt(self):
        """Pure dialogue has an empty roll_result — no dice, no attempt."""
        session = make_session()

        class _NoRoll:
            roll_result = {}

        session.track_outcome_statistics(_NoRoll())

        assert session._round_stats['actions_attempted'] == 0

    def test_explicit_success_flag_wins(self):
        """roll_result carries `success` directly; prefer it over tier parsing."""
        session = make_session()

        session.track_outcome_statistics(
            _Outcome(SuccessTier.FAILURE, 5, success=True))

        assert session._round_stats['success_count'] == 1

    def test_reads_margin_from_roll_result(self):
        session = make_session()

        session.track_outcome_statistics(_Outcome(SuccessTier.MODERATE, 5))

        assert session._round_stats['total_margin'] == 5
