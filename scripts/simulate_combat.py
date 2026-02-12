#!/usr/bin/env python3
"""
Monte Carlo Combat Simulation for Aeonisk YAGS.

Simulates combat scenarios using YAGS formulas to evaluate balance
across different damage models. Extracts party/enemy data from session
JSONL files or session config JSON.

Usage:
    # From session JSONL (preferred — uses actual enemies from that game)
    python scripts/simulate_combat.py multiagent_output/.../session_xxx.jsonl

    # With options
    python scripts/simulate_combat.py session.jsonl --runs 10000 --model all --seed 42

    # From session config (uses initial_enemies only)
    python scripts/simulate_combat.py --config scripts/session_configs/experiment/session_config_combat_ambush.json

    # Sensitivity sweep
    python scripts/simulate_combat.py session.jsonl --sweep
"""

import argparse
import copy
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# =============================================================================
# WEAPON/ARMOR LOOKUPS (inline to avoid import complexity)
# =============================================================================

# Weapon damage values by key (from weapons.py)
WEAPON_DAMAGE: Dict[str, int] = {
    "fists": 0, "shock_baton": 3, "baton": 5, "combat_knife": 6,
    "void_blade": 8, "ritual_blade": 7, "pistol": 4, "rifle": 5,
    "sniper_rifle": 8, "heavy_weapon": 6, "shotgun": 6, "tranq_gun": 2,
    "stun_gun": 4, "grenade": 10, "stun_grenade": 8, "hacking_toolkit": 3,
    "custom_energy_weapon": 5, "shrike_cannon": 6, "mnemonic_blade": 8,
    "spark_pulse_rifle": 6, "ash_pulse_pike": 7, "hollowed_repeater": 4,
    "union_heavy_pistol": 4, "breach_hammer": 10, "dripshock_baton": 2,
    "sparkspike_dagger": 7, "wraithroot_vineblade": 5, "oathpiercer_carbine": 4,
    "debtbreaker_sidearm": 4, "drip_veil_projector": 2, "ritual_staff": 5,
    "beat_up_pistol": 3, "compact_emp_pistol": 3, "void_cloak": 4,
}

WEAPON_ATTACK: Dict[str, int] = {
    "fists": 0, "shock_baton": 2, "baton": 2, "combat_knife": 3,
    "void_blade": 4, "ritual_blade": 3, "pistol": 0, "rifle": 0,
    "sniper_rifle": 2, "heavy_weapon": -1, "shotgun": 1, "tranq_gun": 0,
    "stun_gun": 0, "grenade": 0, "stun_grenade": 0, "hacking_toolkit": -1,
    "custom_energy_weapon": 1, "shrike_cannon": 1, "mnemonic_blade": 4,
    "spark_pulse_rifle": 2, "ash_pulse_pike": 3, "hollowed_repeater": 0,
    "union_heavy_pistol": 0, "breach_hammer": 1, "dripshock_baton": 2,
    "sparkspike_dagger": 4, "wraithroot_vineblade": 3, "oathpiercer_carbine": 0,
    "debtbreaker_sidearm": 0, "drip_veil_projector": -1, "ritual_staff": 1,
    "beat_up_pistol": -1, "compact_emp_pistol": 0, "void_cloak": 1,
}

WEAPON_SKILL: Dict[str, str] = {
    "fists": "Brawl", "shock_baton": "Brawl", "baton": "Melee",
    "combat_knife": "Melee", "void_blade": "Melee", "ritual_blade": "Melee",
    "pistol": "Guns", "rifle": "Guns", "sniper_rifle": "Guns",
    "heavy_weapon": "Guns", "shotgun": "Guns", "tranq_gun": "Guns",
    "stun_gun": "Guns", "grenade": "Throw", "stun_grenade": "Throw",
    "hacking_toolkit": "Guns", "custom_energy_weapon": "Guns",
    "shrike_cannon": "Guns", "mnemonic_blade": "Melee",
    "spark_pulse_rifle": "Guns", "ash_pulse_pike": "Melee",
    "hollowed_repeater": "Guns", "union_heavy_pistol": "Guns",
    "breach_hammer": "Melee", "dripshock_baton": "Brawl",
    "sparkspike_dagger": "Melee", "wraithroot_vineblade": "Melee",
    "oathpiercer_carbine": "Guns", "debtbreaker_sidearm": "Guns",
    "drip_veil_projector": "Guns", "ritual_staff": "Melee",
    "beat_up_pistol": "Guns", "compact_emp_pistol": "Guns", "void_cloak": "Melee",
}

