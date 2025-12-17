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
from .energy_economy import EnergyPurse, Seed, SeedType, Element, create_raw_seed
from .prompt_loader import load_agent_prompt, compose_sections
from .schemas.story_events import NarrativeMemory
from .schemas.shared_types import Bond
from .awareness import NarrationEntry

logger = logging.getLogger(__name__)

# Constants for prompt text
DECLARED_ACTIONS_HEADER = "Declared Actions This Round"


@dataclass
class CharacterState:
    """Current character state."""
    name: str
    faction: str
    attributes: Dict[str, int]
    skills: Dict[str, int]
    void_score: int
    soulcredit: int
    bonds: List[Bond]  # Formal metaphysical connections (max 3, Freeborn max 1)
    goals: List[str]
    pronouns: str = "they/them"  # Default to gender-neutral
    inventory: Dict[str, int] = None
    energy_purse: Optional['EnergyPurse'] = None
    item_metadata: Dict[str, Dict[str, Any]] = None  # Tracks usage counts, durability, etc.

    def __post_init__(self):
        """Initialize default inventory and energy purse if not provided."""
        # Initialize energy purse with randomized currency
        if self.energy_purse is None:
            self.energy_purse = EnergyPurse(
                breath=random.randint(5, 15),  # Variable starting amounts
                drip=random.randint(3, 10),
                grain=random.randint(0, 3),
                spark=random.randint(0, 2),  # Most start with 0-2 Spark
                seeds=[]
            )
            # Add some starter seeds based on faction (varying freshness)
            if 'Tempest' in self.faction:
                # Tempest gets Hollow seeds (stable, no decay)
                self.energy_purse.add_seed(Seed(SeedType.HOLLOW, origin="tempest_supply"))
            elif 'Sovereign' in self.faction or 'Pantheon' in self.faction:
                # Pro-Nexus factions get Attuned seeds (stable)
                self.energy_purse.add_seed(Seed(SeedType.ATTUNED, element=Element.SPIRIT, origin="nexus_sanctified"))
            else:
                # Others get Raw seeds with random freshness (might be aged/old)
                raw_seed = create_raw_seed(origin="leyline_harvest", freshness="random")
                self.energy_purse.add_seed(raw_seed)

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

        if self.item_metadata is None:
            self.item_metadata = {}
            # Initialize metadata for items that need tracking
            # Echo-Calibrator usage will be tracked when purchased

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
        llm_logger: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        agent_prompt_logger: Optional[Any] = None,
    ):
        super().__init__(agent_id, socket_path)
        self.character_config = character_config
        self.llm_config = llm_config or {}
        self.character_state: Optional[CharacterState] = None
        self.human_controlled = False
        self.personality = character_config.get('personality', {})
        self.personality_notes = character_config.get('personality_notes', '')
        self.direction = character_config.get('direction', '')
        self.current_scenario: Optional[Dict[str, Any]] = None
        self.voice_profile = voice_profile
        self.shared_state = shared_state
        self._prompt_enricher = prompt_enricher
        self._history_supplier = history_supplier
        self.llm_logger = llm_logger  # LLMCallLogger for replay functionality
        self.agent_prompt_logger = agent_prompt_logger  # AgentPromptLogger for human-readable debugging
        self._last_prompt_metadata = None  # Track prompt version/metadata for logging

        # LLM client - DEPRECATED (kept for replay compatibility with MockLLMClient)
        # Modern code uses llm_provider instead
        if llm_client:
            self.llm_client = llm_client
        else:
            self.llm_client = None  # No longer needed - use llm_provider

        # LLM Provider for structured output (supports all providers: Anthropic, OpenAI, local)
        # Only create if not in replay mode (llm_client injected)
        if not llm_client:
            from .llm_provider import LLMConfig, create_provider
            try:
                provider_config = LLMConfig(
                    provider=self.llm_config.get('provider', 'anthropic'),
                    model=self.llm_config.get('model', 'claude-sonnet-4-5'),
                    max_tokens=self.llm_config.get('max_tokens', 1000),
                    temperature=self.llm_config.get('temperature', 1.0)
                )
                self.llm_provider = create_provider(provider_config)
                logger.debug(f"Player {self.agent_id}: LLM provider initialized ({provider_config.provider}:{provider_config.model})")
            except Exception as e:
                logger.warning(f"Player {self.agent_id}: Failed to create LLM provider: {e}")
                self.llm_provider = None
        else:
            # Replay mode - no structured output
            self.llm_provider = None

        # Narrative context tracking (for player awareness of story progression)
        self.recent_narrations: List[str] = []  # Last 5 action resolution narrations (FIFO)
        self.last_round_synthesis: Optional[str] = None  # Most recent round synthesis from DM
        # Stores ALL declarations this round (PCs + enemies) with initiative for tactical display
        # {character_name: (description, intent, target, weapon, reasoning, initiative_score)}
        self.declared_actions_this_round: Dict[str, Tuple[str, str, Optional[str], Optional[str], str, int]] = {}

        # Persistent narrative memory (tracks journey across session)
        self.narrative_memory = NarrativeMemory(
            locations_visited=[],
            story_beats=[],
            story_summary=""
        )

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

        # Stabilization state (YAGS First Aid system)
        self.is_stabilized = False  # True = bleeding stopped, no more death checks needed
        self.is_extracted = False  # True = medevac arrived, character removed from combat

        # Weapon inventory (initialized in on_start)
        from .weapons import Weapon
        self.equipped_weapons = {
            "primary": None,  # Currently equipped primary weapon (Weapon object)
            "sidearm": None,  # Currently equipped sidearm (Weapon object)
        }
        self.weapon_inventory = []  # List of additional Weapon objects in inventory

        # Free action tracking (one per round)
        self.free_action_used = False

        # Buff tracking (positive effects from allies)
        self.buffs = []  # List of active buffs from ally support

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
        # Load inventory ONLY from config (no defaults - everything comes from session config)
        inventory = self.character_config.get('inventory', {})

        self.character_state = CharacterState(
            name=self.character_config.get('name', f'Player_{self.agent_id}'),
            faction=self.character_config.get('faction', 'Unaffiliated'),
            attributes=self.character_config.get('attributes', {}),
            skills=self.character_config.get('skills', {}),
            void_score=self.character_config.get('void', 0),  # Standardized on "void" key
            soulcredit=self.character_config.get('soulcredit', random.randint(4, 7)),  # Lower, varied starting soulcredit
            bonds=self.character_config.get('bonds', []),
            goals=self.character_config.get('goals', []),
            pronouns=self.character_config.get('pronouns', 'they/them'),
            inventory=inventory
        )

        # Override energy purse with starting_currency from config if provided
        starting_currency = self.character_config.get('starting_currency')
        if starting_currency:
            self.character_state.energy_purse.breath = starting_currency.get('breath', self.character_state.energy_purse.breath)
            self.character_state.energy_purse.drip = starting_currency.get('drip', self.character_state.energy_purse.drip)
            self.character_state.energy_purse.grain = starting_currency.get('grain', self.character_state.energy_purse.grain)
            self.character_state.energy_purse.spark = starting_currency.get('spark', self.character_state.energy_purse.spark)

        # Override seeds with starting_seeds from config if provided
        starting_seeds = self.character_config.get('starting_seeds')
        if starting_seeds:
            from .energy_economy import Seed, SeedType, Element, create_raw_seed
            # Clear auto-generated seeds
            self.character_state.energy_purse.seeds = []
            # Add seeds from config
            for seed_config in starting_seeds:
                if isinstance(seed_config, dict):
                    # Explicit seed configuration
                    seed_type_str = seed_config.get('seed_type', 'RAW')
                    seed_type = SeedType[seed_type_str] if isinstance(seed_type_str, str) else seed_type_str

                    if seed_type == SeedType.RAW:
                        freshness = seed_config.get('freshness', 'fresh')
                        origin = seed_config.get('origin', 'config_specified')
                        seed = create_raw_seed(origin=origin, freshness=freshness)
                    elif seed_type == SeedType.ATTUNED:
                        element_str = seed_config.get('element', 'SPIRIT')
                        element = Element[element_str] if isinstance(element_str, str) else element_str
                        origin = seed_config.get('origin', 'config_specified')
                        seed = Seed(seed_type=SeedType.ATTUNED, element=element, origin=origin)
                    elif seed_type == SeedType.HOLLOW:
                        origin = seed_config.get('origin', 'config_specified')
                        seed = Seed(seed_type=SeedType.HOLLOW, origin=origin)
                    else:
                        raise ValueError(f"Unknown seed_type: {seed_type}")

                    # Override seed ID if provided
                    if 'id' in seed_config:
                        seed.id = seed_config['id']
                    if 'cycles_remaining' in seed_config and seed_type == SeedType.RAW:
                        seed.cycles_remaining = seed_config['cycles_remaining']

                    self.character_state.energy_purse.add_seed(seed)
                else:
                    # Simple string format: "RAW" or "HOLLOW" or "ATTUNED:SPIRIT"
                    raise ValueError("starting_seeds must be list of dicts, not strings")

        # Initialize combat attributes (for enemy attacks to work)
        # Health = Size × 2 + Endurance (YAGS-compliant toughness bonus)
        size = self.character_state.attributes.get('Size', 5)
        endurance = self.character_state.attributes.get('Endurance', 3)
        self.size = size
        # HP = (Size × 2) + Endurance + 13 combat balance bonus
        # Increased from +3 to +13 to support sustained tactical combat (3-4 rounds)
        # e.g., Size 5 + Endurance 3 + 13 = 26 HP (was 16 HP)
        self.max_health = (size * 2) + endurance + 13
        self.health = self.max_health
        self.wounds = 0  # Wound count (tactical module)

        # Soak calculation (YAGS formula + Aeonisk combat balance)
        # YAGS: Soak = Size + Agility + Endurance - 5
        # Aeonisk: +4 combat balance (keeps avg=10 for backwards compatibility)
        SOAK_COMBAT_BALANCE = 4

        agility = self.character_state.attributes.get('Agility', 3)

        base_soak = size + agility + endurance - 5
        self.soak = base_soak + SOAK_COMBAT_BALANCE

        logger.debug(
            f"{self.character_state.name} Soak calculation: "
            f"Size({size}) + Agi({agility}) + End({endurance}) - 5 + balance({SOAK_COMBAT_BALANCE}) = {self.soak}"
        )

        # Initialize weapons from config or use defaults
        from .weapons import get_weapon

        # Support both old structure (weapons: {equipped: {}, carried: []})
        # and new structure (equipped_weapons: {}, carried_weapons: [])
        if 'equipped_weapons' in self.character_config or 'carried_weapons' in self.character_config:
            # New structure (direct top-level keys)
            equipped_config = self.character_config.get('equipped_weapons', {})
            carried_config = self.character_config.get('carried_weapons', [])
        else:
            # Old structure (nested under 'weapons' key)
            weapons_config = self.character_config.get('weapons', {})
            equipped_config = weapons_config.get('equipped', {})
            carried_config = weapons_config.get('carried', [])

        # Apply defaults if nothing specified
        if not equipped_config:
            equipped_config = {
                "primary": "pistol",  # Default lethal sidearm
                "sidearm": "combat_knife"  # Default melee weapon
            }

        # Load equipped weapons
        try:
            if equipped_config.get("primary"):
                self.equipped_weapons["primary"] = get_weapon(equipped_config["primary"])
            if equipped_config.get("sidearm"):
                self.equipped_weapons["sidearm"] = get_weapon(equipped_config["sidearm"])

            # Load carried weapons
            for weapon_id in carried_config:
                self.weapon_inventory.append(get_weapon(weapon_id))

            logger.debug(f"Player {self.character_state.name} equipped: {self.equipped_weapons}, carried: {[w.name for w in self.weapon_inventory]}")
        except KeyError as e:
            logger.error(f"Failed to load weapon for {self.character_state.name}: {e}")
            # Crash on missing weapon - this is a config error that must be fixed
            raise ValueError(
                f"Character '{self.character_state.name}' configured with invalid weapon. "
                f"Check session config and WEAPON_LIBRARY. Error: {e}"
            ) from e

        logger.debug(f"Player {self.agent_id} ({self.character_state.name}) started")

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
        logger.debug(f"Player {self.agent_id} shutting down")

    # === YAGS Combat Lifecycle Properties ===

    @property
    def is_alive(self) -> bool:
        """Check if player is alive (health > 0)."""
        return self.health is not None and self.health > 0

    @property
    def is_in_combat(self) -> bool:
        """
        Check if player can participate in combat.

        Returns False if:
        - Dead (health <= 0 with fatal wounds)
        - Extracted (medevac arrived after stabilization)
        """
        if not self.is_alive:
            return False
        if self.is_extracted:
            return False
        return True

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

    def add_buff(self, effect: str, bonus: int, duration: int, source: str = "unknown"):
        """
        Add a positive buff to this player from an ally action.

        Args:
            effect: Description of the buff (e.g., "aim bonus", "morale boost")
            bonus: Positive modifier to apply
            duration: How many rounds the buff lasts
            source: Who provided the buff
        """
        buff = {
            'effect': effect,
            'bonus': bonus,
            'duration': duration,
            'source': source,
            'rounds_remaining': duration
        }
        self.buffs.append(buff)
        logger.info(f"{self.character_state.name} gained buff: {effect} (+{bonus}) from {source} for {duration} rounds")

    def tick_buffs(self):
        """Reduce buff durations and remove expired buffs."""
        expired_buffs = []
        for buff in self.buffs:
            buff['rounds_remaining'] = buff.get('rounds_remaining', 1) - 1
            if buff['rounds_remaining'] <= 0:
                expired_buffs.append(buff)

        for buff in expired_buffs:
            logger.info(f"{self.character_state.name} buff expired: {buff['effect']}")
            self.buffs.remove(buff)

    async def _handle_scenario_setup(self, message: Message):
        """Handle scenario setup from DM."""
        self.current_scenario = message.payload.get('scenario', {})
        opening = message.payload.get('opening_narration', '')

        # Initialize narrative memory with starting location (round 0)
        starting_location = self.current_scenario.get('location', 'Unknown')
        # Check if location already in list (compare just the location string)
        existing_locations = [loc for _, loc in self.narrative_memory.locations_visited]
        if starting_location and starting_location not in existing_locations:
            self.narrative_memory.locations_visited.append((0, starting_location))
            # Initialize summary with opening context
            self.narrative_memory.story_summary = f"Started at {starting_location}."

        # Scenario is now printed once by session.py, not per-player
        # Only print if human controlled (to notify the human player)
        if self.human_controlled:
            print(f"\n[{self.character_state.name}] === New Scenario ===")
            print(f"Theme: {self.current_scenario.get('theme', 'Unknown')}")
            print(f"Location: {self.current_scenario.get('location', 'Unknown')}")
            print(f"\nDM: {opening}")
            print(f"\n[HUMAN - {self.character_state.name}] Waiting for your input...")

    async def _handle_scenario_update(self, message: Message):
        """Handle mid-game scenario pivot or story advancement from DM."""
        new_theme = message.payload.get('new_theme', 'Unknown')
        new_situation = message.payload.get('new_situation', '')
        pivot_narration = message.payload.get('pivot_narration', '')
        new_location = message.payload.get('new_location', '')  # Story advancement

        # Update scenario with new theme while preserving location
        if self.current_scenario:
            self.current_scenario['theme'] = new_theme
            if new_situation:
                self.current_scenario['situation'] = new_situation
            if new_location:
                self.current_scenario['location'] = new_location
        else:
            self.current_scenario = {
                'theme': new_theme,
                'situation': new_situation
            }

        # Add new location to narrative memory (story advancement)
        existing_locations = [loc for _, loc in self.narrative_memory.locations_visited]
        if new_location and new_location not in existing_locations:
            # Get current round from shared_state
            current_round = 0
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics:
                    current_round = mechanics.current_round or 0
            self.narrative_memory.locations_visited.append((current_round, new_location))

        # Scenario pivot is now printed once by session.py, not per-player
        # Only print if human controlled
        if self.human_controlled:
            print(f"\n[{self.character_state.name}] 🔄 SCENARIO PIVOT: {new_theme}")
            if pivot_narration:
                print(f"    {pivot_narration}")

    async def _handle_action_declared(self, message: Message):
        """Handle action declarations from other combatants - store for tactical awareness."""
        action = message.payload

        # Don't show our own actions (we already printed them)
        if action.get('agent_id') == self.agent_id:
            return

        character_name = action.get('character_name', 'Unknown')
        description = action.get('description', '')
        intent = action.get('intent', '')
        target = action.get('target')  # NEW: targeting info (may be None)
        weapon = action.get('weapon')  # NEW: weapon info (may be None)
        reasoning = action.get('reasoning', '')  # NEW: reasoning (may be empty)
        initiative = action.get('initiative', 0)

        # Store ALL combatant actions for tactical awareness (neutral - no ally/enemy distinction)
        # Store description, intent, target, weapon, and initiative for AI context
        if intent or description:
            self.declared_actions_this_round[character_name] = (description, intent, target, weapon, reasoning, initiative)
            logger.debug(f"Player {self.character_state.name}: Stored action from {character_name} (init {initiative}, target={target})")

    async def _handle_turn_request(self, message: Message):
        """Handle turn request - decide on action."""
        # Reset free action flag each round (prevents bug where main action is skipped in Round 2+)
        self.free_action_used = False
        # NOTE: declared_actions_this_round is now cleared at round start (session.py), not here

        # Store current round and initiative from payload
        self.current_round = message.payload.get('round', 0)
        self.current_initiative = message.payload.get('initiative', 0)

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

        logger.debug(f"[{self.character_state.name}] Declared: {description}")
        
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

        # Validate action (structural validation only - duplicates are allowed by default for combat)
        if validator:
            is_valid, issues = validator.validate_action(action_declaration)
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
            # Check if action targets a party member using target field
            target_agent_id = None
            target_name = None

            if action_declaration.target:
                # Resolve target using target_id_mapper
                target_id_mapper = self.shared_state.target_id_mapper
                if target_id_mapper:
                    # Try to resolve target ID to agent
                    target_agent = target_id_mapper.resolve_target(action_declaration.target)
                    if target_agent:
                        # Check if target is a player (has character_state)
                        if hasattr(target_agent, 'character_state'):
                            target_agent_id = target_agent.agent_id
                            target_name = target_agent.character_state.name
                        # Also check by agent_id against registered players
                        elif hasattr(target_agent, 'agent_id'):
                            for player in self.shared_state.registered_players:
                                if player['agent_id'] == target_agent.agent_id:
                                    target_agent_id = target_agent.agent_id
                                    target_name = player['name']
                                    break

                # If not found via mapper, check if target is a direct name match
                if not target_agent_id:
                    for player in self.shared_state.registered_players:
                        if player['name'].lower() == action_declaration.target.lower():
                            target_agent_id = player['agent_id']
                            target_name = player['name']
                            break

            # If targeting a party member, grant free action + coordination bonus
            if target_agent_id and target_agent_id != self.agent_id and target_name:
                is_free_action = True

                if is_intimacy_ritual:
                    print(f"[{self.character_state.name}] Inter-party ritual detected - FREE ACTION")
                else:
                    print(f"[{self.character_state.name}] Inter-party dialogue detected - FREE ACTION")

                # Grant coordination bonus (inter-party dialogue inherently shares information)
                self.shared_state.grant_coordination_bonus(
                    from_agent=self.agent_id,
                    from_name=self.character_state.name,
                    to_name=target_name,
                    reason="coordinated information sharing"
                )

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

        # Display character declaration in console (for visibility during declaration phase)
        print(f"[{self.character_state.name}] {action_declaration.description}")
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

            # Apply same normalization as first action
            # Only check if action intent mentions "ritual" explicitly
            is_explicit_ritual_main = router.is_explicit_ritual(main_action.intent)
            if is_explicit_ritual_main or main_action.action_type == 'ritual':
                main_action.is_ritual = True
                main_action.action_type = 'ritual'

            # Normalize skill name ONLY if it's an alias
            if main_action.skill:
                original_skill = main_action.skill
                normalized_skill = normalize_skill(main_action.skill)
                if normalized_skill != original_skill:
                    main_action.skill = normalized_skill

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

            # Display main action declaration in console (for visibility during declaration phase)
            print(f"[{self.character_state.name}] **MAIN ACTION:** {main_action.description}")
            print(f"   └─ {main_action.get_summary()}")
            logger.info(f"{self.character_state.name} completed 2-action turn (free + main)")
        
    async def _handle_action_resolved(self, message: Message):
        """Handle action resolution from DM."""
        # Defensive: Check if payload is actually a dict
        if not isinstance(message.payload, dict):
            logger.error(f"Player {self.character_state.name}: Received non-dict payload in ACTION_RESOLVED: {type(message.payload)} = {message.payload}")
            return

        outcome = message.payload.get('outcome', {})
        narration = message.payload.get('narration', '')
        resolved_agent_id = message.payload.get('agent_id')

        # Store ALL action resolution narrations (for tactical awareness)
        # This includes other players' actions and enemy actions
        if narration and resolved_agent_id != 'adjudication':  # Skip adjudication complete signal
            # Get character name for context
            original_action = message.payload.get('original_action', {})
            acting_character = original_action.get('character_name', original_action.get('character', 'Unknown'))

            # Get aware_agents from DM's resolution (empty = public, populated = private)
            aware_agents = message.payload.get('aware_agents', [])

            # Prefix narration with character name for clarity
            prefixed_narration = f"[{acting_character}] {narration}"

            # Store as NarrationEntry with awareness metadata
            entry = NarrationEntry(
                text=prefixed_narration,
                aware_agents=aware_agents if isinstance(aware_agents, list) else []
            )
            self.recent_narrations.append(entry)

            # Keep only last 20 narrations (FIFO rolling window) - enough for 1-2 full rounds
            if len(self.recent_narrations) > 20:
                self.recent_narrations.pop(0)

            logger.debug(f"Player {self.character_state.name}: Stored resolution from {acting_character} (aware: {aware_agents})")

        # Only update OWN character state for resolutions targeting this agent
        if resolved_agent_id != self.agent_id:
            return  # Don't process state updates for other agents

        print(f"\n[{self.character_state.name}] Received resolution")

        # Extract story beat from own significant actions
        self._extract_story_beat(original_action, outcome, narration)

        # NOTE: Offering consumption now happens BEFORE DM narration in dm.py (mechanics-first architecture)
        # No need to consume here anymore - mechanics layer handles it pre-narration

        # Update void state from mechanics engine
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            void_state = mechanics.get_void_state(self.agent_id)
            self.character_state.void_score = void_state.score

            # Sync soulcredit from mechanics engine (parallel to void sync)
            # Fix for bug: soulcredit changes were applied to mechanics.soulcredit_states
            # but not synced to character_state.soulcredit before JSONL logging
            sc_state = mechanics.get_soulcredit_state(self.agent_id)
            self.character_state.soulcredit = sc_state.score

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

        # Note: Purchases are now handled via DM structured output (ActionResolution.effects.purchase)
        # Currency transfers still handled here temporarily (will migrate to DM structured output)
        intent = original_action.get('intent', '').lower()
        if ('give' in intent or 'transfer' in intent or 'pool' in intent) and outcome.get('success', False):
            self._process_transfer(intent, outcome)

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
        if self.character_state.energy_purse.spend_currency(currency_type, amount):
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
            print(f"[{self.character_state.name}] Remaining: {self.character_state.energy_purse.spark} Spark, {self.character_state.energy_purse.drip} Drip, {self.character_state.energy_purse.breath} Breath")
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
            self.character_state.energy_purse.add_currency(
                transfer['currency_type'],
                transfer['amount']
            )

            logger.info(f"{self.character_state.name} received {transfer['amount']} {transfer['currency_type']} from {transfer['from_name']}")
            print(f"[{self.character_state.name}] 💰 Received {transfer['amount']} {transfer['currency_type']} from {transfer['from_name']}")
            print(f"[{self.character_state.name}] New total: {self.character_state.energy_purse.spark} Spark, {self.character_state.energy_purse.drip} Drip, {self.character_state.energy_purse.breath} Breath")

            # Remove from pending
            self.shared_state.pending_transfers.remove(transfer)

    def _extract_story_beat(self, original_action: Dict[str, Any], outcome: Dict[str, Any], narration: str):
        """
        Extract a story beat from a significant action for narrative memory.

        Only captures notable events (combat victories, discoveries, social successes).
        Keeps story_beats list to max 10 entries (FIFO).
        """
        # Skip if no narration or trivial action
        if not narration or len(narration) < 20:
            return

        action_type = original_action.get('action_type', '').upper()
        success = outcome.get('success', False)
        intent = original_action.get('intent', '')

        # Determine if this action is significant enough to be a story beat
        beat = None

        # Combat victories are always notable
        if action_type == 'COMBAT' and success:
            # Try to extract target from action
            target = original_action.get('target_name', original_action.get('target', ''))
            if target:
                beat = f"Defeated {target} in combat"
            else:
                beat = f"Won combat engagement"

        # Social successes (negotiation, intimidation, persuasion)
        elif action_type == 'SOCIAL' and success:
            # Shorten the intent to a beat
            if 'negotiate' in intent.lower() or 'persuade' in intent.lower():
                beat = f"Negotiated successfully: {intent[:50]}..."
            elif 'intimidate' in intent.lower():
                beat = f"Intimidated target: {intent[:50]}..."
            else:
                beat = f"Social success: {intent[:50]}..."

        # Investigation discoveries
        elif action_type == 'INVESTIGATE' and success:
            beat = f"Discovered: {intent[:60]}..."

        # Ritual/magic successes
        elif action_type == 'RITUAL' and success:
            beat = f"Completed ritual: {intent[:50]}..."

        # Technical/hacking successes
        elif action_type == 'TECHNICAL' and success:
            beat = f"Tech success: {intent[:50]}..."

        # Critical failures (dramatic moments)
        tier = outcome.get('tier', outcome.get('outcome_tier', ''))
        if tier in ['CRITICAL_FAILURE', 'CATASTROPHIC'] and not beat:
            beat = f"Critical failure: {intent[:50]}..."

        # Add the beat if significant
        if beat:
            # Get current round from shared_state
            current_round = 0
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics:
                    current_round = mechanics.current_round or 0

            # Keep only last 10 story beats (FIFO)
            if len(self.narrative_memory.story_beats) >= 10:
                self.narrative_memory.story_beats.pop(0)
            self.narrative_memory.story_beats.append((current_round, beat))
            logger.debug(f"Player {self.character_state.name}: Added story beat (R{current_round}): {beat}")

    async def _handle_dm_narration(self, message: Message):
        """Handle general DM narration."""
        # Don't echo DM narration - users can see it from DM's output directly
        # This prevents duplicate display of synthesis and other DM messages

        # Store round synthesis for narrative context
        narration = message.payload.get('narration', '')
        is_round_synthesis = message.payload.get('is_round_synthesis', False)
        if is_round_synthesis and narration:
            self.last_round_synthesis = narration
            logger.debug(f"Player {self.character_state.name}: Stored round synthesis ({len(narration)} chars)")

        # Still prompt human-controlled characters for response
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
            bond_names = [f"{bond.character_b} ({bond.bond_type.value}, {bond.status.value})" for bond in self.character_state.bonds]
            print(f"Bonds: {', '.join(bond_names)}")

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

    def _get_required_player_sections(self) -> List[str]:
        """
        Determine which player prompt sections to load based on character skills.

        Returns:
            List of section names to load
        """
        # Always load core sections (in order from player.yaml section_order)
        sections = [
            'character_introduction',
            'character_sheet',
            'inventory_resources',
            'personality_traits',
            'goals',
            'lookup_rules',
            'stat_awareness_guidance',
            'action_declaration_unified',
            # Conditional sections added below based on character/context
            'coordination_dialogue',
            'vendor_interaction',
            'currency_transfers',
            'action_guidelines',
            'bond_mechanics',
            'important_rules'
        ]

        # Conditional: Load ritual requirements only if character has Astral Arts skill
        if self.character_state.skills.get("Astral Arts", 0) > 0:
            # Insert after action_declaration_unified
            insert_index = sections.index('action_declaration_unified') + 1
            sections.insert(insert_index, 'ritual_requirements_conditional')
            logger.debug(f"Player {self.character_state.name}: Loading ritual_requirements (Astral Arts {self.character_state.skills['Astral Arts']})")
        else:
            logger.debug(f"Player {self.character_state.name}: Skipping ritual_requirements (no Astral Arts skill)")

        # Always load faction reference, pydantic philosophy, and targeting guidance from conditional_sections
        # (These are in conditional_sections but always loaded - just organized that way in YAML)
        sections.append('faction_reference')
        sections.append('pydantic_philosophy')
        sections.append('targeting_guidance')

        return sections

    def _build_player_system_prompt_new(self, recent_intents: List[str], other_players: List[str]) -> str:
        """Build player system prompt using new prompt_loader system."""
        from .enhanced_prompts import _format_tiered_skills

        # Format attributes
        attributes_text = "\n".join([
            f"- {attr}: {val}"
            for attr, val in self.character_state.attributes.items()
        ])

        # Format skills using tiered display
        skills_text = _format_tiered_skills(self.character_state.skills)

        # Format currency display
        energy_inv = self.character_state.energy_purse
        if energy_inv:
            currency_display = f"""- Breath: {energy_inv.breath} (smallest denomination)
- Drip: {energy_inv.drip}
- Grain: {energy_inv.grain}
- Spark: {energy_inv.spark} (largest standard unit)"""

            raw_count = sum(1 for s in energy_inv.seeds if s.seed_type == SeedType.RAW)
            attuned_count = sum(1 for s in energy_inv.seeds if s.seed_type == SeedType.ATTUNED)
            hollow_count = sum(1 for s in energy_inv.seeds if s.seed_type == SeedType.HOLLOW)

            # Warn if no Raw Seeds available (prevents invalid attunement attempts)
            if raw_count == 0:
                seeds_display = f"""⚠️ **NO RAW SEEDS AVAILABLE** - You CANNOT perform attunement!
- Raw Seeds: 0 (REQUIRED for attunement - acquire more via search/purchase)
- Attuned Seeds: {attuned_count} (stable, ritual fuel)
- Hollow Seeds: {hollow_count} (illicit, black market commodity)"""
            else:
                seeds_display = f"""- Raw Seeds: {raw_count} (degrade over time, need attunement)
- Attuned Seeds: {attuned_count} (stable, ritual fuel)
- Hollow Seeds: {hollow_count} (illicit, black market commodity)"""
        else:
            currency_display = "- No currency data available"
            seeds_display = "- No seed data available"

        # Build void warning if needed
        void_warning = ""
        if self.character_state.void_score >= 5:
            void_warning = f"⚠️ **WARNING**: Your Void score is {self.character_state.void_score}/10 - you are significantly corrupted.\nFurther void exposure may have severe consequences."

        # Build recent intents warning if needed
        recent_intents_section = ""
        if recent_intents:
            intents_list = "\n".join([f"- {intent}" for intent in recent_intents])
            recent_intents_section = f"**Your Recent Actions (DO NOT REPEAT):**\n{intents_list}\n\nYou MUST try a different approach, tool, location, or angle. Repeating the same action is not allowed."

        # Build stat awareness lists FIRST (needed for failure loop warning)
        # Top 3 skills
        skills_sorted = sorted(
            self.character_state.skills.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        top_skills_list = ", ".join([f"{skill} ({val})" for skill, val in skills_sorted])

        # Low attributes (< 4)
        low_attrs = [
            f"{attr} ({val})"
            for attr, val in self.character_state.attributes.items()
            if val < 4
        ]
        low_attributes_list = ", ".join(low_attrs) if low_attrs else "None (all attributes 4+)"

        # Check for failure loop and build warning
        failure_loop_warning = ""
        high_void_warning = ""
        if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
            session = self.shared_state.session
            if self.character_state.name in session._character_action_history:
                history = session._character_action_history[self.character_state.name]

                # Check last 3 actions for failure pattern
                if len(history) >= 2:
                    last_actions = history[-3:]  # Last 3 actions

                    # Count consecutive failures of same action type
                    failure_types = {}
                    for action_type, success_tier, void_change, _ in last_actions:
                        # Count as failure if CRITICAL_FAILURE or FAILURE, or if void increased
                        is_failure = success_tier in ['CRITICAL_FAILURE', 'FAILURE'] or void_change > 0
                        if is_failure:
                            failure_types[action_type] = failure_types.get(action_type, 0) + 1

                    # If same action type failed 2+ times
                    for action_type, count in failure_types.items():
                        if count >= 2:
                            # Build failure list
                            failure_list_items = []
                            for at, st, vc, rnd in last_actions:
                                if at == action_type:
                                    void_text = f", Void +{vc}" if vc > 0 else ""
                                    failure_list_items.append(f"- Round {rnd}: {at} ({st}{void_text})")

                            failures_text = "\n".join(failure_list_items)

                            failure_loop_warning = f"""🚨 **FAILURE LOOP DETECTED** 🚨

You have failed {count} {action_type} actions in a row!
**Your recent failures:**
{failures_text}

**STOP and reassess:**
1. You may lack the right skills for this approach
2. Your stats may be too low for these DCs
3. The situation may require a completely different strategy

**REQUIRED: Choose a DIFFERENT action type this turn!**
- Use your strengths: {top_skills_list}
- OR coordinate with allies who have better skills for this task
- OR pivot to a support/reconnaissance role

Continuing the same failing approach will only increase your void corruption and waste rounds!"""
                            break  # Only show one warning

            # High void warning (void >= 8)
            if self.character_state.void_score >= 8:
                high_void_warning = f"""⚠️ **VOID CORRUPTION CRITICAL** ⚠️

Your void score is {self.character_state.void_score}/10. You are dangerously close to possession!

**AVOID THESE ACTIONS:**
- Void analysis or manipulation (risk of catastrophic failure → more void!)
- Ritual magic without offerings (adds +1 void!)
- Any action using "unskilled" penalties near void phenomena

**SAFER ALTERNATIVES:**
- Coordinate with allies (DC 10-15, low risk)
- Use offerings for magic (REDUCES void by -1!)
- Support actions (buff allies, create advantages)
- Defensive/protective actions
- Consider emergency void cleansing ritual if you have offerings!"""

        # Build dialogue goal text based on character goals
        dialogue_goal_text = ""
        if other_players:
            party_members_str = ", ".join(other_players)
            goals = self.character_state.goals

            if any('bond' in goal.lower() or 'harmony' in goal.lower() or 'community' in goal.lower() for goal in goals):
                dialogue_goal_text = f"""**🎯 HOW TO ACHIEVE YOUR GOALS:**
Your goals involve harmony and community - this means TALKING TO YOUR COMPANIONS!
- Coordinate with {party_members_str} about the situation
- Share what you've learned to build trust and cooperation
- Ask them about their findings to work together more effectively
- Teamwork advances your goals more than working alone
- Note: Casual coordination ≠ forming a formal Bond (capital B)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!"""
            elif any('tempest' in goal.lower() or 'corporate' in goal.lower() or 'advance' in goal.lower() for goal in goals):
                dialogue_goal_text = f"""**🎯 HOW TO ACHIEVE YOUR GOALS:**
Advancing corporate interests requires COORDINATION and INFORMATION.
- Share tactical intelligence with {party_members_str}
- Coordinate strategy to maximize mission efficiency
- Learn what they've discovered to complete objectives faster
- Two operatives working together > working separately
- Note: Tactical coordination ≠ forming a formal Bond (you can avoid Bonds while still coordinating)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!"""
            else:
                dialogue_goal_text = f"""**🎯 COORDINATION STRATEGY:**
- Talk to {party_members_str} about what you've learned
- Coordinate your next moves to avoid duplication of effort
- Share discoveries to piece together the full picture
- Working together ≠ formal Bonds (you can coordinate without commitment)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!"""

        # Build risk/void curiosity guidance
        risk_tolerance = self.personality.get('riskTolerance', 5)
        void_curiosity = self.personality.get('voidCuriosity', 5)

        risk_guidance = "- Take bold, proactive actions\n- Not afraid of difficult checks" if risk_tolerance > 6 else "- Be cautious and methodical\n- Prefer safer, more certain approaches"
        void_curiosity_guidance = "- Actively investigate void phenomena\n- Use void-manipulation tech if available" if void_curiosity > 6 else "- Avoid void-related risks\n- Use traditional, non-void methods"

        # Build bond guidance
        bond_preference = self.personality.get('bondPreference', 'neutral')
        if bond_preference == 'seeks':
            bond_guidance = "- Seek to form and protect formal Bonds (spiritual/economic commitments)"
        elif bond_preference == 'avoids':
            bond_guidance = "- Avoid formal Bond commitments (but casual teamwork/coordination is fine)"
        else:
            bond_guidance = "- Pragmatic about formal Bonds"

        # Build goals text
        goals_text = "\n".join([f"- {goal}" for goal in self.character_state.goals])

        # Calculate health status (matching enemy agent pattern)
        health_pct = int((self.health / self.max_health) * 100) if self.max_health > 0 else 100

        if health_pct >= 75:
            health_status = "Healthy"
        elif health_pct >= 50:
            health_status = "Wounded"
        elif health_pct >= 25:
            health_status = "Bloodied"
        else:
            health_status = "CRITICAL"

        # Wound status annotation (matching enemy agent pattern)
        if self.wounds >= 4:
            wound_status = "(HEAVY WOUNDS -15)"
        elif self.wounds >= 2:
            wound_status = "(WOUNDED -5)"
        else:
            wound_status = ""

        # Build variables dict for prompt template
        variables = {
            "character_name": self.character_state.name,
            "pronouns": self.character_state.pronouns,
            "attributes_text": attributes_text,
            "skills_text": skills_text,
            "health": str(self.health),
            "max_health": str(self.max_health),
            "health_pct": str(health_pct),
            "health_status": health_status,
            "wounds": str(self.wounds),
            "wound_status": wound_status,
            "stuns": str(self.stuns),
            "void_score": str(self.character_state.void_score),
            "soulcredit": str(self.character_state.soulcredit),
            "void_warning": void_warning,
            "currency_display": currency_display,
            "seeds_display": seeds_display,
            "risk_tolerance": str(risk_tolerance),
            "void_curiosity": str(void_curiosity),
            "bond_preference": bond_preference,
            "ritual_conservatism": str(self.personality.get('ritualConservatism', 5)),
            "goals_text": goals_text,
            "dialogue_goal_text": dialogue_goal_text,
            "recent_intents_section": recent_intents_section,
            "risk_guidance": risk_guidance,
            "void_curiosity_guidance": void_curiosity_guidance,
            "bond_guidance": bond_guidance,
            "top_skills_list": top_skills_list,
            "low_attributes_list": low_attributes_list,
            "failure_loop_warning": failure_loop_warning,
            "high_void_warning": high_void_warning
        }

        # Determine which sections to load (conditional loading based on skills)
        required_sections = self._get_required_player_sections()

        # Load prompt from YAML with conditional sections and variable substitution
        loaded_prompt = compose_sections(
            agent_type="player",
            section_names=required_sections,
            provider="claude",
            language="en",  # TODO: Make this configurable
            variables=variables
        )

        # Inject dynamic warnings after character sheet
        content = loaded_prompt.content

        # Find the character sheet section and inject warnings after it
        if failure_loop_warning or high_void_warning:
            # Insert after "# Character Sheet" section
            char_sheet_end = content.find("# Inventory & Resources")
            if char_sheet_end != -1:
                warnings = []
                if failure_loop_warning:
                    warnings.append(failure_loop_warning)
                if high_void_warning:
                    warnings.append(high_void_warning)

                warning_text = "\n\n" + "\n\n".join(warnings) + "\n"
                content = content[:char_sheet_end] + warning_text + "\n" + content[char_sheet_end:]

        # Store prompt metadata for logging
        self._last_prompt_metadata = loaded_prompt.metadata

        return content

    async def _generate_action_intent(self) -> Optional['ActionIntent']:
        """
        Phase 1: Generate lightweight action type selection.
        Returns ActionIntent with chosen action type, or None on failure.
        """
        from .schemas.player_action import ActionIntent
        from .enhanced_prompts import _format_tiered_skills

        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug(f"Player {self.character_state.name}: No llm_provider for Phase 1 (action intent)")
            return None

        try:
            # Build comprehensive context for Phase 1 (needs most info from legacy prompt)
            from .enhanced_prompts import _format_tiered_skills

            # Format attributes
            attributes_text = "\n".join([
                f"- {attr}: {val}"
                for attr, val in self.character_state.attributes.items()
            ])

            # Format skills using tiered display
            skills_text = _format_tiered_skills(self.character_state.skills)

            # Top 3 skills (for skill awareness)
            skills_sorted = sorted(
                self.character_state.skills.items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            top_skills_list = ", ".join([f"{skill} ({val})" for skill, val in skills_sorted])

            # Calculate health status
            health_pct = int((self.health / self.max_health) * 100) if self.max_health > 0 else 100
            if health_pct >= 75:
                health_status = "Healthy"
            elif health_pct >= 50:
                health_status = "Wounded"
            elif health_pct >= 25:
                health_status = "Bloodied"
            else:
                health_status = "CRITICAL"

            # Format inventory (seeds + currency) for Phase 1
            energy_purse = getattr(self.character_state, 'energy_purse', None)
            if energy_purse:
                # Count seeds by type
                raw_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.RAW']
                hollow_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.HOLLOW']
                attuned_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.ATTUNED']

                # Energy currencies + hollow (hollow are energy currency)
                energy_parts = [
                    f"Breath: {energy_purse.breath}",
                    f"Grain: {energy_purse.grain}",
                    f"Drip: {energy_purse.drip}",
                    f"Spark: {energy_purse.spark}"
                ]
                if hollow_seeds:
                    energy_parts.append(f"Hollow: {len(hollow_seeds)}")
                currency_display = ", ".join(energy_parts)

                # Physical seeds (raw and attuned only)
                seed_parts = []
                if raw_seeds:
                    seed_parts.append(f"Raw: {len(raw_seeds)}")
                if attuned_seeds:
                    seed_parts.append(f"Attuned: {len(attuned_seeds)}")

                seeds_display = ", ".join(seed_parts) if seed_parts else "No physical seeds"
            else:
                # No energy purse - show equipment instead
                equipment_list = []
                if hasattr(self.character_state, 'weapons') and self.character_state.weapons:
                    equipment_list.append(f"Weapons: {', '.join(self.character_state.weapons)}")
                if hasattr(self.character_state, 'armor') and self.character_state.armor:
                    equipment_list.append(f"Armor: {self.character_state.armor}")

                currency_display = " | ".join(equipment_list) if equipment_list else "Standard loadout"
                seeds_display = "(No seeds)"

            # Build goals text
            goals_text = "\n".join([f"- {goal}" for goal in self.character_state.goals]) if self.character_state.goals else "- No specific goals defined"

            # Build void warning if needed
            void_warning = ""
            if self.character_state.void_score >= 5:
                void_warning = f"⚠️ Void: {self.character_state.void_score}/10 (significantly corrupted)"

            # Wound status annotation
            if self.wounds >= 4:
                wound_status = "(HEAVY WOUNDS -15)"
            elif self.wounds >= 2:
                wound_status = "(WOUNDED -5)"
            else:
                wound_status = ""

            # Build declared actions context (what allies/enemies have declared THIS round)
            declared_actions_text = ""
            if self.declared_actions_this_round:
                # Show ALL declarations from this round (don't filter by initiative)
                # Sort by initiative (highest first, matching declaration order)
                sorted_declarations = sorted(
                    self.declared_actions_this_round.items(),
                    key=lambda x: x[1][-1],  # initiative is always last element
                    reverse=True  # Highest initiative (fastest actors) first
                )

                if sorted_declarations:
                    declared_actions_text = f"\n**{DECLARED_ACTIONS_HEADER} (Initiative Order):**\n"
                    for char_name, action_data in sorted_declarations:
                        # Current format: (description, action_intent, target, weapon, reasoning, initiative)
                        if len(action_data) == 6:
                            description, action_intent, target, weapon, reasoning_text, init_score = action_data

                            # Format action with targeting info if available
                            if description:
                                action_text = description
                            else:
                                action_text = action_intent
                                if target:
                                    action_text += f" targeting {target}"
                                if weapon:
                                    action_text += f" with {weapon}"

                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {action_text}\n"
                        elif len(action_data) == 3:
                            # Legacy format (description, action_intent, initiative)
                            description, action_intent, init_score = action_data
                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {description if description else action_intent}\n"
                        else:
                            # Very old format (action_intent, initiative)
                            action_intent, init_score = action_data
                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {action_intent}\n"

            # Build recent action outcomes (detailed narrations from recent actions)
            recent_outcomes_text = ""
            if self.recent_narrations:
                recent_outcomes_text = "\n**Recent Action Outcomes:**\n"
                for i, narration in enumerate(self.recent_narrations[-5:], 1):  # Last 5 narrations
                    recent_outcomes_text += f"{i}. {narration}\n"

            # Low attributes (< 4)
            low_attrs = [
                f"{attr} ({val})"
                for attr, val in self.character_state.attributes.items()
                if val < 4
            ]
            low_attributes_list = ", ".join(low_attrs) if low_attrs else "None (all attributes 4+)"

            # Build personality guidance
            risk_tolerance = self.personality.get('riskTolerance', 5)
            void_curiosity = self.personality.get('voidCuriosity', 5)
            bond_preference = self.personality.get('bondPreference', 'neutral')
            ritual_conservatism = self.personality.get('ritualConservatism', 5)

            risk_guidance = "Take bold, proactive actions" if risk_tolerance > 6 else "Be cautious and methodical"
            void_curiosity_guidance = "Actively investigate void phenomena" if void_curiosity > 6 else "Avoid void-related risks"

            if bond_preference == 'seeks':
                bond_guidance = "Seek to form and protect formal Bonds"
            elif bond_preference == 'avoids':
                bond_guidance = "Avoid formal Bond commitments (but teamwork is fine)"
            else:
                bond_guidance = "Pragmatic about formal Bonds"

            # Get other players for dialogue prompts
            other_players = []
            if self.shared_state and self.shared_state.player_agents:
                other_players = [
                    agent.character_state.name
                    for agent in self.shared_state.player_agents
                    if agent.agent_id != self.agent_id
                ]

            # Build dialogue goal text
            dialogue_goal_text = ""
            if other_players:
                party_members_str = ", ".join(other_players)
                dialogue_goal_text = f"\n💬 Coordinate with {party_members_str} (dialogue is a FREE ACTION!)"

            # Check for failure loop warning
            failure_loop_warning = ""
            high_void_warning = ""
            if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                session = self.shared_state.session
                if self.character_state.name in session._character_action_history:
                    history = session._character_action_history[self.character_state.name]

                    if len(history) >= 2:
                        last_actions = history[-3:]
                        failure_types = {}
                        for action_type, success_tier, void_change, _ in last_actions:
                            is_failure = success_tier in ['CRITICAL_FAILURE', 'FAILURE'] or void_change > 0
                            if is_failure:
                                failure_types[action_type] = failure_types.get(action_type, 0) + 1

                        for action_type, count in failure_types.items():
                            if count >= 2:
                                failure_list_items = []
                                for at, st, vc, rnd in last_actions:
                                    if at == action_type:
                                        void_text = f", Void +{vc}" if vc > 0 else ""
                                        failure_list_items.append(f"Round {rnd}: {at} ({st}{void_text})")
                                failures_text = ", ".join(failure_list_items)
                                failure_loop_warning = f"\n🚨 FAILURE LOOP: {count} {action_type} failures ({failures_text}) - CHOOSE DIFFERENT ACTION TYPE!\n"
                                break

                if self.character_state.void_score >= 8:
                    high_void_warning = f"\n⚠️ VOID CRITICAL ({self.character_state.void_score}/10) - Avoid risky actions! Use offerings to reduce void!\n"

            # Build variables for Phase 1 prompt
            variables = {
                # Character identity
                "character_name": self.character_state.name,
                "pronouns": self.character_state.pronouns,
                # Stats
                "attributes_text": attributes_text,
                "skills_text": skills_text,
                "top_skills_list": top_skills_list,
                "low_attributes_list": low_attributes_list,
                # Health/status
                "current_round": str(getattr(self, 'current_round', 0)),
                "health": str(self.health),
                "max_health": str(self.max_health),
                "health_status": health_status,
                "wounds": str(self.wounds),
                "wound_status": wound_status,
                "stuns": str(self.stuns),
                "void_score": str(self.character_state.void_score),
                "void_warning": void_warning,
                "soulcredit": str(self.character_state.soulcredit),
                "position": str(self.position) if hasattr(self, 'position') else "Unknown",
                # Scenario context (current location and situation)
                "location": self.current_scenario.get('location', 'Unknown') if self.current_scenario else 'Unknown',
                "situation": self.current_scenario.get('situation', 'No current situation') if self.current_scenario else 'No current situation',
                "theme": self.current_scenario.get('theme', 'Unknown') if self.current_scenario else 'Unknown',
                # Narrative memory (persistent journey context) - format with round numbers
                "journey_locations": " → ".join(f"(R{r}) {loc}" for r, loc in self.narrative_memory.locations_visited) if self.narrative_memory.locations_visited else "Just started",
                "journey_beats": "\n".join(f"- (R{r}) {beat}" for r, beat in self.narrative_memory.story_beats[-5:]) if self.narrative_memory.story_beats else "No significant events yet",
                "journey_summary": self.narrative_memory.story_summary if self.narrative_memory.story_summary else "Journey just beginning...",
                # Goals & personality
                "goals_text": goals_text,
                "dialogue_goal_text": dialogue_goal_text,
                "risk_tolerance": str(risk_tolerance),
                "void_curiosity": str(void_curiosity),
                "bond_preference": bond_preference,
                "ritual_conservatism": str(ritual_conservatism),
                "risk_guidance": risk_guidance,
                "void_curiosity_guidance": void_curiosity_guidance,
                "bond_guidance": bond_guidance,
                # Customizable personality/direction guidance (with labels when present)
                "personality_notes": f"- **Personality Notes:** {self.personality_notes}" if self.personality_notes else "",
                "direction": f"- **Direction:** {self.direction}" if self.direction else "",
                # Warnings
                "failure_loop_warning": failure_loop_warning,
                "high_void_warning": high_void_warning,
                # Include recent events from narrative context
                "recent_events": self.last_round_synthesis if self.last_round_synthesis else "Round starting...",
                # NEW: What allies/enemies have declared THIS round (tactical coordination)
                "declared_actions_this_round": declared_actions_text,
                # NEW: Recent action outcomes (detailed narrations)
                "recent_action_outcomes": recent_outcomes_text,
                # Unified entity awareness (allies + enemies + NPCs)
                "entities_present": self._format_entities_present(),
                # Legacy fields (for backward compat with old prompts)
                "ally_status": self._format_ally_status(),
                "threat_status": self._format_threat_status(),
                # Inventory for attunement/purchase decisions
                "currency_display": currency_display,
                "seeds_display": seeds_display,
                # Environment features (altars, vendors, situational factors)
                "altar_availability": self._format_altar_availability(),
                "vendor_status": self._format_vendor_status()
            }

            # Load Phase 1 prompt (player_intent.yaml) from player/ subdirectory
            from .prompt_loader import load_modular_prompt
            loaded_prompt = load_modular_prompt(
                agent_type="player",
                module_names=["player_intent"],  # Loads player/player_intent.yaml
                provider="claude",
                language="en",
                variables=variables
            )

            logger.debug(f"Player {self.character_state.name}: Phase 1 (action intent) - generating...")

            # Capture prompts for logging
            phase1_system_prompt = f"You are {self.character_state.name}, choosing your next action type."
            phase1_user_prompt = loaded_prompt.content

            # Generate ActionIntent
            action_intent: ActionIntent = await self.llm_provider.generate_structured(
                prompt=phase1_user_prompt,
                result_type=ActionIntent,
                system_prompt=phase1_system_prompt,
                max_tokens=self.llm_config.get('max_tokens', 4000),  # Increased from 2000 - prevent OpenAI finish_reason:length errors
                temperature=self.llm_config.get('temperature', 1.0),
                llm_logger=self.llm_logger,
                current_round=getattr(self, 'current_round', None)
            )

            # Log Phase 1 prompts to agent prompt logger
            if self.agent_prompt_logger:
                try:
                    full_prompt = f"System: {phase1_system_prompt}\n\nUser: {phase1_user_prompt}"
                    response_text = action_intent.model_dump_json(indent=2)

                    self.agent_prompt_logger.log_llm_call(
                        agent_id=self.agent_id,
                        round_num=getattr(self, 'current_round', None),
                        call_sequence=getattr(self.llm_logger, 'call_count', 0) if self.llm_logger else 0,
                        prompt=full_prompt,
                        response=response_text,
                        model=self.llm_config.get('model', 'claude-sonnet-4-5'),
                        temperature=self.llm_config.get('temperature', 1.0),
                        metadata={'phase': 'Phase 1: Action Intent', 'note': 'Pydantic AI structured output (ActionIntent schema)'}
                    )
                except Exception as e:
                    logger.error(f"Player {self.agent_id}: Failed to log Phase 1 to agent prompt logger: {e}")

            logger.debug(f"✓ Player {self.character_state.name} Phase 1: {action_intent.action_type} - {action_intent.intent}")
            return action_intent

        except Exception as e:
            logger.error(f"Player {self.character_state.name}: Phase 1 (action intent) failed: {e}")
            return None

    async def _generate_action_details(self, intent: 'ActionIntent') -> Optional[Any]:
        """
        Phase 2: Generate action-specific details based on Phase 1 action type.
        Uses discriminated union routing to call appropriate schema.
        Returns action-specific schema instance (e.g., AttuneAction, CombatAction), or None on failure.
        """
        from .schemas.player_action import ACTION_TYPE_SCHEMA_MAP
        from .enhanced_prompts import _format_tiered_skills

        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug(f"Player {self.character_state.name}: No llm_provider for Phase 2 (action details)")
            return None

        # Get the correct schema for this action type
        schema_class = ACTION_TYPE_SCHEMA_MAP.get(intent.action_type)
        if not schema_class:
            logger.error(f"Player {self.character_state.name}: No schema found for action type {intent.action_type}")
            return None

        try:
            # Map action type to prompt module name (e.g., ATTUNE → player_action_attune)
            action_type_lower = intent.action_type.value.lower()
            prompt_module = f"player_action_{action_type_lower}"

            # Build comprehensive context for Phase 2 (action-specific guidance)

            # Build declared actions context (what allies/enemies have declared THIS round)
            declared_actions_text = ""
            if self.declared_actions_this_round:
                # Show ALL declarations from this round (don't filter by initiative)
                # Sort by initiative (highest first, matching declaration order)
                sorted_declarations = sorted(
                    self.declared_actions_this_round.items(),
                    key=lambda x: x[1][-1],  # initiative is always last element
                    reverse=True  # Highest initiative (fastest actors) first
                )

                if sorted_declarations:
                    declared_actions_text = f"\n**{DECLARED_ACTIONS_HEADER} (Initiative Order):**\n"
                    for char_name, action_data in sorted_declarations:
                        # Current format: (description, action_intent, target, weapon, reasoning, initiative)
                        if len(action_data) == 6:
                            description, action_intent, target, weapon, reasoning_text, init_score = action_data

                            # Format action with targeting info if available
                            if description:
                                action_text = description
                            else:
                                action_text = action_intent
                                if target:
                                    action_text += f" targeting {target}"
                                if weapon:
                                    action_text += f" with {weapon}"

                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {action_text}\n"
                        elif len(action_data) == 3:
                            # Legacy format (description, action_intent, initiative)
                            description, action_intent, init_score = action_data
                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {description if description else action_intent}\n"
                        else:
                            # Very old format (action_intent, initiative)
                            action_intent, init_score = action_data
                            declared_actions_text += f"- **{char_name}** [Init {init_score}]: {action_intent}\n"

            # Build recent action outcomes (detailed narrations from recent actions)
            recent_outcomes_text = ""
            if self.recent_narrations:
                recent_outcomes_text = "\n**Recent Action Outcomes:**\n"
                for i, narration in enumerate(self.recent_narrations[-5:], 1):  # Last 5 narrations
                    recent_outcomes_text += f"{i}. {narration}\n"

            # Format attributes
            attributes_text = "\n".join([
                f"- {attr}: {val}"
                for attr, val in self.character_state.attributes.items()
            ])

            # Format skills using tiered display
            skills_text = _format_tiered_skills(self.character_state.skills)

            # Format currency display (compact format, same as Phase 1)
            energy_purse = getattr(self.character_state, 'energy_purse', None)
            if energy_purse:
                # Count seeds by type
                raw_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.RAW']
                hollow_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.HOLLOW']
                attuned_seeds = [s for s in energy_purse.seeds if hasattr(s, 'seed_type') and str(s.seed_type) == 'SeedType.ATTUNED']

                # Energy currencies + hollow (hollow are energy currency)
                energy_parts = [
                    f"Breath: {energy_purse.breath}",
                    f"Grain: {energy_purse.grain}",
                    f"Drip: {energy_purse.drip}",
                    f"Spark: {energy_purse.spark}"
                ]
                if hollow_seeds:
                    energy_parts.append(f"Hollow: {len(hollow_seeds)}")
                currency_display = ", ".join(energy_parts)

                # Physical seeds (raw and attuned only)
                seed_parts = []
                if raw_seeds:
                    seed_parts.append(f"Raw: {len(raw_seeds)}")
                if attuned_seeds:
                    seed_parts.append(f"Attuned: {len(attuned_seeds)}")

                seeds_display = ", ".join(seed_parts) if seed_parts else "No physical seeds"
            else:
                # No energy purse - show equipment instead (compact format)
                equipment_list = []
                if hasattr(self.character_state, 'weapons') and self.character_state.weapons:
                    equipment_list.append(f"Weapons: {', '.join(self.character_state.weapons)}")
                if hasattr(self.character_state, 'armor') and self.character_state.armor:
                    equipment_list.append(f"Armor: {self.character_state.armor}")

                currency_display = " | ".join(equipment_list) if equipment_list else "Standard loadout"
                seeds_display = "(No seeds)"

            # Calculate health status
            health_pct = int((self.health / self.max_health) * 100) if self.max_health > 0 else 100
            if health_pct >= 75:
                health_status = "Healthy"
            elif health_pct >= 50:
                health_status = "Wounded"
            elif health_pct >= 25:
                health_status = "Bloodied"
            else:
                health_status = "CRITICAL"

            # Build variables for Phase 2 prompt (include Phase 1 context)
            variables = {
                # Phase 1 context (so Phase 2 knows what the user already decided)
                "phase1_intent": intent.intent,
                "phase1_reasoning": intent.reasoning or "No reasoning provided",
                # Character context
                "character_name": self.character_state.name,
                "attributes_text": attributes_text,
                "skills_text": skills_text,
                "currency_display": currency_display,
                "seeds_display": seeds_display,
                "void_score": str(self.character_state.void_score),
                "health": str(self.health),
                "max_health": str(self.max_health),
                "health_status": health_status,
                "position": str(self.position) if hasattr(self, 'position') else "Unknown",
                # Scenario context (current location and situation)
                "location": self.current_scenario.get('location', 'Unknown') if self.current_scenario else 'Unknown',
                "situation": self.current_scenario.get('situation', 'No current situation') if self.current_scenario else 'No current situation',
                "theme": self.current_scenario.get('theme', 'Unknown') if self.current_scenario else 'Unknown',
                # Narrative memory (persistent journey context) - format with round numbers
                "journey_locations": " → ".join(f"(R{r}) {loc}" for r, loc in self.narrative_memory.locations_visited) if self.narrative_memory.locations_visited else "Just started",
                "journey_beats": "\n".join(f"- (R{r}) {beat}" for r, beat in self.narrative_memory.story_beats[-5:]) if self.narrative_memory.story_beats else "No significant events yet",
                "journey_summary": self.narrative_memory.story_summary if self.narrative_memory.story_summary else "Journey just beginning...",
                # Combat-specific context (if applicable)
                "combat_attribute": str(self.character_state.attributes.get('Agility', 0)),
                "combat_skills": str(self.character_state.skills.get('Guns', 0)),
                # Social-specific context (if applicable)
                "empathy": str(self.character_state.attributes.get('Empathy', 0)),
                "charm_skill": str(self.character_state.skills.get('Charm', 0)),
                "negotiation_skill": str(self.character_state.skills.get('Negotiation', 0)),
                # Attunement-specific context (if applicable)
                "willpower": str(self.character_state.attributes.get('Willpower', 0)),
                "attunement_skill": str(self.character_state.skills.get('Attunement', 0)),
                "attunement_total": str(self.character_state.attributes.get('Willpower', 0) + self.character_state.skills.get('Attunement', 0)),
                "unskilled_warning": "" if self.character_state.skills.get('Attunement', 0) > 0 else "⚠️ Unskilled (-5 penalty)",
                # Environment context (unified + legacy)
                "entities_present": self._format_entities_present(),
                "vendor_status": self._format_vendor_status(),
                "threat_status": self._format_threat_status(),  # Legacy
                "altar_availability": self._format_altar_availability(),
                "void_warning": "Low void risk" if self.character_state.void_score < 5 else f"⚠️ Void score: {self.character_state.void_score}/10",
                "situational_factors": self._format_situational_factors(),
                # NEW: What allies/enemies have declared THIS round (tactical coordination)
                "declared_actions_this_round": declared_actions_text,
                # NEW: Recent action outcomes (detailed narrations)
                "recent_action_outcomes": recent_outcomes_text,
                # Customizable personality/direction guidance (with labels when present)
                "personality_notes": f"**Personality Notes:** {self.personality_notes}" if self.personality_notes else "",
                "direction": f"**Direction:** {self.direction}" if self.direction else ""
            }

            # Load Phase 2 action-specific prompt from player/ subdirectory
            from .prompt_loader import load_modular_prompt
            loaded_prompt = load_modular_prompt(
                agent_type="player",
                module_names=[prompt_module],  # e.g., "player_action_attune" → player/player_action_attune.yaml
                provider="claude",
                language="en",
                variables=variables
            )

            logger.debug(f"Player {self.character_state.name}: Phase 2 ({intent.action_type}) - generating with {schema_class.__name__}...")

            # Capture prompts for logging
            phase2_system_prompt = f"You are {self.character_state.name}, declaring the detailed mechanics of your {intent.action_type} action."
            phase2_user_prompt = loaded_prompt.content

            # Generate action-specific details
            action_details = await self.llm_provider.generate_structured(
                prompt=phase2_user_prompt,
                result_type=schema_class,  # Route to correct schema (AttuneAction, CombatAction, etc.)
                system_prompt=phase2_system_prompt,
                max_tokens=self.llm_config.get('max_tokens', 3000),  # Phase 2: Complex schemas, OpenAI verbose
                temperature=self.llm_config.get('temperature', 1.0),
                llm_logger=self.llm_logger,
                current_round=getattr(self, 'current_round', None)
            )

            # Log Phase 2 prompts to agent prompt logger
            if self.agent_prompt_logger:
                try:
                    full_prompt = f"System: {phase2_system_prompt}\n\nUser: {phase2_user_prompt}"
                    response_text = action_details.model_dump_json(indent=2)

                    self.agent_prompt_logger.log_llm_call(
                        agent_id=self.agent_id,
                        round_num=getattr(self, 'current_round', None),
                        call_sequence=getattr(self.llm_logger, 'call_count', 0) if self.llm_logger else 0,
                        prompt=full_prompt,
                        response=response_text,
                        model=self.llm_config.get('model', 'claude-sonnet-4-5'),
                        temperature=self.llm_config.get('temperature', 1.0),
                        metadata={'phase': f'Phase 2: {intent.action_type} Details', 'schema': schema_class.__name__, 'note': f'Pydantic AI structured output ({schema_class.__name__} schema)'}
                    )
                except Exception as e:
                    logger.error(f"Player {self.agent_id}: Failed to log Phase 2 to agent prompt logger: {e}")

            logger.debug(f"✓ Player {self.character_state.name} Phase 2: {action_details.attribute} × {action_details.skill} (DC {action_details.difficulty_estimate})")
            return action_details

        except Exception as e:
            logger.error(f"Player {self.character_state.name}: Phase 2 (action details) failed: {e}")
            return None

    def _format_entities_present(self) -> str:
        """Format all entities in the scene (allies, enemies, NPCs) for tactical awareness."""
        entities = []

        # Get target ID mapper if available
        target_mapper = self.shared_state.target_id_mapper if self.shared_state else None

        # Add player allies (with target IDs for combat)
        if self.shared_state and self.shared_state.player_agents:
            for agent in self.shared_state.player_agents:
                if agent.agent_id == self.agent_id:
                    continue  # Skip self

                name = agent.character_state.name if hasattr(agent, 'character_state') else agent.agent_id
                health = getattr(agent, 'health', '?')
                max_health = getattr(agent, 'max_health', '?')

                # Extract pronouns if available
                pronouns = None
                if hasattr(agent, 'character_state'):
                    pronouns = getattr(agent.character_state, 'pronouns', None)

                # Get target ID from mapper
                target_id = target_mapper.get_target_id(agent.agent_id) if target_mapper else agent.agent_id

                # Format with optional pronouns
                if pronouns:
                    entities.append(f"- {name} ({pronouns}, ID: {target_id}, HP: {health}/{max_health})")
                else:
                    entities.append(f"- {name} (ID: {target_id}, HP: {health}/{max_health})")

        # Add active enemies (with target IDs for combat)
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            if enemy_combat and enemy_combat.enabled:
                # Use get_active_enemies to safely get non-defeated enemies
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                for enemy in active_enemies:
                    # Get target ID from mapper
                    target_id = target_mapper.get_target_id(enemy.agent_id) if target_mapper else enemy.agent_id

                    # Extract pronouns if available
                    pronouns = getattr(enemy, 'pronouns', None)

                    # Format with optional pronouns
                    if pronouns:
                        entities.append(
                            f"- {enemy.name} ({pronouns}, ID: {target_id}, HP: {enemy.health}/{enemy.max_health})"
                        )
                    else:
                        entities.append(
                            f"- {enemy.name} (ID: {target_id}, HP: {enemy.health}/{enemy.max_health})"
                        )

        # Add NPCs (with target IDs for combat)
        if self.shared_state and self.shared_state.npc_agents:
            for npc in self.shared_state.npc_agents:
                # NPCs have .name directly (dataclass), not .character_state.name
                name = getattr(npc, 'name', None)
                if not name and hasattr(npc, 'character_state'):
                    name = getattr(npc.character_state, 'name', None)
                if not name:
                    name = npc.agent_id  # Fallback
                health = getattr(npc, 'health', '?')
                max_health = getattr(npc, 'max_health', '?')

                # Extract pronouns if available (NPCs don't currently have pronouns field, but futureproof)
                pronouns = getattr(npc, 'pronouns', None)
                if not pronouns and hasattr(npc, 'character_state'):
                    pronouns = getattr(npc.character_state, 'pronouns', None)

                # Get target ID from mapper
                target_id = target_mapper.get_target_id(npc.agent_id) if target_mapper else npc.agent_id

                # Format with optional pronouns
                if pronouns:
                    entities.append(f"- {name} ({pronouns}, ID: {target_id}, HP: {health}/{max_health})")
                else:
                    entities.append(f"- {name} (ID: {target_id}, HP: {health}/{max_health})")

        # Add environmental objects (non-targetable, narrative grounding)
        if self.shared_state and self.shared_state.current_env_objects:
            if entities:  # Only add separator if there are already entities
                entities.append("")  # Blank line separator
                entities.append("**Environmental Features:**")
            else:
                entities.append("**Environmental Features:**")

            for env_obj in self.shared_state.current_env_objects:
                # Format state info if present
                state_str = ""
                if env_obj.state:
                    state_parts = []
                    for key, value in env_obj.state.items():
                        if isinstance(value, bool):
                            state_parts.append(f"{key}: {'Yes' if value else 'No'}")
                        else:
                            state_parts.append(f"{key}: {value}")
                    if state_parts:
                        state_str = f" ({', '.join(state_parts)})"

                entities.append(f"- {env_obj.name} [ID: {env_obj.object_id}]{state_str}")

        return "\n".join(entities) if entities else "You are alone"

    def _format_ally_status(self) -> str:
        """Legacy method - use _format_entities_present() instead."""
        return self._format_entities_present()

    def _format_threat_status(self) -> str:
        """Legacy method - use _format_entities_present() instead."""
        return self._format_entities_present()

    def _format_vendor_status(self) -> str:
        """Format vendor availability for purchase actions with IDs and inventory."""
        if not self.shared_state:
            return "No vendors present"

        vendor_lines = []

        # Check legacy vendors (backward compatibility)
        if hasattr(self.shared_state, 'current_vendors') and self.shared_state.current_vendors:
            for vendor in self.shared_state.current_vendors:
                # Format vendor header with ID
                vendor_line = f"**{vendor.name}** (ID: `{vendor.vendor_id}`, Type: {vendor.vendor_type.value})"
                vendor_lines.append(vendor_line)
                vendor_lines.append(f"  Greeting: \"{vendor.greeting}\"")

                # Format inventory with item IDs
                if vendor.inventory:
                    vendor_lines.append(f"  **Inventory ({len(vendor.inventory)} items):**")
                    for item in vendor.inventory:
                        price_parts = []
                        if item.price_spark > 0:
                            price_parts.append(f"{item.price_spark} Spark")
                        if item.price_grain > 0:
                            price_parts.append(f"{item.price_grain} Grain")
                        if item.price_drip > 0:
                            price_parts.append(f"{item.price_drip} Drip")
                        if item.price_breath > 0:
                            price_parts.append(f"{item.price_breath} Breath")
                        if item.seed_barter:
                            price_parts.append("OR 1 Raw Seed")

                        price_str = " + ".join(price_parts) if price_parts else "FREE"
                        vendor_lines.append(f"    - {item.name} (ID: `{item.item_id}`) - {item.description} - **Price:** {price_str}")
                else:
                    vendor_lines.append("  (No items in stock)")

                vendor_lines.append("")  # Blank line between vendors

        # Check NPC vendors (unified vendor system)
        if hasattr(self.shared_state, 'npc_agents') and self.shared_state.npc_agents:
            for npc in self.shared_state.npc_agents:
                # Only include NPCs with is_vendor=True
                if not getattr(npc, 'is_vendor', False):
                    continue

                # Format NPC vendor header with agent_id
                vendor_type = getattr(npc, 'vendor_type', 'human_trader')
                vendor_line = f"**{npc.name}** (ID: `{npc.agent_id}`, Type: {vendor_type})"
                vendor_lines.append(vendor_line)

                # Greeting (optional for NPC vendors)
                greeting = getattr(npc, 'vendor_greeting', None)
                if greeting:
                    vendor_lines.append(f"  Greeting: \"{greeting}\"")

                # Format inventory with item IDs
                inventory = getattr(npc, 'vendor_inventory', [])
                if inventory:
                    vendor_lines.append(f"  **Inventory ({len(inventory)} items):**")
                    for item in inventory:
                        price_parts = []
                        if item.price_spark > 0:
                            price_parts.append(f"{item.price_spark} Spark")
                        if item.price_grain > 0:
                            price_parts.append(f"{item.price_grain} Grain")
                        if item.price_drip > 0:
                            price_parts.append(f"{item.price_drip} Drip")
                        if item.price_breath > 0:
                            price_parts.append(f"{item.price_breath} Breath")
                        if item.seed_barter:
                            price_parts.append("OR 1 Raw Seed")

                        price_str = " + ".join(price_parts) if price_parts else "FREE"
                        vendor_lines.append(f"    - {item.name} (ID: `{item.item_id}`) - {item.description} - **Price:** {price_str}")
                else:
                    vendor_lines.append("  (No items in stock)")

                vendor_lines.append("")  # Blank line between vendors

        if not vendor_lines:
            return "No vendors present"

        return "\n".join(vendor_lines)

    def _format_altar_availability(self) -> str:
        """Format altar availability for attunement actions."""
        if not self.shared_state or not hasattr(self.shared_state, 'current_altars'):
            return "No altars available"

        altars = self.shared_state.current_altars
        if not altars:
            return "No altars available (DC 25 for no-equipment attunement, or use Echo-Calibrator if you have one)"

        # Format altar list with IDs, types, quality, and bonuses
        altar_lines = []
        for altar in altars:
            bonus = altar.get_ritual_bonus()
            location_text = f" at {altar.location}" if altar.location else ""
            # Bonus is DC reduction, so show as -N DC
            altar_lines.append(
                f"  - {altar.altar_id} ({altar.altar_type.value}, quality {altar.quality}, -{bonus} DC){location_text}"
            )

        return "Altars available:\n" + "\n".join(altar_lines)

    def _format_situational_factors(self) -> str:
        """Format situational modifiers for combat actions."""
        return "Standard conditions"

    async def _generate_player_action_pydantic(self, prompt: str):
        """
        Generate player action using two-phase structured output (Phase 1: Intent, Phase 2: Details).
        Returns ActionDeclaration if structured output succeeds.

        Returns None if all retries exhausted (enables graceful fallback handling by caller).

        NOTE: The 'prompt' parameter is preserved for backward compatibility but not used.
        Phase 1 and Phase 2 build their own prompts using compose_sections().
        """
        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.error(f"Player {self.character_state.name}: No llm_provider configured - cannot generate actions")
            return None

        from .action_schema import ActionDeclaration
        import asyncio

        max_retries = 3
        base_delay = 0.5  # Exponential backoff: 0.5s, 1s, 2s

        logger.debug(f"Player {self.character_state.name}: Two-phase structured output (Phase 1: Intent, Phase 2: Details)")

        action_intent = None
        action_details = None

        for attempt in range(max_retries):
            try:
                # ===== PHASE 1: Action Intent (lightweight action type selection) =====
                action_intent = await self._generate_action_intent()
                if not action_intent:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Player {self.character_state.name}: Phase 1 failed (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s")
                        await asyncio.sleep(delay)
                        continue
                    logger.error(f"Player {self.character_state.name}: Phase 1 (action intent) failed after {max_retries} attempts")
                    return None

                # ===== PHASE 2: Action Details (action-specific schema with routing) =====
                action_details = await self._generate_action_details(action_intent)
                if not action_details:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Player {self.character_state.name}: Phase 2 failed for {action_intent.action_type} (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s")
                        await asyncio.sleep(delay)
                        continue
                    logger.error(
                        f"Player {self.character_state.name}: Phase 2 (action details) failed for {action_intent.action_type} after {max_retries} attempts. "
                        f"Missing prompt file: player_action_{action_intent.action_type.value}.yaml"
                    )
                    return None

                # Success - break out of retry loop
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Player {self.character_state.name}: Two-phase generation exception (attempt {attempt + 1}/{max_retries}): {e}, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Player {self.character_state.name}: Two-phase generation failed after {max_retries} attempts: {e}")
                    return None
        else:
            # All retries exhausted without success (loop finished without break)
            return None

        # Verify we have both required objects after retry loop
        if not action_intent or not action_details:
            return None

        # Populate identity fields from player object (LLM doesn't generate these)
        action_details.character_name = self.character_state.name
        action_details.agent_id = self.agent_id

        logger.debug(f"✓ Player {self.character_state.name} two-phase action complete: {action_details.action_type}, {action_details.attribute} × {action_details.skill}")

        # Increment call count for TWO LLM calls (Phase 1 + Phase 2)
        # (Both phases already logged tokens automatically via generate_structured, and prompts logged in individual phase methods)
        if self.llm_logger:
            self.llm_logger.call_count += 2  # Two separate LLM calls

        # NOTE: Agent prompt logging now happens in _generate_action_intent() and _generate_action_details()
        # to capture the actual prompts sent to the LLM (not just summaries)

        # Convert action-specific schema (AttuneAction, CombatAction, etc.) to ActionDeclaration (legacy format)
        # ActionDeclaration expects all fields from PlayerAction, so we need to extract them
        action_declaration = ActionDeclaration(
            intent=action_details.intent,
            description=action_details.description,
            attribute=action_details.attribute,
            skill=action_details.skill,
            difficulty_estimate=action_details.difficulty_estimate,
            difficulty_justification=action_details.difficulty_justification,
            character_name=self.character_state.name,
            agent_id=self.agent_id,
            action_type=action_details.action_type,
            # Action-specific fields (may be None for non-applicable action types)
            target=getattr(action_details, 'target', None),
            target_position=getattr(action_details, 'target_position', None),
            vendor_id=getattr(action_details, 'vendor_id', None),
            item_id=getattr(action_details, 'item_id', None),
            transfer_target=getattr(action_details, 'transfer_target', None),
            transfer_currency=getattr(action_details, 'transfer_currency', None),
            transfer_items=getattr(action_details, 'transfer_items', None),
            # Attunement-specific fields
            target_energy=getattr(action_details, 'target_energy', None),
            altar_id=getattr(action_details, 'altar_id', None),
            use_echo_calibrator=getattr(action_details, 'use_echo_calibrator', None)
        )

        return action_declaration

    async def _generate_llm_action_structured(self, recent_intents: List[str], exclude_dialogue: bool = False):
        """Generate structured action using LLM with enhanced prompts."""
        from .action_schema import ActionDeclaration

        # Get other party members for dialogue prompts
        other_players = []
        if self.shared_state:
            other_players = self.shared_state.get_other_players(self.agent_id)

        # Build system prompt using new prompt_loader system
        system_prompt = self._build_player_system_prompt_new(
            recent_intents=recent_intents,
            other_players=other_players
        )

        scenario_context = ""
        if self.current_scenario:
            vendor_info = ""
            # Check for vendors (supports both single vendor dict and vendor list)
            vendors = self.current_scenario.get('active_vendors', [])
            if not vendors and self.current_scenario.get('active_vendor'):
                # Backwards compatibility: single vendor dict
                vendors = [self.current_scenario['active_vendor']]

            if vendors:
                vendor_info = "\n**💰 VENDORS PRESENT:**\n\n"
                for vendor in vendors:
                    vendor_id = vendor.get('vendor_id', 'unknown')
                    vendor_info += f"**{vendor['name']}** ({vendor['faction']} {vendor['type']}) `[{vendor_id}]`\n"
                    vendor_info += f"\"{vendor['greeting']}\"\n\n"

                    # Show full inventory with prices
                    if 'inventory' in vendor and vendor['inventory']:
                        vendor_info += "**Inventory:**\n"
                        for item in vendor['inventory'][:8]:  # Show first 8 items
                            item_id = item.get('item_id', 'unknown')
                            prices = []
                            if item.get('price_spark', 0) > 0:
                                prices.append(f"{item['price_spark']} Spark")
                            if item.get('price_drip', 0) > 0:
                                prices.append(f"{item['price_drip']} Drip")
                            if item.get('price_breath', 0) > 0:
                                prices.append(f"{item['price_breath']} Breath")
                            price_str = " or ".join(prices) if prices else "Free"
                            vendor_info += f"- **{item['name']}** `[{item_id}]` - {price_str}\n"

                        if len(vendor['inventory']) > 8:
                            vendor_info += f"  _(and {len(vendor['inventory']) - 8} more items)_\n"
                    elif 'inventory_preview' in vendor:
                        # Fallback: Sample goods preview
                        vendor_info += f"Sample goods: {', '.join(vendor.get('inventory_preview', []))}\n"

                    vendor_info += "\n"

                vendor_info += "**To purchase:** Set action_type='purchase', provide vendor_id and item_id.\n"
                vendor_info += "Example: `action_type: 'purchase', vendor_id: 'vnd_a1b2', item_id: 'itm_c3d4'`\n"

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
                        if clock.advance_meaning:
                            clock_line += f"\n  Advance = {clock.advance_meaning}"
                        if clock.regress_meaning:
                            clock_line += f" | Regress = {clock.regress_meaning}"
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

        # Add tactical combat context
        tactical_combat_context = ""
        logger.debug(f"Checking tactical combat context for {self.character_state.name}")
        logger.debug(f"  has shared_state: {self.shared_state is not None}")

        # Check for free targeting mode FIRST (works with or without enemies)
        config = self.shared_state.session_config if self.shared_state else {}
        enemy_config = config.get('enemy_agent_config', {})
        free_targeting = enemy_config.get('free_targeting_mode', True)  # Default: enabled

        # Get active enemies (empty list if enemy combat disabled)
        active_enemies = []
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            logger.debug(f"  enemy_combat exists: {enemy_combat is not None}")
            if enemy_combat:
                logger.debug(f"  enemy_combat.enabled: {enemy_combat.enabled}")
                logger.debug(f"  enemy_agents count: {len(enemy_combat.enemy_agents)}")

                if enemy_combat.enabled:
                    from .enemy_spawner import get_active_enemies
                    active_enemies = get_active_enemies(enemy_combat.enemy_agents)
                    logger.debug(f"Player {self.character_state.name}: {len(active_enemies)} active enemies present")

        # Build tactical context for targeting
        # In free targeting mode: ALWAYS show UI (IFF/ROE testing - PCs can heal/harm each other)
        # In standard mode: only show UI when enemies present (backward compatible)
        if free_targeting or active_enemies:
            # Build weapon inventory summary (for lethal/non-lethal choices)
            weapon_inventory_text = ""
            if hasattr(self, 'equipped_weapons') and hasattr(self, 'weapon_inventory'):
                equipped_list = []
                if self.equipped_weapons.get('primary'):
                    wpn = self.equipped_weapons['primary']
                    equipped_list.append(f"Primary: {wpn.name} ({wpn.damage_type.upper()} damage)")
                if self.equipped_weapons.get('sidearm'):
                    wpn = self.equipped_weapons['sidearm']
                    equipped_list.append(f"Sidearm: {wpn.name} ({wpn.damage_type.upper()} damage)")

                carried_list = []
                for wpn in self.weapon_inventory:
                    carried_list.append(f"{wpn.name} ({wpn.damage_type.upper()})")

                if equipped_list or carried_list:
                    weapon_inventory_text = "\n\n🔫 **Your Weapons:**\n"
                    if equipped_list:
                        weapon_inventory_text += "**Equipped:** " + ", ".join(equipped_list) + "\n"
                    if carried_list:
                        weapon_inventory_text += "**Carried in inventory:** " + ", ".join(carried_list) + "\n"
                    weapon_inventory_text += "\n**Damage Types:**\n"
                    weapon_inventory_text += "- STUN = Non-lethal (knockout, bruising, recovers after combat)\n"
                    weapon_inventory_text += "- MIXED = Partially lethal (some wounds, some stuns)\n"
                    weapon_inventory_text += "- WOUND = Fully lethal (can kill)\n"
                    weapon_inventory_text += "\n**IMPORTANT:** Specify which weapon you're using in your action! You can swap weapons if needed.\n"

            if free_targeting:
                # FREE TARGETING MODE: Unified combatant list with generic IDs
                target_id_mapper = self.shared_state.get_target_id_mapper()
                combatants = []

                # Add all players (including self)
                all_players = self.shared_state.get_all_players()
                for pc in all_players:
                    tgt_id = target_id_mapper.get_target_id(pc.agent_id)
                    if tgt_id:
                        pc_name = pc.character_state.name
                        pc_position = str(getattr(pc, 'position', 'Unknown'))
                        pc_health = pc.health  # Health is on AIPlayerAgent, not CharacterState
                        pc_max_health = pc.max_health
                        void_score = pc.character_state.void_score

                        # Build wound indicator (shows injury severity to teammates)
                        pc_wounds = getattr(pc, 'wounds', 0)
                        if pc_wounds >= 4:
                            wound_indicator = f" | {pc_wounds}w (HEAVY -15) ⚠️"
                        elif pc_wounds >= 2:
                            wound_indicator = f" | {pc_wounds}w (WOUNDED -5)"
                        elif pc_wounds == 1:
                            wound_indicator = f" | {pc_wounds}w"
                        else:
                            wound_indicator = ""

                        # Build stun indicator
                        pc_stuns = getattr(pc, 'stuns', 0)
                        stun_indicator = f" | {pc_stuns}s" if pc_stuns > 0 else ""

                        combatants.append(f"[{tgt_id}] {pc_name:20s} | {pc_position:12s} | {pc_health}/{pc_max_health} HP{wound_indicator}{stun_indicator} | Void {void_score}/10")

                # Add all active enemies
                for enemy in active_enemies:
                    tgt_id = target_id_mapper.get_target_id(enemy.agent_id)
                    if tgt_id:
                        combatants.append(f"[{tgt_id}] {enemy.name:20s} | {str(enemy.position):12s} | {enemy.health}/{enemy.max_health} HP")

                combatants_text = "\n  ".join(combatants)

                # Add NPCs if present
                npc_section = ""
                if self.shared_state and hasattr(self.shared_state, 'npc_agents') and self.shared_state.npc_agents:
                    npcs = []
                    for npc in self.shared_state.npc_agents:
                        # Get NPC target ID
                        tgt_id = target_id_mapper.get_target_id(npc.agent_id)
                        if tgt_id:
                            # Format disposition with emoji
                            disp_emoji = {
                                "friendly": "🤝",
                                "neutral": "😐",
                                "wary": "😟",
                                "prisoner": "🔒"
                            }.get(npc.disposition, "❓")

                            npcs.append(f"[{tgt_id}] {npc.name:30s} | {disp_emoji} {npc.disposition:10s} | {npc.health}/{npc.max_health} HP")

                    if npcs:
                        npcs_text = "\n  ".join(npcs)
                        npc_section = f"""

👥 **NPCs PRESENT** (Non-Combatants):

  {npcs_text}

**NPC Interactions:**
- NPCs can be targeted for social actions (negotiation, interrogation, assistance)
- Use their target ID [tgt_XXXX] just like combatants
- Prisoners may have intel, neutrals may help/flee, wary NPCs are unpredictable
- Attacking NPCs may escalate them back to enemies!
"""

                tactical_combat_context = f"""

⚔️  **COMBAT SITUATION** ⚔️

⚠️  Combatants in Combat Zone:

  {combatants_text}{npc_section}

**YOUR CHARACTER**: {self.character_state.name}
**YOUR FACTION**: {self.character_state.faction}

⚠️  **CRITICAL TARGETING INSTRUCTIONS** ⚠️
- Each person has a unique ID in brackets: [tgt_XXXX]
- You MUST use the target ID when targeting, NOT the name
- CORRECT: TARGET: tgt_7a3f
- WRONG: TARGET: Gang Ambushers (this will FAIL!)

**How to decide who to target:**
1. Read the names to identify faction allegiance
2. Consider your faction relationships ({self.character_state.faction})
3. Use the target ID (in brackets) when declaring your target

⚠️  **WARNING**: You can target ANYONE on this list, including allies or party members. Choose carefully!

⚠️  **ONE ACTION PER TURN - DO NOT COMBINE ACTIONS** ⚠️

Your action should have ONE clear subject and ONE clear intent:
- ✓ "Purify void corruption from Riven"
- ✓ "Attack the Void Spawn with rifle"
- ✓ "Share tactical analysis with Ash"
- ✗ "Help Riven then attack the corruption" (TWO actions!)
- ✗ "Coordinate with Ash before engaging enemies" (TWO actions!)

If you want to coordinate: make that your action.
If you want to attack: make that your action.
Do NOT try to do both in one turn.
{weapon_inventory_text}"""

            else:
                # STANDARD MODE: Enemy-only list (backwards compatible)
                if active_enemies:
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

⚠️  **TARGETING FORMAT** ⚠️
When declaring combat actions, use the enemy NAME exactly as listed above:
- CORRECT: target: "Tempest Operatives"
- WRONG: target: "tgt_tempest_operatives" (don't invent IDs!)
- WRONG: target: "the enemies" (be specific!)

{weapon_inventory_text}
💬 **SOCIAL DE-ESCALATION OPTIONS** 💬
Combat doesn't always require killing! Consider non-violent neutralization:

**Intimidation** (Willpower × Intimidation skill):
- Threat display to force surrender/retreat
- Best when: You have numbers advantage, enemy is wounded, allies are down
- **IMPORTANT**: Use `attribute: "Willpower", skill: "Intimidation"` in your action
- Example intent: "Intimidate the wounded smuggler into surrendering"
- Example description: "I aim my weapon at the wounded smuggler: 'Drop it NOW or join your friends!'"
- On success: Enemy may surrender or flee (forced morale check)
- Your Intimidation skill: {self.character_state.skills.get('Intimidation', 0)}

**Persuasion** (Empathy × Persuasion skill):
- Offer terms, appeal to self-preservation
- Best when: Enemy is cornered, no escape route, not fanatic
- **IMPORTANT**: Use `attribute: "Empathy", skill: "Persuasion"` in your action
- Example intent: "Persuade the cornered smuggler to stand down"
- Example description: "I lower my weapon slightly: 'You're not getting paid enough to die here. Walk away.'"
- On success: Enemy may surrender or negotiate
- Your Persuasion skill: {self.character_state.skills.get('Persuasion', 0)}

**When to use social actions:**
- Enemy health < 50% (desperate, more likely to surrender)
- Multiple enemies down (morale shaken)
- You've surrounded them (tactical hopelessness)
- They're NOT fanatics/void-possessed (check enemy type)

⚠️  Social actions are RISKY in active combat - enemy may attack during negotiation!
⚠️  Some enemies (cultists, void-possessed) may be immune to intimidation

**Combat Priority:**
1. **ATTACK** - Shoot/stab/punch an enemy (specify which enemy and how)
   - Ranged attacks: Use Agility × Combat skill
   - Melee attacks: Use Agility × Combat skill (or Strength × Combat for heavy weapons)
2. **INTIMIDATE/PERSUADE** - Force surrender without killing (if tactical advantage exists)
3. **REPOSITION WHILE ATTACKING** - Move + shoot (if needed for range/cover)
4. **Only reposition without attacking if:**
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
                else:
                    # NO active enemies - make this CRYSTAL CLEAR to prevent targeting ghosts
                    tactical_combat_context = """

✅ **NO ACTIVE COMBATANTS** ✅

There are currently NO combatants in the targeting list. All forces have been defeated or withdrawn.

⚠️  **CRITICAL**: Do NOT target anyone that doesn't exist!
⚠️  **DO NOT** use TARGET field - there is no one to target!
⚠️  **DO NOT** target names from narration that aren't in the list above!

If the DM mentions enemies in narration but they're not listed above with HP/position, they are NOT targetable enemies - they may be:
- Already defeated
- Not yet arrived (reinforcements)
- Background/narrative elements only

Available non-combat actions:
- Investigate the area (Awareness, Perception)
- Reposition tactically (Athletics)
- Prepare defenses or fortifications
- Search for clues/evidence (Investigation)
- Assist/evacuate civilians
- Prepare for incoming enemies

**DO NOT ATTACK NON-EXISTENT ENEMIES!** Only attack enemies explicitly listed with HP and position.
"""
        else:
            tactical_combat_context = ""

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

        # Build narrative context section (what's been happening in the story)
        narrative_context = ""

        # Add round synthesis (overall story progression)
        if self.last_round_synthesis:
            narrative_context += "\n# 📖 Recent Story Events\n\n"
            narrative_context += "## What Just Happened (Last Round Summary):\n"
            narrative_context += f"{self.last_round_synthesis}\n\n"

        # Add recent action resolution narrations (specific outcomes)
        if self.recent_narrations:
            if not narrative_context:
                narrative_context += "\n# 📖 Recent Story Events\n\n"
            narrative_context += "## Recent Action Outcomes:\n"
            # Show ALL recent narrations (rolling window already limits to last 20)
            for i, narration in enumerate(self.recent_narrations, 1):
                # Keep full narration - this is juicy coordination info!
                narrative_context += f"{i}. {narration}\n\n"

        # Add declared actions this round (only from agents with LOWER initiative who declared before you)
        if self.declared_actions_this_round:
            # Filter to only show agents who declared before this player (lower initiative = declared first)
            current_init = getattr(self, 'current_initiative', 0)
            filtered_declarations = {
                char_name: action_data
                for char_name, action_data in self.declared_actions_this_round.items()
                if action_data[-1] < current_init  # initiative is always last element
            }

            if filtered_declarations:
                if not narrative_context:
                    narrative_context += "\n# 📖 Recent Story Events\n\n"

                # Sort by initiative (slowest first, matching declaration order)
                sorted_declarations = sorted(
                    filtered_declarations.items(),
                    key=lambda x: x[1][-1]  # initiative is always last element
                )

                narrative_context += f"## 🎯 {DECLARED_ACTIONS_HEADER} (Initiative Order):\n"
                narrative_context += "*You see what slower combatants (lower initiative) declared before you. React accordingly!*\n\n"
                for char_name, action_data in sorted_declarations:
                    # Current format: (description, intent, target, weapon, reasoning, initiative)
                    if len(action_data) == 6:
                        description, intent, target, weapon, reasoning, initiative = action_data

                        # Format action with targeting info if available
                        if description:
                            # NPCs and players with descriptions
                            action_text = description
                        else:
                            # Enemies without description - build from components
                            action_text = intent
                            if target:
                                action_text += f" targeting {target}"
                            if weapon:
                                action_text += f" with {weapon}"

                        narrative_context += f"- **{char_name}** [Init {initiative}]: {action_text}\n"
                    elif len(action_data) == 3:
                        # Legacy format (description, intent, initiative)
                        description, intent, initiative = action_data
                        narrative_context += f"- **{char_name}** [Init {initiative}]: {description if description else intent}\n"
                    else:
                        # Very old format (intent, initiative)
                        intent, initiative = action_data
                        narrative_context += f"- **{char_name}** [Init {initiative}]: {intent}\n"
                narrative_context += "\n"

        prompt = f"""{system_prompt}

{scenario_context}
{narrative_context}
{tactical_combat_context}
{party_knowledge}

Declare your next action using the required format:

```
INTENT: [what you're doing]
ATTRIBUTE: [which attribute]
SKILL: [which skill or None]
DIFFICULTY: [estimate]
JUSTIFICATION: [why that difficulty]
ACTION_TYPE: [explore/investigate/ritual/social/combat/technical]
TARGET: [tgt_XXXX from list above, or None]
TARGET_POSITION: [if moving: Engaged/Near-PC/Far-PC/Extreme-PC/Near-Enemy/Far-Enemy/Extreme-Enemy, otherwise: None]
DESCRIPTION: [narrative description]
```

**NOTE ON TARGETING:**
- TARGET is neutral - your INTENT determines whether this is friendly, hostile, or neutral
- You can target anyone (ally, enemy, or neutral) - the situation determines the outcome
- If you don't need a target (exploration, investigation), use TARGET: None"""

        # Try structured output first (Phase 3: Pydantic AI migration)
        if hasattr(self, 'llm_provider') and self.llm_provider is not None:
            # NO FALLBACK - if structured output fails, we want to know immediately
            structured_action = await self._generate_player_action_pydantic(prompt)
            if structured_action:
                logger.debug(f"✓ Player {self.character_state.name} structured action: {structured_action.action_type}")
                return structured_action
            else:
                raise RuntimeError(f"Player {self.character_state.name}: Structured output returned None (should have raised error)")

        # Legacy text parsing fallback
        try:
            provider = self.llm_config.get('provider', 'anthropic')
            model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')
            temperature = self.llm_config.get('temperature', 1.0)

            if provider == 'anthropic':
                # Use rate-limited wrapper to prevent API overload
                from .llm_provider import call_anthropic_with_retry

                response = await call_anthropic_with_retry(
                    client=self.llm_client,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=temperature,
                    max_retries=3,
                    base_delay=2.0,
                    max_delay=120.0,
                    use_rate_limiter=True
                )
                llm_text = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=llm_text,
                        model=model,
                        temperature=temperature,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1
            else:
                # Fallback to simple action
                return self._generate_simple_action(recent_intents, self.personality.get('riskTolerance', 5), self.personality.get('voidCuriosity', 3))

            # Check if agent requested a rules/lore lookup
            if 'LOOKUP:' in llm_text:
                logger.debug(f"🔍 Agent {self.character_state.name} requested a lookup")
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

        logger.debug(f"  Query: '{lookup_query}'")

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
                # Use rate-limited wrapper to prevent API overload
                from .llm_provider import call_anthropic_with_retry

                response = await call_anthropic_with_retry(
                    client=self.llm_client,
                    model=model,
                    messages=[{"role": "user", "content": followup_prompt}],
                    max_tokens=300,
                    temperature=temperature,
                    max_retries=3,
                    base_delay=2.0,
                    max_delay=120.0,
                    use_rate_limiter=True
                )
                followup_text = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": followup_prompt}],
                        response=followup_text,
                        model=model,
                        temperature=temperature,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

                return followup_text
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
            'dexterity': 'Dexterity',
            'perception': 'Perception',
            'intelligence': 'Intelligence',
            'empathy': 'Empathy',
            'willpower': 'Willpower'
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
                elif 'target' in key and 'target_character' not in key and 'target_position' not in key:
                    # Extract target if specified (neutral - could be friendly, hostile, or neutral)
                    if value.lower() != 'none':
                        data['target'] = value

                        # Resolve target ID to actual name for logging
                        target_display = value
                        if value.startswith('tgt_') and self.shared_state:
                            target_id_mapper = self.shared_state.get_target_id_mapper()
                            if target_id_mapper and target_id_mapper.enabled:
                                target_entity = target_id_mapper.resolve_target(value)
                                if target_entity:
                                    # Get name from either enemy or PC
                                    if hasattr(target_entity, 'name'):
                                        target_display = f"{target_entity.name} ({value})"
                                    elif hasattr(target_entity, 'character_state'):
                                        target_display = f"{target_entity.character_state.name} ({value})"

                        logger.info(f"{self.character_state.name} targeting: {target_display}")

                elif 'target_character' in key or 'target_pc' in key:
                    # Universal character targeting (for rituals, buffs, debuffs, IFF scenarios)
                    if value.lower() not in ['none', '']:
                        # Handle "self" keyword
                        if value.lower() == 'self':
                            data['target_character'] = self.character_state.name
                            logger.info(f"{self.character_state.name} targeting self")
                        else:
                            # Resolve target ID to actual name
                            target_display = value
                            if value.startswith('tgt_') and self.shared_state:
                                target_id_mapper = self.shared_state.get_target_id_mapper()
                                if target_id_mapper and target_id_mapper.enabled:
                                    target_entity = target_id_mapper.resolve_target(value)
                                    if target_entity:
                                        # Get name from either enemy or PC
                                        if hasattr(target_entity, 'name'):
                                            target_display = target_entity.name
                                            data['target_character'] = target_entity.name
                                        elif hasattr(target_entity, 'character_state'):
                                            target_display = target_entity.character_state.name
                                            data['target_character'] = target_entity.character_state.name
                                    else:
                                        # Couldn't resolve combat ID, use as-is
                                        data['target_character'] = value
                                else:
                                    # No combat ID mapper, use as-is
                                    data['target_character'] = value
                            else:
                                # Direct name targeting
                                data['target_character'] = value

                            logger.info(f"{self.character_state.name} targeting character: {target_display}")
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