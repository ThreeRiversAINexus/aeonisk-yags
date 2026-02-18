"""
Unit tests for enemy declaration parsing and action execution in enemy_combat.py.

Tests the parse_enemy_declaration function handles various LLM output formats,
including markdown bold formatting that was previously dropped.

Also tests dialogue and wait action handlers.
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.enemy_combat import parse_enemy_declaration, EnemyCombatManager, EnemyDeclaration
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position


def _make_mock_enemy(name="Thug #2", agent_id="enemy_02", initiative=5):
    enemy = MagicMock()
    enemy.name = name
    enemy.agent_id = agent_id
    enemy.initiative = initiative
    return enemy


class TestParseEnemyDeclarationMarkdownBold:
    """Bug fix: LLM returns **KEY:** Value format — must parse, not skip."""

    def test_parse_markdown_bold_declaration(self):
        """**MAJOR_ACTION:** Attack should parse correctly."""
        text = """\
**MAJOR_ACTION:** Attack
**TARGET:** tgt_6x24
**WEAPON:** Fists
**DEFENCE_TOKEN:** tgt_abc1
**MINOR_ACTION:** None
**TACTICAL_REASONING:** Closing in for melee
**SHARE_INTEL:** None
"""
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Attack"
        assert result.target == "tgt_6x24"
        assert result.weapon == "Fists"
        assert result.defence_token == "tgt_abc1"
        assert result.minor_action is None
        assert result.reasoning == "Closing in for melee"
        assert result.shared_intel is None

    def test_parse_mixed_format_declaration(self):
        """Some keys bold, some plain — all should parse."""
        text = """\
**MAJOR_ACTION:** Shift_2
TARGET: tgt_abc1
**WEAPON:** Rifle
MINOR_ACTION: None
TACTICAL_REASONING: Repositioning for better angle
"""
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Shift_2"
        assert result.target == "tgt_abc1"
        assert result.weapon == "Rifle"
        assert result.minor_action is None
        assert result.reasoning == "Repositioning for better angle"


class TestParseEnemyDeclarationPlaintext:
    """Existing plaintext format must still work."""

    def test_parse_plain_declaration(self):
        text = """\
MAJOR_ACTION: Attack
TARGET: tgt_1234
WEAPON: Knife
DEFENCE_TOKEN: tgt_abc1
MINOR_ACTION: None
TACTICAL_REASONING: Going for the kill
SHARE_INTEL: Enemy spotted at flank
"""
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Attack"
        assert result.target == "tgt_1234"
        assert result.weapon == "Knife"
        assert result.defence_token == "tgt_abc1"
        assert result.minor_action is None
        assert result.reasoning == "Going for the kill"
        assert result.shared_intel == "Enemy spotted at flank"

    def test_parse_code_block_declaration(self):
        """Code-fenced declarations should still work (fences stripped)."""
        text = """\
```
MAJOR_ACTION: Attack
TARGET: tgt_5678
WEAPON: Pistol
TACTICAL_REASONING: Standard engagement
```
"""
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Attack"
        assert result.target == "tgt_5678"

    def test_missing_major_action_returns_none(self):
        text = "TARGET: tgt_1234\nWEAPON: Sword\n"
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)
        assert result is None


class TestParseEnemyDeclarationEdgeCases:
    """Edge cases for markdown stripping."""

    def test_bold_with_leading_whitespace(self):
        """Indented bold lines should parse."""
        text = "  **MAJOR_ACTION:** Defend\n  **TARGET:** None\n"
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Defend"

    def test_markdown_headers_still_skipped(self):
        """Lines starting with # should still be skipped."""
        text = """\
# Enemy Declaration
MAJOR_ACTION: Attack
TARGET: tgt_1234
"""
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Attack"

    def test_double_star_in_value_preserved(self):
        """Bold markers in values get stripped too, which is acceptable."""
        text = "MAJOR_ACTION: Attack\nTACTICAL_REASONING: **very** important reason\n"
        enemy = _make_mock_enemy()
        result = parse_enemy_declaration(text, enemy)

        assert result is not None
        assert result.major_action == "Attack"
        # Bold markers in values get stripped — acceptable trade-off
        assert "important reason" in result.reasoning


