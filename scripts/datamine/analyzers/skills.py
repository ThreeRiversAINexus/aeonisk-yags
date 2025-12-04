"""
Skills analyzer - extract attribute x skill patterns and difficulty calibration.

Metrics:
- Most common attr x skill combinations
- Success rate by ability bucket (attr + skill_val)
- Expected vs observed success rates (DC calibration)
- Margin distribution by skill
"""

from collections import Counter, defaultdict
from typing import Dict, Any, Set, List
import statistics

from .base import BaseAnalyzer, AnalyzerResult


# Ability level buckets for grouping
ABILITY_BUCKETS = [
    ("negative", lambda x: x < 0),
    ("0 (unskilled)", lambda x: x == 0),
    ("1-10 (low)", lambda x: 1 <= x <= 10),
    ("11-20 (moderate)", lambda x: 11 <= x <= 20),
    ("21-30 (high)", lambda x: 21 <= x <= 30),
    ("31+ (expert)", lambda x: x > 30),
]

# Bucket midpoints for expected success calculation
BUCKET_MIDPOINTS = {
    "negative": -2,
    "0 (unskilled)": -2,  # Unskilled penalty
    "1-10 (low)": 5,
    "11-20 (moderate)": 15,
    "21-30 (high)": 25,
    "31+ (expert)": 35,
}


def get_ability_bucket(ability: int) -> str:
    """Classify ability value into bucket."""
    for bucket_name, predicate in ABILITY_BUCKETS:
        if predicate(ability):
            return bucket_name
    return "31+ (expert)"  # Fallback


def calculate_expected_success(ability_midpoint: int, dc: int = 18) -> float:
    """
    Calculate expected success rate for a given ability against DC.

    Formula: d20 + ability >= DC
    Success if d20 >= (DC - ability)
    """
    needed_roll = dc - ability_midpoint
    if needed_roll <= 1:
        return 100.0  # Auto-success (need 1 or less)
    elif needed_roll >= 20:
        return 5.0  # Only nat 20 succeeds
    else:
        # Probability of rolling needed_roll or higher on d20
        return ((21 - needed_roll) / 20) * 100


