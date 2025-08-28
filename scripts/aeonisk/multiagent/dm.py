"""
AI Dungeon Master agent for multi-agent self-playing system.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import Agent, Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class Scenario:
    """Current game scenario state."""
    theme: str
    location: str
    situation: str
    active_npcs: List[str]
    environmental_factors: List[str]
    void_level: int


class AIDMAgent(Agent):
    """
    AI Dungeon Master agent that orchestrates scenarios, controls NPCs,
    and drives narrative forward.
    """
    
    def __init__(self, agent_id: str, socket_path: str, llm_config: Dict[str, Any]):
        super().__init__(agent_id, socket_path)
        self.llm_config = llm_config
        self.current_scenario: Optional[Scenario] = None
        self.human_controlled = False
        self.human_input_queue = asyncio.Queue()
        
        # Set up DM-specific message handlers
        self.message_handlers[MessageType.SESSION_START] = self._handle_session_start
        self.message_handlers[MessageType.ACTION_DECLARED] = self._handle_action_declared
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        
        # Human override handlers
        self.message_handlers[MessageType.PING] = self._handle_human_override_request
        
    async def on_start(self):
        """Initialize DM agent."""
        logger.info(f"AI DM {self.agent_id} started")
        
        # Announce readiness
        self.send_message_sync(
            MessageType.AGENT_READY,
            None,  # broadcast
            {'agent_type': 'dm', 'capabilities': ['scenario_generation', 'npc_control', 'narrative']}
        )
        
        if not self.human_controlled:
            print(f"\n[DM {self.agent_id}] AI Dungeon Master ready")
            print("Type 'take_control' to switch to human control")
        
    async def on_shutdown(self):
        """Cleanup on shutdown."""
        logger.info(f"AI DM {self.agent_id} shutting down")
        
    async def _handle_session_start(self, message: Message):
        """Handle session start - generate initial scenario."""
        config = message.payload.get('config', {})
        
        if self.human_controlled:
            await self._request_human_scenario(config)
        else:
            await self._generate_ai_scenario(config)
            
    async def _generate_ai_scenario(self, config: Dict[str, Any]):
        """Generate scenario using AI."""
        # Use existing scenario seeds from your codebase
        from ...game.aiDM import SCENARIO_SEEDS
        import random
        
        seed = random.choice(SCENARIO_SEEDS)
        
        scenario = Scenario(
            theme=seed['theme'],
            location=seed['location'],
            situation=f"The situation involves {random.choice(seed['conflicts'])}",
            active_npcs=[],
            environmental_factors=seed.get('voidThreats', [])[:2],
            void_level=config.get('void_influence', 3)
        )
        
        self.current_scenario = scenario
        
        # Broadcast scenario setup
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,  # broadcast
            {
                'scenario': {
                    'theme': scenario.theme,
                    'location': scenario.location,
                    'situation': scenario.situation,
                    'void_level': scenario.void_level
                },
                'opening_narration': self._generate_opening_narration(scenario)
            }
        )
        
        print(f"\n[DM {self.agent_id}] Generated scenario: {scenario.theme}")
        print(f"Location: {scenario.location}")
        print(f"Situation: {scenario.situation}")
        
    async def _request_human_scenario(self, config: Dict[str, Any]):
        """Request scenario from human DM."""
        print(f"\n[HUMAN DM {self.agent_id}] Please describe the opening scenario:")
        print("Theme: ", end='')
        theme = (await asyncio.get_event_loop().run_in_executor(None, input)).strip()
        
        print("Location: ", end='')
        location = (await asyncio.get_event_loop().run_in_executor(None, input)).strip()
        
        print("Situation: ", end='')
        situation = (await asyncio.get_event_loop().run_in_executor(None, input)).strip()
        
        try:
            void_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "Void influence level (0-10): "
            )
            void_level = int(void_input.strip() or "3")
        except ValueError:
            void_level = 3
            print("Invalid input, using default void level 3")
        
        scenario = Scenario(
            theme=theme,
            location=location, 
            situation=situation,
            active_npcs=[],
            environmental_factors=[],
            void_level=void_level
        )
        
        self.current_scenario = scenario
        
        # Broadcast scenario
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,
            {
                'scenario': {
                    'theme': theme,
                    'location': location,
                    'situation': situation,
                    'void_level': void_level
                },
                'opening_narration': input("Opening narration: ").strip()
            }
        )
        
    def _generate_opening_narration(self, scenario: Scenario) -> str:
        """Generate opening narration for scenario."""
        return f"""
