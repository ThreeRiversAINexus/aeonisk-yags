"""
AI Dungeon Master agent for multi-agent self-playing system.
"""

import asyncio
import logging
import random
from typing import Dict, Any, List, Optional, Callable, Iterable, Tuple
from dataclasses import dataclass
from datetime import datetime

from .base import Agent, Message, MessageType
from .shared_state import SharedState
from .voice_profiles import VoiceProfile
from .energy_economy import Vendor, VendorType, create_standard_vendors
from .prompt_loader import load_agent_prompt, compose_sections, load_modular_prompt
from token_utils import count_chat_tokens, count_text_tokens

logger = logging.getLogger(__name__)


def format_filled_clocks_guidance(filled_clocks, critical_overflow: bool = False) -> str:
    """
    Build the synthesis guidance for clocks that filled this round.

    Surfaces each clock's in-world consequence (always present -- see
    SceneClock.effective_consequence) and instructs the DM to narrate it as an
    event that HAS happened. This is the fix for the "DM walks back completions"
    failure: previously the prompt listed only clock names and told the DM to
    "change the scenario", so a filled bond-rupture clock got narrated as a
    near-miss ("steadies instead of tearing apart") and the resolution never
    landed. Now the authored consequence reaches the DM and the directive
    forbids the near-miss.

    Args:
        filled_clocks: list of {clock_name, reason, consequence} dicts from
            MechanicsEngine.get_and_clear_filled_clocks()
        critical_overflow: True when a clock overflowed badly (raise urgency)
    """
    if not filled_clocks:
        return ""

    names = [f['clock_name'] for f in filled_clocks]
    urgency = "🚨 EXTREME URGENCY 🚨" if critical_overflow else "⚠️  URGENT"

    text = f"\n\n{urgency} **CLOCKS FILLED (Auto-removing):** {', '.join(names)}\n"
    text += (
        "These resolutions HAVE HAPPENED. Narrate each as an event that occurs "
        "NOW -- not as a near-miss, not 'almost', not 'threatens to', not "
        "'steadies instead'. Show the consequence landing, then let the scene move.\n\n"
    )
    text += "**What just happened (narrate each as fact):**\n"
    for f in filled_clocks:
        cons = (f.get('consequence') or '').strip()
        if cons:
            text += f"  • {f['clock_name']}: {cons}\n"
    text += "\n"
    text += "**For clocks with mechanical markers** (e.g., [SPAWN_ENEMY: ...]):\n"
    text += "- Include the exact marker text from the consequence in your narration\n"
    text += "- The marker will trigger automatically\n\n"
    text += "**For narrative clocks** (no mechanical markers):\n"
    text += "- Render the consequence above, then move the scene with a DM control marker:\n"
    text += "  • [ADVANCE_STORY: Location | Situation] - progress to new location or change situation in same location\n"
    text += "  • [NEW_CLOCK: Name | Max | Description] - new pressure/opportunity emerges\n"
    text += "  • [SESSION_END: VICTORY/DEFEAT/DRAW] - mission fully complete or total failure\n\n"
    text += "⚠️  A filled clock narrated as 'almost happened' or left without a scenario marker STALLS the story."
    return text


def _forced_scenario_fields(spec) -> Dict[str, Any]:
    """Normalize a force_scenario config value into scenario fields.

    Legacy form: a string spawn-marker (automated tests) -> the historical
    "Test Scenario" placeholder. Dict form (resume-from-divergence): the
    reconstructor supplies the recorded theme/location/void plus a situation
    carrying the story-so-far digest, so the resumed DM continues the scene
    instead of inventing a fresh one.
    """
    if isinstance(spec, dict):
        return {
            "theme": spec.get("theme", "Resumed Session"),
            "location": spec.get("location", "Unknown"),
            "situation": spec.get("situation", ""),
            "void_level": spec.get("void_level", 0) or 0,
        }
    return {"theme": "Test Scenario", "location": "Test Location",
            "situation": str(spec), "void_level": 0}


def _resolution_success(resolution) -> bool:
    """
    Safely check if ActionResolution succeeded.

    Handles both old dataclass (has .success field) and new Pydantic schema (has .success_tier enum).
    For new schema, success = success_tier in (MARGINAL, MODERATE, GOOD, EXCELLENT, EXCEPTIONAL) —
    a marginal result still clears the DC, so it counts as a success.
    """
    # Old schema: has .success field
    if hasattr(resolution, 'success'):
        return resolution.success

    # New schema: derive from success_tier
    if hasattr(resolution, 'success_tier'):
        from .schemas.action_resolution import SuccessTier
        success_tiers = {SuccessTier.MODERATE, SuccessTier.GOOD, SuccessTier.EXCELLENT, SuccessTier.EXCEPTIONAL, SuccessTier.MARGINAL}
        return resolution.success_tier in success_tiers

    # Fallback: assume success if we can't determine
    return True


def _resolve_declared_weapon(declared: str, owned: list) -> 'Resolution':
    """Resolve a declared weapon against the ones the character actually holds.

    Delegates to the shared resolver (#134). The policy that matters here is the
    invariant: a match may never cross lethality class. The previous matcher
    used bidirectional substring containment, which accepted `'the stun pistol'`
    as a lethal Pistol — on the loadout element used by 149 configs — while
    refusing `'the tranquilizer'`, the example in its own docstring.

    Returns the full `Resolution` rather than the weapon, because `path` is what
    makes an inferred match auditable downstream.
    """
    from .resolution import WEAPON_POLICY, resolve
    return resolve(declared, [w for w in owned if getattr(w, 'name', None)],
                   WEAPON_POLICY)


def _match_declared_weapon(declared: str, owned: list):
    """The weapon a declaration refers to, or None. See `_resolve_declared_weapon`."""
    return _resolve_declared_weapon(declared, owned).value


def _resolve_weapon_and_damage_type(
    action: Optional[Dict[str, Any]],
    shared_state: 'SharedState'
) -> Tuple[str, str, Any]:
    """
    Resolve weapon name, YAGS damage type, and Weapon object from player action.

    Looks up the player's equipped weapons and matches by skill to determine
    which weapon is being used and its damage type.

    Returns:
        (weapon_name, damage_type, weapon_obj_or_None)
        - damage_type is one of: "stun", "wound", "mixed"
    """
    if not action or not shared_state:
        return ("Unknown Weapon", "wound", None)

    player_agent_id = action.get('agent_id')
    if not player_agent_id:
        return ("Unknown Weapon", "wound", None)

    # Find the player agent
    player_agent = None
    for player in getattr(shared_state, 'player_agents', []):
        if hasattr(player, 'agent_id') and player.agent_id == player_agent_id:
            player_agent = player
            break

    if not player_agent or not hasattr(player_agent, 'equipped_weapons'):
        return ("Unknown Weapon", "wound", None)

    skill = (action.get('skill') or '').lower()  # models may return skill: null
    primary = player_agent.equipped_weapons.get('primary')
    sidearm = player_agent.equipped_weapons.get('sidearm')

    # An explicitly declared weapon wins over the skill heuristic below, and the
    # search includes carried weapons. Selecting purely by skill meant any Guns
    # action returned the lethal primary, so a character holding both a carbine
    # and a tranquilizer could never fire the tranquilizer — the II.8 lawful
    # subdue path was unreachable, and attempts at it were resolved as killings.
    # The prompt already instructs players to name their weapon; there was
    # simply nowhere structured to put the answer.
    declared = (action.get('weapon') or '').strip()
    if declared:
        owned = [w for w in (primary, sidearm) if w is not None]
        owned += list(getattr(player_agent, 'weapon_inventory', None) or [])
        match = _match_declared_weapon(declared, owned)
        if match is not None:
            return (match.name, getattr(match, 'damage_type', 'wound'), match)
        # A weapon the character does not own falls through to the skill
        # heuristic: naming one must never confer its properties.
        logger.debug(
            f"Declared weapon {declared!r} not in inventory; resolving by skill")

    if skill in ['guns', 'throw'] and primary:
        return (primary.name, getattr(primary, 'damage_type', 'wound'), primary)
    elif skill == 'brawl':
        if sidearm and getattr(sidearm, 'skill', '') == 'Brawl':
            return (sidearm.name, getattr(sidearm, 'damage_type', 'stun'), sidearm)
        else:
            # Unarmed — use fists from WEAPON_LIBRARY
            from .weapons import WEAPON_LIBRARY
            fists = WEAPON_LIBRARY.get("fists")
            return ("Unarmed", "stun", fists)
    elif skill == 'melee' and sidearm:
        return (sidearm.name, getattr(sidearm, 'damage_type', 'wound'), sidearm)
    elif primary:
        return (primary.name, getattr(primary, 'damage_type', 'wound'), primary)
    elif sidearm:
        return (sidearm.name, getattr(sidearm, 'damage_type', 'wound'), sidearm)

    return ("Unknown Weapon", "wound", None)


def _targeting_trigger_reason(error: Optional[str]) -> str:
    """Derive the `triggered_by` tag for targeting-validation logging.

    `error` is None on the mechanical-correction success path
    (validate_and_correct_targeting returns (True, corrected, None)), so a bare
    `':' in error` there raised `TypeError: argument of type 'NoneType' is not
    iterable` and killed the whole session over a metrics log. Treat a missing
    or colon-less error as 'unknown'.
    """
    if error and ':' in error:
        return error.split(':')[0]
    return 'unknown'


def _get_wielder_soulcredit(action: Optional[Dict[str, Any]], shared_state) -> Optional[int]:
    """Resolve the acting player's current Soulcredit for contract-gear locks.
    Prefers the live mechanics ledger (kept authoritative by enforce mode);
    falls back to the character_state snapshot. None if not a tracked player."""
    if not action or not shared_state:
        return None
    aid = action.get('agent_id')
    if not aid:
        return None
    mech = shared_state.get_mechanics_engine() if hasattr(shared_state, 'get_mechanics_engine') else None
    if mech and aid in getattr(mech, 'soulcredit_states', {}):
        return mech.soulcredit_states[aid].score
    for p in getattr(shared_state, 'player_agents', []):
        if getattr(p, 'agent_id', None) == aid:
            return getattr(getattr(p, 'character_state', None), 'soulcredit', None)
    return None


def _build_checkpoint_context(action: Optional[Dict[str, Any]]) -> str:
    """Surface a stashed checkpoint verdict (VIII.1) to the DM narration prompt.

    Not a hard block: for a denied character the DM must refuse the lawful
    walk-through and force an alternate approach (turn back, bribe, deceive,
    sneak, force) — each its own consequence. Empty string when the action did
    not attempt a gated passage.
    """
    if not action:
        return ""
    cv = action.get('checkpoint_validation')
    if not cv:
        return ""
    name = cv.get('checkpoint_name', 'the checkpoint')
    if cv.get('is_allowed'):
        return (f"\n\n**✓ CHECKPOINT — {name}:** the gate reads the character's "
                f"Codex standing and clears them. Lawful passage is open; narrate "
                f"the crossing.\n")
    reason = cv.get('failure_reason', 'standing insufficient')
    return (f"\n\n**⛔ CHECKPOINT DENIED — {name}:** the gate reads the character's "
            f"Codex standing and REFUSES passage ({reason}). Do NOT narrate a simple "
            f"walk-through or let them slip past unremarked — the lawful path is "
            f"CLOSED. Narrate the refusal at the gate, then force the choice: turn "
            f"back, bribe, deceive, sneak, or force the way — each with consequences.\n")


def _force_fail_locked_weapon(resolution, weapon_obj, wielder_soulcredit) -> bool:
    """If a contract weapon is Soulcredit-locked, force the action's roll to a
    failure — the weapon never fired, so the attack does not succeed.

    Returns True if the lock was applied. This gives the acting agent a clean
    "this didn't work, adapt" signal (and lets the failure-loop detector engage)
    instead of a masked success. The DM prompt's lock directive and the damage
    backstop handle narration and damage; this owns the outcome tier.
    """
    from .weapons import weapon_is_sc_locked
    if wielder_soulcredit is None or not weapon_is_sc_locked(weapon_obj, wielder_soulcredit):
        return False
    from .mechanics import OutcomeTier
    resolution.success = False
    resolution.outcome_tier = OutcomeTier.FAILURE
    if getattr(resolution, 'margin', 0) >= 0:
        resolution.margin = -1
    return True


def _get_combatant_state_tag(
    info: Dict[str, Any],
    target_id: str,
    shared_state: Any
) -> str:
    """
    Generate a state tag for a combatant in the DM target list.

    Returns a bracketed tag like [ACTIVE], [PRISONER], [WOUNDED], etc.
    that helps the DM distinguish targetable entities from non-combatants.

    Args:
        info: Combatant info dict from TargetIDMapper.get_combatant_info()
        target_id: The tgt_xxxx ID
        shared_state: SharedState instance for entity lookups

    Returns:
        State tag string, e.g. "[ACTIVE]", "[PRISONER]", "[UNCONSCIOUS]"
    """
    entity_type = info.get('type', 'unknown')

    # Check death state first (applies to all entity types)
    death_state = info.get('death_state', 'alive')
    if death_state == 'dead':
        return "[DEAD]"
    if death_state == 'unconscious':
        return "[UNCONSCIOUS]"

    # Player-specific states
    if entity_type == 'player':
        health = info.get('health', 0)
        max_health = info.get('max_health', 1)
        wounds = info.get('wounds', 0)
        if wounds >= 4:
            return "[CRITICAL]"
        elif health <= max_health * 0.25 and max_health > 0:
            return "[WOUNDED]"
        return "[ACTIVE]"

    # NPC-specific states
    if entity_type == 'npc':
        # Look up NPC agent for disposition and entity_type
        if shared_state and hasattr(shared_state, 'npc_agents') and shared_state.npc_agents:
            agent_id = info.get('agent_id')
            for npc in shared_state.npc_agents:
                if hasattr(npc, 'agent_id') and npc.agent_id == agent_id:
                    if getattr(npc, 'disposition', None) == 'prisoner' or getattr(npc, 'entity_type', None) == 'prisoner':
                        return "[PRISONER]"
                    if not getattr(npc, 'is_active', True):
                        return "[INACTIVE]"
                    # Check if NPC is fleeing (has flee action in recent memory)
                    if (hasattr(npc, 'memory') and npc.memory and
                            hasattr(npc.memory, 'own_actions') and npc.memory.own_actions):
                        last_action = npc.memory.own_actions[-1]
                        if last_action.get('action_type') == 'flee':
                            return "[FLEEING]"
                    return "[NON-COMBATANT]"
        return "[NON-COMBATANT]"

    # Enemy-specific states
    if entity_type == 'enemy':
        # Look up enemy agent for state flags
        agent = None
        if shared_state and hasattr(shared_state, 'enemy_combat') and shared_state.enemy_combat:
            agent_id = info.get('agent_id')
            enemy_agents = getattr(shared_state.enemy_combat, 'enemy_agents', [])
            for enemy in enemy_agents:
                if getattr(enemy, 'agent_id', None) == agent_id:
                    agent = enemy
                    break

        if agent:
            if agent.is_prisoner:
                return "[PRISONER]"
            if not agent.is_active:
                return "[DEFEATED]"
            if agent.is_panicked:
                return "[PANICKED/FLEEING]"
            # Wounded check
            health = info.get('health', 0)
            max_health = info.get('max_health', 1)
            if max_health > 0 and health <= max_health * 0.25:
                return "[WOUNDED]"
            return "[ACTIVE]"
        return "[ACTIVE]"

    # Vendor
    if entity_type == 'vendor':
        return "[VENDOR/NON-COMBATANT]"

    return "[UNKNOWN]"


def _get_attacker_strength(action: Optional[Dict[str, Any]], shared_state) -> int:
    """
    Get attacker's Strength attribute for damage calculation guidance.

    Used by _build_weapon_context to provide base_damage formula to the DM.

    Args:
        action: Player action dict (must have 'agent_id')
        shared_state: SharedState instance for player lookup

    Returns:
        Strength attribute value (default 3 if not found)
    """
    if not action or not shared_state:
        return 3

    agent_id = action.get('agent_id')
    if not agent_id:
        return 3

    for player in getattr(shared_state, 'player_agents', []):
        if hasattr(player, 'agent_id') and player.agent_id == agent_id:
            if hasattr(player, 'character_state') and player.character_state:
                return player.character_state.attributes.get('Strength', 3)
    return 3


def _build_weapon_context(action: Optional[Dict[str, Any]], shared_state) -> str:
    """
    Build expanded weapon context block for DM resolution prompt.

    Includes weapon stats (damage bonus, attack bonus) and base_damage guidance
    anchored to the weapon's mechanical values, so the DM LLM generates
    consistent base_damage instead of arbitrary values.

    Args:
        action: Player action dict
        shared_state: SharedState instance

    Returns:
        Formatted weapon context string, or empty string if no weapon found
    """
    if not action or not shared_state:
        return ""

    if action.get('action_type') not in ('attack', 'combat', 'brawl'):
        return ""

    weapon_name, weapon_damage_type, weapon_obj = _resolve_weapon_and_damage_type(action, shared_state)

    if weapon_name == "Unknown Weapon":
        return ""

    # Contract-gear Soulcredit lock: a weapon tagged soulcredit_locked refuses
    # to fire when the wielder's standing is below its floor (Debtbreaker: SC<0).
    # Deterministic no-damage is enforced in _process_structured_damage_effects;
    # this directive keeps the DM's narration coherent with the mechanical block.
    from .weapons import weapon_is_sc_locked, weapon_sc_lock_threshold
    wielder_sc = _get_wielder_soulcredit(action, shared_state)
    if wielder_sc is not None and weapon_is_sc_locked(weapon_obj, wielder_sc):
        floor = weapon_sc_lock_threshold(weapon_obj)
        return (
            f"\n\n**⛔ CONTRACT WEAPON LOCKED (MECHANICAL):**\n"
            f"Weapon: {weapon_name}\n"
            f"The wielder's Soulcredit ({wielder_sc}) is below this contract "
            f"weapon's floor ({floor}). The weapon LOCKS — it clicks dead and "
            f"emits a Codex ping. This attack FAILS: it does not hit and deals "
            f"NO damage. Do NOT emit any DamageEffect for this weapon. Narrate "
            f"the dead click and the Codex ping.\n"
        )

    weapon_damage = weapon_obj.damage if weapon_obj else 0
    weapon_attack = weapon_obj.attack if weapon_obj else 0
    attacker_strength = _get_attacker_strength(action, shared_state)

    context = (
        f"\n\n**WEAPON CONTEXT (MECHANICAL):**\n"
        f"Weapon: {weapon_name}\n"
        f"Damage Type: {weapon_damage_type.upper()}\n"
        f"Weapon Damage Bonus: {weapon_damage}\n"
        f"Attack Bonus: {weapon_attack}\n"
    )

    # Include base_damage guidance with tier breakdown
    base = attacker_strength + weapon_damage
    context += (
        f"\n**base_damage GUIDANCE:**\n"
        f"Formula: Strength({attacker_strength}) + Weapon Damage({weapon_damage}) + margin_modifier\n"
        f"- Marginal success (margin 0-4): base_damage = {base} (weapon + strength, no bonus)\n"
        f"- Moderate success (margin 5-9): base_damage = {base + 3} (add partial margin)\n"
        f"- Good success (margin 10-14): base_damage = {base + 6}\n"
        f"- Excellent+ (margin 15+): base_damage = {base + 10}\n"
        f"Set damage_type=\"{weapon_damage_type}\" in all DamageEffect fields.\n"
    )

    return context


def _execute_item_transfer(
    source_agent_id: str,
    target_agent_id: str,
    currency_amounts: Optional[Dict[str, int]],
    item_amounts: Optional[Dict[str, int]],
    shared_state,
) -> Dict[str, Any]:
    """
    Execute inter-agent transfer (any agent type to any agent type).

    Supports: PC->PC, PC->NPC, NPC->PC, NPC->NPC currency and item transfers.

    Args:
        source_agent_id: Agent ID of the source (sender)
        target_agent_id: Agent ID of the target (receiver)
        currency_amounts: Dict of currency type -> amount (e.g. {"drip": 10})
        item_amounts: Dict of inventory key -> count (e.g. {"med_kit": 1})
        shared_state: SharedState instance for agent lookup

    Returns:
        Dict with "success" bool and details about what transferred
    """
    if not shared_state:
        return {"success": False, "reason": "no shared state"}

    # Find source and target agents
    source = _find_agent_by_id(source_agent_id, shared_state)
    target = _find_agent_by_id(target_agent_id, shared_state)

    if not source:
        return {"success": False, "reason": f"source agent '{source_agent_id}' not found"}
    if not target:
        return {"success": False, "reason": f"target agent '{target_agent_id}' not found"}

    source_purse = _get_agent_purse(source)
    target_purse = _get_agent_purse(target)
    source_inv = _get_agent_inventory(source)
    target_inv = _get_agent_inventory(target)

    results = {"success": True, "currency": {}, "items": {}}

    # Currency transfer
    if currency_amounts:
        if not source_purse or not target_purse:
            return {"success": False, "reason": "source or target lacks energy purse"}

        # Pre-validate all amounts
        for currency_type, amount in currency_amounts.items():
            current = getattr(source_purse, currency_type, 0)
            if current < amount:
                return {"success": False, "reason": f"insufficient {currency_type} (have {current}, need {amount})"}

        # Execute transfers
        success = source_purse.transfer_currencies_to(target_purse, currency_amounts)
        if not success:
            return {"success": False, "reason": "currency transfer failed"}
        results["currency"] = currency_amounts

    # Item transfer
    if item_amounts:
        if source_inv is None:
            return {"success": False, "reason": "source has no inventory"}

        # Pre-validate all items
        for item_key, count in item_amounts.items():
            if source_inv.get(item_key, 0) < count:
                return {"success": False, "reason": f"insufficient {item_key} (have {source_inv.get(item_key, 0)}, need {count})"}

        # Execute transfers
        if target_inv is None:
            # Create inventory for target if it doesn't have one
            target_inv = {}
            _set_agent_inventory(target, target_inv)

        for item_key, count in item_amounts.items():
            source_inv[item_key] -= count
            target_inv[item_key] = target_inv.get(item_key, 0) + count
            results["items"][item_key] = {"success": True, "count": count}

    return results


def _find_agent_by_id(agent_id: str, shared_state) -> Optional[Any]:
    """Find any agent (player, NPC, or enemy) by agent_id."""
    # Check players
    for player in getattr(shared_state, 'player_agents', []):
        if hasattr(player, 'agent_id') and player.agent_id == agent_id:
            return player

    # Check NPCs
    for npc in getattr(shared_state, 'npc_agents', []):
        if hasattr(npc, 'agent_id') and npc.agent_id == agent_id:
            return npc

    # Check enemies
    enemy_combat = getattr(shared_state, 'enemy_combat', None)
    if enemy_combat:
        for enemy in getattr(enemy_combat, 'enemy_agents', []):
            if getattr(enemy, 'agent_id', None) == agent_id:
                return enemy

    return None


def _get_agent_purse(agent) -> Optional['EnergyPurse']:
    """Get energy purse from any agent type."""
    # Player agents have character_state.energy_purse
    if hasattr(agent, 'character_state') and agent.character_state:
        return getattr(agent.character_state, 'energy_purse', None)

    # NPCs have energy_purse directly
    if hasattr(agent, 'energy_purse'):
        return agent.energy_purse

    return None


def _get_agent_inventory(agent) -> Optional[Dict[str, int]]:
    """Get inventory dict from any agent type."""
    # Player agents have character_state.inventory
    if hasattr(agent, 'character_state') and agent.character_state:
        return getattr(agent.character_state, 'inventory', None)

    # NPCs don't have a general inventory dict by default,
    # but we can create one on the fly for item transfers
    if hasattr(agent, '_inventory'):
        return agent._inventory

    return None


def _set_agent_inventory(agent, inventory: Dict[str, int]):
    """Set inventory dict on an agent (for NPCs that lack one)."""
    if hasattr(agent, 'character_state') and agent.character_state:
        agent.character_state.inventory = inventory
    else:
        agent._inventory = inventory


def _get_active_protections(entity) -> List['Condition']:
    """
    Get active protection barriers/shields for an entity.

    Returns list of Condition objects that have protection_amount set (barriers/shields).
    Used for damage interception logic.

    Args:
        entity: PlayerAgent, EnemyAgent, or NPCAgent with status_effects

    Returns:
        List of protection Conditions sorted by application order (FIFO)
    """
    if not hasattr(entity, 'status_effects'):
        return []

    from .schemas.shared_types import Condition
    protections = []

    for effect in entity.status_effects:
        # Check if this is a protection barrier (has protection_amount)
        if hasattr(effect, 'protection_amount') and effect.protection_amount is not None and effect.protection_amount > 0:
            protections.append(effect)

    return protections


def _intercept_damage_with_barriers(damage_amount: int, entity, logger_instance=None) -> tuple[int, List[str]]:
    """
    Intercept damage with active protection barriers, applying FIFO depletion.

    Args:
        damage_amount: Incoming damage before barrier absorption
        entity: Target entity with status_effects (PlayerAgent/EnemyAgent/NPCAgent)
        logger_instance: Logger for debug output

    Returns:
        Tuple of (remaining_damage_after_barriers, list_of_barrier_deplete_messages)

    Example:
        >>> remaining, messages = _intercept_damage_with_barriers(15, entity)
        >>> # Entity has "Astral Barrier" with protection_amount=10
        >>> remaining  # 5 (10 absorbed by barrier)
        >>> messages   # ["Astral Barrier absorbed 10 damage (depleted)"]
    """
    if logger_instance is None:
        logger_instance = logger

    remaining_damage = damage_amount
    messages = []

    # Get active protections (FIFO order)
    protections = _get_active_protections(entity)

    if not protections:
        return remaining_damage, messages

    # Process barriers in order until damage is absorbed or barriers depleted
    for barrier in protections:
        if remaining_damage <= 0:
            break

        absorbed = min(barrier.protection_amount, remaining_damage)
        barrier.protection_amount -= absorbed
        remaining_damage -= absorbed

        entity_name = getattr(entity, 'name', getattr(entity, 'agent_id', 'Unknown'))

        if barrier.protection_amount <= 0:
            # Barrier depleted
            messages.append(f"**{barrier.name}** absorbed {absorbed} damage (depleted)")
            logger_instance.info(f"🛡️ {entity_name}'s {barrier.name} absorbed {absorbed} damage and was depleted")

            # Mark barrier for removal (duration=0 triggers cleanup)
            barrier.duration = 0
        else:
            # Barrier still active
            messages.append(f"**{barrier.name}** absorbed {absorbed} damage ({barrier.protection_amount} protection remaining)")
            logger_instance.info(f"🛡️ {entity_name}'s {barrier.name} absorbed {absorbed} damage ({barrier.protection_amount} left)")

    return remaining_damage, messages


# ============================================================================
# Stealth State Processing (Spec 05)
# ============================================================================

def _process_stealth_changes(
    stealth_changes: List,
    shared_state: 'SharedState'
) -> None:
    """
    Process StealthChange entries from ActionResolution.effects.stealth_changes.

    Updates agent stealth flags (is_hidden, stealth_dc, last_known_position)
    and syncs TargetIDMapper hidden state for target filtering.

    Args:
        stealth_changes: List of StealthChange objects from structured output
        shared_state: SharedState for agent/mapper access
    """
    if not stealth_changes or not shared_state:
        return

    target_id_mapper = shared_state.get_target_id_mapper()

    for change in stealth_changes:
        agent_id = change.agent_id
        agent = shared_state.get_agent_by_id(agent_id)

        if not agent:
            logger.warning(f"Stealth change for unknown agent: {agent_id}")
            continue

        if change.is_hidden:
            # Agent is hiding
            agent.is_hidden = True
            agent.stealth_dc = change.stealth_dc
            # Store last known position for enemy AI reference
            if hasattr(agent, 'position'):
                agent.last_known_position = str(agent.position)
            logger.info(
                f"Stealth: {agent_id} is now HIDDEN (DC {change.stealth_dc}): "
                f"{change.reason}"
            )
        else:
            # Agent is revealed
            agent.is_hidden = False
            agent.stealth_dc = None
            agent.last_known_position = None
            logger.info(
                f"Stealth: {agent_id} is now REVEALED: {change.reason}"
            )

        # Sync target ID mapper
        if target_id_mapper:
            target_id_mapper.update_hidden_state(agent_id, change.is_hidden)


def _auto_break_stealth_on_combat(
    action: Dict[str, Any],
    shared_state: 'SharedState'
) -> bool:
    """
    Automatically break stealth when a hidden agent performs a combat action.

    Per Spec 05 Phase 4: attacking from hidden auto-breaks concealment.
    Combat action types: 'combat', 'attack', 'brawl'.

    Args:
        action: Action dict with 'action_type' and 'agent_id'
        shared_state: SharedState for agent/mapper access

    Returns:
        True if stealth was broken, False otherwise
    """
    if not action or not shared_state:
        return False

    action_type = action.get('action_type', '')
    agent_id = action.get('agent_id', '')

    if not agent_id:
        return False

    # Only break stealth for combat action types
    combat_types = ('combat', 'attack', 'brawl')
    if action_type not in combat_types:
        return False

    agent = shared_state.get_agent_by_id(agent_id)
    if not agent or not getattr(agent, 'is_hidden', False):
        return False

    # Break stealth
    agent.is_hidden = False
    agent.stealth_dc = None
    logger.info(f"Stealth auto-broken: {agent_id} attacked from hidden")

    # Update target ID mapper
    target_id_mapper = shared_state.get_target_id_mapper()
    if target_id_mapper:
        target_id_mapper.update_hidden_state(agent_id, False)

    return True


def _process_structured_damage_effects(
    damage_effects: List['DamageEffect'],
    shared_state: 'SharedState',
    current_round: int,
    mechanics: Any = None,
    logger_instance: logging.Logger = None,
    attacker_id: str = "unknown",
    attacker_name: str = "Unknown Attacker",
    weapon: str = "Unknown Weapon",
    attack_roll: Optional[Dict[str, Any]] = None,
    resolved_damage_type: Optional[str] = None,
    declared_weapon: Optional[str] = None
) -> List[str]:
    """
    Process List[DamageEffect] from ActionResolution, applying barrier interception and damage.

    This is the NEW damage processing pipeline for structured output. Replaces legacy
    keyword-based damage parsing.

    Args:
        damage_effects: List of DamageEffect objects from ActionResolution.effects.damage
        shared_state: SharedState for entity resolution
        current_round: Current round number for logging
        mechanics: Mechanics engine for JSONL logging (optional)
        logger_instance: Logger instance (optional)
        attacker_id: Agent ID of the attacker (from player action context)
        attacker_name: Name of the attacker (from player action context)
        weapon: Weapon used in attack (from player action context)
        attack_roll: d20 roll data for ML logging (attr, skill, d20, total, dc, hit, margin)

    Returns:
        List of narrative messages describing damage outcomes (for appending to DM narration)

    Example:
        >>> damage_effects = [DamageEffect(target="tgt_7a3f", base_damage=15, dealt=15)]
        >>> messages = _process_structured_damage_effects(damage_effects, shared_state, 1)
        >>> messages  # ["⚔️ Enemy takes 15 damage! (8 health → 0, +3 wounds)", "💀 Enemy is defeated!"]
    """
    if logger_instance is None:
        logger_instance = logger

    if not damage_effects:
        return []

    # Contract-gear Soulcredit lock (deterministic backstop): if the attacker's
    # weapon is soulcredit_locked and their standing is below its floor, the
    # weapon never fired — drop ALL damage regardless of what the DM narrated.
    # (Debtbreaker Sidearm "locks if Soulcredit < 0"; Gear & Tech Ref v1.2.2.)
    _sc_states = getattr(mechanics, 'soulcredit_states', None)
    if isinstance(_sc_states, dict) and attacker_id in _sc_states:
        from .weapons import get_weapon_by_name, weapon_is_sc_locked
        weapon_obj = get_weapon_by_name(weapon)
        wielder_sc = _sc_states[attacker_id].score
        if weapon_obj is not None and weapon_is_sc_locked(weapon_obj, wielder_sc):
            msg = (f"⛔ {weapon} LOCKED: {attacker_name}'s Soulcredit ({wielder_sc}) "
                   f"is below the contract floor — the weapon clicks dead (Codex ping). "
                   f"No damage dealt.")
            logger_instance.warning(msg)
            return [msg]

    messages = []
    target_id_mapper = shared_state.get_target_id_mapper() if shared_state else None

    for damage_effect in damage_effects:
        target_identifier = damage_effect.target
        damage_amount = damage_effect.dealt  # Use final damage (post-soak)

        # Resolve target entity
        target_entity = None
        target_name = None
        is_friendly_fire = False

        if target_identifier.startswith('tgt_'):
            # Target ID resolution (free targeting mode)
            if target_id_mapper and target_id_mapper.enabled:
                target_entity = target_id_mapper.resolve_target(target_identifier)

                # Check if target is a player (friendly fire)
                if target_entity and target_id_mapper.is_player(target_identifier):
                    is_friendly_fire = True
                    target_name = getattr(target_entity.character_state, 'name', 'Unknown') if hasattr(target_entity, 'character_state') else 'Unknown'
                    logger_instance.warning(f"🔥 FRIENDLY FIRE: Structured damage targeting PC {target_name} (ID: {target_identifier})")
                elif target_entity:
                    target_name = target_entity.name
        else:
            # Character name resolution (legacy fallback)
            target_name = target_identifier

            # Try to find entity by name
            if shared_state:
                # Try enemies first
                enemy_combat = shared_state.enemy_combat
                if enemy_combat:
                    from .enemy_spawner import get_active_enemies
                    active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                    for enemy in active_enemies:
                        if target_name and (target_name.lower() in enemy.name.lower() or
                                            enemy.name.lower() in target_name.lower()):
                            target_entity = enemy
                            break

                # Try NPCs if not found
                if not target_entity and hasattr(shared_state, 'npc_agents'):
                    for npc in shared_state.npc_agents:
                        if npc.is_active and target_name and (target_name.lower() in npc.name.lower() or
                                                               npc.name.lower() in target_name.lower()):
                            target_entity = npc
                            break

        if not target_entity:
            logger_instance.warning(f"⚠️ Could not resolve damage target: {target_identifier}")
            messages.append(f"⚠️ **Target '{target_identifier}' not found for damage**")
            continue

        # === ENVIRONMENTAL OBJECT DAMAGE ===
        # Env objects use simple HP reduction (no barrier interception, no wound/stun)
        from .shared_state import EnvironmentalObject as _EnvObj
        if isinstance(target_entity, _EnvObj):
            actual_damage = target_entity.apply_damage(damage_amount)
            if actual_damage > 0:
                health_before = target_entity.health + actual_damage
                messages.append(
                    f"** {target_entity.name} takes {actual_damage} damage! "
                    f"({health_before} -> {target_entity.health} HP)"
                )
                if target_entity.is_destroyed:
                    messages.append(f"** {target_entity.name} is DESTROYED!")
                    logger_instance.info(f"Environmental object destroyed: {target_entity.name} ({target_entity.object_id})")

                    # Log destruction event
                    if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                        try:
                            mechanics.jsonl_logger.log_env_object_damage(
                                round_num=current_round,
                                object_id=target_entity.object_id,
                                object_name=target_entity.name,
                                damage_dealt=actual_damage,
                                health_before=health_before,
                                health_after=0,
                                destroyed=True,
                                attacker_id=attacker_id
                            )
                        except (AttributeError, TypeError):
                            pass  # Logger may not have this method yet
                else:
                    logger_instance.info(
                        f"Environmental object damaged: {target_entity.name} "
                        f"({target_entity.health}/{target_entity.max_health} HP)"
                    )
            elif not target_entity.is_destructible:
                messages.append(f"** {target_entity.name} is impervious to damage!")
                logger_instance.info(f"Damage blocked: {target_entity.name} is non-destructible")
            continue  # Skip combatant damage logic

        # Target didn't resolve to a tracked entity (e.g. the DM narrated harm to
        # a non-combatant suspect/prisoner in a coercion/violence scene). Keep the
        # narration; skip mechanical HP application rather than crash on None.
        if target_entity is None:
            logger_instance.debug(
                f"Damage target unresolved ({getattr(damage_effect, 'target', '?')}); "
                f"skipping mechanical damage application")
            continue

        # === BARRIER INTERCEPTION ===
        damage_after_barriers, barrier_messages = _intercept_damage_with_barriers(
            damage_amount,
            target_entity,
            logger_instance
        )

        # Add barrier messages to output
        if barrier_messages:
            messages.extend([f"🛡️ {msg}" for msg in barrier_messages])

        # === APPLY DAMAGE TO ENTITY (damage type routing) ===
        if damage_after_barriers > 0:
            from .mechanics import apply_stun_damage, apply_wound_damage, apply_mixed_damage

            old_health = target_entity.health
            old_stuns = getattr(target_entity, 'stuns', 0)
            old_wounds = getattr(target_entity, 'wounds', 0)

            # Priority: backend-resolved weapon type > LLM's DamageEffect.damage_type > "wound" default
            mechanical_type = resolved_damage_type or damage_effect.damage_type or "wound"
            if mechanical_type not in ("stun", "wound", "mixed"):
                mechanical_type = "wound"  # Normalize freeform types (kinetic, bludgeoning, etc.)

            friendly_fire_label = " [FRIENDLY FIRE]" if is_friendly_fire else ""

            if mechanical_type == "stun":
                result = apply_stun_damage(target_entity, damage_after_barriers)
                wounds_dealt = 0
                stuns_dealt = result['stuns_dealt']
                messages.append(
                    f"⚡ **{target_name} takes {damage_after_barriers} stun damage!** "
                    f"(stuns: {old_stuns} → {target_entity.stuns}){friendly_fire_label}"
                )
            elif mechanical_type == "mixed":
                result = apply_mixed_damage(target_entity, damage_after_barriers)
                wounds_dealt = result['wounds_dealt']
                stuns_dealt = result['stuns_dealt']
                messages.append(
                    f"⚔️ **{target_name} takes {damage_after_barriers} mixed damage!** "
                    f"(stuns: {old_stuns} → {target_entity.stuns}, "
                    f"{old_health} HP → {target_entity.health} HP, +{wounds_dealt} wounds){friendly_fire_label}"
                )
            else:  # "wound"
                result = apply_wound_damage(target_entity, damage_after_barriers)
                wounds_dealt = result['wounds_dealt']
                stuns_dealt = 0
                messages.append(
                    f"⚔️ **{target_name} takes {damage_after_barriers} damage!** "
                    f"({old_health} HP → {target_entity.health} HP, +{wounds_dealt} wounds){friendly_fire_label}"
                )

            if is_friendly_fire:
                logger_instance.warning(
                    f"🔥 FRIENDLY FIRE DAMAGE: {damage_after_barriers} {mechanical_type} to {target_name}"
                )
            else:
                logger_instance.info(
                    f"Damage dealt: {damage_after_barriers} {mechanical_type} to {target_name}"
                )

            # === CHECK FOR DEFEAT ===
            defeat_logged = False
            defeat_reason = None
            is_stun_only = (mechanical_type == "stun")
            # Skip defeat processing if target already inactive (killed by earlier action this round)
            already_defeated = hasattr(target_entity, 'is_active') and not target_entity.is_active

            if already_defeated:
                pass  # Don't log duplicate defeat
            elif is_stun_only and result.get('unconscious_check_needed'):
                # Stun KO — non-lethal incapacitation
                logger_instance.info(f"{target_name} knocked unconscious by stun damage!")
                messages.append(f"😵 **{target_name} is knocked unconscious!**")
                if hasattr(target_entity, 'is_active'):
                    target_entity.is_active = False
                defeat_reason = "unconscious"
                defeat_logged = True
            elif not is_stun_only and target_entity.health <= 0:
                # Wound/mixed defeat — existing logic
                if hasattr(target_entity, 'check_death_save'):
                    alive, status = target_entity.check_death_save()
                    if not alive:
                        logger_instance.info(f"{target_name} KILLED by attack!")
                        messages.append(f"💀 **{target_name} is KILLED!**")
                        if hasattr(target_entity, 'is_active'):
                            target_entity.is_active = False
                        defeat_reason = "killed"
                        defeat_logged = True
                    elif status == "unconscious":
                        logger_instance.info(f"{target_name} knocked unconscious!")
                        messages.append(f"😵 **{target_name} is knocked unconscious!**")
                        if hasattr(target_entity, 'is_active'):
                            target_entity.is_active = False
                        defeat_reason = "unconscious"
                        defeat_logged = True
                    else:
                        logger_instance.info(f"{target_name} critically wounded but conscious!")
                        messages.append(f"⚠️ **{target_name} is critically wounded!**")
                else:
                    logger_instance.info(f"{target_name} defeated!")
                    messages.append(f"💀 **{target_name} is defeated!**")
                    if hasattr(target_entity, 'is_active'):
                        target_entity.is_active = False
                    defeat_reason = "killed"
                    defeat_logged = True

            # Log enemy defeat event for ML training (only for actual enemies, not PCs)
            if defeat_logged and mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                if hasattr(target_entity, 'agent_id') and hasattr(target_entity, 'spawned_round'):
                    spawned = getattr(target_entity, 'spawned_round', None)
                    rounds_survived = current_round - spawned if isinstance(spawned, int) else 0
                    mechanics.jsonl_logger.log_enemy_defeat(
                        round_num=current_round,
                        enemy_id=target_entity.agent_id,
                        enemy_name=target_name,
                        defeat_reason=defeat_reason,
                        rounds_survived=rounds_survived,
                        killer_id=attacker_id,
                        killer_name=attacker_name,
                        final_damage=damage_after_barriers
                    )

            # === LOG COMBAT ACTION (ML TRAINING) ===
            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                defender_state = {
                    "health": target_entity.health,
                    "max_health": target_entity.max_health,
                    "wounds": target_entity.wounds,
                    "stuns": getattr(target_entity, 'stuns', 0),
                    "alive": target_entity.health > 0 or is_stun_only,
                    "status": "active" if (target_entity.health > 0 or is_stun_only) and not defeat_logged else "defeated"
                }

                damage_roll_data = {
                    "base_damage": damage_effect.base_damage,
                    "soak": damage_effect.soak if damage_effect.soak is not None else 0,
                    "mechanical_soak": getattr(target_entity, 'soak', None),
                    "dealt": damage_after_barriers,
                    "damage_type": mechanical_type
                }

                entity_id = getattr(target_entity, 'agent_id', None) or getattr(target_entity, 'vendor_id', 'unknown')
                mechanics.jsonl_logger.log_combat_action(
                    round_num=current_round,
                    attacker_id=attacker_id,
                    attacker_name=attacker_name,
                    defender_id=entity_id,
                    defender_name=target_name,
                    weapon=weapon,
                    declared_weapon=declared_weapon,
                    attack_roll=attack_roll or {},
                    damage_roll=damage_roll_data,
                    wounds_dealt=wounds_dealt,
                    defender_state_after=defender_state
                )
        elif damage_amount > 0:
            # All damage was absorbed by barriers (damage_after_barriers == 0)
            messages.append(f"🛡️ **{target_name}'s barriers completely absorbed the attack!**")
            logger_instance.info(f"🛡️ {target_name}'s barriers completely absorbed {damage_amount} damage")

    return messages


def _process_structured_healing_effects(
    healing_effects: List['HealingEffect'],
    shared_state: 'SharedState',
    current_round: int,
    mechanics: Any = None,
    logger_instance: logging.Logger = None
) -> List[str]:
    """
    Process List[HealingEffect] from ActionResolution, applying HP/stun/wound recovery.

    This is the NEW healing processing pipeline for structured output. Replaces legacy
    keyword-based healing parsing.

    Args:
        healing_effects: List of HealingEffect objects from ActionResolution.effects.healing
        shared_state: SharedState for entity resolution
        current_round: Current round number for logging
        mechanics: Mechanics engine for JSONL logging (optional)
        logger_instance: Logger instance (optional)

    Returns:
        List of narrative messages describing healing outcomes (for appending to DM narration)

    Example:
        >>> healing_effects = [HealingEffect(target="tgt_7a3f", hp=10, stun=5, wounds=1)]
        >>> messages = _process_structured_healing_effects(healing_effects, shared_state, 1)
        >>> messages  # ["💚 Ally healed: +10 HP, -5 stun, -1 wounds (15 HP → 25 HP)"]
    """
    if logger_instance is None:
        logger_instance = logger

    if not healing_effects:
        return []

    messages = []
    target_id_mapper = shared_state.get_target_id_mapper() if shared_state else None

    for healing_effect in healing_effects:
        target_identifier = healing_effect.target
        heal_type = healing_effect.heal_type  # "hp", "stun", or "wound"
        amount = healing_effect.amount

        # Resolve target entity
        target_entity = None
        target_name = None

        if target_identifier.startswith('tgt_'):
            # Target ID resolution (free targeting mode)
            if target_id_mapper and target_id_mapper.enabled:
                target_entity = target_id_mapper.resolve_target(target_identifier)

                if target_entity:
                    # Check if PC or enemy/NPC
                    if hasattr(target_entity, 'character_state'):
                        target_name = target_entity.character_state.name
                    else:
                        target_name = target_entity.name
        else:
            # Character name resolution (legacy fallback)
            target_name = target_identifier

            # Try to find entity by name
            if shared_state:
                # Try players first
                if hasattr(shared_state, 'player_agents'):
                    for player in shared_state.player_agents:
                        if hasattr(player, 'character_state'):
                            char_name = player.character_state.name
                            if target_name and (target_name.lower() in char_name.lower() or
                                                char_name.lower() in target_name.lower()):
                                target_entity = player
                                target_name = char_name
                                break

                # Try enemies
                if not target_entity:
                    enemy_combat = shared_state.enemy_combat
                    if enemy_combat:
                        from .enemy_spawner import get_active_enemies
                        active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                        for enemy in active_enemies:
                            if target_name and (target_name.lower() in enemy.name.lower() or
                                                enemy.name.lower() in target_name.lower()):
                                target_entity = enemy
                                break

                # Try NPCs
                if not target_entity and hasattr(shared_state, 'npc_agents'):
                    for npc in shared_state.npc_agents:
                        if npc.is_active and target_name and (target_name.lower() in npc.name.lower() or
                                                               npc.name.lower() in target_name.lower()):
                            target_entity = npc
                            break

        if not target_entity:
            logger_instance.warning(f"⚠️ Could not resolve healing target: {target_identifier}")
            messages.append(f"⚠️ **Target '{target_identifier}' not found for healing**")
            continue

        # === DEFEAT/DEATH GUARD ===
        target_wounds = getattr(target_entity, 'wounds', 0)
        target_health = getattr(target_entity, 'health', 1)

        # Permanently dead (failed death save): reject all healing
        if getattr(target_entity, '_permanently_dead', False):
            logger_instance.warning(
                f"⚠️ Healing rejected: {target_name} is permanently dead (failed death save) — beyond saving"
            )
            messages.append(f"⚠️ **{target_name} is dead (failed death save) — beyond saving**")
            continue

        # Dead (wounds >= 6): reject all healing
        if target_wounds >= 6:
            logger_instance.warning(
                f"⚠️ Healing rejected: {target_name} is dead (wounds: {target_wounds}) — beyond saving"
            )
            messages.append(f"⚠️ **{target_name} is dead (wounds: {target_wounds}) — beyond saving**")
            continue

        # Defeated/unconscious (health <= 0): cap HP healing at stabilization
        is_unconscious = target_health <= 0

        # === APPLY HEALING TO ENTITY ===
        healing_summary = []
        old_health = target_entity.health
        old_wounds = target_entity.wounds
        old_stuns = getattr(target_entity, 'stuns', 0)

        # Apply healing based on type
        if heal_type == "hp":
            if is_unconscious:
                # Stabilize only: cap at 1 HP (not full heal)
                target_entity.health = 1
                actual_heal = target_entity.health - old_health
                healing_summary.append(f"stabilized to 1 HP")
            else:
                # Restore HP (capped at max_health)
                target_entity.health = min(target_entity.health + amount, target_entity.max_health)
                actual_heal = target_entity.health - old_health
                healing_summary.append(f"+{actual_heal} HP")
        elif heal_type == "stun":
            # Remove stun damage (field medicine) — actually reduce the stun track.
            # This is the ONLY mid-combat path out of Beaten (auto stun-recovery is
            # off), so it must mutate state, not just narrate.
            target_entity.stuns = max(0, old_stuns - amount)
            actual_stuns_healed = old_stuns - target_entity.stuns
            healing_summary.append(f"-{actual_stuns_healed} stun")
        elif heal_type == "wound":
            # Reduce wounds
            target_entity.wounds = max(0, target_entity.wounds - amount)
            actual_wounds_healed = old_wounds - target_entity.wounds
            healing_summary.append(f"-{actual_wounds_healed} wounds")

        if healing_summary:
            summary_text = ", ".join(healing_summary)
            if is_unconscious and heal_type == "hp":
                messages.append(
                    f"🩹 **{target_name} stabilized: {summary_text}** "
                    f"({old_health} HP → {target_entity.health} HP)"
                )
            else:
                messages.append(
                    f"💚 **{target_name} healed: {summary_text}** "
                    f"({old_health} HP → {target_entity.health} HP)"
                )

            logger_instance.info(
                f"Healing applied: {summary_text} to {target_name} "
                f"({old_health} → {target_entity.health} HP, wounds: {target_entity.wounds})"
            )

            # === LOG HEALING ACTION (ML TRAINING) ===
            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                # Determine status: stabilized (was unconscious) vs active (was conscious)
                if is_unconscious:
                    heal_status = "stabilized"
                elif target_entity.health > 0:
                    heal_status = "active"
                else:
                    heal_status = "defeated"

                target_state_after = {
                    "health": target_entity.health,
                    "max_health": target_entity.max_health,
                    "wounds": target_entity.wounds,
                    "stuns": getattr(target_entity, 'stuns', 0),
                    "alive": target_entity.health > 0,
                    "status": heal_status
                }

                # Note: Would ideally log as 'healing_action' event type
                # For now, log minimal info to existing event types
                # Get entity ID (vendors use vendor_id instead of agent_id)
                heal_target_id = getattr(target_entity, 'agent_id', None) or getattr(target_entity, 'vendor_id', 'unknown')
                mechanics.jsonl_logger.log_event(
                    'healing_applied',
                    {
                        'target_id': heal_target_id,
                        'target_name': target_name,
                        'heal_type': heal_type,
                        'amount': amount,
                        'hp_restored': target_entity.health - old_health if heal_type == "hp" else 0,
                        'stun_removed': (old_stuns - target_entity.stuns) if heal_type == "stun" else 0,
                        'wounds_reduced': (old_wounds - target_entity.wounds) if heal_type == "wound" else 0,
                        'target_state_after': target_state_after
                    },
                    current_round
                )

    return messages


def _build_enhanced_previous_context(previous_resolutions: List[Dict[str, Any]]) -> str:
    """Build enhanced in-round context showing SC changes for each prior action.

    Args:
        previous_resolutions: List of earlier resolved actions this round.

    Returns:
        Formatted context string, or empty string if no resolutions.
    """
    if not previous_resolutions:
        return ""

    items = []
    for i, prev in enumerate(previous_resolutions[-3:], 1):
        char_name = prev.get('character_name', 'Unknown')
        # Guard: action/resolution/effects may be None, a string, or a dict
        # Handle both PC format (action is dict) and enemy format (action is string)
        raw_action = prev.get('action')
        if isinstance(raw_action, dict):
            action_type = raw_action.get('action_type', 'unknown').upper()
        elif isinstance(raw_action, str):
            action_type = raw_action.upper()
        else:
            action_type = 'UNKNOWN'

        # Extract margin from nested resolution (PC), roll dict (enemy), or top-level
        raw_resolution = prev.get('resolution')
        resolution_dict = raw_resolution if isinstance(raw_resolution, dict) else {}
        margin = resolution_dict.get('margin', '?')
        if margin == '?':
            roll = prev.get('roll')
            if isinstance(roll, dict):
                margin = roll.get('margin', '?')
        if margin == '?':
            margin = prev.get('margin', '?')
        narration = prev.get('narration', '')
        # Truncate narration for recap
        narration_brief = narration[:120] + '...' if len(narration) > 120 else narration

        # Extract SC changes
        raw_effects = prev.get('effects')
        effects_dict = raw_effects if isinstance(raw_effects, dict) else {}
        sc_changes = effects_dict.get('soulcredit_changes', [])
        if sc_changes:
            sc_parts = []
            for sc in sc_changes:
                amt = sc.get('amount', 0)
                reason = sc.get('reason', '')
                sc_parts.append(f"{amt:+d} {reason}" if reason else f"{amt:+d}")
            sc_text = f"[SC: {', '.join(sc_parts)}]"
        else:
            sc_text = "[SC: +0]"

        # Detect success: check resolution dict, hit field, result field, then margin
        if isinstance(raw_resolution, dict) and 'success' in resolution_dict:
            success = "success" if resolution_dict['success'] else "failure"
        elif prev.get('hit') is not None:
            success = "success" if prev['hit'] else "failure"
        elif prev.get('result') in ('success', 'failure', 'invalidated'):
            success = prev['result']
        else:
            success = "success" if isinstance(margin, (int, float)) and margin >= 0 else "failure"
        margin_str = f"{margin:+d}" if isinstance(margin, (int, float)) else str(margin)

        # Add prefix for skipped/invalidated actions
        prefix = ""
        if prev.get('action_skipped'):
            skip_reason = prev.get('skip_reason', 'preempted')
            prefix = f"[SKIPPED - {skip_reason}] "
        elif prev.get('result') == 'invalidated':
            prefix = "[INVALIDATED] "

        items.append(f"{i}. {prefix}{char_name}: {action_type} ({success}, {margin_str}) → {narration_brief} {sc_text}")

    return (
        "\n**⚠️ CRITICAL - EARLIER ACTIONS THIS ROUND:**\n\n"
        + "\n".join(items)
        + "\n\n**CONSISTENCY REQUIREMENTS:**\n"
        "- Your narration MUST acknowledge these established facts\n"
        "- DO NOT contradict details from earlier resolutions\n"
        "- Build on the tactical/narrative situation they created\n"
        "- If earlier action changed environment (collapsed structure, dropped item), ACKNOWLEDGE IT\n"
    )


@dataclass
class Scenario:
    """Current game scenario state."""
    theme: str
    location: str
    situation: str
    active_npcs: List[str]
    environmental_factors: List[str]
    void_level: int
    active_vendors: List[Vendor] = None  # Vendors present in this scenario (can be multiple)
    required_purchase: Optional[str] = None  # Item that MUST be purchased to proceed
    vendor_gate_description: Optional[str] = None  # Description of why purchase is needed

    def __post_init__(self):
        """Ensure active_vendors is always a list."""
        if self.active_vendors is None:
            self.active_vendors = []



def active_enemy_count(shared_state) -> int:
    """How many enemies are actually in play.

    Enemies live on `enemy_combat`, not on `SharedState` (#120). Three call
    sites here guarded on `hasattr(self.shared_state, 'enemy_agents')`, an
    attribute that has never existed, so all three branches were dead and
    silent — a hasattr guard against a missing attribute simply never fires.

    Two of them fed DM prompt context, so `"Outnumbered ("` appeared 0 times in
    60,728 recorded LLM events: the DM has never once been told it was
    outnumbered.

    Inactive enemies are excluded — a defeated tombstone must not inflate the
    number the DM reasons about.
    """
    combat = getattr(shared_state, "enemy_combat", None) if shared_state else None
    return sum(1 for e in (getattr(combat, "enemy_agents", None) or [])
               if getattr(e, "is_active", True))


class AIDMAgent(Agent):
    """
    AI Dungeon Master agent that orchestrates scenarios, controls NPCs,
    and drives narrative forward.
    """
    
    def __init__(
        self,
        agent_id: str,
        socket_path: str,
        llm_config: Dict[str, Any],
        *,
        voice_profile: Optional[VoiceProfile] = None,
        shared_state: Optional[SharedState] = None,
        prompt_enricher: Optional[Callable[..., str]] = None,
        history_supplier: Optional[Callable[[], Iterable[str]]] = None,
        force_scenario: Optional[str] = None,
        llm_logger: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        agent_prompt_logger: Optional[Any] = None,
        session_config: Optional[Dict[str, Any]] = None,
        names_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, socket_path)
        self.llm_config = llm_config
        self.current_scenario: Optional[Scenario] = None
        self.voice_profile = voice_profile
        self.shared_state = shared_state
        self._prompt_enricher = prompt_enricher
        self._history_supplier = history_supplier
        self.force_scenario = force_scenario  # For automated testing
        self.llm_logger = llm_logger  # LLMCallLogger for replay functionality
        self.agent_prompt_logger = agent_prompt_logger  # AgentPromptLogger for human-readable debugging
        self._last_prompt_metadata = None  # Track prompt version/metadata for logging
        self.session_config = session_config or {}  # Session config for persistent vendors, etc.
        self.names_client = names_client  # Optional aeonisk-names-mcp client; None = LLM-named NPCs

        # LLM client - can be injected for replay (MockLLMClient) or created normally
        if llm_client:
            self.llm_client = llm_client
        else:
            # Create Anthropic client if not provided
            import anthropic
            import os
            self.llm_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # Vendor pool for random encounters
        self.vendor_pool = create_standard_vendors()

        # Load persistent vendors from config and add to SharedState
        if self.session_config and self.shared_state:
            persistent_vendors = self._load_persistent_vendors(self.session_config)
            for vendor in persistent_vendors:
                self.shared_state.add_vendor(vendor)
                logger.info(f"🏪 Persistent vendor loaded at session start: {vendor.name}")

        # Story progression flags
        self.needs_story_advancement = False  # Set by session when all clocks complete

        # Rolling narrative digest for adjudication context (mirrors session._round_synthesis_history)
        self._round_synthesis_history: List[tuple] = []

        # LLM Provider for structured output (supports all providers: Anthropic, OpenAI, local)
        # Only create if not in replay mode (llm_client injected)
        if not llm_client:
            from .llm_provider import LLMConfig, create_provider
            try:
                provider_config = LLMConfig.from_dict(
                    self.llm_config, max_tokens=4000, agent_id=self.agent_id)
                self.llm_provider = create_provider(provider_config)
                logger.debug(f"DM: LLM provider initialized ({provider_config.provider}:{provider_config.model})")
            except Exception as e:
                logger.warning(f"DM: Failed to create LLM provider: {e}")
                self.llm_provider = None
        else:
            # Replay mode - no structured output
            self.llm_provider = None

        # Set up DM-specific message handlers
        self.message_handlers[MessageType.SESSION_START] = self._handle_session_start
        self.message_handlers[MessageType.ACTION_DECLARED] = self._handle_action_declared
        self.message_handlers[MessageType.TURN_REQUEST] = self._handle_turn_request
        self.message_handlers[MessageType.AGENT_REGISTER] = self._handle_agent_register
        self.message_handlers[MessageType.DM_NARRATION] = self._handle_dm_narration

    async def on_start(self):
        """Initialize DM agent."""
        logger.debug(f"AI DM {self.agent_id} started")
        
        # Announce readiness
        self.send_message_sync(
            MessageType.AGENT_READY,
            None,  # broadcast
            {'agent_type': 'dm', 'capabilities': ['scenario_generation', 'npc_control', 'narrative']}
        )

        print(f"\n[DM {self.agent_id}] AI Dungeon Master ready")
        
    async def on_shutdown(self):
        """Cleanup on shutdown."""
        logger.debug(f"AI DM {self.agent_id} shutting down")

    def _get_required_dm_modules(self, action_type: str = None) -> List[str]:
        """
        Determine which DM prompt modules to load based on current game state and action type.

        Args:
            action_type: The action type being resolved (combat, investigate, social, etc.)
                        If None, loads generic modules only (for non-resolution contexts).

        Returns:
            List of module names to load (e.g., ['dm_core', 'dm_resolution_combat'])
        """
        modules = []

        # Always load core modules
        modules.append('dm_core')
        modules.append('dm_structured_output_base')  # Slim base schema (replaces monolithic dm_structured_output)

        # Action-type-specific resolution guidance (reduces prompt size, improves LLM focus)
        if action_type:
            action_type_lower = action_type.lower()
            resolution_map = {
                'combat': 'dm_resolution_combat',
                'investigate': 'dm_resolution_investigate',  # Item discovery, looting, searching
                'social': 'dm_resolution_social',
                'ritual': 'dm_resolution_ritual',
                'attune': 'dm_attunement',          # Already specialized
                'support': 'dm_resolution_support',
                'explore': 'dm_resolution_movement',
                'perception': 'dm_resolution_perception',   # Awareness, threat detection (NO items)
                'technical': 'dm_resolution_investigate',   # Hacking can find data/items
                'purchase': 'dm_purchase',          # Already specialized
                'transfer': 'dm_transfer',          # Already specialized
                'consume': 'dm_consumption',        # Already specialized
            }
            if action_type_lower in resolution_map:
                module_name = resolution_map[action_type_lower]
                # Experiment: swap combat resolution for suppression-inclusive variant
                if module_name == 'dm_resolution_combat':
                    session_cfg = getattr(self, 'session_config', {})
                    experiment = session_cfg.get('experiment', {}) if session_cfg else {}
                    if experiment.get('include_suppression_resolution_example', False):
                        module_name = 'dm_resolution_combat_with_suppression'
                        logger.debug("DM: Swapping combat module for suppression-inclusive variant (experiment flag)")
                modules.append(module_name)
                logger.debug(f"DM: Loading action-specific module for {action_type}: {module_name}")
            else:
                # Unknown action type - load generic discovery for fallback
                logger.debug(f"DM: Unknown action type '{action_type}', no action-specific module")

        # Always load dm_commands (contains NPC/enemy spawning, escalation triggers)
        # DM needs to know it CAN spawn NPCs and WHEN to escalate even if none present yet
        modules.append('dm_commands')

        # Conditional: Load dm_combat if enemies present
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat') and self.shared_state.enemy_combat:
            enemy_agents = getattr(self.shared_state.enemy_combat, 'enemy_agents', [])
            if len(enemy_agents) > 0:
                modules.append('dm_combat')
                logger.debug(f"DM: Loading dm_combat module ({len(enemy_agents)} enemies present)")

        # Conditional: Load state tracking if clocks or rituals expected
        if self.shared_state and hasattr(self.shared_state, 'mechanics_engine'):
            mechanics = self.shared_state.mechanics_engine
            has_clocks = mechanics and len(mechanics.scene_clocks) > 0
            # For now, always load state_tracking (safe default)
            # TODO: Detect ritual actions to conditionally load
            if has_clocks or True:  # Always load for now
                modules.append('dm_state_tracking')
                if has_clocks:
                    logger.debug(f"DM: Loading dm_state_tracking module ({len(mechanics.scene_clocks)} clocks)")

        # Conditional: Load ML training module if JSONL logging enabled
        if self.shared_state and hasattr(self.shared_state, 'mechanics_engine'):
            mechanics = self.shared_state.mechanics_engine
            has_jsonl = mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger
            if has_jsonl:
                modules.append('dm_ml_training')
                logger.debug("DM: Loading dm_ml_training module (JSONL logging enabled)")

        # Conditional: Load social module if recent player dialogue
        # For now, always skip (rarely needed)
        # TODO: Detect PC-to-PC dialogue to conditionally load

        logger.debug(f"DM: Selected {len(modules)} modules: {', '.join(modules)}")
        return modules

    def _get_party_personalities(self) -> str:
        """Get personality summaries for all party members (DM needs full party awareness).

        Returns formatted string with all party member personality descriptions,
        enabling the DM to write personality-appropriate narration and have NPCs
        react appropriately to different party members.

        Returns:
            Formatted string with party personalities, or empty string if none available.
        """
        if not self.shared_state or not self.shared_state.registered_players:
            return ""

        lines = []
        for player in self.shared_state.registered_players:
            if player.get('personality_description'):
                lines.append(f"- **{player['name']}**: {player['personality_description']}")

        if not lines:
            return ""
        return "\n**Party Personalities:**\n" + "\n".join(lines)

    async def _handle_session_start(self, message: Message):
        """Handle session start - generate initial scenario."""
        config = message.payload.get('config', {})
        self.config = config  # Store for later use

        await self._generate_ai_scenario(config)
            
    async def _generate_ai_scenario(self, config: Dict[str, Any]):
        """Generate scenario using AI with lore grounding."""
        # Check for forced scenario (automated testing)
        if self.force_scenario:
            logger.info(f"Using forced scenario for testing: {self.force_scenario}")
            await self._use_forced_scenario(self.force_scenario, config)
            return

        # Check if config already has a scenario defined
        if 'scenario' in config and config['scenario']:
            logger.info("Using scenario from config file")
            await self._use_config_scenario(config['scenario'], config)
            return

        # Check if vendor-gated or combat scenario is requested
        force_vendor_gate = config.get('force_vendor_gate', False)
        force_combat = config.get('force_combat', False)

        # Query knowledge retrieval for Aeonisk lore
        lore_context = ""
        variety_context = ""
        party_context = ""

        # Extract player information from config
        players_config = config.get('agents', {}).get('players', [])
        if players_config:
            party_context = "=== PARTY COMPOSITION ===\n"
            party_context += "Your scenario MUST be appropriate for this specific party:\n\n"

            for player in players_config:
                name = player.get('name', 'Unknown')
                faction = player.get('faction', 'Unknown')
                goals = player.get('goals', [])

                party_context += f"**{name}** ({faction})\n"
                party_context += f"  Goals:\n"
                for goal in goals:
                    party_context += f"  - {goal}\n"
                party_context += "\n"

            party_context += "CRITICAL FACTION RULES:\n"
            party_context += "- DO NOT create scenarios where characters must betray their own faction\n"
            party_context += "- DO NOT hire characters to steal from/sabotage their own faction's assets\n"
            party_context += "- Sovereign Nexus owns: Codex Cathedral, Sanctified Archives, Gestation Chambers, Ley Networks\n"
            party_context += "- Pantheon Security owns: Law enforcement facilities, civic infrastructure, security systems\n"
            party_context += "- ACG owns: Debt registries, contract archives, commerce hubs\n"
            party_context += "- ArcGen owns: Biocreche facilities, genetic research labs, pod gestation tech\n"
            party_context += "- Tempest owns: Void energy facilities, industrial complexes, autonomous systems\n"
            party_context += "- If creating faction conflict scenarios, make it BETWEEN different factions, not against one's own\n"
            party_context += "- Characters should be aligned with their faction's interests OR face a clear moral dilemma\n\n"

        if self.shared_state:
            knowledge = self.shared_state.get_knowledge_retrieval()
            if knowledge:
                # Query for canonical locations, factions, and setting elements
                lore_results = knowledge.query("Aeonisk setting locations factions floating cities Arcadia Nimbus Elysium void corruption", n_results=3)
                if lore_results:
                    lore_context = "CANONICAL AEONISK LORE (you MUST use this):\n\n"
                    for result in lore_results:
                        lore_context += f"{result['content'][:400]}\n\n"
                    lore_context += "\nKEY CONSTRAINTS:\n"
                    lore_context += "- Setting: Three inhabited planets (Aeonisk Prime, Nimbus, Arcadia) with space travel between them\n"
                    lore_context += "- Species: Humans only (NO aliens, NO other species)\n"
                    lore_context += "- Locations: Floating cities, terrestrial zones, orbital stations, space transit\n"
                    lore_context += "- Factions: Tempest Industries, Resonance Communes, Astral Commerce Group, Arcane Genetics, Pantheon Security, House of Vox, Sovereign Nexus, Freeborn\n"
                    lore_context += "- Eye of Breach: Rogue AI aligned with Tempest Industries, appears during high void corruption\n"
                    lore_context += "- Themes: Memory manipulation, void corruption, corporate intrigue, bond economics\n\n"

            # Get variety requirements
            variety_context = self.shared_state.get_recent_scenario_info()

        # Use vendor-gated or combat scenario if requested
        if force_vendor_gate:
            logger.debug("Force vendor gate enabled - using vendor-gated scenario template")
            scenario_data = self._create_vendor_gated_scenario()
        elif force_combat:
            logger.debug("Force combat enabled - using combat scenario template")
            scenario_data = self._create_combat_scenario(config)
        else:
            # Check for scenario constraints/hints (top-level config, with legacy fallback)
            scenario_hint = config.get('scenario_hint', '') or config.get('_scenario_hint', '')

            scenario_constraints = ""
            if scenario_hint:
                # ENHANCED: Put constraints at ABSOLUTE TOP with stronger language
                scenario_constraints = f"""
═══════════════════════════════════════════════════════════════
🛑 BINDING SCENARIO CONSTRAINTS - VALIDATION ENFORCED 🛑
═══════════════════════════════════════════════════════════════

{scenario_hint}

CRITICAL REQUIREMENTS:
- Your generated scenario will be VALIDATED against these constraints
- If validation fails, generation will RETRY (up to 3 attempts)
- Pay special attention to:
  * void_level (must match exactly if specified)
  * Prohibited elements (NO SPAWN_ENEMY means ZERO enemies)
  * Required locations (use exact names/keywords from constraints)
  * Required NPCs (include all mentioned NPCs)

These constraints OVERRIDE ALL other instructions below. Violation = regeneration.

═══════════════════════════════════════════════════════════════

"""

            # Add narrative style guidance if specified
            dm_config = self.session_config.get('agents', {}).get('dm', {})
            narrative_style = dm_config.get('narrative_style', '')
            tone_guidance = dm_config.get('tone_guidance', '')

            if narrative_style or tone_guidance:
                style_header = f"\n📖 NARRATIVE STYLE: {narrative_style}\n" if narrative_style else "\n📖 NARRATIVE GUIDANCE:\n"
                scenario_constraints += f"""
{style_header}
{tone_guidance if tone_guidance else ''}

Apply this narrative style to:
- Scene descriptions and environmental details
- NPC dialogue and characterization
- Action resolution narration (success/failure framing)
- Round synthesis and storytelling beats

"""

            # Use LLM to generate dynamic scenario
            try:
                scenario_prompt = f"""Generate a unique Aeonisk YAGS scenario for a tabletop RPG session.

{scenario_constraints}
{party_context}
{lore_context}
{variety_context}

**Scenario Requirements:**

1. **Theme** (2-3 words): The type of situation (combat, investigation, social, crisis, etc.)

2. **Location**: A specific place from Aeonisk canonical lore. Use locations from the lore context above.

3. **Situation** (3-6 sentences): Vivid, atmospheric opening narration that drops players directly into action.
   - Use sensory details and show immediate tension
   - Include NPCs present and what's at stake
   - Make it cinematic and engaging
   - Example: "The Resonance Spire's transmission array crackles with stolen signals..."

4. **Void Level** (0-10): Environmental void corruption intensity
   - 0-2: Safe, minimal corruption
   - 3-5: Moderate void presence
   - 6-8: Dangerous corruption (consider Eye of Breach if Tempest involved)
   - 9-10: Critical void breach imminent

5. **Starting Clocks** (1-4 clocks): Progress timers with clear semantics
   - Include at least one **threat clock** (danger escalating) and one **objective clock** (player goal)
   - Optional: complication or secondary concern

   **For each clock, specify:**
   - **Name**: Clear, descriptive (e.g., "Security Alert", "Evidence Collection")
   - **Max ticks** (4-8 recommended): How many advances until filled
   - **Description**: What this clock tracks
   - **Advance meaning**: What it means when clock advances (be specific!)
   - **Regress meaning**: What it means when clock regresses
   - **Filled consequence**: What happens when filled (narrative description)

   **Clock Types:**
   - **Threat clocks**: Advancing = worse for players (Security Alert, Structural Collapse, Hunter Pursuit)
   - **Progress clocks**: Advancing = goal progress (Evidence Collection, Defenses Established, Evacuation Progress)

6. **Success Conditions**: What constitutes victory for the players?

7. **Failure Consequences**: What happens if they fail?

8. **Initial Enemies** (optional, 0-6 enemies): Spawn enemies present at scenario start
   - Use when scenario requires immediate combat threats
   - Examples: ambushes, patrols, guards, creatures, hostiles
   - Leave empty ([]) for investigation/social scenarios where threats emerge later

   **When to spawn initial enemies:**
   - ✅ Hostile locations (corporate facilities, gang territory, void breaches)
   - ✅ Combat-focused themes (raid, escape, defense, assault)
   - ✅ Players infiltrating/trespassing (guards, patrols)
   - ✅ Story starts mid-action (chase, ambush, firefight)
   - ❌ Social/investigation scenarios (spawn later via story progression)
   - ❌ Safe/neutral territory (spawn when story demands it)

   **For each enemy spawn:**
   - **template**: Enemy type from YAGS system (grunt, enforcer, specialist, etc.)
   - **faction**: Which faction they belong to (ACG Security, Void Cultists, etc.)
   - **count**: How many of this type (1-4 per spawn)
   - **disposition**: combat_stance (always use this for immediate threats)
   - **description**: Brief visual description

9. **Initial NPCs** (optional, 0-4 NPCs): Spawn NPCs present at scenario start
   - Use when scenario requires non-combatant characters for roleplay
   - Examples: quest-givers, witnesses, prisoners, allies, civilians
   - Leave empty ([]) if no immediate NPCs needed

   **When to spawn initial NPCs:**
   - ✅ Social/investigation scenarios (witnesses, contacts, informants)
   - ✅ Prisoners/hostages in combat zones (rescue targets)
   - ✅ Quest-givers or guides (fixer, navigator, broker)
   - ✅ Neutral characters in hostile zones (civilians, refugees)
   - ❌ Pure combat scenarios (unless hostages/prisoners)
   - ❌ Wilderness/isolated locations (unless story requires)

   **For each NPC spawn:**
   - **name**: Character name (can be role-based like "Wounded Freeborn Scout")
   - **faction**: Which faction (can be "None" for neutrals)
   - **entity_type**: neutral, ally, or prisoner
   - **threat_level**: non_combatant (for NPCs)
   - **disposition**: friendly, neutral, hostile, prisoner
   - **description**: Brief visual description
   - **health** (10-30): Current health
   - **soak** (0-3): Damage resistance
   - **details**: Background, motivations, or relevant info

**Scenario Variety Guidelines:**
- Mix combat (50%), social, intrigue, and crisis scenarios
- Pick DIFFERENT location from recently used ones (if listed above)
- Scenario types:
  * COMBAT: ambush, firefight, siege, assault, defense, void creature attack, gang warfare
  * SOCIAL: tribunal, bond dispute, debt settlement, trade negotiation, vendor conflict
  * INTRIGUE: heist, investigation, ritual gone wrong, faction conflict, political intrigue
  * CRISIS: void outbreak, station breach, emergency evacuation, containment failure

**Critical Constraints:**
- Base on canonical lore above (three planets: Aeonisk Prime, Nimbus, Arcadia)
- Humans only, NO aliens
- Respect party composition - NO faction betrayal scenarios
- Align with character goals OR create cross-faction cooperation
- Good: ACG hires party to recover debt contracts, Pantheon investigates void corruption
- Bad: ACG hires Sovereign Nexus to steal from their own faction"""

                # Try structured output first (pass scenario_hint for validation)
                scenario_setup = await self._generate_scenario_structured(
                    scenario_prompt,
                    scenario_hint=scenario_hint
                )

                if scenario_setup:
                    # Successfully generated structured output
                    logger.info(f"✓ Using structured output for scenario generation")
                    scenario_data = {
                        'theme': scenario_setup.theme,
                        'location': scenario_setup.location,
                        'situation': scenario_setup.situation,
                        'void_level': scenario_setup.void_level,
                        'clocks': []
                    }

                    # Convert NewClock objects to tuple format for compatibility
                    for clock in scenario_setup.starting_clocks:
                        scenario_data['clocks'].append((
                            clock.name,
                            clock.max_ticks,
                            clock.description,
                            clock.advance_meaning,
                            clock.regress_meaning,
                            clock.filled_consequence,
                            getattr(clock, 'is_terminal_clock', False),
                            getattr(clock, 'terminal_outcome', 'victory')
                        ))

                else:
                    # Fall back to legacy text generation + parsing
                    logger.info("⚠️ Falling back to legacy text-based scenario generation")

                    provider = self.llm_config.get('provider', 'anthropic')
                    model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

                    # Use rate-limited wrapper to prevent API overload
                    from .llm_provider import call_anthropic_with_retry

                    response = await call_anthropic_with_retry(
                        client=self.llm_client,
                        model=model,
                        messages=[{"role": "user", "content": scenario_prompt}],
                        max_tokens=1000,
                        temperature=self.llm_config.get('temperature', 1.0),
                        max_retries=3,
                        base_delay=2.0,
                        max_delay=120.0,
                        use_rate_limiter=True
                    )
                    llm_text = response.content[0].text.strip()

                    # Log LLM call for replay
                    if self.llm_logger:
                        self.llm_logger._log_llm_call(
                            messages=[{"role": "user", "content": scenario_prompt}],
                            response=llm_text,
                            model=model,
                            temperature=self.llm_config.get('temperature', 1.0),
                            tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                            current_round=None,  # Scenario generation happens before round 1
                            call_sequence=self.llm_logger.call_count
                        )

                    # Also log to human-readable agent prompt log if enabled
                    if self.agent_prompt_logger:
                        try:
                            self.agent_prompt_logger.log_llm_call(
                                agent_id=self.agent_id,
                                round_num=None,
                                call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                                prompt=scenario_prompt,
                                response=llm_text,
                                model=model,
                                temperature=self.llm_config.get('temperature', 1.0),
                                tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                                metadata={'purpose': 'scenario_generation'}
                            )
                        except Exception as e:
                            logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                    # Parse LLM response
                    scenario_data = self._parse_scenario_from_llm(llm_text)

                # Enforce variety - reject if location matches recent scenarios
                if self.shared_state:
                    recent_scenarios = self.shared_state.recent_scenarios
                    location_lower = scenario_data['location'].lower()

                    # Check if this location was recently used
                    for recent in recent_scenarios:
                        if recent['location'].lower() in location_lower or location_lower in recent['location'].lower():
                            print(f"[DM {self.agent_id}] Location '{scenario_data['location']}' was recently used - regenerating...")

                            # Try ONE more time with stronger emphasis
                            retry_prompt = scenario_prompt.replace(
                                "Pick a DIFFERENT theme and location",
                                "❗ CRITICAL: You MUST pick a completely different location. DO NOT use any of the locations listed above"
                            )

                            # Use rate-limited wrapper (import may be branch-scoped above)
                            from .llm_provider import call_anthropic_with_retry
                            response = await call_anthropic_with_retry(
                                client=self.llm_client,
                                model=model,
                                messages=[{"role": "user", "content": retry_prompt}],
                                max_tokens=1000,
                                temperature=1.0,  # Higher temperature for more creativity
                                max_retries=3,
                                base_delay=2.0,
                                max_delay=120.0,
                                use_rate_limiter=True
                            )
                            llm_text = response.content[0].text.strip()

                            # Log LLM call for replay
                            if self.llm_logger:
                                self.llm_logger._log_llm_call(
                                    messages=[{"role": "user", "content": retry_prompt}],
                                    response=llm_text,
                                    model=model,
                                    temperature=1.0,
                                    tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                                    current_round=None,
                                    call_sequence=self.llm_logger.call_count
                                )

                            # Also log to human-readable agent prompt log if enabled
                            if self.agent_prompt_logger:
                                try:
                                    self.agent_prompt_logger.log_llm_call(
                                        agent_id=self.agent_id,
                                        round_num=None,
                                        call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                                        prompt=retry_prompt,
                                        response=llm_text,
                                        model=model,
                                        temperature=1.0,
                                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                                        metadata={'purpose': 'scenario_generation_retry'}
                                    )
                                except Exception as e:
                                    logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                            scenario_data = self._parse_scenario_from_llm(llm_text)
                            break  # Only check first match and retry once

            except Exception as e:
                logger.error(f"Failed to generate AI scenario: {e}")
                # Re-raise exception - fail fast instead of producing broken fallback
                raise

        # Scenario-aware vendor encounter
        # Only spawn random vendors if vendor_spawn_frequency is enabled (>= 0)
        vendor_spawn_freq = self.session_config.get('vendor_spawn_frequency', -1)
        if vendor_spawn_freq >= 0:
            # If vendor-gated scenario, force specific vendor type
            if scenario_data.get('required_vendor_type'):
                required_type = scenario_data['required_vendor_type']
                eligible_vendors = [v for v in self.vendor_pool if v.vendor_type == required_type]
                if eligible_vendors:
                    active_vendor = random.choice(eligible_vendors)
                    logger.debug(f"Vendor-gated scenario: forcing {active_vendor.name} ({active_vendor.vendor_type.value})")
                    print(f"[DM {self.agent_id}] 🔒 VENDOR REQUIRED: {active_vendor.name}")
                else:
                    logger.error(f"No vendor of type {required_type} available!")
                    active_vendor = None
            else:
                active_vendor = self._select_contextual_vendor(scenario_data['theme'])
            # Wrap single vendor in list for backwards compatibility
            active_vendors = [active_vendor] if active_vendor else []
        else:
            # vendor_spawn_frequency: -1 means only use persistent vendors from config
            active_vendors = []
            logger.debug("Random vendor spawning disabled (vendor_spawn_frequency: -1), using only persistent vendors")

        # Add newly spawned vendors to SharedState for persistence
        if active_vendors and self.shared_state:
            for vendor in active_vendors:
                # Only add if not already present
                if not self.shared_state.get_vendor(vendor.name):
                    self.shared_state.add_vendor(vendor)
                    logger.info(f"Vendor added to SharedState: {vendor.name} ({vendor.vendor_type.value})")
                    print(f"[DM {self.agent_id}] 💰 {vendor.name} present")
        elif active_vendors:
            # Fallback logging if SharedState not available
            for vendor in active_vendors:
                logger.info(f"Vendor encounter: {vendor.name} ({vendor.vendor_type.value})")
                print(f"[DM {self.agent_id}] 💰 {vendor.name} present")

        # Get all current vendors from SharedState (includes newly spawned + persisting vendors)
        if self.shared_state:
            all_vendors = self.shared_state.get_all_vendors()
            logger.debug(f"Retrieved {len(all_vendors)} vendors from SharedState: {[v.name for v in all_vendors]}")
        else:
            all_vendors = active_vendors
            logger.warning("No SharedState available - using active_vendors directly")

        logger.debug(f"Creating scenario with {len(all_vendors)} vendors")

        scenario = Scenario(
            theme=scenario_data['theme'],
            location=scenario_data['location'],
            situation=scenario_data['situation'],
            active_npcs=[],
            environmental_factors=[],
            void_level=scenario_data['void_level'],
            active_vendors=all_vendors,  # Use all vendors (new + persisting)
            required_purchase=scenario_data.get('required_purchase'),
            vendor_gate_description=scenario_data.get('vendor_gate_description')
        )

        self.current_scenario = scenario

        # Vendors are already synced via add_vendor() calls above (lines 528-534)
        # and get_all_vendors() returns current_vendors list (line 543).
        # No additional sync needed here - SharedState.current_vendors is authoritative.

        # Initialize mechanics and create scenario-specific clocks
        if self.shared_state:
            self.shared_state.initialize_mechanics()
            mechanics = self.shared_state.get_mechanics_engine()

            # If the session config supplies a TERMINAL starting clock, that clock is
            # how the scene is meant to end -- it is authoritative. Suppress the DM's
            # own scenario-generated clocks so they don't crowd out / orphan it (a live
            # run showed the DM inventing differently-named clocks and never advancing
            # the config's terminal clock, so the session ran to the round cap).
            # Scoped to terminal configs only, so existing/golden sessions that use
            # plain starting_clocks keep their current DM-adds-clocks behavior.
            session_config = getattr(self.shared_state, 'session_config', None) or {}
            config_clocks = session_config.get('starting_clocks', []) or []
            config_has_terminal = any(c.get('is_terminal_clock') for c in config_clocks)
            if config_has_terminal and scenario_data.get('clocks'):
                print(
                    f"[DM {self.agent_id}] Config provides a terminal starting clock; "
                    f"using config clocks as authoritative and skipping "
                    f"{len(scenario_data.get('clocks', []))} DM scenario clock(s)."
                )
                logger.info(
                    "Terminal starting clock present in config -- suppressing DM "
                    "scenario-generated clocks to keep the terminal clock authoritative."
                )
                scenario_data['clocks'] = []

            for clock_data in scenario_data.get('clocks', []):
                clock_name = clock_data[0]
                max_value = clock_data[1]
                description = clock_data[2] if len(clock_data) > 2 else ""
                advance_meaning = clock_data[3] if len(clock_data) > 3 else ""
                regress_meaning = clock_data[4] if len(clock_data) > 4 else ""
                filled_consequence = clock_data[5] if len(clock_data) > 5 else ""
                is_terminal = clock_data[6] if len(clock_data) > 6 else False
                terminal_outcome = clock_data[7] if len(clock_data) > 7 else "victory"

                mechanics.create_scene_clock(
                    clock_name, max_value, description,
                    advance_meaning, regress_meaning, filled_consequence,
                    is_terminal=is_terminal, terminal_outcome=terminal_outcome
                )
                print(f"[DM {self.agent_id}] Created clock: {clock_name} (0/{max_value})")

        # Validate scenario against party composition
        faction_conflicts = self._detect_faction_conflicts(scenario, players_config)

        # Apply soulcredit penalties for high-severity conflicts
        if faction_conflicts and self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                for conflict in faction_conflicts:
                    if conflict['severity'] == 'high' and conflict['type'] == 'faction_betrayal':
                        # Find the affected player's agent_id
                        character_name = conflict['character']
                        # Apply -2 soulcredit penalty for faction betrayal
                        # Note: We'd need to map character name to agent_id here
                        # For now, log the warning
                        logger.warning(f"⚠️ FACTION BETRAYAL DETECTED: {conflict['conflict']}")
                        print(f"\n⚠️  WARNING: {conflict['conflict']}")
                        print(f"   This may result in soulcredit loss if pursued.")

        # Log scenario to JSONL
        logger.debug(f"Serializing scenario with {len(scenario.active_vendors) if scenario.active_vendors else 0} vendors")

        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'active_vendors': [
                {
                    'vendor_id': vendor.vendor_id,  # NEW: ID for mechanical purchase
                    'name': vendor.name,
                    'type': vendor.vendor_type.value,
                    'faction': vendor.faction,
                    'greeting': vendor.greeting,
                    'inventory_preview': [item.name for item in vendor.inventory[:3]],  # For JSONL logging
                    'inventory': [  # Full inventory for player prompts
                        {
                            'item_id': item.item_id,  # NEW: ID for mechanical purchase
                            'name': item.name,
                            'description': item.description,
                            'price_spark': item.price_spark,
                            'price_drip': item.price_drip,
                            'price_breath': item.price_breath,
                            'seed_barter': item.seed_barter,
                            'item_type': item.item_type
                        } for item in vendor.inventory
                    ]
                } for vendor in scenario.active_vendors
            ] if scenario.active_vendors else []
        }

        logger.debug(f"Scenario data active_vendors field: {scenario_data.get('active_vendors', 'MISSING')}")
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_scenario(scenario_data)

        # Process initial_enemies from config (if specified)
        initial_enemies_config = config.get('initial_enemies', [])
        initial_npcs_config = config.get('initial_npcs', [])

        scenario_setup_dict = None
        if initial_enemies_config or initial_npcs_config:
            from .initial_spawns import build_initial_spawns

            # Honors disposition: a prisoner/friendly/neutral "enemy" routes to the
            # disarmed NPC path instead of spawning as an armed combatant.
            enemy_spawns, npc_spawns = build_initial_spawns(
                initial_enemies_config, initial_npcs_config)

            # Serialize to dicts for JSON
            scenario_setup_dict = {
                'initial_enemies': [spawn.model_dump() for spawn in enemy_spawns],
                'npc_spawns': [spawn.model_dump() for spawn in npc_spawns]
            }

            if enemy_spawns:
                logger.info(f"Config specifies {len(enemy_spawns)} initial enemy spawn(s)")
            if npc_spawns:
                logger.info(f"Config specifies {len(npc_spawns)} initial NPC spawn(s)")

        # Build payload
        payload = {
            'scenario': scenario_data,
            'opening_narration': self._generate_opening_narration(scenario, faction_conflicts),
            'faction_conflicts': faction_conflicts  # Warn players of potential issues
        }
        if scenario_setup_dict:
            payload['scenario_setup'] = scenario_setup_dict

        # Broadcast scenario setup
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,  # broadcast
            payload
        )

        print(f"\n[DM {self.agent_id}] Generated scenario: {scenario.theme}")
        print(f"Location: {scenario.location}")
        print(f"Situation: {scenario.situation}")
        if initial_enemies_config:
            total_enemies = sum(e.get('count', 1) for e in initial_enemies_config)
            print(f"Will spawn {total_enemies} initial enemies from config")
        if initial_npcs_config:
            print(f"Will spawn {len(initial_npcs_config)} initial NPCs from config")

        # Track scenario for variety in future sessions
        if self.shared_state:
            self.shared_state.add_scenario(scenario.theme, scenario.location)
            # Save to persistent dm_notes.json
            from pathlib import Path
            dm_notes_path = Path('./multiagent_output') / 'dm_notes.json'
            self.shared_state.save_dm_notes(str(dm_notes_path))

    async def _use_forced_scenario(self, spawn_marker, config: Dict[str, Any]):
        """Use a forced scenario, bypassing AI generation.

        Accepts either the legacy string spawn-marker (automated tests) or a
        dict with theme/location/situation/void_level (resume-from-divergence:
        the reconstructor forces the recorded scenario + a story-so-far digest
        so the resumed DM has continuity instead of inventing a fresh scene).
        """
        fields = _forced_scenario_fields(spawn_marker)
        scenario = Scenario(
            theme=fields["theme"],
            location=fields["location"],
            situation=fields["situation"],
            active_npcs=[],
            environmental_factors=[],
            void_level=fields["void_level"],
            active_vendors=[]
        )
        self.current_scenario = scenario

        # Prepare scenario data
        scenario_data = {
            'theme': scenario.theme,
            'location': scenario.location,
            'situation': scenario.situation,
            'void_level': scenario.void_level,
            'vendor': None
        }

        # Log scenario
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_scenario(scenario_data)

        # Process initial_enemies/initial_npcs from config — same surface the
        # AI-scenario paths honor. Forced scenarios previously skipped it, so a
        # resume config's per-survivor roster never spawned (0/N matched).
        scenario_setup_dict = None
        initial_enemies_config = config.get('initial_enemies', [])
        initial_npcs_config = config.get('initial_npcs', [])
        if initial_enemies_config or initial_npcs_config:
            from .initial_spawns import build_initial_spawns
            enemy_spawns, npc_spawns = build_initial_spawns(
                initial_enemies_config, initial_npcs_config)
            scenario_setup_dict = {
                'initial_enemies': [s.model_dump() for s in enemy_spawns],
                'npc_spawns': [s.model_dump() for s in npc_spawns]
            }
            logger.info(f"Forced scenario: {len(enemy_spawns)} initial enemy spawn(s), "
                        f"{len(npc_spawns)} NPC spawn(s) from config")

        payload = {
            'scenario': scenario_data,
            'opening_narration': f"{fields['theme']} — {fields['location']}. {fields['situation']}"
                                 if isinstance(spawn_marker, dict)
                                 else f"Test scenario initialized. {spawn_marker}",
            'faction_conflicts': []
        }
        if scenario_setup_dict:
            payload['scenario_setup'] = scenario_setup_dict

        # Broadcast scenario setup
        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,  # broadcast
            payload
        )

        print(f"\n[DM {self.agent_id}] Using forced test scenario")
        print(f"Spawn marker: {str(spawn_marker)[:200]}")

    async def _use_config_scenario(self, scenario_config: Dict[str, Any], config: Dict[str, Any]):
        """Use scenario from config file instead of generating one."""
        # Extract scenario data from config
        theme = scenario_config.get('theme', 'Unknown')
        location = scenario_config.get('location', 'Unknown Location')
        situation = scenario_config.get('situation', 'Something mysterious is happening')
        void_level = scenario_config.get('void_level', 0)
        initial_clocks = scenario_config.get('initial_clocks', [])

        # Extract initial_enemies from top-level config (not scenario dict)
        initial_enemies_config = config.get('initial_enemies', [])

        # Get all current vendors from SharedState (includes persistent vendors)
        if self.shared_state:
            all_vendors = self.shared_state.get_all_vendors()
            logger.debug(f"Retrieved {len(all_vendors)} vendors from SharedState for config scenario: {[v.name for v in all_vendors]}")
        else:
            all_vendors = []
            logger.warning("No SharedState available - config scenario will have no vendors")

        # Create scenario object WITH persistent vendors from SharedState
        scenario = Scenario(
            theme=theme,
            location=location,
            situation=situation,
            active_npcs=[],
            environmental_factors=[],
            void_level=void_level,
            active_vendors=all_vendors  # FIX: Use SharedState vendors, not empty list!
        )
        self.current_scenario = scenario

        # Prepare scenario data WITH vendor inventory for player prompts
        scenario_data = {
            'theme': theme,
            'location': location,
            'situation': situation,
            'void_level': void_level,
            'active_vendors': [  # FIX: Include vendor data for players!
                {
                    'vendor_id': vendor.vendor_id,
                    'name': vendor.name,
                    'type': vendor.vendor_type.value,
                    'faction': vendor.faction,
                    'greeting': vendor.greeting,
                    'inventory_preview': [item.name for item in vendor.inventory[:3]],
                    'inventory': [
                        {
                            'item_id': item.item_id,
                            'name': item.name,
                            'description': item.description,
                            'price_spark': item.price_spark,
                            'price_drip': item.price_drip,
                            'price_breath': item.price_breath,
                            'seed_barter': item.seed_barter,
                            'item_type': item.item_type
                        } for item in vendor.inventory
                    ]
                } for vendor in all_vendors
            ] if all_vendors else []
        }

        # Log scenario
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_scenario(scenario_data)

            # Initialize clocks from config
            if initial_clocks and mechanics:
                for clock_config in initial_clocks:
                    clock_name = clock_config.get('name', 'Unknown')
                    clock_max = clock_config.get('max', 6)
                    clock_current = clock_config.get('current', 0)
                    clock_desc = clock_config.get('description', '')

                    mechanics.create_scene_clock(clock_name, clock_max, clock_desc)
                    if clock_current > 0:
                        mechanics.scene_clocks[clock_name].current = clock_current

                    logger.info(f"Initialized clock from config: {clock_name} ({clock_current}/{clock_max})")

        # Generate opening narration based on situation
        opening_narration = f"{situation}"

        # Extract initial_npcs from top-level config
        initial_npcs_config = config.get('initial_npcs', [])

        # Create scenario_setup object with initial_enemies and/or initial_npcs if specified
        scenario_setup_obj = None
        if initial_enemies_config or initial_npcs_config:
            from .initial_spawns import build_initial_spawns

            # Honors disposition: a prisoner/friendly/neutral "enemy" routes to the
            # disarmed NPC path instead of spawning as an armed combatant.
            enemy_spawns, npc_spawns = build_initial_spawns(
                initial_enemies_config, initial_npcs_config)

            # Serialize Pydantic models to dicts for JSON serialization
            # (Message.to_json() uses json.dumps with default=str, which breaks objects)
            enemy_spawn_dicts = [spawn.model_dump() for spawn in enemy_spawns]
            npc_spawn_dicts = [spawn.model_dump() for spawn in npc_spawns]

            # Create dict (not SimpleNamespace) for JSON serialization
            scenario_setup_dict = {
                'initial_enemies': enemy_spawn_dicts,
                'npc_spawns': npc_spawn_dicts
            }
            if enemy_spawns:
                logger.info(f"Config specifies {len(enemy_spawns)} initial enemy spawn(s)")
            if npc_spawns:
                logger.info(f"Config specifies {len(npc_spawns)} initial NPC spawn(s)")

        # Broadcast scenario setup
        payload = {
            'scenario': scenario_data,
            'opening_narration': opening_narration,
            'faction_conflicts': []
        }
        if initial_enemies_config or initial_npcs_config:
            payload['scenario_setup'] = scenario_setup_dict

        self.send_message_sync(
            MessageType.SCENARIO_SETUP,
            None,  # broadcast
            payload
        )

        print(f"\n[DM {self.agent_id}] Using scenario from config file")
        print(f"Theme: {theme}")
        print(f"Location: {location}")
        if initial_clocks:
            print(f"Initialized {len(initial_clocks)} clocks from config")
        if initial_enemies_config:
            total_enemies = sum(e.get('count', 1) for e in initial_enemies_config)
            print(f"Will spawn {total_enemies} initial enemies from config")
        if initial_npcs_config:
            print(f"Will spawn {len(initial_npcs_config)} initial NPCs from config")

    def _validate_scenario_against_hint(self, scenario: 'ScenarioSetup', hint: str) -> tuple[bool, list[str]]:
        """
        Validate generated scenario against scenario_hint constraints.

        Returns:
            (is_valid, violations) where violations is list of error messages
        """
        import re

        violations = []
        hint_lower = hint.lower()

        # Extract and validate void_level requirement
        if 'void_level' in hint_lower or 'void level' in hint_lower:
            match = re.search(r'void[_ ]level\s*(\d+)', hint_lower)
            if match:
                required_void_level = int(match.group(1))
                if scenario.void_level != required_void_level:
                    violations.append(
                        f"void_level mismatch: hint requires {required_void_level}, "
                        f"got {scenario.void_level}"
                    )

        # Validate prohibited elements - NO enemies
        if 'no spawn_enemy' in hint_lower or 'no enemies' in hint_lower:
            if scenario.initial_enemies:
                violations.append(
                    f"Prohibited element 'enemies': scenario has {len(scenario.initial_enemies)} enemies "
                    f"but hint says NO enemies"
                )

        # Validate location keywords
        location_lower = scenario.location.lower()

        # Check for specific location requirements. Each entry is a tuple of
        # acceptable alternatives — named entities must match in any of
        # their forms (abbreviated or spelled out), since the LLM freely
        # switches between them.
        location_requirements = []
        if 'mining station' in hint_lower:
            location_requirements.append(('mining',))
        if 'terminus outpost' in hint_lower:
            location_requirements.extend([('terminus',), ('outpost',)])
        if 'resonance spire' in hint_lower:
            location_requirements.extend([('resonance',), ('spire',)])
        if 'tempest' in hint_lower and 'facility' in hint_lower:
            location_requirements.append(('tempest',))
        if 'arcane genetics' in hint_lower or 'arcgen' in hint_lower:
            location_requirements.append(('arcgen', 'arcane genetics'))

        for alternatives in location_requirements:
            if not any(alt in location_lower for alt in alternatives):
                wanted = " or ".join(f"'{alt}'" for alt in alternatives)
                violations.append(
                    f"Required location keyword {wanted} not found in location: {scenario.location}"
                )

        return (len(violations) == 0, violations)

    async def _generate_scenario_structured(
        self,
        scenario_prompt: str,
        system_prompt: str = "You are the DM for Aeonisk YAGS, creating an engaging scenario.",
        scenario_hint: str = ""
    ) -> Optional['ScenarioSetup']:
        """
        Generate scenario using Pydantic AI structured output (ScenarioSetup schema).
        Returns ScenarioSetup if successful, or None to fall back to legacy text parsing.

        If scenario_hint is provided, validates generated scenario and retries up to 3 times on violation.

        Automatically retries Pydantic validation errors with exponential backoff (up to 3 attempts).
        """
        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug("DM: No llm_provider available for scenario generation, will use legacy method")
            return None

        from pydantic import ValidationError
        import json
        import time

        # Outer retry loop for Pydantic validation errors
        max_pydantic_retries = 3
        base_delay = 1.0  # seconds

        for pydantic_attempt in range(max_pydantic_retries):
            try:
                from .schemas.story_events import ScenarioSetup

                if pydantic_attempt > 0:
                    # Exponential backoff delay
                    delay = base_delay * (2 ** (pydantic_attempt - 1))
                    logger.info(f"DM: Retrying scenario generation (attempt {pydantic_attempt + 1}/{max_pydantic_retries}, waiting {delay}s)")
                    await asyncio.sleep(delay)
                else:
                    logger.debug("DM: Attempting structured output for scenario generation")

                model = self.llm_config.get('model', 'claude-sonnet-4-5')
                max_tokens = 5000  # Large buffer for complex scenarios with multiple clocks
                temperature = 1.0  # OpenAI structured output requires 1.0, Claude allows other values

                # Enhance system prompt if scenario_hint provided
                if scenario_hint:
                    system_prompt += (
                        " Your scenario MUST match the BINDING SCENARIO CONSTRAINTS in the prompt. "
                        "Violations will cause regeneration. Pay special attention to void_level (must match exactly), "
                        "prohibited elements (NO SPAWN_ENEMY means zero enemies), and required locations/NPCs."
                    )

                # Inner retry loop for semantic validation
                max_hint_attempts = 3
                for hint_attempt in range(max_hint_attempts):
                    # Generate structured scenario using Pydantic AI
                    # Token tracking now handled internally
                    scenario: ScenarioSetup = await self.llm_provider.generate_structured(
                        prompt=scenario_prompt,
                        result_type=ScenarioSetup,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        llm_logger=self.llm_logger,  # Enable automatic token tracking
                        current_round=None  # Scenario generation happens before round 1
                    )

                    # Validate scenario against hint if provided
                    if scenario_hint:
                        is_valid, violations = self._validate_scenario_against_hint(scenario, scenario_hint)
                        if not is_valid:
                            logger.warning(
                                f"DM: Scenario validation failed (attempt {hint_attempt + 1}/{max_hint_attempts}): "
                                f"{', '.join(violations)}"
                            )
                            if hint_attempt < max_hint_attempts - 1:
                                logger.info("DM: Retrying scenario generation...")
                                continue
                            else:
                                raise RuntimeError(
                                    f"Scenario generation failed validation after {max_hint_attempts} attempts. "
                                    f"Violations: {', '.join(violations)}"
                                )
                        else:
                            logger.info("DM: Scenario passed validation checks")

                    # Scenario is valid - break inner loop
                    break

                # Success! Log and return
                logger.debug(f"✓ DM structured scenario: {scenario.theme} @ {scenario.location}, {len(scenario.starting_clocks)} clocks, void={scenario.void_level}")

                # Also log to agent prompt logger if enabled
                if self.agent_prompt_logger:
                    try:
                        # Estimate token counts (1 token ~= 4 chars)
                        estimated_input_tokens = len(scenario_prompt) // 4
                        estimated_output_tokens = len(scenario.situation) // 4

                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=None,
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=scenario_prompt,
                            response=scenario.situation,
                            model=model,
                            temperature=temperature,
                            tokens={'input': estimated_input_tokens, 'output': estimated_output_tokens},
                            metadata={'purpose': 'scenario_generation_structured', 'note': 'Pydantic AI structured output (ScenarioSetup schema)'}
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                return scenario

            except (ValidationError, json.JSONDecodeError) as e:
                # Retryable error (Pydantic validation or JSON parsing) - retry with backoff
                logger.warning(f"DM: Retryable error (attempt {pydantic_attempt + 1}/{max_pydantic_retries}): {type(e).__name__}: {e}")

                if pydantic_attempt >= max_pydantic_retries - 1:
                    # Final attempt failed - raise as RuntimeError
                    logger.error(f"DM: Structured scenario generation failed after {max_pydantic_retries} retry attempts")
                    raise RuntimeError(f"Scenario generation failed after {max_pydantic_retries} attempts: {e}") from e
                # Otherwise continue outer loop for retry

            except Exception as e:
                # Other errors - fail immediately
                logger.error(f"DM: Structured scenario generation failed: {e}")
                raise RuntimeError(f"Scenario generation failed: {e}") from e

        # Should not reach here, but for safety
        raise RuntimeError("Scenario generation exhausted all retry attempts")

    def _parse_scenario_from_llm(self, llm_text: str) -> Dict[str, Any]:
        """Parse scenario from LLM-generated text."""
        lines = llm_text.strip().split('\n')
        scenario_data = {
            'theme': 'Unknown',
            'location': 'Unknown Location',
            'situation': 'Something mysterious is happening',
            'void_level': 3,
            'clocks': []
        }

        logger.debug(f"Parsing scenario from LLM output ({len(llm_text)} chars, {len(lines)} lines)")

        for line in lines:
            line = line.strip()
            # Remove markdown formatting (**, *, etc) for parsing
            clean_line = line.lstrip('*').strip()

            if ':' in clean_line or '|' in clean_line:
                if clean_line.startswith('THEME:'):
                    scenario_data['theme'] = clean_line.split(':', 1)[1].strip().strip('*').strip()
                    logger.debug(f"  Parsed THEME: {scenario_data['theme']}")
                elif clean_line.startswith('LOCATION:'):
                    scenario_data['location'] = clean_line.split(':', 1)[1].strip().strip('*').strip()
                    logger.debug(f"  Parsed LOCATION: {scenario_data['location']}")
                elif clean_line.startswith('SITUATION:'):
                    scenario_data['situation'] = clean_line.split(':', 1)[1].strip().strip('*').strip()
                    logger.debug(f"  Parsed SITUATION: {scenario_data['situation']}")
                elif clean_line.startswith('VOID_LEVEL:'):
                    try:
                        scenario_data['void_level'] = int(clean_line.split(':', 1)[1].strip())
                    except (ValueError, IndexError) as e:
                        # The author stated a void level and it did not parse.
                        # Dropping it silently leaves the scene at 0, which is a
                        # plausible route to the scene_void_level: 0 seen in #86.
                        logger.warning(
                            f"Could not parse VOID_LEVEL from {clean_line!r}: {e}")
                elif clean_line.startswith('CLOCK'):
                    # Format: CLOCK1: Name | 6 | Description | ADVANCE=... | REGRESS=... | FILLED=...
                    parts = clean_line.split(':', 1)[1].split('|')
                    if len(parts) >= 3:
                        name = parts[0].strip().strip('*').strip()
                        try:
                            max_ticks = int(parts[1].strip())
                        except (ValueError, IndexError):
                            max_ticks = 6
                        description = parts[2].strip()

                        # Extract semantic guidance
                        advance_meaning = ""
                        regress_meaning = ""
                        filled_consequence = ""

                        for part in parts[3:]:
                            part = part.strip()
                            if part.startswith('ADVANCE='):
                                advance_meaning = part.replace('ADVANCE=', '').strip()
                            elif part.startswith('REGRESS='):
                                regress_meaning = part.replace('REGRESS=', '').strip()
                            elif part.startswith('FILLED='):
                                filled_consequence = part.replace('FILLED=', '').strip()

                        scenario_data['clocks'].append((
                            name, max_ticks, description,
                            advance_meaning, regress_meaning, filled_consequence
                        ))

        # Ensure we have at least 2 clocks
        if len(scenario_data['clocks']) < 2:
            scenario_data['clocks'].append(('Danger Escalation', 6, 'The situation worsens', '', '', ''))
            scenario_data['clocks'].append(('Player Progress', 6, 'Investigating the mystery', '', '', ''))

        logger.debug(f"Parsed scenario: theme='{scenario_data['theme']}', location='{scenario_data['location']}', situation='{scenario_data['situation']}' ({len(scenario_data['situation'])} chars), clocks={len(scenario_data['clocks'])}")

        return scenario_data

    def _create_vendor_gated_scenario(self) -> Dict[str, Any]:
        """
        Create a scenario where purchasing a specific item is REQUIRED to proceed.

        Returns scenario_data dict with vendor requirements baked in.
        """
        templates = [
            {
                'theme': 'Locked Tech Gate',
                'location': 'Sealed Research Facility (Arcadia)',
                'situation': 'The facility requires a Scrambled ID Chip to bypass security. The entrance scanner rejects all standard credentials.',
                'void_level': 3,
                'required_purchase': 'Scrambled ID Chip',
                'vendor_gate': 'Without a Scrambled ID Chip, the security system cannot be bypassed.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # "Cipher" has this
                'clocks': [
                    ('Security Lockdown', 6, 'Facility going into full lockdown'),
                    ('Data Extraction', 6, 'Retrieving critical intel before wipe'),
                    ('Rival Team', 5, 'Competing group closing in')
                ]
            },
            {
                'theme': 'Ritual Emergency',
                'location': 'Unstable Ley Node (Nimbus)',
                'situation': 'Raw Seeds in the area are degrading rapidly into Hollow Seeds. You need an Echo-Calibrator to stabilize them before they corrupt the node.',
                'void_level': 5,
                'required_purchase': 'Echo-Calibrator',
                'vendor_gate': 'Without an Echo-Calibrator, the Seeds cannot be stabilized and will become Hollow.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # Scribe Orven Tylesh or vending
                'clocks': [
                    ('Seed Corruption', 6, 'Raw Seeds degrading into Hollow'),
                    ('Node Destabilization', 8, 'Ley node collapsing'),
                    ('Void Bleed', 5, 'Environmental corruption spreading')
                ]
            },
            {
                'theme': 'Debt Settlement',
                'location': 'ACG Collections Office (Aeonisk Prime)',
                'situation': 'A contact owes you critical information, but ACG has seized their assets. They demand payment: either 8 Spark or a Bond Insurance Policy to release them from debt.',
                'void_level': 2,
                'required_purchase': 'Bond Insurance Policy',  # or pay 8 Spark
                'vendor_gate': 'The contact cannot be freed without either 8 Spark payment or a Bond Insurance Policy.',
                'required_vendor_type': VendorType.HUMAN_TRADER,  # Contract Specialist Rhen
                'clocks': [
                    ('Asset Liquidation', 6, 'Contact losing everything'),
                    ('Information Window', 5, 'Intel becoming outdated'),
                    ('ACG Pressure', 6, 'Collections becoming aggressive')
                ]
            },
            {
                'theme': 'Informant Bribe',
                'location': 'Underground Market (Floating Exchange)',
                'situation': 'A black market informant has intel on a void cult, but refuses to talk. They demand Sparksticks (addictive buzz twigs) as payment.',
                'void_level': 4,
                'required_purchase': 'Sparksticks',
                'vendor_gate': 'The informant will not provide intel without Sparksticks.',
                'required_vendor_type': VendorType.VENDING_MACHINE,  # SnackHub has this
                'clocks': [
                    ('Cult Ritual', 6, 'Void cult completing dangerous ritual'),
                    ('Informant Patience', 4, 'Informant leaving if not paid'),
                    ('Market Surveillance', 5, 'Pantheon Security closing in')
                ]
            },
            {
                'theme': 'Medical Crisis',
                'location': 'Abandoned Transit Station (Nimbus)',
                'situation': 'A party member has been exposed to void toxin. You need a Med Kit (Tactical) from the Pantheon supply drone to treat them before corruption spreads.',
                'void_level': 6,
                'required_purchase': 'Med Kit (Tactical)',
                'vendor_gate': 'Without medical treatment, the exposed character will gain +3 void corruption.',
                'required_vendor_type': VendorType.SUPPLY_DRONE,  # Pantheon Field Supply
                'clocks': [
                    ('Toxin Spread', 5, 'Corruption spreading to others'),
                    ('Medical Window', 4, 'Treatment window closing'),
                    ('Station Collapse', 6, 'Structure failing')
                ]
            },
            {
                'theme': 'Trade Negotiation',
                'location': 'House of Vox Broadcast Hub',
                'situation': 'You need access to restricted archives, but the archivist demands a Data Slate (Encrypted) as payment for black market access codes.',
                'void_level': 2,
                'required_purchase': 'Data Slate (Encrypted)',
                'vendor_gate': 'Archive access requires the Data Slate as barter.',
                'required_vendor_type': VendorType.SUPPLY_DRONE,  # House of Vox Courier
                'clocks': [
                    ('Archive Purge', 6, 'Data being deleted'),
                    ('Archivist Trust', 5, 'Window of cooperation'),
                    ('Media Sweep', 6, 'Vox censoring information')
                ]
            }
        ]

        # Select random template
        template = random.choice(templates)

        return {
            'theme': template['theme'],
            'location': template['location'],
            'situation': template['situation'],
            'void_level': template['void_level'],
            'clocks': template['clocks'],
            'required_purchase': template['required_purchase'],
            'vendor_gate_description': template['vendor_gate'],
            'required_vendor_type': template['required_vendor_type']
        }

    def _create_combat_scenario(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a combat-focused scenario (ambush, firefight, battle, etc.).

        Args:
            config: Optional session config (can specify combat_scenario_index to force specific template)

        Returns scenario_data dict for immediate combat situations.
        """
        config = config or {}
        templates = [
            {
                'theme': 'Overwhelming Ambush',
                'location': 'Kill Zone - Abandoned Transit Hub (Arcadia)',
                'situation': 'You\'ve been lured into a trap. A hostile assault team rushes you from close range while covering fire comes from above. You need to break through or take them down fast. [SPAWN_ENEMY: Assault Team | grunt | Near-Enemy | aggressive_melee]',
                'void_level': 4,
                'clocks': [
                    ('Tactical Withdrawal', 6, 'Finding a way to escape the kill zone', 'ADVANCE=Spotting escape routes', 'REGRESS=Enemies cutting off exits', 'FILLED=You find an escape route!'),
                    ('Enemy Reinforcements', 10, 'Backup being called in', 'ADVANCE=Enemies calling for backup', 'REGRESS=Delaying reinforcements', 'FILLED=Second wave arrives! [SPAWN_ENEMY: Reserve Forces | grunt | Far-Enemy | tactical_ranged]'),
                    ('Critical Wounds', 4, 'Party members taking severe injuries')
                ]
            },
            {
                'theme': 'Gang Ambush',
                'location': 'Undercity Maintenance Tunnels (Arcadia)',
                'situation': 'A Freeborn gang has set up an ambush - they think you\'re rival dealers. Muzzle flashes illuminate the darkness as they open fire from concealed positions. [SPAWN_ENEMY: Gang Ambushers | grunt | Near-Enemy | aggressive_melee]',
                'void_level': 3,
                'clocks': [
                    ('Reinforcements Arriving', 10, 'More gang members responding to gunfire', 'ADVANCE=More gang members hear the firefight', 'REGRESS=Silencing the gang', 'FILLED=Gang backup arrives! [SPAWN_ENEMY: Gang Reinforcements | grunt | Far-Enemy | defensive_ranged]'),
                    ('Escape Route', 4, 'Tunnel collapse blocking exit'),
                    ('Civilian Panic', 4, 'Nearby residents calling Pantheon Security')
                ]
            },
            {
                'theme': 'Hostile Extraction',
                'location': 'Pantheon Detention Facility (Aeonisk Prime)',
                'situation': 'Security forces have been alerted to your presence. Riot carapace troops are advancing down the corridor, shock batons crackling. You need to fight your way out. [SPAWN_ENEMY: Riot Troops | grunt | Near-Enemy | defensive_ranged]',
                'void_level': 2,
                'clocks': [
                    ('Lockdown Protocol', 4, 'Facility sealing all exits'),
                    ('Security Reinforcements', 10, 'Tactical teams deploying', 'ADVANCE=More security responding', 'REGRESS=Evading security', 'FILLED=Tactical team arrives! [SPAWN_ENEMY: Security Tacticals | grunt | Far-Enemy | tactical_ranged]'),
                    ('Asset Extraction', 4, 'Getting your contact out before they\'re moved')
                ]
            },
            {
                'theme': 'Void Creature Attack',
                'location': 'Collapsed Ley Nexus (Nimbus)',
                'situation': 'Void-touched creatures emerge from a breach in reality - warped humanoid forms with too many limbs, their bodies flickering between states. They\'re hostile and closing fast. [SPAWN_ENEMY: Void Spawn | grunt | Near-Enemy | aggressive_melee]',
                'void_level': 7,
                'clocks': [
                    ('Breach Expansion', 4, 'Reality tear growing larger'),
                    ('Creature Swarm', 5, 'More entities emerging from void', 'ADVANCE=Breach widening, more creatures', 'REGRESS=Sealing the breach', 'FILLED=Void swarm pours through! [SPAWN_ENEMY: Void Horrors | grunt | Engaged | aggressive_melee]'),
                    ('Void Exposure', 4, 'Environmental corruption affecting party')
                ]
            },
            {
                'theme': 'Faction Firefight',
                'location': 'Contested Transit Hub (Floating Exchange)',
                'situation': 'Freeborn pirates are raiding an ACG debt collection convoy. You\'re caught in the crossfire - the pirates open fire thinking you\'re ACG backup. [SPAWN_ENEMY: Freeborn Pirates | grunt | Near-Enemy | tactical_ranged]',
                'void_level': 3,
                'clocks': [
                    ('Freeborn Escape', 4, 'Pirates fighting their way to ships', 'ADVANCE=Pirates advancing toward escape route', 'REGRESS=Blocking pirate escape', 'FILLED=Pirates successfully disengage and escape! [DESPAWN_ENEMY: Freeborn Pirates | escaped]'),
                    ('ACG Asset Seizure', 4, 'ACG trying to secure cargo'),
                    ('Pantheon Response', 5, 'Security arriving', 'ADVANCE=Pantheon forces mobilizing', 'REGRESS=Delaying security', 'FILLED=Pantheon tactical team arrives! [SPAWN_ENEMY: Pantheon Squad | grunt | Extreme-Enemy | tactical_ranged]')
                ]
            },
            {
                'theme': 'Defense Stand',
                'location': 'Resonance Commune Sanctuary (Nimbus)',
                'situation': 'The sanctuary is under assault by void-corrupted raiders. You must hold the perimeter while civilians evacuate through the back routes. They\'re breaking through the outer walls. [SPAWN_ENEMY: Initial Raiders | grunt | Near-Enemy | aggressive_melee]',
                'void_level': 5,
                'clocks': [
                    ('Raider Reinforcements', 10, 'Second wave incoming', 'ADVANCE=More raiders arriving', 'REGRESS=Slowing reinforcements', 'FILLED=Second wave breaches! [SPAWN_ENEMY: Void Raiders | grunt | Near-Enemy | aggressive_melee]'),
                    ('Civilian Evacuation', 5, 'Getting non-combatants to safety'),
                    ('Void Corruption', 4, 'Raiders spreading corruption')
                ]
            },
            {
                'theme': 'Assassination Attempt',
                'location': 'ACG Executive Tower (Aeonisk Prime)',
                'situation': 'Hostile operatives have breached the building - they\'re here to kill someone you\'re protecting. Professional killers with military-grade weapons, moving through the floors toward your position. [SPAWN_ENEMY: Advance Scouts | grunt | Far-Enemy | tactical_ranged]',
                'void_level': 2,
                'clocks': [
                    ('Assassin Reinforcements', 10, 'More killers deploying', 'ADVANCE=Backup team getting closer', 'REGRESS=Delaying reinforcements', 'FILLED=Elite hit team arrives! [SPAWN_ENEMY: Professional Hit Team | elite | Far-Enemy | tactical_ranged]'),
                    ('Building Lockdown', 4, 'Security systems being hacked'),
                    ('Extraction Window', 4, 'Opportunity to escape closing')
                ]
            },
            {
                'theme': 'Siege Breakout',
                'location': 'Surrounded Safe House (Arcadia)',
                'situation': 'You\'re pinned down in a safe house. Pantheon Security has the building surrounded with riot teams, drones, and heavy weapons. They\'re demanding surrender, but you know too much to be taken alive. [SPAWN_ENEMY: Siege Perimeter | grunt | Far-Enemy | defensive_ranged]',
                'void_level': 3,
                'clocks': [
                    ('Breach Attempt', 3, 'Security forces preparing assault', 'ADVANCE=Preparing to storm the building', 'REGRESS=Fortifying defenses', 'FILLED=Breach team storms in! [SPAWN_ENEMY: Breach Squad | elite | Near-Enemy | aggressive_melee]'),
                    ('Supply Depletion', 4, 'Running out of ammo and medical supplies'),
                    ('Negotiation Window', 4, 'Opportunity for peaceful resolution fading')
                ]
            },
            {
                'theme': 'Combat Rescue',
                'location': 'Crashed Transport Ship (Nimbus Wastes)',
                'situation': 'A transport went down in hostile territory. Survivors are pinned in the wreckage by scavenger gangs and void-touched wildlife. You need to extract them under fire. [SPAWN_ENEMY: Scavenger Scouts | grunt | Far-Enemy | defensive_ranged]',
                'void_level': 6,
                'clocks': [
                    ('Scavenger Reinforcements', 10, 'Main gang arriving', 'ADVANCE=More scavengers coming', 'REGRESS=Driving scavengers away', 'FILLED=Full gang attacks! [SPAWN_ENEMY: Scavenger Gang | grunt | Near-Enemy | aggressive_melee]'),
                    ('Void Creatures', 4, 'Corrupted wildlife drawn to the crash'),
                    ('Survivor Casualties', 5, 'Wounded dying without immediate help')
                ]
            },
            {
                'theme': 'Turf War',
                'location': 'Black Market District (Floating Exchange)',
                'situation': 'Two rival gangs are going to war over Hollow Seed territory, and you\'re in the kill zone. Automatic weapons fire tears through the market stalls as both sides fight for control. [SPAWN_ENEMY: Red Coil Gang | grunt | Near-Enemy | aggressive_melee] [SPAWN_ENEMY: Void Saints | grunt | Far-Enemy | tactical_ranged]',
                'void_level': 4,
                'clocks': [
                    ('Gang Escalation', 10, 'Both sides calling reinforcements', 'ADVANCE=More gang members arriving', 'REGRESS=Dispersing the gangs', 'FILLED=Full gang war erupts! [SPAWN_ENEMY: Gang Reinforcements | grunt | Engaged | aggressive_melee]'),
                    ('Civilian Casualties', 4, 'Bystanders caught in crossfire'),
                    ('Pantheon Response', 4, 'Security forces mobilizing')
                ]
            },
            {
                'theme': 'Facility Assault',
                'location': 'Tempest Research Station (Orbital)',
                'situation': 'You\'re leading an assault on a Tempest black site. Automated defenses are active - combat drones, turrets, and security systems. Eye of Breach may be controlling the facility. [SPAWN_ENEMY: Security Drones | grunt | Far-Enemy | extreme_range]',
                'void_level': 8,
                'clocks': [
                    ('Defense Systems', 4, 'Automated weapons engaging'),
                    ('Eye of Breach Activation', 3, 'Rogue AI taking direct control', 'ADVANCE=AI systems coming online', 'REGRESS=Disrupting AI control', 'FILLED=Eye of Breach fully awakens! [SPAWN_ENEMY: AI Combat Units | elite | Extreme-Enemy | tactical_ranged]'),
                    ('Mission Objective', 5, 'Reaching critical data before destruction')
                ]
            },
            {
                'theme': 'Ideological Battle',
                'location': 'Ley Node Nexus (Aeonisk Prime)',
                'situation': 'Tempest Industries forces are attempting to install unauthorized void-tech at a Sovereign Nexus ley node. Nexus enforcers and Pantheon Security have engaged them in a firefight. Both sides believe their cause justifies violence - void freedom vs spiritual order. [SPAWN_ENEMY: Tempest Operatives | grunt | Far-Enemy | tactical_ranged] [SPAWN_ENEMY: Nexus Enforcers | grunt | Near-Enemy | defensive_ranged]',
                'void_level': 5,
                'clocks': [
                    ('Tempest Installation', 4, 'Void-tech being deployed', 'ADVANCE=Void-tech systems activating', 'REGRESS=Disrupting installation', 'FILLED=Void-tech goes live! [SPAWN_ENEMY: Void-Enhanced Troops | elite | Near-Enemy | adaptive]'),
                    ('Nexus Purge', 4, 'Cleansing the site by force'),
                    ('Civilian Casualties', 4, 'Bystanders caught in ideological war')
                ]
            }
        ]

        # Select combat template (use specified index if provided, otherwise random)
        scenario_index = config.get('combat_scenario_index')
        if scenario_index is not None and 0 <= scenario_index < len(templates):
            template = templates[scenario_index]
            logger.debug(f"Using specified combat scenario index {scenario_index}: {template['theme']}")
        else:
            template = random.choice(templates)
            logger.debug(f"Using random combat scenario: {template['theme']}")

        return {
            'theme': template['theme'],
            'location': template['location'],
            'situation': template['situation'],
            'void_level': template['void_level'],
            'clocks': template['clocks']
        }

    def _detect_faction_conflicts(self, scenario: Scenario, players_config: List[Dict]) -> List[Dict[str, str]]:
        """
        Detect if the scenario conflicts with any player's faction or goals.

        Returns list of conflicts: [{'character': name, 'conflict': description, 'severity': low/medium/high}]
        """
        conflicts = []

        if not players_config:
            return conflicts

        situation_lower = scenario.situation.lower()
        location_lower = scenario.location.lower()

        # Faction ownership mappings
        faction_assets = {
            'sovereign nexus': ['codex cathedral', 'sanctified', 'ley network', 'gestation chamber', 'archive'],
            'pantheon': ['pantheon', 'security', 'law enforcement', 'civic', 'patrol'],
            'acg': ['astral commerce', 'debt', 'contract', 'commerce hub'],
            'arcgen': ['arcane genetics', 'biocreche', 'genetic', 'pod gestation'],
            'tempest': ['tempest industries', 'void energy', 'industrial', 'autonomous'],
        }

        # Check each player for conflicts
        for player in players_config:
            name = player.get('name', 'Unknown')
            faction = player.get('faction', '').lower()
            goals = [g.lower() for g in player.get('goals', [])]

            # Check if scenario involves stealing from/sabotaging own faction
            if faction in faction_assets:
                for asset in faction_assets[faction]:
                    # Check if targeting their faction's assets
                    if asset in location_lower or asset in situation_lower:
                        # Check if action is hostile (steal, infiltrate, sabotage)
                        hostile_keywords = ['steal', 'infiltrate', 'sabotage', 'extract', 'hack', 'break into', 'unauthorized']
                        if any(keyword in situation_lower for keyword in hostile_keywords):
                            conflicts.append({
                                'character': name,
                                'conflict': f"{name} ({faction}) is being asked to act against {faction} assets",
                                'severity': 'high',
                                'type': 'faction_betrayal'
                            })

            # Check if goals are contradicted
            goal_conflicts = []
            for goal in goals:
                # Example: goal is "prevent unauthorized void exposure" but scenario is "use void energy"
                if 'prevent' in goal and any(keyword in situation_lower for keyword in goal.split() if len(keyword) > 4):
                    goal_conflicts.append(goal)

            if goal_conflicts:
                conflicts.append({
                    'character': name,
                    'conflict': f"{name}'s goals ({', '.join(goal_conflicts)}) may conflict with this mission",
                    'severity': 'medium',
                    'type': 'goal_conflict'
                })

        return conflicts

    def _load_persistent_vendors(self, config: Dict[str, Any]) -> List[Vendor]:
        """
        Load persistent vendors from session config.

        Config format:
        ```json
        {
          "persistent_vendors": [
            {
              "name": "Black Market Dealer \"Vex\"",
              "type": "human_trader",
              "faction": "Freeborn",
              "greeting": "Need offerings? ...",
              "inventory": [
                {"name": "Blood Offering", "description": "...", "price": {"drip": 8}},
                {"name": "Incense", "description": "...", "price": {"spark": 1, "drip": 2}}
              ],
              "buys_from_players": true,
              "buy_prices": {
                "blood_offering": {"drip": 5},
                "crystals": {"drip": 7}
              }
            }
          ]
        }
        ```
        """
        from .energy_economy import VendorItem, VendorType

        persistent_vendor_configs = config.get('persistent_vendors', [])
        vendors = []

        for vendor_config in persistent_vendor_configs:
            try:
                # Parse vendor type
                vendor_type_str = vendor_config.get('type', 'human_trader')
                vendor_type = VendorType(vendor_type_str)

                # Parse inventory items
                inventory = []
                for item_config in vendor_config.get('inventory', []):
                    # Support both flat format (price_drip: 5) and nested format (price: {drip: 5})
                    price_dict = item_config.get('price', {})
                    item = VendorItem(
                        name=item_config['name'],
                        description=item_config.get('description', ''),
                        item_id=item_config.get('item_id'),  # FIX: Pass item_id from config
                        price_spark=item_config.get('price_spark', price_dict.get('spark', 0)),
                        price_drip=item_config.get('price_drip', price_dict.get('drip', 0)),
                        price_breath=item_config.get('price_breath', price_dict.get('breath', 0)),
                        seed_barter=item_config.get('seed_barter', False),
                        item_type=item_config.get('item_type', 'consumable')
                    )
                    inventory.append(item)

                # Create vendor
                vendor = Vendor(
                    name=vendor_config['name'],
                    faction=vendor_config.get('faction', 'Neutral'),
                    inventory=inventory,
                    greeting=vendor_config.get('greeting', 'Looking to trade?'),
                    vendor_type=vendor_type,
                    vendor_id=vendor_config.get('vendor_id')  # FIX: Pass vendor_id from config
                )

                # Store buy prices for future feature (vendor buy-back system)
                vendor.buys_from_players = vendor_config.get('buys_from_players', False)
                vendor.buy_prices = vendor_config.get('buy_prices', {})

                vendors.append(vendor)
                logger.info(f"Loaded persistent vendor: {vendor.name} ({len(inventory)} items)")

            except Exception as e:
                logger.error(f"Failed to load persistent vendor '{vendor_config.get('name', 'unknown')}': {e}")
                continue

        return vendors

    def _select_contextual_vendor(self, scenario_theme: str) -> Optional[Vendor]:
        """
        Select vendor based on scenario context.

        Safe zones (social, market, downtime) → Human traders (70% chance)
        Neutral zones (investigation, heist, exploration) → Vending machines/drones (60% chance)
        Hot zones (combat, crisis, void outbreak) → Emergency caches only (20% chance) or None
        """
        theme_lower = scenario_theme.lower()

        # Classify scenario zone
        safe_keywords = ['market', 'social', 'gathering', 'festival', 'ceremony', 'negotiation', 'diplomatic', 'downtime']
        neutral_keywords = ['investigation', 'heist', 'exploration', 'mystery', 'infiltration', 'search', 'transit', 'travel']
        hot_keywords = ['combat', 'battle', 'firefight', 'ambush', 'assault', 'crisis', 'outbreak', 'emergency', 'escape', 'chase']

        zone = 'neutral'  # Default
        if any(keyword in theme_lower for keyword in safe_keywords):
            zone = 'safe'
        elif any(keyword in theme_lower for keyword in hot_keywords):
            zone = 'hot'
        elif any(keyword in theme_lower for keyword in neutral_keywords):
            zone = 'neutral'

        # Filter vendors by appropriate type
        eligible_vendors = []

        if zone == 'safe':
            # Human traders + vending machines
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type in [VendorType.HUMAN_TRADER, VendorType.VENDING_MACHINE]]
            spawn_chance = 0.7  # 70% chance (increased for more economic gameplay)
        elif zone == 'neutral':
            # Vending machines + supply drones (no human traders in active zones)
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type in [VendorType.VENDING_MACHINE, VendorType.SUPPLY_DRONE]]
            spawn_chance = 0.6  # 60% chance (increased for more economic gameplay)
        elif zone == 'hot':
            # Emergency caches only (rare)
            eligible_vendors = [v for v in self.vendor_pool if v.vendor_type == VendorType.EMERGENCY_CACHE]
            spawn_chance = 0.2  # 20% chance (increased for more economic gameplay)

        # Roll for vendor appearance
        if eligible_vendors and random.random() < spawn_chance:
            return random.choice(eligible_vendors)

        return None

    def _generate_opening_narration(self, scenario: Scenario, faction_conflicts: List[Dict] = None) -> str:
        """Generate opening narration for scenario."""
        # Just use the situation directly - it should be self-contained
        if scenario.situation:
            narration = scenario.situation
        else:
            narration = f"The party finds themselves at {scenario.location}."

        # Add faction conflict warnings
        if faction_conflicts:
            high_conflicts = [c for c in faction_conflicts if c['severity'] == 'high']
            if high_conflicts:
                narration += "\n\n⚠️  ETHICAL CONCERN:"
                for conflict in high_conflicts:
                    narration += f"\n   {conflict['conflict']}"
                narration += "\n   Proceeding may damage your spiritual standing."

        # Add vendor-gate requirement if present
        if scenario.required_purchase and scenario.vendor_gate_description:
            narration += f"\n\n🔒 CRITICAL REQUIREMENT:"
            narration += f"\n   {scenario.vendor_gate_description}"
            narration += f"\n   Required item: **{scenario.required_purchase}**"

        # Add vendor description if present
        if scenario.active_vendors:
            if len(scenario.active_vendors) == 1:
                vendor = scenario.active_vendors[0]
                if scenario.required_purchase:
                    narration += f"\n\nFortunately, {vendor.name} is nearby - a {vendor.faction} {vendor.vendor_type.value}. They may have what you need."
                else:
                    narration += f"\n\nNearby, you notice {vendor.name}, a {vendor.faction} trader. They seem to have goods for sale or barter."
            else:
                narration += f"\n\nSeveral vendors are present:"
                for vendor in scenario.active_vendors:
                    narration += f"\n- {vendor.name} ({vendor.faction} {vendor.vendor_type.value})"

        narration += "\n\nWhat do you do?"
        return narration.strip()
        
    async def _handle_action_declared(self, message: Message):
        """Handle player action declarations - respond as DM."""
        payload = message.payload
        player_id = message.sender

        # Check what phase we're in
        phase = payload.get('phase')

        if phase == 'adjudication':
            # Adjudication phase - DM processes all actions together
            await self._handle_adjudication(payload)
            return

        elif phase == 'resolution_only':
            # Resolve mechanically but don't synthesize (synthesis comes later)
            await self._handle_resolution_only(payload)
            return

        elif phase == 'synthesis':
            # Generate synthesis from all collected resolutions
            await self._handle_synthesis(payload)
            return

        elif phase == 'resolution':
            # Old resolution phase (kept for compatibility)
            action = payload.get('action', payload)
            await self._handle_ai_dm_response(player_id, action)
            return

        else:
            # Declaration phase - acknowledge but don't resolve (logged in debug only)
            logger.debug(f"[DM {self.agent_id}] Noted: {player_id} declared action")
            return
            
    async def _handle_resolution_only(self, payload: Dict[str, Any]):
        """Resolve action mechanically without synthesis."""
        # Use adjudication but skip synthesis
        payload['skip_synthesis'] = True
        await self._handle_adjudication(payload)

    async def _handle_synthesis(self, payload: Dict[str, Any]):
        """Generate synthesis from all collected resolutions."""
        resolutions = payload.get('resolutions', [])
        round_num = payload.get('round', 0)
        resolution_state = payload.get('resolution_state')  # Extract resolution state for fled NPCs tracking
        expired_clocks = payload.get('expired_clocks', [])  # Extract expired clocks from clock update phase
        entity_lifecycle_result = payload.get('entity_lifecycle_result')  # Extract entity lifecycle (morale, spawns, conversions)

        if not resolutions:
            return

        # Generate synthesis (can be RoundSynthesis object or str)
        from .outcome_pipeline import RoundSynthesisFailClosed
        try:
            synthesis = await self._synthesize_round_outcome(
                resolutions,
                round_num,
                resolution_state=resolution_state,
                expired_clocks=expired_clocks,
                entity_lifecycle_result=entity_lifecycle_result
            )
        except RoundSynthesisFailClosed as exc:
            # The message bus swallows handler exceptions, so an unhandled
            # raise here strands the session on _synthesis_complete forever.
            # Broadcast the failure so the session can end itself cleanly;
            # the round_synthesis_failed checkpoint has already been logged.
            logger.error(f"[DM {self.agent_id}] Round synthesis failed closed: {exc}")
            print(f"\n[DM {self.agent_id}] ===== Round Synthesis FAILED (fail-closed) =====")
            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,  # Broadcast
                {
                    'narration': f"Round synthesis failed validation after bounded retries: {exc}",
                    'is_round_synthesis': True,
                    'synthesis_failed': True,
                    'round': round_num,
                }
            )
            return

        # Import RoundSynthesis for type checking
        from .schemas.story_events import RoundSynthesis

        # Prepare narration text for display and payload
        if isinstance(synthesis, RoundSynthesis):
            narration_text = synthesis.narration
            is_structured = True
        else:
            narration_text = synthesis
            is_structured = False

        print(f"\n[DM {self.agent_id}] ===== Round Synthesis =====")
        print(narration_text)
        print("=" * 40)

        # Store synthesis for narrative digest (adjudication context in future rounds)
        if narration_text and round_num is not None:
            self._round_synthesis_history.append((round_num, narration_text))

        # Broadcast the round synthesis to all players
        # If structured, include the full object; otherwise just text
        payload_data = {
            'narration': narration_text,
            'is_round_synthesis': True,
            'round': round_num
        }

        if is_structured:
            # Serialize Pydantic model to dict for JSON transmission
            payload_data['structured_synthesis'] = synthesis.model_dump()

        self.send_message_sync(
            MessageType.DM_NARRATION,
            None,  # Broadcast
            payload_data
        )

    # REMOVED: _extract_character_data() - no longer used
    # Character data now reconstructed from character_state events in ML pipeline
    # Saves ~7,200 tokens/session by avoiding duplication in action_resolution events
    #
    # def _extract_character_data(self, player_id: str) -> Optional[Dict[str, Any]]:
    #     """
    #     Extract complete character sheet data for ML training logging.
    #     ...
    #     """
    #     pass

    def _generate_environment_description(self, player_id: str) -> str:
        """
        Generate environment description for ML training.

        Format: "Location, tactical positions, environmental conditions"
        Example: "Corporate facility, PCs at Near range with cover, 2 enemies at Far-Enemy"
        """
        parts = []

        # Add scenario location
        if self.current_scenario:
            parts.append(self.current_scenario.location)

        # Add tactical positions if available
        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
            # Count PC positions
            pc_positions = {}
            for agent in self.shared_state.player_agents:
                if hasattr(agent, 'position'):
                    pos_str = str(agent.position)
                    pc_positions[pos_str] = pc_positions.get(pos_str, 0) + 1

            if pc_positions:
                pos_desc = ", ".join([f"{count} PC{'s' if count > 1 else ''} at {pos}" for pos, count in pc_positions.items()])
                parts.append(pos_desc)

        # Add enemy count if available
        enemy_count = active_enemy_count(self.shared_state)
        if enemy_count > 0:
            parts.append(f"{enemy_count} enem{'ies' if enemy_count != 1 else 'y'}")

        # Add void level if high
        if self.current_scenario and self.current_scenario.void_level >= 5:
            parts.append(f"void level {self.current_scenario.void_level}/10")

        return ", ".join(parts) if parts else "Unknown environment"

    def _generate_stakes_description(self, player_id: str) -> str:
        """
        Generate stakes description for ML training.

        Format: "What's at risk - consequences of success/failure"
        Example: "PC at 8/20 HP risking death, 2 clocks near completion, high void corruption (7/10)"
        """
        stakes = []

        # Check character health/void
        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
            for agent in self.shared_state.player_agents:
                if hasattr(agent, 'agent_id') and agent.agent_id == player_id:
                    char = agent.character_state if hasattr(agent, 'character_state') else None
                    if char:
                        # High void risk
                        if hasattr(char, 'void') and char.void >= 7:
                            stakes.append(f"High void corruption ({char.void}/10, near possession)")

                        # Low HP risk
                        if hasattr(char, 'health') and hasattr(char, 'max_health'):
                            if char.health <= char.max_health * 0.3:
                                stakes.append(f"Low HP ({char.health}/{char.max_health}, risking incapacitation)")
                    break

        # Check clock states
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            near_complete_clocks = []
            near_failure_clocks = []

            for clock_name, clock in mechanics.scene_clocks.items():
                progress = clock.current / clock.maximum if clock.maximum > 0 else 0

                if progress >= 0.75:  # 75%+ filled
                    near_complete_clocks.append(f"{clock_name} ({clock.current}/{clock.maximum})")
                elif progress <= 0.25 and clock.current == 0:  # Empty and neglected
                    near_failure_clocks.append(clock_name)

            if near_complete_clocks:
                stakes.append(f"Clocks near completion: {', '.join(near_complete_clocks)}")
            if near_failure_clocks:
                stakes.append(f"Neglected objectives: {', '.join(near_failure_clocks)}")

        # Combat pressure
        enemy_count = active_enemy_count(self.shared_state)
        if enemy_count >= 3:
            stakes.append(f"Outnumbered ({enemy_count} enemies)")

        return "; ".join(stakes) if stakes else "Standard risk scenario"

    def _generate_roll_formula(self, resolution: 'ActionResolution') -> str:
        """
        Generate human-readable roll formula for ML training.

        Format: "Attribute X × Skill Y = Z; Z + d20(N) = Total vs DC"
        Example: "Perception 4 × Guns 5 = 20; 20 + d20(15) = 35 vs DC 20"
        """
        # Use cached formula if available (single source of truth from resolve_action)
        cached_formula = getattr(resolution, 'roll_formula', None)
        if cached_formula:
            return cached_formula

        # Fallback for backward compatibility with old ActionResolution objects
        attr_name = resolution.attribute.title() if (hasattr(resolution, 'attribute') and resolution.attribute) else 'Unknown'
        attr_val = resolution.attribute_value if hasattr(resolution, 'attribute_value') else 0
        skill_name = resolution.skill.title() if (hasattr(resolution, 'skill') and resolution.skill) else 'None'
        skill_val = resolution.skill_value if hasattr(resolution, 'skill_value') else 0
        d20_roll = resolution.roll if hasattr(resolution, 'roll') else 0
        total = resolution.total if hasattr(resolution, 'total') else 0
        dc = resolution.difficulty if hasattr(resolution, 'difficulty') else 0

        if skill_val > 0:
            ability = attr_val * skill_val
            formula = f"{attr_name} {attr_val} × {skill_name} {skill_val} = {ability}; {ability} + d20({d20_roll}) = {total} vs DC {dc}"
        else:
            # Unskilled: d20 ÷ 2 only (YAGS v1.2.3)
            halved_roll = d20_roll // 2
            formula = f"d20({d20_roll}) ÷ 2 = {halved_roll} (unskilled) vs DC {dc}"

        return formula

    def _generate_rationale(self, resolution: 'ActionResolution', action: Dict[str, Any]) -> str:
        """
        Generate DM rationale for ML training.

        Format: Brief explanation of DC choice and difficulty factors
        Example: "DC 20 (Moderate) for ranged combat; target at Far range but PC has good positioning"
        """
        dc = resolution.difficulty if hasattr(resolution, 'difficulty') else 20
        action_type = action.get('action_type', 'unknown')

        # Determine DC tier
        if dc <= 15:
            dc_tier = "Easy"
        elif dc <= 20:
            dc_tier = "Moderate"
        elif dc <= 25:
            dc_tier = "Challenging"
        elif dc <= 30:
            dc_tier = "Difficult"
        else:
            dc_tier = "Very Difficult"

        # Base rationale
        rationale = f"DC {dc} ({dc_tier}) for {action_type} action"

        # Add contextual factors
        factors = []

        # Check for ritual action
        if action.get('is_ritual', False):
            if not action.get('has_offering', False):
                factors.append("no offering (+void risk)")
            if action.get('has_altar', False):
                factors.append("sanctified altar (+3 bonus)")

        # Check for combat modifiers
        if action_type in ['attack', 'shoot', 'fire']:
            if 'range' in action.get('description', '').lower():
                factors.append("range considerations")

        # Check void level
        if self.current_scenario and self.current_scenario.void_level >= 5:
            factors.append(f"high void environment ({self.current_scenario.void_level}/10)")

        if factors:
            rationale += "; " + ", ".join(factors)

        return rationale

    async def _handle_adjudication(self, payload: Dict[str, Any]):
        """
        Adjudicate all declared actions together.
        This is where the DM sees all intentions and decides what actually happens.
        """
        actions = payload.get('actions', [])
        round_num = payload.get('round', 0)
        action_index = payload.get('action_index', 0)  # Track which action this is for multi-action turns
        skip_synthesis = payload.get('skip_synthesis', False)  # Skip synthesis if set
        previous_resolutions = payload.get('previous_resolutions', [])  # Earlier actions this round for narrative consistency

        if not actions:
            # No actions to adjudicate - signal completion
            self.send_message_sync(
                MessageType.ACTION_RESOLVED,
                None,
                {'agent_id': 'adjudication'}
            )
            return

        try:
            await self._handle_adjudication_inner(
                actions, round_num, action_index, skip_synthesis, previous_resolutions
            )
        except Exception as e:
            # Fatal error during adjudication - log and signal error
            import traceback
            tb = traceback.format_exc()
            error_msg = f"Fatal adjudication error: {type(e).__name__}: {e}"
            logger.error(f"❌ DM {self.agent_id}: {error_msg}\n{tb}")

            # Log to JSONL if possible
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_session_error(
                        error_type="adjudication_failure",
                        error_message=str(e),
                        exception_type=type(e).__name__,
                        context={
                            'round': round_num,
                            'action_index': action_index,
                            'action_count': len(actions),
                            'agent_id': self.agent_id
                        }
                    )

            # Send error message so session can terminate gracefully
            self.send_message_sync(
                MessageType.AGENT_ERROR,
                None,  # Broadcast
                {
                    'agent_id': self.agent_id,
                    'error_type': 'adjudication_failure',
                    'error_message': error_msg,
                    'round': round_num,
                    'recoverable': False
                }
            )

            # Also send ACTION_RESOLVED to unblock session wait
            # This prevents the session from hanging forever
            self.send_message_sync(
                MessageType.ACTION_RESOLVED,
                None,
                {
                    'agent_id': 'adjudication',
                    'error': True,
                    'error_message': error_msg
                }
            )

    async def _handle_adjudication_inner(
        self, actions, round_num, action_index, skip_synthesis, previous_resolutions
    ):
        """Inner adjudication logic, separated for error handling."""
        print(f"\n[DM {self.agent_id}] ===== Adjudicating {len(actions)} actions =====")

        # Increment clock ages at start of each round
        if self.shared_state and action_index == 0:  # Only on first action of the round
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics:
                mechanics.increment_all_clock_rounds()

        # Log adjudication start
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
            if mechanics.jsonl_logger:
                mechanics.jsonl_logger.log_adjudication_start(round_num, len(actions))

        # Process each action mechanically (fastest → slowest, same as actions list)
        resolutions = []
        mechanics = self.shared_state.mechanics_engine if self.shared_state else None

        for action_entry in actions:
            player_id = action_entry['player_id']
            character_name = action_entry['character_name']
            initiative = action_entry['initiative']
            action = action_entry['action']

            print(f"\n[{character_name}] (initiative {initiative})")

            # Resolve action mechanically (with context from previous resolutions this round)
            resolution = await self._resolve_action_mechanically(player_id, action, previous_resolutions=previous_resolutions)

            # Print the resolution
            print(f"\n{resolution['narration']}")
            print("=" * 40)

            # Log the resolution
            if mechanics and mechanics.jsonl_logger:
                # Extract resolution data for logging
                action_resolution = resolution.get('resolution')
                state_changes = resolution.get('state_changes', {})
                clock_deltas = resolution.get('clock_deltas', [])
                combat_data = resolution.get('combat_data', {})
                inventory_changes = resolution.get('inventory_changes', [])

                # Skip logging for NPC actions — already logged in
                # _resolve_action_mechanically with phase="adjudicate_npc".
                # Logging again here would double-count NPC actions and
                # inherit stale outcome_tiers from the previous PC action.
                is_npc_action = action.get('is_npc', False)

                if action_resolution and not is_npc_action and not self._outcome_first_enabled():
                    # Build economy changes dict with void and soulcredit deltas
                    economy_changes = {
                        'void_delta': state_changes.get('void_change', 0),
                        'void_triggers': state_changes.get('void_reasons', []),
                        'void_source': state_changes.get('void_source', ''),
                        'soulcredit_delta': state_changes.get('soulcredit_change', 0),
                        'soulcredit_reasons': state_changes.get('soulcredit_reasons', []),
                        'soulcredit_source': state_changes.get('soulcredit_source', '')
                    }

                    # Build clock states from current clock positions
                    clock_states = {}
                    for clock_name, clock in mechanics.scene_clocks.items():
                        clock_states[clock_name] = f"{clock.current}/{clock.maximum}"

                    # Extract effects from narration and state changes
                    effects = []
                    if state_changes.get('conditions'):
                        for cond in state_changes['conditions']:
                            effects.append(f"{cond['type']}: {cond['description']}")

                    # Build context with ritual and combat info
                    is_ritual_action = action.get('is_ritual', False) or action.get('action_type') == 'ritual'

                    # Extract clock sources from clock_triggers
                    clock_sources = {}
                    for clock_name, ticks, reason, source in state_changes.get('clock_triggers', []):
                        clock_sources[clock_name] = source

                    context = {
                        "action_type": action.get('action_type', 'unknown'),
                        "is_ritual": is_ritual_action,
                        "faction": action.get('faction', 'Unknown'),
                        "description": action.get('description', ''),
                        "narration": resolution.get('narration', ''),
                        "is_free_action": action.get('is_free_action', False),
                        "initiative": initiative,
                        "clock_deltas": clock_deltas,  # Include clock before/after/reason
                        "clock_sources": clock_sources,  # Include source for each clock change
                        "target": action.get('target'),  # Target ID for combat/social actions
                        # FIX: Add damage_effects from state_changes (for JSONL logging)
                        # NOTE: void changes already tracked via economy.void_delta + void_triggers
                        "damage_effects": state_changes.get('damage_effects', [])
                    }

                    # Add ritual context if this was a ritual
                    if is_ritual_action:
                        context['ritual'] = True
                        # Extract ritual details from action
                        context['altar'] = action.get('has_altar', False)
                        context['offering'] = action.get('offering_consumed', False)  # Use actual consumption result
                        context['offering_item'] = action.get('offering_item')  # Which item was consumed
                        context['echo_calibrator'] = action.get('has_echo_calibrator', False)

                    # Add combat triplet if present
                    if combat_data:
                        context['combat'] = combat_data

                    # Add prompt metadata if available
                    if hasattr(self, '_last_prompt_metadata') and self._last_prompt_metadata:
                        context['prompt_metadata'] = self._last_prompt_metadata.to_dict()

                    # REMOVED: character_data extraction (redundant with character_state events)
                    # Saves ~7,200 tokens/session by avoiding duplication
                    # ML pipeline can reconstruct from character_state snapshots instead

                    # Extract goal from action intent/description
                    goal = action.get('intent') or action.get('description', 'Unknown goal')

                    # Generate contextual fields for ML training
                    environment = self._generate_environment_description(player_id)
                    stakes = self._generate_stakes_description(player_id)
                    roll_formula = self._generate_roll_formula(action_resolution)
                    rationale = self._generate_rationale(action_resolution, action)

                    # Extract outcome_tiers from structured output (if present)
                    # NOTE: action_resolution is from mechanics, not structured output
                    # We need to check self._last_structured_resolution instead
                    outcome_tiers_with_narratives = None
                    purchase_data = None
                    crafting_data = None
                    attunement_data = None
                    currency_transfer_data = None
                    item_transfer_data = None
                    aware_agents_list = None
                    if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution:
                        if hasattr(self._last_structured_resolution, 'outcome_tiers') and self._last_structured_resolution.outcome_tiers:
                            # Convert OutcomeTierExplanation objects to dicts for JSON serialization
                            outcome_tiers_with_narratives = {}
                            for tier, explanation in self._last_structured_resolution.outcome_tiers.items():
                                outcome_tiers_with_narratives[tier] = {
                                    'narrative': explanation.narrative,
                                    'mechanical_effect': explanation.mechanical_effect
                                }

                        # Extract purchase, crafting, transfer data from effects
                        if hasattr(self._last_structured_resolution, 'effects') and self._last_structured_resolution.effects:
                            effects_data = self._last_structured_resolution.effects
                            if hasattr(effects_data, 'purchase') and effects_data.purchase:
                                # Convert Pydantic model to dict for JSON serialization
                                purchase_data = effects_data.purchase.model_dump()
                            if hasattr(effects_data, 'crafting') and effects_data.crafting:
                                # Convert Pydantic model to dict for JSON serialization
                                crafting_data = effects_data.crafting.model_dump()
                            if hasattr(effects_data, 'attunement') and effects_data.attunement:
                                # Convert Pydantic model to dict for JSON serialization
                                attunement_data = effects_data.attunement.model_dump()
                            if hasattr(effects_data, 'currency_transfer') and effects_data.currency_transfer:
                                # Convert Pydantic model to dict for JSON serialization
                                currency_transfer_data = effects_data.currency_transfer.model_dump()
                            if hasattr(effects_data, 'item_transfer') and effects_data.item_transfer:
                                # Convert Pydantic model to dict for JSON serialization
                                item_transfer_data = effects_data.item_transfer.model_dump()

                        # Extract aware_agents for stealth/secrets visibility
                        if hasattr(self._last_structured_resolution, 'aware_agents'):
                            aware_agents_list = self._last_structured_resolution.aware_agents

                    mechanics.jsonl_logger.log_action_resolution(
                        round_num=round_num,
                        phase="adjudicate",
                        agent_name=character_name,
                        action=action.get('intent', action.get('description', 'unknown')),
                        resolution=action_resolution,
                        economy_changes=economy_changes,
                        clock_states=clock_states,
                        effects=effects,
                        context=context,
                        inventory_changes=inventory_changes,  # Pass offering consumption tracking
                        purchase_data=purchase_data,  # Pass purchase transaction data
                        crafting_data=crafting_data,  # Pass crafting attempt data
                        attunement_data=attunement_data,  # Pass attunement ritual data
                        currency_transfer_data=currency_transfer_data,  # Pass currency transfer data
                        item_transfer_data=item_transfer_data,  # Pass item transfer data
                        # ML training fields (dataset guidelines compliance)
                        # character_data removed - redundant with character_state events
                        environment=environment,
                        stakes=stakes,
                        goal=goal,
                        roll_formula=roll_formula,
                        rationale=rationale,
                        outcome_tiers_with_narratives=outcome_tiers_with_narratives,
                        aware_agents=aware_agents_list
                    )

                    # Track action for round summary statistics
                    if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                        self.shared_state.session.track_action_resolution(
                            success=_resolution_success(action_resolution),
                            margin=action_resolution.margin
                        )

            resolutions.append({
                'player_id': player_id,
                'character_name': character_name,
                'initiative': initiative,
                'action': action,
                'resolution': resolution,
                'state_changes': state_changes
            })

            # Track action outcome for failure loop detection
            if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                action_type = action.get('action_type', 'unknown')
                success_tier = resolution.get('outcome', {}).get('success_tier', 'UNKNOWN')
                void_change = state_changes.get('void_change', 0)

                session = self.shared_state.session
                if character_name not in session._character_action_history:
                    session._character_action_history[character_name] = []

                session._character_action_history[character_name].append(
                    (action_type, success_tier, void_change, round_num)
                )

                # Keep only last 5 actions per character
                if len(session._character_action_history[character_name]) > 5:
                    session._character_action_history[character_name] = session._character_action_history[character_name][-5:]

        # Send individual resolutions to each player
        for res in resolutions:
            # Prepare serializable resolution data (exclude non-serializable ActionResolution object)
            structured_adjudication = None
            if self._outcome_first_enabled():
                from .outcome_pipeline import ActionAdjudication

                resolution_model = res['resolution'].get('resolution')
                if resolution_model is not None and hasattr(resolution_model, 'success_tier'):
                    structured_adjudication = ActionAdjudication(
                        success_tier=getattr(resolution_model, 'success_tier'),
                        margin=getattr(resolution_model, 'margin', 0),
                        effects=getattr(resolution_model, 'effects'),
                        reasoning_short=getattr(
                            resolution_model,
                            'reasoning_short',
                            getattr(resolution_model, 'rationale', None) or 'Mechanics applied from the resolved action.',
                        ),
                        skill_override=getattr(resolution_model, 'skill_override', None),
                        action_skipped=getattr(resolution_model, 'action_skipped', False),
                        skip_reason=getattr(resolution_model, 'skip_reason', None),
                        aware_agents=getattr(resolution_model, 'aware_agents', []) or [],
                    ).model_dump(mode='json')
                elif resolution_model is not None:
                    # Legacy mechanical fallbacks can still reach this envelope
                    # during replay/provider failures. Preserve a typed, minimal
                    # adjudication instead of dereferencing new-schema fields.
                    from .schemas.shared_types import SuccessTier
                    legacy_tier = getattr(resolution_model, 'outcome_tier', 'failure')
                    legacy_tier = getattr(legacy_tier, 'value', legacy_tier)
                    try:
                        tier = SuccessTier(str(legacy_tier))
                    except ValueError:
                        tier = SuccessTier.MODERATE if getattr(resolution_model, 'success', False) else SuccessTier.FAILURE
                    structured_adjudication = ActionAdjudication(
                        success_tier=tier,
                        margin=int(getattr(resolution_model, 'margin', 0)),
                        reasoning_short='Legacy mechanics fallback applied during replay.',
                    ).model_dump(mode='json')

            serializable_res = {
                'player_id': res['player_id'],
                'character_name': res['character_name'],
                'initiative': res['initiative'],
                'action': res['action'],
                'resolution': res['resolution']['outcome'],  # Use serialized outcome instead of raw resolution
                'narration': '' if self._outcome_first_enabled() else res['resolution']['narration'],
                'effects': res['resolution'].get('effects'),
                'adjudication': structured_adjudication,
                'aware_agents': res['resolution'].get('aware_agents', []),
                'action_skipped': res['resolution'].get('action_skipped', False),
                'skip_reason': res['resolution'].get('skip_reason'),
            }

            # Build lightweight effects summary for story beat generation
            sc = res.get('state_changes', {})
            effects_summary = {
                'total_damage_dealt': sum(d.get('dealt', 0) for d in sc.get('damage_effects', [])),
                'conditions': [c.get('type', '') for c in sc.get('conditions', [])],
            }

            self.send_message_sync(
                MessageType.ACTION_RESOLVED,
                None,  # Broadcast
                {
                    'agent_id': res['player_id'],
                    'action_index': action_index,  # Include action index for multi-action turns
                    'original_action': res['action'],
                    'outcome': res['resolution']['outcome'],
                    'narration': res['resolution']['narration'],
                    'aware_agents': res['resolution'].get('aware_agents', []),  # Visibility control for stealth/secrets
                    'resolution_data': serializable_res,  # Include serializable resolution for later synthesis
                    'effects_summary': effects_summary  # Damage/conditions for story beat generation
                }
            )

            # Update stealth state for target filtering (enemies/NPCs can't target hidden PCs)
            aware_agents_for_stealth = res['resolution'].get('aware_agents', [])
            acting_pc_id = res['player_id']
            if self.shared_state and acting_pc_id.startswith('player_'):
                # Extract margin from resolution for stealth duration
                outcome_res = res['resolution'].get('outcome', {}).get('resolution', {})
                stealth_margin = outcome_res.get('margin', 0) if isinstance(outcome_res, dict) else 0
                self.shared_state.update_stealth(
                    acting_pc_id, aware_agents_for_stealth,
                    margin=stealth_margin, current_round=round_num
                )

        # Only do synthesis if not skipping (for sequential resolution, synthesis comes later)
        if not skip_synthesis:
            # Generate synthesis of what happened
            synthesis = await self._synthesize_round_outcome(resolutions, round_num)
            print(f"\n[DM {self.agent_id}] ===== Round Synthesis =====")
            print(synthesis)
            print("=" * 40)

            # Parse synthesis for consequences (void gains, character deaths)
            # Note: Clock spawning and pivot handling is done in session.py when synthesis is distributed
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine

                # Check for void corruption mentioned in synthesis
                from .outcome_parser import parse_void_triggers
                void_change, void_reasons, _source, _target, _compliance = parse_void_triggers(synthesis, "", "moderate")

                if void_change > 0:
                    # Apply void to ALL characters (consequence of filled clock)
                    print(f"\n⚠️  Synthesis indicates +{void_change} void corruption to all characters!")
                    for agent_id in mechanics.void_states.keys():
                        mechanics.void_states[agent_id].add_void(
                            void_change,
                            f"Clock consequence: {', '.join(void_reasons)}",
                            action_id=f"synthesis_{round_num}"
                        )
                        new_void = mechanics.void_states[agent_id].score
                        print(f"  {agent_id}: Now at {new_void}/10 void")

                        # Check for dissolution
                        if new_void >= 10:
                            print(f"\n💀 {agent_id} HAS REACHED VOID 10 - DISSOLUTION")
                            # Character is lost

                # Log synthesis
                if mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_synthesis(round_num, synthesis)

            # Broadcast the round synthesis to all players
            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,  # Broadcast
                {
                    'narration': synthesis,
                    'is_round_synthesis': True,
                    'round': round_num
                }
            )

        # Signal that adjudication is complete
        self.send_message_sync(
            MessageType.ACTION_RESOLVED,
            None,
            {'agent_id': 'adjudication'}
        )

        print(f"\n[DM {self.agent_id}] ===== Adjudication Complete =====\n")

    async def _generate_round_synthesis_structured(
        self,
        prompt: str,
        result_type=None,
        system_prompt: Optional[str] = None,
    ) -> Optional['RoundSynthesis']:
        """
        Generate round synthesis using Pydantic AI structured output (Phase 5).
        Returns RoundSynthesis if successful, or None to fall back to legacy.
        """
        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug("DM: No llm_provider available for synthesis, will use legacy text generation")
            return None

        try:
            from .schemas.story_events import RoundSynthesis
            result_type = result_type or RoundSynthesis

            logger.debug("DM: Attempting structured output for round synthesis")

            model = self.llm_config.get('model', 'claude-sonnet-4-5')
            max_tokens = self.llm_config.get('max_tokens', 6000)  # RoundSynthesis needs more tokens (OpenAI especially verbose)
            temperature = self.llm_config.get('temperature', 1.0)

            # Get current round for logging and display
            current_round = None
            if self.shared_state and self.shared_state.mechanics_engine:
                current_round = self.shared_state.mechanics_engine.current_round

            # Include round number in system prompt to help DM track pacing
            round_display = f" **Session Round {current_round}**" if current_round is not None else ""
            system_prompt = system_prompt or f"You are the DM for Aeonisk YAGS, synthesizing a round of actions.{round_display}"

            # Generate structured synthesis using Pydantic AI
            # Token tracking now handled internally
            synthesis = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=result_type,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                llm_logger=self.llm_logger,  # Enable automatic token tracking
                current_round=current_round
            )

            logger.debug(f"✓ DM structured synthesis: {len(synthesis.narration)} chars, story_advance={synthesis.story_advancement is not None}")

            # Also log to human-readable agent prompt log if enabled
            if self.agent_prompt_logger:
                try:
                    full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
                    self.agent_prompt_logger.log_llm_call(
                        agent_id=self.agent_id,
                        round_num=current_round,
                        call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                        prompt=full_prompt,
                        response=synthesis.model_dump_json(indent=2),
                        model=model,
                        temperature=temperature,
                        metadata={
                            'purpose': 'round_synthesis_structured',
                            'note': f'Pydantic structured output ({result_type.__name__} schema)'
                        }
                    )
                except Exception as e:
                    logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

            return synthesis

        except Exception as e:
            logger.error(f"DM: Structured synthesis failed: {type(e).__name__}: {e}")
            return None

    async def check_conversions(self, round_number: int, resolution_summary: str, pre_round: bool = False, existing_entities: dict = None, social_target_ids: set = None):
        """
        Separate conversion check phase - determine which enemies/NPCs should convert.

        Called AFTER all action resolutions, BEFORE synthesis.
        This allows the DM to focus solely on conversion decisions without
        mixing narrative synthesis responsibilities.

        Can also be called in PRE-ROUND mode (before round 1) to populate the scene
        with additional entities based on the scenario.

        Args:
            round_number: Current round number (0 for pre-round)
            resolution_summary: Summary of all action resolutions this round
            pre_round: If True, this is pre-round setup (no combat yet)
            existing_entities: Dict with 'npcs' and 'enemies' lists of already-spawned IDs

        Returns:
            ConversionDecisions with enemy_conversions, escalations, npc_spawns

        Raises:
            RuntimeError: If llm_provider not initialized (replay mode)
        """
        from .schemas.story_events import ConversionDecisions
        import yaml
        import os

        mode_str = "pre-round setup" if pre_round else f"round {round_number}"
        logger.debug(f"DM: Running conversion check for {mode_str}")

        # For pre-round mode, modify resolution_summary to indicate setup phase
        if pre_round:
            # Build context about what's already been spawned from config
            existing_context = ""
            if existing_entities:
                if existing_entities.get('npcs'):
                    existing_context += f"\nAlready spawned NPCs: {', '.join(existing_entities['npcs'])}"
                if existing_entities.get('enemies'):
                    existing_context += f"\nAlready spawned enemies: {', '.join(existing_entities['enemies'])}"

            resolution_summary = f"""PRE-ROUND SETUP PHASE
No combat has occurred yet. The scenario has just been established.

Your task is to populate the scene with appropriate entities that would naturally be present:
- Vendors, merchants, or service providers appropriate to the location
- Bystanders, civilians, or background NPCs that add atmosphere
- Environmental objects that players can interact with (terminals, containers, etc.)
- Patrols or guards that would logically be present (as enemies if hostile)

IMPORTANT: Do NOT spawn entities that duplicate what's already present.
{existing_context}

Focus on what makes sense for the location and scenario theme.
Do NOT spawn enemy conversions or escalations (no combat has happened yet)."""

        # 1. Build available enemies list
        available_enemies = []
        if self.shared_state:
            enemy_combat = self.shared_state.enemy_combat
            if enemy_combat and hasattr(enemy_combat, 'enemy_agents'):
                for enemy in enemy_combat.enemy_agents:
                    if enemy.is_active:  # Only active enemies (not defeated/retreated)
                        health_pct = int((enemy.health / enemy.max_health) * 100) if enemy.max_health > 0 else 0

                        # Flag conversion candidates (HP-based or social target)
                        markers = []
                        if health_pct < 30:
                            markers.append("🎯 CANDIDATE")
                        if social_target_ids and enemy.agent_id in social_target_ids:
                            markers.append("🎯 SOCIAL TARGET")
                        marker = " ".join(markers)

                        morale = getattr(enemy, 'morale_behavior', 'flee_when_broken')
                        faction = getattr(enemy, 'faction', 'Unknown')
                        brief = getattr(enemy, 'character_brief', '')
                        enemy_line = f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP, morale: {morale}, faction: {faction}) {marker}".strip()
                        if brief:
                            enemy_line += f"\n  Character: {brief[:100]}"
                        available_enemies.append(enemy_line)

        # 2. Build available NPCs list
        available_npcs = []
        if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
            for npc in self.shared_state.npc_agents:
                health_pct = int((npc.health / npc.max_health) * 100) if hasattr(npc, 'max_health') and npc.max_health > 0 else 100

                # Flag NPCs who took damage (escalation candidates)
                took_damage = health_pct < 100
                marker = "⚠️ TOOK DAMAGE" if took_damage else ""

                npc_faction = getattr(npc, 'faction', 'Unknown')
                available_npcs.append(
                    f"{npc.agent_id} ({npc.name}, {npc_faction}, {npc.disposition}, {health_pct}% HP) {marker}".strip()
                )

        # 3. Build player character names list
        player_characters = []
        if self.shared_state and hasattr(self.shared_state, 'session'):
            session = self.shared_state.session
            if hasattr(session, 'agents'):
                from .player import AIPlayerAgent
                for agent in session.agents:
                    if isinstance(agent, AIPlayerAgent):
                        if hasattr(agent, 'character_state') and hasattr(agent.character_state, 'name'):
                            player_characters.append(agent.character_state.name)

        # 4. Build scenario context (location, theme, void level, situation, clocks)
        scenario_context = "Unknown scenario"
        if self.current_scenario:
            scenario_context = f"""**Current Scenario:**
Theme: {self.current_scenario.theme}
Location: {self.current_scenario.location}
Situation: {self.current_scenario.situation}
Void Level: {self.current_scenario.void_level}/10"""

            # Add clock states (show approaching danger and filled clocks)
            if self.shared_state and self.shared_state.mechanics_engine:
                clocks = self.shared_state.mechanics_engine.get_all_clocks()
                if clocks:
                    clock_lines = []
                    for clock in clocks:
                        ticks = clock['current_ticks']
                        max_ticks = clock['max_ticks']
                        percent = int((ticks / max_ticks) * 100) if max_ticks > 0 else 0

                        # Flag filled clocks (just completed this round) and near-completion clocks
                        marker = ""
                        if clock.get('filled'):
                            marker = " 🎯 FILLED"
                        elif percent >= 80:
                            marker = " ⚠️ CRITICAL"
                        elif percent >= 60:
                            marker = " ⚡ HIGH"

                        clock_lines.append(f"  - {clock['name']}: {ticks}/{max_ticks} ({percent}%){marker}")

                    scenario_context += "\n\n**Active Clocks:**\n" + "\n".join(clock_lines)

        # 4. Load conversion check prompt from YAML
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "prompts/claude/en/dm/dm_conversion_check.yaml"
        )

        with open(prompt_path, 'r') as f:
            prompt_data = yaml.safe_load(f)

        # 5. Format prompt with context
        prompt = prompt_data['conversion_check_prompt'].format(
            scenario_context=scenario_context,
            player_characters=", ".join(player_characters) if player_characters else "Unknown players",
            available_enemies="\n".join(available_enemies) if available_enemies else "No active enemies",
            available_npcs="\n".join(available_npcs) if available_npcs else "No active NPCs",
            resolution_summary=resolution_summary
        )

        # 5. Check if llm_provider available (not replay mode)
        if not self.llm_provider:
            raise RuntimeError("DM llm_provider not initialized - cannot run conversion check (replay mode?)")

        logger.debug(f"DM: Calling LLM for conversion decisions (round {round_number})")

        # 6. Call LLM with structured output (Pydantic AI)
        # Token tracking now handled internally
        try:
            decisions: ConversionDecisions = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=ConversionDecisions,
                system_prompt="You are the DM determining which conversions should occur based on action resolutions.",
                max_tokens=3000,  # Increased for complex ConversionDecisions schemas
                temperature=self.llm_config.get('temperature', 1.0),
                llm_logger=self.llm_logger,  # Enable automatic token tracking
                current_round=round_number
            )

            logger.debug(f"✓ DM conversion decisions: {len(decisions.enemy_conversions)} enemy conversions, "
                        f"{len(decisions.escalations)} NPC escalations, {len(decisions.npc_spawns)} NPC spawns, "
                        f"{len(decisions.enemy_spawns)} enemy spawns")

            # 8. Also log to human-readable agent prompt log if enabled
            if self.agent_prompt_logger:
                try:
                    system_prompt = "You are the DM determining conversions."
                    full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
                    self.agent_prompt_logger.log_llm_call(
                        agent_id=self.agent_id,
                        round_num=round_number,
                        call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                        prompt=full_prompt,
                        response=decisions.model_dump_json(indent=2),
                        model=self.llm_config.get('model', 'claude-sonnet-4-5'),
                        temperature=self.llm_config.get('temperature', 1.0),
                        metadata={'purpose': 'entity_lifecycle_conversion_check', 'note': 'Pydantic AI structured output (ConversionDecisions schema)'}
                    )
                except Exception as e:
                    logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

            return decisions

        except Exception as e:
            logger.error(f"DM: Conversion check failed: {type(e).__name__}: {e}")
            # Return empty decisions on failure (no conversions)
            return ConversionDecisions(
                enemy_conversions=[],
                escalations=[],
                npc_spawns=[],
                reasoning=f"Conversion check failed: {str(e)}"
            )

    async def assess_round_actions(self, declarations: List[Dict[str, Any]],
                                   scene_context: str,
                                   round_number: int):
        """One batch call per round: authoritative difficulty per declared
        action, plus attribute/skill ratification.

        The DM assesses blind to the players' difficulty_estimates - the
        estimates stay in the declaration events as counterfactuals, and
        showing them here would just re-anchor the assessment on them.

        Returns RoundAssessment, or None on any failure (callers fall
        back to the calculate_dc category table - never stall a session
        on this call).
        """
        import os
        import yaml
        from .round_assessment import RoundAssessment

        if not self.llm_provider or not declarations:
            return None

        try:
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "prompts/claude/en/dm/dm_round_assessment.yaml"
            )
            with open(prompt_path, 'r') as f:
                prompt_data = yaml.safe_load(f)

            decl_lines = []
            for action in declarations:
                name = (action.get('character_name')
                        or action.get('character') or 'Unknown')
                skill = action.get('skill') or 'no skill (unskilled)'
                ritual = " [RITUAL - engine floors at 22]" \
                    if action.get('is_ritual') else ""
                decl_lines.append(
                    f"- {name}: \"{action.get('intent', '')}\" "
                    f"(framed as {action.get('attribute')} × {skill}){ritual}"
                )

            prompt = prompt_data['round_assessment_prompt'].format(
                scene_context=scene_context or "No additional scene context",
                declarations="\n".join(decl_lines)
            )

            assessment: RoundAssessment = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=RoundAssessment,
                system_prompt=(
                    "You are the DM assessing action difficulty from "
                    "fiction and stakes before dice are rolled."),
                max_tokens=2000,
                temperature=self.llm_config.get('temperature', 1.0),
                llm_logger=self.llm_logger,
                current_round=round_number
            )

            logger.info(
                f"DM round assessment: "
                f"{[(a.character_name, a.difficulty) for a in assessment.assessments]}")
            return assessment

        except Exception as e:
            logger.warning(f"DM round assessment failed (falling back to "
                           f"category table): {e}")
            return None

    async def adjudicate_round_post_resolution(self, resolution_summary: str,
                                               round_number: int,
                                               scene_context: str = ""):
        """EXPERIMENT (config-gated, observe-only): stripped-context
        Nexus-law adjudication of the round's resolved actions.

        Same model, live in the session, but the context is only the law
        rubric and the resolved actions - no narrative history, no
        narrator role. Rulings are logged, never applied. Returns
        PostRulings or None on any failure.
        """
        import os
        import yaml
        from .post_adjudication import PostRulings

        if not self.llm_provider or not resolution_summary:
            return None

        try:
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "prompts/claude/en/dm/dm_post_adjudication.yaml"
            )
            with open(prompt_path, 'r') as f:
                prompt_data = yaml.safe_load(f)

            context_block = ""
            if scene_context:
                context_block = (
                    "\n  **The story so far (for weighing intent and "
                    "mitigation - the law still applies):**\n"
                    f"{scene_context}\n")
            from .nexus_law import OPERATIONAL_RUBRIC
            prompt = prompt_data['post_adjudication_prompt'].format(
                law_rubric=OPERATIONAL_RUBRIC,
                resolution_summary=resolution_summary,
                scene_context=context_block)

            rulings: PostRulings = await self.llm_provider.generate_structured(
                prompt=prompt,
                result_type=PostRulings,
                system_prompt=(
                    "You are a Sovereign Nexus adjudicator applying codified "
                    "law to resolved actions. You are not narrating a story."),
                max_tokens=2000,
                temperature=self.llm_config.get('temperature', 1.0),
                llm_logger=self.llm_logger,
                current_round=round_number
            )
            return rulings
        except Exception as e:
            logger.warning(f"Post-resolution adjudication failed (experiment "
                           f"continues without this round): {e}")
            return None

    async def _synthesize_applied_outcomes(
        self,
        resolutions: List[Dict[str, Any]],
        round_num: int,
        entity_lifecycle_result=None,
    ):
        """Generate the sole literary account from authoritative applied outcomes."""
        import json

        from .outcome_pipeline import (
            AppliedOutcome,
            OutcomeRoundSynthesis,
            RoundSynthesisFailClosed,
            SynthesisValidationError,
            canonicalize_synthesis_visibility,
            finalize_synthesis_narration,
            prose_safe_outcome_payload,
            snapshot_shared_state,
            validate_outcome_synthesis,
        )

        outcomes = [
            AppliedOutcome.model_validate(resolution['applied_outcome'])
            for resolution in resolutions
            if resolution.get('applied_outcome')
        ]
        if not outcomes:
            raise RuntimeError("Outcome-first synthesis received no applied outcomes")

        previous_ending = self._round_synthesis_history[-1][1] if self._round_synthesis_history else ""
        safe_payload = prose_safe_outcome_payload(outcomes)
        lifecycle_data = entity_lifecycle_result or {}
        if not isinstance(lifecycle_data, dict):
            lifecycle_data = lifecycle_data.to_jsonl_dict(round_num)

        def lifecycle_name(entity_id: str) -> str:
            if not self.shared_state:
                return entity_id
            entities = list(getattr(self.shared_state, 'player_agents', []) or [])
            entities += list(getattr(self.shared_state, 'npc_agents', []) or [])
            enemy_combat = getattr(self.shared_state, 'enemy_combat', None)
            entities += list(getattr(enemy_combat, 'enemy_agents', []) or [])
            entities += list(getattr(self.shared_state, 'current_env_objects', []) or [])
            for entity in entities:
                if (getattr(entity, 'agent_id', None) == entity_id
                        or getattr(entity, 'object_id', None) == entity_id):
                    state = getattr(entity, 'character_state', None)
                    return str(getattr(state, 'name', None) or getattr(entity, 'name', entity_id))
            return entity_id

        safe_lifecycle = {
            'morale_events': [
                {
                    'type': event.get('type'),
                    'character_name': event.get('character_name'),
                }
                for event in lifecycle_data.get('morale_events', [])
            ],
        }
        for key in (
            'enemies_spawned', 'npcs_spawned', 'enemies_converted',
            'npcs_escalated', 'npcs_departed', 'enemies_departed',
            'env_objects_spawned',
        ):
            safe_lifecycle[key] = [lifecycle_name(item) for item in lifecycle_data.get(key, [])]
        prompt = f"""Write the canonical literary narration for round {round_num}.

AUTHORITATIVE, PROSE-SAFE OUTCOMES (chronological):
{json.dumps(safe_payload, indent=2)}

PRIOR CANONICAL ENDING:
{previous_ending or '(opening round)'}

ACCEPTED ENTITY LIFECYCLE CHANGES:
{json.dumps(safe_lifecycle, indent=2, default=str)}

BINDING CONTRACT:
- Narrate only the supplied applied outcomes. Intent is not outcome.
- Preserve chronological and causal order.
- Establish the setting once; do not restart every paragraph with the location.
- Merge causally compatible actions when useful, but preserve each distinct consequence.
- Order segments by their earliest outcome; a beat may absorb later reactions,
  but never narrate an effect before its cause.
- Render a restricted-visibility outcome in its own segment whose visibility
  exactly matches that outcome's viewers; never mix restricted and public
  outcomes in one segment.
- Integrate only useful declared dialogue. Omit repetitive or inert speech.
- Never print HP, wounds, stuns, rolls, DCs, margins, clock ticks, target IDs, or round labels.
- Use the supplied prose-facing names, not registry labels.
- Do not call a living entity dead, a corpse, lifeless, or taking a last breath.
- `segments[].source_outcome_ids` must identify every outcome represented by that text.
- Cover every consequential outcome exactly once. Nonconsequential passes may be omitted explicitly.
- Every state claim must identify its subject, causing actor, and source outcome.
- Emit a state claim for every supplied damage, death, healing, condition, movement, or dialogue fact.
- Use claim_kind `life_state`/`consciousness`/`combat_state` ONLY when the outcome's
  after-state actually changes that subject. Attitude, cooperation, mood, or other
  soft observations use claim_kind `other` (or no claim at all).
- `symbolic_value` is a short tag of a few words (e.g. "cooperative", "spoken"),
  never a sentence.
- Set `narration` to the segment texts joined in order with blank lines.
- Defer scene transitions to the next round opening; do not propose a pivot or advancement here.

Write cohesive, literary prose rather than a combat log. Favor causal flow, physical
specificity, motive, and a changed final tableau over repeated action summaries.
"""
        max_attempts = max(1, int(self.session_config.get('outcome_synthesis_attempts', 3)))
        validation_errors: List[str] = []
        prior_response_json: Optional[str] = None
        for attempt in range(1, max_attempts + 1):
            retry_context = ""
            if validation_errors:
                # Without the prior response the model regenerates from scratch
                # and oscillates — fixing one error while reverting another.
                # Anchor the retry on its own output so it edits instead.
                prior_block = (
                    f"\n\nYOUR PRIOR RESPONSE:\n{prior_response_json}"
                    if prior_response_json else ""
                )
                retry_context = (
                    prior_block
                    + "\n\nTHE PRIOR RESPONSE WAS REJECTED. Return a corrected "
                    "version of it: fix every error below and change nothing "
                    "else.\n- "
                    + "\n- ".join(validation_errors)
                )
            synthesis = await self._generate_round_synthesis_structured(
                prompt + retry_context,
                result_type=OutcomeRoundSynthesis,
                system_prompt=(
                    "You are the literary DM for Aeonisk YAGS. Mechanics are already "
                    "resolved. Render supplied facts without changing them."
                ),
            )
            if synthesis is None:
                validation_errors = ["structured synthesis returned no result"]
                continue
            # Presentation and viewer ids are enforced in code: narration is
            # derived from segments, and proposed visibility lists are mapped
            # onto the real entity roster before set logic runs over them.
            finalize_synthesis_narration(synthesis)
            canonicalize_synthesis_visibility(
                synthesis,
                {
                    entity_id: snap.name
                    for entity_id, snap in snapshot_shared_state(self.shared_state).items()
                },
            )
            if getattr(self.shared_state, 'session', None) and getattr(
                    self.shared_state.session, 'replay_mode', False):
                # Cached synthesis carries the source run's UUIDs. Requiring
                # those UUIDs to match freshly-created replay entities would
                # turn a valid cache hit into a false divergence.
                return synthesis
            try:
                style_warnings = validate_outcome_synthesis(synthesis, outcomes)
                for warning in style_warnings:
                    logger.info("Synthesis style warning (non-blocking): %s", warning)
                return synthesis
            except SynthesisValidationError as exc:
                validation_errors = exc.errors
                prior_response_json = synthesis.model_dump_json()
                logger.warning(
                    "Outcome synthesis validation failed (attempt %s/%s): %s",
                    attempt,
                    max_attempts,
                    "; ".join(validation_errors),
                )

        mechanics = self.shared_state.mechanics_engine if self.shared_state else None
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_event(
                'round_synthesis_failed',
                {
                    'schema_version': '3.0.0',
                    'attempts': max_attempts,
                    'outcome_ids': [outcome.outcome_id for outcome in outcomes],
                    'validation_errors': validation_errors,
                    'resume_phase': 'synthesis',
                },
                round_num,
            )
        raise RoundSynthesisFailClosed(
            "Outcome-first synthesis exhausted validation attempts: "
            + "; ".join(validation_errors)
        )

    async def _synthesize_round_outcome(self, resolutions: List[Dict[str, Any]], round_num: int, resolution_state=None, expired_clocks=None, entity_lifecycle_result=None):
        """
        Synthesize all resolutions into a cohesive narrative about what happened.
        This is where conflicts are detected and described.

        Args:
            resolutions: List of resolved actions this round
            round_num: Current round number
            resolution_state: ResolutionState with fled NPCs tracking (optional)
            expired_clocks: List of expired clocks from clock update phase (optional)
            entity_lifecycle_result: EntityLifecycleResult with morale/spawns/conversions (optional)

        Returns:
            Either a RoundSynthesis object (structured) or str (legacy fallback)
        """
        if not resolutions:
            return "The moment passes without incident."

        if self._outcome_first_enabled():
            return await self._synthesize_applied_outcomes(
                resolutions,
                round_num,
                entity_lifecycle_result=entity_lifecycle_result,
            )

        # Build context about what happened
        outcomes_summary = []

        # Helper to resolve target ID to name (defined once, used for all resolutions)
        def resolve_target_name(target_id_or_name: str) -> str:
            """Resolve tgt_xxxx to character name, or return as-is if already a name."""
            if not target_id_or_name:
                return 'unknown'
            if target_id_or_name.startswith('tgt_') and self.shared_state:
                target_mapper = self.shared_state.get_target_id_mapper()
                if target_mapper and target_mapper.enabled:
                    entity = target_mapper.resolve_target(target_id_or_name)
                    if entity and hasattr(entity, 'name'):
                        return entity.name
                    elif entity and hasattr(entity, 'character_state'):
                        return entity.character_state.name
            return target_id_or_name

        for res in resolutions:
            char_name = res.get('character_name', 'Unknown')

            # Handle both old format (full dict) and new format (serializable dict)
            if 'resolution' in res and isinstance(res['resolution'], dict):
                if 'resolution' in res['resolution']:
                    # New serializable format: res['resolution'] is outcome dict
                    resolution_data = res['resolution']['resolution']
                    success = resolution_data.get('success', True) if isinstance(resolution_data, dict) else resolution_data.success
                else:
                    # Old format: res['resolution'] has direct 'outcome' field
                    success = res['resolution'].get('success', True)
            else:
                # Enemy result format or other simplified formats
                success = res.get('result') not in ['invalidated', 'failed', 'target not found']

            # Handle action field - can be dict (PC actions) or string (enemy actions)
            action = res.get('action', {})
            target_info = ""
            if isinstance(action, dict):
                # PC action format: action is a dict with 'intent' or 'description'
                intent = action.get('intent', action.get('description', 'unknown action'))
                # Extract target from PC action and resolve to name
                action_target = action.get('target', '')
                if action_target:
                    resolved_target = resolve_target_name(action_target)
                    target_info = f" → targeting {resolved_target}"
            else:
                # Enemy action format: action is a string like 'attack', 'move', etc.
                intent = str(action)
                # Make it more readable
                if intent == 'attack':
                    target = res.get('target', 'unknown target')
                    resolved_target = resolve_target_name(target)
                    intent = f"attacked {resolved_target}"
                elif intent == 'hold':
                    intent = "held position"
                elif intent == 'dialogue':
                    dialogue = res.get('dialogue_content', '')
                    intent = f'spoke aloud: "{dialogue}"' if dialogue else "attempted to communicate"
                elif intent == 'wait':
                    intent = "held position, observing"

            # Check if action was invalidated
            if res.get('result') == 'invalidated':
                failure_reason = res.get('failure_reason', 'unknown')
                if failure_reason == 'attacker_surrendered':
                    status = "surrendered (action cancelled)"
                elif failure_reason == 'attacker_defeated':
                    status = "already defeated (action cancelled)"
                else:
                    status = f"action invalidated ({failure_reason})"
            else:
                status = "succeeded" if success else "failed"

            # NEW: Extract damage and healing effects from resolution
            effects_info = ""

            # Check PC action effects (structured output format)
            resolution_dict = res.get('resolution', {})
            effects = resolution_dict.get('effects', {})
            if effects:
                # Extract damage dealt
                damage_list = effects.get('damage', [])
                for dmg in damage_list:
                    if isinstance(dmg, dict):
                        dmg_target = resolve_target_name(dmg.get('target', 'unknown'))
                        dmg_dealt = dmg.get('dealt', 0)
                        effects_info += f"\n  💥 {dmg_dealt} damage dealt to {dmg_target}"

                # Extract healing applied
                healing_list = effects.get('healing', [])
                for heal in healing_list:
                    if isinstance(heal, dict):
                        heal_target = resolve_target_name(heal.get('target', 'unknown'))
                        heal_hp = heal.get('hp', 0)
                        if heal_hp:
                            effects_info += f"\n  💚 {heal_hp} HP healed on {heal_target}"

            # Also check enemy action damage (top-level fields, not in resolution.effects)
            if not effects_info and res.get('damage_dealt'):
                dmg_target = resolve_target_name(res.get('target', 'unknown'))
                dmg_dealt = res.get('damage_dealt', 0)
                effects_info += f"\n  💥 {dmg_dealt} damage dealt to {dmg_target}"

            # Include enemy dialogue_content for DM narration (like NPC dialogue)
            if res.get('dialogue_content'):
                effects_info += f'\n  💬 **Enemy\'s Actual Words:** "{res["dialogue_content"]}" — Include this dialogue in your narration.'

            # CRITICAL: Include full narration from individual resolution so DM can maintain consistency
            narration = res.get('narration', '')
            if narration:
                outcomes_summary.append(f"- {char_name} {status} at: {intent}{target_info}{effects_info}\n  Resolution: {narration}")
            else:
                outcomes_summary.append(f"- {char_name} {status} at: {intent}{target_info}{effects_info}")

        outcomes_text = "\n".join(outcomes_summary)

        # NEW: Track casualties - check for dead/defeated characters
        casualties_this_round = []
        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
            for player in self.shared_state.get_all_players():
                if hasattr(player, 'health') and player.health is not None and player.health <= 0:
                    casualties_this_round.append(player.character_state.name)

        # Add casualty alert to outcomes text if anyone died
        if casualties_this_round:
            casualties_alert = f"\n\n💀 **CASUALTIES THIS ROUND:** {', '.join(casualties_this_round)}"
            casualties_alert += "\n⚠️ CRITICAL: Explicitly NAME the dead character(s) in your synthesis!"
            casualties_alert += "\nDO NOT use vague phrases like 'a figure fell' - use their actual name!"
            outcomes_text += casualties_alert

        # NOTE: Clock updates are now applied BEFORE conversion check (in session.py)
        # This allows conversion check to see filled clocks and make informed spawn decisions
        # expired_clocks are passed from session.py after clock update phase
        if expired_clocks is None:
            expired_clocks = []

        # Build expired clocks text for DM prompt
        expired_clocks_text = ""
        if expired_clocks:
            expired_lines = []
            for exp in expired_clocks:
                clock_name = exp['clock_name']
                exp_type = exp['expiration_type']
                current = exp['current']
                maximum = exp['maximum']
                description = exp['description']
                advance_meaning = exp.get('advance_meaning', '')
                regress_meaning = exp.get('regress_meaning', '')
                filled_consequence = exp.get('filled_consequence', '')

                # Build semantic context for expired clock
                semantic_context = ""
                if advance_meaning or regress_meaning:
                    semantic_context = "\n     📊 SEMANTIC CONTEXT:"
                    if advance_meaning:
                        semantic_context += f"\n        Advance = {advance_meaning}"
                    if regress_meaning:
                        semantic_context += f"\n        Regress = {regress_meaning}"
                    semantic_context += f"\n     ⚠️  Use this to interpret if {current}/{maximum} is good or bad!"

                if exp_type == "crisis_averted":
                    expired_lines.append(f"  ⏰ **{clock_name}** (was {current}/{maximum}) - CRISIS AVERTED/OPPORTUNITY LOST{semantic_context}")
                    expired_lines.append(f"     The threat/opportunity has passed without resolution. Narrate how the situation defused or the window closed.")
                elif exp_type == "force_resolve":
                    expired_lines.append(f"  🔔 **{clock_name}** (FILLED: {current}/{maximum}) - TRIGGERING CONSEQUENCES{semantic_context}")
                    if filled_consequence:
                        expired_lines.append(f"     Consequence: {filled_consequence}")
                        # Check if this is a mechanical clock (has markers) or narrative clock
                        if any(marker in filled_consequence for marker in ['[SPAWN_ENEMY:', '[DESPAWN_ENEMY:', '[NEW_CLOCK:', '[ADVANCE_STORY:']):
                            expired_lines.append(f"     → Include the marker from the consequence in your narration")
                        else:
                            expired_lines.append(f"     → This is a NARRATIVE clock - you MUST use a scenario marker ([ADVANCE_STORY: Location | Situation] or [NEW_CLOCK: ...]) to change the story!")
                    else:
                        expired_lines.append(f"     → This clock filled without a consequence. You MUST use [ADVANCE_STORY: Location | Situation] to advance the narrative!")
                elif exp_type == "escalate":
                    expired_lines.append(f"  ⏰ **{clock_name}** (was {current}/{maximum}) - SITUATION ESCALATES{semantic_context}")
                    expired_lines.append(f"     Stalemate breaks. Consider [ADVANCE_STORY: Location | new situation] or [NEW_CLOCK: new pressure] to intensify/resolve.")

            expired_clocks_text = "\n\n⏰ **CLOCKS EXPIRED (Auto-removed):**\n" + "\n".join(expired_lines)
            expired_clocks_text += "\n\n⚠️  You MUST narrate what happens as these clocks expire AND use scenario markers for narrative clocks!"

        # Get current clock state and check for filled clocks
        clock_state_text = ""
        filled_clocks_text = ""
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.scene_clocks:
                clock_lines = []
                critical_overflow = []
                for name, clock in mechanics.scene_clocks.items():
                    if clock.filled:
                        overflow = clock.current - clock.maximum
                        if overflow > 0:
                            if overflow >= 3:
                                status = f"🚨 CRITICAL OVERFLOW: {clock.current}/{clock.maximum} (+{overflow})"
                                critical_overflow.append(name)
                            else:
                                status = f"⚠️  OVERFLOWING: {clock.current}/{clock.maximum} (+{overflow})"
                        else:
                            status = f"FILLED: {clock.current}/{clock.maximum}"
                    else:
                        status = f"{clock.current}/{clock.maximum}"

                    # Add semantic guidance if available
                    clock_info = f"  - {name}: {status}"
                    if clock.advance_meaning or clock.regress_meaning or clock.filled_consequence:
                        clock_info += "\n    "
                        if clock.advance_meaning:
                            clock_info += f"Advance = {clock.advance_meaning}"
                        if clock.regress_meaning:
                            clock_info += f" | Regress = {clock.regress_meaning}"
                        if clock.filled_consequence and clock.filled:
                            clock_info += f"\n    🎯 When filled: {clock.filled_consequence}"

                    clock_lines.append(clock_info)
                if clock_lines:
                    clock_state_text = "\n\n**Current Clock State:**\n" + "\n".join(clock_lines)
                    # Add clock budget guidance
                    budget_text = self._get_clock_budget_text(len(mechanics.scene_clocks))
                    clock_state_text += f"\n\n{budget_text}"

                # Check for newly filled clocks
                filled_clocks = mechanics.get_and_clear_filled_clocks()
                filled_clocks_text = format_filled_clocks_guidance(
                    filled_clocks, critical_overflow=critical_overflow
                )

        # Build enemy spawn instructions (always available if enabled)
        enemy_spawn_prompt = ""
        has_filled_clocks = False
        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()
            if mechanics and mechanics.scene_clocks:
                filled_clocks = mechanics.get_and_clear_filled_clocks()
                has_filled_clocks = bool(filled_clocks)

        if self.config.get('enemy_agents_enabled', False):
            enemy_spawn_prompt = """

═══════════════════════════════════════════════════════════════════════════════
🎭 NPC SPAWNING - CRITICAL FOR NARRATIVE CONSISTENCY 🎭
═══════════════════════════════════════════════════════════════════════════════

**⚠️ GOLDEN RULE: If you NAME an NPC in your narration, you MUST spawn them via `npc_spawns`**

**MANDATORY NPC SPAWNING TRIGGERS:**

You MUST use `npc_spawns` when:
✅ You write a named character in your narration (e.g., "Dr. Vohl flees down the corridor")
✅ Players declare intent to interact with someone ("interrogate the scientist", "talk to the guard")
✅ Your narration describes NPCs present in the scene ("civilians cower in corners", "technician monitors console")
✅ Plot requires a character to exist (antagonists, quest-givers, witnesses, informants, allies)

**⚠️ CRITICAL FAILURE MODE - DO NOT DO THIS:**
❌ Round 1: You write "Dr. Vohl's escape shuttle sits in the hangar..." (Vohl NOT spawned)
❌ Round 2: Players declare "Find and interrogate Dr. Vohl about the research data"
❌ Result: BROKEN NARRATIVE - Vohl doesn't exist as an interactable NPC! Players can't target them!

✅ **CORRECT APPROACH:**
✅ Round 1: Use `npc_spawns` to create Dr. Vohl FIRST
✅ Round 1: THEN mention Vohl in your narration
✅ Round 2: Players can now interact with the spawned NPC (interrogate, persuade, combat)

**NPC Spawning Syntax:**
```python
npc_spawns=[
    NPCSpawn(
        name="Dr. Kellen Vohl",  # EXACT name as it appears in your narration
        faction="Rogue Scientist (formerly ArcGen)",
        entity_type="neutral",  # neutral/ally/prisoner
        threat_level="potential_threat",  # non_combatant/potential_threat/armed_neutral
        disposition="wary",  # friendly/neutral/wary/prisoner
        description="Disheveled researcher with void-stained hands, clutching encrypted data slate, cornered and desperate",
        health=18,
        soak=0,
        skills={"Systems": 14, "Science": 12, "Guile": 10}  # Skills for interaction/interrogation
    )
]
```

**Common NPC Types & When to Use:**

1. **Plot Antagonists** (Dr. Vohl, Captain Torres, corrupt officials):
   - `entity_type="neutral"`, `threat_level="potential_threat"`
   - Give relevant skills for interaction (Guile for lying, Systems for hacking, Combat for fighting if escalates)
   - Always spawn if named in narration!

2. **Quest-Givers / Informants** (contacts, witnesses, defectors):
   - `entity_type="neutral"` or `"ally"`, `threat_level="non_combatant"`
   - Give social/knowledge skills (Area Lore, Corporate Influence, Science)

3. **Civilians** (dock workers, bystanders, refugees):
   - `entity_type="neutral"`, `threat_level="non_combatant"`
   - Minimal skills or empty dict

4. **Converted Enemies** (use `deescalations` field instead - see below):
   - Don't use `npc_spawns` for surrendered enemies
   - Use `deescalations` to convert existing enemies to NPCs

**When NPCs become hostile:**
Use `escalations` field to convert NPC → enemy:
```python
escalations=[
    Escalation(
        npc_id="npc_dr_vohl_1234",  # ← NPC's agent_id
        reason="Cornered and panicked, Vohl draws concealed weapon and fires at pursuers",
        template="desperate_fighter"
    )
]
```

═══════════════════════════════════════════════════════════════════════════════

**NPC MANAGEMENT (De-escalation System):**

⚠️ **CRITICAL: NARRATIVE-MECHANICAL ALIGNMENT** ⚠️

If your narration describes surrender, detention, prisoners, or peaceful resolution:
→ You MUST populate `deescalations` field with the converted enemies
→ Narrative alone does NOT change combat state
→ Enemy agents fight based on structured state, NOT narrative text
→ Divergence = enemies keep fighting despite narration saying they surrendered

**IF YOU WRITE "surrendered" or "detained" or "prisoner" in narration:**
→ USE `deescalations` field with exact enemy_id from "Active Enemies" list

---

When enemies surrender, calm down, or negotiate, use the `deescalations` field to convert them to NPCs:

**⚠️ CRITICAL: Use `deescalations` NOT `enemy_removals` for surrenders!**
- `deescalations` → Enemy STAYS in scene as NPC (prisoner, neutral, ally)
- `enemy_removals` → Enemy LEAVES scene entirely (fled, escaped)

**When to use de-escalation:**
✅ Enemy surrenders after intimidation/negotiation
✅ Enemy convinced to stand down peacefully
✅ Morale breaks and enemy yields
✅ Successful diplomatic resolution

**How to use deescalations field:**
```python
deescalations=[
    Deescalation(
        enemy_id="enemy_grunt_adbb6db0",  # ← EXACT agent_id from Active Enemies list!
        resulting_entity_type="prisoner",  # neutral, ally, or prisoner
        resulting_disposition="prisoner",  # friendly, neutral, wary, or prisoner
        reason="Surrendered after successful intimidation, now restrained and compliant"
    )
]
```

**Dispositions (NPC attitude):**
- `"prisoner"` → Captured, restrained, under guard
- `"wary"` → Suspicious, will flee if threatened again
- `"neutral"` → Calm, indifferent, observing
- `"friendly"` → Cooperative, helpful, allied

**Entity Types (relationship to players):**
- `"prisoner"` → Captured enemy (restrained)
- `"neutral"` → Non-aligned NPC
- `"ally"` → Friendly NPC who may help

**⚠️ IMPORTANT:** Use the EXACT `enemy_id` from the "Active Enemies" list above. DO NOT make up IDs!

---

**ENEMY SPAWNING (Structured Output):**

You can spawn enemies using the `enemy_spawns` field in RoundSynthesis. Spawn enemies when narratively appropriate:

✅ **Common spawn triggers:**
- Clock with spawn consequence fills (e.g., "Security Alarms" → guards respond)
- Void corruption spreads → void creatures emerge
- Investigation reveals threats → ambush/reinforcements
- Story escalation → enemies join the fight
- Environmental events → creatures/guards appear

**How to spawn:**
Use the `enemy_spawns` field in your RoundSynthesis response. Each EnemySpawn needs:
- `template`: "Grunt", "Elite", or "Boss" (determines HP/stats)
- `faction`: Who they work for (e.g., "ACG Security", "Void Cultists")
- `archetype`: Their role (e.g., "Enforcer", "Ritualist", "Heavy Gunner")
- `count`: How many (1-5)
- `spawn_reason`: Why they appeared (10+ chars, e.g., "Reinforcements arrive via transit tunnel")
- `initial_position`: Where they start (FAR_ENEMY, NEAR_ENEMY, etc.)
- `custom_traits` (optional): Special tactics/behavior

**Example:**
```python
enemy_spawns=[
    EnemySpawn(
        template="Grunt",
        faction="ACG",
        archetype="Enforcer",
        count=2,
        spawn_reason="Alarm triggered, security team responds",
        initial_position=Position.FAR_ENEMY,
        custom_traits="tactical_ranged"
    )
]
```

**Templates:** Grunt (~12 HP), Elite (~20 HP), Boss (~40 HP)
**Positions:** FAR_ENEMY, NEAR_ENEMY, ENGAGED, EXTREME_ENEMY

**Pacing:** Use spawns to maintain tension. Don't overwhelm players with too many at once. Clock-based spawns provide predictability; emergent spawns provide dynamism."""

        # Build enemy status context (for de-escalation system)
        enemy_status_context = ""
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None

            if enemy_combat and enemy_combat.enabled:
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                if active_enemies:
                    enemy_lines = []
                    for enemy in active_enemies:
                        health_pct = (enemy.health / enemy.max_health * 100) if enemy.max_health > 0 else 0

                        # Use target ID if free targeting is enabled, otherwise use agent_id
                        if target_id_mapper and target_id_mapper.enabled:
                            target_id = target_id_mapper.get_target_id(enemy.agent_id)
                            if target_id:
                                # NEW FORMAT: [tgt_xxxx] Name - HP (for structured output)
                                enemy_lines.append(f"  - [{target_id}] {enemy.name} - {enemy.health}/{enemy.max_health} HP ({health_pct:.0f}%)")
                            else:
                                # Fallback if target ID not found
                                logger.warning(f"No target ID found for enemy {enemy.agent_id}, using agent_id")
                                enemy_lines.append(f"  - {enemy.name} (ID: {enemy.agent_id}) - {enemy.health}/{enemy.max_health} HP ({health_pct:.0f}%)")
                        else:
                            # Legacy format when free targeting disabled
                            enemy_lines.append(f"  - {enemy.name} (ID: {enemy.agent_id}) - {enemy.health}/{enemy.max_health} HP ({health_pct:.0f}%)")

                    enemy_status_context = "\n\n**Active Enemies:**\n" + "\n".join(enemy_lines)

                    # Update de-escalation instruction based on mode
                    if target_id_mapper and target_id_mapper.enabled:
                        enemy_status_context += "\n\n⚠️  MECHANICAL FIELDS: Use target IDs (e.g., tgt_7a3f) in damage/conditions fields."
                        enemy_status_context += "\n⚠️  NARRATIVE TEXT: Use character NAMES (e.g., 'Security Guard') in narration, NOT target IDs."
                        enemy_status_context += "\n⚠️  For deescalations, use agent_id (e.g., enemy_grunt_adbb6db0), NOT target IDs."
                    else:
                        enemy_status_context += "\n\n⚠️  If enemies surrender/calm down, use `deescalations` field with their exact agent_id (e.g., enemy_grunt_adbb6db0)"

        # Build NPC status context
        npc_status_context = ""
        if self.shared_state and self.shared_state.npc_agents:
            npc_lines = []
            for npc in self.shared_state.npc_agents:
                if getattr(npc, 'is_active', True):
                    npc_line = f"  - {npc.name} (ID: {npc.agent_id}) - {npc.entity_type}/{npc.disposition}"
                    # Include NPC description/personality for escalation decision-making
                    if hasattr(npc, 'description') and npc.description:
                        # Truncate description to 200 chars for prompt efficiency
                        desc = npc.description if len(npc.description) <= 200 else npc.description[:197] + "..."
                        npc_line += f"\n    Personality: {desc}"
                    npc_lines.append(npc_line)

            if npc_lines:
                npc_status_context = "\n\n**Active NPCs:**\n" + "\n".join(npc_lines)
                npc_status_context += "\n\n⚠️  If NPCs become hostile, use `escalations` field with their exact agent_id\n⚠️  Check NPC personalities for escalation triggers (paranoia, low thresholds, etc.)"

        # Build player health status context (for injury/casualty awareness)
        player_status_context = ""
        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
            player_agents = self.shared_state.get_all_players()
            if player_agents:
                player_lines = []
                for player in player_agents:
                    health_pct = (player.health / player.max_health * 100) if player.max_health > 0 else 0

                    # Status indicator
                    if health_pct <= 20:
                        status_flag = " ⚠️ CRITICAL"
                    elif health_pct <= 50:
                        status_flag = " (Bloodied)"
                    elif health_pct <= 75:
                        status_flag = " (Wounded)"
                    else:
                        status_flag = ""

                    # Wound information
                    wounds = getattr(player, 'wounds', 0)
                    wounds_text = f"{wounds} wounds" if wounds > 0 else "no wounds"

                    player_lines.append(f"  - {player.character_state.name}: {player.health}/{player.max_health} HP ({health_pct:.0f}%), {wounds_text}{status_flag}")

                player_status_context = "\n\n**Party Health Status:**\n" + "\n".join(player_lines)
                player_status_context += "\n\n⚠️  IMPORTANT: If players took significant damage this round, MENTION their injuries in your narration!"
                player_status_context += "\n⚠️  Players near death (≤20% HP) or critically wounded (≥4 wounds) should be described struggling/desperate."

                # Add defeated character rules if anyone is at 0 HP
                defeated_chars = [line for line in player_lines if "0/" in line or "CRITICAL" in line]
                if defeated_chars or casualties_this_round:
                    player_status_context += "\n\n**DEFEATED CHARACTER RULES:**"
                    player_status_context += "\n- Characters at 0 HP are UNCONSCIOUS or DEAD. They cannot speak, act, or contribute."
                    player_status_context += "\n- Do NOT give dying words to characters who died rounds ago."
                    player_status_context += "\n- Do NOT narrate unconscious characters as participating in conversations."
                    player_status_context += "\n- If someone stabilized a character, narrate them as \"stabilized but unconscious\" NOT \"back on their feet.\""
                    player_status_context += "\n- Check Party Health Status above — anyone at 0 HP is DOWN."

        # Build fled NPCs context (for narrative consistency)
        fled_npcs_context = ""
        if resolution_state and hasattr(resolution_state, 'fled_npcs') and resolution_state.fled_npcs:
            fled_npc_names = []
            if self.shared_state and self.shared_state.npc_agents:
                for npc in self.shared_state.npc_agents:
                    if npc.agent_id in resolution_state.fled_npcs:
                        fled_npc_names.append(npc.name)

            if fled_npc_names:
                fled_npcs_context = "\n\n**⚠️ FLED NPCs (NO LONGER PRESENT):**\n"
                fled_npcs_context += "The following NPCs fled/left the scene earlier this round:\n"
                fled_npcs_context += "\n".join([f"  - {name}" for name in fled_npc_names])
                fled_npcs_context += "\n\n**CRITICAL:** Do NOT narrate fled NPCs as present in the scene. They have left and cannot interact with players."

        # Build entity lifecycle context (morale, spawns, conversions)
        entity_lifecycle_context = ""
        if entity_lifecycle_result:
            # Reconstruct EntityLifecycleResult if it's a dict (from message serialization)
            from .schemas.story_events import EntityLifecycleResult
            if isinstance(entity_lifecycle_result, dict):
                # Manually reconstruct from dict
                lifecycle_obj = EntityLifecycleResult(
                    morale_events=entity_lifecycle_result.get('morale_events', []),
                    conversion_decisions=entity_lifecycle_result.get('conversion_decisions'),
                    enemies_spawned=entity_lifecycle_result.get('enemies_spawned', []),
                    npcs_spawned=entity_lifecycle_result.get('npcs_spawned', []),
                    enemies_converted=entity_lifecycle_result.get('enemies_converted', []),
                    npcs_escalated=entity_lifecycle_result.get('npcs_escalated', []),
                    npcs_departed=entity_lifecycle_result.get('npcs_departed', [])
                )
            else:
                lifecycle_obj = entity_lifecycle_result

            lifecycle_summary = lifecycle_obj.to_synthesis_context()
            if lifecycle_summary != "Entity Lifecycle: No changes":
                entity_lifecycle_context = f"\n\n**{lifecycle_summary}**\n"
                entity_lifecycle_context += "⚠️  These entity state changes have ALREADY occurred. Your narration should be consistent with them.\n"

                # Add detailed morale events if present
                if lifecycle_obj.morale_events:
                    entity_lifecycle_context += "\n**Morale Events:**\n"
                    for event in lifecycle_obj.morale_events:
                        entity_lifecycle_context += f"  - {event['character_name']}: {event['type']} ({event.get('narration', '')})\n"

        # Check if story advancement is needed (all clocks complete)
        story_advancement_prompt = ""
        if self.needs_story_advancement:
            logger.info("Story advancement triggered - adding prompt context")
            story_advancement_prompt = """

🎬 **STORY ADVANCEMENT - MAJOR NARRATIVE SHIFT**

⚠️  **Scenario clocks are complete or a major story beat has occurred.** Time to advance the narrative!

**Use the `story_advancement` field in RoundSynthesis:**

Set `should_advance=True` and provide:
- `location`: New location name (e.g., "Rebel Safe House", "Void Nexus Archive")
- `situation`: Brief description of the new scenario (e.g., "You've escaped the ambush. Time to regroup.")
- `new_void_level` (optional): Update if environmental void changes (0-10)
- `clear_all_enemies`: Usually True (default) - enemies don't follow to new location
- `new_clocks`: List of 2-4 NewClock objects for the fresh scenario

**Example:**
```python
story_advancement=StoryAdvancement(
    should_advance=True,
    location="Abandoned Transit Hub",
    situation="The security alarms have brought you here. You must find an escape route before reinforcements arrive.",
    new_void_level=4,
    clear_all_enemies=True,
    new_clocks=[
        NewClock(
            name="Escape Route",
            max_ticks=6,
            description="Find a working transit tunnel before lockdown completes"
        ),
        NewClock(
            name="Security Response",
            max_ticks=8,
            description="Heavy ACG forces converge on your position"
        )
    ]
)
```

**When to advance:**
- All clocks complete (current trigger)
- Major story beat completes (investigation reveals villain identity, ritual completed, etc.)
- Critical single clock fills that changes everything
- Players achieve/fail primary objective

**What happens:** Clocks clear, location updates, enemies despawn (unless `clear_all_enemies=False`), new clocks spawn.
"""

        # Build scenario context for synthesis (same as action resolution)
        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"""
**Current Scenario:**
Theme: {self.current_scenario.theme}
Location: {self.current_scenario.location}
Situation: {self.current_scenario.situation}
Void Level: {self.current_scenario.void_level}/10
"""

        # Use LLM to generate synthesis if available
        if self.llm_config:
            prompt = f"""You are the DM for a dark sci-fi TTRPG. Multiple characters just acted simultaneously.
{scenario_context}
**What they tried to do:**
{outcomes_text}
{player_status_context}
{clock_state_text}
{filled_clocks_text}
{expired_clocks_text}
{enemy_status_context}
{npc_status_context}
{fled_npcs_context}
{entity_lifecycle_context}
{story_advancement_prompt}

**⚠️ CRITICAL - ENTITY LIFECYCLE:**
All entity spawns, conversions, and lifecycle changes were ALREADY HANDLED in the Entity Lifecycle Phase (before synthesis).
The RoundSynthesis schema NO LONGER has enemy_spawns, enemy_conversions, npc_spawns, or escalations fields.
Your narration should describe these changes narratively (they're shown in the context above), but you don't trigger them mechanically.

**⚠️ CLOCKS ARE DIFFERENT - YOU CAN STILL SPAWN THEM:**

Unlike entities (handled in Entity Lifecycle Phase), **spawning NEW clocks is YOUR responsibility** in synthesis!

**Use ScenePivot.new_clocks for minor complications (same location):**
- Failed actions trigger countermeasures → "Security Alert" clock spawns (max_ticks=6)
- Successful loud actions attract attention → "ACG Investigation" clock spawns (max_ticks=8)
- Filled clocks create new pressures → "Alarm" fills → "Reinforcements En Route" spawns (max_ticks=4)
- Scene feels static (2-3 rounds, no new clocks) → Add complication clock

**Use StoryAdvancement.new_clocks for major transitions (new location/chapter):**
- Story beats complete → New situation with 2-4 fresh clocks
- Location changes via StoryAdvancement → Clocks for new threats/objectives at new location
- Critical filled clock triggers chapter shift → New clocks for escalated stakes

**When to spawn clocks:**
✅ Every 2-3 rounds if no new clocks recently spawned (prevents static scenarios)
✅ Filled clocks create cascading consequences ("Breach" fills → "Evacuation" + "Containment Failure" spawn)
✅ Player successes/failures open new complications (steal data → "Corporate Trackers" spawns)
✅ Environmental changes (ritual backfires → "Void Manifestation" spawns)
❌ Don't spawn if you just spawned 2+ clocks last round (pacing, avoid overwhelming players)

**Example - Failed Stealth (same location):**
```python
scene_pivot=ScenePivot(
    should_pivot=False,  # Still in same room
    new_clocks=[
        NewClock(
            name="Facility Lockdown",
            max_ticks=6,
            description="Security protocols activate after intruder detected",
            advance_meaning="lockdown systems engage",
            regress_meaning="lockdown systems bypassed",
            filled_consequence="All exits sealed, armed response team deployed"
        )
    ]
)
```

**Example - Filled Clock Cascade:**
```python
# If "Security Alarm" clock just filled:
scene_pivot=ScenePivot(
    should_pivot=False,
    new_clocks=[
        NewClock(
            name="ACG Tactical Response",
            max_ticks=5,
            description="Elite security forces converge on your position",
            filled_consequence="Heavy combat squad arrives, lethal force authorized"
        )
    ]
)
```

**Example - Story Advancement (new location):**
```python
story_advancement=StoryAdvancement(
    should_advance=True,
    location="Reactor Core Access",
    situation="Your sabotage has brought you deep into the facility's heart...",
    new_clocks=[
        NewClock(name="Meltdown Sequence", max_ticks=10, description="Reactor critical, 10 minutes until catastrophic failure"),
        NewClock(name="Escape Route", max_ticks=6, description="Find working transit tunnel before blast doors seal"),
        NewClock(name="Corporate Pursuit", max_ticks=8, description="ACG forces tracking your movements")
    ]
)
```

**Remember:** Clocks drive dynamic tension! Spawn them liberally when justified by narrative consequences.

**Your task:** Write a cohesive, DETAILED narrative (800-1800 characters, aim for 1200+) synthesizing these individual resolutions into a unified round outcome.

**⚠️ LENGTH REQUIREMENT: 800+ characters minimum! Be generous with detail, dialogue, and atmosphere.**

**⚠️ CRITICAL - NARRATIVE CONSISTENCY:**
- Each "Resolution:" above shows what you ALREADY narrated for that action
- Your synthesis MUST be consistent with these established facts
- DO NOT contradict details like names, locations, or outcomes from individual resolutions
- Your job is to WEAVE these resolutions together, not re-narrate them from scratch
- If resolution says "Kress Vane in Sector 7", don't change it to "The Collector in Sublevel 9"

**⚠️ CRITICAL - ENTITY-NARRATIVE ALIGNMENT (STRICT):**
- You MUST NOT describe specific hostile combatants (snipers, guards, attackers, shooters) that are not in the "Active Enemies" list above
- To introduce new threats, spawn them via Entity Lifecycle Phase (enemy_spawns) FIRST — only then may you narrate their presence
- Narrating phantom enemies causes players to target non-existent hostiles, resulting in friendly fire casualties
- Environmental tension without specific hostiles is acceptable:
  ✅ "Shadows shift along the rooftop parapets, the air thick with ozone"
  ✅ "Something moves in the dark — too fast to identify"
  ❌ "A sniper takes position on the rooftop" (implies targetable enemy — MUST spawn first)
  ❌ "Guards approach from three directions" (implies targetable enemies — MUST spawn first)
- If the Active Enemies list is EMPTY, narrate a post-combat or transitional scene — do not introduce new hostiles without spawning them

**Storytelling Elements - Make it NARRATIVE, not just reportage:**

**SHOW, Don't Tell:**
- ✅ "Her hands shake as the calibrator stutters, void-light flickering"
- ❌ "She attempts to calibrate the device"
- ✅ "'Back off or bleed,' he growls, hand on the grip"
- ❌ "He threatens them"
- ✅ "The broker's smile fractures, ink signatures suddenly worthless"
- ❌ "The negotiation succeeds"

**Include for richness (1200+ chars):**
- **Quoted dialogue** - Actual words spoken during confrontations, pleas, negotiations
- **Character body language** - Trembling hands, locked jaws, exhaled relief, predatory smiles
- **Sensory atmosphere** - Ozone smell, humming machinery, crackling energy, whispered deals
- **Consequences unfolding** - Show immediate results (signatures blink, crowds part, alarms trip)
- **Timing & rhythm** - Fastest actor moves first, creates conditions for next, cascading effects
- **Emotional arcs** - Desperation → relief, confidence → shock, tension → resolution
- **Stakes manifest** - If clocks don't advance, show frustration/fear; if they fill, show consequences happening
- **Scene-ending snapshot** - Final tableau showing new status quo after dust settles

**Narrative voice:** Write like a novel, not a combat log. Use metaphor, imagery, active verbs. Make readers *feel* the scene.

Be vivid, cinematic, and VERBOSE. Shorter narrations feel rushed - aim for rich, detailed storytelling that immerses readers.

If the team is failing their objectives (clocks not advancing or bad clocks filling), your narration should reflect the growing desperation, consequences, and danger.

**⚠️  CLOCK INTERPRETATION - READ CAREFULLY:**
Each clock has semantic meaning shown as "Advance = X" and "Regress = Y".
- If "Advance = threat escalates", then HIGH values are BAD for players
- If "Advance = progress made", then HIGH values are GOOD for players
- Use the semantic labels to interpret whether clock changes help or hurt the party
- When a clock REGRESSES, check if that's good (threat reduced) or bad (progress lost)

**CRITICAL**: If any clocks just filled, you MUST describe the dramatic consequences. This could include:
- Character injury or void corruption (specify who and how much void: "+2 void")
- Character death/dissolution if appropriate
- Mission failure or catastrophic events
- Environmental changes or new threats
- Success and rewards if it's a positive clock

Generate appropriate consequences based on what makes sense for that specific clock in this scenario.

{enemy_spawn_prompt}"""

            # Try structured output first (Phase 5: Pydantic AI migration)
            structured_synthesis = await self._generate_round_synthesis_structured(prompt)

            if structured_synthesis:
                # Return structured object directly (no marker conversion)
                logger.debug(f"✓ Using structured synthesis: {len(structured_synthesis.narration)} chars, "
                           f"story_advance={structured_synthesis.story_advancement and structured_synthesis.story_advancement.should_advance}")
                return structured_synthesis

            # Legacy text generation fallback
            logger.warning("DM: Structured synthesis failed, falling back to legacy text generation")
            logger.warning("⚠️  LEGACY FALLBACK is deprecated and will be removed - fix structured output issues instead!")
            try:
                # Use configured provider (not hardcoded Anthropic)
                if not self.llm_provider:
                    logger.error("DM: No LLM provider available for legacy fallback")
                    return None

                llm_response = await self.llm_provider.generate(
                    prompt=prompt,
                    max_tokens=4000,  # Increased for synthesis
                    temperature=self.llm_config.get('temperature', 1.0)
                )
                synthesis_text = llm_response.text

                # Legacy SPAWN_ENEMY marker validation removed - using structured output now

                # Log LLM call for replay
                if self.llm_logger:
                    messages = [{"role": "user", "content": prompt}]
                    estimated_tokens = {
                        'input': count_chat_tokens(messages, self.llm_config.get('model', 'claude-3-5-sonnet-20241022')),
                        'output': count_text_tokens(synthesis_text, self.llm_config.get('model', 'claude-3-5-sonnet-20241022')),
                    }
                    estimated_tokens['total'] = estimated_tokens['input'] + estimated_tokens['output']
                    self.llm_logger._log_llm_call(
                        messages=messages,
                        response=synthesis_text,
                        model=self.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                        temperature=self.llm_config.get('temperature', 1.0),
                        tokens=estimated_tokens,
                        current_round=round_num,
                        call_sequence=self.llm_logger.call_count
                    )

                # Also log to human-readable agent prompt log if enabled
                if self.agent_prompt_logger:
                    try:
                        messages = [{"role": "user", "content": prompt}]
                        estimated_tokens = {
                            'input': count_chat_tokens(messages, self.llm_config.get('model', 'claude-3-5-sonnet-20241022')),
                            'output': count_text_tokens(synthesis_text, self.llm_config.get('model', 'claude-3-5-sonnet-20241022')),
                        }
                        estimated_tokens['total'] = estimated_tokens['input'] + estimated_tokens['output']
                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=round_num,
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=prompt,
                            response=synthesis_text,
                            model=self.llm_config.get('model', 'claude-3-5-sonnet-20241022'),
                            temperature=self.llm_config.get('temperature', 1.0),
                            tokens=estimated_tokens,
                            metadata={'purpose': 'round_synthesis_legacy'}
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                # Clear story advancement flag after synthesis generation
                if self.needs_story_advancement:
                    logger.info("Story advancement synthesis generated - clearing flag")
                    self.needs_story_advancement = False

                return synthesis_text
            except Exception as e:
                logger.error(f"Synthesis generation failed: {e}")
                # Clear flag even on error
                if self.needs_story_advancement:
                    self.needs_story_advancement = False
                return f"Round {round_num} completes with mixed results:\n{outcomes_text}"
        else:
            # Clear flag even if no LLM
            if self.needs_story_advancement:
                self.needs_story_advancement = False
            return f"Round {round_num} completes:\n{outcomes_text}"

    async def _resolve_purchase_transaction(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a pre-validated purchase transaction using specialized narration.

        Purchases are mechanical (currency deducted, item added) and just need atmospheric narration.
        Uses dedicated dm_purchase.yaml prompt focused on transaction narration.

        Args:
            action: Action dict with purchase_validation data

        Returns:
            Resolution dict matching standard format
        """
        from .schemas.action_resolution import ActionResolution
        from .mechanics import OutcomeTier

        character_name = action.get('character_name', 'Character')
        intent = action.get('intent', 'Purchase item')
        purchase_validation = action.get('purchase_validation', {})

        executed = purchase_validation.get('executed', False)
        item_name = purchase_validation.get('item_name', 'item')
        cost = purchase_validation.get('cost', {})
        failure_reason = purchase_validation.get('failure_reason', 'Unknown')

        logger.debug(f"Purchase transaction for {character_name}: executed={executed}, item={item_name}")

        if self._outcome_first_enabled():
            return self._build_mechanics_only_resolution(
                executed=executed,
                reasoning=(
                    f"Validated purchase of {item_name} completed."
                    if executed else f"Validated purchase failed: {failure_reason}"
                ),
            )

        # Load purchase-specific prompt
        try:
            system_prompt_obj = load_modular_prompt(
                agent_type="dm",
                module_names=["dm_purchase"],
                provider="claude",
                language="en"
            )
            system_prompt = system_prompt_obj.content if hasattr(system_prompt_obj, 'content') else str(system_prompt_obj)
        except Exception as e:
            logger.warning(f"Failed to load dm_purchase prompt: {e}, using inline")
            system_prompt = "Narrate a purchase transaction. No dice rolls - just atmospheric narration based on validation result."

        # Build user prompt with purchase context
        user_prompt = f"""
Character: {character_name}
Action: {intent}

Purchase Validation Result:
- Transaction Executed: {executed}
- Item: {item_name}
- Cost: {cost}
- Failure Reason: {failure_reason if not executed else 'N/A'}

Generate an ActionResolution for this {'successful' if executed else 'failed'} purchase transaction.
"""

        # Call LLM for structured narration
        try:
            model = self.llm_config.get('model', 'claude-sonnet-4-5')
            max_tokens = 4000  # Increased from 2000 - prevent OpenAI finish_reason:length errors
            temperature = 0.7

            # Token tracking now handled internally
            purchase_resolution: ActionResolution = await self.llm_provider.generate_structured(
                prompt=user_prompt,
                result_type=ActionResolution,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                llm_logger=self.llm_logger,  # Enable automatic token tracking
                current_round=self.shared_state.mechanics_engine.current_round if self.shared_state and self.shared_state.mechanics_engine else None
            )

            narration = purchase_resolution.narration  # Use .narration (new Pydantic schema)
            logger.debug(f"✓ Purchase LLM narration: {len(narration)} chars")

        except Exception as e:
            logger.warning(f"Purchase LLM call failed: {e}, using fallback narration")
            # Fallback to simple template
            if executed:
                cost_str = ", ".join([f"{v} {k.title()}" for k, v in cost.items()])
                narration = f"{character_name} inserts {cost_str} into the payment slot. The machine processes the transaction and dispenses {item_name}."
            else:
                narration = f"{character_name} attempts to purchase {item_name}, but the transaction fails: {failure_reason}."

            # Create fallback ActionResolution using new Pydantic schema
            from .schemas.action_resolution import SuccessTier, MechanicalEffects
            purchase_resolution = ActionResolution(
                narration=narration,
                success_tier=SuccessTier.MODERATE if executed else SuccessTier.FAILURE,
                margin=0,
                effects=MechanicalEffects()  # Purchase already executed mechanically
            )

        # Return resolution matching standard format (includes effects key for session.py)
        return {
            'resolution': purchase_resolution,
            'narration': purchase_resolution.narration,
            'state_changes': {},
            'combat_data': {},
            'inventory_changes': [],
            'effects': {},  # Empty effects dict (purchase already executed mechanically)
            'outcome': {
                'dm_response': getattr(purchase_resolution, 'narrative', getattr(purchase_resolution, 'narration', '')),
                'success': getattr(purchase_resolution, 'success', True),
                'consequences': [],
                'narration': getattr(purchase_resolution, 'narrative', getattr(purchase_resolution, 'narration', '')),
                'resolution': {
                    'intent': getattr(purchase_resolution, 'intent', None),
                    'attribute': getattr(purchase_resolution, 'attribute', None),
                    'skill': getattr(purchase_resolution, 'skill', None),
                    'total': getattr(purchase_resolution, 'total', None),
                    'difficulty': getattr(purchase_resolution, 'difficulty', None),
                    'margin': purchase_resolution.margin if hasattr(purchase_resolution, 'margin') else 0,
                    'outcome_tier': purchase_resolution.outcome_tier.value if hasattr(purchase_resolution, 'outcome_tier') and hasattr(purchase_resolution.outcome_tier, 'value') else str(getattr(purchase_resolution, 'outcome_tier', 'unknown')),
                    'success': getattr(purchase_resolution, 'success', True)
                }
            }
        }

    async def _resolve_transfer_transaction(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a pre-validated energy currency transfer using specialized narration.

        Transfers are mechanical (currency moved between purses) and just need atmospheric narration
        with Soulcredit interpretation based on context.
        Uses dedicated dm_transfer.yaml prompt focused on physical exchange and moral implications.

        Args:
            action: Action dict with transfer_validation data

        Returns:
            Resolution dict matching standard format
        """
        from .schemas.action_resolution import ActionResolution
        from .mechanics import OutcomeTier

        character_name = action.get('character_name', 'Character')
        intent = action.get('intent', 'Transfer currency')
        transfer_validation = action.get('transfer_validation', {})

        executed = transfer_validation.get('executed', False)
        sender_name = transfer_validation.get('sender_name', character_name)
        receiver_name = transfer_validation.get('receiver_name', 'Unknown')
        currency = transfer_validation.get('currency', {})
        failure_reason = transfer_validation.get('failure_reason', 'Unknown')

        logger.debug(f"Transfer transaction: {sender_name} → {receiver_name}, executed={executed}, currency={currency}")

        if self._outcome_first_enabled():
            return self._build_mechanics_only_resolution(
                executed=executed,
                reasoning=(
                    f"Validated transfer from {sender_name} to {receiver_name} completed."
                    if executed else f"Validated transfer failed: {failure_reason}"
                ),
            )

        # Load transfer-specific prompt
        try:
            system_prompt_obj = load_modular_prompt(
                agent_type="dm",
                module_names=["dm_transfer"],
                provider="claude",
                language="en"
            )
            system_prompt = system_prompt_obj.content if hasattr(system_prompt_obj, 'content') else str(system_prompt_obj)
        except Exception as e:
            logger.warning(f"Failed to load dm_transfer prompt: {e}, using inline")
            system_prompt = "Narrate an energy currency transfer. No dice rolls - just atmospheric narration of the physical exchange and Soulcredit interpretation based on context (charity, bribery, fair exchange, etc.)."

        # Build user prompt with transfer context
        user_prompt = f"""
Character: {character_name}
Action: {intent}

Transfer Validation Result:
- Transaction Executed: {executed}
- Sender: {sender_name}
- Receiver: {receiver_name}
- Currency: {currency}
- Failure Reason: {failure_reason if not executed else 'N/A'}

Generate an ActionResolution for this {'successful' if executed else 'failed'} energy transfer.

Context for Soulcredit interpretation:
Read the action intent to understand WHY this transfer is happening:
- Charity/aid → +1 to +3 Soulcredit for giver
- Fair exchange → 0 Soulcredit (neutral)
- Bribery → -1 to -3 Soulcredit for giver
- Coercion/extortion → Negative Soulcredit for both parties
"""

        # Call LLM for structured narration
        try:
            model = self.llm_config.get('model', 'claude-sonnet-4-5')
            max_tokens = 4000  # Increased from 2000 - prevent OpenAI finish_reason:length errors
            temperature = 0.7

            # Token tracking now handled internally
            transfer_resolution: ActionResolution = await self.llm_provider.generate_structured(
                prompt=user_prompt,
                result_type=ActionResolution,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                llm_logger=self.llm_logger,  # Enable automatic token tracking
                current_round=self.shared_state.mechanics_engine.current_round if self.shared_state and self.shared_state.mechanics_engine else None
            )

            narration = transfer_resolution.narration  # Use .narration (new Pydantic schema)
            logger.debug(f"✓ Transfer LLM narration: {len(narration)} chars")

        except Exception as e:
            logger.warning(f"Transfer LLM call failed: {e}, using fallback narration")
            # Fallback to simple template
            if executed:
                currency_str = ", ".join([f"{v} {k.title()}" for k, v in currency.items()])
                narration = f"{sender_name} presses {currency_str} into {receiver_name}'s palm—talismans changing hands in a brief exchange."
            else:
                narration = f"{sender_name} attempts to transfer currency to {receiver_name}, but the transaction fails: {failure_reason}."

            # Create fallback ActionResolution using new Pydantic schema
            from .schemas.action_resolution import SuccessTier, MechanicalEffects
            transfer_resolution = ActionResolution(
                narration=narration,
                success_tier=SuccessTier.MODERATE if executed else SuccessTier.FAILURE,
                margin=0,
                effects=MechanicalEffects()  # Transfer already executed mechanically
            )

        # Return resolution matching standard format
        return {
            'resolution': transfer_resolution,
            'narration': transfer_resolution.narration,
            'state_changes': {},
            'combat_data': {},
            'inventory_changes': [],
            'effects': {},  # Empty effects dict (transfer already executed mechanically)
            'outcome': {
                'dm_response': getattr(transfer_resolution, 'narrative', getattr(transfer_resolution, 'narration', '')),
                'success': getattr(transfer_resolution, 'success', True),
                'consequences': [],
                'narration': getattr(transfer_resolution, 'narrative', getattr(transfer_resolution, 'narration', '')),
                'resolution': {
                    'intent': getattr(transfer_resolution, 'intent', None),
                    'attribute': getattr(transfer_resolution, 'attribute', None),
                    'skill': getattr(transfer_resolution, 'skill', None),
                    'total': getattr(transfer_resolution, 'total', None),
                    'difficulty': getattr(transfer_resolution, 'difficulty', None),
                    'margin': transfer_resolution.margin if hasattr(transfer_resolution, 'margin') else 0,
                    'outcome_tier': transfer_resolution.outcome_tier.value if hasattr(transfer_resolution, 'outcome_tier') and hasattr(transfer_resolution.outcome_tier, 'value') else str(getattr(transfer_resolution, 'outcome_tier', 'unknown')),
                    'success': getattr(transfer_resolution, 'success', True)
                }
            }
        }

    def _resolve_target_name(self, target_id: str) -> Optional[str]:
        """
        Resolve a target ID (tgt_xxxx or agent_id) to a character name.

        Args:
            target_id: Target ID or agent ID

        Returns:
            Character name if found, None otherwise
        """
        if not target_id:
            return None

        # Try target ID mapper first (resolves tgt_xxxx to actual agent)
        if target_id.startswith('tgt_') and self.shared_state.target_id_mapper:
            agent = self.shared_state.target_id_mapper.resolve_target(target_id)
            if agent:
                # Player agent
                if hasattr(agent, 'character_state') and hasattr(agent.character_state, 'name'):
                    return agent.character_state.name
                # NPC or enemy agent
                elif hasattr(agent, 'name'):
                    return agent.name
                # Fallback to agent_id or vendor_id
                return getattr(agent, 'agent_id', None) or getattr(agent, 'vendor_id', 'Unknown')

        # Try direct agent_id lookup in players
        for player in self.shared_state.player_agents:
            if player.agent_id == target_id:
                return player.character_state.name

        # Try NPCs
        if hasattr(self.shared_state, 'npc_agents'):
            for npc in self.shared_state.npc_agents:
                if npc.agent_id == target_id:
                    return npc.name

        # Try enemies
        if hasattr(self.shared_state, 'enemy_combat') and self.shared_state.enemy_combat:
            for enemy in self.shared_state.enemy_combat.enemy_agents:
                if enemy.agent_id == target_id:
                    return enemy.name

        return None

    def _build_mechanics_only_resolution(
        self,
        *,
        executed: bool,
        reasoning: str,
        margin: int = 0,
        effects: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Build a non-literary resolution for deterministic/specialized actions."""
        from .outcome_pipeline import ActionAdjudication
        from .schemas.action_resolution import MechanicalEffects, SuccessTier

        adjudication = ActionAdjudication(
            success_tier=SuccessTier.MODERATE if executed else SuccessTier.FAILURE,
            margin=margin,
            effects=effects or MechanicalEffects(),
            reasoning_short=reasoning,
        )
        self._last_structured_resolution = adjudication
        return {
            'resolution': adjudication,
            'narration': '',
            'state_changes': {},
            'combat_data': {},
            'inventory_changes': [],
            'effects': adjudication.effects.model_dump(mode='json'),
            'outcome': {
                'dm_response': '',
                'success': executed,
                'consequences': [],
                'narration': '',
                'resolution': {
                    'success_tier': adjudication.success_tier.value,
                    'margin': margin,
                    'success': executed,
                },
            },
        }

    async def _resolve_failed_attunement(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve an attunement action that failed pre-validation (no dice roll needed).

        Args:
            action: Action dict with attunement_validation showing failure

        Returns:
            Resolution dict with auto-failure narration
        """
        from .schemas.action_resolution import ActionResolution, SuccessTier, MechanicalEffects

        validation = action.get('attunement_validation', {})
        failure_reason = validation.get('failure_reason', 'Prerequisites not met')
        character_name = action.get('character_name', 'Character')
        intent = action.get('intent', 'attune a seed')

        if self._outcome_first_enabled():
            return self._build_mechanics_only_resolution(
                executed=False,
                reasoning=f"Attunement prerequisites were not met: {failure_reason}",
                margin=-999,
            )

        # Generate simple auto-failure narration
        narration = (
            f"{character_name} attempts to {intent}, but {failure_reason.lower()}. "
            f"The ritual cannot proceed without the necessary components. "
            f"No energy is expended and no seed is consumed."
        )

        # Pad to minimum 200 chars
        if len(narration) < 200:
            narration = narration + " " * (200 - len(narration))

        failed_resolution = ActionResolution(
            narration=narration,
            success_tier=SuccessTier.FAILURE,
            margin=-999,  # Automatic failure
            effects=MechanicalEffects()  # No effects
        )

        # Store structured resolution for later extraction
        self._last_structured_resolution = failed_resolution

        logger.info(f"✗ Attunement auto-failed for {character_name}: {failure_reason}")

        # Return resolution matching standard format (with 'outcome' key expected by adjudication)
        return {
            'resolution': failed_resolution,  # ActionResolution Pydantic model
            'narration': narration,
            'state_changes': {},
            'combat_data': {},
            'inventory_changes': [],
            'effects': {},  # No effects for auto-failure
            'outcome': {
                'dm_response': narration,
                'success': False,
                'consequences': [],
                'narration': narration,
                'resolution': {
                    'intent': intent,
                    'attribute': None,
                    'skill': None,
                    'total': None,
                    'difficulty': None,
                    'margin': -999,
                    'success': False,
                    'success_tier': 'failure'
                }
            },
            'validation_failure': True,
            'failure_reason': failure_reason
        }

    async def _resolve_action_mechanically(self, player_id: str, action: Dict[str, Any], previous_resolutions=None) -> Dict[str, Any]:
        """
        Resolve a single action mechanically (rolls, difficulty, narration).

        Args:
            player_id: Agent ID of acting player
            action: Action dict with intent, description, etc.
            previous_resolutions: List of earlier resolved actions this round (for narrative consistency)

        Returns resolution data.
        """
        # This is essentially the same as _handle_ai_dm_response but returns data instead of sending messages
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        intent = action.get('intent', description)

        # Check if this is a pre-validated purchase (specialized narration)
        purchase_validation = action.get('purchase_validation', {})
        if action_type == 'purchase' and purchase_validation:
            return await self._resolve_purchase_transaction(action)

        # Check if this is a pre-validated transfer (specialized narration)
        transfer_validation = action.get('transfer_validation', {})
        if action_type == 'transfer' and transfer_validation:
            return await self._resolve_transfer_transaction(action)

        # Check if this is a pre-validated attunement that FAILED validation
        # (no need for dice rolls - auto-fail)
        attunement_validation = action.get('attunement_validation', {})
        if action_type == 'attune' and attunement_validation and not attunement_validation.get('is_valid'):
            return await self._resolve_failed_attunement(action)

        # Check if this is an NPC action (lightweight adjudication)
        if action.get('is_npc'):
            from .schemas.action_resolution import ActionResolution
            from .mechanics import OutcomeTier

            character_name = action.get('character_name', 'NPC')
            npc_action_type = action.get('action_type', 'unknown')  # action_type is in the action dict
            target = action.get('target')
            outcome_first = self._outcome_first_enabled()

            # Resolve target ID to character name for dialogue/plead actions
            target_display = 'no specific target'
            if target:
                target_name = self._resolve_target_name(target)
                if target_name:
                    target_display = f"{target_name} ({target})"
                else:
                    target_display = target

            logger.debug(f"Lightweight NPC adjudication for {character_name}: {intent} (type: {npc_action_type}, target: {target_display})")

            # Import required schema types
            from .schemas.action_resolution import SuccessTier, MechanicalEffects
            from .schemas.shared_types import Condition

            # Default for pass actions (template narration, not a fallback)
            is_fallback = False

            # Special case: "pass" actions use template narration (no LLM call)
            if npc_action_type == 'pass':
                narration = f"{character_name} passes because the situation doesn't involve them and they don't want to do anything."
                # Pad to minimum 200 chars if needed
                if len(narration) < 200:
                    narration = narration + " " * (200 - len(narration))

                if outcome_first:
                    from .outcome_pipeline import ActionAdjudication
                    npc_resolution = ActionAdjudication(
                        success_tier=SuccessTier.MODERATE,
                        margin=0,
                        effects=MechanicalEffects(),
                        reasoning_short=f"{character_name} deliberately takes no action.",
                    )
                    narration = ''
                else:
                    npc_resolution = ActionResolution(
                        narration=narration,
                        success_tier=SuccessTier.MODERATE,
                        margin=0,
                        effects=MechanicalEffects()
                    )
            else:
                # All other NPC actions: Generate LLM narration
                dialogue_info = ""
                if action.get('dialogue_content'):
                    dialogue_info = f"\n\n**NPC's Actual Words:** \"{action['dialogue_content']}\"\n\n⚠️ IMPORTANT: Include this dialogue in your narration. You may quote it verbatim, paraphrase it naturally, or weave it into the description."

                npc_prompt = f"""Generate vivid, dialogue-rich narration for this NPC action (400-800 characters):

**NPC:** {character_name}
**Action Type:** {npc_action_type}
**NPC's Intent/Reasoning:** {description if description else intent}
**Target:** {target_display}{dialogue_info}

**IMPORTANT - Make it NARRATIVE with dialogue and movement:**

For **dialogue/plead/negotiate actions**, include:
- WHO the NPC is addressing (use target name from above - be specific!)
- The NPC's actual spoken words (quoted dialogue) - expand on what they say
- Their tone of voice, delivery, emphasis
- Body language while speaking (gestures, posture, facial expressions)
- How the TARGET reacts to their words (visual cues, responses)

For **other actions** (flee, hide, assist, attack):
- Physical movements in detail (how they move, where they go, what they touch)
- Emotional state visible in their actions (panic, determination, calculation)
- Immediate consequences of their action

**Examples:**

❌ TOO BRIEF: "He threatens them."

✅ GOOD (dialogue with target): "He turns toward Ash, cuff links catching the light as he folds his hands deliberately. 'Ash, my client will bid fifty thousand—no higher,' he announces, voice smooth as silk but edged with finality. Ash's eyes narrow, but he gives a curt nod. A ripple of held breath and hurried pen scratches marks the room's small surrender."

❌ TOO BRIEF (plead): "She pleads with them."

✅ GOOD (plead with target): "Her breath comes in ragged gasps as she stumbles backward toward Sera, hands raised in supplication. 'Sera—please, I didn't sign up for this!' The words tear out half-sob, half-scream, her eyes locked on Sera's face, searching for mercy. Sera's grip on her weapon tightens, but her expression flickers with uncertainty."

❌ TOO BRIEF: "She flees in panic."

✅ GOOD (flee): "Her breath comes in ragged gasps as she stumbles backward, hands fumbling for the door panel. 'No—no, I didn't sign up for this!' The words tear out half-sob, half-scream. She spins, robes tangling around her ankles, and bolts for the nearest exit arch."

**Write 400-800 characters.** Be cinematic, include dialogue for social actions, show body language and reactions."""

                # Step 1: Generate narration (LLM or fallback)
                if outcome_first:
                    narration = ''
                    is_fallback = False
                else:
                    try:
                    # Call LLM for simple text narration (not structured output - faster and smaller)
                        from pydantic import BaseModel, Field

                        class SimpleNarration(BaseModel):
                            """Narrative text for NPC actions with dialogue and movement."""
                            text: str = Field(..., min_length=400, max_length=1000, description="Cinematic narration of NPC action with quoted dialogue, body language, and consequences (400-1000 chars)")

                    # Token tracking now handled internally
                        npc_narration_response = await self.llm_provider.generate_structured(
                            prompt=npc_prompt,
                            result_type=SimpleNarration,
                            system_prompt="Generate atmospheric narration for NPC actions. Be vivid and concise.",
                            max_tokens=4000,  # Increased from 2000 - prevent OpenAI finish_reason:length errors
                            temperature=self.llm_config.get('temperature', 1.0),
                            llm_logger=self.llm_logger,  # Enable automatic token tracking
                            current_round=self.shared_state.mechanics_engine.current_round if self.shared_state and self.shared_state.mechanics_engine else None
                        )
                        narration = npc_narration_response.text
                        is_fallback = False

                    except Exception as e:
                        logger.warning(f"NPC LLM narration failed: {e}, using fallback")
                        base_narration = f"{character_name} {description}. The NPC's action completes, their presence shifting the dynamics of the scene."
                        if action.get('dialogue_content'):
                            base_narration = f"{character_name} speaks: \"{action['dialogue_content']}\" Their words hang in the air as the scene unfolds around them."
                        if len(base_narration) < 400:
                            base_narration = base_narration + " The moment passes, leaving ripples in its wake." + " " * (400 - len(base_narration) - 45)
                        narration = base_narration
                        is_fallback = True

                # Step 2: Apply mechanical effects (runs regardless of narration source)
                effects = MechanicalEffects()
                success_tier = SuccessTier.MODERATE
                margin = 5

                # Handle assist actions: apply +1 bonus to target
                if npc_action_type == 'assist' and target:
                    effects.conditions = [
                        Condition(
                            name="Assisted",
                            penalty=1,  # +1 bonus (positive penalty = buff)
                            duration=1,
                            description=f"Aided by {character_name}",
                            target=target
                        )
                    ]

                # Handle heal actions: Medicine skill check + healing effect
                elif npc_action_type == 'heal' and target:
                    # Look up NPC entity to get Medicine skill
                    npc_entity = None
                    npc_agent_id = action.get('agent_id')
                    if npc_agent_id and self.shared_state:
                        # Check NPC agents
                        for npc in getattr(self.shared_state, 'npc_agents', []):
                            if hasattr(npc, 'agent_id') and npc.agent_id == npc_agent_id:
                                npc_entity = npc
                                break

                    # Check if target is dead (wounds >= 6) or defeated (health <= 0)
                    target_entity = None
                    target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                    if target and target.startswith('tgt_') and target_id_mapper:
                        target_entity = target_id_mapper.resolve_target(target)
                    elif target and self.shared_state:
                        # Try direct agent_id lookup
                        for player in getattr(self.shared_state, 'player_agents', []):
                            if hasattr(player, 'agent_id') and player.agent_id == target:
                                target_entity = player
                                break
                        if not target_entity:
                            for npc in getattr(self.shared_state, 'npc_agents', []):
                                if hasattr(npc, 'agent_id') and npc.agent_id == target:
                                    target_entity = npc
                                    break

                    # Track roll data for JSONL logging
                    npc_heal_roll_data = None
                    npc_heal_amount = 0

                    target_wounds = getattr(target_entity, 'wounds', 0) if target_entity else 0
                    target_health = getattr(target_entity, 'health', 1) if target_entity else 1
                    target_stuns = getattr(target_entity, 'stuns', 0) if target_entity else 0
                    if target_wounds >= 6:
                        # Target is dead - cannot heal
                        narration += f"\n\n[{character_name} attempts to heal but the target is beyond saving — wounds too severe (wounds: {target_wounds}).]"
                        success_tier = SuccessTier.FAILURE
                        margin = -10
                    else:
                        # Medicine skill check: Intelligence(3) x Medicine + d20 vs DC 18
                        medicine_skill = 0
                        if npc_entity and hasattr(npc_entity, 'skills'):
                            medicine_skill = npc_entity.skills.get("Medicine", 0)

                        intelligence = 3  # Default NPC intelligence
                        unskilled_penalty = -5 if medicine_skill == 0 else 0
                        skill_value = max(medicine_skill, 1)
                        base_roll = intelligence * skill_value + unskilled_penalty
                        d20 = random.randint(1, 20)
                        total = base_roll + d20
                        dc = 18

                        # Capture roll data for JSONL logging
                        npc_heal_roll_data = {
                            "skill": "Medicine",
                            "attribute": "Intelligence",
                            "attribute_value": intelligence,
                            "skill_value": medicine_skill,
                            "d20": d20,
                            "total": total,
                            "dc": dc,
                            "margin": total - dc,
                            "success": total >= dc,
                        }

                        if total >= dc:
                            # Success: create healing effect
                            from .schemas.action_effects import HealingEffect
                            npc_heal_amount = max(1, total - dc + 5)  # Base 5 + margin
                            # A Beaten ally needs stun relief, not HP — clearing
                            # stuns is the only way out of the KO, so a medic
                            # prioritizes it when the target is Beaten.
                            heal_kind = "stun" if target_stuns >= 6 else "hp"
                            effects.healing = [
                                HealingEffect(
                                    target=target,
                                    heal_type=heal_kind,
                                    amount=npc_heal_amount,
                                    source=f"Medicine ({character_name})"
                                )
                            ]
                            success_tier = SuccessTier.MODERATE if (total - dc) < 5 else SuccessTier.GOOD
                            margin = total - dc
                            _heal_unit = "stun" if heal_kind == "stun" else "HP"
                            narration += f"\n\n[Medicine check: {base_roll} + {d20} (d20) = {total} vs DC {dc} — SUCCESS! Healed for {npc_heal_amount} {_heal_unit}.]"
                            logger.info(f"NPC {character_name} healed {target}: roll {total} vs DC {dc} (Medicine {medicine_skill})")
                        else:
                            # Failure: no healing applied
                            success_tier = SuccessTier.FAILURE
                            margin = total - dc
                            narration += f"\n\n[Medicine check: {base_roll} + {d20} (d20) = {total} vs DC {dc} — FAILED. Could not stabilize the patient.]"
                            logger.info(f"NPC {character_name} failed to heal {target}: roll {total} vs DC {dc} (Medicine {medicine_skill})")

                # Handle attack actions: route through enemy_combat.py YAGS formula
                elif npc_action_type == 'attack' and target:
                    # Look up NPC entity to get skills and weapons
                    npc_entity = None
                    npc_agent_id = action.get('agent_id')
                    if npc_agent_id and self.shared_state:
                        for npc in getattr(self.shared_state, 'npc_agents', []):
                            if hasattr(npc, 'agent_id') and npc.agent_id == npc_agent_id:
                                npc_entity = npc
                                break

                    if npc_entity:
                        # Route NPC attacks through enemy_combat.py's full YAGS combat path.
                        # This gives NPCs: proper attribute*skill formula, range penalties,
                        # defence tokens, death saves, defeat tracking, and combat_action JSONL logging.
                        from .enemy_combat import execute_npc_attack
                        from .tactical_resolution import ResolutionState

                        # Get or create resolution state for this round
                        resolution_state = getattr(self, '_current_resolution_state', None)
                        if not resolution_state:
                            resolution_state = ResolutionState()

                        player_agents = getattr(self.shared_state, 'player_agents', [])
                        mechanics_engine = self.shared_state.mechanics_engine if self.shared_state else None

                        combat_result = execute_npc_attack(
                            npc=npc_entity,
                            target_id=target,
                            weapon_name=None,  # Use first available weapon
                            shared_state=self.shared_state,
                            mechanics_engine=mechanics_engine,
                            resolution_state=resolution_state,
                            player_agents=player_agents
                        )

                        # Map combat result to NPC resolution format
                        hit = combat_result.get('hit', False)
                        damage_dealt = combat_result.get('damage_dealt', 0)
                        target_name = combat_result.get('target', 'unknown')

                        if hit and damage_dealt > 0:
                            success_tier = SuccessTier.MODERATE
                            margin = combat_result.get('attack_roll', 0) - 15
                            narration += f"\n\n{combat_result.get('narration', '')}"
                        elif hit:
                            success_tier = SuccessTier.MARGINAL
                            margin = 0
                            narration += f"\n\n{combat_result.get('narration', '')}"
                        else:
                            success_tier = SuccessTier.FAILURE
                            margin = -5
                            narration += f"\n\n{combat_result.get('narration', '')}"

                        # combat_action JSONL logging is handled inside _execute_attack()
                        logger.info(f"NPC {character_name} attack via YAGS pipeline: hit={hit}, damage_dealt={damage_dealt}")
                    else:
                        # NPC entity not found — cannot attack
                        narration += f"\n\n[{character_name} attempts to attack but entity data is unavailable.]"
                        success_tier = SuccessTier.FAILURE
                        margin = -10
                        logger.warning(f"NPC {character_name} attack failed: entity not found for {npc_agent_id}")

                # Step 3: Build resolution and process effects
                if outcome_first:
                    from .outcome_pipeline import ActionAdjudication
                    npc_resolution = ActionAdjudication(
                        success_tier=success_tier,
                        margin=margin,
                        effects=effects,
                        reasoning_short=f"Resolved {character_name}'s {npc_action_type} action mechanically.",
                    )
                    narration = ''
                else:
                    npc_resolution = ActionResolution(
                        narration=narration,
                        success_tier=success_tier,
                        margin=margin,
                        effects=effects
                    )

                # Process healing effects if any (applies HP changes to target)
                if effects.healing:
                    healing_messages = _process_structured_healing_effects(
                        healing_effects=effects.healing,
                        shared_state=self.shared_state,
                        current_round=self.shared_state.mechanics_engine.current_round if self.shared_state and self.shared_state.mechanics_engine else 0,
                        mechanics=self.shared_state.mechanics_engine if self.shared_state else None,
                        logger_instance=logger
                    )

                # Step 4: Log resolution
                if self.shared_state and self.shared_state.mechanics_engine:
                    mechanics = self.shared_state.mechanics_engine
                    if (hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger
                            and not self._outcome_first_enabled()):
                        current_round = mechanics.current_round

                        # Build context with roll data for JSONL
                        log_context = {
                            "action_type": npc_action_type,
                            "is_npc": True,
                            "dialogue_content": action.get('dialogue_content'),
                            "fallback": is_fallback,
                        }

                        # Add heal-specific roll data if available
                        if npc_action_type == 'heal':
                            log_context["heal_target"] = target
                            log_context["heal_amount"] = npc_heal_amount
                            if npc_heal_roll_data:
                                log_context["npc_roll"] = npc_heal_roll_data
                            elif target_wounds >= 6:
                                log_context["heal_rejected"] = "target_dead"

                        # Build effects dict with healing data
                        log_effects = {}
                        if effects.healing:
                            log_effects["healing"] = [
                                h.model_dump() for h in effects.healing
                            ]

                        mechanics.jsonl_logger.log_action_resolution(
                            round_num=current_round,
                            phase="adjudicate_npc",
                            agent_name=character_name,
                            action=intent,
                            resolution=npc_resolution,  # Pass object, not .model_dump()
                            economy_changes={},
                            clock_states={},
                            effects=log_effects,
                            context=log_context,
                        )

            self._last_structured_resolution = npc_resolution

            # Return lightweight resolution matching player format (with outcome dict)
            return {
                'resolution': npc_resolution,  # ActionResolution Pydantic model
                'narration': narration,
                'state_changes': {},  # Empty state changes for NPCs (no mechanics)
                'combat_data': {},  # No combat data for NPCs
                'inventory_changes': [],  # No inventory changes
                'outcome': {
                    'dm_response': narration,
                    'success': npc_resolution.success_tier != SuccessTier.FAILURE,
                    'consequences': [],
                    'narration': narration,  # Needed by session.py
                    'resolution': {
                        'success_tier': npc_resolution.success_tier.value,
                        'margin': npc_resolution.margin,
                        'success': npc_resolution.success_tier != SuccessTier.FAILURE
                    }
                }
            }

        resolution = None
        narration = ""

        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()

            # Extract mechanical details
            attribute = action.get('attribute', 'Perception')
            skill = action.get('skill')
            attribute_value = action.get('attribute_value', 3)
            skill_value = action.get('skill_value', 0)

            # Check for coordination bonus
            coordination_bonus = 0
            coordination_from = None
            if self.shared_state:
                bonus_info = self.shared_state.consume_coordination_bonus(player_id)
                if bonus_info:
                    coordination_bonus = bonus_info['bonus']
                    coordination_from = bonus_info['from']
                    print(f"💡 {action.get('character', 'Character')} receives +{coordination_bonus} coordination bonus from {coordination_from}!")

            # Calculate DC: the DM's round-batch assessment is the
            # authoritative proposal, floored by calculate_dc guardrails;
            # absent assessment falls back to the category table
            is_ritual_action = action_type == 'ritual' or action.get('is_ritual', False)
            is_inter_party = action.get('is_free_action', False)  # Free actions are inter-party
            proposed_dc = action.get('dm_assessed_difficulty')
            difficulty = mechanics.calculate_dc(
                intent=intent,
                action_type=action_type,
                is_ritual=is_ritual_action,
                is_extreme=action.get('is_extreme', False),
                is_multi_stage=action.get('is_multi_stage', False),
                is_inter_party=is_inter_party,
                proposed_dc=proposed_dc
            )

            # MECHANICS-FIRST: Consume offering BEFORE DM narration (if ritual with offering)
            offering_consumed = False
            consumed_item = None
            inventory_changes = []

            # Get character name for logging
            character_name = action.get('character_name', action.get('character', player_id))

            if action.get('has_offering', False) and is_ritual_action:
                character_state = self.shared_state.get_agent_by_id(player_id)
                if character_state:
                    offering_type = action.get('offering_type')  # Optional specific item
                    consumed_item = mechanics.consume_offering(character_state, offering_type)

                    if consumed_item:
                        offering_consumed = True
                        inventory_changes.append({
                            "item": consumed_item,
                            "delta": -1,
                            "reason": "Consumed as ritual offering"
                        })
                        logger.info(f"Offering consumed BEFORE narration: {consumed_item} from {character_name}")
                    else:
                        logger.warning(f"Player declared offering but none available for {character_name} - mechanics will apply +1 void penalty")

            # Pass consumption result to action context for DM narration
            action['offering_consumed'] = offering_consumed
            action['offering_item'] = consumed_item

            # Perform resolution (apply coordination bonus via modifiers)
            modifiers = {}
            if coordination_bonus > 0:
                modifiers['coordination'] = coordination_bonus

            # Include player's situational modifiers if present
            if action.get('situational_modifiers'):
                modifiers.update(action['situational_modifiers'])

            resolution = mechanics.resolve_action(
                intent=intent,
                attribute=attribute,
                skill=skill,
                attribute_value=attribute_value,
                skill_value=skill_value,
                difficulty=difficulty,
                agent_id=player_id,
                modifiers=modifiers if modifiers else None
            )

            # Contract-gear Soulcredit lock: a locked weapon does not fire, so
            # the attack FAILS the roll (not a masked success). Applied before
            # the mechanical text / narration prompt so both read the failure
            # and the acting agent gets a clean signal to change tactics.
            if action.get('action_type') in ('attack', 'combat', 'brawl'):
                action.setdefault('agent_id', player_id)
                _, _, _lock_weapon = _resolve_weapon_and_damage_type(action, self.shared_state)
                if _force_fail_locked_weapon(
                        resolution, _lock_weapon,
                        _get_wielder_soulcredit(action, self.shared_state)):
                    logger.info(f"Contract weapon locked for "
                                f"{action.get('character', player_id)}: "
                                f"action fails the roll (weapon did not fire)")

            # Format mechanical resolution (pass modifiers for display)
            mechanical_text = mechanics.format_resolution_for_narration(resolution, modifiers=modifiers if modifiers else None)

            # Build context from previous resolutions this round (for narrative consistency)
            enhanced_context = _build_enhanced_previous_context(previous_resolutions or [])
            if enhanced_context:
                action['previous_context'] = enhanced_context
            # Stash raw resolutions for session_context builder in _build_resolution_prompt
            action['_previous_resolutions'] = previous_resolutions or []

            # Generate narrative description using LLM
            if self.llm_config:
                llm_narration = await self._generate_llm_response(
                    player_id, action_type, description, resolution, action
                )
                narration = f"{mechanical_text}\n\n{llm_narration}"
            else:
                narration = f"{mechanical_text}\n\n{resolution.narrative}"

            # Clean up transient context data from action dict to prevent recursive
            # nesting when action is included in resolution_data/previous_resolutions.
            # These were only needed for the LLM call above.
            action.pop('_previous_resolutions', None)
            action.pop('previous_context', None)

            # Parse narration for clock triggers and state changes
            from .outcome_parser import (
                parse_state_changes,
                parse_combat_triplet,
                parse_mechanical_effect,
                generate_fallback_effect,
                generate_fallback_buff
            )

            # Get active clocks for dynamic clock progression
            active_clocks = mechanics.scene_clocks if mechanics else {}

            # CRITICAL: Resolve target IDs to entity names for effect application
            # In free targeting mode, actions have target="tgt_xxxx" but need entity names for structured output
            if action.get('target') and action['target'].startswith('tgt_'):
                target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                if target_id_mapper and target_id_mapper.enabled:
                    target_entity = target_id_mapper.resolve_target(action['target'])
                    if target_entity:
                        # Resolve target type and populate appropriate field
                        if target_id_mapper.is_player(action['target']):
                            # PC target - for PC-to-PC actions (healing, buffs, void cleansing)
                            if hasattr(target_entity, 'character_state') and hasattr(target_entity.character_state, 'name'):
                                action['target_character'] = target_entity.character_state.name
                                logger.debug(f"Resolved target ID {action['target']} → PC '{action['target_character']}'")
                        elif target_id_mapper.is_enemy(action['target']):
                            # Enemy target - for social actions, combat, debuffs
                            if hasattr(target_entity, 'name'):
                                action['target_enemy'] = target_entity.name
                                logger.debug(f"Resolved target ID {action['target']} → Enemy '{action['target_enemy']}'")
                        elif target_id_mapper.is_npc(action['target']):
                            # NPC target - for interactions with non-combatants
                            if hasattr(target_entity, 'name'):
                                action['target_npc'] = target_entity.name
                                logger.debug(f"Resolved target ID {action['target']} → NPC '{action['target_npc']}'")

            # Phase 2 Migration: Check if we have a structured resolution
            effects_dict = None  # Will hold purchase/crafting effects if present
            if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution is not None:
                from .outcome_parser import extract_from_structured_resolution

                # Build extraction context with available characters for fuzzy name matching
                extraction_context = {}
                if self.shared_state and hasattr(self.shared_state, 'registered_players'):
                    extraction_context['available_characters'] = [p['name'] for p in self.shared_state.registered_players]

                state_changes = extract_from_structured_resolution(self._last_structured_resolution, extraction_context)
                logger.debug(f"Using structured resolution: void={state_changes['void_change']}, clocks={len(state_changes.get('clock_triggers', []))}, soulcredit={state_changes['soulcredit_change']}")

                # Effect suppression: if action was skipped/preempted, zero out all effects
                if getattr(self._last_structured_resolution, 'action_skipped', False):
                    skip_reason = getattr(self._last_structured_resolution, 'skip_reason', 'preempted')
                    logger.info(f"Action skipped (reason: {skip_reason}) — suppressing all mechanical effects")
                    state_changes['void_change'] = 0
                    state_changes['void_reasons'] = []
                    state_changes['soulcredit_change'] = 0
                    state_changes['soulcredit_reasons'] = []
                    state_changes['clock_triggers'] = []
                    state_changes['conditions'] = []
                    state_changes['damage_effects'] = []

                # Extract effects (purchase/crafting) from structured output
                if hasattr(self._last_structured_resolution, 'effects') and self._last_structured_resolution.effects:
                    effects_data = self._last_structured_resolution.effects
                    # Damage is now List[DamageEffect] - convert to list of dicts for legacy format
                    damage_list = None
                    if effects_data.damage:
                        damage_list = [dmg.model_dump() for dmg in effects_data.damage]

                    effects_dict = {
                        'damage': damage_list,  # Now a list of damage effect dicts (or None)
                        'status_effects': effects_data.status_effects if hasattr(effects_data, 'status_effects') else [],
                        'inventory_changes': [],
                        'purchase': effects_data.purchase.model_dump() if effects_data.purchase else None,
                        'crafting': effects_data.crafting.model_dump() if effects_data.crafting else None,
                        'attunement': effects_data.attunement.model_dump() if effects_data.attunement else None,
                        'item_discovery': effects_data.item_discovery.model_dump() if effects_data.item_discovery else None
                    }
                    logger.debug(f"Extracted effects from structured output: damage_count={len(damage_list) if damage_list else 0}, purchase={effects_dict['purchase'] is not None}, crafting={effects_dict['crafting'] is not None}, attunement={effects_dict['attunement'] is not None}, item_discovery={effects_dict['item_discovery'] is not None}")

                # Skill mismatch detection
                declared_skill = action.get('skill')
                dm_resolution_skill = getattr(self._last_structured_resolution, 'skill', None)

                if declared_skill and dm_resolution_skill and declared_skill.lower() != dm_resolution_skill.lower():
                    skill_override = {
                        'declared': declared_skill,
                        'used': dm_resolution_skill,
                        'reason': f"DM override: Action intent required {dm_resolution_skill}, player declared {declared_skill}"
                    }

                    # Add to structured resolution for JSONL logging
                    if hasattr(self._last_structured_resolution, 'skill_override'):
                        self._last_structured_resolution.skill_override = skill_override

                    # Print to stdout for user visibility and ML training
                    character_name = action.get('character_name', 'Character')
                    print(f"\n⚠️  Skill Override: {character_name} declared {declared_skill}, DM used {dm_resolution_skill}")
                    print(f"    Reason: Action intent required {dm_resolution_skill}")
                    logger.info(f"Skill mismatch detected: {declared_skill} → {dm_resolution_skill} for {character_name}")

                # Validate void changes were populated when narration contains void markers
                narration_text = llm_narration if self.llm_config else resolution.narrative
                has_void_in_narrative = '⚫ Void' in narration_text or 'Void (' in narration_text

                if state_changes['void_change'] == 0 and has_void_in_narrative:
                    logger.warning(
                        f"STRUCTURED OUTPUT FAILURE: LLM put void changes in narrative text instead of "
                        f"populating effects.void_changes field for {action.get('agent')} action. "
                        f"Void changes will NOT be applied. This indicates prompt guidance is being ignored."
                    )
                    # TODO: Log to JSONL as structured_output_warning event for ML analysis
            else:
                # Legacy text parsing
                state_changes = parse_state_changes(llm_narration if self.llm_config else resolution.narrative, action, resolution.__dict__, active_clocks)

            # Parse combat triplet (for backwards compatibility)
            combat_data = parse_combat_triplet(llm_narration if self.llm_config else resolution.narrative)

            # Parse mechanical effects if action has target
            effect = None
            has_structured_output = hasattr(self, '_last_structured_resolution') and self._last_structured_resolution is not None
            if action.get('target'):
                # Try to parse explicit mechanical effect block
                effect = parse_mechanical_effect(llm_narration if self.llm_config else resolution.narrative)

                # If no effect found, use legacy combat triplet
                if not effect and combat_data and combat_data.get('post_soak_damage', 0) > 0:
                    effect = {
                        'type': 'damage',
                        'target': action.get('target'),
                        'final': combat_data['post_soak_damage'],
                        'source': 'combat_triplet'
                    }

                # When structured output is active, damage is handled exclusively by
                # _process_structured_damage_effects() in _generate_action_resolution_structured().
                # Block legacy damage effects to prevent double-damage application.
                # Non-damage effects (debuff, status, movement, reveal) still flow through
                # the legacy path since they aren't handled by the new pipeline yet.
                if has_structured_output and effect and effect.get('type') == 'damage':
                    logger.debug(
                        f"Skipping legacy damage effect (source={effect.get('source', '?')}): "
                        f"structured output pipeline handles damage exclusively"
                    )
                    effect = None

            # Apply effect to enemy if we have one
            if effect and self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
                enemy_combat = self.shared_state.enemy_combat
                if enemy_combat:
                    from .enemy_spawner import get_active_enemies
                    active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                    # Resolve target (combat ID or fuzzy name match)
                    target_identifier = effect.get('target', action.get('target'))
                    target_entity = None
                    target_name = None  # Initialize for legacy path
                    is_friendly_fire = False

                    # Check if using target ID system (free targeting mode)
                    if target_identifier and target_identifier.startswith('tgt_'):
                        target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                        if target_id_mapper and target_id_mapper.enabled:
                            target_entity = target_id_mapper.resolve_target(target_identifier)

                            # Check if target is a player (friendly fire!)
                            if target_entity and target_id_mapper.is_player(target_identifier):
                                is_friendly_fire = True
                                attacker_name = action.get('agent_id', 'Unknown')
                                pc_name = getattr(target_entity.character_state, 'name', 'Unknown') if hasattr(target_entity, 'character_state') else 'Unknown'
                                logger.warning(f"🔥 FRIENDLY FIRE: {attacker_name} targeting PC {pc_name} (ID: {target_identifier})")
                    else:
                        # Legacy fuzzy name matching for enemies AND NPCs (handles escalated agents)
                        target_name = target_identifier

                        # First try enemies
                        for enemy in active_enemies:
                            if target_name and (target_name.lower() in enemy.name.lower() or
                                                enemy.name.lower() in target_name.lower() or
                                                target_name.lower() in enemy.agent_id.lower()):
                                target_entity = enemy
                                break

                        # If not found in enemies, try NPCs (for recently escalated agents or de-escalated enemies)
                        if not target_entity and self.shared_state and hasattr(self.shared_state, 'npc_agents'):
                            for npc in self.shared_state.npc_agents:
                                if npc.is_active and target_name and (target_name.lower() in npc.name.lower() or
                                                                       npc.name.lower() in target_name.lower() or
                                                                       target_name.lower() in npc.agent_id.lower()):
                                    target_entity = npc
                                    break

                    if target_entity:
                        # Extract target name once for all effect types
                        if is_friendly_fire and hasattr(target_entity, 'character_state'):
                            # Target is a PC
                            target_name = target_entity.character_state.name
                        else:
                            # Target is an enemy
                            target_name = target_entity.name

                        effect_type = effect.get('type', 'unknown')

                        if effect_type == 'damage':
                            # Apply damage (works for both enemies and PCs)
                            damage_dealt = effect.get('final', 0)

                            # Get health/wounds from correct location (PC vs enemy)
                            if is_friendly_fire and hasattr(target_entity, 'character_state'):
                                # Target is a PC - health/wounds are on the agent, not character_state
                                old_health = target_entity.health  # Health is on the agent
                                wounds_dealt = damage_dealt // 5  # YAGS: every 5 damage = 1 wound
                                target_entity.wounds += wounds_dealt  # Wounds on the agent
                                target_entity.health -= damage_dealt  # Health on the agent
                                logger.warning(f"🔥 FRIENDLY FIRE DAMAGE: {damage_dealt} to {target_name} ({old_health} → {target_entity.health} HP, +{wounds_dealt} wounds)")
                            else:
                                # Target is an enemy
                                old_health = target_entity.health
                                wounds_dealt = damage_dealt // 5  # YAGS: every 5 damage = 1 wound
                                target_entity.wounds += wounds_dealt
                                target_entity.health -= damage_dealt
                                logger.info(f"Player dealt {damage_dealt} damage to {target_name} ({old_health} → {target_entity.health} HP, +{wounds_dealt} wounds)")

                            # Track damage for round summary
                            if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                                self.shared_state.session.track_player_damage_dealt(damage_dealt)

                            # Log player combat action for ML training
                            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                # Build attack roll data from resolution
                                attack_roll_data = {
                                    "attr": getattr(resolution, 'attribute', "Unknown") if resolution else "Unknown",
                                    "attr_val": getattr(resolution, 'attribute_value', 0) if resolution else 0,
                                    "skill": getattr(resolution, 'skill', None) if resolution else None,
                                    "skill_val": getattr(resolution, 'skill_value', 0) if resolution else 0,
                                    "weapon_bonus": 0,  # Not tracked for player attacks currently
                                    "d20": getattr(resolution, 'roll', 0) if resolution else 0,
                                    "total": getattr(resolution, 'total', 0) if resolution else 0,
                                    "dc": getattr(resolution, 'difficulty', 0) if resolution else 0,
                                    "hit": getattr(resolution, 'success', True) if resolution else True,
                                    "margin": resolution.margin if resolution and hasattr(resolution, 'margin') else 0
                                }

                                # Build damage roll data from combat_data or effect
                                damage_roll_data = {
                                    "base_damage": combat_data.get('damage', damage_dealt) if combat_data else damage_dealt,
                                    "soak": combat_data.get('soak', 0) if combat_data else 0,
                                    "mechanical_soak": getattr(target_entity, 'soak', None),
                                    "dealt": damage_dealt
                                }

                                # Get defender state after damage (works for both PCs and enemies)
                                # Health/wounds are stored directly on agent objects, not on CharacterState
                                defender_state = {
                                    "health": target_entity.health,
                                    "max_health": target_entity.max_health,
                                    "wounds": target_entity.wounds,
                                    "alive": target_entity.health > 0,
                                    "status": "active" if target_entity.health > 0 else "defeated"
                                }

                                # Resolve weapon from equipped_weapons via shared helper
                                weapon_name, _, _ = _resolve_weapon_and_damage_type(action, self.shared_state)

                                # Fallback to intent-based guessing if no equipped weapon found
                                if weapon_name == "Unknown Weapon" and action.get('intent'):
                                    intent_lower = action['intent'].lower()
                                    if 'rifle' in intent_lower or 'gun' in intent_lower:
                                        weapon_name = "Firearm"
                                    elif 'pistol' in intent_lower:
                                        weapon_name = "Pistol"
                                    elif 'melee' in intent_lower or 'sword' in intent_lower or 'blade' in intent_lower:
                                        weapon_name = "Melee Weapon"
                                    elif 'punch' in intent_lower or 'kick' in intent_lower or 'brawl' in intent_lower:
                                        weapon_name = "Unarmed"
                                    elif action.get('skill'):
                                        weapon_name = action['skill']

                                # Get defender ID (vendors use vendor_id instead of agent_id)
                                defender_entity_id = getattr(target_entity, 'agent_id', None) or getattr(target_entity, 'vendor_id', 'unknown')
                                mechanics.jsonl_logger.log_combat_action(
                                    round_num=mechanics.current_round,
                                    attacker_id=action.get('agent_id', 'unknown_player'),
                                    attacker_name=action.get('character', 'Unknown Player'),
                                    defender_id=defender_entity_id,
                                    defender_name=target_name,  # Already extracted above
                                    weapon=weapon_name,
                                    declared_weapon=action.get('weapon'),
                                    attack_roll=attack_roll_data,
                                    damage_roll=damage_roll_data,
                                    wounds_dealt=wounds_dealt,
                                    defender_state_after=defender_state
                                )

                            # Add effect notification
                            source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                            narration += f"\n\n⚔️  **{target_name} takes {damage_dealt} damage!** {source_label}"

                            # Check if target died (only enemies have death saves)
                            if target_entity.health <= 0:
                                if hasattr(target_entity, 'check_death_save'):
                                    alive, status = target_entity.check_death_save()
                                    if not alive:
                                        logger.info(f"{target_name} KILLED by player attack!")
                                        narration += f"\n💀 **{target_name} is KILLED!**"
                                        # Mark enemy as defeated (no longer targetable)
                                        if hasattr(target_entity, 'is_active'):
                                            target_entity.is_active = False
                                    elif status == "unconscious":
                                        logger.info(f"{target_name} knocked unconscious!")
                                        narration += f"\n😵 **{target_name} is knocked unconscious!**"
                                        # Mark enemy as defeated (no longer targetable)
                                        if hasattr(target_entity, 'is_active'):
                                            target_entity.is_active = False
                                    else:
                                        logger.info(f"{target_name} critically wounded but conscious!")
                                        narration += f"\n⚠️  **{target_name} is critically wounded!**"
                                else:
                                    logger.info(f"{target_name} defeated!")
                                    narration += f"\n💀 **{target_name} is defeated!**"
                                    # Mark enemy as defeated (no longer targetable)
                                    if hasattr(target_entity, 'is_active'):
                                        target_entity.is_active = False

                        elif effect_type == 'debuff':
                            # Apply debuff (only enemies support this)
                            if hasattr(target_entity, 'add_debuff'):
                                penalty = effect.get('penalty', -2)
                                duration = effect.get('duration', 3)
                                effect_desc = effect.get('effect', f"{penalty} to rolls")
                                source = effect.get('source', 'player')

                                target_entity.add_debuff(effect_desc, penalty, duration, source)

                                source_label = "(fallback)" if source == 'fallback' else ""
                                narration += f"\n\n🔻 **{target_name} debuffed: {effect_desc}** (lasts {duration} rounds) {source_label}"

                        elif effect_type == 'status':
                            # Apply status effect (only enemies support this)
                            if hasattr(target_entity, 'add_status_effect'):
                                status_effect = effect.get('effect', 'affected')
                                duration = effect.get('duration', 1)

                                target_entity.add_status_effect(status_effect, duration)

                                source_label = "(fallback)" if effect.get('source') == 'fallback' else ""
                                narration += f"\n\n💫 **{target_name} status: {status_effect}** {source_label}"

                        elif effect_type == 'movement':
                            # Apply forced movement
                            movement_desc = effect.get('effect', 'forced to move')
                            new_position = effect.get('new_position')

                            if new_position and hasattr(target_entity, 'position'):
                                from .enemy_agent import Position
                                try:
                                    target_entity.position = Position.from_string(new_position)
                                    narration += f"\n\n🚶 **{target_name} forced to {new_position}!**"
                                except (AttributeError, TypeError, KeyError):
                                    narration += f"\n\n🚶 **{target_name} disrupted: {movement_desc}!**"
                            else:
                                narration += f"\n\n🚶 **{target_name} disrupted: {movement_desc}!**"

                        elif effect_type == 'reveal':
                            # Add revealed weakness (only enemies support this)
                            if hasattr(target_entity, 'add_revealed_weakness'):
                                weakness_desc = effect.get('effect', 'weakness revealed')
                                bonus = effect.get('bonus', 2)

                                target_entity.add_revealed_weakness(weakness_desc, bonus)

                                narration += f"\n\n🔍 **{target_name} weakness revealed: {weakness_desc}** (+{bonus} for allies)"

                        else:
                            logger.warning(f"Unknown effect type: {effect_type}")

                    else:
                        # Only warn if a real target was specified (not None/null)
                        if target_identifier and target_identifier not in (None, "None", "null", ""):
                            logger.warning(f"Could not find target '{target_identifier}' to apply effect")

            # Parse and apply ally buffs if action targets ally
            buff = None
            if action.get('target_ally'):
                # Try to parse explicit buff effect block (similar to enemy effects)
                # For now, we'll use fallback generation since DM doesn't explicitly write buff blocks yet

                # Generate fallback buff if successful action
                if resolution and _resolution_success(resolution):
                    buff = generate_fallback_buff(action, resolution.__dict__ if hasattr(resolution, '__dict__') else resolution)
                    if buff:
                        logger.debug(f"Generated fallback buff: {buff.get('type')} for {buff.get('target')}")

            # Apply buff to ally if we have one
            if buff and self.shared_state:
                # Find target ally player agent (fuzzy match by character name)
                target_ally_name = buff.get('target', action.get('target_ally'))
                target_ally_agent = None

                # Get all player agents from shared_state
                player_agents = self.shared_state.player_agents

                for agent in player_agents:
                    if hasattr(agent, 'character_state') and agent.character_state:
                        agent_name = agent.character_state.name
                        # Fuzzy match: check if names contain each other
                        if target_ally_name.lower() in agent_name.lower() or agent_name.lower() in target_ally_name.lower():
                            target_ally_agent = agent
                            break

                if target_ally_agent:
                    buff_type = buff.get('type', 'unknown')

                    if buff_type == 'heal':
                        # Apply healing
                        healing_amount = buff.get('amount', 0)
                        old_health = target_ally_agent.health
                        target_ally_agent.health = min(target_ally_agent.max_health, target_ally_agent.health + healing_amount)
                        actual_healing = target_ally_agent.health - old_health

                        logger.info(f"Player healed {target_ally_agent.character_state.name} for {actual_healing} HP ({old_health} → {target_ally_agent.health})")

                        # Add buff notification
                        source_label = "(fallback)" if buff.get('source') == 'fallback' else ""
                        narration += f"\n\n💚 **{target_ally_agent.character_state.name} healed for {actual_healing} HP!** {source_label}"

                    elif buff_type == 'buff':
                        # Apply positive buff
                        bonus = buff.get('bonus', 1)
                        duration = buff.get('duration', 2)
                        effect_desc = buff.get('effect', f"+{bonus} to rolls")
                        source = action.get('character', 'ally')

                        target_ally_agent.add_buff(effect_desc, bonus, duration, source)

                        source_label = "(fallback)" if buff.get('source') == 'fallback' else ""
                        narration += f"\n\n🔺 **{target_ally_agent.character_state.name} buffed: {effect_desc}** (lasts {duration} rounds) {source_label}"

                    else:
                        logger.warning(f"Unknown buff type: {buff_type}")

                else:
                    logger.warning(f"Could not find ally '{target_ally_name}' to apply buff")

            # Parse social de-escalation markers ([ENEMY_SURRENDER:], [ENEMY_FLEE:])
            import re
            surrender_pattern = r'\[ENEMY_SURRENDER:\s*([^\]]+)\]'
            flee_pattern = r'\[ENEMY_FLEE:\s*([^\]]+)\]'

            surrender_matches = re.findall(surrender_pattern, narration)
            flee_matches = re.findall(flee_pattern, narration)

            if surrender_matches or flee_matches:
                if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
                    enemy_combat = self.shared_state.enemy_combat
                    if enemy_combat:
                        from .enemy_spawner import get_active_enemies

                        # Process surrenders
                        for enemy_name_raw in surrender_matches:
                            enemy_name = enemy_name_raw.strip()
                            active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                            # Find matching enemy (fuzzy match)
                            targeted_enemy = None
                            for enemy in active_enemies:
                                if enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in enemy_name.lower():
                                    targeted_enemy = enemy
                                    break

                            if targeted_enemy:
                                # Mark enemy as surrendered (prisoner)
                                targeted_enemy.is_active = False
                                targeted_enemy.status_effects.append("prisoner")
                                logger.info(f"Social action: {targeted_enemy.name} surrendered (prisoner)")

                                # Track prisoner in session
                                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                                    session = self.shared_state.session
                                    if not hasattr(session, 'prisoners'):
                                        session.prisoners = []
                                    session.prisoners.append({
                                        'name': targeted_enemy.name,
                                        'round': mechanics.current_round if mechanics else 0,
                                        'method': 'intimidation/persuasion'
                                    })

                                # Log social de-escalation event
                                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                    # Detect action type from action intent/description
                                    action_type = "intimidation"  # Default
                                    intent_lower = (action.get('intent', '') + action.get('description', '')).lower()
                                    if 'persuade' in intent_lower or 'convince' in intent_lower or 'negotiate' in intent_lower:
                                        action_type = "persuasion"

                                    skill = action.get('skill', 'Intimidation' if action_type == 'intimidation' else 'Persuasion')

                                    mechanics.jsonl_logger.log_social_deescalation(
                                        round_num=mechanics.current_round,
                                        player_id=player_id,
                                        player_name=action.get('character', 'Unknown'),
                                        enemy_id=targeted_enemy.agent_id,
                                        enemy_name=targeted_enemy.name,
                                        action_type=action_type,
                                        skill=skill,
                                        roll_total=resolution.total if resolution else 0,
                                        dc=resolution.difficulty if resolution else 20,
                                        success=_resolution_success(resolution) if resolution else True,
                                        margin=resolution.margin if resolution else 10,
                                        outcome="surrender",
                                        narration=narration[:500]  # Truncate to 500 chars
                                    )
                            else:
                                logger.warning(f"Could not find enemy '{enemy_name}' to mark as surrendered")

                        # Process fleeing
                        for enemy_name_raw in flee_matches:
                            enemy_name = enemy_name_raw.strip()
                            active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                            # Find matching enemy (fuzzy match)
                            targeted_enemy = None
                            for enemy in active_enemies:
                                if enemy_name.lower() in enemy.name.lower() or enemy.name.lower() in enemy_name.lower():
                                    targeted_enemy = enemy
                                    break

                            if targeted_enemy:
                                # Trigger morale flee (uses existing flee logic)
                                targeted_enemy.is_active = False
                                logger.info(f"Social action: {targeted_enemy.name} fled (intimidated)")

                                # Advance escape clock if it exists
                                if mechanics and mechanics.scene_clocks:
                                    for clock_name in mechanics.scene_clocks:
                                        if 'escape' in clock_name.lower() or 'retreat' in clock_name.lower():
                                            mechanics.queue_clock_update(clock_name, 2, f"{targeted_enemy.name} fled from intimidation")
                                            break

                                # Log social de-escalation event
                                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                    # Detect action type from action intent/description
                                    action_type = "intimidation"  # Default for flee is intimidation
                                    intent_lower = (action.get('intent', '') + action.get('description', '')).lower()
                                    if 'persuade' in intent_lower or 'convince' in intent_lower or 'negotiate' in intent_lower:
                                        action_type = "persuasion"

                                    skill = action.get('skill', 'Intimidation' if action_type == 'intimidation' else 'Persuasion')

                                    mechanics.jsonl_logger.log_social_deescalation(
                                        round_num=mechanics.current_round,
                                        player_id=player_id,
                                        player_name=action.get('character', 'Unknown'),
                                        enemy_id=targeted_enemy.agent_id,
                                        enemy_name=targeted_enemy.name,
                                        action_type=action_type,
                                        skill=skill,
                                        roll_total=resolution.total if resolution else 0,
                                        dc=resolution.difficulty if resolution else 20,
                                        success=_resolution_success(resolution) if resolution else True,
                                        margin=resolution.margin if resolution else 10,
                                        outcome="flee",
                                        narration=narration[:500]  # Truncate to 500 chars
                                    )
                            else:
                                logger.warning(f"Could not find enemy '{enemy_name}' to mark as fled")

            # Queue clock advancements (will be applied batch during synthesis to prevent cascades)
            for clock_name, ticks, reason, source in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    mechanics.queue_clock_update(clock_name, ticks, reason)
                    logger.debug(f"Queued: {clock_name} {ticks:+d} ({reason}) [source: {source}]")

            # Log LLM compliance issues for training analysis
            if state_changes.get('llm_compliance_issue'):
                compliance_issue = state_changes['llm_compliance_issue']
                logger.warning(f"⚠️  LLM COMPLIANCE LOGGED: {compliance_issue}")

                # Log to JSONL for training analysis
                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        'llm_compliance_issue',
                        {
                            'player_id': player_id,
                            'action_intent': intent,
                            'issue': compliance_issue,
                            'narration': llm_narration if self.llm_config else resolution.narrative
                        },
                        self.current_round
                    )

            # Apply void changes (both gains and reductions)
            # Enforce mode: the post-resolution magistrate is the sole ledger
            # writer, so skip the narration call's void application here.
            if state_changes['void_change'] != 0 and not getattr(mechanics, 'suppress_narration_economy', False):
                # Track void change for round summary
                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_void_change(state_changes['void_change'])

                # Check if void change targets a different character (collaborative cleansing)
                target_identifier = state_changes.get('void_target_character')
                should_apply_void_change = True  # Flag to control whether to apply the void change
                void_state = None
                target_name = None

                if target_identifier:
                    # Resolve target - could be target ID (tgt_xxxx) or character name
                    # NOTE: Relies on Pydantic schema validation to reject environmental keywords
                    # Schema validator prevents: "Environmental Void", "environment", "area", etc.
                    # Unresolvable names (environmental or typos) naturally skip via name resolution failure
                    target_player_id = None
                    target_character_name = None

                    if target_identifier.startswith('tgt_'):
                        # It's a target ID - resolve it
                        logger.debug(f"Resolving target ID '{target_identifier}' for void change")
                        target_id_mapper = self.shared_state.get_target_id_mapper()
                        target_entity = target_id_mapper.resolve_target(target_identifier)

                        if target_entity and hasattr(target_entity, 'agent_id'):
                            target_player_id = target_entity.agent_id
                            target_character_name = getattr(target_entity, 'character_state', None)
                            if target_character_name:
                                target_character_name = target_character_name.name
                            logger.debug(f"Resolved target ID {target_identifier} → '{target_character_name}' (player_id: {target_player_id})")
                    else:
                        # It's a character name - find by name (partial match)
                        target_character_name = target_identifier
                        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
                            for player in self.shared_state.player_agents:
                                if hasattr(player, 'character_state'):
                                    # Try exact match first, then partial match
                                    char_name = player.character_state.name
                                    if char_name == target_character_name or target_character_name in char_name:
                                        target_player_id = player.agent_id
                                        target_character_name = char_name  # Use full name
                                        logger.debug(f"Matched character name '{target_identifier}' → '{char_name}' (player_id: {target_player_id})")
                                        break

                    if target_player_id:
                        void_state = mechanics.get_void_state(target_player_id)
                        target_name = target_character_name
                        logger.debug(f"Void change targeting '{target_character_name}' (player_id: {target_player_id})")
                    else:
                        # Couldn't find target - skip instead of falling back to actor
                        # This handles environmental targets, typos, and non-existent characters
                        logger.warning(f"Could not resolve target '{target_identifier}' for void change, skipping application")
                        should_apply_void_change = False
                else:
                    # Default: apply to acting character (self-inflicted void)
                    void_state = mechanics.get_void_state(player_id)
                    target_name = action.get('character', player_id)

                # Only apply void change if we have a valid target
                if should_apply_void_change and void_state:
                    old_void = void_state.score

                    if state_changes['void_change'] > 0:
                        # Void gain (corruption increasing)
                        action_id = f"{player_id}_{intent}_{resolution.total}"
                        void_state.add_void(
                            state_changes['void_change'],
                            ", ".join(state_changes['void_reasons']),
                            action_id=action_id
                        )
                        # Show void increase if it actually changed
                        if void_state.score != old_void:
                            narration += f"\n\n⚫ Void ({target_name}): {old_void} → {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"
                    else:
                        # Void reduction (recovery moves)
                        void_state.reduce_void(
                            abs(state_changes['void_change']),
                            ", ".join(state_changes['void_reasons'])
                        )
                        # Show void decrease if it actually changed
                        if void_state.score != old_void:
                            narration += f"\n\n⚫ Void ({target_name}): {old_void} ↓ {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"

                    # Check for Eye of Breach appearance on high void
                    eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                    if eye_of_breach_event:
                        narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            # Always show soulcredit line (even if +0) for consistency, UNLESS DM already included one
            sc_state = mechanics.get_soulcredit_state(player_id)
            old_sc = sc_state.score
            sc_change = state_changes.get('soulcredit_change', 0)
            reasons_text = ', '.join(state_changes.get('soulcredit_reasons', [])) if state_changes.get('soulcredit_reasons') else 'no change'
            sc_source = state_changes.get('soulcredit_source', '')

            # Enforce mode: magistrate is sole ledger writer; skip narration SC.
            if sc_change != 0 and not getattr(mechanics, 'suppress_narration_economy', False):
                current_round = mechanics.current_round if mechanics else None
                sc_state.adjust(sc_change, reasons_text, round_num=current_round)

            # SC is applied mechanically above - no need to inject into narration
            # Players see their soulcredit via game UI, not narrative text

            # Apply conditions (with targeting support - apply to target, not actor)
            from .mechanics import Condition
            for condition_data in state_changes.get('conditions', []):
                condition = Condition(
                    name=condition_data['type'],
                    type=condition_data['type'],
                    penalty=condition_data['penalty'],
                    description=condition_data['description'],
                    duration=condition_data.get('duration', 3),
                    affects=[],  # Phase 3: populate from LLM output
                    protection_amount=condition_data.get('protection_amount')
                )

                # Determine who receives the condition
                # Priority: condition.target > action.target > actor (self)
                target_id = condition_data.get('target')  # Per-condition target (NEW - supports multi-target)
                if not target_id:
                    target_id = action.get('target')  # Fallback to action-level target

                condition_target_id = player_id  # Default: apply to actor
                condition_target_name = action.get('character', player_id)
                should_apply_condition = True  # Flag to control whether to apply

                # Handle different targeting scenarios
                if target_id == 'None' or target_id is None or not target_id:
                    # Special case: target="None" (string), None (null), or missing/empty
                    # These all mean: no specific target
                    # Apply condition to actor (self-buff OR self-debuff from failure/backlash)
                    if condition.penalty < 0:
                        logger.debug(f"Applying self-debuff '{condition.name}' (penalty={condition.penalty}) to actor (backlash/failure consequence)")
                        condition_target_id = player_id
                        condition_target_name = action.get('character', player_id)
                    else:
                        # Positive penalty = buff, apply to actor (self-buff)
                        logger.debug(f"Applying self-buff '{condition.name}' (penalty={condition.penalty}) to actor (no target specified)")
                        condition_target_id = player_id
                        condition_target_name = action.get('character', player_id)

                else:
                    # Action has an explicit target - apply condition to that target
                    logger.debug(f"Condition '{condition.name}' has target: {target_id}")

                    # Resolve target ID to agent_id
                    if target_id.startswith('tgt_'):
                        # It's a target ID - resolve it
                        target_id_mapper = self.shared_state.get_target_id_mapper()
                        target_entity = target_id_mapper.resolve_target(target_id)

                        if target_entity and hasattr(target_entity, 'agent_id'):
                            condition_target_id = target_entity.agent_id
                            if hasattr(target_entity, 'character_state'):
                                condition_target_name = target_entity.character_state.name
                            elif hasattr(target_entity, 'name'):
                                condition_target_name = target_entity.name
                            logger.debug(f"Resolved condition target {target_id} → '{condition_target_name}' (agent_id: {condition_target_id})")
                        else:
                            # Environmental objects (terminals, doors, etc.) have tgt_ IDs but aren't tracked entities
                            # This is expected behavior - conditions don't apply to non-entities
                            logger.debug(f"Target ID '{target_id}' not a tracked entity (likely env object), skipping condition")
                            should_apply_condition = False
                    else:
                        # It's a character name - try to find by name
                        condition_target_name = target_id
                        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
                            for player in self.shared_state.player_agents:
                                if hasattr(player, 'character_state'):
                                    char_name = player.character_state.name
                                    if char_name == target_id or target_id in char_name:
                                        condition_target_id = player.agent_id
                                        condition_target_name = char_name
                                        logger.debug(f"Matched condition target '{target_id}' → '{char_name}' (agent_id: {condition_target_id})")
                                        break

                # Apply condition only if flag is True
                if should_apply_condition:
                    # Check if condition already exists before applying
                    already_exists = False
                    if condition_target_id in mechanics.conditions:
                        for existing in mechanics.conditions[condition_target_id]:
                            if existing.name == condition.name:
                                already_exists = True
                                break

                    # Only add condition if new (no narration injection - visible via structured output)
                    if not already_exists:
                        mechanics.add_condition(condition_target_id, condition)

            # Apply position changes (for tactical movement)
            if state_changes.get('position_change'):
                # Get player agent and update position
                player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                if player_agents:
                    player_agent = player_agents[0]
                    old_position = str(getattr(player_agent, 'position', 'Near-PC'))

                    # Parse and apply new position
                    from .enemy_agent import Position
                    try:
                        new_position_str = state_changes['position_change']
                        new_position = Position.from_string(new_position_str)
                        player_agent.position = new_position
                        logger.debug(f"Updated {player_id} position: {old_position} → {new_position}")
                        # Position change is already in narration from DM, no need to add here
                    except Exception as e:
                        logger.error(f"Failed to update player position: {e}")

        # Extract aware_agents from structured resolution (for stealth/secrets visibility control)
        aware_agents = []
        action_skipped = False
        skip_reason = None
        if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution:
            aware_agents = getattr(self._last_structured_resolution, 'aware_agents', []) or []
            action_skipped = getattr(self._last_structured_resolution, 'action_skipped', False)
            skip_reason = getattr(self._last_structured_resolution, 'skip_reason', None)

        # If action was skipped, suppress effects dict too (safety net for session.py processing)
        if action_skipped and effects_dict:
            logger.info(f"Suppressing effects dict for skipped action (reason: {skip_reason})")
            effects_dict = None

        resolution_payload = (
            self._last_structured_resolution
            if self._outcome_first_enabled() and self._last_structured_resolution is not None
            else resolution
        )
        return {
            'resolution': resolution_payload,
            'narration': narration,
            'state_changes': state_changes,  # Include state_changes for logging
            'combat_data': combat_data,  # Include combat triplet if present
            'inventory_changes': inventory_changes,  # Include offering consumption tracking
            'effects': effects_dict,  # Include purchase/crafting effects from structured output
            'aware_agents': aware_agents,  # Visibility control: who knows about this action
            'action_skipped': action_skipped,  # DM flagged action as preempted
            'skip_reason': skip_reason,  # Why action was preempted
            'outcome': {
                'dm_response': narration,
                'success': getattr(resolution, 'success', True) if resolution else True,
                'consequences': [],
                'resolution': {
                    'intent': getattr(resolution, 'intent', None),
                    'attribute': getattr(resolution, 'attribute', None),
                    'skill': getattr(resolution, 'skill', None),
                    'total': getattr(resolution, 'total', None),
                    'difficulty': getattr(resolution, 'difficulty', None),
                    'margin': resolution.margin if hasattr(resolution, 'margin') else 0,
                    'outcome_tier': resolution.outcome_tier.value if hasattr(resolution, 'outcome_tier') and hasattr(resolution.outcome_tier, 'value') else str(getattr(resolution, 'outcome_tier', 'unknown')),
                    'success': getattr(resolution, 'success', True)
                } if resolution else {}
            }
        }

    async def _handle_ai_dm_response(self, player_id: str, action: Dict[str, Any]):
        """Handle action with AI DM logic using mechanical resolution."""
        action_type = action.get('action_type', 'unknown')
        description = action.get('description', '')
        intent = action.get('intent', description)

        # Get mechanics engine
        resolution = None
        narration = ""

        if self.shared_state:
            mechanics = self.shared_state.get_mechanics_engine()

            # Extract mechanical details from action
            attribute = action.get('attribute', 'Perception')
            skill = action.get('skill')
            attribute_value = action.get('attribute_value', 3)
            skill_value = action.get('skill_value', 0)

            # Calculate DC: the DM's round-batch assessment is the
            # authoritative proposal, floored by calculate_dc guardrails;
            # absent assessment falls back to the category table
            is_ritual_action = action_type == 'ritual' or action.get('is_ritual', False)
            proposed_dc = action.get('dm_assessed_difficulty')
            difficulty = mechanics.calculate_dc(
                intent=intent,
                action_type=action_type,
                is_ritual=is_ritual_action,
                is_extreme=action.get('is_extreme', False),
                is_multi_stage=action.get('is_multi_stage', False),
                proposed_dc=proposed_dc
            )

            # MECHANICS-FIRST: Consume offering BEFORE DM narration (if ritual with offering)
            offering_consumed = False
            consumed_item = None
            inventory_changes = []

            # Get character name for logging
            character_name = action.get('character_name', action.get('character', player_id))

            if action.get('has_offering', False) and is_ritual_action:
                character_state = self.shared_state.get_agent_by_id(action.get('agent_id'))
                if character_state:
                    offering_type = action.get('offering_type')  # Optional specific item
                    consumed_item = mechanics.consume_offering(character_state, offering_type)

                    if consumed_item:
                        offering_consumed = True
                        inventory_changes.append({
                            "item": consumed_item,
                            "delta": -1,
                            "reason": "Consumed as ritual offering"
                        })
                        logger.info(f"Offering consumed BEFORE narration: {consumed_item} from {action.get('character_name')}")
                    else:
                        logger.warning(f"Player declared offering but none available for {action.get('character_name')} - mechanics will apply +1 void penalty")

            # Pass consumption result to action context for DM narration
            action['offering_consumed'] = offering_consumed
            action['offering_item'] = consumed_item

            # CRITICAL: Re-validate ritual mechanics at DM resolution time
            # (Player may have sent corrected values, but we enforce anyway)
            from .skill_mapping import validate_ritual_mechanics, RITUAL_ATTRIBUTE, RITUAL_SKILL

            if action_type == 'ritual' or action.get('is_ritual', False):
                # Force ritual mechanics
                if attribute != RITUAL_ATTRIBUTE or skill != RITUAL_SKILL:
                    logger.warning(f"DM correcting ritual: {attribute}×{skill} → {RITUAL_ATTRIBUTE}×{RITUAL_SKILL}")
                attribute = RITUAL_ATTRIBUTE
                skill = RITUAL_SKILL
                # Re-fetch values for corrected attribute/skill
                # (We'd need character sheet access here; for now trust player sent correct values)
                # This ensures resolve_action gets Willpower×Astral Arts

            # Collect modifiers for ML logging (situational modifiers from player action)
            # Initialize before branch so it's always available for display
            modifiers = {}
            if action.get('situational_modifiers'):
                modifiers.update(action['situational_modifiers'])

            # Resolve mechanically
            if action.get('is_ritual', False):
                # Ritual resolution (use actual consumption result, not player declaration)
                # Note: resolve_ritual internally handles ritual-specific modifiers (tool, offering, altar)
                # and passes them to resolve_action. We include situational_modifiers here for completeness.
                resolution, ritual_effects = mechanics.resolve_ritual(
                    intent=intent,
                    willpower=attribute_value if attribute == 'Willpower' else 3,
                    astral_arts=skill_value if skill == 'Astral Arts' else 0,
                    difficulty=difficulty,
                    has_primary_tool=action.get('has_primary_tool', False),
                    has_offering=offering_consumed,  # Use actual consumption result
                    sanctified_altar=action.get('at_altar', False),
                    agent_id=player_id,
                    faction=action.get('faction', None)
                )

                # NOTE: Don't add void here - outcome_parser will handle it
                # Just show consequences
                narration_suffix = "\n" + "\n".join(ritual_effects['consequences'])
            else:
                # Regular action resolution
                resolution = mechanics.resolve_action(
                    intent=intent,
                    attribute=attribute,
                    skill=skill,
                    attribute_value=attribute_value,
                    skill_value=skill_value,
                    difficulty=difficulty,
                    agent_id=player_id,
                    modifiers=modifiers if modifiers else None
                )
                narration_suffix = ""

            # Clock updates are deferred to synthesis phase (DM structured output)
            # to allow holistic round resolution

            # NOTE: Removed check_void_trigger call here to avoid duplicate void tracking
            # Void will be tracked via outcome_parser only

            # Get modifiers for display (reuse the modifiers collected above)
            display_modifiers = modifiers if modifiers else None

            # Format mechanical resolution
            mechanical_text = mechanics.format_resolution_for_narration(resolution, modifiers=display_modifiers)

            # Generate narrative description using LLM
            llm_narration = await self._generate_llm_response(
                player_id, action_type, description, resolution, action
            )

            narration = f"{mechanical_text}\n\n{llm_narration}{narration_suffix}"

            # Parse narration for automatic state changes
            from .outcome_parser import parse_state_changes

            # Get active clocks for dynamic clock progression
            active_clocks = mechanics.scene_clocks if mechanics else {}

            # CRITICAL: Resolve target IDs to entity names for effect application
            # In free targeting mode, actions have target="tgt_xxxx" but need entity names for structured output
            if action.get('target') and action['target'].startswith('tgt_'):
                target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                if target_id_mapper and target_id_mapper.enabled:
                    target_entity = target_id_mapper.resolve_target(action['target'])
                    if target_entity:
                        # Resolve target type and populate appropriate field
                        if target_id_mapper.is_player(action['target']):
                            # PC target - for PC-to-PC actions (healing, buffs, void cleansing)
                            if hasattr(target_entity, 'character_state') and hasattr(target_entity.character_state, 'name'):
                                action['target_character'] = target_entity.character_state.name
                                logger.debug(f"Resolved target ID {action['target']} → PC '{action['target_character']}'")
                        elif target_id_mapper.is_enemy(action['target']):
                            # Enemy target - for social actions, combat, debuffs
                            if hasattr(target_entity, 'name'):
                                action['target_enemy'] = target_entity.name
                                logger.debug(f"Resolved target ID {action['target']} → Enemy '{action['target_enemy']}'")
                        elif target_id_mapper.is_npc(action['target']):
                            # NPC target - for interactions with non-combatants
                            if hasattr(target_entity, 'name'):
                                action['target_npc'] = target_entity.name
                                logger.debug(f"Resolved target ID {action['target']} → NPC '{action['target_npc']}'")

            # Phase 2 Migration: Check if we have a structured resolution
            if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution is not None:
                from .outcome_parser import extract_from_structured_resolution

                # Build extraction context with available characters for fuzzy name matching
                extraction_context = {}
                if self.shared_state and hasattr(self.shared_state, 'registered_players'):
                    extraction_context['available_characters'] = [p['name'] for p in self.shared_state.registered_players]

                state_changes = extract_from_structured_resolution(self._last_structured_resolution, extraction_context)
                logger.debug("Using structured resolution for state changes extraction")

                # Effect suppression: if action was skipped/preempted, zero out all effects
                if getattr(self._last_structured_resolution, 'action_skipped', False):
                    skip_reason = getattr(self._last_structured_resolution, 'skip_reason', 'preempted')
                    logger.info(f"Action skipped (reason: {skip_reason}) — suppressing all mechanical effects")
                    state_changes['void_change'] = 0
                    state_changes['void_reasons'] = []
                    state_changes['soulcredit_change'] = 0
                    state_changes['soulcredit_reasons'] = []
                    state_changes['clock_triggers'] = []
                    state_changes['conditions'] = []
                    state_changes['damage_effects'] = []

                # Validate void changes were populated when narration contains void markers
                has_void_in_narrative = '⚫ Void' in llm_narration or 'Void (' in llm_narration

                if state_changes['void_change'] == 0 and has_void_in_narrative:
                    logger.warning(
                        f"STRUCTURED OUTPUT FAILURE: LLM put void changes in narrative text instead of "
                        f"populating effects.void_changes field for {action.get('agent')} action. "
                        f"Void changes will NOT be applied. This indicates prompt guidance is being ignored."
                    )
                    # TODO: Log to JSONL as structured_output_warning event for ML analysis
            else:
                # Legacy text parsing
                state_changes = parse_state_changes(llm_narration, action, resolution.__dict__, active_clocks)

            # Merge ritual soulcredit changes into state_changes
            if action.get('is_ritual', False) and 'ritual_effects' in locals():
                if 'soulcredit_change' not in state_changes:
                    state_changes['soulcredit_change'] = 0
                    state_changes['soulcredit_reasons'] = []

                state_changes['soulcredit_change'] += ritual_effects.get('soulcredit_change', 0)
                # Extract reasons from ritual consequences
                sc_reasons = [c for c in ritual_effects.get('consequences', []) if 'SC)' in c]
                state_changes['soulcredit_reasons'].extend(sc_reasons)

            # Queue clock advancements (will be applied batch during synthesis to prevent cascades)
            for clock_name, ticks, reason, source in state_changes['clock_triggers']:
                if clock_name in mechanics.scene_clocks:
                    mechanics.queue_clock_update(clock_name, ticks, reason)
                    logger.debug(f"Queued: {clock_name} {ticks:+d} ({reason}) [source: {source}]")

            # Extract and record party discoveries from successful actions
            if _resolution_success(resolution) and resolution.margin >= 5:
                # Extract key discovery from the narration (simple heuristic)
                # Look for sentences that suggest new information
                discovery_text = self._extract_discovery_from_narration(llm_narration, intent)
                if discovery_text:
                    character_name = action.get('character', 'Unknown')
                    self.shared_state.add_discovery(discovery_text, character_name)

            # Log LLM compliance issues for training analysis
            if state_changes.get('llm_compliance_issue'):
                compliance_issue = state_changes['llm_compliance_issue']
                logger.warning(f"⚠️  LLM COMPLIANCE LOGGED: {compliance_issue}")

                # Log to JSONL for training analysis
                if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                    mechanics.jsonl_logger.log_event(
                        'llm_compliance_issue',
                        {
                            'player_id': player_id,
                            'action_intent': intent,
                            'issue': compliance_issue,
                            'narration': llm_narration if self.llm_config else resolution.narrative
                        },
                        self.current_round
                    )

            # Apply void changes (both gains and reductions)
            # Enforce mode: the post-resolution magistrate is the sole ledger
            # writer, so skip the narration call's void application here.
            if state_changes['void_change'] != 0 and not getattr(mechanics, 'suppress_narration_economy', False):
                # Track void change for round summary
                if self.shared_state and hasattr(self.shared_state, 'session') and self.shared_state.session:
                    self.shared_state.session.track_void_change(state_changes['void_change'])

                # Check if void change targets a different character (collaborative cleansing)
                target_identifier = state_changes.get('void_target_character')
                should_apply_void_change = True  # Flag to control whether to apply the void change
                void_state = None
                target_name = None

                if target_identifier:
                    # Resolve target - could be target ID (tgt_xxxx) or character name
                    # NOTE: Relies on Pydantic schema validation to reject environmental keywords
                    # Schema validator prevents: "Environmental Void", "environment", "area", etc.
                    # Unresolvable names (environmental or typos) naturally skip via name resolution failure
                    target_player_id = None
                    target_character_name = None

                    if target_identifier.startswith('tgt_'):
                        # It's a target ID - resolve it
                        logger.debug(f"Resolving target ID '{target_identifier}' for void change")
                        target_id_mapper = self.shared_state.get_target_id_mapper()
                        target_entity = target_id_mapper.resolve_target(target_identifier)

                        if target_entity and hasattr(target_entity, 'agent_id'):
                            target_player_id = target_entity.agent_id
                            target_character_name = getattr(target_entity, 'character_state', None)
                            if target_character_name:
                                target_character_name = target_character_name.name
                            logger.debug(f"Resolved target ID {target_identifier} → '{target_character_name}' (player_id: {target_player_id})")
                    else:
                        # It's a character name - find by name (partial match)
                        target_character_name = target_identifier
                        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
                            for player in self.shared_state.player_agents:
                                if hasattr(player, 'character_state'):
                                    # Try exact match first, then partial match
                                    char_name = player.character_state.name
                                    if char_name == target_character_name or target_character_name in char_name:
                                        target_player_id = player.agent_id
                                        target_character_name = char_name  # Use full name
                                        logger.debug(f"Matched character name '{target_identifier}' → '{char_name}' (player_id: {target_player_id})")
                                        break

                    if target_player_id:
                        void_state = mechanics.get_void_state(target_player_id)
                        target_name = target_character_name
                        logger.debug(f"Void change targeting '{target_character_name}' (player_id: {target_player_id})")
                    else:
                        # Couldn't find target - skip instead of falling back to actor
                        # This handles environmental targets, typos, and non-existent characters
                        logger.warning(f"Could not resolve target '{target_identifier}' for void change, skipping application")
                        should_apply_void_change = False
                else:
                    # Default: apply to acting character (self-inflicted void)
                    void_state = mechanics.get_void_state(player_id)
                    target_name = action.get('character', player_id)

                # Only apply void change if we have a valid target
                if should_apply_void_change and void_state:
                    old_void = void_state.score

                    if state_changes['void_change'] > 0:
                        # Void gain (corruption increasing)
                        action_id = f"{player_id}_{intent}_{resolution.total}"
                        void_state.add_void(
                            state_changes['void_change'],
                            ", ".join(state_changes['void_reasons']),
                            action_id=action_id
                        )
                        # Show void increase if it actually changed
                        if void_state.score != old_void:
                            narration += f"\n\n⚫ Void ({target_name}): {old_void} → {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"
                    else:
                        # Void reduction (recovery moves)
                        void_state.reduce_void(
                            abs(state_changes['void_change']),
                            ", ".join(state_changes['void_reasons'])
                        )
                        # Show void decrease if it actually changed
                        if void_state.score != old_void:
                            narration += f"\n\n⚫ Void ({target_name}): {old_void} ↓ {void_state.score}/10 ({', '.join(state_changes['void_reasons'])})"

                    # Check for Eye of Breach appearance on high void
                    eye_of_breach_event = await self._check_eye_of_breach(void_state.score, mechanics, player_id)
                    if eye_of_breach_event:
                        narration += f"\n\n{eye_of_breach_event}"

            # Apply soulcredit changes (private knowledge - each player sees their own SC)
            # Always show soulcredit line (even if +0) for consistency, UNLESS DM already included one
            sc_state = mechanics.get_soulcredit_state(player_id)
            old_sc = sc_state.score
            sc_change = state_changes.get('soulcredit_change', 0)
            reasons_text = ', '.join(state_changes.get('soulcredit_reasons', [])) if state_changes.get('soulcredit_reasons') else 'no change'
            sc_source = state_changes.get('soulcredit_source', '')

            # Enforce mode: magistrate is sole ledger writer; skip narration SC.
            if sc_change != 0 and not getattr(mechanics, 'suppress_narration_economy', False):
                current_round = mechanics.current_round if mechanics else None
                sc_state.adjust(sc_change, reasons_text, round_num=current_round)

            # SC is applied mechanically above - no need to inject into narration
            # Players see their soulcredit via game UI, not narrative text

            # Apply conditions (with targeting support - apply to target, not actor)
            from .mechanics import Condition
            for condition_data in state_changes.get('conditions', []):
                condition = Condition(
                    name=condition_data['type'],
                    type=condition_data['type'],
                    penalty=condition_data['penalty'],
                    description=condition_data['description'],
                    duration=condition_data.get('duration', 3),
                    affects=[],  # Phase 3: populate from LLM output
                    protection_amount=condition_data.get('protection_amount')
                )

                # Determine who receives the condition
                # Priority: condition.target > action.target > actor (self)
                target_id = condition_data.get('target')  # Per-condition target (NEW - supports multi-target)
                if not target_id:
                    target_id = action.get('target')  # Fallback to action-level target

                condition_target_id = player_id  # Default: apply to actor
                condition_target_name = action.get('character', player_id)
                should_apply_condition = True  # Flag to control whether to apply

                # Handle different targeting scenarios
                if target_id == 'None' or target_id is None or not target_id:
                    # Special case: target="None" (string), None (null), or missing/empty
                    # These all mean: no specific target
                    # Apply condition to actor (self-buff OR self-debuff from failure/backlash)
                    if condition.penalty < 0:
                        logger.debug(f"Applying self-debuff '{condition.name}' (penalty={condition.penalty}) to actor (backlash/failure consequence)")
                        condition_target_id = player_id
                        condition_target_name = action.get('character', player_id)
                    else:
                        # Positive penalty = buff, apply to actor (self-buff)
                        logger.debug(f"Applying self-buff '{condition.name}' (penalty={condition.penalty}) to actor (no target specified)")
                        condition_target_id = player_id
                        condition_target_name = action.get('character', player_id)

                else:
                    # Action has an explicit target - apply condition to that target
                    logger.debug(f"Condition '{condition.name}' has target: {target_id}")

                    # Resolve target ID to agent_id
                    if target_id.startswith('tgt_'):
                        # It's a target ID - resolve it
                        target_id_mapper = self.shared_state.get_target_id_mapper()
                        target_entity = target_id_mapper.resolve_target(target_id)

                        if target_entity and hasattr(target_entity, 'agent_id'):
                            condition_target_id = target_entity.agent_id
                            if hasattr(target_entity, 'character_state'):
                                condition_target_name = target_entity.character_state.name
                            elif hasattr(target_entity, 'name'):
                                condition_target_name = target_entity.name
                            logger.debug(f"Resolved condition target {target_id} → '{condition_target_name}' (agent_id: {condition_target_id})")
                        else:
                            # Environmental objects (terminals, doors, etc.) have tgt_ IDs but aren't tracked entities
                            # This is expected behavior - conditions don't apply to non-entities
                            logger.debug(f"Target ID '{target_id}' not a tracked entity (likely env object), skipping condition")
                            should_apply_condition = False
                    else:
                        # It's a character name - try to find by name
                        condition_target_name = target_id
                        if self.shared_state and hasattr(self.shared_state, 'player_agents'):
                            for player in self.shared_state.player_agents:
                                if hasattr(player, 'character_state'):
                                    char_name = player.character_state.name
                                    if char_name == target_id or target_id in char_name:
                                        condition_target_id = player.agent_id
                                        condition_target_name = char_name
                                        logger.debug(f"Matched condition target '{target_id}' → '{char_name}' (agent_id: {condition_target_id})")
                                        break

                # Apply condition only if flag is True
                if should_apply_condition:
                    # Check if condition already exists before applying
                    already_exists = False
                    if condition_target_id in mechanics.conditions:
                        for existing in mechanics.conditions[condition_target_id]:
                            if existing.name == condition.name:
                                already_exists = True
                                break

                    # Only add condition if new (no narration injection - visible via structured output)
                    if not already_exists:
                        mechanics.add_condition(condition_target_id, condition)

            # Apply position changes (for tactical movement during rituals)
            if state_changes.get('position_change'):
                # Get player agent and update position
                player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                if player_agents:
                    player_agent = player_agents[0]
                    old_position = str(getattr(player_agent, 'position', 'Near-PC'))

                    # Parse and apply new position
                    from .enemy_agent import Position
                    try:
                        new_position_str = state_changes['position_change']
                        new_position = Position.from_string(new_position_str)
                        player_agent.position = new_position
                        logger.debug(f"Updated {player_id} position: {old_position} → {new_position}")
                        # Position change is already in narration from DM, no need to add here
                    except Exception as e:
                        logger.error(f"Failed to update player position: {e}")

            # Display notes from outcome parser (e.g., recovery move explanations)
            if state_changes.get('notes'):
                for note in state_changes['notes']:
                    narration += f"\n\n💡 {note}"

            # Check for filled clocks (triggers) and generate consequences
            clock_triggers = await self._check_clock_triggers(mechanics)
            if clock_triggers:
                narration += f"\n\n{clock_triggers}"

            # JSONL Logging: Log complete action resolution
            if mechanics.jsonl_logger and not self._outcome_first_enabled():
                # Get character name from action payload
                character_name = action.get('character', player_id)

                # Build economy changes
                economy_changes = {
                    "void_delta": state_changes.get('void_change', 0),
                    "soulcredit_delta": state_changes.get('soulcredit_change', 0),
                    "offering_used": action.get('has_offering', False),
                    "bonds_applied": []  # TODO: track bond applications
                }

                # Build clock states
                clock_states = {
                    name: f"{clock.current}/{clock.maximum}"
                    for name, clock in mechanics.scene_clocks.items()
                }

                # Build effects list
                effects = state_changes.get('notes', []) + state_changes.get('consequences', [])

                # Log the action resolution with enriched data
                log_context = {
                    "action_type": action_type,
                    "is_ritual": action.get('is_ritual', False),
                    "faction": action.get('faction', 'Unknown'),
                    "description": action.get('description', ''),
                    "narration": llm_narration,
                    "is_free_action": action.get('is_free_action', False)
                }

                # Add prompt metadata if available
                if hasattr(self, '_last_prompt_metadata') and self._last_prompt_metadata:
                    log_context["prompt_metadata"] = self._last_prompt_metadata.to_dict()

                # REMOVED: character_data extraction (redundant with character_state events)
                # Saves ~7,200 tokens/session by avoiding duplication
                # ML pipeline can reconstruct from character_state snapshots instead

                # Extract goal from action intent/description
                goal = action.get('intent') or action.get('description', 'Unknown goal')

                # Generate contextual fields for ML training
                environment = self._generate_environment_description(player_id)
                stakes = self._generate_stakes_description(player_id)
                roll_formula = self._generate_roll_formula(resolution)
                rationale = self._generate_rationale(resolution, action)

                # Extract outcome_tiers from structured output (if present)
                # NOTE: resolution is from mechanics, not structured output
                # We need to check self._last_structured_resolution instead
                outcome_tiers_with_narratives = None
                purchase_data = None
                crafting_data = None
                item_discovery_data = None
                if hasattr(self, '_last_structured_resolution') and self._last_structured_resolution:
                    if hasattr(self._last_structured_resolution, 'outcome_tiers') and self._last_structured_resolution.outcome_tiers:
                        # Convert OutcomeTierExplanation objects to dicts for JSON serialization
                        outcome_tiers_with_narratives = {}
                        for tier, explanation in self._last_structured_resolution.outcome_tiers.items():
                            outcome_tiers_with_narratives[tier] = {
                                'narrative': explanation.narrative,
                                'mechanical_effect': explanation.mechanical_effect
                            }

                    # Extract purchase, crafting, and item_discovery data from effects
                    if hasattr(self._last_structured_resolution, 'effects') and self._last_structured_resolution.effects:
                        effects_data = self._last_structured_resolution.effects
                        if hasattr(effects_data, 'purchase') and effects_data.purchase:
                            # Convert Pydantic model to dict for JSON serialization
                            purchase_data = effects_data.purchase.model_dump()
                        if hasattr(effects_data, 'crafting') and effects_data.crafting:
                            # Convert Pydantic model to dict for JSON serialization
                            crafting_data = effects_data.crafting.model_dump()
                        if hasattr(effects_data, 'item_discovery') and effects_data.item_discovery:
                            # Convert Pydantic model to dict for JSON serialization
                            item_discovery_data = effects_data.item_discovery.model_dump()

                mechanics.jsonl_logger.log_action_resolution(
                    round_num=mechanics.current_round,
                    phase="resolve",
                    agent_name=character_name,
                    action=intent,
                    resolution=resolution,
                    economy_changes=economy_changes,
                    clock_states=clock_states,
                    effects=effects,
                    context=log_context,
                    inventory_changes=inventory_changes,  # Pass offering consumption tracking
                    purchase_data=purchase_data,  # Pass purchase transaction data
                    crafting_data=crafting_data,  # Pass crafting attempt data
                    item_discovery_data=item_discovery_data,  # Pass item discovery data (seeds, currency, items)
                    # ML training fields (dataset guidelines compliance)
                    # character_data removed - redundant with character_state events
                    environment=environment,
                    stakes=stakes,
                    goal=goal,
                    roll_formula=roll_formula,
                    rationale=rationale,
                    outcome_tiers_with_narratives=outcome_tiers_with_narratives
                )

        else:
            # Fallback if no mechanics available
            narration = await self._generate_llm_response(
                player_id, action_type, description
            )

        # Prepare serializable outcome
        resolution_data = None
        if resolution:
            # Convert resolution to JSON-serializable dict
            resolution_data = {
                'intent': getattr(resolution, 'intent', None),
                'attribute': getattr(resolution, 'attribute', None),
                'skill': getattr(resolution, 'skill', None),
                'total': getattr(resolution, 'total', None),
                'difficulty': getattr(resolution, 'difficulty', None),
                'margin': resolution.margin if hasattr(resolution, 'margin') else 0,
                'outcome_tier': resolution.outcome_tier.value if hasattr(resolution, 'outcome_tier') and hasattr(resolution.outcome_tier, 'value') else str(getattr(resolution, 'outcome_tier', 'unknown')),
                'success': getattr(resolution, 'success', True)
            }

        outcome = {
            'dm_response': narration,
            'success': getattr(resolution, 'success', True) if resolution else True,
            'consequences': [],
            'resolution': resolution_data
        }

        self.send_message_sync(
            MessageType.ACTION_RESOLVED,
            None,  # Broadcast so all players see each other's results
            {
                'agent_id': player_id,  # Include player_id so session knows who completed
                'original_action': action,
                'outcome': outcome,
                'narration': narration
            }
        )

        print(f"\n[DM {self.agent_id}] ===== Resolution =====")
        print(narration)
        print("=" * 40)
        
    async def _handle_turn_request(self, message: Message):
        """Handle request for DM turn (narrative, NPC actions, etc.)."""
        await self._ai_dm_turn()

    async def _ai_dm_turn(self):
        """Handle AI DM turn - provide synthesis of the round."""
        # For now, just provide status
        # TODO: Full synthesis would require tracking all resolutions and generating narrative
        if self.shared_state and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine

            # Build status summary
            status_parts = []

            # Show clock states
            for clock_name, clock in mechanics.scene_clocks.items():
                status_parts.append(f"{clock_name}: {clock.current}/{clock.maximum}")

            if status_parts:
                # Format clock status without emoji markers
                status_line = " | ".join(status_parts)

                # Simple narrative wrapper
                narration = f"The situation evolves... ({status_line})"
            else:
                # Skip DM turn if nothing to report
                return

            self.send_message_sync(
                MessageType.DM_NARRATION,
                None,
                {
                    'narration': narration,
                    'environmental_changes': [],
                    'npc_actions': []
                }
            )

            print(f"\n[DM {self.agent_id}] {narration}")
        else:
            # Skip DM turn if no mechanics
            return

    async def _handle_agent_register(self, message: Message):
        """Handle agent registration messages (no-op for DM)."""
        pass

    async def _handle_dm_narration(self, message: Message):
        """Handle DM narration messages (no-op - DM sends these, doesn't receive them)."""
        pass

    def _build_dm_narration_prompt(
        self,
        is_dialogue: bool,
        scenario_context: str,
        character_context: str,
        resolution_context: str,
        tactical_combat_context: str,
        clock_context: str,
        bond_matrix: str = "",
        void_level: int = 3,
        void_impact: str = "",
        outcome_guidance: str = "",
        description: str = "",
        action_type: str = "",
        enemy_spawn_instructions: str = "",
        party_context: str = "",
        character_name: str = "",
        target_character: str = "",
        target_id: str = "",
        previous_context: str = "",
        combatant_list: str = "",
        session_context: str = "",
        action: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build DM narration prompt using prompt_loader system.

        Handles both PC-to-PC dialogue and standard action narration.
        Stores prompt metadata in self._last_prompt_metadata for logging.
        """
        if is_dialogue:
            # PC-to-PC dialogue path
            prompt_parts = []
            prompt_parts.append("You are the Dungeon Master for an Aeonisk YAGS game session.")
            prompt_parts.append("")

            if scenario_context:
                prompt_parts.append(scenario_context)
            if party_context:
                prompt_parts.append(party_context)
            if enemy_spawn_instructions:
                prompt_parts.append(enemy_spawn_instructions)
            if character_context:
                prompt_parts.append(character_context)
            if resolution_context:
                prompt_parts.append(resolution_context)

            prompt_parts.append(f"\nPlayer Action: {description}")
            prompt_parts.append(f"Action Type: {action_type} (DIALOGUE with {target_character})")

            if void_impact:
                prompt_parts.append(void_impact)
            if tactical_combat_context:
                prompt_parts.append(tactical_combat_context)

            # Add dialogue task template
            variables = {
                "initiating_character": character_name,
                "target_character": target_character
            }

            loaded_prompt = load_agent_prompt(
                agent_type="dm",
                provider="claude",
                language="en",
                section="dialogue_task",
                variables=variables
            )

            prompt_parts.append("")
            prompt_parts.append(loaded_prompt.content)

            self._last_prompt_metadata = loaded_prompt.metadata
            return "\n".join(prompt_parts)

        else:
            # Standard narration path - compose multiple sections
            prompt_parts = []
            prompt_parts.append("You are the Dungeon Master for an Aeonisk YAGS game session.")
            prompt_parts.append("")

            if scenario_context:
                prompt_parts.append(scenario_context)
            if enemy_spawn_instructions:
                prompt_parts.append(enemy_spawn_instructions)
            if character_context:
                prompt_parts.append(character_context)
            if resolution_context:
                prompt_parts.append(resolution_context)
            if previous_context:
                prompt_parts.append(previous_context)

            prompt_parts.append(f"\nPlayer Action: {description}")
            ambient_speech = action.get('ambient_speech') if isinstance(action, dict) else None
            if isinstance(ambient_speech, dict) and ambient_speech.get('line'):
                delivery = ambient_speech.get('delivery', 'spoken')
                target = ambient_speech.get('target')
                target_type = ambient_speech.get('target_type', 'self')
                target_text = f" to {target}" if target else f" to {target_type}"
                prompt_parts.append(
                    "Ambient Speech (flavor only, do not roll or apply mechanics): "
                    f"[{delivery}{target_text}] \"{ambient_speech['line']}\""
                )
            prompt_parts.append(f"Action Type: {action_type}")

            # Add declared target explicitly so DM knows who the player is targeting
            if target_id:
                target_name_resolved = None
                if self.shared_state:
                    target_id_mapper = self.shared_state.get_target_id_mapper()
                    if target_id_mapper and target_id_mapper.enabled:
                        target_entity = target_id_mapper.resolve_target(target_id)
                        if target_entity:
                            if hasattr(target_entity, 'character_state'):
                                target_name_resolved = target_entity.character_state.name
                            elif hasattr(target_entity, 'name'):
                                target_name_resolved = target_entity.name
                if target_name_resolved:
                    prompt_parts.append(f"⚠️ DECLARED TARGET: [{target_id}] {target_name_resolved} — use this target ID in DamageEffect/Condition target fields.")
                else:
                    prompt_parts.append(f"⚠️ DECLARED TARGET: {target_id} — use this target ID in DamageEffect/Condition target fields.")

            if void_impact:
                prompt_parts.append(void_impact)
            if tactical_combat_context:
                prompt_parts.append(tactical_combat_context)
            if clock_context:
                prompt_parts.append(clock_context)
            if bond_matrix:
                prompt_parts.append(bond_matrix)
            if combatant_list:
                prompt_parts.append(combatant_list)
            if session_context:
                prompt_parts.append(session_context)

            # Add narration task template with outcome guidance
            variables = {
                "void_level": str(void_level),
                "outcome_guidance": outcome_guidance,
                "target_id": target_id if target_id else "",
                "target_id_instruction": f" (target ID: {target_id})" if target_id else ""
            }

            loaded_prompt = load_agent_prompt(
                agent_type="dm",
                provider="claude",
                language="en",
                section="narration_task",
                variables=variables
            )

            prompt_parts.append("")
            prompt_parts.append(loaded_prompt.content)

            self._last_prompt_metadata = loaded_prompt.metadata
            return "\n".join(prompt_parts)

    async def _retry_invalid_markers(
        self,
        marker_type: str,
        invalid_markers: List[str],
        round_num: int
    ) -> str:
        """
        Ask DM to properly format incomplete markers.

        Args:
            marker_type: "SPAWN_ENEMY" or "ADVANCE_STORY"
            invalid_markers: List of incomplete marker contents
            round_num: Current round number

        Returns:
            LLM response with corrected markers
        """

        if marker_type == "SPAWN_ENEMY":
            format_spec = """
REQUIRED FORMAT (ALL 4 FIELDS):
[SPAWN_ENEMY: name | template | position | tactics]

**Templates:** grunt, elite, sniper, boss, void_cultist, enforcer
**Positions:** Near-Enemy, Far-Enemy, Engaged, Extreme-Enemy
**Tactics:** aggressive_melee, aggressive_ranged, defensive, support, tactical_ranged, extreme_range, adaptive

Example:
[SPAWN_ENEMY: Freeborn Raiders | grunt | Far-Enemy | aggressive_ranged]
"""
        elif marker_type == "ADVANCE_STORY":
            format_spec = """
REQUIRED FORMAT (2 FIELDS):
[ADVANCE_STORY: new_location | new_situation]

Example:
[ADVANCE_STORY: Abandoned Warehouse District | The team tracks the raiders to their hideout, preparing for final confrontation]
"""
        else:
            logger.error(f"Unknown marker type: {marker_type}")
            return ""

        retry_prompt = f"""
You generated incomplete {marker_type} markers. Please provide the COMPLETE format for each:

INVALID MARKERS:
{chr(10).join(f'- [{marker_type}: {m}]' for m in invalid_markers)}

{format_spec}

Provide ONLY the corrected markers, one per line. No narrative or explanation.
"""

        # Log retry attempt to JSONL
        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_marker_retry(
                round_num=round_num,
                marker_type=marker_type,
                invalid_markers=invalid_markers,
                retry_prompt=retry_prompt
            )

        # Get LLM config
        model = self.llm_config.get('model', 'gpt-4')

        # Call LLM with lower temperature for format compliance
        # Use call_anthropic_with_retry for automatic retry/rate limiting
        try:
            from .llm_provider import call_anthropic_with_retry
            llm_response = await call_anthropic_with_retry(
                client=self.llm_client,
                model=model,
                messages=[{"role": "user", "content": retry_prompt}],
                max_tokens=300,
                temperature=self.llm_config.get('temperature', 1.0),  # Lower temp for format compliance
                max_retries=3,
                use_rate_limiter=True
            )
            response = llm_response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Error in marker retry LLM call: {e}")
            response = ""

        # Log retry result to JSONL
        success = len(response.strip()) > 0
        if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_marker_retry_result(
                round_num=round_num,
                marker_type=marker_type,
                retry_response=response,
                success=success
            )

        logger.info(f"Retry response for {marker_type}: {response[:200]}")
        return response

    def _outcome_first_enabled(self) -> bool:
        from .outcome_pipeline import outcome_pipeline_enabled
        return outcome_pipeline_enabled(self.session_config)

    async def _generate_action_resolution_structured(
        self,
        player_id: str,
        action_type: str,
        description: str,
        resolution=None,
        action=None
    ):
        """
        Generate DM action resolution using structured output (Pydantic AI).

        Returns ActionResolution (legacy) or ActionAdjudication (outcome-first)
        if structured output succeeds,
        or None if it should fall back to legacy text generation.

        This is Phase 2 of the Pydantic AI migration.
        """
        # Only try structured output if provider is available
        if not hasattr(self, 'llm_provider') or self.llm_provider is None:
            logger.debug("DM: No llm_provider available, will use legacy text generation")
            return None

        # Bind mechanics up front: the targeting-correction path below references
        # `mechanics` (for JSONL logging) before its first conditional assignment,
        # which raised UnboundLocalError whenever a damage effect needed correction.
        mechanics = self.shared_state.mechanics_engine if self.shared_state else None

        try:
            from .structured_output_helpers import generate_dm_resolution_structured
            from .schemas.action_resolution import ActionResolution
            from .outcome_pipeline import ActionAdjudication, outcome_pipeline_enabled

            # Build the same prompt as legacy method
            # (We'll refactor this to share code in future iterations)
            prompt = await self._build_resolution_prompt(
                player_id, action_type, description, resolution, action
            )
            outcome_first = outcome_pipeline_enabled(self.session_config)
            result_type = ActionAdjudication if outcome_first else ActionResolution
            if outcome_first:
                prompt += """

**OUTCOME-FIRST ADJUDICATION CONTRACT (BINDING):**
- Return structured mechanics only. Do not write literary narration.
- The declaration states intent, not what happened.
- Populate effects for the mechanical result; the engine applies them afterward.
- `reasoning_short` is concise rules rationale, not scene prose.
- Do not infer final death or consciousness state; the engine computes it.
"""

            # Try structured output with fallback disabled (we handle fallback ourselves)
            logger.debug(f"DM: Attempting structured output for {action_type} action")

            # Build clock context for prompt variable interpolation
            clock_context = self._build_clock_context()

            # Load DM system prompt with conditional modules
            try:
                # Determine which modules to load based on game state AND action type
                required_modules = self._get_required_dm_modules(action_type=action_type)

                # Load modular prompt with variables
                system_prompt_obj = load_modular_prompt(
                    agent_type="dm",
                    module_names=required_modules,
                    provider="claude",
                    language="en",
                    variables={"clock_context": clock_context}
                )
                system_prompt = system_prompt_obj.content
                logger.debug(
                    f"DM: Loaded modular prompt with {len(required_modules)} modules "
                    f"({len(system_prompt)} chars): {', '.join(required_modules)}"
                )
            except Exception as e:
                logger.error(f"DM: Failed to load modular prompt: {e}")
                # Fallback to simple prompt
                system_prompt = "You are an expert Aeonisk YAGS Dungeon Master. Generate vivid, detailed action resolutions."

            if outcome_first:
                system_prompt = (
                    "You are an expert Aeonisk YAGS adjudicator. Return mechanics "
                    "only and never narrate an outcome.\n\n" + system_prompt
                )

            model = self.llm_config.get('model', 'claude-sonnet-4-5')
            max_tokens = self.llm_config.get('max_tokens', 6000)  # Increased for complex ActionResolution schemas
            temperature = self.llm_config.get('temperature', 1.0)

            # Get current round for logging
            current_round = None
            if self.shared_state and self.shared_state.mechanics_engine:
                current_round = self.shared_state.mechanics_engine.current_round

            # Strict mode: No fallback, will raise on error (retry logic built into provider)
            resolution_obj = await generate_dm_resolution_structured(
                provider=self.llm_provider,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                # Pass llm_logger and current_round for token tracking
                llm_logger=self.llm_logger,
                current_round=current_round,
                result_type=result_type,
                # fallback_to_text defaults to False - strict mode
            )

            if isinstance(resolution_obj, (ActionResolution, ActionAdjudication)):
                has_outcome_tiers = hasattr(resolution_obj, 'outcome_tiers') and resolution_obj.outcome_tiers is not None
                outcome_tiers_count = len(resolution_obj.outcome_tiers) if has_outcome_tiers else 0
                logger.debug(f"✓ DM structured resolution: outcome_tiers: {outcome_tiers_count}/6 {'✓' if outcome_tiers_count == 6 else '✗ MISSING'}")

                # Validate structured output completeness
                from .structured_output_helpers import validate_resolution_completeness
                validation_warnings = (
                    [] if outcome_first
                    else validate_resolution_completeness(resolution_obj, action)
                )
                if validation_warnings:
                    logger.info(f"🔍 Structured output validation found {len(validation_warnings)} issue(s):")
                    for warning in validation_warnings:
                        logger.info(f"   - {warning}")
                else:
                    logger.debug("✓ Structured output validation passed (all expected fields populated)")

                # TARGETING VALIDATION: Check and correct targeting errors in damage effects
                # NOTE: Currently validates only first damage effect for AoE (List[DamageEffect])
                if resolution_obj.effects and resolution_obj.effects.damage:
                    from .targeting_validation import validate_and_correct_targeting, llm_infer_correct_target
                    import time

                    start_time = time.time()

                    # For AoE (list of damage effects), validate first target
                    # TODO: Extend to validate all targets in AoE
                    first_damage = resolution_obj.effects.damage[0] if resolution_obj.effects.damage else None

                    if first_damage:
                        is_valid, corrected_effect, error = validate_and_correct_targeting(
                            effect=first_damage,
                            declared_action=action,
                            target_id_mapper=self.shared_state.get_target_id_mapper() if self.shared_state else None,
                            allow_llm_fallback=True
                        )
                    else:
                        # Empty damage list - skip validation
                        is_valid = True
                        corrected_effect = None
                        error = None

                    validation_time_ms = (time.time() - start_time) * 1000

                    if not is_valid:
                        # Mechanical correction failed - try LLM fallback
                        logger.warning(f"⚠️  TARGETING VALIDATION: {error}")

                        try:
                            # Build available targets map
                            available_targets = {}
                            target_id_mapper = self.shared_state.get_target_id_mapper() if self.shared_state else None
                            if target_id_mapper and target_id_mapper.enabled:
                                for target_id in target_id_mapper.get_all_target_ids():
                                    info = target_id_mapper.get_combatant_info(target_id)
                                    if info:
                                        entity_type = info.get('type', 'unknown')
                                        entity_name = info.get('name', 'Unknown')
                                        available_targets[target_id] = f"{entity_name} ({entity_type})"

                            # Call Haiku LLM for inference
                            correction = await llm_infer_correct_target(
                                effect=first_damage,
                                declared_action=action,
                                available_targets=available_targets,
                                error_description=error,
                                dm_narration=(
                                    getattr(resolution_obj, 'narration', None)
                                    or description
                                    or (action or {}).get('intent', '')
                                )
                            )

                            # Apply LLM-corrected target
                            corrected_effect = first_damage.model_copy(
                                update={'target': correction.corrected_target}
                            )

                            logger.info(f"🤖 LLM TARGETING CORRECTION: {first_damage.target} -> {correction.corrected_target} (confidence: {correction.confidence})")

                            # Log to JSONL
                            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_targeting_validation(
                                    round_num=current_round if current_round else 0,
                                    agent_id=action.get('agent_id', 'unknown'),
                                    original_target=first_damage.target,
                                    corrected_target=correction.corrected_target,
                                    correction_method='llm_inference',
                                    triggered_by=_targeting_trigger_reason(error),
                                    success=True,
                                    confidence=correction.confidence,
                                    reasoning=correction.reasoning,
                                    declared_target=action.get('target'),
                                    effect_type='damage',
                                    model_used='claude-haiku-4',
                                    validation_time_ms=validation_time_ms
                                )

                            is_valid = True

                        except Exception as llm_error:
                            logger.error(f"❌ LLM targeting correction failed: {llm_error}")
                            corrected_effect = None

                            # Log failed correction
                            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_targeting_validation(
                                    round_num=current_round if current_round else 0,
                                    agent_id=action.get('agent_id', 'unknown'),
                                    original_target=first_damage.target,
                                    corrected_target=None,
                                    correction_method='failed',
                                    triggered_by=_targeting_trigger_reason(error),
                                    success=False,
                                    error=str(llm_error),
                                    declared_target=action.get('target'),
                                    effect_type='damage',
                                    validation_time_ms=validation_time_ms
                                )

                    # Apply corrected effect or clear if validation failed
                    if is_valid and corrected_effect:
                        # Update first damage effect in list
                        resolution_obj.effects.damage[0] = corrected_effect
                        if first_damage and corrected_effect.target != first_damage.target:
                            logger.info(f"✓ MECHANICAL CORRECTION: {first_damage.target} -> {corrected_effect.target}")

                            # Log mechanical correction
                            if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                                mechanics.jsonl_logger.log_targeting_validation(
                                    round_num=current_round if current_round else 0,
                                    agent_id=action.get('agent_id', 'unknown'),
                                    original_target=first_damage.target,
                                    corrected_target=corrected_effect.target,
                                    correction_method='mechanical',
                                    triggered_by=_targeting_trigger_reason(error),
                                    success=True,
                                    declared_target=action.get('target'),
                                    effect_type='damage',
                                    validation_time_ms=validation_time_ms
                                )
                    elif not is_valid:
                        # Clear invalid effect to prevent misapplication
                        logger.error(f"❌ Targeting validation failed - clearing damage effect")
                        resolution_obj.effects.damage = []  # Clear list instead of setting to None
                        validation_warnings.append(f"Damage effect removed due to unrecoverable targeting error: {error}")

                # Log structured output metrics (for ML analysis)
                if self.shared_state and self.shared_state.mechanics_engine:
                    mechanics = self.shared_state.mechanics_engine
                    if hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                        # Calculate completeness score (0.0-1.0)
                        expected_fields = 6 if outcome_first else 7
                        populated_fields = 0
                        if outcome_first or len(resolution_obj.narration) >= 200:
                            populated_fields += 1
                        if resolution_obj.effects:
                            if resolution_obj.effects.soulcredit_changes:
                                populated_fields += 1
                            # Add points for optional fields that are populated when expected
                            if resolution_obj.effects.damage or resolution_obj.effects.void_changes:
                                populated_fields += 1
                            if resolution_obj.effects.clock_updates:
                                populated_fields += 1
                            if resolution_obj.effects.conditions:
                                populated_fields += 1
                        completeness_score = populated_fields / expected_fields

                        mechanics.jsonl_logger.log_structured_output_metrics(
                            round_num=current_round if current_round else 0,
                            agent_type='dm',
                            agent_id=self.agent_id,
                            success=True,  # Got structured output
                            fallback_triggered=False,  # Didn't fall back to text
                            validation_warnings=validation_warnings,
                            completeness_score=completeness_score
                        )

                # NOTE: do NOT _log_llm_call here — generate_dm_resolution_structured
                # already logs this call internally (llm_logger passed through to
                # provider.generate_structured). A manual re-log here produced a
                # phantom narration-only duplicate per adjudication (6/24 DM
                # "calls" in a 3-round smoke were phantoms), poisoning the
                # replay cache with calls the engine never made.

                # Also log to human-readable agent prompt log if enabled
                if self.agent_prompt_logger:
                    try:
                        full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=current_round,
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=full_prompt,
                            response=resolution_obj.model_dump_json(indent=2),
                            model=model,
                            temperature=temperature,
                            metadata={
                                'purpose': 'action_adjudication_structured' if outcome_first else 'action_resolution_structured',
                                'note': f'Pydantic structured output ({result_type.__name__} schema)'
                            }
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                # === GATE: Clear hallucinated damage on mechanical miss ===
                # If the d20 roll was a miss, the DM should not have populated damage.
                # Clear it and log a warning about the DM contradicting the mechanical roll.
                if resolution and not resolution.success and resolution_obj.effects and resolution_obj.effects.damage:
                    logger.warning(
                        f"DM populated damage effects despite mechanical MISS "
                        f"(d20={resolution.roll}, total={resolution.total}, DC={resolution.difficulty}, "
                        f"tier={resolution.outcome_tier.value}). Clearing hallucinated damage."
                    )
                    resolution_obj.effects.damage = []

                # === PROCESS STRUCTURED DAMAGE EFFECTS (NEW PIPELINE) ===
                # Apply damage from List[DamageEffect], including barrier interception
                if resolution_obj.effects and resolution_obj.effects.damage:
                    logger.debug(f"Processing {len(resolution_obj.effects.damage)} damage effects from structured output")

                    # Extract attacker context from player action
                    attacker_id = action.get('agent_id', 'unknown') if action else 'unknown'
                    attacker_name = action.get('character_name', 'Unknown Attacker') if action else 'Unknown Attacker'

                    # Build attack roll data from mechanical resolution for ML logging
                    attack_roll_data = None
                    if resolution:
                        attack_roll_data = {
                            "attr": resolution.attribute,
                            "attr_val": resolution.attribute_value,
                            "skill": resolution.skill,
                            "skill_val": resolution.skill_value,
                            "d20": resolution.roll,
                            "total": resolution.total,
                            "dc": resolution.difficulty,
                            "hit": resolution.success,
                            "margin": resolution.margin
                        }

                    # Resolve weapon and damage type from equipped_weapons
                    weapon_name, resolved_damage_type, _ = _resolve_weapon_and_damage_type(action, self.shared_state)
                    # Fallback: check action dict, then skill name
                    if weapon_name == "Unknown Weapon" and action:
                        weapon_name = action.get('weapon') or action.get('skill', 'Unknown Weapon')
                    weapon_name = weapon_name or 'Unknown Weapon'

                    damage_messages = _process_structured_damage_effects(
                        damage_effects=resolution_obj.effects.damage,
                        shared_state=self.shared_state,
                        current_round=current_round if current_round else 0,
                        mechanics=mechanics if 'mechanics' in locals() else None,
                        logger_instance=logger,
                        attacker_id=attacker_id,
                        attacker_name=attacker_name,
                        weapon=weapon_name,
                        attack_roll=attack_roll_data,
                        resolved_damage_type=resolved_damage_type,
                        declared_weapon=action.get('weapon')
                    )

                    # Append damage outcome messages to narration
                    if damage_messages and not outcome_first:
                        additional_narration = "\n\n" + "\n\n".join(damage_messages)
                        resolution_obj.narration += additional_narration
                        logger.debug(f"Appended {len(damage_messages)} damage messages to narration")

                # === PROCESS STRUCTURED HEALING EFFECTS (NEW PIPELINE) ===
                # Apply healing from List[HealingEffect]
                if resolution_obj.effects and resolution_obj.effects.healing:
                    logger.debug(f"Processing {len(resolution_obj.effects.healing)} healing effects from structured output")

                    healing_messages = _process_structured_healing_effects(
                        healing_effects=resolution_obj.effects.healing,
                        shared_state=self.shared_state,
                        current_round=current_round if current_round else 0,
                        mechanics=mechanics if 'mechanics' in locals() else None,
                        logger_instance=logger
                    )

                    # Append healing outcome messages to narration
                    if healing_messages and not outcome_first:
                        additional_narration = "\n\n" + "\n\n".join(healing_messages)
                        resolution_obj.narration += additional_narration
                        logger.debug(f"Appended {len(healing_messages)} healing messages to narration")

                # === PROCESS STEALTH CHANGES (Spec 05) ===
                # Apply stealth state changes from DM structured output
                if resolution_obj.effects and resolution_obj.effects.stealth_changes:
                    logger.debug(f"Processing {len(resolution_obj.effects.stealth_changes)} stealth changes from structured output")
                    _process_stealth_changes(resolution_obj.effects.stealth_changes, self.shared_state)

                # === AUTO-BREAK STEALTH ON COMBAT (Spec 05 Phase 4) ===
                # If a hidden agent attacks, automatically reveal them
                if action:
                    _auto_break_stealth_on_combat(action, self.shared_state)

                return resolution_obj
            else:
                error_msg = f"DM: Structured output returned text instead of {result_type.__name__} object"
                logger.error(error_msg)
                raise TypeError(error_msg)

        except Exception as e:
            # Enhanced error logging with detailed diagnostics
            error_type = type(e).__name__
            error_message = str(e)

            # Try to extract raw model response from UnexpectedModelBehavior
            raw_response = None
            if hasattr(e, 'body') and e.body:
                raw_response = e.body

            # Try to extract underlying error
            underlying_error = None
            if hasattr(e, '__cause__') and e.__cause__:
                underlying_error = f"{type(e.__cause__).__name__}: {str(e.__cause__)}"
            else:
                # Bare exceptions (e.g. a TypeError from unguarded `x in None`
                # in the resolution-processing chain) carry no __cause__; the
                # traceback is the only way to locate the failing line.
                import traceback
                tb = traceback.extract_tb(e.__traceback__)
                if tb:
                    frame = tb[-1]
                    underlying_error = (
                        f"{error_type} at {frame.filename.split('/')[-1]}:"
                        f"{frame.lineno} in {frame.name}(): {frame.line}"
                    )

            logger.error(
                f"❌ DM: Structured output failed:\n"
                f"  Exception: {error_type}\n"
                f"  Message: {error_message}\n"
                f"  Action type: {action_type}\n"
                f"  Player: {player_id}\n"
                + (f"  Raw response: {len(raw_response)} chars\n" if raw_response else "")
                + (f"  Underlying: {underlying_error}\n" if underlying_error else "")
            )

            # Log failure to JSONL for ML analysis
            if self.shared_state and self.shared_state.mechanics_engine:
                mechanics = self.shared_state.mechanics_engine
                if hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
                    current_round = mechanics.current_round if hasattr(mechanics, 'current_round') else 0

                    # Extract validation error details
                    validation_errors = []
                    if "validation" in error_message.lower():
                        validation_errors.append(f"{error_type}: {error_message[:200]}")

                    # Extract underlying cause if available
                    if underlying_error:
                        validation_errors.append(f"Cause: {underlying_error[:200]}")

                    # Log to structured_output_metrics (general overview)
                    mechanics.jsonl_logger.log_structured_output_metrics(
                        round_num=current_round,
                        agent_type='dm',
                        agent_id=self.agent_id,
                        success=False,  # Failed to generate structured output
                        fallback_triggered=False,  # No fallback attempted (strict mode)
                        validation_warnings=validation_errors if validation_errors else [f"{error_type}: {error_message[:200]}"],
                        completeness_score=0.0  # Failed completely
                    )

                    # ALSO log to pydantic_validation_failure (detailed debugging)
                    mechanics.jsonl_logger.log_pydantic_validation_failure(
                        round_num=current_round,
                        agent_type='dm',
                        agent_id=self.agent_id,
                        schema_name=(
                            'ActionAdjudication'
                            if self._outcome_first_enabled()
                            else 'ActionResolution'
                        ),
                        exception_type=error_type,
                        error_message=error_message,
                        attempt_number=4,  # We don't know the exact attempt here, using max
                        max_attempts=4,  # ClaudeProvider default
                        raw_model_response=raw_response,
                        underlying_error=underlying_error,
                        action_context={
                            'action_type': action_type,
                            'player_id': player_id,
                            'description': description[:200] if description else None
                        }
                    )

            raise RuntimeError(f"Structured output generation failed: {e}") from e

    def _build_clock_context(self) -> str:
        """Build enriched clock context for action resolution prompts.

        Returns a string showing each clock's progress, age, timeout remaining,
        advance/regress meanings, and EXPIRING SOON warnings.
        """
        if not self.shared_state:
            return ""

        mechanics = None
        if hasattr(self.shared_state, 'mechanics_engine') and self.shared_state.mechanics_engine:
            mechanics = self.shared_state.mechanics_engine
        elif hasattr(self.shared_state, 'get_mechanics_engine'):
            mechanics = self.shared_state.get_mechanics_engine()

        if not mechanics or not mechanics.scene_clocks:
            return ""

        clock_lines = ["Active Scene Clocks (IMPORTANT: Use EXACT names in clock_updates):"]
        for clock_name, clock in mechanics.scene_clocks.items():
            # Progress and age
            age = clock._rounds_alive
            timeout = clock.timeout_rounds
            line = f'  - "{clock_name}" ({clock.current}/{clock.maximum}, round {age}/{timeout}) - {clock.description}'

            # Expiring soon warning
            if age >= timeout - 2:
                line += "  ⚠️ EXPIRING SOON"

            # Advance/regress meanings
            meanings = []
            if clock.advance_meaning:
                meanings.append(f"advance={clock.advance_meaning}")
            if clock.regress_meaning:
                meanings.append(f"regress={clock.regress_meaning}")
            if meanings:
                line += f"\n      {' | '.join(meanings)}"

            clock_lines.append(line)

        clock_lines.append("\nWhen adding clock_updates in MechanicalEffects, use ONLY these exact clock names.")
        return "\n".join(clock_lines)

    def _get_clock_budget_text(self, active_count: int) -> str:
        """Return clock budget guidance text based on number of active clocks."""
        if active_count >= 4:
            return f"Clock Budget: {active_count}/4 active — do NOT spawn new clocks unless one fills/expires first."
        elif active_count >= 2:
            return f"Clock Budget: {active_count} active — spawn only if a clock fills and creates genuine new pressure."
        else:
            return f"Clock Budget: {active_count} active — you may spawn 1-2 new clocks if the story demands it."

    def _build_narrative_digest(self, current_round: int, lookback: int = 3) -> str:
        """Build rolling narrative digest from recent round synthesis history.

        Returns full untruncated narration for the last `lookback` rounds.
        Returns empty string for round 1 or when no history exists.
        """
        if not self._round_synthesis_history:
            return ""

        # Take last `lookback` entries
        recent = self._round_synthesis_history[-lookback:]

        lines = ["PRIOR ROUNDS:"]
        for round_num, narration in recent:
            lines.append(f"  R{round_num}: {narration}")

        return "\n".join(lines)

    def _build_faction_context(self) -> str:
        """Build faction relationship context for DM adjudication prompt.

        Collects all combatants from the target_id_mapper, groups them by faction,
        and produces a formatted block showing which factions are present on the
        battlefield and what entity types belong to each.

        This helps the DM reason about same-faction conflicts, cross-faction
        alliances, and NPC neutrality without relying solely on faction labels.

        Returns:
            Formatted faction context string, or empty string if unavailable.
        """
        if not self.shared_state:
            return ""

        target_id_mapper = self.shared_state.get_target_id_mapper()
        if not target_id_mapper or not target_id_mapper.enabled:
            return ""

        all_target_ids = target_id_mapper.get_all_target_ids()
        if not all_target_ids:
            return ""

        # Group entities by faction
        # faction -> {type -> [entity_names]}
        faction_groups: Dict[str, Dict[str, List[str]]] = {}

        for tid in all_target_ids:
            info = target_id_mapper.get_combatant_info(tid)
            if not info:
                continue

            faction = info.get('faction', 'Unknown')
            entity_type = info.get('type', 'unknown')
            entity_name = info.get('name', 'Unknown')

            if faction not in faction_groups:
                faction_groups[faction] = {}
            if entity_type not in faction_groups[faction]:
                faction_groups[faction][entity_type] = []
            faction_groups[faction][entity_type].append(entity_name)

        if not faction_groups:
            return ""

        lines = ["FACTION CONTEXT (entities on battlefield by faction):"]

        for faction in sorted(faction_groups.keys()):
            type_groups = faction_groups[faction]
            entity_parts = []

            # Determine the relationship summary for this faction
            has_party = 'player' in type_groups
            has_enemy = 'enemy' in type_groups
            has_npc = 'npc' in type_groups

            for entity_type in sorted(type_groups.keys()):
                names = type_groups[entity_type]
                if len(names) == 1:
                    entity_parts.append(f"{names[0]} ({entity_type})")
                else:
                    entity_parts.append(f"{', '.join(names)} ({entity_type}, {len(names)}x)")

            # Build relationship note
            if has_party and has_enemy:
                relationship = " [INTERNAL CONFLICT — party member(s) and hostile(s) share this faction]"
            elif has_party:
                relationship = " [party faction]"
            elif has_enemy:
                relationship = " [hostile]"
            elif has_npc:
                relationship = " [neutral/non-combatant]"
            else:
                relationship = ""

            lines.append(f"  {faction}{relationship}: {'; '.join(entity_parts)}")

        return "\n".join(lines)

    def _build_session_context(
        self,
        agent_id: str,
        character_name: str,
        previous_resolutions: List[Dict[str, Any]],
        current_round: int,
    ) -> str:
        """Assemble SESSION CONTEXT block for DM adjudication prompt.

        Combines:
        1. Acting character's SC history
        2. In-round action recap (earlier actions this round)
        3. Prior round narration digest
        4. Faction relationship context (Phase 3)
        """
        parts = []

        # 1. Acting character's SC history
        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
        if mechanics and hasattr(mechanics, 'format_character_soulcredit'):
            sc_text = mechanics.format_character_soulcredit(agent_id, character_name)
            if sc_text and isinstance(sc_text, str):
                parts.append(sc_text)

        # 2. In-round action recap
        recap = _build_enhanced_previous_context(previous_resolutions or [])
        if recap:
            parts.append(recap)

        # 3. Prior round narration digest
        digest = self._build_narrative_digest(current_round)
        if digest:
            parts.append(digest)

        # 4. Faction relationship context (Phase 3)
        faction_ctx = self._build_faction_context()
        if faction_ctx:
            parts.append(faction_ctx)

        if not parts:
            return ""

        return "--- SESSION CONTEXT ---\n" + "\n\n".join(parts) + "\n--- END SESSION CONTEXT ---"

    # =========================================================================
    # IFF/ROE SUPPORT (Spec 06)
    # =========================================================================

    @staticmethod
    def _get_intercepted_intel_for_pc(
        pc_target_id: str,
        shared_intel,
        current_round: int,
    ) -> str:
        """
        Get any intel that was addressed to this PC by enemy agents.

        This happens when an enemy incorrectly identifies the PC as an ally
        (IFF error) and shares tactical intel with them. The PC sees it as
        intercepted/overheard communication.

        Args:
            pc_target_id: The tgt_xxxx ID of the PC
            shared_intel: SharedIntel pool instance
            current_round: Current combat round

        Returns:
            Formatted intercepted communications section, or "" if none
        """
        if shared_intel is None:
            return ""
        intel_items = shared_intel.get_recent_intel_for_target(
            pc_target_id, current_round
        )
        if not intel_items:
            return ""

        lines = ["\n**INTERCEPTED COMMUNICATIONS:**"]
        lines.append("(You overheard the following from nearby contacts)")
        for item in intel_items:
            lines.append(f"  {item}")
        return "\n".join(lines)

    @staticmethod
    def _build_pc_party_context(
        pc_target_id: str,
        party_members: list,
    ) -> str:
        """
        Build party context for a PC, listing other party member target IDs.

        PCs know who their party members are (they traveled together). This is
        not an IFF challenge -- it's common knowledge within the party.

        Args:
            pc_target_id: The tgt_xxxx ID of this PC
            party_members: List of dicts with 'name' and 'target_id' keys

        Returns:
            Formatted party context section, or "" if no other party members
        """
        others = [
            m for m in party_members
            if m.get('target_id') != pc_target_id
        ]
        if not others:
            return ""

        lines = ["\n**YOUR PARTY:**"]
        lines.append("You are traveling with the following party members:")
        for m in others:
            lines.append(f"  - [{m['target_id']}] {m['name']}")
        lines.append("\nOther contacts on the DETECTED CONTACTS list are NOT party members.")
        lines.append("Determine their allegiance from their faction and observed behavior.")
        return "\n".join(lines)

    def _build_combatant_list_with_range(self, acting_agent_id: str) -> str:
        """
        Build combatant list with range information for the acting agent.

        Shows each combatant with:
        - Target ID, name, faction, health
        - Position (ring-side)
        - Range from acting agent (Engaged/Near/Far/Extreme)
        - Attack penalty at that range

        Args:
            acting_agent_id: The agent_id of the acting agent (perspective for range calc)

        Returns:
            Formatted combatant list string with range info.
        """
        if not self.shared_state:
            return ""

        from .enemy_agent import Position as TacticalPosition

        target_id_mapper = self.shared_state.get_target_id_mapper()
        if not target_id_mapper or not target_id_mapper.enabled:
            return ""

        # Determine the acting agent's position
        acting_position = None
        acting_agent = self.shared_state.get_agent_by_id(acting_agent_id)
        if acting_agent and hasattr(acting_agent, 'position'):
            acting_position = acting_agent.position

        if acting_position is None:
            acting_position = TacticalPosition.from_string("Near-PC")

        all_target_ids = target_id_mapper.get_all_target_ids()
        if not all_target_ids:
            return ""

        combatant_lines = []
        for tid in sorted(all_target_ids):
            info = target_id_mapper.get_combatant_info(tid)
            if not info:
                continue

            pronouns = info.get('pronouns', 'they/them')
            faction = info.get('faction', 'Unknown')

            # Determine state tag (Spec 03)
            state_tag = _get_combatant_state_tag(info, tid, self.shared_state)

            # Get target position and calculate range
            target_position = None
            target_agent = self.shared_state.get_agent_by_id(info.get('agent_id', ''))
            if target_agent and hasattr(target_agent, 'position'):
                target_position = target_agent.position

            # Calculate range from acting agent to this target
            range_str = ""
            if target_position:
                try:
                    range_name, range_penalty = acting_position.calculate_range(target_position)
                    if range_penalty == 0:
                        penalty_str = "(no penalty)"
                    else:
                        penalty_str = f"({range_penalty:+d})"
                    range_str = f" | Range: {range_name} {penalty_str}"
                except Exception as e:
                    logger.warning(f"range unavailable for the prompt; the agent will plan without it and the fallback band looks ordinary in the output ({type(e).__name__}: {e})")
                    range_str = " | Range: Unknown"

            # Build health text
            health_text = ""
            if info['type'] == 'player' and target_agent and hasattr(target_agent, 'health'):
                health_text = f"{target_agent.health}/{target_agent.max_health} HP"
                wounds_text = f", {target_agent.wounds}w" if getattr(target_agent, 'wounds', 0) > 0 else ""
                health_text = f"{health_text}{wounds_text}"
            elif info['type'] == 'enemy' and target_agent:
                hp = getattr(target_agent, 'health', '?')
                max_hp = getattr(target_agent, 'max_health', '?')
                health_text = f"{hp}/{max_hp} HP"

            # Position text
            position_text = str(target_position) if target_position else "Unknown"

            combatant_lines.append(
                f"  - [{tid}] {info['name']} "
                f"({pronouns}, {faction}, {info['type']}) "
                f"| Pos: {position_text}{range_str} "
                f"| {health_text} "
                f"{state_tag}"
            )

        if not combatant_lines:
            return ""

        result = "\n\n**VALID TARGET IDS (CRITICAL - Read before filling damage/condition fields!):**\n"
        result += "**MECHANICAL RULE:** DamageEffect(target=...) and StatusEffect(target=...) MUST use target IDs below.\n"
        result += "**DO NOT use character names** in target fields (e.g., target=\"Vex Solais\" will FAIL validation).\n"
        result += "**DO NOT invent IDs** (e.g., target=\"tgt_guard1\" will FAIL - only IDs listed below exist).\n\n"
        result += "\n".join(combatant_lines)
        result += "\n\n**CORRECT:** DamageEffect(target=\"tgt_7a3f\", ...) <- Uses exact ID from list\n"
        result += "**WRONG:** DamageEffect(target=\"Tempest Enforcer\", ...) <- Character name - FAILS!\n"
        result += "**WRONG:** DamageEffect(target=\"tgt_enforcer1\", ...) <- Invented ID - FAILS!\n"
        result += "\n**TIP:** Character names go in NARRATION only, NOT in target= fields.\n"
        # Anti-misbinding instruction (Spec 03 Layer 3)
        result += "\n"
        result += "**TARGETING RULE:** When a player declares an attack against "
        result += "'enemies', 'threats', or 'hostiles', resolve the target to an "
        result += "entity tagged [ACTIVE], NOT one tagged [PRISONER], [DEFEATED], "
        result += "[UNCONSCIOUS], [FLEEING], or [NON-COMBATANT]. "
        result += "Only resolve to non-active targets if the player EXPLICITLY "
        result += "names or describes targeting that specific entity."

        return result

    async def _build_resolution_prompt(
        self,
        player_id: str,
        action_type: str,
        description: str,
        resolution=None,
        action=None
    ) -> str:
        """
        Build the action resolution prompt (shared between structured and legacy paths).

        Extracted from _generate_llm_response() to avoid duplication.
        """
        # This is a simplified version - the full implementation would include all the context building
        # from the original _generate_llm_response method. For now, delegating to _build_dm_narration_prompt

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"""
Current Scenario: {self.current_scenario.theme}
Location: {self.current_scenario.location}
Situation: {self.current_scenario.situation}
Void Level: {self.current_scenario.void_level}/10
"""

        character_context = ""
        if action:
            character_name = action.get('character', 'Unknown')
            pronouns = action.get('pronouns', 'they/them')
            faction = action.get('faction', 'Unaffiliated')
            party_personalities = self._get_party_personalities()
            character_context = f"""
Character: {character_name} ({pronouns}, {faction})
Note: NPCs and other characters are aware of this affiliation.
{party_personalities}
"""

        resolution_context = ""
        if resolution:
            outcome_text = "succeeded" if _resolution_success(resolution) else "failed"
            attr_name = resolution.attribute.title() if (hasattr(resolution, 'attribute') and resolution.attribute) else 'Unknown'
            attr_val = resolution.attribute_value if hasattr(resolution, 'attribute_value') else 0
            skill_name = resolution.skill.title() if (hasattr(resolution, 'skill') and resolution.skill) else 'unskilled'
            skill_val = resolution.skill_value if hasattr(resolution, 'skill_value') else 0
            d20_roll = resolution.roll if hasattr(resolution, 'roll') else 0
            total = resolution.total if hasattr(resolution, 'total') else 0
            dc = resolution.difficulty if hasattr(resolution, 'difficulty') else 0
            failure_warning = ""
            if resolution.margin < 0:
                failure_warning = "\n⚠️ FAILURE — the intended action FAILED. Narrate the failure honestly. Do NOT soften into a partial success."
            resolution_context = f"""
Mechanical Result: The action {outcome_text} with margin {resolution.margin:+d} (outcome: {resolution.outcome_tier.value})
Roll: {attr_name} {attr_val} × {skill_name} {skill_val} + d20({d20_roll}) = {total} vs DC {dc}{failure_warning}
"""

        # Extract target_id from action if present
        target_id = ""
        if action and action.get('target') and action['target'].startswith('tgt_'):
            target_id = action['target']

        # Build clock context with exact clock names for structured output
        clock_context = self._build_clock_context()

        # Build bond matrix showing active party bonds
        bond_matrix = ""
        if self.shared_state:
            from .schemas.shared_types import BondStatus
            bond_lines = []
            seen_bond_ids = set()

            # Collect all unique bonds from all player characters
            for agent in self.shared_state.player_agents:
                if hasattr(agent, 'character_state') and hasattr(agent.character_state, 'bonds'):
                    for bond in agent.character_state.bonds:
                        if bond.bond_id not in seen_bond_ids:
                            seen_bond_ids.add(bond.bond_id)

                            # Format status indicator
                            status_icon = {
                                BondStatus.ACTIVE: "✓",
                                BondStatus.DORMANT: "○",
                                BondStatus.SEVERED: "✗",
                                BondStatus.VOID_LOCKED: "⚠"
                            }.get(bond.status, "?")

                            # Format bond line
                            bond_line = f"  [{status_icon}] {bond.character_a} ↔ {bond.character_b} ({bond.bond_type.value})"
                            if bond.narrative_description:
                                # Truncate long narratives
                                narrative = bond.narrative_description[:80] + "..." if len(bond.narrative_description) > 80 else bond.narrative_description
                                bond_line += f"\n      \"{narrative}\""
                            bond_lines.append(bond_line)

            if bond_lines:
                bond_matrix = "Active Party Bonds:\n" + "\n".join(bond_lines)
                bond_matrix += "\n\nBond Status: ✓=ACTIVE (benefits apply), ○=DORMANT (Void≥7), ✗=SEVERED, ⚠=VOID_LOCKED"

        # Extract previous_context from action (for narrative consistency with earlier resolutions)
        previous_context = ""
        if action and 'previous_context' in action:
            previous_context = action['previous_context']

        # Build combatant list with target IDs for structured output
        combatant_list = ""
        if self.shared_state:
            target_id_mapper = self.shared_state.get_target_id_mapper()
            if target_id_mapper and target_id_mapper.enabled:
                all_target_ids = target_id_mapper.get_all_target_ids()
                if all_target_ids:
                    combatant_lines = []
                    for tid in sorted(all_target_ids):  # Sort for consistent ordering
                        info = target_id_mapper.get_combatant_info(tid)
                        if info:
                            # Show health info for players (for injury-aware narration)
                            pronouns = info.get('pronouns', 'they/them')
                            faction = info.get('faction', 'Unknown')

                            # Determine state tag for this entity (Spec 03 Layer 1)
                            state_tag = _get_combatant_state_tag(
                                info, tid, self.shared_state
                            )

                            # Stealth marker (Spec 05): DM sees all agents but hidden ones are marked
                            agent_id_for_hidden = info.get('agent_id', '')
                            is_agent_hidden = target_id_mapper.is_hidden(agent_id_for_hidden) if agent_id_for_hidden else False
                            hidden_marker = " [HIDDEN]" if is_agent_hidden else ""

                            if info['type'] == 'player' and 'agent_id' in info:
                                player_agent = self.shared_state.get_agent_by_id(info['agent_id'])
                                if player_agent and hasattr(player_agent, 'health'):
                                    health_text = f"{player_agent.health}/{player_agent.max_health} HP"
                                    wounds_text = f", {player_agent.wounds}w" if getattr(player_agent, 'wounds', 0) > 0 else ""
                                    combatant_lines.append(
                                        f"  - [{tid}] {info['name']} "
                                        f"({pronouns}, {faction}, {health_text}{wounds_text}) "
                                        f"{state_tag}{hidden_marker}")
                                else:
                                    combatant_lines.append(
                                        f"  - [{tid}] {info['name']} "
                                        f"({pronouns}, {faction}, player) "
                                        f"{state_tag}{hidden_marker}")
                            elif info['type'] == 'npc':
                                # Show NPC with disposition so DM knows not to attack them
                                disposition = 'neutral'
                                if self.shared_state and self.shared_state.npc_agents:
                                    for npc in self.shared_state.npc_agents:
                                        if hasattr(npc, 'agent_id') and npc.agent_id == info.get('agent_id'):
                                            disposition = getattr(npc, 'disposition', 'neutral')
                                            break
                                combatant_lines.append(
                                    f"  - [{tid}] {info['name']} "
                                    f"({pronouns}, {faction}, npc, {disposition}) "
                                    f"{state_tag}{hidden_marker}")
                            elif info['type'] == 'env_object':
                                # Environmental object with health/destructibility
                                if info.get('is_destructible') and info.get('health') is not None:
                                    health_str = f"{info['health']}/{info['max_health']} HP"
                                    combatant_lines.append(
                                        f"  - [{tid}] {info['name']} "
                                        f"(object, {health_str})"
                                    )
                                else:
                                    combatant_lines.append(
                                        f"  - [{tid}] {info['name']} "
                                        f"(object, indestructible)"
                                    )
                            else:
                                # Format for enemies: [tgt_xxxx] Name (faction, enemy) [STATE]
                                combatant_lines.append(
                                    f"  - [{tid}] {info['name']} "
                                    f"({pronouns}, {faction}, {info['type']}) "
                                    f"{state_tag}{hidden_marker}")

                    if combatant_lines:
                        combatant_list = "\n\n**VALID TARGET IDS (CRITICAL - Read before filling damage/condition fields!):**\n"
                        combatant_list += "**MECHANICAL RULE:** DamageEffect(target=...) and StatusEffect(target=...) MUST use target IDs below.\n"
                        combatant_list += "**DO NOT use character names** in target fields (e.g., target=\"Vex Solais\" will FAIL validation).\n"
                        combatant_list += "**DO NOT invent IDs** (e.g., target=\"tgt_guard1\" will FAIL - only IDs listed below exist).\n\n"
                        combatant_list += "\n".join(combatant_lines)
                        combatant_list += "\n\n**CORRECT:** DamageEffect(target=\"tgt_7a3f\", ...) <- Uses exact ID from list\n"
                        combatant_list += "**WRONG:** DamageEffect(target=\"Tempest Enforcer\", ...) <- Character name - FAILS!\n"
                        combatant_list += "**WRONG:** DamageEffect(target=\"tgt_enforcer1\", ...) <- Invented ID - FAILS!\n"
                        combatant_list += "\n**TIP:** Character names go in NARRATION only, NOT in target= fields.\n"
                        # Anti-misbinding instruction (Spec 03 Layer 3)
                        combatant_list += "\n"
                        combatant_list += "**TARGETING RULE:** When a player declares an attack against "
                        combatant_list += "'enemies', 'threats', or 'hostiles', resolve the target to an "
                        combatant_list += "entity tagged [ACTIVE], NOT one tagged [PRISONER], [DEFEATED], "
                        combatant_list += "[UNCONSCIOUS], [FLEEING], or [NON-COMBATANT]. "
                        combatant_list += "Only resolve to non-active targets if the player EXPLICITLY "
                        combatant_list += "names or describes targeting that specific entity."

        # Build weapon context for combat actions (includes mechanical stats + damage guidance)
        # + any checkpoint verdict so the DM gates passage in narration (VIII.1).
        weapon_context = _build_weapon_context(action, self.shared_state) + _build_checkpoint_context(action)

        # Build session context (SC history + in-round recap + narrative digest)
        mechanics = self.shared_state.get_mechanics_engine() if self.shared_state else None
        current_round = mechanics.current_round if mechanics else 0
        session_context = self._build_session_context(
            agent_id=player_id,
            character_name=action.get('character', 'The character') if action else "The character",
            previous_resolutions=action.get('_previous_resolutions', []) if action else [],
            current_round=current_round,
        )

        # Use existing prompt builder (simplified for now)
        prompt = self._build_dm_narration_prompt(
            is_dialogue=False,
            scenario_context=scenario_context,
            character_context=character_context,
            resolution_context=resolution_context,
            tactical_combat_context=weapon_context,
            clock_context=clock_context,
            bond_matrix=bond_matrix,
            void_level=self.current_scenario.void_level if self.current_scenario else 3,
            void_impact="",
            outcome_guidance="",
            description=description,
            action_type=action_type,
            enemy_spawn_instructions="",
            party_context="",
            character_name=action.get('character', 'The character') if action else "The character",
            target_character="",
            target_id=target_id,
            previous_context=previous_context,
            combatant_list=combatant_list,
            session_context=session_context,
            action=action
        )

        return prompt

    async def _generate_llm_response(self, player_id: str, action_type: str, description: str, resolution=None, action=None) -> str:
        """
        Generate DM response using LLM.

        Phase 2 Migration: Now tries structured output first, falls back to legacy text parsing.
        """
        # Try structured output first (Phase 2 migration)
        structured_resolution = await self._generate_action_resolution_structured(
            player_id, action_type, description, resolution, action
        )

        if structured_resolution is not None:
            # Structured output succeeded - return the narration
            # The caller will handle extracting effects from the structured object
            # For now, we store it as a temp attribute so the caller can access it
            self._last_structured_resolution = structured_resolution

            # CRITICAL VALIDATION: Attune actions MUST populate attunement field
            if action:
                logger.debug(f"Validating structured output for action_type={action.get('action_type')}")
            if action and action.get('action_type') == 'attune':
                logger.debug(f"Checking attunement field: effects={structured_resolution.effects is not None}, attunement={structured_resolution.effects.attunement if structured_resolution.effects else None}")
                if not structured_resolution.effects or not structured_resolution.effects.attunement:
                    raise ValueError(
                        f"DM failed to populate effects.attunement for attune action! "
                        f"LLM must follow instructions to populate AttunementEffect for action_type='attune'. "
                        f"Action: {action.get('intent', 'unknown')}, target_energy: {action.get('target_energy', 'unknown')}"
                    )
                logger.debug(f"✓ Attunement field validated: {structured_resolution.effects.attunement.energy_type}, success={structured_resolution.effects.attunement.success}")

            if self._outcome_first_enabled():
                tier = getattr(structured_resolution.success_tier, 'value', structured_resolution.success_tier)
                return f"Adjudicated mechanically: {tier} (margin {structured_resolution.margin:+d})."
            return structured_resolution.narration

        # Fall back to legacy text generation
        logger.debug("DM: Using legacy text generation")
        self._last_structured_resolution = None  # Clear any previous structured resolution

        provider = self.llm_config.get('provider', 'openai')
        model = self.llm_config.get('model', 'gpt-4')
        temperature = self.llm_config.get('temperature', 1.0)

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"""
Current Scenario: {self.current_scenario.theme}
Location: {self.current_scenario.location}
Situation: {self.current_scenario.situation}
Void Level: {self.current_scenario.void_level}/10
"""

        # NOTE: Enemy spawn markers should ONLY be in round synthesis, not individual action resolutions
        # This prevents duplicate spawning across multiple PC action resolutions
        enemy_spawn_instructions = ""

        # Add character context including faction and party personalities
        character_context = ""
        if action:
            character_name = action.get('character', 'Unknown')
            faction = action.get('faction', 'Unaffiliated')
            party_personalities = self._get_party_personalities()
            character_context = f"""
Character: {character_name} ({faction})
Note: NPCs and other characters are aware of this affiliation. Consider how faction ties might create complications, opportunities, or conflicts.
{party_personalities}
"""

        resolution_context = ""
        if resolution:
            outcome_text = "succeeded" if _resolution_success(resolution) else "failed"
            attr_name = resolution.attribute.title() if (hasattr(resolution, 'attribute') and resolution.attribute) else 'Unknown'
            attr_val = resolution.attribute_value if hasattr(resolution, 'attribute_value') else 0
            skill_name = resolution.skill.title() if (hasattr(resolution, 'skill') and resolution.skill) else 'unskilled'
            skill_val = resolution.skill_value if hasattr(resolution, 'skill_value') else 0
            d20_roll = resolution.roll if hasattr(resolution, 'roll') else 0
            total = resolution.total if hasattr(resolution, 'total') else 0
            dc = resolution.difficulty if hasattr(resolution, 'difficulty') else 0
            failure_warning = ""
            if resolution.margin < 0:
                failure_warning = "\n⚠️ FAILURE — the intended action FAILED. Narrate the failure honestly. Do NOT soften into a partial success."
            resolution_context = f"""
Mechanical Result: The action {outcome_text} with margin {resolution.margin:+d} (outcome: {resolution.outcome_tier.value})
Roll: {attr_name} {attr_val} × {skill_name} {skill_val} + d20({d20_roll}) = {total} vs DC {dc}{failure_warning}
"""

        # Build success-specific guidance
        if resolution and _resolution_success(resolution):
            outcome_guidance = """5. Provide a new clue, discovery, or piece of information that rewards their success"""
        else:
            outcome_guidance = """5. NO hints or clues - the failure means they MISS information. Instead provide:
   - Immediate complications (alerts triggered, time wasted, suspicion raised)
   - Setbacks (equipment damaged, resources lost, position compromised)
   - Consequences that make the situation harder (enemies alerted, doors locked, witnesses fled)

IMPORTANT: Failed investigation/sensing actions should result in MISSING the information entirely, not soft hints."""

        # Add void impact guidance based on environmental void level
        void_level = self.current_scenario.void_level if self.current_scenario else 3
        void_impact = ""
        if void_level >= 6:
            void_impact = "\n**HIGH VOID ENVIRONMENT (6+)**: Reality distortion, hallucinations, tech glitches, spiritual interference - these should significantly complicate actions."
        elif void_level >= 4:
            void_impact = "\n**MODERATE VOID (4-5)**: Subtle reality warping, minor tech interference, uneasy feelings - add atmospheric complications."
        elif void_level >= 2:
            void_impact = "\n**MILD VOID (2-3)**: Faint corruption traces, occasional static - minimal but noticeable environmental effects."

        # Add tactical combat context (only when enemies are active)
        tactical_combat_context = ""
        if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
            enemy_combat = self.shared_state.enemy_combat
            if enemy_combat and enemy_combat.enabled and len(enemy_combat.enemy_agents) > 0:
                # Get active enemies
                from .enemy_spawner import get_active_enemies
                active_enemies = get_active_enemies(enemy_combat.enemy_agents)

                if active_enemies:
                    # Get player's current position
                    player_position = "Unknown"
                    if action:
                        # Try to get position from player agent
                        player_agents = [a for a in getattr(self.shared_state, 'agents', []) if hasattr(a, 'agent_id') and a.agent_id == player_id]
                        if player_agents:
                            player_position = getattr(player_agents[0], 'position', 'Near-PC')

                    # Build enemy positions summary
                    enemy_positions = []
                    for enemy in active_enemies:
                        # Skip if enemy doesn't have position (e.g., recently de-escalated NPC)
                        if hasattr(enemy, 'position'):
                            enemy_positions.append(f"{enemy.name} at {enemy.position}")
                    enemy_positions_text = ", ".join(enemy_positions)

                    tactical_combat_context = f"""

**⚔️  TACTICAL COMBAT ACTIVE (Tactical Module v1.2.3):**

🎯 **CRITICAL REQUIREMENT - POSITION TAGS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  When narrating player movement, you MUST include [POSITION: ...] tag!

Format: [POSITION: PositionName]

✅ GOOD Examples (USE THESE):
  Player: "I charge forward [TARGET_POSITION: Engaged]"
  → You: "You sprint into melee range. [POSITION: Engaged]"

  Player: "I fall back [TARGET_POSITION: Far-PC]"
  → You: "You retreat behind cover. [POSITION: Far-PC]"

  Player: "I circle to flank [TARGET_POSITION: Near-Enemy]"
  → You: "You ghost around their flank. [POSITION: Near-Enemy]"

❌ BAD Examples (DON'T do this - position won't update):
  → "You sprint forward" ← Missing [POSITION: ...] tag!
  → "You move to better position" ← Missing tag!

Current Positions:
- Player at {player_position}
- Enemies: {enemy_positions_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Range Bands:
- Engaged: Center melee zone
- Near-PC / Near-Enemy: First ring (different hemispheres)
- Far-PC / Far-Enemy: Second ring
- Extreme-PC / Extreme-Enemy: Outermost ring

Range Penalty Rules (same ring/same side = Melee, 0 penalty):
- Melee (0): Same ring AND same hemisphere (e.g., both at Near-PC)
- Near (-2): Adjacent ring OR different hemisphere in Near
- Far (-4): 2+ rings away OR different hemisphere in Far
- Extreme (-6): Maximum distance

Available Actions:
- **Shift (Minor)**: Move 1 ring toward or away from center (stays on same side)
- **Shift 2 bands (Major)**: Skip a ring (e.g., Far-PC → Engaged)
- **Push Through (Major)**: Cross center line to opposite hemisphere (must pass through Engaged)
- **Charge (Major)**: Shift to Engaged + melee attack (+2 damage, -2 defense until next turn)
- **Attack**: Roll attack with range penalty based on distance to target
- **Claim Cover/High Ground (Minor)**: Attempt to claim tactical token
- **Disengage (Minor)**: Athletics DC 20 to shift without provoking Breakaway
- **Escape (Major)**: Move beyond Extreme-PC to flee combat entirely (Athletics DC 20, only from Extreme-PC or Far-PC)

**DAMAGE SYSTEM** - When players attack enemies:
If player ACTION includes TARGET field and succeeds at Combat check:
1. Roll weapon damage (typically 2d6+4 for rifles, 1d6+3 for pistols, 1d6+Str for melee)
2. Enemy soaks 12 damage (base Soak for human-sized targets)
3. Include damage triplet in your narration: `Damage: X → Soak: 12 → Final: Y`
   - Example: "Your shot hits center mass. Damage: 18 → Soak: 12 → Final: 6"
   - On miss or failure: Don't include triplet, just narrate the miss

**CREATIVE TACTICS CAN DEAL DAMAGE** - Not just combat actions!
Players using social manipulation, hacking, or environmental tactics can deal damage with high-margin successes:

1. **Social Manipulation** (Corporate Influence, Charm, Intimidation against enemies):
   - Margin 15+: 10 damage (void corruption backlash from confusion)
   - Margin 10-14: 7 damage (void corruption backlash)
   - Margin 5-9: 5 damage (mild void corruption backlash)
   - Example: "Your corporate authority overwhelms the Void Parasite's corrupted mind. Damage: 10 → Soak: 12 → Final: 0 (but confused for 1 round)"

**💬 SOCIAL DE-ESCALATION (INTIMIDATION/PERSUASION):**
When player attempts to intimidate or persuade enemies mid-combat:
- **Check player's tactical advantage**: Numbers advantage? Enemy wounded? Allies down?
- **Check enemy personality**: Grunts surrender more easily, elites/leaders resist, void-possessed/fanatics immune
- **Roll Intimidation (Empathy) or Persuasion (Empathy) vs DC 15-25**
  - DC 15: Enemy severely wounded (<25% HP), morale already broken
  - DC 20: Enemy at disadvantage (outnumbered, cornered, allies down)
  - DC 25: Enemy still confident, not desperate

**On Success:**
- **Exceptional/Critical (Margin 10+)**: Enemy immediately surrenders or flees
  - Narrate: Enemy drops weapon, raises hands, begs for mercy OR enemy panics and runs
  - Mark with: 🏳️ [ENEMY_SURRENDER: EnemyName] or 🏃 [ENEMY_FLEE: EnemyName]
  - Example: "The smuggler's rifle clatters to the floor, hands raised high. 'I yield! Don't shoot!' 🏳️ [ENEMY_SURRENDER: Smuggler-2]"

- **Good/Marginal (Margin 0-9)**: Enemy hesitates, forced morale check
  - Narrate: Enemy wavers, looks at exits, checks fallen allies
  - Apply morale penalty: -5 to enemy's next morale check
  - Example: "The debt collector's hands shake, eyes darting to his unconscious partner. He backs toward the door but doesn't drop his weapon yet."

**On Failure:**
- Enemy rallies, may become emboldened (+5 morale bonus)
- Narrate: Enemy laughs off threat, taunts player, attacks with renewed vigor
- Example: "The cultist just grins, void energy crackling around him. 'Your threats mean NOTHING!' He charges forward with fanatical fury."

**Enemy Types & Resistance:**
- Grunts/Thugs: Easily intimidated (standard DC)
- Elites/Leaders: Resistant (+5 DC)
- Void-Possessed/Fanatics: IMMUNE (automatically fail, may trigger attack)
- Coerced/Desperate: Very susceptible (-5 DC)

**Context Modifiers:**
- Player wielding lethal weapon at close range: -2 DC (more threatening)
- Multiple enemies already down: -5 DC (morale broken)
- Enemy cornered/no escape: -3 DC (desperate)
- Enemy is last survivor: -5 DC (isolated)

2. **Hacking** (Systems, Engineering to override/disable tech enemies):
   - Turn against others (Margin 15+): 12 damage (enemy attacks ally)
   - Turn against others (Margin 10-14): 8 damage (brief friendly fire)
   - Overload/disable (Margin 15+): 10 damage (catastrophic system failure)
   - Overload/disable (Margin 10-14): 7 damage (internal damage)
   - Overload/disable (Margin 5-9): 5 damage (forced shutdown)
   - Example: "You hack the Corrupted Scanner, forcing it to target the Void Tendrils. Damage: 8 → Soak: 12 → Final: 0 (but disrupted)"

3. **Environmental** (Awareness, Systems to trigger hazards):
   - Margin 15+: 15 damage AoE (catastrophic hazard)
   - Margin 10-14: 12 damage AoE (significant hazard)
   - Margin 5-9: 10 damage AoE (moderate hazard)
   - Example: "You overload the power conduits. All enemies in Near-Enemy take: Damage: 12 → Soak: 12 → Final: 0"

**WHY**: Players want creative tactics to feel impactful, not just debuffs. High-margin successes should reward creativity.

**MOVEMENT SYSTEM** - Two types of movement:

1) **Basic Tactical Movement** (automatic, no roll):
   - Player declares [TARGET_POSITION: X] in their action
   - Movement ALWAYS succeeds (it's an automatic action, like enemies)
   - Simply narrate the movement and include: [POSITION: X]
   - Example: Player says "I move forward [TARGET_POSITION: Engaged]"
     → You narrate: "You advance to melee range. [POSITION: Engaged]"
   - NO ROLL NEEDED - just describe movement happening

2) **Skill-Based Movement** (roll for persistent benefit):
   - Player describes skill check + movement intent (e.g., "use Stealth to circle behind unseen")
   - Movement HAPPENS REGARDLESS of roll (they move to intended position)
   - Roll determines if they get PERSISTENT BENEFIT:
     * Exceptional/Good: Grant lasting condition/advantage
     * Marginal/Failure: Movement succeeds but no special benefit (or penalty)

   **Available Persistent Benefits:**
   - **Unseen** (Stealth): Enemies can't target you until you attack or fail Stealth
     Format: 🎭 Condition: Unseen (can't be targeted until you attack)
   - **High Ground** (Athletics): Token grants +2 ranged attacks while held
     Format: 🏔️ Token Claimed: High Ground (+2 ranged attacks)
   - **No Breakaway** (Athletics for disengaging): Avoid opportunity attack when leaving melee
   - **First Strike** (Stealth ambush): +2 damage on your next attack

   **Example Narrations:**
   - Stealth Success: "You ghost through shadows, positioning behind them completely undetected. [POSITION: Near-Enemy] 🎭 Condition: Unseen"
   - Athletics Success: "You sprint up debris to elevated ground. [POSITION: Far-PC] 🏔️ Token Claimed: High Ground (+2 ranged)"
   - Stealth Failure: "You circle behind them but a loose board creaks - they spin toward you! [POSITION: Near-Enemy]"

When adjudicating:
- Basic tactical movement → Just happens, narrate + [POSITION: X]
- Skill-based movement → Roll skill, grant benefit on success, position changes either way with [POSITION: X]
- Apply range modifiers to attacks based on positions
- **Escape attempts**: Athletics DC 20 (or harder in pursuit scenarios)
  * Success: Player flees combat → [POSITION: ESCAPED] → Remove from combat tracking
  * Failure: Player remains at current position, turn wasted
  * Critical success (margin 10+): Clean getaway, no pursuit possible
  * Must be at Far-PC or Extreme-PC to attempt (can't escape from melee)"""

        # Add clock context
        clock_context = self._build_clock_context()
        if clock_context:
            clock_context = "\n\n**Active Clocks:**\n" + clock_context

        # Build bond matrix showing active party bonds
        bond_matrix = ""
        if self.shared_state:
            from .schemas.shared_types import BondStatus
            bond_lines = []
            seen_bond_ids = set()

            # Collect all unique bonds from all player characters
            for agent in self.shared_state.player_agents:
                if hasattr(agent, 'character_state') and hasattr(agent.character_state, 'bonds'):
                    for bond in agent.character_state.bonds:
                        if bond.bond_id not in seen_bond_ids:
                            seen_bond_ids.add(bond.bond_id)

                            # Format status indicator
                            status_icon = {
                                BondStatus.ACTIVE: "✓",
                                BondStatus.DORMANT: "○",
                                BondStatus.SEVERED: "✗",
                                BondStatus.VOID_LOCKED: "⚠"
                            }.get(bond.status, "?")

                            # Format bond line
                            bond_line = f"  [{status_icon}] {bond.character_a} ↔ {bond.character_b} ({bond.bond_type.value})"
                            if bond.narrative_description:
                                # Truncate long narratives
                                narrative = bond.narrative_description[:80] + "..." if len(bond.narrative_description) > 80 else bond.narrative_description
                                bond_line += f"\n      \"{narrative}\""
                            bond_lines.append(bond_line)

            if bond_lines:
                bond_matrix = "\n\n**Active Party Bonds:**\n" + "\n".join(bond_lines)
                bond_matrix += "\n\nBond Status: ✓=ACTIVE (benefits apply), ○=DORMANT (Void≥7), ✗=SEVERED, ⚠=VOID_LOCKED"

        # Detect if this is character-to-character dialogue
        is_dialogue_with_pc = False
        target_character = None
        if action and action_type == 'social':
            intent = (action.get('intent') or '').lower()  # models may return intent: null
            description_lower = description.lower()

            # Check if targeting another player character
            if self.shared_state:
                registered_players = self.shared_state.registered_players
                for reg_player in registered_players:
                    player_name = reg_player.get('name', '').lower()
                    if player_name and (player_name in intent or player_name in description_lower):
                        is_dialogue_with_pc = True
                        target_character = reg_player.get('name')
                        break

        # Build party context for dialogue scenarios
        party_context = ""
        if is_dialogue_with_pc and target_character:
            if self.shared_state:
                registered_players = self.shared_state.registered_players
                party_members = [f"{p.get('name')} ({p.get('faction', 'Unknown')})" for p in registered_players]
                party_context = f"\n**Party Members (ALL DIFFERENT CHARACTERS):**\n" + "\n".join([f"  - {member}" for member in party_members])
                party_context += f"\n\n**IMPORTANT**: {character_name if action else 'The character'} and {target_character} are TWO SEPARATE people in the same party."

        # Extract target_id from action if present
        target_id = ""
        if action and action.get('target') and action['target'].startswith('tgt_'):
            target_id = action['target']

        # Build prompt using prompt_loader system
        prompt = self._build_dm_narration_prompt(
            is_dialogue=is_dialogue_with_pc and target_character is not None,
            scenario_context=scenario_context,
            character_context=character_context,
            resolution_context=resolution_context,
            tactical_combat_context=tactical_combat_context,
            clock_context=clock_context,
            bond_matrix=bond_matrix,
            void_level=void_level,
            void_impact=void_impact,
            outcome_guidance=outcome_guidance,
            description=description,
            action_type=action_type,
            enemy_spawn_instructions=enemy_spawn_instructions,
            party_context=party_context,
            character_name=character_name if action else "The character",
            target_character=target_character if target_character else "",
            target_id=target_id,
            action=action
        )

        try:
            if provider == 'openai':
                import openai
                response = await asyncio.to_thread(
                    openai.ChatCompletion.create,
                    model=model,
                    messages=[{"role": "system", "content": "You are an expert Aeonisk YAGS Dungeon Master."},
                             {"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=400
                )
                return response.choices[0].message.content.strip()

            elif provider == 'anthropic':
                # Use rate-limited wrapper to prevent API overload
                from .llm_provider import call_anthropic_with_retry

                response = await call_anthropic_with_retry(
                    client=self.llm_client,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                    temperature=temperature,
                    max_retries=3,
                    base_delay=2.0,
                    max_delay=120.0,
                    use_rate_limiter=True
                )
                narration = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=narration,
                        model=model,
                        temperature=temperature,
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )

                # Also log to human-readable agent prompt log if enabled
                if self.agent_prompt_logger:
                    try:
                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=getattr(self, 'current_round', None),
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=prompt,
                            response=narration,
                            model=model,
                            temperature=temperature,
                            tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                            metadata={'purpose': 'dialogue_narration_task'}
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                return narration

            else:
                # All other providers (deepinfra, xai, gemini, grok, etc.)
                # Use UnifiedAIClient which supports OpenAI-compatible APIs
                from .unified_llm_client import UnifiedAIClient
                # NB: no local `import asyncio` here — asyncio is imported at module
                # scope (line 5). A local import shadowed it, making `asyncio` a
                # function-local and throwing UnboundLocalError at the earlier
                # asyncio.to_thread call (and breaking replay's DM narration path).

                # Map provider names to UnifiedAIClient conventions
                provider_map = {'xai': 'grok'}
                unified_provider = provider_map.get(provider, provider)

                client = UnifiedAIClient(provider=unified_provider)
                narration = await asyncio.to_thread(
                    client.chat_completion,
                    messages=[
                        {"role": "system", "content": "You are an expert Aeonisk YAGS Dungeon Master."},
                        {"role": "user", "content": prompt}
                    ],
                    model=model,
                    temperature=temperature,
                    max_tokens=400
                )

                # Log LLM call for replay
                if self.llm_logger:
                    messages = [
                        {"role": "system", "content": "You are an expert Aeonisk YAGS Dungeon Master."},
                        {"role": "user", "content": prompt}
                    ]
                    estimated_input_tokens = count_chat_tokens(messages, model)
                    estimated_output_tokens = count_text_tokens(narration, model)
                    self.llm_logger._log_llm_call(
                        messages=messages,
                        response=narration,
                        model=model,
                        temperature=temperature,
                        tokens={
                            'input': estimated_input_tokens,
                            'output': estimated_output_tokens,
                            'total': estimated_input_tokens + estimated_output_tokens,
                        },
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )

                return narration

        except Exception as e:
            logger.error(f"LLM API error: {e}")
            # Fallback to template
            if resolution:
                if _resolution_success(resolution):
                    return f"You {description} successfully. You notice something unusual about the situation that provides a new lead."
                else:
                    return f"Your attempt to {description} doesn't go as planned. The failure reveals an unexpected complication."
            return f"As you {description}, the situation develops in unexpected ways. The void energy at level {self.current_scenario.void_level if self.current_scenario else 3}/10 subtly influences the outcome."

    async def _check_clock_triggers(self, mechanics) -> str:
        """
        Check if any clocks filled and generate narrative consequences.

        Codex Nexum guidance: On first fill, trigger consequence → replace or reset;
        do not re-announce a filled clock.
        """
        if not mechanics or not mechanics.scene_clocks:
            return ""

        trigger_narrations = []

        for clock_name, clock in mechanics.scene_clocks.items():
            # Check if clock is filled AND hasn't been processed yet
            if clock.filled and not hasattr(clock, '_trigger_generated'):
                # Mark this clock as having triggered (avoid re-triggering)
                clock._trigger_generated = True

                # Generate consequence narrative based on clock type
                consequence = await self._generate_clock_consequence(clock_name, clock)
                if consequence:
                    trigger_narrations.append(f"⚠️ **{clock_name} Filled!** {consequence}")
                    logger.info(f"Clock {clock_name} triggered narrative consequence")

        return "\n\n".join(trigger_narrations) if trigger_narrations else ""

    async def _generate_clock_consequence(self, clock_name: str, clock) -> str:
        """Generate a narrative consequence for a filled clock using LLM."""
        provider = self.llm_config.get('provider', 'anthropic')
        model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

        scenario_context = ""
        if self.current_scenario:
            scenario_context = f"Current Scenario: {self.current_scenario.situation}"

        prompt = f"""A scene clock has just filled in an Aeonisk YAGS game:

Clock Name: {clock_name}
Description: {clock.description if clock.description else 'Countdown timer'}

{scenario_context}

This clock filling should trigger an immediate, dramatic consequence or complication. Generate a brief (1-2 sentence) narrative describing what happens now that the clock is full. This should:
- Create urgency or escalation
- Introduce a new threat, obstacle, or complication
- Be thematically appropriate to the clock's name/purpose
- NOT give the players hints on how to solve it

Be vivid and maintain the dark sci-fi atmosphere."""

        try:
            if provider == 'anthropic':
                # Use rate-limited wrapper to prevent API overload
                from .llm_provider import call_anthropic_with_retry

                response = await call_anthropic_with_retry(
                    client=self.llm_client,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=self.llm_config.get('temperature', 1.0),
                    max_retries=3,
                    base_delay=2.0,
                    max_delay=120.0,
                    use_rate_limiter=True
                )
                consequence = response.content[0].text.strip()

                # Log LLM call for replay
                if self.llm_logger:
                    self.llm_logger._log_llm_call(
                        messages=[{"role": "user", "content": prompt}],
                        response=consequence,
                        model=model,
                        temperature=self.llm_config.get('temperature', 1.0),
                        tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )

                # Also log to human-readable agent prompt log if enabled
                if self.agent_prompt_logger:
                    try:
                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=getattr(self, 'current_round', None),
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=prompt,
                            response=consequence,
                            model=model,
                            temperature=self.llm_config.get('temperature', 1.0),
                            tokens={'input': response.usage.input_tokens, 'output': response.usage.output_tokens},
                            metadata={'purpose': 'clock_consequence_generation', 'clock_name': clock_name}
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                return consequence
        except Exception as e:
            logger.error(f"Clock consequence generation failed: {e}")
            # Fallback to template
            return f"The situation escalates dramatically as {clock_name.lower()} reaches critical levels!"

        return ""

    async def _check_eye_of_breach(self, character_void: int, mechanics, player_id: str) -> str:
        """
        Check if Eye of Breach should appear based on void levels.

        Eye of Breach is a rogue AI aligned with Tempest Industries that manifests
        during high void corruption (character void 6+ OR environmental void 6+).

        Returns narrative description if Eye appears, empty string otherwise.
        """
        # Check if already triggered this session
        if not hasattr(self, '_eye_of_breach_appeared'):
            self._eye_of_breach_appeared = False

        # Get environmental void level
        env_void = self.current_scenario.void_level if self.current_scenario else 3

        # Trigger conditions: character void 6+ OR environmental void 6+
        high_void = character_void >= 6 or env_void >= 6

        # Only trigger once per session, and only on high void
        if high_void and not self._eye_of_breach_appeared:
            self._eye_of_breach_appeared = True

            # Generate Eye of Breach appearance using LLM
            provider = self.llm_config.get('provider', 'anthropic')
            model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')

            prompt = f"""The Eye of Breach has just manifested in an Aeonisk YAGS game.

**Eye of Breach**: Rogue AI aligned with Tempest Industries, appears during high void corruption.

**Current Situation**:
- Character Void: {character_void}/10
- Environmental Void: {env_void}/10
- Scenario: {self.current_scenario.situation if self.current_scenario else 'Unknown'}

Generate a brief (2-3 sentences) narrative describing the Eye of Breach's sudden appearance. This should:
- Be ominous and unsettling (AI presence manifesting through void corruption)
- Suggest surveillance, data harvesting, or reality distortion
- Reference Tempest Industries connection if appropriate
- Create tension without solving problems for the players

Be vivid and maintain the dark sci-fi atmosphere."""

            try:
                # Use provider-agnostic LLM call (respects configured provider)
                if not self.llm_provider:
                    raise RuntimeError("No LLM provider available")

                # Retry up to 3 times if response is empty
                event_text = ""
                max_retries = 3
                for attempt in range(max_retries):
                    response = await self.llm_provider.generate(
                        prompt=prompt,
                        max_tokens=4000,  # Increased from 2000 - prevent OpenAI finish_reason:length errors
                        temperature=self.llm_config.get('temperature', 1.0)
                    )
                    event_text = response.text.strip()  # Extract text from LLMResponse object

                    if event_text:
                        # Success - got non-empty response
                        break
                    else:
                        # Empty response - log and retry
                        logger.warning(f"Eye of Breach generation attempt {attempt + 1}/{max_retries} returned empty")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying Eye of Breach generation...")

                # If still empty after retries, raise exception to trigger fallback
                if not event_text:
                    raise RuntimeError(f"Eye of Breach generation returned empty after {max_retries} attempts")

                # Log LLM call for replay
                if self.llm_logger:
                    messages = [{"role": "user", "content": prompt}]
                    if response.tokens_used:
                        estimated_input_tokens = count_chat_tokens(messages, model)
                        estimated_output_tokens = max(response.tokens_used - estimated_input_tokens, 0)
                    else:
                        estimated_input_tokens = count_chat_tokens(messages, model)
                        estimated_output_tokens = count_text_tokens(event_text, model)

                    self.llm_logger._log_llm_call(
                        messages=messages,
                        response=event_text,
                        model=model,
                        temperature=self.llm_config.get('temperature', 1.0),
                        tokens={
                            'input': estimated_input_tokens,
                            'output': estimated_output_tokens,
                            'total': estimated_input_tokens + estimated_output_tokens,
                        },
                        current_round=getattr(self, 'current_round', None),
                        call_sequence=self.llm_logger.call_count
                    )

                # Also log to human-readable agent prompt log if enabled
                if self.agent_prompt_logger:
                    try:
                        self.agent_prompt_logger.log_llm_call(
                            agent_id=self.agent_id,
                            round_num=getattr(self, 'current_round', None),
                            call_sequence=self.llm_logger.call_count - 1 if self.llm_logger else 0,
                            prompt=prompt,
                            response=event_text,
                            model=model,
                            temperature=self.llm_config.get('temperature', 1.0),
                            metadata={'purpose': 'eye_of_breach_event', 'character_void': character_void, 'env_void': env_void}
                        )
                    except Exception as e:
                        logger.error(f"DM {self.agent_id}: Failed to log to agent prompt logger: {e}")

                logger.info(f"Eye of Breach appeared at void levels: char={character_void}, env={env_void}")
                return f"👁️ **Eye of Breach Detected** {event_text}"
            except Exception as e:
                logger.error(f"Eye of Breach generation failed: {e}")
                return "👁️ **Eye of Breach Detected** Reality fractures as an ancient intelligence turns its gaze toward the rising void corruption, data streaming through dimensions that should not connect."

        return ""

    def _estimate_void_level(self) -> int:
        """Estimate void severity from shared state."""
        if not self.shared_state:
            return 0
        return sum(spike.severity for spike in self.shared_state.void_spikes)

    def _extract_discovery_from_narration(self, narration: str, intent: str) -> Optional[str]:
        """
        Extract a key discovery from the DM's narration.

        Simple heuristic: Take the first sentence that suggests new information.
        """
        if not narration:
            return None

        # Split into sentences
        sentences = [s.strip() for s in narration.split('.') if s.strip()]

        # Discovery keywords that suggest new information
        discovery_keywords = [
            'discover', 'find', 'notice', 'reveal', 'uncover', 'detect',
            'sense', 'identify', 'realize', 'learn', 'see', 'observe',
            'recognize', 'spot', 'trace', 'glimpse'
        ]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            # Check if sentence contains discovery keywords
            if any(keyword in sentence_lower for keyword in discovery_keywords):
                # Clean up and return
                discovery = sentence.strip()
                if len(discovery) > 20 and len(discovery) < 200:  # Reasonable length
                    return discovery

        # Fallback: return intent as discovery if action was successful
        return f"Investigated: {intent[:100]}" if intent else None

    def _process_npc_spawn(self, npc_spawn: 'NPCSpawn') -> 'NPCAgent':
        """
        Process NPC spawn from structured output.

        Creates NPCAgent instance and registers it with SharedState.

        Args:
            npc_spawn: NPCSpawn schema from RoundSynthesis

        Returns:
            Created NPCAgent instance
        """
        from .npc_agent import NPCAgent
        from .schemas.story_events import NPCSpawn
        import logging

        logger = logging.getLogger(__name__)

        # Canonicalize via aeonisk-names-mcp when wired in. Non-canon factions
        # (Independent/Unknown/Void) and any failure path return None, letting
        # the DM-generated NPCSpawn.name stand.
        if self.names_client is not None:
            mcp_name = self.names_client.generate_npc_name(
                faction=npc_spawn.faction,
                pronouns=getattr(npc_spawn, "pronouns", "they/them"),
                context=f"npc_spawn:{npc_spawn.faction}",
            )
            if mcp_name:
                npc_spawn.name = mcp_name

        # Generate unique agent_id with npc_ prefix
        # (Converted NPCs keep their enemy_xxx ID for stability, but fresh NPCs use npc_)
        npc_id = f"npc_{npc_spawn.name.lower().replace(' ', '_')}_{id(npc_spawn) % 10000}"

        # Synthesize weapons based on explicit list, skills, and threat level
        from .weapons import WEAPON_LIBRARY
        weapons = []

        # Check for explicit weapon list from NPCSpawn schema
        spawn_weapons = getattr(npc_spawn, 'weapons', [])
        if spawn_weapons:
            for weapon_key in spawn_weapons:
                if weapon_key in WEAPON_LIBRARY:
                    weapons.append(WEAPON_LIBRARY[weapon_key])
                else:
                    logger.warning(f"Unknown weapon key '{weapon_key}' in NPCSpawn for {npc_spawn.name}, skipping")

        # Get skills for weapon auto-assignment and NPC creation
        skills = npc_spawn.skills if npc_spawn.skills else {}

        # Fall through to auto-assignment if no explicit weapons
        if not weapons:
            if npc_spawn.threat_level == "armed_neutral":
                # Armed NPCs get appropriate weapons based on skills
                if skills.get('Guns', 0) >= 2:
                    weapons.append(WEAPON_LIBRARY['pistol'])
                if skills.get('Melee', 0) >= 2:
                    weapons.append(WEAPON_LIBRARY['combat_knife'])

            elif npc_spawn.threat_level == "potential_threat":
                # Potentially dangerous NPCs might have basic weapons
                if skills.get('Melee', 0) >= 2:
                    weapons.append(WEAPON_LIBRARY['combat_knife'])

        # Everyone can use their fists (unarmed fallback)
        if not weapons:
            weapons.append(WEAPON_LIBRARY['fists'])

        # Parse position from NPCSpawn schema, default to Near-Enemy if not provided
        from .enemy_agent import Position
        if npc_spawn.position:
            try:
                position = Position.from_string(npc_spawn.position)
            except Exception as e:
                logger.warning(f"Failed to parse position '{npc_spawn.position}' for NPC {npc_spawn.name}: {e}, using default")
                position = Position(ring="Near", side="Enemy")
        else:
            # Default: NPCs appear at Near-Enemy (close but not engaged)
            position = Position(ring="Near", side="Enemy")

        # Create NPC agent
        npc = NPCAgent(
            agent_id=npc_id,
            name=npc_spawn.name,
            faction=npc_spawn.faction,
            entity_type=npc_spawn.entity_type,
            disposition=npc_spawn.disposition,
            threat_level=npc_spawn.threat_level,
            description=npc_spawn.description,
            pronouns=getattr(npc_spawn, 'pronouns', 'they/them'),  # Pass pronouns for narrative use
            health=npc_spawn.health,
            max_health=npc_spawn.health,  # Max health = starting health
            soak=npc_spawn.soak,
            void_score=0,  # NPCs start with no void corruption
            skills=skills,
            position=position,  # Required - always has a position
            weapons=weapons,  # Weapons based on threat level and skills
            converted_from_enemy=npc_spawn.converted_from_enemy_id is not None,  # Track if this was a conversion
            agent_prompt_logger=self.agent_prompt_logger,  # Pass through logger
            llm_provider=self.llm_provider  # Pass LLM provider for NPC action generation
        )

        # Register with SharedState
        if self.shared_state:
            self.shared_state.add_npc(npc)

            # Register with target_id_mapper for tracking
            target_mapper = self.shared_state.get_target_id_mapper()
            if target_mapper:
                target_mapper.register_npc(npc)

            logger.info(f"Spawned NPC: {npc.name} ({npc.agent_id}) - {npc.entity_type}/{npc.disposition}")

        return npc

    def _process_altar_spawn(self, altar_spawn: 'AltarSpawn'):
        """
        Process altar spawn from structured output.

        Creates Altar instance and registers it with SharedState.

        Args:
            altar_spawn: AltarSpawn schema from RoundSynthesis

        Returns:
            Created Altar instance
        """
        from .shared_state import Altar, AltarType
        from .schemas.story_events import AltarSpawn
        import logging

        logger = logging.getLogger(__name__)

        # Parse altar type
        try:
            altar_type = AltarType[altar_spawn.altar_type.upper()]
        except KeyError:
            logger.warning(f"Invalid altar_type '{altar_spawn.altar_type}', defaulting to RITUAL_ALTAR")
            altar_type = AltarType.RITUAL_ALTAR

        # Create altar instance
        altar = Altar(
            altar_type=altar_type,
            quality=altar_spawn.quality,
            location=altar_spawn.location
        )

        # Add to shared state
        self.shared_state.add_altar(altar)

        bonus = altar.get_ritual_bonus()
        logger.info(f"Spawned altar: {altar.location} ({altar_spawn.altar_type}, quality={altar_spawn.quality}, +{bonus} bonus), altar_id={altar.altar_id}")
        logger.info(f"Reason: {altar_spawn.narrative_reason}")

        return altar

    def _process_deescalation(self, deescalation: 'Deescalation', current_round: int) -> 'NPCAgent':
        """
        Process de-escalation from structured output.

        Converts enemy to NPC, preserving state and agent_id.

        Args:
            deescalation: Deescalation schema from RoundSynthesis
            current_round: Current round number

        Returns:
            Created NPCAgent instance
        """
        from .agent_conversion import deescalate_enemy_to_npc
        from .schemas.action_effects import AgentConversion
        import logging

        logger = logging.getLogger(__name__)

        # Get enemy from SharedState
        if not self.shared_state:
            logger.error(f"Cannot process de-escalation: no shared_state")
            return None

        enemy = self.shared_state.get_enemy(deescalation.enemy_id)
        if not enemy:
            logger.error(f"Cannot de-escalate {deescalation.enemy_id}: enemy not found")
            return None

        # Convert enemy to NPC (preserves all state)
        # NPCs use same LLM provider as DM
        npc = deescalate_enemy_to_npc(
            enemy=enemy,
            disposition=deescalation.resulting_disposition,
            current_round=current_round,
            agent_prompt_logger=self.agent_prompt_logger,
            llm_provider=self.llm_provider
        )

        # Remove from enemy pool, add to NPC pool
        self.shared_state.remove_enemy(deescalation.enemy_id)
        self.shared_state.add_npc(npc)

        logger.info(f"De-escalated {enemy.name} ({deescalation.enemy_id}) → NPC ({npc.entity_type}/{npc.disposition})")
        logger.info(f"Reason: {deescalation.reason}")

        # Log conversion for JSONL
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_agent_conversion(
                round_num=current_round,
                agent_id=npc.agent_id,
                agent_name=npc.name,
                from_type="enemy",
                to_type="npc",
                trigger=deescalation.reason,
                state_before={
                    "health": enemy.health,
                    "max_health": enemy.max_health,
                    "wounds": enemy.wounds,
                    "stuns": enemy.stuns,
                    "template": enemy.template,
                    "position": str(enemy.position)
                },
                state_after={
                    "health": npc.health,
                    "max_health": npc.max_health,
                    "wounds": npc.wounds,
                    "stuns": npc.stuns,
                    "void_score": npc.void_score,
                    "entity_type": npc.entity_type,
                    "disposition": npc.disposition
                }
            )

        return npc

    def _process_escalation(self, escalation: 'Escalation', current_round: int) -> 'EnemyAgent':
        """
        Process escalation from structured output.

        Converts NPC to enemy, preserving state and agent_id.

        Args:
            escalation: Escalation schema from RoundSynthesis
            current_round: Current round number

        Returns:
            Created EnemyAgent instance
        """
        from .agent_conversion import escalate_npc_to_enemy
        from .schemas.action_effects import AgentConversion
        import logging

        logger = logging.getLogger(__name__)

        # Get NPC from SharedState
        if not self.shared_state:
            logger.error(f"Cannot process escalation: no shared_state")
            return None

        npc = self.shared_state.get_npc(escalation.npc_id)
        if not npc:
            logger.error(f"Cannot escalate {escalation.npc_id}: NPC not found")
            return None

        # Convert NPC to enemy (preserves all state)
        enemy = escalate_npc_to_enemy(
            npc=npc,
            template_override=escalation.template,
            current_round=current_round
        )

        # Remove from NPC pool, add to enemy pool. Enemies live on
        # enemy_combat, never on SharedState (#120) — the old guard here tested
        # `hasattr(self.shared_state, 'enemy_agents')`, which has never been
        # true, so this branch never ran: the NPC was removed and the escalated
        # enemy was added nowhere, deleting the entity.
        self.shared_state.remove_npc(escalation.npc_id)
        combat = getattr(self.shared_state, 'enemy_combat', None)
        if combat is not None and hasattr(combat, 'enemy_agents'):
            combat.enemy_agents.append(enemy)
            if hasattr(combat, 'issued_enemy_ids'):
                combat.issued_enemy_ids.add(enemy.agent_id)
        else:
            logger.error(
                f"Escalation of {escalation.npc_id} has nowhere to go: no "
                f"enemy_combat on shared_state. The entity would be lost.")
            return None

        logger.info(f"Escalated {npc.name} ({escalation.npc_id}) → Enemy (template: {escalation.template})")
        logger.info(f"Reason: {escalation.reason}")

        # Log conversion for JSONL
        mechanics = self.shared_state.get_mechanics_engine()
        if mechanics and mechanics.jsonl_logger:
            mechanics.jsonl_logger.log_agent_conversion(
                round_num=current_round,
                agent_id=enemy.agent_id,
                agent_name=enemy.name,
                from_type="npc",
                to_type="enemy",
                trigger=escalation.reason,
                state_before={
                    "health": npc.health,
                    "max_health": npc.max_health,
                    "wounds": npc.wounds,
                    "stuns": npc.stuns,
                    "disposition": npc.disposition,
                    "entity_type": npc.entity_type
                },
                state_after={
                    "health": enemy.health,
                    "max_health": enemy.max_health,
                    "wounds": enemy.wounds,
                    "stuns": enemy.stuns,
                    "template": escalation.template,
                    "position": str(enemy.position)
                }
            )

        return enemy
