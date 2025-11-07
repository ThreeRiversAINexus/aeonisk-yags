"""
Action Effect Schemas for NPC System

Defines structured output for healing effects and agent conversions.
These are used in action resolution and JSONL logging.
"""

from pydantic import BaseModel, Field
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
