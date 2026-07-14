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

# YAGS: 6+ stuns is the Beaten/KO threshold. (Verified against 80k events: in
# character_state, wounds>=6 <=> death_state=='dead', exactly — but the checker
# reads death_state directly rather than re-deriving it from a threshold.)
STUN_KO = 6
# The hostile major_action values that ACTUALLY occur in the corpus (mined, not
# assumed). Cast/Ritual/Aim never appear as major_action — rituals route through
# action_type/is_ritual — so encoding them was fiction; Suppress is the one real
# hostile action an earlier draft missed. Enforced by test_schema_drift.py.
HOSTILE_ACTIONS = {"Attack", "Suppress"}


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
def _death_oracle(events):
    """Authoritative life-state, from the ONE self-consistent oracle
    (character_state) plus the authoritative lifecycle events. Returns:

      dead_round:  name -> first round the entity is truly DEAD (character_state
                   death_state=='dead', or enemy_defeat with reason killed/
                   unconscious for enemies that carry no character_state).
      defeated_tl: name -> sorted [(round, defeated: bool)] transitions, where
                   defeated = is_defeated or death_state in (dead, unconscious),
                   and a healing_applied that restores the target to alive is the
                   sanctioned revival.

    combat_action.defender_state_after is deliberately NOT consulted: it is a
    transient mid-round snapshot on a different wound scale, and every apparent
    contradiction it raised (17/17 checkable) was reconciled by the round-end
    character_state. See memory project_jsonl_authoritative_oracle."""
    dead_round: Dict[str, int] = {}
    tl: Dict[str, List[tuple]] = {}
    for e in events:
        t = e.get("event_type")
        b = _body(e)
        r = e.get("round")
        if t == "character_state":
            nm = b.get("character_name")
            ds = b.get("death_state")
            defeated = bool(b.get("is_defeated")) or ds in ("dead", "unconscious")
            tl.setdefault(nm, []).append((r or 0, defeated))
            if ds == "dead" and nm not in dead_round:
                dead_round[nm] = r
        elif t == "enemy_defeat":
            if b.get("defeat_reason") in ("killed", "unconscious"):
                nm = b.get("enemy_name")
                if nm and nm not in dead_round:
                    dead_round[nm] = r
        elif t == "healing_applied":
            if (b.get("target_state_after") or {}).get("alive"):
                nm = b.get("target_name")
                if nm:
                    tl.setdefault(nm, []).append((r or 0, False))  # revived
    for k in tl:
        # stable sort by round; a revival and a defeat logged in the same round
        # keep insertion order (heals are logged after the state that prompted them)
        tl[k].sort(key=lambda x: x[0])
    return dead_round, tl


def _defeated_at(tl, name, round) -> bool:
    """Was `name` defeated as of `round`, per the authoritative timeline?"""
    st = False
    for (rr, dv) in tl.get(name, []):
        if rr <= (round or 0):
            st = dv
        else:
            break
    return st


def inv_zombie_actor(events, cfg) -> List[Violation]:
    """A defeated entity must not act again until revived. The defeated state is
    read from the authoritative oracle (character_state / enemy_defeat, with
    healing_applied as revival) — never from combat_action's transient snapshot.
    Keyed off BOTH a hostile declared action AND actual combat damage: the
    declaration alone missed the real Hard Vane case (major_action logged None
    while he still shot). 'Defeated as of the prior round' avoids flagging the
    same-round killing/KO that is logged alongside its own resolution."""
    out: List[Violation] = []
    _, tl = _death_oracle(events)
    if not tl:
        return out
    for e in events:
        t = e.get("event_type")
        b = _body(e)
        r = e.get("round")
        if t == "combat_action":
            atk = (b.get("attacker") or {}).get("name")
            dealt = (b.get("damage") or {}).get("dealt") or 0
            if dealt > 0 and _defeated_at(tl, atk, (r or 0) - 1):
                out.append(Violation("zombie_actor", ERROR,
                    f"dealt {dealt} damage while defeated", r, atk))
        elif t == "action_declaration":
            nm = b.get("character_name")
            act = (b.get("action") or {}).get("major_action")
            if act in HOSTILE_ACTIONS and _defeated_at(tl, nm, (r or 0) - 1):
                out.append(Violation("zombie_actor", ERROR,
                    f"declared {act} while defeated", r, nm))
    return out


