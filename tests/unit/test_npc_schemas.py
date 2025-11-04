"""
Unit tests for NPC-related Pydantic schemas.

Tests structured output schemas for NPCSpawn, Deescalation, Escalation, and related types.
"""

import pytest
from pydantic import ValidationError
from scripts.aeonisk.multiagent.schemas.story_events import (
    NPCSpawn,
    Deescalation,
    Escalation,
)
from scripts.aeonisk.multiagent.schemas.action_effects import (
    HealingEffect,
    AgentConversion,
)


def test_npc_spawn_valid():
    """NPCSpawn validates with all required fields."""
    spawn = NPCSpawn(
        name="Freeborn Guide",
        faction="Freeborn",
        entity_type="neutral",
        threat_level="non_combatant",
        disposition="neutral",
        description="Weathered navigator with neural optics and void-stained fingers",
        health=20,
        soak=2,
        skills={"perception": 5, "astral_arts": 3}
    )

    assert spawn.name == "Freeborn Guide"
    assert spawn.faction == "Freeborn"
    assert spawn.entity_type == "neutral"
    assert spawn.threat_level == "non_combatant"
    assert spawn.disposition == "neutral"
    assert spawn.health == 20
    assert spawn.soak == 2
    assert spawn.skills == {"perception": 5, "astral_arts": 3}


def test_npc_spawn_entity_types():
    """NPCSpawn supports all valid entity types."""
    entity_types = ["neutral", "ally", "prisoner"]

    for entity_type in entity_types:
        spawn = NPCSpawn(
            name="Test NPC",
            faction="Test",
            entity_type=entity_type,
            threat_level="non_combatant",
            disposition="neutral" if entity_type != "prisoner" else "prisoner",
            description="Test description for validation",
            health=20,
            soak=0
        )
        assert spawn.entity_type == entity_type


def test_npc_spawn_threat_levels():
    """NPCSpawn supports all valid threat levels."""
    threat_levels = ["non_combatant", "potential_threat", "armed_neutral"]

    for threat_level in threat_levels:
        spawn = NPCSpawn(
            name="Test NPC",
            faction="Test",
            entity_type="neutral",
            threat_level=threat_level,
            disposition="neutral",
            description="Test description for validation",
            health=20,
            soak=0
        )
        assert spawn.threat_level == threat_level


def test_npc_spawn_dispositions():
    """NPCSpawn supports all valid dispositions."""
    dispositions = ["friendly", "neutral", "wary", "prisoner"]

    for disposition in dispositions:
        spawn = NPCSpawn(
            name="Test NPC",
            faction="Test",
            entity_type="neutral" if disposition != "prisoner" else "prisoner",
            threat_level="non_combatant",
            disposition=disposition,
            description="Test description for validation",
            health=20,
            soak=0
        )
        assert spawn.disposition == disposition


def test_npc_spawn_min_description_length():
    """NPCSpawn requires description >= 20 chars."""
    with pytest.raises(ValidationError):
        NPCSpawn(
            name="Test",
            faction="Test",
            entity_type="neutral",
            threat_level="non_combatant",
            disposition="neutral",
            description="Too short",  # < 20 chars
            health=20,
            soak=0
        )


def test_npc_spawn_converted_from_enemy():
    """NPCSpawn can track conversion from enemy."""
    spawn = NPCSpawn(
        name="Surrendered Pirate",
        faction="Freeborn",
        entity_type="prisoner",
        threat_level="armed_neutral",
        disposition="prisoner",
        description="Former hostile pirate, now captured",
        health=15,
        soak=5,
        converted_from_enemy_id="enemy_pirate_1"
    )

    assert spawn.converted_from_enemy_id == "enemy_pirate_1"


def test_deescalation_valid():
    """Deescalation validates with all required fields."""
    deesc = Deescalation(
        enemy_id="enemy_raider_1",
        resulting_entity_type="neutral",
        resulting_disposition="neutral",
        reason="Convinced of shared Freeborn kinship, agrees to temporary ceasefire"
    )

    assert deesc.enemy_id == "enemy_raider_1"
    assert deesc.resulting_entity_type == "neutral"
    assert deesc.resulting_disposition == "neutral"
    assert len(deesc.reason) >= 20


