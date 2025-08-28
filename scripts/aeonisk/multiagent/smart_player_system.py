#!/usr/bin/env python3
"""
Smart Player-Perspective Aeonisk YAGS System

Actually analyzes situations and makes intelligent, context-aware decisions
rather than hardcoded responses. Properly handles void mechanics, inventory,
and realistic character reasoning.
"""

import random
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class VoidRisk(Enum):
    NONE = "no_risk"
    LOW = "low_risk"
    MODERATE = "moderate_risk"
    HIGH = "high_risk"
    EXTREME = "extreme_risk"


@dataclass
class InventoryItem:
    name: str
    item_type: str  # ritual_focus, weapon, talisman, consumable, etc.
    void_tainted: bool = False
    charges: Optional[int] = None
    description: str = ""


@dataclass
class AeoniskCharacter:
    """Properly detailed Aeonisk character with inventory and context-aware reasoning."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    family_reputation: str
    personal_motivation: str
    
    # YAGS Attributes (2-5 range, 3 average)
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
    birth_method: str = "biocreche_pod"
    
    # Skills - all YAGS skills
    athletics: int = 2
    awareness: int = 2
    brawl: int = 2
    charm: int = 2
    guile: int = 2
    sleight: int = 2
    stealth: int = 2
    throw: int = 2
    astral_arts: int = 0
    magick_theory: int = 0
    intimacy_ritual: int = 0
    corporate_influence: int = 0
    debt_law: int = 0
    pilot: int = 0
    drone_operation: int = 0
    hacking: int = 0
    melee: int = 0
    
    # Equipment and inventory
    primary_ritual_item: InventoryItem = None
    inventory: List[InventoryItem] = field(default_factory=list)
    
    def __post_init__(self):
        if self.primary_ritual_item is None:
            self.primary_ritual_item = InventoryItem("Basic Focus", "ritual_focus")
            
    def get_skill_value(self, skill_name: str) -> int:
        """Get skill value by name."""
        return getattr(self, skill_name.lower().replace(' ', '_').replace('-', '_'), 0)
        
    def get_attribute_value(self, attr_name: str) -> int:
        """Get attribute value by name."""
        return getattr(self, attr_name.lower().replace(' ', '_'), 3)
        
    def has_void_tainted_items(self) -> bool:
        """Check if character has any void-tainted items."""
        if self.primary_ritual_item and self.primary_ritual_item.void_tainted:
            return True
        return any(item.void_tainted for item in self.inventory)
        
    def get_relevant_skills_for_action(self, action_type: str, situation_context: Dict[str, Any]) -> List[tuple]:
        """Get relevant skills for an action type, considering character's actual skill levels."""
        skill_mappings = {
            'investigate': [('awareness', 'perception'), ('magick_theory', 'intelligence'), ('corporate_influence', 'empathy')],
            'ritual_attempt': [('astral_arts', 'willpower'), ('magick_theory', 'intelligence')],
            'negotiate': [('charm', 'empathy'), ('corporate_influence', 'empathy'), ('guile', 'empathy')],
            'stealth': [('stealth', 'agility'), ('sleight', 'dexterity')],
            'confront': [('brawl', 'agility'), ('melee', 'dexterity'), ('charm', 'empathy')],
            'alliance': [('charm', 'empathy'), ('intimacy_ritual', 'empathy')],
            'influence': [('corporate_influence', 'empathy'), ('guile', 'empathy')],
            'reconnaissance': [('awareness', 'perception'), ('stealth', 'agility')]
        }
        
        possible_skills = skill_mappings.get(action_type, [('awareness', 'perception')])
        
        # Filter to skills the character actually has (>0) and rank by skill level
        viable_skills = []
        for skill, attr in possible_skills:
            skill_level = self.get_skill_value(skill)
            if skill_level > 0:  # Character has this skill
                viable_skills.append((skill, attr, skill_level))
                
        # If no trained skills, fall back to talents (always ≥2)
        if not viable_skills:
            talent_fallbacks = [
                ('awareness', 'perception', self.awareness),
                ('charm', 'empathy', self.charm),
                ('guile', 'empathy', self.guile),
                ('stealth', 'agility', self.stealth)
            ]
            viable_skills = [(s, a, l) for s, a, l in talent_fallbacks if (s, a) in possible_skills]
            
        # Sort by skill level (character uses their best skills)
        viable_skills.sort(key=lambda x: x[2], reverse=True)
        return viable_skills[:3]  # Top 3 options


