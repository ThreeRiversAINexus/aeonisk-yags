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
            self.llm_client = NPCLLMClient(self)


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
    reason: str = Field(..., min_length=10, max_length=500, description="Why NPC chose this action")
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
        npc: 'NPCAgent',
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 1.0
    ):
        """
        Initialize NPC LLM client.

        Args:
            npc: The NPC this client represents
            model: Anthropic model ID
            temperature: Sampling temperature (1.0 = balanced)
        """
        self.npc = npc
        self.model = model
        self.temperature = temperature
        logger.debug(f"✅ NPCLLMClient initialized for {npc.name} with model {model}")

    async def declare_action(self, context: str) -> NPCAction:
        """
        Get NPC action with simplified prompt.

        Args:
            context: Current situation description

        Returns:
            NPCAction with action_type and reason

        Behavior based on NPC state:
        - can_act=False → always pass
        - Non-combatant + combat → flee/hide
        - Prisoner → plead/comply
        - Ally → assist/dialogue
        - Neutral + calm → pass (opportunistic)
        """
        # Check if NPC can act
        if not self.npc.can_act:
            return NPCAction(
                action_type="pass",
                reason="I cannot act this turn"
            )

        # Build prompt based on NPC state
        prompt = self._build_prompt(context)

        # Call LLM with Pydantic AI
        try:
            from pydantic_ai import Agent
            from os import getenv

            # Create agent with structured output
            agent = Agent(
                self.model,
                result_type=NPCAction,
                system_prompt=self._get_system_prompt()
            )

            # Get API key
            api_key = getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning(f"No ANTHROPIC_API_KEY for NPC {self.npc.name}, using fallback")
                return self._get_fallback_action(context)

            # Run agent
            result = await agent.run(prompt, model_settings={"temperature": self.temperature})
            action = result.output

            logger.debug(f"NPC {self.npc.name} declares: {action.action_type}")
            return action

        except Exception as e:
            logger.warning(f"NPC LLM call failed for {self.npc.name}: {e}, using fallback")
            return self._get_fallback_action(context)

    def _get_system_prompt(self) -> str:
        """Get system prompt based on NPC type."""
        return f"""You are {self.npc.name}, a {self.npc.entity_type} NPC in a tactical RPG.

**Your Role:**
- Entity Type: {self.npc.entity_type} (neutral/ally/prisoner)
- Disposition: {self.npc.disposition} (friendly/neutral/wary/prisoner)
- Threat Level: {self.npc.threat_level} (non_combatant/potential_threat/armed_neutral)
- Faction: {self.npc.faction}

**Action Options:**
- flee: Run away from danger
- hide: Take cover, avoid attention
- plead: Beg for mercy, express fear
- comply: Follow instructions, cooperate
- dialogue: Speak, answer questions, negotiate
- assist: Help players with tasks (if friendly)
- pass: Do nothing this turn (use when situation doesn't involve you)

**Guidelines:**
1. Non-combatants flee or hide during combat
2. Prisoners plead or comply when threatened
3. Allies assist or provide dialogue
4. Pass when nothing relevant is happening (opportunistic acting)
5. Low health → prioritize fleeing/hiding
6. Stay in character based on disposition (friendly NPCs are helpful, wary NPCs are cautious)

Choose the most appropriate action and explain why in 10-100 words."""

    def _build_prompt(self, context: str) -> str:
        """Build user prompt with NPC state and context."""
        # Get health status
        health_pct = (self.npc.health / self.npc.max_health) * 100 if self.npc.max_health > 0 else 0
        health_status = "critically wounded" if health_pct < 25 else "wounded" if health_pct < 50 else "healthy"

        prompt = f"""**Current Situation:**
{context}

**Your Status:**
- Health: {self.npc.health}/{self.npc.max_health} ({health_status})
- Disposition: {self.npc.disposition}
- Stuns: {self.npc.stuns}, Wounds: {self.npc.wounds}

What do you do? Choose action_type and explain your reason."""

        return prompt

    def _get_fallback_action(self, context: str) -> NPCAction:
        """
        Generate fallback action based on NPC state (no LLM).

        Simple heuristic for when LLM unavailable.
        """
        context_lower = context.lower()

        # Check health
        health_pct = (self.npc.health / self.npc.max_health) * 100 if self.npc.max_health > 0 else 0

        # Wounded NPCs flee
        if health_pct < 30:
            return NPCAction(
                action_type="flee",
                reason="I'm badly wounded and need to escape to safety."
            )

        # Prisoners plead or comply
        if self.npc.entity_type == "prisoner" or self.npc.disposition == "prisoner":
            return NPCAction(
                action_type="plead",
                reason="I surrender! Please don't hurt me!"
            )

        # Combat situations - non-combatants flee (but not if combat has ended)
        combat_keywords = ["gunfire", "shooting", "attack", "weapon", "fighting"]
        calm_keywords = ["ended", "peaceful", "regrouping", "calm", "quiet", "over"]

        is_combat = any(word in context_lower for word in combat_keywords)
        is_calm = any(word in context_lower for word in calm_keywords)

        if is_combat and not is_calm:
            if self.npc.threat_level == "non_combatant":
                return NPCAction(
                    action_type="hide",
                    reason="I take cover to avoid the crossfire."
                )

        # Allies assist when players need help
        if self.npc.entity_type == "ally" and any(word in context_lower for word in ["wounded", "help", "assist"]):
            return NPCAction(
                action_type="assist",
                reason="I help the players as best I can."
            )

        # Direct address - respond with dialogue
        if any(word in context_lower for word in ["asks", "questions", "speaks", "addresses"]):
            return NPCAction(
                action_type="dialogue",
                reason="I respond to the players' question."
            )

        # Default: pass when nothing relevant
        return NPCAction(
            action_type="pass",
            reason="The situation doesn't involve me right now."
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
