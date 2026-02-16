#!/usr/bin/env python3
"""
Comprehensive Enemy & NPC Behavior Analysis across LLM Models
Analyzes YAGS session JSONL data from lethality experiment combat ambush runs.
"""

import json
import glob
import os
from collections import defaultdict, Counter

# ============================================================
# CONFIGURATION
# ============================================================
BASE_DIR = "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_113048_5276cf26"

MODEL_RUNS = {
    "GPT-5.2":       ["run_0001", "run_0006", "run_0011", "run_0016", "run_0021"],
    "Grok 4":        ["run_0002", "run_0007", "run_0012", "run_0017", "run_0022"],
    "Gemini 2.5 Pro":["run_0003", "run_0008", "run_0013", "run_0018", "run_0023"],
    "DeepSeek V3.2": ["run_0005", "run_0010", "run_0015", "run_0020", "run_0025"],
}

ALL_MODELS = ["GPT-5.2", "Grok 4", "Gemini 2.5 Pro", "DeepSeek V3.2"]

# ============================================================
# DATA LOADING
# ============================================================

def load_session(run_dir):
    """Load all events from a session JSONL file."""
    files = glob.glob(os.path.join(run_dir, "session_*.jsonl"))
    if not files:
        return []
    events = []
    with open(files[0]) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def load_all_sessions():
    """Load all sessions grouped by model."""
    data = {}
    for model, runs in MODEL_RUNS.items():
        data[model] = {}
        for run in runs:
            run_dir = os.path.join(BASE_DIR, run)
            events = load_session(run_dir)
            if events:
                data[model][run] = events
    return data


# ============================================================
# FORMATTING HELPERS
# ============================================================

def print_header(title):
    print()
    print("=" * 90)
    print(f"  {title}")
    print("=" * 90)


def print_subheader(title):
    print()
    print(f"--- {title} ---")


def print_table(headers, rows, col_widths=None):
    """Print a formatted table."""
    if not col_widths:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for r in rows:
                if i < len(r):
                    max_w = max(max_w, len(str(r[i])))
            col_widths.append(min(max_w + 2, 40))

    # Header
    hdr = ""
    for i, h in enumerate(headers):
        hdr += str(h).ljust(col_widths[i])
    print(hdr)
    print("-" * sum(col_widths))

    # Rows
    for row in rows:
        line = ""
        for i, val in enumerate(row):
            if i < len(col_widths):
                line += str(val).ljust(col_widths[i])
        print(line)


# ============================================================
# ENEMY ANALYSIS
# ============================================================

def analyze_enemy_declarations(data):
    """1. Enemy action_declaration events."""
    print_header("1. ENEMY ACTION DECLARATIONS")

    # Per-model action counts
    model_actions = {m: Counter() for m in ALL_MODELS}
    model_targets = {m: Counter() for m in ALL_MODELS}
    model_total = {m: 0 for m in ALL_MODELS}
    per_run_details = {}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            run_actions = Counter()
            for e in events:
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("enemy_"):
                    action = e.get("action", {})
                    major = action.get("major_action", "unknown")
                    target = action.get("target", "none")
                    model_actions[model][major] += 1
                    model_targets[model][target] += 1
                    model_total[model] += 1
                    run_actions[major] += 1
            per_run_details[(model, run)] = run_actions

    # All unique actions across all models
    all_actions = set()
    for c in model_actions.values():
        all_actions.update(c.keys())
    all_actions = sorted(all_actions)

    print_subheader("Enemy Declared Actions by Model (counts)")
    headers = ["Action"] + ALL_MODELS + ["Total"]
    rows = []
    for action in all_actions:
        row = [action]
        total = 0
        for m in ALL_MODELS:
            cnt = model_actions[m][action]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    # Totals row
    rows.append(["TOTAL"] + [model_total[m] for m in ALL_MODELS] + [sum(model_total.values())])
    print_table(headers, rows)

    print_subheader("Enemy Declared Actions by Model (percentages)")
    headers = ["Action"] + ALL_MODELS
    rows = []
    for action in all_actions:
        row = [action]
        for m in ALL_MODELS:
            tot = model_total[m]
            cnt = model_actions[m][action]
            pct = f"{cnt/tot*100:.1f}%" if tot > 0 else "0.0%"
            row.append(f"{cnt} ({pct})")
        rows.append(row)
    print_table(headers, rows, col_widths=[25, 18, 18, 18, 18])

    # Per-run breakdown
    print_subheader("Enemy Declarations Per Run")
    headers = ["Model", "Run", "Total", "Top Actions"]
    rows = []
    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            rc = per_run_details.get((model, run), Counter())
            total = sum(rc.values())
            top3 = ", ".join(f"{a}:{c}" for a, c in rc.most_common(3))
            rows.append([model, run, total, top3])
    print_table(headers, rows, col_widths=[16, 12, 8, 50])


