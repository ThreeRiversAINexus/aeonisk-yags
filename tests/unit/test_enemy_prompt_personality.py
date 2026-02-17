"""
Tests for enemy prompt personality injection and morale-aware retreat.

Covers:
- Phase 1C: Situation history in prompts
- Phase 1D: Character brief injection, morale-aware retreat, action guidance
"""

import pytest
from unittest.mock import MagicMock, patch
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position
from scripts.aeonisk.multiagent.enemy_prompts import (
    generate_tactical_prompt_structured,
    _format_retreat_assessment,
    _format_character,
    _format_situation_history,
)


def _make_enemy(**overrides):
    """Create a minimal EnemyAgent for testing."""
    defaults = dict(
        agent_id="enemy_test_01",
        name="Test Guard",
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
        skills={"Brawl": 2, "Guns": 3},
        health=30,
        max_health=30,
        soak=8,
        wounds=0,
        position=Position(ring="Near", side="Enemy"),
        initiative=12,
        faction="ACG",
        morale_behavior="flee_when_broken",
        character_brief="Nervous and poorly trained.",
    )
    defaults.update(overrides)
    return EnemyAgent(**defaults)


class TestFormatCharacter:
    """_format_character() section in tactical prompt."""

    def test_prompt_includes_character_brief(self):
        enemy = _make_enemy(character_brief="Cool-headed professional. Fights with discipline.")
        section = _format_character(enemy)
        assert "Cool-headed professional" in section
        assert "## CHARACTER" in section

    def test_character_brief_in_character_section(self):
        enemy = _make_enemy(character_brief="Patient and calculating.")
        section = _format_character(enemy)
        assert "Patient and calculating" in section

    def test_empty_character_brief_omits_section(self):
        enemy = _make_enemy(character_brief="")
        section = _format_character(enemy)
        assert section == ""


class TestMoraleAwareRetreat:
    """_format_retreat_assessment() morale-behavior-aware."""

    def test_retreat_assessment_surrender_recommended(self):
        enemy = _make_enemy(
            morale_behavior="surrender_if_cornered",
            health=5, max_health=30, retreat_threshold=0.3
        )
        section = _format_retreat_assessment(enemy)
        assert "SURRENDER RECOMMENDED" in section

    def test_retreat_assessment_retreat_recommended(self):
        enemy = _make_enemy(
            morale_behavior="flee_when_broken",
            health=5, max_health=30, retreat_threshold=0.3
        )
        section = _format_retreat_assessment(enemy)
        assert "RETREAT RECOMMENDED" in section

    def test_retreat_assessment_fight_to_death_override(self):
        enemy = _make_enemy(
            morale_behavior="fight_to_death",
            health=2, max_health=30, retreat_threshold=0.1
        )
        section = _format_retreat_assessment(enemy)
        assert "fight to the end" in section.lower() or "fight until" in section.lower()
        assert "RETREAT RECOMMENDED" not in section
        assert "SURRENDER RECOMMENDED" not in section

    def test_retreat_assessment_void_possessed_override(self):
        enemy = _make_enemy(
            morale_behavior="surrender_if_cornered",
            health=5, max_health=30, retreat_threshold=0.3,
            void_score=10
        )
        section = _format_retreat_assessment(enemy)
        assert "VOID POSSESSED" in section

    def test_above_threshold_holding(self):
        """When above threshold, no special morale message."""
        enemy = _make_enemy(
            morale_behavior="surrender_if_cornered",
            health=25, max_health=30, retreat_threshold=0.3
        )
        section = _format_retreat_assessment(enemy)
        assert "HOLDING" in section


class TestSituationHistory:
    """_format_situation_history() section."""

    def test_situation_history_shows_3_rounds(self):
        history = [
            (1, "The patrol began normally."),
            (2, "Strangers approached the checkpoint."),
            (3, "Shots fired in the corridor."),
        ]
        section = _format_situation_history(history)
        assert "Round 3" in section
        assert "Round 2" in section
        assert "Round 1" in section

    def test_situation_history_truncates_long_synthesis(self):
        history = [
            (1, "x" * 500),
        ]
        section = _format_situation_history(history)
        assert len(section) < 600  # Should be truncated

    def test_situation_history_empty_for_round_1(self):
        section = _format_situation_history([])
        assert section == ""

    def test_situation_history_shows_most_recent_first(self):
        history = [
            (1, "First round happened."),
            (2, "Second round happened."),
            (3, "Third round happened."),
        ]
        section = _format_situation_history(history)
        # Most recent (Round 3) should appear before Round 2
        pos_3 = section.index("Round 3")
        pos_2 = section.index("Round 2")
        assert pos_3 < pos_2


class TestPromptActionGuidance:
    """Tactical prompt includes Wait/Dialogue/Surrender guidance."""

    def test_prompt_includes_wait_action_guidance(self):
        enemy = _make_enemy()
        prompt = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        assert "Wait" in prompt

    def test_prompt_includes_dialogue_action_guidance(self):
        enemy = _make_enemy()
        prompt = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        assert "Dialogue" in prompt
        assert "dialogue_content" in prompt

    def test_prompt_includes_surrender_action_guidance(self):
        enemy = _make_enemy()
        prompt = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        assert "Surrender" in prompt
