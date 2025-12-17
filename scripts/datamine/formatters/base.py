"""
Base class for output formatters.

Formatters take AnalyzerResult objects and render them to different formats.
"""

from abc import ABC, abstractmethod
from typing import IO, List
from ..analyzers.base import AnalyzerResult


class OutputFormatter(ABC):
    """
    Base class for output formatters.

    Formatters take AnalyzerResult objects and render them to output streams.
    """

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Format identifier (e.g., 'terminal', 'json', 'csv')."""
        ...

    @abstractmethod
    def format(self, result: AnalyzerResult, output: IO[str]) -> None:
        """
        Write formatted result to output stream.

        Args:
            result: The analyzer result to format
            output: Output stream (file or stdout)
        """
        ...

    def format_multiple(self, results: List[AnalyzerResult], output: IO[str]) -> None:
        """
        Format multiple analyzer results together.

        Default implementation formats each result sequentially.
        Override for custom multi-result formatting.
        """
        for i, result in enumerate(results):
            if i > 0:
                output.write("\n")
            self.format(result, output)
