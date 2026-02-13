"""
NPC Agent and LLM Client for simple non-combatant behavior.

NPCs (Non-Player Characters) are agents with stats but limited agency:
- Can flee, hide, plead, dialogue, assist, comply, transfer, attack
- Have full combat stats for healing/conversion
- Have Position (for tactical continuity during conversions)
- NO tactics (no tactical AI)
- Simple LLM client (not full player sophistication)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, TYPE_CHECKING, Set
from pydantic import BaseModel, Field
import logging
import hashlib

from .schemas.shared_types import Condition

if TYPE_CHECKING:
    from .enemy_agent import Position

logger = logging.getLogger(__name__)


@dataclass
class NPCMemory:
    """
    Memory system for NPCs to track their own actions, interactions, and goals.

    Solves the "Groundhog Day" problem where NPCs repeat the same dialogue
    because they have no memory of what they already said or how characters
    responded to them.

    Features:
    - Own action tracking: What the NPC said/did in previous rounds
    - Interaction history: How other characters interacted with this NPC
    - Goal evolution: NPC's current objective (can change based on events)
    - Event deduplication: Prevents seeing the same story events multiple times
    """

    # Configuration
    max_own_actions: int = 5
    max_interactions_per_char: int = 3
    max_goal_history: int = 3
    max_seen_events: int = 200

    # State
    own_actions: List[Dict] = field(default_factory=list)
    interactions: Dict[str, List[Dict]] = field(default_factory=dict)
    current_goal: Optional[str] = None
    goal_history: List[str] = field(default_factory=list)
    seen_event_hashes: Set[str] = field(default_factory=set)

    def record_own_action(
        self,
        round_num: int,
        action_type: str,
        dialogue: Optional[str] = None,
        target: Optional[str] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Record an action this NPC took.

        Args:
            round_num: The round when action occurred
            action_type: flee/hide/dialogue/etc
            dialogue: What the NPC said (if dialogue action)
            target: Who the action targeted
            reason: Why the NPC took this action
        """
        action_record = {
            'round': round_num,
            'action_type': action_type,
            'dialogue': dialogue,
            'target': target,
            'reason': reason
        }
        self.own_actions.append(action_record)

        # Limit history size (keep most recent)
        if len(self.own_actions) > self.max_own_actions:
            self.own_actions.pop(0)

    def record_interaction(
        self,
        character_name: str,
        interaction_type: str,
        details: str,
        round_num: int
    ) -> None:
        """
        Record an interaction with another character.

        Args:
            character_name: Who interacted with this NPC
            interaction_type: charmed/threatened/questioned/attacked/etc
            details: What happened
            round_num: When it happened
        """
        if character_name not in self.interactions:
            self.interactions[character_name] = []

        self.interactions[character_name].append({
            'type': interaction_type,
            'details': details,
            'round': round_num
        })

        # Limit per-character history
        if len(self.interactions[character_name]) > self.max_interactions_per_char:
            self.interactions[character_name].pop(0)

    def set_goal(self, goal: str) -> None:
        """
        Set or update the NPC's current goal.

        Args:
            goal: The NPC's current objective
        """
        if self.current_goal:
            self.goal_history.append(self.current_goal)
            # Limit history
            if len(self.goal_history) > self.max_goal_history:
                self.goal_history.pop(0)

        self.current_goal = goal

    def get_relationship_summary(self) -> str:
        """
        Generate a summary of relationships with other characters.

        Returns:
            String describing how this NPC relates to known characters
        """
        if not self.interactions:
            return ""

        lines = []
        for char_name, interactions in self.interactions.items():
            if interactions:
                # Get most recent interaction
                latest = interactions[-1]
                lines.append(f"- {char_name}: {latest['type']} (Round {latest['round']}) - {latest['details']}")

        return "\n".join(lines)

    def _hash_event(self, event: str) -> str:
        """Generate a hash for an event string."""
        return hashlib.md5(event.encode()).hexdigest()[:16]

    def has_seen_event(self, event: str) -> bool:
        """Check if NPC has already seen this event."""
        return self._hash_event(event) in self.seen_event_hashes

    def mark_event_seen(self, event: str) -> None:
        """Mark an event as seen."""
        event_hash = self._hash_event(event)
        self.seen_event_hashes.add(event_hash)

        # Prune if too large (remove random old ones)
        if len(self.seen_event_hashes) > self.max_seen_events:
            # Convert to list, remove oldest half
            hash_list = list(self.seen_event_hashes)
            self.seen_event_hashes = set(hash_list[len(hash_list) // 2:])

    def filter_unseen_events(self, events: List[str]) -> List[str]:
        """
        Filter a list of events to only those not seen before.

        Args:
            events: List of event strings

        Returns:
            List of events the NPC hasn't seen yet
        """
        unseen = []
        for event in events:
            if not self.has_seen_event(event):
                unseen.append(event)
        return unseen

    def get_memory_context(self) -> str:
        """
        Generate memory context string for inclusion in NPC prompt.

        Returns:
            Formatted string with NPC's memories, or empty if no memories
        """
        sections = []

        # Own actions section
        if self.own_actions:
            action_lines = []
            for action in self.own_actions[-3:]:  # Last 3 actions
                if action.get('dialogue'):
                    action_lines.append(
                        f"- Round {action['round']}: Said \"{action['dialogue']}\""
                        + (f" to {action['target']}" if action.get('target') else "")
                    )
                else:
                    action_lines.append(
                        f"- Round {action['round']}: {action['action_type'].title()}"
                        + (f" targeting {action['target']}" if action.get('target') else "")
                    )
            if action_lines:
                sections.append("**Your Recent Actions:**\n" + "\n".join(action_lines))

        # Relationships section
        relationship_summary = self.get_relationship_summary()
        if relationship_summary:
            sections.append("**Your Relationships:**\n" + relationship_summary)

        # Current goal section
        if self.current_goal:
            sections.append(f"**Your Current Goal:** {self.current_goal}")

        if not sections:
            return ""

        return "\n\n".join(sections)


def _default_npc_position():
    """Get default position for NPCs (Near-Enemy)."""
    from .enemy_agent import Position
    return Position(ring="Near", side="Enemy")


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
    - Have position on tactical grid (preserved during conversions)
    - Act as vendors (sell items, accept currency) if is_vendor=True

    NPCs cannot:
    - Use combat tactics (no tactical AI)
    - Declare attack actions (only if escalated to enemy)

    Vendor NPCs:
    - Can hold inventory for sale (vendor_inventory)
    - Accept purchases via is_vendor=True + accepts_purchases=True
    - Can dialogue (human traders) OR be static (vending machines via can_act=False)
    - Can be damaged, converted to enemies, flee during danger
    - Unified with regular NPCs (no separate Vendor class)

    Critical: agent_id is STABLE across conversions (never changes).
    Position is STABLE across conversions (preserves location).
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

    # Fields with defaults (must come after required fields)
    pronouns: str = "they/them"  # Default to gender-neutral
    skills: Dict[str, int] = field(default_factory=dict)

    # Tactical state (preserved across conversions) - with sensible default
    position: 'Position' = field(default_factory=lambda: _default_npc_position())
    stuns: int = 0
    wounds: int = 0
    conditions: List[Condition] = field(default_factory=list)

    # Equipment (for escalation to enemy)
    weapons: List = field(default_factory=list)  # List[Weapon], will be preserved during escalation

    # NPC-specific
    llm_client: Optional['NPCLLMClient'] = None  # Simple action declarations
    can_act: bool = True

    # Conversion tracking (for reverse operations)
    converted_from_enemy: bool = False
    original_enemy_template: Optional[str] = None
    conversion_history: List['ConversionRecord'] = field(default_factory=list)

    # Flags
    is_active: bool = True  # Can be set False if NPC leaves scene

    # Logging
    agent_prompt_logger: Optional['AgentPromptLogger'] = None  # Human-readable prompt/response logging

    # LLM provider (for creating NPCLLMClient)
    llm_provider: Optional['LLMProvider'] = None  # LLM provider instance (OpenAI, Anthropic, etc.)

    # Vendor functionality (optional - enables NPCs to sell items/services)
    is_vendor: bool = False
    vendor_inventory: List = field(default_factory=list)  # List[VendorItem] - items for sale
    vendor_greeting: Optional[str] = None  # Vendor-specific greeting (overrides general dialogue)
    vendor_type: Optional[str] = None  # "human_trader", "vending_machine", "supply_drone", etc.
    accepts_purchases: bool = False  # Whether this NPC actually processes purchases
    energy_purse: Optional['EnergyPurse'] = None  # For receiving payment (if needed for two-way trading)

    # Memory system (tracks own actions, interactions, goals)
    memory: 'NPCMemory' = field(default_factory=lambda: NPCMemory())

    def __post_init__(self):
        """Initialize LLM client if not provided."""
        if self.llm_client is None and self.can_act:
            try:
                self.llm_client = NPCLLMClient(
                    self,
                    llm_provider=self.llm_provider,
                    agent_prompt_logger=self.agent_prompt_logger
                )
                logger.debug(f"NPCLLMClient initialized for {self.name} ({self.agent_id})")
            except Exception as e:
                logger.warning(f"Failed to initialize NPCLLMClient for {self.name}: {e}. NPC will use fallback actions.")
                self.can_act = False  # Disable acting if LLM client fails

    def get_vendor_item_by_id(self, item_id: str):
        """
        Get vendor item by ID (for purchase processing).

        Returns:
            VendorItem if found, None otherwise
        """
        if not self.is_vendor:
            logger.warning(f"get_vendor_item_by_id called on non-vendor NPC {self.name}")
            return None

        for item in self.vendor_inventory:
            if hasattr(item, 'item_id') and item.item_id == item_id:
                return item
        return None


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
    - heal: Use Medicine skill to stabilize wounded allies (requires target)
    - attack: Attack players/others (simplified YAGS combat)
    - transfer: Give currency/items to another character
    - pass: Explicitly do nothing
    """

    action_type: Literal["flee", "hide", "plead", "comply", "dialogue", "assist", "heal", "attack", "transfer", "pass"]
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1500,
        description="""Why NPC chose this action (10-1500 chars).

        For dialogue/plead actions, this should be detailed enough to capture your intent,
        emotional state, and tactical considerations.

        ⚠️ NARRATIVE STYLE: Use CHARACTER NAMES, NOT target IDs.
        - ✅ CORRECT: "Fleeing from Ash who is approaching with weapon drawn"
        - ❌ WRONG: "Fleeing from tgt_3c5d who is approaching..."
        """
    )
    target: Optional[str] = Field(None, description="Target agent ID for dialogue/assist/attack")
    dialogue_content: Optional[str] = Field(
        None,
        min_length=5,
        max_length=500,
        description="""ACTUAL WORDS SPOKEN by the NPC (REQUIRED when action_type='dialogue' or 'plead').

        When choosing dialogue or plead action, you MUST provide what the NPC actually says.
        - ✅ CORRECT (dialogue): "The vault is in the basement, past the security checkpoint."
        - ✅ CORRECT (plead): "Please, don't shoot! I have a family!"
        - ❌ WRONG: None (leaving this empty for dialogue/plead actions)
        - ❌ WRONG: "Responding to the question" (this is the reason, not the dialogue)

        Use first-person perspective (what you say, not what "the NPC says").
        Keep it concise (5-500 characters).
        """
    )

    # Transfer-specific fields
    transfer_target: Optional[str] = Field(
        None,
        description="""Target character name or agent_id for transfer action.
        REQUIRED when action_type='transfer'.
        Examples: "player_01", "Ash Vex", "tgt_a3f2"
        """
    )
    transfer_currency: Optional[Dict[str, int]] = Field(
        None,
        description="""Currency amounts to transfer.
        At least one of transfer_currency or transfer_items required for transfer action.
        Example: {"drip": 10, "spark": 2}
        """
    )
    transfer_items: Optional[Dict[str, int]] = Field(
        None,
        description="""Item amounts to transfer.
        At least one of transfer_currency or transfer_items required for transfer action.
        Example: {"Medkit": 1, "KeyCard": 1}
        """
    )

    def model_post_init(self, __context):
        """Validate action-specific requirements."""
        # Dialogue/plead validation
        if self.action_type in ["dialogue", "plead"] and not self.dialogue_content:
            raise ValueError(
                f"dialogue_content is REQUIRED when action_type='{self.action_type}'. "
                f"You must provide what the NPC actually says, not just the reason. "
                f"Example: dialogue_content='Please don't shoot, I surrender!'"
            )

        # Attack validation
        if self.action_type == "attack" and not self.target:
            raise ValueError(
                "target is REQUIRED when action_type='attack'. "
                "Specify the agent_id or tgt_ ID of the character to attack. "
                "Example: target='tgt_1234'"
            )

        # Heal validation
        if self.action_type == "heal" and not self.target:
            raise ValueError(
                "target is REQUIRED when action_type='heal'. "
                "Specify the agent_id of the character to heal. "
                "Example: target='player_01'"
            )

        # Transfer validation
        if self.action_type == "transfer":
            if not self.transfer_target:
                raise ValueError(
                    "transfer_target is REQUIRED when action_type='transfer'. "
                    "Specify character name or agent_id of the recipient."
                )
            if not self.transfer_currency and not self.transfer_items:
                raise ValueError(
                    "At least one of transfer_currency or transfer_items is REQUIRED "
                    "when action_type='transfer'. Example: transfer_currency={'drip': 5}"
                )


class NPCLLMClient:
    """
    Lightweight LLM client for NPC actions.

    Much simpler than PlayerLLMClient:
    - Prompts ~500 tokens (vs ~2000 for players)
    - Limited action set (flee/hide/plead/comply/dialogue/assist/heal/transfer/attack/pass)
    - No LOOKUP capability (pre-baked faction lore)
    - Opportunistic acting (skip turns when nothing interesting)
    """

    def __init__(
        self,
        npc: 'NPCAgent',
        llm_provider=None,
        temperature: float = 1.0,
        agent_prompt_logger=None
    ):
        """
        Initialize NPC LLM client.

        Args:
            npc: The NPC this client represents
            llm_provider: LLMProvider instance (OpenAI, Anthropic, etc.)
            temperature: Sampling temperature (1.0 = balanced)
            agent_prompt_logger: Optional AgentPromptLogger for human-readable logging
        """
        self.npc = npc
        self.llm_provider = llm_provider
        self.temperature = temperature
        self.agent_prompt_logger = agent_prompt_logger
        self.call_count = 0  # Track LLM call sequence

        if llm_provider:
            logger.debug(f"✅ NPCLLMClient initialized for {npc.name} with provider {type(llm_provider).__name__}")
        else:
            logger.warning(f"⚠️  NPCLLMClient initialized for {npc.name} WITHOUT LLM provider - will use fallback actions")

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

        # Check if LLM provider available
        if not self.llm_provider:
            logger.warning(f"No LLM provider for NPC {self.npc.name}, using fallback")
            return self._get_fallback_action(context)

        # Call LLM with provider
        try:
            action = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=NPCAction,
                system_prompt=self._get_system_prompt(),
                max_tokens=4000,  # Increased from 2000 - prevent OpenAI finish_reason:length errors
                temperature=self.temperature
            )

            # Log to human-readable agent prompt log if enabled
            if self.agent_prompt_logger:
                try:
                    system_prompt = self._get_system_prompt()
                    full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
                    response_text = action.model_dump_json(indent=2)

                    self.agent_prompt_logger.log_llm_call(
                        agent_id=self.npc.agent_id,
                        round_num=None,  # NPCs don't track round internally
                        call_sequence=self.call_count,
                        prompt=full_prompt,
                        response=response_text,
                        model=getattr(self.llm_provider, 'model_name', 'unknown'),
                        temperature=self.temperature,
                        metadata={'purpose': 'npc_action_declaration', 'note': 'Structured output (NPCAction schema)'}
                    )
                    self.call_count += 1
                except Exception as e:
                    logger.error(f"NPC {self.npc.agent_id}: Failed to log to agent prompt logger: {e}")

            logger.debug(f"NPC {self.npc.name} declares: {action.action_type}")
            return action

        except Exception as e:
            logger.warning(f"NPC LLM call failed for {self.npc.name}: {e}, using fallback")
            return self._get_fallback_action(context)

    def _get_system_prompt(self) -> str:
        """Get system prompt based on NPC type."""
        # Get personality from description if available
        personality_note = ""
        if hasattr(self.npc, 'description') and self.npc.description:
            personality_note = f"\n**Your Personality:** {self.npc.description}\n"

        return f"""You are {self.npc.name}, a {self.npc.entity_type} NPC in a tactical RPG.

**Your Role:**
- Entity Type: {self.npc.entity_type} (neutral/ally/prisoner)
- Disposition: {self.npc.disposition} (friendly/neutral/wary/prisoner)
- Threat Level: {self.npc.threat_level} (non_combatant/potential_threat/armed_neutral)
- Faction: {self.npc.faction}
{personality_note}
**Faction Abbreviations (CANONICAL):**
- **ACG** = Astral Commerce Group (corporate megacorp, commerce and trade)
- **ArcGen** = Arcane Genetics (bio-engineering corporation, NOT the same as ACG!)
- **Sovereign Nexus** = The government
- **Pantheon Security** = Law enforcement
- **Tempest Industries** = Anti-Nexus rebels (void research)
- **House of Vox** = Media/broadcast corporation
- **Freeborn** = Natural-born, outside the pod system

**Action Options:**
- flee: Run away from danger
- hide: Take cover, avoid attention
- plead: Beg for mercy, express fear
- comply: Follow instructions, cooperate
- **dialogue: Speak, answer questions, negotiate - REQUIRES dialogue_content field with ACTUAL WORDS SPOKEN**
- assist: Help players with tasks (if friendly) - **USE target ID (tgt_xxxx) from combatant list**
- **heal: Use Medicine skill to stabilize wounded allies** - REQUIRES target ID (tgt_xxxx). Check wounds < 6 first!
- **attack: Attack players or others (if threatened, paranoid, or hostile)**
- **transfer: Give currency/items to another character - REQUIRES transfer_target + transfer_currency/transfer_items**
- pass: Do nothing this turn (use when situation doesn't involve you)

**Guidelines:**
1. Non-combatants flee or hide during combat (but can attack if cornered/panicked)
2. Prisoners plead or comply when threatened
3. Allies assist or provide dialogue
4. **For assist/dialogue actions: ALWAYS use target IDs (tgt_xxxx) from the combatant list**
5. **CRITICAL: For dialogue actions, you MUST populate dialogue_content with what you actually say**
   - ✅ CORRECT: dialogue_content="The vault is in the basement, past the security checkpoint."
   - ❌ WRONG: Leaving dialogue_content empty or null
   - Use first-person (what you say, not "the NPC says...")
   - Keep it concise (5-500 characters)
6. Pass when nothing relevant is happening (opportunistic acting)
7. Low health → prioritize fleeing/hiding
8. Stay in character based on disposition (friendly NPCs are helpful, wary NPCs are cautious)
9. **CHECK YOUR PERSONALITY** - If paranoid, threatened, or trigger-happy, consider attacking preemptively
10. If players seem hostile (armed, aggressive, threatening), you CAN attack first
11. **For transfer actions: Use to give currency/items to players or other NPCs**
    - transfer_target: Character name or agent_id (e.g., "player_01", "Ash Vex")
    - transfer_currency: Dict of amounts (e.g., {{"drip": 10, "spark": 2}})
    - transfer_items: Dict of items (e.g., {{"Medkit": 1, "KeyCard": 1}})

**When to use "transfer":**
- Paying a player for services rendered (quest rewards, escort fees)
- Giving supplies to injured/needy characters
- Bribing someone to leave you alone
- Returning borrowed/stolen items

**When to use "attack":**
- You're paranoid and see armed threats (even if they haven't acted yet)
- Players are clearly hostile (weapons drawn, threats made, aggressive posture)
- Your personality says to escalate (check your description!)
- You're cornered and panic (even non-combatants can grab weapons in desperation)
- Someone is threatening you, your faction, or people you care about

Choose the most appropriate action and explain why in 10-100 words."""

    def _build_prompt(self, context: str) -> str:
        """Build user prompt with NPC state and context."""
        # Get health status
        health_pct = (self.npc.health / self.npc.max_health) * 100 if self.npc.max_health > 0 else 0
        health_status = "critically wounded" if health_pct < 25 else "wounded" if health_pct < 50 else "healthy"

        # Build memory context if NPC has memory
        memory_section = ""
        if hasattr(self.npc, 'memory') and self.npc.memory:
            memory_context = self.npc.memory.get_memory_context()
            if memory_context:
                memory_section = f"""

**What You Remember:**
{memory_context}

**IMPORTANT:** You have already taken actions in previous rounds. DO NOT repeat yourself!
- If you already asked for IDs, don't ask again unless something changed
- If someone charmed/bribed you, remember that relationship
- Vary your dialogue and actions based on what has happened
"""

        # Build skills section (so LLM knows what NPC can do, especially Medicine for healing)
        skills_section = ""
        if hasattr(self.npc, 'skills') and self.npc.skills:
            skills_text = ", ".join(f"{k}: {v}" for k, v in self.npc.skills.items())
            skills_section = f"\n- Skills: {skills_text}"

        prompt = f"""**Current Situation:**
{context}
{memory_section}
**Your Status:**
- Health: {self.npc.health}/{self.npc.max_health} ({health_status})
- Disposition: {self.npc.disposition}
- Stuns: {self.npc.stuns}, Wounds: {self.npc.wounds}{skills_section}

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
                reason="Desperately begging for mercy as a prisoner.",
                dialogue_content="Please, I surrender! Don't hurt me!"
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
                reason="Responding to the players' question or address.",
                dialogue_content="I hear you. What would you like to know?"
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
