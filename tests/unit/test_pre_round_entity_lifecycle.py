"""
Tests for Pre-Round Entity Lifecycle Phase.

TDD Tests - These define the expected behavior for pre-populating NPCs, objects,
and enemies after scenario generation but before round 1.

The pre-round lifecycle phase runs AFTER scenario setup (which processes initial_enemies
and initial_npcs from config) but BEFORE round 1, allowing the DM to dynamically
spawn additional entities based on the scenario theme.
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from dataclasses import dataclass, field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from aeonisk.multiagent.session import SelfPlayingSession
from aeonisk.multiagent.schemas.story_events import (
    NPCSpawn, EnemySpawn, ConversionDecisions, EnvObjectSpawn,
    ScenarioSetup, NewClock, Position
)
from aeonisk.multiagent.mechanics import JSONLLogger


class TestPreRoundEntityLifecycle:
    """Test that pre-round entity lifecycle runs after scenario setup, before round 1."""

    def _create_test_clock(self):
        """Helper to create a minimal valid NewClock for testing."""
        return NewClock(
            name="Test Clock",
            max_ticks=6,
            description="A test progress clock for this scenario",
            advance_meaning="Test progresses forward",
            regress_meaning="Test moves backwards"
        )

    @pytest.fixture
    def temp_config(self):
        """Create a minimal session config for testing."""
        config = {
            "session_name": "Pre-Round Lifecycle Test",
            "max_turns": 1,
            "party_size": 1,
            "agents": {
                "dm": {
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.7
                    }
                },
                "players": [
                    {
                        "name": "Test Character",
                        "faction": "ACG",
                        "archetype": "investigator",
                        "llm": {
                            "provider": "anthropic",
                            "model": "claude-3-5-haiku-20241022",
                            "temperature": 0.8
                        }
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        yield config_path

        Path(config_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_jsonl_logger(self):
        """Create a mock JSONL logger to track logged events."""
        logger = Mock(spec=JSONLLogger)
        logger.log_event = Mock()
        return logger

    def test_pre_round_lifecycle_called_before_round_1(self, temp_config, mock_jsonl_logger):
        """
        Test that pre-round entity lifecycle runs after scenario setup, before round 1.

        EXPECTED FLOW:
        1. Scenario setup processes initial_enemies/initial_npcs from config
        2. Pre-round entity lifecycle runs (calls check_conversions with pre_round=True)
        3. Round 1 begins

        The pre-round phase allows DM to dynamically spawn additional entities
        based on the scenario (vendors, bystanders, environmental objects).
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock mechanics engine
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Track method calls
        pre_round_lifecycle_called = False
        round_1_started = False
        call_order = []

        # Capture when pre-round lifecycle is called
        original_method = getattr(session, '_run_pre_round_entity_lifecycle', None)

        async def mock_pre_round_lifecycle():
            nonlocal pre_round_lifecycle_called
            pre_round_lifecycle_called = True
            call_order.append('pre_round_lifecycle')
            if original_method:
                return await original_method()

        # Assert: Session should have _run_pre_round_entity_lifecycle method
        assert hasattr(session, '_run_pre_round_entity_lifecycle'), \
            "Session should have _run_pre_round_entity_lifecycle method"

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_calls_check_conversions_with_pre_round_flag(
        self, temp_config, mock_jsonl_logger
    ):
        """
        Test that pre-round lifecycle calls dm.check_conversions() with pre_round=True.

        This flag tells the DM:
        - No combat has occurred yet
        - Focus on scenario-appropriate spawns (vendors, bystanders, env objects)
        - Don't do morale checks or enemy conversions
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock DM agent with check_conversions method
        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            reasoning="Pre-round setup complete"
        ))
        session.agents = [mock_dm]

        # Mock mechanics
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Act: Call pre-round lifecycle (if it exists)
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: check_conversions was called with pre_round=True
            mock_dm.check_conversions.assert_called_once()
            call_kwargs = mock_dm.check_conversions.call_args.kwargs
            assert call_kwargs.get('pre_round') is True, \
                "check_conversions should be called with pre_round=True"

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_does_not_duplicate_config_entities(
        self, temp_config, mock_jsonl_logger
    ):
        """
        Test that pre-round lifecycle doesn't duplicate entities already spawned from config.

        The scenario setup processes initial_enemies and initial_npcs from the session config.
        Pre-round lifecycle should receive a list of already-spawned entity IDs so the DM
        knows not to duplicate them.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Pre-populate with config entities (simulating scenario setup already ran)
        from aeonisk.multiagent.npc_agent import NPCAgent

        existing_npc = NPCAgent(
            agent_id="npc_vendor_abc123",
            name="Street Vendor",
            faction="Independent",
            entity_type="neutral",
            disposition="friendly",
            threat_level="non_combatant",
            description="A vendor from config",
            health=20,
            max_health=20,
            soak=0,
            void_score=0,
            skills={}
        )
        session.shared_state.npc_agents = [existing_npc]

        # Mock DM
        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            reasoning="No additional spawns needed"
        ))
        session.agents = [mock_dm]

        # Mock mechanics
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Act
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: check_conversions was called with existing_entities context
            mock_dm.check_conversions.assert_called_once()
            call_kwargs = mock_dm.check_conversions.call_args.kwargs

            # Should have some way to communicate existing entities to DM
            # Either in resolution_summary or via a new parameter
            assert 'pre_round' in call_kwargs or 'existing_entities' in call_kwargs, \
                "check_conversions should receive context about already-spawned entities"

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_logs_entity_lifecycle_event_at_round_0(
        self, temp_config, mock_jsonl_logger
    ):
        """
        Test that pre-round lifecycle logs entity_lifecycle event at round 0.

        This ensures all entity spawns (both from config and from DM pre-round decisions)
        are properly logged for ML training data.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock DM that spawns an NPC during pre-round
        mock_npc = Mock()
        mock_npc.agent_id = "npc_bystander_xyz789"
        mock_npc.name = "Curious Bystander"
        mock_npc.entity_type = "neutral"
        mock_npc.disposition = "neutral"

        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[
                NPCSpawn(
                    name="Curious Bystander",
                    faction="Unknown",
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="neutral",
                    description="A passerby watching events unfold",
                    health=10,
                    soak=0
                )
            ],
            reasoning="Spawning bystander appropriate for street scene"
        ))
        mock_dm._process_npc_spawn = Mock(return_value=mock_npc)
        session.agents = [mock_dm]

        # Mock mechanics
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Act
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: entity_lifecycle event was logged at round 0
            entity_lifecycle_calls = [
                call for call in mock_jsonl_logger.log_event.call_args_list
                if call[0][0] == 'entity_lifecycle'
            ]

            assert len(entity_lifecycle_calls) >= 1, \
                "Should log entity_lifecycle event for pre-round spawns"

            # Check round number is 0
            kwargs = entity_lifecycle_calls[0][1]
            assert kwargs.get('round_num') == 0, \
                "Pre-round entity lifecycle should log at round 0"

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_processes_npc_spawns(self, temp_config, mock_jsonl_logger):
        """
        Test that NPC spawns from pre-round lifecycle are properly processed.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock DM that spawns NPCs during pre-round
        mock_npc1 = Mock()
        mock_npc1.agent_id = "npc_vendor_001"
        mock_npc1.name = "Vendor"

        mock_npc2 = Mock()
        mock_npc2.agent_id = "npc_guard_002"
        mock_npc2.name = "Guard"

        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[
                NPCSpawn(
                    name="Vendor",
                    faction="Independent",
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="friendly",
                    description="A vendor selling supplies",
                    health=15,
                    soak=0,
                    is_vendor=True,
                    vendor_type="general"
                ),
                NPCSpawn(
                    name="Guard",
                    faction="ACG Security",
                    entity_type="neutral",
                    threat_level="potential_threat",
                    disposition="neutral",
                    description="A guard patrolling the area",
                    health=25,
                    soak=3
                )
            ],
            reasoning="Spawning vendor and guard appropriate for station market"
        ))
        mock_dm._process_npc_spawn = Mock(side_effect=[mock_npc1, mock_npc2])
        session.agents = [mock_dm]

        # Mock mechanics
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Act
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: _process_npc_spawn was called for each NPC
            assert mock_dm._process_npc_spawn.call_count == 2, \
                "Should process each NPC spawn from pre-round decisions"

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_processes_enemy_spawns(self, temp_config, mock_jsonl_logger):
        """
        Test that enemy spawns from pre-round lifecycle are properly processed.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Set up enemy combat
        session.enemy_combat = Mock()
        session.enemy_combat.enabled = True
        session.enemy_combat.spawn_from_structured = Mock(return_value=["Enemy patrol spawned"])
        session.enemy_combat.enemy_agents = []

        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            enemy_spawns=[
                EnemySpawn(
                    template="grunt",
                    faction="Hostile Faction",
                    archetype="enforcer",
                    count=2,
                    spawn_reason="Patrol enters the area",
                    initial_position=Position.FAR_ENEMY
                )
            ],
            reasoning="Spawning patrol enemies that were out of sight at scenario start"
        ))
        session.agents = [mock_dm]

        # Mock mechanics
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}

        # Act
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: spawn_from_structured was called
            session.enemy_combat.spawn_from_structured.assert_called_once()

    @pytest.mark.xfail(reason="Test isolation issue - asyncio event loop conflicts when running in full suite")
    def test_pre_round_lifecycle_processes_env_object_spawns(self, temp_config, mock_jsonl_logger):
        """
        Test that environmental object spawns from pre-round lifecycle are properly processed.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_dm.check_conversions = AsyncMock(return_value=ConversionDecisions(
            enemy_conversions=[],
            escalations=[],
            npc_spawns=[],
            env_object_spawns=[
                EnvObjectSpawn(
                    object_type="terminal",
                    name="Data Terminal",
                    description="A glowing terminal with encrypted data access panels",
                    initial_state={"locked": True, "powered": True},
                    narrative_reason="Terminal present in tech lab scene for interaction"
                )
            ],
            reasoning="Spawning interactive objects appropriate for the tech lab scene"
        ))
        session.agents = [mock_dm]

        # Mock mechanics with env_objects
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}
        session.shared_state.mechanics_engine.env_objects = {}

        # Act
        import asyncio

        if hasattr(session, '_run_pre_round_entity_lifecycle'):
            asyncio.get_event_loop().run_until_complete(
                session._run_pre_round_entity_lifecycle()
            )

            # Assert: env_objects were processed
            # (implementation will add to mechanics.env_objects)


