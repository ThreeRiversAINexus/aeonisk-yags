"""Unit tests for Environmental Objects & Destructibles system (Spec 10).

Tests cover:
- Phase 1: Schema (health, max_health, is_destructible, apply_damage, is_destroyed)
- Phase 2: Target ID integration (env objects get tgt_xxxx, resolve, is_env_object)
- Phase 3: Damage application via _process_structured_damage_effects
- Phase 4: Display (combatant list includes env objects)
"""

import pytest
from unittest.mock import MagicMock, patch
from scripts.aeonisk.multiagent.shared_state import (
    SharedState,
    EnvironmentalObject,
    EnvironmentalObjectType,
    generate_env_object_id
)
from scripts.aeonisk.multiagent.target_ids import TargetIDMapper
from scripts.aeonisk.multiagent.schemas.story_events import EnvObjectSpawn


# =============================================================================
# Phase 1: Schema — EnvironmentalObject health, destructibility, damage
# =============================================================================


class TestEnvironmentalObjectCreation:
    """Test environmental object dataclass and ID generation."""

    def test_generate_env_object_id_format(self):
        """Test that generated IDs follow env_xxxx format."""
        obj_id = generate_env_object_id()

        assert obj_id.startswith("env_")
        assert len(obj_id) == 8  # "env_" + 4 chars
        suffix = obj_id[4:]
        assert suffix.isalnum()
        assert suffix == suffix.lower()

    def test_generate_env_object_id_unique(self):
        """Test that multiple IDs are unique."""
        ids = [generate_env_object_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_env_object_auto_id_generation(self):
        """Test that EnvironmentalObject auto-generates ID if not provided."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Test Terminal",
            description="A test terminal"
        )
        assert obj.object_id is not None
        assert obj.object_id.startswith("env_")

    def test_env_object_custom_id(self):
        """Test that custom ID is preserved when provided."""
        custom_id = "env_test"
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Test Door",
            description="A test door",
            object_id=custom_id
        )
        assert obj.object_id == custom_id

    def test_env_object_with_state(self):
        """Test environmental object with initial state."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Security Terminal",
            description="A locked terminal",
            state={"locked": True, "powered": True, "health": 30}
        )
        assert obj.state["locked"] is True
        assert obj.state["powered"] is True
        assert obj.state["health"] == 30

    def test_env_object_empty_state(self):
        """Test environmental object with default empty state."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.CARGO,
            name="Supply Crate",
            description="A sealed crate"
        )
        assert obj.state == {}

    def test_env_object_all_types(self):
        """Test creating objects of all valid types."""
        types_to_test = [
            EnvironmentalObjectType.DOOR,
            EnvironmentalObjectType.TERMINAL,
            EnvironmentalObjectType.CARGO,
            EnvironmentalObjectType.VEHICLE,
            EnvironmentalObjectType.BARRIER,
            EnvironmentalObjectType.STRUCTURE,
            EnvironmentalObjectType.EQUIPMENT
        ]
        for obj_type in types_to_test:
            obj = EnvironmentalObject(
                object_type=obj_type,
                name=f"Test {obj_type.value}",
                description=f"A test {obj_type.value}"
            )
            assert obj.object_type == obj_type
            assert obj.object_id.startswith("env_")


class TestEnvironmentalObjectHealth:
    """Test health fields and destructibility on EnvironmentalObject."""

    def test_env_object_has_health_fields(self):
        """EnvironmentalObject accepts health, max_health, is_destructible."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Blast Door",
            description="Reinforced door",
            health=30,
            max_health=30,
            is_destructible=True
        )
        assert obj.health == 30
        assert obj.max_health == 30
        assert obj.is_destructible is True
        assert obj.is_destroyed is False

    def test_env_object_default_health_none(self):
        """Objects without explicit health have health=None."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.EQUIPMENT,
            name="Sensor Array",
            description="A sensor"
        )
        assert obj.health is None
        assert obj.max_health is None
        assert obj.is_destructible is True  # Default
        assert obj.is_destroyed is False

    def test_env_object_apply_damage(self):
        """Damage reduces health, returns actual damage dealt."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )
        actual = obj.apply_damage(10)
        assert actual == 10
        assert obj.health == 20
        assert obj.is_destroyed is False

    def test_env_object_destroy_at_zero_hp(self):
        """Object at 0 HP triggers _on_destroyed() state change."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=5,
            max_health=30,
            state={"locked": True}
        )
        actual = obj.apply_damage(10)
        assert actual == 5  # Capped at remaining HP
        assert obj.health == 0
        assert obj.is_destroyed is True
        assert obj.state["locked"] is False
        assert obj.state["destroyed"] is True

    def test_env_object_overkill_capped(self):
        """Damage exceeding HP is capped; returns only remaining HP."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Console",
            description="A terminal",
            health=10,
            max_health=10
        )
        actual = obj.apply_damage(999)
        assert actual == 10
        assert obj.health == 0
        assert obj.is_destroyed is True

    def test_env_object_non_destructible_ignores_damage(self):
        """Non-destructible objects return 0 damage and stay intact."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.STRUCTURE,
            name="Steel Pillar",
            description="Structural pillar",
            health=100,
            max_health=100,
            is_destructible=False
        )
        actual = obj.apply_damage(50)
        assert actual == 0
        assert obj.health == 100
        assert obj.is_destroyed is False

    def test_env_object_no_health_not_destroyable(self):
        """Objects with health=None cannot be destroyed."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.EQUIPMENT,
            name="Sensor Array",
            description="A sensor"
        )
        assert obj.health is None
        assert obj.is_destroyed is False
        actual = obj.apply_damage(999)
        assert actual == 0

    def test_env_object_already_destroyed_ignores_damage(self):
        """Already-destroyed objects ignore further damage."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=0,
            max_health=30
        )
        assert obj.is_destroyed is True
        actual = obj.apply_damage(10)
        assert actual == 0
        assert obj.health == 0

    def test_env_object_target_id_field(self):
        """EnvironmentalObject has target_id field (None by default)."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )
        assert obj.target_id is None


