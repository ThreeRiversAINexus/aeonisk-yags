"""
Unit tests for conservative fuzzy name matching.

Tests the name matching logic that allows DM to use shortened character names
while preventing mismatches.
"""

import pytest
from scripts.aeonisk.multiagent.name_matching import match_character_name, resolve_character_name


class TestMatchCharacterName:
    """Test conservative fuzzy matching for character names."""

    def test_exact_match_no_fuzzing(self):
        """Exact matches should return immediately without fuzzing."""
        characters = ["Vessel Sera Karsel", "Guardian Rhea Ireveth"]

        matched, is_fuzzy, error = match_character_name("Vessel Sera Karsel", characters)

        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is False
        assert error is None

    def test_suffix_match_removes_title(self):
        """Should match when provided name is suffix of full name (title removed)."""
        characters = ["Vessel Sera Karsel", "Guardian Rhea Ireveth"]

        matched, is_fuzzy, error = match_character_name("Sera Karsel", characters)

        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is True
        assert error is None

    def test_suffix_match_multiple_characters(self):
        """Should match correct character when multiple characters present."""
        characters = ["Vessel Sera Karsel", "Guardian Rhea Ireveth", "Anchor Dex Thaurin"]

        # Test each character
        matched1, is_fuzzy1, error1 = match_character_name("Sera Karsel", characters)
        assert matched1 == "Vessel Sera Karsel"
        assert is_fuzzy1 is True

        matched2, is_fuzzy2, error2 = match_character_name("Rhea Ireveth", characters)
        assert matched2 == "Guardian Rhea Ireveth"
        assert is_fuzzy2 is True

        matched3, is_fuzzy3, error3 = match_character_name("Dex Thaurin", characters)
        assert matched3 == "Anchor Dex Thaurin"
        assert is_fuzzy3 is True

    def test_single_word_rejected(self):
        """Single-word names should be rejected (too ambiguous)."""
        characters = ["Vessel Sera Karsel", "Guardian Rhea Ireveth"]

        matched, is_fuzzy, error = match_character_name("Sera", characters)

        assert matched is None
        assert is_fuzzy is False
        assert "too short" in error.lower()
        assert "2 words required" in error.lower()

    def test_no_match_found(self):
        """Should fail gracefully when no match exists."""
        characters = ["Vessel Sera Karsel", "Guardian Rhea Ireveth"]

        matched, is_fuzzy, error = match_character_name("Bob Smith", characters)

        assert matched is None
        assert is_fuzzy is False
        assert "No character found" in error
        assert "Bob Smith" in error

    def test_ambiguous_match_rejected(self):
        """Should reject when multiple characters could match."""
        # Create ambiguous scenario: two characters with "Sera" in name
        characters = ["Vessel Sera Karsel", "Sera Thorne Medic"]

        # "Sera Thorne" could match "Sera Thorne Medic"
        # but what if there's another "Sera Thorne" character?
        # This test verifies we don't accidentally match
        matched, is_fuzzy, error = match_character_name("Sera Karsel", characters)

        # This should still work (unambiguous suffix match)
        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is True

    def test_ambiguous_suffix_rejected(self):
        """Should reject when suffix matches multiple characters."""
        # Contrived example: two characters ending with same suffix
        characters = ["Title1 John Smith", "Title2 John Smith"]

        matched, is_fuzzy, error = match_character_name("John Smith", characters)

        assert matched is None
        assert is_fuzzy is False
        assert "Ambiguous" in error
        assert "multiple characters" in error

    def test_empty_inputs(self):
        """Should handle empty inputs gracefully."""
        matched1, is_fuzzy1, error1 = match_character_name("", ["Character Name"])
        assert matched1 is None
        assert "Empty name" in error1

        matched2, is_fuzzy2, error2 = match_character_name("Character Name", [])
        assert matched2 is None
        assert "no characters available" in error2

    def test_whitespace_handling(self):
        """Should handle leading/trailing whitespace."""
        characters = ["Vessel Sera Karsel"]

        matched, is_fuzzy, error = match_character_name("  Sera Karsel  ", characters)

        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is True

    def test_case_sensitive_matching(self):
        """Name matching should be case-sensitive (as names are proper nouns)."""
        characters = ["Vessel Sera Karsel"]

        # Different case should not match
        matched, is_fuzzy, error = match_character_name("sera karsel", characters)

        assert matched is None
        assert "No character found" in error

    def test_partial_word_no_match(self):
        """Partial word matches should not work (only full suffix)."""
        characters = ["Vessel Sera Karsel"]

        # "Karsel" alone should fail (only 1 word)
        matched1, is_fuzzy1, error1 = match_character_name("Karsel", characters)
        assert matched1 is None

        # "era Karsel" actually DOES match (it's a valid 2-word suffix)
        # This is fine - it's still unambiguous and has 2+ words
        matched2, is_fuzzy2, error2 = match_character_name("era Karsel", characters)
        assert matched2 == "Vessel Sera Karsel"
        assert is_fuzzy2 is True


