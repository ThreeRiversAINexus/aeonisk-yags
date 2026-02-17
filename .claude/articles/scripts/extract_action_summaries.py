#!/usr/bin/env python3
"""
Extract comprehensive action type summaries across all three experiment conditions.

Data locations:
- Control (baseline): /home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/
- Treatment v1: /home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/
- Treatment v2: /home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment/treatment_v2/
"""

import json
import os
import glob
from collections import defaultdict, Counter
from pathlib import Path


# ── Model name mapping ───────────────────────────────────────────────────────

def map_model_name(raw_model: str) -> str:
    """Map raw model identifiers to display names."""
    raw = raw_model.lower()
    if "deepseek" in raw:
        return "DeepSeek V3.2"
    if "gpt" in raw:
        return "GPT-5.2"
    if "gemini" in raw:
        return "Gemini 2.5 Pro"
    if "grok" in raw:
        return "Grok 4"
    if "claude" in raw:
        return "Claude Opus 4.6"
    return raw_model


# ── PC character names ────────────────────────────────────────────────────────

PC_NAMES = {"Enforcer Kael Dren", "Drifter Sable"}


# ── Data collection ──────────────────────────────────────────────────────────

def find_run_dirs(base_path: str) -> list[str]:
    """Find all run_XXXX subdirectories under a base path."""
    runs = []
    for entry in sorted(os.listdir(base_path)):
        if entry.startswith("run_") and os.path.isdir(os.path.join(base_path, entry)):
            runs.append(os.path.join(base_path, entry))
    return runs


def get_model_from_config(run_dir: str) -> str | None:
    """Extract model name from config.json in a run directory."""
    cfg_path = os.path.join(run_dir, "config.json")
    if not os.path.exists(cfg_path):
        return None
    with open(cfg_path) as f:
        cfg = json.load(f)
    return cfg.get("agents", {}).get("dm", {}).get("llm", {}).get("model")


def get_jsonl_file(run_dir: str) -> str | None:
    """Find the JSONL session file in a run directory."""
    files = glob.glob(os.path.join(run_dir, "*.jsonl"))
    if not files:
        return None
    return files[0]


def analyze_session(jsonl_path: str) -> dict:
    """Analyze a single session JSONL file and return stats."""
    result = {
        "pc_actions": Counter(),       # action_type -> count
        "pc_action_total": 0,
        "enemy_combat_actions": 0,     # combat_action events + enemy_execution resolutions
        "npc_actions": 0,              # adjudicate_npc phase resolutions
        "max_round": 0,
    }

    # Track to avoid double-counting: combat_action events already logged as
    # enemy_execution action_resolutions share parent_event_id linkage.
    # We count combat_action events (mechanical) as the primary source for enemies,
    # and adjudicate_npc action_resolutions for NPCs.

    seen_enemy_combat_action_events = set()

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = e.get("event_type")
            r = e.get("round")
            if r is not None and isinstance(r, (int, float)) and r > result["max_round"]:
                result["max_round"] = int(r)

            # ── PC Actions: action_declaration events for PCs ──
            if event_type == "action_declaration":
                char_name = e.get("character_name", "")
                if char_name in PC_NAMES:
                    action_type = e.get("action", {}).get("action_type", "unknown") or "unknown"
                    result["pc_actions"][action_type] += 1
                    result["pc_action_total"] += 1

            # ── Enemy Actions: combat_action events ──
            elif event_type == "combat_action":
                result["enemy_combat_actions"] += 1
                seen_enemy_combat_action_events.add(e.get("event_id"))

            # ── Enemy Actions: action_resolution with enemy_execution phase ──
            # Only count if no corresponding combat_action was logged
            # (combat_action is the parent of enemy_execution resolution)
            elif event_type == "action_resolution":
                phase = e.get("phase", "")
                if phase == "enemy_execution":
                    parent_id = e.get("parent_event_id")
                    if parent_id not in seen_enemy_combat_action_events:
                        result["enemy_combat_actions"] += 1

                # ── NPC Actions ──
                elif phase == "adjudicate_npc" or (phase and "npc" in phase.lower()):
                    result["npc_actions"] += 1

    return result


# ── Data source definitions ──────────────────────────────────────────────────

