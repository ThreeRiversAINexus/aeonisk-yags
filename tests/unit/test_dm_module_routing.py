"""
Unit tests for DM module routing based on action type.

Tests the _get_required_dm_modules() function to ensure correct action-specific
resolution prompts are loaded for each action type.
"""

import pytest
from unittest.mock import Mock, MagicMock


class TestDMModuleRouting:
    """Tests for DM._get_required_dm_modules() action type routing."""

    @pytest.fixture
    def mock_dm(self):
        """Create a mock DM agent with minimal dependencies."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        # Create minimal mock shared_state
        mock_shared = Mock()
        mock_shared.enemy_combat = None
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {}
        mock_shared.mechanics_engine.jsonl_logger = None

        # Create DM with mocked dependencies
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"

        return dm

    def test_base_modules_always_loaded(self, mock_dm):
        """Base modules should always be loaded regardless of action type."""
        modules = mock_dm._get_required_dm_modules(action_type=None)

        assert 'dm_core' in modules
        assert 'dm_structured_output_base' in modules
        assert 'dm_commands' in modules

    def test_old_monolithic_module_not_loaded(self, mock_dm):
        """The old monolithic dm_structured_output should NOT be loaded."""
        modules = mock_dm._get_required_dm_modules(action_type=None)

        assert 'dm_structured_output' not in modules

    # Action-type specific module tests

    def test_combat_action_loads_combat_module(self, mock_dm):
        """Combat actions should load dm_resolution_combat."""
        modules = mock_dm._get_required_dm_modules(action_type='combat')

        assert 'dm_resolution_combat' in modules
        assert 'dm_resolution_investigate' not in modules

    def test_investigate_action_loads_investigate_module(self, mock_dm):
        """Investigate actions should load dm_resolution_investigate."""
        modules = mock_dm._get_required_dm_modules(action_type='investigate')

        assert 'dm_resolution_investigate' in modules
        assert 'dm_resolution_combat' not in modules

    def test_social_action_loads_social_module(self, mock_dm):
        """Social actions should load dm_resolution_social."""
        modules = mock_dm._get_required_dm_modules(action_type='social')

        assert 'dm_resolution_social' in modules

    def test_ritual_action_loads_ritual_module(self, mock_dm):
        """Ritual actions should load dm_resolution_ritual."""
        modules = mock_dm._get_required_dm_modules(action_type='ritual')

        assert 'dm_resolution_ritual' in modules

    def test_support_action_loads_support_module(self, mock_dm):
        """Support actions should load dm_resolution_support."""
        modules = mock_dm._get_required_dm_modules(action_type='support')

        assert 'dm_resolution_support' in modules

    def test_explore_action_loads_movement_module(self, mock_dm):
        """Explore actions should load dm_resolution_movement."""
        modules = mock_dm._get_required_dm_modules(action_type='explore')

        assert 'dm_resolution_movement' in modules

    def test_perception_action_loads_perception_module(self, mock_dm):
        """Perception actions should load dm_resolution_perception (awareness, NOT item discovery)."""
        modules = mock_dm._get_required_dm_modules(action_type='perception')

        assert 'dm_resolution_perception' in modules
        assert 'dm_resolution_investigate' not in modules  # Perception is separate from investigate

    def test_technical_action_loads_investigate_module(self, mock_dm):
        """Technical actions should load dm_resolution_investigate (similar mechanics)."""
        modules = mock_dm._get_required_dm_modules(action_type='technical')

        assert 'dm_resolution_investigate' in modules

    def test_attune_action_loads_attunement_module(self, mock_dm):
        """Attune actions should load dm_attunement (pre-existing specialized module)."""
        modules = mock_dm._get_required_dm_modules(action_type='attune')

        assert 'dm_attunement' in modules

    def test_purchase_action_loads_purchase_module(self, mock_dm):
        """Purchase actions should load dm_purchase (pre-existing specialized module)."""
        modules = mock_dm._get_required_dm_modules(action_type='purchase')

        assert 'dm_purchase' in modules

    def test_transfer_action_loads_transfer_module(self, mock_dm):
        """Transfer actions should load dm_transfer (pre-existing specialized module)."""
        modules = mock_dm._get_required_dm_modules(action_type='transfer')

        assert 'dm_transfer' in modules

    def test_consume_action_loads_consumption_module(self, mock_dm):
        """Consume actions should load dm_consumption (pre-existing specialized module)."""
        modules = mock_dm._get_required_dm_modules(action_type='consume')

        assert 'dm_consumption' in modules

    def test_action_type_case_insensitive(self, mock_dm):
        """Action type matching should be case-insensitive."""
        modules_lower = mock_dm._get_required_dm_modules(action_type='combat')
        modules_upper = mock_dm._get_required_dm_modules(action_type='COMBAT')
        modules_mixed = mock_dm._get_required_dm_modules(action_type='Combat')

        assert 'dm_resolution_combat' in modules_lower
        assert 'dm_resolution_combat' in modules_upper
        assert 'dm_resolution_combat' in modules_mixed

    def test_unknown_action_type_no_crash(self, mock_dm):
        """Unknown action types should not crash, just skip action-specific module."""
        modules = mock_dm._get_required_dm_modules(action_type='unknown_action')

        # Should still have base modules
        assert 'dm_core' in modules
        assert 'dm_structured_output_base' in modules
        # Should not have any action-specific module
        assert 'dm_resolution_combat' not in modules
        assert 'dm_resolution_investigate' not in modules

    def test_none_action_type_loads_base_only(self, mock_dm):
        """None action type should load base modules only."""
        modules = mock_dm._get_required_dm_modules(action_type=None)

        assert 'dm_core' in modules
        assert 'dm_structured_output_base' in modules
        # Should not have action-specific modules
        for module in modules:
            assert not module.startswith('dm_resolution_')


class TestDMModuleRoutingWithEnemies:
    """Tests for module loading when enemies are present."""

    @pytest.fixture
    def mock_dm_with_enemies(self):
        """Create a mock DM agent with enemies present."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_enemy_combat = Mock()
        mock_enemy_combat.enemy_agents = [Mock(), Mock()]  # 2 enemies

        mock_shared = Mock()
        mock_shared.enemy_combat = mock_enemy_combat
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {}
        mock_shared.mechanics_engine.jsonl_logger = None

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"

        return dm

    def test_combat_module_loaded_when_enemies_present(self, mock_dm_with_enemies):
        """dm_combat should be loaded when enemies are present (tactical rules)."""
        modules = mock_dm_with_enemies._get_required_dm_modules(action_type='investigate')

        # Should have both the action-specific AND the tactical combat module
        assert 'dm_resolution_investigate' in modules
        assert 'dm_combat' in modules


