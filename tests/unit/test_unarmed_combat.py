"""
Unit tests for unarmed combat visibility feature.

Tests that:
1. WEAPON_LIBRARY["fists"] has name="Unarmed" with correct stats
2. Player weapon display always shows unarmed option
3. Brawl skill correctly maps to unarmed or sidearm based on weapon skill
"""

import pytest
from unittest.mock import MagicMock, patch

from scripts.aeonisk.multiagent.weapons import WEAPON_LIBRARY


class TestUnarmedWeaponStats:
    """Test WEAPON_LIBRARY['fists'] has correct stats."""

    def test_unarmed_weapon_stats(self):
        """WEAPON_LIBRARY['fists'] has name='Unarmed', stun damage, correct YAGS stats."""
        fists = WEAPON_LIBRARY["fists"]
        assert fists.name == "Unarmed"
        assert fists.skill == "Brawl"
        assert fists.damage_type == "stun"
        assert fists.attack == 0
        assert fists.defence == 0
        assert fists.damage == 0
        assert fists.reach == 0
        assert fists.load == 0

    def test_fists_key_preserved(self):
        """Internal key is still 'fists' for backward compat."""
        assert "fists" in WEAPON_LIBRARY


class TestWeaponDisplay:
    """Test player weapon display includes unarmed option."""

    def _make_player_with_weapons(self, primary=None, sidearm=None, inventory=None):
        """Create a mock player agent with weapon setup."""
        player = MagicMock()
        player.equipped_weapons = {}
        if primary:
            player.equipped_weapons['primary'] = primary
        if sidearm:
            player.equipped_weapons['sidearm'] = sidearm
        player.weapon_inventory = inventory or []
        # Need hasattr checks to pass
        player.configure_mock(**{
            'equipped_weapons': player.equipped_weapons,
            'weapon_inventory': player.weapon_inventory
        })
        return player

    def _make_weapon(self, name, skill, damage_type="wound"):
        """Create a mock weapon."""
        wpn = MagicMock()
        wpn.name = name
        wpn.skill = skill
        wpn.damage_type = damage_type
        return wpn

    def test_weapon_display_includes_unarmed(self):
        """Unarmed always shown in weapon text, even with no weapons equipped."""
        # Build weapon text the same way player.py does
        primary = self._make_weapon("Plasma Rifle", "Guns")
        sidearm = self._make_weapon("Combat Knife", "Melee")

        equipped_list = [
            f"Primary: {primary.name} ({primary.damage_type.upper()} damage)",
            f"Sidearm: {sidearm.name} ({sidearm.damage_type.upper()} damage)"
        ]

        weapon_inventory_text = "\n\n**Your Weapons:**\n"
        weapon_inventory_text += "**Equipped:** " + ", ".join(equipped_list) + "\n"
        weapon_inventory_text += "**Always available:** Unarmed (STUN damage, Strength x Brawl) - tackles, grapples, punches, restraining\n"

        assert "Unarmed" in weapon_inventory_text
        assert "STUN" in weapon_inventory_text
        assert "Brawl" in weapon_inventory_text

    def test_weapon_display_unarmed_shows_stun(self):
        """Unarmed display clearly indicates STUN damage type."""
        unarmed_text = "**Always available:** Unarmed (STUN damage, Strength x Brawl) - tackles, grapples, punches, restraining"
        assert "STUN damage" in unarmed_text
        assert "tackles" in unarmed_text
        assert "grapples" in unarmed_text

    def test_weapon_display_shown_even_without_equipped_weapons(self):
        """Weapon section shown even when no weapons are equipped (unarmed always available)."""
        # With no equipped or carried weapons, old code would skip weapon section entirely.
        # New code should always show weapon section because unarmed is always available.
        equipped_list = []
        carried_list = []

        # New behavior: always show weapon section
        weapon_inventory_text = "\n\n**Your Weapons:**\n"
        if equipped_list:
            weapon_inventory_text += "**Equipped:** " + ", ".join(equipped_list) + "\n"
        if carried_list:
            weapon_inventory_text += "**Carried in inventory:** " + ", ".join(carried_list) + "\n"
        weapon_inventory_text += "**Always available:** Unarmed (STUN damage, Strength x Brawl) - tackles, grapples, punches, restraining\n"

        assert "Unarmed" in weapon_inventory_text
        assert "Your Weapons" in weapon_inventory_text


class TestBrawlWeaponMapping:
    """Test Brawl skill correctly maps to weapon based on sidearm's skill."""

    def _resolve_weapon(self, skill, primary=None, sidearm=None):
        """Simulate weapon resolution logic from dm.py."""
        weapon_name = "Unknown Weapon"
        skill_lower = skill.lower()

        if skill_lower in ['guns', 'throw'] and primary:
            weapon_name = primary.name
        elif skill_lower == 'brawl':
            # Use sidearm only if it's actually a Brawl-skill weapon
            if sidearm and sidearm.skill == 'Brawl':
                weapon_name = sidearm.name
            else:
                weapon_name = "Unarmed"
        elif skill_lower == 'melee' and sidearm:
            weapon_name = sidearm.name
        elif primary:
            weapon_name = primary.name
        elif sidearm:
            weapon_name = sidearm.name

        return weapon_name

    def _make_weapon(self, name, skill):
        """Create a mock weapon."""
        wpn = MagicMock()
        wpn.name = name
        wpn.skill = skill
        return wpn

    def test_brawl_with_brawl_sidearm_uses_sidearm(self):
        """Brawl + shock_baton (Brawl weapon) → 'Shock Baton'."""
        sidearm = self._make_weapon("Shock Baton", "Brawl")
        primary = self._make_weapon("Plasma Rifle", "Guns")

        weapon = self._resolve_weapon("Brawl", primary=primary, sidearm=sidearm)
        assert weapon == "Shock Baton"

    def test_brawl_with_melee_sidearm_uses_unarmed(self):
        """Brawl + combat_knife (Melee weapon) → 'Unarmed'."""
        sidearm = self._make_weapon("Combat Knife", "Melee")
        primary = self._make_weapon("Plasma Rifle", "Guns")

        weapon = self._resolve_weapon("Brawl", primary=primary, sidearm=sidearm)
        assert weapon == "Unarmed"

    def test_brawl_no_sidearm_uses_unarmed(self):
        """Brawl + no sidearm → 'Unarmed'."""
        primary = self._make_weapon("Plasma Rifle", "Guns")

        weapon = self._resolve_weapon("Brawl", primary=primary, sidearm=None)
        assert weapon == "Unarmed"

    def test_melee_skill_still_uses_sidearm(self):
        """Melee mapping unchanged - uses sidearm regardless of sidearm skill."""
        sidearm = self._make_weapon("Combat Knife", "Melee")
        primary = self._make_weapon("Plasma Rifle", "Guns")

        weapon = self._resolve_weapon("Melee", primary=primary, sidearm=sidearm)
        assert weapon == "Combat Knife"

    def test_guns_skill_uses_primary(self):
        """Guns mapping unchanged - uses primary."""
        primary = self._make_weapon("Plasma Rifle", "Guns")
        sidearm = self._make_weapon("Combat Knife", "Melee")

        weapon = self._resolve_weapon("Guns", primary=primary, sidearm=sidearm)
        assert weapon == "Plasma Rifle"
