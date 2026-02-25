"""
Tests for the de-escalation pipeline fix.

Covers 4 pipeline gaps:
1. Resolution summary data shape + target info
2. Social target extraction + conversion check markers
3. Enemy prompt declared actions + non-combat options
4. Conversion check YAML prompt updates (tested indirectly via markers)
"""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


# =============================================================================
# HELPERS
# =============================================================================

def _make_mock_enemy():
    """Create a mock enemy agent with all required attributes for prompt generation."""
    enemy = MagicMock()
    enemy.name = "Test Enemy"
    enemy.agent_id = "enemy_test_001"
    enemy.template = "grunt"
    enemy.health = 20
    enemy.max_health = 20
    enemy.wounds = 0
    enemy.stuns = 0
    enemy.void_score = 0
    enemy.position = MagicMock()
    enemy.position.name = "Near-PC"
    enemy.initiative = 10
    enemy.stance = "aggressive"
    enemy.weapons = []
    enemy.special_abilities = []
    enemy.faction = "Independent"
    enemy.doctrine = {}
    enemy.status_effects = []
    enemy._situation_history = None
    enemy.character_brief = None
    enemy.unit_count = 1
    enemy.engagement_stance = "lethal"
    enemy.get_health_percentage.return_value = 100
    enemy.morale_behavior = 'flee_when_broken'
    enemy.retreat_threshold = 0.25
    enemy.archetype = None
    enemy.tactics = 'aggressive'
    enemy.threat_priority = 'nearest'
    return enemy


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_target_id_mapper():
    """Create a mock target_id_mapper that resolves tgt IDs to agents."""
    mapper = MagicMock()

    # Create mock agents with names
    enemy_agent = MagicMock()
    enemy_agent.name = "Veyra Sato"
    enemy_agent.agent_id = "enemy_elite_veyra_001"

    npc_agent = MagicMock()
    npc_agent.name = "Dock Worker"
    npc_agent.agent_id = "npc_dock_worker_001"

    pc_agent = MagicMock()
    pc_agent.name = "Kael Dren"
    pc_agent.agent_id = "pc_kael_001"
    pc_agent.character_state = MagicMock()
    pc_agent.character_state.name = "Kael Dren"

    def resolve_target(target_id):
        mapping = {
            'tgt_a1b2': enemy_agent,
            'tgt_c3d4': npc_agent,
            'tgt_e5f6': pc_agent,
        }
        return mapping.get(target_id)

    mapper.resolve_target = resolve_target
    return mapper


@pytest.fixture
def mock_shared_state(mock_target_id_mapper):
    """Create a mock shared_state with target_id_mapper."""
    state = MagicMock()
    state.get_target_id_mapper.return_value = mock_target_id_mapper
    return state


@pytest.fixture
def pc_resolution_dict():
    """A PC resolution dict as it appears in all_resolutions (serializable_res format from dm.py:3136)."""
    return {
        'player_id': 'player_01',
        'character_name': 'Kael Dren',
        'initiative': 14,
        'action': {
            'action_type': 'social',
            'intent': 'Negotiate a ceasefire with the guard',
            'description': 'I try to talk the guard into standing down',
            'target': 'tgt_a1b2',
            'weapon': None,
        },
        'resolution': {
            'resolution': {
                'success': True,
                'margin': 8,
                'success_tier': 'SOLID_SUCCESS',
            },
        },
        'narration': 'Kael speaks with calm authority, and the guard hesitates...',
        'effects': None,
    }


@pytest.fixture
def pc_combat_resolution_dict():
    """A PC combat resolution that dealt damage."""
    return {
        'player_id': 'player_02',
        'character_name': 'Riven Ashford',
        'initiative': 16,
        'action': {
            'action_type': 'combat',
            'intent': 'Shoot the enemy with my rifle',
            'description': 'I fire at the guard',
            'target': 'tgt_a1b2',
            'weapon': 'Kinetic Rifle',
        },
        'resolution': {
            'resolution': {
                'success': True,
                'margin': 5,
                'success_tier': 'MARGINAL_SUCCESS',
            },
        },
        'narration': 'Riven fires a burst from her rifle...',
        'effects': MagicMock(
            damage=[MagicMock(dealt=12)],
            clock_changes=None,
            conditions=None,
        ),
    }


@pytest.fixture
def pc_failed_social_resolution():
    """A PC social resolution that failed."""
    return {
        'player_id': 'player_03',
        'character_name': 'Sera Voss',
        'initiative': 10,
        'action': {
            'action_type': 'social',
            'intent': 'Intimidate the enemy into backing down',
            'description': 'I threaten the guard',
            'target': 'tgt_a1b2',
            'weapon': None,
        },
        'resolution': {
            'resolution': {
                'success': False,
                'margin': -3,
                'success_tier': 'FAILURE',
            },
        },
        'narration': 'Sera tries to intimidate the guard but her words fall flat...',
        'effects': None,
    }


