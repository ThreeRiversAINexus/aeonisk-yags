"""
AI Dungeon Master agent for multi-agent self-playing system.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from .base import Agent, Message, MessageType
from .shared_state import SharedState
from .voice_profiles import VoiceProfile

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
    
    def __init__(
        self,
        agent_id: str,
        socket_path: str,
        llm_config: Dict[str, Any],
        *,
        voice_profile: Optional[VoiceProfile] = None,
        shared_state: Optional[SharedState] = None,
        prompt_enricher: Optional[Callable[..., str]] = None,
        history_supplier: Optional[Callable[[], Iterable[str]]] = None,
    ):
        super().__init__(agent_id, socket_path)
        self.llm_config = llm_config
        self.current_scenario: Optional[Scenario] = None
        self.human_controlled = False
        self.human_input_queue = asyncio.Queue()
        self.voice_profile = voice_profile
        self.shared_state = shared_state
        self._prompt_enricher = prompt_enricher
        self._history_supplier = history_supplier
        
        # Set up DM-specific message handlers
        self.message_handlers[MessageType.SESSION_START] = self._handle_session_start
        self.message_handlers[MessageType.ACTION_DECLARED] = self._handle_action_declared
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        self.message_handlers[MessageType.AGENT_REGISTER] = self._handle_agent_register
        self.message_handlers[MessageType.DM_NARRATION] = self._handle_dm_narration

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
        # Use LLM to generate dynamic scenario
        try:
            scenario_prompt = """Generate a unique Aeonisk YAGS scenario for a tabletop RPG session.

Create a scenario with:
1. Theme (2-3 words): The type of situation
2. Location: A specific place in the Aeonisk setting
3. Situation (1-2 sentences): What's happening
4. Void level (0-10): How much void corruption is present
5. Three clocks/timers (name, max ticks 4-8, description) that track:
   - A threat/danger that could escalate
   - Something the players are trying to accomplish
   - A complication or secondary concern

Format:
THEME: [theme]
LOCATION: [location]
SITUATION: [situation]
VOID_LEVEL: [number]
CLOCK1: [name] | [max] | [description]
CLOCK2: [name] | [max] | [description]
CLOCK3: [name] | [max] | [description]

