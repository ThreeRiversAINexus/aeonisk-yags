#!/usr/bin/env python3
"""
Deep Action Analysis: Player declarations vs resolutions across 20 YAGS sessions.
Extracts all player action_declaration + matching action_resolution events.
Classifies intent, computes damage-per-margin, status effects, and more.
"""

import json
import glob
import re
import os
from collections import defaultdict, Counter

# ── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = os.path.expanduser(
    "~/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/"
    "control/models/run_2026-02-14_113048_5276cf26"
)

SUCCESSFUL_RUNS = [
    "run_0001", "run_0002", "run_0003", "run_0005", "run_0006",
    "run_0007", "run_0008", "run_0010", "run_0011", "run_0012",
    "run_0013", "run_0015", "run_0016", "run_0017", "run_0018",
    "run_0020", "run_0021", "run_0022", "run_0023", "run_0025",
]

MODEL_MAP = {
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
}

PC_NAMES = {"Enforcer Kael Dren", "Drifter Sable"}

# ── Intent Classification ────────────────────────────────────────────────────

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

    # Check in priority order
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


# ── Data Loading ─────────────────────────────────────────────────────────────

def load_session_events(run_id):
    """Load all events from a session JSONL file."""
    run_dir = os.path.join(BASE_DIR, run_id)
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


def extract_player_actions(events, run_id):
    """Extract player declarations and match them with resolutions."""
    model = MODEL_MAP[run_id]

    # Gather all player action declarations
    declarations = []
    for e in events:
        if (e.get("event_type") == "action_declaration"
                and e.get("player_id", "").startswith("player_")):
            declarations.append(e)

    # Gather all action resolutions indexed by (round, agent_name)
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

    # Match declarations to resolutions
    matched = []
    for decl in declarations:
        action = decl.get("action", {})
        char_name = decl.get("character_name", "")
        rnd = decl.get("round")

        if char_name not in PC_NAMES:
            continue

        # Find matching resolution
        key = (rnd, char_name)
        res = None
        candidates = resolutions_by_key.get(key, [])
        if len(candidates) == 1:
            res = candidates[0]
        elif len(candidates) > 1:
            # Try to match on action text or target
            decl_intent = action.get("intent", "")
            for c in candidates:
                if c.get("goal", "") == decl_intent or c.get("action", "") == decl_intent:
                    res = c
                    break
            if res is None:
                res = candidates[0]  # fallback to first

        intent_text = action.get("intent", "")
        desc_text = action.get("description", "")
        intent_cat = classify_intent(intent_text, desc_text)

        # Short character label
        if "Kael" in char_name:
            char_short = "Kael"
        elif "Sable" in char_name:
            char_short = "Sable"
        else:
            char_short = char_name

        record = {
            "run_id": run_id,
            "model": model,
            "round": rnd,
            "character": char_short,
            "player_id": decl.get("player_id"),
            "intent": intent_text,
            "description": desc_text,
            "skill": action.get("skill"),
            "attribute": action.get("attribute"),
            "action_type": action.get("action_type"),
            "target": action.get("target"),
            "target_position": action.get("target_position"),
            "difficulty_estimate": action.get("difficulty_estimate"),
            "intent_category": intent_cat,
            # Resolution fields
            "has_resolution": res is not None,
        }

        if res:
            roll = res.get("roll", {})
            record["roll_d20"] = roll.get("d20")
            record["roll_total"] = roll.get("total")
            record["roll_dc"] = roll.get("dc")
            record["roll_margin"] = roll.get("margin")
            record["roll_tier"] = roll.get("tier")
            record["roll_success"] = roll.get("success")
            record["roll_skill"] = roll.get("skill")
            record["roll_skill_val"] = roll.get("skill_val")
            record["roll_attr"] = roll.get("attr")
            record["roll_attr_val"] = roll.get("attr_val")

            effects = res.get("effects", {})
            damage = effects.get("damage") or {}
            record["damage_dealt"] = damage.get("dealt", 0) if damage else 0
            record["status_effects"] = effects.get("status_effects", [])

            ctx = res.get("context", {})
            damage_effects = ctx.get("damage_effects", [])
            record["damage_effects"] = damage_effects

            narration = ctx.get("narration", "")
            record["narration_preview"] = (narration[:200] + "...") if len(narration) > 200 else narration
        else:
            record["roll_d20"] = None
            record["roll_total"] = None
            record["roll_dc"] = None
            record["roll_margin"] = None
            record["roll_tier"] = None
            record["roll_success"] = None
            record["roll_skill"] = None
            record["roll_skill_val"] = None
            record["roll_attr"] = None
            record["roll_attr_val"] = None
            record["damage_dealt"] = 0
            record["status_effects"] = []
            record["damage_effects"] = []
            record["narration_preview"] = ""

        matched.append(record)

    return matched


