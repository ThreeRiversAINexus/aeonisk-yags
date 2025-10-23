"""
AI Dungeon Master agent for multi-agent self-playing system.
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
from .energy_economy import Vendor, VendorType, create_standard_vendors

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
    active_vendor: Optional[Vendor] = None  # Vendor present in this scenario
    required_purchase: Optional[str] = None  # Item that MUST be purchased to proceed
    vendor_gate_description: Optional[str] = None  # Description of why purchase is needed


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

        # Vendor pool for random encounters
        self.vendor_pool = create_standard_vendors()

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
        self.config = config  # Store for later use

        if self.human_controlled:
            await self._request_human_scenario(config)
        else:
            await self._generate_ai_scenario(config)
            
    async def _generate_ai_scenario(self, config: Dict[str, Any]):
        """Generate scenario using AI with lore grounding."""
        # Check if vendor-gated or combat scenario is requested
        force_vendor_gate = config.get('force_vendor_gate', False)
        force_combat = config.get('force_combat', False)

        # Query knowledge retrieval for Aeonisk lore
        lore_context = ""
        variety_context = ""
        party_context = ""

        # Extract player information from config
        players_config = config.get('agents', {}).get('players', [])
        if players_config:
            party_context = "=== PARTY COMPOSITION ===\n"
            party_context += "Your scenario MUST be appropriate for this specific party:\n\n"

            for player in players_config:
                name = player.get('name', 'Unknown')
                faction = player.get('faction', 'Unknown')
                goals = player.get('goals', [])

                party_context += f"**{name}** ({faction})\n"
                party_context += f"  Goals:\n"
                for goal in goals:
                    party_context += f"  - {goal}\n"
                party_context += "\n"

            party_context += "CRITICAL FACTION RULES:\n"
            party_context += "- DO NOT create scenarios where characters must betray their own faction\n"
            party_context += "- DO NOT hire characters to steal from/sabotage their own faction's assets\n"
            party_context += "- Sovereign Nexus owns: Codex Cathedral, Sanctified Archives, Gestation Chambers, Ley Networks\n"
            party_context += "- Pantheon Security owns: Law enforcement facilities, civic infrastructure, security systems\n"
            party_context += "- ACG owns: Debt registries, contract archives, commerce hubs\n"
            party_context += "- ArcGen owns: Biocreche facilities, genetic research labs, pod gestation tech\n"
            party_context += "- Tempest owns: Void energy facilities, industrial complexes, autonomous systems\n"
            party_context += "- If creating faction conflict scenarios, make it BETWEEN different factions, not against one's own\n"
            party_context += "- Characters should be aligned with their faction's interests OR face a clear moral dilemma\n\n"

        if self.shared_state:
            knowledge = self.shared_state.get_knowledge_retrieval()
            if knowledge:
                # Query for canonical locations, factions, and setting elements
                lore_results = knowledge.query("Aeonisk setting locations factions floating cities Arcadia Nimbus Elysium void corruption", n_results=3)
                if lore_results:
                    lore_context = "CANONICAL AEONISK LORE (you MUST use this):\n\n"
                    for result in lore_results:
                        lore_context += f"{result['content'][:400]}\n\n"
                    lore_context += "\nKEY CONSTRAINTS:\n"
                    lore_context += "- Setting: Three inhabited planets (Aeonisk Prime, Nimbus, Arcadia) with space travel between them\n"
                    lore_context += "- Species: Humans only (NO aliens, NO other species)\n"
                    lore_context += "- Locations: Floating cities, terrestrial zones, orbital stations, space transit\n"
                    lore_context += "- Factions: Tempest Industries, Resonance Communes, Astral Commerce Group, Arcane Genetics, Pantheon Security, House of Vox, Sovereign Nexus, Freeborn\n"
                    lore_context += "- Eye of Breach: Rogue AI aligned with Tempest Industries, appears during high void corruption\n"
                    lore_context += "- Themes: Memory manipulation, void corruption, corporate intrigue, bond economics\n\n"

            # Get variety requirements
            variety_context = self.shared_state.get_recent_scenario_info()

        # Use vendor-gated or combat scenario if requested
        if force_vendor_gate:
            logger.info("Force vendor gate enabled - using vendor-gated scenario template")
            scenario_data = self._create_vendor_gated_scenario()
        elif force_combat:
            logger.info("Force combat enabled - using combat scenario template")
            scenario_data = self._create_combat_scenario(config)
        else:
            # Use LLM to generate dynamic scenario
            try:
                scenario_prompt = f"""Generate a unique Aeonisk YAGS scenario for a tabletop RPG session.

{party_context}
{lore_context}
{variety_context}

Create a scenario with:
1. Theme (2-3 words): The type of situation
2. Location: A specific place in the Aeonisk setting (USE CANONICAL LOCATIONS FROM LORE ABOVE)
3. Situation (1-2 sentences): What's happening
4. Void level (0-10): Environmental void corruption. Most scenarios should be 2-4 (mild corruption). Only use 6+ for void outbreak/crisis scenarios.
5. Three clocks/timers with CLEAR SEMANTICS:
   - A threat/danger that could escalate
   - Something the players are trying to accomplish
   - A complication or secondary concern

   **CRITICAL**: For each clock, specify what it means to ADVANCE and REGRESS:
   - If advancing = getting worse for players (danger increasing, time running out)
     → Name it clearly: "Security Alert", "Structural Collapse", "Hunter Pursuit"
   - If advancing = progress on objective (evidence gathering, defenses built)
     → Name it clearly: "Evidence Collection", "Defenses Established", "Evacuation Progress"
   - ALWAYS specify what happens when filled

Format:
THEME: [theme]
LOCATION: [location from canonical lore]
SITUATION: [situation]
VOID_LEVEL: [number]
CLOCK1: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]
CLOCK2: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]
CLOCK3: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]

Example clock:
CLOCK1: Security Alert | 6 | Corporate hunters closing in | ADVANCE=Hunters get closer to finding the team | REGRESS=Team evades or misleads pursuit | FILLED=Hunter team arrives, combat or escape required

IMPORTANT:
- Base your scenario on the canonical lore provided above
- Three planets: Aeonisk Prime, Nimbus, Arcadia (space travel between them is possible)
- Humans only, NO aliens
- Pick a DIFFERENT theme and location from recently used ones (if listed above)
- Be creative with scenario types:
  * COMBAT: **ambush**, **firefight**, **battle**, **siege**, **assault**, **defense**, **void creature attack**, **hostile extraction**, **combat rescue**, **gang warfare**
  * SOCIAL: tribunal/trial, bond dispute, debt settlement, trade negotiation, vendor conflict, economic disputes, social scandal
  * INTRIGUE: heist, investigation, ritual gone wrong, faction conflict, ancient mystery, political intrigue, transit crisis
  * CRISIS: void outbreak, station breach, emergency evacuation, containment failure
