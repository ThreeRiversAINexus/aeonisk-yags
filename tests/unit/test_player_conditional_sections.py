"""
Unit tests for player prompt conditional section loading (Phase 3).

Tests the logic that determines which prompt sections to load based on:
- Character skills (Astral Arts → ritual_requirements)
- Always-loaded sections (faction_reference, pydantic_philosophy, targeting_guidance)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState


@pytest.fixture
def base_character_data():
    """Base character data for testing."""
    return {
        "name": "Test Character",
        "pronouns": "they/them",
        "faction": "Freeborn",
        "attributes": {
            "Strength": 3,
            "Agility": 3,
            "Endurance": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 3,
            "Willpower": 3,
            "Empathy": 3
        },
        "void_score": 0,
        "soulcredit": 0,
        "bonds": [],
        "goals": ["Test goal"]
    }


@pytest.fixture
def astral_arts_character(base_character_data):
    """Character with Astral Arts skill (should load ritual_requirements)."""
    character_data = base_character_data.copy()
    character_data["skills"] = {
        "Astral Arts": 6,
        "Attunement": 5,
        "Combat": 3
    }
    return CharacterState(**character_data)


@pytest.fixture
def non_magic_character(base_character_data):
    """Character without Astral Arts skill (should skip ritual_requirements)."""
    character_data = base_character_data.copy()
    character_data["skills"] = {
        "Combat": 8,
        "Guns": 7,
        "Athletics": 5
    }
    return CharacterState(**character_data)


@pytest.fixture
def magic_theory_only_character(base_character_data):
    """Character with Magic Theory but no Astral Arts (should skip ritual_requirements)."""
    character_data = base_character_data.copy()
    character_data["skills"] = {
        "Magic Theory": 6,
        "Investigation": 5,
        "Systems": 4
    }
    return CharacterState(**character_data)


def create_mock_player(character_state: CharacterState) -> AIPlayerAgent:
    """
    Create a mock AIPlayerAgent for testing section loading.

    Uses minimal mocking to avoid complex constructor requirements.
    """
    # Create mock with character_state attribute
    player = MagicMock(spec=AIPlayerAgent)
    player.character_state = character_state

    # Use the real _get_required_player_sections method
    player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

    return player


class TestConditionalSectionLoading:
    """Test conditional section loading based on character skills."""

    def test_astral_arts_character_loads_ritual_requirements(self, astral_arts_character):
        """Test that characters with Astral Arts skill load ritual_requirements."""
        player = create_mock_player(astral_arts_character)
        sections = player._get_required_player_sections()

        # Assert ritual_requirements_conditional is included
        assert 'ritual_requirements_conditional' in sections, \
            "Astral Arts character should load ritual_requirements"

        # Assert it's positioned after action_declaration_unified
        action_idx = sections.index('action_declaration_unified')
        ritual_idx = sections.index('ritual_requirements_conditional')
        assert ritual_idx == action_idx + 1, \
            "ritual_requirements should immediately follow action_declaration_unified"

    def test_non_magic_character_skips_ritual_requirements(self, non_magic_character):
        """Test that characters without Astral Arts skip ritual_requirements."""
        player = create_mock_player(non_magic_character)
        sections = player._get_required_player_sections()

        # Assert ritual_requirements_conditional is NOT included
        assert 'ritual_requirements_conditional' not in sections, \
            "Non-magic character should skip ritual_requirements"

    def test_magic_theory_only_skips_ritual_requirements(self, magic_theory_only_character):
        """Test that Magic Theory (analysis) without Astral Arts (casting) skips ritual_requirements."""
        player = create_mock_player(magic_theory_only_character)
        sections = player._get_required_player_sections()

        # Assert ritual_requirements_conditional is NOT included
        assert 'ritual_requirements_conditional' not in sections, \
            "Magic Theory without Astral Arts should skip ritual_requirements"

    def test_all_characters_load_faction_reference(
        self, astral_arts_character, non_magic_character
    ):
        """Test that all characters load faction_reference (canonical factions)."""
        # Test with Astral Arts character
        player_magic = create_mock_player(astral_arts_character)
        sections_magic = player_magic._get_required_player_sections()
        assert 'faction_reference' in sections_magic, \
            "Magic character should load faction_reference"

        # Test with non-magic character
        player_nonmagic = create_mock_player(non_magic_character)
        sections_nonmagic = player_nonmagic._get_required_player_sections()
        assert 'faction_reference' in sections_nonmagic, \
            "Non-magic character should load faction_reference"

    def test_all_characters_load_pydantic_philosophy(
        self, astral_arts_character, non_magic_character
    ):
        """Test that all characters load pydantic_philosophy section."""
        # Test with Astral Arts character
        player_magic = create_mock_player(astral_arts_character)
        sections_magic = player_magic._get_required_player_sections()
        assert 'pydantic_philosophy' in sections_magic, \
            "Magic character should load pydantic_philosophy"

        # Test with non-magic character
        player_nonmagic = create_mock_player(non_magic_character)
        sections_nonmagic = player_nonmagic._get_required_player_sections()
        assert 'pydantic_philosophy' in sections_nonmagic, \
            "Non-magic character should load pydantic_philosophy"

    def test_all_characters_load_targeting_guidance(
        self, astral_arts_character, non_magic_character
    ):
        """Test that all characters load targeting_guidance section."""
        # Test with Astral Arts character
        player_magic = create_mock_player(astral_arts_character)
        sections_magic = player_magic._get_required_player_sections()
        assert 'targeting_guidance' in sections_magic, \
            "Magic character should load targeting_guidance"

        # Test with non-magic character
        player_nonmagic = create_mock_player(non_magic_character)
        sections_nonmagic = player_nonmagic._get_required_player_sections()
        assert 'targeting_guidance' in sections_nonmagic, \
            "Non-magic character should load targeting_guidance"

    def test_core_sections_always_loaded(self, non_magic_character):
        """Test that core sections are always present."""
        player = create_mock_player(non_magic_character)
        sections = player._get_required_player_sections()

        # Core sections that should always be present
        core_sections = [
            'character_introduction',
            'character_sheet',
            'inventory_resources',
            'personality_traits',
            'goals',
            'lookup_rules',
            'stat_awareness_guidance',
            'action_declaration_unified',
            'coordination_dialogue',
            'vendor_interaction',
            'currency_transfers',
            'action_guidelines',
            'bond_mechanics',
            'important_rules'
        ]

        for section in core_sections:
            assert section in sections, f"Core section '{section}' should always be loaded"


class TestConditionalLoadingLogging:
    """Test that conditional loading logs correctly."""

    def test_astral_arts_loading_logged(self, astral_arts_character, caplog):
        """Test that loading ritual_requirements is logged."""
        import logging
        caplog.set_level(logging.DEBUG)

        player = create_mock_player(astral_arts_character)
        player._get_required_player_sections()

        # Check for loading message
        assert any(
            "Loading ritual_requirements" in record.message
            for record in caplog.records
        ), "Should log when loading ritual_requirements"

        # Check that Astral Arts skill level is mentioned
        assert any(
            "Astral Arts 6" in record.message
            for record in caplog.records
        ), "Should log Astral Arts skill level"

    def test_non_magic_skipping_logged(self, non_magic_character, caplog):
        """Test that skipping ritual_requirements is logged."""
        import logging
        caplog.set_level(logging.DEBUG)

        player = create_mock_player(non_magic_character)
        player._get_required_player_sections()

        # Check for skipping message
        assert any(
            "Skipping ritual_requirements" in record.message
            for record in caplog.records
        ), "Should log when skipping ritual_requirements"

        # Check that reason is given
        assert any(
            "no Astral Arts skill" in record.message
            for record in caplog.records
        ), "Should log reason for skipping"


class TestTokenSavingsScenarios:
    """Test scenarios that demonstrate token savings."""

    def test_mixed_party_section_distribution(
        self, astral_arts_character, non_magic_character
    ):
        """Test mixed party (2 magic + 2 non-magic) section distribution."""
        # Create 2 magic characters
        player_magic_1 = create_mock_player(astral_arts_character)
        player_magic_2 = create_mock_player(astral_arts_character)

        # Create 2 non-magic characters
        player_nonmagic_1 = create_mock_player(non_magic_character)
        player_nonmagic_2 = create_mock_player(non_magic_character)

        # Get sections for all
        sections_magic_1 = player_magic_1._get_required_player_sections()
        sections_magic_2 = player_magic_2._get_required_player_sections()
        sections_nonmagic_1 = player_nonmagic_1._get_required_player_sections()
        sections_nonmagic_2 = player_nonmagic_2._get_required_player_sections()

        # Assert magic characters have ritual_requirements
        assert 'ritual_requirements_conditional' in sections_magic_1
        assert 'ritual_requirements_conditional' in sections_magic_2

        # Assert non-magic characters don't
        assert 'ritual_requirements_conditional' not in sections_nonmagic_1
        assert 'ritual_requirements_conditional' not in sections_nonmagic_2

    def test_all_nonmagic_party_maximum_savings(self, non_magic_character):
        """Test all-nonmagic party (maximum token savings scenario)."""
        # Create 4 non-magic characters
        players = [
            create_mock_player(non_magic_character)
            for _ in range(4)
        ]

        # Get sections for all
        all_sections = [player._get_required_player_sections() for player in players]

        # Assert NONE have ritual_requirements
        for sections in all_sections:
            assert 'ritual_requirements_conditional' not in sections, \
                "All-nonmagic party should skip ritual_requirements for maximum savings"
