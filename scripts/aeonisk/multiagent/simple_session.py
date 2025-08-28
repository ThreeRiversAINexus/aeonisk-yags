"""
Simplified self-playing session that focuses on AI agents actually playing the game.
"""

import asyncio
import json
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml

logger = logging.getLogger(__name__)


class AeoniskCharacter:
    """An Aeonisk character with YAGS mechanics."""
    
    def __init__(self, name: str, faction: str):
        self.name = name
        self.faction = faction
        
        # YAGS attributes (human average is 3)
        self.attributes = {
            'Body': random.randint(2, 6),
            'Agility': random.randint(2, 6), 
            'Mind': random.randint(2, 6),
            'Soul': random.randint(2, 6),
            'Strength': random.randint(2, 6),
            'Health': random.randint(2, 6),
            'Will': random.randint(2, 6),
            'Perception': random.randint(2, 6)
        }
        
        # Key Aeonisk skills
        self.skills = {
            'Astral Arts': random.randint(1, 5),
            'Investigation': random.randint(1, 4),
            'Social': random.randint(1, 4),
            'Melee': random.randint(1, 3),
            'Ranged': random.randint(1, 3),
            'Athletics': random.randint(1, 3),
            'Magick Theory': random.randint(0, 3),
            'Intimacy Ritual': random.randint(0, 3),
            'Corporate Influence': random.randint(0, 3) if faction in ['Tempest Industries', 'Astral Commerce Group'] else 0
        }
        
        # Aeonisk-specific attributes
        self.void_score = 0  # 0-10, corruption
        self.soulcredit = random.randint(8, 15)  # spiritual economy
        self.bonds = []  # formal connections
        
        # Birth method (from lore)
        self.birth_method = 'biocreche_pod' if faction != 'Freeborn' else 'natural'
        
        # Personality traits that drive AI decisions
        self.personality = self._generate_personality()
        self.goals = self._generate_goals()
        
    def _generate_personality(self) -> Dict[str, int]:
        """Generate personality based on faction."""
        base = {
            'risk_tolerance': 5,
            'void_curiosity': 3,
            'bond_preference': 5,  # 1=avoids, 10=seeks
            'ritual_conservatism': 5,
            'faction_loyalty': 5
        }
        
        # Faction modifications
        if self.faction == 'Tempest Industries':
            base.update({
                'risk_tolerance': 8,
                'void_curiosity': 8,
                'bond_preference': 2,
                'ritual_conservatism': 2,
                'faction_loyalty': 7
            })
        elif self.faction == 'Sovereign Nexus':
            base.update({
                'risk_tolerance': 3,
                'bond_preference': 8,
                'ritual_conservatism': 7,
                'faction_loyalty': 9
            })
        elif self.faction == 'Resonance Communes':
            base.update({
                'bond_preference': 9,
                'ritual_conservatism': 3,
                'faction_loyalty': 6
            })
        elif self.faction == 'Freeborn':
            base.update({
                'risk_tolerance': 7,
                'void_curiosity': 7,
                'bond_preference': 2,
                'ritual_conservatism': 2,
                'faction_loyalty': 1
            })
            
        return base
    
    def _generate_goals(self) -> List[str]:
        """Generate character goals based on faction and personality."""
        goals = []
        
        if self.personality['void_curiosity'] > 6:
            goals.append("Explore and understand void manipulation")
        if self.personality['bond_preference'] > 6:
            goals.append("Form meaningful bonds with others")
        if self.personality['faction_loyalty'] > 6:
            goals.append(f"Advance the interests of {self.faction}")
        if self.skills['Astral Arts'] > 3:
            goals.append("Master advanced ritual techniques")
            
        # Faction-specific goals
        if self.faction == 'Tempest Industries':
            goals.append("Push boundaries of void research")
        elif self.faction == 'Sovereign Nexus':
            goals.append("Maintain harmony and continuity")
        elif self.faction == 'Resonance Communes':
            goals.append("Support community bonds")
        elif self.faction == 'Freeborn':
            goals.append("Preserve independence from faction control")
            
        return goals[:3]  # Max 3 goals
    
    def make_skill_check(self, attribute: str, skill: str, difficulty: int = 20) -> Tuple[bool, int, str]:
        """Make a YAGS skill check: Attribute × Skill + d20 vs Difficulty."""
        attr_score = self.attributes.get(attribute, 3)
        skill_score = self.skills.get(skill, 0)
        
        roll = random.randint(1, 20)
        total = (attr_score * skill_score) + roll
        
        success = total >= difficulty
        margin = total - difficulty
        
        # Generate outcome description
        if success:
            if margin >= 15:
                outcome = "exceptional success"
            elif margin >= 5:
                outcome = "clear success"
            else:
                outcome = "narrow success"
        else:
            if margin <= -15:
                outcome = "critical failure"
            elif margin <= -5:
                outcome = "clear failure"
            else:
                outcome = "narrow failure"
                
        return success, total, outcome
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for data collection."""
        return {
            'name': self.name,
            'faction': self.faction,
            'attributes': self.attributes,
            'skills': self.skills,
            'void_score': self.void_score,
            'soulcredit': self.soulcredit,
            'bonds': self.bonds,
            'birth_method': self.birth_method,
            'personality': self.personality,
            'goals': self.goals
        }


class SimpleAeoniskSession:
    """A simplified self-playing Aeonisk session."""
    
    def __init__(self):
        self.characters: List[AeoniskCharacter] = []
        self.session_data: List[Dict[str, Any]] = []
        self.current_scenario = None
        self.turn_count = 0
        
    def create_characters(self, count: int = 3) -> List[AeoniskCharacter]:
        """Create a party of AI characters."""
        factions = ['Tempest Industries', 'Sovereign Nexus', 'Resonance Communes', 'Freeborn', 'Astral Commerce Group']
        
        names = {
            'Tempest Industries': ['Zara Nightwhisper', 'Void Kaine', 'Storm Celeste'],
            'Sovereign Nexus': ['Aurora Harmony', 'Echo Continuity', 'Pulse Unity'],
            'Resonance Communes': ['River Resonance', 'Song Wavelength', 'Chorus Bond'],
            'Freeborn': ['Wild Sky', 'Free Current', 'Unbound Drift'],
            'Astral Commerce Group': ['Credit Exchange', 'Value Ledger', 'Profit Margin']
        }
        
        characters = []
        used_factions = []
        
        for i in range(count):
            # Ensure diverse party
            available_factions = [f for f in factions if f not in used_factions or len(used_factions) >= len(factions)]
            if not available_factions:
                available_factions = factions
                
            faction = random.choice(available_factions)
            used_factions.append(faction)
            
            name = random.choice(names[faction])
            char = AeoniskCharacter(name, faction)
            characters.append(char)
            
        self.characters = characters
        return characters
        
    def generate_scenario(self) -> Dict[str, Any]:
        """Generate an Aeonisk scenario using lore elements."""
        themes = [
            "Void Corruption Investigation",
            "Bond Betrayal Crisis", 
            "Faction Politics Intrigue",
            "Ancient Astral Artifact Discovery",
            "Corporate Espionage Operation",
            "Soulcredit Debt Collection",
            "Ritual Gone Wrong",
            "Memory Theft Investigation"
        ]
        
        locations = [
            "Abandoned Astral Node",
            "Nexus Council Chamber",
            "Corporate Facility",
            "Resonance Commune Sanctuary",
            "Freeborn Settlement",
            "Void-touched Ruins",
            "Biocreche Pod Facility",
            "Interstellar Transport Hub"
        ]
        
        complications = [
            "Void influence is spreading",
            "A trusted bond has been severed",
            "Corporate interests conflict",
            "Ancient memories are surfacing", 
            "Soulcredit debts are being called in",
            "Ritual components are corrupted",
            "Political alliances are shifting",
            "The Codex is recording everything"
        ]
        
        scenario = {
            'theme': random.choice(themes),
            'location': random.choice(locations),
            'complication': random.choice(complications),
            'void_level': random.randint(1, 5),
            'stakes': 'moderate'
        }
        
        self.current_scenario = scenario
        return scenario
        
    def ai_character_action(self, character: AeoniskCharacter, scenario: Dict[str, Any], other_characters: List[AeoniskCharacter]) -> Dict[str, Any]:
        """Generate an AI character's action based on personality and scenario."""
        
        # Action types available in Aeonisk
        action_types = ['investigate', 'social_interaction', 'ritual_attempt', 'exploration', 'tactical', 'bond_action']
        
        # Weight actions based on personality
        weights = {}
        
        if character.personality['void_curiosity'] > 6 and 'void' in scenario['theme'].lower():
            weights['investigate'] = 3
            weights['ritual_attempt'] = 2
        
        if character.personality['bond_preference'] > 6:
            weights['social_interaction'] = 3
            weights['bond_action'] = 2
            
        if character.personality['risk_tolerance'] > 6:
            weights['exploration'] = 2
            weights['tactical'] = 2
        
        if character.skills['Astral Arts'] > 3:
            weights['ritual_attempt'] = 2
            
        # Default weights
        for action_type in action_types:
            if action_type not in weights:
                weights[action_type] = 1
                
        # Choose action based on weights
        action_choices = []
        for action_type, weight in weights.items():
            action_choices.extend([action_type] * weight)
            
        chosen_action_type = random.choice(action_choices)
        
        # Generate specific action based on type
        action = self._generate_specific_action(character, chosen_action_type, scenario, other_characters)
        
        return action
        
    def _generate_specific_action(self, character: AeoniskCharacter, action_type: str, scenario: Dict[str, Any], others: List[AeoniskCharacter]) -> Dict[str, Any]:
        """Generate specific action details."""
        
        if action_type == 'investigate':
            targets = ['the void disturbance', 'corporate records', 'memory fragments', 'astral traces', 'the facility']
            target = random.choice(targets)
            
            # Use Mind + Investigation
            success, total, outcome = character.make_skill_check('Mind', 'Investigation', 15 + scenario['void_level'])
            
            return {
                'type': 'investigate',
                'description': f"{character.name} investigates {target}",
                'skill_used': 'Investigation',
                'attribute_used': 'Mind',
                'roll_result': total,
                'success': success,
                'outcome': outcome,
                'consequences': self._generate_consequences(character, success, action_type, scenario)
            }
            
        elif action_type == 'social_interaction':
            if others:
                target = random.choice(others)
                interactions = ['attempts to form a bond with', 'shares information with', 'seeks support from', 'confronts']
                interaction = random.choice(interactions)
                
                success, total, outcome = character.make_skill_check('Soul', 'Social', 18)
                
                return {
                    'type': 'social_interaction',
                    'description': f"{character.name} {interaction} {target.name}",
                    'target': target.name,
                    'skill_used': 'Social',
                    'attribute_used': 'Soul',
                    'roll_result': total,
                    'success': success,
                    'outcome': outcome,
                    'consequences': self._generate_consequences(character, success, action_type, scenario)
                }
            else:
                return self._generate_specific_action(character, 'exploration', scenario, others)
                
        elif action_type == 'ritual_attempt':
            rituals = ['astral navigation', 'void channeling', 'bond strengthening', 'memory reading', 'corporate influence']
            ritual = random.choice(rituals)
            
            # Willpower × Astral Arts + d20 vs Ritual Threshold
            difficulty = 16 + scenario['void_level'] + random.randint(0, 4)
            success, total, outcome = character.make_skill_check('Will', 'Astral Arts', difficulty)
            
            # Ritual consequences
            consequences = []
            if success:
                consequences.append("Ritual succeeds with intended effect")
                character.soulcredit += 1
            else:
                consequences.append("Ritual backfires")
                character.void_score += 1
                character.soulcredit -= 1
                
            return {
                'type': 'ritual_attempt',
                'description': f"{character.name} attempts {ritual} ritual",
                'ritual_name': ritual,
                'skill_used': 'Astral Arts',
                'attribute_used': 'Will',
                'roll_result': total,
                'success': success,
                'outcome': outcome,
                'consequences': consequences,
                'void_gained': 0 if success else 1,
                'soulcredit_change': 1 if success else -1
            }
            
        elif action_type == 'exploration':
            locations = ['deeper into the facility', 'toward the void disturbance', 'through corporate archives', 'into restricted areas']
            location = random.choice(locations)
            
            success, total, outcome = character.make_skill_check('Perception', 'Athletics', 16)
            
            return {
                'type': 'exploration',
                'description': f"{character.name} explores {location}",
                'skill_used': 'Athletics', 
                'attribute_used': 'Perception',
                'roll_result': total,
                'success': success,
                'outcome': outcome,
                'consequences': self._generate_consequences(character, success, action_type, scenario)
            }
            
        else:  # Default to investigation
            return self._generate_specific_action(character, 'investigate', scenario, others)
            
    def _generate_consequences(self, character: AeoniskCharacter, success: bool, action_type: str, scenario: Dict[str, Any]) -> List[str]:
        """Generate consequences for actions."""
        consequences = []
        
        if success:
            consequences.append("Action succeeds as intended")
            if action_type == 'social_interaction':
                consequences.append("Relationship improved")
            elif action_type == 'investigate':
                consequences.append("Valuable information discovered")
            elif action_type == 'exploration':
                consequences.append("New area or opportunity found")
        else:
            consequences.append("Action fails with complications")
            if scenario['void_level'] > 3 and random.random() < 0.3:
                character.void_score += 1
                consequences.append("Void influence increases")
                
        return consequences
        
    def run_turn(self, turn_number: int) -> List[Dict[str, Any]]:
        """Run a single turn for all characters."""
        print(f"\n=== Turn {turn_number} ===")
        
        turn_actions = []
        
        for character in self.characters:
            others = [c for c in self.characters if c != character]
            action = self.ai_character_action(character, self.current_scenario, others)
            turn_actions.append(action)
            
            # Display action
            print(f"\n[{character.name} - {character.faction}]")
            print(f"  Action: {action['description']}")
            print(f"  Roll: {action['roll_result']} ({action['outcome']})")
            
            if 'consequences' in action:
                for consequence in action['consequences']:
                    print(f"  → {consequence}")
                    
            # Update character state
            if 'void_gained' in action:
                character.void_score += action['void_gained']
            if 'soulcredit_change' in action:
                character.soulcredit += action['soulcredit_change']
                
        return turn_actions
        
    async def run_session(self, max_turns: int = 10) -> Dict[str, Any]:
        """Run a complete self-playing session."""
        
        print("=== Aeonisk Self-Playing Session ===")
        
        # Create characters
        print("\n--- Character Generation ---")
        characters = self.create_characters(3)
        for char in characters:
            print(f"\n{char.name} ({char.faction})")
            print(f"  Void Score: {char.void_score}, Soulcredit: {char.soulcredit}")
            print(f"  Goals: {', '.join(char.goals)}")
            print(f"  Key Skills: Astral Arts {char.skills['Astral Arts']}, Investigation {char.skills['Investigation']}")
            
        # Generate scenario
        print("\n--- Scenario Setup ---")
        scenario = self.generate_scenario()
        print(f"Theme: {scenario['theme']}")
        print(f"Location: {scenario['location']}")
        print(f"Complication: {scenario['complication']}")
        print(f"Void Level: {scenario['void_level']}/10")
        
        # Run turns
        all_actions = []
        for turn in range(1, max_turns + 1):
            turn_actions = self.run_turn(turn)
            all_actions.extend(turn_actions)
            
            # Brief pause for readability
            await asyncio.sleep(0.5)
            
            # Check for dramatic developments
            total_void = sum(c.void_score for c in self.characters)
            if total_void > 15:
                print("\n!!! The void influence grows too strong! !!!")
                break
                
        # Session summary
        print(f"\n=== Session Summary ===")
        print(f"Turns completed: {min(turn, max_turns)}")
        print(f"Total actions: {len(all_actions)}")
        
        for char in self.characters:
            print(f"\n{char.name} final state:")
            print(f"  Void Score: {char.void_score}/10")
            print(f"  Soulcredit: {char.soulcredit}")
            
        # Compile session data
        session_data = {
            'session_id': f"simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'scenario': scenario,
            'characters': [char.to_dict() for char in self.characters],
            'actions': all_actions,
            'turns_completed': min(turn, max_turns),
            'end_time': datetime.now().isoformat()
        }
        
        return session_data
        
    def save_session_data(self, session_data: Dict[str, Any], output_dir: str = "./multiagent_output"):
        """Save session data."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save as JSON
        json_file = output_path / f"{session_data['session_id']}.json"
        with open(json_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)
            
        # Save as YAML for readability
        yaml_file = output_path / f"{session_data['session_id']}.yaml"
        
        # Convert any custom objects to dictionaries to avoid Python object serialization
        def safe_dict_conversion(obj):
            """Safely convert custom objects to dictionaries."""
            if hasattr(obj, '__dict__'):
                return {k: safe_dict_conversion(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, dict):
                return {k: safe_dict_conversion(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [safe_dict_conversion(item) for item in obj]
            else:
                return obj
        
        safe_session_data = safe_dict_conversion(session_data)
        
        with open(yaml_file, 'w') as f:
            yaml.dump(safe_session_data, f, default_flow_style=False)
            
        print(f"\nSession data saved to: {json_file}")
        return json_file