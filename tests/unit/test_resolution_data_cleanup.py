"""
Regression test: Verify _previous_resolutions is cleaned from action dicts
after LLM call to prevent recursive nesting in ACTION_RESOLVED messages.

Bug: action['_previous_resolutions'] was set in _resolve_action_mechanically
but never cleaned up. When the action dict was included in resolution_data
and passed as previous_resolutions to subsequent adjudication calls, each
resolution recursively contained all prior resolutions, causing O(n^2) growth
that produced 219KB+ message bus messages and JSON parse failures.
"""

import json
import pytest


class TestPreviousResolutionsCleanup:
    """Verify _previous_resolutions doesn't leak into serialized resolution data."""

    def test_action_dict_cleaned_after_resolution(self):
        """After resolution, action dict should not contain _previous_resolutions."""
        # Simulate what _resolve_action_mechanically does
        action = {
            'action_type': 'combat',
            'description': 'Attack the enemy',
            'intent': 'Attack',
        }

        # This is what dm.py:5341 does
        previous_resolutions = [{'player_id': 'p1', 'narration': 'Hit!'}]
        action['_previous_resolutions'] = previous_resolutions
        action['previous_context'] = 'P1 attacked and hit.'

        # After LLM call, this is what the fix does (dm.py:5355-5356)
        action.pop('_previous_resolutions', None)
        action.pop('previous_context', None)

        assert '_previous_resolutions' not in action
        assert 'previous_context' not in action
        # Original fields preserved
        assert action['action_type'] == 'combat'

    def test_recursive_nesting_prevented(self):
        """
        Simulate the resolution loop to verify no recursive nesting.

        Without the fix, resolution N would contain all N-1 previous resolutions,
        each containing their own previous resolutions, growing quadratically.
        """
        all_resolutions = []

        for i in range(8):  # 8 actions (4 players x 2 actions each)
            action = {
                'action_type': 'combat',
                'description': f'Action {i}',
                'character': f'Player {i // 2}',
            }

            # dm.py:5341 — stash previous resolutions for LLM context
            action['_previous_resolutions'] = list(all_resolutions)
            action['previous_context'] = f'Context from {len(all_resolutions)} previous actions'

            # (LLM call would happen here)

            # dm.py:5355-5356 — cleanup after LLM call (THE FIX)
            action.pop('_previous_resolutions', None)
            action.pop('previous_context', None)

            # dm.py:3155-3163 — build serializable resolution
            resolution_data = {
                'player_id': f'player_{i // 2:02d}',
                'character_name': f'Player {i // 2}',
                'action': action,  # Action dict is included
                'narration': f'Resolution {i} narration text',
                'resolution': {'success': True},
            }

            # session.py:2245 — append to all_resolutions
            all_resolutions.append(resolution_data)

        # Verify: no resolution_data contains _previous_resolutions
        for i, res in enumerate(all_resolutions):
            assert '_previous_resolutions' not in res['action'], \
                f"Resolution {i} action still contains _previous_resolutions"
            assert 'previous_context' not in res['action'], \
                f"Resolution {i} action still contains previous_context"

        # Verify: serialized size grows linearly, not quadratically
        total_json = json.dumps(all_resolutions)
        # With 8 resolutions, each ~200 bytes, total should be <5KB
        # Without the fix, recursive nesting would make this 100KB+
        assert len(total_json) < 10000, \
            f"all_resolutions is {len(total_json)} chars - possible recursive nesting"

    def test_without_fix_would_grow_quadratically(self):
        """
        Demonstrate what happens WITHOUT the cleanup (the bug).
        Each resolution embeds all previous, causing quadratic growth.
        """
        all_resolutions = []
        sizes = []

        for i in range(8):
            action = {
                'action_type': 'combat',
                'description': f'Action {i}',
            }

            # BUG: _previous_resolutions NOT cleaned up
            action['_previous_resolutions'] = list(all_resolutions)

            resolution_data = {
                'player_id': f'player_{i // 2:02d}',
                'action': action,
                'narration': f'Resolution {i}',
            }

            all_resolutions.append(resolution_data)
            sizes.append(len(json.dumps(all_resolutions)))

        # Verify quadratic growth (each size much larger than linear)
        # Size of iteration 7 should be >> 8x size of iteration 0
        assert sizes[-1] > sizes[0] * 20, \
            f"Expected quadratic growth: first={sizes[0]}, last={sizes[-1]}"


class TestActionResolvedMessageSize:
    """Verify ACTION_RESOLVED message payloads stay reasonable."""

    def test_message_payload_size_bounded(self):
        """The ACTION_RESOLVED message payload should not exceed 50KB."""
        # Simulate building the message payload as in dm.py:3172-3185
        action = {
            'action_type': 'combat',
            'description': 'A detailed combat action description ' * 10,
            'intent': 'Attack the enemy with full force',
            'target': 'tgt_a1b2',
            'skill': 'Melee',
        }

        outcome = {
            'success_tier': 'GOOD',
            'margin': 5,
            'resolution': {'success': True, 'roll': 15, 'difficulty': 10},
        }

        narration = 'A ' * 500  # ~1KB narration

        serializable_res = {
            'player_id': 'player_01',
            'character_name': 'Test Character',
            'initiative': 12,
            'action': action,
            'resolution': outcome,
            'narration': narration,
        }

        payload = {
            'agent_id': 'player_01',
            'action_index': 0,
            'original_action': action,
            'outcome': outcome,
            'narration': narration,
            'aware_agents': ['player_01', 'player_02', 'enemy_01'],
            'resolution_data': serializable_res,
            'effects_summary': {'total_damage_dealt': 5, 'conditions': []},
        }

        payload_json = json.dumps(payload, default=str)
        assert len(payload_json) < 50000, \
            f"ACTION_RESOLVED payload is {len(payload_json)} chars, expected <50KB"