class SmartAeoniskAnalyzer:
    """Analyzes situations and makes intelligent, context-aware decisions."""
    
    @staticmethod
    def analyze_void_risk(action_description: str, character: AeoniskCharacter, 
                         scenario: Dict[str, Any]) -> tuple[VoidRisk, str]:
        """Intelligently analyze actual void risk for a specific action."""
        
        action_lower = action_description.lower()
        scenario_desc = scenario.get('description', '').lower()
        
        # No void risk situations
        if all(term not in action_lower for term in ['ritual', 'void', 'forbidden', 'corrupt', 'sacrifice']):
            if all(term not in scenario_desc for term in ['void', 'corrupt', 'taint']):
                if not character.has_void_tainted_items():
                    return VoidRisk.NONE, "No void risk - this is a mundane action with no ritual components or void exposure"
        
        # Check for ritual without offering
        if 'ritual' in action_lower and 'offering' not in action_lower:
            if character.void_score >= 5:
                return VoidRisk.HIGH, "High void risk - attempting ritual without offering while already void-touched (5+ void)"
            else:
                return VoidRisk.MODERATE, "Moderate void risk - ritual without proper offering incurs +1 void"
        
        # Environmental void influence
        void_level = scenario.get('void_influence', 0)
        if void_level >= 7:
            if 'ritual' in action_lower or 'astral' in action_lower:
                return VoidRisk.HIGH, f"High void risk - void level {void_level}/10 severely disrupts all spiritual activities"
            elif 'technology' in action_lower or 'hack' in action_lower:
                return VoidRisk.MODERATE, f"Moderate void risk - void level {void_level}/10 causes technology malfunctions"
        elif void_level >= 4:
            if 'ritual' in action_lower:
                return VoidRisk.MODERATE, f"Moderate void risk - void level {void_level}/10 interferes with ritual stability"
        
        # Void-tainted equipment
        if character.has_void_tainted_items():
            return VoidRisk.LOW, "Low void risk - carrying void-tainted items may cause gradual corruption"
        
        # Investigating void phenomena
        if 'void' in action_lower or 'corrupt' in action_lower:
            return VoidRisk.LOW, "Low void risk - investigating void phenomena without direct contact is relatively safe"
        
        return VoidRisk.NONE, "No significant void risk identified for this action"
    
    @staticmethod
    def analyze_action_suitability(action: str, character: AeoniskCharacter, 
                                 scenario: Dict[str, Any]) -> tuple[int, str]:
        """Analyze how suitable an action is for this specific character (0-10 rating)."""
        
        action_lower = action.lower()
        score = 5  # Base suitability
        reasons = []
        
        # Family line specialization bonuses
        family_data = FAMILY_LINES[character.origin_faction][character.family_line]
        specialty = family_data['specialty']
        
        if 'ritual' in specialty and 'ritual' in action_lower:
            if character.astral_arts >= 4:
                score += 3
                reasons.append(f"{character.family_line} Line specializes in {specialty}, with strong Astral Arts skill")
            else:
                score += 1
                reasons.append(f"{character.family_line} Line background in {specialty}")
        
        if 'enforcement' in specialty and ('confront' in action_lower or 'direct' in action_lower):
            score += 2
            reasons.append(f"{character.family_line} Line trained in enforcement approaches")
        
        if 'trading' in specialty or 'contract' in specialty:
            if 'negotiate' in action_lower:
                score += 3
                reasons.append(f"{character.family_line} Line excels at negotiation and contracts")
            elif 'influence' in action_lower:
                score += 2
                reasons.append(f"{character.family_line} Line understands corporate influence")
        
        if 'void' in specialty and 'void' in scenario.get('description', '').lower():
            score += 2
            reasons.append(f"{character.family_line} Line has experience with void phenomena")
        
        # Skill-based suitability
        relevant_skills = character.get_relevant_skills_for_action(
            action_lower.split()[0], scenario
        )
        
        if relevant_skills:
            best_skill_level = relevant_skills[0][2]
            if best_skill_level >= 5:
                score += 2
                reasons.append(f"Excellent {relevant_skills[0][0]} skill ({best_skill_level})")
            elif best_skill_level >= 3:
                score += 1
                reasons.append(f"Good {relevant_skills[0][0]} skill ({best_skill_level})")
        
        # Personal motivation alignment
        motivation = character.personal_motivation.lower()
        if 'prove' in motivation and ('family' in action_lower or 'honor' in action_lower):
            score += 1
            reasons.append("Aligns with proving family worthiness")
        elif 'redeem' in motivation and 'challenge' not in action_lower:
            score += 1  
            reasons.append("Cautious approach suits redemption goals")
        elif 'challenge' in motivation and 'confront' in action_lower:
            score += 2
            reasons.append("Direct confrontation aligns with challenging authority")
        
        # Faction considerations
        if character.origin_faction == 'Sovereign Nexus':
            if 'harmony' in action_lower or 'stabilize' in action_lower:
                score += 1
                reasons.append("Sovereign Nexus values harmony and stability")
        elif character.origin_faction == 'Tempest Industries':
            if 'disrupt' in action_lower or 'void' in action_lower:
                score += 1
                reasons.append("Tempest Industries comfortable with void and disruption")
        elif character.origin_faction == 'Astral Commerce Group':
            if 'negotiate' in action_lower or 'alliance' in action_lower:
                score += 1
                reasons.append("ACG excels at deal-making and alliances")
        
        # Risk tolerance based on void score and family status
        if character.void_score >= 5:
            if 'ritual' in action_lower:
                score -= 2
                reasons.append("High void score makes ritual work dangerous")
        
        if character.family_reputation == 'disgraced':
            if 'family connections' in action_lower:
                score -= 2
                reasons.append("Disgraced family connections may be unreliable")
            elif 'challenge' in action_lower or 'confront' in action_lower:
                score += 1
                reasons.append("Bold action might restore family honor")
        
        score = max(1, min(10, score))  # Clamp to 1-10
        reason_text = "; ".join(reasons) if reasons else "Standard approach for character type"
        
        return score, reason_text
    
    @staticmethod
    def select_best_action(available_actions: List[str], character: AeoniskCharacter, 
                          scenario: Dict[str, Any]) -> tuple[str, str, int]:
        """Select the most suitable action based on character analysis."""
        
        action_scores = []
        
        for action in available_actions:
            suitability, reasoning = SmartAeoniskAnalyzer.analyze_action_suitability(
                action, character, scenario
            )
            action_scores.append((action, reasoning, suitability))
        
        # Sort by suitability score
        action_scores.sort(key=lambda x: x[2], reverse=True)
        
        # Add some randomness among top choices (top 3 if they're close)
        top_actions = [a for a in action_scores if a[2] >= action_scores[0][2] - 1]
        chosen = random.choice(top_actions[:3])
        
        return chosen[0], chosen[1], chosen[2]


