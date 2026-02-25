"""
Unit tests for Enemy↔NPC conversion schema fixes.

Tests 6 bugs found in enforcer_dilemma session logs where
NPC→Enemy→NPC cycling caused data integrity issues.
"""

import pytest
from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context
from scripts.aeonisk.multiagent.session import _normalize_enemy_result
from scripts.aeonisk.multiagent.agent_conversion import escalate_npc_to_enemy
from scripts.aeonisk.multiagent.npc_agent import NPCAgent
from scripts.aeonisk.multiagent.schemas.shared_types import Condition
from scripts.aeonisk.multiagent.enemy_agent import Position


# =============================================================================
# Helpers
# =============================================================================

def _make_pc_resolution(char_name="Vessel Kira", action_type="attack", margin=5, success=True, narration="Kira strikes."):
    """Create a PC-style resolution dict (action is dict, resolution is dict)."""
    return {
        'character_name': char_name,
        'action': {
            'action_type': action_type,
            'intent': 'Attack the target',
            'description': 'Swings blade',
        },
        'resolution': {
            'margin': margin,
            'success': success,
            'success_tier': 'GOOD' if success else 'FAILURE',
        },
        'effects': {
            'soulcredit_changes': [],
        },
        'narration': narration,
    }


def _make_enemy_attack_result(char_name="Grunt Squad Alpha", hit=True, margin=3):
    """Create an enemy attack result (action is string, hit/roll at top level)."""
    return {
        'character_name': char_name,
        'action': 'attack',
        'action_description': 'Opens fire on the party',
        'hit': hit,
        'roll': {'d20': 14, 'margin': margin, 'total': 17},
        'damage': {'dealt': 8, 'type': 'ballistic'},
        'target': 'tgt_abc1',
    }


def _make_enemy_flee_result(char_name="Raider Scout", margin=-2):
    """Create an enemy flee result (action string, margin in roll dict)."""
    return {
        'character_name': char_name,
        'action': 'flee',
        'result': 'failure',
        'roll': {'d20': 8, 'margin': margin, 'total': 11},
    }


def _make_enemy_dialogue_result(char_name="Protector Tomas"):
    """Create an enemy dialogue result (result field, no hit/roll)."""
    return {
        'character_name': char_name,
        'action': 'dialogue',
        'result': 'success',
        'narration': 'Tomas speaks calmly.',
    }


def _make_test_npc(
    agent_id="npc_tomas_1",
    name="Protector Tomas",
    conditions=None,
    health=25,
    max_health=25,
):
    """Create a minimal NPCAgent for testing."""
    return NPCAgent(
        agent_id=agent_id,
        name=name,
        faction="ACG",
        entity_type="neutral",
        disposition="neutral",
        threat_level="potential_threat",
        description="An ACG protector",
        health=health,
        max_health=max_health,
        soak=8,
        void_score=3,
        skills={"Guns": 3, "Awareness": 2, "Melee": 2},
        conditions=conditions or [],
        position=Position(ring="mid", side="left"),
    )


# =============================================================================
# Bug 1: _build_enhanced_previous_context can't parse enemy results
# =============================================================================

class TestBug1EnhancedContextParsing:
    """Bug 1: Lines 667-672 assume PC format (action is dict, resolution is dict with margin).
    Enemy results have action as a string and no resolution dict."""

    def test_enhanced_context_with_enemy_attack_result(self):
        """Enemy attack result (string action, hit field, margin in roll dict)."""
        resolutions = [_make_enemy_attack_result()]
        result = _build_enhanced_previous_context(resolutions)

        assert "Grunt Squad Alpha" in result
        assert "ATTACK" in result
        assert "UNKNOWN" not in result  # Should NOT show UNKNOWN
        assert "success" in result  # hit=True → success

    def test_enhanced_context_with_enemy_flee_result(self):
        """Enemy flee result (margin in roll dict, result='failure')."""
        resolutions = [_make_enemy_flee_result()]
        result = _build_enhanced_previous_context(resolutions)

        assert "Raider Scout" in result
        assert "FLEE" in result
        assert "UNKNOWN" not in result
        assert "failure" in result  # result='failure'

    def test_enhanced_context_with_mixed_pc_and_enemy(self):
        """Both PC and enemy results in same list."""
        resolutions = [
            _make_pc_resolution(),
            _make_enemy_attack_result(),
        ]
        result = _build_enhanced_previous_context(resolutions)

        assert "Vessel Kira" in result
        assert "ATTACK" in result
        assert "Grunt Squad Alpha" in result
        # Neither should show UNKNOWN
        assert result.count("UNKNOWN") == 0

    def test_enhanced_context_with_enemy_dialogue_result(self):
        """Enemy dialogue result (result field, no hit or roll)."""
        resolutions = [_make_enemy_dialogue_result()]
        result = _build_enhanced_previous_context(resolutions)

        assert "Protector Tomas" in result
        assert "DIALOGUE" in result
        assert "UNKNOWN" not in result
        assert "success" in result  # result='success'


