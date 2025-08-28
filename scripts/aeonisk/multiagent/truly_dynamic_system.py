#!/usr/bin/env python3
"""
Truly Dynamic Aeonisk YAGS Player System

Uses randomized personality traits, dynamic scenario generation, and
varied decision-making patterns to create diverse, unpredictable output.
"""

import random
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import time

# Family lines and factions from the lore
FAMILY_LINES = {
    'Sovereign Nexus': {
        'Elaras': {'reputation': 'rising', 'specialty': 'harmony_rituals'},
        'Halessan': {'reputation': 'stable', 'specialty': 'civic_duty'}, 
        'Ireveth': {'reputation': 'stable', 'specialty': 'enforcement'},
        'Unified Hand': {'reputation': 'mysterious', 'specialty': 'observation'}
    },
    'Astral Commerce Group': {
        'Kythea': {'reputation': 'rising', 'specialty': 'futures_trading'},
        'Exchange': {'reputation': 'stable', 'specialty': 'contract_law'},
        'Ledger-Kaine': {'reputation': 'declining', 'specialty': 'audit_enforcement'}
    },
    'Tempest Industries': {
        'Karsel': {'reputation': 'disgraced', 'specialty': 'void_research'},
        'Dissolution': {'reputation': 'rising', 'specialty': 'chaos_theory'},
        'Liberty-Void': {'reputation': 'stable', 'specialty': 'liberation_tech'}
    },
    'Arcane Genetics': {
        'Vireya': {'reputation': 'stable', 'specialty': 'bio_enhancement'},
        'Catalyst': {'reputation': 'rising', 'specialty': 'mutation_control'}
    },
    'Freeborn': {
        'Unbound': {'reputation': 'variable', 'specialty': 'independence'},
        'Wild-Current': {'reputation': 'variable', 'specialty': 'natural_harmony'}
    }
}

GIVEN_NAMES = [
    'Irele', 'Zara', 'Echo', 'Kaelen', 'Varis', 'Liora', 'Wren', 'Nyx',
    'Thane', 'Riven', 'Vera', 'Magnus', 'Cira', 'Dex', 'Nova', 'Kael'
]


@dataclass
class PersonalityProfile:
    """Dynamic personality that affects all decision making."""
    risk_tolerance: int = 5  # 1-10
    void_curiosity: int = 3  # 1-10  
    authority_respect: int = 5  # 1-10
    family_loyalty: int = 7  # 1-10
    pragmatism: int = 5  # 1-10 (vs idealism)
    social_preference: int = 5  # 1-10 (vs solo work)
    innovation_drive: int = 5  # 1-10 (vs tradition)
    
    def __post_init__(self):
        """Add some correlated personality adjustments."""
        # High void curiosity often correlates with lower authority respect
        if self.void_curiosity >= 8:
            self.authority_respect = max(1, self.authority_respect - random.randint(1, 3))
        
        # High family loyalty often correlates with higher authority respect (for established families)
        if self.family_loyalty >= 8:
            self.authority_respect = min(10, self.authority_respect + random.randint(0, 2))


@dataclass
class InventoryItem:
    name: str
    item_type: str
    void_tainted: bool = False
    charges: Optional[int] = None
    quality: str = "standard"  # poor, standard, fine, exceptional
    description: str = ""


