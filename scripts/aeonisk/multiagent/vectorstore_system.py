#!/usr/bin/env python3
"""
Aeonisk YAGS Vectorstore-Enhanced Multi-Agent System

Creates a self-playing MUD-like experience with rule-aware AI agents
that query a comprehensive vectorstore of YAGS and Aeonisk content.
"""

import asyncio
import json
import yaml
import random
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import chromadb
from chromadb.config import Settings


@dataclass
class RuleChunk:
    """A chunk of game rules or lore with metadata."""
    content: str
    source_file: str
    section: str
    rule_type: str  # 'mechanic', 'lore', 'equipment', 'skill', 'attribute'
    tags: List[str] = field(default_factory=list)


class AeoniskVectorStore:
    """ChromaDB-based vectorstore for all YAGS and Aeonisk content."""
    
    def __init__(self, persist_directory: str = "./vectorstore_data"):
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="aeonisk_yags_rules",
            metadata={"description": "Complete YAGS and Aeonisk game rules and lore"}
        )
    
    def chunk_markdown_content(self, file_path: str) -> List[RuleChunk]:
        """Parse markdown into meaningful rule chunks."""
        chunks = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by headers
        sections = re.split(r'\n(#{1,4})\s+(.+)', content)
        current_section = "Introduction"
        
        for i in range(0, len(sections), 3):
            if i + 2 < len(sections):
                header_level = sections[i + 1] if i + 1 < len(sections) else "#"
                section_title = sections[i + 2] if i + 2 < len(sections) else "Unknown"
                section_content = sections[i] if sections[i].strip() else sections[i + 3] if i + 3 < len(sections) else ""
                
                if len(section_content.strip()) > 50:  # Skip tiny sections
                    rule_type = self._classify_content(section_title, section_content)
                    tags = self._extract_tags(section_title, section_content)
                    
                    chunks.append(RuleChunk(
                        content=section_content.strip(),
                        source_file=Path(file_path).name,
                        section=section_title,
                        rule_type=rule_type,
                        tags=tags
                    ))
        
        return chunks
    
    def _classify_content(self, title: str, content: str) -> str:
        """Classify content type for better retrieval."""
        title_lower = title.lower()
        content_lower = content.lower()
        
        if any(word in title_lower for word in ['attribute', 'skill', 'roll', 'check', 'difficulty']):
            return 'mechanic'
        elif any(word in title_lower for word in ['equipment', 'gear', 'weapon', 'armor', 'item']):
            return 'equipment'
        elif any(word in title_lower for word in ['faction', 'family', 'history', 'world', 'culture']):
            return 'lore'
        elif any(word in content_lower for word in ['roll', 'difficulty', 'success', 'failure', 'bonus']):
            return 'mechanic'
        else:
            return 'general'
    
    def _extract_tags(self, title: str, content: str) -> List[str]:
        """Extract relevant tags for better search."""
        tags = []
        
        # Common YAGS concepts
        yags_terms = ['attribute', 'skill', 'difficulty', 'roll', 'bonus', 'penalty', 'success', 'failure']
        aeonisk_terms = ['void', 'soulcredit', 'bond', 'ritual', 'astral', 'faction', 'family']
        
        for term in yags_terms + aeonisk_terms:
            if term in title.lower() or term in content.lower():
                tags.append(term)
        
        return tags
    
    async def populate_vectorstore(self):
        """Load all markdown files into the vectorstore."""
        
        # Define all the rule files to process
        rule_files = [
            "ai_pack/core.md",
            "ai_pack/character.md", 
            "ai_pack/scifitech.md",
            "content/Aeonisk - YAGS Module - v1.2.1.md",
            "content/Aeonisk - System Neutral Lore - v1.2.1.md",
            "content/Aeonisk - Gear & Tech Reference - v1.2.1.md",
            "content/experimental/Aeonisk - Tactical Module - v1.2.1.md"
        ]
        
        all_chunks = []
        
        for file_path in rule_files:
            full_path = Path(file_path)
            if full_path.exists():
                print(f"Processing {file_path}...")
                chunks = self.chunk_markdown_content(str(full_path))
                all_chunks.extend(chunks)
            else:
                print(f"Warning: {file_path} not found")
        
        # Add to vectorstore
        if all_chunks:
            documents = [chunk.content for chunk in all_chunks]
            metadatas = [
                {
                    "source_file": chunk.source_file,
                    "section": chunk.section,
                    "rule_type": chunk.rule_type,
                    "tags": ",".join(chunk.tags)
                }
                for chunk in all_chunks
            ]
            ids = [f"{chunk.source_file}_{i}" for i, chunk in enumerate(all_chunks)]
            
            # Clear existing collection and add new documents
            try:
                # Get all existing IDs first
                existing = self.collection.get()
                if existing['ids']:
                    self.collection.delete(ids=existing['ids'])
            except:
                pass  # Collection might be empty
                
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            print(f"Added {len(all_chunks)} rule chunks to vectorstore")
        
    async def query_rules(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query the vectorstore for relevant rules."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            if not results['documents'] or not results['documents'][0]:
                return []
            
            formatted_results = []
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 1.0
                
                formatted_results.append({
                    'content': doc,
                    'source': metadata.get('source_file', 'unknown'),
                    'section': metadata.get('section', 'unknown'),
                    'rule_type': metadata.get('rule_type', 'general'),
                    'relevance': 1.0 - distance,
                    'tags': metadata.get('tags', '').split(',') if metadata.get('tags') else []
                })
            
            return formatted_results
            
        except Exception as e:
            print(f"Vectorstore query error: {e}")
            return []


class RuleAwareCharacterSystem:
    """Character system that queries rules for accurate decision making."""
    
    def __init__(self, vectorstore: AeoniskVectorStore):
        self.vectorstore = vectorstore
        
    async def make_informed_decision(self, character: 'AeoniskCharacter', scenario: Dict[str, Any], available_actions: List[str]) -> Dict[str, Any]:
        """Make a decision based on character personality AND relevant rules."""
        
        # Query for relevant rules based on the scenario and character
        rule_queries = [
            f"void score {character.void_score} corruption effects",
            f"{character.family_line} family line specialty abilities",
            f"skill check {scenario.get('primary_skill', 'awareness')} difficulty",
            f"ritual mechanics willpower astral arts",
            f"{character.origin_faction} faction resources"
        ]
        
        relevant_rules = []
        for query in rule_queries:
            rules = await self.vectorstore.query_rules(query, n_results=2)
            relevant_rules.extend(rules)
        
        # Analyze each action based on rules and personality
        action_analysis = []
        
        for action in available_actions:
            # Get rules relevant to this specific action
            action_rules = await self.vectorstore.query_rules(f"{action} skill check difficulty", n_results=2)
            
            # Calculate appeal based on personality (from existing system)
            appeal_score = self._calculate_personality_appeal(action, character)
            
            # Adjust based on rule knowledge
            rule_adjustment = self._analyze_rule_feasibility(action, action_rules, character)
            
            final_score = appeal_score + rule_adjustment
            
            action_analysis.append({
                'action': action,
                'appeal_score': appeal_score,
                'rule_feasibility': rule_adjustment,
                'final_score': final_score,
                'supporting_rules': action_rules[:2]  # Top 2 most relevant rules
            })
        
        # Choose the best action
        best_action = max(action_analysis, key=lambda x: x['final_score'])
        
        # Generate reasoning based on rules
        reasoning = await self._generate_rule_based_reasoning(
            best_action, character, scenario, relevant_rules
        )
        
        return {
            'chosen_action': best_action['action'],
            'reasoning': reasoning,
            'rule_support': best_action['supporting_rules'],
            'all_analysis': action_analysis
        }
    
    def _calculate_personality_appeal(self, action: str, character: 'AeoniskCharacter') -> int:
        """Calculate base appeal from personality (simplified from existing system)."""
        p = character.personality
        action_lower = action.lower()
        score = 5
        
        if 'confront' in action_lower or 'direct' in action_lower:
            score += (p.risk_tolerance - 5)
        if 'ritual' in action_lower or 'void' in action_lower:
            score += (p.void_curiosity - 5)
        if 'negotiate' in action_lower or 'alliance' in action_lower:
            score += (p.social_preference - 5)
        if 'stealth' in action_lower or 'investigate' in action_lower:
            score += (10 - p.social_preference - 5)
            
        return max(1, min(10, score))
    
    def _analyze_rule_feasibility(self, action: str, rules: List[Dict], character: 'AeoniskCharacter') -> int:
        """Analyze if character can actually perform this action based on rules."""
        adjustment = 0
        
        for rule in rules:
            content = rule['content'].lower()
            
            # Check skill requirements
            if 'astral arts' in content and character.astral_arts < 3:
                if 'ritual' in action.lower():
                    adjustment -= 2  # Can't do rituals well
            
            if 'stealth' in content and character.stealth < 3:
                if 'stealth' in action.lower():
                    adjustment -= 2  # Poor at stealth
                    
            if 'corporate influence' in content and character.corporate_influence < 3:
                if 'negotiate' in action.lower():
                    adjustment -= 1  # Limited social resources
            
            # Void score considerations
            if character.void_score >= 5 and 'ritual' in content:
                adjustment -= 1  # High void makes rituals dangerous
            
            # Family line bonuses
            if character.family_line.lower() in content:
                adjustment += 1  # Family expertise applies
        
        return adjustment
    
    async def _generate_rule_based_reasoning(self, best_action: Dict, character: 'AeoniskCharacter', scenario: Dict, rules: List[Dict]) -> str:
        """Generate rich, story-driven reasoning with character voice."""
        
        # Create varied opening structures
        motivation_openers = [
            f"My {character.family_line} heritage compels me to {character.personal_motivation.lower()}",
            f"The weight of {character.personal_motivation.lower()} drives my choice here",
            f"As someone determined to {character.personal_motivation.lower()}, I see this as crucial",
            f"This situation aligns with my core drive to {character.personal_motivation.lower()}",
            f"Given everything my family has taught me about {character.personal_motivation.lower()}"
        ]
        
        # Family line specific voice patterns
        family_voices = {
            'Elaras': [
                "The harmony of all things guides my approach",
                "Balance and unity are paramount in this chaos", 
                "My family's spiritual wisdom suggests",
                "The Elaras way demands measured response"
            ],
            'Karsel': [
                "Despite our family's disgrace, I know void corruption better than most",
                "The Karsel Line may be fallen, but our expertise in dangerous knowledge remains",
                "My family's dark legacy actually serves me here",
                "Others fear what we've learned through suffering"
            ],
            'Kythea': [
                "The futures market has taught me to read patterns others miss",
                "My trading instincts see opportunity in this crisis",
                "Kythea wisdom: every disruption creates profit potential",
                "The commercial implications here are staggering"
            ],
            'Wild-Current': [
                "The natural flow of things has been disrupted - I must restore it",
                "Freedom means taking responsibility when others won't", 
                "My Freeborn instincts rebel against this artificial chaos",
                "The wild currents whisper warnings about this situation"
            ]
        }
        
        # Risk personality expressions
        risk_expressions = {
            'high': [
                "The potential rewards justify the danger",
                "Fortune favors the bold in times like these",
                "Sometimes you have to gamble everything",
                "Calculated risks separate leaders from followers"
            ],
            'low': [
                "Caution serves better than reckless action here",
                "The smart play is the safe play",
                "Too much is at stake for unnecessary chances", 
                "Wisdom lies in protecting what we have"
            ],
            'medium': [
                "This requires careful judgment of risk versus reward",
                "The situation demands measured boldness",
                "Neither reckless nor cowardly - but strategic"
            ]
        }
        
        # Void awareness expressions
        void_awareness = {
            'high': f"With void influence at {scenario['void_influence']}, reality itself is unstable here",
            'medium': f"The void presence complicates everything",
            'low': f"At least the void contamination seems manageable",
            'none': "Thankfully, void corruption isn't a major factor"
        }
        
        # Build narrative reasoning
        opener = random.choice(motivation_openers)
        
        family_voice = ""
        if character.family_line in family_voices:
            family_voice = random.choice(family_voices[character.family_line])
        else:
            family_voice = f"My {character.family_line} training shapes how I approach this"
        
        # Risk assessment
        risk_level = 'high' if character.personality.risk_tolerance >= 7 else 'low' if character.personality.risk_tolerance <= 3 else 'medium'
        risk_voice = random.choice(risk_expressions[risk_level])
        
        # Void considerations
        void_level = scenario['void_influence']
        if void_level >= 7:
            void_voice = void_awareness['high']
        elif void_level >= 4:
            void_voice = void_awareness['medium']
        elif void_level >= 2:
            void_voice = void_awareness['low']
        else:
            void_voice = void_awareness['none']
        
        # Action-specific reasoning
        action_reasoning = ""
        action_lower = best_action['action'].lower()
        
        if 'investigate' in action_lower:
            action_reasoning = "Knowledge is power, and understanding the true scope of this crisis comes first."
        elif 'ritual' in action_lower:
            action_reasoning = "Sometimes the spiritual solution is the only real solution."
        elif 'alliance' in action_lower or 'seek' in action_lower:
            action_reasoning = "No one faces challenges like this alone - strength comes through unity."
        elif 'stealth' in action_lower:
            action_reasoning = "Information gathered unseen is worth more than bold gestures."
        elif 'negotiate' in action_lower:
            action_reasoning = "Words can achieve what force cannot, especially in delicate situations."
        else:
            action_reasoning = "Direct action cuts through uncertainty."
        
        # Combine into flowing narrative
        reasoning = f"{opener}. {family_voice}. {void_voice}. {action_reasoning} {risk_voice}."
        
        return reasoning


class MultiTurnGameSession:
    """Manages a persistent multi-turn game session with story continuity."""
    
    def __init__(self, vectorstore: AeoniskVectorStore):
        self.vectorstore = vectorstore
        self.rule_system = RuleAwareCharacterSystem(vectorstore)
        self.session_id = f"session_{int(time.time())}"
        self.turn_number = 0
        self.story_history = []
        self.characters = []
        self.current_scenario = None
        
    async def initialize_session(self, num_players: int = 3):
        """Set up a new game session with diverse characters."""
        print(f"🎲 Initializing Aeonisk YAGS Session {self.session_id}")
        
        # Generate diverse characters from different factions
        factions = list(FAMILY_LINES.keys())
        
        for i in range(num_players):
            faction = random.choice(factions)
            family_options = list(FAMILY_LINES[faction].keys())
            family_line = random.choice(family_options)
            
            character = await self._generate_rule_aware_character(faction, family_line)
            self.characters.append(character)
            
            print(f"📋 Generated {character.full_name} ({character.family_line} of {character.origin_faction})")
        
        # Generate opening scenario
        self.current_scenario = await self._generate_opening_scenario()
        print(f"🌟 Opening Scenario: {self.current_scenario['title']}")
        
    async def _generate_rule_aware_character(self, faction: str, family_line: str) -> 'AeoniskCharacter':
        """Generate character using vectorstore knowledge of rules."""
        
        # Query for character creation rules
        char_rules = await self.vectorstore.query_rules(
            f"character creation attributes skills {faction} {family_line}", 
            n_results=3
        )
        
        # Use rules to inform character generation
        base_character = self._create_base_character(faction, family_line)
        
        # Apply rule-based modifications
        for rule in char_rules:
            if 'attribute' in rule['content'].lower():
                # Adjust attributes based on faction/family rules
                if faction.lower() in rule['content'].lower():
                    base_character = self._apply_faction_bonuses(base_character, rule['content'])
        
        return base_character
    
    def _create_base_character(self, faction: str, family_line: str) -> 'AeoniskCharacter':
        """Create base character with personality."""
        from truly_dynamic_system import DynamicCharacterGenerator, PersonalityProfile, AeoniskCharacter
        
        # Generate dynamic personality
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
        
        char = AeoniskCharacter(
            given_name=given_name,
            family_line=family_line,
            full_name=f"{given_name} {family_line}",
            origin_faction=faction,
            family_reputation=line_data['reputation'],
            personal_motivation=self._generate_dynamic_motivation(line_data['reputation']),
            personality=personality
        )
        
        # Generate attributes with personality influence
        for attr in ['strength', 'health', 'agility', 'dexterity', 'perception', 'intelligence', 'empathy', 'willpower']:
            base_value = random.randint(2, 5)
            
            # Personality influences certain attributes
            if attr == 'willpower' and personality.void_curiosity >= 7:
                base_value = min(6, base_value + 1)
            elif attr == 'empathy' and personality.social_preference >= 7:
                base_value = min(6, base_value + 1)
            elif attr == 'intelligence' and personality.pragmatism >= 7:
                base_value = min(6, base_value + 1)
                
            setattr(char, attr, base_value)
        
        return char
    
    def _generate_dynamic_motivation(self, reputation: str) -> str:
        """Generate varied motivations based on family reputation."""
        motivations = {
            'rising': [
                'Capitalize on family momentum', 'Prove worthy of rising status', 
                'Seize emerging opportunities', 'Build lasting influence'
            ],
            'stable': [
                'Maintain family honor', 'Protect established interests', 
                'Serve faction loyally', 'Preserve traditions'
            ],
            'declining': [
                'Restore family standing', 'Uncover what went wrong', 
                'Forge new alliances', 'Break from failing strategies'
            ],
            'disgraced': [
                'Redeem family name', 'Prove past mistakes wrong', 
                'Create new identity', 'Challenge the system that failed us'
            ],
            'mysterious': [
                'Fulfill hidden agenda', 'Maintain family secrets', 
                'Gather crucial intelligence', 'Protect ancient knowledge'
            ]
        }
        
        return random.choice(motivations.get(reputation, motivations['stable']))
    
    async def _generate_opening_scenario(self) -> Dict[str, Any]:
        """Generate opening scenario using rule knowledge."""
        
        # Query for scenario inspiration
        scenario_rules = await self.vectorstore.query_rules(
            "void corruption faction conflict astral disruption", 
            n_results=3
        )
        
        # Use rules to create grounded scenarios
        scenario_types = [
            {
                'title': 'Void Corruption Outbreak',
                'base': 'mysterious void energy signatures detected',
                'complications': ['reality distortions', 'tech malfunctions', 'spiritual interference']
            },
            {
                'title': 'Faction Resource Dispute', 
                'base': 'competing claims over astral harvesting rights',
                'complications': ['legal challenges', 'corporate espionage', 'family honor at stake']
            },
            {
                'title': 'Bond Network Disruption',
                'base': 'spiritual connections being severed systematically',
                'complications': ['traumatized individuals', 'ritual sabotage', 'hidden agendas']
            }
        ]
        
        base_scenario = random.choice(scenario_types)
        
        return {
            'title': base_scenario['title'],
            'description': f"{base_scenario['base']} - investigation reveals {random.choice(base_scenario['complications'])}",
            'location': self._generate_location(),
            'void_influence': random.randint(2, 8),
            'key_elements': random.sample(base_scenario['complications'], 2),
            'faction_tensions': self._generate_faction_tensions(),
            'supporting_rules': scenario_rules
        }
    
    def _generate_location(self) -> str:
        """Generate varied locations."""
        locations = [
            "Corporate Sector Alpha, Aeonisk Prime",
            "Abandoned Mining Station, Outer Rim", 
            "Resonance Temple Complex, Nimbus",
            "Underground Market, Void Quarter",
            "Astral Research Facility, Arcadia",
            "Freeborn Settlement, Wild Territories"
        ]
        return random.choice(locations)
    
    def _generate_faction_tensions(self) -> List[str]:
        """Generate realistic faction conflicts."""
        all_factions = list(FAMILY_LINES.keys())
        involved = random.sample(all_factions, random.randint(2, 3))
        
        tensions = []
        for i in range(len(involved) - 1):
            tensions.append(f"{involved[i]} vs {involved[i+1]}")
            
        return tensions
    
    async def play_turn(self) -> Dict[str, Any]:
        """Execute one turn of the game session."""
        self.turn_number += 1
        
        print(f"\n🎯 === Turn {self.turn_number} ===")
        print(f"Scenario: {self.current_scenario['title']}")
        print(f"Location: {self.current_scenario['location']}")
        
        turn_results = []
        
        # Each character takes an action
        for character in self.characters:
            print(f"\n🎭 {character.full_name}'s turn:")
            
            # Generate available actions based on current situation
            available_actions = await self._generate_contextual_actions(character, self.current_scenario)
            
            # Make informed decision
            decision = await self.rule_system.make_informed_decision(
                character, self.current_scenario, available_actions
            )
            
            # Execute action and get results
            action_result = await self._execute_action(character, decision, self.current_scenario)
            
            turn_results.append({
                'character': character.full_name,
                'decision': decision,
                'result': action_result
            })
            
            print(f"   Action: {decision['chosen_action']}")
            print(f"   Reasoning: {decision['reasoning']}")
            print(f"   Outcome: {action_result['outcome']}")
        
        # Update scenario based on actions
        self.current_scenario = await self._evolve_scenario(turn_results)
        
        # Add to story history
        turn_story = {
            'turn': self.turn_number,
            'scenario': self.current_scenario['title'],
            'character_actions': turn_results,
            'scenario_evolution': self.current_scenario.get('changes', 'Situation remains stable')
        }
        
        self.story_history.append(turn_story)
        
        return turn_story
    
    async def _generate_contextual_actions(self, character: 'AeoniskCharacter', scenario: Dict) -> List[str]:
        """Generate actions relevant to current scenario and character abilities."""
        
        # Query for action options based on scenario
        action_rules = await self.vectorstore.query_rules(
            f"{scenario['title']} possible actions player options", 
            n_results=2
        )
        
        # Base actions that adapt to context
        base_actions = [
            f"Investigate the {scenario['key_elements'][0]} using {character.family_line} expertise",
            f"Attempt to {random.choice(['stabilize', 'contain', 'analyze'])} the situation with available skills",
            f"Seek alliance with {random.choice(['local contacts', 'faction representatives', 'affected parties'])}",
            f"Use {random.choice(['stealth', 'diplomacy', 'technical analysis'])} to gather more information",
        ]
        
        # Add character-specific actions
        if character.astral_arts >= 3:
            base_actions.append("Perform ritual to address the spiritual aspects")
        if character.hacking >= 3:
            base_actions.append("Hack into relevant systems for digital intelligence")
        if character.corporate_influence >= 3:
            base_actions.append("Leverage corporate connections for resources")
            
        return random.sample(base_actions, min(6, len(base_actions)))
    
    async def _execute_action(self, character: 'AeoniskCharacter', decision: Dict, scenario: Dict) -> Dict[str, Any]:
        """Execute the chosen action and determine outcomes based on rules."""
        
        action = decision['chosen_action']
        
        # Query for relevant mechanics
        mechanic_rules = await self.vectorstore.query_rules(
            f"skill check difficulty success failure {action}", 
            n_results=2
        )
        
        # Determine primary skill and attribute
        skill_mapping = {
            'investigate': ('intelligence', 'awareness'),
            'ritual': ('willpower', 'astral_arts'),
            'negotiate': ('empathy', 'corporate_influence'),
            'stealth': ('agility', 'stealth'),
            'hack': ('intelligence', 'hacking'),
            'alliance': ('empathy', 'charm')
        }
        
        # Find best match
        primary_attr, primary_skill = 'intelligence', 'awareness'  # default
        for keyword, (attr, skill) in skill_mapping.items():
            if keyword in action.lower():
                primary_attr, primary_skill = attr, skill
                break
        
        # Calculate success based on YAGS rules (Attribute x Skill + d20)
        attr_value = getattr(character, primary_attr, 3)
        skill_value = getattr(character, primary_skill, 2)
        roll = random.randint(1, 20)
        total = attr_value * skill_value + roll
        
        # Difficulty based on scenario complexity and void influence
        base_difficulty = 15 + scenario['void_influence']
        
        # Determine outcome
        success = total >= base_difficulty
        margin = total - base_difficulty
        
        if success:
            if margin >= 10:
                outcome = f"Exceptional success! {character.given_name} achieves more than expected."
                story_impact = "major_positive"
            else:
                outcome = f"Success. {character.given_name} accomplishes the goal effectively."
                story_impact = "positive"
        else:
            if margin <= -10:
                outcome = f"Critical failure. {character.given_name}'s action backfires significantly."
                story_impact = "major_negative"
            else:
                outcome = f"Failure. {character.given_name}'s attempt doesn't succeed."
                story_impact = "negative"
        
        return {
            'outcome': outcome,
            'roll_total': total,
            'difficulty': base_difficulty,
            'margin': margin,
            'story_impact': story_impact,
            'primary_skill_used': f"{primary_attr} × {primary_skill}",
            'supporting_rules': mechanic_rules
        }
    
    async def _evolve_scenario(self, turn_results: List[Dict]) -> Dict[str, Any]:
        """Evolve the scenario based on character actions."""
        
        # Analyze turn results
        successes = sum(1 for result in turn_results if result['result']['story_impact'] in ['positive', 'major_positive'])
        failures = sum(1 for result in turn_results if result['result']['story_impact'] in ['negative', 'major_negative'])
        
        scenario = self.current_scenario.copy()
        
        if successes > failures:
            scenario['title'] = scenario['title'].replace('Outbreak', 'Investigation').replace('Disruption', 'Resolution')
            scenario['description'] += " The situation shows signs of improvement."
            scenario['void_influence'] = max(1, scenario['void_influence'] - 1)
            scenario['changes'] = "Situation improving due to character actions"
        else:
            scenario['title'] = scenario['title'].replace('Investigation', 'Crisis').replace('Resolution', 'Escalation')
            scenario['description'] += " The situation worsens."
            scenario['void_influence'] = min(10, scenario['void_influence'] + 1)
            scenario['changes'] = "Situation deteriorating despite efforts"
        
        return scenario
    
    async def generate_dataset_entry(self) -> Dict[str, Any]:
        """Generate comprehensive dataset entry for this session."""
        
        return {
            'session_id': self.session_id,
            'total_turns': self.turn_number,
            'domain': {
                'core': 'multi_turn_player_decisions',
                'subdomain': 'collaborative_problem_solving'
            },
            'characters': [
                {
                    'name': char.full_name,
                    'faction': char.origin_faction,
                    'family_line': char.family_line,
                    'motivation': char.personal_motivation,
                    'personality_summary': f"Risk {char.personality.risk_tolerance}/10, Void Curiosity {char.personality.void_curiosity}/10",
                    'key_stats': {
                        'willpower': char.willpower,
                        'intelligence': char.intelligence,
                        'void_score': char.void_score
                    }
                }
                for char in self.characters
            ],
            'story_progression': self.story_history,
            'final_scenario_state': self.current_scenario,
            'training_value': {
                'collaborative_decision_making': 'Characters with different backgrounds solving problems together',
                'rule_grounded_reasoning': 'Decisions based on actual game mechanics',
                'narrative_continuity': 'Story evolves based on character actions',
                'personality_consistency': 'Character decisions reflect established personality traits'
            }
        }


# Import existing components
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


async def main():
    """Run the vectorstore-enhanced multi-turn system."""
    
    print("🚀 Starting Aeonisk YAGS Vectorstore-Enhanced System")
    print("Building your personal MUD with rule-aware AI agents...\n")
    
    # Initialize vectorstore
    vectorstore = AeoniskVectorStore()
    
    # Populate with all rules (this may take a moment)
    print("📚 Loading all YAGS and Aeonisk rules into vectorstore...")
    await vectorstore.populate_vectorstore()
    
    # Start a multi-turn session
    session = MultiTurnGameSession(vectorstore)
    await session.initialize_session(num_players=3)
    
    # Play several turns to show continuity
    for turn in range(3):
        turn_result = await session.play_turn()
        
        # Brief pause to show turn progression
        await asyncio.sleep(1)
    
    # Generate final dataset
    print("\n📊 Generating Training Dataset...")
    dataset = await session.generate_dataset_entry()
    
    # Save dataset
    timestamp = int(time.time())
    dataset_file = f"./vectorstore_session_{timestamp}.yaml"
    
    with open(dataset_file, 'w') as f:
        yaml.dump(dataset, f, default_flow_style=False, sort_keys=False)
    
    print(f"\n✅ Complete game session saved to: {dataset_file}")
    print("\n🎮 Your personal Aeonisk MUD session is complete!")
    print("Each run creates unique stories with rule-grounded AI decisions.")


if __name__ == "__main__":
    import time
    asyncio.run(main())