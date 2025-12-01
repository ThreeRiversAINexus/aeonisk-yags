"""
Unit tests for NPCAgent and NPCLLMClient.

Tests the core NPC data structures and simple LLM client for NPC actions.
"""

import pytest
from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient, NPCAction
from scripts.aeonisk.multiagent.mechanics import apply_stun_damage, apply_healing
from scripts.aeonisk.multiagent.schemas.shared_types import Condition


def test_npc_agent_creation():
    """NPCs have stats and position (for tactical continuity)."""
    npc = NPCAgent(
        agent_id="enemy_pirate_1",
        name="Freeborn Pirate",
        faction="Freeborn",
        entity_type="neutral",
        disposition="neutral",
        threat_level="armed_neutral",
        description="Surrendered pirate",
        health=20,
        max_health=20,
        soak=2,
        void_score=3,
        skills={"combat": 3, "guile": 4}
    )

    assert npc.agent_id == "enemy_pirate_1"
    assert npc.name == "Freeborn Pirate"
    assert npc.health == 20
    assert npc.entity_type == "neutral"
    assert npc.disposition == "neutral"
    assert npc.threat_level == "armed_neutral"
    assert not hasattr(npc, 'tactics')
    assert hasattr(npc, 'position')  # NPCs always have position
    assert npc.position.ring == "Near"  # Default position
    assert npc.position.side == "Enemy"


def test_npc_has_full_stats():
    """NPCs have complete stat block like enemies."""
    npc = NPCAgent(
        agent_id="enemy_civilian_1",
        name="Bystander",
        faction="Civilian",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Scared civilian",
        health=15,
        max_health=15,
        soak=0,
        void_score=2,
        skills={"perception": 2},
        stuns=0,
        wounds=0,
        conditions=[]
    )

    assert npc.health == 15
    assert npc.max_health == 15
    assert npc.soak == 0
    assert npc.void_score == 2
    assert npc.stuns == 0
    assert npc.wounds == 0
    assert len(npc.conditions) == 0


def test_npc_can_take_damage():
    """NPCs can be damaged (triggers escalation potential)."""
    npc = NPCAgent(
        agent_id="enemy_bystander_1",
        name="Bystander",
        faction="Civilian",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Civilian caught in crossfire",
        health=20,
        max_health=20,
        soak=2,
        void_score=2,
        skills={}
    )

    # Apply stun damage
    initial_health = npc.health
    apply_stun_damage(npc, 15)

    assert npc.stuns > 0
    assert npc.health == initial_health  # Health unchanged, stuns applied


def test_npc_can_be_healed():
    """NPCs can receive healing (key for prisoner stabilization)."""
    npc = NPCAgent(
        agent_id="enemy_injured_1",
        name="Injured Civilian",
        faction="Civilian",
        entity_type="prisoner",
        disposition="prisoner",
        threat_level="non_combatant",
        description="Wounded prisoner",
        health=10,
        max_health=20,
        soak=0,
        void_score=2,
        skills={}
    )

    result = apply_healing(npc, amount=5, heal_type="hp")

    assert npc.health == 15
    assert result["amount_healed"] == 5


def test_npc_conversion_tracking():
    """NPCs track conversion history."""
    npc = NPCAgent(
        agent_id="enemy_raider_1",
        name="Raider",
        faction="Freeborn",
        entity_type="prisoner",
        disposition="prisoner",
        threat_level="potential_threat",
        description="Captured raider",
        health=15,
        max_health=30,
        soak=5,
        void_score=4,
        skills={"combat": 5},
        converted_from_enemy=True,
        original_enemy_template="freeborn_pirate"
    )

    assert npc.converted_from_enemy == True
    assert npc.original_enemy_template == "freeborn_pirate"


def test_npc_action_schema():
    """NPCAction validates correctly."""
    action = NPCAction(
        action_type="flee",
        reason="I run for cover behind the cargo crates"
    )

    assert action.action_type == "flee"
    assert len(action.reason) > 0
    assert action.target is None


def test_npc_action_with_target():
    """NPCAction can have target for dialogue/assist."""
    action = NPCAction(
        action_type="dialogue",
        reason="I tell the player about the vault code",
        target="player_01",
        dialogue_content="The vault code is 4-7-2-9. Use it wisely."
    )

    assert action.action_type == "dialogue"
    assert action.target == "player_01"
    assert action.dialogue_content == "The vault code is 4-7-2-9. Use it wisely."


def test_npc_action_types_valid():
    """NPCAction only accepts valid action types."""
    valid_types = ["flee", "hide", "plead", "comply", "dialogue", "assist", "pass"]
    # These action types require dialogue_content
    dialogue_required = ["dialogue", "plead"]

    for action_type in valid_types:
        if action_type in dialogue_required:
            action = NPCAction(
                action_type=action_type,
                reason="Test action with sufficient length for validation",
                dialogue_content="Test dialogue content for validation purposes."
            )
        else:
            action = NPCAction(
                action_type=action_type,
                reason="Test action with sufficient length for validation"
            )
        assert action.action_type == action_type


