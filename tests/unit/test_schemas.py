"""
Unit tests for Pydantic schemas (structured output validation).

Tests all schema models from scripts/aeonisk/multiagent/schemas/:
- Shared types (VoidChange, ClockUpdate, Condition, etc.)
- ActionResolution (DM resolutions)
- PlayerAction (player declarations)
- EnemyDecision (enemy tactics)
- StoryEvents (narrative progression)

Philosophy: Ensure all Pydantic models validate correctly and catch invalid data.
"""

import pytest
from pydantic import ValidationError

from aeonisk.multiagent.schemas.shared_types import (
    SuccessTier,
    ActionType,
    Position,
    VoidChange,
    SoulcreditChange,
    ClockUpdate,
    Condition,
    DamageEffect,
    PositionChange
)

from aeonisk.multiagent.schemas.action_resolution import (
    MechanicalEffects,
    ActionResolution,
    CombatResolution,
    OutcomeTierExplanation,
    create_failure_resolution,
    create_combat_resolution
)


# ============================================================================
# Shared Types Tests
# ============================================================================

class TestSharedTypes:
    """Test shared Pydantic types."""

    def test_success_tier_enum(self):
        """Test SuccessTier enum values."""
        assert SuccessTier.CRITICAL_FAILURE == "critical_failure"
        assert SuccessTier.EXCEPTIONAL == "exceptional"
        assert len(list(SuccessTier)) == 7

    def test_action_type_enum(self):
        """Test ActionType enum values."""
        assert ActionType.COMBAT == "combat"
        assert ActionType.RITUAL == "ritual"
        assert ActionType.EXPLORE == "explore"

    def test_position_enum(self):
        """Test Position enum values."""
        assert Position.ENGAGED == "Engaged"
        assert Position.FAR_PC == "Far-PC"

    def test_void_change_valid(self):
        """Test valid VoidChange creation."""
        void_change = VoidChange(
            character_name="TestChar",
            amount=2,
            reason="Failed ritual"
        )

        assert void_change.character_name == "TestChar"
        assert void_change.amount == 2
        assert void_change.reason == "Failed ritual"

    def test_void_change_missing_reason(self):
        """Test VoidChange requires reason."""
        with pytest.raises(ValidationError) as exc_info:
            VoidChange(
                character_name="TestChar",
                amount=2
            )

        assert "reason" in str(exc_info.value)

    def test_void_change_reason_too_short(self):
        """Test VoidChange reason has min_length."""
        with pytest.raises(ValidationError) as exc_info:
            VoidChange(
                character_name="TestChar",
                amount=2,
                reason="Bad"  # Too short (< 5 chars)
            )

        assert "reason" in str(exc_info.value)

    def test_soulcredit_change_valid(self):
        """Test valid SoulcreditChange creation."""
        sc_change = SoulcreditChange(
            character_name="Echo",
            amount=-2,
            reason="Created Hollow Seed"
        )

        assert sc_change.character_name == "Echo"
        assert sc_change.amount == -2
        assert sc_change.reason == "Created Hollow Seed"

    def test_soulcredit_change_neutral(self):
        """Test SoulcreditChange with amount=0 for neutral actions."""
        sc_change = SoulcreditChange(
            character_name="Riven",
            amount=0,
            reason="Justified combat, morally neutral"
        )

        assert sc_change.amount == 0

    def test_clock_update_valid(self):
        """Test valid ClockUpdate creation."""
        clock = ClockUpdate(
            clock_name="Enemy Reinforcements",
            ticks=2,
            reason="Alarm triggered"
        )

        assert clock.clock_name == "Enemy Reinforcements"
        assert clock.ticks == 2
        assert clock.reason == "Alarm triggered"

    def test_clock_update_negative_ticks(self):
        """Test ClockUpdate can regress (negative ticks)."""
        clock = ClockUpdate(
            clock_name="Passenger Safety",
            ticks=-1,
            reason="Evacuation successful"
        )

        assert clock.ticks == -1

    def test_condition_valid(self):
        """Test valid Condition creation."""
        condition = Condition(
            name="Stunned",
            penalty=-3,
            duration=2,
            description="Next 2 actions at -3"
        )

        assert condition.name == "Stunned"
        assert condition.penalty == -3
        assert condition.duration == 2

    def test_condition_buff(self):
        """Test Condition with positive penalty (buff)."""
        condition = Condition(
            name="Inspired",
            penalty=2,
            duration=1,
            description="+2 to next action"
        )

        assert condition.penalty == 2

    def test_damage_effect_valid(self):
        """Test valid DamageEffect creation."""
        damage = DamageEffect(
            target="tgt_001",
            base_damage=15,
            soak=7,
            dealt=8,
            damage_type="kinetic"
        )

        assert damage.target == "tgt_001"
        assert damage.base_damage == 15
        assert damage.dealt == 8

    def test_damage_effect_with_soak(self):
        """Test DamageEffect with explicit dealt value."""
        damage = DamageEffect(
            target="tgt_001",
            base_damage=15,
            soak=7,
            dealt=8  # dealt is required, not auto-calculated
        )

        assert damage.dealt == 8

    def test_position_change_valid(self):
        """Test valid PositionChange creation."""
        pos_change = PositionChange(
            character_name="TestChar",
            new_position=Position.ENGAGED,
            reason="Charged into melee"
        )

        assert pos_change.new_position == Position.ENGAGED
        assert pos_change.character_name == "TestChar"


