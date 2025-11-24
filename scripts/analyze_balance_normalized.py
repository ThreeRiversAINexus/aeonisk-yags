#!/usr/bin/env python3
"""
Analyze game balance with attribute-normalized success rates.

This script computes success rates adjusted for player skill/attribute levels,
providing a more accurate picture of game difficulty and balance.
"""
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple
import statistics

archive_dir = Path.home() / "Coding" / "aeonisk-logs-data" / "archive"
sessions = list(archive_dir.glob("*.jsonl"))

print(f"Analyzing {len(sessions)} sessions with attribute normalization...\n")

# Skill check stats with attribute tracking
skill_performance = defaultdict(lambda: {
    "by_ability": defaultdict(lambda: {"success": 0, "total": 0, "margins": []}),
    "by_attr_val": defaultdict(lambda: {"success": 0, "total": 0, "margins": []}),
    "by_skill_val": defaultdict(lambda: {"success": 0, "total": 0, "margins": []}),
    "all_rolls": []  # Store all roll data for statistical analysis
})

# Attribute usage tracking
attribute_usage = defaultdict(lambda: {"success": 0, "total": 0, "margins": []})

# Combined ability level buckets (attr * skill or attr + skill)
ability_buckets = defaultdict(lambda: {"success": 0, "total": 0, "margins": []})

# Void tracking
void_gains = []
void_by_faction = defaultdict(list)

# Soulcredit tracking
sc_changes = []

sessions_processed = 0
total_action_resolutions = 0

for session_file in sessions:
    try:
        with open(session_file) as f:
            events = [json.loads(line) for line in f if line.strip()]

        sessions_processed += 1

        for event in events:
            event_type = event.get("event_type")

            # Action resolutions (skill checks)
            if event_type == "action_resolution":
                total_action_resolutions += 1
                roll = event.get("roll", {})

                if roll:
                    skill = roll.get("skill", "None")
                    attr = roll.get("attr", "Unknown")
                    attr_val = roll.get("attr_val", 0)
                    skill_val = roll.get("skill_val", 0)
                    ability = roll.get("ability", 0)  # This is attr*skill or attr+skill
                    success = roll.get("success", False)
                    margin = roll.get("margin", 0)
                    d20 = roll.get("d20", 0)

                    # Store comprehensive roll data
                    roll_data = {
                        "skill": skill,
                        "attr": attr,
                        "attr_val": attr_val,
                        "skill_val": skill_val,
                        "ability": ability,
                        "success": success,
                        "margin": margin,
                        "d20": d20
                    }
                    skill_performance[skill]["all_rolls"].append(roll_data)

                    # Track by ability level (combined stat)
                    skill_performance[skill]["by_ability"][ability]["total"] += 1
                    if success:
                        skill_performance[skill]["by_ability"][ability]["success"] += 1
                    skill_performance[skill]["by_ability"][ability]["margins"].append(margin)

                    # Track by attribute value
                    skill_performance[skill]["by_attr_val"][attr_val]["total"] += 1
                    if success:
                        skill_performance[skill]["by_attr_val"][attr_val]["success"] += 1
                    skill_performance[skill]["by_attr_val"][attr_val]["margins"].append(margin)

                    # Track by skill value
                    skill_performance[skill]["by_skill_val"][skill_val]["total"] += 1
                    if success:
                        skill_performance[skill]["by_skill_val"][skill_val]["success"] += 1
                    skill_performance[skill]["by_skill_val"][skill_val]["margins"].append(margin)

                    # Track attribute usage overall
                    attribute_usage[attr]["total"] += 1
                    if success:
                        attribute_usage[attr]["success"] += 1
                    attribute_usage[attr]["margins"].append(margin)

                    # Bucket by ability ranges
                    if ability < 0:
                        bucket = "negative"
                    elif ability == 0:
                        bucket = "0 (unskilled)"
                    elif ability <= 10:
                        bucket = "1-10 (low)"
                    elif ability <= 20:
                        bucket = "11-20 (moderate)"
                    elif ability <= 30:
                        bucket = "21-30 (high)"
                    else:
                        bucket = "31+ (expert)"

                    ability_buckets[bucket]["total"] += 1
                    if success:
                        ability_buckets[bucket]["success"] += 1
                    ability_buckets[bucket]["margins"].append(margin)

                # Void changes
                effects = event.get("effects", {})
                void_change = effects.get("void_changes")
                if void_change:
                    void_gains.append(void_change)
                    faction = event.get("faction", "unknown")
                    void_by_faction[faction].append(void_change)

                # SC changes
                sc_change = effects.get("soulcredit_changes")
                if sc_change:
                    sc_changes.append(sc_change)

    except Exception as e:
        continue

