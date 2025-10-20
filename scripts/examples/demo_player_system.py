#!/usr/bin/env python3
"""
Demo of the Player-Perspective Aeonisk YAGS LLM Training System

This demonstrates the rich character generation, family lines, and 
dataset structure for training AI to make player-like decisions.
"""

import random
import yaml
from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class AeoniskCharacter:
    """Rich Aeonisk character with proper family lineage."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    family_reputation: str
    personal_motivation: str
    
    # YAGS Attributes
    strength: int = 3
    agility: int = 3
    perception: int = 3
    intelligence: int = 3
    empathy: int = 3
    willpower: int = 3
    
    # Aeonisk specifics
    void_score: int = 0
    soulcredit: int = 0
    
    # Key skills
    astral_arts: int = 0
    corporate_influence: int = 0
    hacking: int = 0
    stealth: int = 0
    awareness: int = 2
    
    primary_ritual_item: str = ""


# Actual family lines from the lore
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

GIVEN_NAMES = ['Irele', 'Zara', 'Echo', 'Kaelen', 'Varis', 'Liora', 'Wren', 'Nyx']


def generate_character(faction: str, family_line: str) -> AeoniskCharacter:
    """Generate a rich Aeonisk character."""
    
    line_data = FAMILY_LINES[faction][family_line]
    given_name = random.choice(GIVEN_NAMES)
    full_name = f"{given_name} {family_line}"
    
    # Generate personal motivation based on family reputation
    motivations = {
        'rising': ['Prove family worthiness', 'Seize new opportunities', 'Build lasting legacy'],
        'stable': ['Maintain family honor', 'Serve faction interests', 'Protect traditions'],
        'declining': ['Restore family reputation', 'Uncover family secrets', 'Break from past shame'],
        'disgraced': ['Redeem family name', 'Forge new identity', 'Challenge the system'],
        'mysterious': ['Fulfill hidden agenda', 'Gather crucial intelligence']
    }
    
    char = AeoniskCharacter(
        given_name=given_name,
        family_line=family_line,
        full_name=full_name,
        origin_faction=faction,
        family_reputation=line_data['reputation'],
        personal_motivation=random.choice(motivations.get(line_data['reputation'], motivations['stable']))
    )
    
    # Generate attributes
    char.strength = random.randint(2, 5)
    char.agility = random.randint(2, 5) 
    char.perception = random.randint(2, 5)
    char.intelligence = random.randint(2, 5)
    char.empathy = random.randint(2, 5)
    char.willpower = random.randint(2, 5)
    
    # Family line specializations
    specialty = line_data['specialty']
    if 'ritual' in specialty or 'harmony' in specialty:
        char.willpower = min(5, char.willpower + 1)
        char.astral_arts = random.randint(3, 6)
    elif 'enforcement' in specialty:
        char.perception = min(5, char.perception + 1)
        char.awareness = random.randint(3, 5)
    elif 'trading' in specialty or 'contract' in specialty:
        char.empathy = min(5, char.empathy + 1)
        char.corporate_influence = random.randint(3, 6)
    elif 'void' in specialty or 'chaos' in specialty:
        char.willpower = min(5, char.willpower + 1)
        char.void_score = random.randint(1, 3)
        char.astral_arts = random.randint(2, 5)
    elif 'bio' in specialty:
        char.intelligence = min(5, char.intelligence + 1)
    
    # Faction traits
    if faction == 'Sovereign Nexus':
        char.soulcredit = random.randint(0, 3)
    elif faction == 'Astral Commerce Group':
        char.soulcredit = random.randint(1, 5)
    elif faction == 'Tempest Industries':
        char.hacking = random.randint(2, 5)
        char.stealth = random.randint(2, 4)
    elif faction == 'Freeborn':
        char.soulcredit = random.randint(-2, 1)
    
    # Generate ritual item
    ritual_items = {
        'Elaras': ['Harmony Crystal', 'Unity Sigil'],
        'Halessan': ['Civic Seal', 'Authority Rod'],
        'Karsel': ['Void Shard', 'Chaos Fragment'],
        'Vireya': ['Gene Helix', 'Bio Matrix'],
        'Unbound': ['Freedom Stone', 'Wild Focus']
    }
    
    char.primary_ritual_item = random.choice(ritual_items.get(family_line, ['Ancient Focus', 'Family Heirloom']))
    
    return char


def generate_scenario() -> Dict[str, Any]:
    """Generate a rich Aeonisk scenario."""
    scenarios = [
        {
            'title': 'Memory Theft at Biocreche Facility',
            'location': 'Abandoned Biocreche Pod Complex, Arcadia',
            'description': 'Corporate agents are stealing memories from gestating Echo Children, threatening to destabilize multiple family lineages.',
            'faction_tensions': ['Arcane Genetics vs Astral Commerce Group', 'Sovereign Nexus intervention'],
            'void_influence': random.randint(2, 5),
            'key_elements': ['corrupted pod matrices', 'stolen memory fragments', 'Echo Children witnesses']
        },
        {
            'title': 'Ley Line Convergence Disruption', 
            'location': 'Primary Ley Nexus, Aeonisk Prime',
            'description': 'Ancient ley lines are being artificially destabilized, causing reality fluctuations across the homeworld.',
            'faction_tensions': ['Tempest Industries suspected', 'Aether Dynamics investigating'],
            'void_influence': random.randint(3, 7),
            'key_elements': ['unstable astral currents', 'malfunctioning tech', 'temporal anomalies']
        },
        {
            'title': 'Bond Betrayal Investigation',
            'location': 'Resonance Commune Sanctuary, Nimbus',
            'description': 'A sacred bonding ritual was sabotaged, severing dozens of spiritual connections and leaving participants void-touched.',
            'faction_tensions': ['Internal Commune strife', 'External faction manipulation'],
            'void_influence': random.randint(1, 4),
            'key_elements': ['severed bonds', 'traumatized participants', 'ritual sabotage evidence']
        }
    ]
    
    return random.choice(scenarios)


def create_player_dataset_entry(character: AeoniskCharacter, scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Create a player-perspective dataset entry."""
    
    # Available actions for this scenario
    available_actions = [
        "Investigate the source using family connections and specialized knowledge",
        "Attempt a ritual to stabilize the situation using personal ritual focus", 
        "Negotiate with rival factions present to form temporary alliances",
        "Gather intelligence through stealth observation and careful analysis",
        "Directly confront the responsible parties with faction backing",
        "Seek alliance with other affected parties to pool resources",
        "Use corporate/family influence to access restricted areas",
        "Perform reconnaissance to understand the full scope of the threat"
    ]
    
    # Mock what an LLM would generate for player decision-making
    if character.family_line == 'Elaras':
        chosen_action = available_actions[0]  # Use family connections
        reasoning = f"As an {character.family_line}, I have a duty to restore harmony. My family's spiritual connections can provide insight into this corruption while maintaining our reputation for guidance."
    elif character.family_line == 'Karsel':
        chosen_action = available_actions[6]  # Use influence 
        reasoning = f"The {character.family_line} Line may be disgraced, but we understand void corruption better than anyone. I'll use what influence remains to access the truth."
    elif character.origin_faction == 'Astral Commerce Group':
        chosen_action = available_actions[2]  # Negotiate
        reasoning = f"As {character.origin_faction}, negotiation and contract-making are my strengths. I can potentially turn this crisis into an opportunity."
    else:
        chosen_action = random.choice(available_actions)
        reasoning = f"Given my {character.family_line} background, this action aligns with my family's approach to challenges."
    
    # Mock skill reasoning
    if 'investigate' in chosen_action.lower():
        attribute_used = 'Intelligence'
        skill_used = 'Awareness'
    elif 'ritual' in chosen_action.lower():
        attribute_used = 'Willpower'
        skill_used = 'Astral Arts'
    elif 'negotiate' in chosen_action.lower():
        attribute_used = 'Empathy'
        skill_used = 'Corporate Influence'
    elif 'stealth' in chosen_action.lower():
        attribute_used = 'Agility'
        skill_used = 'Stealth'
    else:
        attribute_used = 'Intelligence'
        skill_used = 'Awareness'
    
    # Create dataset entry in proper format
    entry = {
        'task_id': 'AEONISK-PLAYER-DEMO-001',
        'domain': {
            'core': 'player_decision_making',
            'subdomain': 'action_choice_reasoning'
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
            'key_stats': {
                'willpower': character.willpower,
                'empathy': character.empathy,
                'intelligence': character.intelligence
            },
            'notable_skills': {
                'astral_arts': character.astral_arts,
                'corporate_influence': character.corporate_influence,
                'hacking': character.hacking,
                'stealth': character.stealth
            },
            'ritual_focus': character.primary_ritual_item
        },
        'available_actions': available_actions,
        'player_decision': {
            'chosen_action': chosen_action,
            'primary_reasoning': reasoning,
            'family_influence': f"The {character.family_line} Line's specialty in {FAMILY_LINES[character.origin_faction][character.family_line]['specialty']} guides this choice",
            'risk_assessment': f"Moderate risk to family reputation and personal safety, but aligns with {character.personal_motivation.lower()}",
            'expected_outcome': "Hope to resolve the crisis while advancing family interests and personal goals",
            'backup_plan': "If primary approach fails, fall back on faction resources and family connections"
        },
        'mechanical_analysis': {
            'attribute_used': attribute_used,
            'skill_used': skill_used,
            'estimated_difficulty': 18 + scenario['void_influence'],
            'reasoning': f"This action requires {attribute_used.lower()} and {skill_used.lower()}, with void influence making it more difficult",
            'void_complications': f"Void level {scenario['void_influence']} may cause reality distortions affecting technology and spiritual connections"
        },
        'training_focus': {
            'family_line_behavior': f"How {character.family_line} approaches challenges based on their reputation and specialty",
            'faction_loyalty': f"Balancing {character.origin_faction} interests with personal motivations",
            'void_risk_management': "Understanding when to accept void exposure for greater goals",
            'social_consequences': "Considering political ramifications of actions on family and faction standing"
        }
    }
    
    return entry


