"""Machine-readable session liveness: completed, failed, or stalled.

Why this exists: detecting whether a run had finished meant grepping stdout for
a phrase the process only prints on a clean exit. A run killed by a timeout
never printed it, so a wait loop on that phrase spun forever — and a hung run
was indistinguishable from a slow one, since both look like "no new output".

A status sidecar makes the three cases separable without parsing anything:
terminal state is recorded explicitly, and a heartbeat timestamp turns "hung"
into an observable condition rather than a guess.
"""

import json
import time
from pathlib import Path

import pytest

from scripts.aeonisk.multiagent.session_status import (
    COMPLETED, FAILED, INTERRUPTED, RUNNING, STALLED,
    classify, latest_status_file, prune_status_files, read_status,
    status_dir_for, write_status,
)


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "multiagent_output" / "transmedia"
    d.mkdir(parents=True)
    return d


class TestStatusDir:

    def test_status_dir_is_hidden_beside_the_jsonl(self, out_dir):
        """multiagent_output/ is gitignored, so .status/ inside it is too."""
        assert status_dir_for(out_dir).name == ".status"
        assert status_dir_for(out_dir).parent == out_dir

    def test_writing_creates_the_dir(self, out_dir):
        write_status(out_dir, "abc123", RUNNING, round=1)

        assert status_dir_for(out_dir).is_dir()


class TestWriteAndRead:

    def test_roundtrip(self, out_dir):
        write_status(out_dir, "abc123", RUNNING, round=2, max_turns=4, pid=999)

        status = read_status(status_dir_for(out_dir) / "abc123.json")

        assert status["state"] == RUNNING
        assert status["round"] == 2
        assert status["max_turns"] == 4
        assert status["session_id"] == "abc123"

    def test_updated_timestamp_advances(self, out_dir):
        write_status(out_dir, "abc123", RUNNING, round=1)
        first = read_status(status_dir_for(out_dir) / "abc123.json")["updated"]
        time.sleep(0.01)
        write_status(out_dir, "abc123", RUNNING, round=2)
        second = read_status(status_dir_for(out_dir) / "abc123.json")["updated"]

        assert second > first

    def test_started_is_preserved_across_updates(self, out_dir):
        """Only `updated` moves; `started` anchors total elapsed time."""
        write_status(out_dir, "abc123", RUNNING, round=1)
        started = read_status(status_dir_for(out_dir) / "abc123.json")["started"]
        time.sleep(0.01)
        write_status(out_dir, "abc123", RUNNING, round=2)

        assert read_status(status_dir_for(out_dir) / "abc123.json")["started"] == started

    def test_failure_records_the_error(self, out_dir):
        write_status(out_dir, "abc123", FAILED, error="TypeError: boom")

        assert read_status(status_dir_for(out_dir) / "abc123.json")["error"] == "TypeError: boom"

    def test_write_is_atomic(self, out_dir):
        """A reader must never catch a half-written file (poll loops read often)."""
        write_status(out_dir, "abc123", RUNNING, round=1)
        leftovers = list(status_dir_for(out_dir).glob("*.tmp"))

        assert leftovers == []

    def test_missing_file_reads_as_none(self, out_dir):
        assert read_status(status_dir_for(out_dir) / "nope.json") is None

    def test_corrupt_file_reads_as_none_rather_than_raising(self, out_dir):
        path = status_dir_for(out_dir) / "bad.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")

        assert read_status(path) is None


class TestClassify:
    """The whole point: three outcomes, no guessing."""

    # Fixed clock: comparing against wall-clock time makes the boundary case
    # racy, since real time passes between building the status and classifying.
    NOW = 1_000_000.0

    def _running(self, age_seconds=0.0):
        return {"state": RUNNING, "updated": self.NOW - age_seconds}

    def test_terminal_states_pass_through(self):
        for state in (COMPLETED, FAILED, INTERRUPTED):
            assert classify({"state": state, "updated": 0}) == state

    def test_fresh_running_is_running(self):
        assert classify(self._running(5), stall_after=600, now=self.NOW) == RUNNING

    def test_stale_running_is_stalled(self):
        """The case that previously had no signal at all — a hung run and a slow
        run both just stop producing output."""
        assert classify(self._running(900), stall_after=600, now=self.NOW) == STALLED

    def test_boundary_is_not_yet_stalled(self):
        assert classify(self._running(600), stall_after=600, now=self.NOW) == RUNNING

    def test_none_status_is_none(self):
        assert classify(None) is None

    def test_terminal_state_is_never_stalled(self):
        """A finished run is finished no matter how old the file is."""
        assert classify({"state": COMPLETED, "updated": 0}, stall_after=1) == COMPLETED


class TestLatestStatusFile:

    def test_picks_the_newest(self, out_dir):
        write_status(out_dir, "older", COMPLETED)
        time.sleep(0.01)
        write_status(out_dir, "newer", RUNNING, round=1)

        assert latest_status_file(out_dir).stem == "newer"

    def test_none_when_empty(self, out_dir):
        assert latest_status_file(out_dir) is None

    def test_none_when_dir_absent(self, tmp_path):
        assert latest_status_file(tmp_path / "does-not-exist") is None


class TestPrune:
    """Sidecars must not accumulate one-per-session forever."""

    def _age(self, path, days):
        old = time.time() - days * 86400
        import os
        os.utime(path, (old, old))

    def test_removes_old_terminal_statuses(self, out_dir):
        write_status(out_dir, "done", COMPLETED)
        self._age(status_dir_for(out_dir) / "done.json", days=30)

        removed = prune_status_files(out_dir, keep_days=7)

        assert removed == 1
        assert not (status_dir_for(out_dir) / "done.json").exists()

    def test_keeps_recent_terminal_statuses(self, out_dir):
        write_status(out_dir, "done", COMPLETED)

        assert prune_status_files(out_dir, keep_days=7) == 0

    def test_never_removes_a_running_session(self, out_dir):
        """Even an ancient 'running' file is evidence of a hang worth seeing."""
        write_status(out_dir, "hung", RUNNING, round=2)
        self._age(status_dir_for(out_dir) / "hung.json", days=90)

        assert prune_status_files(out_dir, keep_days=7) == 0
        assert (status_dir_for(out_dir) / "hung.json").exists()

    def test_missing_dir_is_a_noop(self, tmp_path):
        assert prune_status_files(tmp_path / "nope", keep_days=7) == 0
