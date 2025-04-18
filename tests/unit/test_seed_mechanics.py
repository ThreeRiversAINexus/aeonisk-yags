"""
Unit tests for the Seed Economy and Attunement mechanics in the game engine.
"""

import pytest
from unittest.mock import patch, MagicMock
from aeonisk.engine.game import GameSession, Character


class TestSeedMechanics:
    """Test suite for Seed Economy and Attunement mechanics."""

    def test_seed_attunement(self):
        """Test that a character can attune a raw Seed to an element."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add raw Seeds to the character
        raw_seed = {"id": "seed1", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed)
        
        # Mock the skill check to succeed
        with patch.object(session, 'skill_check', return_value=(True, 5, "Success")):
            # Test that the character can attune a Seed to an element
            success, message = session.attune_seed(character, raw_seed["id"], "Spark")
        
        assert success is True
        assert len(character.raw_seeds) == 0  # Seed should be removed from raw_seeds
        assert character.attuned_seeds.get("Spark", 0) == 1  # Attuned to Spark

    def test_seed_attunement_nonexistent(self):
        """Test that a character cannot attune a nonexistent Seed."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Test that the character cannot attune a nonexistent Seed
        success, message = session.attune_seed(character, "nonexistent_seed", "Spark")
        
        assert success is False
        assert "not found" in message.lower() or "doesn't exist" in message.lower()
        assert "Spark" not in character.attuned_seeds or character.attuned_seeds["Spark"] == 0

    def test_seed_attunement_multiple(self):
        """Test that a character can attune multiple Seeds to different elements."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add raw Seeds to the character
        raw_seed1 = {"id": "seed1", "acquisition_cycle": 1}
        raw_seed2 = {"id": "seed2", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed1)
        character.raw_seeds.append(raw_seed2)
        
        # Mock the skill check to always succeed for multiple calls
        with patch.object(session, 'skill_check', return_value=(True, 5, "Success")):
            # Attune seeds to different elements
            success1, _ = session.attune_seed(character, raw_seed1["id"], "Spark")
            success2, _ = session.attune_seed(character, raw_seed2["id"], "Drip")
        
        assert success1 is True
        assert success2 is True
        assert len(character.raw_seeds) == 0
        assert character.attuned_seeds.get("Spark", 0) == 1
        assert character.attuned_seeds.get("Drip", 0) == 1

    def test_seed_attunement_skill_check(self):
        """Test that Attunement skill is used for Seed attunement."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a raw Seed to the character and set Attunement skill
        raw_seed = {"id": "seed1", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed)
        character.skills["Attunement"] = 4
        
        # Mock the skill check to always succeed
        with patch.object(session, 'skill_check', return_value=(True, 5, "Success")):
            success, message = session.attune_seed(character, raw_seed["id"], "Spark")
            
            # Verify that skill_check was called with the correct parameters
            session.skill_check.assert_called_once_with(
                character, "Willpower", "Attunement", pytest.approx(18, abs=4)
            )
            
            assert success is True
            assert len(character.raw_seeds) == 0
            assert character.attuned_seeds.get("Spark", 0) == 1

    def test_seed_attunement_skill_check_failure(self):
        """Test that Seed attunement fails if the skill check fails."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a raw Seed to the character and set Attunement skill
        raw_seed = {"id": "seed1", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed)
        character.skills["Attunement"] = 2
        
        # Mock the skill check to always fail
        with patch.object(session, 'skill_check', return_value=(False, -5, "Failure")):
            success, message = session.attune_seed(character, raw_seed["id"], "Spark")
            
            # Verify that skill_check was called with the correct parameters
            session.skill_check.assert_called_once_with(
                character, "Willpower", "Attunement", pytest.approx(18, abs=4)
            )
            
            assert success is False
            assert "failed" in message.lower()
            assert len(character.raw_seeds) == 1  # Seed should still be in raw_seeds
            assert "Spark" not in character.attuned_seeds or character.attuned_seeds["Spark"] == 0

    def test_seed_degradation(self):
        """Test that raw Seeds degrade over time (7 cycles)."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add raw Seeds to the character with acquisition cycles
        raw_seed1 = {"id": "seed1", "acquisition_cycle": 1}
        raw_seed2 = {"id": "seed2", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed1)
        character.raw_seeds.append(raw_seed2)
        character.current_cycle = 1
        
        # Advance 7 cycles and collect degraded seeds
        degraded_seeds = []
        for _ in range(7):
            cycle_degraded = session.advance_cycle(character)
            degraded_seeds.extend(cycle_degraded)
        
        # Test that the Seeds have degraded
        
        assert len(degraded_seeds) == 2
        assert raw_seed1["id"] in [seed["id"] for seed in degraded_seeds]
        assert raw_seed2["id"] in [seed["id"] for seed in degraded_seeds]
        assert len(character.raw_seeds) == 0  # All seeds should be degraded

    def test_seed_degradation_partial(self):
        """Test that only Seeds older than 7 cycles degrade."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add raw Seeds to the character with different acquisition cycles
        raw_seed1 = {"id": "seed1", "acquisition_cycle": 1}  # Old seed
        raw_seed2 = {"id": "seed2", "acquisition_cycle": 1}  # Old seed
        raw_seed3 = {"id": "seed3", "acquisition_cycle": 7}  # New seed
        character.raw_seeds.append(raw_seed1)
        character.raw_seeds.append(raw_seed2)
        character.raw_seeds.append(raw_seed3)
        character.current_cycle = 7
        
        # Advance 1 cycle and collect degraded seeds
        degraded_seeds = session.advance_cycle(character)
        
        # Test that only the older Seeds have degraded
        
        assert len(degraded_seeds) == 2
        assert raw_seed1["id"] in [seed["id"] for seed in degraded_seeds]
        assert raw_seed2["id"] in [seed["id"] for seed in degraded_seeds]
        assert raw_seed3["id"] not in [seed["id"] for seed in degraded_seeds]
        assert len(character.raw_seeds) == 1  # Only the new seed should remain
        assert character.raw_seeds[0]["id"] == "seed3"

    def test_using_unattuned_seed(self):
        """Test that using an unattuned Seed inflicts +1 Void."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add a raw Seed to the character
        raw_seed = {"id": "seed1", "acquisition_cycle": 1}
        character.raw_seeds.append(raw_seed)
        character.void_score = 0
        
        # Test that using an unattuned Seed inflicts +1 Void
        success, message, void_gain = session.use_raw_seed(character, raw_seed["id"])
        
        assert success is True
        assert void_gain == 1
        assert character.void_score == 1
        assert len(character.raw_seeds) == 0  # Seed should be consumed

    def test_using_attuned_seed(self):
        """Test that using an attuned Seed does not inflict Void."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Add attuned Seeds to the character
        character.attuned_seeds = {"Spark": 3}
        character.void_score = 0
        
        # Test that using an attuned Seed does not inflict Void
        success, message, void_gain = session.use_attuned_seed(character, "Spark")
        
        assert success is True
        assert void_gain == 0
        assert character.void_score == 0
        assert character.attuned_seeds["Spark"] == 2

    def test_using_nonexistent_attuned_seed(self):
        """Test that using a nonexistent attuned Seed fails."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Test that using a nonexistent attuned Seed fails
        success, message, void_gain = session.use_attuned_seed(character, "Spark")
        
        assert success is False
        # Update assertion to match the actual error message format
        assert f"character does not have any attuned spark seeds" in message.lower()
        assert void_gain == 0

    def test_using_nonexistent_raw_seed(self):
        """Test that using a nonexistent raw Seed fails."""
        session = GameSession()
        character = session.create_character("Test Character", "Test Concept")
        
        # Test that using a nonexistent raw Seed fails
        success, message, void_gain = session.use_raw_seed(character, "nonexistent_seed")
        
        assert success is False
        assert "not found" in message.lower() or "doesn't exist" in message.lower()
        assert void_gain == 0