# Actual family lines from the lore with detailed data
FAMILY_LINES = {
    'Sovereign Nexus': {
        'Elaras': {
            'reputation': 'rising',
            'specialty': 'harmony_rituals',
            'strengths': ['spiritual_guidance', 'ritual_mastery', 'diplomatic_harmony'],
            'weaknesses': ['political_naivety', 'void_vulnerability'],
            'typical_goals': ['restore_cosmic_harmony', 'prove_spiritual_worth', 'gain_nexus_recognition']
        },
        'Halessan': {
            'reputation': 'stable', 
            'specialty': 'civic_duty',
            'strengths': ['bureaucratic_efficiency', 'legal_knowledge', 'institutional_loyalty'],
            'weaknesses': ['inflexibility', 'resistance_to_change'],
            'typical_goals': ['maintain_order', 'serve_nexus_faithfully', 'protect_institutions']
        },
        'Ireveth': {
            'reputation': 'stable',
            'specialty': 'enforcement',
            'strengths': ['tactical_thinking', 'authority_presence', 'conflict_resolution'],
            'weaknesses': ['authoritarian_tendencies', 'limited_diplomacy'],
            'typical_goals': ['maintain_security', 'enforce_nexus_will', 'prevent_disorder']
        },
        'Unified Hand': {
            'reputation': 'mysterious',
            'specialty': 'intelligence_gathering',
            'strengths': ['information_networks', 'covert_operations', 'strategic_planning'],
            'weaknesses': ['trust_issues', 'isolation_tendency'],
            'typical_goals': ['gather_intelligence', 'protect_nexus_secrets', 'prevent_threats']
        }
    },
    'Astral Commerce Group': {
        'Kythea': {
            'reputation': 'rising',
            'specialty': 'futures_trading',
            'strengths': ['market_analysis', 'risk_assessment', 'profit_optimization'],
            'weaknesses': ['short_term_focus', 'greed_vulnerability'],
            'typical_goals': ['maximize_profits', 'corner_markets', 'build_trading_empire']
        },
        'Exchange': {
            'reputation': 'stable',
            'specialty': 'contract_law', 
            'strengths': ['legal_expertise', 'negotiation_mastery', 'debt_enforcement'],
            'weaknesses': ['rigid_thinking', 'letter_over_spirit'],
            'typical_goals': ['perfect_contracts', 'enforce_agreements', 'build_legal_precedent']
        },
        'Ledger-Kaine': {
            'reputation': 'declining',
            'specialty': 'debt_collection',
            'strengths': ['financial_investigation', 'pressure_tactics', 'asset_recovery'],
            'weaknesses': ['reputation_damage', 'ethical_compromise'],
            'typical_goals': ['restore_family_standing', 'collect_outstanding_debts', 'prove_competence']
        }
    },
    'Tempest Industries': {
        'Karsel': {
            'reputation': 'disgraced',
            'specialty': 'void_research',
            'strengths': ['void_understanding', 'chaos_navigation', 'reality_manipulation'],
            'weaknesses': ['void_corruption', 'social_isolation', 'instability'],
            'typical_goals': ['redeem_family_name', 'master_void_control', 'prove_research_value']
        },
        'Dissolution': {
            'reputation': 'rising',
            'specialty': 'chaos_theory',
            'strengths': ['system_disruption', 'pattern_breaking', 'adaptive_thinking'],
            'weaknesses': ['unpredictability', 'relationship_difficulty'],
            'typical_goals': ['break_stagnant_systems', 'embrace_change', 'challenge_orthodoxy']
        },
        'Liberty-Void': {
            'reputation': 'stable',
            'specialty': 'liberation_technology',
            'strengths': ['freedom_advocacy', 'anti_authority', 'technological_innovation'],
            'weaknesses': ['authority_conflict', 'anarchist_tendencies'],
            'typical_goals': ['free_oppressed_people', 'develop_liberation_tech', 'resist_control']
        }
    },
    'Arcane Genetics': {
        'Vireya': {
            'reputation': 'stable',
            'specialty': 'bio_enhancement',
            'strengths': ['genetic_artistry', 'biological_mastery', 'enhancement_protocols'],
            'weaknesses': ['ethical_blindness', 'perfectionist_obsession'],
            'typical_goals': ['perfect_genetic_forms', 'advance_human_evolution', 'create_masterpieces']
        },
        'Catalyst': {
            'reputation': 'rising',
            'specialty': 'mutation_control',
            'strengths': ['adaptation_protocols', 'change_management', 'biological_flexibility'],
            'weaknesses': ['instability_risk', 'experimental_nature'],
            'typical_goals': ['master_controlled_mutation', 'develop_adaptation_tech', 'prove_safety']
        }
    },
    'Freeborn': {
        'Unbound': {
            'reputation': 'variable',
            'specialty': 'independence_maintenance',
            'strengths': ['self_reliance', 'authority_resistance', 'adaptability'],
            'weaknesses': ['isolation', 'resource_limitations', 'trust_issues'],
            'typical_goals': ['maintain_freedom', 'resist_control', 'protect_independence']
        },
        'Wild-Current': {
            'reputation': 'variable',
            'specialty': 'natural_harmony',
            'strengths': ['ecosystem_bonding', 'natural_insight', 'environmental_balance'],
            'weaknesses': ['technology_aversion', 'civilization_conflict'],
            'typical_goals': ['preserve_natural_balance', 'resist_artificiality', 'commune_with_nature']
        }
    }
}