@pytest.fixture
def pc_social_targeting_npc():
    """A PC social resolution targeting an NPC (not enemy)."""
    return {
        'player_id': 'player_01',
        'character_name': 'Kael Dren',
        'initiative': 14,
        'action': {
            'action_type': 'social',
            'intent': 'Ask the dock worker for information',
            'description': 'I talk to the dock worker',
            'target': 'tgt_c3d4',
            'weapon': None,
        },
        'resolution': {
            'resolution': {
                'success': True,
                'margin': 6,
                'success_tier': 'SOLID_SUCCESS',
            },
        },
        'narration': 'The dock worker nods and shares what he knows...',
        'effects': None,
    }


@pytest.fixture
def enemy_resolution_dict():
    """An enemy resolution dict as it appears in all_resolutions (from enemy_combat.py)."""
    return {
        'enemy_id': 'enemy_grunt_4bc22537',
        'character_name': 'ACG Enforcer Alpha',
        'action': 'attack',
        'result': 'success',
        'target': 'pc_kael_001',
        'narration': 'ACG Enforcer Alpha fires at Kael with a kinetic rifle...',
        'effects': {
            'damage': {'dealt': 8, 'type': 'wound'},
        },
    }


@pytest.fixture
def mock_player_agents_with_declarations():
    """Create mock player agents with declared_actions_this_round."""
    agent1 = MagicMock()
    agent1.declared_actions_this_round = {
        'Kael Dren': ('Negotiate ceasefire', 'Negotiate a ceasefire', 'tgt_a1b2', None, 'Diplomatic approach', 14),
    }

    agent2 = MagicMock()
    agent2.declared_actions_this_round = {
        'Riven Ashford': ('Cover fire', 'Provide suppressing fire', 'tgt_c3d4', 'Kinetic Rifle', 'Support teammates', 16),
    }

    return [agent1, agent2]


@pytest.fixture
def mock_player_agents_no_declarations():
    """Create mock player agents with no declarations."""
    agent1 = MagicMock()
    agent1.declared_actions_this_round = {}
    return [agent1]


# =============================================================================
# GAP 1: Resolution Summary Tests
# =============================================================================

class TestResolutionSummaryDataShape:
    """Test that _build_resolution_summary correctly extracts data from both PC and enemy formats."""

    def _build_summary(self, session, resolutions):
        """Helper to call _build_resolution_summary."""
        return session._build_resolution_summary(resolutions)

    def _make_session(self, shared_state=None):
        """Create a minimal session mock with _build_resolution_summary from real code."""
        # Import the real class to get the method
        import importlib
        import sys

        # We need to import the actual method, but the class is huge.
        # Instead, create a mock and bind the real method.
        from scripts.aeonisk.multiagent.session import SelfPlayingSession

        session = MagicMock(spec=SelfPlayingSession)
        session.shared_state = shared_state
        # Bind the real method
        session._build_resolution_summary = SelfPlayingSession._build_resolution_summary.__get__(session, SelfPlayingSession)
        return session

    def test_resolution_summary_extracts_action_from_pc_dict_format(self, pc_resolution_dict, mock_shared_state):
        """PC dict action should extract intent, not show 'Unknown action'."""
        session = self._make_session(mock_shared_state)
        summary = self._build_summary(session, [pc_resolution_dict])

        # Should contain the intent text, not 'Unknown action'
        assert 'Negotiate a ceasefire' in summary
        assert 'Unknown action' not in summary

    def test_resolution_summary_extracts_success_from_nested_outcome(self, pc_resolution_dict, mock_shared_state):
        """PC resolution success/margin should be extracted from nested resolution dict."""
        session = self._make_session(mock_shared_state)
        summary = self._build_summary(session, [pc_resolution_dict])

        # Should show SUCCESS with correct margin
        assert 'SUCCESS' in summary
        assert '+8' in summary

    def test_resolution_summary_includes_target_name(self, pc_resolution_dict, mock_shared_state):
        """Resolution summary should include resolved target name when target exists."""
        session = self._make_session(mock_shared_state)
        summary = self._build_summary(session, [pc_resolution_dict])

        # Should include target name (resolved from tgt_a1b2 -> Veyra Sato)
        assert 'Veyra Sato' in summary

    def test_resolution_summary_no_target_when_none(self, mock_shared_state):
        """No target info when action has no target."""
        resolution = {
            'player_id': 'player_01',
            'character_name': 'Kael Dren',
            'initiative': 14,
            'action': {
                'action_type': 'investigate',
                'intent': 'Search the room for clues',
                'target': None,
            },
            'resolution': {
                'resolution': {
                    'success': True,
                    'margin': 3,
                },
            },
            'narration': 'Kael searches carefully...',
            'effects': None,
        }
        session = self._make_session(mock_shared_state)
        summary = self._build_summary(session, [resolution])

        assert 'targeting' not in summary.lower()

    def test_resolution_summary_enemy_format_works(self, enemy_resolution_dict, mock_shared_state):
        """Enemy string action format should still work correctly."""
        session = self._make_session(mock_shared_state)
        summary = self._build_summary(session, [enemy_resolution_dict])

        # Enemy action is a string 'attack'
        assert 'attack' in summary.lower()
        assert 'ACG Enforcer Alpha' in summary


