#!/usr/bin/env python3
"""
Enhanced Aeonisk YAGS Multi-Agent System

Uses actual family names, locations, and equipment from the lore,
with realistic YAGS difficulty scaling and advanced tech/robots.
"""

import asyncio
import json
import yaml
import random
import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the vectorstore system
from vectorstore_system import AeoniskVectorStore

try:
    import aiohttp
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# Actual family lines from the Aeonisk lore
FAMILY_LINES = {
    'Sovereign Nexus': {
        'Elaras': {'reputation': 'rising', 'specialty': 'harmony_rituals', 'breath': 'Harmony'},
        'Halessan': {'reputation': 'stable', 'specialty': 'civic_duty', 'breath': 'Authority'}, 
        'Ireveth': {'reputation': 'stable', 'specialty': 'enforcement', 'breath': 'Order'},
        'Nymir': {'reputation': 'mysterious', 'specialty': 'surveillance', 'breath': 'Sight'},
        'Gaze': {'reputation': 'secretive', 'specialty': 'intelligence', 'breath': 'Knowledge'}
    },
    'Astral Commerce Group': {
        'Kythea': {'reputation': 'rising', 'specialty': 'futures_trading', 'breath': 'Profit'},
        'Exchange': {'reputation': 'stable', 'specialty': 'contract_law', 'breath': 'Balance'},
        'Ossai': {'reputation': 'stable', 'specialty': 'ley_navigation', 'breath': 'Journey'}
    },
    'Tempest Industries': {
        'Karsel': {'reputation': 'disgraced', 'specialty': 'void_research', 'breath': 'Innovation'},
        'Xalith': {'reputation': 'mysterious', 'specialty': 'void_engines', 'breath': 'Transgression'}
    },
    'Arcane Genetics': {
        'Vireya': {'reputation': 'stable', 'specialty': 'bio_enhancement', 'breath': 'Evolution'},
        'Catalyst': {'reputation': 'rising', 'specialty': 'mutation_control', 'breath': 'Change'},
        'Thaurin': {'reputation': 'ancient', 'specialty': 'emotional_resonance', 'breath': 'Feeling'}
    },
    'Resonance Communes': {
        'Breath': {'reputation': 'spiritual', 'specialty': 'communion_rites', 'breath': 'Unity'},
        'Seed': {'reputation': 'nurturing', 'specialty': 'growth_rituals', 'breath': 'Potential'}
    },
    'Freeborn': {
        'Unbound': {'reputation': 'variable', 'specialty': 'independence', 'breath': 'Freedom'},
        'Wild-Current': {'reputation': 'variable', 'specialty': 'natural_harmony', 'breath': 'Flow'}
    }
}

GIVEN_NAMES = [
    'Irele', 'Zara', 'Echo', 'Kaelen', 'Varis', 'Liora', 'Wren', 'Nyx',
    'Thane', 'Riven', 'Vera', 'Magnus', 'Cira', 'Dex', 'Nova', 'Kael',
    'Aria', 'Soren', 'Lyra', 'Daven', 'Mira', 'Jorin', 'Kessa', 'Vale'
]

# Authentic Aeonisk locations from the lore
AEONISK_LOCATIONS = [
    {
        'name': 'Central Sanctum, Aeonisk Prime',
        'type': 'government',
        'description': 'Heart of the Sovereign Nexus with crystalline ley-conductors webbing alabaster spires'
    },
    {
        'name': 'Port Gale-Spire, Arcadia',
        'type': 'spaceport',
        'description': 'Biotech customs hub where cargo signatures get soft-laundered'
    },
    {
        'name': 'Port Eidolon, Nimbus',
        'type': 'spaceport',
        'description': 'Rogue engineer paradise with Vox broadcast temples and surveillance networks'
    },
    {
        'name': 'ACG Futures Market Exchange, Aeonisk Prime High Spire',
        'type': 'commercial',
        'description': 'Gleaming trade center where Soulcredit futures are bought and sold'
    },
    {
        'name': 'Forge-Station K-27, Arcadia Orbit',
        'type': 'industrial',
        'description': 'Gene-temples and Seed arboreta orbiting the lush biotech world'
    },
    {
        'name': 'Public Plaza 94, Aeonisk Prime',
        'type': 'civic',
        'description': 'Citizens check Soulcredit at public kiosks under Choir-class ferries'
    },
    {
        'name': 'Resonance Temple Complex, Nimbus',
        'type': 'spiritual',
        'description': 'Sacred bonding chambers where spiritual connections are forged'
    },
    {
        'name': 'Biocreche Facility Alpha, Arcadia',
        'type': 'medical',
        'description': 'Pod gestation chambers where Echo Children are born from Matron Bonds'
    },
    {
        'name': 'Outer Beacon Array Σ',
        'type': 'frontier',
        'description': 'Remote monitoring station on the edge of known space'
    },
    {
        'name': 'The Veil Transit Hub',
        'type': 'transport',
        'description': 'Dangerous ley-line nexus where reality signatures become unstable'
    }
]


