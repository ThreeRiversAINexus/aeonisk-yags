"""
Unit tests for WEAPON_LIBRARY and weapon-related functionality.

TDD approach: These tests are written FIRST to define expected behavior,
then implementation follows to make them pass.
"""

import pytest
from scripts.aeonisk.multiagent.weapons import (
    WEAPON_LIBRARY,
    get_weapon,
    Weapon
)


class TestWeaponLibraryCompleteness:
    """Test that all required weapons exist in the library."""

    def test_hacking_toolkit_exists_in_library(self):
        """Hacking toolkit should be in WEAPON_LIBRARY as a tech weapon."""
        assert "hacking_toolkit" in WEAPON_LIBRARY
        weapon = WEAPON_LIBRARY["hacking_toolkit"]
        assert weapon.name == "Hacking Toolkit"
        assert weapon.is_ranged is True
        assert weapon.damage_type == "stun"
        assert weapon.short_range > 0
        assert "electric" in weapon.special or "tech" in weapon.special

    def test_custom_energy_weapon_exists_in_library(self):
        """Custom energy weapon should be in WEAPON_LIBRARY."""
        assert "custom_energy_weapon" in WEAPON_LIBRARY
        weapon = WEAPON_LIBRARY["custom_energy_weapon"]
        assert weapon.name == "Custom Energy Weapon"
        assert weapon.is_ranged is True
        assert weapon.damage_type == "wound"
        assert weapon.damage >= 4  # Should be combat-effective

    def test_glyph_bonded_weapons_exist(self):
        """Glyph and bonded weapons from Gear & Tech Reference should exist."""
        required_weapons = [
            "shrike_cannon",
            "mnemonic_blade",
            "spark_pulse_rifle"
        ]
        for weapon_id in required_weapons:
            assert weapon_id in WEAPON_LIBRARY, f"Missing: {weapon_id}"
            weapon = WEAPON_LIBRARY[weapon_id]
            assert weapon.damage >= 4, f"{weapon_id} should have meaningful damage"

    def test_void_weapons_exist(self):
        """Void weapons from Gear & Tech Reference should exist."""
        required_weapons = [
            "ash_pulse_pike",
            "hollowed_repeater"
        ]
        for weapon_id in required_weapons:
            assert weapon_id in WEAPON_LIBRARY, f"Missing: {weapon_id}"
            weapon = WEAPON_LIBRARY[weapon_id]
            # Void weapons should have void-related special properties
            assert any(s in weapon.special for s in ["void", "void_corrupted", "void_infused"]) \
                   or "void" in weapon.name.lower()

    def test_street_gear_weapons_exist(self):
        """Standard street gear from Gear & Tech Reference should exist."""
        required_weapons = [
            "union_heavy_pistol",
            "breach_hammer",
            "dripshock_baton"
        ]
        for weapon_id in required_weapons:
            assert weapon_id in WEAPON_LIBRARY, f"Missing: {weapon_id}"


class TestFragGrenadeAOE:
    """Test frag grenade configuration and AoE notation."""

    def test_frag_grenade_has_aoe_special(self):
        """Frag grenade should have 'aoe' in special properties."""
        assert "grenade" in WEAPON_LIBRARY
        grenade = WEAPON_LIBRARY["grenade"]
        assert "aoe" in grenade.special, "Grenade should have 'aoe' special property"
        assert "one_use" in grenade.special, "Grenade should be one-use"

    def test_frag_grenade_aoe_not_implemented_note(self):
        """Grenade should have documentation note about AoE not being implemented."""
        grenade = WEAPON_LIBRARY["grenade"]
        # Check that special list contains aoe (even though targeting not implemented)
        assert "aoe" in grenade.special
        # Note: The actual implementation comment should be in weapons.py near the grenade definition


class TestWeaponValidation:
    """Test weapon validation and error handling."""

    def test_get_weapon_raises_error_for_missing(self):
        """get_weapon() should raise KeyError for non-existent weapons."""
        with pytest.raises(KeyError) as exc_info:
            get_weapon("nonexistent_weapon_xyz")

        assert "nonexistent_weapon_xyz" in str(exc_info.value)
        assert "not found in WEAPON_LIBRARY" in str(exc_info.value)

    def test_get_weapon_returns_valid_weapon_object(self):
        """get_weapon() should return Weapon objects for valid IDs."""
        weapon = get_weapon("pistol")
        assert isinstance(weapon, Weapon)
        assert weapon.name == "Pistol"

    def test_all_weapons_have_required_fields(self):
        """All weapons in library should have required fields populated."""
        for weapon_id, weapon in WEAPON_LIBRARY.items():
            assert weapon.name, f"{weapon_id} missing name"
            assert weapon.skill, f"{weapon_id} missing skill"
            assert weapon.damage_type in ["stun", "wound", "mixed"], \
                   f"{weapon_id} has invalid damage_type: {weapon.damage_type}"
            assert isinstance(weapon.special, list), f"{weapon_id} special should be list"


