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
            faction="ACG",
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
        assert enemy.name == "ACG Enforcer"
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
            faction="Void",
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
        assert enemy_combat.enemy_agents[0].name == "Void Ritualist #1"
        assert enemy_combat.enemy_agents[1].name == "Void Ritualist #2"
        assert enemy_combat.enemy_agents[2].name == "Void Ritualist #3"

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
                faction="Independent",
                archetype="Enforcer",
                count=2,
                spawn_reason="Street gang backup arrives",
                initial_position=Position.NEAR_ENEMY
            ),
            EnemySpawn(
                template="Elite",
                faction="Independent",
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
        assert enemy_combat.enemy_agents[0].name == "Independent Enforcer #1"
        assert enemy_combat.enemy_agents[1].name == "Independent Enforcer #2"
        assert enemy_combat.enemy_agents[2].name == "Independent Leader"

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
            faction="Independent",
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
            faction="ACG",
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


class TestFactionValidation:
    """Test that EnemySpawn and NPCSpawn enforce canonical faction names."""

    def test_enemy_spawn_rejects_non_canonical_faction(self):
        """Non-canonical faction strings must be rejected by Pydantic validation."""
        from pydantic import ValidationError

        bad_factions = [
            "Pantheon Crew",
            "ACG Security",
            "Tempest Corp Security",
            "Red Coil Syndicate",
            "Void Cultists",
            "Local Criminal Syndicate",
            "Gang",
            "Corp",
        ]
        for bad_faction in bad_factions:
            with pytest.raises(ValidationError):
                EnemySpawn(
                    template="grunt",
                    faction=bad_faction,
                    archetype="Enforcer",
                    count=1,
                    spawn_reason="Test spawn with non-canonical faction",
                )

    def test_enemy_spawn_accepts_all_canonical_factions(self):
        """All 10 canonical faction values must be accepted."""
        canonical = [
            "Sovereign Nexus", "Pantheon Security", "ACG", "ArcGen",
            "House of Vox", "Tempest Industries", "Freeborn",
            "Void", "Independent", "Unknown",
        ]
        for faction in canonical:
            spawn = EnemySpawn(
                template="grunt",
                faction=faction,
                archetype="Enforcer",
                count=1,
                spawn_reason="Test spawn with canonical faction value",
            )
            assert spawn.faction == faction

    def test_npc_spawn_rejects_non_canonical_faction(self):
        """NPCSpawn must also reject non-canonical faction strings."""
        from pydantic import ValidationError
        from aeonisk.multiagent.schemas.story_events import NPCSpawn

        bad_factions = [
            "Pantheon Crew",
            "Station Security",
            "Independent Civilian",
            "Freeborn Medical Corps",
        ]
        for bad_faction in bad_factions:
            with pytest.raises(ValidationError):
                NPCSpawn(
                    name="Test NPC",
                    faction=bad_faction,
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="neutral",
                    description="Test NPC for faction validation check",
                    health=20,
                    soak=0,
                )

    def test_npc_spawn_accepts_all_canonical_factions(self):
        """NPCSpawn must accept all 10 canonical faction values."""
        from aeonisk.multiagent.schemas.story_events import NPCSpawn

        canonical = [
            "Sovereign Nexus", "Pantheon Security", "ACG", "ArcGen",
            "House of Vox", "Tempest Industries", "Freeborn",
            "Void", "Independent", "Unknown",
        ]
        for faction in canonical:
            npc = NPCSpawn(
                name="Test NPC",
                faction=faction,
                entity_type="neutral",
                threat_level="non_combatant",
                disposition="neutral",
                description="Test NPC for faction validation check",
                health=20,
                soak=0,
            )
            assert npc.faction == faction


class TestFactionUtilsVoid:
    """Test Void faction handling in faction_utils."""

    def test_void_hostile_to_all_non_void(self):
        """Void faction should be hostile to every non-Void faction."""
        from aeonisk.multiagent.faction_utils import are_factions_allied

        non_void = [
            "Sovereign Nexus", "Pantheon Security", "ACG", "ArcGen",
            "House of Vox", "Tempest Industries", "Freeborn",
            "Independent", "Unknown", "Nexus", "Pantheon",
        ]
        for faction in non_void:
            assert are_factions_allied("Void", faction) is False, \
                f"Void should be hostile to {faction}"
            assert are_factions_allied(faction, "Void") is False, \
                f"{faction} should be hostile to Void"

    def test_void_allied_with_void(self):
        """Void should be allied with other Void entities."""
        from aeonisk.multiagent.faction_utils import are_factions_allied
        assert are_factions_allied("Void", "Void") is True

    def test_void_faction_stance(self):
        """get_faction_stance should return 'Void' for Void faction."""
        from aeonisk.multiagent.faction_utils import get_faction_stance
        assert get_faction_stance("Void") == "Void"

    def test_extract_faction_void(self):
        """extract_faction should match 'Void' in enemy names."""
        from aeonisk.multiagent.faction_utils import extract_faction
        assert extract_faction("Void Creature") == "Void"
        assert extract_faction("Corrupted Void Entity") == "Void"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
