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

        # Set up player-specific message handlers
        self.message_handlers[MessageType.SCENARIO_SETUP] = self._handle_scenario_setup
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
            inventory=inventory
        )
        
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

        # Apply mechanical validation and corrections
        from .skill_mapping import validate_action_mechanics, get_character_skill_value, RITUAL_ATTRIBUTE, RITUAL_SKILL
        from .action_router import ActionRouter

        # Use action router to determine correct attribute/skill
        router = ActionRouter()
        is_explicit_ritual = router.is_explicit_ritual(action_declaration.intent)

        # Get other player names for inter-party ritual detection
        other_players = []
        if self.shared_state:
            other_players = self.shared_state.get_other_players(self.agent_id)

        # Route action to appropriate attribute + skill
        routed_attr, routed_skill, rationale = router.route_action(
            action_declaration.intent,
            action_declaration.action_type,
            self.character_state.skills,
            is_explicit_ritual,
            declared_skill=action_declaration.skill,  # Pass declared skill so router can trust it
            other_players=other_players  # Pass other player names for inter-party detection
        )

        # Apply routing if it differs from declared
        if routed_attr != action_declaration.attribute or routed_skill != action_declaration.skill:
            print(f"[{self.character_state.name}] Routed: {action_declaration.attribute}×{action_declaration.skill or 'None'} → {routed_attr}×{routed_skill or 'None'} ({rationale})")
            action_declaration.attribute = routed_attr
            action_declaration.skill = routed_skill

        # Mark as ritual if explicitly stated OR if action_type is 'ritual'
        # This ensures both LLM-declared rituals and keyword-detected rituals are flagged
        # EXCEPTIONS:
        #   - If action was routed to dialogue (Empathy × Charm/Counsel), don't override
        #   - If action was routed to Intimacy Ritual (social/bonding ritual), don't override
        is_dialogue_action = (routed_attr == 'Empathy' and routed_skill in ['Charm', 'Counsel'])
        is_intimacy_ritual = (routed_attr == 'Empathy' and routed_skill == 'Intimacy Ritual')

        if not is_dialogue_action and not is_intimacy_ritual and (is_explicit_ritual or action_declaration.action_type == 'ritual'):
            action_declaration.is_ritual = True
            action_declaration.action_type = 'ritual'
            # Ensure ritual mechanics (Willpower × Astral Arts)
            if action_declaration.attribute != 'Willpower' or action_declaration.skill != 'Astral Arts':
                print(f"[{self.character_state.name}] Ritual detected - enforcing Willpower × Astral Arts")
                action_declaration.attribute = 'Willpower'
                action_declaration.skill = 'Astral Arts'

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

        # Detect if this is inter-party communication (free action)
        # This includes dialogue (Charm/Counsel) and social rituals (Intimacy Ritual)
        is_free_action = False
        if (is_dialogue_action or is_intimacy_ritual) and self.shared_state:
            # Check if intent mentions any party member name
            intent_lower = action_declaration.intent.lower()
            for player_name in other_players:
                if player_name.lower() in intent_lower:
                    is_free_action = True
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
        if is_free_action:
            print(f"[{self.character_state.name}] Free action used - generating main action...")
            await asyncio.sleep(0.5)  # Small delay for readability

            # Generate main action (excluding dialogue to avoid infinite loop)
            if self.llm_config:
                main_action = await self._generate_llm_action_structured(recent_intents, exclude_dialogue=True)
            else:
                main_action = self._generate_simple_action(recent_intents, risk_tolerance, void_curiosity, exclude_dialogue=True)

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

            self.send_message_sync(
                MessageType.ACTION_DECLARED,
                None,
                main_action_dict
            )

            # Display with character voice
            print(f"\n[{self.character_state.name}] {main_action.description}")
            print(f"   └─ {main_action.get_summary()}")
        
    async def _handle_action_resolved(self, message: Message):
        """Handle action resolution from DM."""
        if message.recipient == self.agent_id or message.recipient is None:
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

            scenario_context = f"""
Current Scenario: {self.current_scenario.get('theme', 'Unknown')}
Location: {self.current_scenario.get('location', 'Unknown')}
Situation: {self.current_scenario.get('situation', 'Unknown')}
{vendor_info}
**Your Affiliation**: {self.character_state.faction}
- Consider how your background and affiliations might be relevant to this situation
- Others can see your affiliation unless you actively disguise it
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
{party_knowledge}

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