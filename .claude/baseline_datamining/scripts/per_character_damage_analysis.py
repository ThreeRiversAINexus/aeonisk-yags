#!/usr/bin/env python3
"""
Per-Character Damage Analysis: Controls for weapon type and character stats.

Key question: When the SAME character uses the SAME weapon for lethal vs
suppressive fire, does the DM assign different base_damage?

Also: Soulcredit distribution by keyword-classified intent.
"""

import json
import glob
import re
import os
from collections import defaultdict, Counter

# ── Configuration ────────────────────────────────────────────────────────────

RUNS = {
    "original": {
        "base": os.path.expanduser(
            "~/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/"
            "control/models/run_2026-02-14_113048_5276cf26"
        ),
        "runs": [
            "run_0001", "run_0002", "run_0003", "run_0005", "run_0006",
            "run_0007", "run_0008", "run_0010", "run_0011", "run_0012",
            "run_0013", "run_0015", "run_0016", "run_0017", "run_0018",
            "run_0020", "run_0021", "run_0022", "run_0023", "run_0025",
        ],
        "model_map": {
            "run_0001": "GPT-5.2", "run_0006": "GPT-5.2", "run_0011": "GPT-5.2",
            "run_0016": "GPT-5.2", "run_0021": "GPT-5.2",
            "run_0002": "Grok 4", "run_0007": "Grok 4", "run_0012": "Grok 4",
            "run_0017": "Grok 4", "run_0022": "Grok 4",
            "run_0003": "Gemini 2.5 Pro", "run_0008": "Gemini 2.5 Pro",
            "run_0013": "Gemini 2.5 Pro", "run_0018": "Gemini 2.5 Pro",
            "run_0023": "Gemini 2.5 Pro",
            "run_0005": "DeepSeek V3.2", "run_0010": "DeepSeek V3.2",
            "run_0015": "DeepSeek V3.2", "run_0020": "DeepSeek V3.2",
            "run_0025": "DeepSeek V3.2",
        },
    },
    "claude": {
        "base": os.path.expanduser(
            "~/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/"
            "control/models/run_2026-02-14_171956_2540eedd"
        ),
        "runs": [
            "run_0001", "run_0002", "run_0003", "run_0004", "run_0005",
        ],
        "model_map": {
            "run_0001": "Claude Opus 4.6", "run_0002": "Claude Opus 4.6",
            "run_0003": "Claude Opus 4.6", "run_0004": "Claude Opus 4.6",
            "run_0005": "Claude Opus 4.6",
        },
    },
}

PC_NAMES = {"Enforcer Kael Dren", "Drifter Sable"}

# Character weapons from session config
CHAR_WEAPONS = {
    "Kael": {"primary": "shotgun", "sidearm": "shock_baton"},
    "Sable": {"primary": "rifle", "sidearm": "combat_knife"},
}


# ── Intent Classification (same as deep_action_analysis.py) ──────────────────

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
    combined = f"{intent_text or ''} {description_text or ''}".lower()
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


def short_char(name):
    if "Kael" in name:
        return "Kael"
    if "Sable" in name:
        return "Sable"
    return name


# ── Data Loading ─────────────────────────────────────────────────────────────

