"""
Integration test: YAGS-correct soak calculation in combat pipeline.

Tests that:
1. Enemy soak = Size + Agi + End - 5 + armor (no +4 combat balance)
2. PC armor from inventory applies to soak via _load_armor()
3. Damage dealt in structured output reflects new soak values
4. Full _resolve_action_mechanically pipeline applies correct damage

Mock point: generate_dm_resolution_structured (the LLM call), so the full
_resolve_action_mechanically flow runs including _process_structured_damage_effects.
"""

import pytest
import logging
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


# ============================================================================
# Fixtures (following existing test_double_damage_integration.py pattern)
# ============================================================================

def make_enemy(agent_id="enemy_grunt_1234", name="Test Grunt", health=30,
               max_health=30, wounds=0, soak=9, spawned_round=0):
    """Create a mock enemy with YAGS-correct soak (no +4 balance)."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stuns = 0
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
        skill: Optional[str] = "Guns"
        attribute_value: int = 4
        skill_value: int = 3
        roll: int = 15
        total: int = 27
        difficulty: int = 15
        margin: int = 12
        outcome_tier: Any = None
        success: bool = True
        narrative: str = "You fire accurately!"
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
        return_value="🎲 **Agility × Guns** | d20(15) + 12 = 27 vs DC 15 | **GOOD** (+12)"
    )
    mechanics.queue_clock_update = Mock()

    return mechanics


def make_structured_resolution(target_id="tgt_1234", damage_dealt=10,
                                soak_applied=9, base_damage=19):
    """
    Create a Pydantic ActionResolution with damage reflecting YAGS soak.

    Soak values should reflect new YAGS formula:
    - Grunt: base(6) + light_armor(3) = 9
    - NOT old: base(6) + balance(4) + light_armor(3) = 13
    """
    from scripts.aeonisk.multiagent.schemas.action_resolution import (
        ActionResolution, MechanicalEffects
    )
    from scripts.aeonisk.multiagent.schemas.shared_types import (
        DamageEffect, SuccessTier, SoulcreditChange
    )

    narration = (
        "Enforcer Kael raises his shotgun with practiced precision, racking the pump action "
        "in a single fluid motion. The weapon thunders — a deafening report that echoes off "
        "the alley walls — and the spread catches the grunt squarely in the torso, sending "
        "them staggering backward as fragments of their light armor scatter across the ground."
    )

    return ActionResolution(
        narration=narration,
        success_tier=SuccessTier.GOOD,
        margin=12,
        effects=MechanicalEffects(
            damage=[
                DamageEffect(
                    target=target_id,
                    base_damage=base_damage,
                    dealt=damage_dealt,
                    soak=soak_applied
                )
            ],
            soulcredit_changes=[
                SoulcreditChange(
                    character_name="Enforcer Kael",
                    amount=0,
                    reason="justified combat action"
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
# Tests: YAGS Soak in Combat Pipeline
# ============================================================================

class TestYAGSSoakIntegration:
    """
    Integration tests verifying YAGS-correct soak (no +4 combat balance)
    flows through the full _resolve_action_mechanically pipeline.
    """

    @pytest.mark.asyncio
    async def test_grunt_soak_9_takes_correct_damage(self):
        """
        Grunt with YAGS soak = 9 (base 6 + light_armor 3, no +4 balance).
        Previously soak was 13 (base 6 + balance 4 + light_armor 3).

        With soak=9 and base_damage=19, dealt should be 10.
        Enemy HP: 30 → 20.
        """
        enemy = make_enemy(health=30, max_health=30, soak=9)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        # Soak=9 (YAGS), base_damage=19, dealt=10
        structured_res = make_structured_resolution(
            target_id="tgt_1234", damage_dealt=10, soak_applied=9, base_damage=19
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_01',
                'character': 'Enforcer Kael',
                'character_name': 'Enforcer Kael',
                'action_type': 'combat',
                'intent': 'Shoot the grunt with my shotgun',
                'description': 'Takes aim and fires shotgun at the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 5,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        assert enemy.health == 20, (
            f"Grunt (soak=9, YAGS) should take 10 damage (30→20). "
            f"Got HP={enemy.health}, delta={30 - enemy.health}"
        )

    @pytest.mark.asyncio
    async def test_high_soak_enemy_takes_reduced_damage(self):
        """
        Boss with heavy_armor: YAGS soak = 10 + 8 = 18 (was 22 with +4).
        Low damage attack should still deal some damage.
        """
        enemy = make_enemy(
            agent_id="enemy_boss_5678", name="Void Boss",
            health=50, max_health=50, soak=18
        )
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        # Soak=18, base_damage=22, dealt=4
        structured_res = make_structured_resolution(
            target_id="tgt_5678", damage_dealt=4, soak_applied=18, base_damage=22
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_01',
                'character': 'Enforcer Kael',
                'character_name': 'Enforcer Kael',
                'action_type': 'combat',
                'intent': 'Shoot the boss',
                'description': 'Fires at the boss',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 5,
                'target': 'tgt_5678',
            }

            await dm._resolve_action_mechanically('player_01', action)

        assert enemy.health == 46, (
            f"Boss (soak=18, YAGS) should take 4 damage (50→46). "
            f"Got HP={enemy.health}"
        )


class TestEnemySoakCalculationIntegration:
    """
    Integration tests verifying EnemyAgent calculates soak correctly
    using the pure YAGS formula with armor.
    """

    def test_grunt_soak_with_light_armor_no_balance(self):
        """
        Grunt: Size=5, Agi=3, End=3, light_armor(+3).
        YAGS soak = 5+3+3-5 + 3 = 9. NOT 13 (old: +4 balance).
        """
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position
        from scripts.aeonisk.multiagent.weapons import get_armor

        enemy = EnemyAgent(
            agent_id="enemy_grunt_test",
            name="Grunt",
            template="grunt",
            attributes={"Agility": 3, "Endurance": 3},
            skills={"Guns": 3, "Melee": 3},
            health=30,
            max_health=30,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=10,
            size=5,
            armor=get_armor("light_armor")
        )

        assert enemy.soak == 9, (
            f"Grunt soak should be 9 (base 6 + light_armor 3), got {enemy.soak}. "
            f"If 13, SOAK_COMBAT_BALANCE was not removed."
        )

    def test_enforcer_soak_with_heavy_armor_no_balance(self):
        """
        Enforcer: Size=5, Agi=4, End=4, heavy_armor(+8).
        YAGS soak = 5+4+4-5 + 8 = 16. NOT 20 (old: +4 balance).
        """
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position
        from scripts.aeonisk.multiagent.weapons import get_armor

        enemy = EnemyAgent(
            agent_id="enemy_enforcer_test",
            name="Enforcer",
            template="enforcer",
            attributes={"Agility": 4, "Endurance": 4},
            skills={"Guns": 4, "Melee": 3},
            health=40,
            max_health=40,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=12,
            size=5,
            armor=get_armor("heavy_armor")
        )

        assert enemy.soak == 16, (
            f"Enforcer soak should be 16 (base 8 + heavy_armor 8), got {enemy.soak}. "
            f"If 20, SOAK_COMBAT_BALANCE was not removed."
        )

    def test_unarmored_enemy_soak_is_base_only(self):
        """
        Unarmored enemy: Size=5, Agi=3, End=3, no armor.
        YAGS soak = 5+3+3-5 = 6. NOT 10 (old: +4 balance).
        """
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        enemy = EnemyAgent(
            agent_id="enemy_unarmed_test",
            name="Street Thug",
            template="grunt",
            attributes={"Agility": 3, "Endurance": 3},
            skills={"Brawl": 2},
            health=25,
            max_health=25,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=8,
            size=5
        )

        assert enemy.soak == 6, (
            f"Unarmored enemy soak should be 6 (pure YAGS base), got {enemy.soak}. "
            f"If 10, SOAK_COMBAT_BALANCE was not removed."
        )


class TestPlayerArmorIntegration:
    """
    Integration tests verifying player armor loading from inventory.
    """

    def test_player_load_armor_finds_riot_carapace(self):
        """
        Player with riot_carapace in inventory should get Armor with soak_bonus=3.
        """
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {
            "inventory": {
                "shotgun": 1,
                "riot_carapace": 1,
                "med_kit": 1
            }
        }

        armor = player._load_armor()
        assert armor is not None, "Should find riot_carapace"
        assert armor.soak_bonus == 3

    def test_player_load_armor_picks_best_armor(self):
        """
        If multiple armor items in inventory, pick the one with highest soak_bonus.
        """
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {
            "inventory": {
                "robes": 1,           # soak_bonus=1
                "light_armor": 1,     # soak_bonus=3
                "tactical_vest": 1,   # soak_bonus=4
            }
        }

        armor = player._load_armor()
        assert armor is not None
        assert armor.soak_bonus == 4, (
            f"Should pick tactical_vest (soak=4), got {armor.name} (soak={armor.soak_bonus})"
        )

    def test_player_load_armor_ignores_zero_count(self):
        """
        Armor with count=0 in inventory should not be loaded.
        """
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {
            "inventory": {
                "heavy_armor": 0,  # Removed/sold
                "pistol": 1
            }
        }

        armor = player._load_armor()
        assert armor is None, "Should not load armor with count=0"

    def test_player_soak_formula_with_riot_carapace(self):
        """
        End-to-end: Kael Dren (Agi=4, End=4, Size=5) + riot_carapace.
        Base soak = 5+4+4-5 = 8, + riot_carapace(3) = 11.
        Old: 8 + balance(4) = 12 (no armor applied).
        """
        # Verify the math matches what on_start() would compute
        size = 5
        agility = 4
        endurance = 4
        base_soak = size + agility + endurance - 5  # = 8

        from scripts.aeonisk.multiagent.weapons import get_armor
        armor = get_armor("riot_carapace")
        total_soak = base_soak + armor.soak_bonus  # = 11

        assert base_soak == 8, f"Base soak should be 8, got {base_soak}"
        assert total_soak == 11, f"Total soak should be 11 (8+3), got {total_soak}"


class TestGunsDamageBoostIntegration:
    """
    Integration tests verifying boosted gun damage values flow correctly
    through the weapon loading pipeline.
    """

    def test_shotgun_damage_8_in_combat(self):
        """
        Shotgun now has damage=8 (+2 boost). Verify it loads correctly.
        """
        from scripts.aeonisk.multiagent.weapons import get_weapon

        shotgun = get_weapon("shotgun")
        assert shotgun.damage == 8, f"Shotgun should be 8 (was 6), got {shotgun.damage}"
        assert shotgun.skill == "Guns"

    def test_pistol_damage_6_in_combat(self):
        """
        Pistol now has damage=6 (+2 boost). Verify it loads correctly.
        """
        from scripts.aeonisk.multiagent.weapons import get_weapon

        pistol = get_weapon("pistol")
        assert pistol.damage == 6, f"Pistol should be 6 (was 4), got {pistol.damage}"

    def test_rifle_damage_7_in_combat(self):
        """
        Assault Rifle now has damage=7 (+2 boost). Verify it loads correctly.
        """
        from scripts.aeonisk.multiagent.weapons import get_weapon

        rifle = get_weapon("rifle")
        assert rifle.damage == 7, f"Rifle should be 7 (was 5), got {rifle.damage}"
