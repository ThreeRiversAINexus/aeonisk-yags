#!/usr/bin/env python3
"""
Simple test script to verify batch proxy provider works.
"""

import asyncio
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.aeonisk.multiagent.llm_provider import LLMConfig
from scripts.aeonisk.multiagent.llm_batch_provider import BatchProxyProvider
from pydantic import BaseModel


class SimpleResponse(BaseModel):
    """Simple test response."""
    greeting: str
    number: int


async def test_batch_proxy():
    """Test batch proxy with a simple request."""
    print("Testing BatchProxyProvider...")

    # Create provider
    config = LLMConfig(
        provider="batch_proxy",
        model="gpt-4o-mini",  # Try cheaper model first
        temperature=0.7,
        extra_params={
            'underlying_provider': 'openai',
            'use_proxy': True,
            'proxy_url': 'http://localhost:8000',
            'proxy_priority': 'normal',
            'proxy_strategy': 'auto'
        }
    )

    provider = BatchProxyProvider(config)

    # Check proxy health
    print("\n1. Checking proxy health...")
    health = provider.health_check()
    print(f"   Proxy status: {health}")

    if not health['reachable']:
        print("   ❌ Proxy not reachable! Start proxy first:")
        print("   cd ../aeonisk-transmedia-pipeline && python main.py proxy-start")
        return False

    # Test unstructured generation
    print("\n2. Testing unstructured generation...")
    try:
        response = await provider.generate(
            prompt="Say hello and count to 3",
            system_prompt="You are a helpful assistant.",
            max_tokens=50
        )
        print(f"   ✓ Response: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

    # Test structured generation
    print("\n3. Testing structured generation...")
    try:
        result = await provider.generate_structured(
            prompt="Greet me and provide the number 42",
            result_type=SimpleResponse,
            system_prompt="You are a helpful assistant.",
            max_tokens=100
        )
        print(f"   ✓ Structured result: greeting='{result.greeting}', number={result.number}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_batch_proxy())
    sys.exit(0 if success else 1)