The party finds themselves at {scenario.location}. {scenario.situation}. 
The air carries a distinct tension, and you sense the void's influence at level {scenario.void_level}/10.
{' '.join(scenario.environmental_factors[:1])} looms as a potential threat.

What do you do?
        """.strip()
        
    async def _handle_action_declared(self, message: Message):
        """Handle player action declarations - respond as DM."""
        action = message.payload
        player_id = message.sender
        
        if self.human_controlled:
            await self._handle_human_dm_response(player_id, action)
        else:
            await self._handle_ai_dm_response(player_id, action)
            
    async def _handle_human_dm_response(self, player_id: str, action: Dict[str, Any]):
        """Handle action with human DM input."""
        print(f"\n[HUMAN DM] {player_id} declared action:")
        print(f"Action: {action.get('action_type', 'unknown')}")
        print(f"Description: {action.get('description', 'No description')}")
        
        print("\nYour response as DM:")
        dm_response = input().strip()
        
        # Ask for mechanical resolution if needed
        needs_roll = input("Does this require a dice roll? (y/n): ").lower().startswith('y')
        
        outcome = {
            'dm_response': dm_response,
            'success': True,  # Human determines
            'consequences': []
        }
        
        if needs_roll:
            print("Enter roll requirements (attribute+skill, difficulty):")
            roll_req = input().strip()
            outcome['roll_required'] = roll_req
            
        self.send_message_sync(
            MessageType.ACTION_RESOLVED,
            player_id,
            {
                'original_action': action,
                'outcome': outcome,
                'narration': dm_response
            }
        )
        
    async def _handle_ai_dm_response(self, player_id: str, action: Dict[str, Any]):
        """Handle action with AI DM logic."""
        # Simplified AI response - you can enhance this with your LLM integration
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        
        # Basic outcome determination
        success = True  # You can add dice rolling logic here
        
        response_templates = {
            'explore': f"You explore the area and discover...",
            'interact': f"Your interaction reveals...", 
            'ritual': f"You attempt the ritual and...",
            'combat': f"The combat unfolds as...",
            'default': f"Your action results in..."
        }
        
        template = response_templates.get(action_type, response_templates['default'])
        narration = f"{template} [AI DM response to {description}]"
        
        outcome = {
            'dm_response': narration,
            'success': success,
            'consequences': []
        }
        
        self.send_message_sync(
            MessageType.ACTION_RESOLVED,
            player_id,
            {
                'original_action': action,
                'outcome': outcome,
                'narration': narration
            }
        )
        
        print(f"[DM {self.agent_id}] Responded to {player_id}: {narration}")
        
    async def _handle_turn_request(self, message: Message):
        """Handle request for DM turn (narrative, NPC actions, etc.)."""
        if self.human_controlled:
            await self._human_dm_turn()
        else:
            await self._ai_dm_turn()
            
    async def _human_dm_turn(self):
        """Handle human DM turn."""
        print(f"\n[HUMAN DM {self.agent_id}] Your turn - describe what happens next:")
        narration = input().strip()
        
        if narration:
            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,  # broadcast
                {
                    'narration': narration,
                    'environmental_changes': [],
                    'npc_actions': []
                }
            )
        
    async def _ai_dm_turn(self):
        """Handle AI DM turn."""
        # Generate environmental/narrative progression
        narration = "The situation evolves... [AI DM narrative]"
        
        self.send_message_sync(
            MessageType.DM_NARRATION,
            None,
            {
                'narration': narration,
                'environmental_changes': [],
                'npc_actions': []
            }
        )
        
        print(f"[DM {self.agent_id}] Narrative: {narration}")
        
    async def _handle_human_override_request(self, message: Message):
        """Handle requests to switch between AI/human control."""
        if message.payload.get('command') == 'take_control' and message.sender == 'human':
            self.human_controlled = True
            print(f"[HUMAN DM {self.agent_id}] You now control the DM")
            
        elif message.payload.get('command') == 'release_control' and message.sender == 'human':
            self.human_controlled = False
            print(f"[DM {self.agent_id}] Switched back to AI control")
            
    def toggle_human_control(self):
        """Toggle between human and AI control."""
        self.human_controlled = not self.human_controlled
        status = "HUMAN" if self.human_controlled else "AI"
        print(f"[{status} DM {self.agent_id}] Control switched to {status} mode")