"""
Unit tests for altar removal via StoryAdvancement.altar_removals field.

Tests that:
1. altar_removals field is parsed correctly from StoryAdvancement
2. Altars are removed from SharedState when listed in altar_removals
3. Multiple altars can be removed in a single advancement
4. Unlisted altars are preserved
5. Invalid altar IDs are handled gracefully
"""

import pytest
from scripts.aeonisk.multiagent.shared_state import SharedState, Altar, AltarType
from scripts.aeonisk.multiagent.schemas.story_events import StoryAdvancement


class TestAltarRemovalSchema:
    """Test that StoryAdvancement schema supports altar_removals field."""

    def test_story_advancement_has_altar_removals_field(self):
        """Test that StoryAdvancement schema includes altar_removals."""
        # This will fail until we add the field to the schema
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="The nexus altar crumbles as you leave the temple district. The ancient stones crack and fall, scattering void-tainted dust across the abandoned courtyard. Ahead lies a new path through the ruins.",
            altar_removals=["alt_nexus_001", "alt_ritual_002"]
        )

        assert hasattr(advancement, 'altar_removals')
        assert len(advancement.altar_removals) == 2
        assert "alt_nexus_001" in advancement.altar_removals

    def test_altar_removals_defaults_to_empty_list(self):
        """Test that altar_removals defaults to empty list if not provided."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="You move deeper into the corrupted station. The air grows thick with void energy. Flickering emergency lights cast long shadows down the narrow maintenance corridor ahead."
        )

        assert hasattr(advancement, 'altar_removals')
        assert advancement.altar_removals == []

    def test_altar_removals_accepts_empty_list(self):
        """Test that explicitly passing empty list works."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="The vault doors seal behind you with a resonant clang. Ahead, sterile white hallways stretch into the research complex, untouched by void corruption but equally lifeless.",
            altar_removals=[]
        )

        assert advancement.altar_removals == []


class TestAltarRemovalProcessing:
    """Test that altars are removed from SharedState during story advancement."""

    def test_single_altar_removal(self):
        """Test removing a single altar via story advancement."""
        # Setup: Create shared state with altars
        shared_state = SharedState()

        altar1 = Altar(
            altar_type=AltarType.NEXUS_ALTAR,
            quality=5,
            location="Old Temple",
            altar_id="alt_nexus_001"
        )
        altar2 = Altar(
            altar_type=AltarType.RITUAL_ALTAR,
            quality=7,
            location="Hidden Shrine",
            altar_id="alt_ritual_001"
        )

        shared_state.add_altar(altar1)
        shared_state.add_altar(altar2)

        assert len(shared_state.current_altars) == 2

        # Story advancement removes one altar
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="The nexus altar crumbles as you leave the temple, its void-corrupted stones collapsing into rubble. The sacred site is lost, but the path ahead beckons through the ruins.",
            altar_removals=["alt_nexus_001"]
        )

        # Process removal (this logic will be implemented in dm.py)
        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)

        # Verify: Only one altar remains
        assert len(shared_state.current_altars) == 1
        assert shared_state.get_altar_by_id("alt_nexus_001") is None
        assert shared_state.get_altar_by_id("alt_ritual_001") is not None

    def test_multiple_altar_removal(self):
        """Test removing multiple altars in a single story advancement."""
        shared_state = SharedState()

        altars = [
            Altar(AltarType.NEXUS_ALTAR, 5, "Temple 1", "alt_001"),
            Altar(AltarType.RITUAL_ALTAR, 6, "Temple 2", "alt_002"),
            Altar(AltarType.FREEBORN_ALTAR, 8, "Temple 3", "alt_003"),
        ]

        for altar in altars:
            shared_state.add_altar(altar)

        assert len(shared_state.current_altars) == 3

        # Remove two altars
        advancement = StoryAdvancement(
            should_advance=True,
            location="Abandoned District",
            situation="The ancient temples collapse behind you as void corruption spreads. Stone and sacred artifacts tumble into the chasm. Only silence remains in this abandoned district.",
            altar_removals=["alt_001", "alt_002"]
        )

        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)

        # Verify: Only third altar remains
        assert len(shared_state.current_altars) == 1
        assert shared_state.get_altar_by_id("alt_001") is None
        assert shared_state.get_altar_by_id("alt_002") is None
        assert shared_state.get_altar_by_id("alt_003") is not None

    def test_altar_removal_preserves_other_altars(self):
        """Test that removing altars doesn't affect other altars."""
        shared_state = SharedState()

        altar_to_remove = Altar(
            AltarType.NEXUS_ALTAR,
            quality=4,
            location="Old Site",
            altar_id="alt_remove"
        )
        altar_to_keep = Altar(
            AltarType.RITUAL_ALTAR,
            quality=9,
            location="Safe Site",
            altar_id="alt_keep"
        )

        shared_state.add_altar(altar_to_remove)
        shared_state.add_altar(altar_to_keep)

        # Remove one altar
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Area",
            situation="You depart the old site, leaving the crumbling altar behind. The safe site's ritual chamber remains intact, protected by ancient wards against void corruption.",
            altar_removals=["alt_remove"]
        )

        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)

        # Verify kept altar is unchanged
        kept_altar = shared_state.get_altar_by_id("alt_keep")
        assert kept_altar is not None
        assert kept_altar.altar_type == AltarType.RITUAL_ALTAR
        assert kept_altar.quality == 9
        assert kept_altar.location == "Safe Site"

    def test_invalid_altar_id_handled_gracefully(self):
        """Test that removing non-existent altar doesn't crash."""
        shared_state = SharedState()

        altar = Altar(
            AltarType.NEXUS_ALTAR,
            quality=5,
            location="Temple",
            altar_id="alt_valid"
        )
        shared_state.add_altar(altar)

        # Try to remove non-existent altar
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="The journey continues through desolate corridors. No sacred sites remain here, only the echoes of what once was. The path stretches onward into darkness.",
            altar_removals=["alt_nonexistent"]
        )

        # Should not raise exception
        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)  # SharedState.remove_altar handles this gracefully

        # Original altar should still exist
        assert len(shared_state.current_altars) == 1
        assert shared_state.get_altar_by_id("alt_valid") is not None

    def test_altar_removal_with_vendors_unchanged(self):
        """Test that altar removal doesn't affect vendor tracking."""
        from scripts.aeonisk.multiagent.energy_economy import Vendor

        shared_state = SharedState()

        # Add both altar and vendor
        altar = Altar(
            AltarType.NEXUS_ALTAR,
            quality=5,
            location="Temple",
            altar_id="alt_001"
        )
        vendor = Vendor(
            name="Test Vendor",
            vendor_id="vnd_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Hello",
            inventory=[]
        )

        shared_state.add_altar(altar)
        shared_state.add_vendor(vendor)

        # Remove altar via story advancement
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Location",
            situation="The ancient altar crumbles, its stones scattered by void corruption. The vendor remains, stoically offering their wares despite the destruction surrounding them.",
            altar_removals=["alt_001"],
            vendor_departures=[]  # Vendor stays
        )

        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)

        # Vendor should be unaffected
        assert len(shared_state.current_vendors) == 1
        assert shared_state.get_vendor_by_id("vnd_001") is not None

        # Altar should be removed
        assert len(shared_state.current_altars) == 0


