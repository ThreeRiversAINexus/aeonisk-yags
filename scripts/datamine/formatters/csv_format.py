"""
CSV formatter - flat CSV output for spreadsheet analysis.
"""

import csv
from typing import IO, List, Dict, Any
from ..analyzers.base import AnalyzerResult
from .base import OutputFormatter


class CSVFormatter(OutputFormatter):
    """CSV export for spreadsheet analysis."""

    @property
    def format_name(self) -> str:
        return "csv"

    def format(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Write CSV formatted result to output stream."""
        # Dispatch to analyzer-specific CSV formatter
        method = getattr(self, f'_format_{result.analyzer_name}', self._format_generic)
        method(result, output)

    def _format_generic(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Generic CSV formatter - flattens metrics into rows."""
        rows = self._flatten_metrics(result.metrics, result.analyzer_name)
        if not rows:
            return

        # Write CSV
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    def _flatten_metrics(self, metrics: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
        """Flatten nested metrics into CSV rows."""
        rows = []

        for key, value in metrics.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                # List of dicts - each becomes a row
                for item in value:
                    row = {"category": key}
                    row.update(item)
                    rows.append(row)
            elif isinstance(value, dict) and not any(isinstance(v, (list, dict)) for v in value.values()):
                # Flat dict - becomes a single row
                row = {"category": key}
                row.update(value)
                rows.append(row)

        return rows

    def _format_skills(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Format skills analyzer as CSV."""
        metrics = result.metrics

        # Attr x Skill combos table
        combos = metrics.get("attr_skill_combos", [])
        if combos:
            output.write("# Attribute x Skill Combinations\n")
            writer = csv.DictWriter(output, fieldnames=["attr", "skill", "count", "percentage"])
            writer.writeheader()
            writer.writerows(combos)
            output.write("\n")

        # Ability buckets table
        buckets = metrics.get("ability_buckets", [])
        if buckets:
            output.write("# Success Rate by Ability Bucket\n")
            writer = csv.DictWriter(output, fieldnames=[
                "bucket", "success", "total", "success_rate", "expected_rate", "delta", "avg_margin"
            ])
            writer.writeheader()
            writer.writerows(buckets)
            output.write("\n")

        # Skill performance table
        skills = metrics.get("skill_performance", [])
        if skills:
            output.write("# Skill Performance\n")
            writer = csv.DictWriter(output, fieldnames=[
                "skill", "success", "total", "success_rate", "avg_margin"
            ])
            writer.writeheader()
            writer.writerows(skills)

    def _format_weapons(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Format weapons analyzer as CSV."""
        metrics = result.metrics

        # Summary
        output.write("# Summary\n")
        output.write(f"total_attacks,{metrics.get('total_attacks', 0)}\n")
        output.write(f"total_hits,{metrics.get('total_hits', 0)}\n")
        output.write(f"overall_hit_rate,{metrics.get('overall_hit_rate', 0)}\n")
        output.write(f"total_damage,{metrics.get('total_damage', 0)}\n")
        output.write(f"total_kills,{metrics.get('total_kills', 0)}\n")
        output.write("\n")

        # Weapon effectiveness table
        weapons = metrics.get("weapon_effectiveness", [])
        if weapons:
            output.write("# Weapon Effectiveness\n")
            writer = csv.DictWriter(output, fieldnames=[
                "weapon", "hits", "total", "hit_rate", "avg_damage", "max_damage", "total_damage", "kills"
            ])
            writer.writeheader()
            writer.writerows(weapons)

    def _format_enemies(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Format enemies analyzer as CSV."""
        metrics = result.metrics

        # Summary
        output.write("# Summary\n")
        output.write(f"total_spawns,{metrics.get('total_spawns', 0)}\n")
        output.write(f"total_defeats,{metrics.get('total_defeats', 0)}\n")
        output.write("\n")

        # Template stats table
        templates = metrics.get("template_stats", [])
        if templates:
            output.write("# Enemy Templates\n")
            writer = csv.DictWriter(output, fieldnames=[
                "template", "spawn_count", "spawn_percentage", "avg_health", "avg_soak",
                "avg_survival_rounds", "max_survival_rounds", "defeats"
            ])
            writer.writeheader()
            writer.writerows(templates)
            output.write("\n")

        # Defeat reasons
        defeats = metrics.get("defeat_breakdown", [])
        if defeats:
            output.write("# Defeat Reasons\n")
            writer = csv.DictWriter(output, fieldnames=["reason", "count", "percentage"])
            writer.writeheader()
            writer.writerows(defeats)

    def _format_economy(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Format economy analyzer as CSV."""
        metrics = result.metrics

        # Void stats
        void = metrics.get("void", {})
        if void:
            output.write("# Void Statistics\n")
            for key, value in void.items():
                if not isinstance(value, dict):
                    output.write(f"{key},{value}\n")
            output.write("\n")

        # Void by faction
        by_faction = metrics.get("void_by_faction", {})
        if by_faction:
            output.write("# Void by Faction\n")
            output.write("faction,count,avg_change,total\n")
            for faction, data in by_faction.items():
                output.write(f"{faction},{data['count']},{data['avg_change']},{data['total']}\n")
            output.write("\n")

        # Character summaries
        summaries = metrics.get("character_summaries", [])
        if summaries:
            output.write("# Character Summaries\n")
            fieldnames = ["character", "void_start", "void_end", "void_delta", "void_max"]
            if any("soulcredit_delta" in s for s in summaries):
                fieldnames.extend(["soulcredit_start", "soulcredit_end", "soulcredit_delta"])
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(summaries)
