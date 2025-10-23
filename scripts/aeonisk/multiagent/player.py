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
from .energy_economy import EnergyInventory, Seed, SeedType, Element, create_raw_seed

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
    pronouns: str = "they/them"  # Default to gender-neutral
    inventory: Dict[str, int] = None
    energy_inventory: Optional['EnergyInventory'] = None

    def __post_init__(self):
        """Initialize default inventory and energy inventory if not provided."""
        # Initialize energy inventory with randomized currency
        if self.energy_inventory is None:
            self.energy_inventory = EnergyInventory(
                breath=random.randint(5, 15),  # Variable starting amounts
                drip=random.randint(3, 10),
                grain=random.randint(0, 3),
                spark=random.randint(0, 2),  # Most start with 0-2 Spark
                seeds=[]
            )
            # Add some starter seeds based on faction (varying freshness)
            if 'Tempest' in self.faction:
                # Tempest gets Hollow seeds (stable, no decay)
                self.energy_inventory.add_seed(Seed(SeedType.HOLLOW, origin="tempest_supply"))
            elif 'Sovereign' in self.faction or 'Pantheon' in self.faction:
                # Pro-Nexus factions get Attuned seeds (stable)
                self.energy_inventory.add_seed(Seed(SeedType.ATTUNED, element=Element.SPIRIT, origin="nexus_sanctified"))
            else:
                # Others get Raw seeds with random freshness (might be aged/old)
                raw_seed = create_raw_seed(origin="leyline_harvest", freshness="random")
                self.energy_inventory.add_seed(raw_seed)

        if self.inventory is None:
            self.inventory = {
                # Ritual Consumables
                'blood_offering': 0,
                'incense': 0,
                'neural_stimulant': 0,
                'memory_crystal': 0,

                # Tools & Focuses
                'crystal_focus': 0,
                'tech_kit': 0,
                'neural_interface_module': 0,
                'void_scanner': 0,
                'resonance_tuner': 0,

                # Medical/Utility
                'med_kit': 0,
                'data_slate': 0,
                'comm_unit': 0,
            }

    def has_offering(self, offering_type: str = None) -> bool:
        """Check if character has any offering."""
        if offering_type:
            return self.inventory.get(offering_type, 0) > 0
        # Check for any offering type
        return any(v > 0 for k, v in self.inventory.items() if 'offering' in k)

    def consume_offering(self, offering_type: str = None) -> bool:
        """Consume an offering and return True if successful."""
        if offering_type and self.inventory.get(offering_type, 0) > 0:
            self.inventory[offering_type] -= 1
            return True
        # Consume first available offering
        for item, count in self.inventory.items():
            if 'offering' in item and count > 0:
                self.inventory[item] -= 1
                return True
        return False

    def has_focus(self) -> bool:
        """Check if character has a ritual focus."""
        return (self.inventory.get('crystal_focus', 0) > 0 or
                self.inventory.get('tech_kit', 0) > 0)


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

        # Tactical positioning (for Tactical Module v1.2.3)
        from .enemy_agent import Position
        self.position = Position.from_string("Near-PC")  # Default starting position

        # Combat attributes (for enemy attacks and YAGS combat)
        # Will be initialized properly in on_start() after character_state is created
        self.health = None  # Current HP
        self.max_health = None  # Maximum HP
        self.soak = None  # Damage resistance
        self.wounds = 0  # Wound count (Tactical Module wound ladder)
        self.stuns = 0  # Stun damage (YAGS)

        # Free action tracking (one per round)
        self.free_action_used = False

        # Set up player-specific message handlers
        self.message_handlers[MessageType.SCENARIO_SETUP] = self._handle_scenario_setup
        self.message_handlers[MessageType.SCENARIO_UPDATE] = self._handle_scenario_update
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        self.message_handlers[MessageType.ACTION_DECLARED] = self._handle_action_declared
        self.message_handlers[MessageType.ACTION_RESOLVED] = self._handle_action_resolved
        self.message_handlers[MessageType.DM_NARRATION] = self._handle_dm_narration
        self.message_handlers[MessageType.AGENT_REGISTER] = self._handle_agent_register
        self.message_handlers[MessageType.SESSION_START] = self._handle_session_start
        
    async def on_start(self):
        """Initialize player agent."""
        # Create character from config
        # Load inventory from config or use defaults
        inventory_config = self.character_config.get('inventory', {})
        default_inventory = {
            # Ritual Consumables
            'blood_offering': 2,
            'incense': 2,
            'neural_stimulant': 1,
            'memory_crystal': 3,

            # Tools & Focuses
            'crystal_focus': 1,
            'tech_kit': 1,
            'neural_interface_module': 1,
            'void_scanner': 1,
            'resonance_tuner': 1,

            # Medical/Utility
            'med_kit': 2,
            'data_slate': 1,
            'comm_unit': 1,
        }
        # Merge config with defaults
        inventory = {**default_inventory, **inventory_config}

        self.character_state = CharacterState(
            name=self.character_config.get('name', f'Player_{self.agent_id}'),
            faction=self.character_config.get('faction', 'Unaffiliated'),
            attributes=self.character_config.get('attributes', {}),
            skills=self.character_config.get('skills', {}),
            void_score=self.character_config.get('void_score', 0),
            soulcredit=self.character_config.get('soulcredit', random.randint(4, 7)),  # Lower, varied starting soulcredit
            bonds=self.character_config.get('bonds', []),
            goals=self.character_config.get('goals', []),
            pronouns=self.character_config.get('pronouns', 'they/them'),
            inventory=inventory
        )

        # Initialize combat attributes (for enemy attacks to work)
        # Health = Size × 2 (YAGS rules)
        size = self.character_state.attributes.get('Size', 5)
        self.max_health = size * 2
        self.health = self.max_health
        # Soak = YAGS standard base soak for adult humans (character.md:598-600)
        self.soak = 12

        logger.info(f"Player {self.agent_id} ({self.character_state.name}) started")

        # Register with shared state for party awareness
        if self.shared_state:
            self.shared_state.register_player(
                self.agent_id,
                self.character_state.name,
                self.character_state.faction
            )

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

    # === YAGS Combat Lifecycle Properties ===

    @property
    def is_alive(self) -> bool:
        """Check if player is alive (health > 0)."""
        return self.health is not None and self.health > 0

    @property
    def is_conscious(self) -> bool:
        """
        Check if player is conscious.

        YAGS Rules (combat.md:406-422):
        - At 5+ wounds (fatally wounded), must make death saves
        - Good success: Can continue fighting (but -25 penalty)
        - Success: Unconscious (cannot act)
        - Failure: Dead
        """
        if not self.is_alive:
            return False

        # If fatally wounded (5+ wounds), must make death save
        if self.wounds >= 5:
            # Note: Actual death save is rolled when damage is taken
            # This property returns current conscious state
            # TODO: Track consciousness state separately if needed
            return False

        return True

    def check_death_save(self) -> tuple[bool, str]:
        """
        Make YAGS death save when fatally wounded.

        YAGS Rules (combat.md:406-422):
        - At 5+ wounds (fatally wounded), make Health check
        - DC = 20 + 5 per wound beyond fatal (5th wound)
        - Success: Unconscious (must reroll each round)
        - Good success (DC+10): Can continue fighting (but -25 penalty)
        - Failure: DEAD

        Returns:
            (alive, status) where status is "conscious", "unconscious", or "dead"
        """
        if self.wounds < 5:
            return True, "conscious"

        # Calculate DC: 20 base + 5 per extra wound beyond 5th
        extra_wounds = self.wounds - 5
        dc = 20 + (5 * extra_wounds)

        # Roll Health check (Health attribute × 2 + d20)
        health_attr = self.character_state.attributes.get('Health', 3)
        roll = random.randint(1, 20)
        total = (health_attr * 2) + roll

        logger.info(f"{self.character_state.name} death save: {health_attr}×2 + {roll} = {total} vs DC {dc} (wounds: {self.wounds})")

        # Fumble (nat 1) = automatic death
        if roll == 1:
            logger.warning(f"{self.character_state.name} FUMBLED death save - KILLED!")
            return False, "dead"

        # Good success (beat DC by 10+) = can keep fighting
        if total >= dc + 10:
            logger.info(f"{self.character_state.name} passed death save with good success - still conscious!")
            return True, "conscious"

        # Success = unconscious but alive
        elif total >= dc:
            logger.info(f"{self.character_state.name} passed death save - unconscious but alive")
            return True, "unconscious"

        # Failure = dead
        else:
            logger.warning(f"{self.character_state.name} FAILED death save - KILLED!")
            return False, "dead"

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

    async def _handle_scenario_update(self, message: Message):
        """Handle mid-game scenario pivot from DM."""
        new_theme = message.payload.get('new_theme', 'Unknown')
        new_situation = message.payload.get('new_situation', '')
        pivot_narration = message.payload.get('pivot_narration', '')

        # Update scenario with new theme while preserving location
        if self.current_scenario:
            self.current_scenario['theme'] = new_theme
            if new_situation:
                self.current_scenario['situation'] = new_situation
        else:
            self.current_scenario = {
                'theme': new_theme,
                'situation': new_situation
            }

        print(f"\n[{self.character_state.name}] 🔄 SCENARIO PIVOT: {new_theme}")
        if pivot_narration:
            print(f"    {pivot_narration}")

    async def _handle_action_declared(self, message: Message):
        """Handle action declarations from other players - show character voice."""
        action = message.payload

        # Don't show our own actions (we already printed them)
        if action.get('agent_id') == self.agent_id:
            return

        character_name = action.get('character_name', 'Unknown')
        description = action.get('description', '')
        intent = action.get('intent', '')

        # Show the character voice description
        if description:
            print(f"\n[{character_name}] {description}")
        else:
            print(f"\n[{character_name}] {intent}")

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
            logger.debug(f"{self.character_state.name} has no scenario, returning without action")
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

        # MINIMAL validation - only normalize skill name aliases, preserve all AI choices
        # Philosophy: Let AI make "wrong" choices - that's valuable data. DM handles corrections narratively.
        from .skill_mapping import normalize_skill, get_character_skill_value
        from .action_router import ActionRouter

        # Get other player names for inter-party action detection
        other_players = []
        if self.shared_state:
            other_players = self.shared_state.get_other_players(self.agent_id)

        # Only check if action intent mentions "ritual" explicitly
        router = ActionRouter()
        is_explicit_ritual = router.is_explicit_ritual(action_declaration.intent)

        # Mark as ritual if explicitly stated (but don't change attribute/skill)
        if is_explicit_ritual or action_declaration.action_type == 'ritual':
            action_declaration.is_ritual = True
            action_declaration.action_type = 'ritual'

        # Normalize skill name ONLY if it's an alias (e.g., "social" → "Charm", "investigation" → "Awareness")
        if action_declaration.skill:
            original_skill = action_declaration.skill
            normalized_skill = normalize_skill(action_declaration.skill)

            # If normalization changed the name, it was an alias - apply silently
            if normalized_skill != original_skill:
                action_declaration.skill = normalized_skill
                # Don't log - this is just alias normalization

        # Validate action (checks for duplicates)
        if validator:
            is_valid, issues = validator.validate_action(action_declaration, allow_duplicates=False)
            if not is_valid:
                print(f"[{self.character_state.name}] Action rejected: {issues[0]}")
                # Try again with simpler action
                action_declaration = self._generate_simple_action(recent_intents, risk_tolerance, void_curiosity)

        # Detect if this is inter-party communication (free action)
        # This includes dialogue (Charm/Counsel) and social rituals (Intimacy Ritual)
        is_dialogue_action = (action_declaration.attribute == 'Empathy' and action_declaration.skill in ['Charm', 'Counsel'])
        is_intimacy_ritual = (action_declaration.skill == 'Intimacy Ritual')
        is_free_action = False

        logger.debug(f"Free action check: is_dialogue={is_dialogue_action}, attr={action_declaration.attribute}, skill={action_declaration.skill}")
        logger.debug(f"Other players: {other_players}")
        logger.debug(f"Intent: {action_declaration.intent}")

        if (is_dialogue_action or is_intimacy_ritual) and self.shared_state:
            # Check if intent or description mentions any party member name
            intent_lower = action_declaration.intent.lower()
            description_lower = action_declaration.description.lower()
            for player_name in other_players:
                logger.debug(f"Checking if '{player_name.lower()}' or parts in '{intent_lower}'")
                # Check if full name or significant parts are mentioned (handle "Enforcer Kael" vs "Enforcer Kael Dren")
                name_parts = player_name.lower().split()
                # Check if at least 2 words from name appear, or the full name
                if player_name.lower() in intent_lower or player_name.lower() in description_lower:
                    is_free_action = True
                elif len(name_parts) >= 2:
                    # Check if at least 2 consecutive words from the name appear
                    for i in range(len(name_parts) - 1):
                        two_word_combo = f"{name_parts[i]} {name_parts[i+1]}"
                        if two_word_combo in intent_lower or two_word_combo in description_lower:
                            is_free_action = True
                            break

                if is_free_action:
                    if is_intimacy_ritual:
                        print(f"[{self.character_state.name}] Inter-party ritual detected - FREE ACTION")
                    else:
                        print(f"[{self.character_state.name}] Inter-party dialogue detected - FREE ACTION")

                    # Grant coordination bonus to the target
                    # Detect coordination keywords
                    coordination_keywords = [
                        'share', 'tell', 'inform', 'coordinate', 'discuss', 'ask',
                        'brief', 'report', 'advise', 'warn', 'update', 'consult'
                    ]
                    if any(kw in intent_lower for kw in coordination_keywords):
                        self.shared_state.grant_coordination_bonus(
                            from_agent=self.agent_id,
                            from_name=self.character_state.name,
                            to_name=player_name,
                            reason="coordinated information sharing"
                        )

                    break

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
        action['faction'] = self.character_state.faction  # Track faction affiliation
        action['is_free_action'] = is_free_action  # Mark free inter-party dialogue

        # Add inventory info for rituals
        if action_declaration.is_ritual or action_declaration.action_type == 'ritual':
            action['has_offering'] = self.character_state.has_offering()
            action['has_primary_tool'] = self.character_state.has_focus()
        else:
            action['has_offering'] = False
            action['has_primary_tool'] = False

        # Send action declaration
        self.send_message_sync(
            MessageType.ACTION_DECLARED,
            None,
            action
        )

        # Display with character voice
        print(f"\n[{self.character_state.name}] {action_declaration.description}")
        print(f"   └─ {action_declaration.get_summary()}")

        # If this was a free action (inter-party dialogue), generate a second action
        if is_free_action and not self.free_action_used:
            self.free_action_used = True
            print(f"[{self.character_state.name}] Free action used - requesting main action...")
            await asyncio.sleep(0.5)  # Small delay for readability

            try:
                # Generate main action (excluding dialogue to avoid infinite loop)
                if self.llm_config:
                    main_action = await self._generate_llm_action_structured(recent_intents, exclude_dialogue=True)
                else:
                    main_action = self._generate_simple_action(recent_intents, risk_tolerance, void_curiosity, exclude_dialogue=True)
            except Exception as e:
                logger.error(f"Failed to generate main action after free action: {e}")
                return  # Skip second action on error

            logger.debug(f"Main action generated: {main_action.intent}")

            # Apply same routing and validation
            main_routed_attr, main_routed_skill, main_rationale = router.route_action(
                main_action.intent,
                main_action.action_type,
                self.character_state.skills,
                router.is_explicit_ritual(main_action.intent),
                declared_skill=main_action.skill,
                other_players=other_players  # Use same other_players list
            )

            if main_routed_attr != main_action.attribute or main_routed_skill != main_action.skill:
                print(f"[{self.character_state.name}] Routed: {main_action.attribute}×{main_action.skill or 'None'} → {main_routed_attr}×{main_routed_skill or 'None'} ({main_rationale})")
                main_action.attribute = main_routed_attr
                main_action.skill = main_routed_skill

            # Convert and send
            main_action_dict = main_action.to_dict()
            main_action_dict['attribute_value'] = self.character_state.attributes.get(main_action.attribute, 3)
            main_action_dict['skill_value'] = get_character_skill_value(
                self.character_state.skills,
                main_action.skill,
                fallback_value=0
            )
            main_action_dict['character'] = self.character_state.name
            main_action_dict['agent_id'] = self.agent_id
            main_action_dict['faction'] = self.character_state.faction
            main_action_dict['is_free_action'] = False

            if main_action.is_ritual or main_action.action_type == 'ritual':
                main_action_dict['has_offering'] = self.character_state.has_offering()
                main_action_dict['has_primary_tool'] = self.character_state.has_focus()
            else:
                main_action_dict['has_offering'] = False
                main_action_dict['has_primary_tool'] = False

            logger.debug(f"Sending main action: {main_action_dict['intent']}")
            self.send_message_sync(
                MessageType.ACTION_DECLARED,
                None,
                main_action_dict
            )

            # Display with character voice
            print(f"\n[{self.character_state.name}] **MAIN ACTION:** {main_action.description}")
            print(f"   └─ {main_action.get_summary()}")
            logger.info(f"{self.character_state.name} completed 2-action turn (free + main)")
        
    async def _handle_action_resolved(self, message: Message):
        """Handle action resolution from DM."""
        # Only process resolutions for this specific agent (filter out broadcasts meant for others)
        resolved_agent_id = message.payload.get('agent_id')
        if resolved_agent_id != self.agent_id:
            return  # This resolution is for another agent

        outcome = message.payload.get('outcome', {})
        narration = message.payload.get('narration', '')

        print(f"\n[{self.character_state.name}] Received resolution")

        # Consume offering if it was used in the action
        original_action = message.payload.get('original_action', {})
        if original_action.get('has_offering', False):
            if self.character_state.consume_offering():
                print(f"[{self.character_state.name}] Consumed offering")

        # Update void state from mechanics engine
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            void_state = mechanics.get_void_state(self.agent_id)
            self.character_state.void_score = void_state.score

            # Note: Void changes are already displayed in DM narration (⚫ Void: X → Y)
            # Suppressing duplicate player-side print to avoid repetition
            # if len(void_state.history) > 0:
            #     last_change = void_state.history[-1]
            #     if last_change['new_score'] != last_change['old_score']:
            #         print(f"[{self.character_state.name}] Void: {last_change['old_score']} → {last_change['new_score']} ({last_change['reason']})")

        # Update character state based on outcome (legacy path - usually handled by mechanics engine)
        if 'void_gained' in outcome:
            self.character_state.void_score += outcome['void_gained']
            # Suppressed: void changes already shown in DM narration
            # print(f"[{self.character_state.name}] Void Score: {self.character_state.void_score}")

        if 'soulcredit_cost' in outcome:
            self.character_state.soulcredit -= outcome['soulcredit_cost']
            print(f"[{self.character_state.name}] Soulcredit: {self.character_state.soulcredit}")

        # Handle vendor purchases - deduct currency if action succeeded
        intent = original_action.get('intent', '').lower()
        if ('purchase' in intent or 'buy' in intent) and outcome.get('success', False):
            self._process_purchase(intent, outcome)

        # Handle currency/item transfers between players
        if ('give' in intent or 'transfer' in intent or 'pool' in intent) and outcome.get('success', False):
            self._process_transfer(intent, outcome)

    def _process_purchase(self, intent: str, outcome: Dict[str, Any]):
        """Process a successful purchase and deduct currency."""
        # Simple item price lookup (prices from energy_economy.py)
        item_prices = {
            'breathwater flask': {'drip': 2},
            'dripfruit chews': {'drip': 1},
            'med kit (basic)': {'drip': 5},
            'med kit (tactical)': {'drip': 6},
            'ration pack': {'drip': 2},
            'glowsticks': {'breath': 8},
            'comm unit': {'drip': 3},
            'sparksticks': {'breath': 3},
            'echo-calibrator': {'spark': 8},
            'scrambled id chip': {'spark': 4},
            'bond insurance policy': {'spark': 12},
            'data slate (encrypted)': {'drip': 10},
            'incense stick': {'breath': 10},
            'ritual altar access': {'spark': 1},
            'void scanner (basic)': {'spark': 4},
        }

        # Extract item name from intent (very simple parsing)
        purchased_item = None
        for item_name in item_prices.keys():
            if item_name in intent:
                purchased_item = item_name
                break

        if purchased_item and self.character_state.energy_inventory:
            price = item_prices[purchased_item]
            currency_type = list(price.keys())[0]
            amount = price[currency_type]

            # Attempt to spend currency
            if self.character_state.energy_inventory.spend_currency(currency_type, amount):
                logger.info(f"{self.character_state.name} purchased {purchased_item} for {amount} {currency_type}")
                print(f"[{self.character_state.name}] 💰 Purchased {purchased_item} (-{amount} {currency_type})")
                print(f"[{self.character_state.name}] Currency: {self.character_state.energy_inventory.spark} Spark, {self.character_state.energy_inventory.drip} Drip, {self.character_state.energy_inventory.breath} Breath")
            else:
                logger.warning(f"{self.character_state.name} couldn't afford {purchased_item} ({amount} {currency_type})")
                print(f"[{self.character_state.name}] ⚠️ Insufficient {currency_type} for {purchased_item}")

    def _process_transfer(self, intent: str, outcome: Dict[str, Any]):
        """Process currency or item transfers between players."""
        # Extract recipient name and amount from intent
        # Format: "Give 2 Spark to Mira" or "Transfer 5 Drip to Kress"
        import re

        # Find currency type and amount
        currency_match = re.search(r'(\d+)\s+(spark|drip|grain|breath)', intent, re.IGNORECASE)
        if not currency_match:
            return  # Not a currency transfer

        amount = int(currency_match.group(1))
        currency_type = currency_match.group(2).lower()

        # Find recipient (character name)
        # Look for "to [Name]" pattern
        recipient_match = re.search(r'to\s+(\w+(?:\s+\w+)*)', intent, re.IGNORECASE)
        if not recipient_match:
            return

        recipient_name = recipient_match.group(1).strip()

        # Find the recipient character via shared state
        if not self.shared_state:
            logger.warning("Cannot transfer without shared state")
            return

        # Get all other players
        other_players = self.shared_state.get_other_players(self.agent_id)
        recipient_agent = None

        for player in other_players:
            if recipient_name.lower() in player.get('name', '').lower():
                # Found the recipient! Get their agent from session
                # We need to access the actual agent object to modify their inventory
                # This is a bit hacky - we'll store the transfer in shared state for now
                recipient_agent = player
                break

        if not recipient_agent:
            logger.warning(f"Could not find recipient: {recipient_name}")
            print(f"[{self.character_state.name}] ⚠️ Could not find {recipient_name} to transfer to")
            return

        # Attempt the transfer
        if self.character_state.energy_inventory.spend_currency(currency_type, amount):
            # Store pending transfer in shared state
            if not hasattr(self.shared_state, 'pending_transfers'):
                self.shared_state.pending_transfers = []

            self.shared_state.pending_transfers.append({
                'from': self.agent_id,
                'to': recipient_agent.get('agent_id'),
                'currency_type': currency_type,
                'amount': amount,
                'from_name': self.character_state.name,
                'to_name': recipient_agent.get('name')
            })

            logger.info(f"{self.character_state.name} transferred {amount} {currency_type} to {recipient_name}")
            print(f"[{self.character_state.name}] 💸 Gave {amount} {currency_type} to {recipient_name}")
            print(f"[{self.character_state.name}] Remaining: {self.character_state.energy_inventory.spark} Spark, {self.character_state.energy_inventory.drip} Drip, {self.character_state.energy_inventory.breath} Breath")
        else:
            logger.warning(f"{self.character_state.name} couldn't afford to transfer {amount} {currency_type}")
            print(f"[{self.character_state.name}] ⚠️ Insufficient {currency_type} to give")

    def _process_incoming_transfers(self):
        """Check for and accept pending transfers addressed to this agent."""
        if not self.shared_state or not hasattr(self.shared_state, 'pending_transfers'):
            return

        # Find transfers for this agent
        incoming = [t for t in self.shared_state.pending_transfers if t['to'] == self.agent_id]

        for transfer in incoming:
            # Add the currency
            self.character_state.energy_inventory.add_currency(
                transfer['currency_type'],
                transfer['amount']
            )

            logger.info(f"{self.character_state.name} received {transfer['amount']} {transfer['currency_type']} from {transfer['from_name']}")
            print(f"[{self.character_state.name}] 💰 Received {transfer['amount']} {transfer['currency_type']} from {transfer['from_name']}")
            print(f"[{self.character_state.name}] New total: {self.character_state.energy_inventory.spark} Spark, {self.character_state.energy_inventory.drip} Drip, {self.character_state.energy_inventory.breath} Breath")

            # Remove from pending
            self.shared_state.pending_transfers.remove(transfer)

    async def _handle_dm_narration(self, message: Message):
        """Handle general DM narration."""
        # Don't echo DM narration - users can see it from DM's output directly
        # This prevents duplicate display of synthesis and other DM messages

        # Still prompt human-controlled characters for response
        narration = message.payload.get('narration', '')
        if narration and self.human_controlled:
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

        # Display inventory organized by category
        print("\nInventory:")

        consumables = {k: v for k, v in self.character_state.inventory.items()
                      if 'offering' in k or 'stimulant' in k or 'crystal' in k}
        tools = {k: v for k, v in self.character_state.inventory.items()
                if 'focus' in k or 'kit' in k or 'scanner' in k or 'tuner' in k or 'module' in k}
        utility = {k: v for k, v in self.character_state.inventory.items()
                  if k not in consumables and k not in tools}

        if any(v > 0 for v in consumables.values()):
            print("  Consumables:")
            for item, count in consumables.items():
                if count > 0:
                    print(f"    - {item.replace('_', ' ').title()}: {count}")

        if any(v > 0 for v in tools.values()):
            print("  Tools:")
            for item, count in tools.items():
                if count > 0:
                    print(f"    - {item.replace('_', ' ').title()}: {count}")

        if any(v > 0 for v in utility.values()):
            print("  Utility:")
            for item, count in utility.items():
                if count > 0:
                    print(f"    - {item.replace('_', ' ').title()}: {count}")

        print("=" * 30)
        
    def toggle_human_control(self):
        """Toggle between human and AI control."""
        self.human_controlled = not self.human_controlled
        status = "HUMAN" if self.human_controlled else "AI"
        print(f"[{status} - {self.character_state.name}] Control switched to {status} mode")

        if self.human_controlled:
            print("Available commands: explore, interact, ritual, combat, status, release_control")
            print("Or type any freeform action description")

    async def _generate_llm_action_structured(self, recent_intents: List[str], exclude_dialogue: bool = False):
        """Generate structured action using LLM with enhanced prompts."""
        from .enhanced_prompts import get_player_system_prompt
        from .action_schema import ActionDeclaration

        # Get other party members for dialogue prompts
        other_players = []
        if self.shared_state:
            other_players = self.shared_state.get_other_players(self.agent_id)

        # Build system prompt with mechanical scaffolding
        # Note: Knowledge context is empty by default - agents can research when needed
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
            void_score=self.character_state.void_score,
            other_party_members=other_players,
            energy_inventory=self.character_state.energy_inventory.as_dict() if self.character_state.energy_inventory else None,
            knowledge_context=""  # Empty - they can research if they want
        )

        scenario_context = ""
        if self.current_scenario:
            vendor_info = ""
            if self.current_scenario.get('active_vendor'):
                vendor = self.current_scenario['active_vendor']
                vendor_info = f"""

**💰 VENDOR AVAILABLE: {vendor['name']}**
- Type: {vendor['type']}
- Faction: {vendor['faction']}
- "{vendor['greeting']}"
- Sample goods: {', '.join(vendor.get('inventory_preview', []))}

You can purchase items, barter, or ask for information! Use your currency (Sparks, Drips, Breath, Grain).
"""

            # Get clock states with semantic guidance
            clock_context = ""
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics and mechanics.scene_clocks:
                    clock_lines = []
                    for clock_name, clock in mechanics.scene_clocks.items():
                        if clock.filled:
                            overflow = clock.current - clock.maximum
                            if overflow > 0:
                                status = f"⚠️  {clock.current}/{clock.maximum} (OVERFLOWING +{overflow})"
                            else:
                                status = f"🔔 {clock.current}/{clock.maximum} (FILLED)"
                        else:
                            status = f"{clock.current}/{clock.maximum}"

                        clock_line = f"- **{clock_name}**: {status}"
                        if clock.advance_means:
                            clock_line += f"\n  Advance = {clock.advance_means}"
                        if clock.regress_means:
                            clock_line += f" | Regress = {clock.regress_means}"
                        if clock.filled_consequence and clock.filled:
                            clock_line += f"\n  🎯 Consequence: {clock.filled_consequence}"

                        clock_lines.append(clock_line)

                    if clock_lines:
                        clock_context = "\n\n📊 **Current Situation Clocks:**\n" + "\n".join(clock_lines)
                        clock_context += "\n(Your actions can advance or regress these clocks)"

            scenario_context = f"""
Current Scenario: {self.current_scenario.get('theme', 'Unknown')}
Location: {self.current_scenario.get('location', 'Unknown')}
Situation: {self.current_scenario.get('situation', 'Unknown')}
{clock_context}
{vendor_info}
**Your Affiliation**: {self.character_state.faction}
- Consider how your background and affiliations might be relevant to this situation
- Others can see your affiliation unless you actively disguise it
"""

        # Add tactical combat context (only when enemies are active)
        tactical_combat_context = ""
        logger.debug(f"Checking tactical combat context for {self.character_state.name}")
        logger.debug(f"  has shared_state: {self.shared_state is not None}")
        if self.shared_state:
            logger.debug(f"  has enemy_combat attr: {hasattr(self.shared_state, 'enemy_combat')}")

        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            logger.debug(f"  enemy_combat exists: {enemy_combat is not None}")
            if enemy_combat:
                logger.debug(f"  enemy_combat.enabled: {enemy_combat.enabled}")
                logger.debug(f"  enemy_agents count: {len(enemy_combat.enemy_agents)}")

            if enemy_combat and enemy_combat.enabled and len(enemy_combat.enemy_agents) > 0:
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)
                logger.debug(f"  active_enemies count: {len(active_enemies)}")

                if active_enemies:
                    # Build enemy positions summary
                    enemy_positions = []
                    for enemy in active_enemies:
                        enemy_positions.append(f"{enemy.name} at {enemy.position} ({enemy.health}/{enemy.max_health} HP)")
                    enemy_positions_text = "\n  - ".join(enemy_positions)

                    tactical_combat_context = f"""

⚔️  **ACTIVE COMBAT - ENEMIES ARE ATTACKING YOU NOW!** ⚔️

🚨 **YOU ARE IN A FIREFIGHT!** These enemies are actively trying to KILL you right now.

**DEFAULT ACTION: ATTACK!**
Unless you have a SPECIFIC tactical reason (wrong range for weapon, need cover from heavy fire,
need to charge into melee, etc.), your action should be ATTACKING an enemy.

🎯 **Enemy Targets:**
  {enemy_positions_text}

**Combat Priority:**
1. **ATTACK** - Shoot/stab/punch an enemy (specify which enemy and how)
   - Ranged attacks: Use Agility × Combat skill
   - Melee attacks: Use Agility × Combat skill (or Strength × Combat for heavy weapons)
2. **REPOSITION WHILE ATTACKING** - Move + shoot (if needed for range/cover)
3. **Only reposition without attacking if:**
   - You're at completely wrong range for your weapon
   - You need to charge into melee distance
   - You're being overwhelmed and need to retreat

⚠️  DO NOT endlessly reposition without attacking - you're in a fight, ACT like it!
⚠️  Your Combat skill is {self.character_state.skills.get('Combat', 0)} - USE IT!

🎯 **CRITICAL REQUIREMENT - POSITION TAGS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  When moving, you MUST include position tags or your position will NOT update!

Format: [TARGET_POSITION: PositionName]

✅ GOOD Examples (USE THESE):
  "I charge forward [TARGET_POSITION: Engaged]"
  "I fall back to cover [TARGET_POSITION: Far-PC]"
  "I circle to flank them [TARGET_POSITION: Near-Enemy]"
  "I sprint to extreme range [TARGET_POSITION: Extreme-PC]"
  "I advance cautiously [TARGET_POSITION: Near-Enemy]"

❌ BAD Examples (DON'T do this - position won't update):
  "I charge forward" ← Missing tag!
  "I move to better position" ← Missing tag!
  "I carefully reposition" ← Missing tag!

Your Position: **{self.position}**
Available Positions: Engaged, Near-PC, Far-PC, Extreme-PC, Near-Enemy, Far-Enemy, Extreme-Enemy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enemy Positions:
  - {enemy_positions_text}

**MOVEMENT SYSTEM** - You have two options:

1) **Basic Tactical Movement** (automatic, no roll needed):
   - Declare target position with [TARGET_POSITION: ...] tag (REQUIRED!)
   - Movement happens automatically based on action economy:
     * Minor Action: Shift 1 band (Near-PC → Engaged OR Near-PC → Far-PC)
     * Major Action: Shift 2 bands (Far-PC → Engaged OR Engaged → Far-PC)

2) **Skill-Based Movement** (roll for persistent benefit):
   - Still use [TARGET_POSITION: ...] tag + describe HOW you move
   - Movement happens, roll determines if you get lasting advantage
   - Examples:
     * "I use Stealth to circle behind them [TARGET_POSITION: Near-Enemy]" → On success: Move + Unseen
     * "I use Athletics to sprint for cover [TARGET_POSITION: Far-PC]" → On success: Move + Cover token
     * "I disengage using Athletics [TARGET_POSITION: Far-PC]" → On success: Move without Breakaway attack

**Tactical Actions:**
- **Attack**: Standard combat action (range penalties apply)
- **Claim Token (Minor)**: Grab Cover/High Ground (if available)
- **Charge (Major)**: Move to Engaged + attack (+2 damage, -2 defense)

Range Penalties (same ring/same side = Melee, 0 penalty):
- Melee (0): Same ring AND same hemisphere
- Near (-2): 1 ring apart OR different hemisphere in Near
- Far (-4): 2 rings apart OR different hemisphere in Far
- Extreme (-6): 3+ rings apart

**REMEMBER:** Always include [TARGET_POSITION: ...] when moving or your position stays unchanged!
"""

        # Add party discoveries to reduce repetition and encourage dialogue
        party_knowledge = ""
        if self.shared_state:
            discoveries = self.shared_state.get_recent_discoveries(limit=5)
            if discoveries:
                party_knowledge = "\n**What the party has discovered:**\n"
                for disc_info in discoveries:
                    character = disc_info.get('character', 'Unknown')
                    discovery = disc_info.get('discovery', '')
                    party_knowledge += f"- **{character}** discovered: {discovery}\n"
                party_knowledge += "\nYou can:\n"
                party_knowledge += "- Build on these discoveries with new investigation\n"
                party_knowledge += "- Talk to your companions about what they found\n"
                party_knowledge += "- Explore a completely different angle\n"

        prompt = f"""{system_prompt}

{scenario_context}
{tactical_combat_context}
{party_knowledge}

Declare your next action using the required format:
INTENT: [what you're doing]
ATTRIBUTE: [which attribute]
SKILL: [which skill or None]
DIFFICULTY: [estimate]
JUSTIFICATION: [why that difficulty]
ACTION_TYPE: [explore/investigate/ritual/social/combat/technical]
TARGET_POSITION: [if moving: Engaged/Near-PC/Far-PC/Extreme-PC/Near-Enemy/Far-Enemy/Extreme-Enemy, otherwise: None]
DESCRIPTION: [narrative description]

**COMBAT EXAMPLES:**

ATTACKING (most common - do this!):
```
INTENT: Shoot Void Spawn with rifle
ATTRIBUTE: Agility
SKILL: Combat
DIFFICULTY: 20
JUSTIFICATION: standard combat difficulty
ACTION_TYPE: combat
TARGET_POSITION: None
DESCRIPTION: I aim carefully and fire controlled bursts at the Void Spawn
```

ATTACKING WHILE MOVING:
```
INTENT: Advance and shoot Assault Team
ATTRIBUTE: Agility
SKILL: Combat
DIFFICULTY: 22
JUSTIFICATION: moving while shooting is slightly harder
ACTION_TYPE: combat
TARGET_POSITION: Near-Enemy
DESCRIPTION: I move to better range while firing at the Assault Team
```

CHARGING INTO MELEE:
```
INTENT: Charge and attack with knife
ATTRIBUTE: Agility
SKILL: Combat
DIFFICULTY: 18
JUSTIFICATION: charging gives bonus to hit
ACTION_TYPE: combat
TARGET_POSITION: Engaged
DESCRIPTION: I sprint forward and engage in close combat
```

REPOSITIONING ONLY (use sparingly - only when needed):
```
INTENT: Fall back to cover
ATTRIBUTE: Agility
SKILL: Athletics
DIFFICULTY: 18
JUSTIFICATION: tactical movement under fire
ACTION_TYPE: combat
TARGET_POSITION: Far-PC
DESCRIPTION: I retreat to better defensive position
```"""

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

            # Check if agent requested a rules/lore lookup
            if 'LOOKUP:' in llm_text:
                logger.info(f"🔍 Agent {self.character_state.name} requested a lookup")
                lookup_result = await self._handle_lookup_request(llm_text, prompt, provider, model, temperature)
                if lookup_result:
                    llm_text = lookup_result  # Use the response after lookup

            # Parse LLM response into ActionDeclaration
            action = self._parse_action_from_llm(llm_text)
            return action

        except Exception as e:
            logger.error(f"LLM API error for player action: {e}")
            # Fallback to simple action
            return self._generate_simple_action(recent_intents, self.personality.get('riskTolerance', 5), self.personality.get('voidCuriosity', 3))

    async def _handle_lookup_request(self, initial_response: str, original_prompt: str, provider: str, model: str, temperature: float):
        """Handle a LOOKUP request from the agent."""
        import re

        # Extract the lookup query
        lookup_match = re.search(r'LOOKUP:\s*(.+?)(?:\n|$)', initial_response, re.IGNORECASE | re.DOTALL)
        if not lookup_match:
            return None

        lookup_query = lookup_match.group(1).strip()

        # Clean up markdown formatting from query
        lookup_query = lookup_query.replace('```', '').strip()
        lookup_query = lookup_query.replace('`', '').strip()

        # If query is too short or empty after cleaning, skip
        if len(lookup_query) < 3:
            logger.warning(f"  LOOKUP query too short or empty after cleaning: '{lookup_query}'")
            return None

        logger.info(f"  Query: '{lookup_query}'")

        # Query ChromaDB
        knowledge_context = ""
        if self.shared_state:
            knowledge = self.shared_state.get_knowledge_retrieval()
            if knowledge:
                from .enhanced_prompts import format_knowledge_for_prompt
                knowledge_context = format_knowledge_for_prompt(knowledge, lookup_query, max_length=800)

        if not knowledge_context:
            logger.warning("  No results found for lookup query")
            knowledge_context = "No relevant information found in the knowledge base."

        # Send results back to agent and request final action
        followup_prompt = f"""{original_prompt}

**LOOKUP RESULTS:**
{knowledge_context}

Now that you have this information, declare your action using the required format."""

        try:
            if provider == 'anthropic':
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=300,
                    temperature=temperature,
                    messages=[{"role": "user", "content": followup_prompt}]
                )
                return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Error in lookup followup: {e}")
            return None

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

        # Valid tactical positions
        VALID_POSITIONS = {
            'engaged', 'near-pc', 'far-pc', 'extreme-pc',
            'near-enemy', 'far-enemy', 'extreme-enemy'
        }

        # Track if player specified a position change
        target_position = None

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
                elif 'target_position' in key:
                    # Extract position if specified - STORE but don't apply yet
                    value_lower = value.lower()
                    if value_lower != 'none' and value_lower in VALID_POSITIONS:
                        target_position = value
                        data['target_position'] = target_position
                        logger.info(f"{self.character_state.name} declared intent to move: {self.position} → {target_position}")
                elif 'description' in key:
                    data['description'] = value

        # Store target position for later application during execution
        # (Position changes happen in execution phase, not declaration phase)

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

    def _generate_simple_action(self, recent_intents: List[str], risk_tolerance: int, void_curiosity: int, exclude_dialogue: bool = False):
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

        # 30% chance of social interaction with other players (unless excluded)
        if not exclude_dialogue and 'social' not in recent_types and random.random() < 0.3:
            # Get other player names for character-specific dialogue
            other_players = []
            if self.shared_state:
                other_players = self.shared_state.get_other_players(self.agent_id)

            if other_players:
                # Character-specific dialogue actions
                target = random.choice(other_players)
                social_actions = [
                    f"Ask {target} about their findings",
                    f"Share observations with {target}",
                    f"Discuss the situation with {target}",
                    f"Coordinate next steps with {target}",
                    f"Tell {target} what you've learned",
                ]
            else:
                # Fallback to generic group dialogue
                social_actions = [
                    "Discuss findings with the group",
                    "Share observations with companions",
                    "Coordinate strategy with party members",
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