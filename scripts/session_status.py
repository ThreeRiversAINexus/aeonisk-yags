#!/usr/bin/env python3
"""Is that session done, dead, or stuck?

    python scripts/session_status.py multiagent_output/transmedia
    python scripts/session_status.py multiagent_output/transmedia --wait

Exit codes make this usable as a condition instead of a log grep:

    0  completed    3  stalled (running, but no heartbeat for a while)
    1  failed       4  no session found
    2  running      5  --wait timed out

Detecting completion used to mean grepping stdout for a line the process only
prints on a clean exit. A run killed by a timeout never prints it, so a wait
loop on that phrase spins forever; and a hung run is indistinguishable from a
slow one because both simply stop producing output. `--wait` blocks until the
session reaches a terminal state OR stalls, so it always ends.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aeonisk.multiagent.session_status import (  # noqa: E402
    COMPLETED, FAILED, INTERRUPTED, RUNNING, STALLED,
    DEFAULT_STALL_AFTER, classify, latest_status_file, read_status,
)

EXIT_CODES = {
    COMPLETED: 0,
    FAILED: 1,
    INTERRUPTED: 1,
    RUNNING: 2,
    STALLED: 3,
}
NOT_FOUND = 4
WAIT_TIMEOUT = 5


def _resolve(target: Path) -> Path | None:
    """Accept an output dir, a .status dir, or a status file directly."""
    if target.is_file():
        return target
    if target.name == ".status" and target.is_dir():
        candidates = sorted(target.glob("*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None
    return latest_status_file(target)


def _describe(status: dict, state: str) -> str:
    session = status.get("session_id", "?")
    parts = [f"{state.upper():9s} {session}"]

    if status.get("round") is not None:
        parts.append(f"round {status['round']}/{status.get('max_turns', '?')}")

    started, updated = status.get("started"), status.get("updated")
    if started and updated:
        parts.append(f"elapsed {int(float(updated) - float(started))}s")
    if updated and state in (RUNNING, STALLED):
        parts.append(f"last heartbeat {int(time.time() - float(updated))}s ago")
    if status.get("error"):
        parts.append(f"error: {status['error']}")
    if status.get("jsonl"):
        parts.append(str(status["jsonl"]))

    return "  ".join(parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report whether a session completed, failed, or stalled.")
    parser.add_argument(
        "target", type=Path,
        help="Session output dir (or a .status dir / status file).")
    parser.add_argument(
        "--wait", action="store_true",
        help="Block until the session is terminal or stalls, then exit.")
    parser.add_argument(
        "--timeout", type=float, default=7200,
        help="Give up waiting after this many seconds (default 7200).")
    parser.add_argument(
        "--poll", type=float, default=15,
        help="Seconds between checks while waiting (default 15).")
    parser.add_argument(
        "--stall-after", type=float, default=DEFAULT_STALL_AFTER,
        help=f"Heartbeat age that counts as stalled (default {DEFAULT_STALL_AFTER:.0f}s).")
    args = parser.parse_args(argv)

    deadline = time.time() + args.timeout

    while True:
        path = _resolve(args.target)
        status = read_status(path) if path else None
        state = classify(status, stall_after=args.stall_after)

        if state is None:
            if not args.wait or time.time() >= deadline:
                print(f"NONE      no session status under {args.target}")
                return NOT_FOUND
        else:
            print(_describe(status, state), flush=True)
            # Stalled is terminal *for waiting purposes*: the whole point is
            # that a wait must never outlive the thing it waits on.
            if not args.wait or state != RUNNING:
                return EXIT_CODES[state]

        if time.time() >= deadline:
            print(f"TIMEOUT   still not terminal after {args.timeout:.0f}s")
            return WAIT_TIMEOUT

        time.sleep(min(args.poll, max(0.0, deadline - time.time())))


if __name__ == "__main__":
    sys.exit(main())
