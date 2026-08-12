#!/usr/bin/env python3
"""Offline scorers for outcome-first round synthesis (#158).

These run against recorded output with no API calls. They do not judge prose —
they measure three things a judge should never have to be paid to notice:

  * `opening_similarity` — how much of round N's opening is round N-1's;
  * `length_growth` — whether narration accretes across rounds;
  * `actor_presence` — whether a segment names the actors of the outcomes it
    cites. **A filter, not a measurement.** It is a necessary condition with
    real false negatives, so it selects cases for a judge and never scores
    prose on its own, and it must never be used to produce a research number
    out of narration.

The first two found the defect in #156 for nothing: across the corpus's
outcome-first sessions, **22% of consecutive round pairs open with
character-identical text**, and one session opens all six of its rounds with
the same sentence. Legacy-pipeline sessions sit at 4% similar-or-better. The
difference is a prompt field: the synthesis prompt hands the model the entire
previous round's narration under the label `PRIOR CANONICAL ENDING`.

Usage:
    python scripts/synthesis_scorers.py bulk_output multiagent_output
    python scripts/synthesis_scorers.py <dir> --json
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import statistics
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.session_invariants import _body, load  # noqa: E402

#: How much of an opening to compare. Long enough that a shared first clause
#: does not dominate, short enough that a genuinely new scene scores low.
OPENING_CHARS = 120


@dataclass
class RoundNarration:
    round: int
    text: str


def synthesis_rounds(events: Sequence[dict]) -> List[RoundNarration]:
    """Every round's narration, in round order, from a loaded session."""
    seen: Dict[int, str] = {}
    for e in events:
        if e.get("event_type") != "round_synthesis":
            continue
        body = _body(e)
        text = body.get("narration") or body.get("synthesis") or ""
        rnd = e.get("round")
        if text and isinstance(rnd, int):
            seen[rnd] = text
    return [RoundNarration(r, seen[r]) for r in sorted(seen)]


def is_outcome_first(events: Sequence[dict]) -> bool:
    """Only the outcome-first pipeline's prompt carries the prior narration."""
    return any(e.get("event_type") == "applied_outcome" for e in events)


def opening_similarity(rounds: Sequence[RoundNarration]) -> List[Dict[str, Any]]:
    """Round N's opening against round N-1's. 1.0 means character-identical.

    Exact and deterministic. It measures repetition and claims nothing about
    quality — a session may legitimately return to the same room, but it should
    not return to the same sentence.
    """
    out = []
    for prev, cur in zip(rounds, rounds[1:]):
        a, b = prev.text[:OPENING_CHARS], cur.text[:OPENING_CHARS]
        out.append({
            "round": cur.round,
            "prev_round": prev.round,
            "similarity": difflib.SequenceMatcher(None, a, b).ratio(),
            "identical": a == b,
        })
    return out


def length_growth(rounds: Sequence[RoundNarration]) -> List[Dict[str, Any]]:
    """Narration length relative to the session's first round.

    Accretion is the signature of a narrator re-telling what it was shown
    rather than continuing from it.
    """
    if not rounds:
        return []
    base = len(rounds[0].text) or 1
    return [{"round": r.round, "chars": len(r.text), "ratio": len(r.text) / base}
            for r in rounds]


def actor_presence(events: Sequence[dict]) -> List[Dict[str, Any]]:
    """Does each segment name the actors of the outcomes it cites?

    A FILTER, NOT A SCORE. Naming the actor is necessary for a segment to be
    about the outcome it claims, and nowhere near sufficient — the #156 case
    named Hard Vane while describing an action he took the previous round. Use
    it to choose which cases are worth a judge's attention; never to assert
    that narration is faithful, and never to derive a research number.
    """
    actors: Dict[str, str] = {}
    for e in events:
        if e.get("event_type") == "applied_outcome":
            b = _body(e)
            name = b.get("actor_narrative_name") or b.get("actor_name")
            if b.get("outcome_id") and name:
                actors[b["outcome_id"]] = name

    findings = []
    for e in events:
        if e.get("event_type") != "llm_call":
            continue
        body = _body(e)
        if "OutcomeRoundSynthesis" not in str(body.get("call_type")):
            continue
        try:
            parsed = json.loads(body.get("response") or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for seg in parsed.get("segments") or []:
            text = (seg.get("text") or "").lower()
            missing = [actors[oid] for oid in seg.get("source_outcome_ids") or []
                       if oid in actors and actors[oid].lower() not in text]
            if missing:
                findings.append({
                    "round": e.get("round"),
                    "segment_id": seg.get("segment_id"),
                    "cites": seg.get("source_outcome_ids"),
                    "unnamed_actors": missing,
                })
    return findings


def score_session(path: str) -> Optional[Dict[str, Any]]:
    """All three scorers over one session file, or None if it has no synthesis."""
    try:
        events = load(path)
    except Exception:
        return None
    rounds = synthesis_rounds(events)
    if not rounds:
        return None
    return {
        "session": os.path.basename(path),
        "outcome_first": is_outcome_first(events),
        "rounds": len(rounds),
        "opening_similarity": opening_similarity(rounds),
        "length_growth": length_growth(rounds),
        "actor_presence": actor_presence(events),
    }


def _session_files(roots: Iterable[str]) -> List[str]:
    found: List[str] = []
    for root in roots:
        if os.path.isfile(root):
            found.append(root)
            continue
        found += [p for p in glob.glob(os.path.join(root, "**", "*.jsonl"),
                                       recursive=True)
                  if "session_" in os.path.basename(p)]
    return sorted(set(found))


def summarise(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Split by pipeline, because the comparison is the finding."""
    out: Dict[str, Any] = {}
    for label, want in (("outcome_first", True), ("legacy", False)):
        sims, identical, pairs, ratios = [], 0, 0, []
        for r in results:
            if r["outcome_first"] is not want:
                continue
            for s in r["opening_similarity"]:
                sims.append(s["similarity"])
                identical += s["identical"]
                pairs += 1
            if r["length_growth"]:
                ratios.append(r["length_growth"][-1]["ratio"])
        out[label] = {
            "sessions": sum(1 for r in results if r["outcome_first"] is want),
            "round_pairs": pairs,
            "median_opening_similarity": statistics.median(sims) if sims else None,
            "identical_openings": identical,
            "identical_pct": (100 * identical / pairs) if pairs else None,
            "median_final_length_ratio": statistics.median(ratios) if ratios else None,
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="session files or directories")
    ap.add_argument("--json", action="store_true", help="emit per-session JSON")
    args = ap.parse_args(argv)

    results = [r for r in (score_session(p) for p in _session_files(args.paths)) if r]
    if args.json:
        print(json.dumps({"sessions": results, "summary": summarise(results)}, indent=2))
        return 0

    s = summarise(results)
    print(f"Scored {len(results)} sessions with round synthesis\n")
    print(f"{'':22s} {'outcome-first':>14s} {'legacy':>10s}")
    for key, label in (("sessions", "sessions"),
                       ("round_pairs", "round pairs"),
                       ("median_opening_similarity", "median opening sim"),
                       ("identical_pct", "identical openings %"),
                       ("median_final_length_ratio", "final/first length")):
        a, b = s["outcome_first"][key], s["legacy"][key]
        fmt = lambda v: "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
        print(f"{label:22s} {fmt(a):>14s} {fmt(b):>10s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
