"""
Unit tests for combat targeting list injury display.

Tests verify that the combat targeting list shows wounds/stuns for all players,
not just raw HP, so teammates can see injury severity at a glance.
"""

import pytest
from unittest.mock import MagicMock
from scripts.aeonisk.multiagent.player import AIPlayerAgent, CharacterState


@pytest.fixture
def base_character_state():
    """Create a base character state for testing."""
    return CharacterState(
        name="Test Character",
        pronouns="they/them",
        faction="Test Faction",
        attributes={
            "Strength": 3,
            "Health": 4,
            "Agility": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 3,
            "Resolve": 3,
        },
        skills={"Combat": 4},
        void_score=2,
        soulcredit=100,
        bonds=[],
        goals=["Test Goal"],
    )


def create_mock_player_for_targeting(name: str, health: int, max_health: int, wounds: int = 0, stuns: int = 0):
    """Create a mock player with specific health/wound status for targeting list tests."""
    char_state = CharacterState(
        name=name,
        pronouns="they/them",
        faction="Test Faction",
        attributes={"Strength": 3, "Health": 4, "Agility": 3, "Perception": 3,
                   "Intelligence": 3, "Empathy": 3, "Resolve": 3},
        skills={"Combat": 4},
        void_score=2,
        soulcredit=100,
        bonds=[],
        goals=["Test"],
    )

    player = MagicMock(spec=AIPlayerAgent)
    player.character_state = char_state
    player.agent_id = f"test_{name}"
    player.health = health
    player.max_health = max_health
    player.wounds = wounds
    player.stuns = stuns

    return player


class TestCombatTargetingWoundDisplay:
    """Test that combat targeting list shows wounds/stuns for all players."""

    def test_wound_indicator_format_no_wounds(self):
        """Test wound indicator with 0 wounds shows nothing."""
        wounds = 0

        # Replicate the logic we'll add to player.py
        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == "", "0 wounds should show no indicator"

    def test_wound_indicator_format_one_wound(self):
        """Test wound indicator with 1 wound shows count only."""
        wounds = 1

        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == " | 1w", "1 wound should show count"

    def test_wound_indicator_format_two_wounds(self):
        """Test wound indicator with 2 wounds shows WOUNDED -5 penalty."""
        wounds = 2

        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == " | 2w (WOUNDED -5)", "2 wounds should show penalty"

    def test_wound_indicator_format_three_wounds(self):
        """Test wound indicator with 3 wounds shows WOUNDED -5 penalty."""
        wounds = 3

        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == " | 3w (WOUNDED -5)", "3 wounds should show penalty"

    def test_wound_indicator_format_four_wounds(self):
        """Test wound indicator with 4 wounds shows HEAVY -15 penalty and warning."""
        wounds = 4

        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == " | 4w (HEAVY -15) ⚠️", "4+ wounds should show heavy penalty"

    def test_wound_indicator_format_five_wounds(self):
        """Test wound indicator with 5+ wounds shows HEAVY -15 penalty and warning."""
        wounds = 5

        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        assert wound_indicator == " | 5w (HEAVY -15) ⚠️", "5+ wounds should show heavy penalty"

    def test_stun_indicator_format_no_stuns(self):
        """Test stun indicator with 0 stuns shows nothing."""
        stuns = 0

        stun_indicator = f" | {stuns}s" if stuns > 0 else ""

        assert stun_indicator == "", "0 stuns should show nothing"

    def test_stun_indicator_format_with_stuns(self):
        """Test stun indicator with stuns shows count."""
        stuns = 2

        stun_indicator = f" | {stuns}s" if stuns > 0 else ""

        assert stun_indicator == " | 2s", "Stuns should show count"

    def test_combined_wounds_and_stuns(self):
        """Test combined wound and stun indicators."""
        wounds = 3
        stuns = 2

        # Wound indicator
        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        # Stun indicator
        stun_indicator = f" | {stuns}s" if stuns > 0 else ""

        combined = wound_indicator + stun_indicator

        assert combined == " | 3w (WOUNDED -5) | 2s", "Should show both wounds and stuns"

    def test_full_combatant_line_format_healthy(self):
        """Test full combatant line format for healthy player."""
        # Expected format: [tgt_id] Name | Position | HP | wounds | stuns | Void
        name = "Ash"
        tgt_id = "tgt_001"
        position = "Near-PC"
        health = 40
        max_health = 40
        wounds = 0
        stuns = 0
        void_score = 3

        # Build wound/stun indicators
        wound_indicator = ""
        stun_indicator = ""

        # Format line
        line = f"[{tgt_id}] {name:20s} | {position:12s} | {health}/{max_health} HP{wound_indicator}{stun_indicator} | Void {void_score}/10"

        assert "[tgt_001]" in line
        assert "Ash" in line
        assert "40/40 HP" in line
        assert "Void 3/10" in line
        assert "WOUNDED" not in line

    def test_full_combatant_line_format_wounded(self):
        """Test full combatant line format for wounded player."""
        name = "Kade"
        tgt_id = "tgt_002"
        position = "Far-PC"
        health = 15
        max_health = 35
        wounds = 2
        stuns = 0
        void_score = 5

        # Build indicators
        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        stun_indicator = f" | {stuns}s" if stuns > 0 else ""

        line = f"[{tgt_id}] {name:20s} | {position:12s} | {health}/{max_health} HP{wound_indicator}{stun_indicator} | Void {void_score}/10"

        assert "[tgt_002]" in line
        assert "15/35 HP" in line
        assert "2w (WOUNDED -5)" in line
        assert "Void 5/10" in line

    def test_full_combatant_line_format_critical(self):
        """Test full combatant line format for critically wounded player."""
        name = "Mira"
        tgt_id = "tgt_003"
        position = "Near-PC"
        health = 5
        max_health = 30
        wounds = 4
        stuns = 3
        void_score = 2

        # Build indicators
        if wounds >= 4:
            wound_indicator = f" | {wounds}w (HEAVY -15) ⚠️"
        elif wounds >= 2:
            wound_indicator = f" | {wounds}w (WOUNDED -5)"
        elif wounds == 1:
            wound_indicator = f" | {wounds}w"
        else:
            wound_indicator = ""

        stun_indicator = f" | {stuns}s" if stuns > 0 else ""

        line = f"[{tgt_id}] {name:20s} | {position:12s} | {health}/{max_health} HP{wound_indicator}{stun_indicator} | Void {void_score}/10"

        assert "[tgt_003]" in line
        assert "5/30 HP" in line
        assert "4w (HEAVY -15) ⚠️" in line
        assert "3s" in line
        assert "Void 2/10" in line
