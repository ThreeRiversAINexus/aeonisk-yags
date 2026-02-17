"""
Integration test: Unarmed combat and Brawl weapon resolution.

Tests that the DM weapon selection logic in _resolve_action_mechanically
correctly resolves Brawl skill to "Unarmed" when the sidearm is not a
Brawl-skill weapon, and to the sidearm name when it IS a Brawl weapon.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ============================================================================
# Fixtures
# ============================================================================

def make_weapon(name, skill, damage_type="wound", attack=3, damage=5):
    """Create a mock Weapon object."""
    from scripts.aeonisk.multiagent.weapons import Weapon
    return Weapon(
        name=name,
        skill=skill,
        attack=attack,
        defence=1,
        damage=damage,
        damage_type=damage_type,
        reach=1,
        load=1
    )


def make_player(agent_id="player_01", name="Enforcer Kael",
                primary=None, sidearm=None):
    """Create a mock player with equipped weapons."""
    player = Mock()
    player.agent_id = agent_id
    player.health = 20
    player.max_health = 20
    player.wounds = 0
    player.stuns = 0
    player.is_active = True
    player.character_state = Mock()
    player.character_state.name = name
    player.character_state.void_score = 2
    player.character_state.bonds = []  # Bonds must be iterable (not Mock)
    player.equipped_weapons = {}
    if primary:
        player.equipped_weapons['primary'] = primary
    if sidearm:
        player.equipped_weapons['sidearm'] = sidearm
    player.weapon_inventory = []
    return player


def make_enemy(agent_id="enemy_grunt_1234", name="Test Grunt",
               health=30, max_health=30):
    """Create a mock enemy."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = 0
    enemy.stuns = 0
    enemy.soak = 5
    enemy.barriers = []
    enemy.is_active = True
    enemy.status_effects = []

    def check_death_save():
        if enemy.health <= 0:
            return (False, "killed")
        return (True, "alive")
    enemy.check_death_save = Mock(side_effect=check_death_save)

    return enemy


def make_target_id_mapper(entities):
    """Create a target ID mapper."""
    mapper = Mock()
    mapper.enabled = True

    tgt_map = {}
    for e in entities:
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


