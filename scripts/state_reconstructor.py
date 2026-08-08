#!/usr/bin/env python3
"""Resume-from-divergence state reconstruction (replay rung 3).

Folds a recorded session's events to the end of round K-1 and emits a resume
config that seeds a LIVE session at round K — the prefix is loaded, never
replayed, so a code change diverging at round K is verified by paying tokens
only for rounds K..end. (Design call: after the cheap detectors — the
mechanics-diff harness or a semantic cache miss — pick K, resume live from
there; no MockLLMProvider prefix machinery.)

Sources, per .claude/REPLAY_RESUME_FEASIBILITY.md (verified, not assumed):
  party   — per-round character_state (exact end-of-round snapshot: vitals,
            purse, seeds, position, conditions)
  enemies — enemy_spawn stats -> latest enemy character_state <= K-1 ->
            any later combat_action.defender_state_after / healing_applied;
            minus enemy_defeat-ed / departed ids
  clocks  — latest action_resolution.clocks reading ("cur/max" strings),
            metadata merged from clock_spawn/clock_advancement, minus
            clock_removal <= K-1
  void    — latest void_level_update else scenario.void_level
  story   — scenario event + round_synthesis <= K-1 (the DM's continuity)

Seeding rides EXISTING config surfaces where possible: starting_clocks
(supports current_ticks), initial_enemies (archetype carries the exact
"#N"-suffixed name so f"{faction} {archetype}" reproduces recorded names),
force_scenario (extended to accept a dict). Exact vitals land via the one new
seam: a `resume_state` config block applied by the session after scenario
setup (see session._apply_resume_state).

Usage:
    python scripts/state_reconstructor.py session.jsonl --resume-round 3 \
        --out resume_config.json
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResumeState:
    resume_round: int
    party: List[Dict[str, Any]] = field(default_factory=list)
    enemies: List[Dict[str, Any]] = field(default_factory=list)
    clocks: List[Dict[str, Any]] = field(default_factory=list)
    void_level: int = 0
    scenario: Dict[str, Any] = field(default_factory=dict)
    story_so_far: str = ""
    warnings: List[str] = field(default_factory=list)


def _rnd(e) -> Optional[int]:
    r = e.get("round")
    return r if isinstance(r, int) else None


def reconstruct(events: List[Dict[str, Any]], resume_round: int) -> ResumeState:
    """Fold events to the end of round K-1 (K = resume_round)."""
    cutoff = resume_round - 1
    rs = ResumeState(resume_round=resume_round)

    # --- scenario + story ---------------------------------------------------
    scen = next((e for e in events if e.get("event_type") == "scenario"), None)
    if scen:
        rs.scenario = dict(scen.get("scenario") or {})
        rs.void_level = rs.scenario.get("void_level", 0) or 0
    for e in events:
        if e.get("event_type") == "void_level_update" and (_rnd(e) or 0) <= cutoff:
            body = e.get("data") if isinstance(e.get("data"), dict) else e
            rs.void_level = body.get("new_level", body.get("void_level", rs.void_level))
    syntheses = [(e.get("round"), e.get("synthesis", ""))
                 for e in events
                 if e.get("event_type") == "round_synthesis"
                 and (_rnd(e) or 0) <= cutoff]
    rs.story_so_far = "\n\n".join(
        f"[Round {r}] {s}" for r, s in syntheses if s)

    # --- party (exact per-round snapshots) -----------------------------------
    latest_pc: Dict[str, Dict[str, Any]] = {}
    for e in events:
        if e.get("event_type") != "character_state":
            continue
        if e.get("agent") == "enemy":
            continue
        r = _rnd(e)
        if r is None or r > cutoff:
            continue
        prev = latest_pc.get(e.get("character_id"))
        if prev is None or (_rnd(prev) or 0) <= r:
            latest_pc[e.get("character_id")] = e
    for cid, e in latest_pc.items():
        rs.party.append({
            "name": e.get("character_name"),
            "character_id": cid,
            "health": e.get("health"), "max_health": e.get("max_health"),
            "wounds": e.get("wounds", 0), "stuns": e.get("stuns", 0),
            "void_score": e.get("void_score", 0),
            "soulcredit": e.get("soulcredit", 0),
            "position": e.get("position"),
            "energy": e.get("energy") or {},
            "seeds": e.get("seeds") or {},
            "conditions": e.get("conditions") or [],
        })

    # --- enemies (spawn -> snapshot -> combat fold) --------------------------
    spawns: Dict[str, Dict[str, Any]] = {}
    for e in events:
        if e.get("event_type") == "enemy_spawn" and (_rnd(e) or 0) <= cutoff:
            spawns[e.get("enemy_id")] = e
    gone = {e.get("enemy_id") for e in events
            if e.get("event_type") == "enemy_defeat" and (_rnd(e) or 0) <= cutoff}
    # conversions to NPC leave the enemy roster too
    for e in events:
        if e.get("event_type") == "agent_conversion" and (_rnd(e) or 0) <= cutoff:
            body = e.get("data") if isinstance(e.get("data"), dict) else e
            for k in ("agent_id", "enemy_id"):
                if body.get(k):
                    gone.add(body[k])

    for eid, sp in spawns.items():
        if eid in gone:
            continue
        stats = sp.get("stats") or {}
        state = {
            "health": stats.get("health"), "max_health": stats.get("max_health"),
            "wounds": 0, "stuns": 0,
            "position": sp.get("position"),
        }
        state_round = -1
        # overlay latest enemy character_state
        for e in events:
            if (e.get("event_type") == "character_state" and e.get("agent") == "enemy"
                    and e.get("character_id") == eid):
                r = _rnd(e)
                if r is not None and r <= cutoff and r >= state_round:
                    state_round = r
                    state.update({
                        "health": e.get("health"), "max_health": e.get("max_health"),
                        "wounds": e.get("wounds", 0), "stuns": e.get("stuns", 0),
                        "position": e.get("position", state["position"]),
                    })
        # overlay combat/healing at or after the snapshot round (same-round events
        # postdate the end-of-round snapshot only if the snapshot round is older)
        for e in events:
            r = _rnd(e)
            if r is None or r > cutoff or r < state_round:
                continue
            if e.get("event_type") == "combat_action" \
                    and (e.get("defender") or {}).get("id") == eid:
                after = e.get("defender_state_after") or {}
                if r > state_round and after:
                    for k_src, k_dst in (("health", "health"), ("wounds", "wounds"),
                                         ("stuns", "stuns")):
                        if k_src in after:
                            state[k_dst] = after[k_src]
            elif e.get("event_type") == "healing_applied" \
                    and e.get("target_id") == eid and r > state_round:
                after = e.get("target_state_after") or {}
                if "health" in after:
                    state["health"] = after["health"]

        name = sp.get("enemy_name") or eid
        faction = sp.get("faction") or "Hostile"
        # archetype such that the spawner's f"{faction} {archetype}" == name
        archetype = name[len(faction):].strip() if name.startswith(faction) else name
        rs.enemies.append({
            "enemy_id": eid, "name": name, "faction": faction,
            "archetype": archetype,
            "template": (sp.get("template") or "Grunt").lower(),
            "position": state["position"],
            "health": state["health"], "max_health": state["max_health"],
            "wounds": state["wounds"], "stuns": state["stuns"],
            "stats": stats,  # full sheet for reference/debugging
        })

    # --- clocks --------------------------------------------------------------
    readings: Dict[str, Dict[str, Any]] = {}   # name -> {current, max, round}
    meta: Dict[str, Dict[str, Any]] = {}
    removed = set()
    for e in events:
        r = _rnd(e)
        if r is None or r > cutoff:
            continue
        et = e.get("event_type")
        body = e.get("data") if isinstance(e.get("data"), dict) else e
        if et == "action_resolution":
            for name, s in (e.get("clocks") or {}).items():
                try:
                    cur, mx = (int(x) for x in str(s).split("/", 1))
                except (ValueError, AttributeError):
                    continue
                prev = readings.get(name)
                if prev is None or r >= prev["round"]:
                    readings[name] = {"current": cur, "max": mx, "round": r}
        elif et in ("clock_spawn", "clock_advancement", "clock_update"):
            name = body.get("clock_name")
            if not name:
                continue
            m = meta.setdefault(name, {})
            for k in ("description", "advance_meaning", "regress_meaning",
                      "filled_consequence"):
                if body.get(k):
                    m[k] = body[k]
            cur = body.get("after_ticks", body.get("current_ticks"))
            mx = body.get("maximum_ticks", body.get("max_ticks"))
            if cur is not None and mx is not None:
                prev = readings.get(name)
                if prev is None or r >= prev["round"]:
                    readings[name] = {"current": cur, "max": mx, "round": r}
        elif et in ("clock_removal", "clock_completion"):
            if body.get("clock_name"):
                removed.add(body["clock_name"])

    for name, rd in readings.items():
        if name in removed:
            continue
        m = meta.get(name, {})
        # config validation requires non-empty meanings; recordings often carry
        # empty ones, so fall back to honest placeholders
        rs.clocks.append({
            "name": name,
            "current_ticks": rd["current"], "max_ticks": rd["max"],
            "description": m.get("description") or f"(resumed) {name}",
            "advance_meaning": m.get("advance_meaning") or f"{name} draws closer",
            "regress_meaning": m.get("regress_meaning") or f"{name} recedes",
            "filled_consequence": m.get("filled_consequence")
                                  or f"{name} comes to pass",
        })

    if not rs.party:
        rs.warnings.append("no party character_state found at or before the cutoff")
    return rs


def build_resume_config(original_config: Dict[str, Any], rs: ResumeState) -> Dict[str, Any]:
    """Emit a session config that seeds a live session at rs.resume_round."""
    cfg = copy.deepcopy(original_config)
    k = rs.resume_round

    cfg["session_name"] = f"{cfg.get('session_name', 'session')}_resume_r{k}"
    if isinstance(cfg.get("max_turns"), int):
        cfg["max_turns"] = max(1, cfg["max_turns"] - (k - 1))

    cfg["starting_clocks"] = rs.clocks

    # one initial_enemies entry per survivor; archetype carries the "#N" suffix
    # so the spawner's f"{faction} {archetype}" reproduces the recorded name
    cfg["initial_enemies"] = [
        {"name": e["name"], "faction": e["faction"], "archetype": e["archetype"],
         "template": e["template"], "count": 1,
         "position": e["position"] or "Near-Enemy",
         "spawn_reason": f"(resumed at round {k}) survivor of rounds 1-{k - 1}"}
        for e in rs.enemies
    ]
    cfg.pop("initial_npcs", None)  # NPC resume not yet supported (documented gap)

    situation = rs.scenario.get("situation", "")
    # strip legacy spawn markers: the resumed roster comes from initial_enemies;
    # replaying a recorded [SPAWN_ENEMY: ...] would double-spawn
    situation = re.sub(r"\s*\[SPAWN_ENEMY:[^\]]*\]", "", situation)
    if rs.story_so_far:
        situation = (f"{situation}\n\nSTORY SO FAR (rounds 1-{k - 1}, already "
                     f"played — continue from here, do not restart):\n{rs.story_so_far}")
    cfg["force_scenario"] = {
        "theme": rs.scenario.get("theme", "Resumed Session"),
        "location": rs.scenario.get("location", "Unknown"),
        "situation": situation,
        "void_level": rs.void_level,
    }

    cfg["resume_state"] = {
        "resume_round": k,
        "party": rs.party,
        "enemies": [{k2: e[k2] for k2 in
                     ("name", "health", "max_health", "wounds", "stuns", "position")}
                    for e in rs.enemies],
    }
    return cfg


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fold a session to round K-1 and emit a resume config.")
    ap.add_argument("session", help="recorded session JSONL")
    ap.add_argument("--resume-round", type=int, required=True,
                    help="round K to resume at (state folds to end of K-1)")
    ap.add_argument("--out", required=True, help="path for the resume config JSON")
    args = ap.parse_args(argv)

    events = []
    with open(args.session) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    start = next((e for e in events if e.get("event_type") == "session_start"), None)
    if not start or not isinstance(start.get("config"), dict):
        print("error: session has no session_start.config to base the resume on",
              file=sys.stderr)
        return 2

    rs = reconstruct(events, args.resume_round)
    for w in rs.warnings:
        print(f"warning: {w}", file=sys.stderr)
    cfg = build_resume_config(start["config"], rs)
    with open(args.out, "w") as f:
        json.dump(cfg, f, indent=1)

    print(f"resume config written: {args.out}")
    print(f"  resume at round {args.resume_round}: party={len(rs.party)} "
          f"enemies={len(rs.enemies)} clocks={len(rs.clocks)} "
          f"void={rs.void_level} max_turns={cfg.get('max_turns')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
