"""
Tests for NPC prompt YAML migration.

Verifies that NPC prompts load from npc_identity.yaml and npc_action.yaml
via load_modular_prompt(), variables substitute correctly, and the refactored
_get_system_prompt() uses the YAML loader.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from scripts.aeonisk.multiagent.prompt_loader import PromptLoader, load_modular_prompt
from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient


def _make_npc(**overrides) -> NPCAgent:
    """Create a minimal NPCAgent for testing."""
    defaults = dict(
        agent_id="npc_test_01",
        name="Mira Chen",
        faction="Freeborn",
        entity_type="neutral",
        disposition="friendly",
        threat_level="non_combatant",
        description="A nervous courier with darting eyes.",
        health=20,
        max_health=20,
        soak=6,
        void_score=0,
        can_act=False,  # Prevent LLM client init
    )
    defaults.update(overrides)
    return NPCAgent(**defaults)


class TestNpcIdentityLoads:
    """npc_identity.yaml loads via load_modular_prompt."""

    def test_npc_identity_loads_with_variables(self):
        variables = {
            'npc_name': 'Mira Chen',
            'entity_type': 'neutral',
            'disposition': 'friendly',
            'threat_level': 'non_combatant',
            'faction': 'Freeborn',
            'personality_note': '**Your Personality:** A nervous courier with darting eyes.',
            'faction_context': 'Your faction (Freeborn) stance: Neutral',
        }
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity'],
            variables=variables,
        )
        assert 'Mira Chen' in result.content
        assert 'neutral' in result.content
        assert 'Freeborn' in result.content

    def test_npc_identity_has_faction_abbreviations(self):
        """Identity module should include canonical faction abbreviations."""
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity'],
        )
        assert 'ACG' in result.content
        assert 'Tempest Industries' in result.content or 'Tempest' in result.content


class TestNpcActionLoads:
    """npc_action.yaml loads via load_modular_prompt."""

    def test_npc_action_loads(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_action'],
        )
        assert len(result.content) > 100
        assert 'NPC' in result.content

    def test_npc_action_has_heal_guidance(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_action'],
        )
        assert 'heal' in result.content.lower()
        assert 'Medicine' in result.content


class TestNpcPromptHasAllActions:
    """Combined NPC prompt includes all required action types."""

    def test_combined_prompt_includes_all_actions(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity', 'npc_action'],
        )
        content_lower = result.content.lower()
        required_actions = ['flee', 'hide', 'plead', 'comply', 'dialogue',
                           'assist', 'heal', 'attack', 'transfer', 'pass']
        for action in required_actions:
            assert action in content_lower, f"Missing action '{action}' in NPC prompt"


class TestNpcVariableSubstitution:
    """NPC template variables substitute correctly."""

    def test_npc_name_substitutes(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity'],
            variables={'npc_name': 'Korvax Prime'},
        )
        assert 'Korvax Prime' in result.content
        assert '{npc_name}' not in result.content

    def test_entity_type_substitutes(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity'],
            variables={'entity_type': 'prisoner'},
        )
        assert 'prisoner' in result.content

    def test_disposition_substitutes(self):
        result = load_modular_prompt(
            agent_type='npc',
            module_names=['npc_identity'],
            variables={'disposition': 'wary'},
        )
        assert 'wary' in result.content


class TestGetSystemPromptUsesYaml:
    """Refactored _get_system_prompt() routes through YAML loader."""

    def test_system_prompt_contains_identity(self):
        """System prompt should include NPC identity from YAML."""
        npc = _make_npc(can_act=False)
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        assert 'Mira Chen' in prompt
        assert 'neutral' in prompt
        assert 'Freeborn' in prompt

    def test_system_prompt_contains_action_guidance(self):
        """System prompt should include action guidance from YAML."""
        npc = _make_npc(can_act=False)
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        # Should have all action types documented
        assert 'flee' in prompt.lower()
        assert 'dialogue' in prompt.lower()
        assert 'heal' in prompt.lower()
        assert 'attack' in prompt.lower()
        assert 'transfer' in prompt.lower()

    def test_system_prompt_has_personality(self):
        """System prompt should include personality from NPC description."""
        npc = _make_npc(description="A nervous courier with darting eyes.", can_act=False)
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        assert 'nervous courier' in prompt

    def test_system_prompt_has_faction_context(self):
        """System prompt should include faction relationship context."""
        npc = _make_npc(faction="ACG", can_act=False)
        client = NPCLLMClient(npc)
        prompt = client._get_system_prompt()
        assert 'ACG' in prompt

    def test_system_prompt_uses_loader(self):
        """Verify _get_system_prompt calls load_modular_prompt internally."""
        npc = _make_npc(can_act=False)
        client = NPCLLMClient(npc)
        with patch('scripts.aeonisk.multiagent.npc_agent.load_modular_prompt') as mock_loader:
            mock_loader.return_value = MagicMock(content="Mocked NPC prompt content")
            prompt = client._get_system_prompt()
            mock_loader.assert_called_once()
            assert prompt == "Mocked NPC prompt content"