GIVEN_NAMES = [
    'Irele', 'Zara', 'Echo', 'Kaelen', 'Varis', 'Liora', 'Wren', 'Nyx',
    'Aurora', 'Void', 'Storm', 'Gene', 'Credit', 'Resonance', 'Free', 
    'Wild', 'Harmony', 'Pulse', 'Drift', 'Catalyst', 'Unity', 'Breach'
]


def generate_character(faction: str, family_line: str) -> AeoniskCharacter:
    """Generate a character with proper family line specialization and realistic inventory."""
    
    line_data = FAMILY_LINES[faction][family_line]
    given_name = random.choice(GIVEN_NAMES)
    full_name = f"{given_name} {family_line}"
    
    # Select personal motivation based on family data and reputation
    if line_data['reputation'] == 'rising':
        motivations = ['Prove family worthiness', 'Seize new opportunities', 'Build lasting legacy']
    elif line_data['reputation'] == 'declining':
        motivations = ['Restore family reputation', 'Uncover family secrets', 'Break from past shame']
    elif line_data['reputation'] == 'disgraced':
        motivations = ['Redeem family name', 'Forge new identity', 'Challenge the system']
    elif line_data['reputation'] == 'mysterious':
        motivations = ['Fulfill hidden agenda', 'Gather crucial intelligence', 'Serve greater purpose']
    else:  # stable
        motivations = ['Maintain family honor', 'Serve faction interests', 'Protect traditions']
    
    char = AeoniskCharacter(
        given_name=given_name,
        family_line=family_line,
        full_name=full_name,
        origin_faction=faction,
        family_reputation=line_data['reputation'],
        personal_motivation=random.choice(motivations)
    )
    
    # Generate realistic attributes
    char.strength = random.randint(2, 5)
    char.health = random.randint(2, 5)
    char.agility = random.randint(2, 5)
    char.dexterity = random.randint(2, 5)
    char.perception = random.randint(2, 5)
    char.intelligence = random.randint(2, 5)
    char.empathy = random.randint(2, 5)
    char.willpower = random.randint(2, 5)
    
    # Apply family line specialization
    specialty = line_data['specialty']
    
    if 'ritual' in specialty or 'harmony' in specialty:
        char.willpower = min(5, char.willpower + 1)
        char.astral_arts = random.randint(4, 6)
        char.magick_theory = random.randint(2, 4)
    elif 'enforcement' in specialty or 'tactical' in specialty:
        char.perception = min(5, char.perception + 1)
        char.awareness = random.randint(3, 5)
        char.brawl = random.randint(3, 4)
    elif 'trading' in specialty or 'contract' in specialty or 'debt' in specialty:
        char.empathy = min(5, char.empathy + 1)
        char.corporate_influence = random.randint(4, 6)
        char.debt_law = random.randint(3, 5)
        char.guile = random.randint(3, 4)
    elif 'void' in specialty or 'chaos' in specialty:
        char.willpower = min(5, char.willpower + 1)
        char.void_score = random.randint(1, 3)
        char.astral_arts = random.randint(3, 5)
        char.stealth = random.randint(2, 4)
    elif 'bio' in specialty or 'genetic' in specialty:
        char.intelligence = min(5, char.intelligence + 1)
        char.magick_theory = random.randint(3, 5)
    elif 'intelligence' in specialty:
        char.perception = min(5, char.perception + 1)
        char.intelligence = min(5, char.intelligence + 1)
        char.awareness = random.randint(4, 6)
        char.guile = random.randint(3, 5)
        char.stealth = random.randint(3, 4)
    elif 'independence' in specialty:
        char.athletics = random.randint(3, 5)
        char.stealth = random.randint(3, 4)
        char.birth_method = 'natural'
    
    # Faction-wide effects
    if faction == 'Sovereign Nexus':
        char.soulcredit = random.randint(0, 3)
        char.intimacy_ritual = random.randint(1, 3)
    elif faction == 'Astral Commerce Group':
        char.soulcredit = random.randint(2, 6)
        char.charm = random.randint(3, 4)
    elif faction == 'Tempest Industries':
        char.hacking = random.randint(2, 5)
        if random.random() < 0.3:  # 30% chance of void taint
            char.void_score = random.randint(1, 2)
    elif faction == 'Arcane Genetics':
        char.health = min(5, char.health + 1)  # Bio enhancements
    elif faction == 'Freeborn':
        char.birth_method = 'natural'
        char.soulcredit = random.randint(-2, 1)
        char.athletics = random.randint(3, 5)
    
    # Generate appropriate ritual item and inventory
    char.primary_ritual_item = _generate_ritual_item(family_line, char.void_score > 0)
    char.inventory = _generate_starting_inventory(faction, family_line, char.soulcredit)
    
    return char


