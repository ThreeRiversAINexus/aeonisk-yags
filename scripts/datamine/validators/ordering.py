"""
Ordering validator for JSONL session events.

Validates:
- round_start before action_resolution for each round
- event_id / parent_event_id chains are valid
- Round numbers increment properly (no gaps)
- session_start is first, session_end is last (if present)
"""

from typing import List, Dict, Any, Set, Optional
from ..types import ValidationResult, ValidatorType


class OrderingValidator:
    """Validate event ordering in session logs."""

    def validate(self, events: List[Dict[str, Any]], result: ValidationResult) -> None:
        """
        Validate event ordering.

        Args:
            events: List of parsed events (with _line_num field)
            result: ValidationResult to add errors/warnings to
        """
        if not events:
            result.add_error(
                ValidatorType.ORDERING,
                "No events in session"
            )
            return

        # Check session_start is first
        first_event = events[0]
        if first_event.get('event_type') != 'session_start':
            result.add_error(
                ValidatorType.ORDERING,
                f"First event is '{first_event.get('event_type')}', expected 'session_start'",
                line_number=first_event.get('_line_num')
            )

        # Track rounds and their events
        round_events: Dict[int, List[Dict[str, Any]]] = {}
        seen_event_ids: Set[str] = set()
        event_id_to_line: Dict[str, int] = {}
        has_session_end = False
        last_event = events[-1]

        for event in events:
            event_type = event.get('event_type')
            line_num = event.get('_line_num', 0)
            round_num = event.get('round')

            # Track event IDs for causal chain validation
            event_id = event.get('event_id')
            if event_id:
                if event_id in seen_event_ids:
                    result.add_error(
                        ValidatorType.ORDERING,
                        f"Duplicate event_id '{event_id}'",
                        line_number=line_num,
                        event_type=event_type
                    )
                seen_event_ids.add(event_id)
                event_id_to_line[event_id] = line_num

            # Track round events
            if round_num is not None:
                if round_num not in round_events:
                    round_events[round_num] = []
                round_events[round_num].append(event)

            # Check for session_end
            if event_type == 'session_end':
                has_session_end = True

        # Check session_end is last (if present)
        if has_session_end and last_event.get('event_type') != 'session_end':
            result.add_warning(
                ValidatorType.ORDERING,
                f"session_end is not the last event (last is '{last_event.get('event_type')}')",
                line_number=last_event.get('_line_num')
            )

        # Validate parent_event_id references
        for event in events:
            parent_id = event.get('parent_event_id')
            line_num = event.get('_line_num', 0)
            event_type = event.get('event_type')

            if parent_id and parent_id not in seen_event_ids:
                # Skip if it's a setup event (session_start, scenario have no parent)
                if event_type not in ('session_start', 'scenario'):
                    result.add_warning(
                        ValidatorType.ORDERING,
                        f"parent_event_id '{parent_id}' not found",
                        line_number=line_num,
                        event_type=event_type
                    )

        # Check round progression
        if round_events:
            round_nums = sorted(round_events.keys())

            # Check for gaps in round numbers
            for i in range(len(round_nums) - 1):
                if round_nums[i + 1] - round_nums[i] > 1:
                    result.add_warning(
                        ValidatorType.ORDERING,
                        f"Gap in round numbers: {round_nums[i]} -> {round_nums[i + 1]}"
                    )

            # Check round_start before action_resolution per round
            for round_num, round_event_list in round_events.items():
                round_start_seen = False
                for event in round_event_list:
                    event_type = event.get('event_type')
                    line_num = event.get('_line_num', 0)

                    if event_type == 'round_start':
                        round_start_seen = True

                    elif event_type in ('action_resolution', 'action_declaration'):
                        if not round_start_seen:
                            result.add_error(
                                ValidatorType.ORDERING,
                                f"'{event_type}' in round {round_num} before round_start",
                                line_number=line_num,
                                event_type=event_type
                            )

        # Store round count in stats
        result.stats['round_count'] = len(round_events)
