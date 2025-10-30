"""
Pydantic schemas for structured LLM output.

Eliminates keyword detection and text parsing by using validated structured output.
Supports multi-provider LLMs (Anthropic, OpenAI, local models) via Pydantic AI.

Author: Three Rivers AI Nexus
Date: 2025-10-29
Branch: revamp-structured-output
"""

from .shared_types import (
    SuccessTier,
    ActionType,
    Position,
    VoidChange,
    SoulcreditChange,
    ClockUpdate,
    Condition,
    DamageEffect,
)

from .action_resolution import (
    MechanicalEffects,
    ActionResolution,
)

from .player_action import PlayerAction

from .enemy_decision import EnemyDecision

from .story_events import (
    NewClock,
    StoryAdvancement,
    EnemySpawn,
    RoundSynthesis,
)

__all__ = [
    # Shared types
    "SuccessTier",
    "ActionType",
    "Position",
    "VoidChange",
    "SoulcreditChange",
    "ClockUpdate",
    "Condition",
    "DamageEffect",
    # DM resolution
    "MechanicalEffects",
    "ActionResolution",
    # Player action
    "PlayerAction",
    # Enemy decision
    "EnemyDecision",
    # Story events
    "NewClock",
    "StoryAdvancement",
    "EnemySpawn",
    "RoundSynthesis",
]
