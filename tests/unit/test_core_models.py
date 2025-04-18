"""
Unit tests for the core models module.
"""

import pytest
from aeonisk.core.models import Character, Bond, Equipment


class TestCharacterModel:
    """Test suite for the Character model."""

    def test_character_initialization(self):
        """Test that a character can be initialized with default values."""
        character = Character(
            name="Test Character",
            concept="Test Concept"
        )
        
        assert character.name == "Test Character"
        assert character.concept == "Test Concept"
        assert character.void_score == 0
        assert character.soulcredit == 0
        assert character.bonds == []
        assert character.true_will is None
        assert character.equipment == []

    def test_character_with_custom_attributes(self):
        """Test that a character can be initialized with custom attributes."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            attributes={"Strength": 4, "Willpower": 5},
            skills={"Athletics": 3, "Astral_Arts": 4},
            void_score=2,
            soulcredit=3,
            bonds=[{"name": "Test Bond", "type": "Kinship"}],
            true_will="Test True Will",
            equipment=[{"name": "Test Equipment", "type": "Weapon"}]
        )
        
        assert character.name == "Test Character"
        assert character.concept == "Test Concept"
        assert character.attributes["Strength"] == 4
        assert character.attributes["Willpower"] == 5
        assert character.skills["Athletics"] == 3
        assert character.skills["Astral_Arts"] == 4
        assert character.void_score == 2
        assert character.soulcredit == 3
        assert len(character.bonds) == 1
        assert character.bonds[0]["name"] == "Test Bond"
        assert character.true_will == "Test True Will"
        assert len(character.equipment) == 1
        assert character.equipment[0]["name"] == "Test Equipment"

    def test_attunement_skill_default(self):
        """Test that the Attunement skill is available with a default value."""
        character = Character(
            name="Test Character",
            concept="Test Concept"
        )
        
        # Attunement should be in the default skills with a value of 2
        assert "Attunement" in character.skills
        assert character.skills["Attunement"] == 2

    def test_dreamwork_skill_default(self):
        """Test that the Dreamwork skill is available with a default value."""
        character = Character(
            name="Test Character",
            concept="Test Concept"
        )
        
        # Dreamwork should be in the default skills with a value of 2
        assert "Dreamwork" in character.skills
        assert character.skills["Dreamwork"] == 2

    def test_seed_tracking(self):
        """Test that a character can track raw and attuned Seeds."""
        # Create raw seeds with acquisition cycles
        raw_seed1 = {"id": "seed1", "acquisition_cycle": 1}
        raw_seed2 = {"id": "seed2", "acquisition_cycle": 2}
        raw_seed3 = {"id": "seed3", "acquisition_cycle": 3}
        
        character = Character(
            name="Test Character",
            concept="Test Concept",
            raw_seeds=[raw_seed1, raw_seed2, raw_seed3],
            attuned_seeds={"Spark": 1, "Grain": 4}
        )
        
        assert len(character.raw_seeds) == 3
        assert character.raw_seeds[0]["id"] == "seed1"
        assert character.raw_seeds[1]["id"] == "seed2"
        assert character.raw_seeds[2]["id"] == "seed3"
        assert character.raw_seeds[0]["acquisition_cycle"] == 1
        assert character.attuned_seeds["Spark"] == 1
        assert character.attuned_seeds["Grain"] == 4

    def test_seed_tracking_default(self):
        """Test that seed tracking has appropriate defaults."""
        character = Character(
            name="Test Character",
            concept="Test Concept"
        )
        
        assert character.raw_seeds == []
        assert character.attuned_seeds == {}

    def test_cycle_tracking(self):
        """Test that a character can track cycles."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            current_cycle=3
        )
        
        assert character.current_cycle == 3

    def test_cycle_tracking_default(self):
        """Test that cycle tracking has appropriate defaults."""
        character = Character(
            name="Test Character",
            concept="Test Concept"
        )
        
        assert character.current_cycle == 0

    def test_raw_seed_creation(self):
        """Test that a raw seed can be created with an acquisition cycle."""
        character = Character(
            name="Test Character",
            concept="Test Concept",
            current_cycle=5
        )
        
        # Add a new raw seed
        new_seed = {"id": "new_seed", "acquisition_cycle": character.current_cycle}
        character.raw_seeds.append(new_seed)
        
        assert len(character.raw_seeds) == 1
        assert character.raw_seeds[0]["id"] == "new_seed"
        assert character.raw_seeds[0]["acquisition_cycle"] == 5


class TestBondModel:
    """Test suite for the Bond model."""

    def test_bond_initialization(self):
        """Test that a bond can be initialized."""
        bond = Bond(
            name="Test Bond",
            type="Kinship"
        )
        
        assert bond.name == "Test Bond"
        assert bond.type == "Kinship"
        assert bond.strength == 1
        assert bond.description is None

    def test_bond_with_custom_attributes(self):
        """Test that a bond can be initialized with custom attributes."""
        bond = Bond(
            name="Test Bond",
            type="Kinship",
            strength=3,
            description="Test Description"
        )
        
        assert bond.name == "Test Bond"
        assert bond.type == "Kinship"
        assert bond.strength == 3
        assert bond.description == "Test Description"

    def test_bond_status(self):
        """Test that a bond can have a status."""
        bond = Bond(
            name="Test Bond",
            type="Kinship",
            status="Active"
        )
        
        assert bond.status == "Active"

    def test_bond_status_default(self):
        """Test that bond status has appropriate defaults."""
        bond = Bond(
            name="Test Bond",
            type="Kinship"
        )
        
        assert bond.status == "Active"


class TestEquipmentModel:
    """Test suite for the Equipment model."""

    def test_equipment_initialization(self):
        """Test that equipment can be initialized."""
        equipment = Equipment(
            name="Test Equipment",
            type="Weapon"
        )
        
        assert equipment.name == "Test Equipment"
        assert equipment.type == "Weapon"
        assert equipment.description is None
        assert equipment.effects is None

    def test_equipment_with_custom_attributes(self):
        """Test that equipment can be initialized with custom attributes."""
        equipment = Equipment(
            name="Test Equipment",
            type="Weapon",
            description="Test Description",
            effects={"damage": 3, "range": 10}
        )
        
        assert equipment.name == "Test Equipment"
        assert equipment.type == "Weapon"
        assert equipment.description == "Test Description"
        assert equipment.effects["damage"] == 3
        assert equipment.effects["range"] == 10
