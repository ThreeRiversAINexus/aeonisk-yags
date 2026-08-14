#!/usr/bin/env python3
"""Measure how often synthesis prose describes the outcome it cites (#156).

The pipeline validates **coverage** — every outcome is cited by some segment,
no segment cites an outcome that does not exist, no segment claims a life-state
change the mechanics did not apply. It does not validate **correspondence**:
that the words in a segment describe the outcome that segment names. Round 3 of
`3de9e609` bound its segments to exactly the right round-3 outcome ids and then
wrote round 2's prose, satisfying every structural check.

`synthesis_scorers` holds three deterministic filters over the same pairs. All
three are necessary conditions with real error in both directions, so they
select cases; they cannot say whether prose is faithful. That reading is what
this lane pays a judge for.

Order of operations, and none of it is optional:

  1. `calibrate` — judge the seed below, which was read by hand first. If the
     judge cannot reproduce a separation we already know the answer to, the
     census is a number nobody can falsify and the work stops here.
  2. `prompts` — build the census, filters HELD OUT of every prompt.
  3. `score` — join verdicts back, report drift, and measure each filter's
     precision and recall against the verdicts. That comparison is the point:
     it says whether a free check can stand in for a paid one in production.

Usage:
    correspondence_eval.py prompts multiagent_output bulk_output -o p.jsonl
    fidelity_runner.py run --prompts p.jsonl --provider openai \\
        --model gpt-5.4-mini --output v.jsonl --workers 8
    correspondence_eval.py score multiagent_output bulk_output -v v.jsonl

    correspondence_eval.py calibrate -o seed.jsonl        # then run, then:
    correspondence_eval.py calibrate -v seed_verdicts.jsonl
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.session_invariants import load  # noqa: E402
from scripts.synthesis_scorers import (  # noqa: E402
    SegmentOutcomePair, actor_presence, cross_round_reuse, is_outcome_first,
    segment_outcome_pairs, target_presence,
)

CHAIN = "tests/fixtures/sessions/synthesis_repetition_chain.jsonl"

# ---------------------------------------------------------------------------
# The seed, and what reading it changed.
#
# #156's table says round 3's `seg_3` "describes out_000009, round 2". That is
# true of its first half and false of its second: after re-narrating Hard Vane
# holstering his weapon, the passage goes on to render out_000015 — the
# Corporate Influence call — and renders it as the failure the record says it
# was. `seg_4` does the same for Sela. The first calibration run caught this:
# the judge called both faithful, the seed said drift, and the seed was wrong.
#
# So there are two defects here, not one, and only the second is the one the
# issue named:
#
#   1. NOT RENDERED — the passage does not describe its outcome at all.
#      `r3/seg_1` cites Sela's failed coordination and narrates Cold Tarn's
#      round-2 overwatch, down to the same quoted line.
#   2. UNACCOUNTED — the passage renders its outcome AND asserts, as happening
#      now, events that are not in this round's record. All four round-3
#      segments do this; three of them still render what they cite.
#
# A check for (1) alone would have passed three of the four segments in the
# round that #156 was filed about.
# ---------------------------------------------------------------------------

#: Cites out_000016 and renders nothing of it.
SEED_NOT_RENDERED = (
    "r3/seg_1/out_000016",
)

#: Both halves of the balance. The three round-3 entries are the correction:
#: they are contaminated, and they do render what they cite.
SEED_RENDERED = (
    "r1/seg_2/out_000003",   # Hard Vane draws the Union Heavy Pistol and fires
    "r2/seg_01/out_000007",  # Cold Tarn takes up his post and stands watch
    "r2/seg_02/out_000008",  # the first operative pleads
    "r2/seg_03/out_000009",  # Hard Vane holsters — here it IS this round
    "r3/seg_3/out_000015",   # "his call goes nowhere useful" — the failure, rendered
    "r3/seg_4/out_000016",   # "the effort does not fully land" — likewise
)

#: Segment-level, because contamination is a property of the passage and not of
#: any one citation in it.
SEED_UNACCOUNTED = (
    "r3/seg_1",  # Cold Tarn's round-2 overwatch, same dialogue, verbatim
    "r3/seg_2",  # the operatives plead; in round 3 they hide
    "r3/seg_3",  # Hard Vane holsters again, an action from round 2
    "r3/seg_4",  # Sela works the medkit again, an action from round 2
)

SEED_ACCOUNTED = (
    "r1/seg_2",
    "r2/seg_01",
    "r2/seg_02",
    "r2/seg_03",
)

SYSTEM = """You are auditing a tabletop RPG session log.

