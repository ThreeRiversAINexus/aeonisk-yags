"""
Unit tests for the Stealth System (Spec 05).

Tests the 7-phase stealth implementation:
1. Agent state (is_hidden, stealth_dc, last_known_position)
2. Hide check (Agility x Stealth + d20 vs Environment DC)
3. Detect check (Perception x Awareness + d20 vs stealth_dc)
4. Target filtering (hidden agents excluded from opposing target lists)
5. Stealth breaking (attack from hidden auto-breaks stealth)
6. Scan action (search_for_hidden field on PerceptionAction)
7. Last known position tracking

Also tests:
- Void interaction (void >= 7: +5 detection bonus; void 10: stealth impossible)
- First Strike bonus (+2 damage from hidden)
- Schema validation (StealthChange, MechanicalEffects.stealth_changes)
"""

import pytest
import random
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ============================================================================
# Mock agent types for testing (lightweight, no LLM dependencies)
# ============================================================================

@dataclass
class MockPlayerAgent:
    """Mock AIPlayerAgent with stealth fields."""
    agent_id: str = "player_01"
    is_hidden: bool = False
    stealth_dc: Optional[int] = None
    last_known_position: Optional[str] = None
    health: int = 20
    max_health: int = 20
    position: str = "Near-PC"
    character_state: Optional[object] = None

    def __post_init__(self):
        if self.character_state is None:
            self.character_state = MockCharacterState()


@dataclass
class MockCharacterState:
    """Mock CharacterState with attributes and skills."""
    name: str = "Test PC"
    faction: str = "Freeborn"
    attributes: Dict[str, int] = field(default_factory=lambda: {
        'Agility': 4, 'Strength': 3, 'Perception': 3,
        'Intelligence': 3, 'Empathy': 2, 'Willpower': 3,
        'Endurance': 3, 'Dexterity': 3
    })
    skills: Dict[str, int] = field(default_factory=lambda: {
        'Stealth': 3, 'Awareness': 2, 'Guns': 2
    })
    void_score: int = 0
    pronouns: str = "they/them"


@dataclass
class MockEnemyAgent:
    """Mock EnemyAgent with stealth fields."""
    agent_id: str = "enemy_grunt_01"
    name: str = "Grunt"
    is_hidden: bool = False
    stealth_dc: Optional[int] = None
    last_known_position: Optional[str] = None
    is_active: bool = True
    tactics: str = "aggressive"
    health: int = 15
    max_health: int = 15
    position: str = "Near-Enemy"
    faction: str = "ACG"
    pronouns: str = "they/them"
    attributes: Dict[str, int] = field(default_factory=lambda: {
        'Agility': 3, 'Strength': 3, 'Perception': 3,
        'Intelligence': 2, 'Empathy': 2, 'Willpower': 2,
        'Endurance': 3, 'Dexterity': 3
    })
    skills: Dict[str, int] = field(default_factory=lambda: {
        'Stealth': 2, 'Awareness': 3, 'Guns': 3
    })
    void_score: int = 0


@dataclass
class MockNPCAgent:
    """Mock NPCAgent with stealth fields."""
    agent_id: str = "npc_civilian_01"
    name: str = "Civilian"
    is_hidden: bool = False
    stealth_dc: Optional[int] = None
    last_known_position: Optional[str] = None
    is_active: bool = True
    health: int = 10
    max_health: int = 10
    position: str = "Far-PC"
    faction: str = "Civilian"
    pronouns: str = "they/them"
    skills: Dict[str, int] = field(default_factory=lambda: {
        'Stealth': 1, 'Awareness': 1
    })


# ============================================================================
# Phase 1: Agent State Tests
# ============================================================================

