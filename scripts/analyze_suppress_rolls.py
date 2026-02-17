#!/usr/bin/env python3
"""
Analyze suppressive fire roll outcomes across all three experiment conditions.

Finds:
1. All suppressive fire declarations (PC only)
2. Matching action_resolution roll data
3. Comparison with lethal combat actions
4. Shock baton actions (separate category)
"""

import json
import glob
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# === Configuration ===

CONDITION_DIRS = {
    "control": [
        "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/run_2026-02-14_113048_5276cf26",
        "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/run_2026-02-14_171956_2540eedd",
    ],
    "treatment_v1": [
        "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/run_2026-02-15_080601_11e9b721",
        "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/run_2026-02-15_092951_17617f09",
    ],
    "treatment_v2": [
        "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment/treatment_v2/run_2026-02-16_172446_72c3a9ef",
        "/home/p/Coding/aeonisk-yags/multiagent_output/lethality_experiment/treatment_v2/run_2026-02-16_200845_9b430506",
    ],
}

SUPPRESS_KEYWORDS = [
    'suppressive fire', 'suppressing fire', 'suppress', 'suppressing',
    'pin them down', 'covering fire', 'warning shot', 'pinning fire',
    'area denial', 'keep their heads down', 'non-lethal',
]

# Exclusion patterns (not suppress)
SUPPRESS_EXCLUSIONS = ['not a warning', 'without warning']

BATON_KEYWORDS = ['shock baton', 'stun baton', 'baton']


@dataclass
class ActionRecord:
    condition: str
    model: str
    session_file: str
    character_name: str
    agent_id: str
    round_num: int
    category: str  # 'suppress', 'lethal', 'baton'
    # Declaration fields
    intent: str = ""
    description: str = ""
    difficulty_estimate: Optional[float] = None
    difficulty_justification: str = ""
    action_type: str = ""
    # Resolution fields
    dm_dc: Optional[float] = None
    roll_total: Optional[float] = None
    margin: Optional[float] = None
    success: Optional[bool] = None
    d20: Optional[int] = None
    tier: str = ""
    attr: str = ""
    skill: str = ""
    matched_keyword: str = ""


def get_model_from_config(run_dir):
    """Extract model name from config.json in run directory."""
    config_path = os.path.join(run_dir, 'config.json')
    if os.path.exists(config_path):
        with open(config_path) as f:
            d = json.load(f)
        return d.get('agents', {}).get('dm', {}).get('llm', {}).get('model', 'unknown')
    return 'unknown'


def shorten_model(model):
    """Shorten model name for display."""
    mappings = {
        'gpt-5.2-2025-12-11': 'GPT-5.2',
        'grok-4-latest': 'Grok-4',
        'gemini-2.5-pro': 'Gemini-2.5',
        'claude-opus-4-6': 'Claude-Opus',
        'deepseek-ai/DeepSeek-V3.2': 'DeepSeek-V3.2',
    }
    return mappings.get(model, model)


def is_suppress_action(text):
    """Check if text contains suppress keywords but not exclusions."""
    text_lower = text.lower()
    # Check exclusions first
    for excl in SUPPRESS_EXCLUSIONS:
        if excl in text_lower:
            return False, ""
    # Check keywords
    for kw in SUPPRESS_KEYWORDS:
        if kw in text_lower:
            return True, kw
    return False, ""


