"""
Tests for Spec 12: Display & Observability Improvements

Tests for _display_round_status and enemy/NPC declaration display changes.
All tests capture stdout and verify display output content.

TDD: Write failing tests FIRST, then implement in session.py.
"""

import io
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock, patch
from enum import Enum

import pytest


# ---------------------------------------------------------------------------
# Lightweight mock classes for testing display output
# ---------------------------------------------------------------------------

class MockPosition:
    """Mock position for display testing."""
    def __init__(self, name="Near-PC"):
        self._name = name

    def __str__(self):
        return self._name


class MockWeapon:
    """Mock weapon for enemy display testing."""
    def __init__(self, name="Pulse Rifle", damage_type="wound"):
        self.name = name
        self.damage_type = damage_type


class MockArmor:
    """Mock armor for display testing."""
    def __init__(self, name="Combat Vest", soak_bonus=3):
        self.name = name
        self.soak_bonus = soak_bonus


class MockCharacterState:
    """Mock character state for PC display testing."""
    def __init__(self, name="Vessel Sera Karsel", void_score=3, faction="Sovereign Nexus",
                 soulcredit=5, inventory=None, energy_purse=None):
        self.name = name
        self.void_score = void_score
        self.faction = faction
        self.soulcredit = soulcredit
        self.inventory = inventory or {}
        self.energy_purse = energy_purse


class MockPlayerAgent:
    """Mock player agent for display testing."""
    def __init__(self, name="Vessel Sera Karsel", health=27, max_health=27,
                 position=None, void_score=3, faction="Sovereign Nexus",
                 wounds=0, stuns=0, agent_id="player_01",
                 soulcredit=5):
        self.agent_id = agent_id
        self.health = health
        self.max_health = max_health
        self.position = position or MockPosition("Near-PC")
        self.wounds = wounds
        self.stuns = stuns
        self.character_state = MockCharacterState(
            name=name, void_score=void_score, faction=faction,
            soulcredit=soulcredit
        )
        self.equipped_weapons = {}
        self.weapon_inventory = []


class MockEnemyAgent:
    """Mock enemy agent for display testing."""
    def __init__(self, name="Tempest Enforcer", health=23, max_health=23,
                 position=None, void_score=0, faction="Tempest Coalition",
                 wounds=0, stuns=0, agent_id="enemy_grunt_01",
                 weapons=None, status_effects=None, conditions=None):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = max_health
        self.position = position or MockPosition("Near-Enemy")
        self.void_score = void_score
        self.faction = faction
        self.wounds = wounds
        self.stuns = stuns
        self.weapons = weapons or []
        self.status_effects = status_effects or []
        self.conditions = conditions or []
        self.is_active = True


class MockCondition:
    """Mock condition for display testing."""
    def __init__(self, name="Stunned", penalty=-3, duration=2, affects=None):
        self.name = name
        self.penalty = penalty
        self.duration = duration
        self.affects = affects or []


class MockNPCAgent:
    """Mock NPC agent for display testing."""
    def __init__(self, name="Surrendered Guard", health=15, max_health=23,
                 position=None, disposition="friendly", entity_type="neutral",
                 faction="Tempest", threat_level="non_combatant",
                 is_active=True, agent_id="npc_guard_01",
                 wounds=0, stuns=0, conditions=None, void_score=0):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = max_health
        self.position = position or MockPosition("Near-PC")
        self.disposition = disposition
        self.entity_type = entity_type
        self.faction = faction
        self.threat_level = threat_level
        self.is_active = is_active
        self.can_act = True
        self.wounds = wounds
        self.stuns = stuns
        self.conditions = conditions or []
        self.void_score = void_score


class MockEnvironmentalObjectType(Enum):
    """Mock environmental object type."""
    DOOR = "door"
    TERMINAL = "terminal"
    BARRIER = "barrier"


class MockEnvironmentalObject:
    """Mock environmental object for display testing."""
    def __init__(self, object_type=None, name="Blast Door Alpha",
                 health=30, max_health=30, is_destructible=True,
                 state=None, object_id="env_k3r8", target_id="tgt_k3r8"):
        self.object_type = object_type or MockEnvironmentalObjectType.DOOR
        self.name = name
        self.health = health
        self.max_health = max_health
        self.is_destructible = is_destructible
        self.state = state or {}
        self.object_id = object_id
        self.target_id = target_id

    @property
    def is_destroyed(self):
        if self.health is None:
            return False
        return self.health <= 0