@dataclass
class PersonalityProfile:
    """Character personality that drives interactions."""
    risk_tolerance: int = 5
    void_curiosity: int = 3  
    authority_respect: int = 5
    family_loyalty: int = 7
    pragmatism: int = 5
    social_preference: int = 5
    innovation_drive: int = 5
    
    # Team interaction traits
    team_cooperation: int = 5
    leadership_drive: int = 5
    trust_others: int = 5


@dataclass
class AeoniskEquipment:
    """Rich Aeonisk equipment with robots and advanced tech."""
    name: str
    item_type: str  # weapon, armor, accessory, talisman, robot, vehicle
    class_type: str  # bonded, glyph, void, spirit, contract, conventional
    effect: str
    upkeep: str
    void_risk: int = 0
    soulcredit_requirement: int = 0
    spark_cost: int = 0


@dataclass
class AeoniskCharacter:
    """Character with authentic family names and equipment."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    family_reputation: str
    family_breath: str  # The spiritual focus of their line
    personal_motivation: str
    personality: PersonalityProfile = field(default_factory=PersonalityProfile)
    
    # YAGS Attributes
    strength: int = 3
    health: int = 3
    agility: int = 3
    dexterity: int = 3
    perception: int = 3
    intelligence: int = 3
    empathy: int = 3
    willpower: int = 3
    
    # Aeonisk mechanics
    void_score: int = 0
    soulcredit: int = 0
    bonds: List[str] = field(default_factory=list)
    
    # Skills
    athletics: int = 2
    awareness: int = 2
    brawl: int = 2
    charm: int = 2
    guile: int = 2
    stealth: int = 2
    astral_arts: int = 0
    corporate_influence: int = 0
    hacking: int = 0
    
    # Equipment
    equipment: List[AeoniskEquipment] = field(default_factory=list)
    current_sparks: int = 5
    current_drips: int = 10


class EnhancedEquipmentGenerator:
    """Generates authentic Aeonisk equipment including robots and advanced tech."""
    
    EQUIPMENT_CATALOG = [
        # Weapons from lore
        AeoniskEquipment("Mnemonic Blade", "weapon", "bonded", "+3 DMG, +2 when trauma invoked", "Re-ink sigils monthly", 0, 0, 0),
        AeoniskEquipment("Shrike Cannon", "weapon", "glyph", "+4 DMG, ignores ritual shields", "Glyph stabilizer monthly", 0, 0, 2),
        AeoniskEquipment("Debtbreaker Sidearm", "weapon", "contract", "+2 DMG, fires track-tags", "Codex ping per shot", 0, 0, 1),
        AeoniskEquipment("Wraithroot Vineblade", "weapon", "spirit", "+1 DMG, +2 vs defending Bond", "Water with Drip", 0, 0, 0),
        AeoniskEquipment("Hollowed Repeater", "weapon", "void", "Damage scales with Void score", "Accuracy drops if Bonds > 0", 1, 0, 0),
        AeoniskEquipment("Oathpiercer Carbine", "weapon", "conventional", "+2 DMG vs ex-Bonds", "Ethically suspect", 0, 0, 0),
        AeoniskEquipment("Sparkspike Dagger", "weapon", "bonded", "+2 DMG, +1 DEF if duel", "Re-spark daily", 0, 0, 1),
        
        # Armor from lore
        AeoniskEquipment("Sovereign Sanctum Mantle", "armor", "bonded", "+4 Soak, blocks ritual tracking", "Monthly oath rite", 0, 0, 0),
        AeoniskEquipment("Resonant Shell Weave", "armor", "glyph", "+3 Soak, -2 energy damage", "Cracks add +1 Void", 0, 0, 1),
        AeoniskEquipment("Tempest Tactical Skin", "armor", "contract", "+3 Soak, breach ping if torn", "Requires Soulcredit ≥ 0", 0, 0, 0),
        AeoniskEquipment("Voidshroud Drape", "armor", "void", "+2 Soak, phase-shift defense", "Wears +1 Void/hour", 1, 0, 0),
        AeoniskEquipment("Echo-Lattice Gown", "armor", "spirit", "+1 Soak, +1 DEF when True Will", "Nightly dream quest", 0, 0, 0),
        
        # Accessories and sensors
        AeoniskEquipment("Leyshade Visor", "accessory", "sensor", "Reveals hidden glyphs/Bonds", "1 Breath use, +1 Void in dreamspace", 1, 0, 0),
        AeoniskEquipment("Multi-Bind Sheath", "accessory", "bracer", "Quick-swap 4 Talismans", "1 Spark/day to bond", 0, 0, 1),
        AeoniskEquipment("Soulcredit Tag", "accessory", "civic", "Broadcasts ledger status", "+1 Void per forged sync", 0, -2, 0),
        AeoniskEquipment("Echo-Calibrator", "accessory", "tool", "Stabilizes Raw Seeds in rituals", "1 Drip per 3 uses", 0, 0, 0),
        AeoniskEquipment("Resonance Aligner", "accessory", "glyph", "Calibrated to pilot's Soulcredit", "Spark maintenance", 0, 0, 1),
        
        # Robots and Companions (from gear reference)
        AeoniskEquipment("Static (Dust-Bot)", "robot", "conventional", "Archive companion, data analysis", "Basic maintenance", 0, 0, 0),
        AeoniskEquipment("Confessor Unit", "robot", "void", "Void breach hunter, reality stabilizer", "High void exposure risk", 2, 0, 5),
        AeoniskEquipment("Compact Drone Halo", "robot", "contract", "Auto-deploy shield, +3 Soak", "1 Spark/hr, Soulcredit ≥ -2", 0, -2, 1),
        AeoniskEquipment("Voidcradle Anti-Ritual Bot", "robot", "void", "Disrupts hostile rituals", "Illegal in most zones", 1, 0, 3),
        AeoniskEquipment("Choir-Class Escort Drone", "robot", "bonded", "Navigation and protection", "Bond oath required", 0, 1, 2),
        AeoniskEquipment("Memory Glass Archive", "robot", "glyph", "Stores encrypted echoes", "Glyph refresh cycle", 0, 0, 1),
        
        # Talismans and Special Items
        AeoniskEquipment("Raw Seed (Unstable)", "talisman", "void", "Becomes elemental when attuned", "Degrades in 7 cycles, +1 Void if raw", 1, 0, 0),
        AeoniskEquipment("Harmony Crystal", "talisman", "spirit", "Enhances unity rituals", "Monthly purification", 0, 0, 0),
        AeoniskEquipment("Unity Sigil", "talisman", "bonded", "Strengthens team bonds", "Requires shared ritual", 0, 1, 0),
        AeoniskEquipment("Void Shard", "talisman", "void", "Amplifies void manipulation", "Constant +1 Void risk", 1, 0, 0),
        AeoniskEquipment("Freedom Stone", "talisman", "spirit", "Breaks unwanted bonds", "Absorbs negative emotions", 0, 0, 0),
        AeoniskEquipment("Astral Lodestone", "talisman", "glyph", "Fossilized Seed, ley navigation", "Route-specific attunement", 0, 0, 1),
        AeoniskEquipment("Dream Ring", "talisman", "spirit", "Navigate psychic hazards", "Dream-state maintenance", 0, 0, 0),
        AeoniskEquipment("Covenant Ring", "talisman", "bonded", "First Soulcredit imprint", "Ceremonial significance", 0, 0, 0),
        
        # Vehicles and Advanced Tech
        AeoniskEquipment("Choir-Class Ferry", "vehicle", "bonded", "Silent glide transport", "Harmony frequency maintenance", 0, 1, 3),
        AeoniskEquipment("Voidcore Engine", "vehicle", "void", "Reality-breaking propulsion", "Requires broken Bond to activate", 2, 0, 10),
        AeoniskEquipment("Resonance Commune Pod", "vehicle", "spirit", "Group travel vessel", "Emotional sync required", 0, 0, 2),
        AeoniskEquipment("ACG Trade Hauler", "vehicle", "contract", "Commercial cargo transport", "Valid contracts required", 0, 0, 4)
    ]
    
    @classmethod
    def generate_starting_equipment(cls, character: AeoniskCharacter) -> List[AeoniskEquipment]:
        """Generate appropriate equipment based on character and family."""
        equipment = []
        
        # Everyone gets basic gear
        equipment.append(AeoniskEquipment("Personal Commlink", "accessory", "conventional", "Standard communication", "None", 0, 0, 0))
        
        # Family line specific equipment based on Breath
        if character.family_breath == 'Harmony':
            equipment.append(AeoniskEquipment("Harmony Crystal", "talisman", "spirit", "Unity rituals", "Monthly purification", 0, 0, 0))
        elif character.family_breath == 'Authority':
            equipment.append(AeoniskEquipment("Covenant Ring", "talisman", "bonded", "Authority symbol", "Ceremonial upkeep", 0, 0, 0))
        elif character.family_breath == 'Sight':
            equipment.append(AeoniskEquipment("Leyshade Visor", "accessory", "sensor", "Reveals hidden patterns", "Void risk in use", 1, 0, 0))
        elif character.family_breath == 'Innovation':
            equipment.append(AeoniskEquipment("Static (Dust-Bot)", "robot", "conventional", "Data analysis companion", "Basic maintenance", 0, 0, 0))
        elif character.family_breath == 'Evolution':
            equipment.append(AeoniskEquipment("Echo-Calibrator", "accessory", "tool", "Bio-modification support", "Organic components", 0, 0, 0))
        
        # Faction-specific gear
        if character.origin_faction == 'Sovereign Nexus':
            if character.soulcredit >= 0:
                equipment.append(AeoniskEquipment("Sovereign Sanctum Mantle", "armor", "bonded", "+4 Soak, blocks tracking", "Monthly oath", 0, 0, 0))
        
        elif character.origin_faction == 'Tempest Industries':
            equipment.append(AeoniskEquipment("Crypto Commlink", "accessory", "glyph", "Encrypted communication", "Glyph refresh", 0, 0, 1))
            if character.void_score >= 1 and character.current_sparks >= 3:
                equipment.append(AeoniskEquipment("Voidcradle Anti-Ritual Bot", "robot", "void", "Ritual disruption", "Illegal, void risk", 1, 0, 3))
        
        elif character.origin_faction == 'Astral Commerce Group':
            equipment.append(AeoniskEquipment("Soulcredit Tag", "accessory", "civic", "Ledger broadcast", "Forgery +1 Void", 0, -2, 0))
            if character.corporate_influence >= 3:
                equipment.append(AeoniskEquipment("Debtbreaker Sidearm", "weapon", "contract", "Track-tags", "Codex ping", 0, 0, 1))
        
        elif character.origin_faction == 'Arcane Genetics':
            equipment.append(AeoniskEquipment("Bio-Scanner", "accessory", "sensor", "Genetic analysis", "Bio sample refresh", 0, 0, 0))
            equipment.append(AeoniskEquipment("Echo-Calibrator", "accessory", "tool", "Seed stabilization", "1 Drip per 3 uses", 0, 0, 0))
        
        # Add weapon based on skills and sparks
        if character.astral_arts >= 3:
            equipment.append(AeoniskEquipment("Wraithroot Vineblade", "weapon", "spirit", "+1 DMG, Bond defense", "Water with Drip", 0, 0, 0))
        elif character.hacking >= 3 and character.current_sparks >= 2:
            equipment.append(AeoniskEquipment("Shrike Cannon", "weapon", "glyph", "Tech disruption", "Glyph charge", 0, 0, 2))
        else:
            equipment.append(AeoniskEquipment("Union Heavy Pistol", "weapon", "conventional", "Standard sidearm", "Legal in most zones", 0, 0, 0))
        
        return equipment


class EnhancedLLMEngine:
    """LLM engine with improved character interactions."""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        
        # Initialize providers
        if ANTHROPIC_AVAILABLE and os.getenv('ANTHROPIC_API_KEY'):
            self.providers['anthropic'] = {'api_key': os.getenv('ANTHROPIC_API_KEY')}
            print("✅ Anthropic provider initialized")
        
        if OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY'):
            self.providers['openai'] = {'client': openai.OpenAI()}
            print("✅ OpenAI provider initialized")
        
        # Prefer Anthropic
        if 'anthropic' in self.providers:
            self.active_provider = 'anthropic'
            print("🎯 Using Anthropic Claude for narrative generation")
        elif 'openai' in self.providers:
            self.active_provider = 'openai'
            print("🎯 Using OpenAI for narrative generation")
        
        self.available = len(self.providers) > 0
    
    async def _call_llm(self, prompt: str, max_tokens: int = 200, temperature: float = 0.8) -> str:
        """Call active LLM provider."""
        if not self.available:
            return "LLM not available."
        
        if self.active_provider == 'anthropic':
            return await self._call_anthropic(prompt, max_tokens, temperature)
        elif self.active_provider == 'openai':
            return await self._call_openai(prompt, max_tokens, temperature)
        
        return "No provider available."
    
    async def _call_anthropic(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call Anthropic Claude API."""
        try:
            headers = {
                'x-api-key': self.providers["anthropic"]["api_key"],
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            }
            
            data = {
                'model': 'claude-3-haiku-20240307',
                'max_tokens': max_tokens,
                'temperature': temperature,
                'messages': [{'role': 'user', 'content': prompt}]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.anthropic.com/v1/messages', headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['content'][0]['text'].strip()
                    else:
                        error = await response.text()
                        print(f"Anthropic error: {error}")
                        return "Claude API error"
        except Exception as e:
            print(f"Anthropic exception: {e}")
            return "Claude generation failed"
    
    async def _call_openai(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call OpenAI API."""
        try:
            response = self.providers['openai']['client'].chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI error: {e}")
            return "OpenAI generation failed"
    
    async def generate_character_reasoning(
        self,
        character: AeoniskCharacter,
        scenario: Dict[str, Any], 
        chosen_action: str,
        available_actions: List[str],
        team_context: List[Dict[str, Any]],
        relevant_rules: List[Dict[str, Any]]
    ) -> str:
        """Generate character reasoning with family breath and team awareness."""
        
        # Build team context
        team_summary = ""
        if team_context:
            team_actions = []
            for teammate in team_context:
                if teammate['character'] != character.full_name:
                    team_actions.append(f"- {teammate['character']} ({teammate['family_line']}): {teammate.get('last_action', 'preparing')} → {teammate.get('last_outcome', 'unknown')}")
            
            if team_actions:
                team_summary = f"\n\nTEAM STATUS:\n" + "\n".join(team_actions)
        
        # Build equipment context
        notable_equipment = [eq for eq in character.equipment if eq.class_type != 'conventional']
        equipment_desc = ""
        if notable_equipment:
            equipment_desc = f"\n\nAVAILABLE GEAR:\n" + "\n".join([
                f"- {eq.name} ({eq.class_type}): {eq.effect}"
                for eq in notable_equipment[:3]
            ])
        
        prompt = f"""You are {character.full_name} of the {character.family_line} Line, working with a team in the Aeonisk universe.

BACKGROUND:
- Family Breath: "{character.family_breath}" (your line's spiritual focus)
- Faction: {character.origin_faction} ({character.family_reputation} reputation)
- Personal Drive: {character.personal_motivation}
- Void Score: {character.void_score}/10, Soulcredit: {character.soulcredit}
- Team Traits: Cooperation {character.personality.team_cooperation}/10, Trust {character.personality.trust_others}/10

CURRENT CRISIS:
{scenario['description']}
Location: {scenario['location']}
Void Influence: {scenario['void_influence']}/10

{team_summary}

{equipment_desc}

AVAILABLE ACTIONS:
{chr(10).join([f"• {action}" for action in available_actions])}

YOU CHOOSE: {chosen_action}

Write 2-3 sentences in first person explaining your choice. Focus on:
- How you're responding to your teammates' actions/failures
- How your family's Breath ({character.family_breath}) guides your approach  
- What unique value you bring to the team situation
- How your equipment could help

Show character voice and team dynamics, not just family exposition.

Reasoning:"""

        response = await self._call_llm(prompt, max_tokens=250, temperature=0.9)
        return response if response else f"My {character.family_line} training and {character.family_breath} Breath guide this choice."
    
    async def generate_action_outcome(
        self,
        character: AeoniskCharacter,
        action: str,
        roll_result: Dict[str, Any],
        scenario: Dict[str, Any],
        using_equipment: Optional[AeoniskEquipment] = None
    ) -> str:
        """Generate vivid action outcome."""
        
        equipment_context = ""
        if using_equipment:
            equipment_context = f"\n\nEQUIPMENT: {using_equipment.name} ({using_equipment.class_type}) - {using_equipment.effect}"
        
        prompt = f"""You are the Game Master narrating an Aeonisk YAGS action outcome.

CHARACTER: {character.full_name} ({character.family_line} Line, {character.family_breath} Breath)
ACTION: {action}
LOCATION: {scenario['location']}

{equipment_context}

ROLL RESULT:
- Total: {roll_result['roll_total']} vs Difficulty {roll_result['difficulty']}
- Outcome: {'SUCCESS' if roll_result['success'] else 'FAILURE'} (margin: {roll_result['margin']})

Write a cinematic 1-2 sentence description with:
- Aeonisk atmosphere (ley-conductors, Soulcredit kiosks, void energy, Codex surveillance)
- How their family Breath manifests in the attempt
- Specific sensory details of success/failure
- How it affects the team dynamic

Be vivid and setting-specific.

Outcome:"""

        response = await self._call_llm(prompt, max_tokens=180, temperature=0.9)
        return response if response else f"{character.given_name}'s attempt {'succeeds' if roll_result['success'] else 'fails'}."


class EnhancedGameSession:
    """Game session with authentic locations and realistic difficulty."""
    
    def __init__(self, vectorstore: AeoniskVectorStore, llm_engine: EnhancedLLMEngine):
        self.vectorstore = vectorstore
        self.llm = llm_engine
        self.session_id = f"enhanced_{int(asyncio.get_event_loop().time())}"
        self.turn_number = 0
        self.story_history = []
        self.characters = []
        self.current_scenario = None
        self.team_context = []
    
    async def initialize_session(self, num_players: int = 3):
        """Initialize with authentic Aeonisk characters and location."""
        print(f"🎲 Initializing Enhanced Aeonisk Session {self.session_id}")
        
        # Generate diverse characters from different factions
        factions = list(FAMILY_LINES.keys())
        used_factions = []
        
        for i in range(num_players):
            # Ensure faction diversity
            available_factions = [f for f in factions if f not in used_factions or len(used_factions) >= len(factions)]
            faction = random.choice(available_factions)
            used_factions.append(faction)
            
            family_line = random.choice(list(FAMILY_LINES[faction].keys()))
            character = self._generate_authentic_character(faction, family_line)
            self.characters.append(character)
            
            # Add to team context
            self.team_context.append({
                'character': character.full_name,
                'faction': character.origin_faction,
                'family_line': character.family_line,
                'last_action': 'preparing for mission',
                'last_outcome': 'ready'
            })
            
            print(f"📋 {character.full_name} ({character.family_line} Line - {character.family_breath} Breath)")
            print(f"   🎯 {character.personal_motivation}")
            print(f"   🧠 Cooperation: {character.personality.team_cooperation}/10, Trust: {character.personality.trust_others}/10")
            
            # Show notable equipment
            notable_gear = [eq for eq in character.equipment if eq.class_type != 'conventional']
            if notable_gear:
                print(f"   🛡️  Notable Gear: {', '.join([eq.name for eq in notable_gear[:2]])}")
        
        # Generate scenario with authentic location
        self.current_scenario = await self._generate_authentic_scenario()
        print(f"\n🌟 Opening: {self.current_scenario['title']}")
        print(f"📍 {self.current_scenario['location']}")
        print(f"📜 {self.current_scenario['description']}")
    
    def _generate_authentic_character(self, faction: str, family_line: str) -> AeoniskCharacter:
        """Generate character with authentic family data."""
        
        personality = PersonalityProfile(
            risk_tolerance=random.randint(1, 10),
            void_curiosity=random.randint(1, 10),
            authority_respect=random.randint(1, 10),
            family_loyalty=random.randint(3, 8),  # Less family obsession
            pragmatism=random.randint(1, 10),
            social_preference=random.randint(1, 10),
            innovation_drive=random.randint(1, 10),
            team_cooperation=random.randint(2, 10),
            leadership_drive=random.randint(1, 9),
            trust_others=random.randint(2, 9)
        )
        
        given_name = random.choice(GIVEN_NAMES)
        line_data = FAMILY_LINES[faction][family_line]
        
        # More varied motivations
        motivations = [
            'Uncover forbidden knowledge', 'Protect team members', 'Master void manipulation',
            'Build lasting alliances', 'Challenge corrupt authority', 'Preserve ancient wisdom',
            'Create revolutionary change', 'Forge new traditions', 'Seek personal redemption',
            'Advance understanding', 'Maintain cosmic balance', 'Break dangerous cycles'
        ]
        
        character = AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=f"{given_name} {family_line}",
            origin_faction=faction,
            family_reputation=line_data['reputation'],
            family_breath=line_data['breath'],
            personal_motivation=random.choice(motivations),
            personality=personality,
            
            # Generate varied attributes
            strength=random.randint(2, 5),
            health=random.randint(2, 5),
            agility=random.randint(2, 5),
            dexterity=random.randint(2, 5),
            perception=random.randint(2, 5),
            intelligence=random.randint(2, 5),
            empathy=random.randint(2, 5),
            willpower=random.randint(2, 5),
            
            # Skills based on personality and faction
            astral_arts=random.randint(0, 4) if personality.void_curiosity >= 6 else random.randint(0, 2),
            hacking=random.randint(2, 5) if faction == 'Tempest Industries' else random.randint(0, 2),
            corporate_influence=random.randint(2, 5) if faction == 'Astral Commerce Group' else random.randint(0, 2),
            stealth=random.randint(2, 5) if personality.social_preference <= 4 else random.randint(0, 2),
            charm=random.randint(2, 5) if personality.team_cooperation >= 7 else random.randint(0, 2),
            
            void_score=random.randint(0, 2) if personality.void_curiosity >= 7 else 0,
            soulcredit=random.randint(-1, 3),
            current_sparks=random.randint(3, 8),
            current_drips=random.randint(5, 15)
        )
        
        # Generate equipment
        character.equipment = EnhancedEquipmentGenerator.generate_starting_equipment(character)
        
        return character
    
    async def _generate_authentic_scenario(self) -> Dict[str, Any]:
        """Generate scenario using real Aeonisk locations."""
        
        location = random.choice(AEONISK_LOCATIONS)
        
        if not self.llm.available:
            return {
                'title': 'Crisis at ' + location['name'],
                'location': location['name'],
                'description': f"A serious situation unfolds at this {location['type']} location requiring team coordination.",
                'void_influence': random.randint(3, 6)
            }
        
        # Create location-appropriate scenarios
        scenario_types = {
            'government': 'Codex surveillance malfunction threatens citizen data',
            'spaceport': 'Void contamination in cargo manifests destabilizes ley-routes', 
            'commercial': 'Soulcredit futures market manipulation by rogue AI',
            'industrial': 'Biocreche pod gestation failure threatens Echo Children',
            'civic': 'Public Soulcredit kiosks broadcasting false ledger data',
            'spiritual': 'Sacred bonding rituals disrupted by void energy surge',
            'medical': 'Matron Bond corruption affecting new gestations',
            'frontier': 'Reality signatures becoming unstable near Veil transit',
            'transport': 'Ley-line nexus showing signs of Eye of Breach influence'
        }
        
        crisis_base = scenario_types.get(location['type'], 'Unknown crisis unfolds')
        
        factions_present = [char.origin_faction for char in self.characters]
        
        prompt = f"""Create an Aeonisk YAGS scenario set at a specific location.

LOCATION: {location['name']} 
TYPE: {location['type']} - {location['description']}
CRISIS: {crisis_base}

TEAM FACTIONS: {', '.join(factions_present)}

Create a scenario that:
- Uses the specific location's unique features and atmosphere
- Requires different faction expertise (Sovereign order, ACG commerce, Tempest tech, etc.)
- Involves authentic Aeonisk elements (Codex, Soulcredit, Bonds, void energy, ley-lines)
- Creates team cooperation opportunities and inter-faction tension

TITLE: [location-specific crisis name]
DESCRIPTION: [2-3 sentences using location details and Aeonisk lore]
VOID: [3-7, appropriate to crisis severity]"""

        response = await self.llm._call_llm(prompt, max_tokens=250, temperature=0.8)
        
        # Parse response
        scenario = {
            'title': f'Crisis at {location["name"]}',
            'location': location['name'],
            'description': f"A serious situation at this {location['type']} location requires immediate attention.",
            'void_influence': random.randint(3, 6)
        }
        
        # Better parsing
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if line.upper().startswith('TITLE:') or line.startswith('Title:'):
                title = re.sub(r'^TITLE:\s*|^Title:\s*', '', line, flags=re.IGNORECASE).strip()
                if title:
                    scenario['title'] = title
            elif line.upper().startswith('DESCRIPTION:') or line.startswith('Description:'):
                desc = re.sub(r'^DESCRIPTION:\s*|^Description:\s*', '', line, flags=re.IGNORECASE).strip()
                if desc:
                    scenario['description'] = desc
            elif line.upper().startswith('VOID:') or line.startswith('Void:'):
                void_match = re.search(r'(\d+)', line)
                if void_match:
                    scenario['void_influence'] = int(void_match.group(1))
        
        return scenario
    
    async def _execute_with_realistic_difficulty(self, character: AeoniskCharacter, action: str) -> Dict[str, Any]:
        """Execute action with realistic YAGS difficulty scaling."""
        
        # Determine skill and attribute
        skill_mapping = {
            'investigate': ('intelligence', 'awareness'),
            'ritual': ('willpower', 'astral_arts'),
            'hack': ('intelligence', 'hacking'),
            'coordinate': ('empathy', 'charm'),
            'stealth': ('agility', 'stealth'),
            'support': ('empathy', 'charm'),
            'analyze': ('intelligence', 'awareness'),
            'negotiate': ('empathy', 'corporate_influence')
        }
        
        primary_attr, primary_skill = 'intelligence', 'awareness'  # default
        for keyword, (attr, skill) in skill_mapping.items():
            if keyword in action.lower():
                primary_attr, primary_skill = attr, skill
                break
        
        attr_value = getattr(character, primary_attr, 3)
        skill_value = getattr(character, primary_skill, 2)
        
        # Equipment bonuses
        equipment_bonus = 0
        used_equipment = self._select_relevant_equipment(character, action)
        if used_equipment:
            # Extract numeric bonus from equipment effect
            bonus_match = re.search(r'\+(\d+)', used_equipment.effect)
            if bonus_match:
                equipment_bonus = min(3, int(bonus_match.group(1)) // 2)  # Scale down and cap
        
        # YAGS roll: Attribute × Skill + d20
        roll = random.randint(1, 20)
        
        # Void penalties - only apply to ritual actions in YAGS
        void_penalty = 0
        if 'ritual' in action.lower():
            void_penalty = character.void_score  # -1 per void level for rituals only
        
        total = attr_value * skill_value + roll + equipment_bonus - void_penalty
        
        # REALISTIC difficulty based on YAGS standards
        # Base difficulties: Easy 10, Moderate 15, Hard 20, Very Hard 25
        base_difficulty = 12  # Moderate baseline
        
        # Scenario modifiers (smaller than before)
        void_modifier = min(4, self.current_scenario['void_influence'] // 2)  # Max +4 from void
        chaos_modifier = random.randint(0, 3)  # Random variance
        
        difficulty = base_difficulty + void_modifier + chaos_modifier
        
        success = total >= difficulty
        margin = total - difficulty
        
        if success:
            if margin >= 8:
                story_impact = 'major_positive'
            else:
                story_impact = 'positive'
        else:
            if margin <= -8:
                story_impact = 'major_negative'
            else:
                story_impact = 'negative'
        
        return {
            'roll_total': total,
            'difficulty': difficulty,
            'margin': margin,
            'success': success,
            'story_impact': story_impact,
            'equipment_bonus': equipment_bonus,
            'void_penalty': void_penalty,
            'base_roll': attr_value * skill_value + roll,
            'skill_used': f"{primary_attr} × {primary_skill}",
            'used_equipment': used_equipment
        }
    
    def _select_relevant_equipment(self, character: AeoniskCharacter, action: str) -> Optional[AeoniskEquipment]:
        """Select equipment relevant to the action."""
        action_lower = action.lower()
        
        for equipment in character.equipment:
            if equipment.class_type == 'conventional':
                continue
                
            # Match equipment to action type
            if 'ritual' in action_lower and equipment.class_type in ['spirit', 'bonded']:
                return equipment
            elif 'hack' in action_lower and equipment.class_type == 'glyph':
                return equipment
            elif 'void' in action_lower and equipment.class_type == 'void':
                return equipment
            elif 'coordinate' in action_lower and 'unity' in equipment.name.lower():
                return equipment
            elif equipment.item_type == 'robot' and 'analyze' in action_lower:
                return equipment
        
        # Return any notable equipment - ensure we always use something
        notable = [eq for eq in character.equipment if eq.class_type != 'conventional']
        if notable:
            return random.choice(notable)
        
        # Fall back to any equipment if no notable gear
        return random.choice(character.equipment) if character.equipment else None
    
    async def play_turn(self) -> Dict[str, Any]:
        """Execute turn with realistic mechanics."""
        self.turn_number += 1
        
        print(f"\n🎯 === Turn {self.turn_number}: {self.current_scenario['title']} ===")
        print(f"📍 {self.current_scenario['location']}")
        print(f"🌀 Void Influence: {self.current_scenario['void_influence']}/10")
        print(f"📜 {self.current_scenario['description']}")
        
        turn_results = []
        
        for character in self.characters:
            print(f"\n🎭 {character.full_name} ({character.family_line} - {character.family_breath} Breath):")
            
            # Generate team-aware actions
            available_actions = [
                f"Coordinate with team using {character.family_line} expertise",
                f"Analyze the situation through {character.family_breath} Breath insight", 
                f"Support teammates' efforts with specialized equipment",
                f"Take point on next phase while others provide backup",
                f"Use {character.family_line} connections to access restricted resources",
                f"Investigate the crisis using family knowledge and training"
            ]
            
            # Add skill-specific actions
            if character.astral_arts >= 3:
                available_actions.append("Perform stabilizing ritual to counter void influence")
            if character.hacking >= 3:
                available_actions.append("Hack systems to gain digital advantage for team")
            
            chosen_action = random.choice(available_actions)  # Simplified for now
            
            # Get relevant rules
            relevant_rules = await self.vectorstore.query_rules(
                f"{chosen_action} {character.family_line} {character.family_breath}", 
                n_results=2
            )
            
            # Generate reasoning
            reasoning = await self.llm.generate_character_reasoning(
                character, self.current_scenario, chosen_action, available_actions,
                self.team_context, relevant_rules
            )
            
            # Execute with realistic difficulty  
            action_result = await self._execute_with_realistic_difficulty(character, chosen_action)
            used_equipment = action_result.get('used_equipment')
            
            # Generate outcome
            outcome = await self.llm.generate_action_outcome(
                character, chosen_action, action_result, self.current_scenario, used_equipment
            )
            
            print(f"   💭 {reasoning}")
            print(f"   🎲 {outcome}")
            if used_equipment:
                print(f"   🛡️  Using: {used_equipment.name}")
            print(f"   📊 Roll: {action_result['roll_total']} vs {action_result['difficulty']} (margin: {action_result['margin']})")
            
            # Update team context
            for ctx in self.team_context:
                if ctx['character'] == character.full_name:
                    ctx['last_action'] = chosen_action
                    ctx['last_outcome'] = action_result['story_impact']
                    break
            
            turn_results.append({
                'character': character.full_name,
                'action': chosen_action,
                'reasoning': reasoning,
                'outcome': outcome,
                'mechanics': action_result,
                'equipment_used': used_equipment.name if used_equipment else None
            })
        
        self.story_history.append({
            'turn': self.turn_number,
            'scenario': self.current_scenario.copy(),
            'actions': turn_results
        })
        
        return turn_results


async def main():
    """Run the enhanced Aeonisk system."""
    
    print("🚀 Enhanced Aeonisk YAGS Multi-Agent System")
    print("Authentic family names, locations, equipment, and realistic difficulty\n")
    
    # Initialize systems
    vectorstore = AeoniskVectorStore()
    
    # Check if vectorstore has data
    try:
        test_query = await vectorstore.query_rules("attribute skill", n_results=1)
        if not test_query:
            print("📚 Loading YAGS/Aeonisk rules...")
            await vectorstore.populate_vectorstore()
    except:
        print("📚 Loading YAGS/Aeonisk rules...")
        await vectorstore.populate_vectorstore()
    
    llm_engine = EnhancedLLMEngine()
    session = EnhancedGameSession(vectorstore, llm_engine)
    
    # Run session
    await session.initialize_session(num_players=3)
    
    # Play several turns
    for turn in range(4):
        await session.play_turn()
        await asyncio.sleep(1)
    
    # Save dataset
    dataset = {
        'session_id': session.session_id,
        'session_type': 'enhanced_authentic_aeonisk',
        'total_turns': session.turn_number,
        'characters': [
            {
                'name': char.full_name,
                'faction': char.origin_faction,
                'family_line': char.family_line,
                'family_breath': char.family_breath,
                'motivation': char.personal_motivation,
                'equipment': [eq.name for eq in char.equipment if eq.class_type != 'conventional']
            }
            for char in session.characters
        ],
        'story_progression': session.story_history,
        'enhancements': {
            'authentic_family_names': 'Using actual lines from lore (Halessan, Elaras, Vireya, Karsel, etc.)',
            'family_breath_system': 'Each line has spiritual focus guiding decisions',
            'realistic_difficulty': 'YAGS-appropriate DC 12-20 range instead of 24-29',
            'authentic_locations': 'Real places from lore with specific atmosphere',
            'advanced_equipment': 'Robots, vehicles, and high-tech gear from game'
        }
    }
    
    import time
    timestamp = int(time.time())
    dataset_file = f"./enhanced_aeonisk_{timestamp}.yaml"
    
    with open(dataset_file, 'w') as f:
        yaml.dump(dataset, f, default_flow_style=False)
    
    print(f"\n✅ Enhanced Aeonisk session saved to: {dataset_file}")
    print("🎮 Now with authentic family names, realistic difficulty, and advanced equipment!")


if __name__ == "__main__":
    asyncio.run(main())