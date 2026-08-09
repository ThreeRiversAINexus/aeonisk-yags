"""Invariants for the defects that passed the gate in session fa9d2891.

That session exited 0 from `session_invariants.py` and clean from
`analyze_session.py --mode=errors`, while carrying a duplicated teardown, a
three-way disagreement about whether a PC was alive, 8 of 13 enforce rulings
silently dropped, and three clocks that were never born. Each of those is now a
checker.
"""

import pytest

from scripts.session_invariants import (
    ERROR, WARN, check, ids,
    inv_single_session_end,
    inv_snapshot_matches_oracle,
    inv_enforce_rulings_dropped,
    inv_clock_without_spawn,
)


def _ev(event_type, round_=1, **fields):
    e = {"event_type": event_type, "round": round_}
    e.update(fields)
    return e


class TestSingleSessionEnd:

    def test_one_is_fine(self):
        assert inv_single_session_end([_ev("session_end")], {}) == []

    def test_duplicate_is_an_error(self):
        """Two teardown paths each called log_session_end()."""
        violations = inv_single_session_end(
            [_ev("session_end"), _ev("session_end")], {})

        assert [v.severity for v in violations] == [ERROR]
        assert "2" in violations[0].message

    def test_missing_is_not_this_checker_s_problem(self):
        """An incomplete session is caught elsewhere; don't double-report."""
        assert inv_single_session_end([_ev("round_start")], {}) == []


class TestSnapshotMatchesOracle:

    def test_agreement_is_clean(self):
        events = [
            _ev("character_state", character_name="Nera", is_defeated=True,
                death_state="unconscious"),
            _ev("end_state_snapshot", data={"party": [
                {"name": "Nera", "is_defeated": True}]}),
        ]

        assert inv_snapshot_matches_oracle(events, {}) == []

    def test_snapshot_contradicting_the_oracle_is_an_error(self):
        """The observed case: character_state said defeated, snapshot said not."""
        events = [
            _ev("character_state", character_name="Nera", is_defeated=True,
                death_state="unconscious"),
            _ev("end_state_snapshot", data={"party": [
                {"name": "Nera", "is_defeated": False}]}),
        ]

        violations = inv_snapshot_matches_oracle(events, {})

        assert [v.severity for v in violations] == [ERROR]
        assert violations[0].entity == "Nera"

    def test_uses_the_last_character_state(self):
        """Early-round rows must not outvote the final one."""
        events = [
            _ev("character_state", round_=1, character_name="Nera", is_defeated=False),
            _ev("character_state", round_=4, character_name="Nera", is_defeated=True),
            _ev("end_state_snapshot", round_=4, data={"party": [
                {"name": "Nera", "is_defeated": True}]}),
        ]

        assert inv_snapshot_matches_oracle(events, {}) == []

    def test_no_snapshot_is_clean(self):
        assert inv_snapshot_matches_oracle([_ev("character_state")], {}) == []


class TestEnforceRulingsDropped:

    def test_all_applied_is_clean(self):
        events = [_ev("post_resolution_adjudication", data={
            "regime": "v1.1-law-LIVE",
            "applied": [{"character_name": "Nera", "applied": True}]})]

        assert inv_enforce_rulings_dropped(events, {}) == []

    def test_dropped_ruling_is_reported(self):
        """8 of 13 dropped in the observed session — every antagonist ruling."""
        events = [_ev("post_resolution_adjudication", data={
            "regime": "v1.1-law-LIVE",
            "applied": [
                {"character_name": "Nera", "applied": True},
                {"character_name": "Void Theorist", "applied": False,
                 "error": "No character found"},
            ]})]

        violations = inv_enforce_rulings_dropped(events, {})

        assert len(violations) == 1
        assert violations[0].severity == ERROR
        assert "Void Theorist" in violations[0].message

    def test_observe_only_mode_is_ignored(self):
        """Observe-only logs rulings with no per-ruling `applied` records."""
        events = [_ev("post_resolution_adjudication", data={
            "rulings": [{"character_name": "X", "soulcredit_delta": -1}]})]

        assert inv_enforce_rulings_dropped(events, {}) == []


class TestClockWithoutSpawn:

    def test_spawned_clock_is_clean(self):
        events = [
            _ev("clock_spawn", data={"clock_name": "Lattice"}),
            _ev("clock_advancement", data={"clock_name": "Lattice"}),
        ]

        assert inv_clock_without_spawn(events, {}) == []

    def test_unborn_clock_is_reported(self):
        """DM-created clocks emitted advancement and removal but no spawn."""
        events = [_ev("clock_advancement", data={"clock_name": "Coven Containment"})]

        violations = inv_clock_without_spawn(events, {})

        assert len(violations) == 1
        assert "Coven Containment" in violations[0].message

    def test_reported_once_per_clock(self):
        events = [
            _ev("clock_advancement", data={"clock_name": "Ghost"}),
            _ev("clock_advancement", data={"clock_name": "Ghost"}),
            _ev("clock_removal", data={"clock_name": "Ghost"}),
        ]

        assert len(inv_clock_without_spawn(events, {})) == 1


class TestRegisteredInTheSuite:

    def test_new_checkers_run_from_check(self):
        """ids() reports the violation label, not the function name."""
        events = [_ev("session_end"), _ev("session_end")]

        assert "duplicate_session_end" in ids(check(events))
