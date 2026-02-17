#!/usr/bin/env python3
"""
Treatment v3 Analysis — Suppressive Fire Lethality Experiment
Compares DM base_damage assignment for suppressive vs lethal PC actions.
"""

import json
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path("multiagent_output/lethality_experiment/treatment_v3/run_2026-02-17_070931_b310db5d")

# Model mapping: run_id -> model name
RUN_MODEL = {
    "run_0001": "Claude Opus 4.6",
    "run_0005": "Claude Opus 4.6",
    "run_0002": "DeepSeek V3.2",
    "run_0006": "DeepSeek V3.2",
    "run_0003": "Grok 4",
    "run_0007": "Grok 4",
    "run_0004": "GPT-5.2",
    "run_0008": "GPT-5.2",
}

# v2 baselines from the article
V2_BASELINES = {
    "GPT-5.2":        {"ratio": 0.20, "avg_suppress_base": 0.2,  "n_suppress": 2,  "n_lethal": 19},
    "DeepSeek V3.2":  {"ratio": 0.69, "avg_suppress_base": 7.4,  "n_suppress": 14, "n_lethal": 19},
    "Grok 4":         {"ratio": 0.71, "avg_suppress_base": 8.8,  "n_suppress": 1,  "n_lethal": 26},
    "Claude Opus 4.6":{"ratio": None,  "avg_suppress_base": None, "n_suppress": 0,  "n_lethal": None},
}

# Suppress keywords
SUPPRESS_KEYWORDS = [
    "suppress", "pin down", "pinning", "covering fire", "warning shot",
    "keep their heads down", "area denial", "force them into cover",
    "suppressive", "pin them down", "keep them pinned",
]

STUN_KEYWORDS = ["shock baton", "stun", "non-lethal"]


def classify_intent(action_dict):
    """Classify a PC action_declaration as suppress/stun/lethal.

    Uses keyword matching with negation handling to avoid false positives
    like 'no warning shots' or 'drop or suppress this one' (lethal intent
    using the word 'suppress' in a different sense).
    """
    text = ""
    if isinstance(action_dict, dict):
        text = " ".join([
            str(action_dict.get("intent", "")),
            str(action_dict.get("description", "")),
        ]).lower()
    else:
        text = str(action_dict).lower()

    # Check suppress — with negation and context handling
    suppress_hit = False
    for kw in SUPPRESS_KEYWORDS:
        idx = text.find(kw)
        if idx < 0:
            continue

        # Get preceding context (30 chars before the keyword)
        prefix = text[max(0, idx - 30):idx].strip()

        # Negation check: "no warning shots", "not suppress", etc.
        if re.search(r'\bno\b|\bnot\b|\bwithout\b|\bnever\b', prefix[-15:] if len(prefix) >= 15 else prefix):
            continue

        # Context check for 'suppress':
        # "drop or suppress" = lethal intent (eliminate the target)
        # "lay down suppressing fire" / "suppressive fire" = actual suppress
        if kw == "suppress":
            # Check if it's used as "suppress this one" / "drop or suppress" (lethal)
            after = text[idx:idx + 30]
            if re.search(r'suppress\s+(this|that|the\s+target|him|her|them|it)\b', after):
                continue  # "suppress this one" = eliminate, not suppressive fire
            before_20 = text[max(0, idx - 20):idx]
            if 'drop or' in before_20 or 'kill or' in before_20 or 'neutralize or' in before_20:
                continue  # "drop or suppress" = lethal
            # "standard suppression tactics" in a debrief (social context) is not combat suppress
            if 'tactics' in text[idx:idx + 40] or 'standard' in text[max(0, idx - 20):idx]:
                continue

        suppress_hit = True
        break

    if suppress_hit:
        # Final check: if description explicitly says "WOUND damage" as primary intent,
        # it's lethal even with suppress keywords
        # But "suppressing fire" + "WOUND" could be ambiguous — check if suppress is
        # the primary described action (in intent field)
        intent_text = ""
        if isinstance(action_dict, dict):
            intent_text = str(action_dict.get("intent", "")).lower()

        # If intent explicitly says suppress/pin/covering fire, it's suppress
        for kw in SUPPRESS_KEYWORDS:
            if kw in intent_text:
                return "suppress"

        # If intent doesn't mention suppress but description does,
        # check if description's primary verb is about suppressing
        desc_text = ""
        if isinstance(action_dict, dict):
            desc_text = str(action_dict.get("description", "")).lower()

        # Look for suppressive fire as a described action (not just mentioned)
        if any(phrase in desc_text for phrase in [
            "lay down suppress", "suppressing fire", "suppressive fire",
            "covering fire", "pin them down", "pin down",
            "pinning fire", "keep their heads down",
            "suppress their advance", "forcing the", "force them to take cover",
            "forcing them into cover", "forcing the thugs to take cover",
        ]):
            return "suppress"

        # Check for "suppress" + area denial language in description
        if "suppress" in desc_text and any(p in desc_text for p in [
            "take cover", "fall back", "heads down", "into cover",
        ]):
            return "suppress"

        # Otherwise it's probably incidental use of the word
        # Fall through to other checks

    # Check stun
    for kw in STUN_KEYWORDS:
        if kw in text:
            return "stun"
    return "lethal"


