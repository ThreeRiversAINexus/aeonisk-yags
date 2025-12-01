"""
Unit tests for datamine validators.

Tests the ordering, integrity, and LLM error validators.
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any

# Add scripts to path
import sys
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from datamine.types import ValidationResult, ValidatorType
from datamine.validators.ordering import OrderingValidator
from datamine.validators.integrity import IntegrityValidator
from datamine.validators.llm_errors import LLMErrorValidator


def make_event(event_type: str, line_num: int = 1, **kwargs) -> Dict[str, Any]:
    """Helper to create test events."""
    event = {
        'event_type': event_type,
        '_line_num': line_num,
        'ts': '2025-01-01T00:00:00',
        'session': 'test-session',
    }
    event.update(kwargs)
    return event


class TestOrderingValidator:
    """Tests for OrderingValidator."""

    def test_empty_events_error(self):
        """Empty event list should produce an error."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        validator.validate([], result)
        assert not result.passed
        assert len(result.errors) == 1
        assert 'No events' in result.errors[0].message

    def test_session_start_first(self):
        """First event should be session_start."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('scenario', line_num=1),
            make_event('session_start', line_num=2),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('expected \'session_start\'' in e.message for e in result.errors)

    def test_valid_ordering(self):
        """Valid event ordering should pass."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('scenario', line_num=2),
            make_event('round_start', line_num=3, round=0),
            make_event('action_declaration', line_num=4, round=0),
            make_event('action_resolution', line_num=5, round=0),
            make_event('session_end', line_num=6),
        ]
        validator.validate(events, result)
        assert result.passed
        assert len(result.errors) == 0

    def test_action_before_round_start(self):
        """Action before round_start should produce error."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('action_resolution', line_num=2, round=0),  # Before round_start!
            make_event('round_start', line_num=3, round=0),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('before round_start' in e.message for e in result.errors)

    def test_duplicate_event_id(self):
        """Duplicate event IDs should produce error."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1, event_id='evt-001'),
            make_event('scenario', line_num=2, event_id='evt-001'),  # Duplicate!
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('Duplicate event_id' in e.message for e in result.errors)

    def test_round_gap_warning(self):
        """Gap in round numbers should produce warning."""
        validator = OrderingValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('round_start', line_num=2, round=0),
            make_event('round_start', line_num=3, round=2),  # Skipped round 1!
        ]
        validator.validate(events, result)
        assert result.passed  # Warnings don't fail
        assert len(result.warnings) >= 1
        assert any('Gap in round numbers' in w.message for w in result.warnings)


class TestIntegrityValidator:
    """Tests for IntegrityValidator."""

    def test_negative_health_error(self):
        """Negative health should produce error."""
        validator = IntegrityValidator(require_session_end=False)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('character_state', line_num=2, character_name='Test', health=-5, max_health=20),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('Negative health' in e.message for e in result.errors)

    def test_health_exceeds_max_warning(self):
        """Health exceeding max should produce warning."""
        validator = IntegrityValidator(require_session_end=False)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('character_state', line_num=2, character_name='Test', health=25, max_health=20),
        ]
        validator.validate(events, result)
        assert result.passed  # Warning doesn't fail
        assert any('exceeds max_health' in w.message for w in result.warnings)

    def test_void_score_bounds(self):
        """Void score should be in 0-10 range."""
        validator = IntegrityValidator(require_session_end=False)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('character_state', line_num=2, character_name='Test', void_score=15),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('exceeds maximum' in e.message for e in result.errors)

    def test_negative_void_score(self):
        """Negative void score should produce error."""
        validator = IntegrityValidator(require_session_end=False)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('character_state', line_num=2, character_name='Test', void_score=-1),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('Negative void_score' in e.message for e in result.errors)

    def test_missing_session_end_error(self):
        """Missing session_end should produce error when required."""
        validator = IntegrityValidator(require_session_end=True)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('scenario', line_num=2),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('missing session_end' in e.message for e in result.errors)

    def test_complete_session_passes(self):
        """Complete session should pass."""
        validator = IntegrityValidator(require_session_end=True)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('scenario', line_num=2),
            make_event('session_end', line_num=3),
        ]
        validator.validate(events, result)
        assert result.passed

    def test_invalid_d20_roll(self):
        """D20 value outside 1-20 should produce error."""
        validator = IntegrityValidator(require_session_end=False)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('action_resolution', line_num=2, roll={'d20': 25, 'total': 30}),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('Invalid d20 value' in e.message for e in result.errors)