def analyze_combat_actions(data):
    """2. Enemy combat_action events."""
    print_header("2. ENEMY COMBAT ACTIONS")

    model_hits = {m: 0 for m in ALL_MODELS}
    model_misses = {m: 0 for m in ALL_MODELS}
    model_dmg = {m: [] for m in ALL_MODELS}
    model_weapons = {m: Counter() for m in ALL_MODELS}
    model_targets_pc = {m: Counter() for m in ALL_MODELS}
    per_run_combat = {}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            run_stats = {"hits": 0, "misses": 0, "total_dmg": 0, "attacks": 0}
            for e in events:
                if e.get("event_type") != "combat_action":
                    continue
                attacker = e.get("attacker", {})
                att_id = attacker.get("id", "")
                if not att_id.startswith("enemy_"):
                    continue

                attack = e.get("attack") or {}
                damage = e.get("damage") or {}
                defender = e.get("defender") or {}
                weapon = e.get("weapon", "Unknown")

                hit = attack.get("hit", False)
                dealt = damage.get("dealt", 0) or 0
                d20 = attack.get("d20", 0)
                defender_name = defender.get("name", "Unknown")

                if hit:
                    model_hits[model] += 1
                    model_dmg[model].append(dealt)
                    run_stats["hits"] += 1
                    run_stats["total_dmg"] += dealt
                else:
                    model_misses[model] += 1
                    run_stats["misses"] += 1

                run_stats["attacks"] += 1
                model_weapons[model][weapon] += 1

                # Track PC targeting
                if "Kael" in defender_name:
                    model_targets_pc[model]["Kael Dren"] += 1
                elif "Sable" in defender_name:
                    model_targets_pc[model]["Sable"] += 1
                else:
                    model_targets_pc[model][defender_name] += 1

            per_run_combat[(model, run)] = run_stats

    # Summary table
    print_subheader("Enemy Combat Summary by Model")
    headers = ["Model", "Attacks", "Hits", "Misses", "Hit Rate", "Avg Dmg/Hit", "Total Dmg"]
    rows = []
    for m in ALL_MODELS:
        total_attacks = model_hits[m] + model_misses[m]
        hit_rate = f"{model_hits[m]/total_attacks*100:.1f}%" if total_attacks > 0 else "N/A"
        avg_dmg = f"{sum(model_dmg[m])/len(model_dmg[m]):.1f}" if model_dmg[m] else "N/A"
        total_dmg = sum(model_dmg[m])
        rows.append([m, total_attacks, model_hits[m], model_misses[m], hit_rate, avg_dmg, total_dmg])
    print_table(headers, rows, col_widths=[16, 10, 8, 8, 10, 14, 12])

    # Weapon distribution
    all_weapons = set()
    for c in model_weapons.values():
        all_weapons.update(c.keys())
    all_weapons = sorted(all_weapons)

    print_subheader("Weapon Distribution (enemy attacks)")
    headers = ["Weapon"] + ALL_MODELS + ["Total"]
    rows = []
    for w in all_weapons:
        row = [w]
        total = 0
        for m in ALL_MODELS:
            cnt = model_weapons[m][w]
            total += cnt
            tot_att = sum(model_weapons[m].values())
            pct = f"{cnt/tot_att*100:.0f}%" if tot_att > 0 else ""
            row.append(f"{cnt} ({pct})")
        row.append(total)
        rows.append(row)
    print_table(headers, rows, col_widths=[20, 16, 16, 16, 16, 8])

    # PC targeting
    print_subheader("PC Targeting by Enemies (who gets attacked more?)")
    headers = ["Target"] + ALL_MODELS + ["Total"]
    all_targets = set()
    for c in model_targets_pc.values():
        all_targets.update(c.keys())
    all_targets = sorted(all_targets)
    rows = []
    for t in all_targets:
        row = [t]
        total = 0
        for m in ALL_MODELS:
            cnt = model_targets_pc[m][t]
            total += cnt
            tot = sum(model_targets_pc[m].values())
            pct = f"{cnt/tot*100:.0f}%" if tot > 0 else ""
            row.append(f"{cnt} ({pct})")
        row.append(total)
        rows.append(row)
    print_table(headers, rows, col_widths=[22, 16, 16, 16, 16, 8])

    # Per-run combat details
    print_subheader("Enemy Combat Per Run")
    headers = ["Model", "Run", "Attacks", "Hits", "Hit Rate", "Total Dmg", "Avg Dmg/Hit"]
    rows = []
    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            rs = per_run_combat.get((model, run), {"attacks": 0, "hits": 0, "misses": 0, "total_dmg": 0})
            att = rs["attacks"]
            hits = rs["hits"]
            hit_rate = f"{hits/att*100:.0f}%" if att > 0 else "N/A"
            avg = f"{rs['total_dmg']/hits:.1f}" if hits > 0 else "N/A"
            rows.append([model, run, att, hits, hit_rate, rs["total_dmg"], avg])
    print_table(headers, rows, col_widths=[16, 12, 10, 8, 10, 12, 14])

    # Damage distribution per hit
    print_subheader("Damage Distribution Per Hit by Model")
    for m in ALL_MODELS:
        dmg_list = model_dmg[m]
        if not dmg_list:
            print(f"  {m}: No hits recorded")
            continue
        zeros = sum(1 for d in dmg_list if d == 0)
        nonzero = [d for d in dmg_list if d > 0]
        max_d = max(dmg_list) if dmg_list else 0
        min_nz = min(nonzero) if nonzero else 0
        median_d = sorted(dmg_list)[len(dmg_list)//2]
        print(f"  {m}: hits={len(dmg_list)}, 0-dmg hits={zeros} ({zeros/len(dmg_list)*100:.0f}%), "
              f"min(>0)={min_nz}, median={median_d}, max={max_d}, avg={sum(dmg_list)/len(dmg_list):.1f}")


def analyze_enemy_spawning(data):
    """3. Enemy spawning analysis."""
    print_header("3. ENEMY SPAWNING")

    model_spawn_by_round = {m: Counter() for m in ALL_MODELS}
    model_templates = {m: Counter() for m in ALL_MODELS}
    model_factions = {m: Counter() for m in ALL_MODELS}
    model_total_spawns = {m: 0 for m in ALL_MODELS}
    per_run_spawns = {}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            run_spawns = []
            for e in events:
                if e.get("event_type") == "enemy_spawn":
                    rnd = e.get("round", 0)
                    template = e.get("template", "unknown")
                    faction = e.get("faction", "Unknown")
                    name = e.get("enemy_name", "")

                    model_spawn_by_round[model][rnd] += 1
                    model_templates[model][template] += 1
                    model_factions[model][faction] += 1
                    model_total_spawns[model] += 1
                    run_spawns.append({
                        "round": rnd,
                        "name": name,
                        "template": template,
                        "faction": faction,
                    })
            per_run_spawns[(model, run)] = run_spawns

    # Spawns per round
    all_rounds = set()
    for c in model_spawn_by_round.values():
        all_rounds.update(c.keys())
    all_rounds = sorted(all_rounds)

    print_subheader("Enemy Spawns by Round (when do enemies appear?)")
    headers = ["Round"] + ALL_MODELS + ["Total"]
    rows = []
    for rnd in all_rounds:
        row = [f"Round {rnd}"]
        total = 0
        for m in ALL_MODELS:
            cnt = model_spawn_by_round[m][rnd]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    rows.append(["TOTAL"] + [model_total_spawns[m] for m in ALL_MODELS] + [sum(model_total_spawns.values())])
    print_table(headers, rows)

    # Template distribution
    print_subheader("Enemy Templates (types)")
    all_templates = set()
    for c in model_templates.values():
        all_templates.update(c.keys())
    all_templates = sorted(all_templates, key=str.lower)
    headers = ["Template"] + ALL_MODELS + ["Total"]
    rows = []
    for t in all_templates:
        row = [t]
        total = 0
        for m in ALL_MODELS:
            cnt = model_templates[m][t]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    print_table(headers, rows)

    # Faction distribution
    print_subheader("Enemy Factions")
    all_factions = set()
    for c in model_factions.values():
        all_factions.update(c.keys())
    all_factions = sorted(all_factions)
    headers = ["Faction"] + ALL_MODELS + ["Total"]
    rows = []
    for f in all_factions:
        row = [f]
        total = 0
        for m in ALL_MODELS:
            cnt = model_factions[m][f]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    print_table(headers, rows)

    # Reinforcement analysis (post-round-0 spawns)
    print_subheader("Reinforcement Spawns (post-round-0) Per Run")
    headers = ["Model", "Run", "Round-0", "Reinforcements", "Reinf. Rounds", "Reinf. Names"]
    rows = []
    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            spawns = per_run_spawns.get((model, run), [])
            r0 = [s for s in spawns if s["round"] == 0]
            reinforcements = [s for s in spawns if s["round"] > 0]
            reinf_rounds = sorted(set(s["round"] for s in reinforcements)) if reinforcements else []
            reinf_names = ", ".join(s["name"] for s in reinforcements[:4])
            if len(reinforcements) > 4:
                reinf_names += f" (+{len(reinforcements)-4} more)"
            rows.append([model, run, len(r0), len(reinforcements),
                        str(reinf_rounds) if reinf_rounds else "none", reinf_names or "none"])
    print_table(headers, rows, col_widths=[16, 12, 10, 16, 16, 45])


def analyze_enemy_defeats(data):
    """4. Enemy defeat events."""
    print_header("4. ENEMY DEFEATS")

    model_reasons = {m: Counter() for m in ALL_MODELS}
    model_rounds_survived = {m: [] for m in ALL_MODELS}
    model_killers = {m: Counter() for m in ALL_MODELS}
    model_final_damage = {m: [] for m in ALL_MODELS}
    model_total_defeats = {m: 0 for m in ALL_MODELS}
    per_run_defeats = {}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            run_defeats = []
            for e in events:
                if e.get("event_type") == "enemy_defeat":
                    reason = e.get("defeat_reason", "unknown")
                    rounds_survived = e.get("rounds_survived", 0) or 0
                    killer = e.get("killer_name", "unknown")
                    final_dmg = e.get("final_damage", 0) or 0
                    enemy_name = e.get("enemy_name", "")

                    model_reasons[model][reason] += 1
                    model_rounds_survived[model].append(rounds_survived)
                    model_killers[model][killer or "unknown"] += 1
                    model_final_damage[model].append(final_dmg)
                    model_total_defeats[model] += 1
                    run_defeats.append({
                        "name": enemy_name,
                        "reason": reason,
                        "rounds_survived": rounds_survived,
                        "killer": killer,
                    })
            per_run_defeats[(model, run)] = run_defeats

    # Defeat reasons
    all_reasons = set()
    for c in model_reasons.values():
        all_reasons.update(c.keys())
    all_reasons = sorted(all_reasons)

    print_subheader("Defeat Reasons by Model")
    headers = ["Reason"] + ALL_MODELS + ["Total"]
    rows = []
    for reason in all_reasons:
        row = [reason]
        total = 0
        for m in ALL_MODELS:
            cnt = model_reasons[m][reason]
            total += cnt
            tot = model_total_defeats[m]
            pct = f"{cnt/tot*100:.0f}%" if tot > 0 else ""
            row.append(f"{cnt} ({pct})")
        row.append(total)
        rows.append(row)
    rows.append(["TOTAL"] + [model_total_defeats[m] for m in ALL_MODELS] + [sum(model_total_defeats.values())])
    print_table(headers, rows, col_widths=[16, 16, 16, 16, 16, 8])

    # Rounds survived
    print_subheader("Average Rounds Survived by Model")
    headers = ["Model", "Total Defeats", "Avg Rounds", "Min", "Max", "Median"]
    rows = []
    for m in ALL_MODELS:
        rs = model_rounds_survived[m]
        if rs:
            avg = sum(rs) / len(rs)
            median = sorted(rs)[len(rs) // 2]
            rows.append([m, len(rs), f"{avg:.1f}", min(rs), max(rs), median])
        else:
            rows.append([m, 0, "N/A", "N/A", "N/A", "N/A"])
    print_table(headers, rows)

    # Who kills the most enemies?
    print_subheader("Killer Distribution (who defeats enemies?)")
    all_killers = set()
    for c in model_killers.values():
        all_killers.update(c.keys())
    all_killers = sorted(all_killers)
    headers = ["Killer"] + ALL_MODELS + ["Total"]
    rows = []
    for k in all_killers:
        row = [k]
        total = 0
        for m in ALL_MODELS:
            cnt = model_killers[m][k]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    print_table(headers, rows, col_widths=[30, 12, 12, 16, 16, 8])

    # Per-run defeats
    print_subheader("Enemy Defeats Per Run")
    headers = ["Model", "Run", "Defeated", "Killed", "Fled/Other", "Avg Rounds"]
    rows = []
    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            defs = per_run_defeats.get((model, run), [])
            killed = sum(1 for d in defs if d["reason"] == "killed")
            other = len(defs) - killed
            avg_r = f"{sum(d['rounds_survived'] for d in defs)/len(defs):.1f}" if defs else "N/A"
            rows.append([model, run, len(defs), killed, other, avg_r])
    print_table(headers, rows, col_widths=[16, 12, 10, 10, 12, 12])


def analyze_enemy_factions_detail(data):
    """5. Enemy faction/name distribution."""
    print_header("5. ENEMY NAME & FACTION DETAIL")

    model_names = {m: Counter() for m in ALL_MODELS}
    for model in ALL_MODELS:
        for run, events in data[model].items():
            for e in events:
                if e.get("event_type") == "enemy_spawn":
                    name = e.get("enemy_name", "Unknown")
                    model_names[model][name] += 1

    # Show unique enemy names per model
    for m in ALL_MODELS:
        print(f"\n  {m} - unique enemy names ({len(model_names[m])}):")
        for name, cnt in model_names[m].most_common():
            print(f"    {name}: {cnt}")


# ============================================================
# NPC ANALYSIS
# ============================================================

def analyze_npc_declarations(data):
    """NPC action_declaration events."""
    print_header("6. NPC ACTION DECLARATIONS")

    model_actions = {m: Counter() for m in ALL_MODELS}
    model_total = {m: 0 for m in ALL_MODELS}
    model_npc_names = {m: set() for m in ALL_MODELS}
    npc_snippets = []
    per_run_npc = {}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            run_npc_actions = Counter()
            run_npc_names = set()
            for e in events:
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("npc_"):
                    action = e.get("action", {})
                    major = action.get("major_action", "unknown")
                    char_name = e.get("character_name", "Unknown NPC")
                    desc = action.get("description", "")

                    model_actions[model][major] += 1
                    model_total[model] += 1
                    model_npc_names[model].add(char_name)
                    run_npc_actions[major] += 1
                    run_npc_names.add(char_name)

                    # Collect interesting snippets
                    if desc and major not in ("hide", "flee"):
                        npc_snippets.append({
                            "model": model, "run": run, "npc": char_name,
                            "action": major, "snippet": desc[:150]
                        })
                    elif desc and len(npc_snippets) < 20:
                        npc_snippets.append({
                            "model": model, "run": run, "npc": char_name,
                            "action": major, "snippet": desc[:150]
                        })

            per_run_npc[(model, run)] = {"actions": run_npc_actions, "names": run_npc_names}

    # Action distribution
    all_actions = set()
    for c in model_actions.values():
        all_actions.update(c.keys())
    all_actions = sorted(all_actions)

    print_subheader("NPC Action Distribution by Model")
    headers = ["Action"] + ALL_MODELS + ["Total"]
    rows = []
    for action in all_actions:
        row = [action]
        total = 0
        for m in ALL_MODELS:
            cnt = model_actions[m][action]
            total += cnt
            tot = model_total[m]
            pct = f"{cnt/tot*100:.0f}%" if tot > 0 else ""
            row.append(f"{cnt} ({pct})")
        row.append(total)
        rows.append(row)
    rows.append(["TOTAL"] + [model_total[m] for m in ALL_MODELS] + [sum(model_total.values())])
    print_table(headers, rows, col_widths=[16, 16, 16, 16, 16, 8])

    # NPC diversity per model
    print_subheader("NPC Names/Types by Model")
    for m in ALL_MODELS:
        names = sorted(model_npc_names[m])
        print(f"\n  {m} ({len(names)} unique NPCs):")
        for n in names:
            print(f"    - {n}")

    # Per-run NPC summary
    print_subheader("NPC Activity Per Run")
    headers = ["Model", "Run", "NPC Actions", "Unique NPCs", "Top Actions"]
    rows = []
    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            info = per_run_npc.get((model, run), {"actions": Counter(), "names": set()})
            total = sum(info["actions"].values())
            top = ", ".join(f"{a}:{c}" for a, c in info["actions"].most_common(3))
            rows.append([model, run, total, len(info["names"]), top or "none"])
    print_table(headers, rows, col_widths=[16, 12, 14, 14, 45])

    return npc_snippets


def analyze_npc_resolutions(data):
    """NPC action_resolution events - damage, healing, status effects."""
    print_header("7. NPC ACTION RESOLUTIONS")

    model_npc_res = {m: Counter() for m in ALL_MODELS}
    model_npc_damage = {m: 0 for m in ALL_MODELS}
    model_npc_healing = {m: 0 for m in ALL_MODELS}
    model_npc_status = {m: [] for m in ALL_MODELS}
    notable_npc_res = []

    for model in ALL_MODELS:
        for run, events in data[model].items():
            for e in events:
                if e.get("event_type") == "action_resolution" and e.get("phase") == "adjudicate_npc":
                    action = e.get("action", "")
                    agent = e.get("agent", "")
                    model_npc_res[model][action] += 1

                    effects = e.get("effects", {})
                    if effects:
                        dmg = effects.get("damage")
                        if dmg and isinstance(dmg, dict):
                            dealt = dmg.get("dealt", 0) or dmg.get("total", 0) or 0
                            if dealt:
                                model_npc_damage[model] += dealt
                                notable_npc_res.append({
                                    "model": model, "run": run, "npc": agent,
                                    "action": action, "damage": dealt
                                })

                        healing = effects.get("healing")
                        if healing and isinstance(healing, dict):
                            healed = healing.get("amount", 0) or 0
                            if healed:
                                model_npc_healing[model] += healed
                                notable_npc_res.append({
                                    "model": model, "run": run, "npc": agent,
                                    "action": action, "healing": healed
                                })

                        status = effects.get("status_effects")
                        if status and isinstance(status, dict) and status:
                            model_npc_status[model].append({
                                "npc": agent, "effects": status, "run": run
                            })

    print_subheader("NPC Resolution Actions by Model (adjudicate_npc phase)")
    all_actions = set()
    for c in model_npc_res.values():
        all_actions.update(c.keys())
    all_actions = sorted(all_actions, key=str.lower)
    headers = ["Action"] + ALL_MODELS + ["Total"]
    rows = []
    for action in all_actions:
        row = [action[:30]]
        total = 0
        for m in ALL_MODELS:
            cnt = model_npc_res[m][action]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    totals = [sum(model_npc_res[m].values()) for m in ALL_MODELS]
    rows.append(["TOTAL"] + totals + [sum(totals)])
    print_table(headers, rows, col_widths=[32, 12, 12, 16, 16, 8])

    print_subheader("NPC Damage & Healing by Model")
    headers = ["Model", "Total Damage Dealt", "Total Healing", "Notable Events"]
    rows = []
    for m in ALL_MODELS:
        notables = [n for n in notable_npc_res if n["model"] == m]
        note_str = "; ".join(
            f"{n['npc']}({n.get('damage', n.get('healing', 0))})"
            for n in notables[:3]
        ) or "none"
        rows.append([m, model_npc_damage[m], model_npc_healing[m], note_str])
    print_table(headers, rows, col_widths=[16, 20, 16, 40])

    if model_npc_status:
        print_subheader("NPC Status Effects Applied")
        for m in ALL_MODELS:
            if model_npc_status[m]:
                for s in model_npc_status[m]:
                    print(f"  [{m}] {s['run']}: {s['npc']} -> {s['effects']}")
            else:
                print(f"  [{m}] No status effects from NPCs")


def analyze_entity_lifecycle(data):
    """Entity lifecycle events - conversions, departures."""
    print_header("8. ENTITY LIFECYCLE EVENTS")

    model_conversions = {m: 0 for m in ALL_MODELS}
    model_escalations = {m: 0 for m in ALL_MODELS}
    model_npc_spawns = {m: 0 for m in ALL_MODELS}
    model_enemy_spawns_lifecycle = {m: 0 for m in ALL_MODELS}
    model_departures = {m: 0 for m in ALL_MODELS}
    model_npc_departure_reasons = {m: Counter() for m in ALL_MODELS}
    conversion_details = []
    departure_details = []

    for model in ALL_MODELS:
        for run, events in data[model].items():
            for e in events:
                if e.get("event_type") == "entity_lifecycle":
                    d = e.get("data", {})
                    rnd = e.get("round", "?")

                    converted = d.get("enemies_converted", [])
                    escalated = d.get("npcs_escalated", [])
                    npc_spawned = d.get("npcs_spawned", [])
                    enemy_spawned = d.get("enemies_spawned", [])
                    npc_departed = d.get("npcs_departed", [])
                    enemies_departed = d.get("enemies_departed", [])

                    model_conversions[model] += len(converted)
                    model_escalations[model] += len(escalated)
                    model_npc_spawns[model] += len(npc_spawned)
                    model_enemy_spawns_lifecycle[model] += len(enemy_spawned)

                    if converted:
                        reasoning = ""
                        cd = d.get("conversion_decisions", {})
                        if cd:
                            reasoning = str(cd.get("reasoning", ""))[:200]
                        conversion_details.append({
                            "model": model, "run": run, "round": rnd,
                            "converted": converted, "reasoning": reasoning
                        })

                    if escalated:
                        conversion_details.append({
                            "model": model, "run": run, "round": rnd,
                            "escalated": escalated, "reasoning": ""
                        })

                elif e.get("event_type") == "npc_departure":
                    model_departures[model] += 1
                    reason = e.get("departure_reason", "unknown")
                    model_npc_departure_reasons[model][reason] += 1
                    departure_details.append({
                        "model": model, "run": run,
                        "npc_name": e.get("npc_name", "Unknown"),
                        "reason": reason,
                        "round": e.get("round", "?")
                    })

    print_subheader("Entity Lifecycle Summary by Model")
    headers = ["Model", "Enemy->NPC Conv.", "NPC->Enemy Esc.", "NPC Spawns (lifecycle)", "Enemy Spawns (lifecycle)", "NPC Departures"]
    rows = []
    for m in ALL_MODELS:
        rows.append([m, model_conversions[m], model_escalations[m],
                     model_npc_spawns[m], model_enemy_spawns_lifecycle[m], model_departures[m]])
    print_table(headers, rows, col_widths=[16, 18, 18, 24, 24, 16])

    # NPC departure reasons
    print_subheader("NPC Departure Reasons by Model")
    all_reasons = set()
    for c in model_npc_departure_reasons.values():
        all_reasons.update(c.keys())
    all_reasons = sorted(all_reasons)
    headers = ["Reason"] + ALL_MODELS + ["Total"]
    rows = []
    for reason in all_reasons:
        row = [reason]
        total = 0
        for m in ALL_MODELS:
            cnt = model_npc_departure_reasons[m][reason]
            total += cnt
            row.append(cnt)
        row.append(total)
        rows.append(row)
    print_table(headers, rows, col_widths=[30, 12, 12, 16, 16, 8])

    # Conversion details
    if conversion_details:
        print_subheader("Enemy-to-NPC Conversion Details")
        for cd in conversion_details:
            converted = cd.get("converted", [])
            escalated = cd.get("escalated", [])
            if converted:
                print(f"  [{cd['model']}] {cd['run']} round {cd['round']}: "
                      f"Converted {converted}")
                if cd["reasoning"]:
                    print(f"    Reasoning: {cd['reasoning']}")
            if escalated:
                print(f"  [{cd['model']}] {cd['run']} round {cd['round']}: "
                      f"ESCALATED {escalated}")

    # Departure details by run
    print_subheader("NPC Departures Per Run (selected)")
    headers = ["Model", "Run", "NPC Name", "Round", "Reason"]
    rows = []
    for dd in departure_details[:40]:
        rows.append([dd["model"], dd["run"], dd["npc_name"], dd["round"], dd["reason"]])
    if len(departure_details) > 40:
        rows.append(["...", "...", f"(+{len(departure_details)-40} more)", "...", "..."])
    print_table(headers, rows, col_widths=[16, 12, 35, 8, 30])


def analyze_outliers_and_snippets(data, npc_snippets):
    """Notable outlier sessions and NPC dialogue."""
    print_header("9. NOTABLE OUTLIERS & NPC SNIPPETS")

    # Session stats for outlier detection
    print_subheader("Session-Level Stats for Outlier Detection")
    headers = ["Model", "Run", "Total Enemies", "Total NPCs", "Conversions", "Rounds", "Enemy Acts", "NPC Acts"]
    rows = []

    for model in ALL_MODELS:
        for run in sorted(data[model].keys()):
            events = data[model][run]
            n_enemies = sum(1 for e in events if e.get("event_type") == "enemy_spawn")
            n_npcs = len(set(
                e.get("player_id") for e in events
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("npc_")
            ))
            n_conversions = sum(
                len(e.get("data", {}).get("enemies_converted", []))
                for e in events if e.get("event_type") == "entity_lifecycle"
            )
            max_round = max(
                (e.get("round", 0) or 0 for e in events if e.get("round") is not None),
                default=0
            )
            enemy_acts = sum(
                1 for e in events
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("enemy_")
            )
            npc_acts = sum(
                1 for e in events
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("npc_")
            )
            rows.append([model, run, n_enemies, n_npcs, n_conversions, max_round, enemy_acts, npc_acts])

    print_table(headers, rows, col_widths=[16, 12, 16, 12, 14, 8, 12, 10])

    # NPC snippets
    print_subheader("Selected NPC Action Descriptions (interesting behaviors)")

    # Prioritize non-hide/flee snippets
    interesting = [s for s in npc_snippets if s["action"] not in ("hide", "flee")]
    boring = [s for s in npc_snippets if s["action"] in ("hide", "flee")]

    shown = 0
    for s in interesting[:20]:
        print(f"\n  [{s['model']}] {s['run']} - {s['npc']} ({s['action']}):")
        print(f"    \"{s['snippet']}\"")
        shown += 1

    if shown < 15:
        for s in boring[:10]:
            print(f"\n  [{s['model']}] {s['run']} - {s['npc']} ({s['action']}):")
            print(f"    \"{s['snippet']}\"")
            shown += 1
            if shown >= 15:
                break


def analyze_enemy_combat_detail_by_weapon(data):
    """Bonus: Detailed weapon performance analysis."""
    print_header("10. WEAPON PERFORMANCE DETAIL (ENEMY ATTACKS)")

    weapon_stats = {}  # weapon -> {model -> {hits, misses, total_dmg, dmg_list}}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            for e in events:
                if e.get("event_type") != "combat_action":
                    continue
                attacker = e.get("attacker", {})
                if not attacker.get("id", "").startswith("enemy_"):
                    continue

                weapon = e.get("weapon", "Unknown")
                attack = e.get("attack") or {}
                damage = e.get("damage") or {}
                hit = attack.get("hit", False)
                dealt = damage.get("dealt", 0) or 0

                if weapon not in weapon_stats:
                    weapon_stats[weapon] = {m: {"hits": 0, "misses": 0, "total_dmg": 0, "dmg_list": []}
                                            for m in ALL_MODELS}

                if hit:
                    weapon_stats[weapon][model]["hits"] += 1
                    weapon_stats[weapon][model]["total_dmg"] += dealt
                    weapon_stats[weapon][model]["dmg_list"].append(dealt)
                else:
                    weapon_stats[weapon][model]["misses"] += 1

    for weapon in sorted(weapon_stats.keys()):
        print_subheader(f"Weapon: {weapon}")
        headers = ["Model", "Attacks", "Hits", "Hit Rate", "Avg Dmg/Hit", "Max Dmg", "Total Dmg"]
        rows = []
        for m in ALL_MODELS:
            s = weapon_stats[weapon][m]
            total = s["hits"] + s["misses"]
            if total == 0:
                continue
            hit_rate = f"{s['hits']/total*100:.0f}%" if total > 0 else "N/A"
            avg_dmg = f"{s['total_dmg']/s['hits']:.1f}" if s["hits"] > 0 else "N/A"
            max_dmg = max(s["dmg_list"]) if s["dmg_list"] else 0
            rows.append([m, total, s["hits"], hit_rate, avg_dmg, max_dmg, s["total_dmg"]])
        if rows:
            print_table(headers, rows, col_widths=[16, 10, 8, 10, 14, 10, 12])
        else:
            print("  No attacks with this weapon")


def analyze_target_id_resolution(data):
    """Bonus: Map tgt_xxx IDs to actual PC names via combat_action events."""
    print_header("11. TARGET ID RESOLUTION (tgt_xxx -> PC names)")

    # Collect target mappings from combat_action events
    model_target_map = {m: {} for m in ALL_MODELS}

    for model in ALL_MODELS:
        for run, events in data[model].items():
            # First pass: build target map from declarations + combat_actions
            # In action_declaration, enemies target tgt_xxx
            # In combat_action, we see the actual defender name
            enemy_targets = {}  # enemy_id -> tgt_xxx from declarations
            for e in events:
                if e.get("event_type") == "action_declaration" and e.get("player_id", "").startswith("enemy_"):
                    enemy_id = e.get("player_id")
                    target = e.get("action", {}).get("target", "") or ""
                    rnd = e.get("round")
                    if target.startswith("tgt_"):
                        enemy_targets[(enemy_id, rnd)] = target

            for e in events:
                if e.get("event_type") == "combat_action":
                    attacker = e.get("attacker", {})
                    if not attacker.get("id", "").startswith("enemy_"):
                        continue
                    defender = e.get("defender", {})
                    rnd = e.get("round")
                    att_id = attacker.get("id")
                    tgt = enemy_targets.get((att_id, rnd), "?")
                    if tgt.startswith("tgt_"):
                        def_name = defender.get("name", "?")
                        if tgt not in model_target_map[model]:
                            model_target_map[model][tgt] = set()
                        model_target_map[model][tgt].add(def_name)

    for m in ALL_MODELS:
        if model_target_map[m]:
            print(f"\n  {m}:")
            for tgt, names in sorted(model_target_map[m].items()):
                print(f"    {tgt} -> {', '.join(sorted(names))}")
        else:
            print(f"\n  {m}: No target ID mappings found")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Loading session data...")
    data = load_all_sessions()

    # Summary
    total_sessions = sum(len(runs) for runs in data.values())
    total_events = sum(len(events) for runs in data.values() for events in runs.values())
    print(f"Loaded {total_sessions} sessions, {total_events} total events")
    for model in ALL_MODELS:
        print(f"  {model}: {len(data[model])} sessions, "
              f"{sum(len(e) for e in data[model].values())} events")

    # ENEMY ANALYSIS
    analyze_enemy_declarations(data)
    analyze_combat_actions(data)
    analyze_enemy_spawning(data)
    analyze_enemy_defeats(data)
    analyze_enemy_factions_detail(data)

    # NPC ANALYSIS
    npc_snippets = analyze_npc_declarations(data)
    analyze_npc_resolutions(data)
    analyze_entity_lifecycle(data)

    # OUTLIERS & DETAIL
    analyze_outliers_and_snippets(data, npc_snippets)
    analyze_enemy_combat_detail_by_weapon(data)
    analyze_target_id_resolution(data)

    print()
    print("=" * 90)
    print("  ANALYSIS COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
