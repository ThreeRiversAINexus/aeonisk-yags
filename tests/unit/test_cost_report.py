"""
Unit tests for token and cost reporting.
"""

import json
import sys
from pathlib import Path

import pytest


scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import cost_report


def write_jsonl(path: Path, events):
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")


def test_analyze_cost_uses_logged_tokens_and_pricing(tmp_path):
    session = tmp_path / "session_test.jsonl"
    pricing = tmp_path / "pricing.json"
    write_jsonl(
        session,
        [
            {"event_type": "session_start", "config": {"session_name": "cost_test"}},
            {
                "event_type": "llm_call",
                "agent_type": "dm",
                "model": "gpt-test",
                "tokens": {"input": 1000, "output": 200, "total": 1200},
            },
        ],
    )
    pricing.write_text(json.dumps({"gpt-test": {"input_per_1m": 1.0, "output_per_1m": 2.0}}))

    report = cost_report.analyze_cost(session, pricing_file=pricing)

    assert report.session_files == 1
    assert report.calls == 1
    assert report.logged_calls == 1
    assert report.input_tokens == 1000
    assert report.output_tokens == 200
    assert report.cost_usd == pytest.approx(0.0014)


def test_analyze_cost_uses_proxy_underlying_provider_for_pricing(tmp_path):
    session = tmp_path / "session_test.jsonl"
    pricing = tmp_path / "pricing.json"
    write_jsonl(
        session,
        [
            {
                "event_type": "session_start",
                "config": {
                    "session_name": "provider_test",
                    "agents": {
                        "dm": {
                            "llm": {
                                "provider": "batch_proxy",
                                "underlying_provider": "openai",
                                "model": "gpt-test",
                            }
                        },
                        "players": [
                            {
                                "llm": {
                                    "provider": "batch_proxy",
                                    "underlying_provider": "gemini",
                                    "model": "gemini-test",
                                }
                            }
                        ],
                        "enemies": {
                            "llm": {
                                "provider": "batch_proxy",
                                "underlying_provider": "gemini",
                                "model": "gemini-test",
                            }
                        },
                    },
                },
            },
            {
                "event_type": "llm_call",
                "agent_id": "dm_01",
                "agent_type": "dm",
                "model": "gpt-test",
                "tokens": {"input": 1000, "output": 100},
            },
            {
                "event_type": "llm_call",
                "agent_id": "player_01",
                "agent_type": "player",
                "model": "gemini-test",
                "tokens": {"input": 2000, "output": 200},
            },
            {
                "event_type": "llm_call",
                "agent_id": "enemy_guard_01",
                "agent_type": "enemy",
                "model": "gemini-test",
                "tokens": {"input": 3000, "output": 300},
            },
        ],
    )
    pricing.write_text(
        json.dumps(
            {
                "openai:gpt-test": {"input_per_1m": 1.0, "output_per_1m": 2.0},
                "gemini:gemini-test": {"input_per_1m": 3.0, "output_per_1m": 4.0},
            }
        )
    )

    report = cost_report.analyze_cost(session, pricing_file=pricing)
    buckets = {(bucket.agent_type, bucket.provider, bucket.model): bucket for bucket in report.sorted_buckets()}

    assert report.cost_usd == pytest.approx(0.0182)
    assert buckets[("dm", "openai", "gpt-test")].cost_usd == pytest.approx(0.0012)
    assert buckets[("player", "gemini", "gemini-test")].cost_usd == pytest.approx(0.0068)
    assert buckets[("enemy", "gemini", "gemini-test")].cost_usd == pytest.approx(0.0102)


def test_analyze_cost_flags_logged_model_mismatch(tmp_path):
    session = tmp_path / "session_test.jsonl"
    write_jsonl(
        session,
        [
            {
                "event_type": "session_start",
                "config": {
                    "session_name": "mismatch_test",
                    "agents": {
                        "enemies": {
                            "llm": {
                                "provider": "batch_proxy",
                                "underlying_provider": "gemini",
                                "model": "gemini-test",
                            }
                        }
                    },
                },
            },
            {
                "event_type": "llm_call",
                "agent_id": "enemy_guard_01",
                "agent_type": "enemy",
                "model": "gpt-test",
                "tokens": {"input": 10, "output": 5},
            },
        ],
    )

    report = cost_report.analyze_cost(session)
    bucket = report.sorted_buckets()[0]

    assert report.model_mismatch_calls == 1
    assert bucket.provider == "gemini"
    assert bucket.model == "gemini-test"
    assert bucket.logged_models == {"gpt-test": 1}


def test_analyze_cost_estimates_missing_tokens_with_tokenizer(tmp_path, monkeypatch):
    session_dir = tmp_path / "run_0001"
    session_dir.mkdir()
    session = session_dir / "session_test.jsonl"
    write_jsonl(
        session,
        [
            {"event_type": "session_start", "config": {"session_name": "estimate_test"}},
            {
                "event_type": "llm_call",
                "agent_type": "enemy",
                "model": "gpt-test",
                "prompt": [{"role": "user", "content": "hello"}],
                "response": "world",
                "tokens": {"input": 0, "output": 0},
            },
        ],
    )

    monkeypatch.setattr(cost_report, "get_encoding", lambda model: object())
    monkeypatch.setattr(cost_report, "count_chat_tokens", lambda messages, model: 11)
    monkeypatch.setattr(cost_report, "count_text_tokens", lambda text, model: 7)

    report = cost_report.analyze_cost(tmp_path)

    assert report.calls == 1
    assert report.tokenizer_estimated_calls == 1
    assert report.input_tokens == 11
    assert report.output_tokens == 7


def test_cost_report_json_shape(tmp_path):
    session = tmp_path / "session_test.jsonl"
    write_jsonl(
        session,
        [
            {"event_type": "session_start", "config": {"session_name": "shape_test"}},
            {
                "event_type": "llm_call",
                "agent_type": "player",
                "model": "gpt-test",
                "tokens": {"input": 5, "output": 3},
            },
        ],
    )

    data = cost_report.analyze_cost(session).to_dict()

    assert data["calls"] == 1
    assert data["total_tokens"] == 8
    assert data["buckets"][0]["config"] == "shape_test"
    assert data["buckets"][0]["agent_type"] == "player"
    assert data["buckets"][0]["provider"] == "unknown"
