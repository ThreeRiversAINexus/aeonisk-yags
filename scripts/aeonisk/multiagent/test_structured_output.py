#!/usr/bin/env python3
"""
Test script for structured output using Pydantic AI.

Validates that our schemas work correctly with the LLM provider.

Usage:
    cd scripts/aeonisk
    source .venv/bin/activate
    python3 multiagent/test_structured_output.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from llm_provider import create_claude_provider, LLMConfig
from schemas.action_resolution import ActionResolution, MechanicalEffects, create_combat_resolution
from schemas.player_action import PlayerAction, ActionType
from schemas.shared_types import VoidChange, SoulcreditChange, ClockUpdate, SuccessTier

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_action_resolution():
    """Test DM action resolution with structured output."""
    logger.info("\n=== Testing ActionResolution Schema ===\n")

    # Create provider
    config = LLMConfig(
        provider="claude",
        model="claude-sonnet-4-5",
        max_tokens=2000,
        temperature=0.8,
        use_rate_limiter=False  # Disable for testing
    )
    provider = create_claude_provider(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        temperature=0.8
    )

    # Test prompt
    system_prompt = """You are a game master resolving a player action.

The player attempted: "Scan void corruption patterns using neural interface"
Character: Echo Resonance (Intelligence 5, Systems 4)
Roll: Intelligence 5 × Systems 4 + d20(14) = 34 vs DC 22
Result: SUCCESS, margin +12 (good success)

Generate a structured resolution with:
1. Vivid narration (500-800 chars) describing what happens
2. Success tier: "good"
3. Margin: 12
4. Mechanical effects: void change for Echo (+1 void from interface feedback)
"""

    user_prompt = "Resolve this action with structured output."

    try:
        # Call structured output generation
        logger.info("Calling Claude API with ActionResolution schema...")
        resolution: ActionResolution = await provider.generate_structured(
            prompt=user_prompt,
            result_type=ActionResolution,  # Note: internally converted to output_type for pydantic-ai 1.9.0
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.8
        )

        # Display results
        logger.info("✓ Structured output received!\n")
        print("=" * 80)
        print("NARRATION:")
        print("-" * 80)
        print(resolution.narration)
        print("\n" + "=" * 80)
        print(f"SUCCESS TIER: {resolution.success_tier}")
        print(f"MARGIN: {resolution.margin}")
        print("\n" + "=" * 80)
        print("MECHANICAL EFFECTS:")
        print("-" * 80)

        if resolution.effects.void_changes:
            print(f"Void Changes: {len(resolution.effects.void_changes)}")
            for vc in resolution.effects.void_changes:
                print(f"  - {vc.character_name}: {vc.amount:+d} ({vc.reason})")
        else:
            print("  No void changes")

        if resolution.effects.soulcredit_changes:
            print(f"Soulcredit Changes: {len(resolution.effects.soulcredit_changes)}")
            for sc in resolution.effects.soulcredit_changes:
                print(f"  - {sc.character_name}: {sc.amount:+d} ({sc.reason})")

        if resolution.effects.clock_updates:
            print(f"Clock Updates: {len(resolution.effects.clock_updates)}")
            for cu in resolution.effects.clock_updates:
                print(f"  - {cu.clock_name}: {cu.ticks:+d} ({cu.reason})")

        if resolution.effects.damage:
            print(f"Damage: {resolution.effects.damage.dealt} to {resolution.effects.damage.target}")

        if resolution.effects.conditions:
            print(f"Conditions: {len(resolution.effects.conditions)}")
            for cond in resolution.effects.conditions:
                print(f"  - {cond.name}: {cond.description}")

        print("=" * 80)

        logger.info("\n✅ ActionResolution test PASSED!")
        return True

    except Exception as e:
        logger.error(f"\n❌ ActionResolution test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_player_action():
    """Test player action declaration with structured output."""
    logger.info("\n=== Testing PlayerAction Schema ===\n")

    # Create provider
    provider = create_claude_provider(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        temperature=0.7
    )

    # Test prompt
    system_prompt = """You are a player agent declaring an action.

Character: Ash Vex (Willpower 6, Astral Arts 5)
Situation: Void corruption spreading from failed containment breach
Available actions: ritual cleansing, technical containment, tactical retreat