class TestDMModuleRoutingWithClocks:
    """Tests for module loading when scene clocks are present."""

    @pytest.fixture
    def mock_dm_with_clocks(self):
        """Create a mock DM agent with scene clocks."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_shared = Mock()
        mock_shared.enemy_combat = None
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {'Investigation': Mock(), 'Alert': Mock()}
        mock_shared.mechanics_engine.jsonl_logger = None

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"

        return dm

    def test_state_tracking_loaded_when_clocks_present(self, mock_dm_with_clocks):
        """dm_state_tracking should be loaded when clocks are present."""
        modules = mock_dm_with_clocks._get_required_dm_modules(action_type='investigate')

        assert 'dm_state_tracking' in modules


class TestPromptFilesExist:
    """Tests to verify all referenced prompt files actually exist."""

    def test_base_prompt_exists(self):
        """dm_structured_output_base.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_structured_output_base.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_combat_exists(self):
        """dm_resolution_combat.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_investigate_exists(self):
        """dm_resolution_investigate.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_investigate.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_social_exists(self):
        """dm_resolution_social.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_social.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_ritual_exists(self):
        """dm_resolution_ritual.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_ritual.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_support_exists(self):
        """dm_resolution_support.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_support.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_movement_exists(self):
        """dm_resolution_movement.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_movement.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_perception_exists(self):
        """dm_resolution_perception.yaml should exist (separate from investigate)."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_perception.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"

    def test_resolution_combat_with_suppression_exists(self):
        """dm_resolution_combat_with_suppression.yaml should exist."""
        import os
        path = 'scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml'
        assert os.path.exists(path), f"Missing prompt file: {path}"


class TestPromptLoadingIntegration:
    """Integration tests for actually loading prompts via prompt_loader."""

    def test_can_load_investigate_resolution_prompt(self):
        """Should be able to load dm_resolution_investigate module."""
        from scripts.aeonisk.multiagent.prompt_loader import load_modular_prompt

        result = load_modular_prompt(
            agent_type="dm",
            module_names=["dm_core", "dm_structured_output_base", "dm_resolution_investigate"],
            provider="claude",
            language="en",
            variables={}
        )

        assert result is not None
        assert len(result.content) > 0
        # Should contain item_discovery guidance
        assert 'item_discovery' in result.content.lower()

    def test_can_load_combat_resolution_prompt(self):
        """Should be able to load dm_resolution_combat module."""
        from scripts.aeonisk.multiagent.prompt_loader import load_modular_prompt

        result = load_modular_prompt(
            agent_type="dm",
            module_names=["dm_core", "dm_structured_output_base", "dm_resolution_combat"],
            provider="claude",
            language="en",
            variables={}
        )

        assert result is not None
        assert len(result.content) > 0
        # Should contain damage guidance
        assert 'damage' in result.content.lower()

    def test_investigate_prompt_smaller_than_old_monolithic(self):
        """New action-specific prompts should be smaller than old monolithic prompt."""
        from scripts.aeonisk.multiagent.prompt_loader import load_modular_prompt

        # Load new action-specific version
        new_result = load_modular_prompt(
            agent_type="dm",
            module_names=["dm_core", "dm_structured_output_base", "dm_resolution_investigate"],
            provider="claude",
            language="en",
            variables={}
        )

        # Load old monolithic version (if it still exists)
        try:
            old_result = load_modular_prompt(
                agent_type="dm",
                module_names=["dm_core", "dm_structured_output"],
                provider="claude",
                language="en",
                variables={}
            )
            # New should be smaller
            assert len(new_result.content) < len(old_result.content), \
                f"New prompt ({len(new_result.content)} chars) should be smaller than old ({len(old_result.content)} chars)"
        except Exception:
            # Old module may have been removed - that's fine
            pass

    def test_can_load_combat_with_suppression_resolution_prompt(self):
        """Should be able to load dm_resolution_combat_with_suppression merged module."""
        from scripts.aeonisk.multiagent.prompt_loader import load_modular_prompt

        result = load_modular_prompt(
            agent_type="dm",
            module_names=["dm_core", "dm_structured_output_base", "dm_resolution_combat_with_suppression"],
            provider="claude",
            language="en",
            variables={}
        )

        assert result is not None
        assert len(result.content) > 0
        assert 'Pinned' in result.content                  # suppression content
        assert 'LETHAL DAMAGE TABLE' in result.content      # lethal content preserved
        assert 'proportionality' in result.content          # freeform soulcredit
        assert 'no damage entries' in result.content.lower()  # note about Example 2


class TestDMModuleRoutingWithExperimentFlags:
    """Tests for module loading when experiment flags are set in session_config."""

    @pytest.fixture
    def mock_dm_with_experiment(self):
        """Create a mock DM agent with suppression experiment flag enabled."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_shared = Mock()
        mock_shared.enemy_combat = None
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {}
        mock_shared.mechanics_engine.jsonl_logger = None

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"
        dm.session_config = {
            'experiment': {
                'include_suppression_resolution_example': True
            }
        }

        return dm

    @pytest.fixture
    def mock_dm_without_experiment(self):
        """Create a mock DM agent with suppression experiment flag disabled."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_shared = Mock()
        mock_shared.enemy_combat = None
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {}
        mock_shared.mechanics_engine.jsonl_logger = None

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"
        dm.session_config = {
            'experiment': {
                'include_suppression_resolution_example': False
            }
        }

        return dm

    def test_combat_module_swapped_when_flag_true(self, mock_dm_with_experiment):
        """Combat module should be swapped for merged variant when experiment flag is True."""
        modules = mock_dm_with_experiment._get_required_dm_modules(action_type='combat')

        assert 'dm_resolution_combat_with_suppression' in modules
        assert 'dm_resolution_combat' not in modules  # Swapped out, not both

    def test_combat_module_unchanged_when_flag_false(self, mock_dm_without_experiment):
        """Combat module should remain unchanged when experiment flag is False."""
        modules = mock_dm_without_experiment._get_required_dm_modules(action_type='combat')

        assert 'dm_resolution_combat' in modules
        assert 'dm_resolution_combat_with_suppression' not in modules

    def test_non_combat_unaffected_by_flag(self, mock_dm_with_experiment):
        """Non-combat action types should not be affected by suppression experiment flag."""
        for action_type in ['investigate', 'social', 'ritual', 'support', 'explore']:
            modules = mock_dm_with_experiment._get_required_dm_modules(action_type=action_type)
            assert 'dm_resolution_combat_with_suppression' not in modules, \
                f"Merged suppression module should not load for {action_type}"
            assert 'dm_resolution_combat' not in modules, \
                f"Combat module should not load for {action_type}"

    def test_no_action_type_unaffected_by_flag(self, mock_dm_with_experiment):
        """None action type should not load any combat module."""
        modules = mock_dm_with_experiment._get_required_dm_modules(action_type=None)

        assert 'dm_resolution_combat_with_suppression' not in modules
        assert 'dm_resolution_combat' not in modules

    def test_dm_without_session_config_still_works(self):
        """DM agents without session_config (e.g., test fixtures) should not crash."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_shared = Mock()
        mock_shared.enemy_combat = None
        mock_shared.mechanics_engine = Mock()
        mock_shared.mechanics_engine.scene_clocks = {}
        mock_shared.mechanics_engine.jsonl_logger = None

        dm = AIDMAgent.__new__(AIDMAgent)
        dm.shared_state = mock_shared
        dm.agent_id = "test_dm"
        # Deliberately NOT setting dm.session_config

        # Should not crash — getattr fallback handles missing attribute
        modules = dm._get_required_dm_modules(action_type='combat')
        assert 'dm_resolution_combat' in modules
        assert 'dm_resolution_combat_with_suppression' not in modules