@dataclass
class AeoniskCharacter:
    """Highly variable Aeonisk character with dynamic personality."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    family_reputation: str
    personal_motivation: str
    personality: PersonalityProfile = field(default_factory=PersonalityProfile)
    
    # Attributes
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
    true_will: str = ""
    
    # Skills with variation
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
    primary_ritual_item: InventoryItem = None
    inventory: List[InventoryItem] = field(default_factory=list)
    
    # Dynamic state
    current_stress: int = 0  # 0-10
    recent_failures: int = 0  # Affects confidence
    session_void_exposure: int = 0  # Accumulated this session


class DynamicScenarioGenerator:
    """Generates highly varied scenarios using combinatorial elements."""
    
    SCENARIO_ELEMENTS = {
        'primary_threats': [
            'void_containment_breach', 'memory_theft_operation', 'bond_sabotage_ritual',
            'ley_line_disruption', 'corporate_espionage', 'echo_children_crisis',
            'temporal_anomaly', 'faction_war_brewing', 'soulcredit_market_crash',
            'ancient_artifact_awakening', 'biocreche_malfunction', 'reality_virus_spread'
        ],
        'locations': [
            'Research Station Omega-7', 'Abandoned Biocreche Complex', 'Nexus Council Chambers',
            'Corporate Memory Vault', 'Freeborn Settlement Ruins', 'Ley Line Convergence Point',
            'Echo Children Sanctuary', 'Void-touched Archive', 'Slipstream Dock Alpha',
            'Family Estate Manor', 'Underground Market Hub', 'Sacred Bonding Circle'
        ],
        'secondary_complications': [
            'family_honor_at_stake', 'rival_agents_present', 'time_pressure_extreme',
            'innocent_lives_threatened', 'evidence_being_destroyed', 'witnesses_compromised',
            'technology_failures', 'political_ramifications', 'void_corruption_spreading',
            'memory_fragments_degrading', 'bonds_under_strain', 'reality_becoming_unstable'
        ],
        'faction_dynamics': [
            'Sovereign_Nexus_investigating', 'Tempest_Industries_suspected', 'ACG_covering_tracks',
            'Arcane_Genetics_experimenting', 'Freeborn_network_mobilizing', 'internal_faction_strife',
            'cross_faction_alliance', 'faction_war_escalating', 'rogue_agents_operating'
        ]
    }
    
    @classmethod
    def generate_scenario(cls, seed: Optional[str] = None) -> Dict[str, Any]:
        """Generate a unique scenario using combinatorial elements."""
        
        if seed:
            random.seed(hashlib.md5(seed.encode()).hexdigest())
        else:
            random.seed(int(time.time() * 1000) % 2**32)
        
        threat = random.choice(cls.SCENARIO_ELEMENTS['primary_threats'])
        location = random.choice(cls.SCENARIO_ELEMENTS['locations'])
        complication = random.choice(cls.SCENARIO_ELEMENTS['secondary_complications'])
        faction_dynamic = random.choice(cls.SCENARIO_ELEMENTS['faction_dynamics'])
        
        # Generate description based on elements
        descriptions = {
            'void_containment_breach': f"A critical void containment failure at {location} has released raw chaotic energy",
            'memory_theft_operation': f"Coordinated memory extraction is occurring at {location}, targeting specific individuals",
            'bond_sabotage_ritual': f"Sacred bonding ceremonies at {location} are being systematically disrupted",
            'ley_line_disruption': f"Ancient ley lines connected to {location} are being artificially destabilized"
        }
        
        base_desc = descriptions.get(threat, f"A crisis involving {threat.replace('_', ' ')} unfolds at {location}")
        
        # Add complication
        complication_text = {
            'family_honor_at_stake': "with family reputations hanging in the balance",
            'time_pressure_extreme': "with only hours before irreversible consequences",
            'innocent_lives_threatened': "while innocent civilians remain trapped in danger",
            'void_corruption_spreading': "as void corruption spreads to nearby areas"
        }.get(complication, f"while {complication.replace('_', ' ')}")
        
        full_description = f"{base_desc} {complication_text}."
        
        return {
            'title': threat.replace('_', ' ').title(),
            'location': location,
            'description': full_description,
            'primary_threat': threat,
            'complication': complication,
            'faction_dynamic': faction_dynamic,
            'void_influence': random.randint(1, 9),  # Full range
            'time_pressure': random.choice(['low', 'moderate', 'high', 'extreme']),
            'civilian_risk': random.choice(['none', 'low', 'moderate', 'high']),
            'political_sensitivity': random.choice(['low', 'moderate', 'high', 'extreme'])
        }


class DynamicCharacterGenerator:
    """Generates highly varied characters with unique personalities and backgrounds."""
    
    @staticmethod
    def generate_personality() -> PersonalityProfile:
        """Generate a unique personality profile."""
        
        # Use different distribution patterns for variety
        distributions = [
            lambda: random.randint(1, 10),  # Uniform
            lambda: max(1, min(10, int(random.gauss(5, 2)))),  # Normal distribution
            lambda: random.choice([1, 2, 3, 8, 9, 10]),  # Extreme values
            lambda: random.choice([3, 4, 5, 6, 7])  # Moderate values
        ]
        
        return PersonalityProfile(
            risk_tolerance=random.choice(distributions)(),
            void_curiosity=random.choice(distributions)(),
            authority_respect=random.choice(distributions)(),
            family_loyalty=random.choice(distributions)(),
            pragmatism=random.choice(distributions)(),
            social_preference=random.choice(distributions)(),
            innovation_drive=random.choice(distributions)()
        )
    
    @staticmethod
    def generate_varied_character(faction: str = None, family_line: str = None) -> AeoniskCharacter:
        """Generate a character with high variation and personality-driven traits."""
        
        if not faction:
            factions = ['Sovereign Nexus', 'Astral Commerce Group', 'Tempest Industries', 'Arcane Genetics', 'Freeborn']
            faction = random.choice(factions)
        
        if not family_line:
            family_options = list(FAMILY_LINES[faction].keys())
            family_line = random.choice(family_options)
        
        names = [
            'Irele', 'Zara', 'Echo', 'Kaelen', 'Varis', 'Liora', 'Wren', 'Nyx',
            'Aurora', 'Void', 'Storm', 'Cipher', 'Flux', 'Resonance', 'Drift',
            'Cascade', 'Prism', 'Vector', 'Matrix', 'Quantum', 'Nexus', 'Spiral'
        ]
        
        given_name = random.choice(names)
        personality = DynamicCharacterGenerator.generate_personality()
        
        char = AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=f"{given_name} {family_line}",
            origin_faction=faction,
            family_reputation=FAMILY_LINES[faction][family_line]['reputation'],
            personal_motivation="",  # Will be generated based on personality
            personality=personality
        )
        
        # Generate motivation based on personality + family situation
        char.personal_motivation = DynamicCharacterGenerator._generate_motivation(char, personality)
        
        # Generate attributes with personality influence
        DynamicCharacterGenerator._apply_personality_to_stats(char, personality)
        
        # Generate skills based on family + personality
        DynamicCharacterGenerator._generate_skills(char, personality)
        
        # Generate inventory based on personality and resources
        char.inventory = DynamicCharacterGenerator._generate_dynamic_inventory(char, personality)
        
        return char
    
    @staticmethod
    def _generate_motivation(char: AeoniskCharacter, personality: PersonalityProfile) -> str:
        """Generate motivation based on personality and family situation."""
        
        motivations = []
        
        # Family-based motivations
        if char.family_reputation == 'rising':
            motivations.extend(['Prove family worthiness', 'Seize new opportunities', 'Build lasting legacy'])
        elif char.family_reputation == 'disgraced':
            motivations.extend(['Redeem family name', 'Forge new identity', 'Challenge the system'])
        elif char.family_reputation == 'declining':
            motivations.extend(['Restore family reputation', 'Uncover family secrets', 'Break from shame'])
        else:
            motivations.extend(['Maintain family honor', 'Serve faction interests', 'Protect traditions'])
        
        # Personality-driven motivations
        if personality.void_curiosity >= 8:
            motivations.append('Master void manipulation techniques')
        if personality.innovation_drive >= 8:
            motivations.append('Pioneer revolutionary approaches')
        if personality.authority_respect <= 3:
            motivations.append('Undermine corrupt authority structures')
        if personality.family_loyalty >= 9:
            motivations.append('Sacrifice everything for family glory')
        if personality.risk_tolerance >= 8:
            motivations.append('Seek dangerous adventures and challenges')
        
        # Weight based on personality
        weighted_choices = []
        for motivation in motivations:
            weight = 1
            
            if 'family' in motivation.lower() and personality.family_loyalty >= 7:
                weight += 2
            if 'challenge' in motivation.lower() and personality.risk_tolerance >= 7:
                weight += 2
            if 'void' in motivation.lower() and personality.void_curiosity >= 7:
                weight += 2
            
            weighted_choices.extend([motivation] * weight)
        
        return random.choice(weighted_choices)
    
    @staticmethod
    def _apply_personality_to_stats(char: AeoniskCharacter, personality: PersonalityProfile):
        """Apply personality influence to attributes and derived stats."""
        
        # Base random attributes
        char.strength = random.randint(2, 5)
        char.health = random.randint(2, 5)
        char.agility = random.randint(2, 5)
        char.dexterity = random.randint(2, 5)
        char.perception = random.randint(2, 5)
        char.intelligence = random.randint(2, 5)
        char.empathy = random.randint(2, 5)
        char.willpower = random.randint(2, 5)
        
        # Personality influences (subtle bonuses/penalties)
        if personality.risk_tolerance >= 8:
            char.agility = min(5, char.agility + 1)  # Risk-takers are often quick
        if personality.authority_respect <= 3:
            char.willpower = min(5, char.willpower + 1)  # Rebels have strong will
        if personality.social_preference >= 8:
            char.empathy = min(5, char.empathy + 1)  # Social people read others well
        if personality.innovation_drive >= 8:
            char.intelligence = min(5, char.intelligence + 1)  # Innovators are clever
        
        # Void and Soulcredit based on personality and faction
        if personality.void_curiosity >= 7:
            char.void_score = random.randint(0, 3)
        if personality.authority_respect >= 7 and char.origin_faction in ['Sovereign Nexus', 'Astral Commerce Group']:
            char.soulcredit = random.randint(1, 4)
        elif personality.authority_respect <= 3:
            char.soulcredit = random.randint(-2, 1)
    
    @staticmethod
    def _generate_skills(char: AeoniskCharacter, personality: PersonalityProfile):
        """Generate skills based on family line AND personality."""
        
        family_data = FAMILY_LINES[char.origin_faction][char.family_line]
        specialty = family_data['specialty']
        
        # Base skill allocation
        available_points = random.randint(12, 20)  # Variable skill budgets
        
        # Family specialty skills
        if 'ritual' in specialty or 'harmony' in specialty:
            char.astral_arts = random.randint(3, 6)
            available_points -= char.astral_arts
        elif 'enforcement' in specialty:
            char.awareness = random.randint(3, 5)
            char.brawl = random.randint(3, 4)
            available_points -= (char.awareness + char.brawl)
        elif 'trading' in specialty or 'contract' in specialty:
            char.corporate_influence = random.randint(3, 6)
            char.guile = random.randint(2, 4)
            available_points -= (char.corporate_influence + char.guile)
        elif 'void' in specialty:
            char.astral_arts = random.randint(2, 5)
            char.stealth = random.randint(2, 4)
            available_points -= (char.astral_arts + char.stealth)
        elif 'intelligence' in specialty:
            char.awareness = random.randint(4, 6)
            char.guile = random.randint(3, 5)
            available_points -= (char.awareness + char.guile)
        
        # Personality-driven skill bonuses
        if personality.social_preference >= 8:
            char.charm = min(6, char.charm + random.randint(1, 2))
        if personality.risk_tolerance >= 8:
            char.athletics = min(6, char.athletics + random.randint(1, 2))
        if personality.void_curiosity >= 7:
            char.astral_arts = min(6, char.astral_arts + random.randint(1, 2))
        if personality.innovation_drive >= 7:
            char.hacking = random.randint(2, 4)
            
        # Distribute remaining points randomly among untrained skills
        skill_options = ['athletics', 'awareness', 'brawl', 'charm', 'guile', 'stealth', 'hacking']
        while available_points > 0 and random.random() < 0.7:
            skill = random.choice(skill_options)
            current_val = getattr(char, skill)
            if current_val < 5:  # Don't exceed reasonable limits
                setattr(char, skill, current_val + 1)
                available_points -= 1
    
    @staticmethod  
    def _generate_dynamic_inventory(char: AeoniskCharacter, personality: PersonalityProfile) -> List[InventoryItem]:
        """Generate inventory based on personality, resources, and randomness."""
        
        inventory = []
        
        # Everyone has basics
        inventory.append(InventoryItem("Personal Commlink", "technology"))
        inventory.append(InventoryItem(f"{char.origin_faction} ID", "documents"))
        
        # Generate ritual item with personality influence
        ritual_names = {
            'Elaras': ['Harmony Crystal', 'Unity Bell', 'Resonance Prism', 'Peace Stone'],
            'Karsel': ['Void Shard', 'Chaos Lens', 'Reality Anchor', 'Entropy Stone'],
            'Kythea': ['Market Oracle', 'Profit Stone', 'Trade Compass', 'Future Glass'],
            'Vireya': ['Gene Helix', 'Bio Matrix', 'Evolution Seed', 'Life Prism']
        }
        
        ritual_name = random.choice(ritual_names.get(char.family_line, ['Ancient Focus', 'Family Heirloom', 'Sacred Stone']))
        
        # Ritual item may be void-tainted based on personality and family
        void_tainted = False
        if personality.void_curiosity >= 7 and char.void_score > 0:
            void_tainted = random.random() < 0.4
        elif char.family_line == 'Karsel':
            void_tainted = random.random() < 0.6  # Karsel often has void gear
            
        char.primary_ritual_item = InventoryItem(
            ritual_name, "ritual_focus", 
            void_tainted=void_tainted,
            quality=random.choice(['standard', 'fine', 'exceptional']),
            description=f"{char.family_line} Line ritual focus"
        )
        
        # Soulcredit-based gear
        if char.soulcredit >= 3:
            talisman_options = ['Spark Core', 'Drip Matrix', 'Breath Wisp', 'Grain Stone']
            inventory.append(InventoryItem(
                random.choice(talisman_options),
                "talisman",
                charges=random.randint(40, 100),
                quality=random.choice(['standard', 'fine'])
            ))
        elif char.soulcredit <= -2:
            # Poor soulcredit = knockoff gear
            inventory.append(InventoryItem(
                "Counterfeit Talisman", "talisman",
                charges=random.randint(5, 20),
                quality="poor",
                description="Unreliable energy source"
            ))
        
        # Personality-driven gear
        if personality.risk_tolerance >= 8:
            inventory.append(InventoryItem("Emergency Stims", "consumable", charges=2))
        if personality.void_curiosity >= 7:
            inventory.append(InventoryItem("Void Detector", "technology", description="Personal void monitoring device"))
        if personality.social_preference <= 3:
            inventory.append(InventoryItem("Isolation Gear", "tools", description="Self-sufficiency equipment"))
        if personality.authority_respect <= 3:
            inventory.append(InventoryItem("Crypto Commlink", "technology", description="Encrypted communications"))
        
        # Faction-specific gear with randomness
        if char.origin_faction == 'Tempest Industries':
            if random.random() < 0.4:  # 40% chance
                inventory.append(InventoryItem(
                    "Experimental Void Device", "technology",
                    void_tainted=random.random() < 0.7,
                    description="Prototype void-manipulation technology"
                ))
        elif char.origin_faction == 'Astral Commerce Group':
            if random.random() < 0.5:
                inventory.append(InventoryItem("Contract Scanner", "technology", description="Legal document analyzer"))
        elif char.origin_faction == 'Arcane Genetics':
            if random.random() < 0.3:
                inventory.append(InventoryItem("Bio Enhancement Serum", "consumable", charges=1))
        
        # Random additional gear
        random_items = [
            'Backup Power Cell', 'Encrypted Data Pad', 'Emergency Rations',
            'Meditation Focus', 'Signal Jammer', 'Medical Kit', 'Tool Kit'
        ]
        
        num_random = random.randint(0, 3)
        for _ in range(num_random):
            item_name = random.choice(random_items)
            random_items.remove(item_name)  # No duplicates
            inventory.append(InventoryItem(item_name, "tools"))
        
        return inventory


class PersonalityDrivenDecisionMaker:
    """Makes decisions based on character personality rather than hardcoded logic."""
    
    @staticmethod
    def evaluate_action_appeal(action: str, character: AeoniskCharacter, scenario: Dict[str, Any]) -> int:
        """Score how appealing an action is to this specific character (1-10)."""
        
        p = character.personality
        action_lower = action.lower()
        score = 5  # Base appeal
        
        # Risk tolerance effects
        if 'confront' in action_lower or 'direct' in action_lower:
            score += (p.risk_tolerance - 5)  # High risk tolerance = more appealing
        
        # Void curiosity effects  
        if 'void' in action_lower or 'ritual' in action_lower:
            score += (p.void_curiosity - 5)
        
        # Authority respect effects
        if 'negotiate' in action_lower or 'alliance' in action_lower:
            score += (p.authority_respect - 5)  # Respectful people negotiate
        if 'influence' in action_lower and character.origin_faction in ['Sovereign Nexus', 'Astral Commerce Group']:
            score += (p.authority_respect - 3)
        
        # Family loyalty effects
        if 'family' in action_lower:
            score += (p.family_loyalty - 5)
        
        # Social preference effects
        if 'alliance' in action_lower or 'negotiate' in action_lower:
            score += (p.social_preference - 5)
        elif 'stealth' in action_lower or 'reconnaissance' in action_lower:
            score += (10 - p.social_preference - 5)  # Loners prefer solo work
        
        # Pragmatism effects
        if 'investigate' in action_lower or 'reconnaissance' in action_lower:
            score += (p.pragmatism - 5)  # Practical people gather info
        elif 'confront' in action_lower:
            score += (10 - p.pragmatism - 5)  # Idealists are more confrontational
        
        # Innovation drive effects
        if 'archives' in action_lower or 'historical' in action_lower:
            score += (10 - p.innovation_drive - 5)  # Traditional approach
        elif 'technological' in action_lower:
            score += (p.innovation_drive - 5)  # New tech approach
        
        # Current state effects (stress, recent failures)
        if character.current_stress >= 7:
            if 'careful' in action_lower or 'stealth' in action_lower:
                score += 2  # Stressed characters prefer caution
            elif 'confront' in action_lower:
                score -= 2
        
        if character.recent_failures >= 2:
            if 'alliance' in action_lower or 'seek' in action_lower:
                score += 2  # Failing characters seek help
            elif 'direct' in action_lower:
                score -= 1  # Less confident in direct action
        
        return max(1, min(10, score))
    
    @staticmethod
    def select_character_action(available_actions: List[str], character: AeoniskCharacter, scenario: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """Select action based on character's unique personality and situation."""
        
        # Score all actions
        action_scores = []
        for action in available_actions:
            appeal = PersonalityDrivenDecisionMaker.evaluate_action_appeal(action, character, scenario)
            action_scores.append((action, appeal))
        
        # Sort by appeal
        action_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Add personality-based randomness
        if character.personality.risk_tolerance >= 7:
            # Risk-takers sometimes choose suboptimal actions
            if random.random() < 0.3:
                chosen = random.choice(action_scores[:5])  # Pick from top 5
            else:
                chosen = action_scores[0]
        elif character.personality.pragmatism >= 8:
            # Pragmatists almost always choose the best option
            chosen = action_scores[0]
        else:
            # Normal characters choose from top 3 with some randomness
            top_choices = action_scores[:3]
            weights = [3, 2, 1]  # Prefer better options
            chosen = random.choices(top_choices, weights=weights)[0]
        
        # Generate reasoning based on personality
        reasoning = PersonalityDrivenDecisionMaker._generate_personality_reasoning(
            chosen[0], character, scenario, chosen[1]
        )
        
        # Additional context about the choice
        choice_context = {
            'appeal_score': chosen[1],
            'personality_factors': {
                'risk_tolerance': character.personality.risk_tolerance,
                'void_curiosity': character.personality.void_curiosity,
                'authority_respect': character.personality.authority_respect,
                'family_loyalty': character.personality.family_loyalty
            },
            'alternative_considered': action_scores[1][0] if len(action_scores) > 1 else None
        }
        
        return chosen[0], reasoning, choice_context
    
    @staticmethod
    def _generate_personality_reasoning(action: str, character: AeoniskCharacter, scenario: Dict[str, Any], appeal_score: int) -> str:
        """Generate reasoning that reflects the character's personality."""
        
        p = character.personality
        family_data = FAMILY_LINES[character.origin_faction][character.family_line]
        
        reasoning_parts = []
        
        # Primary motivation
        if appeal_score >= 8:
            reasoning_parts.append(f"This strongly appeals to my {character.personal_motivation.lower()}")
        elif appeal_score >= 6:
            reasoning_parts.append(f"This aligns with my goals of {character.personal_motivation.lower()}")
        
        # Family influence
        if p.family_loyalty >= 7:
            reasoning_parts.append(f"as a {character.family_line}, our specialty in {family_data['specialty']} guides this choice")
        elif p.family_loyalty <= 3:
            reasoning_parts.append(f"though I must balance family expectations with my own judgment")
        
        # Personality-specific reasoning
        if 'risk' in action.lower() and p.risk_tolerance >= 7:
            reasoning_parts.append("I'm willing to accept significant risk for meaningful results")
        elif 'careful' in action.lower() and p.risk_tolerance <= 4:
            reasoning_parts.append("careful approaches align with my cautious nature")
        
        if 'void' in action.lower() and p.void_curiosity >= 7:
            reasoning_parts.append("my fascination with void phenomena drives this choice")
        elif 'void' in action.lower() and p.void_curiosity <= 3:
            reasoning_parts.append("though I'm wary of void exposure, the situation demands it")
        
        if 'authority' in action.lower() or 'official' in action.lower():
            if p.authority_respect >= 7:
                reasoning_parts.append("working through proper channels respects established order")
            else:
                reasoning_parts.append("though I distrust authority, pragmatism sometimes requires cooperation")
        
        # Current state influences
        if character.void_score >= 3:
            reasoning_parts.append(f"with my current void exposure ({character.void_score}/10), I must be strategic")
        
        if character.soulcredit >= 4:
            reasoning_parts.append("my good standing provides access to resources others lack")
        elif character.soulcredit <= -1:
            reasoning_parts.append("my poor standing limits options, but may provide different opportunities")
        
        return ". ".join(reasoning_parts).capitalize() + "."


