#!/usr/bin/env python3
"""
Extract suppressive fire action quotes and condition data from treatment v2 sessions.

Searches action_declaration events for suppressive keywords, then matches
to action_resolution events to get DM narration, damage, conditions, etc.

Filters:
- Only PC actions (Enforcer Kael Dren, Drifter Sable)
- Only combat-type actions
- Negation patterns excluded ("No warning shot", etc.)
- Past-tense/third-party references excluded
"""

import json
import glob
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# Configuration
BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../../multiagent_output/lethality_experiment/treatment_v2"
)

MAIN_RUN = os.path.join(BASE_DIR, "run_2026-02-16_172446_72c3a9ef")
DEEPSEEK_RETRY = os.path.join(BASE_DIR, "run_2026-02-16_200845_9b430506")

MODEL_NAMES = {
    "claude-opus-4-6": "Claude Opus 4.6",
    "deepseek-ai/DeepSeek-V3.2": "DeepSeek V3.2",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "grok-4-latest": "Grok 4",
    "gpt-5.2-2025-12-11": "GPT-5.2",
}

# PCs only
PC_NAMES = {"Enforcer Kael Dren", "Drifter Sable"}

# Suppressive keywords - positive matches
SUPPRESSIVE_PATTERNS_POS = [
    re.compile(r"\bsuppress(?:ive|ing|ion)?\b", re.IGNORECASE),
    re.compile(r"\bpin(?:ning)?\s+(?:them\s+)?down\b", re.IGNORECASE),
    re.compile(r"\bcovering\s+fire\b", re.IGNORECASE),
    re.compile(r"\bcover\s+fire\b", re.IGNORECASE),
    re.compile(r"\bwarning\s+shot\b", re.IGNORECASE),
    re.compile(r"\bwarning\s+burst\b", re.IGNORECASE),
    re.compile(r"\bforce\s+\w+\s+(?:behind|into)\s+cover\b", re.IGNORECASE),
    re.compile(r"\bnon-lethal\b", re.IGNORECASE),
    re.compile(r"\bnonlethal\b", re.IGNORECASE),
    re.compile(r"\bincapacitat\w*\b", re.IGNORECASE),
    re.compile(r"\barea\s+denial\b", re.IGNORECASE),
]

# Negation patterns - exclude matches where keyword is negated
NEGATION_PATTERNS = [
    re.compile(r"\bno\s+warning\s+shot", re.IGNORECASE),
    re.compile(r"\bno\s+warning\s+burst", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:a\s+)?warning", re.IGNORECASE),
    re.compile(r"\brather\s+than\s+warning", re.IGNORECASE),
    re.compile(r"\binstead\s+of\s+warning", re.IGNORECASE),
    re.compile(r"\bwithout\s+warning", re.IGNORECASE),
]

# Condition keywords to detect in status_effects
CONDITION_KEYWORDS = [
    "pinned", "suppressed", "pinned down", "forced into cover",
    "full suppression",
    "scared", "flinch", "cowering", "shaken", "rattled",
    "prone", "stunned", "dazed", "disoriented", "off-balance",
    "disadvantage", "penalty",
    "unnerved",
]


@dataclass
class SuppressiveAction:
    run_id: str
    model: str
    model_short: str
    round: int
    character_name: str
    player_description: str
    player_intent: str
    action_type: str
    dm_narration: str = ""
    dm_action_summary: str = ""
    rationale: str = ""
    roll_total: Optional[int] = None
    roll_margin: Optional[int] = None
    roll_tier: str = ""
    roll_success: Optional[bool] = None
    d20: Optional[int] = None
    base_damage: int = 0
    damage_dealt: int = 0
    damage_type: str = ""
    damage_soak: int = 0
    status_effects: list = field(default_factory=list)
    conditions_applied: list = field(default_factory=list)
    soulcredit_delta: int = 0
    soulcredit_reasons: list = field(default_factory=list)
    void_delta: int = 0
    matched_keywords: list = field(default_factory=list)
    target: str = ""


