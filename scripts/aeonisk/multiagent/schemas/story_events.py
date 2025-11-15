"""
Story Event Schemas

Structured output for story advancement, clock creation, and round synthesis.

Replaces marker parsing ([NEW_CLOCK: ...], [ADVANCE_STORY: ...], etc.) with
validated structured output.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
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
        max_length=150,
        description="What it means when clock advances (e.g., 'threat escalates', 'progress made')"
    )

    regress_meaning: str = Field(
        ...,
        min_length=5,
        max_length=150,
        description="What it means when clock regresses (opposite of advance)"
    )

    filled_consequence: str = Field(
        default="",
        min_length=0,
        max_length=400,
        description="What happens when clock fills (e.g., 'Enemy reinforcements arrive')"
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

    npc_departures: List[str] = Field(
        default_factory=list,
        description="NPC agent_ids or names to remove from scenario (e.g., ['npc_civilian_1']). NPCs can leave during minor scene changes (flee from alarm, dismissed, walk away)."
    )

    enemy_departures: List[str] = Field(
        default_factory=list,
        description="Enemy agent_ids to remove from scenario (e.g., ['enemy_grunt_abc123']). Enemies can leave during scene pivots (patrol moves on, guards finish inspection, pursuers lost during escape)."
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
        min_length=100,
        max_length=1500,
        description="""New situation description (if advancing).

⚠️ IMPORTANT: Be GENEROUS with detail! Aim for 400-800 characters.

Story advancements are major narrative transitions - paint a vivid picture:
- Describe the new location atmosphere (sights, sounds, smells, lighting)
- Establish immediate situation and stakes
- Introduce new NPCs/threats/complications present in the scene
- Show how players arrived here (transition from previous scene)
- Set tone and tension for the new chapter

