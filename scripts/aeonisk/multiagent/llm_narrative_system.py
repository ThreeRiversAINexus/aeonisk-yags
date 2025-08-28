#!/usr/bin/env python3
"""
LLM-Driven Aeonisk YAGS Multi-Agent System

Uses actual LLMs to generate character reasoning, narrative descriptions,
and story progression for truly dynamic storytelling.
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

# Import the vectorstore system we built
from vectorstore_system import AeoniskVectorStore, FAMILY_LINES, GIVEN_NAMES

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import aiohttp
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


@dataclass
class PersonalityProfile:
    """Character personality that drives LLM reasoning."""
    risk_tolerance: int = 5  # 1-10
    void_curiosity: int = 3  # 1-10  
    authority_respect: int = 5  # 1-10
    family_loyalty: int = 7  # 1-10
    pragmatism: int = 5  # 1-10
    social_preference: int = 5  # 1-10
    innovation_drive: int = 5  # 1-10


@dataclass
class AeoniskCharacter:
    """Character for LLM-driven gameplay."""
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
    
    # Aeonisk specifics
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


class LLMNarrativeEngine:
    """Handles all LLM interactions for narrative generation with multiple providers."""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        
        # Initialize OpenAI if available
        if OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY'):
            self.providers['openai'] = {
                'client': openai.OpenAI(),
                'models': ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo']
            }
            print("✅ OpenAI provider initialized")
        
        # Initialize Anthropic if available
        if ANTHROPIC_AVAILABLE and os.getenv('ANTHROPIC_API_KEY'):
            self.providers['anthropic'] = {
                'api_key': os.getenv('ANTHROPIC_API_KEY'),
                'models': ['claude-3-haiku-20240307', 'claude-3-sonnet-20240229', 'claude-3-5-sonnet-20241022']
            }
            print("✅ Anthropic provider initialized")
        
        # Set active provider
        if 'anthropic' in self.providers:
            self.active_provider = 'anthropic'
            print("🎯 Using Anthropic Claude as primary provider")
        elif 'openai' in self.providers:
            self.active_provider = 'openai'
            print("🎯 Using OpenAI as primary provider")
        else:
            print("⚠️  No LLM providers available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY")
            
        self.available = len(self.providers) > 0
    
    async def _call_llm(self, prompt: str, max_tokens: int = 150, temperature: float = 0.8) -> str:
        """Make LLM call with fallback between providers."""
        
        if not self.available:
            return "LLM not available for generation."
        
        if self.active_provider == 'anthropic':
            return await self._call_anthropic(prompt, max_tokens, temperature)
        elif self.active_provider == 'openai':
            return await self._call_openai(prompt, max_tokens, temperature)
        else:
            return "No active LLM provider."
    
    async def _call_anthropic(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call Anthropic Claude API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.providers["anthropic"]["api_key"]}',
                'Content-Type': 'application/json',
                'x-api-key': self.providers["anthropic"]["api_key"],
                'anthropic-version': '2023-06-01'
            }
            
            data = {
                'model': 'claude-3-haiku-20240307',
                'messages': [{"role": "user", "content": prompt}],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post('https://api.anthropic.com/v1/messages', headers=headers, json=data) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        return response_data['content'][0]['text'].strip()
                    else:
                        error_text = await response.text()
                        print(f"Anthropic API error: {error_text}")
                        return "Claude API error."
                        
        except Exception as e:
            print(f"Anthropic error: {e}")
            return "Claude generation failed."
    
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
            return "OpenAI generation failed."

    async def generate_character_reasoning(
        self, 
        character: AeoniskCharacter, 
        scenario: Dict[str, Any], 
        chosen_action: str,
        available_actions: List[str],
        relevant_rules: List[Dict[str, Any]]
    ) -> str:
        """Generate character's reasoning using LLM."""
        
        personality_desc = f"Risk Tolerance {character.personality.risk_tolerance}/10, Void Curiosity {character.personality.void_curiosity}/10, Family Loyalty {character.personality.family_loyalty}/10"
        
        rule_context = ""
        if relevant_rules:
            rule_context = "\n\nRelevant game rules:\n" + "\n".join([
                f"- {rule['section']}: {rule['content'][:150]}..."
                for rule in relevant_rules[:2]
            ])
        
        prompt = f"""You are {character.full_name}, member of the {character.family_line} family line within {character.origin_faction}.

BACKGROUND:
- Family reputation: {character.family_reputation}
- Personal motivation: {character.personal_motivation}
- Personality: {personality_desc}
- Void score: {character.void_score}/10, Soulcredit: {character.soulcredit}

SITUATION:
{scenario['description']}
Location: {scenario['location']}
Void influence: {scenario['void_influence']}/10

AVAILABLE ACTIONS:
{chr(10).join([f"• {action}" for action in available_actions])}

YOU CHOSE: {chosen_action}

{rule_context}

Write 2-3 sentences in first person explaining WHY you chose this action. Show your character's voice, personality, family background, and tactical thinking. Be specific and personal - not generic. Sound like a real person with real concerns and expertise.

Reasoning:"""

        response = await self._call_llm(prompt, max_tokens=200, temperature=0.9)
        
        # Clean up response
        response = re.sub(r'^(Reasoning:|My reasoning:|I choose because)', '', response).strip()
        return response if response else f"My {character.family_line} training guides this choice."
    
    async def generate_action_outcome(
        self,
        character: AeoniskCharacter,
        action: str,
        roll_result: Dict[str, Any],
        scenario: Dict[str, Any]
    ) -> str:
        """Generate narrative description of action outcome using LLM."""
        
        prompt = f"""You are the Game Master narrating an Aeonisk YAGS tabletop RPG session.

CHARACTER: {character.full_name} ({character.family_line} of {character.origin_faction})
ACTION: {action}
LOCATION: {scenario['location']}

DICE RESULT:
- Roll Total: {roll_result['roll_total']} vs Difficulty {roll_result['difficulty']}
- Success Margin: {roll_result['margin']} ({'SUCCESS' if roll_result['margin'] >= 0 else 'FAILURE'})
- Story Impact: {roll_result['story_impact']}

Write a cinematic 1-2 sentence description of exactly what happens when {character.given_name} attempts this action. Focus on:
- Specific sensory details (what they see, hear, feel)
- How their family background/expertise shows in the attempt
- The immediate consequences of success/failure
- Aeonisk setting flavor (void energy, astral tech, faction politics)

Be vivid and specific, not generic. Show don't tell.

Outcome:"""

        response = await self._call_llm(prompt, max_tokens=150, temperature=0.9)
        return response if response else f"{character.given_name}'s action {'succeeds' if roll_result['success'] else 'fails'}."
    
    async def generate_scenario_evolution(
        self,
        scenario: Dict[str, Any],
        turn_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate how the scenario evolves using LLM."""
        
        # Build action summary
        action_summary = []
        for result in turn_results:
            char_name = result['character']
            action = result['action']
            outcome = result['mechanics']['story_impact']
            narrative = result['outcome_narrative']
            action_summary.append(f"- {char_name}: {action}\n  Result: {narrative} ({outcome})")
        
        prompt = f"""You are the AI Game Master for an Aeonisk YAGS session. The scenario must evolve based on what the characters accomplished this turn.

CURRENT SCENARIO:
Title: {scenario['title']}
Description: {scenario['description']}
Location: {scenario['location']}
Void influence: {scenario['void_influence']}/10

CHARACTER ACTIONS THIS TURN:
{chr(10).join(action_summary)}

Based on these specific outcomes, evolve the scenario for next turn. Show realistic consequences - successes should create new opportunities or reduce danger, failures should escalate problems or create complications.

Format your response as:
Title: [evolved scenario name reflecting the changes]
Description: [2-3 sentences showing how the situation has specifically changed based on character actions]
Void: [new level 1-10, adjusted based on actions and outcomes]

Be specific about cause and effect. Reference what actually happened."""

        response = await self._call_llm(prompt, max_tokens=250, temperature=0.7)
        
        # Parse response
        new_scenario = scenario.copy()
        
        try:
            if "Title:" in response:
                title_match = re.search(r'Title:\s*(.+)', response)
                if title_match:
                    new_scenario['title'] = title_match.group(1).strip()
            
            if "Description:" in response:
                desc_match = re.search(r'Description:\s*(.+?)(?=\nVoid:|$)', response, re.DOTALL)
                if desc_match:
                    new_scenario['description'] = desc_match.group(1).strip()
            
            if "Void:" in response:
                void_match = re.search(r'Void:\s*(\d+)', response)
                if void_match:
                    new_scenario['void_influence'] = int(void_match.group(1))
        except:
            # Fallback if parsing fails
            pass
            
        return new_scenario


class LLMGameSession:
    """Multi-turn game session with full LLM narrative generation."""
    
    def __init__(self, vectorstore: AeoniskVectorStore, llm_engine: LLMNarrativeEngine):
        self.vectorstore = vectorstore
        self.llm = llm_engine
        self.session_id = f"llm_session_{int(asyncio.get_event_loop().time())}"
        self.turn_number = 0
        self.story_history = []
        self.characters = []
        self.current_scenario = None
    
    async def initialize_session(self, num_players: int = 3):
        """Initialize with diverse characters and opening scenario."""
        print(f"🎲 Initializing LLM-Driven Session {self.session_id}")
        
        # Generate diverse characters
        factions = list(FAMILY_LINES.keys())
        
        for i in range(num_players):
            faction = random.choice(factions)
            family_line = random.choice(list(FAMILY_LINES[faction].keys()))
            character = self._generate_character(faction, family_line)
            self.characters.append(character)
            
            print(f"📋 {character.full_name} ({character.family_line} of {character.origin_faction})")
            print(f"   Motivation: {character.personal_motivation}")
            print(f"   Personality: Risk {character.personality.risk_tolerance}/10, Void Curiosity {character.personality.void_curiosity}/10")
        
        # Generate opening scenario
        self.current_scenario = await self._generate_opening_scenario()
        print(f"\n🌟 Opening: {self.current_scenario['title']}")
        print(f"📍 {self.current_scenario['location']}")
        
    def _generate_character(self, faction: str, family_line: str) -> AeoniskCharacter:
        """Generate character with dynamic personality."""
        personality = PersonalityProfile(
            risk_tolerance=random.randint(1, 10),
            void_curiosity=random.randint(1, 10),
            authority_respect=random.randint(1, 10),
            family_loyalty=random.randint(1, 10),
            pragmatism=random.randint(1, 10),
            social_preference=random.randint(1, 10),
            innovation_drive=random.randint(1, 10)
        )
        
        given_name = random.choice(GIVEN_NAMES)
        line_data = FAMILY_LINES[faction][family_line]
        
        # Generate varied motivations
        motivations = {
            'rising': ['Prove family worthiness', 'Seize new opportunities', 'Build lasting legacy', 'Expand family influence'],
            'stable': ['Maintain family honor', 'Serve faction interests', 'Protect traditions', 'Uphold family values'],
            'declining': ['Restore family reputation', 'Uncover family secrets', 'Break from past shame', 'Forge new path'],
            'disgraced': ['Redeem family name', 'Challenge the system', 'Forge new identity', 'Prove others wrong'],
            'mysterious': ['Fulfill hidden agenda', 'Protect ancient secrets', 'Gather intelligence', 'Maintain the balance']
        }
        
        return AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=f"{given_name} {family_line}",
            origin_faction=faction,
            family_reputation=line_data['reputation'],
            personal_motivation=random.choice(motivations.get(line_data['reputation'], motivations['stable'])),
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
            
            # Generate skills based on family specialty
            astral_arts=random.randint(0, 4) if 'ritual' in line_data['specialty'] else random.randint(0, 2),
            hacking=random.randint(2, 5) if faction == 'Tempest Industries' else random.randint(0, 2),
            corporate_influence=random.randint(2, 5) if faction == 'Astral Commerce Group' else random.randint(0, 2),
            
            void_score=random.randint(0, 2) if 'void' in line_data['specialty'] else 0,
            soulcredit=random.randint(-1, 3) if faction != 'Freeborn' else random.randint(-2, 1)
        )
    
    async def _generate_opening_scenario(self) -> Dict[str, Any]:
        """Generate opening scenario with LLM assistance."""
        
        if not self.llm.available:
            # Fallback scenario
            return {
                'title': 'Void Corruption Investigation',
                'description': 'Strange void energies are disrupting the local area, affecting both technology and spiritual connections.',
                'location': 'Corporate District, Aeonisk Prime',
                'void_influence': random.randint(3, 7),
                'faction_tensions': ['Multiple factions investigating', 'Competing interests'],
                'key_elements': ['void anomalies', 'tech malfunctions', 'spiritual disruption']
            }
        
        # Use LLM to generate richer scenario
        characters_desc = ", ".join([f"{c.family_line} of {c.origin_faction}" for c in self.characters])
        
        prompt = f"""Create an opening scenario for an Aeonisk YAGS tabletop RPG session.

Player characters present:
{characters_desc}

Generate a scenario that:
- Involves multiple factions or family lines
- Has clear stakes and consequences  
- Incorporates void mechanics (corruption/spiritual elements)
- Gives each character type something meaningful to contribute
- Creates opportunities for both cooperation and conflict

Format:
Title: [compelling scenario name]
Location: [specific Aeonisk location]
Description: [2-3 sentences describing the situation and immediate challenge]
Void Influence: [number 1-10]
Key Elements: [3 important scenario features]"""

        try:
            response = self.llm.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.8
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse the LLM response
            scenario = {
                'title': 'Generated Scenario',
                'description': 'An interesting situation unfolds.',
                'location': 'Unknown Location',
                'void_influence': 5,
                'key_elements': ['mystery', 'danger', 'opportunity']
            }
            
            # Extract structured data
            for line in content.split('\n'):
                if line.startswith('Title:'):
                    scenario['title'] = line.replace('Title:', '').strip()
                elif line.startswith('Location:'):
                    scenario['location'] = line.replace('Location:', '').strip()
                elif line.startswith('Description:'):
                    scenario['description'] = line.replace('Description:', '').strip()
                elif line.startswith('Void Influence:'):
                    void_match = re.search(r'(\d+)', line)
                    if void_match:
                        scenario['void_influence'] = int(void_match.group(1))
                elif line.startswith('Key Elements:'):
                    elements = line.replace('Key Elements:', '').strip()
                    scenario['key_elements'] = [e.strip() for e in elements.split(',')][:3]
            
            return scenario
            
        except Exception as e:
            print(f"LLM error in scenario generation: {e}")
            return {
                'title': 'Void Corruption Investigation',
                'description': 'Strange energies disrupt the area.',
                'location': 'Corporate District',
                'void_influence': 5,
                'key_elements': ['void anomalies', 'investigation', 'danger']
            }
    
    async def play_turn(self) -> Dict[str, Any]:
        """Execute one turn with full LLM narrative generation."""
        self.turn_number += 1
        
        print(f"\n🎯 === Turn {self.turn_number}: {self.current_scenario['title']} ===")
        print(f"📍 {self.current_scenario['location']}")
        print(f"🌀 Void Influence: {self.current_scenario['void_influence']}/10")
        print(f"📜 {self.current_scenario['description']}")
        
        turn_results = []
        
        for character in self.characters:
            print(f"\n🎭 {character.full_name}'s Turn:")
            
            # Generate contextual actions
            available_actions = await self._generate_contextual_actions(character)
            
            # Character chooses action (personality-based)
            chosen_action = self._choose_action_by_personality(character, available_actions)
            
            # Get relevant rules from vectorstore
            relevant_rules = await self.vectorstore.query_rules(
                f"{chosen_action} {character.family_line} {self.current_scenario['title']}", 
                n_results=2
            )
            
            # Generate LLM reasoning
            reasoning = await self.llm.generate_character_reasoning(
                character, self.current_scenario, chosen_action, available_actions, relevant_rules
            )
            
            # Execute action with dice mechanics
            action_result = await self._execute_action_with_mechanics(character, chosen_action)
            
            # Generate LLM outcome narrative
            outcome_narrative = await self.llm.generate_action_outcome(
                character, chosen_action, action_result, self.current_scenario
            )
            
            print(f"   💭 {reasoning}")
            print(f"   🎲 {outcome_narrative}")
            print(f"   📊 Roll: {action_result['roll_total']} vs {action_result['difficulty']} (margin: {action_result['margin']})")
            
            turn_results.append({
                'character': character.full_name,
                'action': chosen_action,
                'reasoning': reasoning,
                'outcome_narrative': outcome_narrative,
                'mechanics': action_result,
                'supporting_rules': relevant_rules
            })
        
        # Evolve scenario with LLM
        self.current_scenario = await self.llm.generate_scenario_evolution(
            self.current_scenario, turn_results
        )
        
        # Add to story history
        turn_story = {
            'turn': self.turn_number,
            'scenario_state': self.current_scenario.copy(),
            'character_actions': turn_results
        }
        self.story_history.append(turn_story)
        
        return turn_story
    
    async def _generate_contextual_actions(self, character: AeoniskCharacter) -> List[str]:
        """Generate actions relevant to character and scenario."""
        
        # Query vectorstore for action inspiration
        action_rules = await self.vectorstore.query_rules(
            f"{self.current_scenario['title']} player actions {character.family_line}", 
            n_results=3
        )
        
        # Base action templates that get contextualized
        base_actions = [
            f"Investigate using {character.family_line} family expertise",
            f"Attempt to stabilize the situation with available resources",
            f"Seek cooperation with other factions present",
            f"Use stealth and observation to gather intelligence",
            f"Leverage {character.origin_faction} connections for support"
        ]
        
        # Add skill-specific actions
        if character.astral_arts >= 3:
            base_actions.append("Perform ritual intervention to address spiritual aspects")
        if character.hacking >= 3:
            base_actions.append("Hack relevant systems to access restricted information")
        if character.corporate_influence >= 3:
            base_actions.append("Use corporate channels to mobilize official response")
        
        return random.sample(base_actions, min(6, len(base_actions)))
    
    def _choose_action_by_personality(self, character: AeoniskCharacter, actions: List[str]) -> str:
        """Choose action based on character personality preferences."""
        
        action_scores = []
        
        for action in actions:
            score = 5  # base
            action_lower = action.lower()
            
            # Personality influences
            if 'investigate' in action_lower:
                score += (character.personality.pragmatism - 5)
            if 'ritual' in action_lower:
                score += (character.personality.void_curiosity - 5)
            if 'stealth' in action_lower:
                score += (10 - character.personality.social_preference - 5)
            if 'cooperation' in action_lower or 'seek' in action_lower:
                score += (character.personality.social_preference - 5)
            if 'leverage' in action_lower or 'corporate' in action_lower:
                score += (character.personality.authority_respect - 5)
            
            action_scores.append((action, max(1, score)))
        
        # Weighted random selection
        total_weight = sum(score for _, score in action_scores)
        roll = random.uniform(0, total_weight)
        
        current = 0
        for action, weight in action_scores:
            current += weight
            if roll <= current:
                return action
        
        return random.choice(actions)  # fallback
    
    async def _execute_action_with_mechanics(self, character: AeoniskCharacter, action: str) -> Dict[str, Any]:
        """Execute action with proper YAGS mechanics."""
        
        # Determine skill and attribute based on action
        skill_mapping = {
            'investigate': ('intelligence', 'awareness'),
            'ritual': ('willpower', 'astral_arts'),
            'stealth': ('agility', 'stealth'),
            'corporate': ('empathy', 'corporate_influence'),
            'hack': ('intelligence', 'hacking'),
            'cooperation': ('empathy', 'charm')
        }
        
        primary_attr, primary_skill = 'intelligence', 'awareness'  # default
        for keyword, (attr, skill) in skill_mapping.items():
            if keyword in action.lower():
                primary_attr, primary_skill = attr, skill
                break
        
        # YAGS mechanics: Attribute × Skill + d20
        attr_value = getattr(character, primary_attr, 3)
        skill_value = getattr(character, primary_skill, 2)
        roll = random.randint(1, 20)
        total = attr_value * skill_value + roll
        
        # Dynamic difficulty based on scenario
        base_difficulty = 12 + self.current_scenario['void_influence'] + random.randint(0, 6)
        
        success = total >= base_difficulty
        margin = total - base_difficulty
        
        # Determine story impact
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
            'skill_used': f"{primary_attr} × {primary_skill}",
            'attribute_value': attr_value,
            'skill_value': skill_value,
            'die_roll': roll
        }
    
    async def generate_dataset_entry(self) -> Dict[str, Any]:
        """Generate rich dataset entry with full LLM narrative."""
        
        return {
            'session_id': self.session_id,
            'session_type': 'llm_generated_narrative',
            'total_turns': self.turn_number,
            'domain': {
                'core': 'multi_turn_collaborative_gameplay',
                'subdomain': 'llm_driven_character_decisions'
            },
            'characters': [
                {
                    'name': char.full_name,
                    'faction': char.origin_faction,
                    'family_line': char.family_line,
                    'motivation': char.personal_motivation,
                    'personality': {
                        'risk_tolerance': char.personality.risk_tolerance,
                        'void_curiosity': char.personality.void_curiosity,
                        'family_loyalty': char.personality.family_loyalty,
                        'social_preference': char.personality.social_preference
                    },
                    'stats': {
                        'willpower': char.willpower,
                        'intelligence': char.intelligence,
                        'empathy': char.empathy,
                        'void_score': char.void_score,
                        'soulcredit': char.soulcredit
                    },
                    'key_skills': {
                        'astral_arts': char.astral_arts,
                        'hacking': char.hacking,
                        'corporate_influence': char.corporate_influence
                    }
                }
                for char in self.characters
            ],
            'narrative_progression': self.story_history,
            'llm_generation_info': {
                'reasoning_method': 'openai_gpt4o_mini',
                'narrative_style': 'character_voice_driven',
                'rule_integration': 'vectorstore_semantic_search',
                'total_rule_chunks_available': 382
            },
            'training_focus': {
                'llm_character_reasoning': 'AI-generated first-person decision explanations',
                'collaborative_problem_solving': 'Multi-character approaches to shared challenges',
                'rule_grounded_decisions': 'Choices informed by actual game mechanics',
                'personality_consistency': 'Character voice maintained across multiple turns',
                'emergent_storytelling': 'Narrative develops organically from character choices'
            }
        }


async def main():
    """Run the LLM-driven Aeonisk MUD system."""
    
    print("🚀 LLM-Driven Aeonisk YAGS Multi-Agent System")
    print("Your Personal MUD with AI-Generated Narrative\n")
    
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("💡 Set OPENAI_API_KEY environment variable for full LLM narrative generation")
        print("   Running with fallback generation for now...\n")
    
    # Initialize systems
    vectorstore = AeoniskVectorStore()
    
    # Only populate if needed (check if we have data)
    try:
        test_query = await vectorstore.query_rules("attribute skill", n_results=1)
        if not test_query:
            print("📚 Loading YAGS/Aeonisk rules into vectorstore...")
            await vectorstore.populate_vectorstore()
    except:
        print("📚 Loading YAGS/Aeonisk rules into vectorstore...")
        await vectorstore.populate_vectorstore()
    
    llm_engine = LLMNarrativeEngine()
    session = LLMGameSession(vectorstore, llm_engine)
    
    # Initialize and play session
    await session.initialize_session(num_players=3)
    
    # Play multiple turns
    for turn in range(4):  # Longer session for richer story
        await session.play_turn()
        await asyncio.sleep(0.5)  # Brief pause for readability
    
    # Generate final dataset
    print(f"\n📊 Generating Rich Training Dataset...")
    dataset = await session.generate_dataset_entry()
    
    # Save with timestamp
    import time
    timestamp = int(time.time())
    dataset_file = f"./llm_mud_session_{timestamp}.yaml"
    
    with open(dataset_file, 'w') as f:
        f.write("# LLM-Generated Aeonisk YAGS Multi-Agent Session\n")
        f.write("# Rich narrative reasoning and character development\n\n")
        yaml.dump(dataset, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Complete LLM-driven session saved to: {dataset_file}")
    print(f"\n🎮 Your Personal Aeonisk MUD Session Complete!")
    print(f"   • {len(session.characters)} AI characters with unique personalities")
    print(f"   • {session.turn_number} turns of evolving narrative") 
    print(f"   • Rule-grounded decisions using {382} game rule chunks")
    print(f"   • LLM-generated character reasoning and outcomes")


if __name__ == "__main__":
    asyncio.run(main())