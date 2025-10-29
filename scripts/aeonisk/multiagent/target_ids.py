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
        enemy_agents: List[Any]
    ) -> Dict[str, Any]:
        """
        Assign random IDs to all combatants at combat start.

        Combines PCs and enemies into single pool, shuffles to
        randomize order (prevents pattern detection), then assigns
        unique target IDs.

        Args:
            player_agents: List of PC agents
            enemy_agents: List of enemy agents (active only)

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

        logger.info(f"Assigning target IDs to {len(all_combatants)} combatants ({len(player_agents)} PCs, {len([e for e in enemy_agents if hasattr(e, 'is_active') and e.is_active])} enemies)")

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

        # Enemy agents have is_active and is_group attributes
        is_npc = hasattr(agent, 'is_active') and hasattr(agent, 'is_group')
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
            info['unit_count'] = agent.unit_count if agent.is_group else 1

        return info

    def __repr__(self) -> str:
        """String representation for debugging."""
        if not self.enabled:
            return "<CombatIDMapper: disabled>"

        return f"<CombatIDMapper: {len(self.combat_id_map)} combatants>"
