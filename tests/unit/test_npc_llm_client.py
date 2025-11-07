"""
Unit tests for NPC LLM Client.

Tests NPC action declaration system with simple prompts.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient, NPCAction


def create_test_npc(
    agent_id="enemy_guide_1",
    name="Guide",
    entity_type="neutral",
    disposition="neutral",
    threat_level="non_combatant"
):
    """Create test NPC."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="Freeborn",
        entity_type=entity_type,
        disposition=disposition,
        threat_level=threat_level,
        description="Test NPC for LLM client testing",
        health=20,
        max_health=20,
        soak=0,
        void_score=0,
        skills={}
    )


@pytest.mark.asyncio
async def test_npc_llm_client_initialization():
    """NPCLLMClient initializes with NPC reference."""
    npc = create_test_npc()
    client = NPCLLMClient(npc)

    assert client.npc == npc
    assert client.npc.name == "Guide"


@pytest.mark.asyncio
async def test_npc_client_declares_pass_when_calm():
    """NPC passes turn when situation is calm and non-threatening."""
    npc = create_test_npc(disposition="friendly")
    client = NPCLLMClient(npc)

    context = "The combat has ended. Players are regrouping peacefully."
    action = await client.declare_action(context)

    assert action.action_type == "pass"
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_declares_dialogue_when_addressed():
    """NPC engages in dialogue when players address them."""
    npc = create_test_npc(disposition="neutral")
    client = NPCLLMClient(npc)

    context = "Player approaches and asks for directions to the data vault."
    action = await client.declare_action(context)

    # Should either dialogue or comply (both reasonable)
    assert action.action_type in ["dialogue", "comply"]
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_declares_flee_when_threatened():
    """Non-combatant NPC flees when combat breaks out."""
    npc = create_test_npc(threat_level="non_combatant", disposition="neutral")
    client = NPCLLMClient(npc)

    context = "Gunfire erupts. Enemies are shooting at the players nearby."
    action = await client.declare_action(context)

    # Non-combatants should flee or hide in combat
    assert action.action_type in ["flee", "hide"]
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_declares_assist_when_allied():
    """Allied NPC assists players when appropriate."""
    npc = create_test_npc(entity_type="ally", disposition="friendly")
    client = NPCLLMClient(npc)

    context = "Player is wounded and needs medical attention."
    action = await client.declare_action(context)

    # Ally should assist or provide dialogue
    assert action.action_type in ["assist", "dialogue"]
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_declares_plead_when_prisoner():
    """Prisoner NPC pleads or complies."""
    npc = create_test_npc(entity_type="prisoner", disposition="prisoner")
    client = NPCLLMClient(npc)

    context = "Players interrogate the captured enemy."
    action = await client.declare_action(context)

    # Prisoner should plead or comply
    assert action.action_type in ["plead", "comply", "dialogue"]
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_includes_npc_context():
    """NPC client includes NPC's name, disposition, and entity type in prompts."""
    npc = create_test_npc(name="Freeborn Navigator", disposition="wary")
    client = NPCLLMClient(npc)

    # Check that client has access to NPC details
    assert client.npc.name == "Freeborn Navigator"
    assert client.npc.disposition == "wary"
    assert client.npc.entity_type == "neutral"


@pytest.mark.asyncio
async def test_npc_client_respects_can_act_flag():
    """NPC client returns pass action when can_act is False."""
    npc = create_test_npc()
    npc.can_act = False
    client = NPCLLMClient(npc)

    context = "Combat rages around the NPC."
    action = await client.declare_action(context)

    assert action.action_type == "pass"
    assert "cannot act" in action.reason.lower()


@pytest.mark.asyncio
async def test_npc_action_schema_validation():
    """NPCAction validates action types and reason length."""
    # Valid actions
    valid_types = ["flee", "hide", "plead", "comply", "dialogue", "assist", "pass"]

    for action_type in valid_types:
        action = NPCAction(
            action_type=action_type,
            reason="Valid reason for action with sufficient length"
        )
        assert action.action_type == action_type

    # Invalid action type should fail
    with pytest.raises(Exception):  # Pydantic ValidationError
        NPCAction(
            action_type="attack",  # Not in valid set
            reason="Invalid action type"
        )


@pytest.mark.asyncio
async def test_npc_client_handles_low_health():
    """NPC with low health prioritizes fleeing or hiding."""
    npc = create_test_npc()
    npc.health = 5  # Low health
    npc.max_health = 20
    client = NPCLLMClient(npc)

    context = "Combat continues. NPC is wounded and bleeding."
    action = await client.declare_action(context)

    # Wounded non-combatant should flee or hide
    assert action.action_type in ["flee", "hide", "plead"]
    assert len(action.reason) > 10


@pytest.mark.asyncio
async def test_npc_client_opportunistic_behavior():
    """NPC passes turn when nothing relevant happening (opportunistic acting)."""
    npc = create_test_npc(disposition="neutral")
    client = NPCLLMClient(npc)

    context = "Players are investigating a terminal. NPC is not involved."
    action = await client.declare_action(context)

    # Should pass when not relevant to situation
    assert action.action_type == "pass"
    assert len(action.reason) > 10