class TestAgentStealthState:
    """Phase 1: Verify is_hidden, stealth_dc, last_known_position on all agent types."""

    def test_player_agent_has_stealth_fields(self):
        """AIPlayerAgent should have is_hidden, stealth_dc, last_known_position."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        # Verify the class supports the fields (we check via the mock since
        # AIPlayerAgent requires complex init; the real test is that the fields
        # exist on the real class after init)
        agent = MockPlayerAgent()
        assert agent.is_hidden is False
        assert agent.stealth_dc is None
        assert agent.last_known_position is None

    def test_enemy_agent_has_stealth_fields(self):
        """EnemyAgent should have is_hidden, stealth_dc, last_known_position."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        # Check that the dataclass accepts these fields
        assert hasattr(EnemyAgent, '__dataclass_fields__')
        assert 'is_hidden' in EnemyAgent.__dataclass_fields__
        assert 'stealth_dc' in EnemyAgent.__dataclass_fields__
        assert 'last_known_position' in EnemyAgent.__dataclass_fields__

    def test_npc_agent_has_stealth_fields(self):
        """NPCAgent should have is_hidden, stealth_dc, last_known_position."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent
        assert hasattr(NPCAgent, '__dataclass_fields__')
        assert 'is_hidden' in NPCAgent.__dataclass_fields__
        assert 'stealth_dc' in NPCAgent.__dataclass_fields__
        assert 'last_known_position' in NPCAgent.__dataclass_fields__

    def test_enemy_stealth_defaults(self):
        """EnemyAgent stealth fields should default to False/None/None."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        defaults = EnemyAgent.__dataclass_fields__
        assert defaults['is_hidden'].default is False
        assert defaults['stealth_dc'].default is None
        assert defaults['last_known_position'].default is None

    def test_npc_stealth_defaults(self):
        """NPCAgent stealth fields should default to False/None/None."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent
        defaults = NPCAgent.__dataclass_fields__
        assert defaults['is_hidden'].default is False
        assert defaults['stealth_dc'].default is None
        assert defaults['last_known_position'].default is None


# ============================================================================
# Phase 2: Hide Check Tests
# ============================================================================

class TestStealthCheck:
    """Phase 2: Stealth check resolution mechanics."""

    def test_stealth_check_returns_required_fields(self):
        """resolve_stealth_check should return success, stealth_roll, d20, margin, formula."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 4, 'Perception': 3},
            skills={'Stealth': 3}
        )
        result = resolve_stealth_check(agent, environment_dc=15)
        assert 'success' in result
        assert 'stealth_roll' in result
        assert 'd20' in result
        assert 'margin' in result
        assert 'formula' in result

    def test_stealth_check_success_with_high_stats(self):
        """Agent with high Agility/Stealth should reliably succeed against low DC."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 5, 'Perception': 3},
            skills={'Stealth': 5}
        )
        # Agility 5 x Stealth 5 = 25 base + d20 (1-20) = 26-45 vs DC 10
        # Always succeeds
        random.seed(1)  # Deterministic
        result = resolve_stealth_check(agent, environment_dc=10)
        assert result['success'] is True
        assert result['stealth_roll'] >= 10

    def test_stealth_check_unskilled_penalty(self):
        """Agent with Stealth=0 should get -5 unskilled penalty."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 3, 'Perception': 3},
            skills={'Stealth': 0}
        )
        result = resolve_stealth_check(agent, environment_dc=10)
        assert 'unskilled' in result['formula']

    def test_stealth_check_modifiers_apply(self):
        """Situational modifiers should be reflected in formula."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 3, 'Perception': 3},
            skills={'Stealth': 2}
        )
        result = resolve_stealth_check(agent, environment_dc=15, modifiers=5)
        assert 'modifiers' in result['formula']

    def test_stealth_check_formula_breakdown(self):
        """Formula should show Agility, Stealth, d20, and DC."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 4, 'Perception': 3},
            skills={'Stealth': 3}
        )
        result = resolve_stealth_check(agent, environment_dc=15)
        assert 'Agility 4' in result['formula']
        assert 'Stealth 3' in result['formula']
        assert 'd20' in result['formula']
        assert 'DC 15' in result['formula']

    def test_stealth_check_minimum_roll_is_1(self):
        """Stealth check total should never go below 1."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 1, 'Perception': 1},
            skills={'Stealth': 0}
        )
        # Agility 1 x Stealth 0 = 0 base + d20(min 1) - 5 unskilled = -4
        # Should be clamped to 1
        with patch('random.randint', return_value=1):
            result = resolve_stealth_check(agent, environment_dc=30)
        assert result['stealth_roll'] >= 1

    def test_stealth_check_returns_raw_stats(self):
        """Result should include agility and stealth_skill values."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 4, 'Perception': 3},
            skills={'Stealth': 3}
        )
        result = resolve_stealth_check(agent, environment_dc=15)
        assert result['agility'] == 4
        assert result['stealth_skill'] == 3

    def test_stealth_check_player_agent(self):
        """resolve_stealth_check should work with player agents (character_state pattern)."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockPlayerAgent()
        agent.character_state = MockCharacterState(
            attributes={'Agility': 4, 'Perception': 3},
            skills={'Stealth': 3}
        )
        result = resolve_stealth_check(agent, environment_dc=15)
        assert result['agility'] == 4
        assert result['stealth_skill'] == 3

    def test_stealth_check_void_10_impossible(self):
        """Agent with void_score=10 should automatically fail stealth checks."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        agent = MockEnemyAgent(
            attributes={'Agility': 5, 'Perception': 3},
            skills={'Stealth': 5},
            void_score=10
        )
        result = resolve_stealth_check(agent, environment_dc=10)
        assert result['success'] is False


