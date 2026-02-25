"""
Unit tests for enemy lifecycle improvements (Spec 02):
1. Suppression logging format matches attack format (consistent field names)
2. Deprecated log_enemy_action() emits DeprecationWarning
3. Defeated enemies pruned after grace period
4. Active enemies never pruned
5. Pruning cleans up target ID mapper
6. Mixed active/inactive pruning
7. Skipped player actions don't use deprecated log_enemy_action()

TDD: These tests are written FIRST before implementation.
"""

import warnings
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


# ============================================================================
# Test Helpers
# ============================================================================

def create_test_enemy(
    agent_id: str = "enemy_grunt_1",
    name: str = "Guard",
    skills: Optional[Dict[str, int]] = None,
    weapons: Optional[list] = None,
    is_active: bool = True,
    despawned_round: Optional[int] = None,
    faction: str = "Hostile",
    health: int = 20,
    max_health: int = 20,
) -> Any:
    """Create a real EnemyAgent for testing."""
    from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position
    from scripts.aeonisk.multiagent.weapons import Weapon

    default_weapon = Weapon(
        name="Pistol",
        skill="Guns",
        damage=5,
        damage_type="wound",
        attack=2,
        defence=0,
        is_ranged=True,
        rof=1,
    )

    default_skills = skills or {"Guns": 3, "Awareness": 2}
    weapon_list = weapons or [default_weapon]

    enemy = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template="grunt",
        attributes={"Perception": 3, "Dexterity": 3, "Agility": 3, "Strength": 3},
        skills=default_skills,
        health=health,
        max_health=max_health,
        soak=10,
        wounds=0,
        position=Position.from_string("Near-Left"),
        initiative=10,
        weapons=weapon_list,
        faction=faction,
        is_active=is_active,
        despawned_round=despawned_round,
    )
    return enemy


def create_suppress_weapon():
    """Create a weapon with sufficient RoF for suppression (RoF >= 3)."""
    from scripts.aeonisk.multiagent.weapons import Weapon

    return Weapon(
        name="LMG",
        skill="Guns",
        damage=7,
        damage_type="wound",
        attack=3,
        defence=0,
        is_ranged=True,
        rof=5,
    )


def create_test_player(agent_id: str = "player_01", name: str = "Sera"):
    """Create a mock player agent for testing."""
    player = MagicMock()
    player.agent_id = agent_id
    player.name = name
    player.health = 25
    player.max_health = 25
    player.soak = 12
    player.wounds = 0
    player.stuns = 0
    player.position = MagicMock()
    player.position.__str__ = lambda self: "Near-Right"
    player.defence_token = None
    player.is_active = True
    return player


def create_enemy_combat_manager(shared_state=None):
    """Create an EnemyCombatManager for testing."""
    from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager

    ecm = EnemyCombatManager(shared_state=shared_state)
    ecm.enabled = True
    ecm.current_round = 1
    return ecm


class MockJSONLLogger:
    """Mock JSONL logger that captures logged events."""

    def __init__(self):
        self.events = []
        self.current_round = 0

    def log_combat_action(self, **kwargs):
        event = {"event_type": "combat_action"}
        event.update(kwargs)
        self.events.append(event)

    def log_enemy_action(self, **kwargs):
        event = {"event_type": "action_resolution"}
        event.update(kwargs)
        self.events.append(event)

    def log_action_resolution(self, **kwargs):
        event = {"event_type": "action_resolution"}
        event.update(kwargs)
        self.events.append(event)


# ============================================================================
# Test 1: Suppression logging format matches attack format
# ============================================================================

