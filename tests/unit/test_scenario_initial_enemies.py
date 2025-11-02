"""
Unit tests for ScenarioSetup.initial_enemies processing.

Tests verify that the session._handle_scenario_setup() method correctly
processes initial_enemies from ScenarioSetup structured output and spawns
them at session start.

This test file implements TDD for the initial_enemies feature.

Author: Three Rivers AI Nexus
Date: 2025-11-02
"""

import pytest
from unittest.mock import Mock, patch, call
from aeonisk.multiagent.session import Message, MessageType
from aeonisk.multiagent.enemy_combat import EnemyCombatManager
from aeonisk.multiagent.schemas.story_events import ScenarioSetup, EnemySpawn, NewClock
from aeonisk.multiagent.schemas.shared_types import Position


class TestScenarioInitialEnemies:
    """Test initial_enemies spawning from ScenarioSetup."""

    def test_scenario_setup_spawns_initial_enemies(self, capsys):
        """
        ScenarioSetup.initial_enemies triggers enemy spawning at session start.

        Expected behavior:
        - DM generates ScenarioSetup with initial_enemies field populated
        - Session._handle_scenario_setup() extracts initial_enemies
        - Calls EnemyCombatManager.spawn_from_structured() with initial_enemies list
        - Prints spawn notifications to console

        This test will FAIL until we add initial_enemies processing to session.py
        """
        # Setup: Create mock session components
        from aeonisk.multiagent.session import SelfPlayingSession

        # Create minimal session (don't start it)
        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None  # Simplify for this test
        session._scenario_ready = Mock()

        # Create ScenarioSetup with initial_enemies
        scenario_setup = ScenarioSetup(
            theme="Corporate Raid",
            location="ACG Security Checkpoint",
            situation="You approach the heavily fortified ACG checkpoint. Guards patrol the entrance, and automated turrets track movement. Intelligence suggests the checkpoint stores sensitive data on void-corrupted assets. Your team needs to bypass security without triggering alarms.",
            starting_clocks=[
                NewClock(name="Security Alert", max_ticks=6, description="Guards raise alarm level")
            ],
            success_conditions="Bypass checkpoint without raising alarm",
            failure_consequences="Full lockdown, heavy reinforcements arrive",
            initial_enemies=[
                EnemySpawn(
                    template="Elite",
                    faction="ACG Security",
                    archetype="Guard Captain",
                    count=1,
                    spawn_reason="Stationed at checkpoint entry",
                    initial_position=Position.NEAR_ENEMY,
                    custom_traits="vigilant, disciplined"
                ),
                EnemySpawn(
                    template="Grunt",
                    faction="ACG Security",
                    archetype="Checkpoint Guard",
                    count=2,
                    spawn_reason="Routine patrol duty",
                    initial_position=Position.FAR_ENEMY,
                    custom_traits="alert"
                )
            ]
        )

        # Mock spawn_from_structured to return notifications
        session.enemy_combat.spawn_from_structured.return_value = [
            "Spawned: ACG Security Guard Captain (Elite, Near position)",
            "Spawned: ACG Security Checkpoint Guard #1 (Grunt, Far position)",
            "Spawned: ACG Security Checkpoint Guard #2 (Grunt, Far position)"
        ]

        # Create SCENARIO_SETUP message
        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            content="Scenario ready",
            payload={
                'scenario': {
                    'theme': scenario_setup.theme,
                    'location': scenario_setup.location
                },
                'scenario_setup': scenario_setup,  # Structured output object
                'opening_narration': "You approach the heavily fortified ACG checkpoint..."
            }
        )

        # Import the real _handle_scenario_setup method
        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup

        # Execute: Call _handle_scenario_setup with our mocked session
        real_handler(session, message)

        # Verify: spawn_from_structured was called with initial_enemies
        session.enemy_combat.spawn_from_structured.assert_called_once_with(
            scenario_setup.initial_enemies
        )

        # Verify: Spawn notifications were printed
        captured = capsys.readouterr()
        assert "Spawned: ACG Security Guard Captain" in captured.out
        assert "Spawned: ACG Security Checkpoint Guard #1" in captured.out
        assert "Spawned: ACG Security Checkpoint Guard #2" in captured.out

    def test_initial_enemies_respects_disabled_mode(self):
        """
        initial_enemies ignored when enemy_combat.enabled=False.

        Even if ScenarioSetup has initial_enemies, they should not spawn
        if enemy combat is disabled in session config.
        """
        from aeonisk.multiagent.session import MultiAgentSession

        session = Mock(spec=MultiAgentSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = False  # Disabled!
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        scenario_setup = ScenarioSetup(
            theme="Peaceful Negotiation",
            location="Neutral Meeting Ground",
            situation="You arrive at the neutral zone for trade negotiations. Mediator Chen oversees the talks between Resonance Communes and Independent Traders. The atmosphere is tense but peaceful.",
            starting_clocks=[
                NewClock(name="Negotiation Progress", max_ticks=8, description="Trust builds between factions")
            ],
            success_conditions="Reach trade agreement",
            failure_consequences="Trade talks collapse",
            initial_enemies=[
                EnemySpawn(
                    template="Grunt",
                    faction="Bandits",
                    archetype="Ambusher",
                    count=1,
                    spawn_reason="Hidden ambush",
                    initial_position=Position.FAR_ENEMY
                )
            ]
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            content="Scenario ready",
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': "You enter the neutral zone..."
            }
        )

        from aeonisk.multiagent.session import MultiAgentSession
        real_handler = MultiAgentSession._handle_scenario_setup
        real_handler(session, message)

        # Verify: spawn_from_structured was NOT called (combat disabled)
        session.enemy_combat.spawn_from_structured.assert_not_called()

    def test_initial_enemies_empty_list_handled_gracefully(self):
        """
        Empty initial_enemies list is handled without errors.

        ScenarioSetup with initial_enemies=[] should not crash or call spawn.
        """
        from aeonisk.multiagent.session import MultiAgentSession

        session = Mock(spec=MultiAgentSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        scenario_setup = ScenarioSetup(
            theme="Social Investigation",
            location="Resonance Community Hub",
            situation="The Resonance Communes welcome you cautiously. Elder Yara and Tech Specialist Finn observe your actions, gauging trustworthiness. The community values harmony and transparency.",
            starting_clocks=[
                NewClock(name="Community Trust", max_ticks=10, description="Earn the commune's confidence")
            ],
            success_conditions="Gain community trust",
            failure_consequences="Expelled from hub",
            initial_enemies=[]  # Empty list
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            content="Scenario ready",
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': "The community welcomes you warmly..."
            }
        )

        from aeonisk.multiagent.session import MultiAgentSession
        real_handler = MultiAgentSession._handle_scenario_setup

        # Execute: Should not raise any errors
        real_handler(session, message)

        # Verify: spawn_from_structured NOT called (empty list)
        session.enemy_combat.spawn_from_structured.assert_not_called()

    def test_scenario_setup_without_initial_enemies_field(self):
        """
        ScenarioSetup without initial_enemies field doesn't crash.

        Older scenarios or DM responses might not include initial_enemies.
        Should handle gracefully (field defaults to empty list in schema).
        """
        from aeonisk.multiagent.session import MultiAgentSession

        session = Mock(spec=MultiAgentSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Create ScenarioSetup without initial_enemies (will default to [])
        scenario_setup = ScenarioSetup(
            theme="Mystery Investigation",
            location="Abandoned Research Lab",
            situation="The lab is eerily quiet. Void energy crackles through damaged conduits. An AI fragment calling itself 'Echo' flickers on ancient terminals, offering cryptic hints about the research conducted here before the collapse.",
            starting_clocks=[
                NewClock(name="Lab Stability", max_ticks=8, description="Structure deteriorates")
            ],
            success_conditions="Uncover research data",
            failure_consequences="Lab collapses"
            # initial_enemies omitted (defaults to [])
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            content="Scenario ready",
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': "The lab is eerily quiet..."
            }
        )

        from aeonisk.multiagent.session import MultiAgentSession
        real_handler = MultiAgentSession._handle_scenario_setup

        # Execute: Should not raise any errors
        real_handler(session, message)

        # Verify: No spawn attempt (default empty list)
        session.enemy_combat.spawn_from_structured.assert_not_called()

    def test_legacy_scenario_format_without_scenario_setup_object(self):
        """
        Legacy message format without scenario_setup object doesn't crash.

        Older sessions may only have 'scenario' dict without ScenarioSetup object.
        Should handle gracefully and skip initial_enemies processing.
        """
        from aeonisk.multiagent.session import MultiAgentSession

        session = Mock(spec=MultiAgentSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Legacy message format (no scenario_setup object)
        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            content="Scenario ready",
            payload={
                'scenario': {
                    'theme': "Old Format Scenario",
                    'location': "Legacy Location"
                },
                # No scenario_setup key
                'opening_narration': "This is an old format scenario..."
            }
        )

        from aeonisk.multiagent.session import MultiAgentSession
        real_handler = MultiAgentSession._handle_scenario_setup

        # Execute: Should not crash
        real_handler(session, message)

        # Verify: No spawn attempt (no scenario_setup object)
        session.enemy_combat.spawn_from_structured.assert_not_called()
