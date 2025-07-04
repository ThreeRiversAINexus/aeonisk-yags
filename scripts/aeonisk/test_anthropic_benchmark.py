#!/usr/bin/env python3
"""
Simple test to run Anthropic models through the benchmark system.
This bypasses the module import issues.
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the models and providers directly (copy-pasted to avoid import issues)
class TaskDomain(BaseModel):
    core: str
    subdomain: str

class BenchmarkTask(BaseModel):
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
    difficulty_level: Optional[str] = None
    task_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

class ModelResponse(BaseModel):
    task_id: str
    model_name: str
    provider: str
    response_time: float
    token_count: Optional[int] = None
    raw_response: str
    parsed_response: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    attribute_used: Optional[str] = None
    skill_used: Optional[str] = None
    roll_formula: Optional[str] = None
    difficulty_guess: Optional[int] = None
    outcome_explanation: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    error: Optional[str] = None
    successful_parse: bool = True

class AnthropicProvider:
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
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f'{self.base_url}/v1/messages', headers=headers, json=data) as response:
                    response_text = await response.text()
                    
                    if response.status == 200:
                        response_data = json.loads(response_text)
                        raw_response = response_data['content'][0]['text']
                        response_time = time.time() - start_time
                        
                        return ModelResponse(
                            task_id=task.task_id,
                            model_name=self.model_name,
                            provider=self.name,
                            response_time=response_time,
                            token_count=response_data.get('usage', {}).get('output_tokens'),
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

def load_dataset_tasks(dataset_path: str, max_tasks: int = 2) -> List[BenchmarkTask]:
    """Load tasks from the dataset file."""
    tasks = []
    
    logger.info(f"Loading tasks from {dataset_path}")
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse the dataset file (simplified version)
    sections = content.split('---')
    
    for i, section in enumerate(sections):
        if i >= max_tasks:
            break
        
        if not section.strip():
            continue
        
        # Simple parsing - look for key sections
        lines = section.strip().split('\n')
        
        task_data = {
            'task_id': f'task_{i:03d}',
            'domain': TaskDomain(core='general', subdomain='general'),
            'scenario': '',
            'environment': '',
            'stakes': '',
            'characters': [],
            'goal': '',
            'expected_fields': ['attribute_used', 'skill_used', 'roll_formula', 'difficulty_guess'],
            'gold_answer': {}
        }
        
        # Extract scenario (first meaningful line)
        for line in lines:
            if line.strip() and not line.startswith('#'):
                task_data['scenario'] = line.strip()
                break
        
        # Default values for missing fields
        task_data['environment'] = 'Standard RPG environment'
        task_data['stakes'] = 'Standard stakes'
        task_data['goal'] = 'Resolve the scenario using YAGS rules'
        task_data['characters'] = [
            {
                'name': 'Player Character',
                'attributes': {'Intelligence': 3, 'Dexterity': 3, 'Strength': 3, 'Will': 3},
                'skills': {'General': 2, 'Combat': 2, 'Knowledge': 2},
                'current_void': 0,
                'wound': 0
            }
        ]
        
        if task_data['scenario']:
            tasks.append(BenchmarkTask(**task_data))
    
    logger.info(f"Loaded {len(tasks)} tasks from dataset")
    return tasks

async def run_benchmark_test():
    """Run a simple benchmark test with Anthropic models."""
    
    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment")
        return
    
    print(f"✓ Found API key: {api_key[:10]}...")
    
    # Configure models to test
    model_configs = [
        {
            'id': 'claude-haiku',
            'model': 'claude-3-haiku-20240307',
            'api_key': api_key,
            'timeout': 30
        },
        {
            'id': 'claude-sonnet',
            'model': 'claude-3-sonnet-20240229',
            'api_key': api_key,
            'timeout': 30
        }
    ]
    
    # Load dataset tasks
    dataset_path = '../../datasets/aeonisk_dataset_normalized_complete.txt'
    tasks = load_dataset_tasks(dataset_path, max_tasks=2)
    
    if not tasks:
        print("❌ No tasks loaded from dataset")
        return
    
    print(f"✓ Loaded {len(tasks)} tasks from dataset")
    
    # Test each model
    all_results = {}
    
    for model_config in model_configs:
        print(f"\n🔄 Testing {model_config['id']} ({model_config['model']})")
        
        provider = AnthropicProvider(model_config)
        model_results = []
        
        for task in tasks:
            print(f"  📋 Task {task.task_id}: {task.scenario[:60]}...")
            
            response = await provider.generate_response(task)
            model_results.append(response)
            
            if response.error:
                print(f"    ❌ Error: {response.error}")
            else:
                print(f"    ✓ Success ({response.response_time:.2f}s, {len(response.raw_response)} chars)")
        
        all_results[model_config['id']] = model_results
        
        # Calculate success rate
        successful = sum(1 for r in model_results if not r.error)
        success_rate = successful / len(model_results) * 100
        avg_time = sum(r.response_time for r in model_results) / len(model_results)
        
        print(f"  📊 Success rate: {success_rate:.1f}% ({successful}/{len(model_results)})")
        print(f"  📊 Average time: {avg_time:.2f}s")
    
    # Summary
    print(f"\n📊 BENCHMARK SUMMARY")
    print(f"Dataset: {dataset_path}")
    print(f"Tasks: {len(tasks)}")
    print(f"Models: {len(model_configs)}")
    
    for model_id, results in all_results.items():
        successful = sum(1 for r in results if not r.error)
        success_rate = successful / len(results) * 100
        avg_time = sum(r.response_time for r in results) / len(results)
        
        print(f"  {model_id}: {success_rate:.1f}% success, {avg_time:.2f}s avg")
    
    print(f"\n✅ Benchmark test completed!")
    return all_results

if __name__ == "__main__":
    asyncio.run(run_benchmark_test())