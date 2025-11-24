"""Unit tests for Environmental Objects system."""

import pytest
from scripts.aeonisk.multiagent.shared_state import (
    SharedState,
    EnvironmentalObject,
    EnvironmentalObjectType,
    generate_env_object_id
)
from scripts.aeonisk.multiagent.schemas.story_events import EnvObjectSpawn


class TestEnvironmentalObjectCreation:
    """Test environmental object dataclass and ID generation."""

    def test_generate_env_object_id_format(self):
        """Test that generated IDs follow env_xxxx format."""
        obj_id = generate_env_object_id()

        assert obj_id.startswith("env_")
        assert len(obj_id) == 8  # "env_" + 4 chars
        # Check that suffix is alphanumeric lowercase (letters) or digits
        suffix = obj_id[4:]
        assert suffix.isalnum()
        # Ensure no uppercase letters (lowercase letters and digits are both OK)
        assert suffix == suffix.lower()

    def test_generate_env_object_id_unique(self):
        """Test that multiple IDs are unique."""
        ids = [generate_env_object_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All should be unique

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
        state.add_env_object(obj)  # Try to add again

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
        # Too short (< 5 chars)
        with pytest.raises(Exception):  # Pydantic ValidationError
            EnvObjectSpawn(
                object_type="door",
                name="ABC",  # Too short
                description="A test door with short name",
                narrative_reason="Testing validation"
            )

        # Too long (> 50 chars)
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="door",
                name="A" * 51,  # Too long
                description="A test door with long name",
                narrative_reason="Testing validation"
            )

    def test_env_spawn_description_length_validation(self):
        """Test that description field enforces min/max length."""
        # Too short (< 10 chars)
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="terminal",
                name="Test Terminal",
                description="Short",  # Too short
                narrative_reason="Testing validation"
            )

        # Too long (> 200 chars)
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="terminal",
                name="Test Terminal",
                description="A" * 201,  # Too long
                narrative_reason="Testing validation"
            )

    def test_env_spawn_narrative_reason_validation(self):
        """Test that narrative_reason field enforces min/max length."""
        # Too short (< 10 chars)
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="cargo",
                name="Supply Crate",
                description="A sealed cargo crate",
                narrative_reason="Short"  # Too short
            )

        # Too long (> 200 chars)
        with pytest.raises(Exception):
            EnvObjectSpawn(
                object_type="cargo",
                name="Supply Crate",
                description="A sealed cargo crate",
                narrative_reason="A" * 201  # Too long
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


class TestEnvObjectIntegration:
    """Test integration scenarios for environmental objects."""

    def test_spawn_to_shared_state_workflow(self):
        """Test complete workflow: spawn schema → shared state."""
        # 1. Create spawn schema (DM output)
        spawn = EnvObjectSpawn(
            object_type="terminal",
            name="Security Terminal",
            description="A glowing terminal with access logs",
            initial_state={"locked": True, "powered": True},
            narrative_reason="Player wants to hack systems"
        )

        # 2. Process spawn (session.py logic)
        obj_type = EnvironmentalObjectType[spawn.object_type.upper()]
        env_object = EnvironmentalObject(
            object_type=obj_type,
            name=spawn.name,
            description=spawn.description,
            state=spawn.initial_state
        )

        # 3. Add to shared state
        state = SharedState()
        state.add_env_object(env_object)

        # 4. Verify
        assert len(state.current_env_objects) == 1
        retrieved = state.current_env_objects[0]
        assert retrieved.name == "Security Terminal"
        assert retrieved.state["locked"] is True
        assert retrieved.object_id.startswith("env_")

    def test_multiple_object_lifecycle(self):
        """Test managing lifecycle of multiple environmental objects."""
        state = SharedState()

        # Spawn terminal
        terminal = EnvironmentalObject(
            object_type=EnvironmentalObjectType.TERMINAL,
            name="Control Terminal",
            description="A terminal",
            object_id="env_term"
        )
        state.add_env_object(terminal)

        # Spawn door
        door = EnvironmentalObject(
            object_type=EnvironmentalObjectType.DOOR,
            name="Sealed Door",
            description="A door",
            object_id="env_door"
        )
        state.add_env_object(door)

        # Verify both exist
        assert len(state.current_env_objects) == 2

        # Remove terminal (e.g., destroyed)
        state.remove_env_object("env_term")
        assert len(state.current_env_objects) == 1

        # Door still exists
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

        # Retrieve and modify state (e.g., door unlocked)
        retrieved = state.current_env_objects[0]
        retrieved.state["locked"] = False
        retrieved.state["health"] = 30  # Damaged

        # Verify modifications persist
        assert state.current_env_objects[0].state["locked"] is False
        assert state.current_env_objects[0].state["health"] == 30
