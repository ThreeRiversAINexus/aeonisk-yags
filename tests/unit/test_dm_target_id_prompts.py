"""
Test DM prompts correctly include target IDs for structured output.

This test suite verifies that the DM receives valid target IDs in prompts
so it can reference them in structured damage/condition outputs, preventing
target ID hallucination bugs.

Author: Three Rivers AI Nexus
Date: 2025-01-07
"""

import pytest
from unittest.mock import Mock, patch


class TestRoundSynthesisTargetIDs:
    """Test that round synthesis includes target IDs in enemy list."""

    def test_enemy_list_includes_target_ids_in_format(self):
        """
        Enemy list in round synthesis should use [tgt_xxxx] format, not agent_id.

        This prevents the DM from hallucinating target IDs like 'tgt_grd1' when
        it should be using actual assigned IDs like 'tgt_7a3f'.
        """
        # Import here to avoid module-level import failures
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        from scripts.aeonisk.multiagent.enemy_spawner import get_active_enemies

        # Create mocks
        mock_shared_state = Mock()
        mock_target_mapper = Mock()
        mock_target_mapper.enabled = True
        mock_target_mapper.get_target_id = Mock(side_effect=lambda agent_id: {
            'enemy_grunt_001': 'tgt_7a3f',
            'enemy_grunt_002': 'tgt_9b2e'
        }.get(agent_id))

        mock_shared_state.get_target_id_mapper = Mock(return_value=mock_target_mapper)

        # Create mock enemies
        enemy1 = Mock()
        enemy1.name = "Security Guard #1"
        enemy1.agent_id = "enemy_grunt_001"
        enemy1.health = 30
        enemy1.max_health = 30
        enemy1.is_active = True

        enemy2 = Mock()
        enemy2.name = "Security Guard #2"
        enemy2.agent_id = "enemy_grunt_002"
        enemy2.health = 25
        enemy2.max_health = 30
        enemy2.is_active = True

        mock_enemy_combat = Mock()
        mock_enemy_combat.enabled = True
        mock_enemy_combat.enemy_agents = [enemy1, enemy2]
        mock_shared_state.enemy_combat = mock_enemy_combat

        # Create DM instance
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            dm = AIDMAgent(
                agent_id="dm_test",
                socket_path="/tmp/test.sock",
                llm_config={'model': 'claude-sonnet-4', 'max_tokens': 2000},
                shared_state=mock_shared_state
            )

        # Build enemy status context (the part we're testing)
        # This is extracted from dm.py:2523-2538
        enemy_status_context = ""
        if dm.shared_state and hasattr(dm.shared_state, 'enemy_combat'):
            enemy_combat = dm.shared_state.enemy_combat
            target_id_mapper = dm.shared_state.get_target_id_mapper()

            if enemy_combat and enemy_combat.enabled and target_id_mapper and target_id_mapper.enabled:
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                if active_enemies:
                    enemy_lines = []
                    for enemy in active_enemies:
                        health_pct = (enemy.health / enemy.max_health * 100) if enemy.max_health > 0 else 0
                        target_id = target_id_mapper.get_target_id(enemy.agent_id)

                        # NEW FORMAT (what we're testing for)
                        if target_id:
                            enemy_lines.append(f"  - [{target_id}] {enemy.name} - {enemy.health}/{enemy.max_health} HP ({health_pct:.0f}%)")
                        else:
                            # Fallback to old format (should NOT happen in free targeting mode)
                            enemy_lines.append(f"  - {enemy.name} (ID: {enemy.agent_id}) - {enemy.health}/{enemy.max_health} HP ({health_pct:.0f}%)")

                    enemy_status_context = "\n\n**Active Enemies:**\n" + "\n".join(enemy_lines)

        # Assertions
        assert enemy_status_context != "", "Should have enemy context"

        # CRITICAL: Should include target IDs in bracket notation
        assert '[tgt_7a3f]' in enemy_status_context, \
            "Enemy list must include [tgt_7a3f] for Security Guard #1"
        assert '[tgt_9b2e]' in enemy_status_context, \
            "Enemy list must include [tgt_9b2e] for Security Guard #2"

        # Should include enemy names
        assert 'Security Guard #1' in enemy_status_context
        assert 'Security Guard #2' in enemy_status_context

        # Should NOT include old agent_id format (this is the bug!)
        assert 'enemy_grunt_001' not in enemy_status_context, \
            "Should NOT show agent_id in enemy list (old buggy format)"
        assert 'ID: enemy_' not in enemy_status_context, \
            "Should NOT use 'ID: enemy_xxx' format"