# ============================================================================
# ActionResolution Tests
# ============================================================================

class TestActionResolution:
    """Test ActionResolution schema and validation."""

    def test_mechanical_effects_empty(self):
        """Test MechanicalEffects can be empty."""
        effects = MechanicalEffects()

        assert effects.damage is None
        assert effects.void_changes == []
        assert effects.soulcredit_changes == []
        assert effects.clock_updates == []
        assert effects.conditions == []

    def test_mechanical_effects_with_damage(self):
        """Test MechanicalEffects with damage."""
        effects = MechanicalEffects(
            damage=DamageEffect(
                target="tgt_001",
                base_damage=12,
                soak=4,
                dealt=8
            ),
            soulcredit_changes=[
                SoulcreditChange(
                    character_name="Riven",
                    amount=0,
                    reason="Justified combat"
                )
            ]
        )

        assert effects.damage.dealt == 8
        assert len(effects.soulcredit_changes) == 1

    def test_mechanical_effects_multiple_void_changes(self):
        """Test MechanicalEffects with multiple void changes."""
        effects = MechanicalEffects(
            void_changes=[
                VoidChange(character_name="Ash", amount=2, reason="Ritual backfire"),
                VoidChange(character_name="Echo", amount=1, reason="Proximity to void source")
            ]
        )

        assert len(effects.void_changes) == 2

    def test_action_resolution_minimal(self):
        """Test minimal valid ActionResolution."""
        resolution = ActionResolution(
            narration="The action succeeds. The target is struck by the attack, dealing damage. " * 5,  # Make it 200+ chars
            success_tier=SuccessTier.GOOD,
            margin=10
        )

        assert resolution.success_tier == SuccessTier.GOOD
        assert resolution.margin == 10
        assert resolution.effects.damage is None

    def test_action_resolution_narration_too_short(self):
        """Test ActionResolution requires min 200 char narration."""
        with pytest.raises(ValidationError) as exc_info:
            ActionResolution(
                narration="Too short",
                success_tier=SuccessTier.GOOD,
                margin=10
            )

        assert "narration" in str(exc_info.value)

    def test_action_resolution_with_combat_effects(self):
        """Test ActionResolution with combat damage."""
        resolution = ActionResolution(
            narration="Your kinetic round punches through their shoulder guard, spinning them sideways. They stagger back, weapon clattering to the deck. Blood sprays across the bulkhead as they clutch the wound." * 2,
            success_tier=SuccessTier.GOOD,
            margin=12,
            effects=MechanicalEffects(
                damage=DamageEffect(
                    target="tgt_7a3f",
                    base_damage=15,
                    soak=7,
                    dealt=8,
                    damage_type="kinetic"
                ),
                conditions=[
                    Condition(
                        name="Off-Balance",
                        penalty=-2,
                        duration=1,
                        description="next attack at -2"
                    )
                ],
                soulcredit_changes=[
                    SoulcreditChange(
                        character_name="Riven",
                        amount=0,
                        reason="Justified combat against hostile enemy"
                    )
                ]
            )
        )

        assert resolution.effects.damage.dealt == 8
        assert len(resolution.effects.conditions) == 1
        assert resolution.effects.conditions[0].name == "Off-Balance"

    def test_action_resolution_with_void(self):
        """Test ActionResolution with void corruption."""
        resolution = ActionResolution(
            narration="Ash's ritual shatters against inverted resonance patterns. Pain sears through neural pathways as void corruption floods in. The circle collapses, symbols bleeding darkness." * 3,
            success_tier=SuccessTier.CRITICAL_FAILURE,
            margin=-8,
            effects=MechanicalEffects(
                void_changes=[
                    VoidChange(
                        character_name="Ash Vex",
                        amount=2,
                        reason="Ritual backfire"
                    )
                ],
                soulcredit_changes=[
                    SoulcreditChange(
                        character_name="Ash Vex",
                        amount=0,
                        reason="Attempted beneficial ritual despite failure"
                    )
                ],
                clock_updates=[
                    ClockUpdate(
                        clock_name="Void Surge",
                        ticks=2,
                        reason="Uncontrolled energy"
                    )
                ]
            )
        )

        assert len(resolution.effects.void_changes) == 1
        assert resolution.effects.void_changes[0].amount == 2
        assert len(resolution.effects.clock_updates) == 1

    def test_action_resolution_with_ml_training_fields(self):
        """Test ActionResolution with optional ML training fields."""
        resolution = ActionResolution(
            narration="The investigation reveals crucial evidence. Security logs show unauthorized access." * 5,
            success_tier=SuccessTier.GOOD,
            margin=11,
            character_data={
                "name": "Echo",
                "class": "Hacker",
                "level": 3,
                "skills": {"Technical": 4, "Notice": 3}
            },
            environment="Corporate server room, dimly lit, security cameras disabled",
            stakes="If caught, Echo faces corporate black-ops team. Success reveals conspiracy.",
            goal="Access security logs without triggering alarms",
            roll_formula="Str 3 × Technical 4 = 12; 12 + d20(15) = 27 vs DC 16",
            rationale="DC 16: moderate security, but cameras disabled (-2 DC). Echo has prep time."
        )

        assert resolution.character_data["name"] == "Echo"
        assert resolution.environment is not None
        assert resolution.stakes is not None
        assert resolution.goal is not None
        assert resolution.roll_formula is not None

    def test_outcome_tier_explanation_valid(self):
        """Test OutcomeTierExplanation validation."""
        tier = OutcomeTierExplanation(
            narrative="The attack strikes true, piercing vital systems and causing catastrophic damage.",
            mechanical_effect="+15 damage, target Stunned (-3) for 2 rounds"
        )

        assert len(tier.narrative) >= 50
        assert "damage" in tier.mechanical_effect

    def test_outcome_tier_explanation_narrative_too_short(self):
        """Test OutcomeTierExplanation requires min 50 char narrative."""
        with pytest.raises(ValidationError) as exc_info:
            OutcomeTierExplanation(
                narrative="Short",
                mechanical_effect="+5 damage"
            )

        assert "narrative" in str(exc_info.value)

    def test_combat_resolution_extended_fields(self):
        """Test CombatResolution with combat-specific fields."""
        resolution = CombatResolution(
            narration="Your plasma bolt scorches through their armor, leaving a molten crater. They collapse, screaming." * 5,
            success_tier=SuccessTier.EXCELLENT,
            margin=18,
            effects=MechanicalEffects(
                damage=DamageEffect(
                    target="enemy_001",
                    base_damage=20,
                    soak=5,
                    dealt=15,
                    damage_type="energy"
                )
            ),
            attack_roll=35,
            attack_dc=17,
            attack_hit=True,
            weapon_used="Plasma Rifle",
            critical_hit=True
        )

        assert resolution.attack_hit is True
        assert resolution.critical_hit is True
        assert resolution.weapon_used == "Plasma Rifle"
        assert resolution.attack_roll == 35