class MockSceneClock:
    """Mock scene clock for display testing."""
    def __init__(self, current=3, maximum=6, filled=False):
        self.current = current
        self.maximum = maximum
        self.filled = filled


class MockTargetIDMapper:
    """Mock target ID mapper for display testing."""
    def __init__(self, enabled=True, mappings=None):
        self.enabled = enabled
        self._mappings = mappings or {}

    def get_all_target_ids(self):
        return list(self._mappings.keys())

    def get_combatant_info(self, target_id):
        return self._mappings.get(target_id)


class MockMechanicsEngine:
    """Mock mechanics engine for display testing."""
    def __init__(self, scene_clocks=None, conditions=None):
        self.scene_clocks = scene_clocks or {}
        self.conditions = conditions or {}

    def get_conditions(self, agent_id):
        return self.conditions.get(agent_id, [])


class MockSharedState:
    """Mock shared state for display testing."""
    def __init__(self, env_objects=None, target_id_mapper=None, npc_agents=None):
        self.current_env_objects = env_objects or []
        self._target_id_mapper = target_id_mapper or MockTargetIDMapper(enabled=False)
        self.npc_agents = npc_agents or []
        self.target_id_mapper = self._target_id_mapper

    def get_target_id_mapper(self):
        return self._target_id_mapper


class MockSession:
    """
    Minimal mock of MultiAgentSession with just _display_round_status.

    We import the actual method to test the real implementation.
    """
    def __init__(self, shared_state=None, mechanics=None):
        self.shared_state = shared_state or MockSharedState()
        self._current_initiative = {}


def _capture_display_output(session, initiative_order, mechanics, player_agents):
    """Capture stdout from _display_round_status."""
    f = io.StringIO()
    with redirect_stdout(f):
        session._display_round_status(initiative_order, mechanics, player_agents)
    return f.getvalue()


def _build_session_with_method(shared_state=None, mechanics=None):
    """
    Build a mock session that uses the real _display_round_status method.

    This imports the real method from session.py and binds it to our mock.
    """
    from scripts.aeonisk.multiagent.session import SelfPlayingSession
    mock_session = MockSession(shared_state=shared_state, mechanics=mechanics)
    # Bind the real method to our mock object
    import types
    mock_session._display_round_status = types.MethodType(
        SelfPlayingSession._display_round_status, mock_session
    )
    return mock_session


# ===========================================================================
# TEST 1: NPC Initiative Shows Actual Number (not [--])
# ===========================================================================

