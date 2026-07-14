"""The bulk runner's post-session mechanical-integrity gate.

A session can run to completion and still be self-contradictory; the gate
quarantines those so they never silently enter a dataset. These tests exercise
`gate_session_invariants` directly (the subprocess `run_single_session` wrapper
is integration-tested elsewhere) on synthetic JSONL sessions.
"""
import json

import pytest

from scripts.bulk_session_runner import gate_session_invariants


def _write_session(path, events):
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    return path


def _clean_events():
    return [
        {"event_type": "session_start"},
        {"event_type": "character_state", "round": 1, "character_name": "Vane",
         "health": 26, "max_health": 26, "wounds": 0, "stuns": 0,
         "is_defeated": False, "death_state": "alive", "void_score": 3, "soulcredit": 0,
         "agent": "player"},
        {"event_type": "session_end"},
    ]


def _dirty_events():
    # An entity converted to prisoner that then attacks with no jailbreak =
    # restrained_hostile_action ERROR (config-independent, so it fires without
    # a config.json sidecar).
    return [
        {"event_type": "session_start"},
        {"event_type": "enemy_spawn", "round": 0, "enemy_id": "g1",
         "enemy_name": "Operative", "stats": {"health": 30, "weapons": []}},
        {"event_type": "entity_lifecycle", "round": 1, "enemies_converted": ["g1"]},
        {"event_type": "action_declaration", "round": 2, "player_id": "g1",
         "character_name": "Operative", "action": {"major_action": "Attack", "target": "tgt_x"}},
        {"event_type": "session_end"},
    ]


def test_clean_session_passes_gate(tmp_path):
    p = _write_session(tmp_path / "session_clean.jsonl", _clean_events())
    assert gate_session_invariants(p) == []
    assert not (tmp_path / "invariant_violations.json").exists()


def test_dirty_session_is_flagged_with_sidecar(tmp_path):
    p = _write_session(tmp_path / "session_dirty.jsonl", _dirty_events())
    errors = gate_session_invariants(p)
    assert errors, "gate must report the restrained_hostile_action contradiction"
    assert {e["invariant"] for e in errors} == {"restrained_hostile_action"}
    assert all(e["severity"] == "error" for e in errors)

    sidecar = tmp_path / "invariant_violations.json"
    assert sidecar.exists(), "a quarantined run must be self-describing"
    assert json.loads(sidecar.read_text())[0]["invariant"] == "restrained_hostile_action"


def test_gate_never_raises_on_garbage(tmp_path):
    p = tmp_path / "session_garbage.jsonl"
    p.write_text("not json\n{broken\n")
    # Must degrade to "no errors" rather than crashing the run it audits.
    assert gate_session_invariants(p) == []
