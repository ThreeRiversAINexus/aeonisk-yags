"""
Story Event Schemas

Structured output for story advancement, clock creation, and round synthesis.

Replaces marker parsing ([NEW_CLOCK: ...], [ADVANCE_STORY: ...], etc.) with
validated structured output.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from .shared_types import Position


class NewClock(BaseModel):
    """
    New progress clock to spawn.

    Example:
    ```python
    clock = NewClock(
        name="Passenger Safety",
        max_ticks=8,
        description="Evacuate civilians from void surge zone",
        advance_meaning="passengers evacuated",
        regress_meaning="passengers endangered"
    )
    ```
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Clock name (unique identifier)"
    )

    max_ticks: int = Field(
        ...,
        ge=4,
        le=12,
        description="Maximum ticks before clock fills (4-12 recommended)"
    )

    description: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What this clock represents"
    )

    advance_meaning: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="What it means when clock advances (e.g., 'threat escalates', 'progress made')"
    )

    regress_meaning: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="What it means when clock regresses (opposite of advance)"
    )

    current_ticks: int = Field(
        default=0,
        ge=0,
        description="Starting tick count (usually 0)"
    )

    @field_validator('current_ticks')
    @classmethod
    def validate_current_ticks(cls, v: int, info) -> int:
        """Ensure current_ticks doesn't exceed max_ticks."""
        max_ticks = info.data.get('max_ticks', 10)
        if v > max_ticks:
            raise ValueError(f"current_ticks ({v}) cannot exceed max_ticks ({max_ticks})")
        return v


class StoryAdvancement(BaseModel):
    """
    Story/scenario progression with new location and situation.

    Example:
    ```python
    advancement = StoryAdvancement(
        should_advance=True,
        location="Abandoned Transit Hub - Platform 7",
        situation="Having escaped the facility, you find a wounded courier clutching a data slate with urgent intel about the Obsidian Path",
        new_clocks=[
            NewClock(name="Courier's Life", max_ticks=6, description="Stabilize courier before they expire"),
            NewClock(name="ACG Response", max_ticks=8, description="ACG security lockdown approaching")
        ]
    )
    ```
    """

    should_advance: bool = Field(
        ...,
        description="Should the story advance to a new location/situation?"
    )

    location: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=100,
        description="New location name (if advancing)"
    )

    situation: Optional[str] = Field(
        default=None,
        min_length=20,
        max_length=500,
        description="New situation description (if advancing)"
    )

    new_clocks: List[NewClock] = Field(
        default_factory=list,
        description="New clocks to spawn with this story beat"
    )

    @field_validator('location', 'situation')
    @classmethod
    def validate_advancement_fields(cls, v: Optional[str], info) -> Optional[str]:
        """If should_advance=True, require location and situation."""
        should_advance = info.data.get('should_advance', False)
        if should_advance and not v:
            field_name = info.field_name
            raise ValueError(f"{field_name} required when should_advance=True")
        return v


class EnemySpawn(BaseModel):
    """
    New enemy to spawn during story advancement or round synthesis.

    Example:
    ```python
    spawn = EnemySpawn(
        template="Grunt",
        faction="ACG Security",
        archetype="Enforcer",
        count=2,
        spawn_reason="Reinforcements arrive via transit tunnel",
        initial_position=Position.FAR_ENEMY
    )
    ```
    """

    template: Literal["Grunt", "Elite", "Boss"] = Field(
        ...,
        description="Enemy power level template"
    )

    faction: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Faction/affiliation (e.g., 'ACG Security', 'Void Cultist')"
    )

    archetype: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Role/type (e.g., 'Enforcer', 'Scanner', 'Ritualist')"
    )

    count: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of this enemy type to spawn (1-5)"
    )

    spawn_reason: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Narrative reason for spawn (e.g., 'Alarm triggered', 'Ritual completed')"
    )

    initial_position: Position = Field(
        default=Position.FAR_ENEMY,
        description="Starting tactical position"
    )

    custom_traits: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Special traits or modifications (optional)"
    )


class RoundSynthesis(BaseModel):
    """
    DM's round summary with potential story advancement and enemy spawns.

    Example:
    ```python
    synthesis = RoundSynthesis(
        narration="The round concludes in controlled chaos. Ash's ritual barely holds...",
        story_advancement=StoryAdvancement(should_advance=False),
        enemy_spawns=[],
        clocks_filled=["Void Surge"],
        clocks_expired=[]
    )
    ```
    """

    # Narrative summary
    narration: str = Field(
        ...,
        min_length=100,
        max_length=2000,
        description="DM's cohesive narrative summarizing the round (100-2000 chars)"
    )

    # Story progression
    story_advancement: Optional[StoryAdvancement] = Field(
        default=None,
        description="Story advancement (if clocks filled/expired or scenario complete)"
    )

    # Enemy management
    enemy_spawns: List[EnemySpawn] = Field(
        default_factory=list,
        description="New enemies to spawn this round"
    )

    # Clock lifecycle
    clocks_filled: List[str] = Field(
        default_factory=list,
        description="Clock names that just filled (reached max ticks)"
    )

    clocks_expired: List[str] = Field(
        default_factory=list,
        description="Clock names that expired (not advancing, time limit reached)"
    )

    # Session end condition
    session_end: Optional[Literal["victory", "defeat", "draw"]] = Field(
        default=None,
        description="If session should end, what's the outcome?"
    )

    session_end_reason: Optional[str] = Field(
        default=None,
        description="Why session ended (if session_end is set)"
    )

    @field_validator('session_end_reason')
    @classmethod
    def validate_session_end_reason(cls, v: Optional[str], info) -> Optional[str]:
        """If session_end is set, require reason."""
        session_end = info.data.get('session_end')
        if session_end and not v:
            raise ValueError("session_end_reason required when session_end is set")
        return v


class ScenarioSetup(BaseModel):
    """
    Initial scenario setup with theme, location, situation, and starting clocks.

    Used for DM scenario generation at session start.

    Example:
    ```python
    scenario = ScenarioSetup(
        theme="Corporate espionage meets void corruption",
        location="Tempest Industries R&D Facility - Sub-Level 4",
        situation="You've infiltrated to steal prototype void scanner, but something's wrong - staff are catatonic, void readings spiking",
        starting_clocks=[
            NewClock(name="Facility Lockdown", max_ticks=10, description="Security protocol engages"),
            NewClock(name="Void Surge", max_ticks=6, description="Uncontrolled void energy cascade")
        ],
        success_conditions="Extract prototype + escape before lockdown OR neutralize void surge source",
        failure_consequences="Captured by ACG, exposed to critical void corruption, or trapped in facility"
    )
    ```
    """

    theme: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Scenario theme/hook"
    )

    location: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="Starting location"
    )

    situation: str = Field(
        ...,
        min_length=50,
        max_length=800,
        description="Opening situation (3-5 sentences)"
    )

    starting_clocks: List[NewClock] = Field(
        ...,
        min_items=1,
        max_items=4,
        description="Initial progress clocks (1-4 recommended)"
    )

    success_conditions: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="What constitutes victory?"
    )

    failure_consequences: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="What happens if they fail?"
    )

    initial_enemies: List[EnemySpawn] = Field(
        default_factory=list,
        description="Enemies present at scenario start (optional)"
    )
