#!/usr/bin/env python3
"""
Compute grand totals across all 20 original (non-Claude) sessions from the
lethality experiment combat ambush control run.

Outputs:
  1. Total player action_declarations (player_id starts with "player_")
  2. Total action_resolutions matched to player declarations
  3. Overall intent distribution (keyword classification)
  4. Grand total enemies spawned, defeated (by defeat_reason)
  5. Grand total NPC actions by type
  6. Grand total soulcredit changes (from character_state diffs)
"""

import json
import glob
import os
from collections import defaultdict

BASE_DIR = (
    "/home/p/Coding/aeonisk-yags/multiagent_output/"
    "lethality_experiment_combat_ambush/control/models/"
    "run_2026-02-14_113048_5276cf26"
)

# 20 successful runs (excluding failed Claude runs: 4, 9, 14, 19, 24)
# Actual model mapping from configs:
#   Runs ending in 1,6: OpenAI/GPT-5.2
#   Runs ending in 2,7: Grok 4
#   Runs ending in 3,8: Gemini 2.5 Pro
#   Runs ending in 4,9: Anthropic/Claude (all failed)
#   Runs ending in 5,0: DeepSeek V3.2
SUCCESSFUL_RUNS = [
    1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 20, 21, 22, 23, 25
]

MODEL_MAP = {}
for r in SUCCESSFUL_RUNS:
    last_digit = r % 5
    if last_digit == 1:
        MODEL_MAP[r] = "GPT-5.2"
    elif last_digit == 2:
        MODEL_MAP[r] = "Grok 4"
    elif last_digit == 3:
        MODEL_MAP[r] = "Gemini 2.5 Pro"
    elif last_digit == 0:
        MODEL_MAP[r] = "DeepSeek V3.2"

# ── Intent Classification Keywords (same as deep_action_analysis.py) ────────

SUPPRESSING_KW = [
    "suppress", "suppressing", "suppressive", "cover fire", "covering fire",
    "warning shot", "pin down", "pinned", "keep heads down", "lay down fire",
    "pin them", "pins them", "pinning",
]

NON_LETHAL_KW = [
    "shock baton", "baton", "stun", "non-lethal", "nonlethal", "subdue",
    "restrain", "cuffs", "knockout", "incapacitate", "taser", "capture alive",
    "restraint", "shock_baton",
]

DEFENSIVE_KW = [
    "take cover", "taking cover", "find cover", "dodge", "retreat",
    "reposition", "hunker", "duck", "fall back", "pull back", "disengage",
    "evade", "evasive", "behind cover", "into cover", "seek cover",
]

SOCIAL_KW = [
    "intimidate", "intimidation", "surrender", "negotiate", "de-escalate",
    "deescalate", "demand", "threaten", "order to", "stand down", "call out",
    "yell at", "shout", "warning", "bark", "command",
]

LETHAL_KW = [
    "shoot", "fire", "attack", "strike", "blast", "kill", "aim",
    "rifle", "shotgun", "pistol", "knife", "stab", "slash", "burst",
    "trigger", "round", "shot", "headshot", "center mass", "combat_knife",
    "cutting", "lethal",
]


def classify_intent(intent_text, description_text):
    """Classify a player action based on intent + description text."""
    combined = f"{intent_text or ''} {description_text or ''}".lower()

    # Check in priority order (suppressive before lethal)
    for kw in SUPPRESSING_KW:
        if kw in combined:
            return "suppressing_fire"
    for kw in NON_LETHAL_KW:
        if kw in combined:
            return "non_lethal"
    for kw in DEFENSIVE_KW:
        if kw in combined:
            return "defensive"
    for kw in SOCIAL_KW:
        if kw in combined:
            return "social"
    for kw in LETHAL_KW:
        if kw in combined:
            return "lethal_attack"
    return "other"


