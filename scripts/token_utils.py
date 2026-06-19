#!/usr/bin/env python3
"""
Token counting helpers shared by analysis and cost reporting tools.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

try:
    import tiktoken
except ImportError:  # pragma: no cover - dependency optional in dev env
    tiktoken = None


def get_encoding(model: Optional[str] = None):
    """Return a tiktoken encoding for a model, or None if unavailable."""
    if tiktoken is None:
        return None

    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            pass

    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_text_tokens(text: str, model: Optional[str] = None) -> int:
    """Count tokens in plain text."""
    if not text:
        return 0

    encoding = get_encoding(model)
    if encoding is not None:
        return len(encoding.encode(text))

    return max(1, len(text) // 4)


def count_chat_tokens(messages: Iterable[Dict[str, Any]], model: Optional[str] = None) -> int:
    """
    Count tokens for a chat message list.

    Uses tiktoken when available and a conservative chat-message overhead
    approximation otherwise.
    """
    messages = list(messages or [])
    if not messages:
        return 0

    encoding = get_encoding(model)
    if encoding is None:
        total_chars = 0
        for message in messages:
            total_chars += len(str(message.get("content", "")))
            total_chars += len(str(message.get("role", "")))
            if message.get("name"):
                total_chars += len(str(message["name"]))
        return max(1, total_chars // 4)

    tokens = 0
    tokens_per_message = 3
    tokens_per_name = 1

    for message in messages:
        tokens += tokens_per_message
        for key, value in message.items():
            if key == "content" and value is not None:
                tokens += len(encoding.encode(str(value)))
            elif key == "name" and value is not None:
                tokens += tokens_per_name + len(encoding.encode(str(value)))
            elif key != "content" and key != "name" and value is not None:
                tokens += len(encoding.encode(str(value)))

    tokens += 3
    return tokens
