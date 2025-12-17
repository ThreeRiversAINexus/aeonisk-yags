"""
LLM error validator for JSONL session events.

Validates:
- Count pydantic_validation_failure events
- Check structured_output_metrics for fallback_triggered=true
- Find llm_call events with error responses
- Aggregate: total calls, success rate, fallback rate
"""

from typing import List, Dict, Any
from ..types import ValidationResult, ValidatorType


class LLMErrorValidator:
    """Validate LLM-related errors and metrics in session logs."""

    def __init__(
        self,
        fallback_threshold: float = 0.10,
        validation_failure_threshold: int = 5,
    ):
        """
        Initialize LLM error validator.

        Args:
            fallback_threshold: Warn if fallback rate exceeds this (default: 10%)
            validation_failure_threshold: Warn if more than this many failures
        """
        self.fallback_threshold = fallback_threshold
        self.validation_failure_threshold = validation_failure_threshold

    def validate(self, events: List[Dict[str, Any]], result: ValidationResult) -> None:
        """
        Validate LLM-related events for errors.

        Args:
            events: List of parsed events (with _line_num field)
            result: ValidationResult to add errors/warnings to
        """
        # Track LLM metrics
        total_llm_calls = 0
        llm_calls_by_agent: Dict[str, int] = {}
        validation_failures = 0
        fallback_triggers = 0
        structured_output_success = 0
        structured_output_total = 0

        # Error details
        error_details: List[Dict[str, Any]] = []

        for event in events:
            event_type = event.get('event_type')
            line_num = event.get('_line_num', 0)

            if event_type == 'llm_call':
                total_llm_calls += 1
                agent_type = event.get('agent_type', 'unknown')
                llm_calls_by_agent[agent_type] = llm_calls_by_agent.get(agent_type, 0) + 1

                # Check for error in response
                response = event.get('response', '')
                if isinstance(response, str):
                    if 'error' in response.lower() or 'exception' in response.lower():
                        error_details.append({
                            'line': line_num,
                            'agent': agent_type,
                            'type': 'llm_error_response'
                        })

                # Check for explicit error field
                if event.get('error'):
                    result.add_error(
                        ValidatorType.LLM,
                        f"LLM call error: {event.get('error')}",
                        line_number=line_num,
                        event_type='llm_call',
                        details={'agent_type': agent_type}
                    )

            elif event_type == 'pydantic_validation_failure':
                validation_failures += 1
                error_details.append({
                    'line': line_num,
                    'error': event.get('error', 'unknown'),
                    'type': 'pydantic_failure'
                })

            elif event_type == 'structured_output_metrics':
                structured_output_total += 1

                # Check for fallback
                if event.get('fallback_triggered'):
                    fallback_triggers += 1
                    error_details.append({
                        'line': line_num,
                        'phase': event.get('phase', 'unknown'),
                        'type': 'fallback_triggered'
                    })
                else:
                    structured_output_success += 1

                # Check for validation warnings
                warnings = event.get('validation_warnings', [])
                if warnings:
                    for warning in warnings[:3]:  # Limit to first 3
                        result.add_warning(
                            ValidatorType.LLM,
                            f"Validation warning: {warning}",
                            line_number=line_num,
                            event_type='structured_output_metrics'
                        )

            elif event_type == 'marker_retry_attempt':
                # Track retry attempts as warnings
                attempt = event.get('attempt', 1)
                if attempt > 1:
                    error_details.append({
                        'line': line_num,
                        'attempt': attempt,
                        'type': 'marker_retry'
                    })

        # Store metrics in result stats
        result.stats['llm_total_calls'] = total_llm_calls
        result.stats['llm_calls_by_agent'] = llm_calls_by_agent
        result.stats['validation_failures'] = validation_failures
        result.stats['fallback_triggers'] = fallback_triggers
        result.stats['structured_output_success'] = structured_output_success
        result.stats['structured_output_total'] = structured_output_total

        # Calculate rates
        fallback_rate = 0.0
        if structured_output_total > 0:
            fallback_rate = fallback_triggers / structured_output_total
            result.stats['fallback_rate'] = round(fallback_rate * 100, 1)

        # Add warnings/errors based on thresholds
        if validation_failures > self.validation_failure_threshold:
            result.add_warning(
                ValidatorType.LLM,
                f"High validation failure count: {validation_failures} failures"
            )

        if fallback_rate > self.fallback_threshold:
            result.add_warning(
                ValidatorType.LLM,
                f"High fallback rate: {fallback_rate * 100:.1f}% (threshold: {self.fallback_threshold * 100}%)",
                details={'fallback_triggers': fallback_triggers, 'total': structured_output_total}
            )

        # If there are many errors, add a summary
        if validation_failures > 0 or fallback_triggers > 0:
            result.stats['llm_error_details'] = error_details[:10]  # Keep first 10
