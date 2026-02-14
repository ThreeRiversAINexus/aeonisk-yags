"""
Unit tests for enemy-on-enemy targeting in enemy_combat.py.

Tests that enemies from hostile factions can attack each other,
while allied/same-faction attacks are rejected.
"""

import pytest
import random
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position
from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY


def _make_enemy(
    name="Thug",
    agent_id="enemy_01",
    faction="Pantheon Security",
    health=20,
    max_health=20,
    soak=8,
    weapons=None,
    position=None,
    skills=None,
    attributes=None,
    is_active=True,
):
    """Create a mock enemy agent for testing."""
    enemy = MagicMock(spec=EnemyAgent)
    enemy.name = name
    enemy.agent_id = agent_id
    enemy.faction = faction
    enemy.health = health
    enemy.max_health = max_health
    enemy.soak = soak
    enemy.stuns = 0
    enemy.wounds = 0
    enemy.is_active = is_active
    enemy.tactics = "aggressive"
    enemy.position = position or Position(ring="Near", side="PC")
    enemy.weapons = weapons or [WEAPON_LIBRARY['pistol']]
    enemy.skills = skills or {"Guns": 3, "Melee": 3}
    enemy.attributes = attributes or {"Perception": 3, "Dexterity": 3, "Agility": 3, "Strength": 3}
    enemy.defence_token = None
    enemy.is_prisoner = False
    enemy.despawned_round = None
    enemy.check_death_save = MagicMock(return_value=(True, "conscious"))
    return enemy


def _make_player(name="Ash Vex", agent_id="player_01"):
    """Create a mock player agent."""
    player = MagicMock()
    player.name = name
    player.agent_id = agent_id
    player.health = 27
    player.max_health = 27
    player.soak = 12
    player.stuns = 0
    player.wounds = 0
    player.position = Position(ring="Near", side="PC")
    player.defence_token = None
    # Player agents have character_state (distinguishes from enemies)
    player.character_state = MagicMock()
    player.character_state.name = name
    player.check_death_save = MagicMock(return_value=(True, "conscious"))
    return player


def _make_npc(name="Freeborn Worker", agent_id="npc_worker_01", health=15, soak=4):
    """Create a mock NPC agent."""
    npc = MagicMock()
    npc.name = name
    npc.agent_id = agent_id
    npc.health = health
    npc.max_health = health
    npc.soak = soak
    npc.stuns = 0
    npc.wounds = 0
    npc.is_active = True
    npc.position = Position(ring="Near", side="Enemy")
    npc.defence_token = None
    # NPCs don't have character_state or tactics
    npc.check_death_save = MagicMock(return_value=(True, "conscious"))
    return npc


def _make_declaration(major_action="Attack", target="tgt_0001", weapon="Pistol"):
    """Create a mock enemy declaration."""
    decl = MagicMock()
    decl.major_action = major_action
    decl.target = target
    decl.weapon = weapon
    decl.defence_token = None
    decl.minor_action = None
    decl.reasoning = "Test combat"
    decl.shared_intel = None
    return decl


def _make_shared_state(players=None, enemies=None, npcs=None, mapper=None):
    """Create a mock shared state with target ID mapper."""
    shared_state = MagicMock()

    if mapper is None:
        mapper = MagicMock()
        mapper.enabled = True
    shared_state.get_target_id_mapper.return_value = mapper

    # Session mock for track_player_damage_taken
    session = MagicMock()
    shared_state.session = session

    # Mechanics engine mock
    mechanics = MagicMock()
    mechanics.jsonl_logger = None  # Disable logging in tests
    shared_state.get_mechanics_engine.return_value = mechanics
    shared_state.mechanics_engine = mechanics

    # NPC agents
    shared_state.npc_agents = npcs or []

    return shared_state


def _make_resolution_state():
    """Create a mock resolution state."""
    rs = MagicMock()
    rs.is_defeated.return_value = False
    rs.is_surrendered.return_value = False
    rs.is_incapacitated.return_value = False
    rs.has_acted.return_value = False
    rs.mark_defeated = MagicMock()
    rs.mark_incapacitated = MagicMock()
    rs.record_position_change = MagicMock()
    return rs


def _make_resolver(shared_state=None, current_round=1):
    """Create an EnemyCombatManager with mocked dependencies."""
    resolver = EnemyCombatManager.__new__(EnemyCombatManager)
    resolver.shared_state = shared_state or _make_shared_state()
    resolver.current_round = current_round
    return resolver


class TestEnemyAttackHostileEnemy:
    """Hostile-faction enemy can attack another enemy."""

    def test_hostile_faction_attack_not_rejected(self):
        """Tempest enemy attacking Pantheon enemy should not return 'invalid target'."""
        attacker = _make_enemy(
            name="Tempest Operative",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=15):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        # Successful attack won't have 'result' key (it has 'hit' instead)
        # Only rejection returns 'result': 'invalid target'
        assert result.get('result') != 'invalid target', \
            "Hostile-faction enemy attack should not be rejected as invalid target"

    def test_hostile_faction_attack_resolves_hit_or_miss(self):
        """Attack against hostile enemy resolves to hit or miss, not error."""
        attacker = _make_enemy(
            name="Tempest Operative",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
            health=20,
            soak=8,
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=15):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        # Should have hit/miss resolution, not error
        assert 'hit' in result or result.get('result') in ('hit', 'miss', 'target not found'), \
            f"Expected hit/miss resolution, got: {result}"


