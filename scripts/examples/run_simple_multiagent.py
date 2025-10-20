#!/usr/bin/env python3
"""
Simple Aeonisk YAGS Multi-Agent Self-Playing Session

Uses the actual tabletop RPG mechanics from the markdown files to simulate
AI characters playing a real Aeonisk YAGS session together.
"""

import asyncio
import json
import random
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class AeoniskCharacter:
    """A proper Aeonisk YAGS character following the tabletop rules."""
    name: str
    origin: str  # Faction/background
    
    # YAGS 8 Attributes (human average = 3, range 2-5)
    strength: int = 3
    health: int = 3
    agility: int = 3
    dexterity: int = 3
    perception: int = 3
    intelligence: int = 3
    empathy: int = 3
    willpower: int = 3
    
    # Secondary attributes
    size: int = 5  # Human default
    move: int = 12  # Size + Str + Agi + 1
    soak: int = 12  # Human default
    
    # Core Aeonisk mechanics
    void_score: int = 0  # 0-10 corruption
    soulcredit: int = 0  # -10 to +10 spiritual standing
    bonds: List[str] = None  # Max 3 (Freeborn: 1)
    true_will: str = ""  # Declared during play
    
    # Birth method (from lore)
    birth_method: str = "biocreche_pod"  # or "natural" for Freeborn
    
    # Skills (Aeonisk-specific)
    astral_arts: int = 0  # Willpower skill - key for rituals
    magick_theory: int = 0  # Intelligence
    intimacy_ritual: int = 0  # Empathy
    corporate_influence: int = 0  # Empathy
    debt_law: int = 0  # Intelligence
    pilot: int = 0  # Agility
    drone_operation: int = 0  # Intelligence
    
    # YAGS Talents (everyone starts at 2)
    athletics: int = 2
    awareness: int = 2
    brawl: int = 2
    charm: int = 2
    guile: int = 2
    sleight: int = 2
    stealth: int = 2
    throw: int = 2
    
    # Ritual equipment
    primary_ritual_item: str = ""
    offerings: List[str] = None
    
    def __post_init__(self):
        if self.bonds is None:
            self.bonds = []
        if self.offerings is None:
            self.offerings = []
            
        # Calculate derived stats
        self.move = self.size + self.strength + self.agility + 1
        
        # Apply origin bonuses and traits
        self._apply_origin_effects()
        
    def _apply_origin_effects(self):
        """Apply origin attribute bonuses and traits."""
        origin_bonuses = {
            'Sovereign Nexus': {'willpower': 1, 'trait': 'Indoctrinated'},
            'Astral Commerce Group': {'intelligence': 1, 'trait': 'Contract-Bound', 'soulcredit': 1},
            'Pantheon Security': {'strength': 1, 'trait': 'Tactical Protocol'},
            'Aether Dynamics': {'empathy': 1, 'trait': 'Ley Sense'},
            'Arcane Genetics': {'health': 1, 'trait': 'Bio-Stabilized'},
            'Tempest Industries': {'dexterity': 1, 'trait': 'Disruptor'},
            'Freeborn': {'trait': 'Wild Will'}
        }
        
        if self.origin in origin_bonuses:
            bonus = origin_bonuses[self.origin]
            
            # Apply attribute bonus
            for attr in ['strength', 'health', 'agility', 'dexterity', 'perception', 'intelligence', 'empathy', 'willpower']:
                if attr in bonus:
                    setattr(self, attr, getattr(self, attr) + bonus[attr])
                    
            # Apply special effects
            if 'soulcredit' in bonus:
                self.soulcredit += bonus['soulcredit']
                
            if self.origin == 'Freeborn':
                self.birth_method = 'natural'
    
    def make_skill_check(self, attribute: str, skill: str, difficulty: int = 20) -> Tuple[bool, int, int, str]:
        """Make a YAGS skill check: Attribute × Skill + d20 vs Difficulty."""
        attr_val = getattr(self, attribute.lower())
        skill_val = getattr(self, skill.lower().replace(' ', '_'))
        
        roll = random.randint(1, 20)
        total = (attr_val * skill_val) + roll
        
        success = total >= difficulty
        margin = total - difficulty
        
        # Determine degree of success/failure
        if success:
            if margin >= 20:
                degree = "excellent success"
            elif margin >= 10:
                degree = "good success"
            else:
                degree = "moderate success"
        else:
            if margin <= -10:
                degree = "significant failure"
            else:
                degree = "simple failure"
                
        return success, total, margin, degree
    
    def make_ritual_check(self, ritual_threshold: int, has_offering: bool = True, bonded_assist: bool = False) -> Tuple[bool, int, int, str]:
        """Make an Aeonisk ritual check: Willpower × Astral Arts + d20 vs Ritual Threshold."""
        base_roll = (self.willpower * self.astral_arts) + random.randint(1, 20)
        
        # Bonded assistance
        if bonded_assist:
            base_roll += 2
            
        # No offering penalty
        void_gain = 0
        if not has_offering:
            void_gain = 1
            
        margin = base_roll - ritual_threshold
        
        # Determine outcome from margin table
        if margin <= -10:
            result = "catastrophic fumble"
            void_gain += 2
        elif margin <= -5:
            result = "failed with backlash"
            void_gain += 1
        elif margin <= -1:
            result = "simple failure"
        elif margin <= 4:
            result = "weak success"
        elif margin <= 9:
            result = "solid success"
        elif margin <= 14:
            result = "strong resonance"
        else:
            result = "echo/breakthrough"
            
        # Apply void gain
        if void_gain > 0:
            self.void_score = min(10, self.void_score + void_gain)
            
        return margin >= 0, base_roll, margin, result