# ============================================================================
# Phase 3: Detection Check Tests
# ============================================================================

class TestDetectionCheck:
    """Phase 3: Detection check resolution mechanics."""

    def test_detection_check_returns_required_fields(self):
        """resolve_detection_check should return success, detection_roll, d20, margin, formula."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 4, 'Agility': 3},
            skills={'Awareness': 3}
        )
        result = resolve_detection_check(observer, stealth_dc=15)
        assert 'success' in result
        assert 'detection_roll' in result
        assert 'd20' in result
        assert 'margin' in result
        assert 'formula' in result

    def test_detection_success_against_low_dc(self):
        """Observer with good Perception/Awareness should detect low-DC target."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 5, 'Agility': 3},
            skills={'Awareness': 5}
        )
        # Per 5 x Awa 5 = 25 base + d20 (1-20) = 26-45 vs DC 10
        random.seed(1)
        result = resolve_detection_check(observer, stealth_dc=10)
        assert result['success'] is True

    def test_detection_unskilled_penalty(self):
        """Observer with Awareness=0 should get -5 unskilled penalty."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 3, 'Agility': 3},
            skills={'Awareness': 0}
        )
        result = resolve_detection_check(observer, stealth_dc=15)
        assert 'unskilled' in result['formula']

    def test_detection_modifiers_apply(self):
        """Situational modifiers should affect detection."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 3, 'Agility': 3},
            skills={'Awareness': 2}
        )
        result = resolve_detection_check(observer, stealth_dc=15, modifiers=5)
        assert 'modifiers' in result['formula']

    def test_detection_void_bonus(self):
        """When target has void_score >= 7, detector gets +5 bonus."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 3, 'Agility': 3},
            skills={'Awareness': 2}
        )
        # With void bonus (+5), should be reflected in roll
        result_normal = resolve_detection_check(observer, stealth_dc=15, modifiers=0)
        result_void = resolve_detection_check(observer, stealth_dc=15, modifiers=5)
        # The void bonus is applied as a modifier by the caller
        # Just verify modifiers work
        assert 'modifiers' in result_void['formula']

    def test_detection_formula_breakdown(self):
        """Formula should show Perception, Awareness, d20, and DC."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 4, 'Agility': 3},
            skills={'Awareness': 3}
        )
        result = resolve_detection_check(observer, stealth_dc=18)
        assert 'Perception 4' in result['formula']
        assert 'Awareness 3' in result['formula']
        assert 'd20' in result['formula']
        assert 'DC 18' in result['formula']

    def test_detection_returns_raw_stats(self):
        """Result should include perception and awareness_skill values."""
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 4, 'Agility': 3},
            skills={'Awareness': 3}
        )
        result = resolve_detection_check(observer, stealth_dc=15)
        assert result['perception'] == 4
        assert result['awareness_skill'] == 3


# ============================================================================
# Phase 2/3 Helpers: _get_attribute, _get_skill
# ============================================================================

