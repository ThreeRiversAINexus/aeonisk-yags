"""
LLM-powered Aeonisk YAGS Multi-Agent Self-Playing System

Uses actual LLMs (OpenAI/Claude) to generate narrative content, character decisions,
and gameplay in the exact dataset format for training AI systems.
"""

import asyncio
import json
import os
import random
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import openai

# Configure OpenAI (or use other LLM providers)
openai.api_key = os.getenv('OPENAI_API_KEY')

@dataclass
class AeoniskCharacter:
    """Full Aeonisk character with proper family lines and factions."""
    name: str
    full_name: str  # Including family line
    origin_faction: str
    family_line: str
    
    # YAGS Attributes
    strength: int = 3
    health: int = 3 
    agility: int = 3
    dexterity: int = 3
    perception: int = 3
    intelligence: int = 3
    empathy: int = 3
    willpower: int = 3
    
    # Aeonisk specifics
    void_score: int = 0
    soulcredit: int = 0
    bonds: List[str] = None
    true_will: str = ""
    birth_method: str = "biocreche_pod"
    
    # Skills (key ones for dataset)
    athletics: int = 2
    awareness: int = 2
    brawl: int = 2
    charm: int = 2
    guile: int = 2
    stealth: int = 2
    astral_arts: int = 0
    hacking: int = 0
    melee: int = 0
    pilot: int = 0
    
    # Equipment
    primary_ritual_item: str = ""
    current_gear: List[str] = None
    
    def __post_init__(self):
        if self.bonds is None:
            self.bonds = []
        if self.current_gear is None:
            self.current_gear = []
            
    def to_dataset_format(self) -> Dict[str, Any]:
        """Convert to the dataset character format."""
        return {
            'name': self.full_name,
            'tech_level': 'High Tech',
            'attributes': {
                'strength': self.strength,
                'dexterity': self.dexterity, 
                'agility': self.agility,
                'intelligence': self.intelligence,
                'perception': self.perception,
                'willpower': self.willpower,
                'empathy': self.empathy
            },
            'skills': {
                'athletics': self.athletics,
                'awareness': self.awareness,
                'brawl': self.brawl,
                'charm': self.charm,
                'guile': self.guile,
                'stealth': self.stealth,
                'astral_arts': self.astral_arts,
                'hacking': self.hacking,
                'melee': self.melee,
                'pilot': self.pilot
            },
            'current_void': self.void_score,
            'soulcredit': self.soulcredit,
            'bonds': self.bonds,
            'gear': self.current_gear
        }


