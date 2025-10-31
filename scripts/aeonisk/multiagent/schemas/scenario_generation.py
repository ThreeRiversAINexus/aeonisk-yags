"""
Pydantic schema for DM scenario generation.

This replaces text parsing with structured output for scenario creation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class ClockSemantics(BaseModel):
    """
    Semantic guidance for how a clock behaves.

    Clarifies what advancing/regressing means and what happens when filled.
    """
    advance_means: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What advancing this clock means (e.g., 'Hunters get closer to finding the team', 'More evidence is collected')"
    )

    regress_means: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What regressing this clock means (e.g., 'Team evades pursuit', 'Evidence is destroyed')"
    )

    filled_consequence: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="What happens when clock fills. MUST include a marker: [SPAWN_ENEMY: ...] for mechanical, [ADVANCE_STORY: ...] or [NEW_CLOCK: ...] for narrative. Example: 'Hunter team arrives [SPAWN_ENEMY: Corporate Hunters | elite | 2 | Far-Enemy | tactical_ranged]'"
    )


class ScenarioClock(BaseModel):
    """
    A scene clock that tracks progress or danger.

    Examples:
    - MECHANICAL: Security Alert | 6 | Corporate hunters closing in | [SPAWN_ENEMY when filled]
    - NARRATIVE: Evidence Collection | 8 | Gathering proof | [ADVANCE_STORY when filled]
    """
    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Clock name (clear, specific: 'Security Alert', 'Evidence Collection', not generic 'Progress')"
    )

    max_ticks: int = Field(
        ...,
        ge=3,
        le=12,
        description="Maximum ticks before clock fills (typically 4-8)"
    )

    description: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What this clock represents (e.g., 'Corporate hunters closing in on team location')"
    )

    semantics: ClockSemantics = Field(
        ...,
        description="How this clock advances/regresses and what happens when filled"
    )


class ScenarioGeneration(BaseModel):
    """
    Complete scenario generation for Aeonisk YAGS.

    The DM generates scenarios using this structured format instead of text parsing.

    Example:
    ```python
    ScenarioGeneration(
        theme="Media Hijacking",
        location="The Resonance Spire – Nimbus Cloudbreak District",
        situation="The Resonance Spire's transmission array crackles with stolen signals - House of Vox feeds hijacked mid-broadcast, replaced with manifesto scrolls denouncing the Nexus. Below, Pantheon Security cordons spiral upward through the cloudbreak, boots hammering on glass walkways. The hijackers are still inside, somewhere in the 200 floors of offices and studios. You have maybe ten minutes before the building locks down completely.",
        clocks=[
            ScenarioClock(
                name="Security Response",
                max_ticks=6,
                description="Pantheon Security investigating the hijack",
                semantics=ClockSemantics(
                    advance_means="Security teams get closer to finding you",
                    regress_means="You evade or mislead investigators",
                    filled_consequence="Security team arrives [SPAWN_ENEMY: Pantheon Security | elite | 2 | Far-Enemy | tactical_ranged]"
                )
            ),
            ScenarioClock(
                name="Trace the Signal",
                max_ticks=8,
                description="Tracking the hijackers' origin point",
                semantics=ClockSemantics(
                    advance_means="You narrow down the source location",
                    regress_means="Trail goes cold or gets corrupted",
                    filled_consequence="Source found! [ADVANCE_STORY: Underground Network Hub | You've traced the signal to a hidden data nexus]"
                )
            )
        ]
    )
    ```
    """

    theme: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Scenario type (2-4 words): 'Media Hijacking', 'Void Outbreak', 'Corporate Heist', 'Tribunal Trial', etc."
    )

    location: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Specific canonical Aeonisk location (use lore-accurate names from the setting)"
    )

    situation: str = Field(
        ...,
        min_length=100,
        max_length=800,
        description="Vivid, atmospheric opening narration (3-6 sentences). Paint the scene with sensory details, tension, and immediate hooks. Show don't tell. Include environmental details, NPCs present, immediate danger/opportunity. Example: 'The Resonance Spire's transmission array crackles with stolen signals - House of Vox feeds hijacked mid-broadcast, replaced with manifesto scrolls denouncing the Nexus. Below, Pantheon Security cordons spiral upward through the cloudbreak, boots hammering on glass walkways. The hijackers are still inside, somewhere in the 200 floors of offices and studios. You have maybe ten minutes before the building locks down completely.'"
    )

    clocks: List[ScenarioClock] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="2-5 scene clocks with clear semantics. Mix danger clocks (spawn enemies when filled) with progress clocks (advance story when filled)."
    )
