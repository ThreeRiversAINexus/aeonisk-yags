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
    parse_pivot_scenario_marker,
    parse_advance_story_marker
)
from .enemy_combat import EnemyCombatManager
from .tactical_resolution import ResolutionState

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
        self._declared_actions: Dict[str, List[Dict[str, Any]]] = {}  # Buffer actions during declaration phase (supports multiple actions per agent)
        self._in_declaration_phase: bool = False  # Track current phase
        self._scenario_ready: asyncio.Event = asyncio.Event()  # Track when scenario is generated
        self._synthesis_complete: asyncio.Event = asyncio.Event()  # Track when round synthesis is complete
        self._last_dm_narration: str = ""  # Track last DM narration for marker parsing
        self._session_end_status: Optional[str] = None  # Track if DM declared session end

        # Round statistics for ML training / balance analysis
        self._round_stats = {
            'actions_attempted': 0,
            'success_count': 0,
            'total_margin': 0,
            'damage_dealt_by_players': 0,
            'damage_taken_by_players': 0,
            'void_gained': 0,
            'void_lost': 0,
            'clocks_advanced': 0,
            'clocks_filled': 0
        }

        # Track if scenario had clocks (for detecting when all clocks expire/complete)
        self._had_active_clocks = False

        # Initialize mechanics systems
        print("Initializing mechanics systems...")
        self.shared_state.initialize_mechanics()
        print("✓ Mechanics engine ready")
        print("✓ Action validator ready")
        print("✓ Knowledge retrieval ready")

        # Initialize enemy combat manager
        self.enemy_combat = EnemyCombatManager(shared_state=self.shared_state)
        self.enemy_combat.initialize(self.config)
        # Add to shared state so players can access it for tactical prompts
        self.shared_state.enemy_combat = self.enemy_combat
        # Add session reference for round stats tracking
        self.shared_state.session = self
        if self.enemy_combat.enabled:
            print("✓ Enemy combat manager ENABLED")
        else:
            print("  Enemy combat manager disabled")

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
        logger.debug("Starting self-playing session")

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
        jsonl_logger = JSONLLogger(self.session_id, output_dir, config=self.config)

        # Attach logger to mechanics engine
        if self.shared_state and self.shared_state.mechanics_engine:
            self.shared_state.mechanics_engine.jsonl_logger = jsonl_logger
            print(f"✓ JSONL logging enabled: {jsonl_logger.log_file}")

        # Wait for DM to generate initial scenario before starting gameplay
        # SESSION_START triggers scenario generation, wait for SCENARIO_SETUP message
        print("Waiting for scenario generation...")
        await self._scenario_ready.wait()
        print("Scenario ready!")

        # Give players time to receive and process SCENARIO_SETUP message
        # before starting declarations (fixes race condition where enemies
        # declare before players see the scenario)
        print("Waiting for players to process scenario...")
        await asyncio.sleep(2)
        print("All agents ready to begin!")

        # Run the gameplay loop
        await self._run_gameplay_loop()
        
    async def _create_agents(self):
        """Create and start all AI agents."""
        agents_config = self.config.get('agents', {})
        
        # Create DM agent
        dm_config = agents_config.get('dm', {})
        dm_voice = self.voice_library.get_profile('ritual_scholar')

        # Pass force_scenario if present (for automated testing)
        force_scenario = self.config.get('force_scenario', None)

        dm_agent = AIDMAgent(
            agent_id='dm_01',
            socket_path=str(self.coordinator.message_bus.socket_path),
            llm_config=dm_config.get('llm', {}),
            voice_profile=dm_voice,
            shared_state=self.shared_state,
            prompt_enricher=self.voice_library.enrich_prompt,
            history_supplier=self._recent_history,
            force_scenario=force_scenario,
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
            logger.debug(f"Selected {party_size} players: {[p['name'] for p in selected_players]}")
        else:
            selected_players = players_config
            logger.debug(f"Using all {len(selected_players)} players from pool")

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
            # Populate player_agents in shared_state for ally buff targeting
            self.shared_state.player_agents = player_agents
            for player in player_agents:
                # Initialize soulcredit state with character's starting value
                initial_sc = getattr(player.character_state, 'soulcredit', 0)
                mechanics.get_soulcredit_state(player.agent_id, initial_score=initial_sc)
                logger.debug(f"Initialized {player.character_state.name} soulcredit: {initial_sc}")

                # Degrade Raw Seeds (1 cycle per session)
                if hasattr(player.character_state, 'energy_inventory') and player.character_state.energy_inventory:
                    player.character_state.energy_inventory.degrade_raw_seeds(cycles=1)
                    raw_count = player.character_state.energy_inventory.count_seeds(SeedType.RAW)
                    hollow_count = player.character_state.energy_inventory.count_seeds(SeedType.HOLLOW)
                    if hollow_count > 0:
                        logger.debug(f"{player.character_state.name}: Raw Seeds degraded (now {raw_count} Raw, {hollow_count} Hollow)")

        logger.debug(f"Created {len(self.agents)} agents")
        
    async def _wait_for_agents_ready(self):
        """Wait for all agents to signal readiness."""
        # Simple wait - you could enhance with proper synchronization
        await asyncio.sleep(2)
        logger.debug("All agents ready")
        
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
            combat_continues = await self._run_initiative_round()

            # Check if all players defeated (TPK)
            if not combat_continues:
                print("\n=== SESSION ENDED - TOTAL PARTY KILL ===")
                break

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
        
    async def _run_initiative_round(self) -> bool:
        """
        Run a round with proper tactical flow:
        1. Declaration phase (slowest → fastest)
        2. Resolution phase (fastest → slowest)
        3. DM describes overall outcome

        Returns:
            bool: True if combat should continue, False if all players defeated
        """
        # Filter to alive players only (YAGS defeat mechanics)
        player_agents = [agent for agent in self.agents
                        if isinstance(agent, AIPlayerAgent) and agent.is_alive]

        if not player_agents:
            logger.warning("All players defeated - combat should end")
            print("\n💀 All players defeated - TPK (Total Party Kill)!")
            return False  # Signal that combat cannot continue

        # Calculate initiative for each player (Agility × 4 + d20)
        initiative_order = []
        mechanics = self.shared_state.get_mechanics_engine()

        for player_agent in player_agents:
            # Get player's Agility attribute
            agility = player_agent.character_state.attributes.get('Agility', 3)
            initiative = mechanics.calculate_initiative(agility)
            initiative_order.append((initiative, 'player', player_agent))

            # Display with position if available
            position_str = f" ({player_agent.position})" if hasattr(player_agent, 'position') else ""
            print(f"[{player_agent.character_state.name}] Initiative: {initiative}{position_str}")

        # Add enemy initiative entries
        if self.enemy_combat.enabled:
            enemy_entries = self.enemy_combat.get_initiative_entries()
            for init, enemy in enemy_entries:
                initiative_order.append((init, 'enemy', enemy))
                print(f"[{enemy.name}] (ENEMY) Initiative: {init} ({enemy.position})")

        # Sort by initiative (highest first)
        initiative_order.sort(key=lambda x: x[0], reverse=True)

        # Display comprehensive round status
        self._display_round_status(initiative_order, mechanics, player_agents)

        # PHASE 1: DECLARATIONS (slowest → fastest, so faster players can react)
        print("\n=== Declaration Phase ===")
        self._in_declaration_phase = True
        self._declared_actions.clear()

        # Log declaration phase start
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_declaration_phase_start(mechanics.current_round)

        # Prepare LLM client for enemy declarations (if needed)
        llm_client = None
        available_tokens = []
        if self.enemy_combat.enabled and len(self.enemy_combat.enemy_agents) > 0:
            # Get available tactical tokens (if mechanics tracks them)
            if mechanics and hasattr(mechanics, 'get_unclaimed_tokens'):
                available_tokens = mechanics.get_unclaimed_tokens()

            # Get DM's LLM config for enemy prompts
            dm_agents = [a for a in self.agents if isinstance(a, AIDMAgent)]
            if dm_agents:
                dm_agent = dm_agents[0]

                # Create a simple wrapper for the DM's LLM functionality
                class DMLLMClient:
                    def __init__(self, llm_config):
                        self.llm_config = llm_config

                    async def generate_async(self, prompt: str, temperature: float = 0.7, max_tokens: int = 500):
                        provider = self.llm_config.get('provider', 'anthropic')
                        model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

                        if provider == 'anthropic':
                            import anthropic
                            import os
                            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                            response = client.messages.create(
                                model=model,
                                max_tokens=max_tokens,
                                temperature=temperature,
                                messages=[{"role": "user", "content": prompt}]
                            )
                            return {"content": response.content[0].text}
                        else:
                            raise NotImplementedError(f"Provider {provider} not supported for enemy declarations")

                llm_client = DMLLMClient(dm_agent.llm_config)

        # Declaration loop (slowest → fastest, reversed initiative order)
        for initiative_score, agent_type, agent in reversed(initiative_order):
            if agent_type == 'player':
                # Skip dead/unconscious players
                if not agent.is_alive:
                    print(f"\n[{agent.character_state.name}] is unconscious/defeated - cannot declare actions")
                    continue

                print(f"\n[{agent.character_state.name}] declaring (initiative {initiative_score})...")

                # Create event to track when this player's declaration arrives
                declaration_event = asyncio.Event()
                self._pending_declarations[agent.agent_id] = declaration_event

                turn_message = Message(
                    id=f"turn_{datetime.now().isoformat()}_{agent.agent_id}",
                    type=MessageType.TURN_REQUEST,
                    sender='coordinator',
                    recipient=agent.agent_id,
                    payload={'phase': 'declaration', 'initiative': initiative_score},
                    timestamp=datetime.now()
                )

                await self.coordinator.message_bus._route_message(turn_message)

                # Wait for this player's declaration to be buffered
                await declaration_event.wait()
                logger.debug(f"{agent.character_state.name} declaration received")

                # Clean up the event
                if agent.agent_id in self._pending_declarations:
                    del self._pending_declarations[agent.agent_id]

            elif agent_type == 'enemy':
                # Enemy declares inline (interleaved with PCs)
                if llm_client:
                    print(f"\n[{agent.name}] declaring (initiative {initiative_score})...")

                    declaration = await self.enemy_combat.declare_single_enemy(
                        enemy=agent,
                        player_agents=player_agents,
                        available_tokens=available_tokens,
                        llm_client=llm_client
                    )

                    # Log enemy declaration
                    if declaration and mechanics and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_action_declaration(
                            player_id=declaration['agent_id'],
                            character_name=declaration['character_name'],
                            initiative=declaration['initiative'],
                            action={'major_action': declaration['major_action'], 'target': declaration.get('target')},
                            round_num=mechanics.current_round
                        )

        self._in_declaration_phase = False

        # PHASE 2: RESOLUTION (execute in descending initiative order)
        print("\n=== Resolution Phase ===")
        logger.debug(f"Declared actions at resolution start: {list(self._declared_actions.keys())}")

        # Create resolution state tracker for declare/resolve cycle
        resolution_state = ResolutionState()

        # Collect all resolutions for synthesis at the end
        all_resolutions = []

        # Execute actions in initiative order (highest first)
        for initiative_score, agent_type, agent in initiative_order:
            logger.debug(f"Processing {agent_type} with initiative {initiative_score}")
            if agent_type == 'player':
                # Skip dead/unconscious players
                if not agent.is_alive:
                    logger.debug(f"{agent.character_state.name} is dead/unconscious - skipping execution")
                    continue

                # PC action execution via DM adjudication
                # Process ALL buffered actions for this agent (supports free action system)
                if agent.agent_id in self._declared_actions:
                    buffered_actions = self._declared_actions[agent.agent_id]

                    print(f"\n[{agent.character_state.name}] executing action...")

                    # Process each action in order (free action first, then main action)
                    for idx, buffered_action in enumerate(buffered_actions):
                        action_label = "FREE ACTION" if buffered_action['action'].get('is_free_action') else f"ACTION {idx+1}"
                        logger.debug(f"Processing {action_label} for {agent.character_state.name}")

                        # Apply position change NOW (execution phase) if declared
                        target_position = buffered_action['action'].get('target_position')
                        if target_position:
                            old_position = agent.position
                            # Validate: don't move to same position (bug fix)
                            if old_position == target_position:
                                logger.warning(f"{agent.character_state.name} tried to move to same position: {old_position}. Skipping movement.")
                                print(f"[{agent.character_state.name}] Position unchanged: {old_position} (invalid move)")
                            else:
                                agent.position = target_position
                                print(f"[{agent.character_state.name}] Position: {old_position} → {agent.position}")
                                logger.info(f"{agent.character_state.name} moved from {old_position} to {agent.position}")

                        # Build single action for DM adjudication
                        action_for_adjudication = {
                            'player_id': agent.agent_id,
                            'character_name': agent.character_state.name,
                            'initiative': initiative_score,
                            'action': buffered_action['action']
                        }

                        # Create event to track when this adjudication completes
                        adjudication_event = asyncio.Event()
                        self._pending_resolutions[f"{agent.agent_id}_{idx}"] = adjudication_event

                        # Send action to DM for mechanical resolution (no synthesis yet)
                        adjudication_message = Message(
                            id=f"adjudicate_{datetime.now().isoformat()}_{agent.agent_id}_{idx}",
                            type=MessageType.ACTION_DECLARED,
                            sender='coordinator',
                            recipient='dm_01',
                            payload={
                                'phase': 'resolution_only',  # Resolve mechanically but don't synthesize yet
                                'actions': [action_for_adjudication],
                                'round': mechanics.current_round if mechanics else 0,
                                'action_index': idx  # Track which action this is for multi-action turns
                            },
                            timestamp=datetime.now()
                        )

                        await self.coordinator.message_bus._route_message(adjudication_message)

                        # Wait for DM to complete adjudication
                        await adjudication_event.wait()
                        logger.debug(f"{agent.character_state.name} {action_label} adjudicated")

                        # Clean up and collect resolution for synthesis
                        # Get the resolution data that was stored when ACTION_RESOLVED was received
                        resolution_data = getattr(adjudication_event, 'resolution_data', None)
                        if resolution_data:
                            all_resolutions.append(resolution_data)

                        if f"{agent.agent_id}_{idx}" in self._pending_resolutions:
                            del self._pending_resolutions[f"{agent.agent_id}_{idx}"]

                        # TODO: Update resolution_state based on PC action results
                        # (Would need to parse DM adjudication results for defeated targets, claimed tokens, etc.)

            elif agent_type == 'enemy':
                # Enemy action execution with resolution state tracking
                if self.enemy_combat.enabled:
                    result = self.enemy_combat.execute_enemy_action(
                        enemy_id=agent.agent_id,
                        player_agents=player_agents,
                        mechanics_engine=mechanics,
                        resolution_state=resolution_state
                    )

                    if result:
                        # Check if action was invalidated
                        if result.get('result') == 'invalidated':
                            print(f"\n⚠️  {result['narration']}")
                        else:
                            print(f"\n[{result['character_name']}] {result['narration']}")

                        # TODO: Enemy action logging
                        # Enemy actions use a simplified result dict that doesn't match
                        # the ActionResolution schema. Consider implementing enemy-specific
                        # logging or adapting the result format.

        # Generate single synthesis from all collected resolutions
        if all_resolutions:
            print("\n=== Generating Round Synthesis ===")
            logger.debug(f"Sending {len(all_resolutions)} resolutions to DM for synthesis")

            # Reset synthesis event before requesting synthesis
            self._synthesis_complete.clear()

            synthesis_message = Message(
                id=f"synthesis_{datetime.now().isoformat()}",
                type=MessageType.ACTION_DECLARED,
                sender='coordinator',
                recipient='dm_01',
                payload={
                    'phase': 'synthesis',
                    'resolutions': all_resolutions,
                    'round': mechanics.current_round if mechanics else 0
                },
                timestamp=datetime.now()
            )

            await self.coordinator.message_bus._route_message(synthesis_message)

            # Wait for DM to complete and broadcast synthesis
            await self._synthesis_complete.wait()
            logger.debug("Round synthesis complete")

        # PHASE 3: CLEANUP
        if self.enemy_combat.enabled:
            print("\n=== Cleanup Phase ===")
            cleanup_events = self.enemy_combat.cleanup_round()

            for event in cleanup_events:
                print(f"[CLEANUP] {event['narration']}")

                if mechanics and mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        event_type=event['type'],
                        data=event,
                        round_num=mechanics.current_round
                    )

            # Tick player buffs (reduce durations, remove expired)
            player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
            for player in player_agents:
                if hasattr(player, 'tick_buffs'):
                    player.tick_buffs()

            # Log character state snapshots for all players (for ML training/balance analysis)
            if mechanics and mechanics.jsonl_logger:
                for player in player_agents:
                    if hasattr(player, 'character_state'):
                        char_state = player.character_state
                        # Health/wounds are stored on player agent, not CharacterState
                        mechanics.jsonl_logger.log_character_state(
                            round_num=mechanics.current_round,
                            character_id=player.agent_id,
                            character_name=char_state.name,
                            health=player.health if hasattr(player, 'health') else 0,
                            max_health=player.max_health if hasattr(player, 'max_health') else 0,
                            wounds=player.wounds if hasattr(player, 'wounds') else 0,
                            void_score=char_state.void_score if hasattr(char_state, 'void_score') else 0,
                            soulcredit=char_state.soulcredit if hasattr(char_state, 'soulcredit') else 0,
                            position=str(getattr(player, 'position', 'Unknown')),
                            conditions=[],  # TODO: Add condition tracking
                            is_defeated=(player.health <= 0) if hasattr(player, 'health') else False
                        )

                # Log round summary for balance analysis
                active_enemy_count = len([e for e in self.enemy_combat.enemy_agents if e.health > 0]) if self.enemy_combat.enabled else 0
                player_wounds_total = sum(player.wounds for player in player_agents if hasattr(player, 'wounds'))

                # Compute clocks advanced/filled from clock states
                clocks_advanced = 0
                clocks_filled = 0
                if mechanics.scene_clocks:
                    for clock in mechanics.scene_clocks.values():
                        if clock.current > 0:
                            clocks_advanced += 1
                        if clock.filled:
                            clocks_filled += 1

                round_summary = {
                    'actions_attempted': self._round_stats['actions_attempted'],
                    'success_count': self._round_stats['success_count'],
                    'success_rate': (self._round_stats['success_count'] / self._round_stats['actions_attempted']) if self._round_stats['actions_attempted'] > 0 else 0.0,
                    'avg_margin': (self._round_stats['total_margin'] / self._round_stats['actions_attempted']) if self._round_stats['actions_attempted'] > 0 else 0.0,
                    'damage_dealt_by_players': self._round_stats['damage_dealt_by_players'],
                    'damage_taken_by_players': self._round_stats['damage_taken_by_players'],
                    'void_gained': self._round_stats['void_gained'],
                    'void_lost': self._round_stats['void_lost'],
                    'clocks_advanced': clocks_advanced,
                    'clocks_filled': clocks_filled,
                    'active_enemies': active_enemy_count,
                    'player_wounds_total': player_wounds_total
                }

                mechanics.jsonl_logger.log_round_summary(
                    round_num=mechanics.current_round,
                    summary=round_summary
                )

                # Reset round stats for next round
                self._round_stats = {
                    'actions_attempted': 0,
                    'success_count': 0,
                    'total_margin': 0,
                    'damage_dealt_by_players': 0,
                    'damage_taken_by_players': 0,
                    'void_gained': 0,
                    'void_lost': 0,
                    'clocks_advanced': 0,
                    'clocks_filled': 0
                }

            # Check if all clocks are complete and trigger story advancement
            await self._check_and_trigger_story_advancement()

        # Clear the action buffer for next round
        self._declared_actions.clear()

        # Reset free action slots for all players
        for agent in self.agents:
            if hasattr(agent, 'free_action_used'):
                agent.free_action_used = False

        return True  # Combat continues

    def track_action_resolution(self, success: bool, margin: int):
        """Track action resolution for round summary statistics."""
        self._round_stats['actions_attempted'] += 1
        if success:
            self._round_stats['success_count'] += 1
        self._round_stats['total_margin'] += margin

    def track_player_damage_dealt(self, damage: int):
        """Track damage dealt by players for round summary."""
        self._round_stats['damage_dealt_by_players'] += damage

    def track_player_damage_taken(self, damage: int):
        """Track damage taken by players for round summary."""
        self._round_stats['damage_taken_by_players'] += damage

    def track_void_change(self, delta: int):
        """Track void score changes for round summary."""
        if delta > 0:
            self._round_stats['void_gained'] += delta
        elif delta < 0:
            self._round_stats['void_lost'] += abs(delta)

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

                # Check if player is dead and modify prompt accordingly
                is_dead = not player.is_alive if hasattr(player, 'is_alive') else False
                wounds = player.wounds if hasattr(player, 'wounds') else 0

                if is_dead:
                    # Dead player - give dying words
                    debrief_prompt = f"""You are {player.character_state.name} ({player.character_state.faction}) giving your FINAL WORDS before dying.

**You are DEAD.** You took {wounds} fatal wounds and failed your death save. You are bleeding out, taking your last breaths.

**Mission Context:**
{scenario_situation}

**Your Faction**: {player.character_state.faction}
**Your Goals (unfulfilled)**: {', '.join(player.character_state.goals)}
{conversation_so_far}

Provide a brief (1-2 sentence) dying statement in character voice:
- Final words, regrets, or defiant last stand
- Something meaningful to say before you die
- Keep it dramatic but not melodramatic

Examples: "Tell... tell them the truth about..." or "Not like this... *coughs blood* not like this..." or "I die as I lived - fighting the void"

Keep it brief and impactful. You're dying."""
                else:
                    # Alive player - normal debrief
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

                # Add death marker for dead players
                if is_dead:
                    print(f"💀 [{player.character_state.name}] (DYING) {debrief_text}\n")
                else:
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

    def _display_round_status(self, initiative_order: List[tuple], mechanics, player_agents: List):
        """Display comprehensive round status with initiative, health, and position."""
        print("\n=== Round Status ===")

        # Group combatants by type
        pcs = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'player']
        enemies = [(init, agent) for init, agent_type, agent in initiative_order if agent_type == 'enemy']

        # Display PCs
        if pcs:
            print("\n  Player Characters:")
            for init, agent in pcs:
                # Get health info from agent's combat attributes (initialized from Size × 2)
                current_health = getattr(agent, 'health', 0)
                max_health = getattr(agent, 'max_health', 0)
                health_str = f"{current_health}/{max_health} HP"

                # Get position
                position = getattr(agent, 'position', 'Unknown')
                position_str = str(position) if position != 'Unknown' else 'Unknown'

                # Get void score
                void_score = getattr(agent.character_state, 'void_score', 0)
                void_str = f"Void {void_score}/10"

                print(f"    [{init:2d}] {agent.character_state.name:20s} | {health_str:12s} | {position_str:15s} | {void_str}")

                # Display equipped weapons (always show)
                if hasattr(agent, 'equipped_weapons'):
                    weapon_items = []
                    if agent.equipped_weapons.get('primary'):
                        wpn = agent.equipped_weapons['primary']
                        weapon_items.append(f"{wpn.name} [{wpn.damage_type.upper()}]")
                    if agent.equipped_weapons.get('sidearm'):
                        wpn = agent.equipped_weapons['sidearm']
                        weapon_items.append(f"{wpn.name} [{wpn.damage_type.upper()}]")

                    if weapon_items:
                        weapon_str = " | ".join(weapon_items)
                        print(f"         └─ Equipped: {weapon_str}")

                    # Show carried weapons if any
                    if hasattr(agent, 'weapon_inventory') and agent.weapon_inventory:
                        carried_items = [f"{w.name} [{w.damage_type.upper()}]" for w in agent.weapon_inventory[:2]]  # Show first 2
                        if carried_items:
                            carried_str = " | ".join(carried_items)
                            print(f"         └─ Carried: {carried_str}")

                # Display key inventory items (offerings, seeds, currency)
                inventory_items = []
                if hasattr(agent.character_state, 'inventory') and agent.character_state.inventory:
                    inv = agent.character_state.inventory

                    # Ritual offerings
                    if inv.get('blood_offering', 0) > 0:
                        inventory_items.append(f"Blood:{inv['blood_offering']}")
                    if inv.get('incense', 0) > 0:
                        inventory_items.append(f"Incense:{inv['incense']}")
                    if inv.get('crystal_focus', 0) > 0:
                        inventory_items.append(f"Crystal:{inv['crystal_focus']}")

                    # Show first 3 items to keep it compact
                    if inventory_items:
                        inv_str = " | ".join(inventory_items[:3])
                        print(f"         └─ Inventory: {inv_str}")

                # Display energy/seeds if available
                if hasattr(agent.character_state, 'energy_inventory') and agent.character_state.energy_inventory:
                    energy_inv = agent.character_state.energy_inventory
                    energy_items = []

                    # Seeds
                    seeds = getattr(energy_inv, 'seed_counts', {})
                    if seeds.get('attuned', 0) > 0:
                        energy_items.append(f"Attuned Seeds:{seeds['attuned']}")
                    if seeds.get('raw', 0) > 0:
                        energy_items.append(f"Raw Seeds:{seeds['raw']}")
                    if seeds.get('hollow', 0) > 0:
                        energy_items.append(f"Hollow:{seeds['hollow']}")

                    # Currency (show highest denomination available)
                    currency = getattr(energy_inv, 'currencies', {})
                    if currency.get('spark', 0) > 0:
                        energy_items.append(f"Sparks:{currency['spark']}")
                    elif currency.get('grain', 0) > 0:
                        energy_items.append(f"Grains:{currency['grain']}")
                    elif currency.get('drip', 0) > 0:
                        energy_items.append(f"Drips:{currency['drip']}")

                    if energy_items:
                        energy_str = " | ".join(energy_items[:3])
                        print(f"         └─ Resources: {energy_str}")

        # Display Enemies
        if enemies:
            print("\n  Enemies:")
            for init, agent in enemies:
                # Get health info
                health = getattr(agent, 'health', '?')
                max_health = getattr(agent, 'max_health', '?')
                health_str = f"{health}/{max_health} HP"

                # Get position
                position = getattr(agent, 'position', 'Unknown')
                position_str = str(position) if position != 'Unknown' else 'Unknown'

                # Get group count if available
                unit_count = getattr(agent, 'unit_count', 1)
                count_str = f" (×{unit_count})" if unit_count > 1 else ""

                print(f"    [{init:2d}] {agent.name:20s}{count_str:6s} | {health_str:12s} | {position_str:15s}")

        # Display clock states if available
        if mechanics and mechanics.scene_clocks:
            print("\n  Scene Clocks:")
            for name, clock in mechanics.scene_clocks.items():
                status = f"{clock.current}/{clock.maximum}"
                filled_str = " [FILLED]" if clock.filled else ""
                print(f"    • {name}: {status}{filled_str}")

        print()

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

    async def _check_and_trigger_story_advancement(self):
        """Check if all clocks are complete and trigger DM to advance the story."""
        if not self.shared_state:
            return

        mechanics = self.shared_state.get_mechanics_engine()
        if not mechanics:
            return

        # Track if we currently have clocks
        if mechanics.scene_clocks and len(mechanics.scene_clocks) > 0:
            self._had_active_clocks = True

        # Count active (non-filled) clocks
        active_clocks = [clock for clock in mechanics.scene_clocks.values() if not clock.filled] if mechanics.scene_clocks else []

        # Trigger story advancement if:
        # 1. We previously had clocks AND
        # 2. Now all clocks are gone (expired/filled/archived) OR all remaining clocks are filled
        should_advance = self._had_active_clocks and len(active_clocks) == 0

        if should_advance:
            logger.info("All clocks complete/expired - triggering story advancement")
            print("\n⏰ All scenario objectives complete - Story will advance to new location/situation")

            # Set flag on DM agent to trigger story advancement
            dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
            if dm_agents:
                dm_agent = dm_agents[0]
                dm_agent.needs_story_advancement = True
                logger.info(f"Set needs_story_advancement=True on DM {dm_agent.agent_id}")

            # Reset flag so we don't trigger again until new clocks appear
            self._had_active_clocks = False

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

        logger.debug("All agents shutdown")

    def _recent_history(self) -> List[str]:
        """Return a small slice of recent turn history for prompt context."""
        return self._turn_history[-5:]

    def _handle_scenario_setup(self, message: Message):
        """Track when scenario is ready and process initial enemy spawns."""
        if message.type != MessageType.SCENARIO_SETUP:
            return

        # Display scenario once (instead of each player printing it)
        scenario = message.payload.get('scenario', {})
        opening_narration = message.payload.get('opening_narration', '')

        print(f"\n=== New Scenario ===")
        print(f"Theme: {scenario.get('theme', 'Unknown')}")
        print(f"Location: {scenario.get('location', 'Unknown')}")
        print(f"\nDM: {opening_narration}")

        # Process enemy spawn markers from opening narration
        if opening_narration and self.enemy_combat.enabled:
            spawn_notifications = self.enemy_combat.process_dm_narration(opening_narration)
            for notification in spawn_notifications:
                print(f"\n{notification}")

        self._scenario_ready.set()

    def _handle_action_declared(self, message: Message):
        """Buffer ACTION_DECLARED messages during declaration phase."""
        if message.type != MessageType.ACTION_DECLARED:
            return

        # Only buffer during declaration phase
        if not self._in_declaration_phase:
            return

        # Buffer the action (supports multiple actions per agent for free action system)
        # Note: message.payload IS the action dict (not nested under 'action' key)
        agent_id = message.sender

        # Initialize list if this is the first action from this agent
        if agent_id not in self._declared_actions:
            self._declared_actions[agent_id] = []

        # Append this action to the agent's action list
        self._declared_actions[agent_id].append({
            'agent_id': agent_id,
            'action': message.payload,  # Payload IS the action
            'timestamp': message.timestamp
        })
        logger.debug(f"Buffered action from {agent_id} (total: {len(self._declared_actions[agent_id])} actions)")

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
        action_index = message.payload.get('action_index', 0)  # Default to 0 for backward compatibility

        # Build the event key (must match the key used when storing the event)
        event_key = f"{agent_id}_{action_index}"

        if event_key in self._pending_resolutions:
            # Store resolution data on the event for later collection
            event = self._pending_resolutions[event_key]
            event.resolution_data = message.payload.get('resolution_data')
            # Signal that this agent's resolution/adjudication is complete
            event.set()
            logger.debug(f"Resolution complete for {event_key}")
        elif agent_id in self._pending_resolutions:
            # Fallback for old-style keys (no index)
            event = self._pending_resolutions[agent_id]
            event.resolution_data = message.payload.get('resolution_data')
            event.set()
            logger.debug(f"Resolution complete for {agent_id} (legacy)")

    def _handle_dm_narration(self, message: Message):
        """Handle DM narration and check for control markers."""
        if message.type != MessageType.DM_NARRATION:
            return

        narration = message.payload.get('narration', '')
        self._last_dm_narration = narration

        # Check if this is a round synthesis completion
        if message.payload.get('is_round_synthesis', False):
            self._synthesis_complete.set()
            logger.debug("Round synthesis received, signaling completion")

            # Log round synthesis for narrative reconstruction
            mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
            round_num = message.payload.get('round', mechanics.current_round if mechanics else 0)
            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_synthesis(
                    round_num=round_num,
                    synthesis=narration
                )

        # Process enemy spawn/despawn markers
        if self.enemy_combat.enabled:
            spawn_notifications = self.enemy_combat.process_dm_narration(narration)
            for notification in spawn_notifications:
                print(f"\n{notification}")

        # Check for session end marker
        end_result = parse_session_end_marker(narration)
        if end_result['status'] != 'none':
            self._session_end_status = end_result['status']
            logger.info(f"DM declared session end: {end_result['status']}" +
                       (f" - {end_result['reason']}" if end_result['reason'] else ""))

        # Check for story advancement marker FIRST
        # (so we can clear old clocks before spawning new ones)
        advance_result = parse_advance_story_marker(narration)
        if advance_result['should_advance']:
            logger.info(f"DM requested story advancement: {advance_result['location']} - {advance_result['situation']}")

            # Clear ALL old clocks when story advances (fresh start)
            mechanics = self.shared_state.mechanics_engine
            if mechanics and mechanics.scene_clocks:
                archived_clocks = list(mechanics.scene_clocks.keys())
                mechanics.scene_clocks.clear()
                logger.info(f"🗑️  Cleared all old clocks for story advancement: {', '.join(archived_clocks)}")

                print(f"\n✨ STORY ADVANCES ✨")
                print(f"   New Location: {advance_result['location']}")
                print(f"   Situation: {advance_result['situation']}")
                if archived_clocks:
                    print(f"   Previous clocks cleared: {', '.join(archived_clocks)}")

            # Notify all players of the story advancement
            advance_narration = f"Story advances to: {advance_result['location']}\n{advance_result['situation']}"
            advance_message = Message(
                id=f"advance_{datetime.now().isoformat()}",
                type=MessageType.SCENARIO_UPDATE,
                sender='coordinator',
                recipient=None,  # Broadcast to all
                payload={
                    'new_location': advance_result['location'],
                    'new_situation': advance_result['situation'],
                    'advance_narration': advance_narration,
                    'story_advanced': True
                },
                timestamp=datetime.now()
            )
            import asyncio
            asyncio.create_task(self.coordinator.message_bus._route_message(advance_message))

            # Store advancement for DM to use in generating next scenario
            dm_agents = [agent for agent in self.agents if isinstance(agent, AIDMAgent)]
            if dm_agents:
                dm_agents[0].current_location = advance_result['location']
                dm_agents[0].pending_scenario_pivot = advance_result['situation']

        # Check for new clock markers (spawned AFTER clearing for story advancement)
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
            pivot_message = Message(
                id=f"pivot_{datetime.now().isoformat()}",
                type=MessageType.SCENARIO_UPDATE,
                sender='coordinator',
                recipient=None,  # Broadcast to all
                payload={
                    'new_theme': pivot_result['new_theme'],
                    'new_situation': pivot_narration,
                    'pivot_narration': pivot_narration
                },
                timestamp=datetime.now()
            )
            # Note: This is async context, but we can't await here in a non-async handler
            # The message will be queued for delivery
            import asyncio
            asyncio.create_task(self.coordinator.message_bus._route_message(pivot_message))

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