Make it creative and thematic to Aeonisk's dark sci-fi setting."""

            provider = self.llm_config.get('provider', 'anthropic')
            model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

            import anthropic
            import os
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=500,
                temperature=0.9,
                messages=[{"role": "user", "content": scenario_prompt}]
            )
            llm_text = response.content[0].text.strip()

            # Parse LLM response
            scenario_data = self._parse_scenario_from_llm(llm_text)

        except Exception as e:
            logger.error(f"Failed to generate AI scenario: {e}, using fallback")
            # Fallback to simple random scenario
            import random
            themes = ['Corporate Intrigue', 'Void Investigation', 'Bond Crisis', 'Tech Heist', 'Ritual Gone Wrong']
            scenario_data = {
                'theme': random.choice(themes),
                'location': 'Unknown Location',
                'situation': 'The party finds themselves in a mysterious situation',
                'void_level': 3,
                'clocks': [
                    ('Danger Level', 6, 'Escalating threat'),
                    ('Investigation', 6, 'Uncovering the truth'),
                    ('Time Pressure', 6, 'Running out of time')
                ]
            }

        scenario = Scenario(
            theme=scenario_data['theme'],
            location=scenario_data['location'],
            situation=scenario_data['situation'],
            active_npcs=[],
            environmental_factors=[],
            void_level=scenario_data['void_level']
        )

        self.current_scenario = scenario

        # Initialize mechanics and create scenario-specific clocks
        if self.shared_state:
            self.shared_state.initialize_mechanics()
            mechanics = self.shared_state.get_mechanics_engine()

            for clock_name, max_value, description in scenario_data.get('clocks', []):
                mechanics.create_scene_clock(clock_name, max_value, description)
                print(f"[DM {self.agent_id}] Created clock: {clock_name} (0/{max_value})")

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
        
    def _parse_scenario_from_llm(self, llm_text: str) -> Dict[str, Any]:
        """Parse scenario from LLM-generated text."""
        lines = llm_text.strip().split('\n')
        scenario_data = {
            'theme': 'Unknown',
            'location': 'Unknown Location',
            'situation': 'Something mysterious is happening',
            'void_level': 3,
            'clocks': []
        }

        for line in lines:
            line = line.strip()
            if ':' in line or '|' in line:
                if line.startswith('THEME:'):
                    scenario_data['theme'] = line.split(':', 1)[1].strip()
                elif line.startswith('LOCATION:'):
                    scenario_data['location'] = line.split(':', 1)[1].strip()
                elif line.startswith('SITUATION:'):
                    scenario_data['situation'] = line.split(':', 1)[1].strip()
                elif line.startswith('VOID_LEVEL:'):
                    try:
                        scenario_data['void_level'] = int(line.split(':', 1)[1].strip())
                    except:
                        pass
                elif line.startswith('CLOCK'):
                    # Format: CLOCK1: Name | 6 | Description
                    parts = line.split(':', 1)[1].split('|')
                    if len(parts) >= 3:
                        name = parts[0].strip()
                        try:
                            max_ticks = int(parts[1].strip())
                        except:
                            max_ticks = 6
                        description = parts[2].strip()
                        scenario_data['clocks'].append((name, max_ticks, description))

        # Ensure we have at least 2 clocks
        if len(scenario_data['clocks']) < 2:
            scenario_data['clocks'].append(('Danger Escalation', 6, 'The situation worsens'))
            scenario_data['clocks'].append(('Player Progress', 6, 'Investigating the mystery'))

        return scenario_data

    def _generate_opening_narration(self, scenario: Scenario) -> str:
        """Generate opening narration for scenario."""
        return f"""
The party finds themselves at {scenario.location}. {scenario.situation}.
The air carries a distinct tension, and you sense the void's influence at level {scenario.void_level}/10.

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
        """Handle action with AI DM logic using mechanical resolution."""
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        intent = action.get('intent', description)

        # Get mechanics engine
        resolution = None
        narration = ""

        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()

            # Extract mechanical details from action
            attribute = action.get('attribute', 'Perception')
            skill = action.get('skill')
            attribute_value = action.get('attribute_value', 3)
            skill_value = action.get('skill_value', 0)
            difficulty = action.get('difficulty_estimate', 20)

            # CRITICAL: Re-validate ritual mechanics at DM resolution time
            # (Player may have sent corrected values, but we enforce anyway)
            from .skill_mapping import validate_ritual_mechanics, RITUAL_ATTRIBUTE, RITUAL_SKILL

            if action_type == 'ritual' or action.get('is_ritual', False):
                # Force ritual mechanics
                if attribute != RITUAL_ATTRIBUTE or skill != RITUAL_SKILL:
                    logger.warning(f"DM correcting ritual: {attribute}×{skill} → {RITUAL_ATTRIBUTE}×{RITUAL_SKILL}")
                attribute = RITUAL_ATTRIBUTE
                skill = RITUAL_SKILL
                # Re-fetch values for corrected attribute/skill
                # (We'd need character sheet access here; for now trust player sent correct values)
                # This ensures resolve_action gets Willpower×Astral Arts

            # Resolve mechanically
            if action.get('is_ritual', False):
                # Ritual resolution
                resolution, ritual_effects = mechanics.resolve_ritual(
                    intent=intent,
                    willpower=attribute_value if attribute == 'Willpower' else 3,
                    astral_arts=skill_value if skill == 'Astral Arts' else 0,
                    difficulty=difficulty,
                    has_primary_tool=action.get('has_primary_tool', False),
                    has_offering=action.get('has_offering', False),
                    sanctified_altar=action.get('at_altar', False),
                    agent_id=player_id
                )

                # NOTE: Don't add void here - outcome_parser will handle it
                # Just show consequences
                narration_suffix = "\n" + "\n".join(ritual_effects['consequences'])
            else:
                # Regular action resolution
                resolution = mechanics.resolve_action(
                    intent=intent,
                    attribute=attribute,
                    skill=skill,
                    attribute_value=attribute_value,
                    skill_value=skill_value,
                    difficulty=difficulty,
                    agent_id=player_id
                )
                narration_suffix = ""

            # Update clocks based on outcome
            mechanics.update_clocks_from_action(resolution, action)

            # NOTE: Removed check_void_trigger call here to avoid duplicate void tracking
            # Void will be tracked via outcome_parser only

            # Format mechanical resolution
            mechanical_text = mechanics.format_resolution_for_narration(resolution)

            # Generate narrative description using LLM
            llm_narration = await self._generate_llm_response(
                player_id, action_type, description, resolution
            )

            narration = f"{mechanical_text}\n\n{llm_narration}{narration_suffix}"

            # Parse narration for automatic state changes
            from .outcome_parser import parse_state_changes

            # Get active clocks for dynamic clock progression
            active_clocks = mechanics.scene_clocks if mechanics else {}

            state_changes = parse_state_changes(llm_narration, action, resolution.__dict__, active_clocks)

            # Apply clock advancements (positive=advance, negative=regress)
            clock_updates = []
            for clock_name, ticks, reason in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    if ticks < 0:
                        # Negative ticks = regress (improve)
                        mechanics.scene_clocks[clock_name].regress(abs(ticks))
                        clock = mechanics.scene_clocks[clock_name]
                        clock_updates.append(f"{clock_name}: {clock.current}/{clock.maximum} ↓")
                    else:
                        # Positive ticks = advance (degrade)
                        filled = mechanics.advance_clock(clock_name, ticks, reason)
                        clock = mechanics.scene_clocks[clock_name]
                        clock_updates.append(f"{clock_name}: {clock.current}/{clock.maximum}")
                        if filled:
                            clock_updates.append(f"🚨 {clock_name} FILLED!")

            if clock_updates:
                narration += "\n\n📊 " + " | ".join(clock_updates)

            # Apply void changes (both gains and reductions)
            if state_changes['void_change'] != 0:
                void_state = mechanics.get_void_state(player_id)
                old_void = void_state.score

                if state_changes['void_change'] > 0:
                    # Void gain (corruption increasing)
                    action_id = f"{player_id}_{intent}_{resolution.total}"
                    void_state.add_void(
                        state_changes['void_change'],
                        ", ".join(state_changes['void_reasons']),
                        action_id=action_id
                    )
                    # Show void increase if it actually changed
                    if void_state.score != old_void:
                        narration += f"\n\n⚫ Void: {old_void} → {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"
                else:
                    # Void reduction (recovery moves)
                    void_state.reduce_void(
                        abs(state_changes['void_change']),
                        ", ".join(state_changes['void_reasons'])
                    )
                    # Show void decrease if it actually changed
                    if void_state.score != old_void:
                        narration += f"\n\n⚫ Void: {old_void} ↓ {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"

            # Apply conditions
            from .mechanics import Condition
            for condition_data in state_changes.get('conditions', []):
                condition = Condition(
                    name=condition_data['type'],
                    type=condition_data['type'],
                    penalty=condition_data['penalty'],
                    description=condition_data['description'],
                    duration=3,  # Default duration
                    affects=[]  # Affects all by default
                )
                mechanics.add_condition(player_id, condition)

                # Show condition application
                narration += f"\n\n🩹 Condition: {condition.name} ({condition.penalty:+d})"

            # Display notes from outcome parser (e.g., recovery move explanations)
            if state_changes.get('notes'):
                for note in state_changes['notes']:
                    narration += f"\n\n💡 {note}"

            # Check for filled clocks (triggers)
            clock_triggers = self._check_clock_triggers(mechanics)
            if clock_triggers:
                narration += f"\n\n{clock_triggers}"

        else:
            # Fallback if no mechanics available
            narration = await self._generate_llm_response(
                player_id, action_type, description
            )

        # Prepare serializable outcome
        resolution_data = None
        if resolution:
            # Convert resolution to JSON-serializable dict
            resolution_data = {
                'intent': resolution.intent,
                'attribute': resolution.attribute,
                'skill': resolution.skill,
                'total': resolution.total,
                'difficulty': resolution.difficulty,
                'margin': resolution.margin,
                'outcome_tier': resolution.outcome_tier.value,  # Convert enum to string
                'success': resolution.success
            }

        outcome = {
            'dm_response': narration,
            'success': resolution.success if resolution else True,
            'consequences': [],
            'resolution': resolution_data
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

        print(f"\n[DM {self.agent_id}] ===== Resolution =====")
        print(narration)
        print("=" * 40)
        
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
        # DM turn: provide status update instead of empty narration
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine

            # Build status summary
            status_parts = []

            # Show clock states
            for clock_name, clock in mechanics.scene_clocks.items():
                status_parts.append(f"{clock_name}: {clock.current}/{clock.maximum}")

            if status_parts:
                narration = "📊 " + " | ".join(status_parts)
            else:
                # Skip DM turn if nothing to report
                return

            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,
                {
                    'narration': narration,
                    'environmental_changes': [],
                    'npc_actions': []
                }
            )

            print(f"[DM {self.agent_id}] Status: {narration}")
        else:
            # Skip DM turn if no mechanics
            return
        
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

    async def _handle_agent_register(self, message: Message):
        """Handle agent registration messages (no-op for DM)."""
        pass

    async def _handle_dm_narration(self, message: Message):
        """Handle DM narration messages (no-op - DM sends these, doesn't receive them)."""
        pass

    async def _generate_llm_response(self, player_id: str, action_type: str, description: str, resolution=None) -> str:
        """Generate DM response using LLM."""
        provider = self.llm_config.get('provider', 'openai')
        model = self.llm_config.get('model', 'gpt-4')
        temperature = self.llm_config.get('temperature', 0.7)

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"""
Current Scenario: {self.current_scenario.theme}
Location: {self.current_scenario.location}
Situation: {self.current_scenario.situation}
Void Level: {self.current_scenario.void_level}/10
"""

        resolution_context = ""
        if resolution:
            outcome_text = "succeeded" if resolution.success else "failed"
            resolution_context = f"""
Mechanical Result: The action {outcome_text} with margin {resolution.margin:+d} (outcome: {resolution.outcome_tier.value})
"""

        prompt = f"""You are the Dungeon Master for an Aeonisk YAGS game session.

{scenario_context}
{resolution_context}

Player Action: {description}
Action Type: {action_type}

As the DM, describe what happens narratively as a result of this action. Be vivid and thematic. Include:
1. What the player discovers or experiences
2. Any immediate consequences or complications
3. How the void energy might influence the outcome (if relevant)
4. Provide a new clue, complication, or piece of information to advance the story

Keep the response to 2-3 sentences. Be engaging and maintain the dark sci-fi atmosphere."""

        try:
            if provider == 'openai':
                import openai
                response = await asyncio.to_thread(
                    openai.ChatCompletion.create,
                    model=model,
                    messages=[{"role": "system", "content": "You are an expert Aeonisk YAGS Dungeon Master."},
                             {"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=150
                )
                return response.choices[0].message.content.strip()

            elif provider == 'anthropic':
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=150,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"LLM API error: {e}")
            # Fallback to template
            if resolution:
                if resolution.success:
                    return f"You {description} successfully. You notice something unusual about the situation that provides a new lead."
                else:
                    return f"Your attempt to {description} doesn't go as planned. The failure reveals an unexpected complication."
            return f"As you {description}, the situation develops in unexpected ways. The void energy at level {self.current_scenario.void_level if self.current_scenario else 3}/10 subtly influences the outcome."

    def _check_clock_triggers(self, mechanics) -> str:
        """Check if any clocks filled and return trigger narration."""
        triggers = []

        for clock_name, clock in mechanics.scene_clocks.items():
            if clock.filled:
                # Generate appropriate trigger based on clock name
                if "Corruption" in clock_name:
                    triggers.append(f"🚨 **{clock_name} FILLED!** The void corruption manifests - a minor entity coalesces from the corrupted field!")
                elif "Exposure" in clock_name:
                    triggers.append(f"🚨 **{clock_name} FILLED!** You've identified the perpetrator - they make a desperate move!")
                elif "Stability" in clock_name:
                    triggers.append(f"🚨 **{clock_name} FILLED!** The communal bonds fracture - panic spreads through the group!")
                elif "Evidence" in clock_name or "Investigation" in clock_name:
                    triggers.append(f"✅ **{clock_name} FILLED!** The pieces fall into place - you understand the full picture!")
                elif "Lockdown" in clock_name or "Collapse" in clock_name:
                    triggers.append(f"⚠️ **{clock_name} FILLED!** The situation reaches critical mass!")
                else:
                    triggers.append(f"📍 **{clock_name} FILLED!** A major story beat occurs!")

        return "\n".join(triggers) if triggers else ""

    def _estimate_void_level(self) -> int:
        """Estimate void severity from shared state."""
        if not self.shared_state:
            return 0
        return sum(spike.severity for spike in self.shared_state.void_spikes)