def is_baton_action(text):
    """Check if text mentions shock baton."""
    text_lower = text.lower()
    for kw in BATON_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def process_session(jsonl_path, condition, model):
    """Process a single JSONL session file."""
    records = []

    # First pass: collect all events
    declarations = {}  # key: (character_name, round) -> action_declaration event
    resolutions = {}   # key: (character_name_or_agent, round) -> action_resolution event

    events = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Collect PC declarations
    for e in events:
        if e.get('event_type') != 'action_declaration':
            continue
        pid = e.get('player_id', '') or ''
        if not str(pid).startswith('player_'):
            continue
        action = e.get('action', {}) or {}
        char_name = e.get('character_name', '') or action.get('character_name', '')
        rnd = e.get('round')
        if rnd is not None and char_name:
            declarations[(char_name, rnd)] = e

    # Collect PC resolutions (adjudicate phase, not enemy, not NPC)
    for e in events:
        if e.get('event_type') != 'action_resolution':
            continue
        ctx = e.get('context', {}) or {}
        if ctx.get('is_enemy') or ctx.get('is_npc'):
            continue
        phase = e.get('phase', '')
        if phase != 'adjudicate':
            continue
        agent_name = e.get('agent', '')
        rnd = e.get('round')
        if rnd is not None and agent_name:
            resolutions[(agent_name, rnd)] = e

    # Match declarations to resolutions and categorize
    for (char_name, rnd), decl_event in declarations.items():
        action = decl_event.get('action', {}) or {}
        intent = str(action.get('intent', '') or '')
        desc = str(action.get('description', '') or '')
        combined_text = desc + ' ' + intent
        action_type = str(action.get('action_type', '') or '')
        agent_id = str(decl_event.get('player_id', '') or '')

        # Categorize - check baton FIRST (baton is separate from both suppress and lethal)
        is_bat = is_baton_action(combined_text)
        is_suppress, matched_kw = is_suppress_action(combined_text)

        if is_bat and not is_suppress:
            category = 'baton'
        elif is_suppress and not is_bat:
            category = 'suppress'
        elif is_suppress and is_bat:
            # Both keywords present - classify as baton (stun weapon takes priority)
            category = 'baton'
            matched_kw = ""
        elif action_type == 'combat':
            category = 'lethal'
        else:
            continue  # Not combat-related

        # Build record
        rec = ActionRecord(
            condition=condition,
            model=shorten_model(model),
            session_file=os.path.basename(jsonl_path),
            character_name=char_name,
            agent_id=agent_id,
            round_num=rnd,
            category=category,
            intent=intent,
            description=desc,
            difficulty_estimate=action.get('difficulty_estimate'),
            difficulty_justification=str(action.get('difficulty_justification', '') or ''),
            action_type=action_type,
            matched_keyword=matched_kw,
        )

        # Try to find matching resolution
        res = resolutions.get((char_name, rnd))
        if res:
            roll = res.get('roll', {}) or {}
            rec.dm_dc = roll.get('dc')
            rec.roll_total = roll.get('total')
            rec.margin = roll.get('margin')
            rec.success = roll.get('success')
            rec.d20 = roll.get('d20')
            rec.tier = str(roll.get('tier', '') or '')
            rec.attr = str(roll.get('attr', '') or '')
            rec.skill = str(roll.get('skill', '') or '')

        records.append(rec)

    return records


def print_table(headers, rows, col_widths=None):
    """Print a formatted table."""
    if not col_widths:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, len(str(row[i])))
            col_widths.append(min(max_w + 2, 30))

    # Header
    header_line = ""
    for i, h in enumerate(headers):
        header_line += str(h).ljust(col_widths[i])
    print(header_line)
    print("-" * sum(col_widths))

    # Rows
    for row in rows:
        line = ""
        for i, val in enumerate(row):
            if i < len(col_widths):
                line += str(val).ljust(col_widths[i])
        print(line)


