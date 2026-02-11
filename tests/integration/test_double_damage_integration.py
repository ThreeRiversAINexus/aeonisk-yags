"""
Integration test: Double damage application bug.

Tests that _resolve_action_mechanically applies damage exactly ONCE when
structured output is active. The bug was: the new pipeline
(_process_structured_damage_effects) and the legacy text-parsing pipeline
(parse_combat_triplet / parse_mechanical_effect → effect dict → damage
application) BOTH fired on the same action, doubling damage.

This test would have caught the original bug because it exercises the full
_resolve_action_mechanically flow with a mocked LLM that returns a structured
ActionResolution containing damage, whose narration also contains
"takes X damage" text (which triggers the legacy parse_combat_triplet regex).
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
               max_health=30, wounds=0, soak=5, spawned_round=0):
    """Create a mock enemy entity with real mutable state."""
    enemy = Mock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.health = health
    enemy.max_health = max_health
    enemy.wounds = wounds
    enemy.stun = 0
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

    # Build map: tgt_<last4 of agent_id> → enemy
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


def make_shared_state(enemies, mechanics):
    """Create a mock SharedState."""
    shared = Mock()

    enemy_combat = Mock()
    enemy_combat.enemy_agents = enemies
    shared.enemy_combat = enemy_combat

    shared.get_mechanics_engine = Mock(return_value=mechanics)
    shared.get_target_id_mapper = Mock(return_value=make_target_id_mapper(enemies))
    shared.consume_coordination_bonus = Mock(return_value=None)
    shared.registered_players = []
    shared.player_agents = []
    shared.npc_agents = []
    shared.session = Mock()
    shared.session.track_player_damage_dealt = Mock()
    shared.get_agent_by_id = Mock(return_value=None)

    return shared


def make_mechanics(jsonl_logger=None):
    """Create a real-ish MechanicsEngine mock with deterministic resolve_action."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, OutcomeTier

    mechanics = Mock(spec=MechanicsEngine)
    mechanics.current_round = 1
    mechanics.scene_clocks = {}
    mechanics.jsonl_logger = jsonl_logger

    # Deterministic resolve_action: always a successful hit
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