def _generate_ritual_item(family_line: str, has_void: bool) -> InventoryItem:
    """Generate appropriate ritual item based on family line."""
    ritual_items = {
        'Elaras': ['Harmony Crystal', 'Unity Sigil', 'Resonance Bell'],
        'Halessan': ['Civic Seal', 'Authority Rod', 'Order Stone'],
        'Ireveth': ['Enforcement Badge', 'Justice Scale', 'Law Crystal'],
        'Unified Hand': ['Observer Stone', 'Information Matrix', 'Truth Lens'],
        'Kythea': ['Market Predictor', 'Future Glass', 'Trade Compass'],
        'Exchange': ['Contract Seal', 'Agreement Stone', 'Bond Crystal'],
        'Ledger-Kaine': ['Debt Tracker', 'Collection Rod', 'Payment Stone'],
        'Karsel': ['Void Shard', 'Chaos Fragment', 'Reality Lens'],
        'Dissolution': ['Change Catalyst', 'Entropy Stone', 'Flux Crystal'],
        'Liberty-Void': ['Freedom Key', 'Liberation Spark', 'Unbound Stone'],
        'Vireya': ['Gene Helix', 'Bio Matrix', 'Evolution Seed'],
        'Catalyst': ['Mutation Stone', 'Change Crystal', 'Adaptation Core'],
        'Unbound': ['Freedom Stone', 'Wild Focus', 'Independence Crystal'],
        'Wild-Current': ['Nature Stone', 'Flow Crystal', 'Current Focus']
    }
    
    name = random.choice(ritual_items.get(family_line, ['Ancient Focus', 'Family Heirloom']))
    
    return InventoryItem(
        name=name,
        item_type="ritual_focus",
        void_tainted=has_void and random.random() < 0.4,  # 40% chance if character has void
        description=f"Sacred {family_line} Line ritual focus"
    )