class AeoniskScenario:
    """An Aeonisk scenario generator using the actual lore."""
    
    @staticmethod
    def generate() -> Dict[str, Any]:
        themes = [
            "Void Corruption Investigation",
            "Bond Betrayal Crisis", 
            "Faction Contract Dispute",
            "Ancient Astral Artifact",
            "Corporate Memory Theft",
            "Soulcredit Debt Crisis",
            "Ritual Sabotage Plot",
            "Biocreche Pod Malfunction",
            "Ley Line Disruption"
        ]
        
        locations = [
            "Abandoned Astral Node",
            "Nexus Covenant Ring",
            "Corporate Memory Vault",
            "Resonance Commune Sanctuary", 
            "Freeborn Settlement",
            "Void-touched Archive",
            "Biocreche Facility",
            "Elemental Talisman Exchange",
            "Ley Line Convergence"
        ]
        
        complications = [
            "Void corruption is spreading through the area",
            "A crucial Bond has been severed under suspicious circumstances", 
            "Corporate factions are manipulating contracts behind the scenes",
            "Ancient memories are bleeding through from the Astral",
            "Soulcredit debts are being weaponized for political control",
            "Someone is sabotaging rituals to destabilize the community",
            "The Codex itself appears to be recording false information",
            "Elemental talismans are being drained of their charge"
        ]
        
        void_influences = [
            "Reality flickers and distorts around high-Void individuals",
            "Technology malfunctions when exposed to Void energy", 
            "Bonds become strained and difficult to maintain",
            "Sacred spaces reject those tainted by the Void",
            "Memories become confused and unreliable",
            "Elemental talismans lose their charge spontaneously"
        ]
        
        return {
            'theme': random.choice(themes),
            'location': random.choice(locations),
            'complication': random.choice(complications),
            'void_influence': random.choice(void_influences),
            'ritual_threshold_base': random.randint(16, 22),
            'key_npcs': random.randint(1, 3),
            'stakes': random.choice(['personal', 'community', 'faction', 'spiritual'])
        }