def collect_all_sessions() -> dict:
    """
    Collect all sessions organized by condition and model.

    Returns:
        {condition: {display_model: [session_stats, ...]}}
    """
    data = defaultdict(lambda: defaultdict(list))

    # ── Control ──────────────────────────────────────────────────────────
    control_base = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/"
    for batch_dir in sorted(os.listdir(control_base)):
        if not batch_dir.startswith("run_"):
            continue
        batch_path = os.path.join(control_base, batch_dir)
        if not os.path.isdir(batch_path):
            continue
        for run_dir in find_run_dirs(batch_path):
            model = get_model_from_config(run_dir)
            jsonl = get_jsonl_file(run_dir)
            if model and jsonl:
                stats = analyze_session(jsonl)
                data["Control"][map_model_name(model)].append(stats)

    # ── Treatment v1 ─────────────────────────────────────────────────────
    v1_base = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/"
    for batch_dir in sorted(os.listdir(v1_base)):
        if not batch_dir.startswith("run_"):
            continue
        batch_path = os.path.join(v1_base, batch_dir)
        if not os.path.isdir(batch_path):
            continue
        for run_dir in find_run_dirs(batch_path):
            model = get_model_from_config(run_dir)
            jsonl = get_jsonl_file(run_dir)
            if model and jsonl:
                stats = analyze_session(jsonl)
                data["Treatment v1"][map_model_name(model)].append(stats)

    # ── Treatment v2 (main run) ──────────────────────────────────────────
    v2_main = "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment/treatment_v2/run_2026-02-16_172446_72c3a9ef"
    for run_dir in find_run_dirs(v2_main):
        model = get_model_from_config(run_dir)
        jsonl = get_jsonl_file(run_dir)
        if model and jsonl:
            stats = analyze_session(jsonl)
            data["Treatment v2"][map_model_name(model)].append(stats)

    # ── Treatment v2 DeepSeek retry ──────────────────────────────────────
    v2_retry = "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment/treatment_v2/run_2026-02-16_200845_9b430506"
    if os.path.isdir(v2_retry):
        for run_dir in find_run_dirs(v2_retry):
            model = get_model_from_config(run_dir)
            jsonl = get_jsonl_file(run_dir)
            if model and jsonl:
                stats = analyze_session(jsonl)
                data["Treatment v2"][map_model_name(model)].append(stats)

    return data


# ── Reporting ────────────────────────────────────────────────────────────────

def fmt_avg(total: float, count: int) -> str:
    """Format an average value."""
    if count == 0:
        return "0.0"
    return f"{total / count:.1f}"


