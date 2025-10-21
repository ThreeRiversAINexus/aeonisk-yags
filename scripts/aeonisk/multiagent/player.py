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
        llm_config: Optional[Dict[str, Any]] = None,
        voice_profile: Optional[VoiceProfile] = None,
        shared_state: Optional[SharedState] = None,
        prompt_enricher: Optional[Callable[..., str]] = None,
        history_supplier: Optional[Callable[[], Iterable[str]]] = None,
    ):
        super().__init__(agent_id, socket_path)
        self.character_config = character_config
        self.llm_config = llm_config or {}
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
        self.message_handlers[MessageType.AGENT_REGISTER] = self._handle_agent_register
        self.message_handlers[MessageType.SESSION_START] = self._handle_session_start
        
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
        """Handle AI player turn using personality-driven decision making with mechanics."""
        if not self.current_scenario:
            return

        # Get action validator for de-duplication
        if self.shared_state:
            validator = self.shared_state.get_action_validator()
            recent_intents = validator.deduplicator.get_recent_intents(self.agent_id)
        else:
            validator = None
            recent_intents = []

        # Generate action using LLM if configured
        risk_tolerance = self.personality.get('riskTolerance', 5)
        void_curiosity = self.personality.get('voidCuriosity', 3)

        if self.llm_config:
            action_declaration = await self._generate_llm_action_structured(recent_intents)
        else:
            # Fallback to simple personality-based choice
            action_declaration = self._generate_simple_action(recent_intents, risk_tolerance, void_curiosity)

        # Apply mechanical validation and corrections
        from .skill_mapping import validate_action_mechanics, get_character_skill_value, RITUAL_ATTRIBUTE, RITUAL_SKILL
        from .action_router import ActionRouter

        # Use action router to determine correct attribute/skill
        router = ActionRouter()
        is_explicit_ritual = router.is_explicit_ritual(action_declaration.intent)

        # Route action to appropriate attribute + skill
        routed_attr, routed_skill, rationale = router.route_action(
            action_declaration.intent,
            action_declaration.action_type,
            self.character_state.skills,
            is_explicit_ritual
        )

        # Apply routing if it differs from declared
        if routed_attr != action_declaration.attribute or routed_skill != action_declaration.skill:
            print(f"[{self.character_state.name}] Routed: {action_declaration.attribute}×{action_declaration.skill or 'None'} → {routed_attr}×{routed_skill or 'None'} ({rationale})")
            action_declaration.attribute = routed_attr
            action_declaration.skill = routed_skill

        # Mark as ritual if explicitly stated
        if is_explicit_ritual:
            action_declaration.is_ritual = True
            action_declaration.action_type = 'ritual'

        corrected_attr, corrected_skill, is_valid, message = validate_action_mechanics(
            action_declaration.action_type,
            action_declaration.attribute,
            action_declaration.skill,
            self.character_state.skills
        )

        # Update action with corrected mechanics
        if corrected_attr != action_declaration.attribute or corrected_skill != action_declaration.skill:
            print(f"[{self.character_state.name}] Mechanics corrected: {action_declaration.attribute}×{action_declaration.skill} → {corrected_attr}×{corrected_skill}")
            action_declaration.attribute = corrected_attr
            action_declaration.skill = corrected_skill

        if message:
            print(f"[{self.character_state.name}] {message}")

        # Validate action (checks for duplicates)
        if validator:
            is_valid, issues = validator.validate_action(action_declaration, allow_duplicates=False)
            if not is_valid:
                print(f"[{self.character_state.name}] Action rejected: {issues[0]}")
                # Try again with simpler action
                action_declaration = self._generate_simple_action(recent_intents, risk_tolerance, void_curiosity)

        # Convert to dict and add character-specific data
        action = action_declaration.to_dict()
        action['attribute_value'] = self.character_state.attributes.get(action_declaration.attribute, 3)
        action['skill_value'] = get_character_skill_value(
            self.character_state.skills,
            action_declaration.skill,
            fallback_value=0
        )
        action['character'] = self.character_state.name
        action['agent_id'] = self.agent_id

        # Send action declaration
        self.send_message_sync(
            MessageType.ACTION_DECLARED,
            None,
            action
        )

        print(f"\n[{self.character_state.name}] {action_declaration.get_summary()}")
        
    async def _handle_action_resolved(self, message: Message):
        """Handle action resolution from DM."""
        if message.recipient == self.agent_id or message.recipient is None:
            outcome = message.payload.get('outcome', {})
            narration = message.payload.get('narration', '')

            print(f"\n[{self.character_state.name}] Received resolution")

            # Update void state from mechanics engine
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                void_state = mechanics.get_void_state(self.agent_id)
                self.character_state.void_score = void_state.score

                if len(void_state.history) > 0:
                    last_change = void_state.history[-1]
                    if last_change['new_score'] != last_change['old_score']:
                        print(f"[{self.character_state.name}] Void: {last_change['old_score']} → {last_change['new_score']} ({last_change['reason']})")

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

    async def _handle_agent_register(self, message: Message):
        """Handle agent registration messages (no-op for players)."""
        pass

    async def _handle_session_start(self, message: Message):
        """Handle session start messages (no-op for players - handled via SCENARIO_SETUP)."""
        pass

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

    async def _generate_llm_action_structured(self, recent_intents: List[str]):
        """Generate structured action using LLM with enhanced prompts."""
        from .enhanced_prompts import get_player_system_prompt
        from .action_schema import ActionDeclaration

        # Build system prompt with mechanical scaffolding
        system_prompt = get_player_system_prompt(
            character_name=self.character_state.name,
            character_stats={
                'attributes': self.character_state.attributes,
                'skills': self.character_state.skills,
                'soulcredit': self.character_state.soulcredit
            },
            personality=self.personality,
            goals=self.character_state.goals,
            recent_intents=recent_intents,
            void_score=self.character_state.void_score
        )

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"""
Current Scenario: {self.current_scenario.get('theme', 'Unknown')}
Location: {self.current_scenario.get('location', 'Unknown')}
Situation: {self.current_scenario.get('situation', 'Unknown')}
"""

        prompt = f"""{system_prompt}

{scenario_context}

Declare your next action using the required format:
INTENT: [what you're doing]
ATTRIBUTE: [which attribute]
SKILL: [which skill or None]
DIFFICULTY: [estimate]
JUSTIFICATION: [why that difficulty]
ACTION_TYPE: [explore/investigate/ritual/social/combat/technical]
DESCRIPTION: [narrative description]"""

        try:
            provider = self.llm_config.get('provider', 'anthropic')
            model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')
            temperature = self.llm_config.get('temperature', 0.8)

            if provider == 'anthropic':
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=300,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}]
                )
                llm_text = response.content[0].text.strip()
            else:
                # Fallback to simple action
                return self._generate_simple_action(recent_intents, self.personality.get('riskTolerance', 5), self.personality.get('voidCuriosity', 3))

            # Parse LLM response into ActionDeclaration
            action = self._parse_action_from_llm(llm_text)
            return action

        except Exception as e:
            logger.error(f"LLM API error for player action: {e}")
            # Fallback to simple action
            return self._generate_simple_action(recent_intents, self.personality.get('riskTolerance', 5), self.personality.get('voidCuriosity', 3))

    def _parse_action_from_llm(self, llm_text: str):
        """Parse structured action from LLM response."""
        from .action_schema import ActionDeclaration

        lines = llm_text.strip().split('\n')
        data = {
            'intent': 'investigate the situation',
            'description': llm_text[:200],
            'attribute': 'Perception',
            'skill': None,
            'difficulty_estimate': 20,
            'difficulty_justification': 'moderate challenge',
            'action_type': 'investigate',
            'character_name': self.character_state.name,
            'agent_id': self.agent_id
        }

        # Valid attributes with proper capitalization
        VALID_ATTRIBUTES = {
            'strength': 'Strength',
            'agility': 'Agility',
            'endurance': 'Endurance',
            'perception': 'Perception',
            'intelligence': 'Intelligence',
            'empathy': 'Empathy',
            'willpower': 'Willpower',
            'charisma': 'Charisma'
        }

        # Parse fields from LLM output
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if 'intent' in key:
                    data['intent'] = value
                elif 'attribute' in key:
                    # Normalize attribute name
                    attr_lower = value.lower()
                    data['attribute'] = VALID_ATTRIBUTES.get(attr_lower, 'Perception')
                elif 'skill' in key:
                    data['skill'] = value if value.lower() != 'none' else None
                elif 'difficulty' in key and not 'justification' in key:
                    try:
                        data['difficulty_estimate'] = int(value.split()[0])
                        if '-' in value:
                            data['difficulty_justification'] = value.split('-', 1)[1].strip()
                    except:
                        pass
                elif 'justification' in key:
                    data['difficulty_justification'] = value
                elif 'action_type' in key or 'type' in key:
                    data['action_type'] = value.lower()
                elif 'description' in key:
                    data['description'] = value

        try:
            return ActionDeclaration(**data)
        except Exception as e:
            logger.error(f"Failed to create ActionDeclaration: {e}")
            # Return minimal valid action
            return ActionDeclaration(
                intent=data['intent'],
                description=data['description'],
                attribute=data['attribute'],
                skill=data.get('skill'),
                difficulty_estimate=data['difficulty_estimate'],
                difficulty_justification=data['difficulty_justification'],
                action_type=data['action_type'],
                character_name=self.character_state.name,
                agent_id=self.agent_id
            )

    def _generate_simple_action(self, recent_intents: List[str], risk_tolerance: int, void_curiosity: int):
        """Generate simple action based on personality without LLM."""
        from .action_schema import ActionDeclaration
        import random

        # Avoid recently used action types
        recent_types = set()
        for intent in recent_intents:
            if 'scan' in intent.lower() or 'investigate' in intent.lower():
                recent_types.add('investigate')
            if 'ritual' in intent.lower() or 'harmoniz' in intent.lower():
                recent_types.add('ritual')
            if 'ask' in intent.lower() or 'talk' in intent.lower() or 'question' in intent.lower() or 'discuss' in intent.lower():
                recent_types.add('social')

        # Get character's actual skills (use canonical YAGS names)
        has_charm = 'Charm' in self.character_state.skills
        has_guile = 'Guile' in self.character_state.skills
        has_social = has_charm or has_guile
        has_astral = 'Astral Arts' in self.character_state.skills
        has_awareness = 'Awareness' in self.character_state.skills

        # 30% chance of social interaction with other players
        if 'social' not in recent_types and random.random() < 0.3:
            # Get other player names from current scenario
            social_actions = [
                "Discuss findings with the group",
                "Share observations with companions",
                "Coordinate strategy with party members",
                "Ask others about their insights",
                "Suggest a collaborative approach",
            ]
            intent = random.choice(social_actions)
            action_type = "social"
            attribute = "Empathy"
            skill = "Charm" if has_charm else ("Guile" if has_guile else None)
        # Choose action type based on personality, skills, and what hasn't been done recently
        elif 'social' not in recent_types and has_social and not has_astral:
            # Non-astral characters prefer social
            intent = f"Question NPCs about the situation"
            action_type = "social"
            attribute = "Empathy"
            skill = "Charm" if has_charm else "Guile"
        elif 'ritual' not in recent_types and has_astral and void_curiosity > 5:
            intent = "Use astral arts to sense void presence"
            action_type = "ritual"
            attribute = "Willpower"
            skill = "Astral Arts"
        elif 'investigate' not in recent_types and has_awareness:
            intent = "Investigate physical evidence"
            action_type = "investigate"
            attribute = "Perception"
            skill = "Awareness"
        elif has_astral:
            # Ritual fallback
            intent = "Perform minor ritual to assess the situation"
            action_type = "ritual"
            attribute = "Willpower"
            skill = "Astral Arts"
        else:
            # Explore with raw perception (no skill)
            intent = "Carefully examine the environment"
            action_type = "explore"
            attribute = "Perception"
            skill = None

        return ActionDeclaration(
            intent=intent,
            description=f"{self.character_state.name} attempts to {intent.lower()}",
            attribute=attribute,
            skill=skill,
            difficulty_estimate=20,
            difficulty_justification="moderate task in current conditions",
            action_type=action_type,
            character_name=self.character_state.name,
            agent_id=self.agent_id
        )