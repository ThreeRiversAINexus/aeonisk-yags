"""
Player Action Declaration Schema

Structured output for player agent action declarations.

Replaces the current text-based parsing with validated structured output.
Player agents must provide complete mechanical information with each action.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict
from .shared_types import ActionType, Position


class PlayerAction(BaseModel):
    """
    Structured player action declaration.

    Forces agents to think mechanically and provide complete information.
    Eliminates ambiguity and skill routing edge cases.

    Example:
    ```python
    action = PlayerAction(
        intent="Scan void corruption patterns",
        description="Using neural interface to analyze anomalous resonance frequencies",
        attribute="Intelligence",
        skill="Systems",
        difficulty_estimate=22,
        difficulty_justification="Complex technical analysis under pressure",
        action_type=ActionType.TECHNICAL,
        character_name="Echo Resonance",
        agent_id="player_echo"
    )
    ```
    """

    # Core action definition
    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Clear, concise description of what you're doing (10-200 chars)"
    )

    description: str = Field(
        ...,
        min_length=50,
        max_length=800,
        description="1-3 sentence narrative description with context (50-800 chars)"
    )

    # Mechanical components
    attribute: str = Field(
        ...,
        description="Attribute used: Strength, Agility, Endurance, Perception, Intelligence, Empathy, Willpower, Charisma"
    )

    skill: Optional[str] = Field(
        default=None,
        description="Skill used (or None for raw attribute check). Agent chooses skill explicitly - no automatic routing."
    )

    difficulty_estimate: int = Field(
        ...,
        ge=5,
        le=50,
        description="Estimated target DC: 10=Easy, 15=Moderate, 20=Challenging, 25=Hard, 30+=Very Hard"
    )

    difficulty_justification: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Why you chose this difficulty estimate (10-300 chars)"
    )

    # Action categorization
    action_type: ActionType = Field(
        ...,
        description="Action category for context"
    )

    # Character identification
    character_name: str = Field(
        ...,
        description="Full character name"
    )

    agent_id: str = Field(
        ...,
        description="Agent identifier (e.g., 'player_ash', 'player_echo')"
    )

    # Tactical components (optional)
    target_position: Optional[Position] = Field(
        default=None,
        description="Desired tactical position after movement (if applicable)"
    )

    target: Optional[str] = Field(
        default=None,
        description="Target ID (tgt_xxxx) or character name for targeted actions"
    )

    # Ritual-specific fields (optional)
    is_ritual: bool = Field(
        default=False,
        description="Whether this is a ritual action"
    )

    has_primary_tool: bool = Field(
        default=False,
        description="Do you have the required ritual focus/tool?"
    )

    has_offering: bool = Field(
        default=False,
        description="Are you making an offering to reduce void risk?"
    )

    ritual_components: Optional[str] = Field(
        default=None,
        max_length=200,
        description="What materials/components are you using? (if ritual)"
    )

    # Optional modifiers
    situational_modifiers: Dict[str, int] = Field(
        default_factory=dict,
        description="Situational bonuses/penalties (e.g., {'high_ground': 2, 'darkness': -3})"
    )

    # Metadata
    reasoning: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Internal reasoning for this action choice (for ML training)"
    )

    @field_validator('attribute')
    @classmethod
    def validate_attribute(cls, v: str) -> str:
        """Validate attribute is one of the canonical 8."""
        valid_attributes = {
            "Strength", "Agility", "Endurance", "Perception",
            "Intelligence", "Empathy", "Willpower", "Charisma"
        }
        if v not in valid_attributes:
            raise ValueError(
                f"Attribute must be one of: {', '.join(sorted(valid_attributes))}"
            )
        return v

    @field_validator('skill')
    @classmethod
    def validate_skill(cls, v: Optional[str]) -> Optional[str]:
        """Allow None or normalize skill name."""
        if v is None or v.lower() == 'none':
            return None
        return v

    @field_validator('ritual_components')
    @classmethod
    def validate_ritual_components(cls, v: Optional[str], info) -> Optional[str]:
        """Ritual components only allowed if is_ritual=True."""
        if v and not info.data.get('is_ritual', False):
            raise ValueError("ritual_components can only be set if is_ritual=True")
        return v

    def get_summary(self) -> str:
        """Get brief action summary for logging."""
        skill_text = f" × {self.skill}" if self.skill else ""
        target_text = f" → {self.target}" if self.target else ""
        return f"{self.character_name}: {self.intent} ({self.attribute}{skill_text} vs ~{self.difficulty_estimate}){target_text}"

    def to_legacy_dict(self) -> Dict:
        """
        Convert to legacy dict format for backward compatibility.

        Returns dict matching the old ActionDeclaration format.
        """
        return {
            'intent': self.intent,
            'description': self.description,
            'attribute': self.attribute,
            'skill': self.skill,
            'difficulty_estimate': self.difficulty_estimate,
            'difficulty_justification': self.difficulty_justification,
            'action_type': self.action_type.value if isinstance(self.action_type, ActionType) else self.action_type,
            'character_name': self.character_name,
            'agent_id': self.agent_id,
            'target_position': self.target_position.value if self.target_position else None,
            'target': self.target,
            'is_ritual': self.is_ritual,
            'has_primary_tool': self.has_primary_tool,
            'has_offering': self.has_offering,
            'ritual_components': self.ritual_components,
            'situational_modifiers': self.situational_modifiers,
        }


class FreeAction(BaseModel):
    """
    Free actions (dialogue, coordination, minor interactions).

    Simpler than full PlayerAction - no difficulty estimates or mechanical components.

    Example:
    ```python
    free_action = FreeAction(
        intent="Share tactical data with Thresh",
        description="Transmit neural scan results showing enemy weak point at junction B-7",
        character_name="Echo Resonance",
        agent_id="player_echo",
        target="Thresh Ireveth"
    )
    ```
    """

    intent: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="What you're doing/saying"
    )

    description: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Details of the free action"
    )

    character_name: str = Field(
        ...,
        description="Character taking action"
    )

    agent_id: str = Field(
        ...,
        description="Agent identifier"
    )

    target: Optional[str] = Field(
        default=None,
        description="Target character (if directed at someone)"
    )

    is_coordination: bool = Field(
        default=False,
        description="Is this a coordination action that grants bonus to ally?"
    )

    coordination_bonus: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Bonus granted if is_coordination=True"
    )

    def get_summary(self) -> str:
        """Get brief summary."""
        target_text = f" → {self.target}" if self.target else ""
        coord_text = f" [+{self.coordination_bonus}]" if self.is_coordination else ""
        return f"{self.character_name}: {self.intent}{target_text}{coord_text}"