def make_structured_resolution(target_id="tgt_1234", damage_dealt=10):
    """
    Create a Pydantic ActionResolution with damage in effects.

    The narration intentionally includes "takes X damage" text, which
    triggers the legacy parse_combat_triplet regex. This is exactly
    what the real code does — _process_structured_damage_effects appends
    damage messages to the narration.
    """
    from scripts.aeonisk.multiagent.schemas.action_resolution import (
        ActionResolution, MechanicalEffects
    )
    from scripts.aeonisk.multiagent.schemas.shared_types import (
        DamageEffect, SuccessTier, SoulcreditChange
    )

    # Narration must be >= 200 chars per schema. Pad with vivid combat prose.
    narration = (
        "Enforcer Kael raises his sidearm with practiced precision, the barrel tracking "
        "smoothly to center mass. The weapon bucks once — a sharp crack splitting the air "
        "— and the round catches the grunt squarely in the shoulder, spinning them sideways "
        "as fragments of ablative armor scatter across the ferrocrete floor."
        # This line is what _process_structured_damage_effects appends in real code:
        f"\n\n⚔️ **Test Grunt takes {damage_dealt} damage!** "
        f"(30 HP → {30 - damage_dealt} HP, +{damage_dealt // 5} wounds)"
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
                    soak=5
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
    dm.llm_provider = Mock()  # Needed for structured output path
    dm.llm_client = Mock()

    # Mock mechanics_engine on shared_state for clock context
    shared_state.mechanics_engine = shared_state.get_mechanics_engine()

    return dm


# ============================================================================
# Test: Double Damage (Bug 1)
# ============================================================================

class TestDoubleDamageIntegration:
    """
    Integration test exercising _resolve_action_mechanically to verify
    damage is applied exactly once when structured output is active.
    """

    @pytest.mark.asyncio
    async def test_enemy_takes_damage_exactly_once(self):
        """
        Core regression test: a single player combat action should
        reduce enemy HP by exactly the dealt amount, not 2x.

        Setup:
        - Enemy at 30 HP
        - Structured resolution says dealt=10 damage
        - Narration contains "takes 10 damage" (triggers legacy parser)

        Expected: enemy HP = 20 (not 10 from double application)

        Mock point: generate_dm_resolution_structured (the LLM call),
        so the full _generate_action_resolution_structured method runs
        (including _process_structured_damage_effects and the miss-gate),
        and then _resolve_action_mechanically's legacy path also runs.
        """
        enemy = make_enemy(health=30, max_health=30)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        structured_res = make_structured_resolution(target_id="tgt_1234", damage_dealt=10)

        # Mock the LLM call, not the method — so full damage processing runs
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
                'intent': 'Shoot the grunt with my pistol',
                'description': 'Takes aim and fires at the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        assert enemy.health == 20, (
            f"Enemy HP should be 20 (30 - 10), got {enemy.health}. "
            f"Delta={30 - enemy.health}. "
            f"{'DOUBLE DAMAGE BUG: damage applied twice!' if enemy.health == 10 else ''}"
        )

    @pytest.mark.asyncio
    async def test_combat_action_logged_exactly_once(self):
        """
        log_combat_action should fire once per player attack, not twice
        (once from new pipeline, once from legacy path).
        """
        enemy = make_enemy(health=30, max_health=30)
        jsonl_logger = Mock()
        jsonl_logger.log_combat_action = Mock()
        jsonl_logger.log_enemy_defeat = Mock()
        mechanics = make_mechanics(jsonl_logger=jsonl_logger)
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        structured_res = make_structured_resolution(target_id="tgt_1234", damage_dealt=10)

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
                'intent': 'Shoot the grunt',
                'description': 'Fires at the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        assert jsonl_logger.log_combat_action.call_count == 1, (
            f"Expected 1 log_combat_action call, got {jsonl_logger.log_combat_action.call_count}. "
            f"{'DOUBLE LOGGING BUG!' if jsonl_logger.log_combat_action.call_count == 2 else ''}"
        )

    @pytest.mark.asyncio
    async def test_legacy_narration_damage_text_does_not_trigger_second_application(self):
        """
        Specifically tests the mechanism that caused the bug:
        _process_structured_damage_effects appends "takes X damage" to narration,
        then parse_combat_triplet finds it and creates a legacy damage effect.

        With the fix, the legacy damage effect should be suppressed when
        structured output is active.
        """
        enemy = make_enemy(health=30, max_health=30)
        mechanics = make_mechanics(jsonl_logger=Mock())
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        structured_res = make_structured_resolution(target_id="tgt_1234", damage_dealt=12)

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
                'intent': 'Attack the grunt',
                'description': 'Attacks the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        # 30 - 12 = 18 (single application)
        # 30 - 24 = 6  (double application — the bug)
        assert enemy.health == 18, (
            f"Expected HP=18 (30 - 12), got {enemy.health}. "
            f"Damage was applied {(30 - enemy.health) // 12} time(s)."
        )


# ============================================================================
# Test: Damage on Miss (Bug 2)
# ============================================================================

