#!/usr/bin/env python3
"""
Resolve-then-leap continuation generator (prototype).

Reads a finished session's `end_state_snapshot` (emitted when a terminal clock
resolves the scene) and produces the NEXT session config with:

  * CONTINUITY (deterministic): surviving party members carried forward with their
    evolved void / soulcredit from the snapshot; the prior outcome recorded as
    established backstory. Defeated characters are dropped.
  * THE LEAP (one live LLM call): given how the chapter ended, imagine a
    continuation set a big time-jump later -- a premise, a new scenario_hint that
    treats the old verdict as history, and fresh starting_clocks for the new
    chapter (exactly one flagged is_terminal_clock so the next session also knows
    how to end).

Usage:
    python scripts/generate_continuation.py \
        --session  path/to/session_*.jsonl \
        --base-config scripts/session_configs/session_config_terminal_clock_test.json \
        --time-jump "three years later" \
        --out scripts/session_configs/session_config_continuation.json

Pass --no-llm to skip the leap call and emit a deterministic stub instead.
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # picks up ./.env (OPENAI_API_KEY etc.)


def read_snapshot(jsonl_path: str) -> dict:
    """Pull the end_state_snapshot payload from a session JSONL."""
    snap = None
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("event_type") == "end_state_snapshot":
                snap = row.get("data")  # last one wins
    if snap is None:
        sys.exit(f"No end_state_snapshot event in {jsonl_path} -- did a terminal clock resolve the scene?")
    return snap


def imagine_leap(snapshot: dict, time_jump: str, model: str) -> dict:
    """One live LLM call: turn the resolving beat into a continuation premise."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    survivors = ", ".join(
        f"{p['name']} ({p['faction']}, void {p['void_score']})"
        for p in snapshot.get("party", []) if not p.get("is_defeated")
    ) or "no named survivors"

    system = (
        "You are a continuity editor for the Aeonisk transmedia world. You are handed "
        "how one session ended and you design the NEXT chapter after a deliberate time "
        "jump. Honor what resolved as fixed history; do not retcon it. Invent forward, "
        "not sideways. Return JSON only."
    )
    user = (
        f"PRIOR CHAPTER OUTCOME: {snapshot.get('outcome')} -- resolved by the "
        f"'{snapshot.get('resolved_by_clock')}' beat: {snapshot.get('resolution')}\n"
        f"SURVIVORS CARRIED FORWARD: {survivors}\n"
        f"Scene void level at close: {snapshot.get('scene_void_level')}\n\n"
        f"Design a continuation set {time_jump}. The old outcome is now established "
        f"history that shaped the world. Return a JSON object with:\n"
        f"  - time_jump_label: short phrase (e.g. '{time_jump}')\n"
        f"  - premise: 2-3 sentences on what the world/these people became, treating "
        f"the prior outcome as the seed.\n"
        f"  - scenario_hint: a DM-facing setup paragraph for the new session. State the "
        f"NEW central dramatic question and say the session ends when its terminal clock "
        f"fills. Reference the prior verdict as backstory.\n"
        f"  - starting_clocks: array of 2-3 clocks. Each: name, max_ticks (4-8), "
        f"description (>=10 chars), advance_meaning, regress_meaning, filled_consequence. "
        f"EXACTLY ONE clock must have is_terminal_clock=true and a terminal_outcome of "
        f"victory/defeat/draw -- the clock that resolves this new chapter."
    )

    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = 2000  # gpt-5 family: default temp, completion-tokens param
    else:
        kwargs["temperature"] = 1.0
        kwargs["max_tokens"] = 2000

    resp = client.chat.completions.create(**kwargs)
    return json.loads(resp.choices[0].message.content)


# Words that signal a clock is the one that RESOLVES a chapter (used to pick the
# terminal clock when the LLM forgets to flag one -- which it reliably does).
_RESOLUTION_WORDS = (
    "verdict", "adjudication", "judgment", "judgement", "ruling", "decision",
    "final", "reckoning", "confrontation", "showdown", "resolution", "trial",
    "decisive", "fate", "sentence",
)


def ensure_one_terminal(clocks: list, default_outcome: str = "draw") -> list:
    """Guarantee EXACTLY one terminal clock.

    The leap LLM almost never sets is_terminal_clock, so we enforce it: keep the
    first clock already flagged terminal (clearing any others), otherwise designate
    one by resolution-keyword score, falling back to the last clock (LLMs tend to
    order clocks build-up -> resolution).
    """
    if not clocks:
        return clocks

    flagged = [i for i, c in enumerate(clocks) if c.get("is_terminal_clock")]
    if flagged:
        keep = flagged[0]
    else:
        def score(c):
            text = f"{c.get('name','')} {c.get('description','')} {c.get('filled_consequence','')}".lower()
            return sum(w in text for w in _RESOLUTION_WORDS)
        scored = [(score(c), i) for i, c in enumerate(clocks)]
        best = max(scored)
        keep = best[1] if best[0] > 0 else len(clocks) - 1

    for i, c in enumerate(clocks):
        if i == keep:
            c["is_terminal_clock"] = True
            c.setdefault("terminal_outcome", default_outcome)
            if c.get("terminal_outcome") not in ("victory", "defeat", "draw"):
                c["terminal_outcome"] = default_outcome
        else:
            c["is_terminal_clock"] = False
            c.pop("terminal_outcome", None)
    return clocks