def test_deescalation_prisoner():
    """Deescalation can convert to prisoner."""
    deesc = Deescalation(
        enemy_id="enemy_guard_1",
        resulting_entity_type="prisoner",
        resulting_disposition="prisoner",
        reason="Subdued via stun damage, now restrained and interrogatable"
    )

    assert deesc.resulting_entity_type == "prisoner"
    assert deesc.resulting_disposition == "prisoner"


def test_deescalation_min_reason_length():
    """Deescalation requires reason >= 20 chars."""
    with pytest.raises(ValidationError):
        Deescalation(
            enemy_id="enemy_test_1",
            resulting_entity_type="neutral",
            resulting_disposition="neutral",
            reason="Too short"  # < 20 chars
        )


def test_escalation_valid():
    """Escalation validates with all required fields."""
    esc = Escalation(
        npc_id="enemy_civilian_1",
        reason="Attacked by player, now defending self in panic",
        template="desperate_fighter"
    )

    assert esc.npc_id == "enemy_civilian_1"
    assert esc.reason.startswith("Attacked")
    assert esc.template == "desperate_fighter"


def test_escalation_custom_template():
    """Escalation can specify custom enemy template."""
    esc = Escalation(
        npc_id="enemy_guard_1",
        reason="Faction loyalty overrides neutrality, engaging players",
        template="acg_security_guard"
    )

    assert esc.template == "acg_security_guard"


def test_escalation_min_reason_length():
    """Escalation requires reason >= 20 chars."""
    with pytest.raises(ValidationError):
        Escalation(
            npc_id="enemy_test_1",
            reason="Too short",  # < 20 chars
            template="desperate_fighter"
        )


def test_healing_effect_valid():
    """HealingEffect validates with all required fields."""
    heal = HealingEffect(
        target="enemy_guide_1",
        heal_type="hp",
        amount=15,
        source="medkit"
    )

    assert heal.target == "enemy_guide_1"
    assert heal.heal_type == "hp"
    assert heal.amount == 15
    assert heal.source == "medkit"


def test_healing_effect_types():
    """HealingEffect supports all heal types."""
    heal_types = ["stun", "wound", "hp"]

    for heal_type in heal_types:
        heal = HealingEffect(
            target="player_01",
            heal_type=heal_type,
            amount=5
        )
        assert heal.heal_type == heal_type


def test_healing_effect_no_negative():
    """HealingEffect validates amount >= 0."""
    with pytest.raises(ValidationError):
        HealingEffect(
            target="player_01",
            heal_type="hp",
            amount=-5  # Invalid
        )


def test_agent_conversion_valid():
    """AgentConversion validates with all required fields."""
    conversion = AgentConversion(
        round=4,
        agent_id="enemy_pirate_1",
        from_type="enemy",
        to_type="npc",
        trigger="player_intimidation",
        state_snapshot={"health": 12, "stuns": 1, "wounds": 2}
    )

    assert conversion.round == 4
    assert conversion.agent_id == "enemy_pirate_1"
    assert conversion.from_type == "enemy"
    assert conversion.to_type == "npc"
    assert conversion.trigger == "player_intimidation"
    assert conversion.state_snapshot["health"] == 12


def test_agent_conversion_stable_id():
    """AgentConversion preserves agent_id (critical for replay)."""
    conversion = AgentConversion(
        round=7,
        agent_id="enemy_civilian_1",
        from_type="npc",
        to_type="enemy",
        trigger="player_attack",
        state_snapshot={"health": 20}
    )

    # Agent ID never changes
    assert conversion.agent_id == "enemy_civilian_1"
    assert conversion.from_type == "npc"
    assert conversion.to_type == "enemy"


def test_agent_conversion_bidirectional():
    """AgentConversion supports both directions."""
    # Enemy → NPC
    conv1 = AgentConversion(
        round=1,
        agent_id="test_1",
        from_type="enemy",
        to_type="npc",
        trigger="deescalation",
        state_snapshot={}
    )

    # NPC → Enemy
    conv2 = AgentConversion(
        round=2,
        agent_id="test_2",
        from_type="npc",
        to_type="enemy",
        trigger="escalation",
        state_snapshot={}
    )

    assert conv1.from_type == "enemy" and conv1.to_type == "npc"
    assert conv2.from_type == "npc" and conv2.to_type == "enemy"