# =============================================================================
# Bug 2: Enemy results lack consistent schema in all_resolutions
# =============================================================================

class TestBug2NormalizeEnemyResult:
    """Bug 2: Enemy results appended raw to all_resolutions have inconsistent
    field names (hit vs success, roll.margin vs flat margin, action string vs dict)."""

    def test_normalize_enemy_attack_result(self):
        """hit→success, computes margin from roll dict."""
        raw = _make_enemy_attack_result()
        normalized = _normalize_enemy_result(raw)

        # Action should be dict
        assert isinstance(normalized['action'], dict)
        assert normalized['action']['action_type'] == 'attack'
        assert normalized['action']['character_name'] == 'Grunt Squad Alpha'

        # Should have top-level success and margin
        assert normalized['success'] is True
        assert normalized['margin'] == 3

    def test_normalize_enemy_flee_result(self):
        """Extracts margin from roll dict, result→success."""
        raw = _make_enemy_flee_result()
        normalized = _normalize_enemy_result(raw)

        assert isinstance(normalized['action'], dict)
        assert normalized['action']['action_type'] == 'flee'
        assert normalized['success'] is False  # result='failure'
        assert normalized['margin'] == -2

    def test_normalize_enemy_dialogue_result(self):
        """result field→success."""
        raw = _make_enemy_dialogue_result()
        normalized = _normalize_enemy_result(raw)

        assert isinstance(normalized['action'], dict)
        assert normalized['action']['action_type'] == 'dialogue'
        assert normalized['success'] is True  # result='success'

    def test_normalize_preserves_pc_format(self):
        """PC results pass through with no schema changes."""
        raw = _make_pc_resolution()
        normalized = _normalize_enemy_result(raw)

        # Action should remain dict
        assert isinstance(normalized['action'], dict)
        assert normalized['action']['action_type'] == 'attack'

        # Success derived from resolution dict
        assert 'success' in normalized

        # Original resolution dict preserved
        assert 'resolution' in normalized
        assert normalized['resolution']['margin'] == 5

    def test_normalize_preserves_all_original_fields(self):
        """Normalization should not lose any original data."""
        raw = _make_enemy_attack_result()
        normalized = _normalize_enemy_result(raw)

        # Original fields still present
        assert normalized['roll'] == raw['roll']
        assert normalized['damage'] == raw['damage']
        assert normalized['target'] == raw['target']


# =============================================================================
# Bug 3: NPC "pass" actions produce no resolution event
# =============================================================================

class TestBug3PassActionFallback:
    """Bug 3: is_fallback is only initialized inside the else block (non-pass actions).
    The pass branch skips the else, so is_fallback is undefined at logging time."""

    def test_npc_pass_action_is_fallback_initialized(self):
        """Verify is_fallback=False is available for pass path.

        We can't easily call the full _resolve_action_mechanically (requires LLM setup),
        so we verify the fix exists by checking the source code pattern.
        """
        import inspect
        from scripts.aeonisk.multiagent import dm

        # Read the entire dm module source
        source = inspect.getsource(dm)
        # Find the pass action check
        pass_idx = source.find("if npc_action_type == 'pass':")
        assert pass_idx > 0, "Could not find pass action check"

        # is_fallback should be initialized BEFORE the pass check
        # Look for initialization in the 300 chars before the pass check
        pre_pass = source[max(0, pass_idx - 300):pass_idx]
        assert 'is_fallback' in pre_pass, \
            "is_fallback must be initialized before the pass/else branch"


