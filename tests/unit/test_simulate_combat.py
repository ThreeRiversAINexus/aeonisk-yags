"""
TDD tests for Monte Carlo combat simulation.

Tests cover:
- Formula calculations (HP, soak, attack, damage)
- Four damage models (LLM, mechanical, margin, DM modifier)
- Damage application (wound, stun, mixed)
- Simulation loop (determinism, termination, victory conditions)
- Input parsing (session JSONL, session config)
"""

import json
import math
import random
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from simulate_combat import (
    Combatant,
    SimConfig,
    WEAPON_DAMAGE,
    WEAPON_SKILL,
    calc_pc_hp,
    calc_pc_soak,
    calc_enemy_soak,
    roll_enemy_attack,
    roll_enemy_damage,
    roll_pc_attack,
    damage_model_llm,
    damage_model_mechanical,
    damage_model_margin,
    damage_model_dm_modifier,
    apply_damage,
    run_combat,
    parse_session_jsonl,
    parse_session_config,
    run_monte_carlo,
)


# =============================================================================
# FORMULA TESTS
# =============================================================================

class TestPCFormulas:
    """Test PC stat calculations match player.py formulas."""

    def test_pc_hp_calculation(self):
        """HP = (Size*2) + Endurance + 13. Size=5, End=4 => 27."""
        assert calc_pc_hp(size=5, endurance=4) == 27

    def test_pc_hp_default_stats(self):
        """HP with default human stats (Size=5, End=3) => 26."""
        assert calc_pc_hp(size=5, endurance=3) == 26

    def test_pc_soak_calculation(self):
        """Soak = Size + Agi + End - 5 + armor. Size=5, Agi=4, End=4, armor=3 => 11."""
        assert calc_pc_soak(size=5, agility=4, endurance=4, armor_soak=3) == 11

    def test_pc_soak_low_stats(self):
        """Soak with low stats no armor. Size=5, Agi=2, End=2 => 4."""
        assert calc_pc_soak(size=5, agility=2, endurance=2) == 4


class TestEnemyFormulas:
    """Test enemy stat calculations match enemy_agent.py formulas."""

    def test_enemy_soak_with_armor(self):
        """Grunt soak: Size(5)+Agi(3)+End(3)-5+armor(3) = 9."""
        assert calc_enemy_soak(size=5, agility=3, endurance=3, armor_soak=3) == 9

    def test_enemy_soak_no_armor(self):
        """Soak without armor. Size(5)+Agi(3)+End(3)-5 = 6."""
        assert calc_enemy_soak(size=5, agility=3, endurance=3, armor_soak=0) == 6

    def test_enemy_soak_heavy_armor(self):
        """Enforcer soak: Size(5)+Agi(3)+End(3)-5+armor(8) = 14."""
        assert calc_enemy_soak(size=5, agility=3, endurance=3, armor_soak=8) == 14


class TestEnemyAttack:
    """Test enemy attack roll formula from enemy_combat.py."""

    def test_enemy_attack_hit(self):
        """(attr*skill) + weapon_attack + d20 + flanking(+2) >= 15."""
        # Grunt with pistol: Perception(2)*Guns(3) + 0 + 15 + 2 = 23 >= 15
        hit, margin = roll_enemy_attack(
            attr=2, skill=3, weapon_attack=0, d20=15, flanking=True
        )
        assert hit is True
        assert margin == 23 - 15  # 8

    def test_enemy_attack_miss(self):
        """Low roll should miss."""
        # (2*3) + 0 + 1 + 2 = 9 < 15
        hit, margin = roll_enemy_attack(
            attr=2, skill=3, weapon_attack=0, d20=1, flanking=True
        )
        assert hit is False

    def test_enemy_attack_no_flanking(self):
        """Without flanking, -2 penalty instead of +2."""
        # (2*3) + 0 + 10 - 2 = 14 < 15
        hit, margin = roll_enemy_attack(
            attr=2, skill=3, weapon_attack=0, d20=10, flanking=False
        )
        assert hit is False


