"""TDD spec for contract replay (scripts/contract_replay.py) — Phase 2.

The sound, cheap tool for prompt/schema changes: re-validate each recorded
structured llm_call response against the CURRENT Pydantic schema (named by the
event's call_type tag). No LLM, no session engine, no chaining — each recorded
decision is checked independently, so a schema change that breaks old decisions
is caught by one command instead of a live session crash.

Honest-accounting rules: unknown schema names and untagged/legacy events are
COUNTED and reported, never silently passed.
"""
import json

from scripts.contract_replay import (
    build_registry,
    check_call,
    replay_events,
)


def call(call_type, response, agent="dm_01", seq=0):
    return {"event_type": "llm_call", "round": 1, "agent_id": agent,
            "agent_type": "dm", "call_sequence": seq, "call_type": call_type,
            "prompt": [{"role": "user", "content": "p"}], "response": response,
            "model": "m", "temperature": 0.7}


def test_registry_finds_known_schemas():
    reg = build_registry()
    for name in ("ActionResolution", "PlayerAction", "ScenarioSetup",
                 "RoundSynthesis", "EnemyDecision", "ActionIntent",
                 "RoundAssessment", "PostRulings", "NPCAction"):
        assert name in reg, f"registry missing {name}"


VALID_ENEMY_DECISION = {
    "major_action": "Attack",
    "tactical_reasoning": "Flank the exposed PC on the left while cover holds.",
}


def test_valid_response_passes():
    ev = call("structured:EnemyDecision", json.dumps(VALID_ENEMY_DECISION))
    result = check_call(ev, build_registry())
    assert result.status == "ok", result.error


def test_broken_response_fails_with_error():
    ev = call("structured:EnemyDecision", json.dumps({"nonsense": True}))
    result = check_call(ev, build_registry())
    assert result.status == "invalid"
    assert result.error  # carries the validation error summary


def test_unparseable_json_is_invalid():
    ev = call("structured:EnemyDecision", "not json at all")
    assert check_call(ev, build_registry()).status == "invalid"


def test_unknown_schema_is_reported_not_passed():
    ev = call("structured:SomeFutureSchema", "{}")
    assert check_call(ev, build_registry()).status == "unknown_schema"


def test_text_calls_are_skipped():
    ev = call("text", "just narration")
    assert check_call(ev, build_registry()).status == "skipped_text"


def test_untagged_legacy_calls_are_counted():
    ev = call(None, "{}")
    del ev["call_type"]
    assert check_call(ev, build_registry()).status == "untagged"


def test_replay_events_aggregates():
    events = [
        call("structured:EnemyDecision", json.dumps(VALID_ENEMY_DECISION)),  # ok
        call("structured:EnemyDecision", '{"broken": 1}', seq=1),   # invalid
        call("text:enemy_tactical", "narration", seq=2),            # skipped
        {"event_type": "llm_call", "agent_id": "x", "call_sequence": 3,
         "response": "{}"},                                          # untagged
        {"event_type": "round_start", "round": 1},                   # not an llm_call
    ]
    rep = replay_events(events)
    assert rep.ok == 1
    assert rep.invalid == 1
    assert rep.skipped_text == 1
    assert rep.untagged == 1
    assert rep.has_failures is True
    assert len(rep.failures) == 1
    assert rep.failures[0].agent == "dm_01"