def main():
    """Run the player-perspective demo."""
    
    print("=== Aeonisk YAGS Player-Perspective Training System Demo ===")
    print("Rich character generation with actual family lines and faction lore\n")
    
    # Generate diverse characters from different factions and family lines
    demo_configs = [
        ('Sovereign Nexus', 'Elaras'),
        ('Astral Commerce Group', 'Kythea'),
        ('Tempest Industries', 'Karsel'),
        ('Arcane Genetics', 'Vireya'),
        ('Freeborn', 'Unbound')
    ]
    
    characters = []
    
    for faction, family_line in demo_configs:
        char = generate_character(faction, family_line)
        characters.append(char)
        
        print(f"--- {char.full_name} ---")
        print(f"Family: {char.family_line} Line of {char.origin_faction}")
        print(f"Reputation: {char.family_reputation} family standing")
        print(f"Personal Drive: {char.personal_motivation}")
        print(f"Attributes: Str {char.strength}, Agi {char.agility}, Per {char.perception}, Int {char.intelligence}, Emp {char.empathy}, Wil {char.willpower}")
        print(f"Spiritual: Void {char.void_score}/10, Soulcredit {char.soulcredit}")
        print(f"Key Skills: Astral Arts {char.astral_arts}, Corporate Influence {char.corporate_influence}, Hacking {char.hacking}")
        print(f"Ritual Focus: {char.primary_ritual_item}")
        print()
    
    # Generate scenario
    print("--- Rich Scenario Generation ---")
    scenario = generate_scenario()
    print(f"Title: {scenario['title']}")
    print(f"Location: {scenario['location']}")
    print(f"Description: {scenario['description']}")
    print(f"Faction Tensions: {', '.join(scenario['faction_tensions'])}")
    print(f"Void Influence: {scenario['void_influence']}/10")
    print(f"Key Elements: {', '.join(scenario['key_elements'])}")
    print()
    
    # Create player-perspective dataset entry
    print("--- Player-Perspective Dataset Entry ---")
    character = characters[0]  # Use Elaras character
    entry = create_player_dataset_entry(character, scenario)
    
    print("This shows the dataset format for training AI to make character decisions:")
    print("=" * 60)
    print(yaml.dump(entry, default_flow_style=False, sort_keys=False))
    
    print("=" * 60)
    print("Key Features of This System:")
    print("• Rich character generation with actual Aeonisk family lines")
    print("• Faction-specific motivations and specializations")
    print("• Player decision-making reasoning (not just DM mechanics)")
    print("• Family reputation and political consequences")
    print("• Void corruption risk assessment")
    print("• LLM-generated narrative reasoning for each choice")
    print()
    print("With LLM API keys, this system generates hundreds of diverse")
    print("training examples for teaching AI to play like human players!")


if __name__ == "__main__":
    main()