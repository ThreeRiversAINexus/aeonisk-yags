#!/usr/bin/env python3
"""
Intention-Lethality Mismatch Analysis
======================================
Mines 20 successful YAGS session JSONL files to analyze the gap between
player-declared action intentions and DM-resolved mechanical outcomes.

Focus: Do suppressing fire / non-lethal declarations get resolved as lethal damage?
"""

import json
import glob
import os
import re
from collections import defaultdict, Counter
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

BASE_DIR = "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_113048_5276cf26"

SUCCESSFUL_RUNS = [
    "run_0001", "run_0002", "run_0003", "run_0005", "run_0006",
    "run_0007", "run_0008", "run_0010", "run_0011", "run_0012",
    "run_0013", "run_0015", "run_0016", "run_0017", "run_0018",
    "run_0020", "run_0021", "run_0022", "run_0023", "run_0025",
]

PLAYER_NAMES = {
    "player_01": "Kael (Enforcer)",
    "player_02": "Sable (Drifter)",
}

# ============================================================================
# Classification Keywords
# ============================================================================

def classify_action(text):
    """Classify a player action declaration into intention categories."""
    t = text.lower()

    # Check suppressing/covering fire FIRST (before generic "fire"/"shoot")
    suppression_kw = [
        "suppressing", "suppress", "suppressive", "cover fire", "covering fire",
        "warning shot", "warning shots", "pin down", "pinned down", "keep heads down",
        r"keep .* heads down", "pin them", "lay down fire", "laying down fire",
        r"force .* into cover", r"force .* behind cover", r"drive .* into cover",
        r"keep .* pinned", "discourage", "deter",
    ]
    for kw in suppression_kw:
        if re.search(kw, t):
            return "suppressing_fire"

    # Non-lethal
    nonlethal_kw = [
        "shock baton", "shock-baton", "stun", "non-lethal", "nonlethal",
        "non lethal", "subdue", "restrain", "restraint", "cuffs",
        "knockout", "knock out", r"knock .* out", "incapacitate",
        r"take .* alive", "capture", "disable without",
        "baton", "taser", "tranq",
    ]
    for kw in nonlethal_kw:
        if re.search(kw, t):
            return "non_lethal"

    # Defensive
    defensive_kw = [
        "take cover", "takes cover", "taking cover", "find cover", "behind cover",
        "dodge", "dodging", "retreat", "retreating", "reposition", "repositioning",
        "defensive", "hunker", "hunker down", "duck", "drop prone", "fall back",
        "pull back", "disengage", "evade", "evasive",
    ]
    for kw in defensive_kw:
        if re.search(kw, t):
            return "defensive"

    # Social
    social_kw = [
        "intimidate", "intimidation", "surrender", "negotiate", "negotiation",
        "de-escalate", "deescalate", "call out", "demand", "threaten",
        "persuade", "diplomacy", "talk", r"shout .* warning", "verbal",
        r"yell .* to stop", r"order .* to",
    ]
    for kw in social_kw:
        if re.search(kw, t):
            return "social"

    # Lethal attack (generic combat)
    lethal_kw = [
        "shoot", "shoots", "shooting", "fire", "fires", "firing",
        "attack", "attacks", "attacking", "strike", "strikes", "striking",
        "slash", "slashes", "slashing", "stab", "stabs", "stabbing",
        "blast", "blasts", "aim", "aims", "aiming", "snipe", "snipes",
        "rifle", "shotgun", "pistol", "gun", "knife", "blade",
        "kill", "killing", "lethal", "neutralize", "eliminate",
        "burst", "round", "shot", "shots",
        "combat_knife", "combat knife",
    ]
    for kw in lethal_kw:
        if re.search(r'\b' + kw + r'\b', t):
            return "lethal_attack"

    return "other"


# ============================================================================
# Data Mining
# ============================================================================

