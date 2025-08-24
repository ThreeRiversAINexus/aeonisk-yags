"""
Player-Perspective Aeonisk YAGS LLM Training System

Generates dataset entries from the PLAYER'S perspective - learning to make character
decisions, choose actions, and provide reasoning like a real player would.
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

openai.api_key = os.getenv('OPENAI_API_KEY')

@dataclass
class AeoniskCharacter:
    """Rich Aeonisk character with proper family lineage and faction depth."""
    given_name: str
    family_line: str
    full_name: str
    origin_faction: str
    
    # YAGS Attributes (2-5 range, 3 average)
    strength: int = 3
    health: int = 3
    agility: int = 3
    dexterity: int = 3
    perception: int = 3
    intelligence: int = 3
    empathy: int = 3
    willpower: int = 3
    
    # Core Aeonisk mechanics
    void_score: int = 0
    soulcredit: int = 0
    bonds: List[str] = None
    true_will: str = ""
    birth_method: str = "biocreche_pod"
    
    # Skills
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
    
    # Equipment and background
    primary_ritual_item: str = ""
    faction_standing: str = "member"  # member, initiate, trusted, inner_circle
    family_reputation: str = "stable"  # rising, stable, declining, disgraced
    personal_motivation: str = ""
    
    def __post_init__(self):
        if self.bonds is None:
            self.bonds = []


class AeoniskWorldBuilder:
    """Builds rich, lore-accurate Aeonisk characters and scenarios."""
    
    # Actual family lines from the lore
    FAMILY_LINES = {
        'Sovereign Nexus': {
            'Elaras': {'reputation': 'rising', 'specialty': 'harmony_rituals', 'notable': 'spiritual_guidance'},
            'Halessan': {'reputation': 'stable', 'specialty': 'civic_duty', 'notable': 'bureaucratic_excellence'},
            'Ireveth': {'reputation': 'stable', 'specialty': 'enforcement', 'notable': 'order_maintenance'},
            'Unified Hand': {'reputation': 'mysterious', 'specialty': 'observation', 'notable': 'intelligence_gathering'}
        },
        'Astral Commerce Group': {
            'Kythea': {'reputation': 'rising', 'specialty': 'futures_trading', 'notable': 'risk_assessment'},
            'Exchange': {'reputation': 'stable', 'specialty': 'contract_law', 'notable': 'negotiation'},
            'Ledger-Kaine': {'reputation': 'declining', 'specialty': 'audit_enforcement', 'notable': 'debt_collection'}
        },
        'Tempest Industries': {
            'Karsel': {'reputation': 'disgraced', 'specialty': 'void_research', 'notable': 'reality_manipulation'},
            'Dissolution': {'reputation': 'rising', 'specialty': 'chaos_theory', 'notable': 'system_disruption'},
            'Liberty-Void': {'reputation': 'stable', 'specialty': 'liberation_tech', 'notable': 'anti_authority'}
        },
        'Arcane Genetics': {
            'Vireya': {'reputation': 'stable', 'specialty': 'bio_enhancement', 'notable': 'genetic_artistry'},
            'Catalyst': {'reputation': 'rising', 'specialty': 'mutation_control', 'notable': 'adaptation_protocols'},
            'Evolution': {'reputation': 'stable', 'specialty': 'species_development', 'notable': 'long_term_planning'}
        },
        'Aether Dynamics': {
            'Resonance': {'reputation': 'stable', 'specialty': 'ley_navigation', 'notable': 'astral_sensitivity'},
            'Current': {'reputation': 'rising', 'specialty': 'energy_flow', 'notable': 'power_distribution'},
            'Wavelength': {'reputation': 'stable', 'specialty': 'harmonic_analysis', 'notable': 'pattern_recognition'}
        },
        'Freeborn': {
            'Unbound': {'reputation': 'variable', 'specialty': 'independence', 'notable': 'authority_resistance'},
            'Wild-Current': {'reputation': 'variable', 'specialty': 'natural_harmony', 'notable': 'ecosystem_bonding'},
            'Free-Sky': {'reputation': 'variable', 'specialty': 'exploration', 'notable': 'boundary_crossing'}
        }
    }
    
    # Rich given names that fit the lore
    GIVEN_NAMES = {
        'traditional': ['Irele', 'Wren', 'Varis', 'Liora', 'Nyx', 'Olen', 'Kaelen'],
        'concept_names': ['Echo', 'Resonance', 'Harmony', 'Void', 'Storm', 'Catalyst', 'Unity'],
        'modern': ['Zara', 'Aurora', 'Gene', 'Credit', 'Spark', 'Current', 'Drift', 'Pulse']
    }
    
    @classmethod
    def generate_character(cls, faction: str = None, family_line: str = None) -> AeoniskCharacter:
        """Generate a richly detailed Aeonisk character."""
        
        if not faction:
            faction = random.choice(list(cls.FAMILY_LINES.keys()))
            
        if not family_line:
            family_line = random.choice(list(cls.FAMILY_LINES[faction].keys()))
            
        line_data = cls.FAMILY_LINES[faction][family_line]
        
        # Choose name style based on family line
        if line_data['reputation'] == 'rising':
            name_pool = cls.GIVEN_NAMES['modern'] + cls.GIVEN_NAMES['concept_names']
        elif line_data['reputation'] == 'disgraced':
            name_pool = cls.GIVEN_NAMES['concept_names']  # More unconventional
        else:
            name_pool = cls.GIVEN_NAMES['traditional'] + cls.GIVEN_NAMES['modern']
            
        given_name = random.choice(name_pool)
        full_name = f"{given_name} {family_line}"
        
        char = AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=full_name,
            origin_faction=faction,
            family_reputation=line_data['reputation']
        )
        
        # Generate attributes with some family line influence
        base_attrs = [random.randint(2, 5) for _ in range(8)]
        char.strength, char.health, char.agility, char.dexterity = base_attrs[:4]
        char.perception, char.intelligence, char.empathy, char.willpower = base_attrs[4:]
        
        # Family line specialization bonuses
        specialty = line_data['specialty']
        if 'ritual' in specialty:
            char.willpower = min(5, char.willpower + 1)
            char.astral_arts = random.randint(3, 6)
        elif 'enforcement' in specialty or 'tactical' in specialty:
            char.perception = min(5, char.perception + 1)
            char.awareness = random.randint(3, 5)
        elif 'trading' in specialty or 'contract' in specialty:
            char.empathy = min(5, char.empathy + 1)
            char.corporate_influence = random.randint(3, 6)
            char.guile = random.randint(3, 5)
        elif 'void' in specialty or 'chaos' in specialty:
            char.willpower = min(5, char.willpower + 1)
            char.void_score = random.randint(1, 3)
            char.astral_arts = random.randint(2, 5)
        elif 'bio' in specialty or 'genetic' in specialty:
            char.intelligence = min(5, char.intelligence + 1)
            char.magick_theory = random.randint(2, 4)
            
        # Faction-wide traits
        if faction == 'Sovereign Nexus':
            char.soulcredit = random.randint(0, 3)
            char.intimacy_ritual = random.randint(1, 3)
        elif faction == 'Astral Commerce Group':
            char.soulcredit = random.randint(1, 5)
            char.debt_law = random.randint(2, 4)
        elif faction == 'Tempest Industries':
            char.hacking = random.randint(2, 5)
            char.stealth = random.randint(2, 4)
        elif faction == 'Freeborn':
            char.birth_method = 'natural'
            char.athletics = random.randint(3, 6)
            char.soulcredit = random.randint(-2, 1)
            
        # Generate personal motivation based on family status
        motivations = {
            'rising': ['Prove family worthiness', 'Seize new opportunities', 'Build lasting legacy'],
            'stable': ['Maintain family honor', 'Serve faction interests', 'Protect traditions'],
            'declining': ['Restore family reputation', 'Uncover family secrets', 'Break from past shame'],
            'disgraced': ['Redeem family name', 'Forge new identity', 'Challenge the system'],
            'mysterious': ['Fulfill hidden agenda', 'Gather crucial intelligence', 'Serve greater purpose']
        }
        
        char.personal_motivation = random.choice(motivations.get(line_data['reputation'], motivations['stable']))
        
        # Generate ritual item based on family line
        ritual_items = {
            'Elaras': ['Harmony Crystal', 'Unity Sigil', 'Resonance Bell'],
            'Halessan': ['Civic Seal', 'Authority Rod', 'Order Stone'],
            'Karsel': ['Void Shard', 'Chaos Fragment', 'Reality Lens'],
            'Vireya': ['Gene Helix', 'Bio Matrix', 'Evolution Seed'],
            'Unbound': ['Freedom Stone', 'Wild Focus', 'Liberation Crystal']
        }
        
        char.primary_ritual_item = random.choice(ritual_items.get(family_line, ['Ancient Focus', 'Family Heirloom', 'Personal Talisman']))
        
        return char
    
    @classmethod
    def generate_scenario_situation(cls) -> Dict[str, Any]:\n        \"\"\"Generate a rich scenario situation with faction dynamics.\"\"\"\n        \n        situations = [\n            {\n                'title': 'Memory Theft at Biocreche Facility',\n                'location': 'Abandoned Biocreche Pod Complex, Arcadia',\n                'description': 'Corporate agents are stealing memories from gestating Echo Children, threatening to destabilize multiple family lineages.',\n                'faction_tensions': ['Arcane Genetics vs Astral Commerce Group', 'Sovereign Nexus intervention'],\n                'void_influence': random.randint(2, 5),\n                'key_elements': ['corrupted pod matrices', 'stolen memory fragments', 'Echo Children witnesses']\n            },\n            {\n                'title': 'Ley Line Convergence Disruption',\n                'location': 'Primary Ley Nexus, Aeonisk Prime',\n                'description': 'Ancient ley lines are being artificially destabilized, causing reality fluctuations across the homeworld.',\n                'faction_tensions': ['Tempest Industries suspected', 'Aether Dynamics investigating'],\n                'void_influence': random.randint(3, 7),\n                'key_elements': ['unstable astral currents', 'malfunctioning tech', 'temporal anomalies']\n            },\n            {\n                'title': 'Bond Betrayal Investigation',\n                'location': 'Resonance Commune Sanctuary, Nimbus',\n                'description': 'A sacred bonding ritual was sabotaged, severing dozens of spiritual connections and leaving participants void-touched.',\n                'faction_tensions': ['Internal Commune strife', 'External faction manipulation'],\n                'void_influence': random.randint(1, 4),\n                'key_elements': ['severed bonds', 'traumatized participants', 'ritual sabotage evidence']\n            }\n        ]\n        \n        return random.choice(situations)\n\n\nclass PlayerPerspectiveLLM:\n    \"\"\"Uses LLM to generate player-perspective decision making and reasoning.\"\"\"\n    \n    def __init__(self, model: str = \"gpt-4\"):\n        self.model = model\n        \n    async def generate_player_decision(self, character: AeoniskCharacter, \n                                     situation: Dict[str, Any],\n                                     available_actions: List[str]) -> Dict[str, Any]:\n        \"\"\"Generate a player's decision-making process and action choice.\"\"\"\n        \n        family_context = f\"\"\"\nFamily Line: {character.family_line} Line of {character.origin_faction}\nReputation: {character.family_reputation}\nSpecialty: Known for {character.origin_faction} values\nPersonal Drive: {character.personal_motivation}\nCurrent Standing: Void {character.void_score}/10, Soulcredit {character.soulcredit}\nRitual Focus: {character.primary_ritual_item}\n\"\"\"\n        \n        prompt = f\"\"\"You are playing {character.full_name}, a member of the {character.family_line} Line from {character.origin_faction}. \n\n{family_context}\n\nSituation: {situation['description']}\nLocation: {situation['location']}\nTensions: {', '.join(situation['faction_tensions'])}\nVoid Influence: {situation['void_influence']}/10 (affecting technology and rituals)\n\nAvailable Actions:\n{chr(10).join(f'- {action}' for action in available_actions)}\n\nAs this character, considering your family's reputation, faction loyalties, and personal motivations:\n\n1. What would you choose to do and why?\n2. How does your family line's specialty influence this decision?\n3. What are the risks you're willing to accept?\n4. How does this serve your personal motivation?\n\nRespond as the player making this decision, with your reasoning.\n\nReturn JSON with:\n- chosen_action: (your choice from the available actions)\n- primary_reasoning: (why this action fits your character)\n- family_influence: (how your family line affects this choice)\n- risk_assessment: (what you're risking and why it's worth it)\n- expected_outcome: (what you hope to achieve)\n- backup_plan: (what if this goes wrong)\"\"\"\n\n        try:\n            response = await openai.ChatCompletion.acreate(\n                model=self.model,\n                messages=[{\"role\": \"user\", \"content\": prompt}],\n                temperature=0.8  # Higher for more personality variation\n            )\n            \n            return json.loads(response.choices[0].message.content)\n            \n        except Exception as e:\n            print(f\"LLM Error: {e}\")\n            # Fallback based on character traits\n            return {\n                'chosen_action': random.choice(available_actions),\n                'primary_reasoning': f\"As a {character.family_line}, I must act according to my line's traditions.\",\n                'family_influence': f\"The {character.family_line} way guides my choice.\",\n                'risk_assessment': \"Moderate risk, but necessary for family honor.\",\n                'expected_outcome': \"Hope to advance my personal goals while serving my faction.\",\n                'backup_plan': \"Adapt based on circumstances and family guidance.\"\n            }\n    \n    async def generate_skill_choice_reasoning(self, character: AeoniskCharacter, \n                                            action_description: str,\n                                            situation: Dict[str, Any]) -> Dict[str, Any]:\n        \"\"\"Generate the reasoning for which attribute/skill to use for an action.\"\"\"\n        \n        char_skills = {\n            'Athletics': character.athletics,\n            'Awareness': character.awareness, \n            'Brawl': character.brawl,\n            'Charm': character.charm,\n            'Guile': character.guile,\n            'Stealth': character.stealth,\n            'Astral Arts': character.astral_arts,\n            'Corporate Influence': character.corporate_influence,\n            'Hacking': character.hacking,\n            'Melee': character.melee\n        }\n        \n        char_attrs = {\n            'Strength': character.strength,\n            'Agility': character.agility,\n            'Perception': character.perception, \n            'Intelligence': character.intelligence,\n            'Empathy': character.empathy,\n            'Willpower': character.willpower\n        }\n        \n        prompt = f\"\"\"You are {character.full_name} attempting: {action_description}\n\nYour Attributes: {', '.join(f'{k} {v}' for k, v in char_attrs.items())}\nYour Skills: {', '.join(f'{k} {v}' for k, v in char_skills.items() if v > 0)}\n\nSituation: {situation['description']}\nVoid Level: {situation['void_influence']}/10\n\nAs an experienced Aeonisk YAGS player, explain:\n1. Which attribute best applies to this action?\n2. Which skill is most relevant?\n3. What's the likely difficulty (15-30 range)?\n4. How does the void influence affect this?\n5. What could go wrong vs. go right?\n\nReturn JSON with:\n- attribute_choice: (e.g., \"Intelligence\")\n- skill_choice: (e.g., \"Hacking\")\n- difficulty_estimate: (15-30)\n- reasoning: (why these choices make sense)\n- void_complications: (how void level affects this)\n- success_description: (what success looks like)\n- failure_consequences: (what failure means)\"\"\"\n\n        try:\n            response = await openai.ChatCompletion.acreate(\n                model=self.model,\n                messages=[{\"role\": \"user\", \"content\": prompt}],\n                temperature=0.3  # Lower for more consistent mechanical reasoning\n            )\n            \n            return json.loads(response.choices[0].message.content)\n            \n        except Exception as e:\n            print(f\"LLM Error: {e}\")\n            # Fallback reasoning\n            return {\n                'attribute_choice': 'Intelligence',\n                'skill_choice': 'Awareness',\n                'difficulty_estimate': 20,\n                'reasoning': 'This requires careful analysis and perception.',\n                'void_complications': 'Void energy may interfere with technology.',\n                'success_description': 'Objective achieved with minimal complications.',\n                'failure_consequences': 'Complications arise, possibly increasing void exposure.'\n            }\n\n\nclass PlayerPerspectiveDatasetGenerator:\n    \"\"\"Generates player-perspective training data for Aeonisk YAGS AI.\"\"\"\n    \n    def __init__(self):\n        self.llm = PlayerPerspectiveLLM()\n        self.world_builder = AeoniskWorldBuilder()\n        self.dataset_entries = []\n        \n    async def generate_player_decision_entry(self, character: AeoniskCharacter, \n                                           situation: Dict[str, Any]) -> Dict[str, Any]:\n        \"\"\"Generate a dataset entry focused on player decision-making.\"\"\"\n        \n        # Generate available actions for the situation\n        available_actions = [\n            \"Investigate the source of the disruption using family connections\",\n            \"Attempt a ritual to stabilize the situation\", \n            \"Negotiate with rival factions present\",\n            \"Gather intelligence through stealth observation\",\n            \"Directly confront the responsible parties\",\n            \"Seek alliance with other affected parties\",\n            \"Use corporate/family influence to access restricted areas\",\n            \"Perform reconnaissance to understand the full scope\"\n        ]\n        \n        # Get player decision via LLM\n        decision = await self.llm.generate_player_decision(character, situation, available_actions)\n        \n        # Get skill reasoning for the chosen action\n        skill_reasoning = await self.llm.generate_skill_choice_reasoning(\n            character, decision['chosen_action'], situation\n        )\n        \n        task_id = f\"AEONISK-PLAYER-{len(self.dataset_entries) + 1:03d}\"\n        \n        entry = {\n            'task_id': task_id,\n            'domain': {\n                'core': 'player_decision_making',\n                'subdomain': 'action_choice_reasoning'\n            },\n            'scenario': situation['description'],\n            'location': situation['location'],\n            'faction_context': f\"Tensions between {', '.join(situation['faction_tensions'])}\",\n            'void_influence': situation['void_influence'],\n            'character': {\n                'name': character.full_name,\n                'family_line': character.family_line,\n                'origin_faction': character.origin_faction,\n                'family_reputation': character.family_reputation,\n                'personal_motivation': character.personal_motivation,\n                'void_score': character.void_score,\n                'soulcredit': character.soulcredit,\n                'key_stats': {\n                    'willpower': character.willpower,\n                    'empathy': character.empathy,\n                    'intelligence': character.intelligence\n                },\n                'notable_skills': {\n                    skill: getattr(character, skill.lower().replace(' ', '_'))\n                    for skill in ['Astral Arts', 'Corporate Influence', 'Stealth', 'Awareness']\n                    if getattr(character, skill.lower().replace(' ', '_')) > 2\n                }\n            },\n            'available_actions': available_actions,\n            'player_decision': {\n                'chosen_action': decision['chosen_action'],\n                'reasoning': decision['primary_reasoning'],\n                'family_influence': decision['family_influence'],\n                'risk_assessment': decision['risk_assessment'],\n                'expected_outcome': decision['expected_outcome'],\n                'backup_plan': decision['backup_plan']\n            },\n            'mechanical_analysis': {\n                'attribute_used': skill_reasoning['attribute_choice'],\n                'skill_used': skill_reasoning['skill_choice'],\n                'estimated_difficulty': skill_reasoning['difficulty_estimate'],\n                'reasoning': skill_reasoning['reasoning'],\n                'void_complications': skill_reasoning['void_complications']\n            },\n            'expected_outcomes': {\n                'success_scenario': skill_reasoning['success_description'],\n                'failure_scenario': skill_reasoning['failure_consequences']\n            },\n            'training_focus': {\n                'family_line_behavior': f\"How {character.family_line} approaches challenges\",\n                'faction_loyalty': f\"Balancing {character.origin_faction} interests with personal goals\",\n                'void_risk_management': \"Managing void exposure in decision making\",\n                'social_consequences': \"Understanding political ramifications of actions\"\n            }\n        }\n        \n        return entry\n    \n    async def run_training_session(self, num_scenarios: int = 5):\n        \"\"\"Generate multiple training scenarios with diverse characters and situations.\"\"\"\n        \n        print(\"=== Aeonisk YAGS Player-Perspective Training Data Generation ===\")\n        print(f\"Generating {num_scenarios} rich scenario training entries\\n\")\n        \n        for i in range(num_scenarios):\n            print(f\"--- Scenario {i+1} ---\")\n            \n            # Generate character with diverse background\n            factions = list(self.world_builder.FAMILY_LINES.keys())\n            chosen_faction = factions[i % len(factions)]  # Rotate through factions\n            \n            character = self.world_builder.generate_character(chosen_faction)\n            situation = self.world_builder.generate_scenario_situation()\n            \n            print(f\"Character: {character.full_name} ({character.family_line} Line)\")\n            print(f\"Reputation: {character.family_reputation} family, {character.origin_faction}\")\n            print(f\"Motivation: {character.personal_motivation}\")\n            print(f\"Situation: {situation['title']}\")\n            print(f\"Location: {situation['location']}\")\n            \n            # Generate training entry\n            entry = await self.generate_player_decision_entry(character, situation)\n            self.dataset_entries.append(entry)\n            \n            print(f\"Decision: {entry['player_decision']['chosen_action']}\")\n            print(f\"Reasoning: {entry['player_decision']['reasoning'][:100]}...\")\n            print(f\"Skill Check: {entry['mechanical_analysis']['attribute_used']} × {entry['mechanical_analysis']['skill_used']}\")\n            print()\n            \n        # Save dataset\n        await self.save_dataset()\n        print(f\"Generated {len(self.dataset_entries)} training entries for player decision-making AI!\")\n        \n    async def save_dataset(self):\n        \"\"\"Save the player-perspective dataset.\"\"\"\n        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')\n        \n        # Save as YAML (standard dataset format)\n        yaml_file = Path(f'./player_perspective_dataset_{timestamp}.yaml')\n        with open(yaml_file, 'w') as f:\n            f.write(\"# Aeonisk YAGS Player-Perspective Training Dataset\\n\")\n            f.write(\"# Generated for training AI to make character decisions like human players\\n\\n\")\n            yaml.dump_all(self.dataset_entries, f, default_flow_style=False, sort_keys=False)\n            \n        print(f\"\\nPlayer-perspective dataset saved to: {yaml_file}\")\n        return yaml_file\n\n\nasync def main():\n    \"\"\"Generate player-perspective training data.\"\"\"\n    \n    if not os.getenv('OPENAI_API_KEY'):\n        print(\"Warning: No OPENAI_API_KEY found. Using fallback generation.\")\n    \n    generator = PlayerPerspectiveDatasetGenerator()\n    await generator.run_training_session(8)  # Generate diverse scenarios\n\n\nif __name__ == \"__main__\":\n    asyncio.run(main())