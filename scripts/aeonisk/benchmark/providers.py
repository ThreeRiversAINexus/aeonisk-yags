"""
LLM providers for the Aeonisk YAGS benchmarking system.

This module provides interfaces to various language model providers.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
import aiohttp
import openai
from openai import OpenAI

from .models import BenchmarkTask, ModelResponse

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.model_name = config.get('model', 'unknown')
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)
    
    @abstractmethod
    async def generate_response(self, task: BenchmarkTask) -> ModelResponse:
        """Generate a response for a benchmark task."""
        pass
    
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
    
    def parse_response(self, response_text: str, task: BenchmarkTask) -> Dict[str, Any]:
        """Parse the model's response to extract structured data."""
        parsed = {
            'attribute_used': None,
            'skill_used': None,
            'roll_formula': None,
            'difficulty_guess': None,
            'rationale': None,
            'outcome_explanation': {}
        }
        
        try:
            # Extract basic fields using regex patterns
            import re
            
            # Attribute Used
            attr_match = re.search(r'\*\*Attribute Used:\*\*\s*([^\n]+)', response_text)
            if attr_match:
                parsed['attribute_used'] = attr_match.group(1).strip()
            
            # Skill Used
            skill_match = re.search(r'\*\*Skill Used:\*\*\s*([^\n]+)', response_text)
            if skill_match:
                parsed['skill_used'] = skill_match.group(1).strip()
            
            # Roll Formula
            formula_match = re.search(r'\*\*Roll Formula:\*\*\s*([^\n]+)', response_text)
            if formula_match:
                parsed['roll_formula'] = formula_match.group(1).strip()
            
            # Difficulty Guess
            diff_match = re.search(r'\*\*Difficulty Guess:\*\*\s*(\d+)', response_text)
            if diff_match:
                parsed['difficulty_guess'] = int(diff_match.group(1))
            
            # Rationale
            rationale_match = re.search(r'\*\*Rationale:\*\*\s*([^\n]+)', response_text)
            if rationale_match:
                parsed['rationale'] = rationale_match.group(1).strip()
            
            # Outcome explanations
            outcome_levels = [
                'Critical Failure',
                'Failure',
                'Moderate Success',
                'Good Success',
                'Excellent Success',
                'Exceptional Success'
            ]
            
            for level in outcome_levels:
                level_key = level.lower().replace(' ', '_')
                
                # Find the section for this outcome level
                pattern = rf'\*\*{re.escape(level)}:\*\*\s*\n(.*?)(?=\*\*[^*]+:\*\*|$)'
                match = re.search(pattern, response_text, re.DOTALL)
                
                if match:
                    section_text = match.group(1).strip()
                    
                    # Extract narrative and mechanical effect
                    narrative_match = re.search(r'- Narrative:\s*([^\n]+)', section_text)
                    mechanical_match = re.search(r'- Mechanical Effect:\s*([^\n]+)', section_text)
                    
                    parsed['outcome_explanation'][level_key] = {
                        'narrative': narrative_match.group(1).strip() if narrative_match else '',
                        'mechanical_effect': mechanical_match.group(1).strip() if mechanical_match else ''
                    }
            
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            # Return partial parse
        
        return parsed


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('openai', config)
        self.client = OpenAI(api_key=config['api_key'])
    
    async def generate_response(self, task: BenchmarkTask) -> ModelResponse:
        """Generate a response using OpenAI API."""
        start_time = time.time()
        
        try:
            prompt = self.create_prompt(task)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert tabletop RPG game master specializing in the Aeonisk YAGS system."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000,
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            raw_response = response.choices[0].message.content
            
            # Parse the response
            parsed_response = self.parse_response(raw_response, task)
            
            return ModelResponse(
                task_id=task.task_id,
                model_name=self.model_name,
                provider=self.name,
                response_time=response_time,
                token_count=response.usage.total_tokens if response.usage else None,
                raw_response=raw_response,
                parsed_response=parsed_response,
                **parsed_response
            )
        
        except Exception as e:
            logger.error(f"Error generating response with OpenAI: {e}")
            return ModelResponse(
                task_id=task.task_id,
                model_name=self.model_name,
                provider=self.name,
                response_time=time.time() - start_time,
                raw_response="",
                error=str(e),
                successful_parse=False
            )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('anthropic', config)
        self.api_key = config['api_key']
        self.base_url = config.get('base_url', 'https://api.anthropic.com')
    
    async def generate_response(self, task: BenchmarkTask) -> ModelResponse:
        """Generate a response using Anthropic API."""
        import sys
        start_time = time.time()
        max_credit_retries = 3
        backoff_times = [5, 15, 30]
        attempt = 0
        while True:
            try:
                prompt = self.create_prompt(task)
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
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
                        try:
                            response_data = await response.json()
                        except Exception as json_exc:
                            raw_text = await response.text()
                            logger.error(f"Anthropic API non-JSON response (status {response.status}): {raw_text}")
                            logger.error(f"Anthropic API headers: {dict(response.headers)}")
                            print(f"\n[Anthropic DEBUG] Non-JSON response (status {response.status})\nHeaders: {dict(response.headers)}\nBody: {raw_text}\n", file=sys.stderr)
                            error_msg = f"Non-JSON response (status {response.status}): {raw_text} | JSON error: {json_exc} | Headers: {dict(response.headers)}"
                            raise Exception(error_msg)
                response_time = time.time() - start_time
                if response.status == 200:
                    raw_response = response_data['content'][0]['text']
                    parsed_response = self.parse_response(raw_response, task)
                    return ModelResponse(
                        task_id=task.task_id,
                        model_name=self.model_name,
                        provider=self.name,
                        response_time=response_time,
                        token_count=response_data.get('usage', {}).get('total_tokens'),
                        raw_response=raw_response,
                        parsed_response=parsed_response,
                        **parsed_response
                    )
                else:
                    error_msg = response_data.get('error', {}).get('message', '')
                    logger.error(f"Anthropic API error (status {response.status}): {error_msg} | Response: {response_data}")
                    print(f"\n[Anthropic DEBUG] Error response (status {response.status})\nHeaders: {dict(response.headers)}\nBody: {response_data}\n", file=sys.stderr)
                    if not error_msg:
                        error_msg = f"Empty error message. Status: {response.status}, Headers: {dict(response.headers)}, Body: {response_data}"
                        print(f"[Anthropic DEBUG] WARNING: Empty error message!\n", file=sys.stderr)
                    if 'credit balance is too low' in error_msg.lower():
                        if attempt < max_credit_retries:
                            wait_time = backoff_times[attempt] if attempt < len(backoff_times) else backoff_times[-1]
                            print(f"[Anthropic API] Credit balance too low. Retrying in {wait_time} seconds...", file=sys.stderr)
                            await asyncio.sleep(wait_time)
                            attempt += 1
                            continue
                        else:
                            print("\n[Anthropic API] Credit balance too low. Please top up your account and press Enter to retry...", file=sys.stderr)
                            input()
                            attempt = 0
                            continue
                    raise Exception(f"API Error (status {response.status}): {error_msg}")
            except Exception as e:
                # Only handle credit error with special logic, otherwise fail as before
                if 'credit balance is too low' in str(e).lower():
                    if attempt < max_credit_retries:
                        wait_time = backoff_times[attempt] if attempt < len(backoff_times) else backoff_times[-1]
                        print(f"[Anthropic API] Credit balance too low. Retrying in {wait_time} seconds...", file=sys.stderr)
                        await asyncio.sleep(wait_time)
                        attempt += 1
                        continue
                    else:
                        print("\n[Anthropic API] Credit balance too low. Please top up your account and press Enter to retry...", file=sys.stderr)
                        input()
                        attempt = 0
                        continue
                logger.error(f"Error generating response with Anthropic: {e}")
                print(f"[Anthropic DEBUG] Exception: {e}", file=sys.stderr)
                return ModelResponse(
                    task_id=task.task_id,
                    model_name=self.model_name,
                    provider=self.name,
                    response_time=time.time() - start_time,
                    raw_response="",
                    error=str(e) if str(e) else "Unknown error in AnthropicProvider (no message)",
                    successful_parse=False
                )


