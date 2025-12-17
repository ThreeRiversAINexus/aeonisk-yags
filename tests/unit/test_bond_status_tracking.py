"""
Unit tests for bond status tracking and automatic transitions.

Tests cover:
- Automatic Dormant transition when character Void ≥ 7
- Automatic Active restoration when Void drops below 7
- Void-Locked transition at Void = 10
- Bond status changes in check_bond_dormancy()
- Status tracking for all character bonds
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.shared_types import Bond, BondType, BondStatus


class TestVoidSevenDormancy:
    """Test automatic Dormant transition at Void ≥ 7."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_active_bonds_become_dormant_at_void_7(self):
        """ACTIVE bonds become DORMANT when character reaches Void 7."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=1,
                witnessed_by=["Eve"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6
        )

        # Both bonds should transition to DORMANT
        assert result['status_changed'] is True
        assert result['transitions'] == 2
        assert bonds[0].status == BondStatus.DORMANT
        assert bonds[1].status == BondStatus.DORMANT

    def test_active_bonds_become_dormant_above_void_7(self):
        """ACTIVE bonds become DORMANT when character has Void > 7."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.FACTION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=9,
            previous_void=8
        )

        assert bonds[0].status == BondStatus.DORMANT

    def test_no_transition_when_void_below_7(self):
        """No transition when Void is below 7."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=6,
            previous_void=5
        )

        assert result['status_changed'] is False
        assert bonds[0].status == BondStatus.ACTIVE

    def test_no_transition_when_void_stays_at_7(self):
        """No re-transition when Void stays at 7 (already transitioned)."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.DORMANT,  # Already dormant
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=7
        )

        assert result['status_changed'] is False


class TestVoidRecoveryReactivation:
    """Test bond reactivation when Void drops below 7."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_dormant_bonds_become_active_when_void_drops_below_7(self):
        """DORMANT bonds become ACTIVE when Void drops below 7."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.DORMANT,
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.PASSION,
                status=BondStatus.DORMANT,
                formed_round=1,
                witnessed_by=["Eve"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=6,  # Dropped from 7 to 6
            previous_void=7
        )

        assert result['status_changed'] is True
        assert result['reactivations'] == 2
        assert bonds[0].status == BondStatus.ACTIVE
        assert bonds[1].status == BondStatus.ACTIVE

    def test_only_dormant_bonds_reactivate(self):
        """Only DORMANT bonds reactivate, not SEVERED or VOID_LOCKED."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.DORMANT,  # Should reactivate
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.PASSION,
                status=BondStatus.SEVERED,  # Should NOT reactivate
                formed_round=1,
                witnessed_by=["Eve"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=5,
            previous_void=7
        )

        assert bonds[0].status == BondStatus.ACTIVE
        assert bonds[1].status == BondStatus.SEVERED  # Unchanged


class TestVoidTenLocking:
    """Test Void-Locked transition at Void = 10."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_all_bonds_become_void_locked_at_void_10(self):
        """All bonds (ACTIVE and DORMANT) become VOID_LOCKED at Void = 10."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.VOIDWARD,  # Ironically, even Voidward bonds get locked
                status=BondStatus.DORMANT,
                formed_round=1,
                witnessed_by=["Eve"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=10,
            previous_void=9
        )

        assert result['void_locked'] is True
        assert bonds[0].status == BondStatus.VOID_LOCKED
        assert bonds[1].status == BondStatus.VOID_LOCKED

    def test_severed_bonds_stay_severed_at_void_10(self):
        """SEVERED bonds remain SEVERED, not converted to VOID_LOCKED."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.PASSION,
                status=BondStatus.SEVERED,  # Should stay severed
                formed_round=1,
                witnessed_by=["Eve"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=10,
            previous_void=9
        )

        assert bonds[0].status == BondStatus.VOID_LOCKED
        assert bonds[1].status == BondStatus.SEVERED  # Unchanged

    def test_void_locked_bonds_stay_locked_when_void_drops(self):
        """VOID_LOCKED bonds do NOT revert when Void drops (permanent corruption)."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.VOID_LOCKED,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=8,  # Dropped from 10 to 8
            previous_void=10
        )

        # VOID_LOCKED is permanent
        assert bonds[0].status == BondStatus.VOID_LOCKED


class TestComplexStatusTransitions:
    """Test complex multi-transition scenarios."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_void_trajectory_6_to_7_to_6(self):
        """Void 6 → 7 (bonds Dormant) → 6 (bonds reactivate)."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        # Void 6 → 7 (become Dormant)
        result1 = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6
        )
        assert bonds[0].status == BondStatus.DORMANT

        # Void 7 → 6 (reactivate)
        result2 = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=6,
            previous_void=7
        )
        assert bonds[0].status == BondStatus.ACTIVE

    def test_void_trajectory_9_to_10_is_permanent(self):
        """Void 9 → 10 (bonds Void-Locked) → cannot recover."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.DORMANT,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        # Void 9 → 10 (Void-Locked)
        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=10,
            previous_void=9
        )
        assert bonds[0].status == BondStatus.VOID_LOCKED

        # Even if Void drops to 0, bond stays Void-Locked
        result2 = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=0,
            previous_void=10
        )
        assert bonds[0].status == BondStatus.VOID_LOCKED

    def test_mixed_bond_statuses_transition_correctly(self):
        """Different bond statuses transition independently."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,  # Will become Dormant
                formed_round=0,
                witnessed_by=["Charlie"]
            ),
            Bond(
                bond_id="bond_002",
                character_a="Alice",
                character_b="Dana",
                bond_type=BondType.PASSION,
                status=BondStatus.SEVERED,  # Stays Severed
                formed_round=1,
                witnessed_by=["Eve"]
            ),
            Bond(
                bond_id="bond_003",
                character_a="Alice",
                character_b="Frank",
                bond_type=BondType.FACTION,
                status=BondStatus.VOID_LOCKED,  # Stays Void-Locked
                formed_round=2,
                witnessed_by=["George"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6
        )

        assert bonds[0].status == BondStatus.DORMANT  # Changed
        assert bonds[1].status == BondStatus.SEVERED  # Unchanged
        assert bonds[2].status == BondStatus.VOID_LOCKED  # Unchanged
        assert result['transitions'] == 1  # Only one bond changed

    def test_no_bonds_returns_early(self):
        """Character with no bonds returns immediately."""
        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=[],
            current_void=10,
            previous_void=5
        )

        assert result['status_changed'] is False


class TestBondStatusChangeTracking:
    """Test tracking of status changes for JSONL logging."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_status_changes_include_character_and_bond_details(self):
        """Status changes include all details for logging."""
        bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.check_bond_dormancy(
            character_name="Alice",
            character_bonds=bonds,
            current_void=7,
            previous_void=6
        )

        # Should include details for JSONL logging
        assert 'changes' in result
        assert len(result['changes']) == 1
        change = result['changes'][0]
        assert change['bond_id'] == "bond_001"
        assert change['character_a'] == "Alice"
        assert change['character_b'] == "Bob"
        assert change['old_status'] == BondStatus.ACTIVE
        assert change['new_status'] == BondStatus.DORMANT
        assert change['reason'] == "void_threshold"