class TestDamageOnMissIntegration:
    """
    Integration test exercising _resolve_action_mechanically to verify
    no damage is applied when the mechanical d20 roll is a miss.
    """

    @pytest.mark.asyncio
    async def test_missed_roll_no_damage_despite_dm_hallucination(self):
        """
        When mechanics says MISS but DM hallucinated damage in effects,
        the damage gate should clear it before application.
        """
        from scripts.aeonisk.multiagent.mechanics import OutcomeTier
        from scripts.aeonisk.multiagent.schemas.action_resolution import (
            ActionResolution, MechanicalEffects
        )
        from scripts.aeonisk.multiagent.schemas.shared_types import (
            DamageEffect, SuccessTier, SoulcreditChange
        )

        enemy = make_enemy(health=30, max_health=30)
        mechanics = make_mechanics(jsonl_logger=Mock())
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        # Override resolve_action to return a MISS
        @dataclass
        class MissResolution:
            intent: str = "Attack the grunt"
            attribute: str = "Agility"
            skill: Optional[str] = "Guns"
            attribute_value: int = 4
            skill_value: int = 3
            roll: int = 1
            total: int = 5
            difficulty: int = 15
            margin: int = -10
            outcome_tier: Any = OutcomeTier.FAILURE
            success: bool = False
            narrative: str = "Your shot goes wide!"
            state_effects: Dict[str, Any] = field(default_factory=dict)
            modifiers_applied: list = field(default_factory=list)
            ability: int = 12
            is_unskilled: bool = False
            roll_formula: Optional[str] = "4×3 + d20(1) = 13 vs DC 15"

        mechanics.resolve_action = Mock(return_value=MissResolution())
        mechanics.format_resolution_for_narration = Mock(
            return_value="🎲 **Agility × Guns** | d20(1) + 12 = 13 vs DC 15 | **FAILURE** (-10)"
        )

        # DM hallucinated damage despite the miss
        hallucinated_res = ActionResolution(
            narration=(
                "Kael's shot goes wide, the round sparking off the ferrocrete wall behind the "
                "grunt. The recoil throws his aim off as adrenaline surges. The grunt flinches "
                "but is unharmed — the round embedded harmlessly in the wall plating three meters "
                "to the left. Kael curses under his breath and adjusts his grip for another attempt."
            ),
            success_tier=SuccessTier.FAILURE,
            margin=-10,
            effects=MechanicalEffects(
                damage=[
                    DamageEffect(target="tgt_1234", base_damage=8, dealt=5, soak=3)
                ],
                soulcredit_changes=[
                    SoulcreditChange(
                        character_name="Enforcer Kael",
                        amount=0,
                        reason="missed combat action"
                    )
                ]
            )
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=hallucinated_res
        ):
            action = {
                'agent_id': 'player_01',
                'character': 'Enforcer Kael',
                'character_name': 'Enforcer Kael',
                'action_type': 'combat',
                'intent': 'Shoot the grunt',
                'description': 'Fires at the grunt',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        assert enemy.health == 30, (
            f"Enemy HP should be unchanged at 30 (roll was a miss), got {enemy.health}. "
            f"Hallucinated damage was not gated!"
        )

    @pytest.mark.asyncio
    async def test_missed_roll_logs_warning_about_hallucinated_damage(self, caplog):
        """
        When the miss-gate fires, a warning should be logged about the
        DM contradicting the mechanical roll.
        """
        from scripts.aeonisk.multiagent.mechanics import OutcomeTier
        from scripts.aeonisk.multiagent.schemas.action_resolution import (
            ActionResolution, MechanicalEffects
        )
        from scripts.aeonisk.multiagent.schemas.shared_types import (
            DamageEffect, SuccessTier, SoulcreditChange
        )

        enemy = make_enemy(health=30)
        mechanics = make_mechanics(jsonl_logger=Mock())
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        @dataclass
        class MissResolution:
            intent: str = "Attack"
            attribute: str = "Agility"
            skill: Optional[str] = "Guns"
            attribute_value: int = 4
            skill_value: int = 3
            roll: int = 2
            total: int = 6
            difficulty: int = 18
            margin: int = -12
            outcome_tier: Any = OutcomeTier.FAILURE
            success: bool = False
            narrative: str = "Miss!"
            state_effects: Dict[str, Any] = field(default_factory=dict)
            modifiers_applied: list = field(default_factory=list)
            ability: int = 12
            is_unskilled: bool = False
            roll_formula: Optional[str] = None

        mechanics.resolve_action = Mock(return_value=MissResolution())
        mechanics.format_resolution_for_narration = Mock(return_value="FAILURE")

        hallucinated_res = ActionResolution(
            narration=(
                "Kael squeezes the trigger but the shot goes impossibly wide, the round "
                "ricocheting off a vent duct overhead and embedding in the ceiling. His hands "
                "tremble from the adrenaline dump. The grunt ducks reflexively but emerges "
                "completely unscathed, already pivoting to return fire from behind the cargo container."
            ),
            success_tier=SuccessTier.FAILURE,
            margin=-12,
            effects=MechanicalEffects(
                damage=[DamageEffect(target="tgt_1234", base_damage=8, dealt=5, soak=3)],
                soulcredit_changes=[SoulcreditChange(character_name="Kael", amount=0, reason="missed combat attempt")]
            )
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=hallucinated_res
        ), caplog.at_level(logging.WARNING, logger='scripts.aeonisk.multiagent.dm'):
            action = {
                'agent_id': 'player_01',
                'character': 'Kael',
                'character_name': 'Kael',
                'action_type': 'combat',
                'intent': 'Attack',
                'description': 'Attack',
                'attribute': 'Agility',
                'skill': 'Guns',
                'attribute_value': 4,
                'skill_value': 3,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        # Check that a warning was logged about hallucinated damage
        miss_warnings = [r for r in caplog.records if 'MISS' in r.message and 'hallucinated' in r.message.lower()]
        assert len(miss_warnings) >= 1, (
            f"Expected warning about hallucinated damage on miss. "
            f"All warnings: {[r.message for r in caplog.records if r.levelno >= logging.WARNING]}"
        )


# ============================================================================
# Test: Non-damage effects still work through legacy path
# ============================================================================

class TestNonDamageEffectsUnaffected:
    """
    Verify that non-damage effects (debuff, status, etc.) still flow
    through the legacy path even when structured output is active.
    """

    @pytest.mark.asyncio
    async def test_debuff_still_applied_via_legacy_path(self):
        """
        When structured output is active but DM narration contains a
        [MECHANICAL_EFFECT] debuff block, it should still be applied.
        Only damage is suppressed from the legacy path.
        """
        from scripts.aeonisk.multiagent.schemas.action_resolution import (
            ActionResolution, MechanicalEffects
        )
        from scripts.aeonisk.multiagent.schemas.shared_types import (
            SuccessTier, SoulcreditChange
        )

        enemy = make_enemy(health=30)
        # Enemy needs add_debuff method
        enemy.add_debuff = Mock()
        mechanics = make_mechanics(jsonl_logger=Mock())
        shared = make_shared_state([enemy], mechanics)
        dm = make_dm(shared)

        # Structured resolution with NO damage but narration has debuff block
        structured_res = ActionResolution(
            narration=(
                "Kael pulls the pin on the flashbang and hurls it in a perfect arc over the "
                "cargo container. The device detonates with a blinding flash and a concussive "
                "thump that rattles the grunt's teeth. Disoriented and stumbling, the grunt "
                "claws at their eyes, their weapon dangling uselessly at their side.\n\n"
                "[MECHANICAL_EFFECT]\n"
                "Type: debuff\n"
                "Target: tgt_1234\n"
                "Effect: -3 to rolls\n"
                "Penalty: -3\n"
                "Duration: 2\n"
                "[/MECHANICAL_EFFECT]"
            ),
            success_tier=SuccessTier.GOOD,
            margin=8,
            effects=MechanicalEffects(
                soulcredit_changes=[
                    SoulcreditChange(character_name="Kael", amount=0, reason="tactical flashbang usage")
                ]
            )
        )

        with patch(
            'scripts.aeonisk.multiagent.structured_output_helpers.generate_dm_resolution_structured',
            new_callable=AsyncMock,
            return_value=structured_res
        ):
            action = {
                'agent_id': 'player_01',
                'character': 'Kael',
                'character_name': 'Kael',
                'action_type': 'combat',
                'intent': 'Throw flashbang at grunt',
                'description': 'Throws flashbang',
                'attribute': 'Agility',
                'skill': 'Throw',
                'attribute_value': 4,
                'skill_value': 2,
                'target': 'tgt_1234',
            }

            await dm._resolve_action_mechanically('player_01', action)

        # Debuff should still be applied via legacy parse_mechanical_effect path
        enemy.add_debuff.assert_called_once()
        # Health should be unchanged (no damage)
        assert enemy.health == 30
