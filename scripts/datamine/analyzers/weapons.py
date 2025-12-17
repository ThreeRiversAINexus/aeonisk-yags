"""
Weapons analyzer - extract weapon effectiveness and damage metrics.

Metrics:
- Hit rates by weapon
- Average damage per weapon
- Weapon usage frequency
- Time-to-kill estimates
"""

from collections import Counter, defaultdict
from typing import Dict, Any, Set, List
import statistics

from .base import BaseAnalyzer, AnalyzerResult


class WeaponsAnalyzer(BaseAnalyzer):
    """
    Analyze weapon effectiveness from combat events.

    Processes combat_action and action_resolution events to extract:
    - Weapon hit rates
    - Damage per weapon
    - Kill tracking
    - Faction-specific weapon usage
    """

    @property
    def name(self) -> str:
        return "weapons"

    @property
    def event_types(self) -> Set[str]:
        return {"combat_action", "action_resolution", "enemy_defeat"}

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Reset all accumulated state."""
        # Weapon stats: hits, total attempts, damage values
        self._weapon_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"hits": 0, "total": 0, "damage": [], "kills": 0}
        )

        # Weapon by faction
        self._weapon_by_faction: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"hits": 0, "total": 0})
        )

        # Track defeats to attribute kills
        self._recent_attacks: List[Dict[str, Any]] = []

        self._event_count = 0
        self._session_count = 0

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process combat events."""
        event_type = event.get("event_type")

        if event_type == "combat_action":
            self._process_combat_action(event)
        elif event_type == "action_resolution":
            self._process_action_resolution(event)
        elif event_type == "enemy_defeat":
            self._process_defeat(event)

    def _process_combat_action(self, event: Dict[str, Any]) -> None:
        """Process a combat_action event."""
        self._event_count += 1

        weapon = event.get("weapon", "unknown")
        # Hit is nested inside attack dict
        attack = event.get("attack", {})
        hit = attack.get("hit", False) if isinstance(attack, dict) else False
        damage = event.get("damage", {})
        damage_dealt = damage.get("dealt", 0) if isinstance(damage, dict) else 0
        # Get attacker info for faction
        attacker = event.get("attacker", {})
        faction = attacker.get("faction", event.get("attacker_faction", "unknown")) if isinstance(attacker, dict) else "unknown"

        # Update weapon stats
        self._weapon_stats[weapon]["total"] += 1
        if hit:
            self._weapon_stats[weapon]["hits"] += 1
            if damage_dealt > 0:
                self._weapon_stats[weapon]["damage"].append(damage_dealt)

        # Track by faction
        self._weapon_by_faction[faction][weapon]["total"] += 1
        if hit:
            self._weapon_by_faction[faction][weapon]["hits"] += 1

        # Store for kill attribution
        if hit and damage_dealt > 0:
            defender = event.get("defender", {})
            target_id = defender.get("id") if isinstance(defender, dict) else event.get("defender_id", event.get("target"))
            self._recent_attacks.append({
                "weapon": weapon,
                "target": target_id,
                "damage": damage_dealt,
            })
            # Keep only recent attacks
            if len(self._recent_attacks) > 100:
                self._recent_attacks = self._recent_attacks[-50:]

    def _process_action_resolution(self, event: Dict[str, Any]) -> None:
        """Process action_resolution for attack actions."""
        # Check if this is a combat action
        effects = event.get("effects", {})
        damage = effects.get("damage", {})

        if not damage:
            return

        damage_dealt = damage.get("dealt", 0)
        if damage_dealt <= 0:
            return

        self._event_count += 1

        # Try to extract weapon from narration or use generic
        weapon = event.get("weapon", "attack")
        target = event.get("target")

        # Update weapon stats
        self._weapon_stats[weapon]["total"] += 1
        self._weapon_stats[weapon]["hits"] += 1
        self._weapon_stats[weapon]["damage"].append(damage_dealt)

        # Store for kill attribution
        self._recent_attacks.append({
            "weapon": weapon,
            "target": target,
            "damage": damage_dealt,
        })

    def _process_defeat(self, event: Dict[str, Any]) -> None:
        """Process enemy_defeat to attribute kills."""
        defeated_id = event.get("enemy_id")
        defeat_reason = event.get("defeat_reason", "")

        # Try to attribute kill to recent attack
        if defeat_reason in ("killed", "defeated") and self._recent_attacks:
            for attack in reversed(self._recent_attacks):
                if attack.get("target") == defeated_id:
                    weapon = attack["weapon"]
                    self._weapon_stats[weapon]["kills"] += 1
                    break

    def get_result(self) -> AnalyzerResult:
        """Produce final result with weapon statistics."""
        warnings = []

        # Compute weapon effectiveness
        weapon_effectiveness = []
        for weapon, stats in sorted(
            self._weapon_stats.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        ):
            if stats["total"] >= 3:  # Min sample size
                hit_rate = (stats["hits"] / stats["total"]) * 100
                avg_damage = statistics.mean(stats["damage"]) if stats["damage"] else 0
                max_damage = max(stats["damage"]) if stats["damage"] else 0
                total_damage = sum(stats["damage"])

                weapon_data = {
                    "weapon": weapon,
                    "hits": stats["hits"],
                    "total": stats["total"],
                    "hit_rate": round(hit_rate, 1),
                    "avg_damage": round(avg_damage, 1),
                    "max_damage": max_damage,
                    "total_damage": total_damage,
                    "kills": stats["kills"],
                }
                weapon_effectiveness.append(weapon_data)

                # Balance warnings
                if hit_rate > 75 and stats["total"] >= 10:
                    warnings.append(f"Weapon '{weapon}' may be overpowered ({hit_rate:.1f}% hit rate)")
                elif hit_rate < 45 and stats["total"] >= 10:
                    warnings.append(f"Weapon '{weapon}' may be underpowered ({hit_rate:.1f}% hit rate)")

        # Weapon by faction summary
        faction_weapons = {}
        for faction, weapons in self._weapon_by_faction.items():
            faction_data = []
            for weapon, stats in sorted(weapons.items(), key=lambda x: x[1]["total"], reverse=True)[:5]:
                if stats["total"] >= 2:
                    hit_rate = (stats["hits"] / stats["total"]) * 100
                    faction_data.append({
                        "weapon": weapon,
                        "total": stats["total"],
                        "hit_rate": round(hit_rate, 1),
                    })
            if faction_data:
                faction_weapons[faction] = faction_data

        # Overall statistics
        total_attacks = sum(s["total"] for s in self._weapon_stats.values())
        total_hits = sum(s["hits"] for s in self._weapon_stats.values())
        total_damage = sum(sum(s["damage"]) for s in self._weapon_stats.values())
        total_kills = sum(s["kills"] for s in self._weapon_stats.values())
        overall_hit_rate = (total_hits / total_attacks * 100) if total_attacks > 0 else 0

        return AnalyzerResult(
            analyzer_name=self.name,
            session_count=self._session_count,
            event_count=self._event_count,
            metrics={
                "total_attacks": total_attacks,
                "total_hits": total_hits,
                "total_damage": total_damage,
                "total_kills": total_kills,
                "overall_hit_rate": round(overall_hit_rate, 1),
                "weapon_effectiveness": weapon_effectiveness,
                "faction_weapons": faction_weapons,
            },
            warnings=warnings,
        )