class TestSuppressionLogging:
    """After fixing suppress logging, combat_action events should have
    consistent field names matching the attack logging format."""

    def test_suppression_logged_as_combat_action(self):
        """Suppression actions must produce a combat_action event with
        full roll data and weapon marked as '(suppress)'."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager, EnemyDeclaration
        from scripts.aeonisk.multiagent.tactical_resolution import ResolutionState

        mock_logger = MockJSONLLogger()
        mock_mechanics = MagicMock()
        mock_mechanics.jsonl_logger = mock_logger
        mock_mechanics.current_round = 1

        suppress_weapon = create_suppress_weapon()
        enemy = create_test_enemy(
            agent_id="enemy_heavy_1",
            name="Heavy Gunner",
            skills={"Guns": 4, "Awareness": 2},
            weapons=[suppress_weapon],
        )

        target = create_test_player(agent_id="player_02", name="Vex")

        ecm = create_enemy_combat_manager()
        ecm.enemy_agents.append(enemy)

        declaration = EnemyDeclaration(
            agent_id=enemy.agent_id,
            character_name=enemy.name,
            initiative=10,
            defence_token=None,
            major_action="Suppress",
            target="player_02",
            weapon="LMG",
            minor_action=None,
            token_target=None,
            reasoning="Suppressing target",
            shared_intel=None,
        )

        resolution_state = ResolutionState()

        result = ecm._execute_suppress(
            enemy, declaration, [target], mock_mechanics, resolution_state
        )

        # Should produce a combat_action event
        combat_events = [e for e in mock_logger.events if e["event_type"] == "combat_action"]
        assert len(combat_events) == 1, f"Expected 1 combat_action, got {len(combat_events)}"

        event = combat_events[0]
        assert "suppress" in event["weapon"].lower()

        # Check attack_roll has consistent field names matching attack format
        attack_data = event["attack_roll"]
        assert attack_data is not None
        # These field names should match the _execute_attack format:
        assert "attr" in attack_data, "Missing 'attr' field (should be attribute name like 'Perception')"
        assert "attr_val" in attack_data, "Missing 'attr_val' field"
        assert "skill" in attack_data, "Missing 'skill' field (should be skill name like 'Guns')"
        assert "skill_val" in attack_data, "Missing 'skill_val' field"
        assert "d20" in attack_data, "Missing 'd20' field"
        assert "total" in attack_data, "Missing 'total' field"
        assert "dc" in attack_data, "Missing 'dc' field (should be target defence)"
        assert "hit" in attack_data, "Missing 'hit' field"
        assert "margin" in attack_data, "Missing 'margin' field"

        # Verify actual values
        assert attack_data["skill"] == "Guns", f"Expected skill='Guns', got '{attack_data['skill']}'"
        assert attack_data["skill_val"] == 4, f"Expected skill_val=4, got {attack_data['skill_val']}"
        assert attack_data["attr"] == "Perception", f"Expected attr='Perception' for Guns skill"
        assert isinstance(attack_data["d20"], int)
        assert 1 <= attack_data["d20"] <= 20

        # Suppression: no damage
        assert event["damage_roll"] is None
        assert event["wounds_dealt"] == 0


# ============================================================================
# Test 2: Deprecated log_enemy_action warning
# ============================================================================

class TestLogEnemyActionDeprecation:
    """log_enemy_action() should emit a DeprecationWarning when called."""

    def test_log_enemy_action_deprecation_warning(self):
        """Calling log_enemy_action() directly emits a DeprecationWarning."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        logger = JSONLLogger(session_id="test", output_dir="/tmp")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            logger.log_enemy_action(
                round_num=1,
                enemy_id="enemy_1",
                enemy_name="Guard",
                action_type="attack",
                result="hit",
                narration="Guard attacks",
            )
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1, f"Expected DeprecationWarning, got {[x.category for x in w]}"
            assert "log_combat_action" in str(deprecation_warnings[0].message)


# ============================================================================
# Test 3: Defeated enemy pruned after grace period
# ============================================================================

