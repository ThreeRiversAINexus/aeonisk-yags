"""
Enemy Agent Combat Integration

Integrates autonomous enemy agents into the existing tactical combat flow.
Manages enemy lifecycle during combat rounds: spawn, initiative, declaration,
action execution, and cleanup.

Design Document: /content/experimental/Enemy Agent System - Design Document.md

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import random

from .enemy_agent import EnemyAgent, SharedIntel, Position
from .enemy_spawner import (
    auto_despawn_defeated,
    get_active_enemies,
    suggest_loot
)
from .enemy_prompts import generate_tactical_prompt
from .awareness import filter_narrations_for_agent, NarrationEntry
from .prompt_loader import compose_sections
from .tactical_resolution import (
    ResolutionState,
    ActionValidator,
    generate_invalidation_message
)
from .base import Message, MessageType

logger = logging.getLogger(__name__)


# =============================================================================
# ENEMY DECLARATION PARSING
# =============================================================================

@dataclass
class EnemyDeclaration:
    """Parsed enemy tactical declaration."""
    agent_id: str
    character_name: str
    initiative: int
    defence_token: Optional[str]
    major_action: str
    target: Optional[str]
    weapon: Optional[str]
    minor_action: Optional[str]
    token_target: Optional[str]
    reasoning: str
    shared_intel: Optional[str]
    dialogue_content: Optional[str] = None


def _get_panicked_action(enemy: EnemyAgent) -> str:
    """
    Determine what action a panicked enemy takes based on morale_behavior.

    Returns:
        "Surrender" for surrender_if_cornered, "FLEE" for all others
    """
    morale_behavior = getattr(enemy, 'morale_behavior', 'flee_when_broken')
    if morale_behavior == 'surrender_if_cornered':
        return "Surrender"
    return "FLEE"


def parse_enemy_declaration(declaration_text: str, enemy: EnemyAgent) -> Optional[EnemyDeclaration]:
    """
    Parse structured enemy declaration output.

    Expected format:
        DEFENCE_TOKEN: pc_id
        MAJOR_ACTION: Attack
        TARGET: pc_id
        WEAPON: Rifle
        MINOR_ACTION: None
        TACTICAL_REASONING: ...
        SHARE_INTEL: ...

    Args:
        declaration_text: Enemy's LLM output
        enemy: Enemy agent that made declaration

    Returns:
        Parsed EnemyDeclaration or None if parsing failed
    """
    lines = declaration_text.strip().split('\n')
    parsed = {}

    for line in lines:
        stripped = line.strip()
        # Skip code block fences and markdown headers
        if stripped.startswith('```') or stripped.startswith('#'):
            continue

        # Strip markdown bold markers (e.g. "**MAJOR_ACTION:** Attack" → "MAJOR_ACTION: Attack")
        stripped = stripped.replace('**', '')

        if ':' in stripped:
            key, value = stripped.split(':', 1)
            key = key.strip().upper()
            value = value.strip()

            # Map keys
            if key in ['DEFENCE_TOKEN', 'DEFENSE_TOKEN']:
                parsed['defence_token'] = value if value.lower() != 'none' else None
            elif key == 'MAJOR_ACTION':
                parsed['major_action'] = value
            elif key == 'TARGET':
                parsed['target'] = value if value.lower() != 'none' else None
            elif key == 'WEAPON':
                parsed['weapon'] = value if value.lower() != 'none' else None
            elif key == 'MINOR_ACTION':
                parsed['minor_action'] = value if value.lower() != 'none' else None
            elif key in ['TOKEN_TARGET', 'TACTICAL_TOKEN']:
                parsed['token_target'] = value if value.lower() != 'none' else None
            elif key == 'TACTICAL_REASONING':
                parsed['reasoning'] = value
            elif key == 'SHARE_INTEL':
                parsed['shared_intel'] = value if value.lower() != 'none' else None

    # Validate required fields
    if 'major_action' not in parsed:
        logger.warning(f"{enemy.name}: No MAJOR_ACTION in declaration")
        return None

    return EnemyDeclaration(
        agent_id=enemy.agent_id,
        character_name=enemy.name,
        initiative=enemy.initiative,
        defence_token=parsed.get('defence_token'),
        major_action=parsed['major_action'],
        target=parsed.get('target'),
        weapon=parsed.get('weapon'),
        minor_action=parsed.get('minor_action'),
        token_target=parsed.get('token_target'),
        reasoning=parsed.get('reasoning', 'No reasoning provided'),
        shared_intel=parsed.get('shared_intel')
    )


# =============================================================================
# COMBAT MANAGER
# =============================================================================

class EnemyCombatManager:
    """
    Manages enemy agents during combat rounds.

    Integrates with existing session combat flow:
    - Spawns enemies from DM narration markers
    - Adds enemies to initiative order
    - Generates tactical prompts during declaration phase
    - Parses and executes enemy actions
    - Handles cleanup (attrition, despawn, loot)
    """

    def __init__(self, shared_state=None):
        self.enemy_agents: List[EnemyAgent] = []
        self.shared_intel = SharedIntel()
        self.enemy_declarations: Dict[str, EnemyDeclaration] = {}
        self.current_round: int = 0
        self.enabled: bool = False
        self.config: Dict[str, Any] = {}
        self.shared_state = shared_state  # Reference to shared state for logging

        # LLM Provider for structured output - initialized later from session config
        self.llm_provider = None
        # LLM Call Logger for JSONL token tracking - set by session.py after init
        self.llm_logger = None

    def _get_agent_name(self, agent: Any, fallback_id: str) -> str:
        """
        Extract name from agent, handling both enemy and player agent structures.

        - Enemy agents have .name directly
        - Player agents have .character_state.name

        Args:
            agent: Agent object (enemy or player)
            fallback_id: ID to return if name cannot be extracted

        Returns:
            Character name or fallback_id
        """
        # Try direct .name (enemy agents)
        if hasattr(agent, 'name') and agent.name:
            return agent.name

        # Try .character_state.name (player agents)
        if hasattr(agent, 'character_state'):
            char_state = agent.character_state
            if hasattr(char_state, 'name') and char_state.name:
                return char_state.name

        # Fallback to ID
        return str(fallback_id)

    def _get_agent_id(self, agent: Any, fallback_id: str) -> str:
        """
        Extract agent_id from agent object.

        Args:
            agent: Agent object (enemy or player)
            fallback_id: ID to return if agent_id cannot be extracted

        Returns:
            Agent ID or fallback_id
        """
        if hasattr(agent, 'agent_id') and agent.agent_id:
            return agent.agent_id
        return str(fallback_id)

    def initialize(self, session_config: Dict[str, Any]):
        """
        Initialize from session configuration.

        Args:
            session_config: Session configuration dict
        """
        self.enabled = (
            session_config.get('tactical_module_enabled', False) and
            session_config.get('enemy_agents_enabled', False)
        )

        if self.enabled:
            self.config = session_config.get('enemy_agent_config', {})

            # Initialize LLM provider from DM config (enemies use same provider as DM)
            from .llm_provider import create_provider
            try:
                dm_config = session_config.get('agents', {}).get('dm', {})
                llm_config = dm_config.get('llm', {})

                if llm_config:
                    from .llm_provider import LLMConfig

                    config = LLMConfig.from_dict(llm_config, max_tokens=4000)
                    self.llm_provider = create_provider(config)
                    logger.debug(f"EnemyCombatManager: Structured output provider initialized ({config.provider}:{config.model})")
                    logger.debug(f"EnemyCombatManager: llm_provider type = {type(self.llm_provider)}, is_none = {self.llm_provider is None}")
                else:
                    logger.warning("EnemyCombatManager: No DM LLM config found, structured output disabled")
                    self.llm_provider = None
            except Exception as e:
                import traceback
                logger.warning(f"EnemyCombatManager: Failed to create structured output provider: {e}")
                logger.warning(f"Traceback: {traceback.format_exc()}")
                self.llm_provider = None

            logger.debug("Enemy combat manager initialized (ENABLED)")
        else:
            logger.debug("Enemy combat manager initialized (DISABLED)")

    def process_dm_narration(self, narration: str) -> List[str]:
        """
        Legacy marker processing removed - use structured output instead.

        This method is deprecated. Enemy spawning now uses RoundSynthesis.enemy_spawns
        with spawn_from_structured().

        Args:
            narration: DM narration text (ignored)

        Returns:
            Empty list (only auto-despawn still functions)
        """
        if not self.enabled:
            return []

        # Note: This method is still called for auto-despawn functionality
        # Enemy spawning now uses RoundSynthesis.enemy_spawns with spawn_from_structured()

        # Still handle auto-despawn for defeated enemies
        notifications = []
        auto_despawned = auto_despawn_defeated(self.enemy_agents, self.current_round)
        for enemy in auto_despawned:
            notifications.append(f"💀 **{enemy.name}** defeated!")
            logger.info(f"Auto-despawned enemy: {enemy.name} (ID: {enemy.agent_id})")

        return notifications

    def spawn_from_structured(self, enemy_spawns: List['EnemySpawn']) -> List[str]:
        """
        Spawn enemies from structured output (Phase 5: Pydantic AI migration).

        Args:
            enemy_spawns: List of EnemySpawn objects from RoundSynthesis

        Returns:
            List of spawn notification messages
        """
        from .schemas.story_events import EnemySpawn
        from .enemy_spawner import spawn_enemy

        if not self.enabled:
            return []

        notifications = []

        for spawn in enemy_spawns:
            # Spawn each enemy from the structured data
            for i in range(spawn.count):
                # Generate unique name for each unit
                if spawn.count > 1:
                    enemy_name = f"{spawn.faction} {spawn.archetype} #{i+1}"
                else:
                    enemy_name = f"{spawn.faction} {spawn.archetype}"

                # Use the template-based spawner
                # spawn_enemy signature: (name, template_key, position_str, tactics_override, personality_override, current_round)
                enemy = spawn_enemy(
                    name=enemy_name,
                    template_key=spawn.template.lower(),
                    position_str=spawn.initial_position.value,  # Convert Position enum to string
                    tactics_override=spawn.custom_traits or "adaptive",
                    current_round=self.current_round
                )

                if enemy:
                    self.enemy_agents.append(enemy)
                    notifications.append(
                        f"⚔️  **{enemy.name}** spawned! "
                        f"({spawn.spawn_reason}) "
                        f"[{enemy.health} HP, {enemy.position}, tactics: {enemy.tactics}]"
                    )
                    logger.info(f"Spawned enemy (structured): {enemy.name} (ID: {enemy.agent_id}) - {spawn.spawn_reason}")

                    # Log enemy spawn to JSONL for ML training
                    if self.shared_state:
                        mechanics = self.shared_state.get_mechanics_engine()
                        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                            # Build stats dict
                            stats = {
                                "health": enemy.health,
                                "max_health": enemy.max_health,
                                "soak": enemy.soak,
                                "attributes": enemy.attributes,
                                "skills": enemy.skills,
                                "weapons": [{"name": w.name, "attack": w.attack, "damage": w.damage, "skill": w.skill} for w in enemy.weapons],
                                "armor": {"name": enemy.armor.name, "soak_bonus": enemy.armor.soak_bonus} if enemy.armor else None
                            }

                            mechanics.jsonl_logger.log_enemy_spawn(
                                round_num=self.current_round,
                                enemy_id=enemy.agent_id,
                                enemy_name=enemy.name,
                                template=spawn.template,
                                stats=stats,
                                position=str(enemy.position),
                                tactics=enemy.tactics,
                                count=spawn.count,  # Number of enemies spawned in this batch
                                faction=spawn.faction,
                            )

        return notifications

    def remove_from_structured(self, enemy_removals: List['EnemyRemoval']) -> List[str]:
        """
        Remove enemies from structured output (Phase 5: Pydantic AI migration).

        Args:
            enemy_removals: List of EnemyRemoval objects from RoundSynthesis

        Returns:
            List of removal notification messages
        """
        from .schemas.story_events import EnemyRemoval

        if not self.enabled:
            return []

        notifications = []

        for removal in enemy_removals:
            # Find matching enemies by name (partial match)
            matching_enemies = [
                e for e in self.enemy_agents
                if e.is_active and removal.enemy_name.lower() in e.name.lower()
            ]

            if not matching_enemies:
                logger.warning(f"No active enemy found matching '{removal.enemy_name}' for removal")
                continue

            for enemy in matching_enemies:
                # Check if this is a de-escalation (surrender/capture) or departure (fled/killed)
                from .schemas.story_events import EnemyResolution

                if removal.resolution in [EnemyResolution.CONVINCED, EnemyResolution.NEUTRALIZED, EnemyResolution.SUBDUED]:
                    # DE-ESCALATION: Convert enemy to NPC instead of removing
                    from .agent_conversion import deescalate_enemy_to_npc

                    # Determine disposition from resolution type
                    if removal.resolution == EnemyResolution.NEUTRALIZED:
                        disposition = "prisoner"  # Arrested, captured, restrained
                    elif removal.resolution == EnemyResolution.CONVINCED:
                        disposition = "wary"  # Talked down, suspicious but compliant
                    elif removal.resolution == EnemyResolution.SUBDUED:
                        disposition = "prisoner"  # Knocked out, incapacitated

                    # Convert enemy to NPC
                    # NPCs use same LLM provider as enemies
                    npc = deescalate_enemy_to_npc(
                        enemy=enemy,
                        disposition=disposition,
                        current_round=self.current_round,
                        llm_provider=self.llm_provider if hasattr(self, 'llm_provider') else None
                    )

                    # Add NPC to shared state
                    if self.shared_state:
                        self.shared_state.npc_agents.append(npc)
                        # Register NPC in target mapper
                        if hasattr(self.shared_state, 'target_id_mapper') and self.shared_state.target_id_mapper:
                            self.shared_state.target_id_mapper.register_npc(npc)

                    # Mark enemy as inactive
                    enemy.is_active = False
                    enemy.despawned_round = self.current_round

                    notifications.append(
                        f"🕊️  **{enemy.name}** de-escalated to NPC ({disposition}): {removal.reason}"
                    )
                    logger.info(f"De-escalated enemy to NPC: {enemy.name} ({removal.resolution.value}) → {disposition}")

                    # Log agent conversion event
                    if self.shared_state:
                        mechanics = self.shared_state.get_mechanics_engine()
                        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                            mechanics.jsonl_logger.log_event(
                                event_type="agent_conversion",
                                data={
                                    "agent_id": npc.agent_id,
                                    "from_type": "enemy",
                                    "to_type": "npc",
                                    "trigger": removal.resolution.value,
                                    "resulting_disposition": disposition,
                                    "reason": removal.reason
                                },
                                round_num=self.current_round
                            )

                else:
                    # DEPARTURE: Remove enemy from scene (fled, killed, etc.)
                    enemy.is_active = False
                    enemy.despawned_round = self.current_round

                    notifications.append(
                        f"💀 **{enemy.name}** removed ({removal.resolution.value}): {removal.reason}"
                    )
                    logger.info(f"Removed enemy (structured): {enemy.name} - {removal.resolution.value}: {removal.reason}")

                    # Log enemy defeat to JSONL for ML training
                    if self.shared_state:
                        mechanics = self.shared_state.get_mechanics_engine()
                        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                            rounds_survived = enemy.despawned_round - enemy.spawned_round
                            mechanics.jsonl_logger.log_enemy_defeat(
                                round_num=self.current_round,
                                enemy_id=enemy.agent_id,
                                enemy_name=enemy.name,
                                defeat_reason=removal.resolution.value,
                                rounds_survived=rounds_survived
                            )

        return notifications

    def get_initiative_entries(self) -> List[Tuple[int, EnemyAgent]]:
        """
        Get enemy initiative entries for combat round.

        Returns:
            List of (initiative, enemy) tuples for active enemies
        """
        if not self.enabled:
            return []

        # Re-roll initiative for all active enemies
        entries = []
        for enemy in get_active_enemies(self.enemy_agents):
            enemy.initiative = enemy.roll_initiative()
            entries.append((enemy.initiative, enemy))
            logger.debug(f"{enemy.name}: Initiative {enemy.initiative}")

        return entries

    async def declare_single_enemy(
        self,
        enemy: 'EnemyAgent',
        player_agents: List[Any],
        available_tokens: List[str],
        llm_client: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Generate declaration for a single enemy during declaration phase.
        Used for interleaved declarations in initiative order.

        Args:
            enemy: The enemy to generate declaration for
            player_agents: List of PC agents
            available_tokens: Unclaimed tactical tokens
            llm_client: LLM client for generating responses

        Returns:
            Declaration dict for logging, or None if failed
        """
        if not self.enabled or not enemy.is_active:
            return None

        # Override: Panicked enemies auto-declare based on morale behavior
        if enemy.is_panicked:
            panicked_action = _get_panicked_action(enemy)
            logger.info(f"{enemy.name} is panicked - auto-declaring {panicked_action} action")

            if panicked_action == "Surrender":
                reasoning = f"Panicked due to {enemy.panic_trigger} - surrendering (morale behavior: surrender_if_cornered)"
                intel = "Surrendering - morale broken"
            else:
                reasoning = f"Panicked due to {enemy.panic_trigger} - attempting to flee combat"
                intel = "Attempting to escape - morale broken"

            parsed = EnemyDeclaration(
                agent_id=enemy.agent_id,
                character_name=enemy.name,
                initiative=enemy.initiative,
                major_action=panicked_action,
                target="None",
                weapon="None",
                defence_token=None,
                minor_action=None,
                token_target=None,
                shared_intel=intel,
                reasoning=reasoning
            )

            self.enemy_declarations[enemy.agent_id] = parsed

            logger.info(f"{enemy.name} declared: FLEE (panicked: {enemy.panic_trigger})")

            return {
                'agent_id': enemy.agent_id,
                'character_name': enemy.name,
                'initiative': enemy.initiative,
                'major_action': parsed.major_action,
                'target': parsed.target,
                'reasoning': parsed.reasoning
            }

        active_enemies = get_active_enemies(self.enemy_agents)

        logger.debug(f"Generating declaration for {enemy.name} (ID: {enemy.agent_id})")

        # Check if free targeting mode is enabled
        config = self.shared_state.session_config if self.shared_state else {}
        enemy_config = config.get('enemy_agent_config', {})
        free_targeting = enemy_config.get('free_targeting_mode', True)  # Default: enabled

        # Get target ID mapper if in free targeting mode
        target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state and free_targeting else None

        # Inject situation history for prompt generation
        if self.shared_state and hasattr(self.shared_state, 'round_synthesis_history'):
            enemy._situation_history = self.shared_state.round_synthesis_history[-3:]
        else:
            enemy._situation_history = None

        # Generate tactical prompt
        from .enemy_prompts import generate_tactical_prompt

        # Collect recent action narrations from player agents (filtered by awareness)
        recent_narrations = []
        for player_agent in player_agents:
            if hasattr(player_agent, 'recent_narrations') and player_agent.recent_narrations:
                # Filter narrations based on what this enemy can see
                visible_narrations = filter_narrations_for_agent(
                    enemy.agent_id,
                    player_agent.recent_narrations
                )
                # Convert NarrationEntry to text for prompt
                for narration in visible_narrations:
                    narration_text = narration.text if isinstance(narration, NarrationEntry) else narration
                    recent_narrations.append(narration_text)

        prompt = generate_tactical_prompt(
            enemy=enemy,
            player_agents=player_agents,
            enemy_agents=active_enemies,
            shared_intel=self.shared_intel,
            available_tokens=available_tokens,
            current_round=self.current_round,
            target_id_mapper=target_id_mapper,
            free_targeting=free_targeting,
            recent_narrations=recent_narrations if recent_narrations else None
        )

        # Get LLM response
        try:
            response = await llm_client.generate_async(
                prompt=prompt,
                temperature=1.0,
                max_tokens=4000  # Matches DM/player defaults, prevents OpenAI token limit errors
            )
            declaration_text = response.get('content', '')

            # Parse declaration
            parsed = parse_enemy_declaration(declaration_text, enemy)

            if parsed:
                self.enemy_declarations[enemy.agent_id] = parsed

                # Update enemy defence token
                enemy.defence_token = parsed.defence_token

                # Add to shared intel
                if parsed.shared_intel:
                    self.shared_intel.add_intel(
                        enemy.name,
                        parsed.shared_intel,
                        self.current_round
                    )

                logger.info(
                    f"{enemy.name} declared: {parsed.major_action} "
                    f"(target: {parsed.target}, reasoning: {parsed.reasoning[:50]}...)"
                )

                # Return declaration dict for logging
                return {
                    'agent_id': enemy.agent_id,
                    'character_name': enemy.name,
                    'initiative': enemy.initiative,
                    'major_action': parsed.major_action,
                    'target': parsed.target,
                    'reasoning': parsed.reasoning
                }
            else:
                logger.warning(f"{enemy.name}: Failed to parse declaration")
                return None

        except Exception as e:
            logger.error(f"{enemy.name}: Error generating declaration: {e}")
            return None

    async def _generate_enemy_decision_structured(self, enemy, prompt: str):
        """
        Generate enemy tactical decision using Pydantic AI structured output (Phase 4).
        Returns EnemyDeclaration if structured output succeeds, or None to fall back to legacy.
        """
        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug(f"Enemy {enemy.name}: No llm_provider available, will use legacy text parsing")
            return None

        try:
            from .schemas.enemy_decision import EnemyDecision
            # EnemyDeclaration is defined in this file at line 43, no import needed

            logger.debug(f"Enemy {enemy.name}: Attempting structured output for tactical decision")

            # Generate structured decision using Pydantic AI
            # Note: LLM only generates tactical fields, we populate identity after
            system_prompt = f"You are {enemy.name}, an enemy combatant making tactical decisions."

            enemy_decision: EnemyDecision = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=EnemyDecision,
                system_prompt=system_prompt,
                max_tokens=4000,  # Matches DM/player defaults, prevents OpenAI token limit errors
                temperature=1.0,
                llm_logger=self.llm_logger,
                current_round=self.current_round
            )

            # Log the raw decision object for debugging
            logger.debug(f"Enemy {enemy.name} raw decision object: {enemy_decision}")
            logger.debug(f"Enemy {enemy.name} decision type: {type(enemy_decision)}")

            if enemy_decision is None:
                logger.error(f"Enemy {enemy.name}: Structured output returned None!")
                return None

            logger.debug(f"✓ Enemy {enemy.name} structured decision: major_action={enemy_decision.major_action}, target={enemy_decision.target}")

            # Convert EnemyDecision (Pydantic) to EnemyDeclaration (legacy format)
            # Use enemy object's identity fields directly (not from LLM output)
            enemy_declaration = EnemyDeclaration(
                agent_id=enemy.agent_id,
                character_name=enemy.name,
                initiative=enemy.initiative,
                major_action=enemy_decision.major_action,
                minor_action=enemy_decision.minor_action or "None",
                target=enemy_decision.target or "None",
                weapon=enemy_decision.weapon or "None",
                defence_token=enemy_decision.defence_token or "None",
                token_target=enemy_decision.token_target or "None",
                reasoning=enemy_decision.tactical_reasoning,
                shared_intel=enemy_decision.shared_intel
            )

            logger.debug(f"✓ Enemy {enemy.name} converted to EnemyDeclaration: {enemy_declaration.major_action}")
            return enemy_declaration

        except Exception as e:
            import traceback
            logger.error(f"Enemy {enemy.name}: Structured output failed: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def declare_actions(
        self,
        player_agents: List[Any],
        available_tokens: List[str],
        llm_client: Any
    ) -> List[Dict[str, Any]]:
        """
        Generate enemy declarations during declaration phase.

        Args:
            player_agents: List of PC agents
            available_tokens: Unclaimed tactical tokens
            llm_client: LLM client for generating responses

        Returns:
            List of declaration dicts for logging
        """
        logger.debug(f"declare_actions called: enabled={self.enabled}, enemy_count={len(self.enemy_agents)}")

        if not self.enabled:
            return []

        active_enemies = get_active_enemies(self.enemy_agents)
        logger.debug(f"Active enemies count: {len(active_enemies)}")

        if not active_enemies:
            logger.warning("No active enemies found in declare_actions")
            return []

        declarations = []

        for enemy in active_enemies:
            logger.debug(f"Generating declaration for {enemy.name} (ID: {enemy.agent_id})")

            # Collect context once for all prompt variants
            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
            free_targeting = self.shared_state.config.get('free_targeting_mode', True) if self.shared_state else True
            recent_narrations = []
            for player_agent in player_agents:
                if hasattr(player_agent, 'recent_narrations') and player_agent.recent_narrations:
                    recent_narrations.extend(player_agent.recent_narrations)

            # Try structured output first (Phase 4: Pydantic AI migration)
            parsed = None
            logger.debug(f"Enemy {enemy.name}: llm_provider check - hasattr={hasattr(self, 'llm_provider')}, value={getattr(self, 'llm_provider', 'NOT_SET')}, is_none={self.llm_provider is None if hasattr(self, 'llm_provider') else 'N/A'}")
            if hasattr(self, 'llm_provider') and self.llm_provider is not None:
                try:
                    # Use structured-output-compatible prompt (no text format instructions)
                    from .enemy_prompts import generate_tactical_prompt_structured

                    structured_prompt = generate_tactical_prompt_structured(
                        enemy=enemy,
                        player_agents=player_agents,
                        enemy_agents=active_enemies,
                        shared_intel=self.shared_intel,
                        available_tokens=available_tokens,
                        current_round=self.current_round,
                        target_id_mapper=target_id_mapper,
                        free_targeting=free_targeting,
                        recent_narrations=recent_narrations if recent_narrations else None
                    )

                    parsed = await self._generate_enemy_decision_structured(enemy, structured_prompt)
                    if parsed:
                        logger.debug(f"✓ Enemy {enemy.name} structured decision: {parsed.major_action}")
                except Exception as e:
                    logger.warning(f"Enemy {enemy.name}: Structured output failed ({e}), falling back to legacy")

            # Legacy text parsing fallback
            if not parsed:
                try:
                    # Generate legacy prompt with text format instructions
                    from .enemy_prompts import generate_tactical_prompt

                    legacy_prompt = generate_tactical_prompt(
                        enemy=enemy,
                        player_agents=player_agents,
                        enemy_agents=active_enemies,
                        shared_intel=self.shared_intel,
                        available_tokens=available_tokens,
                        current_round=self.current_round,
                        target_id_mapper=target_id_mapper,
                        free_targeting=free_targeting,
                        recent_narrations=recent_narrations if recent_narrations else None
                    )

                    response = await llm_client.generate_async(
                        prompt=legacy_prompt,
                        temperature=1.0,
                        max_tokens=4000  # Matches DM/player defaults, prevents OpenAI token limit errors
                    )
                    declaration_text = response.get('content', '')

                    # Parse declaration
                    parsed = parse_enemy_declaration(declaration_text, enemy)
                except Exception as e:
                    logger.error(f"{enemy.name}: Error generating declaration: {e}")

            # Process the parsed declaration (whether from structured or legacy)
            if parsed:
                self.enemy_declarations[enemy.agent_id] = parsed

                # Update enemy defence token
                enemy.defence_token = parsed.defence_token

                # Add to shared intel
                if parsed.shared_intel:
                    self.shared_intel.add_intel(
                        enemy.name,
                        parsed.shared_intel,
                        self.current_round
                    )

                # Log declaration
                declarations.append({
                    'agent_id': enemy.agent_id,
                    'character_name': enemy.name,
                    'initiative': enemy.initiative,
                    'major_action': parsed.major_action,
                    'target': parsed.target,
                    'reasoning': parsed.reasoning
                })

                logger.info(
                    f"{enemy.name} declared: {parsed.major_action} "
                    f"(target: {parsed.target}, reasoning: {parsed.reasoning[:50]}...)"
                )
            else:
                logger.warning(f"{enemy.name}: Failed to parse declaration")

        return declarations

    def execute_enemy_action(
        self,
        enemy_id: str,
        player_agents: List[Any],
        mechanics_engine: Any,
        resolution_state: Optional[ResolutionState] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a single enemy action during resolution phase.

        Args:
            enemy_id: Enemy agent ID
            player_agents: List of PC agents
            mechanics_engine: Mechanics engine for rolls
            resolution_state: Resolution state tracker (for declare/resolve cycle)

        Returns:
            Action result dict or None
        """
        if not self.enabled:
            return None

        declaration = self.enemy_declarations.get(enemy_id)
        if not declaration:
            logger.warning(f"No declaration for enemy {enemy_id}")
            return None

        enemy = next((e for e in self.enemy_agents if e.agent_id == enemy_id), None)
        if not enemy or not enemy.is_active:
            return None

        # Create resolution state if not provided
        if resolution_state is None:
            resolution_state = ResolutionState()

        # Execute based on major action
        major_action = declaration.major_action.lower()

        # Handle "None" as hold position / no major action
        if major_action.lower() == 'none':
            return {
                'enemy_id': enemy_id,
                'character_name': enemy.name,
                'action': 'hold',
                'result': 'success',
                'narration': f"{enemy.name} holds position at {enemy.position}"
            }

        if 'flee' in major_action or 'escape' in major_action:
            return self._execute_flee(enemy, declaration, mechanics_engine)
        elif 'attack' in major_action:
            return self._execute_attack(enemy, declaration, player_agents, mechanics_engine, resolution_state)
        elif 'suppress' in major_action:
            return self._execute_suppress(enemy, declaration, player_agents, mechanics_engine, resolution_state)
        elif 'claim' in major_action or 'token' in major_action:
            return self._execute_claim_token(enemy, declaration, resolution_state)
        elif 'shift' in major_action or 'push' in major_action:
            # Handle both Shift and Push_Through movements
            return self._execute_movement(enemy, declaration, resolution_state)
        elif 'charge' in major_action:
            return self._execute_charge(enemy, declaration, player_agents, mechanics_engine, resolution_state)
        elif 'retreat' in major_action:
            return self._execute_retreat(enemy, declaration, resolution_state)
        elif 'dialogue' in major_action:
            return self._execute_dialogue(enemy, declaration, mechanics_engine)
        elif 'wait' in major_action:
            return self._execute_wait(enemy, declaration, mechanics_engine)
        elif 'surrender' in major_action:
            return self._execute_surrender(enemy, declaration, resolution_state)
        elif 'grenade' in major_action or 'throw' in major_action:
            return self._execute_grenade(enemy, declaration, player_agents, mechanics_engine, resolution_state)
        else:
            logger.warning(f"{enemy.name}: Unknown action '{major_action}'")
            return {
                'enemy_id': enemy_id,
                'character_name': enemy.name,
                'action': major_action,
                'result': 'unknown action',
                'narration': f"{enemy.name} attempts {major_action}"
            }

    def _execute_attack(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any,
        resolution_state: ResolutionState
    ) -> Dict[str, Any]:
        """Execute enemy attack action."""
        target_id = declaration.target
        weapon_name = declaration.weapon

        # Resolve target ID (free targeting mode support)
        target = None
        if target_id and target_id.startswith('tgt_'):
            # Free targeting mode - resolve through target mapper
            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
            if target_id_mapper and target_id_mapper.enabled:
                target_entity = target_id_mapper.resolve_target(target_id)

                # Verify target type and apply faction rules
                if target_entity and target_id_mapper.is_player(target_id):
                    # Faction-aware: check if player is from an allied faction
                    from .faction_utils import are_factions_allied
                    target_info = target_id_mapper.get_combatant_info(target_id)
                    target_faction = target_info.get('faction', 'Unknown') if target_info else 'Unknown'
                    if are_factions_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} ({enemy.faction}) attempted to attack allied player {target_id} ({target_faction})")
                        return {
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'action': 'attack',
                            'result': 'invalid target',
                            'narration': f"{enemy.name} cannot attack allied {target_faction} forces"
                        }
                    else:
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) attacking hostile player {target_id} ({target_faction})")
                elif target_entity and target_id_mapper.is_enemy(target_id):
                    # Faction-aware: hostile factions can attack each other
                    from .faction_utils import are_factions_allied as are_allied
                    target_faction = getattr(target_entity, 'faction', 'Unknown')
                    if are_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} attempted to attack allied enemy {target_id} ({target_faction})")
                        return {
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'action': 'attack',
                            'result': 'invalid target',
                            'narration': f"{enemy.name} cannot attack allied {target_faction} forces"
                        }
                    else:
                        # Hostile faction - allow attack
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) attacking hostile enemy {target_entity.name} ({target_faction})")
                elif target_entity:
                    # NPC or other entity type - allow targeting
                    target = target_entity
        else:
            # Legacy mode - direct agent_id match
            target = next((p for p in player_agents if p.agent_id == target_id), None)

        if not target:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'attack',
                'result': 'target not found',
                'narration': f"{enemy.name} attacks but target has moved"
            }

        # Validate attack prerequisites
        can_proceed, failure_reason = ActionValidator.can_attack(
            enemy.agent_id,
            target_id,
            resolution_state
        )

        if not can_proceed:
            target_name = target.name if hasattr(target, 'name') else str(target_id)
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'attack',
                failure_reason,
                target_name
            )
            logger.info(f"Attack invalidated: {enemy.name} -> {target_name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'attack',
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        # Find weapon
        if weapon_name:
            weapon = next((w for w in enemy.weapons if w.name.lower() == weapon_name.lower()), None)
        else:
            weapon = None

        if not weapon:
            weapon = enemy.weapons[0] if enemy.weapons else None

        if not weapon:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'attack',
                'result': 'no weapon',
                'narration': f"{enemy.name} has no weapon to attack with"
            }

        # Calculate range penalty
        try:
            target_position = Position.from_string(str(target.position if hasattr(target, 'position') else "Near-PC"))
            range_name, range_penalty = enemy.position.calculate_range(target_position)
        except:
            range_name, range_penalty = "Unknown", 0

        # Roll attack
        # YAGS: Attribute × Skill + weapon attack + d20 + modifiers
        if weapon.skill == "Guns":
            attribute = enemy.attributes.get('Perception', 3)
        elif weapon.skill == "Melee":
            attribute = enemy.attributes.get('Dexterity', 3)
        else:  # Brawl
            attribute = enemy.attributes.get('Agility', 3)

        skill = enemy.skills.get(weapon.skill, 2)
        attack_roll = random.randint(1, 20)
        attack_total = (attribute * skill) + weapon.attack + attack_roll + range_penalty

        # Check if target has defence token on this enemy
        target_defence_token = getattr(target, 'defence_token', None)
        if target_defence_token == enemy.agent_id:
            attack_total -= 2  # Target watching this enemy
            defence_note = "(target watching -2)"
        else:
            attack_total += 2  # Flanking bonus
            defence_note = "(flanking +2)"

        # Placeholder: Compare to target defence (would need target's defence roll)
        # For now, use passive defence of 15 (YAGS standard)
        target_defence = 15  # Simplified
        hit = attack_total >= target_defence

        target_name = target.name if hasattr(target, 'name') else str(target_id)

        result = {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'attack',
            'target': target_name,
            'weapon': weapon.name,
            'range': range_name,
            'hit': hit,
            'attack_roll': attack_total,
            'narration': f"{enemy.name} attacks {target_name} with {weapon.name}"
        }

        if hit:
            # Roll damage
            strength = enemy.attributes.get('Strength', 3)
            damage_roll = random.randint(1, 20)
            base_damage = strength + weapon.damage + damage_roll

            # Combat balance: Reduce enemy damage by 15% to prevent one-shots while avoiding stalemate
            total_damage = int(base_damage * 0.85)

            result['damage'] = total_damage

            # Apply damage to target (if target has health tracking)
            if hasattr(target, 'health') and hasattr(target, 'soak'):
                damage_dealt = max(0, total_damage - target.soak)
                result['damage_dealt'] = damage_dealt
                # Start building clearer narration: Attacker HIT Target with Weapon for X damage
                result['narration'] = f"{enemy.name} HIT {target_name} with {weapon.name} for {total_damage} damage ({damage_dealt} after soak)"

                # Track damage for round summary (only for PC targets)
                is_pc_target = hasattr(target, 'character_state')
                if is_pc_target and self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_player_damage_taken(damage_dealt)

                # Apply damage based on weapon type (YAGS damage types)
                from .mechanics import apply_stun_damage, apply_wound_damage, apply_mixed_damage
                damage_type = weapon.damage_type
                damage_result = None

                if damage_dealt > 0:
                    if damage_type == "stun":
                        damage_result = apply_stun_damage(target, damage_dealt)
                        logger.info(f"{target_name} took {damage_result['stuns_dealt']} stuns ({damage_result['old_stuns']} → {damage_result['new_stuns']}) - {damage_result['effect']['name']}")
                        result['damage_type'] = 'stun'
                        result['stuns_dealt'] = damage_result['stuns_dealt']
                        # Add stun info to narration
                        result['narration'] += f" - {target_name} took {damage_result['stuns_dealt']} stuns ({damage_result['effect']['name']})"
                    elif damage_type == "wound":
                        damage_result = apply_wound_damage(target, damage_dealt)
                        # Only log if actual wounds were dealt (not just HP damage)
                        if damage_result['wounds_dealt'] > 0:
                            logger.info(f"{target_name} took {damage_result['wounds_dealt']} wounds ({damage_result['old_wounds']} → {damage_result['new_wounds']}) - {damage_result['effect']['name']}")
                        result['damage_type'] = 'wound'
                        result['wounds_dealt'] = damage_result['wounds_dealt']
                        # Add wound info to narration
                        result['narration'] += f" - {target_name} took {damage_result['wounds_dealt']} wounds ({damage_result['effect']['name']})"
                    elif damage_type == "mixed":
                        damage_result = apply_mixed_damage(target, damage_dealt)
                        logger.info(f"{target_name} took {damage_result['stuns_dealt']} stuns + {damage_result['wounds_dealt']} wounds (mixed)")
                        result['damage_type'] = 'mixed'
                        result['stuns_dealt'] = damage_result['stuns_dealt']
                        result['wounds_dealt'] = damage_result['wounds_dealt']
                        # Add mixed damage info to narration (mixed has separate stun_effect and wound_effect)
                        stun_status = damage_result['stun_effect']['name']
                        wound_status = damage_result['wound_effect']['name']
                        result['narration'] += f" - {target_name} took {damage_result['stuns_dealt']} stuns + {damage_result['wounds_dealt']} wounds ({stun_status}/{wound_status})"

                # Mark target as defeated if killed or unconscious
                # Check stun KO FIRST (stuns >= 6 = Beaten/unconscious, independent of wounds)
                is_stun_ko = (damage_result and damage_result.get('unconscious_check_needed')
                              and damage_type == "stun")
                if is_stun_ko:
                    # Stun KO — non-lethal incapacitation (bypass wound-based death save)
                    result['narration'] += f" - {target_name} KNOCKED UNCONSCIOUS (stun)"
                    logger.info(f"{target_name} knocked unconscious by stun damage from {enemy.name}")
                    resolution_state.mark_incapacitated(target_id)
                    result['target_defeated'] = True
                elif target.health <= 0 or (damage_result and damage_result.get('unconscious_check_needed')):
                    # Wound/mixed KO — check death saves
                    if hasattr(target, 'check_death_save'):
                        alive, status = target.check_death_save()

                        if not alive:
                            # Player died - mark as defeated
                            result['narration'] += f" - {target_name} KILLED"
                            logger.warning(f"{target_name} KILLED by {enemy.name}")
                            resolution_state.mark_defeated(target_id)
                            result['target_defeated'] = True
                        elif status == "unconscious":
                            # Player unconscious - mark as defeated (can't act)
                            result['narration'] += f" - {target_name} UNCONSCIOUS"
                            logger.info(f"{target_name} falls unconscious")
                            resolution_state.mark_defeated(target_id)
                            result['target_defeated'] = True
                        elif status == "conscious":
                            # Player critically wounded but still fighting - NOT defeated
                            result['narration'] += f" - {target_name} CRITICALLY WOUNDED (still conscious)"
                            logger.info(f"{target_name} critically wounded but fighting on")
                            # DO NOT mark as defeated - they can still act!
                            result['target_defeated'] = False
                    else:
                        # No death save system - just mark as defeated
                        result['narration'] += " - TARGET DEFEATED!"
                        resolution_state.mark_defeated(target_id)
                        result['target_defeated'] = True
                        # Deactivate enemy/NPC targets
                        if hasattr(target, 'is_active'):
                            target.is_active = False
                        logger.info(f"{enemy.name} defeated {target.name if hasattr(target, 'name') else target_id}")
        else:
            result['narration'] += f" - MISS ({attack_total} vs defence {target_defence})"

        # Log combat action to JSONL for ML training
        if mechanics_engine and hasattr(mechanics_engine, 'jsonl_logger') and mechanics_engine.jsonl_logger:
            # Build attack roll dict
            attack_roll_data = {
                "attr": "Perception" if weapon.skill == "Guns" else ("Dexterity" if weapon.skill == "Melee" else "Agility"),
                "attr_val": attribute,
                "skill": weapon.skill,
                "skill_val": skill,
                "weapon_bonus": weapon.attack,
                "range_penalty": range_penalty,
                "d20": attack_roll,
                "total": attack_total,
                "dc": target_defence,
                "hit": hit,
                "margin": attack_total - target_defence
            }

            # Build damage roll dict (if hit)
            damage_roll_data = None
            wounds_dealt_count = 0
            stuns_dealt_count = 0
            if hit and hasattr(target, 'soak'):
                damage_roll_data = {
                    "strength": strength,
                    "weapon_dmg": weapon.damage,
                    "d20": damage_roll,
                    "base_damage": base_damage,
                    "combat_balance_modifier": 0.85,
                    "total": total_damage,
                    "soak": target.soak,
                    "dealt": damage_dealt,
                    "damage_type": weapon.damage_type
                }
                # Get actual damage dealt from result
                wounds_dealt_count = result.get('wounds_dealt', 0)
                stuns_dealt_count = result.get('stuns_dealt', 0)

            # Build defender state dict
            defender_state = None
            if hasattr(target, 'health'):
                defender_state = {
                    "health": target.health,
                    "max_health": getattr(target, 'max_health', None),
                    "wounds": getattr(target, 'wounds', 0),
                    "stuns": getattr(target, 'stuns', 0),
                    "alive": target.health > 0,
                    "status": status if hit and target.health <= 0 and hasattr(target, 'check_death_save') else "active"
                }

            mechanics_engine.jsonl_logger.log_combat_action(
                round_num=mechanics_engine.current_round if mechanics_engine else self.current_round,
                attacker_id=enemy.agent_id,
                attacker_name=enemy.name,
                defender_id=self._get_agent_id(target, target_id),
                defender_name=self._get_agent_name(target, target_id),
                weapon=weapon.name,
                attack_roll=attack_roll_data,
                damage_roll=damage_roll_data,
                wounds_dealt=wounds_dealt_count,
                defender_state_after=defender_state
            )

        return result

    def _execute_suppress(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any,
        resolution_state: ResolutionState
    ) -> Dict[str, Any]:
        """
        Execute enemy Suppress action.

        Suppress (Tactical Module v1.2.3):
        - Requires weapon with RoF ≥ 3
        - On successful hit: target must choose:
          * Dive: immediately shift 1 band + lose Cover token if held
          * Hunker Down: suffer -4 to all attack and defense rolls until next turn
        """
        target_id = declaration.target
        weapon_name = declaration.weapon

        # Resolve target ID (free targeting mode support)
        target = None
        if target_id and target_id.startswith('tgt_'):
            # Free targeting mode - resolve through target mapper
            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
            if target_id_mapper and target_id_mapper.enabled:
                target_entity = target_id_mapper.resolve_target(target_id)

                # Verify target type and apply faction rules
                if target_entity and target_id_mapper.is_player(target_id):
                    # Faction-aware: check if player is from an allied faction
                    from .faction_utils import are_factions_allied
                    target_info = target_id_mapper.get_combatant_info(target_id)
                    target_faction = target_info.get('faction', 'Unknown') if target_info else 'Unknown'
                    if are_factions_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} ({enemy.faction}) attempted to suppress allied player {target_id} ({target_faction})")
                        return {
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'action': 'suppress',
                            'result': 'invalid target',
                            'narration': f"{enemy.name} cannot suppress allied {target_faction} forces"
                        }
                    else:
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) suppressing hostile player {target_id} ({target_faction})")
                elif target_entity and target_id_mapper.is_enemy(target_id):
                    # Faction-aware: hostile factions can suppress each other
                    from .faction_utils import are_factions_allied as are_allied
                    target_faction = getattr(target_entity, 'faction', 'Unknown')
                    if are_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} attempted to suppress allied enemy {target_id} ({target_faction})")
                        return {
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'action': 'suppress',
                            'result': 'invalid target',
                            'narration': f"{enemy.name} cannot suppress allied {target_faction} forces"
                        }
                    else:
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) suppressing hostile enemy {target_entity.name} ({target_faction})")
                elif target_entity:
                    # NPC or other entity type - allow targeting
                    target = target_entity
        else:
            # Legacy mode - direct agent_id match
            target = next((p for p in player_agents if p.agent_id == target_id), None)

        if not target:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'suppress',
                'result': 'target not found',
                'narration': f"{enemy.name} tries to suppress but target has moved"
            }

        # Validate suppress prerequisites
        can_proceed, failure_reason = ActionValidator.can_attack(
            enemy.agent_id,
            target_id,
            resolution_state
        )

        if not can_proceed:
            target_name = target.name if hasattr(target, 'name') else str(target_id)
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'suppress',
                failure_reason,
                target_name
            )
            logger.info(f"Suppress invalidated: {enemy.name} -> {target_name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'suppress',
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        # Find weapon
        if weapon_name:
            weapon = next((w for w in enemy.weapons if w.name.lower() == weapon_name.lower()), None)
        else:
            weapon = None

        if not weapon:
            weapon = enemy.weapons[0] if enemy.weapons else None

        if not weapon:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'suppress',
                'result': 'no weapon',
                'narration': f"{enemy.name} has no weapon to suppress with"
            }

        # Check if weapon has sufficient RoF (Rate of Fire ≥ 3)
        weapon_rof = getattr(weapon, 'rate_of_fire', 0)
        if weapon_rof < 3:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'suppress',
                'result': 'insufficient_rof',
                'narration': f"{enemy.name}'s {weapon.name} lacks sufficient rate of fire for suppression (RoF {weapon_rof} < 3)"
            }

        # Roll suppression attack (same as attack roll)
        if weapon.skill == "Guns":
            attribute = enemy.attributes.get('Perception', 3)
        elif weapon.skill == "Melee":
            attribute = enemy.attributes.get('Dexterity', 3)
        else:  # Brawl
            attribute = enemy.attributes.get('Agility', 3)

        skill = enemy.skills.get(weapon.skill, 2)
        attack_roll = random.randint(1, 20)

        # Calculate range penalty
        try:
            target_position = Position.from_string(str(target.position if hasattr(target, 'position') else "Near-PC"))
            range_name, range_penalty = enemy.position.calculate_range(target_position)
        except:
            range_name, range_penalty = "Unknown", 0

        attack_total = (attribute * skill) + weapon.attack + attack_roll + range_penalty

        # Check defence token
        target_defence_token = getattr(target, 'defence_token', None)
        if target_defence_token == enemy.agent_id:
            attack_total -= 2  # Target watching this enemy
            defence_note = "(target watching -2)"
        else:
            attack_total += 2  # Flanking bonus
            defence_note = "(flanking +2)"

        # Check hit (simplified)
        target_defence = 15
        hit = attack_total >= target_defence

        result = {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'suppress',
            'target': target.name if hasattr(target, 'name') else str(target_id),
            'weapon': weapon.name,
            'range': range_name,
            'hit': hit,
            'attack_roll': attack_total,
            'narration': f"{enemy.name} lays down suppressive fire on {target.name if hasattr(target, 'name') else 'target'} with {weapon.name}"
        }

        if hit:
            # Target must choose: Dive or Hunker Down
            # For now, we'll apply Hunker Down effect (player can override via narration)
            # Apply -4 penalty to target for next round

            # Store debuff effect (requires debuff tracking system)
            target_name = target.name if hasattr(target, 'name') else str(target_id)
            logger.info(f"{target_name} suppressed by {enemy.name} - target must Dive or Hunker Down")

            result['narration'] += f" - SUPPRESSED! {target_name} must choose: Dive (shift 1 band + lose Cover) OR Hunker Down (-4 to attacks/defense until next turn)"
            result['effect'] = 'suppressed'
            result['choices'] = ['Dive', 'Hunker Down']
        else:
            result['narration'] += f" - MISS ({attack_total} vs defence {target_defence})"

        # Log suppress action to JSONL
        if mechanics_engine and hasattr(mechanics_engine, 'jsonl_logger') and mechanics_engine.jsonl_logger:
            attack_roll_data = {
                "attribute": attribute,
                "skill": skill,
                "weapon_bonus": weapon.attack,
                "d20": attack_roll,
                "range_penalty": range_penalty,
                "total": attack_total,
                "defence": target_defence,
                "hit": hit
            }
            mechanics_engine.jsonl_logger.log_combat_action(
                round_num=mechanics_engine.current_round if mechanics_engine else self.current_round,
                attacker_id=enemy.agent_id,
                attacker_name=enemy.name,
                defender_id=self._get_agent_id(target, target_id),
                defender_name=self._get_agent_name(target, target_id),
                weapon=f"{weapon.name} (suppress)",
                attack_roll=attack_roll_data,
                damage_roll=None,
                wounds_dealt=0,
                defender_state_after=None
            )

        return result

    def _execute_claim_token(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        resolution_state: ResolutionState
    ) -> Dict[str, Any]:
        """Execute tactical token claim action."""
        token_name = declaration.token_target or declaration.target or "unknown_token"

        # Validate token claim prerequisites
        can_proceed, failure_reason = ActionValidator.can_claim_token(
            enemy.agent_id,
            token_name,
            resolution_state
        )

        if not can_proceed:
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'claim_token',
                failure_reason
            )
            logger.info(f"Token claim invalidated: {enemy.name} -> {token_name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'claim_token',
                'token': token_name,
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        # Attempt to claim the token
        success = resolution_state.claim_token(token_name, enemy.agent_id)

        if success:
            logger.info(f"{enemy.name} claimed {token_name}")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'claim_token',
                'token': token_name,
                'result': 'success',
                'narration': f"✓ {enemy.name} claims {token_name}"
            }
        else:
            # Token was claimed by someone else (race condition)
            holder = resolution_state.get_token_holder(token_name)
            logger.info(f"{enemy.name} failed to claim {token_name} - already taken by {holder}")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'claim_token',
                'token': token_name,
                'result': 'already_taken',
                'holder': holder,
                'narration': f"❌ {enemy.name} cannot claim {token_name} - {holder} claimed it first"
            }

    def _execute_movement(self, enemy: EnemyAgent, declaration: EnemyDeclaration, resolution_state: ResolutionState) -> Dict[str, Any]:
        """Execute enemy movement action."""
        # Validate movement prerequisites
        can_proceed, failure_reason = ActionValidator.can_move(
            enemy.agent_id,
            resolution_state
        )

        if not can_proceed:
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'movement',
                failure_reason
            )
            logger.info(f"Movement invalidated: {enemy.name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'movement',
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        old_position = str(enemy.position)

        # Parse movement from action
        action = declaration.major_action.lower()

        # Determine max shifts based on action type
        max_shifts = 0
        if 'shift_2' in action or 'shift 2' in action:
            max_shifts = 2  # Major: Shift 2 bands
        elif 'shift' in action and 'shift_2' not in action:
            max_shifts = 1  # Major: Shift 1 band
        elif declaration.minor_action and 'shift' in declaration.minor_action.lower():
            max_shifts = 1  # Minor: Shift 1 band
        elif 'push' in action:
            # Push through to opposite side
            enemy.position = enemy.position.push_through()
            new_position = str(enemy.position)
            resolution_state.record_position_change(enemy.agent_id, new_position)
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'movement',
                'old_position': old_position,
                'new_position': new_position,
                'narration': f"{enemy.name} moves from {old_position} to {new_position}"
            }

        # Execute shifts toward target if we have a valid movement
        if max_shifts > 0 and declaration.target:
            try:
                target_position = Position.from_string(declaration.target)

                # Check if we need to cross hemispheres (Enemy ↔ PC)
                needs_hemisphere_change = enemy.position.side != target_position.side

                if needs_hemisphere_change:
                    # Crossing hemispheres: move through center
                    # Path: Current → Engaged → Target
                    # This counts as multiple ring shifts
                    logger.info(f"{enemy.name} crossing hemisphere from {enemy.position.side} to {target_position.side} (target: {target_position})")

                    shifts_used = 0

                    # Step 1: Move toward center until we reach Engaged
                    while shifts_used < max_shifts and enemy.position.ring != "Engaged":
                        new_pos = enemy.position.shift_toward_center()
                        if new_pos:
                            enemy.position = new_pos
                            shifts_used += 1
                            logger.debug(f"  Shift {shifts_used}: moved to {enemy.position}")
                        else:
                            break

                    # Step 2: Cross to opposite hemisphere (costs 1 shift if not already at Engaged)
                    if shifts_used < max_shifts and enemy.position.side != target_position.side:
                        # Flip hemisphere
                        enemy.position = Position(ring=enemy.position.ring, side=target_position.side)
                        shifts_used += 1
                        logger.debug(f"  Shift {shifts_used}: crossed hemisphere to {enemy.position}")

                    # Step 3: Move away from center toward target ring
                    target_distance = self._distance_from_center(target_position)
                    current_distance = self._distance_from_center(enemy.position)

                    while shifts_used < max_shifts and current_distance < target_distance:
                        new_pos = enemy.position.shift_away_from_center()
                        if new_pos:
                            enemy.position = new_pos
                            shifts_used += 1
                            current_distance = self._distance_from_center(enemy.position)
                            logger.debug(f"  Shift {shifts_used}: moved to {enemy.position}")
                        else:
                            break

                    logger.info(f"{enemy.name} completed cross-hemisphere movement to {enemy.position} ({shifts_used} shifts used)")

                else:
                    # Same hemisphere - just adjust ring distance
                    current_distance = self._distance_from_center(enemy.position)
                    target_distance = self._distance_from_center(target_position)

                    # Calculate how many rings we need to move
                    rings_to_move = abs(target_distance - current_distance)

                    # Move up to max_shifts, but don't overshoot the target
                    actual_shifts = min(rings_to_move, max_shifts)

                    # Determine direction
                    if target_distance > current_distance:
                        # Moving away from center
                        for _ in range(actual_shifts):
                            new_pos = enemy.position.shift_away_from_center()
                            if new_pos:
                                enemy.position = new_pos
                    else:
                        # Moving toward center
                        for _ in range(actual_shifts):
                            new_pos = enemy.position.shift_toward_center()
                            if new_pos:
                                enemy.position = new_pos
            except Exception as e:
                logger.error(f"Failed to parse target position '{declaration.target}': {e}")
                # Fallback: shift toward center
                for _ in range(max_shifts):
                    new_pos = enemy.position.shift_toward_center()
                    if new_pos:
                        enemy.position = new_pos
        elif max_shifts > 0:
            # No target specified, default to toward center
            for _ in range(max_shifts):
                new_pos = enemy.position.shift_toward_center()
                if new_pos:
                    enemy.position = new_pos

        new_position = str(enemy.position)

        # Record position change in resolution state
        resolution_state.record_position_change(enemy.agent_id, new_position)

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'movement',
            'old_position': old_position,
            'new_position': new_position,
            'narration': f"{enemy.name} moves from {old_position} to {new_position}"
        }

    def _distance_from_center(self, position: Position) -> int:
        """
        Calculate distance from center (Engaged band).
        Returns: 0 for Engaged, 1 for Near, 2 for Far, 3 for Extreme
        """
        ring_distances = {
            "Engaged": 0,
            "Near": 1,
            "Far": 2,
            "Extreme": 3
        }
        return ring_distances.get(position.ring, 0)

    def _execute_charge(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any,
        resolution_state: ResolutionState
    ) -> Dict[str, Any]:
        """Execute enemy charge action (movement + attack)."""
        # Validate charge prerequisites (movement + attack)
        can_proceed, failure_reason = ActionValidator.can_move(
            enemy.agent_id,
            resolution_state
        )

        if not can_proceed:
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'charge',
                failure_reason
            )
            logger.info(f"Charge invalidated: {enemy.name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'charge',
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        # Move to engaged/melee with target
        old_position = str(enemy.position)

        # Resolve target ID (free targeting mode support)
        target = None
        target_id = declaration.target
        if target_id and target_id.startswith('tgt_'):
            # Free targeting mode - resolve through target mapper
            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
            if target_id_mapper and target_id_mapper.enabled:
                target_entity = target_id_mapper.resolve_target(target_id)

                # Verify target type and apply faction rules
                if target_entity and target_id_mapper.is_player(target_id):
                    # Faction-aware: check if player is from an allied faction
                    from .faction_utils import are_factions_allied
                    target_info = target_id_mapper.get_combatant_info(target_id)
                    target_faction = target_info.get('faction', 'Unknown') if target_info else 'Unknown'
                    if are_factions_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} ({enemy.faction}) attempted to charge allied player {target_id} ({target_faction})")
                    else:
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) charging hostile player {target_id} ({target_faction})")
                elif target_entity and target_id_mapper.is_enemy(target_id):
                    # Faction-aware: hostile factions can charge each other
                    from .faction_utils import are_factions_allied as are_allied
                    target_faction = getattr(target_entity, 'faction', 'Unknown')
                    if are_allied(enemy.faction, target_faction):
                        logger.warning(f"{enemy.name} attempted to charge allied enemy {target_id} ({target_faction})")
                    else:
                        target = target_entity
                        logger.info(f"{enemy.name} ({enemy.faction}) charging hostile enemy {target_entity.name} ({target_faction})")
                elif target_entity:
                    # NPC or other entity type - allow targeting
                    target = target_entity
        else:
            # Legacy mode - direct agent_id match
            target = next((p for p in player_agents if p.agent_id == target_id), None)

        if target:
            try:
                target_position = Position.from_string(str(getattr(target, 'position', "Near-PC")))
                # Move to same ring as target
                enemy.position = Position(ring=target_position.ring, side=target_position.side)
                resolution_state.record_position_change(enemy.agent_id, str(enemy.position))
            except:
                pass

        # Execute attack with charge bonus
        attack_result = self._execute_attack(enemy, declaration, player_agents, mechanics_engine, resolution_state)
        if attack_result.get('hit') and 'damage' in attack_result:
            attack_result['damage'] += 2  # Charge bonus
            attack_result['narration'] = f"{enemy.name} charges from {old_position} to {enemy.position} and attacks (+2 damage)"

        return attack_result

    def _execute_surrender(self, enemy: EnemyAgent, declaration: EnemyDeclaration, resolution_state: ResolutionState) -> Dict[str, Any]:
        """
        Execute enemy surrender action.

        Enemy has decided to surrender (morale broken, negotiation, overwhelming odds).
        This marks them for conversion to prisoner NPC in conversion check phase.
        """
        # Mark enemy as surrendered (will be converted to NPC prisoner by DM conversion check)
        enemy.is_active = False
        enemy.is_prisoner = True
        enemy.despawned_round = self.current_round

        # Mark in resolution state so conversion check knows they surrendered
        resolution_state.mark_defeated(enemy.agent_id)

        # Add to shared intel
        intel_msg = f"{enemy.name} surrendering - {declaration.reasoning[:100]}"
        resolution_state.add_shared_intel(intel_msg)

        logger.info(f"✓ {enemy.name} surrendered (will convert to prisoner NPC)")

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'surrender',
            'result': 'success',
            'narration': f"{enemy.name} lowers their weapon and surrenders",
            'surrender': True  # Signal for conversion check
        }

    def _execute_dialogue(self, enemy: EnemyAgent, declaration: EnemyDeclaration, mechanics_engine: Any) -> Dict[str, Any]:
        """Execute enemy dialogue action (speak, warn, demand, negotiate)."""
        dialogue = getattr(declaration, 'dialogue_content', None) or ''

        result = {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'dialogue',
            'result': 'success',
            'dialogue_content': dialogue,
            'narration': f'{enemy.name} speaks: "{dialogue}"' if dialogue else f'{enemy.name} attempts to communicate.'
        }

        # JSONL logging
        if mechanics_engine and hasattr(mechanics_engine, 'jsonl_logger') and mechanics_engine.jsonl_logger:
            mechanics_engine.jsonl_logger.log_enemy_action(
                round_num=self.current_round,
                enemy_id=enemy.agent_id,
                enemy_name=enemy.name,
                action_type='dialogue',
                result='success',
                narration=result['narration']
            )

        return result

    def _execute_wait(self, enemy: EnemyAgent, declaration: EnemyDeclaration, mechanics_engine: Any) -> Dict[str, Any]:
        """Execute enemy wait action (observe, hold position)."""
        result = {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'wait',
            'result': 'success',
            'narration': f'{enemy.name} holds position, observing.'
        }

        # JSONL logging
        if mechanics_engine and hasattr(mechanics_engine, 'jsonl_logger') and mechanics_engine.jsonl_logger:
            mechanics_engine.jsonl_logger.log_enemy_action(
                round_num=self.current_round,
                enemy_id=enemy.agent_id,
                enemy_name=enemy.name,
                action_type='wait',
                result='success',
                narration=result['narration']
            )

        return result

    def _execute_retreat(self, enemy: EnemyAgent, declaration: EnemyDeclaration, resolution_state: ResolutionState) -> Dict[str, Any]:
        """Execute enemy retreat action."""
        # Validate retreat prerequisites
        can_proceed, failure_reason = ActionValidator.can_move(
            enemy.agent_id,
            resolution_state
        )

        if not can_proceed:
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'retreat',
                failure_reason
            )
            logger.info(f"Retreat invalidated: {enemy.name} ({failure_reason})")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'retreat',
                'result': 'invalidated',
                'failure_reason': failure_reason,
                'narration': invalidation_msg
            }

        enemy.is_active = False
        enemy.despawned_round = self.current_round

        # Mark as defeated in resolution state (retreated = removed from combat)
        resolution_state.mark_defeated(enemy.agent_id)

        # Add to shared intel
        if declaration.shared_intel:
            self.shared_intel.add_intel(enemy.name, declaration.shared_intel, self.current_round)

        # Auto-advance Escape Route clock (voluntary retreat = more efficient)
        if self.shared_state and hasattr(self.shared_state, 'scene_clocks'):
            escape_clock = self.shared_state.scene_clocks.get('Escape Route')
            if escape_clock:
                advance = 3  # Voluntary retreat = efficient escape
                escape_clock.advance(advance)
                logger.info(f"{enemy.name} retreating (voluntary), advancing Escape Route: +{advance}")

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'retreat',
            'reason': declaration.reasoning,
            'narration': f"{enemy.name} retreats from combat: {declaration.reasoning}"
        }

    def _execute_flee(self, enemy: EnemyAgent, declaration: EnemyDeclaration, mechanics_engine: Any) -> Dict[str, Any]:
        """
        Execute panicked enemy flee attempt with Athletics check.

        Panicked enemies attempt to escape combat by making an Athletics check:
        - Roll: Agility × Athletics + d20 vs DC 15
        - Success: Enemy escapes (despawns)
        - Failure: Enemy pinned down, remains in combat
        """
        import random

        # Get enemy's Agility and Athletics skill
        agility = enemy.attributes.get('Agility', 3)
        athletics_skill = enemy.skills.get('Athletics', 0)

        # Make escape check: Agility × Athletics + d20 vs DC 15
        d20 = random.randint(1, 20)
        total = (agility * athletics_skill) + d20
        dc = 15
        success = total >= dc
        margin = total - dc

        logger.info(f"{enemy.name} flee check: {agility}×{athletics_skill}+{d20} = {total} vs DC {dc} - {'SUCCESS' if success else 'FAILED'}")

        if success:
            # Escape successful - despawn
            enemy.is_active = False
            enemy.despawned_round = self.current_round

            # Advance Escape Route clock if it exists
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics and mechanics.scene_clocks:
                    escape_clock = mechanics.scene_clocks.get('Escape Route')
                    if escape_clock:
                        advance = 2  # Panic flee = less efficient than voluntary retreat
                        escape_clock.advance(advance)
                        logger.info(f"{enemy.name} escaped, advancing Escape Route: +{advance}")

            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'flee',
                'result': 'success',
                'roll': {'agility': agility, 'athletics': athletics_skill, 'd20': d20, 'total': total, 'dc': dc, 'margin': margin},
                'narration': f"{enemy.name} (panicked) breaks away and flees! (Athletics check: {total} vs DC {dc})"
            }
        else:
            # Escape failed - enemy pinned down, still in combat
            # Clear panic so they can fight normally next turn
            enemy.is_panicked = False
            enemy.panic_trigger = None

            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'flee',
                'result': 'failure',
                'roll': {'agility': agility, 'athletics': athletics_skill, 'd20': d20, 'total': total, 'dc': dc, 'margin': margin},
                'narration': f"{enemy.name} (panicked) attempts to flee but is cut off! (Athletics check: {total} vs DC {dc}, failed by {abs(margin)})"
            }

    def _execute_grenade(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any,
        resolution_state: ResolutionState
    ) -> Dict[str, Any]:
        """Execute grenade throw (AoE attack)."""
        # Validate grenade prerequisites (attacker must be alive)
        if resolution_state.is_defeated(enemy.agent_id):
            invalidation_msg = generate_invalidation_message(
                enemy.name,
                'grenade',
                'attacker_defeated'
            )
            logger.info(f"Grenade invalidated: {enemy.name} (attacker_defeated)")
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'grenade',
                'result': 'invalidated',
                'failure_reason': 'attacker_defeated',
                'narration': invalidation_msg
            }

        target_location = declaration.target  # e.g., "Near-Enemy"

        # Find all PCs and enemies at target location
        affected = []

        # Check PCs (only include if not already defeated in this resolution phase)
        for pc in player_agents:
            try:
                pc_position = Position.from_string(str(getattr(pc, 'position', "Near-PC")))
                if str(pc_position) == target_location and not resolution_state.is_defeated(pc.agent_id):
                    affected.append(('PC', pc.name if hasattr(pc, 'name') else str(pc.agent_id), pc.agent_id))
            except:
                pass

        # Check enemies (only include if not already defeated)
        for ally in get_active_enemies(self.enemy_agents):
            if ally.agent_id != enemy.agent_id and str(ally.position) == target_location and not resolution_state.is_defeated(ally.agent_id):
                affected.append(('Enemy', ally.name, ally.agent_id))

        # Note: Full damage/save rolls would be implemented here
        # For now, just mark targets as affected
        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'grenade',
            'target_location': target_location,
            'affected': [(a[0], a[1]) for a in affected],  # (type, name) tuples
            'narration': f"{enemy.name} throws grenade at {target_location} (affects: {', '.join(a[1] for a in affected)})"
        }

    def check_morale_all(self) -> List[Dict[str, Any]]:
        """
        Check morale for all active enemies.

        Called during Entity Lifecycle phase (before synthesis) so DM can narrate
        morale breaks immediately.

        Returns:
            List of morale events (panicked, surrender)
        """
        if not self.enabled:
            return []

        events = []

        # Check morale for active enemies (skip if already panicked)
        active_enemies = list(get_active_enemies(self.enemy_agents))
        for enemy in active_enemies:
            # Skip morale check if already panicked
            if enemy.is_panicked:
                continue

            morale_trigger = None

            # Check HP below 25%
            if enemy.get_health_percentage() < 25:
                morale_trigger = "hp_below_25"
            # Check critical stuns (5+ stuns)
            elif getattr(enemy, 'stuns', 0) >= 5:
                morale_trigger = "critical_stuns"
            # NOTE: Removed "last_survivor" trigger - being outnumbered doesn't auto-panic

            if morale_trigger:
                morale_result = enemy.check_morale(trigger=morale_trigger)

                # Log morale check to JSONL
                if self.shared_state:
                    mechanics = self.shared_state.get_mechanics_engine()
                    if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                        mechanics.jsonl_logger.log_event(
                            'morale_check',
                            {
                                'character': enemy.name,
                                'trigger': morale_trigger,
                                'roll': {
                                    'willpower': morale_result['willpower'],
                                    'd20': morale_result['d20'],
                                    'total': morale_result['total'],
                                    'dc': morale_result['dc']
                                },
                                'result': 'success' if morale_result['success'] else 'failure',
                                'action': morale_result['action']
                            },
                            self.current_round
                        )

                # Handle morale failure - set panicked status instead of instant despawn
                if not morale_result['success']:
                    action = morale_result['action']
                    if action == "surrender":
                        # Surrender = instant (no escape check needed)
                        enemy.is_active = False
                        enemy.is_prisoner = True
                        enemy.despawned_round = self.current_round
                        events.append({
                            'type': 'surrender',
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'narration': f"{enemy.name} surrenders! Morale broken ({morale_trigger})"
                        })
                        logger.info(f"{enemy.name} surrendered (morale broken)")
                    elif action == "flee":
                        # Flee = set panicked status, will attempt escape on next turn
                        enemy.is_panicked = True
                        enemy.panic_trigger = morale_trigger
                        events.append({
                            'type': 'panicked',
                            'enemy_id': enemy.agent_id,
                            'character_name': enemy.name,
                            'narration': f"{enemy.name} morale breaks! They're panicked and will attempt to flee ({morale_trigger})"
                        })
                        logger.info(f"{enemy.name} is now panicked (morale broken: {morale_trigger})")

        return events

    def cleanup_round(self) -> List[Dict[str, Any]]:
        """
        Perform end-of-round cleanup.

        - Tick down debuff/status durations
        - Auto-despawn defeated enemies
        - Clear old shared intel
        - Generate loot suggestions

        NOTE: Morale checks have been moved to check_morale_all() which is called
        during Entity Lifecycle phase (before synthesis).

        Returns:
            List of cleanup events
        """
        if not self.enabled:
            return []

        events = []

        # Tick down debuff/status durations
        for enemy in get_active_enemies(self.enemy_agents):
            if hasattr(enemy, 'tick_debuffs'):
                enemy.tick_debuffs()

        # Auto-despawn defeated
        defeated = auto_despawn_defeated(self.enemy_agents, self.current_round)
        for enemy in defeated:
            loot = suggest_loot(enemy)

            events.append({
                'type': 'defeated',
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'loot': loot,
                'narration': f"{enemy.name} defeated! {loot}"
            })

            # Log enemy defeat to JSONL for ML training
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                    rounds_survived = enemy.despawned_round - enemy.spawned_round if enemy.despawned_round else 0
                    mechanics.jsonl_logger.log_enemy_defeat(
                        round_num=self.current_round,
                        enemy_id=enemy.agent_id,
                        enemy_name=enemy.name,
                        defeat_reason="killed" if enemy.health <= 0 else "defeated",
                        rounds_survived=rounds_survived
                    )

        # Clear old intel
        self.shared_intel.clear_old_intel(self.current_round, max_age=3)

        # Prune defeated enemies past grace period (memory cleanup)
        pruned = self.prune_defeated_enemies()
        if pruned:
            logger.info(f"Pruned {pruned} defeated enemy(ies) from list")

        # Increment round
        self.current_round += 1

        return events

    def prune_defeated_enemies(self, grace_rounds: int = 2) -> int:
        """Remove enemies inactive for >grace_rounds from the list.

        Not a game rule — just memory cleanup after logging is done.
        Defeated enemies stay for a grace period so the DM can reference
        them in narration, then get garbage-collected.

        Args:
            grace_rounds: How many rounds after defeat to keep the enemy.

        Returns:
            Number of enemies pruned.
        """
        surviving = []
        pruned_ids = []
        for enemy in self.enemy_agents:
            if enemy.is_active:
                surviving.append(enemy)
            elif (enemy.despawned_round is not None
                  and self.current_round - enemy.despawned_round > grace_rounds):
                pruned_ids.append(enemy.agent_id)
            else:
                surviving.append(enemy)  # Keep recently defeated or safety case (no despawned_round)

        # Clean up target mapper entries for pruned enemies
        if pruned_ids and self.shared_state:
            target_id_mapper = self.shared_state.get_target_id_mapper()
            if target_id_mapper:
                for agent_id in pruned_ids:
                    target_id = target_id_mapper.reverse_map.pop(agent_id, None)
                    if target_id:
                        target_id_mapper.target_id_map.pop(target_id, None)

        self.enemy_agents = surviving
        return len(pruned_ids)

    def get_active_enemy_count(self) -> int:
        """Get count of active enemy units."""
        return len(get_active_enemies(self.enemy_agents))

    def is_combat_active(self) -> bool:
        """Check if any enemies are still active."""
        return len(get_active_enemies(self.enemy_agents)) > 0


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'EnemyCombatManager',
    'EnemyDeclaration',
    'parse_enemy_declaration'
]
