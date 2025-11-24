#!/usr/bin/env python3
"""
Mine combat and skill check data from archive for game balance analysis.
"""
import json
from pathlib import Path
from collections import defaultdict, Counter

archive_dir = Path.home() / "Coding" / "aeonisk-logs-data" / "archive"
sessions = list(archive_dir.glob("*.jsonl"))

print(f"Analyzing {len(sessions)} sessions...\n")

# Combat stats
weapon_stats = defaultdict(lambda: {"hits": 0, "total": 0, "damage": []})
weapon_by_faction = defaultdict(lambda: defaultdict(lambda: {"hits": 0, "total": 0}))

# Skill check stats
skill_checks = defaultdict(lambda: {"success": 0, "total": 0, "margins": []})
skill_by_level = defaultdict(lambda: defaultdict(lambda: {"success": 0, "total": 0}))

# Void tracking
void_gains = []
void_by_faction = defaultdict(list)

# Soulcredit tracking
sc_changes = []

sessions_processed = 0

for session_file in sessions:
    try:
        with open(session_file) as f:
            events = [json.loads(line) for line in f if line.strip()]

        sessions_processed += 1

        for event in events:
            event_type = event.get("event_type")

            # Combat actions
            if event_type == "combat_action":
                weapon = event.get("weapon", "unknown")
                hit = event.get("hit", False)
                damage = event.get("damage_dealt", 0)
                faction = event.get("faction", "unknown")

                weapon_stats[weapon]["total"] += 1
                if hit:
                    weapon_stats[weapon]["hits"] += 1
                    weapon_stats[weapon]["damage"].append(damage)

                weapon_by_faction[faction][weapon]["total"] += 1
                if hit:
                    weapon_by_faction[faction][weapon]["hits"] += 1

            # Action resolutions (skill checks)
            if event_type == "action_resolution":
                roll = event.get("roll", {})
                if roll:
                    skill = roll.get("skill", "None")
                    skill_level = roll.get("skill_level", 0)
                    success = roll.get("success", False)
                    margin = roll.get("margin", 0)

                    skill_checks[skill]["total"] += 1
                    if success:
                        skill_checks[skill]["success"] += 1
                    skill_checks[skill]["margins"].append(margin)

                    # Track by skill level
                    skill_by_level[skill][skill_level]["total"] += 1
                    if success:
                        skill_by_level[skill][skill_level]["success"] += 1

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

print(f"✅ Processed {sessions_processed}/{len(sessions)} sessions\n")

# ===== WEAPON BALANCE REPORT =====
print("=" * 60)
print("WEAPON BALANCE ANALYSIS")
print("=" * 60)

if weapon_stats:
    print("\n📊 Weapon Effectiveness (sorted by hit rate):\n")
    sorted_weapons = sorted(weapon_stats.items(),
                          key=lambda x: x[1]["hits"]/x[1]["total"] if x[1]["total"] > 0 else 0,
                          reverse=True)

    for weapon, stats in sorted_weapons:
        if stats["total"] >= 3:  # Only show weapons used 3+ times
            hit_rate = (stats["hits"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            avg_damage = sum(stats["damage"]) / len(stats["damage"]) if stats["damage"] else 0

            status = ""
            if hit_rate > 75:
                status = "⚠️ OVERPOWERED?"
            elif hit_rate < 45:
                status = "⚠️ UNDERPOWERED?"

            print(f"  {weapon:25s} | {stats['hits']:3d}/{stats['total']:3d} hits ({hit_rate:5.1f}%) | "
                  f"Avg dmg: {avg_damage:4.1f} {status}")
else:
    print("  No combat data found in sessions")

# ===== SKILL CHECK BALANCE REPORT =====
print("\n" + "=" * 60)
print("SKILL CHECK BALANCE ANALYSIS")
print("=" * 60)

if skill_checks:
    print("\n📊 Skill Success Rates (sorted by success rate):\n")
    sorted_skills = sorted(skill_checks.items(),
                          key=lambda x: x[1]["success"]/x[1]["total"] if x[1]["total"] > 0 else 0,
                          reverse=True)

    for skill, stats in sorted_skills:
        if skill is None:
            continue  # Skip None skills
        if stats["total"] >= 5:  # Only show skills used 5+ times
            success_rate = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            avg_margin = sum(stats["margins"]) / len(stats["margins"]) if stats["margins"] else 0

            status = ""
            if success_rate > 80:
                status = "⚠️ TOO EASY?"
            elif success_rate < 40:
                status = "⚠️ TOO HARD?"

            print(f"  {skill:20s} | {stats['success']:3d}/{stats['total']:3d} success ({success_rate:5.1f}%) | "
                  f"Avg margin: {avg_margin:+5.1f} {status}")

    # Show skill level breakdown for top skills
    print("\n📊 Success Rate by Skill Level (top 3 skills):\n")
    top_skills = [s[0] for s in sorted_skills[:3] if s[1]["total"] >= 5]

    for skill in top_skills:
        print(f"  {skill}:")
        levels = sorted(skill_by_level[skill].items())
        for level, stats in levels:
            if stats["total"] >= 2:
                success_rate = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
                print(f"    Level {level}: {stats['success']}/{stats['total']} ({success_rate:.0f}%)")
else:
    print("  No skill check data found")

# ===== VOID ECONOMY REPORT =====
print("\n" + "=" * 60)
print("VOID ECONOMY ANALYSIS")
print("=" * 60)

if void_gains:
    print(f"\n📊 Void Changes ({len(void_gains)} events):\n")
    avg_void = sum(void_gains) / len(void_gains)
    max_void = max(void_gains)
    min_void = min(void_gains)

    print(f"  Average Void change: {avg_void:+.2f}")
    print(f"  Max Void gain: {max_void:+d}")
    print(f"  Min Void loss: {min_void:+d}")

    # Void distribution
    void_dist = Counter(void_gains)
    print(f"\n  Distribution:")
    for change in sorted(void_dist.keys()):
        count = void_dist[change]
        bar = "█" * (count // 2)
        print(f"    {change:+2d}: {bar} ({count})")

    # By faction
    if void_by_faction:
        print(f"\n  Average by faction:")
        for faction, changes in void_by_faction.items():
            if changes:
                avg = sum(changes) / len(changes)
                print(f"    {faction:20s}: {avg:+.2f} ({len(changes)} events)")
else:
    print("  No Void data found")

# ===== SOULCREDIT REPORT =====
print("\n" + "=" * 60)
print("SOULCREDIT ANALYSIS")
print("=" * 60)

if sc_changes:
    print(f"\n📊 Soulcredit Changes ({len(sc_changes)} events):\n")
    avg_sc = sum(sc_changes) / len(sc_changes)

    print(f"  Average SC change: {avg_sc:+.2f}")

    # SC distribution
    sc_dist = Counter(sc_changes)
    print(f"\n  Distribution:")
    for change in sorted(sc_dist.keys()):
        count = sc_dist[change]
        bar = "█" * (count // 2)
        print(f"    {change:+2d}: {bar} ({count})")
else:
    print("  No Soulcredit data found")

print("\n" + "=" * 60)
print("ANALYSIS COMPLETE")
print("=" * 60)
