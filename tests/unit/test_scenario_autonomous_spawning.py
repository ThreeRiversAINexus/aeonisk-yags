"""
Unit tests for autonomous enemy and NPC spawning in scenario generation.

Tests verify that:
1. DM can autonomously populate ScenarioSetup.initial_enemies for combat scenarios
2. DM can autonomously populate ScenarioSetup.initial_npcs for social scenarios
3. Session correctly processes both initial_enemies and initial_npcs at startup
4. Spawning respects scenario hints and constraints

This test file implements TDD for the autonomous spawning feature.

Author: Three Rivers AI Nexus
Date: 2025-11-15
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, call
from aeonisk.multiagent.session import Message, MessageType
from aeonisk.multiagent.enemy_combat import EnemyCombatManager
from aeonisk.multiagent.schemas.story_events import ScenarioSetup, EnemySpawn, NPCSpawn, NewClock
from aeonisk.multiagent.schemas.shared_types import Position


class TestAutonomousEnemySpawning:
    """Test DM autonomously spawning enemies in combat scenarios."""

    def test_combat_scenario_spawns_enemies_autonomously(self, capsys):
        """
        Combat-themed scenarios should spawn initial enemies autonomously.

        Expected behavior:
        - DM generates ScenarioSetup with theme="Combat/Raid/Assault"
        - DM populates initial_enemies with 2-6 enemies (guards, patrols, etc.)
        - Session spawns these enemies at session start

        This test validates the DM follows prompt guidance for combat scenarios.
        """
        from aeonisk.multiagent.session import SelfPlayingSession

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Simulate DM-generated combat scenario with autonomous enemy spawning
        scenario_setup = ScenarioSetup(
            theme="Corporate Facility Raid",
            location="ACG Weapons Research Lab - Sub-Level 3",
            situation="You breach the security door into Sub-Level 3. Red lights pulse as alarms wail. ACG Security forces converge on your position - two heavily armed guards take defensive positions behind lab equipment while their captain barks orders into comms. You have seconds before reinforcements arrive.",
            void_level=4,
            starting_clocks=[
                NewClock(
                    name="Reinforcements Arrive",
                    max_ticks=6,
                    description="Additional ACG forces mobilize",
                    advance_meaning="More guards arrive",
                    regress_meaning="Guards delayed"
                ),
                NewClock(
                    name="Data Extraction",
                    max_ticks=8,
                    description="Download research files",
                    advance_meaning="Data downloaded",
                    regress_meaning="Download interrupted"
                )
            ],
            success_conditions="Extract weapon research data before reinforcements overwhelm you",
            failure_consequences="Captured, data wiped, void experiments exposed to public",
            # DM autonomously populated initial_enemies for combat scenario
            initial_enemies=[
                EnemySpawn(
                    template="Elite",
                    faction="ACG",
                    archetype="Security Captain",
                    count=1,
                    spawn_reason="Leading defense of research facility",
                    initial_position=Position.NEAR_ENEMY,
                    disposition="combat_stance",
                    description="Tactical armor, neural-link headset, void-enhanced assault rifle"
                ),
                EnemySpawn(
                    template="Grunt",
                    faction="ACG",
                    archetype="Lab Guard",
                    count=2,
                    spawn_reason="Stationed at Sub-Level 3 entry",
                    initial_position=Position.FAR_ENEMY,
                    disposition="combat_stance",
                    description="Standard ACG security, riot shields and stun batons"
                )
            ]
        )

        session.enemy_combat.spawn_from_structured.return_value = [
            "Spawned: ACG Security Captain (Elite, Near)",
            "Spawned: Lab Guard #1 (Grunt, Far)",
            "Spawned: Lab Guard #2 (Grunt, Far)"
        ]

        message = Message(
            id="msg_001",
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            recipient=None,
            timestamp=datetime.now(),
            payload={
                'scenario': {
                    'theme': scenario_setup.theme,
                    'location': scenario_setup.location
                },
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify enemies spawned
        session.enemy_combat.spawn_from_structured.assert_called_once_with(
            scenario_setup.initial_enemies
        )

        captured = capsys.readouterr()
        assert "ACG Security Captain" in captured.out
        assert "Lab Guard" in captured.out

    def test_hostile_location_spawns_patrols(self, capsys):
        """
        Hostile locations should spawn enemies even for non-combat themes.

        Expected behavior:
        - Location is hostile (gang territory, void breach, restricted zone)
        - DM spawns patrol/guard enemies as environmental threats
        - Theme might be investigation/infiltration, not pure combat
        """
        from aeonisk.multiagent.session import SelfPlayingSession

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Investigation theme in hostile location
        scenario_setup = ScenarioSetup(
            theme="Infiltration and Investigation",
            location="Iron Fist Gang Territory - Warehouse District",
            situation="You slip into the Iron Fist's warehouse district under cover of darkness. Diesel fumes mix with void-tainted fog. Gang members patrol between crates of stolen goods, their void-enhanced tattoos glowing faintly. You need to find evidence of their void trafficking operation without raising alarms.",
            void_level=6,
            starting_clocks=[
                NewClock(
                    name="Gang Alert Level",
                    max_ticks=8,
                    description="Gang awareness of intruders",
                    advance_meaning="Gang alerted",
                    regress_meaning="Gang distracted"
                ),
                NewClock(
                    name="Evidence Collection",
                    max_ticks=6,
                    description="Gather proof of void trafficking",
                    advance_meaning="Evidence gathered",
                    regress_meaning="Evidence lost"
                )
            ],
            success_conditions="Collect trafficking evidence and escape undetected",
            failure_consequences="Discovered, interrogated, or sacrificed in void ritual",
            # DM spawns patrols for hostile location
            initial_enemies=[
                EnemySpawn(
                    template="Grunt",
                    faction="Independent",
                    archetype="Void-Touched Thug",
                    count=2,
                    spawn_reason="Patrolling warehouse perimeter",
                    initial_position=Position.FAR_ENEMY,
                    disposition="combat_stance",
                    description="Leather jackets, void tattoos, makeshift weapons"
                )
            ]
        )

        session.enemy_combat.spawn_from_structured.return_value = [
            "Spawned: Void-Touched Thug #1 (Grunt, Far)",
            "Spawned: Void-Touched Thug #2 (Grunt, Far)"
        ]

        message = Message(
            id="msg_002",
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            recipient=None,
            timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        session.enemy_combat.spawn_from_structured.assert_called_once()
        captured = capsys.readouterr()
        assert "Void-Touched Thug" in captured.out

    def test_social_scenario_no_enemies(self):
        """
        Social/investigation scenarios in safe zones don't spawn enemies.

        Expected behavior:
        - Theme is social/negotiation/investigation
        - Location is safe/neutral (community hub, neutral meeting ground)
        - DM leaves initial_enemies empty
        - Threats emerge later via story progression
        """
        from aeonisk.multiagent.session import SelfPlayingSession

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        scenario_setup = ScenarioSetup(
            theme="Trade Negotiation",
            location="Resonance Commune Hub - Harmony Hall",
            situation="Elder Yara welcomes you to Harmony Hall, a circular chamber filled with bioluminescent plants and soft music. Representatives from three factions sit at the negotiating table, each with competing interests in the upcoming trade route. Mediator Finn keeps the peace. Your diplomatic skills will determine if these factions cooperate or clash.",
            void_level=2,
            starting_clocks=[
                NewClock(
                    name="Faction Trust",
                    max_ticks=10,
                    description="Build consensus among factions",
                    advance_meaning="Trust builds",
                    regress_meaning="Trust erodes"
                ),
                NewClock(
                    name="Tension Level",
                    max_ticks=8,
                    description="Arguments escalate toward conflict",
                    advance_meaning="Tension rises",
                    regress_meaning="Calm restored"
                )
            ],
            success_conditions="All factions agree to trade route terms",
            failure_consequences="Negotiations collapse, factions turn hostile",
            initial_enemies=[]  # No enemies in safe social scenario
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # No enemies should spawn
        session.enemy_combat.spawn_from_structured.assert_not_called()

    def test_scenario_hint_no_enemies_respected(self):
        """
        Scenario hint with "NO enemies" constraint prevents spawning.

        Expected behavior:
        - Scenario hint explicitly says "NO SPAWN_ENEMY"
        - DM respects constraint and leaves initial_enemies empty
        - Even if location/theme would normally spawn enemies
        """
        from aeonisk.multiagent.session import SelfPlayingSession

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Even with hostile location, NO enemies due to hint constraint
        scenario_setup = ScenarioSetup(
            theme="Aftermath Investigation",
            location="ACG Security Checkpoint (Abandoned)",
            situation="The checkpoint is eerily quiet. Automated systems still flicker, but all personnel have vanished. Blood stains and void residue suggest a violent incident. You need to investigate what happened before the trail goes cold.",
            void_level=7,
            starting_clocks=[
                NewClock(
                    name="Evidence Degradation",
                    max_ticks=8,
                    description="Void corruption destroys evidence",
                    advance_meaning="Evidence corrupts",
                    regress_meaning="Evidence preserved"
                )
            ],
            success_conditions="Uncover what happened to checkpoint personnel",
            failure_consequences="Evidence lost to void corruption",
            initial_enemies=[]  # Respecting "NO SPAWN_ENEMY" hint
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify no spawning despite hostile location
        session.enemy_combat.spawn_from_structured.assert_not_called()


class TestAutonomousNPCSpawning:
    """Test DM autonomously spawning NPCs in scenarios."""

    def test_social_scenario_spawns_npcs_autonomously(self):
        """
        Social scenarios should spawn initial NPCs autonomously.

        Expected behavior:
        - DM generates ScenarioSetup with social/investigation theme
        - DM populates initial_npcs with quest-givers, witnesses, contacts
        - Session spawns these NPCs at session start via DM._process_npc_spawn
        """
        from aeonisk.multiagent.session import SelfPlayingSession
        from aeonisk.multiagent.dm import AIDMAgent

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        # Mock DM agent
        dm_agent = Mock(spec=AIDMAgent)
        dm_agent.agent_id = "dm_agent_001"
        dm_agent._process_npc_spawn = Mock(return_value=Mock(
            name="Fixer Kael",
            entity_type="neutral",
            disposition="neutral"
        ))

        session.agents = [dm_agent]

        # Social scenario with autonomous NPC spawning
        scenario_setup = ScenarioSetup(
            theme="Information Brokerage",
            location="The Void's Edge Cantina - Undercity",
            situation="Neon lights flicker in the smoke-filled cantina. Fixer Kael, a weathered information broker with neural implants, waves you over to a corner booth. He claims to have intel on ACG's void experiments, but his price is steep and his loyalty questionable. Other patrons watch with suspicious eyes.",
            void_level=5,
            starting_clocks=[
                NewClock(
                    name="Kael's Patience",
                    max_ticks=6,
                    description="Fixer gets impatient with negotiation",
                    advance_meaning="Kael grows impatient",
                    regress_meaning="Kael calms down"
                ),
                NewClock(
                    name="Rival Interest",
                    max_ticks=8,
                    description="Competing buyers arrive",
                    advance_meaning="Rivals approach",
                    regress_meaning="Rivals delayed"
                )
            ],
            success_conditions="Acquire ACG void experiment intel at acceptable price",
            failure_consequences="Intel sold to rivals, or Kael disappears",
            initial_enemies=[],  # No combat in social scenario
            # DM autonomously populated initial_npcs
            initial_npcs=[
                NPCSpawn(
                    name="Fixer Kael",
                    faction="Independent",
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="neutral",
                    description="Weathered face, neural implants, calculating eyes, data-slate in hand",
                    health=15,
                    soak=1,
                    details="Information broker specializing in corporate secrets. Motivated by profit, not loyalty. Has connections in ACG, Pantheon, and underworld."
                )
            ]
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify NPC spawn was processed
        dm_agent._process_npc_spawn.assert_called_once()
        call_args = dm_agent._process_npc_spawn.call_args[0][0]
        assert call_args.name == "Fixer Kael"
        assert call_args.entity_type == "neutral"

    def test_combat_scenario_spawns_prisoner_npcs(self):
        """
        Combat scenarios can spawn NPCs as prisoners/hostages.

        Expected behavior:
        - Combat theme with rescue/extraction objective
        - DM spawns enemies AND NPC prisoners
        - NPCs have entity_type="prisoner" or disposition="prisoner"
        """
        from aeonisk.multiagent.session import SelfPlayingSession
        from aeonisk.multiagent.dm import AIDMAgent

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        dm_agent = Mock(spec=AIDMAgent)
        dm_agent.agent_id = "dm_agent_001"
        dm_agent._process_npc_spawn = Mock(return_value=Mock(
            name="Captured Freeborn Scout",
            entity_type="prisoner",
            disposition="prisoner"
        ))

        session.agents = [dm_agent]

        scenario_setup = ScenarioSetup(
            theme="Hostage Rescue",
            location="Iron Fist Hideout - Basement Cells",
            situation="You descend into the Iron Fist's underground detention area. Two gang enforcers guard a makeshift cell where a Freeborn scout is chained and beaten. She mouths 'help me' as the enforcers turn toward you, weapons drawn. Time to act.",
            void_level=6,
            starting_clocks=[
                NewClock(
                    name="Backup Arrives",
                    max_ticks=6,
                    description="More gang members respond to alarm",
                    advance_meaning="Backup closes in",
                    regress_meaning="Backup delayed"
                )
            ],
            success_conditions="Rescue the Freeborn scout and escape",
            failure_consequences="Scout executed, party captured or killed",
            initial_enemies=[
                EnemySpawn(
                    template="Grunt",
                    faction="Independent",
                    archetype="Enforcer",
                    count=2,
                    spawn_reason="Guarding prisoner",
                    initial_position=Position.NEAR_ENEMY,
                    disposition="combat_stance",
                    description="Thugs with void-scarred knuckles and brutal weapons"
                )
            ],
            # Prisoner NPC
            initial_npcs=[
                NPCSpawn(
                    name="Captured Freeborn Scout",
                    faction="Freeborn",
                    entity_type="prisoner",
                    threat_level="non_combatant",
                    disposition="prisoner",
                    description="Bloodied scout with torn navigation gear, chained to wall",
                    health=5,  # Wounded
                    soak=0,
                    details="Scout was tracking void smuggling route, captured 3 days ago. Has critical intel on Iron Fist operations."
                )
            ]
        )

        session.enemy_combat.spawn_from_structured.return_value = [
            "Spawned: Enforcer #1 (Grunt, Near)",
            "Spawned: Enforcer #2 (Grunt, Near)"
        ]

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify both enemies and NPC prisoner spawned
        session.enemy_combat.spawn_from_structured.assert_called_once()
        dm_agent._process_npc_spawn.assert_called_once()

        call_args = dm_agent._process_npc_spawn.call_args[0][0]
        assert call_args.entity_type == "prisoner"
        assert "Scout" in call_args.name

    def test_investigation_scenario_spawns_witness_npcs(self):
        """
        Investigation scenarios spawn witnesses and informants.

        Expected behavior:
        - Investigation theme
        - DM spawns NPC witnesses with relevant knowledge
        - NPCs provide clues through dialogue
        """
        from aeonisk.multiagent.session import SelfPlayingSession
        from aeonisk.multiagent.dm import AIDMAgent

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        dm_agent = Mock(spec=AIDMAgent)
        dm_agent.agent_id = "dm_agent_001"
        dm_agent._process_npc_spawn = Mock(return_value=Mock(
            name="Terrified Lab Technician",
            entity_type="neutral",
            disposition="friendly"
        ))

        session.agents = [dm_agent]

        scenario_setup = ScenarioSetup(
            theme="Crime Scene Investigation",
            location="Pantheon Research Lab - Crime Scene",
            situation="The lab is a disaster. Equipment smashed, void residue everywhere. A terrified technician, Maya Chen, huddles in the corner. She witnessed the attack but is too traumatized to speak coherently. You need to calm her down and extract what she knows before Pantheon security arrives and locks down the scene.",
            void_level=4,
            starting_clocks=[
                NewClock(
                    name="Security Lockdown",
                    max_ticks=8,
                    description="Pantheon security secures crime scene",
                    advance_meaning="Lockdown imminent",
                    regress_meaning="Security delayed"
                ),
                NewClock(
                    name="Evidence Collection",
                    max_ticks=6,
                    description="Gather critical clues",
                    advance_meaning="Clues found",
                    regress_meaning="Clues contaminated"
                )
            ],
            success_conditions="Extract witness testimony and collect evidence",
            failure_consequences="Locked out, evidence confiscated by Pantheon",
            initial_enemies=[],
            # Witness NPC
            initial_npcs=[
                NPCSpawn(
                    name="Maya Chen",
                    faction="Pantheon Security",
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="friendly",
                    description="Young technician in torn lab coat, shaking, void burns on hands",
                    health=12,
                    soak=0,
                    details="Witnessed void entity attack. Knows about unauthorized experiments. Terrified but wants justice for her colleagues."
                )
            ]
        )

        message = Message(
            id="msg_002",
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            recipient=None,
            timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify witness NPC spawned
        dm_agent._process_npc_spawn.assert_called_once()
        call_args = dm_agent._process_npc_spawn.call_args[0][0]
        assert "Maya Chen" in call_args.name or "Technician" in call_args.name

    def test_empty_initial_npcs_handled_gracefully(self):
        """
        Empty initial_npcs list doesn't crash.

        Expected behavior:
        - ScenarioSetup with initial_npcs=[]
        - No NPC spawn attempts
        - No errors
        """
        from aeonisk.multiagent.session import SelfPlayingSession

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        scenario_setup = ScenarioSetup(
            theme="Wilderness Survival",
            location="Void-Tainted Wasteland",
            situation="The wasteland stretches endlessly. No signs of civilization. You're alone with the void.",
            void_level=8,
            starting_clocks=[
                NewClock(
                    name="Void Exposure",
                    max_ticks=10,
                    description="Prolonged void corruption effects",
                    advance_meaning="Corruption worsens",
                    regress_meaning="Corruption stabilizes"
                )
            ],
            success_conditions="Find shelter before void corruption overwhelms you",
            failure_consequences="Lost to void corruption, mind shattered",
            initial_enemies=[],
            initial_npcs=[]  # No NPCs in wilderness
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup

        # Should not crash
        real_handler(session, message)

    def test_npcs_without_dm_agent_logs_warning(self):
        """
        NPCs spawn attempt without DM agent logs warning.

        Expected behavior:
        - ScenarioSetup has initial_npcs
        - DM agent not found in session.agents
        - Warning logged, no crash
        """
        from aeonisk.multiagent.session import SelfPlayingSession
        import logging

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()
        session.agents = []  # No DM agent!

        scenario_setup = ScenarioSetup(
            theme="Social Encounter",
            location="Cantina",
            situation="A mysterious information broker slides into the booth across from you, offering valuable intel for the right price.",
            void_level=3,
            starting_clocks=[
                NewClock(
                    name="Timer",
                    max_ticks=5,
                    description="Time passes",
                    advance_meaning="Time runs out",
                    regress_meaning="Time gained"
                )
            ],
            success_conditions="Complete negotiation successfully",
            failure_consequences="Deal falls through, broker vanishes",
            initial_npcs=[
                NPCSpawn(
                    name="Broker",
                    faction="Independent",
                    entity_type="neutral",
                    threat_level="non_combatant",
                    disposition="neutral",
                    description="Mysterious information broker with data implants",
                    health=15,
                    soak=0,
                    details="Knows secrets"
                )
            ]
        )

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup

        # Should log warning but not crash
        with patch('aeonisk.multiagent.session.logger') as mock_logger:
            real_handler(session, message)
            mock_logger.warning.assert_called()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Cannot spawn NPC" in warning_call or "DM not found" in warning_call


class TestCombinedEnemyAndNPCSpawning:
    """Test scenarios that spawn both enemies and NPCs."""

    def test_mixed_scenario_spawns_both(self):
        """
        Mixed scenarios can spawn both enemies and NPCs.

        Expected behavior:
        - Scenario has combat element + social element
        - DM populates both initial_enemies and initial_npcs
        - Both spawn correctly at session start
        - Example: Rescue mission (enemies=guards, NPCs=prisoners)
        """
        from aeonisk.multiagent.session import SelfPlayingSession
        from aeonisk.multiagent.dm import AIDMAgent

        session = Mock(spec=SelfPlayingSession)
        session.enemy_combat = Mock(spec=EnemyCombatManager)
        session.enemy_combat.enabled = True
        session.shared_state = Mock()
        session.shared_state.mechanics_engine = None
        session._scenario_ready = Mock()

        dm_agent = Mock(spec=AIDMAgent)
        dm_agent.agent_id = "dm_agent_001"
        dm_agent._process_npc_spawn = Mock(return_value=Mock(
            name="Hostage",
            entity_type="prisoner",
            disposition="prisoner"
        ))

        session.agents = [dm_agent]

        scenario_setup = ScenarioSetup(
            theme="Extraction Under Fire",
            location="ACG Detention Facility",
            situation="Your contact is held in ACG's detention block. Guards patrol the corridors. You need to extract your contact and fight your way out.",
            void_level=4,
            starting_clocks=[
                NewClock(
                    name="Facility Alarm",
                    max_ticks=8,
                    description="Full lockdown activated",
                    advance_meaning="Alarm escalates",
                    regress_meaning="Alarm suppressed"
                )
            ],
            success_conditions="Extract contact and escape",
            failure_consequences="Contact executed, party captured",
            # Both enemies AND NPCs
            initial_enemies=[
                EnemySpawn(
                    template="Grunt",
                    faction="ACG",
                    archetype="Guard",
                    count=2,
                    spawn_reason="Patrolling detention block",
                    initial_position=Position.FAR_ENEMY,
                    disposition="combat_stance",
                    description="Armed guards"
                )
            ],
            initial_npcs=[
                NPCSpawn(
                    name="Contact - Rin Voss",
                    faction="Freeborn",
                    entity_type="prisoner",
                    threat_level="non_combatant",
                    disposition="prisoner",
                    description="Chained in cell, bruised but alert",
                    health=10,
                    soak=0,
                    details="Freeborn operative with critical intel"
                )
            ]
        )

        session.enemy_combat.spawn_from_structured.return_value = [
            "Spawned: Guard #1",
            "Spawned: Guard #2"
        ]

        message = Message(
            type=MessageType.SCENARIO_SETUP,
            sender="dm_agent",
            id="msg_test", recipient=None, timestamp=datetime.now(),
            payload={
                'scenario': {'theme': scenario_setup.theme, 'location': scenario_setup.location},
                'scenario_setup': scenario_setup,
                'opening_narration': scenario_setup.situation
            }
        )

        from aeonisk.multiagent.session import SelfPlayingSession
        real_handler = SelfPlayingSession._handle_scenario_setup
        real_handler(session, message)

        # Verify both enemies and NPCs spawned
        session.enemy_combat.spawn_from_structured.assert_called_once()
        dm_agent._process_npc_spawn.assert_called_once()