class AeoniskCharacterGenerator:
    """Generates proper Aeonisk characters with family lines and realistic names."""
    
    # From the lore - actual family lines
    FAMILY_LINES = {
        'Sovereign Nexus': ['Elaras', 'Halessan', 'Ireveth', 'Unified Hand'],
        'Astral Commerce Group': ['Vireya', 'Ledger-Kaine', 'Exchange'],
        'Tempest Industries': ['Karsel', 'Dissolution', 'Liberty-Void'],
        'Arcane Genetics': ['Vireya', 'Catalyst', 'Morph-Prime'],
        'Aether Dynamics': ['Resonance', 'Ley-Walker', 'Current'],
        'Pantheon Security': ['Guardian', 'Shield-Bearer', 'Tactical'],
        'House of Vox': ['Broadcast', 'Echo-Song', 'Transmission'],
        'Resonance Communes': ['Harmony', 'Pulse', 'Wavelength'],
        'Freeborn': ['Unbound', 'Wild-Current', 'Free-Sky', 'Natural']
    }
    
    # Proper given names that fit the setting
    GIVEN_NAMES = [
        'Irele', 'Zara', 'Echo', 'Aurora', 'Void', 'Storm', 'Gene', 'Credit', 
        'Resonance', 'Free', 'Wild', 'Harmony', 'Pulse', 'Drift', 'Catalyst',
        'Nexus', 'Continuity', 'Liberty', 'Dissolution', 'Spark', 'Current',
        'Weave', 'Morph', 'Exchange', 'Unity', 'Breach', 'Cascade', 'Flow'
    ]
    
    @classmethod
    def generate_character(cls, faction: str = None) -> AeoniskCharacter:
        """Generate a character with proper Aeonisk naming and background."""
        
        if not faction:
            faction = random.choice(list(cls.FAMILY_LINES.keys()))
            
        family_line = random.choice(cls.FAMILY_LINES[faction])
        given_name = random.choice(cls.GIVEN_NAMES)
        
        # Create full name in Aeonisk style
        full_name = f"{given_name} {family_line}"
        
        # Generate attributes (YAGS standard: 2-5, average 3)
        char = AeoniskCharacter(
            name=given_name,
            full_name=full_name,
            origin_faction=faction,
            family_line=family_line,
            strength=random.randint(2, 5),
            health=random.randint(2, 5),
            agility=random.randint(2, 5),
            dexterity=random.randint(2, 5),
            perception=random.randint(2, 5),
            intelligence=random.randint(2, 5),
            empathy=random.randint(2, 5),
            willpower=random.randint(2, 5)
        )
        
        # Faction-specific skill adjustments
        if faction == 'Sovereign Nexus':
            char.astral_arts = random.randint(3, 6)
            char.charm = random.randint(3, 5)
        elif faction == 'Astral Commerce Group':
            char.guile = random.randint(3, 6)
            char.charm = random.randint(3, 5)
            char.soulcredit = random.randint(2, 5)
        elif faction == 'Tempest Industries':
            char.hacking = random.randint(3, 6)
            char.stealth = random.randint(3, 5)
            char.void_score = random.randint(1, 3)
        elif faction == 'Arcane Genetics':
            char.awareness = random.randint(3, 5)
            char.astral_arts = random.randint(2, 4)
        elif faction == 'Freeborn':
            char.athletics = random.randint(3, 6)
            char.stealth = random.randint(3, 5)
            char.birth_method = 'natural'
            
        # Generate ritual item
        ritual_items = {
            'Sovereign Nexus': ['Covenant Ring', 'Harmony Sigil', 'Unity Crystal'],
            'Astral Commerce Group': ['Ledger Stone', 'Contract Seal', 'Credit Matrix'],
            'Tempest Industries': ['Void Shard', 'Chaos Anchor', 'Dissolution Key'],
            'Arcane Genetics': ['Gene Helix', 'Bio-Catalyst', 'Evolution Seed'],
            'Freeborn': ['Wild Stone', 'Free Spirit Token', 'Natural Focus']
        }
        
        char.primary_ritual_item = random.choice(ritual_items.get(faction, ['Unknown Focus']))
        
        # Basic gear
        char.current_gear = [
            char.primary_ritual_item,
            'Standard Commlink',
            'Elemental Talisman (mixed)',
            'Personal Effects'
        ]
        
        return char