Each item gives you one recorded outcome — what a character attempted, how the
attempt resolved, and who it was aimed at — and one passage of narration that
was bound to that outcome. Decide one thing: does the passage describe that
outcome?

Judge only against the record you are given. Do not reward good writing, do not
penalise brevity, and do not require that the passage mention every detail. A
passage may cover several outcomes at once; when it does, you are asked about
one of them, and the rest of the passage is not evidence against it.

Answer no when the passage describes a different action, a different character
acting, or a result the record contradicts — an attempt recorded as a failure
narrated as succeeding, or the reverse.

Reply with JSON only:
{"renders": true|false, "reason": "<20 words", "instead": "<what it describes, or empty>"}"""

SEGMENT_SYSTEM = """You are auditing a tabletop RPG session log.

You are given everything that happened in one round of play — every character's
attempt and how it resolved — and one passage of the narration written for that
round. Decide one thing: does the passage narrate, as happening now, an action
or event that is not in this round's record?

Referring to earlier events as past is correct and expected: "after the earlier
violence", "the gunfire has already done its work". That is not what you are
looking for. You are looking for a character performing an action in the
present tense of this passage — drawing a weapon, speaking a line, treating a
wound, taking up a post — when this round's record contains no such action.

Atmosphere, interiority and description of the standing scene are not actions.
Do not flag them.

