"""
Unit tests for bond formation validation.

Tests cover:
- Bond limit enforcement (max 3, Freeborn max 1)
- Void score prerequisites (both participants must have Void < 7)
- Witnessed requirement validation
- Duplicate bond prevention
- Bond formation validation function
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.shared_types import Bond, BondType, BondStatus, BondTargetType


class TestBondLimitValidation:
    """Test bond limit enforcement."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_character_can_form_bond_when_under_limit(self):
        """Character with 2 bonds can form a third (max 3)."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
            Bond(bond_id="bond_002", character_a="Alice", character_b="Dana", bond_type=BondType.PASSION, status=BondStatus.ACTIVE, formed_round=1, witnessed_by=["Eve"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Frank",
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Bob"]
        )

        assert result['valid'] is True
        assert 'bond_limit' not in result.get('errors', [])

    def test_character_cannot_exceed_bond_limit(self):
        """Character with 3 bonds cannot form a fourth."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
            Bond(bond_id="bond_002", character_a="Alice", character_b="Dana", bond_type=BondType.PASSION, status=BondStatus.ACTIVE, formed_round=1, witnessed_by=["Eve"]),
            Bond(bond_id="bond_003", character_a="Alice", character_b="Frank", bond_type=BondType.FACTION, status=BondStatus.ACTIVE, formed_round=2, witnessed_by=["George"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Helen",
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Bob"]
        )

        assert result['valid'] is False
        assert 'bond_limit' in result['errors']
        assert 'maximum of 3 bonds' in result['errors']['bond_limit'].lower()

    def test_freeborn_cannot_exceed_one_bond_limit(self):
        """Freeborn character with 1 bond cannot form a second."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Kaelen", character_b="Automata Unit-7", bond_type=BondType.PASSION, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=[], bond_target_type=BondTargetType.OBJECT, codex_registered=False),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Kaelen",
            target_name="New Friend",
            character_bonds=character_bonds,
            character_void=4,
            target_void=3,
            origin="freeborn",
            witnesses=["Someone"]
        )

        assert result['valid'] is False
        assert 'bond_limit' in result['errors']
        assert 'freeborn' in result['errors']['bond_limit'].lower()
        assert 'maximum of 1 bond' in result['errors']['bond_limit'].lower()

    def test_freeborn_can_form_first_bond(self):
        """Freeborn character with no bonds can form their first."""
        result = self.mechanics.validate_bond_formation(
            character_name="Kaelen",
            target_name="Companion",
            character_bonds=[],
            character_void=3,
            target_void=2,
            origin="freeborn",
            witnesses=["Witness"]
        )

        assert result['valid'] is True

    def test_dormant_and_severed_bonds_still_count_toward_limit(self):
        """Dormant and severed bonds still count toward the 3-bond limit."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.DORMANT, formed_round=0, witnessed_by=["Charlie"]),
            Bond(bond_id="bond_002", character_a="Alice", character_b="Dana", bond_type=BondType.PASSION, status=BondStatus.SEVERED, formed_round=1, witnessed_by=["Eve"]),
            Bond(bond_id="bond_003", character_a="Alice", character_b="Frank", bond_type=BondType.FACTION, status=BondStatus.ACTIVE, formed_round=2, witnessed_by=["George"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Helen",
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Bob"]
        )

        assert result['valid'] is False
        assert 'bond_limit' in result['errors']


class TestVoidPrerequisiteValidation:
    """Test void score prerequisite checks."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_both_participants_void_below_7_allows_bond(self):
        """Characters with Void < 7 can form bonds."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=6,  # Below threshold
            target_void=5,     # Below threshold
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is True

    def test_character_void_7_or_higher_prevents_bond(self):
        """Character with Void ≥ 7 cannot form new bonds."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=7,  # At threshold
            target_void=3,
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is False
        assert 'void_too_high' in result['errors']
        assert 'alice' in result['errors']['void_too_high'].lower()

    def test_target_void_7_or_higher_prevents_bond(self):
        """Target with Void ≥ 7 cannot form new bonds."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=3,
            target_void=8,  # Above threshold
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is False
        assert 'void_too_high' in result['errors']
        assert 'bob' in result['errors']['void_too_high'].lower()

    def test_both_participants_high_void_prevents_bond(self):
        """Both participants with Void ≥ 7 cannot form bonds."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=9,
            target_void=8,
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is False
        assert 'void_too_high' in result['errors']


class TestWitnessedRequirementValidation:
    """Test witnessed requirement validation."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_bond_formation_with_witness_is_valid(self):
        """Bond formation with at least one witness is valid."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is True

    def test_bond_formation_with_multiple_witnesses_is_valid(self):
        """Bond formation with multiple witnesses is valid."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Charlie", "Dana", "Eve"]
        )

        assert result['valid'] is True

    def test_bond_formation_without_witness_generates_warning(self):
        """Bond formation without witness generates warning (but may be valid for taboo bonds)."""
        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=[],
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=[]
        )

        # Implementation choice: either valid with warning, or invalid
        # For now, let's say it's valid but generates a warning
        assert 'no_witness_warning' in result.get('warnings', {})


class TestDuplicateBondPrevention:
    """Test duplicate bond prevention."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_cannot_form_duplicate_bond_with_same_character(self):
        """Cannot form a bond with someone you're already bonded to."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",  # Already bonded
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Dana"]
        )

        assert result['valid'] is False
        assert 'duplicate_bond' in result['errors']

    def test_can_form_bond_with_different_character(self):
        """Can form bond with character not already bonded."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Dana",  # Different character
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Charlie"]
        )

        assert result['valid'] is True

    def test_severed_bond_prevents_reformation(self):
        """Cannot re-form a severed bond (would need cleansing ritual)."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.PASSION, status=BondStatus.SEVERED, formed_round=0, witnessed_by=["Charlie"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Bob",
            character_bonds=character_bonds,
            character_void=3,
            target_void=2,
            origin="standard",
            witnesses=["Dana"]
        )

        assert result['valid'] is False
        assert 'severed_bond' in result['errors']


class TestComplexValidationScenarios:
    """Test complex validation scenarios with multiple constraints."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_multiple_validation_errors_all_reported(self):
        """All validation errors are reported, not just the first one."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
            Bond(bond_id="bond_002", character_a="Alice", character_b="Dana", bond_type=BondType.PASSION, status=BondStatus.ACTIVE, formed_round=1, witnessed_by=["Eve"]),
            Bond(bond_id="bond_003", character_a="Alice", character_b="Frank", bond_type=BondType.FACTION, status=BondStatus.ACTIVE, formed_round=2, witnessed_by=["George"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Helen",
            character_bonds=character_bonds,
            character_void=8,  # Too high
            target_void=2,
            origin="standard",
            witnesses=[]  # No witnesses
        )

        assert result['valid'] is False
        assert 'bond_limit' in result['errors']
        assert 'void_too_high' in result['errors']
        assert 'no_witness_warning' in result.get('warnings', {})

    def test_valid_bond_formation_all_checks_pass(self):
        """Valid bond formation passes all validation checks."""
        character_bonds = [
            Bond(bond_id="bond_001", character_a="Alice", character_b="Bob", bond_type=BondType.KINSHIP, status=BondStatus.ACTIVE, formed_round=0, witnessed_by=["Charlie"]),
        ]

        result = self.mechanics.validate_bond_formation(
            character_name="Alice",
            target_name="Dana",
            character_bonds=character_bonds,
            character_void=4,
            target_void=3,
            origin="standard",
            witnesses=["Bob", "Eve"]
        )

        assert result['valid'] is True
        assert len(result.get('errors', {})) == 0
