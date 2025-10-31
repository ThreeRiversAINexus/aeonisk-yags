"""
Shared Pydantic types used across multiple schemas.

These models represent common game mechanics that appear in multiple contexts
(DM resolutions, player actions, enemy decisions, etc.).
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from enum import Enum


class SuccessTier(str, Enum):
    """Action outcome tiers."""
    CRITICAL_FAILURE = "critical_failure"
    FAILURE = "failure"
    MARGINAL = "marginal"
    MODERATE = "moderate"
    GOOD = "good"
    EXCELLENT = "excellent"
    EXCEPTIONAL = "exceptional"


class ActionType(str, Enum):
    """Action categorization."""
    EXPLORE = "explore"
    INVESTIGATE = "investigate"
    RITUAL = "ritual"
    SOCIAL = "social"
    COMBAT = "combat"
    TECHNICAL = "technical"
    PERCEPTION = "perception"
    SUPPORT = "support"
    CUSTOM = "custom"


class Position(str, Enum):
    """Tactical positioning."""
    ENGAGED = "Engaged"
    NEAR_PC = "Near-PC"
    NEAR_ENEMY = "Near-Enemy"
    FAR_PC = "Far-PC"
    FAR_ENEMY = "Far-Enemy"
    EXTREME_PC = "Extreme-PC"
    EXTREME_ENEMY = "Extreme-Enemy"


class VoidChange(BaseModel):
    """
    Void corruption change (positive = corruption, negative = cleansing).

    Examples:
    - VoidChange(character_name="Ash Vex", amount=2, reason="Failed ritual without offering")
    - VoidChange(character_name="Riven", amount=-3, reason="Powerful purification ritual")
    """
    character_name: str = Field(..., description="Name of character affected")
    amount: int = Field(..., description="Void change: +X corruption, -X cleansing")
    reason: str = Field(..., min_length=5, description="Why this void change occurred")


class SoulcreditChange(BaseModel):
    """
    Soulcredit economy change - REQUIRED FOR EVERY SINGLE ACTION.

    Soulcredit tracks trustworthiness and moral choices. Even neutral actions
    must explicitly log amount=0 to show intentional moral assessment.

    Examples:
    - SoulcreditChange(character_name="Echo", amount=-2, reason="Created Hollow Seed")
    - SoulcreditChange(character_name="Thresh", amount=1, reason="Void creature defeated")
    - SoulcreditChange(character_name="Ash", amount=0, reason="Justified combat, morally neutral")
    - SoulcreditChange(character_name="Riven", amount=0, reason="Normal investigation, no moral choice")
    """
    character_name: str = Field(..., description="Name of character affected")
    amount: int = Field(..., description="Soulcredit change: +X gain, -X cost, or 0 for neutral")
    reason: str = Field(..., min_length=5, description="Why this change occurred (even if +0)")


class ClockUpdate(BaseModel):
    """
    Progress clock advancement/regression.

    Examples:
    - ClockUpdate(clock_name="Enemy Reinforcements", ticks=2, reason="Alarm triggered")
    - ClockUpdate(clock_name="Passenger Safety", ticks=-1, reason="Evacuation successful")
    """
    clock_name: str = Field(..., description="Exact name of clock to update")
    ticks: int = Field(..., description="Ticks to add (+) or regress (-)")
    reason: str = Field(..., min_length=5, description="Why this clock changed")


class Condition(BaseModel):
    """
    Status effect or condition applied to character.

    IMPORTANT: Always specify the penalty value explicitly!
    - Negative penalties are DEBUFFS (e.g., penalty=-3 for Stunned = -3 to rolls)
    - Positive penalties are BUFFS (e.g., penalty=2 for Inspired = +2 to rolls)
    - Use penalty=0 ONLY for purely narrative conditions with no mechanical effect

    Examples:
    - Condition(name="Stunned", penalty=-3, duration=2, description="Cannot act next round, -3 to all rolls")
    - Condition(name="Inspired", penalty=2, duration=3, description="+2 to next attack")
    - Condition(name="Marked", penalty=0, duration=5, description="Target tracked by scanner, no mechanical penalty")
    """
    name: str = Field(..., description="Condition name (e.g., Stunned, Prone, Inspired)")
    penalty: int = Field(..., description="REQUIRED: Penalty/bonus to rolls. Negative = debuff (e.g., -3), positive = buff (e.g., +2), 0 = narrative only")
    duration: int = Field(default=1, ge=1, description="Rounds this condition lasts")
    description: str = Field(..., min_length=5, description="What this condition does")


class DamageEffect(BaseModel):
    """
    Damage dealt to a target.

    For enemy → player attacks: Full breakdown with soak.
    For player → enemy attacks: Simplified (DM infers enemy soak).

    Examples:
    - DamageEffect(target="Thresh Ireveth", base_damage=14, soak=10, dealt=4)
    - DamageEffect(target="tgt_7a3f", base_damage=12, dealt=12)  # Enemy (soak unknown)
    """
    target: str = Field(..., description="Target character name or target ID (tgt_xxxx)")
    base_damage: int = Field(..., ge=0, description="Damage before soak")
    soak: Optional[int] = Field(default=None, ge=0, description="Damage soaked (if known)")
    dealt: int = Field(..., ge=0, description="Final damage dealt after soak")
    damage_type: Optional[str] = Field(default=None, description="Type of damage (kinetic, void, psychic, etc.)")


class PositionChange(BaseModel):
    """
    Character movement to new tactical position.

    Examples:
    - PositionChange(character_name="Ash Vex", new_position="Near-PC", reason="Rushed forward")
    """
    character_name: str = Field(..., description="Character that moved")
    new_position: Position = Field(..., description="New tactical position")
    reason: str = Field(..., min_length=5, description="Why/how they moved")