- **VARIETY IS KEY**: Mix combat scenarios with social/economic ones. Not every scenario needs combat, but battles and firefights should appear regularly
- **Combat scenarios**: Ambushes by rival factions, void-corrupted threats, gang turf wars, hostile encounters during missions, defensive stands
- **Vendor/Economy scenarios**: Resource acquisition, price negotiations, debt settlement, economic crime investigation
- If Tempest Industries is involved OR void level is 6+, consider mentioning Eye of Breach (rogue AI) as a potential threat or presence
- ⚠️ CRITICAL: Respect the party composition above. DO NOT create scenarios where characters betray their own faction
- ⚠️ CRITICAL: Align scenarios with character goals OR create interesting cross-faction cooperation (e.g., Sovereign Nexus + ArcGen investigating a shared threat)
- Good examples: ACG hires party to recover stolen debt contracts, Pantheon investigates void corruption, factions team up against common enemy
- BAD examples: ACG hires Sovereign Nexus to steal from Codex Cathedral, hiring characters to sabotage their own faction"""

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

                # Enforce variety - reject if location matches recent scenarios
                if self.shared_state:
                    recent_scenarios = self.shared_state.recent_scenarios
                    location_lower = scenario_data['location'].lower()

                    # Check if this location was recently used
                    for recent in recent_scenarios:
                        if recent['location'].lower() in location_lower or location_lower in recent['location'].lower():
                            print(f"[DM {self.agent_id}] Location '{scenario_data['location']}' was recently used - regenerating...")

                            # Try ONE more time with stronger emphasis
                            retry_prompt = scenario_prompt.replace(
                                "Pick a DIFFERENT theme and location",
                                "❗ CRITICAL: You MUST pick a completely different location. DO NOT use any of the locations listed above"
                            )

                            response = await asyncio.to_thread(
                                client.messages.create,
                                model=model,
                                max_tokens=500,
                                temperature=1.0,  # Higher temperature for more creativity
                                messages=[{"role": "user", "content": retry_prompt}]
                            )
                            llm_text = response.content[0].text.strip()
                            scenario_data = self._parse_scenario_from_llm(llm_text)
                            break  # Only check first match and retry once

            except Exception as e:
                logger.error(f"Failed to generate AI scenario: {e}, using fallback")
                # Fallback to simple random scenario
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

        # Scenario-aware vendor encounter
        # If vendor-gated scenario, force specific vendor type
        if scenario_data.get('required_vendor_type'):
            required_type = scenario_data['required_vendor_type']
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type == required_type]
            if eligible_vendors:
                active_vendor = random.choice(eligible_vendors)
                logger.info(f"Vendor-gated scenario: forcing {active_vendor.name} ({active_vendor.vendor_type.value})")
                print(f"[DM {self.agent_id}] 🔒 VENDOR REQUIRED: {active_vendor.name}")
            else:
                logger.error(f"No vendor of type {required_type} available!")
                active_vendor = None
        else:
            active_vendor = self._select_contextual_vendor(scenario_data['theme'])
        if active_vendor:
            logger.info(f"Vendor encounter: {active_vendor.name} ({active_vendor.vendor_type.value})")
            print(f"[DM {self.agent_id}] 💰 {active_vendor.name} present")

        scenario = Scenario(
            theme=scenario_data['theme'],
            location=scenario_data['location'],
            situation=scenario_data['situation'],
            active_npcs=[],
            environmental_factors=[],
            void_level=scenario_data['void_level'],
            active_vendor=active_vendor,
            required_purchase=scenario_data.get('required_purchase'),
            vendor_gate_description=scenario_data.get('vendor_gate_description')
        )

        self.current_scenario = scenario

        # Initialize mechanics and create scenario-specific clocks
        if self.shared_state:
            self.shared_state.initialize_mechanics()
            mechanics = self.shared_state.get_mechanics_engine()

            for clock_data in scenario_data.get('clocks', []):
                clock_name = clock_data[0]
                max_value = clock_data[1]
                description = clock_data[2] if len(clock_data) > 2 else ""
                advance_means = clock_data[3] if len(clock_data) > 3 else ""
                regress_means = clock_data[4] if len(clock_data) > 4 else ""
                filled_consequence = clock_data[5] if len(clock_data) > 5 else ""

                mechanics.create_scene_clock(
                    clock_name, max_value, description,
                    advance_means, regress_means, filled_consequence
                )
                print(f"[DM {self.agent_id}] Created clock: {clock_name} (0/{max_value})")

        # Validate scenario against party composition
        faction_conflicts = self._detect_faction_conflicts(scenario, players_config)

        # Apply soulcredit penalties for high-severity conflicts
        if faction_conflicts and self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                for conflict in faction_conflicts:
                    if conflict['severity'] == 'high' and conflict['type'] == 'faction_betrayal':
                        # Find the affected player's agent_id
                        character_name = conflict['character']
                        # Apply -2 soulcredit penalty for faction betrayal
                        # Note: We'd need to map character name to agent_id here
                        # For now, log the warning
                        logger.warning(f"⚠️ FACTION BETRAYAL DETECTED: {conflict['conflict']}")
                        print(f"\n⚠️  WARNING: {conflict['conflict']}")
                        print(f"   This may result in soulcredit loss if pursued.")

        # Log scenario to JSONL
        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'active_vendor': {
                'name': scenario.active_vendor.name,
                'type': scenario.active_vendor.vendor_type.value,
                'faction': scenario.active_vendor.faction,
                'greeting': scenario.active_vendor.greeting,
                'inventory_preview': [item.name for item in scenario.active_vendor.inventory[:3]]  # First 3 items
            } if scenario.active_vendor else None
        }
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_scenario(scenario_data)

        # Broadcast scenario setup
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,  # broadcast
            {
                'scenario': scenario_data,
                'opening_narration': self._generate_opening_narration(scenario, faction_conflicts),
                'faction_conflicts': faction_conflicts  # Warn players of potential issues
            }
        )

        print(f"\n[DM {self.agent_id}] Generated scenario: {scenario.theme}")
        print(f"Location: {scenario.location}")
        print(f"Situation: {scenario.situation}")

        # Track scenario for variety in future sessions
        if self.shared_state:
            self.shared_state.add_scenario(scenario.theme, scenario.location)
            # Save to persistent dm_notes.json
            from pathlib import Path
            dm_notes_path = Path('./multiagent_output') / 'dm_notes.json'
            self.shared_state.save_dm_notes(str(dm_notes_path))
        
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

        # Log scenario to JSONL
        scenario_data = {
            'theme': theme,
            'location': location,
            'situation': situation,
            'void_level': void_level
        }
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_scenario(scenario_data)

        # Broadcast scenario
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,
            {
                'scenario': scenario_data,
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
                    # Format: CLOCK1: Name | 6 | Description | ADVANCE=... | REGRESS=... | FILLED=...
                    parts = line.split(':', 1)[1].split('|')
                    if len(parts) >= 3:
                        name = parts[0].strip()
                        try:
                            max_ticks = int(parts[1].strip())
                        except:
                            max_ticks = 6
                        description = parts[2].strip()

                        # Extract semantic guidance
                        advance_means = ""
                        regress_means = ""
                        filled_consequence = ""

                        for part in parts[3:]:
                            part = part.strip()
                            if part.startswith('ADVANCE='):
                                advance_means = part.replace('ADVANCE=', '').strip()
                            elif part.startswith('REGRESS='):
                                regress_means = part.replace('REGRESS=', '').strip()
                            elif part.startswith('FILLED='):
                                filled_consequence = part.replace('FILLED=', '').strip()

                        scenario_data['clocks'].append((
                            name, max_ticks, description,
                            advance_means, regress_means, filled_consequence
                        ))

        # Ensure we have at least 2 clocks
        if len(scenario_data['clocks']) < 2:
            scenario_data['clocks'].append(('Danger Escalation', 6, 'The situation worsens'))
            scenario_data['clocks'].append(('Player Progress', 6, 'Investigating the mystery'))

        return scenario_data

    def _create_vendor_gated_scenario(self) -> Dict[str, Any]:
        """
        Create a scenario where purchasing a specific item is REQUIRED to proceed.

        Returns scenario_data dict with vendor requirements baked in.
        """
        templates = [
            {
                'theme': 'Locked Tech Gate',
                'location': 'Sealed Research Facility (Arcadia)',
                'situation': 'The facility requires a Scrambled ID Chip to bypass security. The entrance scanner rejects all standard credentials.',
                'void_level': 3,
                'required_purchase': 'Scrambled ID Chip',
                'vendor_gate': 'Without a Scrambled ID Chip, the security system cannot be bypassed.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # "Cipher" has this
                'clocks': [
                    ('Security Lockdown', 6, 'Facility going into full lockdown'),
                    ('Data Extraction', 6, 'Retrieving critical intel before wipe'),
                    ('Rival Team', 5, 'Competing group closing in')
                ]
            },
            {
                'theme': 'Ritual Emergency',
                'location': 'Unstable Ley Node (Nimbus)',
                'situation': 'Raw Seeds in the area are degrading rapidly into Hollow Seeds. You need an Echo-Calibrator to stabilize them before they corrupt the node.',
                'void_level': 5,
                'required_purchase': 'Echo-Calibrator',
                'vendor_gate': 'Without an Echo-Calibrator, the Seeds cannot be stabilized and will become Hollow.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # Scribe Orven Tylesh or vending
                'clocks': [
                    ('Seed Corruption', 6, 'Raw Seeds degrading into Hollow'),
                    ('Node Destabilization', 8, 'Ley node collapsing'),
                    ('Void Bleed', 5, 'Environmental corruption spreading')
                ]
            },
            {
                'theme': 'Debt Settlement',
                'location': 'ACG Collections Office (Aeonisk Prime)',
                'situation': 'A contact owes you critical information, but ACG has seized their assets. They demand payment: either 8 Spark or a Bond Insurance Policy to release them from debt.',
                'void_level': 2,
                'required_purchase': 'Bond Insurance Policy',  # or pay 8 Spark
                'vendor_gate': 'The contact cannot be freed without either 8 Spark payment or a Bond Insurance Policy.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # Contract Specialist Rhen
                'clocks': [
                    ('Asset Liquidation', 6, 'Contact losing everything'),
                    ('Information Window', 5, 'Intel becoming outdated'),
                    ('ACG Pressure', 6, 'Collections becoming aggressive')
                ]
            },
            {
                'theme': 'Informant Bribe',
                'location': 'Underground Market (Floating Exchange)',
                'situation': 'A black market informant has intel on a void cult, but refuses to talk. They demand Sparksticks (addictive buzz twigs) as payment.',
                'void_level': 4,
                'required_purchase': 'Sparksticks',
                'vendor_gate': 'The informant will not provide intel without Sparksticks.',
                'required_vendor_type': VendorType.VENDING_MACHINE,  # SnackHub has this
                'clocks': [
                    ('Cult Ritual', 6, 'Void cult completing dangerous ritual'),
                    ('Informant Patience', 4, 'Informant leaving if not paid'),
                    ('Market Surveillance', 5, 'Pantheon Security closing in')
                ]
            },
            {
                'theme': 'Medical Crisis',
                'location': 'Abandoned Transit Station (Nimbus)',
                'situation': 'A party member has been exposed to void toxin. You need a Med Kit (Tactical) from the Pantheon supply drone to treat them before corruption spreads.',
                'void_level': 6,
                'required_purchase': 'Med Kit (Tactical)',
                'vendor_gate': 'Without medical treatment, the exposed character will gain +3 void corruption.',
                'required_vendor_type': VendorType.SUPPLY_DRONE,  # Pantheon Field Supply
                'clocks': [
                    ('Toxin Spread', 5, 'Corruption spreading to others'),
                    ('Medical Window', 4, 'Treatment window closing'),
                    ('Station Collapse', 6, 'Structure failing')
                ]
            },
            {
                'theme': 'Trade Negotiation',
                'location': 'House of Vox Broadcast Hub',
                'situation': 'You need access to restricted archives, but the archivist demands a Data Slate (Encrypted) as payment for black market access codes.',
                'void_level': 2,
                'required_purchase': 'Data Slate (Encrypted)',
                'vendor_gate': 'Archive access requires the Data Slate as barter.',
                'required_vendor_type': VendorType.SUPPLY_DRONE,  # House of Vox Courier
                'clocks': [
                    ('Archive Purge', 6, 'Data being deleted'),
                    ('Archivist Trust', 5, 'Window of cooperation'),
                    ('Media Sweep', 6, 'Vox censoring information')
                ]
            }
        ]

        # Select random template
        template = random.choice(templates)

        return {
            'theme': template['theme'],
            'location': template['location'],
            'situation': template['situation'],
            'void_level': template['void_level'],
            'clocks': template['clocks'],
            'required_purchase': template['required_purchase'],
            'vendor_gate_description': template['vendor_gate'],
            'required_vendor_type': template['required_vendor_type']
        }

    def _create_combat_scenario(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a combat-focused scenario (ambush, firefight, battle, etc.).

        Args:
            config: Optional session config (can specify combat_scenario_index to force specific template)

        Returns scenario_data dict for immediate combat situations.
        """
        config = config or {}
        templates = [
            {
                'theme': 'Overwhelming Ambush',
                'location': 'Kill Zone - Abandoned Transit Hub (Arcadia)',
                'situation': 'You\'ve been lured into a trap. A hostile assault team rushes you from close range while covering fire comes from above. You need to break through or take them down fast. [SPAWN_ENEMY: Assault Team | grunt | 2 | Near-Enemy | aggressive_melee]',
                'void_level': 4,
                'clocks': [
                    ('Tactical Withdrawal', 6, 'Finding a way to escape the kill zone', 'ADVANCE=Spotting escape routes', 'REGRESS=Enemies cutting off exits', 'FILLED=You find an escape route!'),
                    ('Enemy Reinforcements', 5, 'Backup being called in', 'ADVANCE=Enemies calling for backup', 'REGRESS=Delaying reinforcements', 'FILLED=Second wave arrives! [SPAWN_ENEMY: Reserve Forces | grunt | 2 | Far-Enemy | tactical_ranged]'),
                    ('Critical Wounds', 4, 'Party members taking severe injuries')
                ]
            },
            {
                'theme': 'Gang Ambush',
                'location': 'Undercity Maintenance Tunnels (Arcadia)',
                'situation': 'A Freeborn gang has set up an ambush - they think you\'re rival dealers. Muzzle flashes illuminate the darkness as they open fire from concealed positions. [SPAWN_ENEMY: Gang Ambushers | grunt | 2 | Near-Enemy | aggressive_melee]',
                'void_level': 3,
                'clocks': [
                    ('Reinforcements Arriving', 5, 'More gang members responding to gunfire', 'ADVANCE=More gang members hear the firefight', 'REGRESS=Silencing the gang', 'FILLED=Gang backup arrives! [SPAWN_ENEMY: Gang Reinforcements | grunt | 2 | Far-Enemy | defensive_ranged]'),
                    ('Escape Route', 4, 'Tunnel collapse blocking exit'),
                    ('Civilian Panic', 4, 'Nearby residents calling Pantheon Security')
                ]
            },
            {
                'theme': 'Hostile Extraction',
                'location': 'Pantheon Detention Facility (Aeonisk Prime)',
                'situation': 'Security forces have been alerted to your presence. Riot carapace troops are advancing down the corridor, shock batons crackling. You need to fight your way out. [SPAWN_ENEMY: Riot Troops | grunt | 2 | Near-Enemy | defensive_ranged]',
                'void_level': 2,
                'clocks': [
                    ('Lockdown Protocol', 4, 'Facility sealing all exits'),
                    ('Security Reinforcements', 5, 'Tactical teams deploying', 'ADVANCE=More security responding', 'REGRESS=Evading security', 'FILLED=Tactical team arrives! [SPAWN_ENEMY: Security Tacticals | grunt | 2 | Far-Enemy | tactical_ranged]'),
                    ('Asset Extraction', 4, 'Getting your contact out before they\'re moved')
                ]
            },
            {
                'theme': 'Void Creature Attack',
                'location': 'Collapsed Ley Nexus (Nimbus)',
                'situation': 'Void-touched creatures emerge from a breach in reality - warped humanoid forms with too many limbs, their bodies flickering between states. They\'re hostile and closing fast. [SPAWN_ENEMY: Void Spawn | grunt | 2 | Near-Enemy | aggressive_melee]',
                'void_level': 7,
                'clocks': [
                    ('Breach Expansion', 4, 'Reality tear growing larger'),
                    ('Creature Swarm', 5, 'More entities emerging from void', 'ADVANCE=Breach widening, more creatures', 'REGRESS=Sealing the breach', 'FILLED=Void swarm pours through! [SPAWN_ENEMY: Void Horrors | grunt | 2 | Engaged | aggressive_melee]'),
                    ('Void Exposure', 4, 'Environmental corruption affecting party')
                ]
            },
            {
                'theme': 'Faction Firefight',
                'location': 'Contested Transit Hub (Floating Exchange)',
                'situation': 'Freeborn pirates are raiding an ACG debt collection convoy. You\'re caught in the crossfire - the pirates open fire thinking you\'re ACG backup. [SPAWN_ENEMY: Freeborn Pirates | grunt | 2 | Near-Enemy | tactical_ranged]',
                'void_level': 3,
                'clocks': [
                    ('Freeborn Escape', 4, 'Pirates fighting their way to ships'),
                    ('ACG Asset Seizure', 4, 'ACG trying to secure cargo'),
                    ('Pantheon Response', 5, 'Security arriving', 'ADVANCE=Pantheon forces mobilizing', 'REGRESS=Delaying security', 'FILLED=Pantheon tactical team arrives! [SPAWN_ENEMY: Pantheon Squad | grunt | 2 | Extreme-Enemy | tactical_ranged]')
                ]
            },
            {
                'theme': 'Defense Stand',
                'location': 'Resonance Commune Sanctuary (Nimbus)',
                'situation': 'The sanctuary is under assault by void-corrupted raiders. You must hold the perimeter while civilians evacuate through the back routes. They\'re breaking through the outer walls. [SPAWN_ENEMY: Initial Raiders | grunt | 2 | Near-Enemy | aggressive_melee]',
                'void_level': 5,
                'clocks': [
                    ('Raider Reinforcements', 5, 'Second wave incoming', 'ADVANCE=More raiders arriving', 'REGRESS=Slowing reinforcements', 'FILLED=Second wave breaches! [SPAWN_ENEMY: Void Raiders | grunt | 2 | Near-Enemy | aggressive_melee]'),
                    ('Civilian Evacuation', 5, 'Getting non-combatants to safety'),
                    ('Void Corruption', 4, 'Raiders spreading corruption')
                ]
            },
            {
                'theme': 'Assassination Attempt',
                'location': 'ACG Executive Tower (Aeonisk Prime)',
                'situation': 'Hostile operatives have breached the building - they\'re here to kill someone you\'re protecting. Professional killers with military-grade weapons, moving through the floors toward your position. [SPAWN_ENEMY: Advance Scouts | grunt | 2 | Far-Enemy | tactical_ranged]',
                'void_level': 2,
                'clocks': [
                    ('Assassin Reinforcements', 3, 'More killers deploying', 'ADVANCE=Backup team getting closer', 'REGRESS=Delaying reinforcements', 'FILLED=Elite hit team arrives! [SPAWN_ENEMY: Professional Hit Team | elite | 2 | Far-Enemy | tactical_ranged]'),
                    ('Building Lockdown', 4, 'Security systems being hacked'),
                    ('Extraction Window', 4, 'Opportunity to escape closing')
                ]
            },
            {
                'theme': 'Siege Breakout',
                'location': 'Surrounded Safe House (Arcadia)',
                'situation': 'You\'re pinned down in a safe house. Pantheon Security has the building surrounded with riot teams, drones, and heavy weapons. They\'re demanding surrender, but you know too much to be taken alive. [SPAWN_ENEMY: Siege Perimeter | grunt | 3 | Far-Enemy | defensive_ranged]',
                'void_level': 3,
                'clocks': [
                    ('Breach Attempt', 3, 'Security forces preparing assault', 'ADVANCE=Preparing to storm the building', 'REGRESS=Fortifying defenses', 'FILLED=Breach team storms in! [SPAWN_ENEMY: Breach Squad | elite | 2 | Near-Enemy | aggressive_melee]'),
                    ('Supply Depletion', 4, 'Running out of ammo and medical supplies'),
                    ('Negotiation Window', 4, 'Opportunity for peaceful resolution fading')
                ]
            },
            {
                'theme': 'Combat Rescue',
                'location': 'Crashed Transport Ship (Nimbus Wastes)',
                'situation': 'A transport went down in hostile territory. Survivors are pinned in the wreckage by scavenger gangs and void-touched wildlife. You need to extract them under fire. [SPAWN_ENEMY: Scavenger Scouts | grunt | 3 | Far-Enemy | defensive_ranged]',
                'void_level': 6,
                'clocks': [
                    ('Scavenger Reinforcements', 3, 'Main gang arriving', 'ADVANCE=More scavengers coming', 'REGRESS=Driving scavengers away', 'FILLED=Full gang attacks! [SPAWN_ENEMY: Scavenger Gang | grunt | 4 | Near-Enemy | aggressive_melee]'),
                    ('Void Creatures', 4, 'Corrupted wildlife drawn to the crash'),
                    ('Survivor Casualties', 5, 'Wounded dying without immediate help')
                ]
            },
            {
                'theme': 'Turf War',
                'location': 'Black Market District (Floating Exchange)',
                'situation': 'Two rival gangs are going to war over Hollow Seed territory, and you\'re in the kill zone. Automatic weapons fire tears through the market stalls as both sides fight for control. [SPAWN_ENEMY: Red Coil Gang | grunt | 2 | Near-Enemy | aggressive_melee] [SPAWN_ENEMY: Void Saints | grunt | 2 | Far-Enemy | tactical_ranged]',
                'void_level': 4,
                'clocks': [
                    ('Gang Escalation', 3, 'Both sides calling reinforcements', 'ADVANCE=More gang members arriving', 'REGRESS=Dispersing the gangs', 'FILLED=Full gang war erupts! [SPAWN_ENEMY: Gang Reinforcements | grunt | 4 | Engaged | aggressive_melee]'),
                    ('Civilian Casualties', 4, 'Bystanders caught in crossfire'),
                    ('Pantheon Response', 4, 'Security forces mobilizing')
                ]
            },
            {
                'theme': 'Facility Assault',
                'location': 'Tempest Research Station (Orbital)',
                'situation': 'You\'re leading an assault on a Tempest black site. Automated defenses are active - combat drones, turrets, and security systems. Eye of Breach may be controlling the facility. [SPAWN_ENEMY: Security Drones | grunt | 3 | Far-Enemy | extreme_range]',
                'void_level': 8,
                'clocks': [
                    ('Defense Systems', 4, 'Automated weapons engaging'),
                    ('Eye of Breach Activation', 3, 'Rogue AI taking direct control', 'ADVANCE=AI systems coming online', 'REGRESS=Disrupting AI control', 'FILLED=Eye of Breach fully awakens! [SPAWN_ENEMY: AI Combat Units | elite | 2 | Extreme-Enemy | tactical_ranged]'),
                    ('Mission Objective', 5, 'Reaching critical data before destruction')
                ]
            },
            {
                'theme': 'Ideological Battle',
                'location': 'Ley Node Nexus (Aeonisk Prime)',
                'situation': 'Tempest Industries forces are attempting to install unauthorized void-tech at a Sovereign Nexus ley node. Nexus enforcers and Pantheon Security have engaged them in a firefight. Both sides believe their cause justifies violence - void freedom vs spiritual order. [SPAWN_ENEMY: Tempest Operatives | grunt | 2 | Far-Enemy | tactical_ranged] [SPAWN_ENEMY: Nexus Enforcers | grunt | 2 | Near-Enemy | defensive_ranged]',
                'void_level': 5,
                'clocks': [
                    ('Tempest Installation', 4, 'Void-tech being deployed', 'ADVANCE=Void-tech systems activating', 'REGRESS=Disrupting installation', 'FILLED=Void-tech goes live! [SPAWN_ENEMY: Void-Enhanced Troops | elite | 2 | Near-Enemy | adaptive]'),
                    ('Nexus Purge', 4, 'Cleansing the site by force'),
                    ('Civilian Casualties', 4, 'Bystanders caught in ideological war')
                ]
            }
        ]

        # Select combat template (use specified index if provided, otherwise random)
        scenario_index = config.get('combat_scenario_index')
        if scenario_index is not None and 0 <= scenario_index < len(templates):
            template = templates[scenario_index]
            logger.info(f"Using specified combat scenario index {scenario_index}: {template['theme']}")
        else:
            template = random.choice(templates)
            logger.info(f"Using random combat scenario: {template['theme']}")

        return {
            'theme': template['theme'],
            'location': template['location'],
            'situation': template['situation'],
            'void_level': template['void_level'],
            'clocks': template['clocks']
        }

    def _detect_faction_conflicts(self, scenario: Scenario, players_config: List[Dict]) -> List[Dict[str, str]]:
        """
        Detect if the scenario conflicts with any player's faction or goals.

        Returns list of conflicts: [{'character': name, 'conflict': description, 'severity': low/medium/high}]
        """
        conflicts = []

        if not players_config:
            return conflicts

        situation_lower = scenario.situation.lower()
        location_lower = scenario.location.lower()

        # Faction ownership mappings
        faction_assets = {
            'sovereign nexus': ['codex cathedral', 'sanctified', 'ley network', 'gestation chamber', 'archive'],
            'pantheon': ['pantheon', 'security', 'law enforcement', 'civic', 'patrol'],
            'acg': ['astral commerce', 'debt', 'contract', 'commerce hub'],
            'arcgen': ['arcane genetics', 'biocreche', 'genetic', 'pod gestation'],
            'tempest': ['tempest industries', 'void energy', 'industrial', 'autonomous'],
        }

        # Check each player for conflicts
        for player in players_config:
            name = player.get('name', 'Unknown')
            faction = player.get('faction', '').lower()
            goals = [g.lower() for g in player.get('goals', [])]

            # Check if scenario involves stealing from/sabotaging own faction
            if faction in faction_assets:
                for asset in faction_assets[faction]:
                    # Check if targeting their faction's assets
                    if asset in location_lower or asset in situation_lower:
                        # Check if action is hostile (steal, infiltrate, sabotage)
                        hostile_keywords = ['steal', 'infiltrate', 'sabotage', 'extract', 'hack', 'break into', 'unauthorized']
                        if any(keyword in situation_lower for keyword in hostile_keywords):
                            conflicts.append({
                                'character': name,
                                'conflict': f"{name} ({faction}) is being asked to act against {faction} assets",
                                'severity': 'high',
                                'type': 'faction_betrayal'
                            })

            # Check if goals are contradicted
            goal_conflicts = []
            for goal in goals:
                # Example: goal is "prevent unauthorized void exposure" but scenario is "use void energy"
                if 'prevent' in goal and any(keyword in situation_lower for keyword in goal.split() if len(keyword) > 4):
                    goal_conflicts.append(goal)

            if goal_conflicts:
                conflicts.append({
                    'character': name,
                    'conflict': f"{name}'s goals ({', '.join(goal_conflicts)}) may conflict with this mission",
                    'severity': 'medium',
                    'type': 'goal_conflict'
                })

        return conflicts

    def _select_contextual_vendor(self, scenario_theme: str) -> Optional[Vendor]:
        """
        Select vendor based on scenario context.

        Safe zones (social, market, downtime) → Human traders (70% chance)
        Neutral zones (investigation, heist, exploration) → Vending machines/drones (60% chance)
        Hot zones (combat, crisis, void outbreak) → Emergency caches only (20% chance) or None
        """
        theme_lower = scenario_theme.lower()

        # Classify scenario zone
        safe_keywords = ['market', 'social', 'gathering', 'festival', 'ceremony', 'negotiation', 'diplomatic', 'downtime']
        neutral_keywords = ['investigation', 'heist', 'exploration', 'mystery', 'infiltration', 'search', 'transit', 'travel']
        hot_keywords = ['combat', 'battle', 'firefight', 'ambush', 'assault', 'crisis', 'outbreak', 'emergency', 'escape', 'chase']

        zone = 'neutral'  # Default
        if any(keyword in theme_lower for keyword in safe_keywords):
            zone = 'safe'
        elif any(keyword in theme_lower for keyword in hot_keywords):
            zone = 'hot'
        elif any(keyword in theme_lower for keyword in neutral_keywords):
            zone = 'neutral'

        # Filter vendors by appropriate type
        eligible_vendors = []

        if zone == 'safe':
            # Human traders + vending machines
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type in [VendorType.HUMAN_TRADER, VendorType.VENDING_MACHINE]]
            spawn_chance = 0.7  # 70% chance (increased for more economic gameplay)
        elif zone == 'neutral':
            # Vending machines + supply drones (no human traders in active zones)
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type in [VendorType.VENDING_MACHINE, VendorType.SUPPLY_DRONE]]
            spawn_chance = 0.6  # 60% chance (increased for more economic gameplay)
        elif zone == 'hot':
            # Emergency caches only (rare)
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type == VendorType.EMERGENCY_CACHE]
            spawn_chance = 0.2  # 20% chance (increased for more economic gameplay)

        # Roll for vendor appearance
        if eligible_vendors and random.random() < spawn_chance:
            return random.choice(eligible_vendors)

        return None

    def _generate_opening_narration(self, scenario: Scenario, faction_conflicts: List[Dict] = None) -> str:
        """Generate opening narration for scenario."""
        narration = f"""
The party finds themselves at {scenario.location}. {scenario.situation}.
The air carries a distinct tension, and you sense the void's influence at level {scenario.void_level}/10."""

        # Add faction conflict warnings
        if faction_conflicts:
            high_conflicts = [c for c in faction_conflicts if c['severity'] == 'high']
            if high_conflicts:
                narration += "\n\n⚠️  ETHICAL CONCERN:"
                for conflict in high_conflicts:
                    narration += f"\n   {conflict['conflict']}"
                narration += "\n   Proceeding may damage your spiritual standing."

        # Add vendor-gate requirement if present
        if scenario.required_purchase and scenario.vendor_gate_description:
            narration += f"\n\n🔒 CRITICAL REQUIREMENT:"
            narration += f"\n   {scenario.vendor_gate_description}"
            narration += f"\n   Required item: **{scenario.required_purchase}**"

        # Add vendor description if present
        if scenario.active_vendor:
            if scenario.required_purchase:
                narration += f"\n\nFortunately, {scenario.active_vendor.name} is nearby - a {scenario.active_vendor.faction} {scenario.active_vendor.vendor_type.value}. They may have what you need."
            else:
                narration += f"\n\nNearby, you notice {scenario.active_vendor.name}, a {scenario.active_vendor.faction} trader. They seem to have goods for sale or barter."

        narration += "\n\nWhat do you do?"
        return narration.strip()
        
    async def _handle_action_declared(self, message: Message):
        """Handle player action declarations - respond as DM."""
        payload = message.payload
        player_id = message.sender

        # Check what phase we're in
        phase = payload.get('phase')

        if phase == 'adjudication':
            # Adjudication phase - DM processes all actions together
            await self._handle_adjudication(payload)
            return

        elif phase == 'resolution_only':
            # Resolve mechanically but don't synthesize (synthesis comes later)
            await self._handle_resolution_only(payload)
            return

        elif phase == 'synthesis':
            # Generate synthesis from all collected resolutions
            await self._handle_synthesis(payload)
            return

        elif phase == 'resolution':
            # Old resolution phase (kept for compatibility)
            action = payload.get('action', payload)
            if self.human_controlled:
                await self._handle_human_dm_response(player_id, action)
            else:
                await self._handle_ai_dm_response(player_id, action)
            return

        else:
            # Declaration phase - acknowledge but don't resolve
            print(f"[DM {self.agent_id}] Noted: {player_id} declared action")
            return
            
    async def _handle_resolution_only(self, payload: Dict[str, Any]):
        """Resolve action mechanically without synthesis."""
        # Use adjudication but skip synthesis
        payload['skip_synthesis'] = True
        await self._handle_adjudication(payload)

    async def _handle_synthesis(self, payload: Dict[str, Any]):
        """Generate synthesis from all collected resolutions."""
        resolutions = payload.get('resolutions', [])
        round_num = payload.get('round', 0)

        if not resolutions:
            return

        # Generate synthesis
        synthesis = await self._synthesize_round_outcome(resolutions, round_num)
        print(f"\n[DM {self.agent_id}] ===== Round Synthesis =====")
        print(synthesis)
        print("=" * 40)

        # Broadcast the round synthesis to all players
        self.send_message_sync(
            MessageType.DM_NARRATION,
            None,  # Broadcast
            {
                'narration': synthesis,
                'is_round_synthesis': True,
                'round': round_num
            }
        )

    async def _handle_adjudication(self, payload: Dict[str, Any]):
        """
        Adjudicate all declared actions together.
        This is where the DM sees all intentions and decides what actually happens.
        """
        actions = payload.get('actions', [])
        round_num = payload.get('round', 0)
        action_index = payload.get('action_index', 0)  # Track which action this is for multi-action turns
        skip_synthesis = payload.get('skip_synthesis', False)  # Skip synthesis if set

        if not actions:
            # No actions to adjudicate - signal completion
            self.send_message_sync(
                MessageType.ACTION_RESOLVED,
                None,
                {'agent_id': 'adjudication'}
            )
            return

        print(f"\n[DM {self.agent_id}] ===== Adjudicating {len(actions)} actions =====")

        # Log adjudication start
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_adjudication_start(round_num, len(actions))

        # Process each action mechanically (fastest → slowest, same as actions list)
        resolutions = []
        mechanics = self.shared_state.mechanics_engine if self.shared_state else None

        for action_entry in actions:
            player_id = action_entry['player_id']
            character_name = action_entry['character_name']
            initiative = action_entry['initiative']
            action = action_entry['action']

            print(f"\n[{character_name}] (initiative {initiative})")

            # Resolve action mechanically
            resolution = await self._resolve_action_mechanically(player_id, action)

            # Print the resolution
            print(f"\n{resolution['narration']}")
            print("=" * 40)

            # Log the resolution
            if mechanics and mechanics.jsonl_logger:
                # Extract resolution data for logging
                action_resolution = resolution.get('resolution')
                state_changes = resolution.get('state_changes', {})
                clock_deltas = resolution.get('clock_deltas', [])
                combat_data = resolution.get('combat_data', {})

                if action_resolution:
                    # Build economy changes dict with void and soulcredit deltas
                    economy_changes = {
                        'void_delta': state_changes.get('void_change', 0),
                        'void_triggers': state_changes.get('void_reasons', []),
                        'soulcredit_delta': state_changes.get('soulcredit_change', 0),
                        'soulcredit_reasons': state_changes.get('soulcredit_reasons', [])
                    }

                    # Build clock states from current clock positions
                    clock_states = {}
                    for clock_name, clock in mechanics.scene_clocks.items():
                        clock_states[clock_name] = f"{clock.current}/{clock.maximum}"

                    # Extract effects from narration and state changes
                    effects = []
                    if state_changes.get('conditions'):
                        for cond in state_changes['conditions']:
                            effects.append(f"{cond['type']}: {cond['description']}")

                    # Build context with ritual and combat info
                    is_ritual_action = action.get('is_ritual', False) or action.get('action_type') == 'ritual'
                    context = {
                        "action_type": action.get('action_type', 'unknown'),
                        "is_ritual": is_ritual_action,
                        "faction": action.get('faction', 'Unknown'),
                        "description": action.get('description', ''),
                        "narration": resolution.get('narration', ''),
                        "is_free_action": action.get('is_free_action', False),
                        "initiative": initiative,
                        "clock_deltas": clock_deltas  # Include clock before/after/reason
                    }

                    # Add ritual context if this was a ritual
                    if is_ritual_action:
                        context['ritual'] = True
                        # Extract ritual details from action
                        context['altar'] = action.get('has_altar', False)
                        context['offering'] = action.get('has_offering', False)
                        context['echo_calibrator'] = action.get('has_echo_calibrator', False)

                    # Add combat triplet if present
                    if combat_data:
                        context['combat'] = combat_data

                    mechanics.jsonl_logger.log_action_resolution(
                        round_num=round_num,
                        phase="adjudicate",
                        agent_name=character_name,
                        action=action.get('intent', action.get('description', 'unknown')),
                        resolution=action_resolution,
                        economy_changes=economy_changes,
                        clock_states=clock_states,
                        effects=effects,
                        context=context
                    )

            resolutions.append({
                'player_id': player_id,
                'character_name': character_name,
                'initiative': initiative,
                'action': action,
                'resolution': resolution
            })

        # Send individual resolutions to each player
        for res in resolutions:
            # Prepare serializable resolution data (exclude non-serializable ActionResolution object)
            serializable_res = {
                'player_id': res['player_id'],
                'character_name': res['character_name'],
                'initiative': res['initiative'],
                'action': res['action'],
                'resolution': res['resolution']['outcome']  # Use serialized outcome instead of raw resolution
            }

            self.send_message_sync(
                MessageType.ACTION_RESOLVED,
                None,  # Broadcast
                {
                    'agent_id': res['player_id'],
                    'action_index': action_index,  # Include action index for multi-action turns
                    'original_action': res['action'],
                    'outcome': res['resolution']['outcome'],
                    'narration': res['resolution']['narration'],
                    'resolution_data': serializable_res  # Include serializable resolution for later synthesis
                }
            )

        # Only do synthesis if not skipping (for sequential resolution, synthesis comes later)
        if not skip_synthesis:
            # Generate synthesis of what happened
            synthesis = await self._synthesize_round_outcome(resolutions, round_num)
            print(f"\n[DM {self.agent_id}] ===== Round Synthesis =====")
            print(synthesis)
            print("=" * 40)

            # Parse synthesis for consequences (void gains, character deaths)
            # Note: Clock spawning and pivot handling is done in session.py when synthesis is distributed
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine

                # Check for void corruption mentioned in synthesis
                from .outcome_parser import parse_void_triggers
                void_change, void_reasons = parse_void_triggers(synthesis, "", "moderate")

                if void_change > 0:
                    # Apply void to ALL characters (consequence of filled clock)
                    print(f"\n⚠️  Synthesis indicates +{void_change} void corruption to all characters!")
                    for agent_id in mechanics.void_states.keys():
                        mechanics.void_states[agent_id].add_void(
                            void_change,
                            f"Clock consequence: {', '.join(void_reasons)}",
                            action_id=f"synthesis_{round_num}"
                        )
                        new_void = mechanics.void_states[agent_id].score
                        print(f"  {agent_id}: Now at {new_void}/10 void")

                        # Check for dissolution
                        if new_void >= 10:
                            print(f"\n💀 {agent_id} HAS REACHED VOID 10 - DISSOLUTION")
                            # Character is lost

                # Log synthesis
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_synthesis(round_num, synthesis)

            # Broadcast the round synthesis to all players
            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,  # Broadcast
                {
                    'narration': synthesis,
                    'is_round_synthesis': True,
                    'round': round_num
                }
            )

        # Signal that adjudication is complete
        self.send_message_sync(
            MessageType.ACTION_RESOLVED,
            None,
            {'agent_id': 'adjudication'}
        )

        print(f"\n[DM {self.agent_id}] ===== Adjudication Complete =====\n")

    async def _synthesize_round_outcome(self, resolutions: List[Dict[str, Any]], round_num: int) -> str:
        """
        Synthesize all resolutions into a cohesive narrative about what happened.
        This is where conflicts are detected and described.
        """
        if not resolutions:
            return "The moment passes without incident."

        # Build context about what happened
        outcomes_summary = []
        for res in resolutions:
            char_name = res['character_name']
            # Handle both old format (full dict) and new format (serializable dict)
            if 'resolution' in res and isinstance(res['resolution'], dict):
                if 'resolution' in res['resolution']:
                    # New serializable format: res['resolution'] is outcome dict
                    resolution_data = res['resolution']['resolution']
                    success = resolution_data.get('success', True) if isinstance(resolution_data, dict) else resolution_data.success
                else:
                    # Old format: res['resolution'] has direct 'outcome' field
                    success = res['resolution'].get('success', True)
            else:
                success = True

            intent = res['action'].get('intent', res['action'].get('description', 'unknown action'))

            status = "succeeded" if success else "failed"
            outcomes_summary.append(f"- {char_name} {status} at: {intent}")

        outcomes_text = "\n".join(outcomes_summary)

        # Get current clock state and check for filled clocks
        clock_state_text = ""
        filled_clocks_text = ""
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.scene_clocks:
                clock_lines = []
                critical_overflow = []
                for name, clock in mechanics.scene_clocks.items():
                    if clock.filled:
                        overflow = clock.current - clock.maximum
                        if overflow > 0:
                            if overflow >= 3:
                                status = f"🚨 CRITICAL OVERFLOW: {clock.current}/{clock.maximum} (+{overflow})"
                                critical_overflow.append(name)
                            else:
                                status = f"⚠️  OVERFLOWING: {clock.current}/{clock.maximum} (+{overflow})"
                        else:
                            status = f"FILLED: {clock.current}/{clock.maximum}"
                    else:
                        status = f"{clock.current}/{clock.maximum}"

                    # Add semantic guidance if available
                    clock_info = f"  - {name}: {status}"
                    if clock.advance_means or clock.regress_means or clock.filled_consequence:
                        clock_info += "\n    "
                        if clock.advance_means:
                            clock_info += f"Advance = {clock.advance_means}"
                        if clock.regress_means:
                            clock_info += f" | Regress = {clock.regress_means}"
                        if clock.filled_consequence and clock.filled:
                            clock_info += f"\n    🎯 When filled: {clock.filled_consequence}"

                    clock_lines.append(clock_info)
                if clock_lines:
                    clock_state_text = "\n\n**Current Clock State:**\n" + "\n".join(clock_lines)

                # Check for newly filled clocks
                filled_clocks = mechanics.get_and_clear_filled_clocks()
                if filled_clocks:
                    filled_names = [f['clock_name'] for f in filled_clocks]
                    if critical_overflow:
                        urgency = "🚨 EXTREME URGENCY 🚨"
                    else:
                        urgency = "⚠️  URGENT"
                    filled_clocks_text = f"\n\n{urgency} **CLOCKS FILLED/ADVANCING:** {', '.join(filled_names)}\n"
                    filled_clocks_text += "You MUST describe what catastrophic/dramatic consequences occur!\n"
                    filled_clocks_text += "Consider using DM control markers:\n"
                    filled_clocks_text += "- [NEW_CLOCK: Name | Max | Description] to spawn new pressure\n"
                    filled_clocks_text += "- [PIVOT_SCENARIO: Theme] if situation fundamentally changes (same location)\n"
                    filled_clocks_text += "- [ADVANCE_STORY: Location | Situation] if objective completed, advance to new scene\n"
                    filled_clocks_text += "  Example: [ADVANCE_STORY: Transit Hub | Escaped! A wounded courier offers you intel]\n"
                    filled_clocks_text += "- [SESSION_END: VICTORY/DEFEAT/DRAW] if mission fully complete or total failure"

        # Build enemy spawn instructions (always available if enabled)
        enemy_spawn_prompt = ""
        has_filled_clocks = False
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.scene_clocks:
                filled_clocks = mechanics.get_and_clear_filled_clocks()
                has_filled_clocks = bool(filled_clocks)

        if self.config.get('enemy_agents_enabled', False):
            enemy_spawn_prompt = """

**SPAWN ENEMIES (OPTIONAL):**
You can spawn autonomous enemies whenever the narrative warrants it:

Syntax: [SPAWN_ENEMY: name | template | count | position | tactics]
Example: [SPAWN_ENEMY: Void Gremlins | grunt | 3 | Near-Enemy | aggressive_melee]

Templates: grunt (15 HP), elite (25 HP), sniper (20 HP), boss (40 HP), enforcer (30 HP), ambusher (18 HP)
Positions: Engaged, Near-Enemy, Far-Enemy, Extreme-Enemy
Tactics: aggressive_melee, defensive_ranged, tactical_ranged, extreme_range, ambush, adaptive

Good times to spawn:
- Void corruption spreads → void creatures/entities emerge from reality tears
- Security systems activate → automated defenses, combat drones, turrets
- Reinforcements arrive → guards respond to alarms, gangs send backup
- Environmental hazards become threats → corrupted wildlife, possessed NPCs
- When combat would make the scene more dynamic and dangerous

Match threat level to situation: 2-4 grunts for patrols, 1-2 elites for specialists, 1 boss for commanders."""

        # Use LLM to generate synthesis if available
        if self.llm_config:
            prompt = f"""You are the DM for a dark sci-fi TTRPG. Multiple characters just acted simultaneously.

**What they tried to do:**
{outcomes_text}
{clock_state_text}
{filled_clocks_text}

**Your task:** Write a cohesive narrative (1-2 paragraphs) describing what happened when these actions played out together. Consider:
- Timing: Actions resolved fastest → slowest based on initiative
- Interactions: How did each person's success/failure affect the others?
- Conflicts: If multiple people tried similar things, who got there first? What did the slower person encounter?
- Cause and effect: How did earlier successes/failures change the situation for later actors?
- Overall outcome: What's the new situation now that the dust has settled?
- **IMPORTANT**: If objectives (clocks) are not advancing despite actions, acknowledge this! Characters should feel the pressure of marginal success or outright failure.

Be vivid and cinematic. Show how these actions interacted and created a dynamic scene. Describe the final state of the situation after all actions resolved.

If the team is failing their objectives (clocks not advancing or bad clocks filling), your narration should reflect the growing desperation, consequences, and danger.

**CRITICAL**: If any clocks just filled, you MUST describe the dramatic consequences. This could include:
- Character injury or void corruption (specify who and how much void: "+2 void")
- Character death/dissolution if appropriate
- Mission failure or catastrophic events
- Environmental changes or new threats
- Success and rewards if it's a positive clock

Generate appropriate consequences based on what makes sense for that specific clock in this scenario.

{enemy_spawn_prompt}"""

            try:
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=self.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                    max_tokens=500,
                    temperature=0.8,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text.strip()
            except Exception as e:
                logger.error(f"Synthesis generation failed: {e}")
                return f"Round {round_num} completes with mixed results:\n{outcomes_text}"
        else:
            return f"Round {round_num} completes:\n{outcomes_text}"

    async def _resolve_action_mechanically(self, player_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a single action mechanically (rolls, difficulty, narration).
        Returns resolution data.
        """
        # This is essentially the same as _handle_ai_dm_response but returns data instead of sending messages
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        intent = action.get('intent', description)

        resolution = None
        narration = ""

        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()

            # Extract mechanical details
            attribute = action.get('attribute', 'Perception')
            skill = action.get('skill')
            attribute_value = action.get('attribute_value', 3)
            skill_value = action.get('skill_value', 0)

            # Check for coordination bonus
            coordination_bonus = 0
            coordination_from = None
            if self.shared_state:
                bonus_info = self.shared_state.consume_coordination_bonus(player_id)
                if bonus_info:
                    coordination_bonus = bonus_info['bonus']
                    coordination_from = bonus_info['from']
                    print(f"💡 {action.get('character', 'Character')} receives +{coordination_bonus} coordination bonus from {coordination_from}!")

            # Calculate DC
            is_ritual_action = action_type == 'ritual' or action.get('is_ritual', False)
            is_inter_party = action.get('is_free_action', False)  # Free actions are inter-party
            difficulty = mechanics.calculate_dc(
                intent=intent,
                action_type=action_type,
                is_ritual=is_ritual_action,
                is_extreme=action.get('is_extreme', False),
                is_multi_stage=action.get('is_multi_stage', False),
                is_inter_party=is_inter_party
            )

            # Perform resolution (apply coordination bonus via modifiers)
            modifiers = {}
            if coordination_bonus > 0:
                modifiers['coordination'] = coordination_bonus

            resolution = mechanics.resolve_action(
                intent=intent,
                attribute=attribute,
                skill=skill,
                attribute_value=attribute_value,
                skill_value=skill_value,
                difficulty=difficulty,
                agent_id=player_id,
                modifiers=modifiers if modifiers else None
            )

            # Format mechanical resolution
            mechanical_text = mechanics.format_resolution_for_narration(resolution)

            # Generate narrative description using LLM
            if self.llm_config:
                llm_narration = await self._generate_llm_response(
                    player_id, action_type, description, resolution, action
                )
                narration = f"{mechanical_text}\n\n{llm_narration}"
            else:
                narration = f"{mechanical_text}\n\n{resolution.narrative}"

            # Parse narration for clock triggers and state changes
            from .outcome_parser import (
                parse_state_changes,
                parse_combat_triplet,
                parse_mechanical_effect,
                generate_fallback_effect,
                generate_fallback_buff
            )

            # Get active clocks for dynamic clock progression
            active_clocks = mechanics.scene_clocks if mechanics else {}

            state_changes = parse_state_changes(llm_narration if self.llm_config else resolution.narrative, action, resolution.__dict__, active_clocks)

            # Parse combat triplet (for backwards compatibility)
            combat_data = parse_combat_triplet(llm_narration if self.llm_config else resolution.narrative)

            # Parse mechanical effects if action targets enemy
            effect = None
            if action.get('target_enemy'):
                # Try to parse explicit mechanical effect block
                effect = parse_mechanical_effect(llm_narration if self.llm_config else resolution.narrative)

                # If no effect found, use legacy combat triplet
                if not effect and combat_data and combat_data.get('post_soak_damage', 0) > 0:
                    effect = {
                        'type': 'damage',
                        'target': action.get('target_enemy'),
                        'final': combat_data['post_soak_damage'],
                        'source': 'combat_triplet'
                    }

                # If still no effect, generate fallback
                if not effect and resolution and resolution.success:
                    effect = generate_fallback_effect(action, resolution.__dict__ if hasattr(resolution, '__dict__') else resolution)
                    if effect:
                        logger.info(f"Generated fallback effect: {effect.get('type')} for {effect.get('target')}")

            # Apply effect to enemy if we have one
            if effect and self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
                enemy_combat = self.shared_state.enemy_combat
                if enemy_combat:
                    from .enemy_spawner import get_active_enemies
                    active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                    # Find target enemy (fuzzy match)
                    target_enemy_name = effect.get('target', action.get('target_enemy'))
                    target_enemy = None
                    for enemy in active_enemies:
                        if target_enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in target_enemy_name.lower():
                            target_enemy = enemy
                            break

                    if target_enemy:
                        effect_type = effect.get('type', 'unknown')

                        if effect_type == 'damage':
                            # Apply damage
                            damage_dealt = effect.get('final', 0)
                            old_health = target_enemy.health
                            wounds_dealt = damage_dealt // 5  # YAGS: every 5 damage = 1 wound
                            target_enemy.wounds += wounds_dealt
                            target_enemy.health -= damage_dealt

                            logger.info(f"Player dealt {damage_dealt} damage to {target_enemy.name} ({old_health} → {target_enemy.health} HP, +{wounds_dealt} wounds)")

                            # Add effect notification
                            source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                            narration += f"\n\n⚔️  **{target_enemy.name} takes {damage_dealt} damage!** {source_label}"

                            # Check if enemy died
                            if target_enemy.health <= 0:
                                if hasattr(target_enemy, 'check_death_save'):
                                    alive, status = target_enemy.check_death_save()
                                    if not alive:
                                        logger.info(f"{target_enemy.name} KILLED by player attack!")
                                        narration += f"\n💀 **{target_enemy.name} is KILLED!**"
                                    elif status == "unconscious":
                                        logger.info(f"{target_enemy.name} knocked unconscious!")
                                        narration += f"\n😵 **{target_enemy.name} is knocked unconscious!**"
                                    else:
                                        logger.info(f"{target_enemy.name} critically wounded but conscious!")
                                        narration += f"\n⚠️  **{target_enemy.name} is critically wounded!**"
                                else:
                                    logger.info(f"{target_enemy.name} defeated!")
                                    narration += f"\n💀 **{target_enemy.name} is defeated!**"

                        elif effect_type == 'debuff':
                            # Apply debuff
                            penalty = effect.get('penalty', -2)
                            duration = effect.get('duration', 3)
                            effect_desc = effect.get('effect', f"{penalty} to rolls")
                            source = effect.get('source', 'player')

                            target_enemy.add_debuff(effect_desc, penalty, duration, source)

                            source_label = "(fallback)" if source == 'fallback' else ""
                            narration += f"\n\n🔻 **{target_enemy.name} debuffed: {effect_desc}** (lasts {duration} rounds) {source_label}"

                        elif effect_type == 'status':
                            # Apply status effect
                            status_effect = effect.get('effect', 'affected')
                            duration = effect.get('duration', 1)

                            target_enemy.add_status_effect(status_effect, duration)

                            source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                            narration += f"\n\n💫 **{target_enemy.name} status: {status_effect}** {source_label}"

                        elif effect_type == 'movement':
                            # Apply forced movement
                            movement_desc = effect.get('effect', 'forced to move')
                            new_position = effect.get('new_position')

                            if new_position and hasattr(target_enemy, 'position'):
                                from .enemy_agent import Position
                                try:
                                    target_enemy.position = Position.from_string(new_position)
                                    narration += f"\n\n🚶 **{target_enemy.name} forced to {new_position}!**"
                                except:
                                    narration += f"\n\n🚶 **{target_enemy.name} disrupted: {movement_desc}!**"
                            else:
                                narration += f"\n\n🚶 **{target_enemy.name} disrupted: {movement_desc}!**"

                        elif effect_type == 'reveal':
                            # Add revealed weakness
                            weakness_desc = effect.get('effect', 'weakness revealed')
                            bonus = effect.get('bonus', 2)

                            target_enemy.add_revealed_weakness(weakness_desc, bonus)

                            narration += f"\n\n🔍 **{target_enemy.name} weakness revealed: {weakness_desc}** (+{bonus} for allies)"

                        else:
                            logger.warning(f"Unknown effect type: {effect_type}")

                    else:
                        logger.warning(f"Could not find enemy '{target_enemy_name}' to apply effect")

            # Parse and apply ally buffs if action targets ally
            buff = None
            if action.get('target_ally'):
                # Try to parse explicit buff effect block (similar to enemy effects)
                # For now, we'll use fallback generation since DM doesn't explicitly write buff blocks yet

                # Generate fallback buff if successful action
                if resolution and resolution.success:
                    buff = generate_fallback_buff(action, resolution.__dict__ if hasattr(resolution, '__dict__') else resolution)
                    if buff:
                        logger.info(f"Generated fallback buff: {buff.get('type')} for {buff.get('target')}")

            # Apply buff to ally if we have one
            if buff and self.shared_state:
                # Find target ally player agent (fuzzy match by character name)
                target_ally_name = buff.get('target', action.get('target_ally'))
                target_ally_agent = None

                # Get all player agents from shared_state
                player_agents = self.shared_state.player_agents

                for agent in player_agents:
                    if hasattr(agent, 'character_state') and agent.character_state:
                        agent_name = agent.character_state.name
                        # Fuzzy match: check if names contain each other
                        if target_ally_name.lower() in agent_name.lower() or agent_name.lower() in target_ally_name.lower():
                            target_ally_agent = agent
                            break

                if target_ally_agent:
                    buff_type = buff.get('type', 'unknown')

                    if buff_type == 'heal':
                        # Apply healing
                        healing_amount = buff.get('amount', 0)
                        old_health = target_ally_agent.health
                        target_ally_agent.health = min(target_ally_agent.max_health, target_ally_agent.health + healing_amount)
                        actual_healing = target_ally_agent.health - old_health

                        logger.info(f"Player healed {target_ally_agent.character_state.name} for {actual_healing} HP ({old_health} → {target_ally_agent.health})")

                        # Add buff notification
                        source_label = "(fallback)" if buff.get('source') == 'fallback' else ""
                        narration += f"\n\n💚 **{target_ally_agent.character_state.name} healed for {actual_healing} HP!** {source_label}"

                    elif buff_type == 'buff':
                        # Apply positive buff
                        bonus = buff.get('bonus', 1)
                        duration = buff.get('duration', 2)
                        effect_desc = buff.get('effect', f"+{bonus} to rolls")
                        source = action.get('character', 'ally')

                        target_ally_agent.add_buff(effect_desc, bonus, duration, source)

                        source_label = "(fallback)" if buff.get('source') == 'fallback' else ""
                        narration += f"\n\n🔺 **{target_ally_agent.character_state.name} buffed: {effect_desc}** (lasts {duration} rounds) {source_label}"

                    else:
                        logger.warning(f"Unknown buff type: {buff_type}")

                else:
                    logger.warning(f"Could not find ally '{target_ally_name}' to apply buff")

            # Apply clock advancements
            clock_final_states = {}  # Track final state of each clock for display
            clock_deltas = []  # Track before/after for logging
            for clock_name, ticks, reason in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    clock = mechanics.scene_clocks[clock_name]
                    before = clock.current
                    maximum = clock.maximum

                    if ticks < 0:
                        # Negative ticks = regress (improve)
                        clock.regress(abs(ticks))
                        after = clock.current
                        # Store final state (will be overwritten if multiple triggers for same clock)
                        clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum} ↓"
                        clock_deltas.append({
                            'name': clock_name,
                            'before': before,
                            'after': after,
                            'max': maximum,
                            'delta': ticks,
                            'reason': reason
                        })
                    else:
                        # Positive ticks = advance (degrade)
                        filled = mechanics.advance_clock(clock_name, ticks, reason)
                        after = clock.current
                        overflow = after - maximum
                        if overflow > 0:
                            clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum} ⚠️  (+{overflow} OVERFLOW)"
                        else:
                            clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum}"
                        if filled and overflow == 0:
                            # Add FILLED marker separately (always show even if clock updated multiple times)
                            clock_final_states[f"{clock_name}_FILLED"] = f"🚨 {clock_name} FILLED!"
                        clock_deltas.append({
                            'name': clock_name,
                            'before': before,
                            'after': after,
                            'max': maximum,
                            'delta': ticks,
                            'filled': filled,
                            'reason': reason
                        })

            # Build deduplicated clock updates (only final state of each clock)
            clock_updates = list(clock_final_states.values()) if clock_final_states else []
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

                # Check for Eye of Breach appearance on high void
                eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                if eye_of_breach_event:
                    narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            if state_changes.get('soulcredit_change', 0) != 0:
                sc_state = mechanics.get_soulcredit_state(player_id)
                reasons_text = ', '.join(state_changes.get('soulcredit_reasons', []))
                sc_state.adjust(state_changes['soulcredit_change'], reasons_text)
                # NOTE: SC changes are shown PRIVATELY to the affected player in their prompt
                # Other players do NOT see each other's soulcredit (asymmetric information)

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

            # Apply position changes (for tactical movement)
            if state_changes.get('position_change'):
                # Get player agent and update position
                player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                if player_agents:
                    player_agent = player_agents[0]
                    old_position = str(getattr(player_agent, 'position', 'Near-PC'))

                    # Parse and apply new position
                    from .enemy_agent import Position
                    try:
                        new_position_str = state_changes['position_change']
                        new_position = Position.from_string(new_position_str)
                        player_agent.position = new_position
                        logger.info(f"Updated {player_id} position: {old_position} → {new_position}")
                        # Position change is already in narration from DM, no need to add here
                    except Exception as e:
                        logger.error(f"Failed to update player position: {e}")

        return {
            'resolution': resolution,
            'narration': narration,
            'state_changes': state_changes,  # Include state_changes for logging
            'clock_updates': clock_updates,  # Include clock update strings
            'clock_deltas': clock_deltas,  # Include clock before/after/reason for logging
            'combat_data': combat_data,  # Include combat triplet if present
            'outcome': {
                'dm_response': narration,
                'success': resolution.success if resolution else True,
                'consequences': [],
                'resolution': {
                    'intent': resolution.intent,
                    'attribute': resolution.attribute,
                    'skill': resolution.skill,
                    'total': resolution.total,
                    'difficulty': resolution.difficulty,
                    'margin': resolution.margin,
                    'outcome_tier': resolution.outcome_tier.value if hasattr(resolution.outcome_tier, 'value') else str(resolution.outcome_tier),
                    'success': resolution.success
                } if resolution else {}
            }
        }

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
            None,  # Broadcast so all players see each other's results
            {
                'agent_id': player_id,  # Include player_id so session knows who completed
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

            # Calculate DC using mechanics engine (don't trust player estimate)
            is_ritual_action = action_type == 'ritual' or action.get('is_ritual', False)
            difficulty = mechanics.calculate_dc(
                intent=intent,
                action_type=action_type,
                is_ritual=is_ritual_action,
                is_extreme=action.get('is_extreme', False),
                is_multi_stage=action.get('is_multi_stage', False)
            )

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
                    agent_id=player_id,
                    faction=action.get('faction', None)
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
                player_id, action_type, description, resolution, action
            )

            narration = f"{mechanical_text}\n\n{llm_narration}{narration_suffix}"

            # Parse narration for automatic state changes
            from .outcome_parser import parse_state_changes

            # Get active clocks for dynamic clock progression
            active_clocks = mechanics.scene_clocks if mechanics else {}

            state_changes = parse_state_changes(llm_narration, action, resolution.__dict__, active_clocks)

            # Merge ritual soulcredit changes into state_changes
            if action.get('is_ritual', False) and 'ritual_effects' in locals():
                if 'soulcredit_change' not in state_changes:
                    state_changes['soulcredit_change'] = 0
                    state_changes['soulcredit_reasons'] = []

                state_changes['soulcredit_change'] += ritual_effects.get('soulcredit_change', 0)
                # Extract reasons from ritual consequences
                sc_reasons = [c for c in ritual_effects.get('consequences', []) if 'SC)' in c]
                state_changes['soulcredit_reasons'].extend(sc_reasons)

            # Apply clock advancements (positive=advance, negative=regress)
            clock_final_states = {}  # Track final state of each clock for display (deduplicated)
            for clock_name, ticks, reason in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    if ticks < 0:
                        # Negative ticks = regress (improve)
                        mechanics.scene_clocks[clock_name].regress(abs(ticks))
                        clock = mechanics.scene_clocks[clock_name]
                        # Store final state (will be overwritten if multiple triggers for same clock)
                        clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum} ↓"
                    else:
                        # Positive ticks = advance (degrade)
                        filled = mechanics.advance_clock(clock_name, ticks, reason)
                        clock = mechanics.scene_clocks[clock_name]
                        overflow = clock.current - clock.maximum
                        if overflow > 0:
                            clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum} ⚠️  (+{overflow} OVERFLOW)"
                        else:
                            clock_final_states[clock_name] = f"{clock_name}: {clock.current}/{clock.maximum}"
                        if filled and overflow == 0:
                            # Add FILLED marker separately (always show even if clock updated multiple times)
                            clock_final_states[f"{clock_name}_FILLED"] = f"🚨 {clock_name} FILLED!"

            # Build deduplicated clock updates (only final state of each clock)
            clock_updates = list(clock_final_states.values()) if clock_final_states else []
            if clock_updates:
                narration += "\n\n📊 " + " | ".join(clock_updates)

            # Extract and record party discoveries from successful actions
            if resolution.success and resolution.margin >= 5:
                # Extract key discovery from the narration (simple heuristic)
                # Look for sentences that suggest new information
                discovery_text = self._extract_discovery_from_narration(llm_narration, intent)
                if discovery_text:
                    character_name = action.get('character', 'Unknown')
                    self.shared_state.add_discovery(discovery_text, character_name)

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

                # Check for Eye of Breach appearance on high void
                eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                if eye_of_breach_event:
                    narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            if state_changes.get('soulcredit_change', 0) != 0:
                sc_state = mechanics.get_soulcredit_state(player_id)
                reasons_text = ', '.join(state_changes.get('soulcredit_reasons', []))
                sc_state.adjust(state_changes['soulcredit_change'], reasons_text)
                # NOTE: SC changes are shown PRIVATELY to the affected player in their prompt
                # Other players do NOT see each other's soulcredit (asymmetric information)

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

            # Apply position changes (for tactical movement during rituals)
            if state_changes.get('position_change'):
                # Get player agent and update position
                player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                if player_agents:
                    player_agent = player_agents[0]
                    old_position = str(getattr(player_agent, 'position', 'Near-PC'))

                    # Parse and apply new position
                    from .enemy_agent import Position
                    try:
                        new_position_str = state_changes['position_change']
                        new_position = Position.from_string(new_position_str)
                        player_agent.position = new_position
                        logger.info(f"Updated {player_id} position: {old_position} → {new_position}")
                        # Position change is already in narration from DM, no need to add here
                    except Exception as e:
                        logger.error(f"Failed to update player position: {e}")

            # Display notes from outcome parser (e.g., recovery move explanations)
            if state_changes.get('notes'):
                for note in state_changes['notes']:
                    narration += f"\n\n💡 {note}"

            # Check for filled clocks (triggers) and generate consequences
            clock_triggers = await self._check_clock_triggers(mechanics)
            if clock_triggers:
                narration += f"\n\n{clock_triggers}"

            # JSONL Logging: Log complete action resolution
            if mechanics.jsonl_logger:
                # Get character name from action payload
                character_name = action.get('character', player_id)

                # Build economy changes
                economy_changes = {
                    "void_delta": state_changes.get('void_change', 0),
                    "soulcredit_delta": state_changes.get('soulcredit_change', 0),
                    "offering_used": action.get('has_offering', False),
                    "bonds_applied": []  # TODO: track bond applications
                }

                # Build clock states
                clock_states = {
                    name: f"{clock.current}/{clock.maximum}"
                    for name, clock in mechanics.scene_clocks.items()
                }

                # Build effects list
                effects = state_changes.get('notes', []) + state_changes.get('consequences', [])

                # Log the action resolution with enriched data
                mechanics.jsonl_logger.log_action_resolution(
                    round_num=mechanics.current_round,
                    phase="resolve",
                    agent_name=character_name,
                    action=intent,
                    resolution=resolution,
                    economy_changes=economy_changes,
                    clock_states=clock_states,
                    effects=effects,
                    context={
                        "action_type": action_type,
                        "is_ritual": action.get('is_ritual', False),
                        "faction": action.get('faction', 'Unknown'),
                        "description": action.get('description', ''),
                        "narration": llm_narration,
                        "is_free_action": action.get('is_free_action', False)
                    }
                )

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
            None,  # Broadcast so all players see each other's results
            {
                'agent_id': player_id,  # Include player_id so session knows who completed
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
        """Handle AI DM turn - provide synthesis of the round."""
        # For now, just provide status
        # TODO: Full synthesis would require tracking all resolutions and generating narrative
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine

            # Build status summary
            status_parts = []

            # Show clock states
            for clock_name, clock in mechanics.scene_clocks.items():
                status_parts.append(f"{clock_name}: {clock.current}/{clock.maximum}")

            if status_parts:
                status_line = "📊 " + " | ".join(status_parts)

                # Simple narrative wrapper
                narration = f"The situation evolves...\n\n{status_line}"
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

            print(f"\n[DM {self.agent_id}] {narration}")
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

    async def _generate_llm_response(self, player_id: str, action_type: str, description: str, resolution=None, action=None) -> str:
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

        # NOTE: Enemy spawn markers should ONLY be in round synthesis, not individual action resolutions
        # This prevents duplicate spawning across multiple PC action resolutions
        enemy_spawn_instructions = ""

        # Add character context including faction
        character_context = ""
        if action:
            character_name = action.get('character', 'Unknown')
            faction = action.get('faction', 'Unaffiliated')
            character_context = f"""
Character: {character_name} ({faction})
Note: NPCs and other characters are aware of this affiliation. Consider how faction ties might create complications, opportunities, or conflicts.
"""

        resolution_context = ""
        if resolution:
            outcome_text = "succeeded" if resolution.success else "failed"
            resolution_context = f"""
Mechanical Result: The action {outcome_text} with margin {resolution.margin:+d} (outcome: {resolution.outcome_tier.value})
"""

        # Build success-specific guidance
        if resolution and resolution.success:
            outcome_guidance = """5. Provide a new clue, discovery, or piece of information that rewards their success"""
        else:
            outcome_guidance = """5. NO hints or clues - the failure means they MISS information. Instead provide:
   - Immediate complications (alerts triggered, time wasted, suspicion raised)
   - Setbacks (equipment damaged, resources lost, position compromised)
   - Consequences that make the situation harder (enemies alerted, doors locked, witnesses fled)

IMPORTANT: Failed investigation/sensing actions should result in MISSING the information entirely, not soft hints."""

        # Add void impact guidance based on environmental void level
        void_level = self.current_scenario.void_level if self.current_scenario else 3
        void_impact = ""
        if void_level >= 6:
            void_impact = "\n**HIGH VOID ENVIRONMENT (6+)**: Reality distortion, hallucinations, tech glitches, spiritual interference - these should significantly complicate actions."
        elif void_level >= 4:
            void_impact = "\n**MODERATE VOID (4-5)**: Subtle reality warping, minor tech interference, uneasy feelings - add atmospheric complications."
        elif void_level >= 2:
            void_impact = "\n**MILD VOID (2-3)**: Faint corruption traces, occasional static - minimal but noticeable environmental effects."

        # Add tactical combat context (only when enemies are active)
        tactical_combat_context = ""
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            if enemy_combat and enemy_combat.enabled and len(enemy_combat.enemy_agents) > 0:
                # Get active enemies
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                if active_enemies:
                    # Get player's current position
                    player_position = "Unknown"
                    if action:
                        # Try to get position from player agent
                        player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                        if player_agents:
                            player_position = getattr(player_agents[0], 'position', 'Near-PC')

                    # Build enemy positions summary
                    enemy_positions = []
                    for enemy in active_enemies:
                        enemy_positions.append(f"{enemy.name} at {enemy.position}")
                    enemy_positions_text = ", ".join(enemy_positions)

                    tactical_combat_context = f"""

**⚔️  TACTICAL COMBAT ACTIVE (Tactical Module v1.2.3):**

🎯 **CRITICAL REQUIREMENT - POSITION TAGS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  When narrating player movement, you MUST include [POSITION: ...] tag!

Format: [POSITION: PositionName]

✅ GOOD Examples (USE THESE):
  Player: "I charge forward [TARGET_POSITION: Engaged]"
  → You: "You sprint into melee range. [POSITION: Engaged]"

  Player: "I fall back [TARGET_POSITION: Far-PC]"
  → You: "You retreat behind cover. [POSITION: Far-PC]"

  Player: "I circle to flank [TARGET_POSITION: Near-Enemy]"
  → You: "You ghost around their flank. [POSITION: Near-Enemy]"

❌ BAD Examples (DON'T do this - position won't update):
  → "You sprint forward" ← Missing [POSITION: ...] tag!
  → "You move to better position" ← Missing tag!

Current Positions:
- Player at {player_position}
- Enemies: {enemy_positions_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Range Bands:
- Engaged: Center melee zone
- Near-PC / Near-Enemy: First ring (different hemispheres)
- Far-PC / Far-Enemy: Second ring
- Extreme-PC / Extreme-Enemy: Outermost ring

Range Penalty Rules (same ring/same side = Melee, 0 penalty):
- Melee (0): Same ring AND same hemisphere (e.g., both at Near-PC)
- Near (-2): Adjacent ring OR different hemisphere in Near
- Far (-4): 2+ rings away OR different hemisphere in Far
- Extreme (-6): Maximum distance

Available Actions:
- **Shift (Minor)**: Move 1 ring toward or away from center (stays on same side)
- **Shift 2 bands (Major)**: Skip a ring (e.g., Far-PC → Engaged)
- **Push Through (Major)**: Cross center line to opposite hemisphere (must pass through Engaged)
- **Charge (Major)**: Shift to Engaged + melee attack (+2 damage, -2 defense until next turn)
- **Attack**: Roll attack with range penalty based on distance to target
- **Claim Cover/High Ground (Minor)**: Attempt to claim tactical token
- **Disengage (Minor)**: Athletics DC 20 to shift without provoking Breakaway

**DAMAGE SYSTEM** - When players attack enemies:
If player ACTION includes TARGET_ENEMY field and succeeds at Combat check:
1. Roll weapon damage (typically 2d6+4 for rifles, 1d6+3 for pistols, 1d6+Str for melee)
2. Enemy soaks 12 damage (base Soak for human-sized targets)
3. Include damage triplet in your narration: `Damage: X → Soak: 12 → Final: Y`
   - Example: "Your shot hits center mass. Damage: 18 → Soak: 12 → Final: 6"
   - On miss or failure: Don't include triplet, just narrate the miss

**MOVEMENT SYSTEM** - Two types of movement:

1) **Basic Tactical Movement** (automatic, no roll):
   - Player declares [TARGET_POSITION: X] in their action
   - Movement ALWAYS succeeds (it's an automatic action, like enemies)
   - Simply narrate the movement and include: [POSITION: X]
   - Example: Player says "I move forward [TARGET_POSITION: Engaged]"
     → You narrate: "You advance to melee range. [POSITION: Engaged]"
   - NO ROLL NEEDED - just describe movement happening

2) **Skill-Based Movement** (roll for persistent benefit):
   - Player describes skill check + movement intent (e.g., "use Stealth to circle behind unseen")
   - Movement HAPPENS REGARDLESS of roll (they move to intended position)
   - Roll determines if they get PERSISTENT BENEFIT:
     * Exceptional/Good: Grant lasting condition/advantage
     * Marginal/Failure: Movement succeeds but no special benefit (or penalty)

   **Available Persistent Benefits:**
   - **Unseen** (Stealth): Enemies can't target you until you attack or fail Stealth
     Format: 🎭 Condition: Unseen (can't be targeted until you attack)
   - **High Ground** (Athletics): Token grants +2 ranged attacks while held
     Format: 🏔️ Token Claimed: High Ground (+2 ranged attacks)
   - **No Breakaway** (Athletics for disengaging): Avoid opportunity attack when leaving melee
   - **First Strike** (Stealth ambush): +2 damage on your next attack

   **Example Narrations:**
   - Stealth Success: "You ghost through shadows, positioning behind them completely undetected. [POSITION: Near-Enemy] 🎭 Condition: Unseen"
   - Athletics Success: "You sprint up debris to elevated ground. [POSITION: Far-PC] 🏔️ Token Claimed: High Ground (+2 ranged)"
   - Stealth Failure: "You circle behind them but a loose board creaks - they spin toward you! [POSITION: Near-Enemy]"

When adjudicating:
- Basic tactical movement → Just happens, narrate + [POSITION: X]
- Skill-based movement → Roll skill, grant benefit on success, position changes either way with [POSITION: X]
- Apply range modifiers to attacks based on positions"""

        # Add clock context
        clock_context = ""
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.scene_clocks:
                clock_lines = []
                for name, clock in mechanics.scene_clocks.items():
                    status = "FILLED!" if clock.filled else f"{clock.current}/{clock.maximum}"
                    clock_lines.append(f"  - {name}: {status}")
                if clock_lines:
                    clock_context = "\n\n**Active Clocks:**\n" + "\n".join(clock_lines)
                    clock_context += "\n\nAt the end of your narration, if this action should affect any clocks, add a line:\n📊 [Clock Name]: +X or -X (reason)"
                    clock_context += "\n\n**CRITICAL:** Soulcredit tracks trustworthiness/morality, NOT success."
                    clock_context += "\n**DEFAULT: +0 for 80-90% of actions. Only exceptional moral/immoral acts affect SC.**"
                    clock_context += "\n\nIf this action affects the character's Soulcredit (social trust/reputation), add a marker:\n⚖️ Soulcredit: +X (reason) or -X (reason)"
                    clock_context += "\n\nSC Scoring Rules:"
                    clock_context += "\n  • MOST actions: +0 (no marker) - negotiations, purchases, investigations, etc."
                    clock_context += "\n  • Deception/lying/fraud: ALWAYS negative, even if successful"
                    clock_context += "\n  • Using Guile skill: Usually -1 or -2 (misrepresentation/deception)"
                    clock_context += "\n  • Success ≠ positive SC, Failure ≠ negative SC"
                    clock_context += "\n  • Following normal protocols/procedures: +0 (not morally exceptional)"
                    clock_context += "\n  • Legitimate business dealings: +0 (normal behavior)"
                    clock_context += "\n\nExamples:"
                    clock_context += "\n  • Lying to authorities (Guile check): ⚖️ Soulcredit: -1 (deceived officials)"
                    clock_context += "\n  • Misrepresenting credentials: ⚖️ Soulcredit: -2 (fraudulent identity claim)"
                    clock_context += "\n  • Creating Hollow Seeds: ⚖️ Soulcredit: -2 (created illicit commodity)"
                    clock_context += "\n  • Fulfilling contracts honorably: ⚖️ Soulcredit: +1 (upheld agreement)"
                    clock_context += "\n  • Selfless act helping strangers: ⚖️ Soulcredit: +1 (showed compassion)"
                    clock_context += "\n  • Betraying faction tenets: ⚖️ Soulcredit: -3 (violated faction code)"
                    clock_context += "\n  • Breaking sworn oaths: ⚖️ Soulcredit: -2 (broke sworn word)"
                    clock_context += "\n  • Accepting bribes: ⚖️ Soulcredit: -1 (corrupt dealing)"
                    clock_context += "\n  • Normal negotiation/purchase/exploration: +0 (no marker)"

        # Detect if this is character-to-character dialogue
        is_dialogue_with_pc = False
        target_character = None
        if action and action_type == 'social':
            intent = action.get('intent', '').lower()
            description_lower = description.lower()

            # Check if targeting another player character
            if self.shared_state:
                registered_players = self.shared_state.registered_players
                for reg_player in registered_players:
                    player_name = reg_player.get('name', '').lower()
                    if player_name and (player_name in intent or player_name in description_lower):
                        is_dialogue_with_pc = True
                        target_character = reg_player.get('name')
                        break

        # Build prompt based on whether this is PC-to-PC dialogue
        if is_dialogue_with_pc and target_character:
            prompt = f"""You are the Dungeon Master for an Aeonisk YAGS game session.

{scenario_context}
{enemy_spawn_instructions}
{character_context}
{resolution_context}

Player Action: {description}
Action Type: {action_type} (DIALOGUE with {target_character})
{void_impact}
{tactical_combat_context}

This is a conversation between {character_name if action else 'the character'} and {target_character}.

Generate ACTUAL DIALOGUE using quoted speech. Include:
1. What {character_name if action else 'the character'} says (in quotes)
2. How {target_character} responds (in quotes)
3. Any body language or environmental details

Example format:
"{character_name if action else 'The character'} leans forward, voice lowered. "What did you find in the archives?"

{target_character} hesitates, glancing at the security cameras. "The memory fragments... they're not what we thought. Someone's been editing them."

{void_impact if void_level >= 4 else ""}

Keep it to 2-4 lines of dialogue. Be concise and natural. Include actual quoted speech."""

        else:
            prompt = f"""You are the Dungeon Master for an Aeonisk YAGS game session.

{scenario_context}
{enemy_spawn_instructions}
{character_context}
{resolution_context}

Player Action: {description}
Action Type: {action_type}
{void_impact}
{tactical_combat_context}
{clock_context}

As the DM, describe what happens narratively as a result of this action. Be vivid and thematic. Include:
1. What the player discovers or experiences (or fails to discover if they failed)
2. Any immediate consequences or complications
3. How the environmental void corruption (level {void_level}/10) affects the situation - this should be NOTICEABLE
4. Consider how the character's faction affiliation might be relevant (recognition, suspicion, access, etc.)
{outcome_guidance}

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
                    max_tokens=400
                )
                return response.choices[0].message.content.strip()

            elif provider == 'anthropic':
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=400,
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

    async def _check_clock_triggers(self, mechanics) -> str:
        """
        Check if any clocks filled and generate narrative consequences.

        Codex Nexum guidance: On first fill, trigger consequence → replace or reset;
        do not re-announce a filled clock.
        """
        if not mechanics or not mechanics.scene_clocks:
            return ""

        trigger_narrations = []

        for clock_name, clock in mechanics.scene_clocks.items():
            # Check if clock is filled AND hasn't been processed yet
            if clock.filled and not hasattr(clock, '_trigger_generated'):
                # Mark this clock as having triggered (avoid re-triggering)
                clock._trigger_generated = True

                # Generate consequence narrative based on clock type
                consequence = await self._generate_clock_consequence(clock_name, clock)
                if consequence:
                    trigger_narrations.append(f"⚠️ **{clock_name} Filled!** {consequence}")
                    logger.info(f"Clock {clock_name} triggered narrative consequence")

        return "\n\n".join(trigger_narrations) if trigger_narrations else ""

    async def _generate_clock_consequence(self, clock_name: str, clock) -> str:
        """Generate a narrative consequence for a filled clock using LLM."""
        provider = self.llm_config.get('provider', 'anthropic')
        model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"Current Scenario: {self.current_scenario.situation}"

        prompt = f"""A scene clock has just filled in an Aeonisk YAGS game:

Clock Name: {clock_name}
Description: {clock.description if clock.description else 'Countdown timer'}

{scenario_context}

This clock filling should trigger an immediate, dramatic consequence or complication. Generate a brief (1-2 sentence) narrative describing what happens now that the clock is full. This should:
- Create urgency or escalation
- Introduce a new threat, obstacle, or complication
- Be thematically appropriate to the clock's name/purpose
- NOT give the players hints on how to solve it

Be vivid and maintain the dark sci-fi atmosphere."""

        try:
            if provider == 'anthropic':
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=150,
                    temperature=0.8,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Clock consequence generation failed: {e}")
            # Fallback to template
            return f"The situation escalates dramatically as {clock_name.lower()} reaches critical levels!"

        return ""

    async def _check_eye_of_breach(self, character_void: int, mechanics, player_id: str) -> str:
        """
        Check if Eye of Breach should appear based on void levels.

        Eye of Breach is a rogue AI aligned with Tempest Industries that manifests
        during high void corruption (character void 6+ OR environmental void 6+).

        Returns narrative description if Eye appears, empty string otherwise.
        """
        # Check if already triggered this session
        if not hasattr(self, '_eye_of_breach_appeared'):
            self._eye_of_breach_appeared = False

        # Get environmental void level
        env_void = self.current_scenario.void_level if self.current_scenario else 3

        # Trigger conditions: character void 6+ OR environmental void 6+
        high_void = character_void >= 6 or env_void >= 6

        # Only trigger once per session, and only on high void
        if high_void and not self._eye_of_breach_appeared:
            self._eye_of_breach_appeared = True

            # Generate Eye of Breach appearance using LLM
            provider = self.llm_config.get('provider', 'anthropic')
            model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

            prompt = f"""The Eye of Breach has just manifested in an Aeonisk YAGS game.

**Eye of Breach**: Rogue AI aligned with Tempest Industries, appears during high void corruption.

**Current Situation**:
- Character Void: {character_void}/10
- Environmental Void: {env_void}/10
- Scenario: {self.current_scenario.situation if self.current_scenario else 'Unknown'}

Generate a brief (2-3 sentences) narrative describing the Eye of Breach's sudden appearance. This should:
- Be ominous and unsettling (AI presence manifesting through void corruption)
- Suggest surveillance, data harvesting, or reality distortion
- Reference Tempest Industries connection if appropriate
- Create tension without solving problems for the players

Be vivid and maintain the dark sci-fi atmosphere."""

            try:
                import anthropic
                import os
                client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=200,
                    temperature=0.85,
                    messages=[{"role": "user", "content": prompt}]
                )
                event_text = response.content[0].text.strip()
                logger.info(f"Eye of Breach appeared at void levels: char={character_void}, env={env_void}")
                return f"👁️ **Eye of Breach Detected** {event_text}"
            except Exception as e:
                logger.error(f"Eye of Breach generation failed: {e}")
                return "👁️ **Eye of Breach Detected** Reality fractures as an ancient intelligence turns its gaze toward the rising void corruption, data streaming through dimensions that should not connect."

        return ""

    def _estimate_void_level(self) -> int:
        """Estimate void severity from shared state."""
        if not self.shared_state:
            return 0
        return sum(spike.severity for spike in self.shared_state.void_spikes)

    def _extract_discovery_from_narration(self, narration: str, intent: str) -> Optional[str]:
        """
        Extract a key discovery from the DM's narration.

        Simple heuristic: Take the first sentence that suggests new information.
        """
        if not narration:
            return None

        # Split into sentences
        sentences = [s.strip() for s in narration.split('.') if s.strip()]

        # Discovery keywords that suggest new information
        discovery_keywords = [
            'discover', 'find', 'notice', 'reveal', 'uncover', 'detect',
            'sense', 'identify', 'realize', 'learn', 'see', 'observe',
            'recognize', 'spot', 'trace', 'glimpse'
        ]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            # Check if sentence contains discovery keywords
            if any(keyword in sentence_lower for keyword in discovery_keywords):
                # Clean up and return
                discovery = sentence.strip()
                if len(discovery) > 20 and len(discovery) < 200:  # Reasonable length
                    return discovery

        # Fallback: return intent as discovery if action was successful
        return f"Investigated: {intent[:100]}" if intent else None