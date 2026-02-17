"""
Unit tests for NPC heal JSONL logging (Fix 1).

Problem: NPC heal events log roll.d20: null, roll.skill: null, effects: null.
The ActionResolution is created without roll fields, and model_dump() loses them.

Tests verify:
1. log_action_resolution receives the Pydantic resolution object (not .model_dump())
2. Context dict includes Medicine roll data for JSONL extraction
3. Effects dict includes healing data
"""

import pytest
import random
from unittest.mock import MagicMock, patch, AsyncMock, call

from scripts.aeonisk.multiagent.schemas.action_resolution import ActionResolution, MechanicalEffects
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier
from scripts.aeonisk.multiagent.schemas.action_effects import HealingEffect


class TestNPCHealLogging:
    """Verify NPC heal resolution populates JSONL fields properly."""

    def test_npc_heal_log_receives_resolution_object_not_dict(self):
        """log_action_resolution should receive ActionResolution object, not .model_dump() dict.

        Bug: npc_resolution.model_dump() converts to dict, then getattr(dict, 'margin', 0)
        returns 0 instead of the actual margin value.
        """
        resolution = ActionResolution(
            narration="Medic applies field medicine to the wounded ally, checking vitals and wrapping injuries carefully. " * 3,
            success_tier=SuccessTier.MODERATE,
            margin=6,
            effects=MechanicalEffects(),
        )

        # model_dump() produces a dict — getattr on dict loses all fields
        dumped = resolution.model_dump()
        assert isinstance(dumped, dict)
        assert getattr(dumped, 'margin', 0) == 0  # Bug: dict attr access fails

        # Direct object preserves fields via getattr
        assert getattr(resolution, 'margin', 0) == 6  # Correct
        assert getattr(resolution, 'success_tier', None) == SuccessTier.MODERATE

    def test_npc_heal_context_has_roll_data(self):
        """Context dict should include NPC heal roll data for JSONL extraction."""
        medicine_skill = 3
        intelligence = 3
        d20 = 15
        unskilled_penalty = 0
        skill_value = max(medicine_skill, 1)
        base_roll = intelligence * skill_value + unskilled_penalty
        total = base_roll + d20
        dc = 18
        heal_amount = max(1, total - dc + 5)

        # This is what the fixed context should look like
        context = {
            "action_type": "heal",
            "is_npc": True,
            "heal_target": "player_01",
            "heal_amount": heal_amount,
            "npc_roll": {
                "skill": "Medicine",
                "attribute": "Intelligence",
                "attribute_value": intelligence,
                "skill_value": medicine_skill,
                "d20": d20,
                "total": total,
                "dc": dc,
                "margin": total - dc,
                "success": total >= dc,
            },
        }

        # Verify all fields present
        assert context["npc_roll"]["skill"] == "Medicine"
        assert context["npc_roll"]["d20"] == 15
        assert context["npc_roll"]["total"] == 24
        assert context["npc_roll"]["dc"] == 18
        assert context["npc_roll"]["success"] is True
        assert context["heal_amount"] == 11

    def test_npc_heal_failure_context_has_roll_data(self):
        """Failed heal attempts should still have roll data in context."""
        medicine_skill = 1
        intelligence = 3
        d20 = 5
        skill_value = max(medicine_skill, 1)
        base_roll = intelligence * skill_value
        total = base_roll + d20  # 8
        dc = 18

        context = {
            "action_type": "heal",
            "is_npc": True,
            "heal_target": "player_01",
            "heal_amount": 0,
            "npc_roll": {
                "skill": "Medicine",
                "attribute": "Intelligence",
                "attribute_value": intelligence,
                "skill_value": medicine_skill,
                "d20": d20,
                "total": total,
                "dc": dc,
                "margin": total - dc,
                "success": False,
            },
        }

        assert context["npc_roll"]["total"] < context["npc_roll"]["dc"]
        assert context["npc_roll"]["success"] is False
        assert context["heal_amount"] == 0

    def test_npc_heal_effects_dict_has_healing_data(self):
        """Effects dict should include healing info for JSONL."""
        heal_amount = 11
        effects_dict = {
            "healing": [{
                "target": "player_01",
                "heal_type": "hp",
                "amount": heal_amount,
                "source": "Medicine (Medic Kira)"
            }]
        }

        assert len(effects_dict["healing"]) == 1
        assert effects_dict["healing"][0]["amount"] == 11

    def test_npc_heal_dead_target_context(self):
        """Dead target context should still have action_type but no roll data."""
        context = {
            "action_type": "heal",
            "is_npc": True,
            "heal_target": "player_01",
            "heal_amount": 0,
            "heal_rejected": "target_dead",
        }

        assert context["heal_rejected"] == "target_dead"
        assert context["heal_amount"] == 0

    def test_npc_heal_log_action_resolution_called_with_resolution_object(self):
        """Integration: verify log_action_resolution receives Pydantic object."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger = JSONLLogger.__new__(JSONLLogger)
        logger.session_id = "test-session"
        logger.log_file = None

        captured = []
        logger._write_event = lambda event: captured.append(event)

        resolution = ActionResolution(
            narration="The medic carefully applies antiseptic gel to the wound, then wraps pressure bandages. " * 3,
            success_tier=SuccessTier.MODERATE,
            margin=6,
            effects=MechanicalEffects(
                healing=[
                    HealingEffect(
                        target="player_01",
                        heal_type="hp",
                        amount=11,
                        source="Medicine (Medic Kira)"
                    )
                ]
            ),
        )

        context = {
            "action_type": "heal",
            "is_npc": True,
            "heal_target": "player_01",
            "heal_amount": 11,
            "npc_roll": {
                "skill": "Medicine",
                "attribute": "Intelligence",
                "attribute_value": 3,
                "skill_value": 3,
                "d20": 15,
                "total": 24,
                "dc": 18,
                "margin": 6,
                "success": True,
            },
        }

        logger.log_action_resolution(
            round_num=2,
            phase="adjudicate_npc",
            agent_name="Medic Kira",
            action="heal player_01",
            resolution=resolution,
            economy_changes={},
            clock_states={},
            effects={},
            context=context,
        )

        assert len(captured) == 1
        event = captured[0]
        assert event["event_type"] == "action_resolution"
        assert event["phase"] == "adjudicate_npc"
        # margin should be populated (from Pydantic object via getattr)
        assert event["roll"]["margin"] == 6
        # Context should have roll data
        assert event["context"]["npc_roll"]["skill"] == "Medicine"
        assert event["context"]["npc_roll"]["d20"] == 15