class LLMGameMaster:
    """Uses LLM to act as game master, generating scenarios and responses."""
    
    def __init__(self, llm_model: str = "gpt-4", temperature: float = 0.7):
        self.model = llm_model
        self.temperature = temperature
        self.session_context = ""
        
    async def generate_scenario(self, characters: List[AeoniskCharacter]) -> Dict[str, Any]:
        """Generate an Aeonisk scenario using LLM."""
        
        char_descriptions = []
        for char in characters:
            char_descriptions.append(
                f"- {char.full_name} ({char.origin_faction}, {char.family_line} Line): "
                f"Void {char.void_score}, Soulcredit {char.soulcredit}, "
                f"notable skills: {char.astral_arts} Astral Arts"
            )
            
        char_summary = "\n".join(char_descriptions)
        
        prompt = f"""You are generating a scenario for Aeonisk YAGS, a science-fantasy tabletop RPG where:
- Factions compete over Bonds, Soulcredit, and spiritual power
- Void corruption spreads through failed rituals and unethical acts
- Technology is powered by elemental talismans and spiritual energy
- Family lines have deep political/spiritual significance

Party composition:
{char_summary}

Generate an Aeonisk scenario with:
1. A compelling theme involving faction politics, void corruption, or bond betrayal
2. A specific location with spiritual/technological significance
3. Clear stakes that matter to these specific characters
4. Environmental complications related to void influence or ley line disruption

Return JSON with: theme, location, stakes, complication, void_influence_level (1-10), key_npcs"""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            
            # Try to parse as JSON, fall back to structured generation
            try:
                return json.loads(content)
            except:
                # Fallback structured scenario
                return {
                    "theme": "Corporate Memory Theft Investigation",
                    "location": "Abandoned Biocreche Facility",
                    "stakes": "Prevent stolen memories from destabilizing faction alliances",
                    "complication": "Void corruption from failed memory extraction rituals",
                    "void_influence_level": random.randint(3, 7),
                    "key_npcs": ["Corrupted Facility AI", "Rogue Memory Broker"]
                }
                
        except Exception as e:
            print(f"LLM Error: {e}, using fallback scenario")
            return {
                "theme": "Void Corruption Investigation", 
                "location": "Destabilized Ley Line Nexus",
                "stakes": "Prevent reality breakdown threatening multiple family lines",
                "complication": "Unstable astral currents affecting all technology",
                "void_influence_level": 5,
                "key_npcs": ["Void-touched Researcher", "Desperate Faction Agent"]
            }
    
    async def generate_character_action(self, character: AeoniskCharacter, scenario: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Generate a character's action using LLM."""
        
        prompt = f"""You are playing {character.full_name} from the {character.family_line} Line of {character.origin_faction}.

Character Details:
- Attributes: Str {character.strength}, Agi {character.agility}, Per {character.perception}, Int {character.intelligence}, Emp {character.empathy}, Wil {character.willpower}
- Key Skills: Astral Arts {character.astral_arts}, Athletics {character.athletics}, Stealth {character.stealth}, Guile {character.guile}
- Void Score: {character.void_score}/10 (corruption level)
- Soulcredit: {character.soulcredit} (spiritual standing)
- Ritual Item: {character.primary_ritual_item}

Current Scenario: {scenario['theme']}
Location: {scenario['location']}
Stakes: {scenario['stakes']}
Void Level: {scenario['void_influence_level']}/10

Context: {context}

As this character, choose an action that fits their faction background, family line, and personal stats. Consider:
- Sovereign Nexus values harmony and proper procedure
- Astral Commerce Group focuses on contracts and deals
- Tempest Industries embraces chaos and void research
- Arcane Genetics pursues biological/genetic advancement
- Freeborn reject authority and bonds

Return JSON with:
- action_type: (investigate, ritual_attempt, social_interaction, combat, exploration, corporate_maneuver)
- description: Detailed narrative of what the character does
- target_attribute: Which attribute they'd use (strength, agility, perception, intelligence, empathy, willpower)  
- target_skill: Which skill they'd use (athletics, awareness, astral_arts, stealth, guile, etc.)
- reasoning: Why this character would take this action"""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            
            try:
                return json.loads(content)
            except:
                # Fallback action based on faction
                fallback_actions = {
                    'Sovereign Nexus': {
                        'action_type': 'ritual_attempt',
                        'description': f'{character.name} attempts to harmonize the disrupted ley energies using their {character.primary_ritual_item}',
                        'target_attribute': 'willpower',
                        'target_skill': 'astral_arts',
                        'reasoning': 'Sovereign Nexus prioritizes restoring harmony and order'
                    },
                    'Tempest Industries': {
                        'action_type': 'investigation', 
                        'description': f'{character.name} investigates the void corruption patterns to understand their source',
                        'target_attribute': 'intelligence',
                        'target_skill': 'awareness',
                        'reasoning': 'Tempest Industries seeks to understand and exploit void phenomena'
                    }
                }
                
                return fallback_actions.get(character.origin_faction, {
                    'action_type': 'exploration',
                    'description': f'{character.name} explores the area cautiously',
                    'target_attribute': 'perception',
                    'target_skill': 'awareness',
                    'reasoning': 'Default cautious exploration'
                })
                
        except Exception as e:
            print(f"LLM Error generating action: {e}")
            return {
                'action_type': 'investigation',
                'description': f'{character.name} investigates the situation',
                'target_attribute': 'intelligence', 
                'target_skill': 'awareness',
                'reasoning': 'Fallback investigation action'
            }
    
    async def generate_outcome_narrative(self, character: AeoniskCharacter, action: Dict[str, Any], 
                                       roll_result: int, margin: int, success: bool) -> Dict[str, Any]:
        """Generate detailed outcome narrative using LLM."""
        
        prompt = f"""Generate an Aeonisk YAGS outcome for:

Character: {character.full_name} ({character.origin_faction})
Action: {action['description']}
Roll Result: {roll_result} (Margin: {margin}, Success: {success})

Create vivid narrative outcomes following the Aeonisk dataset format with six tiers:
- exceptional_success (margin 20+): Amazing results with major advantages
- excellent_success (margin 10-19): Great results with clear benefits  
- good_success (margin 5-9): Solid success with minor benefits
- moderate_success (margin 0-4): Basic success, objective achieved
- failure (margin -1 to -9): Action fails with complications
- critical_failure (margin -10+): Catastrophic failure with major consequences

Consider Aeonisk themes: void corruption, soulcredit, bonds, family honor, faction politics.

Return JSON with outcome tier and detailed narrative describing what happens."""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            print(f"LLM Error generating outcome: {e}")
            
            # Fallback outcome generation
            if success:
                if margin >= 20:
                    return {
                        "tier": "exceptional_success",
                        "narrative": f"{character.name}'s action succeeds spectacularly, achieving far more than intended."
                    }
                elif margin >= 10:
                    return {
                        "tier": "excellent_success", 
                        "narrative": f"{character.name} achieves excellent results with clear benefits."
                    }
                else:
                    return {
                        "tier": "moderate_success",
                        "narrative": f"{character.name} successfully completes their intended action."
                    }
            else:
                if margin <= -10:
                    return {
                        "tier": "critical_failure",
                        "narrative": f"{character.name}'s action backfires catastrophically."
                    }
                else:
                    return {
                        "tier": "failure",
                        "narrative": f"{character.name}'s action fails with complications."
                    }


class LLMMultiAgentSession:
    """Main session orchestrator using LLMs for narrative generation."""
    
    def __init__(self, llm_model: str = "gpt-4"):
        self.gm = LLMGameMaster(llm_model)
        self.characters: List[AeoniskCharacter] = []
        self.scenario: Dict[str, Any] = {}
        self.session_log: List[Dict[str, Any]] = []
        self.dataset_entries: List[Dict[str, Any]] = []
        
    def generate_party(self, size: int = 3) -> List[AeoniskCharacter]:
        """Generate a diverse party with proper faction representation."""
        major_factions = ['Sovereign Nexus', 'Astral Commerce Group', 'Tempest Industries', 'Arcane Genetics']
        
        party = []
        for i in range(size):
            if i < len(major_factions):
                faction = major_factions[i]
            else:
                faction = random.choice(major_factions + ['Freeborn', 'Aether Dynamics'])
                
            char = AeoniskCharacterGenerator.generate_character(faction)
            party.append(char)
            
        self.characters = party
        return party
    
    def calculate_difficulty(self, action_type: str, void_level: int) -> int:
        """Calculate YAGS difficulty based on action and environment."""
        base_difficulties = {
            'investigate': 18,
            'ritual_attempt': 20,
            'social_interaction': 16,
            'combat': 15,
            'exploration': 15,
            'corporate_maneuver': 20
        }
        
        base = base_difficulties.get(action_type, 18)
        # Void influence makes things harder
        return base + (void_level // 2)
    
    def make_skill_check(self, character: AeoniskCharacter, attribute: str, skill: str, difficulty: int) -> Tuple[bool, int, int]:
        """Make a YAGS skill check."""
        attr_val = getattr(character, attribute.lower())
        skill_val = getattr(character, skill.lower().replace('_', ''))
        
        roll = random.randint(1, 20)
        total = (attr_val * skill_val) + roll
        
        success = total >= difficulty
        margin = total - difficulty
        
        return success, total, margin
    
    async def create_dataset_entry(self, character: AeoniskCharacter, action: Dict[str, Any], 
                                 roll_result: int, margin: int, difficulty: int,
                                 outcome: Dict[str, Any]) -> Dict[str, Any]:
        """Create a dataset entry in the proper format."""
        
        task_id = f"YAGS-AEONISK-{len(self.dataset_entries) + 1:03d}"
        
        # Get outcome for all tiers using LLM
        outcome_prompt = f"""Generate all six outcome tiers for this Aeonisk YAGS action:

Character: {character.full_name} 
Action: {action['description']}
Skill Check: {action['target_attribute']} × {action['target_skill']} vs {difficulty}

Create narrative and mechanical effects for each tier following the dataset format:
- critical_failure (margin ≤ -10)  
- failure (margin -9 to -1)
- moderate_success (margin 0-4)
- good_success (margin 5-9)
- excellent_success (margin 10-19)
- exceptional_success (margin ≥ 20)

Include vivid Aeonisk-specific consequences involving void, soulcredit, bonds, technology failures, family honor."""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model=self.gm.model,
                messages=[{"role": "user", "content": outcome_prompt}],
                temperature=0.7
            )
            
            outcome_explanation = json.loads(response.choices[0].message.content)
            
        except Exception as e:
            print(f"Error generating outcomes: {e}")
            outcome_explanation = {
                "critical_failure": {
                    "narrative": f"{character.name}'s action fails catastrophically.",
                    "mechanical_effect": "+2 Void, equipment damaged"
                },
                "failure": {
                    "narrative": f"{character.name}'s action fails with complications.", 
                    "mechanical_effect": "+1 Void or minor consequence"
                },
                "moderate_success": {
                    "narrative": f"{character.name} achieves their basic objective.",
                    "mechanical_effect": "Objective completed"
                },
                "good_success": {
                    "narrative": f"{character.name} succeeds with style.",
                    "mechanical_effect": "Objective completed with advantage"
                },
                "excellent_success": {
                    "narrative": f"{character.name} achieves excellent results.",
                    "mechanical_effect": "Major advantage gained"
                },
                "exceptional_success": {
                    "narrative": f"{character.name} achieves legendary results.",
                    "mechanical_effect": "Exceptional advantage, possible +1 Soulcredit"
                }
            }
        
        entry = {
            'task_id': task_id,
            'domain': {
                'core': 'rule_application',
                'subdomain': f'skill_check_{action["target_skill"]}'
            },
            'scenario': action['description'],
            'environment': f"{self.scenario['location']}; void level {self.scenario['void_influence_level']}/10",
            'stakes': self.scenario['stakes'],
            'characters': [character.to_dataset_format()],
            'goal': f"Identify attribute and skill for {action['action_type']}, compute roll formula and difficulty, describe outcomes.",
            'expected_fields': [
                'attribute_used',
                'skill_used', 
                'roll_formula',
                'difficulty_guess',
                'outcome_explanation',
                'rationale'
            ],
            'gold_answer': {
                'attribute_used': action['target_attribute'].title(),
                'skill_used': action['target_skill'].title().replace('_', ' '),
                'roll_formula': f"{action['target_attribute'].title()} {getattr(character, action['target_attribute'])} x {action['target_skill'].title()} {getattr(character, action['target_skill'])} = {getattr(character, action['target_attribute']) * getattr(character, action['target_skill'])}; result + d20",
                'difficulty_guess': difficulty,
                'outcome_explanation': outcome_explanation,
                'rationale': f"{action['reasoning']} YAGS difficulty {difficulty} reflects environmental complications."
            },
            'aeonisk_extra_data': {
                'module': 'yags-aeonisk',
                'version': 'v1.2.1',
                'family_line': character.family_line,
                'void_influence': self.scenario['void_influence_level']
            }
        }
        
        return entry
    
    async def run_session(self, max_turns: int = 6):
        """Run a complete LLM-powered Aeonisk session."""
        
        print("=== LLM-Powered Aeonisk YAGS Session ===")
        print("Using GPT-4 for narrative generation and character agency\n")
        
        # Generate party
        print("--- Party Generation ---")
        party = self.generate_party(3)
        
        for char in party:
            print(f"\n{char.full_name}")
            print(f"  Family Line: {char.family_line} Line ({char.origin_faction})")
            print(f"  Stats: Str {char.strength}, Agi {char.agility}, Per {char.perception}, Int {char.intelligence}")
            print(f"  Spirit: Void {char.void_score}/10, Soulcredit {char.soulcredit}")
            print(f"  Key Skills: Astral Arts {char.astral_arts}, Stealth {char.stealth}")
            print(f"  Ritual Focus: {char.primary_ritual_item}")
            
        # Generate scenario using LLM
        print(f"\n--- Scenario Generation (via {self.gm.model}) ---") 
        scenario = await self.gm.generate_scenario(party)
        self.scenario = scenario
        
        print(f"Theme: {scenario['theme']}")
        print(f"Location: {scenario['location']}")
        print(f"Stakes: {scenario['stakes']}")
        print(f"Void Influence: {scenario['void_influence_level']}/10")
        
        # Run turns
        context = f"The party arrives at {scenario['location']}. {scenario['complication']}"
        
        for turn in range(1, max_turns + 1):
            print(f"\n=== Turn {turn} ===")
            
            for character in party:
                # LLM generates character action
                action = await self.gm.generate_character_action(character, scenario, context)
                
                print(f"\n[{character.name} {character.family_line}] {action['description']}")
                
                # Calculate skill check
                difficulty = self.calculate_difficulty(action['action_type'], scenario['void_influence_level'])
                success, total, margin = self.make_skill_check(
                    character, action['target_attribute'], action['target_skill'], difficulty
                )
                
                print(f"  Roll: {action['target_attribute'].title()} × {action['target_skill'].title()} + d20 = {total}")
                print(f"  vs Difficulty {difficulty} → {'Success' if success else 'Failure'} (margin: {margin:+d})")
                
                # LLM generates outcome narrative
                outcome = await self.gm.generate_outcome_narrative(character, action, total, margin, success)
                print(f"  Result: {outcome.get('narrative', 'Action resolves')}")
                
                # Create dataset entry
                dataset_entry = await self.create_dataset_entry(character, action, total, margin, difficulty, outcome)
                self.dataset_entries.append(dataset_entry)
                
                # Update character based on results
                if not success and margin <= -5:
                    character.void_score = min(10, character.void_score + 1)
                    print(f"  → Void increased to {character.void_score}/10")
                elif success and margin >= 10:
                    character.soulcredit = min(10, character.soulcredit + 1)  
                    print(f"  → Soulcredit increased to {character.soulcredit}")
                    
                # Update context for next character
                context += f" {character.name} {action['description']} with {outcome.get('tier', 'mixed')} results."
                
            await asyncio.sleep(1)  # Brief pause
        
        # Save dataset entries
        await self.save_dataset()
        
        print(f"\n=== Session Complete ===")
        print(f"Generated {len(self.dataset_entries)} dataset entries")
        print("Ready for AI training!")
        
    async def save_dataset(self):
        """Save generated dataset entries."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save as YAML (dataset format)
        yaml_file = Path(f'./llm_generated_dataset_{timestamp}.yaml')
        with open(yaml_file, 'w') as f:
            yaml.dump_all(self.dataset_entries, f, default_flow_style=False, sort_keys=False)
            
        # Save as JSON for processing
        json_file = Path(f'./llm_session_data_{timestamp}.json')
        with open(json_file, 'w') as f:
            json.dump({
                'session_id': f'llm_aeonisk_{timestamp}',
                'scenario': self.scenario,
                'characters': [asdict(c) for c in self.characters],
                'dataset_entries': self.dataset_entries
            }, f, indent=2, default=str)
            
        print(f"\nDataset saved to: {yaml_file}")
        print(f"Session data saved to: {json_file}")


async def main():
    """Run an LLM-powered Aeonisk session."""
    
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: Please set OPENAI_API_KEY environment variable")
        return
        
    session = LLMMultiAgentSession(llm_model="gpt-4")
    await session.run_session()


if __name__ == "__main__":
    asyncio.run(main())