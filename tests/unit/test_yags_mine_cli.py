"""
Unit tests for the yags_mine CLI wrapper.
"""

import argparse
import sys
from pathlib import Path


scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import analyze_session
import yags_mine
from analyze_session import SessionDiscovery


def test_cmd_analyze_dispatches_current_session_analyzer_methods(tmp_path, monkeypatch):
    """Analyze mode should call the current SessionAnalyzer print methods."""
    session_file = tmp_path / "session_test.jsonl"
    session_file.write_text('{"event_type": "session_start"}\n')
    calls = []

    class FakeSessionAnalyzer:
        def __init__(self, path):
            self.path = path

        def print_errors(self):
            calls.append(("errors", self.path))

        def print_void(self):
            calls.append(("void", self.path))

        def print_clocks(self):
            calls.append(("clocks", self.path))

        def print_summary(self):
            calls.append(("summary", self.path))

    monkeypatch.setattr(analyze_session, "SessionAnalyzer", FakeSessionAnalyzer)

    for mode in ("errors", "void", "clocks", "summary"):
        args = argparse.Namespace(
            path=str(session_file),
            mode=mode,
            recursive=False,
            limit=None,
        )
        assert yags_mine.cmd_analyze(args) == 0

    assert calls == [
        ("errors", session_file),
        ("void", session_file),
        ("clocks", session_file),
        ("summary", session_file),
    ]


def test_session_discovery_scans_nested_bulk_output(tmp_path):
    """Discovery should find session files inside bulk run subdirectories."""
    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    session_file = run_dir / "session_test.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"event_type": "session_start", "config": {"party_size": 2}}',
                '{"event_type": "round_start", "round": 1}',
                '{"event_type": "enemy_spawn", "count": 3}',
                '{"event_type": "round_start", "round": 2}',
                '{"event_type": "session_end"}',
            ]
        )
        + "\n"
    )

    sessions = SessionDiscovery(tmp_path).scan(complete_only=True, min_rounds=2)

    assert len(sessions) == 1
    assert sessions[0]["path"] == session_file
    assert sessions[0]["complete"] is True
    assert sessions[0]["rounds"] == 2
    assert sessions[0]["enemies_spawned"] == 3


def test_cmd_discover_reports_scores_actions_and_completion(tmp_path, capsys):
    """Discover CLI should print computed metadata instead of stale defaults."""
    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    session_file = run_dir / "session_test.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"event_type": "session_start", "config": {"party_size": 2}}',
                '{"event_type": "round_start", "round": 1}',
                '{"event_type": "action_resolution"}',
                '{"event_type": "round_start", "round": 2}',
                '{"event_type": "session_end"}',
            ]
        )
        + "\n"
    )

    args = argparse.Namespace(
        directory=str(tmp_path),
        complete_only=True,
        min_rounds=2,
        limit=20,
        format="text",
    )

    assert yags_mine.cmd_discover(args) == 0
    output = capsys.readouterr().out

    assert "Found: 1 sessions" in output
    assert "Score: 122.0" in output
    assert "Actions: 1" in output
    assert "Complete:" in output


def test_cmd_fidelity_extracts_items_from_directory(tmp_path, capsys):
    """Fidelity command should extract eval items and write them to JSONL."""
    import json

    session_file = tmp_path / "golden_test.jsonl"
    event = {
        "event_type": "action_resolution",
        "session": "abc12345-feed-face-cafe-000000000000",
        "round": 1, "phase": "adjudicate", "agent": "Tester",
        "action": "Strike",
        "context": {"action_type": "combat", "faction": "Freeborn",
                    "description": "swing", "is_ritual": False,
                    "damage_effects": []},
        "roll": {"attr": "Agility", "attr_val": 4, "skill": "Combat",
                 "skill_val": 5, "ability": 20, "d20": 8,
                 "modifiers": None, "modifier_total": None,
                 "total": 28, "dc": 18, "margin": 10,
                 "tier": "good", "success": True},
        "economy": {"void_delta": 0, "soulcredit_delta": 1,
                    "soulcredit_reasons": ["protected a bystander"]},
    }
    session_file.write_text(json.dumps(event) + "\n")
    output = tmp_path / "items.jsonl"

    args = argparse.Namespace(
        path=str(tmp_path), tasks=None, output=str(output),
        quarantine_output=None, recursive=True, format="json",
    )
    assert yags_mine.cmd_fidelity(args) == 0

    items = [json.loads(line) for line in output.read_text().strip().split("\n")]
    tasks = {item["task"] for item in items}
    assert tasks == {"roll_resolution", "soulcredit_adjudication"}
    stats = json.loads(capsys.readouterr().out)
    assert stats["items"] == 2
    assert stats["quarantined"] == 0


def test_cmd_fidelity_rejects_unknown_task(tmp_path):
    session_file = tmp_path / "s.jsonl"
    session_file.write_text("")
    args = argparse.Namespace(
        path=str(session_file), tasks="bogus", output=None,
        quarantine_output=None, recursive=True, format="text",
    )
    assert yags_mine.cmd_fidelity(args) == 1
