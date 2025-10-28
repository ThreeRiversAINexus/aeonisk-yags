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
from .prompt_loader import load_agent_prompt, compose_sections

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
        force_scenario: Optional[str] = None,
        llm_logger: Optional[Any] = None,
        llm_client: Optional[Any] = None,
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
        self.force_scenario = force_scenario  # For automated testing
        self.llm_logger = llm_logger  # LLMCallLogger for replay functionality
        self._last_prompt_metadata = None  # Track prompt version/metadata for logging

        # LLM client - can be injected for replay (MockLLMClient) or created normally
        if llm_client:
            self.llm_client = llm_client
        else:
            # Create Anthropic client if not provided
            import anthropic
            import os
            self.llm_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # Vendor pool for random encounters
        self.vendor_pool = create_standard_vendors()

        # Story progression flags
        self.needs_story_advancement = False  # Set by session when all clocks complete

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
        logger.debug(f"AI DM {self.agent_id} started")
        
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
        logger.debug(f"AI DM {self.agent_id} shutting down")
        
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
        # Check for forced scenario (automated testing)
        if self.force_scenario:
            logger.info(f"Using forced scenario for testing: {self.force_scenario}")
            await self._use_forced_scenario(self.force_scenario, config)
            return

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
            logger.debug("Force vendor gate enabled - using vendor-gated scenario template")
            scenario_data = self._create_vendor_gated_scenario()
        elif force_combat:
            logger.debug("Force combat enabled - using combat scenario template")
            scenario_data = self._create_combat_scenario(config)
        else:
            # Check for scenario constraints/hints in DM config
            dm_config = config.get('agents', {}).get('dm', {})
            scenario_hint = dm_config.get('_scenario_hint', '')

            scenario_constraints = ""
            if scenario_hint:
                scenario_constraints = f"""
⚠️⚠️⚠️ **CRITICAL SCENARIO CONSTRAINTS** ⚠️⚠️⚠️
{scenario_hint}

YOU MUST FOLLOW THESE CONSTRAINTS EXACTLY. They override all other instructions below.
⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️

"""

            # Use LLM to generate dynamic scenario
            try:
                scenario_prompt = f"""Generate a unique Aeonisk YAGS scenario for a tabletop RPG session.

{scenario_constraints}
{party_context}
{lore_context}
{variety_context}

Create a scenario with:
1. Theme (2-3 words): The type of situation
2. Location: A specific place in the Aeonisk setting (USE CANONICAL LOCATIONS FROM LORE ABOVE)
3. Situation (1-2 sentences): What's happening
4. Three clocks/timers with CLEAR SEMANTICS:
   - A threat/danger that could escalate
   - Something the players are trying to accomplish
   - A complication or secondary concern

   **CRITICAL**: For each clock, specify what it means to ADVANCE and REGRESS:
   - If advancing = getting worse for players (danger increasing, time running out)
     → Name it clearly: "Security Alert", "Structural Collapse", "Hunter Pursuit"
     → Use MECHANICAL clock: FILLED should include [SPAWN_ENEMY: ...]
   - If advancing = progress on objective (evidence gathering, defenses built)
     → Name it clearly: "Evidence Collection", "Defenses Established", "Evacuation Progress"
     → Use NARRATIVE clock: FILLED should include [ADVANCE_STORY: Location | Situation] or [NEW_CLOCK: ...]
   - ALWAYS specify what happens when filled (mechanical OR narrative marker required)

Format:
THEME: [theme]
LOCATION: [location from canonical lore]
SITUATION: [situation]
CLOCK1: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]
CLOCK2: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]
CLOCK3: [name] | [max] | [description] | ADVANCE=[what advancing means] | REGRESS=[what regressing means] | FILLED=[consequence when filled]

Example clocks (MECHANICAL - with spawn markers):
CLOCK1: Security Alert | 6 | Corporate hunters closing in | ADVANCE=Hunters get closer to finding the team | REGRESS=Team evades or misleads pursuit | FILLED=Hunter team arrives [SPAWN_ENEMY: Corporate Hunters | elite | 2 | Far-Enemy | tactical_ranged]
CLOCK2: Containment Failure | 4 | Void breach imminent | ADVANCE=Breach worsens | REGRESS=Containment reinforced | FILLED=Void creature emerges [SPAWN_ENEMY: Void Manifestation | boss | 1 | Near-Enemy | aggressive_melee]

Example clocks (NARRATIVE - with scenario markers):
CLOCK3: Evidence Collection | 8 | Gathering proof of corruption | ADVANCE=More evidence found | REGRESS=Evidence destroyed | FILLED=Case ready, evidence complete [ADVANCE_STORY: Magistrate's Office | Confrontation with the corrupt magistrate]
CLOCK4: Escape Route | 6 | Finding way out of the facility | ADVANCE=Exit path revealed | REGRESS=Path blocked | FILLED=Exit found! [ADVANCE_STORY: Maintenance Tunnels | You emerge into the tunnels. Allies are regrouping ahead]
CLOCK5: Void Resonance | 4 | Growing instability | ADVANCE=Resonance intensifies | REGRESS=Stabilization efforts succeed | FILLED=New void rift opening [NEW_CLOCK: Rift Manifestation | 6 | Entities crossing over]

**IMPORTANT**: ALL clocks MUST have consequences in their FILLED field. Use:
- **Mechanical markers** for spawns/despawns: [SPAWN_ENEMY: ...], [DESPAWN_ENEMY: ...]
- **Scenario markers** for narrative progression: [ADVANCE_STORY: Location | Situation], [NEW_CLOCK: ...]

**ENEMY SPAWNING**: For combat/danger clocks, add enemy spawn markers to FILLED consequences:
- Syntax: [SPAWN_ENEMY: name | template | count | position | tactics]
- Templates: grunt (15 HP), elite (25 HP), sniper (20 HP), boss (40 HP), enforcer (30 HP), ambusher (18 HP)
- Positions: Engaged, Near-Enemy, Far-Enemy, Extreme-Enemy
- Tactics: aggressive_melee, defensive_ranged, tactical_ranged, extreme_range, ambush, adaptive
- Use for: Security teams, void creatures, gang members, hostile factions, corrupted entities
- Example: [SPAWN_ENEMY: Security Team | grunt | 2 | Far-Enemy | tactical_ranged]

**ENEMY DESPAWNING**: For escape/retreat clocks, add despawn markers:
- Syntax: [DESPAWN_ENEMY: enemy_name | reason]
- Reasons: escaped, retreated, teleported, fled, recalled, withdrew
- Example: [DESPAWN_ENEMY: Corporate Hunters | escaped through emergency exit]

IMPORTANT:
- Base your scenario on the canonical lore provided above
- Three planets: Aeonisk Prime, Nimbus, Arcadia (space travel between them is possible)
- Humans only, NO aliens
- Pick a DIFFERENT theme and location from recently used ones (if listed above)
- Be creative with scenario types:
  * COMBAT (50% of scenarios): **ambush**, **firefight**, **battle**, **siege**, **assault**, **defense**, **void creature attack**, **hostile extraction**, **combat rescue**, **gang warfare**, **security breach**
  * SOCIAL: tribunal/trial, bond dispute, debt settlement, trade negotiation, vendor conflict, economic disputes, social scandal
  * INTRIGUE: heist, investigation, ritual gone wrong, faction conflict, ancient mystery, political intrigue, transit crisis
  * CRISIS: void outbreak, station breach, emergency evacuation, containment failure
- **VARIETY IS KEY**: Mix combat scenarios with social/economic ones. About 50% of scenarios should have combat elements (enemies spawning when danger clocks fill)
- **Combat scenarios MUST include**: At least one clock with [SPAWN_ENEMY: ...] in its FILLED consequence
- **Good combat setups**: Ambushes by rival factions, void-corrupted threats, gang turf wars, hostile encounters during missions, defensive stands, security teams responding to alarms
- **Vendor/Economy scenarios**: Resource acquisition, price negotiations, debt settlement, economic crime investigation
- If Tempest Industries is involved OR void level is 6+, consider mentioning Eye of Breach (rogue AI) as a potential threat or presence
- ⚠️ CRITICAL: Respect the party composition above. DO NOT create scenarios where characters betray their own faction
- ⚠️ CRITICAL: Align scenarios with character goals OR create interesting cross-faction cooperation (e.g., Sovereign Nexus + ArcGen investigating a shared threat)
- Good examples: ACG hires party to recover stolen debt contracts, Pantheon investigates void corruption, factions team up against common enemy
- BAD examples: ACG hires Sovereign Nexus to steal from Codex Cathedral, hiring characters to sabotage their own faction"""

                provider = self.llm_config.get('provider', 'anthropic')
                model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

                response = await asyncio.to_thread(
                    self.llm_client.messages.create,
                    model=model,
                    max_tokens=500,
                    temperature=0.9,
                    messages=[{"role": "user", "content": scenario_prompt}]
                )
                llm_text = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": scenario_prompt}],
                        response=llm_text,
                        model=model,
                        temperature=0.9,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=None,  # Scenario generation happens before round 1
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

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

                            # Log LLM call for replay
                            if self.llm_logger:
                                self.llm_logger._log_llm_call(
                                    messages=[{"role": "user", "content": retry_prompt}],
                                    response=llm_text,
                                    model=model,
                                    temperature=1.0,
                                    tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                                    current_round=None,
                                    call_sequence=self.llm_logger.call_count
                                )
                                self.llm_logger.call_count += 1

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
                logger.debug(f"Vendor-gated scenario: forcing {active_vendor.name} ({active_vendor.vendor_type.value})")
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

    async def _use_forced_scenario(self, spawn_marker: str, config: Dict[str, Any]):
        """Use a forced scenario for automated testing (bypasses AI generation)."""
        # Create minimal scenario object
        scenario = Scenario(
            theme="Test Scenario",
            location="Test Location",
            situation=spawn_marker,
            active_npcs=[],
            environmental_factors=[],
            void_level=0,
            active_vendor=None
        )
        self.current_scenario = scenario

        # Prepare scenario data
        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'vendor': None
        }

        # Log scenario
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
                'opening_narration': f"Test scenario initialized. {spawn_marker}",
                'faction_conflicts': []
            }
        )

        print(f"\n[DM {self.agent_id}] Using forced test scenario")
        print(f"Spawn marker: {spawn_marker}")

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
                    ('Enemy Reinforcements', 10, 'Backup being called in', 'ADVANCE=Enemies calling for backup', 'REGRESS=Delaying reinforcements', 'FILLED=Second wave arrives! [SPAWN_ENEMY: Reserve Forces | grunt | 2 | Far-Enemy | tactical_ranged]'),
                    ('Critical Wounds', 4, 'Party members taking severe injuries')
                ]
            },
            {
                'theme': 'Gang Ambush',
                'location': 'Undercity Maintenance Tunnels (Arcadia)',
                'situation': 'A Freeborn gang has set up an ambush - they think you\'re rival dealers. Muzzle flashes illuminate the darkness as they open fire from concealed positions. [SPAWN_ENEMY: Gang Ambushers | grunt | 2 | Near-Enemy | aggressive_melee]',
                'void_level': 3,
                'clocks': [
                    ('Reinforcements Arriving', 10, 'More gang members responding to gunfire', 'ADVANCE=More gang members hear the firefight', 'REGRESS=Silencing the gang', 'FILLED=Gang backup arrives! [SPAWN_ENEMY: Gang Reinforcements | grunt | 2 | Far-Enemy | defensive_ranged]'),
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
                    ('Security Reinforcements', 10, 'Tactical teams deploying', 'ADVANCE=More security responding', 'REGRESS=Evading security', 'FILLED=Tactical team arrives! [SPAWN_ENEMY: Security Tacticals | grunt | 2 | Far-Enemy | tactical_ranged]'),
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
                    ('Freeborn Escape', 4, 'Pirates fighting their way to ships', 'ADVANCE=Pirates advancing toward escape route', 'REGRESS=Blocking pirate escape', 'FILLED=Pirates successfully disengage and escape! [DESPAWN_ENEMY: Freeborn Pirates | escaped]'),
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
                    ('Raider Reinforcements', 10, 'Second wave incoming', 'ADVANCE=More raiders arriving', 'REGRESS=Slowing reinforcements', 'FILLED=Second wave breaches! [SPAWN_ENEMY: Void Raiders | grunt | 2 | Near-Enemy | aggressive_melee]'),
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
                    ('Assassin Reinforcements', 10, 'More killers deploying', 'ADVANCE=Backup team getting closer', 'REGRESS=Delaying reinforcements', 'FILLED=Elite hit team arrives! [SPAWN_ENEMY: Professional Hit Team | elite | 2 | Far-Enemy | tactical_ranged]'),
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
                    ('Scavenger Reinforcements', 10, 'Main gang arriving', 'ADVANCE=More scavengers coming', 'REGRESS=Driving scavengers away', 'FILLED=Full gang attacks! [SPAWN_ENEMY: Scavenger Gang | grunt | 2 | Near-Enemy | aggressive_melee]'),
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
                    ('Gang Escalation', 10, 'Both sides calling reinforcements', 'ADVANCE=More gang members arriving', 'REGRESS=Dispersing the gangs', 'FILLED=Full gang war erupts! [SPAWN_ENEMY: Gang Reinforcements | grunt | 2 | Engaged | aggressive_melee]'),
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
            logger.debug(f"Using specified combat scenario index {scenario_index}: {template['theme']}")
        else:
            template = random.choice(templates)
            logger.debug(f"Using random combat scenario: {template['theme']}")

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
            # Declaration phase - acknowledge but don't resolve (logged in debug only)
            logger.debug(f"[DM {self.agent_id}] Noted: {player_id} declared action")
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

        # Increment clock ages at start of each round
        if self.shared_state and action_index == 0:  # Only on first action of the round
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                mechanics.increment_all_clock_rounds()

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
                        'void_source': state_changes.get('void_source', ''),
                        'soulcredit_delta': state_changes.get('soulcredit_change', 0),
                        'soulcredit_reasons': state_changes.get('soulcredit_reasons', []),
                        'soulcredit_source': state_changes.get('soulcredit_source', '')
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

                    # Extract clock sources from clock_triggers
                    clock_sources = {}
                    for clock_name, ticks, reason, source in state_changes.get('clock_triggers', []):
                        clock_sources[clock_name] = source

                    context = {
                        "action_type": action.get('action_type', 'unknown'),
                        "is_ritual": is_ritual_action,
                        "faction": action.get('faction', 'Unknown'),
                        "description": action.get('description', ''),
                        "narration": resolution.get('narration', ''),
                        "is_free_action": action.get('is_free_action', False),
                        "initiative": initiative,
                        "clock_deltas": clock_deltas,  # Include clock before/after/reason
                        "clock_sources": clock_sources  # Include source for each clock change
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

                    # Add prompt metadata if available
                    if hasattr(self, '_last_prompt_metadata') and self._last_prompt_metadata:
                        context['prompt_metadata'] = self._last_prompt_metadata.to_dict()

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

                    # Track action for round summary statistics
                    if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                        self.shared_state.session.track_action_resolution(
                            success=action_resolution.success,
                            margin=action_resolution.margin
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

        # Apply all queued clock updates (batch application prevents cascade fills)
        clock_updates_applied = {}
        expired_clocks = []
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                clock_updates_applied = mechanics.apply_queued_clock_updates()
                if clock_updates_applied:
                    logger.debug(f"Applied {len(clock_updates_applied)} queued clock updates during synthesis")

                # Check for expired clocks after applying updates
                expired_clocks = mechanics.check_and_expire_clocks()
                if expired_clocks:
                    logger.warning(f"Found {len(expired_clocks)} expired clocks: {[c['clock_name'] for c in expired_clocks]}")

        # Build expired clocks text for DM prompt
        expired_clocks_text = ""
        if expired_clocks:
            expired_lines = []
            for exp in expired_clocks:
                clock_name = exp['clock_name']
                exp_type = exp['expiration_type']
                current = exp['current']
                maximum = exp['maximum']
                description = exp['description']
                advance_means = exp.get('advance_means', '')
                regress_means = exp.get('regress_means', '')
                filled_consequence = exp.get('filled_consequence', '')

                # Build semantic context for expired clock
                semantic_context = ""
                if advance_means or regress_means:
                    semantic_context = "\n     📊 SEMANTIC CONTEXT:"
                    if advance_means:
                        semantic_context += f"\n        Advance = {advance_means}"
                    if regress_means:
                        semantic_context += f"\n        Regress = {regress_means}"
                    semantic_context += f"\n     ⚠️  Use this to interpret if {current}/{maximum} is good or bad!"

                if exp_type == "crisis_averted":
                    expired_lines.append(f"  ⏰ **{clock_name}** (was {current}/{maximum}) - CRISIS AVERTED/OPPORTUNITY LOST{semantic_context}")
                    expired_lines.append(f"     The threat/opportunity has passed without resolution. Narrate how the situation defused or the window closed.")
                elif exp_type == "force_resolve":
                    expired_lines.append(f"  🔔 **{clock_name}** (FILLED: {current}/{maximum}) - TRIGGERING CONSEQUENCES{semantic_context}")
                    if filled_consequence:
                        expired_lines.append(f"     Consequence: {filled_consequence}")
                        # Check if this is a mechanical clock (has markers) or narrative clock
                        if any(marker in filled_consequence for marker in ['[SPAWN_ENEMY:', '[DESPAWN_ENEMY:', '[NEW_CLOCK:', '[ADVANCE_STORY:']):
                            expired_lines.append(f"     → Include the marker from the consequence in your narration")
                        else:
                            expired_lines.append(f"     → This is a NARRATIVE clock - you MUST use a scenario marker ([ADVANCE_STORY: Location | Situation] or [NEW_CLOCK: ...]) to change the story!")
                    else:
                        expired_lines.append(f"     → This clock filled without a consequence. You MUST use [ADVANCE_STORY: Location | Situation] to advance the narrative!")
                elif exp_type == "escalate":
                    expired_lines.append(f"  ⏰ **{clock_name}** (was {current}/{maximum}) - SITUATION ESCALATES{semantic_context}")
                    expired_lines.append(f"     Stalemate breaks. Consider [ADVANCE_STORY: Location | new situation] or [NEW_CLOCK: new pressure] to intensify/resolve.")

            expired_clocks_text = "\n\n⏰ **CLOCKS EXPIRED (Auto-removed):**\n" + "\n".join(expired_lines)
            expired_clocks_text += "\n\n⚠️  You MUST narrate what happens as these clocks expire AND use scenario markers for narrative clocks!"

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
                    filled_clocks_text = f"\n\n{urgency} **CLOCKS FILLED (Auto-removing):** {', '.join(filled_names)}\n"
                    filled_clocks_text += "⚠️  **MANDATORY**: Filled clocks MUST trigger scenario changes!\n\n"
                    filled_clocks_text += "**For clocks with mechanical markers** (e.g., [SPAWN_ENEMY: ...]):\n"
                    filled_clocks_text += "- Include the exact marker text from filled_consequence in your narration\n"
                    filled_clocks_text += "- The marker will trigger automatically\n\n"
                    filled_clocks_text += "**For narrative clocks** (no mechanical markers):\n"
                    filled_clocks_text += "- You MUST use a DM control marker to change the scenario:\n"
                    filled_clocks_text += "  • [ADVANCE_STORY: Location | Situation] - progress to new location or change situation in same location\n"
                    filled_clocks_text += "    Examples:\n"
                    filled_clocks_text += "      - Investigation clock fills → [ADVANCE_STORY: Magistrate's Office | Confrontation with the saboteur]\n"
                    filled_clocks_text += "      - Escape clock fills → [ADVANCE_STORY: Safe House | You've escaped. Regrouping with wounded allies]\n"
                    filled_clocks_text += "      - Same location → [ADVANCE_STORY: Corporate Facility - Lockdown | Alarms blare as security seals all exits]\n"
                    filled_clocks_text += "  • [NEW_CLOCK: Name | Max | Description] - new pressure/opportunity emerges\n"
                    filled_clocks_text += "    Example: Corruption clock fills → [NEW_CLOCK: Void Manifestation | 4 | Entity taking form]\n"
                    filled_clocks_text += "  • [SESSION_END: VICTORY/DEFEAT/DRAW] - mission fully complete or total failure\n\n"
                    filled_clocks_text += "⚠️  Narrative clocks that fill WITHOUT a scenario marker will stall the story!"

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

**SPAWN ENEMIES - CLOCK FILLS ONLY:**
⚠️  **CRITICAL RESTRICTION**: You may ONLY spawn enemies when a clock with [SPAWN_ENEMY: ...] in its filled_consequence actually fills!

❌ **FORBIDDEN**: Do NOT spawn enemies in general narration
❌ **FORBIDDEN**: Do NOT add [SPAWN_ENEMY: ...] to dramatic descriptions
❌ **FORBIDDEN**: Do NOT spawn "because it feels dramatic"

✅ **ALLOWED**: ONLY when you see "🎯 When filled: [SPAWN_ENEMY: ...]" in the clock list above

Syntax: [SPAWN_ENEMY: name | template | count | position | tactics]
Example from filled clock: [SPAWN_ENEMY: Security Team | grunt | 2 | Far-Enemy | tactical_ranged]

Templates: grunt (15 HP), elite (25 HP), sniper (20 HP), boss (40 HP), enforcer (30 HP), ambusher (18 HP)
Positions: Engaged, Near-Enemy, Far-Enemy, Extreme-Enemy
Tactics: aggressive_melee, defensive_ranged, tactical_ranged, extreme_range, ambush, adaptive

**WHY THIS RESTRICTION**: Mid-round spawns bypass clock-based pacing and overwhelm players. Spawns must be predictable and tied to clock advancement.

**DESPAWN ENEMIES - AUTOMATIC MECHANIC:**
When a clock with [DESPAWN_ENEMY: ...] in its filled_consequence fills, that enemy is automatically removed from combat.

Syntax: [DESPAWN_ENEMY: enemy_name | reason]
Example from filled clock: [DESPAWN_ENEMY: Freeborn Pirates | escaped]

Common reasons: escaped, retreated, teleported, fled, recalled, withdrew

**IMPORTANT**: You still narrate the escape/withdrawal, but the [DESPAWN_ENEMY: ...] marker is already in the clock's filled_consequence. Just copy the consequence text including the marker when you describe what happens."""

        # Check if story advancement is needed (all clocks complete)
        story_advancement_prompt = ""
        if self.needs_story_advancement:
            logger.info("Story advancement triggered - adding prompt context")
            story_advancement_prompt = """

🎬 **STORY ADVANCEMENT REQUIRED - ALL CLOCKS COMPLETE**

⚠️  **CRITICAL**: All scenario clocks have been resolved! The current situation has concluded.

**YOU MUST** use the [ADVANCE_STORY: location | situation] marker to move the narrative forward:

**Format:** [ADVANCE_STORY: New Location | New Situation Description]

**Examples:**
- [ADVANCE_STORY: Rebel Safe House | You've escaped the ambush. Time to regroup and plan your next move]
- [ADVANCE_STORY: The Void Nexus | The corruption has spread. You must investigate the source]
- [ADVANCE_STORY: Corporate Trading Hub | With intel gathered, you head to sell information and resupply]

**What happens when you use [ADVANCE_STORY: ...]:**
1. All remaining clocks are cleared
2. Players are notified of the new location and situation
3. A fresh scenario with new clocks will be generated for the next round

**After the [ADVANCE_STORY: ...] marker, you MUST create 2-3 new clocks using [NEW_CLOCK: ...] markers:**

**Format:** [NEW_CLOCK: Clock Name | Max Ticks | Description]

**Examples:**
- [NEW_CLOCK: Security Override | 6 | Bypass the archive's automated defenses]
- [NEW_CLOCK: Void Spread | 6 | The archive's corruption grows stronger]
- [NEW_CLOCK: Data Decay | 4 | Critical information is being lost]

**CRITICAL:** You must include BOTH markers:
1. [ADVANCE_STORY: location | situation] - Moves to new location
2. [NEW_CLOCK: name | max | desc] - Creates new objectives (2-3 clocks)

Without [NEW_CLOCK:...] markers, the new scenario will have NO objectives and the session will stall!

⚠️  **DO NOT** write clock names in prose - use the [NEW_CLOCK:...] marker format!
⚠️  **DO NOT** continue in the current location with no clocks - the story will stall!
"""

        # Use LLM to generate synthesis if available
        if self.llm_config:
            prompt = f"""You are the DM for a dark sci-fi TTRPG. Multiple characters just acted simultaneously.

**What they tried to do:**
{outcomes_text}
{clock_state_text}
{filled_clocks_text}
{expired_clocks_text}
{story_advancement_prompt}

**Your task:** Write a cohesive narrative (1-2 paragraphs) describing what happened when these actions played out together. Consider:
- Timing: Actions resolved fastest → slowest based on initiative
- Interactions: How did each person's success/failure affect the others?
- Conflicts: If multiple people tried similar things, who got there first? What did the slower person encounter?
- Cause and effect: How did earlier successes/failures change the situation for later actors?
- Overall outcome: What's the new situation now that the dust has settled?
- **IMPORTANT**: If objectives (clocks) are not advancing despite actions, acknowledge this! Characters should feel the pressure of marginal success or outright failure.

Be vivid and cinematic. Show how these actions interacted and created a dynamic scene. Describe the final state of the situation after all actions resolved.

If the team is failing their objectives (clocks not advancing or bad clocks filling), your narration should reflect the growing desperation, consequences, and danger.

**⚠️  CLOCK INTERPRETATION - READ CAREFULLY:**
Each clock has semantic meaning shown as "Advance = X" and "Regress = Y".
- If "Advance = threat escalates", then HIGH values are BAD for players
- If "Advance = progress made", then HIGH values are GOOD for players
- Use the semantic labels to interpret whether clock changes help or hurt the party
- When a clock REGRESSES, check if that's good (threat reduced) or bad (progress lost)

**CRITICAL**: If any clocks just filled, you MUST describe the dramatic consequences. This could include:
- Character injury or void corruption (specify who and how much void: "+2 void")
- Character death/dissolution if appropriate
- Mission failure or catastrophic events
- Environmental changes or new threats
- Success and rewards if it's a positive clock

Generate appropriate consequences based on what makes sense for that specific clock in this scenario.

{enemy_spawn_prompt}"""

            try:
                response = await asyncio.to_thread(
                    self.llm_client.messages.create,
                    model=self.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                    max_tokens=500,
                    temperature=0.8,
                    messages=[{"role": "user", "content": prompt}]
                )
                synthesis_text = response.content[0].text.strip()

                # Check for invalid SPAWN_ENEMY markers and retry if needed
                from .enemy_spawner import extract_invalid_spawn_markers
                invalid_spawns = extract_invalid_spawn_markers(synthesis_text)

                if invalid_spawns:
                    logger.warning(f"Found {len(invalid_spawns)} invalid SPAWN_ENEMY markers in synthesis - requesting retry")
                    retry_response = await self._retry_invalid_markers(
                        marker_type="SPAWN_ENEMY",
                        invalid_markers=invalid_spawns,
                        round_num=round_num
                    )
                    # Append corrected markers to synthesis
                    if retry_response.strip():
                        synthesis_text += f"\n\n{retry_response}"
                        logger.info(f"Appended retry response to synthesis")

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=synthesis_text,
                        model=self.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                        temperature=0.8,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=round_num,
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

                # Clear story advancement flag after synthesis generation
                if self.needs_story_advancement:
                    logger.info("Story advancement synthesis generated - clearing flag")
                    self.needs_story_advancement = False

                return synthesis_text
            except Exception as e:
                logger.error(f"Synthesis generation failed: {e}")
                # Clear flag even on error
                if self.needs_story_advancement:
                    self.needs_story_advancement = False
                return f"Round {round_num} completes with mixed results:\n{outcomes_text}"
        else:
            # Clear flag even if no LLM
            if self.needs_story_advancement:
                self.needs_story_advancement = False
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

            # CRITICAL: Resolve target IDs to character names for void cleansing
            # In free targeting mode, actions have target_enemy="tgt_xxxx" but outcome parser needs target_character="Name"
            if action.get('target_enemy') and action['target_enemy'].startswith('tgt_'):
                target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                if target_id_mapper and target_id_mapper.enabled:
                    target_entity = target_id_mapper.resolve_target(action['target_enemy'])
                    # If targeting a PC, populate target_character for void cleansing mechanics
                    if target_entity and target_id_mapper.is_player(action['target_enemy']):
                        if hasattr(target_entity, 'character_state') and hasattr(target_entity.character_state, 'name'):
                            action['target_character'] = target_entity.character_state.name
                            logger.debug(f"Resolved target ID {action['target_enemy']} → character '{action['target_character']}' for void cleansing")

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

                # If still no effect, generate fallback damage ONLY for actual enemies
                # For PC-to-PC actions in free targeting mode, trust the DM's narration entirely
                if not effect and resolution and resolution.success:
                    # Check if target is a PC or enemy
                    target_identifier = action.get('target_enemy')
                    is_targeting_pc = False

                    if target_identifier and target_identifier.startswith('tgt_'):
                        target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                        if target_id_mapper and target_id_mapper.enabled:
                            is_targeting_pc = target_id_mapper.is_player(target_identifier)

                    # Only generate fallback damage if targeting an actual enemy (not a PC)
                    # For PC-to-PC actions: DM narration is authoritative (heal/harm/purify determined by DM)
                    if not is_targeting_pc:
                        effect = generate_fallback_effect(action, resolution.__dict__ if hasattr(resolution, '__dict__') else resolution)
                        if effect:
                            logger.debug(f"Generated fallback effect for enemy: {effect.get('type')} targeting {effect.get('target')}")
                    else:
                        logger.debug(f"Targeting PC detected - trusting DM narration entirely (no fallback damage)")

            # Apply effect to enemy if we have one
            if effect and self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
                enemy_combat = self.shared_state.enemy_combat
                if enemy_combat:
                    from .enemy_spawner import get_active_enemies
                    active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                    # Resolve target (combat ID or fuzzy name match)
                    target_identifier = effect.get('target', action.get('target_enemy'))
                    target_entity = None
                    target_enemy_name = None  # Initialize for legacy path
                    is_friendly_fire = False

                    # Check if using target ID system (free targeting mode)
                    if target_identifier and target_identifier.startswith('tgt_'):
                        target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                        if target_id_mapper and target_id_mapper.enabled:
                            target_entity = target_id_mapper.resolve_target(target_identifier)

                            # Check if target is a player (friendly fire!)
                            if target_entity and target_id_mapper.is_player(target_identifier):
                                is_friendly_fire = True
                                attacker_name = action.get('agent_id', 'Unknown')
                                target_name = getattr(target_entity.character_state, 'name', 'Unknown') if hasattr(target_entity, 'character_state') else 'Unknown'
                                logger.warning(f"🔥 FRIENDLY FIRE: {attacker_name} targeting PC {target_name} (ID: {target_identifier})")
                    else:
                        # Legacy fuzzy name matching for enemies
                        target_enemy_name = target_identifier
                        for enemy in active_enemies:
                            if target_enemy_name and (target_enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in target_enemy_name.lower()):
                                target_entity = enemy
                                break

                    if target_entity:
                        # Extract target name once for all effect types
                        if is_friendly_fire and hasattr(target_entity, 'character_state'):
                            # Target is a PC
                            target_name = target_entity.character_state.name
                        else:
                            # Target is an enemy
                            target_name = target_entity.name

                        effect_type = effect.get('type', 'unknown')

                        if effect_type == 'damage':
                            # Apply damage (works for both enemies and PCs)
                            damage_dealt = effect.get('final', 0)

                            # Get health/wounds from correct location (PC vs enemy)
                            if is_friendly_fire and hasattr(target_entity, 'character_state'):
                                # Target is a PC - health/wounds are on the agent, not character_state
                                old_health = target_entity.health  # Health is on the agent
                                wounds_dealt = damage_dealt // 5  # YAGS: every 5 damage = 1 wound
                                target_entity.wounds += wounds_dealt  # Wounds on the agent
                                target_entity.health -= damage_dealt  # Health on the agent
                                logger.warning(f"🔥 FRIENDLY FIRE DAMAGE: {damage_dealt} to {target_name} ({old_health} → {target_entity.health} HP, +{wounds_dealt} wounds)")
                            else:
                                # Target is an enemy
                                old_health = target_entity.health
                                wounds_dealt = damage_dealt // 5  # YAGS: every 5 damage = 1 wound
                                target_entity.wounds += wounds_dealt
                                target_entity.health -= damage_dealt
                                logger.info(f"Player dealt {damage_dealt} damage to {target_name} ({old_health} → {target_entity.health} HP, +{wounds_dealt} wounds)")

                            # Track damage for round summary
                            if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                                self.shared_state.session.track_player_damage_dealt(damage_dealt)

                            # Log player combat action for ML training
                            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                # Build attack roll data from resolution
                                attack_roll_data = {
                                    "attr": resolution.attribute if resolution else "Unknown",
                                    "attr_val": resolution.attribute_value if resolution else 0,
                                    "skill": resolution.skill if resolution else None,
                                    "skill_val": resolution.skill_value if resolution else 0,
                                    "weapon_bonus": 0,  # Not tracked for player attacks currently
                                    "d20": resolution.roll if resolution else 0,
                                    "total": resolution.total if resolution else 0,
                                    "dc": resolution.difficulty if resolution else 0,
                                    "hit": resolution.success if resolution else True,
                                    "margin": resolution.margin if resolution else 0
                                }

                                # Build damage roll data from combat_data or effect
                                damage_roll_data = {
                                    "base_damage": combat_data.get('damage', damage_dealt) if combat_data else damage_dealt,
                                    "soak": combat_data.get('soak', 0) if combat_data else 0,
                                    "dealt": damage_dealt
                                }

                                # Get defender state after damage (works for both PCs and enemies)
                                # Health/wounds are stored directly on agent objects, not on CharacterState
                                defender_state = {
                                    "health": target_entity.health,
                                    "max_health": target_entity.max_health,
                                    "wounds": target_entity.wounds,
                                    "alive": target_entity.health > 0,
                                    "status": "active" if target_entity.health > 0 else "defeated"
                                }

                                # Get weapon from action intent or default
                                weapon_name = "Unknown Weapon"
                                if action.get('intent'):
                                    intent_lower = action['intent'].lower()
                                    if 'rifle' in intent_lower or 'gun' in intent_lower:
                                        weapon_name = "Firearm"
                                    elif 'pistol' in intent_lower:
                                        weapon_name = "Pistol"
                                    elif 'melee' in intent_lower or 'sword' in intent_lower or 'blade' in intent_lower:
                                        weapon_name = "Melee Weapon"
                                    elif 'punch' in intent_lower or 'kick' in intent_lower or 'brawl' in intent_lower:
                                        weapon_name = "Unarmed"
                                    elif action.get('skill'):
                                        weapon_name = f"{action['skill']} Attack"

                                mechanics.jsonl_logger.log_combat_action(
                                    round_num=mechanics.current_round,
                                    attacker_id=action.get('agent_id', 'unknown_player'),
                                    attacker_name=action.get('character', 'Unknown Player'),
                                    defender_id=target_entity.agent_id,
                                    defender_name=target_name,  # Already extracted above
                                    weapon=weapon_name,
                                    attack_roll=attack_roll_data,
                                    damage_roll=damage_roll_data,
                                    wounds_dealt=wounds_dealt,
                                    defender_state_after=defender_state
                                )

                            # Add effect notification
                            source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                            narration += f"\n\n⚔️  **{target_name} takes {damage_dealt} damage!** {source_label}"

                            # Check if target died (only enemies have death saves)
                            if target_entity.health <= 0:
                                if hasattr(target_entity, 'check_death_save'):
                                    alive, status = target_entity.check_death_save()
                                    if not alive:
                                        logger.info(f"{target_name} KILLED by player attack!")
                                        narration += f"\n💀 **{target_name} is KILLED!**"
                                    elif status == "unconscious":
                                        logger.info(f"{target_name} knocked unconscious!")
                                        narration += f"\n😵 **{target_name} is knocked unconscious!**"
                                    else:
                                        logger.info(f"{target_name} critically wounded but conscious!")
                                        narration += f"\n⚠️  **{target_name} is critically wounded!**"
                                else:
                                    logger.info(f"{target_name} defeated!")
                                    narration += f"\n💀 **{target_name} is defeated!**"

                        elif effect_type == 'debuff':
                            # Apply debuff (only enemies support this)
                            if hasattr(target_entity, 'add_debuff'):
                                penalty = effect.get('penalty', -2)
                                duration = effect.get('duration', 3)
                                effect_desc = effect.get('effect', f"{penalty} to rolls")
                                source = effect.get('source', 'player')

                                target_entity.add_debuff(effect_desc, penalty, duration, source)

                                source_label = "(fallback)" if source == 'fallback' else ""
                                narration += f"\n\n🔻 **{target_name} debuffed: {effect_desc}** (lasts {duration} rounds) {source_label}"

                        elif effect_type == 'status':
                            # Apply status effect (only enemies support this)
                            if hasattr(target_entity, 'add_status_effect'):
                                status_effect = effect.get('effect', 'affected')
                                duration = effect.get('duration', 1)

                                target_entity.add_status_effect(status_effect, duration)

                                source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                                narration += f"\n\n💫 **{target_name} status: {status_effect}** {source_label}"

                        elif effect_type == 'movement':
                            # Apply forced movement
                            movement_desc = effect.get('effect', 'forced to move')
                            new_position = effect.get('new_position')

                            if new_position and hasattr(target_entity, 'position'):
                                from .enemy_agent import Position
                                try:
                                    target_entity.position = Position.from_string(new_position)
                                    narration += f"\n\n🚶 **{target_name} forced to {new_position}!**"
                                except:
                                    narration += f"\n\n🚶 **{target_name} disrupted: {movement_desc}!**"
                            else:
                                narration += f"\n\n🚶 **{target_name} disrupted: {movement_desc}!**"

                        elif effect_type == 'reveal':
                            # Add revealed weakness (only enemies support this)
                            if hasattr(target_entity, 'add_revealed_weakness'):
                                weakness_desc = effect.get('effect', 'weakness revealed')
                                bonus = effect.get('bonus', 2)

                                target_entity.add_revealed_weakness(weakness_desc, bonus)

                                narration += f"\n\n🔍 **{target_name} weakness revealed: {weakness_desc}** (+{bonus} for allies)"

                        else:
                            logger.warning(f"Unknown effect type: {effect_type}")

                    else:
                        logger.warning(f"Could not find target '{target_identifier}' to apply effect")

            # Parse and apply ally buffs if action targets ally
            buff = None
            if action.get('target_ally'):
                # Try to parse explicit buff effect block (similar to enemy effects)
                # For now, we'll use fallback generation since DM doesn't explicitly write buff blocks yet

                # Generate fallback buff if successful action
                if resolution and resolution.success:
                    buff = generate_fallback_buff(action, resolution.__dict__ if hasattr(resolution, '__dict__') else resolution)
                    if buff:
                        logger.debug(f"Generated fallback buff: {buff.get('type')} for {buff.get('target')}")

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

            # Parse social de-escalation markers ([ENEMY_SURRENDER:], [ENEMY_FLEE:])
            import re
            surrender_pattern = r'\[ENEMY_SURRENDER:\s*([^\]]+)\]'
            flee_pattern = r'\[ENEMY_FLEE:\s*([^\]]+)\]'

            surrender_matches = re.findall(surrender_pattern, narration)
            flee_matches = re.findall(flee_pattern, narration)

            if surrender_matches or flee_matches:
                if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
                    enemy_combat = self.shared_state.enemy_combat
                    if enemy_combat:
                        from .enemy_spawner import get_active_enemies

                        # Process surrenders
                        for enemy_name_raw in surrender_matches:
                            enemy_name = enemy_name_raw.strip()
                            active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                            # Find matching enemy (fuzzy match)
                            target_enemy = None
                            for enemy in active_enemies:
                                if enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in enemy_name.lower():
                                    target_enemy = enemy
                                    break

                            if target_enemy:
                                # Mark enemy as surrendered (prisoner)
                                target_enemy.is_active = False
                                target_enemy.status_effects.append("prisoner")
                                logger.info(f"Social action: {target_enemy.name} surrendered (prisoner)")

                                # Track prisoner in session
                                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                                    session = self.shared_state.session
                                    if not hasattr(session, 'prisoners'):
                                        session.prisoners = []
                                    session.prisoners.append({
                                        'name': target_enemy.name,
                                        'round': mechanics.current_round if mechanics else 0,
                                        'method': 'intimidation/persuasion'
                                    })

                                # Log social de-escalation event
                                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                    # Detect action type from action intent/description
                                    action_type = "intimidation"  # Default
                                    intent_lower = (action.get('intent', '') + action.get('description', '')).lower()
                                    if 'persuade' in intent_lower or 'convince' in intent_lower or 'negotiate' in intent_lower:
                                        action_type = "persuasion"

                                    skill = action.get('skill', 'Intimidation' if action_type == 'intimidation' else 'Persuasion')

                                    mechanics.jsonl_logger.log_social_deescalation(
                                        round_num=mechanics.current_round,
                                        player_id=player_id,
                                        player_name=action.get('character', 'Unknown'),
                                        enemy_id=target_enemy.agent_id,
                                        enemy_name=target_enemy.name,
                                        action_type=action_type,
                                        skill=skill,
                                        roll_total=resolution.total if resolution else 0,
                                        dc=resolution.difficulty if resolution else 20,
                                        success=resolution.success if resolution else True,
                                        margin=resolution.margin if resolution else 10,
                                        outcome="surrender",
                                        narration=narration[:500]  # Truncate to 500 chars
                                    )
                            else:
                                logger.warning(f"Could not find enemy '{enemy_name}' to mark as surrendered")

                        # Process fleeing
                        for enemy_name_raw in flee_matches:
                            enemy_name = enemy_name_raw.strip()
                            active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                            # Find matching enemy (fuzzy match)
                            target_enemy = None
                            for enemy in active_enemies:
                                if enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in enemy_name.lower():
                                    target_enemy = enemy
                                    break

                            if target_enemy:
                                # Trigger morale flee (uses existing flee logic)
                                target_enemy.is_active = False
                                logger.info(f"Social action: {target_enemy.name} fled (intimidated)")

                                # Advance escape clock if it exists
                                if mechanics and mechanics.scene_clocks:
                                    for clock_name in mechanics.scene_clocks:
                                        if 'escape' in clock_name.lower() or 'retreat' in clock_name.lower():
                                            mechanics.queue_clock_update(clock_name, 2, f"{target_enemy.name} fled from intimidation")
                                            break

                                # Log social de-escalation event
                                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                    # Detect action type from action intent/description
                                    action_type = "intimidation"  # Default for flee is intimidation
                                    intent_lower = (action.get('intent', '') + action.get('description', '')).lower()
                                    if 'persuade' in intent_lower or 'convince' in intent_lower or 'negotiate' in intent_lower:
                                        action_type = "persuasion"

                                    skill = action.get('skill', 'Intimidation' if action_type == 'intimidation' else 'Persuasion')

                                    mechanics.jsonl_logger.log_social_deescalation(
                                        round_num=mechanics.current_round,
                                        player_id=player_id,
                                        player_name=action.get('character', 'Unknown'),
                                        enemy_id=target_enemy.agent_id,
                                        enemy_name=target_enemy.name,
                                        action_type=action_type,
                                        skill=skill,
                                        roll_total=resolution.total if resolution else 0,
                                        dc=resolution.difficulty if resolution else 20,
                                        success=resolution.success if resolution else True,
                                        margin=resolution.margin if resolution else 10,
                                        outcome="flee",
                                        narration=narration[:500]  # Truncate to 500 chars
                                    )
                            else:
                                logger.warning(f"Could not find enemy '{enemy_name}' to mark as fled")

            # Queue clock advancements (will be applied batch during synthesis to prevent cascades)
            for clock_name, ticks, reason, source in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    mechanics.queue_clock_update(clock_name, ticks, reason)
                    logger.debug(f"Queued: {clock_name} {ticks:+d} ({reason}) [source: {source}]")

            # Apply void changes (both gains and reductions)
            if state_changes['void_change'] != 0:
                # Track void change for round summary
                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_void_change(state_changes['void_change'])

                # Check if void change targets a different character (collaborative cleansing)
                target_character_name = state_changes.get('void_target_character')
                if target_character_name:
                    # Find target character's player_id by character name
                    target_player_id = None
                    for pid, char_state in mechanics.character_states.items():
                        if hasattr(char_state, 'name') and char_state.name == target_character_name:
                            target_player_id = pid
                            break

                    if target_player_id:
                        void_state = mechanics.get_void_state(target_player_id)
                        target_name = target_character_name
                    else:
                        # Couldn't find target, fall back to acting character
                        logger.warning(f"Could not find target character '{target_character_name}' for void change, applying to actor")
                        void_state = mechanics.get_void_state(player_id)
                        target_name = action.get('character', player_id)
                else:
                    # Default: apply to acting character
                    void_state = mechanics.get_void_state(player_id)
                    target_name = action.get('character', player_id)

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
                        narration += f"\n\n⚫ Void ({target_name}): {old_void} → {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"
                else:
                    # Void reduction (recovery moves)
                    void_state.reduce_void(
                        abs(state_changes['void_change']),
                        ", ".join(state_changes['void_reasons'])
                    )
                    # Show void decrease if it actually changed
                    if void_state.score != old_void:
                        narration += f"\n\n⚫ Void ({target_name}): {old_void} ↓ {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"

                # Check for Eye of Breach appearance on high void
                eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                if eye_of_breach_event:
                    narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            if state_changes.get('soulcredit_change', 0) != 0:
                sc_state = mechanics.get_soulcredit_state(player_id)
                old_sc = sc_state.score
                reasons_text = ', '.join(state_changes.get('soulcredit_reasons', []))
                sc_state.adjust(state_changes['soulcredit_change'], reasons_text)
                # Show SC change to the affected player only (private knowledge)
                # Other players do NOT see each other's soulcredit (asymmetric information)
                if sc_state.score != old_sc:
                    narration += f"\n\n⚖️ Soulcredit: {old_sc} → {sc_state.score} ({reasons_text})"

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
                        logger.debug(f"Updated {player_id} position: {old_position} → {new_position}")
                        # Position change is already in narration from DM, no need to add here
                    except Exception as e:
                        logger.error(f"Failed to update player position: {e}")

        return {
            'resolution': resolution,
            'narration': narration,
            'state_changes': state_changes,  # Include state_changes for logging
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

            # CRITICAL: Resolve target IDs to character names for void cleansing
            # In free targeting mode, actions have target_enemy="tgt_xxxx" but outcome parser needs target_character="Name"
            if action.get('target_enemy') and action['target_enemy'].startswith('tgt_'):
                target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                if target_id_mapper and target_id_mapper.enabled:
                    target_entity = target_id_mapper.resolve_target(action['target_enemy'])
                    # If targeting a PC, populate target_character for void cleansing mechanics
                    if target_entity and target_id_mapper.is_player(action['target_enemy']):
                        if hasattr(target_entity, 'character_state') and hasattr(target_entity.character_state, 'name'):
                            action['target_character'] = target_entity.character_state.name
                            logger.debug(f"Resolved target ID {action['target_enemy']} → character '{action['target_character']}' for void cleansing")

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

            # Queue clock advancements (will be applied batch during synthesis to prevent cascades)
            for clock_name, ticks, reason, source in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    mechanics.queue_clock_update(clock_name, ticks, reason)
                    logger.debug(f"Queued: {clock_name} {ticks:+d} ({reason}) [source: {source}]")

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
                # Track void change for round summary
                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_void_change(state_changes['void_change'])

                # Check if void change targets a different character (collaborative cleansing)
                target_character_name = state_changes.get('void_target_character')
                if target_character_name:
                    # Find target character's player_id by character name
                    target_player_id = None
                    for pid, char_state in mechanics.character_states.items():
                        if hasattr(char_state, 'name') and char_state.name == target_character_name:
                            target_player_id = pid
                            break

                    if target_player_id:
                        void_state = mechanics.get_void_state(target_player_id)
                        target_name = target_character_name
                    else:
                        # Couldn't find target, fall back to acting character
                        logger.warning(f"Could not find target character '{target_character_name}' for void change, applying to actor")
                        void_state = mechanics.get_void_state(player_id)
                        target_name = action.get('character', player_id)
                else:
                    # Default: apply to acting character
                    void_state = mechanics.get_void_state(player_id)
                    target_name = action.get('character', player_id)

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
                        narration += f"\n\n⚫ Void ({target_name}): {old_void} → {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"
                else:
                    # Void reduction (recovery moves)
                    void_state.reduce_void(
                        abs(state_changes['void_change']),
                        ", ".join(state_changes['void_reasons'])
                    )
                    # Show void decrease if it actually changed
                    if void_state.score != old_void:
                        narration += f"\n\n⚫ Void ({target_name}): {old_void} ↓ {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"

                # Check for Eye of Breach appearance on high void
                eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                if eye_of_breach_event:
                    narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            if state_changes.get('soulcredit_change', 0) != 0:
                sc_state = mechanics.get_soulcredit_state(player_id)
                old_sc = sc_state.score
                reasons_text = ', '.join(state_changes.get('soulcredit_reasons', []))
                sc_state.adjust(state_changes['soulcredit_change'], reasons_text)
                # Show SC change to the affected player only (private knowledge)
                # Other players do NOT see each other's soulcredit (asymmetric information)
                if sc_state.score != old_sc:
                    narration += f"\n\n⚖️ Soulcredit: {old_sc} → {sc_state.score} ({reasons_text})"

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
                        logger.debug(f"Updated {player_id} position: {old_position} → {new_position}")
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
                log_context = {
                    "action_type": action_type,
                    "is_ritual": action.get('is_ritual', False),
                    "faction": action.get('faction', 'Unknown'),
                    "description": action.get('description', ''),
                    "narration": llm_narration,
                    "is_free_action": action.get('is_free_action', False)
                }

                # Add prompt metadata if available
                if hasattr(self, '_last_prompt_metadata') and self._last_prompt_metadata:
                    log_context["prompt_metadata"] = self._last_prompt_metadata.to_dict()

                mechanics.jsonl_logger.log_action_resolution(
                    round_num=mechanics.current_round,
                    phase="resolve",
                    agent_name=character_name,
                    action=intent,
                    resolution=resolution,
                    economy_changes=economy_changes,
                    clock_states=clock_states,
                    effects=effects,
                    context=log_context
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

    def _build_dm_narration_prompt(
        self,
        is_dialogue: bool,
        scenario_context: str,
        character_context: str,
        resolution_context: str,
        tactical_combat_context: str,
        clock_context: str,
        void_level: int,
        void_impact: str,
        outcome_guidance: str,
        description: str,
        action_type: str,
        enemy_spawn_instructions: str = "",
        party_context: str = "",
        character_name: str = "",
        target_character: str = ""
    ) -> str:
        """
        Build DM narration prompt using prompt_loader system.

        Handles both PC-to-PC dialogue and standard action narration.
        Stores prompt metadata in self._last_prompt_metadata for logging.
        """
        if is_dialogue:
            # PC-to-PC dialogue path
            prompt_parts = []
            prompt_parts.append("You are the Dungeon Master for an Aeonisk YAGS game session.")
            prompt_parts.append("")

            if scenario_context:
                prompt_parts.append(scenario_context)
            if party_context:
                prompt_parts.append(party_context)
            if enemy_spawn_instructions:
                prompt_parts.append(enemy_spawn_instructions)
            if character_context:
                prompt_parts.append(character_context)
            if resolution_context:
                prompt_parts.append(resolution_context)

            prompt_parts.append(f"\nPlayer Action: {description}")
            prompt_parts.append(f"Action Type: {action_type} (DIALOGUE with {target_character})")

            if void_impact:
                prompt_parts.append(void_impact)
            if tactical_combat_context:
                prompt_parts.append(tactical_combat_context)

            # Add dialogue task template
            variables = {
                "initiating_character": character_name,
                "target_character": target_character
            }

            loaded_prompt = load_agent_prompt(
                agent_type="dm",
                provider="claude",
                language="en",
                section="dialogue_task",
                variables=variables
            )

            prompt_parts.append("")
            prompt_parts.append(loaded_prompt.content)

            self._last_prompt_metadata = loaded_prompt.metadata
            return "\n".join(prompt_parts)

        else:
            # Standard narration path - compose multiple sections
            prompt_parts = []
            prompt_parts.append("You are the Dungeon Master for an Aeonisk YAGS game session.")
            prompt_parts.append("")

            if scenario_context:
                prompt_parts.append(scenario_context)
            if enemy_spawn_instructions:
                prompt_parts.append(enemy_spawn_instructions)
            if character_context:
                prompt_parts.append(character_context)
            if resolution_context:
                prompt_parts.append(resolution_context)

            prompt_parts.append(f"\nPlayer Action: {description}")
            prompt_parts.append(f"Action Type: {action_type}")

            if void_impact:
                prompt_parts.append(void_impact)
            if tactical_combat_context:
                prompt_parts.append(tactical_combat_context)
            if clock_context:
                prompt_parts.append(clock_context)

            # Add narration task template with outcome guidance
            variables = {
                "void_level": str(void_level),
                "outcome_guidance": outcome_guidance
            }

            loaded_prompt = load_agent_prompt(
                agent_type="dm",
                provider="claude",
                language="en",
                section="narration_task",
                variables=variables
            )

            prompt_parts.append("")
            prompt_parts.append(loaded_prompt.content)

            self._last_prompt_metadata = loaded_prompt.metadata
            return "\n".join(prompt_parts)

    async def _retry_invalid_markers(
        self,
        marker_type: str,
        invalid_markers: List[str],
        round_num: int
    ) -> str:
        """
        Ask DM to properly format incomplete markers.

        Args:
            marker_type: "SPAWN_ENEMY" or "ADVANCE_STORY"
            invalid_markers: List of incomplete marker contents
            round_num: Current round number

        Returns:
            LLM response with corrected markers
        """

        if marker_type == "SPAWN_ENEMY":
            format_spec = """
REQUIRED FORMAT (ALL 5 FIELDS):
[SPAWN_ENEMY: name | template | count | position | tactics]

**Templates:** grunt, elite, sniper, boss, void_cultist, enforcer
**Positions:** Near-Enemy, Far-Enemy, Engaged
**Tactics:** aggressive_melee, aggressive_ranged, defensive, support
**Count:** 1 or 2 only

Example:
[SPAWN_ENEMY: Freeborn Raiders | grunt | 2 | Far-Enemy | aggressive_ranged]
"""
        elif marker_type == "ADVANCE_STORY":
            format_spec = """
REQUIRED FORMAT (2 FIELDS):
[ADVANCE_STORY: new_location | new_situation]

Example:
[ADVANCE_STORY: Abandoned Warehouse District | The team tracks the raiders to their hideout, preparing for final confrontation]
"""
        else:
            logger.error(f"Unknown marker type: {marker_type}")
            return ""

        retry_prompt = f"""
You generated incomplete {marker_type} markers. Please provide the COMPLETE format for each:

INVALID MARKERS:
{chr(10).join(f'- [{marker_type}: {m}]' for m in invalid_markers)}

{format_spec}

Provide ONLY the corrected markers, one per line. No narrative or explanation.
"""

        # Log retry attempt to JSONL
        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_marker_retry(
                round_num=round_num,
                marker_type=marker_type,
                invalid_markers=invalid_markers,
                retry_prompt=retry_prompt
            )

        # Get LLM config
        provider = self.llm_config.get('provider', 'openai')
        model = self.llm_config.get('model', 'gpt-4')

        # Call LLM with lower temperature for format compliance
        from .llm_provider import get_provider
        llm_client = get_provider(provider, model)

        response = await llm_client.generate_async(
            prompt=retry_prompt,
            temperature=0.3,  # Lower temp for format compliance
            max_tokens=300
        )

        # Log retry result to JSONL
        success = len(response.strip()) > 0
        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_marker_retry_result(
                round_num=round_num,
                marker_type=marker_type,
                retry_response=response,
                success=success
            )

        logger.info(f"Retry response for {marker_type}: {response[:200]}")
        return response

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
- **Escape (Major)**: Move beyond Extreme-PC to flee combat entirely (Athletics DC 20, only from Extreme-PC or Far-PC)

**DAMAGE SYSTEM** - When players attack enemies:
If player ACTION includes TARGET_ENEMY field and succeeds at Combat check:
1. Roll weapon damage (typically 2d6+4 for rifles, 1d6+3 for pistols, 1d6+Str for melee)
2. Enemy soaks 12 damage (base Soak for human-sized targets)
3. Include damage triplet in your narration: `Damage: X → Soak: 12 → Final: Y`
   - Example: "Your shot hits center mass. Damage: 18 → Soak: 12 → Final: 6"
   - On miss or failure: Don't include triplet, just narrate the miss

**CREATIVE TACTICS CAN DEAL DAMAGE** - Not just combat actions!
Players using social manipulation, hacking, or environmental tactics can deal damage with high-margin successes:

1. **Social Manipulation** (Corporate Influence, Charm, Intimidation against enemies):
   - Margin 15+: 10 damage (void corruption backlash from confusion)
   - Margin 10-14: 7 damage (void corruption backlash)
   - Margin 5-9: 5 damage (mild void corruption backlash)
   - Example: "Your corporate authority overwhelms the Void Parasite's corrupted mind. Damage: 10 → Soak: 12 → Final: 0 (but confused for 1 round)"

**💬 SOCIAL DE-ESCALATION (INTIMIDATION/PERSUASION):**
When player attempts to intimidate or persuade enemies mid-combat:
- **Check player's tactical advantage**: Numbers advantage? Enemy wounded? Allies down?
- **Check enemy personality**: Grunts surrender more easily, elites/leaders resist, void-possessed/fanatics immune
- **Roll Intimidation (Charisma) or Persuasion (Empathy) vs DC 15-25**
  - DC 15: Enemy severely wounded (<25% HP), morale already broken
  - DC 20: Enemy at disadvantage (outnumbered, cornered, allies down)
  - DC 25: Enemy still confident, not desperate

**On Success:**
- **Exceptional/Critical (Margin 10+)**: Enemy immediately surrenders or flees
  - Narrate: Enemy drops weapon, raises hands, begs for mercy OR enemy panics and runs
  - Mark with: 🏳️ [ENEMY_SURRENDER: EnemyName] or 🏃 [ENEMY_FLEE: EnemyName]
  - Example: "The smuggler's rifle clatters to the floor, hands raised high. 'I yield! Don't shoot!' 🏳️ [ENEMY_SURRENDER: Smuggler-2]"

- **Good/Marginal (Margin 0-9)**: Enemy hesitates, forced morale check
  - Narrate: Enemy wavers, looks at exits, checks fallen allies
  - Apply morale penalty: -5 to enemy's next morale check
  - Example: "The debt collector's hands shake, eyes darting to his unconscious partner. He backs toward the door but doesn't drop his weapon yet."

**On Failure:**
- Enemy rallies, may become emboldened (+5 morale bonus)
- Narrate: Enemy laughs off threat, taunts player, attacks with renewed vigor
- Example: "The cultist just grins, void energy crackling around him. 'Your threats mean NOTHING!' He charges forward with fanatical fury."

**Enemy Types & Resistance:**
- Grunts/Thugs: Easily intimidated (standard DC)
- Elites/Leaders: Resistant (+5 DC)
- Void-Possessed/Fanatics: IMMUNE (automatically fail, may trigger attack)
- Coerced/Desperate: Very susceptible (-5 DC)

**Context Modifiers:**
- Player wielding lethal weapon at close range: -2 DC (more threatening)
- Multiple enemies already down: -5 DC (morale broken)
- Enemy cornered/no escape: -3 DC (desperate)
- Enemy is last survivor: -5 DC (isolated)

2. **Hacking** (Systems, Engineering to override/disable tech enemies):
   - Turn against others (Margin 15+): 12 damage (enemy attacks ally)
   - Turn against others (Margin 10-14): 8 damage (brief friendly fire)
   - Overload/disable (Margin 15+): 10 damage (catastrophic system failure)
   - Overload/disable (Margin 10-14): 7 damage (internal damage)
   - Overload/disable (Margin 5-9): 5 damage (forced shutdown)
   - Example: "You hack the Corrupted Scanner, forcing it to target the Void Tendrils. Damage: 8 → Soak: 12 → Final: 0 (but disrupted)"

3. **Environmental** (Awareness, Systems to trigger hazards):
   - Margin 15+: 15 damage AoE (catastrophic hazard)
   - Margin 10-14: 12 damage AoE (significant hazard)
   - Margin 5-9: 10 damage AoE (moderate hazard)
   - Example: "You overload the power conduits. All enemies in Near-Enemy take: Damage: 12 → Soak: 12 → Final: 0"

**WHY**: Players want creative tactics to feel impactful, not just debuffs. High-margin successes should reward creativity.

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
- Apply range modifiers to attacks based on positions
- **Escape attempts**: Athletics DC 20 (or harder in pursuit scenarios)
  * Success: Player flees combat → [POSITION: ESCAPED] → Remove from combat tracking
  * Failure: Player remains at current position, turn wasted
  * Critical success (margin 10+): Clean getaway, no pursuit possible
  * Must be at Far-PC or Extreme-PC to attempt (can't escape from melee)"""

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
                    clock_context += "\n\n**EXPLICIT STATE MARKERS** - Mark state changes at the end of your narration:\n"
                    clock_context += "\n📊 [Clock Name]: +X or -X (reason) - Advance/regress a scene clock"
                    clock_context += "\n⚫ Void: +X (reason) - Character gains void corruption"
                    clock_context += "\n⚖️ Soulcredit: +X or -X (reason) - Character's spiritual trust/morality changes"
                    clock_context += "\n\nExamples:"
                    clock_context += "\n  📊 Evidence Collection: +2 (found hidden documents)"
                    clock_context += "\n  ⚫ Void: +1 (ritual backfire)"
                    clock_context += "\n  ⚖️ Soulcredit: +0 (neutral combat action)"
                    clock_context += "\n  ⚖️ Soulcredit: -2 (deceived officials)"
                    clock_context += "\n\n**CRITICAL:** Soulcredit tracks trustworthiness/morality, NOT success."
                    clock_context += "\n**ALWAYS mark soulcredit for every action, even when +0 (neutral).**"
                    clock_context += "\n\nSC Scoring Rules (consider CONTEXT and INTENT):"
                    clock_context += "\n  • Combat CONTEXT matters:"
                    clock_context += "\n    - Fighting justified enemies: ⚖️ Soulcredit: +0 (neutral combat)"
                    clock_context += "\n    - Fighting own faction/allies: ⚖️ Soulcredit: -2 (betrayal)"
                    clock_context += "\n    - Attacking innocents/excessive force: ⚖️ Soulcredit: -1 to -3 (unjust violence)"
                    clock_context += "\n    - Protecting innocents in combat: ⚖️ Soulcredit: +1 (protective action)"
                    clock_context += "\n  • Deception INTENT matters:"
                    clock_context += "\n    - Lying for personal gain: ⚖️ Soulcredit: -1 to -2 (selfish deception)"
                    clock_context += "\n    - Lying to protect innocents: ⚖️ Soulcredit: +0 or +1 (complex morality)"
                    clock_context += "\n    - Fraud/identity theft: ⚖️ Soulcredit: -2 (serious deception)"
                    clock_context += "\n  • Neutral actions: ⚖️ Soulcredit: +0"
                    clock_context += "\n    - Exploration, investigation, normal purchases, following protocols"
                    clock_context += "\n  • Success/failure doesn't determine SC - only moral choice matters"
                    clock_context += "\n\nExamples (showing moral complexity):"
                    clock_context += "\n  • Shooting hostile Tempest operatives: ⚖️ Soulcredit: +0 (justified combat)"
                    clock_context += "\n  • Attacking own Pantheon allies: ⚖️ Soulcredit: -2 (betrayal of faction)"
                    clock_context += "\n  • Lying to save innocent bystanders: ⚖️ Soulcredit: +0 (morally complex, protective intent)"
                    clock_context += "\n  • Lying for profit/personal gain: ⚖️ Soulcredit: -1 (selfish deception)"
                    clock_context += "\n  • Creating Hollow Seeds: ⚖️ Soulcredit: -2 (created illicit commodity)"
                    clock_context += "\n  • Fulfilling contracts honorably: ⚖️ Soulcredit: +1 (upheld agreement)"
                    clock_context += "\n  • Protecting civilians in crossfire: ⚖️ Soulcredit: +1 (selfless protection)"
                    clock_context += "\n  • Breaking sworn oaths: ⚖️ Soulcredit: -2 (broke sworn word)"
                    clock_context += "\n  • Excessive force on defeated foe: ⚖️ Soulcredit: -1 (unjust violence)"
                    clock_context += "\n  • Normal investigation/exploration: ⚖️ Soulcredit: +0 (neutral action)"

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

        # Build party context for dialogue scenarios
        party_context = ""
        if is_dialogue_with_pc and target_character:
            if self.shared_state:
                registered_players = self.shared_state.registered_players
                party_members = [f"{p.get('name')} ({p.get('faction', 'Unknown')})" for p in registered_players]
                party_context = f"\n**Party Members (ALL DIFFERENT CHARACTERS):**\n" + "\n".join([f"  - {member}" for member in party_members])
                party_context += f"\n\n**IMPORTANT**: {character_name if action else 'The character'} and {target_character} are TWO SEPARATE people in the same party."

        # Build prompt using prompt_loader system
        prompt = self._build_dm_narration_prompt(
            is_dialogue=is_dialogue_with_pc and target_character is not None,
            scenario_context=scenario_context,
            character_context=character_context,
            resolution_context=resolution_context,
            tactical_combat_context=tactical_combat_context,
            clock_context=clock_context,
            void_level=void_level,
            void_impact=void_impact,
            outcome_guidance=outcome_guidance,
            description=description,
            action_type=action_type,
            enemy_spawn_instructions=enemy_spawn_instructions,
            party_context=party_context,
            character_name=character_name if action else "The character",
            target_character=target_character if target_character else ""
        )

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
                response = await asyncio.to_thread(
                    self.llm_client.messages.create,
                    model=model,
                    max_tokens=400,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}]
                )
                narration = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=narration,
                        model=model,
                        temperature=temperature,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

                return narration

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
                response = await asyncio.to_thread(
                    self.llm_client.messages.create,
                    model=model,
                    max_tokens=150,
                    temperature=0.8,
                    messages=[{"role": "user", "content": prompt}]
                )
                consequence = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=consequence,
                        model=model,
                        temperature=0.8,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

                return consequence
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
                response = await asyncio.to_thread(
                    self.llm_client.messages.create,
                    model=model,
                    max_tokens=200,
                    temperature=0.85,
                    messages=[{"role": "user", "content": prompt}]
                )
                event_text = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=event_text,
                        model=model,
                        temperature=0.85,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )
                    self.llm_logger.call_count += 1

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