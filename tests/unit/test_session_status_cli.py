"""The CLI contract: detection is an exit code, not a log grep.

The failure this replaces: a wait loop keyed on a stdout phrase that a
timeout-killed run never prints, spinning forever with no way to tell a hung
session from a slow one.
"""

import importlib.util
import sys
import time
from pathlib import Path

import pytest

from scripts.aeonisk.multiagent.session_status import (
    COMPLETED, FAILED, INTERRUPTED, RUNNING, status_dir_for, write_status,
)

_CLI = Path(__file__).resolve().parents[2] / "scripts" / "session_status.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("session_status_cli", _CLI)
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_status_cli"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli():
    return load_cli()


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


class TestExitCodes:

    def test_completed_is_zero(self, cli, out_dir, capsys):
        write_status(out_dir, "s1", COMPLETED, round=4, max_turns=4)

        assert cli.main([str(out_dir)]) == 0
        assert "COMPLETED" in capsys.readouterr().out

    def test_failed_is_one(self, cli, out_dir, capsys):
        write_status(out_dir, "s1", FAILED, error="TypeError: boom")

        assert cli.main([str(out_dir)]) == 1
        assert "TypeError: boom" in capsys.readouterr().out

    def test_interrupted_is_one(self, cli, out_dir):
        write_status(out_dir, "s1", INTERRUPTED)

        assert cli.main([str(out_dir)]) == 1

    def test_running_is_two(self, cli, out_dir):
        write_status(out_dir, "s1", RUNNING, round=2, max_turns=4)

        assert cli.main([str(out_dir)]) == 2

    def test_stalled_is_three(self, cli, out_dir, capsys):
        """A run whose heartbeat went cold — previously undetectable."""
        write_status(out_dir, "s1", RUNNING, round=2)
        path = status_dir_for(out_dir) / "s1.json"
        stale = json_with_old_heartbeat(path, age_seconds=4000)

        assert cli.main([str(out_dir), "--stall-after", "600"]) == 3
        assert "STALLED" in capsys.readouterr().out
        assert stale  # heartbeat really was rewritten

    def test_no_session_is_four(self, cli, out_dir, capsys):
        assert cli.main([str(out_dir)]) == 4
        assert "no session status" in capsys.readouterr().out


def json_with_old_heartbeat(path: Path, age_seconds: float) -> bool:
    import json
    data = json.loads(path.read_text())
    data["updated"] = time.time() - age_seconds
    path.write_text(json.dumps(data))
    return True


class TestWaitAlwaysTerminates:
    """The core requirement: a wait must never outlive what it waits on."""

    def test_wait_returns_immediately_when_terminal(self, cli, out_dir):
        write_status(out_dir, "s1", COMPLETED)

        started = time.time()
        code = cli.main([str(out_dir), "--wait", "--poll", "0.01"])

        assert code == 0
        assert time.time() - started < 2

    def test_wait_ends_on_a_stall_rather_than_hanging(self, cli, out_dir):
        """This is precisely the case that hung the old loop."""
        write_status(out_dir, "s1", RUNNING, round=1)
        json_with_old_heartbeat(status_dir_for(out_dir) / "s1.json", 4000)

        code = cli.main([str(out_dir), "--wait", "--poll", "0.01",
                         "--stall-after", "600", "--timeout", "5"])

        assert code == 3

    def test_wait_times_out_rather_than_spinning(self, cli, out_dir):
        write_status(out_dir, "s1", RUNNING, round=1)

        started = time.time()
        code = cli.main([str(out_dir), "--wait", "--timeout", "0.2",
                         "--poll", "0.05"])

        assert code == 5
        assert time.time() - started < 5


class TestTargetResolution:

    def test_accepts_a_status_file_directly(self, cli, out_dir):
        write_status(out_dir, "s1", COMPLETED)

        assert cli.main([str(status_dir_for(out_dir) / "s1.json")]) == 0

    def test_accepts_the_status_dir(self, cli, out_dir):
        write_status(out_dir, "s1", COMPLETED)

        assert cli.main([str(status_dir_for(out_dir))]) == 0

    def test_picks_the_newest_session(self, cli, out_dir, capsys):
        write_status(out_dir, "old", COMPLETED)
        time.sleep(0.01)
        write_status(out_dir, "new", FAILED, error="x")

        assert cli.main([str(out_dir)]) == 1
        assert "new" in capsys.readouterr().out
