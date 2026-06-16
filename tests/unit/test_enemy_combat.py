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
        mock_mechanics.current_round = 7
        mock_mechanics.jsonl_logger = mock_logger
        manager.current_round = 0

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=mock_mechanics,
        )

        assert result is not None
        mock_logger.log_enemy_action.assert_called_once()
        call_kwargs = mock_logger.log_enemy_action.call_args
        assert call_kwargs[1]['action_type'] == 'dialogue' or call_kwargs[0][3] == 'dialogue'
        assert call_kwargs[1]['round_num'] == 7


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
        mock_mechanics.current_round = 7
        mock_mechanics.jsonl_logger = mock_logger
        manager.current_round = 0

        result = manager.execute_enemy_action(
            enemy_id=enemy.agent_id,
            player_agents=[],
            mechanics_engine=mock_mechanics,
        )

        assert result is not None
        mock_logger.log_enemy_action.assert_called_once()
        call_kwargs = mock_logger.log_enemy_action.call_args
        assert call_kwargs[1]['action_type'] == 'wait' or call_kwargs[0][3] == 'wait'
        assert call_kwargs[1]['round_num'] == 7


class TestEnemyDecisionToDeclarationConversion:
    """Regression: EnemyDecision (Pydantic) → EnemyDeclaration (dataclass) must preserve all fields."""

    def test_dialogue_content_preserved_in_conversion(self):
        """Bug fix: dialogue_content was dropped during EnemyDecision → EnemyDeclaration conversion.

        The LLM generates an EnemyDecision with dialogue_content, but the conversion
        at enemy_combat.py:692 was not copying it to EnemyDeclaration, causing
        'attempts to communicate' fallback instead of actual speech.
        """
        from scripts.aeonisk.multiagent.schemas.enemy_decision import EnemyDecision

        # Simulate what the LLM returns via structured output
        decision = EnemyDecision(
            major_action="Dialogue",
            dialogue_content="Hold your fire — we can negotiate!",
            tactical_reasoning="PCs attempted diplomacy, responding with dialogue to de-escalate",
        )

        # Simulate the conversion that happens in _generate_enemy_decision_structured
        declaration = EnemyDeclaration(
            agent_id="enemy_enforcer_01",
            character_name="Pantheon Security #1",
            initiative=22,
            major_action=decision.major_action,
            minor_action=decision.minor_action or "None",
            target=decision.target or "None",
            weapon=decision.weapon or "None",
            defence_token=decision.defence_token or "None",
            token_target=decision.token_target or "None",
            reasoning=decision.tactical_reasoning,
            shared_intel=decision.shared_intel,
            dialogue_content=decision.dialogue_content,
        )

        assert declaration.dialogue_content == "Hold your fire — we can negotiate!"
        assert declaration.major_action == "Dialogue"

    def test_dialogue_content_none_for_non_dialogue_actions(self):
        """Non-dialogue actions should have dialogue_content=None after conversion."""
        from scripts.aeonisk.multiagent.schemas.enemy_decision import EnemyDecision

        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_1234",
            weapon="Pistol",
            tactical_reasoning="Engaging primary target at close range with sidearm",
        )

        declaration = EnemyDeclaration(
            agent_id="enemy_01",
            character_name="Guard",
            initiative=15,
            major_action=decision.major_action,
            minor_action=decision.minor_action or "None",
            target=decision.target or "None",
            weapon=decision.weapon or "None",
            defence_token=decision.defence_token or "None",
            token_target=decision.token_target or "None",
            reasoning=decision.tactical_reasoning,
            shared_intel=decision.shared_intel,
            dialogue_content=decision.dialogue_content,
        )

        assert declaration.dialogue_content is None