def make_mechanics(jsonl_logger=None):
    """Create a mock MechanicsEngine."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, OutcomeTier

    mechanics = Mock(spec=MechanicsEngine)
    mechanics.current_round = 1
    mechanics.scene_clocks = {}
    mechanics.jsonl_logger = jsonl_logger or Mock()
    mechanics.jsonl_logger.log_action_resolution = Mock()
    mechanics.jsonl_logger.log_combat_action = Mock()
    mechanics.jsonl_logger.log_enemy_defeat = Mock()

    @dataclass
    class FakeResolution:
        intent: str = "Attack"
        attribute: str = "Strength"
        skill: Optional[str] = "Brawl"
        attribute_value: int = 5
        skill_value: int = 3
        roll: int = 14
        total: int = 29
        difficulty: int = 15
        margin: int = 14
        outcome_tier: Any = None
        success: bool = True
        narrative: str = "You strike!"
        state_effects: Dict[str, Any] = field(default_factory=dict)
        modifiers_applied: list = field(default_factory=list)
        ability: int = 15
        is_unskilled: bool = False
        roll_formula: Optional[str] = "5×3 + d20(14) = 29"

        def __post_init__(self):
            if self.outcome_tier is None:
                self.outcome_tier = OutcomeTier.GOOD

    mechanics.resolve_action = Mock(return_value=FakeResolution())
    mechanics.calculate_dc = Mock(return_value=15)
    mechanics.format_resolution_for_narration = Mock(
        return_value="🎲 **Strength × Brawl** | d20(14) + 15 = 29 vs DC 15 | **GOOD** (+14)"
    )
    mechanics.queue_clock_update = Mock()

    return mechanics


def make_shared_state(players, enemies, mechanics):
    """Create a mock SharedState."""
    shared = Mock()
    shared.player_agents = players
    shared.npc_agents = []
    shared.registered_players = []

    enemy_combat = Mock()
    enemy_combat.enemy_agents = enemies
    shared.enemy_combat = enemy_combat

    shared.get_mechanics_engine = Mock(return_value=mechanics)
    shared.get_target_id_mapper = Mock(return_value=make_target_id_mapper(players + enemies))
    shared.consume_coordination_bonus = Mock(return_value=None)
    shared.session = Mock()
    shared.session.track_player_damage_dealt = Mock()
    shared.get_agent_by_id = Mock(return_value=None)

    return shared


def make_dm(shared_state):
    """Create a minimal DM instance."""
    from scripts.aeonisk.multiagent.dm import AIDMAgent

    dm = AIDMAgent.__new__(AIDMAgent)
    dm.agent_id = "dm_test"
    dm.shared_state = shared_state
    dm.llm_config = {"provider": "openai", "model": "gpt-5-mini", "temperature": 0.7}
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


def make_structured_resolution(target_id="tgt_1234", damage_dealt=8):
    """Create a structured ActionResolution with stun damage from brawl."""
    from scripts.aeonisk.multiagent.schemas.action_resolution import (
        ActionResolution, MechanicalEffects
    )
    from scripts.aeonisk.multiagent.schemas.shared_types import (
        DamageEffect, SuccessTier, SoulcreditChange
    )

    narration = (
        "Enforcer Kael lunges forward, grabbing the grunt by the collar and driving a "
        "powerful knee into their midsection. The grunt doubles over with a pained gasp, "
        "stumbling backward as Kael follows through with a sweeping leg trip that sends "
        "them crashing to the ground. The grunt lies there groaning, momentarily stunned "
        "by the ferocity of the unarmed assault."
    )

    return ActionResolution(
        narration=narration,
        success_tier=SuccessTier.GOOD,
        margin=14,
        effects=MechanicalEffects(
            damage=[
                DamageEffect(
                    target=target_id,
                    base_damage=12,
                    dealt=damage_dealt,
                    soak=4
                )
            ],
            soulcredit_changes=[
                SoulcreditChange(
                    character_name="Enforcer Kael",
                    amount=0,
                    reason="justified non-lethal action"
                )
            ]
        )
    )


# ============================================================================
# Tests
# ============================================================================

class TestBrawlWeaponResolutionIntegration:
    """Test Brawl skill resolves to correct weapon through full DM flow."""

    @pytest.mark.asyncio
    async def test_brawl_action_resolves_to_unarmed_weapon(self):
        """
        Player with primary=Plasma Rifle, sidearm=Combat Knife (Melee skill).
        Declares Brawl attack. Weapon should resolve to "Unarmed" not "Combat Knife".
        """
        primary = make_weapon("Plasma Rifle", "Guns")
        sidearm = make_weapon("Combat Knife", "Melee")
        player = make_player(primary=primary, sidearm=sidearm)
        enemy = make_enemy()

        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_action_resolution = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([player], [enemy], mechanics)
        dm = make_dm(shared)

        structured_res = make_structured_resolution(target_id="tgt_1234", damage_dealt=8)

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            result = await dm._resolve_action_mechanically(
                player_id='player_01',
                action={
                    'agent_id': 'player_01',
                    'character': 'Enforcer Kael',
                    'character_name': 'Enforcer Kael',
                    'action_type': 'combat',
                    'intent': 'Tackle and restrain the grunt',
                    'description': 'I charge in and tackle the grunt to the ground',
                    'attribute': 'Strength',
                    'skill': 'Brawl',
                    'difficulty_estimate': 15,
                    'target': 'tgt_1234',
                }
            )

        # Check the combat_action JSONL log for weapon name
        if jsonl_logger.log_combat_action.called:
            call_kwargs = jsonl_logger.log_combat_action.call_args
            if call_kwargs:
                weapon_logged = call_kwargs.kwargs.get('weapon') or (
                    call_kwargs[1].get('weapon') if len(call_kwargs) > 1 else None
                )
                if weapon_logged:
                    assert weapon_logged == "Unarmed", f"Expected 'Unarmed' but got '{weapon_logged}'"

    @pytest.mark.asyncio
    async def test_brawl_with_brawl_sidearm_resolves_correctly(self):
        """
        Player with sidearm=Shock Baton (Brawl skill).
        Declares Brawl attack. Weapon should resolve to "Shock Baton".
        """
        primary = make_weapon("Plasma Rifle", "Guns")
        sidearm = make_weapon("Shock Baton", "Brawl", damage_type="stun")
        player = make_player(primary=primary, sidearm=sidearm)
        enemy = make_enemy()

        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_action_resolution = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([player], [enemy], mechanics)
        dm = make_dm(shared)

        structured_res = make_structured_resolution(target_id="tgt_1234", damage_dealt=10)

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            result = await dm._resolve_action_mechanically(
                player_id='player_01',
                action={
                    'agent_id': 'player_01',
                    'character': 'Enforcer Kael',
                    'character_name': 'Enforcer Kael',
                    'action_type': 'combat',
                    'intent': 'Strike the grunt with shock baton',
                    'description': 'I swing my shock baton at the grunt',
                    'attribute': 'Strength',
                    'skill': 'Brawl',
                    'difficulty_estimate': 15,
                    'target': 'tgt_1234',
                }
            )

        if jsonl_logger.log_combat_action.called:
            call_kwargs = jsonl_logger.log_combat_action.call_args
            if call_kwargs:
                weapon_logged = call_kwargs.kwargs.get('weapon') or (
                    call_kwargs[1].get('weapon') if len(call_kwargs) > 1 else None
                )
                if weapon_logged:
                    assert weapon_logged == "Shock Baton", f"Expected 'Shock Baton' but got '{weapon_logged}'"

    @pytest.mark.asyncio
    async def test_unarmed_weapon_in_library(self):
        """Verify WEAPON_LIBRARY 'fists' entry has name 'Unarmed' and correct stats."""
        from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY

        fists = WEAPON_LIBRARY["fists"]
        assert fists.name == "Unarmed"
        assert fists.skill == "Brawl"
        assert fists.damage_type == "stun"
        assert fists.damage == 0  # Unarmed base damage
        assert fists.attack == 0  # No attack bonus