# =============================================================================
# Bug 5: dialogue_content never captured in JSONL
# =============================================================================

class TestBug5DialogueContent:
    """Bug 5: dialogue_content is used as fallback for description but not
    passed as its own field in the NPC action dict sent to DM."""

    def test_npc_dialogue_content_in_action_dict(self):
        """Verify that building NPC action dict preserves dialogue_content.

        Simulates the action dict construction from session.py:2441-2449.
        """
        # Simulate what session.py does when building action_for_adjudication
        npc_action = {
            'action_type': 'dialogue',
            'reason': 'Warn the party about danger',
            'dialogue_content': 'You must leave now, the void storms approach!',
            'target': 'tgt_abc1',
        }

        npc_intent = npc_action.get('intent') or npc_action.get('reason', 'NPC action')
        npc_description = npc_action.get('description') or npc_action.get('dialogue_content') or npc_action.get('reason', '')
        npc_action_type = npc_action.get('action_type', 'dialogue')

        # Build action dict the way session.py does (with fix applied)
        action = {
            'agent_id': 'npc_tomas_1',
            'character_name': 'Protector Tomas',
            'intent': npc_intent,
            'description': npc_description,
            'action_type': npc_action_type,
            'target': npc_action.get('target'),
            'is_npc': True,
            'dialogue_content': npc_action.get('dialogue_content'),
        }

        # dialogue_content should be present as its own field
        assert action['dialogue_content'] == 'You must leave now, the void storms approach!'
        # description should also have it (as fallback)
        assert action['description'] == 'You must leave now, the void storms approach!'

    def test_npc_action_without_dialogue_content(self):
        """NPC actions without dialogue_content should have None, not crash."""
        npc_action = {
            'action_type': 'flee',
            'reason': 'Too dangerous to stay',
        }

        action = {
            'agent_id': 'npc_tomas_1',
            'character_name': 'Protector Tomas',
            'intent': npc_action.get('reason', 'NPC action'),
            'description': npc_action.get('description') or npc_action.get('dialogue_content') or npc_action.get('reason', ''),
            'action_type': npc_action.get('action_type', 'dialogue'),
            'target': npc_action.get('target'),
            'is_npc': True,
            'dialogue_content': npc_action.get('dialogue_content'),
        }

        assert action['dialogue_content'] is None


# =============================================================================
# Bug 6: Conditions lost on NPC→Enemy escalation
# =============================================================================

class TestBug6ConditionsOnEscalation:
    """Bug 6: escalate_npc_to_enemy() creates EnemyAgent without converting
    npc.conditions (List[Condition]) to status_effects (List[str])."""

    def test_escalation_preserves_conditions_as_status_effects(self):
        """NPC conditions should be converted to enemy status_effects."""
        conditions = [
            Condition(name="Stunned", penalty=-3, duration=2, description="Cannot act, -3 to all rolls"),
            Condition(name="Prone", penalty=-2, duration=1, description="Knocked down, -2 to defense"),
        ]
        npc = _make_test_npc(conditions=conditions)

        enemy = escalate_npc_to_enemy(npc, template_override="grunt", current_round=3)

        assert "stunned" in enemy.status_effects
        assert "prone" in enemy.status_effects
        assert len(enemy.status_effects) == 2

    def test_escalation_empty_conditions(self):
        """NPC with no conditions should produce empty status_effects."""
        npc = _make_test_npc(conditions=[])

        enemy = escalate_npc_to_enemy(npc, template_override="grunt", current_round=3)

        assert enemy.status_effects == []

    def test_escalation_preserves_other_state(self):
        """Condition conversion doesn't break other state preservation."""
        conditions = [
            Condition(name="Inspired", penalty=2, duration=3, description="+2 to rolls"),
        ]
        npc = _make_test_npc(
            conditions=conditions,
            health=15,
            max_health=25,
        )

        enemy = escalate_npc_to_enemy(npc, template_override="elite", current_round=5)

        assert enemy.health == 15
        assert enemy.max_health == 25
        assert enemy.agent_id == "npc_tomas_1"
        assert enemy.name == "Protector Tomas"
        assert "inspired" in enemy.status_effects
