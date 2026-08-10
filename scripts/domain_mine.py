"""Distil the session corpus into a small committed snapshot of real inputs.

Why a snapshot and not the corpus: `multiagent_output/` and `bulk_output/` are
gitignored (`.gitignore:161-162`) and get cleared. Nothing durable can depend on
them. Mining is a **harvest** — read whatever sessions exist right now, keep the
distillation, let the sessions go.

Two rules follow, and both are tested:

* **Merge is the default.** If a harvest replaced the snapshot, then harvesting
  and later clearing `bulk_output/` would destroy every domain only that batch
  had seen. `--replace` exists but has to be asked for.
* **Provenance travels with the sample.** A tuple outlives its session file, so
  it carries the commit that produced it. 37% of the corpus was recorded from a
  `-dirty` tree, where the commit does not identify the code that ran.

What comes out is deliberately two different things:

* **joint tuples** — real co-occurring `(health, wounds, stuns)`, which is what
  the damage functions consume. `schema_mine.py` gives per-field *marginals*,
  and marginals cannot say which values occurred together.
* **oracle rows** — `ko_check` records every input AND every output including
  the injected roll, so the expected value is the engine's own answer rather
  than an invariant someone invented. Those stay whole, never reduced to tuples.

Usage
-----
    python scripts/domain_mine.py --out tests/fixtures/domains/domain_corpus.json
    python scripts/domain_mine.py --replace --out <path>     # discards coverage
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schema_mine import iter_session_files  # noqa: E402
from session_extract import (  # noqa: E402
    body_states, damage_applications, healing_applications, ko_check_rows,
    load, provenance,
)

SCHEMA_VERSION = "1.0.0"
DEFAULT_ROOTS = ["multiagent_output", "bulk_output"]
DEFAULT_OUT = "tests/fixtures/domains/domain_corpus.json"

# Fields whose numeric envelope bounds extrapolation. "We have never seen this"
# becomes a measured fact instead of an assumption.
_NUMERIC_DOMAINS = ("health", "max_health", "wounds", "stuns", "void_score",
                    "soulcredit")


def _empty() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        # Sessions are identified, not tallied. Incrementing a counter made a
        # re-harvest of the same 330 files report 660 sessions, which would have
        # the snapshot overstate the evidence behind it.
        "provenance": {"sessions": 0, "dirty_sessions": 0, "session_ids": [],
                       "dirty_session_ids": [], "commits": {}, "roots": [],
                       "generated_at": None},
        "samples": {"body_states": [], "damage": [], "healing": [],
                    "ko_check": []},
        "domains": {},
    }


def _observe(domains: dict, field: str, value) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        return
    d = domains.setdefault(field, {"min": value, "max": value})
    d["min"] = min(d["min"], value)
    d["max"] = max(d["max"], value)


def harvest_events(sessions) -> dict:
    """Build a snapshot from an iterable of event lists (one per session)."""
    snap = _empty()
    samples = snap["samples"]
    prov = snap["provenance"]
    body_seen, damage_seen, healing_seen, ko_seen = set(), set(), set(), set()
    ids_seen, dirty_seen = set(), set()

    for events in sessions:
        events = list(events)
        pv = provenance(events)
        # Fall back to object identity when a fixture has no session_start, so
        # anonymous extracts still count once each rather than collapsing.
        sid = pv["session"] or f"anon:{id(events)}"
        if sid not in ids_seen:
            ids_seen.add(sid)
            prov["session_ids"].append(sid)
        if pv["dirty"] and sid not in dirty_seen:
            dirty_seen.add(sid)
            prov["dirty_session_ids"].append(sid)
        if pv["git_commit"]:
            entry = prov["commits"].setdefault(pv["git_commit"], {"session_ids": []})
            if sid not in entry["session_ids"]:
                entry["session_ids"].append(sid)

        for row in body_states(events):
            key = (row["health"], row["wounds"], row["stuns"])
            for field in _NUMERIC_DOMAINS:
                _observe(snap["domains"], field, row.get(field))
            if key not in body_seen:
                body_seen.add(key)
                samples["body_states"].append(list(key))

        for row in damage_applications(events):
            key = (row["dealt"], row["damage_type"],
                   row["pre"].get("wounds"), row["pre"].get("health"))
            _observe(snap["domains"], "dealt", row["dealt"])
            if key not in damage_seen:
                damage_seen.add(key)
                samples["damage"].append({
                    "dealt": row["dealt"], "damage_type": row["damage_type"],
                    "pre": row["pre"], "wounds_dealt": row["wounds_dealt"]})

        for row in healing_applications(events):
            key = (row["heal_type"], row["amount"], row["hp_restored"],
                   row["stun_removed"], row["wounds_reduced"])
            _observe(snap["domains"], "heal_amount", row["amount"])
            if key not in healing_seen:
                healing_seen.add(key)
                samples["healing"].append({
                    "heal_type": row["heal_type"], "amount": row["amount"],
                    "hp_restored": row["hp_restored"],
                    "stun_removed": row["stun_removed"],
                    "wounds_reduced": row["wounds_reduced"],
                    "after": row["after"]})

        for row in ko_check_rows(events):
            # Kept whole: inputs and the engine's recorded answer travel together.
            key = (row["stuns"], row["wounds"], row["health_attr"], row["roll"])
            if key not in ko_seen:
                ko_seen.add(key)
                samples["ko_check"].append({
                    "stuns": row["stuns"], "wounds": row["wounds"],
                    "health_attr": row["health_attr"], "roll": row["roll"],
                    "dc": row["dc"], "total": row["total"],
                    "can_act": row["can_act"], "status": row["status"],
                    "git_commit": pv["git_commit"], "dirty": pv["dirty"]})

    _recount(prov)
    return snap


def _key_of(kind: str, row):
    if kind == "body_states":
        return tuple(row)
    if kind == "damage":
        return (row["dealt"], row["damage_type"],
                (row.get("pre") or {}).get("wounds"),
                (row.get("pre") or {}).get("health"))
    if kind == "healing":
        return (row["heal_type"], row["amount"], row["hp_restored"],
                row["stun_removed"], row["wounds_reduced"])
    return (row["stuns"], row["wounds"], row["health_attr"], row["roll"])


def merge_snapshots(base: dict, incoming: dict) -> dict:
    """Union of two snapshots. Never subtracts.

    This is what makes clearing a corpus directory safe: coverage from a batch
    that no longer exists on disk stays in the snapshot forever.
    """
    out = json.loads(json.dumps(base))
    for kind, rows in incoming.get("samples", {}).items():
        existing = out["samples"].setdefault(kind, [])
        seen = {_key_of(kind, r) for r in existing}
        for row in rows:
            key = _key_of(kind, row)
            if key not in seen:
                seen.add(key)
                existing.append(row)

    for field, d in incoming.get("domains", {}).items():
        cur = out["domains"].setdefault(field, dict(d))
        cur["min"] = min(cur["min"], d["min"])
        cur["max"] = max(cur["max"], d["max"])

    bp, ip = out["provenance"], incoming.get("provenance", {})
    for key in ("session_ids", "dirty_session_ids"):
        bp[key] = sorted(set(bp.get(key) or []) | set(ip.get(key) or []))
    for commit, entry in ip.get("commits", {}).items():
        cur = bp["commits"].setdefault(commit, {"session_ids": []})
        cur["session_ids"] = sorted(
            set(cur.get("session_ids") or []) | set(entry.get("session_ids") or []))
    bp["roots"] = sorted(set(bp.get("roots") or []) | set(ip.get("roots") or []))
    _recount(bp)
    return out


def _recount(prov: dict) -> None:
    """Counts are derived from the identified sets, never incremented."""
    prov["sessions"] = len(prov.get("session_ids") or [])
    prov["dirty_sessions"] = len(prov.get("dirty_session_ids") or [])
    for entry in prov.get("commits", {}).values():
        entry["sessions"] = len(entry.get("session_ids") or [])


def build_snapshot(snap: dict) -> str:
    """Serialise deterministically — an unchanged harvest must not churn git."""
    ordered = json.loads(json.dumps(snap))
    for kind, rows in ordered["samples"].items():
        ordered["samples"][kind] = sorted(
            rows, key=lambda r: json.dumps(r, sort_keys=True))
    return json.dumps(ordered, indent=1, sort_keys=True) + "\n"


def _commit_dates(commits):
    """Resolve commits to dates so samples stay orderable after the session file
    is gone. Unresolvable commits are not an error — history gets rewritten."""
    for commit, entry in commits.items():
        try:
            entry["date"] = subprocess.check_output(
                ["git", "show", "-s", "--format=%ci", commit],
                stderr=subprocess.DEVNULL).decode().split()[0]
        except Exception:
            entry["date"] = None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    replace = "--replace" in argv
    for flag in ("--replace", "--merge"):
        while flag in argv:
            argv.remove(flag)
    out_path = DEFAULT_OUT
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
        del argv[i:i + 2]
    roots = argv or DEFAULT_ROOTS

    files = iter_session_files(roots)
    fresh = harvest_events(load(f) for f in files)
    fresh["provenance"]["roots"] = sorted(roots)

    base = _empty()
    if not replace and os.path.exists(out_path):
        try:
            base = json.load(open(out_path))
        except (OSError, json.JSONDecodeError):
            print(f"warning: could not read {out_path}; starting fresh")
    snap = fresh if replace else merge_snapshots(base, fresh)

    _commit_dates(snap["provenance"]["commits"])
    snap["provenance"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    snap["schema_version"] = SCHEMA_VERSION

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(build_snapshot(snap))

    s = snap["samples"]
    print(f"{'replaced' if replace else 'merged'} -> {out_path}")
    print(f"  {len(files)} session files, {snap['provenance']['sessions']} sessions "
          f"({snap['provenance']['dirty_sessions']} dirty), "
          f"{len(snap['provenance']['commits'])} commits")
    for kind in sorted(s):
        print(f"  {len(s[kind]):5} {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