class TestNPCInitiativeDisplay:
    """NPC initiative should show actual value, not hardcoded [--]."""

    def test_npc_initiative_shows_number(self):
        """NPC initiative shows actual value, not [--]."""
        npc = MockNPCAgent(name="Surrendered Guard")
        initiative_order = [(23, 'npc', npc)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "[23]" in output
        assert "[--]" not in output

    def test_npc_initiative_shows_single_digit(self):
        """Single-digit NPC initiative is right-aligned in 2 chars."""
        npc = MockNPCAgent(name="Civilian")
        initiative_order = [(5, 'npc', npc)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "[ 5]" in output
        assert "[--]" not in output


# ===========================================================================
# TEST 2: Enemy Detail Display (Weapons, Void, Faction, Wounds/Stuns)
# ===========================================================================

class TestEnemyDetailDisplay:
    """Enemy display should show detailed info like PCs."""

    def test_enemy_shows_faction(self):
        """Enemy display includes faction when known."""
        enemy = MockEnemyAgent(faction="Tempest Coalition")
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Tempest Coalition" in output

    def test_enemy_shows_weapons(self):
        """Enemy display includes weapon names and damage types."""
        enemy = MockEnemyAgent(weapons=[
            MockWeapon("Assault Rifle", "wound"),
            MockWeapon("Shock Baton", "stun"),
        ])
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Assault Rifle" in output
        assert "WOUND" in output
        assert "Shock Baton" in output
        assert "STUN" in output

    def test_enemy_shows_void_score_when_nonzero(self):
        """Enemy display includes void score when non-zero."""
        enemy = MockEnemyAgent(void_score=5)
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Void 5/10" in output

    def test_enemy_hides_void_score_when_zero(self):
        """Enemy display does not show void score when zero."""
        enemy = MockEnemyAgent(void_score=0)
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Void 0/10" not in output

    def test_enemy_shows_wounds_stuns(self):
        """Enemy display includes wound and stun counts."""
        enemy = MockEnemyAgent(wounds=2, stuns=1)
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "2w" in output
        assert "1s" in output

    def test_enemy_hides_wounds_stuns_when_zero(self):
        """Enemy display does not show wounds/stuns when both are zero."""
        enemy = MockEnemyAgent(wounds=0, stuns=0)
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        # Should not contain wound/stun indicators
        assert "0w" not in output
        assert "0s" not in output

    def test_enemy_shows_status_effects(self):
        """Enemy display includes active status effects."""
        enemy = MockEnemyAgent(status_effects=["stunned", "suppressed"])
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "stunned" in output
        assert "suppressed" in output

    def test_enemy_shows_conditions(self):
        """Enemy display includes condition objects with penalties."""
        enemy = MockEnemyAgent(conditions=[
            MockCondition("Prone", penalty=-2, duration=1),
        ])
        initiative_order = [(18, 'enemy', enemy)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Prone" in output
        assert "-2" in output


# ===========================================================================
# TEST 3: PC Conditions Display
# ===========================================================================

class TestPCConditionsDisplay:
    """PC display should show active conditions from mechanics engine."""

    def test_pc_shows_conditions(self):
        """PC display includes active conditions with penalties."""
        from scripts.aeonisk.multiagent.mechanics import Condition
        player = MockPlayerAgent(agent_id="player_01")
        conditions = {
            "player_01": [
                Condition(name="Stunned", type="stun", penalty=-3,
                         description="Dazed from impact", duration=2)
            ]
        }
        mechanics = MockMechanicsEngine(conditions=conditions)
        initiative_order = [(14, 'player', player)]

        session = _build_session_with_method(mechanics=mechanics)
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "Stunned" in output
        assert "-3" in output

    def test_pc_hides_conditions_when_none(self):
        """PC display does not show conditions line when agent has none."""
        player = MockPlayerAgent(agent_id="player_01")
        mechanics = MockMechanicsEngine(conditions={})
        initiative_order = [(14, 'player', player)]

        session = _build_session_with_method(mechanics=mechanics)
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "Conditions:" not in output

    def test_pc_shows_wounds(self):
        """PC display includes wound count when non-zero."""
        player = MockPlayerAgent(wounds=2)
        mechanics = MockMechanicsEngine()
        initiative_order = [(14, 'player', player)]

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "2 wound" in output

    def test_pc_shows_stuns(self):
        """PC display includes stun count when non-zero."""
        player = MockPlayerAgent(stuns=3)
        mechanics = MockMechanicsEngine()
        initiative_order = [(14, 'player', player)]

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "3 stun" in output

    def test_pc_hides_wounds_stuns_when_zero(self):
        """PC display does not show wounds/stuns when zero."""
        player = MockPlayerAgent(wounds=0, stuns=0)
        mechanics = MockMechanicsEngine()
        initiative_order = [(14, 'player', player)]

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "wound" not in output.lower()
        assert "stun" not in output.lower()


# ===========================================================================
# TEST 4: NPC Wounds/Stuns Display
# ===========================================================================

class TestNPCWoundsStuns:
    """NPC display should show wounds and stuns."""

    def test_npc_shows_wounds_stuns(self):
        """NPC display includes wound and stun counts when non-zero."""
        npc = MockNPCAgent(wounds=1, stuns=2)
        initiative_order = [(20, 'npc', npc)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "1w" in output
        assert "2s" in output

    def test_npc_hides_wounds_stuns_when_zero(self):
        """NPC display does not show wounds/stuns when both are zero."""
        npc = MockNPCAgent(wounds=0, stuns=0)
        initiative_order = [(20, 'npc', npc)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "0w" not in output
        assert "0s" not in output


# ===========================================================================
# TEST 5: NPC Conditions Display
# ===========================================================================

class TestNPCConditionsDisplay:
    """NPC display should show active conditions."""

    def test_npc_shows_conditions(self):
        """NPC display includes condition objects with penalties."""
        npc = MockNPCAgent(conditions=[
            MockCondition("Prone", penalty=-2, duration=1),
        ])
        initiative_order = [(20, 'npc', npc)]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Prone" in output
        assert "-2" in output


# ===========================================================================
# TEST 6: Environmental Objects Section
# ===========================================================================

class TestEnvironmentalObjectsDisplay:
    """Environmental objects section in round status."""

    def test_env_objects_section_displayed(self):
        """Environmental objects section appears when objects exist."""
        env_obj = MockEnvironmentalObject(
            object_type=MockEnvironmentalObjectType.DOOR,
            name="Blast Door Alpha",
            health=30,
            max_health=30,
            target_id="tgt_k3r8"
        )
        shared_state = MockSharedState(env_objects=[env_obj])
        initiative_order = []
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Environmental Objects:" in output
        assert "Blast Door Alpha" in output
        assert "DOOR" in output

    def test_env_objects_section_hidden_when_empty(self):
        """Environmental objects section does not appear when no objects."""
        shared_state = MockSharedState(env_objects=[])
        initiative_order = []
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Environmental Objects:" not in output

    def test_env_objects_show_health(self):
        """Environmental objects show HP when destructible."""
        env_obj = MockEnvironmentalObject(
            name="Barricade",
            health=35,
            max_health=50,
            object_type=MockEnvironmentalObjectType.BARRIER
        )
        shared_state = MockSharedState(env_objects=[env_obj])
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "35/50 HP" in output

    def test_env_objects_show_destroyed_status(self):
        """Environmental objects show [DESTROYED] when health <= 0."""
        env_obj = MockEnvironmentalObject(
            name="Wrecked Door",
            health=0,
            max_health=30,
        )
        shared_state = MockSharedState(env_objects=[env_obj])
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "DESTROYED" in output

    def test_env_objects_show_state_flags(self):
        """Environmental objects show state flags like 'locked'."""
        env_obj = MockEnvironmentalObject(
            name="Blast Door",
            state={"locked": True, "reinforced": True},
        )
        shared_state = MockSharedState(env_objects=[env_obj])
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "locked" in output
        assert "reinforced" in output


# ===========================================================================
# TEST 7: Target ID Mapping Table
# ===========================================================================

class TestTargetIDTable:
    """Target ID reference table for free targeting mode."""

    def test_target_id_table_displayed(self):
        """Target ID reference table appears when free targeting is active."""
        mapper = MockTargetIDMapper(enabled=True, mappings={
            "tgt_3f8a": {"name": "Vessel Sera Karsel", "type": "player"},
            "tgt_7k2m": {"name": "Tempest Enforcer", "type": "enemy"},
        })
        shared_state = MockSharedState(target_id_mapper=mapper)
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "Target ID Reference:" in output
        assert "tgt_3f8a" in output
        assert "Vessel Sera Karsel" in output
        assert "PC" in output
        assert "tgt_7k2m" in output
        assert "Tempest Enforcer" in output
        assert "ENEMY" in output

    def test_target_id_table_hidden_when_disabled(self):
        """Target ID table does not appear when free targeting is disabled."""
        mapper = MockTargetIDMapper(enabled=False)
        shared_state = MockSharedState(target_id_mapper=mapper)
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "Target ID Reference:" not in output

    def test_target_id_table_shows_npc_type(self):
        """Target ID table shows NPC type tag."""
        mapper = MockTargetIDMapper(enabled=True, mappings={
            "tgt_9p1q": {"name": "Surrendered Guard", "type": "npc"},
        })
        shared_state = MockSharedState(target_id_mapper=mapper)
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "NPC" in output
        assert "Surrendered Guard" in output

    def test_target_id_table_shows_env_object_type(self):
        """Target ID table shows OBJECT type tag for env objects."""
        mapper = MockTargetIDMapper(enabled=True, mappings={
            "tgt_k3r8": {"name": "Blast Door Alpha", "type": "env_object"},
        })
        shared_state = MockSharedState(target_id_mapper=mapper)
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method(shared_state=shared_state)
        output = _capture_display_output(session, [], mechanics, [])

        assert "OBJECT" in output
        assert "Blast Door Alpha" in output


# ===========================================================================
# TEST 8: Clock Progress Bars
# ===========================================================================

class TestClockProgressBars:
    """Scene clocks should show visual progress bars."""

    def test_clock_shows_progress_bar(self):
        """Scene clocks display with visual progress bar."""
        mechanics = MockMechanicsEngine(scene_clocks={
            "Ambush Chaos": MockSceneClock(current=4, maximum=8),
        })
        initiative_order = []

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [])

        assert "Scene Clocks:" in output
        # Should have filled and empty blocks
        assert "4/8" in output
        # Progress bar should contain fill characters
        # Exact format: [████░░░░] 4/8
        assert "\u2588" in output or "#" in output  # filled block chars

    def test_clock_full_shows_filled_bar(self):
        """Filled clock shows fully filled progress bar."""
        mechanics = MockMechanicsEngine(scene_clocks={
            "Civilian Exposure": MockSceneClock(current=4, maximum=4, filled=True),
        })

        session = _build_session_with_method()
        output = _capture_display_output(session, [], mechanics, [])

        assert "4/4" in output
        assert "[FILLED]" in output

    def test_clock_empty_shows_empty_bar(self):
        """Empty clock shows unfilled progress bar."""
        mechanics = MockMechanicsEngine(scene_clocks={
            "Alarm Response": MockSceneClock(current=0, maximum=6),
        })

        session = _build_session_with_method()
        output = _capture_display_output(session, [], mechanics, [])

        assert "0/6" in output


# ===========================================================================
# TEST 9: Enemy Declaration - Full Reasoning & Shared Intel
# ===========================================================================

class TestEnemyDeclarationDisplay:
    """Enemy declarations should show full reasoning and shared intel in stdout."""

    def test_enemy_declaration_shows_reasoning(self):
        """Enemy declaration stdout includes full reasoning text."""
        # We test the print statements in the declaration phase.
        # The declaration print code in session.py after the one-liner.
        # Since the declaration code is in an async method, we test the
        # display helper we add.
        from scripts.aeonisk.multiagent.session import _format_enemy_declaration_details
        output = _format_enemy_declaration_details(
            reasoning="Target is wounded and exposed at Near-PC",
            shared_intel=None
        )
        assert "Reasoning:" in output
        assert "Target is wounded and exposed at Near-PC" in output

    def test_enemy_declaration_shows_shared_intel(self):
        """Enemy declaration stdout includes shared intel broadcast."""
        from scripts.aeonisk.multiagent.session import _format_enemy_declaration_details
        output = _format_enemy_declaration_details(
            reasoning="Pressing the attack",
            shared_intel="Focus fire on wounded target"
        )
        assert "Shared Intel:" in output
        assert "Focus fire on wounded target" in output

    def test_enemy_declaration_hides_empty_intel(self):
        """Shared intel line not shown when shared_intel is None."""
        from scripts.aeonisk.multiagent.session import _format_enemy_declaration_details
        output = _format_enemy_declaration_details(
            reasoning="Taking cover",
            shared_intel=None
        )
        assert "Shared Intel:" not in output

    def test_enemy_reasoning_not_truncated(self):
        """Reasoning in stdout should show full text, not truncated to 100 chars."""
        from scripts.aeonisk.multiagent.session import _format_enemy_declaration_details
        long_reasoning = "A" * 150
        output = _format_enemy_declaration_details(
            reasoning=long_reasoning,
            shared_intel=None
        )
        assert long_reasoning in output  # Full text, not truncated


# ===========================================================================
# TEST 10: NPC Declaration - Full Reason Not Truncated
# ===========================================================================

class TestNPCDeclarationDisplay:
    """NPC declarations should show full reason, not truncated."""

    def test_npc_reason_format_helper(self):
        """NPC declaration reason uses format helper for full display."""
        from scripts.aeonisk.multiagent.session import _format_npc_declaration_reason
        long_reason = "B" * 150
        output = _format_npc_declaration_reason(long_reason)
        assert long_reason in output  # Full text, not truncated to 60 chars


# ===========================================================================
# TEST 11: Disposition Emoji Deduplication
# ===========================================================================

class TestDispositionEmojiDedup:
    """Disposition emoji mapping should use module-level constant."""

    def test_disposition_emoji_constant_exists(self):
        """NPC_DISPOSITION_EMOJI module-level constant exists."""
        from scripts.aeonisk.multiagent.session import NPC_DISPOSITION_EMOJI
        assert isinstance(NPC_DISPOSITION_EMOJI, dict)
        assert "friendly" in NPC_DISPOSITION_EMOJI
        assert "neutral" in NPC_DISPOSITION_EMOJI
        assert "wary" in NPC_DISPOSITION_EMOJI
        assert "prisoner" in NPC_DISPOSITION_EMOJI


# ===========================================================================
# TEST 12: Range-Band Map Display
# ===========================================================================

class TestRangeBandMapDisplay:
    """Range-band map should show agent positions."""

    def test_range_band_map_displayed(self):
        """Range-band map appears when combatants have positions."""
        player = MockPlayerAgent(position=MockPosition("Near-PC"))
        enemy = MockEnemyAgent(position=MockPosition("Far-Enemy"))
        initiative_order = [
            (14, 'player', player),
            (18, 'enemy', enemy),
        ]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        assert "Range-Band Map:" in output
        assert "Near-PC" in output
        assert "Far-Enemy" in output

    def test_range_band_map_groups_by_position(self):
        """Range-band map groups agents at the same position."""
        player1 = MockPlayerAgent(name="Agent Alpha", position=MockPosition("Near-PC"),
                                  agent_id="player_01")
        player2 = MockPlayerAgent(name="Agent Beta", position=MockPosition("Near-PC"),
                                  agent_id="player_02")
        initiative_order = [
            (14, 'player', player1),
            (12, 'player', player2),
        ]
        mechanics = MockMechanicsEngine()

        session = _build_session_with_method()
        output = _capture_display_output(session, initiative_order, mechanics, [player1, player2])

        # Both should appear under Near-PC
        assert "Near-PC" in output
        assert "Agent Alpha" in output or "Alpha" in output
        assert "Agent Beta" in output or "Beta" in output


# ===========================================================================
# TEST: Combined Scenario (integration-style)
# ===========================================================================

class TestCombinedDisplay:
    """Integration-style test with all combatant types and features."""

    def test_full_display_with_all_types(self):
        """Full round status with PCs, enemies, NPCs, clocks, env objects, and target IDs."""
        player = MockPlayerAgent(
            name="Vessel Sera Karsel",
            health=20, max_health=27,
            wounds=1, stuns=0,
            agent_id="player_01"
        )
        enemy = MockEnemyAgent(
            name="Tempest Enforcer",
            health=15, max_health=23,
            wounds=2, stuns=1,
            faction="Tempest Coalition",
            weapons=[MockWeapon("Pulse Rifle", "wound")],
            status_effects=["suppressed"],
        )
        npc = MockNPCAgent(
            name="Surrendered Guard",
            health=15, max_health=23,
            wounds=0, stuns=1,
            disposition="friendly",
        )
        env_obj = MockEnvironmentalObject(
            name="Blast Door",
            health=25, max_health=30,
            object_type=MockEnvironmentalObjectType.DOOR,
            state={"locked": True},
        )
        mapper = MockTargetIDMapper(enabled=True, mappings={
            "tgt_3f8a": {"name": "Vessel Sera Karsel", "type": "player"},
            "tgt_7k2m": {"name": "Tempest Enforcer", "type": "enemy"},
            "tgt_9p1q": {"name": "Surrendered Guard", "type": "npc"},
        })
        shared_state = MockSharedState(
            env_objects=[env_obj],
            target_id_mapper=mapper,
        )
        mechanics = MockMechanicsEngine(
            scene_clocks={
                "Ambush Chaos": MockSceneClock(current=3, maximum=6),
            },
            conditions={
                "player_01": [
                    MockCondition("Inspired", penalty=2, duration=3),
                ],
            }
        )
        initiative_order = [
            (18, 'enemy', enemy),
            (14, 'player', player),
            (23, 'npc', npc),
        ]

        session = _build_session_with_method(shared_state=shared_state, mechanics=mechanics)
        output = _capture_display_output(session, initiative_order, mechanics, [player])

        # Verify all sections present
        assert "Player Characters:" in output
        assert "Enemies:" in output
        assert "NPCs (Non-Combatants):" in output
        assert "Scene Clocks:" in output
        assert "Environmental Objects:" in output
        assert "Target ID Reference:" in output

        # Verify key details
        assert "1 wound" in output  # PC wound
        assert "2w" in output  # Enemy wounds
        assert "1s" in output  # Enemy stuns (or NPC stun)
        assert "Tempest Coalition" in output  # Enemy faction
        assert "Pulse Rifle" in output  # Enemy weapon
        assert "suppressed" in output  # Enemy status effect
        assert "Blast Door" in output  # Env object
        assert "[23]" in output  # NPC real initiative
        assert "tgt_3f8a" in output  # Target ID mapping