class LocalProvider(LLMProvider):
    """Local/Self-hosted model provider (e.g., Ollama, vLLM)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('local', config)
        self.base_url = config.get('base_url', 'http://localhost:11434')
        self.endpoint = config.get('endpoint', '/api/generate')
    
    async def generate_response(self, task: BenchmarkTask) -> ModelResponse:
        """Generate a response using local model API."""
        start_time = time.time()
        
        try:
            prompt = self.create_prompt(task)
            
            data = {
                'model': self.model_name,
                'prompt': prompt,
                'options': {
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_tokens': 2000
                }
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f'{self.base_url}{self.endpoint}', json=data) as response:
                    response_data = await response.json()
            
            response_time = time.time() - start_time
            
            if response.status == 200:
                raw_response = response_data.get('response', '')
                parsed_response = self.parse_response(raw_response, task)
                
                return ModelResponse(
                    task_id=task.task_id,
                    model_name=self.model_name,
                    provider=self.name,
                    response_time=response_time,
                    raw_response=raw_response,
                    parsed_response=parsed_response,
                    **parsed_response
                )
            else:
                error_msg = response_data.get('error', 'Unknown error')
                raise Exception(f"API Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error generating response with local model: {e}")
            return ModelResponse(
                task_id=task.task_id,
                model_name=self.model_name,
                provider=self.name,
                response_time=time.time() - start_time,
                raw_response="",
                error=str(e),
                successful_parse=False
            )


class ProviderFactory:
    """Factory for creating LLM providers."""
    
    @staticmethod
    def create_provider(provider_type: str, config: Dict[str, Any]) -> LLMProvider:
        """Create a provider based on type and configuration."""
        if provider_type == 'openai':
            return OpenAIProvider(config)
        elif provider_type == 'anthropic':
            return AnthropicProvider(config)
        elif provider_type == 'local':
            return LocalProvider(config)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available provider types."""
        return ['openai', 'anthropic', 'local']


