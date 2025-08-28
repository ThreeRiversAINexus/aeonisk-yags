#!/usr/bin/env python3
"""
Interactive Aeonisk YAGS Multi-Agent System

Characters acknowledge each other, react to teammates' actions, and use
rich Aeonisk equipment and lore. LLM-generated narrative focused on
character interactions rather than just family background.
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
from vectorstore_system import AeoniskVectorStore, FAMILY_LINES, GIVEN_NAMES

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
    
    # New interaction traits
    team_cooperation: int = 5  # 1-10
    leadership_drive: int = 5  # 1-10
    trust_others: int = 5      # 1-10


@dataclass
class AeoniskEquipment:
    """Rich Aeonisk equipment from the lore."""
    name: str
    item_type: str  # weapon, armor, accessory, talisman
    class_type: str  # bonded, glyph, void, spirit, contract, conventional
    effect: str
    upkeep: str
    void_risk: int = 0
    soulcredit_requirement: int = 0


@dataclass
class AeoniskCharacter:
    """Interactive character with equipment and team awareness."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    family_reputation: str
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


class EquipmentGenerator:
    """Generates appropriate Aeonisk equipment based on character background."""
    
    EQUIPMENT_CATALOG = [
        # Weapons
        AeoniskEquipment("Mnemonic Blade", "weapon", "bonded", "+5 DMG, +2 when trauma invoked", "Re-ink sigils monthly", 0, 0),
        AeoniskEquipment("Shrike Cannon", "weapon", "glyph", "+6 DMG, ignores ritual shields", "Glyph stabilizer monthly", 0, 0),
        AeoniskEquipment("Debtbreaker Sidearm", "weapon", "contract", "+4 DMG, fires track-tags", "Codex ping per shot", 0, 0),
        AeoniskEquipment("Wraithroot Vineblade", "weapon", "spirit", "+2 DMG, +1 vs defending Bond", "Water with Drip", 0, 0),
        AeoniskEquipment("Hollowed Repeater", "weapon", "void", "Damage scales with Void score", "Accuracy drops if Bonds > 0", 1, 0),
        
        # Armor  
        AeoniskEquipment("Sovereign Sanctum Mantle", "armor", "bonded", "+4 Soak, blocks ritual tracking", "Monthly oath rite", 0, 0),
        AeoniskEquipment("Resonant Shell Weave", "armor", "glyph", "+3 Soak, -2 energy damage", "Cracks add +1 Void", 0, 0),
        AeoniskEquipment("Tempest Tactical Skin", "armor", "contract", "+5 Soak, breach ping if torn", "Requires Soulcredit ≥ 0", 0, 0),
        AeoniskEquipment("Voidshroud Drape", "armor", "void", "+2 Soak, phase-shift defense", "Wears +1 Void/hour", 1, 0),
        
        # Accessories
        AeoniskEquipment("Leyshade Visor", "accessory", "sensor", "Reveals hidden glyphs/Bonds", "1 Breath use, +1 Void in dreamspace", 1, 0),
        AeoniskEquipment("Multi-Bind Sheath", "accessory", "bracer", "Quick-swap 4 Talismans", "1 Spark/day to bond", 0, 0),
        AeoniskEquipment("Soulcredit Tag", "accessory", "civic", "Broadcasts ledger status", "+1 Void per forged sync", 0, -2),
        AeoniskEquipment("Echo-Calibrator", "accessory", "tool", "Stabilizes Raw Seeds in rituals", "1 Drip per 3 uses", 0, 0),
        
        # Talismans & Special
        AeoniskEquipment("Raw Seed (Unstable)", "talisman", "void", "Becomes elemental when attuned", "Degrades in 7 cycles, +1 Void if raw", 1, 0),
        AeoniskEquipment("Harmony Crystal", "talisman", "spirit", "Enhances unity rituals", "Monthly purification", 0, 0),
        AeoniskEquipment("Unity Sigil", "talisman", "bonded", "Strengthens team bonds", "Requires shared ritual", 0, 0),
        AeoniskEquipment("Void Shard", "talisman", "void", "Amplifies void manipulation", "Constant +1 Void risk", 1, 0),
        AeoniskEquipment("Freedom Stone", "talisman", "spirit", "Breaks unwanted bonds", "Absorbs negative emotions", 0, 0)
    ]
    
    @classmethod
    def generate_starting_equipment(cls, character: AeoniskCharacter) -> List[AeoniskEquipment]:
        """Generate appropriate starting equipment based on character."""
        equipment = []
        
        # Everyone gets basic gear
        equipment.append(AeoniskEquipment("Personal Commlink", "accessory", "conventional", "Standard communication", "None", 0, 0))
        
        # Faction-specific gear
        if character.origin_faction == 'Sovereign Nexus':
            equipment.append(random.choice([
                AeoniskEquipment("Harmony Crystal", "talisman", "spirit", "Unity rituals", "Monthly purification", 0, 0),
                AeoniskEquipment("Unity Sigil", "talisman", "bonded", "Team bonds", "Shared ritual", 0, 0)
            ]))
            if character.soulcredit >= 0:
                equipment.append(AeoniskEquipment("Sovereign Sanctum Mantle", "armor", "bonded", "+4 Soak, blocks tracking", "Monthly oath", 0, 0))
        
        elif character.origin_faction == 'Tempest Industries':
            equipment.append(AeoniskEquipment("Crypto Commlink", "accessory", "glyph", "Encrypted communication", "Glyph refresh", 0, 0))
            if character.void_score >= 1:
                equipment.append(random.choice([
                    AeoniskEquipment("Void Shard", "talisman", "void", "Void amplification", "+1 Void risk", 1, 0),
                    AeoniskEquipment("Voidshroud Drape", "armor", "void", "Phase defense", "+1 Void/hour", 1, 0)
                ]))
        
        elif character.origin_faction == 'Astral Commerce Group':
            equipment.append(AeoniskEquipment("Soulcredit Tag", "accessory", "civic", "Ledger broadcast", "Forgery +1 Void", 0, -2))
            if character.corporate_influence >= 3:
                equipment.append(AeoniskEquipment("Debtbreaker Sidearm", "weapon", "contract", "Track-tags", "Codex ping", 0, 0))
        
        elif character.origin_faction == 'Arcane Genetics':
            equipment.append(AeoniskEquipment("Bio-Scanner", "accessory", "sensor", "Genetic analysis", "Bio sample refresh", 0, 0))
            equipment.append(AeoniskEquipment("Echo-Calibrator", "accessory", "tool", "Seed stabilization", "1 Drip per 3 uses", 0, 0))
        
        elif character.origin_faction == 'Freeborn':
            equipment.append(AeoniskEquipment("Freedom Stone", "talisman", "spirit", "Bond breaking", "Emotion absorption", 0, 0))
            equipment.append(AeoniskEquipment("Jury-Rigged Scanner", "accessory", "conventional", "Makeshift detection", "Frequent repairs", 0, 0))
        
        # Add weapon based on skills
        if character.astral_arts >= 3:
            equipment.append(AeoniskEquipment("Wraithroot Vineblade", "weapon", "spirit", "+2 DMG, Bond defense", "Water with Drip", 0, 0))
        elif character.hacking >= 3:
            equipment.append(AeoniskEquipment("Pulse Disruptor", "weapon", "glyph", "Tech disruption", "Glyph charge", 0, 0))
        else:
            equipment.append(AeoniskEquipment("Union Heavy Pistol", "weapon", "conventional", "Standard sidearm", "Legal in most zones", 0, 0))
        
        return equipment


