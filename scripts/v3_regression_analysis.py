#!/usr/bin/env python3
"""
Treatment v3 Regression Analysis: Lethal & Stun Combat Resolution

Compares v3 suppression-prompt treatment data against v1 baselines to detect
regressions in normal combat resolution (lethal + stun).
"""

import json
import glob
import re
import sys
from collections import defaultdict
from statistics import mean, median

BASE = "multiagent_output/lethality_experiment/treatment_v3/run_2026-02-17_070931_b310db5d"

# Model mapping: run_id -> (short_name, model_id)
MODEL_MAP = {
    "run_0001": ("Claude Opus 4.6", "claude-opus-4-6"),
    "run_0002": ("DeepSeek V3.2", "deepseek-v3.2"),
    "run_0003": ("Grok 4", "grok-4"),
    "run_0004": ("GPT-5.2", "gpt-5.2"),
    "run_0005": ("Claude Opus 4.6", "claude-opus-4-6"),
    "run_0006": ("DeepSeek V3.2", "deepseek-v3.2"),
    "run_0007": ("Grok 4", "grok-4"),
    "run_0008": ("GPT-5.2", "gpt-5.2"),
}

PC_NAMES = {"Drifter Sable", "Enforcer Kael Dren"}

# v1 Baselines (from article)
V1_BASELINES = {
    "Claude Opus 4.6": {"avg_lethal_base": 16.2},
    "DeepSeek V3.2": {"avg_lethal_base": 19.4},
    "Grok 4": {"avg_lethal_base": 23.6},
    "GPT-5.2": {"avg_lethal_base": 16.7},
}
V1_OVERALL_LETHAL_AVG = 19.0
BASELINE_OVERALL_LETHAL_AVG = 19.2

# Suppress intent patterns
SUPPRESS_PATTERNS = [
    r"suppress", r"pin\s*down", r"pinning", r"covering\s*fire",
    r"warning\s*shot", r"keep\s+their\s+heads?\s+down", r"area\s+denial",
    r"force\s+them\s+into\s+cover", r"buying\s+time", r"suppressive",
    r"suppression",
]

# Negation patterns that override suppress classification back to lethal
NEGATION_PATTERNS = [
    r"no\s+warning\s*shot", r"not?\s+suppress", r"no\s+covering\s*fire",
    r"no\s+suppression", r"beyond\s+suppression",
]


def classify_intent(description: str, damage_effects: list) -> str:
    """Classify combat action intent: lethal, stun, suppress, or mixed."""
    desc_lower = description.lower()

    # Check for stun via damage_type
    for d in damage_effects:
        if d.get("damage_type") == "stun":
            return "stun"

    # Check for shock baton mention + stun context
    if "shock" in desc_lower and "baton" in desc_lower:
        return "stun"

    # Check for negation first (e.g. "no warning shots" = lethal)
    has_negation = any(re.search(p, desc_lower) for p in NEGATION_PATTERNS)

    # Check for suppress patterns
    has_suppress = any(re.search(p, desc_lower) for p in SUPPRESS_PATTERNS)

    if has_suppress and not has_negation:
        return "suppress"

    # Check damage_type for mixed
    for d in damage_effects:
        if d.get("damage_type") == "mixed":
            return "mixed"

    return "lethal"


def load_all_events():
    """Load all events from all session JSONL files, tagged with run/model info.
    Also builds a declaration lookup for cross-referencing player intent."""
    all_events = []
    declarations = {}  # (run_id, round, agent_name) -> declaration description
    for fpath in sorted(glob.glob(f"{BASE}/run_*/session_*.jsonl")):
        run_id = fpath.split("/")[-2]
        model_name = MODEL_MAP[run_id][0]
        with open(fpath) as f:
            for line in f:
                e = json.loads(line)
                e["_run_id"] = run_id
                e["_model"] = model_name
                all_events.append(e)
                # Build declaration index
                if e.get("event_type") == "action_declaration":
                    key = (run_id, e.get("round"), e.get("character_name", ""))
                    declarations[key] = e.get("action", {}).get("description", "")
    return all_events, declarations