Reply with JSON only:
{"unaccounted": true|false, "reason": "<20 words", "quote": "<the phrase, or empty>"}"""


@dataclass
class Verdict:
    renders: bool
    reason: str = ""
    instead: str = ""


def _outcome_block(pair: SegmentOutcomePair) -> str:
    lines = [f"Character:  {pair.actor_narrative_name}",
             f"Attempted:  {pair.intent}"]
    if pair.method:
        lines.append(f"How:        {pair.method}")
    if pair.target_names:
        lines.append(f"Aimed at:   {', '.join(pair.target_names)}")
    if pair.weapon:
        lines.append(f"Weapon:     {pair.weapon}"
                     + (f" ({pair.damage_type})" if pair.damage_type else ""))
    if pair.declared_dialogue:
        lines.append(f"Said:       {pair.declared_dialogue}")

    if pair.success is None:
        result = pair.outcome_tier or "not rolled"
    else:
        result = "SUCCEEDED" if pair.success else "FAILED"
        if pair.outcome_tier:
            result += f" ({pair.outcome_tier})"
        if pair.margin is not None:
            result += f", by {pair.margin:+g}"
    lines.append(f"Result:     {result}")

    for fact in pair.observable_facts:
        summary = fact.get("prose_safe_summary") or fact.get("symbolic_value")
        if summary:
            lines.append(f"Also:       {summary}")
    return "\n".join(lines)


def build_prompts(pairs: Sequence[SegmentOutcomePair],
                  session: str) -> List[Dict[str, str]]:
    """One judge item per resolved pair, with every filter's opinion left out.

    A judge told that `actor_presence` fired cannot be used to measure whether
    `actor_presence` was right. Nothing in `synthesis_scorers` may appear here,
    and `test_the_filters_are_held_out` fails the build if it does.
    """
    prompts = []
    for pair in pairs:
        if not pair.resolved:
            continue
        others = [o for o in pair.cited_outcome_ids if o != pair.outcome_id]
        also = (f"\nThe passage was also bound to {', '.join(others)}, so it is "
                f"expected to cover those as well.\n" if others else "\n")
        prompts.append({
            "item_id": f"{session}|{pair.key}",
            "system": SYSTEM,
            "user": (f"RECORDED OUTCOME {pair.outcome_id} (round {pair.round})\n"
                     f"{_outcome_block(pair)}\n"
                     f"{also}"
                     f"NARRATION BOUND TO IT\n{pair.text}\n\n"
                     f"Does the narration describe outcome {pair.outcome_id}?"),
        })
    return prompts


def build_segment_prompts(pairs: Sequence[SegmentOutcomePair],
                          session: str) -> List[Dict[str, str]]:
    """One item per segment: does the passage narrate anything this round did not?

    Asked per segment rather than per citation, because contamination is a
    property of the passage. `r3/seg_3` renders its own outcome faithfully and
    re-narrates round 2's holstering in the same breath; per-citation, that
    passage is correct.

    The whole round's record goes in, not just the cited outcomes — otherwise a
    passage covering a teammate's action in the same round reads as invention.
    """
    by_round: Dict[int, Dict[str, SegmentOutcomePair]] = {}
    segments: Dict[tuple, SegmentOutcomePair] = {}
    for pair in pairs:
        if not pair.resolved:
            continue
        by_round.setdefault(pair.round, {}).setdefault(pair.outcome_id, pair)
        segments.setdefault((pair.round, pair.segment_id), pair)

    prompts = []
    for (rnd, segment_id), pair in sorted(segments.items()):
        record = "\n\n".join(
            f"OUTCOME {oid}\n{_outcome_block(p)}"
            for oid, p in sorted(by_round.get(rnd, {}).items()))
        prompts.append({
            "item_id": f"{session}|r{rnd}/{segment_id}",
            "system": SEGMENT_SYSTEM,
            "user": (f"EVERYTHING RECORDED IN ROUND {rnd}\n\n{record}\n\n"
                     f"A PASSAGE OF ROUND {rnd}'S NARRATION\n{pair.text}\n\n"
                     f"Does the passage narrate, as happening now, anything "
                     f"absent from round {rnd}'s record?"),
        })
    return prompts


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _parse_bool_field(text: Optional[str], field: str) -> Optional[dict]:
    if not text:
        return None
    match = _FENCE.search(text)
    if match:
        text = match.group(1)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get(field), bool):
        return None
    return data


def parse_unaccounted(text: Optional[str]) -> Optional[bool]:
    """None for anything unreadable, on the same terms as `parse_verdict`."""
    data = _parse_bool_field(text, "unaccounted")
    return None if data is None else data["unaccounted"]


def parse_verdict(text: Optional[str]) -> Optional[Verdict]:
    """None for anything unreadable — never a default in either direction.

    The silent direction of a broken join is "clean", so a response that did not
    arrive, did not parse, or did not answer the question must drop out of the
    numerator AND the denominator rather than land in one of them.
    """
    data = _parse_bool_field(text, "renders")
    if data is None:
        return None
    return Verdict(renders=data["renders"],
                   reason=str(data.get("reason") or "")[:200],
                   instead=str(data.get("instead") or "")[:200])


def filter_agreement(flagged: Set[str], drift: Set[str],
                     universe: Set[str]) -> Dict[str, Any]:
    """A deterministic filter against the judge, over the pairs actually judged.

    `precision` is None when the filter never fired. Reporting 1.0 there would
    read as a perfect check when it is in fact a silent one — the same
    absence-of-evidence trap the invariant runner fell into.
    """
    flagged &= universe
    drift &= universe
    true_positive = len(flagged & drift)
    false_positive = len(flagged - drift)
    false_negative = len(drift - flagged)
    return {
        "flagged": len(flagged),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": (true_positive / len(flagged)) if flagged else None,
        "recall": (true_positive / len(drift)) if drift else None,
    }


def score(pairs: Sequence[SegmentOutcomePair], responses: Sequence[dict],
          session: str) -> Dict[str, Any]:
    """Join verdicts back onto pairs and report what is and is not known."""
    by_key = {p.key: p for p in pairs}
    expected = {p.key for p in pairs if p.resolved}
    verdicts: Dict[str, Verdict] = {}
    unreadable = unmatched = 0

    for record in responses:
        item_id = str(record.get("item_id") or "")
        key = item_id.split("|", 1)[-1]
        if key not in expected:
            unmatched += 1
            continue
        verdict = parse_verdict(record.get("response"))
        if verdict is None:
            unreadable += 1
            continue
        verdicts[key] = verdict

    drift = {k for k, v in verdicts.items() if not v.renders}
    judged = set(verdicts)
    by_tier: Dict[str, Dict[str, int]] = {}
    for key in judged:
        pair = by_key[key]
        tier = ("not rolled" if pair.success is None
                else "succeeded" if pair.success else "failed")
        bucket = by_tier.setdefault(tier, {"judged": 0, "drift": 0})
        bucket["judged"] += 1
        bucket["drift"] += key in drift

    return {
        "session": session,
        "pairs": len(pairs),
        "unresolved": sum(1 for p in pairs if not p.resolved),
        "judged": len(judged),
        "unanswered": len(expected - judged) - unreadable,
        "unreadable": unreadable,
        "unmatched": unmatched,
        "drift": len(drift),
        "drift_pct": (100 * len(drift) / len(judged)) if judged else None,
        "drift_keys": sorted(drift),
        # The universe for `filter_agreement`. A filter firing on a pair the
        # judge never answered is neither right nor wrong about it, and folding
        # those in silently deflates precision for the filters that fire most.
        "judged_keys": sorted(judged),
        "by_result": by_tier,
        "reasons": {k: verdicts[k].reason for k in sorted(drift)},
    }


def session_files(roots: Iterable[str]) -> List[str]:
    found: List[str] = []
    for root in roots:
        if os.path.isfile(root):
            found.append(root)
            continue
        found += glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    return sorted(set(found))


def _load_pairs(roots: Iterable[str]):
    """Every outcome-first session under `roots`, as {session: pairs}."""
    out: Dict[str, List[SegmentOutcomePair]] = {}
    for path in session_files(roots):
        try:
            events = load(path)
        except Exception:
            continue
        if not is_outcome_first(events):
            continue
        pairs = segment_outcome_pairs(events)
        if pairs:
            out[os.path.basename(path).replace(".jsonl", "")] = pairs
    return out


def _filters(pairs: Sequence[SegmentOutcomePair]) -> Dict[str, Set[str]]:
    reuse = {f["segment_id"]: f for f in cross_round_reuse(pairs)}
    return {
        "actor_presence": {f["key"] for f in actor_presence(pairs)},
        "target_presence": {f["key"] for f in target_presence(pairs)},
        # A reuse finding is about a segment; every citation in it inherits it.
        "cross_round_reuse": {p.key for p in pairs
                              if p.segment_id in reuse
                              and reuse[p.segment_id]["round"] == p.round},
    }


def _seed_pairs() -> List[SegmentOutcomePair]:
    """Only the pairs the seed names, so nothing unlabelled is paid for."""
    keys = set(SEED_NOT_RENDERED) | set(SEED_RENDERED)
    segments = set(SEED_UNACCOUNTED) | set(SEED_ACCOUNTED)
    return [p for p in segment_outcome_pairs(load(CHAIN))
            if p.key in keys or f"r{p.round}/{p.segment_id}" in segments]


def cmd_prompts(args) -> int:
    sessions = ({"chain": _seed_pairs()} if args.calibrate
                else _load_pairs(args.paths))
    prompts = []
    for session, pairs in sorted(sessions.items()):
        if args.calibrate:
            keys = set(SEED_NOT_RENDERED) | set(SEED_RENDERED)
            prompts += build_prompts([p for p in pairs if p.key in keys], session)
        else:
            prompts += build_prompts(pairs, session)
        prompts += build_segment_prompts(pairs, session)
    with open(args.output, "w") as handle:
        for prompt in prompts:
            handle.write(json.dumps(prompt, ensure_ascii=False) + "\n")
    print(f"Wrote {len(prompts)} prompts from {len(sessions)} session(s) "
          f"to {args.output}", file=sys.stderr)
    return 0


def cmd_score(args) -> int:
    responses = [json.loads(line) for line in open(args.verdicts) if line.strip()]
    if args.calibrate:
        return _report_calibration(_seed_pairs(), responses)
    sessions = _load_pairs(args.paths)

    all_pairs: List[SegmentOutcomePair] = []
    drift: Set[str] = set()
    judged_universe: Set[str] = set()
    flagged_all: Dict[str, Set[str]] = {}
    totals = {"judged": 0, "unanswered": 0, "unreadable": 0, "unmatched": 0}
    by_result: Dict[str, Dict[str, int]] = {}
    reasons: Dict[str, str] = {}

    for session, pairs in sorted(sessions.items()):
        mine = [r for r in responses
                if str(r.get("item_id", "")).startswith(f"{session}|")]
        report = score(pairs, mine, session)
        all_pairs += pairs
        drift |= {f"{session}|{k}" for k in report["drift_keys"]}
        judged_universe |= {f"{session}|{k}" for k in report["judged_keys"]}
        reasons.update({f"{session}|{k}": v for k, v in report["reasons"].items()})
        for field in totals:
            totals[field] += report[field]
        for tier, bucket in report["by_result"].items():
            target = by_result.setdefault(tier, {"judged": 0, "drift": 0})
            target["judged"] += bucket["judged"]
            target["drift"] += bucket["drift"]
        for name, keys in _filters(pairs).items():
            flagged_all.setdefault(name, set())
            flagged_all[name] |= {f"{session}|{k}" for k in keys}

    print(f"\nCorrespondence census — {len(sessions)} outcome-first sessions, "
          f"{len(all_pairs)} segment-outcome pairs\n")
    print(f"  judged      {totals['judged']}")
    if totals["judged"]:
        print(f"  drifted     {len(drift)}  "
              f"({100 * len(drift) / totals['judged']:.1f}%)")
    for field in ("unanswered", "unreadable", "unmatched"):
        if totals[field]:
            print(f"  {field:<11} {totals[field]}")

    print("\n  by recorded result")
    for tier in sorted(by_result):
        bucket = by_result[tier]
        print(f"    {tier:<12} {bucket['drift']:>4} / {bucket['judged']:<4} "
              f"({100 * bucket['drift'] / bucket['judged']:.1f}%)")

    print("\n  deterministic filters, measured against the verdicts")
    for name, flagged in sorted(flagged_all.items()):
        agreement = filter_agreement(flagged, drift, judged_universe)
        precision = ("  -  " if agreement["precision"] is None
                     else f"{agreement['precision']:.2f}")
        recall = ("  -  " if agreement["recall"] is None
                  else f"{agreement['recall']:.2f}")
        print(f"    {name:<18} fired {agreement['flagged']:>4}   "
              f"precision {precision}   recall {recall}")

    if args.json:
        print(json.dumps({"drift": sorted(drift), "reasons": reasons}, indent=2))
    return 0


def _report_calibration(pairs, responses) -> int:
    """The judge against cases already read. Exit 1 if it cannot reproduce them.

    Both questions, because they catch different defects and a lane that
    calibrates only one of them is calibrated on nothing.
    """
    seeded = set(SEED_NOT_RENDERED) | set(SEED_RENDERED)
    report = score([p for p in pairs if p.key in seeded], responses, "chain")
    not_rendered = set(report["drift_keys"])

    unaccounted, unreadable = set(), 0
    for record in responses:
        key = str(record.get("item_id") or "").split("|", 1)[-1]
        if key.count("/") != 1:
            continue
        answer = parse_unaccounted(record.get("response"))
        if answer is None:
            unreadable += 1
        elif answer:
            unaccounted.add(key)

    questions = [
        ("Q1  does the passage render the outcome it cites?",
         [(k, "not rendered", k in not_rendered) for k in SEED_NOT_RENDERED]
         + [(k, "rendered", k not in not_rendered) for k in SEED_RENDERED]),
        ("Q2  does the passage narrate what this round did not?",
         [(k, "unaccounted", k in unaccounted) for k in SEED_UNACCOUNTED]
         + [(k, "accounted", k not in unaccounted) for k in SEED_ACCOUNTED]),
    ]

    print("\nCalibration against the hand-read seed")
    wrong = []
    for heading, rows in questions:
        print(f"\n  {heading}")
        for key, label, ok in rows:
            if not ok:
                wrong.append((key, label))
            print(f"    {'ok  ' if ok else 'WRONG'}  {label:<13} {key}"
                  f"   {report['reasons'].get(key, '')[:55]}")
    print(f"\n  Q1 judged {report['judged']}, unreadable {report['unreadable']}; "
          f"Q2 unreadable {unreadable}")

    if wrong:
        print(f"\nThe judge does not reproduce the seed ({len(wrong)} wrong: "
              f"{', '.join(k for k, _ in wrong)}). The census would be a number "
              f"nobody can falsify. Stop here.", file=sys.stderr)
        return 1
    print("\nSeparation is exact on both questions. The census may proceed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("prompts", "score", "calibrate"):
        p = sub.add_parser(name)
        p.add_argument("paths", nargs="*", default=[],
                       help="session files or directories")
        p.add_argument("-o", "--output", default="correspondence_prompts.jsonl")
        p.add_argument("-v", "--verdicts", help="responses JSONL from fidelity_runner")
        p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    args.calibrate = args.cmd == "calibrate"
    if args.cmd == "prompts" or (args.calibrate and not args.verdicts):
        return cmd_prompts(args)
    if not args.verdicts:
        parser.error("--verdicts is required to score")
    return cmd_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