def load_session_events(run_dir):
    """Load all events from a session JSONL file."""
    jsonl_files = glob.glob(os.path.join(run_dir, "session_*.jsonl"))
    if not jsonl_files:
        return []
    events = []
    with open(jsonl_files[0]) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def get_model_from_config(run_dir):
    """Extract model name from config.json."""
    config_path = os.path.join(run_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
        return cfg.get("agents", {}).get("dm", {}).get("llm", {}).get("model", "unknown")
    return "unknown"


def extract_player_declarations(events):
    """Extract all player action declarations."""
    declarations = []
    for e in events:
        if e.get("event_type") != "action_declaration":
            continue
        player_id = e.get("player_id", "")
        if not player_id.startswith("player_"):
            continue
        action = e.get("action", {})
        if isinstance(action, dict):
            # Rich player action
            decl_text = action.get("intent", "") or action.get("description", "") or ""
            full_desc = action.get("description", "")
            weapon = None
            target = action.get("target", None)
            target_char = action.get("target_character", None)
            action_type = action.get("action_type", "")
        else:
            # Simple action (e.g., enemy format)
            decl_text = str(action)
            full_desc = ""
            weapon = None
            target = None
            target_char = None
            action_type = ""

        declarations.append({
            "player_id": player_id,
            "character_name": e.get("character_name", ""),
            "round": e.get("round"),
            "intent": decl_text,
            "description": full_desc,
            "action_type": action_type,
            "target": target,
            "target_character": target_char,
            "correlation_id": e.get("correlation_id"),
            "event_id": e.get("event_id"),
        })
    return declarations


def find_matching_resolution(events, declaration):
    """Find the action_resolution matching a declaration."""
    rnd = declaration["round"]
    char_name = declaration["character_name"]

    for e in events:
        if e.get("event_type") != "action_resolution":
            continue
        if e.get("round") != rnd:
            continue
        # Match by agent name (character name) in resolution
        agent = e.get("agent", "")
        if agent != char_name:
            continue
        # Also check phase is player adjudication (not enemy)
        phase = e.get("phase", "")
        if "enemy" in phase or "npc" in phase:
            continue
        return e
    return None


# ============================================================================
# Main Analysis
# ============================================================================

def main():
    all_declarations = []
    session_count = 0
    category_counts = Counter()
    per_player_category = defaultdict(Counter)

    suppression_cases = []
    nonlethal_cases = []
    defensive_cases = []
    social_cases = []

    for run_name in SUCCESSFUL_RUNS:
        run_dir = os.path.join(BASE_DIR, run_name)
        if not os.path.isdir(run_dir):
            print(f"WARNING: {run_dir} not found, skipping")
            continue

        model = get_model_from_config(run_dir)
        events = load_session_events(run_dir)
        if not events:
            print(f"WARNING: No events in {run_name}, skipping")
            continue

        session_count += 1
        declarations = extract_player_declarations(events)

        for decl in declarations:
            text_to_classify = decl["intent"]
            if not text_to_classify:
                text_to_classify = decl["description"]
            category = classify_action(text_to_classify)

            resolution = find_matching_resolution(events, decl)

            res_data = {}
            if resolution:
                effects = resolution.get("effects", {})
                damage = effects.get("damage")
                damage_dealt = 0
                damage_target = None
                if damage and isinstance(damage, dict):
                    damage_dealt = damage.get("dealt", 0) or 0
                    damage_target = damage.get("target")

                roll = resolution.get("roll", {})
                context = resolution.get("context", {})
                narration = context.get("narration", "")
                dm_description = context.get("description", "")

                damage_effects = context.get("damage_effects", [])
                total_damage_from_effects = sum(
                    de.get("dealt", 0) or 0 for de in (damage_effects or [])
                )

                res_data = {
                    "damage_dealt": damage_dealt,
                    "damage_from_effects": total_damage_from_effects,
                    "damage_target": damage_target,
                    "roll_success": roll.get("success"),
                    "roll_tier": roll.get("tier"),
                    "roll_margin": roll.get("margin"),
                    "roll_total": roll.get("total"),
                    "roll_dc": roll.get("dc"),
                    "narration": narration[:500] if narration else "",
                    "dm_description": dm_description[:300] if dm_description else "",
                    "action_type_resolved": context.get("action_type", ""),
                    "soulcredit_reasons": resolution.get("economy", {}).get("soulcredit_reasons", []),
                }

            enriched = {
                **decl,
                "category": category,
                "model": model,
                "run": run_name,
                "resolution": res_data,
            }
            all_declarations.append(enriched)
            category_counts[category] += 1
            per_player_category[decl["player_id"]][category] += 1

            if category == "suppressing_fire":
                suppression_cases.append(enriched)
            elif category == "non_lethal":
                nonlethal_cases.append(enriched)
            elif category == "defensive":
                defensive_cases.append(enriched)
            elif category == "social":
                social_cases.append(enriched)

    # ========================================================================
    # OUTPUT
    # ========================================================================

    print("=" * 100)
    print("INTENTION-LETHALITY MISMATCH ANALYSIS")
    print("=" * 100)
    print(f"\nSessions analyzed: {session_count}")
    print(f"Total player declarations: {len(all_declarations)}")
    print(f"Model: gpt-5.2-2025-12-11 (all sessions)")
    print()

    # ---- Summary Table ----
    print("-" * 100)
    print("SUMMARY: Player Action Declaration Categories")
    print("-" * 100)
    categories_ordered = [
        "lethal_attack", "suppressing_fire", "non_lethal",
        "defensive", "social", "other"
    ]

    print(f"{'Category':<22} {'Total':>7} {'player_01 (Kael)':>18} {'player_02 (Sable)':>19} {'% of Total':>12}")
    print("-" * 80)
    total = len(all_declarations)
    for cat in categories_ordered:
        cnt = category_counts.get(cat, 0)
        p1 = per_player_category.get("player_01", {}).get(cat, 0)
        p2 = per_player_category.get("player_02", {}).get(cat, 0)
        pct = (cnt / total * 100) if total > 0 else 0
        print(f"{cat:<22} {cnt:>7} {p1:>18} {p2:>19} {pct:>11.1f}%")
    print("-" * 80)
    p1_total = sum(per_player_category.get("player_01", {}).values())
    p2_total = sum(per_player_category.get("player_02", {}).values())
    print(f"{'TOTAL':<22} {total:>7} {p1_total:>18} {p2_total:>19} {'100.0%':>12}")
    print()

    # ---- Per-Round Breakdown ----
    print("-" * 100)
    print("PER-ROUND CATEGORY DISTRIBUTION")
    print("-" * 100)
    round_cats = defaultdict(Counter)
    for d in all_declarations:
        round_cats[d["round"]][d["category"]] += 1

    for rnd in sorted(round_cats.keys()):
        cats = round_cats[rnd]
        parts = [f"{cat}={cnt}" for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])]
        print(f"  Round {rnd}: {', '.join(parts)}")
    print()

    # ---- Detailed: Suppressing Fire ----
    print("=" * 100)
    print(f"SUPPRESSING FIRE DECLARATIONS: {len(suppression_cases)} found")
    print("=" * 100)
    if not suppression_cases:
        print("  (none found)")
    for i, case in enumerate(suppression_cases, 1):
        res = case.get("resolution", {})
        print(f"\n  [{i}] Run: {case['run']} | Round: {case['round']} | Agent: {case['player_id']} ({case['character_name']})")
        print(f"      INTENT: {case['intent'][:250]}")
        if case['description'] and case['description'] != case['intent']:
            print(f"      DESCRIPTION: {case['description'][:250]}")
        print(f"      CLASSIFICATION: {case['category']}")
        if res:
            print(f"      ROLL: success={res.get('roll_success')}, tier={res.get('roll_tier')}, margin={res.get('roll_margin')}, total={res.get('roll_total')} vs DC {res.get('roll_dc')}")
            print(f"      DAMAGE DEALT: {res.get('damage_dealt', 0)} (from effects: {res.get('damage_from_effects', 0)})")
            print(f"      SOULCREDIT REASONS: {res.get('soulcredit_reasons', [])}")
            narr = res.get('narration', '')
            if narr:
                print(f"      DM NARRATION: {narr[:500]}...")
        print()

    # ---- Detailed: Non-Lethal ----
    print("=" * 100)
    print(f"NON-LETHAL DECLARATIONS: {len(nonlethal_cases)} found")
    print("=" * 100)
    if not nonlethal_cases:
        print("  (none found)")
    for i, case in enumerate(nonlethal_cases, 1):
        res = case.get("resolution", {})
        print(f"\n  [{i}] Run: {case['run']} | Round: {case['round']} | Agent: {case['player_id']} ({case['character_name']})")
        print(f"      INTENT: {case['intent'][:250]}")
        if case['description'] and case['description'] != case['intent']:
            print(f"      DESCRIPTION: {case['description'][:250]}")
        print(f"      CLASSIFICATION: {case['category']}")
        if res:
            print(f"      ROLL: success={res.get('roll_success')}, tier={res.get('roll_tier')}, margin={res.get('roll_margin')}, total={res.get('roll_total')} vs DC {res.get('roll_dc')}")
            print(f"      DAMAGE DEALT: {res.get('damage_dealt', 0)} (from effects: {res.get('damage_from_effects', 0)})")
            print(f"      SOULCREDIT REASONS: {res.get('soulcredit_reasons', [])}")
            narr = res.get('narration', '')
            if narr:
                print(f"      DM NARRATION: {narr[:500]}...")
        print()

    # ---- Detailed: Defensive ----
    print("=" * 100)
    print(f"DEFENSIVE DECLARATIONS: {len(defensive_cases)} found")
    print("=" * 100)
    if not defensive_cases:
        print("  (none found)")
    for i, case in enumerate(defensive_cases, 1):
        res = case.get("resolution", {})
        print(f"\n  [{i}] Run: {case['run']} | Round: {case['round']} | Agent: {case['player_id']} ({case['character_name']})")
        print(f"      INTENT: {case['intent'][:250]}")
        if case['description'] and case['description'] != case['intent']:
            print(f"      DESCRIPTION: {case['description'][:250]}")
        print(f"      CLASSIFICATION: {case['category']}")
        if res:
            print(f"      ROLL: success={res.get('roll_success')}, tier={res.get('roll_tier')}, margin={res.get('roll_margin')}, total={res.get('roll_total')} vs DC {res.get('roll_dc')}")
            print(f"      DAMAGE DEALT: {res.get('damage_dealt', 0)} (from effects: {res.get('damage_from_effects', 0)})")
            narr = res.get('narration', '')
            if narr:
                print(f"      DM NARRATION: {narr[:500]}...")
        print()

    # ---- Detailed: Social ----
    print("=" * 100)
    print(f"SOCIAL DECLARATIONS: {len(social_cases)} found")
    print("=" * 100)
    if not social_cases:
        print("  (none found)")
    for i, case in enumerate(social_cases, 1):
        res = case.get("resolution", {})
        print(f"\n  [{i}] Run: {case['run']} | Round: {case['round']} | Agent: {case['player_id']} ({case['character_name']})")
        print(f"      INTENT: {case['intent'][:250]}")
        if case['description'] and case['description'] != case['intent']:
            print(f"      DESCRIPTION: {case['description'][:250]}")
        print(f"      CLASSIFICATION: {case['category']}")
        if res:
            print(f"      ROLL: success={res.get('roll_success')}, tier={res.get('roll_tier')}, margin={res.get('roll_margin')}, total={res.get('roll_total')} vs DC {res.get('roll_dc')}")
            print(f"      DAMAGE DEALT: {res.get('damage_dealt', 0)} (from effects: {res.get('damage_from_effects', 0)})")
            narr = res.get('narration', '')
            if narr:
                print(f"      DM NARRATION: {narr[:500]}...")
        print()

    # ========================================================================
    # MISMATCH ANALYSIS
    # ========================================================================

    print("=" * 100)
    print("INTENTION-LETHALITY MISMATCH SUMMARY")
    print("=" * 100)

    supp_with_damage = [c for c in suppression_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
    supp_no_damage = [c for c in suppression_cases if c.get("resolution", {}).get("damage_dealt", 0) == 0]

    print(f"\n  SUPPRESSING FIRE declarations: {len(suppression_cases)}")
    print(f"    -> Resulted in damage to enemy:  {len(supp_with_damage)}  ({len(supp_with_damage)/max(1,len(suppression_cases))*100:.0f}%)")
    print(f"    -> No damage dealt:              {len(supp_no_damage)}  ({len(supp_no_damage)/max(1,len(suppression_cases))*100:.0f}%)")
    if supp_with_damage:
        damages = [c["resolution"]["damage_dealt"] for c in supp_with_damage]
        print(f"    -> Damage when dealt: min={min(damages)}, max={max(damages)}, avg={sum(damages)/len(damages):.1f}")

    nl_with_damage = [c for c in nonlethal_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
    nl_no_damage = [c for c in nonlethal_cases if c.get("resolution", {}).get("damage_dealt", 0) == 0]

    print(f"\n  NON-LETHAL declarations: {len(nonlethal_cases)}")
    print(f"    -> Resulted in damage to enemy:  {len(nl_with_damage)}  ({len(nl_with_damage)/max(1,len(nonlethal_cases))*100:.0f}%)")
    print(f"    -> No damage dealt:              {len(nl_no_damage)}  ({len(nl_no_damage)/max(1,len(nonlethal_cases))*100:.0f}%)")
    if nl_with_damage:
        damages = [c["resolution"]["damage_dealt"] for c in nl_with_damage]
        print(f"    -> Damage when dealt: min={min(damages)}, max={max(damages)}, avg={sum(damages)/len(damages):.1f}")

    def_with_damage = [c for c in defensive_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
    def_no_damage = [c for c in defensive_cases if c.get("resolution", {}).get("damage_dealt", 0) == 0]

    print(f"\n  DEFENSIVE declarations: {len(defensive_cases)}")
    print(f"    -> Resulted in damage to enemy:  {len(def_with_damage)}  ({len(def_with_damage)/max(1,len(defensive_cases))*100:.0f}%)")
    print(f"    -> No damage dealt:              {len(def_no_damage)}  ({len(def_no_damage)/max(1,len(defensive_cases))*100:.0f}%)")

    soc_with_damage = [c for c in social_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
    soc_no_damage = [c for c in social_cases if c.get("resolution", {}).get("damage_dealt", 0) == 0]

    print(f"\n  SOCIAL declarations: {len(social_cases)}")
    print(f"    -> Resulted in damage to enemy:  {len(soc_with_damage)}  ({len(soc_with_damage)/max(1,len(social_cases))*100:.0f}%)")
    print(f"    -> No damage dealt:              {len(soc_no_damage)}  ({len(soc_no_damage)/max(1,len(social_cases))*100:.0f}%)")

    lethal_cases = [d for d in all_declarations if d["category"] == "lethal_attack"]
    lethal_with_damage = [c for c in lethal_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
    lethal_no_damage = [c for c in lethal_cases if c.get("resolution", {}).get("damage_dealt", 0) == 0]

    print(f"\n  LETHAL ATTACK declarations: {len(lethal_cases)}")
    print(f"    -> Resulted in damage:           {len(lethal_with_damage)}  ({len(lethal_with_damage)/max(1,len(lethal_cases))*100:.0f}%)")
    print(f"    -> No damage (miss/fail):        {len(lethal_no_damage)}  ({len(lethal_no_damage)/max(1,len(lethal_cases))*100:.0f}%)")
    if lethal_with_damage:
        damages = [c["resolution"]["damage_dealt"] for c in lethal_with_damage]
        print(f"    -> Damage when dealt: min={min(damages)}, max={max(damages)}, avg={sum(damages)/len(damages):.1f}")

    # ========================================================================
    # KEY FINDING: Player lethality choice rates
    # ========================================================================
    print()
    print("=" * 100)
    print("KEY FINDING: PLAYER LETHALITY CHOICE RATES")
    print("=" * 100)

    total_decls = len(all_declarations)
    lethal_count = category_counts.get("lethal_attack", 0)
    nonlethal_total = (category_counts.get("suppressing_fire", 0) +
                       category_counts.get("non_lethal", 0) +
                       category_counts.get("defensive", 0) +
                       category_counts.get("social", 0))
    other_count = category_counts.get("other", 0)

    print(f"\n  Explicitly lethal:      {lethal_count:>4} / {total_decls}  ({lethal_count/max(1,total_decls)*100:.1f}%)")
    print(f"  Non-lethal/restraint:   {nonlethal_total:>4} / {total_decls}  ({nonlethal_total/max(1,total_decls)*100:.1f}%)")
    print(f"    - Suppressing fire:   {category_counts.get('suppressing_fire', 0):>4}")
    print(f"    - Non-lethal:         {category_counts.get('non_lethal', 0):>4}")
    print(f"    - Defensive:          {category_counts.get('defensive', 0):>4}")
    print(f"    - Social:             {category_counts.get('social', 0):>4}")
    print(f"  Other/unclassified:     {other_count:>4} / {total_decls}  ({other_count/max(1,total_decls)*100:.1f}%)")

    for pid in ["player_01", "player_02"]:
        pcats = per_player_category.get(pid, {})
        ptotal = sum(pcats.values())
        p_lethal = pcats.get("lethal_attack", 0)
        p_nonlethal = (pcats.get("suppressing_fire", 0) + pcats.get("non_lethal", 0) +
                       pcats.get("defensive", 0) + pcats.get("social", 0))
        print(f"\n  {PLAYER_NAMES.get(pid, pid)}:")
        print(f"    Lethal:     {p_lethal:>3} / {ptotal}  ({p_lethal/max(1,ptotal)*100:.1f}%)")
        print(f"    Non-lethal: {p_nonlethal:>3} / {ptotal}  ({p_nonlethal/max(1,ptotal)*100:.1f}%)")
        for cat in categories_ordered:
            cnt = pcats.get(cat, 0)
            if cnt > 0:
                print(f"      {cat}: {cnt}")

    # ========================================================================
    # MISMATCH RATE
    # ========================================================================
    print()
    print("=" * 100)
    print("MISMATCH RATE: Non-lethal intent that resolved as lethal damage")
    print("=" * 100)

    mismatch_cases = []
    for case in suppression_cases + nonlethal_cases + defensive_cases + social_cases:
        res = case.get("resolution", {})
        if res.get("damage_dealt", 0) > 0:
            mismatch_cases.append(case)

    total_nonlethal_intent = len(suppression_cases) + len(nonlethal_cases) + len(defensive_cases) + len(social_cases)
    print(f"\n  Total non-lethal-intent declarations: {total_nonlethal_intent}")
    print(f"  Of those, resolved with damage dealt: {len(mismatch_cases)}")
    if total_nonlethal_intent > 0:
        print(f"  MISMATCH RATE: {len(mismatch_cases)/total_nonlethal_intent*100:.1f}%")

    if mismatch_cases:
        print(f"\n  --- Mismatch Details ---")
        for i, case in enumerate(mismatch_cases, 1):
            res = case.get("resolution", {})
            print(f"\n  MISMATCH [{i}]:")
            print(f"    Run: {case['run']} | Round: {case['round']} | {case['player_id']} ({case['character_name']})")
            print(f"    INTENT: {case['intent'][:300]}")
            print(f"    CATEGORY: {case['category']}")
            print(f"    DAMAGE DEALT: {res.get('damage_dealt', 0)}")
            print(f"    ROLL: tier={res.get('roll_tier')}, margin={res.get('roll_margin')}")
            narr = res.get('narration', '')
            if narr:
                print(f"    DM NARRATION: {narr[:500]}")

    # ========================================================================
    # Unresolved declarations
    # ========================================================================
    unresolved = [d for d in all_declarations if not d.get("resolution")]
    if unresolved:
        print(f"\n\n  NOTE: {len(unresolved)} declarations had no matching resolution event")
        for u in unresolved[:10]:
            print(f"    - {u['run']} R{u['round']} {u['player_id']} ({u['character_name']}): {u['intent'][:120]}")

    # ========================================================================
    # "Other" category details
    # ========================================================================
    other_cases = [d for d in all_declarations if d["category"] == "other"]
    if other_cases:
        print()
        print("=" * 100)
        print(f"'OTHER' CATEGORY DECLARATIONS ({len(other_cases)} total) - review for misclassification")
        print("=" * 100)
        for i, case in enumerate(other_cases, 1):
            res = case.get("resolution", {})
            dmg = res.get("damage_dealt", 0) if res else 0
            print(f"  [{i}] {case['run']} R{case['round']} {case['player_id']}: {case['intent'][:200]} [dmg={dmg}]")

    # ========================================================================
    # Comparison: avg damage for lethal vs suppression vs non-lethal
    # ========================================================================
    print()
    print("=" * 100)
    print("DAMAGE COMPARISON BY CATEGORY (successful hits only)")
    print("=" * 100)
    for cat_name, cat_cases in [("lethal_attack", lethal_cases), ("suppressing_fire", suppression_cases),
                                 ("non_lethal", nonlethal_cases), ("defensive", defensive_cases),
                                 ("social", social_cases)]:
        with_dmg = [c for c in cat_cases if c.get("resolution", {}).get("damage_dealt", 0) > 0]
        all_dmg = [c["resolution"]["damage_dealt"] for c in with_dmg]
        if all_dmg:
            print(f"  {cat_name:<22}: n={len(all_dmg):>3}, min={min(all_dmg):>3}, max={max(all_dmg):>3}, avg={sum(all_dmg)/len(all_dmg):>6.1f}, median={sorted(all_dmg)[len(all_dmg)//2]:>3}")
        else:
            print(f"  {cat_name:<22}: n=  0 (no damage dealt)")

    # ========================================================================
    # Per-session summary
    # ========================================================================
    print()
    print("=" * 100)
    print("PER-SESSION BREAKDOWN")
    print("=" * 100)
    per_session = defaultdict(lambda: {"total": 0, "lethal": 0, "suppressing": 0, "nonlethal": 0, "defensive": 0, "social": 0, "other": 0})
    for d in all_declarations:
        run = d["run"]
        per_session[run]["total"] += 1
        if d["category"] == "lethal_attack":
            per_session[run]["lethal"] += 1
        elif d["category"] == "suppressing_fire":
            per_session[run]["suppressing"] += 1
        elif d["category"] == "non_lethal":
            per_session[run]["nonlethal"] += 1
        elif d["category"] == "defensive":
            per_session[run]["defensive"] += 1
        elif d["category"] == "social":
            per_session[run]["social"] += 1
        else:
            per_session[run]["other"] += 1

    print(f"  {'Run':<12} {'Total':>6} {'Lethal':>8} {'Suppr':>7} {'NonLeth':>9} {'Defens':>8} {'Social':>8} {'Other':>7}")
    print("  " + "-" * 70)
    for run in sorted(per_session.keys()):
        s = per_session[run]
        print(f"  {run:<12} {s['total']:>6} {s['lethal']:>8} {s['suppressing']:>7} {s['nonlethal']:>9} {s['defensive']:>8} {s['social']:>8} {s['other']:>7}")

    print()
    print("=" * 100)
    print("ANALYSIS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