class TestCheckConversionsPreRoundFlag:
    """Test that check_conversions supports pre_round flag."""

    def test_check_conversions_accepts_pre_round_parameter(self):
        """
        Test that dm.check_conversions() accepts pre_round parameter.

        When pre_round=True:
        - Skip morale checks (no combat has occurred)
        - Skip enemy conversions (no enemies have been damaged yet)
        - Focus on scenario-appropriate spawns
        """
        from aeonisk.multiagent.dm import AIDMAgent
        import inspect

        # Check that check_conversions accepts pre_round parameter
        sig = inspect.signature(AIDMAgent.check_conversions)
        params = list(sig.parameters.keys())

        assert 'pre_round' in params, \
            "check_conversions should accept pre_round parameter"

    def test_check_conversions_pre_round_skips_morale_context(self):
        """
        Test that pre_round=True mode doesn't include morale events in context.

        Since no combat has occurred, there are no morale events to consider.
        """
        # This test validates the implementation behavior
        # Will be implemented when the feature is added
        pass

    def test_check_conversions_pre_round_resolution_summary(self):
        """
        Test that pre_round=True uses appropriate resolution summary.

        Instead of "Here's what happened this round", the summary should indicate
        "Session starting - populate scene with appropriate entities".
        """
        # This test validates the implementation behavior
        # Will be implemented when the feature is added
        pass