def test_npc_llm_client_exists():
    """NPCLLMClient can be instantiated."""
    npc = NPCAgent(
        agent_id="enemy_test_client",
        name="Test NPC",
        faction="Test",
        entity_type="neutral",
        disposition="neutral",
        threat_level="non_combatant",
        description="Test NPC for client instantiation",
        health=20,
        max_health=20,
        soak=0,
        void_score=2,
        skills={}
    )
    # NPCLLMClient uses llm_provider, not model parameter
    client = NPCLLMClient(npc, llm_provider=None, temperature=0.8)
    assert client is not None
    assert client.npc == npc
    assert client.temperature == 0.8


def test_npc_threat_levels():
    """NPCs support different threat levels."""
    threat_levels = ["non_combatant", "potential_threat", "armed_neutral"]

    for level in threat_levels:
        npc = NPCAgent(
            agent_id=f"enemy_test_{level}",
            name="Test NPC",
            faction="Test",
            entity_type="neutral",
            disposition="neutral",
            threat_level=level,
            description="Test",
            health=20,
            max_health=20,
            soak=0,
            void_score=2,
            skills={}
        )
        assert npc.threat_level == level


def test_npc_entity_types():
    """NPCs support different entity types."""
    entity_types = ["neutral", "ally", "prisoner"]

    for entity_type in entity_types:
        npc = NPCAgent(
            agent_id=f"enemy_test_{entity_type}",
            name="Test NPC",
            faction="Test",
            entity_type=entity_type,
            disposition=entity_type if entity_type != "ally" else "friendly",
            threat_level="non_combatant",
            description="Test",
            health=20,
            max_health=20,
            soak=0,
            void_score=2,
            skills={}
        )
        assert npc.entity_type == entity_type


def test_npc_dispositions():
    """NPCs support different dispositions."""
    dispositions = ["friendly", "neutral", "wary", "prisoner"]

    for disposition in dispositions:
        npc = NPCAgent(
            agent_id=f"enemy_test_{disposition}",
            name="Test NPC",
            faction="Test",
            entity_type="neutral" if disposition != "prisoner" else "prisoner",
            disposition=disposition,
            threat_level="non_combatant",
            description="Test",
            health=20,
            max_health=20,
            soak=0,
            void_score=2,
            skills={}
        )
        assert npc.disposition == disposition


def test_npc_with_conditions():
    """NPCs can have conditions like enemies."""
    npc = NPCAgent(
        agent_id="enemy_wounded_1",
        name="Wounded NPC",
        faction="Freeborn",
        entity_type="prisoner",
        disposition="prisoner",
        threat_level="non_combatant",
        description="Bleeding prisoner",
        health=5,
        max_health=20,
        soak=2,
        void_score=3,
        skills={},
        conditions=[
            Condition(name="Bleeding", penalty=-2, description="Losing blood, -2 to all rolls"),
            Condition(name="Shaken", penalty=-1, description="Frightened, -1 to all rolls")
        ]
    )

    assert len(npc.conditions) == 2
    assert npc.conditions[0].name == "Bleeding"
    assert npc.conditions[1].name == "Shaken"


def test_npc_action_dialogue_has_content():
    """NPCAction with action_type='dialogue' should have actual dialogue content."""
    # Create dialogue action with content
    action = NPCAction(
        action_type="dialogue",
        reason="Responding to player's question about the location of the vault",
        dialogue_content="The vault is in the basement, past the security checkpoint. But you'll need a keycard to get in."
    )

    assert action.action_type == "dialogue"
    assert action.dialogue_content is not None
    assert len(action.dialogue_content) > 0
    assert "vault" in action.dialogue_content.lower()


def test_npc_action_dialogue_content_optional_for_non_dialogue():
    """dialogue_content should be optional for non-dialogue actions."""
    # Non-dialogue actions don't need dialogue_content
    flee_action = NPCAction(
        action_type="flee",
        reason="Running from the armed guards approaching from the north corridor"
    )

    assert flee_action.action_type == "flee"
    assert flee_action.dialogue_content is None


def test_npc_action_dialogue_content_required_for_dialogue():
    """dialogue_content should be required when action_type is 'dialogue'."""
    from pydantic import ValidationError

    # This should fail validation if we try to create dialogue without content
    with pytest.raises(ValidationError, match="dialogue_content.*REQUIRED"):
        NPCAction(
            action_type="dialogue",
            reason="Responding to player",
            dialogue_content=None  # Should fail - dialogue needs content!
        )
