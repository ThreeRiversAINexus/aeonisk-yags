"""
Datamining tools for bulk JSONL session output analysis.

This package provides validation, export, and aggregation tools for
analyzing multi-agent session outputs from bulk runs.
"""

from .types import ValidationResult, BulkReport, SessionInfo
from .bulk_validator import BulkValidator
from .analyzers import (
    BaseAnalyzer,
    AnalyzerResult,
    AnalyzerPipeline,
    stream_events,
    SkillsAnalyzer,
    WeaponsAnalyzer,
    EnemiesAnalyzer,
    EconomyAnalyzer,
)
from .formatters import (
    OutputFormatter,
    TerminalFormatter,
    JSONFormatter,
    CSVFormatter,
)

__all__ = [
    # Validation
    'ValidationResult',
    'BulkReport',
    'SessionInfo',
    'BulkValidator',
    # Analyzers
    'BaseAnalyzer',
    'AnalyzerResult',
    'AnalyzerPipeline',
    'stream_events',
    'SkillsAnalyzer',
    'WeaponsAnalyzer',
    'EnemiesAnalyzer',
    'EconomyAnalyzer',
    # Formatters
    'OutputFormatter',
    'TerminalFormatter',
    'JSONFormatter',
    'CSVFormatter',
]
