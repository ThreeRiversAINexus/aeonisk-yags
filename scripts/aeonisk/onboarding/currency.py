"""Worked examples for Aeonisk's elemental currency conversions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class CurrencyConversionStep:
    """One step in a ritualised currency conversion."""

    step: str
    cost: int
    yield_amount: int
    note: str


@dataclass
class CurrencyConversionExample:
    """Structured illustration of how to convert between Aeonisk resources."""

    name: str
    input_resource: str
    output_resource: str
    steps: List[CurrencyConversionStep]

    @property
    def total_output(self) -> int:
        """Return the sum of all yields produced in the example."""
        return sum(step.yield_amount for step in self.steps)


def spark_core_to_drip_example() -> CurrencyConversionExample:
    """Provide the Spark Core -> Drip upkeep conversion called out in playtests."""

    steps = [
        CurrencyConversionStep(
            step="Crack the Core under guild supervision",
            cost=1,
            yield_amount=4,
            note="Requires the sponsoring Bond present; they witness the extraction to certify the favour repaid.",
        ),
        CurrencyConversionStep(
            step="Channel surplus energy into communal condensers",
            cost=0,
            yield_amount=3,
            note="Faction tithe: at least one communal steward must co-sign the transfer ledger.",
        ),
        CurrencyConversionStep(
            step="Render Drip ampoules for upkeep",
            cost=0,
            yield_amount=2,
            note="Personal claim: player names who receives the ampoules and how it shifts the highlighted bond.",
        ),
    ]

    return CurrencyConversionExample(
        name="Spark Core upkeep conversion",
        input_resource="Spark Core",
        output_resource="Drip",
        steps=steps,
    )
