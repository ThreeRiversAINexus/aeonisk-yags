"""
Integration tests for player prompt conditional loading using real fixtures.

Tests end-to-end prompt assembly with conditional sections based on character skills.
Uses extracted fixtures from Phase 3 testing sessions.
"""

import pytest
import json
from pathlib import Path
from scripts.aeonisk.multiagent.prompt_loader import PromptLoader
from scripts.aeonisk.multiagent.player import CharacterState


# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"
MIXED_PARTY_FIXTURE = FIXTURES_DIR / "golden_prompt_test_mixed.jsonl"
NONMAGIC_PARTY_FIXTURE = FIXTURES_DIR / "golden_prompt_test_nonmagic.jsonl"


def load_characters_from_fixture(fixture_path: Path):
    """
    Extract character configurations from a session fixture.

    Returns:
        List of CharacterState objects
    """
    characters = []

    with open(fixture_path, 'r') as f:
        for line in f:
            event = json.loads(line)

            # Find session_start event
            if event.get('event_type') == 'session_start':
                config = event.get('config', {})
                agents = config.get('agents', {})
                players = agents.get('players', [])

                for player_config in players:
                    # Convert player config to CharacterState
                    char = CharacterState(
                        name=player_config['name'],
                        faction=player_config['faction'],
                        pronouns=player_config.get('pronouns', 'they/them'),
                        attributes=player_config['attributes'],
                        skills=player_config.get('skills', {}),
                        void_score=player_config.get('void', 0),
                        soulcredit=player_config.get('soulcredit', 0),
                        bonds=[],
                        goals=player_config.get('goals', [])
                    )
                    characters.append(char)

                break  # Only need session_start

    return characters


@pytest.fixture(scope="module")
def prompt_loader():
    """Create a PromptLoader instance for testing."""
    return PromptLoader()


@pytest.fixture(scope="module")
def mixed_party_characters():
    """Load characters from mixed party fixture (2 magic + 2 non-magic)."""
    return load_characters_from_fixture(MIXED_PARTY_FIXTURE)


@pytest.fixture(scope="module")
def nonmagic_party_characters():
    """Load characters from all-nonmagic fixture (4 non-magic)."""
    return load_characters_from_fixture(NONMAGIC_PARTY_FIXTURE)


class TestMixedPartyConditionalLoading:
    """Test conditional loading with mixed party (2 magic + 2 non-magic)."""

    def test_fixture_has_mixed_characters(self, mixed_party_characters):
        """Verify fixture contains both magic and non-magic characters."""
        assert len(mixed_party_characters) == 4, "Should have 4 characters"

        magic_chars = [c for c in mixed_party_characters if c.skills.get("Astral Arts", 0) > 0]
        non_magic_chars = [c for c in mixed_party_characters if c.skills.get("Astral Arts", 0) == 0]

        assert len(magic_chars) == 2, "Should have 2 magic characters"
        assert len(non_magic_chars) == 2, "Should have 2 non-magic characters"

    def test_magic_characters_include_ritual_section(
        self, prompt_loader, mixed_party_characters
    ):
        """Test that magic characters' prompts include ritual_requirements section."""
        magic_chars = [c for c in mixed_party_characters if c.skills.get("Astral Arts", 0) > 0]

        for char in magic_chars:
            # Compose sections as player.py does
            from scripts.aeonisk.multiagent.player import AIPlayerAgent
            from unittest.mock import MagicMock

            # Create mock player to use _get_required_player_sections method
            player = MagicMock(spec=AIPlayerAgent)
            player.character_state = char
            player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

            sections = player._get_required_player_sections()
            assert 'ritual_requirements_conditional' in sections, \
                f"{char.name} (Astral Arts {char.skills['Astral Arts']}) should load ritual_requirements"

    def test_non_magic_characters_exclude_ritual_section(
        self, prompt_loader, mixed_party_characters
    ):
        """Test that non-magic characters' prompts exclude ritual_requirements section."""
        non_magic_chars = [c for c in mixed_party_characters if c.skills.get("Astral Arts", 0) == 0]

        for char in non_magic_chars:
            # Compose sections as player.py does
            from scripts.aeonisk.multiagent.player import AIPlayerAgent
            from unittest.mock import MagicMock

            # Create mock player to use _get_required_player_sections method
            player = MagicMock(spec=AIPlayerAgent)
            player.character_state = char
            player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

            sections = player._get_required_player_sections()
            assert 'ritual_requirements_conditional' not in sections, \
                f"{char.name} (no Astral Arts) should skip ritual_requirements"

    def test_all_mixed_party_characters_load_core_sections(
        self, prompt_loader, mixed_party_characters
    ):
        """Test that all characters load core sections regardless of magic ability."""
        # Core sections that should always be present
        core_sections = [
            'faction_reference',
            'pydantic_philosophy',
            'targeting_guidance',
            'action_declaration_unified',
            'character_sheet'
        ]

        for char in mixed_party_characters:
            from scripts.aeonisk.multiagent.player import AIPlayerAgent
            from unittest.mock import MagicMock

            player = MagicMock(spec=AIPlayerAgent)
            player.character_state = char
            player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

            sections = player._get_required_player_sections()

            for core_section in core_sections:
                assert core_section in sections, \
                    f"{char.name} should load core section '{core_section}'"


