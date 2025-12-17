"""
Terminal formatter - rich terminal output with tables.
"""

from typing import IO, List, Dict, Any
from ..analyzers.base import AnalyzerResult
from .base import OutputFormatter


class TerminalFormatter(OutputFormatter):
    """Rich terminal output with tables and visual indicators."""

    @property
    def format_name(self) -> str:
        return "terminal"

    def format(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Write formatted result to output stream."""
        # Header
        output.write(f"\n{'=' * 70}\n")
        output.write(f"{result.analyzer_name.upper()} ANALYSIS\n")
        output.write(f"{'=' * 70}\n")
        output.write(f"Sessions: {result.session_count} | Events: {result.event_count}\n")

        # Dispatch to analyzer-specific formatter
        method = getattr(self, f'_format_{result.analyzer_name}', self._format_generic)
        method(result.metrics, output)

        # Warnings
        if result.warnings:
            output.write(f"\n{'-' * 40}\n")
            output.write("WARNINGS:\n")
            for warning in result.warnings[:10]:
                output.write(f"  - {warning}\n")
            if len(result.warnings) > 10:
                output.write(f"  ... and {len(result.warnings) - 10} more warnings\n")

    def _format_generic(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Generic formatter for unknown analyzer types."""
        import json
        output.write("\nMetrics:\n")
        output.write(json.dumps(metrics, indent=2, default=str)[:2000])
        if len(str(metrics)) > 2000:
            output.write("\n... (truncated)")
        output.write("\n")

    def _format_skills(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Format skills analyzer output."""
        # Attr x Skill combinations
        combos = metrics.get("attr_skill_combos", [])
        if combos:
            output.write(f"\nTop Attr x Skill Combinations ({metrics.get('total_rolls', 0):,} rolls):\n")
            output.write(f"{'Attribute':<15} {'Skill':<20} {'Count':>8} {'%':>8}\n")
            output.write("-" * 55 + "\n")
            for combo in combos[:15]:
                output.write(
                    f"{combo['attr']:<15} {combo['skill']:<20} {combo['count']:>8,} "
                    f"{combo['percentage']:>7.1f}%\n"
                )

        # Ability buckets with DC calibration
        buckets = metrics.get("ability_buckets", [])
        if buckets:
            output.write(f"\nSuccess Rate by Ability Level (DC {metrics.get('dc_baseline', 18)}):\n")
            output.write(f"{'Bucket':<20} {'Success':>12} {'Rate':>8} {'Expected':>10} {'Delta':>8} {'Margin':>8}\n")
            output.write("-" * 70 + "\n")
            for bucket in buckets:
                delta_str = f"{bucket['delta']:+.1f}%"
                if abs(bucket['delta']) > 15:
                    delta_str += " !"
                output.write(
                    f"{bucket['bucket']:<20} "
                    f"{bucket['success']:>4}/{bucket['total']:<5} "
                    f"{bucket['success_rate']:>6.1f}% "
                    f"{bucket['expected_rate']:>9.1f}% "
                    f"{delta_str:>8} "
                    f"{bucket['avg_margin']:>+7.1f}\n"
                )

        # Skill performance
        skills = metrics.get("skill_performance", [])
        if skills:
            output.write(f"\nSkill Performance:\n")
            output.write(f"{'Skill':<20} {'Success':>12} {'Rate':>8} {'Margin':>10}\n")
            output.write("-" * 55 + "\n")
            for skill in skills[:10]:
                status = ""
                if skill['success_rate'] > 80:
                    status = " (easy)"
                elif skill['success_rate'] < 40:
                    status = " (hard)"
                output.write(
                    f"{skill['skill']:<20} "
                    f"{skill['success']:>4}/{skill['total']:<5} "
                    f"{skill['success_rate']:>6.1f}% "
                    f"{skill['avg_margin']:>+9.1f}{status}\n"
                )

        # Attribute usage
        attrs = metrics.get("attribute_usage", [])
        if attrs:
            output.write(f"\nAttribute Usage:\n")
            output.write(f"{'Attribute':<15} {'Usage':>8} {'Rate':>8} {'Margin':>10}\n")
            output.write("-" * 45 + "\n")
            for attr in attrs:
                if attr and attr.get('attribute'):
                    output.write(
                        f"{attr['attribute']:<15} "
                        f"{attr.get('usage_percentage', 0):>6.1f}% "
                        f"{attr.get('success_rate', 0):>6.1f}% "
                        f"{attr.get('avg_margin', 0):>+9.1f}\n"
                    )

    def _format_weapons(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Format weapons analyzer output."""
        # Overall stats
        output.write(f"\nOverall: {metrics.get('total_attacks', 0):,} attacks, ")
        output.write(f"{metrics.get('total_hits', 0):,} hits ")
        output.write(f"({metrics.get('overall_hit_rate', 0):.1f}%), ")
        output.write(f"{metrics.get('total_damage', 0):,} damage, ")
        output.write(f"{metrics.get('total_kills', 0)} kills\n")

        # Weapon effectiveness
        weapons = metrics.get("weapon_effectiveness", [])
        if weapons:
            output.write(f"\nWeapon Effectiveness:\n")
            output.write(f"{'Weapon':<25} {'Hits':>10} {'Rate':>8} {'Avg Dmg':>10} {'Kills':>8}\n")
            output.write("-" * 65 + "\n")
            for w in weapons[:15]:
                status = ""
                if w['hit_rate'] > 75:
                    status = " OP?"
                elif w['hit_rate'] < 45:
                    status = " weak?"
                output.write(
                    f"{w['weapon'][:24]:<25} "
                    f"{w['hits']:>3}/{w['total']:<4} "
                    f"{w['hit_rate']:>6.1f}% "
                    f"{w['avg_damage']:>9.1f} "
                    f"{w['kills']:>8}{status}\n"
                )

        # Faction weapons
        faction_weapons = metrics.get("faction_weapons", {})
        if faction_weapons:
            output.write(f"\nWeapons by Faction:\n")
            for faction, weapons in list(faction_weapons.items())[:5]:
                output.write(f"  {faction}:\n")
                for w in weapons[:3]:
                    output.write(f"    - {w['weapon']}: {w['total']} uses, {w['hit_rate']:.1f}% hit\n")

    def _format_enemies(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Format enemies analyzer output."""
        output.write(f"\nTotal: {metrics.get('total_spawns', 0)} spawned, ")
        output.write(f"{metrics.get('total_defeats', 0)} defeated, ")
        output.write(f"{metrics.get('still_active', 0)} still active\n")

        # Template stats
        templates = metrics.get("template_stats", [])
        if templates:
            output.write(f"\nEnemy Templates:\n")
            output.write(f"{'Template':<20} {'Spawns':>8} {'HP':>8} {'Soak':>6} {'Survival':>10} {'Defeats':>8}\n")
            output.write("-" * 65 + "\n")
            for t in templates[:15]:
                output.write(
                    f"{t['template'][:19]:<20} "
                    f"{t['spawn_count']:>8} "
                    f"{t['avg_health']:>7.0f} "
                    f"{t['avg_soak']:>5.0f} "
                    f"{t['avg_survival_rounds']:>9.1f}r "
                    f"{t['defeats']:>8}\n"
                )

        # Defeat breakdown
        defeats = metrics.get("defeat_breakdown", [])
        if defeats:
            output.write(f"\nDefeat Reasons:\n")
            for d in defeats[:5]:
                bar = "#" * min(30, int(d['percentage'] / 3))
                output.write(f"  {d['reason']:<15} {bar} {d['count']:>4} ({d['percentage']:.1f}%)\n")

        # Survival distribution
        survival = metrics.get("survival_distribution", {})
        if survival:
            output.write(f"\nSurvival Distribution:\n")
            output.write(f"  Avg: {survival.get('avg', 0):.1f} rounds | ")
            output.write(f"Median: {survival.get('median', 0):.1f} | ")
            output.write(f"Range: {survival.get('min', 0)}-{survival.get('max', 0)} rounds\n")

    def _format_economy(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Format economy analyzer output."""
        # === PURCHASES & CURRENCY (NEW) ===
        purchases = metrics.get("purchases", {})
        if purchases:
            output.write(f"\nPurchase Activity:\n")
            output.write(f"  Attempts: {purchases.get('total_attempts', 0)} | ")
            output.write(f"Success: {purchases.get('successes', 0)} | ")
            output.write(f"Failed: {purchases.get('failures', 0)} | ")
            output.write(f"Rate: {purchases.get('success_rate', 0):.1f}%\n")

        # Failure reasons
        failure_reasons = metrics.get("failure_reasons", [])
        if failure_reasons:
            output.write(f"\n  Failure Reasons:\n")
            for r in failure_reasons[:5]:
                output.write(f"    {r['reason']:<30} {r['count']:>4} ({r['percentage']:.1f}%)\n")

        # Currency breakdown
        currency = metrics.get("currency", {})
        currency_breakdown = metrics.get("currency_breakdown", [])
        if currency_breakdown:
            output.write(f"\nEnergy Currency Spent (total: {currency.get('total_all', 0)}):\n")
            for c in currency_breakdown:
                bar = "#" * min(30, c['spent'] // 5)
                output.write(f"  {c['currency']:<10} {bar} {c['spent']:>6} ({c['percentage']:.1f}%)\n")

        # Average held
        avg_held = currency.get("avg_held", {})
        if avg_held:
            output.write(f"\n  Avg Currency Held: ")
            parts = [f"{k}={v:.0f}" for k, v in avg_held.items() if v > 0]
            output.write(", ".join(parts) + "\n")

        # Items purchased
        items_purchased = metrics.get("items_purchased", [])
        if items_purchased:
            output.write(f"\nTop Items Purchased:\n")
            output.write(f"{'Item':<35} {'Count':>6} {'Cost':>25}\n")
            output.write("-" * 70 + "\n")
            for item in items_purchased[:10]:
                cost_parts = [f"{k}:{v}" for k, v in item.get('total_cost', {}).items() if v > 0]
                cost_str = ", ".join(cost_parts) if cost_parts else "free"
                output.write(f"{item['item'][:34]:<35} {item['count']:>6} {cost_str:>25}\n")

        # Items failed
        items_failed = metrics.get("items_failed", [])
        if items_failed:
            output.write(f"\nItems Players Couldn't Afford:\n")
            for item in items_failed[:5]:
                output.write(f"  {item['item']:<35} {item['failed_attempts']} failed attempts\n")

        # Vendor stats
        vendor_stats = metrics.get("vendor_stats", [])
        if vendor_stats:
            output.write(f"\nVendor Performance:\n")
            for v in vendor_stats[:5]:
                output.write(f"  {v['vendor'][:30]:<32} {v['successes']}/{v['attempts']} ({v['success_rate']:.0f}%)\n")

        # === VOID STATISTICS ===
        void = metrics.get("void", {})
        if void:
            output.write(f"\nVoid Economy ({void.get('total_changes', 0)} changes):\n")
            output.write(f"  Avg change: {void.get('avg_change', 0):+.2f} | ")
            output.write(f"Gained: +{void.get('total_gained', 0)} | ")
            output.write(f"Lost: {void.get('total_lost', 0)}\n")

            # Distribution
            dist = void.get("distribution", {})
            if dist:
                output.write(f"\n  Void Change Distribution:\n")
                for change, count in sorted(dist.items(), key=lambda x: int(x[0]))[:10]:
                    bar = "#" * min(40, count)
                    output.write(f"    {int(change):+2d}: {bar} ({count})\n")

        # Void by reason
        by_reason = metrics.get("void_by_reason", [])
        if by_reason:
            output.write(f"\nVoid by Reason:\n")
            for r in by_reason[:5]:
                output.write(f"  {r['reason']:<25} avg {r['avg_change']:+.2f} ({r['count']} events)\n")

        # === SOULCREDIT STATISTICS ===
        sc = metrics.get("soulcredit", {})
        if sc:
            output.write(f"\nSoulcredit Economy ({sc.get('total_changes', 0)} changes):\n")
            output.write(f"  Avg change: {sc.get('avg_change', 0):+.2f} | ")
            output.write(f"Gained: +{sc.get('total_gained', 0)} | ")
            output.write(f"Lost: {sc.get('total_lost', 0)}\n")

        # Character summaries
        summaries = metrics.get("character_summaries", [])
        if summaries:
            output.write(f"\nCharacter Economy Trajectories:\n")
            output.write(f"{'Character':<30} {'Void':>15} {'SC':>15}\n")
            output.write("-" * 65 + "\n")
            for s in summaries[:10]:
                void_str = f"{s.get('void_start', 0)}->{s.get('void_end', 0)} ({s.get('void_delta', 0):+d})"
                sc_delta = s.get('soulcredit_delta')
                sc_str = f"{s.get('soulcredit_start', '?')}->{s.get('soulcredit_end', '?')} ({sc_delta:+d})" if sc_delta is not None else "n/a"
                output.write(f"{s['character'][:29]:<30} {void_str:>15} {sc_str:>15}\n")

    def _format_targeting(self, metrics: Dict[str, Any], output: IO[str]) -> None:
        """Format targeting analyzer output."""
        # Summary stats
        total_decl = metrics.get("total_declarations", 0)
        total_combat = metrics.get("total_combat_actions", 0)
        output.write(f"\nTotal: {total_decl} declarations, {total_combat} combat actions\n")

        # Issues summary
        bracketed = metrics.get("bracketed_targets", 0)
        name_as_target = metrics.get("name_as_target", 0)
        env_targets = metrics.get("env_targets", 0)
        unknown_weapons = metrics.get("unknown_weapons", 0)
        missing_defenders = metrics.get("missing_defenders", 0)

        if bracketed or name_as_target or env_targets or unknown_weapons or missing_defenders:
            output.write(f"\nTargeting Issues Found:\n")
            if bracketed:
                output.write(f"  - Bracketed target IDs ([tgt_xxx]): {bracketed}\n")
            if name_as_target:
                output.write(f"  - Character names as targets: {name_as_target}\n")
            if env_targets:
                output.write(f"  - Environment targets (env_xxx): {env_targets}\n")
            if unknown_weapons:
                pct = (unknown_weapons / total_combat * 100) if total_combat > 0 else 0
                output.write(f"  - Unknown weapons: {unknown_weapons} ({pct:.1f}%)\n")
            if missing_defenders:
                output.write(f"  - Missing defenders: {missing_defenders}\n")

        # Target pattern breakdown
        patterns = metrics.get("target_patterns", [])
        if patterns:
            output.write(f"\nTarget ID Patterns:\n")
            output.write(f"{'Pattern':<25} {'Count':>10} {'%':>8}\n")
            output.write("-" * 45 + "\n")
            for p in patterns[:10]:
                status = ""
                if p['pattern'] in ('bracketed_tgt_id', 'name_as_target'):
                    status = " ⚠"
                output.write(f"{p['pattern']:<25} {p['count']:>10,} {p['percentage']:>7.1f}%{status}\n")

        # Defender pattern breakdown
        defender_patterns = metrics.get("defender_patterns", [])
        if defender_patterns:
            output.write(f"\nDefender ID Patterns:\n")
            output.write(f"{'Pattern':<25} {'Count':>10} {'%':>8}\n")
            output.write("-" * 45 + "\n")
            for p in defender_patterns[:8]:
                output.write(f"{p['pattern']:<25} {p['count']:>10,} {p['percentage']:>7.1f}%\n")

        # Sample issues
        sample_bracketed = metrics.get("sample_bracketed", [])
        if sample_bracketed:
            output.write(f"\nSample Bracketed Targets:\n")
            for s in sample_bracketed[:5]:
                output.write(f"  {s['character']}: {s['target']} (session {s['session']}, round {s['round']})\n")

        sample_names = metrics.get("sample_name_as_target", [])
        if sample_names:
            output.write(f"\nSample Name-as-Target:\n")
            for s in sample_names[:5]:
                output.write(f"  {s['character']}: \"{s['target']}\" (session {s['session']}, round {s['round']})\n")

        # Validation warnings
        val_warnings = metrics.get("validation_warnings", [])
        if val_warnings:
            output.write(f"\nTop Validation Warnings:\n")
            for w in val_warnings[:8]:
                output.write(f"  [{w['count']:>3}x] {w['warning'][:70]}\n")
