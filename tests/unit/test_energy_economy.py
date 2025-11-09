"""
Unit tests for Energy Economy System.

Tests verify:
- Currency operations (add, spend, transfer, convert)
- Seed lifecycle (Raw → Attuned, Raw → Hollow)
- Inventory tracking and persistence
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyInventory,
    Seed,
    SeedType,
    Element,
    create_raw_seed
)


class TestCurrencyOperations:
    """Test currency add/spend/transfer mechanics."""

    def test_add_currency(self):
        """Test adding currency to inventory."""
        inv = EnergyInventory(breath=0, drip=0, grain=0, spark=0)

        inv.add_currency("breath", 10)
        assert inv.breath == 10

        inv.add_currency("drip", 5)
        assert inv.drip == 5

        inv.add_currency("grain", 2)
        assert inv.grain == 2

        inv.add_currency("spark", 1)
        assert inv.spark == 1

    def test_spend_currency_success(self):
        """Test spending currency with sufficient funds."""
        inv = EnergyInventory(breath=10, drip=5, grain=2, spark=1)

        assert inv.spend_currency("breath", 5) is True
        assert inv.breath == 5

        assert inv.spend_currency("drip", 3) is True
        assert inv.drip == 2

        assert inv.spend_currency("grain", 1) is True
        assert inv.grain == 1

        assert inv.spend_currency("spark", 1) is True
        assert inv.spark == 0

    def test_spend_currency_insufficient_funds(self):
        """Test spending currency with insufficient funds."""
        inv = EnergyInventory(breath=5, drip=2, grain=1, spark=0)

        assert inv.spend_currency("breath", 10) is False
        assert inv.breath == 5  # Unchanged

        assert inv.spend_currency("drip", 5) is False
        assert inv.drip == 2  # Unchanged

        assert inv.spend_currency("spark", 1) is False
        assert inv.spark == 0  # Unchanged

    def test_spend_currency_exact_amount(self):
        """Test spending exact amount of currency."""
        inv = EnergyInventory(breath=10, drip=5, grain=2, spark=1)

        assert inv.spend_currency("breath", 10) is True
        assert inv.breath == 0

        assert inv.spend_currency("drip", 5) is True
        assert inv.drip == 0

    def test_transfer_currency_success(self):
        """Test transferring currency between inventories."""
        inv1 = EnergyInventory(breath=10, drip=5, grain=2, spark=1)
        inv2 = EnergyInventory(breath=0, drip=0, grain=0, spark=0)

        assert inv1.transfer_currency_to(inv2, "breath", 5) is True
        assert inv1.breath == 5
        assert inv2.breath == 5

        assert inv1.transfer_currency_to(inv2, "spark", 1) is True
        assert inv1.spark == 0
        assert inv2.spark == 1

    def test_transfer_currency_insufficient_funds(self):
        """Test transferring currency with insufficient funds."""
        inv1 = EnergyInventory(breath=5, drip=2, grain=1, spark=0)
        inv2 = EnergyInventory(breath=0, drip=0, grain=0, spark=0)

        assert inv1.transfer_currency_to(inv2, "breath", 10) is False
        assert inv1.breath == 5  # Unchanged
        assert inv2.breath == 0  # Unchanged

    def test_transfer_currency_all_types(self):
        """Test transferring all currency types."""
        inv1 = EnergyInventory(breath=10, drip=10, grain=10, spark=10)
        inv2 = EnergyInventory(breath=0, drip=0, grain=0, spark=0)

        inv1.transfer_currency_to(inv2, "breath", 3)
        inv1.transfer_currency_to(inv2, "drip", 2)
        inv1.transfer_currency_to(inv2, "grain", 1)
        inv1.transfer_currency_to(inv2, "spark", 1)

        assert inv1.breath == 7
        assert inv1.drip == 8
        assert inv1.grain == 9
        assert inv1.spark == 9

        assert inv2.breath == 3
        assert inv2.drip == 2
        assert inv2.grain == 1
        assert inv2.spark == 1


class TestCurrencyConversions:
    """Test currency conversion mechanics."""

    def test_convert_spark_to_drip(self):
        """Test converting Spark to Drip (1 Spark = 3 Drip default)."""
        inv = EnergyInventory(spark=2, drip=0)

        assert inv.convert_currency("spark", "drip", 1) is True
        assert inv.spark == 1
        assert inv.drip == 3  # 1 Spark → 3 Drip

    def test_convert_drip_to_spark(self):
        """Test converting Drip to Spark (3 Drip = 1 Spark default)."""
        inv = EnergyInventory(spark=0, drip=6)

        assert inv.convert_currency("drip", "spark", 3) is True
        assert inv.drip == 3
        assert inv.spark == 1  # 3 Drip → 1 Spark

    def test_convert_drip_to_breath(self):
        """Test converting Drip to Breath (1 Drip = 4 Breath default)."""
        inv = EnergyInventory(drip=2, breath=0)

        assert inv.convert_currency("drip", "breath", 1) is True
        assert inv.drip == 1
        assert inv.breath == 4  # 1 Drip → 4 Breath

    def test_convert_breath_to_drip(self):
        """Test converting Breath to Drip (4 Breath = 1 Drip default)."""
        inv = EnergyInventory(breath=12, drip=0)

        assert inv.convert_currency("breath", "drip", 8) is True
        assert inv.breath == 4
        assert inv.drip == 2  # 8 Breath → 2 Drip

    def test_convert_insufficient_currency(self):
        """Test conversion with insufficient source currency."""
        inv = EnergyInventory(spark=0, drip=5)

        assert inv.convert_currency("spark", "drip", 1) is False
        assert inv.spark == 0
        assert inv.drip == 5  # Unchanged

    def test_convert_too_small_amount(self):
        """Test conversion that would result in 0 target currency."""
        inv = EnergyInventory(breath=2, drip=10)

        # 2 Breath < 4 (breaths_per_drip), so conversion fails
        assert inv.convert_currency("breath", "drip", 2) is False
        assert inv.breath == 2  # Refunded
        assert inv.drip == 10  # Unchanged

    def test_convert_hollow_seed_to_drip(self):
        """Test converting Hollow Seed to Drip (black market)."""
        inv = EnergyInventory(drip=0)
        hollow_seed = Seed(seed_type=SeedType.HOLLOW, origin="test")
        inv.add_seed(hollow_seed)

        assert inv.convert_currency("hollow", "drip", 1) is True
        assert inv.drip == 5  # 1 Hollow → 5 Drip
        assert inv.count_seeds(SeedType.HOLLOW) == 0  # Consumed

    def test_convert_hollow_seed_no_seed_available(self):
        """Test converting Hollow Seed when none in inventory."""
        inv = EnergyInventory(drip=0)

        assert inv.convert_currency("hollow", "drip", 1) is False
        assert inv.drip == 0  # Unchanged


class TestSeedLifecycle:
    """Test seed creation, degradation, and transformation."""

    def test_create_raw_seed_fresh(self):
        """Test creating fresh Raw Seed (10-14 cycles)."""
        seed = create_raw_seed("test_origin", freshness="fresh")

        assert seed.seed_type == SeedType.RAW
        assert 10 <= seed.cycles_remaining <= 14
        assert seed.origin == "test_origin"

    def test_create_raw_seed_aged(self):
        """Test creating aged Raw Seed (6-9 cycles)."""
        seed = create_raw_seed("test_origin", freshness="aged")

        assert seed.seed_type == SeedType.RAW
        assert 6 <= seed.cycles_remaining <= 9

    def test_create_raw_seed_old(self):
        """Test creating old Raw Seed (3-5 cycles)."""
        seed = create_raw_seed("test_origin", freshness="old")

        assert seed.seed_type == SeedType.RAW
        assert 3 <= seed.cycles_remaining <= 5

    def test_seed_degrade_single_cycle(self):
        """Test degrading a Raw Seed by 1 cycle."""
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=5)

        became_hollow = seed.degrade(1)

        assert became_hollow is False
        assert seed.cycles_remaining == 4
        assert seed.seed_type == SeedType.RAW

    def test_seed_degrade_to_hollow(self):
        """Test Raw Seed degrading completely to Hollow."""
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=2)

        # First degradation
        assert seed.degrade(1) is False
        assert seed.cycles_remaining == 1

        # Second degradation → Hollow
        assert seed.degrade(1) is True
        assert seed.seed_type == SeedType.HOLLOW
        assert seed.cycles_remaining == 0

    def test_seed_degrade_multi_cycle(self):
        """Test degrading a Raw Seed by multiple cycles at once."""
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=5)

        became_hollow = seed.degrade(3)

        assert became_hollow is False
        assert seed.cycles_remaining == 2
        assert seed.seed_type == SeedType.RAW

    def test_attuned_seed_no_degradation(self):
        """Test that Attuned Seeds don't degrade."""
        seed = Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE)

        became_hollow = seed.degrade(5)

        assert became_hollow is False
        assert seed.seed_type == SeedType.ATTUNED

    def test_hollow_seed_no_degradation(self):
        """Test that Hollow Seeds don't degrade further."""
        seed = Seed(seed_type=SeedType.HOLLOW)

        became_hollow = seed.degrade(5)

        assert became_hollow is False
        assert seed.seed_type == SeedType.HOLLOW