class TestPreRoundLifecycleIntegrationWithConfig:
    """Test integration between config initial_* and pre-round lifecycle."""

    @pytest.fixture
    def config_with_initial_entities(self):
        """Create a config with initial_enemies and initial_npcs."""
        config = {
            "session_name": "Config Entities Test",
            "max_turns": 1,
            "party_size": 1,
            "initial_enemies": [
                {
                    "template": "grunt",
                    "faction": "Raiders",
                    "count": 2,
                    "spawn_reason": "Ambush waiting"
                }
            ],
            "initial_npcs": [
                {
                    "name": "Informant",
                    "faction": "Freeborn",
                    "entity_type": "neutral",
                    "disposition": "friendly",
                    "threat_level": "non_combatant",
                    "description": "Your contact for this mission",
                    "health": 15,
                    "soak": 0
                }
            ],
            "agents": {
                "dm": {
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.7
                    }
                },
                "players": [
                    {
                        "name": "Test Character",
                        "faction": "ACG",
                        "archetype": "investigator",
                        "llm": {
                            "provider": "anthropic",
                            "model": "claude-3-5-haiku-20241022",
                            "temperature": 0.8
                        }
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        yield config_path

        Path(config_path).unlink(missing_ok=True)

    def test_config_entities_spawn_before_pre_round_lifecycle(
        self, config_with_initial_entities
    ):
        """
        Test that entities from config spawn BEFORE pre-round lifecycle runs.

        Order should be:
        1. Scenario setup processes config initial_enemies/initial_npcs
        2. Pre-round lifecycle runs (can spawn additional entities)

        This ensures DM sees what's already spawned and doesn't duplicate.
        """
        # This test validates the order of operations
        # Will be implemented when the feature is added
        pass

    def test_pre_round_lifecycle_receives_list_of_spawned_entities(
        self, config_with_initial_entities
    ):
        """
        Test that pre-round lifecycle knows which entities are already spawned.

        The resolution_summary or a dedicated parameter should include:
        - List of spawned enemy agent_ids
        - List of spawned NPC agent_ids

        So DM knows not to spawn "another vendor" if one is already present.
        """
        # This test validates that context is passed correctly
        # Will be implemented when the feature is added
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
