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
from dataclasses import dataclass, asdict, field
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


@dataclass
class SegmentOutcomePair:
    """One segment's prose beside one outcome's record — the judgeable unit.

    The unit is the *citation*, not the segment and not the outcome: a segment
    covering three outcomes can render two faithfully and invent the third, and
    only a per-citation view can say which.
    """
    round: int
    segment_id: str
    text: str
    cited_outcome_ids: List[str]
    outcome_id: str
    resolved: bool = True
    actor_id: Optional[str] = None
    actor_narrative_name: Optional[str] = None
    intent: Optional[str] = None
    method: Optional[str] = None
    weapon: Optional[str] = None
    damage_type: Optional[str] = None
    target_names: List[str] = field(default_factory=list)
    declared_dialogue: Optional[str] = None
    success: Optional[bool] = None
    outcome_tier: Optional[str] = None
    margin: Optional[float] = None
    observable_facts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Round-qualified. `seg_1` is a round-1 id AND a round-3 id in the
        recorded chain, and merging those two hides the drift outright."""
        return f"r{self.round}/{self.segment_id}/{self.outcome_id}"


def segment_outcome_pairs(events: Sequence[dict]) -> List[SegmentOutcomePair]:
    """Every (segment, cited outcome) in a session, from the ACCEPTED synthesis.

    Source is `round_synthesis`, never the `llm_call` log. 103 of the corpus's
    257 `OutcomeRoundSynthesis` calls are surplus to the syntheses actually
    recorded — rejected retries, across 32 sessions — so scoring the call log
    judges prose no reader ever saw.

    A citation whose outcome is missing is returned with `resolved=False`
    rather than dropped. The validator already errors on unknown outcome ids so
    it should not occur; silently filtering it is how a census reports a clean
    number over incomplete data.
    """
    outcomes: Dict[str, dict] = {}
    for e in events:
        if e.get("event_type") != "applied_outcome":
            continue
        body = _body(e)
        if body.get("outcome_id"):
            outcomes[body["outcome_id"]] = body

    pairs: List[SegmentOutcomePair] = []
    for e in events:
        if e.get("event_type") != "round_synthesis":
            continue
        body = _body(e)
        for segment in body.get("segments") or []:
            cited = list(segment.get("source_outcome_ids") or [])
            for outcome_id in cited:
                pair = SegmentOutcomePair(
                    round=e.get("round"),
                    segment_id=segment.get("segment_id"),
                    text=segment.get("text") or "",
                    cited_outcome_ids=cited,
                    outcome_id=outcome_id,
                    resolved=outcome_id in outcomes,
                )
                outcome = outcomes.get(outcome_id)
                if outcome:
                    roll = outcome.get("roll_result") or {}
                    pair.actor_id = outcome.get("actor_id")
                    pair.actor_narrative_name = (outcome.get("actor_narrative_name")
                                                 or outcome.get("actor_name"))
                    pair.intent = outcome.get("intent")
                    pair.method = outcome.get("method")
                    pair.weapon = outcome.get("weapon")
                    pair.damage_type = outcome.get("damage_type")
                    pair.target_names = list(outcome.get("target_names") or [])
                    pair.declared_dialogue = outcome.get("declared_dialogue")
                    pair.success = roll.get("success")
                    pair.outcome_tier = roll.get("outcome_tier")
                    pair.margin = roll.get("margin")
                    pair.observable_facts = list(outcome.get("observable_facts") or [])
                pairs.append(pair)
    return pairs


def actor_presence(pairs: Sequence[SegmentOutcomePair]) -> List[Dict[str, Any]]:
    """Does each segment name the actor of the outcome it cites?

    A FILTER, NOT A SCORE. Naming the actor is necessary for a segment to be
    about the outcome it claims, and nowhere near sufficient — the #156 case
    named Hard Vane while describing an action he took the previous round. Use
    it to choose which cases are worth a judge's attention; never to assert
    that narration is faithful, and never to derive a research number.
    """
    findings = []
    for pair in pairs:
        name = pair.actor_narrative_name
        if name and name.lower() not in pair.text.lower():
            findings.append({
                "key": pair.key,
                "round": pair.round,
                "segment_id": pair.segment_id,
                "cites": pair.cited_outcome_ids,
                "unnamed_actors": [name],
            })
    return findings


def target_presence(pairs: Sequence[SegmentOutcomePair]) -> List[Dict[str, Any]]:
    """Does a segment name anyone the cited outcome was aimed at?

    A FILTER, NOT A SCORE, on the same terms as `actor_presence` and with the
    same error in both directions: "the subdued operatives" is good writing and
    names nobody, while naming a target proves only that the name appears.

    Silent on outcomes with no targets — a watch kept or a call placed has none,
    and inventing a finding there would drown the real ones.
    """
    findings = []
    for pair in pairs:
        if not pair.target_names:
            continue
        text = pair.text.lower()
        if not any(t.lower() in text for t in pair.target_names):
            findings.append({
                "key": pair.key,
                "round": pair.round,
                "segment_id": pair.segment_id,
                "cites": pair.cited_outcome_ids,
                "unnamed_targets": list(pair.target_names),
            })
    return findings


#: Long enough that shared idiom ("he holsters his weapon") does not match by
#: chance, short enough to survive the light rewording the corpus actually does.
SHINGLE_WORDS = 8
#: Round 3's segments reuse 9-30% of their shingles from round 2; round 2 reuses
#: none from round 1. Anything above zero is worth a judge's eye.
REUSE_THRESHOLD = 0.05


def _shingles(text: str, size: int = SHINGLE_WORDS) -> set:
    words = text.lower().split()
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def cross_round_reuse(pairs: Sequence[SegmentOutcomePair]) -> List[Dict[str, Any]]:
    """How much of a segment is lifted from an EARLIER round's narration.

    A FILTER, NOT A SCORE. `opening_similarity` compares round openings, which
    is where repetition usually shows; the #156 case re-narrated round 2's
    dialogue in the middle of round 3 and opened on a fresh sentence, so
    openings alone cannot see it.

    Whole-text similarity cannot see it either — r2->r3 ratios there run
    0.27-0.51 against r1->r2's 0.02-0.07, overlapping far too much to threshold.
    Shared shingles separate them cleanly.
    """
    by_round: Dict[int, Dict[str, str]] = {}
    for pair in pairs:
        by_round.setdefault(pair.round, {})[pair.segment_id] = pair.text

    findings = []
    for rnd in sorted(by_round):
        for segment_id, text in sorted(by_round[rnd].items()):
            mine = _shingles(text)
            if not mine:
                continue
            for prior in sorted(r for r in by_round if r < rnd):
                theirs = set()
                for other in by_round[prior].values():
                    theirs |= _shingles(other)
                shared = mine & theirs
                if len(shared) / len(mine) > REUSE_THRESHOLD:
                    findings.append({
                        "round": rnd,
                        "prior_round": prior,
                        "segment_id": segment_id,
                        "reuse": len(shared) / len(mine),
                        "shared": sorted(shared)[:5],
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
    pairs = segment_outcome_pairs(events)
    return {
        "session": os.path.basename(path),
        "outcome_first": is_outcome_first(events),
        "rounds": len(rounds),
        "opening_similarity": opening_similarity(rounds),
        "length_growth": length_growth(rounds),
        "actor_presence": actor_presence(pairs),
        "target_presence": target_presence(pairs),
        "cross_round_reuse": cross_round_reuse(pairs),
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