class TestInventorySeedOperations:
    """Test seed inventory operations."""

    def test_add_seed(self):
        """Test adding seeds to inventory."""
        inv = EnergyInventory()
        raw_seed = Seed(seed_type=SeedType.RAW, cycles_remaining=10)
        attuned_seed = Seed(seed_type=SeedType.ATTUNED, element=Element.WATER)

        inv.add_seed(raw_seed)
        inv.add_seed(attuned_seed)

        assert len(inv.seeds) == 2
        assert inv.count_seeds(SeedType.RAW) == 1
        assert inv.count_seeds(SeedType.ATTUNED) == 1

    def test_consume_seed_raw(self):
        """Test consuming a Raw Seed from inventory."""
        inv = EnergyInventory()
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=10, origin="test")
        inv.add_seed(seed)

        consumed = inv.consume_seed(SeedType.RAW)

        assert consumed is not None
        assert consumed.seed_type == SeedType.RAW
        assert inv.count_seeds(SeedType.RAW) == 0

    def test_consume_seed_attuned_specific_element(self):
        """Test consuming Attuned Seed with specific element."""
        inv = EnergyInventory()
        fire_seed = Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE)
        water_seed = Seed(seed_type=SeedType.ATTUNED, element=Element.WATER)
        inv.add_seed(fire_seed)
        inv.add_seed(water_seed)

        consumed = inv.consume_seed(SeedType.ATTUNED, element=Element.WATER)

        assert consumed is not None
        assert consumed.element == Element.WATER
        assert inv.count_seeds(SeedType.ATTUNED) == 1
        assert inv.count_seeds(SeedType.ATTUNED, element=Element.FIRE) == 1

    def test_consume_seed_not_available(self):
        """Test consuming seed when none available."""
        inv = EnergyInventory()

        consumed = inv.consume_seed(SeedType.HOLLOW)

        assert consumed is None

    def test_count_seeds_by_type(self):
        """Test counting seeds by type."""
        inv = EnergyInventory()
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=10))
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=8))
        inv.add_seed(Seed(seed_type=SeedType.HOLLOW))
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE))

        assert inv.count_seeds(SeedType.RAW) == 2
        assert inv.count_seeds(SeedType.HOLLOW) == 1
        assert inv.count_seeds(SeedType.ATTUNED) == 1

    def test_count_seeds_by_element(self):
        """Test counting Attuned Seeds by element."""
        inv = EnergyInventory()
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE))
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE))
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.WATER))

        assert inv.count_seeds(SeedType.ATTUNED, element=Element.FIRE) == 2
        assert inv.count_seeds(SeedType.ATTUNED, element=Element.WATER) == 1
        assert inv.count_seeds(SeedType.ATTUNED, element=Element.VOID) == 0

    def test_degrade_all_raw_seeds(self):
        """Test degrading all Raw Seeds in inventory."""
        inv = EnergyInventory()
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=5))
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=2))
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE))

        inv.degrade_raw_seeds(1)

        # First seed: 5 → 4
        # Second seed: 2 → 1
        # Attuned: unchanged
        assert inv.seeds[0].cycles_remaining == 4
        assert inv.seeds[1].cycles_remaining == 1
        assert inv.seeds[2].seed_type == SeedType.ATTUNED

    def test_degrade_raw_seeds_to_hollow(self):
        """Test Raw Seeds degrading to Hollow in inventory."""
        inv = EnergyInventory()
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=1))

        inv.degrade_raw_seeds(1)

        # Should now be Hollow
        assert inv.seeds[0].seed_type == SeedType.HOLLOW
        assert inv.count_seeds(SeedType.HOLLOW) == 1
        assert inv.count_seeds(SeedType.RAW) == 0


