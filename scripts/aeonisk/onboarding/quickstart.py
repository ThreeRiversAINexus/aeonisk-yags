"""Quickstart utilities for onboarding new Aeonisk tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class QuickstartPhase:
    """A discrete phase in the onboarding flowchart."""

    id: str
    name: str
    summary: str
    callouts: List[str]
    decision_points: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a serialisable representation of the phase."""
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "callouts": self.callouts,
            "decision_points": self.decision_points,
        }


class QuickstartGuide:
    """Produce condensed guides for character creation and ritual basics."""

    def __init__(self) -> None:
        self._phases: List[QuickstartPhase] = [
            QuickstartPhase(
                id="origin_seed",
                name="1. Wake from the Creche",
                summary="Anchor the character's pod-born obligations and the first guiding sparks.",
                callouts=[
                    "Choose creche sponsor and note mandatory Bond obligation.",
                    "Record starting Soulcredit favour owed to the institution.",
                ],
                decision_points=[
                    "Are you pod-bound or the rare Freeborn?",
                    "Which faction expects first claim on your labour?",
                ],
            ),
            QuickstartPhase(
                id="bonds",
                name="2. Map Bonds & Guiding Pressure",
                summary="Define two immediate relationships and the pressure they exert on your Guiding Principle.",
                callouts=[
                    "Assign Bond strengths; higher strength means more Soulcredit if honoured.",
                    "Draft a tentative Guiding Principle prompt that can crystallise later.",
                ],
                decision_points=[
                    "Which bond would you betray first if Void tempted you?",
                    "Who can revoke your Soulcredit access if you fail?",
                ],
            ),
            QuickstartPhase(
                id="ritual_loop",
                name="3. Ritual Loop",
                summary="Establish the Will/Bond/Void trade loop for the character's first major ritual.",
                callouts=[
                    "Choose the ritual's Guiding Principle stake and offering.",
                    "List the Bond you risk fraying and the Void spike consequence if you proceed.",
                    "Note Soulcredit payout on a success and collateral owed on a failure.",
                ],
                decision_points=[
                    "Will you trade Bond strength for certainty?",
                    "Does the ritual violate faction doctrine?",
                ],
            ),
            QuickstartPhase(
                id="void_breakpoints",
                name="4. Void Breakpoints",
                summary="Remind the table how Void escalation reshapes scenes and technology.",
                callouts=[
                    "Void 2 triggers environmental flicker; note a visible omen.",
                    "Void 3 demands a faction audit or bond intervention.",
                    "Void 4+ unlocks catastrophic options but corrodes Soulcredit access.",
                ],
                decision_points=[
                    "Do you spend Soulcredit to blunt the spike?",
                    "Who witnesses the Void flare and how do they react?",
                ],
            ),
        ]

    def to_flowchart(self) -> Dict[str, Any]:
        """Return a data structure suitable for rendering onboarding flowcharts."""
        return {
            "title": "Aeonisk Character & Ritual Quickstart",
            "phases": [phase.as_dict() for phase in self._phases],
            "legend": {
                "callout": "Soulcredit reminders or Void warnings",
                "decision_point": "Questions that force Will/Bond/Void trade-offs",
            },
        }

    def to_two_page_brief(self) -> List[Dict[str, Any]]:
        """Return a printable two-page reference summarising onboarding essentials."""
        return [
            {
                "headline": "Page 1: Character Spark",
                "bullets": [
                    "Wake-up interview: choose creche sponsor, log initial Soulcredit debt (1 favour).",
                    "Sketch Bonds with anchors (mentor, rival, communal debt) and assign strength values.",
                    "Draft a Guiding Principle seed phrase that future crises can harden.",
                ],
                "reminders": [
                    "Soulcredit starts at 0 but can drop to -2 if obligations are ignored.",
                    "Freeborn exception: gain +1 starting Bond but owe a cultural tithe.",
                ],
            },
            {
                "headline": "Page 2: Ritual & Void Loop",
                "bullets": [
                    "Ritual prep: specify offering, targeted Will attribute, and Bond you risk.",
                    "On success: earn Soulcredit equal to Bond strength; on failure: pay 1 Drip upkeep and take 1 Void spike.",
                    "Void escalation: at Void 3 trigger a faction audit scene; Void 4 unlocks catastrophic options with collateral.",
                ],
                "reminders": [
                    "Spend Soulcredit mid-scene to reroll once if the table honours a Bond sacrifice.",
                    "Track communal Void spikes on the shared state sheet so agents and players respond in kind.",
                ],
            },
        ]

    def as_dict(self) -> Dict[str, Any]:
        """Expose both the flowchart and printable brief for downstream tooling."""
        return {
            "flowchart": self.to_flowchart(),
            "two_page_brief": self.to_two_page_brief(),
        }