# =============================================================================
# DIALOGUE AND WAIT ACTION HANDLERS
# =============================================================================

def _make_enemy_agent(name="Test Guard", agent_id="enemy_guard_01", faction="Sovereign Nexus"):
    """Create a real EnemyAgent for combat manager tests."""
    return EnemyAgent(
        agent_id=agent_id,
        name=name,
        template="grunt",
        attributes={"Agility": 3, "Strength": 3, "Perception": 2, "Intelligence": 2, "Empathy": 2, "Willpower": 2, "Health": 3},
        skills={"Brawl": 2, "Guns": 3, "Awareness": 2},
        health=30,
        max_health=30,
        soak=0,
        wounds=0,
        position=Position(ring="Near", side="Enemy"),
        initiative=10,
        faction=faction,
        morale_behavior="flee_when_broken",
        character_brief="Test guard.",
    )


def _make_combat_manager_with_enemy(enemy):
    """Create an EnemyCombatManager with a single enemy registered."""
    manager = EnemyCombatManager()
    manager.enabled = True
    manager.enemy_agents = [enemy]
    manager.current_round = 1
    return manager


class TestExecuteDialogue:
    """Tests for enemy dialogue action execution."""

    def test_execute_dialogue_returns_success(self):
        """Dialogue action should return a result dict with dialogue_content."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)
        manager.enemy_declarations[enemy.agent_id] = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=10,
            defence_token=None,
            major_action="Dialogue",
            target=None,
            weapon=None,
            minor_action=None,
            token_target=None,
            reasoning="Demanding surrender",
            shared_intel=None,
            dialogue_content="Drop your weapons or we open fire!",
        )

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=None,
        )

        assert result is not None
        assert result['action'] == 'dialogue'
        assert result['result'] == 'success'
        assert result['dialogue_content'] == "Drop your weapons or we open fire!"
        assert enemy.name in result['narration']

    def test_execute_dialogue_logs_to_jsonl(self):
        """Dialogue action should log to JSONL logger."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)
        manager.enemy_declarations[enemy.agent_id] = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=10,
            defence_token=None,
            major_action="Dialogue",
            target=None,
            weapon=None,
            minor_action=None,
            token_target=None,
            reasoning="Warning intruders",
            shared_intel=None,
            dialogue_content="Halt! Identify yourselves!",
        )

        mock_logger = MagicMock()
        mock_mechanics = MagicMock()
        mock_mechanics.jsonl_logger = mock_logger

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=mock_mechanics,
        )

        assert result is not None
        mock_logger.log_enemy_action.assert_called_once()
        call_kwargs = mock_logger.log_enemy_action.call_args
        assert call_kwargs[1]['action_type'] == 'dialogue' or call_kwargs[0][3] == 'dialogue'


class TestExecuteWait:
    """Tests for enemy wait action execution."""

    def test_execute_wait_returns_success(self):
        """Wait action should return a hold-position result."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)
        manager.enemy_declarations[enemy.agent_id] = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=10,
            defence_token=None,
            major_action="Wait",
            target=None,
            weapon=None,
            minor_action=None,
            token_target=None,
            reasoning="Observing before engaging",
            shared_intel=None,
        )

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=None,
        )

        assert result is not None
        assert result['action'] == 'wait'
        assert result['result'] == 'success'
        assert enemy.name in result['narration']

    def test_execute_wait_logs_to_jsonl(self):
        """Wait action should log to JSONL logger."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)
        manager.enemy_declarations[enemy.agent_id] = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=10,
            defence_token=None,
            major_action="Wait",
            target=None,
            weapon=None,
            minor_action=None,
            token_target=None,
            reasoning="Holding position",
            shared_intel=None,
        )

        mock_logger = MagicMock()
        mock_mechanics = MagicMock()
        mock_mechanics.jsonl_logger = mock_logger

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=mock_mechanics,
        )

        assert result is not None
        mock_logger.log_enemy_action.assert_called_once()
        call_kwargs = mock_logger.log_enemy_action.call_args
        assert call_kwargs[1]['action_type'] == 'wait' or call_kwargs[0][3] == 'wait'