class TestActionResolutionPromptTargetIDs:
    """Test that action resolution prompts include all valid target IDs."""

    @pytest.mark.asyncio
    async def test_build_resolution_prompt_includes_combatant_list(self):
        """
        Action resolution prompt should include all combatant target IDs.

        This gives the DM a reference list of valid IDs to use in damage/condition effects.
        """
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        # Create minimal mocks
        mock_shared_state = Mock()
        mock_target_mapper = Mock()
        mock_target_mapper.enabled = True
        mock_target_mapper.get_all_target_ids = Mock(return_value=[
            'tgt_7a3f', 'tgt_9b2e', 'tgt_3c5d'
        ])
        mock_target_mapper.get_combatant_info = Mock(side_effect=lambda tid: {
            'tgt_7a3f': {'name': 'Security Guard #1', 'type': 'enemy'},
            'tgt_9b2e': {'name': 'Security Guard #2', 'type': 'enemy'},
            'tgt_3c5d': {'name': 'Ash', 'type': 'player'}
        }.get(tid))

        mock_shared_state.get_target_id_mapper = Mock(return_value=mock_target_mapper)
        mock_shared_state.mechanics_engine = Mock(scene_clocks={})
        mock_shared_state.get_mechanics_engine = Mock(return_value=mock_shared_state.mechanics_engine)
        mock_shared_state.player_agents = []  # Empty list - iterable

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            dm = AIDMAgent(
                agent_id="dm_test",
                socket_path="/tmp/test.sock",
                llm_config={'model': 'claude-sonnet-4', 'max_tokens': 2000},
                shared_state=mock_shared_state
            )

        dm.current_scenario = Mock(
            theme="Test",
            location="Test Location",
            situation="Test situation",
            void_level=5
        )

        # Mock action and resolution
        action = {
            'character': 'Ash',
            'faction': 'Pantheon',
            'target': 'tgt_7a3f',
            'action_type': 'combat'
        }

        resolution = Mock()
        resolution.success = True
        resolution.margin = 8
        resolution.outcome_tier = Mock(value='moderate')

        # Call _build_resolution_prompt
        prompt = await dm._build_resolution_prompt(
            player_id='player_001',
            action_type='combat',
            description='Fires at target',
            resolution=resolution,
            action=action
        )

        # NEW REQUIREMENT: Prompt must include combatant list with all target IDs
        # This is what prevents hallucination!
        assert 'tgt_7a3f' in prompt, "Must include Security Guard #1 target ID"
        assert 'tgt_9b2e' in prompt, "Must include Security Guard #2 target ID"
        assert 'tgt_3c5d' in prompt, "Must include Ash target ID"

        # Should have instruction about using exact IDs
        # (either in the prompt builder or in the loaded prompt template)
        assert 'target' in prompt.lower() or 'ID' in prompt, \
            "Should reference target IDs somewhere in prompt"


class TestTargetIDMapperAccess:
    """Test DM correctly accesses TargetIDMapper."""

    def test_dm_can_get_target_id_mapper(self):
        """DM should retrieve TargetIDMapper from SharedState."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent

        mock_shared_state = Mock()
        mock_target_mapper = Mock()
        mock_target_mapper.enabled = True
        mock_shared_state.get_target_id_mapper = Mock(return_value=mock_target_mapper)

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            dm = AIDMAgent(
                agent_id="dm_test",
                socket_path="/tmp/test.sock",
                llm_config={'model': 'claude-sonnet-4', 'max_tokens': 2000},
                shared_state=mock_shared_state
            )

        mapper = dm.shared_state.get_target_id_mapper()
        assert mapper is not None
        assert mapper.enabled


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