class InteractiveLLMEngine:
    """LLM engine focused on character interactions and team dynamics."""
    
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
        
        # Prefer Anthropic for narrative
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
        team_context: List[Dict[str, Any]],  # What teammates have done
        relevant_rules: List[Dict[str, Any]]
    ) -> str:
        """Generate character reasoning that acknowledges teammates and situation."""
        
        # Build team context
        team_summary = ""
        if team_context:
            team_actions = []
            for teammate in team_context:
                if teammate['character'] != character.full_name:
                    team_actions.append(f"- {teammate['character']}: {teammate.get('last_action', 'preparing')} ({teammate.get('last_outcome', 'unknown outcome')})")
            
            if team_actions:
                team_summary = f"\n\nTEAMMATE ACTIONS:\n" + "\n".join(team_actions)
        
        # Build equipment context
        notable_equipment = [eq for eq in character.equipment if eq.class_type != 'conventional']
        equipment_desc = ""
        if notable_equipment:
            equipment_desc = f"\n\nYOUR EQUIPMENT:\n" + "\n".join([
                f"- {eq.name} ({eq.class_type}): {eq.effect}"
                for eq in notable_equipment[:3]
            ])
        
        rule_context = ""
        if relevant_rules:
            rule_context = "\n\nRELEVANT RULES:\n" + "\n".join([
                f"- {rule['section']}: {rule['content'][:120]}..."
                for rule in relevant_rules[:2]
            ])
        
        prompt = f"""You are {character.full_name}, currently working with a team in an Aeonisk YAGS situation.

BACKGROUND:
- Family: {character.family_line} of {character.origin_faction} ({character.family_reputation} reputation)
- Personal Goal: {character.personal_motivation}
- Void Score: {character.void_score}/10, Soulcredit: {character.soulcredit}
- Key Traits: Risk {character.personality.risk_tolerance}/10, Team Cooperation {character.personality.team_cooperation}/10, Trust {character.personality.trust_others}/10

CURRENT SITUATION:
{scenario['description']}
Location: {scenario['location']}
Void Influence: {scenario['void_influence']}/10

{team_summary}

{equipment_desc}

AVAILABLE ACTIONS:
{chr(10).join([f"• {action}" for action in available_actions])}

YOU CHOOSE: {chosen_action}

{rule_context}

Write 2-3 sentences in first person explaining your reasoning. Focus on:
- How you're reacting to what your teammates have done
- What you bring to the team that's unique
- Your tactical thinking about the situation
- How your equipment or expertise helps

BE SPECIFIC about your interactions with others. Don't just focus on family background - show your personality and team dynamics.

Reasoning:"""

        response = await self._call_llm(prompt, max_tokens=250, temperature=0.9)
        return response if response else f"{character.given_name} acts based on the current situation and team needs."
    
    async def generate_action_outcome(
        self,
        character: AeoniskCharacter,
        action: str,
        roll_result: Dict[str, Any],
        scenario: Dict[str, Any],
        using_equipment: Optional[AeoniskEquipment] = None
    ) -> str:
        """Generate vivid action outcome with equipment details."""
        
        equipment_context = ""
        if using_equipment:
            equipment_context = f"\n\nEQUIPMENT USED: {using_equipment.name} ({using_equipment.class_type}) - {using_equipment.effect}"
        
        prompt = f"""You are the Game Master narrating an Aeonisk YAGS action outcome.

CHARACTER: {character.full_name} ({character.family_line} of {character.origin_faction})
ACTION: {action}
LOCATION: {scenario['location']}
VOID INFLUENCE: {scenario['void_influence']}/10

{equipment_context}

ROLL RESULT:
- Total: {roll_result['roll_total']} vs Difficulty {roll_result['difficulty']}
- Margin: {roll_result['margin']} ({'SUCCESS' if roll_result['success'] else 'FAILURE'})
- Impact: {roll_result['story_impact']}

Write a cinematic 1-2 sentence description focusing on:
- Sensory details (void energy, astral tech, environmental atmosphere)
- How their specific equipment/expertise shows in the attempt
- Immediate consequences and how it affects the team situation
- Aeonisk setting flavor (not generic sci-fi)

Be vivid and specific to this world and character.

Outcome:"""

        response = await self._call_llm(prompt, max_tokens=180, temperature=0.9)
        return response if response else f"{character.given_name}'s attempt {'succeeds' if roll_result['success'] else 'fails'}."