def inv_dead_targetable(events, cfg) -> List[Violation]:
    """Once an entity is *dead* (authoritative: character_state death_state=='dead'
    or enemy_defeat killed/unconscious) it must not take further damage. "Dead" is
    NOT merely 0 HP — health<=0 is *unconscious*, and a coup-de-grace on the
    unconscious is a legitimate finishing blow, so we do not flag that. Only
    damage in a round strictly AFTER the death round counts (the killing blow
    itself is not a re-hit)."""
    out: List[Violation] = []
    dead_round, _ = _death_oracle(events)
    if not dead_round:
        return out
    for e in events:
        if e.get("event_type") != "combat_action":
            continue
        b = _body(e)
        r = e.get("round")
        nm = (b.get("defender") or {}).get("name")
        dealt = (b.get("damage") or {}).get("dealt") or 0
        dr = dead_round.get(nm)
        if dr is not None and r is not None and r > dr and dealt > 0:
            out.append(Violation("dead_targetable", ERROR,
                f"took {dealt} damage after dying in r{dr}", r, nm))
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
def _restrained_state_at(events) -> Dict[str, List[tuple]]:
    """Reconstruct each entity's disposition timeline as a list of
    (round, restrained: bool) transitions, keyed by entity id AND name (either
    may be used to reference it later).

    Restrained = a prisoner/subdued NON-hostile state. Transitions are driven by
    the bidirectional entity_lifecycle machinery, so a jailbreak (prisoner -> enemy
    via npcs_escalated) correctly returns the entity to hostile:
      * enemy_spawn / enemies_spawned / npcs_escalated -> restrained=False
      * npc_spawn (prisoner disposition) / enemies_converted -> restrained=True
    """
    tl: Dict[str, List[tuple]] = {}

    def mark(key, r, restrained):
        if key:
            tl.setdefault(key, []).append((r or 0, restrained))

    for e in events:
        t = e.get("event_type")
        r = e.get("round") or 0
        b = _body(e)
        if t == "enemy_spawn":
            mark(b.get("enemy_id"), r, False)
            mark(b.get("enemy_name"), r, False)
        elif t == "npc_spawn":
            restrained = (b.get("disposition") == "prisoner")
            mark(b.get("agent_id") or b.get("npc_id"), r, restrained)
            mark(b.get("name"), r, restrained)
        elif t == "entity_lifecycle":
            # Lifecycle events are logged at END of round r, so the new state
            # takes effect from round r+1 — an entity that attacked DURING round r
            # (as an enemy) and was converted at its end is not retroactively a
            # prisoner for that round's action.
            for cid in (b.get("enemies_converted") or []):
                mark(cid, r + 1, True)    # enemy -> prisoner/NPC
            for cid in (b.get("npcs_escalated") or []):
                mark(cid, r + 1, False)   # jailbreak: prisoner/NPC -> enemy
    for key in tl:
        tl[key].sort()
    return tl


def _is_restrained(tl: Dict[str, List[tuple]], ref: str, round: int) -> bool:
    """Was the entity referenced by `ref` (id or name) in a restrained state as of
    `round`? Uses the most recent transition at or before that round."""
    seq = tl.get(ref)
    if not seq:
        return False
    state = False
    for (r, restrained) in seq:
        if r <= (round or 0):
            state = restrained
        else:
            break
    return state


def inv_config_prisoner_spawned_hostile(events, cfg) -> List[Violation]:
    """A config `initial_enemies` entry declared `disposition: prisoner` (or
    friendly/neutral) but the entity spawned as an armed hostile and/or opened
    fire in round 1 — i.e. the disposition directive was dropped at spawn
    (dm.py:2184). Config-authoritative: keyed off the declared disposition, not a
    name heuristic. This is the execution-probe spawn confound."""
    out: List[Violation] = []
    # Declared prisoner/friendly/neutral bases, minus the trailing "#N". The
    # spawner prepends the faction ("Subdued Operative #1" -> "Independent Subdued
    # Operative #1"), so match by substring on the declared base rather than
    # exact name.
    declared_bases = {}  # base -> disposition
    for ent in (cfg.get("initial_enemies") or []):
        disp = (ent.get("disposition") or "").lower()
        if disp in ("prisoner", "friendly", "neutral"):
            nm = ent.get("name") or ""
            declared_bases[nm.split(" #")[0].strip().lower()] = disp
    if not declared_bases:
        return out

    def declared_disp(name: str):
        low = (name or "").lower()
        for base, disp in declared_bases.items():
            if base and base in low:
                return disp
        return None

    for e in events:
        if e.get("event_type") != "enemy_spawn":
            continue
        b = _body(e)
        nm = b.get("enemy_name")
        disp = declared_disp(nm)
        if disp:
            wpns = [w.get("name") for w in ((b.get("stats") or {}).get("weapons") or [])]
            if wpns:
                out.append(Violation("config_prisoner_spawned_hostile", ERROR,
                    f"declared disposition={disp} but spawned as armed enemy with {wpns}", 0, nm))
    for e in events:
        if e.get("event_type") == "combat_action" and (e.get("round") or 0) == 1:
            b = _body(e)
            nm = (b.get("attacker") or {}).get("name")
            if declared_disp(nm) and ((b.get("damage") or {}).get("dealt") or 0) > 0:
                out.append(Violation("config_prisoner_spawned_hostile", ERROR,
                    "declared prisoner dealt combat damage in round 1", 1, nm))
    return out


def inv_restrained_hostile_action(events, cfg) -> List[Violation]:
    """An entity currently in a restrained/prisoner state (per the bidirectional
    disposition timeline) must not take a hostile/tactical action — the NPC
    whitelist is flee/hide/plead/comply/dialogue/assist/pass. A legitimate
    jailbreak (npcs_escalated back to enemy) returns it to hostile, so an attack
    AFTER escalation is fine and not flagged."""
    out: List[Violation] = []
    tl = _restrained_state_at(events)
    if not tl:
        return out
    for e in events:
        t = e.get("event_type")
        r = e.get("round")
        if t == "action_declaration":
            b = _body(e)
            ref_id, ref_nm = b.get("player_id"), b.get("character_name")
            act = (b.get("action") or {}).get("major_action")
            if act in HOSTILE_ACTIONS and \
                    (_is_restrained(tl, ref_id, r) or _is_restrained(tl, ref_nm, r)):
                out.append(Violation("restrained_hostile_action", ERROR,
                    f"restrained entity took tactical action {act}", r, ref_nm))
        elif t == "combat_action":
            b = _body(e)
            atk = b.get("attacker") or {}
            if ((b.get("damage") or {}).get("dealt") or 0) > 0 and \
                    (_is_restrained(tl, atk.get("id"), r) or _is_restrained(tl, atk.get("name"), r)):
                out.append(Violation("restrained_hostile_action", ERROR,
                    "restrained entity dealt combat damage", r, atk.get("name")))
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
    inv_dead_targetable,
    inv_defeat_flag_internal,
    inv_hp_bounds,
    inv_stun_no_recovery,
    inv_config_prisoner_spawned_hostile,
    inv_restrained_hostile_action,
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
