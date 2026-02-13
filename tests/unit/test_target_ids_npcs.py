"""
Unit tests for NPC support in TargetIDMapper.

Tests personality-based targeting and stable agent_id support.
"""

import pytest
from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
from scripts.aeonisk.multiagent.npc_agent import NPCAgent


def create_test_npc(agent_id="enemy_guide_1", name="Guide", threat_level="non_combatant"):
    """Create minimal test NPC."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level=threat_level,
        description="Test NPC",
        health=20,
        max_health=20,
        soak=0,
        void_score=2,
        skills={}
    )


def test_target_id_mapper_recognizes_npc():
    """TargetIDMapper can identify NPC agents."""
    mapper = TargetIDMapper()
    npc = create_test_npc(agent_id="enemy_guide_1", name="Guide")

    # Register NPC
    mapper.register_npc(npc)

    # Should recognize as NPC
    assert mapper.is_npc("enemy_guide_1") == True


def test_target_id_mapper_stable_ids():
    """TargetIDMapper handles stable IDs (NPCs with enemy_xxx IDs)."""
    mapper = TargetIDMapper()

    # NPC with enemy_xxx ID (from conversion)
    npc = create_test_npc(agent_id="enemy_pirate_1", name="Surrendered Pirate")
    mapper.register_npc(npc)

    # Should recognize as NPC despite enemy_xxx prefix
    assert mapper.is_npc("enemy_pirate_1") == True
    assert mapper.is_enemy("enemy_pirate_1") == False  # Not enemy anymore


def test_target_id_mapper_get_agent_type():
    """TargetIDMapper can return agent type."""
    mapper = TargetIDMapper()

    npc = create_test_npc(agent_id="enemy_guide_1")
    mapper.register_npc(npc)

    assert mapper.get_agent_type("enemy_guide_1") == "npc"


def test_target_id_mapper_player_can_target_npc():
    """Players can always target NPCs."""
    mapper = TargetIDMapper()

    npc = create_test_npc(agent_id="enemy_guide_1")
    mapper.register_npc(npc)

    # Player targeting NPC
    assert mapper.can_target("player_01", "enemy_guide_1", source_type="player") == True


def test_target_id_mapper_enemy_can_target_npc():
    """Enemies can target NPCs (faction check done in enemy_combat.py, not mapper)."""
    mapper = TargetIDMapper()

    npc = create_test_npc(agent_id="enemy_civilian_1", threat_level="non_combatant")
    mapper.register_npc(npc)

    # Enemy targeting NPC - allowed at mapper level
    can_target = mapper.can_target(
        source_id="enemy_raider_1",
        target_id="enemy_civilian_1",
        source_type="enemy"
    )

    assert can_target == True


def test_target_id_mapper_npc_can_target():
    """NPCs can now target (simplified combat in DM adjudication)."""
    mapper = TargetIDMapper()

    # NPC trying to target player - now allowed
    can_target = mapper.can_target("enemy_guide_1", "player_01", source_type="npc")

    assert can_target == True


def test_target_id_mapper_register_multiple_npcs():
    """TargetIDMapper can track multiple NPCs."""
    mapper = TargetIDMapper()

    npc1 = create_test_npc(agent_id="enemy_guide_1", name="Guide")
    npc2 = create_test_npc(agent_id="enemy_medic_1", name="Medic")

    mapper.register_npc(npc1)
    mapper.register_npc(npc2)

    assert mapper.is_npc("enemy_guide_1") == True
    assert mapper.is_npc("enemy_medic_1") == True


def test_target_id_mapper_unregister_npc():
    """TargetIDMapper can unregister NPCs."""
    mapper = TargetIDMapper()

    npc = create_test_npc(agent_id="enemy_guide_1")
    mapper.register_npc(npc)

    assert mapper.is_npc("enemy_guide_1") == True

    mapper.unregister_npc("enemy_guide_1")

    assert mapper.is_npc("enemy_guide_1") == False


def test_target_id_mapper_get_all_npc_ids():
    """TargetIDMapper can list all NPC IDs."""
    mapper = TargetIDMapper()

    npc1 = create_test_npc(agent_id="enemy_guide_1")
    npc2 = create_test_npc(agent_id="enemy_medic_1")

    mapper.register_npc(npc1)
    mapper.register_npc(npc2)

    npc_ids = mapper.get_all_npc_ids()

    assert "enemy_guide_1" in npc_ids
    assert "enemy_medic_1" in npc_ids
    assert len(npc_ids) == 2


def test_target_id_mapper_threat_levels():
    """TargetIDMapper correctly handles all threat levels."""
    mapper = TargetIDMapper()

    threat_levels = ["non_combatant", "potential_threat", "armed_neutral"]

    for level in threat_levels:
        npc = create_test_npc(agent_id=f"enemy_test_{level}", threat_level=level)
        mapper.register_npc(npc)
        assert mapper.is_npc(f"enemy_test_{level}") == True