class SkillsAnalyzer(BaseAnalyzer):
    """
    Analyze skill check patterns and difficulty calibration.

    Processes action_resolution events to extract:
    - Attr x Skill combination usage
    - Success rates by ability level
    - DC calibration (expected vs observed)
    - Margin distributions
    """

    @property
    def name(self) -> str:
        return "skills"

    @property
    def event_types(self) -> Set[str]:
        return {"action_resolution"}

    def __init__(self, dc_baseline: int = 18):
        self.dc_baseline = dc_baseline
        self.reset()

    def reset(self) -> None:
        """Reset all accumulated state."""
        # Attr x Skill combinations
        self._attr_skill_combos: Counter = Counter()

        # Stats by ability bucket
        self._ability_buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"success": 0, "total": 0, "margins": []}
        )

        # Stats by individual skill
        self._skill_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"success": 0, "total": 0, "margins": [], "by_ability": defaultdict(
                lambda: {"success": 0, "total": 0, "margins": []}
            )}
        )

        # Stats by attribute
        self._attribute_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"success": 0, "total": 0, "margins": []}
        )

        # DC distribution
        self._dc_distribution: Counter = Counter()

        self._event_count = 0
        self._session_count = 0

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process an action_resolution event."""
        roll = event.get("roll", {})
        if not roll:
            return

        self._event_count += 1

        # Extract roll data
        attr = roll.get("attr", "Unknown")
        skill = roll.get("skill", "Unknown")
        attr_val = roll.get("attr_val", 0)
        skill_val = roll.get("skill_val", 0)
        ability = roll.get("ability", 0)  # Combined attr + skill
        success = roll.get("success", False)
        margin = roll.get("margin", 0)
        dc = roll.get("dc", self.dc_baseline)

        # Track attr x skill combo
        if skill and skill != "None":
            self._attr_skill_combos[(attr, skill)] += 1

        # Track by ability bucket
        bucket = get_ability_bucket(ability)
        self._ability_buckets[bucket]["total"] += 1
        if success:
            self._ability_buckets[bucket]["success"] += 1
        self._ability_buckets[bucket]["margins"].append(margin)

        # Track by skill
        if skill and skill != "None":
            self._skill_stats[skill]["total"] += 1
            if success:
                self._skill_stats[skill]["success"] += 1
            self._skill_stats[skill]["margins"].append(margin)

            # Track skill by ability level
            self._skill_stats[skill]["by_ability"][ability]["total"] += 1
            if success:
                self._skill_stats[skill]["by_ability"][ability]["success"] += 1
            self._skill_stats[skill]["by_ability"][ability]["margins"].append(margin)

        # Track by attribute
        self._attribute_stats[attr]["total"] += 1
        if success:
            self._attribute_stats[attr]["success"] += 1
        self._attribute_stats[attr]["margins"].append(margin)

        # Track DC distribution
        self._dc_distribution[dc] += 1

    def get_result(self) -> AnalyzerResult:
        """Produce final result with accumulated statistics."""
        warnings = []

        # Compute top attr x skill combos
        top_combos = []
        total_rolls = sum(self._attr_skill_combos.values())
        for (attr, skill), count in self._attr_skill_combos.most_common(20):
            pct = (count / total_rolls * 100) if total_rolls > 0 else 0
            top_combos.append({
                "attr": attr,
                "skill": skill,
                "count": count,
                "percentage": round(pct, 1),
            })

        # Compute ability bucket stats
        ability_bucket_stats = []
        bucket_order = [b[0] for b in ABILITY_BUCKETS]
        for bucket in bucket_order:
            if bucket in self._ability_buckets:
                stats = self._ability_buckets[bucket]
                if stats["total"] >= 5:  # Min sample size
                    success_rate = (stats["success"] / stats["total"]) * 100
                    avg_margin = statistics.mean(stats["margins"]) if stats["margins"] else 0

                    # Expected success rate for DC baseline
                    midpoint = BUCKET_MIDPOINTS.get(bucket, 10)
                    expected = calculate_expected_success(midpoint, self.dc_baseline)
                    delta = success_rate - expected

                    bucket_data = {
                        "bucket": bucket,
                        "success": stats["success"],
                        "total": stats["total"],
                        "success_rate": round(success_rate, 1),
                        "avg_margin": round(avg_margin, 1),
                        "expected_rate": round(expected, 1),
                        "delta": round(delta, 1),
                    }
                    ability_bucket_stats.append(bucket_data)

                    # Add warnings for extreme deviations
                    if abs(delta) > 15:
                        warnings.append(
                            f"Bucket '{bucket}' deviates {delta:+.1f}% from expected "
                            f"(observed {success_rate:.1f}%, expected {expected:.1f}%)"
                        )

        # Compute skill performance
        skill_performance = []
        for skill, stats in sorted(
            self._skill_stats.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )[:15]:  # Top 15 skills
            if stats["total"] >= 5:
                success_rate = (stats["success"] / stats["total"]) * 100
                avg_margin = statistics.mean(stats["margins"]) if stats["margins"] else 0

                skill_data = {
                    "skill": skill,
                    "success": stats["success"],
                    "total": stats["total"],
                    "success_rate": round(success_rate, 1),
                    "avg_margin": round(avg_margin, 1),
                }
                skill_performance.append(skill_data)

                # Warnings for extreme success rates
                if success_rate > 80:
                    warnings.append(f"Skill '{skill}' may be too easy ({success_rate:.1f}% success)")
                elif success_rate < 40:
                    warnings.append(f"Skill '{skill}' may be too hard ({success_rate:.1f}% success)")

        # Compute attribute usage
        attribute_usage = []
        for attr, stats in sorted(
            self._attribute_stats.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        ):
            if stats["total"] >= 10:
                success_rate = (stats["success"] / stats["total"]) * 100
                avg_margin = statistics.mean(stats["margins"]) if stats["margins"] else 0
                usage_pct = (stats["total"] / self._event_count * 100) if self._event_count > 0 else 0

                attribute_usage.append({
                    "attribute": attr,
                    "success": stats["success"],
                    "total": stats["total"],
                    "success_rate": round(success_rate, 1),
                    "avg_margin": round(avg_margin, 1),
                    "usage_percentage": round(usage_pct, 1),
                })

        return AnalyzerResult(
            analyzer_name=self.name,
            session_count=self._session_count,
            event_count=self._event_count,
            metrics={
                "dc_baseline": self.dc_baseline,
                "total_rolls": self._event_count,
                "attr_skill_combos": top_combos,
                "ability_buckets": ability_bucket_stats,
                "skill_performance": skill_performance,
                "attribute_usage": attribute_usage,
                "dc_distribution": dict(self._dc_distribution.most_common(10)),
            },
            warnings=warnings,
        )
