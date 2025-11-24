#!/usr/bin/env python3
"""Quick stats on archive sessions with normalized success analysis."""
import json
import sys
from pathlib import Path
from collections import defaultdict
import statistics

archive_dir = Path.home() / "Coding" / "aeonisk-logs-data" / "archive"

# Allow command-line arg for sample size, default to 50
sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 50
sessions = list(archive_dir.glob("*.jsonl"))[:sample_size]

total_rounds = 0
total_actions = 0
total_events = 0
sessions_with_combat = 0

# Track success by ability level
ability_buckets = defaultdict(lambda: {"success": 0, "total": 0})

for session_file in sessions:
    try:
        with open(session_file) as f:
            events = [json.loads(line) for line in f if line.strip()]

        total_events += len(events)

        # Count rounds
        rounds = set()
        actions = 0
        has_combat = False

        for event in events:
            if "round" in event and event["round"] is not None:
                rounds.add(event["round"])

            if event.get("event_type") == "action_resolution":
                actions += 1

                # Track normalized success
                roll = event.get("roll", {})
                if roll:
                    ability = roll.get("ability", 0)
                    success = roll.get("success", False)

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

            if event.get("event_type") == "combat_action":
                has_combat = True

        total_rounds += len(rounds)
        total_actions += actions
        if has_combat:
            sessions_with_combat += 1

    except Exception as e:
        continue

print(f"Sampled: {len(sessions)} sessions")
print(f"Total events: {total_events:,}")
print(f"Total rounds: {total_rounds}")
print(f"Total actions: {total_actions}")
print(f"Sessions with combat: {sessions_with_combat} (combat logging not available in archive)")
print(f"\nAverages:")
print(f"  Events/session: {total_events // len(sessions)}")
print(f"  Rounds/session: {total_rounds // len(sessions)}")
print(f"  Actions/session: {total_actions // len(sessions)}")

# Show normalized success rates
print(f"\nNormalized Success Rates (by ability level):")
bucket_order = ["negative", "0 (unskilled)", "1-10 (low)", "11-20 (moderate)", "21-30 (high)", "31+ (expert)"]
for bucket in bucket_order:
    if bucket in ability_buckets:
        stats = ability_buckets[bucket]
        if stats["total"] > 0:
            success_rate = (stats["success"] / stats["total"]) * 100
            print(f"  {bucket:<18}: {stats['success']:>3}/{stats['total']:<3} ({success_rate:>5.1f}%)")

print(f"\nEstimated full archive (587 sessions):")
print(f"  Total events: {(total_events // len(sessions)) * 587:,}")
print(f"  Total rounds: {(total_rounds // len(sessions)) * 587:,}")
print(f"  Total actions: {(total_actions // len(sessions)) * 587:,}")

print(f"\nFor detailed normalized analysis, run:")
print(f"  python3 scripts/analyze_balance_normalized.py")