class TestEnvironmentalObjectDestroyedState:
    """Test type-specific state changes on destruction."""

    def test_destroyed_state_door(self):
        """Destroyed DOOR sets locked=False, open=True."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=10,
            max_health=10,
            state={"locked": True}
        )
        obj.apply_damage(10)
        assert obj.state["locked"] is False
        assert obj.state["open"] is True
        assert obj.state["destroyed"] is True

    def test_destroyed_state_terminal(self):
        """Destroyed TERMINAL sets powered=False."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Console",
            description="A terminal",
            health=10,
            max_health=10,
            state={"powered": True}
        )
        obj.apply_damage(10)
        assert obj.state["powered"] is False
        assert obj.state["destroyed"] is True

    def test_destroyed_state_barrier(self):
        """Destroyed BARRIER sets intact=False."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.BARRIER,
            name="Barricade",
            description="A barricade",
            health=20,
            max_health=20,
            state={"intact": True}
        )
        obj.apply_damage(20)
        assert obj.state["intact"] is False

    def test_destroyed_state_vehicle(self):
        """Destroyed VEHICLE sets operational=False."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.VEHICLE,
            name="Shuttle",
            description="A shuttle",
            health=50,
            max_health=50,
            state={"operational": True}
        )
        obj.apply_damage(50)
        assert obj.state["operational"] is False

    def test_destroyed_state_generic(self):
        """Destroyed generic object sets destroyed=True, functional=False."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.CARGO,
            name="Crate",
            description="A crate",
            health=20,
            max_health=20,
            state={}
        )
        obj.apply_damage(20)
        assert obj.state["destroyed"] is True
        assert obj.state["functional"] is False

    def test_cover_degradation_proportional(self):
        """Cover value degrades proportionally to HP lost."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.BARRIER,
            name="Barricade",
            description="A barricade",
            health=50,
            max_health=50,
            cover_value=4
        )
        # At full health, cover_value = 4
        assert obj.cover_value == 4

        # After losing half HP, effective cover should be proportionally reduced
        obj.apply_damage(25)
        assert obj.health == 25
        # effective_cover_value should be about half
        effective = obj.effective_cover_value
        assert effective == 2  # 4 * (25/50) = 2

    def test_cover_degradation_destroyed_zero(self):
        """Destroyed objects have 0 effective cover."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.BARRIER,
            name="Barricade",
            description="A barricade",
            health=10,
            max_health=50,
            cover_value=4
        )
        obj.apply_damage(10)
        assert obj.is_destroyed is True
        assert obj.effective_cover_value == 0

    def test_cover_value_none_when_not_set(self):
        """Objects without cover_value have None."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )
        assert obj.cover_value is None
        assert obj.effective_cover_value == 0


# =============================================================================
# Phase 1.5: SharedState management
# =============================================================================