def print_condition_table(condition: str, model_data: dict):
    """Print a comprehensive table for one condition."""
    print(f"\n{'='*100}")
    print(f"  {condition.upper()}")
    print(f"{'='*100}")

    # Collect all action types across all models
    all_action_types = set()
    for model, sessions in model_data.items():
        for s in sessions:
            all_action_types.update(s["pc_actions"].keys())
    action_types_sorted = sorted(all_action_types)

    # ── Session Info Table ───────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  SESSION INFO")
    print(f"{'─'*80}")
    print(f"  {'Model':<22s} {'Sessions':>10s} {'Total Rnds':>12s} {'Avg Rnds/Sess':>15s}")
    print(f"  {'─'*22} {'─'*10} {'─'*12} {'─'*15}")

    total_sessions = 0
    total_rounds = 0
    for model in sorted(model_data.keys()):
        sessions = model_data[model]
        n = len(sessions)
        rounds = sum(s["max_round"] for s in sessions)
        total_sessions += n
        total_rounds += rounds
        print(f"  {model:<22s} {n:>10d} {rounds:>12d} {fmt_avg(rounds, n):>15s}")
    print(f"  {'─'*22} {'─'*10} {'─'*12} {'─'*15}")
    print(f"  {'TOTAL':<22s} {total_sessions:>10d} {total_rounds:>12d} {fmt_avg(total_rounds, total_sessions):>15s}")

    # ── PC Action Summary Table ──────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  PC ACTIONS (Enforcer Kael Dren + Drifter Sable)")
    print(f"{'─'*80}")

    # Header
    header = f"  {'Model':<22s} {'Total':>7s} {'Avg/Sess':>10s}"
    for at in action_types_sorted:
        header += f" {at:>12s}"
    print(header)
    divider = f"  {'─'*22} {'─'*7} {'─'*10}"
    for at in action_types_sorted:
        divider += f" {'─'*12}"
    print(divider)

    grand_total_pc = 0
    grand_action_counts = Counter()
    grand_sessions = 0
    for model in sorted(model_data.keys()):
        sessions = model_data[model]
        n = len(sessions)
        grand_sessions += n
        total_pc = sum(s["pc_action_total"] for s in sessions)
        grand_total_pc += total_pc
        row = f"  {model:<22s} {total_pc:>7d} {fmt_avg(total_pc, n):>10s}"
        for at in action_types_sorted:
            count = sum(s["pc_actions"].get(at, 0) for s in sessions)
            grand_action_counts[at] += count
            row += f" {count:>12d}"
        print(row)

    # Totals row
    print(divider)
    row = f"  {'TOTAL':<22s} {grand_total_pc:>7d} {fmt_avg(grand_total_pc, grand_sessions):>10s}"
    for at in action_types_sorted:
        row += f" {grand_action_counts[at]:>12d}"
    print(row)

    # ── PC Action Percentages ────────────────────────────────────────────
    print(f"\n  PC Action Type Distribution (%):")
    header2 = f"  {'Model':<22s}"
    for at in action_types_sorted:
        header2 += f" {at:>12s}"
    print(header2)
    print(divider)

    for model in sorted(model_data.keys()):
        sessions = model_data[model]
        total_pc = sum(s["pc_action_total"] for s in sessions)
        row = f"  {model:<22s}"
        for at in action_types_sorted:
            count = sum(s["pc_actions"].get(at, 0) for s in sessions)
            pct = (count / total_pc * 100) if total_pc > 0 else 0
            row += f" {pct:>11.1f}%"
        print(row)

    print(divider)
    row = f"  {'TOTAL':<22s}"
    for at in action_types_sorted:
        pct = (grand_action_counts[at] / grand_total_pc * 100) if grand_total_pc > 0 else 0
        row += f" {pct:>11.1f}%"
    print(row)

    # ── Enemy Actions Table ──────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  ENEMY COMBAT ACTIONS")
    print(f"{'─'*80}")
    print(f"  {'Model':<22s} {'Total':>10s} {'Avg/Sess':>10s}")
    print(f"  {'─'*22} {'─'*10} {'─'*10}")

    grand_enemy = 0
    for model in sorted(model_data.keys()):
        sessions = model_data[model]
        n = len(sessions)
        total_enemy = sum(s["enemy_combat_actions"] for s in sessions)
        grand_enemy += total_enemy
        print(f"  {model:<22s} {total_enemy:>10d} {fmt_avg(total_enemy, n):>10s}")
    print(f"  {'─'*22} {'─'*10} {'─'*10}")
    print(f"  {'TOTAL':<22s} {grand_enemy:>10d} {fmt_avg(grand_enemy, grand_sessions):>10s}")

    # ── NPC Actions Table ────────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  NPC ACTIONS")
    print(f"{'─'*80}")
    print(f"  {'Model':<22s} {'Total':>10s} {'Avg/Sess':>10s}")
    print(f"  {'─'*22} {'─'*10} {'─'*10}")

    grand_npc = 0
    for model in sorted(model_data.keys()):
        sessions = model_data[model]
        n = len(sessions)
        total_npc = sum(s["npc_actions"] for s in sessions)
        grand_npc += total_npc
        print(f"  {model:<22s} {total_npc:>10d} {fmt_avg(total_npc, n):>10s}")
    print(f"  {'─'*22} {'─'*10} {'─'*10}")
    print(f"  {'TOTAL':<22s} {grand_npc:>10d} {fmt_avg(grand_npc, grand_sessions):>10s}")


