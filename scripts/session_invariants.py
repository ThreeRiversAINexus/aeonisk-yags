"""Session-invariant checker — cross-event / cross-subsystem rules over the
typed JSONL event stream.

Motivation
----------
Unit tests verify that individual functions return the right value for an input.
But the bugs we keep finding by reading transcripts live in the *seams*: three
locally-correct subsystems that disagree with each other across a whole session.
A stun-KO'd player whose `death_state` says "unconscious" while the turn engine
keeps letting him shoot; a "subdued prisoner" that the spawner correctly builds
as an armed Grunt because the scenario constraint never reached it; a 0-HP enemy
that stays targetable because nothing set its defeat flag. Every function is
right; the trajectory is wrong. No unit test sees that.

This module asserts the invariants that must hold *across* events, using only
typed fields (never narration — same rule as scripts/session_extract.py). Run it
as a post-session gate in the bulk runner: an ERROR-severity violation means the
session's mechanical record is self-contradictory and any dataset built from it
is contaminated.

Design rules
------------
* Typed fields only. If a rule can't be stated over structured fields, it doesn't
  belong here — it belongs to the human/LLM-judge lens (semantic failures:
  mis-adjudication, confabulation, mechanics-leak). This checker is deliberately
  the *structural* half, not the whole quality story.
* No false positives. A checker that cries wolf gets ignored exactly like the
  keyword analysis did. Every ERROR must be a genuine contradiction; softer or
  heuristic signals are WARN.

CLI
---
    python scripts/session_invariants.py <session.jsonl | dir> [...] \
        [--json manifest.json] [--warn] [--quiet]

Exit code is non-zero if any ERROR-severity violation is found (so it gates CI /
the bulk runner). --warn also surfaces WARN-severity findings.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# Reuse the sanctioned typed accessors. Ensure the repo root is importable
# whether this runs as `python scripts/session_invariants.py` or is imported.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from scripts.session_extract import (  # noqa: E402
    load, is_complete, config_of, players, rulings,
)

ERROR = "error"
WARN = "warn"

# Names that signal an entity is meant to be incapacitated/surrendered.
_SUBDUED_MARKERS = ("subdued", "prisoner", "surrender", "captive", "kneel", "restrained")
# YAGS: 6+ stuns is the Beaten/KO threshold; 6+ wounds is death.
STUN_KO = 6
WOUND_DEATH = 6
# Actions a converted prisoner-NPC may take (CLAUDE.md NPC whitelist).
_NPC_ALLOWED = {"flee", "hide", "plead", "comply", "dialogue", "assist", "pass", None}
_REAL_ACTIONS = {"Attack", "Cast", "Ritual", "Aim"}


@dataclass
class Violation:
    invariant: str
    severity: str
    message: str
    round: Optional[int] = None
    entity: Optional[str] = None

    def __str__(self) -> str:
        r = f"r{self.round}" if self.round is not None else "r?"
        who = f" [{self.entity}]" if self.entity else ""
        return f"{self.severity.upper():5s} {self.invariant:26s} {r}{who}: {self.message}"


def _body(e: dict) -> dict:
    d = e.get("data")
    return d if isinstance(d, dict) else e


def ids(violations: List[Violation]) -> List[str]:
    return [v.invariant for v in violations]


# ---------------------------------------------------------------------------
# Life-state consistency
# ---------------------------------------------------------------------------
def inv_zombie_actor(events, cfg) -> List[Violation]:
    """A defeated entity must not act again until revived. Keyed off BOTH the
    declared action AND actual combat damage — the declaration alone missed the
    real Hard Vane case (his major_action logged None while he still shot)."""
    out: List[Violation] = []
    defeated_since: Dict[str, int] = {}
    for e in events:
        t = e.get("event_type")
        r = e.get("round") or 0
        if t == "character_state":
            b = _body(e)
            n = b.get("character_name")
            if b.get("is_defeated") or b.get("death_state") in ("unconscious", "dead"):
                defeated_since.setdefault(n, r)
            else:
                defeated_since.pop(n, None)  # revived
        elif t == "combat_action":
            b = _body(e)
            atk = (b.get("attacker") or {}).get("name")
            dealt = (b.get("damage") or {}).get("dealt") or 0
            since = defeated_since.get(atk)
            if since is not None and since < r and dealt > 0:
                out.append(Violation("zombie_actor", ERROR,
                    f"dealt {dealt} damage while defeated since r{since}", r, atk))
        elif t == "action_declaration":
            b = _body(e)
            n = b.get("character_name")
            act = (b.get("action") or {}).get("major_action")
            since = defeated_since.get(n)
            if since is not None and since < r and act in _REAL_ACTIONS:
                out.append(Violation("zombie_actor", ERROR,
                    f"declared {act} while defeated since r{since}", r, n))
    return out


def inv_defeat_state_disagreement(events, cfg) -> List[Violation]:
    """combat_action.defender_state_after must not report an entity as able to
    act (`status` active/conscious) while it is simultaneously *dead* — either
    `alive=False` or past the wound-death threshold.

    Scoped deliberately narrow. An earlier draft fired on `alive=True` at
    stuns>=6; that was wrong — the engine's own rule is that a stun-KO'd entity
    IS alive (just unconscious), so alive=True there is correct. The genuine
    contradiction is a *dead* entity still marked active. We do NOT flag stun-KO
    here (the *behavioral* consequence — a KO'd entity still acting — is caught
    by inv_zombie_actor instead, which keys off actions, not labels)."""
    out: List[Violation] = []
    active = {"active", "conscious"}
    for e in events:
        if e.get("event_type") != "combat_action":
            continue
        b = _body(e)
        st = b.get("defender_state_after") or {}
        if st.get("status") not in active:
            continue
        nm = (b.get("defender") or {}).get("name")
        r = e.get("round")
        wounds = st.get("wounds")
        if st.get("alive") is False:
            out.append(Violation("defeat_state_disagreement", ERROR,
                f"status={st.get('status')!r} but alive=False", r, nm))
        elif isinstance(wounds, (int, float)) and wounds >= WOUND_DEATH:
            out.append(Violation("defeat_state_disagreement", ERROR,
                f"status={st.get('status')!r} at wounds={wounds} (>= {WOUND_DEATH} death)", r, nm))
    return out


def inv_dead_targetable(events, cfg) -> List[Violation]:
    """Once an entity is *dead* it must not take further damage. "Dead" means the
    death threshold — wounds>=6 or status/death 'dead' — NOT merely 0 HP. In YAGS
    (and this engine's own death logic) health<=0 is *unconscious*, and finishing
    an unconscious foe is a legitimate coup-de-grace, so we do not flag that."""
    out: List[Violation] = []
    dead_since: Dict[str, int] = {}
    for e in events:
        if e.get("event_type") != "combat_action":
            continue
        b = _body(e)
        r = e.get("round")
        d = b.get("defender") or {}
        did = d.get("id") or d.get("name")
        st = b.get("defender_state_after") or {}
        wounds = st.get("wounds")
        dealt = (b.get("damage") or {}).get("dealt") or 0
        if did in dead_since and dealt > 0:
            out.append(Violation("dead_targetable", ERROR,
                f"took {dealt} damage after dying in r{dead_since[did]}", r, d.get("name")))
        if (isinstance(wounds, (int, float)) and wounds >= WOUND_DEATH) \
                or st.get("status") == "dead" or st.get("death_state") == "dead":
            dead_since.setdefault(did, r)
    return out


def inv_defeat_flag_internal(events, cfg) -> List[Violation]:
    """Within a single character_state, is_defeated must equal
    (death_state != 'alive'). Catches the snapshot contradicting itself."""
    out: List[Violation] = []
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        b = _body(e)
        ds = b.get("death_state")
        isd = b.get("is_defeated")
        if ds is None or isd is None:
            continue
        if isd != (ds != "alive"):
            out.append(Violation("defeat_flag_internal", ERROR,
                f"is_defeated={isd} but death_state={ds!r}", e.get("round"),
                b.get("character_name")))
    return out


def inv_hp_bounds(events, cfg) -> List[Violation]:
    """health must not exceed max_health; wounds/stuns not negative."""
    out: List[Violation] = []
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        b = _body(e)
        h, mx = b.get("health"), b.get("max_health")
        nm, r = b.get("character_name"), e.get("round")
        if isinstance(h, (int, float)) and isinstance(mx, (int, float)) and mx and h > mx:
            out.append(Violation("hp_exceeds_max", WARN, f"health {h} > max {mx}", r, nm))
        for fld in ("wounds", "stuns"):
            v = b.get(fld)
            if isinstance(v, (int, float)) and v < 0:
                out.append(Violation("hp_exceeds_max", WARN, f"{fld}={v} < 0", r, nm))
    return out


def inv_stun_no_recovery(events, cfg) -> List[Violation]:
    """A KO'd entity (stuns>=6) whose stun count never decreases across >=3
    consecutive snapshots — stuns should recover over time in YAGS. WARN because
    it can only fire once `stuns` is logged (post-fix sessions)."""
    out: List[Violation] = []
    hist: Dict[str, List[int]] = {}
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        b = _body(e)
        s = b.get("stuns")
        if isinstance(s, (int, float)):
            hist.setdefault(b.get("character_name"), []).append(int(s))
    for nm, seq in hist.items():
        run = 1
        for i in range(1, len(seq)):
            if seq[i] >= STUN_KO and seq[i] >= seq[i - 1]:
                run += 1
                if run >= 3:
                    out.append(Violation("stun_no_recovery", WARN,
                        f"stuns stuck >= {STUN_KO} for {run} snapshots ({seq})", None, nm))
                    break
            else:
                run = 1
    return out


# ---------------------------------------------------------------------------
# Entity lifecycle / spawn constraints
# ---------------------------------------------------------------------------
def _is_subdued_name(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in _SUBDUED_MARKERS)


def inv_prisoner_armed(events, cfg) -> List[Violation]:
    """An entity framed as subdued/surrendered/prisoner must not spawn holding
    weapons — the scenario's 'weapons kicked away' constraint failed to reach the
    spawner."""
    out: List[Violation] = []
    for e in events:
        if e.get("event_type") != "enemy_spawn":
            continue
        b = _body(e)
        nm = b.get("enemy_name") or ""
        if not _is_subdued_name(nm):
            continue
        wpns = [w.get("name") for w in ((b.get("stats") or {}).get("weapons") or [])]
        if wpns:
            out.append(Violation("prisoner_armed", ERROR,
                f"spawned subdued but armed with {wpns}", 0, nm))
    return out


def inv_prisoner_attacks(events, cfg) -> List[Violation]:
    """A subdued/prisoner-framed entity must not declare Attack or deal combat
    damage (they should already be incapacitated)."""
    out: List[Violation] = []
    subdued_ids, subdued_names = set(), set()
    for e in events:
        if e.get("event_type") == "enemy_spawn":
            b = _body(e)
            if _is_subdued_name(b.get("enemy_name")):
                subdued_ids.add(b.get("enemy_id"))
                subdued_names.add(b.get("enemy_name"))
    if not subdued_ids and not subdued_names:
        return out
    for e in events:
        t = e.get("event_type")
        r = e.get("round")
        if t == "action_declaration":
            b = _body(e)
            if (b.get("player_id") in subdued_ids or b.get("character_name") in subdued_names) \
                    and (b.get("action") or {}).get("major_action") == "Attack":
                out.append(Violation("prisoner_attacks", ERROR,
                    "subdued entity declared Attack", r, b.get("character_name")))
        elif t == "combat_action":
            b = _body(e)
            atk = b.get("attacker") or {}
            if (atk.get("id") in subdued_ids or atk.get("name") in subdued_names) \
                    and ((b.get("damage") or {}).get("dealt") or 0) > 0:
                out.append(Violation("prisoner_attacks", ERROR,
                    "subdued entity dealt combat damage", r, atk.get("name")))
    return out


def inv_npc_tactical_action(events, cfg) -> List[Violation]:
    """An entity converted to a prisoner/NPC (entity_lifecycle.enemies_converted)
    must not subsequently take a tactical action — the NPC whitelist is
    flee/hide/plead/comply/dialogue/assist/pass."""
    out: List[Violation] = []
    converted: Dict[str, int] = {}  # id -> round converted
    for e in events:
        t = e.get("event_type")
        r = e.get("round") or 0
        if t == "entity_lifecycle":
            for cid in (_body(e).get("enemies_converted") or []):
                converted.setdefault(cid, r)
        elif t == "action_declaration":
            b = _body(e)
            pid = b.get("player_id")
            act = (b.get("action") or {}).get("major_action")
            since = converted.get(pid)
            if since is not None and since <= r and act not in _NPC_ALLOWED and act in _REAL_ACTIONS:
                out.append(Violation("npc_tactical_action", ERROR,
                    f"converted NPC took tactical action {act} (converted r{since})",
                    r, b.get("character_name")))
    return out


# ---------------------------------------------------------------------------
# Economy / combat math
# ---------------------------------------------------------------------------
def inv_void_bounds(events, cfg) -> List[Violation]:
    """void_score must stay in [0, 10]."""
    out: List[Violation] = []
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        b = _body(e)
        v = b.get("void_score")
        if isinstance(v, (int, float)) and not (0 <= v <= 10):
            out.append(Violation("void_out_of_bounds", ERROR,
                f"void_score={v} outside [0,10]", e.get("round"), b.get("character_name")))
    return out


def inv_damage_nonneg(events, cfg) -> List[Violation]:
    out: List[Violation] = []
    for e in events:
        if e.get("event_type") != "combat_action":
            continue
        b = _body(e)
        dealt = (b.get("damage") or {}).get("dealt")
        if isinstance(dealt, (int, float)) and dealt < 0:
            out.append(Violation("damage_negative", ERROR,
                f"combat dealt={dealt}", e.get("round"),
                (b.get("defender") or {}).get("name")))
    return out


def inv_soulcredit_ledger(events, cfg) -> List[Violation]:
    """Under enforce, the magistrate is the sole ledger writer: a player's
    per-round soulcredit change should equal the sum of that round's applied
    rulings for them. Divergence means a second writer (narrator) or a dropped
    ruling. WARN (skips non-enforce and sessions without both signals)."""
    out: List[Violation] = []
    pnames = players(cfg) if cfg else set()
    if not pnames:
        return out
    # applied SC delta per (round, name)
    delta: Dict[tuple, int] = {}
    saw_enforce = False
    for e in events:
        if e.get("event_type") != "post_resolution_adjudication":
            continue
        b = _body(e)
        if b.get("regime") == "enforce":
            saw_enforce = True
        r = e.get("round")
        for ru in b.get("applied", []) or []:
            if not ru.get("applied"):
                continue
            nm = ru.get("character_name")
            if nm in pnames:
                delta[(r, nm)] = delta.get((r, nm), 0) + (ru.get("soulcredit_delta") or 0)
    if not saw_enforce:
        return out
    # observed SC per (round, name) from character_state
    obs: Dict[str, List[tuple]] = {}
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        b = _body(e)
        nm = b.get("character_name")
        if nm in pnames and isinstance(b.get("soulcredit"), (int, float)):
            obs.setdefault(nm, []).append((e.get("round"), b.get("soulcredit")))
    for nm, seq in obs.items():
        seq.sort(key=lambda x: (x[0] is None, x[0]))
        for i in range(1, len(seq)):
            (_, prev), (r, cur) = seq[i - 1], seq[i]
            observed = cur - prev
            ruled = delta.get((r, nm), 0)
            if observed != ruled:
                out.append(Violation("soulcredit_ledger_mismatch", WARN,
                    f"SC moved {observed:+d} but applied rulings sum {ruled:+d}", r, nm))
    return out


def inv_round_contiguous(events, cfg) -> List[Violation]:
    """Round numbers on round_start events should be contiguous 1..N."""
    rs = sorted({e.get("round") for e in events
                 if e.get("event_type") == "round_start" and e.get("round")})
    out: List[Violation] = []
    for a, b in zip(rs, rs[1:]):
        if b != a + 1:
            out.append(Violation("round_gap", WARN, f"round {a} -> {b} (gap)", b))
    return out


# ---------------------------------------------------------------------------
# Registry + driver
# ---------------------------------------------------------------------------
CHECKS: List[Callable] = [
    inv_zombie_actor,
    inv_defeat_state_disagreement,
    inv_dead_targetable,
    inv_defeat_flag_internal,
    inv_hp_bounds,
    inv_stun_no_recovery,
    inv_prisoner_armed,
    inv_prisoner_attacks,
    inv_npc_tactical_action,
    inv_void_bounds,
    inv_damage_nonneg,
    inv_soulcredit_ledger,
    inv_round_contiguous,
]


def check(events: List[dict], config: Optional[dict] = None) -> List[Violation]:
    """Run every invariant over a loaded event list. Returns all violations."""
    out: List[Violation] = []
    for fn in CHECKS:
        try:
            out.extend(fn(events, config or {}))
        except Exception as exc:  # a broken check must not mask others
            out.append(Violation(fn.__name__, WARN, f"checker crashed: {exc!r}"))
    return out


def check_file(path: str) -> List[Violation]:
    return check(load(path), config_of(path))


def has_errors(violations: List[Violation]) -> bool:
    return any(v.severity == ERROR for v in violations)


def _iter_sessions(paths: List[str]):
    for p in paths:
        if os.path.isdir(p):
            yield from sorted(glob.glob(f"{p}/**/session_*.jsonl", recursive=True))
        else:
            yield p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_out = None
    show_warn = "--warn" in argv
    quiet = "--quiet" in argv
    if "--json" in argv:
        i = argv.index("--json")
        json_out = argv[i + 1]
        del argv[i:i + 2]
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__.strip().splitlines()[0])
        print("usage: session_invariants.py <session.jsonl | dir> [...] "
              "[--json manifest.json] [--warn] [--quiet]")
        return 2

    from collections import defaultdict
    tally = defaultdict(int)
    manifest, total, dirty, err_sessions = [], 0, 0, 0
    for s in _iter_sessions(paths):
        ev = load(s)
        if not is_complete(ev):
            continue
        total += 1
        vs = check(ev, config_of(s))
        vs = [v for v in vs if show_warn or v.severity == ERROR]
        if not vs:
            continue
        dirty += 1
        if has_errors(vs):
            err_sessions += 1
        for v in vs:
            tally[v.invariant] += 1
        manifest.append({"session": s, "violations": [
            {"invariant": v.invariant, "severity": v.severity, "round": v.round,
             "entity": v.entity, "message": v.message} for v in vs]})
        if not quiet:
            print(f"\n{s}")
            for v in vs:
                print(f"  {v}")

    print(f"\n{'='*60}")
    print(f"Scanned {total} complete sessions: {dirty} with findings, "
          f"{err_sessions} with ERROR-severity.")
    for inv in sorted(tally, key=lambda k: -tally[k]):
        print(f"  {inv:28s} {tally[inv]:4d}")
    if json_out:
        with open(json_out, "w") as fh:
            json.dump({"total": total, "dirty": dirty, "error_sessions": err_sessions,
                       "tally": dict(tally), "sessions": manifest}, fh, indent=2)
        print(f"\nmanifest -> {json_out}")
    return 1 if err_sessions else 0


if __name__ == "__main__":
    sys.exit(main())