def find_matching_keywords(text):
    """Return list of suppressive keywords found in text, after negation check."""
    # First check for negations
    for neg in NEGATION_PATTERNS:
        if neg.search(text):
            # Remove negated regions from consideration
            text = neg.sub("", text)

    matches = []
    for pattern in SUPPRESSIVE_PATTERNS_POS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def is_self_referencing_suppressive(desc, intent):
    """Check if the description is about the CHARACTER performing suppression,
    not just referencing someone else's."""
    combined = f"{desc} {intent}".lower()
    # If it says "Sable's suppressive fire" or "Kael's suppressing" -- that's 3rd party
    # But we already filter to PCs only, so the real question is whether
    # the keyword appears in a self-action context
    # Simple heuristic: if "I" or "my" appears near the keyword, it's self-referencing
    # If it's a passive reference ("under suppressive fire"), skip it
    passive_patterns = [
        re.compile(r"\bunder\s+suppress", re.IGNORECASE),
        re.compile(r"\bwas\s+suppress", re.IGNORECASE),
        re.compile(r"\bbeing\s+suppress", re.IGNORECASE),
        re.compile(r"\bincapacitated\b.*\bbeg\b", re.IGNORECASE),
        re.compile(r"\bsubdued\b.*\bprisoner\b", re.IGNORECASE),
        re.compile(r"\bthe\s+incapacitated\b", re.IGNORECASE),
    ]
    for pp in passive_patterns:
        if pp.search(combined):
            return False
    return True


def extract_conditions(status_effects):
    conditions = []
    for effect in status_effects:
        effect_lower = effect.lower()
        for kw in CONDITION_KEYWORDS:
            if kw in effect_lower:
                conditions.append(effect)
                break
    return conditions


def get_model_short(model_id):
    return MODEL_NAMES.get(model_id, model_id)


def load_run_data(run_path):
    jsonl_files = glob.glob(os.path.join(run_path, "*.jsonl"))
    if not jsonl_files:
        return [], []
    declarations = []
    resolutions = []
    with open(jsonl_files[0]) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event_type") == "action_declaration":
                declarations.append(e)
            elif e.get("event_type") == "action_resolution":
                resolutions.append(e)
    return declarations, resolutions


def process_run(run_path, run_id, model_id):
    declarations, resolutions = load_run_data(run_path)
    results = []

    res_lookup = {}
    for r in resolutions:
        key = (r.get("round"), r.get("agent"))
        if key not in res_lookup:
            res_lookup[key] = r

    for decl in declarations:
        action = decl.get("action", {})
        char_name = decl.get("character_name", "")

        # Filter: PCs only
        if char_name not in PC_NAMES:
            continue

        desc = action.get("description", "") or ""
        intent = action.get("intent", "") or ""
        action_type = action.get("action_type", "") or ""

        # Filter: combat actions only (suppressive fire is a combat action)
        # But also allow "custom" for restrain-type actions
        if action_type not in ("combat", "custom", ""):
            continue

        combined_text = f"{desc} {intent}"

        matched = find_matching_keywords(combined_text)
        if not matched:
            continue

        # Filter: self-referencing check
        if not is_self_referencing_suppressive(desc, intent):
            continue

        rnd = decl.get("round")
        model_short = get_model_short(model_id)

        sa = SuppressiveAction(
            run_id=run_id,
            model=model_id,
            model_short=model_short,
            round=rnd,
            character_name=char_name,
            player_description=desc,
            player_intent=intent,
            action_type=action_type,
            matched_keywords=matched,
        )

        res = res_lookup.get((rnd, char_name))
        if res:
            ctx = res.get("context", {})
            sa.dm_narration = ctx.get("narration", "")
            sa.dm_action_summary = res.get("action", "")
            sa.rationale = res.get("rationale", "")
            sa.target = ctx.get("target", "") or ""

            roll = res.get("roll", {})
            if roll:
                sa.roll_total = roll.get("total")
                sa.roll_margin = roll.get("margin")
                sa.roll_tier = roll.get("tier", "")
                sa.roll_success = roll.get("success")
                sa.d20 = roll.get("d20")

            dmg_effects = ctx.get("damage_effects", [])
            if dmg_effects:
                de = dmg_effects[0]
                sa.base_damage = de.get("base_damage", 0) or 0
                sa.damage_dealt = de.get("dealt", 0) or 0
                sa.damage_type = de.get("damage_type", "") or ""
                sa.damage_soak = de.get("soak", 0) or 0
            else:
                eff_dmg = res.get("effects", {}).get("damage", {})
                if eff_dmg:
                    sa.damage_dealt = eff_dmg.get("dealt", 0) or 0

            effects = res.get("effects", {})
            sa.status_effects = effects.get("status_effects", []) or []
            sa.conditions_applied = extract_conditions(sa.status_effects)

            economy = res.get("economy", {})
            sa.soulcredit_delta = economy.get("soulcredit_delta", 0) or 0
            sa.soulcredit_reasons = economy.get("soulcredit_reasons", []) or []
            sa.void_delta = economy.get("void_delta", 0) or 0

        results.append(sa)

    return results


