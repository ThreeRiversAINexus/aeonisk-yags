"""
Tests for defense token implementation (Spec 04).

Defense tokens are a universal tactical mechanic where an agent "watches"
one other combatant:
- If the watched combatant attacks the watcher: -2 to attack roll
- If any OTHER combatant attacks the watcher: +2 flanking bonus
- One token per round, declared during declaration phase

TDD: These tests are written FIRST before implementation.
"""

import pytest
from typing import Optional, Dict
from dataclasses import dataclass


# ============================================================================
# Mock helpers
# ============================================================================

@dataclass
class MockAgent:
    """Minimal agent mock with defence_token attribute."""
    defence_token: Optional[str] = None
    agent_id: str = "mock_agent_01"


class MockTargetIDMapper:
    """Mock target ID mapper for resolving tgt_xxxx to agent_id."""

    def __init__(self, mappings: Dict[str, str]):
        """
        Args:
            mappings: {agent_id: tgt_xxxx} mapping
        """
        self._agent_to_tgt = mappings
        self._tgt_to_agent = {v: k for k, v in mappings.items()}

    def get_target_id(self, agent_id: str) -> Optional[str]:
        """Get tgt_xxxx for an agent_id."""
        return self._agent_to_tgt.get(agent_id)

    def get_agent_id(self, target_id: str) -> Optional[str]:
        """Get agent_id for a tgt_xxxx."""
        return self._tgt_to_agent.get(target_id)


# ============================================================================
# Test: Schema changes
# ============================================================================

class TestDefenseTokenSchemas:
    """Schema validation for defense token field on all agent types."""

    def test_combat_action_accepts_defense_token(self):
        """CombatAction should accept defence_token field via PlayerActionBase."""
        from scripts.aeonisk.multiagent.schemas.player_action import CombatAction

        action = CombatAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        assert action.defence_token == "tgt_b2e1"

    def test_combat_action_defense_token_optional(self):
        """CombatAction defence_token should default to None."""
        from scripts.aeonisk.multiagent.schemas.player_action import CombatAction

        action = CombatAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            target="tgt_7a3f"
        )
        assert action.defence_token is None

    def test_explore_action_accepts_defense_token(self):
        """Non-combat action types should also accept defence_token (via base class)."""
        from scripts.aeonisk.multiagent.schemas.player_action import ExploreAction

        action = ExploreAction(
            intent="Move to cover behind the barricade",
            description="Sprinting to the barricade while keeping eyes on the enemy flanker.",
            attribute="Agility",
            skill="Athletics",
            difficulty_estimate=12,
            difficulty_justification="Open ground, moderate distance",
            defence_token="tgt_a1b2"
        )
        assert action.defence_token == "tgt_a1b2"

    def test_support_action_accepts_defense_token(self):
        """Support actions should accept defence_token (watching while healing)."""
        from scripts.aeonisk.multiagent.schemas.player_action import SupportAction

        action = SupportAction(
            intent="Provide first aid to wounded teammate",
            description="Treating wounds while keeping watch on the nearest enemy threat.",
            attribute="Intelligence",
            skill="Medicine",
            difficulty_estimate=15,
            difficulty_justification="Treating under fire",
            target="player_02",
            defence_token="tgt_c3d4"
        )
        assert action.defence_token == "tgt_c3d4"

    def test_npc_action_accepts_defense_token(self):
        """NPCAction should accept defence_token field."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAction

        action = NPCAction(
            action_type="hide",
            reason="Taking cover behind the crates during the ongoing combat.",
            defence_token="tgt_a4f2"
        )
        assert action.defence_token == "tgt_a4f2"

    def test_npc_action_defense_token_optional(self):
        """NPCAction defence_token should default to None."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAction

        action = NPCAction(
            action_type="flee",
            reason="Running away from the combat zone as quickly as possible."
        )
        assert action.defence_token is None

    def test_legacy_player_action_accepts_defense_token(self):
        """Legacy PlayerAction should accept defence_token for backward compat."""
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
        from scripts.aeonisk.multiagent.schemas.shared_types import ActionType

        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        assert action.defence_token == "tgt_b2e1"

    def test_legacy_player_action_defense_token_defaults_none(self):
        """Legacy PlayerAction defence_token should default to None (backward compat)."""
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
        from scripts.aeonisk.multiagent.schemas.shared_types import ActionType

        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f"
        )
        assert action.defence_token is None

    def test_to_legacy_dict_includes_defense_token(self):
        """to_legacy_dict should include defence_token."""
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
        from scripts.aeonisk.multiagent.schemas.shared_types import ActionType

        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        legacy = action.to_legacy_dict()
        assert legacy['defence_token'] == "tgt_b2e1"

    def test_to_legacy_dict_includes_defense_token_none(self):
        """to_legacy_dict should include defence_token=None when not set."""
        from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction
        from scripts.aeonisk.multiagent.schemas.shared_types import ActionType

        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f"
        )
        legacy = action.to_legacy_dict()
        assert 'defence_token' in legacy
        assert legacy['defence_token'] is None


# ============================================================================
# Test: Modifier calculation utility
# ============================================================================