def main():
    """Demonstrate the truly dynamic system."""
    
    print("=== Truly Dynamic Aeonisk YAGS System ===")
    print("Each run produces different characters, personalities, and decisions\n")
    
    # Generate 3 different characters from same faction to show variation
    print("--- Showing Variation Within Same Faction ---")
    
    for i in range(3):
        print(f"\n=== Character {i+1} ===")
        
        # All Tempest Industries but different outcomes
        character = DynamicCharacterGenerator.generate_varied_character('Tempest Industries')
        
        print(f"{character.full_name} ({character.family_line} Line)")
        print(f"Motivation: {character.personal_motivation}")
        print(f"Void: {character.void_score}/10, Soulcredit: {character.soulcredit}")
        
        print(f"\nPersonality Profile:")
        p = character.personality
        print(f"  Risk Tolerance: {p.risk_tolerance}/10")
        print(f"  Void Curiosity: {p.void_curiosity}/10")
        print(f"  Authority Respect: {p.authority_respect}/10")
        print(f"  Family Loyalty: {p.family_loyalty}/10")
        print(f"  Social Preference: {p.social_preference}/10")
        
        print(f"\nKey Skills: Astral Arts {character.astral_arts}, Hacking {character.hacking}, Stealth {character.stealth}")
        
        print(f"\nInventory highlights:")
        for item in character.inventory:
            if item.void_tainted or item.item_type in ['technology', 'talisman']:
                void_note = " [VOID TAINTED]" if item.void_tainted else ""
                print(f"  • {item.name}{void_note}")
    
    # Show how same scenario produces different decisions
    print(f"\n--- Same Scenario, Different Decisions ---")
    
    scenario = DynamicScenarioGenerator.generate_scenario("test_seed_123")  # Fixed seed for comparison
    print(f"Scenario: {scenario['title']}")
    print(f"Description: {scenario['description']}")
    print(f"Void Influence: {scenario['void_influence']}/10")
    
    available_actions = [
        "Investigate using family expertise and void knowledge",
        "Attempt emergency containment ritual",
        "Negotiate with Nexus investigators for cooperation", 
        "Use stealth to gather intelligence without detection",
        "Deploy void-scanning technology to analyze the breach",
        "Seek alliance with other affected parties"
    ]
    
    print(f"\nAvailable Actions:")
    for i, action in enumerate(available_actions, 1):
        print(f"  {i}. {action}")
    
    # Generate 3 different Karsel characters and see their choices
    print(f"\nHow different Karsel Line characters approach this:")
    
    for i in range(3):
        # Reset random seed to get different personalities
        random.seed(int(time.time() * 1000 + i) % 2**32)
        
        char = DynamicCharacterGenerator.generate_varied_character('Tempest Industries', 'Karsel')
        decision_maker = PersonalityDrivenDecisionMaker()
        
        chosen_action, reasoning, context = decision_maker.select_character_action(
            available_actions, char, scenario
        )
        
        print(f"\n{char.given_name} Karsel (Risk: {char.personality.risk_tolerance}, Void Curiosity: {char.personality.void_curiosity}):")
        print(f"  Chooses: {chosen_action}")
        print(f"  Because: {reasoning}")
        print(f"  Appeal Score: {context['appeal_score']}/10")
        
    print(f"\n" + "="*60)
    print("🎭 Dynamic System Features:")
    print("✅ Unique personality profiles drive different decisions")
    print("✅ Same family line, different choices based on personality")
    print("✅ Inventory varies based on resources and personality")
    print("✅ Context-aware void risk analysis")
    print("✅ No hardcoded responses - everything adapts")
    print()
    print("This creates truly diverse training data where character")
    print("personality and situation context drive realistic variations!")


if __name__ == "__main__":
    main()