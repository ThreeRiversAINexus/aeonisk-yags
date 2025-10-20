"""
AI Player agent for multi-agent self-playing system.
"""

import asyncio
import logging
import random
from typing import Dict, Any, List, Optional, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from .base import Agent, Message, MessageType
from .shared_state import SharedState
from .voice_profiles import VoiceProfile

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """Current character state."""
    name: str
    faction: str
    attributes: Dict[str, int]
    skills: Dict[str, int]
    void_score: int
    soulcredit: int
    bonds: List[str]
    goals: List[str]


class AIPlayerAgent(Agent):
    """
    AI Player agent that makes decisions based on character personality
    and goals, with option for human takeover.
    """
    
    def __init__(
        self,
        agent_id: str,
        socket_path: str,
        character_config: Dict[str, Any],
        *,
        voice_profile: Optional[VoiceProfile] = None,
        shared_state: Optional[SharedState] = None,
        prompt_enricher: Optional[Callable[..., str]] = None,
        history_supplier: Optional[Callable[[], Iterable[str]]] = None,
    ):
        super().__init__(agent_id, socket_path)
        self.character_config = character_config
        self.character_state: Optional[CharacterState] = None
        self.human_controlled = False
        self.personality = character_config.get('personality', {})
        self.current_scenario: Optional[Dict[str, Any]] = None
        self.voice_profile = voice_profile
        self.shared_state = shared_state
        self._prompt_enricher = prompt_enricher
        self._history_supplier = history_supplier

        # Set up player-specific message handlers
        self.message_handlers[MessageType.SCENARIO_SETUP] = self._handle_scenario_setup
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        self.message_handlers[MessageType.ACTION_RESOLVED] = self._handle_action_resolved
        self.message_handlers[MessageType.DM_NARRATION] = self._handle_dm_narration
        
    async def on_start(self):
        """Initialize player agent."""
        # Create character from config
        self.character_state = CharacterState(
            name=self.character_config.get('name', f'Player_{self.agent_id}'),
            faction=self.character_config.get('faction', 'Unaffiliated'),
            attributes=self.character_config.get('attributes', {}),
            skills=self.character_config.get('skills', {}),
            void_score=self.character_config.get('void_score', 0),
            soulcredit=self.character_config.get('soulcredit', 10),
            bonds=self.character_config.get('bonds', []),
            goals=self.character_config.get('goals', [])
        )
        
        logger.info(f"Player {self.agent_id} ({self.character_state.name}) started")
        
        # Announce readiness
        self.send_message_sync(
            MessageType.AGENT_READY,
            None,
            {
                'agent_type': 'player',
                'character': {
                    'name': self.character_state.name,
                    'faction': self.character_state.faction
                }
            }
        )
        
        print(f"\n[Player {self.character_state.name}] Ready to play")
        if not self.human_controlled:
            print("Type 'take_control' to switch to human control")
        
    async def on_shutdown(self):
        """Cleanup on shutdown."""
        logger.info(f"Player {self.agent_id} shutting down")
        
    async def _handle_scenario_setup(self, message: Message):
        """Handle scenario setup from DM."""
        self.current_scenario = message.payload.get('scenario', {})
        opening = message.payload.get('opening_narration', '')
        
        print(f"\n[{self.character_state.name}] === New Scenario ===")
        print(f"Theme: {self.current_scenario.get('theme', 'Unknown')}")
        print(f"Location: {self.current_scenario.get('location', 'Unknown')}")
        print(f"\nDM: {opening}")
        
        if self.human_controlled:
            print(f"\n[HUMAN - {self.character_state.name}] Waiting for your input...")
        
    async def _handle_turn_request(self, message: Message):
        """Handle turn request - decide on action."""
        if self.human_controlled:
            await self._human_player_turn()
        else:
            await self._ai_player_turn()
            
    async def _human_player_turn(self):
        """Handle human player turn."""
        print(f"\n[HUMAN - {self.character_state.name}] Your turn!")
        print("Available action types: explore, interact, ritual, combat, custom")
        print("Enter your action:")
        
        # Use asyncio-compatible input to avoid blocking event loop
        action_input = await asyncio.get_event_loop().run_in_executor(
            None, input, f"{self.character_state.name}> "
        )
        action_input = action_input.strip()
        
        if not action_input:
            return
            
        # Parse simple commands
        parts = action_input.split(' ', 1)
        action_type = parts[0].lower()
        description = parts[1] if len(parts) > 1 else action_input
        
        # Handle special commands
        if action_type == 'take_control':
            print("You already have control!")
            return
        elif action_type == 'release_control':
            self.human_controlled = False
            print(f"[{self.character_state.name}] Switched back to AI control")
            return
        elif action_type == 'status':
            self._show_character_status()
            return
            
        action = {
            'action_type': action_type,
            'description': description,
            'character': self.character_state.name
        }
        
        self.send_message_sync(
            MessageType.ACTION_DECLARED,
            None,  # broadcast so DM and others can see
            action
        )
        
        print(f"[{self.character_state.name}] Declared: {description}")
        
    async def _ai_player_turn(self):
        """Handle AI player turn using personality-driven decision making."""
        if not self.current_scenario:
            return
            
        # Use existing AI decision making from your codebase
        action_options = [
            'explore the environment carefully',
            'interact with other party members', 
            'investigate the immediate situation',
            'prepare for potential danger',
            'attempt to gather information',
            'look for ritual opportunities'
        ]
        
        # Simple personality-based choice (enhance with your existing logic)
        risk_tolerance = self.personality.get('riskTolerance', 5)
        void_curiosity = self.personality.get('voidCuriosity', 3)
        
        if void_curiosity > 6 and 'void' in str(self.current_scenario).lower():
            chosen_action = 'investigate the void presence'
        elif risk_tolerance > 6:
            chosen_action = 'take bold action to advance the situation'
        elif risk_tolerance < 4:
            chosen_action = random.choice([opt for opt in action_options if 'careful' in opt or 'prepare' in opt])
        else:
            chosen_action = random.choice(action_options)
            
        action = {
            'action_type': 'explore' if 'explore' in chosen_action else 'interact',
            'description': chosen_action,
            'character': self.character_state.name,
            'personality_factors': {
                'risk_tolerance': risk_tolerance,
                'void_curiosity': void_curiosity
            }
        }

        if self._prompt_enricher and self.voice_profile:
            previous_turns = list(self._history_supplier() or []) if self._history_supplier else []
            shared_state_snapshot = self.shared_state.snapshot() if self.shared_state else {}
            enriched = self._prompt_enricher(
                "Propose your action and justify the risk.",
                self.voice_profile,
                previous_turns=previous_turns,
                shared_state=shared_state_snapshot,
            )
            action['prompt_context'] = enriched

        self.send_message_sync(
            MessageType.ACTION_DECLARED,
            None,
            action
        )
        
        print(f"[{self.character_state.name}] AI Action: {chosen_action}")
        
    async def _handle_action_resolved(self, message: Message):
        """Handle action resolution from DM."""
        if message.recipient == self.agent_id or message.recipient is None:
            outcome = message.payload.get('outcome', {})
            narration = message.payload.get('narration', '')
            
            print(f"\n[{self.character_state.name}] DM Response: {narration}")
            
            # Update character state based on outcome
            if 'void_gained' in outcome:
                self.character_state.void_score += outcome['void_gained']
                print(f"[{self.character_state.name}] Void Score: {self.character_state.void_score}")
                
            if 'soulcredit_cost' in outcome:
                self.character_state.soulcredit -= outcome['soulcredit_cost']
                print(f"[{self.character_state.name}] Soulcredit: {self.character_state.soulcredit}")
                
    async def _handle_dm_narration(self, message: Message):
        """Handle general DM narration."""
        narration = message.payload.get('narration', '')
        if narration:
            print(f"\n[DM] {narration}")
            
            if self.human_controlled:
                print(f"[HUMAN - {self.character_state.name}] How do you respond?")
                
    def _show_character_status(self):
        """Show current character status."""
        print(f"\n=== {self.character_state.name} Status ===")
        print(f"Faction: {self.character_state.faction}")
        print(f"Void Score: {self.character_state.void_score}/10")
        print(f"Soulcredit: {self.character_state.soulcredit}")
        print(f"Goals: {', '.join(self.character_state.goals)}")
        if self.character_state.bonds:
            print(f"Bonds: {', '.join(self.character_state.bonds)}")
        print("=" * 30)
        
    def toggle_human_control(self):
        """Toggle between human and AI control."""
        self.human_controlled = not self.human_controlled
        status = "HUMAN" if self.human_controlled else "AI"
        print(f"[{status} - {self.character_state.name}] Control switched to {status} mode")
        
        if self.human_controlled:
            print("Available commands: explore, interact, ritual, combat, status, release_control")
            print("Or type any freeform action description")