Shorter descriptions feel rushed and unsatisfying. Longer descriptions create immersion."""
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

    vendor_departures: List[str] = Field(
        default_factory=list,
        description="Vendor names to remove from scenario (e.g., ['S4CU Vending Node', 'Scribe Orven Tylesh']). Vendors leave when story advances or they complete their business."
    )

    # NOTE: npc_departures removed - NPC lifecycle is handled in Entity Lifecycle Phase #2 (after story advancement)
    # The DM determines which NPCs follow to the new scene vs. stay behind in ConversionDecisions.npc_departures

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
        template="enforcer",
        faction="ACG Security",
        archetype="Enforcer",
        count=2,
        spawn_reason="Reinforcements arrive via transit tunnel",
        initial_position=Position.FAR_ENEMY
    )
    ```
    """

    template: str = Field(
        ...,
        description="""Enemy template - MUST use EXACTLY ONE of these valid templates:

⚠️ VALID TEMPLATES (use these exact strings):
- "grunt": Basic enemy, minimal training
- "elite": Veteran combatant, advanced training
- "boss": Powerful leader/commander
- "enforcer": Security/law enforcement type
- "sniper": Long-range specialist
- "support": Healer/buffer/controller
- "ambusher": Stealth/surprise attacker
- "void_cultist": Void-corrupted enemy
- "security_drone": Automated security
- "seedwalker_heavy": Augmented heavy combatant
- "voidcradle_antibot": Anti-bot specialist

⚠️ INVALID EXAMPLES (do NOT use):
- "elite_operative" → use "elite" or "enforcer"
- "guard" → use "grunt" or "enforcer"
- "soldier" → use "grunt" or "elite"
- "cultist" → use "void_cultist"
- "heavy" → use "seedwalker_heavy"

If unsure, choose the CLOSEST match from the valid templates above."""
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
    DM's round summary with potential scene pivots and story advancement.

    Use scene_pivot for minor transitions (adjacent rooms, tactical repositioning).
    Use story_advancement for major chapter changes (complete location changes).
    Cannot use both in the same round.

    **Phase Responsibilities:**

    - **Entity Lifecycle Phase** (before synthesis):
      - Enemy/NPC spawns, conversions, escalations via EntityLifecycleResult
      - Triggered by filled clocks, morale checks, tactical decisions
      - Processes departures (flee, depart)

    - **Synthesis Phase** (this schema):
      - ✅ Spawn NEW clocks via ScenePivot.new_clocks or StoryAdvancement.new_clocks
      - ✅ Narrate entity changes (describe spawns/conversions from Entity Lifecycle)
      - ✅ Track filled/expired clocks in clocks_filled/clocks_expired (JSONL logging)
      - ❌ Does NOT spawn/convert entities (that's Entity Lifecycle's job)

    - **Action Resolution Phase** (earlier, per-action):
      - Update EXISTING clocks via ActionResolution.effects.clock_updates
      - Damage, void changes, other immediate mechanical effects

    **Clock Spawning Guidance:**
    Spawn 1-2 NEW clocks every 2-3 rounds via ScenePivot.new_clocks (same location) or
    StoryAdvancement.new_clocks (new location). Clocks drive dynamic tension and prevent
    static scenarios. Use liberally when justified by narrative consequences (failed actions,
    filled clocks creating new pressures, environmental changes).

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
        clocks_filled=[],
        clocks_expired=[]
    )
    ```

    Example (Story Advancement):
    ```python
    synthesis = RoundSynthesis(
        narration="The round concludes in controlled chaos. Ash's ritual barely holds...",
        story_advancement=StoryAdvancement(should_advance=False),
        clocks_filled=["Void Surge"],
        clocks_expired=[]
    )
    ```
    """

    # Narrative summary
    narration: str = Field(
        ...,
        min_length=300,
        max_length=3000,
        description="""DM's cohesive narrative summarizing the round (300-3000 chars).

        IMPORTANT: Be generous with detail! Aim for 800-1500 characters.
        - Describe action flow chronologically
        - Include sensory details (sounds, sights, atmosphere)
        - Show consequences of each action
        - Build tension and momentum
        - Paint vivid scene transitions

        Shorter narrations feel rushed. Longer narrations feel cinematic.

        ⚠️ NARRATIVE STYLE: Use CHARACTER NAMES in narrative text, NOT target IDs.
        - ✅ CORRECT: "Ash dives behind cover as the guard opens fire..."
        - ❌ WRONG: "tgt_3c5d dives behind cover as tgt_7a3f opens fire..."

        Target IDs (tgt_xxxx) are ONLY for mechanical fields (damage.target, conditions, etc.)."""
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

    # NOTE: Enemy/NPC lifecycle fields REMOVED - now handled in Entity Lifecycle Phase (before synthesis)
    # All spawns, conversions, and escalations happen in ConversionDecisions and are tracked in EntityLifecycleResult
    # Synthesis narrates these changes but doesn't trigger them mechanically

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

    @field_validator('clocks_filled', 'clocks_expired', mode='before')
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
        max_length=500,
        description="Scenario theme/hook - describe the core tension or conflict"
    )

    location: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Starting location - be specific about the environment"
    )

    situation: str = Field(
        ...,
        min_length=50,
        max_length=2500,
        description="Opening situation - set the scene with as much detail as needed to establish atmosphere, stakes, and immediate context"
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
        max_length=800,  # Increased from 300 for liberal limits
        description="What constitutes victory?"
    )

    failure_consequences: str = Field(
        ...,
        min_length=20,
        max_length=800,  # Increased from 300 for liberal limits
        description="What happens if they fail?"
    )

    initial_enemies: List[EnemySpawn] = Field(
        default_factory=list,
        description="Enemies present at scenario start (optional)"
    )

    initial_npcs: List['NPCSpawn'] = Field(
        default_factory=list,
        description="NPCs present at scenario start (optional)"
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
        description="NPC's RELATIONSHIP to players (how they interact with party, NOT their combat threat). Options: 'neutral' (non-aligned third party), 'ally' (friendly/helpful), 'prisoner' (captured/restrained). ⚠️ DO NOT confuse with threat_level!"
    )
    threat_level: Literal["non_combatant", "potential_threat", "armed_neutral"] = Field(
        "non_combatant",
        description="NPC's COMBAT CAPABILITY (how enemies target them, NOT relationship to players). Options: 'non_combatant' (ignored by most enemies), 'potential_threat' (armed/dangerous, professionals may engage), 'armed_neutral' (visibly armed, treated as threat by ruthless enemies). ⚠️ DO NOT confuse with entity_type!"
    )
    disposition: Literal["friendly", "neutral", "wary", "fearful", "hostile", "prisoner"] = Field(
        ...,
        description="""NPC's EMOTIONAL STATE/ATTITUDE toward players.

⚠️ MUST use EXACTLY ONE of these values (no variations, synonyms, or creative alternatives):
- "friendly": Helpful, cooperative, welcoming
- "neutral": Indifferent, businesslike, professional
- "wary": Suspicious, cautious, distrustful
- "fearful": Scared, intimidated, terrified, panicked, frantic (use this for ANY fear-based state)
- "hostile": Aggressive, antagonistic (but not in combat - use escalations for combat)
- "prisoner": Captured, restrained, compliant, subdued

⚠️ EXAMPLES OF INVALID VALUES (do NOT use):
- "frantic" → use "fearful"
- "panicked" → use "fearful"
- "determined" → use "neutral" or "wary" depending on attitude
- "cooperative" → use "friendly"
- "aggressive" → use "hostile"

If unsure, choose the CLOSEST match from the 6 valid options above."""
    )
    description: str = Field(..., min_length=20, max_length=300)
    health: int = Field(..., ge=1, le=100)
    soak: int = Field(..., ge=0, le=20)
    skills: dict[str, int] = Field(
        default_factory=dict,
        description="Key YAGS skills (NOT attributes). Examples: {'Guns': 10, 'Medicine': 12, 'Stealth': 8}. Do NOT use 'Perception', 'Strength', etc. (those are attributes, not skills)."
    )

    @field_validator('skills')
    @classmethod
    def validate_skills(cls, v: dict) -> dict:
        """Ensure skills dict has integer values, not strings."""
        if not isinstance(v, dict):
            raise ValueError(f"skills must be a dict, got {type(v).__name__}")

        for skill_name, skill_value in v.items():
            if not isinstance(skill_value, int):
                raise ValueError(
                    f"Skill '{skill_name}' has invalid value type: {type(skill_value).__name__}. "
                    f"Expected int (e.g., {{'Notice': 10}}), got {{{skill_name!r}: {skill_value!r}}}"
                )
        return v

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

    resulting_disposition: Optional[Literal["friendly", "neutral", "wary", "fearful", "hostile", "prisoner"]] = Field(
        default=None,
        description="""NPC disposition after conversion (required if resolution=CONVINCED/NEUTRALIZED/SUBDUED).

⚠️ MUST use EXACTLY ONE of: "friendly", "neutral", "wary", "fearful", "hostile", "prisoner"

Common conversions:
- Intimidated surrender → "fearful"
- Captured/subdued → "prisoner"
- Negotiated truce → "neutral"
- Convinced to help → "friendly"

Do NOT use variations like "frantic", "panicked", "determined" - map to closest valid option."""
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


class ConversionDecisions(BaseModel):
    """
    Conversion check phase output - determines which enemies/NPCs should convert.

    This is generated in a SEPARATE phase between resolution and synthesis,
    allowing the DM to focus solely on conversion decisions without
    mixing narrative synthesis responsibilities.

    The conversion check phase runs after all action resolutions are complete,
    giving the DM full context about enemy health, player actions, and tactical situation.

    Example:
    ```python
    decisions = ConversionDecisions(
        enemy_conversions=[
            EnemyConversion(
                enemy_id="enemy_thug_01",
                resolution=EnemyResolution.CONVINCED,
                reason="Surrounded and low HP, surrenders to avoid death",
                resulting_entity_type="prisoner",
                resulting_disposition="prisoner"
            )
        ],
        escalations=[],
        npc_spawns=[
            NPCSpawn(
                name="Station Guard",
                faction="Station Security",
                entity_type="neutral",
                threat_level="armed_neutral",
                disposition="wary",
                description="Armed guard responding to alarm",
                health=60,
                soak=5,
                skills={"combat": 3, "awareness": 4}
            )
        ]
    )
    ```
    """
    enemy_conversions: List[EnemyConversion] = Field(
        default_factory=list,
        description="""Enemies to remove/convert this round.

⚠️ CRITICAL: Validate enemy_id exists before conversion! ⚠️

Valid conversions:
- Enemy flees: resolution=FLED (leaves scene entirely)
- Enemy surrenders: resolution=CONVINCED with resulting_entity_type/disposition (stays as NPC prisoner)
- Enemy subdued: resolution=SUBDUED/NEUTRALIZED with resulting_entity_type/disposition (incapacitated NPC)

See available enemies in conversion check prompt (includes enemy_id, name, health %).
Use empty list [] if no conversions."""
    )

    escalations: List[Escalation] = Field(
        default_factory=list,
        description="""NPCs to convert to enemies this round.

⚠️ CRITICAL: Validate npc_id exists before escalation! ⚠️

Common triggers:
- NPC was attacked by players (took damage)
- NPC's faction was attacked (defending allies)
- NPC was threatened/intimidated (self-defense)

See available NPCs in conversion check prompt (includes npc_id, name, disposition, health %).
Use empty list [] if no escalations."""
    )

    npc_spawns: List[NPCSpawn] = Field(
        default_factory=list,
        description="""New NPCs to spawn this round.

⚠️ CRITICAL: If you mention spawning NPCs in 'reasoning', you MUST populate this list!

Use when:
- Introducing quest-givers, guides, civilians
- Scene requires dialogue characters
- Environmental NPCs (merchants, bystanders, etc.)
- Failed player actions in hostile zones (guards respond to alarms)
- Story requires new characters (medics arrive, enforcers respond, witnesses appear)

❌ DO NOT say "Spawning X" in reasoning without adding NPCSpawn objects to this list!
✅ DO populate this list whenever you mention spawning in your reasoning!

NOTE: For enemy→NPC conversions (surrenders), use enemy_conversions with resolution=CONVINCED.
Only use npc_spawns for BRAND NEW characters entering the scene.
Use empty list [] if no new NPCs."""
    )

    enemy_spawns: List['EnemySpawn'] = Field(
        default_factory=list,
        description="""New enemies to spawn this round.

⚠️ CRITICAL: If you mention spawning enemies in 'reasoning', you MUST populate this list!

Use when:
- Reinforcements arrive after failed stealth/alarms
- New faction enters conflict
- Environmental threats appear (guards, patrols, creatures)
- Clocks trigger enemy arrival (Security Response filled, etc.)

❌ DO NOT say "Spawning X enemies" in reasoning without adding EnemySpawn objects to this list!
✅ DO populate this list whenever you mention spawning in your reasoning!
⚠️ DO NOT duplicate existing enemies! Check active enemies list first.

Use empty list [] if no new enemies needed."""
    )

    npc_departures: List[str] = Field(
        default_factory=list,
        description="""NPC agent_ids to remove from scene (fled, hidden, left).

⚠️ BE AGGRESSIVE about removing NPCs who flee/hide! ⚠️

Auto-remove NPCs when:
- NPC declared "Flee" action → IMMEDIATELY remove (add agent_id here)
- NPC declared "Hide" action → Remove after 1 round unless strong story reason to stay
- NPC has "Pass" action for 2+ consecutive rounds → Likely left scene
- NPC is non-combatant in dangerous area → Fled when combat started
- NPC's purpose is complete → Dismiss them to keep scene dynamic

Examples: ["npc_civilian_a3f2", "npc_guide_5b21"]
Use empty list [] if no NPCs should depart."""
    )

    enemy_departures: List[str] = Field(
        default_factory=list,
        description="""Enemy agent_ids to remove from scene (fled, stood down, left).

⚠️ BE AGGRESSIVE about removing enemies who are no longer relevant! ⚠️

Auto-remove enemies when:
- Enemy declared "Flee" or "Retreat" action → IMMEDIATELY remove (add agent_id here)
- Enemies "stood down" after diplomacy → Security leaves after confirming authorization
- Scene changed and enemies don't follow → Patrol stays in previous area
- Temporary threat resolved → Guards finish inspection and move on
- Combat ended, enemies withdraw → Rival gang retreats after objective complete

Examples: ["enemy_grunt_4bc22537", "enemy_raider_a8f3"]
Use empty list [] if no enemies should depart.

⚠️ CRITICAL: This is for enemies who LEAVE THE SCENE entirely.
- Use enemy_departures for: Fled, stood down, moved on, stopped pursuing
- Use enemy_conversions for: Surrender (→ prisoner NPC), subdued (→ unconscious NPC)"""
    )

    reasoning: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="""Brief explanation of conversion decisions (20-500 chars).

⚠️ CRITICAL: If you say "Spawning X" here, you MUST populate npc_spawns or enemy_spawns lists!
❌ DO NOT use this field to "narrate" spawns without actually creating them in the lists above!

Explain WHY you made these conversion choices based on:
- Enemy health/morale (low HP = surrender likely)
- Player actions (intimidation, diplomacy = de-escalation)
- NPC provocations (attacked = escalation likely)
- Tactical situation (surrounded, outnumbered = flee/surrender)
- Spawn decisions (what triggered spawns, why now)

Example: "Thug #1 surrendered due to low HP (15%) and intimidation. Guard #2 fled when surrounded. No NPC escalations - prisoner remains compliant. Spawned 2 ACG enforcers due to alarm." """
    )


@dataclass
class EntityLifecycleResult:
    """
    Complete result of Entity Lifecycle phase - consolidates all entity state changes.

    This phase runs BEFORE synthesis, allowing DM to see final entity state when narrating.
    Combines morale checks, conversions, spawns, and removals into single result.

    Logged to JSONL as 'entity_lifecycle' event for ML training.
    """
    # Morale events (from enemy_combat.check_morale_all())
    morale_events: List[Dict[str, Any]] = field(default_factory=list)

    # Conversion decisions (from dm.check_conversions())
    conversion_decisions: Optional['ConversionDecisions'] = None

    # Enemy spawns processed (agent_ids of newly spawned enemies)
    enemies_spawned: List[str] = field(default_factory=list)

    # NPC spawns processed (agent_ids of newly spawned NPCs)
    npcs_spawned: List[str] = field(default_factory=list)

    # Enemy conversions processed (agent_ids converted enemy→NPC)
    enemies_converted: List[str] = field(default_factory=list)

    # NPC escalations processed (agent_ids converted NPC→enemy)
    npcs_escalated: List[str] = field(default_factory=list)

    # NPC departures processed (agent_ids removed from scene)
    npcs_departed: List[str] = field(default_factory=list)

    # Enemy departures processed (agent_ids removed from scene)
    enemies_departed: List[str] = field(default_factory=list)

    # Summary for synthesis context
    def to_synthesis_context(self) -> str:
        """Generate human-readable summary for DM synthesis prompt."""
        parts = []

        if self.morale_events:
            panicked = [e for e in self.morale_events if e['type'] == 'panicked']
            surrendered = [e for e in self.morale_events if e['type'] == 'surrender']
            if panicked:
                parts.append(f"{len(panicked)} enemy(ies) panicked: {', '.join(e['character_name'] for e in panicked)}")
            if surrendered:
                parts.append(f"{len(surrendered)} enemy(ies) surrendered: {', '.join(e['character_name'] for e in surrendered)}")

        if self.enemies_spawned:
            parts.append(f"{len(self.enemies_spawned)} new enemy(ies) spawned")

        if self.npcs_spawned:
            parts.append(f"{len(self.npcs_spawned)} new NPC(s) spawned")

        if self.enemies_converted:
            parts.append(f"{len(self.enemies_converted)} enemy(ies) converted to NPCs")

        if self.npcs_escalated:
            parts.append(f"{len(self.npcs_escalated)} NPC(s) escalated to enemies")

        if self.npcs_departed:
            parts.append(f"{len(self.npcs_departed)} NPC(s) departed")

        if self.enemies_departed:
            parts.append(f"{len(self.enemies_departed)} enemy(ies) departed")

        return "Entity Lifecycle: " + ("; ".join(parts) if parts else "No changes")

    def to_jsonl_dict(self, round_num: int) -> Dict[str, Any]:
        """Convert to JSONL-loggable dict for ML training."""
        return {
            'event_type': 'entity_lifecycle',
            'round': round_num,
            'morale_events': self.morale_events,
            'enemies_spawned': self.enemies_spawned,
            'npcs_spawned': self.npcs_spawned,
            'enemies_converted': self.enemies_converted,
            'npcs_escalated': self.npcs_escalated,
            'npcs_departed': self.npcs_departed,
            'enemies_departed': self.enemies_departed,
            'conversion_reasoning': self.conversion_decisions.reasoning if self.conversion_decisions else None
        }
