"""
Unit tests for player prompt generation.

Tests that player prompts include correct context, entity information,
and scenario details according to TDD specifications.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.player import AIPlayerAgent
from scripts.aeonisk.multiagent.shared_state import SharedState


class TestPlayerEntityFormatting:
    """Test that player entity lists show correct names and IDs."""

    def test_npc_names_shown_not_agent_ids(self):
        """
        Test that NPCs show their .name attribute in entity list, not agent_id.

        ISSUE: player.py:1954 checks for npc.character_state.name but NPCs
        (dataclass NPCAgent) have .name directly, NOT .character_state.name
        This causes fallback to npc.agent_id (e.g., "npc_ff5fc612")

        EXPECTED: NPCs should ALWAYS show their .name like
        "Surrendered Gang Member" not "npc_ff5fc612"
        """
        # Create mock player agent
        player = Mock(spec=AIPlayerAgent)
        player.shared_state = Mock(spec=SharedState)

        # Create mock NPC with .name (NOT .character_state.name)
        mock_npc = Mock()
        mock_npc.agent_id = "npc_ff5fc612"
        mock_npc.name = "Surrendered Gang Member"  # NPCs have .name directly
        mock_npc.health = 15
        mock_npc.max_health = 20

        # Mock target ID mapper to provide target ID
        player.shared_state.target_id_mapper = Mock()
        player.shared_state.target_id_mapper.get_target_id.return_value = "tgt_abc123"

        # Mock shared state to include this NPC
        player.shared_state.npc_agents = [mock_npc]
        player.shared_state.player_agents = []
        player.shared_state.enemy_combat = None  # No enemies
        player.shared_state.current_env_objects = []  # No env objects

        # Call the actual formatting method
        result = AIPlayerAgent._format_entities_present(player)

        # ASSERT: Result should contain NPC's character name, NOT agent_id
        assert "Surrendered Gang Member" in result, \
            f"Expected NPC name 'Surrendered Gang Member' in entity list, got: {result}"
        assert "npc_ff5fc612" not in result, \
            f"Agent ID 'npc_ff5fc612' should NOT appear in entity list, got: {result}"
        assert "tgt_abc123" in result, \
            f"Expected target ID 'tgt_abc123' in entity list, got: {result}"

    def test_npc_without_name_attribute_shows_agent_id_fallback(self):
        """
        Test that NPCs without .name attribute fall back to showing agent_id.

        This is a fallback case - ideally all NPCs should have .name,
        but we need graceful degradation if the attribute is missing.
        """
        # Create mock player agent
        player = Mock(spec=AIPlayerAgent)
        player.shared_state = Mock(spec=SharedState)

        # Create mock NPC WITHOUT .name attribute
        # Use spec to prevent auto-creation of missing attributes
        class NPCWithoutName:
            def __init__(self):
                self.agent_id = "npc_broken_123"
                self.health = 12
                self.max_health = 12
                # Deliberately no 'name' attribute

        mock_npc = NPCWithoutName()

        # Mock target ID mapper
        player.shared_state.target_id_mapper = Mock()
        player.shared_state.target_id_mapper.get_target_id.return_value = "tgt_xyz789"

        # Mock shared state
        player.shared_state.npc_agents = [mock_npc]
        player.shared_state.player_agents = []
        player.shared_state.enemy_combat = None
        player.shared_state.current_env_objects = []  # No env objects

        # Call formatting
        result = AIPlayerAgent._format_entities_present(player)

        # ASSERT: Should fall back to showing agent_id
        assert "npc_broken_123" in result, \
            f"Expected fallback to agent_id 'npc_broken_123' for NPC without .name, got: {result}"


class TestPlayerCombatPromptTargeting:
    """Test that combat prompts allow targeting of NPCs, enemies, and allies."""

    def test_combat_prompt_allows_npc_targeting(self):
        """
        Test that Phase 2 combat prompt explicitly allows NPC targeting.

        ISSUE: player_action_combat.yaml:19 says "Declare target (enemy combatant)"
        which excludes NPCs and allies.

        EXPECTED: Prompt should say "Declare target (any combatant - ally, enemy, or NPC)"
        and include NPC targeting examples.
        """
        # Read the actual combat prompt file directly
        import yaml
        prompt_path = "scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_combat.yaml"

        with open(prompt_path, 'r') as f:
            combat_prompt = yaml.safe_load(f)

        prompt_text = combat_prompt.get("content", "")

        # Check for inclusive targeting language
        assert "NPC" in prompt_text or "non-player character" in prompt_text.lower(), \
            "Combat prompt should explicitly mention NPCs as valid targets"

        # Check that targeting instruction mentions allies/enemies/NPCs
        assert ("ally, enemy, or NPC" in prompt_text or
                "ally, enemy, and NPC" in prompt_text or
                "allies, enemies, or NPCs" in prompt_text), \
            "Combat prompt should explicitly state 'ally, enemy, or NPC' as valid targets"

    def test_combat_prompt_includes_npc_targeting_example(self):
        """
        Test that combat prompt includes at least one example of targeting an NPC.

        CURRENT: All examples show tgt_enemy_01, tgt_gang_02, etc.
        EXPECTED: At least one example shows targeting an NPC (e.g., tgt_prisoner_01)
        """
        import yaml
        prompt_path = "scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_combat.yaml"

        with open(prompt_path, 'r') as f:
            combat_prompt = yaml.safe_load(f)

        prompt_text = combat_prompt.get("content", "")

        # Check for NPC targeting examples
        # Look for patterns like: target="tgt_<something_npc_related>"
        npc_target_indicators = [
            "tgt_prisoner",
            "tgt_captive",
            "tgt_surrendered",
            "tgt_npc",
            'target an NPC',
            'targeting an NPC',
            'Targeting an NPC'
        ]

        has_npc_example = any(indicator in prompt_text for indicator in npc_target_indicators)

        assert has_npc_example, \
            f"Combat prompt should include at least one NPC targeting example. " \
            f"Searched for: {npc_target_indicators}"


class TestPlayerScenarioContext:
    """Test that player prompts include scenario context (location, situation, theme)."""

    def test_scenario_context_in_phase1_intent_prompt_template(self):
        """
        Test that player_intent.yaml template includes scenario context variables.

        ISSUE: player_intent.yaml only shows {recent_events} (last round synthesis),
        does NOT show current scenario location/situation/theme variables.

        EXPECTED: Phase 1 template should have placeholders for:
        - {location}
        - {situation}
        - {theme}
        - {recent_events} (already exists)
        """
        import yaml
        prompt_path = "scripts/aeonisk/multiagent/prompts/claude/en/player/player_intent.yaml"

        with open(prompt_path, 'r') as f:
            intent_prompt = yaml.safe_load(f)

        template_text = intent_prompt.get("content", "")

        # Check for scenario context variables
        expected_variables = ["{location}", "{situation}", "{theme}"]

        has_location = "{location}" in template_text
        has_situation = "{situation}" in template_text
        has_theme = "{theme}" in template_text

        # ASSERT: At minimum, location and situation should be present
        assert has_location, \
            "player_intent.yaml should include {location} variable for current location"
        assert has_situation, \
            "player_intent.yaml should include {situation} variable for current situation"

        # Theme is nice-to-have but not critical
        # (Optional assertion - could remove if theme not needed)

    def test_scenario_context_section_exists_in_phase1_template(self):
        """
        Test that player_intent.yaml has a dedicated scenario context section.

        EXPECTED: Template should have a section showing current scenario
        before the "Recent Context" section.
        """
        import yaml
        prompt_path = "scripts/aeonisk/multiagent/prompts/claude/en/player/player_intent.yaml"

        with open(prompt_path, 'r') as f:
            intent_prompt = yaml.safe_load(f)

        template_text = intent_prompt.get("content", "")

        # Check for scenario context section header
        scenario_section_indicators = [
            "Current Scenario",
            "**Current Scenario:**",
            "## Current Scenario",
            "Location:",
            "**Location:**"
        ]

        has_scenario_section = any(indicator in template_text for indicator in scenario_section_indicators)

        assert has_scenario_section, \
            f"player_intent.yaml should have a 'Current Scenario' section. " \
            f"Searched for: {scenario_section_indicators}"
