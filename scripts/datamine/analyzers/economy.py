"""
Economy analyzer - extract void, soulcredit, currency, and purchase data.

Metrics:
- Void gains/losses per round
- Soulcredit changes
- Energy currency (breath, grain, drip, spark, hollow) flow
- Purchase attempts (success/failure, items, costs)
- Item transfers
"""

from collections import Counter, defaultdict
from typing import Dict, Any, Set, List
import statistics

from .base import BaseAnalyzer, AnalyzerResult


# The 5 energy currency types
CURRENCY_TYPES = ["breath", "grain", "drip", "spark", "hollow"]


class EconomyAnalyzer(BaseAnalyzer):
    """
    Analyze the full game economy including void, soulcredit, and energy currencies.

    Processes multiple event types to extract:
    - Void trajectory per character
    - Soulcredit changes
    - Energy currency (breath, grain, drip, spark, hollow) spending/earning
    - Purchase attempts with success/failure analysis
    - Item purchase patterns
    """

    @property
    def name(self) -> str:
        return "economy"

    @property
    def event_types(self) -> Set[str]:
        return {
            "void_change",
            "character_state",
            "action_resolution",
            "round_start",
            "purchase_attempt",  # NEW: track purchases
        }

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Reset all accumulated state."""
        # Void tracking
        self._void_changes: List[int] = []
        self._void_by_faction: Dict[str, List[int]] = defaultdict(list)
        self._void_by_reason: Dict[str, List[int]] = defaultdict(list)
        self._character_void: Dict[str, List[int]] = defaultdict(list)

        # Soulcredit tracking
        self._soulcredit_changes: List[int] = []
        self._soulcredit_by_reason: Dict[str, List[int]] = defaultdict(list)
        self._character_soulcredit: Dict[str, List[int]] = defaultdict(list)

        # Energy currency tracking (NEW)
        self._currency_spent: Dict[str, int] = {c: 0 for c in CURRENCY_TYPES}
        self._currency_by_item: Dict[str, Dict[str, int]] = defaultdict(lambda: {c: 0 for c in CURRENCY_TYPES})

        # Purchase tracking (NEW)
        self._purchase_attempts: int = 0
        self._purchase_successes: int = 0
        self._purchase_failures: int = 0
        self._failure_reasons: Counter = Counter()
        self._items_purchased: Counter = Counter()
        self._items_failed: Counter = Counter()
        self._vendor_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"attempts": 0, "successes": 0})

        # Currency balance snapshots (from purchase_attempt events)
        self._currency_snapshots: List[Dict[str, int]] = []

        # Round tracking
        self._current_round = 0
        self._void_per_round: Dict[int, List[int]] = defaultdict(list)

        self._event_count = 0
        self._session_count = 0

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process economy events."""
        event_type = event.get("event_type")

        if event_type == "round_start":
            self._current_round = event.get("round", self._current_round + 1)
        elif event_type == "void_change":
            self._process_void_change(event)
        elif event_type == "character_state":
            self._process_character_state(event)
        elif event_type == "action_resolution":
            self._process_action_resolution(event)
        elif event_type == "purchase_attempt":
            self._process_purchase_attempt(event)

    def _process_void_change(self, event: Dict[str, Any]) -> None:
        """Process a void_change event."""
        self._event_count += 1

        delta = event.get("delta", event.get("void_delta", 0))
        reason = event.get("reason", "unknown")
        faction = event.get("faction", "unknown")

        if delta == 0:
            return

        self._void_changes.append(delta)
        self._void_by_faction[faction].append(delta)
        self._void_by_reason[reason].append(delta)
        self._void_per_round[self._current_round].append(delta)

    def _process_character_state(self, event: Dict[str, Any]) -> None:
        """Process a character_state event to track trajectories."""
        self._event_count += 1

        character = event.get("character_name", event.get("character_id", "unknown"))
        void_score = event.get("void_score")
        soulcredit = event.get("soulcredit")

        if void_score is not None:
            self._character_void[character].append(void_score)

        if soulcredit is not None:
            self._character_soulcredit[character].append(soulcredit)

    def _process_action_resolution(self, event: Dict[str, Any]) -> None:
        """Process action_resolution for embedded void/soulcredit changes."""
        effects = event.get("effects", {})

        # Process void_changes from effects
        void_changes = effects.get("void_changes")
        if void_changes:
            self._event_count += 1

            if isinstance(void_changes, int):
                self._void_changes.append(void_changes)
                faction = event.get("faction", "unknown")
                self._void_by_faction[faction].append(void_changes)
                self._void_per_round[self._current_round].append(void_changes)
            elif isinstance(void_changes, list):
                for vc in void_changes:
                    if isinstance(vc, dict):
                        delta = vc.get("amount", 0)
                        reason = vc.get("reason", "unknown")
                        if delta != 0:
                            self._void_changes.append(delta)
                            self._void_by_reason[reason].append(delta)
                            self._void_per_round[self._current_round].append(delta)
                    elif isinstance(vc, int):
                        self._void_changes.append(vc)
                        self._void_per_round[self._current_round].append(vc)

        # Process soulcredit_changes from effects
        sc_changes = effects.get("soulcredit_changes")
        if sc_changes:
            if isinstance(sc_changes, int):
                self._soulcredit_changes.append(sc_changes)
            elif isinstance(sc_changes, list):
                for sc in sc_changes:
                    if isinstance(sc, dict):
                        amount = sc.get("amount", 0)
                        reason = sc.get("reason", "unknown")
                        if amount != 0:
                            self._soulcredit_changes.append(amount)
                            self._soulcredit_by_reason[reason].append(amount)
                    elif isinstance(sc, int):
                        self._soulcredit_changes.append(sc)

    def _process_purchase_attempt(self, event: Dict[str, Any]) -> None:
        """Process a purchase_attempt event."""
        self._event_count += 1
        self._purchase_attempts += 1

        success = event.get("success", False)
        item_name = event.get("item_name", "unknown")
        vendor_name = event.get("vendor_name", "unknown")
        cost = event.get("cost", {})
        player_currency = event.get("player_currency", {})
        failure_reason = event.get("failure_reason")

        # Track vendor stats
        self._vendor_stats[vendor_name]["attempts"] += 1

        if success:
            self._purchase_successes += 1
            self._items_purchased[item_name] += 1
            self._vendor_stats[vendor_name]["successes"] += 1

            # Track currency spent by type
            for currency_type, amount in cost.items():
                if currency_type in CURRENCY_TYPES and amount:
                    self._currency_spent[currency_type] += amount
                    self._currency_by_item[item_name][currency_type] += amount
        else:
            self._purchase_failures += 1
            self._items_failed[item_name] += 1
            if failure_reason:
                self._failure_reasons[failure_reason] += 1

        # Snapshot currency balance
        if player_currency:
            self._currency_snapshots.append(player_currency)

    def get_result(self) -> AnalyzerResult:
        """Produce final result with economy statistics."""
        warnings = []

        # === VOID STATISTICS ===
        void_stats = {}
        if self._void_changes:
            void_stats = {
                "total_changes": len(self._void_changes),
                "avg_change": round(statistics.mean(self._void_changes), 2),
                "median_change": round(statistics.median(self._void_changes), 1),
                "total_gained": sum(v for v in self._void_changes if v > 0),
                "total_lost": abs(sum(v for v in self._void_changes if v < 0)),
                "max_gain": max(self._void_changes) if self._void_changes else 0,
                "max_loss": min(self._void_changes) if self._void_changes else 0,
            }
            void_dist = Counter(self._void_changes)
            void_stats["distribution"] = dict(sorted(void_dist.items()))

            if void_stats["avg_change"] > 1:
                warnings.append(f"Average void change is positive ({void_stats['avg_change']:+.2f}), characters accumulating void quickly")

        # Void by faction
        void_by_faction = {}
        for faction, changes in self._void_by_faction.items():
            if changes:
                void_by_faction[faction] = {
                    "count": len(changes),
                    "avg_change": round(statistics.mean(changes), 2),
                    "total": sum(changes),
                }

        # Void by reason
        void_by_reason = []
        for reason, changes in sorted(self._void_by_reason.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            if changes:
                void_by_reason.append({
                    "reason": reason,
                    "count": len(changes),
                    "avg_change": round(statistics.mean(changes), 2),
                    "total": sum(changes),
                })

        # === SOULCREDIT STATISTICS ===
        soulcredit_stats = {}
        if self._soulcredit_changes:
            soulcredit_stats = {
                "total_changes": len(self._soulcredit_changes),
                "avg_change": round(statistics.mean(self._soulcredit_changes), 2),
                "total_gained": sum(v for v in self._soulcredit_changes if v > 0),
                "total_lost": abs(sum(v for v in self._soulcredit_changes if v < 0)),
            }
            sc_dist = Counter(self._soulcredit_changes)
            soulcredit_stats["distribution"] = dict(sorted(sc_dist.items()))

        # === PURCHASE STATISTICS (NEW) ===
        purchase_stats = {}
        if self._purchase_attempts > 0:
            success_rate = (self._purchase_successes / self._purchase_attempts) * 100
            purchase_stats = {
                "total_attempts": self._purchase_attempts,
                "successes": self._purchase_successes,
                "failures": self._purchase_failures,
                "success_rate": round(success_rate, 1),
            }

            # Warning for low success rate
            if success_rate < 50 and self._purchase_attempts >= 10:
                warnings.append(f"Purchase success rate is low ({success_rate:.1f}%), players may be currency-starved")

        # Failure reasons breakdown
        failure_breakdown = []
        for reason, count in self._failure_reasons.most_common(10):
            failure_breakdown.append({
                "reason": reason,
                "count": count,
                "percentage": round((count / self._purchase_failures) * 100, 1) if self._purchase_failures > 0 else 0,
            })

        # === CURRENCY STATISTICS (NEW) ===
        currency_stats = {
            "total_spent": dict(self._currency_spent),
            "total_all": sum(self._currency_spent.values()),
        }

        # Average currency held (from snapshots)
        if self._currency_snapshots:
            avg_held = {}
            for currency in CURRENCY_TYPES:
                values = [s.get(currency, 0) for s in self._currency_snapshots if currency in s]
                if values:
                    avg_held[currency] = round(statistics.mean(values), 1)
            currency_stats["avg_held"] = avg_held

        # Currency spent by type (sorted by amount)
        currency_breakdown = []
        for currency, amount in sorted(self._currency_spent.items(), key=lambda x: x[1], reverse=True):
            if amount > 0:
                currency_breakdown.append({
                    "currency": currency,
                    "spent": amount,
                    "percentage": round((amount / currency_stats["total_all"]) * 100, 1) if currency_stats["total_all"] > 0 else 0,
                })

        # === ITEMS STATISTICS (NEW) ===
        items_purchased = []
        for item, count in self._items_purchased.most_common(15):
            cost_breakdown = self._currency_by_item.get(item, {})
            items_purchased.append({
                "item": item,
                "count": count,
                "total_cost": {k: v for k, v in cost_breakdown.items() if v > 0},
            })

        items_failed = []
        for item, count in self._items_failed.most_common(10):
            items_failed.append({
                "item": item,
                "failed_attempts": count,
            })

        # === VENDOR STATISTICS (NEW) ===
        vendor_stats = []
        for vendor, stats in sorted(self._vendor_stats.items(), key=lambda x: x[1]["attempts"], reverse=True)[:10]:
            rate = (stats["successes"] / stats["attempts"]) * 100 if stats["attempts"] > 0 else 0
            vendor_stats.append({
                "vendor": vendor,
                "attempts": stats["attempts"],
                "successes": stats["successes"],
                "success_rate": round(rate, 1),
            })

        # === CHARACTER TRAJECTORIES ===
        character_summaries = []
        for char, void_scores in self._character_void.items():
            if len(void_scores) >= 2:
                sc_scores = self._character_soulcredit.get(char, [])
                summary = {
                    "character": char,
                    "void_start": void_scores[0],
                    "void_end": void_scores[-1],
                    "void_delta": void_scores[-1] - void_scores[0],
                    "void_max": max(void_scores),
                }
                if sc_scores:
                    summary["soulcredit_start"] = sc_scores[0]
                    summary["soulcredit_end"] = sc_scores[-1]
                    summary["soulcredit_delta"] = sc_scores[-1] - sc_scores[0]
                character_summaries.append(summary)

        return AnalyzerResult(
            analyzer_name=self.name,
            session_count=self._session_count,
            event_count=self._event_count,
            metrics={
                # Void
                "void": void_stats,
                "void_by_faction": void_by_faction,
                "void_by_reason": void_by_reason,
                # Soulcredit
                "soulcredit": soulcredit_stats,
                # Purchases (NEW)
                "purchases": purchase_stats,
                "failure_reasons": failure_breakdown,
                # Currency (NEW)
                "currency": currency_stats,
                "currency_breakdown": currency_breakdown,
                # Items (NEW)
                "items_purchased": items_purchased,
                "items_failed": items_failed,
                # Vendors (NEW)
                "vendor_stats": vendor_stats,
                # Character summaries
                "character_summaries": character_summaries[:20],
            },
            warnings=warnings,
        )