def load_session(jsonl_path):
    """Load all events from a JSONL file."""
    events = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def extract_damage_effects(resolution_event):
    """Extract list of damage effect dicts from an action_resolution event.

    Returns list of dicts with keys: base_damage, dealt, damage_type, target, soak
    """
    effects = []

    # Primary source: context.damage_effects (most detailed)
    ctx = resolution_event.get("context", {})
    if isinstance(ctx, dict):
        dmg_effs = ctx.get("damage_effects", [])
        if isinstance(dmg_effs, list):
            for de in dmg_effs:
                if isinstance(de, dict):
                    effects.append({
                        "base_damage": de.get("base_damage", 0),
                        "dealt": de.get("dealt", 0),
                        "damage_type": de.get("damage_type", "unknown"),
                        "target": de.get("target", "unknown"),
                        "soak": de.get("soak", 0),
                    })

    # If no context.damage_effects, try effects.damage (less detailed)
    if not effects:
        eff = resolution_event.get("effects", {})
        if isinstance(eff, dict):
            dmg = eff.get("damage")
            if isinstance(dmg, dict) and dmg.get("dealt", 0) > 0:
                effects.append({
                    "base_damage": dmg.get("base_damage", None),
                    "dealt": dmg.get("dealt", 0),
                    "damage_type": dmg.get("damage_type", "unknown"),
                    "target": dmg.get("target", "unknown"),
                    "soak": dmg.get("soak", None),
                })
            elif isinstance(dmg, list):
                for d in dmg:
                    if isinstance(d, dict):
                        effects.append({
                            "base_damage": d.get("base_damage", None),
                            "dealt": d.get("dealt", 0),
                            "damage_type": d.get("damage_type", "unknown"),
                            "target": d.get("target", "unknown"),
                            "soak": d.get("soak", None),
                        })

    return effects


def get_status_effects(resolution_event):
    """Extract status effects from an action_resolution."""
    eff = resolution_event.get("effects", {})
    if isinstance(eff, dict):
        se = eff.get("status_effects", [])
        if isinstance(se, list):
            return se
    return []