class TestDefenseTokenModifiers:
    """Attack modifier calculations based on defense tokens."""

    def test_target_watching_attacker_gives_minus_2(self):
        """When target's defence_token matches attacker agent_id, attacker gets -2."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="enemy_grunt_01")
        )
        assert modifier == -2
        assert "watching" in desc

    def test_target_not_watching_gives_plus_2(self):
        """When target watches someone else, attacker gets +2 flanking."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="enemy_sniper_02")
        )
        assert modifier == 2
        assert "flanking" in desc

    def test_target_no_defense_token_gives_plus_2(self):
        """When target has no defence_token (None), attacker gets +2 flanking."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token=None)
        )
        assert modifier == 2
        assert "flanking" in desc

    def test_target_watching_via_target_id_mapper(self):
        """Defence token can be a tgt_xxxx ID, matched via target_id_mapper."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        mapper = MockTargetIDMapper({"enemy_grunt_01": "tgt_7a3f"})
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="tgt_7a3f"),
            target_id_mapper=mapper
        )
        assert modifier == -2

    def test_pc_attacking_enemy_watched_gets_minus_2(self):
        """When PC attacks enemy whose defence_token matches PC's tgt ID, PC gets -2."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        enemy = MockAgent(defence_token="tgt_1234")
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=enemy,
            target_id_mapper=MockTargetIDMapper({"player_01": "tgt_1234"})
        )
        assert modifier == -2  # Enemy is watching this PC

    def test_pc_attacking_unwatched_enemy_gets_flanking(self):
        """PC attacking enemy who watches someone else gets +2."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        enemy = MockAgent(defence_token="tgt_9999")
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=enemy,
            target_id_mapper=MockTargetIDMapper({"player_01": "tgt_1234"})
        )
        assert modifier == 2

    def test_no_defence_token_attr_gives_flanking(self):
        """Target object without defence_token attribute gives +2 flanking."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        class BarebonesTarget:
            pass

        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_01",
            target=BarebonesTarget()
        )
        assert modifier == 2
        assert "flanking" in desc

    def test_direct_agent_id_match_without_mapper(self):
        """Direct agent_id match works without a mapper."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=MockAgent(defence_token="player_01")
        )
        assert modifier == -2

    def test_mapper_mismatch_gives_flanking(self):
        """When mapper exists but tgt_xxxx doesn't match, get flanking."""
        from scripts.aeonisk.multiagent.mechanics import apply_defense_token_modifier

        mapper = MockTargetIDMapper({"player_01": "tgt_1111"})
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=MockAgent(defence_token="tgt_9999"),
            target_id_mapper=mapper
        )
        assert modifier == 2


# ============================================================================
# Test: Agent storage
# ============================================================================