def carry_forward_characters(base_config: dict, snapshot: dict) -> list:
    """Copy surviving players from the base config, evolving void from the snapshot."""
    survivors = {p["name"]: p for p in snapshot.get("party", []) if not p.get("is_defeated")}
    out = []
    for player in base_config.get("agents", {}).get("players", []):
        snap_p = survivors.get(player["name"])
        if snap_p is None:
            continue  # defeated / no longer present
        carried = copy.deepcopy(player)
        if snap_p.get("void_score") is not None:
            carried["void"] = snap_p["void_score"]  # evolved state persists across the jump
        out.append(carried)
    return out


def build_continuation(base_config: dict, snapshot: dict, leap: dict, time_jump: str) -> dict:
    cont = {
        "_role": "Resolve-then-leap continuation generated from a prior session's end_state_snapshot.",
        "_continuation_of": {
            "prior_outcome": snapshot.get("outcome"),
            "resolved_by_clock": snapshot.get("resolved_by_clock"),
            "resolution": snapshot.get("resolution"),
            "time_jump": leap.get("time_jump_label", time_jump),
            "premise": leap.get("premise"),
        },
        "session_name": f"Continuation ({leap.get('time_jump_label', time_jump)}) - {leap.get('premise','')[:60]}",
        "max_turns": base_config.get("max_turns", 6),
        "tactical_module_enabled": False,
        "enemy_agents_enabled": False,
        "vendor_spawn_frequency": 0,
        "scenario_hint": leap.get("scenario_hint", ""),
        "starting_clocks": ensure_one_terminal(leap.get("starting_clocks", [])),
        "agents": {
            "dm": base_config.get("agents", {}).get("dm", {}),
            "players": carry_forward_characters(base_config, snapshot),
        },
        "enable_human_interface": False,
    }
    cont["party_size"] = len(cont["agents"]["players"])
    return cont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="finished session JSONL")
    ap.add_argument("--base-config", required=True, help="original session config (for llm/character sheets)")
    ap.add_argument("--time-jump", default="three years later")
    ap.add_argument("--model", default="gpt-5.4-mini")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-llm", action="store_true", help="skip the leap call (deterministic stub)")
    args = ap.parse_args()

    snapshot = read_snapshot(args.session)
    base_config = json.loads(Path(args.base_config).read_text())

    # Continuation is gated on SURVIVORS, not on outcome. A victory/draw or even a
    # defeat WITH survivors (captured, routed) can continue; a TPK / no-survivors
    # ending has nobody to carry forward -- the saga ends. (A fresh-cast "anthology"
    # leap would be a deliberate opt-in, not a silent default, so we refuse here.)
    survivors = [p for p in snapshot.get("party", []) if not p.get("is_defeated")]
    if not survivors:
        print(
            f"✋ No surviving party members in this ending (outcome={snapshot.get('outcome')}). "
            f"Nothing to carry forward -- the saga ends here. "
            f"(A new-cast anthology continuation would be a separate, deliberate choice.)"
        )
        sys.exit(2)

    if args.no_llm:
        leap = {
            "time_jump_label": args.time_jump,
            "premise": f"(stub) {args.time_jump}, the consequences of a {snapshot.get('outcome')} ruling settle in.",
            "scenario_hint": "(stub - run without --no-llm to generate the leap)",
            "starting_clocks": [],
        }
    else:
        leap = imagine_leap(snapshot, args.time_jump, args.model)

    cont = build_continuation(base_config, snapshot, leap, args.time_jump)
    Path(args.out).write_text(json.dumps(cont, indent=2))
    print(f"✓ Wrote continuation config: {args.out}")
    print(f"  time jump : {cont['_continuation_of']['time_jump']}")
    print(f"  premise   : {cont['_continuation_of']['premise']}")
    print(f"  survivors : {[p['name'] for p in cont['agents']['players']]}")
    term = [c for c in cont['starting_clocks'] if c.get('is_terminal_clock')]
    print(f"  clocks    : {[c['name'] for c in cont['starting_clocks']]}")
    print(f"  terminal  : {[ (c['name'], c.get('terminal_outcome')) for c in term ]}")


if __name__ == "__main__":
    main()