class InteractiveGameSession:
    """Game session with rich character interactions and equipment usage."""
    
    def __init__(self, vectorstore: AeoniskVectorStore, llm_engine: InteractiveLLMEngine):
        self.vectorstore = vectorstore
        self.llm = llm_engine
        self.session_id = f"interactive_{int(asyncio.get_event_loop().time())}"
        self.turn_number = 0
        self.story_history = []
        self.characters = []
        self.current_scenario = None
        self.team_context = []  # Track what each character has done
    
    async def initialize_session(self, num_players: int = 3):
        """Initialize with diverse, well-equipped characters."""
        print(f"🎲 Initializing Interactive Session {self.session_id}")
        
        # Generate diverse characters from different factions
        factions = list(FAMILY_LINES.keys())
        used_factions = []
        
        for i in range(num_players):
            # Ensure faction diversity
            available_factions = [f for f in factions if f not in used_factions or len(used_factions) >= len(factions)]
            faction = random.choice(available_factions)
            used_factions.append(faction)
            
            family_line = random.choice(list(FAMILY_LINES[faction].keys()))
            character = self._generate_interactive_character(faction, family_line)
            self.characters.append(character)
            
            # Add to team context
            self.team_context.append({
                'character': character.full_name,
                'faction': character.origin_faction,
                'family_line': character.family_line,
                'last_action': 'preparing for mission',
                'last_outcome': 'ready'
            })
            
            print(f"📋 {character.full_name} ({character.family_line} of {character.origin_faction})")
            print(f"   🎯 {character.personal_motivation}")
            print(f"   🧠 Cooperation: {character.personality.team_cooperation}/10, Trust: {character.personality.trust_others}/10")
            
            # Show notable equipment
            notable_gear = [eq for eq in character.equipment if eq.class_type != 'conventional']
            if notable_gear:
                print(f"   🛡️  Notable Gear: {', '.join([eq.name for eq in notable_gear[:2]])}")
        
        # Generate opening scenario
        self.current_scenario = await self._generate_team_scenario()
        print(f"\n🌟 Opening: {self.current_scenario['title']}")
        print(f"📍 {self.current_scenario['location']}")
        print(f"📜 {self.current_scenario['description']}")
    
    def _generate_interactive_character(self, faction: str, family_line: str) -> AeoniskCharacter:
        """Generate character focused on team interactions."""
        
        # Generate personality with emphasis on team dynamics
        personality = PersonalityProfile(
            risk_tolerance=random.randint(1, 10),
            void_curiosity=random.randint(1, 10),
            authority_respect=random.randint(1, 10),
            family_loyalty=random.randint(3, 8),  # Reduced emphasis
            pragmatism=random.randint(1, 10),
            social_preference=random.randint(1, 10),
            innovation_drive=random.randint(1, 10),
            
            # New team-focused traits
            team_cooperation=random.randint(2, 10),
            leadership_drive=random.randint(1, 9),
            trust_others=random.randint(2, 9)
        )
        
        given_name = random.choice(GIVEN_NAMES)
        line_data = FAMILY_LINES[faction][family_line]
        
        # More varied motivations beyond family
        all_motivations = [
            'Uncover hidden truths', 'Build meaningful connections', 'Master dangerous knowledge',
            'Protect the innocent', 'Challenge corrupt systems', 'Seek personal redemption',
            'Advance scientific understanding', 'Forge new alliances', 'Preserve ancient wisdom',
            'Create lasting change'
        ]
        
        character = AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=f"{given_name} {family_line}",
            origin_faction=faction,
            family_reputation=line_data['reputation'],
            personal_motivation=random.choice(all_motivations),
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
        character.equipment = EquipmentGenerator.generate_starting_equipment(character)
        
        return character
    
    async def _generate_team_scenario(self) -> Dict[str, Any]:
        """Generate scenario that requires teamwork."""
        
        if not self.llm.available:
            return {
                'title': 'Coordinated Investigation',
                'description': 'Multiple factions must work together to solve a crisis.',
                'location': 'Neutral Zone, Aeonisk Prime',
                'void_influence': 4,
                'requires_teamwork': True
            }
        
        factions_present = list(set([char.origin_faction for char in self.characters]))
        
        prompt = f"""Create an opening scenario for an Aeonisk YAGS session requiring teamwork.

TEAM COMPOSITION:
{chr(10).join([f"- {char.full_name} ({char.family_line} of {char.origin_faction})" for char in self.characters])}

FACTIONS REPRESENTED: {', '.join(factions_present)}

Create a scenario that:
- Requires different faction expertise to solve
- Has clear stakes that matter to all characters
- Creates opportunities for both cooperation and tension
- Involves Aeonisk-specific elements (void energy, astral tech, etc.)
- Gives each character type meaningful contributions

Format:
Title: [scenario name]
Location: [specific Aeonisk location]
Description: [2-3 sentences with immediate challenge requiring teamwork]
Void: [1-10]"""

        response = await self.llm._call_llm(prompt, max_tokens=300, temperature=0.8)
        
        # Parse response
        scenario = {
            'title': 'Team Investigation',
            'description': 'A crisis requires coordinated response.',
            'location': 'Unknown Location',
            'void_influence': 5
        }
        
        for line in response.split('\n'):
            if line.startswith('Title:'):
                scenario['title'] = line.replace('Title:', '').strip()
            elif line.startswith('Location:'):
                scenario['location'] = line.replace('Location:', '').strip()
            elif line.startswith('Description:'):
                scenario['description'] = line.replace('Description:', '').strip()
            elif line.startswith('Void:'):
                void_match = re.search(r'(\d+)', line)
                if void_match:
                    scenario['void_influence'] = int(void_match.group(1))
        
        return scenario
    
    async def play_turn(self) -> Dict[str, Any]:
        """Execute turn with rich character interactions."""
        self.turn_number += 1
        
        print(f"\n🎯 === Turn {self.turn_number}: {self.current_scenario['title']} ===")
        print(f"📍 {self.current_scenario['location']}")
        print(f"🌀 Void Influence: {self.current_scenario['void_influence']}/10")
        print(f"📜 {self.current_scenario['description']}")
        
        turn_results = []
        
        for i, character in enumerate(self.characters):
            print(f"\n🎭 {character.full_name}'s Turn:")
            
            # Generate actions that can build on teammates' work
            available_actions = await self._generate_team_aware_actions(character, self.team_context)
            
            # Choose action based on personality and team dynamics
            chosen_action = self._choose_interactive_action(character, available_actions, self.team_context)
            
            # Get relevant rules
            relevant_rules = await self.vectorstore.query_rules(
                f"{chosen_action} {character.family_line} teamwork", 
                n_results=2
            )
            
            # Generate team-aware reasoning
            reasoning = await self.llm.generate_character_reasoning(
                character, self.current_scenario, chosen_action, available_actions, 
                self.team_context, relevant_rules
            )
            
            # Execute with mechanics
            action_result = await self._execute_with_equipment(character, chosen_action)
            
            # Generate narrative outcome
            used_equipment = self._select_relevant_equipment(character, chosen_action)
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
        
        # Evolve scenario based on team performance
        self.current_scenario = await self._evolve_team_scenario(turn_results)
        
        self.story_history.append({
            'turn': self.turn_number,
            'scenario': self.current_scenario.copy(),
            'actions': turn_results
        })
        
        return turn_results
    
    async def _generate_team_aware_actions(self, character: AeoniskCharacter, team_context: List[Dict]) -> List[str]:
        """Generate actions that can build on what teammates have done."""
        
        # Analyze what teammates have attempted
        teammate_actions = []
        for ctx in team_context:
            if ctx['character'] != character.full_name and 'last_action' in ctx:
                teammate_actions.append(f"{ctx['character']}: {ctx['last_action']} ({ctx.get('last_outcome', 'unknown')})")
        
        base_actions = [
            f"Build on teammates' work by providing {character.family_line} expertise",
            f"Cover for any gaps in the team's approach using specialized skills",
            f"Coordinate with team members to create a unified strategy",
            f"Take point on the next phase while others provide support",
            f"Use equipment to enhance the team's capabilities"
        ]
        
        # Add character-specific options
        if character.astral_arts >= 3:
            base_actions.append("Provide ritual support to stabilize teammates' efforts")
        if character.hacking >= 3:
            base_actions.append("Access systems to give team digital advantage")
        if character.charm >= 3:
            base_actions.append("Negotiate on behalf of the team using social connections")
        
        return random.sample(base_actions, min(6, len(base_actions)))
    
    def _choose_interactive_action(self, character: AeoniskCharacter, actions: List[str], team_context: List[Dict]) -> str:
        """Choose action based on team dynamics and personality."""
        
        # Simple personality-based selection that considers team
        action_weights = []
        
        for action in actions:
            weight = 5  # base
            action_lower = action.lower()
            
            # Team cooperation bonus
            if 'coordinate' in action_lower or 'support' in action_lower:
                weight += (character.personality.team_cooperation - 5)
            
            # Leadership drive
            if 'take point' in action_lower or 'lead' in action_lower:
                weight += (character.personality.leadership_drive - 5)
            
            # Trust in others
            if 'build on' in action_lower and character.personality.trust_others >= 6:
                weight += 2
            elif 'build on' in action_lower and character.personality.trust_others <= 4:
                weight -= 2
            
            action_weights.append((action, max(1, weight)))
        
        # Weighted random selection
        total = sum(w for _, w in action_weights)
        roll = random.uniform(0, total)
        
        current = 0
        for action, weight in action_weights:
            current += weight
            if roll <= current:
                return action
        
        return random.choice(actions)
    
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
        
        # Return any notable equipment
        notable = [eq for eq in character.equipment if eq.class_type != 'conventional']
        return random.choice(notable) if notable else None
    
    async def _execute_with_equipment(self, character: AeoniskCharacter, action: str) -> Dict[str, Any]:
        """Execute action considering equipment bonuses."""
        
        # Base YAGS mechanics
        skill_mapping = {
            'investigate': ('intelligence', 'awareness'),
            'ritual': ('willpower', 'astral_arts'),
            'hack': ('intelligence', 'hacking'),
            'coordinate': ('empathy', 'charm'),
            'stealth': ('agility', 'stealth'),
            'support': ('empathy', 'charm')
        }
        
        primary_attr, primary_skill = 'intelligence', 'awareness'
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
            if '+' in used_equipment.effect:
                # Extract numeric bonus
                bonus_match = re.search(r'\+(\d+)', used_equipment.effect)
                if bonus_match:
                    equipment_bonus = int(bonus_match.group(1)) // 2  # Scale down for skill checks
        
        # Roll with equipment
        roll = random.randint(1, 20)
        total = attr_value * skill_value + roll + equipment_bonus
        
        # Dynamic difficulty
        base_difficulty = 14 + self.current_scenario['void_influence'] + random.randint(0, 4)
        
        success = total >= base_difficulty
        margin = total - base_difficulty
        
        if success:
            story_impact = 'major_positive' if margin >= 10 else 'positive'
        else:
            story_impact = 'major_negative' if margin <= -10 else 'negative'
        
        return {
            'roll_total': total,
            'difficulty': base_difficulty,
            'margin': margin,
            'success': success,
            'story_impact': story_impact,
            'equipment_bonus': equipment_bonus,
            'base_roll': attr_value * skill_value + roll
        }
    
    async def _evolve_team_scenario(self, turn_results: List[Dict]) -> Dict[str, Any]:
        """Evolve scenario based on team performance."""
        
        if not self.llm.available:
            new_scenario = self.current_scenario.copy()
            successes = sum(1 for r in turn_results if r['mechanics']['success'])
            if successes >= 2:
                new_scenario['description'] += " The team's coordination shows promise."
            else:
                new_scenario['description'] += " The team struggles to work together effectively."
            return new_scenario
        
        # Build detailed action summary
        action_summary = []
        for result in turn_results:
            equipment_note = f" (using {result['equipment_used']})" if result['equipment_used'] else ""
            action_summary.append(
                f"- {result['character']}: {result['action']}{equipment_note}\n" +
                f"  Outcome: {result['outcome']} ({result['mechanics']['story_impact']})"
            )
        
        # Count team successes/failures for dramatic evolution
        successes = sum(1 for r in turn_results if r['mechanics']['story_impact'] in ['positive', 'major_positive'])
        failures = sum(1 for r in turn_results if r['mechanics']['story_impact'] in ['negative', 'major_negative'])
        
        prompt = f"""You are the AI Game Master. The scenario must DRAMATICALLY evolve based on team performance.

CURRENT: "{self.current_scenario['title']}" at {self.current_scenario['location']}
DESCRIPTION: {self.current_scenario['description']}
VOID: {self.current_scenario['void_influence']}/10

TEAM PERFORMANCE THIS TURN:
{chr(10).join(action_summary)}
RESULTS: {successes} successes, {failures} failures

The scenario must change significantly. If they're failing badly, introduce new crises, environmental changes, or hostile forces. If they succeed, open new areas, reveal plot twists, or escalate the stakes differently.

Create a completely NEW scenario phase:

TITLE: [new dramatic title - NOT just adding adjectives]
LOCATION: [can change if story demands it]  
DESCRIPTION: [completely new situation based on their actions - 2-3 sentences]
VOID: [1-12, can exceed 10 for catastrophic situations]"""

        response = await self.llm._call_llm(prompt, max_tokens=400, temperature=0.8)
        
        # More robust parsing
        new_scenario = self.current_scenario.copy()
        
        # Handle different response formats
        lines = response.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Title parsing
            if line.upper().startswith('TITLE:') or line.startswith('Title:'):
                title = re.sub(r'^TITLE:\s*|^Title:\s*', '', line, flags=re.IGNORECASE).strip()
                if title:
                    new_scenario['title'] = title
            
            # Location parsing  
            elif line.upper().startswith('LOCATION:') or line.startswith('Location:'):
                location = re.sub(r'^LOCATION:\s*|^Location:\s*', '', line, flags=re.IGNORECASE).strip()
                if location:
                    new_scenario['location'] = location
            
            # Description parsing - can be multiline
            elif line.upper().startswith('DESCRIPTION:') or line.startswith('Description:'):
                desc_lines = [re.sub(r'^DESCRIPTION:\s*|^Description:\s*', '', line, flags=re.IGNORECASE).strip()]
                
                # Collect following lines until we hit another field
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line.upper().startswith(('VOID:', 'TITLE:', 'LOCATION:')) or next_line.startswith(('Void:', 'Title:', 'Location:')):
                        break
                    if next_line:  # Skip empty lines
                        desc_lines.append(next_line)
                
                description = ' '.join(desc_lines).strip()
                if description:
                    new_scenario['description'] = description
            
            # Void parsing
            elif line.upper().startswith('VOID:') or line.startswith('Void:'):
                void_match = re.search(r'(\d+)', line)
                if void_match:
                    new_void = int(void_match.group(1))
                    new_scenario['void_influence'] = max(1, min(12, new_void))
        
        # Fallback evolution if parsing fails
        if new_scenario['title'] == self.current_scenario['title']:
            if failures > successes:
                new_scenario['title'] = f"Crisis: {self.current_scenario['title']}"
                new_scenario['void_influence'] = min(12, self.current_scenario['void_influence'] + 2)
                new_scenario['description'] += f" The team's {failures} failures have created dangerous complications."
            else:
                new_scenario['title'] = f"Resolution: {self.current_scenario['title']}"
                new_scenario['void_influence'] = max(1, self.current_scenario['void_influence'] - 1)
                new_scenario['description'] += f" The team's {successes} successes open new possibilities."
        
        print(f"🔄 Scenario evolved: '{self.current_scenario['title']}' → '{new_scenario['title']}'")
        return new_scenario


