"""
Pydantic models for the Aeonisk YAGS game.

This module defines the core data models used throughout the application,
ensuring type safety and validation.
"""

from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field, validator


class Attribute(BaseModel):
    """Model representing a character attribute."""
    name: str
    value: int = Field(default=3, ge=1, le=10)
    abbreviation: Optional[str] = None
    description: Optional[str] = None


class Skill(BaseModel):
    """Model representing a character skill."""
    name: str
    value: int = Field(default=2, ge=0, le=10)
    attribute: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None


class Bond(BaseModel):
    """Model representing a character bond."""
    name: str
    type: str
    description: Optional[str] = None
    strength: int = Field(default=1, ge=1, le=5)


class Equipment(BaseModel):
    """Model representing a piece of equipment."""
    name: str
    type: str
    description: Optional[str] = None
    effects: Optional[Dict[str, Any]] = None


class Character(BaseModel):
    """Model representing a character in the game."""
    name: str
    concept: str
    attributes: Dict[str, int] = Field(default_factory=dict)
    skills: Dict[str, int] = Field(default_factory=dict)
    void_score: int = Field(default=0, ge=0, le=10)
    soulcredit: int = Field(default=0, ge=-10, le=10)
    bonds: List[Dict[str, Any]] = Field(default_factory=list)
    true_will: Optional[str] = None
    equipment: List[Dict[str, Any]] = Field(default_factory=list)

    @validator('attributes', pre=True, always=True)
    def set_default_attributes(cls, v):
        """Set default attributes if not provided."""
        default_attributes = {
            "Strength": 3,
            "Health": 3,
            "Agility": 3,
            "Dexterity": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 3,
            "Willpower": 3
        }
        if not v:
            return default_attributes
        return v

    @validator('skills', pre=True, always=True)
    def set_default_skills(cls, v):
        """Set default skills if not provided."""
        default_skills = {
            "Athletics": 2,
            "Awareness": 2,
            "Brawl": 2,
            "Charm": 2,
            "Guile": 2,
            "Sleight": 2,
            "Stealth": 2,
            "Throw": 2
        }
        if not v:
            return default_skills
        return v


class NPC(BaseModel):
    """Model representing an NPC in the game."""
    name: str
    faction: Optional[str] = None
    role: Optional[str] = None
    concept: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, int]] = None
    skills: Optional[Dict[str, int]] = None
    motivation: Optional[str] = None
    background: Optional[str] = None


class ScenarioLocation(BaseModel):
    """Model representing a location in a scenario."""
    name: str
    description: str
    atmosphere: Optional[str] = None


class ScenarioChallenge(BaseModel):
    """Model representing a challenge in a scenario."""
    description: str
    skill_check: Optional[str] = None
    difficulty: Optional[int] = None
    outcomes: Optional[Dict[str, str]] = None


class ScenarioOutcome(BaseModel):
    """Model representing a potential outcome in a scenario."""
    name: str
    description: str
    conditions: Optional[str] = None


class Scenario(BaseModel):
    """Model representing a game scenario."""
    title: Optional[str] = None
    theme: Optional[str] = None
    difficulty: Optional[str] = None
    overview: Optional[str] = None
    setting: Optional[Dict[str, Any]] = None
    npcs: Optional[Dict[str, Any]] = None
    plot_hooks: Optional[List[str]] = None
    challenges: Optional[Dict[str, Any]] = None
    outcomes: Optional[Dict[str, Any]] = None
    raw_response: Optional[str] = None


class SkillCheck(BaseModel):
    """Model representing a skill check."""
    character_name: str
    attribute: str
    skill: str
    attribute_value: int
    skill_value: int
    difficulty: int
    roll: int
    total: int
    success: bool
    margin: int
    description: str
    context: Optional[str] = None
    timestamp: Optional[str] = None


class PlayerAction(BaseModel):
    """Model representing a player action."""
    character_name: str
    action_text: str
    result_text: str
    skill_checks: List[SkillCheck] = Field(default_factory=list)
    void_change: int = 0
    soulcredit_change: int = 0
    timestamp: Optional[str] = None
    environment: Optional[str] = None
    npcs_present: Optional[List[str]] = None


class GameSession(BaseModel):
    """Model representing a game session."""
    characters: List[Character] = Field(default_factory=list)
    npcs: List[NPC] = Field(default_factory=list)
    scenario: Optional[Scenario] = None
    actions: List[PlayerAction] = Field(default_factory=list)
    current_character_index: Optional[int] = None
    
    @property
    def current_character(self) -> Optional[Character]:
        """Get the currently selected character."""
        if self.current_character_index is not None and self.characters:
            if 0 <= self.current_character_index < len(self.characters):
                return self.characters[self.current_character_index]
        return None


class DatasetEntry(BaseModel):
    """Model representing an entry in the dataset."""
    task_id: str
    domain: Dict[str, str]
    scenario: str
    environment: str
    stakes: str
    characters: List[Dict[str, Any]]
    goal: str
    expected_fields: List[str]
    gold_answer: Dict[str, Any]
    aeonisk_extra_data: Optional[Dict[str, Any]] = None
