#!/usr/bin/env python3
"""
Direct test for Anthropic provider to debug API issues.
"""

import asyncio
import json
import logging
import time
import os
from typing import Dict, List, Optional, Any
import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TaskDomain(BaseModel):
    """Model representing a task domain."""
    core: str
    subdomain: str

class BenchmarkTask(BaseModel):
    """Model representing a benchmark task from the dataset."""
    task_id: str
    domain: TaskDomain
    scenario: str
    environment: str
    stakes: str
    characters: List[Dict[str, Any]]
    goal: str
    expected_fields: List[str]
    gold_answer: Dict[str, Any]
    aeonisk_extra_data: Optional[Dict[str, Any]] = None
    
    # Metadata for benchmarking
    difficulty_level: Optional[str] = None
    task_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

class ModelResponse(BaseModel):
    """Model representing a model's response to a benchmark task."""
    task_id: str
    model_name: str
    provider: str
    response_time: float
    token_count: Optional[int] = None
    raw_response: str
    parsed_response: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Response fields extracted from model output
    attribute_used: Optional[str] = None
    skill_used: Optional[str] = None
    roll_formula: Optional[str] = None
    difficulty_guess: Optional[int] = None
    outcome_explanation: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    
    # Error handling
    error: Optional[str] = None
    successful_parse: bool = True

class AnthropicProvider:
    """Anthropic Claude API provider."""
    
    def __init__(self, config: Dict[str, Any]):
        self.name = 'anthropic'
        self.config = config
        self.model_name = config.get('model', 'claude-3-haiku-20240307')
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)
        self.api_key = config['api_key']
        self.base_url = config.get('base_url', 'https://api.anthropic.com')
        logger.info(f"Initialized Anthropic provider with model: {self.model_name}")
    
    def create_prompt(self, task: BenchmarkTask) -> str:
        """Create a prompt for the model based on the task."""
        prompt = f"""You are an expert in the Aeonisk YAGS tabletop RPG system. You will be given a gameplay scenario and need to provide a detailed analysis of how to resolve it according to the rules.

SCENARIO:
{task.scenario}

ENVIRONMENT: {task.environment}

STAKES: {task.stakes}

CHARACTERS:
"""
        
        for character in task.characters:
            prompt += f"- {character.get('name', 'Unknown')}\n"
            if 'attributes' in character:
                attrs = character['attributes']
                prompt += f"  Attributes: {attrs}\n"
            if 'skills' in character:
                skills = character['skills']
                prompt += f"  Skills: {skills}\n"
            if 'current_void' in character:
                prompt += f"  Current Void: {character['current_void']}\n"
            if 'wound' in character:
                prompt += f"  Wound: {character['wound']}\n"
            prompt += "\n"
        
        prompt += f"""GOAL: {task.goal}

Please provide your analysis in the following format:

**Attribute Used:** [The primary attribute for this action]
**Skill Used:** [The skill that applies to this action]
**Roll Formula:** [The complete formula: Attribute × Skill = Base; Base + d20]
**Difficulty Guess:** [The target number for a moderate success]
**Rationale:** [Brief explanation of your choices]

**Outcome Explanation:**
For each outcome level, provide both narrative and mechanical effects:

**Critical Failure:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

**Failure:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

**Moderate Success:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

**Good Success:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

**Excellent Success:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

**Exceptional Success:**
- Narrative: [Vivid description of what happens]
- Mechanical Effect: [Specific game mechanical consequences]

Remember to:
1. Follow YAGS core mechanics (Attribute × Skill = Base Ability)
2. Consider Aeonisk-specific rules (Void, Soulcredit, rituals, etc.)
3. Account for character wounds and conditions
4. Set appropriate difficulty levels
5. Create vivid, thematically appropriate narratives
6. Specify clear mechanical consequences
"""
        
        return prompt
    
    async def generate_response(self, task: BenchmarkTask) -> ModelResponse:
        """Generate a response using Anthropic API."""
        start_time = time.time()
        
        try:
            prompt = self.create_prompt(task)
            logger.info(f"Sending request to Anthropic API with model: {self.model_name}")
            
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01'
            }
            
            data = {
                'model': self.model_name,
                'messages': [
                    {"role": "user", "content": prompt}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }
            
            logger.debug(f"Request headers: {headers}")
            logger.debug(f"Request data: {json.dumps(data, indent=2)}")
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f'{self.base_url}/v1/messages', headers=headers, json=data) as response:
                    response_text = await response.text()
                    logger.debug(f"Response status: {response.status}")
                    logger.debug(f"Response text: {response_text}")
                    
                    if response.status == 200:
                        response_data = json.loads(response_text)
                        raw_response = response_data['content'][0]['text']
                        response_time = time.time() - start_time
                        
                        return ModelResponse(
                            task_id=task.task_id,
                            model_name=self.model_name,
                            provider=self.name,
                            response_time=response_time,
                            token_count=response_data.get('usage', {}).get('total_tokens'),
                            raw_response=raw_response,
                            parsed_response={},
                            successful_parse=True
                        )
                    else:
                        error_data = json.loads(response_text) if response_text else {}
                        error_msg = error_data.get('error', {}).get('message', f'HTTP {response.status}')
                        raise Exception(f"API Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error generating response with Anthropic: {e}")
            return ModelResponse(
                task_id=task.task_id,
                model_name=self.model_name,
                provider=self.name,
                response_time=time.time() - start_time,
                raw_response="",
                error=str(e),
                successful_parse=False
            )

async def test_anthropic_provider():
    """Test the Anthropic provider with a simple task."""
    
    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment")
        return
    
    print(f"✓ Found API key: {api_key[:10]}...")
    
    # Create provider config
    config = {
        'model': 'claude-3-haiku-20240307',
        'api_key': api_key,
        'timeout': 30
    }
    
    provider = AnthropicProvider(config)
    print(f"✓ Created provider: {provider.name} - {provider.model_name}")
    
    # Create a simple test task
    task = BenchmarkTask(
        task_id="test_001",
        domain=TaskDomain(core="combat", subdomain="melee"),
        scenario="A cyberpunk hacker attempts to slice through a corporate firewall while under pressure from approaching security guards.",
        environment="Corporate data center, high security, time pressure",
        stakes="High - discovery means imprisonment",
        characters=[
            {
                "name": "Zara Chen",
                "attributes": {"Intelligence": 4, "Dexterity": 3, "Will": 3},
                "skills": {"Hacking": 3, "Electronics": 2, "Stealth": 2},
                "current_void": 2,
                "wound": 0
            }
        ],
        goal="Successfully penetrate the firewall and extract corporate data",
        expected_fields=["attribute_used", "skill_used", "roll_formula", "difficulty_guess"],
        gold_answer={}
    )
    
    print("✓ Created test task")
    
    # Test the provider
    print("🔄 Testing Anthropic provider...")
    response = await provider.generate_response(task)
    
    print(f"📊 Response time: {response.response_time:.2f}s")
    print(f"📊 Success: {response.successful_parse}")
    
    if response.error:
        print(f"❌ Error: {response.error}")
    else:
        print(f"✓ Response received ({len(response.raw_response)} chars)")
        print(f"Raw response preview: {response.raw_response[:200]}...")
    
    return response

if __name__ == "__main__":
    asyncio.run(test_anthropic_provider())