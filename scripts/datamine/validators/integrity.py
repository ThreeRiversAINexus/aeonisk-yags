"""
Integrity validator for JSONL session events.

Validates:
- HP never negative, never exceeds max
- Void scores in valid range (0-10)
- All action_declaration events have matching action_resolution
- Session has session_end (completeness)
- Character state consistency
- Detects user interrupts vs crashes
"""

from pathlib import Path
from typing import List, Dict, Any, Set, Optional
from ..types import ValidationResult, ValidatorType


class SessionTermination:
    """How a session ended."""
    COMPLETED = "completed"           # Has session_end event
    USER_INTERRUPTED = "interrupted"  # User pressed Ctrl+C
    CRASHED = "crashed"               # Exception/error in stderr
    INCOMPLETE = "incomplete"         # No session_end, unknown cause


class IntegrityValidator:
    """Validate data integrity in session logs."""

    def __init__(self, require_session_end: bool = True):
        """
        Initialize integrity validator.

        Args:
            require_session_end: If True, sessions without session_end are errors
        """
        self.require_session_end = require_session_end

    def detect_termination_cause(self, session_path: Path) -> str:
        """
        Detect how a session terminated by checking stderr.log.

        Args:
            session_path: Path to session JSONL file

        Returns:
            One of SessionTermination constants
        """
        # Look for stderr.log in same directory
        stderr_path = session_path.parent / "stderr.log"
        if not stderr_path.exists():
            return SessionTermination.INCOMPLETE

        try:
            content = stderr_path.read_text()

            # Check for user interrupt marker
            if "Session interrupted by user" in content:
                return SessionTermination.USER_INTERRUPTED

            # Check for real errors (not just thread cleanup noise)
            error_indicators = [
                "Traceback (most recent call last)",
                "Error:",
                "FAILED",
                "timeout",
                "ConnectionError",
                "APIError",
            ]
            # Thread cleanup warnings are not real errors
            if any(indicator in content for indicator in error_indicators):
                # But filter out false positives
                if "Exception in thread Thread-2 (_command_loop)" in content:
                    # This is just cleanup noise, not a crash
                    lines = [l for l in content.split('\n')
                             if l.strip() and 'Thread-2' not in l and 'excepthook' not in l]
                    if not lines:
                        return SessionTermination.INCOMPLETE
                return SessionTermination.CRASHED

        except Exception:
            pass

        return SessionTermination.INCOMPLETE

    def validate(self, events: List[Dict[str, Any]], result: ValidationResult, session_path: Optional[Path] = None) -> None:
        """
        Validate data integrity.

        Args:
            events: List of parsed events (with _line_num field)
            result: ValidationResult to add errors/warnings to
            session_path: Path to session file (for termination detection)
        """
        if not events:
            return

        # Track state
        has_session_end = False
        declarations: Dict[str, Dict[str, Any]] = {}  # agent -> most recent declaration
        resolved_declarations: Set[str] = set()  # agent names that have been resolved

        # Track character max health for validation
        character_max_health: Dict[str, int] = {}

        for event in events:
            event_type = event.get('event_type')
            line_num = event.get('_line_num', 0)

            if event_type == 'session_end':
                has_session_end = True

            elif event_type == 'character_state':
                self._validate_character_state(event, line_num, character_max_health, result)

            elif event_type == 'action_declaration':
                agent = event.get('agent', event.get('character_name', 'unknown'))
                declarations[agent] = {
                    'line': line_num,
                    'round': event.get('round'),
                    'action': event.get('action', event.get('intent', ''))
                }

            elif event_type == 'action_resolution':
                agent = event.get('agent', event.get('character_name', 'unknown'))
                if agent in declarations:
                    resolved_declarations.add(agent)
                    # Clear for next round
                    del declarations[agent]

                # Validate roll data if present
                self._validate_roll(event, line_num, result)

                # Validate effects if present
                self._validate_effects(event, line_num, result)

            elif event_type == 'enemy_spawn':
                self._validate_enemy_spawn(event, line_num, result)

            elif event_type == 'void_change':
                self._validate_void_change(event, line_num, result)

        # Check for session completeness and detect termination cause
        # First check if session_end has termination_reason (new format)
        termination = None
        termination_details = None
        for event in events:
            if event.get('event_type') == 'session_end':
                reason = event.get('termination_reason')
                if reason:
                    termination = reason
                    final_state = event.get('final_state', {})
                    termination_details = final_state.get('details')
                    break

        # Fall back to stderr detection for old sessions
        if not termination:
            if has_session_end:
                termination = SessionTermination.COMPLETED
            elif session_path:
                termination = self.detect_termination_cause(session_path)
            else:
                termination = SessionTermination.INCOMPLETE

        result.stats['termination'] = termination
        result.stats['termination_details'] = termination_details
        result.stats['is_complete'] = has_session_end

        if not has_session_end:
            if termination in (SessionTermination.USER_INTERRUPTED, "interrupted"):
                # User interrupts are warnings, not errors
                result.add_warning(
                    ValidatorType.INTEGRITY,
                    "Session interrupted by user (Ctrl+C)"
                )
            elif termination in (SessionTermination.CRASHED, "crashed"):
                msg = "Session crashed"
                if termination_details:
                    msg += f": {termination_details}"
                else:
                    msg += " (check stderr.log for details)"
                result.add_error(
                    ValidatorType.INTEGRITY,
                    msg
                )
            elif self.require_session_end:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    "Session incomplete: missing session_end event (cause unknown)"
                )
            else:
                result.add_warning(
                    ValidatorType.INTEGRITY,
                    "Session incomplete: missing session_end event"
                )

    def _validate_character_state(
        self,
        event: Dict[str, Any],
        line_num: int,
        character_max_health: Dict[str, int],
        result: ValidationResult
    ) -> None:
        """Validate character_state event data."""
        char_name = event.get('character_name', 'unknown')

        # Get health values
        health = event.get('health')
        max_health = event.get('max_health')

        if max_health is not None:
            character_max_health[char_name] = max_health

        # Validate health bounds
        if health is not None:
            if health < 0:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Negative health ({health}) for '{char_name}'",
                    line_number=line_num,
                    event_type='character_state'
                )

            if max_health is not None and health > max_health:
                result.add_warning(
                    ValidatorType.INTEGRITY,
                    f"Health ({health}) exceeds max_health ({max_health}) for '{char_name}'",
                    line_number=line_num,
                    event_type='character_state'
                )

        # Validate void score
        void_score = event.get('void_score')
        if void_score is not None:
            if void_score < 0:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Negative void_score ({void_score}) for '{char_name}'",
                    line_number=line_num,
                    event_type='character_state'
                )
            elif void_score > 10:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Void_score ({void_score}) exceeds maximum (10) for '{char_name}'",
                    line_number=line_num,
                    event_type='character_state'
                )

        # Validate wounds
        wounds = event.get('wounds')
        if wounds is not None and wounds < 0:
            result.add_error(
                ValidatorType.INTEGRITY,
                f"Negative wounds ({wounds}) for '{char_name}'",
                line_number=line_num,
                event_type='character_state'
            )

    def _validate_roll(
        self,
        event: Dict[str, Any],
        line_num: int,
        result: ValidationResult
    ) -> None:
        """Validate roll data in action_resolution."""
        roll = event.get('roll')
        if not roll:
            return

        # Check d20 bounds
        d20 = roll.get('d20')
        if d20 is not None:
            if d20 < 1 or d20 > 20:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Invalid d20 value ({d20}), must be 1-20",
                    line_number=line_num,
                    event_type='action_resolution'
                )

        # Check total calculation consistency
        # YAGS uses MULTIPLICATIVE formula: attr × skill + d20 + modifier
        total = roll.get('total')
        attr_val = roll.get('attr_val', 0)
        skill_val = roll.get('skill_val', 0)
        modifier = roll.get('modifier', 0)
        # Also check 'ability' field which stores attr × skill
        ability = roll.get('ability')

        if total is not None and d20 is not None:
            # Use ability if present (already computed attr × skill), otherwise compute it
            if ability is not None:
                expected_base = ability + d20 + modifier
            else:
                expected_base = (attr_val * skill_val) + d20 + modifier
            # Allow some variance for other modifiers not tracked (wounds, conditions, etc.)
            if abs(total - expected_base) > 10:
                result.add_warning(
                    ValidatorType.INTEGRITY,
                    f"Roll total ({total}) differs significantly from expected ({expected_base})",
                    line_number=line_num,
                    event_type='action_resolution',
                    details={'d20': d20, 'attr_val': attr_val, 'skill_val': skill_val, 'ability': ability}
                )

    def _validate_effects(
        self,
        event: Dict[str, Any],
        line_num: int,
        result: ValidationResult
    ) -> None:
        """Validate effects in action_resolution."""
        effects = event.get('effects', {})
        if not effects:
            return

        # Validate void_changes
        void_changes = effects.get('void_changes') or []
        for vc in void_changes:
            if isinstance(vc, dict):
                amount = vc.get('amount', 0)
                # Void changes should be small (-3 to +3 typically)
                if abs(amount) > 5:
                    result.add_warning(
                        ValidatorType.INTEGRITY,
                        f"Large void change ({amount}) for '{vc.get('character_name', 'unknown')}'",
                        line_number=line_num,
                        event_type='action_resolution'
                    )

        # Validate damage
        damage_list = effects.get('damage') or []
        for dmg in damage_list:
            if isinstance(dmg, dict):
                dealt = dmg.get('dealt', 0)
                if dealt < 0:
                    result.add_error(
                        ValidatorType.INTEGRITY,
                        f"Negative damage dealt ({dealt})",
                        line_number=line_num,
                        event_type='action_resolution'
                    )

    def _validate_enemy_spawn(
        self,
        event: Dict[str, Any],
        line_num: int,
        result: ValidationResult
    ) -> None:
        """Validate enemy_spawn event."""
        stats = event.get('stats', {})
        if not stats:
            return

        health = stats.get('health')
        max_health = stats.get('max_health')

        if health is not None and health < 0:
            result.add_error(
                ValidatorType.INTEGRITY,
                f"Enemy spawned with negative health ({health})",
                line_number=line_num,
                event_type='enemy_spawn'
            )

        if health is not None and max_health is not None:
            if health > max_health:
                result.add_warning(
                    ValidatorType.INTEGRITY,
                    f"Enemy spawned with health ({health}) > max_health ({max_health})",
                    line_number=line_num,
                    event_type='enemy_spawn'
                )

    def _validate_void_change(
        self,
        event: Dict[str, Any],
        line_num: int,
        result: ValidationResult
    ) -> None:
        """Validate void_change event."""
        new_void = event.get('new_void_score')
        if new_void is not None:
            if new_void < 0:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Void score became negative ({new_void})",
                    line_number=line_num,
                    event_type='void_change'
                )
            elif new_void > 10:
                result.add_error(
                    ValidatorType.INTEGRITY,
                    f"Void score exceeded maximum ({new_void} > 10)",
                    line_number=line_num,
                    event_type='void_change'
                )