class TestEnemyPruning:
    """Tests for prune_inactive_enemies() method."""

    def test_defeated_enemy_pruned_after_grace_period(self):
        """Enemies defeated more than min_rounds_inactive ago should be
        pruned from enemy_agents list."""
        ecm = create_enemy_combat_manager()

        # Create and defeat an enemy at round 2
        enemy = create_test_enemy(agent_id="enemy_grunt_1", name="Guard")
        enemy.is_active = False
        enemy.despawned_round = 2
        ecm.enemy_agents.append(enemy)

        # Round 3: grace period (1 round since despawn)
        ecm.current_round = 3
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 0
        assert len(ecm.enemy_agents) == 1

        # Round 4: still within grace period (2 rounds since despawn)
        ecm.current_round = 4
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 0
        assert len(ecm.enemy_agents) == 1

        # Round 5: grace period expired (3 rounds since despawn > 2)
        ecm.current_round = 5
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 1
        assert len(ecm.enemy_agents) == 0

    def test_active_enemy_never_pruned(self):
        """Active enemies must never be removed by pruning, even after
        many rounds."""
        ecm = create_enemy_combat_manager()

        enemy = create_test_enemy(agent_id="enemy_boss_1", name="Boss")
        enemy.is_active = True
        ecm.enemy_agents.append(enemy)

        # Run pruning at high round numbers
        for round_num in range(1, 20):
            ecm.current_round = round_num
            pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
            assert pruned == 0
            assert len(ecm.enemy_agents) == 1
            assert ecm.enemy_agents[0].agent_id == "enemy_boss_1"

    def test_prune_removes_from_target_mapper(self):
        """When an enemy is pruned, its target ID mapping must also be
        removed to prevent stale ID references."""
        from scripts.aeonisk.multiagent.target_ids import TargetIDMapper

        # Create shared_state mock with target mapper
        shared_state = MagicMock()
        mapper = TargetIDMapper()
        mapper.enable()
        shared_state.get_target_id_mapper.return_value = mapper

        ecm = create_enemy_combat_manager(shared_state=shared_state)

        enemy = create_test_enemy(agent_id="enemy_grunt_1", name="Guard")
        ecm.enemy_agents.append(enemy)

        # Register enemy in mapper
        tid = mapper.register_enemy(enemy)
        assert tid is not None
        assert mapper.resolve_target(tid) is not None

        # Defeat and wait for grace period
        enemy.is_active = False
        enemy.despawned_round = 1
        ecm.current_round = 5

        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 1

        # Verify target mapper is cleaned
        assert mapper.resolve_target(tid) is None
        assert mapper.get_target_id("enemy_grunt_1") is None

    def test_mixed_active_inactive_pruning(self):
        """Pruning should only remove stale enemies, keeping active and
        recently defeated ones."""
        ecm = create_enemy_combat_manager()

        # Active enemy
        active = create_test_enemy(agent_id="enemy_1", name="Active Guard")
        active.is_active = True
        ecm.enemy_agents.append(active)

        # Recently defeated (round 8, current is 9 -- within grace)
        recent = create_test_enemy(agent_id="enemy_2", name="Recent Kill")
        recent.is_active = False
        recent.despawned_round = 8
        ecm.enemy_agents.append(recent)

        # Stale defeated (round 3, current is 9 -- well past grace)
        stale = create_test_enemy(agent_id="enemy_3", name="Old Kill")
        stale.is_active = False
        stale.despawned_round = 3
        ecm.enemy_agents.append(stale)

        ecm.current_round = 9
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)

        assert pruned == 1
        assert len(ecm.enemy_agents) == 2
        remaining_ids = {e.agent_id for e in ecm.enemy_agents}
        assert "enemy_1" in remaining_ids  # active
        assert "enemy_2" in remaining_ids  # recently defeated
        assert "enemy_3" not in remaining_ids  # pruned

    def test_prune_empty_list(self):
        """Pruning an empty enemy list should return 0."""
        ecm = create_enemy_combat_manager()
        ecm.current_round = 10
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 0
        assert len(ecm.enemy_agents) == 0

    def test_inactive_without_despawned_round_kept(self):
        """Inactive enemies without despawned_round should be kept (defensive)."""
        ecm = create_enemy_combat_manager()

        enemy = create_test_enemy(agent_id="enemy_glitched", name="Glitched")
        enemy.is_active = False
        enemy.despawned_round = None  # No despawned_round set
        ecm.enemy_agents.append(enemy)

        ecm.current_round = 100
        pruned = ecm.prune_inactive_enemies(min_rounds_inactive=2)
        assert pruned == 0
        assert len(ecm.enemy_agents) == 1


# ============================================================================
# Test 4: Session.py skipped player actions don't use deprecated method
# ============================================================================

class TestSessionSkippedPlayerLogging:
    """Skipped player actions in session.py should not use the deprecated
    log_enemy_action() method."""

    def test_session_has_no_log_enemy_action_for_enemy_combat(self):
        """The enemy combat execution block in session.py should not call
        log_enemy_action() -- it should rely on enemy_combat.py's own
        log_combat_action() calls."""
        import inspect
        from scripts.aeonisk.multiagent.session import SelfPlayingSession

        # Get the source of _run_initiative_round
        source = inspect.getsource(SelfPlayingSession._run_initiative_round)

        # The enemy execution block (after 'elif agent_type == "enemy"')
        # should NOT contain log_enemy_action calls
        # Find the enemy execution section -- look for second occurrence
        # (first is in declaration phase, second is in resolution phase)
        first_enemy = source.find("elif agent_type == 'enemy':")
        assert first_enemy > 0, "Could not find first enemy block"
        second_enemy = source.find("elif agent_type == 'enemy':", first_enemy + 1)
        assert second_enemy > 0, "Could not find enemy execution block in resolution phase"

        # Find the next agent type section (npc) after the resolution-phase enemy block
        npc_section_start = source.find("elif agent_type == 'npc':", second_enemy)
        assert npc_section_start > 0, "Could not find NPC section after enemy"

        enemy_section = source[second_enemy:npc_section_start]
        assert "log_enemy_action" not in enemy_section, \
            "Enemy execution block should not call log_enemy_action() -- " \
            "enemy_combat.py handles logging via log_combat_action()"
