"""Tests for the names_client hook in AIDMAgent._process_npc_spawn.

Confirms the MCP-name override path: when a NamesClient is injected and
returns a non-None canonical name, the spawned NPCAgent uses it (and the
agent_id reflects it). When the client is absent or returns None, the
LLM-generated NPCSpawn.name survives unchanged.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from scripts.aeonisk.multiagent.schemas.story_events import NPCSpawn
from scripts.aeonisk.multiagent.shared_state import SharedState


def _make_shared_state() -> Mock:
    s = Mock(spec=SharedState)
    s.npc_agents = []
    s.enemy_agents = []
    s.add_npc = Mock()
    s.get_target_id_mapper = Mock(return_value=None)
    mechanics = Mock()
    mechanics.jsonl_logger = Mock()
    s.get_mechanics_engine = Mock(return_value=mechanics)
    return s


def _make_npc_spawn(**overrides) -> NPCSpawn:
    defaults = dict(
        name="LLM-Hallucinated Name",
        faction="Sovereign Nexus",
        entity_type="neutral",
        threat_level="non_combatant",
        disposition="friendly",
        description="A short canonical description used for tests only.",
        pronouns="she/her",
        health=20,
        soak=1,
        skills={"perception": 3},
    )
    defaults.update(overrides)
    return NPCSpawn(**defaults)


def test_process_npc_spawn_uses_mcp_name_when_client_provided() -> None:
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    client = Mock()
    client.generate_npc_name = Mock(return_value="Vehalin Halessan")

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=_make_shared_state(),
        names_client=client,
    )

    npc = dm._process_npc_spawn(_make_npc_spawn())

    assert npc.name == "Vehalin Halessan"
    assert "vehalin_halessan" in npc.agent_id
    client.generate_npc_name.assert_called_once()


def test_process_npc_spawn_keeps_llm_name_when_client_none() -> None:
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=_make_shared_state(),
        names_client=None,
    )

    npc = dm._process_npc_spawn(_make_npc_spawn(name="Original LLM Name"))
    assert npc.name == "Original LLM Name"
    assert "original_llm_name" in npc.agent_id


def test_process_npc_spawn_keeps_llm_name_when_mcp_returns_none() -> None:
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    client = Mock()
    client.generate_npc_name = Mock(return_value=None)  # MCP skipped / failed open

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=_make_shared_state(),
        names_client=client,
    )

    npc = dm._process_npc_spawn(_make_npc_spawn(name="Fallback LLM Name"))
    assert npc.name == "Fallback LLM Name"
    client.generate_npc_name.assert_called_once()


def test_process_npc_spawn_passes_pronouns_to_client() -> None:
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    client = Mock()
    client.generate_npc_name = Mock(return_value="Iresa Halessan")

    dm = AIDMAgent(
        agent_id="dm_test",
        socket_path="/tmp/test.sock",
        llm_config={},
        shared_state=_make_shared_state(),
        names_client=client,
    )

    dm._process_npc_spawn(_make_npc_spawn(pronouns="she/her", faction="Sovereign Nexus"))

    call_kwargs = client.generate_npc_name.call_args.kwargs
    assert call_kwargs["faction"] == "Sovereign Nexus"
    assert call_kwargs["pronouns"] == "she/her"