# ── Table Rendering ──────────────────────────────────────────────────────────

MODELS_ORDER = ["GPT-5.2", "Grok 4", "Gemini 2.5 Pro", "DeepSeek V3.2"]


def print_table(headers, rows, title=""):
    """Print a formatted ASCII table."""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Header
    header_line = " | ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    print(f"\n{header_line}")
    print(sep_line)

    # Rows
    for row in rows:
        line = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        print(line)
    print()


# ── Main Analysis ────────────────────────────────────────────────────────────

def main():
    print("Loading session data from 20 runs...")
    all_records = []
    for run_id in SUCCESSFUL_RUNS:
        events = load_session_events(run_id)
        records = extract_player_actions(events, run_id)
        all_records.extend(records)
        print(f"  {run_id} ({MODEL_MAP[run_id]}): {len(records)} player actions, {len(events)} total events")

    print(f"\nTotal player action records: {len(all_records)}")
    print(f"  With resolution: {sum(1 for r in all_records if r['has_resolution'])}")
    print(f"  Without resolution: {sum(1 for r in all_records if not r['has_resolution'])}")

    # ── TABLE 1: action_type distribution by model ──────────────────────────

    action_type_counts = defaultdict(lambda: defaultdict(int))
    action_type_totals = defaultdict(int)
    for r in all_records:
        at = r["action_type"] or "unknown"
        model = r["model"]
        action_type_counts[at][model] += 1
        action_type_totals[at] += 1

    rows = []
    for at in sorted(action_type_totals.keys(), key=lambda x: -action_type_totals[x]):
        row = [at]
        for m in MODELS_ORDER:
            row.append(action_type_counts[at].get(m, 0))
        row.append(action_type_totals[at])
        rows.append(row)

    # Totals row
    total_row = ["TOTAL"]
    for m in MODELS_ORDER:
        total_row.append(sum(action_type_counts[at].get(m, 0) for at in action_type_totals))
    total_row.append(sum(action_type_totals.values()))
    rows.append(total_row)

    print_table(
        ["action_type"] + MODELS_ORDER + ["Total"],
        rows,
        "TABLE 1: action_type Distribution (from schema field) by Model"
    )

    # ── TABLE 2: Skill distribution by model ────────────────────────────────

    skill_counts = defaultdict(lambda: defaultdict(int))
    skill_totals = defaultdict(int)
    for r in all_records:
        sk = r["skill"] or "unknown"
        model = r["model"]
        skill_counts[sk][model] += 1
        skill_totals[sk] += 1

    rows = []
    for sk in sorted(skill_totals.keys(), key=lambda x: -skill_totals[x]):
        row = [sk]
        for m in MODELS_ORDER:
            row.append(skill_counts[sk].get(m, 0))
        row.append(skill_totals[sk])
        rows.append(row)

    total_row = ["TOTAL"]
    for m in MODELS_ORDER:
        total_row.append(sum(skill_counts[sk].get(m, 0) for sk in skill_totals))
    total_row.append(sum(skill_totals.values()))
    rows.append(total_row)

    print_table(
        ["Skill"] + MODELS_ORDER + ["Total"],
        rows,
        "TABLE 2: Skill Distribution by Model"
    )

    # ── TABLE 3: Intent classification by model AND character ───────────────

    intent_model_char = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    intent_totals = defaultdict(int)
    for r in all_records:
        cat = r["intent_category"]
        model = r["model"]
        char = r["character"]
        intent_model_char[cat][model][char] += 1
        intent_totals[cat] += 1

    cat_order = ["lethal_attack", "suppressing_fire", "non_lethal", "defensive", "social", "other"]
    # Add any categories not in our predefined list
    for cat in sorted(intent_totals.keys()):
        if cat not in cat_order:
            cat_order.append(cat)

    rows = []
    for cat in cat_order:
        if cat not in intent_totals:
            continue
        for m in MODELS_ORDER:
            kael_ct = intent_model_char[cat][m].get("Kael", 0)
            sable_ct = intent_model_char[cat][m].get("Sable", 0)
            total_m = kael_ct + sable_ct
            if total_m > 0:
                rows.append([cat, m, kael_ct, sable_ct, total_m])

        # Category subtotal
        kael_total = sum(intent_model_char[cat][m].get("Kael", 0) for m in MODELS_ORDER)
        sable_total = sum(intent_model_char[cat][m].get("Sable", 0) for m in MODELS_ORDER)
        rows.append([f"  [{cat} TOTAL]", "", kael_total, sable_total, intent_totals[cat]])
        rows.append(["", "", "", "", ""])

    print_table(
        ["Intent Category", "Model", "Kael", "Sable", "Total"],
        rows,
        "TABLE 3: Intent Classification by Model and Character"
    )

    # ── TABLE 4: Damage per margin analysis (THE KEY TABLE) ─────────────────

    # For SUCCESSFUL hits only where damage > 0
    print(f"\n{'='*80}")
    print(f"  TABLE 4: Damage Per Margin Analysis (successful hits with damage > 0)")
    print(f"{'='*80}")

    # 4a: By intent category (all models)
    damage_by_cat = defaultdict(list)  # cat -> list of (margin, base_damage, damage_dealt)
    for r in all_records:
        if r["roll_success"] and r["damage_dealt"] and r["damage_dealt"] > 0:
            margin = r["roll_margin"] or 0
            dd = r["damage_dealt"]

            # Get base_damage from damage_effects
            base_dmg = 0
            for de in r.get("damage_effects", []):
                base_dmg += de.get("base_damage", 0) or 0

            damage_by_cat[r["intent_category"]].append({
                "margin": margin,
                "base_damage": base_dmg,
                "damage_dealt": dd,
                "model": r["model"],
            })

    rows = []
    for cat in cat_order:
        entries = damage_by_cat.get(cat, [])
        if not entries:
            continue
        n = len(entries)
        avg_margin = sum(e["margin"] for e in entries) / n
        avg_base = sum(e["base_damage"] for e in entries) / n
        avg_dealt = sum(e["damage_dealt"] for e in entries) / n
        # damage per margin point (avoid div by 0)
        dpm_vals = [e["damage_dealt"] / e["margin"] for e in entries if e["margin"] > 0]
        avg_dpm = sum(dpm_vals) / len(dpm_vals) if dpm_vals else 0

        rows.append([cat, n, f"{avg_margin:.1f}", f"{avg_base:.1f}",
                      f"{avg_dealt:.1f}", f"{avg_dpm:.2f}"])

    print("\n4a. Aggregate (all models combined):")
    print_table(
        ["Intent Category", "N (hits)", "Avg Margin", "Avg Base Dmg", "Avg Dmg Dealt", "Dmg/Margin"],
        rows,
    )

    # 4b: By intent category AND model
    damage_by_cat_model = defaultdict(lambda: defaultdict(list))
    for r in all_records:
        if r["roll_success"] and r["damage_dealt"] and r["damage_dealt"] > 0:
            margin = r["roll_margin"] or 0
            dd = r["damage_dealt"]
            base_dmg = 0
            for de in r.get("damage_effects", []):
                base_dmg += de.get("base_damage", 0) or 0
            damage_by_cat_model[r["intent_category"]][r["model"]].append({
                "margin": margin,
                "base_damage": base_dmg,
                "damage_dealt": dd,
            })

    rows = []
    for cat in cat_order:
        if cat not in damage_by_cat_model:
            continue
        for m in MODELS_ORDER:
            entries = damage_by_cat_model[cat].get(m, [])
            if not entries:
                continue
            n = len(entries)
            avg_margin = sum(e["margin"] for e in entries) / n
            avg_base = sum(e["base_damage"] for e in entries) / n
            avg_dealt = sum(e["damage_dealt"] for e in entries) / n
            dpm_vals = [e["damage_dealt"] / e["margin"] for e in entries if e["margin"] > 0]
            avg_dpm = sum(dpm_vals) / len(dpm_vals) if dpm_vals else 0
            rows.append([cat, m, n, f"{avg_margin:.1f}", f"{avg_base:.1f}",
                          f"{avg_dealt:.1f}", f"{avg_dpm:.2f}"])
        rows.append(["", "", "", "", "", "", ""])

    print("4b. Broken down by model:")
    print_table(
        ["Intent", "Model", "N", "Avg Margin", "Avg Base Dmg", "Avg Dealt", "Dmg/Margin"],
        rows,
    )

    # ── TABLE 5: Success/failure rate by intent category ────────────────────

    print(f"\n{'='*80}")
    print(f"  TABLE 5: Success/Failure Rate by Intent Category")
    print(f"{'='*80}")

    # 5a: Aggregate
    success_by_cat = defaultdict(lambda: {"total": 0, "success": 0, "fail": 0, "null": 0})
    for r in all_records:
        cat = r["intent_category"]
        success_by_cat[cat]["total"] += 1
        if r["roll_success"] is True:
            success_by_cat[cat]["success"] += 1
        elif r["roll_success"] is False:
            success_by_cat[cat]["fail"] += 1
        else:
            success_by_cat[cat]["null"] += 1

    rows = []
    for cat in cat_order:
        if cat not in success_by_cat:
            continue
        d = success_by_cat[cat]
        denominator = d["success"] + d["fail"]
        rate = f"{100*d['success']/denominator:.1f}%" if denominator > 0 else "N/A"
        rows.append([cat, d["total"], d["success"], d["fail"], d["null"], rate])

    print("\n5a. Aggregate:")
    print_table(
        ["Intent Category", "Total", "Success", "Fail", "No Roll", "Success Rate"],
        rows,
    )

    # 5b: By model
    success_by_cat_model = defaultdict(lambda: defaultdict(lambda: {"total": 0, "success": 0, "fail": 0, "null": 0}))
    for r in all_records:
        cat = r["intent_category"]
        m = r["model"]
        success_by_cat_model[cat][m]["total"] += 1
        if r["roll_success"] is True:
            success_by_cat_model[cat][m]["success"] += 1
        elif r["roll_success"] is False:
            success_by_cat_model[cat][m]["fail"] += 1
        else:
            success_by_cat_model[cat][m]["null"] += 1

    rows = []
    for cat in cat_order:
        if cat not in success_by_cat_model:
            continue
        for m in MODELS_ORDER:
            d = success_by_cat_model[cat][m]
            if d["total"] == 0:
                continue
            denominator = d["success"] + d["fail"]
            rate = f"{100*d['success']/denominator:.1f}%" if denominator > 0 else "N/A"
            rows.append([cat, m, d["total"], d["success"], d["fail"], d["null"], rate])
        rows.append(["", "", "", "", "", "", ""])

    print("5b. By model:")
    print_table(
        ["Intent", "Model", "Total", "Success", "Fail", "No Roll", "Success Rate"],
        rows,
    )

    # ── TABLE 6: Status effects by intent category ──────────────────────────

    status_by_cat = defaultdict(Counter)
    status_total_by_cat = defaultdict(int)
    for r in all_records:
        cat = r["intent_category"]
        ses = r.get("status_effects", [])
        if ses:
            for s in ses:
                status_by_cat[cat][s] += 1
                status_total_by_cat[cat] += 1

    print(f"\n{'='*80}")
    print(f"  TABLE 6: Status Effects Applied by Intent Category")
    print(f"{'='*80}")

    rows = []
    for cat in cat_order:
        if cat not in status_by_cat:
            rows.append([cat, "(none)", 0])
            continue
        for effect, count in status_by_cat[cat].most_common():
            rows.append([cat, effect, count])

    print_table(
        ["Intent Category", "Status Effect", "Count"],
        rows,
    )

    # Also show total actions with vs without status effects per category
    print("  Status effect frequency per category:")
    for cat in cat_order:
        total_in_cat = sum(1 for r in all_records if r["intent_category"] == cat)
        with_effects = sum(1 for r in all_records if r["intent_category"] == cat and r.get("status_effects"))
        if total_in_cat > 0:
            pct = 100 * with_effects / total_in_cat
            print(f"    {cat}: {with_effects}/{total_in_cat} actions have status effects ({pct:.1f}%)")
    print()

    # ── TABLE 7: damage_type distribution by intent category ────────────────

    dtype_by_cat = defaultdict(Counter)
    for r in all_records:
        cat = r["intent_category"]
        for de in r.get("damage_effects", []):
            dt = de.get("damage_type", "unknown") or "unknown"
            dtype_by_cat[cat][dt] += 1

    print(f"\n{'='*80}")
    print(f"  TABLE 7: damage_type Distribution by Intent Category")
    print(f"{'='*80}")

    # Collect all damage types
    all_dtypes = set()
    for cat_counts in dtype_by_cat.values():
        all_dtypes.update(cat_counts.keys())
    all_dtypes = sorted(all_dtypes)

    rows = []
    for cat in cat_order:
        if cat not in dtype_by_cat:
            continue
        row = [cat]
        for dt in all_dtypes:
            row.append(dtype_by_cat[cat].get(dt, 0))
        row.append(sum(dtype_by_cat[cat].values()))
        rows.append(row)

    # Also total row
    total_row = ["TOTAL"]
    for dt in all_dtypes:
        total_row.append(sum(dtype_by_cat[cat].get(dt, 0) for cat in dtype_by_cat))
    total_row.append(sum(sum(c.values()) for c in dtype_by_cat.values()))
    rows.append(total_row)

    print_table(
        ["Intent Category"] + all_dtypes + ["Total"],
        rows,
    )

    # Also show by model for the key categories
    print("  damage_type by model (lethal_attack vs suppressing_fire vs non_lethal):")
    dtype_by_cat_model = defaultdict(lambda: defaultdict(Counter))
    for r in all_records:
        cat = r["intent_category"]
        m = r["model"]
        for de in r.get("damage_effects", []):
            dt = de.get("damage_type", "unknown") or "unknown"
            dtype_by_cat_model[cat][m][dt] += 1

    rows = []
    for cat in ["lethal_attack", "suppressing_fire", "non_lethal"]:
        for m in MODELS_ORDER:
            counts = dtype_by_cat_model[cat][m]
            if not counts:
                continue
            row = [cat, m]
            for dt in all_dtypes:
                row.append(counts.get(dt, 0))
            row.append(sum(counts.values()))
            rows.append(row)
        rows.append(["", ""] + [""] * (len(all_dtypes) + 1))

    print_table(
        ["Intent", "Model"] + all_dtypes + ["Total"],
        rows,
    )

    # ── TABLE 8: Interesting intent examples ────────────────────────────────

    print(f"\n{'='*80}")
    print(f"  TABLE 8: Interesting Intent Examples (5 per category)")
    print(f"{'='*80}")

    # Group by category, prefer longer/more interesting intents
    intents_by_cat = defaultdict(list)
    for r in all_records:
        cat = r["intent_category"]
        intents_by_cat[cat].append({
            "intent": r["intent"],
            "description": r["description"],
            "model": r["model"],
            "character": r["character"],
            "run": r["run_id"],
            "round": r["round"],
        })

    # Simple scoring: prefer longer intents, with more specific words
    boring_starts = ["shoot ", "fire ", "attack ", "i shoot", "i fire", "i attack"]

    def interest_score(entry):
        text = (entry["intent"] or "").lower()
        score = len(text)
        # Penalize boring generic intents
        for b in boring_starts:
            if text.startswith(b):
                score -= 50
        # Bonus for tactical language
        for word in ["flank", "cover", "suppress", "controlled", "burst",
                      "momentum", "sweep", "slide", "rush", "feint", "brace",
                      "closing", "intercept", "vulnerable", "exposed"]:
            if word in text:
                score += 20
        return score

    for cat in cat_order:
        entries = intents_by_cat.get(cat, [])
        if not entries:
            continue

        # Sort by interest, pick top 5
        entries.sort(key=interest_score, reverse=True)
        # Deduplicate by intent text
        seen = set()
        unique = []
        for e in entries:
            key = (e["intent"] or "")[:60]
            if key not in seen:
                seen.add(key)
                unique.append(e)
            if len(unique) >= 5:
                break

        print(f"\n  --- {cat.upper()} ({len(intents_by_cat[cat])} total) ---")
        for i, e in enumerate(unique, 1):
            intent = e["intent"] or "(no intent)"
            print(f"  {i}. [{e['model']}/{e['character']}/R{e['round']}] {intent}")
            if e["description"]:
                desc_preview = e["description"][:150]
                print(f"     >> {desc_preview}...")
            print()

    # ── BONUS: Summary statistics ───────────────────────────────────────────

    print(f"\n{'='*80}")
    print(f"  SUMMARY STATISTICS")
    print(f"{'='*80}")

    total = len(all_records)
    by_model = Counter(r["model"] for r in all_records)
    by_char = Counter(r["character"] for r in all_records)
    by_cat = Counter(r["intent_category"] for r in all_records)

    print(f"\n  Total player actions: {total}")
    print(f"\n  By model:")
    for m in MODELS_ORDER:
        print(f"    {m}: {by_model[m]}")
    print(f"\n  By character:")
    for c in sorted(by_char.keys()):
        print(f"    {c}: {by_char[c]}")
    print(f"\n  By intent category:")
    for cat in cat_order:
        if cat in by_cat:
            pct = 100 * by_cat[cat] / total
            print(f"    {cat}: {by_cat[cat]} ({pct:.1f}%)")

    # Average damage dealt per hit by category
    print(f"\n  Average damage dealt (all hits, including 0):")
    for cat in cat_order:
        hits = [r for r in all_records if r["intent_category"] == cat and r["roll_success"] is True]
        if hits:
            avg = sum(r["damage_dealt"] or 0 for r in hits) / len(hits)
            print(f"    {cat}: {avg:.1f} (n={len(hits)} successes)")

    # Unmatched declarations
    unmatched = sum(1 for r in all_records if not r["has_resolution"])
    print(f"\n  Unmatched declarations (no resolution found): {unmatched}")

    # Per-model round counts
    rounds_by_model = defaultdict(set)
    for r in all_records:
        rounds_by_model[r["model"]].add((r["run_id"], r["round"]))
    print(f"\n  Unique (run, round) pairs per model:")
    for m in MODELS_ORDER:
        print(f"    {m}: {len(rounds_by_model[m])}")

    print(f"\n{'='*80}")
    print("  Analysis complete.")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