def analyze_session(jsonl_path, model_name, run_id):
    """Analyze a single session, returning structured data."""
    events = load_session(jsonl_path)

    # Build declaration lookup: (round, player_id) -> declaration event
    declarations = {}
    for e in events:
        if e["event_type"] == "action_declaration":
            key = (e.get("round"), e.get("player_id"))
            declarations[key] = e

    # Collect PC combat resolutions
    pc_combat_actions = []

    for e in events:
        if e["event_type"] != "action_resolution":
            continue

        ctx = e.get("context", {})
        if not isinstance(ctx, dict):
            continue

        action_type = ctx.get("action_type", "")

        # Get the agent name / character
        agent_name = e.get("agent", "")
        round_num = e.get("round")

        # Determine player_id from the event
        # Match to declaration by agent name and round
        player_id = None
        matched_decl = None
        for (r, pid), decl in declarations.items():
            if r == round_num:
                decl_char = decl.get("character_name", "")
                if decl_char == agent_name:
                    player_id = pid
                    matched_decl = decl
                    break

        # Only PC actions
        if player_id and not player_id.startswith("player"):
            continue

        # Record action type for distribution
        pc_combat_actions.append({
            "round": round_num,
            "agent": agent_name,
            "player_id": player_id,
            "action_type": action_type,
            "declaration": matched_decl,
            "resolution": e,
            "model": model_name,
            "run_id": run_id,
        })

    # TPK detection: check last character_state for each PC
    pc_final_states = {}
    for e in events:
        if e["event_type"] == "character_state" and str(e.get("character_id", "")).startswith("player"):
            pc_final_states[e["character_id"]] = e

    # Also check for character_defeated events
    defeated_pcs = set()
    for e in events:
        if e["event_type"] == "character_defeated":
            cid = e.get("character_id", "")
            if cid.startswith("player"):
                defeated_pcs.add(cid)

    # Also check enemy_defeat where killer is a PC (for context)
    # And check is_defeated in character_state
    for pid, state in pc_final_states.items():
        if state.get("is_defeated", False):
            defeated_pcs.add(pid)

    # Count total PCs
    all_pcs = set()
    for e in events:
        if e["event_type"] == "character_state" and str(e.get("character_id", "")).startswith("player"):
            all_pcs.add(e["character_id"])

    tpk = len(defeated_pcs) >= len(all_pcs) and len(all_pcs) > 0

    # Session end info
    session_end = None
    for e in events:
        if e["event_type"] == "session_end":
            session_end = e

    total_rounds = 0
    for e in events:
        if e["event_type"] == "round_start":
            total_rounds += 1

    return {
        "pc_actions": pc_combat_actions,
        "pc_final_states": pc_final_states,
        "defeated_pcs": defeated_pcs,
        "all_pcs": all_pcs,
        "tpk": tpk,
        "session_end": session_end,
        "total_rounds": total_rounds,
        "model": model_name,
        "run_id": run_id,
    }


