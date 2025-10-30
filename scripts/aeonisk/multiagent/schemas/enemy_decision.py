"""
Enemy Tactical Decision Schema

Structured output for enemy agent tactical declarations.

Replaces text parsing of enemy declarations with validated structured output.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from .shared_types import Position


class EnemyDecision(BaseModel):
    """
    Enemy tactical decision for a combat round.

    Mirrors the existing enemy declaration format but with Pydantic validation.

    Example:
    ```python
    decision = EnemyDecision(
        agent_id="enemy_scanner_01",
        character_name="Void Scanner Alpha",
        initiative=18,
        defence_token="tgt_a4f2",
        major_action="Attack",
        target="tgt_a4f2",
        weapon="Void Beam",
        minor_action="Move",
        token_target="Near-PC",
        tactical_reasoning="Focus fire on wounded target (HP: 8/20) to eliminate threat",
        shared_intel="Scanner detected void corruption signature at 85% - prioritize disruption"
    )
    ```
    """

    # Identity
    agent_id: str = Field(
        ...,
        description="Enemy agent ID (e.g., 'enemy_scanner_01')"
    )

    character_name: str = Field(
        ...,
        description="Enemy character name"
    )

    initiative: int = Field(
        ...,
        ge=1,
        le=50,
        description="Initiative roll result"
    )

    # Defensive positioning
    defence_token: Optional[str] = Field(
        default=None,
        description="Target ID (tgt_xxxx) to protect/cover, or None"
    )

    # Major action (primary activity)
    major_action: Literal["Attack", "Move", "Defend", "Ability", "Retreat", "FLEE"] = Field(
        ...,
        description="Primary action this round"
    )

    target: Optional[str] = Field(
        default=None,
        description="Target ID (tgt_xxxx) for Attack/Ability actions"
    )

    weapon: Optional[str] = Field(
        default=None,
        description="Weapon/ability used for Attack/Ability actions"
    )

    # Minor action (optional secondary activity)
    minor_action: Optional[Literal["Move", "Reload", "Scan", "Communicate", "None"]] = Field(
        default=None,
        description="Secondary action (if any)"
    )

    token_target: Optional[str] = Field(
        default=None,
        description="Target ID or Position for minor Move action"
    )

    # Reasoning (for ML training)
    tactical_reasoning: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Why you chose this action (target priority, threat assessment, coordination)"
    )

    shared_intel: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Intel to share with allied enemies (optional)"
    )

    # Panic/morale state
    is_panicked: bool = Field(
        default=False,
        description="Is this enemy panicked (morale broken)?"
    )

    def get_summary(self) -> str:
        """Get brief decision summary for logging."""
        target_text = f" → {self.target}" if self.target else ""
        weapon_text = f" ({self.weapon})" if self.weapon else ""
        return f"{self.character_name} [Init {self.initiative}]: {self.major_action}{weapon_text}{target_text}"

    def to_legacy_dict(self) -> dict:
        """
        Convert to legacy EnemyDeclaration dict format.

        Returns dict matching the old parsed format.
        """
        return {
            'agent_id': self.agent_id,
            'character_name': self.character_name,
            'initiative': self.initiative,
            'defence_token': self.defence_token,
            'major_action': self.major_action,
            'target': self.target,
            'weapon': self.weapon,
            'minor_action': self.minor_action,
            'token_target': self.token_target,
            'reasoning': self.tactical_reasoning,
            'shared_intel': self.shared_intel,
        }


class EnemyMoraleCheck(BaseModel):
    """
    Enemy morale/panic state assessment.

    Used to determine if enemy should panic (flee) based on:
    - Low HP (< 25%)
    - Severe stun accumulation (5+ stun points)
    - Witnessing ally defeats
    """

    should_panic: bool = Field(
        ...,
        description="Should this enemy enter panicked state?"
    )

    reason: str = Field(
        ...,
        min_length=10,
        description="Why morale check triggered (low HP, severe stun, ally defeat, etc.)"
    )

    hp_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Current HP as percentage (if HP-based check)"
    )

    stun_points: Optional[int] = Field(
        default=None,
        ge=0,
        description="Current stun accumulation (if stun-based check)"
    )

    allies_defeated: Optional[int] = Field(
        default=None,
        ge=0,
        description="Number of allies defeated this session (if last-survivor check)"
    )