class TestAltarRemovalConsistency:
    """Test that altar_removals matches vendor_departures pattern."""

    def test_altar_removals_same_pattern_as_vendor_departures(self):
        """Test that altar_removals field matches vendor_departures design."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="New Area",
            situation="Everything changes as the district collapses. Vendors flee with their goods, altars crumble into rubble. The evacuation is complete, leaving only ruins behind.",
            vendor_departures=["Vendor Name 1", "Vendor Name 2"],
            altar_removals=["alt_001", "alt_002"]
        )

        # Both should be List[str]
        assert isinstance(advancement.vendor_departures, list)
        assert isinstance(advancement.altar_removals, list)

        # Both should default to empty
        advancement2 = StoryAdvancement(
            should_advance=True,
            location="Another Area",
            situation="The passage opens to a pristine chamber, untouched by time or void. No vendors, no altars—just silence and the faint hum of pre-collapse machinery."
        )
        assert advancement2.vendor_departures == []
        assert advancement2.altar_removals == []

    def test_combined_vendor_and_altar_removal(self):
        """Test that vendors and altars can be removed simultaneously."""
        from scripts.aeonisk.multiagent.energy_economy import Vendor

        shared_state = SharedState()

        # Add vendor and altar
        vendor = Vendor(
            name="Departing Vendor",
            vendor_id="vnd_001",
            faction="Independent",
            vendor_type="humanoid",
            greeting="Goodbye",
            inventory=[]
        )
        altar = Altar(
            AltarType.RITUAL_ALTAR,
            quality=6,
            location="Old Temple",
            altar_id="alt_001"
        )

        shared_state.add_vendor(vendor)
        shared_state.add_altar(altar)

        # Story advancement removes both
        advancement = StoryAdvancement(
            should_advance=True,
            location="Abandoned Sector",
            situation="The district is evacuated as void corruption spreads. The vendor packs their goods and departs. The ritual altar collapses into rubble, lost to the creeping darkness.",
            vendor_departures=["Departing Vendor"],
            altar_removals=["alt_001"]
        )

        # Process both removals
        for vendor_name in advancement.vendor_departures:
            shared_state.remove_vendor(vendor_name)
        for altar_id in advancement.altar_removals:
            shared_state.remove_altar(altar_id)

        # Both should be removed
        assert len(shared_state.current_vendors) == 0
        assert len(shared_state.current_altars) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