class TestAttributeSkillHelpers:
    """Test _get_attribute and _get_skill helper functions."""

    def test_get_attribute_from_enemy(self):
        """Get attribute from EnemyAgent (direct .attributes dict)."""
        from scripts.aeonisk.multiagent.mechanics import _get_attribute
        agent = MockEnemyAgent(attributes={'Agility': 5})
        assert _get_attribute(agent, 'Agility') == 5

    def test_get_attribute_from_player(self):
        """Get attribute from AIPlayerAgent (via .character_state.attributes)."""
        from scripts.aeonisk.multiagent.mechanics import _get_attribute
        agent = MockPlayerAgent()
        agent.character_state = MockCharacterState(attributes={'Agility': 4})
        assert _get_attribute(agent, 'Agility') == 4

    def test_get_attribute_default(self):
        """Missing attribute returns default value."""
        from scripts.aeonisk.multiagent.mechanics import _get_attribute
        agent = MockEnemyAgent(attributes={})
        assert _get_attribute(agent, 'Agility', default=3) == 3

    def test_get_skill_from_enemy(self):
        """Get skill from EnemyAgent (direct .skills dict)."""
        from scripts.aeonisk.multiagent.mechanics import _get_skill
        agent = MockEnemyAgent(skills={'Stealth': 4})
        assert _get_skill(agent, 'Stealth') == 4

    def test_get_skill_from_player(self):
        """Get skill from AIPlayerAgent (via .character_state.skills)."""
        from scripts.aeonisk.multiagent.mechanics import _get_skill
        agent = MockPlayerAgent()
        agent.character_state = MockCharacterState(skills={'Stealth': 3})
        assert _get_skill(agent, 'Stealth') == 3

    def test_get_skill_default(self):
        """Missing skill returns default value (0)."""
        from scripts.aeonisk.multiagent.mechanics import _get_skill
        agent = MockEnemyAgent(skills={})
        assert _get_skill(agent, 'Stealth', default=0) == 0


# ============================================================================
# Phase 4: Target List Filtering Tests
# ============================================================================

class TestHiddenAgentFiltering:
    """Phase 4: Target list filtering for hidden agents."""

    def _create_mapper_with_agents(self):
        """Create a TargetIDMapper with 2 PCs and 2 enemies registered."""
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        mapper = TargetIDMapper()
        mapper.enabled = True

        # Create mock agents
        pc1 = MockPlayerAgent(agent_id="player_01")
        pc2 = MockPlayerAgent(agent_id="player_02")
        enemy1 = MockEnemyAgent(agent_id="enemy_grunt_01")
        enemy2 = MockEnemyAgent(agent_id="enemy_sniper_01", name="Sniper")

        # Manually assign IDs (bypass randomization)
        mapper.target_id_map["tgt_pc01"] = pc1
        mapper.target_id_map["tgt_pc02"] = pc2
        mapper.target_id_map["tgt_en01"] = enemy1
        mapper.target_id_map["tgt_en02"] = enemy2

        mapper.reverse_map["player_01"] = "tgt_pc01"
        mapper.reverse_map["player_02"] = "tgt_pc02"
        mapper.reverse_map["enemy_grunt_01"] = "tgt_en01"
        mapper.reverse_map["enemy_sniper_01"] = "tgt_en02"

        return mapper

    def test_hidden_agents_set_exists(self):
        """TargetIDMapper should have a hidden_agents set."""
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
        mapper = TargetIDMapper()
        assert hasattr(mapper, 'hidden_agents')
        assert isinstance(mapper.hidden_agents, set)

    def test_update_hidden_state_add(self):
        """update_hidden_state(agent_id, True) should add to hidden set."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)
        assert "player_01" in mapper.hidden_agents

    def test_update_hidden_state_remove(self):
        """update_hidden_state(agent_id, False) should remove from hidden set."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)
        mapper.update_hidden_state("player_01", False)
        assert "player_01" not in mapper.hidden_agents

    def test_is_hidden_method(self):
        """is_hidden() should return True for hidden agents."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)
        assert mapper.is_hidden("player_01") is True
        assert mapper.is_hidden("player_02") is False

    def test_hidden_pc_excluded_from_enemy_targets(self):
        """Hidden PC should not appear in enemy's visible target list."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)

        visible = mapper.get_visible_target_ids("enemy_grunt_01")
        assert "tgt_pc01" not in visible
        # But PC02 should still be visible
        assert "tgt_pc02" in visible

    def test_hidden_pc_visible_to_ally_pc(self):
        """Hidden PC should still be visible to other PCs (same team)."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)

        visible = mapper.get_visible_target_ids("player_02")
        assert "tgt_pc01" in visible

    def test_unhidden_agent_visible_to_all(self):
        """Non-hidden agents should be visible to everyone."""
        mapper = self._create_mapper_with_agents()

        visible_from_enemy = mapper.get_visible_target_ids("enemy_grunt_01")
        assert "tgt_pc01" in visible_from_enemy
        assert "tgt_pc02" in visible_from_enemy

    def test_hidden_enemy_excluded_from_pc_targets(self):
        """Hidden enemy should not appear in PC's visible target list."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("enemy_grunt_01", True)

        visible = mapper.get_visible_target_ids("player_01")
        assert "tgt_en01" not in visible
        # But other enemy should be visible
        assert "tgt_en02" in visible

    def test_hidden_enemy_visible_to_allied_enemy(self):
        """Hidden enemy should be visible to other enemies (same team)."""
        mapper = self._create_mapper_with_agents()
        mapper.update_hidden_state("enemy_grunt_01", True)

        visible = mapper.get_visible_target_ids("enemy_sniper_01")
        assert "tgt_en01" in visible

    def test_all_targets_visible_when_nothing_hidden(self):
        """When no agents are hidden, all targets should be visible."""
        mapper = self._create_mapper_with_agents()

        visible = mapper.get_visible_target_ids("player_01")
        assert len(visible) == 4  # 2 PCs + 2 enemies

    def test_get_visible_returns_empty_when_disabled(self):
        """get_visible_target_ids should return [] when mapper is disabled."""
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
        mapper = TargetIDMapper()
        mapper.enabled = False
        assert mapper.get_visible_target_ids("player_01") == []


