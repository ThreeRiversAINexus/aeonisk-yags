"""
Story Event Schemas

Structured output for story advancement, clock creation, and round synthesis.

Replaces marker parsing ([NEW_CLOCK: ...], [ADVANCE_STORY: ...], etc.) with
validated structured output.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from enum import Enum
from .shared_types import Position


class EnemyResolution(str, Enum):
    """
    How an enemy was removed from combat.

    Used in EnemyRemoval to track non-lethal and narrative enemy exits.
    """
    KILLED = "killed"                    # Reduced to 0 HP in combat
    NEUTRALIZED = "neutralized"          # Arrested, captured, restrained
    FLED = "fled"                        # Scared off, retreated, escaped
    CONVINCED = "convinced"              # Talked down, persuaded, negotiated
    STORY_ADVANCED = "story_advanced"    # Scene changed, no longer present
    SUBDUED = "subdued"                  # Knocked unconscious, incapacitated


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
        regress_meaning="passengers endangered",
        filled_consequence="All passengers safe, transport arrives"
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
        ge=1,
        le=12,
        description="Maximum ticks before clock fills (1-12, 4-8 recommended)"
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

    filled_consequence: str = Field(
        default="",
        min_length=0,
        max_length=300,
        description="What happens when clock fills (e.g., 'Enemy reinforcements arrive', 'Evidence complete, advance to confrontation')"
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


class ScenePivot(BaseModel):
    """
    Scene transition within the same story chapter (lighter than StoryAdvancement).

    Use for:
    - Moving to adjacent room/area within same location
    - Tactical repositioning (hallway → control room)
    - Minor environmental shifts (power goes out, doors open)

    DO NOT use for:
    - Major story beats (use StoryAdvancement instead)
    - Completely different locations (facility → transit hub = StoryAdvancement)

    Example:
    ```python
    pivot = ScenePivot(
        should_pivot=True,
        new_room="Security Control Room",
        situation_change="Alarms blaring, blast doors sealing the exits",
        clear_specific_clocks=["Breach Containment"],  # Optional selective clock clearing
        new_clocks=[
            NewClock(name="Override Lockdown", max_ticks=6, description="Hack security terminal")
        ]
    )
    ```
    """

    should_pivot: bool = Field(
        ...,
        description="Should the scene pivot to a new room/area?"
    )

    new_room: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=100,
        description="New room/area name (e.g., 'Control Room', 'Upper Catwalk')"
    )

    situation_change: Optional[str] = Field(
        default=None,
        min_length=20,
        max_length=500,
        description="How the situation has changed (tactical shift, environment change)"
    )

    clear_specific_clocks: List[str] = Field(
        default_factory=list,
        description="Specific clock names to clear (selective). Empty = keep all clocks."
    )

    new_clocks: List[NewClock] = Field(
        default_factory=list,
        description="New clocks for this scene"
    )

    @field_validator('new_room', 'situation_change')
    @classmethod
    def validate_pivot_fields(cls, v: Optional[str], info) -> Optional[str]:
        """If should_pivot=True, require new_room and situation_change."""
        should_pivot = info.data.get('should_pivot', False)
        if should_pivot and not v:
            field_name = info.field_name
            raise ValueError(f"{field_name} required when should_pivot=True")
        return v


class StoryAdvancement(BaseModel):
    """
    Major story/scenario progression with new location and situation (heavier than ScenePivot).

    Use for:
    - Major chapter transitions (facility escape → transit hub pursuit)
    - Complete location changes (underground → rooftop)
    - Resolution of major story beats

    Example:
    ```python
    advancement = StoryAdvancement(
        should_advance=True,
        location="Abandoned Transit Hub - Platform 7",
        situation="Having escaped the facility, you find a wounded courier clutching a data slate with urgent intel about the Obsidian Path",
        new_void_level=3,  # Optional: reduce void from 8→3 after purification
        clear_all_enemies=True,
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

    new_void_level: Optional[int] = Field(
        default=None,
        ge=0,
        le=10,
        description="New environmental void level (0-10), if changed. Leave None to keep current void_level unchanged."
    )

    clear_all_enemies: bool = Field(
        default=True,
        description="Remove all active enemies when story advances (default: true). Set to false only if enemies follow to new scene."
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
    DM's round summary with potential scene pivots, story advancement, and enemy spawns.

    Use scene_pivot for minor transitions (adjacent rooms, tactical repositioning).
    Use story_advancement for major chapter changes (complete location changes).
    Cannot use both in the same round.

    Example (Scene Pivot):
    ```python
    synthesis = RoundSynthesis(
        narration="As the blast doors seal, you rush into the control room...",
        scene_pivot=ScenePivot(
            should_pivot=True,
            new_room="Security Control Room",
            situation_change="Emergency lockdown engaged, blast doors sealing all exits",
            clear_specific_clocks=["Breach Containment"],
            new_clocks=[NewClock(name="Override Lockdown", max_ticks=6, description="Hack security terminal")]
        ),
        enemy_spawns=[],
        enemy_conversions=[],
        clocks_filled=[],
        clocks_expired=[]
    )
    ```

    Example (Story Advancement with Enemy Surrender):
    ```python
    synthesis = RoundSynthesis(
        narration="The round concludes in controlled chaos. Ash's ritual barely holds...",
        story_advancement=StoryAdvancement(should_advance=False),
        enemy_spawns=[],
        enemy_conversions=[
            EnemyConversion(
                enemy_id="enemy_guard_1",
                resolution=EnemyResolution.FLED,
                reason="Intimidated by overwhelming force, fled through maintenance corridor"
            ),
            EnemyConversion(
                enemy_id="enemy_raider_2",
                resolution=EnemyResolution.CONVINCED,
                reason="Negotiated surrender after diplomacy",
                resulting_entity_type="prisoner",
                resulting_disposition="prisoner"
            )
        ],
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
    scene_pivot: Optional[ScenePivot] = Field(
        default=None,
        description="Scene pivot (minor room/area transition within same chapter). Use for tactical repositioning, adjacent rooms, environmental shifts. Lighter than story_advancement."
    )

    story_advancement: Optional[StoryAdvancement] = Field(
        default=None,
        description="Story advancement (major chapter transition with new location). Use for major story beats, complete location changes. Heavier than scene_pivot."
    )

    # Enemy management
    enemy_spawns: List[EnemySpawn] = Field(
        default_factory=list,
        description="New enemies to spawn this round (use empty list [] if none, NOT null)"
    )

    enemy_conversions: List['EnemyConversion'] = Field(
        default_factory=list,
        description="""Enemies removed/converted this round - use empty list [] if none, NOT null.

**Unified field replacing enemy_removals + deescalations.**

⚠️ CRITICAL: SURRENDERS = enemy_conversions with resolution=CONVINCED, NOT CONDITIONS! ⚠️

When enemies surrender/flee/are arrested:
✅ CORRECT: enemy_conversions=[EnemyConversion(enemy_id="enemy_raider_1", resolution=CONVINCED, reason="Negotiated surrender", resulting_entity_type="prisoner", resulting_disposition="prisoner")]
❌ WRONG: Apply "Surrendered" condition to enemy (conditions are for debuffs like Stunned/Prone, NOT removal from combat!)

WHY: Conditions don't stop enemy agents from acting. Enemy agents check their state and continue attacking despite "Surrendered" conditions. Using enemy_conversions with CONVINCED automatically triggers de-escalation → converts to NPC → removes from combat.

Examples:
- Enemy flees: EnemyConversion(enemy_id="enemy_grunt_1", resolution=FLED, reason="Intimidated, fled through corridor")
- Enemy surrenders: EnemyConversion(enemy_id="enemy_raider_2", resolution=CONVINCED, reason="Negotiated surrender", resulting_entity_type="prisoner", resulting_disposition="prisoner")"""
    )

    # NPC management
    npc_spawns: List['NPCSpawn'] = Field(
        default_factory=list,
        description="New NPCs spawned this round (guides, civilians, allies) - use empty list [] if none, NOT null"
    )

    escalations: List['Escalation'] = Field(
        default_factory=list,
        description="NPCs converted to enemies this round (attacked, provoked, hostile factions) - use empty list [] if none, NOT null"
    )

    # Clock lifecycle
    clocks_filled: List[str] = Field(
        default_factory=list,
        description="Clock names that just filled (reached max ticks) - use empty list [] if none, NOT null"
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

    @field_validator('story_advancement')
    @classmethod
    def validate_story_progression_mutual_exclusion(cls, v: Optional[StoryAdvancement], info) -> Optional[StoryAdvancement]:
        """Ensure only one of scene_pivot or story_advancement is used."""
        scene_pivot = info.data.get('scene_pivot')
        if v and scene_pivot and (v.should_advance and scene_pivot.should_pivot):
            raise ValueError("Cannot use both scene_pivot and story_advancement in the same round. Choose one: scene_pivot for minor transitions, story_advancement for major chapter changes.")
        return v

    @field_validator('enemy_spawns', 'enemy_conversions', 'npc_spawns', 'escalations', 'clocks_filled', 'clocks_expired', mode='before')
    @classmethod
    def convert_none_to_empty_list(cls, v):
        """Convert None to empty list for all list fields. LLMs sometimes return null instead of []."""
        if v is None:
            return []
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
        max_length=200,
        description="Starting location"
    )

    situation: str = Field(
        ...,
        min_length=50,
        max_length=1200,
        description="Opening situation (3-5 sentences)"
    )

    void_level: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Environmental void corruption level (0-10, default 3)"
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


# NPC and De-escalation Schemas (for NPC system)

class NPCSpawn(BaseModel):
    """
    Spawn an NPC into the scene.

    Use when:
    - Introducing non-combatant characters
    - Enemy surrenders/negotiates (DM marks conversion)
    - Scene requires dialogue NPCs
    - Quest-givers, guides, civilians appear

    Example:
    ```python
    spawn = NPCSpawn(
        name="Freeborn Navigator",
        faction="Freeborn",
        entity_type="neutral",
        threat_level="non_combatant",
        disposition="neutral",
        description="Weathered woman with neural optics and void-stained fingers",
        health=20,
        soak=2,
        skills={"perception": 5, "astral_arts": 3}
    )
    ```
    """
    name: str = Field(..., min_length=3, max_length=50)
    faction: str = Field(..., description="NPC's faction/allegiance (Freeborn, ACG, Civilian, etc.)")
    entity_type: Literal["neutral", "ally", "prisoner"] = Field(
        ...,
        description="NPC's relation to players: neutral (non-aligned), ally (friendly), prisoner (captured)"
    )
    threat_level: Literal["non_combatant", "potential_threat", "armed_neutral"] = Field(
        "non_combatant",
        description="Determines enemy targeting: non_combatant (ignored by most), potential_threat (professionals engage), armed_neutral (treated as threat)"
    )
    disposition: Literal["friendly", "neutral", "wary", "prisoner"] = Field(
        ...,
        description="NPC's attitude: friendly (helpful), neutral (indifferent), wary (suspicious), prisoner (captured/restrained)"
    )
    description: str = Field(..., min_length=20, max_length=300)
    health: int = Field(..., ge=1, le=100)
    soak: int = Field(..., ge=0, le=20)
    skills: dict[str, int] = Field(
        default_factory=dict,
        description="Key skills (for cooperative checks, e.g., {'perception': 5, 'combat': 3})"
    )

    # Optional: tactical state (defaults to Near-Enemy if omitted)
    position: Optional[str] = Field(
        None,
        description="Tactical position (e.g., 'Near-Enemy', 'Far-PC', 'Engaged'). Defaults to 'Near-Enemy' if not specified."
    )

    # Optional: conversion tracking
    converted_from_enemy_id: Optional[str] = Field(
        None,
        description="If NPC was converted from enemy, track original agent_id"
    )


class EnemyConversion(BaseModel):
    """
    Enemy removed from combat or converted to NPC.

    **Merges enemy_removals + deescalations into single unified field.**

    Use when:
    - Enemy flees/escapes scene (resolution=FLED)
    - Enemy surrenders and becomes prisoner (resolution=CONVINCED/NEUTRALIZED, stays as NPC)
    - Scene changes and enemies no longer present (resolution=STORY_ADVANCED)

    Examples:
    ```python
    # Enemy flees (leaves scene entirely)
    EnemyConversion(
        enemy_id="enemy_raider_1",
        resolution=EnemyResolution.FLED,
        reason="Intimidated by overwhelming force, fled through maintenance corridor"
    )

    # Enemy surrenders (stays as NPC prisoner)
    EnemyConversion(
        enemy_id="enemy_raider_2",
        resolution=EnemyResolution.CONVINCED,
        reason="Negotiated surrender after Wei Lin's diplomacy",
        resulting_entity_type="prisoner",
        resulting_disposition="prisoner"
    )
    ```
    """
    enemy_id: str = Field(
        ...,
        description="Enemy agent_id (e.g., 'enemy_grunt_abc123') or name (e.g., 'Raider #1')"
    )

    resolution: EnemyResolution = Field(
        ...,
        description="How enemy was removed: FLED/STORY_ADVANCED (leaves scene), CONVINCED/NEUTRALIZED/SUBDUED (stays as NPC)"
    )

    reason: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Why enemy was removed/converted (for ML training and narrative continuity)"
    )

    # Optional NPC conversion fields (required if stays in scene)
    resulting_entity_type: Optional[Literal["neutral", "ally", "prisoner"]] = Field(
        default=None,
        description="NPC entity type after conversion (required if resolution=CONVINCED/NEUTRALIZED/SUBDUED, where enemy stays in scene)"
    )

    resulting_disposition: Optional[Literal["friendly", "neutral", "wary", "prisoner"]] = Field(
        default=None,
        description="NPC disposition after conversion (required if resolution=CONVINCED/NEUTRALIZED/SUBDUED, where enemy stays in scene)"
    )

    @field_validator('resulting_entity_type', 'resulting_disposition')
    @classmethod
    def validate_npc_fields(cls, v, info):
        """Require NPC fields when enemy stays in scene."""
        resolution = info.data.get('resolution')
        stays_in_scene = resolution in [EnemyResolution.CONVINCED, EnemyResolution.NEUTRALIZED, EnemyResolution.SUBDUED]

        if stays_in_scene and v is None:
            raise ValueError(f"{info.field_name} required when resolution={resolution} (enemy stays as NPC)")

        return v