def _generate_starting_inventory(faction: str, family_line: str, soulcredit: int) -> List[InventoryItem]:
    """Generate realistic starting inventory based on faction and resources."""
    inventory = []
    
    # Basic gear everyone has
    inventory.append(InventoryItem("Personal Commlink", "technology", description="Standard communication device"))
    inventory.append(InventoryItem("Identity Credentials", "documents", description=f"{faction} identification"))
    
    # Elemental talismans based on soulcredit
    if soulcredit >= 3:
        talisman_types = ['Spark Talisman', 'Drip Core', 'Breath Wisp', 'Grain Stone']
        inventory.append(InventoryItem(
            random.choice(talisman_types), 
            "talisman", 
            charges=random.randint(50, 100),
            description="Charged elemental energy source"
        ))
    
    # Faction-specific gear
    if faction == 'Sovereign Nexus':
        inventory.append(InventoryItem("Nexus Authority Badge", "credentials", description="Official Nexus identification"))
        if 'enforcement' in FAMILY_LINES[faction][family_line]['specialty']:
            inventory.append(InventoryItem("Stun Baton", "weapon", description="Non-lethal enforcement tool"))
    
    elif faction == 'Astral Commerce Group':
        inventory.append(InventoryItem("Contract Pad", "technology", description="Legal document processor"))
        inventory.append(InventoryItem("Credit Ledger", "technology", description="Soulcredit tracking device"))
    
    elif faction == 'Tempest Industries':
        inventory.append(InventoryItem("Void Scanner", "technology", description="Detects void signatures"))
        if random.random() < 0.3:  # Some have void-tainted gear
            inventory.append(InventoryItem(
                "Prototype Device", "technology", 
                void_tainted=True,
                description="Experimental void-powered equipment"
            ))
    
    elif faction == 'Arcane Genetics':
        inventory.append(InventoryItem("Bio Scanner", "technology", description="Genetic analysis tool"))
        inventory.append(InventoryItem("Enhancement Serum", "consumable", charges=1, description="Minor bio enhancement"))
    
    elif faction == 'Freeborn':
        inventory.append(InventoryItem("Survival Kit", "tools", description="Wilderness survival gear"))
        inventory.append(InventoryItem("Anti-Tracker Device", "technology", description="Blocks surveillance"))
    
    # Personal items based on family reputation
    family_data = FAMILY_LINES[faction][family_line]
    if family_data['reputation'] == 'rising':
        inventory.append(InventoryItem("Family Signet", "jewelry", description="Symbol of rising status"))
    elif family_data['reputation'] == 'disgraced':
        inventory.append(InventoryItem("Hidden Cache Key", "tools", description="Access to family emergency resources"))
    
    return inventory