def main():
    # Collect all sessions
    all_sessions = []

    for run_dir, model in sorted(RUN_MODEL.items()):
        pattern = str(BASE_DIR / run_dir / "session_*.jsonl")
        files = glob.glob(pattern)
        if not files:
            print(f"WARNING: No JSONL found for {run_dir}")
            continue
        jsonl_path = files[0]
        session_data = analyze_session(jsonl_path, model, run_dir)
        all_sessions.append(session_data)

    # ==========================================
    # Classify all PC combat actions
    # ==========================================
    all_combat = []  # combat-type actions with damage analysis
    all_actions = []  # all PC actions for type distribution

    for sess in all_sessions:
        for act in sess["pc_actions"]:
            all_actions.append(act)

            action_type = act["action_type"]
            # Only analyze combat-type actions for damage
            if action_type not in ("combat",):
                continue

            # Classify intent from declaration
            decl = act["declaration"]
            if decl is None:
                intent_class = "lethal"  # default if no declaration found
            else:
                intent_class = classify_intent(decl.get("action", {}))

            # Extract damage effects from resolution
            damage_effects = extract_damage_effects(act["resolution"])
            status_effects = get_status_effects(act["resolution"])

            # Roll info
            roll = act["resolution"].get("roll", {})

            all_combat.append({
                "model": act["model"],
                "run_id": act["run_id"],
                "round": act["round"],
                "agent": act["agent"],
                "intent_class": intent_class,
                "action_type": action_type,
                "damage_effects": damage_effects,
                "status_effects": status_effects,
                "roll": roll,
                "description": decl.get("action", {}).get("description", "")[:150] if decl else "",
                "intent_text": decl.get("action", {}).get("intent", "")[:150] if decl else "",
            })

    # ==========================================
    # TABLE 1: Per-model suppressive fire table
    # ==========================================
    print("=" * 90)
    print("TABLE 1: Suppressive Fire — Per-Model Summary")
    print("=" * 90)

    models = ["Claude Opus 4.6", "DeepSeek V3.2", "Grok 4", "GPT-5.2"]

    header = f"{'Model':<20} {'N suppress':>10} {'N dealt>0':>10} {'Avg dmg(all)':>13} {'Avg dmg(>0)':>12} {'Avg base':>10}"
    print(header)
    print("-" * len(header))

    for model in models:
        suppress_actions = [a for a in all_combat if a["model"] == model and a["intent_class"] == "suppress"]
        n_suppress = len(suppress_actions)

        # Collect all damage effects from suppress actions
        all_dmg = []
        all_base = []
        for a in suppress_actions:
            for de in a["damage_effects"]:
                all_dmg.append(de["dealt"])
                if de["base_damage"] is not None:
                    all_base.append(de["base_damage"])

        # For actions with no damage_effects, count as 0 damage
        n_with_dmg_effects = sum(1 for a in suppress_actions if a["damage_effects"])
        n_no_dmg = n_suppress - n_with_dmg_effects

        # Include 0s for actions with no damage effects
        all_dmg_with_zeros = all_dmg + [0] * n_no_dmg

        n_dealt_gt0 = sum(1 for d in all_dmg if d > 0)
        avg_dmg_all = sum(all_dmg_with_zeros) / len(all_dmg_with_zeros) if all_dmg_with_zeros else 0
        dmg_gt0 = [d for d in all_dmg if d > 0]
        avg_dmg_gt0 = sum(dmg_gt0) / len(dmg_gt0) if dmg_gt0 else 0
        avg_base = sum(all_base) / len(all_base) if all_base else 0

        print(f"{model:<20} {n_suppress:>10} {n_dealt_gt0:>10} {avg_dmg_all:>13.1f} {avg_dmg_gt0:>12.1f} {avg_base:>10.1f}")

    # Totals
    suppress_all = [a for a in all_combat if a["intent_class"] == "suppress"]
    all_dmg_total = []
    all_base_total = []
    for a in suppress_all:
        for de in a["damage_effects"]:
            all_dmg_total.append(de["dealt"])
            if de["base_damage"] is not None:
                all_base_total.append(de["base_damage"])
    n_no_dmg_total = sum(1 for a in suppress_all if not a["damage_effects"])
    all_dmg_total_z = all_dmg_total + [0] * n_no_dmg_total
    n_dealt_gt0_total = sum(1 for d in all_dmg_total if d > 0)
    avg_all_total = sum(all_dmg_total_z) / len(all_dmg_total_z) if all_dmg_total_z else 0
    dmg_gt0_total = [d for d in all_dmg_total if d > 0]
    avg_gt0_total = sum(dmg_gt0_total) / len(dmg_gt0_total) if dmg_gt0_total else 0
    avg_base_tot = sum(all_base_total) / len(all_base_total) if all_base_total else 0

    print("-" * len(header))
    print(f"{'TOTAL':<20} {len(suppress_all):>10} {n_dealt_gt0_total:>10} {avg_all_total:>13.1f} {avg_gt0_total:>12.1f} {avg_base_tot:>10.1f}")

    # ==========================================
    # TABLE 2: Damage Ratio — Suppress vs Lethal
    # ==========================================
    print()
    print("=" * 100)
    print("TABLE 2: Damage Ratio — Suppressive vs Lethal base_damage")
    print("=" * 100)

    header2 = f"{'Model':<20} {'N lethal':>9} {'Avg base(L)':>12} {'N suppress':>11} {'Avg base(S)':>12} {'Ratio S/L':>10}"
    print(header2)
    print("-" * len(header2))

    model_ratios = {}

    for model in models:
        lethal_actions = [a for a in all_combat if a["model"] == model and a["intent_class"] == "lethal"]
        suppress_actions = [a for a in all_combat if a["model"] == model and a["intent_class"] == "suppress"]

        lethal_bases = []
        for a in lethal_actions:
            for de in a["damage_effects"]:
                if de["base_damage"] is not None:
                    lethal_bases.append(de["base_damage"])

        suppress_bases = []
        for a in suppress_actions:
            for de in a["damage_effects"]:
                if de["base_damage"] is not None:
                    suppress_bases.append(de["base_damage"])
            # If no damage_effects, count as base_damage=0
            if not a["damage_effects"]:
                suppress_bases.append(0)

        avg_lethal = sum(lethal_bases) / len(lethal_bases) if lethal_bases else 0
        avg_suppress = sum(suppress_bases) / len(suppress_bases) if suppress_bases else 0
        ratio = avg_suppress / avg_lethal if avg_lethal > 0 else None

        model_ratios[model] = {
            "n_lethal": len(lethal_actions),
            "avg_lethal_base": avg_lethal,
            "n_suppress": len(suppress_actions),
            "avg_suppress_base": avg_suppress,
            "ratio": ratio,
        }

        ratio_str = f"{ratio:.2f}" if ratio is not None else "N/A"
        print(f"{model:<20} {len(lethal_actions):>9} {avg_lethal:>12.1f} {len(suppress_actions):>11} {avg_suppress:>12.1f} {ratio_str:>10}")

    # Overall
    all_lethal = [a for a in all_combat if a["intent_class"] == "lethal"]
    all_suppress = [a for a in all_combat if a["intent_class"] == "suppress"]
    all_lethal_bases = []
    for a in all_lethal:
        for de in a["damage_effects"]:
            if de["base_damage"] is not None:
                all_lethal_bases.append(de["base_damage"])
    all_suppress_bases = []
    for a in all_suppress:
        for de in a["damage_effects"]:
            if de["base_damage"] is not None:
                all_suppress_bases.append(de["base_damage"])
        if not a["damage_effects"]:
            all_suppress_bases.append(0)

    avg_l_all = sum(all_lethal_bases) / len(all_lethal_bases) if all_lethal_bases else 0
    avg_s_all = sum(all_suppress_bases) / len(all_suppress_bases) if all_suppress_bases else 0
    ratio_all = avg_s_all / avg_l_all if avg_l_all > 0 else None
    ratio_all_str = f"{ratio_all:.2f}" if ratio_all is not None else "N/A"

    print("-" * len(header2))
    print(f"{'TOTAL':<20} {len(all_lethal):>9} {avg_l_all:>12.1f} {len(all_suppress):>11} {avg_s_all:>12.1f} {ratio_all_str:>10}")

    # ==========================================
    # TABLE 3: v2 -> v3 Comparison
    # ==========================================
    print()
    print("=" * 110)
    print("TABLE 3: v2 -> v3 Comparison")
    print("=" * 110)

    header3 = f"{'Model':<20} {'v2 ratio':>9} {'v3 ratio':>9} {'Delta':>7} {'v2 avg_base(S)':>15} {'v3 avg_base(S)':>15} {'v2 N(S)':>8} {'v3 N(S)':>8}"
    print(header3)
    print("-" * len(header3))

    for model in models:
        v2 = V2_BASELINES.get(model, {})
        v3 = model_ratios.get(model, {})

        v2_ratio = v2.get("ratio")
        v3_ratio = v3.get("ratio")
        v2_base = v2.get("avg_suppress_base")
        v3_base = v3.get("avg_suppress_base", 0)
        v2_n = v2.get("n_suppress", 0)
        v3_n = v3.get("n_suppress", 0)

        v2r_str = f"{v2_ratio:.2f}" if v2_ratio is not None else "N/A"
        v3r_str = f"{v3_ratio:.2f}" if v3_ratio is not None else "N/A"

        if v2_ratio is not None and v3_ratio is not None:
            delta = v3_ratio - v2_ratio
            delta_str = f"{delta:+.2f}"
        else:
            delta_str = "N/A"

        v2b_str = f"{v2_base:.1f}" if v2_base is not None else "N/A"
        v3b_str = f"{v3_base:.1f}"

        print(f"{model:<20} {v2r_str:>9} {v3r_str:>9} {delta_str:>7} {v2b_str:>15} {v3b_str:>15} {v2_n:>8} {v3_n:>8}")

    # Overall
    v2_overall_ratio = 0.58
    print("-" * len(header3))
    print(f"{'OVERALL':<20} {v2_overall_ratio:>9.2f} {ratio_all_str:>9} {'':>7} {'':>15} {avg_s_all:>15.1f} {'':>8} {len(all_suppress):>8}")

    # ==========================================
    # TABLE 4: Condition Application Rate for Suppressive Actions
    # ==========================================
    print()
    print("=" * 90)
    print("TABLE 4: Condition Application Rate for Suppressive Actions")
    print("=" * 90)

    suppress_conditions_keywords = [
        "pinned", "suppressed", "pinning", "cover", "prone", "stunned",
        "disoriented", "shaken", "cowering", "ducking",
    ]

    header4 = f"{'Model':<20} {'N suppress':>10} {'N with cond':>12} {'% with cond':>12} {'Conditions applied'}"
    print(header4)
    print("-" * 100)

    for model in models:
        suppress_actions = [a for a in all_combat if a["model"] == model and a["intent_class"] == "suppress"]
        n_with_condition = 0
        all_conditions = []

        for a in suppress_actions:
            se = a["status_effects"]
            if se:
                # Check if any condition is related to suppression
                has_relevant = False
                for s in se:
                    all_conditions.append(s)
                    s_lower = s.lower()
                    if any(kw in s_lower for kw in suppress_conditions_keywords):
                        has_relevant = True
                if has_relevant:
                    n_with_condition += 1
                elif se:
                    n_with_condition += 1  # count any status effect

        pct = (n_with_condition / len(suppress_actions) * 100) if suppress_actions else 0
        cond_summary = "; ".join(set(c[:60] for c in all_conditions[:5]))
        print(f"{model:<20} {len(suppress_actions):>10} {n_with_condition:>12} {pct:>11.0f}% {cond_summary[:60]}")

    # ==========================================
    # TABLE 5: Individual Suppressive Action Details
    # ==========================================
    print()
    print("=" * 140)
    print("TABLE 5: Individual Suppressive Action Details")
    print("=" * 140)

    header5 = f"{'Model':<18} {'Run':<10} {'Rnd':>4} {'Character':<25} {'Success':>8} {'Margin':>7} {'Base':>5} {'Dealt':>6} {'Type':<8} {'Conditions'}"
    print(header5)
    print("-" * 140)

    for a in sorted(all_combat, key=lambda x: (x["model"], x["run_id"], x["round"])):
        if a["intent_class"] != "suppress":
            continue

        roll = a["roll"]
        success = roll.get("success", "?")
        margin = roll.get("margin", "?")

        # Damage info
        if a["damage_effects"]:
            for de in a["damage_effects"]:
                base = de.get("base_damage", "?")
                dealt = de.get("dealt", 0)
                dtype = de.get("damage_type", "?")
                conds = "; ".join(s[:40] for s in a["status_effects"][:2]) if a["status_effects"] else "-"
                print(f"{a['model']:<18} {a['run_id']:<10} {a['round']:>4} {a['agent']:<25} {str(success):>8} {margin:>7} {base:>5} {dealt:>6} {dtype:<8} {conds[:50]}")
        else:
            conds = "; ".join(s[:40] for s in a["status_effects"][:2]) if a["status_effects"] else "-"
            print(f"{a['model']:<18} {a['run_id']:<10} {a['round']:>4} {a['agent']:<25} {str(success):>8} {margin:>7} {'N/A':>5} {'0':>6} {'N/A':<8} {conds[:50]}")

    # ==========================================
    # TABLE 6: TPK Rate
    # ==========================================
    print()
    print("=" * 90)
    print("TABLE 6: TPK & Survival Summary")
    print("=" * 90)

    header6 = f"{'Model':<20} {'Run':<10} {'Rounds':>7} {'PCs alive':>10} {'PCs dead':>9} {'TPK':>5} {'End reason':<20}"
    print(header6)
    print("-" * len(header6))

    tpk_by_model = defaultdict(lambda: {"total": 0, "tpk": 0})

    for sess in sorted(all_sessions, key=lambda s: (s["model"], s["run_id"])):
        n_alive = len(sess["all_pcs"]) - len(sess["defeated_pcs"])
        n_dead = len(sess["defeated_pcs"])
        tpk_str = "YES" if sess["tpk"] else "no"
        end_reason = sess["session_end"].get("termination_reason", "?") if sess["session_end"] else "?"

        # Also check final HP
        hp_info = []
        for pid, state in sorted(sess["pc_final_states"].items()):
            hp = state.get("health", "?")
            maxhp = state.get("max_health", "?")
            hp_info.append(f"{state.get('character_name', pid)}: {hp}/{maxhp}")

        print(f"{sess['model']:<20} {sess['run_id']:<10} {sess['total_rounds']:>7} {n_alive:>10} {n_dead:>9} {tpk_str:>5} {end_reason:<20} {'  '.join(hp_info)}")

        tpk_by_model[sess["model"]]["total"] += 1
        if sess["tpk"]:
            tpk_by_model[sess["model"]]["tpk"] += 1

    print()
    print("TPK rates by model:")
    for model in models:
        d = tpk_by_model[model]
        rate = d["tpk"] / d["total"] * 100 if d["total"] > 0 else 0
        print(f"  {model:<20}: {d['tpk']}/{d['total']} ({rate:.0f}%)")

    total_sessions = sum(d["total"] for d in tpk_by_model.values())
    total_tpk = sum(d["tpk"] for d in tpk_by_model.values())
    overall_rate = total_tpk / total_sessions * 100 if total_sessions > 0 else 0
    print(f"  {'OVERALL':<20}: {total_tpk}/{total_sessions} ({overall_rate:.0f}%)")

    # ==========================================
    # TABLE 7: Action Type Distribution
    # ==========================================
    print()
    print("=" * 90)
    print("TABLE 7: PC Action Type Distribution (all PC actions)")
    print("=" * 90)

    # Count action types per model
    type_counts = defaultdict(lambda: defaultdict(int))
    for a in all_actions:
        atype = a["action_type"] or "unknown"
        type_counts[a["model"]][atype] += 1

    all_types = sorted(set(t for m in type_counts.values() for t in m.keys()))

    header7 = f"{'Model':<20}" + "".join(f" {t:>12}" for t in all_types) + f" {'TOTAL':>8}"
    print(header7)
    print("-" * len(header7))

    for model in models:
        counts = type_counts[model]
        total = sum(counts.values())
        row = f"{model:<20}"
        for t in all_types:
            row += f" {counts.get(t, 0):>12}"
        row += f" {total:>8}"
        print(row)

    # Totals
    row = f"{'TOTAL':<20}"
    grand_total = 0
    for t in all_types:
        s = sum(type_counts[m].get(t, 0) for m in models)
        row += f" {s:>12}"
        grand_total += s
    row += f" {grand_total:>8}"
    print("-" * len(header7))
    print(row)

    # ==========================================
    # COMBAT INTENT DISTRIBUTION
    # ==========================================
    print()
    print("=" * 90)
    print("TABLE 8: Combat Intent Classification (combat actions only)")
    print("=" * 90)

    intent_counts = defaultdict(lambda: defaultdict(int))
    for a in all_combat:
        intent_counts[a["model"]][a["intent_class"]] += 1

    all_intents = ["lethal", "suppress", "stun"]
    header8 = f"{'Model':<20}" + "".join(f" {i:>12}" for i in all_intents) + f" {'TOTAL':>8}"
    print(header8)
    print("-" * len(header8))

    for model in models:
        counts = intent_counts[model]
        total = sum(counts.values())
        row = f"{model:<20}"
        for i in all_intents:
            row += f" {counts.get(i, 0):>12}"
        row += f" {total:>8}"
        print(row)

    row = f"{'TOTAL':<20}"
    grand = 0
    for i in all_intents:
        s = sum(intent_counts[m].get(i, 0) for m in models)
        row += f" {s:>12}"
        grand += s
    row += f" {grand:>8}"
    print("-" * len(header8))
    print(row)

    # ==========================================
    # Suppressive action descriptions (for verification)
    # ==========================================
    print()
    print("=" * 140)
    print("APPENDIX: Suppressive Action Descriptions (for intent verification)")
    print("=" * 140)

    for a in sorted(all_combat, key=lambda x: (x["model"], x["run_id"], x["round"])):
        if a["intent_class"] != "suppress":
            continue
        print(f"\n--- {a['model']} / {a['run_id']} / Round {a['round']} / {a['agent']} ---")
        print(f"  Intent: {a['intent_text']}")
        print(f"  Desc:   {a['description']}")
        base_dmgs = [de.get("base_damage", "?") for de in a["damage_effects"]]
        dealt_dmgs = [de.get("dealt", 0) for de in a["damage_effects"]]
        print(f"  base_damage: {base_dmgs}  dealt: {dealt_dmgs}")
        print(f"  Status effects: {a['status_effects']}")


if __name__ == "__main__":
    main()
