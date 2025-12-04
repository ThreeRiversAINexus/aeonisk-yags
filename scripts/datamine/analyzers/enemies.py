"""
Enemies analyzer - extract enemy spawn/defeat statistics.

Metrics:
- Spawn counts by template
- Survival rounds
- Defeat reasons
- Enemy stat distributions
"""

from collections import Counter, defaultdict
from typing import Dict, Any, Set, List, Optional
import statistics

from .base import BaseAnalyzer, AnalyzerResult


class EnemiesAnalyzer(BaseAnalyzer):
    """
    Analyze enemy lifecycle and effectiveness.

    Processes enemy_spawn and enemy_defeat events to extract:
    - Spawn patterns by template
    - Survival duration
    - Defeat causes
    - Enemy stat distributions
    """

    @property
    def name(self) -> str:
        return "enemies"

    @property
    def event_types(self) -> Set[str]:
        return {"enemy_spawn", "enemy_defeat", "round_start"}

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Reset all accumulated state."""
        # Track spawns by template
        self._template_spawns: Counter = Counter()

        # Track enemy stats at spawn
        self._enemy_stats: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # Track active enemies for survival calculation
        self._active_enemies: Dict[str, Dict[str, Any]] = {}

        # Defeat tracking
        self._defeat_reasons: Counter = Counter()
        self._survival_rounds: Dict[str, List[int]] = defaultdict(list)

        # Current round
        self._current_round = 0

        self._event_count = 0
        self._session_count = 0

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process enemy lifecycle events."""
        event_type = event.get("event_type")

        if event_type == "round_start":
            self._current_round = event.get("round", self._current_round + 1)
        elif event_type == "enemy_spawn":
            self._process_spawn(event)
        elif event_type == "enemy_defeat":
            self._process_defeat(event)

    def _process_spawn(self, event: Dict[str, Any]) -> None:
        """Process an enemy_spawn event."""
        self._event_count += 1

        enemy_id = event.get("enemy_id")
        template = event.get("template", "unknown")
        stats = event.get("stats", {})
        round_spawned = event.get("round", self._current_round)

        # Track spawn
        self._template_spawns[template] += 1

        # Store stats for template analysis
        self._enemy_stats[template].append({
            "health": stats.get("health", stats.get("max_health", 0)),
            "soak": stats.get("soak", 0),
            "tactics": event.get("tactics", "unknown"),
        })

        # Track active enemy for survival calculation
        if enemy_id:
            self._active_enemies[enemy_id] = {
                "template": template,
                "spawn_round": round_spawned,
            }

    def _process_defeat(self, event: Dict[str, Any]) -> None:
        """Process an enemy_defeat event."""
        self._event_count += 1

        enemy_id = event.get("enemy_id")
        defeat_reason = event.get("defeat_reason", "unknown")
        round_defeated = event.get("round", self._current_round)
        rounds_survived = event.get("rounds_survived")

        # Track defeat reason
        self._defeat_reasons[defeat_reason] += 1

        # Calculate survival if we tracked this enemy
        template = "unknown"
        if enemy_id and enemy_id in self._active_enemies:
            enemy_data = self._active_enemies[enemy_id]
            template = enemy_data["template"]

            # Use provided rounds_survived or calculate
            if rounds_survived is None:
                rounds_survived = round_defeated - enemy_data["spawn_round"]

            del self._active_enemies[enemy_id]
        elif rounds_survived is None:
            rounds_survived = 0

        # Track survival by template
        self._survival_rounds[template].append(rounds_survived)

    def get_result(self) -> AnalyzerResult:
        """Produce final result with enemy statistics."""
        warnings = []

        # Template spawn statistics
        template_stats = []
        total_spawns = sum(self._template_spawns.values())

        for template, count in self._template_spawns.most_common():
            spawn_pct = (count / total_spawns * 100) if total_spawns > 0 else 0

            # Compute average stats for this template
            stats_list = self._enemy_stats.get(template, [])
            avg_health = statistics.mean([s["health"] for s in stats_list]) if stats_list else 0
            avg_soak = statistics.mean([s["soak"] for s in stats_list]) if stats_list else 0

            # Survival stats
            survival = self._survival_rounds.get(template, [])
            avg_survival = statistics.mean(survival) if survival else 0
            max_survival = max(survival) if survival else 0

            template_data = {
                "template": template,
                "spawn_count": count,
                "spawn_percentage": round(spawn_pct, 1),
                "avg_health": round(avg_health, 1),
                "avg_soak": round(avg_soak, 1),
                "avg_survival_rounds": round(avg_survival, 1),
                "max_survival_rounds": max_survival,
                "defeats": len(survival),
            }
            template_stats.append(template_data)

            # Warnings for templates that survive too long or too short
            if avg_survival > 5 and len(survival) >= 3:
                warnings.append(f"Template '{template}' survives {avg_survival:.1f} rounds on average (may be too tanky)")
            elif avg_survival < 1 and len(survival) >= 5:
                warnings.append(f"Template '{template}' survives {avg_survival:.1f} rounds on average (may be too weak)")

        # Defeat reason breakdown
        defeat_breakdown = []
        total_defeats = sum(self._defeat_reasons.values())
        for reason, count in self._defeat_reasons.most_common():
            pct = (count / total_defeats * 100) if total_defeats > 0 else 0
            defeat_breakdown.append({
                "reason": reason,
                "count": count,
                "percentage": round(pct, 1),
            })

        # Overall survival distribution
        all_survival = []
        for rounds_list in self._survival_rounds.values():
            all_survival.extend(rounds_list)

        survival_distribution = {}
        if all_survival:
            survival_distribution = {
                "avg": round(statistics.mean(all_survival), 1),
                "median": round(statistics.median(all_survival), 1),
                "min": min(all_survival),
                "max": max(all_survival),
            }

        return AnalyzerResult(
            analyzer_name=self.name,
            session_count=self._session_count,
            event_count=self._event_count,
            metrics={
                "total_spawns": total_spawns,
                "total_defeats": total_defeats,
                "still_active": len(self._active_enemies),
                "template_stats": template_stats,
                "defeat_breakdown": defeat_breakdown,
                "survival_distribution": survival_distribution,
            },
            warnings=warnings,
        )