WEAPON_TYPE: Dict[str, str] = {
    "fists": "stun", "shock_baton": "stun", "baton": "mixed",
    "combat_knife": "mixed", "void_blade": "wound", "ritual_blade": "mixed",
    "pistol": "wound", "rifle": "wound", "sniper_rifle": "wound",
    "heavy_weapon": "wound", "shotgun": "wound", "tranq_gun": "stun",
    "stun_gun": "stun", "grenade": "wound", "stun_grenade": "stun",
    "hacking_toolkit": "stun", "custom_energy_weapon": "wound",
    "shrike_cannon": "wound", "mnemonic_blade": "wound",
    "spark_pulse_rifle": "wound", "ash_pulse_pike": "wound",
    "hollowed_repeater": "wound", "union_heavy_pistol": "wound",
    "breach_hammer": "wound", "dripshock_baton": "stun",
    "sparkspike_dagger": "wound", "wraithroot_vineblade": "mixed",
    "oathpiercer_carbine": "wound", "debtbreaker_sidearm": "wound",
    "drip_veil_projector": "stun", "ritual_staff": "mixed",
    "beat_up_pistol": "wound", "compact_emp_pistol": "stun", "void_cloak": "stun",
}

ARMOR_SOAK: Dict[str, int] = {
    "none": 0, "robes": 1, "light_armor": 3, "medium_armor": 5,
    "heavy_armor": 8, "tactical_vest": 4,
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Combatant:
    """A combatant in the simulation (PC or enemy)."""
    name: str
    hp: int
    max_hp: int
    soak: int
    wounds: int = 0
    stuns: int = 0

    # Attack stats
    strength: int = 3
    attack_attr: int = 3  # Perception for guns, Dexterity for melee, Agility for brawl
    attack_skill: int = 3
    weapon_attack: int = 0
    weapon_damage: int = 4
    weapon_type: str = "wound"  # "stun", "wound", "mixed"

    # For enemy damage formula
    is_enemy: bool = False

    def is_defeated(self) -> bool:
        return self.hp <= 0 or self.stuns >= 6

    def clone(self) -> 'Combatant':
        return Combatant(
            name=self.name, hp=self.hp, max_hp=self.max_hp, soak=self.soak,
            wounds=self.wounds, stuns=self.stuns,
            strength=self.strength, attack_attr=self.attack_attr,
            attack_skill=self.attack_skill, weapon_attack=self.weapon_attack,
            weapon_damage=self.weapon_damage, weapon_type=self.weapon_type,
            is_enemy=self.is_enemy,
        )


@dataclass
class CombatResult:
    """Result of a single combat simulation."""
    outcome: str  # "win", "loss", "draw"
    rounds: int
    pc_kills: int  # PCs defeated
    enemy_kills: int  # Enemies defeated
    total_enemies: int


@dataclass
class MonteCarloResult:
    """Aggregate results from multiple simulation runs."""
    model: str
    total_runs: int
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total_enemy_kills: int = 0
    total_rounds: int = 0
    total_enemies: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_runs if self.total_runs else 0

    @property
    def avg_kills(self) -> float:
        return self.total_enemy_kills / self.total_runs if self.total_runs else 0

    @property
    def avg_rounds(self) -> float:
        return self.total_rounds / self.total_runs if self.total_runs else 0


@dataclass
class SimConfig:
    """Configuration for a simulation run."""
    runs: int = 10000
    seed: int = 42
    max_rounds: int = 20
    model: str = "all"  # "llm", "mechanical", "margin", "dm_modifier", "all"


# =============================================================================
# FORMULA FUNCTIONS
# =============================================================================

def calc_pc_hp(size: int = 5, endurance: int = 3) -> int:
    """PC HP = (Size*2) + Endurance + 13."""
    return (size * 2) + endurance + 13


def calc_pc_soak(size: int = 5, agility: int = 3, endurance: int = 3) -> int:
    """PC Soak = Size + Agility + Endurance - 5 + 4 (combat balance)."""
    return size + agility + endurance - 5 + 4


def calc_enemy_soak(size: int = 5, agility: int = 3, endurance: int = 3,
                     armor_soak: int = 0) -> int:
    """Enemy Soak = Size + Agi + End - 5 + 4 + armor_soak_bonus."""
    return size + agility + endurance - 5 + 4 + armor_soak


# =============================================================================
# ATTACK & DAMAGE ROLLS
# =============================================================================

def roll_enemy_attack(attr: int, skill: int, weapon_attack: int,
                       d20: int, flanking: bool = True) -> Tuple[bool, int]:
    """
    Enemy attack roll: (attr*skill) + weapon_attack + d20 ± flanking vs DC 15.

    Returns (hit, margin).
    """
    flank_mod = 2 if flanking else -2
    total = (attr * skill) + weapon_attack + d20 + flank_mod
    dc = 15
    return total >= dc, max(0, total - dc)


def roll_enemy_damage(strength: int, weapon_damage: int, d20: int) -> int:
    """Enemy damage = (Str + weapon.damage + d20) * 0.85."""
    return int((strength + weapon_damage + d20) * 0.85)


def roll_pc_attack(attr: int, skill: int, weapon_attack: int,
                    d20: int) -> Tuple[bool, int]:
    """
    PC attack roll: (attr*skill) + weapon_attack + d20 vs DC 15.

    No flanking modifier for PCs (they choose targets).
    Returns (hit, margin).
    """
    total = (attr * skill) + weapon_attack + d20
    dc = 15
    return total >= dc, max(0, total - dc)


# =============================================================================
# DAMAGE MODELS
# =============================================================================

def damage_model_llm(rng: random.Random = None, mean: float = 9.0,
                      std: float = 3.0) -> int:
    """Model A: Draw from observed LLM distribution (mean=9, std=3)."""
    if rng is None:
        rng = random.Random()
    return max(0, int(rng.gauss(mean, std)))


def damage_model_mechanical(strength: int, weapon_damage: int, d20: int,
                             target_soak: int) -> int:
    """Model B: Symmetric mechanical. Str + weapon.damage + d20 - target_soak."""
    return max(0, strength + weapon_damage + d20 - target_soak)


def damage_model_margin(weapon_damage: int, attack_margin: int, d20: int,
                         target_soak: int) -> int:
    """Model C: Margin bonus. weapon.damage + (margin//3) + d20 - target_soak."""
    bonus = attack_margin // 3
    return max(0, weapon_damage + bonus + d20 - target_soak)


def damage_model_dm_modifier(strength: int, weapon_damage: int, d20: int,
                               target_soak: int, dm_mod: int = 0) -> int:
    """Model D: Mechanical + DM modifier. Str + wpn + d20 + dm_mod - soak."""
    return max(0, strength + weapon_damage + d20 + dm_mod - target_soak)


# =============================================================================
# DAMAGE APPLICATION (mirrors mechanics.py)
# =============================================================================

def apply_damage(target: Combatant, damage: int, damage_type: str) -> None:
    """Apply damage to target per YAGS damage type rules."""
    if damage <= 0:
        return

    if damage_type == "wound":
        target.hp = max(0, target.hp - damage)
        target.wounds += damage // 5

    elif damage_type == "stun":
        # Non-cumulative: if new > current, replace. Elif >= half, +1.
        if damage > target.stuns:
            target.stuns = damage
        elif damage >= (target.stuns // 2):
            target.stuns += 1
        # else: no effect

    elif damage_type == "mixed":
        stun_portion = (damage + 1) // 2
        wound_portion = damage // 2

        # Mixed stuns are CUMULATIVE
        target.stuns += stun_portion

        # Wound portion
        target.hp = max(0, target.hp - wound_portion)
        target.wounds += wound_portion // 5


# =============================================================================
# COMBAT SIMULATION
# =============================================================================

def _resolve_pc_damage(rng: random.Random, model: str, pc: Combatant,
                        target: Combatant, attack_margin: int) -> int:
    """Calculate PC damage dealt using the specified model."""
    d20 = rng.randint(1, 20)

    if model == "llm":
        return damage_model_llm(rng=rng)
    elif model == "mechanical":
        return damage_model_mechanical(
            pc.strength, pc.weapon_damage, d20, target.soak)
    elif model == "margin":
        return damage_model_margin(
            pc.weapon_damage, attack_margin, d20, target.soak)
    elif model == "dm_modifier":
        # Weighted random DM modifier: mostly +0 to +2, occasionally -1 to +5
        weights = [(-2, 5), (-1, 10), (0, 25), (1, 30), (2, 20), (3, 7), (4, 2), (5, 1)]
        dm_mod = rng.choices(
            [w[0] for w in weights],
            weights=[w[1] for w in weights]
        )[0]
        return damage_model_dm_modifier(
            pc.strength, pc.weapon_damage, d20, target.soak, dm_mod)
    else:
        raise ValueError(f"Unknown damage model: {model}")


def run_combat(pcs: List[Combatant], enemies: List[Combatant],
               seed: int = 42, model: str = "mechanical",
               max_rounds: int = 20) -> CombatResult:
    """
    Simulate one combat encounter.

    Each round:
    1. All active enemies attack random alive PC
    2. All alive PCs attack first active enemy (focus fire)
    3. Check for defeat conditions
    """
    rng = random.Random(seed)

    # Clone combatants to avoid mutating originals
    sim_pcs = [pc.clone() for pc in pcs]
    sim_enemies = [e.clone() for e in enemies]

    for round_num in range(1, max_rounds + 1):
        alive_pcs = [p for p in sim_pcs if not p.is_defeated()]
        active_enemies = [e for e in sim_enemies if not e.is_defeated()]

        if not alive_pcs or not active_enemies:
            break

        # --- Enemy phase: each enemy attacks a random alive PC ---
        for enemy in active_enemies:
            alive_pcs_now = [p for p in sim_pcs if not p.is_defeated()]
            if not alive_pcs_now:
                break

            target = rng.choice(alive_pcs_now)
            flanking = rng.random() > 0.3  # ~70% chance of flanking

            d20 = rng.randint(1, 20)
            hit, margin = roll_enemy_attack(
                enemy.attack_attr, enemy.attack_skill,
                enemy.weapon_attack, d20, flanking
            )

            if hit:
                damage_d20 = rng.randint(1, 20)
                raw_damage = roll_enemy_damage(
                    enemy.strength, enemy.weapon_damage, damage_d20
                )
                dealt = max(0, raw_damage - target.soak)
                apply_damage(target, dealt, enemy.weapon_type)

        # --- PC phase: each PC attacks first active enemy (focus fire) ---
        for pc in sim_pcs:
            if pc.is_defeated():
                continue

            active_enemies_now = [e for e in sim_enemies if not e.is_defeated()]
            if not active_enemies_now:
                break

            target = active_enemies_now[0]  # Focus fire

            d20 = rng.randint(1, 20)
            hit, margin = roll_pc_attack(
                pc.attack_attr, pc.attack_skill, pc.weapon_attack, d20
            )

            if hit:
                dealt = _resolve_pc_damage(rng, model, pc, target, margin)
                apply_damage(target, dealt, pc.weapon_type)

        # Check termination
        alive_pcs = [p for p in sim_pcs if not p.is_defeated()]
        active_enemies = [e for e in sim_enemies if not e.is_defeated()]
        if not alive_pcs or not active_enemies:
            break

    # Determine outcome
    alive_pcs = [p for p in sim_pcs if not p.is_defeated()]
    active_enemies = [e for e in sim_enemies if not e.is_defeated()]
    enemy_kills = sum(1 for e in sim_enemies if e.is_defeated())

    if not active_enemies:
        outcome = "win"
    elif not alive_pcs:
        outcome = "loss"
    else:
        outcome = "draw"

    return CombatResult(
        outcome=outcome,
        rounds=min(round_num, max_rounds),
        pc_kills=sum(1 for p in sim_pcs if p.is_defeated()),
        enemy_kills=enemy_kills,
        total_enemies=len(enemies),
    )


# =============================================================================
# MONTE CARLO RUNNER
# =============================================================================

def run_monte_carlo(pcs: List[Combatant], enemies: List[Combatant],
                     model: str = "mechanical", runs: int = 10000,
                     seed: int = 42, max_rounds: int = 20) -> MonteCarloResult:
    """Run multiple combat simulations and aggregate results."""
    result = MonteCarloResult(model=model, total_runs=runs,
                               total_enemies=len(enemies))

    for i in range(runs):
        combat = run_combat(pcs, enemies, seed=seed + i, model=model,
                            max_rounds=max_rounds)

        if combat.outcome == "win":
            result.wins += 1
        elif combat.outcome == "loss":
            result.losses += 1
        else:
            result.draws += 1

        result.total_enemy_kills += combat.enemy_kills
        result.total_rounds += combat.rounds

    return result


# =============================================================================
# INPUT PARSING
# =============================================================================

def _get_attack_attr_for_skill(skill_name: str, attributes: dict) -> int:
    """Get the attribute used for a weapon skill."""
    if skill_name == "Guns":
        return attributes.get("Perception", 3)
    elif skill_name == "Melee":
        return attributes.get("Dexterity", attributes.get("Agility", 3))
    elif skill_name == "Brawl":
        return attributes.get("Agility", 3)
    else:  # Throw, etc
        return attributes.get("Agility", 3)


def _resolve_weapon_key(weapon_name: str) -> Optional[str]:
    """Resolve a weapon display name to its library key."""
    name_lower = weapon_name.lower()
    # Direct key match
    for key in WEAPON_DAMAGE:
        if key == name_lower or key.replace("_", " ") == name_lower:
            return key
    # Fuzzy: check if display name matches
    DISPLAY_NAMES = {
        "pistol": "pistol", "assault rifle": "rifle", "sniper rifle": "sniper_rifle",
        "shotgun": "shotgun", "baton": "baton", "combat knife": "combat_knife",
        "unarmed": "fists", "shock baton": "shock_baton", "void blade": "void_blade",
        "heavy machine gun": "heavy_weapon", "ritual blade": "ritual_blade",
        "frag grenade": "grenade", "stun grenade": "stun_grenade",
        "tranquilizer gun": "tranq_gun", "stun gun": "stun_gun",
        "light combat armor": "light_armor", "beat-up pistol": "beat_up_pistol",
    }
    return DISPLAY_NAMES.get(name_lower)


def parse_session_jsonl(path: Path) -> Tuple[List[Combatant], List[Combatant]]:
    """
    Parse PCs from session_start and enemies from enemy_spawn events.

    Returns (pcs, enemies).
    """
    pcs = []
    enemies = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            et = event.get("event_type")

            if et == "session_start":
                config = event.get("config", {})
                players = config.get("agents", {}).get("players", [])
                for p in players:
                    attrs = p.get("attributes", {})
                    skills = p.get("skills", {})
                    size = attrs.get("Size", 5)
                    endurance = attrs.get("Endurance", 3)
                    agility = attrs.get("Agility", 3)
                    strength = attrs.get("Strength", 3)

                    # Determine primary weapon
                    equipped = p.get("equipped_weapons", {})
                    primary_key = equipped.get("primary", "pistol")
                    wpn_damage = WEAPON_DAMAGE.get(primary_key, 4)
                    wpn_attack = WEAPON_ATTACK.get(primary_key, 0)
                    wpn_skill = WEAPON_SKILL.get(primary_key, "Guns")
                    wpn_type = WEAPON_TYPE.get(primary_key, "wound")

                    attack_attr = _get_attack_attr_for_skill(wpn_skill, attrs)
                    attack_skill = skills.get(wpn_skill, skills.get("Combat", 3))

                    pcs.append(Combatant(
                        name=p.get("name", "PC"),
                        hp=calc_pc_hp(size, endurance),
                        max_hp=calc_pc_hp(size, endurance),
                        soak=calc_pc_soak(size, agility, endurance),
                        strength=strength,
                        attack_attr=attack_attr,
                        attack_skill=attack_skill,
                        weapon_attack=wpn_attack,
                        weapon_damage=wpn_damage,
                        weapon_type=wpn_type,
                    ))

            elif et == "enemy_spawn":
                stats = event.get("stats", {})
                attrs = stats.get("attributes", {})
                skills = stats.get("skills", {})
                weapons = stats.get("weapons", [])

                # Pick best weapon (highest damage)
                best_wpn = None
                if weapons:
                    best_wpn = max(weapons, key=lambda w: w.get("damage", 0))

                wpn_damage = best_wpn.get("damage", 4) if best_wpn else 4
                wpn_attack = best_wpn.get("attack", 0) if best_wpn else 0
                wpn_skill_name = best_wpn.get("skill", "Guns") if best_wpn else "Guns"

                # Resolve damage type from weapon name
                wpn_type = "wound"
                if best_wpn:
                    wpn_key = _resolve_weapon_key(best_wpn.get("name", ""))
                    if wpn_key:
                        wpn_type = WEAPON_TYPE.get(wpn_key, "wound")

                attack_attr = _get_attack_attr_for_skill(wpn_skill_name, attrs)
                attack_skill = skills.get(wpn_skill_name, 2)

                enemies.append(Combatant(
                    name=event.get("enemy_name", "Enemy"),
                    hp=stats.get("health", 30),
                    max_hp=stats.get("max_health", stats.get("health", 30)),
                    soak=stats.get("soak", 10),
                    strength=attrs.get("Strength", 3),
                    attack_attr=attack_attr,
                    attack_skill=attack_skill,
                    weapon_attack=wpn_attack,
                    weapon_damage=wpn_damage,
                    weapon_type=wpn_type,
                    is_enemy=True,
                ))

    return pcs, enemies


def parse_session_config(path: Path) -> Tuple[List[Combatant], List[Combatant]]:
    """
    Parse PCs from agents.players and enemies from initial_enemies.

    Fallback when no session JSONL is available.
    """
    with open(path) as f:
        config = json.load(f)

    pcs = []
    enemies = []

    # Parse PCs
    players = config.get("agents", {}).get("players", [])
    for p in players:
        attrs = p.get("attributes", {})
        skills = p.get("skills", {})
        size = attrs.get("Size", 5)
        endurance = attrs.get("Endurance", 3)
        agility = attrs.get("Agility", 3)
        strength = attrs.get("Strength", 3)

        equipped = p.get("equipped_weapons", {})
        primary_key = equipped.get("primary", "pistol")
        wpn_damage = WEAPON_DAMAGE.get(primary_key, 4)
        wpn_attack = WEAPON_ATTACK.get(primary_key, 0)
        wpn_skill = WEAPON_SKILL.get(primary_key, "Guns")
        wpn_type = WEAPON_TYPE.get(primary_key, "wound")

        attack_attr = _get_attack_attr_for_skill(wpn_skill, attrs)
        attack_skill = skills.get(wpn_skill, skills.get("Combat", 3))

        pcs.append(Combatant(
            name=p.get("name", "PC"),
            hp=calc_pc_hp(size, endurance),
            max_hp=calc_pc_hp(size, endurance),
            soak=calc_pc_soak(size, agility, endurance),
            strength=strength,
            attack_attr=attack_attr,
            attack_skill=attack_skill,
            weapon_attack=wpn_attack,
            weapon_damage=wpn_damage,
            weapon_type=wpn_type,
        ))

    # Parse enemies from initial_enemies + ENEMY_TEMPLATES
    try:
        # Support running from project root or from scripts/
        scripts_dir = Path(__file__).resolve().parent
        multiagent_dir = scripts_dir / "aeonisk" / "multiagent"
        if not multiagent_dir.exists():
            multiagent_dir = scripts_dir.parent / "scripts" / "aeonisk" / "multiagent"
        sys.path.insert(0, str(multiagent_dir.parent.parent))
        from aeonisk.multiagent.enemy_templates import ENEMY_TEMPLATES
    except ImportError:
        ENEMY_TEMPLATES = {}

    for entry in config.get("initial_enemies", []):
        template_key = entry.get("template", "grunt").lower()
        count = entry.get("count", 1)
        template = ENEMY_TEMPLATES.get(template_key, {})

        if not template:
            continue

        t_attrs = template.get("attributes", {})
        t_skills = template.get("skills", {})
        t_weapons = template.get("weapons", [])
        t_armor = template.get("armor", "none")
        armor_soak = ARMOR_SOAK.get(t_armor, 0)

        # Pick best weapon
        best_key = t_weapons[0] if t_weapons else "pistol"
        for wk in t_weapons:
            if WEAPON_DAMAGE.get(wk, 0) > WEAPON_DAMAGE.get(best_key, 0):
                best_key = wk

        wpn_damage = WEAPON_DAMAGE.get(best_key, 4)
        wpn_attack = WEAPON_ATTACK.get(best_key, 0)
        wpn_skill_name = WEAPON_SKILL.get(best_key, "Guns")
        wpn_type = WEAPON_TYPE.get(best_key, "wound")

        size = template.get("size", 5)
        agility = t_attrs.get("Agility", 3)
        endurance = t_attrs.get("Endurance", t_attrs.get("Health", 3))
        strength = t_attrs.get("Strength", 3)

        attack_attr = _get_attack_attr_for_skill(wpn_skill_name, t_attrs)
        attack_skill = t_skills.get(wpn_skill_name, 2)

        hp = template.get("health", 30)

        for i in range(count):
            enemies.append(Combatant(
                name=f"{template_key.title()} #{i+1}",
                hp=hp,
                max_hp=hp,
                soak=calc_enemy_soak(size, agility, endurance, armor_soak),
                strength=strength,
                attack_attr=attack_attr,
                attack_skill=attack_skill,
                weapon_attack=wpn_attack,
                weapon_damage=wpn_damage,
                weapon_type=wpn_type,
                is_enemy=True,
            ))

    return pcs, enemies


# =============================================================================
# SENSITIVITY ANALYSIS
# =============================================================================

def run_sensitivity_sweep(pcs: List[Combatant], enemies: List[Combatant],
                           seed: int = 42, runs: int = 1000) -> Dict[str, List]:
    """Run parameter sweeps with Model B (mechanical) as baseline."""
    results = {}

    # Baseline
    baseline = run_monte_carlo(pcs, enemies, model="mechanical",
                                runs=runs, seed=seed)
    results["baseline"] = baseline

    # Sweep enemy HP
    hp_results = []
    for hp_mult in [0.5, 0.67, 0.83, 1.0, 1.17, 1.33]:
        modified_enemies = []
        for e in enemies:
            m = e.clone()
            m.hp = int(e.max_hp * hp_mult)
            m.max_hp = m.hp
            modified_enemies.append(m)
        r = run_monte_carlo(pcs, modified_enemies, model="mechanical",
                             runs=runs, seed=seed)
        hp_results.append((hp_mult, r))
    results["enemy_hp_sweep"] = hp_results

    # Sweep enemy count (take first N)
    count_results = []
    for count in range(1, min(len(enemies) + 1, 9)):
        r = run_monte_carlo(pcs, enemies[:count], model="mechanical",
                             runs=runs, seed=seed)
        count_results.append((count, r))
    results["enemy_count_sweep"] = count_results

    # Sweep PC weapon damage
    wpn_results = []
    for wpn_key, wpn_label in [("pistol", "Pistol(+4)"), ("rifle", "Rifle(+5)"),
                                 ("shotgun", "Shotgun(+6)"), ("sniper_rifle", "Sniper(+8)")]:
        modified_pcs = []
        for p in pcs:
            m = p.clone()
            m.weapon_damage = WEAPON_DAMAGE[wpn_key]
            m.weapon_attack = WEAPON_ATTACK[wpn_key]
            modified_pcs.append(m)
        r = run_monte_carlo(modified_pcs, enemies, model="mechanical",
                             runs=runs, seed=seed)
        wpn_results.append((wpn_label, r))
    results["pc_weapon_sweep"] = wpn_results

    # Sweep party size (clone first PC)
    party_results = []
    for party_size in [1, 2, 3, 4]:
        modified_pcs = [pcs[0].clone() for _ in range(party_size)]
        for i, p in enumerate(modified_pcs):
            p.name = f"PC{i+1}"
        r = run_monte_carlo(modified_pcs, enemies, model="mechanical",
                             runs=runs, seed=seed)
        party_results.append((party_size, r))
    results["party_size_sweep"] = party_results

    # Sweep enemy damage multiplier
    mult_results = []
    for mult in [0.50, 0.70, 0.85, 1.00, 1.15]:
        # Modify enemy strength to simulate multiplier change
        # Since damage = (str + wpn + d20) * mult, and we can't change mult directly,
        # we adjust by scaling enemy strength + weapon damage proportionally
        # Actually, we'll need a custom model for this — skip for now and note it
        pass
    results["damage_mult_sweep"] = mult_results

    return results


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_model_result(r: MonteCarloResult, label: str, enemy_count: int) -> str:
    """Format a single model result line."""
    return (
        f"  {label:<45s} — Win: {r.win_rate:5.1%}  | "
        f"Avg Kills: {r.avg_kills:.1f}/{enemy_count} | "
        f"Avg Rounds: {r.avg_rounds:.1f}"
    )


def format_results(pcs: List[Combatant], enemies: List[Combatant],
                    model_results: Dict[str, MonteCarloResult],
                    runs: int, sweep_results: Optional[Dict] = None) -> str:
    """Format all results for display."""
    lines = []

    # Header
    lines.append(f"\nMONTE CARLO COMBAT SIMULATION — {runs} runs")

    # Scenario summary
    pc_desc = ", ".join(f"{p.name} (HP={p.max_hp}, Soak={p.soak})" for p in pcs[:3])
    if len(pcs) > 3:
        pc_desc += f", +{len(pcs)-3} more"

    # Count enemy types
    enemy_types = {}
    for e in enemies:
        # Extract template type from name
        key = f"HP={e.max_hp}/Soak={e.soak}"
        enemy_types[key] = enemy_types.get(key, 0) + 1
    enemy_desc = ", ".join(f"{v}x ({k})" for k, v in enemy_types.items())

    lines.append(f"Scenario: {len(pcs)} PCs vs {len(enemies)} Enemies")
    lines.append(f"  PCs: {pc_desc}")
    lines.append(f"  Enemies: {enemy_desc}")
    lines.append("=" * 75)

    # Model results
    model_labels = {
        "llm": "Model A: LLM Distribution (mean=9, std=3)",
        "mechanical": "Model B: Mechanical Symmetric (Str+wpn+d20)",
        "margin": "Model C: Margin Bonus (wpn+margin/3+d20)",
        "dm_modifier": "Model D: Mechanical + DM Mod (base+mod)",
    }

    for model_key in ["llm", "mechanical", "margin", "dm_modifier"]:
        if model_key in model_results:
            lines.append(format_model_result(
                model_results[model_key],
                model_labels[model_key],
                len(enemies)
            ))

    # Sensitivity sweep
    if sweep_results:
        lines.append("")
        lines.append("SENSITIVITY ANALYSIS (Model B: Mechanical Symmetric)")
        lines.append("-" * 75)

        baseline = sweep_results["baseline"]

        # Enemy count
        if sweep_results.get("enemy_count_sweep"):
            lines.append("  Enemy count:")
            for count, r in sweep_results["enemy_count_sweep"]:
                delta = r.win_rate - baseline.win_rate
                lines.append(f"    {count} enemies: Win {r.win_rate:5.1%}  ({delta:+.1%})")

        # Enemy HP
        if sweep_results.get("enemy_hp_sweep"):
            lines.append("  Enemy HP multiplier:")
            for mult, r in sweep_results["enemy_hp_sweep"]:
                delta = r.win_rate - baseline.win_rate
                lines.append(f"    {mult:.0%} HP: Win {r.win_rate:5.1%}  ({delta:+.1%})")

        # PC weapon
        if sweep_results.get("pc_weapon_sweep"):
            lines.append("  PC weapon:")
            for label, r in sweep_results["pc_weapon_sweep"]:
                delta = r.win_rate - baseline.win_rate
                lines.append(f"    {label}: Win {r.win_rate:5.1%}  ({delta:+.1%})")

        # Party size
        if sweep_results.get("party_size_sweep"):
            lines.append("  Party size:")
            for size, r in sweep_results["party_size_sweep"]:
                delta = r.win_rate - baseline.win_rate
                lines.append(f"    {size} PCs: Win {r.win_rate:5.1%}  ({delta:+.1%})")

    lines.append("")
    return "\n".join(lines)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo combat simulation for Aeonisk YAGS"
    )
    parser.add_argument(
        "session_jsonl", nargs="?",
        help="Path to session JSONL file (primary input)"
    )
    parser.add_argument(
        "--config", type=str,
        help="Path to session config JSON (fallback input)"
    )
    parser.add_argument(
        "--runs", type=int, default=10000,
        help="Number of simulation runs (default: 10000)"
    )
    parser.add_argument(
        "--model", type=str, default="all",
        choices=["llm", "mechanical", "margin", "dm_modifier", "all"],
        help="Damage model to use (default: all)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--max-rounds", type=int, default=20,
        help="Maximum rounds per combat (default: 20)"
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="Run sensitivity sweep after main simulation"
    )

    args = parser.parse_args()

    # Parse input
    if args.session_jsonl:
        path = Path(args.session_jsonl)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        pcs, enemies = parse_session_jsonl(path)
        print(f"Parsed from JSONL: {len(pcs)} PCs, {len(enemies)} enemies")
    elif args.config:
        path = Path(args.config)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        pcs, enemies = parse_session_config(path)
        print(f"Parsed from config: {len(pcs)} PCs, {len(enemies)} enemies")
    else:
        print("Error: provide session JSONL path or --config path", file=sys.stderr)
        sys.exit(1)

    if not pcs:
        print("Error: no PCs found", file=sys.stderr)
        sys.exit(1)
    if not enemies:
        print("Error: no enemies found", file=sys.stderr)
        sys.exit(1)

    # Run simulation
    models_to_run = (
        ["llm", "mechanical", "margin", "dm_modifier"]
        if args.model == "all" else [args.model]
    )

    model_results = {}
    for model in models_to_run:
        print(f"Running {model}... ", end="", flush=True)
        result = run_monte_carlo(
            pcs, enemies, model=model, runs=args.runs,
            seed=args.seed, max_rounds=args.max_rounds
        )
        model_results[model] = result
        print(f"Win: {result.win_rate:.1%}")

    # Sensitivity sweep
    sweep_results = None
    if args.sweep:
        print("Running sensitivity sweep...")
        sweep_results = run_sensitivity_sweep(
            pcs, enemies, seed=args.seed, runs=min(args.runs, 1000)
        )

    # Output
    print(format_results(pcs, enemies, model_results, args.runs, sweep_results))


if __name__ == "__main__":
    main()
