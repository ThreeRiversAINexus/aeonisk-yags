"""
Bulk validator for JSONL session files.

Wraps the existing FixtureValidator from analyze_session.py for directory scanning
and adds additional validators (ordering, integrity, LLM errors).
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Set, Iterator, Dict, Any

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from analyze_session import FixtureValidator, EVENT_SCHEMAS

from .types import (
    ValidationResult,
    BulkReport,
    ValidatorType,
    ValidationSeverity,
)
from .validators import OrderingValidator, IntegrityValidator, LLMErrorValidator


class BulkValidator:
    """
    Validate multiple JSONL session files in a directory.

    Combines existing FixtureValidator (schema validation) with new validators
    for ordering, integrity, and LLM error detection.
    """

    def __init__(
        self,
        validators: Optional[Set[ValidatorType]] = None,
        strict: bool = False,
        fallback_threshold: float = 0.10,  # 10% fallback rate warning
    ):
        """
        Initialize bulk validator.

        Args:
            validators: Set of validators to run. Default: all validators
            strict: If True, fail on warnings
            fallback_threshold: LLM fallback rate above which to warn
        """
        self.validators = validators or {
            ValidatorType.SCHEMA,
            ValidatorType.ORDERING,
            ValidatorType.INTEGRITY,
            ValidatorType.LLM,
        }
        self.strict = strict
        self.fallback_threshold = fallback_threshold

    def discover_sessions(
        self,
        directory: Path,
        pattern: str = "session_*.jsonl",
        recursive: bool = True,
    ) -> List[Path]:
        """
        Discover JSONL session files in a directory.

        Args:
            directory: Directory to search
            pattern: Glob pattern to match files
            recursive: If True, search subdirectories

        Returns:
            List of Path objects for discovered session files
        """
        if recursive:
            return sorted(directory.rglob(pattern))
        else:
            return sorted(directory.glob(pattern))

    def validate_session(self, session_path: Path) -> ValidationResult:
        """
        Validate a single session file with all enabled validators.

        Args:
            session_path: Path to JSONL session file

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(session_path=session_path, passed=True)

        # Load all events once for efficiency
        events = []
        try:
            with open(session_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        event['_line_num'] = line_num
                        events.append(event)
                    except json.JSONDecodeError as e:
                        result.add_error(
                            ValidatorType.SCHEMA,
                            f"JSON parse error: {e}",
                            line_number=line_num
                        )
        except FileNotFoundError:
            result.add_error(ValidatorType.SCHEMA, f"File not found: {session_path}")
            return result
        except Exception as e:
            result.add_error(ValidatorType.SCHEMA, f"Error reading file: {e}")
            return result

        result.stats['total_events'] = len(events)

        # Run schema validator (using existing FixtureValidator)
        if ValidatorType.SCHEMA in self.validators:
            self._run_schema_validator(session_path, events, result)

        # Run ordering validator
        if ValidatorType.ORDERING in self.validators:
            ordering = OrderingValidator()
            ordering.validate(events, result)

        # Run integrity validator
        if ValidatorType.INTEGRITY in self.validators:
            integrity = IntegrityValidator()
            integrity.validate(events, result, session_path=session_path)

        # Run LLM error validator
        if ValidatorType.LLM in self.validators:
            llm_validator = LLMErrorValidator(fallback_threshold=self.fallback_threshold)
            llm_validator.validate(events, result)

        # If strict mode, convert warnings to errors
        if self.strict and result.warnings:
            for warning in result.warnings:
                result.add_error(
                    warning.validator,
                    f"[strict] {warning.message}",
                    line_number=warning.line_number,
                    event_type=warning.event_type,
                    details=warning.details
                )
            result.warnings = []

        return result

    def _run_schema_validator(
        self,
        session_path: Path,
        events: List[Dict[str, Any]],
        result: ValidationResult
    ) -> None:
        """Run schema validation using FixtureValidator logic."""
        for event in events:
            line_num = event.get('_line_num', 0)
            event_type = event.get('event_type')

            if not event_type:
                result.add_error(
                    ValidatorType.SCHEMA,
                    "Missing 'event_type' field",
                    line_number=line_num
                )
                continue

            if event_type not in EVENT_SCHEMAS:
                result.add_warning(
                    ValidatorType.SCHEMA,
                    f"Unknown event_type '{event_type}'",
                    line_number=line_num,
                    event_type=event_type
                )
                continue

            schema = EVENT_SCHEMAS[event_type]

            # Check required fields
            for field in schema.get('required', []):
                if field not in event:
                    result.add_error(
                        ValidatorType.SCHEMA,
                        f"Missing required field '{field}'",
                        line_number=line_num,
                        event_type=event_type
                    )

            # Track stats
            if event_type == 'session_start':
                result.stats['has_session_start'] = True
                config = event.get('config', {})
                result.stats['has_random_seed'] = 'random_seed' in config
            elif event_type == 'session_end':
                result.stats['has_session_end'] = True
            elif event_type == 'round_start':
                rounds = result.stats.get('rounds', set())
                if isinstance(rounds, set):
                    rounds.add(event.get('round', 0))
                    result.stats['rounds'] = rounds
            elif event_type == 'llm_call':
                agent_type = event.get('agent_type', '')
                key = f'{agent_type}_llm_calls'
                result.stats[key] = result.stats.get(key, 0) + 1

    def validate_directory(
        self,
        directory: Path,
        pattern: str = "session_*.jsonl",
        recursive: bool = True,
    ) -> BulkReport:
        """
        Validate all session files in a directory.

        Args:
            directory: Directory to validate
            pattern: Glob pattern to match session files
            recursive: If True, search subdirectories

        Returns:
            BulkReport with aggregated results
        """
        report = BulkReport(directory=directory)
        sessions = self.discover_sessions(directory, pattern, recursive)

        for session_path in sessions:
            result = self.validate_session(session_path)
            report.add_result(result)
            report.total_events += result.stats.get('total_events', 0)

        return report

    def validate_files(self, files: List[Path]) -> BulkReport:
        """
        Validate a specific list of session files.

        Args:
            files: List of paths to JSONL files

        Returns:
            BulkReport with aggregated results
        """
        report = BulkReport(directory=files[0].parent if files else Path('.'))

        for session_path in files:
            result = self.validate_session(session_path)
            report.add_result(result)
            report.total_events += result.stats.get('total_events', 0)

        return report
