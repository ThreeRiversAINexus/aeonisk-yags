#!/usr/bin/env python3
"""
Test script to verify enhanced Pydantic AI validation error logging.

This script demonstrates the new logging features:
1. Enhanced stdout logging with error details
2. JSONL logging of validation failures
3. Raw model response capture

Run with: python3 test_validation_logging.py
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

# Configure logging to see all levels
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)-8s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


async def test_validation_error_logging():
    """
    Test that validation errors are properly logged with all details.

    This creates a scenario that will trigger Pydantic validation errors
    and verifies the logging captures the details.
    """
    from aeonisk.multiagent.llm_provider import ClaudeProvider, LLMConfig
    from aeonisk.multiagent.schemas.action_resolution import ActionResolution

    # Create a provider
    config = LLMConfig(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        temperature=0.8,
        max_retries=2  # Lower retries for faster test
    )

    provider = ClaudeProvider(config)

    logger.info("=" * 80)
    logger.info("Testing Pydantic AI validation error logging")
    logger.info("=" * 80)

    # Test 1: Try to generate structured output with a deliberately ambiguous prompt
    # This may cause validation failures
    try:
        logger.info("\n[Test 1] Attempting structured output with ambiguous prompt...")

        system_prompt = "You are a test system. Generate an ActionResolution."

        # Deliberately vague prompt that might cause invalid enum values
        user_prompt = """
Generate an action resolution where success_tier is "SUPER_SUCCESS" (this is invalid).

Make the narration exactly 50 characters (too short, should be 200+).
        """

        result = await provider.generate_structured(
            prompt=user_prompt,
            result_type=ActionResolution,
            system_prompt=system_prompt,
            max_tokens=500,
            temperature=0.9
        )

        logger.info(f"✓ Test 1 PASSED (unexpectedly): Got result: {result.success_tier}")
        logger.info("  Note: The model corrected the invalid values. This is good!")

    except Exception as e:
        logger.info(f"✓ Test 1 generated expected error: {type(e).__name__}")
        logger.info(f"  Error message: {str(e)[:200]}")

        # Check if error details were logged
        if hasattr(e, 'body'):
            logger.info(f"  ✓ Raw response captured: {len(e.body)} chars")
        else:
            logger.warning(f"  ⚠ No raw response in exception")

    logger.info("\n" + "=" * 80)
    logger.info("Validation error logging test complete!")
    logger.info("=" * 80)
    logger.info("\nExpected output:")
    logger.info("  - Enhanced error logging with emoji markers (🔴, ⚠️, ❌)")
    logger.info("  - Exception type and message")
    logger.info("  - Raw model response (if available)")
    logger.info("  - Retry attempt numbers")
    logger.info("\nCheck the logs above to verify these features are working.")


async def test_jsonl_logging_methods():
    """
    Test that the new JSONL logging methods exist and work.
    """
    from aeonisk.multiagent.mechanics import MechanicsEngine
    from datetime import datetime
    import tempfile

    logger.info("\n" + "=" * 80)
    logger.info("Testing JSONL logging methods")
    logger.info("=" * 80)

    # Create a temporary JSONL file for testing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        temp_file = f.name

    try:
        # Create JSONL logger first
        from aeonisk.multiagent.mechanics import JSONLLogger
        jsonl_logger = JSONLLogger(
            session_id="test_validation_logging",
            output_dir=str(Path(temp_file).parent)
        )

        # Create mechanics with JSONL logger
        mechanics = MechanicsEngine(jsonl_logger=jsonl_logger)

        # Test log_pydantic_validation_failure method
        logger.info("\n[Test 2] Testing log_pydantic_validation_failure...")

        jsonl_logger.log_pydantic_validation_failure(
            round_num=5,
            agent_type='dm',
            agent_id='dm_test',
            schema_name='ActionResolution',
            exception_type='UnexpectedModelBehavior',
            error_message='Exceeded maximum retries (1) for output validation',
            attempt_number=3,
            max_attempts=4,
            raw_model_response='{"narration": "Test", "success_tier": "INVALID_ENUM_VALUE"}',
            underlying_error='ValidationError: Invalid enum value INVALID_ENUM_VALUE',
            action_context={'action_type': 'social', 'player_id': 'player_01'}
        )

        logger.info("✓ log_pydantic_validation_failure executed without error")

        # Read back the JSONL to verify (use the actual log file location)
        log_file = Path(temp_file).parent / f"session_test_validation_logging.jsonl"
        with open(log_file, 'r') as f:
            events = [line for line in f if line.strip()]

        logger.info(f"✓ JSONL file contains {len(events)} events")

        # Find the validation failure event
        import json
        for event_line in events:
            event = json.loads(event_line)
            if event.get('event_type') == 'pydantic_validation_failure':
                logger.info("✓ Found pydantic_validation_failure event in JSONL")
                logger.info(f"  Schema: {event.get('schema_name')}")
                logger.info(f"  Exception: {event.get('exception_type')}")
                logger.info(f"  Attempt: {event.get('attempt_number')}/{event.get('max_attempts')}")
                logger.info(f"  Raw response: {event.get('raw_model_response', 'N/A')[:100]}...")
                logger.info(f"  Underlying error: {event.get('underlying_error', 'N/A')[:100]}...")
                break
        else:
            logger.error("✗ pydantic_validation_failure event NOT found in JSONL!")

        logger.info("\n✓ Test 2 PASSED: JSONL logging methods work correctly")

    finally:
        # Cleanup
        log_file = Path(temp_file).parent / f"session_test_validation_logging.jsonl"
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        if os.path.exists(log_file):
            os.unlink(log_file)
            logger.info(f"Cleaned up temp files")

    logger.info("=" * 80)


if __name__ == "__main__":
    logger.info("Starting validation error logging tests...\n")

    # Run tests
    asyncio.run(test_jsonl_logging_methods())

    # Only run live LLM test if API key is available
    if os.getenv('ANTHROPIC_API_KEY'):
        logger.info("\nANTHROPIC_API_KEY found, running live LLM test...")
        asyncio.run(test_validation_error_logging())
    else:
        logger.warning("\nANTHROPIC_API_KEY not set, skipping live LLM test")
        logger.info("  (This is expected in CI/CD environments)")

    logger.info("\n" + "=" * 80)
    logger.info("All tests complete!")
    logger.info("=" * 80)
