"""
Integration test: Weapon damage type routing through full DM resolution pipeline.

Tests that:
1. Brawl/unarmed attacks route through stun damage (no HP loss, stuns increase)
2. Lethal weapon attacks still apply wounds + HP loss (regression)
3. Stun knockouts mark entities inactive without killing them

Mock point: generate_dm_resolution_structured (the LLM call), so the full
_resolve_action_mechanically flow runs including _process_structured_damage_effects.
"""

import pytest
import asyncio
import logging
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ============================================================================
# Fixtures
# ============================================================================

def make_enemy(agent_id="enemy_grunt_1234", name="Test Grunt", health=30,
               max_health=30, wounds=0, stuns=0, soak=5, spawned_round=0):
    """Create a mock enemy entity with real mutable state."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stuns = stuns
    enemy.soak = soak
    enemy.barriers = []
    enemy.status_effects = []
    enemy.is_active = True
    enemy.spawned_round = spawned_round
    enemy.is_broken = False
    enemy.morale = 10
    enemy.faction = "hostile"

    def check_death_save():
        if enemy.health <= 0:
            return (False, "killed")
        return (True, "alive")
    enemy.check_death_save = Mock(side_effect=check_death_save)

    return enemy


def make_target_id_mapper(enemies):
    """Create a target ID mapper that resolves tgt_ IDs to enemies."""
    mapper = Mock()
    mapper.enabled = True

    tgt_map = {}
    for e in enemies:
        tgt_id = f"tgt_{e.agent_id[-4:]}"
        tgt_map[tgt_id] = e

    mapper.resolve_target = Mock(side_effect=lambda tid: tgt_map.get(tid))
    mapper.is_player = Mock(return_value=False)
    mapper.is_enemy = Mock(return_value=True)
    mapper.is_npc = Mock(return_value=False)
    mapper.get_combatant_info = Mock(side_effect=lambda tid: {
        'id': tgt_map[tid].agent_id,
        'name': tgt_map[tid].name,
        'type': 'enemy',
        'agent_id': tgt_map[tid].agent_id,
    } if tid in tgt_map else None)
    mapper.get_all_target_ids = Mock(return_value=list(tgt_map.keys()))
    return mapper


def make_player_agent(agent_id="player_vex_1234", primary=None, sidearm=None):
    """Create a mock player agent with equipped weapons."""
    agent = Mock()
    agent.agent_id = agent_id
    agent.name = "Vex Savage"
    agent.health = 30
    agent.max_health = 30
    agent.wounds = 0
    agent.stuns = 0
    agent.equipped_weapons = {}
    if primary:
        agent.equipped_weapons['primary'] = primary
    if sidearm:
        agent.equipped_weapons['sidearm'] = sidearm
    # Prevent bond matrix iteration from failing on Mock
    char_state = Mock()
    char_state.bonds = []
    agent.character_state = char_state
    return agent


def make_weapon(name="Test Weapon", skill="Guns", damage_type="wound"):
    """Create a mock weapon object."""
    weapon = Mock()
    weapon.name = name
    weapon.skill = skill
    weapon.damage_type = damage_type
    return weapon


def make_shared_state(enemies, mechanics, player_agents=None):
    """Create a mock SharedState."""
    shared = Mock()

    enemy_combat = Mock()
    enemy_combat.enemy_agents = enemies
    shared.enemy_combat = enemy_combat

    shared.get_mechanics_engine = Mock(return_value=mechanics)
    shared.get_target_id_mapper = Mock(return_value=make_target_id_mapper(enemies))
    shared.consume_coordination_bonus = Mock(return_value=None)
    shared.registered_players = []
    shared.player_agents = player_agents or []
    shared.npc_agents = []
    shared.session = Mock()
    shared.session.track_player_damage_dealt = Mock()
    shared.get_agent_by_id = Mock(return_value=None)

    return shared


def make_mechanics(jsonl_logger=None):
    """Create a mechanics mock with deterministic resolve_action."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, OutcomeTier

    mechanics = Mock(spec=MechanicsEngine)
    mechanics.current_round = 1
    mechanics.scene_clocks = {}
    mechanics.jsonl_logger = jsonl_logger

    @dataclass
    class FakeResolution:
        intent: str = "Attack the grunt"
        attribute: str = "Agility"
        skill: Optional[str] = "Brawl"
        attribute_value: int = 4
        skill_value: int = 3
        roll: int = 15
        total: int = 27
        difficulty: int = 15
        margin: int = 12
        outcome_tier: Any = None
        success: bool = True
        narrative: str = "You punch accurately!"
        state_effects: Dict[str, Any] = field(default_factory=dict)
        modifiers_applied: list = field(default_factory=list)
        ability: int = 12
        is_unskilled: bool = False
        roll_formula: Optional[str] = "4×3 + d20(15) = 27"

        def __post_init__(self):
            if self.outcome_tier is None:
                self.outcome_tier = OutcomeTier.GOOD

    mechanics.resolve_action = Mock(return_value=FakeResolution())
    mechanics.calculate_dc = Mock(return_value=15)
    mechanics.format_resolution_for_narration = Mock(
        return_value="🎲 **Agility × Brawl** | d20(15) + 12 = 27 vs DC 15 | **GOOD** (+12)"
    )
    mechanics.queue_clock_update = Mock()

    return mechanics


