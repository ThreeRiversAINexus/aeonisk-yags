#!/usr/bin/env python3
"""
Demo of the player-perspective system structure without requiring LLM API keys.
Shows the rich character generation and dataset format.
"""

import asyncio
import json
import random
import yaml
from datetime import datetime
from pathlib import Path
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aeonisk.multiagent.player_perspective_llm import (
    AeoniskWorldBuilder, AeoniskCharacter
)

async def demo_character_generation():
    """Demonstrate the rich character generation system."""
    
    print("=== Aeonisk YAGS Player-Perspective Character Generation Demo ===")
    print("Showing the depth of character creation with proper family lines and faction lore\n")
    
    # Generate characters from different factions and family lines
    demo_configs = [
        ('Sovereign Nexus', 'Elaras'),
        ('Astral Commerce Group', 'Kythea'), 
        ('Tempest Industries', 'Karsel'),
        ('Arcane Genetics', 'Vireya'),
        ('Freeborn', 'Unbound')
    ]
    
    characters = []
    
    for faction, family_line in demo_configs:
        char = AeoniskWorldBuilder.generate_character(faction, family_line)
        characters.append(char)
        
        print(f"--- {char.full_name} ---")
        print(f"Family: {char.family_line} Line of {char.origin_faction}")
        print(f"Reputation: {char.family_reputation} family standing")
        print(f"Birth Method: {char.birth_method}")
        print(f"Personal Drive: {char.personal_motivation}")
        print(f"")
        print(f"Attributes:")
        print(f"  Str {char.strength}, Hea {char.health}, Agi {char.agility}, Dex {char.dexterity}")
        print(f"  Per {char.perception}, Int {char.intelligence}, Emp {char.empathy}, Wil {char.willpower}")
        print(f"")
        print(f"Spiritual Status:")
        print(f"  Void Score: {char.void_score}/10")
        print(f"  Soulcredit: {char.soulcredit}")
        print(f"")
        print(f"Notable Skills:")
        skills = ['astral_arts', 'corporate_influence', 'hacking', 'stealth', 'awareness']
        for skill in skills:
            value = getattr(char, skill)
            if value > 2:
                print(f"  {skill.replace('_', ' ').title()}: {value}")
        print(f"")
        print(f"Equipment:")
        print(f"  Primary Ritual Item: {char.primary_ritual_item}")
        print(f"")
        print("="*60)
        print()
        
    # Generate scenarios
    print("--- Rich Scenario Generation ---")
    
    for i in range(3):
        situation = AeoniskWorldBuilder.generate_scenario_situation()
        print(f"Scenario {i+1}: {situation['title']}")
        print(f"Location: {situation['location']}")
        print(f"Description: {situation['description']}")
        print(f"Faction Tensions: {', '.join(situation['faction_tensions'])}")
        print(f"Void Influence: {situation['void_influence']}/10")
        print(f"Key Elements: {', '.join(situation['key_elements'])}")
        print()
        
    # Generate mock player decision dataset entry
    print("--- Player-Perspective Dataset Entry Structure ---")
    
    character = characters[0]  # Use first character
    situation = AeoniskWorldBuilder.generate_scenario_situation()
    
    # Mock what the LLM would generate
    mock_decision = {
        'chosen_action': 'Investigate the source using family connections and Elaras Line spiritual guidance',
        'primary_reasoning': f'As an {character.family_line}, I have duty to restore harmony and my family connections can provide access to restricted information',
        'family_influence': f'The {character.family_line} Line specializes in spiritual guidance and harmony restoration - this situation threatens the very foundations we protect',
        'risk_assessment': 'Moderate risk to family reputation if investigation reveals uncomfortable truths, but the spiritual threat requires immediate action',
        'expected_outcome': 'Uncover the source of corruption while maintaining family honor and potentially gaining Soulcredit for service',
        'backup_plan': 'If family connections fail, fall back on Sovereign Nexus official channels and ritual purification protocols'
    }
    
    mock_skill_reasoning = {
        'attribute_choice': 'Intelligence',
        'skill_choice': 'Awareness', 
        'difficulty_estimate': 18,
        'reasoning': f'Investigation requires careful observation and analysis, playing to {character.family_line} strengths in spiritual perception',
        'void_complications': f'Void level {situation["void_influence"]} may cause reality distortions affecting perception and family spiritual connections',
        'success_description': 'Successfully identify corruption source while maintaining family connections and gaining valuable intelligence',
        'failure_consequences': 'Miss crucial details, potentially expose family to spiritual contamination, or alert hostile factions to investigation'
    }
    
    # Create sample dataset entry
    dataset_entry = {
        'task_id': 'AEONISK-PLAYER-DEMO-001',
        'domain': {
            'core': 'player_decision_making',
            'subdomain': 'action_choice_reasoning'
        },
        'scenario': situation['description'],
        'location': situation['location'],
        'faction_context': f"Tensions between {', '.join(situation['faction_tensions'])}",
        'void_influence': situation['void_influence'],
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
                'awareness': character.awareness
            }
        },
        'available_actions': [
            'Investigate using family connections',
            'Attempt stabilization ritual',
            'Negotiate with factions',
            'Gather intelligence stealthily',
            'Direct confrontation',
            'Seek alliances'
        ],
        'player_decision': mock_decision,
        'mechanical_analysis': mock_skill_reasoning,
        'training_focus': {
            'family_line_behavior': f"How {character.family_line} approaches challenges",
            'faction_loyalty': f"Balancing {character.origin_faction} interests",
            'void_risk_management': "Managing corruption exposure",
            'social_consequences': "Understanding political ramifications"
        }
    }
    
    print("Sample Dataset Entry (YAML format):")
    print("="*60)
    print(yaml.dump(dataset_entry, default_flow_style=False, sort_keys=False))
    
    # Save demo dataset
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    demo_file = Path(f'./demo_player_perspective_{timestamp}.yaml')
    
    with open(demo_file, 'w') as f:
        f.write("# Aeonisk YAGS Player-Perspective Training Dataset (Demo)\n")
        f.write("# Demonstrates the rich character and decision-making data structure\n\n")
        yaml.dump(dataset_entry, f, default_flow_style=False, sort_keys=False)
        
    print(f"Demo dataset entry saved to: {demo_file}")
    print(f"\nThis shows the structure for training AI to make character decisions like real players!")
    print(f"With LLM API keys, this generates rich narrative reasoning for each decision.")

if __name__ == "__main__":
    asyncio.run(demo_character_generation())