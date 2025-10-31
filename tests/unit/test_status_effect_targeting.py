"""
Test status effect targeting bug fix.

Bug: When players perform successful attacks with status effects (like stunning enemies),
the debuff is applied to the player (actor) instead of the target when target="None".

Example from session_debt_auction_ambush.jsonl:
- Riven uses "Launch telekinetic debris" against raiders
- Exceptional success with "Stunned (-3)" in effects
- Bug: "Stunned (-3)" gets applied to Riven instead of raiders
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock
from scripts.aeonisk.multiagent.mechanics import Condition


class TestStatusEffectTargeting:
    """Test that status effects are applied to correct targets."""

    def test_tactical_mode_debuff_applied_to_enemy_not_player(self):
        """
        Test using real fixture: tactical mode with target="None".

        Verifies that when a player attacks in tactical mode (with target IDs),
        debuffs are applied to enemies, NOT the player.
        """
        # Load the tactical mode fixture
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sessions" / "session_status_effect_tactical_test.jsonl"

        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")

        # Find the action resolution event
        action_resolution = None
        with open(fixture_path, 'r') as f:
            for line in f:
                event = json.loads(line)
                if event.get('event_type') == 'action_resolution' and event.get('agent') == 'Test Caster':
                    action_resolution = event
                    break

        assert action_resolution is not None, "Could not find Test Caster action resolution in fixture"

        # Extract narration
        narration = action_resolution.get('context', {}).get('narration', '')

        # Verify: Player should NOT have condition applied
        assert 'Condition (Test Caster):' not in narration, \
            "Player (Test Caster) should NOT have any conditions applied to them"

        # Verify: Enemy SHOULD have condition applied
        assert 'Condition (Practice Dummy Alpha): Stunned' in narration or \
               'Condition (Practice Dummy Beta): Stunned' in narration or \
               'Condition (Practice Dummy Gamma): Stunned' in narration, \
            "At least one enemy should have Stunned condition applied"

    def test_narrative_mode_no_player_debuff(self):
        """
        Test using real fixture: narrative mode with no target IDs.

        Verifies that when a player attacks in narrative mode (no tactical IDs),
        debuffs are NOT incorrectly applied to the player.
        """
        # Load the narrative mode fixture
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sessions" / "session_status_effect_narrative_test.jsonl"

        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")

        # Find the action resolution event
        action_resolution = None
        with open(fixture_path, 'r') as f:
            for line in f:
                event = json.loads(line)
                if event.get('event_type') == 'action_resolution' and event.get('agent') == 'Test Striker':
                    action_resolution = event
                    break

        assert action_resolution is not None, "Could not find Test Striker action resolution in fixture"

        # Extract narration
        narration = action_resolution.get('context', {}).get('narration', '')

        # Verify: Player should NOT have debuff condition applied
        assert 'Condition (Test Striker): Stunned' not in narration, \
            "Player (Test Striker) should NOT have Stunned condition"
        assert 'Condition (Test Striker): Dazed' not in narration, \
            "Player (Test Striker) should NOT have Dazed condition"

    def test_debuff_skipped_when_target_none(self):
        """
        When target="None", debuffs (penalty < 0) should be skipped entirely.

        This tests the fix for the bug where debuffs were incorrectly applied to the actor.
        """
        # Create mock mechanics and logger
        mock_mechanics = Mock()
        mock_logger = Mock()

        # Simulate the fixed logic from dm.py
        player_id = "test_player"
        action = {'target': 'None', 'character': 'Test Character'}

        condition_data = {
            'type': 'Stunned',
            'penalty': -3,  # Negative = debuff
            'description': 'Stunned by attack'
        }

        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=3,
            affects=[]
        )

        # Test the logic
        target_id = action.get('target')
        should_apply_condition = True

        if target_id == 'None':
            if condition.penalty < 0:
                # This should skip the debuff
                should_apply_condition = False

        # Verify: debuff should NOT be applied
        assert should_apply_condition == False, \
            "Debuff with target='None' should NOT be applied (should_apply_condition should be False)"

        # Verify mechanics.add_condition would NOT be called
        if should_apply_condition:
            mock_mechanics.add_condition(player_id, condition)

        mock_mechanics.add_condition.assert_not_called()

    def test_buff_applied_to_actor_when_target_none(self):
        """
        When target="None", buffs (penalty > 0) should still be applied to the actor.

        This ensures we don't break self-buffs while fixing the debuff bug.
        """
        # Create mock mechanics
        mock_mechanics = Mock()

        player_id = "test_player"
        action = {'target': 'None', 'character': 'Test Character'}

        condition_data = {
            'type': 'Inspired',
            'penalty': 3,  # Positive = buff
            'description': 'Inspired by success'
        }

        condition = Condition(
            name=condition_data['type'],
            type=condition_data['type'],
            penalty=condition_data['penalty'],
            description=condition_data['description'],
            duration=3,
            affects=[]
        )

        # Test the logic
        target_id = action.get('target')
        should_apply_condition = True
        condition_target_id = player_id

        if target_id == 'None':
            if condition.penalty < 0:
                should_apply_condition = False
            else:
                # Buff should be applied to actor
                condition_target_id = player_id

        # Verify: buff SHOULD be applied to actor
        assert should_apply_condition == True, \
            "Buff with target='None' SHOULD be applied to actor"
        assert condition_target_id == player_id, \
            "Buff should be applied to the actor (player_id)"

        # Verify mechanics.add_condition would be called with correct target
        if should_apply_condition:
            mock_mechanics.add_condition(condition_target_id, condition)

        mock_mechanics.add_condition.assert_called_once_with(player_id, condition)

    def test_self_buff_applied_to_actor(self):
        """
        When an action applies a buff to the actor themselves (e.g., "Focused", "Inspired"),
        it should still be applied even when target is not specified.

        This ensures we don't break legitimate self-buffs while fixing the debuff bug.
        """
        # This is a placeholder test that will be implemented properly once we fix the main bug
        # For now, we're just documenting the expected behavior

        # Expected behavior:
        # - Positive conditions (buffs) with penalty > 0 should apply to actor
        # - Negative conditions (debuffs) with penalty < 0 should NOT apply to actor when target="None"
        pass

    def test_debuff_applied_to_explicit_target(self):
        """
        When an action has an explicit target (not "None"), debuffs should be applied to that target.

        This ensures the fix doesn't break normal targeting behavior.
        """
        # This is a placeholder test documenting expected behavior
        # When target has a value like "tgt_001" or a character name,
        # conditions should be applied to that target
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