class ModelManager:
    """Manager for multiple LLM providers."""
    
    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {}
        self.semaphore = asyncio.Semaphore(5)  # Limit concurrent requests
    
    def add_provider(self, provider_id: str, provider: LLMProvider):
        """Add a provider to the manager."""
        self.providers[provider_id] = provider
        logger.info(f"Added provider {provider_id}: {provider.name} - {provider.model_name}")
    
    def configure_from_config(self, models_config: List[Dict[str, Any]]):
        """Configure providers from configuration list."""
        for model_config in models_config:
            provider_type = model_config.get('provider', 'openai')
            provider_id = model_config.get('id', f"{provider_type}_{model_config.get('model', 'default')}")
            
            try:
                provider = ProviderFactory.create_provider(provider_type, model_config)
                self.add_provider(provider_id, provider)
            except Exception as e:
                logger.error(f"Failed to configure provider {provider_id}: {e}")
    
    async def generate_response(self, provider_id: str, task: BenchmarkTask) -> ModelResponse:
        """Generate a response using a specific provider."""
        async with self.semaphore:
            if provider_id not in self.providers:
                raise ValueError(f"Provider {provider_id} not found")
            
            provider = self.providers[provider_id]
            return await provider.generate_response(task)
    
    async def generate_responses_parallel(self, task: BenchmarkTask) -> Dict[str, ModelResponse]:
        """Generate responses from all providers in parallel."""
        tasks = []
        for provider_id in self.providers.keys():
            task_coro = self.generate_response(provider_id, task)
            tasks.append((provider_id, task_coro))
        
        results = {}
        for provider_id, task_coro in tasks:
            try:
                response = await task_coro
                results[provider_id] = response
            except Exception as e:
                logger.error(f"Error generating response from {provider_id}: {e}")
                results[provider_id] = ModelResponse(
                    task_id=task.task_id,
                    model_name=self.providers[provider_id].model_name,
                    provider=provider_id,
                    response_time=0,
                    raw_response="",
                    error=str(e),
                    successful_parse=False
                )
        
        return results
    
    def get_provider_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all configured providers."""
        info = {}
        for provider_id, provider in self.providers.items():
            info[provider_id] = {
                'name': provider.name,
                'model_name': provider.model_name,
                'timeout': provider.timeout,
                'max_retries': provider.max_retries
            }
        return info