class TestEnemyDamage:
    """Test enemy damage formula from enemy_combat.py:1029-1034."""

    def test_enemy_damage_formula(self):
        """Damage = (Str + weapon.damage + d20) * 0.85."""
        # Str(3) + Pistol(4) + d20(10) = 17, * 0.85 = 14.45 => 14
        raw = roll_enemy_damage(strength=3, weapon_damage=4, d20=10)
        assert raw == int((3 + 4 + 10) * 0.85)  # 14

    def test_enemy_damage_after_soak(self):
        """After soak: max(0, raw - soak)."""
        raw = roll_enemy_damage(strength=3, weapon_damage=4, d20=10)
        dealt = max(0, raw - 12)  # soak=12
        assert dealt == 2


class TestPCAttack:
    """Test PC attack formula."""

    def test_pc_attack_always_hits_high_skill(self):
        """PC with high skill: (4*5)+d20(1) = 21 >= 15. Always hits."""
        hit, margin = roll_pc_attack(attr=4, skill=5, weapon_attack=0, d20=1)
        assert hit is True
        assert margin == 21 - 15  # 6

    def test_pc_attack_can_miss_low_skill(self):
        """PC with low skill: (2*2)+d20(1) = 5 < 15."""
        hit, margin = roll_pc_attack(attr=2, skill=2, weapon_attack=0, d20=1)
        assert hit is False


# =============================================================================
# DAMAGE MODEL TESTS
# =============================================================================

class TestDamageModelLLM:
    """Test Model A: LLM distribution."""

    def test_llm_distribution_range(self):
        """LLM model should produce values in sane range (0-30)."""
        rng = random.Random(42)
        values = [damage_model_llm(rng=rng) for _ in range(1000)]
        assert all(v >= 0 for v in values)
        assert any(v > 0 for v in values)
        # Mean should be around 9
        mean = sum(values) / len(values)
        assert 7 < mean < 11

    def test_llm_distribution_floor(self):
        """LLM damage can't go below 0."""
        rng = random.Random(42)
        values = [damage_model_llm(rng=rng) for _ in range(10000)]
        assert min(values) >= 0


class TestDamageModelMechanical:
    """Test Model B: Mechanical symmetric."""

    def test_mechanical_with_known_roll(self):
        """Str(3)+pistol(4)+d20(10)-soak(13) = 4."""
        dealt = damage_model_mechanical(strength=3, weapon_damage=4, d20=10, target_soak=13)
        assert dealt == 4

    def test_mechanical_zero_floor(self):
        """Damage can't go below 0."""
        dealt = damage_model_mechanical(strength=3, weapon_damage=4, d20=1, target_soak=13)
        assert dealt == 0  # 3+4+1-13 = -5 => 0

    def test_mechanical_high_roll(self):
        """High roll should produce significant damage."""
        dealt = damage_model_mechanical(strength=3, weapon_damage=4, d20=20, target_soak=13)
        assert dealt == 14  # 3+4+20-13 = 14


class TestDamageModelMargin:
    """Test Model C: Margin bonus."""

    def test_margin_bonus_scaling(self):
        """Margin 15 => +5 bonus. weapon(4)+5+d20(10)-soak(13) = 6."""
        dealt = damage_model_margin(
            weapon_damage=4, attack_margin=15, d20=10, target_soak=13
        )
        assert dealt == 6  # 4 + (15//3) + 10 - 13 = 4+5+10-13 = 6

    def test_margin_bonus_low_margin(self):
        """Margin 3 => +1 bonus."""
        dealt = damage_model_margin(
            weapon_damage=4, attack_margin=3, d20=10, target_soak=13
        )
        assert dealt == 2  # 4 + 1 + 10 - 13 = 2

    def test_margin_bonus_zero_floor(self):
        """Floor at 0."""
        dealt = damage_model_margin(
            weapon_damage=4, attack_margin=0, d20=1, target_soak=13
        )
        assert dealt == 0  # 4+0+1-13 = -8 => 0


class TestDamageModelDMModifier:
    """Test Model D: Mechanical + DM modifier."""

    def test_dm_modifier_positive(self):
        """With +3 modifier: Str(3)+wpn(4)+d20(10)+3-soak(13) = 7."""
        dealt = damage_model_dm_modifier(
            strength=3, weapon_damage=4, d20=10, target_soak=13, dm_mod=3
        )
        assert dealt == 7

    def test_dm_modifier_negative(self):
        """With -2 modifier, can reduce to 0."""
        dealt = damage_model_dm_modifier(
            strength=3, weapon_damage=4, d20=5, target_soak=13, dm_mod=-2
        )
        assert dealt == 0  # 3+4+5-2-13 = -3 => 0