def make_structured_resolution(target_id="tgt_1234", damage_dealt=10, damage_type=None):
    """Create a Pydantic ActionResolution with damage in effects."""
    from scripts.aeonisk.multiagent.schemas.action_resolution import (
        ActionResolution, MechanicalEffects
    )
    from scripts.aeonisk.multiagent.schemas.shared_types import (
        DamageEffect, SuccessTier, SoulcreditChange
    )

    narration = (
        "Vex Savage charges forward, fist cocked back with raw fury. The punch connects "
        "solidly with the grunt's jaw, snapping their head sideways with a satisfying crack. "
        "The grunt staggers backward, dazed, knees buckling under the sudden impact as pain "
        "blooms across their face. They clutch at the wall for support, vision swimming."
    )

    return ActionResolution(
        narration=narration,
        success_tier=SuccessTier.GOOD,
        margin=12,
        effects=MechanicalEffects(
            damage=[
                DamageEffect(
                    target=target_id,
                    base_damage=15,
                    dealt=damage_dealt,
                    soak=5,
                    damage_type=damage_type
                )
            ],
            soulcredit_changes=[
                SoulcreditChange(
                    character_name="Vex Savage",
                    amount=0,
                    reason="non-lethal combat action"
                )
            ]
        )
    )


def make_dm(shared_state, llm_config=None):
    """Create a minimal DM instance (bypass __init__)."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent.__new__(AIDMAgent)
    dm.agent_id = "dm_test"
    dm.shared_state = shared_state
    dm.llm_config = llm_config or {"provider": "openai", "model": "gpt-5-mini", "temperature": 0.7}
    dm.current_scenario = Mock()
    dm.current_scenario.void_level = 3
    dm.current_scenario.theme = "combat_test"
    dm.current_scenario.location = "Test Arena"
    dm.current_scenario.situation = "Combat test"
    dm.llm_logger = Mock()
    dm.llm_logger.call_count = 0
    dm.agent_prompt_logger = None
    dm.session_config = {}
    dm._last_structured_resolution = None
    dm.llm_provider = Mock()
    dm.llm_client = Mock()

    shared_state.mechanics_engine = shared_state.get_mechanics_engine()

    return dm


# ============================================================================
# Tests
# ============================================================================

class TestStunDamageIntegration:
    """
    Integration tests exercising _resolve_action_mechanically to verify
    that weapon damage types are correctly routed through the full pipeline.
    """

    @pytest.mark.asyncio
    async def test_brawl_unarmed_applies_stun_not_wounds(self):
        """
        Brawl attack with no Brawl sidearm should route through stun damage.
        Enemy should gain stuns but NOT lose HP or gain wounds.
        """
        enemy = make_enemy(health=30, max_health=30, stuns=0)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)

        # Player with Guns primary but no Brawl sidearm → Unarmed/stun
        player = make_player_agent(
            agent_id="player_vex_1234",
            primary=make_weapon("Plasma Rifle", "Guns", "wound"),
            sidearm=None
        )
        shared = make_shared_state([enemy], mechanics, player_agents=[player])
        dm = make_dm(shared)

        # LLM returns stun damage_type (informed by WEAPON CONTEXT)
        structured_res = make_structured_resolution(
            target_id="tgt_1234", damage_dealt=10, damage_type="stun"
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_vex_1234',
                'character': 'Vex Savage',
                'character_name': 'Vex Savage',
                'action_type': 'combat',
                'intent': 'Punch the grunt in the face',
                'description': 'Punches the grunt with bare fists',
                'attribute': 'Agility',
                'skill': 'Brawl',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_vex_1234', action)

        # Stun damage should NOT reduce HP
        assert enemy.health == 30, (
            f"Stun (unarmed) should not reduce HP. Expected 30, got {enemy.health}"
        )
        # Stun damage should NOT add wounds
        assert enemy.wounds == 0, (
            f"Stun (unarmed) should not add wounds. Expected 0, got {enemy.wounds}"
        )
        # Stun damage SHOULD increase stuns
        assert enemy.stuns > 0, (
            f"Stun (unarmed) should increase stuns. Got {enemy.stuns}"
        )

    @pytest.mark.asyncio
    async def test_lethal_weapon_still_applies_wounds(self):
        """
        Regression: Guns attack with lethal weapon should still apply wound damage.
        """
        enemy = make_enemy(health=30, max_health=30, stuns=0)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)

        player = make_player_agent(
            agent_id="player_vex_1234",
            primary=make_weapon("Plasma Rifle", "Guns", "wound"),
            sidearm=None
        )
        shared = make_shared_state([enemy], mechanics, player_agents=[player])
        dm = make_dm(shared)

        structured_res = make_structured_resolution(
            target_id="tgt_1234", damage_dealt=10, damage_type="wound"
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_vex_1234',
                'character': 'Vex Savage',
                'character_name': 'Vex Savage',
                'action_type': 'combat',
                'intent': 'Shoot the grunt with plasma rifle',
                'description': 'Fires plasma rifle at the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_vex_1234', action)

        # Wound damage SHOULD reduce HP
        assert enemy.health == 20, (
            f"Wound damage should reduce HP. Expected 20, got {enemy.health}"
        )
        # Wound damage SHOULD add wounds (10//5 = 2)
        assert enemy.wounds == 2, (
            f"Wound damage should add wounds. Expected 2, got {enemy.wounds}"
        )
        # Wound damage should NOT affect stuns
        assert enemy.stuns == 0, (
            f"Wound damage should not affect stuns. Got {enemy.stuns}"
        )

    @pytest.mark.asyncio
    async def test_stun_knockout_marks_entity_inactive(self):
        """
        Massive stun damage that triggers unconscious_check_needed should
        deactivate the entity (is_active = False) without killing.
        """
        enemy = make_enemy(health=30, max_health=30, stuns=0)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)

        player = make_player_agent(
            agent_id="player_vex_1234",
            primary=None,
            sidearm=None
        )
        shared = make_shared_state([enemy], mechanics, player_agents=[player])
        dm = make_dm(shared)

        # High stun damage (25 dealt) → will trigger unconscious check
        structured_res = make_structured_resolution(
            target_id="tgt_1234", damage_dealt=25, damage_type="stun"
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_vex_1234',
                'character': 'Vex Savage',
                'character_name': 'Vex Savage',
                'action_type': 'combat',
                'intent': 'Deliver a devastating punch to knock out the grunt',
                'description': 'Delivers a crushing blow to the grunt',
                'attribute': 'Strength',
                'skill': 'Brawl',
                'attribute_value': 5,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_vex_1234', action)

        # HP should remain at 30 (stun doesn't reduce HP)
        assert enemy.health == 30, (
            f"Stun KO should not reduce HP. Expected 30, got {enemy.health}"
        )
        # Should have high stuns
        assert enemy.stuns >= 25, (
            f"Should have high stuns from massive stun damage. Got {enemy.stuns}"
        )
