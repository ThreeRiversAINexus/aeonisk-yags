"""
Self-playing session orchestrator that manages the complete gameplay loop.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from .base import GameCoordinator, MessageType, Message
from .dm import AIDMAgent
from .player import AIPlayerAgent
from .human_interface import HumanInterface
from .shared_state import SharedState
from .voice_profiles import VoiceLibrary
from .energy_economy import SeedType
from .outcome_parser import (
    parse_session_end_marker,
    parse_new_clock_marker,
    parse_pivot_scenario_marker
)

logger = logging.getLogger(__name__)


class SelfPlayingSession:
    """
    Orchestrates a complete self-playing game session with AI agents
    and optional human intervention.
    """
    
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.coordinator: Optional[GameCoordinator] = None
        self.agents: List[Any] = []
        self.human_interface: Optional[HumanInterface] = None
        self.session_id: Optional[str] = None
        self.session_data: List[Dict[str, Any]] = []
        self.running = False
        self.shared_state = SharedState()
        self.voice_library = VoiceLibrary()
        self._turn_history: List[str] = []
        self._pending_resolutions: Dict[str, asyncio.Event] = {}  # Track when resolutions complete
        self._pending_declarations: Dict[str, asyncio.Event] = {}  # Track when declarations complete
        self._declared_actions: Dict[str, Dict[str, Any]] = {}  # Buffer actions during declaration phase
        self._in_declaration_phase: bool = False  # Track current phase
        self._scenario_ready: asyncio.Event = asyncio.Event()  # Track when scenario is generated
        self._last_dm_narration: str = ""  # Track last DM narration for marker parsing
        self._session_end_status: Optional[str] = None  # Track if DM declared session end

        # Initialize mechanics systems
        print("Initializing mechanics systems...")
        self.shared_state.initialize_mechanics()
        print("✓ Mechanics engine ready")
        print("✓ Action validator ready")
        print("✓ Knowledge retrieval ready")

        # Load DM notes for scenario variety
        dm_notes_path = Path(self.config.get('output_dir', './multiagent_output')) / 'dm_notes.json'
        self.shared_state.load_dm_notes(str(dm_notes_path))
        self.dm_notes_path = dm_notes_path
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load session configuration."""
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        except (FileNotFoundError, PermissionError) as e:
            logger.error(f"Failed to access config file {config_path}: {e}")
            raise
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse config file {config_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading config from {config_path}: {e}")
            raise
                
    async def start_session(self):
        """Start the complete self-playing session."""
        logger.info("Starting self-playing session")

        # Start game coordinator
        socket_path = self.config.get('socket_path')
        self.coordinator = GameCoordinator(socket_path)
        await self.coordinator.start()

        # Register message handlers
        self.coordinator.message_bus.add_handler(
            'session_resolution_tracker',
            self._handle_action_resolved
        )
        self.coordinator.message_bus.add_handler(
            'session_declaration_buffer',
            self._handle_action_declared
        )
        self.coordinator.message_bus.add_handler(
            'session_scenario_tracker',
            self._handle_scenario_setup
        )
        self.coordinator.message_bus.add_handler(
            'session_dm_narration_tracker',
            self._handle_dm_narration
        )

        # Start human interface if enabled
        if self.config.get('enable_human_interface', True):
            self.human_interface = HumanInterface(str(self.coordinator.message_bus.socket_path))
            await self.human_interface.start()

        # Create and start AI agents
        await self._create_agents()

        # Wait for all agents to be ready
        await self._wait_for_agents_ready()

        # Start the game session
        self.session_id = await self.coordinator.create_session(self.config)

        # Initialize JSONL logger for machine-readable events
        from .mechanics import JSONLLogger
        output_dir = self.config.get('output_dir', './output')
        jsonl_logger = JSONLLogger(self.session_id, output_dir)

        # Attach logger to mechanics engine
        if self.shared_state and self.shared_state.mechanics_engine:
            self.shared_state.mechanics_engine.jsonl_logger = jsonl_logger
            print(f"✓ JSONL logging enabled: {jsonl_logger.log_file}")

        # Wait for DM to generate initial scenario before starting gameplay
        # SESSION_START triggers scenario generation, wait for SCENARIO_SETUP message
        print("Waiting for scenario generation...")
        await self._scenario_ready.wait()
        print("Scenario ready!")

        # Run the gameplay loop
        await self._run_gameplay_loop()
        
    async def _create_agents(self):
        """Create and start all AI agents."""
        agents_config = self.config.get('agents', {})
        
        # Create DM agent
        dm_config = agents_config.get('dm', {})
        dm_voice = self.voice_library.get_profile('ritual_scholar')
        dm_agent = AIDMAgent(
            agent_id='dm_01',
            socket_path=str(self.coordinator.message_bus.socket_path),
            llm_config=dm_config.get('llm', {}),
            voice_profile=dm_voice,
            shared_state=self.shared_state,
            prompt_enricher=self.voice_library.enrich_prompt,
            history_supplier=self._recent_history,
        )
        self.agents.append(dm_agent)
        await dm_agent.start()

        # Create player agents (randomly select from pool based on party_size)
        import random
        players_config = agents_config.get('players', [])
        party_size = self.config.get('party_size', 2)  # Default to 2 if not specified

        # Randomly select players from the pool
        if len(players_config) > party_size:
            selected_players = random.sample(players_config, party_size)
            logger.info(f"Selected {party_size} players: {[p['name'] for p in selected_players]}")
        else:
            selected_players = players_config
            logger.info(f"Using all {len(selected_players)} players from pool")

        # Update config to only include selected players (so DM sees correct party)
        self.config['agents']['players'] = selected_players

        assignments = self.voice_library.assign_to_agents(
            [f'player_{i+1:02d}' for i in range(len(selected_players))]
        )
        for i, player_config in enumerate(selected_players):
            agent_id = f'player_{i+1:02d}'
            player_agent = AIPlayerAgent(
                agent_id=agent_id,
                socket_path=str(self.coordinator.message_bus.socket_path),
                character_config=player_config,
                llm_config=player_config.get('llm', {}),
                voice_profile=assignments.get(agent_id),
                shared_state=self.shared_state,
                prompt_enricher=self.voice_library.enrich_prompt,
                history_supplier=self._recent_history,
            )
            self.agents.append(player_agent)
            await player_agent.start()

        # Initialize mechanics state for all players
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics:
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
            for player in player_agents:
                # Initialize soulcredit state with character's starting value
                initial_sc = getattr(player.character_state, 'soulcredit', 0)
                mechanics.get_soulcredit_state(player.agent_id, initial_score=initial_sc)
                logger.info(f"Initialized {player.character_state.name} soulcredit: {initial_sc}")

                # Degrade Raw Seeds (1 cycle per session)
                if hasattr(player.character_state, 'energy_inventory') and player.character_state.energy_inventory:
                    player.character_state.energy_inventory.degrade_raw_seeds(cycles=1)
                    raw_count = player.character_state.energy_inventory.count_seeds(SeedType.RAW)
                    hollow_count = player.character_state.energy_inventory.count_seeds(SeedType.HOLLOW)
                    if hollow_count > 0:
                        logger.info(f"{player.character_state.name}: Raw Seeds degraded (now {raw_count} Raw, {hollow_count} Hollow)")

        logger.info(f"Created {len(self.agents)} agents")
        
    async def _wait_for_agents_ready(self):
        """Wait for all agents to signal readiness."""
        # Simple wait - you could enhance with proper synchronization
        await asyncio.sleep(2)
        logger.info("All agents ready")
        
    async def _run_gameplay_loop(self):
        """Run the main gameplay loop."""
        self.running = True
        round_count = 0
        max_rounds = self.config.get('max_turns', 50)

        print(f"\n=== Starting Session {self.session_id} ===")
        print(f"Max rounds: {max_rounds}")
        print(f"Human interface: {'Enabled' if self.human_interface else 'Disabled'}")

        # Show selected players
        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
        if player_agents:
            print(f"Selected Players:")
            for player in player_agents:
                print(f"  - {player.character_state.name} ({player.character_state.faction})")
        print()

        while self.running:
            round_count += 1
            print(f"\n--- Round {round_count} ---")
            self._turn_history.append(f"Round {round_count} begins")

            # Reset void caps for all characters at round start
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                mechanics.current_round = round_count  # Update round counter for logging

                # Log round start event
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_round_start(round_count)

                for agent_id, void_state in mechanics.void_states.items():
                    void_state.reset_round_void()

            # Run round with initiative-based turns
            await self._run_initiative_round()

            # Run DM turn at end of round
            await self._run_dm_turn()

            # Check for random vendor spawns
            await self._check_vendor_spawn(round_count)

            # Check if we've completed enough rounds
            if round_count >= max_rounds:
                print(f"\n=== Completed {round_count} rounds ===")
                break

            # Check for session end conditions
            if await self._check_end_conditions():
                break

            # Brief pause between rounds
            await asyncio.sleep(1)

        # Mission debrief
        await self._run_mission_debrief()

        await self._end_session()
        
    async def _run_initiative_round(self):
        """
        Run a round with proper tactical flow:
        1. Declaration phase (slowest → fastest)
        2. Resolution phase (fastest → slowest)
        3. DM describes overall outcome
        """
        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]

        if not player_agents:
            return

        # Calculate initiative for each player (Agility × 4 + d20)
        initiative_order = []
        mechanics = self.shared_state.get_mechanics_engine()

        for player_agent in player_agents:
            # Get player's Agility attribute
            agility = player_agent.character_state.attributes.get('Agility', 3)
            initiative = mechanics.calculate_initiative(agility)
            initiative_order.append((initiative, player_agent))
            print(f"[{player_agent.character_state.name}] Initiative: {initiative}")

        # Sort by initiative (highest first)
        initiative_order.sort(key=lambda x: x[0], reverse=True)

        # PHASE 1: DECLARATIONS (slowest → fastest, so faster players can react)
        print("\n=== Declaration Phase ===")
        self._in_declaration_phase = True
        self._declared_actions.clear()

        # Log declaration phase start
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_declaration_phase_start(mechanics.current_round)

        for initiative_score, player_agent in reversed(initiative_order):  # Reversed = slowest first
            print(f"\n[{player_agent.character_state.name}] declaring (initiative {initiative_score})...")

            # Create event to track when this player's declaration arrives
            declaration_event = asyncio.Event()
            self._pending_declarations[player_agent.agent_id] = declaration_event

            turn_message = Message(
                id=f"turn_{datetime.now().isoformat()}_{player_agent.agent_id}",
                type=MessageType.TURN_REQUEST,
                sender='coordinator',
                recipient=player_agent.agent_id,
                payload={'phase': 'declaration', 'initiative': initiative_score},
                timestamp=datetime.now()
            )

            await self.coordinator.message_bus._route_message(turn_message)

            # Wait for this player's declaration to be buffered
            await declaration_event.wait()
            logger.debug(f"{player_agent.character_state.name} declaration received")

            # Clean up the event
            if player_agent.agent_id in self._pending_declarations:
                del self._pending_declarations[player_agent.agent_id]

        self._in_declaration_phase = False

        # PHASE 2: DM ADJUDICATION
        # Send ALL declarations to DM for adjudication
        print("\n=== Resolution Phase ===")
        print("DM adjudicating all actions...")

        # Build list of all actions with initiative order
        actions_for_adjudication = []
        for initiative_score, player_agent in initiative_order:  # Sorted by initiative
            if player_agent.agent_id in self._declared_actions:
                buffered_action = self._declared_actions[player_agent.agent_id]
                actions_for_adjudication.append({
                    'player_id': player_agent.agent_id,
                    'character_name': player_agent.character_state.name,
                    'initiative': initiative_score,
                    'action': buffered_action['action']
                })

        if not actions_for_adjudication:
            logger.warning("No actions to adjudicate")
            return

        # Create event to track when adjudication completes
        adjudication_event = asyncio.Event()
        self._pending_resolutions['adjudication'] = adjudication_event

        # Send all actions to DM for adjudication
        adjudication_message = Message(
            id=f"adjudicate_{datetime.now().isoformat()}",
            type=MessageType.ACTION_DECLARED,
            sender='coordinator',
            recipient='dm_01',
            payload={
                'phase': 'adjudication',
                'actions': actions_for_adjudication,
                'round': mechanics.current_round if mechanics else 0
            },
            timestamp=datetime.now()
        )

        await self.coordinator.message_bus._route_message(adjudication_message)

        # Wait for DM to complete adjudication
        await adjudication_event.wait()
        logger.debug("Adjudication complete")

        # Clean up
        if 'adjudication' in self._pending_resolutions:
            del self._pending_resolutions['adjudication']

        # Clear the action buffer for next round
        self._declared_actions.clear()
        
    async def _run_dm_turn(self):
        """Run DM turn."""
        dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
        
        if dm_agents:
            dm_agent = dm_agents[0]
            dm_message = Message(
                id=f"dm_turn_{datetime.now().isoformat()}",
                type=MessageType.TURN_REQUEST,
                sender='coordinator',
                recipient=dm_agent.agent_id,
                payload={'phase': 'dm_narrative'},
                timestamp=datetime.now()
            )
            
            await self.coordinator.message_bus._route_message(dm_message)

        # Wait for DM response
        await asyncio.sleep(2)

    async def _check_vendor_spawn(self, round_count: int):
        """Check if a vendor should randomly spawn this round."""
        vendor_frequency = self.config.get('vendor_spawn_frequency', -1)

        # -1 means vendors never spawn randomly
        if vendor_frequency <= 0:
            return

        # Check if this is a spawn round
        if round_count % vendor_frequency != 0:
            return

        # Get DM agent
        dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
        if not dm_agents:
            return

        dm_agent = dm_agents[0]

        # Get current scenario theme for context-aware vendor selection
        scenario = dm_agent.current_scenario
        scenario_theme = scenario.theme if scenario else "neutral"

        # Use DM's contextual vendor selection logic
        vendor = dm_agent._select_contextual_vendor(scenario_theme)

        if vendor:
            # Update scenario with active vendor
            if scenario:
                scenario.active_vendor = vendor

            # Announce vendor arrival to all players
            print(f"\n💰 [Vendor Arrives] {vendor.name} ({vendor.vendor_type.value})")
            print(f"   Faction: {vendor.faction}")
            print(f"   {vendor.greeting}")

            # Send notification to all players
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]

            vendor_announcement = f"\n💰 **{vendor.name} arrives!**\n"
            vendor_announcement += f"A {vendor.faction} {vendor.vendor_type.value} approaches.\n"
            vendor_announcement += f'"{vendor.greeting}"\n'
            vendor_announcement += f"They have goods for sale or barter."

            for player_agent in player_agents:
                # Send as a DM narration message
                vendor_msg = Message(
                    id=f"vendor_spawn_{round_count}_{datetime.now().isoformat()}",
                    type=MessageType.DM_NARRATION,
                    sender='dm',
                    recipient=player_agent.agent_id,
                    payload={'narration': vendor_announcement},
                    timestamp=datetime.now()
                )
                await self.coordinator.message_bus._route_message(vendor_msg)

            logger.info(f"Round {round_count}: Spawned vendor {vendor.name}")

    async def _run_mission_debrief(self):
        """Run post-mission debrief where players discuss what happened."""
        print(f"\n{'='*60}")
        print(f"=== MISSION DEBRIEF ===")
        print(f"{'='*60}\n")

        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]

        if not player_agents or not player_agents[0].llm_config:
            print("[Debrief skipped - no AI players]\n")
            return

        # Build debrief context
        mechanics = self.shared_state.get_mechanics_engine()

        # Sync final state from mechanics engine to player character states
        if mechanics:
            for player in player_agents:
                player_id = player.agent_id
                # Sync void from mechanics to character state
                if player_id in mechanics.void_states:
                    player.character_state.void_score = mechanics.void_states[player_id].score
                # Sync soulcredit from mechanics to character state
                if player_id in mechanics.soulcredit_states:
                    player.character_state.soulcredit = mechanics.soulcredit_states[player_id].score

        # Get final state
        void_states = []
        for player in player_agents:
            void_score = player.character_state.void_score
            sc_score = player.character_state.soulcredit
            void_states.append(f"{player.character_state.name}: Void {void_score}/10, Soulcredit {sc_score}")

        clocks_status = []
        if mechanics and mechanics.scene_clocks:
            for name, clock in mechanics.scene_clocks.items():
                clocks_status.append(f"{name}: {clock.current}/{clock.maximum}")

        # Prompt each player for debrief (sequential for conversation flow)
        debriefs = []
        for player in player_agents:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

                # Get scenario situation from player's current_scenario
                scenario_situation = "Mission completed"
                if player.current_scenario:
                    scenario_situation = player.current_scenario.get('situation', 'Unknown situation')

                # Build conversation history from previous debriefs
                conversation_so_far = ""
                if debriefs:
                    conversation_so_far = "\n\n**What others have said:**\n"
                    for prev_name, prev_statement in debriefs:
                        conversation_so_far += f"{prev_name}: \"{prev_statement}\"\n"
                    conversation_so_far += "\nYou can respond to what they said or add your own perspective.\n"

                debrief_prompt = f"""You are {player.character_state.name} ({player.character_state.faction}) in a post-mission debrief conversation.

**Mission Context:**
{scenario_situation}

**Final Status:**
{chr(10).join(void_states)}
{chr(10).join(clocks_status) if clocks_status else 'No clocks tracked'}

**Your Faction**: {player.character_state.faction}
**Your Goals**: {', '.join(player.character_state.goals)}
{conversation_so_far}

Provide a brief (2-3 sentence) debrief statement in character voice:
- What did you accomplish or learn?
- How do you feel about working with your companion(s)?
- What are your concerns going forward?
{"- You can respond to what your companion said" if debriefs else ""}

Keep it conversational and in character. This is a dialogue, not a report."""

                response = await asyncio.to_thread(
                    client.messages.create,
                    model=player.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                    max_tokens=250,
                    temperature=0.8,
                    messages=[{"role": "user", "content": debrief_prompt}]
                )

                debrief_text = response.content[0].text.strip()
                print(f"[{player.character_state.name}] {debrief_text}\n")
                debriefs.append((player.character_state.name, debrief_text))

                # Log debrief to JSONL
                if mechanics and mechanics.jsonl_logger:
                    character_state_snapshot = {
                        'name': player.character_state.name,
                        'faction': player.character_state.faction,
                        'void_score': player.character_state.void_score,
                        'soulcredit': player.character_state.soulcredit,
                        'goals': player.character_state.goals,
                    }
                    mechanics.jsonl_logger.log_debrief(
                        character_name=player.character_state.name,
                        debrief_text=debrief_text,
                        character_state=character_state_snapshot
                    )

                await asyncio.sleep(1)

            except Exception as e:
                print(f"[{player.character_state.name}] [Debrief generation failed: {e}]\n")

        print(f"{'='*60}\n")

    def _spawn_new_clocks(self, new_clocks: List[Dict[str, any]]):
        """Spawn new clocks from DM markers."""
        if not self.shared_state or not self.shared_state.mechanics_engine:
            return

        mechanics = self.shared_state.mechanics_engine

        for clock_data in new_clocks:
            name = clock_data['name']
            max_ticks = clock_data['max']
            description = clock_data['description']

            # Create the new clock
            mechanics.create_scene_clock(name, max_ticks, description)
            print(f"\n🕐 NEW CLOCK SPAWNED: {name} (0/{max_ticks}) - {description}")

            # Log the new clock
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_clock_spawn(name, max_ticks, description)

    async def _check_end_conditions(self) -> bool:
        """Check if session should end."""
        # Check if DM declared session end
        if self._session_end_status:
            print(f"\n🎬 DM DECLARED SESSION {self._session_end_status.upper()}")

            # Log session end
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                if mechanics.jsonl_logger:
                    # Get current state for logging
                    final_state = mechanics.get_state_summary()
                    final_state['session_end_status'] = self._session_end_status
                    final_state['dm_final_narration'] = self._last_dm_narration
                    mechanics.jsonl_logger.log_session_end(final_state)

            return True

        # Otherwise session continues
        return False
        
    async def _end_session(self):
        """End the session and save data."""
        print(f"\n=== Session {self.session_id} Ending ===")

        # Print final state summary
        if self.shared_state.mechanics_engine:
            print("\n--- Final State Summary ---")
            state_summary = self.shared_state.mechanics_engine.get_state_summary()

            # Print scene clocks
            if state_summary.get('scene_clocks'):
                print("\nScene Clocks:")
                for name, clock in state_summary['scene_clocks'].items():
                    print(f"  {name}: {clock['progress']} {'[FILLED]' if clock['filled'] else ''}")

            # Print character final states
            if state_summary.get('void_states'):
                print("\nCharacter Final States:")
                for agent_id, void_info in state_summary['void_states'].items():
                    # Find the character details from player agents
                    char_details = None
                    for player in [a for a in self.agents if hasattr(a, 'character_state')]:
                        if player.agent_id == agent_id:
                            char_details = player.character_state
                            break

                    if char_details:
                        # Get key equipment/skills
                        top_skills = sorted(char_details.skills.items(), key=lambda x: x[1], reverse=True)[:3]
                        skills_str = ", ".join([f"{skill} {val}" for skill, val in top_skills])

                        print(f"  {char_details.name} ({char_details.faction}):")
                        print(f"    Void: {void_info['score']}/10 ({void_info['level']})")
                        print(f"    Soulcredit: {char_details.soulcredit}")
                        print(f"    Top Skills: {skills_str}")
                    else:
                        print(f"  {agent_id}: {void_info['score']}/10 ({void_info['level']})")

            print("=" * 40)

            # Log session end event
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_session_end(state_summary)
                print(f"\n✓ JSONL log saved: {mechanics.jsonl_logger.log_file}")

        # Collect voice profiles for ONLY the players in this session (not entire pool)
        player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
        active_voice_profiles = []
        active_player_configs = []
        for player in player_agents:
            if hasattr(player, 'voice_profile') and player.voice_profile:
                active_voice_profiles.append(player.voice_profile.as_dict())
            # Collect character config for this player
            active_player_configs.append({
                'name': player.character_state.name,
                'faction': player.character_state.faction,
                'attributes': player.character_state.attributes,
                'skills': player.character_state.skills,
                'void_score': player.character_state.void_score,
                'soulcredit': player.character_state.soulcredit,
                'goals': player.character_state.goals,
                'bonds': player.character_state.bonds,
            })

        # Filter config to only include active players
        session_config = dict(self.config)
        if 'agents' in session_config and 'players' in session_config['agents']:
            session_config['agents']['players'] = active_player_configs

        # Load JSONL events if available
        jsonl_events = []
        if mechanics and mechanics.jsonl_logger:
            try:
                import json
                with open(mechanics.jsonl_logger.log_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            jsonl_events.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Failed to load JSONL events: {e}")

        # Restructure events into rounds and turns
        structured_rounds = self._restructure_events_into_rounds(jsonl_events)

        # Collect final session data
        final_data = {
            'session_id': self.session_id,
            'config': session_config,  # Filtered config with only active players
            'rounds': structured_rounds,  # NEW: Properly nested rounds/turns/resolutions
            'raw_events': jsonl_events,  # Keep raw events for debugging
            'end_time': datetime.now().isoformat(),
            'shared_state': self.shared_state.snapshot(),
            'voice_profiles': active_voice_profiles,  # Only active players
        }

        # Save session data
        await self._save_session_data(final_data)
        
        # Shutdown all agents
        await self._shutdown_agents()
        
        self.running = False
        
    def _restructure_events_into_rounds(self, events: List[Dict]) -> List[Dict]:
        """
        Restructure flat event list into nested rounds -> turns -> resolutions.

        Expected structure:
        [
            {
                "round_number": 1,
                "scenario": {...},  // Only in round 1
                "turns": [
                    {
                        "agent": "player_01",
                        "character": "Gestator Lyss",
                        "action": {...},
                        "resolution": {...},
                        "narration": "...",
                        "clocks_after": {...}
                    }
                ]
            }
        ]
        """
        if not events:
            return []

        rounds = []
        current_round = None
        pending_actions = {}  # Map agent_id -> action dict
        scenario_info = None  # Store scenario from session start

        for event in events:
            event_type = event.get('event_type')

            # Capture scenario information
            if event_type == 'scenario':
                scenario_info = event.get('scenario')

            # Start new round
            elif event_type == 'round_start':
                if current_round and (current_round.get('declarations') or current_round.get('resolutions')):
                    # Save previous round if it has content
                    rounds.append(current_round)

                current_round = {
                    'round_number': event.get('round'),
                    'timestamp': event.get('ts'),
                    'declarations': [],
                    'resolutions': [],
                    'synthesis': None
                }

                # Add scenario to round 1
                if event.get('round') == 1 and scenario_info:
                    current_round['scenario'] = scenario_info

            # Declaration phase start
            elif event_type == 'declaration_phase_start':
                # Just marks the phase, no action needed
                pass

            # Individual action declaration
            elif event_type == 'action_declaration':
                if current_round:
                    current_round['declarations'].append({
                        'player_id': event.get('player_id'),
                        'character_name': event.get('character_name'),
                        'initiative': event.get('initiative'),
                        'action': event.get('action'),
                        'timestamp': event.get('ts')
                    })

            # Adjudication phase start
            elif event_type == 'adjudication_start':
                # Just marks the phase, no action needed
                pass

            # Action resolution (individual)
            elif event_type == 'action_resolution':
                if current_round:
                    current_round['resolutions'].append({
                        'agent': event.get('agent'),
                        'action': event.get('action'),
                        'context': event.get('context', {}),
                        'roll': event.get('roll', {}),
                        'economy': event.get('economy', {}),
                        'clocks': event.get('clocks', {}),
                        'effects': event.get('effects', []),
                        'timestamp': event.get('ts')
                    })

            # Round synthesis
            elif event_type == 'round_synthesis':
                if current_round:
                    current_round['synthesis'] = event.get('synthesis')
                    current_round['synthesis_timestamp'] = event.get('ts')

            # Mission debrief
            elif event_type == 'mission_debrief':
                if current_round:
                    if 'debriefs' not in current_round:
                        current_round['debriefs'] = []
                    current_round['debriefs'].append({
                        'character': event.get('character'),
                        'debrief': event.get('debrief'),
                        'final_state': event.get('final_state'),
                        'timestamp': event.get('ts')
                    })

        # Add final round
        if current_round and (current_round.get('declarations') or current_round.get('resolutions')):
            rounds.append(current_round)

        return rounds

    async def _save_session_data(self, data: Dict[str, Any]):
        """Save session data for training/analysis."""
        output_dir = Path(self.config.get('output_dir', './output'))
        output_dir.mkdir(exist_ok=True)
        
        # Save as JSON for easy processing
        json_path = output_dir / f"session_{self.session_id}.json"
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            
        # Save as YAML for human readability
        yaml_path = output_dir / f"session_{self.session_id}.yaml"
        
        # Convert any custom objects to dictionaries to avoid Python object serialization
        def safe_dict_conversion(obj):
            """Safely convert custom objects to dictionaries."""
            if hasattr(obj, '__dict__'):
                return {k: safe_dict_conversion(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, dict):
                return {k: safe_dict_conversion(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [safe_dict_conversion(item) for item in obj]
            else:
                return obj
        
        safe_data = safe_dict_conversion(data)
        
        with open(yaml_path, 'w') as f:
            yaml.dump(safe_data, f, default_flow_style=False)
            
        print(f"Session data saved to {json_path}")
        
    async def _shutdown_agents(self):
        """Shutdown all agents."""
        # Send shutdown messages
        shutdown_message = Message(
            id="shutdown_all",
            type=MessageType.SHUTDOWN,
            sender='coordinator',
            recipient=None,  # broadcast
            payload={},
            timestamp=datetime.now()
        )
        
        await self.coordinator.message_bus._route_message(shutdown_message)
        
        # Wait for graceful shutdown
        await asyncio.sleep(1)
        
        # Force shutdown agents
        for agent in self.agents:
            agent.shutdown()
            
        # Shutdown coordinator
        self.coordinator.shutdown()
        
        # Shutdown human interface
        if self.human_interface:
            self.human_interface.shutdown()

        logger.info("All agents shutdown")

    def _recent_history(self) -> List[str]:
        """Return a small slice of recent turn history for prompt context."""
        return self._turn_history[-5:]

    def _handle_scenario_setup(self, message: Message):
        """Track when scenario is ready."""
        if message.type != MessageType.SCENARIO_SETUP:
            return

        self._scenario_ready.set()

    def _handle_action_declared(self, message: Message):
        """Buffer ACTION_DECLARED messages during declaration phase."""
        if message.type != MessageType.ACTION_DECLARED:
            return

        # Only buffer during declaration phase
        if not self._in_declaration_phase:
            return

        # Buffer the action
        # Note: message.payload IS the action dict (not nested under 'action' key)
        agent_id = message.sender
        self._declared_actions[agent_id] = {
            'agent_id': agent_id,
            'action': message.payload,  # Payload IS the action
            'timestamp': message.timestamp
        }
        logger.debug(f"Buffered action from {agent_id}")

        # Log the declaration
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                # Find the character name and initiative for this agent
                player_agent = next((a for a in self.agents if a.agent_id == agent_id), None)
                if player_agent:
                    character_name = player_agent.character_state.name
                    # Get initiative from the payload if available, otherwise 0
                    initiative = message.payload.get('initiative', 0)
                    mechanics.jsonl_logger.log_action_declaration(
                        player_id=agent_id,
                        character_name=character_name,
                        initiative=initiative,
                        action=message.payload,
                        round_num=mechanics.current_round
                    )

        # Signal that this agent's declaration is complete
        if agent_id in self._pending_declarations:
            self._pending_declarations[agent_id].set()
        else:
            logger.warning(f"No pending declaration event for {agent_id}")

    def _handle_action_resolved(self, message: Message):
        """Handle ACTION_RESOLVED messages to signal turn completion."""
        if message.type != MessageType.ACTION_RESOLVED:
            return

        # Extract the agent who completed their action
        agent_id = message.payload.get('agent_id')
        if agent_id and agent_id in self._pending_resolutions:
            # Signal that this agent's resolution/adjudication is complete
            self._pending_resolutions[agent_id].set()
            logger.debug(f"Resolution complete for {agent_id}")

    def _handle_dm_narration(self, message: Message):
        """Handle DM narration and check for control markers."""
        if message.type != MessageType.DM_NARRATION:
            return

        narration = message.payload.get('narration', '')
        self._last_dm_narration = narration

        # Check for session end marker
        end_result = parse_session_end_marker(narration)
        if end_result['status'] != 'none':
            self._session_end_status = end_result['status']
            logger.info(f"DM declared session end: {end_result['status']}" +
                       (f" - {end_result['reason']}" if end_result['reason'] else ""))

        # Check for new clock markers
        new_clocks = parse_new_clock_marker(narration)
        if new_clocks:
            self._spawn_new_clocks(new_clocks)

        # Check for scenario pivot marker
        pivot_result = parse_pivot_scenario_marker(narration)
        if pivot_result['should_pivot']:
            logger.info(f"DM requested scenario pivot: {pivot_result['new_theme']}")

            # Archive ALL filled clocks when scenario pivots
            # The pivot itself means the DM has addressed the situation
            mechanics = self.shared_state.mechanics_engine
            if mechanics and mechanics.scene_clocks:
                clocks_to_archive = []
                for clock_name, clock in list(mechanics.scene_clocks.items()):
                    if clock.filled:  # Archive any filled clock
                        overflow = clock.current - clock.maximum
                        logger.info(f"🗑️  Archiving filled clock after pivot: {clock_name} ({clock.current}/{clock.maximum}, +{overflow})")
                        clocks_to_archive.append(clock_name)
                        del mechanics.scene_clocks[clock_name]

                if clocks_to_archive:
                    print(f"\n🔄 SCENARIO PIVOT: '{pivot_result['new_theme']}'")
                    print(f"   Archived {len(clocks_to_archive)} filled clocks: {', '.join(clocks_to_archive)}")

            # Notify all players of the scenario pivot
            pivot_narration = f"The situation has changed! New objective: {pivot_result['new_theme']}"
            self.bus.send_message(
                MessageType.SCENARIO_UPDATE,
                self.session_id,
                None,  # Broadcast to all
                {
                    'new_theme': pivot_result['new_theme'],
                    'new_situation': pivot_narration,
                    'pivot_narration': pivot_narration
                }
            )

            # Store pivot for DM to use in next scenario generation
            dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
            if dm_agents:
                dm_agents[0].pending_scenario_pivot = pivot_result['new_theme']


# Configuration example
EXAMPLE_CONFIG = {
    "session_name": "test_session",
    "max_turns": 20,
    "output_dir": "./multiagent_output",
    "enable_human_interface": True,
    "agents": {
        "dm": {
            "llm": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7
            }
        },
        "players": [
            {
                "name": "Zara Nightwhisper",
                "faction": "Tempest Industries",
                "personality": {
                    "riskTolerance": 8,
                    "voidCuriosity": 9,
                    "bondPreference": "avoids",
                    "ritualConservatism": 2
                },
                "attributes": {"Body": 6, "Mind": 8, "Soul": 7},
                "skills": {"Astral Arts": 5, "Investigation": 4},
                "void_score": 2,
                "soulcredit": 15,
                "goals": ["Explore void manipulation", "Advance Tempest interests"]
            },
            {
                "name": "Echo Resonance",
                "faction": "Resonance Communes",
                "personality": {
                    "riskTolerance": 4,
                    "voidCuriosity": 3,
                    "bondPreference": "seeks",
                    "ritualConservatism": 6
                },
                "attributes": {"Body": 5, "Mind": 6, "Soul": 9},
                "skills": {"Astral Arts": 6, "Social": 5},
                "void_score": 0,
                "soulcredit": 12,
                "goals": ["Form meaningful bonds", "Support community harmony"]
            }
        ]
    }
}