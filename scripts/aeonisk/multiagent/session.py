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

        # Initialize mechanics systems
        print("Initializing mechanics systems...")
        self.shared_state.initialize_mechanics()
        print("✓ Mechanics engine ready")
        print("✓ Action validator ready")
        print("✓ Knowledge retrieval ready")
        
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

        # Create player agents
        players_config = agents_config.get('players', [])
        assignments = self.voice_library.assign_to_agents(
            [f'player_{i+1:02d}' for i in range(len(players_config))]
        )
        for i, player_config in enumerate(players_config):
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

        while self.running and round_count < max_rounds:
            round_count += 1
            print(f"\n--- Round {round_count} ---")
            self._turn_history.append(f"Round {round_count} begins")

            # Reset void caps for all characters at round start
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                for agent_id, void_state in mechanics.void_states.items():
                    void_state.reset_round_void()

            # Run round with initiative-based turns
            await self._run_initiative_round()

            # Run DM turn at end of round
            await self._run_dm_turn()

            # Check for session end conditions
            if await self._check_end_conditions():
                break

            # Brief pause between rounds
            await asyncio.sleep(1)

        await self._end_session()
        
    async def _run_initiative_round(self):
        """Run a round with all players acting in initiative order."""
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

        # Players act in initiative order
        for initiative_score, player_agent in initiative_order:
            print(f"\n[{player_agent.character_state.name}]'s turn (initiative {initiative_score})")

            turn_message = Message(
                id=f"turn_{datetime.now().isoformat()}_{player_agent.agent_id}",
                type=MessageType.TURN_REQUEST,
                sender='coordinator',
                recipient=player_agent.agent_id,
                payload={'phase': 'player_action', 'initiative': initiative_score},
                timestamp=datetime.now()
            )

            await self.coordinator.message_bus._route_message(turn_message)

            # Wait for this player to complete their action
            await asyncio.sleep(3)
        
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
        
    async def _check_end_conditions(self) -> bool:
        """Check if session should end."""
        # Simple end conditions - enhance as needed
        session_data = self.coordinator.get_session_data()
        
        # End if no activity for several turns
        if len(session_data) == 0:
            return False
            
        # Add more sophisticated end conditions here
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

            # Print void states
            if state_summary.get('void_states'):
                print("\nVoid States:")
                for agent_id, void_info in state_summary['void_states'].items():
                    print(f"  {agent_id}: {void_info['score']}/10 ({void_info['level']})")

            print("=" * 40)

        # Collect final session data
        final_data = {
            'session_id': self.session_id,
            'config': self.config,
            'turns': self.coordinator.get_session_data(),
            'end_time': datetime.now().isoformat(),
            'shared_state': self.shared_state.snapshot(),
            'voice_profiles': [profile.as_dict() for profile in self.voice_library.all_profiles()],
        }

        # Save session data
        await self._save_session_data(final_data)
        
        # Shutdown all agents
        await self._shutdown_agents()
        
        self.running = False
        
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