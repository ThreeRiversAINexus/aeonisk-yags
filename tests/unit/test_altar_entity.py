"""
Unit tests for Altar entity system.

Tests verify:
- Altar dataclass structure (altar_id, type, quality, location)
- SharedState altar tracking (add, remove, lookup)
- Altar quality → bonus mapping (1-3: +1, 4-7: +2, 8-10: +3)
"""

import pytest
from scripts.aeonisk.multiagent.shared_state import SharedState, Altar, AltarType


class TestAltarDataclass:
    """Test Altar entity structure."""

    def test_altar_creation(self):
        """Test creating an Altar instance."""
        altar = Altar(
            altar_id="alt_test1",
            altar_type=AltarType.RITUAL_ALTAR,
            quality=5,
            location="Temple Sanctum"
        )

        assert altar.altar_id == "alt_test1"
        assert altar.altar_type == AltarType.RITUAL_ALTAR
        assert altar.quality == 5
        assert altar.location == "Temple Sanctum"

    def test_altar_auto_generates_id(self):
        """Test that altar_id is auto-generated if not provided."""
        altar = Altar(
            altar_type=AltarType.RITUAL_ALTAR,
            quality=5,
            location="Temple"
        )

        assert altar.altar_id.startswith("alt_")
        assert len(altar.altar_id) == 8  # "alt_" + 4 random chars

    def test_altar_quality_range_valid(self):
        """Test that altar quality is within valid range 1-10."""
        # Valid qualities
        for quality in [1, 5, 10]:
            altar = Altar(
                altar_type=AltarType.RITUAL_ALTAR,
                quality=quality,
                location="Test"
            )
            assert 1 <= altar.quality <= 10

    def test_altar_quality_determines_bonus(self):
        """Test that altar quality maps to correct bonus."""
        # Quality 1-3 → +1 bonus
        altar1 = Altar(altar_type=AltarType.RITUAL_ALTAR, quality=2, location="Low")
        assert altar1.get_ritual_bonus() == 1

        # Quality 4-7 → +2 bonus
        altar2 = Altar(altar_type=AltarType.RITUAL_ALTAR, quality=6, location="Mid")
        assert altar2.get_ritual_bonus() == 2

        # Quality 8-10 → +3 bonus
        altar3 = Altar(altar_type=AltarType.RITUAL_ALTAR, quality=9, location="High")
        assert altar3.get_ritual_bonus() == 3


class TestAltarTypes:
    """Test AltarType enum."""

    def test_altar_types_exist(self):
        """Test that AltarType enum has expected types."""
        assert AltarType.RITUAL_ALTAR
        assert AltarType.NEXUS_ALTAR
        assert AltarType.FREEBORN_ALTAR
        assert AltarType.BLACK_MARKET_ALTAR
        assert AltarType.ABANDONED_ALTAR


class TestSharedStateAltarTracking:
    """Test SharedState methods for tracking altars."""

    def test_shared_state_has_altar_list(self):
        """Test that SharedState has current_altars list."""
        state = SharedState()
        assert hasattr(state, 'current_altars')
        assert isinstance(state.current_altars, list)
        assert len(state.current_altars) == 0

    def test_add_altar_to_shared_state(self):
        """Test adding an altar to SharedState."""
        state = SharedState()
        altar = Altar(
            altar_id="alt_test1",
            altar_type=AltarType.RITUAL_ALTAR,
            quality=5,
            location="Temple"
        )

        state.add_altar(altar)

        assert len(state.current_altars) == 1
        assert state.current_altars[0] == altar

    def test_add_multiple_altars(self):
        """Test adding multiple altars."""
        state = SharedState()
        altar1 = Altar(altar_id="alt_1", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple 1")
        altar2 = Altar(altar_id="alt_2", altar_type=AltarType.FREEBORN_ALTAR, quality=3, location="Market")

        state.add_altar(altar1)
        state.add_altar(altar2)

        assert len(state.current_altars) == 2

    def test_add_duplicate_altar_by_id(self):
        """Test that adding duplicate altar by ID is prevented."""
        state = SharedState()
        altar1 = Altar(altar_id="alt_dup", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple")
        altar2 = Altar(altar_id="alt_dup", altar_type=AltarType.RITUAL_ALTAR, quality=7, location="Temple")

        state.add_altar(altar1)
        state.add_altar(altar2)  # Should be skipped

        assert len(state.current_altars) == 1
        assert state.current_altars[0].quality == 5  # First one kept

    def test_get_altar_by_id(self):
        """Test retrieving altar by ID."""
        state = SharedState()
        altar = Altar(altar_id="alt_find", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple")
        state.add_altar(altar)

        found = state.get_altar_by_id("alt_find")

        assert found is not None
        assert found.altar_id == "alt_find"
        assert found.quality == 5

    def test_get_altar_by_id_not_found(self):
        """Test getting non-existent altar returns None."""
        state = SharedState()

        found = state.get_altar_by_id("alt_nonexistent")

        assert found is None

    def test_remove_altar(self):
        """Test removing an altar from SharedState."""
        state = SharedState()
        altar = Altar(altar_id="alt_remove", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple")
        state.add_altar(altar)

        assert len(state.current_altars) == 1

        state.remove_altar("alt_remove")

        assert len(state.current_altars) == 0

    def test_remove_nonexistent_altar(self):
        """Test removing non-existent altar doesn't error."""
        state = SharedState()
        altar = Altar(altar_id="alt_exists", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple")
        state.add_altar(altar)

        # Should not raise error
        state.remove_altar("alt_nonexistent")

        # Original altar still there
        assert len(state.current_altars) == 1

    def test_get_all_altars(self):
        """Test getting all altars."""
        state = SharedState()
        altar1 = Altar(altar_id="alt_1", altar_type=AltarType.RITUAL_ALTAR, quality=5, location="Temple 1")
        altar2 = Altar(altar_id="alt_2", altar_type=AltarType.FREEBORN_ALTAR, quality=3, location="Market")

        state.add_altar(altar1)
        state.add_altar(altar2)

        all_altars = state.get_all_altars()

        assert len(all_altars) == 2
        assert altar1 in all_altars
        assert altar2 in all_altars


class TestAltarIDGeneration:
    """Test altar ID generation utility."""

    def test_generate_altar_id_format(self):
        """Test that generate_altar_id creates correct format."""
        from scripts.aeonisk.multiagent.shared_state import generate_altar_id

        altar_id = generate_altar_id()

        assert altar_id.startswith("alt_")
        assert len(altar_id) == 8  # "alt_" + 4 chars

    def test_generate_altar_id_uniqueness(self):
        """Test that generated IDs are mostly unique (collisions rare)."""
        from scripts.aeonisk.multiagent.shared_state import generate_altar_id

        ids = [generate_altar_id() for _ in range(100)]

        # Most IDs should be unique (allow 1-2 collisions in 100 due to randomness)
        unique_count = len(set(ids))
        assert unique_count >= 98, f"Expected at least 98 unique IDs, got {unique_count}"