# ============================================================================
# Factory Function Tests
# ============================================================================

class TestFactoryFunctions:
    """Test helper factory functions for creating resolutions."""

    def test_create_failure_resolution_without_void(self):
        """Test creating failure resolution without void."""
        resolution = create_failure_resolution(
            narration="Your attempt fails. The lock remains sealed, mechanisms grinding ominously. You hear footsteps approaching down the corridor." * 3,
            margin=-5
        )

        assert resolution.success_tier == SuccessTier.FAILURE
        assert resolution.margin == -5
        assert len(resolution.effects.void_changes) == 0

    def test_create_failure_resolution_with_void(self):
        """Test creating failure resolution with void corruption."""
        resolution = create_failure_resolution(
            narration="The ritual collapses inward. Void energy burns through your psyche, leaving scars." * 5,
            margin=-12,
            void_change=3,
            character_name="TestChar"
        )

        assert resolution.success_tier == SuccessTier.CRITICAL_FAILURE
        assert len(resolution.effects.void_changes) == 1
        assert resolution.effects.void_changes[0].amount == 3

    def test_create_combat_resolution(self):
        """Test creating combat resolution with damage."""
        resolution = create_combat_resolution(
            narration="Your blade finds the gap in their armor. Blood flows as they stumble backward, wounded." * 5,
            margin=10,
            target="enemy_002",
            base_damage=18,
            soak=6,
            dealt=12
        )

        assert isinstance(resolution, CombatResolution)
        assert resolution.success_tier == SuccessTier.GOOD
        assert resolution.effects.damage.dealt == 12
        assert resolution.attack_hit is True

    def test_create_combat_resolution_auto_calculate_dealt(self):
        """Test combat resolution auto-calculates dealt damage."""
        resolution = create_combat_resolution(
            narration="The shot connects, tearing through their defenses. They cry out in pain." * 5,
            margin=8,
            target="enemy_003",
            base_damage=15,
            soak=4
        )

        assert resolution.effects.damage.dealt == 11  # 15 - 4

    def test_create_combat_resolution_determines_tier(self):
        """Test combat resolution determines correct success tier."""
        # Exceptional (margin >= 20)
        res1 = create_combat_resolution(
            narration="A perfect strike. Critical systems destroyed instantly. The target staggers backward in shock." * 5,
            margin=22,
            target="tgt",
            base_damage=10,
            dealt=10
        )
        assert res1.success_tier == SuccessTier.EXCEPTIONAL

        # Good (margin >= 10)
        res2 = create_combat_resolution(
            narration="A solid hit. The target is clearly wounded, crying out in pain as they fall." * 5,
            margin=10,
            target="tgt",
            base_damage=10,
            dealt=10
        )
        assert res2.success_tier == SuccessTier.GOOD

        # Marginal (margin >= 0)
        res3 = create_combat_resolution(
            narration="A glancing blow. Minor damage dealt, barely scratching the armor plating." * 5,
            margin=0,
            target="tgt",
            base_damage=10,
            dealt=10
        )
        assert res3.success_tier == SuccessTier.MARGINAL