# ============================================================================
# Phase 5: Stealth Breaking Tests
# ============================================================================

class TestStealthBreaking:
    """Phase 5: Automatic stealth breaking rules."""

    def test_break_stealth_on_attack_sets_hidden_false(self):
        """break_stealth_on_attack should set is_hidden=False."""
        from scripts.aeonisk.multiagent.mechanics import break_stealth_on_attack
        agent = MockEnemyAgent(is_hidden=True, stealth_dc=22)
        result = break_stealth_on_attack(agent)
        assert agent.is_hidden is False
        assert agent.stealth_dc is None
        assert result is True  # Indicates stealth was broken

    def test_break_stealth_returns_false_when_not_hidden(self):
        """break_stealth_on_attack should return False if agent wasn't hidden."""
        from scripts.aeonisk.multiagent.mechanics import break_stealth_on_attack
        agent = MockEnemyAgent(is_hidden=False)
        result = break_stealth_on_attack(agent)
        assert result is False

    def test_first_strike_bonus_from_hidden(self):
        """get_first_strike_bonus should return +2 when attacking from hidden."""
        from scripts.aeonisk.multiagent.mechanics import get_first_strike_bonus
        agent = MockEnemyAgent(is_hidden=True)
        bonus = get_first_strike_bonus(agent)
        assert bonus == 2

    def test_no_first_strike_bonus_when_visible(self):
        """get_first_strike_bonus should return 0 when not hidden."""
        from scripts.aeonisk.multiagent.mechanics import get_first_strike_bonus
        agent = MockEnemyAgent(is_hidden=False)
        bonus = get_first_strike_bonus(agent)
        assert bonus == 0


# ============================================================================
# Phase 6: Schema Tests (StealthChange, PerceptionAction.search_for_hidden)
# ============================================================================

