"""
Test seed display in round status.

Verifies that seeds in EnergyPurse are shown with appropriate labels
(freshness for Raw, element for Attuned).
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse, Seed, SeedType, Element, create_raw_seed
)


class TestSeedDisplay:
    """Test seed display logic for round status."""

    def test_raw_seed_freshness_labels(self):
        """Test that Raw seeds show freshness status."""
        purse = EnergyPurse()

        # Fresh seed (>9 cycles)
        fresh_seed = Seed(SeedType.RAW, cycles_remaining=11, origin="test")
        purse.add_seed(fresh_seed)

        # Aged seed (6-9 cycles)
        aged_seed = Seed(SeedType.RAW, cycles_remaining=7, origin="test")
        purse.add_seed(aged_seed)

        # Old seed (<=5 cycles)
        old_seed = Seed(SeedType.RAW, cycles_remaining=3, origin="test")
        purse.add_seed(old_seed)

        # Simulate display logic
        seed_counts = {}
        for seed in purse.seeds:
            if seed.seed_type == SeedType.RAW:
                if seed.cycles_remaining <= 5:
                    label = "Raw (Old)"
                elif seed.cycles_remaining <= 9:
                    label = "Raw (Aged)"
                else:
                    label = "Raw (Fresh)"
            else:
                label = seed.seed_type.value

            seed_counts[label] = seed_counts.get(label, 0) + 1

        # Verify labels
        assert seed_counts["Raw (Fresh)"] == 1
        assert seed_counts["Raw (Aged)"] == 1
        assert seed_counts["Raw (Old)"] == 1

    def test_attuned_seed_element_labels(self):
        """Test that Attuned seeds show their element."""
        purse = EnergyPurse()

        # Fire attuned
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.FIRE, origin="altar"))

        # Water attuned
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.WATER, origin="altar"))

        # Spirit attuned (2 of them)
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.SPIRIT, origin="nexus"))
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.SPIRIT, origin="nexus"))

        # Simulate display logic
        seed_counts = {}
        for seed in purse.seeds:
            if seed.seed_type == SeedType.ATTUNED and seed.element:
                label = f"Attuned ({seed.element.value.title()})"
            else:
                label = seed.seed_type.value

            seed_counts[label] = seed_counts.get(label, 0) + 1

        # Verify labels
        assert seed_counts["Attuned (Fire)"] == 1
        assert seed_counts["Attuned (Water)"] == 1
        assert seed_counts["Attuned (Spirit)"] == 2

    def test_hollow_seed_display(self):
        """Test that Hollow seeds show correctly."""
        purse = EnergyPurse()

        # Add 3 Hollow seeds
        purse.add_seed(Seed(SeedType.HOLLOW, origin="tempest"))
        purse.add_seed(Seed(SeedType.HOLLOW, origin="tempest"))
        purse.add_seed(Seed(SeedType.HOLLOW, origin="tempest"))

        seed_counts = {}
        for seed in purse.seeds:
            label = seed.seed_type.value
            seed_counts[label] = seed_counts.get(label, 0) + 1

        assert seed_counts["hollow"] == 3

    def test_mixed_seed_inventory(self):
        """Test display with multiple seed types."""
        purse = EnergyPurse()

        # Mix of seeds like a real character might have
        purse.add_seed(create_raw_seed(origin="leyline", freshness="fresh"))  # Fresh Raw
        purse.add_seed(create_raw_seed(origin="leyline", freshness="aged"))   # Aged Raw
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.FIRE, origin="purchased"))
        purse.add_seed(Seed(SeedType.HOLLOW, origin="corrupted"))

        # Simulate full display logic
        seed_counts = {}
        for seed in purse.seeds:
            seed_type_name = seed.seed_type.value

            if seed.seed_type == SeedType.RAW:
                if seed.cycles_remaining <= 5:
                    seed_type_name = "Raw (Old)"
                elif seed.cycles_remaining <= 9:
                    seed_type_name = "Raw (Aged)"
                else:
                    seed_type_name = "Raw (Fresh)"
            elif seed.seed_type == SeedType.ATTUNED and seed.element:
                seed_type_name = f"Attuned ({seed.element.value.title()})"

            seed_counts[seed_type_name] = seed_counts.get(seed_type_name, 0) + 1

        # Verify mixed inventory
        assert seed_counts["Raw (Fresh)"] == 1
        assert seed_counts["Raw (Aged)"] == 1
        assert seed_counts["Attuned (Fire)"] == 1
        assert seed_counts["hollow"] == 1

    def test_empty_seed_inventory(self):
        """Test that empty inventory doesn't crash."""
        purse = EnergyPurse()

        # No seeds - should just not display anything
        assert len(purse.seeds) == 0

        seed_counts = {}
        for seed in purse.seeds:
            # This loop won't execute
            pass

        assert seed_counts == {}

    def test_seed_display_string_format(self):
        """Test the actual string format used in round status."""
        purse = EnergyPurse()

        purse.add_seed(create_raw_seed(origin="test", freshness="fresh"))
        purse.add_seed(create_raw_seed(origin="test", freshness="aged"))
        purse.add_seed(Seed(SeedType.ATTUNED, element=Element.SPIRIT, origin="nexus"))

        # Build display string
        seed_counts = {}
        for seed in purse.seeds:
            seed_type_name = seed.seed_type.value

            if seed.seed_type == SeedType.RAW:
                if seed.cycles_remaining <= 5:
                    seed_type_name = "Raw (Old)"
                elif seed.cycles_remaining <= 9:
                    seed_type_name = "Raw (Aged)"
                else:
                    seed_type_name = "Raw (Fresh)"
            elif seed.seed_type == SeedType.ATTUNED and seed.element:
                seed_type_name = f"Attuned ({seed.element.value.title()})"

            seed_counts[seed_type_name] = seed_counts.get(seed_type_name, 0) + 1

        seed_parts = [f"{name}:{count}" for name, count in seed_counts.items()]
        seed_str = " | ".join(seed_parts)

        # Verify format matches expected display
        assert "Raw (Fresh):1" in seed_str
        assert "Raw (Aged):1" in seed_str
        assert "Attuned (Spirit):1" in seed_str
        assert "|" in seed_str  # Separator present
