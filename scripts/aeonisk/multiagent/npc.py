"""
AI NPC agent for multi-agent self-playing system.
"""

import asyncio
import logging
import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import Agent, Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class NPCState:
    """Current NPC state."""
    name: str
    faction: str
    role: str
    motivation: str
    relationships: Dict[str, str]  # character_name -> relationship_type
    active: bool = True


class AINPCAgent(Agent):
    """
    AI NPC agent that represents non-player characters controlled by the system.
    """
    
    def __init__(self, agent_id: str, socket_path: str, npc_config: Dict[str, Any]):
        super().__init__(agent_id, socket_path)
        self.npc_config = npc_config
        self.npc_state: Optional[NPCState] = None
        self.human_controlled = False
        
        # Set up NPC-specific message handlers
        self.message_handlers[MessageType.SCENARIO_SETUP] = self._handle_scenario_setup
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        self.message_handlers[MessageType.NPC_DIALOGUE] = self._handle_dialogue_request
        
    async def on_start(self):
        """Initialize NPC agent."""
        self.npc_state = NPCState(
            name=self.npc_config.get('name', f'NPC_{self.agent_id}'),
            faction=self.npc_config.get('faction', 'Neutral'),
            role=self.npc_config.get('role', 'Civilian'),
            motivation=self.npc_config.get('motivation', 'Survive'),
            relationships=self.npc_config.get('relationships', {})
        )
        
        logger.info(f"NPC {self.agent_id} ({self.npc_state.name}) started")
        
        # Announce readiness
        self.send_message_sync(
            MessageType.AGENT_READY,
            None,
            {
                'agent_type': 'npc',
                'npc': {
                    'name': self.npc_state.name,
                    'faction': self.npc_state.faction,
                    'role': self.npc_state.role
                }
            }
        )
        
        print(f"[NPC {self.npc_state.name}] Ready ({self.npc_state.role} from {self.npc_state.faction})")
        
    async def on_shutdown(self):
        """Cleanup on shutdown."""
        logger.info(f"NPC {self.agent_id} shutting down")
        
    async def _handle_scenario_setup(self, message: Message):
        """Handle scenario setup - determine NPC involvement."""
        scenario = message.payload.get('scenario', {})
        
        # Simple logic to determine if NPC should be active in this scenario
        scenario_factions = scenario.get('factions', [])
        if self.npc_state.faction in scenario_factions or self.npc_state.faction == 'Neutral':
            self.npc_state.active = True
            print(f"[NPC {self.npc_state.name}] Active in scenario: {scenario.get('theme', 'Unknown')}")
        else:
            self.npc_state.active = False
            
    async def _handle_turn_request(self, message: Message):
        """Handle NPC turn - take action if active."""
        if not self.npc_state.active:
            return
            
        if self.human_controlled:
            await self._human_npc_turn()
        else:
            await self._ai_npc_turn()
            
    async def _human_npc_turn(self):
        """Handle human-controlled NPC turn."""
        print(f"\n[HUMAN NPC {self.npc_state.name}] Your turn as {self.npc_state.role}")
        print("What does this NPC do?")
        
        # Use asyncio-compatible input to avoid blocking event loop
        action_input = await asyncio.get_event_loop().run_in_executor(
            None, input, f"{self.npc_state.name}> "
        )
        action_input = action_input.strip()
        
        if action_input:
            self.send_message_sync(
                MessageType.NPC_DIALOGUE,
                None,  # broadcast
                {
                    'npc_name': self.npc_state.name,
                    'action': action_input,
                    'npc_type': self.npc_state.role
                }
            )
            
    async def _ai_npc_turn(self):
        """Handle AI-controlled NPC turn."""
        # Simple NPC behavior based on role and motivation
        actions = self._generate_npc_actions()
        
        if actions:
            chosen_action = random.choice(actions)
            
            self.send_message_sync(
                MessageType.NPC_DIALOGUE,
                None,
                {
                    'npc_name': self.npc_state.name,
                    'action': chosen_action,
                    'npc_type': self.npc_state.role,
                    'motivation': self.npc_state.motivation
                }
            )
            
            print(f"[NPC {self.npc_state.name}] {chosen_action}")
            
    def _generate_npc_actions(self) -> List[str]:
        """Generate possible NPC actions based on role and situation."""
        base_actions = []
        
        if self.npc_state.role == 'Guard':
            base_actions = [
                "maintains watchful position",
                "questions strangers about their business",
                "reports suspicious activity",
                "patrols the area"
            ]
        elif self.npc_state.role == 'Merchant':
            base_actions = [
                "offers goods for sale",
                "negotiates prices",
                "shares market gossip",
                "counts their soulcredit"
            ]
        elif self.npc_state.role == 'Scholar':
            base_actions = [
                "studies ancient texts",
                "shares knowledge about the void",
                "asks probing questions",
                "takes careful notes"
            ]
        elif self.npc_state.role == 'Civilian':
            base_actions = [
                "goes about their daily business",
                "shows concern about recent events",
                "gossips with others",
                "tries to avoid trouble"
            ]
        else:
            base_actions = [
                "observes the situation",
                "reacts to nearby events",
                "pursues their personal agenda"
            ]
            
        return base_actions
        
    async def _handle_dialogue_request(self, message: Message):
        """Handle requests for NPC dialogue/interaction."""
        if not self.npc_state.active:
            return
            
        # This could be enhanced to handle specific dialogue requests
        # For now, just acknowledge if addressed directly
        payload = message.payload
        if self.npc_state.name.lower() in str(payload).lower():
            response = f"[{self.npc_state.name}] responds to the interaction"
            print(response)
            
    def toggle_human_control(self):
        """Toggle between human and AI control."""
        self.human_controlled = not self.human_controlled
        status = "HUMAN" if self.human_controlled else "AI"
        print(f"[{status} NPC {self.npc_state.name}] Control switched to {status} mode")