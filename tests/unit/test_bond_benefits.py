"""
Unit tests for bond mechanical benefits.

Tests cover:
- +2 ritual bonus when bonded participant assists/is present
- +1 Soak bonus when defending bonded partner
- Bond sacrifice mechanic (+5 Willpower, costs: +1 Void, +1 Soul Debt, -1 Empathy for scene)
- Benefits only apply to ACTIVE bonds (not Dormant/Severed/Void-Locked)
"""

import pytest
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
from scripts.aeonisk.multiagent.schemas.shared_types import Bond, BondType, BondStatus


class TestRitualBonusFromBond:
    """Test +2 ritual bonus when bonded participant is present."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_ritual_gets_plus_2_when_bonded_participant_present(self):
        """Ritual with bonded participant present gets +2 bonus."""
        alice_bonds = [
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

        bonus = self.mechanics.get_bond_ritual_bonus(
            caster_name="Alice",
            caster_bonds=alice_bonds,
            participants=["Bob", "Charlie"]  # Bob is bonded, Charlie is not
        )

        assert bonus == 2

    def test_ritual_no_bonus_when_bonded_participant_absent(self):
        """Ritual without bonded participant gets no bonus."""
        alice_bonds = [
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

        bonus = self.mechanics.get_bond_ritual_bonus(
            caster_name="Alice",
            caster_bonds=alice_bonds,
            participants=["Charlie", "Dana"]  # Bob not present
        )

        assert bonus == 0

    def test_ritual_no_bonus_when_caster_has_no_bonds(self):
        """Ritual with no bonds gets no bonus."""
        bonus = self.mechanics.get_bond_ritual_bonus(
            caster_name="Alice",
            caster_bonds=[],
            participants=["Bob", "Charlie"]
        )

        assert bonus == 0

    def test_ritual_bonus_only_applies_to_active_bonds(self):
        """Dormant/Severed/Void-Locked bonds don't give ritual bonus."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.DORMANT,  # Not active
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        bonus = self.mechanics.get_bond_ritual_bonus(
            caster_name="Alice",
            caster_bonds=alice_bonds,
            participants=["Bob"]
        )

        assert bonus == 0

    def test_ritual_bonus_with_multiple_bonded_participants(self):
        """Ritual with multiple bonded participants still gets +2 (not stacking)."""
        alice_bonds = [
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
                character_b="Charlie",
                bond_type=BondType.FACTION,
                status=BondStatus.ACTIVE,
                formed_round=1,
                witnessed_by=["Bob"]
            )
        ]

        bonus = self.mechanics.get_bond_ritual_bonus(
            caster_name="Alice",
            caster_bonds=alice_bonds,
            participants=["Bob", "Charlie"]  # Both bonded
        )

        # Design choice: +2 max, doesn't stack
        assert bonus == 2


class TestSoakBonusFromBond:
    """Test +1 Soak bonus when defending bonded partner."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_soak_plus_1_when_defending_bonded_partner(self):
        """Defender gets +1 Soak when target is bonded partner."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        bonus = self.mechanics.get_bond_soak_bonus(
            defender_name="Alice",
            defender_bonds=alice_bonds,
            attacker_target="Bob"  # Alice's bonded partner
        )

        assert bonus == 1

    def test_soak_no_bonus_when_target_not_bonded(self):
        """No Soak bonus when defending non-bonded character."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        bonus = self.mechanics.get_bond_soak_bonus(
            defender_name="Alice",
            defender_bonds=alice_bonds,
            attacker_target="Charlie"  # Not bonded
        )

        assert bonus == 0

    def test_soak_no_bonus_when_defender_is_target(self):
        """No Soak bonus when defender is being attacked directly."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        bonus = self.mechanics.get_bond_soak_bonus(
            defender_name="Alice",
            defender_bonds=alice_bonds,
            attacker_target="Alice"  # Alice is target, not defending someone else
        )

        assert bonus == 0

    def test_soak_bonus_only_applies_to_active_bonds(self):
        """Dormant/Severed/Void-Locked bonds don't give Soak bonus."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.SEVERED,  # Not active
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        bonus = self.mechanics.get_bond_soak_bonus(
            defender_name="Alice",
            defender_bonds=alice_bonds,
            attacker_target="Bob"
        )

        assert bonus == 0


class TestBondSacrificeMechanic:
    """Test bond sacrifice for +5 Willpower boost."""

    def setup_method(self):
        """Create mechanics engine for tests."""
        self.mechanics = MechanicsEngine()

    def test_bond_sacrifice_grants_plus_5_willpower(self):
        """Sacrificing a bond grants +5 to current Willpower roll."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=5
        )

        assert result['success'] is True
        assert result['willpower_bonus'] == 5
        assert result['bond_status'] == BondStatus.SEVERED

    def test_bond_sacrifice_applies_void_penalty(self):
        """Sacrificing a bond adds +1 Void."""
        alice_bonds = [
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

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=3
        )

        assert result['void_change'] == 1

    def test_bond_sacrifice_applies_soul_debt(self):
        """Sacrificing a bond adds +1 Soul Debt to severed partner."""
        alice_bonds = [
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

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=2
        )

        assert result['soul_debt_target'] == "Bob"
        assert result['soul_debt_change'] == 1

    def test_bond_sacrifice_applies_empathy_penalty_for_scene(self):
        """Sacrificing a bond applies -1 Empathy penalty for the scene."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=4
        )

        assert result['empathy_penalty'] == -1
        assert 'empathy_condition' in result
        assert result['empathy_condition']['duration'] == 'scene'

    def test_cannot_sacrifice_non_existent_bond(self):
        """Cannot sacrifice bond that doesn't exist."""
        alice_bonds = [
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

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Dana",  # No bond with Dana
            current_round=2
        )

        assert result['success'] is False
        assert 'no bond' in result['error'].lower()

    def test_cannot_sacrifice_already_severed_bond(self):
        """Cannot sacrifice a bond that's already severed."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.PASSION,
                status=BondStatus.SEVERED,  # Already severed
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=3
        )

        assert result['success'] is False
        assert 'already severed' in result['error'].lower()

    def test_can_sacrifice_dormant_bond(self):
        """Can sacrifice a Dormant bond (desperate move)."""
        alice_bonds = [
            Bond(
                bond_id="bond_001",
                character_a="Alice",
                character_b="Bob",
                bond_type=BondType.KINSHIP,
                status=BondStatus.DORMANT,  # Dormant but can be sacrificed
                formed_round=0,
                witnessed_by=["Charlie"]
            )
        ]

        result = self.mechanics.process_bond_sacrifice(
            character_name="Alice",
            character_bonds=alice_bonds,
            bond_target="Bob",
            current_round=5
        )

        assert result['success'] is True
        assert result['willpower_bonus'] == 5
        assert result['bond_status'] == BondStatus.SEVERED

    def test_bond_sacrifice_once_per_session_per_bond(self):
        """Can only sacrifice each bond once per session."""
        # This test verifies tracking logic exists
        # Implementation should track sacrificed_bonds_this_session
        pass  # Placeholder - implement when tracking is added to character state