def create_smart_dataset_entry(character: AeoniskCharacter, scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Create an intelligent dataset entry with proper context analysis."""
    
    # Available actions (expanded and more specific)
    available_actions = [
        "Investigate the source using family connections and specialized knowledge",
        "Attempt a stabilizing ritual using personal ritual focus and appropriate offering", 
        "Negotiate with rival factions present to form temporary alliances",
        "Gather intelligence through careful stealth observation and analysis",
        "Directly confront the responsible parties with faction backing and authority",
        "Seek alliance with other affected parties to pool resources and expertise",
        "Use corporate/family influence to access restricted areas and information",
        "Perform detailed reconnaissance to understand the full scope of the threat",
        "Consult family archives and historical records for relevant precedents",
        "Deploy technological assets and scanning equipment for data gathering"
    ]
    
    # Use smart analyzer to select best action
    analyzer = SmartAeoniskAnalyzer()
    chosen_action, reasoning, suitability = analyzer.select_best_action(available_actions, character, scenario)
    
    # Analyze void risk for the chosen action
    void_risk, void_explanation = analyzer.analyze_void_risk(chosen_action, character, scenario)
    
    # Determine most appropriate skill check
    relevant_skills = character.get_relevant_skills_for_action(chosen_action.split()[0].lower(), scenario)
    
    if relevant_skills:
        skill_name, attr_name, skill_level = relevant_skills[0]
        attr_value = character.get_attribute_value(attr_name)
    else:
        # Fallback
        skill_name, attr_name, skill_level = 'awareness', 'perception', character.awareness
        attr_value = character.perception
    
    # Calculate realistic difficulty
    base_difficulty = 18  # Standard YAGS moderate
    void_modifier = min(scenario.get('void_influence', 0) // 2, 3)  # Max +3 from void
    final_difficulty = base_difficulty + void_modifier
    
    # Generate family-specific reasoning
    family_data = FAMILY_LINES[character.origin_faction][character.family_line]
    family_influence = f"The {character.family_line} Line's specialization in {family_data['specialty']} makes this approach natural - {reasoning}"
    
    # Risk assessment based on actual character state and situation
    risk_factors = []
    if void_risk != VoidRisk.NONE:
        risk_factors.append(f"Void exposure risk: {void_explanation}")
    if character.family_reputation == 'disgraced':
        risk_factors.append("Family disgrace limits social options and increases scrutiny")
    if character.soulcredit < 0:
        risk_factors.append("Negative soulcredit restricts access to faction resources")
    
    risk_assessment = "; ".join(risk_factors) if risk_factors else "Minimal personal risk for this approach"
    
    # Expected outcome based on character capabilities
    success_factors = []
    if skill_level >= 4:
        success_factors.append(f"Strong {skill_name} skill ({skill_level}) increases success likelihood")
    if character.soulcredit >= 3:
        success_factors.append("Good soulcredit provides access to resources and cooperation")
    if family_data['reputation'] in ['rising', 'stable']:
        success_factors.append("Family reputation opens doors and provides credibility")
    
    expected_outcome = f"Moderate to high success chance. {' '.join(success_factors)}"
    
    return {
        'task_id': 'AEONISK-SMART-001',
        'domain': {
            'core': 'player_decision_making',
            'subdomain': 'contextual_action_reasoning'
        },
        'scenario': scenario['description'],
        'location': scenario['location'],
        'faction_context': f"Tensions: {', '.join(scenario['faction_tensions'])}",
        'void_influence': scenario['void_influence'],
        'character': {
            'name': character.full_name,
            'family_line': character.family_line,
            'origin_faction': character.origin_faction,
            'family_reputation': character.family_reputation,
            'personal_motivation': character.personal_motivation,
            'void_score': character.void_score,
            'soulcredit': character.soulcredit,
            'birth_method': character.birth_method,
            'key_stats': {
                'strength': character.strength,
                'agility': character.agility,
                'perception': character.perception,
                'intelligence': character.intelligence,
                'empathy': character.empathy,
                'willpower': character.willpower
            },
            'skills': {
                skill: getattr(character, skill)
                for skill in ['astral_arts', 'corporate_influence', 'hacking', 'stealth', 'awareness', 'charm', 'guile']
                if getattr(character, skill) > 2
            },
            'primary_ritual_item': {
                'name': character.primary_ritual_item.name,
                'void_tainted': character.primary_ritual_item.void_tainted
            },
            'inventory': [
                {'name': item.name, 'type': item.item_type, 'void_tainted': item.void_tainted}
                for item in character.inventory
            ]
        },
        'available_actions': available_actions,
        'player_decision': {
            'chosen_action': chosen_action,
            'suitability_score': f"{suitability}/10",
            'primary_reasoning': reasoning,
            'family_influence': family_influence,
            'risk_assessment': risk_assessment,
            'expected_outcome': expected_outcome,
            'backup_plan': f"If this fails, fall back on {family_data['strengths'][0]} or seek faction support"
        },
        'void_analysis': {
            'risk_level': void_risk.value,
            'explanation': void_explanation,
            'character_void_status': f"{character.void_score}/10 (threshold effects at 5+)",
            'environmental_factors': f"Ambient void level {scenario['void_influence']}/10"
        },
        'mechanical_analysis': {
            'attribute_used': attr_name.title(),
            'skill_used': skill_name.title().replace('_', ' '),
            'character_skill_level': skill_level,
            'estimated_difficulty': final_difficulty,
            'success_formula': f"{attr_name.title()} {attr_value} × {skill_name.title()} {skill_level} + d20 vs {final_difficulty}",
            'reasoning': f"Action requires {attr_name}-based {skill_name}; difficulty increased by void influence"
        },
        'training_focus': {
            'contextual_analysis': "Teaching AI to analyze actual situation context rather than generic responses",
            'family_specialization': f"How {character.family_line} Line specialty affects decision-making",
            'void_risk_assessment': "Proper understanding of when actions actually incur void risk",
            'resource_management': "Considering character's actual capabilities and limitations"
        }
    }


def main():
    """Demonstrate the smart, context-aware system."""
    
    print("=== Smart Aeonisk YAGS Player-Perspective System ===")
    print("Context-aware decision making with proper void analysis and inventory\n")
    
    # Generate character with full context
    character = generate_character('Tempest Industries', 'Karsel')
    
    print(f"--- {character.full_name} ---")
    print(f"Family: {character.family_line} Line of {character.origin_faction}")
    print(f"Reputation: {character.family_reputation} family ({character.personal_motivation})")
    print(f"Birth: {character.birth_method}")
    print()
    print(f"Attributes: Str {character.strength}, Hea {character.health}, Agi {character.agility}, Dex {character.dexterity}")
    print(f"           Per {character.perception}, Int {character.intelligence}, Emp {character.empathy}, Wil {character.willpower}")
    print(f"Spiritual: Void {character.void_score}/10, Soulcredit {character.soulcredit}")
    print()
    print(f"Notable Skills:")
    skills_to_show = ['astral_arts', 'corporate_influence', 'hacking', 'stealth', 'awareness', 'brawl']
    for skill in skills_to_show:
        value = getattr(character, skill)
        if value > 2:
            print(f"  {skill.replace('_', ' ').title()}: {value}")
    print()
    print(f"Primary Ritual Item: {character.primary_ritual_item.name}")
    if character.primary_ritual_item.void_tainted:
        print("  ⚠️  VOID TAINTED - This item carries corruption!")
    print()
    print("Inventory:")
    for item in character.inventory:
        void_warning = " [VOID TAINTED]" if item.void_tainted else ""
        charges_info = f" ({item.charges} charges)" if item.charges else ""
        print(f"  • {item.name} ({item.item_type}){charges_info}{void_warning}")
    print()
    
    # Generate scenario with void influence
    scenario = {
        'title': 'Void Containment Breach',
        'location': 'Research Station Omega-7, Deep Void Zone',
        'description': 'A containment breach has released raw void energy into a research facility, causing reality distortions and threatening nearby settlements.',
        'faction_tensions': ['Tempest Industries under investigation', 'Sovereign Nexus demands accountability'],
        'void_influence': 7,  # High void influence
        'key_elements': ['void energy leak', 'reality distortions', 'trapped researchers', 'expanding corruption']
    }
    
    print("--- Scenario Context ---")
    print(f"Title: {scenario['title']}")
    print(f"Location: {scenario['location']}")
    print(f"Description: {scenario['description']}")
    print(f"Void Influence: {scenario['void_influence']}/10 (HIGH - affects all technology and rituals)")
    print(f"Tensions: {', '.join(scenario['faction_tensions'])}")
    print()
    
    # Create smart dataset entry
    entry = create_smart_dataset_entry(character, scenario)
    
    print("--- Smart Decision Analysis ---")
    print(f"Chosen Action: {entry['player_decision']['chosen_action']}")
    print(f"Suitability: {entry['player_decision']['suitability_score']}")
    print(f"Reasoning: {entry['player_decision']['primary_reasoning']}")
    print()
    print(f"Void Risk: {entry['void_analysis']['risk_level'].replace('_', ' ').title()}")
    print(f"Explanation: {entry['void_analysis']['explanation']}")
    print()
    print(f"Skill Check: {entry['mechanical_analysis']['success_formula']}")
    print(f"Reasoning: {entry['mechanical_analysis']['reasoning']}")
    print()
    
    print("--- Complete Dataset Entry ---")
    print("=" * 60)
    print(yaml.dump(entry, default_flow_style=False, sort_keys=False))
    
    print("=" * 60)
    print("🧠 Smart System Features:")
    print("✅ Context-aware void risk analysis (no false positives)")
    print("✅ Character specialization affects action selection") 
    print("✅ Proper inventory with void-tainted item tracking")
    print("✅ Family reputation impacts available options")
    print("✅ Realistic skill checks based on character abilities")
    print("✅ Suitability scoring prevents nonsensical choices")
    print("✅ Environmental factors properly considered")
    print()
    print("This generates intelligent training data that teaches AI to think")
    print("like experienced players who understand the game world!")


if __name__ == "__main__":
    main()