"""
DM Action Resolution Schema

Structured output for DM's action adjudication.

Philosophy: Keep narration freeform and creative, but structure the mechanics.
The DM LLM still writes 500-1500 characters of vivid storytelling, but mechanical
effects (damage, void, clocks, conditions) are validated structured fields.

This eliminates keyword detection (e.g., parsing "⚫ Void: +1" markers from text)
while preserving narrative quality.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from .shared_types import (
    SuccessTier,
    VoidChange,
    SoulcreditChange,
    ClockUpdate,
    Condition,
    DamageEffect,
    PositionChange,
)


class MechanicalEffects(BaseModel):
    """
    Structured mechanical outcomes of an action.

    All fields are optional - only include what actually happened.
    Empty lists mean nothing of that type occurred.

    CRITICAL: Populate clock_updates for actions that advance/regress scene clocks!
    Use exact clock names provided in the prompt. Examples:
    - Investigation succeeds → ClockUpdate(clock_name="Evidence Collection", ticks=2, reason="Found crucial documents")
    - Smuggler intimidated → ClockUpdate(clock_name="Hostage Execution", ticks=-1, reason="Smugglers calmed by negotiation")
    - Alarm triggered → ClockUpdate(clock_name="Security Response", ticks=3, reason="Multiple alarms activated")
    """
    # Combat
    damage: Optional[DamageEffect] = Field(
        default=None,
        description="Damage dealt (if any)"
    )

    # State changes
    void_changes: List[VoidChange] = Field(
        default_factory=list,
        description="Void corruption/cleansing changes"
    )

    soulcredit_changes: List[SoulcreditChange] = Field(
        default_factory=list,
        description="Soulcredit economy changes"
    )

    clock_updates: List[ClockUpdate] = Field(
        default_factory=list,
        description="Progress clock advancements/regressions. IMPORTANT: If action advances/regresses ANY scene clock, populate this field! Use exact clock names from prompt. Example: ClockUpdate(clock_name='Hostage Execution', ticks=1, reason='Tension escalating')"
    )

    # Status effects
    conditions: List[Condition] = Field(
        default_factory=list,
        description="New status effects applied (stunned, prone, inspired, etc.)"
    )

    # Tactical positioning
    position_changes: List[PositionChange] = Field(
        default_factory=list,
        description="Tactical position changes (for characters that moved)"
    )

    # Additional metadata
    notes: List[str] = Field(
        default_factory=list,
        description="Additional mechanical notes (e.g., 'Enemy dropped weapon', 'Ally gained intel')"
    )


class OutcomeTierExplanation(BaseModel):
    """
    ML Training: What would have happened at each success tier.

    Matches aeonisk_dataset_guidelines.txt format for outcome_explanation.
    Each tier needs vivid narrative + specific mechanical effects.
    """
    narrative: str = Field(
        ...,
        min_length=50,
        max_length=500,
        description="Vivid description of what this outcome looks like (50-500 chars)"
    )

    mechanical_effect: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Specific mechanical consequences (e.g., '+2 Void', 'Target takes 3 damage', 'Clock +2')"
    )


class ActionResolution(BaseModel):
    """
    Complete DM action resolution: freeform narration + structured mechanics.

    EXTENDED for ML training with dataset guidelines compliance:
    - Full character sheet data (attributes, skills, status)
    - Contextual fields (environment, stakes, goal)
    - All 6 outcome tier narratives + mechanical effects
    - Roll formula and DM rationale

    Example usage:
    ```python
    resolution = ActionResolution(
        narration="Ash's ritual shatters against inverted resonance patterns...",
        success_tier=SuccessTier.CRITICAL_FAILURE,
        margin=-8,
        effects=MechanicalEffects(
            void_changes=[
                VoidChange(character_name="Ash Vex", amount=2, reason="Ritual backfire")
            ],
            clock_updates=[
                ClockUpdate(clock_name="Void Surge", ticks=2, reason="Uncontrolled energy")
            ]
        ),
        # ML training fields
        character_data={
            "name": "Ash Vex",
            "attributes": {"willpower": 3, "intelligence": 4, ...},
            "skills": {"astral_arts": 6, ...},
            "void": 3,
            "wounds": [],
            "status_effects": []
        },
        environment="Abandoned ritual chamber, ley line intersection, void-tainted",
        stakes="Ash risks void corruption to commune with echo fragment for intel",
        goal="Commune with echo to learn ritual's origin",
        roll_formula="Willpower 3 x Astral Arts 6 = 18; 18 + d20(5) = 23 vs DC 25",
        rationale="High DC (25) due to void taint and unstable ley convergence",
        outcome_tiers={
            "critical_failure": OutcomeTierExplanation(...),
            "failure": OutcomeTierExplanation(...),
            ...
        }
    )
    ```
    """

    # Freeform narrative (DM's creative storytelling)
    narration: str = Field(
        ...,
        min_length=200,
        max_length=2000,
        description="DM's vivid narrative description of what happened (200-2000 chars)"
    )

    # Success determination
    success_tier: SuccessTier = Field(
        ...,
        description="Outcome quality: critical_failure → exceptional"
    )

    margin: int = Field(
        ...,
        description="Success margin: roll - DC (negative = failure, positive = success)"
    )

    # Structured mechanical effects
    effects: MechanicalEffects = Field(
        default_factory=MechanicalEffects,
        description="All mechanical state changes (damage, void, clocks, conditions)"
    )

    # Optional additional context
    roll_details: Optional[str] = Field(
        default=None,
        description="Breakdown of roll (e.g., 'Str 4 × Combat 3 + d20(12) = 24 vs DC 20')"
    )

    llm_compliance_notes: Optional[str] = Field(
        default=None,
        description="Internal notes about LLM compliance issues (for ML training)"
    )

    # ========== ML Training Fields (Dataset Guidelines Compliance) ==========

    # Character data (full sheet snapshot at time of action)
    character_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Complete character state: attributes, skills, void, wounds, status_effects"
    )

    # Contextual fields (dynamic per action)
    environment: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=200,
        description="One-line setting description with relevant conditions"
    )

    stakes: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=300,
        description="What's at risk - consequences of success/failure"
    )

    goal: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=200,
        description="What the character is trying to accomplish"
    )

    # Roll mechanics explanation
    roll_formula: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=200,
        description="Human-readable roll: 'Attribute X × Skill Y = Z; Z + d20(N) = Total vs DC'"
    )

    rationale: Optional[str] = Field(
        default=None,
        min_length=20,
        max_length=500,
        description="DM reasoning for DC, approach choice, and difficulty factors"
    )

    # All 6 outcome tiers with narratives + mechanical effects
    outcome_tiers: Optional[Dict[str, OutcomeTierExplanation]] = Field(
        default=None,
        description="STRONGLY RECOMMENDED for ML training: All 6 outcome tiers (critical_failure, failure, moderate_success, good_success, excellent_success, exceptional_success) with narrative (50-500 chars) + mechanical_effect (10-300 chars) for each tier. See ml_training_tiers section in system prompt for detailed instructions and examples."
    )


class CombatResolution(ActionResolution):
    """
    Extended resolution for combat actions with explicit attack/damage breakdown.

    Inherits all ActionResolution fields, adds combat-specific details.
    """

    attack_roll: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total attack roll value"
    )

    attack_dc: Optional[int] = Field(
        default=None,
        ge=0,
        description="Defense DC the attack was rolled against"
    )

    attack_hit: bool = Field(
        default=False,
        description="Whether attack roll met/exceeded DC"
    )

    # Damage is already in effects.damage, but we can add combat-specific metadata
    weapon_used: Optional[str] = Field(
        default=None,
        description="Weapon/ability used in attack"
    )

    critical_hit: bool = Field(
        default=False,
        description="Whether this was a critical hit (margin ≥ 15)"
    )


# Factory functions for common resolution types

def create_failure_resolution(
    narration: str,
    margin: int,
    void_change: Optional[int] = None,
    character_name: Optional[str] = None
) -> ActionResolution:
    """
    Helper to create a failure resolution with optional void corruption.

    Args:
        narration: DM's description of failure
        margin: How badly it failed (negative number)
        void_change: Void corruption amount (if any)
        character_name: Who gets void (if applicable)

    Returns:
        ActionResolution instance
    """
    effects = MechanicalEffects()

    if void_change and character_name:
        effects.void_changes = [
            VoidChange(
                character_name=character_name,
                amount=void_change,
                reason="Action failure"
            )
        ]

    tier = SuccessTier.CRITICAL_FAILURE if margin <= -10 else SuccessTier.FAILURE

    return ActionResolution(
        narration=narration,
        success_tier=tier,
        margin=margin,
        effects=effects
    )


def create_combat_resolution(
    narration: str,
    margin: int,
    target: str,
    base_damage: int,
    soak: Optional[int] = None,
    dealt: Optional[int] = None
) -> CombatResolution:
    """
    Helper to create a combat resolution with damage.

    Args:
        narration: DM's combat narration
        margin: Success margin
        target: Target character/ID
        base_damage: Damage before soak
        soak: Damage soaked (if known)
        dealt: Final damage (if known, otherwise = base_damage - soak)

    Returns:
        CombatResolution instance
    """
    if dealt is None:
        dealt = base_damage - (soak or 0)

    effects = MechanicalEffects(
        damage=DamageEffect(
            target=target,
            base_damage=base_damage,
            soak=soak,
            dealt=dealt
        )
    )

    # Determine success tier
    if margin >= 20:
        tier = SuccessTier.EXCEPTIONAL
    elif margin >= 15:
        tier = SuccessTier.EXCELLENT
    elif margin >= 10:
        tier = SuccessTier.GOOD
    elif margin >= 5:
        tier = SuccessTier.MODERATE
    elif margin >= 0:
        tier = SuccessTier.MARGINAL
    elif margin >= -5:
        tier = SuccessTier.FAILURE
    else:
        tier = SuccessTier.CRITICAL_FAILURE

    return CombatResolution(
        narration=narration,
        success_tier=tier,
        margin=margin,
        effects=effects,
        attack_hit=(margin >= 0)
    )