Choose the most appropriate action and provide structured declaration:
- Intent: Clear description of what you're doing
- Description: Narrative context (50-200 chars)
- Attribute + Skill
- Difficulty estimate with justification
- Action type
"""

    user_prompt = "Declare your action with structured output."

    try:
        logger.info("Calling Claude API with PlayerAction schema...")
        action: PlayerAction = await provider.generate_structured(
            prompt=user_prompt,
            result_type=PlayerAction,
            system_prompt=system_prompt,
            max_tokens=1000,
            temperature=0.7
        )

        # Display results
        logger.info("✓ Structured output received!\n")
        print("=" * 80)
        print("PLAYER ACTION DECLARATION:")
        print("-" * 80)
        print(f"Character: {action.character_name}")
        print(f"Intent: {action.intent}")
        print(f"Description: {action.description}")
        print(f"\nMechanics:")
        print(f"  Attribute: {action.attribute}")
        print(f"  Skill: {action.skill or 'None (raw attribute)'}")
        print(f"  DC Estimate: {action.difficulty_estimate}")
        print(f"  Justification: {action.difficulty_justification}")
        print(f"  Action Type: {action.action_type}")

        if action.target:
            print(f"  Target: {action.target}")

        if action.is_ritual:
            print(f"\nRitual Components:")
            print(f"  Has Tool: {action.has_primary_tool}")
            print(f"  Has Offering: {action.has_offering}")
            if action.ritual_components:
                print(f"  Components: {action.ritual_components}")

        print("=" * 80)
        print(f"\nSummary: {action.get_summary()}")
        print("=" * 80)

        logger.info("\n✅ PlayerAction test PASSED!")
        return True

    except Exception as e:
        logger.error(f"\n❌ PlayerAction test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_manual_schema_creation():
    """Test creating schemas manually to verify structure."""
    logger.info("\n=== Testing Manual Schema Creation ===\n")

    try:
        # Create a combat resolution manually
        resolution = create_combat_resolution(
            narration="Ash's void beam strikes true, searing through the scanner's optical array. "
                     "Crystalline fragments scatter as the device staggers back, sparking.",
            margin=12,
            target="Void Scanner Alpha",
            base_damage=15,
            soak=8,
            dealt=7
        )

        print("Manual Combat Resolution:")
        print(f"  Narration: {resolution.narration[:100]}...")
        print(f"  Success: {resolution.success_tier}")
        print(f"  Damage: {resolution.effects.damage.dealt} to {resolution.effects.damage.target}")

        # Create a player action manually
        action = PlayerAction(
            intent="Analyze void corruption patterns",
            description="Using neural interface to map void resonance frequencies and identify source",
            attribute="Intelligence",
            skill="Systems",
            difficulty_estimate=20,
            difficulty_justification="Complex technical analysis under time pressure",
            action_type=ActionType.TECHNICAL,
            character_name="Echo Resonance",
            agent_id="player_echo"
        )

        print(f"\nManual Player Action:")
        print(f"  {action.get_summary()}")

        # Test validation
        legacy_dict = action.to_legacy_dict()
        print(f"\nLegacy dict keys: {list(legacy_dict.keys())}")

        logger.info("\n✅ Manual schema creation test PASSED!")
        return True

    except Exception as e:
        logger.error(f"\n❌ Manual schema creation test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("STRUCTURED OUTPUT TEST SUITE")
    logger.info("=" * 80)

    # Manual schema test (no API calls)
    test1_passed = await test_manual_schema_creation()

    # Ask user if they want to run API tests (costs money)
    print("\n" + "=" * 80)
    response = input("Run API tests? (costs ~$0.02, requires ANTHROPIC_API_KEY) [y/N]: ").strip().lower()

    if response in ['y', 'yes']:
        test2_passed = await test_action_resolution()
        test3_passed = await test_player_action()

        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY:")
        print("=" * 80)
        print(f"Manual schema creation: {'✅ PASS' if test1_passed else '❌ FAIL'}")
        print(f"ActionResolution API: {'✅ PASS' if test2_passed else '❌ FAIL'}")
        print(f"PlayerAction API: {'✅ PASS' if test3_passed else '❌ FAIL'}")
        print("=" * 80)

        if all([test1_passed, test2_passed, test3_passed]):
            logger.info("\n🎉 ALL TESTS PASSED! Structured output system working correctly.")
            return 0
        else:
            logger.error("\n⚠️  Some tests failed. Review errors above.")
            return 1
    else:
        print("\nSkipping API tests.")
        print(f"Manual schema test: {'✅ PASS' if test1_passed else '❌ FAIL'}")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