# =============================================================================
# DAMAGE APPLICATION TESTS
# =============================================================================

class TestDamageApplication:
    """Test wound/stun/mixed damage routing."""

    def test_wound_reduces_hp_adds_wounds(self):
        """10 wound damage: HP -= 10, wounds += 2 (10//5)."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=0)
        apply_damage(c, 10, "wound")
        assert c.hp == 17
        assert c.wounds == 2

    def test_wound_zero_damage(self):
        """0 damage should do nothing."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=0)
        apply_damage(c, 0, "wound")
        assert c.hp == 27
        assert c.wounds == 0

    def test_stun_noncumulative_replace(self):
        """Stun 5 when current=3: replace with 5."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=3)
        apply_damage(c, 5, "stun")
        assert c.stuns == 5

    def test_stun_noncumulative_increment(self):
        """Stun 3 when current=4: 3 >= 4//2=2, so +1."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=4)
        apply_damage(c, 3, "stun")
        assert c.stuns == 5

    def test_stun_noncumulative_nothing(self):
        """Stun 1 when current=4: 1 < 4//2=2, no change."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=4)
        apply_damage(c, 1, "stun")
        assert c.stuns == 4

    def test_mixed_splits(self):
        """7 mixed: stun=(7+1)//2=4, wound=7//2=3."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=0)
        apply_damage(c, 7, "mixed")
        assert c.stuns == 4  # (7+1)//2
        assert c.wounds == 0  # 3//5 = 0
        assert c.hp == 24  # 27 - 3 (wound portion)

    def test_mixed_large_damage(self):
        """20 mixed: stun=10 (cumulative), wound_hp=10, wounds=2."""
        c = Combatant(name="Test", hp=50, max_hp=50, soak=12, wounds=0, stuns=0)
        apply_damage(c, 20, "mixed")
        assert c.stuns == 10  # (20+1)//2 = 10 (cumulative for mixed)
        assert c.wounds == 2  # 10//5
        assert c.hp == 40  # 50 - 10


# =============================================================================
# COMBATANT TESTS
# =============================================================================

class TestCombatant:
    """Test Combatant defeat conditions."""

    def test_defeated_hp_zero(self):
        """HP <= 0 is defeated."""
        c = Combatant(name="Test", hp=0, max_hp=27, soak=12, wounds=0, stuns=0)
        assert c.is_defeated()

    def test_defeated_stuns(self):
        """Stuns >= 6 is defeated (unconscious)."""
        c = Combatant(name="Test", hp=27, max_hp=27, soak=12, wounds=0, stuns=6)
        assert c.is_defeated()

    def test_not_defeated(self):
        """Alive with stuns < 6 is not defeated."""
        c = Combatant(name="Test", hp=10, max_hp=27, soak=12, wounds=3, stuns=4)
        assert not c.is_defeated()


# =============================================================================
# SIMULATION TESTS
# =============================================================================

