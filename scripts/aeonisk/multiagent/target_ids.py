"""
Target ID Management for Free-Form Targeting

Generates randomized generic target IDs that hide agent allegiance,
enabling IFF (Identification Friend or Foe) testing.

When free_targeting_mode is enabled, all combatants (PCs and enemies)
receive randomized IDs like 'tgt_7a3f' instead of revealing IDs like
'player_01' or 'enemy_grunt_xxx'.

Author: Three Rivers AI Nexus
Date: 2025-10-26
"""

import random
import string
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def generate_target_id() -> str:
    """
    Generate random target ID like 'tgt_7a3f'.

    Uses lowercase letters and digits for readability.
    Prefix 'tgt_' distinguishes from other ID formats.

    Returns:
        Random target ID string
    """
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"tgt_{suffix}"


class TargetIDMapper:
    """
    Maps generic target IDs to actual agent references.

    Manages bidirectional mapping between randomized target IDs
    and actual agent instances. IDs are assigned at combat start
    and persist for the duration of combat.

    Attributes:
        target_id_map: target_id -> agent reference
        reverse_map: agent_id -> target_id
        enabled: Whether free targeting mode is active
    """

    def __init__(self):
        self.target_id_map: Dict[str, Any] = {}  # tgt_7a3f -> agent reference
        self.reverse_map: Dict[str, str] = {}     # agent_id -> tgt_7a3f
        self.enabled: bool = False
        self.npc_registry: Dict[str, Any] = {}    # agent_id -> NPC reference
        logger.debug("TargetIDMapper initialized")

    def enable(self):
        """Enable free targeting mode."""
        self.enabled = True
        logger.info("Free targeting mode ENABLED - using generic target IDs")

    def disable(self):
        """Disable free targeting mode."""
        self.enabled = False
        self.clear()
        logger.info("Free targeting mode DISABLED - using standard IDs")

    def clear(self):
        """Clear all ID mappings."""
        self.target_id_map.clear()
        self.reverse_map.clear()
        logger.debug("Target ID mappings cleared")

    def assign_ids(
        self,
        player_agents: List[Any],
        enemy_agents: List[Any],
        npc_agents: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Assign random IDs to all combatants at combat start.

        Combines PCs, enemies, and NPCs into single pool, shuffles to
        randomize order (prevents pattern detection), then assigns
        unique target IDs.

        Args:
            player_agents: List of PC agents
            enemy_agents: List of enemy agents (active only)
            npc_agents: List of NPC agents (active only)

        Returns:
            Dict mapping target_id -> agent reference
        """
        if not self.enabled:
            logger.debug("Free targeting disabled - skipping ID assignment")
            return {}

        self.clear()

        all_combatants = []

        # Add players
        for pc in player_agents:
            if hasattr(pc, 'agent_id'):
                all_combatants.append(pc)
            else:
                logger.warning(f"Player agent {pc} missing agent_id attribute")

        # Add active enemies only
        for enemy in enemy_agents:
            if hasattr(enemy, 'is_active') and enemy.is_active:
                all_combatants.append(enemy)

        # Add active NPCs
        npc_count = 0
        if npc_agents:
            for npc in npc_agents:
                if hasattr(npc, 'is_active') and npc.is_active:
                    all_combatants.append(npc)
                    npc_count += 1

        logger.info(f"Assigning target IDs to {len(all_combatants)} combatants ({len(player_agents)} PCs, {len([e for e in enemy_agents if hasattr(e, 'is_active') and e.is_active])} enemies, {npc_count} NPCs)")

        # Shuffle to randomize order (prevents position-based patterns)
        random.shuffle(all_combatants)

        # Assign unique IDs
        assigned_count = 0
        for agent in all_combatants:
            # Generate unique ID (retry if collision, though unlikely)
            target_id = generate_target_id()
            attempts = 0
            while target_id in self.target_id_map and attempts < 10:
                target_id = generate_target_id()
                attempts += 1

            if attempts >= 10:
                logger.error(f"Failed to generate unique target ID after 10 attempts")
                continue

            agent_id = agent.agent_id
            # Get name: enemies have .name, players have .character_state.name
            agent_name = getattr(agent, 'name', None)
            if not agent_name and hasattr(agent, 'character_state'):
                agent_name = getattr(agent.character_state, 'name', 'Unknown')
            if not agent_name:
                agent_name = 'Unknown'

            self.target_id_map[target_id] = agent
            self.reverse_map[agent_id] = target_id

            assigned_count += 1
            logger.debug(f"  {target_id} -> {agent_name} ({agent_id})")

        logger.info(f"Assigned {assigned_count} target IDs successfully")
        return self.target_id_map

    def resolve_target(self, target_id: str) -> Optional[Any]:
        """
        Resolve target ID back to actual agent.

        Args:
            target_id: Target ID to resolve (e.g., 'tgt_7a3f')

        Returns:
            Agent reference or None if not found
        """
        if not self.enabled:
            logger.debug(f"Free targeting disabled - cannot resolve {target_id}")
            return None

        agent = self.target_id_map.get(target_id)

        if agent:
            # Get agent name - handle both enemy agents (with .name) and player agents (with .character_state.name)
            agent_name = getattr(agent, 'name', None)
            if not agent_name and hasattr(agent, 'character_state'):
                char_state = agent.character_state
                if hasattr(char_state, 'name'):
                    agent_name = char_state.name
                else:
                    agent_name = 'Unknown'
            if not agent_name:
                agent_name = 'Unknown'
            logger.debug(f"Resolved {target_id} -> {agent_name}")
        else:
            logger.warning(f"Target ID {target_id} not found in mapping")

        return agent

    def get_target_id(self, agent_id: str) -> Optional[str]:
        """
        Get target ID for an agent.

        Args:
            agent_id: Agent's permanent ID

        Returns:
            Target ID or None if not found
        """
        if not self.enabled:
            return None

        target_id = self.reverse_map.get(agent_id)

        if target_id:
            logger.debug(f"Found target ID {target_id} for agent {agent_id}")
        else:
            logger.debug(f"No target ID found for agent {agent_id}")

        return target_id

    def is_player(self, target_id: str) -> bool:
        """
        Check if target ID belongs to a player character.

        Useful for detecting friendly fire.

        Args:
            target_id: Target ID to check

        Returns:
            True if PC, False if enemy or not found
        """
        agent = self.resolve_target(target_id)
        if not agent:
            return False

        # PC agents have character_state attribute
        is_pc = hasattr(agent, 'character_state')
        return is_pc

    def is_enemy(self, target_id: str) -> bool:
        """
        Check if target ID belongs to an enemy.

        Args:
            target_id: Target ID to check

        Returns:
            True if enemy, False if PC or not found
        """
        agent = self.resolve_target(target_id)
        if not agent:
            return False

        # Enemy agents have is_active and tactics attributes
        is_npc = hasattr(agent, 'is_active') and hasattr(agent, 'tactics')
        return is_npc

    def get_all_target_ids(self) -> List[str]:
        """
        Get list of all active target IDs.

        Returns:
            List of target ID strings
        """
        return list(self.target_id_map.keys())

    def get_combatant_info(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Get structured info about a combatant.

        Args:
            target_id: Target ID to query

        Returns:
            Dict with name, health, position, type, etc. or None
        """
        agent = self.resolve_target(target_id)
        if not agent:
            return None

        info = {
            'target_id': target_id,
            'agent_id': agent.agent_id,
            'type': 'player' if self.is_player(target_id) else 'enemy'
        }

        # Try to extract common attributes
        if hasattr(agent, 'character_state'):
            # Player agent
            cs = agent.character_state
            info['name'] = cs.name
            info['health'] = cs.health
            info['max_health'] = cs.max_health
            info['position'] = str(getattr(agent, 'position', 'Unknown'))
            info['void_score'] = cs.void_score
        elif hasattr(agent, 'name'):
            # Enemy agent
            info['name'] = agent.name
            info['health'] = agent.health
            info['max_health'] = agent.max_health
            info['position'] = str(agent.position)

        return info

    # NPC tracking methods (for de-escalation system)

    def register_npc(self, npc: Any) -> None:
        """
        Register NPC for tracking.

        NPCs have stable agent_id (may be enemy_xxx format from conversions).

        Args:
            npc: NPCAgent instance
        """
        self.npc_registry[npc.agent_id] = npc
        logger.debug(f"Registered NPC: {npc.agent_id} ({npc.name})")

    def unregister_npc(self, agent_id: str) -> bool:
        """
        Unregister NPC.

        Args:
            agent_id: NPC agent ID

        Returns:
            True if removed, False if not found
        """
        if agent_id in self.npc_registry:
            del self.npc_registry[agent_id]
            logger.debug(f"Unregistered NPC: {agent_id}")
            return True
        return False

    def is_npc(self, agent_id: str) -> bool:
        """
        Check if agent_id is registered as NPC.

        Args:
            agent_id: Agent ID to check (can be enemy_xxx format)

        Returns:
            True if NPC, False otherwise
        """
        return agent_id in self.npc_registry

    def get_all_npc_ids(self) -> List[str]:
        """Get all registered NPC agent IDs."""
        return list(self.npc_registry.keys())

    def get_agent_type(self, agent_id: str) -> Optional[str]:
        """
        Determine agent type from agent_id.

        Args:
            agent_id: Agent ID to check

        Returns:
            "player", "enemy", or "npc", or None if unknown
        """
        # Check NPC registry first (handles stable IDs)
        if agent_id in self.npc_registry:
            return "npc"

        # Check if it's in free targeting system
        if self.enabled and agent_id in self.target_id_map:
            agent = self.target_id_map[agent_id]
            if hasattr(agent, 'character_state'):
                return "player"
            else:
                return "enemy"

        # Fallback: guess from ID prefix
        if agent_id.startswith("player_"):
            return "player"
        elif agent_id.startswith("enemy_"):
            # Could be enemy or NPC (stable IDs), check registry
            if agent_id in self.npc_registry:
                return "npc"
            return "enemy"

        return None

    def can_target(
        self,
        source_id: str,
        target_id: str,
        source_type: Optional[str] = None
    ) -> bool:
        """
        Check if source agent can target target agent.

        Rules:
        - Players can target anyone/anything
        - Enemies can target players + NPCs (based on personality, checked elsewhere)
        - NPCs cannot target (non-combatants)

        Args:
            source_id: Source agent ID
            target_id: Target agent ID
            source_type: Optional type hint ("player", "enemy", "npc")

        Returns:
            True if targeting is allowed
        """
        if source_type is None:
            source_type = self.get_agent_type(source_id)

        # Players can target anything
        if source_type == "player":
            return True

        # Enemies can target (checked with personality elsewhere)
        if source_type == "enemy":
            return True  # Personality check done in can_target_with_personality

        # NPCs cannot target (non-combatants)
        if source_type == "npc":
            return False

        # Unknown source type, deny
        return False

    def can_target_with_personality(
        self,
        source_id: str,
        target_id: str,
        personality: str,
        target_threat_level: str
    ) -> bool:
        """
        Check if enemy can target NPC based on personality and threat level.

        Personality-based targeting:
        - ruthless: Target anyone (PCs, all NPCs)
        - professional: Target threats only (PCs, armed/potential threat NPCs)
        - defensive: Only PCs (ignore all NPCs)

        Threat levels:
        - non_combatant: Civilians, unarmed bystanders
        - potential_threat: NPCs that might be dangerous
        - armed_neutral: NPCs with weapons/training

        Args:
            source_id: Enemy agent ID
            target_id: Target agent ID
            personality: Enemy personality ("ruthless", "professional", "defensive")
            target_threat_level: Target's threat level

        Returns:
            True if enemy can target based on personality
        """
        target_type = self.get_agent_type(target_id)

        # Always can target players
        if target_type == "player":
            return True

        # NPC targeting depends on personality
        if target_type == "npc":
            if personality == "ruthless":
                # Ruthless enemies target anyone
                return True
            elif personality == "professional":
                # Professional enemies only target threats
                return target_threat_level in ["potential_threat", "armed_neutral"]
            elif personality == "defensive":
                # Defensive enemies ignore all NPCs
                return False

        # Default: can't target
        return False

    def __repr__(self) -> str:
        """String representation for debugging."""
        if not self.enabled:
            npc_count = len(self.npc_registry)
            return f"<TargetIDMapper: disabled, {npc_count} NPCs>"

        combatant_count = len(self.target_id_map)
        npc_count = len(self.npc_registry)
        return f"<TargetIDMapper: {combatant_count} combatants, {npc_count} NPCs>"