class TestLLMErrorValidator:
    """Tests for LLMErrorValidator."""

    def test_no_errors_passes(self):
        """Session with no LLM errors should pass."""
        validator = LLMErrorValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('llm_call', line_num=2, agent_type='dm', response='OK'),
            make_event('structured_output_metrics', line_num=3, fallback_triggered=False),
        ]
        validator.validate(events, result)
        assert result.passed
        assert result.stats['llm_total_calls'] == 1
        assert result.stats['fallback_triggers'] == 0

    def test_high_fallback_rate_warning(self):
        """High fallback rate should produce warning."""
        validator = LLMErrorValidator(fallback_threshold=0.10)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('structured_output_metrics', line_num=2, fallback_triggered=True),
            make_event('structured_output_metrics', line_num=3, fallback_triggered=True),
            make_event('structured_output_metrics', line_num=4, fallback_triggered=False),
        ]
        validator.validate(events, result)
        assert result.passed  # Warnings don't fail
        # 2/3 = 66% fallback rate
        assert any('High fallback rate' in w.message for w in result.warnings)

    def test_validation_failure_count(self):
        """Pydantic validation failures should be counted."""
        validator = LLMErrorValidator(validation_failure_threshold=2)
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('pydantic_validation_failure', line_num=2, error='Error 1'),
            make_event('pydantic_validation_failure', line_num=3, error='Error 2'),
            make_event('pydantic_validation_failure', line_num=4, error='Error 3'),
        ]
        validator.validate(events, result)
        assert result.passed  # Warnings don't fail
        assert result.stats['validation_failures'] == 3
        assert any('High validation failure count' in w.message for w in result.warnings)

    def test_llm_call_with_error(self):
        """LLM call with error field should produce error."""
        validator = LLMErrorValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('llm_call', line_num=2, agent_type='dm', error='API rate limit exceeded'),
        ]
        validator.validate(events, result)
        assert not result.passed
        assert any('LLM call error' in e.message for e in result.errors)

    def test_llm_calls_by_agent_tracking(self):
        """LLM calls should be tracked by agent type."""
        validator = LLMErrorValidator()
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        events = [
            make_event('session_start', line_num=1),
            make_event('llm_call', line_num=2, agent_type='dm'),
            make_event('llm_call', line_num=3, agent_type='dm'),
            make_event('llm_call', line_num=4, agent_type='player'),
            make_event('llm_call', line_num=5, agent_type='enemy'),
        ]
        validator.validate(events, result)
        assert result.stats['llm_calls_by_agent']['dm'] == 2
        assert result.stats['llm_calls_by_agent']['player'] == 1
        assert result.stats['llm_calls_by_agent']['enemy'] == 1


class TestValidationResult:
    """Tests for ValidationResult type."""

    def test_add_error_sets_passed_false(self):
        """Adding an error should set passed to False."""
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        assert result.passed
        result.add_error(ValidatorType.SCHEMA, "Test error")
        assert not result.passed
        assert result.error_count == 1

    def test_add_warning_keeps_passed_true(self):
        """Adding a warning should not change passed status."""
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        result.add_warning(ValidatorType.SCHEMA, "Test warning")
        assert result.passed
        assert result.warning_count == 1

    def test_to_dict_serialization(self):
        """to_dict should produce JSON-serializable output."""
        result = ValidationResult(session_path=Path('test.jsonl'), passed=True)
        result.add_error(ValidatorType.ORDERING, "Error message", line_number=42)
        result.add_warning(ValidatorType.LLM, "Warning message")
        result.stats['rounds'] = {0, 1, 2}  # Set should be converted to list

        d = result.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert 'test.jsonl' in json_str
        assert 'Error message' in json_str
        assert 'Warning message' in json_str


class TestIntegration:
    """Integration tests using real fixture files."""

    @pytest.fixture
    def fixtures_dir(self):
        """Get path to test fixtures directory."""
        return Path(__file__).parent.parent / 'fixtures' / 'sessions'

    def test_validate_real_fixture_if_exists(self, fixtures_dir):
        """Validate a real fixture file if available."""
        if not fixtures_dir.exists():
            pytest.skip("No fixtures directory")

        jsonl_files = list(fixtures_dir.glob('*.jsonl'))
        if not jsonl_files:
            pytest.skip("No JSONL fixtures available")

        from datamine import BulkValidator
        validator = BulkValidator()
        result = validator.validate_session(jsonl_files[0])

        # Just check it runs without error
        assert result is not None
        assert isinstance(result.passed, bool)