class TestSimulation:
    """Test combat simulation loop."""

    def test_deterministic_with_seed(self):
        """Same seed = same result."""
        pcs = [
            Combatant("PC1", hp=27, max_hp=27, soak=12,
                       strength=3, attack_attr=4, attack_skill=5,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Grunt", hp=30, max_hp=30, soak=13,
                       strength=3, attack_attr=2, attack_skill=3,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]

        r1 = run_combat(pcs, enemies, seed=42, model="mechanical")
        r2 = run_combat(pcs, enemies, seed=42, model="mechanical")
        assert r1.outcome == r2.outcome
        assert r1.rounds == r2.rounds

    def test_combat_terminates(self):
        """Combat ends within max_rounds."""
        pcs = [
            Combatant("PC1", hp=27, max_hp=27, soak=12,
                       strength=3, attack_attr=4, attack_skill=5,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Grunt", hp=30, max_hp=30, soak=13,
                       strength=3, attack_attr=2, attack_skill=3,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]

        result = run_combat(pcs, enemies, seed=42, model="mechanical", max_rounds=20)
        assert result.rounds <= 20

    def test_all_enemies_dead_is_win(self):
        """PC victory when all enemies die."""
        # Strong PC vs weak enemy
        pcs = [
            Combatant("PC1", hp=100, max_hp=100, soak=12,
                       strength=5, attack_attr=5, attack_skill=5,
                       weapon_attack=0, weapon_damage=8, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Weakling", hp=5, max_hp=5, soak=0,
                       strength=1, attack_attr=1, attack_skill=1,
                       weapon_attack=0, weapon_damage=1, weapon_type="wound"),
        ]

        result = run_combat(pcs, enemies, seed=42, model="mechanical")
        assert result.outcome == "win"

    def test_all_pcs_dead_is_loss(self):
        """Enemy victory when all PCs die."""
        # Weak PC vs strong enemy
        pcs = [
            Combatant("Weakling", hp=5, max_hp=5, soak=0,
                       strength=1, attack_attr=1, attack_skill=1,
                       weapon_attack=0, weapon_damage=1, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Boss", hp=100, max_hp=100, soak=0,
                       strength=5, attack_attr=5, attack_skill=5,
                       weapon_attack=0, weapon_damage=8, weapon_type="wound"),
        ]

        result = run_combat(pcs, enemies, seed=42, model="mechanical")
        assert result.outcome == "loss"


# =============================================================================
# INPUT PARSING TESTS
# =============================================================================

class TestParseSessionJSONL:
    """Test parsing PCs and enemies from session JSONL files."""

    def _make_jsonl(self, events):
        """Write events to temp JSONL file."""
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        for event in events:
            tf.write(json.dumps(event) + '\n')
        tf.close()
        return Path(tf.name)

    def test_parse_session_jsonl(self):
        """Extract PCs from session_start and enemies from enemy_spawn."""
        events = [
            {
                "event_type": "session_start",
                "config": {
                    "agents": {
                        "players": [
                            {
                                "name": "Test PC",
                                "attributes": {
                                    "Strength": 3, "Agility": 4,
                                    "Endurance": 4, "Perception": 4,
                                    "Intelligence": 3, "Empathy": 3,
                                    "Willpower": 3, "Dexterity": 3
                                },
                                "skills": {"Guns": 5, "Combat": 5, "Brawl": 4},
                                "equipped_weapons": {"primary": "pistol"},
                            }
                        ]
                    }
                }
            },
            {
                "event_type": "enemy_spawn",
                "enemy_id": "enemy_grunt_1",
                "enemy_name": "Grunt #1",
                "template": "grunt",
                "stats": {
                    "health": 30,
                    "max_health": 30,
                    "soak": 13,
                    "attributes": {"Agility": 3, "Strength": 3, "Perception": 2},
                    "skills": {"Guns": 3, "Brawl": 2, "Melee": 1},
                    "weapons": [
                        {"name": "Pistol", "attack": 0, "damage": 4, "skill": "Guns"}
                    ],
                    "armor": {"name": "Light Combat Armor", "soak_bonus": 3}
                }
            },
        ]

        path = self._make_jsonl(events)
        try:
            pcs, enemies = parse_session_jsonl(path)
            assert len(pcs) == 1
            assert len(enemies) == 1
            assert pcs[0].name == "Test PC"
            assert pcs[0].hp == 27  # (5*2)+4+13
            assert pcs[0].soak == 8  # 5+4+4-5 (YAGS: no balance modifier)
            assert enemies[0].name == "Grunt #1"
            assert enemies[0].hp == 30
            assert enemies[0].soak == 13
        finally:
            path.unlink()

    def test_parse_session_config_fallback(self):
        """Parse from session config JSON when no JSONL available."""
        config = {
            "agents": {
                "players": [
                    {
                        "name": "Test PC",
                        "attributes": {
                            "Strength": 3, "Agility": 4,
                            "Endurance": 4, "Perception": 4,
                        },
                        "skills": {"Guns": 5, "Combat": 5},
                        "equipped_weapons": {"primary": "pistol"},
                    }
                ]
            },
            "initial_enemies": [
                {"template": "grunt", "count": 2}
            ]
        }

        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(config, tf)
        tf.close()
        path = Path(tf.name)

        try:
            pcs, enemies = parse_session_config(path)
            assert len(pcs) == 1
            assert len(enemies) == 2
            assert pcs[0].weapon_damage == 4  # pistol
            assert enemies[0].hp == 30  # grunt HP from template
        finally:
            path.unlink()


# =============================================================================
# MONTE CARLO AGGREGATE TESTS
# =============================================================================

class TestMonteCarlo:
    """Test Monte Carlo runner produces valid aggregate results."""

    def test_monte_carlo_results_structure(self):
        """Results contain win_rate, avg_kills, avg_rounds."""
        pcs = [
            Combatant("PC1", hp=27, max_hp=27, soak=12,
                       strength=3, attack_attr=4, attack_skill=5,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Grunt", hp=30, max_hp=30, soak=13,
                       strength=3, attack_attr=2, attack_skill=3,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]

        results = run_monte_carlo(pcs, enemies, model="mechanical", runs=100, seed=42)
        assert 0 <= results.win_rate <= 1
        assert results.avg_kills >= 0
        assert results.avg_rounds > 0
        assert results.total_runs == 100

    def test_monte_carlo_deterministic(self):
        """Same seed = same aggregate results."""
        pcs = [
            Combatant("PC1", hp=27, max_hp=27, soak=12,
                       strength=3, attack_attr=4, attack_skill=5,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]
        enemies = [
            Combatant("Grunt", hp=30, max_hp=30, soak=13,
                       strength=3, attack_attr=2, attack_skill=3,
                       weapon_attack=0, weapon_damage=4, weapon_type="wound"),
        ]

        r1 = run_monte_carlo(pcs, enemies, model="mechanical", runs=100, seed=42)
        r2 = run_monte_carlo(pcs, enemies, model="mechanical", runs=100, seed=42)
        assert r1.win_rate == r2.win_rate
        assert r1.avg_kills == r2.avg_kills


# =============================================================================
# MELEE BOOST VALIDATION TESTS
# =============================================================================

class TestMeleeBoostSync:
    """Verify melee +3 boost is reflected in simulator's WEAPON_DAMAGE dict."""

    # Expected values after +3 melee boost (Melee-skill weapons only)
    MELEE_BOOSTED = {
        "baton": 5, "combat_knife": 6, "void_blade": 8, "ritual_blade": 7,
        "mnemonic_blade": 8, "ash_pulse_pike": 7, "breach_hammer": 10,
        "sparkspike_dagger": 7, "wraithroot_vineblade": 5, "ritual_staff": 5,
        "void_cloak": 4,
    }

    # Brawl weapons should NOT have the boost
    BRAWL_UNCHANGED = {
        "fists": 0, "shock_baton": 3, "dripshock_baton": 2,
    }

    def test_melee_weapons_have_boost(self):
        """All Melee-skill weapons should have +3 damage boost."""
        for weapon, expected_damage in self.MELEE_BOOSTED.items():
            assert WEAPON_DAMAGE[weapon] == expected_damage, (
                f"{weapon}: expected {expected_damage}, got {WEAPON_DAMAGE[weapon]}"
            )

    def test_brawl_weapons_unchanged(self):
        """Brawl weapons should NOT have melee boost."""
        for weapon, expected_damage in self.BRAWL_UNCHANGED.items():
            assert WEAPON_DAMAGE[weapon] == expected_damage, (
                f"{weapon}: expected {expected_damage}, got {WEAPON_DAMAGE[weapon]}"
            )

    def test_all_melee_skill_weapons_accounted_for(self):
        """Every weapon with skill='Melee' should be in the boost table."""
        melee_weapons = {k for k, v in WEAPON_SKILL.items() if v == "Melee"}
        assert melee_weapons == set(self.MELEE_BOOSTED.keys()), (
            f"Mismatch: {melee_weapons.symmetric_difference(set(self.MELEE_BOOSTED.keys()))}"
        )

    def test_simulator_matches_weapons_py(self):
        """Simulator WEAPON_DAMAGE dict matches weapons.py for all Melee weapons."""
        weapons_py_dir = Path(__file__).resolve().parents[2] / "scripts" / "aeonisk" / "multiagent"
        sys.path.insert(0, str(weapons_py_dir.parent.parent))
        from aeonisk.multiagent.weapons import WEAPON_LIBRARY

        for weapon_id, weapon in WEAPON_LIBRARY.items():
            if weapon.skill == "Melee":
                assert WEAPON_DAMAGE[weapon_id] == weapon.damage, (
                    f"{weapon_id}: simulator={WEAPON_DAMAGE[weapon_id]}, "
                    f"weapons.py={weapon.damage}"
                )
