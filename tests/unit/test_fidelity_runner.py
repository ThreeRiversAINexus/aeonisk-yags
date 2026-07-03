"""Tests for the pure request/response helpers in fidelity_runner."""

import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from fidelity_runner import (
    build_chat_body,
    build_anthropic_body,
    extract_chat_content,
    extract_anthropic_content,
)

PROMPT = {"item_id": "x-r1-e1-roll", "task": "roll_resolution",
          "system": "rules here", "user": "resolve this"}


def test_build_chat_body_shape():
    body = build_chat_body(PROMPT, "gpt-5.4-mini", 300,
                           reasoning_effort="low")
    assert body["model"] == "gpt-5.4-mini"
    assert body["messages"][0] == {"role": "system", "content": "rules here"}
    assert body["messages"][1]["role"] == "user"
    assert body["max_completion_tokens"] == 300
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "low"


def test_build_chat_body_omits_reasoning_effort_when_unset():
    body = build_chat_body(PROMPT, "zai-org/GLM-5.1", 300)
    assert "reasoning_effort" not in body


def test_build_anthropic_body_shape():
    body = build_anthropic_body(PROMPT, "claude-haiku-4-5-20251001", 300)
    assert body["system"] == "rules here"
    assert body["messages"] == [{"role": "user", "content": "resolve this"}]
    assert body["max_tokens"] == 300


def test_extract_chat_content():
    payload = {"choices": [{"message": {"content": '{"total": 28}'}}]}
    assert extract_chat_content(payload) == '{"total": 28}'


def test_extract_anthropic_content_joins_text_blocks():
    payload = {"content": [{"type": "text", "text": '{"total":'},
                           {"type": "text", "text": ' 28}'}]}
    assert extract_anthropic_content(payload) == '{"total": 28}'