class TestNonMagicPartyConditionalLoading:
    """Test conditional loading with all-nonmagic party (maximum token savings)."""

    def test_fixture_has_all_nonmagic_characters(self, nonmagic_party_characters):
        """Verify fixture contains only non-magic characters."""
        assert len(nonmagic_party_characters) == 4, "Should have 4 characters"

        magic_chars = [c for c in nonmagic_party_characters if c.skills.get("Astral Arts", 0) > 0]
        assert len(magic_chars) == 0, "Should have 0 magic characters (all non-magic)"

    def test_all_nonmagic_characters_exclude_ritual_section(
        self, prompt_loader, nonmagic_party_characters
    ):
        """Test that all characters in nonmagic party exclude ritual_requirements."""
        for char in nonmagic_party_characters:
            from scripts.aeonisk.multiagent.player import AIPlayerAgent
            from unittest.mock import MagicMock

            player = MagicMock(spec=AIPlayerAgent)
            player.character_state = char
            player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

            sections = player._get_required_player_sections()
            assert 'ritual_requirements_conditional' not in sections, \
                f"{char.name} should skip ritual_requirements (maximum token savings)"

    def test_nonmagic_party_token_savings_sections(
        self, prompt_loader, nonmagic_party_characters
    ):
        """Test that nonmagic party achieves maximum token savings."""
        # All 4 characters should have identical section lists (no ritual_requirements)
        section_lists = []

        for char in nonmagic_party_characters:
            from scripts.aeonisk.multiagent.player import AIPlayerAgent
            from unittest.mock import MagicMock

            player = MagicMock(spec=AIPlayerAgent)
            player.character_state = char
            player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

            sections = player._get_required_player_sections()
            section_lists.append(sections)

        # All section lists should be identical (maximum uniformity = maximum savings)
        first_sections = section_lists[0]
        for sections in section_lists[1:]:
            assert sections == first_sections, \
                "All nonmagic characters should have identical section lists"

        # None should have ritual_requirements
        assert 'ritual_requirements_conditional' not in first_sections, \
            "Nonmagic party should not load ritual_requirements"


class TestPromptAssembly:
    """Test full prompt assembly with conditional sections."""

    def test_prompt_loader_composes_sections_correctly(self, prompt_loader):
        """Test that PromptLoader can compose sections with conditional loading."""
        # Test with Astral Arts character
        magic_char = CharacterState(
            name="Test Mage",
            faction="Tempest Industries",
            pronouns="she/her",
            attributes={"Strength": 2, "Agility": 3, "Endurance": 3, "Perception": 3,
                       "Intelligence": 4, "Empathy": 2, "Willpower": 4, "Charisma": 2},
            skills={"Astral Arts": 8, "Attunement": 6, "Magick Theory": 5},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=["Test magic"]
        )

        # Get section list
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        from unittest.mock import MagicMock

        player = MagicMock(spec=AIPlayerAgent)
        player.character_state = magic_char
        player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

        sections_to_load = player._get_required_player_sections()

        # Load prompt using PromptLoader
        prompt_result = prompt_loader.compose_sections(
            agent_type="player",
            section_names=sections_to_load,
            provider="claude",
            language="en"
        )

        # Verify prompt contains ritual requirements text
        prompt_content = prompt_result.content
        assert "offering" in prompt_content.lower(), \
            "Magic character prompt should mention offerings (from ritual_requirements)"
        assert "seed" in prompt_content.lower(), \
            "Magic character prompt should mention seeds (from ritual_requirements)"

    def test_nonmagic_prompt_excludes_ritual_content(self, prompt_loader):
        """Test that non-magic character prompts don't contain ritual content."""
        # Test with non-magic character
        nonmagic_char = CharacterState(
            name="Test Fighter",
            faction="Pantheon Security",
            pronouns="he/him",
            attributes={"Strength": 4, "Agility": 4, "Endurance": 4, "Perception": 3,
                       "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Charisma": 2},
            skills={"Combat": 8, "Guns": 7, "Athletics": 5},
            void_score=0,
            soulcredit=0,
            bonds=[],
            goals=["Test combat"]
        )

        # Get section list
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        from unittest.mock import MagicMock

        player = MagicMock(spec=AIPlayerAgent)
        player.character_state = nonmagic_char
        player._get_required_player_sections = AIPlayerAgent._get_required_player_sections.__get__(player, AIPlayerAgent)

        sections_to_load = player._get_required_player_sections()

        # Verify ritual_requirements not in list
        assert 'ritual_requirements_conditional' not in sections_to_load, \
            "Non-magic character should not load ritual_requirements section"

        # Load prompt using PromptLoader
        prompt_result = prompt_loader.compose_sections(
            agent_type="player",
            section_names=sections_to_load,
            provider="claude",
            language="en"
        )

        # Verify prompt content is shorter (token savings)
        # Note: We can't check exact token count without tokenizer, but we can check presence/absence
        prompt_content = prompt_result.content

        # Non-magic prompt should still have core content
        assert "action" in prompt_content.lower(), "Should have action guidance"
        # Note: Faction won't appear because template uses {character.faction} which isn't substituted in test