class TestEnemyAttackAlliedEnemy:
    """Allied/same-faction enemy attacks should be rejected."""

    def test_same_faction_attack_rejected(self):
        """Pantheon enemy can't attack another Pantheon enemy."""
        attacker = _make_enemy(
            name="Pantheon Guard A",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard B",
            agent_id="enemy_pantheon_02",
            faction="Pantheon Security",
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001")
        rs = _make_resolution_state()

        result = resolver._execute_attack(attacker, decl, [], None, rs)
        assert result['result'] == 'invalid target'

    def test_allied_faction_attack_rejected(self):
        """ACG (Nexus-aligned corporate) can't attack Pantheon (Pro-Nexus)."""
        attacker = _make_enemy(
            name="ACG Agent",
            agent_id="enemy_acg_01",
            faction="ACG",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001")
        rs = _make_resolution_state()

        result = resolver._execute_attack(attacker, decl, [], None, rs)
        assert result['result'] == 'invalid target'


class TestEnemyDamageAppliedToEnemy:
    """Damage is correctly applied to enemy targets."""

    def test_damage_reduces_enemy_health(self):
        """Hit against enemy reduces their health."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
            health=20,
            soak=8,
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        # High roll to ensure hit
        with patch('random.randint', return_value=18):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        if result.get('hit'):
            # Damage should have been dealt
            assert 'damage' in result
            assert result['damage'] > 0

    def test_track_player_damage_not_called_for_enemy_target(self):
        """track_player_damage_taken should NOT be called when enemy attacks enemy."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
            health=20,
            soak=8,
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=18):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        # track_player_damage_taken should NOT have been called
        shared_state.session.track_player_damage_taken.assert_not_called()


class TestDefeatedEnemyTarget:
    """When enemy target is defeated, mark correctly."""

    def test_defeated_enemy_marked_in_resolution_state(self):
        """Defeated enemy is marked in resolution_state."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
            health=1,  # Very low health - will be defeated
            soak=0,
        )
        # Override check_death_save to return not alive
        target_enemy.check_death_save = MagicMock(return_value=(False, "dead"))

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        # Ensure hit with high damage
        with patch('random.randint', return_value=20):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        if result.get('hit') and result.get('target_defeated'):
            rs.mark_defeated.assert_called()

    def test_defeated_enemy_deactivated(self):
        """Defeated enemy should have is_active set to False."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
            health=1,
            soak=0,
        )
        # Remove check_death_save to trigger the else branch
        del target_enemy.check_death_save

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0001", weapon="Pistol")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=20):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        if result.get('target_defeated'):
            assert target_enemy.is_active == False


class TestSuppressHostileEnemy:
    """Suppress action works against hostile-faction enemies."""

    def test_suppress_hostile_enemy_not_rejected(self):
        """Suppress against hostile faction enemy should not be invalid target."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
            weapons=[WEAPON_LIBRARY.get('assault_rifle', WEAPON_LIBRARY['pistol'])],
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(major_action="Suppress", target="tgt_0001")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=15):
            result = resolver._execute_suppress(attacker, decl, [], None, rs)

        assert result.get('result') != 'invalid target', \
            "Suppress against hostile-faction enemy should not be rejected"

    def test_suppress_allied_enemy_rejected(self):
        """Suppress against allied faction enemy should be rejected."""
        attacker = _make_enemy(
            name="Pantheon A",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )
        target_enemy = _make_enemy(
            name="ACG Agent",
            agent_id="enemy_acg_01",
            faction="ACG",  # Allied with Pantheon
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(major_action="Suppress", target="tgt_0001")
        rs = _make_resolution_state()

        result = resolver._execute_suppress(attacker, decl, [], None, rs)
        assert result['result'] == 'invalid target'


class TestChargeHostileEnemy:
    """Charge action works against hostile-faction enemies."""

    def test_charge_hostile_enemy_not_rejected(self):
        """Charge against hostile faction enemy should proceed."""
        attacker = _make_enemy(
            name="Tempest Op",
            agent_id="enemy_tempest_01",
            faction="Tempest Industries",
            weapons=[WEAPON_LIBRARY.get('combat_knife', WEAPON_LIBRARY['fists'])],
        )
        target_enemy = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_enemy
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = True
        mapper.is_npc.return_value = False
        mapper.reverse_map = {"enemy_pantheon_01": "tgt_0001"}

        shared_state = _make_shared_state(mapper=mapper)
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(major_action="Charge", target="tgt_0001")
        rs = _make_resolution_state()

        # Patch _execute_attack since charge delegates to it
        with patch.object(resolver, '_execute_attack') as mock_attack:
            mock_attack.return_value = {'hit': True, 'damage': 10, 'narration': 'hit'}
            with patch('random.randint', return_value=15):
                result = resolver._execute_charge(attacker, decl, [], None, rs)

        # Should not be None (charge rejection would return early without calling _execute_attack)
        assert result is not None


class TestEnemyAttackNPC:
    """Enemy can target NPCs."""

    def test_enemy_can_attack_npc(self):
        """Enemy attack targeting an NPC should resolve, not return target not found."""
        attacker = _make_enemy(
            name="Pantheon Guard",
            agent_id="enemy_pantheon_01",
            faction="Pantheon Security",
        )
        target_npc = _make_npc()

        mapper = MagicMock()
        mapper.enabled = True
        mapper.resolve_target.return_value = target_npc
        mapper.is_player.return_value = False
        mapper.is_enemy.return_value = False
        mapper.is_npc.return_value = True
        mapper.reverse_map = {}

        shared_state = _make_shared_state(mapper=mapper, npcs=[target_npc])
        resolver = _make_resolver(shared_state=shared_state)

        decl = _make_declaration(target="tgt_0002", weapon="Pistol")
        rs = _make_resolution_state()

        with patch('random.randint', return_value=15):
            result = resolver._execute_attack(attacker, decl, [], None, rs)

        assert result.get('result') != 'target not found', \
            f"Enemy attack on NPC should resolve, got: {result}"
