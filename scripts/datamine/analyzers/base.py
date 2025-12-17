"""
Base classes for balance analyzers.

Analyzers process JSONL events and extract metrics for game balance analysis.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Iterator, Set, Optional
from pathlib import Path
import json


@dataclass
class AnalyzerResult:
    """Result from running an analyzer across sessions."""

    analyzer_name: str
    session_count: int = 0
    event_count: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def merge(self, other: 'AnalyzerResult') -> 'AnalyzerResult':
        """Merge results from multiple analysis runs."""
        if self.analyzer_name != other.analyzer_name:
            raise ValueError(f"Cannot merge results from different analyzers: "
                           f"{self.analyzer_name} vs {other.analyzer_name}")

        # Create new result with combined counts
        merged = AnalyzerResult(
            analyzer_name=self.analyzer_name,
            session_count=self.session_count + other.session_count,
            event_count=self.event_count + other.event_count,
            warnings=self.warnings + other.warnings,
        )

        # Merge metrics (subclasses should override for proper merging)
        merged.metrics = {**self.metrics, **other.metrics}
        return merged

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "analyzer": self.analyzer_name,
            "session_count": self.session_count,
            "event_count": self.event_count,
            "metrics": self.metrics,
            "warnings": self.warnings,
        }


class BaseAnalyzer(ABC):
    """
    Base class for balance analyzers.

    Analyzers are stateful - they accumulate data across multiple sessions,
    then produce a final result with aggregate statistics.

    Usage:
        analyzer = SkillsAnalyzer()
        for session_file in sessions:
            events = stream_events(session_file)
            analyzer.process_session(events)
        result = analyzer.get_result()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique analyzer name (e.g., 'skills', 'weapons')."""
        ...

    @property
    @abstractmethod
    def event_types(self) -> Set[str]:
        """Event types this analyzer processes (for filtering)."""
        ...

    @abstractmethod
    def process_event(self, event: Dict[str, Any]) -> None:
        """
        Process a single event, accumulating internal state.

        Called only for events whose event_type is in self.event_types.
        """
        ...

    def process_session(self, events: Iterator[Dict[str, Any]]) -> None:
        """
        Process all events from a session.

        Default implementation filters by event_type and delegates to process_event.
        Override for custom session-level processing.
        """
        for event in events:
            if event.get('event_type') in self.event_types:
                self.process_event(event)

    @abstractmethod
    def get_result(self) -> AnalyzerResult:
        """
        Produce final result with accumulated statistics.

        Should be called after all sessions have been processed.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state for fresh analysis."""
        ...


class AnalyzerPipeline:
    """
    Compose multiple analyzers into a single pass over events.

    This is more efficient than running each analyzer separately
    since we only parse JSONL once per session.

    Usage:
        pipeline = AnalyzerPipeline([
            SkillsAnalyzer(),
            WeaponsAnalyzer(),
            EconomyAnalyzer(),
        ])

        for session_path in session_files:
            events = stream_events(session_path)
            pipeline.process_session(events)

        results = pipeline.get_results()
    """

    def __init__(self, analyzers: List[BaseAnalyzer]):
        self.analyzers = analyzers
        self._event_type_map = self._build_event_map()
        self._session_count = 0

    def _build_event_map(self) -> Dict[str, List[BaseAnalyzer]]:
        """Build mapping of event_type -> list of interested analyzers."""
        mapping: Dict[str, List[BaseAnalyzer]] = {}
        for analyzer in self.analyzers:
            for event_type in analyzer.event_types:
                if event_type not in mapping:
                    mapping[event_type] = []
                mapping[event_type].append(analyzer)
        return mapping

    @property
    def all_event_types(self) -> Set[str]:
        """All event types processed by any analyzer in the pipeline."""
        return set(self._event_type_map.keys())

    def process_session(self, events: Iterator[Dict[str, Any]]) -> None:
        """
        Single-pass processing: route each event to interested analyzers.

        More efficient than running each analyzer separately since we only
        iterate through events once.
        """
        self._session_count += 1
        for event in events:
            event_type = event.get('event_type')
            interested_analyzers = self._event_type_map.get(event_type, [])
            for analyzer in interested_analyzers:
                analyzer.process_event(event)

    def get_results(self) -> List[AnalyzerResult]:
        """Get results from all analyzers."""
        results = []
        for analyzer in self.analyzers:
            result = analyzer.get_result()
            # Ensure session count is consistent
            result.session_count = self._session_count
            results.append(result)
        return results

    def reset(self) -> None:
        """Reset all analyzers for fresh analysis."""
        self._session_count = 0
        for analyzer in self.analyzers:
            analyzer.reset()


def stream_events(
    jsonl_path: Path,
    filter_types: Optional[Set[str]] = None
) -> Iterator[Dict[str, Any]]:
    """
    Stream events from a JSONL file with optional filtering.

    Args:
        jsonl_path: Path to JSONL session file
        filter_types: If provided, only yield events with these event_types

    Yields:
        Event dictionaries, optionally filtered by type
    """
    with open(jsonl_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if filter_types is None or event.get('event_type') in filter_types:
                    yield event
            except json.JSONDecodeError:
                continue  # Skip malformed lines