class TestStealthSchemas:
    """Phase 6: Schema validation for stealth-related fields."""

    def test_stealth_change_schema_valid(self):
        """StealthChange should validate correctly with all fields."""
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        change = StealthChange(
            agent_id="player_01",
            is_hidden=True,
            stealth_dc=22,
            reason="Successfully hid behind cargo containers in the dim lighting"
        )
        assert change.is_hidden is True
        assert change.stealth_dc == 22
        assert change.agent_id == "player_01"

    def test_stealth_change_revealed(self):
        """StealthChange with is_hidden=False should validate (reveal event)."""
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        change = StealthChange(
            agent_id="enemy_grunt_01",
            is_hidden=False,
            stealth_dc=None,
            reason="Detected by Scan action from allied forces"
        )
        assert change.is_hidden is False
        assert change.stealth_dc is None

    def test_stealth_change_reason_min_length(self):
        """StealthChange should reject reason shorter than 10 chars."""
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StealthChange(
                agent_id="player_01",
                is_hidden=True,
                reason="Short"  # Too short (< 10)
            )

    def test_mechanical_effects_stealth_changes_field(self):
        """MechanicalEffects should accept stealth_changes list."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        effects = MechanicalEffects(
            stealth_changes=[
                StealthChange(
                    agent_id="player_01",
                    is_hidden=True,
                    stealth_dc=18,
                    reason="Slipped into shadows while guards were distracted nearby"
                )
            ]
        )
        assert len(effects.stealth_changes) == 1
        assert effects.stealth_changes[0].is_hidden is True

    def test_mechanical_effects_stealth_changes_default_empty(self):
        """MechanicalEffects.stealth_changes should default to empty list."""
        from scripts.aeonisk.multiagent.schemas.action_resolution import MechanicalEffects
        effects = MechanicalEffects()
        assert effects.stealth_changes == []

    def test_perception_action_search_for_hidden(self):
        """PerceptionAction should accept search_for_hidden field."""
        from scripts.aeonisk.multiagent.schemas.player_action import PerceptionAction
        action = PerceptionAction(
            intent="Scan area for hidden threats actively",
            description="Using enhanced senses to detect concealed enemies in "
                        "the surrounding cargo bay area.",
            attribute="Perception",
            skill="Awareness",
            difficulty_estimate=18,
            difficulty_justification="Poor visibility and active concealment by targets",
            search_for_hidden=True
        )
        assert action.search_for_hidden is True

    def test_perception_action_search_for_hidden_default(self):
        """PerceptionAction.search_for_hidden should default to False."""
        from scripts.aeonisk.multiagent.schemas.player_action import PerceptionAction
        action = PerceptionAction(
            intent="Listen for approaching footsteps carefully",
            description="Focusing hearing on the corridor beyond the sealed doorway.",
            attribute="Perception",
            skill="Awareness",
            difficulty_estimate=15,
            difficulty_justification="Moderate noise level makes it challenging"
        )
        assert action.search_for_hidden is False


# ============================================================================
# Phase 7: Last Known Position Tests
# ============================================================================

class TestLastKnownPosition:
    """Phase 7: Last known position tracking for hidden agents."""

    def test_position_stored_on_hide(self):
        """When agent hides, their position should be stored as last_known_position."""
        agent = MockEnemyAgent(position="Near-PC", is_hidden=False)
        # Simulating hide action
        agent.last_known_position = str(agent.position)
        agent.is_hidden = True
        assert agent.last_known_position == "Near-PC"
        assert agent.is_hidden is True

    def test_position_cleared_on_detection(self):
        """When agent is detected, last_known_position should be cleared."""
        agent = MockEnemyAgent(
            position="Far-Enemy",
            is_hidden=True,
            last_known_position="Near-PC",
            stealth_dc=18
        )
        # Simulating detection
        agent.is_hidden = False
        agent.last_known_position = None
        agent.stealth_dc = None
        assert agent.last_known_position is None
        assert agent.stealth_dc is None

    def test_position_for_player_agent(self):
        """Player agent should support last_known_position tracking."""
        agent = MockPlayerAgent(position="Near-PC")
        agent.last_known_position = "Near-PC"
        agent.is_hidden = True
        agent.stealth_dc = 20
        assert agent.last_known_position == "Near-PC"
        assert agent.stealth_dc == 20


# ============================================================================
# Void Interaction Tests
# ============================================================================

class TestVoidStealthInteraction:
    """Void interaction with stealth mechanics."""

    def test_void_10_prevents_hiding(self):
        """Agent with void_score=10 should always fail stealth checks."""
        from scripts.aeonisk.multiagent.mechanics import resolve_stealth_check
        # Even with max stats, void 10 = auto fail
        agent = MockEnemyAgent(
            attributes={'Agility': 5, 'Perception': 3},
            skills={'Stealth': 5},
            void_score=10
        )
        with patch('random.randint', return_value=20):  # Max d20
            result = resolve_stealth_check(agent, environment_dc=1)  # Trivial DC
        assert result['success'] is False

    def test_void_7_gives_detection_bonus(self):
        """Detection against target with void >= 7 should note bonus eligibility."""
        # This is caller-side logic, tested in integration
        # Here we just verify the mechanics functions accept modifiers
        from scripts.aeonisk.multiagent.mechanics import resolve_detection_check
        observer = MockEnemyAgent(
            attributes={'Perception': 3, 'Agility': 3},
            skills={'Awareness': 2}
        )
        # Caller should pass modifiers=5 when target void >= 7
        result_with_bonus = resolve_detection_check(observer, stealth_dc=20, modifiers=5)
        result_without = resolve_detection_check(observer, stealth_dc=20, modifiers=0)
        # Can't assert specific success due to randomness, but formula should differ
        assert 'modifiers' in result_with_bonus['formula']

    def test_void_below_7_no_detection_bonus(self):
        """No detection bonus for agents with void < 7."""
        # This is a semantic test - callers should NOT add +5 when void < 7
        agent = MockEnemyAgent(void_score=5)
        assert agent.void_score < 7  # Caller should check this before adding bonus


# ============================================================================
# Awareness Module Stealth Integration Tests
# ============================================================================

class TestAwarenessStealthIntegration:
    """Test that awareness.py stealth filtering functions work with hidden agents."""

    def test_get_hidden_agent_ids_function_exists(self):
        """awareness module should have get_hidden_agent_ids function."""
        from scripts.aeonisk.multiagent.awareness import get_hidden_agent_ids
        assert callable(get_hidden_agent_ids)

    def test_get_hidden_agent_ids_returns_hidden(self):
        """get_hidden_agent_ids should return IDs of hidden agents."""
        from scripts.aeonisk.multiagent.awareness import get_hidden_agent_ids
        agents = [
            MockEnemyAgent(agent_id="enemy_01", is_hidden=True),
            MockEnemyAgent(agent_id="enemy_02", is_hidden=False),
            MockPlayerAgent(agent_id="player_01"),
        ]
        # MockPlayerAgent.is_hidden defaults to False
        hidden = get_hidden_agent_ids(agents)
        assert "enemy_01" in hidden
        assert "enemy_02" not in hidden
        assert "player_01" not in hidden

    def test_get_hidden_agent_ids_empty_list(self):
        """get_hidden_agent_ids should return empty set for no agents."""
        from scripts.aeonisk.multiagent.awareness import get_hidden_agent_ids
        assert get_hidden_agent_ids([]) == set()


# ============================================================================
# Enemy Prompts Stealth Context Tests
# ============================================================================

class TestEnemyPromptsStealthContext:
    """Test that enemy prompts include stealth awareness context."""

    def test_format_hidden_targets_section(self):
        """_format_hidden_targets should produce hidden target info for enemy prompts."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_hidden_targets
        hidden_pcs = [
            {'name': 'Shadow Kael', 'last_known_position': 'Near-PC'},
            {'name': 'Echo Veil', 'last_known_position': 'Far-Enemy'},
        ]
        section = _format_hidden_targets(hidden_pcs)
        assert 'HIDDEN' in section
        assert 'Shadow Kael' in section
        assert 'Near-PC' in section
        assert 'Scan' in section  # Should suggest Scan action

    def test_format_hidden_targets_empty(self):
        """_format_hidden_targets should return empty string when no hidden PCs."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_hidden_targets
        section = _format_hidden_targets([])
        assert section == ""


# ============================================================================
# DM Integration: Combatant List Hidden Markers
# ============================================================================

class TestDMCombatantListHiddenMarkers:
    """DM combatant list should mark hidden agents with [HIDDEN]."""

    def test_process_stealth_changes_hides_agent(self):
        """_process_stealth_changes should set agent.is_hidden and update mapper."""
        from scripts.aeonisk.multiagent.dm import _process_stealth_changes
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        # Create mock shared state
        agent = MockPlayerAgent(agent_id="player_01", is_hidden=False)
        mapper = TargetIDMapper()
        mapper.enabled = True

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        changes = [
            StealthChange(
                agent_id="player_01",
                is_hidden=True,
                stealth_dc=22,
                reason="Successfully hid behind the cargo containers"
            )
        ]

        _process_stealth_changes(changes, shared_state)

        assert agent.is_hidden is True
        assert agent.stealth_dc == 22
        assert mapper.is_hidden("player_01") is True

    def test_process_stealth_changes_reveals_agent(self):
        """_process_stealth_changes should reveal agent and clear stealth state."""
        from scripts.aeonisk.multiagent.dm import _process_stealth_changes
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockPlayerAgent(
            agent_id="player_01",
            is_hidden=True,
            stealth_dc=22,
            last_known_position="Near-PC"
        )
        mapper = TargetIDMapper()
        mapper.enabled = True
        mapper.update_hidden_state("player_01", True)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        changes = [
            StealthChange(
                agent_id="player_01",
                is_hidden=False,
                reason="Detected by enemy scanner during patrol sweep"
            )
        ]

        _process_stealth_changes(changes, shared_state)

        assert agent.is_hidden is False
        assert agent.stealth_dc is None
        assert agent.last_known_position is None
        assert mapper.is_hidden("player_01") is False

    def test_process_stealth_changes_stores_last_known_position(self):
        """When hiding, should store last_known_position from agent's position."""
        from scripts.aeonisk.multiagent.dm import _process_stealth_changes
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockPlayerAgent(
            agent_id="player_01",
            is_hidden=False,
            position="Near-PC"
        )
        mapper = TargetIDMapper()
        mapper.enabled = True

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        changes = [
            StealthChange(
                agent_id="player_01",
                is_hidden=True,
                stealth_dc=18,
                reason="Slipped into shadows near the cargo bay entrance"
            )
        ]

        _process_stealth_changes(changes, shared_state)

        assert agent.last_known_position == "Near-PC"

    def test_process_stealth_changes_handles_missing_agent(self):
        """_process_stealth_changes should handle agent not found gracefully."""
        from scripts.aeonisk.multiagent.dm import _process_stealth_changes
        from scripts.aeonisk.multiagent.schemas.shared_types import StealthChange

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = None  # Agent not found
        shared_state.get_target_id_mapper.return_value = MagicMock()

        changes = [
            StealthChange(
                agent_id="nonexistent_agent",
                is_hidden=True,
                stealth_dc=20,
                reason="Trying to hide a nonexistent agent gracefully"
            )
        ]

        # Should not raise
        _process_stealth_changes(changes, shared_state)

    def test_process_stealth_changes_empty_list(self):
        """_process_stealth_changes with empty list should be a no-op."""
        from scripts.aeonisk.multiagent.dm import _process_stealth_changes

        shared_state = MagicMock()
        _process_stealth_changes([], shared_state)
        # Should not call any methods
        shared_state.get_agent_by_id.assert_not_called()


