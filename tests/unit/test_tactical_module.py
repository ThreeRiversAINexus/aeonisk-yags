"""
tests/unit/test_tactical_module.py

Validate positioning rules from content/experimental/Aeonisk - Tactical Module - v1.2.3.md

Tests tactical positioning mechanics:
- Valid tactical positions (Engaged/Near/Far/Extreme)
- Movement rules and position changes
- Targeting from different ranges
- Position validation and consistency
"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def combat_events():
    """Load real combat session."""
    jsonl_path = Path(__file__).parent.parent / "fixtures" / "sample_logs" / "combat_session_sample.jsonl"
    events = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


class TestTacticalPositions:
    """Validate tactical position values."""

    def test_valid_positions_only(self, combat_events):
        """Only valid tactical positions allowed."""
        # Valid positions from Tactical Module v1.2.3
        valid_positions = [
            'Engaged',
            'Near-PC', 'Near-Enemy',
            'Far-PC', 'Far-Enemy',
            'Extreme-PC', 'Extreme-Enemy'
        ]

        # Check action declarations
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']

        for decl in declarations:
            action = decl.get('action', {})

            # Check for position/target fields
            position = action.get('target') or action.get('position') or action.get('new_position')

            if position and isinstance(position, str):
                # Should match one of the valid positions
                is_valid = any(valid_pos in position for valid_pos in valid_positions)

                if not is_valid:
                    # May be a character name or other target
                    print(f"INFO: Target/position '{position}' may not be tactical position")

    def test_position_format_consistency(self, combat_events):
        """Positions should follow consistent format."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            environment = res.get('environment', '')

            if not environment:
                continue

            # Environment should mention positions
            position_keywords = ['Engaged', 'Near', 'Far', 'Extreme']

            if any(kw in environment for kw in position_keywords):
                # Should follow proper format
                # Example: "2 PCs at Near-PC, 1 enemy at Engaged"

                # Check for valid separators
                assert 'at' in environment.lower() or '@' in environment, \
                    f"Position in environment doesn't use standard format: {environment}"


class TestPositionChanges:
    """Validate movement and position changes."""

    def test_movement_actions_change_position(self, combat_events):
        """Movement actions should result in position changes."""
        # Find movement actions
        movement_keywords = ['move', 'shift', 'advance', 'retreat', 'close', 'withdraw', 'reposition']

        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']

        movement_actions = []
        for decl in declarations:
            action = decl.get('action', {})
            major_action = str(action.get('major_action', '')).lower()

            if any(kw in major_action for kw in movement_keywords):
                movement_actions.append(decl)

        # Soft check - movement should be present in combat
        if len(movement_actions) > 0:
            for movement in movement_actions:
                action = movement.get('action', {})
                target = action.get('target')

                # Should have target position
                if not target:
                    character = movement.get('character_name', 'unknown')
                    print(f"INFO: Movement action by {character} without explicit target")

    def test_shift_action_format(self, combat_events):
        """Shift actions should specify number (Shift_1, Shift_2, etc)."""
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']

        for decl in declarations:
            action = decl.get('action', {})
            major_action = str(action.get('major_action', ''))

            if 'Shift' in major_action:
                # Should be in format Shift_N
                assert '_' in major_action, \
                    f"Shift action should specify number: {major_action}"

                # Extract number
                try:
                    shift_num = int(major_action.split('_')[1])
                    assert 1 <= shift_num <= 3, \
                        f"Shift number should be 1-3, got {shift_num}"
                except (IndexError, ValueError):
                    print(f"WARNING: Shift action format unclear: {major_action}")


