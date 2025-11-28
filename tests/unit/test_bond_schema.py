"""
Unit tests for Bond schema and related enums.

Tests cover:
- Bond model validation
- BondType enum (6 types)
- BondStatus enum (4 states)
- BondTargetType enum (character, object, entity)
- Character-character bonds (standard)
- Character-object bonds (rare/taboo)
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.schemas.shared_types import (
    Bond,
    BondType,
    BondStatus,
    BondTargetType,
)


class TestBondEnums:
    """Test Bond-related enums."""

    def test_bond_type_enum_has_six_types(self):
        """Bond types: Kinship, Ascendancy, Debt, Voidward, Passion, Faction."""
        assert len(BondType) == 6
        assert BondType.KINSHIP in BondType
        assert BondType.ASCENDANCY in BondType
        assert BondType.DEBT in BondType
        assert BondType.VOIDWARD in BondType
        assert BondType.PASSION in BondType
        assert BondType.FACTION in BondType

    def test_bond_status_enum_has_four_states(self):
        """Bond statuses: Active, Dormant, Severed, Void-Locked."""
        assert len(BondStatus) == 4
        assert BondStatus.ACTIVE in BondStatus
        assert BondStatus.DORMANT in BondStatus
        assert BondStatus.SEVERED in BondStatus
        assert BondStatus.VOID_LOCKED in BondStatus

    def test_bond_target_type_enum(self):
        """Bond target types: Character (default), Object (rare), Entity (rare)."""
        assert len(BondTargetType) == 3
        assert BondTargetType.CHARACTER in BondTargetType
        assert BondTargetType.OBJECT in BondTargetType
        assert BondTargetType.ENTITY in BondTargetType


class TestBondSchema:
    """Test Bond model validation."""

    def test_minimal_character_bond(self):
        """Minimal valid character-character bond."""
        bond = Bond(
            bond_id="bond_001",
            character_a="Sera Karsel",
            character_b="Thane Vael",
            bond_type=BondType.KINSHIP,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=["Kael Rift"],
        )

        assert bond.bond_id == "bond_001"
        assert bond.character_a == "Sera Karsel"
        assert bond.character_b == "Thane Vael"
        assert bond.bond_type == BondType.KINSHIP
        assert bond.status == BondStatus.ACTIVE
        assert bond.formed_round == 0
        assert bond.witnessed_by == ["Kael Rift"]
        assert bond.bond_target_type == BondTargetType.CHARACTER  # default
        assert bond.codex_registered is True  # default
        assert bond.narrative_description == ""  # default

    def test_full_character_bond_with_all_fields(self):
        """Full character bond with all optional fields."""
        bond = Bond(
            bond_id="bond_002",
            character_a="Kael Rift",
            character_b="Ash Nomad",
            bond_type=BondType.PASSION,
            status=BondStatus.ACTIVE,
            formed_round=3,
            witnessed_by=["Sera Karsel", "Thane Vael"],
            bond_target_type=BondTargetType.CHARACTER,
            codex_registered=True,
            narrative_description="Formed during desperate ritual to stabilize collapsing node",
        )

        assert bond.bond_id == "bond_002"
        assert bond.narrative_description == "Formed during desperate ritual to stabilize collapsing node"
        assert len(bond.witnessed_by) == 2

    def test_object_bond_rare_case(self):
        """Object bond (rare/taboo) - e.g., bonding with sanitation automata."""
        bond = Bond(
            bond_id="bond_003",
            character_a="Kaelen Freeborn",
            character_b="Sanitation Automata Unit-7",
            bond_type=BondType.PASSION,  # deviant bond type
            status=BondStatus.ACTIVE,
            formed_round=1,
            witnessed_by=[],  # no witnesses (taboo)
            bond_target_type=BondTargetType.OBJECT,
            codex_registered=False,  # not officially registered
            narrative_description="Formed in isolation, rejected by society",
        )

        assert bond.bond_target_type == BondTargetType.OBJECT
        assert bond.codex_registered is False
        assert bond.character_b == "Sanitation Automata Unit-7"

    def test_entity_bond_ai_spirit(self):
        """Entity bond with non-character sapient (AI, spirit, etc.)."""
        bond = Bond(
            bond_id="bond_004",
            character_a="Tech Shaman",
            character_b="Nexus AI Overseer",
            bond_type=BondType.ASCENDANCY,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=["Pantheon Arbiter"],
            bond_target_type=BondTargetType.ENTITY,
        )

        assert bond.bond_target_type == BondTargetType.ENTITY

    def test_dormant_bond_from_high_void(self):
        """Bond status changes to Dormant when Void ≥ 7."""
        bond = Bond(
            bond_id="bond_005",
            character_a="Corrupted PC",
            character_b="Allied NPC",
            bond_type=BondType.KINSHIP,
            status=BondStatus.DORMANT,  # set by check_bond_dormancy()
            formed_round=0,
            witnessed_by=["Witness"],
        )

        assert bond.status == BondStatus.DORMANT

    def test_severed_bond_from_sacrifice(self):
        """Bond severed via sacrifice mechanic."""
        bond = Bond(
            bond_id="bond_006",
            character_a="Desperate PC",
            character_b="Former Ally",
            bond_type=BondType.FACTION,
            status=BondStatus.SEVERED,
            formed_round=2,
            witnessed_by=["Faction Leader"],
            narrative_description="Sacrificed for +5 Willpower bonus in dire ritual",
        )

        assert bond.status == BondStatus.SEVERED

    def test_void_locked_bond_at_max_void(self):
        """Bond corrupted at Void = 10."""
        bond = Bond(
            bond_id="bond_007",
            character_a="Void-Corrupted",
            character_b="Tempest Entity",
            bond_type=BondType.VOIDWARD,
            status=BondStatus.VOID_LOCKED,
            formed_round=5,
            witnessed_by=[],
        )

        assert bond.status == BondStatus.VOID_LOCKED
        assert bond.bond_type == BondType.VOIDWARD

    def test_bond_requires_bond_id(self):
        """Bond must have bond_id."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                character_a="A",
                character_b="B",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=[],
            )
        assert "bond_id" in str(exc_info.value)

    def test_bond_requires_character_a(self):
        """Bond must have character_a."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_008",
                character_b="B",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=[],
            )
        assert "character_a" in str(exc_info.value)

    def test_bond_requires_character_b(self):
        """Bond must have character_b."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_009",
                character_a="A",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=[],
            )
        assert "character_b" in str(exc_info.value)

    def test_bond_requires_bond_type(self):
        """Bond must have bond_type."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_010",
                character_a="A",
                character_b="B",
                status=BondStatus.ACTIVE,
                formed_round=0,
                witnessed_by=[],
            )
        assert "bond_type" in str(exc_info.value)

    def test_bond_requires_status(self):
        """Bond must have status."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_011",
                character_a="A",
                character_b="B",
                bond_type=BondType.KINSHIP,
                formed_round=0,
                witnessed_by=[],
            )
        assert "status" in str(exc_info.value)

    def test_bond_requires_formed_round(self):
        """Bond must have formed_round."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_012",
                character_a="A",
                character_b="B",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                witnessed_by=[],
            )
        assert "formed_round" in str(exc_info.value)

    def test_bond_requires_witnessed_by_list(self):
        """Bond must have witnessed_by (can be empty list)."""
        with pytest.raises(ValidationError) as exc_info:
            Bond(
                bond_id="bond_013",
                character_a="A",
                character_b="B",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=0,
            )
        assert "witnessed_by" in str(exc_info.value)

    def test_witnessed_by_can_be_empty_list(self):
        """witnessed_by can be empty (taboo bonds, unwitnessed)."""
        bond = Bond(
            bond_id="bond_014",
            character_a="A",
            character_b="B",
            bond_type=BondType.PASSION,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=[],  # allowed
        )

        assert bond.witnessed_by == []

    def test_formed_round_can_be_zero(self):
        """formed_round=0 for pre-story bonds."""
        bond = Bond(
            bond_id="bond_015",
            character_a="A",
            character_b="B",
            bond_type=BondType.KINSHIP,
            status=BondStatus.ACTIVE,
            formed_round=0,  # pre-story
            witnessed_by=["C"],
        )

        assert bond.formed_round == 0

    def test_formed_round_negative_should_fail(self):
        """formed_round cannot be negative."""
        with pytest.raises(ValidationError):
            Bond(
                bond_id="bond_016",
                character_a="A",
                character_b="B",
                bond_type=BondType.KINSHIP,
                status=BondStatus.ACTIVE,
                formed_round=-1,  # invalid
                witnessed_by=[],
            )


class TestBondDefaults:
    """Test Bond schema default values."""

    def test_bond_target_type_defaults_to_character(self):
        """bond_target_type defaults to CHARACTER."""
        bond = Bond(
            bond_id="bond_017",
            character_a="A",
            character_b="B",
            bond_type=BondType.KINSHIP,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=[],
        )

        assert bond.bond_target_type == BondTargetType.CHARACTER

    def test_codex_registered_defaults_to_true(self):
        """codex_registered defaults to True."""
        bond = Bond(
            bond_id="bond_018",
            character_a="A",
            character_b="B",
            bond_type=BondType.KINSHIP,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=[],
        )

        assert bond.codex_registered is True

    def test_narrative_description_defaults_to_empty_string(self):
        """narrative_description defaults to empty string."""
        bond = Bond(
            bond_id="bond_019",
            character_a="A",
            character_b="B",
            bond_type=BondType.KINSHIP,
            status=BondStatus.ACTIVE,
            formed_round=0,
            witnessed_by=[],
        )

        assert bond.narrative_description == ""
