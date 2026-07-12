#!/usr/bin/env python3
"""Mechanics-diff harness — token-free formula verification.

Replay's real purpose is answering "did my formula change alter outcomes?"
without paying for LLM calls or fighting nondeterminism. This harness does that
directly: it re-runs the *current* pure mechanics functions over the mechanical
inputs already recorded in a session's events, and diffs the recomputed outcome
against what was logged. No LLM, no MockLLMProvider, no session engine — just the
math.

What it verifies (extensible):
  * combat_action (wound)  -> mechanics.apply_wound_damage
  * combat_action (stun)   -> mechanics.apply_stun_damage   (non-cumulative rule)
  * combat_action (mixed)  -> mechanics.apply_mixed_damage
  * action_resolution      -> MechanicsEngine._determine_outcome_tier

Each transition is evaluated INDEPENDENTLY — pre-state comes from the log, the
recomputed outcome is diffed, and then the *logged* after-state (ground truth)
is folded forward. A diff therefore never cascades into later checks, which is
what makes this sound where chained full-replay is not (divergence propagation).

Pre-state sourcing, in order of preference:
  * wound events carry their own deltas (wounds_dealt + dealt), so they are
    reconstructed self-containedly and never depend on state tracking;
  * stun/mixed events depend on prior stuns (YAGS non-cumulative rule), so the
    harness tracks running state per defender id: seeded from enemy_spawn,
    folded forward from each combat_action.defender_state_after and
    healing_applied.target_state_after. A first-seen entity is assumed fresh
    (stuns/wounds 0, health unknown -> health not diffed).

Because there is no LLM in the loop this is immune to the call-flow-alignment
problem that constrains full replay: it verifies formula/number changes only,
but exactly and for free over an entire corpus.

Usage:
    python scripts/mechanics_replay.py session.jsonl [session2.jsonl ...]
    python scripts/mechanics_replay.py --corpus multiagent_output/
    python scripts/mechanics_replay.py --json session.jsonl

Exit code is non-zero if any diff is found (so it can gate CI after a formula
edit). NOTE: on sessions recorded by OLDER code, diffs are expected and are a
mechanical changelog (e.g. pre-clamp sessions log negative health).
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from aeonisk.multiagent.mechanics import (
    MechanicsEngine,
    apply_mixed_damage,
    apply_stun_damage,
    apply_wound_damage,
    resolve_ko_check,
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
    ko_checked: int = 0
    combat_unsupported: int = 0     # events the harness can't (yet) re-run
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


@dataclass
class _Pre:
    """Known pre-state for an entity (folded from the log's own ground truth)."""
    wounds: int = 0
    stuns: int = 0
    health: Optional[int] = None   # None = unknown -> health not diffed


def _who(event: Dict[str, Any]) -> Optional[str]:
    d = event.get("defender") or {}
    return d.get("name") or d.get("id")


# ---------------------------------------------------------------------------
# Per-event checks
# ---------------------------------------------------------------------------
def check_combat_damage(event: Dict[str, Any], pre: Optional[_Pre] = None) -> List[Diff]:
    """Re-run the damage->wounds pipeline for a wound-type combat_action.

    When `pre` is None the pre-state is reconstructed self-containedly from the
    logged after-state and the logged deltas (before_wounds = after_wounds -
    wounds_dealt, before_health = after_health + dealt), so the check does not
    assume the OLD formula was right — it only assumes the log's own arithmetic.
    That reconstruction still catches clamp/formula divergences (e.g. a session
    logging health -5 where current code clamps at 0).
    """
    dmg = event.get("damage")
    if not isinstance(dmg, dict):
        return []
    dealt = dmg.get("dealt")
    if dealt is None:
        return []
    if (dmg.get("damage_type") or "wound") != "wound":
        return []
    after = event.get("defender_state_after") or {}
    rnd = event.get("round")
    who = _who(event)

    wounds_dealt_logged = event.get("wounds_dealt")
    if pre is None:
        if wounds_dealt_logged is None:
            return []  # nothing to reconstruct from
        pre = _Pre(wounds=after.get("wounds", 0) - wounds_dealt_logged,
                   health=after.get("health", 0) + dealt)

    target = _Target(wounds=pre.wounds, stuns=pre.stuns,
                     health=pre.health if pre.health is not None else 0)
    result = apply_wound_damage(target, dealt)

    diffs: List[Diff] = []
    if wounds_dealt_logged is not None and result["wounds_dealt"] != wounds_dealt_logged:
        diffs.append(Diff("combat_damage", "wounds_dealt", wounds_dealt_logged,
                          result["wounds_dealt"], rnd, who))
    if "wounds" in after and target.wounds != after["wounds"]:
        diffs.append(Diff("combat_damage", "wounds_after", after["wounds"],
                          target.wounds, rnd, who))
    if "health" in after and pre.health is not None and target.health != after["health"]:
        diffs.append(Diff("combat_damage", "health_after", after["health"],
                          target.health, rnd, who))
    return diffs


def check_stun_damage(event: Dict[str, Any], pre: _Pre) -> List[Diff]:
    """Re-run YAGS non-cumulative stun for a stun-type combat_action.

    Requires a known pre-state (prior stuns change the outcome), supplied by the
    caller's forward-fold. Pure stun touches neither wounds nor health, so only
    stuns_after is diffed.
    """
    dealt = (event.get("damage") or {}).get("dealt")
    after = event.get("defender_state_after") or {}
    if dealt is None or "stuns" not in after:
        return []

    target = _Target(wounds=pre.wounds, stuns=pre.stuns, health=pre.health or 0)
    apply_stun_damage(target, dealt)

    if target.stuns != after["stuns"]:
        return [Diff("combat_damage", "stuns_after", after["stuns"], target.stuns,
                     event.get("round"), _who(event))]
    return []


def check_mixed_damage(event: Dict[str, Any], pre: _Pre) -> List[Diff]:
    """Re-run YAGS mixed (split stun/wound) damage for a mixed-type combat_action."""
    dealt = (event.get("damage") or {}).get("dealt")
    after = event.get("defender_state_after") or {}
    if dealt is None:
        return []
    rnd = event.get("round")
    who = _who(event)

    target = _Target(wounds=pre.wounds, stuns=pre.stuns,
                     health=pre.health if pre.health is not None else 0)
    apply_mixed_damage(target, dealt)

    diffs: List[Diff] = []
    if "stuns" in after and target.stuns != after["stuns"]:
        diffs.append(Diff("combat_damage", "stuns_after", after["stuns"],
                          target.stuns, rnd, who))
    if "wounds" in after and target.wounds != after["wounds"]:
        diffs.append(Diff("combat_damage", "wounds_after", after["wounds"],
                          target.wounds, rnd, who))
    if "health" in after and pre.health is not None and target.health != after["health"]:
        diffs.append(Diff("combat_damage", "health_after", after["health"],
                          target.health, rnd, who))
    return diffs


def check_ko_check(event: Dict[str, Any]) -> List[Diff]:
    """Re-run the Beaten/Fatal consciousness check for a ko_check event.

    The event carries its own inputs (stuns/wounds/health_attr) AND the rolled
    d20, so resolve_ko_check re-runs deterministically — dc, total, can_act and
    status are all recomputed and diffed.
    """
    needed = ("stuns", "wounds", "health_attr", "roll")
    if any(event.get(k) is None for k in needed):
        return []
    result = resolve_ko_check(event["stuns"], event["wounds"],
                              event["health_attr"], roll=event["roll"])
    rnd = event.get("round")
    who = event.get("name") or event.get("agent_id")

    diffs: List[Diff] = []
    for fld in ("dc", "total", "can_act", "status"):
        if fld in event and event[fld] != result[fld]:
            diffs.append(Diff("ko_check", fld, event[fld], result[fld], rnd, who))
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
def _fold(states: Dict[str, _Pre], eid: Optional[str], after: Dict[str, Any]) -> None:
    """Fold a logged after-state (ground truth) into the running state."""
    if not eid or not after:
        return
    cur = states.get(eid) or _Pre()
    states[eid] = _Pre(
        wounds=after.get("wounds", cur.wounds),
        stuns=after.get("stuns", cur.stuns),
        health=after.get("health", cur.health),
    )


def replay_events(events: List[Dict[str, Any]]) -> Report:
    report = Report()
    states: Dict[str, _Pre] = {}

    for e in events:
        et = e.get("event_type")

        if et == "enemy_spawn":
            eid = e.get("enemy_id")
            if eid:
                states[eid] = _Pre(0, 0, (e.get("stats") or {}).get("health"))

        elif et == "healing_applied":
            _fold(states, e.get("target_id"), e.get("target_state_after") or {})

        elif et == "combat_action":
            dmg = e.get("damage")
            did = (e.get("defender") or {}).get("id")
            after = e.get("defender_state_after") or {}
            if isinstance(dmg, dict) and dmg.get("dealt") is not None:
                dtype = dmg.get("damage_type") or "wound"
                pre = states.get(did)
                if dtype == "wound":
                    report.combat_checked += 1
                    # self-contained reconstruction is the robust default; the
                    # folded state only enables old-schema events w/o wounds_dealt
                    if e.get("wounds_dealt") is not None:
                        report.diffs.extend(check_combat_damage(e))
                    elif pre is not None:
                        report.diffs.extend(check_combat_damage(e, pre))
                    else:
                        report.combat_checked -= 1
                        report.combat_unsupported += 1
                elif dtype == "stun":
                    report.combat_checked += 1
                    report.diffs.extend(check_stun_damage(e, pre or _Pre()))
                elif dtype == "mixed":
                    report.combat_checked += 1
                    report.diffs.extend(check_mixed_damage(e, pre or _Pre()))
                else:
                    report.combat_unsupported += 1
            # always fold logged ground truth forward (a diff must not cascade)
            _fold(states, did, after)

        elif et == "ko_check":
            if e.get("roll") is not None:
                report.ko_checked += 1
                report.diffs.extend(check_ko_check(e))

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


def replay_paths(paths: List[str]) -> Dict[str, Report]:
    """Run the harness over many session files; per-file reports, insertion order."""
    return {p: replay_events(load_jsonl(p)) for p in paths}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Token-free mechanics-diff harness.")
    ap.add_argument("sessions", nargs="*", help="session JSONL file(s)")
    ap.add_argument("--corpus", metavar="DIR", action="append", default=[],
                    help="also check every *.jsonl under DIR (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    paths = list(args.sessions)
    for d in args.corpus:
        paths.extend(sorted(glob.glob(str(Path(d) / "*.jsonl"))))
    if not paths:
        ap.error("no sessions given (positional files and/or --corpus DIR)")

    per_file = replay_paths(paths)
    agg = Report()
    for rep in per_file.values():
        agg.combat_checked += rep.combat_checked
        agg.tier_checked += rep.tier_checked
        agg.ko_checked += rep.ko_checked
        agg.combat_unsupported += rep.combat_unsupported
        agg.diffs.extend(rep.diffs)

    if args.json:
        print(json.dumps({
            "combat_checked": agg.combat_checked,
            "tier_checked": agg.tier_checked,
            "combat_unsupported": agg.combat_unsupported,
            "files": {p: {"combat_checked": r.combat_checked,
                          "tier_checked": r.tier_checked,
                          "combat_unsupported": r.combat_unsupported,
                          "diffs": [d.__dict__ for d in r.diffs]}
                      for p, r in per_file.items()},
        }, indent=2))
        return 1 if agg.has_diffs else 0

    # per-file table (only rows with something checked or diffed)
    for p, r in per_file.items():
        if not (r.combat_checked or r.tier_checked or r.ko_checked or r.diffs):
            continue
        tag = "clean" if not r.has_diffs else f"{len(r.diffs)} DIFF(S)"
        print(f"  combat={r.combat_checked:3} tier={r.tier_checked:4} "
              f"ko={r.ko_checked:2} unsup={r.combat_unsupported:2}  "
              f"{tag:12s} {Path(p).name}")
        for d in r.diffs:
            print(f"      {d}")

    print(f"\nChecked {agg.combat_checked} combat damage + {agg.tier_checked} "
          f"outcome tiers + {agg.ko_checked} KO checks across {len(paths)} session(s).")
    if agg.combat_unsupported:
        print(f"  ({agg.combat_unsupported} event(s) not re-runnable: unknown damage "
              f"type or no wounds_dealt/pre-state)")
    if agg.diffs:
        print(f"✗ {len(agg.diffs)} diff(s) — current formulas diverge from the log "
              f"(expected on sessions recorded by older code).")
    else:
        print("✓ No diffs — current formulas reproduce the logged outcomes exactly.")

    return 1 if agg.has_diffs else 0


if __name__ == "__main__":
    sys.exit(main())