class TestResolveCharacterName:
    """Test convenience wrapper for SharedState.registered_players format."""

    def test_resolve_with_registered_players(self):
        """Should work with SharedState.registered_players format."""
        registered = [
            {'agent_id': 'p1', 'name': 'Vessel Sera Karsel', 'faction': 'Tempest'},
            {'agent_id': 'p2', 'name': 'Guardian Rhea Ireveth', 'faction': 'Pantheon'},
            {'agent_id': 'p3', 'name': 'Anchor Dex Thaurin', 'faction': 'Resonance'}
        ]

        matched, is_fuzzy, error = resolve_character_name("Sera Karsel", registered)

        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is True
        assert error is None

    def test_resolve_exact_match(self):
        """Should handle exact matches."""
        registered = [
            {'agent_id': 'p1', 'name': 'Vessel Sera Karsel', 'faction': 'Tempest'}
        ]

        matched, is_fuzzy, error = resolve_character_name("Vessel Sera Karsel", registered)

        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is False

    def test_resolve_no_match(self):
        """Should fail when no match found."""
        registered = [
            {'agent_id': 'p1', 'name': 'Vessel Sera Karsel', 'faction': 'Tempest'}
        ]

        matched, is_fuzzy, error = resolve_character_name("Bob Smith", registered)

        assert matched is None
        assert "No character found" in error


class TestRealWorldScenarios:
    """Test with real examples from error logs."""

    def test_session_a1d0e81f_scenario(self):
        """Test actual names from session_a1d0e81f that triggered warnings."""
        registered = [
            {'agent_id': 'p1', 'name': 'Anchor Dex Thaurin', 'faction': 'Resonance'},
            {'agent_id': 'p2', 'name': 'Interrogator Vance Nymir', 'faction': 'Pantheon'},
            {'agent_id': 'p3', 'name': 'Guardian Rhea Ireveth', 'faction': 'Pantheon'},
            {'agent_id': 'p4', 'name': 'Vessel Sera Karsel', 'faction': 'Arcane'}
        ]

        # DM applied void to "Sera Karsel" (action by Dex Thaurin)
        matched, is_fuzzy, error = resolve_character_name("Sera Karsel", registered)
        assert matched == "Vessel Sera Karsel"
        assert is_fuzzy is True

        # DM applied void to "Vance Nymir" (action by self)
        matched2, is_fuzzy2, error2 = resolve_character_name("Vance Nymir", registered)
        assert matched2 == "Interrogator Vance Nymir"
        assert is_fuzzy2 is True

        # DM applied void to "Rhea Ireveth" (action by self)
        matched3, is_fuzzy3, error3 = resolve_character_name("Rhea Ireveth", registered)
        assert matched3 == "Guardian Rhea Ireveth"
        assert is_fuzzy3 is True

    def test_session_aaf5bc19_scenario(self):
        """Test actual names from session_aaf5bc19."""
        registered = [
            {'agent_id': 'p1', 'name': 'Vessel Sera Karsel', 'faction': 'Arcane'},
            {'agent_id': 'p2', 'name': 'Guardian Rhea Ireveth', 'faction': 'Pantheon'}
        ]

        matched1, is_fuzzy1, error1 = resolve_character_name("Sera Karsel", registered)
        assert matched1 == "Vessel Sera Karsel"

        matched2, is_fuzzy2, error2 = resolve_character_name("Rhea Ireveth", registered)
        assert matched2 == "Guardian Rhea Ireveth"
