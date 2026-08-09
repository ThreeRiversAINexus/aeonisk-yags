"""Pin EnergyPurse conversion to the v1.3.0 currency ladder.

Canon (Economy & Money-Making Guide §0, YAGS Module, Gear & Tech, Culinary):

    1 Drip  = 20 Breath
    1 Grain = 20 Drip  =   400 Breath
    1 Spark = 20 Grain = 400 Drip = 8 000 Breath

The engine previously carried the pre-1.3.0 rates (3 Drip/Spark, 2 Grain/Spark,
4 Breath/Drip), which both destroyed value on the way up (1 Spark -> 3 Drip) and
minted it on the way down (2 Grain -> 1 Spark, a ~10x money printer on a
starting purse). Prices and starting wealth were always denominated against the
20x ladder, so only the conversion table was wrong.
"""

import pytest

from scripts.aeonisk.multiagent.energy_economy import EnergyPurse


def make_purse(**kwargs) -> EnergyPurse:
    """An empty purse, overridden with the named currencies."""
    balances = {"breath": 0, "drip": 0, "grain": 0, "spark": 0}
    balances.update(kwargs)
    return EnergyPurse(**balances)


def test_ladder_constants_are_canonical():
    purse = EnergyPurse()
    assert purse.breaths_per_drip == 20
    assert purse.drips_per_grain == 20
    assert purse.grains_per_spark == 20
    assert purse.drips_per_spark == 400


@pytest.mark.parametrize(
    "from_type,to_type,amount,expected_field,expected_value",
    [
        ("drip", "breath", 1, "breath", 20),
        ("breath", "drip", 20, "drip", 1),
        ("grain", "drip", 1, "drip", 20),
        ("drip", "grain", 20, "grain", 1),
        ("spark", "grain", 1, "grain", 20),
        ("grain", "spark", 20, "spark", 1),
        ("spark", "drip", 1, "drip", 400),
        ("drip", "spark", 400, "spark", 1),
        ("spark", "breath", 1, "breath", 8000),
        ("breath", "spark", 8000, "spark", 1),
        ("grain", "breath", 1, "breath", 400),
        ("breath", "grain", 400, "grain", 1),
    ],
)
def test_conversion_matches_ladder(from_type, to_type, amount, expected_field, expected_value):
    purse = make_purse(**{from_type: amount})
    assert purse.convert_currency(from_type, to_type, amount) is True
    assert getattr(purse, expected_field) == expected_value
    assert getattr(purse, from_type) == 0


def test_round_trip_does_not_mint_value():
    """Converting up then back down must never exceed the starting amount."""
    purse = make_purse(spark=1)
    assert purse.convert_currency("spark", "drip", 1) is True
    assert purse.convert_currency("drip", "spark", purse.drip) is True
    assert purse.spark == 1
    assert purse.drip == 0


def test_grain_to_spark_is_not_a_money_printer():
    """The old table let 2 Grain become 1 Spark (worth 20 Grain)."""
    purse = make_purse(grain=2)
    assert purse.convert_currency("grain", "spark", 2) is False, (
        "2 Grain is below the 20 Grain needed for a Spark and must not convert"
    )
    assert purse.grain == 2, "failed conversion must refund"
    assert purse.spark == 0
