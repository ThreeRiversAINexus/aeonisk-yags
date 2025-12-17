"""
JSON formatter - structured JSON output for programmatic consumption.
"""

import json
from typing import IO, List
from datetime import datetime
from ..analyzers.base import AnalyzerResult
from .base import OutputFormatter


class JSONFormatter(OutputFormatter):
    """JSON export for programmatic consumption."""

    @property
    def format_name(self) -> str:
        return "json"

    def __init__(self, pretty: bool = True):
        self.pretty = pretty

    def format(self, result: AnalyzerResult, output: IO[str]) -> None:
        """Write JSON formatted result to output stream."""
        data = {
            "analyzer": result.analyzer_name,
            "generated": datetime.now().isoformat(),
            "session_count": result.session_count,
            "event_count": result.event_count,
            "metrics": result.metrics,
            "warnings": result.warnings,
        }

        indent = 2 if self.pretty else None
        json.dump(data, output, indent=indent, default=str)
        output.write("\n")

    def format_multiple(self, results: List[AnalyzerResult], output: IO[str]) -> None:
        """Format multiple results as a single JSON object."""
        data = {
            "generated": datetime.now().isoformat(),
            "session_count": results[0].session_count if results else 0,
            "analyzers": {}
        }

        for result in results:
            data["analyzers"][result.analyzer_name] = {
                "event_count": result.event_count,
                "metrics": result.metrics,
                "warnings": result.warnings,
            }

        indent = 2 if self.pretty else None
        json.dump(data, output, indent=indent, default=str)
        output.write("\n")