class TestInventorySerialization:
    """Test inventory serialization to dictionary."""

    def test_inventory_as_dict(self):
        """Test serializing full inventory to dict."""
        inv = EnergyInventory(breath=10, drip=5, grain=2, spark=1)
        inv.add_seed(Seed(seed_type=SeedType.RAW, cycles_remaining=8, origin="loot"))
        inv.add_seed(Seed(seed_type=SeedType.ATTUNED, element=Element.FIRE, origin="vendor"))

        data = inv.as_dict()

        assert data['currencies']['breath'] == 10
        assert data['currencies']['drip'] == 5
        assert data['currencies']['grain'] == 2
        assert data['currencies']['spark'] == 1
        assert len(data['seeds']) == 2

        # Check seed data
        assert data['seeds'][0]['type'] == 'raw'
        assert data['seeds'][0]['cycles_remaining'] == 8
        assert data['seeds'][1]['type'] == 'attuned'
        assert data['seeds'][1]['element'] == 'fire'

    def test_seed_as_dict(self):
        """Test serializing individual Seed to dict."""
        raw_seed = Seed(seed_type=SeedType.RAW, cycles_remaining=10, origin="test")
        data = raw_seed.as_dict()

        assert data['type'] == 'raw'
        assert data['cycles_remaining'] == 10
        assert data['origin'] == 'test'
        assert data['element'] is None

        attuned_seed = Seed(seed_type=SeedType.ATTUNED, element=Element.VOID, origin="altar")
        data = attuned_seed.as_dict()

        assert data['type'] == 'attuned'
        assert data['element'] == 'void'
        assert data['cycles_remaining'] is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_spend_zero_currency(self):
        """Test spending 0 currency (should succeed trivially)."""
        inv = EnergyInventory(breath=10)

        assert inv.spend_currency("breath", 0) is True
        assert inv.breath == 10

    def test_transfer_zero_currency(self):
        """Test transferring 0 currency (should succeed trivially)."""
        inv1 = EnergyInventory(breath=10)
        inv2 = EnergyInventory(breath=5)

        assert inv1.transfer_currency_to(inv2, "breath", 0) is True
        assert inv1.breath == 10
        assert inv2.breath == 5

    def test_multiple_currency_types_independence(self):
        """Test that currency types are independent."""
        inv = EnergyInventory(breath=10, drip=5, grain=2, spark=1)

        inv.spend_currency("breath", 10)
        assert inv.breath == 0
        assert inv.drip == 5  # Unaffected
        assert inv.grain == 2  # Unaffected
        assert inv.spark == 1  # Unaffected

    def test_seed_cycles_exactly_zero_becomes_hollow(self):
        """Test seed becoming Hollow when cycles reach exactly 0."""
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=1)

        assert seed.degrade(1) is True
        assert seed.seed_type == SeedType.HOLLOW
        assert seed.cycles_remaining == 0

    def test_seed_cycles_negative_becomes_hollow(self):
        """Test seed becoming Hollow when cycles go below 0."""
        seed = Seed(seed_type=SeedType.RAW, cycles_remaining=2)

        assert seed.degrade(5) is True
        assert seed.seed_type == SeedType.HOLLOW
        assert seed.cycles_remaining < 0