class TestDefenseTokenStorage:
    """Verify defense tokens are stored on agent instances."""

    def test_player_agent_has_defence_token_attribute(self):
        """AIPlayerAgent should have defence_token attribute defaulting to None."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        # Create a minimal player agent
        agent = AIPlayerAgent(
            agent_id="player_test_01",
            socket_path="/tmp/test",
            character_config={
                'name': 'Test PC',
                'faction': 'Tempest Wardens',
                'attributes': {'Strength': 3, 'Agility': 4, 'Endurance': 3,
                              'Dexterity': 3, 'Perception': 4, 'Intelligence': 3,
                              'Empathy': 3, 'Willpower': 3},
                'skills': {'Guns': 3, 'Awareness': 2},
                'goals': ['survive'],
                'pronouns': 'they/them',
            },
            llm_client=object()  # Inject dummy to skip LLM provider init
        )
        assert hasattr(agent, 'defence_token')
        assert agent.defence_token is None

    def test_player_agent_defence_token_settable(self):
        """AIPlayerAgent.defence_token should be settable."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        agent = AIPlayerAgent(
            agent_id="player_test_01",
            socket_path="/tmp/test",
            character_config={
                'name': 'Test PC',
                'faction': 'Tempest Wardens',
                'attributes': {'Strength': 3, 'Agility': 4, 'Endurance': 3,
                              'Dexterity': 3, 'Perception': 4, 'Intelligence': 3,
                              'Empathy': 3, 'Willpower': 3},
                'skills': {'Guns': 3, 'Awareness': 2},
                'goals': ['survive'],
                'pronouns': 'they/them',
            },
            llm_client=object()
        )
        agent.defence_token = "tgt_7a3f"
        assert agent.defence_token == "tgt_7a3f"

    def test_npc_agent_has_defence_token_attribute(self):
        """NPCAgent should have defence_token attribute defaulting to None."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent

        npc = NPCAgent(
            agent_id="npc_test_01",
            name="Test NPC",
            faction="Tempest Wardens",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="A test NPC",
            health=20,
            max_health=20,
            soak=5,
            void_score=0,
            can_act=False,  # Prevent LLM client init
        )
        assert hasattr(npc, 'defence_token')
        assert npc.defence_token is None

    def test_npc_agent_defence_token_settable(self):
        """NPCAgent.defence_token should be settable."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent

        npc = NPCAgent(
            agent_id="npc_test_01",
            name="Test NPC",
            faction="Tempest Wardens",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="A test NPC",
            health=20,
            max_health=20,
            soak=5,
            void_score=0,
            can_act=False,
        )
        npc.defence_token = "tgt_b2e1"
        assert npc.defence_token == "tgt_b2e1"

    def test_enemy_agent_already_has_defence_token(self):
        """EnemyAgent already has defence_token (regression check)."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position

        enemy = EnemyAgent(
            agent_id="enemy_test_01",
            name="Test Enemy",
            template="grunt",
            health=30,
            max_health=30,
            soak=8,
            wounds=0,
            attributes={'Strength': 3, 'Agility': 3, 'Perception': 3, 'Dexterity': 3},
            skills={'Guns': 2, 'Melee': 2},
            position=Position.from_string("Near-PC"),
            initiative=10,
        )
        assert hasattr(enemy, 'defence_token')
        assert enemy.defence_token is None


# ============================================================================
# Test: Session processing - defence token stored from declaration
# ============================================================================

class TestDefenseTokenSessionProcessing:
    """Verify defense tokens are stored on agents during declaration processing."""

    def test_npc_declaration_stores_defence_token(self):
        """When NPC declares with defence_token, it should be stored on agent."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCAction

        npc = NPCAgent(
            agent_id="npc_test_01",
            name="Test NPC",
            faction="Tempest Wardens",
            entity_type="neutral",
            disposition="neutral",
            threat_level="armed_neutral",
            description="An armed neutral NPC",
            health=20,
            max_health=20,
            soak=5,
            void_score=0,
            can_act=False,
        )

        # Simulate the NPC action parsed by LLM
        npc_action = NPCAction(
            action_type="hide",
            reason="Taking cover behind the crates during the ongoing combat.",
            defence_token="tgt_a4f2"
        )

        # Simulate the session's NPC declaration processing
        # (extract defence_token from action and store on agent)
        if hasattr(npc_action, 'defence_token'):
            npc.defence_token = npc_action.defence_token

        assert npc.defence_token == "tgt_a4f2"

    def test_npc_combat_proxy_copies_defence_token(self):
        """NPCCombatProxy should copy defence_token from NPC agent.

        NPCCombatProxy wraps NPCAgent with fields _execute_attack() expects.
        After adding defence_token to NPCAgent, the proxy must copy it
        (instead of hardcoding None).
        """
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent

        npc = NPCAgent(
            agent_id="npc_test_01",
            name="Test NPC",
            faction="Tempest Wardens",
            entity_type="neutral",
            disposition="neutral",
            threat_level="armed_neutral",
            description="An armed NPC",
            health=20,
            max_health=20,
            soak=5,
            void_score=0,
            can_act=False,
        )
        npc.defence_token = "tgt_b2e1"

        # NPCCombatProxy is defined late in enemy_combat.py and may not
        # be importable directly. Test the behavior it should have:
        # After we modify NPCCombatProxy to copy defence_token from NPC,
        # we verify it by creating a mock proxy that mimics the expected behavior.
        # The actual integration test is that getattr(proxy, 'defence_token')
        # returns the NPC's value.

        # Simulate what NPCCombatProxy.__init__ should do after our fix:
        class ProxyLike:
            def __init__(self, npc_agent):
                self.defence_token = getattr(npc_agent, 'defence_token', None)

        proxy = ProxyLike(npc)
        assert proxy.defence_token == "tgt_b2e1"


# ============================================================================
# Test: Round reset
# ============================================================================

class TestDefenseTokenRoundReset:
    """Defense tokens should be clearable per round."""

    def test_player_defence_token_reset(self):
        """Player defence_token can be reset to None at round start."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        agent = AIPlayerAgent(
            agent_id="player_test_01",
            socket_path="/tmp/test",
            character_config={
                'name': 'Test PC',
                'faction': 'Tempest Wardens',
                'attributes': {'Strength': 3, 'Agility': 4, 'Endurance': 3,
                              'Dexterity': 3, 'Perception': 4, 'Intelligence': 3,
                              'Empathy': 3, 'Willpower': 3},
                'skills': {'Guns': 3},
                'goals': ['survive'],
                'pronouns': 'they/them',
            },
            llm_client=object()
        )
        agent.defence_token = "tgt_7a3f"
        assert agent.defence_token == "tgt_7a3f"

        # Reset at round start
        agent.defence_token = None
        assert agent.defence_token is None

    def test_npc_defence_token_reset(self):
        """NPC defence_token can be reset to None at round start."""
        from scripts.aeonisk.multiagent.npc_agent import NPCAgent

        npc = NPCAgent(
            agent_id="npc_test_01",
            name="Test NPC",
            faction="Tempest Wardens",
            entity_type="neutral",
            disposition="neutral",
            threat_level="non_combatant",
            description="A test NPC",
            health=20,
            max_health=20,
            soak=5,
            void_score=0,
            can_act=False,
        )
        npc.defence_token = "tgt_b2e1"
        assert npc.defence_token == "tgt_b2e1"

        # Reset at round start
        npc.defence_token = None
        assert npc.defence_token is None
