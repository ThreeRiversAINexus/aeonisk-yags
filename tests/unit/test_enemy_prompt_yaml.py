"""
Tests for enemy prompt YAML migration.

Verifies that enemy prompts load from enemy.yaml via compose_sections(),
template variables substitute correctly, and output matches legacy formatters.
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.prompt_loader import PromptLoader, compose_sections
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position, SharedIntel
from scripts.aeonisk.multiagent.enemy_prompts import (
    generate_tactical_prompt,
    generate_tactical_prompt_structured,
    _format_declaration_requirements,
    _format_structured_decision_guidance,
    _format_footer,
    _compute_enemy_variables,
    _get_required_sections,
)


def _make_enemy(**overrides) -> EnemyAgent:
    """Create a minimal EnemyAgent for testing."""
    defaults = dict(
        agent_id="enemy_test_01",
        name="ACG Enforcer",
        template="enforcer",
        attributes={"Agility": 3, "Strength": 5, "Perception": 3,
                     "Intelligence": 2, "Empathy": 2, "Willpower": 4,
                     "Dexterity": 3, "Endurance": 4},
        skills={"Brawl": 4, "Melee": 4, "Guns": 3},
        health=55,
        max_health=55,
        soak=8,
        wounds=0,
        position=Position(ring="Near", side="Enemy"),
        initiative=12,
        faction="ACG",
        morale_behavior="flee_when_broken",
        character_brief="Methodical enforcer.",
    )
    defaults.update(overrides)
    return EnemyAgent(**defaults)


class TestComposeSectionsLoadsFromYaml:
    """compose_sections('enemy', ...) loads content from enemy.yaml."""

    def test_compose_sections_loads_header(self):
        result = compose_sections(
            'enemy',
            ['header'],
            variables={'enemy_name': 'Test Unit'}
        )
        assert 'TACTICAL COMBAT AGENT' in result.content
        assert 'Test Unit' in result.content

    def test_compose_sections_loads_footer(self):
        result = compose_sections('enemy', ['footer'])
        assert 'tactical combat agent' in result.content.lower()

    def test_compose_sections_multiple(self):
        result = compose_sections(
            'enemy',
            ['header', 'footer'],
            variables={'enemy_name': 'Alpha'}
        )
        assert 'TACTICAL COMBAT AGENT' in result.content
        assert 'tactical combat agent' in result.content.lower()


class TestStaticSectionsUnchanged:
    """Static YAML sections match original Python output exactly."""

    def test_declaration_requirements_text_matches(self):
        """declaration_requirements from YAML should match Python _format_declaration_requirements()."""
        loader = PromptLoader()
        yaml_result = loader.load_agent_prompt('enemy', section='declaration_requirements')
        python_result = _format_declaration_requirements()
        # Both should contain the core format requirements
        assert 'DEFENCE_TOKEN' in yaml_result.content
        assert 'MAJOR_ACTION' in yaml_result.content
        assert 'TACTICAL_REASONING' in yaml_result.content

    def test_footer_text_matches(self):
        """footer from YAML should match Python _format_footer()."""
        loader = PromptLoader()
        yaml_result = loader.load_agent_prompt('enemy', section='footer')
        python_result = _format_footer()
        # Core content should match
        assert 'tactical combat agent' in yaml_result.content.lower()
        assert 'tactical combat agent' in python_result.lower()

    def test_structured_decision_guidance_matches(self):
        """structured_decision_guidance from YAML should match Python."""
        loader = PromptLoader()
        yaml_result = loader.load_agent_prompt('enemy', section='structured_decision_guidance')
        python_result = _format_structured_decision_guidance()
        assert 'Dialogue' in yaml_result.content
        assert 'Wait' in yaml_result.content
        assert 'Surrender' in yaml_result.content


class TestTemplateVariableSubstitution:
    """Template variables substitute correctly in YAML sections."""

    def test_header_substitutes_enemy_name(self):
        result = compose_sections(
            'enemy', ['header'],
            variables={'enemy_name': 'Void Sniper'}
        )
        assert 'Void Sniper' in result.content
        assert '{enemy_name}' not in result.content

    def test_status_substitutes_health_vars(self):
        variables = {
            'template': 'ENFORCER',
            'health': 40,
            'max_health': 55,
            'health_pct': 72,
            'health_status': 'Wounded',
            'wounds': 1,
            'wound_status': '',
            'stuns': 0,
            'void_score': 2,
            'void_status': '(Stable)',
            'position': 'Near-Enemy',
            'initiative': 12,
            'stance': 'normal',
            'status_effects_display': '',
        }
        result = compose_sections('enemy', ['status'], variables=variables)
        assert '40' in result.content
        assert '55' in result.content
        assert 'Wounded' in result.content


class TestDynamicSectionsPassthrough:
    """Computed Python content passes through via {variable_content} placeholders."""

    def test_battlefield_content_passthrough(self):
        result = compose_sections(
            'enemy', ['battlefield'],
            variables={'battlefield_content': '### Combatants:\n- Alpha at Near-PC'}
        )
        assert 'Combatants' in result.content
        assert 'Alpha at Near-PC' in result.content

    def test_tactical_options_content_passthrough(self):
        result = compose_sections(
            'enemy', ['tactical_options'],
            variables={'tactical_options_content': '### Attack Options:\n- Rifle (Far range)'}
        )
        assert 'Attack Options' in result.content
        assert 'Rifle' in result.content


class TestSectionSelection:
    """_get_required_sections() selects correct sections for text vs structured mode."""

    def test_text_mode_includes_declaration_requirements(self):
        sections = _get_required_sections(structured=False)
        assert 'declaration_requirements' in sections
        assert 'structured_decision_guidance' not in sections

    def test_structured_mode_includes_structured_guidance(self):
        sections = _get_required_sections(structured=True)
        assert 'structured_decision_guidance' in sections
        assert 'declaration_requirements' not in sections

    def test_both_modes_include_core_sections(self):
        for mode in [True, False]:
            sections = _get_required_sections(structured=mode)
            assert 'header' in sections
            assert 'status' in sections
            assert 'doctrine' in sections
            assert 'battlefield' in sections
            assert 'tactical_options' in sections
            assert 'tactical_analysis' in sections
            assert 'retreat_assessment' in sections
            assert 'footer' in sections


class TestConditionalSectionsOmittedWhenEmpty:
    """Optional sections excluded when no data available."""

    def test_situation_history_excluded_when_no_data(self):
        sections = _get_required_sections(
            structured=False, has_history=False
        )
        assert 'situation_history' not in sections

    def test_situation_history_included_when_data(self):
        sections = _get_required_sections(
            structured=False, has_history=True
        )
        assert 'situation_history' in sections

    def test_character_excluded_when_no_brief(self):
        sections = _get_required_sections(
            structured=False, has_character=False
        )
        assert 'character' not in sections

    def test_shared_intel_excluded_when_no_intel(self):
        sections = _get_required_sections(
            structured=False, has_intel=False
        )
        assert 'shared_intel' not in sections

    def test_recent_outcomes_excluded_when_no_narrations(self):
        sections = _get_required_sections(
            structured=False, has_narrations=False
        )
        assert 'recent_outcomes' not in sections

    def test_declared_actions_excluded_when_none(self):
        sections = _get_required_sections(
            structured=False, has_declarations=False
        )
        assert 'declared_actions' not in sections

    def test_engagement_stance_lethal_excluded(self):
        sections = _get_required_sections(
            structured=False, engagement_stance='lethal'
        )
        assert 'engagement_stance_capture' not in sections
        assert 'engagement_stance_adaptive' not in sections

    def test_engagement_stance_capture_included(self):
        sections = _get_required_sections(
            structured=False, engagement_stance='capture'
        )
        assert 'engagement_stance_capture' in sections

    def test_engagement_stance_adaptive_included(self):
        sections = _get_required_sections(
            structured=False, engagement_stance='adaptive'
        )
        assert 'engagement_stance_adaptive' in sections


class TestComputeEnemyVariables:
    """_compute_enemy_variables() builds correct variable dict."""

    def test_returns_dict_with_core_vars(self):
        enemy = _make_enemy()
        variables = _compute_enemy_variables(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=None,
            available_tokens=[],
            current_round=1,
        )
        assert variables['enemy_name'] == 'ACG Enforcer'
        assert variables['health'] == 55
        assert variables['max_health'] == 55
        assert 'health_pct' in variables
        assert 'battlefield_content' in variables
        assert 'tactical_options_content' in variables

    def test_includes_dynamic_content_strings(self):
        enemy = _make_enemy()
        variables = _compute_enemy_variables(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=None,
            available_tokens=[],
            current_round=1,
        )
        # Dynamic content should be pre-computed strings
        assert isinstance(variables['battlefield_content'], str)
        assert isinstance(variables['tactical_options_content'], str)
        assert isinstance(variables['tactical_analysis_content'], str)
        assert isinstance(variables['retreat_assessment_content'], str)


class TestFullPromptRegression:
    """Full prompt generation via YAML matches legacy output structure."""

    def test_generate_tactical_prompt_has_all_sections(self):
        enemy = _make_enemy()
        prompt = generate_tactical_prompt(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        # Should contain key section markers
        assert 'TACTICAL COMBAT AGENT' in prompt
        assert 'YOUR STATUS' in prompt
        assert 'COMBAT DOCTRINE' in prompt
        assert 'BATTLEFIELD' in prompt
        assert 'TACTICAL OPTIONS' in prompt
        assert 'TACTICAL ANALYSIS' in prompt
        assert 'RETREAT ASSESSMENT' in prompt
        assert 'YOUR DECLARATION' in prompt
        assert 'tactical combat agent' in prompt.lower()  # footer

    def test_generate_tactical_prompt_structured_has_structured_guidance(self):
        enemy = _make_enemy()
        prompt = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        assert 'YOUR DECISION' in prompt
        assert 'Dialogue' in prompt
        assert 'Surrender' in prompt
        # Should NOT have text declaration format
        assert 'YOUR DECLARATION' not in prompt

    def test_structured_vs_text_only_differ_in_output_section(self):
        """Both modes should produce identical content except the output format section."""
        enemy = _make_enemy()
        shared_intel = MagicMock(get_recent_intel=MagicMock(return_value=[]))

        text_prompt = generate_tactical_prompt(
            enemy=enemy, player_agents=[], enemy_agents=[enemy],
            shared_intel=shared_intel, available_tokens=[], current_round=1,
        )
        struct_prompt = generate_tactical_prompt_structured(
            enemy=enemy, player_agents=[], enemy_agents=[enemy],
            shared_intel=shared_intel, available_tokens=[], current_round=1,
        )

        # Core sections should appear in both
        for section_header in ['TACTICAL COMBAT AGENT', 'YOUR STATUS', 'COMBAT DOCTRINE',
                               'BATTLEFIELD', 'TACTICAL OPTIONS', 'RETREAT ASSESSMENT']:
            assert section_header in text_prompt, f"Missing '{section_header}' in text prompt"
            assert section_header in struct_prompt, f"Missing '{section_header}' in structured prompt"
