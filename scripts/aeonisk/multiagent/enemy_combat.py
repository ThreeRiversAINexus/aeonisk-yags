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
    spawn_from_marker,
    despawn_from_markers,
    auto_despawn_defeated,
    get_active_enemies,
    suggest_loot
)
from .enemy_prompts import generate_tactical_prompt
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
        # Skip code blocks, examples, headers
        if line.strip().startswith('```') or line.strip().startswith('#') or line.strip().startswith('**'):
            continue

        if ':' in line:
            key, value = line.split(':', 1)
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

    def __init__(self):
        self.enemy_agents: List[EnemyAgent] = []
        self.shared_intel = SharedIntel()
        self.enemy_declarations: Dict[str, EnemyDeclaration] = {}
        self.current_round: int = 0
        self.enabled: bool = False
        self.config: Dict[str, Any] = {}

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
            logger.info("Enemy combat manager initialized (ENABLED)")
        else:
            logger.info("Enemy combat manager initialized (DISABLED)")

    def process_dm_narration(self, narration: str) -> List[str]:
        """
        Process DM narration for spawn/despawn markers.

        Args:
            narration: DM narration text

        Returns:
            List of spawn/despawn notification messages
        """
        if not self.enabled:
            return []

        notifications = []

        # Process spawns
        spawned = spawn_from_marker(narration, self.current_round)
        for enemy in spawned:
            self.enemy_agents.append(enemy)
            notifications.append(
                f"⚔️  **{enemy.name}** spawned! "
                f"({enemy.unit_count} {'units' if enemy.is_group else 'unit'}, "
                f"{enemy.health} HP, {enemy.position}, "
                f"tactics: {enemy.tactics})"
            )
            logger.info(f"Spawned enemy: {enemy.name} (ID: {enemy.agent_id})")

        # Process despawns
        despawned = despawn_from_markers(narration, self.enemy_agents, self.current_round)
        for enemy in despawned:
            notifications.append(
                f"💀 **{enemy.name}** despawned "
                f"({enemy.despawned_round - enemy.spawned_round} rounds survived)"
            )
            logger.info(f"Despawned enemy: {enemy.name} (ID: {enemy.agent_id})")

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
        if not self.enabled:
            return []

        active_enemies = get_active_enemies(self.enemy_agents)
        if not active_enemies:
            return []

        declarations = []

        for enemy in active_enemies:
            # Generate tactical prompt
            prompt = generate_tactical_prompt(
                enemy=enemy,
                player_agents=player_agents,
                enemy_agents=active_enemies,
                shared_intel=self.shared_intel,
                available_tokens=available_tokens,
                current_round=self.current_round
            )

            # Get LLM response
            try:
                response = await llm_client.generate_async(
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=500
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

            except Exception as e:
                logger.error(f"{enemy.name}: Error generating declaration: {e}")

        return declarations

    def execute_enemy_action(
        self,
        enemy_id: str,
        player_agents: List[Any],
        mechanics_engine: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a single enemy action during resolution phase.

        Args:
            enemy_id: Enemy agent ID
            player_agents: List of PC agents
            mechanics_engine: Mechanics engine for rolls

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

        # Execute based on major action
        major_action = declaration.major_action.lower()

        if 'attack' in major_action:
            return self._execute_attack(enemy, declaration, player_agents, mechanics_engine)
        elif 'shift' in major_action:
            return self._execute_movement(enemy, declaration)
        elif 'charge' in major_action:
            return self._execute_charge(enemy, declaration, player_agents, mechanics_engine)
        elif 'retreat' in major_action:
            return self._execute_retreat(enemy, declaration)
        elif 'grenade' in major_action or 'throw' in major_action:
            return self._execute_grenade(enemy, declaration, player_agents, mechanics_engine)
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
        mechanics_engine: Any
    ) -> Dict[str, Any]:
        """Execute enemy attack action."""
        target_id = declaration.target
        weapon_name = declaration.weapon

        # Find target PC
        target = next((p for p in player_agents if p.agent_id == target_id), None)
        if not target:
            return {
                'enemy_id': enemy.agent_id,
                'character_name': enemy.name,
                'action': 'attack',
                'result': 'target not found',
                'narration': f"{enemy.name} attacks but target has moved"
            }

        # Find weapon
        weapon = next((w for w in enemy.weapons if w.name.lower() == weapon_name.lower()), None)
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

        result = {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'attack',
            'target': target.name if hasattr(target, 'name') else str(target_id),
            'weapon': weapon.name,
            'range': range_name,
            'hit': hit,
            'attack_roll': attack_total,
            'narration': f"{enemy.name} attacks {target.name if hasattr(target, 'name') else 'target'} with {weapon.name}"
        }

        if hit:
            # Roll damage
            strength = enemy.attributes.get('Strength', 3)
            group_bonus = enemy.get_group_damage_bonus()
            damage_roll = random.randint(1, 20)
            total_damage = strength + weapon.damage + damage_roll + group_bonus

            result['damage'] = total_damage
            result['narration'] += f" - HIT! {total_damage} damage"

            # Apply damage to target (if target has health tracking)
            if hasattr(target, 'health') and hasattr(target, 'soak'):
                damage_dealt = max(0, total_damage - target.soak)
                target.health -= damage_dealt
                result['damage_dealt'] = damage_dealt
                result['narration'] += f" ({damage_dealt} after soak)"
        else:
            result['narration'] += f" - MISS ({attack_total} vs defence {target_defence})"

        return result

    def _execute_movement(self, enemy: EnemyAgent, declaration: EnemyDeclaration) -> Dict[str, Any]:
        """Execute enemy movement action."""
        old_position = str(enemy.position)

        # Parse movement from action
        action = declaration.major_action.lower()

        if 'shift_2' in action or 'shift 2' in action:
            # Major: Shift 2 bands
            # Simplified: shift toward center twice
            enemy.position = enemy.position.shift_toward_center() or enemy.position
            enemy.position = enemy.position.shift_toward_center() or enemy.position
        elif 'push' in action:
            # Push through to opposite side
            enemy.position = enemy.position.push_through()
        elif declaration.minor_action and 'shift' in declaration.minor_action.lower():
            # Minor: Shift 1 band
            if 'away' in declaration.minor_action.lower():
                enemy.position = enemy.position.shift_away_from_center() or enemy.position
            else:
                enemy.position = enemy.position.shift_toward_center() or enemy.position

        new_position = str(enemy.position)

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'movement',
            'old_position': old_position,
            'new_position': new_position,
            'narration': f"{enemy.name} moves from {old_position} to {new_position}"
        }

    def _execute_charge(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any
    ) -> Dict[str, Any]:
        """Execute enemy charge action (movement + attack)."""
        # Move to engaged/melee with target
        old_position = str(enemy.position)
        target = next((p for p in player_agents if p.agent_id == declaration.target), None)

        if target:
            try:
                target_position = Position.from_string(str(getattr(target, 'position', "Near-PC")))
                # Move to same ring as target
                enemy.position = Position(ring=target_position.ring, side=target_position.side)
            except:
                pass

        # Execute attack with charge bonus
        attack_result = self._execute_attack(enemy, declaration, player_agents, mechanics_engine)
        if attack_result.get('hit') and 'damage' in attack_result:
            attack_result['damage'] += 2  # Charge bonus
            attack_result['narration'] = f"{enemy.name} charges from {old_position} to {enemy.position} and attacks (+2 damage)"

        return attack_result

    def _execute_retreat(self, enemy: EnemyAgent, declaration: EnemyDeclaration) -> Dict[str, Any]:
        """Execute enemy retreat action."""
        enemy.is_active = False
        enemy.despawned_round = self.current_round

        # Add to shared intel
        if declaration.shared_intel:
            self.shared_intel.add_intel(enemy.name, declaration.shared_intel, self.current_round)

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'retreat',
            'reason': declaration.reasoning,
            'narration': f"{enemy.name} retreats from combat: {declaration.reasoning}"
        }

    def _execute_grenade(
        self,
        enemy: EnemyAgent,
        declaration: EnemyDeclaration,
        player_agents: List[Any],
        mechanics_engine: Any
    ) -> Dict[str, Any]:
        """Execute grenade throw (AoE attack)."""
        target_location = declaration.target  # e.g., "Near-Enemy"

        # Find all PCs and enemies at target location
        affected = []

        # Check PCs
        for pc in player_agents:
            try:
                pc_position = Position.from_string(str(getattr(pc, 'position', "Near-PC")))
                if str(pc_position) == target_location:
                    affected.append(('PC', pc.name if hasattr(pc, 'name') else str(pc.agent_id)))
            except:
                pass

        # Check enemies
        for ally in get_active_enemies(self.enemy_agents):
            if ally.agent_id != enemy.agent_id and str(ally.position) == target_location:
                affected.append(('Enemy', ally.name))

        return {
            'enemy_id': enemy.agent_id,
            'character_name': enemy.name,
            'action': 'grenade',
            'target_location': target_location,
            'affected': affected,
            'narration': f"{enemy.name} throws grenade at {target_location} (affects: {', '.join(a[1] for a in affected)})"
        }

    def cleanup_round(self) -> List[Dict[str, Any]]:
        """
        Perform end-of-round cleanup.

        - Apply group attrition
        - Auto-despawn defeated enemies
        - Clear old shared intel
        - Generate loot suggestions

        Returns:
            List of cleanup events
        """
        if not self.enabled:
            return []

        events = []

        # Apply attrition to groups
        for enemy in get_active_enemies(self.enemy_agents):
            if enemy.is_group:
                old_count = enemy.unit_count
                enemy.apply_group_attrition()

                if enemy.unit_count < old_count:
                    events.append({
                        'type': 'attrition',
                        'enemy_id': enemy.agent_id,
                        'character_name': enemy.name,
                        'old_count': old_count,
                        'new_count': enemy.unit_count,
                        'narration': f"{enemy.name}: {old_count - enemy.unit_count} units lost, {enemy.unit_count} remain"
                    })

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

        # Clear old intel
        self.shared_intel.clear_old_intel(self.current_round, max_age=3)

        # Increment round
        self.current_round += 1

        return events

    def get_active_enemy_count(self) -> int:
        """Get count of active enemy units."""
        return sum(e.unit_count for e in get_active_enemies(self.enemy_agents))

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