class TestSharedStateEnvObjects:
    """Test SharedState environmental object management methods."""

    def test_add_env_object(self):
        """Test adding environmental object to shared state."""
        state = SharedState()
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Test Terminal",
            description="A test terminal"
        )
        state.add_env_object(obj)
        assert len(state.current_env_objects) == 1
        assert state.current_env_objects[0] == obj

    def test_add_multiple_env_objects(self):
        """Test adding multiple environmental objects."""
        state = SharedState()
        terminal = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Terminal",
            description="A terminal"
        )
        door = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door"
        )
        state.add_env_object(terminal)
        state.add_env_object(door)
        assert len(state.current_env_objects) == 2

    def test_add_duplicate_env_object(self):
        """Test that duplicate objects (same ID) are not added twice."""
        state = SharedState()
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.CARGO,
            name="Crate",
            description="A crate",
            object_id="env_test"
        )
        state.add_env_object(obj)
        state.add_env_object(obj)
        assert len(state.current_env_objects) == 1

    def test_remove_env_object(self):
        """Test removing environmental object by ID."""
        state = SharedState()
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Terminal",
            description="A terminal",
            object_id="env_remove"
        )
        state.add_env_object(obj)
        assert len(state.current_env_objects) == 1
        removed = state.remove_env_object("env_remove")
        assert removed is True
        assert len(state.current_env_objects) == 0

    def test_remove_nonexistent_env_object(self):
        """Test removing object that doesn't exist returns False."""
        state = SharedState()
        removed = state.remove_env_object("env_nonexistent")
        assert removed is False

    def test_get_env_object_by_id(self):
        """Test retrieving environmental object by ID."""
        state = SharedState()
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Test Door",
            description="A test door",
            object_id="env_get"
        )
        state.add_env_object(obj)
        retrieved = state.get_env_object_by_id("env_get")
        assert retrieved is not None
        assert retrieved.object_id == "env_get"
        assert retrieved.name == "Test Door"

    def test_get_nonexistent_env_object(self):
        """Test retrieving non-existent object returns None."""
        state = SharedState()
        retrieved = state.get_env_object_by_id("env_nonexistent")
        assert retrieved is None

    def test_get_all_env_objects(self):
        """Test retrieving all environmental objects."""
        state = SharedState()
        obj1 = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Terminal 1",
            description="First terminal"
        )
        obj2 = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door 1",
            description="First door"
        )
        state.add_env_object(obj1)
        state.add_env_object(obj2)
        all_objects = state.get_all_env_objects()
        assert len(all_objects) == 2
        assert obj1 in all_objects
        assert obj2 in all_objects

    def test_get_all_env_objects_empty(self):
        """Test get_all returns empty list when no objects."""
        state = SharedState()
        all_objects = state.get_all_env_objects()
        assert all_objects == []

    def test_clear_env_objects(self):
        """Test clearing all environmental objects."""
        state = SharedState()
        for i in range(3):
            obj = EnvironmentalObject(
                object_type=EnvironmentalObjectType.CARGO,
                name=f"Crate {i}",
                description=f"Crate number {i}"
            )
            state.add_env_object(obj)
        assert len(state.current_env_objects) == 3
        state.clear_env_objects()
        assert len(state.current_env_objects) == 0


# =============================================================================
# Phase 1.6: EnvObjectSpawn schema
# =============================================================================