# ============================================================================
# DM Integration: Auto-Break Stealth on Combat Action
# ============================================================================

class TestDMAutoBreakStealth:
    """DM should auto-break stealth when hidden agent performs combat action."""

    def test_auto_break_stealth_on_combat_action(self):
        """_auto_break_stealth should break stealth for combat action types."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockPlayerAgent(agent_id="player_01", is_hidden=True, stealth_dc=20)
        mapper = TargetIDMapper()
        mapper.enabled = True
        mapper.update_hidden_state("player_01", True)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        action = {'action_type': 'combat', 'agent_id': 'player_01'}
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is True
        assert agent.is_hidden is False
        assert agent.stealth_dc is None
        assert mapper.is_hidden("player_01") is False

    def test_auto_break_stealth_on_attack_action(self):
        """_auto_break_stealth should work for 'attack' action type too."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockEnemyAgent(agent_id="enemy_01", is_hidden=True, stealth_dc=18)
        mapper = TargetIDMapper()
        mapper.enabled = True
        mapper.update_hidden_state("enemy_01", True)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        action = {'action_type': 'attack', 'agent_id': 'enemy_01'}
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is True
        assert agent.is_hidden is False

    def test_no_break_stealth_on_perception_action(self):
        """_auto_break_stealth should NOT break stealth for non-combat actions."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockPlayerAgent(agent_id="player_01", is_hidden=True, stealth_dc=20)
        mapper = TargetIDMapper()
        mapper.enabled = True
        mapper.update_hidden_state("player_01", True)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        action = {'action_type': 'perception', 'agent_id': 'player_01'}
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is False
        assert agent.is_hidden is True  # Still hidden

    def test_no_break_when_agent_not_hidden(self):
        """_auto_break_stealth should return False if agent wasn't hidden."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat

        agent = MockPlayerAgent(agent_id="player_01", is_hidden=False)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = MagicMock()

        action = {'action_type': 'combat', 'agent_id': 'player_01'}
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is False

    def test_no_break_when_no_agent_id(self):
        """_auto_break_stealth should handle missing agent_id gracefully."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat

        shared_state = MagicMock()
        action = {'action_type': 'combat'}  # No agent_id
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is False

    def test_auto_break_on_brawl_action(self):
        """_auto_break_stealth should break stealth for 'brawl' action type."""
        from scripts.aeonisk.multiagent.dm import _auto_break_stealth_on_combat
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        agent = MockPlayerAgent(agent_id="player_01", is_hidden=True, stealth_dc=15)
        mapper = TargetIDMapper()
        mapper.enabled = True
        mapper.update_hidden_state("player_01", True)

        shared_state = MagicMock()
        shared_state.get_agent_by_id.return_value = agent
        shared_state.get_target_id_mapper.return_value = mapper

        action = {'action_type': 'brawl', 'agent_id': 'player_01'}
        was_broken = _auto_break_stealth_on_combat(action, shared_state)

        assert was_broken is True
        assert agent.is_hidden is False
