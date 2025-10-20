"""Guidance for triggering and resolving Guiding Principle crises."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class GuidingPrincipleCrisis:
    """Represent a pivotal moment where a character's principle is threatened."""

    trigger: str
    fallout: str
    support: str

    def as_dict(self) -> Dict[str, str]:
        """Return a dictionary representation for downstream tooling."""
        return {
            "trigger": self.trigger,
            "fallout": self.fallout,
            "support": self.support,
        }


class GuidingPrincipleCrisisLibrary:
    """Curated list of crises and cadence suggestions for GMs."""

    def __init__(self) -> None:
        self._crises: List[GuidingPrincipleCrisis] = [
            GuidingPrincipleCrisis(
                trigger="Faction tribunal questions the character's loyalty after a void-tainted contract.",
                fallout="Gain +3 Void, lose 1 Soulcredit unless the bond advocate speaks in your defence.",
                support="Offer the player a bargain: sacrifice a Bond or accept exile from the faction network.",
            ),
            GuidingPrincipleCrisis(
                trigger="A mentor demands you abandon a newfound community to pursue their agenda.",
                fallout="If refused, mark a Bond as strained and roll with disadvantage on related rituals for a scene.",
                support="Present a flashback or dreamwork vignette that clarifies what the principle truly protects.",
            ),
            GuidingPrincipleCrisis(
                trigger="Void surge exposes a contradiction between your declared principle and a desperate ally's plea.",
                fallout="Accepting the plea adds a permanent Void scar but cements a new Bond at strength 2.",
                support="Let the table describe the scar and decide which faction takes note of the compromise.",
            ),
        ]

    def recommended_cadence(self) -> Dict[str, int]:
        """Return cadence guidance for checking whether principles should shift."""
        return {
            "check_every_sessions": 2,
            "void_threshold_trigger": 3,
            "bond_breach_trigger": 2,
        }

    def sample_crises(self) -> List[Dict[str, str]]:
        """Return representative crises for pacing pivotal moments."""
        return [crisis.as_dict() for crisis in self._crises]