class TestWeaponStats:
    """Test weapon stats are reasonable and follow YAGS conventions."""

    def test_melee_weapons_have_reach_and_defence(self):
        """Melee weapons should have reach and defence values."""
        melee_weapons = {
            wid: w for wid, w in WEAPON_LIBRARY.items()
            if not w.is_ranged and w.skill in ["Melee", "Brawl"]
        }

        assert len(melee_weapons) > 0, "Should have melee weapons"

        for weapon_id, weapon in melee_weapons.items():
            # Melee weapons can have 0 defence (some are pure offensive)
            # but should have reach defined
            assert weapon.reach >= 0, f"{weapon_id} should have non-negative reach"

    def test_ranged_weapons_have_range_stats(self):
        """Ranged weapons should have range statistics."""
        ranged_weapons = {
            wid: w for wid, w in WEAPON_LIBRARY.items()
            if w.is_ranged
        }

        assert len(ranged_weapons) > 0, "Should have ranged weapons"

        for weapon_id, weapon in ranged_weapons.items():
            assert weapon.short_range > 0, f"{weapon_id} missing short_range"
            assert weapon.medium_range >= weapon.short_range, \
                   f"{weapon_id} medium_range < short_range"
            assert weapon.long_range >= weapon.medium_range, \
                   f"{weapon_id} long_range < medium_range"


class TestGunsDamageBoost:
    """Verify all Guns-skill weapons have +2 damage boost applied."""

    # Expected damage values after +2 boost
    EXPECTED_GUN_DAMAGE = {
        "pistol": 6,
        "rifle": 7,           # Assault Rifle
        "sniper_rifle": 10,
        "heavy_weapon": 8,    # Heavy Machine Gun
        "shotgun": 8,
        "tranq_gun": 4,
        "stun_gun": 6,
        "hacking_toolkit": 5,
        "custom_energy_weapon": 7,
        "shrike_cannon": 8,
        "spark_pulse_rifle": 8,
        "hollowed_repeater": 6,
        "union_heavy_pistol": 6,
        "oathpiercer_carbine": 6,
        "debtbreaker_sidearm": 6,
        "drip_veil_projector": 4,
        "beat_up_pistol": 5,
        "compact_emp_pistol": 5,
    }

    def test_all_guns_weapons_have_boosted_damage(self):
        """Every Guns-skill weapon should have +2 damage from balance patch."""
        for weapon_id, expected_damage in self.EXPECTED_GUN_DAMAGE.items():
            weapon = WEAPON_LIBRARY[weapon_id]
            assert weapon.skill == "Guns", f"{weapon_id} should be Guns skill"
            assert weapon.damage == expected_damage, (
                f"{weapon_id} ({weapon.name}): expected damage={expected_damage}, "
                f"got {weapon.damage}"
            )

    def test_guns_weapon_count(self):
        """Should have exactly 18 Guns-skill weapons."""
        guns_weapons = [
            wid for wid, w in WEAPON_LIBRARY.items()
            if w.skill == "Guns"
        ]
        assert len(guns_weapons) == 18, (
            f"Expected 18 Guns weapons, got {len(guns_weapons)}: {guns_weapons}"
        )

    def test_melee_weapons_unchanged_by_gun_boost(self):
        """Melee weapons should NOT be affected by guns boost."""
        melee_expected = {
            "baton": 5,          # +3 melee boost from prior patch
            "combat_knife": 6,
            "void_blade": 8,
            "ritual_blade": 7,
            "mnemonic_blade": 8,
            "ash_pulse_pike": 7,
            "breach_hammer": 10,
            "sparkspike_dagger": 7,
            "wraithroot_vineblade": 5,
            "ritual_staff": 5,
            "void_cloak": 4,
        }
        for weapon_id, expected_damage in melee_expected.items():
            weapon = WEAPON_LIBRARY[weapon_id]
            assert weapon.damage == expected_damage, (
                f"Melee weapon {weapon_id} damage should be {expected_damage}, "
                f"got {weapon.damage}"
            )
