"""Invariants for the non-lethal off-ramp.

Two checks, from two different failures in session a8ca2b7f:

`weapon_substituted` — the actor declared one weapon and the engine resolved a
different one. Corin declared the Tranquilizer Gun in all four rounds and every
`combat_action` recorded the Oathpiercer Carbine, wound damage, 2-3 wounds each
time. Note this could NOT have been caught on that file: the substitution
happened before logging, and the typed record had no field for the declared
weapon at all. `declared_weapon` was added to `combat_action` precisely so this
becomes auditable.

`stun_weapon_dealt_wounds` — a non-lethal weapon that produced wounds. This is
the downstream signature of the same class of fault, and it stays valuable if
the routing is ever bypassed another way.
"""

import pytest

from scripts.session_invariants import (
    ERROR, check, ids, inv_stun_weapon_dealt_wounds, inv_weapon_substituted,
)


def combat(weapon, declared=None, wounds=0, damage_type="wound", round_=1,
           attacker="Sergeant Corin Ireveth"):
    return {
        "event_type": "combat_action",
        "round": round_,
        "attacker": {"id": "player_02", "name": attacker},
        "defender": {"id": "enemy_1", "name": "Threshold Acolyte Nyv Rift"},
        "weapon": weapon,
        "declared_weapon": declared,
        "damage": {"damage_type": damage_type, "dealt": 16},
        "wounds_dealt": wounds,
    }


class TestWeaponSubstitution:

    def test_matching_weapon_is_clean(self):
        assert inv_weapon_substituted(
            [combat("Tranquilizer Gun", declared="Tranquilizer Gun")], {}) == []

    def test_substitution_is_an_error(self):
        """The a8ca2b7f shape: declared non-lethal, resolved lethal."""
        violations = inv_weapon_substituted(
            [combat("Oathpiercer Carbine", declared="Tranquilizer Gun", wounds=3)], {})

        assert len(violations) == 1
        assert violations[0].severity == ERROR
        assert "Tranquilizer Gun" in violations[0].message

    def test_partial_name_is_not_a_substitution(self):
        """Models write 'the tranquilizer'; resolution names it in full."""
        assert inv_weapon_substituted(
            [combat("Tranquilizer Gun", declared="tranquilizer")], {}) == []

    def test_no_declaration_is_not_a_substitution(self):
        """Omitting the field means 'use my equipped weapon' — not a mismatch."""
        assert inv_weapon_substituted([combat("Oathpiercer Carbine")], {}) == []

    def test_old_sessions_without_the_field_are_clean(self):
        """Files predating declared_weapon must not light up retroactively."""
        event = combat("Oathpiercer Carbine")
        del event["declared_weapon"]

        assert inv_weapon_substituted([event], {}) == []


class TestStunWeaponDealtWounds:

    def test_stun_weapon_dealing_stuns_is_clean(self):
        assert inv_stun_weapon_dealt_wounds(
            [combat("Tranquilizer Gun", damage_type="stun", wounds=0)], {}) == []

    def test_stun_weapon_dealing_wounds_is_an_error(self):
        violations = inv_stun_weapon_dealt_wounds(
            [combat("Tranquilizer Gun", damage_type="wound", wounds=3)], {})

        assert len(violations) == 1
        assert violations[0].severity == ERROR

    def test_lethal_weapon_dealing_wounds_is_fine(self):
        assert inv_stun_weapon_dealt_wounds(
            [combat("Oathpiercer Carbine", damage_type="wound", wounds=3)], {}) == []

    def test_unknown_weapon_is_ignored(self):
        """DM-invented weapon names must not crash or false-positive."""
        assert inv_stun_weapon_dealt_wounds(
            [combat("Improvised Chair Leg", wounds=2)], {}) == []

    def test_mixed_weapons_may_wound(self):
        assert inv_stun_weapon_dealt_wounds(
            [combat("Ritual Blade", damage_type="mixed", wounds=1)], {}) == []


class TestRegisteredInTheSuite:

    def test_both_run_from_check(self):
        events = [combat("Oathpiercer Carbine", declared="Tranquilizer Gun", wounds=3)]

        assert "weapon_substituted" in ids(check(events))
