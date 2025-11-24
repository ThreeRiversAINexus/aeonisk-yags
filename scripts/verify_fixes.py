#!/usr/bin/env python3
"""
Quick verification script for multi-target transfer and Echo-Calibrator rental fixes.

Run this to verify both fixes are working correctly:
    python3 scripts/verify_fixes.py
"""

import sys
sys.path.insert(0, 'scripts')

from aeonisk.multiagent.mechanics import MechanicsEngine
from aeonisk.multiagent.shared_state import SharedState
from aeonisk.multiagent.player import CharacterState
from aeonisk.multiagent.energy_economy import EnergyPurse, Seed, SeedType


def test_multi_target_transfer():
    """Test that multi-target transfers are properly rejected."""
    print("=" * 60)
    print("TEST 1: Multi-Target Transfer Validation")
    print("=" * 60)

    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)

    # Create sender
    sender = CharacterState(
        name="Ryn Thrace",
        faction="Test",
        attributes={"Willpower": 3},
        skills={},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[]
    )
    sender.energy_purse = EnergyPurse(grain=10, drip=50, spark=5, breath=20)
    sender.inventory = {}

    # Test comma-separated targets
    print("\n1. Testing comma-separated targets...")
    validation = mechanics.validate_transfer(
        sender_state=sender,
        transfer_target="Mira Solis, Sera Vex",
        transfer_currency={"drip": 10}
    )

    if not validation.is_valid and "Multi-target" in validation.failure_reason:
        print("   ✅ PASS: Comma-separated targets rejected")
        print(f"      Reason: {validation.failure_reason}")
    else:
        print("   ❌ FAIL: Should reject comma-separated targets")
        return False

    # Test semicolon-separated targets
    print("\n2. Testing semicolon-separated targets...")
    validation = mechanics.validate_transfer(
        sender_state=sender,
        transfer_target="Mira Solis; Sera Vex; Jace Kordell",
        transfer_currency={"drip": 10}
    )

    if not validation.is_valid and "Multi-target" in validation.failure_reason:
        print("   ✅ PASS: Semicolon-separated targets rejected")
        print(f"      Reason: {validation.failure_reason}")
    else:
        print("   ❌ FAIL: Should reject semicolon-separated targets")
        return False

    # Test with target IDs
    print("\n3. Testing semicolon-separated target IDs...")
    validation = mechanics.validate_transfer(
        sender_state=sender,
        transfer_target="tgt_abc123, tgt_def456",
        transfer_currency={"drip": 10}
    )

    if not validation.is_valid and "Multi-target" in validation.failure_reason:
        print("   ✅ PASS: Semicolon-separated target IDs rejected")
        print(f"      Reason: {validation.failure_reason}")
    else:
        print("   ❌ FAIL: Should reject semicolon-separated target IDs")
        return False

    print("\n✅ ALL MULTI-TARGET TRANSFER TESTS PASSED\n")
    return True


def test_echo_calibrator_rental():
    """Test that Echo-Calibrator rentals are recognized."""
    print("=" * 60)
    print("TEST 2: Echo-Calibrator Rental Recognition")
    print("=" * 60)

    shared_state = SharedState()
    mechanics = MechanicsEngine(shared_state=shared_state)

    # Create character with Raw Seed
    character = CharacterState(
        name="Mira Solis",
        faction="Test",
        attributes={"Willpower": 3, "Agility": 3},
        skills={"Attunement": 2},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[]
    )
    character.energy_purse = EnergyPurse(grain=0, drip=2, spark=0, breath=0)
    character.energy_purse.add_seed(Seed(SeedType.RAW, origin="test"))
    character.inventory = {}

    # Test 1: Purchased Echo-Calibrator
    print("\n1. Testing purchased Echo-Calibrator...")
    character.inventory = {"Echo-Calibrator": 1}
    validation = mechanics.validate_attunement(
        character_state=character,
        target_energy="drip",
        use_echo_calibrator=True
    )

    if validation.is_valid and validation.has_echo_calibrator:
        print("   ✅ PASS: Purchased Echo-Calibrator recognized")
    else:
        print("   ❌ FAIL: Should recognize purchased Echo-Calibrator")
        print(f"      Reason: {validation.failure_reason}")
        return False

    # Test 2: Rental Echo-Calibrator (config format: lowercase with underscores)
    print("\n2. Testing rental Echo-Calibrator (config format: echo_calibrator_rental)...")
    character.inventory = {"echo_calibrator_rental": 1}
    validation = mechanics.validate_attunement(
        character_state=character,
        target_energy="drip",
        use_echo_calibrator=True
    )

    if validation.is_valid and validation.has_echo_calibrator:
        print("   ✅ PASS: Rental Echo-Calibrator (config format) recognized")
    else:
        print("   ❌ FAIL: Should recognize rental Echo-Calibrator (config format)")
        print(f"      Reason: {validation.failure_reason}")
        return False

    # Test 3: Rental Echo-Calibrator (alternate format: with spaces)
    print("\n3. Testing rental Echo-Calibrator (alternate format: Echo Calibrator Rental)...")
    character.inventory = {"Echo Calibrator Rental": 1}
    validation = mechanics.validate_attunement(
        character_state=character,
        target_energy="drip",
        use_echo_calibrator=True
    )

    if validation.is_valid and validation.has_echo_calibrator:
        print("   ✅ PASS: Rental Echo-Calibrator (alternate format) recognized")
    else:
        print("   ❌ FAIL: Should recognize rental Echo-Calibrator (alternate format)")
        print(f"      Reason: {validation.failure_reason}")
        return False

    # Test 4: No Echo-Calibrator should fail
    print("\n4. Testing missing Echo-Calibrator...")
    character.inventory = {}
    validation = mechanics.validate_attunement(
        character_state=character,
        target_energy="drip",
        use_echo_calibrator=True
    )

    if not validation.is_valid and "No Echo-Calibrator available" in validation.failure_reason:
        print("   ✅ PASS: Missing Echo-Calibrator properly rejected")
        print(f"      Reason: {validation.failure_reason}")
    else:
        print("   ❌ FAIL: Should reject when Echo-Calibrator missing")
        return False

    print("\n✅ ALL ECHO-CALIBRATOR RENTAL TESTS PASSED\n")
    return True


def main():
    """Run all verification tests."""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  FIX VERIFICATION: Multi-Target & Echo-Calibrator  ".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    all_passed = True

    # Test 1: Multi-target transfers
    if not test_multi_target_transfer():
        all_passed = False

    # Test 2: Echo-Calibrator rentals
    if not test_echo_calibrator_rental():
        all_passed = False

    # Final result
    print("=" * 60)
    if all_passed:
        print("✅ ALL VERIFICATION TESTS PASSED")
        print("=" * 60)
        print()
        print("Both fixes are working correctly:")
        print("  1. Multi-target transfers (comma/semicolon) are rejected")
        print("  2. Echo-Calibrator rentals (3 formats) are recognized")
        print()
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        print()
        print("Please review the test output above for details.")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