async def main():
    """Run the interactive narrative system."""
    
    print("🚀 Interactive Aeonisk YAGS Multi-Agent System")
    print("Rich character interactions with Aeonisk equipment and lore\n")
    
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
    
    llm_engine = InteractiveLLMEngine()
    session = InteractiveGameSession(vectorstore, llm_engine)
    
    # Run interactive session
    await session.initialize_session(num_players=3)
    
    # Play several turns
    for turn in range(4):
        await session.play_turn()
        await asyncio.sleep(1)
    
    # Save dataset
    dataset = {
        'session_id': session.session_id,
        'session_type': 'interactive_team_focused',
        'total_turns': session.turn_number,
        'characters': [
            {
                'name': char.full_name,
                'faction': char.origin_faction, 
                'motivation': char.personal_motivation,
                'team_traits': {
                    'cooperation': char.personality.team_cooperation,
                    'leadership': char.personality.leadership_drive,
                    'trust': char.personality.trust_others
                },
                'equipment': [eq.name for eq in char.equipment if eq.class_type != 'conventional']
            }
            for char in session.characters
        ],
        'story_progression': session.story_history,
        'training_focus': {
            'team_dynamics': 'Characters acknowledge and build on teammates actions',
            'equipment_integration': 'Rich Aeonisk gear usage with mechanical effects',
            'reduced_family_focus': 'Personal goals and team needs over family loyalty',
            'interactive_reasoning': 'Decisions consider what others have done'
        }
    }
    
    import time
    timestamp = int(time.time())
    dataset_file = f"./interactive_session_{timestamp}.yaml"
    
    with open(dataset_file, 'w') as f:
        yaml.dump(dataset, f, default_flow_style=False)
    
    print(f"\n✅ Interactive session saved to: {dataset_file}")
    print("🎮 Characters now acknowledge teammates and use rich Aeonisk equipment!")


if __name__ == "__main__":
    asyncio.run(main())