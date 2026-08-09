"""Machine-readable liveness for a running session.

A session's JSONL tells you what happened, but not whether the process is still
alive. Detecting completion therefore meant grepping stdout for a phrase printed
only on a clean exit — which a timeout-killed run never reaches, so a wait loop
on that phrase never terminates. Worse, a hung run and a slow one look identical
from outside: both simply stop producing output.

This module writes a small sidecar next to the JSONL recording the terminal
state explicitly and stamping a heartbeat every round. That makes three
questions answerable without parsing anything:

    completed / failed / interrupted   -> `state` says so
    running                            -> heartbeat is fresh
    stalled                            -> `state` is running but the heartbeat is old

Sidecars live in ``<output_dir>/.status/`` — hidden, and already covered by the
``multiagent_output/`` gitignore rule. They are pruned automatically (see
``prune_status_files``) so they cannot accumulate one-per-session forever.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Terminal states
COMPLETED = "completed"
FAILED = "failed"
INTERRUPTED = "interrupted"
# Live states
RUNNING = "running"
STALLED = "stalled"  # derived, never written

TERMINAL_STATES = frozenset({COMPLETED, FAILED, INTERRUPTED})

STATUS_DIR_NAME = ".status"

# A round involves several LLM round-trips under rate limiting; a live 2-round
# session has taken >12 minutes. Ten minutes without a heartbeat is genuinely
# stuck rather than merely slow.
DEFAULT_STALL_AFTER = 600.0

DEFAULT_KEEP_DAYS = 7


def status_dir_for(output_dir: os.PathLike | str) -> Path:
    """The hidden directory holding sidecars for one output_dir."""
    return Path(output_dir) / STATUS_DIR_NAME


def status_path_for(output_dir: os.PathLike | str, session_id: str) -> Path:
    return status_dir_for(output_dir) / f"{session_id}.json"


def write_status(
    output_dir: os.PathLike | str,
    session_id: str,
    state: str,
    **fields: Any,
) -> Path:
    """Write or update a session's sidecar. Returns the path written.

    `started` is set once and preserved across updates; `updated` moves every
    call and is the heartbeat that makes stalling detectable. The write is
    atomic (temp file + replace) because poll loops read this often and must
    never catch it half-written.
    """
    path = status_path_for(output_dir, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = time.time()
    existing = read_status(path) or {}

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "state": state,
        "pid": os.getpid(),
        "started": existing.get("started", now),
        "updated": now,
    }
    # Carry forward previously-recorded context so a terminal write does not
    # erase the round/jsonl the run reached.
    for key in ("round", "max_turns", "jsonl", "config"):
        if key in existing:
            payload[key] = existing[key]
    payload.update(fields)

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)
    return path


def read_status(path: os.PathLike | str) -> Optional[Dict[str, Any]]:
    """Parse a sidecar, or None if absent/unreadable.

    Never raises: a status check must not itself become a failure mode.
    """
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def classify(
    status: Optional[Dict[str, Any]],
    stall_after: float = DEFAULT_STALL_AFTER,
    now: Optional[float] = None,
) -> Optional[str]:
    """Resolve a sidecar to one of the five states, or None if there is no status.

    A terminal state is returned as-is regardless of age — a finished run is
    finished no matter how long the file has sat there.
    """
    if not status:
        return None

    state = status.get("state")
    if state in TERMINAL_STATES:
        return state

    updated = status.get("updated") or 0
    age = (time.time() if now is None else now) - float(updated)
    return STALLED if age > stall_after else RUNNING


def latest_status_file(output_dir: os.PathLike | str) -> Optional[Path]:
    """Most recently updated sidecar in an output_dir, or None."""
    directory = status_dir_for(output_dir)
    if not directory.is_dir():
        return None
    candidates = [p for p in directory.glob("*.json") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def prune_status_files(
    output_dir: os.PathLike | str,
    keep_days: int = DEFAULT_KEEP_DAYS,
) -> int:
    """Delete terminal sidecars older than keep_days. Returns how many went.

    Running sidecars are never pruned however old they are: an ancient
    'running' file is the fingerprint of a hang, which is exactly the evidence
    worth keeping.
    """
    directory = status_dir_for(output_dir)
    if not directory.is_dir():
        return 0

    cutoff = time.time() - keep_days * 86400
    removed = 0
    for path in directory.glob("*.json"):
        status = read_status(path)
        if not status or status.get("state") not in TERMINAL_STATES:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
