"""
Test that session start NPCs are properly tracked via entity_lifecycle events.

TDD Tests - These tests SHOULD FAIL initially until the fix is implemented.
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import session and related classes
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from aeonisk.multiagent.session import SelfPlayingSession
from aeonisk.multiagent.schemas.story_events import NPCSpawn, ScenarioSetup
from aeonisk.multiagent.mechanics import JSONLLogger


class TestSessionStartNPCLifecycleLogging:
    """Test that initial NPCs from scenario setup are tracked in entity_lifecycle events."""

    def _create_test_clock(self):
        """Helper to create a minimal valid NewClock for testing."""
        from aeonisk.multiagent.schemas.story_events import NewClock
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
            "session_name": "NPC Lifecycle Test",
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

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        yield config_path

        # Cleanup
        Path(config_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_jsonl_logger(self):
        """Create a mock JSONL logger to track logged events."""
        logger = Mock(spec=JSONLLogger)
        logger.log_event = Mock()
        logger.call_count = 0
        return logger

    def test_session_start_npcs_generate_entity_lifecycle_event(self, temp_config, mock_jsonl_logger):
        """
        Test that NPCs spawned at session start generate an entity_lifecycle event.

        EXPECTED BEHAVIOR:
        - When ScenarioSetup contains initial_npcs
        - Session processes these NPCs during _handle_scenario_setup()
        - An entity_lifecycle event is logged with npcs_spawned populated

        CURRENT BUG:
        - NPCs are spawned but NO entity_lifecycle event is generated
        - Only mid-session NPC spawns (from conversion check) generate events
        """
        # Arrange: Create session
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock the mechanics jsonl_logger (note: mechanics_engine not _mechanics_engine)
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}  # Empty dict for clock iteration

        # Create initial NPCs via ScenarioSetup
        initial_npcs = [
            NPCSpawn(
                name="Test NPC 1",
                faction="Freeborn",
                disposition="friendly",
                entity_type="neutral",
                threat_level="non_combatant",
                health=10,
                soak=0,
                skills={},
                description="A test NPC character for lifecycle testing"
            ),
            NPCSpawn(
                name="Test NPC 2",
                faction="ACG",
                disposition="neutral",
                entity_type="ally",
                threat_level="potential_threat",
                health=15,
                soak=2,
                skills={"Bureaucracy": 6},
                description="Another test NPC for lifecycle testing"
            )
        ]

        scenario_setup = ScenarioSetup(
            theme="Test Scenario for NPC Lifecycle Logging",
            location="Test Location",
            situation="Testing NPC lifecycle logging functionality to ensure session start NPCs generate entity_lifecycle events properly",
            starting_clocks=[self._create_test_clock()],
            success_conditions="Complete the test successfully",
            failure_consequences="Test fails and validation does not work properly",
            initial_enemies=[],
            initial_npcs=initial_npcs
        )

        # Mock DM agent with _process_npc_spawn method
        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_npc_1 = Mock()
        mock_npc_1.agent_id = "npc_abc123"
        mock_npc_1.name = "Test NPC 1"
        mock_npc_1.entity_type = "civilian"
        mock_npc_1.disposition = "friendly"

        mock_npc_2 = Mock()
        mock_npc_2.agent_id = "npc_def456"
        mock_npc_2.name = "Test NPC 2"
        mock_npc_2.entity_type = "official"
        mock_npc_2.disposition = "neutral"

        mock_dm._process_npc_spawn = Mock(side_effect=[mock_npc_1, mock_npc_2])
        session.agents = [mock_dm]

        # Act: Process scenario setup (this triggers NPC spawning)
        from aeonisk.multiagent.base import Message, MessageType
        import uuid
        from datetime import datetime

        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.SCENARIO_SETUP,
            sender='dm_test',
            recipient=None,
            payload={'scenario_setup': scenario_setup},
            timestamp=datetime.now()
        )

        session._handle_scenario_setup(message)

        # Assert: entity_lifecycle event was logged
        # Find the entity_lifecycle log_event call
        entity_lifecycle_calls = [
            call for call in mock_jsonl_logger.log_event.call_args_list
            if call[0][0] == 'entity_lifecycle'
        ]

        assert len(entity_lifecycle_calls) == 1, \
            "Expected exactly 1 entity_lifecycle event to be logged for session start NPCs"

        # Extract the logged data
        event_type, event_data, *_ = entity_lifecycle_calls[0][0]

        # Verify npcs_spawned contains both NPC agent_ids
        assert 'npcs_spawned' in event_data, \
            "entity_lifecycle event should have npcs_spawned field"

        npcs_spawned = event_data['npcs_spawned']
        assert len(npcs_spawned) == 2, \
            f"Expected 2 NPCs in npcs_spawned, got {len(npcs_spawned)}"

        assert mock_npc_1.agent_id in npcs_spawned, \
            f"NPC 1 ({mock_npc_1.agent_id}) should be in npcs_spawned"

        assert mock_npc_2.agent_id in npcs_spawned, \
            f"NPC 2 ({mock_npc_2.agent_id}) should be in npcs_spawned"

    def test_no_entity_lifecycle_event_when_no_npcs(self, temp_config, mock_jsonl_logger):
        """
        Test that NO entity_lifecycle event is logged when there are no initial NPCs.

        This ensures we're not logging empty events.
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock the mechanics jsonl_logger (note: mechanics_engine not _mechanics_engine)
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}  # Empty dict for clock iteration

        # Create scenario with NO initial NPCs
        scenario_setup = ScenarioSetup(
            theme="Test Scenario with No NPCs",
            location="Test Location",
            situation="Testing empty NPC lifecycle to ensure no entity_lifecycle events are logged when there are no NPCs to spawn",
            starting_clocks=[self._create_test_clock()],
            success_conditions="Complete the test successfully",
            failure_consequences="Test fails if empty events are logged incorrectly",
            initial_enemies=[],
            initial_npcs=[]  # Empty!
        )

        # Mock DM agent
        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        session.agents = [mock_dm]

        # Act
        from aeonisk.multiagent.base import Message, MessageType
        import uuid
        from datetime import datetime

        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.SCENARIO_SETUP,
            sender='dm_test',
            recipient=None,
            payload={'scenario_setup': scenario_setup},
            timestamp=datetime.now()
        )

        session._handle_scenario_setup(message)

        # Assert: NO entity_lifecycle event logged
        entity_lifecycle_calls = [
            call for call in mock_jsonl_logger.log_event.call_args_list
            if call[0][0] == 'entity_lifecycle'
        ]

        assert len(entity_lifecycle_calls) == 0, \
            "Should NOT log entity_lifecycle event when no NPCs are spawned"

    def test_entity_lifecycle_event_round_number(self, temp_config, mock_jsonl_logger):
        """
        Test that entity_lifecycle event for session start NPCs uses appropriate round number.

        Session start NPCs should be logged at round 0 (before game starts).
        """
        # Arrange
        session = SelfPlayingSession(config_path=temp_config, random_seed=12345)

        # Mock the mechanics jsonl_logger (note: mechanics_engine not _mechanics_engine)
        session.shared_state.mechanics_engine = Mock()
        session.shared_state.mechanics_engine.jsonl_logger = mock_jsonl_logger
        session.shared_state.mechanics_engine.current_round = 0
        session.shared_state.mechanics_engine.scene_clocks = {}  # Empty dict for clock iteration

        # Create initial NPC
        initial_npcs = [
            NPCSpawn(
                name="Round Test NPC",
                faction="Freeborn",
                disposition="friendly",
                entity_type="neutral",
                threat_level="non_combatant",
                health=10,
                soak=0,
                skills={},
                description="Testing round number tracking for lifecycle events"
            )
        ]

        scenario_setup = ScenarioSetup(
            theme="Test Scenario for Round Number Tracking",
            location="Test Location",
            situation="Testing round number tracking to ensure entity_lifecycle events are logged with correct round numbers",
            starting_clocks=[self._create_test_clock()],
            success_conditions="Complete the test successfully",
            failure_consequences="Test fails if round numbers are incorrect",
            initial_enemies=[],
            initial_npcs=initial_npcs
        )

        # Mock DM agent
        mock_dm = Mock()
        mock_dm.agent_id = "dm_test"
        mock_npc = Mock()
        mock_npc.agent_id = "npc_round_test"
        mock_npc.name = "Round Test NPC"
        mock_dm._process_npc_spawn = Mock(return_value=mock_npc)
        session.agents = [mock_dm]

        # Act
        from aeonisk.multiagent.base import Message, MessageType
        import uuid
        from datetime import datetime

        message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.SCENARIO_SETUP,
            sender='dm_test',
            recipient=None,
            payload={'scenario_setup': scenario_setup},
            timestamp=datetime.now()
        )

        session._handle_scenario_setup(message)

        # Assert: Event logged with round_num kwarg
        entity_lifecycle_calls = [
            call for call in mock_jsonl_logger.log_event.call_args_list
            if call[0][0] == 'entity_lifecycle'
        ]

        assert len(entity_lifecycle_calls) == 1

        # Check round_num kwarg (should be 0 for session start)
        kwargs = entity_lifecycle_calls[0][1]
        assert 'round_num' in kwargs, \
            "log_event should be called with round_num kwarg"

        assert kwargs['round_num'] == 0, \
            f"Session start NPCs should be logged at round 0, got {kwargs['round_num']}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
