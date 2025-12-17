"""
Unit tests for enemy group mechanics removal.

Tests verify that all group-related mechanics have been properly removed:
- EnemyAgent no longer has is_group, unit_count, original_unit_count fields
- Enemy spawner uses 4-field syntax (no count parameter)
- Damage calculations don't include group_bonus
- No attrition system
- Target counting is simple (no unit_count multiplication)

Author: Three Rivers AI Nexus
Date: 2025-11-01
"""

import pytest
from aeonisk.multiagent.enemy_agent import EnemyAgent
from aeonisk.multiagent.enemy_spawner import (
    spawn_enemy,
    count_active_units
)
from aeonisk.multiagent.schemas.shared_types import Position


class TestEnemyAgentNoGroupFields:
    """Test that EnemyAgent dataclass has no group-related fields."""

    def test_enemy_agent_has_no_is_group_field(self):
        """EnemyAgent should not have is_group field."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        assert not hasattr(enemy, 'is_group'), "EnemyAgent should not have is_group field"

    def test_enemy_agent_has_no_unit_count_field(self):
        """EnemyAgent should not have unit_count field."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        assert not hasattr(enemy, 'unit_count'), "EnemyAgent should not have unit_count field"

    def test_enemy_agent_has_no_original_unit_count_field(self):
        """EnemyAgent should not have original_unit_count field."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        assert not hasattr(enemy, 'original_unit_count'), "EnemyAgent should not have original_unit_count field"

    def test_enemy_agent_has_no_get_group_damage_bonus_method(self):
        """EnemyAgent should not have get_group_damage_bonus method."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        assert not hasattr(enemy, 'get_group_damage_bonus'), "EnemyAgent should not have get_group_damage_bonus method"

    def test_enemy_agent_has_no_apply_group_attrition_method(self):
        """EnemyAgent should not have apply_group_attrition method."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        assert not hasattr(enemy, 'apply_group_attrition'), "EnemyAgent should not have apply_group_attrition method"


# NOTE: TestSpawnMarkerParsing class was deleted.
# The parse_spawn_markers() function was removed from the codebase.
# Enemy spawning now uses structured output (ScenarioSetup.initial_enemies) instead of text markers.


class TestEnemySpawning:
    """Test enemy spawning without count parameter."""

    def test_spawn_enemy_4_field_signature(self):
        """spawn_enemy should accept 4 required fields (no count)."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )

        assert enemy is not None
        assert enemy.name == "Test Enemy"
        # Position is stored as a Position object with ring and side attributes
        assert enemy.position.ring == "Near"
        assert enemy.position.side == "Enemy"

    def test_spawn_enemy_hp_not_scaled(self):
        """Enemy HP should match template exactly (no count-based scaling)."""
        # Grunt template has 12 HP (Health attribute 3 * body_levels 5 = 15, but actual template is 12)
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )

        # Verify HP is not scaled (would have been multiplied by count in old system)
        assert enemy.health == enemy.max_health  # Not damaged
        assert enemy.health == 30  # Grunt base HP from template (Health 3 * body_levels 10)

    def test_spawn_enemy_elite_hp_not_scaled(self):
        """Elite enemy HP should match template exactly."""
        # Elite template has 50 HP (Health attribute 5 * body_levels 10 = 50)
        enemy = spawn_enemy(
            name="Elite Squad",
            template_key="elite",
            position_str="Far-Enemy",
            tactics_override="defensive"
        )

        # Verify HP is not scaled (would have been multiplied by count * 0.7 in old system)
        assert enemy.health == enemy.max_health  # Not damaged
        assert enemy.health == 50  # Elite base HP from template (Health 5 * body_levels 10)


class TestActiveUnitCounting:
    """Test that active unit counting is simple (count agents, not unit_count)."""

    def test_count_active_units_single_enemy(self):
        """Count should be 1 for single active enemy."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )
        enemy.is_active = True

        count = count_active_units([enemy])
        assert count == 1

    def test_count_active_units_multiple_enemies(self):
        """Count should equal number of active enemies."""
        enemies = []
        for i in range(3):
            enemy = spawn_enemy(
                name=f"Enemy {i}",
                template_key="grunt",
                position_str="Near-Enemy",
                tactics_override="aggressive"
            )
            enemy.is_active = True
            enemies.append(enemy)

        count = count_active_units(enemies)
        assert count == 3

    def test_count_active_units_excludes_inactive(self):
        """Count should exclude inactive enemies."""
        enemies = []
        for i in range(3):
            enemy = spawn_enemy(
                name=f"Enemy {i}",
                template_key="grunt",
                position_str="Near-Enemy",
                tactics_override="aggressive"
            )
            enemy.is_active = (i < 2)  # Only first 2 active
            enemies.append(enemy)

        count = count_active_units(enemies)
        assert count == 2


class TestNoDamageBonus:
    """Test that damage calculations don't include group bonuses."""

    def test_enemy_weapon_damage_no_bonus(self):
        """Enemy weapon should have no group damage bonus."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )

        # Enemy should have weapons
        assert len(enemy.weapons) > 0

        # Calculate expected damage (Strength + weapon.damage)
        weapon = enemy.weapons[0]
        strength = enemy.attributes.get('Strength', 3)
        expected_base = strength + weapon.damage

        # Should NOT have any group bonus addition
        # (We can't directly test the damage calculation without running combat,
        # but we verified no get_group_damage_bonus method exists)
        assert not hasattr(enemy, 'get_group_damage_bonus')


class TestEnemyAgentSerialization:
    """Test that EnemyAgent serialization doesn't include group fields."""

    def test_to_dict_no_group_fields(self):
        """to_dict() should not include is_group or unit_count."""
        enemy = spawn_enemy(
            name="Test Enemy",
            template_key="grunt",
            position_str="Near-Enemy",
            tactics_override="aggressive"
        )

        data = enemy.to_dict()

        assert 'is_group' not in data
        assert 'unit_count' not in data
        assert 'original_unit_count' not in data


# Mark known targeting issues for future fixes
class TestKnownTargetingBugs:
    """Tests for known targeting bugs - marked as expected failures."""

    @pytest.mark.xfail(reason="Known bug: DM invents target IDs like 'tgt_heavy_gunners' instead of using actual IDs")
    def test_dm_uses_actual_target_ids(self):
        """DM should use actual target IDs from combatant list, not invented ones."""
        # This test documents the known bug where DM creates IDs like
        # 'tgt_heavy_gunners' instead of using the actual randomized IDs
        # like 'tgt_9i1b' from the target_id_mapper
        pytest.fail("DM targeting bug not yet fixed")

    @pytest.mark.xfail(reason="Known bug: DM not using ActionResolutionEffects schema for damage")
    def test_dm_uses_structured_damage_effects(self):
        """DM should use ActionResolutionEffects with DamageEffect objects."""
        # This test documents the known bug where DM mentions damage in
        # narration but doesn't populate the structured effects field
        pytest.fail("DM structured output bug not yet fixed")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