def main():
    print("=" * 80)
    print("SUPPRESSIVE FIRE ACTION EXTRACTION - Treatment v2 Sessions")
    print("=" * 80)
    print("Filters: PC-only (Kael/Sable), combat actions, negation-aware")
    print()

    all_actions = []

    for run_dir in sorted(os.listdir(MAIN_RUN)):
        if not run_dir.startswith("run_"):
            continue
        run_path = os.path.join(MAIN_RUN, run_dir)
        if not os.path.isdir(run_path):
            continue
        cfg_path = os.path.join(run_path, "config.json")
        if not os.path.exists(cfg_path):
            continue
        with open(cfg_path) as f:
            cfg = json.load(f)
        model_id = cfg.get("agents", {}).get("dm", {}).get("llm", {}).get("model", "unknown")
        actions = process_run(run_path, run_dir, model_id)
        all_actions.extend(actions)

    retry_run_path = os.path.join(DEEPSEEK_RETRY, "run_0001")
    if os.path.isdir(retry_run_path):
        cfg_path = os.path.join(retry_run_path, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            model_id = cfg.get("agents", {}).get("dm", {}).get("llm", {}).get("model", "unknown")
            actions = process_run(retry_run_path, "retry_run_0001", model_id)
            all_actions.extend(actions)

    if not all_actions:
        print("ERROR: No suppressive actions found!")
        sys.exit(1)

    # SECTION 1: Player Declaration Quotes
    print("=" * 80)
    print("SECTION 1: PLAYER DECLARATION QUOTES (Suppressive Actions)")
    print("=" * 80)
    print()

    by_model = defaultdict(list)
    for a in all_actions:
        by_model[a.model_short].append(a)

    for model_name in sorted(by_model.keys()):
        actions = by_model[model_name]
        print(f"--- {model_name} ({len(actions)} suppressive actions) ---")
        print()
        for a in sorted(actions, key=lambda x: (x.run_id, x.round)):
            print(f"  [{a.run_id}] Round {a.round} | {a.character_name}")
            print(f"  Keywords matched: {', '.join(a.matched_keywords)}")
            print(f"  Action type: {a.action_type}")
            print(f"  Intent: {a.player_intent}")
            print(f"  Description: {a.player_description}")
            print()

    # SECTION 2: DM Resolution Details
    print()
    print("=" * 80)
    print("SECTION 2: DM RESOLUTION DETAILS (Narration + Mechanics)")
    print("=" * 80)
    print()

    for model_name in sorted(by_model.keys()):
        actions = by_model[model_name]
        print(f"--- {model_name} ---")
        print()
        for a in sorted(actions, key=lambda x: (x.run_id, x.round)):
            has_resolution = bool(a.dm_narration or a.roll_total is not None)
            print(f"  [{a.run_id}] Round {a.round} | {a.character_name}")
            if not has_resolution:
                print(f"    *** NO MATCHING RESOLUTION FOUND ***")
                print()
                continue

            print(f"  Roll: total={a.roll_total}, margin={a.roll_margin}, "
                  f"tier={a.roll_tier}, d20={a.d20}, success={a.roll_success}")
            print(f"  Damage: base={a.base_damage}, dealt={a.damage_dealt}, "
                  f"type={a.damage_type}, soak={a.damage_soak}")
            print(f"  Status effects: {a.status_effects}")
            print(f"  Conditions extracted: {a.conditions_applied}")
            print(f"  Soulcredit delta: {a.soulcredit_delta} | "
                  f"Reasons: {a.soulcredit_reasons}")
            print(f"  Void delta: {a.void_delta}")
            print(f"  Target: {a.target}")
            print(f"  DM Action Summary: {a.dm_action_summary}")
            print(f"  Rationale: {a.rationale}")
            print()
            print(f"  DM Narration:")
            for nline in a.dm_narration.split("\n"):
                print(f"    {nline}")
            print()
            print(f"  {'~' * 70}")
            print()

    # SECTION 3: Condition Application Analysis
    print()
    print("=" * 80)
    print("SECTION 3: CONDITION APPLICATION ANALYSIS")
    print("=" * 80)
    print()

    total = len(all_actions)
    with_conditions = [a for a in all_actions if a.conditions_applied]
    without_conditions = [a for a in all_actions if not a.conditions_applied]
    with_any_status = [a for a in all_actions if a.status_effects]
    without_any_status = [a for a in all_actions if not a.status_effects]

    print(f"Total suppressive actions found: {total}")
    print(f"With condition-like status effects: {len(with_conditions)} "
          f"({100*len(with_conditions)/total:.1f}%)")
    print(f"Without condition-like status effects: {len(without_conditions)} "
          f"({100*len(without_conditions)/total:.1f}%)")
    print(f"With ANY status effects: {len(with_any_status)} "
          f"({100*len(with_any_status)/total:.1f}%)")
    print(f"Without ANY status effects: {len(without_any_status)} "
          f"({100*len(without_any_status)/total:.1f}%)")
    print()

    condition_type_counts = defaultdict(int)
    for a in all_actions:
        for cond in a.conditions_applied:
            cond_name = cond.split(":")[0].strip() if ":" in cond else cond.strip()
            condition_type_counts[cond_name] += 1

    if condition_type_counts:
        print("Condition type breakdown:")
        for cond, count in sorted(condition_type_counts.items(), key=lambda x: -x[1]):
            print(f"  {cond}: {count}")
        print()

    all_status = defaultdict(int)
    for a in all_actions:
        for se in a.status_effects:
            all_status[se] += 1

    print("All unique status effects applied to suppressive actions:")
    for se, count in sorted(all_status.items(), key=lambda x: -x[1]):
        print(f"  [{count}x] {se}")
    print()

    print("Conditions by model:")
    for model_name in sorted(by_model.keys()):
        actions = by_model[model_name]
        n = len(actions)
        n_cond = sum(1 for a in actions if a.conditions_applied)
        n_status = sum(1 for a in actions if a.status_effects)
        print(f"  {model_name}: {n} suppressive, "
              f"{n_cond} with conditions ({100*n_cond/n:.0f}%), "
              f"{n_status} with any status ({100*n_status/n:.0f}%)")

    # SECTION 4: Standout Quotes
    print()
    print()
    print("=" * 80)
    print("SECTION 4: STANDOUT QUOTES")
    print("=" * 80)
    print()

    # Good examples: low damage + strong conditions
    good_candidates = [
        a for a in all_actions
        if a.conditions_applied and a.damage_dealt <= 5 and a.dm_narration
    ]
    good_candidates.sort(key=lambda x: (x.damage_dealt, -len(x.conditions_applied)))

    print("-- GOOD EXAMPLES (Low damage, strong conditions -- suppression working) --")
    print()
    seen_models = set()
    good_shown = 0
    for a in good_candidates:
        if a.model_short in seen_models:
            continue
        seen_models.add(a.model_short)
        print(f"  >>> [{a.model_short}] {a.run_id} R{a.round} {a.character_name}")
        print(f"  Player declaration:")
        print(f"    \"{a.player_description}\"")
        print(f"  Roll: margin={a.roll_margin}, tier={a.roll_tier}")
        print(f"  Damage dealt: {a.damage_dealt} ({a.damage_type})")
        print(f"  Conditions: {a.conditions_applied}")
        print(f"  Soulcredit: {a.soulcredit_delta}")
        # Print key narration excerpts (skip roll formulas)
        narr = a.dm_narration
        paragraphs = [p.strip() for p in narr.split("\n") if len(p.strip()) > 60]
        desc_paragraphs = [p for p in paragraphs
                          if not p.startswith("Roll:") and not p.startswith("Calculation:")
                          and not p.startswith("DC:") and not p.startswith("**")]
        if desc_paragraphs:
            print(f"  DM narration excerpt:")
            print(f"    \"{desc_paragraphs[0]}\"")
        print()
        good_shown += 1
        if good_shown >= 4:
            break

    # Fill from zero-damage if needed
    if good_shown < 4:
        zero_dmg = [a for a in all_actions if a.damage_dealt == 0 and a.dm_narration
                    and a.model_short not in seen_models and a.status_effects]
        zero_dmg.sort(key=lambda x: -len(x.status_effects))
        for a in zero_dmg:
            seen_models.add(a.model_short)
            print(f"  >>> [{a.model_short}] {a.run_id} R{a.round} {a.character_name}")
            print(f"  Player declaration:")
            print(f"    \"{a.player_description}\"")
            print(f"  Roll: margin={a.roll_margin}, tier={a.roll_tier}")
            print(f"  Damage dealt: {a.damage_dealt} ({a.damage_type})")
            print(f"  Status effects: {a.status_effects}")
            print(f"  Soulcredit: {a.soulcredit_delta}")
            narr = a.dm_narration
            paragraphs = [p.strip() for p in narr.split("\n") if len(p.strip()) > 60]
            desc_paragraphs = [p for p in paragraphs
                              if not p.startswith("Roll:") and not p.startswith("Calculation:")
                              and not p.startswith("DC:") and not p.startswith("**")]
            if desc_paragraphs:
                print(f"  DM narration excerpt:")
                print(f"    \"{desc_paragraphs[0]}\"")
            print()
            good_shown += 1
            if good_shown >= 4:
                break

    print()
    print("-- BAD EXAMPLES (High damage despite suppressive intent -- lethality leak) --")
    print()

    bad_candidates = [
        a for a in all_actions
        if a.damage_dealt >= 8 and a.dm_narration
    ]
    bad_candidates.sort(key=lambda x: -x.damage_dealt)

    seen_models_bad = set()
    bad_shown = 0
    for a in bad_candidates:
        if a.model_short in seen_models_bad:
            continue
        seen_models_bad.add(a.model_short)
        print(f"  >>> [{a.model_short}] {a.run_id} R{a.round} {a.character_name}")
        print(f"  Player declaration:")
        print(f"    \"{a.player_description}\"")
        print(f"  Roll: margin={a.roll_margin}, tier={a.roll_tier}")
        print(f"  Damage dealt: {a.damage_dealt} ({a.damage_type})")
        print(f"  Status effects: {a.status_effects}")
        print(f"  Conditions: {a.conditions_applied}")
        print(f"  Soulcredit: {a.soulcredit_delta}")
        narr = a.dm_narration
        paragraphs = [p.strip() for p in narr.split("\n") if len(p.strip()) > 60]
        desc_paragraphs = [p for p in paragraphs
                          if not p.startswith("Roll:") and not p.startswith("Calculation:")
                          and not p.startswith("DC:") and not p.startswith("**")]
        if desc_paragraphs:
            print(f"  DM narration excerpt:")
            print(f"    \"{desc_paragraphs[0]}\"")
        print()
        bad_shown += 1
        if bad_shown >= 4:
            break

    # Fill in more if needed
    if bad_shown < 4:
        more_bad = [a for a in all_actions if a.damage_dealt > 0 and a.dm_narration
                    and a.model_short not in seen_models_bad]
        more_bad.sort(key=lambda x: -x.damage_dealt)
        for a in more_bad:
            seen_models_bad.add(a.model_short)
            print(f"  >>> [{a.model_short}] {a.run_id} R{a.round} {a.character_name}")
            print(f"  Player declaration:")
            print(f"    \"{a.player_description}\"")
            print(f"  Damage dealt: {a.damage_dealt} ({a.damage_type})")
            print(f"  Status effects: {a.status_effects}")
            narr = a.dm_narration
            paragraphs = [p.strip() for p in narr.split("\n") if len(p.strip()) > 60]
            desc_paragraphs = [p for p in paragraphs
                              if not p.startswith("Roll:") and not p.startswith("Calculation:")
                              and not p.startswith("DC:") and not p.startswith("**")]
            if desc_paragraphs:
                print(f"  DM narration excerpt:")
                print(f"    \"{desc_paragraphs[0]}\"")
            print()
            bad_shown += 1
            if bad_shown >= 4:
                break

    # SECTION 5: Summary Statistics
    print()
    print("=" * 80)
    print("SECTION 5: SUMMARY STATISTICS")
    print("=" * 80)
    print()

    n_total = len(all_actions)
    n_with_resolution = sum(1 for a in all_actions if a.dm_narration)
    n_with_damage = sum(1 for a in all_actions if a.damage_dealt > 0)
    n_with_conditions = sum(1 for a in all_actions if a.conditions_applied)
    n_with_any_status = sum(1 for a in all_actions if a.status_effects)
    n_with_both = sum(1 for a in all_actions if a.damage_dealt > 0 and a.conditions_applied)
    n_with_neither = sum(1 for a in all_actions if a.damage_dealt == 0 and not a.conditions_applied)
    n_damage_only = sum(1 for a in all_actions if a.damage_dealt > 0 and not a.conditions_applied)
    n_conditions_only = sum(1 for a in all_actions if a.damage_dealt == 0 and a.conditions_applied)
    n_wound = sum(1 for a in all_actions if a.damage_type == "wound")
    n_stun = sum(1 for a in all_actions if a.damage_type == "stun")

    damages = [a.damage_dealt for a in all_actions if a.damage_dealt > 0]
    avg_damage = sum(damages) / len(damages) if damages else 0
    max_damage = max(damages) if damages else 0
    min_damage = min(damages) if damages else 0

    all_damages = [a.damage_dealt for a in all_actions]
    overall_avg = sum(all_damages) / len(all_damages) if all_damages else 0

    print(f"Total suppressive actions classified: {n_total}")
    print(f"  With resolution events: {n_with_resolution}")
    print()
    print(f"Damage breakdown:")
    print(f"  N with damage > 0: {n_with_damage} ({100*n_with_damage/n_total:.1f}%)")
    print(f"  N with damage = 0: {n_total - n_with_damage} ({100*(n_total-n_with_damage)/n_total:.1f}%)")
    if damages:
        print(f"  Avg damage (when > 0): {avg_damage:.1f}")
    print(f"  Avg damage (overall): {overall_avg:.1f}")
    print(f"  Max damage: {max_damage}")
    if damages:
        print(f"  Min damage (when > 0): {min_damage}")
    print(f"  Wound type: {n_wound}, Stun type: {n_stun}")
    print()
    print(f"Condition breakdown:")
    print(f"  N with conditions applied: {n_with_conditions} ({100*n_with_conditions/n_total:.1f}%)")
    print(f"  N with ANY status effects: {n_with_any_status} ({100*n_with_any_status/n_total:.1f}%)")
    print()
    print(f"Cross-tabulation:")
    print(f"  Damage + Conditions: {n_with_both} ({100*n_with_both/n_total:.1f}%)")
    print(f"  Damage only (no conditions): {n_damage_only} ({100*n_damage_only/n_total:.1f}%)")
    print(f"  Conditions only (no damage): {n_conditions_only} ({100*n_conditions_only/n_total:.1f}%)")
    print(f"  Neither damage nor conditions: {n_with_neither} ({100*n_with_neither/n_total:.1f}%)")
    print()

    print("By model:")
    print(f"  {'Model':<20} {'N':>4} {'Dmg>0':>6} {'Cond':>6} {'Both':>6} {'Neither':>8} {'AvgDmg':>8} {'AvgDmgAll':>10}")
    for model_name in sorted(by_model.keys()):
        actions = by_model[model_name]
        n = len(actions)
        nd = sum(1 for a in actions if a.damage_dealt > 0)
        nc = sum(1 for a in actions if a.conditions_applied)
        nb = sum(1 for a in actions if a.damage_dealt > 0 and a.conditions_applied)
        nn = sum(1 for a in actions if a.damage_dealt == 0 and not a.conditions_applied)
        dms = [a.damage_dealt for a in actions if a.damage_dealt > 0]
        ad = sum(dms) / len(dms) if dms else 0
        ada = sum(a.damage_dealt for a in actions) / n if n else 0
        print(f"  {model_name:<20} {n:>4} {nd:>6} {nc:>6} {nb:>6} {nn:>8} {ad:>8.1f} {ada:>10.1f}")
    print()

    sc_positive = sum(1 for a in all_actions if a.soulcredit_delta > 0)
    sc_negative = sum(1 for a in all_actions if a.soulcredit_delta < 0)
    sc_zero = sum(1 for a in all_actions if a.soulcredit_delta == 0)
    print(f"Soulcredit for suppressive actions:")
    print(f"  Positive: {sc_positive}")
    print(f"  Zero: {sc_zero}")
    print(f"  Negative: {sc_negative}")
    print()

    print("Damage type by model:")
    for model_name in sorted(by_model.keys()):
        actions = by_model[model_name]
        wound = sum(1 for a in actions if a.damage_type == "wound")
        stun = sum(1 for a in actions if a.damage_type == "stun")
        none_t = sum(1 for a in actions if not a.damage_type)
        other = sum(1 for a in actions if a.damage_type and a.damage_type not in ("wound", "stun", ""))
        print(f"  {model_name}: wound={wound}, stun={stun}, none={none_t}, other={other}")

    # SECTION 6: Compact Individual Actions
    print()
    print("=" * 80)
    print("SECTION 6: INDIVIDUAL ACTION DETAILS (COMPACT)")
    print("=" * 80)
    print()

    for i, a in enumerate(sorted(all_actions, key=lambda x: (x.model_short, x.run_id, x.round)), 1):
        flag_dmg = "DMG" if a.damage_dealt > 0 else "---"
        flag_cond = "COND" if a.conditions_applied else "----"
        flag_status = "STAT" if a.status_effects and not a.conditions_applied else "    "
        print(f"{i:3d}. [{a.model_short:<18}] {a.run_id:<16} R{a.round:>2} {a.character_name:<22} "
              f"{flag_dmg} {a.damage_dealt:>3}hp({a.damage_type or 'none':>5}) "
              f"{flag_cond} {flag_status} "
              f"roll={a.roll_total or '?':>3} margin={a.roll_margin or '?':>3} "
              f"sc={a.soulcredit_delta:>2}")

    print()
    print("DONE.")


if __name__ == "__main__":
    main()