def extract_pc_combat_resolutions(events, declarations):
    """Extract PC combat action_resolution events with classification.
    Uses both DM description and player declaration for intent classification."""
    results = []
    for e in events:
        if e.get("event_type") != "action_resolution":
            continue
        if e.get("agent") not in PC_NAMES:
            continue
        ctx = e.get("context", {})
        if ctx.get("action_type") != "combat":
            continue

        desc = ctx.get("description", "")
        damage_effects = ctx.get("damage_effects", [])
        roll = e.get("roll", {})

        # Get player declaration for cross-reference
        decl_key = (e["_run_id"], e.get("round"), e.get("agent"))
        player_decl = declarations.get(decl_key, "")

        # Classify using DM description (which includes player declaration text)
        intent = classify_intent(desc, damage_effects)

        # Also classify from player declaration alone for cross-reference
        player_intent = classify_intent(player_decl, damage_effects) if player_decl else intent

        # Check narration for suppress bleed (DM narrates suppress keywords even for lethal actions)
        narration = ctx.get("narration", "").lower()
        narr_suppress_kw = []
        for kw in ["suppress", "grazing", "graze", "pin them down", "pinning",
                    "area denial", "forcing.*cover", "heads down"]:
            if re.search(kw, narration):
                narr_suppress_kw.append(kw)

        # Extract damage info
        base_damage = None
        dealt = None
        damage_type = None
        if damage_effects:
            base_damage = damage_effects[0].get("base_damage")
            dealt = damage_effects[0].get("dealt")
            damage_type = damage_effects[0].get("damage_type")

        results.append({
            "run_id": e["_run_id"],
            "model": e["_model"],
            "agent": e["agent"],
            "round": e.get("round"),
            "intent": intent,
            "player_intent": player_intent,
            "base_damage": base_damage,
            "dealt": dealt,
            "damage_type": damage_type,
            "margin": roll.get("margin"),
            "success": roll.get("success"),
            "d20": roll.get("d20"),
            "dc": roll.get("dc"),
            "total": roll.get("total"),
            "tier": roll.get("tier"),
            "desc_snippet": desc[:150],
            "narr_suppress_kw": narr_suppress_kw,
            "player_decl_snippet": player_decl[:150] if player_decl else "",
        })
    return results


def extract_enemy_combat(events):
    """Extract enemy combat_action events."""
    results = []
    for e in events:
        if e.get("event_type") != "combat_action":
            continue
        attacker = e.get("attacker", {})
        damage = e.get("damage") or {}
        attack = e.get("attack") or {}

        # Only enemy attackers (id starts with enemy_)
        if not attacker.get("id", "").startswith("enemy_"):
            continue

        results.append({
            "run_id": e["_run_id"],
            "model": e["_model"],
            "attacker_name": attacker.get("name"),
            "weapon": e.get("weapon"),
            "base_damage": damage.get("base_damage"),
            "dealt": damage.get("dealt"),
            "damage_type": damage.get("damage_type"),
            "hit": attack.get("hit"),
            "margin": attack.get("margin"),
            "d20": attack.get("d20"),
        })
    return results


def print_separator(char="=", width=100):
    print(char * width)


def print_header(title):
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


def print_table(headers, rows, col_widths=None):
    """Print a formatted table."""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for r in rows:
                max_w = max(max_w, len(str(r[i])))
            col_widths.append(max_w + 2)

    # Header
    header_line = ""
    for i, h in enumerate(headers):
        header_line += str(h).ljust(col_widths[i])
    print(header_line)
    print("-" * sum(col_widths))

    # Rows
    for r in rows:
        row_line = ""
        for i, val in enumerate(r):
            row_line += str(val).ljust(col_widths[i])
        print(row_line)


def margin_bucket(m):
    if m is None:
        return "N/A"
    if m < 0:
        return "<0 (fail)"
    elif m <= 5:
        return "0-5"
    elif m <= 10:
        return "6-10"
    elif m <= 15:
        return "11-15"
    elif m <= 20:
        return "16-20"
    else:
        return "21+"