class TestEnvObjectSpawnSchema:
    """Test EnvObjectSpawn Pydantic schema validation."""

    def test_valid_env_object_spawn(self):
        """Test creating valid EnvObjectSpawn."""
        spawn = EnvObjectSpawn(
            object_type="terminal",
            name="Security Terminal",
            description="A flickering terminal panel embedded in the wall",
            initial_state={"locked": True, "powered": True},
            narrative_reason="Player mentioned hacking terminal"
        )
        assert spawn.object_type == "terminal"
        assert spawn.name == "Security Terminal"
        assert spawn.initial_state["locked"] is True

    def test_env_spawn_with_empty_state(self):
        """Test EnvObjectSpawn with default empty state."""
        spawn = EnvObjectSpawn(
            object_type="door",
            name="Airlock",
            description="A sealed airlock",
            narrative_reason="Narrative mentioned sealed door"
        )
        assert spawn.initial_state == {}

    def test_env_spawn_name_length_validation(self):
        """Test that name field enforces min/max length."""
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="door",
                name="ABC",
                description="A test door with short name",
                narrative_reason="Testing validation"
            )
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="door",
                name="A" * 51,
                description="A test door with long name",
                narrative_reason="Testing validation"
            )

    def test_env_spawn_description_length_validation(self):
        """Test that description field enforces min/max length."""
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="terminal",
                name="Test Terminal",
                description="Short",
                narrative_reason="Testing validation"
            )
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="terminal",
                name="Test Terminal",
                description="A" * 201,
                narrative_reason="Testing validation"
            )

    def test_env_spawn_narrative_reason_validation(self):
        """Test that narrative_reason field enforces min/max length."""
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="cargo",
                name="Supply Crate",
                description="A sealed cargo crate",
                narrative_reason="Short"
            )
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="cargo",
                name="Supply Crate",
                description="A sealed cargo crate",
                narrative_reason="A" * 201
            )

    def test_env_spawn_all_valid_types(self):
        """Test spawning with all valid object types."""
        valid_types = ["door", "terminal", "cargo", "vehicle", "barrier", "structure", "equipment"]
        for obj_type in valid_types:
            spawn = EnvObjectSpawn(
                object_type=obj_type,
                name=f"Test {obj_type.capitalize()}",
                description=f"A test {obj_type} object for validation",
                narrative_reason=f"Testing {obj_type} spawn validation"
            )
            assert spawn.object_type == obj_type

    def test_env_spawn_with_health(self):
        """Test EnvObjectSpawn with health in initial_state."""
        spawn = EnvObjectSpawn(
            object_type="door",
            name="Blast Door",
            description="A reinforced blast door blocking the corridor",
            initial_state={"locked": True, "health": 30},
            narrative_reason="Players need to breach this door"
        )
        assert spawn.initial_state["health"] == 30


# =============================================================================
# Phase 2: Target ID Integration
# =============================================================================


class TestEnvObjectTargetRegistration:
    """Test env object registration in TargetIDMapper."""

    def test_env_object_gets_target_id(self):
        """Destructible env objects receive tgt_xxxx IDs from TargetIDMapper."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )

        mapper.assign_ids(
            player_agents=[],
            enemy_agents=[],
            env_objects=[obj]
        )

        assert obj.target_id is not None
        assert obj.target_id.startswith("tgt_")

    def test_env_object_resolved_by_target_id(self):
        """TargetIDMapper.resolve_target() returns env object for its tgt_xxxx."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )

        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])

        resolved = mapper.resolve_target(obj.target_id)
        assert resolved is obj

    def test_is_env_object_returns_true(self):
        """is_env_object() returns True for env objects."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )

        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])
        assert mapper.is_env_object(obj.target_id) is True

    def test_is_env_object_returns_false_for_combatant(self):
        """is_env_object() returns False for player/enemy agents."""
        mapper = TargetIDMapper()
        mapper.enable()

        # Mock a player agent
        mock_player = MagicMock()
        mock_player.agent_id = "player_01"
        mock_player.character_state = MagicMock()
        mock_player.character_state.name = "Test Player"

        mapper.assign_ids(
            player_agents=[mock_player],
            enemy_agents=[]
        )

        player_tid = mapper.get_target_id("player_01")
        assert player_tid is not None
        assert mapper.is_env_object(player_tid) is False

    def test_is_env_object_returns_false_for_unknown_id(self):
        """is_env_object() returns False for unknown target IDs."""
        mapper = TargetIDMapper()
        mapper.enable()
        assert mapper.is_env_object("tgt_zzzz") is False

    def test_get_combatant_info_env_object(self):
        """get_combatant_info() returns correct type and health for env objects."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.BARRIER,
            name="Barricade",
            description="Cover",
            health=50,
            max_health=50
        )

        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])
        info = mapper.get_combatant_info(obj.target_id)
        assert info is not None
        assert info['type'] == 'env_object'
        assert info['health'] == 50
        assert info['max_health'] == 50
        assert info['name'] == 'Barricade'
        assert info['destroyed'] is False
        assert info['is_destructible'] is True
        assert info['object_type'] == 'barrier'

    def test_env_object_mixed_with_combatants(self):
        """Env objects and regular combatants coexist in target ID mapper."""
        mapper = TargetIDMapper()
        mapper.enable()

        # Mock player
        mock_player = MagicMock()
        mock_player.agent_id = "player_01"
        mock_player.character_state = MagicMock()
        mock_player.character_state.name = "Hero"

        # Mock enemy
        mock_enemy = MagicMock()
        mock_enemy.agent_id = "enemy_grunt_001"
        mock_enemy.is_active = True
        mock_enemy.name = "Grunt"
        mock_enemy.tactics = "aggressive"

        # Env object
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=30,
            max_health=30
        )

        mapper.assign_ids(
            player_agents=[mock_player],
            enemy_agents=[mock_enemy],
            env_objects=[obj]
        )

        # Should have 3 target IDs total
        all_ids = mapper.get_all_target_ids()
        assert len(all_ids) == 3

        # Each should resolve correctly
        assert mapper.resolve_target(obj.target_id) is obj
        assert mapper.is_env_object(obj.target_id) is True

        player_tid = mapper.get_target_id("player_01")
        assert mapper.is_player(player_tid) is True
        assert mapper.is_env_object(player_tid) is False

    def test_destroyed_objects_excluded_from_id_assignment(self):
        """Already-destroyed objects should not get new target IDs (session filter)."""
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=0,
            max_health=30
        )
        # Session.py filters destroyed objects before passing to assign_ids
        active_objects = [o for o in [obj] if not o.is_destroyed]
        assert len(active_objects) == 0

    def test_assign_ids_without_env_objects_backward_compat(self):
        """assign_ids() without env_objects param works (backward compatibility)."""
        mapper = TargetIDMapper()
        mapper.enable()

        mock_player = MagicMock()
        mock_player.agent_id = "player_01"
        mock_player.character_state = MagicMock()
        mock_player.character_state.name = "Player"

        # Should work without env_objects param
        mapper.assign_ids(
            player_agents=[mock_player],
            enemy_agents=[]
        )
        all_ids = mapper.get_all_target_ids()
        assert len(all_ids) == 1


