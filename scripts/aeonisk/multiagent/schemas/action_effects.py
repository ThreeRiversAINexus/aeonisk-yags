"""
Action Effect Schemas for NPC System

Defines structured output for healing effects and agent conversions.
These are used in action resolution and JSONL logging.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, Dict, Any


class HealingEffect(BaseModel):
    """
    Track healing applied to target.

    Used in ActionResolution to log healing actions.

    Examples:
    - HealingEffect(target="player_01", heal_type="hp", amount=15, source="medkit")
    - HealingEffect(target="enemy_guide_1", heal_type="stun", amount=2, source="field_medicine")
    """
    target: str = Field(
        ...,
        description="Target agent ID (player_xx, enemy_xxx, or NPC agent_id)"
    )
    heal_type: Literal["stun", "wound", "hp"] = Field(
        ...,
        description="Type of healing: stun (remove stuns), wound (reduce wounds), hp (restore health)"
    )
    amount: int = Field(
        ...,
        ge=0,
        description="Amount healed (stuns removed, wounds treated, or HP restored)"
    )
    source: Optional[str] = Field(
        None,
        description="Healing source (medkit, skill check, ritual, etc.)"
    )


class AgentConversion(BaseModel):
    """
    Log agent conversions for ML training and replay.

    Critical: agent_id is STABLE across conversions (never changes).

    Used in JSONL logging to track enemy ↔ NPC conversions.

    Examples:
    - AgentConversion(round=4, agent_id="enemy_pirate_1", from_type="enemy", to_type="npc", trigger="player_intimidation")
    - AgentConversion(round=7, agent_id="enemy_pirate_1", from_type="npc", to_type="enemy", trigger="player_attack")
    """
    event_type: Literal["agent_conversion"] = "agent_conversion"
    round: int = Field(..., description="Round number when conversion occurred")
    agent_id: str = Field(
        ...,
        description="Agent ID (STABLE - never changes across conversions)"
    )
    from_type: Literal["enemy", "npc"] = Field(
        ...,
        description="Agent type before conversion"
    )
    to_type: Literal["enemy", "npc"] = Field(
        ...,
        description="Agent type after conversion"
    )
    trigger: str = Field(
        ...,
        description="What caused conversion (player_intimidation, player_attack, morale_break, voluntary, etc.)"
    )
    state_snapshot: Dict[str, Any] = Field(
        ...,
        description="Agent state at conversion (health, stuns, wounds, conditions) for replay verification"
    )


class AttunementEffect(BaseModel):
    """
    Track seed attunement outcome.

    Used in ActionResolution to log successful/failed attunement rituals.

    Examples:
    - AttunementEffect(success=True, seed_consumed=True, energy_type="spark", energy_gained=5, altar_bonus=2)
    - AttunementEffect(success=False, seed_consumed=True, energy_type="breath", energy_gained=0, void_penalty=0)
    - AttunementEffect(success=True, seed_consumed=True, energy_type="drip", energy_gained=20, echo_calibrator_used=True, calibrator_void=1)
    """
    success: bool = Field(
        ...,
        description="Whether attunement ritual succeeded"
    )
    seed_consumed: bool = Field(
        ...,
        description="Whether Raw Seed was consumed (always True currently)"
    )
    energy_type: Literal["breath", "grain", "drip", "spark"] = Field(
        ...,
        description="Target energy type for attunement"
    )
    energy_gained: int = Field(
        ...,
        ge=0,
        description="Amount of energy added to purse (0 on failure, conversion rate on success)"
    )
    # Altar bonuses
    altar_id: Optional[str] = Field(
        None,
        description="Altar ID if used for bonus"
    )
    altar_bonus: int = Field(
        default=0,
        description="Bonus from altar quality (+1-3)"
    )
    # Echo-Calibrator
    echo_calibrator_used: bool = Field(
        default=False,
        description="Whether Echo-Calibrator was used"
    )
    calibrator_check_success: Optional[bool] = Field(
        None,
        description="Whether DC 16 Dex+Craft/Tech check succeeded (only if echo_calibrator_used=True)"
    )
    calibrator_void: int = Field(
        default=0,
        description="Void added from failed Echo-Calibrator check (+1 on failure)"
    )
    upkeep_paid: bool = Field(
        default=False,
        description="Whether 1 Drip upkeep was paid (every 3rd use)"
    )
    # Outcome details
    void_penalty: int = Field(
        default=0,
        description="Total void added from ritual (failed ritual or Echo-Calibrator failure)"
    )
    roll_total: Optional[int] = Field(
        None,
        description="Total roll result (if ritual roll was made)"
    )
    roll_margin: Optional[int] = Field(
        None,
        description="Margin of success/failure vs DC 20"
    )

    @field_validator('altar_bonus', 'calibrator_void', 'void_penalty', mode='before')
    @classmethod
    def coerce_none_to_zero(cls, v):
        """Coerce None to 0 for integer fields with defaults (LLM compatibility)."""
        return 0 if v is None else v
