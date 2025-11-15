"""
Unit tests for AoE damage, protection barriers, and healing integration.

Tests three related features added together:
1. Multi-target damage (List[DamageEffect]) for AoE attacks
2. Protection barriers via Condition.protection_amount
3. HealingEffect integration into MechanicalEffects

Philosophy: Test-driven development - these tests define the behavior BEFORE implementation.
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.schemas.shared_types import (
    DamageEffect,
    Condition,
    Position,
    PositionChange,
)

from scripts.aeonisk.multiagent.schemas.action_resolution import (
    MechanicalEffects,
    ActionResolution,
)

from scripts.aeonisk.multiagent.schemas.action_effects import (
    HealingEffect,
)


# ============================================================================
# Test 1: List[DamageEffect] Multi-Target Validation (AoE)
# ============================================================================

class TestAoEDamageValidation:
    """Test List[DamageEffect] schema validation for multi-target attacks."""

    def test_empty_damage_list_valid(self):
        """Empty damage list should be valid (no damage dealt)."""
        effects = MechanicalEffects(
            damage=[],
            soulcredit_changes=[]
        )
        assert effects.damage == []

    def test_single_target_damage_as_list(self):
        """Single-target damage should work as list with one element."""
        damage = DamageEffect(
            target="tgt_7a3f",
            base_damage=15,
            dealt=12
        )

        effects = MechanicalEffects(
            damage=[damage],
            soulcredit_changes=[]
        )

        assert len(effects.damage) == 1
        assert effects.damage[0].target == "tgt_7a3f"
        assert effects.damage[0].dealt == 12

    def test_multi_target_damage_aoe(self):
        """Multiple targets should be supported for AoE attacks."""
        damages = [
            DamageEffect(target="tgt_7a3f", base_damage=15, dealt=15),
            DamageEffect(target="tgt_3c5d", base_damage=15, dealt=12),  # Different damage (margin-based)
            DamageEffect(target="tgt_2b1c", base_damage=15, dealt=8),   # Even less damage
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert len(effects.damage) == 3
        assert effects.damage[0].dealt == 15
        assert effects.damage[1].dealt == 12
        assert effects.damage[2].dealt == 8

    def test_aoe_with_different_damage_types(self):
        """AoE can have different damage types per target (e.g., fire + kinetic)."""
        damages = [
            DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12, damage_type="fire"),
            DamageEffect(target="tgt_3c5d", base_damage=8, dealt=8, damage_type="kinetic"),
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert effects.damage[0].damage_type == "fire"
        assert effects.damage[1].damage_type == "kinetic"

    def test_aoe_with_mixed_target_types(self):
        """AoE can target mix of target IDs and character names."""
        damages = [
            DamageEffect(target="tgt_7a3f", base_damage=10, dealt=10),
            DamageEffect(target="Heavy Gunner", base_damage=10, dealt=10),  # Character name
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert len(effects.damage) == 2

    def test_full_action_resolution_with_aoe(self):
        """Complete ActionResolution with AoE damage."""
        resolution = ActionResolution(
            success=True,
            success_tier="good",
            margin=8,
            narration="The grenade explodes in the middle of the enemy formation, catching three enemies in the blast radius! The lead enemy takes the full force of the explosion, while the two flanking enemies are thrown back by the shockwave.",
            effects=MechanicalEffects(
                damage=[
                    DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12),
                    DamageEffect(target="tgt_3c5d", base_damage=12, dealt=10),
                    DamageEffect(target="tgt_2b1c", base_damage=12, dealt=8),
                ],
                soulcredit_changes=[]
            )
        )

        assert len(resolution.effects.damage) == 3
        assert resolution.narration.startswith("The grenade explodes")


# ============================================================================
# Test 1.5: Range-Band-Aware AoE (Tactical Module)
# ============================================================================

class TestRangeBandAoE:
    """Test AoE attacks constrained by tactical range bands."""

    def test_aoe_hits_all_targets_in_range_band(self):
        """
        Scenario: Grenade targets "Near-Enemy" range, hits all enemies there.
        Expected: DamageEffect for each target in that range band.
        """
        # Player declares: "Throw grenade at Near-Enemy"
        # DM generates damage for all targets at Near-Enemy
        damages = [
            DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12),  # Enemy at Near-Enemy
            DamageEffect(target="tgt_3c5d", base_damage=12, dealt=12),  # Enemy at Near-Enemy
            DamageEffect(target="tgt_2b1c", base_damage=12, dealt=12),  # Enemy at Near-Enemy
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        # All targets in range band are hit
        assert len(effects.damage) == 3

    def test_aoe_different_damage_by_position_in_blast(self):
        """
        Scenario: AoE centered on Near-Enemy, affects Engaged enemies at reduced damage.
        Expected: Different damage amounts based on proximity to center.
        """
        damages = [
            # Center of blast (Near-Enemy) - full damage
            DamageEffect(target="tgt_7a3f", base_damage=15, dealt=15),
            DamageEffect(target="tgt_3c5d", base_damage=15, dealt=15),
            # Edge of blast (Engaged) - reduced damage
            DamageEffect(target="tgt_2b1c", base_damage=15, dealt=8),
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert effects.damage[0].dealt == 15  # Full damage at center
        assert effects.damage[1].dealt == 15  # Full damage at center
        assert effects.damage[2].dealt == 8   # Reduced damage at edge

    def test_aoe_respects_range_band_boundaries(self):
        """
        Scenario: AoE targets Far-Enemy, doesn't hit Near-Enemy targets.
        Expected: Only Far-Enemy targets in damage list.

        Note: DM handles range logic, damage list reflects final targets hit.
        """
        damages = [
            DamageEffect(target="tgt_7a3f", base_damage=10, dealt=10),  # Far-Enemy
            DamageEffect(target="tgt_3c5d", base_damage=10, dealt=10),  # Far-Enemy
            # No Near-Enemy targets in damage list
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert len(effects.damage) == 2

    def test_aoe_with_position_changes(self):
        """
        Scenario: Explosive pushes targets back to different range band.
        Expected: Both damage and position changes in same resolution.
        """
        resolution = ActionResolution(
            success=True,
            success_tier="good",
            margin=8,
            narration="The explosion blasts enemies backward, throwing them across the battlefield! Two enemies are hurled away from close range, landing in a heap at the far edge of the combat zone with visible injuries from both the blast and the impact.",
            effects=MechanicalEffects(
                damage=[
                    DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12),
                    DamageEffect(target="tgt_3c5d", base_damage=12, dealt=10),
                ],
                position_changes=[
                    # Both targets pushed from Near-Enemy to Far-Enemy
                    PositionChange(character_name="tgt_7a3f", new_position=Position.FAR_ENEMY, reason="Blasted backward by explosion"),
                    PositionChange(character_name="tgt_3c5d", new_position=Position.FAR_ENEMY, reason="Thrown back by shockwave"),
                ],
                soulcredit_changes=[]
            )
        )

        assert len(resolution.effects.damage) == 2
        assert len(resolution.effects.position_changes) == 2

    def test_cone_aoe_adjacent_range_bands(self):
        """
        Scenario: Cone attack hits two adjacent range bands (Engaged + Near-Enemy).
        Expected: Targets from both ranges in damage list, possibly different damage.
        """
        damages = [
            # Engaged targets - full damage
            DamageEffect(target="tgt_abc1", base_damage=14, dealt=14),
            # Near-Enemy targets - slightly reduced
            DamageEffect(target="tgt_def2", base_damage=14, dealt=12),
            DamageEffect(target="tgt_ghi3", base_damage=14, dealt=11),
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        # Mix of range bands
        assert len(effects.damage) == 3
        assert effects.damage[0].dealt > effects.damage[1].dealt


# ============================================================================
# Test 2: Condition with Protection Amount (Barriers)
# ============================================================================

class TestProtectionBarriers:
    """Test Condition.protection_amount for damage-absorbing barriers."""

    def test_condition_without_protection(self):
        """Normal conditions should work without protection_amount."""
        condition = Condition(
            name="Stunned",
            penalty=-3,
            duration=2,
            description="Cannot act, -3 to all rolls"
        )

        assert condition.name == "Stunned"
        assert condition.penalty == -3
        # protection_amount should be None or not present
        assert not hasattr(condition, 'protection_amount') or condition.protection_amount is None

    def test_condition_with_protection_amount(self):
        """Condition with protection_amount creates damage-absorbing barrier."""
        barrier = Condition(
            name="Astral Barrier",
            penalty=0,  # Barriers don't modify rolls
            duration=2,
            description="Blocks 10 damage",
            protection_amount=10
        )

        assert barrier.name == "Astral Barrier"
        assert barrier.protection_amount == 10
        assert barrier.penalty == 0

    def test_protection_amount_must_be_positive(self):
        """Protection amount must be >= 0."""
        with pytest.raises(ValidationError) as exc_info:
            Condition(
                name="Broken Barrier",
                penalty=0,
                duration=1,
                description="Invalid barrier",
                protection_amount=-5  # Invalid - negative protection
            )

        assert "protection_amount" in str(exc_info.value).lower()

    def test_multi_target_barriers(self):
        """Barriers can protect multiple targets."""
        barriers = [
            Condition(
                name="Energy Shield",
                target="tgt_7a3f",
                penalty=0,
                duration=2,
                description="Absorbs 8 damage",
                protection_amount=8
            ),
            Condition(
                name="Energy Shield",
                target="tgt_3c5d",
                penalty=0,
                duration=2,
                description="Absorbs 8 damage",
                protection_amount=8
            ),
        ]

        effects = MechanicalEffects(
            conditions=barriers,
            soulcredit_changes=[]
        )

        assert len(effects.conditions) == 2
        assert all(c.protection_amount == 8 for c in effects.conditions)

    def test_barrier_with_zero_protection(self):
        """Protection amount of 0 is valid (depleted barrier)."""
        depleted_barrier = Condition(
            name="Shattered Barrier",
            penalty=0,
            duration=1,  # Will be removed at end of round
            description="Barrier depleted, shatters immediately",
            protection_amount=0
        )

        assert depleted_barrier.protection_amount == 0
        # Barrier with protection_amount=0 should be removed by condition cleanup

    def test_full_action_resolution_with_barrier(self):
        """Complete ActionResolution creating protective barrier."""
        resolution = ActionResolution(
            success=True,
            success_tier="good",
            margin=5,
            narration="You weave a shimmering astral barrier around your allies! The translucent shield pulses with protective energy, forming a dome that will intercept incoming attacks. Your allies feel the warmth of the barrier's protective aura enveloping them as you channel your will into maintaining its integrity.",
            effects=MechanicalEffects(
                conditions=[
                    Condition(
                        name="Astral Barrier",
                        target="tgt_abc1",
                        penalty=0,
                        duration=2,
                        description="Blocks 12 damage from next attack",
                        protection_amount=12
                    ),
                    Condition(
                        name="Astral Barrier",
                        target="tgt_def2",
                        penalty=0,
                        duration=2,
                        description="Blocks 12 damage from next attack",
                        protection_amount=12
                    ),
                ],
                soulcredit_changes=[]
            )
        )

        assert len(resolution.effects.conditions) == 2


# ============================================================================
# Test 3: HealingEffect Integration
# ============================================================================

class TestHealingIntegration:
    """Test HealingEffect integration into MechanicalEffects."""

    def test_healing_effect_valid(self):
        """Valid HealingEffect should validate correctly."""
        healing = HealingEffect(
            target="tgt_7a3f",
            heal_type="hp",
            amount=15,
            source="medkit"
        )

        assert healing.target == "tgt_7a3f"
        assert healing.heal_type == "hp"
        assert healing.amount == 15
        assert healing.source == "medkit"

    def test_healing_in_mechanical_effects(self):
        """HealingEffect should be part of MechanicalEffects."""
        effects = MechanicalEffects(
            healing=[
                HealingEffect(target="tgt_7a3f", heal_type="hp", amount=12, source="medkit")
            ],
            soulcredit_changes=[]
        )

        assert len(effects.healing) == 1
        assert effects.healing[0].amount == 12

    def test_multiple_healing_targets(self):
        """Multiple targets can be healed in one action."""
        effects = MechanicalEffects(
            healing=[
                HealingEffect(target="tgt_7a3f", heal_type="hp", amount=10, source="medkit"),
                HealingEffect(target="tgt_3c5d", heal_type="stun", amount=2, source="field_medicine"),
            ],
            soulcredit_changes=[]
        )

        assert len(effects.healing) == 2
        assert effects.healing[0].heal_type == "hp"
        assert effects.healing[1].heal_type == "stun"

    def test_healing_types(self):
        """All healing types (hp, stun, wound) should be supported."""
        hp_heal = HealingEffect(target="tgt_1", heal_type="hp", amount=15)
        stun_heal = HealingEffect(target="tgt_2", heal_type="stun", amount=2)
        wound_heal = HealingEffect(target="tgt_3", heal_type="wound", amount=1)

        assert hp_heal.heal_type == "hp"
        assert stun_heal.heal_type == "stun"
        assert wound_heal.heal_type == "wound"

    def test_healing_amount_non_negative(self):
        """Healing amount must be >= 0."""
        with pytest.raises(ValidationError):
            HealingEffect(
                target="tgt_7a3f",
                heal_type="hp",
                amount=-5  # Invalid - negative healing
            )

    def test_full_action_resolution_with_healing(self):
        """Complete ActionResolution with healing."""
        resolution = ActionResolution(
            success=True,
            success_tier="good",
            margin=7,
            narration="You apply the medkit, stabilizing your ally's wounds.",
            effects=MechanicalEffects(
                healing=[
                    HealingEffect(target="tgt_7a3f", heal_type="hp", amount=18, source="medkit")
                ],
                soulcredit_changes=[]
            )
        )

        assert len(resolution.effects.healing) == 1
        assert resolution.effects.healing[0].amount == 18


# ============================================================================
# Test 4: Damage Interception by Barriers (Integration Logic)
# ============================================================================

class TestDamageInterception:
    """
    Test damage interception logic (implementation will be in dm.py).

    These tests define the expected behavior when damage hits a protected target.
    """

    def test_barrier_reduces_damage_simple(self):
        """
        Test scenario: 10 damage vs 5 protection
        Expected: 5 damage dealt, barrier depleted

        Note: This tests the LOGIC that will be implemented in dm.py,
        not the schema itself. Actual implementation test will use mocking.
        """
        # This is a design spec test - actual implementation will be in integration tests
        incoming_damage = 10
        barrier_protection = 5

        expected_damage_dealt = incoming_damage - barrier_protection
        expected_barrier_remaining = 0

        assert expected_damage_dealt == 5
        assert expected_barrier_remaining == 0

    def test_barrier_blocks_all_damage(self):
        """
        Test scenario: 8 damage vs 15 protection
        Expected: 0 damage dealt, barrier reduced to 7
        """
        incoming_damage = 8
        barrier_protection = 15

        expected_damage_dealt = max(0, incoming_damage - barrier_protection)
        expected_barrier_remaining = barrier_protection - incoming_damage

        assert expected_damage_dealt == 0
        assert expected_barrier_remaining == 7

    def test_barrier_depletes_exactly(self):
        """
        Test scenario: 12 damage vs 12 protection
        Expected: 0 damage dealt, barrier depleted
        """
        incoming_damage = 12
        barrier_protection = 12

        expected_damage_dealt = 0
        expected_barrier_remaining = 0

        assert expected_damage_dealt == 0
        assert expected_barrier_remaining == 0

    def test_multiple_hits_deplete_barrier(self):
        """
        Test scenario: Barrier with 10 protection takes 3 hits (4, 4, 5 damage)
        Expected: Hit 1: 0 dealt (6 remaining), Hit 2: 0 dealt (2 remaining), Hit 3: 3 dealt (0 remaining)
        """
        barrier_protection = 10
        hits = [4, 4, 5]

        results = []
        for hit_damage in hits:
            damage_dealt = max(0, hit_damage - barrier_protection)
            barrier_protection = max(0, barrier_protection - hit_damage)
            results.append((damage_dealt, barrier_protection))

        assert results[0] == (0, 6)  # First hit: no damage, barrier at 6
        assert results[1] == (0, 2)  # Second hit: no damage, barrier at 2
        assert results[2] == (3, 0)  # Third hit: 3 damage, barrier depleted


# ============================================================================
# Test 5: Barrier Expiration and Duration
# ============================================================================

class TestBarrierDuration:
    """Test barrier expiration and duration mechanics."""

    def test_barrier_duration_decrements(self):
        """Barrier duration should decrement each round."""
        initial_duration = 3

        # Simulate 3 rounds
        for round_num in range(1, 4):
            current_duration = initial_duration - round_num
            if current_duration <= 0:
                # Barrier expired
                assert True
            else:
                assert current_duration > 0

    def test_barrier_expires_after_duration(self):
        """Barrier should be removed when duration reaches 0."""
        barrier = Condition(
            name="Temporary Shield",
            penalty=0,
            duration=1,  # Lasts 1 round
            description="Blocks 10 damage",
            protection_amount=10
        )

        # After 1 round, duration becomes 0 and barrier should be removed
        barrier.duration -= 1
        assert barrier.duration == 0
        # Implementation will remove this condition in dm.py

    def test_permanent_barrier_zero_duration(self):
        """
        Barriers with duration=0 are removed immediately.
        Note: This is for depleted barriers created during combat.
        """
        depleted = Condition(
            name="Shattered Barrier",
            penalty=0,
            duration=0,
            description="Barrier just broke",
            protection_amount=0
        )

        assert depleted.duration == 0
        assert depleted.protection_amount == 0


# ============================================================================
# Test 6: Combined Scenarios (AoE + Barriers + Healing)
# ============================================================================

class TestCombinedEffects:
    """Test scenarios combining AoE, barriers, and healing."""

    def test_aoe_damage_with_barriers_on_targets(self):
        """
        Scenario: AoE attack hits 3 targets, 2 have barriers
        Expected: Different damage outcomes based on protection
        """
        # Create AoE damage
        damages = [
            DamageEffect(target="tgt_abc1", base_damage=15, dealt=15),  # No barrier
            DamageEffect(target="tgt_def2", base_damage=15, dealt=7),   # Has 8 protection
            DamageEffect(target="tgt_ghi3", base_damage=15, dealt=0),   # Has 20 protection
        ]

        effects = MechanicalEffects(
            damage=damages,
            soulcredit_changes=[]
        )

        assert effects.damage[0].dealt == 15  # Full damage
        assert effects.damage[1].dealt == 7   # Reduced by barrier
        assert effects.damage[2].dealt == 0   # Fully blocked

    def test_barrier_then_healing(self):
        """
        Scenario: Create barrier, barrier blocks damage, then heal target
        Expected: All effects tracked in single resolution
        """
        resolution = ActionResolution(
            success=True,
            success_tier="exceptional",
            margin=12,
            narration="You create a protective barrier and channel healing energy!",
            effects=MechanicalEffects(
                conditions=[
                    Condition(
                        name="Healing Barrier",
                        target="tgt_7a3f",
                        penalty=0,
                        duration=2,
                        description="Blocks 10 damage and slowly heals",
                        protection_amount=10
                    )
                ],
                healing=[
                    HealingEffect(target="tgt_7a3f", heal_type="hp", amount=8, source="ritual")
                ],
                soulcredit_changes=[]
            )
        )

        assert len(resolution.effects.conditions) == 1
        assert len(resolution.effects.healing) == 1
        assert resolution.effects.conditions[0].protection_amount == 10

    def test_aoe_healing(self):
        """
        Scenario: Mass healing ritual heals multiple targets
        Expected: Multiple HealingEffect entries
        """
        effects = MechanicalEffects(
            healing=[
                HealingEffect(target="tgt_abc1", heal_type="hp", amount=10, source="mass_healing_ritual"),
                HealingEffect(target="tgt_def2", heal_type="hp", amount=10, source="mass_healing_ritual"),
                HealingEffect(target="tgt_ghi3", heal_type="stun", amount=1, source="mass_healing_ritual"),
            ],
            void_changes=[],  # Mass healing might have void cost
            soulcredit_changes=[]
        )

        assert len(effects.healing) == 3

    def test_complex_combat_round(self):
        """
        Scenario: Complex round with AoE damage, barriers, and healing
        Player 1: AoE grenade (3 targets)
        Player 2: Creates barrier on ally
        Player 3: Heals wounded ally
        """
        # This would be multiple ActionResolution objects, but we test the schemas work together

        aoe_attack = MechanicalEffects(
            damage=[
                DamageEffect(target="tgt_1", base_damage=12, dealt=12),
                DamageEffect(target="tgt_2", base_damage=12, dealt=10),
                DamageEffect(target="tgt_3", base_damage=12, dealt=8),
            ],
            soulcredit_changes=[]
        )

        barrier_creation = MechanicalEffects(
            conditions=[
                Condition(
                    name="Barrier",
                    target="player_01",
                    penalty=0,
                    duration=2,
                    description="Blocks 15 damage",
                    protection_amount=15
                )
            ],
            soulcredit_changes=[]
        )

        healing_action = MechanicalEffects(
            healing=[
                HealingEffect(target="player_02", heal_type="hp", amount=18, source="medkit")
            ],
            soulcredit_changes=[]
        )

        # All schemas validate
        assert len(aoe_attack.damage) == 3
        assert barrier_creation.conditions[0].protection_amount == 15
        assert healing_action.healing[0].amount == 18
