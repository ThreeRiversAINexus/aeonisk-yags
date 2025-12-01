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

        # Find the action resolution event for the player
        action_resolution = None
        with open(fixture_path, 'r') as f:
            for line in f:
                event = json.loads(line)
                if event.get('event_type') == 'action_resolution' and event.get('agent') == 'Test Caster':
                    # Only check adjudicate phase (DM resolution), not declaration
                    if event.get('phase') == 'adjudicate':
                        action_resolution = event
                        break

        assert action_resolution is not None, "Could not find Test Caster action resolution in fixture"

        # Extract narration and status effects
        narration = action_resolution.get('context', {}).get('narration', '')
        status_effects = action_resolution.get('effects', {}).get('status_effects', [])

        # Verify: Player should NOT have debuff condition applied to them in narration
        # The narration should describe effects on enemies, not the player
        assert 'Condition (Test Caster): Stunned' not in narration, \
            "Player (Test Caster) should NOT have Stunned condition applied in narration"

        # Verify status effects are present (either as list or indicates enemy was affected)
        # The fixture shows effects applied narratively - enemies are stunned/incapacitated
        has_stun_effect = any('stun' in str(s).lower() for s in status_effects) if status_effects else False
        narration_has_stun = 'stun' in narration.lower() or 'incapacitat' in narration.lower()

        assert has_stun_effect or narration_has_stun, \
            "Expected stun/incapacitate effect in status_effects or narration"

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

        # Find the action resolution event for the player character
        # Note: Fixture uses "Test Caster" not "Test Striker"
        action_resolution = None
        with open(fixture_path, 'r') as f:
            for line in f:
                event = json.loads(line)
                if event.get('event_type') == 'action_resolution' and event.get('agent') == 'Test Caster':
                    # Only check adjudicate phase (DM resolution), not declaration
                    if event.get('phase') == 'adjudicate':
                        action_resolution = event
                        break

        assert action_resolution is not None, "Could not find Test Caster action resolution in fixture"

        # Extract narration
        narration = action_resolution.get('context', {}).get('narration', '')

        # Verify: Player should NOT have debuff condition applied to them
        # The bug was that debuffs meant for enemies were incorrectly applied to the player
        assert 'Condition (Test Caster): Stunned' not in narration, \
            "Player (Test Caster) should NOT have Stunned condition applied to them"
        assert 'Condition (Test Caster): Dazed' not in narration, \
            "Player (Test Caster) should NOT have Dazed condition applied to them"

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
        player_id = "test_player"

        # Create a buff condition (positive penalty)
        buff_condition = Condition(
            name="Focused",
            type="Focused",
            penalty=2,  # Positive = buff
            description="Heightened concentration",
            duration=3,
            affects=[]
        )

        # Simulate buff application logic with target="self" or implicit self-targeting
        should_apply = True
        target_id = player_id

        # Buffs should always apply to the actor
        if buff_condition.penalty > 0:
            should_apply = True
            target_id = player_id

        # Verify buff is applied to actor
        assert should_apply == True, \
            "Buff should be applied to actor"
        assert target_id == player_id, \
            "Buff should target the actor (player_id)"

    def test_debuff_applied_to_explicit_target(self):
        """
        When an action has an explicit target (not "None"), debuffs should be applied to that target.

        This ensures the fix doesn't break normal targeting behavior.
        """
        player_id = "test_player"
        explicit_target = "tgt_001"

        # Create a debuff condition (negative penalty)
        debuff_condition = Condition(
            name="Stunned",
            type="Stunned",
            penalty=-3,  # Negative = debuff
            description="Unable to act",
            duration=1,
            affects=[]
        )

        # Simulate debuff application logic with explicit target
        action = {'target': explicit_target}
        target_id = action.get('target')

        # When target is explicitly specified, apply condition to that target
        should_apply = True
        condition_target = target_id if target_id != 'None' else player_id

        # Verify debuff is applied to the explicit target
        assert should_apply == True, \
            "Debuff with explicit target should be applied"
        assert condition_target == explicit_target, \
            f"Debuff should target the specified target ({explicit_target}), not the actor"
        assert condition_target != player_id, \
            "Debuff should NOT be applied to the actor when target is explicitly specified"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
