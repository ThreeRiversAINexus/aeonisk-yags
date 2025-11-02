"""
Unit tests for structured enemy spawning.

Tests verify that the EnemyCombatManager.spawn_from_structured() method
correctly processes EnemySpawn objects from DM's RoundSynthesis.

This test file documents and fixes the spawn_enemy_from_template import error
that was blocking enemy spawning in production sessions.

Author: Three Rivers AI Nexus
Date: 2025-11-02
"""

import pytest
from aeonisk.multiagent.enemy_combat import EnemyCombatManager
from aeonisk.multiagent.schemas.story_events import EnemySpawn
from aeonisk.multiagent.schemas.shared_types import Position


class TestEnemySpawnStructured:
    """Test structured enemy spawning from RoundSynthesis."""

    def test_spawn_from_structured_single_enemy(self):
        """
        Test spawning a single enemy from EnemySpawn object.

        This test documents the import error that blocked enemy spawning:
        - Line 273 of enemy_combat.py imports non-existent spawn_enemy_from_template
        - Correct function is spawn_enemy from enemy_spawner module

        Expected behavior:
        - DM generates RoundSynthesis with enemy_spawns field
        - EnemyCombatManager.spawn_from_structured() processes spawns
        - Each EnemySpawn creates count enemies using spawn_enemy()
        """
        # Setup: Create EnemyCombatManager
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = True
        enemy_combat.current_round = 1

        # Create EnemySpawn object (from DM's RoundSynthesis)
        spawn = EnemySpawn(
            template="Grunt",
            faction="ACG Security",
            archetype="Enforcer",
            count=1,
            spawn_reason="Alarm triggered, reinforcements arrive",
            initial_position=Position.FAR_ENEMY,
            custom_traits="aggressive"
        )

        # Execute: Spawn enemies from structured output
        # This will FAIL with ImportError until we fix enemy_combat.py:273
        notifications = enemy_combat.spawn_from_structured([spawn])

        # Verify: Enemy spawned successfully
        assert len(notifications) == 1, "Should spawn 1 enemy"
        assert len(enemy_combat.enemy_agents) == 1, "Should have 1 enemy agent"

        enemy = enemy_combat.enemy_agents[0]
        assert enemy.name == "ACG Security Enforcer"
        # Position is stored as object with ring and side attributes
        assert enemy.position.ring == "Far"
        assert enemy.position.side == "Enemy"
        assert enemy.is_active is True

    def test_spawn_from_structured_multiple_count(self):
        """
        Test spawning multiple enemies from single EnemySpawn with count > 1.

        When count=3, should spawn 3 individual enemies with #1, #2, #3 suffixes.
        """
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = True
        enemy_combat.current_round = 1

        spawn = EnemySpawn(
            template="Grunt",
            faction="Void Cultist",
            archetype="Ritualist",
            count=3,
            spawn_reason="Ritual circle activates, cultists emerge",
            initial_position=Position.NEAR_ENEMY,
            custom_traits=None  # Uses default "adaptive"
        )

        notifications = enemy_combat.spawn_from_structured([spawn])

        assert len(notifications) == 3, "Should spawn 3 enemies"
        assert len(enemy_combat.enemy_agents) == 3, "Should have 3 enemy agents"

        # Verify names have #1, #2, #3 suffixes
        assert enemy_combat.enemy_agents[0].name == "Void Cultist Ritualist #1"
        assert enemy_combat.enemy_agents[1].name == "Void Cultist Ritualist #2"
        assert enemy_combat.enemy_agents[2].name == "Void Cultist Ritualist #3"

    def test_spawn_from_structured_multiple_spawn_objects(self):
        """
        Test spawning from multiple EnemySpawn objects in one call.

        DM can spawn different enemy types simultaneously (e.g., 2 grunts + 1 elite).
        """
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = True
        enemy_combat.current_round = 2

        spawns = [
            EnemySpawn(
                template="Grunt",
                faction="Gang",
                archetype="Enforcer",
                count=2,
                spawn_reason="Street gang backup arrives",
                initial_position=Position.NEAR_ENEMY
            ),
            EnemySpawn(
                template="Elite",
                faction="Gang",
                archetype="Leader",
                count=1,
                spawn_reason="Gang leader joins the fight",
                initial_position=Position.FAR_ENEMY
            )
        ]

        notifications = enemy_combat.spawn_from_structured(spawns)

        assert len(notifications) == 3, "Should spawn 3 total enemies (2 + 1)"
        assert len(enemy_combat.enemy_agents) == 3

        # Verify mix of templates
        assert enemy_combat.enemy_agents[0].name == "Gang Enforcer #1"
        assert enemy_combat.enemy_agents[1].name == "Gang Enforcer #2"
        assert enemy_combat.enemy_agents[2].name == "Gang Leader"

    def test_spawn_from_structured_disabled(self):
        """
        Test that spawning is skipped when enemy_agents_enabled=False.

        Returns empty list without errors.
        """
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = False  # Disabled
        enemy_combat.current_round = 1

        spawn = EnemySpawn(
            template="Grunt",
            faction="Test",
            archetype="Test",
            count=1,
            spawn_reason="Test spawn reason (disabled)",
            initial_position=Position.NEAR_ENEMY
        )

        notifications = enemy_combat.spawn_from_structured([spawn])

        assert len(notifications) == 0, "Should not spawn when disabled"
        assert len(enemy_combat.enemy_agents) == 0

    def test_spawn_from_structured_empty_list(self):
        """
        Test that empty spawn list is handled gracefully.

        DM's RoundSynthesis.enemy_spawns defaults to empty list if no spawns.
        """
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = True
        enemy_combat.current_round = 1

        notifications = enemy_combat.spawn_from_structured([])

        assert len(notifications) == 0
        assert len(enemy_combat.enemy_agents) == 0


class TestEnemySpawnParameterMapping:
    """
    Test that EnemySpawn fields correctly map to spawn_enemy() parameters.

    Documents the parameter mismatch that caused the import error:
    - spawn_enemy_from_template() doesn't exist
    - Actual function is spawn_enemy(name, template_key, position_str, ...)
    - Must convert Position enum to string
    - Must use correct parameter names
    """

    def test_spawn_parameters_correct_order(self):
        """
        Verify spawn_enemy() called with correct parameter order.

        spawn_enemy signature:
        - name (str)
        - template_key (str)  # NOT "template"
        - position_str (str)  # NOT Position enum
        - tactics_override (Optional[str])
        - personality_override (Optional[str])
        - current_round (int)  # NOT "spawned_round"
        """
        enemy_combat = EnemyCombatManager(shared_state=None)
        enemy_combat.enabled = True
        enemy_combat.current_round = 5

        spawn = EnemySpawn(
            template="Elite",  # Must be lowercased for template_key
            faction="Corp",
            archetype="Security",
            count=1,
            spawn_reason="Test spawn for parameter verification",
            initial_position=Position.NEAR_PC,  # Must convert to "Near-PC"
            custom_traits="defensive"
        )

        notifications = enemy_combat.spawn_from_structured([spawn])

        assert len(enemy_combat.enemy_agents) == 1
        enemy = enemy_combat.enemy_agents[0]

        # Verify Position enum was converted to string
        assert enemy.position.ring == "Near"
        assert enemy.position.side == "PC"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
