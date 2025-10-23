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

    def __init__(self, shared_state=None):
        self.enemy_agents: List[EnemyAgent] = []
        self.shared_intel = SharedIntel()
        self.enemy_declarations: Dict[str, EnemyDeclaration] = {}
        self.current_round: int = 0
        self.enabled: bool = False
        self.config: Dict[str, Any] = {}
        self.shared_state = shared_state  # Reference to shared state for logging

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
            logger.debug("Enemy combat manager initialized (ENABLED)")
        else:
            logger.debug("Enemy combat manager initialized (DISABLED)")

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
                        "armor": {"name": enemy.armor.name, "soak_bonus": enemy.armor.soak_bonus} if enemy.armor else None,
                        "is_group": enemy.is_group,
                        "unit_count": enemy.unit_count if enemy.is_group else 1
                    }

                    mechanics.jsonl_logger.log_enemy_spawn(
                        round_num=self.current_round,
                        enemy_id=enemy.agent_id,
                        enemy_name=enemy.name,
                        template=enemy.template or "unknown",
                        stats=stats,
                        position=str(enemy.position),
                        tactics=enemy.tactics
                    )

        # Process despawns
        despawned = despawn_from_markers(narration, self.enemy_agents, self.current_round)
        for enemy in despawned:
            notifications.append(
                f"💀 **{enemy.name}** despawned "
                f"({enemy.despawned_round - enemy.spawned_round} rounds survived)"
            )
            logger.info(f"Despawned enemy: {enemy.name} (ID: {enemy.agent_id})")

            # Log enemy despawn to JSONL for ML training
            if self.shared_state:
                mechanics = self.shared_state.get_mechanics_engine()
                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                    rounds_survived = enemy.despawned_round - enemy.spawned_round
                    mechanics.jsonl_logger.log_enemy_defeat(
                        round_num=self.current_round,
                        enemy_id=enemy.agent_id,
                        enemy_name=enemy.name,
                        defeat_reason="despawned",  # Escaped/retreated via marker
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

        active_enemies = get_active_enemies(self.enemy_agents)

        logger.debug(f"Generating declaration for {enemy.name} (ID: {enemy.agent_id})")

        # Generate tactical prompt
        from .enemy_prompts import generate_tactical_prompt

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

        if 'attack' in major_action:
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
            base_damage = strength + weapon.damage + damage_roll + group_bonus

            # Combat balance: Reduce enemy damage by 15% to prevent one-shots while avoiding stalemate
            total_damage = int(base_damage * 0.85)

            result['damage'] = total_damage
            result['narration'] += f" - HIT! {total_damage} damage"

            # Apply damage to target (if target has health tracking)
            if hasattr(target, 'health') and hasattr(target, 'soak'):
                damage_dealt = max(0, total_damage - target.soak)
                target.health -= damage_dealt
                result['damage_dealt'] = damage_dealt
                result['narration'] += f" ({damage_dealt} after soak)"

                # Track damage for round summary
                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_player_damage_taken(damage_dealt)

                # Calculate wounds (YAGS: every 5 points of damage = 1 wound)
                if hasattr(target, 'wounds') and damage_dealt > 0:
                    wounds_dealt = damage_dealt // 5
                    target.wounds += wounds_dealt
                    logger.info(f"{target.name if hasattr(target, 'name') else target_id} took {wounds_dealt} wounds (total: {target.wounds})")

                # Mark target as defeated if killed
                if target.health <= 0:
                    # Check for death/unconsciousness (YAGS death saves)
                    if hasattr(target, 'check_death_save'):
                        alive, status = target.check_death_save()

                        if not alive:
                            # Player died - mark as defeated
                            result['narration'] += " - KILLED!"
                            logger.warning(f"{target.name if hasattr(target, 'name') else target_id} KILLED by {enemy.name}")
                            resolution_state.mark_defeated(target_id)
                            result['target_defeated'] = True
                        elif status == "unconscious":
                            # Player unconscious - mark as defeated (can't act)
                            result['narration'] += " - UNCONSCIOUS!"
                            logger.info(f"{target.name if hasattr(target, 'name') else target_id} falls unconscious")
                            resolution_state.mark_defeated(target_id)
                            result['target_defeated'] = True
                        elif status == "conscious":
                            # Player critically wounded but still fighting - NOT defeated
                            result['narration'] += " - CRITICALLY WOUNDED but still conscious!"
                            logger.info(f"{target.name if hasattr(target, 'name') else target_id} critically wounded but fighting on")
                            # DO NOT mark as defeated - they can still act!
                            result['target_defeated'] = False
                    else:
                        # No death save system - just mark as defeated
                        result['narration'] += " - TARGET DEFEATED!"
                        resolution_state.mark_defeated(target_id)
                        result['target_defeated'] = True
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
            if hit and hasattr(target, 'soak'):
                damage_roll_data = {
                    "strength": strength,
                    "weapon_dmg": weapon.damage,
                    "group_bonus": group_bonus,
                    "d20": damage_roll,
                    "base_damage": base_damage,
                    "combat_balance_modifier": 0.85,
                    "total": total_damage,
                    "soak": target.soak,
                    "dealt": damage_dealt
                }
                wounds_dealt_count = wounds_dealt if hasattr(target, 'wounds') and damage_dealt > 0 else 0

            # Build defender state dict
            defender_state = None
            if hasattr(target, 'health'):
                defender_state = {
                    "health": target.health,
                    "max_health": getattr(target, 'max_health', None),
                    "wounds": getattr(target, 'wounds', 0),
                    "alive": target.health > 0,
                    "status": status if hit and target.health <= 0 and hasattr(target, 'check_death_save') else "active"
                }

            mechanics_engine.jsonl_logger.log_combat_action(
                round_num=self.current_round,
                attacker_id=enemy.agent_id,
                attacker_name=enemy.name,
                defender_id=target_id,
                defender_name=target.name if hasattr(target, 'name') else str(target_id),
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

        # Find target PC
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
        weapon = next((w for w in enemy.weapons if w.name.lower() == weapon_name.lower()), None)
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
        target = next((p for p in player_agents if p.agent_id == declaration.target), None)

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