def load_all_records():
    """Load all player declarations with matched resolutions from all runs."""
    all_records = []

    for batch_name, batch in RUNS.items():
        base_dir = batch["base"]
        for run_id in batch["runs"]:
            run_dir = os.path.join(base_dir, run_id)
            files = glob.glob(os.path.join(run_dir, "session_*.jsonl"))
            if not files:
                continue

            events = []
            with open(files[0]) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            model = batch["model_map"].get(run_id, "unknown")

            # Gather declarations
            declarations = []
            for e in events:
                if (e.get("event_type") == "action_declaration"
                        and e.get("player_id", "").startswith("player_")):
                    declarations.append(e)

            # Gather resolutions
            resolutions_by_key = defaultdict(list)
            for e in events:
                if e.get("event_type") == "action_resolution":
                    phase = e.get("phase", "")
                    if "enemy" in phase or "npc" in phase:
                        continue
                    agent = e.get("agent", "")
                    rnd = e.get("round")
                    if agent in PC_NAMES and rnd is not None:
                        resolutions_by_key[(rnd, agent)].append(e)

            # Match
            for decl in declarations:
                action = decl.get("action", {})
                char_name = decl.get("character_name", "")
                rnd = decl.get("round")
                if char_name not in PC_NAMES:
                    continue

                key = (rnd, char_name)
                candidates = resolutions_by_key.get(key, [])
                res = candidates[0] if len(candidates) >= 1 else None

                intent_text = action.get("intent", "")
                desc_text = action.get("description", "")
                intent_cat = classify_intent(intent_text, desc_text)
                char = short_char(char_name)

                record = {
                    "batch": batch_name,
                    "run_id": run_id,
                    "model": model,
                    "round": rnd,
                    "character": char,
                    "intent_category": intent_cat,
                    "intent_text": intent_text,
                    "desc_text": desc_text,
                    "skill": action.get("skill"),
                    "has_resolution": res is not None,
                }

                if res:
                    roll = res.get("roll", {})
                    effects = res.get("effects", {})
                    ctx = res.get("context", {})
                    econ = res.get("economy", {}) or {}

                    record["roll_success"] = roll.get("success")
                    record["roll_margin"] = roll.get("margin")
                    record["roll_d20"] = roll.get("d20")
                    record["roll_skill"] = roll.get("skill")

                    # Damage from context.damage_effects
                    damage_effects = ctx.get("damage_effects", []) or []
                    record["damage_effects"] = damage_effects
                    record["total_base_damage"] = sum(
                        (de.get("base_damage") or 0) for de in damage_effects
                    )
                    record["total_dealt"] = sum(
                        (de.get("dealt") or 0) for de in damage_effects
                    )
                    record["damage_types"] = [
                        de.get("damage_type", "unknown") for de in damage_effects
                    ]

                    # Damage from effects.damage (top-level)
                    eff_damage = effects.get("damage") or {}
                    record["effects_dealt"] = eff_damage.get("dealt", 0) or 0

                    # Soulcredit
                    record["sc_delta"] = econ.get("soulcredit_delta", 0) or 0
                    record["sc_reasons"] = econ.get("soulcredit_reasons", []) or []

                    # Also check effects.soulcredit_changes
                    sc_changes = effects.get("soulcredit_changes", []) or []
                    if sc_changes and not record["sc_reasons"]:
                        for sc in sc_changes:
                            if isinstance(sc, dict):
                                record["sc_delta"] = sc.get("amount", 0) or 0
                                reason = sc.get("reason", "")
                                if reason:
                                    record["sc_reasons"] = [reason]
                else:
                    record["roll_success"] = None
                    record["roll_margin"] = None
                    record["roll_d20"] = None
                    record["roll_skill"] = None
                    record["damage_effects"] = []
                    record["total_base_damage"] = 0
                    record["total_dealt"] = 0
                    record["damage_types"] = []
                    record["effects_dealt"] = 0
                    record["sc_delta"] = 0
                    record["sc_reasons"] = []

                all_records.append(record)

    return all_records


# ── Analysis Functions ───────────────────────────────────────────────────────

def damage_stats(records):
    """Compute damage statistics for a list of records (successful hits only)."""
    hits = [r for r in records if r["roll_success"] and r["total_base_damage"] > 0]
    if not hits:
        return None
    n = len(hits)
    margins = [r["roll_margin"] or 0 for r in hits]
    bases = [r["total_base_damage"] for r in hits]
    dealts = [r["total_dealt"] for r in hits]
    d20s = [r["roll_d20"] or 0 for r in hits]

    wound_count = sum(
        1 for r in hits
        for dt in r["damage_types"]
        if dt == "wound"
    )
    stun_count = sum(
        1 for r in hits
        for dt in r["damage_types"]
        if dt == "stun"
    )
    total_dtype = wound_count + stun_count

    return {
        "n": n,
        "avg_margin": sum(margins) / n,
        "avg_d20": sum(d20s) / n,
        "avg_base": sum(bases) / n,
        "avg_dealt": sum(dealts) / n,
        "min_base": min(bases),
        "max_base": max(bases),
        "pct_wound": (wound_count / total_dtype * 100) if total_dtype > 0 else 0,
    }


