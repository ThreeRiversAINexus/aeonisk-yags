"""
Tests for EnemyDecision schema — Wait, Dialogue, Surrender action types.

TDD: Written BEFORE implementation to define expected behavior.
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.schemas.enemy_decision import EnemyDecision


class TestWaitAction:
    """Wait action: observe, maintain position, no offensive action."""

    def test_wait_action_valid(self):
        decision = EnemyDecision(
            major_action="Wait",
            tactical_reasoning="No clear hostiles detected, maintaining position and observing the situation"
        )
        assert decision.major_action == "Wait"

    def test_wait_no_target_needed(self):
        decision = EnemyDecision(
            major_action="Wait",
            target=None,
            weapon=None,
            tactical_reasoning="Observing strangers at checkpoint before engaging"
        )
        assert decision.target is None
        assert decision.weapon is None

    def test_wait_preserves_defence_token(self):
        decision = EnemyDecision(
            major_action="Wait",
            defence_token="tgt_a1b2",
            tactical_reasoning="Holding position but keeping watch on the suspicious individual"
        )
        assert decision.defence_token == "tgt_a1b2"


class TestDialogueAction:
    """Dialogue action: verbal interaction (challenge, warn, demand, negotiate)."""

    def test_dialogue_action_valid(self):
        decision = EnemyDecision(
            major_action="Dialogue",
            dialogue_content="Halt! Identify yourselves or we will open fire!",
            tactical_reasoning="Challenging unknown intruders before engaging — need to determine intent"
        )
        assert decision.major_action == "Dialogue"
        assert decision.dialogue_content == "Halt! Identify yourselves or we will open fire!"

    def test_dialogue_requires_content(self):
        """Dialogue without dialogue_content should fail validation."""
        with pytest.raises(ValidationError):
            EnemyDecision(
                major_action="Dialogue",
                dialogue_content=None,
                tactical_reasoning="Attempting to challenge intruders at the checkpoint"
            )

    def test_dialogue_without_content_fails_validation(self):
        """Dialogue with empty string should fail min_length validation."""
        with pytest.raises(ValidationError):
            EnemyDecision(
                major_action="Dialogue",
                dialogue_content="",
                tactical_reasoning="Attempting to challenge intruders at the checkpoint"
            )

    def test_dialogue_preserves_defence_token(self):
        decision = EnemyDecision(
            major_action="Dialogue",
            dialogue_content="Drop your weapons! This is your only warning!",
            defence_token="tgt_c3d4",
            tactical_reasoning="Warning the intruders while maintaining defensive watch"
        )
        assert decision.defence_token == "tgt_c3d4"

    def test_dialogue_content_max_length(self):
        """Dialogue content has reasonable max length."""
        with pytest.raises(ValidationError):
            EnemyDecision(
                major_action="Dialogue",
                dialogue_content="x" * 501,
                tactical_reasoning="Testing max length constraint on dialogue content field"
            )


class TestSurrenderAction:
    """Surrender action: voluntary capitulation."""

    def test_surrender_action_valid(self):
        decision = EnemyDecision(
            major_action="Surrender",
            tactical_reasoning="Outnumbered and outgunned, surrender is the only option to survive this encounter"
        )
        assert decision.major_action == "Surrender"

    def test_surrender_reasoning_required(self):
        """Surrender still requires tactical_reasoning (min_length=20)."""
        with pytest.raises(ValidationError):
            EnemyDecision(
                major_action="Surrender",
                tactical_reasoning=""  # Too short
            )


class TestLegacyActionsStillWork:
    """Existing action types must not break."""

    def test_attack_still_valid(self):
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_1234",
            weapon="Pistol",
            tactical_reasoning="Engaging primary target at close range with sidearm"
        )
        assert decision.major_action == "Attack"

    def test_flee_still_valid(self):
        decision = EnemyDecision(
            major_action="FLEE",
            tactical_reasoning="Morale broken, attempting to flee the combat zone immediately"
        )
        assert decision.major_action == "FLEE"

    def test_retreat_still_valid(self):
        decision = EnemyDecision(
            major_action="Retreat",
            tactical_reasoning="Health critical, retreating to regroup with allies at safe position"
        )
        assert decision.major_action == "Retreat"


class TestDialogueValidatorEdgeCases:
    """Non-Dialogue actions should NOT require dialogue_content."""

    def test_attack_without_dialogue_content_is_fine(self):
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_1234",
            weapon="Rifle",
            tactical_reasoning="Engaging hostile target with primary weapon from cover position"
        )
        assert decision.dialogue_content is None

    def test_wait_without_dialogue_content_is_fine(self):
        decision = EnemyDecision(
            major_action="Wait",
            tactical_reasoning="Holding position and observing the area for hostile activity"
        )
        assert decision.dialogue_content is None

    def test_surrender_without_dialogue_content_is_fine(self):
        decision = EnemyDecision(
            major_action="Surrender",
            tactical_reasoning="Cornered with no ammunition remaining, surrender is the only option"
        )
        assert decision.dialogue_content is None


class TestToLegacyDict:
    """to_legacy_dict should include new fields."""

    def test_dialogue_legacy_dict_includes_content(self):
        decision = EnemyDecision(
            major_action="Dialogue",
            dialogue_content="Stand down!",
            tactical_reasoning="Warning shot across the bow before committing to engagement"
        )
        d = decision.to_legacy_dict()
        assert d['major_action'] == "Dialogue"
        assert d.get('dialogue_content') == "Stand down!"

    def test_get_summary_wait(self):
        decision = EnemyDecision(
            agent_id="enemy_01",
            character_name="Guard Alpha",
            initiative=15,
            major_action="Wait",
            tactical_reasoning="Observing the area while maintaining defensive posture"
        )
        summary = decision.get_summary()
        assert "Wait" in summary
        assert "Guard Alpha" in summary
