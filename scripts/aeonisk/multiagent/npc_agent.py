"""
NPC Agent and LLM Client for simple non-combatant behavior.

NPCs (Non-Player Characters) are agents with stats but limited agency:
- Can flee, hide, plead, dialogue, assist, comply
- Have full combat stats for healing/conversion
- NO tactics, NO Position (exist "off-grid")
- Simple LLM client (not full player sophistication)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import logging

from scripts.aeonisk.multiagent.schemas.shared_types import Condition

logger = logging.getLogger(__name__)


@dataclass
class NPCAgent:
    """
    Non-player character with stats and simple LLM client.

    NPCs can:
    - Declare simple actions (flee/hide/plead/dialogue/assist/pass)
    - Be targeted for healing, buffs, conditions
    - Participate in skill checks
    - Take damage (triggers escalation potential)
    - Dialogue with players via simple LLM

    NPCs cannot:
    - Use combat tactics (no tactical AI)
    - Have Position on tactical grid
    - Declare attack actions (only if escalated to enemy)

    Critical: agent_id is STABLE across conversions (never changes).
    """

    # Identity (STABLE - never changes during conversions)
    agent_id: str
    name: str
    faction: str  # "Freeborn", "ACG", "Civilian", etc.
    entity_type: Literal["neutral", "ally", "prisoner"]

    # Behavior
    disposition: Literal["friendly", "neutral", "wary", "prisoner"]
    threat_level: Literal["non_combatant", "potential_threat", "armed_neutral"]
    description: str

    # Combat stats (preserved across conversions)
    health: int
    max_health: int
    soak: int
    void_score: int
    skills: Dict[str, int] = field(default_factory=dict)

    # Damage tracking
    stuns: int = 0
    wounds: int = 0
    conditions: List[Condition] = field(default_factory=list)

    # NPC-specific
    llm_client: Optional['NPCLLMClient'] = None  # Simple action declarations
    can_act: bool = True

    # Conversion tracking (for reverse operations)
    converted_from_enemy: bool = False
    original_enemy_template: Optional[str] = None
    conversion_history: List['ConversionRecord'] = field(default_factory=list)

    # Flags
    is_active: bool = True  # Can be set False if NPC leaves scene

    def __post_init__(self):
        """Initialize LLM client if not provided."""
        if self.llm_client is None and self.can_act:
            self.llm_client = NPCLLMClient()


class NPCAction(BaseModel):
    """
    Simple action declaration from NPC.

    NPCs have limited action set compared to players:
    - flee: Run away from combat
    - hide: Take cover, become passive
    - plead: Beg for mercy, surrender
    - comply: Follow player orders
    - dialogue: Talk, answer questions
    - assist: Help players (if friendly)
    - pass: Explicitly do nothing
    """

    action_type: Literal["flee", "hide", "plead", "comply", "dialogue", "assist", "pass"]
    description: str = Field(..., min_length=10, max_length=500)
    target: Optional[str] = Field(None, description="Target agent ID for dialogue/assist")


class NPCLLMClient:
    """
    Lightweight LLM client for NPC actions.

    Much simpler than PlayerLLMClient:
    - Prompts ~500 tokens (vs ~2000 for players)
    - Limited action set (flee/hide/plead/comply/dialogue/assist/pass)
    - No LOOKUP capability (pre-baked faction lore)
    - Opportunistic acting (skip turns when nothing interesting)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 1.0
    ):
        """
        Initialize NPC LLM client.

        Args:
            model: Anthropic model ID
            temperature: Sampling temperature (1.0 = balanced)
        """
        self.model = model
        self.temperature = temperature
        logger.debug(f"✅ NPCLLMClient initialized with model {model}")

    async def declare_action(
        self,
        npc: NPCAgent,
        context: 'NPCContext'
    ) -> NPCAction:
        """
        Get NPC action with simplified prompt.

        Args:
            npc: The NPC declaring action
            context: Simplified context (nearby agents, recent events)

        Returns:
            NPCAction with action_type and description

        Note: Full implementation deferred to Phase 7.
        For Phase 1, this is a stub.
        """
        # Stub implementation for Phase 1
        # Will be fully implemented in Phase 7
        logger.debug(f"🔍 NPC {npc.name} declaring action (stub)")
        return NPCAction(
            action_type="pass",
            description="I wait and observe the situation"
        )


@dataclass
class ConversionRecord:
    """
    Track a single agent conversion for replay/ML training.

    Records when agent converted between enemy/NPC types.
    """

    round: int
    from_type: Literal["enemy", "npc"]
    to_type: Literal["enemy", "npc"]
    trigger: str  # "morale_break", "player_intimidation", "player_attack", "voluntary"
    state_snapshot: Dict  # Health, stuns, wounds at conversion


def should_npc_act(npc: NPCAgent, context: Dict) -> bool:
    """
    Determine if NPC should act this round (opportunistic acting).

    NPCs skip turns when nothing interesting happening to reduce LLM calls.

    Act if:
    - Targeted by action this round
    - Enemy within immediate range
    - Player addresses NPC directly
    - Combat started/ended
    - Situation changed dramatically

    Pass if:
    - Safe and ignored
    - Already hiding/complying
    - No meaningful options

    Args:
        npc: The NPC to check
        context: Current situation context

    Returns:
        True if NPC should declare action, False to skip turn

    Note: Full implementation deferred to Phase 7.
    """
    # Stub implementation for Phase 1
    # Will be fully implemented in Phase 7

    # Always act if targeted
    if context.get("targeted", False):
        return True

    # Always act if enemies nearby
    if context.get("nearby_enemies", []):
        return True

    # Always act if combat just started/ended
    if context.get("combat_state_changed", False):
        return True

    # Otherwise, skip turn (opportunistic)
    return False