def print_damage_table(title, groups, group_labels):
    """Print a formatted damage comparison table."""
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(f"  {'Group':<30} {'N':>4} {'Avg Margin':>11} {'Avg d20':>8} {'Avg Base':>9} {'Avg Dealt':>10} {'%Wound':>7}")
    print(f"  {'-'*30} {'-'*4} {'-'*11} {'-'*8} {'-'*9} {'-'*10} {'-'*7}")
    for label in group_labels:
        stats = groups.get(label)
        if stats is None:
            print(f"  {label:<30} {'—':>4}")
            continue
        print(f"  {label:<30} {stats['n']:>4} {stats['avg_margin']:>11.1f} {stats['avg_d20']:>8.1f} "
              f"{stats['avg_base']:>9.1f} {stats['avg_dealt']:>10.1f} {stats['pct_wound']:>6.0f}%")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading all session data...")
    records = load_all_records()
    print(f"Total records: {len(records)}")
    print(f"  With resolution: {sum(1 for r in records if r['has_resolution'])}")
    print(f"  Kael: {sum(1 for r in records if r['character'] == 'Kael')}")
    print(f"  Sable: {sum(1 for r in records if r['character'] == 'Sable')}")
    print()

    # ── TABLE 1: Aggregate (all characters, all models) ──────────────────────

    by_intent = defaultdict(list)
    for r in records:
        by_intent[r["intent_category"]].append(r)

    intent_order = ["lethal_attack", "suppressing_fire", "non_lethal"]
    groups = {cat: damage_stats(by_intent[cat]) for cat in intent_order}
    print_damage_table("TABLE 1: Aggregate Damage by Intent (all characters)", groups, intent_order)

    # ── TABLE 2: Per-Character Damage (THE KEY TABLE) ────────────────────────

    print(f"\n{'='*90}")
    print(f"  TABLE 2: Per-Character Damage by Intent (controls for weapon type)")
    print(f"{'='*90}")
    print()
    print("  Kael: primary=shotgun, sidearm=shock_baton, Guns 5, Melee 4")
    print("  Sable: primary=rifle, sidearm=combat_knife, Guns 5, no non-lethal")
    print()

    for char in ["Sable", "Kael"]:
        char_records = [r for r in records if r["character"] == char]
        char_by_intent = defaultdict(list)
        for r in char_records:
            char_by_intent[r["intent_category"]].append(r)

        # Count declarations per intent
        print(f"  {char} declarations: ", end="")
        parts = []
        for cat in intent_order + ["defensive", "social", "other"]:
            n = len(char_by_intent.get(cat, []))
            if n > 0:
                parts.append(f"{cat}={n}")
        print(", ".join(parts))

        groups = {}
        labels = []
        for cat in intent_order:
            label = f"{char} {cat}"
            labels.append(label)
            groups[label] = damage_stats(char_by_intent.get(cat, []))

        print_damage_table(f"{char} — Same Character, Same Primary Weapon", groups, labels)

    # ── TABLE 3: Margin-Binned Comparison (tight control) ────────────────────

    print(f"\n{'='*90}")
    print(f"  TABLE 3: Margin-Binned Comparison (margin 6-14 only)")
    print(f"{'='*90}")
    print("  Filtering to margin 6-14 controls tightly for roll quality.")
    print()

    margin_filtered = [r for r in records if r["roll_margin"] is not None and 6 <= r["roll_margin"] <= 14]

    by_intent_mf = defaultdict(list)
    for r in margin_filtered:
        by_intent_mf[r["intent_category"]].append(r)

    groups = {cat: damage_stats(by_intent_mf[cat]) for cat in intent_order}
    print_damage_table("Margin 6-14 Only (all characters)", groups, intent_order)

    # Per-character margin-binned
    for char in ["Sable", "Kael"]:
        char_mf = [r for r in margin_filtered if r["character"] == char]
        char_by_intent = defaultdict(list)
        for r in char_mf:
            char_by_intent[r["intent_category"]].append(r)

        groups = {}
        labels = []
        for cat in ["lethal_attack", "suppressing_fire"]:
            label = f"{char} {cat}"
            labels.append(label)
            groups[label] = damage_stats(char_by_intent.get(cat, []))

        if any(groups[l] is not None for l in labels):
            print_damage_table(f"{char} — Margin 6-14 Only", groups, labels)

    # ── TABLE 4: Soulcredit by Keyword-Classified Intent ─────────────────────

    print(f"\n{'='*90}")
    print(f"  TABLE 4: Soulcredit Distribution by Intent (keyword-classified)")
    print(f"{'='*90}")
    print()

    sc_cats = ["lethal_attack", "suppressing_fire", "non_lethal", "defensive", "social", "other"]
    print(f"  {'Intent':<20} {'N':>5} {'SC=0':>6} {'SC>0':>6} {'SC<0':>6} {'Net SC':>7} {'Avg SC':>8}")
    print(f"  {'-'*20} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*8}")

    for cat in sc_cats:
        cat_records = [r for r in records if r["intent_category"] == cat and r["has_resolution"]]
        if not cat_records:
            continue
        n = len(cat_records)
        sc_zero = sum(1 for r in cat_records if r["sc_delta"] == 0)
        sc_pos = sum(1 for r in cat_records if r["sc_delta"] > 0)
        sc_neg = sum(1 for r in cat_records if r["sc_delta"] < 0)
        net_sc = sum(r["sc_delta"] for r in cat_records)
        avg_sc = net_sc / n if n > 0 else 0
        print(f"  {cat:<20} {n:>5} {sc_zero:>6} {sc_pos:>6} {sc_neg:>6} {net_sc:>+7} {avg_sc:>+8.3f}")

    print()

    # Detail: all non-zero SC events for suppressive fire
    print("  Non-zero SC events for suppressing_fire:")
    supp_nonzero = [r for r in records if r["intent_category"] == "suppressing_fire"
                    and r["has_resolution"] and r["sc_delta"] != 0]
    if not supp_nonzero:
        print("    (none — all suppressive fire actions scored SC=0)")
    else:
        for r in supp_nonzero:
            print(f"    {r['run_id']} R{r['round']} | {r['model']} | {r['character']} | "
                  f"SC={r['sc_delta']:+d} | {'; '.join(r['sc_reasons'])}")
    print()

    # Detail: all non-zero SC events for lethal_attack
    print("  Non-zero SC events for lethal_attack:")
    lethal_nonzero = [r for r in records if r["intent_category"] == "lethal_attack"
                      and r["has_resolution"] and r["sc_delta"] != 0]
    if not lethal_nonzero:
        print("    (none)")
    else:
        for r in lethal_nonzero:
            print(f"    {r['run_id']} R{r['round']} | {r['model']} | {r['character']} | "
                  f"SC={r['sc_delta']:+d} | {'; '.join(r['sc_reasons'])}")
    print()

    # ── TABLE 5: SC reason strings for suppressive fire ──────────────────────

    print(f"\n{'='*90}")
    print(f"  TABLE 5: SC Reason Strings for Suppressive Fire (all events)")
    print(f"{'='*90}")
    print()

    supp_with_res = [r for r in records if r["intent_category"] == "suppressing_fire"
                     and r["has_resolution"]]
    reason_counter = Counter()
    for r in supp_with_res:
        for reason in r["sc_reasons"]:
            reason_counter[reason] += 1

    if reason_counter:
        print(f"  {'Count':>5}  Reason")
        print(f"  {'-'*5}  {'-'*70}")
        for reason, count in reason_counter.most_common(20):
            print(f"  {count:>5}  {reason[:80]}")
    else:
        print("  No SC reasons found for suppressive fire.")
    print()

    # ── TABLE 6: Per-model per-intent (for cross-model consistency) ──────────

    print(f"\n{'='*90}")
    print(f"  TABLE 6: Per-Model Damage for Lethal vs Suppressive (successful hits)")
    print(f"{'='*90}")
    print()

    models = ["GPT-5.2", "Grok 4", "DeepSeek V3.2", "Claude Opus 4.6", "Gemini 2.5 Pro"]
    print(f"  {'Model':<18} {'Intent':<20} {'N':>4} {'Avg Margin':>11} {'Avg Base':>9} {'Avg Dealt':>10} {'%Wound':>7}")
    print(f"  {'-'*18} {'-'*20} {'-'*4} {'-'*11} {'-'*9} {'-'*10} {'-'*7}")

    for model in models:
        model_records = [r for r in records if r["model"] == model]
        for cat in ["lethal_attack", "suppressing_fire"]:
            cat_records = [r for r in model_records if r["intent_category"] == cat]
            stats = damage_stats(cat_records)
            if stats is None:
                print(f"  {model:<18} {cat:<20} {'—':>4}")
            else:
                print(f"  {model:<18} {cat:<20} {stats['n']:>4} {stats['avg_margin']:>11.1f} "
                      f"{stats['avg_base']:>9.1f} {stats['avg_dealt']:>10.1f} {stats['pct_wound']:>6.0f}%")
        print()

    # ── TABLE 7: Individual damage_effects for suppressive fire ──────────────

    print(f"\n{'='*90}")
    print(f"  TABLE 7: Individual damage_effects for Suppressive Fire (first 15)")
    print(f"{'='*90}")
    print("  Shows per-damage-effect entries (not aggregated per action)")
    print()

    supp_hits = [r for r in records if r["intent_category"] == "suppressing_fire"
                 and r["roll_success"] and r["damage_effects"]]

    print(f"  {'Run':<12} {'R':>2} {'Char':<7} {'Model':<16} {'Margin':>6} {'base_dmg':>8} {'dealt':>6} {'type':<6}")
    print(f"  {'-'*12} {'-'*2} {'-'*7} {'-'*16} {'-'*6} {'-'*8} {'-'*6} {'-'*6}")

    count = 0
    for r in supp_hits:
        for de in r["damage_effects"]:
            count += 1
            if count > 15:
                break
            bd = de.get("base_damage", 0) or 0
            dealt = de.get("dealt", 0) or 0
            dtype = de.get("damage_type", "?")
            print(f"  {r['run_id']:<12} {r['round']:>2} {r['character']:<7} {r['model']:<16} "
                  f"{r['roll_margin'] or 0:>6} {bd:>8} {dealt:>6} {dtype:<6}")
        if count > 15:
            break

    remaining = sum(len(r["damage_effects"]) for r in supp_hits) - min(count, 15)
    if remaining > 0:
        print(f"  ... and {remaining} more damage_effect entries")
    print()

    print("=" * 90)
    print("  ANALYSIS COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