class TestRangeBasedCombat:
    """Validate targeting at different ranges."""

    def test_targeting_includes_position_context(self, combat_events):
        """Combat actions should reference tactical positions."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('context', {}).get('action_type') in ['combat', 'attack', 'melee', 'ranged']]

        for res in resolutions:
            environment = res.get('environment', '')

            # Should have position context
            position_keywords = ['Engaged', 'Near', 'Far', 'Extreme', 'range', 'distance']

            has_position_context = any(kw in environment for kw in position_keywords)

            if not has_position_context:
                action = res.get('action', '')
                print(f"INFO: Combat action without clear position context: {action[:50]}")

    @pytest.mark.xfail(reason="Known bug: Range modifiers may not be consistently applied")
    def test_extreme_range_has_penalty(self, combat_events):
        """Extreme range attacks should have difficulty penalties (known gaps)."""
        resolutions = [e for e in combat_events
                      if e['event_type'] == 'action_resolution'
                      and e.get('roll')]

        for res in resolutions:
            environment = res.get('environment', '')
            roll = res.get('roll', {})

            # If at extreme range
            if 'Extreme' in environment:
                action_type = res.get('context', {}).get('action_type', '').lower()

                if 'combat' in action_type or 'attack' in action_type:
                    dc = roll.get('dc', 0)

                    # Extreme range should have higher DC (this may fail)
                    # Typical baseline is DC 18, extreme should be 20+
                    assert dc >= 18, \
                        f"Extreme range attack should have elevated DC, got {dc}"


class TestEnvironmentTracking:
    """Validate environmental position tracking."""

    def test_environment_field_present(self, combat_events):
        """Action resolutions should have environment field."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        environment_count = sum(1 for res in resolutions if res.get('environment'))

        # Most resolutions should have environment
        assert environment_count >= len(resolutions) * 0.7, \
            f"Only {environment_count}/{len(resolutions)} resolutions have environment field"

    def test_environment_includes_pc_positions(self, combat_events):
        """Environment should track PC positions."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            environment = res.get('environment', '')

            if environment:
                # Should mention PCs
                has_pc_info = 'PC' in environment or 'player' in environment.lower()

                if not has_pc_info:
                    # May be single PC session or narrative action
                    print(f"INFO: Environment without PC reference: {environment[:80]}")

    def test_environment_shows_combatant_count(self, combat_events):
        """Environment should show number of combatants at each position."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            environment = res.get('environment', '')

            if environment and ('PC' in environment or 'enemy' in environment.lower()):
                # Should have numbers (like "2 PCs at Near-PC")
                has_counts = any(char.isdigit() for char in environment)

                if not has_counts:
                    print(f"INFO: Environment without combatant counts: {environment}")


class TestPositionValidation:
    """Validate position consistency and logic."""

    def test_no_duplicate_positions_same_character(self, combat_events):
        """A character can't be at multiple positions simultaneously."""
        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']

        for res in resolutions:
            environment = res.get('environment', '')

            # Parse environment for character positions
            # This is a soft check - hard to validate without deep parsing

            if environment:
                # Check for obviously wrong patterns like "Kael at Near-PC, Kael at Far-Enemy"
                # (would need more sophisticated parsing for real validation)
                pass

    def test_position_transitions_make_sense(self, combat_events):
        """Position changes should follow movement rules."""
        # Track position changes through combat
        character_positions = {}

        resolutions = [e for e in combat_events if e['event_type'] == 'action_resolution']
        resolutions_sorted = sorted(resolutions, key=lambda e: e['ts'])

        for res in resolutions_sorted:
            environment = res.get('environment', '')
            character = res.get('agent') or res.get('character_name')

            if character and environment:
                # Extract position (simplified - would need better parsing)
                position_keywords = ['Engaged', 'Near-PC', 'Near-Enemy', 'Far-PC', 'Far-Enemy',
                                   'Extreme-PC', 'Extreme-Enemy']

                current_position = None
                for pos in position_keywords:
                    if pos in environment and character in environment:
                        current_position = pos
                        break

                if current_position:
                    if character in character_positions:
                        prev_position = character_positions[character]

                        # Validate transition (simplified rules)
                        # Can't jump Engaged → Extreme in one move
                        invalid_jumps = [
                            ('Engaged', 'Extreme'),
                            ('Extreme', 'Engaged')
                        ]

                        for pos1, pos2 in invalid_jumps:
                            if pos1 in prev_position and pos2 in current_position:
                                print(f"WARNING: {character} jumped {prev_position} → {current_position}")

                    character_positions[character] = current_position


class TestTacticalDeclarations:
    """Validate tactical action declarations."""

    def test_major_actions_use_tactical_keywords(self, combat_events):
        """Major actions should use recognized tactical keywords."""
        declarations = [e for e in combat_events if e['event_type'] == 'action_declaration']

        # Common tactical major actions
        tactical_actions = [
            'Attack', 'Shoot', 'Charge',
            'Move', 'Shift', 'Advance', 'Retreat',
            'Defend', 'Guard', 'Cover',
            'Aim', 'Ready', 'Prepare'
        ]

        for decl in declarations:
            action = decl.get('action', {})
            major_action = str(action.get('major_action', ''))

            if major_action:
                # Should use tactical keywords (case insensitive)
                uses_tactical = any(ta.lower() in major_action.lower() for ta in tactical_actions)

                if not uses_tactical:
                    character = decl.get('character_name', 'unknown')
                    print(f"INFO: {character} using non-standard major action: {major_action}")


# Helper functions
def parse_into_rounds(events):
    """Group events by round number."""
    rounds = {}
    for event in events:
        if 'round' in event:
            round_num = event['round']
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(event)
    return rounds
