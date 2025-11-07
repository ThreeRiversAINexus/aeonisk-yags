"""
Unit tests for NPC tracking in target_ids.py.

Tests verify that TargetIDMapper correctly:
- Recognizes npc_ prefix for fresh NPCs
- Recognizes enemy_ prefix for converted NPCs (stable IDs)
- Registers NPCs for tracking
- Differentiates between NPCs, enemies, and players
- Handles NPC targeting rules
"""

import pytest
from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
from scripts.aeonisk.multiagent.npc_agent import NPCAgent


def create_test_npc(
    agent_id="npc_test_1",
    name="Test NPC",
    entity_type="neutral",
    threat_level="non_combatant"
):
    """Create test NPC for target ID testing."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="Test Faction",
        entity_type=entity_type,
        disposition="neutral",
        threat_level=threat_level,
        description="Test NPC",
        health=20,
        max_health=20,
        soak=0,
        void_score=0,
        skills={}
    )


class TestTargetIDMapperNPC:
    """Tests for NPC functionality in TargetIDMapper."""

    def test_get_agent_type_recognizes_npc_prefix(self):
        """get_agent_type recognizes npc_ prefix."""
        mapper = TargetIDMapper()

        # Fresh NPCs use npc_ prefix
        assert mapper.get_agent_type("npc_dock_worker_1234") == "npc"
        assert mapper.get_agent_type("npc_civilian_5678") == "npc"
        assert mapper.get_agent_type("npc_informant_9999") == "npc"

    def test_get_agent_type_recognizes_converted_npc(self):
        """get_agent_type recognizes enemy_ prefix for converted NPCs."""
        mapper = TargetIDMapper()

        # Register converted NPC (has enemy_ ID but is in NPC registry)
        npc = create_test_npc(agent_id="enemy_raider_1", name="Converted Raider")
        mapper.register_npc(npc)

        # Should return "npc" even though ID starts with enemy_
        assert mapper.get_agent_type("enemy_raider_1") == "npc"

    def test_get_agent_type_differentiates_enemy_and_npc(self):
        """get_agent_type differentiates between enemy and converted NPC."""
        mapper = TargetIDMapper()

        # Register NPC with enemy_ prefix
        npc = create_test_npc(agent_id="enemy_prisoner_1", name="Prisoner")
        mapper.register_npc(npc)

        # This enemy_ ID is NPC (in registry)
        assert mapper.get_agent_type("enemy_prisoner_1") == "npc"

        # This enemy_ ID is not in registry, so it's an enemy
        assert mapper.get_agent_type("enemy_grunt_1") == "enemy"

    def test_register_npc(self):
        """NPCs can be registered for tracking."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="npc_guide_1", name="Guide")

        # Register NPC
        mapper.register_npc(npc)

        # Should be in registry
        assert mapper.is_npc("npc_guide_1") == True
        assert mapper.get_agent_type("npc_guide_1") == "npc"

    def test_register_npc_with_enemy_prefix(self):
        """Converted NPCs (enemy_ prefix) can be registered."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="enemy_raider_1", name="Surrendered Raider")

        mapper.register_npc(npc)

        # Should be recognized as NPC
        assert mapper.is_npc("enemy_raider_1") == True
        assert mapper.get_agent_type("enemy_raider_1") == "npc"

    def test_unregister_npc(self):
        """NPCs can be unregistered (e.g., when they flee)."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="npc_civilian_1", name="Civilian")

        mapper.register_npc(npc)
        assert mapper.is_npc("npc_civilian_1") == True

        # Unregister
        result = mapper.unregister_npc("npc_civilian_1")
        assert result == True
        assert mapper.is_npc("npc_civilian_1") == False

    def test_unregister_npc_not_found(self):
        """Unregistering non-existent NPC returns False."""
        mapper = TargetIDMapper()

        result = mapper.unregister_npc("npc_nonexistent_1")
        assert result == False

    def test_is_npc(self):
        """is_npc checks NPC registry."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="npc_informant_1", name="Informant")

        # Not registered yet
        assert mapper.is_npc("npc_informant_1") == False

        # Register
        mapper.register_npc(npc)
        assert mapper.is_npc("npc_informant_1") == True

    def test_get_all_npc_ids(self):
        """get_all_npc_ids returns all registered NPCs."""
        mapper = TargetIDMapper()

        npc1 = create_test_npc(agent_id="npc_guide_1", name="Guide")
        npc2 = create_test_npc(agent_id="enemy_prisoner_1", name="Prisoner")
        npc3 = create_test_npc(agent_id="npc_civilian_1", name="Civilian")

        mapper.register_npc(npc1)
        mapper.register_npc(npc2)
        mapper.register_npc(npc3)

        npc_ids = mapper.get_all_npc_ids()
        assert len(npc_ids) == 3
        assert "npc_guide_1" in npc_ids
        assert "enemy_prisoner_1" in npc_ids
        assert "npc_civilian_1" in npc_ids

    def test_can_target_npc_rules(self):
        """can_target enforces NPC targeting rules."""
        mapper = TargetIDMapper()

        # NPCs cannot target (non-combatants)
        assert mapper.can_target(
            source_id="npc_civilian_1",
            target_id="player_01",
            source_type="npc"
        ) == False

        # Players can target NPCs
        assert mapper.can_target(
            source_id="player_01",
            target_id="npc_civilian_1",
            source_type="player"
        ) == True

        # Enemies can target NPCs (checked with personality elsewhere)
        assert mapper.can_target(
            source_id="enemy_grunt_1",
            target_id="npc_civilian_1",
            source_type="enemy"
        ) == True

    def test_can_target_with_personality_ruthless(self):
        """Ruthless enemies can target all NPCs."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="npc_civilian_1", threat_level="non_combatant")
        mapper.register_npc(npc)

        # Ruthless enemies target anyone
        assert mapper.can_target_with_personality(
            source_id="enemy_grunt_1",
            target_id="npc_civilian_1",
            personality="ruthless",
            target_threat_level="non_combatant"
        ) == True

    def test_can_target_with_personality_professional(self):
        """Professional enemies only target threats."""
        mapper = TargetIDMapper()

        # Non-combatant NPC - professional won't target
        assert mapper.can_target_with_personality(
            source_id="enemy_soldier_1",
            target_id="npc_civilian_1",
            personality="professional",
            target_threat_level="non_combatant"
        ) == False

        # Armed neutral - professional will target
        assert mapper.can_target_with_personality(
            source_id="enemy_soldier_1",
            target_id="npc_guard_1",
            personality="professional",
            target_threat_level="armed_neutral"
        ) == True

        # Potential threat - professional will target
        assert mapper.can_target_with_personality(
            source_id="enemy_soldier_1",
            target_id="npc_informant_1",
            personality="professional",
            target_threat_level="potential_threat"
        ) == True

    def test_can_target_with_personality_defensive(self):
        """Defensive enemies ignore all NPCs."""
        mapper = TargetIDMapper()

        # Defensive enemies don't target any NPCs
        assert mapper.can_target_with_personality(
            source_id="enemy_grunt_1",
            target_id="npc_civilian_1",
            personality="defensive",
            target_threat_level="non_combatant"
        ) == False

        assert mapper.can_target_with_personality(
            source_id="enemy_grunt_1",
            target_id="npc_guard_1",
            personality="defensive",
            target_threat_level="armed_neutral"
        ) == False

    def test_can_target_with_personality_always_targets_players(self):
        """All personalities can target players."""
        mapper = TargetIDMapper()

        # All personalities target players
        for personality in ["ruthless", "professional", "defensive"]:
            assert mapper.can_target_with_personality(
                source_id="enemy_grunt_1",
                target_id="player_01",
                personality=personality,
                target_threat_level="armed_neutral"
            ) == True

    def test_npc_prefix_priority_in_get_agent_type(self):
        """npc_ prefix is checked before enemy_ prefix."""
        mapper = TargetIDMapper()

        # Fresh NPC with npc_ prefix
        assert mapper.get_agent_type("npc_civilian_1") == "npc"

        # Converted NPC with enemy_ prefix (not in registry yet)
        assert mapper.get_agent_type("enemy_raider_1") == "enemy"

        # Register converted NPC
        npc = create_test_npc(agent_id="enemy_raider_1")
        mapper.register_npc(npc)

        # Now recognized as NPC
        assert mapper.get_agent_type("enemy_raider_1") == "npc"

    def test_player_prefix_recognized(self):
        """player_ prefix recognized correctly."""
        mapper = TargetIDMapper()

        assert mapper.get_agent_type("player_01") == "player"
        assert mapper.get_agent_type("player_02") == "player"

    def test_unknown_prefix_returns_none(self):
        """Unknown prefixes return None."""
        mapper = TargetIDMapper()

        assert mapper.get_agent_type("unknown_agent_1") == None
        assert mapper.get_agent_type("invalid_id") == None

    def test_multiple_npcs_registration(self):
        """Multiple NPCs can be registered and tracked."""
        mapper = TargetIDMapper()

        npcs = [
            create_test_npc(agent_id="npc_civilian_1", name="Civilian 1"),
            create_test_npc(agent_id="npc_civilian_2", name="Civilian 2"),
            create_test_npc(agent_id="enemy_prisoner_1", name="Prisoner 1"),
            create_test_npc(agent_id="enemy_prisoner_2", name="Prisoner 2"),
        ]

        for npc in npcs:
            mapper.register_npc(npc)

        # All should be in registry
        npc_ids = mapper.get_all_npc_ids()
        assert len(npc_ids) == 4

        for npc in npcs:
            assert mapper.is_npc(npc.agent_id) == True
            assert mapper.get_agent_type(npc.agent_id) == "npc"

    def test_npc_registry_independent_of_free_targeting(self):
        """NPC registry works whether free targeting is enabled or not."""
        mapper = TargetIDMapper()
        npc = create_test_npc(agent_id="npc_guide_1", name="Guide")

        # Register NPC (free targeting disabled)
        mapper.register_npc(npc)
        assert mapper.is_npc("npc_guide_1") == True

        # Enable free targeting
        mapper.enable()
        assert mapper.enabled == True

        # NPC registry still works
        assert mapper.is_npc("npc_guide_1") == True

        # Disable free targeting
        mapper.disable()

        # NPC registry still intact
        assert mapper.is_npc("npc_guide_1") == True

    def test_repr_shows_npc_count(self):
        """__repr__ shows NPC count."""
        mapper = TargetIDMapper()

        npc1 = create_test_npc(agent_id="npc_civilian_1")
        npc2 = create_test_npc(agent_id="npc_civilian_2")

        mapper.register_npc(npc1)
        mapper.register_npc(npc2)

        repr_str = repr(mapper)
        assert "2 NPCs" in repr_str

    def test_npc_agent_id_format_validation(self):
        """Test various agent_id formats are recognized correctly."""
        mapper = TargetIDMapper()

        test_cases = [
            # (agent_id, expected_type_when_not_registered)
            ("npc_simple", "npc"),
            ("npc_with_underscores_1234", "npc"),
            ("npc_multiple_parts_here_5678", "npc"),
            ("enemy_simple", "enemy"),
            ("enemy_grunt_1234", "enemy"),
            ("player_01", "player"),
            ("player_simple", "player"),
        ]

        for agent_id, expected_type in test_cases:
            result = mapper.get_agent_type(agent_id)
            assert result == expected_type, \
                f"Expected {expected_type} for {agent_id}, got {result}"