class SimpleAeoniskSession:
    """A self-playing Aeonisk YAGS session with proper mechanics."""
    
    def __init__(self):
        self.characters: List[AeoniskCharacter] = []
        self.scenario: Dict[str, Any] = {}
        self.turn_count = 0
        self.session_log: List[Dict[str, Any]] = []
        
    def generate_character(self, origin: str) -> AeoniskCharacter:
        """Generate a character following Aeonisk rules."""
        
        # Name pools by origin
        names = {
            'Sovereign Nexus': ['Aurora Echo', 'Harmony Pulse', 'Continuity Weave', 'Unity Resonance'],
            'Astral Commerce Group': ['Credit Ledger', 'Value Exchange', 'Profit Margin', 'Debt Collector'],
            'Tempest Industries': ['Void Storm', 'Chaos Navigator', 'Disruption Field', 'Liberty Spark'],
            'Arcane Genetics': ['Gene Weaver', 'Strain Adapter', 'Morph Catalyst', 'Evolution Prime'],
            'Freeborn': ['Wild Current', 'Free Sky', 'Unbound Drift', 'Natural Flow']
        }
        
        name = random.choice(names.get(origin, ['Unknown Walker']))
        
        # Generate attributes (2-5 range, 3 average)
        char = AeoniskCharacter(
            name=name,
            origin=origin,
            strength=random.randint(2, 5),
            health=random.randint(2, 5),
            agility=random.randint(2, 5),
            dexterity=random.randint(2, 5),
            perception=random.randint(2, 5),
            intelligence=random.randint(2, 5),
            empathy=random.randint(2, 5),
            willpower=random.randint(2, 5)
        )
        
        # Assign skills based on origin
        if origin == 'Sovereign Nexus':
            char.astral_arts = random.randint(3, 6)
            char.magick_theory = random.randint(2, 4)
            char.intimacy_ritual = random.randint(2, 4)
        elif origin == 'Astral Commerce Group':
            char.corporate_influence = random.randint(3, 6)
            char.debt_law = random.randint(3, 5)
            char.charm = random.randint(3, 5)
        elif origin == 'Tempest Industries':
            char.astral_arts = random.randint(4, 7)
            char.pilot = random.randint(2, 4)
            char.drone_operation = random.randint(2, 4)
        elif origin == 'Arcane Genetics':
            char.magick_theory = random.randint(3, 5)
            char.astral_arts = random.randint(2, 4)
        elif origin == 'Freeborn':
            char.astral_arts = random.randint(2, 5)
            char.athletics = random.randint(3, 6)
            char.stealth = random.randint(3, 5)
            
        # Generate ritual items and offerings
        ritual_items = {
            'Sovereign Nexus': ['Covenant Ring', 'Memory Crystal', 'Harmony Sigil'],
            'Astral Commerce Group': ['Contract Seal', 'Credit Talisman', 'Ledger Stone'],
            'Tempest Industries': ['Void Shard', 'Chaos Anchor', 'Liberty Flame'],
            'Arcane Genetics': ['Gene Helix', 'Bio-Catalyst', 'Evolution Seed'],
            'Freeborn': ['Natural Stone', 'Wild Feather', 'Free Spirit Token']
        }
        
        char.primary_ritual_item = random.choice(ritual_items.get(origin, ['Unknown Focus']))
        char.offerings = [
            random.choice(['Memory Fragment', 'Emotional Echo', 'Spark Talisman', 'Blood Drop', 'Sacred Oath']),
            random.choice(['Grain Talisman', 'Drip Core', 'Breath Wisp', 'Personal Secret'])
        ]
        
        return char
        
    def generate_party(self, size: int = 3) -> List[AeoniskCharacter]:
        """Generate a diverse party of characters."""
        origins = ['Sovereign Nexus', 'Astral Commerce Group', 'Tempest Industries', 'Arcane Genetics', 'Freeborn']
        
        party = []
        used_origins = []
        
        for i in range(size):
            # Ensure variety
            available_origins = [o for o in origins if o not in used_origins or len(used_origins) >= len(origins)]
            if not available_origins:
                available_origins = origins
                
            origin = random.choice(available_origins)
            used_origins.append(origin)
            
            char = self.generate_character(origin)
            party.append(char)
            
        self.characters = party
        return party
        
    def ai_character_decision(self, character: AeoniskCharacter, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI character decision based on origin and mechanics."""
        
        # Decision types based on Aeonisk mechanics
        decisions = ['investigate', 'ritual_attempt', 'social_bond', 'corporate_maneuver', 'void_research', 'exploration']
        
        # Weight decisions by origin and skills
        weights = {}
        
        if character.origin == 'Sovereign Nexus':
            weights = {'ritual_attempt': 3, 'social_bond': 2, 'investigate': 2}
        elif character.origin == 'Astral Commerce Group':
            weights = {'corporate_maneuver': 3, 'social_bond': 2, 'investigate': 1}
        elif character.origin == 'Tempest Industries':
            weights = {'void_research': 3, 'ritual_attempt': 2, 'exploration': 2}
        elif character.origin == 'Arcane Genetics':
            weights = {'investigate': 2, 'ritual_attempt': 2, 'exploration': 1}
        elif character.origin == 'Freeborn':
            weights = {'exploration': 3, 'investigate': 2, 'void_research': 1}
            
        # Default weights
        for decision in decisions:
            if decision not in weights:
                weights[decision] = 1
                
        # Choose weighted decision
        weighted_choices = []
        for decision, weight in weights.items():
            weighted_choices.extend([decision] * weight)
            
        chosen_decision = random.choice(weighted_choices)
        
        return self._execute_decision(character, chosen_decision, scenario)
        
    def _execute_decision(self, character: AeoniskCharacter, decision_type: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the character's decision with proper Aeonisk mechanics."""
        
        if decision_type == 'ritual_attempt':
            ritual_types = ['bond_strengthening', 'void_cleansing', 'astral_navigation', 'memory_reading', 'corporate_influence']
            ritual = random.choice(ritual_types)
            
            # Determine if offering is used (AI makes smart choice based on Void score)
            has_offering = character.void_score < 7  # Higher void = more desperate
            bonded_assist = len([c for c in self.characters if c.name in character.bonds]) > 0
            
            threshold = scenario['ritual_threshold_base']
            success, roll, margin, result = character.make_ritual_check(threshold, has_offering, bonded_assist)
            
            action_desc = f"attempts {ritual} ritual using {character.primary_ritual_item}"
            if has_offering:
                offering = random.choice(character.offerings)
                action_desc += f", offering {offering}"
            else:
                action_desc += " without offering (risk of Void)"
                
            return {
                'type': 'ritual_attempt',
                'description': action_desc,
                'ritual_name': ritual,
                'roll_result': roll,
                'margin': margin,
                'outcome': result,
                'success': success,
                'void_gained': 1 if not has_offering or not success else 0,
                'offering_used': offering if has_offering else None
            }
            
        elif decision_type == 'investigate':
            targets = ['void traces', 'corporate records', 'memory fragments', 'ritual components', 'faction movements']
            target = random.choice(targets)
            
            success, roll, margin, result = character.make_skill_check('intelligence', 'awareness', 18)
            
            return {
                'type': 'investigate',
                'description': f"investigates {target} in {scenario['location']}",
                'target': target,
                'roll_result': roll,
                'margin': margin,
                'outcome': result,
                'success': success
            }
            
        elif decision_type == 'social_bond':
            other_chars = [c for c in self.characters if c != character]
            if other_chars and len(character.bonds) < 3:  # Can form new bonds
                target = random.choice(other_chars)
                
                success, roll, margin, result = character.make_skill_check('empathy', 'charm', 20)
                
                if success and target.name not in character.bonds:
                    character.bonds.append(target.name)
                    # Mutual bond
                    if character.name not in target.bonds and len(target.bonds) < 3:
                        target.bonds.append(character.name)
                        
                return {
                    'type': 'social_bond',
                    'description': f"attempts to form/strengthen bond with {target.name}",
                    'target': target.name,
                    'roll_result': roll,
                    'margin': margin,
                    'outcome': result,
                    'success': success,
                    'bond_formed': success and target.name not in character.bonds
                }
            else:
                # Fallback to investigation
                return self._execute_decision(character, 'investigate', scenario)
                
        elif decision_type == 'corporate_maneuver':
            maneuvers = ['contract negotiation', 'debt manipulation', 'favor trading', 'information brokering']
            maneuver = random.choice(maneuvers)
            
            success, roll, margin, result = character.make_skill_check('empathy', 'corporate_influence', 22)
            
            soulcredit_change = 0
            if success:
                soulcredit_change = random.choice([1, 2])  # Gain soulcredit
            else:
                soulcredit_change = random.choice([-1, 0])  # Risk losing soulcredit
                
            character.soulcredit = max(-10, min(10, character.soulcredit + soulcredit_change))
            
            return {
                'type': 'corporate_maneuver',
                'description': f"attempts {maneuver}",
                'maneuver': maneuver,
                'roll_result': roll,
                'margin': margin,
                'outcome': result,
                'success': success,
                'soulcredit_change': soulcredit_change
            }
            
        elif decision_type == 'void_research':
            research_types = ['void artifact analysis', 'corruption pattern study', 'void entity communication']
            research = random.choice(research_types)
            
            success, roll, margin, result = character.make_skill_check('intelligence', 'magick_theory', 25)
            
            # Void research is risky
            void_gain = 0
            if not success:
                void_gain = 1
            elif margin < 5:  # Weak success
                void_gain = 1 if random.random() < 0.3 else 0
                
            character.void_score = min(10, character.void_score + void_gain)
            
            return {
                'type': 'void_research',
                'description': f"conducts {research}",
                'research_type': research,
                'roll_result': roll,
                'margin': margin,
                'outcome': result,
                'success': success,
                'void_gained': void_gain
            }
            
        else:  # exploration
            locations = ['restricted areas', 'hidden passages', 'astral currents', 'abandoned facilities']
            location = random.choice(locations)
            
            success, roll, margin, result = character.make_skill_check('perception', 'athletics', 16)
            
            return {
                'type': 'exploration',
                'description': f"explores {location}",
                'location': location,
                'roll_result': roll,
                'margin': margin,
                'outcome': result,
                'success': success
            }
            
    async def run_session(self, max_turns: int = 8):
        """Run a complete Aeonisk self-playing session."""
        
        print("=== Aeonisk YAGS Self-Playing Session ===")
        print("Using actual tabletop RPG mechanics from the markdown files\n")
        
        # Generate party
        print("--- Party Generation ---")
        party = self.generate_party(3)
        
        for char in party:
            print(f"\n{char.name} ({char.origin})")
            print(f"  Attributes: Str {char.strength}, Hea {char.health}, Agi {char.agility}, Dex {char.dexterity}")
            print(f"             Per {char.perception}, Int {char.intelligence}, Emp {char.empathy}, Wil {char.willpower}")
            print(f"  Key Skills: Astral Arts {char.astral_arts}, Corporate Influence {char.corporate_influence}")
            print(f"  Spiritual: Void {char.void_score}/10, Soulcredit {char.soulcredit}")
            print(f"  Ritual Kit: {char.primary_ritual_item} + {len(char.offerings)} offerings")
            print(f"  Origin Trait: {char.origin} special ability")
            
        # Generate scenario  
        print("\n--- Scenario Generation ---")
        scenario = AeoniskScenario.generate()
        self.scenario = scenario
        
        print(f"Theme: {scenario['theme']}")
        print(f"Location: {scenario['location']}")
        print(f"Complication: {scenario['complication']}")
        print(f"Void Influence: {scenario['void_influence']}")
        print(f"Ritual Difficulty: {scenario['ritual_threshold_base']}")
        
        # Form initial bonds (some characters might know each other)
        if random.random() < 0.6:  # 60% chance of pre-existing bonds
            bonded_pair = random.sample(party, 2)
            bonded_pair[0].bonds.append(bonded_pair[1].name)
            bonded_pair[1].bonds.append(bonded_pair[0].name)
            print(f"\nPre-existing Bond: {bonded_pair[0].name} ⟷ {bonded_pair[1].name}")
            
        # Run gameplay turns
        print(f"\n--- Gameplay ({max_turns} turns max) ---")
        
        for turn in range(1, max_turns + 1):
            print(f"\n=== Turn {turn} ===")
            turn_actions = []
            
            for character in party:
                action = self.ai_character_decision(character, scenario)
                turn_actions.append(action)
                
                print(f"\n[{character.name}] {action['description']}")
                print(f"  Roll: {action['roll_result']} → {action['outcome']} (margin: {action.get('margin', 'N/A')})")
                
                # Show consequences
                if 'void_gained' in action and action['void_gained'] > 0:
                    print(f"  → Void increased to {character.void_score}/10")
                if 'soulcredit_change' in action and action['soulcredit_change'] != 0:
                    print(f"  → Soulcredit changed by {action['soulcredit_change']} to {character.soulcredit}")
                if 'bond_formed' in action and action['bond_formed']:
                    print(f"  → New bond formed with {action['target']}")
                    
            self.session_log.extend(turn_actions)
            
            # Check for dramatic escalation
            party_void = sum(c.void_score for c in party)
            if party_void >= 15:
                print(f"\n!!! VOID CRISIS: Combined party Void reaches {party_void} !!!")
                print("Reality becomes unstable, technology malfunctions, Bonds strain...")
                break
                
            # Brief pause
            await asyncio.sleep(0.8)
            
        # Session conclusion
        print(f"\n=== Session Conclusion ===")
        print(f"Turns completed: {min(turn, max_turns)}")
        print(f"Total actions taken: {len(self.session_log)}")
        
        print(f"\nFinal Party Status:")
        for char in party:
            print(f"\n{char.name}:")
            print(f"  Void Score: {char.void_score}/10")
            print(f"  Soulcredit: {char.soulcredit}")
            print(f"  Bonds: {', '.join(char.bonds) if char.bonds else 'None'}")
            
        # Generate session data for training
        session_data = {
            'session_id': f"aeonisk_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'system': 'Aeonisk YAGS',
            'scenario': scenario,
            'characters': [{
                'name': c.name,
                'origin': c.origin,
                'attributes': {
                    'strength': c.strength, 'health': c.health, 'agility': c.agility,
                    'dexterity': c.dexterity, 'perception': c.perception,
                    'intelligence': c.intelligence, 'empathy': c.empathy, 'willpower': c.willpower
                },
                'skills': {
                    'astral_arts': c.astral_arts, 'magick_theory': c.magick_theory,
                    'intimacy_ritual': c.intimacy_ritual, 'corporate_influence': c.corporate_influence,
                    'debt_law': c.debt_law, 'pilot': c.pilot, 'drone_operation': c.drone_operation,
                    'athletics': c.athletics, 'awareness': c.awareness, 'brawl': c.brawl,
                    'charm': c.charm, 'guile': c.guile, 'stealth': c.stealth
                },
                'void_score': c.void_score,
                'soulcredit': c.soulcredit,
                'bonds': c.bonds,
                'primary_ritual_item': c.primary_ritual_item,
                'birth_method': c.birth_method
            } for c in party],
            'actions': self.session_log,
            'turns_completed': min(turn, max_turns),
            'final_party_void': sum(c.void_score for c in party),
            'mechanics_used': ['ritual_checks', 'skill_checks', 'void_accumulation', 'soulcredit_changes', 'bond_formation'],
            'end_time': datetime.now().isoformat()
        }
        
        # Save session data
        output_dir = Path('./aeonisk_sessions')
        output_dir.mkdir(exist_ok=True)
        
        session_file = output_dir / f"{session_data['session_id']}.json"
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)
            
        print(f"\nSession data saved to: {session_file}")
        print("Ready for training data use or benchmark evaluation!")
        
        return session_data


async def main():
    """Run a simple Aeonisk self-playing session."""
    print("Starting Aeonisk YAGS Self-Playing Multi-Agent Session")
    print("=" * 60)
    
    session = SimpleAeoniskSession()
    await session.run_session()


if __name__ == "__main__":
    asyncio.run(main())