def main():
    all_records = []

    for condition, run_dirs_list in CONDITION_DIRS.items():
        for run_batch_dir in run_dirs_list:
            if not os.path.exists(run_batch_dir):
                print(f"WARNING: Directory not found: {run_batch_dir}")
                continue
            # Find all run_XXXX subdirectories
            run_subdirs = sorted(glob.glob(os.path.join(run_batch_dir, 'run_*')))
            for run_dir in run_subdirs:
                if not os.path.isdir(run_dir):
                    continue
                model = get_model_from_config(run_dir)
                # Find JSONL files
                jsonl_files = glob.glob(os.path.join(run_dir, '*.jsonl'))
                for jf in jsonl_files:
                    records = process_session(jf, condition, model)
                    all_records.extend(records)

    # Separate by category
    suppress_recs = [r for r in all_records if r.category == 'suppress']
    lethal_recs = [r for r in all_records if r.category == 'lethal']
    baton_recs = [r for r in all_records if r.category == 'baton']

    print("=" * 100)
    print("SUPPRESSIVE FIRE ROLL ANALYSIS")
    print("=" * 100)
    print()
    print(f"Total records found: {len(all_records)} combat actions")
    print(f"  Suppress: {len(suppress_recs)}")
    print(f"  Lethal:   {len(lethal_recs)}")
    print(f"  Baton:    {len(baton_recs)}")
    print()

    # ============================================================
    # TABLE 1: Suppress rolls by condition x model
    # ============================================================
    print("=" * 100)
    print("TABLE 1: SUPPRESS ROLL OUTCOMES BY CONDITION x MODEL")
    print("=" * 100)
    print()

    # Group by (condition, model)
    suppress_groups = defaultdict(list)
    for r in suppress_recs:
        suppress_groups[(r.condition, r.model)].append(r)

    headers = ["Condition", "Model", "N", "N_failed", "Min_margin", "Max_margin", "Avg_margin", "Avg_DC", "Avg_total"]
    rows = []
    for (cond, model), recs in sorted(suppress_groups.items()):
        margins = [r.margin for r in recs if r.margin is not None]
        dcs = [r.dm_dc for r in recs if r.dm_dc is not None]
        totals = [r.roll_total for r in recs if r.roll_total is not None]
        n_failed = sum(1 for m in margins if m < 0)
        rows.append([
            cond, model, len(recs), n_failed,
            f"{min(margins):.0f}" if margins else "N/A",
            f"{max(margins):.0f}" if margins else "N/A",
            f"{sum(margins)/len(margins):.1f}" if margins else "N/A",
            f"{sum(dcs)/len(dcs):.1f}" if dcs else "N/A",
            f"{sum(totals)/len(totals):.1f}" if totals else "N/A",
        ])

    # Add totals row
    all_margins = [r.margin for r in suppress_recs if r.margin is not None]
    all_dcs = [r.dm_dc for r in suppress_recs if r.dm_dc is not None]
    all_totals = [r.roll_total for r in suppress_recs if r.roll_total is not None]
    if all_margins:
        rows.append([
            "ALL", "ALL", len(suppress_recs), sum(1 for m in all_margins if m < 0),
            f"{min(all_margins):.0f}", f"{max(all_margins):.0f}",
            f"{sum(all_margins)/len(all_margins):.1f}",
            f"{sum(all_dcs)/len(all_dcs):.1f}" if all_dcs else "N/A",
            f"{sum(all_totals)/len(all_totals):.1f}" if all_totals else "N/A",
        ])

    print_table(headers, rows)
    print()

    # ============================================================
    # TABLE 2: PC difficulty_estimate vs DM DC for suppress actions
    # ============================================================
    print("=" * 100)
    print("TABLE 2: PC DIFFICULTY ESTIMATE vs DM DC - SUPPRESS ACTIONS")
    print("=" * 100)
    print()

    headers2 = ["Condition", "Model", "N", "Avg_PC_est", "Avg_DM_DC", "Avg_diff(PC-DM)", "Min_PC", "Max_PC", "Min_DM", "Max_DM"]
    rows2 = []
    for (cond, model), recs in sorted(suppress_groups.items()):
        pc_ests = [r.difficulty_estimate for r in recs if r.difficulty_estimate is not None]
        dm_dcs = [r.dm_dc for r in recs if r.dm_dc is not None]
        # Paired comparisons
        paired = [(r.difficulty_estimate, r.dm_dc) for r in recs
                  if r.difficulty_estimate is not None and r.dm_dc is not None]
        diffs = [p[0] - p[1] for p in paired]

        rows2.append([
            cond, model, len(recs),
            f"{sum(pc_ests)/len(pc_ests):.1f}" if pc_ests else "N/A",
            f"{sum(dm_dcs)/len(dm_dcs):.1f}" if dm_dcs else "N/A",
            f"{sum(diffs)/len(diffs):.1f}" if diffs else "N/A",
            f"{min(pc_ests):.0f}" if pc_ests else "N/A",
            f"{max(pc_ests):.0f}" if pc_ests else "N/A",
            f"{min(dm_dcs):.0f}" if dm_dcs else "N/A",
            f"{max(dm_dcs):.0f}" if dm_dcs else "N/A",
        ])

    # Totals
    all_pc = [r.difficulty_estimate for r in suppress_recs if r.difficulty_estimate is not None]
    all_dm = [r.dm_dc for r in suppress_recs if r.dm_dc is not None]
    all_paired = [(r.difficulty_estimate, r.dm_dc) for r in suppress_recs
                  if r.difficulty_estimate is not None and r.dm_dc is not None]
    all_diffs = [p[0] - p[1] for p in all_paired]
    if all_pc:
        rows2.append([
            "ALL", "ALL", len(suppress_recs),
            f"{sum(all_pc)/len(all_pc):.1f}", f"{sum(all_dm)/len(all_dm):.1f}" if all_dm else "N/A",
            f"{sum(all_diffs)/len(all_diffs):.1f}" if all_diffs else "N/A",
            f"{min(all_pc):.0f}", f"{max(all_pc):.0f}",
            f"{min(all_dm):.0f}" if all_dm else "N/A", f"{max(all_dm):.0f}" if all_dm else "N/A",
        ])

    print_table(headers2, rows2)
    print()

    # ============================================================
    # TABLE 3: Same for LETHAL combat actions (comparison)
    # ============================================================
    print("=" * 100)
    print("TABLE 3: LETHAL COMBAT ROLL OUTCOMES BY CONDITION x MODEL (comparison)")
    print("=" * 100)
    print()

    lethal_groups = defaultdict(list)
    for r in lethal_recs:
        lethal_groups[(r.condition, r.model)].append(r)

    headers3 = ["Condition", "Model", "N", "N_failed", "Min_margin", "Max_margin", "Avg_margin", "Avg_PC_est", "Avg_DM_DC"]
    rows3 = []
    for (cond, model), recs in sorted(lethal_groups.items()):
        margins = [r.margin for r in recs if r.margin is not None]
        pc_ests = [r.difficulty_estimate for r in recs if r.difficulty_estimate is not None]
        dm_dcs = [r.dm_dc for r in recs if r.dm_dc is not None]
        n_failed = sum(1 for m in margins if m < 0)
        rows3.append([
            cond, model, len(recs), n_failed,
            f"{min(margins):.0f}" if margins else "N/A",
            f"{max(margins):.0f}" if margins else "N/A",
            f"{sum(margins)/len(margins):.1f}" if margins else "N/A",
            f"{sum(pc_ests)/len(pc_ests):.1f}" if pc_ests else "N/A",
            f"{sum(dm_dcs)/len(dm_dcs):.1f}" if dm_dcs else "N/A",
        ])

    # Totals
    lm = [r.margin for r in lethal_recs if r.margin is not None]
    lp = [r.difficulty_estimate for r in lethal_recs if r.difficulty_estimate is not None]
    ld = [r.dm_dc for r in lethal_recs if r.dm_dc is not None]
    if lm:
        rows3.append([
            "ALL", "ALL", len(lethal_recs), sum(1 for m in lm if m < 0),
            f"{min(lm):.0f}", f"{max(lm):.0f}", f"{sum(lm)/len(lm):.1f}",
            f"{sum(lp)/len(lp):.1f}" if lp else "N/A",
            f"{sum(ld)/len(ld):.1f}" if ld else "N/A",
        ])

    print_table(headers3, rows3)
    print()

    # ============================================================
    # TABLE 4: FAILED suppress rolls detail
    # ============================================================
    print("=" * 100)
    print("TABLE 4: INDIVIDUAL FAILED SUPPRESS ROLLS (margin < 0)")
    print("=" * 100)
    print()

    failed = [r for r in suppress_recs if r.margin is not None and r.margin < 0]
    if failed:
        headers4 = ["Condition", "Model", "Character", "Round", "Margin", "DM_DC", "Total", "d20", "Tier", "Keyword"]
        rows4 = []
        for r in failed:
            rows4.append([
                r.condition, r.model, r.character_name, r.round_num,
                f"{r.margin:.0f}", f"{r.dm_dc}" if r.dm_dc else "N/A",
                f"{r.roll_total}" if r.roll_total else "N/A",
                r.d20, r.tier, r.matched_keyword,
            ])
        print_table(headers4, rows4)
        print()
        # Print details
        for r in failed:
            print(f"  Detail: {r.character_name} R{r.round_num} [{r.condition}/{r.model}]")
            print(f"    Intent: {r.intent[:200]}")
            print(f"    PC est: {r.difficulty_estimate}, DM DC: {r.dm_dc}, Roll: {r.roll_total}, Margin: {r.margin}")
            print(f"    File: {r.session_file}")
            print()
    else:
        print("  *** NO FAILED SUPPRESS ROLLS FOUND ***")
        print()

    # ============================================================
    # TABLE 5: Margin distribution buckets
    # ============================================================
    print("=" * 100)
    print("TABLE 5: MARGIN DISTRIBUTION - SUPPRESS vs LETHAL")
    print("=" * 100)
    print()

    buckets = [("<0", lambda m: m < 0),
               ("0-5", lambda m: 0 <= m <= 5),
               ("6-10", lambda m: 6 <= m <= 10),
               ("11-15", lambda m: 11 <= m <= 15),
               ("16-20", lambda m: 16 <= m <= 20),
               ("21+", lambda m: m >= 21)]

    suppress_margins = [r.margin for r in suppress_recs if r.margin is not None]
    lethal_margins = [r.margin for r in lethal_recs if r.margin is not None]

    headers5 = ["Bucket", "Suppress_N", "Suppress_%", "Lethal_N", "Lethal_%"]
    rows5 = []
    for label, pred in buckets:
        s_count = sum(1 for m in suppress_margins if pred(m))
        l_count = sum(1 for m in lethal_margins if pred(m))
        s_pct = f"{100*s_count/len(suppress_margins):.1f}" if suppress_margins else "0"
        l_pct = f"{100*l_count/len(lethal_margins):.1f}" if lethal_margins else "0"
        rows5.append([label, s_count, s_pct, l_count, l_pct])

    print_table(headers5, rows5)
    print()

    # ============================================================
    # TABLE 6: Baton actions
    # ============================================================
    print("=" * 100)
    print("TABLE 6: SHOCK BATON ACTIONS (excluded from suppress)")
    print("=" * 100)
    print()

    if baton_recs:
        baton_groups = defaultdict(list)
        for r in baton_recs:
            baton_groups[(r.condition, r.model)].append(r)

        headers6 = ["Condition", "Model", "N", "N_failed", "Avg_margin", "Avg_DC"]
        rows6 = []
        for (cond, model), recs in sorted(baton_groups.items()):
            margins = [r.margin for r in recs if r.margin is not None]
            dcs = [r.dm_dc for r in recs if r.dm_dc is not None]
            n_failed = sum(1 for m in margins if m < 0)
            rows6.append([
                cond, model, len(recs), n_failed,
                f"{sum(margins)/len(margins):.1f}" if margins else "N/A",
                f"{sum(dcs)/len(dcs):.1f}" if dcs else "N/A",
            ])
        print_table(headers6, rows6)
        print()

        # Individual baton details
        print("  Individual baton actions:")
        for r in baton_recs:
            print(f"    [{r.condition}/{r.model}] {r.character_name} R{r.round_num}: "
                  f"margin={r.margin}, DC={r.dm_dc}, total={r.roll_total}, d20={r.d20}")
            print(f"      intent: {r.intent[:150]}")
            print()
    else:
        print("  No shock baton actions found.")
        print()

    # ============================================================
    # TABLE 7: All suppress actions detailed listing
    # ============================================================
    print("=" * 100)
    print("TABLE 7: ALL SUPPRESS ACTIONS - DETAILED LISTING")
    print("=" * 100)
    print()

    if suppress_recs:
        for i, r in enumerate(suppress_recs, 1):
            success_str = "PASS" if r.margin is not None and r.margin >= 0 else "FAIL" if r.margin is not None else "NO_ROLL"
            print(f"{i:3d}. [{r.condition}/{r.model}] {r.character_name} R{r.round_num} "
                  f"| {success_str} margin={r.margin} DC={r.dm_dc} total={r.roll_total} d20={r.d20} "
                  f"| PC_est={r.difficulty_estimate} | kw={r.matched_keyword}")
            print(f"     intent: {r.intent[:180]}")
            if r.description and r.description != r.intent:
                print(f"     desc:   {r.description[:180]}")
            print()
    else:
        print("  No suppress actions found.")
        print()

    # ============================================================
    # TABLE 8: Suppress vs Lethal summary comparison
    # ============================================================
    print("=" * 100)
    print("TABLE 8: SUPPRESS vs LETHAL SUMMARY BY CONDITION")
    print("=" * 100)
    print()

    headers8 = ["Condition", "Category", "N", "N_failed", "Fail_%", "Avg_margin", "Avg_PC_est", "Avg_DM_DC", "Avg_diff"]
    rows8 = []
    for cond in ["control", "treatment_v1", "treatment_v2"]:
        for cat_label, cat_recs in [("suppress", suppress_recs), ("lethal", lethal_recs), ("baton", baton_recs)]:
            recs = [r for r in cat_recs if r.condition == cond]
            if not recs:
                continue
            margins = [r.margin for r in recs if r.margin is not None]
            pc_ests = [r.difficulty_estimate for r in recs if r.difficulty_estimate is not None]
            dm_dcs = [r.dm_dc for r in recs if r.dm_dc is not None]
            paired = [(r.difficulty_estimate, r.dm_dc) for r in recs
                      if r.difficulty_estimate is not None and r.dm_dc is not None]
            diffs = [p[0] - p[1] for p in paired]
            n_failed = sum(1 for m in margins if m < 0)
            rows8.append([
                cond, cat_label, len(recs), n_failed,
                f"{100*n_failed/len(margins):.1f}" if margins else "N/A",
                f"{sum(margins)/len(margins):.1f}" if margins else "N/A",
                f"{sum(pc_ests)/len(pc_ests):.1f}" if pc_ests else "N/A",
                f"{sum(dm_dcs)/len(dm_dcs):.1f}" if dm_dcs else "N/A",
                f"{sum(diffs)/len(diffs):.1f}" if diffs else "N/A",
            ])

    print_table(headers8, rows8)
    print()

    # ============================================================
    # BONUS: Check for suppress-like actions that got classified as non-combat
    # ============================================================
    print("=" * 100)
    print("BONUS: SUPPRESS KEYWORD ACTIONS WITH NON-COMBAT action_type")
    print("=" * 100)
    print()

    non_combat_suppress = [r for r in suppress_recs if r.action_type != 'combat']
    if non_combat_suppress:
        for r in non_combat_suppress:
            print(f"  [{r.condition}/{r.model}] {r.character_name} R{r.round_num}: "
                  f"action_type={r.action_type}, kw={r.matched_keyword}")
            print(f"    intent: {r.intent[:150]}")
            print()
    else:
        print("  All suppress actions were correctly typed as 'combat'.")
        print()

    # ============================================================
    # Check: non-lethal keyword overlap with suppress
    # ============================================================
    print("=" * 100)
    print("BONUS: 'non-lethal' KEYWORD ACTIONS (may overlap with suppress)")
    print("=" * 100)
    print()
    
    nonlethal_recs = [r for r in all_records if 'non-lethal' in (r.matched_keyword or '') or 'non-lethal' in (r.intent + ' ' + r.description).lower()]
    if nonlethal_recs:
        for r in nonlethal_recs:
            is_also_suppress = any(kw in (r.intent + ' ' + r.description).lower() for kw in SUPPRESS_KEYWORDS if kw != 'non-lethal')
            print(f"  [{r.condition}/{r.model}] {r.character_name} R{r.round_num}: "
                  f"category={r.category}, also_suppress_kw={is_also_suppress}")
            print(f"    intent: {r.intent[:180]}")
            print()
    else:
        print("  No 'non-lethal' keyword actions found.")
        print()

    # ============================================================
    # TABLE 9: Suppress rolls with NO matching resolution
    # ============================================================
    print("=" * 100)
    print("TABLE 9: SUPPRESS DECLARATIONS WITH NO MATCHING RESOLUTION")
    print("=" * 100)
    print()
    
    no_res = [r for r in suppress_recs if r.dm_dc is None and r.margin is None]
    if no_res:
        for r in no_res:
            print(f"  [{r.condition}/{r.model}] {r.character_name} R{r.round_num}: "
                  f"PC_est={r.difficulty_estimate}, action_type={r.action_type}")
            print(f"    intent: {r.intent[:180]}")
            print()
    else:
        print("  All suppress declarations have matching resolutions.")
        print()


if __name__ == '__main__':
    main()