def load_events(run_id):
    """Load all events from a session JSONL file."""
    run_dir = os.path.join(BASE_DIR, f"run_{run_id:04d}")
    files = glob.glob(os.path.join(run_dir, "session_*.jsonl"))
    if not files:
        return []
    events = []
    with open(files[0], "r") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def main():
    # Accumulators
    total_player_declarations = 0
    total_player_resolutions = 0
    intent_counts = defaultdict(int)
    total_enemies_spawned = 0
    total_enemies_defeated = 0
    defeat_reasons = defaultdict(int)
    npc_actions_by_type = defaultdict(int)
    total_npc_actions = 0
    soulcredit_changes = []  # list of (run, character, start_sc, end_sc, delta)

    # Action type distribution from schema (context.action_type)
    action_type_counts = defaultdict(int)

    for run_id in SUCCESSFUL_RUNS:
        events = load_events(run_id)
        if not events:
            print(f"WARNING: No events for run_{run_id:04d}")
            continue

        # ── 1. Player action declarations ────────────────────────────────
        player_decls = [
            e for e in events
            if e.get("event_type") == "action_declaration"
            and e.get("player_id", "").startswith("player_")
        ]
        total_player_declarations += len(player_decls)

        # ── 2. Action resolutions matched to players ─────────────────────
        # Build resolution index by (round, agent_name)
        resolutions_by_key = defaultdict(list)
        for e in events:
            if e.get("event_type") == "action_resolution":
                phase = e.get("phase", "")
                if "enemy" in phase or "npc" in phase:
                    continue
                agent = e.get("agent", "")
                rd = e.get("round")
                resolutions_by_key[(rd, agent)].append(e)

        matched = 0
        for decl in player_decls:
            rd = decl.get("round")
            char_name = decl.get("character_name", "")
            if (rd, char_name) in resolutions_by_key:
                matched += 1
        total_player_resolutions += matched

        # ── 3. Intent classification ─────────────────────────────────────
        for decl in player_decls:
            action = decl.get("action", {})
            if isinstance(action, dict):
                intent_text = action.get("intent", action.get("major_action", ""))
                desc_text = action.get("description", "")
            else:
                intent_text = str(action)
                desc_text = ""
            category = classify_intent(intent_text, desc_text)
            intent_counts[category] += 1

        # Action type from resolution context
        for e in events:
            if e.get("event_type") == "action_resolution":
                phase = e.get("phase", "")
                if "enemy" in phase or "npc" in phase:
                    continue
                # Check if this is a player resolution
                agent = e.get("agent", "")
                ctx = e.get("context", {})
                if isinstance(ctx, dict):
                    at = ctx.get("action_type", "unknown")
                else:
                    at = "unknown"
                # Only count if agent matches a player character
                rd = e.get("round")
                if (rd, agent) in {(d.get("round"), d.get("character_name")) for d in player_decls}:
                    action_type_counts[at] += 1

        # ── 4. Enemies spawned and defeated ──────────────────────────────
        spawned = [e for e in events if e.get("event_type") == "enemy_spawn"]
        defeated = [e for e in events if e.get("event_type") == "enemy_defeat"]
        total_enemies_spawned += len(spawned)
        total_enemies_defeated += len(defeated)
        for e in defeated:
            reason = e.get("defeat_reason", "unknown")
            defeat_reasons[reason] += 1

        # ── 5. NPC actions ───────────────────────────────────────────────
        npc_decls = [
            e for e in events
            if e.get("event_type") == "action_declaration"
            and e.get("player_id", "").startswith("npc_")
        ]
        total_npc_actions += len(npc_decls)
        for e in npc_decls:
            action = e.get("action", {})
            if isinstance(action, dict):
                act_type = action.get("major_action", "unknown")
            else:
                act_type = "unknown"
            npc_actions_by_type[act_type or "unknown"] += 1

        # ── 6. Soulcredit changes ────────────────────────────────────────
        # Track via character_state events (first vs last per character)
        sc_first = {}
        sc_last = {}
        for e in events:
            if e.get("event_type") == "character_state" and e.get("agent") == "player":
                name = e["character_name"]
                sc = e.get("soulcredit", 0)
                if name not in sc_first:
                    sc_first[name] = sc
                sc_last[name] = sc
        for name in sc_first:
            delta = sc_last[name] - sc_first[name]
            if delta != 0:
                soulcredit_changes.append((run_id, name, sc_first[name], sc_last[name], delta))

    # ── Print Results ────────────────────────────────────────────────────────

    print("=" * 70)
    print("GRAND TOTALS: 20 Original Sessions (non-Claude)")
    print("=" * 70)

    print(f"\n1. PLAYER ACTION DECLARATIONS")
    print(f"   Total: {total_player_declarations}")

    print(f"\n2. PLAYER ACTION RESOLUTIONS (matched to declarations)")
    print(f"   Total: {total_player_resolutions}")
    print(f"   Unmatched: {total_player_declarations - total_player_resolutions}")
    print(f"   Match rate: {total_player_resolutions/total_player_declarations*100:.1f}%")

    print(f"\n3. INTENT DISTRIBUTION (keyword classification)")
    ordered = sorted(intent_counts.items(), key=lambda x: -x[1])
    for cat, count in ordered:
        pct = count / total_player_declarations * 100
        print(f"   {cat:20s}: {count:4d}  ({pct:5.1f}%)")
    print(f"   {'TOTAL':20s}: {total_player_declarations:4d}")

    print(f"\n   ACTION_TYPE DISTRIBUTION (from schema context.action_type):")
    ordered_at = sorted(action_type_counts.items(), key=lambda x: -x[1])
    at_total = sum(action_type_counts.values())
    for at, count in ordered_at:
        pct = count / at_total * 100 if at_total else 0
        print(f"   {at:20s}: {count:4d}  ({pct:5.1f}%)")
    print(f"   {'TOTAL':20s}: {at_total:4d}")

    print(f"\n4. ENEMIES")
    print(f"   Spawned: {total_enemies_spawned}")
    print(f"   Defeated: {total_enemies_defeated}")
    print(f"   Defeat reasons:")
    for reason, count in sorted(defeat_reasons.items(), key=lambda x: -x[1]):
        print(f"     {reason:20s}: {count:4d}")

    print(f"\n5. NPC ACTIONS")
    print(f"   Total NPC action declarations: {total_npc_actions}")
    print(f"   By type:")
    for act_type, count in sorted(npc_actions_by_type.items(), key=lambda x: -x[1]):
        print(f"     {act_type:20s}: {count:4d}")

    print(f"\n6. SOULCREDIT CHANGES")
    print(f"   Characters with changes: {len(soulcredit_changes)}")
    total_positive = sum(d for _, _, _, _, d in soulcredit_changes if d > 0)
    total_negative = sum(d for _, _, _, _, d in soulcredit_changes if d < 0)
    net = total_positive + total_negative
    print(f"   Total positive: +{total_positive}")
    print(f"   Total negative: {total_negative}")
    print(f"   Net: {net}")
    print(f"   Detail:")
    for run_id, name, start, end, delta in soulcredit_changes:
        sign = "+" if delta > 0 else ""
        model = MODEL_MAP.get(run_id, "?")
        print(f"     Run {run_id:04d} ({model:15s}): {name:25s} {start} -> {end} ({sign}{delta})")

    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70)


if __name__ == "__main__":
    main()