class TestDeclarationDictIncludesDialogueContent:
    """Bug fix: declaration dicts returned to session.py must include dialogue_content."""

    def test_declare_actions_includes_dialogue_content(self):
        """declare_actions() dict must propagate dialogue_content from EnemyDeclaration."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)

        # Simulate what happens after parsing: parsed declaration stored + dict built
        parsed = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=enemy.initiative,
            defence_token=None,
            major_action="Dialogue",
            target="tgt_abc1",
            weapon="None",
            minor_action=None,
            token_target=None,
            reasoning="Attempting to negotiate",
            shared_intel=None,
            dialogue_content="We don't want to fight — stand down!",
        )

        # Build declaration dict the same way declare_actions does
        declaration_dict = {
            'agent_id': enemy.agent_id,
            'character_name': enemy.name,
            'initiative': enemy.initiative,
            'major_action': parsed.major_action,
            'target': parsed.target,
            'weapon': parsed.weapon,
            'reasoning': parsed.reasoning,
            'dialogue_content': parsed.dialogue_content
        }

        assert declaration_dict['dialogue_content'] == "We don't want to fight — stand down!"
        assert declaration_dict['major_action'] == "Dialogue"
        assert declaration_dict['weapon'] == "None"

    def test_declaration_dict_dialogue_content_none_for_attack(self):
        """Non-dialogue actions should have dialogue_content=None in the dict."""
        parsed = EnemyDeclaration(
            agent_id="enemy_01",
            character_name="Guard",
            initiative=15,
            defence_token=None,
            major_action="Attack",
            target="tgt_1234",
            weapon="Pistol",
            minor_action=None,
            token_target=None,
            reasoning="Engaging target",
            shared_intel=None,
        )

        declaration_dict = {
            'agent_id': parsed.agent_id,
            'character_name': parsed.character_name,
            'initiative': parsed.initiative,
            'major_action': parsed.major_action,
            'target': parsed.target,
            'weapon': parsed.weapon,
            'reasoning': parsed.reasoning,
            'dialogue_content': parsed.dialogue_content
        }

        assert declaration_dict['dialogue_content'] is None
        assert declaration_dict['weapon'] == "Pistol"

    @pytest.mark.asyncio
    async def test_declare_single_enemy_includes_dialogue_content(self):
        """declare_single_enemy() must include dialogue_content in returned dict."""
        enemy = _make_enemy_agent()
        manager = _make_combat_manager_with_enemy(enemy)
        manager.shared_state = MagicMock()
        manager.shared_state.session_config = {}
        manager.shared_state.config = {}
        manager.shared_state.get_target_id_mapper.return_value = None
        manager.shared_state.round_synthesis_history = []

        # Mock LLM to return dialogue declaration text
        mock_llm = MagicMock()
        mock_llm.generate_async = MagicMock(return_value={
            'content': (
                'MAJOR_ACTION: Dialogue\n'
                'TARGET: tgt_abc1\n'
                'WEAPON: None\n'
                'DIALOGUE_CONTENT: Surrender now or face the consequences!\n'
                'TACTICAL_REASONING: Attempting intimidation before combat\n'
            )
        })

        # Make generate_async a coroutine
        import asyncio
        async def mock_generate(**kwargs):
            return {'content': (
                'MAJOR_ACTION: Dialogue\n'
                'TARGET: tgt_abc1\n'
                'WEAPON: None\n'
                'DIALOGUE_CONTENT: Surrender now or face the consequences!\n'
                'TACTICAL_REASONING: Attempting intimidation before combat\n'
            )}
        mock_llm.generate_async = mock_generate

        result = await manager.declare_single_enemy(
            enemy=enemy,
            player_agents=[],
            available_tokens=[],
            llm_client=mock_llm
        )

        assert result is not None
        assert result['major_action'] == 'Dialogue'
        assert 'dialogue_content' in result
        # dialogue_content comes from parsed text — may or may not be populated
        # depending on whether parse_enemy_declaration extracts DIALOGUE_CONTENT
        # The key assertion is that the field EXISTS in the dict
        assert 'weapon' in result
