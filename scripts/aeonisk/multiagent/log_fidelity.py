"""Does the JSONL actually say what the engine holds?

Five of the nine defects found in the 2026-08-09 audit shared one shape: the log
and the live state disagreed, silently, and nothing was watching.

    #89          engine had 7 NPCs alive      log had no NPC rows at all
    #80 fallout  ledger said the Matron -8    log said soulcredit: 0 (hardcoded)
    #86          is_defeated: true            end_state_snapshot said false
    #87          margins -12, -18             round_summary said avg_margin 0.0
    #88          tranquilizer declared        never appeared in any event

Every one is mechanically detectable by comparing what was written against what
the engine holds. This module does that comparison.

**It deliberately shares no code with the writers.** `session.character_state_row`
is the writer's builder; if the oracle used it too, it could only ever compare
that builder against itself and would be blind to exactly the bugs above — a
hardcoded constant, a missing loop, an entity kind nobody logs. `live_snapshot`
below re-reads the entity independently, and that independence is the whole
point. Do not refactor them together.

Warn-only by design: divergence is reported, never enforced. Telemetry must not
gate play.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional

# Fields the oracle cross-checks. Deliberately the mechanical ones — narrative
# fields drift for legitimate reasons, these do not.
CHECKED_FIELDS = (
    "health", "max_health", "wounds", "stuns",
    "void_score", "soulcredit", "is_defeated", "death_state",
)

MISSING_ROW = "missing_row"
EXTRA_ROW = "extra_row"
VALUE_MISMATCH = "value_mismatch"


@dataclass
class Divergence:
    kind: str
    agent_id: str
    field: Optional[str] = None
    expected: Any = None
    logged: Any = None
    name: Optional[str] = None

    def __str__(self) -> str:
        who = f"{self.name} ({self.agent_id})" if self.name else self.agent_id
        if self.kind == MISSING_ROW:
            return f"{who}: active but produced no character_state row"
        if self.kind == EXTRA_ROW:
            return f"{who}: character_state row for an entity not in live state"
        return (f"{who}: {self.field} logged as {self.logged!r} "
                f"but engine holds {self.expected!r}")

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _derive_death_state(entity) -> str:
    """Independent restatement of the life-state rule.

    Intentionally duplicated from session.derive_death_state. A cross-check that
    imports the thing it is checking is not a cross-check; if the rule changes in
    one place and not the other, that disagreement is a finding worth surfacing,
    not a bug in this module.
    """
    wounds = getattr(entity, "wounds", 0) or 0
    health = getattr(entity, "health", 0) or 0
    stuns = getattr(entity, "stuns", 0) or 0
    if wounds >= 6:
        return "dead"
    if health <= 0 or stuns >= 6:
        return "unconscious"
    return "alive"


def live_snapshot(entity, mechanics=None) -> Dict[str, Any]:
    """Read the mechanical state of one entity straight off the live object."""
    death_state = _derive_death_state(entity)

    soulcredit = 0
    char_state = getattr(entity, "character_state", None)
    if char_state is not None and hasattr(char_state, "soulcredit"):
        soulcredit = char_state.soulcredit or 0
    if mechanics is not None:
        states = getattr(mechanics, "soulcredit_states", None) or {}
        ledger = states.get(getattr(entity, "agent_id", None))
        if ledger is not None:
            soulcredit = getattr(ledger, "score", soulcredit)

    void_score = getattr(entity, "void_score", None)
    if void_score is None and char_state is not None:
        void_score = getattr(char_state, "void_score", 0)

    return {
        "health": getattr(entity, "health", 0) or 0,
        "max_health": getattr(entity, "max_health", 0) or 0,
        "wounds": getattr(entity, "wounds", 0) or 0,
        "stuns": getattr(entity, "stuns", 0) or 0,
        "void_score": void_score or 0,
        "soulcredit": soulcredit,
        "is_defeated": death_state != "alive",
        "death_state": death_state,
    }


def live_state(players: Iterable = (), enemies: Iterable = (),
               npcs: Iterable = (), mechanics=None) -> Dict[str, Dict[str, Any]]:
    """Snapshot every entity that ought to appear in this round's log.

    Only *active* enemies and NPCs are expected to produce rows, matching what
    the writers do. Players are always expected — a downed player still has a
    life state worth recording, and #86 turned on exactly that.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for group, active_only in ((players, False), (enemies, True), (npcs, True)):
        for entity in group or []:
            agent_id = getattr(entity, "agent_id", None)
            if not agent_id:
                continue
            if active_only and not getattr(entity, "is_active", True):
                continue
            out[agent_id] = live_snapshot(entity, mechanics)
    return out


def compare_rows(
    expected: Dict[str, Dict[str, Any]],
    logged: Dict[str, Dict[str, Any]],
    names: Optional[Dict[str, str]] = None,
) -> List[Divergence]:
    """Diff live state against what was written. Empty list means faithful."""
    names = names or {}
    out: List[Divergence] = []

    for agent_id, live in expected.items():
        row = logged.get(agent_id)
        if row is None:
            out.append(Divergence(MISSING_ROW, agent_id, name=names.get(agent_id)))
            continue
        for field in CHECKED_FIELDS:
            if field not in row:
                continue
            if row[field] != live[field]:
                out.append(Divergence(
                    VALUE_MISMATCH, agent_id, field,
                    expected=live[field], logged=row[field],
                    name=names.get(agent_id)))

    for agent_id in logged:
        if agent_id not in expected:
            out.append(Divergence(EXTRA_ROW, agent_id, name=names.get(agent_id)))

    return out


def compare_round_summary(summary: Dict[str, Any],
                          resolutions: List[Dict[str, Any]]) -> List[Divergence]:
    """Cross-check round_summary counters against the round's actual resolutions.

    #87: every round reported actions_attempted 0 and average_margin +0.0 while
    real margins were -12, -18, +10, +2, -5 — the counters were simply never
    incremented under the outcome-first pipeline.
    """
    out: List[Divergence] = []
    attempted = len(resolutions)
    logged_attempted = summary.get("actions_attempted")

    if logged_attempted is not None and logged_attempted != attempted:
        out.append(Divergence(
            VALUE_MISMATCH, "round_summary", "actions_attempted",
            expected=attempted, logged=logged_attempted))

    if attempted:
        margins = [r.get("margin") or 0 for r in resolutions]
        expected_avg = sum(margins) / attempted
        logged_avg = summary.get("average_margin")
        if logged_avg is not None and abs(logged_avg - expected_avg) > 0.05:
            out.append(Divergence(
                VALUE_MISMATCH, "round_summary", "average_margin",
                expected=round(expected_avg, 2), logged=logged_avg))

    return out
