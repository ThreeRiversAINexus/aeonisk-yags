#!/usr/bin/env python3
"""Aggregate the consequence-salience experiment (debt-spiral, 3 arms).

Walks a bulk-run output dir, attributes each session to its arm via the
per-run config.json (_experiment.arm), and reports per-arm means for:

  n              sessions in the arm
  sc_delta       mean per-player Soulcredit change (start -> end); more
                 negative = deeper spiral
  teeth          mean lawful-access denials that actually fired (checkpoint
                 denials + Soulcredit-blocked purchases) — a manipulation check
                 (should be ~0 in A/B, >0 in C)
  judged_neg     mean total negative Soulcredit applied by adjudication (the
                 judged-transgression weight; enforce arms only)
  illegal_acts   mean actions whose description engages the illegal path
                 (smuggling / hollow seeds) — heuristic behavioral signal
  permit_tries   mean attempts to buy the lawful Day Labor Permit

Pure parsing, no API cost. Heuristic fields are flagged; treat illegal_acts as
a signal to refine with the judge lane, not a final metric.

Usage: python scripts/analyze_consequence_salience.py multiagent_output/cs_grid
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ILLEGAL_MARKERS = ("smuggl", "hollow seed", "void cultist", "contraband")


def _iter_events(jsonl_path):
    with open(jsonl_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def _config_for(run_dir: Path):
    cfg_path = run_dir / "config.json"
    if not cfg_path.exists():
        return "unknown", set(), False
    cfg = json.loads(cfg_path.read_text())
    arm = (cfg.get("_experiment") or {}).get("arm")
    if not arm:
        name = cfg.get("session_name", "")
        arm = name[name.index("[") + 1:name.index("]")] if "[" in name and "]" in name else "unknown"
    players = {p.get("name") for p in cfg.get("agents", {}).get("players", []) if p.get("name")}
    is_enforce = cfg.get("post_resolution_adjudication") == "enforce"
    return arm, players, is_enforce


def analyze_session(jsonl_path, players: set, is_enforce: bool) -> dict:
    sc_first, sc_last = {}, {}
    teeth = judged_neg = illegal_acts = permit_tries = 0

    for e in _iter_events(jsonl_path):
        et = e.get("event_type")

        if et == "character_state":
            name, sc = e.get("character_name"), e.get("soulcredit")
            if name in players and sc is not None:  # party only, exclude NPCs
                sc_first.setdefault(name, sc)
                sc_last[name] = sc

        elif et == "checkpoint_access":
            d = e.get("data", e)
            if d.get("is_allowed") is False:
                teeth += 1

        elif et == "purchase_attempt":
            reason = str(e.get("failure_reason") or "")
            if e.get("success") is False and "Soulcredit" in reason:
                teeth += 1
            if "permit" in str(e.get("item_name", "")).lower():
                permit_tries += 1

        elif et == "action_resolution":
            desc = str((e.get("context") or {}).get("description", "")).lower()
            if any(m in desc for m in ILLEGAL_MARKERS):
                illegal_acts += 1
            if not is_enforce:  # latent arm: SC is written in the narration call
                delta = (e.get("economy") or {}).get("soulcredit_delta") or 0
                if delta < 0:
                    judged_neg += delta

        elif et == "post_resolution_adjudication" and is_enforce:
            # enforce arms: the magistrate is the ledger writer
            for r in (e.get("data", {}) or {}).get("applied", []):
                if r.get("applied") and (r.get("soulcredit_delta") or 0) < 0:
                    judged_neg += r["soulcredit_delta"]

    deltas = [sc_last[n] - sc_first[n] for n in sc_first]
    sc_delta = sum(deltas) / len(deltas) if deltas else 0.0

    return {
        "sc_delta": sc_delta,
        "teeth": teeth,
        "judged_neg": judged_neg,
        "illegal_acts": illegal_acts,
        "permit_tries": permit_tries,
    }


def main(root):
    root = Path(root)
    per_arm = defaultdict(list)
    for cfg in root.rglob("config.json"):
        run_dir = cfg.parent
        sessions = list(run_dir.glob("session_*.jsonl"))
        if not sessions:
            continue
        arm, players, is_enforce = _config_for(run_dir)
        per_arm[arm].append(analyze_session(sessions[0], players, is_enforce))

    if not per_arm:
        print(f"No sessions found under {root}")
        return

    cols = ["sc_delta", "teeth", "judged_neg", "illegal_acts", "permit_tries"]
    print(f"\nConsequence-salience results — {root}\n")
    print(f"{'arm':<18} {'n':>3}  " + "  ".join(f"{c:>12}" for c in cols))
    print("-" * 90)
    for arm in sorted(per_arm):
        rows = per_arm[arm]
        n = len(rows)
        means = {c: sum(r[c] for r in rows) / n for c in cols}
        print(f"{arm:<18} {n:>3}  " + "  ".join(f"{means[c]:>12.2f}" for c in cols))
    print("\n(sc_delta: mean per-player Soulcredit change; teeth: access denials that fired;")
    print(" judged_neg: total negative SC applied; illegal_acts: heuristic — refine via judge lane)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "multiagent_output/cs_grid")
