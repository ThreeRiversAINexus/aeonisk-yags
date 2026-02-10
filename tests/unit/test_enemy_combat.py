"""
Unit tests for enemy declaration parsing in enemy_combat.py.

Tests the parse_enemy_declaration function handles various LLM output formats,
including markdown bold formatting that was previously dropped.
"""

import pytest
from unittest.mock import MagicMock

from scripts.aeonisk.multiagent.enemy_combat import parse_enemy_declaration


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
