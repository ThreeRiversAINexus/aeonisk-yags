"""
Shared types for datamining tools.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum


class ValidatorType(Enum):
    """Types of validators available."""
    SCHEMA = "schema"
    ORDERING = "ordering"
    INTEGRITY = "integrity"
    LLM = "llm"


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation issue found in a session."""
    validator: ValidatorType
    severity: ValidationSeverity
    message: str
    line_number: Optional[int] = None
    event_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        prefix = f"[{self.validator.value}]"
        if self.line_number:
            prefix += f" Line {self.line_number}:"
        return f"{prefix} {self.message}"


@dataclass
class SessionInfo:
    """Metadata about a session file."""
    path: Path
    session_id: str
    total_events: int
    rounds: int
    is_complete: bool
    has_random_seed: bool = False
    player_count: int = 0
    enemy_count: int = 0

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass
class ValidationResult:
    """Result of validating a single session."""
    session_path: Path
    passed: bool
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def add_error(self, validator: ValidatorType, message: str,
                  line_number: Optional[int] = None,
                  event_type: Optional[str] = None,
                  details: Optional[Dict[str, Any]] = None) -> None:
        """Add an error to the result."""
        self.errors.append(ValidationIssue(
            validator=validator,
            severity=ValidationSeverity.ERROR,
            message=message,
            line_number=line_number,
            event_type=event_type,
            details=details or {}
        ))
        self.passed = False

    def add_warning(self, validator: ValidatorType, message: str,
                    line_number: Optional[int] = None,
                    event_type: Optional[str] = None,
                    details: Optional[Dict[str, Any]] = None) -> None:
        """Add a warning to the result."""
        self.warnings.append(ValidationIssue(
            validator=validator,
            severity=ValidationSeverity.WARNING,
            message=message,
            line_number=line_number,
            event_type=event_type,
            details=details or {}
        ))

    def _serialize_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Convert stats to JSON-serializable format (sets -> lists)."""
        result = {}
        for k, v in stats.items():
            if isinstance(v, set):
                result[k] = sorted(list(v))
            elif isinstance(v, dict):
                result[k] = self._serialize_stats(v)
            else:
                result[k] = v
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "session_path": str(self.session_path),
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "errors": [
                {
                    "validator": e.validator.value,
                    "severity": e.severity.value,
                    "message": e.message,
                    "line_number": e.line_number,
                    "event_type": e.event_type,
                    "details": e.details
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "validator": w.validator.value,
                    "severity": w.severity.value,
                    "message": w.message,
                    "line_number": w.line_number,
                    "event_type": w.event_type,
                    "details": w.details
                }
                for w in self.warnings
            ],
            "stats": self._serialize_stats(self.stats)
        }


@dataclass
class BulkReport:
    """Aggregated report from validating multiple sessions."""
    directory: Path
    total_sessions: int = 0
    passed_sessions: int = 0
    failed_sessions: int = 0
    results: List[ValidationResult] = field(default_factory=list)

    # Aggregated stats
    total_events: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    error_counts_by_validator: Dict[str, int] = field(default_factory=dict)
    warning_counts_by_validator: Dict[str, int] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if self.total_sessions == 0:
            return 0.0
        return self.passed_sessions / self.total_sessions

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result and update aggregated stats."""
        self.results.append(result)
        self.total_sessions += 1

        if result.passed:
            self.passed_sessions += 1
        else:
            self.failed_sessions += 1

        self.total_errors += result.error_count
        self.total_warnings += result.warning_count

        # Count by validator type
        for error in result.errors:
            key = error.validator.value
            self.error_counts_by_validator[key] = self.error_counts_by_validator.get(key, 0) + 1

        for warning in result.warnings:
            key = warning.validator.value
            self.warning_counts_by_validator[key] = self.warning_counts_by_validator.get(key, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "directory": str(self.directory),
            "summary": {
                "total_sessions": self.total_sessions,
                "passed_sessions": self.passed_sessions,
                "failed_sessions": self.failed_sessions,
                "pass_rate": round(self.pass_rate * 100, 1),
                "total_errors": self.total_errors,
                "total_warnings": self.total_warnings,
            },
            "error_counts_by_validator": self.error_counts_by_validator,
            "warning_counts_by_validator": self.warning_counts_by_validator,
            "results": [r.to_dict() for r in self.results]
        }

    def print_summary(self, show_details: bool = True) -> None:
        """Print human-readable summary to stdout."""
        print(f"\n{'=' * 60}")
        print(f"VALIDATION REPORT: {self.directory}")
        print(f"{'=' * 60}")
        print(f"Sessions scanned: {self.total_sessions}")
        print(f"Sessions passed: {self.passed_sessions} ({self.pass_rate * 100:.0f}%)")
        print(f"Sessions failed: {self.failed_sessions} ({(1 - self.pass_rate) * 100:.0f}%)")

        if self.failed_sessions > 0 and show_details:
            print(f"\n{'─' * 40}")
            print("FAILURES:")
            for result in self.results:
                if not result.passed:
                    print(f"\n  {result.session_path.name}:")
                    for error in result.errors[:5]:  # Limit to first 5
                        print(f"    - {error}")
                    if len(result.errors) > 5:
                        print(f"    ... and {len(result.errors) - 5} more errors")

        if self.total_warnings > 0 and show_details:
            print(f"\n{'─' * 40}")
            print("WARNINGS:")
            warned_sessions = [r for r in self.results if r.warnings]
            for result in warned_sessions[:5]:  # Limit to first 5 sessions
                print(f"\n  {result.session_path.name}:")
                for warning in result.warnings[:3]:  # Limit to first 3
                    print(f"    - {warning}")
                if len(result.warnings) > 3:
                    print(f"    ... and {len(result.warnings) - 3} more warnings")

        print(f"\n{'=' * 60}")
        if self.failed_sessions == 0:
            print("VALIDATION PASSED")
        else:
            print("VALIDATION FAILED")
        print()