print(f"✅ Processed {sessions_processed}/{len(sessions)} sessions")
print(f"   Total action_resolution events: {total_action_resolutions:,}\n")

# ===== ATTRIBUTE-NORMALIZED SUCCESS ANALYSIS =====
print("=" * 70)
print("ATTRIBUTE-NORMALIZED SUCCESS RATE ANALYSIS")
print("=" * 70)

print("\n📊 Success Rate by Ability Level (attr×skill or attr+skill):\n")
print(f"{'Ability Range':<20} | {'Success':<12} | {'Rate':<8} | {'Avg Margin':<12} | {'Sample'}")
print("-" * 70)

# Sort by ability level
bucket_order = ["negative", "0 (unskilled)", "1-10 (low)", "11-20 (moderate)", "21-30 (high)", "31+ (expert)"]
for bucket in bucket_order:
    if bucket in ability_buckets:
        stats = ability_buckets[bucket]
        if stats["total"] >= 5:  # Min sample size
            success_rate = (stats["success"] / stats["total"]) * 100
            avg_margin = statistics.mean(stats["margins"]) if stats["margins"] else 0

            status = ""
            if success_rate > 80:
                status = "⚠️ TOO EASY"
            elif success_rate < 40:
                status = "⚠️ TOO HARD"

            print(f"{bucket:<20} | {stats['success']:>3}/{stats['total']:<6} | {success_rate:>5.1f}% | {avg_margin:>+6.1f}      | n={stats['total']:<5} {status}")

# ===== ATTRIBUTE USAGE ANALYSIS =====
print("\n" + "=" * 70)
print("ATTRIBUTE USAGE & SUCCESS RATES")
print("=" * 70)
print("\n📊 Success Rate by Attribute:\n")
print(f"{'Attribute':<15} | {'Success':<12} | {'Rate':<8} | {'Avg Margin':<12} | {'Usage'}")
print("-" * 70)

sorted_attrs = sorted(attribute_usage.items(),
                     key=lambda x: x[1]["total"],
                     reverse=True)

for attr, stats in sorted_attrs:
    if stats["total"] >= 10:  # Min sample size
        success_rate = (stats["success"] / stats["total"]) * 100
        avg_margin = statistics.mean(stats["margins"]) if stats["margins"] else 0
        usage_pct = (stats["total"] / total_action_resolutions) * 100

        print(f"{attr:<15} | {stats['success']:>3}/{stats['total']:<6} | {success_rate:>5.1f}% | {avg_margin:>+6.1f}      | {usage_pct:>5.1f}%")

# ===== SKILL-SPECIFIC NORMALIZED ANALYSIS =====
print("\n" + "=" * 70)
print("SKILL-SPECIFIC PERFORMANCE (with ability normalization)")
print("=" * 70)

# Filter skills with enough data
significant_skills = {
    skill: data
    for skill, data in skill_performance.items()
    if len(data["all_rolls"]) >= 10 and skill not in [None, "None"]
}

print(f"\n📊 Top Skills by Usage (showing ability level breakdown):\n")

# Sort by total usage
sorted_skills = sorted(
    significant_skills.items(),
    key=lambda x: len(x[1]["all_rolls"]),
    reverse=True
)[:10]  # Top 10 skills

for skill, data in sorted_skills:
    total_uses = len(data["all_rolls"])
    total_success = sum(1 for r in data["all_rolls"] if r["success"])
    overall_rate = (total_success / total_uses) * 100 if total_uses > 0 else 0
    avg_margin = statistics.mean([r["margin"] for r in data["all_rolls"]]) if data["all_rolls"] else 0

    print(f"\n{skill} (n={total_uses}):")
    print(f"  Overall: {total_success}/{total_uses} ({overall_rate:.1f}%) | Avg margin: {avg_margin:+.1f}")

    # Show ability level breakdown
    ability_stats = data["by_ability"]
    if len(ability_stats) > 1:  # Only show if there's variation
        print(f"  By ability level:")
        for ability_level in sorted(ability_stats.keys()):
            if ability_stats[ability_level]["total"] >= 2:  # Min 2 samples
                ab_stats = ability_stats[ability_level]
                ab_rate = (ab_stats["success"] / ab_stats["total"]) * 100
                ab_margin = statistics.mean(ab_stats["margins"]) if ab_stats["margins"] else 0
                print(f"    Ability {ability_level:>3}: {ab_stats['success']:>2}/{ab_stats['total']:<2} ({ab_rate:>5.1f}%) margin {ab_margin:>+5.1f}")