# Legacy aliases for backward compatibility (deprecated)
class EnemyRemoval(EnemyConversion):
    """DEPRECATED: Use EnemyConversion instead. Alias maintained for backward compatibility."""
    # Override description to match old enemy_removals semantics
    enemy_name: str = Field(..., description="Enemy name or ID (legacy field, use enemy_id)")

    def __init__(self, **data):
        # Map enemy_name → enemy_id for backward compat
        if 'enemy_name' in data and 'enemy_id' not in data:
            data['enemy_id'] = data.pop('enemy_name')
        super().__init__(**data)


class Deescalation(EnemyConversion):
    """DEPRECATED: Use EnemyConversion instead. Alias maintained for backward compatibility."""
    pass


class Escalation(BaseModel):
    """
    Convert NPC to enemy after provocation.

    Use when:
    - NPC is attacked
    - NPC is severely threatened
    - NPC's faction is attacked and they choose to defend
    - Situation changes and NPC becomes hostile

    Example:
    ```python
    escalate = Escalation(
        npc_id="enemy_civilian_1",
        reason="Attacked by player, now defending self in panic",
        template="desperate_fighter"
    )
    ```
    """
    npc_id: str = Field(
        ...,
        description="NPC to convert (agent_id is preserved during conversion)"
    )
    reason: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="Why NPC escalated to combat"
    )
    template: str = Field(
        "desperate_fighter",
        description="Enemy template for tactics (default: desperate_fighter for untrained NPCs)"
    )
