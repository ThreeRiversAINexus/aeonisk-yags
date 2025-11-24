"""
Unit tests for Echo-Calibrator rental support in attunement validation.

Tests that both purchased and rental Echo-Calibrators are recognized.
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.shared_state import SharedState
from scripts.aeonisk.multiagent.player import CharacterState
from scripts.aeonisk.multiagent.energy_economy import EnergyPurse, Seed, SeedType


@pytest.fixture
def mechanics():
    """Create a MechanicsEngine with SharedState."""
    shared_state = SharedState()
    return MechanicsEngine(shared_state=shared_state)


@pytest.fixture
def character_with_seed():
    """Create a character with a Raw Seed."""
    character = CharacterState(
        name="Test Character",
        faction="Test",
        attributes={"Willpower": 3, "Agility": 3},
        skills={"Attunement": 2, "Craft": 2},
        void_score=0,
        soulcredit=0,
        bonds=[],
        goals=[]
    )
    # Add Raw Seed
    character.energy_purse = EnergyPurse(grain=0, drip=2, spark=0, breath=0)
    character.energy_purse.add_seed(Seed(SeedType.RAW, origin="test"))

    # Initialize inventory
    character.inventory = {}

    return character


class TestEchoCalibratorPurchase:
    """Test purchased Echo-Calibrator recognition."""

    def test_purchased_echo_calibrator_accepted(self, mechanics, character_with_seed):
        """Test that purchased Echo-Calibrator is recognized."""
        character = character_with_seed
        character.inventory["Echo-Calibrator"] = 1  # Purchased item

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.has_echo_calibrator is True
        assert validation.failure_reason is None or "No Echo-Calibrator available" not in validation.failure_reason

    def test_no_echo_calibrator_rejected(self, mechanics, character_with_seed):
        """Test that missing Echo-Calibrator is rejected."""
        character = character_with_seed
        # No Echo-Calibrator in inventory

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is False
        assert "No Echo-Calibrator available" in validation.failure_reason


class TestEchoCalibratorSnakeCaseVariants:
    """Test snake_case inventory key variants (from session configs)."""

    def test_snake_case_echo_calibrator_accepted(self, mechanics, character_with_seed):
        """Test that snake_case 'echo_calibrator' key is recognized.

        This is the format used in session config inventory definitions.
        Bug found: session_config uses "echo_calibrator": 2 but validation
        only checked "Echo-Calibrator" (hyphen).
        """
        character = character_with_seed
        character.inventory["echo_calibrator"] = 3  # Session config format

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True, f"Expected valid but got: {validation.failure_reason}"
        assert validation.has_echo_calibrator is True
        assert validation.failure_reason is None or "No Echo-Calibrator available" not in (validation.failure_reason or "")

    def test_space_separated_echo_calibrator_accepted(self, mechanics, character_with_seed):
        """Test that space-separated 'Echo Calibrator' key is recognized.

        This is the display name format shown in console output.
        """
        character = character_with_seed
        character.inventory["Echo Calibrator"] = 1  # Display format (space, no hyphen)

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True, f"Expected valid but got: {validation.failure_reason}"
        assert validation.has_echo_calibrator is True


class TestEchoCalibratorRental:
    """Test rented Echo-Calibrator recognition."""

    def test_rental_echo_calibrator_accepted(self, mechanics, character_with_seed):
        """Test that rental Echo-Calibrator is recognized (config inventory_key format)."""
        character = character_with_seed
        character.inventory["echo_calibrator_rental"] = 1  # Rental item (inventory_key format)

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.has_echo_calibrator is True
        assert validation.failure_reason is None or "No Echo-Calibrator available" not in validation.failure_reason

    def test_rental_echo_calibrator_alternate_format_accepted(self, mechanics, character_with_seed):
        """Test that rental Echo-Calibrator is recognized (alternate display format)."""
        character = character_with_seed
        character.inventory["Echo Calibrator Rental"] = 1  # Rental item (display format)

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.has_echo_calibrator is True
        assert validation.failure_reason is None or "No Echo-Calibrator available" not in validation.failure_reason

    def test_both_purchased_and_rental_accepted(self, mechanics, character_with_seed):
        """Test that having both purchased and rental works."""
        character = character_with_seed
        character.inventory["Echo-Calibrator"] = 1  # Purchased
        character.inventory["Echo Calibrator Rental"] = 1  # Rental

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.has_echo_calibrator is True

    def test_zero_quantity_rejected(self, mechanics, character_with_seed):
        """Test that 0 quantity rental is rejected."""
        character = character_with_seed
        character.inventory["Echo Calibrator Rental"] = 0  # Used up

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=True
        )

        assert validation.is_valid is False
        assert "No Echo-Calibrator available" in validation.failure_reason


class TestEchoCalibratorWithoutFlag:
    """Test that Echo-Calibrator is not required when flag is False."""

    def test_no_calibrator_needed_when_not_requested(self, mechanics, character_with_seed):
        """Test that attunement works without Echo-Calibrator if not requested."""
        character = character_with_seed
        # No Echo-Calibrator in inventory

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            use_echo_calibrator=False  # Not using calibrator
        )

        # Should fail for other reasons (no altar), but NOT for missing calibrator
        if not validation.is_valid:
            assert "No Echo-Calibrator" not in validation.failure_reason