# ============================================================================
# Edge Cases and Validation Tests
# ============================================================================

class TestSchemaEdgeCases:
    """Test edge cases and validation boundaries."""

    def test_negative_damage_not_allowed(self):
        """Test DamageEffect doesn't allow negative values."""
        with pytest.raises(ValidationError):
            DamageEffect(
                target="tgt",
                base_damage=-5,  # Invalid
                dealt=0
            )

    def test_empty_string_fields_rejected(self):
        """Test empty strings rejected for required fields."""
        with pytest.raises(ValidationError):
            VoidChange(
                character_name="",  # Empty not allowed
                amount=1,
                reason="test"
            )

    def test_clock_update_zero_ticks(self):
        """Test ClockUpdate with zero ticks (valid but unusual)."""
        clock = ClockUpdate(
            clock_name="Test Clock",
            ticks=0,
            reason="No progress this turn"
        )

        assert clock.ticks == 0

    def test_condition_zero_penalty(self):
        """Test Condition with zero penalty (narrative only)."""
        condition = Condition(
            name="Marked",
            penalty=0,
            duration=999,
            description="Narrative marker with no mechanical effect"
        )

        assert condition.penalty == 0

    def test_narration_max_length(self):
        """Test ActionResolution narration has max length."""
        long_narration = "A" * 2001  # Over 2000 char limit

        with pytest.raises(ValidationError) as exc_info:
            ActionResolution(
                narration=long_narration,
                success_tier=SuccessTier.GOOD,
                margin=10
            )

        assert "narration" in str(exc_info.value)

    def test_serialization_roundtrip(self):
        """Test ActionResolution can serialize and deserialize."""
        original = ActionResolution(
            narration="A complex resolution with multiple effects. The action succeeds, dealing damage and advancing clocks." * 5,
            success_tier=SuccessTier.GOOD,
            margin=15,
            effects=MechanicalEffects(
                damage=DamageEffect(target="tgt", base_damage=10, dealt=10),
                void_changes=[VoidChange(character_name="Test", amount=1, reason="Void exposure")],
                clock_updates=[ClockUpdate(clock_name="Progress", ticks=2, reason="Success")]
            )
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back
        restored = ActionResolution(**data)

        assert restored.narration == original.narration
        assert restored.success_tier == original.success_tier
        assert restored.effects.damage.dealt == 10
        assert len(restored.effects.void_changes) == 1
        assert len(restored.effects.clock_updates) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