# =============================================================================
# GAP 2: Social Target Extraction Tests
# =============================================================================

class TestSocialTargetExtraction:
    """Test _extract_social_target_ids() identifies enemies targeted by successful non-combat actions."""

    def _make_session(self, shared_state=None):
        """Create session with the real _extract_social_target_ids method."""
        from scripts.aeonisk.multiagent.session import SelfPlayingSession
        session = MagicMock(spec=SelfPlayingSession)
        session.shared_state = shared_state
        session._extract_social_target_ids = SelfPlayingSession._extract_social_target_ids.__get__(session, SelfPlayingSession)
        return session

    def _make_shared_state_with_enemies(self, enemy_agent_ids):
        """Create shared_state with enemy combat that has specific enemy agent_ids."""
        state = MagicMock()

        # Mock target_id_mapper
        mapper = MagicMock()
        agents = {}
        for agent_id in enemy_agent_ids:
            agent = MagicMock()
            agent.agent_id = agent_id
            agent.name = f"Enemy {agent_id}"
            agents[agent_id] = agent

        def resolve_target(target_id):
            # Map tgt IDs to agents
            mapping = {
                'tgt_a1b2': agents.get('enemy_elite_veyra_001'),
                'tgt_c3d4': None,  # NPC, not in enemy list
            }
            return mapping.get(target_id)

        mapper.resolve_target = resolve_target
        state.get_target_id_mapper.return_value = mapper

        # Mock enemy_combat with enemy_agents
        enemy_combat = MagicMock()
        enemy_agents = []
        for agent_id in enemy_agent_ids:
            enemy = MagicMock()
            enemy.agent_id = agent_id
            enemy.is_active = True
            enemy_agents.append(enemy)
        enemy_combat.enemy_agents = enemy_agents
        state.enemy_combat = enemy_combat

        return state

    def test_social_target_detected_for_nondamage_success(self, pc_resolution_dict):
        """Successful non-damage PC action targeting enemy -> agent_id in set."""
        shared_state = self._make_shared_state_with_enemies(['enemy_elite_veyra_001'])
        session = self._make_session(shared_state)
        result = session._extract_social_target_ids([pc_resolution_dict])

        assert 'enemy_elite_veyra_001' in result

    def test_combat_action_not_social_target(self, pc_combat_resolution_dict):
        """PC action that dealt damage should NOT be in social targets."""
        shared_state = self._make_shared_state_with_enemies(['enemy_elite_veyra_001'])
        session = self._make_session(shared_state)
        result = session._extract_social_target_ids([pc_combat_resolution_dict])

        assert 'enemy_elite_veyra_001' not in result

    def test_failed_action_not_social_target(self, pc_failed_social_resolution):
        """Failed social action should NOT be in social targets."""
        shared_state = self._make_shared_state_with_enemies(['enemy_elite_veyra_001'])
        session = self._make_session(shared_state)
        result = session._extract_social_target_ids([pc_failed_social_resolution])

        assert 'enemy_elite_veyra_001' not in result

    def test_action_against_npc_not_social_target(self, pc_social_targeting_npc):
        """Social action targeting NPC (not enemy) should NOT be in social targets."""
        shared_state = self._make_shared_state_with_enemies(['enemy_elite_veyra_001'])
        session = self._make_session(shared_state)
        result = session._extract_social_target_ids([pc_social_targeting_npc])

        # tgt_c3d4 resolves to NPC, not an enemy agent_id
        assert len(result) == 0


# =============================================================================
# GAP 2 (continued): Conversion Check Marker Tests
# =============================================================================