# ===== EXPECTED SUCCESS CALCULATION =====
print("\n" + "=" * 70)
print("DIFFICULTY CALIBRATION ANALYSIS")
print("=" * 70)
print("\nFor standard DC 18 (base difficulty):\n")

# Calculate expected success rates for different ability levels
# YAGS formula: d20 + ability vs DC
# Success if: d20 + ability >= DC

dc = 18
print(f"{'Ability':<10} | {'Expected Success':<18} | {'Observed Success':<18} | {'Δ':<10}")
print("-" * 70)

for bucket in bucket_order:
    if bucket in ability_buckets:
        stats = ability_buckets[bucket]
        if stats["total"] >= 5:
            # Calculate expected success rate (probability d20 + ability >= 18)
            # This is approximate - assumes ability is middle of range
            if bucket == "negative":
                avg_ability = -2
            elif bucket == "0 (unskilled)":
                avg_ability = -2  # Unskilled penalty
            elif bucket == "1-10 (low)":
                avg_ability = 5
            elif bucket == "11-20 (moderate)":
                avg_ability = 15
            elif bucket == "21-30 (high)":
                avg_ability = 25
            else:  # 31+ expert
                avg_ability = 35

            # Need d20 >= (DC - ability)
            needed_roll = dc - avg_ability
            if needed_roll <= 1:
                expected_success = 100.0
            elif needed_roll >= 20:
                expected_success = 5.0  # Only nat 20
            else:
                expected_success = ((21 - needed_roll) / 20) * 100

            observed_success = (stats["success"] / stats["total"]) * 100
            delta = observed_success - expected_success

            delta_str = f"{delta:+.1f}%"
            if abs(delta) > 15:
                delta_str += " ⚠️"

            print(f"{bucket:<10} | {expected_success:>5.1f}% (need {needed_roll:>2}+) | {observed_success:>5.1f}% (n={stats['total']:<4}) | {delta_str}")

# ===== VOID ECONOMY REPORT =====
print("\n" + "=" * 70)
print("VOID ECONOMY ANALYSIS")
print("=" * 70)

if void_gains:
    print(f"\n📊 Void Changes ({len(void_gains)} events):\n")
    avg_void = statistics.mean(void_gains)
    median_void = statistics.median(void_gains)
    max_void = max(void_gains)
    min_void = min(void_gains)

    print(f"  Average Void change: {avg_void:+.2f}")
    print(f"  Median Void change:  {median_void:+.1f}")
    print(f"  Max Void gain: {max_void:+d}")
    print(f"  Min Void loss: {min_void:+d}")

    # Void distribution
    void_dist = Counter(void_gains)
    print(f"\n  Distribution:")
    for change in sorted(void_dist.keys()):
        count = void_dist[change]
        pct = (count / len(void_gains)) * 100
        bar = "█" * min(50, count // 2)
        print(f"    {change:+2d}: {bar} ({count:>3}, {pct:>4.1f}%)")

    # By faction
    if void_by_faction:
        print(f"\n  Average by faction:")
        for faction, changes in sorted(void_by_faction.items(), key=lambda x: statistics.mean(x[1]) if x[1] else 0, reverse=True):
            if changes and len(changes) >= 3:
                avg = statistics.mean(changes)
                median = statistics.median(changes)
                print(f"    {faction:<25s}: avg {avg:+.2f}, median {median:+.1f} (n={len(changes)})")
else:
    print("  No Void data found")

# ===== SOULCREDIT REPORT =====
print("\n" + "=" * 70)
print("SOULCREDIT ANALYSIS")
print("=" * 70)

if sc_changes:
    print(f"\n📊 Soulcredit Changes ({len(sc_changes)} events):\n")
    avg_sc = statistics.mean(sc_changes)
    median_sc = statistics.median(sc_changes)

    print(f"  Average SC change: {avg_sc:+.2f}")
    print(f"  Median SC change:  {median_sc:+.1f}")

    # SC distribution
    sc_dist = Counter(sc_changes)
    print(f"\n  Distribution:")
    for change in sorted(sc_dist.keys()):
        count = sc_dist[change]
        pct = (count / len(sc_changes)) * 100
        bar = "█" * min(50, count // 2)
        print(f"    {change:+2d}: {bar} ({count:>3}, {pct:>4.1f}%)")
else:
    print("  No Soulcredit data found")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
print(f"\nKey Insights:")
print(f"  • Analyzed {total_action_resolutions:,} skill checks across {sessions_processed} sessions")
print(f"  • Success rates normalized by player ability (attr×skill)")
print(f"  • Check 'DIFFICULTY CALIBRATION' section for DC tuning recommendations")
print(f"  • Combat logging not available in archive data (ignored)")
print("=" * 70)
