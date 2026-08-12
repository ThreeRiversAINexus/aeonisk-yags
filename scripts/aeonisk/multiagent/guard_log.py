"""One call site for "the engine refused what the DM asked for" (#155).

Guards are spread across five modules and every one of them announced itself to
the console and nowhere else. That made the refusals unmeasurable — 343 dropped
viewer ids and 75 prisoner-targeting warnings sat in stdout, where the project's
own rule says numbers must not come from — and untestable, because no recorded
fixture can assert that a guard fired when firing leaves no trace.

Kept as a free function rather than a logger method so a validator can report a
rejection without taking the mechanics engine as a dependency, and so a missing
logger is never an error: a guard must not be able to crash the session it is
protecting.
"""

from typing import Any, Optional

DISPOSITIONS = frozenset({"skipped", "corrected", "dropped", "allowed"})


def record_guard_rejection(
    mechanics: Any,
    round_num: Optional[int],
    guard: str,
    disposition: str,
    requested: str,
    reason: str,
    subject_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    substituted: Optional[str] = None,
) -> bool:
    """Write one `guard_rejection` event. Returns whether anything was written.

    `disposition` says what the engine actually did, and the four values are not
    interchangeable: `allowed` means the guard flagged a request and permitted it
    (a fidelity signal about the DM), `skipped` means it refused (a correctness
    signal about the engine's protection), `corrected` means it repaired the
    request, `dropped` means it discarded input. Counting them together would
    hide which one is growing.
    """
    if disposition not in DISPOSITIONS:
        raise ValueError(
            f"unknown disposition {disposition!r}; expected one of "
            f"{sorted(DISPOSITIONS)}")

    jsonl = getattr(mechanics, "jsonl_logger", None) if mechanics is not None else None
    if jsonl is None:
        return False

    jsonl.log_guard_rejection(
        round_num=round_num if round_num is not None else getattr(
            mechanics, "current_round", 0),
        guard=guard,
        disposition=disposition,
        requested=requested,
        reason=reason,
        subject_id=subject_id,
        agent_id=agent_id,
        substituted=substituted,
    )
    return True
