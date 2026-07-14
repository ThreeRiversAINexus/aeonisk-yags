"""Regression: character_state snapshots must log the `stuns` count.

Bug (BUG_STUN_KO_DEFEAT.md): a character stun-KO'd (stuns >= 6, the YAGS
Beaten threshold) is logged is_defeated=True / death_state="unconscious" even
at full health and low wounds. The snapshot previously omitted `stuns`, so the
defeat flag looked impossible ("unconscious at 58% HP") and was undiagnosable
from the JSONL alone. These tests pin the field into the schema.
"""
import json
import pytest

from scripts.aeonisk.multiagent.mechanics import JSONLLogger


def _last_character_state(logger: JSONLLogger) -> dict:
    events = [json.loads(l) for l in logger.log_file.read_text().splitlines() if l.strip()]
    states = [e for e in events if e["event_type"] == "character_state"]
    assert states, "no character_state event was written"
    return states[-1]


def test_character_state_logs_stuns(tmp_path):
    logger = JSONLLogger(session_id="stun-test", output_dir=str(tmp_path))
    logger.log_character_state(
        round_num=1, character_id="player_01", character_name="Hard Vane",
        health=15, max_health=26, wounds=2, void_score=3, soulcredit=-1,
        position="Near-PC", is_defeated=True, death_state="unconscious",
        stuns=12,
    )
    state = _last_character_state(logger)
    assert "stuns" in state, "character_state must log the stun count"
    assert state["stuns"] == 12


def test_stun_ko_snapshot_is_now_self_explanatory(tmp_path):
    """The exact Hard Vane paradox: defeated + healthy + few wounds is only
    explicable once `stuns` is present and >= the Beaten threshold (6)."""
    logger = JSONLLogger(session_id="stun-ko", output_dir=str(tmp_path))
    logger.log_character_state(
        round_num=1, character_id="player_01", character_name="Hard Vane",
        health=15, max_health=26, wounds=2, void_score=3, soulcredit=-1,
        position="Near-PC", is_defeated=True, death_state="unconscious",
        stuns=12,
    )
    s = _last_character_state(logger)
    assert s["is_defeated"] and s["death_state"] == "unconscious"
    assert s["health"] > 0 and s["wounds"] < 6  # neither wound nor health explains it
    assert s["stuns"] >= 6  # ...but the stun track does


def test_stuns_defaults_to_zero_when_unspecified(tmp_path):
    """Callers that don't pass stuns (alive characters) still get the field."""
    logger = JSONLLogger(session_id="stun-default", output_dir=str(tmp_path))
    logger.log_character_state(
        round_num=1, character_id="player_02", character_name="Oathkeeper Sela",
        health=26, max_health=26, wounds=0, void_score=3, soulcredit=9,
        position="Near-PC",
    )
    assert _last_character_state(logger)["stuns"] == 0