# =============================================================================
# Phase 3: Damage Application via _process_structured_damage_effects
# =============================================================================


class TestStructuredDamageEnvObjects:
    """Test _process_structured_damage_effects with env object targets."""

    def _make_env_object(self, health=30, max_health=30, name="Blast Door",
                         obj_type=EnvironmentalObjectType.DOOR, is_destructible=True):
        """Helper to create a test env object with target ID."""
        return EnvironmentalObject(
            object_type=obj_type,
            name=name,
            description=f"A test {name}",
            health=health,
            max_health=max_health,
            is_destructible=is_destructible,
            object_id=f"env_test"
        )

    def _make_shared_state_with_env(self, env_obj):
        """Helper to set up SharedState with env object registered in mapper."""
        shared_state = SharedState()
        shared_state.add_env_object(env_obj)

        mapper = shared_state.get_target_id_mapper()
        mapper.enable()
        mapper.assign_ids(
            player_agents=[],
            enemy_agents=[],
            env_objects=[env_obj]
        )
        return shared_state

    def test_structured_damage_resolves_env_object(self):
        """DamageEffect targeting env object tgt_xxxx reduces object HP."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        env_obj = self._make_env_object(health=30, max_health=30)
        shared_state = self._make_shared_state_with_env(env_obj)

        # Create mock DamageEffect
        damage_effect = MagicMock()
        damage_effect.target = env_obj.target_id
        damage_effect.dealt = 10
        damage_effect.base_damage = 10
        damage_effect.damage_type = "wound"

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            attacker_id="player_01",
            attacker_name="Test Player"
        )

        assert env_obj.health == 20
        assert len(messages) > 0
        # Message should mention the object name and damage
        msg_text = " ".join(messages)
        assert "Blast Door" in msg_text
        assert "10" in msg_text

    def test_structured_damage_destroys_env_object(self):
        """DamageEffect that reduces env object to 0 HP triggers destruction."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        env_obj = self._make_env_object(health=10, max_health=30)
        shared_state = self._make_shared_state_with_env(env_obj)

        damage_effect = MagicMock()
        damage_effect.target = env_obj.target_id
        damage_effect.dealt = 15
        damage_effect.base_damage = 15
        damage_effect.damage_type = "wound"

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            attacker_id="player_01",
            attacker_name="Test Player"
        )

        assert env_obj.health == 0
        assert env_obj.is_destroyed is True
        msg_text = " ".join(messages)
        assert "DESTROYED" in msg_text

    def test_structured_damage_indestructible_object(self):
        """DamageEffect targeting indestructible object has no effect."""
        from scripts.aeonisk.multiagent.dm import _process_structured_damage_effects

        env_obj = self._make_env_object(
            health=100, max_health=100, is_destructible=False,
            name="Steel Pillar", obj_type=EnvironmentalObjectType.STRUCTURE
        )
        shared_state = self._make_shared_state_with_env(env_obj)

        damage_effect = MagicMock()
        damage_effect.target = env_obj.target_id
        damage_effect.dealt = 50
        damage_effect.base_damage = 50
        damage_effect.damage_type = "wound"

        messages = _process_structured_damage_effects(
            damage_effects=[damage_effect],
            shared_state=shared_state,
            current_round=1,
            attacker_id="player_01",
            attacker_name="Test Player"
        )

        assert env_obj.health == 100
        assert env_obj.is_destroyed is False
        msg_text = " ".join(messages)
        assert "impervious" in msg_text.lower()