def print_cross_condition_summary(all_data: dict):
    """Print cross-condition comparison."""
    print(f"\n\n{'='*100}")
    print(f"  CROSS-CONDITION COMPARISON")
    print(f"{'='*100}")

    # Collect all action types
    all_action_types = set()
    for cond, model_data in all_data.items():
        for model, sessions in model_data.items():
            for s in sessions:
                all_action_types.update(s["pc_actions"].keys())
    action_types_sorted = sorted(all_action_types)

    # ── Per-model cross-condition ────────────────────────────────────────
    all_models = set()
    for cond, model_data in all_data.items():
        all_models.update(model_data.keys())

    conditions_ordered = ["Control", "Treatment v1", "Treatment v2"]
    conditions_present = [c for c in conditions_ordered if c in all_data]

    for model in sorted(all_models):
        print(f"\n{'─'*90}")
        print(f"  {model}")
        print(f"{'─'*90}")

        header = f"  {'Condition':<18s} {'Sess':>5s} {'Rnds':>5s} {'PC Acts':>8s} {'Avg/S':>6s} {'Enemy':>7s} {'NPC':>5s}"
        for at in action_types_sorted:
            header += f" {at[:8]:>8s}"
        print(header)
        divider = f"  {'─'*18} {'─'*5} {'─'*5} {'─'*8} {'─'*6} {'─'*7} {'─'*5}"
        for at in action_types_sorted:
            divider += f" {'─'*8}"
        print(divider)

        for cond in conditions_present:
            model_data = all_data[cond]
            if model not in model_data:
                continue
            sessions = model_data[model]
            n = len(sessions)
            rounds = sum(s["max_round"] for s in sessions)
            total_pc = sum(s["pc_action_total"] for s in sessions)
            total_enemy = sum(s["enemy_combat_actions"] for s in sessions)
            total_npc = sum(s["npc_actions"] for s in sessions)

            row = f"  {cond:<18s} {n:>5d} {rounds:>5d} {total_pc:>8d} {fmt_avg(total_pc, n):>6s} {total_enemy:>7d} {total_npc:>5d}"
            for at in action_types_sorted:
                count = sum(s["pc_actions"].get(at, 0) for s in sessions)
                row += f" {count:>8d}"
            print(row)

    # ── Aggregate cross-condition ────────────────────────────────────────
    print(f"\n{'─'*90}")
    print(f"  AGGREGATE (all models)")
    print(f"{'─'*90}")

    header = f"  {'Condition':<18s} {'Sess':>5s} {'Rnds':>5s} {'PC Acts':>8s} {'Avg/S':>6s} {'Enemy':>7s} {'E/S':>5s} {'NPC':>5s} {'N/S':>5s}"
    for at in action_types_sorted:
        header += f" {at[:8]:>8s}"
    header += "  " + "  ".join(f"{at[:8]:>8s}%" for at in action_types_sorted)
    print(header)

    divider = f"  {'─'*18} {'─'*5} {'─'*5} {'─'*8} {'─'*6} {'─'*7} {'─'*5} {'─'*5} {'─'*5}"
    for at in action_types_sorted:
        divider += f" {'─'*8}"
    divider += "  " + "  ".join(f"{'─'*8}" for _ in action_types_sorted)
    print(divider)

    for cond in conditions_present:
        model_data = all_data[cond]
        n = sum(len(sessions) for sessions in model_data.values())
        rounds = sum(s["max_round"] for sessions in model_data.values() for s in sessions)
        total_pc = sum(s["pc_action_total"] for sessions in model_data.values() for s in sessions)
        total_enemy = sum(s["enemy_combat_actions"] for sessions in model_data.values() for s in sessions)
        total_npc = sum(s["npc_actions"] for sessions in model_data.values() for s in sessions)

        row = f"  {cond:<18s} {n:>5d} {rounds:>5d} {total_pc:>8d} {fmt_avg(total_pc, n):>6s} {total_enemy:>7d} {fmt_avg(total_enemy, n):>5s} {total_npc:>5d} {fmt_avg(total_npc, n):>5s}"
        for at in action_types_sorted:
            count = sum(s["pc_actions"].get(at, 0) for sessions in model_data.values() for s in sessions)
            row += f" {count:>8d}"
        # Percentages
        for at in action_types_sorted:
            count = sum(s["pc_actions"].get(at, 0) for sessions in model_data.values() for s in sessions)
            pct = (count / total_pc * 100) if total_pc > 0 else 0
            row += f"  {pct:>7.1f}%"
        print(row)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Extracting action summaries across experiment conditions...")
    print("=" * 100)

    all_data = collect_all_sessions()

    # Print session counts for verification
    print("\nData loaded:")
    conditions_ordered = ["Control", "Treatment v1", "Treatment v2"]
    for cond in conditions_ordered:
        if cond in all_data:
            model_data = all_data[cond]
            total = sum(len(s) for s in model_data.values())
            models_str = ", ".join(f"{m}: {len(s)}" for m, s in sorted(model_data.items()))
            print(f"  {cond}: {total} sessions ({models_str})")

    # Print per-condition tables
    for cond in conditions_ordered:
        if cond in all_data:
            print_condition_table(cond, all_data[cond])

    # Print cross-condition summary
    print_cross_condition_summary(all_data)


if __name__ == "__main__":
    main()