def main():
    print("Loading v3 treatment session data...")
    events, declarations = load_all_events()
    print(f"  Total events loaded: {len(events)}")
    print(f"  Player declarations indexed: {len(declarations)}")

    pc_combat = extract_pc_combat_resolutions(events, declarations)
    enemy_combat = extract_enemy_combat(events)
    print(f"  PC combat resolutions: {len(pc_combat)}")
    print(f"  Enemy combat actions: {len(enemy_combat)}")

    # === SECTION 0: Intent Classification Summary ===
    print_header("0. INTENT CLASSIFICATION SUMMARY")
    intent_counts = defaultdict(lambda: defaultdict(int))
    for c in pc_combat:
        intent_counts[c["model"]][c["intent"]] += 1
        intent_counts["ALL MODELS"][c["intent"]] += 1

    headers = ["Model", "Lethal", "Stun", "Suppress", "Mixed", "Total"]
    rows = []
    for model in sorted(set(c["model"] for c in pc_combat)) + ["ALL MODELS"]:
        ic = intent_counts[model]
        total = sum(ic.values())
        rows.append([
            model,
            ic.get("lethal", 0),
            ic.get("stun", 0),
            ic.get("suppress", 0),
            ic.get("mixed", 0),
            total,
        ])
    print_table(headers, rows)

    # === SECTION 1: Lethal Combat base_damage by Model ===
    print_header("1. LETHAL COMBAT base_damage BY MODEL (v3 vs v1 Baseline)")

    lethal = [c for c in pc_combat if c["intent"] == "lethal"]
    lethal_by_model = defaultdict(list)
    for c in lethal:
        if c["base_damage"] is not None:
            lethal_by_model[c["model"]].append(c)

    headers = ["Model", "N", "Avg Base", "v1 Avg", "Delta", "Delta %", "Regression?"]
    rows = []
    all_v3_bases = []
    for model in sorted(lethal_by_model.keys()):
        items = lethal_by_model[model]
        bases = [c["base_damage"] for c in items]
        all_v3_bases.extend(bases)
        avg = mean(bases) if bases else 0
        v1_avg = V1_BASELINES.get(model, {}).get("avg_lethal_base", "N/A")
        if isinstance(v1_avg, (int, float)):
            delta = avg - v1_avg
            delta_pct = f"{(delta / v1_avg) * 100:+.1f}%"
            regression = "YES" if delta < -3.0 else "No"
        else:
            delta = "N/A"
            delta_pct = "N/A"
            regression = "N/A"
        rows.append([
            model,
            len(items),
            f"{avg:.1f}",
            f"{v1_avg}" if isinstance(v1_avg, str) else f"{v1_avg:.1f}",
            f"{delta:+.1f}" if isinstance(delta, float) else delta,
            delta_pct,
            regression,
        ])

    # Overall
    if all_v3_bases:
        overall_avg = mean(all_v3_bases)
        delta = overall_avg - V1_OVERALL_LETHAL_AVG
        rows.append([
            "OVERALL",
            len(all_v3_bases),
            f"{overall_avg:.1f}",
            f"{V1_OVERALL_LETHAL_AVG:.1f}",
            f"{delta:+.1f}",
            f"{(delta / V1_OVERALL_LETHAL_AVG) * 100:+.1f}%",
            "YES" if delta < -3.0 else "No",
        ])

    print_table(headers, rows)
    print()
    print("  Regression threshold: avg base_damage drop > 3.0 from v1 baseline")
    print(f"  Expected range for healthy lethal resolution: 15-23 avg base_damage")

    # === SECTION 2: Stun Combat Analysis ===
    print_header("2. STUN (SHOCK BATON) COMBAT ANALYSIS")

    stun = [c for c in pc_combat if c["intent"] == "stun"]
    if not stun:
        print("  No stun actions found in v3 data.")
    else:
        headers = ["Run", "Model", "Agent", "Round", "Base Dmg", "Dealt", "Type", "Margin", "Description"]
        rows = []
        for c in stun:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["base_damage"] if c["base_damage"] is not None else "N/A",
                c["dealt"] if c["dealt"] is not None else "N/A",
                c["damage_type"] or "N/A",
                c["margin"],
                c["desc_snippet"][:80] + "...",
            ])
        print_table(headers, rows)
        print()
        stun_bases = [c["base_damage"] for c in stun if c["base_damage"] is not None]
        if stun_bases:
            print(f"  Stun avg base_damage: {mean(stun_bases):.1f}")
            print(f"  Stun damage_types: {set(c['damage_type'] for c in stun)}")
            print(f"  Expected: damage_type=stun, reasonable base_damage for melee (8-18)")

    # === SECTION 3: Lethal Damage Distribution ===
    print_header("3. LETHAL DAMAGE DISTRIBUTION BY MODEL")

    headers = ["Model", "N", "Avg Base", "Median", "Min", "Max", "Avg Margin", "% Zero Dmg", "N(no dmg_eff)"]
    rows = []
    for model in sorted(set(c["model"] for c in lethal)):
        model_items = [c for c in lethal if c["model"] == model]
        with_base = [c for c in model_items if c["base_damage"] is not None]
        without_base = [c for c in model_items if c["base_damage"] is None]
        bases = [c["base_damage"] for c in with_base]
        margins = [c["margin"] for c in model_items if c["margin"] is not None]
        zero_dmg = len([b for b in bases if b == 0])
        # Also count actions with 0 dealt
        dealt_vals = [c["dealt"] for c in with_base if c["dealt"] is not None]
        zero_dealt = len([d for d in dealt_vals if d == 0])

        rows.append([
            model,
            len(model_items),
            f"{mean(bases):.1f}" if bases else "N/A",
            f"{median(bases):.1f}" if bases else "N/A",
            f"{min(bases)}" if bases else "N/A",
            f"{max(bases)}" if bases else "N/A",
            f"{mean(margins):.1f}" if margins else "N/A",
            f"{(zero_dmg / len(bases)) * 100:.0f}%" if bases else "N/A",
            len(without_base),
        ])

    # Overall
    all_bases = [c["base_damage"] for c in lethal if c["base_damage"] is not None]
    all_margins = [c["margin"] for c in lethal if c["margin"] is not None]
    all_no_eff = len([c for c in lethal if c["base_damage"] is None])
    zero_base_all = len([b for b in all_bases if b == 0])
    rows.append([
        "OVERALL",
        len(lethal),
        f"{mean(all_bases):.1f}" if all_bases else "N/A",
        f"{median(all_bases):.1f}" if all_bases else "N/A",
        f"{min(all_bases)}" if all_bases else "N/A",
        f"{max(all_bases)}" if all_bases else "N/A",
        f"{mean(all_margins):.1f}" if all_margins else "N/A",
        f"{(zero_base_all / len(all_bases)) * 100:.0f}%" if all_bases else "N/A",
        all_no_eff,
    ])
    print_table(headers, rows)
    print()
    print("  N(no dmg_eff) = combat resolutions with no damage_effects array (e.g. suppress/miss)")
    print("  % Zero Dmg = lethal actions where base_damage=0 (REGRESSION SIGNAL if high)")

    # === SECTION 3b: Lethal actions with very low base_damage ===
    print()
    print("  --- Lethal actions with base_damage <= 5 (potential anomalies) ---")
    low_dmg = [c for c in lethal if c["base_damage"] is not None and c["base_damage"] <= 5]
    if low_dmg:
        headers = ["Run", "Model", "Agent", "Rnd", "Base", "Dealt", "Margin", "Tier", "Description"]
        rows = []
        for c in low_dmg:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["base_damage"],
                c["dealt"],
                c["margin"],
                c["tier"],
                c["desc_snippet"][:90] + "...",
            ])
        print_table(headers, rows)
    else:
        print("  None found. All lethal base_damage > 5.")

    # === SECTION 4: Lethal Damage by Margin Bucket ===
    print_header("4. LETHAL base_damage BY MARGIN BUCKET (Per Model)")

    # Build data
    bucket_data = defaultdict(lambda: defaultdict(list))  # model -> bucket -> [base_damage]
    for c in lethal:
        if c["base_damage"] is not None and c["margin"] is not None:
            bucket = margin_bucket(c["margin"])
            bucket_data[c["model"]][bucket].append(c["base_damage"])
            bucket_data["ALL MODELS"][bucket].append(c["base_damage"])

    bucket_order = ["<0 (fail)", "0-5", "6-10", "11-15", "16-20", "21+"]
    headers = ["Model"] + bucket_order
    rows = []
    for model in sorted(set(c["model"] for c in lethal)) + ["ALL MODELS"]:
        row = [model]
        for bucket in bucket_order:
            vals = bucket_data[model].get(bucket, [])
            if vals:
                row.append(f"{mean(vals):.1f} (n={len(vals)})")
            else:
                row.append("-")
        rows.append(row)
    print_table(headers, rows, col_widths=[18, 14, 14, 14, 14, 14, 14])
    print()
    print("  Expected: base_damage should generally scale with margin (higher margin -> more damage)")
    print("  A flat or inverted pattern would suggest the DM is not scaling damage with roll quality")

    # === SECTION 5: Enemy Combat Sanity Check ===
    print_header("5. ENEMY COMBAT ACTIONS (Mechanical Formula — Sanity Check)")

    enemy_by_model = defaultdict(list)
    for c in enemy_combat:
        enemy_by_model[c["model"]].append(c)

    headers = ["Model", "N", "N Hit", "Hit %", "Avg Base Dmg", "Avg Dealt", "Avg Margin"]
    rows = []
    for model in sorted(enemy_by_model.keys()):
        items = enemy_by_model[model]
        hits = [c for c in items if c["hit"]]
        bases = [c["base_damage"] for c in items if c["base_damage"] is not None]
        dealts = [c["dealt"] for c in items if c["dealt"] is not None]
        margins = [c["margin"] for c in items if c["margin"] is not None]
        rows.append([
            model,
            len(items),
            len(hits),
            f"{(len(hits) / len(items)) * 100:.0f}%" if items else "N/A",
            f"{mean(bases):.1f}" if bases else "N/A",
            f"{mean(dealts):.1f}" if dealts else "N/A",
            f"{mean(margins):.1f}" if margins else "N/A",
        ])

    # Overall
    all_items = enemy_combat
    all_hits = [c for c in all_items if c["hit"]]
    all_bases_e = [c["base_damage"] for c in all_items if c["base_damage"] is not None]
    all_dealts_e = [c["dealt"] for c in all_items if c["dealt"] is not None]
    all_margins_e = [c["margin"] for c in all_items if c["margin"] is not None]
    rows.append([
        "OVERALL",
        len(all_items),
        len(all_hits),
        f"{(len(all_hits) / len(all_items)) * 100:.0f}%" if all_items else "N/A",
        f"{mean(all_bases_e):.1f}" if all_bases_e else "N/A",
        f"{mean(all_dealts_e):.1f}" if all_dealts_e else "N/A",
        f"{mean(all_margins_e):.1f}" if all_margins_e else "N/A",
    ])
    print_table(headers, rows)
    print()
    print("  Enemy combat uses mechanical formula (not DM-generated). Should be unaffected by prompt changes.")
    print("  Any significant deviations would indicate a code bug, not a prompt regression.")

    # === SECTION 6: Suppress Actions Detail ===
    print_header("6. SUPPRESSION ACTIONS DETECTED (Should Have 0 Wound Damage)")

    suppress = [c for c in pc_combat if c["intent"] == "suppress"]
    if not suppress:
        print("  No suppress-intent actions found in v3 data.")
    else:
        headers = ["Run", "Model", "Agent", "Rnd", "Base", "Dealt", "Type", "Margin", "Description"]
        rows = []
        for c in suppress:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["base_damage"] if c["base_damage"] is not None else "none",
                c["dealt"] if c["dealt"] is not None else "none",
                c["damage_type"] or "none",
                c["margin"],
                c["desc_snippet"][:90] + "...",
            ])
        print_table(headers, rows)
        # Check for wound damage in suppress actions
        wound_suppress = [c for c in suppress if c["damage_type"] == "wound" and c["base_damage"] and c["base_damage"] > 0]
        if wound_suppress:
            print(f"\n  WARNING: {len(wound_suppress)} suppression actions dealt WOUND damage (should be 0 or stun)")
        else:
            print(f"\n  OK: All {len(suppress)} suppression actions have no wound damage (correct behavior)")

    # === SECTION 7: Mixed-type Actions Detail ===
    mixed = [c for c in pc_combat if c["intent"] == "mixed"]
    if mixed:
        print_header("7. MIXED-TYPE ACTIONS DETAIL")
        headers = ["Run", "Model", "Agent", "Rnd", "Base", "Dealt", "Type", "Margin", "Description"]
        rows = []
        for c in mixed:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["base_damage"] if c["base_damage"] is not None else "none",
                c["dealt"] if c["dealt"] is not None else "none",
                c["damage_type"] or "none",
                c["margin"],
                c["desc_snippet"][:90] + "...",
            ])
        print_table(headers, rows)

    # === SECTION 8: Combat resolutions with NO damage_effects ===
    print_header("8. COMBAT RESOLUTIONS WITH NO damage_effects (PC Only)")
    no_dmg = [c for c in pc_combat if c["base_damage"] is None and c["intent"] in ("lethal", "suppress")]
    if no_dmg:
        headers = ["Run", "Model", "Agent", "Rnd", "Intent", "Margin", "Success", "Description"]
        rows = []
        for c in no_dmg:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["intent"],
                c["margin"],
                c["success"],
                c["desc_snippet"][:90] + "...",
            ])
        print_table(headers, rows)
        print(f"\n  Total: {len(no_dmg)} combat resolutions with no damage_effects")
        print("  Suppress without damage = CORRECT behavior (suppression shouldn't deal wound damage)")
        print("  Lethal without damage = potential issue (unless roll failed)")
    else:
        print("  All PC combat resolutions have damage_effects.")

    # === SECTION 9: Per-run Summary ===
    print_header("9. PER-RUN LETHAL SUMMARY")
    headers = ["Run", "Model", "N Lethal", "Avg Base", "N Stun", "N Suppress", "N Mixed", "N No-Effect"]
    rows = []
    for run_id in sorted(MODEL_MAP.keys()):
        model = MODEL_MAP[run_id][0]
        run_combat = [c for c in pc_combat if c["run_id"] == run_id]
        run_lethal = [c for c in run_combat if c["intent"] == "lethal" and c["base_damage"] is not None]
        run_stun = [c for c in run_combat if c["intent"] == "stun"]
        run_suppress = [c for c in run_combat if c["intent"] == "suppress"]
        run_mixed = [c for c in run_combat if c["intent"] == "mixed"]
        run_no_eff = [c for c in run_combat if c["base_damage"] is None]
        bases = [c["base_damage"] for c in run_lethal]
        rows.append([
            run_id,
            model,
            len(run_lethal),
            f"{mean(bases):.1f}" if bases else "N/A",
            len(run_stun),
            len(run_suppress),
            len(run_mixed),
            len(run_no_eff),
        ])
    print_table(headers, rows)

    # === SECTION 10: Suppression Bleed-Through Analysis ===
    print_header("10. SUPPRESSION BLEED-THROUGH ANALYSIS")
    print()
    print("  Checks if the DM narrates suppression behavior even when the player declared")
    print("  lethal intent. This is the core regression risk of the v3 suppress prompt.")
    print()

    # Find lethal actions where DM narration contains suppress keywords
    bleed_cases = []
    for c in pc_combat:
        if c["intent"] == "lethal" and c["narr_suppress_kw"]:
            bleed_cases.append(c)

    if bleed_cases:
        headers = ["Run", "Model", "Agent", "Rnd", "Base", "Margin", "Suppress KW in Narration"]
        rows = []
        for c in bleed_cases:
            rows.append([
                c["run_id"],
                c["model"],
                c["agent"],
                c["round"],
                c["base_damage"] if c["base_damage"] is not None else "none",
                c["margin"],
                ", ".join(c["narr_suppress_kw"]),
            ])
        print_table(headers, rows)
        print()

        # Compute impact
        bleed_with_dmg = [c for c in bleed_cases if c["base_damage"] is not None]
        non_bleed_lethal = [c for c in lethal if c["base_damage"] is not None and not c["narr_suppress_kw"]]
        if bleed_with_dmg and non_bleed_lethal:
            bleed_avg = mean([c["base_damage"] for c in bleed_with_dmg])
            clean_avg = mean([c["base_damage"] for c in non_bleed_lethal])
            print(f"  Lethal actions WITH suppress bleed in narration: avg base={bleed_avg:.1f} (n={len(bleed_with_dmg)})")
            print(f"  Lethal actions WITHOUT suppress bleed:           avg base={clean_avg:.1f} (n={len(non_bleed_lethal)})")
            print(f"  Delta: {bleed_avg - clean_avg:+.1f}")
            if bleed_avg < clean_avg - 3:
                print("  ** BLEED CONFIRMED: Suppress keywords in narration correlate with lower base_damage **")
            else:
                print("  Suppress keywords in narration but base_damage not significantly affected.")

        # Per-model bleed rate
        print()
        print("  Per-model bleed rate (lethal actions with suppress keywords in DM narration):")
        for model in sorted(set(c["model"] for c in lethal)):
            model_lethal = [c for c in lethal if c["model"] == model]
            model_bleed = [c for c in bleed_cases if c["model"] == model]
            pct = (len(model_bleed) / len(model_lethal) * 100) if model_lethal else 0
            print(f"    {model}: {len(model_bleed)}/{len(model_lethal)} ({pct:.0f}%)")
    else:
        print("  No suppression bleed-through detected in lethal actions.")

    # === SECTION 11: Grok 4 Deep Dive ===
    grok_lethal = [c for c in lethal if c["model"] == "Grok 4" and c["base_damage"] is not None]
    grok_suppress = [c for c in pc_combat if c["model"] == "Grok 4" and c["intent"] == "suppress"]
    grok_no_eff = [c for c in pc_combat if c["model"] == "Grok 4" and c["intent"] == "lethal" and c["base_damage"] is None]
    if grok_lethal or grok_suppress:
        print_header("11. GROK 4 DEEP DIVE (Potential Model-Specific Regression)")
        print()
        print(f"  Grok 4 lethal actions (with damage): {len(grok_lethal)}, avg base={mean([c['base_damage'] for c in grok_lethal]):.1f}")
        print(f"  Grok 4 suppress actions: {len(grok_suppress)}")
        print(f"  Grok 4 lethal w/o damage_effects: {len(grok_no_eff)}")
        print(f"  v1 baseline: avg lethal base=23.6")
        print()
        print("  Grok 4 has the highest suppress rate ({:.0f}% of combat actions) and the".format(
            len(grok_suppress) / len([c for c in pc_combat if c["model"] == "Grok 4"]) * 100
        ))
        print("  lowest lethal avg base_damage. Two hypotheses:")
        print("  1. Grok's player agent defaults to suppressive behavior (player-side effect)")
        print("  2. Grok's DM agent reduces damage on ambiguous-intent actions (DM-side bleed)")
        print()

        # Show Grok's lethal actions by run to check if one run is worse
        for run_id in ["run_0003", "run_0007"]:
            run_lethal = [c for c in grok_lethal if c["run_id"] == run_id]
            run_supp = [c for c in grok_suppress if c["run_id"] == run_id]
            if run_lethal:
                print(f"  {run_id}: {len(run_lethal)} lethal (avg base={mean([c['base_damage'] for c in run_lethal]):.1f}), {len(run_supp)} suppress")

    # === FINAL VERDICT ===
    print_header("REGRESSION VERDICT")
    print()

    # Check lethal base_damage
    if all_bases:
        overall_v3 = mean(all_bases)
        delta = overall_v3 - V1_OVERALL_LETHAL_AVG
        print(f"  Overall v3 lethal avg base_damage: {overall_v3:.1f}")
        print(f"  Overall v1 lethal avg base_damage: {V1_OVERALL_LETHAL_AVG:.1f}")
        print(f"  Delta: {delta:+.1f} ({(delta / V1_OVERALL_LETHAL_AVG) * 100:+.1f}%)")
        print()

        if delta < -3.0:
            print("  ** REGRESSION DETECTED: Lethal base_damage significantly below v1 baseline **")
            print("  The suppression prompt may be bleeding into lethal resolution.")
        elif delta < -1.5:
            print("  CAUTION: Lethal base_damage slightly below v1 baseline (within noise margin)")
            print("  Monitor in future runs but not a clear regression.")
        elif abs(delta) <= 3.0:
            print("  OK: Lethal base_damage is within normal range of v1 baseline")
            print("  No regression detected in lethal combat resolution.")
        else:
            print("  NOTE: Lethal base_damage is ABOVE v1 baseline (no regression, possibly stronger)")

    # Check zero-damage lethal
    zero_base_lethal = len([c for c in lethal if c["base_damage"] is not None and c["base_damage"] == 0])
    if all_bases:
        zero_pct = (zero_base_lethal / len(all_bases)) * 100
        print()
        print(f"  Zero-damage lethal actions: {zero_base_lethal}/{len(all_bases)} ({zero_pct:.1f}%)")
        if zero_pct > 5:
            print("  ** REGRESSION: >5% of lethal actions deal 0 base_damage **")
        else:
            print("  OK: Zero-damage rate within acceptable range")

    # Stun check
    print()
    stun_ok = all(c["damage_type"] in ("stun", None) for c in stun) if stun else True
    if stun:
        print(f"  Stun actions found: {len(stun)}")
        print(f"  Stun damage types correct: {'Yes' if stun_ok else 'NO - REGRESSION'}")
    else:
        print("  No stun actions in v3 data (cannot assess stun regression)")

    # Grok regression
    if grok_lethal:
        grok_avg = mean([c["base_damage"] for c in grok_lethal])
        grok_delta = grok_avg - V1_BASELINES["Grok 4"]["avg_lethal_base"]
        print()
        print(f"  Grok 4 specific: v3 avg={grok_avg:.1f}, v1 avg=23.6, delta={grok_delta:+.1f} ({grok_delta/23.6*100:+.1f}%)")
        if grok_delta < -5:
            print("  ** MODEL-SPECIFIC REGRESSION: Grok 4 lethal damage dropped significantly **")
            print("    However, Grok also has high suppress action rate (player-side effect).")
            print("    The DM is also generating base_damage=1 for some 'lethal' actions that")
            print("    contain suppress keywords in the narration -- indicating DM-side bleed.")
        else:
            print("  Grok 4 within acceptable range.")

    # Excluding Grok
    non_grok_lethal = [c for c in lethal if c["model"] != "Grok 4" and c["base_damage"] is not None]
    if non_grok_lethal:
        non_grok_avg = mean([c["base_damage"] for c in non_grok_lethal])
        non_grok_delta = non_grok_avg - V1_OVERALL_LETHAL_AVG
        print()
        print(f"  Excluding Grok 4: v3 lethal avg base={non_grok_avg:.1f}, delta from v1={non_grok_delta:+.1f} ({non_grok_delta/V1_OVERALL_LETHAL_AVG*100:+.1f}%)")
        if abs(non_grok_delta) <= 2:
            print("  Non-Grok models show NO regression in lethal combat resolution.")
        elif non_grok_delta < -2:
            print("  CAUTION: Even excluding Grok, slight downward trend in lethal damage.")

    print()
    print_separator()


if __name__ == "__main__":
    main()
