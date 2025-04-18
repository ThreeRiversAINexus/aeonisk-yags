"""
Unit tests for the Void mechanics in the game engine.
"""

import pytest
from unittest.mock import patch, MagicMock
from aeonisk.engine.game import GameSession, Character


class TestVoidMechanics:
    """Test suite for Void mechanics."""

    def test_void_environmental_disruption_level1(self):
        """Test Void Environmental Disruption at level 1 (Void 5-6)."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 5
        
        # Test that the environmental disruption effect is applied
        effect = session.get_void_environmental_effect(character)
        
        assert effect is not None
        assert "disruption" in effect.lower()
        assert "minor" in effect.lower() or "ambient" in effect.lower()

    def test_void_environmental_disruption_level2(self):
        """Test Void Environmental Disruption at level 2 (Void 7-8)."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 7
        
        # Test that the environmental disruption effect is applied
        effect = session.get_void_environmental_effect(character)
        
        assert effect is not None
        assert "disruption" in effect.lower()
        assert "significant" in effect.lower() or "increased" in effect.lower()

    def test_void_environmental_disruption_level3(self):
        """Test Void Environmental Disruption at level 3 (Void 9)."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 9
        
        # Test that the environmental disruption effect is applied
        effect = session.get_void_environmental_effect(character)
        
        assert effect is not None
        assert "disruption" in effect.lower()
        assert "severe" in effect.lower() or "reject" in effect.lower()

    def test_void_environmental_disruption_level4(self):
        """Test Void Environmental Disruption at level 4 (Void 10)."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 10
        
        # Test that the environmental disruption effect is applied
        effect = session.get_void_environmental_effect(character)
        
        assert effect is not None
        # Adjust assertion to match the exact string
        assert "reality warps visibly around the character. claimed by the void." in effect.lower()

    def test_void_environmental_disruption_none(self):
        """Test that no Void Environmental Disruption occurs at low Void scores."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 4
        
        # Test that no environmental disruption effect is applied
        effect = session.get_void_environmental_effect(character)
        
        assert effect is None or effect == ""

    def test_void_spike(self):
        """Test Void Spike when gaining 2+ Void at once."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 3
        
        # Test that a Void Spike occurs when gaining 2+ Void
        is_spiked, effect = session.apply_void_gain(character, 2)
        
        assert is_spiked is True
        assert "stunned" in effect.lower() or "dazed" in effect.lower()
        assert character.void_score == 5

    def test_no_void_spike(self):
        """Test that no Void Spike occurs when gaining less than 2 Void."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 3
        
        # Test that no Void Spike occurs when gaining less than 2 Void
        is_spiked, effect = session.apply_void_gain(character, 1)
        
        assert is_spiked is False
        assert effect is None or effect == ""
        assert character.void_score == 4

    def test_bond_dormancy(self):
        """Test that Bonds become Dormant when Void ≥ 7."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a Bond to the character
        bond = {"name": "Test Bond", "type": "Kinship", "status": "Active"}
        character.bonds.append(bond)
        
        # Set Void score to 7
        character.void_score = 7
        
        # Test that the Bond becomes Dormant
        session.update_bond_status(character)
        
        assert character.bonds[0]["status"] == "Dormant"

    def test_bond_active(self):
        """Test that Bonds remain Active when Void < 7."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a Bond to the character
        bond = {"name": "Test Bond", "type": "Kinship", "status": "Active"}
        character.bonds.append(bond)
        
        # Set Void score to 6
        character.void_score = 6
        
        # Test that the Bond remains Active
        session.update_bond_status(character)
        
        assert character.bonds[0]["status"] == "Active"

    def test_void_cap(self):
        """Test that Void score is capped at 10."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        character.void_score = 9
        
        # Test that Void score is capped at 10
        is_spiked, effect = session.apply_void_gain(character, 3)
        
        assert character.void_score == 10
        assert is_spiked is True