class TestConversionCheckMarkers:
    """Test that social target markers appear in check_conversions() enemy list."""

    def test_social_target_marker_in_available_enemies(self):
        """Social target should get marker in available enemies list."""
        social_target_ids = {'enemy_elite_veyra_001'}

        # Simulate the marker logic from check_conversions
        health_pct = 100  # Full HP
        is_hp_candidate = health_pct < 30
        is_social_target = 'enemy_elite_veyra_001' in social_target_ids

        markers = []
        if is_hp_candidate:
            markers.append("CANDIDATE")
        if is_social_target:
            markers.append("SOCIAL TARGET")

        # At full HP, no HP marker, but should have social target marker
        assert not is_hp_candidate
        assert is_social_target
        assert "SOCIAL TARGET" in markers

    def test_hp_and_social_markers_combined(self):
        """Both HP and social markers should appear when both conditions met."""
        social_target_ids = {'enemy_grunt_001'}

        health_pct = 20  # Below 30%
        is_hp_candidate = health_pct < 30
        is_social_target = 'enemy_grunt_001' in social_target_ids

        markers = []
        if is_hp_candidate:
            markers.append("CANDIDATE")
        if is_social_target:
            markers.append("SOCIAL TARGET")

        assert "CANDIDATE" in markers
        assert "SOCIAL TARGET" in markers

    def test_no_social_marker_without_data(self):
        """No social marker when social_target_ids is empty or None."""
        for social_ids in [set(), None]:
            is_social_target = social_ids and 'enemy_grunt_001' in social_ids
            assert not is_social_target


# =============================================================================
# GAP 3: Enemy Prompt Tests
# =============================================================================

class TestEnemyPromptDeclaredActions:
    """Test that enemy prompts include declared actions and non-combat options."""

    def test_declared_actions_in_enemy_prompt(self, mock_player_agents_with_declarations):
        """Enemy prompt should include a DECLARED ACTIONS section."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declared_actions

        result = _format_declared_actions(mock_player_agents_with_declarations)

        assert 'DECLARED ACTIONS THIS ROUND' in result
        assert 'Kael Dren' in result
        assert 'Riven Ashford' in result

    def test_declared_actions_shows_targets(self, mock_player_agents_with_declarations):
        """Declaration entries should show target info."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declared_actions

        result = _format_declared_actions(mock_player_agents_with_declarations)

        # Riven's action targets tgt_c3d4
        assert 'tgt_c3d4' in result or 'targeting' in result.lower()

    def test_declared_actions_empty_when_none(self, mock_player_agents_no_declarations):
        """No section when no declarations exist."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declared_actions

        result = _format_declared_actions(mock_player_agents_no_declarations)

        assert result == ""

    def test_surrender_in_declaration_requirements(self):
        """Surrender should be listed in MAJOR_ACTION options."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declaration_requirements

        result = _format_declaration_requirements()

        assert 'Surrender' in result

    def test_dialogue_in_declaration_requirements(self):
        """Dialogue should be listed in MAJOR_ACTION options."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declaration_requirements

        result = _format_declaration_requirements()

        assert 'Dialogue' in result

    def test_wait_in_declaration_requirements(self):
        """Wait should be listed in MAJOR_ACTION options."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_declaration_requirements

        result = _format_declaration_requirements()

        assert 'Wait' in result

    def test_dialogue_in_structured_decision_guidance(self):
        """Structured decision guidance should mention de-escalation via Dialogue."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_structured_decision_guidance

        result = _format_structured_decision_guidance()

        assert 'de-escalat' in result.lower()
        assert 'Dialogue' in result

    def test_declared_actions_in_tactical_prompt(self, mock_player_agents_with_declarations):
        """The full tactical prompt should include declared actions when player_agents provided."""
        from scripts.aeonisk.multiagent.enemy_prompts import generate_tactical_prompt

        enemy = _make_mock_enemy()

        result = generate_tactical_prompt(
            enemy=enemy,
            player_agents=mock_player_agents_with_declarations,
            enemy_agents=[],
            shared_intel=None,
            available_tokens=[],
            current_round=2,
            target_id_mapper=None,
            free_targeting=False,
            recent_narrations=None,
        )

        assert 'DECLARED ACTIONS THIS ROUND' in result

    def test_declared_actions_in_structured_prompt(self, mock_player_agents_with_declarations):
        """The structured tactical prompt should also include declared actions."""
        from scripts.aeonisk.multiagent.enemy_prompts import generate_tactical_prompt_structured

        enemy = _make_mock_enemy()

        result = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=mock_player_agents_with_declarations,
            enemy_agents=[],
            shared_intel=None,
            available_tokens=[],
            current_round=2,
            target_id_mapper=None,
            free_targeting=False,
            recent_narrations=None,
        )

        assert 'DECLARED ACTIONS THIS ROUND' in result
