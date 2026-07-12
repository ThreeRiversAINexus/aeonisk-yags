#!/usr/bin/env python3
"""Mechanics-diff harness — token-free formula verification.

Replay's real purpose is answering "did my formula change alter outcomes?"
without paying for LLM calls or fighting nondeterminism. This harness does that
directly: it re-runs the *current* pure mechanics functions over the mechanical
inputs already recorded in a session's events, and diffs the recomputed outcome
against what was logged. No LLM, no MockLLMProvider, no session engine — just the
math.

What it verifies today (extensible):
  * combat_action  -> damage->wounds via mechanics.apply_wound_damage
  * action_resolution -> margin->outcome tier via MechanicsEngine._determine_outcome_tier

Because there is no LLM in the loop, this is immune to the call-flow-alignment
problem that constrains full replay: it verifies formula/number changes only, but
it verifies them exactly and for free over an entire corpus.

Usage:
    python scripts/mechanics_replay.py session.jsonl [session2.jsonl ...]
    python scripts/mechanics_replay.py --json session.jsonl

Exit code is non-zero if any diff is found (so it can gate CI after a formula edit).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from aeonisk.multiagent.mechanics import (
    MechanicsEngine,
    apply_wound_damage,
)


@dataclass
class Diff:
    """A single recomputed-vs-logged discrepancy."""
    kind: str            # "combat_damage" | "outcome_tier"
    field: str           # which field diverged (e.g. "wounds_dealt", "tier")
    logged: Any          # what the session recorded
    recomputed: Any      # what the current code produces
    round: Optional[int] = None
    entity: Optional[str] = None

    def __str__(self) -> str:
        r = f"r{self.round}" if self.round is not None else "r?"
        who = f" [{self.entity}]" if self.entity else ""
        return (f"{self.kind}.{self.field} {r}{who}: "
                f"logged={self.logged!r} recomputed={self.recomputed!r}")


@dataclass
class Report:
    combat_checked: int = 0
    tier_checked: int = 0
    combat_unsupported: int = 0     # damage types the harness can't yet re-run
    diffs: List[Diff] = field(default_factory=list)

    @property
    def has_diffs(self) -> bool:
        return bool(self.diffs)


class _Target:
    """Minimal stand-in for a character/enemy: the damage functions only touch
    .wounds / .stuns / .health."""
    def __init__(self, wounds: int = 0, stuns: int = 0, health: int = 0):
        self.wounds = wounds
        self.stuns = stuns
        self.health = health


# ---------------------------------------------------------------------------
# Per-event checks
# ---------------------------------------------------------------------------
def check_combat_damage(event: Dict[str, Any]) -> List[Diff]:
    """Re-run the damage->wounds pipeline for a combat_action and diff it.

    The pre-state is reconstructed self-containedly from the logged after-state
    and the logged deltas (before_wounds = after_wounds - wounds_dealt,
    before_health = after_health + dealt), so each event is checked in isolation
    — no cross-event state folding, no dependence on the OLD formula being right.
    Only wound-type damage is re-run today; stun/mixed lack a broken-out
    stuns_dealt in the log, so they are reported as unsupported, not silently
    passed.
    """
    dmg = event.get("damage")
    if not isinstance(dmg, dict):
        return []
    dealt = dmg.get("dealt")
    if dealt is None:
        return []
    after = event.get("defender_state_after") or {}
    rnd = event.get("round")
    who = (event.get("defender") or {}).get("name") or (event.get("defender") or {}).get("id")

    dtype = dmg.get("damage_type", "wound")
    if dtype != "wound":
        # Signalled by the caller via a sentinel Diff-free marker; replay_events
        # counts these separately. Return empty here; aggregation handles it.
        return []

    wounds_dealt_logged = event.get("wounds_dealt")
    if wounds_dealt_logged is None:
        return []

    before_wounds = after.get("wounds", 0) - wounds_dealt_logged
    before_health = after.get("health", 0) + dealt
    target = _Target(wounds=before_wounds, health=before_health)

    result = apply_wound_damage(target, dealt)

    diffs: List[Diff] = []
    if result["wounds_dealt"] != wounds_dealt_logged:
        diffs.append(Diff("combat_damage", "wounds_dealt", wounds_dealt_logged,
                          result["wounds_dealt"], rnd, who))
    if "wounds" in after and target.wounds != after["wounds"]:
        diffs.append(Diff("combat_damage", "wounds_after", after["wounds"],
                          target.wounds, rnd, who))
    if "health" in after and target.health != after["health"]:
        diffs.append(Diff("combat_damage", "health_after", after["health"],
                          target.health, rnd, who))
    return diffs


def check_outcome_tier(event: Dict[str, Any]) -> List[Diff]:
    """Re-run margin -> outcome tier for an action_resolution and diff it."""
    roll = event.get("roll") or {}
    margin = roll.get("margin")
    logged_tier = roll.get("tier")
    if logged_tier is None or margin is None:
        return []  # non-rolled action (wait/free); nothing to verify

    recomputed = MechanicsEngine._determine_outcome_tier(None, margin).value  # self unused
    if recomputed != logged_tier:
        who = event.get("agent")
        return [Diff("outcome_tier", "tier", logged_tier, recomputed,
                     event.get("round"), who)]
    return []


# ---------------------------------------------------------------------------
# Aggregation + IO
# ---------------------------------------------------------------------------
def replay_events(events: List[Dict[str, Any]]) -> Report:
    report = Report()
    for e in events:
        et = e.get("event_type")
        if et == "combat_action":
            dmg = e.get("damage")
            if isinstance(dmg, dict) and dmg.get("dealt") is not None:
                if dmg.get("damage_type", "wound") != "wound":
                    report.combat_unsupported += 1
                    continue
                report.combat_checked += 1
                report.diffs.extend(check_combat_damage(e))
        elif et == "action_resolution":
            roll = e.get("roll") or {}
            if roll.get("tier") is not None and roll.get("margin") is not None:
                report.tier_checked += 1
                report.diffs.extend(check_outcome_tier(e))
    return report


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Token-free mechanics-diff harness.")
    ap.add_argument("sessions", nargs="+", help="session JSONL file(s)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    agg = Report()
    per_file = {}
    for path in args.sessions:
        rep = replay_events(load_jsonl(path))
        per_file[path] = rep
        agg.combat_checked += rep.combat_checked
        agg.tier_checked += rep.tier_checked
        agg.combat_unsupported += rep.combat_unsupported
        agg.diffs.extend(rep.diffs)

    if args.json:
        print(json.dumps({
            "combat_checked": agg.combat_checked,
            "tier_checked": agg.tier_checked,
            "combat_unsupported": agg.combat_unsupported,
            "diffs": [d.__dict__ for d in agg.diffs],
        }, indent=2))
    else:
        print(f"Checked {agg.combat_checked} combat damage + {agg.tier_checked} "
              f"outcome tiers across {len(args.sessions)} session(s).")
        if agg.combat_unsupported:
            print(f"  ({agg.combat_unsupported} non-wound damage event(s) not yet re-runnable)")
        if agg.diffs:
            print(f"\n✗ {len(agg.diffs)} DIFF(S) — current formulas diverge from the log:")
            for d in agg.diffs:
                print(f"  {d}")
        else:
            print("✓ No diffs — current formulas reproduce the logged outcomes exactly.")

    return 1 if agg.has_diffs else 0


if __name__ == "__main__":
    sys.exit(main())