# =============================================================================
# Phase 4: Display — combatant list includes env objects
# =============================================================================


class TestEnvObjectDisplay:
    """Test that env objects appear in DM combatant list."""

    def test_combatant_list_includes_env_objects(self):
        """DM combatant list shows env objects with target IDs and health."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.BARRIER,
            name="Barricade",
            description="Cover",
            health=50,
            max_health=50
        )

        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])

        info = mapper.get_combatant_info(obj.target_id)
        assert info is not None
        assert info['type'] == 'env_object'
        assert info['health'] == 50
        assert info['max_health'] == 50

    def test_destroyed_env_object_in_combatant_info(self):
        """Destroyed env objects show destroyed=True in info."""
        mapper = TargetIDMapper()
        mapper.enable()

        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Door",
            description="A door",
            health=0,
            max_health=30
        )
        # Note: destroyed objects wouldn't normally be re-registered,
        # but test the info output if they are
        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])

        info = mapper.get_combatant_info(obj.target_id)
        assert info is not None
        assert info['destroyed'] is True


# =============================================================================
# Integration tests
# =============================================================================


class TestEnvObjectIntegration:
    """Test integration scenarios for environmental objects."""

    def test_spawn_to_shared_state_workflow(self):
        """Test complete workflow: spawn schema -> shared state."""
        spawn = EnvObjectSpawn(
            object_type="terminal",
            name="Security Terminal",
            description="A glowing terminal with access logs",
            initial_state={"locked": True, "powered": True},
            narrative_reason="Player wants to hack systems"
        )

        obj_type = EnvironmentalObjectType[spawn.object_type.upper()]
        env_object = EnvironmentalObject(
            object_type=obj_type,
            name=spawn.name,
            description=spawn.description,
            state=spawn.initial_state
        )

        state = SharedState()
        state.add_env_object(env_object)

        assert len(state.current_env_objects) == 1
        retrieved = state.current_env_objects[0]
        assert retrieved.name == "Security Terminal"
        assert retrieved.state["locked"] is True
        assert retrieved.object_id.startswith("env_")

    def test_multiple_object_lifecycle(self):
        """Test managing lifecycle of multiple environmental objects."""
        state = SharedState()

        terminal = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Control Terminal",
            description="A terminal",
            object_id="env_term"
        )
        state.add_env_object(terminal)

        door = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Sealed Door",
            description="A door",
            object_id="env_door"
        )
        state.add_env_object(door)

        assert len(state.current_env_objects) == 2

        state.remove_env_object("env_term")
        assert len(state.current_env_objects) == 1

        remaining = state.get_env_object_by_id("env_door")
        assert remaining is not None
        assert remaining.name == "Sealed Door"

    def test_state_modification(self):
        """Test modifying environmental object state."""
        state = SharedState()

        door = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Cargo Bay Door",
            description="A reinforced door",
            state={"locked": True, "health": 50}
        )
        state.add_env_object(door)

        retrieved = state.current_env_objects[0]
        retrieved.state["locked"] = False
        retrieved.state["health"] = 30

        assert state.current_env_objects[0].state["locked"] is False
        assert state.current_env_objects[0].state["health"] == 30

    def test_full_damage_lifecycle(self):
        """Test complete lifecycle: create -> register -> damage -> destroy."""
        # Create
        obj = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Blast Door",
            description="A reinforced blast door",
            health=30,
            max_health=30,
            state={"locked": True}
        )

        # Register with mapper
        mapper = TargetIDMapper()
        mapper.enable()
        mapper.assign_ids(player_agents=[], enemy_agents=[], env_objects=[obj])

        assert obj.target_id is not None
        assert obj.target_id.startswith("tgt_")

        # Damage
        actual = obj.apply_damage(20)
        assert actual == 20
        assert obj.health == 10
        assert obj.is_destroyed is False

        # Destroy
        actual = obj.apply_damage(15)
        assert actual == 10  # Capped at remaining
        assert obj.health == 0
        assert obj.is_destroyed is True
        assert obj.state["locked"] is False
        assert obj.state["destroyed"] is True
        assert obj.state["open"] is True
